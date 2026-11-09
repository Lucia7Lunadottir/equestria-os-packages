"""clock: settings page."""
from __future__ import annotations

import json
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget
)
from equestria_kit import qt as kit_qt, themes as kit_themes
from equestria_kit.autostart import Autostart
from .localization import catalog, live_i18n, tr
from .paths import CONFIG_DIR
from .style import DEFAULT_THEME, THEMES, load_all_themes
from .widgets import SoundPicker, Switch, card_row


class SettingsTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        st = win.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 14, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(10)

        # тема
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        self.theme_combo = QComboBox()
        self.theme_combo.activated.connect(self._theme_chosen)
        bl.addWidget(self.theme_combo)
        trow = QHBoxLayout()
        trow.setSpacing(8)
        edit = live_i18n.call(QPushButton, tr("settings_page.edit_my_themes"))
        edit.clicked.connect(self._edit_themes)
        reload_ = live_i18n.call(QPushButton, tr("settings_page.reload_themes"))
        reload_.clicked.connect(self._reload_themes)
        trow.addWidget(edit)
        trow.addWidget(reload_)
        bl.addLayout(trow)
        v.addWidget(card_row(tr("settings_page.color_theme"), box))
        self._fill_themes()
        kit_themes.on_list_change(self._fill_themes)   # новая тема из редактора тем — сразу в списке

        # мелодия
        self.sound = SoundPicker(win, allow_default=False)
        self.sound.set_value(st["sound"])
        self.sound.changed.connect(self._sound_changed)
        v.addWidget(card_row(tr("settings_page.default_melody"), self.sound))

        # громкость
        vbox = QWidget()
        vl = QHBoxLayout(vbox)
        vl.setContentsMargins(0, 0, 0, 0)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(int(st["volume"]))
        self.vol_label = live_i18n.call(QLabel, live_i18n.format_text('{0}%', st['volume']))
        self.vol_label.setMinimumWidth(44)
        self.vol.valueChanged.connect(self._volume)
        self.vol.sliderReleased.connect(win.settings.save)
        vl.addWidget(self.vol, 1)
        vl.addWidget(self.vol_label)
        v.addWidget(card_row(tr("settings_page.volume"), vbox))

        # откладывание
        self.snooze = QComboBox()
        for n in (1, 2, 5, 10, 15, 20, 30):
            live_i18n.call(self.snooze.addItem, tr("common.min", n), n)
        idx = self.snooze.findData(int(st["snooze"]))
        self.snooze.setCurrentIndex(idx if idx >= 0 else 2)
        self.snooze.activated.connect(self._snooze)
        v.addWidget(card_row(tr("settings_page.snooze_button_postpones"), self.snooze))

        # трей
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_sw = Switch(bool(st["tray"]))
            self.tray_sw.toggled.connect(self._tray)
            c = card_row(tr("settings_page.hide_tray_instead_closing"),
                         hint=tr("settings_page.while_program_tray_alarms_timer"))
            c.layout().itemAt(0).layout().addWidget(self.tray_sw)
            v.addWidget(c)
        # запуск вместе с системой (сразу в трей)
        self.autostart = Autostart("equestria-clock", "Equestria Clock",
                                   tr("settings_page.alarm_timer_stopwatch"))
        self.auto_sw = Switch(self.autostart.is_enabled())
        self.auto_sw.toggled.connect(self._autostart)
        c = card_row(tr("settings_page.launch_at_system_startup"),
                     hint=tr("settings_page.clock_starts_minimized_tray_so"))
        c.layout().itemAt(0).layout().addWidget(self.auto_sw)
        v.addWidget(c)
        v.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _autostart(self, on: bool) -> None:
        if on and not self.win.settings["tray"]:
            # без трея окно при автозапуске пришлось бы показывать — включаем трей
            self.win.settings["tray"] = True
            self.win.settings.save()
            if hasattr(self, "tray_sw"):
                self.tray_sw.setChecked(True)
        self.autostart.set_enabled(on)

    # --- темы
    def _fill_themes(self) -> None:
        self.theme_combo.clear()
        # «Как в системе» + все темы; выбор хранит kit отдельно для часов
        for label, value in kit_qt.theme_choices(catalog):
            live_i18n.call(self.theme_combo.addItem, label, value)
        i = self.theme_combo.findData(kit_themes.choice())
        self.theme_combo.setCurrentIndex(max(0, i))

    def _theme_chosen(self, i: int) -> None:
        self.win.set_theme(kit_qt.pick_theme(self.theme_combo.itemData(i)))

    def _edit_themes(self) -> None:
        path = CONFIG_DIR / "themes.json"
        if not path.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            example = {str(tr("settings_page.my_theme")): dict(THEMES[DEFAULT_THEME])}
            path.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _reload_themes(self) -> None:
        load_all_themes()
        self._fill_themes()
        self.win.set_theme(kit_themes.current_name())

    # --- прочее
    def _sound_changed(self) -> None:
        self.win.settings["sound"] = self.sound.value() or "builtin:chime"
        self.win.settings.save()

    def _volume(self, val: int) -> None:
        live_i18n.call(self.vol_label.setText, live_i18n.format_text('{0}%', val))
        self.win.settings["volume"] = val
        self.win.player.set_volume(val)
        if not self.vol.isSliderDown():
            self.win.settings.save()

    def _snooze(self, i: int) -> None:
        self.win.settings["snooze"] = self.snooze.itemData(i)
        self.win.settings.save()

    def _tray(self, on: bool) -> None:
        self.win.settings["tray"] = on
        self.win.settings.save()
