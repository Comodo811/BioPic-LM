from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

import biopic.imaging.project_render as project_render_module
from biopic.imaging.io import import_images, import_stack
from biopic.imaging.editing import apply_edit_operation
from biopic.imaging.layer_buffers import layer_alpha_buffer, layer_content_buffer, set_layer_buffers
from biopic.imaging.project_render import (
    editable_assets,
    render_edit_layers,
    render_edit_layers_region,
    render_project_image,
)
from biopic.imaging.stacking import FocusStackParameters, FocusStackResult
from biopic.imaging.stacking.alignment import AlignmentTransform
from biopic.imaging.tiles import TilePaintSession
from biopic.integrations.gpl_editors import write_external_edit_image
from biopic.models.editing import AdjustmentLayer, EditLayer, LayerContentKind, LayerLock
from biopic.models.image_asset import ImageAssetKind
from biopic.models.image_stack import StackKind
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.pipeline.node import ProcessingNode
from biopic.ui.image_canvas import ImageCanvas, ndarray_to_qimage
from biopic.ui.workspace import (
    _GIMP_TOOLBOX_TOOLS,
    EditWorkspace,
    StackWorkspace,
    _catmull_rom_points,
)
import biopic.ui.workspaces.edit_background as edit_background_module
import biopic.ui.workspaces.edit_operations as edit_operations_module
from biopic.ui.workspaces.edit_filter_dialogs import _LevelsInputWidget, _levels_auto_input_bounds
from biopic.ui.workspace_helpers.icons import tool_icon


def _write_png(path: Path, value: int) -> None:
    Image.fromarray(np.full((8, 12), value, dtype=np.uint8)).save(path)


def _write_array_png(path: Path, pixels: np.ndarray) -> None:
    Image.fromarray(pixels).save(path)


def test_direct_imports_and_stack_sources_are_classified(workspace_tmp_path: Path) -> None:
    direct_path = workspace_tmp_path / "direct.png"
    stack_paths = [workspace_tmp_path / f"z{index}.png" for index in range(3)]
    _write_png(direct_path, 64)
    for index, path in enumerate(stack_paths):
        _write_png(path, 80 + index)

    project = Project.new("Roles")
    direct = import_images(project, [direct_path])[0]
    stack = import_stack(project, stack_paths, StackKind.FOCAL)

    assert direct.kind is ImageAssetKind.DIRECT_IMPORT
    assert all(
        project.assets[asset_id].kind is ImageAssetKind.STACK_SOURCE
        for asset_id in stack.asset_ids
    )
    editable = [asset for asset in project.assets.values() if asset.is_editable_browser_image]
    assert [asset.id for asset in editable] == [direct.id]


def test_editable_assets_excludes_stack_members_even_with_legacy_role(
    workspace_tmp_path: Path,
) -> None:
    direct_path = workspace_tmp_path / "direct.png"
    stack_paths = [workspace_tmp_path / f"legacy_z{index}.png" for index in range(2)]
    _write_png(direct_path, 64)
    for index, path in enumerate(stack_paths):
        _write_png(path, 90 + index)

    project = Project.new("Legacy Roles")
    direct = import_images(project, [direct_path])[0]
    stack = import_stack(project, stack_paths, StackKind.FOCAL)
    for asset_id in stack.asset_ids:
        project.assets[asset_id].kind = ImageAssetKind.DIRECT_IMPORT

    assert [asset.id for asset in editable_assets(project)] == [direct.id]


def test_edit_operation_menu_uses_requested_filter_order() -> None:
    QApplication.instance() or QApplication([])
    workspace = EditWorkspace(Project.new("Operation Order"))

    high_pass = workspace.operation_combo.findData("high_pass")
    denoise = workspace.operation_combo.findData("denoise")
    white_balance = workspace.operation_combo.findData("white_balance")
    background_correction = workspace.operation_combo.findData("flat_field_correction_estimated")

    assert high_pass >= 0
    assert denoise == high_pass + 1
    assert background_correction == white_balance + 1


def test_edit_workspace_exposes_free_rotation_controls() -> None:
    QApplication.instance() or QApplication([])
    workspace = EditWorkspace(Project.new("Rotation Controls"))

    assert "rotate" in workspace.tool_buttons
    assert workspace.tool_buttons["rotate"].toolTip()
    assert not workspace.crop_rotated_button.isHidden()
    assert not workspace.fill_rotated_background_button.isHidden()


def test_adjustment_layer_round_trips_and_invalidates_cache(workspace_tmp_path: Path) -> None:
    project = Project.new("Adjustments")
    layer = AdjustmentLayer(
        name="White Balance",
        image_node_id="source-node",
        operation="white_balance",
        parameters={"r": 1.1, "g": 1.0, "b": 0.95},
        cache_key="cached",
    )
    project.adjustment_layers[layer.id] = layer
    layer.touch()

    path = workspace_tmp_path / "adjustments.biopic.json"
    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)

    loaded_layer = loaded.adjustment_layers[layer.id]
    assert loaded_layer.operation == "white_balance"
    assert loaded_layer.parameters["r"] == 1.1
    assert loaded_layer.cache_key is None


def test_stack_result_registers_as_editable_asset(workspace_tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    stack_paths = [workspace_tmp_path / f"z{index}.png" for index in range(3)]
    for index, path in enumerate(stack_paths):
        _write_png(path, 80 + index)

    project = Project.new("Stack Result")
    stack = import_stack(project, stack_paths, StackKind.FOCAL)
    workspace = StackWorkspace(project)
    workspace._current_stack_id = stack.id
    monkeypatch.chdir(workspace_tmp_path)
    source_node_ids = tuple(
        node_id
        for asset_id in stack.asset_ids
        if (node_id := project.source_node_id_for_asset(asset_id)) is not None
    )
    node = ProcessingNode(operation="focus_stack", inputs=source_node_ids)
    project.graph.add_node(node)
    result = FocusStackResult(
        image=np.full((8, 12), 128, dtype=np.uint8),
        depth_map=np.zeros((8, 12), dtype=np.uint16),
        focus_map=np.zeros((3, 8, 12), dtype=np.float32),
        weights=np.zeros((3, 8, 12), dtype=np.float32),
        transforms=[AlignmentTransform() for _path in stack_paths],
        parameters=FocusStackParameters(),
    )

    workspace._register_stack_result_asset(result, node)

    stack_results = [
        asset for asset in project.assets.values() if asset.kind is ImageAssetKind.STACK_RESULT
    ]
    assert len(stack_results) == 1
    assert stack_results[0].is_editable_browser_image
    assert stack_results[0].metadata["source_stack_id"] == stack.id


def test_edit_workspace_creates_background_layer_and_copy_paste(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "direct.png"
    _write_png(direct_path, 120)
    project = Project.new("Editor Layers")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)

    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    assert any(
        layer.source_node_id == source_node and layer.name == "Background" and not layer.locked
        for layer in project.edit_layers.values()
    )

    workspace.copy_selection()
    workspace.paste_as_layer()

    assert any(layer.name.startswith("Pasted Layer") for layer in project.edit_layers.values())


def test_edit_workspace_creates_healed_uniform_background_layer(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    yy, xx = np.mgrid[:36, :48]
    image = np.clip(70 + xx * 2 + ((xx + yy) % 5), 0, 255).astype(np.uint8)
    image[12:24, 18:30] = 230
    direct_path = workspace_tmp_path / "healed-bg.png"
    _write_array_png(direct_path, image)
    project = Project.new("Healed Background")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)

    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    workspace._selection_coverage = np.zeros(image.shape, dtype=np.float32)
    workspace._selection_coverage[12:24, 18:30] = 1.0
    workspace._selection_rect = (18, 12, 12, 12)
    workspace._selection_shape = "mask"
    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))

    workspace.create_healed_uniform_background_outside_selection_layer()

    healed_layers = [
        layer
        for layer in project.edit_layers.values()
        if (
            layer.source_node_id == source_node
            and layer.name == "Uniform Background Outside Selection (Heal)"
        )
    ]
    organism_layers = [
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "Selected Organism"
    ]
    assert len(healed_layers) == 1
    assert organism_layers
    assert healed_layers[0].content_kind is LayerContentKind.RASTER
    assert project.active_edit_layers[source_node] == healed_layers[0].id
    assert layer_content_buffer(healed_layers[0].id) is not None


def test_uniform_background_commits_edited_lasso_selection(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "lasso-background.png"
    _write_array_png(direct_path, np.full((64, 64), 80, dtype=np.uint8))
    project = Project.new("Lasso Background")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    workspace.select_tool("free_select")
    workspace.canvas._free_selection_closed = True
    workspace.canvas._free_selection_points = [
        QPointF(8, 8),
        QPointF(18, 8),
        QPointF(28, 8),
        QPointF(38, 8),
        QPointF(38, 28),
        QPointF(8, 28),
    ]
    workspace.canvas._selection_handle_drag_started(2)
    workspace.canvas._selection_handle_moved(2, QPointF(28, 22))
    workspace.canvas._selection_handle_released()
    captured: dict[str, np.ndarray] = {}

    def fake_synthesizer(
        image: np.ndarray,
        selection_mask: np.ndarray,
        _transition_px: int,
        *,
        progress: object | None = None,
    ) -> np.ndarray:
        del progress
        captured["mask"] = selection_mask.copy()
        return image.copy()

    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))

    workspace._create_uniform_background_outside_selection_layer(
        layer_name="Uniform Background Outside Selection (Stamp)",
        command_name="uniform background outside selection",
        progress_message="Creating uniform background...",
        options_title="Uniform Background Outside Selection (Stamp)",
        synthesizer=fake_synthesizer,
    )

    assert np.any(captured["mask"])
    assert captured["mask"][22, 28]
    assert not captured["mask"][4, 28]


def test_uniform_background_uses_active_mask_when_selection_rect_is_stale(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "stale-selection-rect.png"
    _write_array_png(direct_path, np.full((32, 40), 90, dtype=np.uint8))
    project = Project.new("Stale Selection Rect")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    workspace._selection_coverage = np.zeros((32, 40), dtype=np.float32)
    workspace._selection_coverage[8:20, 12:24] = 1.0
    workspace._selection_rect = None
    workspace._selection_shape = "mask"
    captured: dict[str, np.ndarray] = {}

    def fake_synthesizer(
        image: np.ndarray,
        selection_mask: np.ndarray,
        _transition_px: int,
        *,
        progress: object | None = None,
    ) -> np.ndarray:
        del progress
        captured["mask"] = selection_mask.copy()
        return image.copy()

    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))

    workspace._create_uniform_background_outside_selection_layer(
        layer_name="Uniform Background Outside Selection (Stamp)",
        command_name="uniform background outside selection",
        progress_message="Creating uniform background...",
        options_title="Uniform Background Outside Selection (Stamp)",
        synthesizer=fake_synthesizer,
    )

    assert np.any(captured["mask"])
    assert captured["mask"][10, 14]
    assert not captured["mask"][2, 14]


def test_uniform_background_updates_edit_canvas_immediately(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "canvas-background-refresh.png"
    _write_array_png(direct_path, np.full((32, 40), 90, dtype=np.uint8))
    project = Project.new("Canvas Background Refresh")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    before_signature = workspace._loaded_asset_signature
    workspace._selection_coverage = np.zeros((32, 40), dtype=np.float32)
    workspace._selection_coverage[8:20, 12:24] = 1.0
    workspace._selection_rect = (12, 8, 12, 12)
    workspace._selection_shape = "mask"

    def fake_synthesizer(
        image: np.ndarray,
        selection_mask: np.ndarray,
        _transition_px: int,
        *,
        progress: object | None = None,
    ) -> np.ndarray:
        del progress
        result = image.copy()
        result[~selection_mask] = 15
        return result

    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))

    workspace._create_uniform_background_outside_selection_layer(
        layer_name="Uniform Background Outside Selection (Stamp)",
        command_name="uniform background outside selection",
        progress_message="Creating uniform background...",
        options_title="Uniform Background Outside Selection (Stamp)",
        synthesizer=fake_synthesizer,
    )

    assert workspace._current_pixels is not None
    assert workspace.canvas._pixels is not None
    assert int(workspace._current_pixels[2, 2]) == 15
    assert int(workspace._current_pixels[10, 14]) == 90
    assert int(workspace.canvas._pixels[2, 2]) == 15
    assert int(workspace.canvas._pixels[10, 14]) == 90
    assert workspace._loaded_asset_signature != before_signature


def test_uniform_background_stamp_uses_native_layer_alpha_when_available(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "native-background-alpha.png"
    _write_array_png(direct_path, np.full((24, 28), 90, dtype=np.uint8))
    project = Project.new("Native Background Alpha")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    workspace._selection_coverage = np.zeros((24, 28), dtype=np.float32)
    workspace._selection_coverage[6:18, 8:20] = 1.0
    workspace._selection_rect = (8, 6, 12, 12)
    workspace._selection_shape = "mask"
    native_pixels = np.full((24, 28), 23, dtype=np.uint8)
    native_alpha = np.zeros((24, 28), dtype=np.float32)
    native_alpha[:6, :] = 1.0

    def fake_native(
        image: np.ndarray,
        selection_mask: np.ndarray,
        transition_px: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        del image, selection_mask, transition_px
        return native_pixels, native_alpha, np.array(23, dtype=np.uint8)

    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))
    monkeypatch.setattr(edit_background_module, "native_uniform_background", fake_native)

    workspace.create_uniform_background_outside_selection_layer()

    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer = next(
        item
        for item in project.edit_layers.values()
        if (
            item.source_node_id == source_node
            and item.name == "Uniform Background Outside Selection (Stamp)"
        )
    )
    assert np.array_equal(layer_content_buffer(layer.id), native_pixels)
    assert np.array_equal(layer_alpha_buffer(layer.id), native_alpha)
    assert int(workspace.canvas._pixels[1, 1]) == 23
    assert int(workspace.canvas._pixels[10, 10]) == 90


def test_uniform_background_apply_button_uses_background_layer_tool(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "apply-background-tool.png"
    _write_array_png(direct_path, np.full((24, 28), 90, dtype=np.uint8))
    project = Project.new("Apply Background Tool")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    workspace._selection_coverage = np.zeros((24, 28), dtype=np.float32)
    workspace._selection_coverage[6:18, 8:20] = 1.0
    workspace._selection_rect = (8, 6, 12, 12)
    workspace._selection_shape = "mask"
    index = workspace.operation_combo.findData("uniform_background_outside_selection")
    assert index >= 0
    workspace.operation_combo.setCurrentIndex(index)
    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))

    workspace.apply_current_operation()

    assert any(
        layer.source_node_id == source_node
        and layer.name == "Uniform Background Outside Selection (Stamp)"
        and layer.filter_operation is None
        for layer in project.edit_layers.values()
    )


def test_edit_image_full_preview_matches_annotate_project_render_path(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "canonical-preview.png"
    _write_array_png(direct_path, np.full((18, 22), 90, dtype=np.uint8))
    project = Project.new("Canonical Preview")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer = EditLayer(
        name="Visible Patch",
        source_node_id=source_node,
        content_kind=LayerContentKind.RASTER,
        order=1,
    )
    project.edit_layers[layer.id] = layer
    content = np.full((18, 22), 33, dtype=np.uint8)
    alpha = np.zeros((18, 22), dtype=np.float32)
    alpha[:5, :5] = 1.0
    set_layer_buffers(layer.id, content, alpha)

    def stale_engine_render(_source_node: str, base: np.ndarray) -> np.ndarray:
        return np.zeros_like(base)

    monkeypatch.setattr(workspace._edit_engine, "render_projection", stale_engine_render)

    workspace._invalidate_edit_composite_cache()
    workspace._render_current_adjustment_preview()
    annotate_rendered = render_project_image(project, source_node)

    assert annotate_rendered is not None
    assert np.array_equal(workspace._current_pixels, annotate_rendered)
    assert np.array_equal(workspace.canvas._pixels, annotate_rendered)
    assert int(workspace.canvas._pixels[2, 2]) == 33
    assert int(workspace.canvas._pixels[10, 10]) == 90


def test_filter_toolbar_operation_creates_result_layer(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "direct.png"
    _write_png(direct_path, 120)
    project = Project.new("Filter Layer")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)

    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    before_layers = len(project.edit_layers)

    workspace.apply_named_operation("flat_field_correction_estimated")

    result_layers = [
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "Flat-Field Correction"
    ]
    assert len(project.edit_layers) == before_layers + 1
    assert result_layers
    assert result_layers[0].content_kind is LayerContentKind.RASTER
    assert result_layers[0].content is None
    assert layer_content_buffer(result_layers[0].id) is not None
    assert any(
        layer.source_node_id == source_node
        and layer.name == "Background"
        and layer.content_kind is LayerContentKind.SOURCE
        for layer in project.edit_layers.values()
    )


def test_classic_flat_field_dialog_creates_undoable_result_layer(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    raw_path = workspace_tmp_path / "flat-field-raw.png"
    reference_path = workspace_tmp_path / "flat-field-reference.png"
    _write_array_png(raw_path, np.array([[50, 100], [150, 200]], dtype=np.uint8))
    _write_array_png(reference_path, np.array([[100, 100], [200, 200]], dtype=np.uint8))
    project = Project.new("Classic Flat Field")
    asset = import_images(project, [raw_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    monkeypatch.setattr(
        workspace,
        "_classic_flat_field_reference_path",
        lambda: reference_path,
    )

    workspace.open_flat_field_dialog()

    layers = [
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "Flat-Field Correction"
    ]
    assert len(layers) == 1
    assert layer_content_buffer(layers[0].id) is not None

    workspace.undo()
    assert not [
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "Flat-Field Correction"
    ]


def test_levels_auto_input_bounds_use_selected_channel() -> None:
    image = np.zeros((20, 20, 3), dtype=np.uint8)
    image[..., 0] = np.linspace(40, 210, 20, dtype=np.uint8)[None, :]
    image[..., 1] = 128
    image[..., 2] = np.linspace(10, 250, 20, dtype=np.uint8)[None, :]

    red_low, red_high = _levels_auto_input_bounds(image, "red")
    blue_low, blue_high = _levels_auto_input_bounds(image, "blue")

    assert red_low > blue_low
    assert blue_high > red_high


def test_levels_input_widget_keeps_gimp_input_marker_order() -> None:
    QApplication.instance() or QApplication([])
    widget = _LevelsInputWidget()
    seen: list[tuple[int, float, int]] = []
    widget.on_values_changed = lambda black, gamma, white: seen.append((black, gamma, white))

    widget.set_values(250, 2.0, 10)

    black, gamma, white = widget.values()
    assert black < white
    assert 0 <= black <= 254
    assert 1 <= white <= 255
    assert gamma == 2.0
    assert seen[-1] == (black, gamma, white)


def test_adjustment_layer_undo_redo_restores_levels(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "levels-undo.png"
    _write_png(direct_path, 120)
    project = Project.new("Levels Undo")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.apply_named_operation(
        "levels",
        {
            "black_point": 0.1,
            "white_point": 0.9,
            "midtone": 1.2,
            "output_black": 0.0,
            "output_white": 1.0,
            "channel": "rgb",
        },
    )

    assert project.adjustment_layers_for_image(source_node)
    assert project.undo_stack

    workspace.undo()
    assert not project.adjustment_layers_for_image(source_node)

    workspace.redo()
    layers = project.adjustment_layers_for_image(source_node)
    assert len(layers) == 1
    assert layers[0].operation == "levels"
    assert layers[0].parameters["midtone"] == 1.2


def test_editable_adjustment_layer_updates_with_undo_redo(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "gamma-edit.png"
    _write_png(direct_path, 120)
    project = Project.new("Editable Gamma")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.apply_named_operation("gamma", {"gamma": 1.4})
    layer = project.adjustment_layers_for_image(source_node)[0]

    workspace._update_adjustment_layer_parameters(layer.id, {"gamma": 2.2})
    assert project.adjustment_layers[layer.id].parameters["gamma"] == 2.2

    workspace.undo()
    assert project.adjustment_layers[layer.id].parameters["gamma"] == 1.4

    workspace.redo()
    assert project.adjustment_layers[layer.id].parameters["gamma"] == 2.2


def test_adjustment_layer_row_exposes_settings_button(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "gamma-settings.png"
    _write_png(direct_path, 120)
    project = Project.new("Adjustment Settings Button")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.apply_named_operation("gamma", {"gamma": 1.4})
    layer = project.adjustment_layers_for_image(source_node)[0]
    called: dict[str, object] = {}
    monkeypatch.setattr(
        workspace,
        "open_gamma_dialog",
        lambda **kwargs: called.update(kwargs),
    )

    workspace._refresh_adjustments()
    item = workspace.adjustment_list.item(0)
    row = workspace.adjustment_list.itemWidget(item)
    assert row is not None
    buttons = row.findChildren(QToolButton)
    assert buttons
    assert not buttons[0].icon().isNull()

    buttons[0].click()
    QApplication.processEvents()

    assert called["layer_id"] == layer.id
    assert called["initial_parameters"] == {"gamma": 1.4}


def test_adjustment_layers_are_visible_in_layers_tab_without_double_text(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "layers-adjustments.png"
    _write_png(direct_path, 120)
    project = Project.new("Adjustment Rows In Layers")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.apply_named_operation(
        "white_balance",
        {"method": "manual", "red": 1.1, "green": 1.0, "blue": 0.95, "normalize": True},
    )
    adjustment = project.adjustment_layers_for_image(source_node)[0]

    adjustment_items = [
        workspace.layers_list.item(index)
        for index in range(workspace.layers_list.count())
        if str(workspace.layers_list.item(index).data(256)) == adjustment.id
    ]
    assert len(adjustment_items) == 1
    assert adjustment_items[0].data(257) == "adjustment"
    assert adjustment_items[0].text() == ""
    row = workspace.layers_list.itemWidget(adjustment_items[0])
    assert row is not None
    labels = [label.text() for label in row.findChildren(QLabel)]
    assert any("White Balance" in label for label in labels)

    adjustment_item = workspace.adjustment_list.item(0)
    assert adjustment_item.text() == ""


def test_white_balance_adjustment_settings_button_uses_safe_dispatch(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "white-balance-settings.png"
    _write_png(direct_path, 120)
    project = Project.new("White Balance Settings Dispatch")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    parameters = {"method": "manual", "red": 1.1, "green": 1.0, "blue": 0.95, "normalize": True}
    workspace.apply_named_operation("white_balance", parameters)
    layer = project.adjustment_layers_for_image(source_node)[0]
    called: dict[str, object] = {}
    monkeypatch.setattr(
        workspace,
        "open_white_balance_dialog",
        lambda **kwargs: called.update(kwargs),
    )

    workspace._refresh_adjustments()
    row = workspace.adjustment_list.itemWidget(workspace.adjustment_list.item(0))
    assert row is not None
    row.findChildren(QToolButton)[0].click()
    QApplication.processEvents()

    assert called["layer_id"] == layer.id
    assert called["initial_parameters"] == parameters


def test_adjustment_preview_does_not_expose_cache_tooltip(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "preview-tooltip.png"
    _write_png(direct_path, 120)
    project = Project.new("Preview Tooltip")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    workspace.apply_named_operation("gamma", {"gamma": 1.4})

    assert workspace.canvas.toolTip() == ""


def test_filter_result_layer_undo_redo_restores_high_pass(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "high-pass-undo.png"
    _write_png(direct_path, 120)
    project = Project.new("High Pass Undo")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.apply_named_operation("high_pass", {"sigma": 1.0, "amount": 1.0})

    high_pass_layers = [
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "High-Pass Filter"
    ]
    assert len(high_pass_layers) == 1
    assert project.undo_stack

    workspace.undo()
    assert not [
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "High-Pass Filter"
    ]

    workspace.redo()
    assert [
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "High-Pass Filter"
    ]


def test_filter_result_layer_stores_editable_parameters(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "editable-filter-parameters.png"
    _write_png(direct_path, 120)
    project = Project.new("Editable Filter Parameters")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    parameters = {"sigma": 1.5, "amount": 0.75}
    workspace.apply_named_operation("high_pass", parameters)

    high_pass_layer = next(
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "High-Pass Filter"
    )

    assert high_pass_layer.filter_operation == "high_pass"
    assert high_pass_layer.filter_parameters == parameters
    restored = EditLayer.from_dict(high_pass_layer.to_dict())
    assert restored.filter_operation == "high_pass"
    assert restored.filter_parameters == parameters


def test_filter_result_layer_uses_settings_row_in_layers_tab(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "editable-filter-row.png"
    _write_png(direct_path, 120)
    project = Project.new("Editable Filter Row")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    workspace.apply_named_operation("high_pass", {"sigma": 1.0, "amount": 1.0})
    QApplication.processEvents()

    rows_with_settings = 0
    for row_index in range(workspace.layers_list.count()):
        row_widget = workspace.layers_list.itemWidget(workspace.layers_list.item(row_index))
        if row_widget is not None and row_widget.findChildren(QToolButton):
            rows_with_settings += 1

    assert rows_with_settings == 1


def test_filter_layer_settings_button_opens_existing_parameters(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "editable-filter-dispatch.png"
    _write_png(direct_path, 120)
    project = Project.new("Editable Filter Dispatch")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    parameters = {"sigma": 1.25, "amount": 0.8}
    workspace.apply_named_operation("high_pass", parameters)
    high_pass_layer = next(
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "High-Pass Filter"
    )
    called: dict[str, object] = {}
    monkeypatch.setattr(
        workspace,
        "open_high_pass_dialog",
        lambda **kwargs: called.update(kwargs),
    )

    workspace._refresh_layers()
    filter_item = next(
        workspace.layers_list.item(index)
        for index in range(workspace.layers_list.count())
        if str(workspace.layers_list.item(index).data(256)) == high_pass_layer.id
    )
    row = workspace.layers_list.itemWidget(filter_item)
    assert row is not None

    row.findChildren(QToolButton)[0].click()
    QApplication.processEvents()

    assert called["layer_id"] == high_pass_layer.id
    assert called["initial_parameters"] == parameters


def test_edit_filter_layer_recomputes_content_and_is_undoable(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    yy, xx = np.mgrid[:24, :32]
    image = np.clip(40 + xx * 4 + ((xx + yy) % 7) * 8, 0, 220).astype(np.uint8)
    direct_path = workspace_tmp_path / "editable-filter-recompute.png"
    _write_array_png(direct_path, image)
    project = Project.new("Editable Filter Recompute")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    original_parameters = {"sigma": 1.0, "amount": 1.0}
    updated_parameters = {"sigma": 2.0, "amount": 0.5}
    workspace.apply_named_operation("high_pass", original_parameters)
    high_pass_layer = next(
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "High-Pass Filter"
    )

    workspace._update_filter_layer_parameters(high_pass_layer.id, updated_parameters)

    updated = layer_content_buffer(high_pass_layer.id)
    assert updated is not None
    assert high_pass_layer.filter_parameters == updated_parameters
    assert np.array_equal(updated, apply_edit_operation(image, "high_pass", updated_parameters))

    workspace.undo()
    restored = project.edit_layers[high_pass_layer.id]
    restored_content = layer_content_buffer(restored.id)
    if restored_content is None:
        restored_content = restored.content_pixels()
    assert restored.filter_parameters == original_parameters
    assert restored_content is not None
    assert np.array_equal(
        restored_content,
        apply_edit_operation(image, "high_pass", original_parameters),
    )

    workspace.redo()
    redone = project.edit_layers[high_pass_layer.id]
    redone_content = layer_content_buffer(redone.id)
    if redone_content is None:
        redone_content = redone.content_pixels()
    assert redone.filter_parameters == updated_parameters
    assert redone_content is not None
    assert np.array_equal(redone_content, updated)


def test_filter_after_levels_uses_pre_adjustment_pixels_for_high_pass(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    yy, xx = np.mgrid[:24, :32]
    image = np.clip(40 + xx * 4 + ((xx + yy) % 7) * 8, 0, 220).astype(np.uint8)
    direct_path = workspace_tmp_path / "levels-then-high-pass.png"
    _write_array_png(direct_path, image)
    project = Project.new("Levels Then High Pass")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    levels_params = {
        "black_point": 0.05,
        "white_point": 0.72,
        "midtone": 0.65,
        "output_black": 0.0,
        "output_white": 1.0,
        "channel": "rgb",
    }
    filter_params = {"sigma": 1.0, "amount": 1.0}
    workspace.apply_named_operation("levels", levels_params)
    workspace.apply_named_operation("high_pass", filter_params)

    high_pass_layer = next(
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "High-Pass Filter"
    )
    stored = layer_content_buffer(high_pass_layer.id)
    expected = apply_edit_operation(image, "high_pass", filter_params)
    wrong_double_source = apply_edit_operation(
        apply_edit_operation(image, "levels", levels_params),
        "high_pass",
        filter_params,
    )

    assert stored is not None
    assert np.array_equal(stored, expected)
    assert not np.array_equal(stored, wrong_double_source)
    assert workspace._current_pixels is not None
    assert float(np.mean(workspace._current_pixels == 255)) < 0.15


def test_filter_after_levels_uses_pre_adjustment_pixels_for_noise_reduction(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    yy, xx = np.mgrid[:24, :32]
    image = np.clip(35 + xx * 5 + ((xx * 3 + yy * 5) % 19), 0, 230).astype(np.uint8)
    direct_path = workspace_tmp_path / "levels-then-denoise.png"
    _write_array_png(direct_path, image)
    project = Project.new("Levels Then Denoise")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    levels_params = {
        "black_point": 0.04,
        "white_point": 0.75,
        "midtone": 0.7,
        "output_black": 0.0,
        "output_white": 1.0,
        "channel": "rgb",
    }
    filter_params = {"method": "gimp", "strength": 3}
    workspace.apply_named_operation("levels", levels_params)
    workspace.apply_named_operation("denoise", filter_params)

    denoise_layer = next(
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node and layer.name == "Noise Reduction"
    )
    stored = layer_content_buffer(denoise_layer.id)
    expected = apply_edit_operation(image, "denoise", filter_params)
    wrong_double_source = apply_edit_operation(
        apply_edit_operation(image, "levels", levels_params),
        "denoise",
        filter_params,
    )

    assert stored is not None
    assert np.array_equal(stored, expected)
    assert not np.array_equal(stored, wrong_double_source)
    assert workspace._current_pixels is not None
    assert float(np.mean(workspace._current_pixels == 255)) < 0.15


def test_levels_after_uniform_background_preserves_background_layer(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    image = np.full((24, 32), 90, dtype=np.uint8)
    image[8:16, 12:20] = 180
    direct_path = workspace_tmp_path / "uniform-background-then-levels.png"
    _write_array_png(direct_path, image)
    project = Project.new("Uniform Background Then Levels")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    workspace._selection_coverage = np.zeros(image.shape, dtype=np.float32)
    workspace._selection_coverage[8:16, 12:20] = 1.0
    workspace._selection_rect = (12, 8, 8, 8)
    workspace._selection_shape = "mask"

    def fake_synthesizer(
        source: np.ndarray,
        selection_mask: np.ndarray,
        _transition_px: int,
        *,
        progress: object | None = None,
    ) -> np.ndarray:
        del progress
        result = source.copy()
        result[~selection_mask] = 15
        return result

    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))

    workspace._create_uniform_background_outside_selection_layer(
        layer_name="Uniform Background Outside Selection (Stamp)",
        command_name="uniform background outside selection",
        progress_message="Creating uniform background...",
        options_title="Uniform Background Outside Selection (Stamp)",
        synthesizer=fake_synthesizer,
    )
    workspace.apply_named_operation(
        "levels",
        {
            "black_point": 0.0,
            "white_point": 1.0,
            "midtone": 1.0,
            "output_black": 0.0,
            "output_white": 1.0,
            "channel": "rgb",
        },
    )

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert workspace._current_pixels is not None
    assert int(rendered[2, 2]) == 15
    assert int(rendered[10, 14]) == 180
    assert int(workspace._current_pixels[2, 2]) == 15
    assert int(workspace._current_pixels[10, 14]) == 180


def test_high_pass_after_uniform_background_uses_uniform_background_source(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    image = np.full((24, 32), 90, dtype=np.uint8)
    image[8:16, 12:20] = 180
    direct_path = workspace_tmp_path / "uniform-background-then-high-pass.png"
    _write_array_png(direct_path, image)
    project = Project.new("Uniform Background Then High Pass")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    workspace._selection_coverage = np.zeros(image.shape, dtype=np.float32)
    workspace._selection_coverage[8:16, 12:20] = 1.0
    workspace._selection_rect = (12, 8, 8, 8)
    workspace._selection_shape = "mask"
    captured: dict[str, np.ndarray] = {}

    def fake_synthesizer(
        source: np.ndarray,
        selection_mask: np.ndarray,
        _transition_px: int,
        *,
        progress: object | None = None,
    ) -> np.ndarray:
        del progress
        result = source.copy()
        result[~selection_mask] = 15
        return result

    def capture_apply(
        source: np.ndarray,
        operation: str,
        parameters: dict[str, object],
    ) -> np.ndarray:
        if operation == "high_pass":
            captured["source"] = source.copy()
            return source.copy()
        return apply_edit_operation(source, operation, parameters)

    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))
    monkeypatch.setattr(edit_operations_module, "apply_edit_operation", capture_apply)

    workspace._create_uniform_background_outside_selection_layer(
        layer_name="Uniform Background Outside Selection (Stamp)",
        command_name="uniform background outside selection",
        progress_message="Creating uniform background...",
        options_title="Uniform Background Outside Selection (Stamp)",
        synthesizer=fake_synthesizer,
    )
    workspace.apply_named_operation("high_pass", {"sigma": 1.0, "amount": 1.0})

    assert int(captured["source"][2, 2]) == 15
    assert int(captured["source"][10, 14]) == 180


def test_noise_reduction_after_uniform_background_uses_uniform_background_source(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    image = np.full((24, 32), 90, dtype=np.uint8)
    image[8:16, 12:20] = 180
    direct_path = workspace_tmp_path / "uniform-background-then-denoise.png"
    _write_array_png(direct_path, image)
    project = Project.new("Uniform Background Then Denoise")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    workspace._selection_coverage = np.zeros(image.shape, dtype=np.float32)
    workspace._selection_coverage[8:16, 12:20] = 1.0
    workspace._selection_rect = (12, 8, 8, 8)
    workspace._selection_shape = "mask"
    captured: dict[str, np.ndarray] = {}

    def fake_synthesizer(
        source: np.ndarray,
        selection_mask: np.ndarray,
        _transition_px: int,
        *,
        progress: object | None = None,
    ) -> np.ndarray:
        del progress
        result = source.copy()
        result[~selection_mask] = 15
        return result

    def capture_apply(
        source: np.ndarray,
        operation: str,
        parameters: dict[str, object],
    ) -> np.ndarray:
        if operation == "denoise":
            captured["source"] = source.copy()
            return source.copy()
        return apply_edit_operation(source, operation, parameters)

    monkeypatch.setattr(workspace, "_uniform_background_options", lambda _title=None: (False, 0))
    monkeypatch.setattr(edit_operations_module, "apply_edit_operation", capture_apply)

    workspace._create_uniform_background_outside_selection_layer(
        layer_name="Uniform Background Outside Selection (Stamp)",
        command_name="uniform background outside selection",
        progress_message="Creating uniform background...",
        options_title="Uniform Background Outside Selection (Stamp)",
        synthesizer=fake_synthesizer,
    )
    workspace.apply_named_operation("denoise", {"method": "gimp", "strength": 3})

    assert int(captured["source"][2, 2]) == 15
    assert int(captured["source"][10, 14]) == 180


def test_uniform_background_operation_applies_as_undoable_layer(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    yy, xx = np.mgrid[:32, :40]
    image = (90 + ((xx * 5 + yy * 3) % 25)).astype(np.uint8)
    image[12:20, 16:24] = 240
    direct_path = workspace_tmp_path / "uniform-operation-layer.png"
    _write_array_png(direct_path, image)
    project = Project.new("Uniform Operation Layer")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    workspace._selection_coverage = np.zeros(image.shape, dtype=np.float32)
    workspace._selection_coverage[12:20, 16:24] = 1.0
    workspace._selection_rect = (16, 12, 8, 8)
    workspace._selection_shape = "mask"
    workspace._uniform_background_options = lambda _title=None: (False, 0)

    workspace.apply_named_operation("healed_uniform_background_outside_selection")

    assert [
        layer
        for layer in project.edit_layers.values()
        if (
            layer.source_node_id == source_node
            and layer.name == "Uniform Background Outside Selection (Heal)"
        )
    ]

    workspace.undo()
    assert not [
        layer
        for layer in project.edit_layers.values()
        if (
            layer.source_node_id == source_node
            and layer.name == "Uniform Background Outside Selection (Heal)"
        )
    ]

    workspace.redo()
    assert [
        layer
        for layer in project.edit_layers.values()
        if (
            layer.source_node_id == source_node
            and layer.name == "Uniform Background Outside Selection (Heal)"
        )
    ]


def test_edit_workspace_exposes_gimp_style_toolbox() -> None:
    tool_ids = {tool_id for tool_id, _label in _GIMP_TOOLBOX_TOOLS}

    assert {
        "rectangle_select",
        "ellipse_select",
        "move",
        "crop",
        "brush",
        "pencil",
        "erase",
        "bucket_fill",
        "color_picker",
        "zoom",
        "pan",
    }.issubset(tool_ids)


def test_edit_workspace_exposes_gamma_dialog() -> None:
    assert callable(getattr(EditWorkspace, "open_gamma_dialog"))


def test_edit_workspace_exposes_curves_dialog() -> None:
    assert callable(getattr(EditWorkspace, "open_curves_dialog"))


def test_edit_workspace_tools_modify_pixels_and_layer_controls(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "direct.png"
    _write_png(direct_path, 100)
    project = Project.new("Tools")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    workspace.add_empty_layer("Paint")
    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(4, 4)
    assert workspace._current_pixels is not None
    assert int(workspace._current_pixels[4, 4]) > 100

    workspace.duplicate_selected_layer()
    assert any(layer.name.endswith("copy") for layer in project.edit_layers.values())

    item = workspace.layers_list.item(0)
    workspace.layers_list.setCurrentItem(item)
    layer_id = str(item.data(256))
    workspace.layer_opacity_spin.setValue(50.0)
    layer = project.edit_layers[layer_id]
    assert layer.opacity == 0.5


def test_edit_workspace_merges_selected_layer_down(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "merge-down.png"
    _write_png(direct_path, 20)
    project = Project.new("Merge Down")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.add_empty_layer("Top")
    top_id = project.active_edit_layers[source_node]
    top = project.edit_layers[top_id]
    content = np.full((8, 12), 200, dtype=np.uint8)
    alpha = np.zeros((8, 12), dtype=np.float32)
    alpha[2:6, 3:9] = 0.5
    top.set_content_pixels(content)
    top.set_alpha_pixels(alpha)
    set_layer_buffers(top.id, content, alpha)
    before = render_project_image(project, source_node)
    assert before is not None
    item = next(
        workspace.layers_list.item(index)
        for index in range(workspace.layers_list.count())
        if str(workspace.layers_list.item(index).data(256)) == top_id
    )
    workspace.layers_list.setCurrentItem(item)

    workspace.merge_selected_layer_down()

    after = render_project_image(project, source_node)
    assert after is not None
    np.testing.assert_array_equal(after, before)
    assert top_id not in project.edit_layers
    assert len([
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node
    ]) == 1
    target_id = project.active_edit_layers[source_node]
    assert project.edit_layers[target_id].content_kind is LayerContentKind.RASTER
    assert layer_content_buffer(target_id) is not None
    assert layer_alpha_buffer(target_id) is not None
    assert project.undo_stack[-1]["description"] == "merge layer down"

    workspace.undo()

    assert top_id in project.edit_layers
    assert len([
        layer
        for layer in project.edit_layers.values()
        if layer.source_node_id == source_node
    ]) == 2


def test_layer_opacity_slider_batches_render_and_undo(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "opacity-slider.png"
    _write_png(direct_path, 100)
    project = Project.new("Opacity Slider")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()
    item = workspace.layers_list.currentItem()
    assert item is not None
    layer_id = str(item.data(256))

    render_count = 0

    def count_render() -> None:
        nonlocal render_count
        render_count += 1

    monkeypatch.setattr(workspace, "_render_current_adjustment_preview", count_render)

    workspace.layer_opacity_slider.setValue(80)
    workspace.layer_opacity_slider.setValue(60)
    workspace.layer_opacity_slider.setValue(40)

    assert project.edit_layers[layer_id].opacity == 0.4
    assert workspace.layer_opacity_spin.value() == 40.0
    assert len(project.undo_stack) == 0
    assert render_count == 0

    workspace._flush_pending_layer_opacity_render()
    workspace._commit_pending_layer_opacity_change()

    assert render_count == 1
    assert project.undo_stack[-1]["kind"] == "layer_metadata"
    assert project.undo_stack[-1]["description"] == "change layer opacity"


def test_filter_layer_row_text_stays_empty_after_opacity_change(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "filter-row-opacity.png"
    _write_png(direct_path, 100)
    project = Project.new("Filter Row Opacity")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer = EditLayer(
        name="High-Pass Filter",
        source_node_id=source_node,
        content_kind=LayerContentKind.RASTER,
        filter_operation="high_pass",
        order=workspace._next_layer_order(source_node),
    )
    project.edit_layers[layer.id] = layer
    project.active_edit_layers[source_node] = layer.id
    workspace._current_layer_id = layer.id
    workspace._refresh_layers()
    item = next(
        workspace.layers_list.item(index)
        for index in range(workspace.layers_list.count())
        if str(workspace.layers_list.item(index).data(256)) == layer.id
    )
    assert workspace.layers_list.itemWidget(item) is not None

    workspace.layers_list.setCurrentItem(item)
    workspace.layer_opacity_slider.setValue(55)
    workspace._commit_pending_layer_opacity_change()

    assert item.text() == ""


def test_layer_visibility_changes_composite_and_undo_redo(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "direct.png"
    _write_png(direct_path, 10)
    project = Project.new("Visibility")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.add_empty_layer("White paint")
    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(4, 4)
    painted = render_project_image(project, source_node)
    assert painted is not None
    assert int(painted[4, 4]) == 255

    layer_id = project.active_edit_layers[source_node]
    item = next(
        workspace.layers_list.item(index)
        for index in range(workspace.layers_list.count())
        if str(workspace.layers_list.item(index).data(256)) == layer_id
    )
    workspace.layers_list.setCurrentItem(item)
    workspace.layer_visible_check.setChecked(False)
    hidden = render_project_image(project, source_node)
    assert hidden is not None
    assert int(hidden[4, 4]) == 10

    workspace.undo()
    restored = render_project_image(project, source_node)
    assert restored is not None
    assert int(restored[4, 4]) == 255

    workspace.redo()
    hidden_again = render_project_image(project, source_node)
    assert hidden_again is not None
    assert int(hidden_again[4, 4]) == 10


def test_layer_model_persists_addressable_drawable_and_mask_state() -> None:
    layer = EditLayer("Layer")

    restored = EditLayer.from_dict(layer.to_dict())

    assert restored.image_item_id == layer.image_item_id
    assert restored.drawable_id == layer.drawable_id
    assert restored.tile_store_id == layer.tile_store_id
    assert restored.graph_node_id == layer.graph_node_id
    assert restored.generation == layer.generation
    assert restored.mask_enabled is True


def test_layer_mask_modulates_alpha_without_flattening() -> None:
    base = np.zeros((3, 3), dtype=np.uint8)
    layer = EditLayer(
        "Masked",
        source_node_id="node",
        content_kind=LayerContentKind.RASTER,
    )
    layer.set_content_pixels(np.full((3, 3), 255, dtype=np.uint8))
    layer.set_alpha_pixels(np.ones((3, 3), dtype=np.float32))
    mask = np.zeros((3, 3), dtype=np.float32)
    mask[1, 1] = 1.0
    layer.set_mask_pixels(mask)
    project = Project.new("Mask")
    project.edit_layers[layer.id] = layer

    rendered = render_edit_layers(project, "node", base)
    region = render_edit_layers_region(project, "node", base, (1, 1, 1, 1))

    assert int(rendered[1, 1]) == 255
    assert int(rendered[0, 0]) == 0
    assert int(region[0, 0]) == 255


def test_layer_lock_toggle_does_not_repaint_canvas(
    workspace_tmp_path: Path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "lock-metadata.png"
    _write_png(direct_path, 20)
    project = Project.new("Lock Metadata")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer_id = project.active_edit_layers[source_node]

    def fail_render() -> None:
        raise AssertionError("lock-only layer changes must not repaint the canvas")

    monkeypatch.setattr(workspace, "_render_current_adjustment_preview", fail_render)
    item = next(
        workspace.layers_list.item(index)
        for index in range(workspace.layers_list.count())
        if str(workspace.layers_list.item(index).data(256)) == layer_id
    )
    workspace.layers_list.setCurrentItem(item)

    workspace.layer_lock_check.setChecked(True)

    assert LayerLock.PIXELS in project.edit_layers[layer_id].lock_flags
    assert "pixels" in item.text()
    assert project.undo_stack[-1]["kind"] == "layer_metadata"


def test_edit_refresh_reuses_current_render_when_image_state_is_unchanged(
    workspace_tmp_path: Path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "refresh-cache.png"
    _write_png(direct_path, 20)
    project = Project.new("Edit Refresh Cache")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    def fail_render() -> None:
        raise AssertionError("unchanged edit refresh must reuse the current render")

    monkeypatch.setattr(workspace, "_render_current_adjustment_preview", fail_render)

    workspace.refresh()


def test_duplicate_layer_shares_live_buffers_until_edit(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "cow-duplicate.png"
    _write_png(direct_path, 0)
    project = Project.new("Copy On Write Duplicate")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.select_tool("brush")
    workspace._tool_point_clicked(1, 1)
    original_id = project.active_edit_layers[source_node]
    original_content = layer_content_buffer(original_id)
    assert original_content is not None

    workspace.duplicate_selected_layer()
    duplicate_id = project.active_edit_layers[source_node]
    assert duplicate_id != original_id
    assert layer_content_buffer(duplicate_id) is original_content
    assert project.edit_layers[duplicate_id].content is project.edit_layers[original_id].content


def test_lock_rejects_paint_until_unlocked(workspace_tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "direct.png"
    _write_png(direct_path, 20)
    project = Project.new("Lock")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.add_empty_layer("Paint")
    layer_id = project.active_edit_layers[source_node]
    project.edit_layers[layer_id].locked = True
    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(4, 4)
    locked = render_project_image(project, source_node)
    assert locked is not None
    assert int(locked[4, 4]) == 20

    project.edit_layers[layer_id].locked = False
    workspace._tool_point_clicked(4, 4)
    unlocked = render_project_image(project, source_node)
    assert unlocked is not None
    assert int(unlocked[4, 4]) == 255


def test_visibility_lock_rejects_hide_toggle(workspace_tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "visibility-lock.png"
    _write_png(direct_path, 20)
    project = Project.new("Visibility Lock")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer_id = project.active_edit_layers[source_node]
    layer = project.edit_layers[layer_id]
    layer.lock_flags.add(LayerLock.VISIBILITY)
    workspace._update_current_layer_item(layer)

    workspace.layer_visible_check.setChecked(False)

    assert layer.visible
    assert workspace.layer_visible_check.isChecked()
    assert "visibility" in workspace.layers_list.currentItem().text()


def test_pixel_lock_allows_layer_drag_preview(workspace_tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "pixel-lock-move.png"
    _write_png(direct_path, 20)
    project = Project.new("Pixel Lock Move")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer_id = project.active_edit_layers[source_node]
    layer = project.edit_layers[layer_id]
    layer.lock_flags.add(LayerLock.PIXELS)

    workspace._begin_layer_move(0, 0)
    workspace._preview_layer_move(0, 0, 3, 2, force=True)

    assert layer.offset_x == 3
    assert layer.offset_y == 2


def test_layer_order_round_trips_and_changes_composite(workspace_tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "direct.png"
    _write_png(direct_path, 0)
    project = Project.new("Order")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.add_empty_layer("Dark")
    dark_id = project.active_edit_layers[source_node]
    workspace.secondary_spin.setValue(80)
    workspace.select_tool("bucket_fill")
    workspace._tool_point_clicked(1, 1)
    workspace.add_empty_layer("Bright")
    bright_id = project.active_edit_layers[source_node]
    workspace.secondary_spin.setValue(200)
    workspace._tool_point_clicked(1, 1)
    top_bright = render_project_image(project, source_node)
    assert top_bright is not None
    assert int(top_bright[1, 1]) == 200

    project.edit_layers[bright_id].order = 1
    project.edit_layers[dark_id].order = 2
    top_dark = render_project_image(project, source_node)
    assert top_dark is not None
    assert int(top_dark[1, 1]) == 80

    path = workspace_tmp_path / "order.biopic.json"
    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)
    assert loaded.edit_layers[bright_id].order == 1
    assert loaded.edit_layers[dark_id].order == 2


def test_unlocked_source_background_can_be_painted(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "stacked-result.png"
    _write_png(direct_path, 40)
    project = Project.new("Stacked Result Editing")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    background_id = project.active_edit_layers[source_node]
    background = project.edit_layers[background_id]
    assert not background.locked

    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(4, 4)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[4, 4]) == 255
    assert project.edit_layers[background_id].content_kind.value == "raster"


def test_external_editor_result_imports_as_unlocked_layer(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "external-source.png"
    external_path = workspace_tmp_path / "external-edit.tif"
    _write_png(direct_path, 40)
    project = Project.new("External GPL Editor")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    write_external_edit_image(external_path, np.full((8, 12), 180, dtype=np.uint8))
    workspace._pending_external_edit_path = external_path
    workspace.import_external_editor_result()

    layer_id = project.active_edit_layers[source_node]
    imported_layer = project.edit_layers[layer_id]
    assert imported_layer.name.startswith("External Edit")
    assert not imported_layer.locked
    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[4, 4]) == 180


def test_rectangle_selection_constrains_brush_painting(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "selection.png"
    _write_png(direct_path, 30)
    project = Project.new("Selection")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    project.edit_layers[project.active_edit_layers[source_node]].locked = False
    workspace.select_tool("rectangle_select")
    workspace._tool_selection_completed("rectangle", 0, 0, 3, 3, [])
    workspace.select_tool("brush")
    workspace.primary_spin.setValue(3)
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(2, 2)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 1]) > 30
    assert int(rendered[5, 5]) == 30


def test_brush_drag_batches_project_commit_until_stroke_end(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "stroke.png"
    _write_png(direct_path, 25)
    project = Project.new("Stroke")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    project.edit_layers[project.active_edit_layers[source_node]].locked = False
    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(1, 1)
    workspace._tool_point_clicked(2, 1)
    workspace._tool_point_clicked(3, 1)
    assert len(project.undo_stack) == 0
    workspace._finish_paint_stroke()

    assert len(project.undo_stack) == 1
    assert project.undo_stack[-1]["kind"] == "tile_paint"
    assert "state" not in project.undo_stack[-1]
    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[2, 1]) == 255
    workspace.undo()
    undone = render_project_image(project, source_node)
    assert undone is not None
    assert int(undone[2, 1]) == 25
    workspace.redo()
    redone = render_project_image(project, source_node)
    assert redone is not None
    assert int(redone[2, 1]) == 255


def test_undo_after_layer_command_preserves_live_painted_background(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "painted-background-undo.png"
    _write_png(direct_path, 25)
    project = Project.new("Painted Background Undo")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    project.edit_layers[project.active_edit_layers[source_node]].locked = False
    workspace.select_tool("brush")
    workspace.primary_spin.setValue(1)
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(2, 2)
    workspace._finish_paint_stroke()

    workspace.add_empty_layer("Temporary")
    workspace.undo()

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered.max()) == 255
    assert int(rendered[0, 0]) == 25
    assert int(rendered[2, 2]) == 255


def test_brush_drag_uses_tile_session_not_full_layer_edit(
    workspace_tmp_path: Path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "tile-session.png"
    _write_png(direct_path, 25)
    project = Project.new("Tile Session")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    def fail_full_layer_edit(*_args: object, **_kwargs: object) -> np.ndarray:
        raise AssertionError("brush drag should use tile-backed painting")

    monkeypatch.setattr(workspace, "_layer_content_for_edit", fail_full_layer_edit)
    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(1, 1)
    workspace._tool_point_clicked(6, 1)
    workspace._finish_paint_stroke()

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 3]) == 255


def test_clone_stamp_copies_from_user_source(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    pixels = np.arange(96, dtype=np.uint8).reshape(8, 12)
    direct_path = workspace_tmp_path / "clone-source.png"
    _write_array_png(direct_path, pixels)
    project = Project.new("Clone Source")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    workspace.select_tool("clone")
    workspace.primary_spin.setValue(1)
    workspace._set_clone_source_point(2, 2)
    workspace._tool_point_clicked(8, 2)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[2, 8]) == int(pixels[2, 2])
    assert int(rendered[2, 7]) == int(pixels[2, 1])
    assert int(rendered[2, 9]) == int(pixels[2, 3])
    assert project.undo_stack[-1]["kind"] == "tile_paint"


def test_clone_and_heal_tools_have_icons() -> None:
    assert tool_icon("clone") is not None
    assert tool_icon("heal") is not None


def test_clone_drag_keeps_aligned_source_offset(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    pixels = np.arange(96, dtype=np.uint8).reshape(8, 12)
    direct_path = workspace_tmp_path / "clone-drag.png"
    _write_array_png(direct_path, pixels)
    project = Project.new("Clone Drag")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    workspace.select_tool("clone")
    workspace.primary_spin.setValue(1)
    workspace._set_clone_source_point(1, 1)
    workspace._begin_paint_stroke()
    workspace._paint_point_moved(6.0, 1.0)
    workspace._paint_point_moved(7.0, 1.0)
    workspace._finish_paint_stroke()

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 6]) == int(pixels[1, 1])
    assert int(rendered[1, 7]) == int(pixels[1, 2])


def test_clone_drag_previews_stamped_pixels_before_commit(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    pixels = np.arange(96, dtype=np.uint8).reshape(8, 12)
    direct_path = workspace_tmp_path / "clone-live-preview.png"
    _write_array_png(direct_path, pixels)
    project = Project.new("Clone Live Preview")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    workspace.select_tool("clone")
    workspace.primary_spin.setValue(1)
    workspace._set_clone_source_point(1, 1)
    workspace._begin_paint_stroke()
    workspace._paint_point_moved(6.0, 1.0)

    assert workspace._current_pixels is not None
    assert int(workspace._current_pixels[1, 6]) == int(pixels[1, 1])
    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 6]) == int(pixels[1, 6])

    workspace._finish_paint_stroke()


def test_clone_stamp_respects_selection(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    pixels = np.arange(96, dtype=np.uint8).reshape(8, 12)
    direct_path = workspace_tmp_path / "clone-selection.png"
    _write_array_png(direct_path, pixels)
    project = Project.new("Clone Selection")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    workspace.select_tool("rectangle_select")
    workspace._tool_selection_completed("rectangle", 8, 2, 1, 1, [])
    workspace.select_tool("clone")
    workspace.primary_spin.setValue(1)
    workspace._set_clone_source_point(2, 2)
    workspace._tool_point_clicked(8, 2)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[2, 8]) == int(pixels[2, 2])
    assert int(rendered[2, 7]) == int(pixels[2, 7])
    assert int(rendered[2, 9]) == int(pixels[2, 9])


def test_heal_uses_source_texture_but_destination_brightness(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    pixels = np.full((9, 13), 200, dtype=np.uint8)
    pixels[3:6, 1:4] = np.array(
        [
            [35, 50, 65],
            [40, 55, 70],
            [45, 60, 75],
        ],
        dtype=np.uint8,
    )
    pixels[4, 9] = 0
    direct_path = workspace_tmp_path / "heal-source.png"
    _write_array_png(direct_path, pixels)
    project = Project.new("Heal Source")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    workspace.select_tool("heal")
    workspace.primary_spin.setValue(1)
    workspace._set_clone_source_point(2, 4)
    workspace._tool_point_clicked(9, 4)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[4, 9]) > 120
    assert int(rendered[4, 9]) != int(pixels[4, 2])
    assert project.undo_stack[-1]["kind"] == "tile_paint"


def test_heal_requires_user_source(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    pixels = np.full((8, 12), 180, dtype=np.uint8)
    pixels[2, 8] = 0
    direct_path = workspace_tmp_path / "heal-no-source.png"
    _write_array_png(direct_path, pixels)
    project = Project.new("Heal No Source")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    workspace.select_tool("heal")
    workspace.primary_spin.setValue(1)
    workspace._tool_point_clicked(8, 2)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[2, 8]) == 0


def test_tile_paint_commit_keeps_layer_payload_deferred_until_save(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "deferred-payload.png"
    _write_png(direct_path, 25)
    project = Project.new("Deferred Payload")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer_id = project.active_edit_layers[source_node]
    layer = project.edit_layers[layer_id]
    original_content = layer.content

    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(1, 1)
    workspace._finish_paint_stroke()

    assert layer.content is original_content
    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 1]) == 255

    path = workspace_tmp_path / "deferred-payload.biopic.json"
    ProjectStore().save(project, path)
    assert layer.content is not None
    loaded = ProjectStore().load(path)
    loaded_rendered = render_project_image(loaded, source_node)
    assert loaded_rendered is not None
    assert int(loaded_rendered[1, 1]) == 255


def test_tile_paint_commit_patches_projection_without_full_preview_render(
    workspace_tmp_path: Path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "projection-patch.png"
    _write_png(direct_path, 25)
    project = Project.new("Projection Patch")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    workspace._render_current_adjustment_preview()

    def fail_full_preview() -> None:
        raise AssertionError("tile paint should patch the dirty projection region")

    monkeypatch.setattr(workspace, "_render_current_adjustment_preview", fail_full_preview)
    full_display_updates = 0
    dirty_tile_updates = 0

    def count_set_pixels(*_args: object, **_kwargs: object) -> None:
        nonlocal full_display_updates
        full_display_updates += 1

    original_update_tile_regions = workspace.canvas.update_tile_regions

    def count_update_tile_regions(*args: object, **kwargs: object) -> None:
        nonlocal dirty_tile_updates
        dirty_tile_updates += 1
        original_update_tile_regions(*args, **kwargs)

    monkeypatch.setattr(workspace.canvas, "set_pixels", count_set_pixels)
    monkeypatch.setattr(workspace.canvas, "update_tile_regions", count_update_tile_regions)
    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(1, 1)
    workspace._finish_paint_stroke()

    assert workspace._current_pixels is not None
    assert int(workspace._current_pixels[1, 1]) == 255
    assert full_display_updates == 0
    assert dirty_tile_updates == 1


def test_edit_composite_cache_key_tracks_layer_generation(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "generation-cache.png"
    _write_png(direct_path, 25)
    project = Project.new("Generation Cache")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    layer = EditLayer(
        name="Mutable raster",
        source_node_id=source_node,
        content_kind=LayerContentKind.RASTER,
        order=workspace._next_layer_order(source_node),
    )
    project.edit_layers[layer.id] = layer
    content = np.full((8, 12), 100, dtype=np.uint8)
    alpha = np.ones((8, 12), dtype=np.float32)
    set_layer_buffers(layer.id, content, alpha)

    first = workspace._render_edit_composite_cached(source_node)
    assert int(first[1, 1]) == 100

    content[:, :] = 200
    layer.bump_generation()
    second = workspace._render_edit_composite_cached(source_node)

    assert int(second[1, 1]) == 200


def test_project_render_cache_reuses_canonical_pixels_between_workspaces(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    direct_path = workspace_tmp_path / "shared-render-cache.png"
    _write_png(direct_path, 25)
    project = Project.new("Shared Render Cache")
    asset = import_images(project, [direct_path])[0]
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project_render_module.clear_project_render_cache()

    first = render_project_image(project, source_node)

    def fail_render_edit_layers(*_args: object, **_kwargs: object) -> np.ndarray:
        raise AssertionError("unchanged project render should come from shared cache")

    monkeypatch.setattr(project_render_module, "render_edit_layers", fail_render_edit_layers)

    second = render_project_image(project, source_node)

    assert second is first


def test_project_render_cache_key_tracks_live_layer_buffers(
    workspace_tmp_path: Path,
) -> None:
    direct_path = workspace_tmp_path / "shared-render-live-buffer.png"
    _write_png(direct_path, 25)
    project = Project.new("Shared Render Live Buffer")
    asset = import_images(project, [direct_path])[0]
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project_render_module.clear_project_render_cache()
    layer = EditLayer(
        name="Live Buffer",
        source_node_id=source_node,
        content_kind=LayerContentKind.RASTER,
        order=1,
    )
    project.edit_layers[layer.id] = layer
    first_content = np.full((8, 12), 100, dtype=np.uint8)
    alpha = np.ones((8, 12), dtype=np.float32)
    set_layer_buffers(layer.id, first_content, alpha)

    first = render_project_image(project, source_node)

    second_content = np.full((8, 12), 200, dtype=np.uint8)
    set_layer_buffers(layer.id, second_content, alpha)
    second = render_project_image(project, source_node)

    assert first is not second
    assert int(first[1, 1]) == 100
    assert int(second[1, 1]) == 200


def test_tile_paint_dirty_rect_tracks_dab_bounds_not_full_tile() -> None:
    base = np.zeros((512, 512), dtype=np.uint8)
    session = TilePaintSession(base, None, None)

    dirty_rect = session.paint_content_and_alpha([(10, 10)], 2, 255)

    assert dirty_rect == (7, 7, 7, 7)
    assert session.dirty_rect() == (7, 7, 7, 7)


def test_long_diagonal_stroke_keeps_sparse_dirty_rectangles() -> None:
    base = np.zeros((512, 512), dtype=np.uint8)
    session = TilePaintSession(base, None, None)
    points = [(index, index) for index in range(20, 490, 12)]

    dirty_rect = session.paint_content_and_alpha(points, 4, 255)
    dirty_area = sum(width * height for _x, _y, width, height in session.last_dirty_rects())

    assert dirty_rect is not None
    assert dirty_rect[2] > 400
    assert dirty_rect[3] > 400
    assert dirty_area < dirty_rect[2] * dirty_rect[3] // 3


def test_brush_stroke_uses_owned_preview_buffer(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "owned-preview-buffer.png"
    _write_png(direct_path, 0)
    project = Project.new("No Preview Copy")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    current_pixels = workspace._current_pixels
    workspace.select_tool("brush")
    workspace._begin_paint_stroke()

    assert workspace._paint_stroke_preview is not current_pixels
    assert workspace._paint_stroke_preview is not None
    assert workspace._paint_stroke_preview.flags["C_CONTIGUOUS"]
    assert np.array_equal(workspace._paint_stroke_preview, current_pixels)


def test_region_edit_projection_matches_full_projection(workspace_tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "region-project.png"
    _write_png(direct_path, 0)
    project = Project.new("Region Projection")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.add_empty_layer("Paint")
    workspace.select_tool("brush")
    workspace.primary_spin.setValue(2)
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(5, 4)

    base = np.full((8, 12), 0, dtype=np.uint8)
    rect = (3, 2, 5, 5)
    full = render_edit_layers(project, source_node, base)
    region = render_edit_layers_region(project, source_node, base, rect)

    x, y, width, height = rect
    assert np.array_equal(region, full[y : y + height, x : x + width])


def test_single_point_brush_uses_tile_paint_session(
    workspace_tmp_path: Path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "single-point-tile.png"
    _write_png(direct_path, 0)
    project = Project.new("Single Point Tile")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    def fail_old_paint_path(*_args, **_kwargs) -> None:
        raise AssertionError("brush/pencil/eraser must not use the old full-image paint path")

    monkeypatch.setattr(workspace, "_paint_stroke_constrained", fail_old_paint_path)
    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(4, 4)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[4, 4]) == 255
    assert workspace._paint_tile_session is None


def test_image_canvas_displays_large_images_as_tiles() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    pixels = np.zeros((300, 520), dtype=np.uint8)

    canvas.set_pixels(pixels, fit=False)

    assert len(canvas._tile_items) == 6


def test_image_canvas_zoom_preserves_cursor_scene_point() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.resize(400, 300)
    canvas.set_pixels(np.zeros((1000, 1000), dtype=np.uint8), fit=False)
    canvas.show()
    QApplication.processEvents()
    cursor = canvas.viewport().rect().bottomRight() - QPointF(40, 40).toPoint()
    before = canvas.mapToScene(cursor)

    canvas._zoom_at_view_position(cursor, 1.25)
    QApplication.processEvents()

    after = canvas.mapToScene(cursor)
    assert abs(after.x() - before.x()) <= 0.5
    assert abs(after.y() - before.y()) <= 0.5


def test_canvas_tiles_use_global_display_range_for_uint16() -> None:
    full_range = (0.0, 1000.0)
    uniform_dirty_tile = np.full((16, 16), 1000, dtype=np.uint16)

    image = ndarray_to_qimage(uniform_dirty_tile, full_range)

    assert image.pixelColor(0, 0).value() == 255


def test_normalized_float_display_uses_fixed_unit_range() -> None:
    pixels = np.array([[0.25, 0.5]], dtype=np.float32)

    image = ndarray_to_qimage(pixels)

    assert image.pixelColor(0, 0).value() == 63
    assert image.pixelColor(1, 0).value() == 127


def test_canvas_paint_preview_does_not_grow_without_bound() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((32, 256), dtype=np.uint8), fit=False)

    for x in range(180):
        canvas.extend_paint_preview([(x, 12)], 2, QColor(255, 255, 255))

    assert len(canvas._paint_preview_segments) <= 32
    canvas.clear_paint_preview()
    assert not canvas._paint_preview_segments


def test_lasso_handle_move_bends_hidden_sample_points() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((120, 160), dtype=np.uint8), fit=False)
    canvas.set_tool_mode("free_select")
    canvas._free_selection_closed = True
    canvas._free_selection_points = [
        QPointF(10, 10),
        QPointF(30, 10),
        QPointF(50, 10),
        QPointF(70, 10),
        QPointF(90, 10),
        QPointF(100, 80),
        QPointF(10, 80),
    ]

    canvas._selection_handle_moved(2, QPointF(50, 50))

    assert canvas._free_selection_points[2] == QPointF(50, 50)
    assert 10 < canvas._free_selection_points[1].y() < 50
    assert 10 < canvas._free_selection_points[3].y() < 50
    assert canvas._free_selection_points[0] == QPointF(10, 10)
    assert canvas._free_selection_points[5] == QPointF(100, 80)


def test_lasso_handles_do_not_draw_qt_selection_boxes() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((80, 80), dtype=np.uint8), fit=False)
    canvas.set_tool_mode("free_select")
    canvas._free_selection_points = [
        QPointF(10, 10),
        QPointF(35, 10),
        QPointF(35, 35),
        QPointF(10, 35),
    ]
    canvas._free_selection_closed = True
    canvas._set_free_selection_handles(canvas._free_selection_points)

    handle = canvas._selection_handles[0]

    assert not handle.flags() & handle.GraphicsItemFlag.ItemIsSelectable
    handle.setSelected(True)
    assert not handle.isSelected()


def test_lasso_clicking_first_handle_closes_open_selection() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((80, 80), dtype=np.uint8), fit=False)
    canvas.set_tool_mode("free_select")
    canvas._free_selection_points = [
        QPointF(10, 10),
        QPointF(35, 10),
        QPointF(35, 35),
        QPointF(10, 35),
    ]
    canvas._free_selection_drawing = True
    canvas._free_selection_closed = False
    canvas._set_free_selection_handles(canvas._free_selection_points)

    view_pos = QPointF(canvas.mapFromScene(canvas._free_selection_points[0]))
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        view_pos,
        view_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert canvas._lasso_handle_at(view_pos.toPoint()) is not None

    canvas.mousePressEvent(event)

    assert canvas._free_selection_closed is True
    assert canvas._free_selection_drawing is False


def test_lasso_sequential_handle_moves_do_not_jump_to_origin() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((120, 160), dtype=np.uint8), fit=False)
    canvas.set_tool_mode("free_select")
    canvas._free_selection_closed = True
    canvas._free_selection_points = [
        QPointF(20, 20),
        QPointF(35, 20),
        QPointF(50, 20),
        QPointF(65, 20),
        QPointF(80, 20),
        QPointF(95, 20),
        QPointF(95, 90),
        QPointF(20, 90),
    ]

    canvas._selection_handle_drag_started(2)
    canvas._selection_handle_moved(2, QPointF(50, 55))
    canvas._selection_handle_released()
    canvas._selection_handle_drag_started(4)
    canvas._selection_handle_moved(4, QPointF(80, 58))
    canvas._selection_handle_released()

    assert canvas._free_selection_points[2] == QPointF(50, 55)
    assert canvas._free_selection_points[4] == QPointF(80, 58)
    assert all(point.x() > 0 and point.y() > 0 for point in canvas._free_selection_points)
    assert canvas._selection_path_item.path().boundingRect().top() >= 19


def test_brush_drag_motion_uses_incremental_tile_paint(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "incremental-drag.png"
    _write_png(direct_path, 0)
    project = Project.new("Incremental Drag")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    for x in range(1, 11):
        workspace._paint_point_moved(float(x), 1.0)

    assert not workspace._paint_live_points
    assert len(workspace.canvas._paint_preview_segments) == 1
    assert workspace._paint_work_queue.depth() > 0

    workspace._flush_queued_paint_points()
    assert workspace._current_pixels is not None
    assert int(workspace._current_pixels[1, 6]) == 255

    workspace._finish_paint_stroke()
    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 6]) == 255
    assert not workspace.canvas._paint_preview_segments


def test_brush_drag_tail_preview_reaches_current_pointer_before_flush(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "tail-preview.png"
    _write_png(direct_path, 0)
    project = Project.new("Tail Preview")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    workspace.select_tool("brush")
    workspace._begin_paint_stroke()
    workspace._paint_point_moved(2.0, 1.0)
    workspace._paint_point_moved(10.0, 1.0)

    assert not workspace._paint_live_points
    assert workspace._paint_work_queue.depth() == 2
    assert len(workspace.canvas._paint_preview_segments) == 1
    assert workspace.canvas._paint_preview_tail == (10, 1)


def test_brush_drag_interpolates_between_mouse_points(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "interpolate.png"
    _write_png(direct_path, 0)
    project = Project.new("Interpolate")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    project.edit_layers[project.active_edit_layers[source_node]].locked = False
    workspace.select_tool("brush")
    workspace.primary_spin.setValue(1)
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(1, 1)
    workspace._tool_point_clicked(6, 1)
    workspace._finish_paint_stroke()

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 3]) == 255


def test_brush_stroke_does_not_lag_behind_current_point(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "brush-current.png"
    _write_png(direct_path, 0)
    project = Project.new("Brush Current")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    workspace._last_tool_point = (1, 1)
    points = workspace._smoothed_stroke_points((6, 1), 2)

    assert (6, 1) in points
    assert (3, 1) in points


def test_brush_drag_updates_dirty_canvas_regions_immediately(
    workspace_tmp_path: Path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "brush-throttle.png"
    _write_png(direct_path, 0)
    project = Project.new("Brush Throttle")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    updates = 0
    dirty_updates = 0

    def count_update(*_args: object, **_kwargs: object) -> None:
        nonlocal updates
        updates += 1

    def count_dirty_update(*_args: object, **_kwargs: object) -> None:
        nonlocal dirty_updates
        dirty_updates += 1

    monkeypatch.setattr(workspace.canvas, "set_pixels", count_update)
    monkeypatch.setattr(workspace.canvas, "update_tile_regions", count_dirty_update)
    workspace.select_tool("brush")
    workspace._begin_paint_stroke()
    for x in range(1, 8):
        workspace._tool_point_clicked(x, 1)

    assert updates == 0
    assert dirty_updates == 0
    assert not workspace._queued_paint_points
    assert workspace._paint_work_queue.depth() > 0
    workspace._flush_queued_paint_points()
    assert dirty_updates == 0
    workspace._flush_paint_display_regions()
    assert dirty_updates > 0
    workspace._finish_paint_stroke()


def test_brush_drag_records_one_retouch_stroke(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "single-retouch-stroke.png"
    _write_png(direct_path, 0)
    project = Project.new("Single Retouch Stroke")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    workspace.select_tool("brush")
    workspace._begin_paint_stroke()
    for x in range(1, 8):
        workspace._tool_point_clicked(x, 1)
    assert not workspace._queued_paint_points
    assert workspace._paint_work_queue.depth() == 7
    assert not project.retouch_strokes

    workspace._finish_paint_stroke()

    assert len(project.retouch_strokes) == 1
    stroke = next(iter(project.retouch_strokes.values()))
    assert len(stroke.points) == 7


def test_active_paint_motion_updates_visible_pixels_before_commit(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "queued-paint-motion.png"
    _write_png(direct_path, 0)
    project = Project.new("Queued Paint Motion")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.select_tool("brush")
    workspace.secondary_spin.setValue(255)
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(1, 1)
    workspace._tool_point_clicked(6, 1)

    assert not workspace._queued_paint_points
    assert workspace._paint_work_queue.depth() == 2
    workspace._flush_queued_paint_points()
    assert workspace._current_pixels is not None
    assert int(workspace._current_pixels[1, 3]) == 255
    queued_render = render_project_image(project, source_node)
    assert queued_render is not None
    assert int(queued_render[1, 3]) == 0

    workspace._finish_paint_stroke()

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 3]) == 255


def test_paint_motion_does_not_use_regular_queue(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "bounded-paint-queue.png"
    _write_png(direct_path, 0)
    project = Project.new("Bounded Paint Queue")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()
    workspace._paint_flush_budget_points = 4

    workspace.select_tool("brush")
    workspace._begin_paint_stroke()
    for x in range(10):
        workspace._tool_point_clicked(x, 1)

    assert not workspace._queued_paint_points
    assert workspace._paint_work_queue.depth() == 10
    workspace._flush_queued_paint_points()
    assert workspace._paint_work_queue.depth() == 6
    workspace._finish_paint_stroke()
    assert not workspace._queued_paint_points
    assert workspace._paint_work_queue.depth() == 0


def test_source_layer_paint_does_not_write_payload_until_save(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "source-buffer-transition.png"
    _write_png(direct_path, 25)
    project = Project.new("Source Buffer Transition")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    layer = project.edit_layers[project.active_edit_layers[source_node]]

    workspace.select_tool("brush")
    workspace._begin_paint_stroke()
    workspace._tool_point_clicked(1, 1)
    workspace._finish_paint_stroke()

    assert layer.content is None
    assert layer.alpha is None
    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[1, 1]) == 255


def test_color_picker_sets_foreground_for_brush(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    path = workspace_tmp_path / "picker.png"
    pixels = np.full((8, 12), 0, dtype=np.uint8)
    pixels[2, 2] = 180
    Image.fromarray(pixels).save(path)
    project = Project.new("Picker")
    asset = import_images(project, [path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None
    project.edit_layers[project.active_edit_layers[source_node]].locked = False

    workspace.select_tool("color_picker")
    workspace._tool_point_clicked(2, 2)
    workspace.select_tool("brush")
    workspace.primary_spin.setValue(1)
    workspace._tool_point_clicked(4, 4)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[4, 4]) == 180


def test_layer_visibility_toggle_uses_metadata_undo_entry(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "toggle.png"
    _write_png(direct_path, 0)
    project = Project.new("Toggle")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    item = workspace.layers_list.currentItem()
    assert item is not None
    workspace.layer_visible_check.setChecked(False)

    assert project.undo_stack[-1]["kind"] == "layer_metadata"
    assert "state" not in project.undo_stack[-1]


def test_checkerboard_is_applied_only_to_transparent_pixels() -> None:
    opaque = np.full((2, 2, 4), 255, dtype=np.uint8)
    transparent = opaque.copy()
    transparent[0, 0, 3] = 0

    opaque_image = ndarray_to_qimage(opaque)
    composited = ndarray_to_qimage(transparent)

    assert opaque_image.pixelColor(0, 0) == QColor(255, 255, 255, 255)
    assert composited.pixelColor(0, 0).alpha() == 255
    assert composited.pixelColor(0, 0) != QColor(255, 255, 255, 255)
    assert composited.pixelColor(1, 1) == QColor(255, 255, 255, 255)


def test_brush_smoothing_uses_curve_points() -> None:
    points = _catmull_rom_points((0, 0), (4, 0), (4, 4), (8, 4), 2)

    assert points
    assert points[-1] == (4, 4)
    assert any(0 < y < 4 for _x, y in points)


def test_pencil_stroke_is_immediate_linear(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "pencil-linear.png"
    _write_png(direct_path, 0)
    project = Project.new("Pencil Linear")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()

    workspace.select_tool("pencil")
    first = workspace._linear_stroke_points((1, 1), 1)
    workspace._last_tool_point = (1, 1)
    second = workspace._linear_stroke_points((6, 1), 1)

    assert first == [(1, 1)]
    assert (6, 1) in second
    assert (3, 1) in second


def test_move_tool_offsets_active_layer_and_undo_restores(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "move.png"
    _write_png(direct_path, 0)
    project = Project.new("Move")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    workspace.add_empty_layer("Dot")
    workspace.select_tool("brush")
    workspace.primary_spin.setValue(1)
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(2, 2)
    layer_id = project.active_edit_layers[source_node]

    workspace.select_tool("move")
    workspace._begin_layer_move(2, 2)
    workspace._finish_layer_move(2, 2, 4, 3)

    assert project.edit_layers[layer_id].offset_x == 2
    assert project.edit_layers[layer_id].offset_y == 1
    moved = render_project_image(project, source_node)
    assert moved is not None
    assert int(moved[3, 4]) == 255

    workspace.undo()
    assert project.edit_layers[layer_id].offset_x == 0
    assert project.edit_layers[layer_id].offset_y == 0


def test_ellipse_selection_constrains_bucket_fill(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "ellipse.png"
    _write_png(direct_path, 10)
    project = Project.new("Ellipse")
    asset = import_images(project, [direct_path])[0]
    workspace = EditWorkspace(project)
    workspace.refresh()
    source_node = project.source_node_id_for_asset(asset.id)
    assert source_node is not None

    project.edit_layers[project.active_edit_layers[source_node]].locked = False
    workspace.select_tool("ellipse_select")
    workspace._tool_selection_completed("ellipse", 0, 0, 6, 6, [])
    workspace.select_tool("bucket_fill")
    workspace.secondary_spin.setValue(255)
    workspace._tool_point_clicked(3, 3)

    rendered = render_project_image(project, source_node)
    assert rendered is not None
    assert int(rendered[3, 3]) == 255
    assert int(rendered[0, 0]) == 10


def test_ellipse_canvas_release_commits_selection_once(workspace_tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    direct_path = workspace_tmp_path / "ellipse-once.png"
    _write_png(direct_path, 10)
    project = Project.new("Ellipse Once")
    import_images(project, [direct_path])
    workspace = EditWorkspace(project)
    workspace.refresh()
    workspace.select_tool("ellipse_select")
    calls: list[tuple[str, tuple[int, int, int, int]]] = []

    def record_commit(
        kind: str,
        rect: tuple[int, int, int, int],
        _polygon: list[tuple[float, float]],
    ) -> None:
        calls.append((kind, rect))

    workspace._commit_selection_shape = record_commit

    workspace._tool_rectangle_selected(0, 0, 6, 6)
    workspace._tool_selection_completed("ellipse", 0, 0, 6, 6, [])

    assert calls == [("ellipse", (0, 0, 6, 6))]


def test_color_saturation_preview_rect_is_capped() -> None:
    QApplication.instance() or QApplication([])
    workspace = EditWorkspace(Project.new("Color Preview"))
    image = np.zeros((2160, 3840, 3), dtype=np.uint8)
    workspace.canvas.set_pixels(image, fit=False)

    rect = workspace._color_saturation_preview_rect(image, max_pixels=1_250_000)

    assert rect is not None
    assert rect[2] * rect[3] <= 1_250_000
    assert rect[2] < image.shape[1]
    assert rect[3] < image.shape[0]
