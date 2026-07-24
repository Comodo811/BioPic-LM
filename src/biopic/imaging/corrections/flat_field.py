"""Flat-field and background correction."""

from __future__ import annotations

import numpy as np

from biopic.imaging.dtype import restore_dtype, to_float


def flat_field_correct(
    raw: np.ndarray,
    flat: np.ndarray,
    dark: np.ndarray | None = None,
    *,
    epsilon: float = 1e-6,
    normalization: float | None = None,
) -> np.ndarray:
    """Apply `(raw - dark) / (flat - dark) * C` with near-zero safeguards."""
    raw_f, dtype = to_float(raw)
    flat_f, _flat_dtype = to_float(_match_shape(flat, raw_f.shape))
    if dark is None:
        dark_f = np.zeros_like(raw_f, dtype=np.float32)
    else:
        dark_f, _dark_dtype = to_float(_match_shape(dark, raw_f.shape))
    denominator = flat_f - dark_f
    safe_denominator = np.where(np.abs(denominator) < epsilon, np.nan, denominator)
    corrected = (raw_f - dark_f) / safe_denominator
    constant = float(np.nanmean(denominator)) if normalization is None else normalization
    corrected = np.nan_to_num(corrected * constant, nan=0.0, posinf=1.0, neginf=0.0)
    return restore_dtype(np.clip(corrected, 0.0, 1.0), dtype)


def background_subtract(raw: np.ndarray, background: np.ndarray) -> np.ndarray:
    """Subtract a background image while preserving dtype range."""
    raw_f, dtype = to_float(raw)
    bg_f, _bg_dtype = to_float(_match_shape(background, raw_f.shape))
    return restore_dtype(np.clip(raw_f - bg_f, 0.0, 1.0), dtype)


def _match_shape(image: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    array = np.asarray(image)
    if array.shape == shape:
        return array
    if array.ndim == 2 and len(shape) == 3 and shape[-1] in {3, 4}:
        return np.repeat(array[..., None], shape[-1], axis=-1)
    raise ValueError(f"Correction image shape {array.shape} does not match raw shape {shape}")
