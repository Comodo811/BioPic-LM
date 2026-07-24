"""Biological microscopy metadata workspace."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.project_render import editable_assets
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.ui.image_canvas import ImageCanvas


class MetadataWorkspace(QWidget):
    """Editable biological microscopy metadata for each project image."""

    _TEXT_FIELDS: tuple[tuple[str, str], ...] = (
        ("scientific_name", "Species / Scientific name"),
        ("taxonomy", "Taxonomy"),
        ("specimen_id", "Specimen ID"),
        ("voucher_id", "Voucher / Collection ID"),
        ("magnification", "Magnification"),
        ("objective", "Objective"),
        ("microscope", "Microscope"),
        ("camera", "Camera"),
        ("imaging_method", "Imaging method"),
        ("illumination", "Illumination"),
        ("staining", "Staining / Contrast"),
        ("preparation", "Preparation"),
        ("collector", "Collector"),
        ("collection_date", "Collection date"),
        ("locality", "Collection locality"),
        ("latitude", "Latitude"),
        ("longitude", "Longitude"),
        ("habitat", "Habitat / Substrate"),
        ("sample_id", "Sample ID"),
        ("institution", "Institution"),
        ("rights", "Rights / License"),
    )
    _COMBO_FIELDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("sex", "Sex", ("", "female", "male", "hermaphrodite", "undetermined", "not applicable")),
        (
            "life_stage",
            "Life stage",
            ("", "egg", "juvenile", "larva", "pupa", "adult", "senescent", "unknown"),
        ),
        (
            "orientation",
            "View / Orientation",
            ("", "dorsal", "ventral", "lateral", "anterior", "posterior", "apical", "basal"),
        ),
        (
            "body_part",
            "Body part / Structure",
            ("", "whole organism", "head", "trunk", "appendage", "mouthparts", "genitalia", "other"),
        ),
        ("side", "Side", ("", "left", "right", "bilateral", "not applicable")),
    )
    _PROFILE_FIELDS: dict[str, tuple[str, ...]] = {
        "Custom": tuple(key for key, _label in _TEXT_FIELDS)
        + tuple(key for key, _label, _values in _COMBO_FIELDS),
        "REMBI": (
            "scientific_name",
            "taxonomy",
            "specimen_id",
            "sample_id",
            "sex",
            "life_stage",
            "body_part",
            "orientation",
            "side",
            "preparation",
            "staining",
            "imaging_method",
            "illumination",
            "microscope",
            "camera",
            "objective",
            "magnification",
            "collector",
            "collection_date",
            "locality",
            "latitude",
            "longitude",
            "habitat",
            "institution",
            "rights",
        ),
        "BioImage Archive": (
            "sample_id",
            "scientific_name",
            "taxonomy",
            "specimen_id",
            "preparation",
            "imaging_method",
            "illumination",
            "microscope",
            "camera",
            "objective",
            "magnification",
            "staining",
            "institution",
            "rights",
        ),
        "OME": (
            "sample_id",
            "specimen_id",
            "scientific_name",
            "preparation",
            "imaging_method",
            "illumination",
            "microscope",
            "camera",
            "objective",
            "magnification",
            "staining",
        ),
    }

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.metadataChanged: Callable[[], None] | None = None
        self._assets: list[ImageAsset] = []
        self._current_asset_id: str | None = None
        self._loading = False
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(250)
        self._notes_timer.timeout.connect(self._store_current_metadata)

        layout = QHBoxLayout(self)
        self.asset_list = QListWidget()
        self.asset_list.setMinimumWidth(220)
        self.canvas = ImageCanvas()

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        title = QLabel("Biological Microscopy Metadata")
        title.setStyleSheet("font-weight: bold;")
        form_layout.addWidget(title)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Metadata type"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(list(self._PROFILE_FIELDS))
        profile_row.addWidget(self.profile_combo, 1)
        form_layout.addLayout(profile_row)
        preset_grid = QGridLayout()
        self.equipment_preset_combo = QComboBox()
        self.location_preset_combo = QComboBox()
        self.collector_preset_combo = QComboBox()
        self.preparation_preset_combo = QComboBox()
        for combo in (
            self.equipment_preset_combo,
            self.location_preset_combo,
            self.collector_preset_combo,
            self.preparation_preset_combo,
        ):
            combo.addItem("No preset", "")
        preset_grid.addWidget(QLabel("Equipment preset"), 0, 0)
        preset_grid.addWidget(self.equipment_preset_combo, 0, 1)
        preset_grid.addWidget(QLabel("Location preset"), 1, 0)
        preset_grid.addWidget(self.location_preset_combo, 1, 1)
        preset_grid.addWidget(QLabel("Collector preset"), 2, 0)
        preset_grid.addWidget(self.collector_preset_combo, 2, 1)
        preset_grid.addWidget(QLabel("Preparation preset"), 3, 0)
        preset_grid.addWidget(self.preparation_preset_combo, 3, 1)
        form_layout.addLayout(preset_grid)
        self.fields: dict[str, QLineEdit | QComboBox] = {}
        self._field_labels: dict[str, QWidget] = {}
        form = QFormLayout()
        for key, label in self._TEXT_FIELDS:
            editor = QLineEdit()
            editor.editingFinished.connect(self._store_current_metadata)
            self.fields[key] = editor
            form.addRow(label, editor)
            label_widget = form.labelForField(editor)
            if label_widget is not None:
                self._field_labels[key] = label_widget
        for key, label, values in self._COMBO_FIELDS:
            editor = QComboBox()
            editor.setEditable(True)
            editor.addItems(list(values))
            editor.currentTextChanged.connect(self._store_current_metadata)
            self.fields[key] = editor
            form.addRow(label, editor)
            label_widget = form.labelForField(editor)
            if label_widget is not None:
                self._field_labels[key] = label_widget
        form_layout.addLayout(form)
        form_layout.addWidget(QLabel("Notes"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Free text notes, preparation details, specimen remarks")
        self.notes.textChanged.connect(lambda: self._notes_timer.start())
        form_layout.addWidget(self.notes, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_container)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.asset_list)
        splitter.addWidget(self.canvas)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        layout.addWidget(splitter)
        self.asset_list.currentRowChanged.connect(self._select_row)
        self.profile_combo.currentTextChanged.connect(self._metadata_profile_changed)
        self.equipment_preset_combo.currentIndexChanged.connect(
            lambda _index: self._apply_metadata_preset("equipment", self.equipment_preset_combo)
        )
        self.location_preset_combo.currentIndexChanged.connect(
            lambda _index: self._apply_metadata_preset("location", self.location_preset_combo)
        )
        self.collector_preset_combo.currentIndexChanged.connect(
            lambda _index: self._apply_metadata_preset("collector", self.collector_preset_combo)
        )
        self.preparation_preset_combo.currentIndexChanged.connect(
            lambda _index: self._apply_metadata_preset(
                "preparation", self.preparation_preset_combo
            )
        )
        self.refresh_metadata_presets()

    def refresh(self) -> None:
        """Refresh the image list while preserving selection."""
        current = self._current_asset_id
        self._assets = editable_assets(self.project)
        self.refresh_metadata_presets()
        self.asset_list.blockSignals(True)
        self.asset_list.clear()
        selected_row = -1
        for row, asset in enumerate(self._assets):
            self.asset_list.addItem(asset.filename)
            if asset.id == current:
                selected_row = row
        self.asset_list.blockSignals(False)
        if selected_row < 0 and self._assets:
            selected_row = 0
        if selected_row >= 0:
            self.asset_list.setCurrentRow(selected_row)
            self._select_row(selected_row)
        else:
            self._current_asset_id = None
            self._load_asset_metadata(None)

    def select_asset_id(self, asset_id: str | None) -> None:
        if asset_id is None:
            return
        for row, asset in enumerate(self._assets):
            if asset.id == asset_id:
                self.asset_list.setCurrentRow(row)
                return

    def _select_row(self, row: int) -> None:
        if row < 0 or row >= len(self._assets):
            return
        asset = self._assets[row]
        self._current_asset_id = asset.id
        try:
            self.canvas.set_asset(asset)
        except OSError:
            pass
        self._load_asset_metadata(asset)

    def _load_asset_metadata(self, asset: ImageAsset | None) -> None:
        self._loading = True
        metadata = {} if asset is None else asset.metadata
        profile = str(metadata.get("metadata_profile", "Custom"))
        if profile not in self._PROFILE_FIELDS:
            profile = "Custom"
        self.profile_combo.setCurrentText(profile)
        for key, editor in self.fields.items():
            value = str(metadata.get(key, ""))
            if isinstance(editor, QComboBox):
                if editor.findText(value) < 0:
                    editor.addItem(value)
                editor.setCurrentText(value)
            else:
                editor.setText(value)
        self.notes.setPlainText(str(metadata.get("notes", "")))
        self._apply_metadata_profile(profile)
        self._loading = False

    def _metadata_profile_changed(self, profile: str) -> None:
        self._apply_metadata_profile(profile)
        self._store_current_metadata()

    def _apply_metadata_profile(self, profile: str) -> None:
        visible_fields = set(self._PROFILE_FIELDS.get(profile, self._PROFILE_FIELDS["Custom"]))
        visible_fields.update(
            {"microscope", "camera", "imaging_method", "objective", "magnification"}
        )
        for key, editor in self.fields.items():
            visible = key in visible_fields
            editor.setVisible(visible)
            label = self._field_labels.get(key)
            if label is not None:
                label.setVisible(visible)

    def refresh_metadata_presets(self) -> None:
        """Refresh preset dropdowns without changing the current image metadata."""
        self._fill_equipment_combo()
        self._fill_preset_combo(self.location_preset_combo, "location")
        self._fill_preset_combo(self.collector_preset_combo, "collector")
        self._fill_preset_combo(self.preparation_preset_combo, "preparation")

    def apply_metadata_preset(self, category: str, name: str) -> None:
        """Apply a saved metadata preset to the currently selected image."""
        combo_by_category = {
            "equipment": self.equipment_preset_combo,
            "location": self.location_preset_combo,
            "collector": self.collector_preset_combo,
            "preparation": self.preparation_preset_combo,
        }
        combo = combo_by_category.get(category)
        if combo is None:
            return
        index = combo.findData(name)
        if index >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        if category == "equipment":
            self._apply_equipment_scale_preset(name)
            return
        self._apply_metadata_preset_name(category, name)

    def _fill_preset_combo(self, combo: QComboBox, category: str) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("No preset", "")
        for preset in self.project.metadata_presets.get(category, []):
            name = preset.get("name", "").strip()
            if name:
                combo.addItem(name, name)
        if current is not None:
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _fill_equipment_combo(self) -> None:
        current = self.equipment_preset_combo.currentData()
        self.equipment_preset_combo.blockSignals(True)
        self.equipment_preset_combo.clear()
        self.equipment_preset_combo.addItem("No preset", "")
        for preset in self.project.scale_presets.values():
            self.equipment_preset_combo.addItem(preset.name, preset.id)
        if current is not None:
            index = self.equipment_preset_combo.findData(current)
            if index >= 0:
                self.equipment_preset_combo.setCurrentIndex(index)
        self.equipment_preset_combo.blockSignals(False)

    def _apply_metadata_preset(self, category: str, combo: QComboBox) -> None:
        if self._loading:
            return
        name = str(combo.currentData() or "")
        if not name:
            return
        if category == "equipment":
            self._apply_equipment_scale_preset(name)
            return
        self._apply_metadata_preset_name(category, name)

    def _apply_equipment_scale_preset(self, preset_id: str) -> None:
        preset = self.project.scale_presets.get(preset_id)
        if preset is None:
            preset = next(
                (item for item in self.project.scale_presets.values() if item.name == preset_id),
                None,
            )
        if preset is None:
            return
        self._loading = True
        for key, value in (
            ("microscope", preset.microscope_name),
            ("camera", preset.camera_name),
            ("imaging_method", preset.imaging_method),
        ):
            if key in self.fields:
                self.fields[key].setText(value)  # type: ignore[attr-defined]
        if preset.scales:
            scale = preset.scales[0]
            if "objective" in self.fields:
                self.fields["objective"].setText(scale.objective)  # type: ignore[attr-defined]
            if "magnification" in self.fields:
                self.fields["magnification"].setText(f"{scale.magnification:g}x")  # type: ignore[attr-defined]
        self._loading = False
        self._store_current_metadata()

    def _apply_metadata_preset_name(self, category: str, name: str) -> None:
        preset = next(
            (
                item
                for item in self.project.metadata_presets.get(category, [])
                if item.get("name") == name
            ),
            None,
        )
        if preset is None:
            return
        self._loading = True
        for key, value in preset.items():
            if key == "objectives" and isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    objective = str(first.get("objective", ""))
                    magnification = str(first.get("magnification", ""))
                    if objective and "objective" in self.fields:
                        self.fields["objective"].setText(objective)  # type: ignore[attr-defined]
                    if magnification and "magnification" in self.fields:
                        self.fields["magnification"].setText(magnification)  # type: ignore[attr-defined]
                continue
            if key == "name" or key not in self.fields:
                continue
            editor = self.fields[key]
            if isinstance(editor, QComboBox):
                if editor.findText(value) < 0:
                    editor.addItem(value)
                editor.setCurrentText(value)
            else:
                editor.setText(value)
        self._loading = False
        self._store_current_metadata()

    def _store_current_metadata(self) -> None:
        if self._loading or self._current_asset_id is None:
            return
        asset = self.project.assets.get(self._current_asset_id)
        if asset is None:
            return
        metadata = dict(asset.metadata)
        metadata["metadata_profile"] = self.profile_combo.currentText()
        for key, editor in self.fields.items():
            value = (
                editor.currentText().strip()
                if isinstance(editor, QComboBox)
                else editor.text().strip()
            )
            if value:
                metadata[key] = value
            else:
                metadata.pop(key, None)
        notes = self.notes.toPlainText().strip()
        if notes:
            metadata["notes"] = notes
        else:
            metadata.pop("notes", None)
        if metadata == asset.metadata:
            return
        asset.metadata = metadata
        self.project.touch()
        if self.metadataChanged is not None:
            self.metadataChanged()
