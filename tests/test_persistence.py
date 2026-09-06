import json
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtWidgets import QTabWidget

from biopic.models.annotations import AnnotationKind, AnnotationObject
from biopic.models.calibration import Calibration
from biopic.models.editing import EditLayer, LayerContentKind
from biopic.models.figure_board import (
    FigureBoard,
    FigureCaption,
    FigurePanel,
    PageFormat,
    PageUnit,
)
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.measurement import ScaleBar
from biopic.models.project import Project
from biopic.persistence.project_archive import (
    SAVE_STAGE_DEFINITIONS,
    ProjectSaveOptions,
    SavePreset,
    SaveStageConfig,
    resolve_filename_template,
    validate_filename_template,
)
from biopic.persistence.project_store import ProjectStore
from biopic.pipeline.node import ProcessingNode
from biopic.ui.main_window_save_options import ProjectSaveOptionsDialog


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


def test_project_save_options_standard_defaults_match_workflow() -> None:
    options = ProjectSaveOptions().normalized()
    preset = options.active_preset
    enabled = {key for key, config in preset.stages.items() if config.enabled}

    assert enabled == {
        "edited_images",
        "annotated_images",
        "figure_board",
    }
    assert {definition.key: definition.folder for definition in SAVE_STAGE_DEFINITIONS}[
        "original_stack_images"
    ] == "original_stack_images"


def unedited_image_save_options() -> ProjectSaveOptions:
    return ProjectSaveOptions(
        active_preset_name="Copy Unedited",
        presets=(
            SavePreset.standard(),
            SavePreset(
                name="Copy Unedited",
                stages={
                    "unedited_images": SaveStageConfig(
                        True,
                        ("tiff", "none", "none"),
                        "{original_name}_unedited",
                    ),
                    "edited_images": SaveStageConfig(False, ("none", "none", "none")),
                    "annotated_images": SaveStageConfig(False, ("none", "none", "none")),
                    "figure_board": SaveStageConfig(False, ("none", "none", "none")),
                },
            ),
        ),
    )


def test_legacy_standard_save_options_disable_unedited_stage() -> None:
    restored = ProjectSaveOptions.from_dict(
        {
            "schema_version": 2,
            "active_preset_name": "Standard",
            "presets": [
                SavePreset(
                    name="Standard",
                    stages={
                        "unedited_images": SaveStageConfig(True, ("tiff", "none", "none"))
                    },
                ).to_dict()
            ],
        }
    )

    assert restored.active_preset.stages["unedited_images"].enabled is False


def test_standard_project_save_does_not_export_unchanged_unedited_images(
    workspace_tmp_path: Path,
) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("No Raw Copies")
    asset = ImageAsset(path=str(source_path), width=8, height=8, dtype="uint16")
    project.add_asset(asset)

    ProjectStore().save(project, workspace_tmp_path / "no-raw-copies.biopic.json")

    assert not list((workspace_tmp_path / "no-raw-copies" / "unedited_images").glob("*"))


def test_default_source_edit_layer_does_not_export_edited_image(
    workspace_tmp_path: Path,
) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Default Layer Only")
    asset = ImageAsset(path=str(source_path), width=8, height=8, dtype="uint16")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    layer = EditLayer(
        name="Background",
        source_node_id=node_id,
        content_kind=LayerContentKind.SOURCE,
    )
    project.edit_layers[layer.id] = layer
    project.active_edit_layers[node_id] = layer.id

    ProjectStore().save(project, workspace_tmp_path / "default-layer-only.biopic.json")

    assert not list((workspace_tmp_path / "default-layer-only" / "edited_images").glob("*"))


def test_archived_source_path_does_not_chain_stage_suffixes(
    workspace_tmp_path: Path,
) -> None:
    project_dir = workspace_tmp_path / "chained-names"
    unedited_dir = project_dir / "unedited_images"
    unedited_dir.mkdir(parents=True)
    archived_source = unedited_dir / "source_unedited.tif"
    tifffile.imwrite(archived_source, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Chained Names")
    asset = ImageAsset(
        path=str(archived_source),
        width=8,
        height=8,
        dtype="uint16",
        display_name="source.tif",
    )
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.annotations["label"] = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.2, 0.2)],
        text="A",
    )
    annotated_dir = project_dir / "annotated_images"
    annotated_dir.mkdir(parents=True)
    tifffile.imwrite(
        annotated_dir / "source_unedited_annotated.tif",
        np.full((8, 8), 50, dtype=np.uint16),
    )
    tifffile.imwrite(
        annotated_dir / "source_unedited_unedited_annotated.tif",
        np.full((8, 8), 50, dtype=np.uint16),
    )

    ProjectStore().save(project, workspace_tmp_path / "chained-names.biopic.json")

    outputs = sorted(path.name for path in annotated_dir.glob("*.tif"))
    assert outputs == ["source_annotated.tif"]


def test_reopened_project_save_does_not_rewrite_unchanged_annotated_output(
    workspace_tmp_path: Path,
) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Stable Annotated Save")
    asset = ImageAsset(
        path=str(source_path),
        width=8,
        height=8,
        dtype="uint16",
        display_name="source.tif",
        metadata={"species": "Lecane"},
    )
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.annotations["label"] = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.2, 0.2)],
        text="A",
    )
    path = workspace_tmp_path / "stable-annotated-save.biopic.json"
    store = ProjectStore()

    store.save(project, path)
    annotated_path = (
        workspace_tmp_path
        / "stable-annotated-save"
        / "annotated_images"
        / "source_annotated.tif"
    )
    first_stat = annotated_path.stat()
    loaded = store.load(path)
    store.save(loaded, path)

    assert annotated_path.stat().st_mtime_ns == first_stat.st_mtime_ns
    assert annotated_path.stat().st_size == first_stat.st_size


def test_figure_board_only_change_does_not_rewrite_image_stage_outputs(
    workspace_tmp_path: Path,
) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Board Only Dirty")
    asset = ImageAsset(
        path=str(source_path),
        width=8,
        height=8,
        dtype="uint16",
        display_name="source.tif",
    )
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.annotations["label"] = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.2, 0.2)],
        text="A",
    )
    path = workspace_tmp_path / "board-only-dirty.biopic.json"
    store = ProjectStore()
    store.save(project, path)
    annotated_path = (
        workspace_tmp_path / "board-only-dirty" / "annotated_images" / "source_annotated.tif"
    )
    first_stat = annotated_path.stat()

    project.figure_boards["board"] = FigureBoard(
        "Board",
        PageFormat("px", 80, 60, PageUnit.PIXEL),
        panels=[FigurePanel(source_node_id=node_id, label="A")],
    )
    store.save(project, path)

    assert annotated_path.stat().st_mtime_ns == first_stat.st_mtime_ns
    assert annotated_path.stat().st_size == first_stat.st_size


def test_figure_board_caption_sidecars_are_save_option_controlled(
    workspace_tmp_path: Path,
) -> None:
    project = Project.new("Caption Sidecars")
    board = FigureBoard(
        "Board",
        PageFormat("px", 80, 60, PageUnit.PIXEL),
        caption=FigureCaption("Auto caption", "", False, False),
    )
    project.figure_boards[board.id] = board
    path = workspace_tmp_path / "caption-sidecars.biopic.json"

    ProjectStore().save(project, path)
    figure_path = (
        workspace_tmp_path
        / "caption-sidecars"
        / "figure_boards"
        / "Caption_Sidecars_figure_board.tif"
    )
    assert figure_path.exists()
    assert not figure_path.with_suffix(".caption.txt").exists()
    assert not figure_path.with_suffix(".caption.tex").exists()

    options = ProjectSaveOptions(
        active_preset_name="Figure captions",
        presets=(
            SavePreset.standard(),
            SavePreset(
                name="Figure captions",
                stages={
                    "figure_board": SaveStageConfig(
                        True,
                        ("tiff", "none", "none"),
                        "{project_name}_figure_board",
                        True,
                        True,
                    ),
                },
            ),
        ),
    )
    ProjectStore().save(project, path, save_options=options)

    assert figure_path.with_suffix(".caption.txt").read_text(encoding="utf-8").strip() == (
        "Auto caption"
    )
    assert "\\caption{Auto caption}" in figure_path.with_suffix(".caption.tex").read_text(
        encoding="utf-8"
    )


def test_project_save_options_round_trips_custom_preset_and_deduplicates_formats() -> None:
    preset = SavePreset(
        name="Lab Export",
        stages={
            "original_images": SaveStageConfig(
                True,
                ("preserve_original", "tiff", "tiff"),
            )
        },
    )
    options = ProjectSaveOptions(
        active_preset_name="Lab Export",
        presets=(SavePreset.standard(), preset),
    )
    restored = ProjectSaveOptions.from_dict(options.to_dict())
    stage = restored.active_preset.stages["original_images"]

    assert restored.active_preset.name == "Lab Export"
    assert stage.enabled
    assert stage.unique_formats(SAVE_STAGE_DEFINITIONS[0]) == ("preserve_original", "tiff")
    assert restored.active_preset.stages["edited_images"].filename_template == (
        "{original_name}_edited"
    )


def test_filename_template_resolver_sanitizes_and_reports_unknown_fields() -> None:
    resolved = resolve_filename_template(
        "{species}_{specimen_id}_annotated",
        {"species": "Lecane lunaris", "specimen_id": "Lake/01"},
        {},
    )

    assert resolved.stem == "Lecane_lunaris_Lake_01_annotated"
    assert resolve_filename_template("../../test", {}, {}).stem == "test"
    assert resolve_filename_template("{species}_{missing}", {"species": "Lecane"}, {}).stem == (
        "Lecane_unknown"
    )
    assert validate_filename_template("{speces}") == ("Unknown metadata field: speces",)


def test_save_options_dialog_inserts_metadata_token_at_cursor(qtbot) -> None:
    dialog = ProjectSaveOptionsDialog(ProjectSaveOptions())
    qtbot.addWidget(dialog)
    editor = dialog._template_edits["annotated_images"]
    editor.setText("{species}_annotated")
    editor.setCursorPosition(len("{species}_"))
    dialog._set_active_template(editor)

    item = next(
        dialog.metadata_tokens.item(row)
        for row in range(dialog.metadata_tokens.count())
        if dialog.metadata_tokens.item(row).data(0x0100) == "specimen_id"
    )
    dialog._insert_metadata_token(item)

    assert editor.text() == "{species}_{specimen_id}annotated"


def test_save_options_dialog_uses_tabbed_sections_and_figure_sidecar_options(qtbot) -> None:
    dialog = ProjectSaveOptionsDialog(ProjectSaveOptions())
    qtbot.addWidget(dialog)

    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Saving Steps",
        "File Types",
        "File Names",
    ]
    assert dialog._figure_board_text_check is not None
    assert dialog._figure_board_latex_check is not None
    figure_config = dialog.options().active_preset.stages["figure_board"]
    assert figure_config.save_caption_text is False
    assert figure_config.save_caption_latex is False

    dialog._figure_board_text_check.setChecked(True)
    dialog._figure_board_latex_check.setChecked(True)
    figure_config = dialog.options().active_preset.stages["figure_board"]
    assert figure_config.save_caption_text is True
    assert figure_config.save_caption_latex is True


def test_raw_source_stage_preserves_original_without_fake_raster_output(
    workspace_tmp_path: Path,
) -> None:
    raw_path = workspace_tmp_path / "camera_raw.cr2"
    raw_path.write_bytes(b"not a decoded raster")
    project = Project.new("Raw Preserve")
    asset = ImageAsset(path=str(raw_path), width=8, height=8, dtype="raw")
    project.add_asset(asset)
    options = ProjectSaveOptions(
        active_preset_name="Raw",
        presets=(
            SavePreset.standard(),
            SavePreset(
                name="Raw",
                stages={
                    "original_images": SaveStageConfig(
                        True,
                        ("preserve_original", "tiff", "none"),
                    ),
                    "unedited_images": SaveStageConfig(False, ("none", "none", "none")),
                    "edited_images": SaveStageConfig(False, ("none", "none", "none")),
                    "annotated_images": SaveStageConfig(False, ("none", "none", "none")),
                    "figure_board": SaveStageConfig(False, ("none", "none", "none")),
                },
            ),
        ),
    )

    ProjectStore().save(project, workspace_tmp_path / "raw.biopic.json", save_options=options)

    project_dir = workspace_tmp_path / "raw"
    assert list((project_dir / "original_images").glob("camera_raw.cr2"))
    assert not list((project_dir / "original_images").glob("camera_raw.tif"))


def test_non_unique_filename_template_is_made_collision_safe(workspace_tmp_path: Path) -> None:
    first_path = workspace_tmp_path / "first.tif"
    second_path = workspace_tmp_path / "second.tif"
    tifffile.imwrite(first_path, np.full((8, 8), 100, dtype=np.uint16))
    tifffile.imwrite(second_path, np.full((8, 8), 200, dtype=np.uint16))
    project = Project.new("Collision Safe")
    project.add_asset(ImageAsset(path=str(first_path), width=8, height=8, dtype="uint16"))
    project.add_asset(ImageAsset(path=str(second_path), width=8, height=8, dtype="uint16"))
    options = ProjectSaveOptions(
        active_preset_name="Collision",
        presets=(
            SavePreset.standard(),
            SavePreset(
                name="Collision",
                stages={
                    "unedited_images": SaveStageConfig(True, ("tiff", "none", "none"), "same"),
                    "edited_images": SaveStageConfig(False, ("none", "none", "none")),
                    "annotated_images": SaveStageConfig(False, ("none", "none", "none")),
                    "figure_board": SaveStageConfig(False, ("none", "none", "none")),
                },
            ),
        ),
    )

    ProjectStore().save(
        project,
        workspace_tmp_path / "collision.biopic.json",
        save_options=options,
    )

    outputs = sorted((workspace_tmp_path / "collision" / "unedited_images").glob("same*.tif"))
    assert [path.name for path in outputs] == ["same.tif", "same_002.tif"]


def test_project_save_does_not_persist_undo_redo_stacks(workspace_tmp_path: Path) -> None:
    project = Project.new("Undo Hygiene")
    project.undo_stack.append({"description": "large edit", "state": {"payload": "before"}})
    project.redo_stack.append({"description": "large edit", "state": {"payload": "after"}})

    path = workspace_tmp_path / "undo-hygiene.biopic.json"
    ProjectStore().save(project, path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    loaded = ProjectStore().load(path)

    assert saved["undo_stack"] == []
    assert saved["redo_stack"] == []
    assert loaded.undo_stack == []
    assert loaded.redo_stack == []
    assert project.undo_stack
    assert project.redo_stack


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
    ProjectStore().save(project, path, save_options=unedited_image_save_options())
    loaded = ProjectStore().load(path)
    project_dir = workspace_tmp_path / "archive"

    assert project_dir.is_dir()
    assert list((project_dir / "unedited_images").glob("source_unedited.tif"))
    assert not list((project_dir / "unedited_images").glob("*__metadata.json"))
    assert not list(project_dir.glob("**/*.signature.json"))
    assert list((project_dir / ".biopic_cache" / "signatures").glob("*.json"))
    assert not list((project_dir / "edited_images").glob("source_edited.tif"))
    archived_source = next((project_dir / "unedited_images").glob("source_unedited.tif"))
    with tifffile.TiffFile(archived_source) as tif:
        assert "camera" in tif.pages[0].description
    assert project.assets[asset.id].path == str(source_path)
    assert Path(loaded.assets[asset.id].path).exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved_asset = saved["assets"][0]
    assert saved["storage"]["mode"] == "self_contained_folder"
    assert not Path(saved_asset["path"]).is_absolute()
    assert Path(loaded.assets[asset.id].path).is_absolute()


def test_project_load_uses_archived_image_when_original_is_missing(
    workspace_tmp_path: Path,
) -> None:
    source_path = workspace_tmp_path / "external_source.tif"
    tifffile.imwrite(source_path, np.full((8, 10), 600, dtype=np.uint16))
    project = Project.new("Portable")
    asset = ImageAsset(path=str(source_path), width=10, height=8, dtype="uint16")
    project.add_asset(asset)
    path = workspace_tmp_path / "portable.biopic.json"

    store = ProjectStore()
    store.save(project, path, save_options=unedited_image_save_options())
    source_path.unlink()
    loaded = store.load(path)

    loaded_asset_path = Path(loaded.assets[asset.id].path)
    assert loaded_asset_path.exists()
    assert loaded_asset_path.parent == workspace_tmp_path / "portable" / "unedited_images"


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

    store.save(project, path, save_options=unedited_image_save_options())

    def fail_render(*_args, **_kwargs):
        raise AssertionError("unchanged save should not render archive outputs")

    monkeypatch.setattr("biopic.persistence.project_archive.render_project_image", fail_render)
    monkeypatch.setattr(
        "biopic.persistence.project_archive.export_project_figure_board", fail_render
    )

    store.save(project, path, save_options=unedited_image_save_options())


def test_reopened_clean_project_save_skips_archive_checks(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Clean Reopened")
    asset = ImageAsset(path=str(source_path), width=8, height=8, dtype="uint16")
    project.add_asset(asset)
    path = workspace_tmp_path / "clean-reopened.biopic.json"
    store = ProjectStore()
    store.save(project, path, save_options=unedited_image_save_options())
    loaded = store.load(path)
    progress_calls: list[tuple[int, int, str, str]] = []

    def fail_archive(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise AssertionError("clean Ctrl-S must not check archive outputs")

    monkeypatch.setattr("biopic.persistence.project_store.export_project_archive", fail_archive)

    store.save(
        loaded,
        path,
        save_options=unedited_image_save_options(),
        progress=lambda done, total, current_path, action: progress_calls.append(
            (done, total, current_path.name, action)
        ),
    )

    assert loaded.archive_is_dirty() is False
    assert progress_calls == [(1, 1, "clean-reopened.biopic.json", "Saving project manifest")]
    loaded.touch()
    assert loaded.archive_is_dirty() is True


def test_project_save_skips_unchanged_unedited_sources(workspace_tmp_path: Path) -> None:
    first_path = workspace_tmp_path / "first.tif"
    second_path = workspace_tmp_path / "second.tif"
    third_path = workspace_tmp_path / "third.tif"
    tifffile.imwrite(first_path, np.full((8, 8), 100, dtype=np.uint16))
    tifffile.imwrite(second_path, np.full((8, 8), 200, dtype=np.uint16))
    tifffile.imwrite(third_path, np.full((8, 8), 300, dtype=np.uint16))
    project = Project.new("Incremental Sources")
    first = ImageAsset(path=str(first_path), width=8, height=8, dtype="uint16")
    second = ImageAsset(path=str(second_path), width=8, height=8, dtype="uint16")
    project.add_asset(first)
    project.add_asset(second)
    path = workspace_tmp_path / "incremental-sources.biopic.json"
    store = ProjectStore()

    store.save(project, path, save_options=unedited_image_save_options())
    archived_first = next(
        (workspace_tmp_path / "incremental-sources" / "unedited_images").glob(
            "first_unedited.tif"
        )
    )
    archived_second = next(
        (workspace_tmp_path / "incremental-sources" / "unedited_images").glob(
            "second_unedited.tif"
        )
    )
    first_stat = archived_first.stat()
    second_stat = archived_second.stat()

    third = ImageAsset(path=str(third_path), width=8, height=8, dtype="uint16")
    project.add_asset(third)
    store.save(project, path, save_options=unedited_image_save_options())

    assert archived_first.stat().st_mtime_ns == first_stat.st_mtime_ns
    assert archived_first.stat().st_size == first_stat.st_size
    assert archived_second.stat().st_mtime_ns == second_stat.st_mtime_ns
    assert archived_second.stat().st_size == second_stat.st_size
    assert list((workspace_tmp_path / "incremental-sources" / "unedited_images").glob(
        "third_unedited.tif"
    ))


def test_project_save_removes_legacy_visible_sidecars(workspace_tmp_path: Path) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Legacy Sidecars")
    asset = ImageAsset(path=str(source_path), width=8, height=8, dtype="uint16")
    project.add_asset(asset)
    project_dir = workspace_tmp_path / "legacy-sidecars"
    unedited_dir = project_dir / "unedited"
    edited_dir = project_dir / "edited"
    figure_dir = project_dir / "figure_boards"
    unedited_dir.mkdir(parents=True)
    edited_dir.mkdir()
    figure_dir.mkdir()
    (unedited_dir / "source__metadata.json").write_text("{}", encoding="utf-8")
    (unedited_dir / "source__source.tif.signature.json").write_text("{}", encoding="utf-8")
    (edited_dir / "source__edited.tif.signature.json").write_text("{}", encoding="utf-8")
    (figure_dir / "board.tif.signature.json").write_text("{}", encoding="utf-8")

    ProjectStore().save(project, workspace_tmp_path / "legacy-sidecars.biopic.json")

    assert not list(project_dir.glob("**/*__metadata.json"))
    assert not list(project_dir.glob("**/*.signature.json"))


def test_project_save_reports_progress_for_archived_files(workspace_tmp_path: Path) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Progress")
    asset = ImageAsset(path=str(source_path), width=8, height=8, dtype="uint16")
    project.add_asset(asset)
    path = workspace_tmp_path / "progress.biopic.json"
    progress_calls: list[tuple[int, int, str, str]] = []

    def progress(done: int, total: int, current_path: Path, action: str) -> None:
        progress_calls.append((done, total, current_path.name, action))

    ProjectStore().save(
        project,
        path,
        save_options=unedited_image_save_options(),
        progress=progress,
    )

    assert progress_calls
    assert progress_calls[-1] == (
        progress_calls[-1][1],
        progress_calls[-1][1],
        "progress.biopic.json",
        "Saving project manifest",
    )
    assert any(name.endswith("_unedited.tif") for _done, _total, name, _action in progress_calls)
    assert not any(
        name.endswith("__metadata.json") for _done, _total, name, _action in progress_calls
    )
    assert [done for done, _total, _name, _action in progress_calls] == list(
        range(1, len(progress_calls) + 1)
    )


def test_project_save_does_not_rewrite_own_archived_source_metadata(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    source_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 100, dtype=np.uint16))
    project = Project.new("Archived Source Metadata")
    asset = ImageAsset(path=str(source_path), width=8, height=8, dtype="uint16")
    project.add_asset(asset)
    path = workspace_tmp_path / "archived-source.biopic.json"
    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)
    loaded_asset = loaded.assets[asset.id]
    loaded_asset.metadata["locality"] = "Pond edge"

    def fail_metadata_write(*_args: object, **_kwargs: object) -> bool:
        raise PermissionError("simulated locked archived TIFF")

    monkeypatch.setattr(
        "biopic.persistence.project_archive.write_image_metadata",
        fail_metadata_write,
    )

    store.save(loaded, path)
    reloaded = store.load(path)

    assert reloaded.assets[asset.id].metadata["locality"] == "Pond edge"
    assert not list(
        (workspace_tmp_path / "archived-source" / "unedited_images").glob("*__metadata.json")
    )


def test_project_save_options_can_keep_originals_external(workspace_tmp_path: Path) -> None:
    source_dir = workspace_tmp_path / "source-folder"
    source_dir.mkdir()
    source_path = source_dir / "external.tif"
    tifffile.imwrite(source_path, np.full((8, 8), 500, dtype=np.uint16))
    project = Project.new("External Originals")
    asset = ImageAsset(
        path=str(source_path),
        kind=ImageAssetKind.STACK_SOURCE,
        width=8,
        height=8,
        dtype="uint16",
    )
    project.add_asset(asset)
    save_dir = workspace_tmp_path / "save-folder"
    path = save_dir / "external-originals.biopic.json"

    ProjectStore().save(
        project,
        path,
        save_options=ProjectSaveOptions(
            include_original_images=False,
            include_stack_source_images=False,
        ),
    )

    saved = json.loads(path.read_text(encoding="utf-8"))
    project_dir = save_dir / "external-originals"
    assert not list(project_dir.rglob("*__source.tif"))
    saved_asset_path = Path(saved["assets"][0]["path"])
    resolved_asset_path = (
        saved_asset_path if saved_asset_path.is_absolute() else path.parent / saved_asset_path
    )
    assert resolved_asset_path.resolve() == source_path.resolve()
    assert saved["storage"]["save_options"]["include_original_images"] is False


def test_project_metadata_presets_save_load_round_trip(workspace_tmp_path: Path) -> None:
    project = Project.new("Preset Persistence")
    project.metadata_presets["location"] = [
        {"name": "Pond A", "locality": "North pond", "habitat": "Plankton"}
    ]
    project.metadata_presets["collector"] = [{"name": "Lab", "collector": "Ada"}]
    project.metadata_presets["preparation"] = [{"name": "Live", "preparation": "Live mount"}]
    path = workspace_tmp_path / "presets.biopic.json"

    ProjectStore().save(project, path)
    loaded = ProjectStore().load(path)

    assert loaded.metadata_presets["location"][0]["locality"] == "North pond"
    assert loaded.metadata_presets["collector"][0]["collector"] == "Ada"
    assert loaded.metadata_presets["preparation"][0]["preparation"] == "Live mount"
