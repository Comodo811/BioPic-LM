"""Native GIMP-style hue/saturation backend."""

from __future__ import annotations

import numpy as np

try:  # pragma: no cover - exercised when the extension is built
    from biopic.native import _hue_saturation_native  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    _hue_saturation_native = None


def native_available() -> bool:
    """Return whether the compiled hue/saturation backend is importable."""
    return _hue_saturation_native is not None


def apply_hue_saturation(
    image: np.ndarray,
    hue_values: np.ndarray,
    lightness_values: np.ndarray,
    saturation_values: np.ndarray,
    overlap_percent: float,
) -> np.ndarray | None:
    """Apply GIMP-style hue/saturation with the native backend when supported."""
    if not _can_use_native(image):
        return None
    assert _hue_saturation_native is not None
    return _hue_saturation_native.apply_hue_saturation(
        np.ascontiguousarray(image),
        np.asarray(hue_values, dtype=np.float64),
        np.asarray(lightness_values, dtype=np.float64),
        np.asarray(saturation_values, dtype=np.float64),
        float(overlap_percent),
    )


def _can_use_native(image: np.ndarray) -> bool:
    return (
        _hue_saturation_native is not None
        and image.ndim == 3
        and image.shape[-1] >= 3
        and image.dtype
        in {
            np.dtype("uint8"),
            np.dtype("uint16"),
            np.dtype("int16"),
            np.dtype("float32"),
            np.dtype("float64"),
        }
    )
