"""Focus-stacking model types and parameter parsing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum

import numpy as np

from biopic.imaging.stacking.alignment import AlignmentTransform
from biopic.imaging.stacking.focus_metrics import FocusMetric


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
    reverse_order: bool = False
    preview_scale: float = 1.0
    output_depth_map: bool = True
    skip_final_depth_buffer: bool = False
    debug_save_stages: bool = False
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
            reverse_order=bool(data.get("reverse_order", False)),
            preview_scale=_as_float(data.get("preview_scale", 1.0)),
            output_depth_map=bool(data.get("output_depth_map", True)),
            skip_final_depth_buffer=bool(data.get("skip_final_depth_buffer", False)),
            debug_save_stages=bool(data.get("debug_save_stages", False)),
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



def _as_float(value: object) -> float:
    if isinstance(value, (str, bytes, int, float)):
        return float(value)
    raise TypeError(f"Expected numeric value, got {type(value).__name__}")


def _as_int(value: object) -> int:
    return int(round(_as_float(value)))
