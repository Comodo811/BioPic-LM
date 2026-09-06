"""Dispatch non-destructive edit operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from scipy import ndimage

from biopic.imaging.corrections import (
    auto_levels,
    background_subtract,
    crop,
    curve_adjust,
    flat_field_correct,
    gamma_correct,
    levels,
    white_balance_rendered,
)
from biopic.imaging.corrections.geometry import resize_uniform
from biopic.imaging.background import (
    fill_transparent_regions_with_background,
    global_textured_background_from_selection,
    healed_textured_background_from_selection,
)
from biopic.imaging.dtype import restore_dtype, to_float
from biopic.imaging.filters import (
    deconvolve_richardson_lucy,
    gaussian_smooth,
    gimp_noise_reduction,
    high_pass,
    local_contrast,
    median_filter,
    total_variation_denoise,
    wavelet_sharpen,
)
from biopic.native.hue_saturation_backend import apply_hue_saturation as native_hue_saturation

ProgressCallback = Callable[[str, float], None]


def apply_edit_operation(
    image: np.ndarray, operation: str, parameters: dict[str, Any]
) -> np.ndarray:
    """Apply an editing operation to pixels."""
    if operation == "levels":
        return levels(
            image,
            black_point=float(parameters.get("black_point", 0.0)),
            white_point=float(parameters.get("white_point", 1.0)),
            midtone=float(parameters.get("midtone", 1.0)),
            output_black=float(parameters.get("output_black", 0.0)),
            output_white=float(parameters.get("output_white", 1.0)),
            channel=str(parameters.get("channel", "rgb")),
        )
    if operation == "auto_levels":
        return auto_levels(image, percentile=float(parameters.get("percentile", 0.5)))
    if operation == "gamma":
        return gamma_correct(image, gamma=float(parameters.get("gamma", 1.0)))
    if operation == "curve":
        points = parameters.get("points", [(0.0, 0.0), (1.0, 1.0)])
        return curve_adjust(
            image,
            [(float(x), float(y)) for x, y in points],
            channel=str(parameters.get("channel", "rgb")),
            curve_type=str(parameters.get("curve_type", "smooth")),
        )
    if operation == "white_balance":
        return white_balance_rendered(
            image,
            method=str(parameters.get("method", "manual")),
            red=float(parameters.get("red", 1.0)),
            green=float(parameters.get("green", 1.0)),
            blue=float(parameters.get("blue", 1.0)),
            temperature=float(parameters.get("temperature", 6500.0)),
            tint=float(parameters.get("tint", 1.0)),
            preset=str(parameters.get("preset", "daylight")),
            blue_red_equalizer=float(parameters.get("blue_red_equalizer", 1.0)),
            awb_temperature_bias=float(parameters.get("awb_temperature_bias", 0.0)),
            histogram_low_clip=float(parameters.get("histogram_low_clip", 0.2)),
            histogram_high_clip=float(parameters.get("histogram_high_clip", 0.2)),
            histogram_bins=int(parameters.get("histogram_bins", 32)),
            raw_metadata=_coerce_raw_metadata(parameters.get("raw_metadata")),
            camera_matrix_strength=float(parameters.get("camera_matrix_strength", 0.0)),
            normalize=bool(parameters.get("normalize", True)),
            sample_rect=_coerce_sample_rect(parameters.get("sample_rect")),
            sample_size=int(parameters.get("sample_size", 16)),
        )
    if operation == "white_correct_background":
        return white_correct_background(
            image,
            selection_mask=parameters.get("selection_mask"),
            strength=float(parameters.get("strength", 1.0)),
        )
    if operation == "color_saturation":
        return color_saturation(
            image,
            saturation=float(parameters.get("saturation", 1.0)),
            lightness=float(parameters.get("lightness", 0.0)),
            hue=float(parameters.get("hue", 0.0)),
            overlap=float(parameters.get("overlap", 0.0)),
            hue_range=str(parameters.get("range", parameters.get("hue_range", "all"))),
            ranges=parameters.get("ranges"),
        )
    if operation == "high_pass":
        return high_pass(
            image,
            sigma=float(parameters.get("sigma", 2.0)),
            amount=float(parameters.get("amount", 1.0)),
            threshold=float(parameters.get("threshold", 0.0)),
            halo_suppression=float(parameters.get("halo_suppression", 0.0)),
            luminance_only=bool(parameters.get("luminance_only", False)),
        )
    if operation == "gaussian":
        return gaussian_smooth(image, sigma=float(parameters.get("sigma", 1.0)))
    if operation == "median":
        return median_filter(image, radius=int(parameters.get("radius", 1)))
    if operation == "invert":
        return invert(image)
    if operation == "threshold":
        return threshold(image, threshold_value=float(parameters.get("threshold", 0.5)))
    if operation == "sharpen":
        return unsharp_mask(
            image,
            sigma=float(parameters.get("sigma", 1.0)),
            amount=float(parameters.get("amount", 1.0)),
        )
    if operation == "denoise":
        return gimp_noise_reduction(image, strength=int(parameters.get("strength", 4)))
    if operation == "total_variation":
        return total_variation_denoise(image, weight=float(parameters.get("weight", 0.08)))
    if operation == "wavelet_sharpen":
        return wavelet_sharpen(
            image,
            levels=int(parameters.get("levels", 4)),
            amount=float(parameters.get("amount", 0.35)),
            threshold=float(parameters.get("threshold", 0.01)),
            luminance_only=bool(parameters.get("luminance_only", False)),
        )
    if operation == "local_contrast":
        return local_contrast(
            image,
            radius=float(parameters.get("radius", 8.0)),
            amount=float(parameters.get("amount", 0.25)),
            threshold=float(parameters.get("threshold", 0.01)),
            halo_suppression=float(parameters.get("halo_suppression", 0.25)),
            shadow_protection=float(parameters.get("shadow_protection", 0.25)),
            highlight_protection=float(parameters.get("highlight_protection", 0.05)),
            luminance_only=bool(parameters.get("luminance_only", True)),
        )
    if operation == "deconvolution":
        return deconvolve_richardson_lucy(
            image,
            radius=float(parameters.get("radius", 1.5)),
            iterations=int(parameters.get("iterations", 8)),
            amount=float(parameters.get("amount", 0.5)),
            damping=float(parameters.get("damping", 0.001)),
        )
    if operation == "rotate_90":
        return np.rot90(image, k=int(parameters.get("turns", 1)))
    if operation == "rotate_free":
        return rotate_free(image, angle=float(parameters.get("angle", 0.0)))
    if operation == "crop_rotated_image":
        return crop_rotated_image(image)
    if operation == "fill_rotated_background":
        return fill_rotated_background(image)
    if operation == "scale_uniform":
        return resize_uniform(image, scale=float(parameters.get("scale", 1.0)))
    if operation == "flip_horizontal":
        return np.flip(image, axis=1).copy()
    if operation == "flip_vertical":
        return np.flip(image, axis=0).copy()
    if operation == "crop":
        return crop(
            image,
            x=int(parameters["x"]),
            y=int(parameters["y"]),
            width=int(parameters["width"]),
            height=int(parameters["height"]),
        )
    if operation == "flat_field":
        flat = np.asarray(parameters["flat"])
        dark = parameters.get("dark")
        dark_array = None if dark is None else np.asarray(dark)
        return flat_field_correct(image, flat, dark_array)
    if operation == "background_subtract":
        return background_subtract(image, np.asarray(parameters["background"]))
    if operation == "subtract_background_estimated":
        return subtract_background_estimated(
            image,
            sigma=float(parameters.get("sigma", 24.0)),
            amount=float(parameters.get("amount", 1.0)),
        )
    if operation == "flat_field_correction_estimated":
        return flat_field_correction_estimated(
            image,
            sigma=float(parameters.get("sigma", 24.0)),
            strength=float(parameters.get("strength", parameters.get("amount", 1.0))),
            preserve_mean=bool(parameters.get("preserve_mean", True)),
        )
    if operation == "uniform_background_outside_selection":
        return uniform_background_outside_selection(
            image,
            selection_mask=parameters.get("selection_mask"),
        )
    if operation == "healed_uniform_background_outside_selection":
        return healed_uniform_background_outside_selection(
            image,
            selection_mask=parameters.get("selection_mask"),
        )
    raise ValueError(f"Unsupported edit operation: {operation}")


def invert(image: np.ndarray) -> np.ndarray:
    """Invert image intensity while preserving dtype."""
    data, dtype = to_float(image)
    return restore_dtype(1.0 - data, dtype)


def threshold(image: np.ndarray, threshold_value: float = 0.5) -> np.ndarray:
    """Apply a binary threshold."""
    data, dtype = to_float(image)
    if data.ndim == 3 and data.shape[-1] >= 3:
        gray = data[..., :3].mean(axis=-1)
        mask = gray >= threshold_value
        result = np.repeat(mask[..., None], data.shape[-1], axis=-1).astype(np.float32)
    else:
        result = (data >= threshold_value).astype(np.float32)
    return restore_dtype(result, dtype)


def unsharp_mask(image: np.ndarray, sigma: float = 1.0, amount: float = 1.0) -> np.ndarray:
    """Sharpen an image with an unsharp mask."""
    data, dtype = to_float(image)
    sigma_spec: float | tuple[float, float, float] = sigma
    if data.ndim == 3:
        sigma_spec = (sigma, sigma, 0.0)
    blurred = ndimage.gaussian_filter(data, sigma=sigma_spec, mode="reflect")
    return restore_dtype(np.clip(data + (data - blurred) * amount, 0.0, 1.0), dtype)


def rotate_free(image: np.ndarray, angle: float = 0.0) -> np.ndarray:
    """Rotate an image by an arbitrary angle and keep empty corners transparent."""
    if abs(float(angle)) < 1e-6:
        return np.asarray(image).copy()
    rgba, dtype = _float_rgba(image)
    rotated = ndimage.rotate(
        rgba,
        float(angle),
        axes=(0, 1),
        reshape=True,
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )
    rotated[..., :3] = np.clip(rotated[..., :3], 0.0, 1.0)
    rotated[..., 3] = np.clip(rotated[..., 3], 0.0, 1.0)
    return restore_dtype(rotated, dtype)


def crop_rotated_image(image: np.ndarray) -> np.ndarray:
    """Crop a transparent rotated image to the largest axis-aligned opaque rectangle."""
    rect = rotated_content_crop_rect(image)
    if rect is None:
        return np.asarray(image).copy()
    x, y, width, height = rect
    return np.asarray(image)[y : y + height, x : x + width].copy()


def fill_rotated_background(image: np.ndarray) -> np.ndarray:
    """Fill transparent rotated-image corners with extrapolated edge background."""
    data = np.asarray(image)
    if data.ndim != 3 or data.shape[2] < 4:
        return data.copy()
    alpha = _normalized_alpha(data[..., 3])
    if not np.any(alpha < (250.0 / 255.0)):
        return data.copy()
    return fill_transparent_regions_with_background(data)


def rotated_content_crop_rect(image: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return the largest opaque axis-aligned rectangle for a rotated transparent image."""
    data = np.asarray(image)
    if data.ndim != 3 or data.shape[2] < 4:
        if data.ndim < 2:
            return None
        return (0, 0, int(data.shape[1]), int(data.shape[0]))
    alpha = _normalized_alpha(data[..., 3])
    mask = alpha > (250.0 / 255.0)
    if not np.any(mask):
        return None
    if np.all(mask):
        return (0, 0, int(mask.shape[1]), int(mask.shape[0]))
    return _largest_true_rectangle(mask)


def _float_rgba(image: np.ndarray) -> tuple[np.ndarray, np.dtype]:
    data, dtype = to_float(image)
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 2:
        rgb = np.repeat(data[..., None], 3, axis=2)
        alpha = np.ones(data.shape, dtype=np.float32)
    elif data.ndim == 3 and data.shape[2] >= 4:
        rgb = data[..., :3]
        alpha = data[..., 3]
    elif data.ndim == 3 and data.shape[2] >= 3:
        rgb = data[..., :3]
        alpha = np.ones(data.shape[:2], dtype=np.float32)
    elif data.ndim == 3 and data.shape[2] == 1:
        rgb = np.repeat(data[..., :1], 3, axis=2)
        alpha = np.ones(data.shape[:2], dtype=np.float32)
    else:
        raise ValueError("rotate_free expects a 2-D or channel-last image")
    return np.dstack([rgb, alpha]).astype(np.float32, copy=False), dtype


def _normalized_alpha(alpha: np.ndarray) -> np.ndarray:
    alpha_array = np.asarray(alpha)
    if np.issubdtype(alpha_array.dtype, np.floating):
        if alpha_array.size and float(np.nanmax(alpha_array)) > 1.0:
            return np.clip(alpha_array.astype(np.float32) / 255.0, 0.0, 1.0)
        return np.clip(alpha_array.astype(np.float32), 0.0, 1.0)
    info = np.iinfo(alpha_array.dtype)
    return np.clip(alpha_array.astype(np.float32) / float(info.max), 0.0, 1.0)


def _largest_true_rectangle(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    height, width = mask.shape
    histogram = np.zeros(width, dtype=np.int32)
    best_area = 0
    best: tuple[int, int, int, int] | None = None
    for y in range(height):
        histogram = np.where(mask[y], histogram + 1, 0)
        stack: list[tuple[int, int]] = []
        for x in range(width + 1):
            current_height = int(histogram[x]) if x < width else 0
            start = x
            while stack and stack[-1][1] > current_height:
                previous_start, previous_height = stack.pop()
                area = previous_height * (x - previous_start)
                if area > best_area:
                    best_area = area
                    best = (
                        previous_start,
                        y - previous_height + 1,
                        x - previous_start,
                        previous_height,
                    )
                start = previous_start
            if not stack or stack[-1] != (start, current_height):
                stack.append((start, current_height))
    return best


def subtract_background_estimated(
    image: np.ndarray,
    sigma: float = 24.0,
    amount: float = 1.0,
    progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Subtract a smooth estimated background field."""
    _emit(progress, "Preparing background subtraction", 0.04)
    data, dtype = to_float(image)
    sigma = max(0.1, float(sigma))
    amount = max(0.0, float(amount))
    _emit(progress, "Estimating smooth background", 0.18)
    background = _progressive_spatial_gaussian(
        data,
        sigma=sigma,
        progress=progress,
        progress_start=0.20,
        progress_end=0.68,
        message="Estimating smooth background",
    )
    _emit(progress, "Subtracting background field", 0.78)
    corrected = data - background * amount + np.median(background, axis=(0, 1))
    result = restore_dtype(np.clip(corrected, 0.0, 1.0), dtype)
    _emit(progress, "Background subtraction complete", 1.0)
    return result


def flat_field_correction_estimated(
    image: np.ndarray,
    sigma: float = 24.0,
    strength: float = 1.0,
    preserve_mean: bool = True,
    progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Correct smooth multiplicative illumination using an estimated flat field."""
    _emit(progress, "Preparing flat-field correction", 0.04)
    data, dtype = to_float(image)
    sigma = max(0.1, float(sigma))
    strength = max(0.0, min(1.0, float(strength)))
    _emit(progress, "Estimating flat-field image", 0.16)
    flat = _progressive_spatial_gaussian(
        data,
        sigma=sigma,
        progress=progress,
        progress_start=0.18,
        progress_end=0.62,
        message="Estimating flat-field image",
    )
    _emit(progress, "Normalizing flat-field image", 0.72)
    eps = max(1e-6, float(np.percentile(flat, 0.1)) * 0.05)
    axes = (0, 1) if data.ndim >= 2 else None
    flat_reference = np.median(flat, axis=axes) if preserve_mean and axes is not None else 1.0
    _emit(progress, "Applying illumination correction", 0.84)
    corrected = data * flat_reference / np.maximum(flat, eps)
    blended = data * (1.0 - strength) + corrected * strength
    result = restore_dtype(np.clip(blended, 0.0, 1.0), dtype)
    _emit(progress, "Flat-field correction complete", 1.0)
    return result


def _progressive_spatial_gaussian(
    data: np.ndarray,
    *,
    sigma: float,
    progress: ProgressCallback | None,
    progress_start: float,
    progress_end: float,
    message: str,
) -> np.ndarray:
    if data.ndim != 3:
        _emit(progress, message, progress_start)
        result = ndimage.gaussian_filter(data, sigma=sigma, mode="reflect")
        _emit(progress, message, progress_end)
        return result
    channels = []
    total = max(1, data.shape[2])
    for channel in range(data.shape[2]):
        fraction = progress_start + (progress_end - progress_start) * (channel / total)
        _emit(progress, f"{message} channel {channel + 1}/{total}", fraction)
        channels.append(
            ndimage.gaussian_filter(
                data[..., channel],
                sigma=sigma,
                mode="reflect",
            )
        )
    _emit(progress, message, progress_end)
    return np.stack(channels, axis=-1)


def _emit(progress: ProgressCallback | None, message: str, fraction: float) -> None:
    if progress is not None:
        progress(message, fraction)


def uniform_background_outside_selection(
    image: np.ndarray,
    selection_mask: object | None = None,
    progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Replace pixels outside the selected organism with cloned background texture."""
    data = np.asarray(image)
    mask = _coerce_selection_mask(selection_mask, data.shape[:2])
    if mask is None:
        mask = _central_ellipse_mask(data.shape[:2])
    result = data.copy()
    outside = ~mask
    result[outside] = global_textured_background_from_selection(
        data,
        mask,
        0,
        progress=progress,
    )[outside]
    return result


def healed_uniform_background_outside_selection(
    image: np.ndarray,
    selection_mask: object | None = None,
    progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Replace pixels outside the selected organism with healed background texture."""
    data = np.asarray(image)
    mask = _coerce_selection_mask(selection_mask, data.shape[:2])
    if mask is None:
        mask = _central_ellipse_mask(data.shape[:2])
    result = data.copy()
    outside = ~mask
    result[outside] = healed_textured_background_from_selection(
        data,
        mask,
        0,
        progress=progress,
    )[outside]
    return result


def white_correct_background(
    image: np.ndarray,
    selection_mask: object | None = None,
    strength: float = 1.0,
) -> np.ndarray:
    """Scale channels so the detected background moves toward white."""
    data, dtype = to_float(image)
    mask = _coerce_selection_mask(selection_mask, data.shape[:2])
    outside = np.ones(data.shape[:2], dtype=bool) if mask is None else ~mask
    if not np.any(outside):
        return image.copy()
    bg = data[outside]
    if bg.size == 0:
        return image.copy()
    bg_color = np.percentile(bg.reshape(-1, *data.shape[2:]), 90.0, axis=0)
    target = 0.95
    gains = target / np.maximum(bg_color, 1e-6)
    gains = 1.0 + (gains - 1.0) * max(0.0, min(1.0, float(strength)))
    result = data * gains
    return restore_dtype(np.clip(result, 0.0, 1.0), dtype)


def color_saturation(
    image: np.ndarray,
    saturation: float = 0.0,
    lightness: float = 0.0,
    hue: float = 0.0,
    overlap: float = 0.0,
    hue_range: str = "all",
    ranges: object | None = None,
) -> np.ndarray:
    """Adjust hue, lightness, and saturation with GIMP-style hue ranges.

    The public UI uses GIMP's ranges: hue in degrees ``[-180, 180]`` and
    lightness/saturation/overlap in percent-like units ``[-100, 100]`` or
    ``[0, 100]``. Internally this mirrors GIMP's HSL operation: hue range
    selection, optional adjacent-range overlap, saturation scaling, signed
    lightness mapping, and alpha preservation.
    """
    data, dtype = to_float(image)
    if data.ndim < 3 or data.shape[-1] < 3:
        return image.copy()
    config = _gimp_hue_saturation_config(hue_range, hue, lightness, saturation, ranges)
    if _is_master_saturation_only(config, overlap):
        return _apply_master_saturation_only(data, dtype, float(config[2][0]) + 1.0)
    native = native_hue_saturation(image, config[0], config[1], config[2], overlap)
    if native is not None:
        return native
    rgb = np.clip(data[..., :3], 0.0, 1.0)
    hsl = _rgb_to_hsl(rgb)
    hsl = _apply_gimp_hue_saturation_hsl(hsl, config, overlap)
    adjusted = _hsl_to_rgb(hsl)
    result = data.copy()
    result[..., :3] = np.clip(adjusted, 0.0, 1.0)
    return restore_dtype(result, dtype)


_GIMP_HUE_RANGES = {
    "all": 0,
    "red": 1,
    "yellow": 2,
    "green": 3,
    "cyan": 4,
    "blue": 5,
    "magenta": 6,
}


def _gimp_hue_saturation_config(
    hue_range: str,
    hue_degrees: float,
    lightness_percent: float,
    saturation_percent: float,
    ranges: object | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hue_values = np.zeros(7, dtype=np.float32)
    lightness_values = np.zeros(7, dtype=np.float32)
    saturation_values = np.zeros(7, dtype=np.float32)
    if isinstance(ranges, dict):
        for name, values in ranges.items():
            if not isinstance(values, dict):
                continue
            index = _GIMP_HUE_RANGES.get(str(name).lower())
            if index is None:
                continue
            hue_values[index] = np.clip(float(values.get("hue", 0.0)), -180.0, 180.0) / 180.0
            lightness_values[index] = np.clip(
                float(values.get("lightness", 0.0)), -100.0, 100.0
            ) / 100.0
            saturation_values[index] = np.clip(
                float(values.get("saturation", 0.0)), -100.0, 100.0
            ) / 100.0
    else:
        range_index = _GIMP_HUE_RANGES.get(hue_range.lower(), 0)
        hue_values[range_index] = np.clip(float(hue_degrees), -180.0, 180.0) / 180.0
        lightness_values[range_index] = np.clip(float(lightness_percent), -100.0, 100.0) / 100.0
        saturation_values[range_index] = np.clip(float(saturation_percent), -100.0, 100.0) / 100.0
    return hue_values, lightness_values, saturation_values


def _is_master_saturation_only(
    config: tuple[np.ndarray, np.ndarray, np.ndarray], overlap_percent: float
) -> bool:
    hue_values, lightness_values, saturation_values = config
    return (
        abs(float(overlap_percent)) <= 1e-12
        and not bool(np.any(np.abs(hue_values) > 1e-12))
        and not bool(np.any(np.abs(lightness_values) > 1e-12))
        and not bool(np.any(np.abs(saturation_values[1:]) > 1e-12))
    )


def _apply_master_saturation_only(data: np.ndarray, dtype: np.dtype, scale: float) -> np.ndarray:
    result = data.copy()
    rgb = np.clip(result[..., :3], 0.0, 1.0)
    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    delta = maxc - minc
    chromatic = delta > 1e-12
    if not np.any(chromatic):
        return restore_dtype(result, dtype)
    lightness = (maxc + minc) * 0.5
    saturation = np.zeros_like(lightness)
    low_lightness = lightness <= 0.5
    saturation[chromatic & low_lightness] = delta[chromatic & low_lightness] / np.maximum(
        maxc[chromatic & low_lightness] + minc[chromatic & low_lightness],
        1e-12,
    )
    high_mask = chromatic & ~low_lightness
    saturation[high_mask] = delta[high_mask] / np.maximum(
        2.0 - maxc[high_mask] - minc[high_mask],
        1e-12,
    )
    effective_scale = np.full(lightness.shape, float(scale), dtype=np.float32)
    overfull = chromatic & (saturation * float(scale) > 1.0)
    effective_scale[overfull] = 1.0 / np.maximum(saturation[overfull], 1e-12)
    rgb[chromatic] = lightness[chromatic, None] + (
        rgb[chromatic] - lightness[chromatic, None]
    ) * effective_scale[chromatic, None]
    result[..., :3] = np.clip(rgb, 0.0, 1.0)
    return restore_dtype(result, dtype)


def _apply_gimp_hue_saturation_hsl(
    hsl: np.ndarray, config: tuple[np.ndarray, np.ndarray, np.ndarray], overlap_percent: float
) -> np.ndarray:
    hue_values, lightness_values, saturation_values = config
    result = hsl.copy()
    h = result[..., 0] * 6.0
    overlap = np.clip(float(overlap_percent), 0.0, 100.0) / 100.0 / 2.0
    hue = np.zeros(h.shape, dtype=np.int16)
    secondary_hue = np.zeros(h.shape, dtype=np.int16)
    use_secondary = np.zeros(h.shape, dtype=bool)
    primary_intensity = np.ones(h.shape, dtype=np.float32)
    secondary_intensity = np.zeros(h.shape, dtype=np.float32)
    assigned = np.zeros(h.shape, dtype=bool)
    for hue_counter in range(7):
        threshold = float(hue_counter) + 0.5
        mask = (~assigned) & (h < (threshold + overlap))
        if not np.any(mask):
            continue
        hue[mask] = hue_counter
        if overlap > 0.0:
            secondary_mask = mask & (h > (threshold - overlap))
            if np.any(secondary_mask):
                use_secondary[secondary_mask] = True
                secondary_hue[secondary_mask] = hue_counter + 1
                secondary_intensity[secondary_mask] = (
                    h[secondary_mask] - threshold + overlap
                ) / (2.0 * overlap)
                primary_intensity[secondary_mask] = 1.0 - secondary_intensity[secondary_mask]
        assigned[mask] = True
    hue = np.where(hue >= 6, 0, hue)
    secondary_hue = np.where(secondary_hue >= 6, 0, secondary_hue)
    primary_range = hue + 1
    secondary_range = secondary_hue + 1
    primary_h = _map_hue(result[..., 0], hue_values, primary_range)
    primary_s = _map_saturation(result[..., 1], saturation_values, primary_range)
    primary_l = _map_lightness(result[..., 2], lightness_values, primary_range)
    secondary_h = _map_hue_overlap(
        result[..., 0],
        hue_values,
        primary_range,
        secondary_range,
        primary_intensity,
        secondary_intensity,
    )
    secondary_s = (
        _map_saturation(result[..., 1], saturation_values, primary_range) * primary_intensity
        + _map_saturation(result[..., 1], saturation_values, secondary_range) * secondary_intensity
    )
    secondary_l = (
        _map_lightness(result[..., 2], lightness_values, primary_range) * primary_intensity
        + _map_lightness(result[..., 2], lightness_values, secondary_range) * secondary_intensity
    )
    achromatic = result[..., 1] <= 0.0
    result[..., 0] = np.where(use_secondary, secondary_h, primary_h)
    result[..., 1] = np.where(use_secondary, secondary_s, primary_s)
    result[..., 2] = np.where(use_secondary, secondary_l, primary_l)
    result[..., 2] = np.where(
        (~use_secondary) & achromatic,
        _map_lightness_achromatic(hsl[..., 2], lightness_values),
        result[..., 2],
    )
    return result


def _map_hue(value: np.ndarray, hue_values: np.ndarray, ranges: np.ndarray) -> np.ndarray:
    mapped = value + (hue_values[0] + hue_values[ranges]) / 2.0
    return np.mod(mapped, 1.0)


def _map_hue_overlap(
    value: np.ndarray,
    hue_values: np.ndarray,
    primary_range: np.ndarray,
    secondary_range: np.ndarray,
    primary_intensity: np.ndarray,
    secondary_intensity: np.ndarray,
) -> np.ndarray:
    mixed = hue_values[primary_range] * primary_intensity + hue_values[secondary_range] * secondary_intensity
    return np.mod(value + (hue_values[0] + mixed) / 2.0, 1.0)


def _map_saturation(value: np.ndarray, saturation_values: np.ndarray, ranges: np.ndarray) -> np.ndarray:
    adjustment = saturation_values[0] + saturation_values[ranges]
    return np.clip(value * (adjustment + 1.0), 0.0, 1.0)


def _map_lightness(value: np.ndarray, lightness_values: np.ndarray, ranges: np.ndarray) -> np.ndarray:
    adjustment = lightness_values[0] + lightness_values[ranges]
    return np.where(
        adjustment < 0.0,
        value * (adjustment + 1.0),
        value + adjustment * (1.0 - value),
    )


def _map_lightness_achromatic(value: np.ndarray, lightness_values: np.ndarray) -> np.ndarray:
    adjustment = lightness_values[0]
    return np.where(
        adjustment < 0.0,
        value * (adjustment + 1.0),
        value + adjustment * (1.0 - value),
    )


def _rgb_to_hsl(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    lightness = (maxc + minc) / 2.0
    delta = maxc - minc
    saturation = np.zeros_like(lightness)
    nonzero = delta > 1e-12
    saturation[nonzero] = np.where(
        lightness[nonzero] <= 0.5,
        delta[nonzero] / np.maximum(maxc[nonzero] + minc[nonzero], 1e-12),
        delta[nonzero] / np.maximum(2.0 - maxc[nonzero] - minc[nonzero], 1e-12),
    )
    hue = np.zeros_like(lightness)
    red_max = nonzero & (maxc == r)
    green_max = nonzero & (maxc == g)
    blue_max = nonzero & (maxc == b)
    hue[red_max] = (g[red_max] - b[red_max]) / delta[red_max]
    hue[green_max] = 2.0 + (b[green_max] - r[green_max]) / delta[green_max]
    hue[blue_max] = 4.0 + (r[blue_max] - g[blue_max]) / delta[blue_max]
    hue = np.mod(hue / 6.0, 1.0)
    return np.stack([hue, saturation, lightness], axis=-1).astype(np.float32)


def _hsl_to_rgb(hsl: np.ndarray) -> np.ndarray:
    h = np.mod(hsl[..., 0], 1.0)
    s = np.clip(hsl[..., 1], 0.0, 1.0)
    l = np.clip(hsl[..., 2], 0.0, 1.0)
    q = np.where(l < 0.5, l * (1.0 + s), l + s - l * s)
    p = 2.0 * l - q
    r = _hue_to_rgb(p, q, h + 1.0 / 3.0)
    g = _hue_to_rgb(p, q, h)
    b = _hue_to_rgb(p, q, h - 1.0 / 3.0)
    gray = s <= 1e-12
    r = np.where(gray, l, r)
    g = np.where(gray, l, g)
    b = np.where(gray, l, b)
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def _hue_to_rgb(p: np.ndarray, q: np.ndarray, t: np.ndarray) -> np.ndarray:
    t = np.mod(t, 1.0)
    return np.where(
        t < 1.0 / 6.0,
        p + (q - p) * 6.0 * t,
        np.where(
            t < 1.0 / 2.0,
            q,
            np.where(t < 2.0 / 3.0, p + (q - p) * (2.0 / 3.0 - t) * 6.0, p),
        ),
    )


def _coerce_selection_mask(selection_mask: object | None, shape: tuple[int, int]) -> np.ndarray | None:
    if selection_mask is None:
        return None
    mask = np.asarray(selection_mask, dtype=bool)
    if mask.shape != shape:
        return None
    return mask


def _coerce_sample_rect(value: object | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    return tuple(int(part) for part in value)


def _coerce_raw_metadata(value: object | None) -> dict[str, object] | None:
    if isinstance(value, dict):
        return dict(value)
    return None


def _central_ellipse_mask(shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    yy, xx = np.ogrid[:height, :width]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    rx = max(1.0, width * 0.38)
    ry = max(1.0, height * 0.38)
    return ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
