from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

from biopic.imaging.io import import_stack
from biopic.imaging.stacking import (
    AlignmentMode,
    BackgroundMode,
    FocusMetric,
    FocusStackParameters,
    FocusStackResult,
    StackingMethod,
    focus_stack,
)
from biopic.imaging.stacking.alignment import align_stack_translation
from biopic.imaging.stacking.focus_metrics import focus_measure
from biopic.imaging.stacking import stacker as stacker_module
from biopic.imaging.stacking.stacker import (
    adjust_depth_regions,
    auto_orient_stack_images,
    blend_low_confidence_background,
    clean_depth_map_by_confidence,
    custom_confidence_stack,
    custom_stack_parameters,
    reference_confidence_background_composite,
    reference_fixed_filter_weights,
    reference_neighbor_smooth,
    reference_output_color_response,
    reference_ring_supported_confidence_cleanup,
    reference_source_buffer_image,
    reference_stack_mode_three_working_image,
    reference_suppression_buffer_blend,
    incremental_reference_custom_buffers,
    preserve_specimen_detail,
    stack_focus_measure,
    stable_background_reference,
    suppress_custom_background_grain,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.image_stack import StackKind
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
        reverse_order=True,
        skip_final_depth_buffer=True,
        debug_save_stages=True,
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
    assert restored.reverse_order is True
    assert restored.skip_final_depth_buffer is True
    assert restored.debug_save_stages is True


def test_custom_stack_parameters_force_confidence_cleanup() -> None:
    params = custom_stack_parameters(
        FocusStackParameters(
            stacking_method=StackingMethod.CUSTOM,
            focus_radius=5,
            score_threshold=2,
            smoothing_sigma=0.25,
            adaptive_weighting=False,
            scale_preset=1,
            detail_scale=10,
            confidence_cleanup=False,
        )
    )

    assert params.stacking_method is StackingMethod.CUSTOM
    assert params.focus_radius == 5
    assert params.score_threshold == 2
    assert params.scale_preset == 1
    assert params.detail_scale == 10
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
    assert workspace._parameters().reverse_order is False
    assert workspace.method_combo.findData(StackingMethod.CUSTOM.value) >= 0


def test_stack_workspace_debug_controls_follow_options_flag(qtbot) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    workspace = StackWorkspace(Project.new("Stack Debug Options"))
    qtbot.addWidget(workspace)
    custom_index = workspace.method_combo.findData(StackingMethod.CUSTOM.value)
    if custom_index >= 0:
        workspace.method_combo.setCurrentIndex(custom_index)

    workspace.skip_final_depth_buffer_check.setChecked(True)
    workspace.debug_save_stages_check.setChecked(True)
    assert workspace._parameters().skip_final_depth_buffer is False
    assert workspace._parameters().debug_save_stages is False
    assert workspace.skip_final_depth_buffer_check.isHidden()
    assert workspace.debug_save_stages_check.isHidden()
    assert workspace.cuda_check.isHidden()
    assert workspace.gpu_limit_label.isHidden()
    assert workspace.gpu_limit_spin.isHidden()

    workspace.set_debug_options_enabled(True)

    if custom_index >= 0:
        assert not workspace.skip_final_depth_buffer_check.isHidden()
        assert not workspace.debug_save_stages_check.isHidden()
    assert workspace._parameters().skip_final_depth_buffer is True
    assert workspace._parameters().debug_save_stages is True
    assert workspace.cuda_check.isHidden()
    assert workspace.gpu_limit_label.isHidden()
    assert workspace.gpu_limit_spin.isHidden()


def test_stack_workspace_reverse_button_reorders_sources(
    qtbot,
    workspace_tmp_path: Path,
) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    project = Project.new("Reverse Stack Sources")
    paths = _write_stack_images(workspace_tmp_path, "reverse-source", 3)
    stack = import_stack(project, paths, StackKind.FOCAL)
    original_order = list(stack.asset_ids)
    workspace = StackWorkspace(project)
    qtbot.addWidget(workspace)
    workspace.refresh()

    workspace.reverse_button.click()

    assert project.stacks[stack.id].asset_ids == list(reversed(original_order))
    assert [
        str(workspace.thumbnails.item(row).data(256))
        for row in range(workspace.thumbnails.count())
    ] == list(reversed(original_order))
    assert workspace._parameters().reverse_order is False


def test_stack_workspace_delete_selected_stack_removes_stack(
    qtbot,
    workspace_tmp_path: Path,
) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    project = Project.new("Delete Stack")
    paths = _write_stack_images(workspace_tmp_path, "delete-stack", 3)
    stack = import_stack(project, paths, StackKind.FOCAL)
    source_asset_ids = set(stack.asset_ids)
    workspace = StackWorkspace(project)
    qtbot.addWidget(workspace)
    workspace.refresh()

    workspace.stack_list.setCurrentRow(0)
    workspace.delete_selected_stack()

    assert stack.id not in project.stacks
    assert not source_asset_ids.intersection(project.assets)
    assert workspace._current_stack_id is None

    workspace.undo()

    assert stack.id in project.stacks
    assert source_asset_ids.issubset(project.assets)

    workspace.redo()

    assert stack.id not in project.stacks


def test_stack_workspace_delete_source_keeps_stack(
    qtbot,
    workspace_tmp_path: Path,
) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    project = Project.new("Delete Stack Source")
    paths = _write_stack_images(workspace_tmp_path, "delete-source", 3)
    stack = import_stack(project, paths, StackKind.FOCAL)
    original_order = list(stack.asset_ids)
    workspace = StackWorkspace(project)
    qtbot.addWidget(workspace)
    workspace.refresh()
    workspace.thumbnails.setCurrentRow(0)

    workspace.remove_selected_image()

    assert stack.id in project.stacks
    assert len(project.stacks[stack.id].asset_ids) == 2

    workspace.undo()

    assert project.stacks[stack.id].asset_ids == original_order

    workspace.redo()

    assert len(project.stacks[stack.id].asset_ids) == 2


def test_stack_workspace_remove_selected_sources_removes_multiple_with_undo(
    qtbot,
    workspace_tmp_path: Path,
) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    project = Project.new("Delete Multiple Sources")
    paths = _write_stack_images(workspace_tmp_path, "delete-multiple", 4)
    stack = import_stack(project, paths, StackKind.FOCAL)
    original_order = list(stack.asset_ids)
    workspace = StackWorkspace(project)
    qtbot.addWidget(workspace)
    workspace.refresh()
    workspace.thumbnails.item(1).setSelected(True)
    workspace.thumbnails.item(3).setSelected(True)

    workspace.remove_selected_image()

    assert project.stacks[stack.id].asset_ids == [original_order[0], original_order[2]]

    workspace.undo()

    assert project.stacks[stack.id].asset_ids == original_order

    workspace.redo()

    assert project.stacks[stack.id].asset_ids == [original_order[0], original_order[2]]


def test_stack_workspace_remove_image_does_not_delete_stack_when_stack_list_focused(
    qtbot,
    workspace_tmp_path: Path,
) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    project = Project.new("Remove Source Not Stack")
    paths = _write_stack_images(workspace_tmp_path, "remove-source-not-stack", 3)
    stack = import_stack(project, paths, StackKind.FOCAL)
    workspace = StackWorkspace(project)
    qtbot.addWidget(workspace)
    workspace.refresh()
    workspace.stack_list.setFocus()
    workspace.stack_list.setCurrentRow(0)

    workspace.remove_selected_image()

    assert stack.id in project.stacks
    assert len(project.stacks[stack.id].asset_ids) == 3


def test_stack_workspace_uses_bounded_source_preview(
    qtbot,
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    from biopic.ui.workspaces import stack as stack_workspace_module
    from biopic.ui.workspaces.stack import StackWorkspace

    project = Project.new("Stack Source Preview")
    paths = _write_stack_images(workspace_tmp_path, "preview-source", 2)
    stack = import_stack(project, paths, StackKind.FOCAL)
    workspace = StackWorkspace(project)
    qtbot.addWidget(workspace)
    calls: list[str] = []

    def fake_preview(asset: ImageAsset) -> np.ndarray:
        calls.append(asset.id)
        return np.zeros((6, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(stack_workspace_module, "asset_preview_pixels", fake_preview)

    workspace.refresh()

    assert calls
    assert workspace.source_canvas._pixels is not None
    assert workspace.source_canvas._pixels.shape[:2] == (6, 8)
    assert calls[-1] in stack.asset_ids


def test_stack_workspace_refresh_preserves_skip_final_preview(
    qtbot,
    workspace_tmp_path: Path,
) -> None:
    from biopic.ui.workspaces.stack import StackWorkspace

    project = Project.new("Skip Final Preview")
    paths = _write_stack_images(workspace_tmp_path, "skip-final-preview", 2)
    stack = import_stack(project, paths, StackKind.FOCAL)
    workspace = StackWorkspace(project)
    qtbot.addWidget(workspace)
    workspace.refresh()
    workspace._running_stack_id = stack.id
    workspace._current_stack_id = stack.id
    preview = np.full((8, 8, 3), 0.75, dtype=np.float32)
    final = np.full((8, 8, 3), 0.25, dtype=np.float32)
    params = FocusStackParameters(
        stacking_method=StackingMethod.CUSTOM,
        alignment_mode=AlignmentMode.NONE,
        skip_final_depth_buffer=True,
    )

    workspace._show_stack_preview(preview, "Stacking frame 2/2")
    workspace._stack_finished(
        FocusStackResult(
            image=final,
            depth_map=np.zeros((8, 8), dtype=np.uint16),
            focus_map=np.zeros((8, 8), dtype=np.float32),
            weights=np.empty((0, 8, 8), dtype=np.float32),
            transforms=[],
            parameters=params,
        )
    )
    workspace.refresh()

    assert workspace.result_canvas._pixels is not None
    assert np.allclose(workspace.result_canvas._pixels, preview)
    assert np.allclose(workspace._stack_results[stack.id], final)


def _write_stack_images(root: Path, prefix: str, count: int) -> list[Path]:
    paths: list[Path] = []
    for index in range(count):
        path = root / f"{prefix}-{index}.png"
        Image.fromarray(np.full((8, 8), index, dtype=np.uint8)).save(path)
        paths.append(path)
    return paths


def test_region_bias_can_grow_depth_regions() -> None:
    scores = np.zeros((2, 9, 9), dtype=np.float32)
    scores[0] = 1.0
    scores[1, 4, 4] = 1.2
    scores[1, 3:6, 3:6] = 1.1
    depth = np.zeros((9, 9), dtype=np.uint16)
    depth[4, 4] = 1

    adjusted = adjust_depth_regions(depth, scores, 1)

    assert np.count_nonzero(adjusted == 1) > 1


def test_reverse_order_controls_custom_incremental_tie_break() -> None:
    first = np.full((12, 12), 0.2, dtype=np.float32)
    second = np.full((12, 12), 0.8, dtype=np.float32)
    params = FocusStackParameters(
        stacking_method=StackingMethod.CUSTOM,
        alignment_mode=AlignmentMode.NONE,
        adaptive_weighting=False,
        detail_scale=1,
        score_threshold=0,
    )

    normal = focus_stack([first, second], params)
    reversed_result = focus_stack([first, second], replace(params, reverse_order=True))

    assert np.allclose(normal.image, first)
    assert np.allclose(reversed_result.image, second)


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


def test_reference_ring_cleanup_uses_sparse_neighbor_support() -> None:
    confidence = np.zeros((25, 25), dtype=np.float32)
    depth = np.zeros((25, 25), dtype=np.uint16)
    confidence[10, 12] = 0.2
    confidence[12, 14] = 0.2
    depth[10, 12] = 2
    depth[12, 14] = 4

    cleaned_confidence, cleaned_depth = reference_ring_supported_confidence_cleanup(
        confidence,
        depth,
        score_threshold=2,
    )

    assert cleaned_confidence[12, 12] > confidence[12, 12]
    assert cleaned_depth[12, 12] == 3
    assert cleaned_confidence[3, 3] == 0.0


def test_reference_confidence_background_composite_uses_score_formula() -> None:
    image = np.full((2, 2), 0.8, dtype=np.float32)
    background = np.full((2, 2), 0.2, dtype=np.float32)
    confidence = np.array([[0.0, 3 / 255], [6 / 255, 1.0]], dtype=np.float32)

    composited = reference_confidence_background_composite(
        image,
        background,
        confidence,
        score_threshold=2,
    )

    assert np.isclose(composited[0, 0], 0.2)
    assert 0.2 < composited[0, 1] < 0.8
    assert np.isclose(composited[1, 0], 0.8)
    assert np.isclose(composited[1, 1], 0.8)


def test_reference_suppression_buffer_blend_uses_score_percent() -> None:
    image = np.full((2, 2), 0.4, dtype=np.float32)
    support = np.full((2, 2), 0.9, dtype=np.float32)

    blended = reference_suppression_buffer_blend(image, support, score_threshold=20)

    assert np.allclose(blended, 0.5)


def test_reference_support_buffer_processes_frames_from_end(monkeypatch) -> None:
    images = [
        np.ones((6, 6), dtype=np.float32),
        np.zeros((6, 6), dtype=np.float32),
    ]
    calls = {"count": 0}

    def fake_score_channels(*_args, **_kwargs):
        calls["count"] += 1
        value = 0.5 if calls["count"] == 1 else 0.3
        return np.full((3, 6, 6), value, dtype=np.float32)

    monkeypatch.setattr(
        stacker_module,
        "reference_focus_score_channels",
        fake_score_channels,
    )

    params = FocusStackParameters(score_threshold=2)
    (
        _depth,
        _confidence,
        _buffers,
        _confidence_buffers,
        _id_buffers,
        _background,
        support_image,
        _support_id,
        _last_progressive,
    ) = incremental_reference_custom_buffers(images, params, progress=None, preview=None)

    assert np.allclose(support_image, 0.0)


def test_reference_fixed_filter_weights_match_inferred_table() -> None:
    assert reference_fixed_filter_weights(1) == (255, 0, 0)
    assert reference_fixed_filter_weights(4) == (64, 191, 0)
    assert reference_fixed_filter_weights(6) == (90, 115, 50)
    assert reference_fixed_filter_weights(10) == (0, 0, 255)


def test_reference_source_buffer_image_uses_byte_precision() -> None:
    image = np.array([[0.0, 0.1234, 0.5, 1.0]], dtype=np.float32)

    quantized = reference_source_buffer_image(image)

    assert np.allclose(quantized * 255.0, np.rint(image * 255.0))


def test_reference_stack_mode_three_working_image_averages_two_by_two() -> None:
    image = np.arange(4 * 4, dtype=np.float32).reshape(4, 4) / 255.0

    working = reference_stack_mode_three_working_image(image)

    assert working.shape == (2, 2)
    assert np.allclose(working[0, 0] * 255.0, 3.0)


def test_reference_working_scores_expand_by_integer_index() -> None:
    scores = np.array([[[1, 2], [3, 4]]], dtype=np.float32) / 255.0

    expanded = stacker_module._expand_reference_working_scores(scores, (4, 4))

    assert np.allclose(
        expanded[0] * 255.0,
        np.array(
            [
                [1, 1, 2, 2],
                [1, 1, 2, 2],
                [3, 3, 4, 4],
                [3, 3, 4, 4],
            ],
            dtype=np.float32,
        ),
    )


def test_reference_score_channel_resize_uses_integer_grid() -> None:
    image = np.array([[0, 20], [40, 80]], dtype=np.float32) / 255.0

    resized = stacker_module._resize_reference_score_channel(image, (4, 4), 2)

    assert np.allclose(resized[1, 1] * 255.0, 35.0)
    assert np.allclose(resized[2, 2] * 255.0, 80.0)


def test_reference_smooth_and_detail_only_overwrites_interior() -> None:
    image = np.zeros((5, 5), dtype=np.float32)
    image[0, :] = 0.5
    image[:, 0] = 0.25
    image[2, 2] = 1.0

    smooth, detail = stacker_module.reference_smooth_and_detail(image)

    assert np.allclose(smooth[0, :] * 255.0, np.rint(image[0, :] * 255.0))
    assert np.allclose(detail[:, 0] * 255.0, np.rint(image[:, 0] * 255.0))
    assert not np.isclose(smooth[2, 2], image[2, 2])


def test_reference_detail_support_score_only_writes_interior() -> None:
    detail = np.ones((5, 5), dtype=np.float32)

    score = stacker_module.reference_detail_support_score(detail, 0)

    assert np.all(score[0, :] == 0.0)
    assert np.all(score[:, 0] == 0.0)
    assert score[2, 2] > 0.0


def test_reference_neighbor_smooth_excludes_center() -> None:
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

    smoothed = reference_neighbor_smooth(image)

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


def test_custom_skip_final_depth_buffer_returns_incremental_buffer() -> None:
    first = np.zeros((24, 28, 3), dtype=np.float32)
    second = first.copy()
    first[:, :14, :] = _stripe_pattern(24, 14)[..., None]
    second[:, 14:, :] = _stripe_pattern(24, 14)[..., None]
    params = custom_stack_parameters(
        FocusStackParameters(
            stacking_method=StackingMethod.CUSTOM,
            alignment_mode=AlignmentMode.NONE,
            adaptive_weighting=False,
            skip_final_depth_buffer=True,
        )
    )
    progress_messages: list[str] = []
    previews: list[np.ndarray] = []

    result = custom_confidence_stack(
        [first, second],
        params,
        progress=lambda message, _fraction: progress_messages.append(message),
        preview=lambda image, _label: previews.append(image),
    )
    (
        _depth,
        _confidence,
        _buffers,
        _confidence_buffers,
        _id_buffers,
        _background,
        _support,
        _support_id,
        last_progressive,
    ) = (
        incremental_reference_custom_buffers(
            [reference_source_buffer_image(first), reference_source_buffer_image(second)],
            params,
            progress=None,
            preview=None,
        )
    )

    expected = last_progressive
    assert np.allclose(result.image, expected)
    assert previews
    assert np.allclose(previews[-1], result.image)
    assert "depth map" not in progress_messages


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
