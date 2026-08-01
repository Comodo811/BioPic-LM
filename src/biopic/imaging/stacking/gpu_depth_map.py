"""Optional CuPy GPU-resident depth-map focus stacking."""

from __future__ import annotations

from typing import Any

import numpy as np

from biopic.imaging.stacking.focus_metrics import FocusMetric
from biopic.imaging.stacking.gpu_memory import configure_cupy_cache, plan_gpu_memory


def stack_depth_map_gpu(images: list[np.ndarray], parameters: object) -> object | None:
    """Run depth-map stacking mostly on the GPU when CuPy is available."""
    try:
        configure_cupy_cache()
        import cupy as cp
        from cupyx.scipy import ndimage as cndimage
    except Exception:
        return None

    if not getattr(parameters, "use_cuda", False) or not images:
        return None

    try:
        memory_plan = plan_gpu_memory(
            images,
            multiplier=5.5,
            memory_limit_mb=getattr(parameters, "gpu_memory_limit_mb", 4096),
        )
        if not memory_plan.full_frame_possible:
            return _stack_depth_map_gpu_tiled(cp, cndimage, images, parameters, memory_plan)
        return _stack_depth_map_gpu_full(cp, cndimage, images, parameters)
    except Exception:
        return None


def _stack_depth_map_gpu_full(cp: Any, cndimage: Any, images: list[np.ndarray], parameters: object) -> object:
    stack = cp.asarray(np.stack(images, axis=0), dtype=cp.float32)
    scores = _focus_scores(cp, cndimage, stack, parameters.focus_metric, parameters.focus_radius)
    filtered = _filter_focus_scores(cp, cndimage, scores, parameters)
    regularized = _apply_score_threshold(cp, filtered, parameters.score_threshold)
    depth_map_gpu = cp.argmax(regularized, axis=0).astype(cp.uint16)
    confidence = _focus_confidence_map(cp, filtered)
    if parameters.confidence_cleanup and parameters.score_threshold >= 2:
        depth_map_gpu = _clean_depth_map(
            cp,
            cndimage,
            depth_map_gpu,
            regularized,
            confidence,
            parameters.score_threshold,
            parameters.region_bias,
        )
        regularized = _enforce_depth_map(cp, regularized, depth_map_gpu)
    elif parameters.region_bias != 0 and parameters.score_threshold >= 2:
        depth_map_gpu = _adjust_depth_regions(
            cp,
            cndimage,
            depth_map_gpu,
            regularized,
            parameters.region_bias,
        )
        regularized = _enforce_depth_map(cp, regularized, depth_map_gpu)

    weights = _focus_weights(cp, regularized, _effective_blend_softness(parameters))
    image = _blend_stack(cp, stack, weights)
    if parameters.halo_suppression_sigma > 0:
        image = _suppress_halos(cp, cndimage, image, stack, weights, parameters.halo_suppression_sigma)
    structure = _stack_structure_confidence(cp, cndimage, stack)
    image = _blend_low_confidence_background(
        cp,
        cndimage,
        image,
        stack,
        filtered,
        parameters,
        confidence,
        structure,
    )
    image = _preserve_specimen_detail(cp, cndimage, image, stack, weights, parameters, structure)

    from biopic.imaging.stacking import stacker as core

    return core._PyramidStack(
        image=cp.asnumpy(cp.clip(image, 0.0, 1.0)).astype(np.float32, copy=False),
        depth_map=cp.asnumpy(depth_map_gpu).astype(np.uint16, copy=False),
        focus_map=cp.asnumpy(regularized).astype(np.float32, copy=False),
        weights=cp.asnumpy(weights).astype(np.float32, copy=False),
    )


def _stack_depth_map_gpu_tiled(
    cp: Any,
    cndimage: Any,
    images: list[np.ndarray],
    parameters: object,
    memory_plan: object,
) -> object | None:
    height, width = images[0].shape[:2]
    overlap = int(max(16, memory_plan.tile_overlap))
    tile_height = int(max(128, memory_plan.tile_height))
    if tile_height >= height:
        return None
    step = max(1, tile_height - overlap * 2)
    output_shape = images[0].shape
    image_out = np.zeros(output_shape, dtype=np.float32)
    depth_out = np.zeros((height, width), dtype=np.uint16)
    focus_out = np.zeros((len(images), height, width), dtype=np.float32)
    weights_out = np.zeros((len(images), height, width), dtype=np.float32)
    core_start = 0
    while core_start < height:
        core_end = min(height, core_start + step)
        tile_start = max(0, core_start - overlap)
        tile_end = min(height, core_end + overlap)
        tile_images = [np.asarray(image[tile_start:tile_end], dtype=np.float32) for image in images]
        tile_result = _stack_depth_map_gpu_full(cp, cndimage, tile_images, parameters)
        local_start = core_start - tile_start
        local_end = local_start + (core_end - core_start)
        image_out[core_start:core_end] = tile_result.image[local_start:local_end]
        depth_out[core_start:core_end] = tile_result.depth_map[local_start:local_end]
        focus_out[:, core_start:core_end] = tile_result.focus_map[:, local_start:local_end]
        weights_out[:, core_start:core_end] = tile_result.weights[:, local_start:local_end]
        try:
            cp.get_default_memory_pool().free_all_blocks()
        except Exception:
            pass
        core_start = core_end

    from biopic.imaging.stacking import stacker as core

    return core._PyramidStack(
        image=np.clip(image_out, 0.0, 1.0).astype(np.float32, copy=False),
        depth_map=depth_out,
        focus_map=focus_out,
        weights=weights_out,
    )


def gpu_backend_status() -> dict[str, Any]:
    """Return a compact status dictionary for diagnostics/UI."""
    try:
        configure_cupy_cache()
        import cupy as cp
        from cupyx.scipy import ndimage as _cndimage  # noqa: F401
    except Exception as exc:
        return {"available": False, "reason": f"CuPy unavailable: {exc}"}
    try:
        count = int(cp.cuda.runtime.getDeviceCount())
        device = cp.cuda.Device()
        props = cp.cuda.runtime.getDeviceProperties(device.id)
        free, total = cp.cuda.runtime.memGetInfo()
        return {
            "available": count > 0,
            "device_count": count,
            "device_id": int(device.id),
            "device_name": props.get("name", b"").decode(errors="replace"),
            "free_memory_mb": int(free // (1024 * 1024)),
            "total_memory_mb": int(total // (1024 * 1024)),
            "depth_map_gpu": True,
            "pyramid_gpu": True,
        }
    except Exception as exc:
        return {"available": False, "reason": f"CUDA unavailable: {exc}"}


def _luminance(cp: Any, stack: Any) -> Any:
    if stack.ndim == 3:
        return stack
    return stack[..., 0] * 0.2126 + stack[..., 1] * 0.7152 + stack[..., 2] * 0.0722


def _focus_scores(cp: Any, cndimage: Any, stack: Any, metric: FocusMetric, radius: int) -> Any:
    gray = _luminance(cp, stack)
    if metric is FocusMetric.LAPLACIAN:
        kernel = cp.zeros((1, 3, 3), dtype=cp.float32)
        kernel[0] = cp.asarray([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=cp.float32)
        score = cp.abs(cndimage.convolve(gray, kernel, mode="reflect"))
    elif metric is FocusMetric.MODIFIED_LAPLACIAN:
        kernel_x = cp.zeros((1, 3, 3), dtype=cp.float32)
        kernel_y = cp.zeros((1, 3, 3), dtype=cp.float32)
        kernel_x[0] = cp.asarray([[0, 0, 0], [-1, 2, -1], [0, 0, 0]], dtype=cp.float32)
        kernel_y[0] = cp.asarray([[0, -1, 0], [0, 2, 0], [0, -1, 0]], dtype=cp.float32)
        score = cp.abs(cndimage.convolve(gray, kernel_x, mode="reflect")) + cp.abs(
            cndimage.convolve(gray, kernel_y, mode="reflect")
        )
    elif metric is FocusMetric.TENEGRAD:
        kernel_x = cp.zeros((1, 3, 3), dtype=cp.float32)
        kernel_y = cp.zeros((1, 3, 3), dtype=cp.float32)
        kernel_x[0] = cp.asarray([[1, 0, -1], [2, 0, -2], [1, 0, -1]], dtype=cp.float32)
        kernel_y[0] = cp.asarray([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=cp.float32)
        sx = cndimage.convolve(gray, kernel_x, mode="reflect")
        sy = cndimage.convolve(gray, kernel_y, mode="reflect")
        score = sx * sx + sy * sy
    elif metric is FocusMetric.SCHARR:
        kernel_x = cp.zeros((1, 3, 3), dtype=cp.float32)
        kernel_y = cp.zeros((1, 3, 3), dtype=cp.float32)
        kernel_x[0] = cp.asarray([[3, 0, -3], [10, 0, -10], [3, 0, -3]], dtype=cp.float32)
        kernel_y[0] = kernel_x[0].T
        sx = cndimage.convolve(gray, kernel_x, mode="reflect")
        sy = cndimage.convolve(gray, kernel_y, mode="reflect")
        score = sx * sx + sy * sy
    elif metric is FocusMetric.LOCAL_VARIANCE:
        size = max(1, int(radius) * 2 + 1)
        mean = cndimage.uniform_filter(gray, size=(1, size, size), mode="reflect")
        mean_sq = cndimage.uniform_filter(gray * gray, size=(1, size, size), mode="reflect")
        return cp.maximum(mean_sq - mean * mean, 0.0).astype(cp.float32, copy=False)
    elif metric is FocusMetric.BRENNER:
        offset = max(1, int(radius))
        score = cp.zeros_like(gray, dtype=cp.float32)
        dx = gray[:, :, offset:] - gray[:, :, :-offset]
        dy = gray[:, offset:, :] - gray[:, :-offset, :]
        score[:, :, :-offset] += dx * dx
        score[:, :-offset, :] += dy * dy
        return score.astype(cp.float32, copy=False)
    elif metric is FocusMetric.WAVELET:
        score = cp.zeros_like(gray, dtype=cp.float32)
        horizontal = gray[:, :, 1::2] - gray[:, :, ::2][:, :, : gray[:, :, 1::2].shape[2]]
        vertical = gray[:, 1::2, :] - gray[:, ::2, :][:, : gray[:, 1::2, :].shape[1], :]
        score[:, :, : horizontal.shape[2]] += horizontal * horizontal
        score[:, : vertical.shape[1], :] += vertical * vertical
    else:
        raise ValueError(f"Unsupported focus metric: {metric}")
    if radius > 0:
        size = max(1, int(radius) * 2 + 1)
        score = cndimage.uniform_filter(score, size=(1, size, size), mode="reflect")
    return score.astype(cp.float32, copy=False)


def _regularize(cp: Any, cndimage: Any, scores: Any, sigma: float) -> Any:
    if sigma <= 0:
        return scores.astype(cp.float32, copy=False)
    return cndimage.gaussian_filter(
        scores.astype(cp.float32, copy=False),
        sigma=(0.0, float(sigma), float(sigma)),
        mode="reflect",
    ).astype(cp.float32, copy=False)


def _filter_focus_scores(cp: Any, cndimage: Any, scores: Any, parameters: object) -> Any:
    base_sigma = max(float(parameters.smoothing_sigma), 0.0)
    level = int(cp.clip(parameters.detail_scale, 1, 10))
    profile = int(cp.clip(parameters.scale_preset, 1, 5))
    level_sigma = (level - 1) * (0.25 + profile * 0.05)
    fixed_sigma = base_sigma + level_sigma
    fixed = _regularize(cp, cndimage, scores, fixed_sigma)
    if not parameters.adaptive_weighting:
        return fixed
    sharp = _regularize(cp, cndimage, scores, max(0.0, base_sigma * 0.35))
    smooth = _regularize(cp, cndimage, scores, fixed_sigma + 0.75 + profile * 0.15)
    confidence = _normalized_score_span(cp, fixed)
    smart_mix = cp.clip(1.0 - confidence * (0.6 + profile * 0.06), 0.15, 0.85)
    return (sharp * (1.0 - smart_mix) + smooth * smart_mix).astype(cp.float32, copy=False)


def _normalize_scores(cp: Any, scores: Any) -> Any:
    shifted = scores - cp.min(scores)
    maximum = cp.max(shifted)
    if float(maximum.get()) <= 1e-12:
        return cp.zeros_like(scores, dtype=cp.float32)
    return (shifted / maximum).astype(cp.float32, copy=False)


def _normalized_score_span(cp: Any, scores: Any) -> Any:
    span = cp.max(scores, axis=0) - cp.mean(scores, axis=0)
    maximum = cp.maximum(cp.max(span), 1e-12)
    return cp.clip(span / maximum, 0.0, 1.0).astype(cp.float32, copy=False)


def _apply_score_threshold(cp: Any, scores: Any, score_threshold: int) -> Any:
    normalized = _normalize_scores(cp, scores)
    level = int(cp.clip(score_threshold, 0, 29))
    if level <= 0:
        return scores.astype(cp.float32, copy=False)
    threshold = min(0.34, (level * 3.0) / 255.0)
    gated = cp.where(normalized >= threshold, scores, 0.0)
    fallback = cp.max(gated, axis=0) <= 0
    gated[:, fallback] = 1.0
    return gated.astype(cp.float32, copy=False)


def _focus_confidence_map(cp: Any, scores: Any) -> Any:
    normalized = _normalize_scores(cp, scores)
    peak = cp.max(normalized, axis=0)
    if normalized.shape[0] == 1:
        return peak.astype(cp.float32, copy=False)
    second = cp.partition(normalized, -2, axis=0)[-2]
    margin = cp.clip(peak - second, 0.0, 1.0)
    contrast = cp.clip(margin / cp.maximum(peak, 1e-6), 0.0, 1.0)
    return cp.clip(peak * 0.55 + contrast * 0.45, 0.0, 1.0).astype(cp.float32, copy=False)


def _clean_depth_map(
    cp: Any,
    cndimage: Any,
    depth_map: Any,
    scores: Any,
    confidence: Any,
    score_threshold: int,
    region_bias: int,
) -> Any:
    level = int(cp.clip(score_threshold, 0, 29))
    if level < 2:
        return depth_map
    threshold = min(0.34, (level * 3.0) / 255.0)
    cleaned = _propagate_depth(cp, cndimage, depth_map, scores, confidence, 2 + level // 7, threshold, False)
    if region_bias == 0:
        return cleaned
    return _propagate_depth(
        cp,
        cndimage,
        cleaned,
        scores,
        confidence,
        abs(int(cp.clip(region_bias, -10, 10))),
        threshold,
        region_bias > 0,
    )


def _adjust_depth_regions(cp: Any, cndimage: Any, depth_map: Any, scores: Any, region_bias: int) -> Any:
    confidence = _focus_confidence_map(cp, scores)
    threshold = max(0.05, float(cp.percentile(confidence, 45.0).get()))
    return _propagate_depth(
        cp,
        cndimage,
        depth_map,
        scores,
        confidence,
        abs(int(cp.clip(region_bias, -10, 10))),
        threshold,
        region_bias > 0,
    )


def _propagate_depth(
    cp: Any,
    cndimage: Any,
    depth_map: Any,
    scores: Any,
    confidence: Any,
    radius: int,
    threshold: float,
    grow: bool,
) -> Any:
    radius = int(cp.clip(radius, 1, 10))
    kernel = cp.asarray(_circular_kernel(radius), dtype=cp.float32)
    labels = cp.arange(scores.shape[0], dtype=cp.uint16)[:, None, None]
    support = confidence >= threshold
    depth_support = depth_map[None, ...] == labels
    max_scores = cp.maximum(cp.max(scores, axis=0), 1e-12)
    if grow:
        neighbor_counts = cndimage.convolve(depth_support.astype(cp.float32), kernel[None, ...], mode="constant")
        candidates = cp.logical_and(neighbor_counts > 0, ~depth_support)
        stronger = scores >= max_scores[None, ...] * 0.9
        votes = cp.where(candidates & stronger, neighbor_counts * cp.maximum(scores, 1e-6), 0.0)
    else:
        votes = cndimage.convolve(
            depth_support.astype(cp.float32) * support[None, ...] * cp.maximum(confidence, 0.05),
            kernel[None, ...],
            mode="constant",
        )
    replacement_score = cp.max(votes, axis=0)
    replacement = cp.argmax(votes, axis=0).astype(cp.uint16)
    return cp.where(replacement_score > 0, replacement, depth_map).astype(cp.uint16, copy=False)


def _enforce_depth_map(cp: Any, scores: Any, depth_map: Any) -> Any:
    adjusted = scores.copy()
    max_score = cp.maximum(cp.max(adjusted, axis=0), 1e-12)
    labels = cp.arange(scores.shape[0], dtype=cp.uint16)[:, None, None]
    selected = depth_map[None, ...] == labels
    adjusted = cp.where(selected, cp.maximum(adjusted, max_score[None, ...] * 1.15), adjusted)
    return adjusted.astype(cp.float32, copy=False)


def _focus_weights(cp: Any, scores: Any, softness: float) -> Any:
    scale = cp.maximum(cp.std(scores), 1e-6) * max(float(softness), 1e-3)
    normalized = (scores - cp.max(scores, axis=0, keepdims=True)) / scale
    exp_scores = cp.exp(cp.clip(normalized, -60.0, 0.0))
    total = cp.sum(exp_scores, axis=0, keepdims=True)
    return (exp_scores / cp.maximum(total, 1e-12)).astype(cp.float32, copy=False)


def _blend_stack(cp: Any, stack: Any, weights: Any) -> Any:
    if stack.ndim == 4:
        return cp.sum(stack * weights[..., None], axis=0)
    return cp.sum(stack * weights, axis=0)


def _suppress_halos(cp: Any, cndimage: Any, blended: Any, stack: Any, weights: Any, sigma: float) -> Any:
    confidence = cp.max(weights, axis=0)
    dominant = cp.argmax(weights, axis=0)
    labels = cp.arange(stack.shape[0], dtype=dominant.dtype)[:, None, None]
    if stack.ndim == 4:
        dominant_image = cp.sum(stack * (dominant[None, ..., None] == labels[..., None]), axis=0)
    else:
        dominant_image = cp.sum(stack * (dominant[None, ...] == labels), axis=0)
    low = confidence < cp.percentile(confidence, 20.0)
    if not bool(cp.any(low).get()):
        return blended
    filter_sigma = (float(sigma), float(sigma)) if blended.ndim == 2 else (float(sigma), float(sigma), 0.0)
    smooth = cndimage.gaussian_filter(blended, sigma=filter_sigma, mode="reflect")
    mix = cp.clip((0.35 - confidence) / 0.35, 0.0, 1.0)
    if blended.ndim == 3:
        mix = mix[..., None]
        low = low[..., None]
    return cp.where(low, blended * (1.0 - mix) + smooth * mix * 0.35 + dominant_image * mix * 0.65, blended)


def _blend_low_confidence_background(
    cp: Any,
    cndimage: Any,
    blended: Any,
    stack: Any,
    scores: Any,
    parameters: object,
    confidence: Any,
    structure: Any,
) -> Any:
    level = int(cp.clip(parameters.score_threshold, 0, 29))
    if level <= 0:
        return blended
    threshold = min(0.45, max(0.02, level * 2.8 / 255.0))
    background = _stable_background(cp, stack, parameters.background_mode)
    score_span = _normalized_score_span(cp, scores)
    weak = cp.clip(1.0 - confidence / threshold, 0.0, 1.0)
    weak *= cp.clip(1.0 - structure * 1.8, 0.0, 1.0)
    weak *= cp.clip(1.0 - score_span * 1.6, 0.0, 1.0)
    weak = cndimage.gaussian_filter(weak, sigma=1.1, mode="reflect")
    if blended.ndim == 3:
        weak = weak[..., None]
    return (blended * (1.0 - weak) + background * weak).astype(cp.float32, copy=False)


def _preserve_specimen_detail(
    cp: Any,
    cndimage: Any,
    blended: Any,
    stack: Any,
    weights: Any,
    parameters: object,
    structure: Any,
) -> Any:
    if int(parameters.detail_scale) <= 1:
        return blended
    detail_weight = cp.clip(structure * (0.4 + int(parameters.detail_scale) * 0.05), 0.0, 0.7)
    dominant = cp.argmax(weights, axis=0)
    labels = cp.arange(stack.shape[0], dtype=dominant.dtype)[:, None, None]
    if stack.ndim == 4:
        selected = cp.sum(stack * (dominant[None, ..., None] == labels[..., None]), axis=0)
    else:
        selected = cp.sum(stack * (dominant[None, ...] == labels), axis=0)
    if blended.ndim == 3:
        detail_weight = detail_weight[..., None]
    detail_weight = cndimage.gaussian_filter(
        detail_weight,
        sigma=(0.7, 0.7, 0.0) if blended.ndim == 3 else (0.7, 0.7),
        mode="reflect",
    )
    return (blended * (1.0 - detail_weight) + selected * detail_weight).astype(cp.float32, copy=False)


def _stack_structure_confidence(cp: Any, cndimage: Any, stack: Any) -> Any:
    gray = _luminance(cp, stack)
    median = cp.median(gray, axis=0)
    smooth = cndimage.gaussian_filter(median, sigma=4.0, mode="reflect")
    detail = cp.abs(median - smooth)
    high = cp.maximum(cp.percentile(detail, 99.0), 1e-6)
    return cp.clip(detail / high, 0.0, 1.0).astype(cp.float32, copy=False)


def _stable_background(cp: Any, stack: Any, mode: object) -> Any:
    value = getattr(mode, "value", str(mode))
    if value == "darkest":
        return cp.min(stack, axis=0)
    if value == "brightest":
        return cp.max(stack, axis=0)
    if value == "first":
        return stack[0]
    if value == "last":
        return stack[-1]
    if value == "mixed":
        return (cp.median(stack, axis=0) * 0.65 + cp.mean(stack, axis=0) * 0.35).astype(
            cp.float32,
            copy=False,
        )
    return cp.median(stack, axis=0).astype(cp.float32, copy=False)


def _effective_blend_softness(parameters: object) -> float:
    base = max(float(parameters.blend_softness), 0.01)
    threshold = int(np.clip(parameters.score_threshold, 0, 29))
    detail = int(np.clip(parameters.detail_scale, 1, 10))
    return base * (1.0 + threshold * 0.01) / (1.0 + detail * 0.03)


def _circular_kernel(radius: int) -> np.ndarray:
    radius = int(np.clip(radius, 1, 10))
    y, x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    kernel = (x * x + y * y <= radius * radius).astype(np.float32)
    total = np.sum(kernel)
    return kernel / max(float(total), 1.0)
