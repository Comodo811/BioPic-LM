"""Shared helpers for focus-stacking methods."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
from scipy import ndimage

from biopic.imaging.stacking import stacking_constants as dc
from biopic.imaging.stacking.focus_metrics import FocusMetric, focus_measure, to_luminance
from biopic.imaging.stacking.shared_acceleration import (
    _cuda_available,
    _downscale_average,
    _filter2d_accelerated,
    _gaussian_blur_accelerated,
    _gaussian_stack_accelerated,
    _resize_accelerated,
    _resize_map,
    _stack_focus_measure_accelerated,
    _uniform_stack_accelerated,
)
from biopic.imaging.stacking.stack_types import BackgroundMode, FocusStackParameters, PreviewCallback, ProgressCallback

try:  # Optional native hot-loop acceleration for Custom stacking.
    from numba import njit, prange
except Exception:  # pragma: no cover - optional dependency
    njit = None
    prange = range


def regularize_focus_scores(
    scores: np.ndarray,
    smoothing_sigma: float,
    use_cuda: bool = False,
) -> np.ndarray:
    """Spatially regularize frame focus scores."""
    if scores.ndim != 3:
        raise ValueError("scores must have shape frame, height, width")
    if smoothing_sigma <= 0:
        return scores.astype(np.float32, copy=False)
    if use_cuda and _cuda_available():
        return _gaussian_stack_accelerated(scores, smoothing_sigma, use_cuda=True)
    return ndimage.gaussian_filter(
        scores.astype(np.float32, copy=False),
        sigma=(0.0, smoothing_sigma, smoothing_sigma),
        mode="reflect",
    ).astype(np.float32, copy=False)


def stack_focus_measure(
    images: list[np.ndarray],
    metric: FocusMetric,
    radius: int,
    use_cuda: bool = False,
) -> np.ndarray:
    """Return focus scores for a stack using spatial-only filters."""
    return np.stack(
        [focus_measure(image, metric, radius) for image in images],
        axis=0,
    ).astype(np.float32, copy=False)


def _resize_reference_score_channel(
    image: np.ndarray,
    shape: tuple[int, int],
    factor: int,
) -> np.ndarray:
    """Resize one score channel back onto the full-resolution grid."""
    target_h, target_w = shape
    source = image.astype(np.float32, copy=False)
    if source.shape[:2] == shape:
        return source
    factor = max(1, int(factor))
    y0 = np.minimum(np.arange(target_h, dtype=np.int32) // factor, source.shape[0] - 1)
    x0 = np.minimum(np.arange(target_w, dtype=np.int32) // factor, source.shape[1] - 1)
    y1 = np.minimum(y0 + 1, source.shape[0] - 1)
    x1 = np.minimum(x0 + 1, source.shape[1] - 1)
    fy = ((np.arange(target_h, dtype=np.float32) % factor) / float(factor))[:, None]
    fx = ((np.arange(target_w, dtype=np.float32) % factor) / float(factor))[None, :]
    top = source[y0, :][:, x0] * (1.0 - fx) + source[y0, :][:, x1] * fx
    bottom = source[y1, :][:, x0] * (1.0 - fx) + source[y1, :][:, x1] * fx
    return (top * (1.0 - fy) + bottom * fy).astype(np.float32, copy=False)


def reference_focus_score_channels(
    image: np.ndarray,
    scale_preset: int,
    luminance: np.ndarray | None = None,
    frame_gain: float = 1.0,
    use_cuda: bool = False,
) -> np.ndarray:
    """Build the three detail/score channels controlled by the filter set."""
    preset = int(np.clip(scale_preset, 1, 5))
    gray = _quantize_unit(reference_luminance(image) if luminance is None else luminance)
    working = gray
    if preset > 4:
        working = _quantize_unit(_downscale_average(working, 2, use_cuda=use_cuda))
    smooth1, detail1 = reference_smooth_and_detail(working, use_cuda=use_cuda)
    if preset in (1, 3):
        working = _quantize_unit(_downscale_average(smooth1, 2, use_cuda=use_cuda))
    elif preset in (2, 4, 5):
        working = _quantize_unit(_downscale_average(smooth1, 3, use_cuda=use_cuda))
    else:
        working = smooth1
    smooth2, detail2 = reference_smooth_and_detail(working, use_cuda=use_cuda)
    if preset in (1, 3):
        working = _quantize_unit(_downscale_average(smooth2, 2, use_cuda=use_cuda))
    elif preset in (2, 4, 5):
        working = _quantize_unit(_downscale_average(smooth2, 3, use_cuda=use_cuda))
    else:
        working = smooth2
    _smooth3, detail3 = reference_smooth_and_detail(working, use_cuda=use_cuda)
    details = [detail1, detail2, detail3]
    if preset in (1, 3):
        resize_factors = (1, 2, 4)
    elif preset in (2, 4, 5):
        resize_factors = (1, 3, 9)
    else:
        resize_factors = (1, 1, 1)
    scores: list[np.ndarray] = []
    for channel_index, detail in enumerate(details):
        score = reference_detail_support_score(
            detail,
            channel_index,
            frame_gain=frame_gain,
            use_cuda=use_cuda,
        )
        score = _quantize_unit(
            _resize_reference_score_channel(
                score,
                gray.shape,
                resize_factors[channel_index],
            )
        )
        if preset > 4:
            score = _quantize_unit(_resize_reference_score_channel(score, gray.shape, 2))
        scores.append(score)
    return _post_smooth_reference_scores(np.stack(scores, axis=0), preset, use_cuda=use_cuda)


def reference_luminance(image: np.ndarray) -> np.ndarray:
    """Use the reference RGB-to-gray weights for focus scoring."""
    if image.ndim == 2:
        return image.astype(np.float32, copy=False)
    source = image.astype(np.float32, copy=False)
    return (
        source[..., 0] * dc.RGB_TO_GRAY_R
        + source[..., 1] * dc.RGB_TO_GRAY_G
        + source[..., 2] * dc.RGB_TO_GRAY_B
    ).astype(np.float32, copy=False)


def reference_source_buffer_image(image: np.ndarray) -> np.ndarray:
    """Convert a source frame to the byte-precision buffer used by the reference stacker."""
    return _quantize_unit(_as_float_image(np.asarray(image)))


def reference_stack_mode_three_working_image(
    image: np.ndarray,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    """Return the 2x2 averaged working copy used by stack mode 3."""
    source = reference_source_buffer_image(image)
    _ = use_cuda
    height, width = source.shape[:2]
    out_h = max(1, height // 2)
    out_w = max(1, width // 2)
    cropped = np.rint(source[: out_h * 2, : out_w * 2] * dc.BYTE_MAX).astype(np.uint16)
    if source.ndim == 2:
        total = (
            cropped[0::2, 0::2]
            + cropped[0::2, 1::2]
            + cropped[1::2, 0::2]
            + cropped[1::2, 1::2]
            + 2
        )
    else:
        total = (
            cropped[0::2, 0::2, :]
            + cropped[0::2, 1::2, :]
            + cropped[1::2, 0::2, :]
            + cropped[1::2, 1::2, :]
            + 2
        )
    return (total // 4).astype(np.float32) / dc.BYTE_MAX


def _quantize_unit(values: np.ndarray) -> np.ndarray:
    """Round a normalized float image to reference 8-bit precision."""
    return (np.rint(np.clip(values, 0.0, 1.0) * dc.BYTE_MAX) / dc.BYTE_MAX).astype(
        np.float32,
        copy=False,
    )


def reference_smooth_and_detail(
    gray: np.ndarray,
    use_cuda: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return center-excluding neighbor smooth and absolute detail images."""
    _ = use_cuda
    source_byte = np.rint(np.clip(gray, 0.0, 1.0) * dc.BYTE_MAX).astype(np.uint16)
    smooth_byte = source_byte.copy()
    detail_byte = source_byte.copy()
    if source_byte.shape[0] > 2 and source_byte.shape[1] > 2:
        smooth_inner = np.rint(
            (
                (
                    source_byte[:-2, 1:-1]
                    + source_byte[1:-1, :-2]
                    + source_byte[1:-1, 2:]
                    + source_byte[2:, 1:-1]
                )
                * 4
                + (
                    source_byte[:-2, :-2]
                    + source_byte[:-2, 2:]
                    + source_byte[2:, :-2]
                    + source_byte[2:, 2:]
                )
                * 3
            )
            / dc.DETAIL_SMOOTH_DENOMINATOR
        ).astype(np.int32)
        smooth_byte[1:-1, 1:-1] = np.clip(smooth_inner, 0, dc.BYTE_MAX_INT).astype(
            np.uint16
        )
        diff = source_byte[1:-1, 1:-1].astype(np.int32) - smooth_inner
        detail_byte[1:-1, 1:-1] = np.abs(diff).astype(np.uint16)
    return (
        smooth_byte.astype(np.float32) / dc.BYTE_MAX,
        detail_byte.astype(np.float32) / dc.BYTE_MAX,
    )


def reference_detail_support_score(
    detail: np.ndarray,
    channel_index: int,
    frame_gain: float = 1.0,
    use_cuda: bool = False,
) -> np.ndarray:
    """Apply 3x3 support weighting and a saturating score curve."""
    _ = use_cuda
    detail_byte = np.rint(np.clip(detail, 0.0, 1.0) * dc.BYTE_MAX).astype(np.uint16)
    score = np.zeros_like(detail_byte, dtype=np.uint16)
    if detail_byte.shape[0] <= 2 or detail_byte.shape[1] <= 2:
        return score.astype(np.float32) / dc.BYTE_MAX
    support = (
        detail_byte[1:-1, 1:-1] * 4
        + (
            detail_byte[:-2, 1:-1]
            + detail_byte[2:, 1:-1]
            + detail_byte[1:-1, :-2]
            + detail_byte[1:-1, 2:]
        )
        * 3
        + (
            detail_byte[:-2, :-2]
            + detail_byte[:-2, 2:]
            + detail_byte[2:, :-2]
            + detail_byte[2:, 2:]
        )
        * 2
    ).astype(np.float32)
    channel_scale = dc.detail_channel_gain(channel_index)
    value = np.rint(support * float(frame_gain) * channel_scale)
    inner_score = np.rint(
        (value * dc.DETAIL_SCORE_NUMERATOR_SCALE)
        / np.maximum(value + dc.DETAIL_SCORE_SATURATION_OFFSET, 1.0)
    )
    score[1:-1, 1:-1] = np.clip(inner_score, 0.0, dc.BYTE_MAX).astype(np.uint16)
    return (score.astype(np.float32) / dc.BYTE_MAX).astype(np.float32, copy=False)


def _post_smooth_reference_scores(
    scores: np.ndarray,
    scale_preset: int,
    use_cuda: bool = False,
) -> np.ndarray:
    """Apply the sparse weighted score cleanup kernel."""
    preset = int(np.clip(scale_preset, 1, 5))
    smoothed = np.empty_like(scores, dtype=np.float32)
    for channel_index in range(scores.shape[0]):
        step = preset * (channel_index + 1)
        smoothed[channel_index] = reference_sparse_wide_smooth(
            scores[channel_index],
            step,
            use_cuda=use_cuda,
        )
    return smoothed


def reference_sparse_wide_smooth(
    values: np.ndarray,
    step: int,
    use_cuda: bool = False,
) -> np.ndarray:
    """Apply the sparse cleanup kernel for one score channel."""
    step = max(1, int(step))
    source = values.astype(np.float32, copy=False)
    y_margin = 6 * step
    # The horizontal margin matches the widest sparse score-channel sample.
    x_margin = 9 * step
    if source.shape[0] <= y_margin * 2 or source.shape[1] <= x_margin * 2:
        return _quantize_unit(source)
    kernel = _reference_sparse_wide_kernel(step)
    filtered = _filter2d_accelerated(
        source,
        kernel,
        borderType=cv2.BORDER_CONSTANT,
        use_cuda=use_cuda,
    )
    filtered = _quantize_unit(filtered)
    out = source.copy()
    out[y_margin:-y_margin, x_margin:-x_margin] = filtered[
        y_margin:-y_margin,
        x_margin:-x_margin,
    ]
    return _quantize_unit(out)


@lru_cache(maxsize=16)
def _reference_sparse_wide_kernel(step: int) -> np.ndarray:
    """Return the normalized sparse cleanup kernel for a channel step."""
    samples: tuple[tuple[int, tuple[tuple[int, int], ...]], ...] = (
        (
            0x0B,
            (
                (-3 * step, -2 * step),
                (-3 * step, 2 * step),
                (-2 * step, -3 * step),
                (-2 * step, 3 * step),
                (3 * step, -2 * step),
                (3 * step, 2 * step),
                (2 * step, -3 * step),
                (2 * step, 3 * step),
            ),
        ),
        (
            0x18,
            (
                (-3 * step, -1 * step),
                (-3 * step, 1 * step),
                (-1 * step, -1 * step),
                (-1 * step, 1 * step),
                (3 * step, -1 * step),
                (3 * step, 1 * step),
                (1 * step, -1 * step),
                (1 * step, 1 * step),
            ),
        ),
        (
            0x1D,
            (
                (-3 * step, 0),
                (3 * step, 0),
                (0, -3 * step),
                (0, 3 * step),
            ),
        ),
        (
            0x2A,
            (
                (-2 * step, -2 * step),
                (-2 * step, 2 * step),
                (2 * step, -2 * step),
                (2 * step, 2 * step),
            ),
        ),
        (
            0x5A,
            (
                (-2 * step, -1 * step),
                (-2 * step, 1 * step),
                (-1 * step, -2 * step),
                (-1 * step, 2 * step),
                (1 * step, -2 * step),
                (1 * step, 2 * step),
                (2 * step, -1 * step),
                (2 * step, 1 * step),
            ),
        ),
        (
            0x6D,
            (
                (-2 * step, 0),
                (2 * step, 0),
                (0, -2 * step),
                (0, 2 * step),
            ),
        ),
        (
            0xC3,
            (
                (-1 * step, -1 * step),
                (-1 * step, 1 * step),
                (1 * step, -1 * step),
                (1 * step, 1 * step),
            ),
        ),
        (
            0xED,
            (
                (-1 * step, 0),
                (1 * step, 0),
                (0, -1 * step),
                (0, 1 * step),
            ),
        ),
        (0x120, ((0, 0),)),
    )
    margin = 3 * step
    kernel = np.zeros((margin * 2 + 1, margin * 2 + 1), dtype=np.float32)
    divisor = 0.0
    for weight, offsets in samples:
        divisor += weight * len(offsets)
        for dy, dx in offsets:
            kernel[margin + dy, margin + dx] += float(weight)
    if not np.isclose(divisor, dc.SPARSE_WIDE_SMOOTH_DIVISOR):
        raise ValueError("reference sparse wide kernel divisor changed unexpectedly")
    return kernel / dc.SPARSE_WIDE_SMOOTH_DIVISOR


def combine_reference_detail_and_confidence_buffers(
    source_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    id_buffers: np.ndarray,
    params: FocusStackParameters,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Combine source and score buffers with the reference filter weights."""
    weights = reference_filter_weight_bytes_map(confidence_buffers, params)
    image = _reference_weighted_byte_sum(source_buffers, weights)
    confidence = _reference_weighted_byte_sum(confidence_buffers, weights)
    id_map = _reference_weighted_byte_sum(id_buffers, weights)
    return (
        image.astype(np.float32, copy=False),
        confidence.astype(np.float32, copy=False),
        _quantize_unit(id_map),
    )


def combine_reference_detail_buffers(
    source_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Combine only source buffers with the reference filter weight map."""
    weights = reference_filter_weight_bytes_map(confidence_buffers, params)
    return _reference_weighted_byte_sum(source_buffers, weights).astype(np.float32)


def _reference_weighted_byte_sum(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    value_bytes = np.rint(
        np.clip(values.astype(np.float32, copy=False), 0.0, 1.0) * dc.BYTE_MAX
    ).astype(np.uint16)
    weight_bytes = weights.astype(np.uint16, copy=False)
    if value_bytes.ndim == 4:
        weighted = (
            np.sum(
                value_bytes.astype(np.uint32) * weight_bytes[..., None].astype(np.uint32),
                axis=0,
            )
            + dc.BYTE_ROUND_INT
        ) // dc.BYTE_MAX_INT
    else:
        weighted = (
            np.sum(value_bytes.astype(np.uint32) * weight_bytes.astype(np.uint32), axis=0)
            + dc.BYTE_ROUND_INT
        ) // dc.BYTE_MAX_INT
    return weighted.astype(np.float32) / dc.BYTE_MAX


def reference_filter_weight_bytes_map(
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Return byte weights for the high/mid/low filter buffers."""
    if not params.adaptive_weighting:
        weights = np.array(reference_fixed_filter_weights(params.detail_scale), dtype=np.uint16)
        return weights.reshape(3, 1, 1)
    return reference_smart_filter_weight_bytes_map(confidence_buffers)


def reference_filter_weights_map(
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Return fixed or Smart filter weights for high/mid/low detail buffers."""
    if not params.adaptive_weighting:
        weights = np.array(reference_fixed_filter_weights(params.detail_scale), dtype=np.float32)
        weights /= max(float(np.sum(weights)), 1.0)
        return weights.reshape(3, 1, 1)
    return reference_smart_filter_weights_map(confidence_buffers)


def reference_smart_filter_weights_map(confidence_buffers: np.ndarray) -> np.ndarray:
    """Return normalized smart-filter weights from confidence buffers."""
    weights = reference_smart_filter_weight_bytes_map(confidence_buffers).astype(np.float32)
    return (weights / dc.SMART_BLEND_DENOMINATOR).astype(np.float32, copy=False)


def reference_smart_filter_weight_bytes_map(confidence_buffers: np.ndarray) -> np.ndarray:
    """Return byte smart-filter weights from confidence buffers."""
    confidence = np.rint(
        np.clip(confidence_buffers.astype(np.float32, copy=False), 0.0, 1.0)
        * dc.BYTE_MAX
    ).astype(np.float32, copy=False)
    high = confidence[0]
    mid = confidence[1]
    low = confidence[2]
    denominator = np.rint(
        high * dc.SMART_HIGH_CONFIDENCE_WEIGHT
        + dc.SMART_DENOMINATOR_BIAS
        + mid * dc.SMART_MID_CONFIDENCE_WEIGHT
        + low * dc.SMART_LOW_CONFIDENCE_WEIGHT
    )
    denominator = np.maximum(denominator, 1.0)
    high_weight = np.rint(high * dc.SMART_HIGH_BYTE_WEIGHT_SCALE / denominator)
    mid_weight = np.rint(mid * dc.SMART_MID_BYTE_WEIGHT_SCALE / denominator)
    high_weight = np.clip(high_weight, 0, dc.BYTE_MAX_INT).astype(np.uint16)
    mid_weight = np.clip(mid_weight, 0, dc.BYTE_MAX_INT).astype(np.uint16)
    low_weight = np.clip(
        dc.BYTE_MAX_INT - (high_weight.astype(np.int16) + mid_weight.astype(np.int16)),
        0,
        dc.BYTE_MAX_INT,
    ).astype(np.uint16)
    return np.stack([high_weight, mid_weight, low_weight], axis=0)


def combine_reference_confidence_buffers(
    confidence_buffers: np.ndarray, params: FocusStackParameters
) -> np.ndarray:
    """Return the confidence channel that the final composite uses."""
    weights = reference_filter_weights_map(confidence_buffers, params)
    return np.sum(confidence_buffers * weights, axis=0)


def combine_reference_depth_buffers(
    depth_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Combine frame-id/depth buffers using the same filter profile."""
    if not params.adaptive_weighting:
        weights = np.array(reference_fixed_filter_weights(params.detail_scale), dtype=np.float32)
        weights /= max(float(np.sum(weights)), 1.0)
        return np.sum(depth_buffers * weights[:, None, None], axis=0)
    weights = reference_smart_filter_weights_map(confidence_buffers)
    return np.sum(depth_buffers * weights, axis=0)


def reference_patch_adjust_confidence(
    confidence: np.ndarray,
    depth_map: np.ndarray,
    score_threshold: int,
    region_bias: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Narrow or widen confidence-supported depth regions."""
    adjustment = int(np.clip(region_bias, dc.PATCH_ADJUST_MIN, dc.PATCH_ADJUST_MAX))
    if adjustment == 0:
        return confidence.astype(np.float32, copy=False), depth_map
    radius = abs(adjustment)
    threshold = dc.minimum_score_threshold_unit(score_threshold)
    kernel = _circular_kernel(max(radius, 1)).astype(np.float32)
    source_confidence = confidence.astype(np.float32, copy=False)
    source_depth = depth_map.astype(np.float32, copy=False)
    strong = source_confidence >= threshold
    support = ndimage.convolve(strong.astype(np.float32), kernel, mode="constant", cval=0.0)
    adjusted_confidence = source_confidence.copy()
    adjusted_depth = np.asarray(depth_map, dtype=np.uint16).copy()
    if adjustment < 0:
        weak_support = ndimage.convolve(
            (~strong).astype(np.float32), kernel, mode="constant", cval=0.0
        )
        shrink = strong & (weak_support > 0)
        adjusted_confidence[shrink] = max(threshold - dc.INCREMENTAL_REPLACE_DELTA, 0.0)
        adjusted_depth[shrink] = np.uint16(max(0, int(np.max(depth_map)) // 2))
    else:
        weighted_depth = ndimage.convolve(
            source_depth * source_confidence * strong,
            kernel,
            mode="constant",
            cval=0.0,
        )
        weight_sum = ndimage.convolve(
            source_confidence * strong,
            kernel,
            mode="constant",
            cval=0.0,
        )
        grow = (~strong) & (support > 0) & (weight_sum > 0)
        adjusted_confidence[grow] = min(threshold + dc.INCREMENTAL_REPLACE_DELTA, 1.0)
        adjusted_depth[grow] = np.clip(
            np.rint(weighted_depth[grow] / np.maximum(weight_sum[grow], 1e-6)),
            0,
            max(0, int(np.max(depth_map))),
        ).astype(np.uint16)
    return adjusted_confidence.astype(np.float32, copy=False), adjusted_depth


def reference_low_score_transition(
    image: np.ndarray,
    detail_image: np.ndarray,
    background: np.ndarray,
    confidence: np.ndarray,
    score_threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the pre-final low-score transition pass."""
    level = int(np.clip(score_threshold, 0, dc.MINIMUM_SCORE_MAX))
    if level <= 0:
        return image.astype(np.float32, copy=False), confidence.astype(np.float32, copy=False)
    threshold = dc.minimum_score_threshold_unit(level)
    if threshold <= 0:
        return image.astype(np.float32, copy=False), confidence.astype(np.float32, copy=False)
    source_confidence = confidence.astype(np.float32, copy=False)
    low = source_confidence < threshold
    if not np.any(low):
        return image.astype(np.float32, copy=False), source_confidence
    current_weight = np.zeros_like(source_confidence, dtype=np.float32)
    current_weight[low] = np.clip(
        source_confidence[low] * dc.LOW_SCORE_CURRENT_NUMERATOR
        / np.maximum(threshold * dc.BYTE_MAX, 1e-6),
        0.0,
        1.0,
    )
    detail_weight = current_weight * dc.LOW_SCORE_DETAIL_FRACTION
    background_weight = np.clip(1.0 - (current_weight + detail_weight), 0.0, 1.0)
    if image.ndim == 3:
        current_weight = current_weight[..., None]
        detail_weight = detail_weight[..., None]
        background_weight = background_weight[..., None]
    else:
        low = low
    blended = image * current_weight + detail_image * detail_weight + background * background_weight
    transitioned = np.where(low[..., None] if image.ndim == 3 else low, blended, image)
    smooth_confidence = reference_low_score_confidence_smooth(source_confidence)
    adjusted_confidence = source_confidence.copy()
    adjusted_confidence[low] = smooth_confidence[low]
    return transitioned.astype(np.float32, copy=False), adjusted_confidence.astype(
        np.float32, copy=False
    )


def reference_low_score_confidence_smooth(confidence: np.ndarray) -> np.ndarray:
    """Use the 3x3 score/id smoothing stencil."""
    kernel = np.array(
        [[2.0, 3.0, 2.0], [3.0, 4.0, 3.0], [2.0, 3.0, 2.0]],
        dtype=np.float32,
    )
    kernel /= dc.LOW_SCORE_CONFIDENCE_SMOOTH_DENOMINATOR
    return cv2.filter2D(
        confidence.astype(np.float32, copy=False),
        -1,
        kernel,
        borderType=cv2.BORDER_REFLECT,
    )

def filter_focus_scores(
    scores: np.ndarray,
    smoothing_sigma: float,
    detail_scale: int,
    scale_preset: int,
    adaptive_weighting: bool,
    use_cuda: bool = False,
) -> np.ndarray:
    """Apply a detail-to-smooth focus-score profile independent of metric type."""
    base_sigma = max(float(smoothing_sigma), 0.0)
    level = int(np.clip(detail_scale, 1, 10))
    profile = int(np.clip(scale_preset, 1, 5))
    level_sigma = (level - 1) * (0.25 + profile * 0.05)
    fixed_sigma = base_sigma + level_sigma
    fixed = regularize_focus_scores(scores, fixed_sigma, use_cuda=use_cuda)
    if not adaptive_weighting:
        return fixed

    sharp = regularize_focus_scores(scores, max(0.0, base_sigma * 0.35), use_cuda=use_cuda)
    smooth = regularize_focus_scores(
        scores,
        fixed_sigma + 0.75 + profile * 0.15,
        use_cuda=use_cuda,
    )
    confidence = _normalized_score_span(fixed)
    smart_mix = np.clip(1.0 - confidence * (0.6 + profile * 0.06), 0.15, 0.85)
    return (sharp * (1.0 - smart_mix) + smooth * smart_mix).astype(np.float32, copy=False)


def apply_score_threshold(scores: np.ndarray, score_threshold: int) -> np.ndarray:
    """Suppress weak normalized focus scores before source-frame selection."""
    return apply_score_threshold_from_normalized(
        scores, _normalize_scores(scores), score_threshold
    )


def apply_score_threshold_from_normalized(
    scores: np.ndarray, normalized: np.ndarray, score_threshold: int
) -> np.ndarray:
    """Suppress weak focus scores using a precomputed normalized score stack."""
    level = int(np.clip(score_threshold, 0, dc.MINIMUM_SCORE_MAX))
    if level <= 0:
        return scores.astype(np.float32, copy=False)
    threshold = min(0.34, (level * 3.0) / 255.0)
    gated = np.where(normalized >= threshold, scores, 0.0)
    fallback = np.max(gated, axis=0) <= 0
    if np.any(fallback):
        # Low-texture regions should average instead of mosaicking arbitrary frame winners.
        gated[:, fallback] = 1.0
    return gated.astype(np.float32, copy=False)


def adjust_depth_regions(
    depth_map: np.ndarray, scores: np.ndarray, region_bias: int
) -> np.ndarray:
    """Shrink or grow same-depth regions using local weighted neighbor support."""
    adjustment = int(np.clip(region_bias, -10, 10))
    if adjustment == 0:
        return depth_map
    confidence = focus_confidence_map(scores)
    threshold = max(0.05, float(np.percentile(confidence, 45.0)))
    return _propagate_depth_with_neighbor_support(
        depth_map,
        scores,
        confidence,
        radius=abs(adjustment),
        threshold=threshold,
        grow=adjustment > 0,
    )


def focus_confidence_map(scores: np.ndarray) -> np.ndarray:
    """Return a normalized confidence map from per-frame focus scores."""
    return focus_confidence_from_normalized(_normalize_scores(scores))


def focus_confidence_from_normalized(normalized: np.ndarray) -> np.ndarray:
    """Return a confidence map from a precomputed normalized score stack."""
    peak = np.max(normalized, axis=0)
    if normalized.shape[0] == 1:
        return peak.astype(np.float32, copy=False)
    second = np.partition(normalized, -2, axis=0)[-2]
    margin = np.clip(peak - second, 0.0, 1.0)
    contrast = np.clip(margin / np.maximum(peak, 1e-6), 0.0, 1.0)
    return np.clip(peak * 0.55 + contrast * 0.45, 0.0, 1.0).astype(np.float32, copy=False)


def reference_ring_supported_confidence_cleanup(
    confidence: np.ndarray,
    depth_map: np.ndarray,
    score_threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the sparse ring confidence propagation from the reference stacker."""
    level = int(np.clip(score_threshold, 0, 29))
    if level < 2:
        return confidence.astype(np.float32, copy=False), depth_map
    threshold = dc.minimum_score_threshold_unit(level)
    offsets = [
        [(-2, 0), (-1, 1), (0, 2), (1, 1), (2, 0), (1, -1), (0, -2), (-1, -1)],
        [(-3, 0), (-2, 2), (0, 3), (2, 2), (3, 0), (2, -2), (0, -3), (-2, -2)],
        [(-6, 0), (-4, 4), (0, 6), (4, 4), (6, 0), (4, -4), (0, -6), (-4, -4)],
        [(-9, 0), (-6, 6), (0, 9), (6, 6), (9, 0), (6, -6), (0, -9), (-6, -6)],
    ]
    source_confidence = confidence.astype(np.float32, copy=False)
    source_depth = np.asarray(depth_map, dtype=np.float32)
    support_count = np.zeros(source_confidence.shape, dtype=np.float32)
    depth_sum = np.zeros(source_confidence.shape, dtype=np.float32)
    unresolved = np.ones(source_confidence.shape, dtype=bool)
    for ring in offsets:
        ring_count = np.zeros(source_confidence.shape, dtype=np.float32)
        ring_depth_sum = np.zeros(source_confidence.shape, dtype=np.float32)
        for dy, dx in ring:
            shifted_conf = _shift_map_constant(source_confidence, -dy, -dx, 0.0)
            strong = shifted_conf > threshold
            ring_count += strong.astype(np.float32)
            ring_depth_sum += _shift_map_constant(source_depth, -dy, -dx, 0.0) * strong
        use_ring = unresolved & (support_count < 3)
        support_count[use_ring] += ring_count[use_ring]
        depth_sum[use_ring] += ring_depth_sum[use_ring]
        unresolved &= support_count < 3
        if not np.any(unresolved):
            break
    supported = support_count > 1
    cleaned_confidence = source_confidence.copy()
    cleaned_depth = np.asarray(depth_map, dtype=np.uint16).copy()
    cleaned_confidence[supported] = max(threshold + dc.INCREMENTAL_REPLACE_DELTA, 0.0)
    cleaned_depth[supported] = np.clip(
        np.rint(depth_sum[supported] / np.maximum(support_count[supported], 1.0)),
        0,
        max(0, int(np.max(depth_map))),
    ).astype(np.uint16)
    return cleaned_confidence.astype(np.float32, copy=False), cleaned_depth


def reference_confidence_background_composite(
    image: np.ndarray,
    background: np.ndarray,
    confidence: np.ndarray,
    score_threshold: int,
    *,
    id_map: np.ndarray | None = None,
) -> np.ndarray:
    """Blend low-confidence pixels with the Reference final composite formula."""
    level = int(np.clip(score_threshold, 0, dc.MINIMUM_SCORE_MAX))
    if level <= 0:
        return image.astype(np.float32, copy=False)
    threshold = dc.minimum_score_threshold_unit(level)
    confidence = confidence.astype(np.float32, copy=False)
    current_weight = np.ones_like(confidence, dtype=np.float32)
    low = confidence <= threshold
    if id_map is not None:
        id_byte = np.rint(np.clip(id_map, 0.0, 1.0) * dc.BYTE_MAX).astype(np.uint8)
        # Fully confident id bytes preserve directly selected detail.
        low &= id_byte != dc.BYTE_MAX_INT
    if np.any(low):
        current_weight[low] = np.clip(
            (confidence[low] * dc.FINAL_COMPOSITE_CURRENT_NUMERATOR)
            / np.maximum(threshold + confidence[low], 1e-6),
            0.0,
            1.0,
        )
    if image.ndim == 3:
        current_weight = current_weight[..., None]
    return (image * current_weight + background * (1.0 - current_weight)).astype(
        np.float32, copy=False
    )


def reference_suppression_id_blend(
    id_map: np.ndarray,
    support_id_map: np.ndarray,
    score_threshold: int,
) -> np.ndarray:
    """Blend the combined id byte toward the support id."""
    suppression = int(np.clip(score_threshold, 0, dc.MINIMUM_SCORE_MAX))
    if suppression <= 0 or id_map.shape != support_id_map.shape:
        return id_map.astype(np.float32, copy=False)
    source = np.rint(np.clip(id_map, 0.0, 1.0) * dc.BYTE_MAX).astype(np.uint16)
    support = np.rint(np.clip(support_id_map, 0.0, 1.0) * dc.BYTE_MAX).astype(np.uint16)
    blended = source.copy()
    if source.shape[0] > 30 and source.shape[1] > 30:
        inner = np.s_[15:-15, 15:-15]
        blended[inner] = (
            source[inner].astype(np.uint32) * np.uint32(100 - suppression)
            + support[inner].astype(np.uint32) * np.uint32(suppression)
            + 50
        ) // 100
    return (np.clip(blended, 0, dc.BYTE_MAX_INT).astype(np.float32) / dc.BYTE_MAX).astype(
        np.float32,
        copy=False,
    )


def reference_suppression_buffer_blend(
    image: np.ndarray,
    support_image: np.ndarray,
    score_threshold: int,
) -> np.ndarray:
    """Blend the final stack toward the support buffer."""
    suppression = int(np.clip(score_threshold, 0, dc.MINIMUM_SCORE_MAX))
    if suppression <= 0:
        return image.astype(np.float32, copy=False)
    support = np.asarray(support_image, dtype=np.float32)
    if support.shape != image.shape:
        return image.astype(np.float32, copy=False)
    support_weight = suppression / dc.SUPPRESSION_PERCENT_DENOMINATOR
    image_weight = 1.0 - support_weight
    return (image * image_weight + support * support_weight).astype(np.float32, copy=False)


def clean_depth_map_by_confidence(
    depth_map: np.ndarray,
    scores: np.ndarray,
    confidence: np.ndarray,
    score_threshold: int,
    region_bias: int,
    cleanup_unsupported: bool = True,
) -> np.ndarray:
    """Remove unsupported focus islands and optionally grow supported regions."""
    level = int(np.clip(score_threshold, 0, 29))
    if level < 2:
        return depth_map
    threshold = min(0.34, (level * 3.0) / 255.0)
    cleanup_radius = int(np.clip(2 + level // 7, 2, 6))
    cleaned = _propagate_depth_with_neighbor_support(
        depth_map,
        scores,
        confidence,
        radius=cleanup_radius,
        threshold=threshold,
        grow=False,
        cleanup_unsupported=cleanup_unsupported,
    )
    if region_bias == 0:
        return cleaned
    return _propagate_depth_with_neighbor_support(
        cleaned,
        scores,
        confidence,
        radius=abs(int(np.clip(region_bias, -10, 10))),
        threshold=threshold,
        grow=region_bias > 0,
        cleanup_unsupported=cleanup_unsupported,
    )


def _propagate_depth_with_neighbor_support(
    depth_map: np.ndarray,
    scores: np.ndarray,
    confidence: np.ndarray,
    radius: int,
    threshold: float,
    grow: bool,
    cleanup_unsupported: bool = True,
) -> np.ndarray:
    radius = int(np.clip(radius, 1, 10))
    kernel = _circular_kernel(radius)
    kernel3 = kernel[None, :, :].astype(np.float32)
    support = confidence >= threshold
    frame_labels = np.arange(scores.shape[0], dtype=np.uint16)[:, None, None]
    depth_support = depth_map[None, ...] == frame_labels
    if grow:
        adjusted = np.asarray(depth_map, dtype=np.uint16).copy()
        max_scores = np.maximum(np.max(scores, axis=0), 1e-12)
        neighbor_counts = ndimage.convolve(
            depth_support.astype(np.float32),
            kernel3,
            mode="reflect",
        )
        candidates = np.logical_and(neighbor_counts > 0, ~depth_support)
        stronger = scores >= max_scores[None, ...] * 0.9
        supported = np.logical_or(support, confidence >= threshold * 0.5)
        candidate_scores = np.where(
            candidates & stronger & supported[None, ...],
            neighbor_counts * np.maximum(scores, 1e-6),
            0.0,
        )
        replacement_score = np.max(candidate_scores, axis=0)
        replacement = np.asarray(np.argmax(candidate_scores, axis=0), dtype=np.uint16)
        replace = replacement_score > 0
        adjusted[replace] = replacement[replace]
        return adjusted.astype(np.uint16, copy=False)
    support_count = ndimage.convolve(
        support.astype(np.float32), kernel.astype(np.float32), mode="reflect"
    )
    required = 2.0 if radius <= 2 else 3.0
    adjusted = np.asarray(depth_map, dtype=np.uint16).copy()
    votes = ndimage.convolve(
        depth_support.astype(np.float32) * support[None, ...] * np.maximum(confidence, 0.05),
        kernel3,
        mode="reflect",
    )
    replacement = np.asarray(np.argmax(votes, axis=0), dtype=np.uint16)
    replacement_score = np.max(votes, axis=0)
    replace = support_count < required
    if cleanup_unsupported:
        replace = np.logical_or(~support, replace)
    replace = np.logical_and(replace, replacement_score > 0)
    adjusted[replace] = replacement[replace]
    return adjusted.astype(np.uint16, copy=False)


def _circular_kernel(radius: int) -> np.ndarray:
    y, x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    kernel = (x * x + y * y) <= radius * radius
    kernel[radius, radius] = False
    return kernel.astype(np.uint8)


def enforce_depth_map(scores: np.ndarray, depth_map: np.ndarray) -> np.ndarray:
    """Bias scores so soft weights respect a post-processed depth map."""
    adjusted = np.array(scores, copy=True)
    max_score = np.maximum(np.max(adjusted, axis=0), 1e-12)
    for frame in range(adjusted.shape[0]):
        mask = depth_map == frame
        adjusted[frame, mask] = np.maximum(adjusted[frame, mask], max_score[mask] * 1.15)
    return adjusted.astype(np.float32, copy=False)


def effective_blend_softness(params: FocusStackParameters) -> float:
    """Use harder winner selection for high-pass/fixed filtering."""
    base = max(params.blend_softness, 1e-3)
    level_factor = 1.0 + (np.clip(params.detail_scale, 1, 10) - 1) * 0.08
    smart_factor = 0.95 if params.adaptive_weighting else 0.65
    return float(base * level_factor * smart_factor)


def focus_weights(scores: np.ndarray, softness: float) -> np.ndarray:
    """Convert focus scores to smooth per-frame blend weights."""
    scale = max(float(np.std(scores)), 1e-6) * max(softness, 1e-3)
    normalized = (scores - np.max(scores, axis=0, keepdims=True)) / scale
    exp_scores = np.exp(np.clip(normalized, -60.0, 0.0))
    total = np.sum(exp_scores, axis=0, keepdims=True)
    return (exp_scores / np.maximum(total, 1e-12)).astype(np.float32)


def blend_low_confidence_background(
    blended: np.ndarray,
    images: list[np.ndarray],
    scores: np.ndarray,
    score_threshold: int,
    background_mode: BackgroundMode = BackgroundMode.MEDIAN,
    confidence: np.ndarray | None = None,
    structure: np.ndarray | None = None,
    background: np.ndarray | None = None,
) -> np.ndarray:
    """Blend weak-focus pixels toward a stable background reference."""
    level = int(np.clip(score_threshold, 0, 29))
    if level <= 0 or len(images) < 2:
        return blended
    confidence = focus_confidence_map(scores) if confidence is None else confidence
    threshold = min(0.34, (level * 3.0) / 255.0)
    if threshold <= 0:
        return blended
    structure = _stack_structure_confidence(images) if structure is None else structure
    current_weight = np.ones_like(confidence, dtype=np.float32)
    weak = confidence < threshold
    low_structure = structure < 0.10
    if not np.any(weak) and not np.any(low_structure):
        return blended
    current_weight[weak] = np.clip(
        (confidence[weak] * 2.0) / np.maximum(threshold + confidence[weak], 1e-6),
        0.0,
        1.0,
    )
    detail_weight = np.clip((structure - threshold * 0.35) / max(threshold * 0.9, 1e-6), 0.0, 1.0)
    current_weight = np.maximum(current_weight, detail_weight.astype(np.float32, copy=False))
    structure_gate = np.clip((structure - 0.10) / 0.24, 0.0, 1.0).astype(
        np.float32, copy=False
    )
    current_weight *= 0.18 + 0.82 * structure_gate
    current_weight = ndimage.gaussian_filter(current_weight, sigma=1.0, mode="reflect")
    background = (
        stable_background_reference(images, background_mode)
        if background is None
        else background
    )
    if np.ndim(current_weight) < np.ndim(blended):
        current_weight = current_weight[..., None]
    return (blended * current_weight + background * (1.0 - current_weight)).astype(
        np.float32, copy=False
    )


def preserve_specimen_detail(
    blended: np.ndarray,
    images: list[np.ndarray],
    weights: np.ndarray,
    params: FocusStackParameters,
    structure: np.ndarray | None = None,
) -> np.ndarray:
    """Restore high-confidence specimen texture from the dominant source frame."""
    if len(images) < 2:
        return blended
    confidence = np.max(weights, axis=0).astype(np.float32, copy=False)
    structure = _stack_structure_confidence(images) if structure is None else structure
    detail_gate = np.clip((structure - 0.18) / 0.42, 0.0, 1.0)
    confidence_gate = np.clip((confidence - 0.52) / 0.34, 0.0, 1.0)
    detail_strength = 0.16 + int(np.clip(params.detail_scale, 1, 10)) * 0.028
    mix = np.clip(detail_gate * confidence_gate * detail_strength, 0.0, 0.42)
    if not np.any(mix > 0):
        return blended
    source_stack = np.stack(images, axis=0).astype(np.float32, copy=False)
    dominant = np.argmax(weights, axis=0)
    if source_stack.ndim == 4:
        source_pixels = np.take_along_axis(
            source_stack, dominant[None, ..., None], axis=0
        )[0]
        mix = mix[..., None]
    else:
        source_pixels = np.take_along_axis(source_stack, dominant[None, ...], axis=0)[0]
    return (blended * (1.0 - mix) + source_pixels * mix).astype(np.float32, copy=False)


def apply_custom_detail_filter(
    image: np.ndarray,
    selected: np.ndarray,
    confidence: np.ndarray,
    structure: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Apply filter-controlled local contrast only where the stack has real structure."""
    detail_level = int(np.clip(params.detail_scale, dc.FIXED_FILTER_MIN, dc.FIXED_FILTER_MAX))
    scale_preset = int(np.clip(params.scale_preset, dc.FILTER_SET_MIN, dc.FILTER_SET_MAX))
    source = (
        reference_fixed_filter_blend(selected, detail_level)
        if not params.adaptive_weighting
        else selected
    )
    sigma = 0.45 + detail_level * 0.12 + scale_preset * 0.04
    base = _gaussian_image(source, sigma=sigma)
    detail = source - base
    structure_gate = np.clip((structure - 0.12) / 0.36, 0.0, 1.0)
    confidence_gate = np.clip((confidence - 0.08) / 0.42, 0.0, 1.0)
    strength = 0.18 + (11 - detail_level) * 0.025 + scale_preset * 0.018
    gate = np.clip(structure_gate * confidence_gate * strength, 0.0, 0.45)
    if image.ndim == 3:
        gate = gate[..., None]
    enhanced = image + detail * gate
    source_mix = np.clip(gate * 0.55, 0.0, 0.25)
    return (enhanced * (1.0 - source_mix) + source * source_mix).astype(
        np.float32, copy=False
    )


def reference_output_color_response(image: np.ndarray) -> np.ndarray:
    """Return the final Custom image without extra cross-channel color remapping.

    The reference stacker writes the already WIC-rendered source colors through
    byte image buffers. The previous fitted RGB matrix was useful only while RAW
    frames entered BioPic through a different rawpy pipeline; with WIC input it
    double-corrects colors and can suppress green specimen detail.
    """
    array = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    return _quantize_unit(array)


def reference_fixed_filter_blend(image: np.ndarray, detail_level: int) -> np.ndarray:
    """Approximate the Reference three-buffer fixed filter using exact UI weights."""
    w_high, w_mid, w_low = reference_fixed_filter_weights(detail_level)
    if w_high == 255 and w_mid == 0 and w_low == 0:
        return image.astype(np.float32, copy=False)
    high = image.astype(np.float32, copy=False)
    mid = reference_neighbor_smooth(high)
    low = reference_neighbor_smooth(mid)
    return ((high * w_high + mid * w_mid + low * w_low) / dc.BYTE_MAX).astype(
        np.float32, copy=False
    )


def reference_neighbor_smooth(image: np.ndarray, use_cuda: bool = False) -> np.ndarray:
    """Use the 8-neighbor smoothing stencil."""
    kernel = np.array(
        [[3.0, 4.0, 3.0], [4.0, 0.0, 4.0], [3.0, 4.0, 3.0]],
        dtype=np.float32,
    )
    kernel /= float(np.sum(kernel))
    if image.ndim == 2:
        return _filter2d_accelerated(
            image.astype(np.float32, copy=False),
            kernel,
            borderType=cv2.BORDER_REFLECT,
            use_cuda=use_cuda,
        )
    return _filter2d_accelerated(
        image.astype(np.float32, copy=False),
        kernel,
        borderType=cv2.BORDER_REFLECT,
        use_cuda=use_cuda,
    ).astype(np.float32, copy=False)


def reference_fixed_filter_weights(detail_level: int) -> tuple[int, int, int]:
    """Return fixed-filter weights for high/mid/low detail buffers."""
    level = int(np.clip(detail_level, dc.FIXED_FILTER_MIN, dc.FIXED_FILTER_MAX))
    if level == 1:
        return 255, 0, 0
    if 2 <= level <= 5:
        high = level * -0x40 + 0x140
        return high, 255 - high, 0
    if 6 <= level <= 9:
        high = (level - 5) * -0x1E + 0x78
        low = (level - 5) * 0x32
        return high, 255 - (high + low), low
    return 0, 0, 255


def suppress_custom_background_grain(
    image: np.ndarray,
    background: np.ndarray,
    confidence: np.ndarray,
    structure: np.ndarray,
) -> np.ndarray:
    """Stabilize flat Custom-stack regions before detail enhancement."""
    flat_gate = np.clip((0.26 - structure) / 0.22, 0.0, 1.0)
    uncertain_gate = np.clip((0.62 - confidence) / 0.48, 0.0, 1.0)
    mix = np.maximum(flat_gate * 0.82, flat_gate * uncertain_gate)
    mix = ndimage.gaussian_filter(mix.astype(np.float32, copy=False), sigma=1.2, mode="reflect")
    if image.ndim == 3:
        mix = mix[..., None]
    return (image * (1.0 - mix) + background * mix).astype(np.float32, copy=False)
def _take_pixels_by_depth(images: list[np.ndarray], depth_map: np.ndarray) -> np.ndarray:
    stack = np.stack(images, axis=0).astype(np.float32, copy=False)
    if stack.ndim == 4:
        return np.take_along_axis(stack, depth_map[None, ..., None], axis=0)[0]
    return np.take_along_axis(stack, depth_map[None, ...], axis=0)[0]


def _one_hot_depth_weights(depth_map: np.ndarray, frame_count: int) -> np.ndarray:
    frame_labels = np.arange(frame_count, dtype=np.uint16)[:, None, None]
    return (depth_map[None, ...] == frame_labels).astype(np.float32, copy=False)
@dataclass(frozen=True, slots=True)
class _PyramidStack:
    image: np.ndarray
    depth_map: np.ndarray
    focus_map: np.ndarray
    weights: np.ndarray
def stable_background_reference(
    images: list[np.ndarray], mode: BackgroundMode = BackgroundMode.MEDIAN
) -> np.ndarray:
    """Build a smooth reference for low-texture regions of a stack."""
    if mode is BackgroundMode.FIRST:
        background = np.asarray(images[0], dtype=np.float32)
    elif mode is BackgroundMode.LAST:
        background = np.asarray(images[-1], dtype=np.float32)
    else:
        stack = np.stack(images, axis=0).astype(np.float32, copy=False)
        if mode is BackgroundMode.MIXED:
            background = np.median(stack, axis=0) * 0.6 + np.mean(stack, axis=0) * 0.4
        elif mode in {BackgroundMode.DARKEST, BackgroundMode.BRIGHTEST}:
            luminance = np.stack([to_luminance(image) for image in stack], axis=0)
            chooser = (
                np.argmin(luminance, axis=0)
                if mode is BackgroundMode.DARKEST
                else np.argmax(luminance, axis=0)
            )
            if stack.ndim == 4:
                background = np.take_along_axis(stack, chooser[None, ..., None], axis=0)[0]
            else:
                background = np.take_along_axis(stack, chooser[None, ...], axis=0)[0]
        else:
            background = np.median(stack, axis=0)
    background = background.astype(np.float32, copy=False)
    sigma = (0.9, 0.9) if background.ndim == 2 else (0.9, 0.9, 0.0)
    return ndimage.gaussian_filter(background, sigma=sigma, mode="reflect").astype(
        np.float32, copy=False
    )


class _referenceBackgroundBuilder:
    """Incrementally build the Custom background while frames are already being scanned."""

    def __init__(self, first_image: np.ndarray, mode: BackgroundMode) -> None:
        self.mode = mode
        first = np.asarray(first_image, dtype=np.float32)
        self._first = first
        self._last = first
        self._sum: np.ndarray | None = None
        self._min_luminance: np.ndarray | None = None
        self._max_luminance: np.ndarray | None = None
        self._darkest: np.ndarray | None = None
        self._brightest: np.ndarray | None = None
        self._count = 0

    def add(self, frame: np.ndarray, luminance: np.ndarray) -> None:
        source = np.asarray(frame, dtype=np.float32)
        gray = np.asarray(luminance, dtype=np.float32)
        self._last = source
        self._count += 1
        if self.mode in {BackgroundMode.FIRST, BackgroundMode.LAST}:
            return
        if self.mode not in {
            BackgroundMode.MIXED,
            BackgroundMode.DARKEST,
            BackgroundMode.BRIGHTEST,
        }:
            if self._sum is None:
                self._sum = np.zeros_like(source, dtype=np.float32)
            self._sum += source
            return
        if self._min_luminance is None:
            self._min_luminance = gray.copy()
            self._max_luminance = gray.copy()
            self._darkest = source.copy()
            self._brightest = source.copy()
            return
        darker = gray < self._min_luminance
        brighter = gray > self._max_luminance
        if np.any(darker):
            self._min_luminance[darker] = gray[darker]
            if source.ndim == 3:
                self._darkest[darker, :] = source[darker, :]
            else:
                self._darkest[darker] = source[darker]
        if np.any(brighter):
            self._max_luminance[brighter] = gray[brighter]
            if source.ndim == 3:
                self._brightest[brighter, :] = source[brighter, :]
            else:
                self._brightest[brighter] = source[brighter]

    def result(self) -> np.ndarray:
        if self.mode is BackgroundMode.FIRST:
            return self._first.astype(np.float32, copy=False)
        if self.mode is BackgroundMode.LAST:
            return self._last.astype(np.float32, copy=False)
        if self.mode is BackgroundMode.DARKEST and self._darkest is not None:
            return self._darkest.astype(np.float32, copy=False)
        if self.mode is BackgroundMode.BRIGHTEST and self._brightest is not None:
            return self._brightest.astype(np.float32, copy=False)
        if (
            self.mode is BackgroundMode.MIXED
            and self._darkest is not None
            and self._brightest is not None
        ):
            return ((self._darkest + self._brightest) * 0.5).astype(np.float32, copy=False)
        if self._sum is not None and self._count > 0:
            return (self._sum / float(self._count)).astype(np.float32, copy=False)
        return self._first.astype(np.float32, copy=False)


def reference_background_reference(
    images: list[np.ndarray], mode: BackgroundMode = BackgroundMode.MIXED
) -> np.ndarray:
    """Build the Custom background from running dark/bright/average buffers."""
    if not images:
        raise ValueError("images must not be empty")
    builder = _referenceBackgroundBuilder(images[0], mode)
    for image in images:
        frame = np.asarray(image, dtype=np.float32)
        builder.add(frame, reference_luminance(frame))
    return builder.result()


def _take_pixels_from_stack(stack: np.ndarray, chooser: np.ndarray) -> np.ndarray:
    if stack.ndim == 4:
        return np.take_along_axis(stack, chooser[None, ..., None], axis=0)[0]
    return np.take_along_axis(stack, chooser[None, ...], axis=0)[0]


def _stack_structure_confidence(images: list[np.ndarray]) -> np.ndarray:
    """Estimate where source images contain real specimen structure."""
    gray_stack = np.stack(
        [to_luminance(image).astype(np.float32, copy=False) for image in images],
        axis=0,
    )
    smooth = ndimage.gaussian_filter(gray_stack, sigma=(0.0, 2.0, 2.0), mode="reflect")
    structure = np.abs(gray_stack - smooth)
    structure = ndimage.gaussian_filter(structure, sigma=(0.0, 0.7, 0.7), mode="reflect")
    structure_map = np.max(structure, axis=0)
    high = float(np.percentile(structure_map, 98.0))
    if high <= 1e-12:
        return np.zeros_like(structure_map, dtype=np.float32)
    return np.clip(structure_map / high, 0.0, 1.0).astype(np.float32, copy=False)


def _normalize_scores(scores: np.ndarray) -> np.ndarray:
    shifted = scores - np.min(scores)
    high = float(np.percentile(shifted, 99.5))
    if high <= 1e-12:
        return np.zeros_like(scores, dtype=np.float32)
    return np.clip(shifted / high, 0.0, 1.0).astype(np.float32, copy=False)


def _low_confidence_measure(scores: np.ndarray) -> np.ndarray:
    normalized = _normalize_scores(scores)
    peak = np.max(normalized, axis=0)
    margin = peak - np.partition(normalized, -2, axis=0)[-2] if scores.shape[0] > 1 else peak
    return np.minimum(peak, margin * 2.0).astype(np.float32, copy=False)


def _normalized_score_span(scores: np.ndarray) -> np.ndarray:
    span = np.max(scores, axis=0) - np.mean(scores, axis=0)
    high = float(np.percentile(span, 99.0))
    if high <= 1e-12:
        return np.zeros_like(span, dtype=np.float32)
    return np.clip(span / high, 0.0, 1.0).astype(np.float32, copy=False)


def _shift_map_constant(values: np.ndarray, dy: int, dx: int, fill: float) -> np.ndarray:
    shifted = np.full(values.shape, fill, dtype=np.float32)
    height, width = values.shape
    src_y0 = max(0, -dy)
    src_y1 = min(height, height - dy)
    dst_y0 = max(0, dy)
    dst_y1 = min(height, height + dy)
    src_x0 = max(0, -dx)
    src_x1 = min(width, width - dx)
    dst_x0 = max(0, dx)
    dst_x1 = min(width, width + dx)
    if src_y1 > src_y0 and src_x1 > src_x0:
        shifted[dst_y0:dst_y1, dst_x0:dst_x1] = values[src_y0:src_y1, src_x0:src_x1]
    return shifted


def _fill_unassigned_depths(depth_map: np.ndarray, scores: np.ndarray) -> np.ndarray:
    unassigned = depth_map < 0
    if not np.any(unassigned):
        return depth_map
    filled = np.array(depth_map, copy=True)
    valid = filled >= 0
    if np.any(valid):
        _distances, indices = ndimage.distance_transform_edt(~valid, return_indices=True)
        filled[unassigned] = filled[tuple(index[unassigned] for index in indices)]
        return filled
    fallback = np.asarray(np.argmax(scores, axis=0), dtype=np.uint16)
    filled[unassigned] = fallback[unassigned]
    return filled


def blend_stack(images: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    """Blend aligned images with per-frame weights."""
    stack = np.stack(images, axis=0).astype(np.float32, copy=False)
    if stack.ndim == 4:
        return np.sum(stack * weights[..., None], axis=0)
    return np.sum(stack * weights, axis=0)


def suppress_halos(
    blended: np.ndarray, images: list[np.ndarray], weights: np.ndarray, sigma: float
) -> np.ndarray:
    """Suppress halos by nudging uncertain pixels toward the dominant source frame."""
    confidence = np.max(weights, axis=0)
    dominant = np.argmax(weights, axis=0)
    source_stack = np.stack(images, axis=0).astype(np.float32, copy=False)
    if source_stack.ndim == 4:
        dominant_pixels = np.take_along_axis(
            source_stack, dominant[None, ..., None], axis=0
        )[0]
    else:
        dominant_pixels = np.take_along_axis(source_stack, dominant[None, ...], axis=0)[0]
    smoothed_confidence = ndimage.gaussian_filter(confidence, sigma=sigma, mode="reflect")
    mix = np.clip(1.0 - smoothed_confidence, 0.0, 0.35)
    if np.ndim(mix) < np.ndim(blended):
        mix = mix[..., None]
    return blended * (1.0 - mix) + dominant_pixels * mix


def _validate_images(images: list[np.ndarray]) -> None:
    if not images:
        raise ValueError("at least one image is required")
    shape = np.asarray(images[0]).shape
    for index, image in enumerate(images):
        if np.asarray(image).shape != shape:
            raise ValueError(f"image {index} has shape {np.asarray(image).shape}; expected {shape}")


def auto_orient_stack_images(images: list[np.ndarray]) -> list[np.ndarray]:
    """Rotate frames with swapped width/height so they match the reference frame."""
    if not images:
        return images
    reference = np.asarray(images[0])
    oriented = [reference]
    for image in images[1:]:
        array = np.asarray(image)
        if array.shape == reference.shape:
            oriented.append(array)
            continue
        if _is_rotated_reference_shape(array.shape, reference.shape):
            oriented.append(_best_right_angle_rotation(reference, array))
            continue
        oriented.append(array)
    return oriented


def _is_rotated_reference_shape(shape: tuple[int, ...], reference_shape: tuple[int, ...]) -> bool:
    if len(shape) != len(reference_shape) or len(shape) < 2:
        return False
    return (
        shape[0] == reference_shape[1]
        and shape[1] == reference_shape[0]
        and shape[2:] == reference_shape[2:]
    )


def _best_right_angle_rotation(reference: np.ndarray, image: np.ndarray) -> np.ndarray:
    candidates = [np.rot90(image, 1, axes=(0, 1)), np.rot90(image, -1, axes=(0, 1))]
    reference_preview = _orientation_preview(reference)
    return min(candidates, key=lambda candidate: _orientation_score(reference_preview, candidate))


def _orientation_score(reference_preview: np.ndarray, candidate: np.ndarray) -> float:
    candidate_preview = _orientation_preview(candidate)
    return float(np.mean(np.abs(reference_preview - candidate_preview)))


def _orientation_preview(image: np.ndarray, max_size: int = 256) -> np.ndarray:
    gray = to_luminance(image).astype(np.float32, copy=False)
    scale = min(1.0, max_size / max(gray.shape))
    if scale < 1.0:
        gray = ndimage.zoom(gray, zoom=(scale, scale), order=1, prefilter=False)
    low, high = np.percentile(gray, [1.0, 99.0])
    if float(high - low) <= 1e-8:
        return np.zeros(gray.shape, dtype=np.float32)
    return np.clip((gray - low) / float(high - low), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )


def _as_float_image(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if np.issubdtype(array.dtype, np.floating):
        return array.astype(np.float32, copy=False)
    info = np.iinfo(array.dtype) if np.issubdtype(array.dtype, np.integer) else None
    if info is None:
        return array.astype(np.float32, copy=False)
    return array.astype(np.float32) / float(info.max)


def _restore_dtype(image: np.ndarray, dtype: np.dtype) -> np.ndarray:
    target = np.dtype(dtype)
    if np.issubdtype(target, np.floating):
        return image.astype(target, copy=False)
    info = np.iinfo(target)
    return np.clip(image * float(info.max), info.min, info.max).astype(target)


def _resize_preview(image: np.ndarray, scale: float) -> np.ndarray:
    if scale >= 0.999:
        return np.asarray(image)
    if not 0 < scale <= 1:
        raise ValueError("preview_scale must be greater than 0 and at most 1")
    array = np.asarray(image)
    height, width = array.shape[:2]
    target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(array, target, interpolation=cv2.INTER_AREA)


def _emit(progress: ProgressCallback | None, message: str, fraction: float) -> None:
    if progress is not None:
        progress(message, fraction)


def _emit_preview(
    preview: PreviewCallback | None,
    image: np.ndarray,
    label: str,
    max_size: int = 1200,
) -> None:
    if preview is None:
        return
    array = np.asarray(image)
    scale = min(1.0, max_size / max(array.shape[:2]))
    display = _resize_preview(array, scale) if scale < 1.0 else array
    preview(np.asarray(display).copy(), label)
