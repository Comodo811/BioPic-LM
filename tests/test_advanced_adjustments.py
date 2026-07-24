import numpy as np

from biopic.imaging.editing import apply_edit_operation
from biopic.imaging.filters import (
    deconvolve_richardson_lucy,
    high_pass,
    local_contrast,
    microscopy_noise_reduction,
    wavelet_sharpen,
)


def test_microscopy_noise_reduction_is_deterministic_and_preserves_dtype() -> None:
    image = np.zeros((16, 16), dtype=np.uint8)
    image[8, 8] = 255
    image[2, 2] = 180

    first = microscopy_noise_reduction(image, impulse_radius=1, preserve_edges=True)
    second = microscopy_noise_reduction(image, impulse_radius=1, preserve_edges=True)

    assert first.dtype == image.dtype
    assert np.array_equal(first, second)
    assert first[2, 2] < image[2, 2]


def test_high_pass_threshold_suppresses_low_detail_noise() -> None:
    image = np.full((16, 16), 128, dtype=np.uint8)
    image[8, 8] = 160

    weak = high_pass(image, sigma=1.0, amount=1.0, threshold=0.5)
    strong = high_pass(image, sigma=1.0, amount=1.0, threshold=0.0)

    assert weak[8, 8] <= strong[8, 8]


def test_wavelet_sharpen_preserves_shape_dtype_and_edges() -> None:
    image = np.zeros((24, 24), dtype=np.uint16)
    image[:, 12:] = 30_000

    sharpened = wavelet_sharpen(image, levels=3, amount=0.25, threshold=0.001)

    assert sharpened.shape == image.shape
    assert sharpened.dtype == image.dtype
    assert sharpened[:, 12].mean() >= image[:, 12].mean()


def test_local_contrast_preserves_shape_and_limits_flat_regions() -> None:
    image = np.full((24, 24), 120, dtype=np.uint8)
    image[8:16, 8:16] = 160

    contrasted = local_contrast(image, radius=4.0, amount=0.3, threshold=0.01)

    assert contrasted.shape == image.shape
    assert contrasted.dtype == image.dtype
    assert abs(int(contrasted[0, 0]) - int(image[0, 0])) < 8


def test_deconvolution_is_finite_and_dtype_preserving() -> None:
    image = np.zeros((16, 16), dtype=np.float32)
    image[8, 8] = 1.0

    result = deconvolve_richardson_lucy(image, radius=1.2, iterations=2, amount=0.4)

    assert result.dtype == image.dtype
    assert np.isfinite(result).all()
    assert result.shape == image.shape


def test_advanced_adjustments_dispatch() -> None:
    image = np.zeros((16, 16), dtype=np.uint8)
    image[8, 8] = 255

    denoised = apply_edit_operation(image, "denoise", {"method": "microscopy"})
    sharpened = apply_edit_operation(image, "wavelet_sharpen", {"levels": 2, "amount": 0.2})
    contrasted = apply_edit_operation(image, "local_contrast", {"radius": 3.0})
    deconvolved = apply_edit_operation(image, "deconvolution", {"iterations": 2})

    assert denoised.shape == image.shape
    assert sharpened.shape == image.shape
    assert contrasted.shape == image.shape
    assert deconvolved.shape == image.shape
