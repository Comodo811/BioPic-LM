"""Enhancement and filtering operations."""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage.restoration import (
    denoise_bilateral,
    denoise_nl_means,
    denoise_tv_chambolle,
    denoise_wavelet,
    richardson_lucy,
)

from biopic.imaging.dtype import restore_dtype, to_float


def high_pass(
    image: np.ndarray,
    *,
    sigma: float,
    amount: float = 1.0,
    threshold: float = 0.0,
    halo_suppression: float = 0.0,
    luminance_only: bool = False,
) -> np.ndarray:
    """Apply GIMP-style high-pass sharpening with Linear Light compositing."""
    if sigma <= 0:
        raise ValueError("sigma must be greater than zero")
    data, dtype = to_float(image)
    del threshold, halo_suppression, luminance_only
    contrast = max(0.0, float(amount))
    result = data.copy()
    if data.ndim == 3 and data.shape[-1] >= 4:
        color = data[..., :3]
        result[..., :3] = _linear_light_high_pass(color, sigma, contrast)
        result[..., 3:] = data[..., 3:]
    else:
        result = _linear_light_high_pass(data, sigma, contrast)
    return restore_dtype(np.clip(result, 0.0, 1.0), dtype)


def _linear_light_high_pass(data: np.ndarray, sigma: float, contrast: float) -> np.ndarray:
    high_pass_layer = _gimp_high_pass_layer(data, sigma, contrast)
    return data + 2.0 * (high_pass_layer - 0.5)


def _gimp_high_pass_layer(data: np.ndarray, sigma: float, contrast: float) -> np.ndarray:
    sigma_spec: float | tuple[float, float, float] = sigma
    if data.ndim == 3:
        sigma_spec = (sigma, sigma, 0.0)
    blurred = ndimage.gaussian_filter(data, sigma=sigma_spec, mode="reflect")
    over = np.clip(0.5 + 0.5 * (data - blurred), 0.0, 1.0)
    inverse_gamma = 1.0 / 2.2
    perceptual = np.power(over, inverse_gamma)
    neutral = np.float32(0.5**inverse_gamma)
    contrasted = (perceptual - neutral) * contrast + neutral
    return np.power(np.clip(contrasted, 0.0, 1.0), 2.2)


def gaussian_smooth(image: np.ndarray, sigma: float) -> np.ndarray:
    """Apply Gaussian smoothing."""
    if sigma <= 0:
        raise ValueError("sigma must be greater than zero")
    data, dtype = to_float(image)
    sigma_spec: float | tuple[float, float, float] = sigma
    if data.ndim == 3:
        sigma_spec = (sigma, sigma, 0.0)
    return restore_dtype(ndimage.gaussian_filter(data, sigma=sigma_spec, mode="reflect"), dtype)


def median_filter(image: np.ndarray, radius: int) -> np.ndarray:
    """Apply median filtering with a square footprint."""
    if radius <= 0:
        raise ValueError("radius must be greater than zero")
    data, dtype = to_float(image)
    size: int | tuple[int, int, int] = radius * 2 + 1
    if data.ndim == 3:
        size = (radius * 2 + 1, radius * 2 + 1, 1)
    return restore_dtype(ndimage.median_filter(data, size=size, mode="reflect"), dtype)


def bilateral_filter(
    image: np.ndarray, sigma_color: float = 0.05, sigma_spatial: float = 3.0
) -> np.ndarray:
    """Apply edge-preserving bilateral denoising."""
    data, dtype = to_float(image)
    result = denoise_bilateral(
        data,
        sigma_color=sigma_color,
        sigma_spatial=sigma_spatial,
        channel_axis=-1 if data.ndim == 3 else None,
    )
    return restore_dtype(np.asarray(result), dtype)


def non_local_means(image: np.ndarray, patch_size: int = 5, h: float = 0.08) -> np.ndarray:
    """Apply non-local means denoising."""
    data, dtype = to_float(image)
    result = denoise_nl_means(
        data,
        patch_size=patch_size,
        h=h,
        fast_mode=True,
        channel_axis=-1 if data.ndim == 3 else None,
    )
    return restore_dtype(np.asarray(result), dtype)


def wavelet_denoise(image: np.ndarray) -> np.ndarray:
    """Apply wavelet denoising."""
    data, dtype = to_float(image)
    result = denoise_wavelet(data, channel_axis=-1 if data.ndim == 3 else None, rescale_sigma=True)
    return restore_dtype(np.asarray(result), dtype)


def total_variation_denoise(image: np.ndarray, weight: float = 0.08) -> np.ndarray:
    """Apply total-variation denoising."""
    data, dtype = to_float(image)
    result = denoise_tv_chambolle(data, weight=weight, channel_axis=-1 if data.ndim == 3 else None)
    return restore_dtype(np.asarray(result), dtype)


def gimp_noise_reduction(image: np.ndarray, *, strength: int = 4) -> np.ndarray:
    """Apply GIMP-style iterative anisotropic noise reduction.

    GIMP exposes GEGL's noise-reduction operation as a single Strength value,
    implemented as repeated anisotropic smoothing iterations. Each iteration
    smooths along the local axis with the lowest second-derivative error, which
    reduces grain while avoiding the patchy texture and color mixing produced by
    the previous median/bilateral/NL-means pipeline.
    """
    iterations = _coerce_gimp_noise_reduction_strength(strength)
    data, dtype = to_float(image)
    if iterations == 0:
        return restore_dtype(data.copy(), dtype)
    result = data.copy()
    if data.ndim == 3 and data.shape[-1] >= 4:
        color = data[..., :3]
        result[..., :3] = _gimp_anisotropic_smooth(color, iterations)
        result[..., 3:] = data[..., 3:]
    else:
        result = _gimp_anisotropic_smooth(data, iterations)
    return restore_dtype(np.clip(result, 0.0, 1.0), dtype)


def microscopy_noise_reduction(
    image: np.ndarray,
    *,
    luminance_strength: float = 0.08,
    chroma_strength: float = 0.04,
    impulse_radius: int = 1,
    preserve_edges: bool = True,
    strength: int | None = None,
) -> np.ndarray:
    """Compatibility wrapper for GIMP-style noise reduction."""
    if luminance_strength < 0 or chroma_strength < 0:
        raise ValueError("noise-reduction strengths must be non-negative")
    del impulse_radius, preserve_edges
    iterations = 4 if strength is None else strength
    return gimp_noise_reduction(image, strength=iterations)


def _coerce_gimp_noise_reduction_strength(strength: int | float) -> int:
    return int(np.clip(round(float(strength)), 0, 32))


def _gimp_anisotropic_smooth(data: np.ndarray, iterations: int) -> np.ndarray:
    if data.ndim == 2:
        return _gimp_anisotropic_smooth_plane(data, iterations)
    channels = [
        _gimp_anisotropic_smooth_plane(data[..., channel], iterations)
        for channel in range(data.shape[-1])
    ]
    return np.stack(channels, axis=-1)


def _gimp_anisotropic_smooth_plane(plane: np.ndarray, iterations: int) -> np.ndarray:
    current = plane.astype(np.float32, copy=True)
    for _ in range(iterations):
        padded = np.pad(current, 1, mode="reflect")
        center = padded[1:-1, 1:-1]
        neighbours = (
            padded[:-2, :-2],
            padded[:-2, 1:-1],
            padded[:-2, 2:],
            padded[1:-1, :-2],
            padded[1:-1, 2:],
            padded[2:, :-2],
            padded[2:, 1:-1],
            padded[2:, 2:],
        )
        axes = (
            (neighbours[0], neighbours[7]),
            (neighbours[1], neighbours[6]),
            (neighbours[2], neighbours[5]),
            (neighbours[3], neighbours[4]),
        )
        metric_reference = tuple((center * 2.0 - before - after) ** 2 for before, after in axes)
        total = center.copy()
        count = np.ones(center.shape, dtype=np.float32)
        for neighbour in neighbours:
            value = (center + neighbour) * 0.5
            valid = np.ones(center.shape, dtype=bool)
            for axis, (before, after) in enumerate(axes):
                metric_new = (value * 2.0 - before - after) ** 2
                valid &= metric_new <= metric_reference[axis]
            total += np.where(valid, value, 0.0)
            count += valid
        current = total / count
    return current



def wavelet_sharpen(
    image: np.ndarray,
    *,
    levels: int = 4,
    amount: float = 0.35,
    threshold: float = 0.01,
    luminance_only: bool = False,
) -> np.ndarray:
    """Sharpen selected spatial-frequency bands with conservative defaults."""
    if levels <= 0:
        raise ValueError("levels must be positive")
    data, dtype = to_float(image)
    target = _luminance(data) if luminance_only and data.ndim == 3 else data
    residual = target
    enhanced = np.zeros_like(target, dtype=np.float32)
    for level in range(levels):
        sigma = float(2**level)
        blurred = _gaussian_float(residual, sigma)
        detail = residual - blurred
        detail = np.where(np.abs(detail) >= threshold, detail, 0.0)
        enhanced += detail * amount
        residual = blurred
    if luminance_only and data.ndim == 3:
        result = _apply_luminance_delta(data, enhanced)
    else:
        result = data + enhanced
    return restore_dtype(np.clip(result, 0.0, 1.0), dtype)


def local_contrast(
    image: np.ndarray,
    *,
    radius: float = 8.0,
    amount: float = 0.25,
    threshold: float = 0.01,
    shadow_protection: float = 0.25,
    highlight_protection: float = 0.05,
    halo_suppression: float = 0.25,
    luminance_only: bool = True,
) -> np.ndarray:
    """Apply edge-aware local contrast using bilateral base/detail decomposition."""
    if radius <= 0:
        raise ValueError("radius must be greater than zero")
    data, dtype = to_float(image)
    target = _luminance(data) if luminance_only and data.ndim == 3 else data
    base = _gaussian_float(target, radius)
    detail = target - base
    detail = np.where(np.abs(detail) >= threshold, detail, 0.0)
    edges = _edge_strength(target)
    detail *= np.clip(edges / max(threshold, 1e-6), 0.0, 1.0)
    protection = np.ones_like(target, dtype=np.float32)
    if shadow_protection > 0:
        protection *= np.clip(target / shadow_protection, 0.0, 1.0)
    if highlight_protection > 0:
        protection *= np.clip((1.0 - target) / highlight_protection, 0.0, 1.0)
    detail = detail * protection
    if luminance_only and data.ndim == 3:
        result = _apply_luminance_delta(data, detail * amount)
    else:
        result = data + detail * amount
    return restore_dtype(np.clip(result, 0.0, 1.0), dtype)


def deconvolve_richardson_lucy(
    image: np.ndarray,
    *,
    radius: float = 1.5,
    iterations: int = 8,
    amount: float = 0.5,
    damping: float = 0.001,
) -> np.ndarray:
    """Conservative Richardson-Lucy deconvolution with result blending.

    This does not recover information that was never recorded; excessive
    iterations can amplify noise and ringing.
    """
    if radius <= 0 or iterations <= 0:
        raise ValueError("radius and iterations must be positive")
    data, dtype = to_float(image)
    psf = _gaussian_psf(radius)
    working = np.clip(data, damping, 1.0)
    if working.ndim == 3:
        channels = [
            richardson_lucy(working[..., channel], psf, num_iter=iterations, clip=False)
            for channel in range(working.shape[-1])
        ]
        deconvolved = np.stack(channels, axis=-1)
    else:
        deconvolved = richardson_lucy(working, psf, num_iter=iterations, clip=False)
    mixed = data * (1.0 - amount) + np.asarray(deconvolved) * amount
    return restore_dtype(np.clip(mixed, 0.0, 1.0), dtype)


def _gaussian_float(data: np.ndarray, sigma: float) -> np.ndarray:
    sigma_spec: float | tuple[float, float, float] = sigma
    if data.ndim == 3:
        sigma_spec = (sigma, sigma, 0.0)
    return ndimage.gaussian_filter(data, sigma=sigma_spec, mode="reflect")


def _luminance(data: np.ndarray) -> np.ndarray:
    return data[..., 0] * 0.2126 + data[..., 1] * 0.7152 + data[..., 2] * 0.0722


def _apply_luminance_delta(data: np.ndarray, delta: np.ndarray) -> np.ndarray:
    result = data.copy()
    result[..., :3] = result[..., :3] + delta[..., None]
    return result


def _gaussian_psf(radius: float) -> np.ndarray:
    half_size = max(2, int(np.ceil(radius * 3)))
    axis = np.arange(-half_size, half_size + 1, dtype=np.float32)
    yy, xx = np.meshgrid(axis, axis)
    psf = np.exp(-0.5 * (xx**2 + yy**2) / (radius**2))
    psf /= np.sum(psf)
    return psf.astype(np.float32)


def _edge_strength(data: np.ndarray) -> np.ndarray:
    if data.ndim == 3:
        channels = [
            ndimage.gaussian_gradient_magnitude(data[..., channel], sigma=1.0, mode="reflect")
            for channel in range(data.shape[-1])
        ]
        return np.maximum.reduce(channels)
    return ndimage.gaussian_gradient_magnitude(data, sigma=1.0, mode="reflect")
