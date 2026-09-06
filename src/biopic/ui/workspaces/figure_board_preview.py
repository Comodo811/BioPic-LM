"""Interactive figure-board preview widget."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap

import numpy as np
from PySide6.QtWidgets import QWidget

from biopic.export.raster import _panel_image
from biopic.imaging.project_render import render_project_image
from biopic.models.figure_board import FigureBoard, FigurePanel, PageFormat
from biopic.models.project import Project
from biopic.resources import resource_path
from biopic.ui.fonts import safe_font_family
from biopic.ui.workspace_helpers.common import (
    page_dimension_mm as _page_dimension_mm,
)
from biopic.ui.workspaces.figure_board_preview_cache import FigureBoardPreviewCacheMixin
from biopic.ui.workspaces.figure_board_preview_geometry import FigureBoardPreviewGeometryMixin
from biopic.ui.workspaces.figure_board_preview_interactions import FigureBoardPreviewInteractionMixin
from biopic.ui.workspaces.figure_board_preview_overlay_interactions import FigureBoardPreviewOverlayInteractionMixin
from biopic.ui.workspaces.figure_board_preview_overlays import FigureBoardPreviewOverlayMixin
from biopic.ui.workspaces.figure_board_preview_overlays import (
    _measurement_preview_text_items,
)
from biopic.ui.workspaces.figure_board_preview_painting import FigureBoardPreviewPaintingMixin


class FigureBoardPreview(
    FigureBoardPreviewInteractionMixin,
    FigureBoardPreviewOverlayInteractionMixin,
    FigureBoardPreviewPaintingMixin,
    FigureBoardPreviewCacheMixin,
    FigureBoardPreviewOverlayMixin,
    FigureBoardPreviewGeometryMixin,
    QWidget,
):
    """Lightweight publication board preview with real panel placeholders."""

    imageDropped = Signal(str, str)
    panelSelected = Signal(str)
    panelTransformed = Signal(str)
    panelDivideRequested = Signal(str, str)
    panelDeleteRequested = Signal(str)
    panelsMergeRequested = Signal(list)
    panelImageClearRequested = Signal(str)
    panelLabelColorRequested = Signal(str)
    boardEditStarted = Signal(object)
    annotationEdited = Signal()
    overlaySelected = Signal(object)
    undoRequested = Signal()
    redoRequested = Signal()
    imageScaleChanged = Signal(float)
    zoomChanged = Signal(int)
    captionClicked = Signal()

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._board: FigureBoard | None = None
        self._highlight_panel_id: str | None = None
        self._selected_panel_id: str | None = None
        self._selected_panel_ids: set[str] = set()
        self._highlight_divider: str | None = None
        self._drag_mode: str | None = None
        self._drag_start: QPointF | None = None
        self._drag_start_crop: tuple[float, float, float] | None = None
        self._drag_start_panel_rect: tuple[float, float, float, float] | None = None
        self._drag_start_content_rect: tuple[float, float, float, float] | None = None
        self._drag_start_panel_rects: dict[str, tuple[float, float, float, float]] = {}
        self._drag_start_rotation = 0.0
        self._drag_panel_changed = False
        self._annotation_edit_enabled = False
        self._overlay_drag: dict[str, object] | None = None
        self._selected_overlay: dict[str, object] | None = None
        self._is_interacting = False
        self._zoom_percent = 35
        self._panel_pixmap_cache: dict[tuple[object, ...], QPixmap] = {}
        self._filled_panel_pixmap_cache: dict[tuple[object, ...], QPixmap] = {}
        self._node_preview_pixels_cache: dict[tuple[object, ...], np.ndarray] = {}
        self._panel_render_queue: list[tuple[tuple[object, ...], str]] = []
        self._panel_render_pending: set[tuple[object, ...]] = set()
        self._panel_render_timer = QTimer(self)
        self._panel_render_timer.setSingleShot(False)
        self._panel_render_timer.setInterval(180)
        self._panel_render_timer.timeout.connect(self._render_next_panel_pixmap)
        self._watermark_pixmap = QPixmap(str(resource_path("icons", "biopic_logo.png")))
        self._workspace_watermark_visible = True
        self._panel_cache_generation = 0
        self._canvas_size = QSize()
        self._zoom_update_timer = QTimer(self)
        self._zoom_update_timer.setSingleShot(True)
        self._zoom_update_timer.setInterval(24)
        self._zoom_update_timer.timeout.connect(self._apply_zoom_update)
        self._interaction_quality_timer = QTimer(self)
        self._interaction_quality_timer.setSingleShot(True)
        self._interaction_quality_timer.setInterval(140)
        self._interaction_quality_timer.timeout.connect(self._finish_interaction_quality)
        self.setMinimumSize(QSize(1, 1))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setAutoFillBackground(False)

    def set_workspace_watermark_visible(self, visible: bool) -> None:
        self._workspace_watermark_visible = bool(visible)
        self.update()

    def set_annotation_edit_enabled(self, enabled: bool) -> None:
        """Toggle direct movement of annotation and measurement text overlays."""
        self._annotation_edit_enabled = bool(enabled)
        self._overlay_drag = None
        self._drag_mode = None
        if not enabled:
            self._selected_overlay = None
            self.overlaySelected.emit(None)
        self.unsetCursor()
        self.update()

    def set_board(self, board: FigureBoard | None) -> None:
        """Set the board shown in the preview."""
        board_changed = board is not self._board
        self._board = board
        valid_ids = set() if board is None else {panel.id for panel in board.panels}
        self._selected_panel_ids.intersection_update(valid_ids)
        if self._selected_panel_id not in valid_ids and self._selected_panel_id != "__board__":
            self._selected_panel_id = None
        if board_changed:
            self._panel_pixmap_cache.clear()
            self._filled_panel_pixmap_cache.clear()
            self._node_preview_pixels_cache.clear()
            self._panel_render_queue.clear()
            self._panel_render_pending.clear()
            self._panel_render_timer.stop()
        self._update_canvas_size(force=True)
        self.update()

    def invalidate_render_cache(self) -> None:
        """Drop cached panel pixmaps after upstream image or overlay changes."""
        self._panel_cache_generation += 1
        self._panel_pixmap_cache.clear()
        self._filled_panel_pixmap_cache.clear()
        self._node_preview_pixels_cache.clear()
        self._panel_render_queue.clear()
        self._panel_render_pending.clear()
        self._panel_render_timer.stop()
        self.update()

    def sizeHint(self) -> QSize:
        """Prefer the current page preview size without forcing the window minimum."""
        return self._canvas_size if self._canvas_size.isValid() else QSize(360, 280)

    def minimumSizeHint(self) -> QSize:
        """Allow the main window to shrink; clipped previews remain interactive."""
        return QSize(1, 1)

    def _set_canvas_size(self, size: QSize, *, force: bool = False) -> None:
        if not force and size == self._canvas_size:
            return
        self._canvas_size = size
        self.resize(size)
        self.updateGeometry()

    def set_zoom_percent(self, percent: int) -> None:
        """Set board zoom where 100% equals page output pixels."""
        next_zoom = max(10, min(400, int(percent)))
        if next_zoom == self._zoom_percent and not self._zoom_update_timer.isActive():
            return
        self._zoom_percent = next_zoom
        self._is_interacting = True
        self._zoom_update_timer.start()
        self._interaction_quality_timer.start()
        self.zoomChanged.emit(self._zoom_percent)

    def _apply_zoom_update(self) -> None:
        self._update_canvas_size()
        self.update()

    def _finish_interaction_quality(self) -> None:
        if self._drag_mode is None:
            self._is_interacting = False
            self.update()

    def _mm_to_preview_px(self, value_mm: float, page_mm: float, preview_px: float) -> float:
        return preview_px * value_mm / max(1.0, page_mm)

    def _board_zoom_scale(self) -> float:
        return max(0.1, float(self._zoom_percent) / 100.0)

    def _page_width_mm(self, page: PageFormat) -> float:
        return _page_dimension_mm(page.width, page.unit)

    def _page_height_mm(self, page: PageFormat) -> float:
        return _page_dimension_mm(page.height, page.unit)

    def _update_canvas_size(self, *, force: bool = False) -> None:
        if self._board is None:
            size = QSize(360, 280)
            self._set_canvas_size(size, force=force)
            return
        width_mm = self._page_width_mm(self._board.page)
        height_mm = self._page_height_mm(self._board.page)
        screen = self.screen()
        pixels_per_mm = (
            screen.physicalDotsPerInch() / 25.4 if screen is not None else 96.0 / 25.4
        )
        scale = self._zoom_percent / 100.0
        size = QSize(
            max(360, int(width_mm * pixels_per_mm * scale) + 96),
            max(280, int(height_mm * pixels_per_mm * scale) + 96),
        )
        self._set_canvas_size(size, force=force)


