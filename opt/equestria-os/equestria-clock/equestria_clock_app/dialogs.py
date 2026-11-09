"""clock: dialogs."""
from __future__ import annotations

import datetime as dt
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
from .localization import live_i18n, tr
from .schedule import DAYS_SHORT
from .widgets import SoundPicker, TimeField


class RingDialog(QDialog):
    """Окно «звонит!» поверх всех окон."""
    snoozed = pyqtSignal()

    def __init__(self, title: str, text: str, snooze_min: int = 0):
        super().__init__(None)
        live_i18n.call(self.setWindowTitle, title)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(400)
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 28, 32, 28)
        v.setSpacing(10)
        t = live_i18n.call(QLabel, title)
        t.setObjectName("ringtitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setWordWrap(True)
        s = live_i18n.call(QLabel, text)
        s.setObjectName("subtle")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        v.addWidget(s)
        v.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        if snooze_min:
            b = live_i18n.call(QPushButton, tr("dialogs.snooze_min", snooze_min))
            b.clicked.connect(self._snooze)
            row.addWidget(b)
        stop = live_i18n.call(QPushButton, tr("common.stop"))
        stop.setObjectName("primary")
        stop.setDefault(True)
        stop.clicked.connect(self.accept)
        row.addWidget(stop)
        v.addLayout(row)

    def _snooze(self) -> None:
        self.snoozed.emit()
        self.accept()


class AlarmDialog(QDialog):
    def __init__(self, win, alarm: dict | None):
        super().__init__(win)
        live_i18n.call(self.setWindowTitle, tr("common.alarm"))
        self.setMinimumWidth(420)
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(14)

        if alarm:
            h, m = map(int, alarm["time"].split(":"))
        else:
            n = dt.datetime.now() + dt.timedelta(minutes=5)
            h, m = n.hour, n.minute
        self.hour = TimeField(23, wrap=True, caption=tr("common.hours"))
        self.minute = TimeField(59, wrap=True, caption=tr("common.minutes"))
        self.hour.setValue(h)
        self.minute.setValue(m)
        trow = QHBoxLayout()
        trow.addStretch()
        trow.addWidget(self.hour)
        colon = live_i18n.call(QLabel, ":")
        colon.setObjectName("colon")
        colon.setAlignment(Qt.AlignmentFlag.AlignTop)
        colon.setContentsMargins(0, 28, 0, 0)
        trow.addWidget(colon)
        trow.addWidget(self.minute)
        trow.addStretch()
        v.addLayout(trow)

        self.name = QLineEdit(alarm["label"] if alarm else "")
        live_i18n.call(self.name.setPlaceholderText, tr("dialogs.name_optional"))
        v.addWidget(self.name)

        self.day_btns = []
        drow = QHBoxLayout()
        drow.setSpacing(6)
        for i, d in enumerate(DAYS_SHORT):
            b = live_i18n.call(QPushButton, d)
            b.setObjectName("day")
            b.setCheckable(True)
            b.setChecked(bool(alarm) and i in alarm["days"])
            self.day_btns.append(b)
            drow.addWidget(b)
        v.addLayout(drow)
        hint = live_i18n.call(QLabel, tr("dialogs.no_days_selected_alarm_will"))
        hint.setObjectName("subtle")
        v.addWidget(hint)

        self.sound = SoundPicker(win, allow_default=True)
        self.sound.set_value(alarm["sound"] if alarm else "")
        v.addWidget(self.sound)

        row = QHBoxLayout()
        row.setSpacing(10)
        cancel = live_i18n.call(QPushButton, tr("dialogs.cancel"))
        cancel.clicked.connect(self.reject)
        ok = live_i18n.call(QPushButton, tr("dialogs.save"))
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)

    def result_data(self) -> dict:
        return {
            "time": live_i18n.format_text('{0:02d}:{1:02d}', self.hour.value(), self.minute.value()),
            "label": self.name.text().strip(),
            "days": [i for i, b in enumerate(self.day_btns) if b.isChecked()],
            "enabled": True,
            "sound": self.sound.value(),
        }
