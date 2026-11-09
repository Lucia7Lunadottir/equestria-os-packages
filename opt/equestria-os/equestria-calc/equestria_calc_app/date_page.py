"""calc: date page."""
from __future__ import annotations

import datetime as dt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout
from .dates import WEEKDAYS, date_diff, parse_date
from .localization import live_i18n, tr
from .widgets import PageBase, mk


class DatePage(PageBase):
    pref = (480, 600)
    minimum = (420, 520)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)
        today = dt.date.today().strftime("%d.%m.%Y")
        self.d1, self.d2, self.days = QLineEdit(today), QLineEdit(today), QLineEdit("30")
        for e in (self.d1, self.d2):
            live_i18n.call(e.setPlaceholderText, tr("date_page.dd_mm_yyyy"))
        live_i18n.call(self.days.setPlaceholderText, tr("date_page.number_days_may_negative"))
        self.res_diff, self.res_add = live_i18n.call(QLabel, ""), live_i18n.call(QLabel, "")
        for lab in (self.res_diff, self.res_add):
            lab.setObjectName("out")
            lab.setWordWrap(True)
        t1 = mk(tr("date_page.today"), "small", expand=False)
        t1.clicked.connect(lambda: live_i18n.call(self.d1.setText, dt.date.today().strftime("%d.%m.%Y")))
        t2 = mk(tr("date_page.today"), "small", expand=False)
        t2.clicked.connect(lambda: live_i18n.call(self.d2.setText, dt.date.today().strftime("%d.%m.%Y")))
        v.addWidget(self._cap(tr("date_page.first_date")))
        r1 = QHBoxLayout()
        r1.addWidget(self.d1, 1)
        r1.addWidget(t1)
        v.addLayout(r1)
        v.addWidget(self._cap(tr("date_page.second_date")))
        r2 = QHBoxLayout()
        r2.addWidget(self.d2, 1)
        r2.addWidget(t2)
        v.addLayout(r2)
        v.addWidget(self._cap(tr("date_page.difference")))
        v.addWidget(self.res_diff)
        v.addWidget(self._cap(tr("date_page.first_date_days")))
        v.addWidget(self.days)
        v.addWidget(self.res_add)
        v.addStretch()
        for e in (self.d1, self.d2, self.days):
            e.textChanged.connect(self._update)
        self._update()

    @staticmethod
    def _cap(text: str) -> QLabel:
        lab = live_i18n.call(QLabel, text)
        lab.setObjectName("h2")
        return lab

    @staticmethod
    def _flag(edit: QLineEdit, bad: bool) -> None:
        edit.setProperty("error", bad)
        edit.style().unpolish(edit)
        edit.style().polish(edit)

    def _update(self) -> None:
        a = b = None
        for edit, name in ((self.d1, "a"), (self.d2, "b")):
            try:
                d = parse_date(edit.text())
                self._flag(edit, False)
            except ValueError:
                d = None
                self._flag(edit, bool(edit.text().strip()))
            if name == "a":
                a = d
            else:
                b = d
        if a and b:
            n, y, m, r = date_diff(a, b)
            w, wd = divmod(n, 7)
            live_i18n.call(self.res_diff.setText, tr("date_page.days_wk_days_yr_mo", n, w, wd, y, m, r))
        else:
            live_i18n.call(self.res_diff.setText, tr("date_page.enter_both_dates_dd_mm"))
        try:
            k = int(self.days.text().strip())
            self._flag(self.days, False)
        except ValueError:
            k = None
            self._flag(self.days, bool(self.days.text().strip()))
        if a and k is not None:
            try:
                r = a + dt.timedelta(days=k)
                live_i18n.call(self.res_add.setText, live_i18n.format_text('{0}, {1}', r.strftime('%d.%m.%Y'), WEEKDAYS[r.weekday()]))
            except OverflowError:
                live_i18n.call(self.res_add.setText, tr("date_page.date_out_range"))
        else:
            live_i18n.call(self.res_add.setText, "—")
