"""Independent focus-stacking implementation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum

import numpy as np
from scipy import ndimage

from biopic.imaging.stacking.alignment import AlignmentTransform, align_stack_translation
from biopic.imaging.stacking.focus_metrics import FocusMetric, focus_measure, to_luminance


class AlignmentMode(StrEnum):
    """Stack alignment mode."""

    NONE = "none"
    TRANSLATION = "translation"


class StackingMethod(StrEnum):
    """Focus-stack synthesis method."""

    DEPTH_MAP = "depth_map"
    PYRAMID_MAX_CONTRAST = "pyramid_max_contrast"


@dataclass(frozen=True, slots=True)
class FocusStackParameters:
    """Reproducible focus-stacking parameters."""

    stacking_method: StackingMethod = StackingMethod.DEPTH_MAP
    focus_metric: FocusMetric = FocusMetric.MODIFIED_LAPLACIAN
    focus_radius: int = 3
    smoothing_sigma: float = 2.0
    blend_softness: float = 0.12
    halo_suppression_sigma: float = 1.0
    score_threshold: int = 4
    region_bias: int = 0
    scale_preset: int = 3
    adaptive_weighting: bool = True
    detail_scale: int = 4
    alignment_mode: AlignmentMode = AlignmentMode.TRANSLATION
    preview_scale: float = 1.0
    output_depth_map: bool = True

    def to_dict(self) -> dict[str, object]:
        """Serialize parameters."""
        data = asdict(self)
        data["stacking_method"] = self.stacking_method.value
        data["focus_metric"] = self.focus_metric.value
        data["alignment_mode"] = self.alignment_mode.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> FocusStackParameters:
        """Deserialize parameters."""
        return cls(
            stacking_method=StackingMethod(str(data.get("stacking_method", StackingMethod.DEPTH_MAP))),
            focus_metric=FocusMetric(str(data.get("focus_metric", FocusMetric.MODIFIED_LAPLACIAN))),
            focus_radius=_as_int(data.get("focus_radius", 3)),
            smoothing_sigma=_as_float(data.get("smoothing_sigma", 2.0)),
            blend_softness=_as_float(data.get("blend_softness", 0.12)),
            halo_suppression_sigma=_as_float(data.get("halo_suppression_sigma", 1.0)),
            score_threshold=_as_int(data.get("score_threshold", data.get("minimum_score", 4))),
            region_bias=_as_int(data.get("region_bias", data.get("patch_adjustment", 0))),
            scale_preset=_as_int(data.get("scale_preset", data.get("filter_set", 3))),
            adaptive_weighting=bool(data.get("adaptive_weighting", data.get("smart_filter", True))),
            detail_scale=_as_int(data.get("detail_scale", data.get("filter_level", 4))),
            alignment_mode=AlignmentMode(
                str(data.get("alignment_mode", AlignmentMode.TRANSLATION))
            ),
            preview_scale=_as_float(data.get("preview_scale", 1.0)),
            output_depth_map=bool(data.get("output_depth_map", True)),
        )


@dataclass(frozen=True, slots=True)
class FocusStackResult:
    """Focus-stacking result and provenance."""

    image: np.ndarray
    depth_map: np.ndarray
    focus_map: np.ndarray
    weights: np.ndarray
    transforms: list[AlignmentTransform]
    parameters: FocusStackParameters


ProgressCallback = Callable[[str, float], None]


def focus_stack(
    images: list[np.ndarray],
    parameters: FocusStackParameters | None = None,
    progress: ProgressCallback | None = None,
) -> FocusStackResult:
    """Create a focus-stacked image from an ordered focal stack."""
    params = parameters or FocusStackParameters()
    _validate_images(images)
    working = [_as_float_image(_resize_preview(image, params.preview_scale)) for image in images]
    _emit(progress, "loaded", 0.05)

    if params.alignment_mode is AlignmentMode.TRANSLATION:
        working, transforms = align_stack_translation(working)
    else:
        transforms = [AlignmentTransform() for _image in working]
    _emit(progress, "aligned", 0.25)

    if params.stacking_method is StackingMethod.PYRAMID_MAX_CONTRAST:
        result = pyramid_max_contrast_stack(working, params)
        _emit(progress, "complete", 1.0)
        return FocusStackResult(
            image=_restore_dtype(result.image, images[0].dtype),
            depth_map=result.depth_map,
            focus_map=result.focus_map,
            weights=result.weights,
            transforms=transforms,
            parameters=params,
        )

    scores = np.stack(
        [
            focus_measure(image, params.focus_metric, max(1, params.focus_radius))
            for image in working
        ],
        axis=0,
    )
    _emit(progress, "focus map", 0.45)

    filtered_scores = filter_focus_scores(
        scores,
        smoothing_sigma=params.smoothing_sigma,
        detail_scale=params.detail_scale,
        scale_preset=params.scale_preset,
        adaptive_weighting=params.adaptive_weighting,
    )
    regularized = apply_score_threshold(filtered_scores, params.score_threshold)
    depth_map = np.asarray(np.argmax(regularized, axis=0), dtype=np.uint16)
    if params.region_bias != 0 and params.score_threshold >= 2:
        depth_map = adjust_depth_regions(depth_map, regularized, params.region_bias)
        regularized = enforce_depth_map(regularized, depth_map)
    weights = focus_weights(regularized, effective_blend_softness(params))
    _emit(progress, "weights", 0.65)

    blended = blend_stack(working, weights)
    if params.halo_suppression_sigma > 0:
        blended = suppress_halos(blended, working, weights, params.halo_suppression_sigma)
    blended = blend_low_confidence_background(
        blended, working, filtered_scores, params.score_threshold
    )
    _emit(progress, "complete", 1.0)
    return FocusStackResult(
        image=_restore_dtype(blended, images[0].dtype),
        depth_map=depth_map,
        focus_map=regularized,
        weights=weights,
        transforms=transforms,
        parameters=params,
    )


def regularize_focus_scores(scores: np.ndarray, smoothing_sigma: float) -> np.ndarray:
    """Spatially regularize frame focus scores."""
    if scores.ndim != 3:
        raise ValueError("scores must have shape frame, height, width")
    if smoothing_sigma <= 0:
        return scores.astype(np.float32, copy=False)
    return np.stack(
        [
            ndimage.gaussian_filter(score, sigma=smoothing_sigma, mode="reflect")
            for score in scores
        ],
        axis=0,
    ).astype(np.float32, copy=False)


def filter_focus_scores(
    scores: np.ndarray,
    smoothing_sigma: float,
    detail_scale: int,
    scale_preset: int,
    adaptive_weighting: bool,
) -> np.ndarray:
    """Apply a detail-to-smooth focus-score profile independent of metric type."""
    base_sigma = max(float(smoothing_sigma), 0.0)
    level = int(np.clip(detail_scale, 1, 10))
    profile = int(np.clip(scale_preset, 1, 5))
    level_sigma = (level - 1) * (0.25 + profile * 0.05)
    fixed_sigma = base_sigma + level_sigma
    fixed = regularize_focus_scores(scores, fixed_sigma)
    if not adaptive_weighting:
        return fixed

    sharp = regularize_focus_scores(scores, max(0.0, base_sigma * 0.35))
    smooth = regularize_focus_scores(scores, fixed_sigma + 0.75 + profile * 0.15)
    confidence = _normalized_score_span(fixed)
    smart_mix = np.clip(1.0 - confidence * (0.6 + profile * 0.06), 0.15, 0.85)
    return (sharp * (1.0 - smart_mix) + smooth * smart_mix).astype(np.float32, copy=False)


def apply_score_threshold(scores: np.ndarray, score_threshold: int) -> np.ndarray:
    """Suppress weak normalized focus scores before source-frame selection."""
    level = int(np.clip(score_threshold, 0, 29))
    if level <= 0:
        return scores.astype(np.float32, copy=False)
    normalized = _normalize_scores(scores)
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
    """Shrink or grow same-depth regions after focus-score selection."""
    adjustment = int(np.clip(region_bias, -10, 10))
    if adjustment == 0:
        return depth_map
    radius = abs(adjustment)
    structure = ndimage.generate_binary_structure(2, 1)
    if radius > 1:
        structure = ndimage.iterate_structure(structure, radius)
    adjusted = np.asarray(depth_map, dtype=np.int32).copy()
    frame_count = scores.shape[0]
    confidence = np.max(scores, axis=0)
    for frame in range(frame_count):
        mask = depth_map == frame
        if adjustment < 0:
            adjusted[np.logical_and(mask, ~ndimage.binary_erosion(mask, structure=structure))] = -1
            continue
        grown = ndimage.binary_dilation(mask, structure=structure)
        candidates = np.logical_and(grown, depth_map != frame)
        stronger = scores[frame] >= confidence * 0.92
        adjusted[np.logical_and(candidates, stronger)] = frame
    if adjustment < 0:
        adjusted = _fill_unassigned_depths(adjusted, scores)
    return adjusted.astype(np.uint16, copy=False)


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
    smart_factor = 1.4 if params.adaptive_weighting else 0.75
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
) -> np.ndarray:
    """Blend weak-focus pixels toward a stable background reference."""
    level = int(np.clip(score_threshold, 0, 29))
    if level <= 0 or len(images) < 2:
        return blended
    confidence = _low_confidence_measure(scores)
    threshold = min(0.34, (level * 3.0) / 255.0)
    if threshold <= 0:
        return blended
    current_weight = np.ones_like(confidence, dtype=np.float32)
    weak = confidence < threshold
    if not np.any(weak):
        return blended
    current_weight[weak] = np.clip(
        (confidence[weak] * 2.0) / np.maximum(threshold + confidence[weak], 1e-6),
        0.0,
        1.0,
    )
    structure = _stack_structure_confidence(images)
    detail_weight = np.clip((structure - threshold * 0.35) / max(threshold * 0.9, 1e-6), 0.0, 1.0)
    current_weight = np.maximum(current_weight, detail_weight.astype(np.float32, copy=False))
    current_weight = ndimage.gaussian_filter(current_weight, sigma=1.0, mode="reflect")
    background = stable_background_reference(images)
    if np.ndim(current_weight) < np.ndim(blended):
        current_weight = current_weight[..., None]
    return (blended * current_weight + background * (1.0 - current_weight)).astype(
        np.float32, copy=False
    )


@dataclass(frozen=True, slots=True)
class _PyramidStack:
    image: np.ndarray
    depth_map: np.ndarray
    focus_map: np.ndarray
    weights: np.ndarray


def pyramid_max_contrast_stack(
    images: list[np.ndarray], params: FocusStackParameters
) -> _PyramidStack:
    """Blend a stack by selecting maximum Laplacian-pyramid contrast per scale."""
    stack = [np.asarray(image, dtype=np.float32) for image in images]
    levels = int(np.clip(params.scale_preset + params.detail_scale // 3, 3, 7))
    pyramids = [_laplacian_pyramid(image, levels) for image in stack]
    selected: list[np.ndarray] = []
    depth_votes: list[np.ndarray] = []
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
        selected.append(_take_band_by_winner(bands, winners))
        depth_votes.append(_resize_label_map(winners, stack[0].shape[:2]))
        focus_layers.append(_resize_float_map(np.max(contrast, axis=0), stack[0].shape[:2]))

    base = np.median(np.stack([pyramid[-1] for pyramid in pyramids], axis=0), axis=0)
    selected.append(base.astype(np.float32, copy=False))
    image = _collapse_laplacian_pyramid(selected)
    focus_map = np.mean(np.stack(focus_layers, axis=0), axis=0).astype(np.float32, copy=False)
    depth_map = _majority_depth(depth_votes, len(stack))
    if params.score_threshold > 0 and confidence_scores is not None:
        image = blend_low_confidence_background(image, stack, confidence_scores, params.score_threshold)
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


def stable_background_reference(images: list[np.ndarray]) -> np.ndarray:
    """Build a smooth reference for low-texture regions of a stack."""
    stack = np.stack(images, axis=0).astype(np.float32, copy=False)
    background = np.median(stack, axis=0).astype(np.float32, copy=False)
    sigma = (0.9, 0.9) if background.ndim == 2 else (0.9, 0.9, 0.0)
    return ndimage.gaussian_filter(background, sigma=sigma, mode="reflect").astype(
        np.float32, copy=False
    )


def _stack_structure_confidence(images: list[np.ndarray]) -> np.ndarray:
    """Estimate where source images contain real specimen structure."""
    structure_layers = []
    for image in images:
        gray = to_luminance(image).astype(np.float32, copy=False)
        smooth = ndimage.gaussian_filter(gray, sigma=2.0, mode="reflect")
        structure = np.abs(gray - smooth)
        structure_layers.append(ndimage.gaussian_filter(structure, sigma=0.7, mode="reflect"))
    structure_map = np.max(np.stack(structure_layers, axis=0), axis=0)
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
    zoom = (scale, scale) if array.ndim == 2 else (scale, scale, 1)
    return ndimage.zoom(array, zoom=zoom, order=1)


def _emit(progress: ProgressCallback | None, message: str, fraction: float) -> None:
    if progress is not None:
        progress(message, fraction)


def _as_float(value: object) -> float:
    if isinstance(value, (str, bytes, int, float)):
        return float(value)
    raise TypeError(f"Expected numeric value, got {type(value).__name__}")


def _as_int(value: object) -> int:
    if isinstance(value, (str, bytes, int, float)):
        return int(value)
    raise TypeError(f"Expected integer value, got {type(value).__name__}")
