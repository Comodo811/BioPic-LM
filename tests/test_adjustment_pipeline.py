import numpy as np

from biopic.imaging.adjustments import (
    adjustment_pipeline_cache_key,
    render_adjustment_pipeline,
)
from biopic.imaging.corrections import (
    curve_adjust,
    estimate_white_balance_from_region,
    levels,
    white_balance_gains_from_temperature,
    white_balance_multipliers,
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


def test_levels_output_points_and_curve_channel() -> None:
    image = np.array([0, 128, 255], dtype=np.uint8)

    leveled = levels(image, black_point=0.0, white_point=1.0, output_black=0.2, output_white=0.8)
    curved = curve_adjust(image, [(0.0, 0.0), (0.5, 0.8), (1.0, 1.0)])

    assert 45 <= int(leveled[0]) <= 55
    assert 198 <= int(leveled[-1]) <= 210
    assert curved[1] > image[1]


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
