"""Laplacian-pyramid maximum-contrast focus-stacking implementation."""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from biopic.imaging.stacking.focus_metrics import to_luminance
from biopic.imaging.stacking.stack_types import FocusStackParameters
from biopic.imaging.stacking.shared import (
    _PyramidStack,
    blend_low_confidence_background,
    clean_depth_map_by_confidence,
    focus_confidence_map,
)


def stack_pyramid_max_contrast(
    images: list[np.ndarray], parameters: FocusStackParameters
) -> _PyramidStack:
    """Run the Pyramid Max Contrast method."""
    from biopic.imaging.stacking.gpu_pyramid import stack_pyramid_max_contrast_gpu

    gpu_result = stack_pyramid_max_contrast_gpu(images, parameters)
    if gpu_result is not None:
        return gpu_result
    return pyramid_max_contrast_stack(images, parameters)


def pyramid_max_contrast_stack(
    images: list[np.ndarray], params: FocusStackParameters
) -> _PyramidStack:
    """Blend a stack by selecting maximum Laplacian-pyramid contrast per scale."""
    stack = [np.asarray(image, dtype=np.float32) for image in images]
    levels = int(np.clip(params.scale_preset + params.detail_scale // 3, 3, 7))
    pyramids = [_laplacian_pyramid(image, levels) for image in stack]
    selected: list[np.ndarray] = []
    depth_votes: list[np.ndarray] = []
    depth_weights: list[np.ndarray] = []
    focus_layers: list[np.ndarray] = []
    confidence_scores: np.ndarray | None = None
    for level in range(levels - 1):
        bands = [pyramid[level] for pyramid in pyramids]
        contrast = np.stack(
            [
                ndimage.gaussian_filter(
                    np.abs(to_luminance(band)), sigma=max(params.smoothing_sigma * 0.25, 0.0)
                )
                for band in bands
            ],
            axis=0,
        )
        if confidence_scores is None:
            confidence_scores = np.stack(
                [_resize_float_map(layer, stack[0].shape[:2]) for layer in contrast], axis=0
            )
        winners = np.asarray(np.argmax(contrast, axis=0), dtype=np.uint16)
        if params.confidence_cleanup and params.score_threshold >= 2:
            confidence = focus_confidence_map(contrast)
            winners = clean_depth_map_by_confidence(
                winners,
                contrast,
                confidence,
                params.score_threshold,
                params.region_bias,
                cleanup_unsupported=False,
            )
        else:
            confidence = focus_confidence_map(contrast)
        selected.append(_take_band_by_winner(bands, winners))
        depth_votes.append(_resize_label_map(winners, stack[0].shape[:2]))
        depth_weights.append(_resize_float_map(confidence, stack[0].shape[:2]))
        focus_layers.append(_resize_float_map(np.max(contrast, axis=0), stack[0].shape[:2]))

    base = np.median(np.stack([pyramid[-1] for pyramid in pyramids], axis=0), axis=0)
    selected.append(base.astype(np.float32, copy=False))
    image = _collapse_laplacian_pyramid(selected)
    focus_map = np.mean(np.stack(focus_layers, axis=0), axis=0).astype(np.float32, copy=False)
    depth_map = _weighted_depth(depth_votes, depth_weights, len(stack))
    if params.confidence_cleanup and confidence_scores is not None and params.score_threshold >= 2:
        depth_map = clean_depth_map_by_confidence(
            depth_map,
            confidence_scores,
            focus_confidence_map(confidence_scores),
            params.score_threshold,
            params.region_bias,
        )
    if params.score_threshold > 0 and confidence_scores is not None:
        image = blend_low_confidence_background(
            image,
            stack,
            confidence_scores,
            params.score_threshold,
            params.background_mode,
        )
    weights = np.zeros((len(stack), *stack[0].shape[:2]), dtype=np.float32)
    for frame in range(len(stack)):
        weights[frame] = depth_map == frame
    total = np.maximum(np.sum(weights, axis=0, keepdims=True), 1.0)
    weights /= total
    return _PyramidStack(
        image=np.clip(image, 0.0, 1.0).astype(np.float32, copy=False),
        depth_map=depth_map,
        focus_map=focus_map,
        weights=weights,
    )


def _laplacian_pyramid(image: np.ndarray, levels: int) -> list[np.ndarray]:
    gaussian = [image]
    for _level in range(1, levels):
        previous = gaussian[-1]
        if min(previous.shape[:2]) < 8:
            break
        blurred = _gaussian_image(previous, sigma=1.0)
        gaussian.append(blurred[::2, ::2] if previous.ndim == 2 else blurred[::2, ::2, :])
    pyramid: list[np.ndarray] = []
    for level, current in enumerate(gaussian[:-1]):
        expanded = _resize_image(gaussian[level + 1], current.shape[:2])
        pyramid.append((current - expanded).astype(np.float32, copy=False))
    pyramid.append(gaussian[-1].astype(np.float32, copy=False))
    return pyramid


def _collapse_laplacian_pyramid(pyramid: list[np.ndarray]) -> np.ndarray:
    image = pyramid[-1]
    for band in reversed(pyramid[:-1]):
        image = _resize_image(image, band.shape[:2]) + band
    return image.astype(np.float32, copy=False)


def _take_band_by_winner(bands: list[np.ndarray], winners: np.ndarray) -> np.ndarray:
    band_stack = np.stack(bands, axis=0)
    if band_stack.ndim == 4:
        return np.take_along_axis(band_stack, winners[None, ..., None], axis=0)[0]
    return np.take_along_axis(band_stack, winners[None, ...], axis=0)[0]


def _majority_depth(depth_votes: list[np.ndarray], frame_count: int) -> np.ndarray:
    if not depth_votes:
        return np.zeros((1, 1), dtype=np.uint16)
    votes = np.stack(depth_votes, axis=0)
    counts = np.stack([np.sum(votes == frame, axis=0) for frame in range(frame_count)], axis=0)
    return np.asarray(np.argmax(counts, axis=0), dtype=np.uint16)


def _weighted_depth(
    depth_votes: list[np.ndarray], depth_weights: list[np.ndarray], frame_count: int
) -> np.ndarray:
    if not depth_votes:
        return np.zeros((1, 1), dtype=np.uint16)
    accum = np.zeros((frame_count, *depth_votes[0].shape), dtype=np.float32)
    for index, vote in enumerate(depth_votes):
        weight = depth_weights[index] if index < len(depth_weights) else np.ones_like(vote)
        scale_weight = 1.0 + index * 0.35
        for frame in range(frame_count):
            accum[frame] += (vote == frame).astype(np.float32) * weight * scale_weight
    accum = np.stack(
        [ndimage.gaussian_filter(layer, sigma=0.9, mode="reflect") for layer in accum],
        axis=0,
    )
    return np.asarray(np.argmax(accum, axis=0), dtype=np.uint16)


def _gaussian_image(image: np.ndarray, sigma: float) -> np.ndarray:
    filter_sigma = (sigma, sigma) if image.ndim == 2 else (sigma, sigma, 0.0)
    return ndimage.gaussian_filter(image, sigma=filter_sigma, mode="reflect")


def _resize_image(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    zoom = (shape[0] / image.shape[0], shape[1] / image.shape[1])
    if image.ndim == 3:
        zoom = (*zoom, 1.0)
    return ndimage.zoom(image, zoom=zoom, order=1, mode="reflect", prefilter=False)[
        : shape[0], : shape[1], ...
    ]


def _resize_label_map(labels: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    return ndimage.zoom(
        labels, zoom=(shape[0] / labels.shape[0], shape[1] / labels.shape[1]), order=0
    )[: shape[0], : shape[1]].astype(np.uint16, copy=False)


def _resize_float_map(values: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    return ndimage.zoom(
        values, zoom=(shape[0] / values.shape[0], shape[1] / values.shape[1]), order=1
    )[: shape[0], : shape[1]].astype(np.float32, copy=False)
