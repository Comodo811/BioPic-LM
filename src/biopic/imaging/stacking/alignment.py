"""Image-stack registration helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from skimage.registration import phase_cross_correlation

from biopic.imaging.stacking.focus_metrics import to_luminance


@dataclass(frozen=True, slots=True)
class AlignmentTransform:
    """Translation-only transform for an aligned stack frame."""

    shift_y: float = 0.0
    shift_x: float = 0.0
    error: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Serialize transform."""
        return {"shift_y": self.shift_y, "shift_x": self.shift_x, "error": self.error}


def align_stack_translation(
    images: list[np.ndarray], *, reference_index: int = 0, upsample_factor: int = 10
) -> tuple[list[np.ndarray], list[AlignmentTransform]]:
    """Align a stack to the reference image using phase correlation."""
    if not images:
        raise ValueError("images must not be empty")
    reference = to_luminance(images[reference_index]).astype(np.float32, copy=False)
    aligned: list[np.ndarray] = []
    transforms: list[AlignmentTransform] = []
    for index, image in enumerate(images):
        if index == reference_index:
            aligned.append(np.asarray(image))
            transforms.append(AlignmentTransform())
            continue
        moving = to_luminance(image).astype(np.float32, copy=False)
        shift, error, _phase = phase_cross_correlation(
            reference, moving, upsample_factor=upsample_factor
        )
        transform = AlignmentTransform(
            shift_y=float(shift[0]), shift_x=float(shift[1]), error=float(error)
        )
        aligned.append(apply_translation(image, transform))
        transforms.append(transform)
    return aligned, transforms


def apply_translation(image: np.ndarray, transform: AlignmentTransform) -> np.ndarray:
    """Apply a subpixel translation to a grayscale or color image."""
    array = np.asarray(image)
    if array.ndim == 2:
        return ndimage.shift(
            array,
            shift=(transform.shift_y, transform.shift_x),
            order=1,
            mode="nearest",
            prefilter=False,
        )
    if array.ndim == 3 and array.shape[-1] in {3, 4}:
        channels = [
            ndimage.shift(
                array[..., channel],
                shift=(transform.shift_y, transform.shift_x),
                order=1,
                mode="nearest",
                prefilter=False,
            )
            for channel in range(array.shape[-1])
        ]
        return np.stack(channels, axis=-1).astype(array.dtype, copy=False)
    return ndimage.shift(
        array,
        shift=(0, transform.shift_y, transform.shift_x),
        order=1,
        mode="nearest",
        prefilter=False,
    )
