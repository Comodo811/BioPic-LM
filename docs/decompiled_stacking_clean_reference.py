"""
Clean reference translation of the decompiled stacking path.

Source files:
- decomp.txt
- docs/decompiled_stacking_core_functions.c

This is not original source code. It is a readable translation of the Ghidra
output used as the implementation target for BioPic's Custom stacking mode.
Names are inferred from call order, UI offsets and image-buffer use.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage


MINIMUM_SCORE_TO_BYTE = 3
FILTER_BLEND_DENOMINATOR = 255
RGB_TO_GRAY_WEIGHTS = np.array([0x36, 0x78, 0x51], dtype=np.float32) / 255.0
DETAIL_SMOOTH_KERNEL = np.array(
    [[3.0, 4.0, 3.0], [4.0, 0.0, 4.0], [3.0, 4.0, 3.0]],
    dtype=np.float32,
) / 28.0
DETAIL_SCORE_KERNEL = np.array(
    [[2.0, 3.0, 2.0], [3.0, 4.0, 3.0], [2.0, 3.0, 2.0]],
    dtype=np.float32,
)


def fixed_filter_weights(filter_fixed: int) -> tuple[int, int, int]:
    """FUN_008c1050 fixed filter table."""
    value = int(np.clip(filter_fixed, 1, 10))
    if value == 1:
        return 255, 0, 0
    if 2 <= value <= 5:
        high = value * -0x40 + 0x140
        return high, 255 - high, 0
    if 6 <= value <= 9:
        high = (value - 5) * -0x1E + 0x78
        low = (value - 5) * 0x32
        return high, 255 - (high + low), low
    return 0, 0, 255


def minimum_score_threshold(minimum_score: int) -> int:
    """UI minimum score/noise suppression value to internal 8-bit score."""
    return int(np.clip(minimum_score, 0, 29)) * MINIMUM_SCORE_TO_BYTE


def rgb_to_gray(source_rgb: np.ndarray) -> np.ndarray:
    """FUN_008644a0: weighted grayscale used before focus scoring."""
    if source_rgb.ndim == 2:
        return source_rgb.astype(np.float32, copy=False)
    return np.tensordot(source_rgb[..., :3], RGB_TO_GRAY_WEIGHTS, axes=([-1], [0]))


def smooth_and_detail(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """FUN_0085ec00: center-excluding neighbor smooth and absolute residual."""
    smooth = ndimage.convolve(gray.astype(np.float32), DETAIL_SMOOTH_KERNEL, mode="reflect")
    detail = np.abs(gray.astype(np.float32) - smooth)
    return smooth, detail


def detail_to_score(detail: np.ndarray, channel: int, contrast_gain: float = 1.0) -> np.ndarray:
    """FUN_0085ee70: local support followed by the saturating 8-bit score curve."""
    support = ndimage.convolve(detail.astype(np.float32), DETAIL_SCORE_KERNEL, mode="reflect")
    channel_gain = (1.0, 1.16, 1.34)[channel]
    value = support * contrast_gain * channel_gain * 255.0
    return np.clip(value / (value + 128.0), 0.0, 1.0)


def build_three_score_channels(source_rgb: np.ndarray, filter_set: int) -> np.ndarray:
    """FUN_0085f120: create high/mid/low detail score channels."""
    preset = int(np.clip(filter_set, 1, 5))
    gray = rgb_to_gray(source_rgb)
    working = downscale_average(gray, 2) if preset > 4 else gray

    smooth_0, detail_0 = smooth_and_detail(working)
    working = next_score_scale(smooth_0, preset)
    smooth_1, detail_1 = smooth_and_detail(working)
    working = next_score_scale(smooth_1, preset)
    _smooth_2, detail_2 = smooth_and_detail(working)

    scores = [
        resize_map(detail_to_score(detail_0, 0), gray.shape),
        resize_map(detail_to_score(detail_1, 1), gray.shape),
        resize_map(detail_to_score(detail_2, 2), gray.shape),
    ]
    return wide_channel_smooth(np.stack(scores, axis=0), preset)


def next_score_scale(image: np.ndarray, filter_set: int) -> np.ndarray:
    """FUN_0085f120 scale transitions before score channels 1 and 2."""
    if filter_set in (1, 3):
        return downscale_average(image, 2)
    if filter_set in (2, 4, 5):
        return downscale_average(image, 3)
    return image


def update_running_buffers(
    source_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    depth_buffers: np.ndarray,
    frame_rgb: np.ndarray,
    score_channels: np.ndarray,
    frame_index: int,
) -> None:
    """FUN_008c1ac0: update high/mid/low source, confidence and depth buffers."""
    old_weight_coefficients = np.array([0x33, 0x40, 0x55], dtype=np.float32) / 255.0
    for channel, coefficient in enumerate(old_weight_coefficients):
        new_score = score_channels[channel]
        old_score = confidence_buffers[channel]
        replace = new_score > old_score + (1.0 / 255.0)
        old_mix = np.zeros_like(new_score, dtype=np.float32)
        old_mix[replace] = np.clip(
            (old_score[replace] * coefficient) / np.maximum(new_score[replace], 1e-6),
            0.0,
            1.0,
        )
        mix = old_mix[..., None] if frame_rgb.ndim == 3 else old_mix
        source_buffers[channel] = source_buffers[channel] * mix + frame_rgb * (1.0 - mix)
        confidence_buffers[channel] = old_score * old_mix + new_score * (1.0 - old_mix)
        depth_buffers[channel] = depth_buffers[channel] * old_mix + frame_index * (1.0 - old_mix)


def combine_detail_buffers(
    source_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    smart_filter: bool,
    fixed_filter: int,
) -> tuple[np.ndarray, np.ndarray]:
    """FUN_008c1050: merge high/mid/low source buffers and confidence/id maps."""
    if smart_filter:
        weights = confidence_buffers / np.maximum(
            np.sum(confidence_buffers, axis=0, keepdims=True), 1e-6
        )
    else:
        weights = np.array(fixed_filter_weights(fixed_filter), dtype=np.float32) / 255.0
        weights = weights[:, None, None]
    image_weights = weights[..., None] if source_buffers.ndim == 4 else weights
    image = np.sum(source_buffers * image_weights, axis=0)
    confidence = np.sum(confidence_buffers * weights, axis=0)
    return image, confidence


def patch_adjust(
    confidence: np.ndarray,
    depth: np.ndarray,
    minimum_score: int,
    patch_adjustment: int,
) -> tuple[np.ndarray, np.ndarray]:
    """FUN_008c3240: negative narrows patches, positive widens patches."""
    radius = abs(int(np.clip(patch_adjustment, -10, 10)))
    if radius == 0:
        return confidence, depth
    threshold = minimum_score_threshold(minimum_score) / 255.0
    kernel = circular_kernel(radius)
    strong = confidence >= threshold
    out_confidence = confidence.copy()
    out_depth = depth.copy()
    if patch_adjustment < 0:
        weak_support = ndimage.convolve((~strong).astype(np.float32), kernel)
        shrink = strong & (weak_support > 0)
        out_confidence[shrink] = max(0.0, threshold - 1.0 / 255.0)
    else:
        strong_support = ndimage.convolve(strong.astype(np.float32), kernel)
        grow = (~strong) & (strong_support > 0)
        out_confidence[grow] = min(1.0, threshold + 1.0 / 255.0)
    return out_confidence, out_depth


def ring_supported_cleanup(
    confidence: np.ndarray,
    depth: np.ndarray,
    minimum_score: int,
) -> tuple[np.ndarray, np.ndarray]:
    """FUN_008c37b0: replace isolated low-confidence pixels by sparse ring support."""
    threshold = minimum_score_threshold(minimum_score) / 255.0
    rings = (
        ((-2, 0), (-1, 1), (0, 2), (1, 1), (2, 0), (1, -1), (0, -2), (-1, -1)),
        ((-3, 0), (-2, 2), (0, 3), (2, 2), (3, 0), (2, -2), (0, -3), (-2, -2)),
        ((-6, 0), (-4, 4), (0, 6), (4, 4), (6, 0), (4, -4), (0, -6), (-4, -4)),
        ((-9, 0), (-6, 6), (0, 9), (6, 6), (9, 0), (6, -6), (0, -9), (-6, -6)),
    )
    count = np.zeros_like(confidence, dtype=np.float32)
    depth_sum = np.zeros_like(confidence, dtype=np.float32)
    for ring in rings:
        for dy, dx in ring:
            shifted_conf = shift_constant(confidence, dy, dx, 0.0)
            strong = shifted_conf > threshold
            count += strong
            depth_sum += shift_constant(depth.astype(np.float32), dy, dx, 0.0) * strong
        if np.all(count >= 3):
            break
    supported = count > 1
    out_confidence = confidence.copy()
    out_depth = depth.copy()
    out_confidence[supported] = threshold + 1.0 / 255.0
    out_depth[supported] = np.rint(depth_sum[supported] / np.maximum(count[supported], 1.0))
    return out_confidence, out_depth


def final_background_composite(
    current: np.ndarray,
    background: np.ndarray,
    confidence: np.ndarray,
    minimum_score: int,
) -> np.ndarray:
    """FUN_008c4290: blend low-confidence pixels to the selected background image."""
    threshold = minimum_score_threshold(minimum_score) / 255.0
    current_weight = np.ones_like(confidence, dtype=np.float32)
    low = confidence <= threshold
    current_weight[low] = np.clip(
        (confidence[low] * 2.0) / np.maximum(threshold + confidence[low], 1e-6),
        0.0,
        1.0,
    )
    if current.ndim == 3:
        current_weight = current_weight[..., None]
    return current * current_weight + background * (1.0 - current_weight)


def downscale_average(image: np.ndarray, factor: int) -> np.ndarray:
    """FUN_0085dec0: average 2x2 or 3x3 blocks."""
    height, width = image.shape[:2]
    out_h = max(1, height // factor)
    out_w = max(1, width // factor)
    cropped = image[: out_h * factor, : out_w * factor]
    return cropped.reshape(out_h, factor, out_w, factor).mean(axis=(1, 3))


def resize_map(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """FUN_0085e2a0: bilinear upsample score maps back to full resolution."""
    if image.shape == shape:
        return image.astype(np.float32, copy=False)
    zoom = (shape[0] / image.shape[0], shape[1] / image.shape[1])
    return ndimage.zoom(image.astype(np.float32), zoom, order=1, mode="nearest")


def wide_channel_smooth(scores: np.ndarray, filter_set: int) -> np.ndarray:
    """FUN_0085e4d0: wide per-channel cleanup filter."""
    out = np.empty_like(scores, dtype=np.float32)
    for channel in range(3):
        out[channel] = sparse_wide_smooth(scores[channel], filter_set * (channel + 1))
    return out


def sparse_wide_smooth(values: np.ndarray, step: int) -> np.ndarray:
    """FUN_0085e4d0: exact sparse weights; divisor is 3736."""
    samples = (
        (0x0B, ((-3, -6), (-3, 6), (-2, -9), (-2, 9), (3, -6), (3, 6), (2, -9), (2, 9))),
        (0x18, ((-3, -3), (-3, 3), (-1, -3), (-1, 3), (3, -3), (3, 3), (1, -3), (1, 3))),
        (0x1D, ((-3, 0), (3, 0), (0, -9), (0, 9))),
        (0x2A, ((-2, -6), (-2, 6), (2, -6), (2, 6))),
        (0x5A, ((-2, -3), (-2, 3), (-1, -6), (-1, 6), (1, -6), (1, 6), (2, -3), (2, 3))),
        (0x6D, ((-2, 0), (2, 0), (0, -6), (0, 6))),
        (0xC3, ((-1, -3), (-1, 3), (1, -3), (1, 3))),
        (0xED, ((-1, 0), (1, 0), (0, -3), (0, 3))),
        (0x120, ((0, 0),)),
    )
    source = values.astype(np.float32, copy=False)
    weighted = np.zeros_like(source)
    divisor = 0.0
    for weight, offsets in samples:
        divisor += weight * len(offsets)
        for dy, dx in offsets:
            weighted += shift_constant(source, dy * step, dx * step, 0.0) * weight
    out = source.copy()
    margin = 9 * step
    if source.shape[0] > margin * 2 and source.shape[1] > margin * 2:
        out[margin:-margin, margin:-margin] = weighted[margin:-margin, margin:-margin] / divisor
    return out


def low_score_transition(
    current: np.ndarray,
    mid_detail: np.ndarray,
    background: np.ndarray,
    confidence: np.ndarray,
    minimum_score: int,
) -> tuple[np.ndarray, np.ndarray]:
    """FUN_008c4770: soften low-score pixels before final background composite."""
    threshold = minimum_score_threshold(minimum_score) / 255.0
    low = confidence < threshold
    current_weight = np.zeros_like(confidence, dtype=np.float32)
    current_weight[low] = confidence[low] * 127.0 / max(threshold * 255.0, 1e-6)
    detail_weight = current_weight * 0.5
    background_weight = 1.0 - (current_weight + detail_weight)
    if current.ndim == 3:
        current_weight = current_weight[..., None]
        detail_weight = detail_weight[..., None]
        background_weight = background_weight[..., None]
        low_mask = low[..., None]
    else:
        low_mask = low
    blended = current * current_weight + mid_detail * detail_weight + background * background_weight
    out = np.where(low_mask, blended, current)
    smooth_confidence = ndimage.convolve(confidence, DETAIL_SCORE_KERNEL / 24.0, mode="reflect")
    return out, np.where(low, smooth_confidence, confidence)


def circular_kernel(radius: int) -> np.ndarray:
    y, x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    kernel = (x * x + y * y) <= radius * radius
    kernel[radius, radius] = False
    return kernel.astype(np.float32)


def shift_constant(image: np.ndarray, dy: int, dx: int, fill: float) -> np.ndarray:
    out = np.full_like(image, fill)
    src_y0 = max(0, -dy)
    src_y1 = image.shape[0] - max(0, dy)
    src_x0 = max(0, -dx)
    src_x1 = image.shape[1] - max(0, dx)
    dst_y0 = max(0, dy)
    dst_y1 = dst_y0 + max(0, src_y1 - src_y0)
    dst_x0 = max(0, dx)
    dst_x1 = dst_x0 + max(0, src_x1 - src_x0)
    if dst_y1 > dst_y0 and dst_x1 > dst_x0:
        out[dst_y0:dst_y1, dst_x0:dst_x1] = image[src_y0:src_y1, src_x0:src_x1]
    return out
