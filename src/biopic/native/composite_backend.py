"""Native compositing backend.

The C extension handles the normal-blend hot path. Python remains the fallback
for source checkouts and unsupported data layouts.
"""

from __future__ import annotations

import numpy as np

try:  # pragma: no cover - exercised only when the extension is built
    from biopic.native import _composite_native  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - fallback is covered instead
    _composite_native = None


def native_available() -> bool:
    """Return whether the compiled compositing backend is importable."""
    return _composite_native is not None


def blend_normal_in_place(
    background: np.ndarray,
    foreground: np.ndarray,
    alpha: np.ndarray,
    *,
    opacity: float = 1.0,
) -> bool:
    """Blend foreground over background in place when the native kernel supports it."""
    if not _can_use_native(background, foreground, alpha):
        return False
    assert _composite_native is not None
    _composite_native.blend_normal_in_place(
        background,
        foreground,
        alpha,
        float(opacity),
    )
    return True


def blend_normal_offset_in_place(
    background: np.ndarray,
    foreground: np.ndarray,
    alpha: np.ndarray | None,
    mask: np.ndarray | None = None,
    *,
    rect_origin: tuple[int, int] = (0, 0),
    offset: tuple[int, int] = (0, 0),
    opacity: float = 1.0,
) -> bool:
    """Blend an offset foreground over a background region without fitted arrays."""
    if not _can_use_native_offset(background, foreground, alpha, mask):
        return False
    assert _composite_native is not None
    _composite_native.blend_normal_offset_in_place(
        background,
        foreground,
        alpha,
        mask,
        int(rect_origin[0]),
        int(rect_origin[1]),
        int(offset[0]),
        int(offset[1]),
        float(opacity),
    )
    return True


def _can_use_native(
    background: np.ndarray,
    foreground: np.ndarray,
    alpha: np.ndarray,
) -> bool:
    return (
        _composite_native is not None
        and background.dtype == np.float32
        and background.flags.c_contiguous
        and foreground.flags.c_contiguous
        and alpha.dtype == np.float32
        and alpha.flags.c_contiguous
        and background.ndim in {2, 3}
        and foreground.ndim in {2, 3}
        and alpha.ndim == 2
        and foreground.shape[:2] == background.shape[:2]
        and alpha.shape == background.shape[:2]
        and foreground.dtype
        in {
            np.dtype("uint8"),
            np.dtype("uint16"),
            np.dtype("int16"),
            np.dtype("float32"),
            np.dtype("float64"),
        }
    )


def _can_use_native_offset(
    background: np.ndarray,
    foreground: np.ndarray,
    alpha: np.ndarray | None,
    mask: np.ndarray | None,
) -> bool:
    return (
        _composite_native is not None
        and background.dtype == np.float32
        and background.flags.c_contiguous
        and foreground.flags.c_contiguous
        and background.ndim in {2, 3}
        and foreground.ndim in {2, 3}
        and foreground.dtype
        in {
            np.dtype("uint8"),
            np.dtype("uint16"),
            np.dtype("int16"),
            np.dtype("float32"),
            np.dtype("float64"),
        }
        and (
            alpha is None
            or (
                alpha.dtype == np.float32
                and alpha.flags.c_contiguous
                and alpha.ndim == 2
                and alpha.shape == foreground.shape[:2]
            )
        )
        and (
            mask is None
            or (
                mask.flags.c_contiguous
                and mask.ndim in {2, 3}
                and mask.shape[:2] == foreground.shape[:2]
                and mask.dtype
                in {
                    np.dtype("bool"),
                    np.dtype("uint8"),
                    np.dtype("uint16"),
                    np.dtype("int16"),
                    np.dtype("float32"),
                    np.dtype("float64"),
                }
            )
        )
    )
