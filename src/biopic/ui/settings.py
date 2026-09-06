"""Small persistent UI settings helpers."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QSize
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QScrollArea, QVBoxLayout, QWidget

from biopic.app.branding import APP_NAME, APP_ORGANIZATION

DEBUG_OPTIONS_SETTING_KEY = "options/debug_options_enabled"
SAVE_OPTIONS_SETTING_KEY = "options/project_save"


def ui_settings() -> QSettings:
    """Return the application settings store."""
    settings_file = os.environ.get("BIOPIC_SETTINGS_FILE")
    if settings_file:
        return QSettings(settings_file, QSettings.Format.IniFormat)
    return QSettings(APP_ORGANIZATION, APP_NAME)


def restore_dialog_size(dialog: QDialog, key: str, default: QSize) -> None:
    """Restore a dialog size and persist the adjusted size when it closes."""
    settings = ui_settings()
    stored = settings.value(f"dialogs/{key}/size")
    if isinstance(stored, QSize) and stored.isValid():
        dialog.resize(_clamped_dialog_size(dialog, stored))
    else:
        dialog.resize(_clamped_dialog_size(dialog, default))
    dialog.setSizeGripEnabled(True)
    dialog.finished.connect(lambda _result: save_dialog_size(dialog, key))


def save_dialog_size(dialog: QDialog, key: str) -> None:
    """Persist the current dialog size."""
    ui_settings().setValue(f"dialogs/{key}/size", dialog.size())


def remembered_open_file(
    parent: QWidget,
    title: str,
    key: str,
    filters: str,
) -> str:
    """Open a file dialog in the last folder used for this key."""
    settings = ui_settings()
    start = str(settings.value(f"folders/{key}", ""))
    filename, _selected = QFileDialog.getOpenFileName(parent, title, start, filters)
    if filename:
        settings.setValue(f"folders/{key}", str(Path(filename).parent))
    return filename


def remembered_open_files(
    parent: QWidget,
    title: str,
    key: str,
    filters: str,
) -> list[str]:
    """Open a multi-file dialog in the last folder used for this key."""
    settings = ui_settings()
    start = str(settings.value(f"folders/{key}", ""))
    filenames, _selected = QFileDialog.getOpenFileNames(parent, title, start, filters)
    if filenames:
        settings.setValue(f"folders/{key}", str(Path(filenames[0]).parent))
    return filenames


def remembered_save_file(
    parent: QWidget,
    title: str,
    key: str,
    filters: str,
    suggested_name: str = "",
) -> str:
    """Open a save dialog in the last folder used for this key."""
    settings = ui_settings()
    folder = str(settings.value(f"folders/{key}", ""))
    start = str(Path(folder) / suggested_name) if folder and suggested_name else folder
    dialog = QFileDialog(parent, title, start, filters)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, False)
    if suggested_name:
        dialog.selectFile(suggested_name)
    filename = ""
    if dialog.exec() == QDialog.DialogCode.Accepted:
        filename = _apply_selected_save_filter_suffix(
            dialog.selectedFiles()[0],
            dialog.selectedNameFilter(),
        )
    if filename:
        settings.setValue(f"folders/{key}", str(Path(filename).parent))
    return filename


def _apply_selected_save_filter_suffix(filename: str, selected_filter: str) -> str:
    """Make a save-dialog path match the selected file-type filter."""
    if not filename:
        return filename
    extensions = _extensions_from_name_filter(selected_filter)
    if not extensions:
        return filename
    path = Path(filename)
    suffix = path.suffix.lower()
    normalized = {extension.lower() for extension in extensions}
    if suffix in normalized:
        return str(path)
    return str(path.with_suffix(extensions[0]))


def _extensions_from_name_filter(name_filter: str) -> list[str]:
    """Extract extensions from a Qt name filter such as ``JPEG (*.jpg *.jpeg)``."""
    return [
        match.group(1).lower()
        for match in re.finditer(r"\*([.][A-Za-z0-9]+)", name_filter)
    ]


def settings_json(key: str, default: Any) -> Any:
    """Read a JSON-compatible value from settings."""
    raw = ui_settings().value(key)
    if not isinstance(raw, str) or not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def set_settings_json(key: str, value: Any) -> None:
    """Write a JSON-compatible value to settings."""
    ui_settings().setValue(key, json.dumps(value, indent=2, sort_keys=True))


def scrollable_dialog_body(dialog: QDialog) -> QWidget:
    """Return a widget for scrollable dialog content plus an outer dialog layout."""
    outer = QVBoxLayout(dialog)
    scroll = QScrollArea(dialog)
    scroll.setWidgetResizable(True)
    body = QWidget(scroll)
    scroll.setWidget(body)
    outer.addWidget(scroll)
    return body


def _clamped_dialog_size(dialog: QDialog, requested: QSize) -> QSize:
    screen = dialog.screen() or QApplication.primaryScreen()
    if screen is None:
        return requested
    available = screen.availableGeometry().size()
    return QSize(
        max(320, min(requested.width(), max(320, available.width() // 2))),
        max(240, min(requested.height(), max(240, available.height() // 2))),
    )
