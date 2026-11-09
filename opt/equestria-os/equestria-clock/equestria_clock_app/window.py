"""clock: window."""
from __future__ import annotations

import datetime as dt
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget
)
from .alarms import AlarmTab
from .dialogs import RingDialog
from .localization import catalog, live_i18n, tr
from .schedule import MONTHS, WEEKDAYS
from .settings import Settings
from .settings_page import SettingsTab
from .sound import SoundPlayer
from .stopwatch import StopwatchTab
from .style import apply_theme, make_icon
from .timer import TimerTab


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.settings = settings
        self.player = SoundPlayer(self)
        self.player.set_volume(int(settings["volume"]))
        self._rings: list[RingDialog] = []
        self.snoozes: list[dict] = []
        self._last_minute = ""
        self._quitting = False
        self._tray_hint_shown = False

        live_i18n.call(self.setWindowTitle, "Equestria Clock")
        self.setWindowIcon(make_icon())
        self.resize(580, 740)
        self.setMinimumSize(500, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(2)
        self.clock_label = live_i18n.call(QLabel, )
        self.clock_label.setObjectName("bigclock")
        self.date_label = live_i18n.call(QLabel, )
        self.date_label.setObjectName("subtle")
        header = QHBoxLayout()
        header.addWidget(self.clock_label, 1)
        self.language_combo = catalog.selector(self)
        header.addWidget(self.language_combo, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)
        root.addWidget(self.date_label)

        self.alarm_tab = AlarmTab(self)
        self.timer_tab = TimerTab(self)
        self.sw_tab = StopwatchTab(self)
        self.settings_tab = SettingsTab(self)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        live_i18n.call(self.tabs.addTab, self.alarm_tab, tr("common.alarm"))
        live_i18n.call(self.tabs.addTab, self.timer_tab, tr("common.timer"))
        live_i18n.call(self.tabs.addTab, self.sw_tab, tr("window.stopwatch"))
        live_i18n.call(self.tabs.addTab, self.settings_tab, tr("window.settings"))
        root.addWidget(self.tabs, 1)

        # значок в трее
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(make_icon(), self)
            live_i18n.call(self.tray.setToolTip, "Equestria Clock")
            menu = QMenu()
            show = live_i18n.call(QAction, tr("window.show"), self)
            show.triggered.connect(self.show_window)
            quit_ = live_i18n.call(QAction, tr("window.quit"), self)
            quit_.triggered.connect(self.quit_app)
            live_i18n.call(menu.addAction, show)
            live_i18n.call(menu.addAction, quit_)
            self._tray_menu = menu
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_clicked)
            self.tray.show()

        # Главный «тик» — одиночный таймер, который сам назначает следующий запуск:
        # окно открыто → ровно на следующей секунде (для цифр на экране);
        # окно в трее → на следующей минуте или к ближайшему «Отложить» (будильникам
        # секунды не нужны), так программа в фоне почти не будит процессор.
        self.clock = QTimer(self)
        self.clock.setSingleShot(True)
        self.clock.setTimerType(Qt.TimerType.PreciseTimer)
        self.clock.timeout.connect(self.tick)
        self.tick()

    # --- тема
    def set_theme(self, name: str) -> None:
        self.settings["theme"] = apply_theme(name)
        self.settings.save()
        for w in self.findChildren(QWidget):
            w.update()
        self.setWindowIcon(make_icon())

    # --- трей
    def _tray_clicked(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.settings.save()
        self.player.stop()
        QApplication.quit()

    def closeEvent(self, e):
        if self.tray and self.settings["tray"] and not self._quitting:
            e.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.showMessage(tr("window.equestria_clock_keeps_running"),
                                      tr("window.alarms_will_ring_while_program"))
        else:
            e.accept()
            self.quit_app()

    # --- звонок
    def ring(self, title: str, text: str, sound: str | None, snooze_cb=None) -> None:
        self.player.play(sound or self.settings["sound"], int(self.settings["volume"]))
        dlg = RingDialog(title, text, int(self.settings["snooze"]) if snooze_cb else 0)
        if snooze_cb:
            dlg.snoozed.connect(snooze_cb)
        dlg.finished.connect(lambda _=0, d=dlg: self._ring_closed(d))
        self._rings.append(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if self.tray:
            self.tray.showMessage(title, text)

    def _ring_closed(self, dlg: RingDialog) -> None:
        if dlg in self._rings:
            self._rings.remove(dlg)
        if not self._rings:
            self.player.stop()

    def _fire_alarm(self, a: dict) -> None:
        title = a["label"] or tr("common.alarm")

        def snooze():
            mins = int(self.settings["snooze"])
            self.snoozes.append({
                "at": dt.datetime.now() + dt.timedelta(minutes=mins),
                "alarm": a,
            })

        self.ring(title, a["time"], a["sound"], snooze_cb=snooze)

    # --- главный «тик»
    def _on_screen(self) -> bool:
        return self.isVisible() and not self.isMinimized()

    def _schedule_tick(self, now: dt.datetime) -> None:
        if self._on_screen():
            ms = 1000 - now.microsecond // 1000 + 5
        else:
            nxt = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
            if self.snoozes:
                nxt = min(nxt, min(s["at"] for s in self.snoozes))
            ms = max(50, int((nxt - now).total_seconds() * 1000) + 5)
        self.clock.start(ms)

    def showEvent(self, e):
        super().showEvent(e)
        self.tick()   # окно снова видно — сразу показываем точное время и тикаем посекундно

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange and not self.isMinimized():
            self.tick()

    def tick(self) -> None:
        now = dt.datetime.now()
        if self._on_screen():
            live_i18n.call(self.clock_label.setText, now.strftime("%H:%M:%S"))
            weekday = WEEKDAYS[now.weekday()]
            # capitalize() у Text работает по тексту на момент создания, поэтому делаем «живую» строку
            weekday_cap = live_i18n.Text(weekday.catalog, lambda: str(weekday).capitalize())
            live_i18n.call(self.date_label.setText, 
                live_i18n.format_text('{0}, {1} {2}', weekday_cap, now.day, MONTHS[now.month - 1]))

        for s in list(self.snoozes):
            if now >= s["at"]:
                self.snoozes.remove(s)
                self._fire_alarm(s["alarm"])

        key = now.strftime("%Y-%m-%d %H:%M")
        if key != self._last_minute:
            self._last_minute = key
            hhmm = now.strftime("%H:%M")
            changed = False
            for a in self.settings["alarms"]:
                if a["enabled"] and a["time"] == hhmm and (not a["days"] or now.weekday() in a["days"]):
                    self._fire_alarm(a)
                    if not a["days"]:  # одноразовый — выключаем
                        a["enabled"] = False
                        changed = True
            if changed:
                self.settings.save()
                self.alarm_tab.refresh()
            else:
                self.alarm_tab.update_next()
        self._schedule_tick(now)
