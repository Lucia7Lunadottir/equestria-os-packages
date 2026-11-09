"""calendar: reminder popup."""
from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout
from datetime import date, datetime
from .dates import MONTHS_G
from .localization import live_i18n, tr


class ReminderPopup(QDialog):
    def __init__(self, app, rem: dict, d: date, occ: datetime):
        super().__init__(None)
        self.app, self.rem, self.d = app, rem, d
        live_i18n.call(self.setWindowTitle, tr("common.reminder"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(400)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(8)
        hint = live_i18n.call(QLabel, tr("reminder_popup.reminder"))
        hint.setObjectName("h2")
        v.addWidget(hint)
        title = live_i18n.call(QLabel, rem["title"])
        title.setObjectName("h3")
        title.setWordWrap(True)
        v.addWidget(title)
        v.addWidget(self._when(occ))
        if rem.get("notes"):
            n = live_i18n.call(QLabel, rem["notes"])
            n.setWordWrap(True)
            v.addWidget(n)
        row = QHBoxLayout()
        snooze = live_i18n.call(QPushButton, tr("reminder_popup.snooze"))
        menu = QMenu(snooze)
        for label, mins in ((tr("reminder_popup.5_minutes"), 5), (tr("reminder_popup.15_minutes"), 15), (tr("reminder_popup.1_hour"), 60), (tr("reminder_popup.until_tomorrow"), -1)):
            live_i18n.call(menu.addAction, label).triggered.connect(lambda _=False, m=mins: self._snooze(m))
        snooze.setMenu(menu)
        done = live_i18n.call(QPushButton, tr("reminder_popup.done"))
        done.clicked.connect(self._done)
        ok = live_i18n.call(QPushButton, tr("reminder_popup.close"))
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        row.addWidget(snooze)
        row.addWidget(done)
        row.addStretch()
        row.addWidget(ok)
        v.addLayout(row)
        self.rep_timer = None
        if rem.get("sound", True) and app.cfg["repeat_sound"]:
            self.count = 0
            self.rep_timer = QTimer(self, interval=9000)
            self.rep_timer.timeout.connect(self._again)
            self.rep_timer.start()

    def _when(self, occ: datetime) -> QLabel:
        now = datetime.now()
        day = {0: tr("common.today"), 1: tr("common.tomorrow"), -1: tr("reminder_popup.yesterday")}.get((occ.date() - now.date()).days,
                                                          live_i18n.format_text('{0} {1}', occ.day, MONTHS_G[occ.month - 1]))
        text = day + (tr("reminder_popup.all_day") if self.rem.get("all_day") else f", {occ:%H:%M}")
        mins = int((occ - now).total_seconds() // 60)
        if not self.rem.get("all_day") and 0 < mins < 1440:
            text += tr("reminder_popup.h_min", mins // 60, mins % 60) if mins >= 60 else tr("reminder_popup.min", mins)
        lbl = live_i18n.call(QLabel, text)
        lbl.setObjectName("hint")
        return lbl

    def _again(self) -> None:
        self.count += 1
        if self.count >= 10:
            self.rep_timer.stop()
            return
        self.app.play_sound()

    def _snooze(self, mins: int) -> None:
        self.app.snooze(self.rem, self.d, mins)
        self.accept()

    def _done(self) -> None:
        self.app.set_done(self.rem, self.d, True)
        self.accept()

    def done(self, r) -> None:
        if self.rep_timer:
            self.rep_timer.stop()
        super().done(r)
