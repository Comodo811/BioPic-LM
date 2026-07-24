import numpy as np
from scipy import ndimage

from biopic.imaging.stacking import (
    AlignmentMode,
    FocusMetric,
    FocusStackParameters,
    StackingMethod,
    focus_stack,
)
from biopic.imaging.stacking.alignment import align_stack_translation
from biopic.imaging.stacking.focus_metrics import focus_measure
from biopic.imaging.stacking.stacker import adjust_depth_regions
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.pipeline.node import ProcessingNode


def test_alignment_recovers_translation() -> None:
    base = np.zeros((48, 48), dtype=np.float32)
    base[18:30, 20:32] = 1.0
    moved = ndimage.shift(base, shift=(3, -4), order=1, mode="nearest", prefilter=False)

    _aligned, transforms = align_stack_translation([base, moved], upsample_factor=1)

    assert abs(transforms[1].shift_y + 3) <= 1
    assert abs(transforms[1].shift_x - 4) <= 1


def test_focus_measure_prefers_sharp_image() -> None:
    sharp = np.zeros((32, 32), dtype=np.float32)
    sharp[:, 16:] = 1.0
    blurred = ndimage.gaussian_filter(sharp, sigma=2.0)

    sharp_score = focus_measure(sharp, FocusMetric.MODIFIED_LAPLACIAN, radius=2)
    blurred_score = focus_measure(blurred, FocusMetric.MODIFIED_LAPLACIAN, radius=2)

    assert float(sharp_score.mean()) > float(blurred_score.mean())


def test_focus_stack_builds_depth_map_and_blended_result() -> None:
    height, width = 40, 48
    left_sharp = np.zeros((height, width), dtype=np.float32)
    right_sharp = np.zeros((height, width), dtype=np.float32)
    left_sharp[:, : width // 2] = _stripe_pattern(height, width // 2)
    left_sharp[:, width // 2 :] = ndimage.gaussian_filter(
        _stripe_pattern(height, width - width // 2), sigma=2
    )
    right_sharp[:, : width // 2] = ndimage.gaussian_filter(
        _stripe_pattern(height, width // 2), sigma=2
    )
    right_sharp[:, width // 2 :] = _stripe_pattern(height, width - width // 2)

    params = FocusStackParameters(
        focus_metric=FocusMetric.TENEGRAD,
        focus_radius=2,
        smoothing_sigma=1.0,
        alignment_mode=AlignmentMode.NONE,
    )
    result = focus_stack([left_sharp, right_sharp], params)

    assert result.image.shape == left_sharp.shape
    assert result.depth_map.shape == left_sharp.shape
    assert np.mean(result.depth_map[:, 4:18]) < 0.4
    assert np.mean(result.depth_map[:, 30:44]) > 0.6
    assert result.weights.shape == (2, height, width)


def test_focus_stack_parameters_round_trip_program_style_options() -> None:
    params = FocusStackParameters(
        stacking_method=StackingMethod.PYRAMID_MAX_CONTRAST,
        score_threshold=12,
        region_bias=-4,
        scale_preset=5,
        adaptive_weighting=False,
        detail_scale=9,
    )

    restored = FocusStackParameters.from_dict(params.to_dict())

    assert restored.stacking_method is StackingMethod.PYRAMID_MAX_CONTRAST
    assert restored.score_threshold == 12
    assert restored.region_bias == -4
    assert restored.scale_preset == 5
    assert restored.adaptive_weighting is False
    assert restored.detail_scale == 9


def test_region_bias_can_grow_depth_regions() -> None:
    scores = np.zeros((2, 9, 9), dtype=np.float32)
    scores[0] = 1.0
    scores[1, 4, 4] = 1.2
    scores[1, 3:6, 3:6] = 1.1
    depth = np.zeros((9, 9), dtype=np.uint16)
    depth[4, 4] = 1

    adjusted = adjust_depth_regions(depth, scores, 1)

    assert np.count_nonzero(adjusted == 1) > 1


def test_pyramid_max_contrast_stack_builds_result() -> None:
    sharp = np.zeros((32, 32), dtype=np.float32)
    sharp[:, 16:] = 1.0
    blurred = ndimage.gaussian_filter(sharp, sigma=2.0)
    params = FocusStackParameters(
        stacking_method=StackingMethod.PYRAMID_MAX_CONTRAST,
        alignment_mode=AlignmentMode.NONE,
        score_threshold=4,
    )

    result = focus_stack([sharp, blurred], params)

    assert result.image.shape == sharp.shape
    assert result.depth_map.shape == sharp.shape
    assert result.weights.shape == (2, 32, 32)


def test_focus_stack_node_can_link_to_source_nodes() -> None:
    project = Project.new("Graph")
    first = ImageAsset(path="a.png")
    second = ImageAsset(path="b.png")
    project.add_asset(first)
    project.add_asset(second)
    source_ids = [
        project.source_node_id_for_asset(first.id),
        project.source_node_id_for_asset(second.id),
    ]

    node = ProcessingNode(
        operation="focus_stack", inputs=tuple(item for item in source_ids if item)
    )
    project.graph.add_node(node)

    assert len(node.inputs) == 2
    assert project.graph.nodes[node.id].operation == "focus_stack"


def _stripe_pattern(height: int, width: int) -> np.ndarray:
    y, x = np.indices((height, width))
    return ((x + y) % 4 < 2).astype(np.float32)
