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
from biopic.imaging.scale_detection import (
    align_image_to_axes,
    confidence_label,
    detect_scale_stripe_pattern,
    detect_scale_stripe_spacing,
    infer_scale_metadata_from_filename,
    measurement_metrics,
    reference_overlay_lengths,
    robust_rotation_from_segments,
    rotate_image_no_scale,
    snapped_measurement_endpoint,
)
from biopic.models.calibration import (
    Calibration,
    MagnificationScale,
    ScalePreset,
    normalize_unit,
    parse_magnification,
)
from biopic.models.measurement import (
    Measurement,
    MeasurementKind,
    MeasurementLabelAlignment,
    Point,
    ScaleBar,
    rotated_rectangle_points,
    scale_bar_panel_geometry,
)
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
    assert rows[0]["length_unit"] == "µm"
    assert rows[1]["area_unit"] == "µm²"


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
    assert "length,length_unit,area,area_unit" in text
    assert "L1" in text


def test_measurement_unit_conversions_and_area_geometry() -> None:
    calibration = Calibration.from_known_distance(100, 50, "um")
    line = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(0, 0), Point(30, 40)],
        image_node_id="node",
        calibration=calibration,
        display_unit="px",
    )
    rectangle = Measurement(
        kind=MeasurementKind.RECTANGLE,
        points=rotated_rectangle_points(Point(10, 10), 20, 10, 30),
        image_node_id="node",
        calibration=calibration,
        area_display_unit="μm²",
    )
    ellipse = Measurement(
        kind=MeasurementKind.ELLIPSE,
        points=[Point(0, 0), Point(10, 0), Point(0, 5)],
        image_node_id="node",
        calibration=calibration,
        area_display_unit="mm²",
    )
    freehand = Measurement(
        kind=MeasurementKind.POLYGON,
        points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
        image_node_id="node",
        calibration=calibration,
        area_display_unit="px²",
    )

    assert line.length_display("px") == 50
    assert line.length_display("μm") == 25
    assert line.length_display("mm") == 0.025
    assert rectangle.rectangle_side_lengths_pixels() == pytest.approx((20, 10))
    assert rectangle.area_pixels() == pytest.approx(200)
    assert rectangle.area_display("μm²") == pytest.approx(50)
    assert ellipse.ellipse_axes_pixels() == pytest.approx((20, 10))
    assert ellipse.area_pixels() == pytest.approx(np.pi * 50)
    assert ellipse.area_display("mm²") == pytest.approx(np.pi * 50 * 0.25 / 1_000_000)
    assert freehand.area_pixels() == 100
    assert freehand.area_display("px²") == 100


def test_measurement_label_unit_alignment_round_trip() -> None:
    measurement = Measurement(
        kind=MeasurementKind.RECTANGLE,
        points=rotated_rectangle_points(Point(10, 10), 20, 10, 12),
        image_node_id="node",
        calibration=Calibration.from_known_distance(100, 50, "um"),
        label="Cell region",
        display_unit="mm",
        area_display_unit="mm²",
        label_alignment=MeasurementLabelAlignment.ALIGNED,
        rotation=12,
    )

    loaded = Measurement.from_dict(measurement.to_dict())

    assert loaded.label == "Cell region"
    assert loaded.display_unit == "mm"
    assert loaded.area_display_unit == "mm²"
    assert loaded.label_alignment is MeasurementLabelAlignment.ALIGNED
    assert loaded.rotation == 12
    assert loaded.area_pixels() == pytest.approx(measurement.area_pixels())


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
    assert hasattr(workspace, "add_to_preset_button")
    assert not workspace.add_to_preset_button.isVisible()


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


def test_preset_table_rows_are_sorted_by_numeric_magnification() -> None:
    QApplication.instance() or QApplication([])
    workspace = MeasureScaleWorkspace(Project.new("Sorted Presets"))
    table = QTableWidget(3, 7)
    rows = [
        ["40x", "Water", "400", "100", "um", "4", ""],
        ["5 x", "Water", "100", "100", "um", "1", ""],
        ["10", "Water", "200", "100", "um", "2", ""],
    ]
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))

    scales = workspace._scale_rows_from_table(table)

    assert [scale.magnification for scale in scales] == [5, 10, 40]


def test_scale_stripe_detection_and_filename_guess() -> None:
    stripe_profile = ((np.arange(240) // 12) % 2).astype(np.float32)
    pixels = np.tile(stripe_profile, (80, 1))

    spacing, axis, confidence = detect_scale_stripe_spacing(pixels)
    guessed = infer_scale_metadata_from_filename("Zeiss_Axiocam_scale_40x_test.tif")

    assert abs(spacing - 24) <= 1
    assert axis == "vertical stripes"
    assert confidence > 2
    assert guessed["magnification"] == "40x"
    assert "Zeiss" in guessed["camera_or_microscope"]


def test_subpixel_scale_detection_handles_blurred_ticks() -> None:
    pixels = _synthetic_scale_ticks(blur_sigma=1.6)

    detection = detect_scale_stripe_pattern(pixels)

    assert detection.axis == "vertical stripes"
    assert detection.spacing_pixels == pytest.approx(18.5, abs=0.12)
    assert detection.spacing_rms_error < 0.12
    assert detection.inlier_tick_count >= 5
    assert detection.micrometers_per_pixel == pytest.approx(10.0 / detection.spacing_pixels)


def test_subpixel_scale_detection_handles_horizontal_ticks() -> None:
    pixels = _synthetic_scale_ticks(vertical=False, shape=(340, 160))

    detection = detect_scale_stripe_pattern(pixels)

    assert detection.axis == "horizontal stripes"
    assert detection.spacing_pixels == pytest.approx(18.5, abs=0.15)


def test_scale_detection_uses_lattice_with_noise_illumination_missing_and_false_ticks() -> None:
    pixels = _synthetic_scale_ticks(
        noise=8.0,
        uneven=True,
        missing=(3, 7),
        false_stripe=True,
    )

    detection = detect_scale_stripe_pattern(pixels)

    assert detection.axis == "vertical stripes"
    assert detection.spacing_pixels == pytest.approx(18.5, abs=0.18)
    assert detection.inlier_tick_count >= 4
    assert detection.spacing_rms_error < 0.25


def test_scale_detection_tolerates_slight_rotation() -> None:
    pixels = _synthetic_scale_ticks(blur_sigma=1.0)
    rotated = rotate_image_no_scale(pixels, 2.0)

    detection = detect_scale_stripe_pattern(rotated)

    assert detection.axis == "vertical stripes"
    assert detection.spacing_pixels == pytest.approx(18.5, abs=0.25)
    assert detection.inlier_tick_count >= 6


def test_scale_detection_recovers_perpendicular_spacing_for_rotations() -> None:
    for angle in (0.0, 2.0, 5.0, 10.0, -5.0, -10.0):
        pixels = _synthetic_scale_ticks(blur_sigma=1.0)
        rotated = rotate_image_no_scale(pixels, angle)

        detection = detect_scale_stripe_pattern(rotated)

        assert detection.spacing_pixels == pytest.approx(18.5, abs=0.25)
        assert detection.tick_angle_std_degrees < 1.0


def test_rotated_scale_overlay_metadata_uses_normal_direction() -> None:
    pixels = _synthetic_scale_ticks(blur_sigma=1.0)
    rotated = rotate_image_no_scale(pixels, 10.0)

    detection = detect_scale_stripe_pattern(rotated)
    first, second = detection.tick_marks[:2]
    v = max(float(first["top"]), float(second["top"]))
    start = _rotated_mark_point(first, v)
    end = _rotated_mark_point(second, v)
    vector = np.array([end[0] - start[0], end[1] - start[1]])
    normal = np.array([float(first["normal_x"]), float(first["normal_y"])])
    vector /= np.linalg.norm(vector)
    normal /= np.linalg.norm(normal)

    assert abs(float(np.dot(vector, normal))) == pytest.approx(1.0, abs=0.02)


def test_tick_size_classification_uses_visible_tick_length() -> None:
    pixels = _synthetic_scale_ticks(blur_sigma=1.2)

    detection = detect_scale_stripe_pattern(pixels)
    classes = {str(mark["class"]) for mark in detection.tick_marks}

    assert "large" in classes
    assert "small" in classes


def test_scale_measurement_snaps_horizontal_and_vertical() -> None:
    end, snap = snapped_measurement_endpoint((10, 10), (40, 24))
    assert end == (40, 10)
    assert snap == "horizontal"

    end, snap = snapped_measurement_endpoint((10, 10), (22, 45))
    assert end == (10, 45)
    assert snap == "vertical"


def test_scale_measurement_free_angle_and_metrics() -> None:
    end, snap = snapped_measurement_endpoint((0, 0), (3, 4), free_angle=True)
    metrics = measurement_metrics((0, 0), end, unit_per_pixel=0.5)

    assert end == (3, 4)
    assert snap == "free"
    assert metrics["distance_pixels"] == 5
    assert metrics["distance_physical"] == 2.5
    assert round(metrics["angle_degrees"], 3) == 53.13


def test_reference_overlay_lengths_for_10_50_100_units() -> None:
    assert reference_overlay_lengths(8.43) == [(100.0, 843.0), (50.0, 421.5), (10.0, 84.3)]


def test_scale_confidence_label_and_micro_unit_normalization() -> None:
    assert confidence_label(354.12) == "excellent"
    assert confidence_label(7.0) == "weak"
    assert normalize_unit("um") == "μm"
    assert normalize_unit("µm") == "μm"


def test_robust_rotation_uses_long_segments_and_rejects_short_outlier() -> None:
    segments = [
        (0, 0, 100, 5),
        (0, 20, 120, 26),
        (50, 0, 55, 120),
        (70, 0, 76, 130),
        (0, 0, 5, 80),
    ]

    rotation, weight = robust_rotation_from_segments(segments)

    assert 2.0 < rotation < 4.0
    assert weight > 300


def test_crosshair_alignment_rotates_off_center_axes_to_image_edges() -> None:
    cv2 = pytest.importorskip("cv2")
    pixels = np.zeros((420, 520), dtype=np.uint8) + 20
    cv2.line(pixels, (320, 40), (320, 390), 255, 7)
    cv2.line(pixels, (80, 250), (500, 250), 255, 7)
    matrix = cv2.getRotationMatrix2D((260, 210), 7.0, 1.0)
    rotated = cv2.warpAffine(pixels, matrix, (520, 420), borderMode=cv2.BORDER_REPLICATE)

    aligned, correction = align_image_to_axes(rotated)

    assert abs(correction + 7.0) < 3.0
    assert aligned.shape[0] > rotated.shape[0]
    assert aligned.shape[1] > rotated.shape[1]
    border = np.concatenate([aligned[0], aligned[-1], aligned[:, 0], aligned[:, -1]])
    assert np.any(border == 0)


def test_stripe_positions_prefer_dark_tick_centers() -> None:
    from biopic.imaging.scale_detection import detect_scale_stripe_pattern

    pixels = np.full((80, 240), 220, dtype=np.uint8)
    pixels[:, ::12] = 20
    pixels[:, 1::12] = 20

    detection = detect_scale_stripe_pattern(pixels)

    assert detection.stripe_positions
    assert min(abs(position - 0.5) for position in detection.stripe_positions) < 2.0


def test_scale_overlay_uses_tick_class_pairs_and_shorter_tick_top() -> None:
    from biopic.ui.scale_detection_canvas import _best_tick_pair

    marks = [
        {"center": 0.0, "top": 10.0, "height": 300.0, "class": "medium"},
        {"center": 20.0, "top": 180.0, "height": 120.0, "class": "small"},
        {"center": 100.0, "top": 95.0, "height": 210.0, "class": "medium"},
        {"center": 200.0, "top": 12.0, "height": 300.0, "class": "large"},
    ]

    pair_100 = _best_tick_pair(marks, 100.0, 200.0)
    pair_50 = _best_tick_pair(marks, 50.0, 100.0)
    pair_10 = _best_tick_pair(marks, 10.0, 20.0)

    assert pair_100 is not None
    assert pair_100[0]["center"] == 0.0
    assert pair_50 is not None
    assert pair_50[0]["center"] == 0.0
    assert pair_10 is not None
    assert pair_10[0]["center"] == 0.0
    y_for_10 = max(float(pair_10[0]["top"]), float(pair_10[1]["top"])) - 5.0
    assert y_for_10 == 175.0


def test_scale_overlay_counts_tick_intervals_from_left_anchor() -> None:
    from biopic.ui.scale_detection_canvas import _best_tick_pair

    classes = [
        "large",
        "small",
        "small",
        "small",
        "small",
        "medium",
        "small",
        "small",
        "small",
        "small",
        "large",
        "small",
    ]
    marks = [
        {"center": float(index * 20), "top": 20.0, "height": 200.0, "class": class_name}
        for index, class_name in enumerate(classes)
    ]

    pair_100 = _best_tick_pair(marks, 100.0, 200.0)
    pair_50 = _best_tick_pair(marks, 50.0, 100.0)
    pair_10 = _best_tick_pair(marks, 10.0, 20.0)

    assert pair_100 is not None
    assert pair_100[0]["center"] == 0.0
    assert pair_100[1]["center"] == 200.0
    assert pair_50 is not None
    assert pair_50[0]["center"] == 0.0
    assert pair_50[1]["center"] == 100.0
    assert pair_10 is not None
    assert pair_10[0]["center"] == 0.0
    assert pair_10[1]["center"] == 20.0


def test_scale_overlay_prefers_large_anchor_over_earlier_small_tick() -> None:
    from biopic.ui.scale_detection_canvas import _best_tick_pair

    classes = [
        "small",
        "large",
        "small",
        "small",
        "small",
        "small",
        "medium",
        "small",
        "small",
        "small",
        "small",
        "large",
    ]
    marks = [
        {"center": float(index * 20), "top": 20.0, "bottom": 220.0, "height": 200.0, "class": class_name}
        for index, class_name in enumerate(classes)
    ]

    pair_100 = _best_tick_pair(marks, 100.0, 200.0)
    pair_50 = _best_tick_pair(marks, 50.0, 100.0)
    pair_10 = _best_tick_pair(marks, 10.0, 20.0)

    assert pair_100 is not None
    assert pair_100[0]["center"] == 20.0
    assert pair_100[1]["center"] == 220.0
    assert pair_50 is not None
    assert pair_50[0]["center"] == 20.0
    assert pair_50[1]["center"] == 120.0
    assert pair_10 is not None
    assert pair_10[0]["center"] == 20.0
    assert pair_10[1]["center"] == 40.0


def test_scale_overlay_distributes_labels_along_small_tick_height() -> None:
    from biopic.ui.scale_detection_canvas import _reference_y_for_pair

    marks = [
        {"center": 0.0, "top": 0.0, "bottom": 300.0, "height": 300.0, "class": "large"},
        {"center": 20.0, "top": 180.0, "bottom": 300.0, "height": 120.0, "class": "small"},
        {"center": 100.0, "top": 95.0, "bottom": 300.0, "height": 205.0, "class": "medium"},
        {"center": 200.0, "top": 0.0, "bottom": 300.0, "height": 300.0, "class": "large"},
    ]

    y_100 = _reference_y_for_pair(marks[0], marks[3], 100.0, 0, marks)
    y_50 = _reference_y_for_pair(marks[0], marks[2], 50.0, 1, marks)
    y_10 = _reference_y_for_pair(marks[0], marks[1], 10.0, 2, marks)

    assert y_100 < y_50 < y_10
    assert y_10 - y_50 > 30.0
    assert y_100 < 190.0


def test_scale_overlay_y_stays_inside_endpoint_tick_overlap() -> None:
    from biopic.ui.scale_detection_canvas import _reference_y_for_pair

    marks = [
        {"center": 0.0, "top": 0.0, "bottom": 300.0, "height": 300.0, "class": "large"},
        {"center": 20.0, "top": 180.0, "bottom": 300.0, "height": 120.0, "class": "small"},
        {"center": 100.0, "top": 240.0, "bottom": 300.0, "height": 60.0, "class": "medium"},
    ]

    y_50 = _reference_y_for_pair(marks[0], marks[2], 50.0, 1, marks)

    assert 240.0 <= y_50 <= 300.0


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


def test_measurement_controls_are_visible_and_line_drag_creates_measurement() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Measurement Controls")
    workspace = MeasureScaleWorkspace(project)
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    project.calibrations["node"] = Calibration.from_known_distance(100, 50, "um")
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.measurement_type_combo.setCurrentText("Line")
    workspace.length_unit_combo.setCurrentText("μm")
    workspace.measurement_font_size.setValue(18.0)
    workspace.measurement_bold.setChecked(True)

    assert workspace.measurement_type_combo.count() == 2
    assert workspace.area_geometry_combo.count() == 3
    assert workspace.length_unit_combo.count() == 3
    assert workspace.area_unit_combo.count() == 3

    workspace.add_line_measurement()
    assert workspace.canvas._tool_mode == "measure_line"
    workspace._measurement_line_selected(0, 0, 30, 40)

    measurement = next(iter(project.measurements.values()))
    assert measurement.length_display("μm") == 25
    assert measurement.display_text().endswith("\u00b5m")
    assert measurement.value_text() == "25.00 µm"
    assert measurement.font_size == 18
    assert measurement.bold is True


def test_measurement_controls_switch_by_mode_and_shortcuts() -> None:
    QApplication.instance() or QApplication([])
    workspace = MeasureScaleWorkspace(Project.new("Measurement Shortcuts"))
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]

    workspace.select_measurement_tool("line")
    assert workspace.measurement_type_combo.currentText() == "Line"
    assert workspace.canvas._tool_mode == "measure_line"
    assert workspace.area_geometry_combo.isHidden()
    assert not workspace.length_unit_combo.isHidden()

    workspace.select_measurement_tool("rectangle")
    assert workspace.measurement_type_combo.currentText() == "Area"
    assert workspace.area_geometry_combo.currentText() == "Rectangle"
    assert workspace.canvas._tool_mode == "select"
    assert not workspace.area_geometry_combo.isHidden()
    assert not workspace.area_unit_combo.isHidden()
    assert workspace.length_unit_combo.isHidden()
    assert not workspace.measurement_show_sides.isHidden()

    workspace.select_measurement_tool("ellipse")
    assert workspace.area_geometry_combo.currentText() == "Ellipse"
    assert workspace.canvas._tool_mode == "ellipse_select"

    workspace.select_measurement_tool("freehand")
    assert workspace.area_geometry_combo.currentText() == "Freehand"
    assert workspace.canvas._tool_mode == "free_select"
    assert workspace.measurement_show_sides.isHidden()


def test_measurement_label_visibility_and_undo_redo() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Measurement Undo")
    workspace = MeasureScaleWorkspace(project)
    project.calibrations["node"] = Calibration.from_known_distance(100, 50, "um")
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.measurement_type_combo.setCurrentText("Line")
    workspace.measurement_show_label.setChecked(False)

    workspace._measurement_line_selected(0, 0, 30, 40)
    measurement = next(iter(project.measurements.values()))
    assert measurement.show_label is False
    assert measurement.display_text() == "25.00 µm"

    workspace.undo()
    assert not project.measurements

    workspace.redo()
    assert len(project.measurements) == 1


def test_measurement_table_label_edit_persists_and_redraws() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Measurement Label Edit")
    workspace = MeasureScaleWorkspace(project)
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(10, 10), Point(30, 10)],
        image_node_id="node",
        calibration=Calibration.from_known_distance(100, 50, "um"),
        label="Line 1",
    )
    project.measurements[measurement.id] = measurement
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    seen = []
    workspace.canvas.set_measurements = lambda items: seen.append(items)  # type: ignore[method-assign]

    workspace._refresh_measurement_table()
    item = workspace.measurement_table.item(0, 0)
    assert item is not None
    item.setText("Body length")

    assert measurement.label == "Body length"
    assert seen[-1][0].display_text().startswith("Body length - ")
    workspace.undo()
    assert project.measurements[measurement.id].label == "Line 1"


def test_measurement_decimal_places_and_value_offset() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Measurement Digits")
    workspace = MeasureScaleWorkspace(project)
    project.calibrations["node"] = Calibration.from_known_distance(100, 50, "um")
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.measurement_digits.setValue(1)

    workspace._measurement_line_selected(0, 0, 30, 40)
    measurement = next(iter(project.measurements.values()))
    assert measurement.value_text() == "25.0 µm"

    workspace._measurement_move_mode = "value"
    workspace.canvas.set_tool_mode("move")
    workspace._measurement_move_started(20, 25)
    workspace._measurement_move_finished(20, 25, 30, 45)

    moved = next(iter(project.measurements.values()))
    assert moved.value_offset == (10.0, 20.0)


def test_measurement_move_translates_geometry_and_is_undoable() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Measurement Move")
    workspace = MeasureScaleWorkspace(project)
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(10, 10), Point(30, 10)],
        image_node_id="node",
        calibration=Calibration.from_known_distance(100, 50, "um"),
    )
    project.measurements[measurement.id] = measurement
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_tool_mode("move")

    workspace._measurement_move_started(10, 10)
    workspace._measurement_move_finished(10, 10, 15, 20)

    moved = project.measurements[measurement.id]
    assert [(point.x, point.y) for point in moved.points] == [(15, 20), (35, 20)]

    workspace.undo()
    restored = project.measurements[measurement.id]
    assert [(point.x, point.y) for point in restored.points] == [(10, 10), (30, 10)]


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

    window._select_workspace(6)

    assert window._workspace_actions[6].isChecked()
    assert not window._workspace_actions[3].isChecked()


def test_scale_bar_panel_geometry_uses_saved_source_offset() -> None:
    calibration = Calibration.from_known_distance(100, 100, "um")
    scale_bar = ScaleBar(
        image_node_id="node",
        physical_length=100,
        unit="um",
        calibration=calibration,
        width_px=10,
        location="Lower Right",
        offset_x=100,
        offset_y=50,
    )

    x, y, width, height = scale_bar_panel_geometry(
        scale_bar,
        1000,
        500,
        (10, 20, 200, 100),
    )

    assert x == pytest.approx(170)
    assert y == pytest.approx(108)
    assert width == pytest.approx(20)
    assert height == pytest.approx(2)


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

    window._select_workspace(7)

    assert window.annotation_workspace.current_asset_id() == asset.id
    assert window.annotation_workspace.canvas._scale_bar_items


def test_annotate_workspace_shows_measurements_for_selected_image(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "annotate-measurement.png"
    Image.fromarray(np.zeros((40, 60), dtype=np.uint8)).save(image_path)
    project = Project.new("Annotate Measurement Sync")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(5, 5), Point(25, 5)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(10, 5, "um"),
        label="Body length",
        display_unit="µm",
        label_alignment=MeasurementLabelAlignment.ALIGNED,
    )
    project.measurements[measurement.id] = measurement
    window = MainWindow(project)

    window._select_workspace(7)

    assert window.annotation_workspace.current_asset_id() == asset.id
    assert window.annotation_workspace.canvas._measurement_items


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

    window._select_workspace(7)
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


def _synthetic_scale_ticks(
    *,
    vertical: bool = True,
    spacing: float = 18.5,
    start: float = 24.35,
    count: int = 14,
    shape: tuple[int, int] = (160, 340),
    blur_sigma: float = 0.0,
    noise: float = 0.0,
    uneven: bool = False,
    missing: tuple[int, ...] = (),
    false_stripe: bool = False,
) -> np.ndarray:
    height, width = shape
    image = np.full((height, width), 220.0, dtype=np.float32)
    if uneven:
        if vertical:
            image += np.linspace(-25.0, 25.0, width, dtype=np.float32)[None, :]
        else:
            image += np.linspace(-25.0, 25.0, height, dtype=np.float32)[:, None]
    axis_length = width if vertical else height
    tick_length_axis = height if vertical else width
    coordinates = np.arange(axis_length, dtype=np.float32)
    for index in range(count):
        if index in missing:
            continue
        center = start + index * spacing
        length_ratio = 0.9 if index % 10 == 0 else 0.68 if index % 5 == 0 else 0.42
        length = int(tick_length_axis * length_ratio)
        sigma = 1.7 if index % 3 == 0 else 1.15
        profile = np.exp(-0.5 * ((coordinates - center) / sigma) ** 2)
        if vertical:
            image[10 : 10 + length, :] -= 185.0 * profile[None, :]
        else:
            image[:, 10 : 10 + length] -= 185.0 * profile[:, None]
    if false_stripe:
        position = int(start + 2.55 * spacing)
        if vertical:
            image[:, position : position + 2] -= 160.0
        else:
            image[position : position + 2, :] -= 160.0
    if blur_sigma > 0:
        cv2 = pytest.importorskip("cv2")
        image = cv2.GaussianBlur(image, (0, 0), blur_sigma)
    if noise > 0:
        rng = np.random.default_rng(4)
        image += rng.normal(0.0, noise, image.shape)
    return np.clip(image, 0, 255).astype(np.uint8)


def _rotated_mark_point(mark: dict[str, float | str], v: float) -> tuple[float, float]:
    u = float(mark["u"])
    return (
        float(mark["normal_x"]) * u + float(mark["tangent_x"]) * v,
        float(mark["normal_y"]) * u + float(mark["tangent_y"]) * v,
    )
