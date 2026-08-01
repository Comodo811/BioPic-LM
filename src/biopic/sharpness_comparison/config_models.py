"""Structured models for stack sharpness comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SharpnessMethodConfig:
    """One generated stack variant in a sharpness comparison run."""

    method_id: str
    display_name: str
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)
    evaluation_weight: float = 1.0


@dataclass(slots=True)
class SharpnessComparisonConfig:
    """Complete settings snapshot for a comparison run."""

    preset_name: str
    methods: list[SharpnessMethodConfig]
    analysis_region: str = "automatic_foreground"
    normalization: str = "percentile_1_99"
    noise_reduction: str = "none"
    gaussian_sigma: float = 0.7


@dataclass(slots=True)
class SharpnessComparisonResult:
    """One generated stack image plus evaluation scores."""

    result_id: str
    method_id: str
    method_name: str
    temporary_path: Path
    runtime_seconds: float
    raw_scores: dict[str, float]
    normalized_scores: dict[str, float]
    combined_score: float
    rank: int
    settings_snapshot: dict[str, Any]


@dataclass(slots=True)
class SharpnessComparisonSummary:
    """All comparison results for one source stack."""

    stack_name: str
    source_count: int
    image_shape: tuple[int, ...]
    dtype: str
    preset_name: str
    analysis_region: str
    temporary_dir: Path
    results: list[SharpnessComparisonResult]
    warnings: list[str] = field(default_factory=list)
