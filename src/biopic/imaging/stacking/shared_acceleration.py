"""Optional accelerated image filtering helpers for focus stacking."""

from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np
from scipy import ndimage

from biopic.imaging.stacking.focus_metrics import FocusMetric, focus_measure
from biopic.imaging.stacking.gpu_memory import suppress_cupy_environment_warnings

try:  # Optional CUDA acceleration.
    suppress_cupy_environment_warnings()
    import cupy as cp  # type: ignore[import-untyped]
    from cupyx.scipy import ndimage as cndimage  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    cp = None
    cndimage = None


def _downscale_average(
    image: np.ndarray,
    factor: int,
    use_cuda: bool = False,
) -> np.ndarray:
    factor = int(max(1, factor))
    if factor <= 1:
        return image.astype(np.float32, copy=False)
    height, width = image.shape[:2]
    out_h = max(1, height // factor)
    out_w = max(1, width // factor)
    resized = _resize_accelerated(
        image.astype(np.float32, copy=False),
        (out_w, out_h),
        interpolation=cv2.INTER_AREA,
        use_cuda=use_cuda,
    )
    return np.asarray(resized, dtype=np.float32)


def _resize_map(
    image: np.ndarray,
    shape: tuple[int, int],
    use_cuda: bool = False,
) -> np.ndarray:
    if image.shape[:2] == shape:
        return image.astype(np.float32, copy=False)
    resized = _resize_accelerated(
        image.astype(np.float32, copy=False),
        (shape[1], shape[0]),
        interpolation=cv2.INTER_LINEAR,
        use_cuda=use_cuda,
    )
    return np.asarray(resized, dtype=np.float32)


def _filter2d_accelerated(
    image: np.ndarray,
    kernel: np.ndarray,
    *,
    borderType: int,
    use_cuda: bool = False,
) -> np.ndarray:
    source = image.astype(np.float32, copy=False)
    if not use_cuda or source.ndim != 2 or not _cuda_available():
        return cv2.filter2D(source, -1, kernel, borderType=borderType)
    try:
        gpu = cv2.cuda_GpuMat()
        gpu.upload(source)
        linear_filter = cv2.cuda.createLinearFilter(
            cv2.CV_32F,
            cv2.CV_32F,
            kernel.astype(np.float32, copy=False),
            borderMode=borderType,
        )
        return linear_filter.apply(gpu).download().astype(np.float32, copy=False)
    except cv2.error:
        return cv2.filter2D(source, -1, kernel, borderType=borderType)


def _resize_accelerated(
    image: np.ndarray,
    size: tuple[int, int],
    *,
    interpolation: int,
    use_cuda: bool = False,
) -> np.ndarray:
    source = image.astype(np.float32, copy=False)
    if not use_cuda or source.ndim != 2 or not _cuda_available():
        return cv2.resize(source, size, interpolation=interpolation)
    try:
        gpu = cv2.cuda_GpuMat()
        gpu.upload(source)
        return cv2.cuda.resize(gpu, size, interpolation=interpolation).download().astype(
            np.float32,
            copy=False,
        )
    except cv2.error:
        return cv2.resize(source, size, interpolation=interpolation)


def _gaussian_stack_accelerated(
    scores: np.ndarray,
    sigma: float,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    source = scores.astype(np.float32, copy=False)
    if sigma <= 0:
        return source
    ksize = max(3, int(np.ceil(float(sigma) * 6.0)) | 1)
    output = np.empty_like(source, dtype=np.float32)
    for index in range(source.shape[0]):
        output[index] = _gaussian_blur_accelerated(
            source[index],
            ksize,
            sigma,
            use_cuda=use_cuda,
        )
    return output


def _gaussian_blur_accelerated(
    image: np.ndarray,
    ksize: int,
    sigma: float,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    source = image.astype(np.float32, copy=False)
    if not use_cuda or source.ndim != 2 or not _cuda_available():
        return cv2.GaussianBlur(
            source,
            (ksize, ksize),
            sigmaX=sigma,
            sigmaY=sigma,
            borderType=cv2.BORDER_REFLECT,
        )
    try:
        gpu = cv2.cuda_GpuMat()
        gpu.upload(source)
        gaussian = cv2.cuda.createGaussianFilter(
            cv2.CV_32F,
            cv2.CV_32F,
            (ksize, ksize),
            sigma1=sigma,
            sigma2=sigma,
            borderMode=cv2.BORDER_REFLECT,
        )
        return gaussian.apply(gpu).download().astype(np.float32, copy=False)
    except (AttributeError, cv2.error):
        return cv2.GaussianBlur(
            source,
            (ksize, ksize),
            sigmaX=sigma,
            sigmaY=sigma,
            borderType=cv2.BORDER_REFLECT,
        )


def _uniform_stack_accelerated(
    scores: np.ndarray,
    size: int,
    *,
    use_cuda: bool = False,
) -> np.ndarray:
    if size <= 1:
        return scores.astype(np.float32, copy=False)
    kernel = np.full((size, size), 1.0 / float(size * size), dtype=np.float32)
    source = scores.astype(np.float32, copy=False)
    output = np.empty_like(source, dtype=np.float32)
    for index in range(source.shape[0]):
        output[index] = _filter2d_accelerated(
            source[index],
            kernel,
            borderType=cv2.BORDER_REFLECT,
            use_cuda=use_cuda,
        )
    return output


def _stack_focus_measure_accelerated(
    images: list[np.ndarray],
    metric: FocusMetric,
    radius: int,
) -> np.ndarray | None:
    if metric not in {
        FocusMetric.LAPLACIAN,
        FocusMetric.MODIFIED_LAPLACIAN,
        FocusMetric.TENEGRAD,
        FocusMetric.SCHARR,
    }:
        return None
    layers: list[np.ndarray] = []
    for image in images:
        gray = to_luminance(image).astype(np.float32, copy=False)
        try:
            filtered = _focus_measure_frame_accelerated(gray, metric)
        except cv2.error:
            return None
        layers.append(filtered)
    score = np.stack(layers, axis=0).astype(np.float32, copy=False)
    if radius > 0:
        score = _uniform_stack_accelerated(score, radius * 2 + 1, use_cuda=True)
    return score


def _focus_measure_frame_accelerated(gray: np.ndarray, metric: FocusMetric) -> np.ndarray:
    gpu = cv2.cuda_GpuMat()
    gpu.upload(gray.astype(np.float32, copy=False))
    if metric is FocusMetric.LAPLACIAN:
        kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        lap = _apply_gpu_linear_filter(gpu, kernel).download()
        return np.abs(lap).astype(np.float32, copy=False)
    if metric is FocusMetric.MODIFIED_LAPLACIAN:
        kernel_x = np.array([[0, 0, 0], [-1, 2, -1], [0, 0, 0]], dtype=np.float32)
        kernel_y = kernel_x.T
        sx = _apply_gpu_linear_filter(gpu, kernel_x).download()
        sy = _apply_gpu_linear_filter(gpu, kernel_y).download()
        return (np.abs(sx) + np.abs(sy)).astype(np.float32, copy=False)
    if metric is FocusMetric.TENEGRAD:
        kernel_x = np.array([[1, 0, -1], [2, 0, -2], [1, 0, -1]], dtype=np.float32)
        kernel_y = kernel_x.T
        sx = _apply_gpu_linear_filter(gpu, kernel_x).download()
        sy = _apply_gpu_linear_filter(gpu, kernel_y).download()
        return (sx * sx + sy * sy).astype(np.float32, copy=False)
    if metric is FocusMetric.SCHARR:
        kernel_x = np.array([[3, 0, -3], [10, 0, -10], [3, 0, -3]], dtype=np.float32)
        kernel_y = kernel_x.T
        sx = _apply_gpu_linear_filter(gpu, kernel_x).download()
        sy = _apply_gpu_linear_filter(gpu, kernel_y).download()
        return (sx * sx + sy * sy).astype(np.float32, copy=False)
    raise ValueError(f"Unsupported CUDA focus metric: {metric}")


def _apply_gpu_linear_filter(gpu: object, kernel: np.ndarray) -> object:
    linear_filter = cv2.cuda.createLinearFilter(
        cv2.CV_32F,
        cv2.CV_32F,
        kernel.astype(np.float32, copy=False),
        borderMode=cv2.BORDER_REFLECT,
    )
    return linear_filter.apply(gpu)


@lru_cache(maxsize=1)
def _cuda_available() -> bool:
    try:
        return bool(hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0)
    except cv2.error:
        return False

