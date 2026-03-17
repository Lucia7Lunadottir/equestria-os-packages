from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QSpinBox, QFrame, QToolButton, QButtonGroup,
                             QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal
from core.locale import tr

LABEL_STYLE = "color:#a6adc8;font-size:11px;background:transparent;"
SPIN_STYLE = ("QSpinBox{background:#313244;color:#cdd6f4;border:none;"
              "padding:2px 4px;border-radius:3px;}"
              "QSpinBox::up-button,QSpinBox::down-button{width:14px;}")
HEADER_STYLE = ("color:#7f849c;font-size:10px;font-weight:bold;letter-spacing:1px;"
                "background:transparent;padding:8px 0 4px 0;")
ALIGN_BTN_STYLE = ("QToolButton{background:#313244;color:#cdd6f4;border:none;"
                   "padding:4px 10px;border-radius:4px;font-size:13px;font-weight:bold;}"
                   "QToolButton:checked{background:#cba6f7;color:#1e1e2e;}"
                   "QToolButton:hover:!checked{background:#45475a;}")


def _make_sep():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#313244;background:#313244;max-height:1px;margin:4px 0;")
    return f


def _spin_row(label_widget, spin_widget):
    row = QWidget()
    lo = QHBoxLayout(row)
    lo.setContentsMargins(0, 0, 0, 0)
    lo.setSpacing(6)
    lo.addWidget(label_widget)
    lo.addStretch()
    lo.addWidget(spin_widget)
    return row


class ParagraphPanel(QWidget):
    option_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        # ---------- Header ----------
        self._header_lbl = QLabel("PARAGRAPH")
        self._header_lbl.setStyleSheet(HEADER_STYLE)
        layout.addWidget(self._header_lbl)
        layout.addWidget(_make_sep())

        # ---------- Alignment ----------
        align_lbl = QLabel("Alignment:")
        align_lbl.setStyleSheet(LABEL_STYLE)
        layout.addWidget(align_lbl)

        align_row = QWidget()
        align_lo = QHBoxLayout(align_row)
        align_lo.setContentsMargins(0, 0, 0, 0)
        align_lo.setSpacing(4)

        self._btn_left    = QToolButton(); self._btn_left.setText("\u2261 L")
        self._btn_center  = QToolButton(); self._btn_center.setText("\u2261 C")
        self._btn_right   = QToolButton(); self._btn_right.setText("\u2261 R")
        self._btn_justify = QToolButton(); self._btn_justify.setText("\u2261 J")

        self._align_btns = {
            "left":    self._btn_left,
            "center":  self._btn_center,
            "right":   self._btn_right,
            "justify": self._btn_justify,
        }

        self._align_group = QButtonGroup(self)
        self._align_group.setExclusive(True)

        for key, btn in self._align_btns.items():
            btn.setCheckable(True)
            btn.setStyleSheet(ALIGN_BTN_STYLE)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(28)
            self._align_group.addButton(btn)
            align_lo.addWidget(btn)
            # Use default-argument capture to avoid closure-over-loop-variable
            btn.clicked.connect(lambda checked, k=key: self.option_changed.emit("text_align", k))

        self._btn_left.setChecked(True)
        layout.addWidget(align_row)
        layout.addWidget(_make_sep())

        # ---------- Indent controls ----------
        self._indent_left_lbl = QLabel("Left Indent:")
        self._indent_left_lbl.setStyleSheet(LABEL_STYLE)
        self._indent_left_spin = QSpinBox()
        self._indent_left_spin.setRange(0, 999)
        self._indent_left_spin.setValue(0)
        self._indent_left_spin.setSuffix(" px")
        self._indent_left_spin.setStyleSheet(SPIN_STYLE)
        self._indent_left_spin.setFixedWidth(72)
        self._indent_left_spin.valueChanged.connect(
            lambda v: self.option_changed.emit("text_indent_left", v))
        layout.addWidget(_spin_row(self._indent_left_lbl, self._indent_left_spin))

        self._indent_right_lbl = QLabel("Right Indent:")
        self._indent_right_lbl.setStyleSheet(LABEL_STYLE)
        self._indent_right_spin = QSpinBox()
        self._indent_right_spin.setRange(0, 999)
        self._indent_right_spin.setValue(0)
        self._indent_right_spin.setSuffix(" px")
        self._indent_right_spin.setStyleSheet(SPIN_STYLE)
        self._indent_right_spin.setFixedWidth(72)
        self._indent_right_spin.valueChanged.connect(
            lambda v: self.option_changed.emit("text_indent_right", v))
        layout.addWidget(_spin_row(self._indent_right_lbl, self._indent_right_spin))

        self._indent_first_lbl = QLabel("First Line:")
        self._indent_first_lbl.setStyleSheet(LABEL_STYLE)
        self._indent_first_spin = QSpinBox()
        self._indent_first_spin.setRange(-999, 999)
        self._indent_first_spin.setValue(0)
        self._indent_first_spin.setSuffix(" px")
        self._indent_first_spin.setStyleSheet(SPIN_STYLE)
        self._indent_first_spin.setFixedWidth(72)
        self._indent_first_spin.valueChanged.connect(
            lambda v: self.option_changed.emit("text_indent_first", v))
        layout.addWidget(_spin_row(self._indent_first_lbl, self._indent_first_spin))

        layout.addWidget(_make_sep())

        # ---------- Spacing controls ----------
        self._space_before_lbl = QLabel("Before \u00b6:")
        self._space_before_lbl.setStyleSheet(LABEL_STYLE)
        self._space_before_spin = QSpinBox()
        self._space_before_spin.setRange(0, 999)
        self._space_before_spin.setValue(0)
        self._space_before_spin.setSuffix(" px")
        self._space_before_spin.setStyleSheet(SPIN_STYLE)
        self._space_before_spin.setFixedWidth(72)
        self._space_before_spin.valueChanged.connect(
            lambda v: self.option_changed.emit("text_space_before", v))
        layout.addWidget(_spin_row(self._space_before_lbl, self._space_before_spin))

        self._space_after_lbl = QLabel("After \u00b6:")
        self._space_after_lbl.setStyleSheet(LABEL_STYLE)
        self._space_after_spin = QSpinBox()
        self._space_after_spin.setRange(0, 999)
        self._space_after_spin.setValue(0)
        self._space_after_spin.setSuffix(" px")
        self._space_after_spin.setStyleSheet(SPIN_STYLE)
        self._space_after_spin.setFixedWidth(72)
        self._space_after_spin.valueChanged.connect(
            lambda v: self.option_changed.emit("text_space_after", v))
        layout.addWidget(_spin_row(self._space_after_lbl, self._space_after_spin))

        layout.addStretch(1)

    # ---------------------------------------------------------------- Public

    def refresh(self, canvas):
        if canvas is None:
            return
        opts = getattr(canvas, "tool_opts", {})

        align = opts.get("text_align", "left")
        btn = self._align_btns.get(align)
        if btn:
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)

        def _set_spin(spin, key, default=0):
            spin.blockSignals(True)
            spin.setValue(int(opts.get(key, default)))
            spin.blockSignals(False)

        _set_spin(self._indent_left_spin,   "text_indent_left",   0)
        _set_spin(self._indent_right_spin,  "text_indent_right",  0)
        _set_spin(self._indent_first_spin,  "text_indent_first",  0)
        _set_spin(self._space_before_spin,  "text_space_before",  0)
        _set_spin(self._space_after_spin,   "text_space_after",   0)

    def retranslate(self):
        self._header_lbl.setText(
            tr("para.title") if tr("para.title") != "para.title" else "PARAGRAPH"
        )
        self._indent_left_lbl.setText(
            tr("para.indent_left") if tr("para.indent_left") != "para.indent_left" else "Left Indent:"
        )
        self._indent_right_lbl.setText(
            tr("para.indent_right") if tr("para.indent_right") != "para.indent_right" else "Right Indent:"
        )
        self._indent_first_lbl.setText(
            tr("para.indent_first") if tr("para.indent_first") != "para.indent_first" else "First Line:"
        )
        self._space_before_lbl.setText(
            tr("para.space_before") if tr("para.space_before") != "para.space_before" else "Before \u00b6:"
        )
        self._space_after_lbl.setText(
            tr("para.space_after") if tr("para.space_after") != "para.space_after" else "After \u00b6:"
        )
