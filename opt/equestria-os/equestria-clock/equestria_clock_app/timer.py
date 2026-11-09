"""clock: timer."""
from __future__ import annotations

import math
import time
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget
from .localization import live_i18n, tr
from .schedule import fmt_hms
from .widgets import RingWidget, TimeField


class TimerTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.state = "idle"  # idle / running / paused
        self.total_ms = 0
        self.remaining_ms = 0.0
        self.end = 0.0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(12)
        self.ring = RingWidget()
        v.addWidget(self.ring, 1)

        self.setup = QWidget()
        sv = QVBoxLayout(self.setup)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.h = TimeField(99, caption=tr("common.hours"))
        self.m = TimeField(59, caption=tr("common.minutes"))
        self.s = TimeField(59, caption=tr("timer.seconds"))
        hh, mm, ss = win.settings["timer"]
        self.h.setValue(int(hh))
        self.m.setValue(int(mm))
        self.s.setValue(int(ss))
        row.addStretch()
        for f in (self.h, self.m, self.s):
            row.addWidget(f)
            f.changed.connect(self._fields_changed)
        row.addStretch()
        sv.addLayout(row)
        pres = QHBoxLayout()
        pres.setSpacing(8)
        for label, secs in [(tr("timer.1_min"), 60), (tr("timer.5_min"), 300), (tr("timer.10_min"), 600),
                            (tr("timer.15_min"), 900), (tr("timer.30_min"), 1800), (tr("timer.1_hour"), 3600)]:
            b = live_i18n.call(QPushButton, label)
            b.clicked.connect(lambda _=False, s=secs: self._preset(s))
            pres.addWidget(b)
        sv.addLayout(pres)
        v.addWidget(self.setup)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.start_btn = live_i18n.call(QPushButton, tr("common.start"))
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.toggle)
        self.reset_btn = live_i18n.call(QPushButton, tr("common.reset"))
        self.reset_btn.clicked.connect(self.reset)
        btns.addWidget(self.start_btn, 1)
        btns.addWidget(self.reset_btn)
        v.addLayout(btns)

        self.clock = QTimer(self)
        self.clock.setInterval(100)
        self.clock.timeout.connect(self.tick)
        self._apply_state()

    def _fields_total(self) -> int:
        return self.h.value() * 3600 + self.m.value() * 60 + self.s.value()

    def _preset(self, secs: int) -> None:
        self.h.setValue(secs // 3600)
        self.m.setValue(secs % 3600 // 60)
        self.s.setValue(secs % 60)

    def _fields_changed(self) -> None:
        if self.state == "idle":
            self._apply_state()

    def _apply_state(self) -> None:
        st = self.state
        # таймер просыпается только пока идёт отсчёт
        if st == "running":
            self.clock.start()
        else:
            self.clock.stop()
        self.setup.setVisible(st == "idle")
        live_i18n.call(self.start_btn.setText, {"idle": tr("common.start"), "running": tr("timer.pause"), "paused": tr("timer.resume")}[st])
        self.reset_btn.setEnabled(st != "idle")
        if st == "idle":
            total = self._fields_total()
            self.ring.set_state(1.0, fmt_hms(total),
                                tr("timer.set") if total else tr("timer.set_time"))
        else:
            self._paint()

    def _paint(self) -> None:
        secs = math.ceil(self.remaining_ms / 1000)
        frac = self.remaining_ms / self.total_ms if self.total_ms else 0
        paused = self.state == "paused"
        self.ring.set_state(frac, fmt_hms(secs), tr("timer.paused") if paused else tr("timer.remaining"),
                            "yellow" if paused else "accent")

    def toggle(self) -> None:
        if self.state == "idle":
            total = self._fields_total()
            if total <= 0:
                return
            self.win.settings["timer"] = [self.h.value(), self.m.value(), self.s.value()]
            self.win.settings.save()
            self.total_ms = total * 1000
            self.remaining_ms = float(self.total_ms)
            self.end = time.monotonic() + total
            self.state = "running"
        elif self.state == "running":
            self.remaining_ms = max(0.0, (self.end - time.monotonic()) * 1000)
            self.state = "paused"
        else:
            self.end = time.monotonic() + self.remaining_ms / 1000
            self.state = "running"
        self._apply_state()

    def reset(self) -> None:
        self.state = "idle"
        self._apply_state()

    def tick(self) -> None:
        if self.state != "running":
            return
        rem = (self.end - time.monotonic()) * 1000
        if rem <= 0:
            total = self.total_ms // 1000
            self.state = "idle"
            self._apply_state()
            self.win.ring(tr("common.timer"), tr("timer.time_s_up", fmt_hms(total)), None)
            return
        self.remaining_ms = rem
        # окно скрыто — кольцо не рисуем и просыпаемся реже, но к концу отсчёта точно
        if self.isVisible():
            self.clock.setInterval(100)
            self._paint()
        else:
            self.clock.setInterval(int(min(1000, max(20, rem))))
