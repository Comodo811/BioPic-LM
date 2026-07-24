"""Native display conversion backend."""

from __future__ import annotations

import numpy as np

try:  # pragma: no cover - exercised when the extension is built
    from biopic.native import _display_native  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    _display_native = None


def native_available() -> bool:
    """Return whether the compiled display backend is importable."""
    return _display_native is not None


def to_display_uint8(
    pixels: np.ndarray,
    display_range: tuple[float, float],
) -> np.ndarray | None:
    """Scale pixels to uint8 with the native backend when supported."""
    if not _can_use_native(pixels):
        return None
    low, high = display_range
    assert _display_native is not None
    return _display_native.to_display_uint8(
        np.ascontiguousarray(pixels),
        float(low),
        float(high),
    )


def _can_use_native(pixels: np.ndarray) -> bool:
    return (
        _display_native is not None
        and pixels.ndim in {2, 3}
        and pixels.dtype
        in {
            np.dtype("uint8"),
            np.dtype("uint16"),
            np.dtype("int16"),
            np.dtype("float32"),
            np.dtype("float64"),
        }
    )
