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
