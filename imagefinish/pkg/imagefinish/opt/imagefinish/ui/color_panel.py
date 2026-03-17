from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QGridLayout)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen

from core.locale import tr


class ColorSwatch(QFrame):
    clicked = pyqtSignal()

    def __init__(self, color: QColor, size: int = 34, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def color(self) -> QColor:
        return self._color

    def set_color(self, c: QColor):
        self._color = c
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        tile = 6
        for tx in range(0, self.width(), tile):
            for ty in range(0, self.height(), tile):
                shade = QColor(200, 200, 200) if (tx // tile + ty // tile) % 2 == 0 else QColor(240, 240, 240)
                p.fillRect(tx, ty, tile, tile, shade)
        p.fillRect(self.rect(), self._color)
        p.setPen(QPen(QColor(60, 60, 80), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    def mousePressEvent(self, _ev):
        self.clicked.emit()


class ColorPanel(QWidget):
    fg_changed = pyqtSignal(QColor)
    bg_changed = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 10)
        layout.setSpacing(6)

        self._title_lbl = QLabel(tr("panel.color"))
        self._title_lbl.setObjectName("panelTitle")
        layout.addWidget(self._title_lbl)

        swatch_container = QWidget()
        swatch_container.setFixedSize(120, 62)

        self._bg_swatch = ColorSwatch(QColor(255, 255, 255), size=38)
        self._fg_swatch = ColorSwatch(QColor(0, 0, 0), size=38)
        self._bg_swatch.setParent(swatch_container)
        self._fg_swatch.setParent(swatch_container)
        self._bg_swatch.move(14, 14)
        self._fg_swatch.move(0, 0)

        self._fg_swatch.clicked.connect(self._pick_fg)
        self._bg_swatch.clicked.connect(self._pick_bg)

        self._swap_btn = QPushButton("⇄")
        self._swap_btn.setObjectName("smallBtn")
        self._swap_btn.setFixedSize(26, 22)
        self._swap_btn.setToolTip(tr("color.swap_tooltip"))
        self._swap_btn.clicked.connect(self._swap)
        self._swap_btn.setParent(swatch_container)
        self._swap_btn.move(54, 38)

        self._reset_btn = QPushButton("↺")
        self._reset_btn.setObjectName("smallBtn")
        self._reset_btn.setFixedSize(26, 22)
        self._reset_btn.setToolTip(tr("color.reset_tooltip"))
        self._reset_btn.clicked.connect(self._reset)
        self._reset_btn.setParent(swatch_container)
        self._reset_btn.move(84, 38)

        layout.addWidget(swatch_container)

        self._hex_label = QLabel("#000000")
        self._hex_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hex_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self._hex_label)

        self._swatches_lbl = QLabel(tr("panel.swatches"))
        self._swatches_lbl.setStyleSheet("color: #7f849c; font-size: 11px; margin-top:4px;")
        layout.addWidget(self._swatches_lbl)

        palette_colors = [
            "#000000", "#ffffff", "#f38ba8", "#fab387",
            "#f9e2af", "#a6e3a1", "#89dceb", "#89b4fa",
            "#b4befe", "#cba6f7", "#45475a", "#9399b2",
        ]
        grid = QGridLayout()
        grid.setSpacing(3)
        for i, hex_color in enumerate(palette_colors):
            swatch = ColorSwatch(QColor(hex_color), size=20)
            swatch.clicked.connect(
                (lambda col: lambda: self._set_fg(QColor(col)))(hex_color)
            )
            grid.addWidget(swatch, i // 4, i % 4)
        layout.addLayout(grid)
        layout.addStretch()

    def fg(self) -> QColor:
        return self._fg_swatch.color()

    def bg(self) -> QColor:
        return self._bg_swatch.color()

    def set_fg(self, c: QColor):
        self._fg_swatch.set_color(c)
        self._hex_label.setText(c.name().upper())

    def set_bg(self, c: QColor):
        self._bg_swatch.set_color(c)

    def _pick_fg(self):
        from .hsv_picker import ColorPickerDialog
        c = ColorPickerDialog.get_color(self._fg_swatch.color(), self, tr("color.fg_title"))
        if c:
            self._set_fg(c)

    def _pick_bg(self):
        from .hsv_picker import ColorPickerDialog
        c = ColorPickerDialog.get_color(self._bg_swatch.color(), self, tr("color.bg_title"))
        if c:
            self._bg_swatch.set_color(c)
            self.bg_changed.emit(c)

    def retranslate(self):
        """Update all static labels/tooltips to the current locale."""
        self._title_lbl.setText(tr("panel.color"))
        self._swatches_lbl.setText(tr("panel.swatches"))
        self._swap_btn.setToolTip(tr("color.swap_tooltip"))
        self._reset_btn.setToolTip(tr("color.reset_tooltip"))

    def _set_fg(self, c: QColor):
        self._fg_swatch.set_color(c)
        self._hex_label.setText(c.name().upper())
        self.fg_changed.emit(c)

    def _swap(self):
        fg, bg = self._fg_swatch.color(), self._bg_swatch.color()
        self._fg_swatch.set_color(bg)
        self._bg_swatch.set_color(fg)
        self._hex_label.setText(bg.name().upper())
        self.fg_changed.emit(bg)
        self.bg_changed.emit(fg)

    def _reset(self):
        self._set_fg(QColor(0, 0, 0))
        self._bg_swatch.set_color(QColor(255, 255, 255))
        self.bg_changed.emit(QColor(255, 255, 255))
