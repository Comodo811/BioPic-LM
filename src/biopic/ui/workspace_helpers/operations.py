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
    }


def operation_layer_name(operation: str) -> str:
    names = {
        "white_balance": "White Balance",
        "flat_field_correction_estimated": "Flat-Field Correction",
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
    }
    return names.get(operation, operation.replace("_", " ").title())
