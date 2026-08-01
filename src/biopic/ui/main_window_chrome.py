"""Main-window visual chrome helpers."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from biopic.ui.app_icon import biopic_logo_path

MAIN_WINDOW_STYLESHEET = """
QMainWindow, QMenuBar, QMenu, QToolBar, QStatusBar, QDockWidget {
    background: palette(window);
    color: palette(window-text);
}
QDialog,
QMessageBox {
    background: palette(window);
    color: palette(window-text);
}
QMessageBox QLabel,
QDialog QLabel {
    color: palette(window-text);
    background: transparent;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: palette(mid);
}
QMenu {
    background: palette(base);
    color: palette(text);
    border: 1px solid palette(dark);
}
QMenu::item {
    color: palette(text);
    background: transparent;
    padding: 4px 24px 4px 18px;
}
QMenu::item:selected {
    color: palette(highlighted-text);
    background: palette(highlight);
}
QMenu::item:disabled {
    color: palette(mid);
}
QMenuBar::item:checked {
    background: palette(highlight);
    color: palette(highlighted-text);
    border: 1px solid palette(light);
}
QMenuBar::item {
    min-width: 92px;
    padding: 6px 10px;
    margin: 2px;
    border-radius: 3px;
}
QMenuBar::separator {
    width: 1px;
    background: palette(mid);
    margin: 5px 7px;
}
QToolTip {
    color: #000000;
    background-color: #ffffff;
    border: 1px solid #707070;
    padding: 3px;
}
QPushButton, QToolButton {
    background: palette(button);
    color: palette(button-text);
    border: 1px solid palette(dark);
    border-radius: 2px;
    padding: 4px;
}
QPushButton:hover, QToolButton:hover {
    background: palette(mid);
}
QLineEdit,
QPlainTextEdit,
QTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QTableWidget,
QListWidget,
QTreeWidget {
    background: palette(base);
    color: palette(text);
    border: 1px solid palette(dark);
}
QComboBox QAbstractItemView {
    background: palette(base);
    color: palette(text);
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}
QHeaderView::section {
    background: palette(alternate-base);
    color: palette(text);
    border: 1px solid palette(dark);
}
QTabWidget::pane {
    border: 1px solid palette(dark);
    background: palette(window);
}
QTabBar::tab {
    background: palette(button);
    color: palette(button-text);
    border: 1px solid palette(dark);
    padding: 5px 9px;
}
QTabBar::tab:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}
QTabBar::tab:hover {
    background: palette(mid);
}
QStackedWidget {
    background: palette(base);
    color: palette(text);
    border: 1px solid palette(dark);
}
"""


class WorkspaceWatermark(QWidget):
    """Transparent global empty-project watermark."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._watermark_pixmap = QPixmap(str(biopic_logo_path()))

    def paintEvent(self, _event: object) -> None:
        if self._watermark_pixmap.isNull():
            return
        painter = QPainter(self)
        target_size = min(self.width(), self.height()) * 0.88
        if target_size <= 1:
            return
        target = QRectF(
            (self.width() - target_size) / 2.0,
            (self.height() - target_size) / 2.0,
            target_size,
            target_size,
        )
        painter.setOpacity(0.045)
        painter.drawPixmap(target, self._watermark_pixmap, QRectF(self._watermark_pixmap.rect()))
