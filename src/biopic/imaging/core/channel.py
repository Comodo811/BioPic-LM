"""Core channel object.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from biopic.imaging.core.item import CoreItem


@dataclass(slots=True)
class CoreChannel:
    """Named grayscale channel, used for selections and future saved channels."""

    item: CoreItem
    pixels: np.ndarray
    opacity: float = 1.0
