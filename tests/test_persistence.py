from pathlib import Path

import numpy as np
import tifffile

from biopic.models.calibration import Calibration
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import ScaleBar
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.pipeline.node import ProcessingNode


def test_project_save_load_round_trip(workspace_tmp_path: Path) -> None:
    project = Project.new("Round Trip")
    asset = ImageAsset(path="sample.tif", width=32, height=24, dtype="uint16")
    project.add_asset(asset)
    node = ProcessingNode(operation="source", parameters={"asset_id": asset.id})
    project.graph.add_node(node)
    project.calibrations[node.id] = Calibration.from_known_distance(100, 50, "um")

    path = workspace_tmp_path / "project.biopic.json"
    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)

    assert loaded.name == "Round Trip"
    assert loaded.assets[asset.id].dtype == "uint16"
    assert loaded.graph.nodes[node.id].parameters["asset_id"] == asset.id
    assert loaded.calibrations[node.id].pixels_per_unit == 2


def test_project_save_creates_project_folder_and_exports_outputs(workspace_tmp_path: Path) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((12, 16), 1000, dtype=np.uint16))
    project = Project.new("Archive")
    asset = ImageAsset(
        path=str(source_path),
        width=16,
        height=12,
        dtype="uint16",
        display_name="source.tif",
        metadata={"camera": "test"},
    )
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    calibration = Calibration.from_known_distance(10, 5, "um")
    project.scale_bars["bar"] = ScaleBar(
        image_node_id=node_id,
        physical_length=2,
        unit="um",
        calibration=calibration,
    )

    path = workspace_tmp_path / "archive.biopic.json"
    ProjectStore().save(project, path)
    loaded = ProjectStore().load(path)
    project_dir = workspace_tmp_path / "archive"

    assert project_dir.is_dir()
    assert list((project_dir / "unedited").glob("*__source.tif"))
    assert list((project_dir / "unedited").glob("*__metadata.json"))
    assert list((project_dir / "edited").glob("*__edited.tif"))
    assert project.assets[asset.id].path == str(source_path)
    assert Path(loaded.assets[asset.id].path).exists()


def test_project_save_skips_unchanged_archive_renders(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((12, 16), 1000, dtype=np.uint16))
    project = Project.new("Incremental Archive")
    asset = ImageAsset(
        path=str(source_path),
        width=16,
        height=12,
        dtype="uint16",
        display_name="source.tif",
    )
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    calibration = Calibration.from_known_distance(10, 5, "um")
    project.scale_bars["bar"] = ScaleBar(
        image_node_id=node_id,
        physical_length=2,
        unit="um",
        calibration=calibration,
    )
    path = workspace_tmp_path / "incremental.biopic.json"
    store = ProjectStore()

    store.save(project, path)

    def fail_render(*_args, **_kwargs):
        raise AssertionError("unchanged save should not render archive outputs")

    monkeypatch.setattr("biopic.persistence.project_archive.render_project_image", fail_render)
    monkeypatch.setattr("biopic.persistence.project_archive.export_project_figure_board", fail_render)

    store.save(project, path)
