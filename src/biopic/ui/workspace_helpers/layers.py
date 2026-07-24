"""Layer-list and layer-metadata helpers for edit workspaces."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from biopic.models.editing import BlendMode, EditLayer, LayerLock
from biopic.ui.workspace_helpers.icons import icon


def layer_label(layer: EditLayer) -> str:
    lock_names = []
    if layer.locked:
        lock_names.append("locked")
    else:
        if LayerLock.PIXELS in layer.lock_flags:
            lock_names.append("pixels")
        if LayerLock.POSITION in layer.lock_flags:
            lock_names.append("position")
        if LayerLock.VISIBILITY in layer.lock_flags:
            lock_names.append("visibility")
    state = "+".join(lock_names) if lock_names else "editable"
    visibility = "visible" if layer.visible else "hidden"
    return f"{visibility}  {state}  {layer.layer_type.value}  {layer.name}"


def layer_icon(layer: EditLayer) -> QIcon | None:
    if layer.locked or layer.lock_flags:
        return icon("layer_locked_icon.png")
    if layer.visible:
        return icon("layer_visible_icon.png")
    return None


def layer_metadata(layer: EditLayer) -> dict[str, object]:
    return {
        "visible": layer.visible,
        "locked": layer.locked,
        "lock_flags": [lock.value for lock in sorted(layer.lock_flags, key=str)],
        "opacity": layer.opacity,
        "blend_mode": layer.blend_mode.value,
        "offset_x": layer.offset_x,
        "offset_y": layer.offset_y,
        "order": layer.order,
        "name": layer.name,
        "mask_enabled": layer.mask_enabled,
        "mask_edit_state": layer.mask_edit_state.value,
        "group_composite_mode": layer.group_composite_mode.value,
        "parent_id": layer.parent_id or "",
        "generation": layer.generation,
    }


def layer_visual_metadata_changed(
    previous: dict[str, object], current: dict[str, object]
) -> bool:
    visual_keys = (
        "visible",
        "opacity",
        "blend_mode",
        "offset_x",
        "offset_y",
        "order",
        "name",
        "mask_enabled",
        "mask_edit_state",
        "group_composite_mode",
        "parent_id",
    )
    return any(previous.get(key) != current.get(key) for key in visual_keys)


def apply_layer_metadata(layer: EditLayer, metadata: dict[str, object]) -> None:
    layer.visible = bool(metadata.get("visible", layer.visible))
    flags = metadata.get("lock_flags")
    if isinstance(flags, list):
        layer.lock_flags = {LayerLock(str(value)) for value in flags}
    else:
        layer.locked = bool(metadata.get("locked", layer.locked))
    layer.opacity = _metadata_float(metadata, "opacity", layer.opacity)
    layer.blend_mode = BlendMode(str(metadata.get("blend_mode", layer.blend_mode.value)))
    layer.offset_x = metadata_int(metadata, "offset_x", layer.offset_x)
    layer.offset_y = metadata_int(metadata, "offset_y", layer.offset_y)
    layer.order = metadata_int(metadata, "order", layer.order)
    layer.name = str(metadata.get("name", layer.name))
    layer.mask_enabled = bool(metadata.get("mask_enabled", layer.mask_enabled))
    layer.mask_edit_state = type(layer.mask_edit_state)(
        str(metadata.get("mask_edit_state", layer.mask_edit_state.value))
    )
    layer.group_composite_mode = type(layer.group_composite_mode)(
        str(metadata.get("group_composite_mode", layer.group_composite_mode.value))
    )
    parent_id = str(metadata.get("parent_id", layer.parent_id or ""))
    layer.parent_id = parent_id or None
    layer.generation = metadata_int(metadata, "generation", layer.generation)


def _metadata_float(metadata: dict[str, object], key: str, default: float) -> float:
    value = metadata.get(key, default)
    return float(value) if isinstance(value, (str, int, float)) else default


def metadata_int(metadata: dict[str, object], key: str, default: int) -> int:
    value = metadata.get(key, default)
    return int(value) if isinstance(value, (str, int, float)) else default
