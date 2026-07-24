"""BioPic LM application entry point."""

from __future__ import annotations

import logging
import sys

from biopic.app.branding import APP_NAME, APP_ORGANIZATION, WINDOWS_APP_USER_MODEL_ID
from biopic.models.project import Project
from biopic.utilities.logging import configure_logging
from biopic.utilities.video_logging import configure_video_backend_logging

LOGGER = logging.getLogger(__name__)


configure_video_backend_logging()


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        LOGGER.debug("Could not set Windows application user model ID.", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    """Run the Qt application."""
    configure_logging()
    _set_windows_app_id()
    args = sys.argv if argv is None else argv
    try:
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication

        from biopic.ui.app_icon import biopic_app_icon
        from biopic.ui.main_window import MainWindow
        from biopic.ui.theme import apply_theme, current_theme
    except ImportError as exc:
        LOGGER.error("PySide6 is required to launch the GUI: %s", exc)
        return 2

    app = QApplication(args)
    qInstallMessageHandler(_qt_message_handler)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    apply_theme(app, current_theme())
    icon = biopic_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow(Project.new("Untitled Project"))
    window.resize(1280, 820)
    window.show()
    return app.exec()


def _qt_message_handler(mode: object, context: object, message: str) -> None:
    del mode
    category = getattr(context, "category", "")
    if "FFmpeg log:" in message or "qt.multimedia.ffmpeg" in str(category):
        return
    LOGGER.debug("Qt: %s", message)


if __name__ == "__main__":
    raise SystemExit(main())
