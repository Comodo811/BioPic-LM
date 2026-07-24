"""Application appearance and palette helpers."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from biopic.ui.settings import ui_settings

THEME_SETTING_KEY = "appearance/theme"
DEFAULT_THEME = "dark"


def current_theme() -> str:
    """Return the persisted application theme name."""
    value = ui_settings().value(THEME_SETTING_KEY, DEFAULT_THEME)
    return str(value) if str(value) in {"dark", "light"} else DEFAULT_THEME


def set_current_theme(theme: str) -> None:
    """Persist the selected application theme name."""
    selected = theme if theme in {"dark", "light"} else DEFAULT_THEME
    ui_settings().setValue(THEME_SETTING_KEY, selected)


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply the requested Qt palette to the running application."""
    if theme == "light":
        app.setPalette(_light_palette())
    else:
        app.setPalette(_dark_palette())


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#3f3f3f"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#2b2b2b"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#343434"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2b2b2b"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#eeeeee"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#eeeeee"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2c2c2c"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#eeeeee"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#6f879c"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#565656"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#777777"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#1f1f1f"))
    return palette


def _light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f4f4f4"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#202020"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#eeeeee"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#202020"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#202020"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#e8e8e8"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#202020"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4d7899"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#d0d0d0"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#9a9a9a"))
    return palette
