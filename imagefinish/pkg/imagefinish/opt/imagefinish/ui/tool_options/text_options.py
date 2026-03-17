from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel,
                             QSpinBox, QPushButton, QFontComboBox, QColorDialog, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from .base_options import BaseOptions
from core.locale import tr


class TextOptions(BaseOptions):
    apply_styles_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setSpacing(4)

        font_combo = QFontComboBox()
        font_combo.setFixedWidth(250)
        font_combo.setCurrentFont(QFont("Sans Serif"))
        font_combo.currentFontChanged.connect(
            lambda f: self.option_changed.emit("font_family", f.family()))

        size_sp = QSpinBox()
        size_sp.setRange(4, 500)
        size_sp.setValue(24)
        size_sp.setFixedWidth(52)
        size_sp.valueChanged.connect(lambda v: self.option_changed.emit("font_size", v))

        bold_f = QFont(); bold_f.setBold(True)
        ital_f = QFont(); ital_f.setItalic(True)
        unde_f = QFont(); unde_f.setUnderline(True)
        stri_f = QFont(); stri_f.setStrikeOut(True)

        btn_b = self._style_btn("B", "font_bold",      bold_f)
        btn_i = self._style_btn("I", "font_italic",    ital_f)
        btn_u = self._style_btn("U", "font_underline", unde_f)
        btn_s = self._style_btn("S", "font_strikeout", stri_f)

        clr_text = self._color_btn(QColor(0, 0, 0), "text_color")
        
        stroke_sp = QSpinBox()
        stroke_sp.setRange(0, 50)
        stroke_sp.setValue(0)
        stroke_sp.setFixedWidth(44)
        stroke_sp.valueChanged.connect(lambda v: self.option_changed.emit("text_stroke_w", v))

        clr_stroke = self._color_btn(QColor(0, 0, 0), "text_stroke_color")

        btn_shadow = QPushButton(tr("opts.shadow"))
        btn_shadow.setObjectName("styleToggleBtn")
        btn_shadow.setCheckable(True)
        btn_shadow.setFixedHeight(26)
        btn_shadow.toggled.connect(lambda v: self.option_changed.emit("text_shadow", v))

        sdx = QSpinBox(); sdx.setRange(-50, 50); sdx.setValue(3); sdx.setFixedWidth(44)
        sdx.valueChanged.connect(lambda v: self.option_changed.emit("text_shadow_dx", v))

        sdy = QSpinBox(); sdy.setRange(-50, 50); sdy.setValue(3); sdy.setFixedWidth(44)
        sdy.valueChanged.connect(lambda v: self.option_changed.emit("text_shadow_dy", v))

        clr_shadow = self._color_btn(QColor(0, 0, 0, 160), "text_shadow_color")

        apply_btn = QPushButton(tr("opts.apply"))
        apply_btn.setObjectName("smallBtn")
        apply_btn.setFixedHeight(26)
        apply_btn.clicked.connect(self.apply_styles_requested.emit)

        stroke_lbl = QLabel(tr("opts.stroke_abbr"))
        stroke_lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")

        self.layout.addWidget(font_combo)
        self.layout.addWidget(size_sp)
        self.layout.addWidget(self._sep())
        self.layout.addWidget(btn_b)
        self.layout.addWidget(btn_i)
        self.layout.addWidget(btn_u)
        self.layout.addWidget(btn_s)
        self.layout.addWidget(clr_text)
        self.layout.addWidget(self._sep())
        self.layout.addWidget(stroke_lbl)
        self.layout.addWidget(stroke_sp)
        self.layout.addWidget(clr_stroke)
        self.layout.addWidget(self._sep())
        self.layout.addWidget(btn_shadow)
        self.layout.addWidget(sdx)
        self.layout.addWidget(sdy)
        self.layout.addWidget(clr_shadow)
        self.layout.addWidget(self._sep())
        self.layout.addWidget(apply_btn)
        self.layout.addStretch()

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    def _style_btn(self, label: str, key: str, font: QFont | None = None) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("styleToggleBtn")
        btn.setCheckable(True)
        btn.setFixedSize(26, 26)
        if font:
            btn.setFont(font)
        btn.toggled.connect(lambda checked: self.option_changed.emit(key, checked))
        return btn

    def _color_btn(self, color: QColor, key: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(26, 26)

        def _set_color(c: QColor):
            btn.setStyleSheet(
                f"background:{c.name()}; border:1px solid #555; border-radius:3px;")
            self.option_changed.emit(key, QColor(c))

        _set_color(color)
        btn.clicked.connect(lambda: self._pick_color(btn, _set_color))
        return btn

    def _pick_color(self, btn, callback):
        c = QColorDialog.getColor(options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
                                   parent=btn)
        if c.isValid():
            callback(c)
