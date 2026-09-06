"""Image-stack registration helpers."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage
from skimage.registration import phase_cross_correlation

from biopic.imaging.stacking.focus_metrics import to_luminance

MIN_SUBJECT_COVERAGE = 0.01
MAX_SUBJECT_COVERAGE = 0.75
MAX_ALIGNMENT_SHIFT_FRACTION = 0.25


@dataclass(frozen=True, slots=True)
class AlignmentTransform:
    """Translation-only transform for an aligned stack frame."""

    shift_y: float = 0.0
    shift_x: float = 0.0
    error: float = 0.0
    affine: tuple[float, float, float, float, float, float] | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize transform."""
        data: dict[str, object] = {
            "shift_y": self.shift_y,
            "shift_x": self.shift_x,
            "error": self.error,
        }
        if self.affine is not None:
            data["affine"] = list(self.affine)
        return data


def align_stack_translation(
    images: list[np.ndarray],
    *,
    reference_index: int = 0,
    upsample_factor: int = 10,
    max_estimation_size: int = 1024,
    use_cuda: bool = False,
    refine_euclidean: bool = True,
) -> tuple[list[np.ndarray], list[AlignmentTransform]]:
    """Align a stack to the reference image using subject-weighted phase correlation."""
    if not images:
        raise ValueError("images must not be empty")
    reference = to_luminance(images[reference_index]).astype(np.float32, copy=False)
    estimation_scale = _estimation_scale(reference.shape, max_estimation_size)
    reference_estimate = _resize_for_estimation(reference, estimation_scale)
    subject_mask = specimen_alignment_mask(reference_estimate)
    aligned: list[np.ndarray] = []
    transforms: list[AlignmentTransform] = []
    for index, image in enumerate(images):
        if index == reference_index:
            aligned.append(np.asarray(image))
            transforms.append(AlignmentTransform())
            continue
        moving = _resize_for_estimation(
            to_luminance(image).astype(np.float32, copy=False),
            estimation_scale,
        )
        estimated = estimate_subject_translation(
            reference_estimate,
            moving,
            subject_mask,
            upsample_factor=upsample_factor,
            refine_euclidean=refine_euclidean,
        )
        transform = _scale_alignment_transform(estimated, estimation_scale)
        aligned.append(apply_translation(image, transform, use_cuda=use_cuda))
        transforms.append(transform)
    return aligned, transforms


def estimate_subject_translation(
    reference: np.ndarray,
    moving: np.ndarray,
    subject_mask: np.ndarray | None = None,
    *,
    upsample_factor: int = 10,
    refine_euclidean: bool = True,
) -> AlignmentTransform:
    """Estimate translation while preferring large specimen structure over dust."""
    reference_gray = _normalize_float_image(reference)
    moving_gray = _normalize_float_image(moving)
    mask = (
        specimen_alignment_mask(reference_gray)
        if subject_mask is None
        else np.asarray(subject_mask, dtype=bool)
    )
    global_shift, global_error = _phase_shift(
        _windowed_for_phase(reference_gray),
        _windowed_for_phase(moving_gray),
        upsample_factor,
    )
    candidates: list[tuple[np.ndarray, float]] = [(global_shift, global_error)]

    if _mask_has_subject(mask):
        bbox = _padded_bbox(mask, reference_gray.shape)
        if bbox is not None:
            top, bottom, left, right = bbox
            reference_roi = reference_gray[top:bottom, left:right]
            moving_roi = moving_gray[top:bottom, left:right]
            mask_roi = mask[top:bottom, left:right]
            if min(reference_roi.shape) >= 8 and np.any(mask_roi):
                roi_shift, roi_error = _phase_shift(
                    _windowed_for_phase(reference_roi, mask_roi),
                    _windowed_for_phase(moving_roi, mask_roi),
                    upsample_factor,
                )
                candidates.append((roi_shift, roi_error))

    best_shift, best_error = min(
        candidates,
        key=lambda candidate: _alignment_score(
            reference_gray,
            moving_gray,
            candidate[0],
            mask,
        ),
    )
    best_shift = _clamp_unreasonable_shift(best_shift, reference_gray.shape)
    if refine_euclidean:
        affine = _estimate_subject_euclidean_transform(
            reference_gray,
            moving_gray,
            mask,
            best_shift,
        )
        if affine is not None:
            shift_score = _alignment_score(reference_gray, moving_gray, best_shift, mask)
            affine_score = _alignment_score(reference_gray, moving_gray, affine, mask)
            if affine_score <= shift_score * 0.96:
                return AlignmentTransform(
                    shift_y=float(best_shift[0]),
                    shift_x=float(best_shift[1]),
                    error=float(affine_score),
                    affine=tuple(float(value) for value in affine.reshape(6)),
                )
    return AlignmentTransform(
        shift_y=float(best_shift[0]),
        shift_x=float(best_shift[1]),
        error=float(best_error),
    )


def specimen_alignment_mask(image: np.ndarray) -> np.ndarray:
    """Return a coarse mask of the main specimen, suppressing isolated particles."""
    gray = _normalize_float_image(image)
    if min(gray.shape) < 8:
        return np.ones(gray.shape, dtype=bool)
    sigma = max(2.0, min(gray.shape) / 40.0)
    background = ndimage.gaussian_filter(gray, sigma=sigma, mode="reflect")
    detail = np.abs(gray - background)
    gradient = ndimage.gaussian_gradient_magnitude(gray, sigma=1.0, mode="reflect")
    activity = detail + gradient * 0.65
    high = float(np.percentile(activity, 99.0))
    if high <= 1e-8:
        return np.ones(gray.shape, dtype=bool)
    normalized = np.clip(activity / high, 0.0, 1.0)
    threshold = max(0.08, float(np.percentile(normalized, 72.0)))
    mask = normalized >= threshold
    mask = ndimage.binary_closing(mask, structure=np.ones((5, 5), dtype=bool))
    mask = ndimage.binary_fill_holes(mask)
    mask = _keep_large_components(mask)
    if not _mask_has_subject(mask):
        return np.ones(gray.shape, dtype=bool)
    return ndimage.binary_dilation(mask, iterations=3)


def apply_translation(
    image: np.ndarray,
    transform: AlignmentTransform,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    """Apply a subpixel translation to a grayscale or color image."""
    array = np.asarray(image)
    if transform.affine is not None and array.ndim in {2, 3}:
        return _apply_affine(array, transform.affine, use_cuda=use_cuda)
    if array.ndim in {2, 3}:
        return _apply_translation_affine(
            array,
            transform.shift_y,
            transform.shift_x,
            use_cuda=use_cuda,
        )
    return ndimage.shift(
        array,
        shift=(0, transform.shift_y, transform.shift_x),
        order=1,
        mode="nearest",
        prefilter=False,
    )


def _apply_translation_affine(
    image: np.ndarray,
    shift_y: float,
    shift_x: float,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    array = np.asarray(image)
    height, width = array.shape[:2]
    matrix = np.asarray(
        [[1.0, 0.0, float(shift_x)], [0.0, 1.0, float(shift_y)]],
        dtype=np.float32,
    )
    warped = _warp_affine_accelerated(
        array,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        use_cuda=use_cuda,
    )
    return np.asarray(warped, dtype=array.dtype)


def _phase_shift(
    reference: np.ndarray, moving: np.ndarray, upsample_factor: int
) -> tuple[np.ndarray, float]:
    shift, error, _phase = phase_cross_correlation(
        reference,
        moving,
        upsample_factor=upsample_factor,
    )
    return np.asarray(shift, dtype=np.float32), float(error)


def _estimation_scale(shape: tuple[int, ...], max_size: int) -> float:
    if max_size <= 0:
        return 1.0
    largest = max(shape[:2])
    if largest <= max_size:
        return 1.0
    return max_size / float(largest)


def _resize_for_estimation(image: np.ndarray, scale: float) -> np.ndarray:
    if scale >= 0.999:
        return np.asarray(image, dtype=np.float32)
    resized = ndimage.zoom(image, zoom=(scale, scale), order=1, prefilter=False)
    return np.asarray(resized, dtype=np.float32)


def _scale_alignment_transform(
    transform: AlignmentTransform, estimation_scale: float
) -> AlignmentTransform:
    if estimation_scale >= 0.999:
        return transform
    factor = 1.0 / estimation_scale
    affine = None
    if transform.affine is not None:
        matrix = np.asarray(transform.affine, dtype=np.float32).reshape(2, 3)
        matrix[:, 2] *= factor
        affine = tuple(float(value) for value in matrix.reshape(6))
    return AlignmentTransform(
        shift_y=transform.shift_y * factor,
        shift_x=transform.shift_x * factor,
        error=transform.error,
        affine=affine,
    )


def _windowed_for_phase(image: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32)
    if mask is not None:
        array = np.where(mask, array, 0.0).astype(np.float32, copy=False)
    array = array - float(np.mean(array))
    if min(array.shape) < 2:
        return array
    window_y = np.hanning(array.shape[0]).astype(np.float32)
    window_x = np.hanning(array.shape[1]).astype(np.float32)
    return (array * window_y[:, None] * window_x[None, :]).astype(np.float32, copy=False)


def _alignment_score(
    reference: np.ndarray,
    moving: np.ndarray,
    transform: np.ndarray,
    mask: np.ndarray,
) -> float:
    if not _mask_has_subject(mask):
        mask = np.ones(reference.shape, dtype=bool)
    if transform.shape == (2, 3):
        shifted = _apply_affine(moving, tuple(float(value) for value in transform.reshape(6)))
    else:
        shifted = ndimage.shift(
            moving,
            shift=(float(transform[0]), float(transform[1])),
            order=1,
            mode="nearest",
            prefilter=False,
        )
    difference = np.abs(reference - shifted)
    return float(np.mean(difference[mask]))


def _estimate_subject_euclidean_transform(
    reference: np.ndarray,
    moving: np.ndarray,
    mask: np.ndarray,
    initial_shift: np.ndarray,
) -> np.ndarray | None:
    if not _mask_has_subject(mask) or min(reference.shape) < 32:
        return None
    warp = np.asarray(
        [
            [1.0, 0.0, -float(initial_shift[1])],
            [0.0, 1.0, -float(initial_shift[0])],
        ],
        dtype=np.float32,
    )
    reference_ecc = _ecc_image(reference, mask)
    moving_ecc = _ecc_image(moving, None)
    input_mask = np.asarray(mask, dtype=np.uint8) * 255
    try:
        _cc, refined = cv2.findTransformECC(
            reference_ecc,
            moving_ecc,
            warp,
            cv2.MOTION_EUCLIDEAN,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5),
            input_mask,
            5,
        )
    except cv2.error:
        return None
    refined = np.asarray(refined, dtype=np.float32)
    if not np.all(np.isfinite(refined)):
        return None
    if not _euclidean_transform_is_reasonable(refined, reference.shape):
        return None
    return refined


def _ecc_image(image: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    normalized = _normalize_float_image(image)
    structure = ndimage.gaussian_gradient_magnitude(normalized, sigma=1.0, mode="reflect")
    if mask is not None:
        structure = np.where(mask, structure, 0.0)
    high = float(np.percentile(structure, 99.0))
    if high > 1e-8:
        structure = np.clip(structure / high, 0.0, 1.0)
    return np.asarray(structure, dtype=np.float32)


def _euclidean_transform_is_reasonable(matrix: np.ndarray, shape: tuple[int, int]) -> bool:
    shift_x = -float(matrix[0, 2])
    shift_y = -float(matrix[1, 2])
    if abs(shift_y) > shape[0] * MAX_ALIGNMENT_SHIFT_FRACTION:
        return False
    if abs(shift_x) > shape[1] * MAX_ALIGNMENT_SHIFT_FRACTION:
        return False
    rotation_scale = matrix[:, :2]
    scale = float(np.sqrt(np.mean(np.sum(rotation_scale * rotation_scale, axis=0))))
    if not 0.92 <= scale <= 1.08:
        return False
    angle = float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0])))
    return abs(angle) <= 8.0


def _apply_affine(
    image: np.ndarray,
    affine: tuple[float, float, float, float, float, float],
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    array = np.asarray(image)
    matrix = np.asarray(affine, dtype=np.float32).reshape(2, 3)
    height, width = array.shape[:2]
    warped = _warp_affine_accelerated(
        array,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        use_cuda=use_cuda,
    )
    return np.asarray(warped, dtype=array.dtype)


def _warp_affine_accelerated(
    image: np.ndarray,
    matrix: np.ndarray,
    size: tuple[int, int],
    *,
    flags: int,
    use_cuda: bool = False,
) -> np.ndarray:
    if not use_cuda or not _opencv_cuda_available():
        return cv2.warpAffine(
            image,
            matrix,
            size,
            flags=flags,
            borderMode=cv2.BORDER_REPLICATE,
        )
    try:
        gpu = cv2.cuda_GpuMat()
        gpu.upload(image)
        warped = cv2.cuda.warpAffine(
            gpu,
            matrix,
            size,
            flags=flags,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return warped.download()
    except (AttributeError, cv2.error):
        return cv2.warpAffine(
            image,
            matrix,
            size,
            flags=flags,
            borderMode=cv2.BORDER_REPLICATE,
        )


def _opencv_cuda_available() -> bool:
    try:
        return bool(hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0)
    except cv2.error:
        return False


def _normalize_float_image(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32)
    low, high = np.percentile(array, [1.0, 99.0])
    if float(high - low) <= 1e-8:
        return np.zeros(array.shape, dtype=np.float32)
    return np.clip((array - low) / float(high - low), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )


def _keep_large_components(mask: np.ndarray) -> np.ndarray:
    labels, count = ndimage.label(mask)
    if count <= 0:
        return np.zeros(mask.shape, dtype=bool)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = int(np.max(sizes))
    min_area = max(32, int(mask.size * 0.002), int(largest * 0.12))
    return sizes[labels] >= min_area


def _mask_has_subject(mask: np.ndarray) -> bool:
    coverage = float(np.mean(mask))
    return MIN_SUBJECT_COVERAGE <= coverage <= MAX_SUBJECT_COVERAGE


def _padded_bbox(
    mask: np.ndarray,
    shape: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    rows, columns = np.nonzero(mask)
    if rows.size == 0 or columns.size == 0:
        return None
    top = int(rows.min())
    bottom = int(rows.max()) + 1
    left = int(columns.min())
    right = int(columns.max()) + 1
    pad_y = max(8, int((bottom - top) * 0.35))
    pad_x = max(8, int((right - left) * 0.35))
    return (
        max(0, top - pad_y),
        min(shape[0], bottom + pad_y),
        max(0, left - pad_x),
        min(shape[1], right + pad_x),
    )


def _clamp_unreasonable_shift(shift: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    max_y = max(1.0, shape[0] * MAX_ALIGNMENT_SHIFT_FRACTION)
    max_x = max(1.0, shape[1] * MAX_ALIGNMENT_SHIFT_FRACTION)
    return np.asarray(
        [np.clip(shift[0], -max_y, max_y), np.clip(shift[1], -max_x, max_x)],
        dtype=np.float32,
    )
