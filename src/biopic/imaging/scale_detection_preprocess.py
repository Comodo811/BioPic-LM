"""Image preprocessing and projection helpers for scale detection."""

from __future__ import annotations

import numpy as np


def _prepared_gray(
    pixels: np.ndarray,
    roi: tuple[int, int, int, int] | None,
) -> tuple[np.ndarray, float]:
    array = np.asarray(pixels)
    if array.ndim > 2:
        channels = array[..., :3].astype(np.float32, copy=False)
        luminance = (
            0.2126 * channels[..., 0]
            + 0.7152 * channels[..., 1]
            + 0.0722 * channels[..., 2]
        )
        channel_options = [luminance, channels[..., 0], channels[..., 1], channels[..., 2]]
        array = max(
            channel_options,
            key=lambda item: float(np.percentile(item, 95.0) - np.percentile(item, 5.0)),
        )
    else:
        array = array.astype(np.float32, copy=False)
    if roi is not None:
        x, y, width, height = roi
        x0 = max(0, min(array.shape[1], int(x)))
        y0 = max(0, min(array.shape[0], int(y)))
        x1 = max(x0, min(array.shape[1], x0 + int(width)))
        y1 = max(y0, min(array.shape[0], y0 + int(height)))
        array = array[y0:y1, x0:x1]
    if array.size == 0:
        return array, 1.0
    scale = min(1.0, 1400.0 / max(array.shape[:2]))
    if scale < 1.0:
        try:
            import cv2  # type: ignore[import-untyped]

            array = cv2.resize(array, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        except ImportError:
            step = max(1, int(round(1.0 / scale)))
            scale = 1.0 / step
            array = array[::step, ::step]
    low, high = np.percentile(array, [2.0, 98.0])
    if high <= low:
        return np.zeros_like(array, dtype=np.float32), scale
    gray = np.clip((array - low) / (high - low), 0.0, 1.0).astype(np.float32, copy=False)
    return gray, scale


def _crop_constant_dark_border(array: np.ndarray) -> np.ndarray:
    if array.ndim != 2 or array.size == 0:
        return array
    low = float(np.percentile(array, 0.5))
    high = float(np.percentile(array, 50.0))
    if high - low < 8.0:
        return array
    border_threshold = low + min(4.0, (high - low) * 0.08)
    content = array > border_threshold
    if float(np.mean(~content)) < 0.03:
        return array
    rows = np.where(np.any(content, axis=1))[0]
    cols = np.where(np.any(content, axis=0))[0]
    if rows.size < max(8, array.shape[0] * 0.30) or cols.size < max(8, array.shape[1] * 0.30):
        return array
    return array[int(rows[0]) : int(rows[-1]) + 1, int(cols[0]) : int(cols[-1]) + 1]


def _period_from_projection(profile: np.ndarray) -> tuple[float, float]:
    values = np.asarray(profile, dtype=np.float32)
    if values.size < 8:
        return 0.0, 0.0
    values = values - np.mean(values)
    window = max(5, min(101, values.size // 12 * 2 + 1))
    if window < values.size:
        kernel = np.ones(window, dtype=np.float32) / window
        values = values - np.convolve(values, kernel, mode="same")
    spectrum = np.abs(np.fft.rfft(values))
    if spectrum.size < 4:
        return 0.0, 0.0
    freqs = np.fft.rfftfreq(values.size)
    min_period = 3.0
    max_period = max(min_period + 1.0, values.size / 2.0)
    valid = (freqs > 0) & (1.0 / np.maximum(freqs, 1e-12) >= min_period)
    valid &= 1.0 / np.maximum(freqs, 1e-12) <= max_period
    if not np.any(valid):
        return 0.0, 0.0
    valid_indices = np.nonzero(valid)[0]
    peak_index = int(valid_indices[np.argmax(spectrum[valid])])
    noise_floor = float(np.median(spectrum[valid_indices])) + 1e-9
    confidence = float(spectrum[peak_index] / noise_floor)
    return float(1.0 / freqs[peak_index]), confidence


def _stripe_positions_from_projection(profile: np.ndarray, period: float) -> list[float]:
    values = np.asarray(profile, dtype=np.float32)
    if values.size < 3 or period <= 0:
        return []
    centered = values - np.median(values)
    bright = centered
    dark = -centered
    bright_score = float(np.percentile(bright, 95.0) - np.percentile(bright, 50.0))
    dark_score = float(np.percentile(dark, 95.0) - np.percentile(dark, 50.0))
    signal = dark if dark_score >= bright_score * 0.55 else bright
    threshold = float(np.percentile(signal, 82.0))
    candidates: list[float] = []
    for index in range(1, signal.size - 1):
        if signal[index] >= threshold and signal[index] >= signal[index - 1] and signal[index] >= signal[index + 1]:
            candidates.append(float(index))
    if not candidates:
        start = float(np.argmax(signal) % period)
        return [start + period * i for i in range(int((signal.size - start) / period) + 1)]
    min_separation = max(2.0, period * 0.55)
    positions: list[float] = []
    for candidate in candidates:
        if not positions or candidate - positions[-1] >= min_separation:
            positions.append(candidate)
        elif signal[int(candidate)] > signal[int(positions[-1])]:
            positions[-1] = candidate
    return positions


def _estimate_rotation_by_projection(pixels: np.ndarray) -> float:
    gray, _scale = _prepared_gray(pixels, None)
    if gray.shape[0] < 16 or gray.shape[1] < 16:
        raise ValueError("image is too small for stripe alignment")
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValueError("stripe alignment requires OpenCV") from exc
    height, width = gray.shape[:2]
    center = (width / 2.0, height / 2.0)
    best_angle = 0.0
    best_score = -1.0
    for angle in np.linspace(-20.0, 20.0, 161):
        matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(
            gray,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        vertical_profile = rotated.mean(axis=0)
        horizontal_profile = rotated.mean(axis=1)
        score = max(_projection_alignment_score(vertical_profile), _projection_alignment_score(horizontal_profile))
        if score > best_score:
            best_score = score
            best_angle = float(angle)
    if best_score <= 0:
        raise ValueError("could not determine stripe alignment")
    return best_angle


def _projection_alignment_score(profile: np.ndarray) -> float:
    values = np.asarray(profile, dtype=np.float32)
    if values.size < 4:
        return 0.0
    values = values - np.mean(values)
    return float(np.std(values) + 0.5 * np.std(np.diff(values)))

