"""Operation metadata used by the edit workspace."""

from __future__ import annotations


def is_adjustment_operation(operation: str) -> bool:
    return operation in {
        "levels",
        "auto_levels",
        "gamma",
        "curve",
        "invert",
        "threshold",
        "white_balance",
        "color_saturation",
    }


def is_filter_result_layer_operation(operation: str) -> bool:
    return operation in {
        "flat_field_correction_estimated",
        "flat_field",
        "subtract_background_estimated",
        "high_pass",
        "gaussian",
        "median",
        "sharpen",
        "denoise",
        "total_variation",
        "wavelet_sharpen",
        "local_contrast",
        "deconvolution",
        "uniform_background_outside_selection",
        "healed_uniform_background_outside_selection",
    }


def operation_layer_name(operation: str) -> str:
    names = {
        "levels": "Levels / Tonwertkorrektur",
        "auto_levels": "Auto Levels",
        "gamma": "Gamma Correction",
        "curve": "Curves / Gradationskurve",
        "invert": "Invert",
        "threshold": "Threshold",
        "white_balance": "White Balance",
        "flat_field_correction_estimated": "Flat-Field Correction",
        "flat_field": "Flat-Field Correction",
        "subtract_background_estimated": "Background Subtraction",
        "color_saturation": "Color / Saturation",
        "high_pass": "High-Pass Filter",
        "gaussian": "Gaussian Smooth",
        "median": "Median Filter",
        "sharpen": "Sharpen",
        "denoise": "Noise Reduction",
        "total_variation": "TV Denoise",
        "wavelet_sharpen": "Wavelet Sharpen",
        "local_contrast": "Local Contrast",
        "deconvolution": "Deconvolution",
        "uniform_background_outside_selection": "Uniform Background Outside Selection (Stamp)",
        "healed_uniform_background_outside_selection": "Uniform Background Outside Selection (Heal)",
    }
    return names.get(operation, operation.replace("_", " ").title())
