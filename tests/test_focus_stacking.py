import cv2
import numpy as np
from scipy import ndimage

from biopic.imaging.stacking import (
    AlignmentMode,
    BackgroundMode,
    FocusMetric,
    FocusStackParameters,
    StackingMethod,
    focus_stack,
)
from biopic.imaging.stacking.alignment import align_stack_translation
from biopic.imaging.stacking.focus_metrics import focus_measure
from biopic.imaging.stacking.stacker import (
    adjust_depth_regions,
    auto_orient_stack_images,
    blend_low_confidence_background,
    clean_depth_map_by_confidence,
    custom_stack_parameters,
    decompiled_confidence_background_composite,
    decompiled_fixed_filter_weights,
    decompiled_neighbor_smooth,
    decompiled_ring_supported_confidence_cleanup,
    preserve_specimen_detail,
    stack_focus_measure,
    stable_background_reference,
    suppress_custom_background_grain,
)
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


def test_alignment_prefers_large_specimen_over_bright_dust() -> None:
    height, width = 96, 112
    y, x = np.indices((height, width))
    organism = (((y - 48) / 20) ** 2 + ((x - 54) / 30) ** 2) <= 1
    texture = ((x * 0.07 + y * 0.11) % 1.0).astype(np.float32)
    base = np.zeros((height, width), dtype=np.float32)
    base[organism] = 0.35 + texture[organism] * 0.45
    base[15:19, 92:96] = 8.0

    moved_organism = ndimage.shift(
        np.where(organism, base, 0.0),
        shift=(5, -6),
        order=1,
        mode="nearest",
        prefilter=False,
    )
    moved_dust = np.zeros_like(base)
    moved_dust[7:11, 103:107] = 8.0
    moved = moved_organism + moved_dust

    _aligned, transforms = align_stack_translation([base, moved], upsample_factor=1)

    assert abs(transforms[1].shift_y + 5) <= 1
    assert abs(transforms[1].shift_x - 6) <= 1


def test_alignment_refines_small_subject_rotation() -> None:
    height, width = 140, 160
    y, x = np.indices((height, width))
    organism = (((y - 70) / 28) ** 2 + ((x - 78) / 44) ** 2) <= 1
    texture = (np.sin(x * 0.25) + np.cos(y * 0.17)).astype(np.float32)
    base = np.zeros((height, width), dtype=np.float32)
    base[organism] = 0.45 + texture[organism] * 0.15
    base[30:34, 130:134] = 7.0
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), 2.5, 1.0)
    matrix[:, 2] += [4, -3]
    moved = cv2.warpAffine(
        base,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    aligned, transforms = align_stack_translation([base, moved], upsample_factor=1)

    before = float(np.mean(np.abs(base - moved)))
    after = float(np.mean(np.abs(base - aligned[1])))
    assert transforms[1].affine is not None
    assert after < before * 0.75


def test_focus_measure_prefers_sharp_image() -> None:
    sharp = np.zeros((32, 32), dtype=np.float32)
    sharp[:, 16:] = 1.0
    blurred = ndimage.gaussian_filter(sharp, sigma=2.0)

    sharp_score = focus_measure(sharp, FocusMetric.MODIFIED_LAPLACIAN, radius=2)
    blurred_score = focus_measure(blurred, FocusMetric.MODIFIED_LAPLACIAN, radius=2)

    assert float(sharp_score.mean()) > float(blurred_score.mean())


def test_stack_focus_measure_matches_frame_metric() -> None:
    rng = np.random.default_rng(42)
    images = [rng.random((24, 28, 3), dtype=np.float32) for _index in range(3)]

    for metric in FocusMetric:
        stacked = stack_focus_measure(images, metric, radius=2)
        expected = np.stack(
            [focus_measure(image, metric, radius=2) for image in images],
            axis=0,
        )
        assert np.allclose(stacked, expected, atol=1e-6)


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


def test_focus_stack_auto_rotates_swapped_landscape_portrait_frames() -> None:
    reference = np.zeros((34, 52, 3), dtype=np.float32)
    reference[9:24, 15:39, :] = 1.0
    rotated = np.rot90(reference, -1, axes=(0, 1))

    oriented = auto_orient_stack_images([reference, rotated])
    result = focus_stack(
        [reference, rotated],
        FocusStackParameters(alignment_mode=AlignmentMode.NONE),
    )

    assert oriented[1].shape == reference.shape
    assert result.image.shape == reference.shape


def test_focus_stack_parameters_round_trip_program_style_options() -> None:
    params = FocusStackParameters(
        stacking_method=StackingMethod.PYRAMID_MAX_CONTRAST,
        score_threshold=12,
        region_bias=-4,
        scale_preset=5,
        adaptive_weighting=False,
        detail_scale=9,
        background_mode=BackgroundMode.DARKEST,
        confidence_cleanup=False,
        use_cuda=True,
    )

    restored = FocusStackParameters.from_dict(params.to_dict())

    assert restored.stacking_method is StackingMethod.PYRAMID_MAX_CONTRAST
    assert restored.score_threshold == 12
    assert restored.region_bias == -4
    assert restored.scale_preset == 5
    assert restored.adaptive_weighting is False
    assert restored.detail_scale == 9
    assert restored.background_mode is BackgroundMode.DARKEST
    assert restored.confidence_cleanup is False
    assert restored.use_cuda is True


def test_custom_stack_parameters_force_confidence_cleanup() -> None:
    params = custom_stack_parameters(
        FocusStackParameters(
            stacking_method=StackingMethod.CUSTOM,
            focus_radius=3,
            score_threshold=2,
            smoothing_sigma=0.25,
            adaptive_weighting=False,
            detail_scale=4,
            confidence_cleanup=False,
        )
    )

    assert params.stacking_method is StackingMethod.CUSTOM
    assert params.focus_radius == 2
    assert params.score_threshold == 2
    assert params.smoothing_sigma >= 0.35
    assert params.confidence_cleanup is True


def test_stack_workspace_parameters_keep_full_resolution(qtbot) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    workspace = StackWorkspace(Project.new("Stack Preview"))
    qtbot.addWidget(workspace)

    assert workspace._parameters().preview_scale == 1.0
    assert workspace.preview_button.text() == "Low-Res Preview"
    assert workspace.patch_size_spin.minimum() == -10
    assert workspace.patch_size_spin.maximum() == 10
    workspace.patch_size_spin.setValue(-3)
    assert workspace._parameters().focus_radius == 3
    assert workspace._parameters().region_bias == -3
    assert workspace._parameters().background_mode is BackgroundMode.MEDIAN
    assert workspace._parameters().confidence_cleanup is True
    assert workspace.method_combo.findData(StackingMethod.CUSTOM.value) >= 0


def test_region_bias_can_grow_depth_regions() -> None:
    scores = np.zeros((2, 9, 9), dtype=np.float32)
    scores[0] = 1.0
    scores[1, 4, 4] = 1.2
    scores[1, 3:6, 3:6] = 1.1
    depth = np.zeros((9, 9), dtype=np.uint16)
    depth[4, 4] = 1

    adjusted = adjust_depth_regions(depth, scores, 1)

    assert np.count_nonzero(adjusted == 1) > 1


def test_confidence_cleanup_replaces_unsupported_depth_island() -> None:
    scores = np.zeros((2, 11, 11), dtype=np.float32)
    scores[0] = 1.0
    scores[1, 5, 5] = 1.2
    depth = np.zeros((11, 11), dtype=np.uint16)
    depth[5, 5] = 1
    confidence = np.full((11, 11), 0.8, dtype=np.float32)
    confidence[5, 5] = 0.03

    cleaned = clean_depth_map_by_confidence(
        depth,
        scores,
        confidence,
        score_threshold=7,
        region_bias=0,
    )

    assert cleaned[5, 5] == 0


def test_decompiled_ring_cleanup_uses_sparse_neighbor_support() -> None:
    confidence = np.zeros((25, 25), dtype=np.float32)
    depth = np.zeros((25, 25), dtype=np.uint16)
    confidence[10, 12] = 0.2
    confidence[12, 14] = 0.2
    depth[10, 12] = 2
    depth[12, 14] = 4

    cleaned_confidence, cleaned_depth = decompiled_ring_supported_confidence_cleanup(
        confidence,
        depth,
        score_threshold=2,
    )

    assert cleaned_confidence[12, 12] > confidence[12, 12]
    assert cleaned_depth[12, 12] == 3
    assert cleaned_confidence[3, 3] == 0.0


def test_decompiled_confidence_background_composite_uses_score_formula() -> None:
    image = np.full((2, 2), 0.8, dtype=np.float32)
    background = np.full((2, 2), 0.2, dtype=np.float32)
    confidence = np.array([[0.0, 3 / 255], [6 / 255, 1.0]], dtype=np.float32)

    composited = decompiled_confidence_background_composite(
        image,
        background,
        confidence,
        score_threshold=2,
    )

    assert np.isclose(composited[0, 0], 0.2)
    assert 0.2 < composited[0, 1] < 0.8
    assert np.isclose(composited[1, 0], 0.8)
    assert np.isclose(composited[1, 1], 0.8)


def test_decompiled_fixed_filter_weights_match_inferred_table() -> None:
    assert decompiled_fixed_filter_weights(1) == (255, 0, 0)
    assert decompiled_fixed_filter_weights(4) == (64, 191, 0)
    assert decompiled_fixed_filter_weights(6) == (90, 115, 50)
    assert decompiled_fixed_filter_weights(10) == (0, 0, 255)


def test_decompiled_neighbor_smooth_excludes_center() -> None:
    image = np.zeros((5, 5), dtype=np.float32)
    image[2, 2] = 1.0
    image[1, 2] = 4.0
    image[2, 1] = 4.0
    image[2, 3] = 4.0
    image[3, 2] = 4.0
    image[1, 1] = 3.0
    image[1, 3] = 3.0
    image[3, 1] = 3.0
    image[3, 3] = 3.0

    smoothed = decompiled_neighbor_smooth(image)

    assert np.isclose(smoothed[2, 2], (4 * 4 * 4 + 4 * 3 * 3) / 28)


def test_stable_background_reference_modes_choose_expected_frames() -> None:
    dark = np.full((4, 4), 0.2, dtype=np.float32)
    bright = np.full((4, 4), 0.8, dtype=np.float32)

    darkest = stable_background_reference([dark, bright], BackgroundMode.DARKEST)
    brightest = stable_background_reference([dark, bright], BackgroundMode.BRIGHTEST)

    assert float(np.mean(darkest)) < 0.3
    assert float(np.mean(brightest)) > 0.7


def test_low_confidence_background_prefers_flat_reference() -> None:
    height, width = 48, 56
    y, x = np.indices((height, width))
    flat = np.full((height, width), 0.45, dtype=np.float32)
    noisy = flat + (((x * 17 + y * 11) % 5) - 2).astype(np.float32) * 0.012
    structured = flat.copy()
    structured[18:30, 20:36] = _stripe_pattern(12, 16)
    blended = noisy.copy()
    scores = np.zeros((3, height, width), dtype=np.float32)
    scores[0] = 0.2
    scores[1] = 0.22
    scores[2, 18:30, 20:36] = 1.0

    restored = blend_low_confidence_background(
        blended,
        [flat, noisy, structured],
        scores,
        score_threshold=2,
        background_mode=BackgroundMode.MEDIAN,
    )

    background = np.s_[0:12, 0:16]
    specimen = np.s_[18:30, 20:36]
    assert float(np.std(restored[background])) < float(np.std(blended[background])) * 0.5
    assert float(np.std(restored[specimen])) > float(np.std(restored[background])) * 4.0


def test_custom_background_grain_suppression_spares_structure() -> None:
    height, width = 64, 72
    y, x = np.indices((height, width))
    flat = np.full((height, width), 0.45, dtype=np.float32)
    noisy = flat + (((x * 19 + y * 13) % 7) - 3).astype(np.float32) * 0.01
    structured = flat.copy()
    structured[22:42, 24:48] = _stripe_pattern(20, 24)
    image = noisy.copy()
    image[22:42, 24:48] = structured[22:42, 24:48]
    confidence = np.full((height, width), 0.85, dtype=np.float32)
    structure = np.zeros((height, width), dtype=np.float32)
    structure[22:42, 24:48] = 0.95

    restored = suppress_custom_background_grain(
        image,
        stable_background_reference([flat, noisy, structured], BackgroundMode.MEDIAN),
        confidence,
        structure,
    )

    background = np.s_[0:16, 0:18]
    specimen = np.s_[22:42, 24:48]
    assert float(np.std(restored[background])) < float(np.std(image[background])) * 0.35
    assert float(np.std(restored[specimen])) > float(np.std(image[specimen])) * 0.9


def test_preserve_specimen_detail_uses_confident_structured_source_pixels() -> None:
    height, width = 40, 48
    sharp = np.full((height, width), 0.35, dtype=np.float32)
    blurred = sharp.copy()
    sharp[12:28, 14:34] = _stripe_pattern(16, 20)
    blurred[12:28, 14:34] = ndimage.gaussian_filter(sharp[12:28, 14:34], sigma=1.8)
    blended = (sharp + blurred) * 0.5
    weights = np.zeros((2, height, width), dtype=np.float32)
    weights[0] = 1.0

    restored = preserve_specimen_detail(
        blended,
        [sharp, blurred],
        weights,
        FocusStackParameters(detail_scale=8),
    )

    specimen = np.s_[12:28, 14:34]
    background = np.s_[0:8, 0:8]
    assert float(np.std(restored[specimen])) > float(np.std(blended[specimen]))
    assert np.allclose(restored[background], blended[background])


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


def test_custom_stack_builds_depth_map_result() -> None:
    sharp = np.zeros((32, 32), dtype=np.float32)
    sharp[:, 16:] = 1.0
    blurred = ndimage.gaussian_filter(sharp, sigma=2.0)
    params = FocusStackParameters(
        stacking_method=StackingMethod.CUSTOM,
        alignment_mode=AlignmentMode.NONE,
        score_threshold=2,
    )

    result = focus_stack([sharp, blurred], params)

    assert result.image.shape == sharp.shape
    assert result.depth_map.shape == sharp.shape
    assert result.parameters.stacking_method is StackingMethod.CUSTOM


def test_custom_stack_emits_incremental_previews() -> None:
    first = np.zeros((24, 28), dtype=np.float32)
    second = first.copy()
    third = first.copy()
    first[:, :10] = _stripe_pattern(24, 10)
    second[:, 9:19] = _stripe_pattern(24, 10)
    third[:, 18:] = _stripe_pattern(24, 10)
    previews: list[tuple[np.ndarray, str]] = []

    result = focus_stack(
        [first, second, third],
        FocusStackParameters(
            stacking_method=StackingMethod.CUSTOM,
            alignment_mode=AlignmentMode.NONE,
            adaptive_weighting=False,
            score_threshold=2,
        ),
        preview=lambda pixels, label: previews.append((pixels, label)),
    )

    assert result.image.shape == first.shape
    assert len(previews) == 3
    assert previews[-1][1] == "Stacking frame 3/3"


def test_custom_stack_keeps_focused_source_contrast() -> None:
    height, width = 56, 64
    y, x = np.indices((height, width))
    first = np.full((height, width), 0.42, dtype=np.float32)
    second = first.copy()
    first[14:42, 10:30] = ((x[14:42, 10:30] + y[14:42, 10:30]) % 4 < 2)
    second[14:42, 34:54] = ((x[14:42, 34:54] + y[14:42, 34:54]) % 4 < 2)
    first[:, 34:54] = ndimage.gaussian_filter(first[:, 34:54], sigma=1.8)
    second[:, 10:30] = ndimage.gaussian_filter(second[:, 10:30], sigma=1.8)
    params = FocusStackParameters(
        stacking_method=StackingMethod.CUSTOM,
        alignment_mode=AlignmentMode.NONE,
        adaptive_weighting=False,
        score_threshold=2,
        detail_scale=4,
    )

    result = focus_stack([first, second], params)

    assert float(np.std(result.image[18:38, 12:28])) > 0.35
    assert float(np.std(result.image[18:38, 36:52])) > 0.35


def test_pyramid_max_contrast_depth_map_tracks_focus_regions() -> None:
    height, width = 64, 64
    y, x = np.indices((height, width))
    left = np.full((height, width), 0.4, dtype=np.float32)
    right = left.copy()
    left[16:48, 10:30] = ((x[16:48, 10:30] + y[16:48, 10:30]) % 4 < 2)
    right[16:48, 34:54] = ((x[16:48, 34:54] + y[16:48, 34:54]) % 4 < 2)
    left[:, 34:54] = ndimage.gaussian_filter(left[:, 34:54], sigma=1.8)
    right[:, 10:30] = ndimage.gaussian_filter(right[:, 10:30], sigma=1.8)
    params = FocusStackParameters(
        stacking_method=StackingMethod.PYRAMID_MAX_CONTRAST,
        alignment_mode=AlignmentMode.NONE,
        score_threshold=7,
        confidence_cleanup=True,
    )

    result = focus_stack([left, right], params)

    assert np.mean(result.depth_map[20:44, 12:28]) < 0.25
    assert np.mean(result.depth_map[20:44, 36:52]) > 0.75


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
