"""Geometry operations for non-destructive edit nodes."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


def crop(image: np.ndarray, x: int, y: int, width: int, height: int) -> np.ndarray:
    """Crop an image without resampling."""
    if width <= 0 or height <= 0:
        raise ValueError("crop width and height must be positive")
    array = np.asarray(image)
    if x < 0 or y < 0 or x + width > array.shape[1] or y + height > array.shape[0]:
        raise ValueError("crop rectangle must stay inside the image")
    return array[y : y + height, x : x + width].copy()


def rotate_90(image: np.ndarray, turns: int) -> np.ndarray:
    """Rotate by 90-degree increments."""
    return np.rot90(image, k=turns).copy()


def flip_horizontal(image: np.ndarray) -> np.ndarray:
    """Flip image horizontally."""
    return np.flip(np.asarray(image), axis=1).copy()


def flip_vertical(image: np.ndarray) -> np.ndarray:
    """Flip image vertically."""
    return np.flip(np.asarray(image), axis=0).copy()


def resize_uniform(image: np.ndarray, scale: float) -> np.ndarray:
    """Uniformly resize an image, preserving aspect ratio."""
    if scale <= 0:
        raise ValueError("scale must be greater than zero")
    array = np.asarray(image)
    zoom: tuple[float, ...] = (scale, scale) if array.ndim == 2 else (scale, scale, 1.0)
    return ndimage.zoom(array, zoom=zoom, order=1)
