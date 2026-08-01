"""Run stack sharpness comparison using the existing stacker."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

import numpy as np

from biopic.imaging.stacking import FocusStackParameters, focus_stack
from biopic.sharpness_comparison.config_models import (
    SharpnessComparisonConfig,
    SharpnessComparisonResult,
    SharpnessComparisonSummary,
)
from biopic.sharpness_comparison.metrics import automatic_foreground_mask, evaluate_metrics
from biopic.sharpness_comparison.normalization import normalize_scores
from biopic.sharpness_comparison.ranking import apply_combined_scores_and_ranks
from biopic.sharpness_comparison.stack_method_adapter import parameters_for_method
from biopic.sharpness_comparison.temporary_results import TemporaryResultStore


def run_comparison(
    *,
    images: list[np.ndarray],
    base_parameters: FocusStackParameters,
    config: SharpnessComparisonConfig,
    project_id: str,
    stack_name: str,
    progress: object | None = None,
    cancelled: object | None = None,
) -> SharpnessComparisonSummary:
    """Generate and evaluate enabled comparison stack results."""
    methods = [method for method in config.methods if method.enabled]
    store = TemporaryResultStore(project_id)
    mask = automatic_foreground_mask(images)
    results: list[SharpnessComparisonResult] = []
    warnings = [
        "Sharpness scores are relative. Noise, halos, oversharpening and compression can increase scores."
    ]
    expected_shape: tuple[int, ...] | None = None
    for index, method in enumerate(methods, start=1):
        if cancelled is not None and cancelled():
            break
        _emit(
            progress,
            f"Sharpness comparison: running {method.display_name}",
            (index - 1) / max(len(methods), 1),
        )
        parameters = parameters_for_method(base_parameters, method)
        start = perf_counter()
        try:
            stack_result = focus_stack(images, parameters)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{method.display_name} failed: {exc}")
            continue
        runtime = perf_counter() - start
        if expected_shape is None:
            expected_shape = tuple(stack_result.image.shape)
        elif tuple(stack_result.image.shape) != expected_shape:
            warnings.append(
                f"{method.display_name} excluded because its result dimensions differ."
            )
            continue
        path = store.save(method.method_id, stack_result.image)
        sigma = config.gaussian_sigma if config.noise_reduction == "mild_gaussian" else 0.0
        raw_scores = evaluate_metrics(stack_result.image, mask, gaussian_sigma=sigma)
        results.append(
            SharpnessComparisonResult(
                result_id=uuid4().hex,
                method_id=method.method_id,
                method_name=method.display_name,
                temporary_path=path,
                runtime_seconds=runtime,
                raw_scores=raw_scores,
                normalized_scores={},
                combined_score=0.0,
                rank=0,
                settings_snapshot=parameters.to_dict(),
            )
        )
    normalized = normalize_scores([result.raw_scores for result in results])
    for result, scores in zip(results, normalized, strict=False):
        result.normalized_scores = scores
    weights = {method.method_id: method.evaluation_weight for method in config.methods}
    apply_combined_scores_and_ranks(results, weights)
    _emit(progress, "Sharpness comparison complete", 1.0)
    return SharpnessComparisonSummary(
        stack_name=stack_name,
        source_count=len(images),
        image_shape=tuple(images[0].shape),
        dtype=str(images[0].dtype),
        preset_name=config.preset_name,
        analysis_region=config.analysis_region,
        temporary_dir=store.directory,
        results=results,
        warnings=warnings,
    )


def _emit(progress: object | None, message: str, fraction: float) -> None:
    if progress is not None:
        progress(message, fraction)
