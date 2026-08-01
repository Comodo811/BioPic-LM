"""Depth-map weighted focus-stacking method."""

from __future__ import annotations

import numpy as np


def stack_depth_map(images: list[np.ndarray], parameters: object) -> object:
    """Run the regular depth-map focus-stacking method."""
    from biopic.imaging.stacking import stacker as core
    from biopic.imaging.stacking.gpu_depth_map import stack_depth_map_gpu

    gpu_result = stack_depth_map_gpu(images, parameters)
    if gpu_result is not None:
        return gpu_result

    scores = core.stack_focus_measure(
        images,
        parameters.focus_metric,
        max(1, parameters.focus_radius),
        use_cuda=parameters.use_cuda,
    )
    filtered_scores = core.filter_focus_scores(
        scores,
        smoothing_sigma=parameters.smoothing_sigma,
        detail_scale=parameters.detail_scale,
        scale_preset=parameters.scale_preset,
        adaptive_weighting=parameters.adaptive_weighting,
        use_cuda=parameters.use_cuda,
    )
    regularized = core.apply_score_threshold(filtered_scores, parameters.score_threshold)
    depth_map = np.asarray(np.argmax(regularized, axis=0), dtype=np.uint16)
    confidence_map = core.focus_confidence_map(filtered_scores)
    if parameters.confidence_cleanup and parameters.score_threshold >= 2:
        depth_map = core.clean_depth_map_by_confidence(
            depth_map,
            regularized,
            confidence_map,
            parameters.score_threshold,
            parameters.region_bias,
        )
        regularized = core.enforce_depth_map(regularized, depth_map)
    elif parameters.region_bias != 0 and parameters.score_threshold >= 2:
        depth_map = core.adjust_depth_regions(depth_map, regularized, parameters.region_bias)
        regularized = core.enforce_depth_map(regularized, depth_map)

    weights = core.focus_weights(regularized, core.effective_blend_softness(parameters))
    blended = core.blend_stack(images, weights)
    if parameters.halo_suppression_sigma > 0:
        blended = core.suppress_halos(
            blended,
            images,
            weights,
            parameters.halo_suppression_sigma,
        )
    structure_map = core._stack_structure_confidence(images)
    blended = core.blend_low_confidence_background(
        blended,
        images,
        filtered_scores,
        parameters.score_threshold,
        parameters.background_mode,
        confidence_map,
        structure_map,
    )
    blended = core.preserve_specimen_detail(
        blended,
        images,
        weights,
        parameters,
        structure_map,
    )
    return core._PyramidStack(
        image=blended,
        depth_map=depth_map,
        focus_map=regularized,
        weights=weights,
    )
