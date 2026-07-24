"""Rendering and cache helpers for the edit workspace."""

from __future__ import annotations

import logging
from time import perf_counter

import numpy as np

from biopic.imaging.adjustments import adjustment_pipeline_cache_key, render_adjustment_pipeline
from biopic.imaging.layer_buffers import (
    clear_layer_buffers,
    layer_alpha_buffer,
    layer_content_buffer,
)

LOGGER = logging.getLogger(__name__)


class EditRenderingMixin:
    """Shared preview rendering and edit-composite cache behavior."""

    def _adjustment_preview_base(self, exclude_operation: str | None = None) -> np.ndarray | None:
        if self._base_pixels is None or self._current_asset_id is None:
            return None
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return self._base_pixels.copy()
        base = self._render_edit_composite_cached(source_node)
        layers = [
            layer
            for layer in self.project.adjustment_layers_for_image(source_node)
            if exclude_operation is None or layer.operation != exclude_operation
        ]
        return render_adjustment_pipeline(base, layers)

    def _render_current_adjustment_preview(self) -> None:
        start = perf_counter()
        if self._base_pixels is None or self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            self._current_pixels = self._base_pixels.copy()
            self.canvas.set_pixels(self._current_pixels, "base image", fit=False)
            return
        layers = self.project.adjustment_layers_for_image(source_node)
        layer_composite = self._render_edit_composite_cached(source_node)
        rendered = render_adjustment_pipeline(layer_composite, layers)
        cache_key = adjustment_pipeline_cache_key(source_node, layers)
        for layer in layers:
            layer.cache_key = cache_key
        self._current_pixels = rendered
        self.canvas.set_pixels(rendered, f"adjusted preview {cache_key[:18]}", fit=False)
        LOGGER.debug(
            "edit preview rendered in %.3fs for shape=%s adjustment_layers=%d",
            perf_counter() - start,
            getattr(rendered, "shape", None),
            len(layers),
        )

    def _render_edit_composite_cached(self, source_node: str) -> np.ndarray:
        if self._base_pixels is None:
            raise ValueError("No base image is loaded")
        key = self._edit_composite_key(source_node)
        if self._edit_composite_cache is not None and self._edit_composite_cache_key == key:
            return self._edit_composite_cache
        start = perf_counter()
        composite = self._edit_engine.render_projection(source_node, self._base_pixels)
        self._edit_composite_cache = composite
        self._edit_composite_cache_key = key
        LOGGER.debug(
            "edit composite rendered in %.3fs for shape=%s layers=%d",
            perf_counter() - start,
            getattr(composite, "shape", None),
            sum(
                1
                for layer in self.project.edit_layers.values()
                if layer.source_node_id in {None, source_node}
            ),
        )
        return composite

    def _render_external_edit_source(self, source_node: str) -> np.ndarray:
        pixels = self._render_edit_composite_cached(source_node)
        adjustment_layers = self.project.adjustment_layers_for_image(source_node)
        if not adjustment_layers:
            return pixels
        return render_adjustment_pipeline(pixels, adjustment_layers)

    def _edit_composite_key(self, source_node: str) -> tuple[object, ...]:
        layers = sorted(
            (
                layer
                for layer in self.project.edit_layers.values()
                if layer.source_node_id in {None, source_node}
            ),
            key=lambda layer: layer.order,
        )
        return tuple(
            (
                layer.id,
                layer.visible,
                layer.opacity,
                layer.blend_mode.value,
                layer.order,
                layer.offset_x,
                layer.offset_y,
                layer.content_kind.value,
                id(layer_content_buffer(layer.id)),
                id(layer_alpha_buffer(layer.id)),
                id(layer.content),
                id(layer.alpha),
            )
            for layer in layers
        )

    def _invalidate_edit_composite_cache(self) -> None:
        self._edit_composite_cache = None
        self._edit_composite_cache_key = None

    def _invalidate_layer_array_cache(self, layer_id: str | None = None) -> None:
        clear_layer_buffers(layer_id)
