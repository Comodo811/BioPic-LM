"""Experimental GEGL projection renderer.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from biopic.imaging.engine.gegl_ctypes import GeglCtypesBridge, GeglCtypesError
from biopic.imaging.project_render import edit_layers_for_image, layer_alpha_region, layer_pixels_region
from biopic.models.editing import BlendMode, EditLayer, EditLayerType, GroupCompositeMode, MaskViewMode
from biopic.models.project import Project


@dataclass(slots=True)
class ProjectionState:
    """Alpha-carrying projection state, matching GEGL/GIMP projection shape."""

    color: np.ndarray
    alpha: np.ndarray


def render_normal_layers_region(
    project: Project,
    source_node: str,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
    *,
    bridge: GeglCtypesBridge,
) -> np.ndarray:
    """Render a region of editable layers with GEGL-backed normal compositing."""
    x, y, width, height = _clamp_rect(rect, base)
    if width <= 0 or height <= 0:
        return np.empty((0, 0), dtype=base.dtype)
    base_region = base[y : y + height, x : x + width]
    layers = edit_layers_for_image(project, source_node)
    if not layers:
        return base_region.copy()
    projection = _render_layer_sequence_gegl(
        layers,
        base,
        parent_id=None,
        rect=(x, y, width, height),
        bridge=bridge,
    )
    return _restore_dtype(projection.color, base_region.dtype)


def _render_layer_sequence_gegl(
    layers: list[EditLayer],
    base: np.ndarray,
    *,
    parent_id: str | None,
    rect: tuple[int, int, int, int],
    bridge: GeglCtypesBridge,
) -> ProjectionState:
    x, y, width, height = rect
    region_shape = base[y : y + height, x : x + width].shape
    composite = ProjectionState(
        color=np.zeros(region_shape, dtype=np.float32),
        alpha=np.zeros(region_shape[:2], dtype=np.float32),
    )
    return _composite_children_into_state(
        composite,
        layers,
        base,
        parent_id=parent_id,
        rect=rect,
        bridge=bridge,
    )


def _composite_children_into_state(
    composite: ProjectionState,
    layers: list[EditLayer],
    base: np.ndarray,
    *,
    parent_id: str | None,
    rect: tuple[int, int, int, int],
    bridge: GeglCtypesBridge,
) -> ProjectionState:
    x, y, width, height = rect
    for layer in sorted(
        (item for item in layers if item.parent_id == parent_id),
        key=lambda item: item.order,
    ):
        if not layer.visible:
            continue
        if layer.layer_type is EditLayerType.GROUP:
            child_output = _render_layer_sequence_gegl(
                layers,
                base,
                parent_id=layer.id,
                rect=rect,
                bridge=bridge,
            )
            if layer.group_composite_mode is GroupCompositeMode.PASS_THROUGH:
                composite = _composite_children_into_state(
                    composite,
                    layers,
                    base,
                    parent_id=layer.id,
                    rect=rect,
                    bridge=bridge,
                )
            else:
                group_alpha = _group_alpha_region(layer, base, rect)
                group_state = ProjectionState(
                    color=child_output.color,
                    alpha=child_output.alpha * group_alpha * float(layer.opacity),
                )
                composite = _blend_states(
                    composite,
                    group_state,
                    layer.blend_mode,
                    bridge=bridge,
                    dtype=base.dtype,
                )
            continue
        pixels = layer_pixels_region(layer, base, (x, y, width, height))
        if pixels is None:
            continue
        alpha = layer_alpha_region(layer, base, (x, y, width, height))
        foreground = ProjectionState(
            color=pixels.astype(np.float32, copy=False),
            alpha=np.clip(alpha * float(layer.opacity), 0.0, 1.0),
        )
        composite = _blend_states(
            composite,
            foreground,
            layer.blend_mode,
            bridge=bridge,
            dtype=base.dtype,
        )
    return composite


def _group_alpha_region(
    layer: EditLayer,
    base: np.ndarray,
    rect: tuple[int, int, int, int],
) -> np.ndarray:
    _x, _y, width, height = rect
    alpha = np.ones((height, width), dtype=np.float32)
    if not layer.mask_enabled or layer.mask_edit_state is MaskViewMode.SHOW:
        return alpha
    mask = layer.mask_pixels()
    if mask is None:
        return alpha
    result = np.zeros(alpha.shape, dtype=np.float32)
    _copy_offset_region(_normalize_mask(mask), result, rect, layer.offset_x, layer.offset_y)
    return alpha * np.clip(result, 0.0, 1.0)


def render_normal_layers(
    project: Project,
    source_node: str,
    base: np.ndarray,
    *,
    bridge: GeglCtypesBridge,
) -> np.ndarray:
    """Render the full normal-layer projection using GEGL."""
    return render_normal_layers_region(
        project,
        source_node,
        base,
        (0, 0, int(base.shape[1]), int(base.shape[0])),
        bridge=bridge,
    )


def render_projection_state(
    project: Project,
    source_node: str,
    base: np.ndarray,
    *,
    bridge: GeglCtypesBridge,
) -> ProjectionState:
    """Render the full alpha-carrying projection state."""
    layers = edit_layers_for_image(project, source_node)
    if not layers:
        return ProjectionState(
            color=base.astype(np.float32, copy=True),
            alpha=np.ones(base.shape[:2], dtype=np.float32),
        )
    return _render_layer_sequence_gegl(
        layers,
        base,
        parent_id=None,
        rect=(0, 0, int(base.shape[1]), int(base.shape[0])),
        bridge=bridge,
    )


def _blend_states(
    background: ProjectionState,
    foreground: ProjectionState,
    blend_mode: BlendMode,
    *,
    bridge: GeglCtypesBridge,
    dtype: np.dtype,
) -> ProjectionState:
    if blend_mode is BlendMode.NORMAL and np.dtype(dtype) == np.dtype(np.uint8):
        try:
            bg_rgba = _state_to_rgba_u8(background)
            fg_rgba = _state_to_rgba_u8(foreground)
            composed = bridge.composite_over_rgba(bg_rgba, fg_rgba)
            return _state_from_rgba_u8(composed, background.color.shape)
        except GeglCtypesError:
            pass
    return _blend_states_numpy(background, foreground, blend_mode, dtype)


def _blend_states_numpy(
    background: ProjectionState,
    foreground: ProjectionState,
    blend_mode: BlendMode,
    dtype: np.dtype,
) -> ProjectionState:
    fg = foreground.color.astype(np.float32, copy=False)
    bg = background.color.astype(np.float32, copy=False)
    if fg.ndim == 2 and bg.ndim == 3:
        fg = np.repeat(fg[..., None], bg.shape[-1], axis=2)
    if fg.ndim == 3 and bg.ndim == 2:
        fg = fg[..., 0]
    fg_alpha = np.clip(foreground.alpha, 0.0, 1.0)
    bg_alpha = np.clip(background.alpha, 0.0, 1.0)
    fg_weight = fg_alpha[..., None] if bg.ndim == 3 else fg_alpha
    bg_weight = bg_alpha[..., None] if bg.ndim == 3 else bg_alpha
    if blend_mode is BlendMode.MULTIPLY:
        max_value = _dtype_max(dtype)
        fg = ((fg / max_value) * (bg / max_value) * max_value).astype(np.float32)
    elif blend_mode is BlendMode.SCREEN:
        max_value = _dtype_max(dtype)
        fg = (max_value - ((max_value - fg) * (max_value - bg) / max_value)).astype(
            np.float32
        )
    elif blend_mode is BlendMode.ADD:
        fg = bg + fg
    out_alpha = fg_alpha + bg_alpha * (1.0 - fg_alpha)
    out_weight = out_alpha[..., None] if bg.ndim == 3 else out_alpha
    premul = fg * fg_weight + bg * bg_weight * (1.0 - fg_weight)
    out_color = np.zeros_like(bg, dtype=np.float32)
    np.divide(premul, out_weight, out=out_color, where=out_weight > 1.0e-8)
    return ProjectionState(color=out_color, alpha=out_alpha.astype(np.float32, copy=False))


def _state_to_rgba_u8(state: ProjectionState) -> np.ndarray:
    color = _restore_dtype(state.color, np.dtype(np.uint8))
    return _to_rgba_u8(color, state.alpha)


def _state_from_rgba_u8(rgba: np.ndarray, color_shape: tuple[int, ...]) -> ProjectionState:
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    if len(color_shape) == 2:
        color = rgba[..., 0].astype(np.float32)
    else:
        color = rgba[..., : color_shape[2]].astype(np.float32)
    return ProjectionState(color=color, alpha=alpha)


def _to_rgba_u8(pixels: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    color = np.asarray(pixels)
    if color.dtype != np.uint8:
        raise GeglCtypesError("Experimental GEGL projection expects uint8 layer pixels")
    if color.ndim == 2:
        rgb = np.repeat(color[..., None], 3, axis=2)
    elif color.ndim == 3 and color.shape[2] == 3:
        rgb = color
    elif color.ndim == 3 and color.shape[2] == 4:
        rgb = color[..., :3]
        alpha = alpha * (color[..., 3].astype(np.float32) / 255.0)
    else:
        raise GeglCtypesError("Experimental GEGL projection expects gray, RGB or RGBA pixels")
    alpha_u8 = np.clip(alpha, 0.0, 1.0)
    alpha_u8 = np.rint(alpha_u8 * 255.0).astype(np.uint8)
    return np.dstack([rgb, alpha_u8]).astype(np.uint8, copy=False)


def _from_rgba_u8(rgba: np.ndarray, reference: np.ndarray) -> np.ndarray:
    if reference.ndim == 2:
        return rgba[..., 0].astype(reference.dtype, copy=False)
    if reference.ndim == 3 and reference.shape[2] == 4:
        return rgba.astype(reference.dtype, copy=False)
    return rgba[..., : reference.shape[2]].astype(reference.dtype, copy=False)


def _restore_dtype(pixels: np.ndarray, dtype: np.dtype) -> np.ndarray:
    np_dtype = np.dtype(dtype)
    if np.issubdtype(np_dtype, np.integer):
        info = np.iinfo(np_dtype)
        return np.clip(pixels, info.min, info.max).astype(np_dtype)
    return pixels.astype(np_dtype, copy=False)


def _dtype_max(dtype: np.dtype) -> float:
    np_dtype = np.dtype(dtype)
    return float(np.iinfo(np_dtype).max) if np.issubdtype(np_dtype, np.integer) else 1.0


def _normalize_mask(mask: np.ndarray) -> np.ndarray:
    mask_2d = mask[..., 0] if mask.ndim == 3 else mask
    mask_float = mask_2d.astype(np.float32, copy=False)
    if np.issubdtype(mask_2d.dtype, np.integer):
        return mask_float / float(np.iinfo(mask_2d.dtype).max)
    return np.clip(mask_float, 0.0, 1.0)


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


def _clamp_rect(
    rect: tuple[int, int, int, int],
    base: np.ndarray,
) -> tuple[int, int, int, int]:
    x, y, width, height = rect
    x = max(0, min(int(x), int(base.shape[1])))
    y = max(0, min(int(y), int(base.shape[0])))
    width = max(0, min(int(width), int(base.shape[1]) - x))
    height = max(0, min(int(height), int(base.shape[0]) - y))
    return x, y, width, height
