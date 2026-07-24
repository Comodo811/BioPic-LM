"""Native adjustment/filter helpers."""

from __future__ import annotations

import numpy as np

try:  # pragma: no cover - exercised when the extension is built
    from biopic.native import _adjustments_native  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    _adjustments_native = None


def native_available() -> bool:
    """Return whether the compiled adjustment backend is importable."""
    return _adjustments_native is not None


def high_pass(
    image: np.ndarray,
    sigma: float,
    amount: float,
    threshold: float,
    halo_suppression: float,
    luminance_only: bool,
) -> np.ndarray | None:
    """Apply high-pass sharpening with the native backend when supported."""
    if not _can_use_image(image):
        return None
    assert _adjustments_native is not None
    return _adjustments_native.high_pass(
        np.ascontiguousarray(image),
        float(sigma),
        float(amount),
        float(threshold),
        float(halo_suppression),
        bool(luminance_only),
    )


def noise_reduction(
    image: np.ndarray,
    luminance_strength: float,
    chroma_strength: float,
    impulse_radius: int,
    preserve_edges: bool,
) -> np.ndarray | None:
    """Apply RawTherapee-inspired luma/chroma noise reduction natively."""
    if not _can_use_image(image):
        return None
    assert _adjustments_native is not None
    return _adjustments_native.noise_reduction(
        np.ascontiguousarray(image),
        float(luminance_strength),
        float(chroma_strength),
        int(impulse_radius),
        bool(preserve_edges),
    )


def uniform_background_outside_selection(
    image: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Create a uniform background layer and alpha mask natively."""
    if not _can_use_image(image):
        return None
    mask = np.asarray(selection_mask, dtype=np.uint8)
    if mask.ndim != 2 or mask.shape[:2] != image.shape[:2]:
        return None
    assert _adjustments_native is not None
    background, alpha, color = _adjustments_native.uniform_background(
        np.ascontiguousarray(image),
        np.ascontiguousarray(mask),
        int(transition_px),
    )
    return background, alpha, color


def _can_use_image(image: np.ndarray) -> bool:
    return (
        _adjustments_native is not None
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
