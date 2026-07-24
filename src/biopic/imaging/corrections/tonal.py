"""Tonal correction operations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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
    return restore_dtype(np.clip(data, 0.0, 1.0) ** gamma, dtype)


def curve_adjust(
    image: np.ndarray, points: list[tuple[float, float]], *, channel: str = "rgb"
) -> np.ndarray:
    """Apply a monotonic PCHIP gradation curve with normalized control points."""
    if len(points) < 2:
        raise ValueError("at least two curve points are required")
    sorted_points = sorted(points)
    xs = np.array([point[0] for point in sorted_points], dtype=np.float32)
    ys = np.array([point[1] for point in sorted_points], dtype=np.float32)
    if np.any(np.diff(xs) <= 0):
        raise ValueError("curve x values must be strictly increasing")
    if xs[0] < 0 or xs[-1] > 1 or np.any((ys < 0) | (ys > 1)):
        raise ValueError("curve points must lie within [0, 1]")
    interpolator = PchipInterpolator(xs, ys, extrapolate=True)
    data, dtype = to_float(image)
    adjusted = data.copy()
    target = _channel_view(adjusted, channel)
    target[...] = np.clip(interpolator(np.clip(target, 0.0, 1.0)), 0.0, 1.0)
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
    normalize: bool = True,
    sample_rect: tuple[int, int, int, int] | None = None,
    sample_size: int = 16,
) -> np.ndarray:
    """Apply rendered-image white balance with RawTherapee-inspired controls.

    ``manual`` applies RGB channel multipliers. ``temperature`` derives gains
    from a D65-referenced black-body approximation plus green-magenta tint.
    ``auto`` and ``spot`` derive multipliers from robust neutral statistics.
    """
    method = method.lower()
    if method == "temperature":
        gains = white_balance_gains_from_temperature(temperature, tint=tint)
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
    return white_balance_multipliers(
        image, red=gains[0], green=gains[1], blue=gains[2], normalize=normalize
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
    channels = {"red": 0, "green": 1, "blue": 2}
    if channel not in channels:
        raise ValueError(f"Unsupported channel: {channel}")
    return data[..., channels[channel]]
