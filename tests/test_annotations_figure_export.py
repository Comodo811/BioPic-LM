from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QInputDialog,
    QLabel,
    QMessageBox,
    QToolButton,
)

import biopic.ui.main_window_project_actions as project_actions
from biopic.app.branding import WINDOW_TITLE_PREFIX
from biopic.export import (
    export_image,
    export_project_figure_board,
    export_project_figure_board_latex,
    export_project_image,
    preflight_project,
)
from biopic.export.raster_figure_board import _panel_image
from biopic.export.raster_figure_board import _visible_wedge_points as _export_visible_wedge_points
from biopic.export.raster_figure_board_rendering import (
    _common_displayed_scale_bar_value_key,
    _draw_antialiased_polygon,
    _draw_panel_scale_bars,
    _panel_draw_size,
)
from biopic.imaging.background import fill_transparent_regions_with_background
from biopic.imaging.io import import_images, read_image_asset
from biopic.imaging.project_render import render_project_image
from biopic.imaging.stacking import StackingMethod
from biopic.models.annotations import (
    AbbreviationEntry,
    AbbreviationTablePreset,
    AnnotationDefinition,
    AnnotationKind,
    AnnotationObject,
    consolidate_legend,
    fit_points_inside_unit_square,
    normalize_wedge_points,
)
from biopic.models.calibration import Calibration
from biopic.models.editing import AdjustmentLayer, EditLayer, LayerContentKind
from biopic.models.figure_board import (
    FigureBoard,
    FigureCaption,
    FigurePanel,
    PageFormat,
    PageUnit,
    PanelLabelMode,
    adjusted_scale_bar_length,
    generate_layout_presets,
    grid_panels,
    journal_presets,
    label_for_index,
    move_vertical_divider,
    page_format_presets,
    panels_from_layout,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import Measurement, MeasurementKind, Point, ScaleBar
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.ui.fonts import safe_font_family
from biopic.ui.main_window import MainWindow
from biopic.ui.settings import set_settings_json, ui_settings
from biopic.ui.workspace import AnnotationWorkspace, FigureBoardWorkspace
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.image_canvas_overlays import _annotation_path, _transformed_wedge_points
from biopic.ui.workspaces.figure_board_preview import _measurement_preview_text_items
from biopic.ui.workspaces.figure_board_preview_overlays import (
    _annotation_text_rect,
    _visible_wedge_points as _preview_visible_wedge_points,
    _wedge_handle_points,
)
from biopic.ui.workspaces.overview import OverviewWorkspace


def test_annotation_legend_consolidates_internal_objects() -> None:
    definition = AnnotationDefinition("MX", "mastax", "anatomy")
    annotations = [
        AnnotationObject("A", AnnotationKind.TEXT, [(0.1, 0.1)], "MX", definition.id),
        AnnotationObject("C", AnnotationKind.TEXT, [(0.2, 0.2)], "MX", definition.id),
    ]

    entries = consolidate_legend({definition.id: definition}, annotations)

    assert entries == ["MX, mastax (A, C)"]


def test_abbreviation_table_preset_switches_language() -> None:
    preset = AbbreviationTablePreset(
        name="Anatomy",
        active_language="German",
        entries=[
            AbbreviationEntry(
                "MX",
                {"English": "mastax", "German": "Kaumagen"},
            )
        ],
    )

    restored = AbbreviationTablePreset.from_dict(preset.to_dict())

    assert restored.languages() == ["English", "German"]
    assert restored.definitions_for_active_language()[0].full_definition == "Kaumagen"
    restored.active_language = "Italian"
    assert restored.entries[0].text_for_language("Italian") == ""
    assert restored.translated_languages() == ["English", "German"]


def test_annotation_workspace_applies_active_abbreviation_table() -> None:
    QApplication.instance() or QApplication([])
    ui_settings().remove("presets/abbreviation_tables")
    project = Project.new("Abbreviations")
    workspace = AnnotationWorkspace(project)
    preset = AbbreviationTablePreset(
        name="Anatomy",
        active_language="German",
        entries=[
            AbbreviationEntry(
                "MX",
                {"English": "mastax", "German": "Kaumagen"},
            )
        ],
    )
    workspace._abbreviation_presets[preset.id] = preset
    workspace._active_abbreviation_table_id = preset.id

    workspace._apply_active_abbreviation_table()

    definitions = list(project.annotation_definitions.values())
    assert definitions[0].abbreviation == "MX"
    assert definitions[0].full_definition == "Kaumagen"


def test_annotation_workspace_language_switch_clears_untranslated_complete_words() -> None:
    QApplication.instance() or QApplication([])
    ui_settings().remove("presets/abbreviation_tables")
    project = Project.new("Language Clear")
    workspace = AnnotationWorkspace(project)
    preset = AbbreviationTablePreset(
        name="Anatomy",
        active_language="English",
        entries=[AbbreviationEntry("MX", {"English": "mastax"})],
    )
    workspace._abbreviation_presets[preset.id] = preset
    workspace._active_abbreviation_table_id = preset.id
    workspace._refresh_abbreviation_table_view()

    workspace._abbreviation_language_changed("German")

    assert workspace.abbreviation_table.item(0, 0).text() == "MX"
    assert workspace.abbreviation_table.item(0, 1).text() == ""


def test_annotation_workspace_legend_hides_internal_node_ids() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Readable Legend")
    definition = AnnotationDefinition("MX", "mastax")
    project.annotation_definitions[definition.id] = definition
    project.annotations["ann"] = AnnotationObject(
        image_node_id="internal-node-id",
        kind=AnnotationKind.TEXT,
        points=[(0.1, 0.1)],
        text="MX",
        definition_id=definition.id,
    )
    workspace = AnnotationWorkspace(project)

    workspace._refresh_records()

    assert workspace.records.toPlainText() == "Legend\nMX, mastax"


def test_annotation_font_picker_uses_directwrite_safe_fonts() -> None:
    QApplication.instance() or QApplication([])
    ui_settings().remove("presets/abbreviation_tables")
    workspace = AnnotationWorkspace(Project.new("Safe Fonts"))
    unsafe_families = {"MS Sans Serif", "MS Serif", "Fixedsys"}

    assert workspace._safe_annotation_font_family() not in unsafe_families
    for family in unsafe_families:
        assert safe_font_family(family) not in unsafe_families


def test_annotation_default_style_is_arial_white_and_persistent() -> None:
    QApplication.instance() or QApplication([])
    ui_settings().remove("annotation/default_style")
    workspace = AnnotationWorkspace(Project.new("Default Annotation Style"))

    assert workspace._safe_annotation_font_family() == safe_font_family("Arial")
    assert workspace._annotation_color == "#ffffff"

    workspace.annotation_font_size.setValue(21.0)
    workspace.annotation_width.setValue(5.0)
    workspace._annotation_color = "#000000"
    workspace._save_persistent_annotation_style()

    restored = AnnotationWorkspace(Project.new("Restored Annotation Style"))
    assert restored.annotation_font_size.value() == 21.0
    assert restored.annotation_width.value() == 5.0
    assert restored._annotation_color == "#000000"


def test_overview_uses_image_names_instead_of_internal_node_ids(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(image_path, np.full((8, 8), 100, dtype=np.uint8))
    project = Project.new("Readable Overview")
    asset = ImageAsset(path=str(image_path), display_name="source.tif", width=8, height=8)
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.calibrations[node_id] = Calibration.from_known_distance(100, 50, "um")
    project.scale_bars["bar"] = ScaleBar(
        image_node_id=node_id,
        physical_length=50,
        unit="um",
        calibration=project.calibrations[node_id],
    )
    project.annotations["ann"] = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.1, 0.1)],
        text="MX",
    )
    workspace = OverviewWorkspace(project)

    workspace.refresh()

    labels = [
        child.text()
        for child in workspace.content.findChildren(QLabel)
        if child.text()
    ]
    assert any("source.tif: 0.5" in label and "/px" in label for label in labels)
    assert any("source.tif: 50" in label and "scale bar" in label for label in labels)
    assert any("source.tif: MX" in label for label in labels)
    assert all(node_id not in label for label in labels)


def test_add_label_uses_active_abbreviation_table_definition() -> None:
    QApplication.instance() or QApplication([])
    ui_settings().remove("presets/abbreviation_tables")
    project = Project.new("Label Definition")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    preset = AbbreviationTablePreset(
        name="Anatomy",
        active_language="English",
        entries=[AbbreviationEntry("MX", {"English": "mastax"})],
    )
    workspace._abbreviation_presets[preset.id] = preset
    workspace._active_abbreviation_table_id = preset.id
    workspace._label_text_from_user = lambda: "mx"  # type: ignore[method-assign]

    workspace.add_label()

    annotation = next(iter(project.annotations.values()))
    definition = project.annotation_definitions[annotation.definition_id]
    assert annotation.text == "mx"
    assert definition.abbreviation == "mx"
    assert definition.full_definition == "mastax"


def test_annotation_shape_tools_create_vector_overlay() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Annotation Shapes")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    workspace.select_annotation_tool("arrow")

    workspace._annotation_rectangle_selected(10, 20, 50, 30)

    annotation = next(iter(project.annotations.values()))
    assert annotation.kind is AnnotationKind.ARROW
    assert annotation.points == [(10 / 120, 20 / 100), (60 / 120, 50 / 100)]
    assert workspace.canvas._annotation_items


def test_annotation_wedge_tool_creates_scalable_triangle() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Annotation Wedge")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    workspace.select_annotation_tool("wedge")

    workspace._annotation_rectangle_selected(10, 20, 50, 30)

    annotation = next(iter(project.annotations.values()))
    assert annotation.kind is AnnotationKind.WEDGE
    assert annotation.points[0] == (60 / 120, 50 / 100)
    assert annotation.points[1][0] < annotation.points[0][0]
    assert annotation.points[2][0] < annotation.points[0][0]
    assert annotation.points[1] != annotation.points[2]
    assert annotation.fill == workspace._annotation_color
    path = _annotation_path(
        annotation.kind,
        [QPointF(x * 120, y * 100) for x, y in annotation.points],
        annotation.line_width,
    )
    assert path.elementCount() >= 4


def test_annotation_shape_mouse_release_emits_drag_start_and_end() -> None:
    QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    canvas.set_tool_mode("annotation_shape")
    canvas._drag_start = QPointF(10.0, 20.0)
    emitted: list[tuple[int, int, int, int]] = []
    canvas.annotationShapeSelected.connect(lambda *args: emitted.append(tuple(args)))
    release_position = QPointF(canvas.mapFromScene(QPointF(60.0, 50.0)))

    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        release_position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mouseReleaseEvent(event)

    assert emitted == [(10, 20, 60, 50)]


def test_annotation_wedge_click_creates_visible_default_triangle() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Annotation Wedge Click")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    workspace.select_annotation_tool("wedge")

    workspace._annotation_point_clicked(60, 50)

    annotation = next(iter(project.annotations.values()))
    assert annotation.kind is AnnotationKind.WEDGE
    assert len(annotation.points) == 3
    xs = [point[0] for point in annotation.points]
    ys = [point[1] for point in annotation.points]
    assert max(xs) > min(xs)
    assert max(ys) > min(ys)
    assert annotation.points[0][0] > annotation.points[1][0]
    assert annotation.points[0][0] > annotation.points[2][0]
    assert annotation.points[1][1] != annotation.points[2][1]


def test_annotation_wedge_creation_preserves_full_triangle_at_image_edge() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Annotation Wedge Edge")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    workspace.select_annotation_tool("wedge")

    workspace._annotation_rectangle_selected(-20, -10, 50, 30)

    annotation = next(iter(project.annotations.values()))
    xs = [point[0] for point in annotation.points]
    ys = [point[1] for point in annotation.points]
    assert min(xs) >= 0.0
    assert min(ys) >= 0.0
    assert max(xs) <= 1.0
    assert max(ys) <= 1.0
    assert annotation.points[1] != annotation.points[2]
    assert (max(xs) - min(xs)) > 0.0
    assert (max(ys) - min(ys)) > 0.0


def test_selected_wedge_shows_transform_handles_and_updates_points() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Wedge Handles")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    annotation = AnnotationObject(
        image_node_id="node",
        kind=AnnotationKind.WEDGE,
        points=[(0.6, 0.5), (0.4, 0.4), (0.4, 0.6)],
        fill="#ffffff",
    )
    project.annotations[annotation.id] = annotation

    workspace._refresh_annotation_overlay()
    workspace._select_annotation_by_id(annotation.id)

    assert len(workspace.canvas._annotation_edit_items) >= 6
    original = list(annotation.points)
    workspace.canvas._annotation_handle_drag_started(annotation.id, "length")
    workspace.canvas._annotation_handle_moved(annotation.id, "length", QPointF(90.0, 50.0))
    workspace.canvas._annotation_handle_released()

    assert annotation.points != original
    assert annotation.points[0][0] > original[0][0]


def test_line_annotation_previews_and_uses_transform_handles() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Line Handles")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    workspace.select_annotation_tool("line")

    workspace.canvas._update_annotation_shape_preview(QPointF(10.0, 20.0), QPointF(80.0, 70.0))

    assert workspace.canvas._line_preview_item.isVisible()
    assert workspace.canvas._line_preview_item.path().elementCount() >= 2
    workspace._annotation_rectangle_selected(10, 20, 50, 30)
    annotation = next(iter(project.annotations.values()))
    workspace._select_annotation_by_id(annotation.id)

    assert len(workspace.canvas._annotation_edit_items) >= 5
    original = list(annotation.points)
    workspace.canvas._annotation_handle_drag_started(annotation.id, "rotate")
    workspace.canvas._annotation_handle_moved(annotation.id, "rotate", QPointF(40.0, 10.0))
    workspace.canvas._annotation_handle_released()

    assert annotation.points != original


def test_annotation_delete_removes_selected_annotation() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Delete Annotation")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    annotation = AnnotationObject(
        image_node_id="node",
        kind=AnnotationKind.WEDGE,
        points=[(0.6, 0.5), (0.4, 0.4), (0.4, 0.6)],
        fill="#ffffff",
    )
    project.annotations[annotation.id] = annotation
    workspace._refresh_annotation_overlay()
    workspace._select_annotation_by_id(annotation.id)

    assert workspace._delete_selected_annotation()

    assert annotation.id not in project.annotations
    assert workspace._selected_annotation_id is None
    assert not workspace.canvas._annotation_edit_items


def test_annotation_undo_redo_restores_shape_creation() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Annotation Undo")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    workspace.select_annotation_tool("wedge")

    workspace._annotation_shape_selected(10, 20, 60, 50)
    annotation_ids = set(project.annotations)
    assert annotation_ids

    workspace.undo()
    assert project.annotations == {}

    workspace.redo()
    assert set(project.annotations) == annotation_ids


def test_figure_board_selected_wedge_handle_transforms_annotation(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "source.tif"
    tifffile.imwrite(image_path, np.full((60, 80), 120, dtype=np.uint8))
    project = Project.new("Figure Wedge Handles")
    asset = ImageAsset(path=str(image_path), display_name="source.tif", width=80, height=60)
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    annotation = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.WEDGE,
        points=[(0.65, 0.5), (0.35, 0.35), (0.35, 0.65)],
        fill="#ffffff",
    )
    project.annotations[annotation.id] = annotation
    board = FigureBoard(
        "Board",
        PageFormat("px", 100, 100, PageUnit.PIXEL),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="A")],
    )
    workspace = FigureBoardWorkspace(project)
    workspace.preview.set_board(board)
    workspace.preview.set_annotation_edit_enabled(True)
    workspace.preview._selected_overlay = {"kind": "annotation", "id": annotation.id}
    panel_rect = workspace.preview._panel_rect(
        board.panels[0],
        workspace.preview._content_rect(
            workspace.preview._printable_rect(workspace.preview._page_rect())
        ),
    )
    transform, local_rect, _polygon = workspace.preview._image_transform_geometry(
        board.panels[0],
        panel_rect,
        workspace.preview._panel_pixmap(board.panels[0], panel_rect, asset),
    )
    widget_points = [
        transform.map(
            QPointF(
                local_rect.x() + x * local_rect.width(),
                local_rect.y() + y * local_rect.height(),
            )
        )
        for x, y in annotation.points
    ]
    scale_handle = _wedge_handle_points(widget_points)["scale"]

    hit = workspace.preview._annotation_overlay_at(
        node_id,
        scale_handle,
        transform,
        local_rect,
    )
    assert hit is not None
    assert hit["target"] == "scale"
    workspace.preview._overlay_drag = hit
    workspace.preview._overlay_drag["start_position"] = scale_handle
    workspace.preview._move_overlay_drag(scale_handle + QPointF(20.0, 20.0))

    assert annotation.points != [(0.65, 0.5), (0.35, 0.35), (0.35, 0.65)]


def test_wedge_transform_can_scale_below_old_twenty_percent_floor() -> None:
    original = [
        QPointF(100.0, 50.0),
        QPointF(60.0, 40.0),
        QPointF(60.0, 60.0),
    ]
    center = QPointF(73.3333333333, 50.0)
    handle = QPointF(120.0, 70.0)
    target = QPointF(center.x() + (handle.x() - center.x()) * 0.05, center.y() + (handle.y() - center.y()) * 0.05)

    transformed = _transformed_wedge_points(original, center, "scale", handle, target)

    old_floor_width = (max(point.x() for point in original) - min(point.x() for point in original)) * 0.2
    new_width = max(point.x() for point in transformed) - min(point.x() for point in transformed)
    assert new_width < old_floor_width


def test_figure_board_preview_keeps_small_wedge_visibly_triangular() -> None:
    points = [
        QPointF(100.0, 100.0),
        QPointF(80.0, 99.0),
        QPointF(80.0, 101.0),
    ]

    visible = _preview_visible_wedge_points(points, 18.0)

    base_width = (
        (visible[2].x() - visible[1].x()) ** 2
        + (visible[2].y() - visible[1].y()) ** 2
    ) ** 0.5
    assert base_width == pytest.approx(18.0)
    assert visible[0] == points[0]


def test_figure_board_preview_expands_legacy_two_point_wedge_to_triangle() -> None:
    points = [
        QPointF(80.0, 100.0),
        QPointF(120.0, 100.0),
    ]

    visible = _preview_visible_wedge_points(points, 18.0)

    assert len(visible) == 3
    assert visible[0] == points[1]
    assert visible[1].x() == pytest.approx(points[0].x())
    assert visible[2].x() == pytest.approx(points[0].x())
    assert abs(visible[2].y() - visible[1].y()) >= 18.0


def test_figure_board_export_keeps_small_wedge_visibly_triangular() -> None:
    points = [
        (100.0, 100.0),
        (80.0, 99.0),
        (80.0, 101.0),
    ]

    visible = _export_visible_wedge_points(points, 18.0)

    base_width = (
        (visible[2][0] - visible[1][0]) ** 2
        + (visible[2][1] - visible[1][1]) ** 2
    ) ** 0.5
    assert base_width == pytest.approx(18.0)
    assert visible[0] == points[0]


def test_figure_board_export_expands_legacy_two_point_wedge_to_triangle() -> None:
    points = [
        (80.0, 100.0),
        (120.0, 100.0),
    ]

    visible = _export_visible_wedge_points(points, 18.0)

    assert len(visible) == 3
    assert visible[0] == points[1]
    assert visible[1][0] == pytest.approx(points[0][0])
    assert visible[2][0] == pytest.approx(points[0][0])
    assert abs(visible[2][1] - visible[1][1]) >= 18.0


def test_figure_board_export_keeps_actual_small_triangle_when_no_minimum_requested() -> None:
    points = [
        (100.0, 100.0),
        (80.0, 99.0),
        (80.0, 101.0),
    ]

    visible = _export_visible_wedge_points(points, 0.0)

    assert visible == points


def test_wedge_polygon_draws_antialiased_edges() -> None:
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))

    _draw_antialiased_polygon(
        image,
        [(5.2, 4.7), (33.6, 17.4), (7.1, 35.3)],
        (255, 255, 255, 255),
    )

    alpha_values = np.asarray(image.getchannel("A"))
    unique_alpha = np.unique(alpha_values)
    assert np.any((unique_alpha > 0) & (unique_alpha < 255))
    assert np.any(unique_alpha == 255)


def test_wedge_points_are_fit_inside_image_without_flattening() -> None:
    points = [(-0.2, -0.1), (0.25, -0.25), (0.25, 0.25)]

    fitted = fit_points_inside_unit_square(points)

    xs = [point[0] for point in fitted]
    ys = [point[1] for point in fitted]
    assert min(xs) >= 0.0
    assert min(ys) >= 0.0
    assert max(xs) <= 1.0
    assert max(ys) <= 1.0
    assert fitted[1] != fitted[2]
    assert (max(xs) - min(xs)) > 0.0
    assert (max(ys) - min(ys)) > 0.0


def test_legacy_two_point_wedge_normalizes_to_bounded_triangle() -> None:
    points = [(0.25, 0.5), (0.75, 0.5)]

    normalized = normalize_wedge_points(points)

    assert len(normalized) == 3
    assert normalized[0] == points[1]
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in normalized)
    assert normalized[1] != normalized[2]


def test_wedge_normalization_respects_padding_without_flattening() -> None:
    points = [(0.0, 0.5), (0.3, 0.1), (0.3, 0.9)]

    normalized = normalize_wedge_points(points, padding=0.05)

    xs = [point[0] for point in normalized]
    ys = [point[1] for point in normalized]
    assert min(xs) >= 0.05
    assert min(ys) >= 0.05
    assert max(xs) <= 0.95
    assert max(ys) <= 0.95
    assert normalized[1] != normalized[2]


def test_annotation_label_tool_uses_active_abbreviation_table_at_click() -> None:
    QApplication.instance() or QApplication([])
    ui_settings().remove("presets/abbreviation_tables")
    project = Project.new("Label Click")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    preset = AbbreviationTablePreset(
        name="Anatomy",
        active_language="English",
        entries=[AbbreviationEntry("MX", {"English": "mastax"})],
    )
    workspace._abbreviation_presets[preset.id] = preset
    workspace._active_abbreviation_table_id = preset.id
    workspace._label_text_from_user = lambda: "mx"  # type: ignore[method-assign]
    workspace.select_annotation_tool("label")

    workspace._annotation_point_clicked(12, 25)

    annotation = next(iter(project.annotations.values()))
    definition = project.annotation_definitions[annotation.definition_id]
    assert annotation.kind is AnnotationKind.TEXT
    assert annotation.points == [(0.1, 0.25)]
    assert definition.full_definition == "mastax"


def test_annotation_label_tool_does_not_create_empty_default_label() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("No Default Label")
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 120), dtype=np.uint8), fit=False)
    workspace._label_text_from_user = lambda: ""  # type: ignore[method-assign]

    workspace._annotation_point_clicked(12, 25)

    assert not project.annotations


def test_annotation_move_tool_repositions_vector_annotation() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Move Annotation")
    annotation = AnnotationObject(
        "node",
        AnnotationKind.LINE,
        [(0.2, 0.2), (0.4, 0.4)],
        include_in_legend=False,
    )
    project.annotations[annotation.id] = annotation
    workspace = AnnotationWorkspace(project)
    workspace._current_source_node_id = lambda: "node"  # type: ignore[method-assign]
    workspace.canvas.set_pixels(np.zeros((100, 100), dtype=np.uint8), fit=False)
    workspace.select_annotation_tool("move")

    workspace._annotation_move_started(20, 20)
    workspace._annotation_move_finished(20, 20, 30, 40)

    assert annotation.points == [(0.3, 0.4), (0.5, 0.6)]


def test_annotate_toolbar_exposes_abbreviation_table_dropdown() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Annotate Toolbar"))

    window._select_workspace(7)
    labels = [
        action.text()
        for action in window.context_toolbar.actions()
        if action.text()
    ]

    assert "Add Label" in labels
    assert any(
        button.text() == "Abbreviation Table"
        for button in window.context_toolbar.findChildren(
            type(window.annotation_workspace.abbreviation_table_button)
        )
    )
    assert "QMenu" in window.annotation_workspace.abbreviation_table_menu.styleSheet()


def test_annotation_style_controls_update_current_image_when_no_row_selected(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "annotation-global-style.png"
    Image.fromarray(np.full((40, 50, 3), 120, dtype=np.uint8)).save(image_path)
    project = Project.new("Annotation Global Style")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    first = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.2, 0.2)],
        text="a",
        size=9.0,
    )
    second = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.LINE,
        points=[(0.2, 0.2), (0.5, 0.5)],
        line_width=1.0,
    )
    project.annotations[first.id] = first
    project.annotations[second.id] = second
    workspace = AnnotationWorkspace(project)
    workspace.refresh()
    workspace._selected_annotation_id = None

    workspace.annotation_font_size.setValue(18.0)
    workspace.annotation_width.setValue(4.0)

    assert first.size == 18.0
    assert second.size == 18.0
    assert first.line_width == 4.0
    assert second.line_width == 4.0


def test_first_image_import_switches_to_overview(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "first-import.png"
    Image.fromarray(np.full((8, 12), 64, dtype=np.uint8)).save(image_path)
    window = MainWindow(Project.new("First Import Switch"))
    window._select_workspace(5)
    monkeypatch.setattr(window, "_select_image_paths", lambda _title: [image_path])

    window.import_image()

    assert window._workspace.currentWidget() is window.overview_workspace


def test_later_image_import_keeps_active_workspace(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    first_path = workspace_tmp_path / "existing.png"
    second_path = workspace_tmp_path / "later-import.png"
    Image.fromarray(np.full((8, 12), 64, dtype=np.uint8)).save(first_path)
    Image.fromarray(np.full((8, 12), 96, dtype=np.uint8)).save(second_path)
    project = Project.new("Later Import Stays Put")

    import_images(project, [first_path])
    window = MainWindow(project)
    window._select_workspace(5)
    monkeypatch.setattr(window, "_select_image_paths", lambda _title: [second_path])

    window.import_image()

    assert window._workspace.currentWidget() is window.edit_workspace
    assert len(project.assets) == 2


def test_open_project_updates_window_title(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    saved_project = Project.new("Loaded Project")
    project_path = workspace_tmp_path / "loaded.biopic.json"
    ProjectStore().save(saved_project, project_path)
    window = MainWindow(Project.new("Untitled Project"))
    monkeypatch.setattr(
        project_actions,
        "remembered_open_file",
        lambda *_args, **_kwargs: str(project_path),
    )

    window.open_project()

    assert window.project.name == "Loaded Project"
    assert window.windowTitle() == f"{WINDOW_TITLE_PREFIX} - Loaded Project"


def test_clean_opened_project_save_is_noop(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    saved_project = Project.new("Loaded Project")
    project_path = workspace_tmp_path / "loaded-clean.biopic.json"
    ProjectStore().save(saved_project, project_path)
    window = MainWindow(Project.new("Untitled Project"))
    monkeypatch.setattr(
        project_actions,
        "remembered_open_file",
        lambda *_args, **_kwargs: str(project_path),
    )
    window.open_project()

    def fail_save(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("clean Ctrl-S must not enter project save/archive")

    monkeypatch.setattr(window.store, "save", fail_save)

    assert window.save_project() is True
    assert window._has_unsaved_changes is False


def test_rename_project_updates_title_and_marks_dirty(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Original Project"))
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Renamed Project", True),
    )

    window.rename_project()

    assert window.project.name == "Renamed Project"
    assert window.windowTitle() == f"{WINDOW_TITLE_PREFIX} - Renamed Project*"


def test_copy_paste_project_image_preserves_editable_state_without_annotations(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.chdir(workspace_tmp_path)
    image_path = workspace_tmp_path / "edited-source.png"
    pixels = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    Image.fromarray(pixels).save(image_path)
    project = Project.new("Copy Paste Image")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    asset.metadata["life_stage"] = "adult"
    project.calibrations[node_id] = Calibration(unit_per_pixel=0.5, unit="um")
    edit_layer = EditLayer(
        name="Retouch",
        source_node_id=node_id,
        content_kind=LayerContentKind.RASTER,
        order=0,
    )
    content = np.zeros_like(pixels)
    content[0, 0] = [255, 0, 0]
    alpha = np.zeros(pixels.shape[:2], dtype=np.float32)
    alpha[0, 0] = 1.0
    edit_layer.set_content_pixels(content)
    edit_layer.set_alpha_pixels(alpha)
    project.edit_layers[edit_layer.id] = edit_layer
    project.active_edit_layers[node_id] = edit_layer.id
    layer = AdjustmentLayer(
        name="Gamma",
        image_node_id=node_id,
        operation="gamma",
        parameters={"gamma": 1.4},
    )
    project.add_adjustment_layer(layer)
    project.annotations["note"] = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.2, 0.2)],
        text="A",
    )
    expected = render_project_image(project, node_id)
    window = MainWindow(project)
    window._select_workspace(5)

    window.copy_current_project_image()
    window.paste_copied_project_image()

    pasted = next(item for item in project.assets.values() if item.id != asset.id)
    pasted_node_id = project.source_node_id_for_asset(pasted.id)
    assert pasted_node_id is not None
    copied_edit_layers = [
        item for item in project.edit_layers.values() if item.source_node_id == pasted_node_id
    ]
    copied_adjustment_layers = project.adjustment_layers_for_image(pasted_node_id)
    assert pasted.metadata["life_stage"] == "adult"
    assert pasted.metadata["copied_from_node_id"] == node_id
    assert Path(pasted.path).suffix == ".png"
    assert Path(pasted.filename).suffix == ".png"
    assert project.calibrations[pasted_node_id].unit_per_pixel == 0.5
    assert len(copied_edit_layers) == 1
    assert copied_edit_layers[0].id != edit_layer.id
    assert copied_edit_layers[0].filter_operation == edit_layer.filter_operation
    assert project.active_edit_layers[pasted_node_id] == copied_edit_layers[0].id
    assert len(copied_adjustment_layers) == 1
    assert copied_adjustment_layers[0].id != layer.id
    assert copied_adjustment_layers[0].parameters == {"gamma": 1.4}
    assert all(
        annotation.image_node_id != pasted_node_id
        for annotation in project.annotations.values()
    )
    assert render_project_image(project, pasted_node_id) is not None
    np.testing.assert_array_equal(render_project_image(project, pasted_node_id), expected)
    project.adjustment_layers[layer.id].parameters = {"gamma": 2.2}
    project.adjustment_layers[layer.id].touch()
    project.edit_layers[edit_layer.id].opacity = 0.25

    assert copied_adjustment_layers[0].parameters == {"gamma": 1.4}
    assert copied_edit_layers[0].opacity == 1.0
    assert not np.array_equal(
        render_project_image(project, node_id),
        render_project_image(project, pasted_node_id),
    )


def test_figure_board_grid_and_divider_movement() -> None:
    panels = grid_panels(3)
    left, right = move_vertical_divider(panels[0], panels[1], 0.05)

    assert len(panels) == 3
    assert panels[0].label == "A"
    assert left.rect[2] > panels[0].rect[2]
    assert right.rect[2] < panels[1].rect[2]


def test_figure_board_publication_layout_presets_and_labels() -> None:
    pages = page_format_presets()
    layouts = generate_layout_presets(4)
    panels = panels_from_layout(layouts[0], PanelLabelMode.NUMERICAL)

    assert "DIN A4 Portrait" in pages
    assert any(layout.name == "Large left" for layout in layouts)
    assert [panel.label for panel in panels] == ["1", "2", "3", "4"]
    assert label_for_index(26, PanelLabelMode.ALPHABETICAL) == "AA"
    assert label_for_index(26, PanelLabelMode.ALPHABETICAL_LOWER) == "aa"
    assert "Nature" in journal_presets()


def test_figure_board_five_panel_split_layout_presets() -> None:
    layouts = generate_layout_presets(5)
    names = {layout.name for layout in layouts}

    assert {
        "Two top, three bottom",
        "Three top, two bottom",
        "Two left, three right",
        "Three left, two right",
    }.issubset(names)
    assert all(len(layout.panels) == 5 for layout in layouts)


def test_figure_caption_manual_lock_preserves_user_text() -> None:
    caption = FigureCaption()
    caption.update_auto_generated("Auto caption")
    caption.user_text = "Manual caption"
    caption.user_modified = True
    caption.locked = True

    caption.update_auto_generated("Updated auto caption")

    assert caption.visible_text() == "Manual caption"
    assert caption.auto_generated == "Updated auto caption"


def test_figure_board_workspace_creates_empty_publication_placeholders() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Publication Board")
    workspace = FigureBoardWorkspace(project)
    workspace.panel_count.setValue(4)

    workspace.create_board()

    board = next(iter(project.figure_boards.values()))
    assert len(board.panels) == 4
    assert all(panel.source_node_id is None for panel in board.panels)
    assert board.label_mode is PanelLabelMode.ALPHABETICAL
    assert board.caption.auto_generated
    assert workspace.preview._board is board
    assert all(0.0 < panel.label_offset[0] < 0.1 for panel in board.panels)
    assert all(0.0 < panel.label_offset[1] < 0.1 for panel in board.panels)
    legacy_offset_px = workspace.preview._panel_label_offset_px(
        2.0,
        100.0,
        workspace.preview._page_rect(),
    )
    assert 1.0 <= legacy_offset_px < 20.0


def test_figure_board_workspace_uses_independent_page_and_journal_fields() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Publication Settings")
    workspace = FigureBoardWorkspace(project)
    workspace.page_combo.setCurrentText("DIN A3 Landscape")
    workspace.set_journal_preset("Nature")
    workspace.horizontal_spacing.setValue(6.0)

    workspace.create_board()

    board = next(iter(project.figure_boards.values()))
    assert board.page.name == "DIN A3 Landscape"
    assert board.journal_preset == "Nature"
    assert board.horizontal_gutter == 6.0


def test_figure_board_workspace_hides_global_layout_controls_from_main_panel() -> None:
    QApplication.instance() or QApplication([])
    workspace = FigureBoardWorkspace(Project.new("Clean Figureboard"))
    visible_group_titles = [
        group.title()
        for group in workspace.findChildren(QGroupBox)
        if group.isVisible()
    ]

    assert hasattr(workspace, "image_strip")
    assert workspace.image_strip.height() == 156
    assert workspace.image_strip.iconSize().width() == 144
    assert not hasattr(workspace, "layout_button")
    assert "Board Size" not in visible_group_titles
    assert "Margins" not in visible_group_titles
    assert not hasattr(workspace, "journal_combo")


def test_figure_board_preview_uses_export_panel_zoom_geometry() -> None:
    QApplication.instance() or QApplication([])
    workspace = FigureBoardWorkspace(Project.new("Preview Export Geometry"))
    panel = FigurePanel(
        crop=(0.43, 0.57, 0.72),
        rotation=33.0,
    )
    panel_rect = QRectF(0.0, 0.0, 180.0, 120.0)
    pixmap = QPixmap(320, 90)
    export_image = Image.new("RGBA", (320, 90))
    preview_size = workspace.preview._panel_pixmap_draw_size(
        pixmap,
        panel_rect,
        panel.crop[2],
        panel.rotation,
    )
    export_size = _panel_draw_size(
        export_image,
        int(round(panel_rect.width())),
        int(round(panel_rect.height())),
        panel.crop[2],
    )

    assert preview_size == export_size


def test_figureboard_toolbar_exposes_layout_next_to_create() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Figure Toolbar"))

    window._select_workspace(8)
    labels = [action.text() for action in window.context_toolbar.actions() if action.text()]

    assert labels[:2] == ["Create Figure Board", "Layout"]


def test_measure_toolbar_restores_scale_and_measurement_actions() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Measure Toolbar"))

    window._select_workspace(6)
    action_labels = [
        action.text() for action in window.context_toolbar.actions() if action.text()
    ]
    button_labels = [
        button.text()
        for button in window.context_toolbar.findChildren(QToolButton)
        if button.text()
    ]

    assert "Set Scale" in button_labels
    assert action_labels[:2] == ["Add Scale Bar", "Add Measurement"]


def test_stack_toolbar_keeps_only_import_save_and_comparison_actions() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Stack Toolbar"))

    window._select_workspace(2)
    labels = [action.text() for action in window.context_toolbar.actions() if action.text()]

    assert labels == ["Import Image Stack", "Save Result As", "Sharpness Comparison"]


def test_main_window_exposes_journal_presets_outside_figure_board_dialog() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Journal Menu"))

    menu_titles = [action.text().replace("&", "") for action in window.menuBar().actions()]

    assert app is not None
    assert "Presets" in menu_titles
    assert window.presets_menu.title().replace("&", "") == "Presets"
    assert any(action.text() == "Nature" for action in window.journal_presets_menu.actions())


def test_main_window_workspace_menu_order_is_fixed() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Menu Order"))

    menu_titles = [
        action.text().replace("&", "")
        for action in window.menuBar().actions()
        if action.text()
    ]

    assert menu_titles == [
        "File",
        "Edit",
        "Options",
        "Presets",
        "Overview",
        "Stack from Video",
        "Stack",
        "Stitch Images",
        "Metadata",
        "Edit Image",
        "Measure and Scale",
        "Annotate",
        "Figure Board",
        "Help",
    ]


def test_main_window_options_controls_stack_debug_and_gpu() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Options Controls"))

    assert window.debug_options_action is not None
    assert window.cuda_action is not None
    assert window.gpu_limit_options_spin is not None
    assert window.stack_workspace.debug_save_stages_check.isHidden()
    assert window.stack_workspace.cuda_check.isHidden()

    window.debug_options_action.setChecked(True)
    custom_index = window.stack_workspace.method_combo.findData(StackingMethod.CUSTOM.value)
    if custom_index >= 0:
        window.stack_workspace.method_combo.setCurrentIndex(custom_index)
        assert not window.stack_workspace.debug_save_stages_check.isHidden()

    window.cuda_action.setChecked(True)
    assert window.stack_workspace._parameters().use_cuda is True
    window.gpu_limit_options_spin.setValue(6)
    assert window.stack_workspace._parameters().gpu_memory_limit_mb == 6144


def test_main_window_loads_persistent_metadata_presets() -> None:
    QApplication.instance() or QApplication([])
    set_settings_json(
        "presets/metadata",
        {
            "schema_version": 1,
            "metadata_presets": {
                "location": [{"name": "Lake", "locality": "Lake edge"}],
                "collector": [{"name": "Team", "collector": "Ada"}],
                "preparation": [{"name": "Mounted", "preparation": "Slide mount"}],
            },
        },
    )

    window = MainWindow(Project.new("Persistent Presets"))

    assert window.project.metadata_presets["location"][0]["locality"] == "Lake edge"
    assert window.project.metadata_presets["collector"][0]["collector"] == "Ada"
    assert window.project.metadata_presets["preparation"][0]["preparation"] == "Slide mount"


def test_figure_board_assignment_references_source_node_and_updates_caption() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Board Assignment")
    asset = ImageAsset(path=str(Path(__file__)), display_name="Brachionus.png")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.assets[asset.id].metadata["scientific_name"] = "Brachionus calyciflorus"
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))

    workspace.assign_image_to_panel(board.id, board.panels[0].id, node_id)

    assert board.panels[0].source_node_id == node_id
    figure_node = next(
        node for node in project.graph.nodes.values() if node.operation == "figure_board"
    )
    assert node_id in figure_node.inputs
    assert "Brachionus calyciflorus" in board.caption.auto_generated


def test_figure_board_clear_panel_image_keeps_frame() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Board Clear Image")
    asset = ImageAsset(path=str(Path(__file__)), display_name="Brachionus.png")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)

    workspace._clear_panel_image(panel.id)

    assert panel.source_node_id is None
    assert panel.rect == board.panels[0].rect
    figure_node = next(
        node for node in project.graph.nodes.values() if node.operation == "figure_board"
    )
    assert node_id not in figure_node.inputs


def test_figure_board_refresh_preserves_active_board_with_assigned_image(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Active Board")
    image_path = workspace_tmp_path / "source.png"
    Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8)).save(image_path)
    asset = ImageAsset(path=str(image_path), display_name="Brachionus.png")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    first = next(iter(project.figure_boards.values()))
    second = FigureBoard(
        "Second",
        first.page,
        panels=[FigurePanel(source_node_id=node_id, label="A")],
    )
    project.figure_boards[second.id] = second
    workspace._current_board_id = second.id

    workspace.refresh()

    assert workspace.preview._board is second
    assert workspace.preview._board.panels[0].source_node_id == node_id


def test_figure_board_refresh_reuses_rendered_strip_thumbnails(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Strip Cache")
    image_path = workspace_tmp_path / "strip-source.png"
    Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8)).save(image_path)
    asset = ImageAsset(path=str(image_path), display_name="Brachionus.png")
    project.add_asset(asset)
    workspace = FigureBoardWorkspace(project)
    workspace.refresh()

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unchanged figure-board refresh must reuse strip thumbnails")

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_strip.render_project_image",
        fail_render,
    )

    workspace.refresh()


def test_figure_board_refresh_defers_strip_thumbnail_rendering(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Lazy Strip")
    image_path = workspace_tmp_path / "lazy-strip-source.png"
    Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    workspace = FigureBoardWorkspace(project)

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("figure-board activation must not synchronously render thumbnails")

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_strip.render_project_image",
        fail_render,
    )

    workspace.refresh()

    assert workspace.image_strip.count() == 1
    assert workspace.image_strip.item(0).data(256) == asset.id
    assert len(workspace.image_strip._thumbnail_queue) == 1


def test_figure_board_source_strip_delete_key_requests_asset_delete(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Delete Key")
    image_path = workspace_tmp_path / "delete-key-source.png"
    Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    workspace = FigureBoardWorkspace(project)
    workspace.refresh()
    workspace.image_strip.setCurrentRow(0)
    requested: list[str] = []
    workspace.image_strip.assetDeleteRequested.connect(requested.append)

    event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Delete,
        Qt.KeyboardModifier.NoModifier,
    )
    workspace.image_strip.keyPressEvent(event)

    assert requested == [asset.id]


def test_figure_board_delete_plain_source_asset_without_prompt(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Delete Plain Source")
    image_path = workspace_tmp_path / "plain-delete-source.png"
    Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    workspace = FigureBoardWorkspace(project)
    workspace.refresh()

    def fail_question(*_args: object, **_kwargs: object) -> QMessageBox.StandardButton:
        raise AssertionError("plain source deletion should not prompt")

    monkeypatch.setattr(QMessageBox, "question", fail_question)

    workspace._delete_source_asset(asset.id)

    assert asset.id not in project.assets
    assert workspace.image_strip.count() == 0


def test_figure_board_delete_protected_source_asset_requires_confirmation(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Delete Protected Source")
    image_path = workspace_tmp_path / "protected-delete-source.png"
    Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    asset.metadata["scientific_name"] = "Hydra vulgaris"
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    workspace._delete_source_asset(asset.id)

    assert asset.id in project.assets
    assert panel.source_node_id == node_id

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    workspace._delete_source_asset(asset.id)

    assert asset.id not in project.assets
    assert panel.source_node_id is None
    assert node_id not in project.calibrations
    assert project.source_node_id_for_asset(asset.id) is None


def test_figure_board_refresh_reuses_panel_pixmap_cache(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Cache")
    image_path = workspace_tmp_path / "panel-source.png"
    Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8)).save(image_path)
    asset = ImageAsset(path=str(image_path), display_name="Brachionus.png")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    pixmap = workspace.preview._panel_pixmap(panel, workspace.preview.rect(), asset)
    assert not pixmap.isNull()

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unchanged figure-board refresh must reuse panel pixmaps")

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_preview.render_project_image",
        fail_render,
    )

    workspace.refresh()
    assert workspace.preview._panel_pixmap(panel, workspace.preview.rect(), asset) is pixmap


def test_figure_board_panel_pixmap_defers_first_full_render(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Deferred Render")
    image_path = workspace_tmp_path / "panel-deferred-source.png"
    Image.fromarray(np.full((40, 40, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("first figure-board paint must use a cheap cached thumbnail")

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_preview.render_project_image",
        fail_render,
    )

    pixmap = workspace.preview._panel_pixmap(panel, workspace.preview.rect(), asset)

    assert not pixmap.isNull()
    assert workspace.preview._panel_render_queue


def test_figure_board_unedited_fallback_preserves_source_aspect(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Fallback Aspect")
    image_path = workspace_tmp_path / "wide-panel-source.png"
    Image.fromarray(np.full((40, 100, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("first unedited figure-board paint must not render synchronously")

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_preview.render_project_image",
        fail_render,
    )

    pixmap = workspace.preview._panel_pixmap(panel, QRectF(0.0, 0.0, 200.0, 200.0), asset)

    assert not pixmap.isNull()
    assert pixmap.width() == 200
    assert pixmap.height() == 80


def test_figure_board_edited_fallback_does_not_show_original_pixels(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Edited Fallback")
    image_path = workspace_tmp_path / "white-edited-source.png"
    source_pixels = np.zeros((40, 100, 3), dtype=np.uint8)
    source_pixels[:] = (255, 64, 32)
    Image.fromarray(source_pixels).save(image_path)
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.add_adjustment_layer(
        AdjustmentLayer(
            name="Gamma",
            image_node_id=node_id,
            operation="gamma",
            parameters={"gamma": 2.0},
        )
    )
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("first edited figure-board paint must not render synchronously")

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_preview.render_project_image",
        fail_render,
    )

    pixmap = workspace.preview._panel_pixmap(panel, QRectF(0.0, 0.0, 200.0, 200.0), asset)
    color = pixmap.toImage().pixelColor(pixmap.width() // 2, pixmap.height() // 2)

    assert not pixmap.isNull()
    assert (color.red(), color.green(), color.blue()) != (255, 64, 32)
    assert workspace.preview._panel_render_queue


def test_figure_board_panel_pixmap_queue_updates_cache(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Queued Render")
    image_path = workspace_tmp_path / "panel-queued-source.png"
    Image.fromarray(np.full((40, 40, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    first = workspace.preview._panel_pixmap(panel, workspace.preview.rect(), asset)

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_preview.render_project_image",
        lambda *_args, **_kwargs: np.full((60, 80, 3), 24, dtype=np.uint8),
    )
    workspace.preview._render_next_panel_pixmap()
    second = workspace.preview._panel_pixmap(panel, workspace.preview.rect(), asset)

    assert not second.isNull()
    assert second is not first


def test_figure_board_panel_pixmap_does_not_queue_full_render_while_zooming(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Zoom Cache")
    image_path = workspace_tmp_path / "panel-zoom-source.png"
    Image.fromarray(np.full((40, 40, 3), 180, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    workspace.preview._is_interacting = True

    pixmap = workspace.preview._panel_pixmap(panel, workspace.preview.rect(), asset)

    assert not pixmap.isNull()
    assert not workspace.preview._panel_render_queue


def test_figure_board_filled_preview_avoids_rerender_during_zoom(
    workspace_tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Filled Preview Zoom")
    image_path = workspace_tmp_path / "filled-preview-source.png"
    Image.fromarray(np.full((60, 80, 3), 150, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    board.page = PageFormat("Large", 5000, 3000, PageUnit.PIXEL, dpi=100)
    board.margin_left = 0.0
    board.margin_right = 0.0
    board.margin_top = 0.0
    board.margin_bottom = 0.0
    board.horizontal_gutter = 0.0
    board.vertical_gutter = 0.0
    board.caption = FigureCaption("", "", False, True)
    panel = board.panels[0]
    panel.rect = (0.0, 0.0, 1.0, 1.0)
    panel.source_node_id = node_id
    panel.fill_empty_background = True
    workspace.preview.set_board(board)
    workspace.preview.set_zoom_percent(400)
    workspace.preview._apply_zoom_update()
    workspace.preview._is_interacting = True
    def fail_panel_image(*_args, **_kwargs):
        raise AssertionError("zooming must not rerender filled panel images")

    monkeypatch.setattr(
        "biopic.ui.workspaces.figure_board_preview._panel_image",
        fail_panel_image,
    )

    pixmap = workspace.preview._filled_panel_pixmap(panel, workspace.preview._page_rect(), asset)

    assert not pixmap.isNull()


def test_figure_board_panel_label_color_round_trips() -> None:
    panel = FigurePanel(
        label="a",
        label_color="#ff0000",
        label_font_family="Times New Roman",
        label_font_size_pt=18.0,
        label_bold=False,
        label_italic=True,
        fill_empty_background=True,
        empty_background_path="cached-fill.png",
        empty_background_signature=("node", (0.5, 0.5, 0.8), 12.0, 100, 80),
    )
    restored = FigurePanel.from_dict(panel.to_dict())

    assert restored.label_color == "#ff0000"
    assert restored.label_font_family == "Times New Roman"
    assert restored.label_font_size_pt == 18.0
    assert restored.label_bold is False
    assert restored.label_italic is True
    assert restored.fill_empty_background is True
    assert restored.empty_background_path == "cached-fill.png"
    assert restored.empty_background_signature == ("node", (0.5, 0.5, 0.8), 12.0, 100, 80)


def test_figure_board_panel_transform_controls_update_selected_panel() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Transform")
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]

    workspace._select_panel(panel.id)
    workspace.panel_image_scale.setValue(2.0)
    workspace.panel_offset_x.setValue(25.0)
    workspace.panel_offset_y.setValue(75.0)
    workspace.panel_rotation.setValue(30.0)
    workspace.panel_label_text.setText("Z")
    workspace.panel_label_font_size.setValue(16.0)
    workspace.panel_label_font_style.setCurrentIndex(
        workspace.panel_label_font_style.findData("italic")
    )

    assert panel.crop == (0.25, 0.75, 2.0)
    assert panel.rotation == 30.0
    assert panel.label == "Z"
    assert panel.label_font_size_pt == 16.0
    assert panel.label_bold is False
    assert panel.label_italic is True


def test_figure_board_add_background_button_bakes_filled_panel_image(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Fill Button")
    yy, xx = np.indices((40, 40), dtype=np.uint8)
    pixels = np.zeros((40, 40, 3), dtype=np.uint8)
    pixels[..., 0] = 70 + xx
    pixels[..., 1] = 95 + yy
    pixels[..., 2] = 150
    source_path = workspace_tmp_path / "panel-fill-source.png"
    Image.fromarray(pixels).save(source_path)
    asset = import_images(project, [source_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    board.page = PageFormat("Small", 80, 80, PageUnit.PIXEL, dpi=100)
    board.margin_left = 0.0
    board.margin_right = 0.0
    board.margin_top = 0.0
    board.margin_bottom = 0.0
    board.horizontal_gutter = 0.0
    board.vertical_gutter = 0.0
    board.caption = FigureCaption("", "", False, True)
    panel = board.panels[0]
    panel.rect = (0.0, 0.0, 1.0, 1.0)
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    panel.crop = (0.5, 0.5, 0.65)
    panel.rotation = 33.0
    workspace._select_panel(panel.id)

    workspace.panel_fill_empty_background_button.click()

    assert panel.source_node_id == node_id
    assert panel.fill_empty_background is False
    assert panel.crop == (0.5, 0.5, 0.65)
    assert panel.rotation == 33.0
    assert len(project.assets) == 1
    workspace.image_strip.set_project_assets(project)
    assert [
        workspace.image_strip.item(index).data(256)
        for index in range(workspace.image_strip.count())
    ] == [asset.id]
    assert panel.empty_background_path is not None
    first_background_path = Path(panel.empty_background_path)
    assert first_background_path.exists()
    assert panel.empty_background_signature is not None
    filled = np.asarray(Image.open(first_background_path).convert("RGB"))
    assert filled.shape[:2] == (52, 80)
    assert not np.any(np.all(filled == 255, axis=2))
    assert len(np.unique(filled[:12, :12].reshape(-1, 3), axis=0)) > 3
    source_image = Image.fromarray(pixels).convert("RGBA")
    expected_panel = FigurePanel(
        source_node_id=node_id,
        rect=(0.0, 0.0, 1.0, 1.0),
        crop=(0.5, 0.5, 0.65),
        rotation=33.0,
        label="",
    )
    expected = fill_transparent_regions_with_background(
        np.asarray(_panel_image(source_image, expected_panel, 80, 52, cover_rotation=False))
    )[..., :3]
    old_zoomed = fill_transparent_regions_with_background(
        np.asarray(_panel_image(source_image, expected_panel, 80, 52, cover_rotation=True))
    )[..., :3]
    assert np.array_equal(filled, expected)
    assert not np.array_equal(filled, old_zoomed)
    workspace.preview.set_board(board)
    preview_pixmap = workspace.preview._baked_empty_background_pixmap(
        panel,
        workspace.preview._page_rect(),
    )
    assert not preview_pixmap.isNull()

    workspace.panel_fill_empty_background_button.click()

    assert panel.source_node_id == node_id
    assert panel.crop == (0.5, 0.5, 0.65)
    assert panel.rotation == 33.0
    assert panel.empty_background_path is not None
    assert Path(panel.empty_background_path).exists()
    assert Path(panel.empty_background_path) != first_background_path
    assert not first_background_path.exists()


def test_figure_board_export_reuses_baked_background_at_output_size(
    workspace_tmp_path: Path,
) -> None:
    source_pixels = np.zeros((40, 40, 3), dtype=np.uint8)
    source_path = workspace_tmp_path / "panel-source.png"
    Image.fromarray(source_pixels).save(source_path)
    baked_pixels = np.zeros((52, 80, 3), dtype=np.uint8)
    baked_pixels[..., 0] = 40
    baked_pixels[..., 1] = np.linspace(80, 180, 80, dtype=np.uint8)
    baked_pixels[..., 2] = 210
    baked_path = workspace_tmp_path / "baked-background.png"
    Image.fromarray(baked_pixels).save(baked_path)
    project = Project.new("Baked Fill Export")
    asset = import_images(project, [source_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    panel = FigurePanel(
        source_node_id=node_id,
        rect=(0.0, 0.0, 1.0, 1.0),
        crop=(0.5, 0.5, 0.65),
        rotation=33.0,
        label="",
        empty_background_path=str(baked_path),
        empty_background_signature=(
            node_id,
            (0.5, 0.5, 0.65),
            33.0,
            80,
            52,
        ),
    )
    board = FigureBoard(
        "Board",
        PageFormat("px", 160, 104, PageUnit.PIXEL, dpi=100),
        panels=[panel],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "baked-export.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    assert exported.shape[:2] == (104, 160)
    assert exported[..., 0].mean() == pytest.approx(40, abs=1.0)
    assert exported[..., 2].mean() == pytest.approx(210, abs=1.0)
    assert exported[:, 0, 1].mean() < exported[:, -1, 1].mean()


def test_figure_board_transform_removes_baked_empty_background(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Panel Fill Invalidated")
    image_path = workspace_tmp_path / "panel-fill-invalidated.png"
    Image.fromarray(np.full((20, 20, 3), 150, dtype=np.uint8)).save(image_path)
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    background_path = workspace_tmp_path / "old-empty-background.png"
    Image.fromarray(np.full((8, 8, 3), 120, dtype=np.uint8)).save(background_path)
    panel.empty_background_path = str(background_path)
    panel.empty_background_signature = ("old",)
    workspace._select_panel(panel.id)

    workspace.panel_image_scale.setValue(1.25)

    assert panel.empty_background_path is None
    assert panel.empty_background_signature is None
    assert not background_path.exists()


def test_figure_board_list_switches_between_multiple_boards() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Multiple Boards")
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    first = workspace._current_board()
    assert first is not None
    workspace.panel_count.setValue(2)
    workspace.create_board()
    second = workspace._current_board()
    assert second is not None
    assert first.id != second.id

    workspace._select_board(first.id)

    assert workspace._current_board() is first
    assert workspace.preview._board is first
    assert workspace.board_list.currentItem() is not None
    assert str(workspace.board_list.currentItem().data(256)) == first.id


def test_figure_board_delete_empty_board_without_prompt(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Delete Empty Board")
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    first = workspace._current_board()
    assert first is not None
    workspace.create_board()
    second = workspace._current_board()
    assert second is not None

    def fail_question(*_args: object, **_kwargs: object) -> QMessageBox.StandardButton:
        raise AssertionError("empty figure-board deletion should not prompt")

    monkeypatch.setattr(QMessageBox, "question", fail_question)

    workspace._delete_board(second.id)

    assert second.id not in project.figure_boards
    assert first.id in project.figure_boards
    assert workspace._current_board() is first


def test_figure_board_delete_assigned_board_requires_confirmation(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Delete Assigned Board")
    asset = ImageAsset(path=str(Path(__file__)), display_name="Brachionus.png")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    workspace.assign_image_to_panel(board.id, board.panels[0].id, node_id)
    assert any(
        node.operation == "figure_board" and node.parameters.get("board_id") == board.id
        for node in project.graph.nodes.values()
    )

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    workspace._delete_board(board.id)
    assert board.id in project.figure_boards

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    workspace._delete_board(board.id)

    assert board.id not in project.figure_boards
    assert not any(
        node.operation == "figure_board" and node.parameters.get("board_id") == board.id
        for node in project.graph.nodes.values()
    )


def test_figure_board_preview_direct_transform_helpers() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Direct Transform")
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.preview.set_board(board)
    workspace.preview._selected_panel_id = panel.id
    rect = workspace.preview._panel_rect(
        panel, workspace.preview._printable_rect(workspace.preview._page_rect())
    )

    assert workspace.preview._handle_at(rect.topLeft(), rect).startswith("scale")
    rotate_handle = workspace.preview._rotate_handle(rect)
    assert workspace.preview._handle_at(rotate_handle.center(), rect) == "rotate"


def test_figure_board_overlay_text_scales_with_panel() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Overlay Scale")
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    panel = board.panels[0]
    workspace.preview.set_board(board)
    page_rect = workspace.preview._page_rect()
    small_rect = workspace.preview._panel_rect(
        panel, workspace.preview._printable_rect(page_rect)
    )
    workspace.preview.set_zoom_percent(100)
    workspace.preview._apply_zoom_update()
    large_page_rect = workspace.preview._page_rect()
    large_rect = workspace.preview._panel_rect(
        panel, workspace.preview._printable_rect(large_page_rect)
    )

    assert int(round(12 * small_rect.width() / 800.0)) <= int(
        round(12 * large_rect.width() / 800.0)
    )
    large_font_size = workspace.preview._paper_font(large_page_rect, 10.0).pixelSize()
    page_font_size = workspace.preview._paper_font(page_rect, 10.0).pixelSize()
    assert large_font_size > page_font_size


def test_figure_board_preview_uses_gutters_and_physical_zoom() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Preview Geometry")
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))
    board.horizontal_gutter = 10.0
    workspace.preview.set_board(board)
    workspace.preview.set_zoom_percent(100)
    page_rect = workspace.preview._page_rect()
    printable = workspace.preview._printable_rect(page_rect)
    panel_rect = workspace.preview._panel_rect(board.panels[0], printable)

    assert page_rect.width() < board.page.pixel_dimensions()[0]
    assert panel_rect.width() < board.panels[0].rect[2] * printable.width()


def test_figure_board_preview_resizes_widget_to_full_canvas() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Preview Canvas Size")
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))

    workspace.preview.set_board(board)
    workspace.preview.set_zoom_percent(150)
    workspace.preview._apply_zoom_update()
    size = workspace.preview.size()
    hint = workspace.preview.sizeHint()
    page_rect = workspace.preview._page_rect()

    assert size == hint
    assert page_rect.right() <= size.width()
    assert page_rect.bottom() <= size.height()


def test_figure_board_drop_uses_asset_source_node() -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Drop Image")
    asset = ImageAsset(path=str(Path(__file__)), display_name="annotated.png")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = next(iter(project.figure_boards.values()))

    workspace._image_dropped_on_preview(board.panels[0].id, asset.id)

    assert board.panels[0].source_node_id == node_id


def test_figure_board_edit_annotation_moves_annotation_and_measurement_text(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "board-overlay-source.png"
    Image.fromarray(np.full((80, 100, 3), 180, dtype=np.uint8)).save(image_path)
    project = Project.new("Board Overlay Move")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    annotation = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.05, 0.05)],
        text="A",
    )
    project.annotations[annotation.id] = annotation
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(20, 40), Point(60, 40)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(100, 50, "um"),
        label="Body",
    )
    project.measurements[measurement.id] = measurement
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    board.page = PageFormat("px", 1000, 800, PageUnit.PIXEL, dpi=100)
    board.margin_left = 0.0
    board.margin_right = 0.0
    board.margin_top = 0.0
    board.margin_bottom = 0.0
    board.caption = FigureCaption("", "", False, True)
    panel = board.panels[0]
    panel.rect = (0.0, 0.0, 1.0, 1.0)
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    workspace.preview.resize(1400, 1100)
    workspace.preview.set_board(board)
    workspace.preview.set_annotation_edit_enabled(True)

    page_rect = workspace.preview._page_rect()
    panel_rect = workspace.preview._panel_rect(
        panel,
        workspace.preview._content_rect(workspace.preview._printable_rect(page_rect)),
    )
    geometry = workspace.preview._panel_image_hit_geometry(panel, panel_rect)
    assert geometry is not None
    transform, image_rect, _source_size = geometry
    label_start = transform.map(
        QPointF(
            image_rect.x() + 46.0 / 100.0 * image_rect.width(),
            image_rect.y() + 46.0 / 80.0 * image_rect.height(),
        )
    )
    drag = workspace.preview._overlay_at(label_start)
    assert drag is not None
    assert drag["kind"] == "measurement"
    drag["start_position"] = label_start
    workspace.preview._overlay_drag = drag
    workspace.preview._move_overlay_drag(label_start + QPointF(15.0, 0.0))

    assert measurement.label_offset[0] > 0.0
    assert measurement.value_offset == (0.0, 0.0)

    line_start = transform.map(
        QPointF(
            image_rect.x() + 20.0 / 100.0 * image_rect.width(),
            image_rect.y() + 40.0 / 80.0 * image_rect.height(),
        )
    )
    drag = workspace.preview._overlay_at(line_start)
    assert drag is not None
    assert drag["kind"] == "measurement"
    assert drag["target"] == "geometry"
    drag["start_position"] = line_start
    workspace.preview._overlay_drag = drag
    workspace.preview._move_overlay_drag(line_start + QPointF(0.0, 20.0))

    assert measurement.points[0].y > 40.0
    assert measurement.points[1].y > 40.0

    annotation_start = transform.map(
        QPointF(
            image_rect.x() + annotation.points[0][0] * image_rect.width(),
            image_rect.y() + annotation.points[0][1] * image_rect.height(),
        )
    )
    drag = workspace.preview._overlay_at(annotation_start)
    assert drag is not None
    assert drag["kind"] == "annotation"
    drag["start_position"] = annotation_start
    workspace.preview._overlay_drag = drag
    workspace.preview._move_overlay_drag(annotation_start + QPointF(18.0, 12.0))

    assert annotation.points[0][0] > 0.05
    assert annotation.points[0][1] > 0.05
    assert panel.crop == (0.5, 0.5, 1.0)


def test_figure_board_delete_removes_selected_annotation_overlay(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "board-delete-annotation-source.png"
    Image.fromarray(np.full((80, 100, 3), 180, dtype=np.uint8)).save(image_path)
    project = Project.new("Board Delete Annotation")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    annotation = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.2, 0.2)],
        text="A",
    )
    project.annotations[annotation.id] = annotation
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    workspace.preview.set_annotation_edit_enabled(True)
    workspace.preview._selected_overlay = {
        "kind": "annotation",
        "id": annotation.id,
        "panel_id": panel.id,
    }

    workspace.preview.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    )

    assert annotation.id not in project.annotations
    assert panel.source_node_id == node_id


def test_figure_board_annotation_text_hit_matches_drawn_text_rect(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "board-text-hit-source.png"
    Image.fromarray(np.full((80, 100, 3), 180, dtype=np.uint8)).save(image_path)
    project = Project.new("Board Text Hit")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    annotation = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.08, 0.08)],
        text="Long label",
        size=24.0,
    )
    project.annotations[annotation.id] = annotation
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    board.page = PageFormat("px", 1000, 800, PageUnit.PIXEL, dpi=100)
    board.margin_left = 0.0
    board.margin_right = 0.0
    board.margin_top = 0.0
    board.margin_bottom = 0.0
    board.caption = FigureCaption("", "", False, True)
    panel = board.panels[0]
    panel.rect = (0.0, 0.0, 1.0, 1.0)
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    workspace.preview.resize(1400, 1100)
    workspace.preview.set_board(board)

    page_rect = workspace.preview._page_rect()
    panel_rect = workspace.preview._panel_rect(
        panel,
        workspace.preview._content_rect(workspace.preview._printable_rect(page_rect)),
    )
    geometry = workspace.preview._panel_image_hit_geometry(panel, panel_rect)
    assert geometry is not None
    transform, image_rect, _source_size = geometry
    anchor = transform.map(
        QPointF(
            image_rect.x() + annotation.points[0][0] * image_rect.width(),
            image_rect.y() + annotation.points[0][1] * image_rect.height(),
        )
    )
    font_size = max(2, int(round(annotation.size * workspace.preview._board_zoom_scale())))
    text_rect = _annotation_text_rect(
        anchor,
        QFont(safe_font_family(annotation.font), font_size),
        annotation.text,
    )
    hit_position = QPointF(text_rect.right() - 2.0, text_rect.top() + 2.0)

    drag = workspace.preview._overlay_at(hit_position)

    assert drag is not None
    assert drag["kind"] == "annotation"
    assert drag["id"] == annotation.id


def test_figure_board_global_overlay_style_updates_annotations_and_measurements(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "board-global-overlay-source.png"
    Image.fromarray(np.full((80, 100, 3), 180, dtype=np.uint8)).save(image_path)
    project = Project.new("Board Global Overlay Style")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    annotation = AnnotationObject(
        image_node_id=node_id,
        kind=AnnotationKind.TEXT,
        points=[(0.1, 0.1)],
        text="mx",
        size=8.0,
    )
    project.annotations[annotation.id] = annotation
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(20, 40), Point(60, 40)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(100, 50, "um"),
        label="Body",
        font_size=9.0,
    )
    project.measurements[measurement.id] = measurement
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    workspace._selected_figure_overlay = None
    workspace.figure_edit_target_combo.setCurrentIndex(
        workspace.figure_edit_target_combo.findData("overlays")
    )

    workspace.panel_label_font_size.setValue(22.0)

    assert annotation.size == 22.0
    assert measurement.font_size == 22.0


def test_figure_board_click_does_not_clear_empty_background(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    image_path = workspace_tmp_path / "click-background-source.png"
    background_path = workspace_tmp_path / "baked-background.png"
    Image.fromarray(np.full((32, 32, 3), 180, dtype=np.uint8)).save(image_path)
    Image.fromarray(np.full((16, 16, 3), 160, dtype=np.uint8)).save(background_path)
    project = Project.new("Panel Background Click")
    asset = import_images(project, [image_path])[0]
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    panel = board.panels[0]
    workspace.assign_image_to_panel(board.id, panel.id, node_id)
    panel.empty_background_path = str(background_path)
    panel.empty_background_signature = ("signature",)
    transformed = []
    workspace.preview.panelTransformed.connect(lambda panel_id: transformed.append(panel_id))
    workspace.preview._selected_panel_id = panel.id
    workspace.preview._selected_panel_ids = {panel.id}
    workspace.preview._drag_mode = "move"
    workspace.preview._drag_start = QPointF(50.0, 50.0)
    workspace.preview._drag_start_crop = panel.crop
    workspace.preview._drag_panel_changed = False

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(50.0, 50.0),
        QPointF(50.0, 50.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    workspace.preview.mouseReleaseEvent(release)

    assert transformed == []
    assert panel.empty_background_path == str(background_path)
    assert panel.empty_background_signature == ("signature",)


def test_page_format_pixel_dimensions() -> None:
    page = PageFormat("Letter", 8.5, 11, PageUnit.INCH, 300)

    assert page.pixel_dimensions() == (2550, 3300)


def test_preflight_reports_empty_board_and_duplicate_definitions() -> None:
    project = Project.new("Preflight")
    first = AnnotationDefinition("MX", "mastax")
    second = AnnotationDefinition("MX", "different")
    project.annotation_definitions[first.id] = first
    project.annotation_definitions[second.id] = second
    board = FigureBoard("Board", PageFormat("px", 100, 100, PageUnit.PIXEL), [])

    issues = preflight_project(project, board)
    codes = {issue.code for issue in issues}

    assert "missing_images" in codes
    assert "duplicate_abbreviation" in codes
    assert "empty_board" in codes


def test_raster_export_image(workspace_tmp_path: Path) -> None:
    image = np.arange(25, dtype=np.uint8).reshape(5, 5)
    path = workspace_tmp_path / "export.png"

    export_image(image, path)

    assert path.exists()
    assert path.stat().st_size > 0


def test_raster_export_image_writes_jpeg(workspace_tmp_path: Path) -> None:
    image = np.full((5, 5, 3), 128, dtype=np.uint8)
    path = workspace_tmp_path / "export.jpg"

    export_image(image, path)

    exported = Image.open(path)
    assert exported.format == "JPEG"


def test_raster_export_preserve_precision_rejects_lossy_non_tiff(
    workspace_tmp_path: Path,
) -> None:
    image = np.full((5, 5), 1024, dtype=np.uint16)
    path = workspace_tmp_path / "export.png"

    with pytest.raises(ValueError, match="Use TIFF export"):
        export_image(image, path, precision_policy="preserve")


def test_project_image_export_embeds_source_metadata_with_overlays(
    workspace_tmp_path: Path,
) -> None:
    source_path = workspace_tmp_path / "metadata-source.png"
    Image.fromarray(np.full((20, 30, 3), 240, dtype=np.uint8)).save(source_path)
    project = Project.new("Project Image Metadata")
    asset = ImageAsset(
        path=str(source_path),
        width=30,
        height=20,
        dtype="uint8",
        metadata={
            "scientific_name": "Brachionus calyciflorus",
            "sex": "female",
            "camera": "Axiocam",
        },
    )
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.calibrations[node_id] = Calibration.from_known_distance(10, 5, "um")
    project.annotations["label"] = AnnotationObject(
        node_id,
        AnnotationKind.TEXT,
        [(0.1, 0.1)],
        text="Label",
        color="#000000",
    )
    output_path = workspace_tmp_path / "project-image.tif"

    export_project_image(project, node_id, output_path)

    exported = read_image_asset(output_path)
    assert exported.asset.metadata["scientific_name"] == "Brachionus calyciflorus"
    assert exported.asset.metadata["sex"] == "female"
    assert exported.asset.metadata["camera"] == "Axiocam"
    assert exported.asset.metadata["physical_pixel_size"] == 0.5
    with tifffile.TiffFile(output_path) as tif:
        page = tif.pages[0]
        assert not page.description.startswith('{"shape"')
        assert "Brachionus calyciflorus" in page.description
        assert "female" in page.description
        xmp = page.tags[700].value.decode("utf-8")
        assert "Brachionus calyciflorus" in xmp
        assert "female" in xmp
        assert "physical_pixel_size" in xmp
        assert "biopic:rembi" in xmp
        assert "image_acquisition" in xmp
        assert "detector" in xmp
        assert "image_data" in xmp


def test_figure_board_export_embeds_panel_source_metadata(
    workspace_tmp_path: Path,
) -> None:
    source_path = workspace_tmp_path / "figure-metadata-source.png"
    Image.fromarray(np.full((12, 16, 3), 180, dtype=np.uint8)).save(source_path)
    project = Project.new("Figure Metadata")
    asset = ImageAsset(
        path=str(source_path),
        width=16,
        height=12,
        dtype="uint8",
        metadata={"scientific_name": "Hydra vulgaris", "collector": "Lee"},
    )
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.calibrations[node_id] = Calibration.from_known_distance(20, 10, "um")
    board = FigureBoard(
        "Board",
        PageFormat("px", 80, 60, PageUnit.PIXEL, dpi=100),
        panels=[FigurePanel(source_node_id=node_id, label="A")],
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "figure-metadata.tif"

    export_project_figure_board(project, board, output_path)

    exported = read_image_asset(output_path)
    assert exported.asset.metadata["scientific_name"] == "Hydra vulgaris"
    assert exported.asset.metadata["collector"] == "Lee"
    assert "figure_sources" in exported.asset.metadata
    assert exported.asset.metadata["physical_pixel_size"] == 0.5
    with tifffile.TiffFile(output_path) as tif:
        page = tif.pages[0]
        assert not page.description.startswith('{"shape"')
        assert "Hydra vulgaris" in page.description
        xmp = page.tags[700].value.decode("utf-8")
        assert "Hydra vulgaris" in xmp
        assert "figure_sources" in xmp


def test_figure_board_export_preserves_layout_gutters_labels_and_transforms(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.zeros((24, 24, 3), dtype=np.uint8)
    pixels[:12, :12] = (255, 0, 0)
    pixels[:, 12:] = (0, 128, 255)
    pixels[12:, :12] = (0, 255, 0)
    source_path = workspace_tmp_path / "source.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Board Export")
    asset = ImageAsset(path=str(source_path), width=24, height=24, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    board = FigureBoard(
        "Board",
        PageFormat("px", 200, 100, PageUnit.PIXEL, dpi=100),
        panels=[
            FigurePanel(
                source_node_id=node_id,
                rect=(0.0, 0.0, 0.5, 1.0),
                crop=(0.5, 0.5, 1.4),
                rotation=90.0,
                label="A",
                label_color="#000000",
                label_offset=(0.05, 0.05),
            ),
            FigurePanel(rect=(0.5, 0.0, 0.5, 1.0), label="B"),
        ],
        horizontal_gutter=2.54,
        vertical_gutter=0.0,
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    assert exported.shape[:2] == (100, 200)
    assert np.all(exported[20, 100] == 255)
    assert np.any(np.all(exported[:35, :45] < 40, axis=2))
    assert np.any(exported[:92, :95] != 255)
    assert len(np.unique(exported[:92, :95].reshape(-1, 3), axis=0)) > 3


def test_figure_board_export_draws_measurements_without_changing_physical_value(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.full((60, 80, 3), 255, dtype=np.uint8)
    source_path = workspace_tmp_path / "measurement-source.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Board Measurement Export")
    asset = ImageAsset(path=str(source_path), width=80, height=60, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(10, 30), Point(70, 30)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(20, 10, "um"),
        label="Body",
        display_unit="µm",
        color="#000000",
    )
    project.measurements[measurement.id] = measurement
    board = FigureBoard(
        "Board",
        PageFormat("px", 160, 120, PageUnit.PIXEL, dpi=100),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="")],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    before = measurement.length_display("µm")
    output_path = workspace_tmp_path / "measurement-board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    assert measurement.length_display("µm") == before
    assert np.any(np.all(exported < 20, axis=2))


def test_figure_board_export_transforms_measurements_with_panel_image(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.full((60, 80, 3), 255, dtype=np.uint8)
    source_path = workspace_tmp_path / "rotated-measurement-source.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Rotated Board Measurement")
    asset = ImageAsset(path=str(source_path), width=80, height=60, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(10, 30), Point(70, 30)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(20, 10, "um"),
        display_unit="px",
        color="#ff0000",
        line_width=5.0,
        show_label=False,
    )
    project.measurements[measurement.id] = measurement
    board = FigureBoard(
        "Board",
        PageFormat("px", 160, 120, PageUnit.PIXEL, dpi=100),
        panels=[
            FigurePanel(
                source_node_id=node_id,
                rect=(0.0, 0.0, 1.0, 1.0),
                rotation=90.0,
                label="",
            )
        ],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "rotated-measurement-board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    red_mask = (
        (exported[:, :, 0] > 220)
        & (exported[:, :, 1] < 40)
        & (exported[:, :, 2] < 40)
    )
    assert red_mask[:, 76:84].sum() > 80
    assert red_mask[57:64, 15:70].sum() < 20
    assert red_mask[57:64, 90:145].sum() < 100


def test_figure_board_export_scales_measurement_stroke_and_text_by_dpi(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.full((60, 80, 3), 255, dtype=np.uint8)
    source_path = workspace_tmp_path / "measurement-size-source.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Board Measurement Size")
    asset = ImageAsset(path=str(source_path), width=80, height=60, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(10, 30), Point(70, 30)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(20, 10, "um"),
        display_unit="px",
        color="#000000",
        line_width=3.0,
        font_size=14.0,
        show_label=False,
    )
    project.measurements[measurement.id] = measurement
    board = FigureBoard(
        "Board",
        PageFormat("px", 240, 180, PageUnit.PIXEL, dpi=300),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="")],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "measurement-size-board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    ink = np.all(exported < 40, axis=2)
    vertical_profile = ink[:, 120]
    assert vertical_profile.sum() >= 10
    assert ink[:, 135:190].sum() > 150


def test_figure_board_export_uses_preview_baseline_for_measurement_values(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.full((60, 80, 3), 255, dtype=np.uint8)
    source_path = workspace_tmp_path / "measurement-baseline-source.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Board Measurement Baseline")
    asset = ImageAsset(path=str(source_path), width=80, height=60, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(10, 30), Point(70, 30)],
        image_node_id=node_id,
        calibration=Calibration.from_known_distance(20, 10, "um"),
        display_unit="px",
        color="#000000",
        line_width=1.0,
        font_size=14.0,
        show_label=False,
    )
    project.measurements[measurement.id] = measurement
    board = FigureBoard(
        "Board",
        PageFormat("px", 160, 120, PageUnit.PIXEL, dpi=72),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="")],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "measurement-baseline-board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    ink = np.all(exported < 40, axis=2)
    text_band = ink[:, 90:150]
    rows = np.where(text_band.sum(axis=1) > 0)[0]
    assert rows.size > 0
    assert rows.max() <= 93


def test_figure_board_export_scales_scale_bar_text_and_thickness_by_dpi(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.full((80, 120, 3), 220, dtype=np.uint8)
    source_path = workspace_tmp_path / "scale-size-source.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Board Scale Size")
    asset = ImageAsset(path=str(source_path), width=120, height=80, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    project.scale_bars["scale"] = ScaleBar(
        image_node_id=node_id,
        physical_length=50.0,
        unit="um",
        calibration=Calibration.from_known_distance(100, 50, "um"),
        foreground="#000000",
        width_px=3.0,
        font_size=14.0,
    )
    board = FigureBoard(
        "Board",
        PageFormat("px", 300, 200, PageUnit.PIXEL, dpi=300),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="")],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "scale-size-board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    ink = np.all(exported < 40, axis=2)
    assert ink[145:170].sum(axis=1).max() >= 70
    assert ink[86:157].sum() > 1000


def test_figure_board_measurement_text_offsets_are_image_scaled() -> None:
    measurement = Measurement(
        kind=MeasurementKind.LINE,
        points=[Point(0, 0), Point(20, 0)],
        image_node_id="node",
        calibration=Calibration.from_known_distance(10, 10, "um"),
        label="Body",
        label_offset=(10.0, 4.0),
        value_offset=(20.0, 8.0),
    )
    base = QPointF(100.0, 50.0)

    items = _measurement_preview_text_items(measurement, base, 0.5, 2.0)
    label, label_pos, _ = items[0]
    value, value_pos, _ = items[1]

    assert label == "Body"
    assert label_pos.x() == 105.0
    assert label_pos.y() == 58.0
    assert value.endswith("µm")
    assert value_pos.x() == 110.0
    assert value_pos.y() == 102.0


def test_figure_board_scale_bar_adapts_to_panel_size() -> None:
    board = FigureBoard(
        "Board",
        PageFormat("px", 100, 50, PageUnit.PIXEL, dpi=100),
        panels=[],
        scale_bar_min_fraction=0.2,
        scale_bar_max_fraction=0.4,
        scale_bar_use_halving=True,
        scale_bar_use_snap_lengths=False,
    )
    physical, pixels = adjusted_scale_bar_length(
        board,
        physical_length=100,
        pixel_length=100,
        display_scale=1.0,
        panel_length_px=100,
    )

    assert physical == 25
    assert pixels == 25


def test_figure_board_hides_repeated_scale_bar_value_labels() -> None:
    from biopic.models.figure_board import common_scale_bar_value_key

    calibration = Calibration.from_known_distance(100, 50, "um")
    bars = [
        ScaleBar("node-a", 50, "um", calibration),
        ScaleBar("node-b", 50, "um", calibration),
        ScaleBar("node-c", 20, "um", calibration),
    ]

    assert common_scale_bar_value_key(bars) == (50.0, "\u03bcm")


def test_figure_board_common_scale_bar_value_is_board_wide() -> None:
    calibration = Calibration.from_known_distance(100, 50, "um")
    project = Project.new("Common Scale")
    for node_id in ("node-a", "node-b", "node-c"):
        project.scale_bars[node_id] = ScaleBar(node_id, 50, "um", calibration)
    image_lookup = {
        node_id: np.full((80, 100, 3), 180, dtype=np.uint8)
        for node_id in ("node-a", "node-b", "node-c")
    }
    board = FigureBoard(
        "Board",
        PageFormat("px", 600, 100, PageUnit.PIXEL, dpi=100),
        panels=[
            FigurePanel(source_node_id="node-a", rect=(0.0, 0.0, 1.0 / 3.0, 1.0)),
            FigurePanel(source_node_id="node-b", rect=(1.0 / 3.0, 0.0, 1.0 / 3.0, 1.0)),
            FigurePanel(source_node_id="node-c", rect=(2.0 / 3.0, 0.0, 1.0 / 3.0, 1.0)),
        ],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        horizontal_gutter=0.0,
        vertical_gutter=0.0,
        scale_bar_min_fraction=0.0,
        scale_bar_max_fraction=1.0,
    )

    common = _common_displayed_scale_bar_value_key(
        project,
        board,
        image_lookup,
        (0, 0, 600, 100),
        0,
        0,
    )

    assert common == (50.0, "\u03bcm")


def test_figure_board_hidden_common_scale_bar_value_skips_text() -> None:
    class RecordingDraw:
        def __init__(self) -> None:
            self.lines = []
            self.texts = []

        def line(self, coordinates, *, fill, width):
            self.lines.append((coordinates, fill, width))

        def textbbox(self, _xy, text, *, font):
            return (0, 0, len(text) * 6, 12)

        def text(self, xy, text, *, fill, font):
            self.texts.append((xy, text, fill, font))

    calibration = Calibration.from_known_distance(100, 50, "um")
    project = Project.new("Hidden Common Scale")
    scale_bar = ScaleBar("node", 50, "um", calibration)
    project.scale_bars[scale_bar.id] = scale_bar
    board = FigureBoard(
        "Board",
        PageFormat("px", 100, 80, PageUnit.PIXEL, dpi=100),
        panels=[FigurePanel(source_node_id="node")],
        scale_bar_min_fraction=0.0,
        scale_bar_max_fraction=1.0,
    )
    draw = RecordingDraw()

    _draw_panel_scale_bars(
        draw,
        project,
        board,
        board.panels[0],
        Image.fromarray(np.full((80, 100, 3), 180, dtype=np.uint8)),
        (0, 0, 100, 80),
        (50.0, "\u03bcm"),
    )

    assert draw.lines
    assert draw.texts == []


def test_figure_board_caption_mentions_common_scale_only_when_hidden(
    workspace_tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    project = Project.new("Caption Common Scale")
    paths = []
    for index in range(3):
        path = workspace_tmp_path / f"caption-scale-{index}.png"
        Image.fromarray(np.full((80, 100, 3), 180, dtype=np.uint8)).save(path)
        paths.append(path)
    assets = import_images(project, paths)
    workspace = FigureBoardWorkspace(project)
    workspace.create_board()
    board = workspace._current_board()
    assert board is not None
    board.panels = [
        FigurePanel(
            source_node_id=project.source_node_id_for_asset(asset.id),
            label=chr(ord("A") + index),
        )
        for index, asset in enumerate(assets)
    ]
    calibration = Calibration.from_known_distance(100, 50, "um")
    for panel in board.panels:
        assert panel.source_node_id is not None
        project.scale_bars[panel.source_node_id] = ScaleBar(
            panel.source_node_id,
            50,
            "um",
            calibration,
        )

    board.hide_common_scale_bar_value = False
    workspace._update_caption(board)
    assert "Scale bars:" not in board.caption.auto_generated

    board.hide_common_scale_bar_value = True
    workspace._update_caption(board)
    assert "Scale bars: 50 \u03bcm." in board.caption.auto_generated

    workspace._sync_scale_bar_controls()
    workspace.scale_bar_hide_common_value.setChecked(False)
    assert "Scale bars:" not in board.caption.auto_generated
    workspace.scale_bar_hide_common_value.setChecked(True)
    assert "Scale bars: 50 \u03bcm." in board.caption.auto_generated


def test_figure_board_hide_common_scale_bar_value_round_trips() -> None:
    board = FigureBoard(
        "Board",
        PageFormat("px", 100, 50, PageUnit.PIXEL, dpi=100),
        hide_common_scale_bar_value=True,
    )

    restored = FigureBoard.from_dict(board.to_dict())

    assert restored.hide_common_scale_bar_value is True


def test_figure_board_export_rotation_preserves_panel_scale(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.zeros((64, 64, 3), dtype=np.uint8)
    pixels[:] = (30, 90, 160)
    source_path = workspace_tmp_path / "rotated.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Rotated Board")
    asset = ImageAsset(path=str(source_path), width=64, height=64, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    board = FigureBoard(
        "Rotated",
        PageFormat("px", 120, 120, PageUnit.PIXEL, dpi=100),
        panels=[
            FigurePanel(
                source_node_id=node_id,
                rect=(0.0, 0.0, 1.0, 1.0),
                crop=(0.5, 0.5, 1.0),
                rotation=35.0,
                label="",
            )
        ],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "rotated_board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    white_fraction = float(np.mean(np.all(exported == 255, axis=2)))
    assert white_fraction > 0.05
    assert np.any(np.all(exported[40:80, 40:80] == (30, 90, 160), axis=2))


def test_figure_board_fill_empty_background_extrapolates_rotated_holes(
    workspace_tmp_path: Path,
) -> None:
    yy, xx = np.indices((48, 48))
    pixels = np.zeros((48, 48, 3), dtype=np.uint8)
    pixels[..., 0] = 70 + (xx % 7) * 4
    pixels[..., 1] = 110 + (yy % 5) * 5
    pixels[..., 2] = 155
    source_path = workspace_tmp_path / "rotated-fill-source.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Rotated Fill Board")
    asset = ImageAsset(path=str(source_path), width=48, height=48, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    board = FigureBoard(
        "Rotated Fill",
        PageFormat("px", 100, 100, PageUnit.PIXEL, dpi=100),
        panels=[
            FigurePanel(
                source_node_id=node_id,
                rect=(0.0, 0.0, 1.0, 1.0),
                crop=(0.5, 0.5, 0.65),
                rotation=33.0,
                label="",
                fill_empty_background=True,
            )
        ],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "rotated_fill_board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    corner_sample = np.concatenate(
        [
            exported[:12, :12].reshape(-1, 3),
            exported[:12, -12:].reshape(-1, 3),
            exported[-12:, :12].reshape(-1, 3),
            exported[-12:, -12:].reshape(-1, 3),
        ],
        axis=0,
    )
    assert not np.any(np.all(corner_sample == 255, axis=1))
    assert len(np.unique(corner_sample, axis=0)) > 3


def test_transparent_fill_continues_edge_gradient() -> None:
    yy, xx = np.indices((80, 80), dtype=np.float32)
    rgba = np.zeros((80, 80, 4), dtype=np.uint8)
    rgba[..., 0] = np.clip(60 + xx * 1.1 + yy * 0.35, 0, 255).astype(np.uint8)
    rgba[..., 1] = np.clip(95 + xx * 0.2 + yy * 0.9, 0, 255).astype(np.uint8)
    rgba[..., 2] = 150
    rgba[..., 3] = 255
    empty_corner = (xx + yy) < 28
    rgba[empty_corner, 3] = 0
    rgba[empty_corner, :3] = 0

    filled = fill_transparent_regions_with_background(rgba)

    assert np.all(filled[empty_corner, 3] == 255)
    assert int(filled[2, 2, 0]) < int(filled[20, 10, 0])
    assert int(filled[2, 2, 1]) < int(filled[10, 20, 1])
    assert int(filled[2, 2, 0]) < 82
    assert int(filled[2, 2, 1]) < 116


def test_transparent_fill_smooths_rotated_edge_banding() -> None:
    yy, xx = np.indices((96, 160), dtype=np.float32)
    rgba = np.zeros((96, 160, 4), dtype=np.uint8)
    rgba[..., 0] = np.clip(95 + xx * 0.18 + yy * 0.08, 0, 255).astype(np.uint8)
    rgba[..., 1] = np.clip(105 + xx * 0.11 + yy * 0.16, 0, 255).astype(np.uint8)
    rgba[..., 2] = np.clip(120 + xx * 0.20 - yy * 0.05, 0, 255).astype(np.uint8)
    stripe = ((xx.astype(np.int32) // 4) % 2) * 18
    rgba[:58, :, :3] = np.clip(rgba[:58, :, :3].astype(np.int16) + stripe[:58, :, None], 0, 255)
    rgba[..., 3] = 255
    rgba[58:, :, 3] = 0
    rgba[58:, :, :3] = 0

    filled = fill_transparent_regions_with_background(rgba)
    empty_fill = filled[70:90, :, :3].astype(np.float32)
    adjacent_column_delta = np.abs(np.diff(empty_fill, axis=1)).mean(axis=(0, 2))
    row_gradient = empty_fill[-1].mean(axis=0) - empty_fill[0].mean(axis=0)

    assert np.all(filled[58:, :, 3] == 255)
    assert float(np.percentile(adjacent_column_delta, 95.0)) < 7.0
    assert float(np.max(np.abs(row_gradient))) > 1.0


def test_figure_board_export_writes_caption_sidecars_not_raster_caption(
    workspace_tmp_path: Path,
) -> None:
    pixels = np.full((16, 16, 3), 90, dtype=np.uint8)
    source_path = workspace_tmp_path / "caption.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Caption Board")
    asset = ImageAsset(path=str(source_path), width=16, height=16, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    board = FigureBoard(
        "Caption Board",
        PageFormat("px", 80, 80, PageUnit.PIXEL, dpi=100),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="")],
        margin_left=0.0,
        margin_right=0.0,
        margin_top=0.0,
        margin_bottom=0.0,
        caption=FigureCaption("Auto $E=mc^2$", "", False, False),
    )
    output_path = workspace_tmp_path / "caption_board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    assert exported.shape[:2] == (52, 80)
    assert np.all(exported[-1, :] != 255)
    caption_text = output_path.with_suffix(".caption.txt").read_text(encoding="utf-8")
    caption_tex = output_path.with_suffix(".caption.tex").read_text(encoding="utf-8")
    assert caption_text.strip() == "Auto $E=mc^2$"
    assert "\\caption{Auto $E=mc^2$}" in caption_tex


def test_figure_board_export_omits_page_margins(workspace_tmp_path: Path) -> None:
    pixels = np.full((16, 16, 3), (80, 120, 180), dtype=np.uint8)
    source_path = workspace_tmp_path / "margins.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("Margin Board")
    asset = ImageAsset(path=str(source_path), width=16, height=16, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    board = FigureBoard(
        "Margin Board",
        PageFormat("px", 100, 80, PageUnit.PIXEL, dpi=100),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="")],
        margin_left=2.54,
        margin_right=2.54,
        margin_top=2.54,
        margin_bottom=2.54,
        caption=FigureCaption("", "", False, True),
    )
    output_path = workspace_tmp_path / "margin_board.png"

    export_project_figure_board(project, board, output_path)

    exported = np.asarray(Image.open(output_path).convert("RGB"))
    assert exported.shape[:2] == (60, 80)
    assert np.any(exported[:, 0] != 255)
    assert np.any(exported[0, :] != 255)


def test_figure_board_latex_export_creates_tex_and_image(workspace_tmp_path: Path) -> None:
    pixels = np.full((16, 16, 3), 120, dtype=np.uint8)
    source_path = workspace_tmp_path / "latex.png"
    Image.fromarray(pixels).save(source_path)
    project = Project.new("LaTeX Board")
    asset = ImageAsset(path=str(source_path), width=16, height=16, dtype="uint8")
    project.add_asset(asset)
    node_id = project.source_node_id_for_asset(asset.id)
    assert node_id is not None
    board = FigureBoard(
        "LaTeX Board",
        PageFormat("px", 80, 80, PageUnit.PIXEL, dpi=100),
        panels=[FigurePanel(source_node_id=node_id, rect=(0.0, 0.0, 1.0, 1.0), label="")],
        caption=FigureCaption(r"\textbf{Caption}", "", False, False),
    )
    tex_path = workspace_tmp_path / "board.tex"

    export_project_figure_board_latex(project, board, tex_path)

    tex = tex_path.read_text(encoding="utf-8")
    assert (workspace_tmp_path / "board.png").exists()
    assert r"\includegraphics[width=\textwidth]{board.png}" in tex
    assert r"\caption{\textbf{Caption}}" in tex


def test_project_round_trips_annotations_and_boards(workspace_tmp_path: Path) -> None:
    project = Project.new("Round Trip")
    definition = AnnotationDefinition("MX", "mastax")
    annotation = AnnotationObject("node", AnnotationKind.TEXT, [(0.1, 0.1)], "MX", definition.id)
    board = FigureBoard(
        "Board",
        PageFormat("A4", 210, 297, PageUnit.MM),
        panels=grid_panels(2),
        margin_left=6,
        margin_right=7,
        label_mode=PanelLabelMode.NUMERICAL,
        caption=FigureCaption("Auto", "Manual", True, True),
        journal_preset="Nature",
    )
    project.annotation_definitions[definition.id] = definition
    project.annotations[annotation.id] = annotation
    project.figure_boards[board.id] = board
    path = workspace_tmp_path / "last_milestones.biopic.json"

    store = ProjectStore()
    store.save(project, path)
    loaded = store.load(path)

    assert loaded.annotations[annotation.id].text == "MX"
    assert loaded.figure_boards[board.id].panels[1].label == "B"
    assert loaded.figure_boards[board.id].margin_left == 6
    assert loaded.figure_boards[board.id].label_mode is PanelLabelMode.NUMERICAL
    assert loaded.figure_boards[board.id].caption.visible_text() == "Manual"
