"""Preset definitions for stack sharpness comparison."""

from __future__ import annotations

from biopic.sharpness_comparison.config_models import (
    SharpnessComparisonConfig,
    SharpnessMethodConfig,
)


METHODS: dict[str, tuple[str, float]] = {
    "modified_laplacian": ("Modified Laplacian", 1.5),
    "tenengrad": ("Tenengrad", 1.5),
    "laplacian": ("Laplacian variance", 0.75),
    "scharr": ("Scharr energy", 1.0),
    "brenner": ("Brenner gradient", 0.5),
    "local_variance": ("Local variance", 1.0),
    "wavelet": ("Wavelet energy", 1.25),
    "current": ("Current user stack settings", 1.0),
}


PRESET_METHODS: dict[str, set[str]] = {
    "Fast comparison": {"modified_laplacian", "tenengrad", "laplacian"},
    "Standard microscopy comparison": {
        "modified_laplacian",
        "tenengrad",
        "scharr",
        "local_variance",
        "wavelet",
        "current",
    },
    "Noise-resistant comparison": {
        "modified_laplacian",
        "tenengrad",
        "local_variance",
        "wavelet",
        "laplacian",
    },
    "Fine-detail comparison": {
        "modified_laplacian",
        "scharr",
        "wavelet",
        "local_variance",
        "brenner",
    },
    "Custom": set(METHODS),
}


def preset_names() -> list[str]:
    """Return available preset labels in UI order."""
    return list(PRESET_METHODS)


def config_for_preset(name: str) -> SharpnessComparisonConfig:
    """Create a comparison config from a preset name."""
    enabled = PRESET_METHODS.get(name, PRESET_METHODS["Standard microscopy comparison"])
    methods: list[SharpnessMethodConfig] = []
    for method_id, (display_name, weight) in METHODS.items():
        method_weight = weight
        if name == "Noise-resistant comparison" and method_id == "laplacian":
            method_weight = 0.35
        parameters = _default_parameters(method_id, name)
        methods.append(
            SharpnessMethodConfig(
                method_id=method_id,
                display_name=display_name,
                enabled=method_id in enabled,
                parameters=parameters,
                evaluation_weight=method_weight,
            )
        )
    noise = "mild_gaussian" if name == "Noise-resistant comparison" else "none"
    return SharpnessComparisonConfig(
        preset_name=name,
        methods=methods,
        noise_reduction=noise,
        gaussian_sigma=0.7,
    )


def _default_parameters(method_id: str, preset_name: str) -> dict[str, object]:
    if method_id == "local_variance":
        return {"window_size": 5 if preset_name == "Fine-detail comparison" else 9}
    if method_id == "tenengrad":
        return {"kernel_size": 3, "gradient_threshold": 0.0}
    if method_id == "brenner":
        return {"offset": 2}
    if method_id == "wavelet":
        return {"wavelet": "haar", "levels": 1}
    return {"kernel_size": 3}
