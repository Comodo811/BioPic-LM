"""Scientific annotation workspace."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.project_render import (
    editable_assets,
    project_image_cache_key,
    render_project_image,
)
from biopic.models.annotations import (
    AbbreviationTablePreset,
    AnnotationDefinition,
    AnnotationKind,
    AnnotationObject,
    consolidate_legend,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.ui.fonts import configure_safe_font_combo, safe_font_family
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.previews import asset_thumbnail
from biopic.ui.workspace_helpers.common import (
    project_asset_display_name as _project_asset_display_name,
)
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET
from biopic.ui.workspaces.annotation_abbreviations import (
    COMMON_ABBREVIATION_LANGUAGES as _COMMON_ABBREVIATION_LANGUAGES,
)
from biopic.ui.workspaces.annotation_abbreviations import (
    AnnotationAbbreviationsMixin,
)


class AnnotationWorkspace(AnnotationAbbreviationsMixin, QWidget):
    """Scientific annotation and legend workspace."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.annotationChanged: Callable[[], None] | None = None
        self._abbreviation_presets: dict[str, AbbreviationTablePreset] = {}
        self._active_abbreviation_table_id: str | None = None
        self._annotation_tool = "label"
        self._annotation_color = "#9fb0bf"
        self._editable_assets: list[ImageAsset] = []
        self._asset_list_signature: tuple[tuple[str, str, str], ...] | None = None
        self._moving_annotation_id: str | None = None
        self._selected_annotation_id: str | None = None
        self._rendered_image_cache: dict[str, tuple[tuple[object, ...], np.ndarray]] = {}
        self._display_signature: tuple[object, ...] | None = None
        self._annotation_overlay_signature: tuple[object, ...] | None = None
        self._scale_bar_overlay_signature: tuple[object, ...] | None = None
        self._annotation_table_signature: tuple[object, ...] | None = None
        self._records_signature: tuple[object, ...] | None = None
        self.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        label_tab = QWidget()
        controls = QHBoxLayout(label_tab)
        self.asset_combo = QComboBox()
        self.abbreviation_text = QPlainTextEdit()
        self.abbreviation_text.setMaximumHeight(32)
        self.definition_text = QPlainTextEdit()
        self.definition_text.setMaximumHeight(32)
        self.add_button = QPushButton("Add Label")
        controls.addWidget(QLabel("Image"))
        controls.addWidget(self.asset_combo)
        controls.addWidget(QLabel("Abbrev"))
        controls.addWidget(self.abbreviation_text)
        controls.addWidget(QLabel("Definition"))
        controls.addWidget(self.definition_text)
        controls.addWidget(self.add_button)
        self.tabs.addTab(label_tab, "Add Label")

        table_tab = QWidget()
        table_layout = QVBoxLayout(table_tab)
        table_controls = QHBoxLayout()
        self.abbreviation_table_button = QToolButton()
        self.abbreviation_table_button.setText("Abbreviation Table")
        self.abbreviation_table_button.setMinimumWidth(150)
        self.abbreviation_table_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.abbreviation_table_menu = QMenu(self.abbreviation_table_button)
        self.abbreviation_table_button.setMenu(self.abbreviation_table_menu)
        self.abbreviation_language_combo = QComboBox()
        self.abbreviation_language_combo.setEditable(True)
        self.abbreviation_language_combo.addItems(_COMMON_ABBREVIATION_LANGUAGES)
        self.apply_abbreviation_table_button = QPushButton("Set Active")
        table_controls.addWidget(self.abbreviation_table_button)
        table_controls.addWidget(QLabel("Language"))
        table_controls.addWidget(self.abbreviation_language_combo)
        table_controls.addWidget(self.apply_abbreviation_table_button)
        table_controls.addStretch(1)
        table_layout.addLayout(table_controls)
        self.abbreviation_table = QTableWidget(0, 2)
        self.abbreviation_table.setHorizontalHeaderLabels(["Abbreviation", "Complete word"])
        self.abbreviation_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table_layout.addWidget(self.abbreviation_table)
        row_controls = QHBoxLayout()
        self.add_abbreviation_row_button = QPushButton("+")
        self.remove_abbreviation_row_button = QPushButton("-")
        row_controls.addWidget(self.add_abbreviation_row_button)
        row_controls.addWidget(self.remove_abbreviation_row_button)
        row_controls.addStretch(1)
        table_layout.addLayout(row_controls)
        self.tabs.addTab(table_tab, "Abbreviation Tables")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        tools_panel = QWidget()
        tools_panel.setObjectName("annotationTools")
        tools_layout = QVBoxLayout(tools_panel)
        tools_layout.setContentsMargins(6, 6, 6, 6)
        self.asset_list = QListWidget()
        self.asset_list.setIconSize(QSize(170, 120))
        self.asset_list.setUniformItemSizes(True)
        self.asset_list.setFlow(QListWidget.Flow.LeftToRight)
        self.asset_list.setWrapping(False)
        self.asset_list.setFixedHeight(150)
        tools_layout.addWidget(QLabel("Tools"))
        self.annotation_tool_buttons: dict[str, QPushButton] = {}
        tools_grid = QGridLayout()
        for index, (tool_id, label) in enumerate(
            [
                ("move", "Move"),
                ("label", "Label"),
                ("arrow", "Arrow"),
                ("line", "Line"),
                ("wedge", "Wedge"),
            ]
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(28)
            button.clicked.connect(
                lambda _checked=False, selected=tool_id: self.select_annotation_tool(
                    selected
                )
            )
            self.annotation_tool_buttons[tool_id] = button
            tools_grid.addWidget(button, index // 2, index % 2)
        tools_layout.addLayout(tools_grid)
        self.annotation_font_family = QFontComboBox()
        configure_safe_font_combo(self.annotation_font_family)
        self.annotation_font_family.currentFontChanged.connect(
            self._annotation_font_changed
        )
        self.annotation_font_size = QDoubleSpinBox()
        self.annotation_font_size.setRange(4.0, 144.0)
        self.annotation_font_size.setValue(14.0)
        self.annotation_font_size.setSuffix(" pt")
        tools_layout.addWidget(QLabel("Font family"))
        tools_layout.addWidget(self.annotation_font_family)
        tools_layout.addWidget(QLabel("Font size"))
        tools_layout.addWidget(self.annotation_font_size)
        tools_layout.addWidget(QLabel("Color"))
        self.annotation_color_button = QPushButton()
        self.annotation_color_button.setFixedSize(QSize(40, 32))
        self.annotation_color_button.setToolTip("Annotation color")
        self.annotation_color_button.clicked.connect(self._open_annotation_color_dialog)
        tools_layout.addWidget(self.annotation_color_button)
        self.annotation_width = QDoubleSpinBox()
        self.annotation_width.setRange(1.0, 20.0)
        self.annotation_width.setValue(2.0)
        self.annotation_width.setSuffix(" px")
        tools_layout.addWidget(QLabel("Line width"))
        tools_layout.addWidget(self.annotation_width)
        tools_layout.addStretch(1)
        layout.addWidget(self.asset_list)
        self.canvas = ImageCanvas()
        self.annotation_table = QTableWidget(0, 5)
        self.annotation_table.setHorizontalHeaderLabels(
            ["Label", "Kind", "Font", "Size", "Color"]
        )
        self.annotation_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.records = QPlainTextEdit()
        self.records.setReadOnly(True)
        annotation_side = QWidget()
        annotation_side_layout = QVBoxLayout(annotation_side)
        annotation_side_layout.addWidget(QLabel("Elements"))
        annotation_side_layout.addWidget(self.annotation_table, 1)
        annotation_side_layout.addWidget(QLabel("Legend"))
        annotation_side_layout.addWidget(self.records, 1)
        splitter.addWidget(tools_panel)
        splitter.addWidget(self.canvas)
        splitter.addWidget(annotation_side)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        self.asset_combo.currentIndexChanged.connect(self._select_asset)
        self.asset_list.currentRowChanged.connect(self._select_asset_row)
        self.add_button.clicked.connect(self.add_label)
        self.canvas.pointClicked.connect(self._annotation_point_clicked)
        self.canvas.rectangleSelected.connect(self._annotation_rectangle_selected)
        self.canvas.layerDragStarted.connect(self._annotation_move_started)
        self.canvas.layerDragFinished.connect(self._annotation_move_finished)
        self.annotation_table.currentCellChanged.connect(
            self._annotation_table_selection_changed
        )
        self.annotation_table.cellChanged.connect(self._annotation_table_cell_changed)
        self.annotation_font_family.currentFontChanged.connect(
            self._apply_selected_annotation_style
        )
        self.annotation_font_size.valueChanged.connect(
            self._apply_selected_annotation_style
        )
        self.annotation_width.valueChanged.connect(self._apply_selected_annotation_style)
        self.abbreviation_table_menu.aboutToShow.connect(self._rebuild_abbreviation_table_menu)
        self.abbreviation_language_combo.currentTextChanged.connect(
            self._abbreviation_language_changed
        )
        self.apply_abbreviation_table_button.clicked.connect(self._apply_active_abbreviation_table)
        self.add_abbreviation_row_button.clicked.connect(self._add_abbreviation_row)
        self.remove_abbreviation_row_button.clicked.connect(self._remove_abbreviation_row)
        self.abbreviation_table.cellChanged.connect(self._abbreviation_table_cell_changed)
        self._load_persistent_abbreviation_tables()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()
        self._update_annotation_color_button()
        self.select_annotation_tool("label")

    def refresh(self) -> None:
        """Refresh image choices and annotation records."""
        if not self._abbreviation_presets:
            self._load_persistent_abbreviation_tables()
        current = self.asset_combo.currentData()
        assets = editable_assets(self.project)
        signature = tuple(
            (
                asset.id,
                _project_asset_display_name(asset, self.project.stacks),
                asset.checksum or asset.path,
            )
            for asset in assets
        )
        if signature != self._asset_list_signature:
            self.asset_combo.blockSignals(True)
            self.asset_list.blockSignals(True)
            self.asset_combo.clear()
            self.asset_list.clear()
            self._editable_assets = assets
            for asset in self._editable_assets:
                label = _project_asset_display_name(asset, self.project.stacks)
                self.asset_combo.addItem(label, asset.id)
                item = QListWidgetItem(
                    QIcon(asset_thumbnail(asset, QSize(170, 120))),
                    label,
                )
                item.setData(256, asset.id)
                self.asset_list.addItem(item)
            self.asset_combo.blockSignals(False)
            self.asset_list.blockSignals(False)
            self._asset_list_signature = signature
        else:
            self._editable_assets = assets
        if current is not None:
            index = self.asset_combo.findData(current)
            if index >= 0:
                self.asset_combo.setCurrentIndex(index)
                self.asset_list.setCurrentRow(index)
        if self.asset_combo.count() and self.asset_combo.currentIndex() < 0:
            self.asset_combo.setCurrentIndex(0)
        if self.asset_list.count() and self.asset_list.currentRow() < 0:
            self.asset_list.setCurrentRow(self.asset_combo.currentIndex())
        self._select_asset()
        self._refresh_records()
        self._refresh_annotation_table()
        self._refresh_abbreviation_table_view()

    def add_label(self) -> None:
        """Add a text annotation and definition."""
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        abbreviation = self._label_text_from_user()
        if not abbreviation:
            return
        full_definition = self.definition_text.toPlainText().strip() or abbreviation
        self._add_text_annotation(node_id, (0.1, 0.1), abbreviation, full_definition)

    def select_annotation_tool(self, tool_id: str) -> None:
        """Select the active annotation placement tool."""
        self._annotation_tool = tool_id
        for current, button in self.annotation_tool_buttons.items():
            button.setChecked(current == tool_id)
        if tool_id == "label":
            self.canvas.set_tool_mode("text")
        elif tool_id == "move":
            self.canvas.set_tool_mode("move")
        else:
            self.canvas.set_tool_mode("select")

    def _definition_for_label(
        self, abbreviation: str, fallback_definition: str
    ) -> AnnotationDefinition:
        preset = self._active_abbreviation_table()
        if preset is not None:
            for entry in preset.entries:
                if entry.abbreviation.casefold() == abbreviation.casefold():
                    full_definition = entry.text_for_language(preset.active_language).strip()
                    if full_definition:
                        existing = self._existing_definition(abbreviation, full_definition)
                        if existing is not None:
                            return existing
                        return AnnotationDefinition(
                            abbreviation=abbreviation,
                            full_definition=full_definition,
                            category="scientific label",
                        )
        existing = self._existing_definition(abbreviation, fallback_definition)
        if existing is not None:
            return existing
        return AnnotationDefinition(
            abbreviation=abbreviation,
            full_definition=fallback_definition,
            category="scientific label",
        )

    def _existing_definition(
        self, abbreviation: str, full_definition: str
    ) -> AnnotationDefinition | None:
        for definition in self.project.annotation_definitions.values():
            if (
                definition.abbreviation.casefold() == abbreviation.casefold()
                and definition.full_definition == full_definition
            ):
                return definition
        return None

    def _select_asset(self) -> None:
        asset_id = self.asset_combo.currentData()
        if asset_id is None:
            return
        row = self.asset_combo.currentIndex()
        if row >= 0 and self.asset_list.currentRow() != row:
            self.asset_list.blockSignals(True)
            self.asset_list.setCurrentRow(row)
            self.asset_list.blockSignals(False)
        asset = self.project.assets.get(str(asset_id))
        if asset is not None:
            node_id = self.project.source_node_id_for_asset(asset.id)
            rendered = self._rendered_project_image(node_id) if node_id is not None else None
            if rendered is not None:
                signature = (
                    asset.id,
                    node_id,
                    project_image_cache_key(self.project, node_id),
                    rendered.shape,
                    str(rendered.dtype),
                )
                if signature != self._display_signature:
                    self.canvas.set_pixels(rendered, asset.filename, fit=True)
                    self._display_signature = signature
            else:
                self.canvas.set_asset(asset)
                self._display_signature = (asset.id, "asset", asset.checksum or asset.path)
            self._refresh_scale_bar_overlay()
            self._refresh_annotation_overlay()

    def _select_asset_row(self, row: int) -> None:
        if row < 0 or row >= len(self._editable_assets):
            return
        if self.asset_combo.currentIndex() != row:
            self.asset_combo.blockSignals(True)
            self.asset_combo.setCurrentIndex(row)
            self.asset_combo.blockSignals(False)
        self._select_asset()

    def _rendered_project_image(self, node_id: str | None) -> np.ndarray | None:
        if node_id is None:
            return None
        key = project_image_cache_key(self.project, node_id)
        if key is None:
            return None
        cached = self._rendered_image_cache.get(node_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        rendered = render_project_image(self.project, node_id)
        if rendered is not None:
            self._rendered_image_cache[node_id] = (key, rendered)
        return rendered

    def current_asset_id(self) -> str | None:
        """Return the currently selected editable image asset id."""
        asset_id = self.asset_combo.currentData()
        return None if asset_id is None else str(asset_id)

    def select_asset_id(self, asset_id: str | None) -> None:
        """Select an editable image asset by id and redraw linked overlays."""
        if asset_id is None:
            self._select_asset()
            return
        index = self.asset_combo.findData(asset_id)
        if index >= 0:
            if self.asset_combo.currentIndex() != index:
                self.asset_combo.setCurrentIndex(index)
            elif self.asset_list.currentRow() != index:
                self.asset_list.setCurrentRow(index)
        self._select_asset()

    def _current_source_node_id(self) -> str | None:
        asset_id = self.asset_combo.currentData()
        if asset_id is None:
            return None
        return self.project.source_node_id_for_asset(str(asset_id))

    def _refresh_records(self) -> None:
        signature = (
            tuple(
                sorted(
                    (
                        definition.id,
                        definition.abbreviation,
                        definition.full_definition,
                        definition.include_in_legend,
                    )
                    for definition in self.project.annotation_definitions.values()
                )
            ),
            tuple(
                sorted(
                    (
                        annotation.id,
                        annotation.text,
                        annotation.definition_id,
                        annotation.visible,
                        annotation.include_in_legend,
                    )
                    for annotation in self.project.annotations.values()
                )
            ),
        )
        if signature == self._records_signature:
            return
        self._records_signature = signature
        entries = consolidate_legend(
            self.project.annotation_definitions, list(self.project.annotations.values())
        )
        lines = ["Legend"]
        lines.extend(entries)
        self.records.setPlainText("\n".join(lines))

    def _refresh_annotation_table(self) -> None:
        node_id = self._current_source_node_id()
        annotations = [
            annotation
            for annotation in self.project.annotations.values()
            if annotation.image_node_id == node_id
        ]
        signature = (
            node_id,
            self._selected_annotation_id,
            tuple(
                (
                    annotation.id,
                    annotation.text,
                    annotation.kind.value,
                    annotation.font,
                    annotation.size,
                    annotation.color,
                    annotation.line_width,
                    annotation.visible,
                )
                for annotation in annotations
            ),
        )
        if signature == self._annotation_table_signature:
            return
        self._annotation_table_signature = signature
        self.annotation_table.blockSignals(True)
        self.annotation_table.setRowCount(len(annotations))
        selected_row = -1
        for row, annotation in enumerate(annotations):
            values = [
                annotation.text or annotation.kind.value,
                annotation.kind.value,
                safe_font_family(annotation.font),
                f"{annotation.size:g}",
                "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(256, annotation.id)
                self.annotation_table.setItem(row, column, item)
            color_button = QPushButton()
            color_button.setFixedSize(QSize(28, 20))
            color_button.setToolTip("Change annotation color")
            color_button.setStyleSheet(
                f"background-color: {annotation.color}; border: 1px solid #151515;"
            )
            color_button.clicked.connect(
                lambda _checked=False, annotation_id=annotation.id: (
                    self._select_annotation_by_id(annotation_id),
                    self._open_annotation_color_dialog(),
                )
            )
            self.annotation_table.setCellWidget(row, 4, color_button)
            if annotation.id == self._selected_annotation_id:
                selected_row = row
        self.annotation_table.blockSignals(False)
        if selected_row >= 0:
            self.annotation_table.setCurrentCell(selected_row, 0)

    def _annotation_table_selection_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if current_row < 0:
            self._selected_annotation_id = None
            return
        item = self.annotation_table.item(current_row, 0)
        if item is None:
            self._selected_annotation_id = None
            return
        self._selected_annotation_id = str(item.data(256))
        self._sync_selected_annotation_controls()

    def _annotation_table_cell_changed(self, row: int, column: int) -> None:
        item = self.annotation_table.item(row, column)
        id_item = self.annotation_table.item(row, 0)
        if item is None or id_item is None:
            return
        annotation = self.project.annotations.get(str(id_item.data(256)))
        if annotation is None:
            return
        value = item.text().strip()
        changed = False
        if column == 0 and annotation.text != value:
            annotation.text = value
            changed = True
        elif column == 2:
            font = safe_font_family(value)
            if annotation.font != font:
                annotation.font = font
                changed = True
        elif column == 3:
            try:
                size = max(4.0, min(144.0, float(value.replace(",", "."))))
            except ValueError:
                self._annotation_table_signature = None
                self._refresh_annotation_table()
                return
            if abs(annotation.size - size) > 1e-6:
                annotation.size = size
                changed = True
        if not changed:
            return
        self._selected_annotation_id = annotation.id
        self._sync_selected_annotation_controls()
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_table_signature = None
        self._annotation_overlay_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _select_annotation_by_id(self, annotation_id: str) -> None:
        self._selected_annotation_id = annotation_id
        for row in range(self.annotation_table.rowCount()):
            item = self.annotation_table.item(row, 0)
            if item is not None and str(item.data(256)) == annotation_id:
                self.annotation_table.setCurrentCell(row, 0)
                break
        self._sync_selected_annotation_controls()

    def _sync_selected_annotation_controls(self) -> None:
        annotation = self.project.annotations.get(self._selected_annotation_id)
        if annotation is None:
            return
        self.annotation_font_family.blockSignals(True)
        self.annotation_font_size.blockSignals(True)
        self.annotation_width.blockSignals(True)
        self.annotation_font_family.setCurrentFont(QFont(safe_font_family(annotation.font)))
        self.annotation_font_size.setValue(float(annotation.size))
        self.annotation_width.setValue(float(annotation.line_width))
        self.annotation_font_family.blockSignals(False)
        self.annotation_font_size.blockSignals(False)
        self.annotation_width.blockSignals(False)
        self._annotation_color = annotation.color
        self._update_annotation_color_button()

    def _apply_selected_annotation_style(self, *_args: object) -> None:
        if self._selected_annotation_id is None:
            return
        annotation = self.project.annotations.get(self._selected_annotation_id)
        if annotation is None:
            return
        annotation.font = self._safe_annotation_font_family()
        annotation.size = float(self.annotation_font_size.value())
        annotation.color = self._annotation_color
        annotation.line_width = float(self.annotation_width.value())
        if annotation.kind is AnnotationKind.WEDGE:
            annotation.fill = self._annotation_color
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_table_signature = None
        self._annotation_overlay_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _refresh_scale_bar_overlay(self) -> None:
        node_id = self._current_source_node_id()
        scale_bars = [
            scale_bar
            for scale_bar in self.project.scale_bars.values()
            if scale_bar.image_node_id == node_id
        ]
        signature = (
            node_id,
            tuple(
                (
                    scale_bar.id,
                    scale_bar.pixel_length,
                    scale_bar.physical_length,
                    scale_bar.unit,
                    scale_bar.location,
                    scale_bar.offset_x,
                    scale_bar.offset_y,
                    scale_bar.foreground,
                    scale_bar.background,
                    scale_bar.font_family,
                    scale_bar.font_size,
                    scale_bar.display_length,
                    scale_bar.opacity,
                )
                for scale_bar in scale_bars
            ),
        )
        if signature == self._scale_bar_overlay_signature:
            return
        self._scale_bar_overlay_signature = signature
        if node_id is not None and node_id in self.project.calibrations:
            calibration = self.project.calibrations[node_id]
            for scale_bar in scale_bars:
                scale_bar.calibration = calibration
        self.canvas.set_scale_bars(scale_bars)

    def _refresh_annotation_overlay(self) -> None:
        node_id = self._current_source_node_id()
        annotations = [
            annotation
            for annotation in self.project.annotations.values()
            if annotation.image_node_id == node_id
        ]
        signature = (
            node_id,
            tuple(
                (
                    annotation.id,
                    annotation.kind.value,
                    tuple(annotation.points),
                    annotation.text,
                    annotation.font,
                    annotation.size,
                    annotation.color,
                    annotation.line_width,
                    annotation.fill,
                    annotation.opacity,
                    annotation.visible,
                )
                for annotation in annotations
            ),
        )
        if signature == self._annotation_overlay_signature:
            return
        self._annotation_overlay_signature = signature
        self.canvas.set_annotations(annotations)

    def _annotation_point_clicked(self, x: int, y: int) -> None:
        if self._annotation_tool != "label":
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        abbreviation = self._label_text_from_user()
        if not abbreviation:
            return
        full_definition = self.definition_text.toPlainText().strip() or abbreviation
        self._add_text_annotation(
            node_id,
            self._normalized_annotation_point(x, y),
            abbreviation,
            full_definition,
        )

    def _annotation_rectangle_selected(
        self, x: int, y: int, width: int, height: int
    ) -> None:
        if self._annotation_tool not in {"arrow", "line", "wedge"}:
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        kind = {
            "arrow": AnnotationKind.ARROW,
            "line": AnnotationKind.LINE,
            "wedge": AnnotationKind.WEDGE,
        }[self._annotation_tool]
        start = self._normalized_annotation_point(x, y)
        end = self._normalized_annotation_point(x + width, y + height)
        annotation = AnnotationObject(
            image_node_id=node_id,
            kind=kind,
            points=[start, end],
            color=self._annotation_color,
            line_width=self.annotation_width.value(),
            fill=self._annotation_color if kind is AnnotationKind.WEDGE else None,
            include_in_legend=False,
        )
        self._store_annotation(annotation)

    def _add_text_annotation(
        self,
        node_id: str,
        point: tuple[float, float],
        abbreviation: str,
        full_definition: str,
    ) -> None:
        definition = self._definition_for_label(abbreviation, full_definition)
        annotation = AnnotationObject(
            image_node_id=node_id,
            kind=AnnotationKind.TEXT,
            points=[point],
            text=abbreviation,
            definition_id=definition.id,
            category=definition.category,
            color=self._annotation_color,
            font=self._safe_annotation_font_family(),
            size=self.annotation_font_size.value(),
        )
        self.project.annotation_definitions[definition.id] = definition
        self._store_annotation(annotation)

    def _annotation_font_changed(self, font: QFont) -> None:
        safe_family = safe_font_family(font.family())
        if safe_family == font.family():
            return
        self.annotation_font_family.blockSignals(True)
        self.annotation_font_family.setCurrentFont(QFont(safe_family))
        self.annotation_font_family.blockSignals(False)

    def _safe_annotation_font_family(self) -> str:
        return safe_font_family(self.annotation_font_family.currentFont().family())

    def _label_text_from_user(self) -> str:
        text, accepted = QInputDialog.getText(
            self,
            "Add Label",
            "Label text:",
            text=self.abbreviation_text.toPlainText().strip(),
        )
        if not accepted:
            return ""
        return text.strip()

    def _store_annotation(self, annotation: AnnotationObject) -> None:
        self.project.annotations[annotation.id] = annotation
        self._selected_annotation_id = annotation.id
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_overlay_signature = None
        self._annotation_table_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _normalized_annotation_point(self, x: int, y: int) -> tuple[float, float]:
        size = self.canvas.image_size()
        if size is None:
            return (0.0, 0.0)
        width, height = size
        normalized_x = max(0.0, min(1.0, float(x) / max(1.0, float(width))))
        normalized_y = max(0.0, min(1.0, float(y) / max(1.0, float(height))))
        return (normalized_x, normalized_y)

    def _annotation_move_started(self, x: int, y: int) -> None:
        if self._annotation_tool != "move":
            return
        self._moving_annotation_id = self._nearest_annotation_id(
            self._normalized_annotation_point(x, y)
        )

    def _annotation_move_finished(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> None:
        if self._annotation_tool != "move" or self._moving_annotation_id is None:
            return
        annotation = self.project.annotations.get(self._moving_annotation_id)
        self._moving_annotation_id = None
        if annotation is None:
            return
        start = self._normalized_annotation_point(start_x, start_y)
        end = self._normalized_annotation_point(end_x, end_y)
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        annotation.points = [
            (
                round(max(0.0, min(1.0, point_x + delta_x)), 10),
                round(max(0.0, min(1.0, point_y + delta_y)), 10),
            )
            for point_x, point_y in annotation.points
        ]
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_overlay_signature = None
        self._annotation_table_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _nearest_annotation_id(
        self, point: tuple[float, float], *, max_distance: float = 0.08
    ) -> str | None:
        node_id = self._current_source_node_id()
        if node_id is None:
            return None
        best_id: str | None = None
        best_distance = max_distance
        for annotation in self.project.annotations.values():
            if annotation.image_node_id != node_id or not annotation.visible:
                continue
            for item_point in annotation.points:
                distance = (
                    (item_point[0] - point[0]) ** 2 + (item_point[1] - point[1]) ** 2
                ) ** 0.5
                if distance <= best_distance:
                    best_distance = distance
                    best_id = annotation.id
        return best_id

    def _open_annotation_color_dialog(self) -> None:
        dialog = QColorDialog(QColor(self._annotation_color), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowTitle("Change Annotation Color")
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        if color.isValid():
            self._annotation_color = color.name(QColor.NameFormat.HexRgb)
            self._update_annotation_color_button()
            self._apply_selected_annotation_style()

    def _update_annotation_color_button(self) -> None:
        self.annotation_color_button.setText("")
        self.annotation_color_button.setStyleSheet(
            "QPushButton {"
            "border: 1px solid #151515;"
            f"background-color: {self._annotation_color};"
            "}"
        )
