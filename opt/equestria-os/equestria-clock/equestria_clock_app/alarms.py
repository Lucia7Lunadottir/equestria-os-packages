"""clock: alarms."""
from __future__ import annotations

import datetime as dt
import math
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from .dialogs import AlarmDialog
from .localization import live_i18n, tr
from .schedule import describe_days, fmt_in, next_fire
from .widgets import Switch


class AlarmRow(QFrame):
    def __init__(self, alarm: dict, on_toggle, on_edit, on_delete):
        super().__init__()
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 12, 12, 12)
        h.setSpacing(12)
        t = live_i18n.call(QLabel, alarm["time"])
        t.setObjectName("rowtime")
        mid = QVBoxLayout()
        mid.setSpacing(0)
        name = live_i18n.call(QLabel, alarm["label"] or tr("common.alarm"))
        name.setObjectName("rowname")
        days = live_i18n.call(QLabel, describe_days(alarm["days"]))
        days.setObjectName("subtle")
        mid.addWidget(name)
        mid.addWidget(days)
        sw = Switch(alarm["enabled"])
        sw.toggled.connect(on_toggle)
        edit = live_i18n.call(QPushButton, "✎")
        edit.setObjectName("flat")
        live_i18n.call(edit.setToolTip, tr("alarms.edit"))
        edit.clicked.connect(on_edit)
        rm = live_i18n.call(QPushButton, "✕")
        rm.setObjectName("flat")
        live_i18n.call(rm.setToolTip, tr("alarms.delete"))
        rm.clicked.connect(on_delete)
        h.addWidget(t)
        h.addLayout(mid, 1)
        h.addWidget(sw)
        h.addWidget(edit)
        h.addWidget(rm)
        if not alarm["enabled"]:
            for w in (t, name, days):
                w.setEnabled(False)


class AlarmTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 14, 0, 0)
        v.setSpacing(12)
        top = QHBoxLayout()
        self.next_label = live_i18n.call(QLabel, )
        self.next_label.setObjectName("subtle")
        add = live_i18n.call(QPushButton, tr("alarms.new_alarm"))
        add.setObjectName("primary")
        add.clicked.connect(lambda: self.edit(None))
        top.addWidget(self.next_label, 1)
        top.addWidget(add)
        v.addLayout(top)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        self.rows = QVBoxLayout(body)
        self.rows.setContentsMargins(0, 0, 6, 0)
        self.rows.setSpacing(10)
        self.rows.addStretch()
        scroll.setWidget(body)
        v.addWidget(scroll, 1)
        self.refresh()

    @property
    def alarms(self):
        return self.win.settings["alarms"]

    def refresh(self) -> None:
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.alarms:
            e = live_i18n.call(QLabel, tr("alarms.no_alarms_yet_press_new"))
            e.setObjectName("subtle")
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setContentsMargins(0, 50, 0, 0)
            self.rows.insertWidget(0, e)
        for i, a in enumerate(self.alarms):
            row = AlarmRow(a, lambda on, i=i: self.toggle(i, on),
                           lambda _=False, i=i: self.edit(i),
                           lambda _=False, i=i: self.delete(i))
            self.rows.insertWidget(i, row)
        self.update_next()

    def update_next(self) -> None:
        nf = next_fire(self.alarms, dt.datetime.now())
        if not nf:
            live_i18n.call(self.next_label.setText, tr("alarms.no_alarms_enabled"))
            return
        a, when = nf
        mins = math.ceil((when - dt.datetime.now()).total_seconds() / 60)
        live_i18n.call(self.next_label.setText, tr("alarms.next", fmt_in(max(1, mins))))

    def toggle(self, i: int, on: bool) -> None:
        self.alarms[i]["enabled"] = on
        self.win.settings.save()
        self.refresh()

    def edit(self, i) -> None:
        dlg = AlarmDialog(self.win, self.alarms[i] if i is not None else None)
        if dlg.exec():
            data = dlg.result_data()
            if i is None:
                self.alarms.append(data)
            else:
                self.alarms[i] = data
            self.alarms.sort(key=lambda a: a["time"])
            self.win.settings.save()
            self.refresh()

    def delete(self, i: int) -> None:
        del self.alarms[i]
        self.win.settings.save()
        self.refresh()
