from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtWidgets import QApplication, QWidget


class _QtBot:
    def __init__(self) -> None:
        self._widgets: list[QWidget] = []

    def addWidget(self, widget: QWidget) -> None:
        self._widgets.append(widget)

    def close(self) -> None:
        for widget in reversed(self._widgets):
            widget.close()
        self._widgets.clear()


@pytest.fixture
def workspace_tmp_path() -> Iterator[Path]:
    """Provide a pytest temp directory inside the writable workspace."""
    root = Path(__file__).resolve().parents[1] / "test_artifacts"
    path = root / uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def qtbot() -> Iterator[_QtBot]:
    QApplication.instance() or QApplication([])
    bot = _QtBot()
    try:
        yield bot
    finally:
        bot.close()


@pytest.fixture(autouse=True)
def isolated_ui_defaults(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    settings_dir = Path(__file__).resolve().parents[1] / "test_artifacts" / "qsettings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / f"{uuid4().hex}.ini"
    monkeypatch.setenv("BIOPIC_SETTINGS_FILE", str(settings_file))
    try:
        yield
    finally:
        settings_file.unlink(missing_ok=True)
