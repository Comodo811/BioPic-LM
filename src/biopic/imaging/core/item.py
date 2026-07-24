"""Core item identity and transform state.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CoreItem:
    """Base object for image tree items, mirroring GIMP's item role."""

    id: str
    name: str
    visible: bool = True
    offset_x: int = 0
    offset_y: int = 0
    parent_id: str | None = None
    generation: int = 0

    def translate(self, dx: int, dy: int) -> None:
        """Move by metadata, not by copying pixels."""
        self.offset_x += int(dx)
        self.offset_y += int(dy)
        self.bump_generation()

    def set_visible(self, visible: bool) -> None:
        """Set visibility and invalidate graph state."""
        if self.visible != visible:
            self.visible = visible
            self.bump_generation()

    def bump_generation(self) -> None:
        """Advance this item's graph/content generation."""
        self.generation += 1
