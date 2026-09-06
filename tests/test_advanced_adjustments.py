import numpy as np
from scipy import ndimage

from biopic.imaging.editing import apply_edit_operation
from biopic.imaging.filters import (
    deconvolve_richardson_lucy,
    gimp_noise_reduction,
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


def test_gimp_noise_reduction_strength_zero_is_passthrough() -> None:
    image = np.arange(25, dtype=np.uint8).reshape(5, 5)

    result = gimp_noise_reduction(image, strength=0)

    assert result.dtype == image.dtype
    assert np.array_equal(result, image)


def test_gimp_noise_reduction_strength_controls_iterations() -> None:
    image = np.full((17, 17), 128, dtype=np.uint8)
    image[8, 8] = 255

    weak = gimp_noise_reduction(image, strength=1)
    strong = gimp_noise_reduction(image, strength=6)

    assert strong[8, 8] < weak[8, 8] < image[8, 8]


def test_gimp_noise_reduction_preserves_alpha_channel() -> None:
    image = np.zeros((9, 9, 4), dtype=np.float32)
    image[..., :3] = 0.5
    image[4, 4, 0] = 1.0
    image[..., 3] = np.linspace(0.1, 0.9, 81, dtype=np.float32).reshape(9, 9)

    result = gimp_noise_reduction(image, strength=4)

    assert result[4, 4, 0] < image[4, 4, 0]
    assert np.allclose(result[..., 3], image[..., 3])


def test_high_pass_threshold_suppresses_low_detail_noise() -> None:
    image = np.full((16, 16), 128, dtype=np.uint8)
    image[8, 8] = 160

    weak = high_pass(image, sigma=1.0, amount=1.0, threshold=0.5)
    strong = high_pass(image, sigma=1.0, amount=1.0, threshold=0.0)

    assert weak[8, 8] <= strong[8, 8]


def test_high_pass_uses_gimp_style_layer_with_linear_light_only() -> None:
    image = np.linspace(0.1, 0.9, 49, dtype=np.float32).reshape(7, 7)

    result = high_pass(
        image,
        sigma=1.2,
        amount=0.75,
        threshold=0.5,
        halo_suppression=5.0,
        luminance_only=True,
    )

    blurred = ndimage.gaussian_filter(image, sigma=1.2, mode="reflect")
    over = np.clip(0.5 + 0.5 * (image - blurred), 0.0, 1.0)
    inverse_gamma = 1.0 / 2.2
    neutral = np.float32(0.5**inverse_gamma)
    high_pass_layer = np.power(
        np.clip((np.power(over, inverse_gamma) - neutral) * 0.75 + neutral, 0.0, 1.0),
        2.2,
    )
    expected = np.clip(image + 2.0 * (high_pass_layer - 0.5), 0.0, 1.0)

    assert np.allclose(result, expected, atol=1e-6)


def test_high_pass_matches_gimp_gamma_contrast_not_direct_detail_gain() -> None:
    image = np.zeros((9, 9), dtype=np.float32) + 0.5
    image[4, 4] = 0.62

    result = high_pass(image, sigma=1.0, amount=1.0)
    blurred = ndimage.gaussian_filter(image, sigma=1.0, mode="reflect")
    old_direct_gain = np.clip(image + 2.0 * (image - blurred), 0.0, 1.0)

    assert result[4, 4] < old_direct_gain[4, 4]


def test_high_pass_keeps_flat_image_neutral_at_legacy_contrast() -> None:
    image = np.full((9, 9), 0.42, dtype=np.float32)

    result = high_pass(image, sigma=1.0, amount=2.0)

    assert np.allclose(result, image, atol=1e-5)


def test_high_pass_preserves_alpha_channel() -> None:
    image = np.zeros((7, 7, 4), dtype=np.float32)
    image[..., 0] = np.linspace(0.1, 0.9, 49, dtype=np.float32).reshape(7, 7)
    image[..., 1] = 0.4
    image[..., 2] = 0.6
    image[..., 3] = np.linspace(0.2, 0.8, 49, dtype=np.float32).reshape(7, 7)

    result = high_pass(image, sigma=1.0, amount=1.0)

    assert np.allclose(result[..., 3], image[..., 3])


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

    denoised = apply_edit_operation(image, "denoise", {"method": "gimp", "strength": 4})
    sharpened = apply_edit_operation(image, "wavelet_sharpen", {"levels": 2, "amount": 0.2})
    contrasted = apply_edit_operation(image, "local_contrast", {"radius": 3.0})
    deconvolved = apply_edit_operation(image, "deconvolution", {"iterations": 2})

    assert denoised.shape == image.shape
    assert sharpened.shape == image.shape
    assert contrasted.shape == image.shape
    assert deconvolved.shape == image.shape
