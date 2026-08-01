"""Optional CuPy GPU-resident Pyramid Max Contrast stacking."""

from __future__ import annotations

import numpy as np

from biopic.imaging.stacking.gpu_depth_map import (
    _blend_low_confidence_background,
    _clean_depth_map,
    _focus_confidence_map,
    _luminance,
)
from biopic.imaging.stacking.gpu_memory import configure_cupy_cache, plan_gpu_memory


def stack_pyramid_max_contrast_gpu(images: list[np.ndarray], parameters: object) -> object | None:
    """Run Pyramid Max Contrast mostly on the GPU when CuPy is available."""
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
            multiplier=4.5,
            memory_limit_mb=getattr(parameters, "gpu_memory_limit_mb", 4096),
        )
        if not memory_plan.full_frame_possible:
            return _stack_pyramid_max_contrast_gpu_tiled(cp, cndimage, images, parameters, memory_plan)
        return _stack_pyramid_max_contrast_gpu_full(cp, cndimage, images, parameters)
    except Exception:
        return None


def _stack_pyramid_max_contrast_gpu_full(cp, cndimage, images: list[np.ndarray], parameters: object):
        stack = [cp.asarray(image, dtype=cp.float32) for image in images]
        levels = int(cp.clip(parameters.scale_preset + parameters.detail_scale // 3, 3, 7))
        pyramids = [_laplacian_pyramid(cp, cndimage, image, levels) for image in stack]
        selected = []
        depth_votes = []
        depth_weights = []
        focus_layers = []
        confidence_scores = None
        base_shape = stack[0].shape[:2]
        for level in range(levels - 1):
            bands = [pyramid[level] for pyramid in pyramids if level < len(pyramid) - 1]
            if not bands:
                break
            contrast = cp.stack(
                [
                    cndimage.gaussian_filter(
                        cp.abs(_luminance(cp, band)),
                        sigma=max(parameters.smoothing_sigma * 0.25, 0.0),
                        mode="reflect",
                    )
                    for band in bands
                ],
                axis=0,
            )
            if confidence_scores is None:
                confidence_scores = cp.stack(
                    [_resize_float_map(cp, cndimage, layer, base_shape) for layer in contrast],
                    axis=0,
                )
            winners = cp.argmax(contrast, axis=0).astype(cp.uint16)
            confidence = _focus_confidence_map(cp, contrast)
            if parameters.confidence_cleanup and parameters.score_threshold >= 2:
                winners = _clean_depth_map(
                    cp,
                    cndimage,
                    winners,
                    contrast,
                    confidence,
                    parameters.score_threshold,
                    parameters.region_bias,
                )
            selected.append(_take_band_by_winner(cp, bands, winners))
            depth_votes.append(_resize_label_map(cp, cndimage, winners, base_shape))
            depth_weights.append(_resize_float_map(cp, cndimage, confidence, base_shape))
            focus_layers.append(_resize_float_map(cp, cndimage, cp.max(contrast, axis=0), base_shape))

        if not selected:
            return None
        base = cp.median(cp.stack([pyramid[-1] for pyramid in pyramids], axis=0), axis=0)
        selected.append(base.astype(cp.float32, copy=False))
        image = _collapse_laplacian_pyramid(cp, cndimage, selected)
        focus_map = cp.mean(cp.stack(focus_layers, axis=0), axis=0).astype(cp.float32, copy=False)
        depth_map = _weighted_depth(cp, cndimage, depth_votes, depth_weights, len(stack))
        if parameters.confidence_cleanup and confidence_scores is not None and parameters.score_threshold >= 2:
            depth_map = _clean_depth_map(
                cp,
                cndimage,
                depth_map,
                confidence_scores,
                _focus_confidence_map(cp, confidence_scores),
                parameters.score_threshold,
                parameters.region_bias,
            )
        if parameters.score_threshold > 0 and confidence_scores is not None:
            image = _blend_low_confidence_background(
                cp,
                cndimage,
                image,
                cp.stack(stack, axis=0),
                confidence_scores,
                parameters,
                _focus_confidence_map(cp, confidence_scores),
                focus_map,
            )
        frame_labels = cp.arange(len(stack), dtype=cp.uint16)[:, None, None]
        weights = (depth_map[None, ...] == frame_labels).astype(cp.float32, copy=False)
        weights /= cp.maximum(cp.sum(weights, axis=0, keepdims=True), 1.0)

        from biopic.imaging.stacking import stacker as core

        return core._PyramidStack(
            image=cp.asnumpy(cp.clip(image, 0.0, 1.0)).astype(np.float32, copy=False),
            depth_map=cp.asnumpy(depth_map).astype(np.uint16, copy=False),
            focus_map=cp.asnumpy(focus_map).astype(np.float32, copy=False),
            weights=cp.asnumpy(weights).astype(np.float32, copy=False),
        )


def _stack_pyramid_max_contrast_gpu_tiled(
    cp,
    cndimage,
    images: list[np.ndarray],
    parameters: object,
    memory_plan: object,
):
    height, width = images[0].shape[:2]
    overlap = int(max(32, memory_plan.tile_overlap))
    tile_height = int(max(160, memory_plan.tile_height))
    if tile_height >= height:
        return None
    step = max(1, tile_height - overlap * 2)
    image_out = np.zeros(images[0].shape, dtype=np.float32)
    depth_out = np.zeros((height, width), dtype=np.uint16)
    focus_out = np.zeros((height, width), dtype=np.float32)
    weights_out = np.zeros((len(images), height, width), dtype=np.float32)
    core_start = 0
    while core_start < height:
        core_end = min(height, core_start + step)
        tile_start = max(0, core_start - overlap)
        tile_end = min(height, core_end + overlap)
        tile_images = [np.asarray(image[tile_start:tile_end], dtype=np.float32) for image in images]
        tile_result = _stack_pyramid_max_contrast_gpu_full(cp, cndimage, tile_images, parameters)
        local_start = core_start - tile_start
        local_end = local_start + (core_end - core_start)
        image_out[core_start:core_end] = tile_result.image[local_start:local_end]
        depth_out[core_start:core_end] = tile_result.depth_map[local_start:local_end]
        focus_out[core_start:core_end] = tile_result.focus_map[local_start:local_end]
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


def _laplacian_pyramid(cp, cndimage, image, levels: int):
    gaussian = [image]
    for _level in range(1, levels):
        previous = gaussian[-1]
        if min(previous.shape[:2]) < 8:
            break
        blurred = _gaussian_image(cndimage, previous, sigma=1.0)
        gaussian.append(blurred[::2, ::2] if previous.ndim == 2 else blurred[::2, ::2, :])
    pyramid = []
    for level, current in enumerate(gaussian[:-1]):
        expanded = _resize_image(cndimage, gaussian[level + 1], current.shape[:2])
        pyramid.append((current - expanded).astype(cp.float32, copy=False))
    pyramid.append(gaussian[-1].astype(cp.float32, copy=False))
    return pyramid


def _collapse_laplacian_pyramid(cp, cndimage, pyramid):
    image = pyramid[-1]
    for band in reversed(pyramid[:-1]):
        image = _resize_image(cndimage, image, band.shape[:2]) + band
    return image.astype(cp.float32, copy=False)


def _gaussian_image(cndimage, image, sigma: float):
    filter_sigma = (sigma, sigma) if image.ndim == 2 else (sigma, sigma, 0.0)
    return cndimage.gaussian_filter(image, sigma=filter_sigma, mode="reflect")


def _resize_image(cndimage, image, shape: tuple[int, int]):
    zoom = (shape[0] / image.shape[0], shape[1] / image.shape[1])
    if image.ndim == 3:
        zoom = (*zoom, 1.0)
    return cndimage.zoom(image, zoom=zoom, order=1, mode="reflect", prefilter=False)[
        : shape[0], : shape[1], ...
    ]


def _resize_label_map(cp, cndimage, labels, shape: tuple[int, int]):
    resized = cndimage.zoom(
        labels.astype(cp.float32),
        zoom=(shape[0] / labels.shape[0], shape[1] / labels.shape[1]),
        order=0,
        mode="nearest",
    )
    return resized[: shape[0], : shape[1]].astype(cp.uint16, copy=False)


def _resize_float_map(cp, cndimage, values, shape: tuple[int, int]):
    resized = cndimage.zoom(
        values,
        zoom=(shape[0] / values.shape[0], shape[1] / values.shape[1]),
        order=1,
        mode="reflect",
    )
    return resized[: shape[0], : shape[1]].astype(cp.float32, copy=False)


def _take_band_by_winner(cp, bands, winners):
    band_stack = cp.stack(bands, axis=0)
    if band_stack.ndim == 4:
        return cp.take_along_axis(band_stack, winners[None, ..., None], axis=0)[0]
    return cp.take_along_axis(band_stack, winners[None, ...], axis=0)[0]


def _weighted_depth(cp, cndimage, depth_votes, depth_weights, frame_count: int):
    if not depth_votes:
        return cp.zeros((1, 1), dtype=cp.uint16)
    accum = cp.zeros((frame_count, *depth_votes[0].shape), dtype=cp.float32)
    for index, vote in enumerate(depth_votes):
        weight = depth_weights[index] if index < len(depth_weights) else cp.ones_like(vote)
        scale_weight = 1.0 + index * 0.35
        labels = cp.arange(frame_count, dtype=cp.uint16)[:, None, None]
        accum += (vote[None, ...] == labels).astype(cp.float32) * weight * scale_weight
    accum = cndimage.gaussian_filter(accum, sigma=(0.0, 0.9, 0.9), mode="reflect")
    return cp.argmax(accum, axis=0).astype(cp.uint16)
