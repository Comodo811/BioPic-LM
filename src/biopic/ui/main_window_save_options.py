"""Project save options dialog helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from biopic.persistence.project_archive import (
    COPYABLE_SOURCE_FORMATS,
    DISABLED_FORMAT,
    ENCODABLE_RASTER_FORMATS,
    METADATA_TOKEN_CATEGORIES,
    SAVE_STAGE_DEFINITIONS,
    VIDEO_FORMATS,
    ProjectSaveOptions,
    SavePreset,
    SaveStageConfig,
    SaveStageDefinition,
    resolve_filename_template,
    validate_filename_template,
)
from biopic.ui.settings import SAVE_OPTIONS_SETTING_KEY, set_settings_json, settings_json

NEW_PRESET_SENTINEL = "__new_preset__"
FORMAT_LABELS = {
    DISABLED_FORMAT: "None",
    "preserve_original": "Preserve original",
    "tiff": "TIFF",
    "png": "PNG",
    "jpeg": "JPEG",
    "bmp": "BMP",
}


def load_project_save_options() -> ProjectSaveOptions:
    """Load persisted project save options."""
    return ProjectSaveOptions.from_dict(settings_json(SAVE_OPTIONS_SETTING_KEY, {}))


def save_project_save_options(options: ProjectSaveOptions) -> None:
    """Persist project save options."""
    set_settings_json(SAVE_OPTIONS_SETTING_KEY, options.normalized().to_dict())


class ProjectSaveOptionsDialog(QDialog):
    """Dialog for configuring project archive behavior."""

    def __init__(self, options: ProjectSaveOptions, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Options")
        self.resize(860, 640)
        self._options = options.normalized()
        self._preset_by_name = {
            preset.name: preset.normalized() for preset in self._options.presets
        }
        if "Standard" not in self._preset_by_name:
            self._preset_by_name["Standard"] = SavePreset.standard()
        self._active_name = self._options.active_preset.name
        self._stage_checks: dict[str, QCheckBox] = {}
        self._figure_board_text_check: QCheckBox | None = None
        self._figure_board_latex_check: QCheckBox | None = None
        self._format_combos: dict[str, list[QComboBox]] = {}
        self._template_edits: dict[str, QLineEdit] = {}
        self._active_template_edit: QLineEdit | None = None
        self._loading = False

        root = QVBoxLayout(self)
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset", self))
        self.preset_selector = QComboBox(self)
        self.preset_selector.setMinimumWidth(260)
        self._reload_preset_selector()
        self.preset_selector.currentIndexChanged.connect(self._preset_changed)
        preset_row.addWidget(self.preset_selector, 1)
        root.addLayout(preset_row)

        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)
        tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #454545;
                top: -1px;
                background: #2b2b2b;
            }
            QTabBar::tab {
                background: #242424;
                border: 1px solid #454545;
                border-bottom-color: #454545;
                padding: 7px 14px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #2b2b2b;
                border-bottom-color: #2b2b2b;
            }
            QTabBar::tab:!selected {
                margin-top: 3px;
            }
            """
        )
        tabs.addTab(self._tab_page(self._saving_steps_group(tabs), tabs), "Saving Steps")
        tabs.addTab(self._tab_page(self._file_types_group(tabs), tabs), "File Types")
        tabs.addTab(self._tab_page(self._file_names_group(tabs), tabs), "File Names")
        root.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._load_preset_into_controls(self._active_preset())

    def options(self) -> ProjectSaveOptions:
        """Return the selected options."""
        self._store_controls_in_active_preset()
        return ProjectSaveOptions(
            folder_structure="standard",
            active_preset_name=self._active_name,
            presets=tuple(self._preset_by_name.values()),
            include_original_images=True,
            include_stack_source_images=True,
            include_edited_outputs=True,
            include_figure_boards=True,
        ).normalized()

    def _saving_steps_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("Saving Steps", parent)
        layout = QVBoxLayout(group)
        for definition in SAVE_STAGE_DEFINITIONS:
            checkbox = QCheckBox(definition.label, group)
            checkbox.toggled.connect(self._control_changed)
            self._stage_checks[definition.key] = checkbox
            layout.addWidget(checkbox)
            if definition.key == "figure_board":
                figure_options = QWidget(group)
                figure_layout = QVBoxLayout(figure_options)
                figure_layout.setContentsMargins(24, 0, 0, 0)
                self._figure_board_text_check = QCheckBox(
                    "Save as text document",
                    figure_options,
                )
                self._figure_board_latex_check = QCheckBox(
                    "Save as LaTeX file",
                    figure_options,
                )
                self._figure_board_text_check.toggled.connect(self._control_changed)
                self._figure_board_latex_check.toggled.connect(self._control_changed)
                checkbox.toggled.connect(figure_options.setEnabled)
                figure_layout.addWidget(self._figure_board_text_check)
                figure_layout.addWidget(self._figure_board_latex_check)
                layout.addWidget(figure_options)
        return group

    def _tab_page(self, widget: QWidget, parent: QWidget) -> QScrollArea:
        page = QScrollArea(parent)
        page.setWidgetResizable(True)
        content = QWidget(page)
        layout = QVBoxLayout(content)
        layout.addWidget(widget)
        layout.addStretch(1)
        page.setWidget(content)
        return page

    def _file_types_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("File Types", parent)
        root = QVBoxLayout(group)
        help_label = QLabel(
            "Format 1, 2, and 3 are simultaneous export slots for the same saving step. "
            "Use None for unused slots; duplicate formats are saved only once.",
            group,
        )
        help_label.setWordWrap(True)
        root.addWidget(help_label)
        layout = QGridLayout()
        layout.setColumnStretch(0, 1)
        layout.addWidget(QLabel("Stage", group), 0, 0)
        for index in range(3):
            label = QLabel(f"Format {index + 1}", group)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label, 0, index + 1)
        for row, definition in enumerate(SAVE_STAGE_DEFINITIONS, start=1):
            layout.addWidget(QLabel(_short_stage_label(definition), group), row, 0)
            combos: list[QComboBox] = []
            for column in range(3):
                combo = QComboBox(group)
                combo.setMinimumWidth(150)
                _populate_format_combo(combo, definition)
                combo.currentIndexChanged.connect(self._control_changed)
                layout.addWidget(combo, row, column + 1)
                combos.append(combo)
            self._format_combos[definition.key] = combos
        root.addLayout(layout)
        return group

    def _reload_preset_selector(self) -> None:
        self.preset_selector.blockSignals(True)
        self.preset_selector.clear()
        ordered_names = ["Standard"] + sorted(
            name for name in self._preset_by_name if name != "Standard"
        )
        for name in ordered_names:
            self.preset_selector.addItem(name, name)
        self.preset_selector.insertSeparator(self.preset_selector.count())
        self.preset_selector.addItem("New Preset...", NEW_PRESET_SENTINEL)
        index = self.preset_selector.findData(self._active_name)
        self.preset_selector.setCurrentIndex(max(0, index))
        self.preset_selector.blockSignals(False)

    def _preset_changed(self) -> None:
        if self._loading:
            return
        selected = str(self.preset_selector.currentData() or "Standard")
        if selected == NEW_PRESET_SENTINEL:
            self._create_preset()
            return
        self._store_controls_in_active_preset()
        self._active_name = selected
        self._load_preset_into_controls(self._active_preset())

    def _create_preset(self) -> None:
        self._store_controls_in_active_preset()
        name, ok = QInputDialog.getText(self, "New Save Preset", "Preset name")
        name = name.strip()
        if not ok or not name:
            self._reload_preset_selector()
            return
        if name in self._preset_by_name:
            QMessageBox.warning(self, "Save Options", "A preset with that name already exists.")
            self._reload_preset_selector()
            return
        source = self._active_preset()
        self._preset_by_name[name] = SavePreset(name=name, stages=dict(source.stages)).normalized()
        self._active_name = name
        self._reload_preset_selector()
        self._load_preset_into_controls(self._active_preset())

    def _active_preset(self) -> SavePreset:
        return self._preset_by_name.get(self._active_name, SavePreset.standard()).normalized()

    def _load_preset_into_controls(self, preset: SavePreset) -> None:
        self._loading = True
        for definition in SAVE_STAGE_DEFINITIONS:
            config = preset.stages.get(
                definition.key,
                SaveStageConfig(definition.default_enabled, definition.default_formats),
            )
            checkbox = self._stage_checks[definition.key]
            checkbox.blockSignals(True)
            checkbox.setChecked(config.enabled)
            checkbox.blockSignals(False)
            if definition.key == "figure_board":
                if self._figure_board_text_check is not None:
                    self._figure_board_text_check.blockSignals(True)
                    self._figure_board_text_check.setChecked(config.save_caption_text)
                    self._figure_board_text_check.setEnabled(config.enabled)
                    self._figure_board_text_check.blockSignals(False)
                if self._figure_board_latex_check is not None:
                    self._figure_board_latex_check.blockSignals(True)
                    self._figure_board_latex_check.setChecked(config.save_caption_latex)
                    self._figure_board_latex_check.setEnabled(config.enabled)
                    self._figure_board_latex_check.blockSignals(False)
            for combo, fmt in zip(self._format_combos[definition.key], config.formats, strict=True):
                combo.blockSignals(True)
                index = combo.findData(fmt)
                combo.setCurrentIndex(max(0, index))
                combo.blockSignals(False)
            edit = self._template_edits[definition.key]
            edit.blockSignals(True)
            edit.setText(config.filename_template)
            edit.blockSignals(False)
        self._loading = False
        self._update_filename_preview()

    def _store_controls_in_active_preset(self) -> None:
        stages: dict[str, SaveStageConfig] = {}
        for definition in SAVE_STAGE_DEFINITIONS:
            formats = tuple(
                str(combo.currentData() or DISABLED_FORMAT)
                for combo in self._format_combos[definition.key]
            )
            stages[definition.key] = SaveStageConfig(
                enabled=self._stage_checks[definition.key].isChecked(),
                formats=formats,  # type: ignore[arg-type]
                filename_template=self._template_edits[definition.key].text().strip(),
                save_caption_text=(
                    bool(self._figure_board_text_check.isChecked())
                    if definition.key == "figure_board"
                    and self._figure_board_text_check is not None
                    else False
                ),
                save_caption_latex=(
                    bool(self._figure_board_latex_check.isChecked())
                    if definition.key == "figure_board"
                    and self._figure_board_latex_check is not None
                    else False
                ),
            )
        self._preset_by_name[self._active_name] = SavePreset(
            name=self._active_name,
            stages=stages,
        ).normalized()

    def _control_changed(self) -> None:
        if not self._loading:
            self._store_controls_in_active_preset()
            self._update_filename_preview()

    def _file_names_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("File Names", parent)
        root = QVBoxLayout(group)
        help_label = QLabel(
            "Use metadata fields in curly brackets, for example "
            "{species}_{specimen_id}_annotated. Extensions are controlled by File Types.",
            group,
        )
        help_label.setWordWrap(True)
        root.addWidget(help_label)

        template_grid = QGridLayout()
        template_grid.setColumnStretch(1, 1)
        for row, definition in enumerate(SAVE_STAGE_DEFINITIONS):
            template_grid.addWidget(QLabel(_short_stage_label(definition), group), row, 0)
            edit = QLineEdit(group)
            edit.setPlaceholderText("{original_name}")
            edit.textChanged.connect(self._control_changed)
            edit.cursorPositionChanged.connect(
                lambda _old, _new, editor=edit: self._set_active_template(editor)
            )
            edit.selectionChanged.connect(lambda editor=edit: self._set_active_template(editor))
            self._template_edits[definition.key] = edit
            template_grid.addWidget(edit, row, 1)
        root.addLayout(template_grid)

        token_row = QHBoxLayout()
        token_panel = QVBoxLayout()
        token_panel.addWidget(
            QLabel("Available metadata fields - click to add to file name", group)
        )
        self.metadata_search = QLineEdit(group)
        self.metadata_search.setPlaceholderText("Search metadata fields")
        self.metadata_search.textChanged.connect(self._reload_metadata_tokens)
        token_panel.addWidget(self.metadata_search)
        self.metadata_tokens = QListWidget(group)
        self.metadata_tokens.itemClicked.connect(self._insert_metadata_token)
        token_panel.addWidget(self.metadata_tokens, 1)
        token_row.addLayout(token_panel, 1)

        preview_panel = QVBoxLayout()
        preview_panel.addWidget(QLabel("Preview", group))
        self.filename_preview = QLabel(group)
        self.filename_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.filename_preview.setWordWrap(True)
        preview_panel.addWidget(self.filename_preview)
        self.filename_warning = QLabel(group)
        self.filename_warning.setWordWrap(True)
        self.filename_warning.setStyleSheet("color: #d6a25e;")
        preview_panel.addWidget(self.filename_warning)
        preview_panel.addStretch(1)
        token_row.addLayout(preview_panel, 1)
        root.addLayout(token_row)
        self._reload_metadata_tokens()
        return group

    def _set_active_template(self, editor: QLineEdit) -> None:
        self._active_template_edit = editor
        self._update_filename_preview()

    def _reload_metadata_tokens(self) -> None:
        query = (
            self.metadata_search.text().strip().lower()
            if hasattr(self, "metadata_search")
            else ""
        )
        self.metadata_tokens.clear()
        for category, fields in METADATA_TOKEN_CATEGORIES:
            matching = [
                (key, label)
                for key, label in fields
                if not query or query in key.lower() or query in label.lower()
            ]
            if not matching:
                continue
            header = QListWidgetItem(category)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.metadata_tokens.addItem(header)
            for key, label in matching:
                item = QListWidgetItem(f"  {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.metadata_tokens.addItem(item)

    def _insert_metadata_token(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if not key:
            return
        editor = self._active_template_edit or next(iter(self._template_edits.values()), None)
        if editor is None:
            return
        editor.setFocus()
        editor.insert(f"{{{key}}}")
        self._set_active_template(editor)

    def _update_filename_preview(self) -> None:
        if self._loading or not hasattr(self, "filename_preview"):
            return
        editor = self._active_template_edit or next(iter(self._template_edits.values()), None)
        if editor is None:
            return
        stage_key = next(
            (key for key, candidate in self._template_edits.items() if candidate is editor),
            SAVE_STAGE_DEFINITIONS[0].key,
        )
        definition = next(item for item in SAVE_STAGE_DEFINITIONS if item.key == stage_key)
        formats = [
            str(combo.currentData() or DISABLED_FORMAT)
            for combo in self._format_combos[stage_key]
        ]
        unique_formats = SaveStageConfig(  # type: ignore[arg-type]
            True,
            tuple(formats),
            editor.text(),
        ).unique_formats(definition)
        metadata = {
            "species": "Lecane lunaris",
            "scientific_name": "Lecane lunaris",
            "specimen_id": "004",
            "magnification": "40",
            "microscope": "Example microscope",
            "camera": "Example camera",
        }
        context = {
            "project_name": "Example Project",
            "project_id": "project",
            "original_name": "IMG_0133",
            "original_extension": "tif",
            "index": "001",
            "sequence": "001",
            "stack_index": "001",
            "frame_index": "000001",
            "width": "1024",
            "height": "768",
            "bit_depth": "uint16",
        }
        resolved = resolve_filename_template(editor.text(), metadata, context)
        suffixes = [_preview_suffix(fmt) for fmt in unique_formats]
        self.filename_preview.setText(
            "\n".join(f"{resolved.stem}{suffix}" for suffix in suffixes) or resolved.stem
        )
        warnings = list(resolved.warnings)
        warnings.extend(validate_filename_template(editor.text()))
        self.filename_warning.setText("\n".join(dict.fromkeys(warnings)))


def _populate_format_combo(combo: QComboBox, definition: SaveStageDefinition) -> None:
    combo.addItem(FORMAT_LABELS[DISABLED_FORMAT], DISABLED_FORMAT)
    allowed = {
        "source": COPYABLE_SOURCE_FORMATS,
        "video": VIDEO_FORMATS,
    }.get(definition.kind, ENCODABLE_RASTER_FORMATS)
    for fmt in allowed:
        combo.addItem(FORMAT_LABELS[fmt], fmt)


def _short_stage_label(definition: SaveStageDefinition) -> str:
    return definition.label.removeprefix("Save ").removesuffix(" into project folder")


def _preview_suffix(fmt: str) -> str:
    if fmt == "preserve_original":
        return ".original"
    if fmt == "jpeg":
        return ".jpg"
    if fmt in {"tiff", "tif"}:
        return ".tif"
    if fmt == DISABLED_FORMAT:
        return ""
    return f".{fmt}"
