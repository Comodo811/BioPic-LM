"""Independent focus-stacking implementation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import lru_cache

import cv2
import numpy as np
from scipy import ndimage

from biopic.imaging.stacking.alignment import AlignmentTransform, align_stack_translation
from biopic.imaging.stacking.focus_metrics import FocusMetric, to_luminance
from biopic.imaging.stacking.private_methods import private_stacking_enabled


class AlignmentMode(StrEnum):
    """Stack alignment mode."""

    NONE = "none"
    TRANSLATION = "translation"


class StackingMethod(StrEnum):
    """Focus-stack synthesis method."""

    DEPTH_MAP = "depth_map"
    PYRAMID_MAX_CONTRAST = "pyramid_max_contrast"
    CUSTOM = "custom"
    CUSTOM2 = "custom2"


class BackgroundMode(StrEnum):
    """Reference image used for low-confidence stack regions."""

    MEDIAN = "median"
    MIXED = "mixed"
    DARKEST = "darkest"
    BRIGHTEST = "brightest"
    FIRST = "first"
    LAST = "last"


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
    background_mode: BackgroundMode = BackgroundMode.MEDIAN
    confidence_cleanup: bool = True
    alignment_mode: AlignmentMode = AlignmentMode.TRANSLATION
    preview_scale: float = 1.0
    output_depth_map: bool = True
    use_cuda: bool = False
    gpu_memory_limit_mb: int = 4096
    custom2_pyramid_levels: int = 0
    custom2_detail_strength: float = 0.65
    custom2_medium_detail: float = 0.30
    custom2_fine_detail: float = 0.70
    custom2_focus_confidence_threshold: float = 0.10
    custom2_depth_smoothness: float = 0.70
    custom2_max_depth_correction: int = 2
    custom2_noise_suppression: float = 0.55
    custom2_halo_suppression: float = 0.75
    custom2_edge_consistency: float = 0.60
    custom2_chrominance_detail: float = 0.15
    custom2_background_detail_suppression: float = 0.80
    custom2_use_source_detail: bool = False
    custom2_save_diagnostics: bool = False
    custom2_preset: str = "natural"

    def to_dict(self) -> dict[str, object]:
        """Serialize parameters."""
        data = asdict(self)
        data["stacking_method"] = self.stacking_method.value
        data["focus_metric"] = self.focus_metric.value
        data["background_mode"] = self.background_mode.value
        data["alignment_mode"] = self.alignment_mode.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> FocusStackParameters:
        """Deserialize parameters."""
        return cls(
            stacking_method=StackingMethod(
                str(data.get("stacking_method", StackingMethod.DEPTH_MAP))
            ),
            focus_metric=FocusMetric(
                str(data.get("focus_metric", FocusMetric.MODIFIED_LAPLACIAN))
            ),
            focus_radius=_as_int(data.get("focus_radius", 3)),
            smoothing_sigma=_as_float(data.get("smoothing_sigma", 2.0)),
            blend_softness=_as_float(data.get("blend_softness", 0.12)),
            halo_suppression_sigma=_as_float(data.get("halo_suppression_sigma", 1.0)),
            score_threshold=_as_int(data.get("score_threshold", data.get("minimum_score", 4))),
            region_bias=_as_int(data.get("region_bias", data.get("patch_adjustment", 0))),
            scale_preset=_as_int(data.get("scale_preset", data.get("filter_set", 3))),
            adaptive_weighting=bool(data.get("adaptive_weighting", data.get("smart_filter", True))),
            detail_scale=_as_int(data.get("detail_scale", data.get("filter_level", 4))),
            background_mode=BackgroundMode(
                str(data.get("background_mode", BackgroundMode.MEDIAN))
            ),
            confidence_cleanup=bool(data.get("confidence_cleanup", True)),
            alignment_mode=AlignmentMode(
                str(data.get("alignment_mode", AlignmentMode.TRANSLATION))
            ),
            preview_scale=_as_float(data.get("preview_scale", 1.0)),
            output_depth_map=bool(data.get("output_depth_map", True)),
            use_cuda=bool(data.get("use_cuda", False)),
            gpu_memory_limit_mb=_as_int(data.get("gpu_memory_limit_mb", 4096)),
            custom2_pyramid_levels=_as_int(data.get("custom2_pyramid_levels", 0)),
            custom2_detail_strength=_as_float(data.get("custom2_detail_strength", 0.65)),
            custom2_medium_detail=_as_float(data.get("custom2_medium_detail", 0.30)),
            custom2_fine_detail=_as_float(data.get("custom2_fine_detail", 0.70)),
            custom2_focus_confidence_threshold=_as_float(
                data.get("custom2_focus_confidence_threshold", 0.10)
            ),
            custom2_depth_smoothness=_as_float(data.get("custom2_depth_smoothness", 0.70)),
            custom2_max_depth_correction=_as_int(data.get("custom2_max_depth_correction", 2)),
            custom2_noise_suppression=_as_float(data.get("custom2_noise_suppression", 0.55)),
            custom2_halo_suppression=_as_float(data.get("custom2_halo_suppression", 0.75)),
            custom2_edge_consistency=_as_float(data.get("custom2_edge_consistency", 0.60)),
            custom2_chrominance_detail=_as_float(data.get("custom2_chrominance_detail", 0.15)),
            custom2_background_detail_suppression=_as_float(
                data.get("custom2_background_detail_suppression", 0.80)
            ),
            custom2_use_source_detail=bool(data.get("custom2_use_source_detail", False)),
            custom2_save_diagnostics=bool(data.get("custom2_save_diagnostics", False)),
            custom2_preset=str(data.get("custom2_preset", "natural")),
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
PreviewCallback = Callable[[np.ndarray, str], None]


def focus_stack(
    images: list[np.ndarray],
    parameters: FocusStackParameters | None = None,
    progress: ProgressCallback | None = None,
    preview: PreviewCallback | None = None,
) -> FocusStackResult:
    """Create a focus-stacked image from an ordered focal stack."""
    params = parameters or FocusStackParameters()
    images = auto_orient_stack_images(images)
    _validate_images(images)
    working = [_as_float_image(_resize_preview(image, params.preview_scale)) for image in images]
    _emit(progress, "loaded", 0.05)

    if params.alignment_mode is AlignmentMode.TRANSLATION:
        working, transforms = align_stack_translation(working, use_cuda=params.use_cuda)
    else:
        transforms = [AlignmentTransform() for _image in working]
    _emit(progress, "aligned", 0.25)

    if params.stacking_method is StackingMethod.PYRAMID_MAX_CONTRAST:
        from biopic.imaging.stacking.methods import stack_pyramid_max_contrast

        result = stack_pyramid_max_contrast(working, params)
        _emit(progress, "complete", 1.0)
        return FocusStackResult(
            image=_restore_dtype(result.image, images[0].dtype),
            depth_map=result.depth_map,
            focus_map=result.focus_map,
            weights=result.weights,
            transforms=transforms,
            parameters=params,
        )
    if params.stacking_method is StackingMethod.CUSTOM:
        if not private_stacking_enabled():
            raise ValueError("Custom stacking is private and is disabled in this build.")
        from biopic.imaging.stacking.methods import stack_custom

        params, result = stack_custom(working, params, progress, preview)
        _emit(progress, "complete", 1.0)
        return FocusStackResult(
            image=_restore_dtype(result.image, images[0].dtype),
            depth_map=result.depth_map,
            focus_map=result.focus_map,
            weights=result.weights,
            transforms=transforms,
            parameters=params,
        )
    if params.stacking_method is StackingMethod.CUSTOM2:
        if not private_stacking_enabled():
            raise ValueError("Custom2 stacking is private and is disabled in this build.")
        from biopic.imaging.stacking.methods import stack_custom2

        result = stack_custom2(working, params, progress, preview)
        _emit(progress, "complete", 1.0)
        return FocusStackResult(
            image=_restore_dtype(result.image, images[0].dtype),
            depth_map=result.depth_map,
            focus_map=result.focus_map,
            weights=result.weights,
            transforms=transforms,
            parameters=params,
        )

    from biopic.imaging.stacking.methods import stack_depth_map

    _emit(progress, "focus map", 0.45)
    result = stack_depth_map(working, params)
    _emit(progress, "weights", 0.65)
    _emit(progress, "complete", 1.0)
    return FocusStackResult(
        image=_restore_dtype(result.image, images[0].dtype),
        depth_map=result.depth_map,
        focus_map=result.focus_map,
        weights=result.weights,
        transforms=transforms,
        parameters=params,
    )


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
    if use_cuda and _cuda_available():
        accelerated = _stack_focus_measure_accelerated(images, metric, radius)
        if accelerated is not None:
            return accelerated
    gray_stack = np.stack(
        [to_luminance(image).astype(np.float32, copy=False) for image in images],
        axis=0,
    )
    if metric is FocusMetric.LAPLACIAN:
        kernel = np.zeros((1, 3, 3), dtype=np.float32)
        kernel[0] = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        score = np.abs(ndimage.convolve(gray_stack, kernel, mode="reflect"))
    elif metric is FocusMetric.MODIFIED_LAPLACIAN:
        kernel_x = np.zeros((1, 3, 3), dtype=np.float32)
        kernel_y = np.zeros((1, 3, 3), dtype=np.float32)
        kernel_x[0] = np.array([[0, 0, 0], [-1, 2, -1], [0, 0, 0]], dtype=np.float32)
        kernel_y[0] = np.array([[0, -1, 0], [0, 2, 0], [0, -1, 0]], dtype=np.float32)
        score = np.abs(ndimage.convolve(gray_stack, kernel_x, mode="reflect")) + np.abs(
            ndimage.convolve(gray_stack, kernel_y, mode="reflect")
        )
    elif metric is FocusMetric.TENEGRAD:
        kernel_x = np.zeros((1, 3, 3), dtype=np.float32)
        kernel_y = np.zeros((1, 3, 3), dtype=np.float32)
        kernel_x[0] = np.array([[1, 0, -1], [2, 0, -2], [1, 0, -1]], dtype=np.float32)
        kernel_y[0] = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float32)
        sx = ndimage.convolve(gray_stack, kernel_x, mode="reflect")
        sy = ndimage.convolve(gray_stack, kernel_y, mode="reflect")
        score = sx * sx + sy * sy
    elif metric is FocusMetric.LOCAL_VARIANCE:
        size = max(1, radius * 2 + 1)
        filter_size = (1, size, size)
        mean = ndimage.uniform_filter(gray_stack, size=filter_size, mode="reflect")
        mean_sq = ndimage.uniform_filter(gray_stack * gray_stack, size=filter_size, mode="reflect")
        return np.maximum(mean_sq - mean * mean, 0.0).astype(np.float32, copy=False)
    elif metric is FocusMetric.SCHARR:
        kernel_x = np.zeros((1, 3, 3), dtype=np.float32)
        kernel_y = np.zeros((1, 3, 3), dtype=np.float32)
        kernel_x[0] = np.array([[3, 0, -3], [10, 0, -10], [3, 0, -3]], dtype=np.float32)
        kernel_y[0] = kernel_x[0].T
        sx = ndimage.convolve(gray_stack, kernel_x, mode="reflect")
        sy = ndimage.convolve(gray_stack, kernel_y, mode="reflect")
        score = sx * sx + sy * sy
    elif metric is FocusMetric.BRENNER:
        offset = max(1, radius)
        score = np.zeros_like(gray_stack, dtype=np.float32)
        dx = gray_stack[:, :, offset:] - gray_stack[:, :, :-offset]
        dy = gray_stack[:, offset:, :] - gray_stack[:, :-offset, :]
        score[:, :, :-offset] += dx * dx
        score[:, :-offset, :] += dy * dy
        return score.astype(np.float32, copy=False)
    elif metric is FocusMetric.WAVELET:
        score = np.zeros_like(gray_stack, dtype=np.float32)
        horizontal = gray_stack[:, :, 1::2] - gray_stack[:, :, ::2][
            :, :, : gray_stack[:, :, 1::2].shape[2]
        ]
        vertical = gray_stack[:, 1::2, :] - gray_stack[:, ::2, :][
            :, : gray_stack[:, 1::2, :].shape[1], :
        ]
        score[:, :, : horizontal.shape[2]] += horizontal * horizontal
        score[:, : vertical.shape[1], :] += vertical * vertical
    else:
        raise ValueError(f"Unsupported focus metric: {metric}")
    if radius > 0:
        size = radius * 2 + 1
        score = _uniform_stack_accelerated(score, size, use_cuda=use_cuda)
    return np.asarray(score, dtype=np.float32)


def custom_stack_parameters(params: FocusStackParameters) -> FocusStackParameters:
    """Return a decompile-style tuned parameter set for confidence-map stacking."""
    detail_level = int(np.clip(params.detail_scale, 1, 10))
    focus_radius = params.focus_radius
    if not params.adaptive_weighting:
        if detail_level <= 3:
            focus_radius = min(focus_radius, 1)
        elif detail_level <= 5:
            focus_radius = min(focus_radius, 2)
    return FocusStackParameters(
        stacking_method=StackingMethod.CUSTOM,
        focus_metric=params.focus_metric,
        focus_radius=max(1, focus_radius),
        smoothing_sigma=max(params.smoothing_sigma, 0.35),
        blend_softness=min(params.blend_softness, 0.08),
        halo_suppression_sigma=max(params.halo_suppression_sigma, 1.0),
        score_threshold=int(np.clip(params.score_threshold, 0, 29)),
        region_bias=params.region_bias,
        scale_preset=max(params.scale_preset, 3),
        adaptive_weighting=params.adaptive_weighting,
        detail_scale=min(max(detail_level, 2), 5),
        background_mode=(
            params.background_mode
            if params.background_mode is not BackgroundMode.MEDIAN
            else BackgroundMode.MIXED
        ),
        confidence_cleanup=True,
        alignment_mode=params.alignment_mode,
        preview_scale=params.preview_scale,
        output_depth_map=params.output_depth_map,
        use_cuda=params.use_cuda,
    )


def custom_confidence_stack(
    images: list[np.ndarray],
    params: FocusStackParameters,
    progress: ProgressCallback | None = None,
    preview: PreviewCallback | None = None,
) -> _PyramidStack:
    """Decompile-style confidence/depth-id stacker for the Custom mode."""
    filtered_scores, depth_map, selected, confidence_map, channel_images, confidence_buffers = (
        incremental_decompiled_custom_buffers(
            images,
            params,
            progress,
            preview,
        )
    )
    _emit(progress, "depth map", 0.65)
    image, confidence_map = combine_decompiled_detail_and_confidence_buffers(
        channel_images,
        confidence_buffers,
        params,
    )
    background = decompiled_background_reference(images, params.background_mode)
    image, confidence_map = decompiled_low_score_transition(
        image,
        channel_images[1],
        background,
        confidence_map,
        params.score_threshold,
    )
    if params.region_bias != 0 and params.score_threshold >= 2:
        confidence_map, depth_map = decompiled_patch_adjust_confidence(
            confidence_map,
            depth_map,
            params.score_threshold,
            params.region_bias,
        )
    if params.confidence_cleanup and params.score_threshold >= 2:
        confidence_map, depth_map = decompiled_ring_supported_confidence_cleanup(
            confidence_map,
            depth_map,
            params.score_threshold,
        )
    image = decompiled_confidence_background_composite(
        image,
        background,
        confidence_map,
        params.score_threshold,
    )
    return _PyramidStack(
        image=np.clip(image, 0.0, 1.0).astype(np.float32, copy=False),
        depth_map=depth_map,
        focus_map=confidence_map,
        weights=np.empty((0, *depth_map.shape), dtype=np.float32),
    )


def legacy_custom_confidence_stack(
    images: list[np.ndarray],
    params: FocusStackParameters,
    progress: ProgressCallback | None = None,
    preview: PreviewCallback | None = None,
) -> _PyramidStack:
    """Previous Custom stacker retained as a comparison reference."""
    filtered_scores, depth_map, selected = incremental_custom_depth_selection(
        images,
        params,
        progress,
        preview,
    )
    normalized_scores = _normalize_scores(filtered_scores)
    regularized = apply_score_threshold_from_normalized(
        filtered_scores, normalized_scores, params.score_threshold
    )
    depth_map = np.asarray(np.argmax(regularized, axis=0), dtype=np.uint16)
    confidence_map = focus_confidence_from_normalized(normalized_scores)
    if params.confidence_cleanup and params.score_threshold >= 2:
        confidence_map, depth_map = decompiled_ring_supported_confidence_cleanup(
            confidence_map,
            depth_map,
            params.score_threshold,
        )
    if params.confidence_cleanup and params.score_threshold >= 2:
        depth_map = clean_depth_map_by_confidence(
            depth_map,
            regularized,
            confidence_map,
            params.score_threshold,
            params.region_bias,
        )
    elif params.region_bias != 0 and params.score_threshold >= 2:
        depth_map = adjust_depth_regions(depth_map, regularized, params.region_bias)
    _emit(progress, "depth map", 0.65)
    selected = _take_pixels_by_depth(images, depth_map)
    image = selected
    structure_map = _stack_structure_confidence(images)
    background = stable_background_reference(images, params.background_mode)
    image = decompiled_confidence_background_composite(
        image,
        background,
        confidence_map,
        params.score_threshold,
    )
    image = suppress_custom_background_grain(
        image,
        background,
        confidence_map,
        structure_map,
    )
    image = apply_custom_detail_filter(image, selected, confidence_map, structure_map, params)
    return _PyramidStack(
        image=np.clip(image, 0.0, 1.0).astype(np.float32, copy=False),
        depth_map=depth_map,
        focus_map=confidence_map,
        weights=np.empty((0, *depth_map.shape), dtype=np.float32),
    )


def incremental_custom_depth_selection(
    images: list[np.ndarray],
    params: FocusStackParameters,
    progress: ProgressCallback | None,
    preview: PreviewCallback | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build Custom focus scores while updating a running hard-selected image."""
    if not images:
        raise ValueError("images must not be empty")
    height, width = images[0].shape[:2]
    best_score = np.full((height, width), -np.inf, dtype=np.float32)
    depth_map = np.zeros((height, width), dtype=np.uint16)
    selected = np.asarray(images[0], dtype=np.float32).copy()
    score_layers: list[np.ndarray] = []
    total = len(images)
    for index, image in enumerate(images):
        score = stack_focus_measure(
            [image],
            params.focus_metric,
            max(1, params.focus_radius),
            use_cuda=params.use_cuda,
        )
        filtered = filter_focus_scores(
            score,
            smoothing_sigma=params.smoothing_sigma,
            detail_scale=params.detail_scale,
            scale_preset=params.scale_preset,
            adaptive_weighting=params.adaptive_weighting,
            use_cuda=params.use_cuda,
        )[0]
        score_layers.append(filtered)
        replace = filtered > best_score
        if np.any(replace):
            best_score[replace] = filtered[replace]
            depth_map[replace] = index
            if selected.ndim == 3:
                selected[replace, :] = np.asarray(image, dtype=np.float32)[replace, :]
            else:
                selected[replace] = np.asarray(image, dtype=np.float32)[replace]
        fraction = 0.30 + ((index + 1) / max(total, 1)) * 0.28
        _emit(progress, f"stacking frame {index + 1}/{total}", fraction)
        _emit_preview(preview, selected, f"Stacking frame {index + 1}/{total}")
    return np.stack(score_layers, axis=0).astype(np.float32, copy=False), depth_map, selected


def incremental_decompiled_custom_buffers(
    images: list[np.ndarray],
    params: FocusStackParameters,
    progress: ProgressCallback | None,
    preview: PreviewCallback | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build the three running source/confidence buffers used by the decompiled stacker."""
    if not images:
        raise ValueError("images must not be empty")
    height, width = images[0].shape[:2]
    channels = 1 if images[0].ndim == 2 else images[0].shape[-1]
    source_buffers = np.repeat(
        np.asarray(images[0], dtype=np.float32)[None, ...],
        3,
        axis=0,
    )
    confidence_buffers = np.zeros((3, height, width), dtype=np.float32)
    depth_buffers = np.zeros((3, height, width), dtype=np.float32)
    hard_best_score = np.full((height, width), -np.inf, dtype=np.float32)
    hard_depth_map = np.zeros((height, width), dtype=np.uint16)
    score_layers: list[np.ndarray] = []
    selected = np.asarray(images[0], dtype=np.float32).copy()
    total = len(images)
    old_weight_coefficients = np.array([0x33, 0x40, 0x55], dtype=np.float32) / 255.0
    for index, image in enumerate(images):
        frame = np.asarray(image, dtype=np.float32)
        scores = decompiled_focus_score_channels(
            frame,
            params.scale_preset,
            use_cuda=params.use_cuda,
        )
        frame_score = np.max(scores, axis=0)
        score_layers.append(frame_score)
        hard_replace = frame_score > hard_best_score
        if np.any(hard_replace):
            hard_best_score[hard_replace] = frame_score[hard_replace]
            hard_depth_map[hard_replace] = index
            if channels == 1:
                selected[hard_replace] = frame[hard_replace]
            else:
                selected[hard_replace, :] = frame[hard_replace, :]
        for channel_index, coefficient in enumerate(old_weight_coefficients):
            new_score = scores[channel_index]
            old_score = confidence_buffers[channel_index]
            replace = new_score > old_score + (1.0 / 255.0)
            if not np.any(replace):
                continue
            old_mix = np.zeros_like(new_score, dtype=np.float32)
            old_mix[replace] = np.clip(
                (old_score[replace] * coefficient) / np.maximum(new_score[replace], 1e-6),
                0.0,
                1.0,
            )
            new_mix = 1.0 - old_mix
            if channels == 1:
                source_buffers[channel_index][replace] = (
                    source_buffers[channel_index][replace] * old_mix[replace]
                    + frame[replace] * new_mix[replace]
                )
            else:
                source_buffers[channel_index][replace, :] = (
                    source_buffers[channel_index][replace, :] * old_mix[replace, None]
                    + frame[replace, :] * new_mix[replace, None]
                )
            confidence_buffers[channel_index][replace] = (
                old_score[replace] * old_mix[replace]
                + new_score[replace] * new_mix[replace]
            )
            depth_buffers[channel_index][replace] = (
                depth_buffers[channel_index][replace] * old_mix[replace]
                + float(index) * new_mix[replace]
            )
        fraction = 0.30 + ((index + 1) / max(total, 1)) * 0.28
        _emit(progress, f"stacking frame {index + 1}/{total}", fraction)
        _emit_preview(preview, source_buffers[1], f"Stacking frame {index + 1}/{total}")
    confidence = combine_decompiled_confidence_buffers(confidence_buffers, params)
    return (
        np.stack(score_layers, axis=0).astype(np.float32, copy=False),
        hard_depth_map,
        selected.astype(np.float32, copy=False),
        confidence.astype(np.float32, copy=False),
        source_buffers.astype(np.float32, copy=False),
        confidence_buffers.astype(np.float32, copy=False),
    )


def decompiled_focus_score_channels(
    image: np.ndarray,
    scale_preset: int,
    use_cuda: bool = False,
) -> np.ndarray:
    """Translate `FUN_0085f120`: three detail/score channels controlled by Filter set."""
    preset = int(np.clip(scale_preset, 1, 5))
    gray = _quantize_unit(decompiled_luminance(image))
    working = gray
    if preset > 4:
        working = _quantize_unit(_downscale_average(working, 2, use_cuda=use_cuda))
    smooth1, detail1 = decompiled_smooth_and_detail(working, use_cuda=use_cuda)
    if preset in (1, 3):
        working = _quantize_unit(_downscale_average(smooth1, 2, use_cuda=use_cuda))
    elif preset in (2, 4, 5):
        working = _quantize_unit(_downscale_average(smooth1, 3, use_cuda=use_cuda))
    else:
        working = smooth1
    smooth2, detail2 = decompiled_smooth_and_detail(working, use_cuda=use_cuda)
    if preset in (1, 3):
        working = _quantize_unit(_downscale_average(smooth2, 2, use_cuda=use_cuda))
    elif preset in (2, 4, 5):
        working = _quantize_unit(_downscale_average(smooth2, 3, use_cuda=use_cuda))
    else:
        working = smooth2
    _smooth3, detail3 = decompiled_smooth_and_detail(working, use_cuda=use_cuda)
    details = [detail1, detail2, detail3]
    scores: list[np.ndarray] = []
    for channel_index, detail in enumerate(details):
        score = decompiled_detail_support_score(detail, channel_index, use_cuda=use_cuda)
        score = _quantize_unit(_resize_map(score, gray.shape, use_cuda=use_cuda))
        if preset > 4:
            score = _quantize_unit(_resize_map(score, gray.shape, use_cuda=use_cuda))
        scores.append(score)
    return _post_smooth_decompiled_scores(np.stack(scores, axis=0), preset, use_cuda=use_cuda)


def decompiled_luminance(image: np.ndarray) -> np.ndarray:
    """Use the decompiled RGB-to-gray weights from `FUN_008644a0`."""
    if image.ndim == 2:
        return image.astype(np.float32, copy=False)
    source = image.astype(np.float32, copy=False)
    return (
        source[..., 0] * (0x36 / 255.0)
        + source[..., 1] * (0x78 / 255.0)
        + source[..., 2] * (0x51 / 255.0)
    ).astype(np.float32, copy=False)


def _quantize_unit(values: np.ndarray) -> np.ndarray:
    """Round a normalized float image to decompiled-style 8-bit precision."""
    return (np.rint(np.clip(values, 0.0, 1.0) * 255.0) / 255.0).astype(
        np.float32,
        copy=False,
    )


def decompiled_smooth_and_detail(
    gray: np.ndarray,
    use_cuda: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the `FUN_0085ec00` neighbor smooth and absolute detail images."""
    source = _quantize_unit(gray)
    smooth = _quantize_unit(decompiled_neighbor_smooth(source, use_cuda=use_cuda))
    detail = _quantize_unit(np.abs(source.astype(np.float32, copy=False) - smooth))
    return smooth.astype(np.float32, copy=False), detail.astype(np.float32, copy=False)


def decompiled_detail_support_score(
    detail: np.ndarray,
    channel_index: int,
    use_cuda: bool = False,
) -> np.ndarray:
    """Translate the 3x3 support and saturating score curve from `FUN_0085ee70`."""
    kernel = np.array(
        [[2.0, 3.0, 2.0], [3.0, 4.0, 3.0], [2.0, 3.0, 2.0]],
        dtype=np.float32,
    )
    detail_byte = np.rint(np.clip(detail, 0.0, 1.0) * 255.0).astype(np.float32)
    support = _filter2d_accelerated(
        detail_byte,
        kernel,
        borderType=cv2.BORDER_REFLECT,
        use_cuda=use_cuda,
    )
    channel_scale = (1.0, 1.16, 1.34)[int(np.clip(channel_index, 0, 2))]
    value = np.rint(support * channel_scale)
    score = np.rint((value * 256.0) / np.maximum(value + 128.0, 1.0))
    return (np.clip(score, 0.0, 255.0) / 255.0).astype(np.float32, copy=False)


def _post_smooth_decompiled_scores(
    scores: np.ndarray,
    scale_preset: int,
    use_cuda: bool = False,
) -> np.ndarray:
    """Apply the sparse weighted score cleanup kernel from `FUN_0085e4d0`."""
    preset = int(np.clip(scale_preset, 1, 5))
    smoothed = np.empty_like(scores, dtype=np.float32)
    for channel_index in range(scores.shape[0]):
        step = preset * (channel_index + 1)
        smoothed[channel_index] = decompiled_sparse_wide_smooth(
            scores[channel_index],
            step,
            use_cuda=use_cuda,
        )
    return smoothed


def decompiled_sparse_wide_smooth(
    values: np.ndarray,
    step: int,
    use_cuda: bool = False,
) -> np.ndarray:
    """Translate the exact sparse `FUN_0085e4d0` kernel for one score channel."""
    step = max(1, int(step))
    source = values.astype(np.float32, copy=False)
    y_margin = 6 * step
    x_margin = 3 * step
    if source.shape[0] <= y_margin * 2 or source.shape[1] <= x_margin * 2:
        return _quantize_unit(source)
    kernel = _decompiled_sparse_wide_kernel(step)
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
def _decompiled_sparse_wide_kernel(step: int) -> np.ndarray:
    """Return the normalized sparse `FUN_0085e4d0` kernel for a channel step."""
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
    return kernel / divisor


def combine_decompiled_detail_and_confidence_buffers(
    source_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> tuple[np.ndarray, np.ndarray]:
    """Combine source and score buffers with the same `FUN_008c1050` weights."""
    weights = decompiled_filter_weights_map(confidence_buffers, params)
    image_weights = weights[..., None] if source_buffers.ndim == 4 else weights
    image = np.sum(source_buffers * image_weights, axis=0)
    confidence = np.sum(confidence_buffers * weights, axis=0)
    return (
        image.astype(np.float32, copy=False),
        confidence.astype(np.float32, copy=False),
    )


def combine_decompiled_detail_buffers(
    source_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Combine only source buffers with the `FUN_008c1050` weight map."""
    weights = decompiled_filter_weights_map(confidence_buffers, params)
    image_weights = weights[..., None] if source_buffers.ndim == 4 else weights
    return np.sum(source_buffers * image_weights, axis=0).astype(np.float32)


def decompiled_filter_weights_map(
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Return fixed or Smart filter weights for high/mid/low detail buffers."""
    if not params.adaptive_weighting:
        weights = np.array(decompiled_fixed_filter_weights(params.detail_scale), dtype=np.float32)
        weights /= max(float(np.sum(weights)), 1.0)
        return weights.reshape(3, 1, 1)
    weights = np.maximum(confidence_buffers.astype(np.float32, copy=False), 0.0)
    weights /= np.maximum(np.sum(weights, axis=0, keepdims=True), 1e-6)
    return weights.astype(np.float32, copy=False)


def combine_decompiled_confidence_buffers(
    confidence_buffers: np.ndarray, params: FocusStackParameters
) -> np.ndarray:
    """Return the confidence channel that the final composite uses."""
    weights = decompiled_filter_weights_map(confidence_buffers, params)
    return np.sum(confidence_buffers * weights, axis=0)


def combine_decompiled_depth_buffers(
    depth_buffers: np.ndarray,
    confidence_buffers: np.ndarray,
    params: FocusStackParameters,
) -> np.ndarray:
    """Combine frame-id/depth buffers using the same filter profile."""
    if not params.adaptive_weighting:
        weights = np.array(decompiled_fixed_filter_weights(params.detail_scale), dtype=np.float32)
        weights /= max(float(np.sum(weights)), 1.0)
        return np.sum(depth_buffers * weights[:, None, None], axis=0)
    weights = confidence_buffers / np.maximum(np.sum(confidence_buffers, axis=0, keepdims=True), 1e-6)
    return np.sum(depth_buffers * weights, axis=0)


def decompiled_patch_adjust_confidence(
    confidence: np.ndarray,
    depth_map: np.ndarray,
    score_threshold: int,
    region_bias: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Translate the narrow/widen confidence-id edit from `FUN_008c3240`."""
    adjustment = int(np.clip(region_bias, -10, 10))
    if adjustment == 0:
        return confidence.astype(np.float32, copy=False), depth_map
    radius = abs(adjustment)
    threshold = min(1.0, (int(np.clip(score_threshold, 0, 29)) * 3.0) / 255.0)
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
        adjusted_confidence[shrink] = max(threshold - (1.0 / 255.0), 0.0)
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
        adjusted_confidence[grow] = min(threshold + (1.0 / 255.0), 1.0)
        adjusted_depth[grow] = np.clip(
            np.rint(weighted_depth[grow] / np.maximum(weight_sum[grow], 1e-6)),
            0,
            max(0, int(np.max(depth_map))),
        ).astype(np.uint16)
    return adjusted_confidence.astype(np.float32, copy=False), adjusted_depth


def decompiled_low_score_transition(
    image: np.ndarray,
    detail_image: np.ndarray,
    background: np.ndarray,
    confidence: np.ndarray,
    score_threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Translate `FUN_008c4770`, the pre-final low-score transition pass."""
    level = int(np.clip(score_threshold, 0, 29))
    if level <= 0:
        return image.astype(np.float32, copy=False), confidence.astype(np.float32, copy=False)
    threshold = min(1.0, (level * 3.0) / 255.0)
    if threshold <= 0:
        return image.astype(np.float32, copy=False), confidence.astype(np.float32, copy=False)
    source_confidence = confidence.astype(np.float32, copy=False)
    low = source_confidence < threshold
    if not np.any(low):
        return image.astype(np.float32, copy=False), source_confidence
    current_weight = np.zeros_like(source_confidence, dtype=np.float32)
    current_weight[low] = np.clip(
        source_confidence[low] * 127.0 / np.maximum(threshold * 255.0, 1e-6),
        0.0,
        1.0,
    )
    detail_weight = current_weight * 0.5
    background_weight = np.clip(1.0 - (current_weight + detail_weight), 0.0, 1.0)
    if image.ndim == 3:
        current_weight = current_weight[..., None]
        detail_weight = detail_weight[..., None]
        background_weight = background_weight[..., None]
    else:
        low = low
    blended = image * current_weight + detail_image * detail_weight + background * background_weight
    transitioned = np.where(low[..., None] if image.ndim == 3 else low, blended, image)
    smooth_confidence = decompiled_low_score_confidence_smooth(source_confidence)
    adjusted_confidence = source_confidence.copy()
    adjusted_confidence[low] = smooth_confidence[low]
    return transitioned.astype(np.float32, copy=False), adjusted_confidence.astype(
        np.float32, copy=False
    )


def decompiled_low_score_confidence_smooth(confidence: np.ndarray) -> np.ndarray:
    """Use the `FUN_008c4770` 3x3 score/id smoothing stencil."""
    kernel = np.array(
        [[2.0, 3.0, 2.0], [3.0, 4.0, 3.0], [2.0, 3.0, 2.0]],
        dtype=np.float32,
    )
    kernel /= 24.0
    return cv2.filter2D(
        confidence.astype(np.float32, copy=False),
        -1,
        kernel,
        borderType=cv2.BORDER_REFLECT,
    )


def _downscale_average(
    image: np.ndarray,
    factor: int,
    use_cuda: bool = False,
) -> np.ndarray:
    factor = int(max(1, factor))
    if factor <= 1:
        return image.astype(np.float32, copy=False)
    height, width = image.shape[:2]
    out_h = max(1, height // factor)
    out_w = max(1, width // factor)
    resized = _resize_accelerated(
        image.astype(np.float32, copy=False),
        (out_w, out_h),
        interpolation=cv2.INTER_AREA,
        use_cuda=use_cuda,
    )
    return np.asarray(resized, dtype=np.float32)


def _resize_map(
    image: np.ndarray,
    shape: tuple[int, int],
    use_cuda: bool = False,
) -> np.ndarray:
    if image.shape[:2] == shape:
        return image.astype(np.float32, copy=False)
    resized = _resize_accelerated(
        image.astype(np.float32, copy=False),
        (shape[1], shape[0]),
        interpolation=cv2.INTER_LINEAR,
        use_cuda=use_cuda,
    )
    return np.asarray(resized, dtype=np.float32)


def _filter2d_accelerated(
    image: np.ndarray,
    kernel: np.ndarray,
    *,
    borderType: int,
    use_cuda: bool = False,
) -> np.ndarray:
    source = image.astype(np.float32, copy=False)
    if not use_cuda or source.ndim != 2 or not _cuda_available():
        return cv2.filter2D(source, -1, kernel, borderType=borderType)
    try:
        gpu = cv2.cuda_GpuMat()
        gpu.upload(source)
        linear_filter = cv2.cuda.createLinearFilter(
            cv2.CV_32F,
            cv2.CV_32F,
            kernel.astype(np.float32, copy=False),
            borderMode=borderType,
        )
        return linear_filter.apply(gpu).download().astype(np.float32, copy=False)
    except cv2.error:
        return cv2.filter2D(source, -1, kernel, borderType=borderType)


def _resize_accelerated(
    image: np.ndarray,
    size: tuple[int, int],
    *,
    interpolation: int,
    use_cuda: bool = False,
) -> np.ndarray:
    source = image.astype(np.float32, copy=False)
    if not use_cuda or source.ndim != 2 or not _cuda_available():
        return cv2.resize(source, size, interpolation=interpolation)
    try:
        gpu = cv2.cuda_GpuMat()
        gpu.upload(source)
        return cv2.cuda.resize(gpu, size, interpolation=interpolation).download().astype(
            np.float32,
            copy=False,
        )
    except cv2.error:
        return cv2.resize(source, size, interpolation=interpolation)


def _gaussian_stack_accelerated(
    scores: np.ndarray,
    sigma: float,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    source = scores.astype(np.float32, copy=False)
    if sigma <= 0:
        return source
    ksize = max(3, int(np.ceil(float(sigma) * 6.0)) | 1)
    output = np.empty_like(source, dtype=np.float32)
    for index in range(source.shape[0]):
        output[index] = _gaussian_blur_accelerated(
            source[index],
            ksize,
            sigma,
            use_cuda=use_cuda,
        )
    return output


def _gaussian_blur_accelerated(
    image: np.ndarray,
    ksize: int,
    sigma: float,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    source = image.astype(np.float32, copy=False)
    if not use_cuda or source.ndim != 2 or not _cuda_available():
        return cv2.GaussianBlur(
            source,
            (ksize, ksize),
            sigmaX=sigma,
            sigmaY=sigma,
            borderType=cv2.BORDER_REFLECT,
        )
    try:
        gpu = cv2.cuda_GpuMat()
        gpu.upload(source)
        gaussian = cv2.cuda.createGaussianFilter(
            cv2.CV_32F,
            cv2.CV_32F,
            (ksize, ksize),
            sigma1=sigma,
            sigma2=sigma,
            borderMode=cv2.BORDER_REFLECT,
        )
        return gaussian.apply(gpu).download().astype(np.float32, copy=False)
    except (AttributeError, cv2.error):
        return cv2.GaussianBlur(
            source,
            (ksize, ksize),
            sigmaX=sigma,
            sigmaY=sigma,
            borderType=cv2.BORDER_REFLECT,
        )


def _uniform_stack_accelerated(
    scores: np.ndarray,
    size: int,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    if size <= 1:
        return scores.astype(np.float32, copy=False)
    kernel = np.full((size, size), 1.0 / float(size * size), dtype=np.float32)
    source = scores.astype(np.float32, copy=False)
    output = np.empty_like(source, dtype=np.float32)
    for index in range(source.shape[0]):
        output[index] = _filter2d_accelerated(
            source[index],
            kernel,
            borderType=cv2.BORDER_REFLECT,
            use_cuda=use_cuda,
        )
    return output


def _stack_focus_measure_accelerated(
    images: list[np.ndarray],
    metric: FocusMetric,
    radius: int,
) -> np.ndarray | None:
    if metric not in {
        FocusMetric.LAPLACIAN,
        FocusMetric.MODIFIED_LAPLACIAN,
        FocusMetric.TENEGRAD,
        FocusMetric.SCHARR,
    }:
        return None
    layers: list[np.ndarray] = []
    for image in images:
        gray = to_luminance(image).astype(np.float32, copy=False)
        try:
            filtered = _focus_measure_frame_accelerated(gray, metric)
        except cv2.error:
            return None
        layers.append(filtered)
    score = np.stack(layers, axis=0).astype(np.float32, copy=False)
    if radius > 0:
        score = _uniform_stack_accelerated(score, radius * 2 + 1, use_cuda=True)
    return score


def _focus_measure_frame_accelerated(gray: np.ndarray, metric: FocusMetric) -> np.ndarray:
    gpu = cv2.cuda_GpuMat()
    gpu.upload(gray.astype(np.float32, copy=False))
    if metric is FocusMetric.LAPLACIAN:
        kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        lap = _apply_gpu_linear_filter(gpu, kernel).download()
        return np.abs(lap).astype(np.float32, copy=False)
    if metric is FocusMetric.MODIFIED_LAPLACIAN:
        kernel_x = np.array([[0, 0, 0], [-1, 2, -1], [0, 0, 0]], dtype=np.float32)
        kernel_y = kernel_x.T
        sx = _apply_gpu_linear_filter(gpu, kernel_x).download()
        sy = _apply_gpu_linear_filter(gpu, kernel_y).download()
        return (np.abs(sx) + np.abs(sy)).astype(np.float32, copy=False)
    if metric is FocusMetric.TENEGRAD:
        kernel_x = np.array([[1, 0, -1], [2, 0, -2], [1, 0, -1]], dtype=np.float32)
        kernel_y = kernel_x.T
        sx = _apply_gpu_linear_filter(gpu, kernel_x).download()
        sy = _apply_gpu_linear_filter(gpu, kernel_y).download()
        return (sx * sx + sy * sy).astype(np.float32, copy=False)
    if metric is FocusMetric.SCHARR:
        kernel_x = np.array([[3, 0, -3], [10, 0, -10], [3, 0, -3]], dtype=np.float32)
        kernel_y = kernel_x.T
        sx = _apply_gpu_linear_filter(gpu, kernel_x).download()
        sy = _apply_gpu_linear_filter(gpu, kernel_y).download()
        return (sx * sx + sy * sy).astype(np.float32, copy=False)
    raise ValueError(f"Unsupported CUDA focus metric: {metric}")


def _apply_gpu_linear_filter(gpu: object, kernel: np.ndarray) -> object:
    linear_filter = cv2.cuda.createLinearFilter(
        cv2.CV_32F,
        cv2.CV_32F,
        kernel.astype(np.float32, copy=False),
        borderMode=cv2.BORDER_REFLECT,
    )
    return linear_filter.apply(gpu)


@lru_cache(maxsize=1)
def _cuda_available() -> bool:
    try:
        return bool(hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0)
    except cv2.error:
        return False


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
    level = int(np.clip(score_threshold, 0, 29))
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


def decompiled_ring_supported_confidence_cleanup(
    confidence: np.ndarray,
    depth_map: np.ndarray,
    score_threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the sparse ring confidence propagation from the decompiled stacker."""
    level = int(np.clip(score_threshold, 0, 29))
    if level < 2:
        return confidence.astype(np.float32, copy=False), depth_map
    threshold = min(1.0, (level * 3.0) / 255.0)
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
            shifted_conf = _shift_map_constant(source_confidence, dy, dx, 0.0)
            strong = shifted_conf > threshold
            ring_count += strong.astype(np.float32)
            ring_depth_sum += _shift_map_constant(source_depth, dy, dx, 0.0) * strong
        use_ring = unresolved & (support_count < 3)
        support_count[use_ring] += ring_count[use_ring]
        depth_sum[use_ring] += ring_depth_sum[use_ring]
        unresolved &= support_count < 3
        if not np.any(unresolved):
            break
    local_evidence = np.maximum(
        source_confidence,
        decompiled_low_score_confidence_smooth(source_confidence),
    )
    supported = (support_count > 1) & (local_evidence >= threshold * 0.55)
    cleaned_confidence = source_confidence.copy()
    cleaned_depth = np.asarray(depth_map, dtype=np.uint16).copy()
    cleaned_confidence[supported] = max(threshold + (1.0 / 255.0), 0.0)
    cleaned_depth[supported] = np.clip(
        np.rint(depth_sum[supported] / np.maximum(support_count[supported], 1.0)),
        0,
        max(0, int(np.max(depth_map))),
    ).astype(np.uint16)
    return cleaned_confidence.astype(np.float32, copy=False), cleaned_depth


def decompiled_confidence_background_composite(
    image: np.ndarray,
    background: np.ndarray,
    confidence: np.ndarray,
    score_threshold: int,
) -> np.ndarray:
    """Blend low-confidence pixels with the decompiled final composite formula."""
    level = int(np.clip(score_threshold, 0, 29))
    if level <= 0:
        return image.astype(np.float32, copy=False)
    threshold = min(1.0, (level * 3.0) / 255.0)
    confidence = confidence.astype(np.float32, copy=False)
    current_weight = np.ones_like(confidence, dtype=np.float32)
    low = confidence <= threshold
    if np.any(low):
        current_weight[low] = np.clip(
            (confidence[low] * 2.0) / np.maximum(threshold + confidence[low], 1e-6),
            0.0,
            1.0,
        )
    if image.ndim == 3:
        current_weight = current_weight[..., None]
    return (image * current_weight + background * (1.0 - current_weight)).astype(
        np.float32, copy=False
    )


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
    detail_level = int(np.clip(params.detail_scale, 1, 10))
    scale_preset = int(np.clip(params.scale_preset, 1, 5))
    source = (
        decompiled_fixed_filter_blend(selected, detail_level)
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


def decompiled_fixed_filter_blend(image: np.ndarray, detail_level: int) -> np.ndarray:
    """Approximate the decompiled three-buffer fixed filter using exact UI weights."""
    w_high, w_mid, w_low = decompiled_fixed_filter_weights(detail_level)
    if w_high == 255 and w_mid == 0 and w_low == 0:
        return image.astype(np.float32, copy=False)
    high = image.astype(np.float32, copy=False)
    mid = decompiled_neighbor_smooth(high)
    low = decompiled_neighbor_smooth(mid)
    return ((high * w_high + mid * w_mid + low * w_low) / 255.0).astype(
        np.float32, copy=False
    )


def decompiled_neighbor_smooth(image: np.ndarray, use_cuda: bool = False) -> np.ndarray:
    """Use the 8-neighbor stencil from `FUN_0085ec00`."""
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


def decompiled_fixed_filter_weights(detail_level: int) -> tuple[int, int, int]:
    """Return exact fixed-filter weights inferred from `FUN_008c1050`."""
    level = int(np.clip(detail_level, 1, 10))
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


def decompiled_background_reference(
    images: list[np.ndarray], mode: BackgroundMode = BackgroundMode.MIXED
) -> np.ndarray:
    """Build the Custom background from running dark/bright/average buffers."""
    if mode is BackgroundMode.FIRST:
        return np.asarray(images[0], dtype=np.float32)
    if mode is BackgroundMode.LAST:
        return np.asarray(images[-1], dtype=np.float32)
    stack = np.stack(images, axis=0).astype(np.float32, copy=False)
    if mode is BackgroundMode.MEDIAN:
        mode = BackgroundMode.MIXED
    luminance = np.stack([decompiled_luminance(image) for image in stack], axis=0)
    if mode is BackgroundMode.DARKEST:
        chooser = np.argmin(luminance, axis=0)
        return _take_pixels_from_stack(stack, chooser)
    if mode is BackgroundMode.BRIGHTEST:
        chooser = np.argmax(luminance, axis=0)
        return _take_pixels_from_stack(stack, chooser)
    darkest = _take_pixels_from_stack(stack, np.argmin(luminance, axis=0))
    brightest = _take_pixels_from_stack(stack, np.argmax(luminance, axis=0))
    if mode is BackgroundMode.MIXED:
        return ((darkest + brightest) * 0.5).astype(np.float32, copy=False)
    return np.mean(stack, axis=0).astype(np.float32, copy=False)


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
    zoom = (scale, scale) if array.ndim == 2 else (scale, scale, 1)
    return ndimage.zoom(array, zoom=zoom, order=1)


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


def _as_float(value: object) -> float:
    if isinstance(value, (str, bytes, int, float)):
        return float(value)
    raise TypeError(f"Expected numeric value, got {type(value).__name__}")


def _as_int(value: object) -> int:
    if isinstance(value, (str, bytes, int, float)):
        return int(value)
    raise TypeError(f"Expected integer value, got {type(value).__name__}")
