"""Ranking utilities for sharpness comparison."""

from __future__ import annotations

from biopic.sharpness_comparison.config_models import SharpnessComparisonResult


def apply_combined_scores_and_ranks(
    results: list[SharpnessComparisonResult],
    weights: dict[str, float],
) -> None:
    """Set combined scores and stable descending ranks in-place."""
    for result in results:
        total_weight = 0.0
        total = 0.0
        for metric, score in result.normalized_scores.items():
            weight = float(weights.get(metric, 1.0))
            if weight <= 0:
                continue
            total += score * weight
            total_weight += weight
        result.combined_score = total / total_weight if total_weight > 0 else 0.0
    ordered = sorted(
        enumerate(results),
        key=lambda item: (-item[1].combined_score, item[0]),
    )
    for rank, (_index, result) in enumerate(ordered, start=1):
        result.rank = rank
