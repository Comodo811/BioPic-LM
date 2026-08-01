"""Laplacian-pyramid maximum-contrast focus-stacking method."""

from __future__ import annotations

import numpy as np


def stack_pyramid_max_contrast(images: list[np.ndarray], parameters: object) -> object:
    """Run the Pyramid Max Contrast method."""
    from biopic.imaging.stacking import stacker as core
    from biopic.imaging.stacking.gpu_pyramid import stack_pyramid_max_contrast_gpu

    gpu_result = stack_pyramid_max_contrast_gpu(images, parameters)
    if gpu_result is not None:
        return gpu_result

    return core.pyramid_max_contrast_stack(images, parameters)
