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
from biopic.native.adjustments_backend import (
    noise_reduction as native_noise_reduction,
)


def high_pass(
    image: np.ndarray,
    *,
    sigma: float,
    amount: float = 1.0,
    threshold: float = 0.0,
    halo_suppression: float = 0.0,
    luminance_only: bool = False,
) -> np.ndarray:
    """Apply high-pass sharpening based on `I - G_sigma * I`."""
    if sigma <= 0:
        raise ValueError("sigma must be greater than zero")
    data, dtype = to_float(image)
    if luminance_only and data.ndim == 3 and data.shape[-1] >= 3:
        luminance = (
            data[..., 0] * 0.2126 + data[..., 1] * 0.7152 + data[..., 2] * 0.0722
        )
        blurred = ndimage.gaussian_filter(luminance, sigma=sigma, mode="reflect")
        detail = (luminance - blurred)[..., None]
    else:
        sigma_spec: float | tuple[float, float, float] = sigma
        if data.ndim == 3:
            sigma_spec = (sigma, sigma, 0.0)
        detail = data - ndimage.gaussian_filter(data, sigma=sigma_spec, mode="reflect")
    if threshold > 0:
        detail = np.where(np.abs(detail) >= threshold, detail, 0.0)
    sharpened = data + detail * amount
    if halo_suppression > 0:
        smoothed = _gaussian_float(sharpened, halo_suppression)
        sharpened = sharpened * 0.75 + smoothed * 0.25
    return restore_dtype(np.clip(sharpened, 0.0, 1.0), dtype)


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


def microscopy_noise_reduction(
    image: np.ndarray,
    *,
    luminance_strength: float = 0.08,
    chroma_strength: float = 0.04,
    impulse_radius: int = 1,
    preserve_edges: bool = True,
) -> np.ndarray:
    """Conservative denoising intended to preserve fine biological structures."""
    if luminance_strength < 0 or chroma_strength < 0:
        raise ValueError("noise-reduction strengths must be non-negative")
    native = native_noise_reduction(
        image,
        luminance_strength=float(luminance_strength),
        chroma_strength=float(chroma_strength),
        impulse_radius=int(impulse_radius),
        preserve_edges=bool(preserve_edges),
    )
    if native is not None and not np.array_equal(native, image):
        return native
    denoised = image
    if impulse_radius > 0:
        denoised = median_filter(denoised, impulse_radius)
    if preserve_edges:
        denoised = bilateral_filter(
            denoised,
            sigma_color=max(chroma_strength, 0.001),
            sigma_spatial=max(luminance_strength * 20.0, 1.0),
        )
    else:
        denoised = non_local_means(
            denoised,
            patch_size=5,
            h=max(luminance_strength, 0.001),
        )
    return denoised


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
