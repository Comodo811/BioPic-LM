import numpy as np

from biopic.imaging.adjustments import (
    adjustment_pipeline_cache_key,
    render_adjustment_pipeline,
)
from biopic.imaging.corrections import (
    apply_raw_camera_profile_matrix,
    curve_adjust,
    estimate_white_balance_from_region,
    estimate_white_balance_temperature_correlation,
    gamma_correct,
    levels,
    white_balance_gains_from_temperature,
    white_balance_multipliers,
    white_balance_preset_gains,
    white_balance_rendered,
)
from biopic.models.editing import AdjustmentLayer
from biopic.models.project import Project
from biopic.pipeline.node import ProcessingNode


def test_white_balance_multipliers_preserve_dtype_and_shift_channels() -> None:
    image = np.full((2, 2, 3), 100, dtype=np.uint16)

    balanced = white_balance_multipliers(image, red=1.4, green=1.0, blue=0.8, normalize=False)

    assert balanced.dtype == np.uint16
    assert np.all(balanced[..., 0] > balanced[..., 1])
    assert np.all(balanced[..., 2] < balanced[..., 1])


def test_white_balance_spot_estimate_neutralizes_patch() -> None:
    image = np.full((24, 24, 3), [0.28, 0.42, 0.56], dtype=np.float32)

    estimate = estimate_white_balance_from_region(image, (2, 2, 20, 20))
    balanced = white_balance_rendered(
        image,
        method="spot",
        sample_rect=(2, 2, 20, 20),
        sample_size=16,
    )

    patch = balanced[2:22, 2:22].mean(axis=(0, 1))
    assert estimate.sample_count > 0
    assert estimate.green == 1.0
    assert np.max(patch) - np.min(patch) < 0.02


def test_white_balance_temperature_gains_are_green_anchored() -> None:
    warm = white_balance_gains_from_temperature(3500.0, tint=1.0)
    cool = white_balance_gains_from_temperature(9000.0, tint=1.0)

    assert warm[1] == 1.0
    assert cool[1] == 1.0
    assert warm[2] > cool[2]


def test_white_balance_temperature_correlation_reduces_rendered_color_cast() -> None:
    yy, xx = np.mgrid[:64, :64]
    image = np.full((64, 64, 3), [0.32, 0.42, 0.54], dtype=np.float32)
    image += (((xx + yy) % 7) - 3)[..., None].astype(np.float32) * 0.003

    estimate = estimate_white_balance_temperature_correlation(image, histogram_bins=24)
    balanced = white_balance_rendered(image, method="auto_temperature", histogram_bins=24)

    before = image.mean(axis=(0, 1))
    after = balanced.mean(axis=(0, 1))
    assert estimate.temperature is not None
    assert estimate.tint is not None
    assert estimate.histogram_bins == 24
    assert estimate.green == 1.0
    assert float(after.max() - after.min()) < float(before.max() - before.min()) * 0.35


def test_white_balance_presets_and_blue_red_equalizer_shift_channel_ratio() -> None:
    image = np.full((2, 2, 3), 0.4, dtype=np.float32)

    daylight = white_balance_preset_gains("daylight")
    tungsten = white_balance_preset_gains("tungsten")
    equalized = white_balance_rendered(
        image,
        method="preset",
        preset="daylight",
        blue_red_equalizer=1.5,
    )

    assert daylight[1] == 1.0
    assert tungsten[2] > daylight[2]
    assert float(equalized[..., 0].mean()) > float(equalized[..., 2].mean())


def test_raw_camera_white_balance_uses_metadata_without_double_applying() -> None:
    image = np.full((2, 2, 3), 0.4, dtype=np.float32)
    raw_metadata = {
        "camera_whitebalance": [2.0, 1.0, 0.5, 0.0],
        "daylight_whitebalance": [1.0, 1.0, 2.0, 0.0],
        "raw_import_use_camera_wb": False,
    }

    camera = white_balance_rendered(image, method="camera", raw_metadata=raw_metadata)
    raw_metadata["raw_import_use_camera_wb"] = True
    as_shot = white_balance_rendered(image, method="camera", raw_metadata=raw_metadata)
    daylight = white_balance_rendered(image, method="raw_daylight", raw_metadata=raw_metadata)

    assert float(camera[..., 0].mean()) > float(camera[..., 2].mean())
    assert np.allclose(as_shot, image)
    assert float(daylight[..., 2].mean()) > float(daylight[..., 0].mean())


def test_raw_camera_matrix_is_opt_in_and_safe_for_missing_metadata() -> None:
    image = np.full((2, 2, 3), 0.4, dtype=np.float32)

    missing = apply_raw_camera_profile_matrix(image, raw_metadata={}, strength=1.0)
    disabled = apply_raw_camera_profile_matrix(
        image,
        raw_metadata={"raw_rgb_xyz_matrix": np.eye(3).tolist()},
        strength=0.0,
    )

    assert np.array_equal(missing, image)
    assert np.array_equal(disabled, image)


def test_levels_output_points_and_curve_channel() -> None:
    image = np.array([0, 128, 255], dtype=np.uint8)

    leveled = levels(image, black_point=0.0, white_point=1.0, output_black=0.2, output_white=0.8)
    curved = curve_adjust(image, [(0.0, 0.0), (0.5, 0.8), (1.0, 1.0)])

    assert 45 <= int(leveled[0]) <= 55
    assert 198 <= int(leveled[-1]) <= 210
    assert curved[1] > image[1]


def test_levels_can_target_alpha_channel_like_gimp() -> None:
    image = np.full((1, 3, 4), 128, dtype=np.uint8)
    image[..., 3] = np.array([[0, 128, 255]], dtype=np.uint8)

    adjusted = levels(
        image,
        black_point=0.0,
        white_point=1.0,
        output_black=0.25,
        output_white=0.75,
        channel="alpha",
    )

    assert np.array_equal(adjusted[..., :3], image[..., :3])
    assert 60 <= int(adjusted[0, 0, 3]) <= 66
    assert 190 <= int(adjusted[0, 2, 3]) <= 194


def test_curves_can_target_alpha_channel_like_gimp() -> None:
    image = np.full((1, 3, 4), 128, dtype=np.uint8)
    image[..., 3] = np.array([[0, 128, 255]], dtype=np.uint8)

    adjusted = curve_adjust(
        image,
        [(0.0, 0.0), (0.5, 0.25), (1.0, 1.0)],
        channel="alpha",
        curve_type="smooth",
    )

    assert np.array_equal(adjusted[..., :3], image[..., :3])
    assert int(adjusted[0, 1, 3]) < int(image[0, 1, 3])
    assert int(adjusted[0, 2, 3]) == 255


def test_curves_free_mode_uses_linear_segments() -> None:
    image = np.array([64, 128, 192], dtype=np.uint8)

    adjusted = curve_adjust(
        image,
        [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)],
        curve_type="free",
    )

    assert int(adjusted[1]) > 245
    assert int(adjusted[0]) < int(adjusted[1])
    assert int(adjusted[2]) < int(adjusted[1])


def test_gamma_correction_preserves_alpha_channel() -> None:
    image = np.array([[[128, 128, 128, 64], [200, 200, 200, 192]]], dtype=np.uint8)

    adjusted = gamma_correct(image, gamma=2.0)

    assert adjusted.dtype == image.dtype
    assert np.array_equal(adjusted[..., 3], image[..., 3])
    assert int(adjusted[0, 0, 0]) < int(image[0, 0, 0])


def test_adjustment_pipeline_renders_enabled_layers_in_order() -> None:
    image = np.array([0, 128, 255], dtype=np.uint8)
    gamma = AdjustmentLayer(
        name="Gamma",
        image_node_id="source",
        operation="gamma",
        parameters={"gamma": 2.0},
        order=0,
    )
    invert = AdjustmentLayer(
        name="Invert",
        image_node_id="source",
        operation="invert",
        parameters={},
        enabled=False,
        order=1,
    )

    rendered = render_adjustment_pipeline(image, [invert, gamma])

    assert rendered[1] < image[1]
    assert rendered[-1] == image[-1]


def test_adjustment_cache_key_changes_when_parameters_change() -> None:
    layer = AdjustmentLayer(
        name="Levels",
        image_node_id="source",
        operation="levels",
        parameters={"midtone": 1.0},
    )
    before = adjustment_pipeline_cache_key("source", [layer])
    layer.parameters = {"midtone": 1.2}
    layer.touch()

    after = adjustment_pipeline_cache_key("source", [layer])

    assert before != after


def test_project_adjustment_update_invalidates_downstream_nodes() -> None:
    project = Project.new("Invalidation")
    source = ProcessingNode(operation="source")
    figure = ProcessingNode(operation="figure_panel", inputs=(source.id,))
    project.graph.add_node(source)
    project.graph.add_node(figure)
    layer = AdjustmentLayer(
        name="White Balance",
        image_node_id=source.id,
        operation="white_balance",
        parameters={"red": 1.0, "green": 1.0, "blue": 1.0},
        cache_key="cached",
    )
    project.add_adjustment_layer(layer)

    stale = project.update_adjustment_layer(layer.id, {"red": 1.1, "green": 1.0, "blue": 0.9})

    assert figure.id in stale
    assert layer.cache_key is None
