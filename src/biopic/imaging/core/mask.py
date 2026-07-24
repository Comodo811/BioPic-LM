"""Core grayscale mask drawable.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from biopic.models.editing import MaskViewMode


@dataclass(slots=True)
class CoreMask:
    """Independent grayscale mask connected to a layer blend operation."""

    pixels: np.ndarray | None = None
    enabled: bool = True
    edit_state: MaskViewMode = MaskViewMode.APPLY

    def effective_alpha(self, shape: tuple[int, int]) -> np.ndarray:
        """Return normalized mask alpha for a target shape."""
        if not self.enabled or self.edit_state is MaskViewMode.SHOW or self.pixels is None:
            return np.ones(shape, dtype=np.float32)
        mask = self.pixels[..., 0] if self.pixels.ndim == 3 else self.pixels
        result = np.zeros(shape, dtype=np.float32)
        height = min(shape[0], mask.shape[0])
        width = min(shape[1], mask.shape[1])
        mask_float = mask.astype(np.float32, copy=False)
        if np.issubdtype(mask.dtype, np.integer):
            mask_float = mask_float / float(np.iinfo(mask.dtype).max)
        result[:height, :width] = np.clip(mask_float[:height, :width], 0.0, 1.0)
        return result
