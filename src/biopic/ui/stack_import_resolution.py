"""Resolve duplicate stack imports that share names but differ by extension."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.io import RAW_EXTENSIONS, TIFF_EXTENSIONS
from biopic.ui.settings import restore_dialog_size


def resolve_stack_import_paths(parent: QWidget, paths: list[Path]) -> list[Path]:
    """Ask how to handle stack files that share a basename but have different types."""
    conflicts = duplicate_basename_extension_groups(paths)
    if not conflicts:
        return paths
    dialog = QDialog(parent)
    dialog.setWindowTitle("Resolve Stack File Types")
    restore_dialog_size(dialog, "stack_import_file_type_resolution", QSize(520, 420))
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        QLabel(
            "Files with the same name but different file types were detected. "
            "Choose how the stack import should handle these duplicates."
        )
    )
    discard_check = QCheckBox("Discard duplicate filenames with non-prioritized extensions")
    discard_check.setChecked(True)
    layout.addWidget(discard_check)

    extension_combo = QComboBox()
    for extension in prioritized_extensions(paths):
        extension_combo.addItem(extension.upper(), extension)
    layout.addWidget(QLabel("Prioritize file type"))
    layout.addWidget(extension_combo)

    tree = QTreeWidget()
    tree.setHeaderLabels(["Filename", "Detected files"])
    for stem, items in sorted(conflicts.items()):
        parent_item = QTreeWidgetItem([stem, f"{len(items)} file types"])
        for path in sorted(items, key=lambda item: item.suffix.lower()):
            parent_item.addChild(QTreeWidgetItem([path.name, path.suffix.lower()]))
        parent_item.setExpanded(True)
        tree.addTopLevelItem(parent_item)
    layout.addWidget(tree)

    def update_enabled() -> None:
        extension_combo.setEnabled(discard_check.isChecked())

    discard_check.toggled.connect(update_enabled)
    update_enabled()

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return []
    if not discard_check.isChecked():
        return paths
    return filter_duplicate_basename_extensions(
        paths,
        preferred_extension=str(extension_combo.currentData()),
    )


def duplicate_basename_extension_groups(paths: list[Path]) -> dict[str, list[Path]]:
    """Return files whose stem appears with more than one extension."""
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        by_stem[path.stem.casefold()].append(path)
    return {
        stem: items
        for stem, items in by_stem.items()
        if len({item.suffix.lower() for item in items}) > 1
    }


def prioritized_extensions(paths: list[Path]) -> list[str]:
    """Return detected extensions ordered by likely microscopy source quality."""
    extensions = {path.suffix.lower() for path in paths if path.suffix}
    return sorted(extensions, key=_extension_priority)


def filter_duplicate_basename_extensions(
    paths: list[Path],
    *,
    preferred_extension: str,
) -> list[Path]:
    """Keep only the preferred extension for conflicting basenames."""
    preferred = preferred_extension.lower()
    conflicts = duplicate_basename_extension_groups(paths)
    conflict_stems = set(conflicts)
    filtered: list[Path] = []
    for path in paths:
        stem = path.stem.casefold()
        if stem not in conflict_stems or path.suffix.lower() == preferred:
            filtered.append(path)
    return filtered


def _extension_priority(extension: str) -> tuple[int, str]:
    if extension in RAW_EXTENSIONS:
        return (0, extension)
    if extension in TIFF_EXTENSIONS:
        return (1, extension)
    return (2, extension)
