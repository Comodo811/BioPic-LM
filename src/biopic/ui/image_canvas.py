"""Qt image canvas with zoom, pan, and inspection support."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QKeySequence,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from biopic.imaging.display import DisplayShellState, DisplayTileCache
from biopic.imaging.io import load_asset_pixels
from biopic.models.annotations import AnnotationKind, AnnotationObject
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import (
    Measurement,
    MeasurementKind,
    MeasurementLabelAlignment,
    ScaleBar,
)
from biopic.ui.app_icon import biopic_logo_path
from biopic.ui.fonts import safe_font_family
from biopic.ui.image_canvas_items import (
    _AnnotationHandleItem,
    _ProjectionItem,
    _SelectionHandleItem,
)
from biopic.ui.image_canvas_overlays import (
    ImageCanvasOverlaysMixin,
    _annotation_path,
    _measurement_label_position,
    _measurement_path,
    _measurement_side_labels,
    _measurement_text_items,
    _midpoint,
    _optional_color,
    _pixel_value,
    _preview_points,
    _rects_intersect,
    _scale_bar_origin,
    np_degrees_qpoints,
)
from biopic.ui.image_canvas_selection import ImageCanvasSelectionMixin, _distance_points
from biopic.ui.image_conversion import (
    display_range as _display_range,
)
from biopic.ui.image_conversion import (
    first_display_plane_view as _first_display_plane_view,
)
from biopic.ui.image_conversion import (
    layer_preview_qimage,
    paint_overlay_qimage,
)
from biopic.ui.image_conversion import ndarray_to_qimage as ndarray_to_qimage
from biopic.ui.image_conversion import (
    owned_first_display_plane as _owned_first_display_plane,
)
from biopic.ui.tool_modes import PAINT_TOOL_MODES, POINT_TOOL_MODES


class ImageCanvas(ImageCanvasOverlaysMixin, ImageCanvasSelectionMixin, QGraphicsView):
    """A zoomable microscopy image preview canvas."""

    pixelInspected = Signal(int, int, str)
    pointClicked = Signal(int, int)
    paintPointMoved = Signal(float, float)
    paintStrokeStarted = Signal()
    paintStrokeFinished = Signal()
    cloneSourceSelected = Signal(int, int)
    viewZoomAboutToChange = Signal()
    layerDragStarted = Signal(int, int)
    layerDragMoved = Signal(int, int, int, int)
    layerDragFinished = Signal(int, int, int, int)
    annotationSelected = Signal(str)
    annotationDeleteRequested = Signal(str)
    annotationTransformed = Signal(str, object)
    annotationShapeSelected = Signal(int, int, int, int)
    annotationTransformFinished = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    rectangleSelected = Signal(int, int, int, int)
    lineSelected = Signal(int, int, int, int)
    selectionCompleted = Signal(str, int, int, int, int, object)
    rotationCommitted = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QColor("#3f3f3f"))
        self._tile_size = 256
        self._tile_items: dict[tuple[int, int], None] = {}
        self._projection_item = _ProjectionItem(self._tile_size)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setVisible(False)
        self._selection_item = QGraphicsRectItem()
        self._selection_item.setPen(QPen(Qt.GlobalColor.yellow, 1, Qt.PenStyle.DashLine))
        self._selection_item.setVisible(False)
        self._selection_path_item = QGraphicsPathItem()
        self._selection_path_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._selection_path_item.setVisible(False)
        self._selection_shadow_item = QGraphicsPathItem()
        self._selection_shadow_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._selection_shadow_item.setVisible(False)
        self._paint_preview_item = QGraphicsPathItem()
        self._paint_preview_item.setVisible(False)
        self._paint_preview_item.setZValue(10.0)
        self._line_preview_item = QGraphicsPathItem()
        self._line_preview_item.setPen(QPen(Qt.GlobalColor.yellow, 1, Qt.PenStyle.DashLine))
        self._line_preview_item.setVisible(False)
        self._line_preview_item.setZValue(10.0)
        self._rotation_outline_item = QGraphicsPathItem()
        self._rotation_outline_item.setPen(QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine))
        self._rotation_outline_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._rotation_outline_item.setVisible(False)
        self._rotation_outline_item.setZValue(11.0)
        self._crop_cut_preview_item = QGraphicsPathItem()
        self._crop_cut_preview_item.setPen(QPen(Qt.PenStyle.NoPen))
        self._crop_cut_preview_item.setBrush(QBrush(QColor(0, 0, 0, 120)))
        self._crop_cut_preview_item.setVisible(False)
        self._crop_cut_preview_item.setZValue(12.0)
        self._move_preview_clip = QGraphicsRectItem()
        self._move_preview_clip.setPen(QPen(Qt.PenStyle.NoPen))
        self._move_preview_clip.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._move_preview_clip.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape,
            True,
        )
        self._move_preview_clip.setZValue(6.0)
        self._move_preview_clip.setVisible(False)
        self._move_preview_item = QGraphicsPixmapItem(self._move_preview_clip)
        self._move_preview_item.setZValue(7.0)
        self._paint_preview_segments: list[QGraphicsPathItem] = []
        self._paint_preview_tail: tuple[int, int] | None = None
        self._paint_overlay_items: dict[tuple[int, int], QGraphicsPixmapItem] = {}
        self._paint_overlay_region_items: list[
            tuple[tuple[int, int, int, int], QGraphicsPixmapItem]
        ] = []
        self._scale_bar_items: list[
            QGraphicsPathItem | QGraphicsRectItem | QGraphicsSimpleTextItem
        ] = []
        self._annotation_items: list[QGraphicsPathItem | QGraphicsSimpleTextItem] = []
        self._annotation_edit_items: list[QGraphicsPathItem | QGraphicsRectItem | _AnnotationHandleItem] = []
        self._measurement_items: list[QGraphicsPathItem | QGraphicsSimpleTextItem] = []
        self._scene.addItem(self._projection_item)
        self._scene.addItem(self._pixmap_item)
        self._scene.addItem(self._selection_item)
        self._scene.addItem(self._selection_shadow_item)
        self._scene.addItem(self._selection_path_item)
        self._scene.addItem(self._paint_preview_item)
        self._scene.addItem(self._line_preview_item)
        self._scene.addItem(self._rotation_outline_item)
        self._scene.addItem(self._crop_cut_preview_item)
        self._scene.addItem(self._move_preview_clip)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHints(self.renderHints())
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pixels: np.ndarray | None = None
        self._display_range: tuple[float, float] | None = None
        self._display_shell = DisplayShellState()
        self._display_cache = DisplayTileCache(tile_size=self._tile_size)
        self._watermark_pixmap = QPixmap(str(biopic_logo_path()))
        self._empty_watermark_visible = True
        self._tile_preview_offset = (0.0, 0.0)
        self._zoom = 1.0
        self._tool_mode = "pan"
        self._drag_start: QPointF | None = None
        self._line_drag_start: QPointF | None = None
        self._free_selection_points: list[QPointF] = []
        self._free_selection_drawing = False
        self._free_selection_hover: QPointF | None = None
        self._free_selection_press_point: QPointF | None = None
        self._free_selection_press_started_new = False
        self._free_selection_dragging = False
        self._free_selection_closed = False
        self._lasso_drag_snapshot: dict[str, object] | None = None
        self._selection_handles: list[_SelectionHandleItem] = []
        self._selected_annotation_id: str | None = None
        self._annotation_pixel_points: dict[str, list[QPointF]] = {}
        self._annotation_handle_snapshot: dict[str, object] | None = None
        self._annotation_shape_kind = AnnotationKind.LINE
        self._annotation_shape_color = QColor("#ffffff")
        self._annotation_shape_line_width = 2.0
        self._move_drag_start: QPointF | None = None
        self._rotation_dragging = False
        self._rotation_preview_angle = 0.0
        self._rotation_drag_base_angle = 0.0
        self._rotation_drag_start_pointer_angle = 0.0
        self._paint_stroke_active = False
        self._last_paint_point: QPointF | None = None
        self._selection_dash_offset = 0.0
        self._selection_timer = QTimer(self)
        self._selection_timer.setInterval(120)
        self._selection_timer.timeout.connect(self._advance_selection_marching_ants)
        self._update_selection_pens()

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)
        if (
            self._pixels is not None
            or self._watermark_pixmap.isNull()
            or not self._empty_watermark_visible
        ):
            return
        painter = QPainter(self.viewport())
        target_size = min(self.viewport().width(), self.viewport().height()) * 0.64
        if target_size <= 1:
            return
        target = QRectF(
            (self.viewport().width() - target_size) / 2.0,
            (self.viewport().height() - target_size) / 2.0,
            target_size,
            target_size,
        )
        painter.setOpacity(0.055)
        painter.drawPixmap(target, self._watermark_pixmap, QRectF(self._watermark_pixmap.rect()))

    def set_empty_watermark_visible(self, visible: bool) -> None:
        self._empty_watermark_visible = bool(visible)
        self.viewport().update()

    def set_selected_annotation_id(self, annotation_id: str | None) -> None:
        """Show edit handles for the selected annotation when supported."""
        self._selected_annotation_id = annotation_id
        self._refresh_selected_annotation_handles()

    def set_annotation_shape_preview_style(
        self,
        kind: AnnotationKind,
        color: str,
        line_width: float,
    ) -> None:
        """Set the live preview style used while drawing annotation shapes."""
        self._annotation_shape_kind = kind
        preview_color = QColor(color)
        self._annotation_shape_color = preview_color if preview_color.isValid() else QColor("#ffffff")
        self._annotation_shape_line_width = max(1.0, float(line_width))

    def set_asset(self, asset: ImageAsset | None) -> None:
        """Load and display an image asset."""
        if asset is None:
            self._pixels = None
            self._display_range = None
            self._clear_tile_items()
            self.clear_layer_move_preview()
            self._selection_item.setVisible(False)
            self._selection_path_item.setVisible(False)
            self._selection_shadow_item.setVisible(False)
            self._clear_selection_handles()
            self._stop_selection_marching_ants_if_hidden()
            self.clear_paint_preview()
            self.clear_rotation_preview()
            self.clear_crop_cut_preview()
            self.set_scale_bars([])
            self.set_annotations([])
            self.set_measurements([])
            self._scene.setSceneRect(0, 0, 1, 1)
            return
        pixels = load_asset_pixels(asset)
        self.set_pixels(pixels, Path(asset.path).name)

    def set_pixels(self, pixels: np.ndarray, label: str = "", *, fit: bool = True) -> None:
        """Display a pixel array."""
        self._pixels = _owned_first_display_plane(pixels)
        self._display_range = _display_range(self._pixels)
        self._display_shell.set_image_size(self._pixels.shape[1], self._pixels.shape[0])
        self._display_cache.invalidate_full()
        self.clear_paint_preview()
        self.clear_rotation_preview()
        self.clear_crop_cut_preview()
        self._rebuild_tile_items()
        self._projection_item.set_pixels(self._pixels, self._display_range)
        self._scene.setSceneRect(0, 0, self._pixels.shape[1], self._pixels.shape[0])
        self._move_preview_clip.setRect(
            QRectF(0, 0, self._pixels.shape[1], self._pixels.shape[0])
        )
        if fit:
            self._selection_item.setVisible(False)
            self._selection_path_item.setVisible(False)
            self._selection_shadow_item.setVisible(False)
            self._clear_selection_handles()
            self._stop_selection_marching_ants_if_hidden()
            self.fit_to_window()
        tooltip = "" if label.lower().startswith("adjusted preview") else label
        self.setToolTip(tooltip)

    def update_tile_region(self, pixels: np.ndarray, rect: tuple[int, int, int, int]) -> None:
        """Update only display tiles intersecting a dirty pixel region."""
        self.update_tile_regions(pixels, [rect])

    def visible_image_rect(self) -> tuple[int, int, int, int] | None:
        """Return the image-space rectangle currently visible in the viewport."""
        if self._pixels is None:
            return None
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        image_rect = visible.intersected(QRectF(0, 0, self._pixels.shape[1], self._pixels.shape[0]))
        if image_rect.isEmpty():
            return None
        x0 = max(0, int(np.floor(image_rect.left())))
        y0 = max(0, int(np.floor(image_rect.top())))
        x1 = min(self._pixels.shape[1], int(np.ceil(image_rect.right())) + 1)
        y1 = min(self._pixels.shape[0], int(np.ceil(image_rect.bottom())) + 1)
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1 - x0, y1 - y0)

    def set_selection_rect(self, rect: tuple[int, int, int, int] | None) -> None:
        """Display a selection rectangle computed by a tool."""
        if rect is None:
            self._selection_item.setVisible(False)
            self._selection_path_item.setVisible(False)
            self._selection_shadow_item.setVisible(False)
            self._free_selection_drawing = False
            self._free_selection_hover = None
            self._free_selection_closed = False
            self._free_selection_points = []
            self._clear_selection_handles()
            self._stop_selection_marching_ants_if_hidden()
            return
        x, y, width, height = rect
        if self._tool_mode == "ellipse_select":
            self._clear_selection_handles()
            path = QPainterPath()
            path.addEllipse(QRectF(float(x), float(y), float(width), float(height)))
            self._selection_path_item.setPath(path)
            self._set_selection_path_visible(True)
        else:
            self._clear_selection_handles()
            path = QPainterPath()
            path.addRect(QRectF(float(x), float(y), float(width), float(height)))
            self._selection_path_item.setPath(path)
            self._set_selection_path_visible(True)

    def update_tile_regions(
        self, pixels: np.ndarray, rects: list[tuple[int, int, int, int]]
    ) -> None:
        """Update display tiles intersecting dirty pixel regions once per tile."""
        display_pixels = _first_display_plane_view(pixels)
        if (
            self._pixels is None
            or self._pixels.shape != display_pixels.shape
            or self._pixels.dtype != display_pixels.dtype
        ):
            self.set_pixels(display_pixels, fit=False)
            return
        dirty_tiles: set[tuple[int, int]] = set()
        for rect in rects:
            x, y, width, height = rect
            if width <= 0 or height <= 0:
                continue
            x0 = max(0, x)
            y0 = max(0, y)
            x1_clip = min(self._pixels.shape[1], x + width)
            y1_clip = min(self._pixels.shape[0], y + height)
            if x1_clip <= x0 or y1_clip <= y0:
                continue
            x, y, width, height = x0, y0, x1_clip - x0, y1_clip - y0
            clipped_rect = self._display_shell.invalidate_area((x, y, width, height))
            if clipped_rect is not None:
                self._display_cache.invalidate_area(clipped_rect)
            self._pixels[y : y + height, x : x + width] = display_pixels[
                y : y + height, x : x + width
            ]
            tile_x0 = max(0, x // self._tile_size)
            tile_y0 = max(0, y // self._tile_size)
            tile_x1 = min(
                (self._pixels.shape[1] - 1) // self._tile_size,
                (x + width - 1) // self._tile_size,
            )
            tile_y1 = min(
                (self._pixels.shape[0] - 1) // self._tile_size,
                (y + height - 1) // self._tile_size,
            )
            for tile_y in range(tile_y0, tile_y1 + 1):
                for tile_x in range(tile_x0, tile_x1 + 1):
                    dirty_tiles.add((tile_x, tile_y))
        self._projection_item.update_regions(rects)

    def update_tile_region_patch(
        self,
        patch: np.ndarray,
        rect: tuple[int, int, int, int],
    ) -> None:
        """Update display pixels from a patch matching one image-space rectangle."""
        if self._pixels is None:
            return
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            return
        display_patch = _first_display_plane_view(patch)
        if display_patch.shape[:2] != (height, width):
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self._pixels.shape[1], x + width)
        y1 = min(self._pixels.shape[0], y + height)
        if x1 <= x0 or y1 <= y0:
            return
        px0 = x0 - x
        py0 = y0 - y
        clipped = (x0, y0, x1 - x0, y1 - y0)
        self._pixels[y0:y1, x0:x1] = display_patch[
            py0 : py0 + clipped[3],
            px0 : px0 + clipped[2],
        ]
        invalidated = self._display_shell.invalidate_area(clipped)
        if invalidated is not None:
            self._display_cache.invalidate_area(invalidated)
        self._projection_item.update_regions([clipped])

    def update_paint_overlay_regions(
        self, preview_pixels: np.ndarray, rects: list[tuple[int, int, int, int]]
    ) -> None:
        """Update active paint overlay tiles without replacing committed image tiles."""
        if self._pixels is None:
            return
        display_pixels = _first_display_plane_view(preview_pixels)
        if display_pixels.shape != self._pixels.shape:
            return
        dirty_tiles: set[tuple[int, int]] = set()
        for rect in rects:
            x, y, width, height = rect
            if width <= 0 or height <= 0:
                continue
            x0 = max(0, x)
            y0 = max(0, y)
            x1_clip = min(self._pixels.shape[1], x + width)
            y1_clip = min(self._pixels.shape[0], y + height)
            if x1_clip <= x0 or y1_clip <= y0:
                continue
            tile_x0 = max(0, x0 // self._tile_size)
            tile_y0 = max(0, y0 // self._tile_size)
            tile_x1 = min(
                (self._pixels.shape[1] - 1) // self._tile_size,
                (x1_clip - 1) // self._tile_size,
            )
            tile_y1 = min(
                (self._pixels.shape[0] - 1) // self._tile_size,
                (y1_clip - 1) // self._tile_size,
            )
            for tile_y in range(tile_y0, tile_y1 + 1):
                for tile_x in range(tile_x0, tile_x1 + 1):
                    dirty_tiles.add((tile_x, tile_y))
        for tile_x, tile_y in sorted(dirty_tiles):
            self._update_paint_overlay_tile(display_pixels, tile_x, tile_y)

    def update_paint_overlay_patches(
        self, patches: list[tuple[tuple[int, int, int, int], np.ndarray]]
    ) -> None:
        """Update active paint overlay from dirty-region patches only."""
        if self._pixels is None:
            return
        for rect, patch in patches:
            x, y, width, height = rect
            if width <= 0 or height <= 0:
                continue
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(self._pixels.shape[1], x + width)
            y1 = min(self._pixels.shape[0], y + height)
            if x1 <= x0 or y1 <= y0:
                continue
            patch_view = _first_display_plane_view(patch)
            clipped_width = x1 - x0
            clipped_height = y1 - y0
            patch_x = x0 - x
            patch_y = y0 - y
            patch_region = patch_view[
                patch_y : patch_y + clipped_height,
                patch_x : patch_x + clipped_width,
            ]
            base_region = self._pixels[y0:y1, x0:x1]
            overlay = paint_overlay_qimage(patch_region, base_region, self._display_range)
            clipped_rect = (x0, y0, clipped_width, clipped_height)
            self._remove_paint_overlay_regions_intersecting(clipped_rect)
            if overlay.isNull():
                continue
            item = QGraphicsPixmapItem()
            item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
            item.setZValue(8.0)
            item.setPixmap(QPixmap.fromImage(overlay))
            item.setPos(float(x0), float(y0))
            self._paint_overlay_region_items.append((clipped_rect, item))
            self._scene.addItem(item)

    def image_size(self) -> tuple[int, int] | None:
        """Return current image dimensions as width, height."""
        if self._pixels is None:
            return None
        return int(self._pixels.shape[1]), int(self._pixels.shape[0])

    def set_tool_mode(self, mode: str) -> None:
        """Set how mouse input should manipulate the image canvas."""
        if mode not in {"measure_line", "annotation_shape"}:
            self._line_drag_start = None
            self._line_preview_item.setVisible(False)
        if self._tool_mode == "free_select" and mode != "free_select":
            self._free_selection_drawing = False
            self._free_selection_hover = None
            self._free_selection_closed = False
        self._tool_mode = mode
        if mode == "pan":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif mode == "move":
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
        elif mode in {
            "select",
            "ellipse_select",
            "free_select",
            "crop",
            "measure_line",
            "rotate",
            "annotation_shape",
        }:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self._update_rotation_outline()

    def fit_to_window(self) -> None:
        """Fit the image to the viewport."""
        if self._pixels is None:
            return
        self.fitInView(
            QRectF(0, 0, self._pixels.shape[1], self._pixels.shape[0]),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._zoom = self.transform().m11()
        self._display_shell.set_scale(self._zoom)

    def actual_size(self) -> None:
        """Show the image at one screen pixel per image pixel."""
        self.resetTransform()
        self._zoom = 1.0
        self._display_shell.actual_size()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom under the mouse wheel."""
        self.viewZoomAboutToChange.emit()
        self._zoom_at_view_position(
            event.position().toPoint(),
            1.25 if event.angleDelta().y() > 0 else 0.8,
        )

    def _zoom_at_view_position(self, cursor_pos: QPoint, factor: float) -> None:
        """Zoom while keeping the scene point under ``cursor_pos`` stable."""
        scene_before = self.mapToScene(cursor_pos)
        self.scale(factor, factor)
        self._zoom *= factor
        self._display_shell.zoom_by(factor)
        scene_after = self.mapToScene(cursor_pos)
        delta = scene_after - scene_before
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - round(delta.x() * self.transform().m11())
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - round(delta.y() * self.transform().m22())
        )

    def refresh_display_tiles(self) -> None:
        """Rebuild current tile pixmaps from the owned display buffer."""
        if self._pixels is None:
            return
        self._projection_item.update()

    def set_tile_preview_offset(self, dx: float, dy: float) -> None:
        """Move the displayed tiles without rebuilding image data."""
        if self._tile_preview_offset == (dx, dy):
            return
        self._tile_preview_offset = (dx, dy)
        self._display_shell.set_offsets(dx, dy)

    def clear_tile_preview_offset(self) -> None:
        """Clear a temporary tile movement preview."""
        self.set_tile_preview_offset(0.0, 0.0)

    def begin_layer_move_preview(
        self,
        content: np.ndarray,
        alpha: np.ndarray,
        offset_x: float,
        offset_y: float,
        *,
        opacity: float = 1.0,
    ) -> None:
        """Show one movable layer over a fixed canvas background."""
        if self._pixels is None:
            return
        self._move_preview_clip.setRect(
            QRectF(0, 0, self._pixels.shape[1], self._pixels.shape[0])
        )
        image = layer_preview_qimage(content, alpha, self._display_range, opacity=opacity)
        self._move_preview_item.setPixmap(QPixmap.fromImage(image))
        self._move_preview_item.setPos(float(offset_x), float(offset_y))
        self._move_preview_clip.setVisible(True)

    def move_layer_preview_to(self, offset_x: float, offset_y: float) -> None:
        """Move the temporary layer preview without changing rendered tiles."""
        if self._move_preview_clip.isVisible():
            self._move_preview_item.setPos(float(offset_x), float(offset_y))

    def clear_layer_move_preview(self) -> None:
        """Remove a temporary moving-layer preview."""
        self._move_preview_item.setPixmap(QPixmap())
        self._move_preview_item.setPos(0.0, 0.0)
        self._move_preview_clip.setVisible(False)

    def clear_rotation_preview(self) -> None:
        """Reset any interactive rotation transform preview."""
        self._rotation_dragging = False
        self._rotation_preview_angle = 0.0
        self._rotation_drag_base_angle = 0.0
        self._rotation_drag_start_pointer_angle = 0.0
        self._projection_item.setTransformOriginPoint(QPointF(0.0, 0.0))
        self._projection_item.setRotation(0.0)
        self._rotation_outline_item.setVisible(False)

    def set_crop_cut_preview_rect(self, rect: tuple[int, int, int, int] | None) -> None:
        """Darken the parts outside the crop result rectangle."""
        if self._pixels is None or rect is None:
            self.clear_crop_cut_preview()
            return
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            self.clear_crop_cut_preview()
            return
        full = QPainterPath()
        full.addRect(QRectF(0, 0, self._pixels.shape[1], self._pixels.shape[0]))
        keep = QPainterPath()
        keep.addRect(QRectF(float(x), float(y), float(width), float(height)))
        self._crop_cut_preview_item.setPath(full.subtracted(keep))
        self._crop_cut_preview_item.setVisible(True)

    def clear_crop_cut_preview(self) -> None:
        """Hide the crop-result hover preview."""
        self._crop_cut_preview_item.setPath(QPainterPath())
        self._crop_cut_preview_item.setVisible(False)

    def _set_rotation_preview_angle(self, angle: float) -> None:
        if self._pixels is None:
            return
        self._rotation_preview_angle = float(angle)
        center = self._rotation_center()
        self._projection_item.setTransformOriginPoint(center)
        self._projection_item.setRotation(self._rotation_preview_angle)
        self._update_rotation_outline()

    def _update_rotation_outline(self) -> None:
        if self._pixels is None or self._tool_mode != "rotate":
            self._rotation_outline_item.setVisible(False)
            return
        width = float(self._pixels.shape[1])
        height = float(self._pixels.shape[0])
        center = self._rotation_center()
        corners = [
            self._rotated_image_point(QPointF(0.0, 0.0), center, self._rotation_preview_angle),
            self._rotated_image_point(QPointF(width, 0.0), center, self._rotation_preview_angle),
            self._rotated_image_point(QPointF(width, height), center, self._rotation_preview_angle),
            self._rotated_image_point(QPointF(0.0, height), center, self._rotation_preview_angle),
        ]
        top_center = self._rotated_image_point(
            QPointF(width * 0.5, -max(18.0, min(width, height) * 0.08)),
            center,
            self._rotation_preview_angle,
        )
        path = QPainterPath(corners[0])
        for corner in corners[1:]:
            path.lineTo(corner)
        path.closeSubpath()
        path.moveTo(
            QPointF(
                (corners[0].x() + corners[1].x()) * 0.5,
                (corners[0].y() + corners[1].y()) * 0.5,
            )
        )
        path.lineTo(top_center)
        handle_radius = max(4.0, min(width, height) * 0.015)
        path.addEllipse(
            QRectF(
                top_center.x() - handle_radius,
                top_center.y() - handle_radius,
                handle_radius * 2.0,
                handle_radius * 2.0,
            )
        )
        self._rotation_outline_item.setPath(path)
        self._rotation_outline_item.setVisible(True)

    def _rotation_center(self) -> QPointF:
        if self._pixels is None:
            return QPointF(0.0, 0.0)
        return QPointF(self._pixels.shape[1] / 2.0, self._pixels.shape[0] / 2.0)

    def _rotated_image_point(self, point: QPointF, center: QPointF, angle: float) -> QPointF:
        radians = np.deg2rad(float(angle))
        cos_angle = float(np.cos(radians))
        sin_angle = float(np.sin(radians))
        dx = point.x() - center.x()
        dy = point.y() - center.y()
        return QPointF(
            center.x() + dx * cos_angle - dy * sin_angle,
            center.y() + dx * sin_angle + dy * cos_angle,
        )

    def _pointer_rotation_angle(self, point: QPointF) -> float:
        center = self._rotation_center()
        return float(np.degrees(np.arctan2(point.y() - center.y(), point.x() - center.x())))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start a tool action."""
        if self._pixels is None:
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        if self._tool_mode in {"select", "ellipse_select", "crop", "annotation_shape"}:
            self._drag_start = point
            self._update_drag_selection_preview(QRectF(point, point).normalized())
            return
        if self._tool_mode == "measure_line":
            self._line_drag_start = point
            self._update_line_measurement_preview(point, point)
            return
        if self._tool_mode == "free_select":
            self.setFocus()
            if self._free_selection_drawing:
                if self._is_free_selection_close_hit(point):
                    self._close_free_selection()
                else:
                    if self._lasso_handle_at(event.position().toPoint()) is not None:
                        super().mousePressEvent(event)
                        return
                    self._free_selection_press_point = point
                    self._free_selection_press_started_new = False
                    self._free_selection_dragging = False
                    self._free_selection_hover = point
                    self._update_free_selection_preview(close=False)
            else:
                if self._lasso_handle_at(event.position().toPoint()) is not None:
                    super().mousePressEvent(event)
                    return
                if self._free_selection_closed:
                    super().mousePressEvent(event)
                    return
                self._clear_selection_handles()
                self._free_selection_points = [point]
                self._free_selection_hover = point
                self._free_selection_drawing = True
                self._free_selection_press_point = point
                self._free_selection_press_started_new = True
                self._free_selection_dragging = False
                self._update_free_selection_preview(close=False)
            return
        if self._tool_mode == "move":
            annotation_id = self._annotation_at_point(point)
            if annotation_id is not None:
                self.set_selected_annotation_id(annotation_id)
                self.annotationSelected.emit(annotation_id)
                return
            self._move_drag_start = point
            self.layerDragStarted.emit(int(point.x()), int(point.y()))
            return
        if self._tool_mode == "rotate":
            if event.button() == Qt.MouseButton.LeftButton:
                self._rotation_dragging = True
                self._rotation_drag_base_angle = self._rotation_preview_angle
                self._rotation_drag_start_pointer_angle = self._pointer_rotation_angle(point)
                self._set_rotation_preview_angle(self._rotation_preview_angle)
            return
        if self._tool_mode == "zoom":
            self.viewZoomAboutToChange.emit()
            factor = 1.25 if event.button() == Qt.MouseButton.LeftButton else 0.8
            self.scale(factor, factor)
            self._zoom *= factor
            self._display_shell.zoom_by(factor)
            return
        if self._tool_mode in POINT_TOOL_MODES:
            x_float, y_float = float(point.x()), float(point.y())
            x, y = int(x_float), int(y_float)
            if 0 <= y < self._pixels.shape[0] and 0 <= x < self._pixels.shape[1]:
                if self._tool_mode in {"clone", "heal"} and (
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier
                ):
                    self.cloneSourceSelected.emit(x, y)
                    return
                if self._tool_mode in PAINT_TOOL_MODES:
                    self._paint_stroke_active = True
                    self._last_paint_point = QPointF(x_float, y_float)
                    self.paintStrokeStarted.emit()
                    self.paintPointMoved.emit(x_float, y_float)
                    return
                self.pointClicked.emit(x, y)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Report image coordinates and pixel values."""
        if self._drag_start is not None and self._tool_mode in {
            "select",
            "ellipse_select",
            "crop",
            "annotation_shape",
        }:
            point = self.mapToScene(event.position().toPoint())
            if self._tool_mode == "annotation_shape":
                self._update_annotation_shape_preview(self._drag_start, point)
            else:
                self._update_drag_selection_preview(QRectF(self._drag_start, point).normalized())
            return
        if self._line_drag_start is not None and self._tool_mode == "measure_line":
            point = self.mapToScene(event.position().toPoint())
            self._update_line_measurement_preview(self._line_drag_start, point)
            return
        if self._tool_mode == "free_select" and self._free_selection_drawing:
            point = self.mapToScene(event.position().toPoint())
            if (
                event.buttons() & Qt.MouseButton.LeftButton
                and self._free_selection_press_point is not None
            ):
                if (
                    self._free_selection_dragging
                    or _distance_points(self._free_selection_press_point, point) >= 2.0
                ):
                    self._free_selection_dragging = True
                    old_count = len(self._free_selection_points)
                    self._append_free_selection_point(
                        point,
                        minimum_distance=self._free_selection_sample_distance(),
                    )
                    if len(self._free_selection_points) != old_count:
                        self._update_free_selection_preview(close=False)
                return
            self._free_selection_hover = point
            self._update_free_selection_preview(close=False)
            return
        if (
            self._pixels is not None
            and self._tool_mode in PAINT_TOOL_MODES
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            point = self.mapToScene(event.position().toPoint())
            x_float, y_float = float(point.x()), float(point.y())
            x, y = int(x_float), int(y_float)
            if 0 <= y < self._pixels.shape[0] and 0 <= x < self._pixels.shape[1]:
                self._last_paint_point = QPointF(x_float, y_float)
                self.paintPointMoved.emit(x_float, y_float)
            return
        if self._move_drag_start is not None and self._tool_mode == "move":
            point = self.mapToScene(event.position().toPoint())
            self.layerDragMoved.emit(
                int(self._move_drag_start.x()),
                int(self._move_drag_start.y()),
                int(point.x()),
                int(point.y()),
            )
            return
        if self._rotation_dragging and self._tool_mode == "rotate":
            point = self.mapToScene(event.position().toPoint())
            delta = self._pointer_rotation_angle(point) - self._rotation_drag_start_pointer_angle
            while delta > 180.0:
                delta -= 360.0
            while delta < -180.0:
                delta += 360.0
            self._set_rotation_preview_angle(self._rotation_drag_base_angle + delta)
            return
        super().mouseMoveEvent(event)
        if self._pixels is None:
            return
        point = self.mapToScene(event.position().toPoint())
        x, y = int(point.x()), int(point.y())
        if 0 <= y < self._pixels.shape[0] and 0 <= x < self._pixels.shape[1]:
            self.pixelInspected.emit(x, y, _pixel_value(self._pixels, QPointF(x, y)))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finish a tool action."""
        if self._paint_stroke_active and self._tool_mode in PAINT_TOOL_MODES:
            point = self.mapToScene(event.position().toPoint())
            x_float, y_float = float(point.x()), float(point.y())
            x, y = int(x_float), int(y_float)
            if (
                self._pixels is not None
                and 0 <= y < self._pixels.shape[0]
                and 0 <= x < self._pixels.shape[1]
                and (
                    self._last_paint_point is None
                    or self._last_paint_point != QPointF(x_float, y_float)
                )
            ):
                self.paintPointMoved.emit(x_float, y_float)
            self._last_paint_point = None
            self._paint_stroke_active = False
            self.paintStrokeFinished.emit()
            return
        if self._move_drag_start is not None and self._tool_mode == "move":
            point = self.mapToScene(event.position().toPoint())
            self.layerDragFinished.emit(
                int(self._move_drag_start.x()),
                int(self._move_drag_start.y()),
                int(point.x()),
                int(point.y()),
            )
            self._move_drag_start = None
            return
        if self._rotation_dragging and self._tool_mode == "rotate":
            angle = float(self._rotation_preview_angle)
            self._rotation_dragging = False
            self._projection_item.setTransformOriginPoint(QPointF(0.0, 0.0))
            self._projection_item.setRotation(0.0)
            self._rotation_preview_angle = 0.0
            self._update_rotation_outline()
            if abs(angle) >= 0.05:
                self.rotationCommitted.emit(angle)
            return
        if self._tool_mode == "free_select":
            if self._free_selection_drawing and self._free_selection_press_point is not None:
                point = self.mapToScene(event.position().toPoint())
                closes_path = self._is_free_selection_close_hit(point)
                if self._free_selection_dragging:
                    if not closes_path:
                        self._append_free_selection_point(
                            point,
                            minimum_distance=self._free_selection_sample_distance(),
                        )
                elif not self._free_selection_press_started_new and not closes_path:
                    self._append_free_selection_point(point, minimum_distance=0.5)
                self._free_selection_hover = point
                self._free_selection_press_point = None
                self._free_selection_press_started_new = False
                self._free_selection_dragging = False
                if closes_path:
                    self._close_free_selection()
                else:
                    self._set_free_selection_handles(self._free_selection_points)
                    self._update_free_selection_preview(close=False)
            return
        if self._line_drag_start is not None and self._tool_mode == "measure_line":
            point = self.mapToScene(event.position().toPoint())
            start = self._line_drag_start
            self._line_drag_start = None
            self._line_preview_item.setVisible(False)
            if _distance_points(start, point) >= 2.0:
                self.lineSelected.emit(
                    int(start.x()),
                    int(start.y()),
                    int(point.x()),
                    int(point.y()),
                )
            else:
                self.pointClicked.emit(int(point.x()), int(point.y()))
            return
        if self._drag_start is None or self._tool_mode not in {
            "select",
            "ellipse_select",
            "crop",
            "annotation_shape",
        }:
            super().mouseReleaseEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        start = self._drag_start
        rect = QRectF(start, point).normalized()
        self._drag_start = None
        if self._tool_mode == "annotation_shape":
            self._line_preview_item.setVisible(False)
            self._set_selection_path_visible(False)
            if start is not None and _distance_points(start, point) >= 2.0:
                self.annotationShapeSelected.emit(
                    int(start.x()),
                    int(start.y()),
                    int(point.x()),
                    int(point.y()),
                )
            else:
                self.pointClicked.emit(int(point.x()), int(point.y()))
            return
        else:
            self._update_drag_selection_preview(rect)
        if rect.width() >= 1 and rect.height() >= 1:
            self.rectangleSelected.emit(
                int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
            )
            kind = "ellipse" if self._tool_mode == "ellipse_select" else "rectangle"
            self.selectionCompleted.emit(
                kind,
                int(rect.x()),
                int(rect.y()),
                int(rect.width()),
                int(rect.height()),
                [],
            )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Close polygonal free selections with a final straight segment."""
        point = self.mapToScene(event.position().toPoint())
        if (
            self._tool_mode == "free_select"
            and self._free_selection_closed
            and self._closed_free_selection_contains(point)
        ):
            self._commit_free_selection()
            event.accept()
            return
        if (
            self._tool_mode == "free_select"
            and self._free_selection_drawing
            and len(self._free_selection_points) >= 3
        ):
            if not self._is_free_selection_close_hit(point):
                self._append_free_selection_point(point, minimum_distance=0.5)
            self._close_free_selection()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle GIMP-like keyboard controls for the free select tool."""
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undoRequested.emit()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redoRequested.emit()
            event.accept()
            return
        if (
            event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}
            and self._selected_annotation_id is not None
        ):
            annotation_id = self._selected_annotation_id
            self.set_selected_annotation_id(None)
            self.annotationDeleteRequested.emit(annotation_id)
            event.accept()
            return
        if self._tool_mode == "free_select" and (
            self._free_selection_drawing or self._free_selection_closed
        ):
            if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                if self._free_selection_closed:
                    self._commit_free_selection()
                else:
                    self._close_free_selection()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_free_selection()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Backspace:
                if self._free_selection_closed:
                    self._reopen_free_selection()
                else:
                    self._remove_last_free_selection_point()
                event.accept()
                return
        super().keyPressEvent(event)

    def _rebuild_tile_items(self) -> None:
        self._clear_tile_items()
        if self._pixels is None:
            return
        tile_columns = (self._pixels.shape[1] + self._tile_size - 1) // self._tile_size
        tile_rows = (self._pixels.shape[0] + self._tile_size - 1) // self._tile_size
        self._tile_items = {
            (tile_x, tile_y): None
            for tile_y in range(tile_rows)
            for tile_x in range(tile_columns)
        }
        self._projection_item.set_pixels(self._pixels, self._display_range)

    def _clear_tile_items(self) -> None:
        self._tile_items.clear()
        self._display_cache.invalidate_full()
        self._clear_paint_overlay_items()
        self._projection_item.clear()
        self._pixmap_item.setPixmap(QPixmap())
        self._tile_preview_offset = (0.0, 0.0)
        self._display_shell.set_offsets(0.0, 0.0)

    def _update_paint_overlay_tile(
        self, preview_pixels: np.ndarray, tile_x: int, tile_y: int
    ) -> None:
        if self._pixels is None:
            return
        x = tile_x * self._tile_size
        y = tile_y * self._tile_size
        tile = preview_pixels[
            y : min(y + self._tile_size, preview_pixels.shape[0]),
            x : min(x + self._tile_size, preview_pixels.shape[1]),
        ]
        base_tile = self._pixels[
            y : min(y + self._tile_size, self._pixels.shape[0]),
            x : min(x + self._tile_size, self._pixels.shape[1]),
        ]
        image = paint_overlay_qimage(tile, base_tile, self._display_range)
        if image.isNull():
            old_item = self._paint_overlay_items.pop((tile_x, tile_y), None)
            if old_item is not None:
                self._scene.removeItem(old_item)
            return
        item = self._paint_overlay_items.get((tile_x, tile_y))
        if item is None:
            item = QGraphicsPixmapItem()
            item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
            item.setZValue(8.0)
            self._paint_overlay_items[(tile_x, tile_y)] = item
            self._scene.addItem(item)
        self._position_tile_item(item, tile_x, tile_y)
        item.setPixmap(QPixmap.fromImage(image))

    def _clear_paint_overlay_items(self) -> None:
        for item in self._paint_overlay_items.values():
            self._scene.removeItem(item)
        self._paint_overlay_items.clear()
        for _rect, item in self._paint_overlay_region_items:
            self._scene.removeItem(item)
        self._paint_overlay_region_items.clear()

    def _remove_paint_overlay_regions_intersecting(
        self, rect: tuple[int, int, int, int]
    ) -> None:
        kept: list[tuple[tuple[int, int, int, int], QGraphicsPixmapItem]] = []
        for existing_rect, item in self._paint_overlay_region_items:
            if _rects_intersect(existing_rect, rect):
                self._scene.removeItem(item)
            else:
                kept.append((existing_rect, item))
        self._paint_overlay_region_items = kept

    def _position_tile_item(
        self, item: QGraphicsPixmapItem, tile_x: int, tile_y: int
    ) -> None:
        dx, dy = self._tile_preview_offset
        item.setPos(
            float(tile_x * self._tile_size) + dx,
            float(tile_y * self._tile_size) + dy,
        )

    def _trim_paint_preview_segments(self) -> None:
        max_segments = 32
        while len(self._paint_preview_segments) > max_segments:
            item = self._paint_preview_segments.pop(0)
            self._scene.removeItem(item)

    def _update_line_measurement_preview(self, start: QPointF, end: QPointF) -> None:
        path = QPainterPath(start)
        path.lineTo(end)
        self._line_preview_item.setPen(QPen(Qt.GlobalColor.yellow, 1, Qt.PenStyle.DashLine))
        self._line_preview_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._line_preview_item.setPath(path)
        self._line_preview_item.setVisible(True)

    def _update_annotation_shape_preview(self, start: QPointF, end: QPointF) -> None:
        points: list[QPointF]
        if self._annotation_shape_kind is AnnotationKind.WEDGE:
            points = _wedge_points_from_axis(
                start,
                end,
                max(5.0, self._annotation_shape_line_width * 3.0),
            )
        else:
            points = [start, end]
        path = _annotation_path(
            self._annotation_shape_kind,
            points,
            self._annotation_shape_line_width,
        )
        color = QColor(self._annotation_shape_color)
        color.setAlpha(210)
        pen = QPen(color, self._annotation_shape_line_width, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._line_preview_item.setPen(pen)
        if self._annotation_shape_kind is AnnotationKind.WEDGE:
            fill = QColor(color)
            fill.setAlpha(90)
            self._line_preview_item.setBrush(QBrush(fill))
        else:
            self._line_preview_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._line_preview_item.setPath(path)
        self._line_preview_item.setVisible(True)


def _wedge_points_from_axis(
    start: QPointF,
    end: QPointF,
    minimum_half_width: float,
) -> list[QPointF]:
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux
    half_width = max(minimum_half_width, length * 0.22)
    return [
        QPointF(end),
        QPointF(start.x() + nx * half_width, start.y() + ny * half_width),
        QPointF(start.x() - nx * half_width, start.y() - ny * half_width),
    ]

