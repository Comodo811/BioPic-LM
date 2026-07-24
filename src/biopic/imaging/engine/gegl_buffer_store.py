"""GEGL-backed drawable buffer objects.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from biopic.imaging.engine.gegl_ctypes import GeglCtypesBridge


@dataclass(slots=True)
class GeglDrawableBuffer:
    """An independently addressable tiled image buffer backed by GEGL."""

    bridge: GeglCtypesBridge
    pointer: object
    width: int
    height: int
    channels: int
    dtype: np.dtype
    generation: int = 0
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_array(
        cls,
        pixels: np.ndarray,
        *,
        bridge: GeglCtypesBridge | None = None,
    ) -> GeglDrawableBuffer:
        """Create a GEGL drawable buffer from a NumPy image."""
        active_bridge = bridge or GeglCtypesBridge()
        array = np.asarray(pixels)
        pointer = active_bridge.ndarray_to_buffer(array)
        channels = 1 if array.ndim == 2 else int(array.shape[2])
        return cls(
            bridge=active_bridge,
            pointer=pointer,
            width=int(array.shape[1]),
            height=int(array.shape[0]),
            channels=channels,
            dtype=array.dtype,
        )

    def read(self) -> np.ndarray:
        """Read the complete drawable into a NumPy array."""
        return self.read_region((0, 0, self.width, self.height))

    def render(self) -> np.ndarray:
        """Render the drawable through a GEGL graph buffer-source node."""
        return self.bridge.blit_buffer_source(
            self.pointer,
            width=self.width,
            height=self.height,
            channels=self.channels,
            dtype=self.dtype,
        )

    def read_region(self, rect: tuple[int, int, int, int]) -> np.ndarray:
        """Read a rectangular region from the drawable."""
        x, y, width, height = _clamp_rect(rect, self.width, self.height)
        return self.bridge.buffer_to_ndarray(
            self.pointer,
            width=width,
            height=height,
            channels=self.channels,
            dtype=self.dtype,
            x=x,
            y=y,
        )

    def write_region(self, rect: tuple[int, int, int, int], pixels: np.ndarray) -> None:
        """Write a rectangular region into the drawable and bump its generation."""
        x, y, width, height = _clamp_rect(rect, self.width, self.height)
        array = np.asarray(pixels)
        if array.shape[:2] != (height, width):
            raise ValueError("Region pixel shape does not match target rectangle")
        self.bridge.write_region(self.pointer, array, x=x, y=y)
        self.generation += 1

    def close(self) -> None:
        """Release the GEGL buffer."""
        if not self._closed:
            self.bridge.unref(self.pointer)
            self._closed = True

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def _clamp_rect(
    rect: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x, y, rect_width, rect_height = rect
    x = max(0, min(int(x), width))
    y = max(0, min(int(y), height))
    rect_width = max(0, min(int(rect_width), width - x))
    rect_height = max(0, min(int(rect_height), height - y))
    return x, y, rect_width, rect_height
