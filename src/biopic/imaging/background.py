"""Background synthesis helpers for selection-based editing."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy import ndimage

ProgressCallback = Callable[[str, float], None]


def mean_background_color(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return the mean color for pixels selected by mask."""
    pixels = np.asarray(image)[mask]
    if pixels.size == 0:
        return np.zeros(image.shape[2:] if image.ndim > 2 else (), dtype=np.asarray(image).dtype)
    color = pixels.reshape(-1, *np.asarray(image).shape[2:]).mean(axis=0)
    if np.issubdtype(np.asarray(image).dtype, np.integer):
        info = np.iinfo(np.asarray(image).dtype)
        color = np.clip(np.rint(color), info.min, info.max)
    return np.asarray(color, dtype=np.asarray(image).dtype)


def background_pixels_from_selection(
    image: np.ndarray,
    background_color: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int,
) -> np.ndarray:
    """Build a uniform background with the original border-aware transition."""
    result = np.empty_like(image)
    result[...] = np.asarray(background_color, dtype=image.dtype)
    outside = ~selection_mask
    if transition_px <= 0 or not np.any(outside):
        return result
    distance, nearest_indices = ndimage.distance_transform_edt(
        outside,
        return_indices=True,
    )
    band = outside & (distance <= float(transition_px))
    if not np.any(band):
        return result
    border_reference = _local_selection_border_reference(
        image,
        selection_mask,
        transition_px,
    )
    nearest_y = nearest_indices[0][band]
    nearest_x = nearest_indices[1][band]
    start_values = border_reference[nearest_y, nearest_x].astype(np.float32, copy=False)
    bg_values = np.asarray(background_color, dtype=np.float32)
    t = np.clip(distance[band] / float(max(1, transition_px)), 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)
    if image.ndim == 3:
        t = t[..., None]
    blended = start_values * (1.0 - t) + bg_values * t
    if np.issubdtype(image.dtype, np.integer):
        info = np.iinfo(image.dtype)
        blended = np.clip(np.rint(blended), info.min, info.max)
    result[band] = blended.astype(image.dtype, copy=False)
    return result


def global_textured_background_from_selection(
    image: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int = 0,
    progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Synthesize a uniform outside background from one low-contrast clone source."""
    _emit(progress, "Preparing background mask", 0.02)
    data = np.asarray(image)
    mask = np.asarray(selection_mask, dtype=bool)
    if data.ndim < 2 or mask.shape != data.shape[:2]:
        raise ValueError("selection_mask must match the image height and width")
    outside = ~mask
    if not np.any(outside):
        _emit(progress, "Background complete", 1.0)
        return data.copy()

    _emit(progress, "Finding ordinary background pixels", 0.10)
    luminance = _luminance(data)
    source_mask = _ordinary_background_source_mask(data, outside, luminance=luminance)
    if not np.any(source_mask):
        source_mask = outside
    if int(np.count_nonzero(source_mask)) < 9:
        _emit(progress, "Filling background color", 0.45)
        color = mean_background_color(data, outside)
        result = background_pixels_from_selection(data, color, mask, transition_px)
        _emit(progress, "Background complete", 1.0)
        return result

    _emit(progress, "Estimating background color", 0.22)
    color = mean_background_color(data, source_mask)
    _emit(progress, "Building base background", 0.34)
    result = background_pixels_from_selection(data, color, mask, transition_px)
    patch = _low_contrast_background_patch(
        data,
        source_mask,
        luminance=luminance,
        progress=progress,
        progress_start=0.42,
        progress_end=0.66,
    )
    if patch is None:
        _emit(progress, "Background complete", 1.0)
        return result
    _emit(progress, "Tiling sampled background texture", 0.78)
    fill = _continuous_clone_fill_from_patch(data.shape, patch, color)
    _emit(progress, "Blending background edge", 0.90)
    blended = _blend_clone_fill_into_background(result, fill, outside, transition_px, data.dtype)
    _emit(progress, "Background complete", 1.0)
    return blended


def healed_textured_background_from_selection(
    image: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int = 0,
    progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Synthesize outside background by healing sampled texture into local lighting."""
    _emit(progress, "Preparing background mask", 0.02)
    data = np.asarray(image)
    mask = np.asarray(selection_mask, dtype=bool)
    if data.ndim < 2 or mask.shape != data.shape[:2]:
        raise ValueError("selection_mask must match the image height and width")
    outside = ~mask
    if not np.any(outside):
        _emit(progress, "Background complete", 1.0)
        return data.copy()

    _emit(progress, "Finding ordinary background pixels", 0.10)
    luminance = _luminance(data)
    source_mask = _ordinary_background_source_mask(data, outside, luminance=luminance)
    if not np.any(source_mask):
        source_mask = outside
    _emit(progress, "Estimating background color", 0.20)
    color = mean_background_color(data, source_mask)
    _emit(progress, "Building base background", 0.30)
    result = background_pixels_from_selection(data, color, mask, transition_px)
    patch = _low_contrast_background_patch(
        data,
        source_mask,
        luminance=luminance,
        progress=progress,
        progress_start=0.38,
        progress_end=0.58,
    )
    if patch is None:
        _emit(progress, "Background complete", 1.0)
        return result
    smooth_field = _smooth_destination_background_field(
        data,
        source_mask,
        outside,
        progress=progress,
        progress_start=0.60,
        progress_end=0.78,
    )
    _emit(progress, "Healing texture into background field", 0.84)
    fill = _continuous_heal_fill_from_patch(data.shape, patch, smooth_field)
    _emit(progress, "Blending background edge", 0.92)
    blended = _blend_clone_fill_into_background(result, fill, outside, transition_px, data.dtype)
    _emit(progress, "Background complete", 1.0)
    return blended


def clone_stamped_background_from_selection(
    image: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int = 0,
) -> np.ndarray:
    """Compatibility wrapper for the global textured background synthesizer."""
    return global_textured_background_from_selection(image, selection_mask, transition_px)


def _emit(progress: ProgressCallback | None, message: str, fraction: float) -> None:
    if progress is not None:
        progress(message, fraction)


def fill_transparent_regions_with_background(
    image: np.ndarray,
    *,
    alpha_threshold: int = 250,
) -> np.ndarray:
    """Fill transparent RGBA regions by extrapolating nearby image background."""
    data = np.asarray(image)
    if data.ndim != 3 or data.shape[2] < 4:
        return data.copy()
    alpha = data[..., 3]
    threshold = float(alpha_threshold)
    if np.issubdtype(alpha.dtype, np.floating) and float(np.nanmax(alpha)) <= 1.0:
        threshold /= 255.0
    empty = alpha <= threshold
    if not np.any(empty):
        return data.copy()
    known = ~empty
    if not np.any(known):
        return data.copy()
    result = data.copy()
    colors = data[..., :3].astype(np.float32, copy=False)
    edge_fill = _smooth_edge_background_field(colors, known, empty)
    gradient_fill = _edge_gradient_extrapolation(colors, known, empty)
    distance_inside_empty = ndimage.distance_transform_edt(empty)
    scale = max(1.0, float(np.percentile(distance_inside_empty[empty], 90.0)))
    gradient_weight = np.clip(distance_inside_empty[empty] / scale, 0.0, 1.0)
    gradient_weight = gradient_weight * gradient_weight * (3.0 - 2.0 * gradient_weight)
    gradient_weight = 0.20 + gradient_weight[..., None] * 0.70
    filled = (
        edge_fill[empty] * (1.0 - gradient_weight)
        + gradient_fill[empty] * gradient_weight
    )
    if np.issubdtype(result.dtype, np.integer):
        info = np.iinfo(result.dtype)
        filled = np.clip(np.rint(filled), info.min, info.max)
        result[empty, :3] = filled.astype(result.dtype, copy=False)
        result[empty, 3] = info.max
    else:
        result[empty, :3] = filled.astype(result.dtype, copy=False)
        result[empty, 3] = 1.0
    return result


def _nearest_opaque_edge_fill(colors: np.ndarray, empty: np.ndarray) -> np.ndarray:
    _, nearest = ndimage.distance_transform_edt(empty, return_indices=True)
    return colors[nearest[0], nearest[1]]


def _smooth_edge_background_field(
    colors: np.ndarray,
    known: np.ndarray,
    empty: np.ndarray,
) -> np.ndarray:
    height, width = empty.shape
    edge_band_width = max(4, min(32, int(round(min(height, width) * 0.08))))
    edge_samples = known & (ndimage.distance_transform_edt(known) <= float(edge_band_width))
    if int(np.count_nonzero(edge_samples)) < 12:
        return _nearest_opaque_edge_fill(colors, empty)

    sigma = max(3.0, min(height, width) * 0.10)
    weights = edge_samples.astype(np.float32)
    smooth_weights = ndimage.gaussian_filter(weights, sigma=sigma, mode="nearest")
    channels = []
    for channel in range(colors.shape[2]):
        smooth = ndimage.gaussian_filter(
            colors[..., channel] * weights,
            sigma=sigma,
            mode="nearest",
        )
        channels.append(smooth / np.maximum(smooth_weights, 1e-6))
    field = np.stack(channels, axis=-1)
    fallback = _edge_gradient_extrapolation(colors, known, empty)
    weak = smooth_weights <= 1e-5
    if np.any(weak):
        field[weak] = fallback[weak]
    return field.astype(np.float32, copy=False)


def _edge_gradient_extrapolation(
    colors: np.ndarray,
    known: np.ndarray,
    empty: np.ndarray,
) -> np.ndarray:
    height, width = empty.shape
    edge_band_width = max(3, min(24, int(round(min(height, width) * 0.06))))
    edge_samples = known & (ndimage.distance_transform_edt(known) <= float(edge_band_width))
    if int(np.count_nonzero(edge_samples)) < 12:
        return _nearest_opaque_edge_fill(colors, empty)

    sample_y, sample_x = np.nonzero(edge_samples)
    sample_count = sample_y.size
    max_samples = 20_000
    if sample_count > max_samples:
        step = int(np.ceil(sample_count / max_samples))
        sample_y = sample_y[::step]
        sample_x = sample_x[::step]

    x_norm = _normalized_coordinate(sample_x.astype(np.float32), width)
    y_norm = _normalized_coordinate(sample_y.astype(np.float32), height)
    design = np.column_stack(
        [
            np.ones_like(x_norm),
            x_norm,
            y_norm,
            x_norm * y_norm,
            x_norm * x_norm,
            y_norm * y_norm,
        ]
    )
    target = colors[sample_y, sample_x]
    try:
        coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    except np.linalg.LinAlgError:
        return _nearest_opaque_edge_fill(colors, empty)

    yy, xx = np.indices(empty.shape, dtype=np.float32)
    xx = _normalized_coordinate(xx, width)
    yy = _normalized_coordinate(yy, height)
    full_design = np.stack(
        [
            np.ones_like(xx),
            xx,
            yy,
            xx * yy,
            xx * xx,
            yy * yy,
        ],
        axis=-1,
    )
    gradient = np.einsum("...k,kc->...c", full_design, coefficients)
    sample_values = target.reshape(-1, target.shape[-1])
    low = np.percentile(sample_values, 1.0, axis=0)
    high = np.percentile(sample_values, 99.0, axis=0)
    margin = np.maximum(high - low, 1.0) * 0.75
    low = low - margin
    high = high + margin
    return np.clip(gradient, low, high).astype(np.float32, copy=False)


def _normalized_coordinate(values: np.ndarray, size: int) -> np.ndarray:
    if size <= 1:
        return np.zeros_like(values, dtype=np.float32)
    return (values / float(size - 1)) * 2.0 - 1.0


def _ordinary_background_source_mask(
    image: np.ndarray,
    outside: np.ndarray,
    *,
    luminance: np.ndarray | None = None,
) -> np.ndarray:
    safe_distance = max(2, min(24, max(outside.shape) // 48))
    source = ndimage.binary_erosion(
        outside,
        structure=np.ones((3, 3), dtype=bool),
        iterations=safe_distance,
        border_value=0,
    )
    if int(np.count_nonzero(source)) < 9:
        source = outside.copy()

    if luminance is None:
        luminance = _luminance(image)
    values = luminance[source]
    if values.size < 9:
        return source
    low, high = np.percentile(values, [5.0, 95.0])
    ordinary = source & (luminance >= low) & (luminance <= high)
    return ordinary if int(np.count_nonzero(ordinary)) >= 9 else source


def _luminance(image: np.ndarray) -> np.ndarray:
    data = np.asarray(image, dtype=np.float32)
    if data.ndim == 2:
        return data
    if data.shape[2] >= 3:
        return data[..., 0] * 0.2126 + data[..., 1] * 0.7152 + data[..., 2] * 0.0722
    return data[..., 0]


def _low_contrast_background_patch(
    image: np.ndarray,
    source_mask: np.ndarray,
    *,
    luminance: np.ndarray | None = None,
    progress: ProgressCallback | None = None,
    progress_start: float = 0.0,
    progress_end: float = 1.0,
) -> np.ndarray | None:
    height, width = source_mask.shape
    if luminance is None:
        luminance = _luminance(image)
    mask_float = source_mask.astype(np.float32, copy=False)
    luminance_sq = luminance * luminance
    patch_sizes = _candidate_patch_sizes((height, width))
    total = max(1, len(patch_sizes))
    for index, patch_size in enumerate(patch_sizes):
        fraction = progress_start + (progress_end - progress_start) * (index / total)
        _emit(progress, f"Searching low-contrast patch {index + 1}/{total}", fraction)
        valid = (
            ndimage.uniform_filter(
                mask_float,
                size=patch_size,
                mode="constant",
                cval=0.0,
            )
            >= 0.55
        )
        if not np.any(valid):
            continue
        mean = ndimage.uniform_filter(luminance, size=patch_size, mode="reflect")
        mean_sq = ndimage.uniform_filter(luminance_sq, size=patch_size, mode="reflect")
        variance = np.maximum(mean_sq - mean * mean, 0.0)
        texture_floor = _background_texture_floor(image.dtype)
        too_flat_penalty = np.maximum(texture_floor - variance, 0.0) * 4.0
        scores = np.where(valid, variance + too_flat_penalty, np.inf)
        y, x = np.unravel_index(int(np.argmin(scores)), scores.shape)
        if not np.isfinite(scores[y, x]):
            continue
        half = patch_size // 2
        y0 = max(0, min(height - patch_size, int(y) - half))
        x0 = max(0, min(width - patch_size, int(x) - half))
        patch = image[y0 : y0 + patch_size, x0 : x0 + patch_size]
        if patch.shape[:2] == (patch_size, patch_size):
            _emit(progress, "Low-contrast patch selected", progress_end)
            return _patch_with_invalid_pixels_repaired(patch, source_mask[y0 : y0 + patch_size, x0 : x0 + patch_size])
    _emit(progress, "No textured patch found", progress_end)
    return None


def _background_texture_floor(dtype: np.dtype) -> float:
    if np.issubdtype(np.dtype(dtype), np.integer):
        return 0.2
    return 1e-5


def _patch_with_invalid_pixels_repaired(patch: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    if np.all(valid_mask):
        return np.asarray(patch)
    repaired = patch.astype(np.float32, copy=True)
    valid_values = repaired[valid_mask]
    if valid_values.size == 0:
        return np.asarray(patch)
    replacement = valid_values.reshape(-1, *patch.shape[2:]).mean(axis=0)
    repaired[~valid_mask] = replacement
    return _restore_background_dtype(repaired, patch.dtype)


def _candidate_patch_sizes(shape: tuple[int, int]) -> list[int]:
    min_dim = max(1, min(shape))
    base = max(9, min(257, min_dim // 5))
    if base % 2 == 0:
        base += 1
    sizes: list[int] = []
    current = base
    while current >= 9:
        sizes.append(current)
        current = current // 2
        if current % 2 == 0:
            current -= 1
    sizes.append(5)
    return sorted(set(sizes), reverse=True)


def _continuous_clone_fill_from_patch(
    shape: tuple[int, ...],
    patch: np.ndarray,
    background_color: np.ndarray,
) -> np.ndarray:
    height, width = shape[:2]
    patch_float = patch.astype(np.float32, copy=False)
    patch_mean = patch_float.reshape(-1, *patch.shape[2:]).mean(axis=0)
    adjusted_patch = patch_float + (np.asarray(background_color, dtype=np.float32) - patch_mean)
    patch_y = _reflected_tile_indices_1d(height, patch.shape[0])
    patch_x = _reflected_tile_indices_1d(width, patch.shape[1])
    return adjusted_patch[patch_y[:, None], patch_x[None, :]]


def _continuous_heal_fill_from_patch(
    shape: tuple[int, ...],
    patch: np.ndarray,
    smooth_field: np.ndarray,
) -> np.ndarray:
    height, width = shape[:2]
    patch_float = patch.astype(np.float32, copy=False)
    sigma_spec: float | tuple[float, float, float] = max(1.0, min(patch.shape[:2]) / 8.0)
    if patch.ndim == 3:
        sigma_spec = (float(sigma_spec), float(sigma_spec), 0.0)
    smooth_patch = ndimage.gaussian_filter(patch_float, sigma=sigma_spec, mode="reflect")
    residual = patch_float - smooth_patch
    patch_y = _reflected_tile_indices_1d(height, patch.shape[0])
    patch_x = _reflected_tile_indices_1d(width, patch.shape[1])
    return smooth_field.astype(np.float32, copy=False) + residual[patch_y[:, None], patch_x[None, :]]


def _smooth_destination_background_field(
    image: np.ndarray,
    source_mask: np.ndarray,
    outside: np.ndarray,
    *,
    progress: ProgressCallback | None = None,
    progress_start: float = 0.0,
    progress_end: float = 1.0,
) -> np.ndarray:
    height, width = source_mask.shape
    if height * width > 700_000:
        return _smooth_destination_background_field_downsampled(
            image,
            source_mask,
            outside,
            progress=progress,
            progress_start=progress_start,
            progress_end=progress_end,
        )
    _emit(progress, "Smoothing destination background field", progress_start)
    data = image.astype(np.float32, copy=False)
    weights = source_mask.astype(np.float32)
    if not np.any(weights):
        weights = outside.astype(np.float32)
    sigma = max(4.0, min(source_mask.shape) / 8.0)
    smooth_weights = ndimage.gaussian_filter(weights, sigma=sigma, mode="nearest")
    if image.ndim == 3:
        channels = []
        for channel in range(image.shape[2]):
            channel_fraction = progress_start + (progress_end - progress_start) * (
                (channel + 1) / max(1, image.shape[2] + 1)
            )
            _emit(
                progress,
                f"Smoothing background channel {channel + 1}/{image.shape[2]}",
                channel_fraction,
            )
            weighted = ndimage.gaussian_filter(
                data[..., channel] * weights,
                sigma=sigma,
                mode="nearest",
            )
            channels.append(weighted / np.maximum(smooth_weights, 1e-6))
        field = np.stack(channels, axis=-1)
    else:
        weighted = ndimage.gaussian_filter(data * weights, sigma=sigma, mode="nearest")
        field = weighted / np.maximum(smooth_weights, 1e-6)
    fallback = mean_background_color(image, source_mask if np.any(source_mask) else outside)
    invalid = smooth_weights < 1e-4
    if np.any(invalid):
        field = field.copy()
        field[invalid] = fallback
    _emit(progress, "Destination background field ready", progress_end)
    return field.astype(np.float32, copy=False)


def _smooth_destination_background_field_downsampled(
    image: np.ndarray,
    source_mask: np.ndarray,
    outside: np.ndarray,
    *,
    progress: ProgressCallback | None = None,
    progress_start: float = 0.0,
    progress_end: float = 1.0,
) -> np.ndarray:
    _emit(progress, "Downsampling background field", progress_start)
    height, width = source_mask.shape
    scale = max(2, int(np.ceil(max(height, width) / 900.0)))
    trim_height = height - (height % scale)
    trim_width = width - (width % scale)
    if trim_height < scale or trim_width < scale:
        return _smooth_destination_background_field_full(
            image,
            source_mask,
            outside,
            progress=progress,
            progress_start=progress_start,
            progress_end=progress_end,
        )
    cropped = image[:trim_height, :trim_width]
    cropped_source = source_mask[:trim_height, :trim_width]
    cropped_outside = outside[:trim_height, :trim_width]
    small_shape = (trim_height // scale, scale, trim_width // scale, scale)
    if image.ndim == 3:
        small_image = cropped.reshape(*small_shape, image.shape[2]).mean(axis=(1, 3))
    else:
        small_image = cropped.reshape(*small_shape).mean(axis=(1, 3))
    small_source = cropped_source.reshape(*small_shape).mean(axis=(1, 3)) >= 0.25
    small_outside = cropped_outside.reshape(*small_shape).mean(axis=(1, 3)) >= 0.25
    small_field = _smooth_destination_background_field_full(
        small_image,
        small_source,
        small_outside,
        progress=progress,
        progress_start=progress_start + (progress_end - progress_start) * 0.20,
        progress_end=progress_start + (progress_end - progress_start) * 0.72,
    )
    _emit(progress, "Upsampling background field", progress_start + (progress_end - progress_start) * 0.82)
    zoom_spec: float | tuple[float, ...] = (scale, scale, 1.0) if image.ndim == 3 else (scale, scale)
    field = ndimage.zoom(small_field, zoom=zoom_spec, order=1, mode="nearest")
    if field.shape[:2] != (height, width):
        pad_width: list[tuple[int, int]] = [
            (0, max(0, height - field.shape[0])),
            (0, max(0, width - field.shape[1])),
        ]
        if image.ndim == 3:
            pad_width.append((0, 0))
        field = np.pad(field, pad_width, mode="edge")
        field = field[:height, :width]
    _emit(progress, "Destination background field ready", progress_end)
    return field.astype(np.float32, copy=False)


def _smooth_destination_background_field_full(
    image: np.ndarray,
    source_mask: np.ndarray,
    outside: np.ndarray,
    *,
    progress: ProgressCallback | None = None,
    progress_start: float = 0.0,
    progress_end: float = 1.0,
) -> np.ndarray:
    _emit(progress, "Smoothing destination background field", progress_start)
    data = image.astype(np.float32, copy=False)
    weights = source_mask.astype(np.float32)
    if not np.any(weights):
        weights = outside.astype(np.float32)
    sigma = max(4.0, min(source_mask.shape) / 8.0)
    smooth_weights = ndimage.gaussian_filter(weights, sigma=sigma, mode="nearest")
    if image.ndim == 3:
        channels = []
        for channel in range(image.shape[2]):
            channel_fraction = progress_start + (progress_end - progress_start) * (
                (channel + 1) / max(1, image.shape[2] + 1)
            )
            _emit(
                progress,
                f"Smoothing background channel {channel + 1}/{image.shape[2]}",
                channel_fraction,
            )
            weighted = ndimage.gaussian_filter(
                data[..., channel] * weights,
                sigma=sigma,
                mode="nearest",
            )
            channels.append(weighted / np.maximum(smooth_weights, 1e-6))
        field = np.stack(channels, axis=-1)
    else:
        weighted = ndimage.gaussian_filter(data * weights, sigma=sigma, mode="nearest")
        field = weighted / np.maximum(smooth_weights, 1e-6)
    fallback = mean_background_color(image, source_mask if np.any(source_mask) else outside)
    invalid = smooth_weights < 1e-4
    if np.any(invalid):
        field = field.copy()
        field[invalid] = fallback
    _emit(progress, "Destination background field ready", progress_end)
    return field.astype(np.float32, copy=False)


def _reflected_tile_indices(indices: np.ndarray, size: int) -> np.ndarray:
    if size <= 1:
        return np.zeros(indices.shape, dtype=np.intp)
    period = size * 2
    tiled = indices % period
    return np.where(tiled < size, tiled, period - 1 - tiled).astype(np.intp, copy=False)


def _reflected_tile_indices_1d(length: int, size: int) -> np.ndarray:
    if size <= 1:
        return np.zeros(length, dtype=np.intp)
    period = size * 2
    tiled = np.arange(length, dtype=np.intp) % period
    return np.where(tiled < size, tiled, period - 1 - tiled).astype(np.intp, copy=False)


def _blend_clone_fill_into_background(
    background: np.ndarray,
    clone_fill: np.ndarray,
    outside: np.ndarray,
    transition_px: int,
    dtype: np.dtype,
) -> np.ndarray:
    result = background.astype(np.float32, copy=False).copy()
    if transition_px <= 0:
        result[outside] = clone_fill[outside]
        return _restore_background_dtype(result, dtype)
    distance = ndimage.distance_transform_edt(outside)
    gain = np.clip(distance / float(max(1, transition_px)), 0.0, 1.0)
    gain = gain * gain * (3.0 - 2.0 * gain)
    if result.ndim == 3:
        gain = gain[..., None]
    result = result * (1.0 - gain) + clone_fill * gain
    return _restore_background_dtype(result, dtype)


def _restore_background_dtype(image: np.ndarray, dtype: np.dtype) -> np.ndarray:
    target = np.dtype(dtype)
    if np.issubdtype(target, np.integer):
        info = np.iinfo(target)
        return np.clip(np.rint(image), info.min, info.max).astype(target)
    return image.astype(target, copy=False)


def _stable_stamp_seed(image: np.ndarray, mask: np.ndarray) -> int:
    height, width = mask.shape
    dtype_hash = sum(ord(char) for char in str(image.dtype))
    return int((height * 73856093) ^ (width * 19349663) ^ (image.ndim * 83492791) ^ dtype_hash)


def _local_selection_border_reference(
    image: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int,
) -> np.ndarray:
    sample_width = max(1, min(8, int(round(max(1, transition_px) / 3.0))))
    inside_distance = ndimage.distance_transform_edt(selection_mask)
    inner_border = selection_mask & (inside_distance <= float(sample_width))
    if not np.any(inner_border):
        return image
    sigma = max(1.0, sample_width / 2.0)
    image_float = image.astype(np.float32, copy=False)
    weights = inner_border.astype(np.float32)
    if image.ndim == 3:
        smooth_weights = ndimage.gaussian_filter(weights, sigma=sigma, mode="nearest")
        channels = []
        for channel in range(image.shape[2]):
            weighted = ndimage.gaussian_filter(
                image_float[..., channel] * weights,
                sigma=sigma,
                mode="nearest",
            )
            channels.append(weighted / np.maximum(smooth_weights, 1e-6))
        reference = np.stack(channels, axis=-1)
    else:
        smooth_weights = ndimage.gaussian_filter(weights, sigma=sigma, mode="nearest")
        weighted = ndimage.gaussian_filter(image_float * weights, sigma=sigma, mode="nearest")
        reference = weighted / np.maximum(smooth_weights, 1e-6)
    return reference.astype(np.float32, copy=False)
