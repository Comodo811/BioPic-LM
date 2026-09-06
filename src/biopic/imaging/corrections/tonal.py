"""Tonal correction operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from scipy.interpolate import PchipInterpolator

from biopic.imaging.dtype import restore_dtype, to_float
from biopic.native.white_balance_backend import apply_rgb_gains as native_apply_rgb_gains


@dataclass(frozen=True, slots=True)
class WhiteBalanceEstimate:
    """Robust neutral-sample estimate and diagnostics."""

    red: float
    green: float
    blue: float
    valid_fraction: float
    clipped_fraction: float
    near_black_fraction: float
    saturated_fraction: float
    local_variance: float
    sample_count: int
    warning: str | None = None
    temperature: float | None = None
    tint: float | None = None
    correlation: float | None = None
    histogram_bins: int | None = None


WHITE_BALANCE_PRESETS: dict[str, tuple[float, float]] = {
    "daylight": (5200.0, 1.0),
    "cloudy": (6000.0, 1.0),
    "shade": (7000.0, 1.0),
    "tungsten": (2850.0, 1.0),
    "fluorescent": (4200.0, 1.15),
    "flash": (5500.0, 1.0),
}


def levels(
    image: np.ndarray,
    *,
    black_point: float = 0.0,
    white_point: float = 1.0,
    midtone: float = 1.0,
    output_black: float = 0.0,
    output_white: float = 1.0,
    channel: str = "rgb",
) -> np.ndarray:
    """Apply GIMP-style levels correction in normalized intensity space.

    Midtone uses ``normalized ** (1 / midtone)``. Output points remap the
    corrected value into ``[output_black, output_white]``.
    """
    if not 0.0 <= black_point < white_point <= 1.0:
        raise ValueError("black_point must be less than white_point within [0, 1]")
    if midtone <= 0:
        raise ValueError("midtone must be greater than zero")
    if not 0.0 <= output_black <= output_white <= 1.0:
        raise ValueError("output points must lie within [0, 1]")
    data, dtype = to_float(image)
    corrected = data.copy()
    target = _channel_view(corrected, channel)
    normalized = np.clip((target - black_point) / (white_point - black_point), 0.0, 1.0)
    target[...] = output_black + (output_white - output_black) * (normalized ** (1.0 / midtone))
    return restore_dtype(corrected, dtype)


def gamma_correct(image: np.ndarray, gamma: float) -> np.ndarray:
    """Apply `out = max * (in / max) ** gamma` in normalized intensity space."""
    if gamma <= 0:
        raise ValueError("gamma must be greater than zero")
    data, dtype = to_float(image)
    adjusted = data.copy()
    if adjusted.ndim == 3 and adjusted.shape[-1] >= 4:
        adjusted[..., :3] = np.clip(adjusted[..., :3], 0.0, 1.0) ** gamma
    else:
        adjusted = np.clip(adjusted, 0.0, 1.0) ** gamma
    return restore_dtype(adjusted, dtype)


def curve_adjust(
    image: np.ndarray,
    points: list[tuple[float, float]],
    *,
    channel: str = "rgb",
    curve_type: str = "smooth",
) -> np.ndarray:
    """Apply a GIMP-style gradation curve with normalized control points."""
    if len(points) < 2:
        raise ValueError("at least two curve points are required")
    sorted_points = sorted(points)
    xs = np.array([point[0] for point in sorted_points], dtype=np.float32)
    ys = np.array([point[1] for point in sorted_points], dtype=np.float32)
    if np.any(np.diff(xs) <= 0):
        raise ValueError("curve x values must be strictly increasing")
    if xs[0] < 0 or xs[-1] > 1 or np.any((ys < 0) | (ys > 1)):
        raise ValueError("curve points must lie within [0, 1]")
    data, dtype = to_float(image)
    adjusted = data.copy()
    target = _channel_view(adjusted, channel)
    clipped = np.clip(target, 0.0, 1.0)
    if curve_type.lower() in {"free", "linear", "freehand", "free_hand"}:
        mapped = np.interp(clipped, xs, ys)
    else:
        interpolator = PchipInterpolator(xs, ys, extrapolate=True)
        mapped = interpolator(clipped)
    target[...] = np.clip(mapped, 0.0, 1.0)
    return restore_dtype(adjusted, dtype)


def auto_levels(image: np.ndarray, percentile: float = 0.5) -> np.ndarray:
    """Apply auto-levels using symmetric percentile clipping."""
    if not 0 <= percentile < 50:
        raise ValueError("percentile must be in [0, 50)")
    data, _dtype = to_float(image)
    black = float(np.percentile(data, percentile))
    white = float(np.percentile(data, 100.0 - percentile))
    if white <= black:
        return image.copy()
    return levels(image, black_point=black, white_point=white)


def white_balance_multipliers(
    image: np.ndarray,
    *,
    red: float = 1.0,
    green: float = 1.0,
    blue: float = 1.0,
    normalize: bool = True,
) -> np.ndarray:
    """Apply RawTherapee-style reproducible RGB white-balance multipliers."""
    multipliers = normalized_white_balance_gains(red, green, blue, normalize=normalize)
    native = native_apply_rgb_gains(image, *multipliers)
    if native is not None:
        return native
    return _apply_white_balance_float(image, multipliers)


def white_balance_rendered(
    image: np.ndarray,
    *,
    method: str = "manual",
    red: float = 1.0,
    green: float = 1.0,
    blue: float = 1.0,
    temperature: float = 6500.0,
    tint: float = 1.0,
    preset: str = "daylight",
    blue_red_equalizer: float = 1.0,
    awb_temperature_bias: float = 0.0,
    histogram_low_clip: float = 0.2,
    histogram_high_clip: float = 0.2,
    histogram_bins: int = 32,
    raw_metadata: Mapping[str, object] | None = None,
    camera_matrix_strength: float = 0.0,
    normalize: bool = True,
    sample_rect: tuple[int, int, int, int] | None = None,
    sample_size: int = 16,
) -> np.ndarray:
    """Apply rendered-image white balance with RawTherapee-inspired controls.

    ``manual`` applies RGB channel multipliers. ``temperature`` and ``preset``
    derive gains from D65-referenced black-body approximations. ``auto`` uses
    robust neutral statistics. ``auto_temperature`` approximates RawTherapee's
    histogram-guided temperature-correlation white balance for rendered RGB.
    """
    method = method.lower()
    if method in {"camera", "as_shot"}:
        gains = _raw_white_balance_gains(raw_metadata, "camera_whitebalance")
        if gains is None:
            gains = (red, green, blue)
        if _raw_camera_wb_already_applied(raw_metadata):
            gains = (1.0, 1.0, 1.0)
    elif method in {"daylight", "raw_daylight"}:
        daylight = _raw_white_balance_gains(raw_metadata, "daylight_whitebalance")
        camera = _raw_white_balance_gains(raw_metadata, "camera_whitebalance")
        if daylight is None:
            gains = white_balance_preset_gains("daylight", tint=tint)
        elif _raw_camera_wb_already_applied(raw_metadata) and camera is not None:
            gains = _relative_white_balance_gains(daylight, camera)
        else:
            gains = daylight
    elif method == "preset":
        gains = white_balance_preset_gains(preset, tint=tint)
    elif method == "temperature":
        gains = white_balance_gains_from_temperature(temperature, tint=tint)
    elif method in {"auto_temperature", "temperature_correlation", "itcwb"}:
        estimate = estimate_white_balance_temperature_correlation(
            image,
            temperature_bias=awb_temperature_bias,
            histogram_low_clip=histogram_low_clip,
            histogram_high_clip=histogram_high_clip,
            histogram_bins=histogram_bins,
        )
        gains = (estimate.red, estimate.green, estimate.blue)
    elif method in {"auto", "spot"}:
        estimate = estimate_white_balance_from_region(
            image,
            sample_rect,
            sample_size=sample_size,
            reject_unsuitable=True,
        )
        gains = (estimate.red, estimate.green, estimate.blue)
    elif method == "manual":
        gains = (red, green, blue)
    else:
        raise ValueError(f"Unsupported white-balance method: {method}")
    gains = _apply_blue_red_equalizer(gains, blue_red_equalizer)
    balanced = white_balance_multipliers(
        image, red=gains[0], green=gains[1], blue=gains[2], normalize=normalize
    )
    return apply_raw_camera_profile_matrix(
        balanced,
        raw_metadata=raw_metadata,
        strength=camera_matrix_strength,
    )


def normalized_white_balance_gains(
    red: float, green: float, blue: float, *, normalize: bool = True
) -> tuple[float, float, float]:
    """Normalize gains around green, matching RawTherapee's stable green anchor."""
    if min(red, green, blue) <= 0:
        raise ValueError("white-balance multipliers must be greater than zero")
    multipliers = np.array([red, green, blue], dtype=np.float32)
    if normalize:
        multipliers = multipliers / max(float(multipliers[1]), 1e-6)
    return (float(multipliers[0]), float(multipliers[1]), float(multipliers[2]))


def white_balance_gains_from_temperature(
    temperature: float, *, tint: float = 1.0
) -> tuple[float, float, float]:
    """Derive D65-referenced rendered-image gains from temperature and tint.

    The approximation follows the common editor convention used for rendered
    previews: estimate black-body RGB for the requested temperature and apply
    gains that make it neutral relative to D65. It is not a RAW camera-profile
    replacement.
    """
    temp = max(1500.0, min(15000.0, float(temperature)))
    tint = max(0.25, min(4.0, float(tint)))
    reference = _blackbody_rgb_approx(6500.0)
    current = np.maximum(_blackbody_rgb_approx(temp), 1e-6)
    gains = reference / current
    gains[1] *= tint
    return normalized_white_balance_gains(
        float(gains[0]), float(gains[1]), float(gains[2]), normalize=True
    )


def white_balance_preset_gains(preset: str, *, tint: float = 1.0) -> tuple[float, float, float]:
    """Return rendered-image gains for a RawTherapee-style light-source preset."""
    key = preset.lower().strip().replace(" ", "_")
    temperature, preset_tint = WHITE_BALANCE_PRESETS.get(key, WHITE_BALANCE_PRESETS["daylight"])
    return white_balance_gains_from_temperature(temperature, tint=preset_tint * tint)


def apply_raw_camera_profile_matrix(
    image: np.ndarray,
    *,
    raw_metadata: Mapping[str, object] | None = None,
    strength: float = 0.0,
) -> np.ndarray:
    """Apply an optional RAW camera RGB-to-sRGB matrix adaptation.

    This is intentionally opt-in because most imported RAW pixels have already
    been color-converted by the decoder, and rendered formats do not have a
    camera-native color space.
    """
    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0.0:
        return np.asarray(image).copy()
    matrix = _raw_rgb_to_srgb_matrix(raw_metadata)
    if matrix is None:
        return np.asarray(image).copy()
    data, dtype = to_float(image)
    if data.ndim < 3 or data.shape[-1] < 3:
        return restore_dtype(data, dtype)
    rgb = data[..., :3]
    converted = np.tensordot(rgb, matrix.T, axes=1)
    adjusted = data.copy()
    adjusted[..., :3] = rgb * (1.0 - strength) + converted * strength
    return restore_dtype(np.clip(adjusted, 0.0, 1.0), dtype)


def estimate_white_balance_temperature_correlation(
    image: np.ndarray,
    *,
    temperature_bias: float = 0.0,
    histogram_low_clip: float = 0.2,
    histogram_high_clip: float = 0.2,
    histogram_bins: int = 32,
) -> WhiteBalanceEstimate:
    """Estimate WB using a rendered-RGB approximation of RawTherapee ITCWB.

    RawTherapee's real ITCWB operates in the raw pipeline with camera metadata
    and spectral reference data. For rendered RGB, the closest useful analogue
    is to denoise lightly, build a chromaticity histogram, keep dominant
    in-gamut color populations, then search temperature/tint candidates for the
    correction that makes those populations most chromatically balanced.
    """
    data, _dtype = to_float(image)
    if data.ndim < 3 or data.shape[-1] < 3:
        return WhiteBalanceEstimate(1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, data.size)
    rgb = np.asarray(data[..., :3], dtype=np.float32)
    denoised = ndimage.median_filter(rgb, size=(3, 3, 1), mode="nearest")
    pixels = denoised.reshape(-1, 3)
    luminance = pixels @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    low_clip = max(0.0, min(25.0, float(histogram_low_clip)))
    high_clip = max(0.0, min(25.0, float(histogram_high_clip)))
    low = float(np.percentile(luminance, low_clip))
    high = float(np.percentile(luminance, 100.0 - high_clip))
    valid = (
        (luminance > max(low, 0.01))
        & (luminance < min(high, 0.99))
        & ~np.any((pixels <= 0.001) | (pixels >= 0.999), axis=1)
    )
    usable = pixels[valid]
    if usable.shape[0] < 16:
        return estimate_white_balance_from_region(image, None, reject_unsuitable=True)
    if usable.shape[0] > 250_000:
        step = int(np.ceil(usable.shape[0] / 250_000))
        usable = usable[::step]

    sums = np.maximum(np.sum(usable, axis=1), 1e-6)
    red_chroma = usable[:, 0] / sums
    blue_chroma = usable[:, 2] / sums
    bins = max(12, min(96, int(histogram_bins)))
    hist, red_edges, blue_edges = np.histogram2d(
        red_chroma,
        blue_chroma,
        bins=bins,
        range=((0.0, 1.0), (0.0, 1.0)),
    )
    red_bin = np.clip(np.searchsorted(red_edges, red_chroma, side="right") - 1, 0, bins - 1)
    blue_bin = np.clip(np.searchsorted(blue_edges, blue_chroma, side="right") - 1, 0, bins - 1)
    populated = hist[red_bin, blue_bin]
    cutoff = float(np.percentile(hist[hist > 0], 70.0)) if np.any(hist > 0) else 1.0
    selected = usable[populated >= max(1.0, cutoff)]
    if selected.shape[0] < 16:
        selected = usable

    best_score = np.inf
    best_temperature = 6500.0
    best_tint = 1.0
    best_gains = (1.0, 1.0, 1.0)
    for candidate_temp in np.linspace(2000.0, 15000.0, 132):
        biased_temp = float(np.clip(candidate_temp + float(temperature_bias), 1500.0, 15000.0))
        for candidate_tint in np.linspace(0.77, 1.30, 28):
            gains = white_balance_gains_from_temperature(biased_temp, tint=float(candidate_tint))
            corrected = selected * np.array(gains, dtype=np.float32)
            mean = np.maximum(corrected.mean(axis=1), 1e-6)
            chroma_error = np.mean(np.std(corrected, axis=1) / mean)
            clipping_penalty = float(np.mean(np.max(corrected, axis=1) > 1.0)) * 0.25
            score = float(chroma_error + clipping_penalty)
            if score < best_score:
                best_score = score
                best_temperature = biased_temp
                best_tint = float(candidate_tint)
                best_gains = gains

    valid_fraction = float(selected.shape[0] / max(1, pixels.shape[0]))
    clipped_fraction = float(np.count_nonzero(np.any(pixels >= 0.999, axis=1)) / pixels.shape[0])
    near_black_fraction = float(np.count_nonzero(luminance < 0.02) / pixels.shape[0])
    saturated_fraction = float(np.count_nonzero(np.max(pixels, axis=1) > 0.98) / pixels.shape[0])
    warning = _white_balance_warning(
        valid_fraction=valid_fraction,
        clipped_fraction=clipped_fraction,
        near_black_fraction=near_black_fraction,
        saturated_fraction=saturated_fraction,
        local_variance=float(np.mean(np.var(selected, axis=0))),
    )
    return WhiteBalanceEstimate(
        red=best_gains[0],
        green=best_gains[1],
        blue=best_gains[2],
        valid_fraction=valid_fraction,
        clipped_fraction=clipped_fraction,
        near_black_fraction=near_black_fraction,
        saturated_fraction=saturated_fraction,
        local_variance=float(np.mean(np.var(selected, axis=0))),
        sample_count=int(selected.shape[0]),
        warning=warning,
        temperature=best_temperature,
        tint=best_tint,
        correlation=best_score,
        histogram_bins=bins,
    )


def _apply_white_balance_float(
    image: np.ndarray, multipliers: tuple[float, float, float]
) -> np.ndarray:
    data, dtype = to_float(image)
    if data.ndim == 3 and data.shape[-1] >= 3:
        adjusted = data.copy()
        adjusted[..., :3] = adjusted[..., :3] * np.array(multipliers, dtype=np.float32)
    else:
        adjusted = data * float(np.mean(multipliers))
    return restore_dtype(np.clip(adjusted, 0.0, 1.0), dtype)


def _apply_blue_red_equalizer(
    gains: tuple[float, float, float], equalizer: float
) -> tuple[float, float, float]:
    equalizer = max(0.25, min(4.0, float(equalizer)))
    red, green, blue = gains
    ratio = equalizer ** 0.5
    return normalized_white_balance_gains(red * ratio, green, blue / ratio, normalize=True)


def _raw_white_balance_gains(
    raw_metadata: Mapping[str, object] | None, key: str
) -> tuple[float, float, float] | None:
    if raw_metadata is None:
        return None
    value = raw_metadata.get(key)
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        gains = [float(value[index]) for index in range(3)]
    except (TypeError, ValueError):
        return None
    if min(gains) <= 0.0:
        return None
    return normalized_white_balance_gains(gains[0], gains[1], gains[2], normalize=True)


def _relative_white_balance_gains(
    target: tuple[float, float, float], current: tuple[float, float, float]
) -> tuple[float, float, float]:
    ratios = np.array(target, dtype=np.float32) / np.maximum(
        np.array(current, dtype=np.float32),
        1e-6,
    )
    return normalized_white_balance_gains(float(ratios[0]), float(ratios[1]), float(ratios[2]))


def _raw_camera_wb_already_applied(raw_metadata: Mapping[str, object] | None) -> bool:
    if raw_metadata is None:
        return False
    return bool(raw_metadata.get("raw_import_use_camera_wb", False))


def _raw_rgb_to_srgb_matrix(raw_metadata: Mapping[str, object] | None) -> np.ndarray | None:
    if raw_metadata is None:
        return None
    matrix = _coerce_matrix(raw_metadata.get("raw_rgb_xyz_matrix"))
    if matrix is None:
        matrix = _coerce_matrix(raw_metadata.get("rgb_xyz_matrix"))
    if matrix is None:
        return None
    if matrix.shape[0] >= 3 and matrix.shape[1] >= 3:
        camera_to_xyz = matrix[:3, :3].astype(np.float32, copy=False)
    else:
        return None
    xyz_to_srgb = np.array(
        [
            [3.2404542, -1.5371385, -0.4985314],
            [-0.9692660, 1.8760108, 0.0415560],
            [0.0556434, -0.2040259, 1.0572252],
        ],
        dtype=np.float32,
    )
    return xyz_to_srgb @ camera_to_xyz


def _coerce_matrix(value: object) -> np.ndarray | None:
    if value is None:
        return None
    try:
        matrix = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if matrix.ndim == 1 and matrix.size in {9, 12}:
        columns = 3 if matrix.size == 9 else 4
        matrix = matrix.reshape(3, columns)
    if matrix.ndim != 2 or matrix.shape[0] < 3 or matrix.shape[1] < 3:
        return None
    if not np.isfinite(matrix).all():
        return None
    return matrix


def _blackbody_rgb_approx(temperature: float) -> np.ndarray:
    kelvin = temperature / 100.0
    if kelvin <= 66.0:
        red = 255.0
        green = 99.4708025861 * np.log(kelvin) - 161.1195681661
        blue = 0.0 if kelvin <= 19.0 else 138.5177312231 * np.log(kelvin - 10.0) - 305.0447927307
    else:
        red = 329.698727446 * ((kelvin - 60.0) ** -0.1332047592)
        green = 288.1221695283 * ((kelvin - 60.0) ** -0.0755148492)
        blue = 255.0
    rgb = np.array([red, green, blue], dtype=np.float32)
    return np.clip(rgb, 1.0, 255.0) / 255.0


def estimate_white_balance_from_region(
    image: np.ndarray,
    rect: tuple[int, int, int, int] | None = None,
    *,
    sample_size: int = 16,
    reject_unsuitable: bool = True,
) -> WhiteBalanceEstimate:
    """Estimate RGB gains with robust RawTherapee-style neutral sampling."""
    data, _dtype = to_float(image)
    if data.ndim < 3 or data.shape[-1] < 3:
        return WhiteBalanceEstimate(1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, data.size)
    region = _white_balance_region(data, rect, sample_size)
    rgb = np.asarray(region[..., :3], dtype=np.float32).reshape(-1, 3)
    if rgb.size == 0:
        raise ValueError("white-balance region must not be empty")
    clipped = np.any((rgb <= 0.001) | (rgb >= 0.999), axis=1)
    luminance = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    near_black = luminance < 0.02
    saturated = np.max(rgb, axis=1) > 0.98
    chroma = np.max(rgb, axis=1) - np.min(rgb, axis=1)
    low_chroma = chroma < max(0.04, float(np.percentile(chroma, 40.0)))
    valid = ~(clipped | near_black | saturated)
    if reject_unsuitable:
        valid &= low_chroma
    if int(np.count_nonzero(valid)) < max(8, rgb.shape[0] // 50):
        valid = ~(clipped | near_black | saturated)
    if int(np.count_nonzero(valid)) < 3:
        raise ValueError("white-balance sample has too few usable neutral pixels")
    sample = rgb[valid]
    estimates = _trimmed_channel_mean(sample, trim_fraction=0.1)
    target = float(estimates[1])
    if target <= 1e-6:
        target = float(np.dot(estimates, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)))
    gains = target / np.maximum(estimates, 1e-6)
    gains = np.array(normalized_white_balance_gains(*gains, normalize=True), dtype=np.float32)
    warning = _white_balance_warning(
        valid_fraction=float(np.count_nonzero(valid) / rgb.shape[0]),
        clipped_fraction=float(np.count_nonzero(clipped) / rgb.shape[0]),
        near_black_fraction=float(np.count_nonzero(near_black) / rgb.shape[0]),
        saturated_fraction=float(np.count_nonzero(saturated) / rgb.shape[0]),
        local_variance=float(np.mean(np.var(sample, axis=0))),
    )
    return WhiteBalanceEstimate(
        red=float(gains[0]),
        green=float(gains[1]),
        blue=float(gains[2]),
        valid_fraction=float(np.count_nonzero(valid) / rgb.shape[0]),
        clipped_fraction=float(np.count_nonzero(clipped) / rgb.shape[0]),
        near_black_fraction=float(np.count_nonzero(near_black) / rgb.shape[0]),
        saturated_fraction=float(np.count_nonzero(saturated) / rgb.shape[0]),
        local_variance=float(np.mean(np.var(sample, axis=0))),
        sample_count=int(np.count_nonzero(valid)),
        warning=warning,
    )


def _white_balance_region(
    data: np.ndarray, rect: tuple[int, int, int, int] | None, sample_size: int
) -> np.ndarray:
    height, width = data.shape[:2]
    if rect is None:
        return data
    x, y, rect_width, rect_height = rect
    if rect_width <= 1 and rect_height <= 1:
        radius = max(1, int(sample_size) // 2)
        x = int(x) - radius
        y = int(y) - radius
        rect_width = rect_height = radius * 2 + 1
    x = max(0, min(int(x), width - 1))
    y = max(0, min(int(y), height - 1))
    rect_width = max(1, min(int(rect_width), width - x))
    rect_height = max(1, min(int(rect_height), height - y))
    return data[y : y + rect_height, x : x + rect_width]


def _trimmed_channel_mean(sample: np.ndarray, *, trim_fraction: float) -> np.ndarray:
    if sample.shape[0] < 10:
        return np.median(sample, axis=0)
    lower = float(trim_fraction * 100.0)
    upper = float(100.0 - lower)
    low = np.percentile(sample, lower, axis=0)
    high = np.percentile(sample, upper, axis=0)
    trimmed = sample[np.all((sample >= low) & (sample <= high), axis=1)]
    if trimmed.shape[0] < 3:
        trimmed = sample
    return np.mean(trimmed, axis=0)


def _white_balance_warning(
    *,
    valid_fraction: float,
    clipped_fraction: float,
    near_black_fraction: float,
    saturated_fraction: float,
    local_variance: float,
) -> str | None:
    warnings: list[str] = []
    if valid_fraction < 0.2:
        warnings.append("few neutral pixels")
    if clipped_fraction > 0.05:
        warnings.append("clipped pixels")
    if near_black_fraction > 0.25:
        warnings.append("near-black sample")
    if saturated_fraction > 0.05:
        warnings.append("saturated pixels")
    if local_variance > 0.03:
        warnings.append("high local variance")
    return ", ".join(warnings) if warnings else None


def _channel_view(data: np.ndarray, channel: str) -> np.ndarray:
    if data.ndim < 3 or data.shape[-1] < 3 or channel in {"rgb", "luminance"}:
        return data
    channels = {"red": 0, "green": 1, "blue": 2, "alpha": 3}
    if channel not in channels:
        raise ValueError(f"Unsupported channel: {channel}")
    if channels[channel] >= data.shape[-1]:
        raise ValueError(f"Image has no {channel} channel")
    return data[..., channels[channel]]
