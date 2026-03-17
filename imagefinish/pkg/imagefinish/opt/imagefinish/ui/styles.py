DARK_STYLE = """
/* ───────────────────────── Global ───────────────────────── */
QMainWindow, QDialog {
    background-color: #1e1e2e;
}
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}
QSplitter::handle {
    background-color: #313244;
    width: 2px;
    height: 2px;
}

/* ─────────────────────── Menu / Status ─────────────────── */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
    padding: 2px 4px;
}
QMenuBar::item:selected {
    background-color: #313244;
    border-radius: 4px;
}
QMenu {
    background-color: #24273a;
    border: 1px solid #414559;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 5px 24px 5px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #7c3aed;
    color: white;
}
QMenu::separator {
    height: 1px;
    background-color: #414559;
    margin: 4px 8px;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    font-size: 12px;
}

/* ─────────────────────── Toolbar (left) ────────────────── */
QWidget#toolbar {
    background-color: #181825;
    border-right: 1px solid #313244;
}
QPushButton#toolBtn, QToolButton#toolBtn {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #cdd6f4;
    font-size: 18px;
    padding: 4px;
}
QPushButton#toolBtn:hover, QToolButton#toolBtn:hover {
    background-color: #313244;
    border-color: #585b70;
}
QPushButton#toolBtn[active="true"], QToolButton#toolBtn[active="true"] {
    background-color: #7c3aed;
    border-color: #a855f7;
    color: white;
}
QToolButton#toolBtn::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: bottom right;
    bottom: 2px;
    right: 2px;
}

/* ──────────────────── Tool Options Bar ─────────────────── */
QWidget#toolOptionsBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    padding: 4px 8px;
}
QLabel#optLabel {
    color: #a6adc8;
    font-size: 12px;
    min-width: 70px;
}
QSlider::groove:horizontal {
    height: 4px;
    background-color: #313244;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background-color: #a855f7;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background-color: #7c3aed;
    border-radius: 2px;
}
QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
    padding: 4px 6px;
}
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
    padding: 3px 8px;
    min-width: 90px;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #45475a;
    border-radius: 0 3px 3px 0;
}
QComboBox::down-arrow {
    image: url(ui/arrow_down.svg);
    width: 10px;
    height: 6px;
}
QComboBox QAbstractItemView {
    background-color: #24273a;
    border: 1px solid #45475a;
    color: #cdd6f4;
    selection-background-color: #7c3aed;
    selection-color: #ffffff;
    outline: none;
}

/* ────────────────────────── Panels ─────────────────────── */
QWidget#panel {
    background-color: #181825;
    border-left: 1px solid #313244;
}
QLabel#panelTitle {
    font-size: 11px;
    font-weight: bold;
    color: #7f849c;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 8px 10px 4px 10px;
}
QTabWidget::pane {
    border: none;
    border-top: 1px solid #313244;
}
QTabBar::tab {
    background-color: #181825;
    color: #7f849c;
    padding: 6px 12px;
    border: none;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
QTabBar::tab:selected {
    color: #cdd6f4;
    background-color: #1e1e2e;
    border-bottom: 2px solid #7c3aed;
}
QTabBar::tab:hover:!selected {
    background-color: #24273a;
    color: #a6adc8;
}

/* ──────────────────────── Layer List ───────────────────── */
QListWidget {
    background-color: #181825;
    border: none;
    outline: none;
}
QListWidget::item {
    background-color: transparent;
    border-radius: 4px;
    padding: 2px 4px;
    min-height: 32px;
}
QListWidget::item:selected {
    background-color: #313244;
    color: white;
}
QListWidget::item:hover {
    background-color: #24273a;
}

/* ─────────────────────── Small Buttons ─────────────────── */
QPushButton#smallBtn {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
    padding: 3px 6px;
    font-size: 12px;
}
QPushButton#smallBtn:hover {
    background-color: #45475a;
}
QPushButton#smallBtn:pressed {
    background-color: #7c3aed;
}
QPushButton#dangerBtn {
    background-color: #8b1a1a;
    border: 1px solid #a03030;
    border-radius: 4px;
    color: #f38ba8;
    padding: 3px 6px;
    font-size: 12px;
}
QPushButton#dangerBtn:hover {
    background-color: #a03030;
}

/* ────────────────── Text-tool style toggle buttons ─────────── */
QPushButton#styleToggleBtn {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
    padding: 2px;
}
QPushButton#styleToggleBtn:hover {
    background-color: #45475a;
}
QPushButton#styleToggleBtn:checked {
    background-color: #7c3aed;
    border-color: #a855f7;
    color: #ffffff;
}
QPushButton#styleToggleBtn:checked:hover {
    background-color: #6d28d9;
}

/* ─────────────────────── Scroll Bars ───────────────────── */
QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal {
    background-color: #1e1e2e;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 4px;
    min-width: 20px;
}

/* ───────────────────── Input / Line Edit ───────────────── */
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
    padding: 4px 8px;
}
QLineEdit:focus {
    border-color: #a855f7;
}

/* ──────────────────────── Tooltips ─────────────────────── */
QToolTip {
    background-color: #24273a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 4px 8px;
}
"""
