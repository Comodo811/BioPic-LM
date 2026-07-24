"""Core selection channel.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class CoreSelection:
    """Image selection stored as an independent mask channel."""

    mask: np.ndarray

    @classmethod
    def empty(cls, width: int, height: int) -> CoreSelection:
        """Create an empty selection channel."""
        return cls(np.zeros((height, width), dtype=np.float32))

    @classmethod
    def rectangle(cls, width: int, height: int, rect: tuple[int, int, int, int]) -> CoreSelection:
        """Create a rectangular selection."""
        selection = cls.empty(width, height)
        x, y, rect_width, rect_height = rect
        selection.mask[y : y + rect_height, x : x + rect_width] = 1.0
        return selection

    @classmethod
    def ellipse(cls, width: int, height: int, rect: tuple[int, int, int, int]) -> CoreSelection:
        """Create an elliptical selection."""
        selection = cls.empty(width, height)
        x, y, rect_width, rect_height = rect
        yy, xx = np.ogrid[:rect_height, :rect_width]
        cx = (rect_width - 1) / 2.0
        cy = (rect_height - 1) / 2.0
        rx = max(rect_width / 2.0, 0.5)
        ry = max(rect_height / 2.0, 0.5)
        mask = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
        selection.mask[y : y + rect_height, x : x + rect_width][mask] = 1.0
        return selection
