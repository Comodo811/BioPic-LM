"""Score normalization for sharpness comparison."""

from __future__ import annotations

import numpy as np


def normalize_scores(raw_scores: list[dict[str, float]]) -> list[dict[str, float]]:
    """Normalize metric scores across results without averaging raw values."""
    if not raw_scores:
        return []
    metric_ids = sorted({metric for scores in raw_scores for metric in scores})
    normalized = [{metric: 0.0 for metric in metric_ids} for _ in raw_scores]
    for metric in metric_ids:
        values = np.array([scores.get(metric, np.nan) for scores in raw_scores], dtype=np.float64)
        valid = np.isfinite(values)
        if not np.any(valid):
            continue
        valid_values = values[valid]
        if len(valid_values) >= 5:
            low = float(np.percentile(valid_values, 5.0))
            high = float(np.percentile(valid_values, 95.0))
        else:
            low = float(np.min(valid_values))
            high = float(np.max(valid_values))
        span = high - low
        if span <= 1e-12:
            for item in normalized:
                item[metric] = 0.5
            continue
        for index, value in enumerate(values):
            normalized[index][metric] = float(np.clip((value - low) / span, 0.0, 1.0))
    return normalized
