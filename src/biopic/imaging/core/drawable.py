"""Core drawable buffer object.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from biopic.imaging.core.item import CoreItem
from biopic.imaging.core.mask import CoreMask
from biopic.imaging.engine.gegl_buffer_store import GeglDrawableBuffer


@dataclass(slots=True)
class CoreDrawable:
    """Editable pixels plus alpha and optional GEGL buffer."""

    item: CoreItem
    content: np.ndarray
    alpha: np.ndarray
    mask: CoreMask | None = None
    gegl_buffer: GeglDrawableBuffer | None = None
    dirty_regions: list[tuple[int, int, int, int]] = field(default_factory=list)

    def mark_dirty(self, rect: tuple[int, int, int, int]) -> None:
        """Record a precise dirty drawable region."""
        self.dirty_regions.append(rect)
        self.item.bump_generation()

    def clear_dirty(self) -> None:
        """Clear drawable dirty regions after projection validation."""
        self.dirty_regions.clear()

    def ensure_gegl_buffer(self) -> GeglDrawableBuffer | None:
        """Return an existing GEGL buffer if this drawable has one."""
        return self.gegl_buffer
