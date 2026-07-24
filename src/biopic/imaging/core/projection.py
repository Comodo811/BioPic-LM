"""Core projection object.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class CoreProjection:
    """Validated image projection state plus invalidated regions."""

    color: np.ndarray
    alpha: np.ndarray
    generation: int = 0
    invalid_regions: list[tuple[int, int, int, int]] = field(default_factory=list)

    @classmethod
    def from_state(cls, state: object) -> CoreProjection:
        """Create a projection from an alpha-carrying render state."""
        return cls(color=getattr(state, "color"), alpha=getattr(state, "alpha"))

    def invalidate(self, rect: tuple[int, int, int, int]) -> None:
        """Mark projection region invalid."""
        self.invalid_regions.append(rect)
        self.generation += 1

    def validate(self) -> None:
        """Clear invalidated regions after rendering."""
        self.invalid_regions.clear()
