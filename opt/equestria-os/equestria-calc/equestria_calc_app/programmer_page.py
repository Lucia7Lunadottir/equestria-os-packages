"""calc: programmer page."""
from __future__ import annotations

import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
from .localization import live_i18n, tr
from .programmer_math import BITS, fmt_base, group, prog_eval
from .widgets import HistoryPanel, PageBase, fit, mk, right_label, toggle_neg


PROG_ROWS = [["A", "<<", ">>", "(", ")", "⌫"],
             ["B", "AND", "7", "8", "9", "÷"],
             ["C", "OR", "4", "5", "6", "×"],
             ["D", "XOR", "1", "2", "3", "−"],
             ["E", "NOT", "±", "0", "mod", "+"],
             ["F", "CE"]]


PROG_TXT = {"AND": "&", "OR": "|", "XOR": "^", "NOT": "~", "mod": "%"}


DIGITS = "0123456789ABCDEF"


class ProgPage(PageBase):
    pref = (640, 780)
    minimum = (560, 680)

    def __init__(self):
        super().__init__()
        self.base, self.bits = 10, 64
        self.expr, self.prev, self.fresh, self.last = "", "", False, 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        top = QHBoxLayout()
        self.hist_btn = mk(tr("common.history"), "small", expand=False)
        self.hist_btn.setCheckable(True)
        self.hist_btn.toggled.connect(self._toggle_history)
        self.word = QComboBox()
        live_i18n.call(self.word.addItems, list(BITS))
        self.word.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.word.currentTextChanged.connect(self._word_changed)
        top.addWidget(self.hist_btn)
        top.addStretch()
        top.addWidget(self.word)
        v.addLayout(top)
        self.expr_label = right_label("expr", 26)
        self.result_label = right_label("result", 56)
        v.addWidget(self.expr_label)
        v.addWidget(self.result_label)

        self.rows = {}
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        for name, base in (("HEX", 16), ("DEC", 10), ("OCT", 8), ("BIN", 2)):
            b = mk(name, "row", expand=False)
            b.setCheckable(True)
            b.setFont(mono)
            b.clicked.connect(lambda _=False, bs=base: self.set_base(bs))
            self.rows[base] = b
            v.addWidget(b)

        self.hist = HistoryPanel()
        self.hist.setVisible(False)
        self.hist.picked.connect(self._pick)
        v.addWidget(self.hist, 1)

        self.body = QWidget()
        g = QGridLayout(self.body)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        self.keys = {}
        for r, row in enumerate(PROG_ROWS):
            for c, lab in enumerate(row):
                name = ("clr" if lab == "CE" else "num" if lab in DIGITS or lab == "±"
                        else "op")
                b = mk(lab, name, self.press)
                self.keys[lab] = b
                g.addWidget(b, r, c)
        g.addWidget(mk("=", "eq", self.press), len(PROG_ROWS) - 1, 2, 1, 4)
        v.addWidget(self.body, 4)
        self._base_changed()
        self._refresh()

    def press(self, t: str) -> None:
        if t == "CE":
            self.expr, self.prev, self.fresh = "", "", False
        elif t == "⌫":
            self.expr = re.sub(r"(?:<<|>>|.)$", "", self.expr)
            self.fresh = False
        elif t == "=":
            self._equals()
            return
        elif t == "±":
            if self.expr and not re.search(r"[-+×÷−*/%&|^~(]$|<<$|>>$", self.expr):
                self.expr = toggle_neg(self.expr, r"[0-9A-F]+")
                self.fresh = False
        else:
            tok = PROG_TXT.get(t, t)
            if self.fresh and tok in DIGITS:
                self.expr = ""
            self.expr += tok
            self.fresh = False
        self._refresh()

    def _balanced(self) -> str:
        e = re.sub(r"(?:[-+×÷−*/%&|^]|<<|>>)+$", "", self.expr)  # висящие операторы
        return e + ")" * (e.count("(") - e.count(")"))

    def _equals(self) -> None:
        if not self.expr or self.fresh:
            return
        try:
            v = prog_eval(self._balanced(), self.base, self.bits)
        except Exception:
            fit(self.result_label, tr("common.error"), True, 38)
            return
        res = fmt_base(v, self.base, self.bits)
        self.hist.add(f"{self.expr}  =  {res}  (base {self.base})", res)
        self.prev, self.expr, self.fresh, self.last = self.expr, res, True, v
        self._refresh()

    def _refresh(self) -> None:
        live_i18n.call(self.expr_label.setText, f"{self.prev} =" if self.fresh else self.expr)
        valid = True
        if not self.expr:
            v = 0
        else:
            try:
                v = prog_eval(self._balanced(), self.base, self.bits)
            except Exception:
                valid, v = False, self.last
        self.last = v
        text = fmt_base(v, self.base, self.bits) if valid else (self.expr[-20:] or "0")
        fit(self.result_label, group(text) if (valid and self.base in (2, 16, 8)) else text, False, 38)
        for base, b in self.rows.items():
            s = fmt_base(v, base, self.bits)
            s = f"{v:,}".replace(",", " ") if base == 10 else group(s)
            live_i18n.call(b.setText, f"{ {16: 'HEX', 10: 'DEC', 8: 'OCT', 2: 'BIN'}[base] }   {s}")
            b.setChecked(base == self.base)

    def set_base(self, base: int) -> None:
        if base != self.base:
            try:
                v = prog_eval(self._balanced(), self.base, self.bits) if self.expr else 0
            except Exception:
                v = self.last
            had = bool(self.expr)
            self.base = base
            self.expr = fmt_base(v, base, self.bits) if had else ""
            self.fresh, self.prev = had, ""
            self._base_changed()
        self._refresh()

    def _base_changed(self) -> None:
        for i, d in enumerate(DIGITS):
            self.keys[d].setEnabled(i < self.base)

    def _word_changed(self, name: str) -> None:
        self.bits = BITS[name]
        self._refresh()

    def _toggle_history(self, on: bool) -> None:
        self.hist.setVisible(on)
        self.body.setVisible(not on)

    def _pick(self, res: str) -> None:
        self.expr, self.fresh, self.prev = res, True, ""
        self.hist_btn.setChecked(False)
        self._refresh()

    def copy_text(self):
        return self.result_label.text().replace(" ", "")

    def key(self, e) -> bool:
        k, txt = e.key(), e.text().upper()
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or txt == "=":
            self.press("=")
        elif k == Qt.Key.Key_Backspace:
            self.press("⌫")
        elif k == Qt.Key.Key_Escape:
            self.press("CE")
        elif txt and txt in DIGITS and DIGITS.index(txt) < self.base:
            self.press(txt)
        elif txt and txt in "+-*/%&|^~()":
            self.press({"*": "×", "/": "÷", "-": "−"}.get(txt, txt))
        elif txt in ("<", ">"):
            self.press(txt * 2)
        else:
            return False
        return True
