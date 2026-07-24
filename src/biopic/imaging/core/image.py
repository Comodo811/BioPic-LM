"""Core image document object.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from biopic.imaging.core.drawable import CoreDrawable
from biopic.imaging.core.item import CoreItem
from biopic.imaging.core.layer import CoreGroupLayer, CoreLayer
from biopic.imaging.core.mask import CoreMask
from biopic.imaging.core.projection import CoreProjection
from biopic.imaging.core.selection import CoreSelection
from biopic.imaging.core.undo import CoreUndoManager
from biopic.imaging.layer_buffers import layer_alpha_buffer, layer_content_buffer
from biopic.models.editing import EditLayer, EditLayerType, LayerContentKind
from biopic.models.project import Project


@dataclass(slots=True)
class CoreImage:
    """Image document containing layers, selection, projection and undo."""

    project: Project
    source_node_id: str
    base: np.ndarray
    root_layers: list[CoreLayer]
    layers_by_id: dict[str, CoreLayer]
    selection: CoreSelection
    undo: CoreUndoManager = field(default_factory=CoreUndoManager)
    projection: CoreProjection | None = None

    @property
    def width(self) -> int:
        """Image width."""
        return int(self.base.shape[1])

    @property
    def height(self) -> int:
        """Image height."""
        return int(self.base.shape[0])

    def layer_tree_generation(self) -> tuple[tuple[str, int], ...]:
        """Return a stable generation key for projection invalidation."""
        return tuple((layer.item.id, layer.item.generation) for layer in self.layers_by_id.values())


def core_image_from_project(project: Project, source_node_id: str, base: np.ndarray) -> CoreImage:
    """Build a core image tree from BioPic LM project edit layers."""
    edit_layers = sorted(
        (
            layer
            for layer in project.edit_layers.values()
            if layer.source_node_id in {None, source_node_id}
        ),
        key=lambda item: item.order,
    )
    layers_by_id: dict[str, CoreLayer] = {}
    root_layers: list[CoreLayer] = []
    pending_children: dict[str, list[CoreLayer]] = {}
    for edit_layer in edit_layers:
        layer = _core_layer_from_edit_layer(edit_layer, base)
        layers_by_id[layer.item.id] = layer
        if edit_layer.parent_id:
            pending_children.setdefault(edit_layer.parent_id, []).append(layer)
        else:
            root_layers.append(layer)
    for parent_id, children in pending_children.items():
        parent = layers_by_id.get(parent_id)
        if isinstance(parent, CoreGroupLayer):
            parent.children.extend(sorted(children, key=lambda layer: layer.order))
    return CoreImage(
        project=project,
        source_node_id=source_node_id,
        base=base,
        root_layers=root_layers,
        layers_by_id=layers_by_id,
        selection=CoreSelection.empty(int(base.shape[1]), int(base.shape[0])),
    )


def _core_layer_from_edit_layer(layer: EditLayer, base: np.ndarray) -> CoreLayer:
    item = CoreItem(
        id=layer.id,
        name=layer.name,
        visible=layer.visible,
        offset_x=layer.offset_x,
        offset_y=layer.offset_y,
        parent_id=layer.parent_id,
        generation=layer.generation,
    )
    if layer.layer_type is EditLayerType.GROUP:
        return CoreGroupLayer(
            item=item,
            drawable=None,
            layer_type=layer.layer_type,
            opacity=layer.opacity,
            blend_mode=layer.blend_mode,
            order=layer.order,
            composite_mode=layer.group_composite_mode,
        )
    content, alpha = _layer_content_alpha(layer, base)
    drawable = CoreDrawable(
        item=item,
        content=content,
        alpha=alpha,
        mask=CoreMask(layer.mask_pixels(), layer.mask_enabled, layer.mask_edit_state),
    )
    return CoreLayer(
        item=item,
        drawable=drawable,
        layer_type=layer.layer_type,
        opacity=layer.opacity,
        blend_mode=layer.blend_mode,
        order=layer.order,
    )


def _layer_content_alpha(layer: EditLayer, base: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if layer.content_kind is LayerContentKind.SOURCE:
        return base, np.ones(base.shape[:2], dtype=np.float32)
    content = layer_content_buffer(layer.id)
    if content is None:
        content = layer.content_pixels()
    if content is None:
        content = np.zeros_like(base)
    alpha = layer_alpha_buffer(layer.id)
    if alpha is None:
        alpha = layer.alpha_pixels()
    if alpha is None:
        alpha = np.zeros(base.shape[:2], dtype=np.float32)
    return content, alpha.astype(np.float32, copy=False)
