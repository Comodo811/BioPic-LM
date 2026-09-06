"""Focus-stacking public facade."""

from __future__ import annotations

import numpy as np

from biopic.imaging.stacking.alignment import AlignmentTransform, align_stack_translation
from biopic.imaging.stacking.focus_metrics import FocusMetric
from biopic.imaging.stacking.private_methods import private_stacking_enabled
from biopic.imaging.stacking.stack_types import (
    AlignmentMode,
    BackgroundMode,
    FocusStackParameters,
    FocusStackResult,
    PreviewCallback,
    ProgressCallback,
    StackingMethod,
)
from biopic.imaging.stacking.shared import (
    _PyramidStack,
    _as_float_image,
    _emit,
    _emit_preview,
    _restore_dtype,
    _resize_preview,
    _stack_structure_confidence,
    _validate_images,
    adjust_depth_regions,
    apply_score_threshold,
    apply_score_threshold_from_normalized,
    auto_orient_stack_images,
    blend_low_confidence_background,
    blend_stack,
    clean_depth_map_by_confidence,
    combine_reference_confidence_buffers,
    combine_reference_depth_buffers,
    combine_reference_detail_and_confidence_buffers,
    combine_reference_detail_buffers,
    reference_background_reference,
    reference_confidence_background_composite,
    reference_detail_support_score,
    reference_filter_weight_bytes_map,
    reference_filter_weights_map,
    reference_fixed_filter_blend,
    reference_fixed_filter_weights,
    reference_focus_score_channels,
    reference_luminance,
    reference_low_score_confidence_smooth,
    reference_low_score_transition,
    reference_neighbor_smooth,
    reference_output_color_response,
    reference_patch_adjust_confidence,
    reference_ring_supported_confidence_cleanup,
    reference_smart_filter_weight_bytes_map,
    reference_smart_filter_weights_map,
    reference_smooth_and_detail,
    reference_source_buffer_image,
    reference_sparse_wide_smooth,
    reference_stack_mode_three_working_image,
    reference_suppression_buffer_blend,
    reference_suppression_id_blend,
    effective_blend_softness,
    enforce_depth_map,
    filter_focus_scores,
    focus_confidence_from_normalized,
    focus_confidence_map,
    focus_weights,
    preserve_specimen_detail,
    regularize_focus_scores,
    stable_background_reference,
    stack_focus_measure,
    suppress_custom_background_grain,
    suppress_halos,
)
from biopic.imaging.stacking.methods.custom import (
    _expand_reference_working_scores,
    _resize_reference_score_channel,
    custom_confidence_stack,
    custom_stack_parameters,
    incremental_custom_depth_selection,
    incremental_reference_custom_buffers,
    legacy_custom_confidence_stack,
)
from biopic.imaging.stacking.methods.pmax import pyramid_max_contrast_stack


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
    if params.reverse_order:
        images = list(reversed(images))
    working = [_as_float_image(_resize_preview(image, params.preview_scale)) for image in images]
    _emit(progress, "loaded", 0.05)

    if params.alignment_mode is AlignmentMode.TRANSLATION:
        working, transforms = align_stack_translation(
            working,
            use_cuda=params.use_cuda,
            refine_euclidean=params.stacking_method is not StackingMethod.CUSTOM,
        )
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


__all__ = [
    "AlignmentMode",
    "BackgroundMode",
    "FocusMetric",
    "FocusStackParameters",
    "FocusStackResult",
    "PreviewCallback",
    "ProgressCallback",
    "StackingMethod",
    "adjust_depth_regions",
    "apply_score_threshold",
    "apply_score_threshold_from_normalized",
    "auto_orient_stack_images",
    "blend_low_confidence_background",
    "blend_stack",
    "clean_depth_map_by_confidence",
    "combine_reference_confidence_buffers",
    "combine_reference_depth_buffers",
    "combine_reference_detail_and_confidence_buffers",
    "combine_reference_detail_buffers",
    "custom_confidence_stack",
    "custom_stack_parameters",
    "reference_background_reference",
    "reference_confidence_background_composite",
    "reference_detail_support_score",
    "reference_filter_weight_bytes_map",
    "reference_filter_weights_map",
    "reference_fixed_filter_blend",
    "reference_fixed_filter_weights",
    "reference_focus_score_channels",
    "reference_luminance",
    "reference_low_score_confidence_smooth",
    "reference_low_score_transition",
    "reference_neighbor_smooth",
    "reference_output_color_response",
    "reference_patch_adjust_confidence",
    "reference_ring_supported_confidence_cleanup",
    "reference_smart_filter_weight_bytes_map",
    "reference_smart_filter_weights_map",
    "reference_smooth_and_detail",
    "reference_source_buffer_image",
    "reference_sparse_wide_smooth",
    "reference_stack_mode_three_working_image",
    "reference_suppression_buffer_blend",
    "reference_suppression_id_blend",
    "effective_blend_softness",
    "enforce_depth_map",
    "filter_focus_scores",
    "focus_confidence_from_normalized",
    "focus_confidence_map",
    "focus_stack",
    "focus_weights",
    "incremental_custom_depth_selection",
    "incremental_reference_custom_buffers",
    "legacy_custom_confidence_stack",
    "preserve_specimen_detail",
    "pyramid_max_contrast_stack",
    "regularize_focus_scores",
    "stable_background_reference",
    "stack_focus_measure",
    "suppress_custom_background_grain",
    "suppress_halos",
]
