from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from biopic.imaging.io import import_images
from biopic.imaging.measurement import export_measurements_csv, measurement_rows
from biopic.models.calibration import (
    Calibration,
    MagnificationScale,
    ScalePreset,
    parse_magnification,
)
from biopic.models.measurement import Measurement, MeasurementKind, Point, ScaleBar
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.main_window import MainWindow
from biopic.ui.workspace import MeasureScaleWorkspace


def test_magnification_parsing_accepts_common_forms() -> None:
    assert parse_magnification("10") == 10
    assert parse_magnification("10x") == 10
    assert parse_magnification("10 x") == 10
    assert parse_magnification("10×") == 10
    assert parse_magnification("10×") == 10


def test_magnification_scale_calculations_and_validation() -> None:
    scale = MagnificationScale(
        magnification=parse_magnification("40x"),
        distance_pixels=400,
        known_distance=100,
        unit="um",
    )

    assert scale.pixels_per_unit == 4
    assert scale.unit_per_pixel == 0.25
    assert scale.menu_label() == "40x (Water)"
    with pytest.raises(ValueError):
        MagnificationScale(magnification=10, distance_pixels=0, known_distance=1)


def test_scale_bar_pixel_length_uses_calibration() -> None:
    calibration = Calibration.from_known_distance(200, 50, "um")
    scale_bar = ScaleBar(
        image_node_id="node",
        physical_length=10,
        unit="um",
        calibration=calibration,
    )

    assert scale_bar.pixel_length == 40


def test_measurement_length_area_and_rows() -> None:
    calibration = Calibration.from_known_distance(100, 50, "um")
    line = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(0, 0), Point(3, 4)],
        image_node_id="node",
        calibration=calibration,
        label="Line",
    )
    rectangle = Measurement(
        kind=MeasurementKind.RECTANGLE,
        points=[Point(0, 0), Point(4, 5)],
        image_node_id="node",
        calibration=calibration,
    )

    rows = measurement_rows([line, rectangle])

    assert line.length_pixels() == 5
    assert line.length_physical() == 2.5
    assert rectangle.area_pixels() == 20
    assert rectangle.area_physical() == 5
    assert rows[0]["unit"] == "μm"


def test_measurements_export_to_csv(workspace_tmp_path: Path) -> None:
    calibration = Calibration.from_known_distance(10, 5, "um")
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(0, 0), Point(10, 0)],
        image_node_id="node",
        calibration=calibration,
        label="L1",
    )
    path = workspace_tmp_path / "measurements.csv"

    export_measurements_csv([measurement], path)

    text = path.read_text(encoding="utf-8")
    assert "length_pixels" in text
    assert "L1" in text


def test_scale_presets_measurements_and_scale_bars_round_trip(workspace_tmp_path: Path) -> None:
    project = Project.new("Scale Project")
    calibration = Calibration.from_known_distance(100, 25, "um")
    preset = ScalePreset(
        name="Camera A",
        scales=[
            MagnificationScale(
                magnification=40,
                distance_pixels=100,
                known_distance=25,
                unit="um",
            )
        ],
    )
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(0, 0), Point(100, 0)],
        image_node_id="node",
        calibration=calibration,
    )
    scale_bar = ScaleBar(
        image_node_id="node",
        physical_length=10,
        unit="um",
        calibration=calibration,
    )
    project.calibrations["node"] = calibration
    project.scale_presets[preset.id] = preset
    project.measurements[measurement.id] = measurement
    project.scale_bars[scale_bar.id] = scale_bar
    path = workspace_tmp_path / "scale_project.biopic.json"

    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)

    assert loaded.scale_presets[preset.id].scales[0].pixels_per_unit == 4
    assert loaded.measurements[measurement.id].length_physical() == 25
    assert loaded.scale_bars[scale_bar.id].pixel_length == 40


def test_measure_scale_set_scale_menu_contains_requested_entries() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Scale Menu")
    preset = ScalePreset(
        name="Camera A",
        scales=[
            MagnificationScale(
                magnification=40,
                distance_pixels=100,
                known_distance=25,
                unit="um",
            )
        ],
    )
    project.scale_presets[preset.id] = preset
    workspace = MeasureScaleWorkspace(project)

    workspace._rebuild_scale_menu()
    labels = [action.text() for action in workspace.set_scale_menu.actions()]

    assert "Set Scale" in labels
    assert "Determine Scale from Image" in labels
    assert "Camera A" in labels
    assert "Add Permanent Scale" in labels
    assert not hasattr(workspace, "add_preset_button")


def test_preset_table_has_no_unit_per_pixel_column() -> None:
    QApplication.instance() or QApplication([])
    workspace = MeasureScaleWorkspace(Project.new("Preset Columns"))
    table = QTableWidget(1, 6)
    for column, value in enumerate(["40x", "Water", "400", "100", "um", ""]):
        table.setItem(0, column, QTableWidgetItem(value))

    workspace._update_preset_table_row(table, 0)

    assert table.columnCount() == 6
    assert table.item(0, 5).text() == "4"


def test_preset_table_accepts_manual_pixels_per_unit() -> None:
    QApplication.instance() or QApplication([])
    workspace = MeasureScaleWorkspace(Project.new("Manual Pixels Per Unit"))
    table = QTableWidget(1, 6)
    for column, value in enumerate(["40x", "Water", "400", "100", "um", "8"]):
        table.setItem(0, column, QTableWidgetItem(value))

    scales = workspace._scale_rows_from_table(table)

    assert scales[0].unit == "μm"
    assert scales[0].pixels_per_unit == 8
    assert scales[0].unit_per_pixel == 0.125


def test_preset_table_updates_known_distance_from_magnification_and_pixels_per_unit() -> None:
    QApplication.instance() or QApplication([])
    workspace = MeasureScaleWorkspace(Project.new("Preset Magnification Defaults"))
    table = QTableWidget(1, 6)
    for column, value in enumerate(["40x", "Water", "", "", "um", "8"]):
        table.setItem(0, column, QTableWidgetItem(value))

    workspace._update_preset_table_row(table, 0)

    assert table.item(0, 2).text() == "1600"
    assert table.item(0, 3).text() == "200"
    assert table.item(0, 5).text() == "8"
    assert workspace._preset_known_distance_for_magnification(30) == 300


def test_scale_menu_checks_active_preset_and_magnification() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Active Scale Menu")
    preset = ScalePreset(
        name="Camera A",
        scales=[
            MagnificationScale(
                magnification=40,
                distance_pixels=1600,
                known_distance=200,
                unit="um",
            )
        ],
    )
    project.scale_presets[preset.id] = preset
    workspace = MeasureScaleWorkspace(project)
    node_id = "node"
    project.calibrations[node_id] = preset.scales[0].to_calibration(source=preset.name)
    workspace._current_source_node_id = lambda: node_id  # type: ignore[method-assign]

    workspace._rebuild_scale_menu()
    preset_action = next(
        action for action in workspace.set_scale_menu.actions() if action.text() == "Camera A"
    )
    scale_action = preset_action.menu().actions()[0]

    assert preset_action.isChecked()
    assert scale_action.isChecked()


def test_canvas_draws_scale_bar_overlay() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    scale_bar = ScaleBar(
        image_node_id="node",
        physical_length=10,
        unit="um",
        calibration=Calibration.from_known_distance(100, 50, "um"),
    )

    canvas.set_scale_bars([scale_bar])

    assert canvas._scale_bar_items


def test_scale_bar_default_offset_uses_two_percent_image_margin() -> None:
    QApplication.instance() or QApplication([])
    workspace = MeasureScaleWorkspace(Project.new("Scale Bar Margin"))
    workspace.canvas.set_pixels(np.zeros((100, 200), dtype=np.uint8), fit=False)

    assert workspace._scale_bar_default_offsets() == (4.0, 2.0)


def test_scale_bar_overlay_refresh_uses_current_image_calibration() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Live Scale Bar")
    workspace = MeasureScaleWorkspace(project)
    scale_bar = ScaleBar(
        image_node_id="node",
        physical_length=10,
        unit="um",
        calibration=Calibration.from_known_distance(100, 50, "um"),
    )
    project.scale_bars[scale_bar.id] = scale_bar
    project.calibrations["node"] = Calibration.from_known_distance(200, 50, "um")
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]

    workspace._refresh_scale_bar_overlay()

    assert scale_bar.calibration.pixels_per_unit == 4


def test_adding_scale_bar_replaces_existing_scale_bar_for_image() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Replace Scale Bar")
    workspace = MeasureScaleWorkspace(project)
    project.calibrations["node"] = Calibration.from_known_distance(100, 50, "um")
    old = ScaleBar(
        image_node_id="node",
        physical_length=10,
        unit="um",
        calibration=project.calibrations["node"],
    )
    project.scale_bars[old.id] = old
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]

    dialog = QDialog()
    enabled = QCheckBox()
    enabled.setChecked(True)
    unit = QComboBox()
    unit.addItem("um")
    length = QDoubleSpinBox()
    length.setValue(20)
    width = QDoubleSpinBox()
    width.setValue(4)
    location = QComboBox()
    location.addItem("Lower Right")
    offset_x = QDoubleSpinBox()
    offset_y = QDoubleSpinBox()
    foreground = QPushButton()
    foreground.setProperty("color", "#ffffff")
    background = QPushButton()
    background.setProperty("color", "#00000080")
    display_length = QCheckBox()
    display_length.setChecked(True)
    font_family = QComboBox()
    font_family.addItem("Arial")
    font_size = QDoubleSpinBox()
    font_size.setValue(12)
    bold = QCheckBox()
    italic = QCheckBox()
    opacity = QDoubleSpinBox()
    opacity.setValue(100)
    dialog.setProperty(
        "scale_bar_controls",
        [
            {
                "enabled": enabled,
                "length": length,
                "unit": unit,
                "orientation": "horizontal",
                "width": width,
                "location": location,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "foreground": foreground,
                "background": background,
                "display_length": display_length,
                "font_family": font_family,
                "font_size": font_size,
                "bold": bold,
                "italic": italic,
                "opacity": opacity,
            }
        ],
    )
    dialog.exec = lambda: QDialog.DialogCode.Accepted  # type: ignore[method-assign]
    workspace._scale_bar_dialog = lambda _calibration, _existing=None: dialog  # type: ignore[method-assign]

    workspace.add_scale_bar()

    assert len(project.scale_bars) == 1
    assert next(iter(project.scale_bars.values())).physical_length == 20


def test_main_window_checks_active_workspace_menu_action() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Active Workspace"))

    window._select_workspace(4)

    assert window._workspace_actions[4].isChecked()
    assert not window._workspace_actions[3].isChecked()


def test_annotate_workspace_shows_measure_scale_bar_for_selected_image(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "annotate-scale.png"
    Image.fromarray(np.zeros((40, 60), dtype=np.uint8)).save(image_path)
    project = Project.new("Annotate Scale Sync")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    calibration = Calibration.from_known_distance(100, 50, "um")
    scale_bar = ScaleBar(
        image_node_id=node_id,
        physical_length=10,
        unit="um",
        calibration=calibration,
    )
    project.calibrations[node_id] = calibration
    project.scale_bars[scale_bar.id] = scale_bar
    window = MainWindow(project)
    window.measure_workspace.refresh()
    window.measure_workspace.select_asset_id(asset.id)

    window._select_workspace(5)

    assert window.annotation_workspace.current_asset_id() == asset.id
    assert window.annotation_workspace.canvas._scale_bar_items


def test_annotation_workspace_exposes_image_list(workspace_tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    paths = []
    for index in range(2):
        path = workspace_tmp_path / f"annotation-image-{index}.png"
        Image.fromarray(np.full((12, 16), index * 80, dtype=np.uint8)).save(path)
        paths.append(path)
    project = Project.new("Annotation Images")
    assets = import_images(project, paths)
    window = MainWindow(project)

    window._select_workspace(6)
    window.annotation_workspace.asset_list.setCurrentRow(1)

    assert window.annotation_workspace.asset_list.count() == 2
    assert window.annotation_workspace.current_asset_id() == assets[1].id


def test_measure_refresh_reuses_render_after_measurement_only_change(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "measure-cache.png"
    Image.fromarray(np.zeros((24, 32), dtype=np.uint8)).save(image_path)
    project = Project.new("Measure Cache")
    asset = import_images(project, [image_path])[0]
    workspace = MeasureScaleWorkspace(project)
    workspace.refresh()

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("measurement-only refresh must reuse cached rendered image")

    monkeypatch.setattr("biopic.ui.workspaces.measure_scale.render_project_image", fail_render)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.measurements["m"] = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(0, 0), Point(1, 1)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(1, 1, "px"),
    )
    project.touch()

    workspace.refresh()
