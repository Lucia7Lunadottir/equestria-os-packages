from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QDoubleSpinBox, QSlider,
                             QFrame, QFontComboBox, QColorDialog, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPixmap, QPainter
from core.locale import tr

LABEL_STYLE = "color:#a6adc8;font-size:11px;background:transparent;"
SPIN_STYLE = ("QSpinBox,QDoubleSpinBox{background:#313244;color:#cdd6f4;border:none;"
              "padding:2px 4px;border-radius:3px;}"
              "QSpinBox::up-button,QSpinBox::down-button,"
              "QDoubleSpinBox::up-button,QDoubleSpinBox::down-button{width:14px;}")
TOGGLE_BTN_STYLE = ("QPushButton{background:#313244;color:#cdd6f4;border:none;padding:4px 8px;"
                    "border-radius:4px;font-weight:bold;}"
                    "QPushButton:checked{background:#cba6f7;color:#1e1e2e;}"
                    "QPushButton:hover{background:#45475a;}")
HEADER_STYLE = ("color:#7f849c;font-size:10px;font-weight:bold;letter-spacing:1px;"
                "background:transparent;padding:8px 0 4px 0;")
SLIDER_STYLE = ("QSlider::groove:horizontal{height:4px;background:#313244;border-radius:2px;}"
                "QSlider::handle:horizontal{background:#a855f7;width:12px;height:12px;margin:-4px 0;border-radius:6px;}"
                "QSlider::sub-page:horizontal{background:#7c3aed;border-radius:2px;}")


def _make_sep():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#313244;background:#313244;max-height:1px;margin:4px 0;")
    return f


class CharacterPanel(QWidget):
    option_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        # ---------- Section header ----------
        self._header_lbl = QLabel("CHARACTER")
        self._header_lbl.setStyleSheet(HEADER_STYLE)
        layout.addWidget(self._header_lbl)
        layout.addWidget(_make_sep())

        # ---------- Font family ----------
        self._font_family_lbl = QLabel("Font:")
        self._font_family_lbl.setStyleSheet(LABEL_STYLE)
        layout.addWidget(self._font_family_lbl)

        self._font_combo = QFontComboBox()
        self._font_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._font_combo.currentFontChanged.connect(
            lambda f: self.option_changed.emit("font_family", f.family())
        )
        layout.addWidget(self._font_combo)

        # ---------- Size ----------
        size_row = QWidget()
        size_lo = QHBoxLayout(size_row)
        size_lo.setContentsMargins(0, 0, 0, 0)
        size_lo.setSpacing(6)

        self._size_lbl = QLabel("Size:")
        self._size_lbl.setStyleSheet(LABEL_STYLE)
        size_lo.addWidget(self._size_lbl)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 999)
        self._size_spin.setValue(24)
        self._size_spin.setSuffix(" pt")
        self._size_spin.setStyleSheet(SPIN_STYLE)
        self._size_spin.setFixedWidth(72)
        self._size_spin.valueChanged.connect(lambda v: self.option_changed.emit("font_size", v))
        size_lo.addWidget(self._size_spin)
        size_lo.addStretch()
        layout.addWidget(size_row)

        layout.addWidget(_make_sep())

        # ---------- B / I / U toggle row ----------
        style_row = QWidget()
        style_lo = QHBoxLayout(style_row)
        style_lo.setContentsMargins(0, 0, 0, 0)
        style_lo.setSpacing(4)

        self._btn_bold = QPushButton("B")
        self._btn_bold.setCheckable(True)
        bold_font = QFont()
        bold_font.setBold(True)
        self._btn_bold.setFont(bold_font)
        self._btn_bold.setFixedSize(28, 28)
        self._btn_bold.setStyleSheet(TOGGLE_BTN_STYLE)
        self._btn_bold.toggled.connect(lambda v: self.option_changed.emit("font_bold", v))

        self._btn_italic = QPushButton("I")
        self._btn_italic.setCheckable(True)
        ital_font = QFont()
        ital_font.setItalic(True)
        self._btn_italic.setFont(ital_font)
        self._btn_italic.setFixedSize(28, 28)
        self._btn_italic.setStyleSheet(TOGGLE_BTN_STYLE)
        self._btn_italic.toggled.connect(lambda v: self.option_changed.emit("font_italic", v))

        self._btn_underline = QPushButton("U")
        self._btn_underline.setCheckable(True)
        under_font = QFont()
        under_font.setUnderline(True)
        self._btn_underline.setFont(under_font)
        self._btn_underline.setFixedSize(28, 28)
        self._btn_underline.setStyleSheet(TOGGLE_BTN_STYLE)
        self._btn_underline.toggled.connect(lambda v: self.option_changed.emit("font_underline", v))

        style_lo.addWidget(self._btn_bold)
        style_lo.addWidget(self._btn_italic)
        style_lo.addWidget(self._btn_underline)

        # Color button
        self._current_color = QColor(0, 0, 0)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(36, 28)
        self._color_btn.setToolTip("Text color")
        self._color_btn.clicked.connect(self._pick_color)
        self._update_color_btn()
        style_lo.addWidget(self._color_btn)
        style_lo.addStretch()

        layout.addWidget(style_row)
        layout.addWidget(_make_sep())

        # ---------- Tracking ----------
        tracking_lbl_row = QWidget()
        tracking_lbl_lo = QHBoxLayout(tracking_lbl_row)
        tracking_lbl_lo.setContentsMargins(0, 0, 0, 0)
        tracking_lbl_lo.setSpacing(6)

        self._tracking_lbl = QLabel("Tracking:")
        self._tracking_lbl.setStyleSheet(LABEL_STYLE)
        tracking_lbl_lo.addWidget(self._tracking_lbl)

        self._tracking_spin = QSpinBox()
        self._tracking_spin.setRange(-500, 500)
        self._tracking_spin.setValue(0)
        self._tracking_spin.setStyleSheet(SPIN_STYLE)
        self._tracking_spin.setFixedWidth(64)
        tracking_lbl_lo.addWidget(self._tracking_spin)
        tracking_lbl_lo.addStretch()
        layout.addWidget(tracking_lbl_row)

        self._tracking_slider = QSlider(Qt.Orientation.Horizontal)
        self._tracking_slider.setRange(-500, 500)
        self._tracking_slider.setValue(0)
        self._tracking_slider.setStyleSheet(SLIDER_STYLE)

        # Connect tracking widgets bidirectionally
        self._tracking_slider.valueChanged.connect(self._on_tracking_slider)
        self._tracking_spin.valueChanged.connect(self._on_tracking_spin)

        layout.addWidget(self._tracking_slider)

        layout.addWidget(_make_sep())

        # ---------- Leading ----------
        leading_row = QWidget()
        leading_lo = QHBoxLayout(leading_row)
        leading_lo.setContentsMargins(0, 0, 0, 0)
        leading_lo.setSpacing(6)

        self._leading_lbl = QLabel("Leading:")
        self._leading_lbl.setStyleSheet(LABEL_STYLE)
        leading_lo.addWidget(self._leading_lbl)

        self._leading_spin = QDoubleSpinBox()
        self._leading_spin.setRange(0.5, 5.0)
        self._leading_spin.setSingleStep(0.1)
        self._leading_spin.setValue(1.0)
        self._leading_spin.setDecimals(2)
        self._leading_spin.setStyleSheet(SPIN_STYLE)
        self._leading_spin.setFixedWidth(72)
        self._leading_spin.valueChanged.connect(lambda v: self.option_changed.emit("text_leading", v))
        leading_lo.addWidget(self._leading_spin)
        leading_lo.addStretch()
        layout.addWidget(leading_row)

        layout.addStretch(1)

    # ---------------------------------------------------------------- Tracking sync

    def _on_tracking_slider(self, value: int):
        self._tracking_spin.blockSignals(True)
        self._tracking_spin.setValue(value)
        self._tracking_spin.blockSignals(False)
        self.option_changed.emit("font_tracking", value)

    def _on_tracking_spin(self, value: int):
        self._tracking_slider.blockSignals(True)
        self._tracking_slider.setValue(value)
        self._tracking_slider.blockSignals(False)
        self.option_changed.emit("font_tracking", value)

    # ---------------------------------------------------------------- Color

    def _pick_color(self):
        color = QColorDialog.getColor(
            self._current_color,
            self,
            "Text Color",
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._current_color = color
            self._update_color_btn()
            self.option_changed.emit("text_color", QColor(color))

    def _update_color_btn(self):
        pix = QPixmap(20, 20)
        pix.fill(self._current_color)
        p = QPainter(pix)
        p.setPen(QColor(80, 80, 80))
        p.drawRect(0, 0, 19, 19)
        p.end()
        from PyQt6.QtGui import QIcon
        self._color_btn.setIcon(QIcon(pix))
        self._color_btn.setStyleSheet(
            f"QPushButton{{background:{self._current_color.name()};border:1px solid #555;"
            f"border-radius:3px;padding:0;}}"
            f"QPushButton:hover{{border:1px solid #a6adc8;}}"
        )

    # ---------------------------------------------------------------- Public

    def refresh(self, canvas):
        if canvas is None:
            return
        opts = getattr(canvas, "tool_opts", {})

        self._font_combo.blockSignals(True)
        family = opts.get("font_family", "Sans Serif")
        font = QFont(family)
        self._font_combo.setCurrentFont(font)
        self._font_combo.blockSignals(False)

        self._size_spin.blockSignals(True)
        self._size_spin.setValue(int(opts.get("font_size", 24)))
        self._size_spin.blockSignals(False)

        self._btn_bold.blockSignals(True)
        self._btn_bold.setChecked(bool(opts.get("font_bold", False)))
        self._btn_bold.blockSignals(False)

        self._btn_italic.blockSignals(True)
        self._btn_italic.setChecked(bool(opts.get("font_italic", False)))
        self._btn_italic.blockSignals(False)

        self._btn_underline.blockSignals(True)
        self._btn_underline.setChecked(bool(opts.get("font_underline", False)))
        self._btn_underline.blockSignals(False)

        color = opts.get("text_color", QColor(0, 0, 0))
        if isinstance(color, str):
            color = QColor(color)
        if isinstance(color, QColor) and color.isValid():
            self._current_color = color
            self._update_color_btn()

        tracking = int(opts.get("font_tracking", 0))
        self._tracking_spin.blockSignals(True)
        self._tracking_slider.blockSignals(True)
        self._tracking_spin.setValue(tracking)
        self._tracking_slider.setValue(tracking)
        self._tracking_spin.blockSignals(False)
        self._tracking_slider.blockSignals(False)

        self._leading_spin.blockSignals(True)
        self._leading_spin.setValue(float(opts.get("text_leading", 1.0)))
        self._leading_spin.blockSignals(False)

    def retranslate(self):
        self._header_lbl.setText(
            tr("char.title") if tr("char.title") != "char.title" else "CHARACTER"
        )
        self._font_family_lbl.setText(
            tr("char.font") if tr("char.font") != "char.font" else "Font:"
        )
        self._size_lbl.setText(
            tr("char.size") if tr("char.size") != "char.size" else "Size:"
        )
        self._tracking_lbl.setText(
            tr("char.tracking") if tr("char.tracking") != "char.tracking" else "Tracking:"
        )
        self._leading_lbl.setText(
            tr("char.leading") if tr("char.leading") != "char.leading" else "Leading:"
        )
