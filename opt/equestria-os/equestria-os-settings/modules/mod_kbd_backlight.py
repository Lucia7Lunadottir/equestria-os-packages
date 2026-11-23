"""Keyboard Backlight module.

Independent things, each in its own card:

  1. Brightness      — a slider over the real LED levels (sysfs *kbd_backlight).
  2. Keep after sleep — switch for the pg-kbd-backlight-keeper user service that
                        brings the light back after suspend.
  3. Colour & effects — colour, animation and speed; the password is asked once
                        (root helper through pkexec) and the permission ends when
                        the page is closed. Optional "no password" access installs
                        a udev rule and enables following the character theme.
  4. ASUS daemon      — asusd also drives the keyboard LEDs on ASUS laptops and
                        can switch them off on resume. The card shows its state
                        and lets the user mask/unmask it (asks for a password
                        through polkit).

Brightness is written through systemd-logind (Session.SetBrightness), so no
root rights are needed for the slider.
"""

import glob
import os
import subprocess
import threading

from PyQt6.QtCore import Qt, QObject, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget,
)

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # соседний kbd_rgb_backends
from base_module import BaseModule  # noqa: E402
import kbd_theme_look  # noqa: E402
from kbd_rgb_backends import EFFECTS_BY_ID, RgbController, RgbSetting, firmware_look  # noqa: E402
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt

_LEDS_DIR = "/sys/class/leds"

_BTN_ACTION = (
    "QPushButton{background:@surface1@;color:@text@;"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid @surface2@;}"
    "QPushButton:hover{background:@surface2@;color:white;}"
    "QPushButton:disabled{color:@subtext@;}"
)


# ── Domain objects (no Qt) ────────────────────────────────────────────────────

class KbdBacklightDevice:
    """One keyboard-backlight LED from /sys/class/leds."""

    def __init__(self, name: str):
        self.name = name
        self._dir = os.path.join(_LEDS_DIR, name)

    @classmethod
    def find(cls) -> "KbdBacklightDevice | None":
        for path in sorted(glob.glob(os.path.join(_LEDS_DIR, "*kbd_backlight*"))):
            if os.access(os.path.join(path, "brightness"), os.R_OK):
                return cls(os.path.basename(path))
        return None

    def _read_int(self, attr: str, default: int = 0) -> int:
        try:
            with open(os.path.join(self._dir, attr)) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return default

    @property
    def max_level(self) -> int:
        return max(1, self._read_int("max_brightness", 1))

    def level(self) -> int:
        return self._read_int("brightness")

    def set_level(self, value: int) -> bool:
        """Write via logind so the unprivileged user can do it."""
        try:
            r = subprocess.run(
                ["busctl", "--system", "call", "org.freedesktop.login1",
                 "/org/freedesktop/login1/session/auto",
                 "org.freedesktop.login1.Session", "SetBrightness",
                 "ssu", "leds", self.name, str(int(value))],
                capture_output=True, timeout=5)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


class SleepKeeperService:
    """pg-kbd-backlight-keeper user service.

    It is enabled for everyone by the package. "Off" is a per-user mask, which
    overrides the global enablement without touching system files.
    """

    UNIT = "pg-kbd-backlight-keeper.service"

    def is_installed(self) -> bool:
        return os.path.exists("/usr/lib/systemd/user/" + self.UNIT)

    def is_enabled(self) -> bool:
        r = _run(["systemctl", "--user", "is-enabled", self.UNIT], 10)
        return r is not None and r.stdout.strip() != "masked" and self.is_installed()

    def set_enabled(self, enabled: bool) -> bool:
        if enabled:
            steps = [["systemctl", "--user", "unmask", self.UNIT],
                     ["systemctl", "--user", "start", self.UNIT]]
        else:
            steps = [["systemctl", "--user", "mask", "--now", self.UNIT]]
        results = [_run(s, 15) for s in steps]
        return all(r is not None and r.returncode == 0 for r in results)


class ThemeSyncService:
    """pg-kbd-theme-sync user service — keyboard colour follows the character theme.

    Not enabled by default: it only runs while the user wants it, so it costs
    no memory otherwise.
    """

    UNIT = "pg-kbd-theme-sync.service"

    def is_installed(self) -> bool:
        return os.path.exists("/usr/lib/systemd/user/" + self.UNIT)

    def is_enabled(self) -> bool:
        r = _run(["systemctl", "--user", "is-enabled", self.UNIT], 10)
        return r is not None and r.stdout.strip() == "enabled"

    def set_enabled(self, enabled: bool) -> bool:
        cmd = ["systemctl", "--user", "enable" if enabled else "disable", "--now", self.UNIT]
        r = _run(cmd, 15)
        return r is not None and r.returncode == 0


class AsusDaemon:
    """asusd — ASUS laptop daemon that also manages the keyboard LEDs."""

    UNIT = "asusd.service"

    def is_installed(self) -> bool:
        return os.path.exists("/usr/lib/systemd/system/" + self.UNIT) or self.is_masked()

    def is_masked(self) -> bool:
        return os.path.realpath("/etc/systemd/system/" + self.UNIT) == "/dev/null"

    def is_running(self) -> bool:
        r = _run(["systemctl", "is-active", self.UNIT], 10)
        return r is not None and r.stdout.strip() == "active"

    def set_masked(self, masked: bool) -> bool:
        if masked:
            cmd = ["pkexec", "systemctl", "mask", "--now", self.UNIT]
        else:
            cmd = ["pkexec", "systemctl", "unmask", self.UNIT]
        r = _run(cmd, 120)
        return r is not None and r.returncode == 0


# ── Background worker ─────────────────────────────────────────────────────────

class _CallWorker(QObject):
    """Runs a blocking callable off the GUI thread and reports success."""
    done = pyqtSignal(bool)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            ok = bool(self._fn())
        except Exception:
            ok = False
        self.done.emit(ok)


# ── Module ────────────────────────────────────────────────────────────────────

class KbdBacklightModule(BaseModule):
    module_id = "mod_kbd_backlight"
    display_name_key = "module.kbd_backlight.name"
    description_key = "module.kbd_backlight.desc"
    category = "system"
    icon = "⌨"
    sort_order = 18
    required_binary = ""
    package_name = ""

    def __init__(self, t_func, base_path: str):
        super().__init__(t_func, base_path)
        self._device = KbdBacklightDevice.find()
        self._keeper = SleepKeeperService()
        self._asusd = AsusDaemon()
        self._theme_sync = ThemeSyncService()
        self._rgb = RgbController()
        self._follow_service_on = False     # the theme service is running: it saves into the keyboard by itself
        self._setting = self._rgb.store.load()
        self._workers: list[_CallWorker] = []

    # ── Build ─────────────────────────────────────────────────────────────────

    def build_widget(self) -> QWidget:
        outer = QWidget()
        outer.setObjectName("ContentPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(outer)
        scroll.setObjectName("ContentPage")

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        self._none_lbl = QLabel(self.t("kbd_backlight.none_found"))
        self._none_lbl.setObjectName("FieldHint")
        self._none_lbl.setWordWrap(True)
        layout.addWidget(self._none_lbl)

        self._level_card = self._build_level_card()
        layout.addWidget(self._level_card)
        self._color_card = self._build_color_card()
        layout.addWidget(self._color_card)
        self._access_card = self._build_access_card()
        layout.addWidget(self._access_card)
        self._keeper_card = self._build_keeper_card()
        layout.addWidget(self._keeper_card)
        self._asusd_card = self._build_asusd_card()
        layout.addWidget(self._asusd_card)
        layout.addStretch()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    @staticmethod
    def _new_card() -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        return card, layout

    def _section(self, layout: QVBoxLayout, title_key: str, hint_key: str):
        title = QLabel(self.t(title_key))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        hint = QLabel(self.t(hint_key))
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return title, hint

    # -- Card 1: brightness --

    def _build_level_card(self) -> QFrame:
        card, layout = self._new_card()
        self._level_title, self._level_hint = self._section(
            layout, "kbd_backlight.level_title", "kbd_backlight.level_hint")

        row = QHBoxLayout()
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.setPageStep(1)
        row.addWidget(self._slider, stretch=1)
        self._level_lbl = QLabel("")
        self._level_lbl.setObjectName("FieldLabel")
        self._level_lbl.setMinimumWidth(110)
        row.addWidget(self._level_lbl)
        layout.addLayout(row)

        self._debounce = QTimer(self._slider)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._apply_level)
        self._slider.valueChanged.connect(self._on_slider_changed)
        return card

    def _level_text(self, value: int) -> str:
        device = self._device
        maximum = device.max_level if device else 1
        if maximum == 3:
            keys = ["off", "low", "medium", "high"]
            return self.t("kbd_backlight.level_" + keys[value])
        if value == 0:
            return self.t("kbd_backlight.level_off")
        return f"{value} / {maximum}"

    def _on_slider_changed(self, value: int):
        self._level_lbl.setText(self._level_text(value))
        self._debounce.start()

    def _apply_level(self):
        if self._device is None:
            return
        value = self._slider.value()
        threading.Thread(target=self._device.set_level, args=(value,), daemon=True).start()

    # -- Card: colour & effects --

    _SPEED_KEYS = ("kbd_backlight.speed_slow", "kbd_backlight.speed_medium", "kbd_backlight.speed_fast")

    def _build_color_card(self) -> QFrame:
        card, layout = self._new_card()
        self._color_title, self._color_hint = self._section(
            layout, "kbd_backlight.color_title", "kbd_backlight.color_hint")

        def row(label_key: str, widget: QWidget):
            r = QHBoxLayout()
            lbl = QLabel(self.t(label_key))
            lbl.setObjectName("FieldLabel")
            lbl.setMinimumWidth(110)
            r.addWidget(lbl)
            r.addWidget(widget)
            r.addStretch()
            layout.addLayout(r)
            return lbl

        self._effect_combo = QComboBox()
        self._effect_lbl = row("kbd_backlight.effect_label", self._effect_combo)
        self._color_btn = QPushButton("")
        self._color_btn.setMinimumWidth(130)
        self._color_btn.clicked.connect(self._pick_color)
        self._color_lbl = row("kbd_backlight.color_label", self._color_btn)
        self._intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self._intensity_slider.setRange(1, 100)
        self._intensity_slider.setMinimumWidth(220)
        self._intensity_value_lbl = QLabel("")
        self._intensity_value_lbl.setObjectName("FieldLabel")
        self._intensity_value_lbl.setMinimumWidth(48)
        intensity_box = QWidget()
        ib = QHBoxLayout(intensity_box)
        ib.setContentsMargins(0, 0, 0, 0)
        ib.addWidget(self._intensity_slider)
        ib.addWidget(self._intensity_value_lbl)
        self._intensity_lbl = row("kbd_backlight.intensity_label", intensity_box)
        self._intensity_slider.valueChanged.connect(self._on_intensity_changed)
        self._speed_combo = QComboBox()
        self._speed_lbl = row("kbd_backlight.speed_label", self._speed_combo)

        save_row = QHBoxLayout()
        self._save_btn = QPushButton(self.t("kbd_backlight.btn_save"))
        kit_qt.style(self._save_btn, _BTN_ACTION)
        self._save_btn.clicked.connect(self._save_rgb)
        save_row.addWidget(self._save_btn)
        self._rgb_status = QLabel("")
        self._rgb_status.setObjectName("FieldHint")
        save_row.addWidget(self._rgb_status)
        save_row.addStretch()
        layout.addLayout(save_row)

        self._experimental_lbl = QLabel(self.t("kbd_backlight.experimental_note"))
        self._experimental_lbl.setObjectName("FieldHint")
        self._experimental_lbl.setWordWrap(True)
        self._experimental_lbl.hide()
        layout.addWidget(self._experimental_lbl)

        self._save_state_lbl = QLabel("")
        self._save_state_lbl.setWordWrap(True)
        layout.addWidget(self._save_state_lbl)
        self._save_hint_lbl = QLabel(self.t("kbd_backlight.save_hint"))
        self._save_hint_lbl.setObjectName("FieldHint")
        self._save_hint_lbl.setWordWrap(True)
        layout.addWidget(self._save_hint_lbl)
        # The button pulses while what the keyboard shows is not yet written into its memory.
        self._pulse = QVariantAnimation(card)
        self._pulse.setDuration(1400)
        self._pulse.setStartValue(0.45)
        self._pulse.setKeyValueAt(0.5, 1.0)
        self._pulse.setEndValue(0.45)
        self._pulse.setLoopCount(-1)
        self._pulse.valueChanged.connect(self._paint_save_pulse)

        self._rgb_debounce = QTimer(card)
        self._rgb_debounce.setSingleShot(True)
        self._rgb_debounce.setInterval(250)
        self._rgb_debounce.timeout.connect(self._preview_rgb)
        self._effect_combo.currentIndexChanged.connect(self._on_effect_changed)
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        return card

    def _fill_rgb_controls(self):
        """(Re)build the effect/speed lists from the current backend and setting."""
        backend = self._rgb.backend
        if backend is None:
            return
        for combo in (self._effect_combo, self._speed_combo):
            combo.blockSignals(True)
            combo.clear()
        self._setting = self._rgb.resolve(self._setting)
        for e in backend.effects():
            self._effect_combo.addItem(self.t(e.label_key), e.id)
        for i, key in enumerate(self._SPEED_KEYS):
            self._speed_combo.addItem(self.t(key), i)
        idx = self._effect_combo.findData(self._setting.effect)
        self._effect_combo.setCurrentIndex(max(0, idx))
        self._speed_combo.setCurrentIndex(self._setting.speed)
        for combo in (self._effect_combo, self._speed_combo):
            combo.blockSignals(False)
        self._intensity_slider.blockSignals(True)
        self._intensity_slider.setValue(self._setting.intensity)
        self._intensity_slider.blockSignals(False)
        self._intensity_value_lbl.setText(f"{self._setting.intensity}%")
        self._update_color_button()
        self._update_rgb_enabled()

    def _update_color_button(self):
        color = self._setting.color
        light = QColor(color).lightness() > 140
        self._color_btn.setText(color.upper())
        self._color_btn.setStyleSheet(
            f"QPushButton{{background:{color};color:{'#000' if light else '#fff'};"
            "border-radius:6px;padding:6px 18px;border:1px solid #888;}")

    def _update_rgb_enabled(self):
        effect = EFFECTS_BY_ID.get(self._setting.effect)
        self._color_btn.setEnabled(bool(effect and effect.uses_color))
        # Scaling the colour only makes sense when the effect has a colour.
        self._intensity_slider.setEnabled(bool(effect and effect.uses_color))
        self._speed_combo.setEnabled(bool(effect and effect.uses_speed))

    def _on_effect_changed(self, _index: int):
        effect_id = self._effect_combo.currentData()
        if effect_id:
            self._setting = self._setting.with_(effect=effect_id)
            self._update_rgb_enabled()
            self._note_change()

    def _on_intensity_changed(self, value: int):
        self._setting = self._setting.with_(intensity=value)
        self._intensity_value_lbl.setText(f"{value}%")
        self._note_change()

    def _on_speed_changed(self, _index: int):
        speed = self._speed_combo.currentData()
        if speed is not None:
            self._setting = self._setting.with_(speed=int(speed))
            self._note_change()

    def _pick_color(self):
        chosen = QColorDialog.getColor(QColor(self._setting.color), self.get_widget(),
                                       self.t("kbd_backlight.color_label"))
        if chosen.isValid():
            self._setting = self._setting.with_(color=chosen.name())
            self._update_color_button()
            self._note_change()

    def _note_change(self):
        """Any change of colour, effect, speed or virtual brightness: show it on the keyboard soon, remember it
        at once (the theme service uses these settings when the theme changes) and update the "not written" cue."""
        self._update_save_state()
        self._rgb_debounce.start()

    def _preview_rgb(self):
        setting = self._setting
        self._rgb_status.setText("")

        def work():
            self._rgb.store.save(setting)          # remembered even if the keyboard is not written to the firmware
            return self._rgb.apply(setting)

        self._run_async(work, self._after_rgb_preview)

    def _after_rgb_preview(self, ok: bool):
        if not ok:
            self._rgb_status.setText(self.t("kbd_backlight.action_failed"))

    def _save_rgb(self):
        setting = self._setting
        self._save_btn.setEnabled(False)

        def work():
            self._rgb.store.save(setting)
            ok = self._rgb.apply(setting, save=True)
            if ok:   # remember what is now in the keyboard's memory, to know when something is not written yet
                self._rgb.store.save_in_keyboard(firmware_look(self._rgb.resolve(setting)))
            return ok

        self._run_async(work, self._after_rgb_saved)

    def _after_rgb_saved(self, ok: bool):
        self._save_btn.setEnabled(True)
        self._rgb_status.setText(self.t("kbd_backlight.saved_ok" if ok else "kbd_backlight.action_failed"))
        self._update_save_state()

    # -- "not written into the keyboard yet" cue --

    def _apply_backend_traits(self):
        """What the page offers depends on the backend: an experimental one is labelled as such, and
        "save into the laptop" only exists where the laptop can remember a look."""
        backend = self._rgb.backend
        firmware = bool(backend and backend.firmware_save)
        self._experimental_lbl.setVisible(bool(backend and backend.experimental))
        for widget in (self._save_btn, self._save_hint_lbl, self._save_state_lbl):
            widget.setVisible(firmware)

    def _is_unsaved_in_keyboard(self) -> bool:
        if self._rgb.backend is None or not self._rgb.backend.firmware_save:
            return False
        return firmware_look(self._rgb.resolve(self._setting)) != self._rgb.store.load_in_keyboard()

    def _update_save_state(self):
        if not hasattr(self, "_save_state_lbl"):
            return
        if self._rgb.backend is None or not self._rgb.backend.firmware_save:
            self._stop_pulse()          # nothing to write into the laptop: no reminder, no pulsing button
            return
        if self._follow_service_on:
            # The theme service writes the look into the keyboard's memory by itself: nothing to remind about.
            self._save_state_lbl.setStyleSheet(f"color:{kit_qt.theme_color('subtext').name()};")
            self._save_state_lbl.setText(self.t("kbd_backlight.save_state_auto"))
            self._stop_pulse()
        elif self._is_unsaved_in_keyboard():
            warn = kit_qt.theme_color("yellow").name()
            self._save_state_lbl.setStyleSheet(f"color:{warn};font-weight:600;")
            self._save_state_lbl.setText(self.t("kbd_backlight.save_state_dirty"))
            if self._pulse.state() != QVariantAnimation.State.Running:
                self._pulse.start()
        else:
            ok = kit_qt.theme_color("green").name()
            self._save_state_lbl.setStyleSheet(f"color:{ok};")
            self._save_state_lbl.setText(self.t("kbd_backlight.save_state_clean"))
            self._stop_pulse()

    def _stop_pulse(self):
        self._pulse.stop()
        kit_qt.style(self._save_btn, _BTN_ACTION)

    def _paint_save_pulse(self, value):
        accent = kit_qt.theme_color("accent")
        r, g, b = accent.red(), accent.green(), accent.blue()
        self._save_btn.setStyleSheet(
            f"QPushButton{{background:rgba({r},{g},{b},{int(255 * float(value))});color:white;font-weight:700;"
            f"border-radius:6px;padding:6px 18px;font-size:13px;border:1px solid rgb({r},{g},{b});}}")

    # -- Card: access without password & theme following --

    def _build_access_card(self) -> QFrame:
        card, layout = self._new_card()
        self._access_title, self._access_hint = self._section(
            layout, "kbd_backlight.access_title", "kbd_backlight.access_hint")
        self._access_cb = QCheckBox(self.t("kbd_backlight.access_toggle"))
        self._access_cb.toggled.connect(self._on_access_toggled)
        layout.addWidget(self._access_cb)

        self._follow_cb = QCheckBox(self.t("kbd_backlight.follow_toggle"))
        self._follow_cb.toggled.connect(self._on_follow_toggled)
        layout.addWidget(self._follow_cb)
        self._follow_hint = QLabel(self.t("kbd_backlight.follow_hint"))
        self._follow_hint.setObjectName("FieldHint")
        self._follow_hint.setWordWrap(True)
        layout.addWidget(self._follow_hint)
        return card

    def _on_access_toggled(self, checked: bool):
        self._access_cb.setEnabled(False)
        self._run_async(lambda: self._rgb.set_direct_access(checked), self._after_access_change)

    def _after_access_change(self, ok: bool):
        if not ok:
            QMessageBox.warning(self.get_widget(), self.t("kbd_backlight.access_title"),
                                self.t("kbd_backlight.action_failed"))
        self._refresh_access()

    def _on_follow_toggled(self, checked: bool):
        self._follow_cb.setEnabled(False)
        setting = self._setting.with_(follow_theme=checked)
        self._setting = setting

        def work():
            self._rgb.store.save(setting)
            return self._theme_sync.set_enabled(checked)

        self._run_async(work, self._after_follow_change)

    def _after_follow_change(self, ok: bool):
        if not ok:
            QMessageBox.warning(self.get_widget(), self.t("kbd_backlight.access_title"),
                                self.t("kbd_backlight.action_failed"))
        self._refresh_access()

    def _refresh_access(self):
        silent = bool(self._rgb.backend and self._rgb.backend.silent)
        self._access_cb.blockSignals(True)
        self._access_cb.setChecked(self._rgb.direct_access_enabled())
        self._access_cb.blockSignals(False)
        self._access_cb.setEnabled(True)
        enabled = self._theme_sync.is_enabled()
        self._follow_service_on = bool(enabled and self._setting.follow_theme)
        self._update_save_state()
        self._follow_cb.blockSignals(True)
        self._follow_cb.setChecked(enabled)
        self._follow_cb.blockSignals(False)
        # Following needs a way to write without a password prompt each time.
        installed = self._theme_sync.is_installed()
        self._follow_cb.setEnabled(silent and installed)
        if not silent:
            hint = "kbd_backlight.follow_needs_access"
        elif not installed:
            hint = "kbd_backlight.follow_not_installed"
        else:
            hint = "kbd_backlight.follow_hint"
        self._follow_hint.setText(self.t(hint))

    # -- Card 2: keep after sleep --

    def _build_keeper_card(self) -> QFrame:
        card, layout = self._new_card()
        self._keeper_title, self._keeper_hint = self._section(
            layout, "kbd_backlight.keeper_title", "kbd_backlight.keeper_hint")
        self._keeper_cb = QCheckBox(self.t("kbd_backlight.keeper_toggle"))
        self._keeper_cb.toggled.connect(self._on_keeper_toggled)
        layout.addWidget(self._keeper_cb)
        return card

    def _on_keeper_toggled(self, checked: bool):
        self._keeper_cb.setEnabled(False)
        self._run_async(lambda: self._keeper.set_enabled(checked),
                        self._after_keeper_change)

    def _after_keeper_change(self, ok: bool):
        if not ok:
            QMessageBox.warning(self.get_widget(), self.t(self.display_name_key),
                                self.t("kbd_backlight.action_failed"))
        self._refresh_keeper()

    # -- Card 3: asusd --

    def _build_asusd_card(self) -> QFrame:
        card, layout = self._new_card()
        self._asusd_title, self._asusd_hint = self._section(
            layout, "kbd_backlight.asusd_title", "kbd_backlight.asusd_hint")
        self._asusd_state_lbl = QLabel("")
        self._asusd_state_lbl.setObjectName("FieldLabel")
        self._asusd_state_lbl.setWordWrap(True)
        layout.addWidget(self._asusd_state_lbl)

        row = QHBoxLayout()
        self._asusd_btn = QPushButton("")
        kit_qt.style(self._asusd_btn, _BTN_ACTION)
        self._asusd_btn.clicked.connect(self._on_asusd_clicked)
        row.addWidget(self._asusd_btn)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _on_asusd_clicked(self):
        mask = not self._asusd.is_masked()
        if mask:
            answer = QMessageBox.question(
                self.get_widget(), self.t("kbd_backlight.asusd_title"),
                self.t("kbd_backlight.asusd_confirm"))
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._asusd_btn.setEnabled(False)
        self._run_async(lambda: self._asusd.set_masked(mask), self._after_asusd_change)

    def _after_asusd_change(self, ok: bool):
        if not ok:
            QMessageBox.warning(self.get_widget(), self.t("kbd_backlight.asusd_title"),
                                self.t("kbd_backlight.action_failed"))
        self._refresh_asusd()

    # ── Async helper ─────────────────────────────────────────────────────────

    def _run_async(self, fn, on_done):
        worker = _CallWorker(fn)
        worker.done.connect(on_done)
        worker.done.connect(lambda _ok, w=worker: self._workers.remove(w))
        self._workers.append(worker)
        threading.Thread(target=worker.run, daemon=True).start()

    # ── Refresh ──────────────────────────────────────────────────────────────

    def on_shown(self) -> None:
        self._device = KbdBacklightDevice.find()
        device = self._device
        has_led = device is not None
        self._none_lbl.setVisible(not has_led)
        self._level_card.setVisible(has_led)
        self._keeper_card.setVisible(has_led and self._keeper.is_installed())
        self._rgb.refresh()
        self._setting = self._saved_setting_as_shown()
        has_rgb = self._rgb.backend is not None
        self._color_card.setVisible(has_rgb)
        self._access_card.setVisible(has_rgb and self._rgb.backend.can_unlock_direct_access)
        if has_rgb:
            self._fill_rgb_controls()
            self._refresh_access()
            self._apply_backend_traits()
            self._update_save_state()
        self._asusd_card.setVisible(self._asusd.is_installed())
        if device is not None:
            self._refresh_level(device)
            self._refresh_keeper()
        if self._asusd.is_installed():
            self._refresh_asusd()

    def _saved_setting_as_shown(self) -> RgbSetting:
        """The page's saved setting, with the theme's colour/effect on top while following the theme
        (so an action on the page keeps the theme's colour instead of resetting it)."""
        saved = self._rgb.store.load()
        try:
            backend = self._rgb.backend
            available = {e.id for e in backend.effects()} if backend else None
            return kbd_theme_look.apply_theme_view(saved, available)
        except Exception:   # the page must open even if theme data is unreadable
            return saved

    def _refresh_level(self, device: KbdBacklightDevice):
        self._slider.blockSignals(True)
        self._slider.setRange(0, device.max_level)
        self._slider.setValue(device.level())
        self._slider.blockSignals(False)
        self._level_lbl.setText(self._level_text(self._slider.value()))

    def _refresh_keeper(self):
        self._keeper_cb.blockSignals(True)
        self._keeper_cb.setChecked(self._keeper.is_enabled())
        self._keeper_cb.blockSignals(False)
        self._keeper_cb.setEnabled(True)

    def _refresh_asusd(self):
        if self._asusd.is_masked():
            state, button = "kbd_backlight.asusd_state_masked", "kbd_backlight.asusd_btn_unmask"
        elif self._asusd.is_running():
            state, button = "kbd_backlight.asusd_state_running", "kbd_backlight.asusd_btn_mask"
        else:
            state, button = "kbd_backlight.asusd_state_stopped", "kbd_backlight.asusd_btn_mask"
        self._asusd_state_lbl.setText(self.t(state))
        self._asusd_btn.setText(self.t(button))
        self._asusd_btn.setEnabled(True)

    def on_hidden(self) -> None:
        # The root helper lives only while this page is open; the pulsing cue only while it is seen.
        self._rgb.close()
        if hasattr(self, "_pulse"):
            self._stop_pulse()

    def apply_language(self) -> None:
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._none_lbl.setText(self.t("kbd_backlight.none_found"))
        self._level_title.setText(self.t("kbd_backlight.level_title"))
        self._level_hint.setText(self.t("kbd_backlight.level_hint"))
        self._color_title.setText(self.t("kbd_backlight.color_title"))
        self._color_hint.setText(self.t("kbd_backlight.color_hint"))
        self._effect_lbl.setText(self.t("kbd_backlight.effect_label"))
        self._color_lbl.setText(self.t("kbd_backlight.color_label"))
        self._intensity_lbl.setText(self.t("kbd_backlight.intensity_label"))
        self._speed_lbl.setText(self.t("kbd_backlight.speed_label"))
        self._save_btn.setText(self.t("kbd_backlight.btn_save"))
        self._save_hint_lbl.setText(self.t("kbd_backlight.save_hint"))
        self._experimental_lbl.setText(self.t("kbd_backlight.experimental_note"))
        self._access_title.setText(self.t("kbd_backlight.access_title"))
        self._access_hint.setText(self.t("kbd_backlight.access_hint"))
        self._access_cb.setText(self.t("kbd_backlight.access_toggle"))
        self._follow_cb.setText(self.t("kbd_backlight.follow_toggle"))
        self._keeper_title.setText(self.t("kbd_backlight.keeper_title"))
        self._keeper_hint.setText(self.t("kbd_backlight.keeper_hint"))
        self._keeper_cb.setText(self.t("kbd_backlight.keeper_toggle"))
        self._asusd_title.setText(self.t("kbd_backlight.asusd_title"))
        self._asusd_hint.setText(self.t("kbd_backlight.asusd_hint"))
        self.on_shown()
