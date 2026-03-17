from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                             QGridLayout, QLabel, QPushButton, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QColor

from core.locale import tr

BTN_STYLE = ("QPushButton{background:#313244;color:#cdd6f4;border:none;"
             "padding:4px 10px;border-radius:4px;}"
             "QPushButton:hover{background:#45475a;}"
             "QPushButton:pressed{background:#585b70;}")
LABEL_STYLE = "color:#a6adc8;font-size:11px;"

DEFAULT_SWATCHES = [
    "#000000", "#1a1a1a", "#333333", "#4d4d4d", "#666666", "#808080",
    "#999999", "#b3b3b3", "#cccccc", "#e6e6e6", "#f2f2f2", "#ffffff",
    "#ff0000", "#ff8000", "#ffff00", "#00ff00", "#00ffff", "#0000ff",
    "#ff00ff", "#8000ff", "#ff0080", "#ff4040", "#ff8040", "#ffff40",
    "#40ff40", "#40ffff", "#4040ff", "#ff40ff", "#a0522d", "#8b4513",
    "#d2691e", "#cd853f", "#f4a460", "#deb887", "#d2b48c", "#ffdead",
]


class _SwatchLabel(QLabel):
    """A single 24×24 coloured swatch that responds to left/right clicks."""

    left_clicked  = pyqtSignal(QColor)
    right_clicked = pyqtSignal(QColor, object)   # color, global QPoint

    _STYLE_NORMAL   = "border:1px solid #45475a;"
    _STYLE_HOVER    = "border:1px solid #89b4fa;"

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(24, 24)
        self._update_style(False)
        self.setToolTip(color.name())

    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor):
        self._color = color
        self._update_style(False)
        self.setToolTip(color.name())

    def _update_style(self, hover: bool):
        border = self._STYLE_HOVER if hover else self._STYLE_NORMAL
        self.setStyleSheet(f"background:{self._color.name()};{border}")

    def enterEvent(self, ev):
        self._update_style(True)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._update_style(False)
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.left_clicked.emit(self._color)
        elif ev.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self._color, ev.globalPosition().toPoint())
        super().mousePressEvent(ev)


class SwatchesPanel(QWidget):
    """
    A grid of colour swatches.  Left-click selects as foreground colour.
    Right-click shows a context menu.
    """

    fg_color_selected     = pyqtSignal(QColor)
    bg_color_selected     = pyqtSignal(QColor)
    add_swatch_requested  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        self._current_fg = QColor("#000000")
        self._swatch_colors: list[QColor] = []
        self._swatch_widgets: list[_SwatchLabel] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Title
        self._title = QLabel(self._title_text())
        self._title.setObjectName("panelTitle")
        main_layout.addWidget(self._title)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{border:none;background:#1e1e2e;}")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background:#1e1e2e;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(3)

        self._scroll.setWidget(self._grid_widget)
        main_layout.addWidget(self._scroll, 1)

        # Bottom row: "+" button
        bottom_row = QWidget()
        bottom_lo = QHBoxLayout(bottom_row)
        bottom_lo.setContentsMargins(0, 0, 0, 0)
        bottom_lo.setSpacing(4)

        self._add_btn = QPushButton("+")
        self._add_btn.setStyleSheet(BTN_STYLE)
        self._add_btn.setFixedHeight(24)
        self._add_btn.setToolTip(tr("swatches.add_fg") if tr("swatches.add_fg") != "swatches.add_fg"
                                  else "Add current foreground color")
        self._add_btn.clicked.connect(self.add_swatch_requested.emit)
        bottom_lo.addStretch()
        bottom_lo.addWidget(self._add_btn)
        main_layout.addWidget(bottom_row)

        # Load persisted / default swatches
        self._load_swatches()
        self._rebuild_grid()

    # ----------------------------------------------------------------- public

    def add_swatch(self, color: QColor):
        """Add a new swatch with the given colour and persist."""
        self._swatch_colors.append(QColor(color))
        self._save_swatches()
        self._rebuild_grid()

    def set_fg_color(self, color: QColor):
        """Track the current foreground colour (used when adding swatches)."""
        self._current_fg = QColor(color)

    def retranslate(self):
        """Update translatable strings."""
        self._title.setText(self._title_text())

    def refresh(self, canvas):
        """No-op: swatches are independent of the canvas."""
        pass

    # ----------------------------------------------------------------- private

    def _title_text(self) -> str:
        val = tr("panel.swatches")
        return val if val != "panel.swatches" else "Swatches"

    def _load_swatches(self):
        settings = QSettings("ImageFinish", "Swatches")
        raw = settings.value("colors", None)
        if raw and isinstance(raw, list) and len(raw) > 0:
            self._swatch_colors = [QColor(c) for c in raw if QColor(c).isValid()]
        else:
            self._swatch_colors = [QColor(h) for h in DEFAULT_SWATCHES]

    def _save_swatches(self):
        settings = QSettings("ImageFinish", "Swatches")
        settings.setValue("colors", [c.name() for c in self._swatch_colors])

    def _rebuild_grid(self):
        """Clear and repopulate the grid widget."""
        # Remove existing widgets
        for w in self._swatch_widgets:
            w.deleteLater()
        self._swatch_widgets.clear()

        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = 9
        for idx, color in enumerate(self._swatch_colors):
            swatch = _SwatchLabel(color)
            swatch.left_clicked.connect(self._on_fg_clicked)
            swatch.right_clicked.connect(self._on_right_clicked)
            self._grid.addWidget(swatch, idx // cols, idx % cols)
            self._swatch_widgets.append(swatch)

    def _on_fg_clicked(self, color: QColor):
        self.fg_color_selected.emit(color)

    def _on_right_clicked(self, color: QColor, global_pos):
        menu = QMenu(self)

        # "Set as Background Color"
        bg_key = tr("swatches.set_bg")
        bg_text = bg_key if bg_key != "swatches.set_bg" else "Set as Background Color"
        bg_act = menu.addAction(bg_text)
        bg_act.triggered.connect(lambda: self.bg_color_selected.emit(color))

        menu.addSeparator()

        # "Add current foreground color"
        add_key = tr("swatches.add_fg")
        add_text = add_key if add_key != "swatches.add_fg" else "Add current foreground color"
        add_act = menu.addAction(add_text)
        add_act.triggered.connect(lambda: self.add_swatch(self._current_fg))

        menu.addSeparator()

        # "Delete swatch"
        del_key = tr("swatches.delete")
        del_text = del_key if del_key != "swatches.delete" else "Delete swatch"
        del_act = menu.addAction(del_text)
        del_act.triggered.connect(lambda: self._delete_swatch(color))

        menu.exec(global_pos)

    def _delete_swatch(self, color: QColor):
        """Remove the first swatch matching the given colour."""
        for i, c in enumerate(self._swatch_colors):
            if c.name() == color.name():
                self._swatch_colors.pop(i)
                break
        self._save_swatches()
        self._rebuild_grid()
