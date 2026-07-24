from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication

from biopic.imaging.io import import_stack
from biopic.imaging.project_render import editable_assets, render_project_image
from biopic.imaging.stacking import FocusStackParameters, FocusStackResult
from biopic.imaging.stacking.alignment import AlignmentTransform
from biopic.models.annotations import AnnotationKind, AnnotationObject
from biopic.models.calibration import Calibration
from biopic.models.editing import AdjustmentLayer, RetouchStroke
from biopic.models.figure_board import FigureBoard, PageFormat, PageUnit, grid_panels
from biopic.models.image_asset import ImageAssetKind
from biopic.models.image_stack import StackKind
from biopic.models.measurement import ScaleBar
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.pipeline.node import ProcessingNode
from biopic.ui.workspace import FigureBoardWorkspace, StackWorkspace


def _write_png(path: Path, value: int) -> None:
    Image.fromarray(np.full((8, 12), value, dtype=np.uint8)).save(path)


def _ensure_qapp() -> None:
    QApplication.instance() or QApplication([])


def _register_stack_result(project: Project, stack_id: str, workspace_tmp_path: Path) -> str:
    _ensure_qapp()
    workspace = StackWorkspace(project)
    workspace._current_stack_id = stack_id
    source_node_ids = tuple(
        node_id
        for asset_id in project.stacks[stack_id].asset_ids
        if (node_id := project.source_node_id_for_asset(asset_id)) is not None
    )
    node = ProcessingNode(operation="focus_stack", inputs=source_node_ids)
    project.graph.add_node(node)
    result = FocusStackResult(
        image=np.full((8, 12), 128, dtype=np.uint8),
        depth_map=np.zeros((8, 12), dtype=np.uint16),
        focus_map=np.zeros((3, 8, 12), dtype=np.float32),
        weights=np.zeros((3, 8, 12), dtype=np.float32),
        transforms=[AlignmentTransform() for _asset_id in project.stacks[stack_id].asset_ids],
        parameters=FocusStackParameters(),
    )
    old_cwd = Path.cwd()
    try:
        import os

        os.chdir(workspace_tmp_path)
        workspace._register_stack_result_asset(result, node)
    finally:
        os.chdir(old_cwd)
    stack_result = next(
        asset for asset in project.assets.values() if asset.kind is ImageAssetKind.STACK_RESULT
    )
    source_node = project.source_node_id_for_asset(stack_result.id)
    assert source_node is not None
    return source_node


def test_final_stack_adjustment_figure_pipeline_round_trip(workspace_tmp_path: Path) -> None:
    stack_paths = [workspace_tmp_path / f"z{index}.png" for index in range(3)]
    for index, path in enumerate(stack_paths):
        _write_png(path, 40 + index * 20)

    project = Project.new("Final")
    stack = import_stack(project, stack_paths, StackKind.FOCAL)
    stack_result_node = _register_stack_result(project, stack.id, workspace_tmp_path)

    assert all(asset.kind is not ImageAssetKind.STACK_SOURCE for asset in editable_assets(project))
    assert any(asset.kind is ImageAssetKind.STACK_RESULT for asset in editable_assets(project))

    adjustment = AdjustmentLayer(
        name="White Balance",
        image_node_id=stack_result_node,
        operation="white_balance",
        parameters={"red": 1.1, "green": 1.0, "blue": 0.9},
    )
    project.add_adjustment_layer(adjustment)
    rendered = render_project_image(project, stack_result_node)
    assert rendered is not None
    assert rendered.shape == (8, 12)

    calibration = Calibration.from_known_distance(100.0, 10.0, "um")
    project.calibrations[stack_result_node] = calibration
    project.scale_bars["scale"] = ScaleBar(
        image_node_id=stack_result_node,
        physical_length=10.0,
        unit="um",
        calibration=calibration,
    )
    project.annotations["ann"] = AnnotationObject(
        image_node_id=stack_result_node,
        kind=AnnotationKind.TEXT,
        points=[(0.5, 0.5)],
        text="MX",
    )
    board = FigureBoard(
        name="Board",
        page=PageFormat("small", 100, 80, PageUnit.PIXEL, 72),
        panels=grid_panels(1),
    )
    board.panels[0].source_node_id = stack_result_node
    project.figure_boards[board.id] = board
    figure_node = ProcessingNode(
        operation="figure_board",
        inputs=(stack_result_node,),
        parameters={"board_id": board.id},
    )
    project.graph.add_node(figure_node)

    stale = project.update_adjustment_layer(
        adjustment.id, {"red": 1.2, "green": 1.0, "blue": 0.85}
    )
    assert figure_node.id in stale

    stroke = RetouchStroke(
        image_node_id=stack_result_node,
        tool="heal",
        points=[(4.0, 4.0)],
        radius=3.0,
    )
    project.retouch_strokes[stroke.id] = stroke
    path = workspace_tmp_path / "final.biopic.json"
    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)

    assert loaded.adjustment_layers[adjustment.id].operation == "white_balance"
    assert loaded.retouch_strokes[stroke.id].tool == "heal"
    assert loaded.figure_boards[board.id].panels[0].source_node_id == stack_result_node


def test_figure_board_workspace_ignores_stack_source_frames(workspace_tmp_path: Path) -> None:
    _ensure_qapp()
    stack_paths = [workspace_tmp_path / f"z{index}.png" for index in range(3)]
    for index, path in enumerate(stack_paths):
        _write_png(path, 80 + index)
    project = Project.new("Figure Filter")
    import_stack(project, stack_paths, StackKind.FOCAL)
    workspace = FigureBoardWorkspace(project)

    workspace.create_board()

    board = next(iter(project.figure_boards.values()))
    assert all(panel.source_node_id is None for panel in board.panels)
