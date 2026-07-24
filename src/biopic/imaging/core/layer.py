"""Core layer and group layer objects.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field

from biopic.imaging.core.drawable import CoreDrawable
from biopic.imaging.core.item import CoreItem
from biopic.models.editing import BlendMode, EditLayerType, GroupCompositeMode


@dataclass(slots=True)
class CoreLayer:
    """Layer compositing node over an optional drawable."""

    item: CoreItem
    drawable: CoreDrawable | None
    layer_type: EditLayerType
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    order: int = 0


@dataclass(slots=True)
class CoreGroupLayer(CoreLayer):
    """Nested layer subgraph."""

    composite_mode: GroupCompositeMode = GroupCompositeMode.PASS_THROUGH
    children: list[CoreLayer] = field(default_factory=list)
