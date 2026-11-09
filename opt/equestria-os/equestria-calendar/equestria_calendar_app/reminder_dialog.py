"""calendar: reminder dialog."""
from __future__ import annotations

import uuid
from PyQt6.QtCore import QDate, QRegularExpression, Qt
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget
)
from datetime import date, datetime, time as dtime, timedelta
from .calendar_views import make_calendar
from .dates import REPEATS, WD_SHORT, add_months, parse_time
from .localization import live_i18n, tr
from .style import SWATCHES, THEME


class ReminderDialog(QDialog):
    ADV = [(tr("reminder_dialog.at_time_event"), 0), (tr("reminder_dialog.5_minutes_before"), 5), (tr("reminder_dialog.15_minutes_before"), 15), (tr("reminder_dialog.30_minutes_before"), 30),
           (tr("reminder_dialog.1_hour_before"), 60), (tr("reminder_dialog.1_day_before"), 1440)]
    UNITS = {"daily": tr("reminder_dialog.d"), "weekly": tr("reminder_dialog.wk"), "monthly": tr("reminder_dialog.mo"), "yearly": tr("reminder_dialog.yr")}

    def __init__(self, parent, rem: dict | None, day: date):
        super().__init__(parent)
        live_i18n.call(self.setWindowTitle, tr("common.reminder"))
        self.setMinimumWidth(520)
        self.rem = rem
        self.deleted = False
        r = rem or {}
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        self.title = QLineEdit(r.get("title", ""))
        live_i18n.call(self.title.setPlaceholderText, tr("reminder_dialog.what_remind"))
        v.addWidget(self.title)

        row = QHBoxLayout()
        row.addWidget(live_i18n.call(QLabel, tr("reminder_dialog.when")))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setCalendarWidget(make_calendar(bool(parent.cfg.get("sunday_first"))))
        self.date.setDisplayFormat("dd.MM.yyyy")
        sd = date.fromisoformat(r["date"]) if r else day
        self.date.setDate(QDate(sd.year, sd.month, sd.day))
        self.time = QLineEdit()
        self.time.setFixedWidth(80)
        self.time.setMaxLength(5)
        self.time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        live_i18n.call(self.time.setPlaceholderText, tr("reminder_dialog.hh_mm"))
        live_i18n.call(self.time.setToolTip, tr("reminder_dialog.time_e_g_14_30"))
        self.time.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9:. ]{0,5}")))
        self.time.editingFinished.connect(lambda: live_i18n.call(self.time.setText, parse_time(self.time.text(), "09:00")))
        self.date.setMinimumWidth(130)
        if r:
            t = dtime.fromisoformat(r.get("time", "09:00"))
        else:
            t = (datetime.now() + timedelta(hours=1)).time().replace(minute=0, second=0, microsecond=0)
        live_i18n.call(self.time.setText, f"{t.hour:02d}:{t.minute:02d}")
        self.allday = live_i18n.call(QCheckBox, tr("common.all_day"))
        self.allday.setChecked(bool(r.get("all_day", False)))
        self.allday.toggled.connect(self._sync)
        row.addWidget(self.date)
        row.addWidget(self.time)
        row.addWidget(self.allday)
        row.addStretch()
        v.addLayout(row)

        rrow = QHBoxLayout()
        self.repeat = QComboBox()
        for key, label in REPEATS:
            live_i18n.call(self.repeat.addItem, label, key)
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(r.get("repeat", "none"))))
        self.repeat.currentIndexChanged.connect(self._sync)
        self.every_lbl = live_i18n.call(QLabel, tr("reminder_dialog.every"))
        self.every = QSpinBox()
        self.every.setRange(1, 999)
        self.every.setValue(int(r.get("every", 1)))
        self.every.setMinimumWidth(70)
        self.unit = live_i18n.call(QLabel, "")
        rrow.addWidget(live_i18n.call(QLabel, tr("reminder_dialog.repeat")))
        rrow.addWidget(self.repeat)
        rrow.addWidget(self.every_lbl)
        rrow.addWidget(self.every)
        rrow.addWidget(self.unit)
        rrow.addStretch()
        v.addLayout(rrow)

        self.wd_box = QWidget()
        wl = QHBoxLayout(self.wd_box)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(live_i18n.call(QLabel, tr("reminder_dialog.by_days")))
        self.wd = []
        for i, n in enumerate(WD_SHORT):
            cb = live_i18n.call(QCheckBox, n)
            cb.setChecked(i in r.get("wdays", []))
            self.wd.append(cb)
            wl.addWidget(cb)
        wl.addStretch()
        v.addWidget(self.wd_box)

        self.until_box = QWidget()
        ul = QHBoxLayout(self.until_box)
        ul.setContentsMargins(0, 0, 0, 0)
        self.until_cb = live_i18n.call(QCheckBox, tr("reminder_dialog.repeat_until"))
        self.until = QDateEdit()
        self.until.setCalendarPopup(True)
        self.until.setCalendarWidget(make_calendar(bool(parent.cfg.get("sunday_first"))))
        self.until.setDisplayFormat("dd.MM.yyyy")
        ud = date.fromisoformat(r["until"]) if r.get("until") else add_months(sd, 12)
        self.until.setDate(QDate(ud.year, ud.month, ud.day))
        self.until_cb.setChecked(bool(r.get("until")))
        self.until_cb.toggled.connect(self._sync)
        ul.addWidget(self.until_cb)
        ul.addWidget(self.until)
        ul.addStretch()
        v.addWidget(self.until_box)

        arow = QHBoxLayout()
        self.alert = live_i18n.call(QCheckBox, tr("reminder_dialog.remind"))
        self.alert.setChecked(bool(r.get("alert", True)))
        self.alert.toggled.connect(self._sync)
        self.adv = QComboBox()
        for label, mins in self.ADV:
            live_i18n.call(self.adv.addItem, label, mins)
        self.adv.setCurrentIndex(max(0, self.adv.findData(int(r.get("advance", 0)))))
        self.sound = live_i18n.call(QCheckBox, tr("reminder_dialog.with_sound"))
        self.sound.setChecked(bool(r.get("sound", True)))
        arow.addWidget(self.alert)
        arow.addWidget(self.adv)
        arow.addWidget(self.sound)
        arow.addStretch()
        v.addLayout(arow)

        crow = QHBoxLayout()
        crow.addWidget(live_i18n.call(QLabel, tr("reminder_dialog.color")))
        self.group = QButtonGroup(self)
        cur = r.get("color", SWATCHES[0])
        for col in SWATCHES:
            b = live_i18n.call(QPushButton, )
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setProperty("hex", col)
            b.setChecked(col == cur)
            b.setStyleSheet(f"QPushButton {{ background:{col}; border-radius:11px; min-width:22px; max-width:22px;"
                            f" min-height:22px; max-height:22px; padding:0; border:3px solid transparent; }}"
                            f"QPushButton:checked {{ border:3px solid {THEME['text']}; }}")
            live_i18n.call(self.group.addButton, b)
            crow.addWidget(b)
        crow.addStretch()
        v.addLayout(crow)

        self.notes = QPlainTextEdit(r.get("notes", ""))
        live_i18n.call(self.notes.setPlaceholderText, tr("reminder_dialog.note_optional"))
        self.notes.setFixedHeight(80)
        v.addWidget(self.notes)

        brow = QHBoxLayout()
        if rem:
            d = live_i18n.call(QPushButton, tr("common.delete"))
            d.setObjectName("danger")
            d.clicked.connect(self._delete)
            brow.addWidget(d)
        brow.addStretch()
        cancel = live_i18n.call(QPushButton, tr("reminder_dialog.cancel"))
        cancel.clicked.connect(self.reject)
        ok = live_i18n.call(QPushButton, tr("reminder_dialog.save"))
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        brow.addWidget(cancel)
        brow.addWidget(ok)
        v.addLayout(brow)
        self._sync()
        self.title.setFocus()

    def _sync(self, *_) -> None:
        rep = self.repeat.currentData()
        self.time.setVisible(not self.allday.isChecked())
        for w in (self.every_lbl, self.every, self.unit):
            w.setVisible(rep != "none")
        live_i18n.call(self.unit.setText, self.UNITS.get(rep, ""))
        self.wd_box.setVisible(rep == "weekly")
        self.until_box.setVisible(rep != "none")
        self.until.setEnabled(self.until_cb.isChecked())
        self.adv.setEnabled(self.alert.isChecked())
        self.sound.setEnabled(self.alert.isChecked())

    def _delete(self) -> None:
        self.deleted = True
        self.accept()

    def result_rem(self) -> dict:
        qd = self.date.date()
        rep = self.repeat.currentData()
        checked = self.group.checkedButton()
        r = dict(self.rem) if self.rem else {"id": uuid.uuid4().hex[:8], "done": [], "skip": []}
        ud = self.until.date()
        r.update({
            "title": self.title.text().strip() or tr("reminder_dialog.untitled"),
            "notes": self.notes.toPlainText().strip(),
            "date": date(qd.year(), qd.month(), qd.day()).isoformat(),
            "all_day": self.allday.isChecked(),
            "time": parse_time(self.time.text(), (self.rem or {}).get("time", "09:00")),
            "repeat": rep,
            "every": self.every.value(),
            "wdays": [i for i, cb in enumerate(self.wd) if cb.isChecked()] if rep == "weekly" else [],
            "until": date(ud.year(), ud.month(), ud.day()).isoformat() if rep != "none" and self.until_cb.isChecked() else None,
            "alert": self.alert.isChecked(),
            "advance": self.adv.currentData(),
            "sound": self.sound.isChecked(),
            "color": checked.property("hex") if checked else SWATCHES[0],
        })
        return r
