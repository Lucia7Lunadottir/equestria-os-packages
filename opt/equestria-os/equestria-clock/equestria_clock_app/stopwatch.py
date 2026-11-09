"""clock: stopwatch."""
from __future__ import annotations

import time
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget
)
from .localization import live_i18n, tr
from .schedule import fmt_sw


class StopwatchTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.running = False
        self.base_ms = 0.0
        self.t0 = 0.0
        self.last_lap_ms = 0.0
        self.lap_count = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 24, 0, 0)
        v.setSpacing(14)
        self.display = live_i18n.call(QLabel, fmt_sw(0))
        self.display.setObjectName("swdisplay")
        self.display.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.display)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.start_btn = live_i18n.call(QPushButton, tr("common.start"))
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.toggle)
        self.lap_btn = live_i18n.call(QPushButton, tr("stopwatch.lap"))
        self.lap_btn.clicked.connect(self.lap)
        self.reset_btn = live_i18n.call(QPushButton, tr("common.reset"))
        self.reset_btn.clicked.connect(self.reset)
        btns.addWidget(self.start_btn, 1)
        btns.addWidget(self.lap_btn)
        btns.addWidget(self.reset_btn)
        v.addLayout(btns)

        self.laps = QListWidget()
        self.laps.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.laps.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.laps.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        v.addWidget(self.laps, 1)

        self.clock = QTimer(self)
        self.clock.setInterval(30)
        self.clock.timeout.connect(self._tick)
        self._buttons()

    def elapsed(self) -> float:
        return self.base_ms + ((time.monotonic() - self.t0) * 1000 if self.running else 0)

    def _buttons(self) -> None:
        live_i18n.call(self.start_btn.setText, tr("common.stop") if self.running else tr("common.start"))
        self.lap_btn.setEnabled(self.running)
        self.reset_btn.setEnabled(not self.running and self.elapsed() > 0)

    def _tick(self) -> None:
        if self.display.isVisible():
            self.clock.setInterval(30)
            live_i18n.call(self.display.setText, fmt_sw(self.elapsed()))
        else:
            self.clock.setInterval(1000)   # время всё равно считается от t0, не от тиков

    def toggle(self) -> None:
        if self.running:
            self.base_ms = self.elapsed()
            self.running = False
            self.clock.stop()
            self._tick()
        else:
            self.t0 = time.monotonic()
            self.running = True
            self.clock.start()
        self._buttons()

    def lap(self) -> None:
        total = self.elapsed()
        self.lap_count += 1
        text = live_i18n.format_text('{0:>2}   +{1}   {2}', self.lap_count, fmt_sw(total - self.last_lap_ms), fmt_sw(total))
        self.last_lap_ms = total
        self.laps.insertItem(0, live_i18n.call(QListWidgetItem, text))

    def reset(self) -> None:
        self.running = False
        self.clock.stop()
        self.base_ms = 0.0
        self.last_lap_ms = 0.0
        self.lap_count = 0
        self.laps.clear()
        self._tick()
        self._buttons()
