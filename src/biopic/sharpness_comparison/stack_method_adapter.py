"""Connect comparison methods to the existing stack processor."""

from __future__ import annotations

from dataclasses import replace

from biopic.imaging.stacking import FocusMetric, FocusStackParameters, StackingMethod
from biopic.sharpness_comparison.config_models import SharpnessMethodConfig


METHOD_TO_FOCUS_METRIC = {
    "laplacian": FocusMetric.LAPLACIAN,
    "modified_laplacian": FocusMetric.MODIFIED_LAPLACIAN,
    "tenengrad": FocusMetric.TENEGRAD,
    "scharr": FocusMetric.SCHARR,
    "brenner": FocusMetric.BRENNER,
    "local_variance": FocusMetric.LOCAL_VARIANCE,
    "wavelet": FocusMetric.WAVELET,
}


def parameters_for_method(
    base: FocusStackParameters,
    method: SharpnessMethodConfig,
) -> FocusStackParameters:
    """Return stack parameters for one comparison method."""
    if method.method_id == "current":
        return base
    metric = METHOD_TO_FOCUS_METRIC[method.method_id]
    radius = base.focus_radius
    if method.method_id == "local_variance":
        radius = max(1, int(method.parameters.get("window_size", 9)) // 2)
    if method.method_id == "brenner":
        radius = max(1, int(method.parameters.get("offset", 2)))
    return replace(
        base,
        stacking_method=StackingMethod.DEPTH_MAP,
        focus_metric=metric,
        focus_radius=radius,
    )
