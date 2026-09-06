"""Pixmap and rendered-image caching for figure-board preview."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from PIL import Image
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPixmap

from biopic.export.raster import _display_compatible, _panel_image as _default_panel_image
from biopic.export.raster_figure_board_rendering import (
    _common_displayed_scale_bar_value_key,
    _panel_draw_size_for_dimensions,
)
from biopic.imaging.project_render import (
    asset_for_source_node,
    project_image_cache_key,
    render_project_image as _default_render_project_image,
)
from biopic.models.figure_board import panel_empty_background_signature
from biopic.models.image_asset import ImageAsset
from biopic.ui.image_canvas import ndarray_to_qimage
from biopic.ui.previews import asset_preview_pixels


class FigureBoardPreviewCacheMixin:
    def _panel_pixmap(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
        asset: ImageAsset,
    ) -> QPixmap:
        if panel.source_node_id is None:
            return QPixmap()
        key = (
            panel.source_node_id,
            project_image_cache_key(self.project, panel.source_node_id),
        )
        cached = self._panel_pixmap_cache.get(key)
        if cached is not None:
            return cached
        preview_size = self._capped_panel_preview_size(panel_rect)
        source = (
            self._placeholder_panel_pixmap(asset, preview_size)
            if _project_image_key_has_edits(key)
            else self._source_preview_pixmap(asset, preview_size)
        )
        self._panel_pixmap_cache[key] = source
        if not self._is_interacting:
            self._queue_panel_render(key, panel.source_node_id)
        return source

    def _capped_panel_preview_size(self, panel_rect: QRectF) -> QSize:
        width = max(1, int(round(panel_rect.width())))
        height = max(1, int(round(panel_rect.height())))
        max_edge = 900 if self._is_interacting else 1200
        if max(width, height) > max_edge:
            scale = max_edge / max(1.0, float(max(width, height)))
            width = max(1, int(round(width * scale)))
            height = max(1, int(round(height * scale)))
        return QSize(width, height)

    def _source_preview_pixmap(self, asset: ImageAsset, size: QSize) -> QPixmap:
        max_edge = max(1, max(size.width(), size.height()))
        pixels = asset_preview_pixels(asset, max_edge=max_edge)
        return self._bounded_preview_pixmap(QPixmap.fromImage(ndarray_to_qimage(pixels)))

    def _placeholder_panel_pixmap(self, asset: ImageAsset, size: QSize) -> QPixmap:
        target_width = max(1.0, float(size.width()))
        target_height = max(1.0, float(size.height()))
        source_width = max(1.0, float(asset.width or target_width))
        source_height = max(1.0, float(asset.height or target_height))
        source_aspect = source_width / source_height
        target_aspect = target_width / target_height
        if source_aspect > target_aspect:
            width = int(round(target_width))
            height = int(round(target_width / source_aspect))
        else:
            height = int(round(target_height))
            width = int(round(target_height * source_aspect))
        pixmap = QPixmap(max(1, width), max(1, height))
        pixmap.fill(QColor("#d9dedb"))
        return pixmap

    def _queue_panel_render(self, key: tuple[object, ...], node_id: str) -> None:
        if key in self._panel_render_pending:
            return
        self._panel_render_pending.add(key)
        self._panel_render_queue.append((key, node_id))
        if not self._panel_render_timer.isActive():
            self._panel_render_timer.start()

    def _render_next_panel_pixmap(self) -> None:
        while self._panel_render_queue:
            key, node_id = self._panel_render_queue.pop(0)
            self._panel_render_pending.discard(key)
            if key not in self._panel_pixmap_cache:
                continue
            current_key = (
                node_id,
                project_image_cache_key(self.project, node_id),
            )
            if key != current_key:
                continue
            rendered = self._preview_pixels_for_node(node_id, max_edge=1400)
            if rendered is None:
                continue
            pixmap = self._bounded_preview_pixmap(QPixmap.fromImage(ndarray_to_qimage(rendered)))
            if pixmap.isNull():
                continue
            self._panel_pixmap_cache[key] = pixmap
            self.update()
            return
        self._panel_render_timer.stop()

    def _filled_panel_pixmap(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
        asset: ImageAsset,
    ) -> QPixmap:
        if panel.source_node_id is None:
            return QPixmap()
        width = max(1, int(round(panel_rect.width())))
        height = max(1, int(round(panel_rect.height())))
        max_edge = 900 if self._is_interacting else 1400
        if max(width, height) > max_edge:
            scale = max_edge / max(1.0, float(max(width, height)))
            width = max(1, int(round(width * scale)))
            height = max(1, int(round(height * scale)))
        width, height = self._preview_cache_size(width, height)
        key = (
            "filled",
            panel.source_node_id,
            project_image_cache_key(self.project, panel.source_node_id),
            panel.crop,
            round(float(panel.rotation), 4),
            width,
            height,
        )
        cached = self._filled_panel_pixmap_cache.get(key)
        if cached is not None:
            return cached
        nearby = self._nearest_filled_panel_pixmap(key, width, height)
        if nearby is not None:
            return nearby
        if self._is_interacting:
            return self._panel_pixmap(panel, panel_rect, asset)
        rendered = self._preview_pixels_for_node(panel.source_node_id, max_edge=1200)
        if rendered is None:
            return self._panel_pixmap(panel, panel_rect, asset)
        image = Image.fromarray(_display_compatible(rendered)).convert("RGBA")
        panel_image = _preview_panel_image()(
            image,
            panel,
            width,
            height,
            cover_rotation=False,
        )
        qimage = ndarray_to_qimage(np.asarray(panel_image))
        pixmap = QPixmap.fromImage(qimage)
        self._filled_panel_pixmap_cache[key] = pixmap
        return pixmap

    def _preview_cache_size(self, width: int, height: int) -> tuple[int, int]:
        """Bucket preview render sizes so zooming reuses nearby cached rasters."""
        if not self._is_interacting:
            return width, height
        bucket = 64
        return (
            max(1, int(round(width / bucket)) * bucket),
            max(1, int(round(height / bucket)) * bucket),
        )

    def _nearest_filled_panel_pixmap(
        self,
        key: tuple[object, ...],
        width: int,
        height: int,
    ) -> QPixmap | None:
        """Return an existing filled preview for the same panel transform."""
        prefix = key[:-2]
        best: tuple[int, QPixmap] | None = None
        for cached_key, pixmap in self._filled_panel_pixmap_cache.items():
            if (
                not isinstance(cached_key, tuple)
                or len(cached_key) != len(key)
                or cached_key[:-2] != prefix
                or pixmap.isNull()
            ):
                continue
            try:
                cached_width = int(cached_key[-2])
                cached_height = int(cached_key[-1])
            except (TypeError, ValueError):
                continue
            distance = abs(cached_width - width) + abs(cached_height - height)
            if best is None or distance < best[0]:
                best = (distance, pixmap)
        return None if best is None else best[1]

    def _preview_pixels_for_node(self, node_id: str, *, max_edge: int) -> np.ndarray | None:
        cache_key = project_image_cache_key(self.project, node_id)
        if cache_key is None:
            return None
        key = (node_id, cache_key, int(max_edge))
        cached = self._node_preview_pixels_cache.get(key)
        if cached is not None:
            return cached
        rendered = _preview_render_project_image()(self.project, node_id)
        if rendered is None:
            return None
        preview = _downsample_preview_pixels(rendered, max_edge=max_edge)
        self._node_preview_pixels_cache[key] = preview
        return preview

    def _baked_empty_background_pixmap(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
    ) -> QPixmap:
        if not panel.empty_background_path or panel.source_node_id is None:
            return QPixmap()
        stored_signature = panel.empty_background_signature
        if (
            stored_signature is None
            or len(stored_signature) < 3
            or stored_signature[:3]
            != panel_empty_background_signature(panel, 1, 1)[:3]
        ):
            return QPixmap()
        path = Path(panel.empty_background_path)
        if not path.exists():
            return QPixmap()
        key = ("baked-empty-background", str(path), stored_signature)
        cached = self._filled_panel_pixmap_cache.get(key)
        if cached is not None:
            return cached
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return pixmap
        self._filled_panel_pixmap_cache[key] = pixmap
        return pixmap

    def _bounded_preview_pixmap(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap
        max_edge = 2200
        if pixmap.width() <= max_edge and pixmap.height() <= max_edge:
            return pixmap
        return pixmap.scaled(
            QSize(max_edge, max_edge),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _panel_pixmap_draw_size(
        self,
        pixmap: QPixmap,
        panel_rect: QRectF,
        zoom: float,
        rotation: float = 0.0,
    ) -> tuple[float, float]:
        del rotation
        target_width = int(round(panel_rect.width()))
        target_height = int(round(panel_rect.height()))
        if pixmap.isNull() or pixmap.height() <= 0:
            return target_width * max(0.1, zoom), target_height * max(0.1, zoom)
        return _panel_draw_size_for_dimensions(
            pixmap.width(),
            pixmap.height(),
            target_width,
            target_height,
            max(0.1, zoom),
        )

def _downsample_preview_pixels(pixels: np.ndarray, *, max_edge: int) -> np.ndarray:
    data = np.asarray(pixels)
    if data.ndim < 2:
        return data.copy()
    height, width = data.shape[:2]
    if max(width, height) <= max_edge:
        return data.copy()
    scale = max_edge / max(1.0, float(max(width, height)))
    target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    image = Image.fromarray(_display_compatible(data))
    return np.asarray(image.resize(target, Image.Resampling.BILINEAR))


def _project_image_key_has_edits(cache_key: tuple[object, ...]) -> bool:
    if len(cache_key) == 2 and isinstance(cache_key[1], tuple):
        cache_key = cache_key[1]
    if len(cache_key) < 5:
        return False
    return bool(cache_key[3]) or bool(cache_key[4])


def _preview_panel_image():
    module = sys.modules.get("biopic.ui.workspaces.figure_board_preview")
    return getattr(module, "_panel_image", _default_panel_image)


def _preview_render_project_image():
    module = sys.modules.get("biopic.ui.workspaces.figure_board_preview")
    return getattr(module, "render_project_image", _default_render_project_image)


