"""Native white-balance backend."""

from __future__ import annotations

import numpy as np

try:  # pragma: no cover - exercised when the extension is built
    from biopic.native import _white_balance_native  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    _white_balance_native = None


def native_available() -> bool:
    """Return whether the compiled white-balance backend is importable."""
    return _white_balance_native is not None


def apply_rgb_gains(
    image: np.ndarray, red: float, green: float, blue: float
) -> np.ndarray | None:
    """Apply RGB gains with the native backend when supported."""
    if not _can_use_native(image):
        return None
    assert _white_balance_native is not None
    return _white_balance_native.apply_rgb_gains(
        np.ascontiguousarray(image),
        float(red),
        float(green),
        float(blue),
    )


def _can_use_native(image: np.ndarray) -> bool:
    return (
        _white_balance_native is not None
        and image.ndim in {2, 3}
        and image.dtype
        in {
            np.dtype("uint8"),
            np.dtype("uint16"),
            np.dtype("int16"),
            np.dtype("float32"),
            np.dtype("float64"),
        }
    )
