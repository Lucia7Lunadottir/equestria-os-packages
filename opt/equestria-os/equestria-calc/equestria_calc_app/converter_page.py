"""calc: converter page."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit, QVBoxLayout
from .arithmetic import fmt
from .localization import live_i18n, tr
from .units import CATS, convert
from .widgets import PageBase, mk


class ConverterPage(PageBase):
    pref = (480, 560)
    minimum = (420, 480)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)
        self.cat = QComboBox()

        for code in CATS:
            live_i18n.call(self.cat.addItem, tr(code), code)
        self.inp = QLineEdit("1")
        self.frm, self.to = QComboBox(), QComboBox()
        swap = mk(tr("converter_page.swap"), "small", expand=False)
        swap.clicked.connect(self._swap)
        self.out = QLineEdit()
        self.out.setReadOnly(True)
        for w in (self.cat, self.frm, self.to):
            w.setMinimumHeight(40)
        v.addWidget(self._cap(tr("converter_page.quantity")))
        v.addWidget(self.cat)
        v.addWidget(self._cap(tr("converter_page.from")))
        v.addWidget(self.inp)
        v.addWidget(self.frm)
        v.addWidget(swap)
        v.addWidget(self._cap(tr("converter_page.to")))
        v.addWidget(self.out)
        v.addWidget(self.to)
        v.addStretch()
        self.cat.currentIndexChanged.connect(self._fill)
        self.inp.textChanged.connect(self._update)
        self.frm.currentIndexChanged.connect(self._update)
        self.to.currentIndexChanged.connect(self._update)
        self._fill()

    @staticmethod
    def _cap(text: str) -> QLabel:
        lab = live_i18n.call(QLabel, text)
        lab.setObjectName("h2")
        return lab

    def _fill(self) -> None:
        units, i, j = CATS[self.cat.currentData()]
        for box, idx in ((self.frm, i), (self.to, j)):
            box.blockSignals(True)
            box.clear()

            for code, _ in units:
                live_i18n.call(box.addItem, tr(code), code)
            box.setCurrentIndex(idx)
            box.blockSignals(False)
        self._update()

    def _swap(self) -> None:
        i, j = self.frm.currentIndex(), self.to.currentIndex()
        self.frm.blockSignals(True)
        self.to.blockSignals(True)
        self.frm.setCurrentIndex(j)
        self.to.setCurrentIndex(i)
        self.frm.blockSignals(False)
        self.to.blockSignals(False)
        self._update()

    def _update(self) -> None:
        bad = False
        try:
            x = float(self.inp.text().replace(",", ".").replace(" ", ""))
            live_i18n.call(self.out.setText, fmt(convert(self.cat.currentData(), x,
                                         self.frm.currentData(), self.to.currentData())))
        except Exception:
            bad = bool(self.inp.text().strip())
            live_i18n.call(self.out.setText, "")
        self.inp.setProperty("error", bad)
        self.inp.style().unpolish(self.inp)
        self.inp.style().polish(self.inp)

    def copy_text(self):
        return None  # у полей свой Ctrl+C
