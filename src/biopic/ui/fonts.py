"""Font helpers for Qt widgets that need DirectWrite-safe families."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QFontComboBox

UNSAFE_FONT_FAMILIES = {
    "Fixedsys",
    "MS Sans Serif",
    "MS Serif",
    "System",
    "Terminal",
}

SAFE_FONT_FALLBACKS = (
    "Segoe UI",
    "Arial",
    "Helvetica",
    "Times New Roman",
)


def fallback_font_family() -> str:
    """Return a broadly available scalable font family."""
    families = set(QFontDatabase.families())
    for family in SAFE_FONT_FALLBACKS:
        if family in families and is_safe_font_family(family):
            return family
    default_family = QFont().defaultFamily()
    if is_safe_font_family(default_family):
        return default_family
    return "Arial"


def is_safe_font_family(family: str | None) -> bool:
    """Return whether Qt can render a font through DirectWrite reliably."""
    if family is None:
        return False
    clean_family = family.strip()
    if not clean_family or clean_family in UNSAFE_FONT_FAMILIES:
        return False
    try:
        return QFontDatabase.isSmoothlyScalable(clean_family)
    except RuntimeError:
        return False


def safe_font_family(family: str | None) -> str:
    """Return family when safe, otherwise a stable scalable fallback."""
    clean_family = family.strip() if family is not None else ""
    if is_safe_font_family(clean_family):
        return clean_family
    return fallback_font_family()


def configure_safe_font_combo(combo: QFontComboBox) -> None:
    """Restrict a font picker to scalable fonts and choose a safe default."""
    combo.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
    combo.setCurrentFont(QFont(fallback_font_family()))
