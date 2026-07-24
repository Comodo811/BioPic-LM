"""Project-aware image rendering for downstream workflow stages.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import numpy as np

from biopic.imaging.adjustments import render_adjustment_pipeline
from biopic.imaging.io import load_asset_pixels
from biopic.imaging.layer_buffers import layer_alpha_buffer, layer_content_buffer
from biopic.native.composite_backend import blend_normal_in_place, blend_normal_offset_in_place
from biopic.models.editing import (
    BlendMode,
    EditLayer,
    EditLayerType,
    GroupCompositeMode,
    LayerContentKind,
    MaskViewMode,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project


def editable_assets(project: Project) -> list[ImageAsset]:
    """Return assets that should appear in normal image-processing workspaces."""
    stack_source_ids = {
        asset_id for stack in project.stacks.values() for asset_id in stack.asset_ids
    }
    return [
        asset
        for asset in project.assets.values()
        if asset.id not in stack_source_ids and asset.is_editable_browser_image
    ]


def asset_for_source_node(project: Project, node_id: str) -> ImageAsset | None:
    """Return the image asset represented by a source-image node."""
    node = project.graph.nodes.get(node_id)
    if node is None or node.operation != "source_image":
        return None
    asset_id = node.parameters.get("asset_id")
    if not isinstance(asset_id, str):
        return None
    return project.assets.get(asset_id)


def source_node_for_asset(project: Project, asset: ImageAsset) -> str | None:
    """Return the processing graph node id for an image asset."""
    return project.source_node_id_for_asset(asset.id)


def render_project_image(project: Project, node_id: str) -> np.ndarray | None:
    """Render a source image plus editable and adjustment layers."""
    asset = asset_for_source_node(project, node_id)
    if asset is None:
        return None
    base = load_asset_pixels(asset)
    base = render_edit_layers(project, node_id, base)
    layers = project.adjustment_layers_for_image(node_id)
    if not layers:
        return base
    return render_adjustment_pipeline(base, layers)


def project_image_cache_key(project: Project, node_id: str) -> tuple[object, ...] | None:
    """Return a cheap signature for pixels produced by render_project_image."""
    asset = asset_for_source_node(project, node_id)
    if asset is None:
        return None
    edit_layers = tuple(
        (
            layer.id,
            layer.visible,
            layer.opacity,
            layer.blend_mode.value,
            layer.order,
            layer.offset_x,
            layer.offset_y,
            layer.content_kind.value,
            layer.generation,
            id(layer.content),
            id(layer.alpha),
        )
        for layer in edit_layers_for_image(project, node_id)
    )
    adjustment_layers = tuple(
        (
            layer.id,
            layer.operation,
            _freeze_cache_value(layer.parameters),
            layer.enabled,
            layer.opacity,
            layer.blend_mode.value,
            layer.order,
            layer.modified_at,
        )
        for layer in project.adjustment_layers_for_image(node_id)
    )
    return (
        node_id,
        asset.id,
        asset.checksum or asset.path,
        edit_layers,
        adjustment_layers,
    )


def _freeze_cache_value(value: object) -> object:
    if isinstance(value, dict):
        return tuple(
            (str(key), _freeze_cache_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_cache_value(item) for item in value)
    if isinstance(value, np.ndarray):
        return ("ndarray", value.shape, str(value.dtype), id(value))
    return value


def render_edit_layers(project: Project, node_id: str, base: np.ndarray) -> np.ndarray:
    """Composite editable layers bottom-to-top over a transparent canvas."""
    layers = edit_layers_for_image(project, node_id)
    if not layers:
        return base.copy()
    composite = _render_layer_sequence(layers, base, None)
    return _restore_dtype(composite, base.dtype)


def render_edit_layers_region(
    project: Project,
    node_id: str,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
) -> np.ndarray:
    """Composite a dirty region of editable layers bottom-to-top."""
    return _render_edit_layers_region(
        project,
        node_id,
        base,
        rect,
        exclude_layer_id=None,
    )


def render_edit_layers_region_excluding(
    project: Project,
    node_id: str,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
    exclude_layer_id: str,
) -> np.ndarray:
    """Composite a dirty region while omitting one layer."""
    return _render_edit_layers_region(
        project,
        node_id,
        base,
        rect,
        exclude_layer_id=exclude_layer_id,
    )


def _render_edit_layers_region(
    project: Project,
    node_id: str,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
    *,
    exclude_layer_id: str | None,
) -> np.ndarray:
    x, y, width, height = rect
    if width <= 0 or height <= 0:
        return np.empty((0, 0), dtype=base.dtype)
    x = max(0, min(x, base.shape[1]))
    y = max(0, min(y, base.shape[0]))
    width = max(0, min(width, base.shape[1] - x))
    height = max(0, min(height, base.shape[0] - y))
    if width <= 0 or height <= 0:
        return np.empty((0, 0), dtype=base.dtype)
    layers = edit_layers_for_image(project, node_id)
    if exclude_layer_id is not None:
        layers = [layer for layer in layers if layer.id != exclude_layer_id]
    composite = _render_layer_sequence(layers, base, None, (x, y, width, height))
    return _restore_dtype(composite, base.dtype)


def edit_layers_for_image(project: Project, node_id: str) -> list[EditLayer]:
    """Return editable layers for a source node in compositing order."""
    return sorted(
        (
            layer
            for layer in project.edit_layers.values()
            if layer.source_node_id in {None, node_id}
        ),
        key=lambda layer: layer.order,
    )


def layer_pixels(layer: EditLayer, base: np.ndarray) -> np.ndarray | None:
    """Resolve layer pixels against a source image."""
    if layer.content_kind is LayerContentKind.SOURCE:
        return _fit_layer_to_base(base, base, layer.offset_x, layer.offset_y)
    if layer.content_kind is LayerContentKind.RASTER:
        content = layer_content_buffer(layer.id)
        if content is None:
            content = layer.content_pixels()
        if content is None:
            return None
        return _fit_layer_to_base(content, base, layer.offset_x, layer.offset_y)
    return None


def layer_alpha(layer: EditLayer, base: np.ndarray) -> np.ndarray:
    """Resolve layer alpha against a source image."""
    alpha = layer_alpha_buffer(layer.id)
    if alpha is None:
        alpha = layer.alpha_pixels()
    if alpha is None:
        alpha = np.ones(base.shape[:2], dtype=np.float32)
        if layer.content_kind is LayerContentKind.EMPTY:
            alpha.fill(0.0)
        elif layer.content_kind is LayerContentKind.SOURCE:
            alpha = _fit_layer_alpha(alpha, base, layer.offset_x, layer.offset_y)
    else:
        alpha = _fit_layer_alpha(alpha, base, layer.offset_x, layer.offset_y)
    return _apply_layer_mask(layer, base, alpha.astype(np.float32, copy=False))


def layer_pixels_region(
    layer: EditLayer,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
) -> np.ndarray | None:
    """Resolve only one layer's pixels for a projection region."""
    x, y, width, height = rect
    result = np.zeros(base[y : y + height, x : x + width].shape, dtype=base.dtype)
    if layer.content_kind is LayerContentKind.SOURCE:
        _copy_offset_region(base, result, rect, layer.offset_x, layer.offset_y)
        return result
    if layer.content_kind is not LayerContentKind.RASTER:
        return None
    content = layer_content_buffer(layer.id)
    if content is None:
        content = layer.content_pixels()
    if content is None:
        return None
    _copy_offset_region(content, result, rect, layer.offset_x, layer.offset_y)
    return result


def layer_alpha_region(
    layer: EditLayer,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
) -> np.ndarray:
    """Resolve only one layer's alpha for a projection region."""
    x, y, width, height = rect
    result = np.zeros((height, width), dtype=np.float32)
    alpha = layer_alpha_buffer(layer.id)
    if alpha is None:
        alpha = layer.alpha_pixels()
    if alpha is None:
        fill_value = 0.0 if layer.content_kind is LayerContentKind.EMPTY else 1.0
        result.fill(fill_value)
        return _apply_layer_mask_region(layer, base, rect, result)
    _copy_offset_region(alpha, result, rect, layer.offset_x, layer.offset_y)
    return _apply_layer_mask_region(
        layer, base, rect, np.clip(result, 0.0, 1.0).astype(np.float32, copy=False)
    )


def _render_layer_sequence(
    layers: list[EditLayer],
    base: np.ndarray,
    parent_id: str | None,
    rect: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    region_shape = (
        base.shape
        if rect is None
        else base[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]].shape
    )
    composite = np.zeros(region_shape, dtype=np.float32)
    for layer in sorted(
        (item for item in layers if item.parent_id == parent_id),
        key=lambda item: item.order,
    ):
        if not layer.visible:
            continue
        if layer.layer_type is EditLayerType.GROUP:
            child_output = _render_layer_sequence(
                layers,
                base,
                layer.id,
                rect if layer.group_composite_mode is GroupCompositeMode.ISOLATED else rect,
            )
            if layer.group_composite_mode is GroupCompositeMode.PASS_THROUGH:
                composite = _blend(
                    composite,
                    child_output,
                    np.ones(region_shape[:2]),
                    BlendMode.NORMAL,
                )
            else:
                group_alpha = _group_alpha(layer, base, rect)
                composite = _blend(
                    composite,
                    child_output,
                    group_alpha * float(layer.opacity),
                    layer.blend_mode,
                )
            continue
        if _blend_layer_offset_native(composite, layer, base, rect):
            continue
        pixels = (
            layer_pixels(layer, base)
            if rect is None
            else layer_pixels_region(layer, base, rect)
        )
        if pixels is None:
            continue
        alpha = layer_alpha(layer, base) if rect is None else layer_alpha_region(layer, base, rect)
        composite = _blend(composite, pixels, alpha * float(layer.opacity), layer.blend_mode)
    return composite


def _blend_layer_offset_native(
    composite: np.ndarray,
    layer: EditLayer,
    base: np.ndarray,
    rect: tuple[int, int, int, int] | None,
) -> bool:
    if layer.blend_mode is not BlendMode.NORMAL:
        return False
    if layer.content_kind is LayerContentKind.EMPTY:
        return True
    if layer.content_kind is LayerContentKind.SOURCE:
        content = base
    elif layer.content_kind is LayerContentKind.RASTER:
        content = layer_content_buffer(layer.id)
        if content is None:
            content = layer.content_pixels()
        if content is None:
            return True
    else:
        return False
    alpha = layer_alpha_buffer(layer.id)
    if alpha is None:
        alpha = layer.alpha_pixels()
    if alpha is not None:
        alpha = np.ascontiguousarray(alpha.astype(np.float32, copy=False))
    mask = None
    if layer.mask_enabled and layer.mask_edit_state is not MaskViewMode.SHOW:
        mask = layer.mask_pixels()
        if mask is not None:
            mask = np.ascontiguousarray(mask)
    rect_origin = (0, 0) if rect is None else (rect[0], rect[1])
    return blend_normal_offset_in_place(
        composite,
        np.ascontiguousarray(content),
        alpha,
        mask,
        rect_origin=rect_origin,
        offset=(layer.offset_x, layer.offset_y),
        opacity=layer.opacity,
    )


def _group_alpha(
    layer: EditLayer,
    base: np.ndarray,
    rect: tuple[int, int, int, int] | None,
) -> np.ndarray:
    if rect is None:
        alpha = np.ones(base.shape[:2], dtype=np.float32)
        return _apply_layer_mask(layer, base, alpha)
    _x, _y, width, height = rect
    alpha = np.ones((height, width), dtype=np.float32)
    return _apply_layer_mask_region(layer, base, rect, alpha)


def _apply_layer_mask(layer: EditLayer, base: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    if not layer.mask_enabled or layer.mask_edit_state is MaskViewMode.SHOW:
        return alpha
    mask = layer.mask_pixels()
    if mask is None:
        return alpha
    fitted = _fit_layer_alpha(_normalize_mask(mask), base, layer.offset_x, layer.offset_y)
    return alpha * fitted


def _apply_layer_mask_region(
    layer: EditLayer,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
    alpha: np.ndarray,
) -> np.ndarray:
    if not layer.mask_enabled or layer.mask_edit_state is MaskViewMode.SHOW:
        return alpha
    mask = layer.mask_pixels()
    if mask is None:
        return alpha
    result = np.zeros(alpha.shape, dtype=np.float32)
    _copy_offset_region(_normalize_mask(mask), result, rect, layer.offset_x, layer.offset_y)
    return alpha * np.clip(result, 0.0, 1.0)


def _normalize_mask(mask: np.ndarray) -> np.ndarray:
    mask_2d = mask[..., 0] if mask.ndim == 3 else mask
    mask_float = mask_2d.astype(np.float32, copy=False)
    if np.issubdtype(mask_2d.dtype, np.integer):
        return mask_float / float(np.iinfo(mask_2d.dtype).max)
    return np.clip(mask_float, 0.0, 1.0)


def _blend(
    background: np.ndarray,
    foreground: np.ndarray,
    alpha: np.ndarray,
    blend_mode: BlendMode,
) -> np.ndarray:
    opacity = 1.0
    if blend_mode is BlendMode.NORMAL:
        bg_native = np.ascontiguousarray(background, dtype=np.float32)
        fg_native = np.ascontiguousarray(foreground)
        alpha_native = np.ascontiguousarray(alpha, dtype=np.float32)
        if blend_normal_in_place(
            bg_native,
            fg_native,
            alpha_native,
            opacity=opacity,
        ):
            return bg_native
    fg = foreground.astype(np.float32, copy=False)
    bg = background.astype(np.float32, copy=False)
    if fg.ndim == 2 and bg.ndim == 3:
        fg = np.repeat(fg[..., None], bg.shape[-1], axis=-1)
    if fg.ndim == 3 and bg.ndim == 2:
        fg = fg[..., 0]
    if alpha.ndim == 2 and bg.ndim == 3:
        alpha = alpha[..., None]
    if blend_mode is BlendMode.MULTIPLY:
        max_value = _dtype_max(foreground.dtype)
        fg = ((fg / max_value) * (bg / max_value) * max_value).astype(np.float32)
    elif blend_mode is BlendMode.SCREEN:
        max_value = _dtype_max(foreground.dtype)
        fg = (max_value - ((max_value - fg) * (max_value - bg) / max_value)).astype(
            np.float32
        )
    elif blend_mode is BlendMode.ADD:
        fg = bg + fg
    return alpha * fg + (1.0 - alpha) * bg


def _copy_offset_region(
    source: np.ndarray,
    dest_region: np.ndarray,
    dest_rect: tuple[int, int, int, int],
    offset_x: int,
    offset_y: int,
) -> None:
    dest_x, dest_y, width, height = dest_rect
    source_x0 = dest_x - offset_x
    source_y0 = dest_y - offset_y
    src_x = max(0, source_x0)
    src_y = max(0, source_y0)
    dst_x = max(0, -source_x0)
    dst_y = max(0, -source_y0)
    copy_width = min(source.shape[1] - src_x, width - dst_x)
    copy_height = min(source.shape[0] - src_y, height - dst_y)
    if copy_width <= 0 or copy_height <= 0:
        return
    dest_region[dst_y : dst_y + copy_height, dst_x : dst_x + copy_width] = source[
        src_y : src_y + copy_height,
        src_x : src_x + copy_width,
    ]


def _fit_to_base(pixels: np.ndarray, base: np.ndarray) -> np.ndarray:
    result = np.zeros_like(base)
    src_y, dst_y, height = _axis_overlap(pixels.shape[0], result.shape[0], 0)
    src_x, dst_x, width = _axis_overlap(pixels.shape[1], result.shape[1], 0)
    if height <= 0 or width <= 0:
        return result
    result[dst_y : dst_y + height, dst_x : dst_x + width] = pixels[
        src_y : src_y + height,
        src_x : src_x + width,
    ]
    return result


def _fit_alpha(alpha: np.ndarray, base: np.ndarray) -> np.ndarray:
    result = np.zeros(base.shape[:2], dtype=np.float32)
    alpha_2d = alpha[..., 0] if alpha.ndim == 3 else alpha
    src_y, dst_y, height = _axis_overlap(alpha_2d.shape[0], result.shape[0], 0)
    src_x, dst_x, width = _axis_overlap(alpha_2d.shape[1], result.shape[1], 0)
    if height <= 0 or width <= 0:
        return result
    result[dst_y : dst_y + height, dst_x : dst_x + width] = np.clip(
        alpha_2d[src_y : src_y + height, src_x : src_x + width],
        0.0,
        1.0,
    )
    return result


def _fit_layer_to_base(
    pixels: np.ndarray,
    base: np.ndarray,
    offset_x: int,
    offset_y: int,
) -> np.ndarray:
    result = np.zeros_like(base)
    src_y, dst_y, height = _axis_overlap(pixels.shape[0], result.shape[0], offset_y)
    src_x, dst_x, width = _axis_overlap(pixels.shape[1], result.shape[1], offset_x)
    if height <= 0 or width <= 0:
        return result
    result[dst_y : dst_y + height, dst_x : dst_x + width] = pixels[
        src_y : src_y + height,
        src_x : src_x + width,
    ]
    return result


def _fit_layer_alpha(
    alpha: np.ndarray,
    base: np.ndarray,
    offset_x: int,
    offset_y: int,
) -> np.ndarray:
    result = np.zeros(base.shape[:2], dtype=np.float32)
    alpha_2d = alpha[..., 0] if alpha.ndim == 3 else alpha
    src_y, dst_y, height = _axis_overlap(alpha_2d.shape[0], result.shape[0], offset_y)
    src_x, dst_x, width = _axis_overlap(alpha_2d.shape[1], result.shape[1], offset_x)
    if height <= 0 or width <= 0:
        return result
    result[dst_y : dst_y + height, dst_x : dst_x + width] = np.clip(
        alpha_2d[src_y : src_y + height, src_x : src_x + width],
        0.0,
        1.0,
    )
    return result


def _axis_overlap(source_size: int, dest_size: int, offset: int) -> tuple[int, int, int]:
    source_start = max(0, -offset)
    dest_start = max(0, offset)
    length = min(source_size - source_start, dest_size - dest_start)
    return source_start, dest_start, length


def _restore_dtype(pixels: np.ndarray, dtype: np.dtype) -> np.ndarray:
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return np.clip(pixels, info.min, info.max).astype(dtype)
    return pixels.astype(dtype, copy=False)


def _dtype_max(dtype: np.dtype) -> float:
    return float(np.iinfo(dtype).max) if np.issubdtype(dtype, np.integer) else 1.0
