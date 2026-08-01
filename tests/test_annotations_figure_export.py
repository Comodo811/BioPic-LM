from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication, QGroupBox

from biopic.export import (
    export_image,
    export_project_figure_board,
    export_project_figure_board_latex,
    preflight_project,
)
from biopic.models.annotations import (
    AbbreviationEntry,
    AbbreviationTablePreset,
    AnnotationDefinition,
    AnnotationKind,
    AnnotationObject,
    consolidate_legend,
)
from biopic.models.figure_board import (
    FigureBoard,
    FigureCaption,
    FigurePanel,
    PageFormat,
    PageUnit,
    PanelLabelMode,
    generate_layout_presets,
    grid_panels,
    journal_presets,
    label_for_index,
    move_vertical_divider,
    page_format_presets,
    panels_from_layout,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.persistence.project_store import ProjectStore
from biopic.ui.fonts import safe_font_family
from biopic.ui.main_window import MainWindow
from biopic.ui.settings import ui_settings
from biopic.ui.workspace import AnnotationWorkspace, FigureBoardWorkspace


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


def test_annotation_font_picker_uses_directwrite_safe_fonts() -> None:
    QApplication.instance() or QApplication([])
    ui_settings().remove("presets/abbreviation_tables")
    workspace = AnnotationWorkspace(Project.new("Safe Fonts"))
    unsafe_families = {"MS Sans Serif", "MS Serif", "Fixedsys"}

    assert workspace._safe_annotation_font_family() not in unsafe_families
    for family in unsafe_families:
        assert safe_font_family(family) not in unsafe_families


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

    window._select_workspace(6)
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


def test_figureboard_toolbar_exposes_layout_next_to_create() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Figure Toolbar"))

    window._select_workspace(7)
    labels = [action.text() for action in window.context_toolbar.actions() if action.text()]

    assert labels[:2] == ["Create Figure Board", "Layout"]


def test_main_window_exposes_journal_presets_outside_figure_board_dialog() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Project.new("Journal Menu"))

    menu_titles = [action.text().replace("&", "") for action in window.menuBar().actions()]

    assert app is not None
    assert "Presets" in menu_titles
    assert window.presets_menu.title().replace("&", "") == "Presets"
    assert any(action.text() == "Nature" for action in window.journal_presets_menu.actions())


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


def test_figure_board_panel_label_color_round_trips() -> None:
    panel = FigurePanel(
        label="a",
        label_color="#ff0000",
        label_font_family="Times New Roman",
        label_font_size_pt=18.0,
        label_bold=False,
        label_italic=True,
    )
    restored = FigurePanel.from_dict(panel.to_dict())

    assert restored.label_color == "#ff0000"
    assert restored.label_font_family == "Times New Roman"
    assert restored.label_font_size_pt == 18.0
    assert restored.label_bold is False
    assert restored.label_italic is True


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
    assert workspace.preview._paper_font(large_page_rect, 10.0).pixelSize() > workspace.preview._paper_font(
        page_rect,
        10.0,
    ).pixelSize()


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


def test_figure_board_export_rotation_covers_panel_without_white_corners(
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
    assert white_fraction < 0.01


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
    assert output_path.with_suffix(".caption.txt").read_text(encoding="utf-8").strip() == "Auto $E=mc^2$"
    assert "\\caption{Auto $E=mc^2$}" in output_path.with_suffix(".caption.tex").read_text(encoding="utf-8")


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
