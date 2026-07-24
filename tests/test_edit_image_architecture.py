from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from biopic.imaging.io import import_images, import_stack
from biopic.imaging.layer_buffers import layer_content_buffer
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
from biopic.ui.image_canvas import ImageCanvas, _checkerboard_transparent_pixels, ndarray_to_qimage
from biopic.ui.workspace import (
    _GIMP_TOOLBOX_TOOLS,
    EditWorkspace,
    StackWorkspace,
    _catmull_rom_points,
)


def _write_png(path: Path, value: int) -> None:
    Image.fromarray(np.full((8, 12), value, dtype=np.uint8)).save(path)


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
    assert full_display_updates == 1
    assert dirty_tile_updates == 1


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


def test_canvas_tiles_use_global_display_range_for_uint16() -> None:
    full_range = (0.0, 1000.0)
    uniform_dirty_tile = np.full((16, 16), 1000, dtype=np.uint16)

    image = ndarray_to_qimage(uniform_dirty_tile, full_range)

    assert image.pixelColor(0, 0).value() == 255


def test_canvas_paint_preview_does_not_grow_without_bound() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((32, 256), dtype=np.uint8), fit=False)

    for x in range(180):
        canvas.extend_paint_preview([(x, 12)], 2, QColor(255, 255, 255))

    assert len(canvas._paint_preview_segments) <= 32
    canvas.clear_paint_preview()
    assert not canvas._paint_preview_segments


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

    assert np.array_equal(_checkerboard_transparent_pixels(opaque), opaque)
    composited = _checkerboard_transparent_pixels(transparent)

    assert composited[0, 0, 3] == 255
    assert not np.array_equal(composited[0, 0, :3], transparent[0, 0, :3])
    assert np.array_equal(composited[1, 1], transparent[1, 1])


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
