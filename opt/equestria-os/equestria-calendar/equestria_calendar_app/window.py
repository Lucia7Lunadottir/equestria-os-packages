"""calendar: window."""
from __future__ import annotations

import os
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget
)
from datetime import date, datetime, time as dtime, timedelta
from equestria_kit import qt as kit_qt
from equestria_kit.autostart import Autostart
from equestria_kit.widgets import small_btn
from pathlib import Path
from .calendar_views import CalView, MoonCard, YearView
from .dates import MONTHS, MONTHS_G, WD_LONG, WD_SHORT, add_months, short_date
from .localization import catalog, live_i18n, tr
from .reminder_dialog import ReminderDialog
from .reminder_popup import ReminderPopup
from .reminders import ReminderBook
from .sounds import SOUND_SPECS, Sounds
from .storage import Store
from .style import apply_theme, make_icon


class MainWindow(QMainWindow):
    def __init__(self, st: Store):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.st, self.cfg = st, st.settings
        self.book = ReminderBook(st, self.cfg)   # логика напоминаний — отдельно от окна
        self.theme = self.cfg["theme"]
        self.sel = date.today()
        self.mode = self.cfg["view"] if self.cfg["view"] in ("month", "week", "year") else "month"
        self.sounds = Sounds()
        self.popups: list = []
        self.quitting = False
        self._icon_day = None
        live_i18n.call(self.setWindowTitle, "Equestria Calendar")
        self.setMinimumSize(1120, 700)
        self.resize(1320, 800)

        self.save_timer = QTimer(self, singleShot=True, interval=400)
        self.save_timer.timeout.connect(self.st.save)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = live_i18n.call(QLabel, "Equestria Calendar")
        title.setObjectName("h2")
        top.addWidget(title)
        top.addStretch()
        self.view_btns = {}
        for mode, label in (("month", tr("window.month")), ("week", tr("window.week")), ("year", tr("window.year"))):
            b = small_btn(label, True, "Ctrl+1 / Ctrl+2 / Ctrl+3")
            b.clicked.connect(lambda _=False, m=mode: self.set_view(m))
            self.view_btns[mode] = b
            top.addWidget(b)
        theme_btn = small_btn(tr("window.theme"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        set_btn = small_btn("⚙")
        set_btn.clicked.connect(lambda: self._settings_menu(set_btn))
        top.addSpacing(10)
        self.language_combo = catalog.selector(self, self._language_changed)
        top.addWidget(self.language_combo)
        top.addWidget(theme_btn)
        top.addWidget(set_btn)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(8)
        nav = QHBoxLayout()
        prev = small_btn("◀")
        prev.clicked.connect(lambda: self.shift(-1))
        nxt = small_btn("▶")
        nxt.clicked.connect(lambda: self.shift(1))
        today = small_btn(tr("common.today"), tip="T")
        today.clicked.connect(lambda: self.set_date(date.today()))
        self.head = live_i18n.call(QLabel, "")
        self.head.setObjectName("big")
        add = live_i18n.call(QPushButton, tr("window.reminder"))
        add.setObjectName("primary")
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add.clicked.connect(lambda: self.edit_reminder(None, self.sel))
        for w in (prev, nxt, today):
            nav.addWidget(w)
        nav.addSpacing(8)
        nav.addWidget(self.head)
        nav.addStretch()
        nav.addWidget(add)
        left.addLayout(nav)
        self.stack = QStackedWidget()
        self.cal = CalView(self)
        self.year = YearView(self)
        self.stack.addWidget(self.cal)
        self.stack.addWidget(self.year)
        for v in (self.cal, self.year):
            v.selected.connect(self.set_date)
            v.shifted.connect(self.shift)
        self.cal.activated.connect(lambda d: self.edit_reminder(None, d))
        self.year.activated.connect(lambda d: (self.set_view("month"), self.set_date(d)))
        left.addWidget(self.stack, 1)
        lw = QWidget()
        lw.setLayout(left)
        body.addWidget(lw, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.day_title = live_i18n.call(QLabel, "")
        self.day_title.setObjectName("h3")
        self.day_sub = live_i18n.call(QLabel, "")
        self.day_sub.setObjectName("hint")
        right.addWidget(self.day_title)
        right.addWidget(self.day_sub)
        self.moon = MoonCard()
        right.addWidget(self.moon)
        h = live_i18n.call(QLabel, tr("window.reminders_day"))
        h.setObjectName("h2")
        right.addWidget(h)
        self.day_list = QListWidget()
        self.day_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.day_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.day_list.itemChanged.connect(self._day_check)
        self.day_list.itemDoubleClicked.connect(self._day_edit)
        self.day_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.day_list.customContextMenuRequested.connect(self._day_menu)
        right.addWidget(self.day_list, 3)
        h2 = live_i18n.call(QLabel, tr("window.upcoming"))
        h2.setObjectName("h2")
        right.addWidget(h2)
        self.up_list = QListWidget()
        self.up_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.up_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.up_list.itemClicked.connect(self._up_click)
        right.addWidget(self.up_list, 2)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(350)
        body.addWidget(rw)

        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self).activated.connect(fn)
        sc("Ctrl+N", lambda: self.edit_reminder(None, self.sel))
        sc("T", lambda: self.set_date(date.today()))
        sc("Ctrl+1", lambda: self.set_view("month"))
        sc("Ctrl+2", lambda: self.set_view("week"))
        sc("Ctrl+3", lambda: self.set_view("year"))

        # трей
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            menu = QMenu(self)
            live_i18n.call(menu.addAction, tr("window.open_calendar")).triggered.connect(self.show_window)
            live_i18n.call(menu.addAction, tr("window.quit")).triggered.connect(self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda r: self.show_window()
                                        if r == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.show()
        self._update_icon()

        # Напоминания — с точностью до минуты, поэтому проверяем ровно на границе
        # минуты (или к ближайшему «Отложить»), а не каждые 15 секунд.
        self.tick_timer = QTimer(self, singleShot=True)
        self.tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.tick_timer.timeout.connect(self._tick)
        self._schedule_tick()
        self.set_view(self.mode, save=False)
        QTimer.singleShot(1500, self.check_due)

    # --- данные
    # --- данные (логика — в ReminderBook; здесь обёртки для видов и всплывающих окон)
    def events_on(self, d: date) -> list:
        return self.book.events_on(d)

    def is_done(self, rem: dict, d: date) -> bool:
        return self.book.is_done(rem, d)

    def find(self, rid: str):
        return self.book.find(rid)

    def _allday_t(self) -> dtime:
        return self.book.allday_time()

    def changed(self) -> None:
        self.save_timer.start()
        self.refresh_all()

    def set_done(self, rem: dict, d: date, on: bool) -> None:
        self.book.set_done(rem, d, on)
        self.changed()

    # --- навигация
    def set_date(self, d: date) -> None:
        self.sel = d
        self.cal.sel = d
        self.year.sel = d
        self.refresh_all()

    def shift(self, n: int) -> None:
        if self.mode == "week":
            self.set_date(self.sel + timedelta(days=7 * n))
        elif self.mode == "year":
            self.set_date(add_months(self.sel, 12 * n))
        else:
            self.set_date(add_months(self.sel, n))

    def set_view(self, mode: str, save: bool = True) -> None:
        self.mode = mode
        self.cal.mode = mode
        for m, b in self.view_btns.items():
            b.setChecked(m == mode)
        self.stack.setCurrentWidget(self.year if mode == "year" else self.cal)
        if save:
            self.cfg["view"] = mode
            self.save_timer.start()
        self.refresh_all()

    # --- отрисовка панелей
    def _language_changed(self) -> None:
        self.cal.update()
        self.year.update()
        self.moon.update()

    def refresh_all(self) -> None:
        d = self.sel
        if self.mode == "year":
            live_i18n.call(self.head.setText, str(d.year))
        elif self.mode == "week":
            a = self.cal.start_date()
            b = a + timedelta(days=6)
            live_i18n.call(self.head.setText, live_i18n.format_text('{0} – {1} {2} {3}', a.day, b.day, MONTHS_G[b.month - 1], b.year) if a.month == b.month
                              else live_i18n.format_text('{0} {1} – {2} {3} {4}', a.day, MONTHS_G[a.month - 1][:3], b.day, MONTHS_G[b.month - 1][:3], b.year))
        else:
            live_i18n.call(self.head.setText, live_i18n.format_text('{0} {1}', MONTHS[d.month - 1], d.year))
        self.cal.update()
        self.year.update()
        live_i18n.call(self.day_title.setText, live_i18n.format_text('{0} {1} {2}', d.day, MONTHS_G[d.month - 1], d.year))
        live_i18n.call(self.day_sub.setText, WD_LONG[d.weekday()] + (tr("window.today") if d == date.today() else ""))
        self.moon.set_date(d)
        self._fill_day()
        self._fill_upcoming()

    def _fill_day(self) -> None:
        lst = self.day_list
        lst.blockSignals(True)
        lst.clear()
        evs = self.events_on(self.sel)
        for r in evs:
            done = self.is_done(r, self.sel)
            text = (tr("common.all_day") if r.get("all_day") else r["time"]) + " · " + r["title"]
            if r.get("repeat", "none") != "none":
                text += "  🔁"
            if r.get("notes"):
                text += "\n" + r["notes"].split("\n")[0][:60]
            it = live_i18n.call(QListWidgetItem, text)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, r["id"])
            pm = QPixmap(12, 12)
            pm.fill(QColor(r["color"]))
            it.setIcon(QIcon(pm))
            if done:
                f = it.font()
                f.setStrikeOut(True)
                it.setFont(f)
            live_i18n.call(lst.addItem, it)
        if not evs:
            it = live_i18n.call(QListWidgetItem, tr("window.no_reminders_double_click_day"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            live_i18n.call(lst.addItem, it)
        lst.blockSignals(False)

    def _fill_upcoming(self) -> None:
        self.up_list.clear()
        today = date.today()
        n = 0
        for i in range(120):
            d = today + timedelta(days=i)
            for r in self.events_on(d):
                if self.is_done(r, d):
                    continue
                when = tr("common.all_day") if r.get("all_day") else r["time"]
                label = tr("common.today") if i == 0 else (tr("common.tomorrow") if i == 1 else live_i18n.format_text('{0}, {1}', WD_SHORT[d.weekday()], short_date(d)))
                it = live_i18n.call(QListWidgetItem, live_i18n.format_text('{0} · {1} · {2}', label, when, r['title']))
                it.setData(Qt.ItemDataRole.UserRole, d.isoformat())
                live_i18n.call(self.up_list.addItem, it)
                n += 1
            if n >= 14:
                break
        if not n:
            it = live_i18n.call(QListWidgetItem, tr("window.no_upcoming_reminders"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            live_i18n.call(self.up_list.addItem, it)

    def _up_click(self, it) -> None:
        iso = it.data(Qt.ItemDataRole.UserRole)
        if iso:
            self.set_date(date.fromisoformat(iso))

    # --- действия с напоминаниями
    def _day_check(self, it) -> None:
        rem = self.find(it.data(Qt.ItemDataRole.UserRole))
        if rem:
            self.set_done(rem, self.sel, it.checkState() == Qt.CheckState.Checked)

    def _day_edit(self, it) -> None:
        rem = self.find(it.data(Qt.ItemDataRole.UserRole))
        if rem:
            self.edit_reminder(rem, self.sel)

    def _day_menu(self, pos) -> None:
        it = self.day_list.itemAt(pos)
        rem = self.find(it.data(Qt.ItemDataRole.UserRole)) if it else None
        menu = QMenu(self)
        if rem:
            live_i18n.call(menu.addAction, tr("window.edit")).triggered.connect(lambda: self.edit_reminder(rem, self.sel))
            if rem.get("repeat", "none") != "none":
                live_i18n.call(menu.addAction, tr("window.skip_only_day")).triggered.connect(lambda: self._skip(rem))
            live_i18n.call(menu.addAction, tr("window.delete_ellipsis")).triggered.connect(lambda: self._delete(rem))
            menu.addSeparator()
        live_i18n.call(menu.addAction, tr("window.new_reminder")).triggered.connect(lambda: self.edit_reminder(None, self.sel))
        menu.exec(self.day_list.viewport().mapToGlobal(pos))

    def _skip(self, rem: dict) -> None:
        self.book.skip(rem, self.sel)
        self.changed()

    def _delete(self, rem: dict) -> None:
        extra = tr("window.all_repeats_will_deleted_too") if rem.get("repeat", "none") != "none" else ""
        if QMessageBox.question(self, tr("common.delete"), tr("window.delete", rem['title'], extra)) != QMessageBox.StandardButton.Yes:
            return
        self.book.delete(rem)
        self.changed()

    def edit_reminder(self, rem, day: date) -> None:
        dlg = ReminderDialog(self, rem, day)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.deleted and rem:
            self._delete_now(rem)
            return
        new = dlg.result_rem()
        self.book.upsert(rem, new)
        self.set_date(date.fromisoformat(new["date"]))
        self.changed()

    def _delete_now(self, rem: dict) -> None:
        self.book.delete(rem, with_snoozes=False)
        self.changed()

    # --- срабатывание
    def play_sound(self) -> None:
        self.sounds.play(self.cfg["sound"], self.cfg["volume"], self.cfg["custom_sound"])

    def snooze(self, rem: dict, d: date, mins: int) -> None:
        self.book.snooze(rem, d, mins)
        self.save_timer.start()

    def fire(self, rem: dict, d: date, occ: datetime) -> None:
        pop = ReminderPopup(self, rem, d, occ)
        self.popups.append(pop)
        pop.finished.connect(lambda _=0, p=pop: self.popups.remove(p) if p in self.popups else None)
        pop.show()
        pop.raise_()
        pop.activateWindow()
        if rem.get("sound", True):
            self.play_sound()

    def check_due(self) -> None:
        to_fire, dirty = self.book.due(datetime.now())
        for rem, d, occ in to_fire:
            self.fire(rem, d, occ)
        if dirty:
            self.save_timer.start()

    def _tick(self) -> None:
        self.check_due()
        if self._icon_day != date.today():
            self._update_icon()
            self.refresh_all()
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        now = datetime.now()
        nxt = self.book.next_check(now)
        self.tick_timer.start(max(50, int((nxt - now).total_seconds() * 1000) + 200))

    # --- трей / иконка / выход
    def _update_icon(self) -> None:
        self._icon_day = date.today()
        ic = make_icon(self._icon_day)
        QApplication.setWindowIcon(ic)
        self.setWindowIcon(ic)
        if self.tray:
            self.tray.setIcon(ic)
            live_i18n.call(self.tray.setToolTip, "Equestria Calendar")

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self.quitting = True
        self.st.save()
        QApplication.quit()

    def closeEvent(self, e) -> None:
        if self.tray and self.cfg["tray"] and not self.quitting:
            e.ignore()
            self.hide()
            return
        self.st.save()
        self.quitting = True
        super().closeEvent(e)
        QApplication.quit()

    # --- меню
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
        self._update_icon()
        self.refresh_all()
        self.st.save()

    def _toggle(self, key: str, on: bool) -> None:
        self.cfg[key] = on
        self.st.save()
        self.refresh_all()

    def _settings_menu(self, btn) -> None:
        menu = QMenu(self)
        snd = live_i18n.call(menu.addMenu, tr("window.reminder_sound"))
        for name in SOUND_SPECS:
            a = live_i18n.call(snd.addAction, tr(name))
            a.setCheckable(True)
            a.setChecked(name == self.cfg["sound"] and not self.cfg["custom_sound"])
            a.triggered.connect(lambda _=False, n=name: self._pick_sound(n))
        a = live_i18n.call(snd.addAction, tr("window.custom_file_wav") + (f" — {os.path.basename(self.cfg['custom_sound'])}" if self.cfg["custom_sound"] else ""))
        a.triggered.connect(self._custom_sound)
        snd.addSeparator()
        live_i18n.call(snd.addAction, tr("window.volume_ellipsis")).triggered.connect(self._volume)
        live_i18n.call(snd.addAction, tr("window.test_sound")).triggered.connect(self.play_sound)
        rs = live_i18n.call(snd.addAction, tr("window.repeat_while_reminder_window_open"))
        rs.setCheckable(True)
        rs.setChecked(self.cfg["repeat_sound"])
        rs.toggled.connect(lambda on: self._toggle("repeat_sound", on))
        live_i18n.call(menu.addAction, tr("window.time_all_day_reminders", self.cfg['allday_time'])).triggered.connect(self._allday_time)
        for key, label in (("sunday_first", tr("window.week_starts_sunday")), ("show_moon", tr("window.moon_phases_cells"))):
            a = live_i18n.call(menu.addAction, label)
            a.setCheckable(True)
            a.setChecked(self.cfg[key])
            a.toggled.connect(lambda on, k=key: self._toggle(k, on))
        auto = Autostart("equestria-calendar", "Equestria Calendar",
                         tr("window.calendar_with_moon_phases_reminders"))
        a = live_i18n.call(menu.addAction, tr("window.launch_at_system_startup"))
        a.setCheckable(True)
        a.setChecked(auto.is_enabled())
        a.toggled.connect(lambda on: self._autostart(auto, on))
        if self.tray:
            a = live_i18n.call(menu.addAction, tr("window.closing_window_minimizes_tray"))
            a.setCheckable(True)
            a.setChecked(self.cfg["tray"])
            a.toggled.connect(lambda on: self._toggle("tray", on))
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _autostart(self, auto: Autostart, on: bool) -> None:
        if on and self.tray and not self.cfg["tray"]:
            self._toggle("tray", True)   # при автозапуске календарь живёт в трее
        auto.set_enabled(on)

    def _pick_sound(self, name: str) -> None:
        self.cfg["sound"], self.cfg["custom_sound"] = name, ""
        self.st.save()
        self.play_sound()

    def _custom_sound(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("window.sound_wav"), str(Path.home()), "WAV (*.wav)")
        if p:
            self.cfg["custom_sound"] = p
            self.st.save()
            self.play_sound()

    def _volume(self) -> None:
        v, ok = QInputDialog.getInt(self, tr("window.volume"), tr("window.volume_percent_label"), self.cfg["volume"], 0, 100)
        if ok:
            self.cfg["volume"] = v
            self.st.save()
            self.play_sound()

    def _allday_time(self) -> None:
        t, ok = QInputDialog.getText(self, tr("common.all_day"), tr("window.reminder_time_hh_mm"), text=self.cfg["allday_time"])
        if ok:
            try:
                self.cfg["allday_time"] = dtime.fromisoformat(t.strip()).strftime("%H:%M")
                self.st.save()
            except ValueError:
                QMessageBox.warning(self, tr("window.time"), tr("window.enter_time_as_hh_mm"))
