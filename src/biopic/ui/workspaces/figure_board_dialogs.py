"""Dialogs used by the figure-board workspace."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from biopic.models.figure_board import (
    FigureBoard,
    JournalPreset,
    LayoutPreset,
    PageFormat,
    PageMargins,
    PageUnit,
    PanelLabelMode,
    generate_layout_presets,
    label_for_index,
    panels_from_layout,
)
from biopic.ui.settings import restore_dialog_size, scrollable_dialog_body
from biopic.ui.workspace_helpers.common import layout_pixmap_preview as _layout_pixmap_preview
from biopic.ui.workspace_helpers.common import (
    page_dimension_mm as _page_dimension_mm,
)
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET
from biopic.ui.workspaces.figure_board_preview import FigureBoardPreview


class FigureBoardDialogsMixin:
    def _current_page(self) -> PageFormat:
        if self.page_combo.currentText() == "Custom":
            return PageFormat(
                "Custom",
                self.page_width.value(),
                self.page_height.value(),
                PageUnit(self.page_unit.currentText()),
                300,
            )
        return self._page_presets[self.page_combo.currentText()]

    def _current_margins(self) -> PageMargins:
        return PageMargins(
            self.margin_left.value(),
            self.margin_right.value(),
            self.margin_top.value(),
            self.margin_bottom.value(),
        )

    def _layout_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Figure Board Layout")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "figure_board_layout", QSize(620, 420))
        layout = QVBoxLayout(dialog)
        page_group = QGroupBox("Board Size")
        page_layout = QFormLayout(page_group)
        page_combo = QComboBox()
        page_combo.addItems(list(self._page_presets) + ["Custom"])
        page_combo.setCurrentText(self.page_combo.currentText())
        board_width = QDoubleSpinBox()
        board_width.setRange(1.0, 5000.0)
        board_width.setValue(self.board_width.value())
        board_width.setSuffix(" mm")
        board_height = QDoubleSpinBox()
        board_height.setRange(1.0, 5000.0)
        board_height.setValue(self.board_height.value())
        board_height.setSuffix(" mm")
        outline_width = QDoubleSpinBox()
        outline_width.setRange(1.0, 5000.0)
        outline_width.setValue(self.outline_width.value())
        outline_width.setSuffix(" mm")
        outline_height = QDoubleSpinBox()
        outline_height.setRange(1.0, 5000.0)
        outline_height.setValue(self.outline_height.value())
        outline_height.setSuffix(" mm")
        page_unit = QComboBox()
        page_unit.addItems([PageUnit.MM.value, PageUnit.CM.value, PageUnit.INCH.value])
        page_unit.setCurrentText(self.page_unit.currentText())
        page_layout.addRow("Preset", page_combo)
        page_layout.addRow("Board Width", board_width)
        page_layout.addRow("Board Height", board_height)
        page_layout.addRow("Outline Width", outline_width)
        page_layout.addRow("Outline Height", outline_height)
        page_layout.addRow("Units", page_unit)
        layout.addWidget(page_group)

        margins_group = QGroupBox("Margins")
        margins_layout = QGridLayout(margins_group)
        margin_left = QDoubleSpinBox()
        margin_right = QDoubleSpinBox()
        margin_top = QDoubleSpinBox()
        margin_bottom = QDoubleSpinBox()
        for source, target in (
            (self.margin_left, margin_left),
            (self.margin_right, margin_right),
            (self.margin_top, margin_top),
            (self.margin_bottom, margin_bottom),
        ):
            target.setRange(0.0, 500.0)
            target.setValue(source.value())
            target.setSuffix(" mm")
        margins_layout.addWidget(QLabel("Left"), 0, 0)
        margins_layout.addWidget(margin_left, 0, 1)
        margins_layout.addWidget(QLabel("Right"), 0, 2)
        margins_layout.addWidget(margin_right, 0, 3)
        margins_layout.addWidget(QLabel("Top"), 1, 0)
        margins_layout.addWidget(margin_top, 1, 1)
        margins_layout.addWidget(QLabel("Bottom"), 1, 2)
        margins_layout.addWidget(margin_bottom, 1, 3)
        layout.addWidget(margins_group)

        def preset_changed(name: str) -> None:
            if name == "Custom":
                return
            page = self._page_presets[name]
            board_width.setValue(page.width)
            board_height.setValue(page.height)
            page_unit.setCurrentText(page.unit.value)

        page_combo.currentTextChanged.connect(preset_changed)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.page_combo.setCurrentText(page_combo.currentText())
        self.page_width.setValue(board_width.value())
        self.page_height.setValue(board_height.value())
        self.page_unit.setCurrentText(page_unit.currentText())
        self.margin_left.setValue(margin_left.value())
        self.margin_right.setValue(margin_right.value())
        self.margin_top.setValue(margin_top.value())
        self.margin_bottom.setValue(margin_bottom.value())
        self.board_width.setValue(board_width.value())
        self.board_height.setValue(board_height.value())
        self.outline_width.setValue(outline_width.value())
        self.outline_height.setValue(outline_height.value())
        self._board_size_controls_changed()
        self._refresh_records()

    def open_layout_dialog(self) -> None:
        """Open the board size and margin layout dialog."""
        self._layout_dialog()

    def open_scale_bar_settings_dialog(self) -> None:
        """Open figure-board scale-bar auto-resize settings."""
        board = self._current_board()
        if board is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Figure Board Scale Bar Settings")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "figure_board_scale_bar_settings", QSize(440, 260))
        layout = QVBoxLayout(dialog)
        auto_group = QGroupBox("Auto-adjust scale")
        auto_layout = QVBoxLayout(auto_group)
        form = QFormLayout()
        max_fraction = QDoubleSpinBox()
        max_fraction.setRange(10.0, 100.0)
        max_fraction.setValue(board.scale_bar_max_fraction * 100.0)
        max_fraction.setSuffix("%")
        min_fraction = QDoubleSpinBox()
        min_fraction.setRange(10.0, 100.0)
        min_fraction.setValue(board.scale_bar_min_fraction * 100.0)
        min_fraction.setSuffix("%")
        form.addRow("Maximum scale-bar width", max_fraction)
        form.addRow("Minimum scale-bar width", min_fraction)
        auto_layout.addLayout(form)
        half_scale = QCheckBox("Half scale bar")
        specified_scale = QCheckBox("Specified scale length")
        scale_mode_group = QButtonGroup(dialog)
        scale_mode_group.setExclusive(True)
        scale_mode_group.addButton(half_scale)
        scale_mode_group.addButton(specified_scale)
        if board.scale_bar_use_snap_lengths:
            specified_scale.setChecked(True)
        else:
            half_scale.setChecked(True)
        custom_values = list(board.scale_bar_snap_lengths)
        custom_values_button = QPushButton("Custom Scale Values...")
        custom_values_button.setVisible(specified_scale.isChecked())
        auto_layout.addWidget(half_scale)
        auto_layout.addWidget(specified_scale)
        auto_layout.addWidget(custom_values_button)
        auto_layout.addStretch(1)
        layout.addWidget(auto_group)
        specified_scale.toggled.connect(custom_values_button.setVisible)

        def edit_custom_values() -> None:
            nonlocal custom_values
            updated = self._custom_scale_values_dialog(custom_values)
            if updated is not None:
                custom_values = updated

        custom_values_button.clicked.connect(edit_custom_values)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._push_board_undo(board)
        minimum = min_fraction.value() / 100.0
        maximum = max_fraction.value() / 100.0
        board.scale_bar_min_fraction = min(minimum, maximum)
        board.scale_bar_max_fraction = max(minimum, maximum)
        board.scale_bar_use_halving = half_scale.isChecked()
        board.scale_bar_use_snap_lengths = specified_scale.isChecked()
        board.scale_bar_snap_lengths = sorted(set(custom_values))
        self.preview.invalidate_render_cache()
        self.project.touch()
        if self.boardChanged is not None:
            self.boardChanged()

    def _custom_scale_values_dialog(self, values: list[float]) -> list[float] | None:
        """Open the replacement scale-length table as a focused dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Custom Scale Values")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "figure_board_custom_scale_values", QSize(420, 360))
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 1)
        table.setHorizontalHeaderLabels(["Replacement scale length"])
        table.horizontalHeader().setStretchLastSection(True)
        for value in values:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(f"{value:g}"))
        layout.addWidget(table)
        row_controls = QHBoxLayout()
        add_row = QPushButton("+")
        remove_row = QPushButton("-")
        row_controls.addWidget(add_row)
        row_controls.addWidget(remove_row)
        row_controls.addStretch(1)
        layout.addLayout(row_controls)
        add_row.clicked.connect(lambda: table.insertRow(table.rowCount()))
        remove_row.clicked.connect(
            lambda: table.removeRow(table.currentRow()) if table.currentRow() >= 0 else None
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        parsed_values: list[float] = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                continue
            try:
                value = float(item.text().strip().replace(",", "."))
            except ValueError:
                continue
            if value > 0:
                parsed_values.append(value)
        return sorted(set(parsed_values))

    def _create_board_dialog(self) -> FigureBoard | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Figure Board")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "figure_board_create", QSize(980, 720))
        body = scrollable_dialog_body(dialog)
        layout = QVBoxLayout(body)
        page = self._current_page()
        board_size_group = QGroupBox("Board Size")
        board_size_layout = QFormLayout(board_size_group)
        board_width = QDoubleSpinBox()
        board_height = QDoubleSpinBox()
        for spin in (board_width, board_height):
            spin.setRange(1.0, 5000.0)
            spin.setSuffix(" mm")
        board_width.setValue(_page_dimension_mm(page.width, page.unit))
        board_height.setValue(_page_dimension_mm(page.height, page.unit))
        board_size_layout.addRow("Width", board_width)
        board_size_layout.addRow("Height", board_height)
        layout.addWidget(board_size_group)

        label_group = QGroupBox("Panel Labels")
        label_layout = QFormLayout(label_group)
        label_mode = QComboBox()
        label_mode.addItem("Alphabetical", PanelLabelMode.ALPHABETICAL.value)
        label_mode.addItem("Alphabetical lowercase", PanelLabelMode.ALPHABETICAL_LOWER.value)
        label_mode.addItem("Numerical", PanelLabelMode.NUMERICAL.value)
        label_layout.addRow("Mode", label_mode)
        layout.addWidget(label_group)

        spacing_group = QGroupBox("Panel Spacing")
        spacing_layout = QGridLayout(spacing_group)
        horizontal_spacing = QDoubleSpinBox()
        horizontal_spacing.setRange(0.0, 100.0)
        horizontal_spacing.setSuffix(" mm")
        vertical_spacing = QDoubleSpinBox()
        vertical_spacing.setRange(0.0, 100.0)
        vertical_spacing.setSuffix(" mm")
        link_spacing = QPushButton("=")
        link_spacing.setCheckable(True)
        link_spacing.setChecked(True)
        horizontal_spacing.setValue(self.horizontal_spacing.value())
        vertical_spacing.setValue(self.vertical_spacing.value())
        spacing_layout.addWidget(QLabel("Horizontal spacing"), 0, 0)
        spacing_layout.addWidget(horizontal_spacing, 0, 1)
        spacing_layout.addWidget(QLabel("Vertical spacing"), 1, 0)
        spacing_layout.addWidget(vertical_spacing, 1, 1)
        spacing_connector = QLabel("│\n=\n│")
        spacing_connector.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spacing_layout.addWidget(spacing_connector, 0, 2, 2, 1)
        spacing_layout.addWidget(link_spacing, 0, 3, 2, 1)
        layout.addWidget(spacing_group)

        panel_group = QGroupBox("Number of Panels")
        panel_layout = QHBoxLayout(panel_group)
        panel_count = QSpinBox()
        panel_count.setRange(1, 8)
        panel_count.setValue(self.panel_count.value())
        panel_layout.addWidget(QLabel("Number of images"))
        panel_layout.addWidget(panel_count)
        panel_layout.addStretch(1)
        layout.addWidget(panel_group)

        presets = QListWidget()
        presets.setMinimumWidth(280)
        presets.setIconSize(QSize(112, 76))
        presets.setSpacing(4)
        preview = FigureBoardPreview(self.project)
        preview.set_workspace_watermark_visible(False)
        preview.set_zoom_percent(35)
        preset_area = QSplitter(Qt.Orientation.Horizontal)
        preset_list_container = QWidget()
        preset_list_layout = QVBoxLayout(preset_list_container)
        preset_list_layout.addWidget(QLabel("Layout Presets"))
        preset_list_layout.addWidget(presets)
        preset_area.addWidget(preset_list_container)
        preset_area.addWidget(preview)
        preset_area.setStretchFactor(0, 0)
        preset_area.setStretchFactor(1, 1)
        layout.addWidget(preset_area)
        current_presets: list[LayoutPreset] = []

        def refresh_presets() -> None:
            current_presets.clear()
            current_presets.extend(generate_layout_presets(panel_count.value()))
            presets.clear()
            for preset in current_presets:
                item = QListWidgetItem(QIcon(_layout_pixmap_preview(preset)), preset.name)
                item.setSizeHint(QSize(260, 86))
                presets.addItem(item)
            presets.setCurrentRow(0)
            refresh_preview()

        def selected_layout() -> LayoutPreset:
            if not current_presets:
                current_presets.extend(generate_layout_presets(panel_count.value()))
            return current_presets[max(0, presets.currentRow())]

        def refresh_preview() -> None:
            board = self._board_from_settings(
                page=self._current_page(),
                panel_count=panel_count.value(),
                label_mode=PanelLabelMode(label_mode.currentData()),
                layout_preset=selected_layout(),
                horizontal_gutter=horizontal_spacing.value(),
                vertical_gutter=vertical_spacing.value(),
                margins=self._current_margins(),
                journal_preset=self._journal_presets[self._current_journal_preset_name],
            )
            board.page = PageFormat(
                "Custom",
                board_width.value(),
                board_height.value(),
                PageUnit.MM,
                page.dpi,
            )
            preview.set_board(board)

        def sync_spacing_from_horizontal(value: float) -> None:
            if link_spacing.isChecked():
                vertical_spacing.setValue(value)
            refresh_preview()

        def sync_spacing_from_vertical(value: float) -> None:
            if link_spacing.isChecked():
                horizontal_spacing.setValue(value)
            refresh_preview()

        def spacing_link_toggled(checked: bool) -> None:
            link_spacing.setText("=" if checked else "free")
            spacing_connector.setText("│\n=\n│" if checked else "│\n \n│")
            if checked:
                vertical_spacing.setValue(horizontal_spacing.value())
            refresh_preview()

        link_spacing.toggled.connect(spacing_link_toggled)
        horizontal_spacing.valueChanged.connect(sync_spacing_from_horizontal)
        vertical_spacing.valueChanged.connect(sync_spacing_from_vertical)
        board_width.valueChanged.connect(lambda _value: refresh_preview())
        board_height.valueChanged.connect(lambda _value: refresh_preview())
        panel_count.valueChanged.connect(lambda _value: refresh_presets())
        label_mode.currentIndexChanged.connect(lambda _index: refresh_preview())
        presets.currentRowChanged.connect(lambda _row: refresh_preview())
        refresh_presets()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        self.panel_count.setValue(panel_count.value())
        self.horizontal_spacing.setValue(horizontal_spacing.value())
        self.vertical_spacing.setValue(vertical_spacing.value())
        self.link_spacing.setChecked(link_spacing.isChecked())
        self.page_combo.setCurrentText("Custom")
        self.page_width.setValue(board_width.value())
        self.page_height.setValue(board_height.value())
        self.page_unit.setCurrentText(PageUnit.MM.value)
        return self._board_from_settings(
            page=PageFormat(
                "Custom",
                board_width.value(),
                board_height.value(),
                PageUnit.MM,
                page.dpi,
            ),
            panel_count=panel_count.value(),
            label_mode=PanelLabelMode(label_mode.currentData()),
            layout_preset=selected_layout(),
            horizontal_gutter=horizontal_spacing.value(),
            vertical_gutter=vertical_spacing.value(),
            margins=self._current_margins(),
            journal_preset=self._journal_presets[self._current_journal_preset_name],
        )

    def _board_from_settings(
        self,
        *,
        page: PageFormat,
        panel_count: int,
        label_mode: PanelLabelMode,
        layout_preset: LayoutPreset,
        horizontal_gutter: float,
        vertical_gutter: float,
        margins: PageMargins,
        journal_preset: JournalPreset,
    ) -> FigureBoard:
        panels = panels_from_layout(layout_preset, label_mode)
        page_width_mm = _page_dimension_mm(page.width, page.unit)
        page_height_mm = _page_dimension_mm(page.height, page.unit)
        content_width_mm = max(
            1e-6,
            page_width_mm - margins.left - margins.right,
        )
        content_height_mm = max(
            1e-6,
            page_height_mm - margins.top - margins.bottom,
        )
        for index, panel in enumerate(panels[:panel_count]):
            panel.label = label_for_index(index, label_mode)
            panel_width_mm = max(1e-6, panel.rect[2] * content_width_mm)
            panel_height_mm = max(1e-6, panel.rect[3] * content_height_mm)
            panel.label_offset = (
                min(0.45, max(0.0, journal_preset.label_offset_mm[0] / panel_width_mm)),
                min(0.45, max(0.0, journal_preset.label_offset_mm[1] / panel_height_mm)),
            )
        return FigureBoard(
            name=f"Figure Board {len(self.project.figure_boards) + 1}",
            page=page,
            panels=panels[:panel_count],
            horizontal_gutter=horizontal_gutter,
            vertical_gutter=vertical_gutter,
            margin_left=margins.left,
            margin_right=margins.right,
            margin_top=margins.top,
            margin_bottom=margins.bottom,
            journal_preset=journal_preset.name,
            label_mode=label_mode,
            metadata_profile="Custom",
        )

