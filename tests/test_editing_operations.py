from pathlib import Path

import numpy as np

from biopic.imaging.corrections import (
    crop,
    curve_adjust,
    flat_field_correct,
    gamma_correct,
    levels,
    resize_uniform,
)
from biopic.imaging.editing import (
    _apply_gimp_hue_saturation_hsl,
    _gimp_hue_saturation_config,
    _hsl_to_rgb,
    _rgb_to_hsl,
    apply_edit_operation,
    flat_field_correction_estimated,
    healed_uniform_background_outside_selection,
    rotated_content_crop_rect,
    subtract_background_estimated,
    uniform_background_outside_selection,
)
from biopic.imaging.filters import gaussian_smooth, high_pass, median_filter
from biopic.models.editing import EditLayer
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore


def test_flat_field_corrects_shading_with_safeguard() -> None:
    raw = np.array([[50, 100], [150, 200]], dtype=np.uint16)
    flat = np.array([[100, 100], [200, 200]], dtype=np.uint16)

    corrected = flat_field_correct(raw, flat)

    assert corrected.dtype == np.uint16
    assert corrected[0, 0] < corrected[0, 1]
    assert np.isfinite(corrected).all()


def test_estimated_flat_field_recovers_smooth_shading() -> None:
    yy, xx = np.mgrid[:64, :64]
    del yy
    specimen = np.full((64, 64), 0.45, dtype=np.float32)
    illumination = (0.65 + 0.35 * (xx.astype(np.float32) / 63.0)).astype(np.float32)
    shaded = specimen * illumination

    corrected = apply_edit_operation(
        shaded,
        "flat_field_correction_estimated",
        {"sigma": 16.0, "strength": 1.0, "preserve_mean": True},
    )

    assert corrected.dtype == np.float32
    assert float(corrected.std()) < float(shaded.std()) * 0.45
    assert np.isfinite(corrected).all()


def test_estimated_background_corrections_report_progress() -> None:
    image = np.linspace(0, 255, 16 * 18, dtype=np.uint8).reshape(16, 18)
    events: list[tuple[str, float]] = []

    flat = flat_field_correction_estimated(
        image,
        sigma=2.0,
        progress=lambda message, fraction: events.append((message, fraction)),
    )

    assert flat.shape == image.shape
    assert events
    assert events[0][1] == 0.04
    assert events[-1] == ("Flat-field correction complete", 1.0)

    events.clear()
    subtracted = subtract_background_estimated(
        image,
        sigma=2.0,
        progress=lambda message, fraction: events.append((message, fraction)),
    )

    assert subtracted.shape == image.shape
    assert events
    assert events[0][1] == 0.04
    assert events[-1] == ("Background subtraction complete", 1.0)


def test_levels_gamma_and_curve_preserve_dtype() -> None:
    image = np.array([0, 128, 255], dtype=np.uint8)

    leveled = levels(image, black_point=0.0, white_point=1.0, midtone=1.0)
    gamma = gamma_correct(image, gamma=2.0)
    curved = curve_adjust(image, [(0.0, 0.0), (0.5, 0.75), (1.0, 1.0)])

    assert leveled.dtype == np.uint8
    assert gamma[1] < image[1]
    assert curved[1] > image[1]


def test_high_pass_and_smoothing_filters() -> None:
    image = np.zeros((9, 9), dtype=np.float32)
    image[4, 4] = 1.0

    smoothed = gaussian_smooth(image, sigma=1.0)
    sharpened = high_pass(smoothed, sigma=1.0, amount=1.0)
    medianed = median_filter((image * 255).astype(np.uint8), radius=1)

    assert smoothed[4, 4] < image[4, 4]
    assert sharpened[4, 4] > smoothed[4, 4]
    assert medianed[4, 4] == 0


def test_uniform_background_uses_global_texture_without_sampling_selection() -> None:
    yy, xx = np.mgrid[:40, :40]
    image = (90 + ((xx * 7 + yy * 5) % 35)).astype(np.uint8)
    mask = np.zeros((40, 40), dtype=bool)
    mask[15:25, 15:25] = True
    image[mask] = 240

    result = uniform_background_outside_selection(image, mask)

    assert result.dtype == image.dtype
    assert np.array_equal(result[mask], image[mask])
    assert 240 not in set(result[~mask].reshape(-1).tolist())
    assert np.unique(result[~mask]).size > 8


def test_uniform_background_reports_determinate_progress() -> None:
    yy, xx = np.mgrid[:36, :42]
    image = (80 + ((xx * 3 + yy * 5) % 20)).astype(np.uint8)
    mask = np.zeros((36, 42), dtype=bool)
    mask[12:24, 16:28] = True
    events: list[tuple[str, float]] = []

    result = uniform_background_outside_selection(
        image,
        mask,
        progress=lambda message, fraction: events.append((message, fraction)),
    )

    assert result.shape == image.shape
    assert events
    assert events[0] == ("Preparing background mask", 0.02)
    assert events[-1] == ("Background complete", 1.0)


def test_uniform_background_prefers_low_contrast_clone_source() -> None:
    image = np.zeros((48, 64), dtype=np.uint8)
    yy, xx = np.mgrid[:48, :64]
    image[:, :] = np.where((xx + yy) % 2 == 0, 40, 180).astype(np.uint8)
    image[4:20, 4:20] = 104
    image[4:20:2, 4:20:2] = 105
    mask = np.zeros((48, 64), dtype=bool)
    mask[20:30, 28:38] = True
    image[mask] = 240

    result = uniform_background_outside_selection(image, mask)

    outside_values = result[~mask]
    assert int(outside_values.max()) - int(outside_values.min()) <= 3
    assert 240 not in set(outside_values.reshape(-1).tolist())


def test_healed_uniform_background_preserves_destination_lighting() -> None:
    yy, xx = np.mgrid[:56, :72]
    base = 70.0 + xx.astype(np.float32) * 1.2 + yy.astype(np.float32) * 0.25
    texture = ((xx * 3 + yy * 5) % 7).astype(np.float32) - 3.0
    image = np.clip(base + texture, 0, 255).astype(np.uint8)
    image[4:20, 5:25] = 92
    image[4:20:2, 5:25:2] = 94
    mask = np.zeros((56, 72), dtype=bool)
    mask[20:36, 28:44] = True
    image[mask] = 240

    result = healed_uniform_background_outside_selection(image, mask)

    assert result.dtype == image.dtype
    assert np.array_equal(result[mask], image[mask])
    assert 240 not in set(result[~mask].reshape(-1).tolist())
    assert np.unique(result[~mask]).size > 8
    assert float(result[:, -10:].mean()) > float(result[:, :10].mean()) + 10.0


def test_gimp_style_hue_saturation_ranges_and_alpha() -> None:
    red = np.array([[[1.0, 0.0, 0.0, 1.0]]], dtype=np.float32)
    gray = np.array([[[0.4, 0.4, 0.4, 0.7]]], dtype=np.float32)
    blue = np.array([[[0.0, 0.0, 1.0]]], dtype=np.float32)

    desaturated = apply_edit_operation(red, "color_saturation", {"range": "all", "saturation": -100.0})
    lighter = apply_edit_operation(gray, "color_saturation", {"range": "all", "lightness": 50.0})
    red_range_only = apply_edit_operation(
        blue, "color_saturation", {"range": "red", "saturation": -100.0}
    )

    assert np.allclose(desaturated[0, 0, :3], [0.5, 0.5, 0.5], atol=1e-6)
    assert desaturated[0, 0, 3] == 1.0
    assert lighter[0, 0, 0] > gray[0, 0, 0]
    assert lighter[0, 0, 3] == gray[0, 0, 3]
    assert np.allclose(red_range_only, blue, atol=1e-6)


def test_master_saturation_fast_path_matches_hsl_reference() -> None:
    image = np.array(
        [
            [[0.9, 0.2, 0.1], [0.2, 0.8, 0.4], [0.4, 0.4, 0.4]],
            [[0.1, 0.2, 0.9], [0.9, 0.9, 0.1], [0.2, 0.7, 0.9]],
        ],
        dtype=np.float32,
    )
    config = _gimp_hue_saturation_config("all", 0.0, 0.0, 35.0)
    expected_hsl = _apply_gimp_hue_saturation_hsl(_rgb_to_hsl(image), config, 0.0)
    expected = _hsl_to_rgb(expected_hsl)

    actual = apply_edit_operation(image, "color_saturation", {"range": "all", "saturation": 35.0})

    assert np.allclose(actual, expected, atol=1e-6)


def test_geometry_crop_and_uniform_resize() -> None:
    image = np.arange(16, dtype=np.uint8).reshape(4, 4)

    cropped = crop(image, 1, 1, 2, 2)
    resized = resize_uniform(image, 0.5)

    assert cropped.tolist() == [[5, 6], [9, 10]]
    assert resized.shape == (2, 2)


def test_free_rotation_keeps_empty_regions_transparent() -> None:
    image = np.full((20, 12, 3), 180, dtype=np.uint8)

    rotated = apply_edit_operation(image, "rotate_free", {"angle": 33.0})

    assert rotated.dtype == image.dtype
    assert rotated.ndim == 3
    assert rotated.shape[2] == 4
    assert rotated.shape[0] > image.shape[0]
    assert np.any(rotated[..., 3] == 0)


def test_crop_rotated_image_uses_largest_opaque_rectangle() -> None:
    image = np.full((8, 10, 4), 255, dtype=np.uint8)
    image[:2, :, 3] = 0
    image[-2:, :, 3] = 0
    image[:, :1, 3] = 0
    image[:, -1:, 3] = 0

    rect = rotated_content_crop_rect(image)
    cropped = apply_edit_operation(image, "crop_rotated_image", {})

    assert rect == (1, 2, 8, 4)
    assert cropped.shape == (4, 8, 4)
    assert np.all(cropped[..., 3] == 255)


def test_fill_rotated_background_fills_transparent_corners() -> None:
    yy, xx = np.mgrid[:16, :18]
    image = np.zeros((16, 18, 4), dtype=np.uint8)
    image[..., 0] = (80 + xx * 3).astype(np.uint8)
    image[..., 1] = (90 + yy * 2).astype(np.uint8)
    image[..., 2] = 110
    image[..., 3] = 255
    image[:4, :4, 3] = 0
    image[-4:, -4:, 3] = 0

    filled = apply_edit_operation(image, "fill_rotated_background", {})

    assert filled.shape == image.shape
    assert np.all(filled[..., 3] == 255)
    assert np.any(filled[:4, :4, :3] != 0)


def test_edit_dispatch_and_project_round_trip(workspace_tmp_path: Path) -> None:
    image = np.array([0, 128, 255], dtype=np.uint8)
    result = apply_edit_operation(image, "gamma", {"gamma": 2.0})
    assert result[1] < image[1]

    project = Project.new("Editing")
    layer = EditLayer(name="Gamma Adjustment", source_node_id="source-node")
    project.edit_layers[layer.id] = layer
    path = workspace_tmp_path / "editing.biopic.json"
    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)

    assert loaded.edit_layers[layer.id].name == "Gamma Adjustment"
