"""Shared workspace stylesheets."""

MEASURE_SCALE_STYLESHEET = """
QWidget, QDialog, QMenu {
    background: palette(window);
    color: palette(window-text);
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
QMenu::item:disabled {
    color: palette(mid);
}
QMenu::item:selected {
    color: palette(highlighted-text);
    background: palette(highlight);
}
QGroupBox {
    border: 1px solid palette(dark);
    margin-top: 10px;
    padding: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QLabel {
    color: palette(window-text);
}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget {
    background: palette(base);
    color: palette(text);
    border: 1px solid palette(dark);
    selection-background-color: palette(highlight);
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
    padding: 4px;
}
QListWidget {
    background: palette(base);
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
QPushButton, QToolButton {
    background: palette(button);
    color: palette(button-text);
    border: 1px solid palette(dark);
    border-radius: 2px;
    padding: 4px 8px;
}
QPushButton:hover, QToolButton:hover {
    background: palette(mid);
}
QMenu::separator {
    height: 1px;
    background: palette(mid);
    margin: 4px 8px;
}
"""
