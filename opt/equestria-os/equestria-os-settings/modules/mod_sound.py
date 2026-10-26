"""Звук — устройства вывода и ввода, громкость, порты, профили звуковых карт,
усиление микрофона и диагностика звуковой системы (драйверы, прошивки, службы).

Работа со звуком — в sound_backend.py (без Qt), прежний модуль «Микрофон» —
вкладка из sound_mic.py. Пока модуль открыт, `pactl subscribe` сообщает о
любых изменениях (подключили наушники, сменили громкость в трее) — списки
обновляются сами.
"""

import os
import subprocess
import sys
import threading

from PyQt6.QtCore import QObject, QProcess, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QRadioButton, QScrollArea, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from base_module import BaseModule
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                    "equestria-qt-kit"))
from equestria_kit import qt as kit_qt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # соседние sound_backend / sound_mic
import sound_backend as sb  # noqa: E402
from sound_mic import MicrophonePanel  # noqa: E402

_BTN = ("QPushButton{background:@surface1@;color:@text@;border-radius:6px;padding:5px 14px;font-size:13px;"
        "border:1px solid @surface2@;}QPushButton:hover{background:@surface2@;}"
        "QPushButton:checked{background:@red%45@;border-color:@red%65@;}"
        "QPushButton:disabled{background:@surface0@;color:@surface2@;}")
_LVL = {"fail": "@red@", "warn": "@yellow@", "info": "@accent@", "ok": "@green@"}
_DOT = {"fail": "✕", "warn": "!", "info": "i", "ok": "✓"}


class _Bus(QObject):
    """Результаты фоновых операций возвращаются в поток окна сигналами."""
    snapshot = pyqtSignal(object)
    diagnosed = pyqtSignal(object)
    command_done = pyqtSignal(bool, str)


def _bg(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


def _scroll(inner: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.Shape.NoFrame)
    s.setWidget(inner)
    s.setObjectName("ContentPage")
    inner.setObjectName("ContentPage")
    return s


# ════════════════════════════════════════════════════════════════════════════
#  СТРОКА УСТРОЙСТВА
# ════════════════════════════════════════════════════════════════════════════
class DeviceRow(QFrame):
    """Одно устройство: основное ли, порт, громкость, без звука, проверка."""

    def __init__(self, module: "SoundModule", dev: sb.Device, group: QButtonGroup):
        super().__init__()
        self.m, self.dev = module, dev
        self.setObjectName("InlineCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 12, 18, 12)
        v.setSpacing(8)
        top = QHBoxLayout()
        self.default_btn = QRadioButton(dev.description)
        self.default_btn.setToolTip(module.t("snd.default_tip"))
        group.addButton(self.default_btn)
        self.default_btn.toggled.connect(self._on_default)
        top.addWidget(self.default_btn, 1)
        self.port = QComboBox()
        self.port.activated.connect(self._on_port)
        top.addWidget(self.port)
        v.addLayout(top)
        row = QHBoxLayout()
        self.mute_btn = QPushButton()
        self.mute_btn.setCheckable(True)
        kit_qt.style(self.mute_btn, _BTN)
        self.mute_btn.toggled.connect(self._on_mute)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 150)
        self.slider.setPageStep(5)
        self.value = QLabel()
        self.value.setMinimumWidth(48)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._vol_timer = QTimer(self, singleShot=True, interval=60)  # не дёргать pactl на каждый пиксель
        self._vol_timer.timeout.connect(lambda: _bg(sb.set_volume, self.dev, self.slider.value()))
        self.slider.valueChanged.connect(self._on_volume)
        row.addWidget(self.mute_btn)
        row.addWidget(self.slider, 1)
        row.addWidget(self.value)
        if dev.kind == "sink":
            self.test_btn = QPushButton()
            kit_qt.style(self.test_btn, _BTN)
            self.test_btn.clicked.connect(self._on_test)
            row.addWidget(self.test_btn)
        v.addLayout(row)
        self.retranslate()
        self.update_from(dev)

    def retranslate(self) -> None:
        t = self.m.t
        self.mute_btn.setText(t("snd.muted") if self.mute_btn.isChecked() else t("snd.mute"))
        if hasattr(self, "test_btn"):
            self.test_btn.setText(t("snd.test"))
            self.test_btn.setToolTip(t("snd.test_tip"))

    def update_from(self, dev: sb.Device) -> None:
        """Показать свежие значения, не мешая тому, что пользователь сейчас двигает."""
        self.dev = dev
        for w in (self.default_btn, self.port, self.mute_btn, self.slider):
            w.blockSignals(True)
        self.default_btn.setText(dev.description)
        self.default_btn.setChecked(dev.is_default)
        self.port.clear()
        for p in dev.ports:
            self.port.addItem(p.description + ("" if p.available else self.m.t("snd.port_unplugged")), p.name)
        self.port.setCurrentIndex(max(0, self.port.findData(dev.active_port)))
        self.port.setVisible(len(dev.ports) > 1)
        self.mute_btn.setChecked(dev.mute)
        if not self.slider.isSliderDown() and not self._vol_timer.isActive():
            self.slider.setValue(dev.volume)
        self.value.setText(f"{self.slider.value()}%")
        for w in (self.default_btn, self.port, self.mute_btn, self.slider):
            w.blockSignals(False)
        self.retranslate()

    def _on_default(self, on: bool) -> None:
        if on:
            _bg(sb.set_default, self.dev)

    def _on_port(self, _i: int) -> None:
        _bg(sb.set_port, self.dev, self.port.currentData())

    def _on_mute(self, on: bool) -> None:
        self.retranslate()
        _bg(sb.set_mute, self.dev, on)

    def _on_volume(self, v: int) -> None:
        self.value.setText(f"{v}%")
        kit_qt.style(self.value, "QLabel{color:@yellow@;}" if v > 100 else "")
        self._vol_timer.start()

    def _on_test(self) -> None:
        cmd = sb.test_sound_cmd(self.dev)
        if cmd:
            QProcess.startDetached(cmd[0], cmd[1:])
        else:
            self.m.toast(self.m.t("snd.test_unavailable"))


# ════════════════════════════════════════════════════════════════════════════
#  МОДУЛЬ
# ════════════════════════════════════════════════════════════════════════════
class SoundModule(BaseModule):
    module_id = "mod_sound"
    display_name_key = "module.sound.name"
    description_key = "module.sound.desc"
    category = "system"
    icon = "🔊"
    sort_order = 16
    required_binary = "/usr/bin/pactl"
    package_name = "libpulse"

    def __init__(self, t_func, base_path: str):
        super().__init__(t_func, base_path)
        self.bus = _Bus()
        self.bus.snapshot.connect(self._on_snapshot)
        self.bus.diagnosed.connect(self._on_diagnosed)
        self.bus.command_done.connect(self._on_command_done)
        self.mic = MicrophonePanel(t_func, base_path)
        self.rows = {"sink": {}, "source": {}}
        self.snap = sb.Snapshot()
        self._watch = None
        self._debounce = QTimer(singleShot=True, interval=250)
        self._debounce.timeout.connect(self.refresh)
        self._busy = False

    # --- построение
    def build_widget(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(40, 30, 40, 20)
        wl.setSpacing(10)
        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        self._toast_lbl = QLabel("")
        self._toast_lbl.setObjectName("FieldHint")
        self._toast_lbl.setWordWrap(True)
        wl.addWidget(self._title_lbl)
        wl.addWidget(self._desc_lbl)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.lists = {}
        self.groups = {}
        for kind in ("sink", "source"):
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 12, 8, 12)
            lay.setSpacing(10)
            lay.addStretch()
            self.lists[kind] = lay
            self.groups[kind] = QButtonGroup(box)
            self.tabs.addTab(_scroll(box), "")
        mic = self.mic.get_widget()
        for attr in ("_title_lbl", "_desc_lbl"):  # заголовок уже есть у «Звука»
            if getattr(self.mic, attr, None) is not None:
                getattr(self.mic, attr).hide()
        self.tabs.addTab(mic, "")
        cards = QWidget()
        self.cards_box = QVBoxLayout(cards)
        self.cards_box.setContentsMargins(0, 12, 8, 12)
        self.cards_box.setSpacing(10)
        self.cards_box.addStretch()
        self.tabs.addTab(_scroll(cards), "")
        self.tabs.addTab(self._build_diag(), "")
        self.tabs.currentChanged.connect(self._on_tab)
        wl.addWidget(self.tabs, 1)
        wl.addWidget(self._toast_lbl)
        self._retranslate_tabs()
        return wrapper

    def _build_diag(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(10)
        head = QHBoxLayout()
        self.diag_hint = QLabel()
        self.diag_hint.setObjectName("FieldHint")
        self.diag_hint.setWordWrap(True)
        self.diag_btn = QPushButton()
        kit_qt.style(self.diag_btn, _BTN)
        self.diag_btn.clicked.connect(self.diagnose)
        head.addWidget(self.diag_hint, 1)
        head.addWidget(self.diag_btn)
        v.addLayout(head)
        self.diag_list = QVBoxLayout()
        self.diag_list.setSpacing(8)
        v.addLayout(self.diag_list)
        self.diag_out = QLabel("")
        self.diag_out.setObjectName("FieldHint")
        self.diag_out.setWordWrap(True)
        self.diag_out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.diag_out)
        v.addStretch()
        return _scroll(box)

    def _retranslate_tabs(self) -> None:
        for i, key in enumerate(("snd.tab_output", "snd.tab_input", "snd.tab_mic", "snd.tab_cards", "snd.tab_diag")):
            self.tabs.setTabText(i, self.t(key))
        self.diag_hint.setText(self.t("snd.diag_hint"))
        self.diag_btn.setText(self.t("snd.diag_run"))

    def toast(self, text: str) -> None:
        self._toast_lbl.setText(text)

    # --- жизненный цикл
    def on_shown(self) -> None:
        self.refresh()
        self.mic.on_shown()
        self._start_watch()

    def on_hidden(self) -> None:
        self._stop_watch()

    def apply_language(self) -> None:
        self.mic.current_lang = getattr(self, "current_lang", None)
        self.mic.apply_language()
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._retranslate_tabs()
        for rows in self.rows.values():
            for r in rows.values():
                r.retranslate()
        self._fill_cards()

    def _start_watch(self) -> None:
        if self._watch is not None:
            return
        self._watch = QProcess()
        self._watch.readyReadStandardOutput.connect(self._on_event)
        self._watch.start("pactl", ["subscribe"])

    def _stop_watch(self) -> None:
        if self._watch is not None:
            self._watch.kill()
            self._watch.waitForFinished(1000)
            self._watch = None

    def _on_event(self) -> None:
        data = bytes(self._watch.readAllStandardOutput()).decode(errors="ignore")
        # клиентские потоки (sink-input, source-output) меняются постоянно — они нам не нужны
        if any(k in data for k in ("on sink #", "on source #", "on card #", "on server", "'new' on sink",
                                   "'remove' on sink", "'new' on source", "'remove' on source")):
            self._debounce.start()

    # --- данные
    def refresh(self) -> None:
        if self._busy:
            self._debounce.start()
            return
        self._busy = True
        _bg(lambda: self.bus.snapshot.emit(sb.snapshot()))

    def _on_snapshot(self, snap: sb.Snapshot) -> None:
        self._busy = False
        self.snap = snap
        if not self._widget:
            return
        if not snap.ok:
            self.toast(self.t("snd.no_server"))
        for kind, devs in (("sink", snap.sinks), ("source", snap.sources)):
            self._sync_rows(kind, devs)
        self._fill_cards()

    def _sync_rows(self, kind: str, devs: list) -> None:
        rows, lay = self.rows[kind], self.lists[kind]
        names = [d.name for d in devs]
        for name in [n for n in rows if n not in names]:
            w = rows.pop(name)
            lay.removeWidget(w)
            w.deleteLater()
        for d in devs:
            if d.name in rows:
                rows[d.name].update_from(d)
            else:
                rows[d.name] = DeviceRow(self, d, self.groups[kind])
                lay.insertWidget(lay.count() - 1, rows[d.name])
        empty_key = "snd.no_outputs" if kind == "sink" else "snd.no_inputs"
        if not devs:
            self.toast(self.t(empty_key))

    def _fill_cards(self) -> None:
        if not self._widget:
            return
        while self.cards_box.count() > 1:
            w = self.cards_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        for c in self.snap.cards:
            card = QFrame()
            card.setObjectName("InlineCard")
            v = QVBoxLayout(card)
            v.setContentsMargins(18, 12, 18, 12)
            name = QLabel(c.description)
            name.setObjectName("SectionTitle")
            bus = {"pci": self.t("snd.bus_pci"), "usb": "USB", "bluetooth": "Bluetooth"}.get(c.bus, c.bus)
            hint = QLabel(f"{bus} · {c.name}")
            hint.setObjectName("FieldHint")
            combo = QComboBox()
            for p in c.profiles:
                if p.available or p.name == c.active_profile:
                    combo.addItem(self.t("snd.profile_off") if p.name == "off" else p.description, p.name)
            combo.setCurrentIndex(max(0, combo.findData(c.active_profile)))
            combo.activated.connect(lambda _i, cb=combo, cn=c.name: _bg(sb.set_profile, cn, cb.currentData()))
            v.addWidget(name)
            v.addWidget(hint)
            v.addWidget(combo)
            self.cards_box.insertWidget(self.cards_box.count() - 1, card)

    # --- диагностика
    def _on_tab(self, i: int) -> None:
        if i == 4 and self.diag_list.count() == 0:
            self.diagnose()

    def diagnose(self) -> None:
        self.diag_btn.setEnabled(False)
        self.diag_out.setText(self.t("snd.diag_running"))
        _bg(lambda: self.bus.diagnosed.emit(sb.diagnose(sb.probe(), self.t)))

    def _on_diagnosed(self, checks: list) -> None:
        self.diag_btn.setEnabled(True)
        self.diag_out.setText("")
        while self.diag_list.count():
            w = self.diag_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        for c in checks:
            self.diag_list.addWidget(self._check_card(c))

    def _check_card(self, c: sb.Check) -> QWidget:
        card = QFrame()
        card.setObjectName("InlineCard")
        h = QHBoxLayout(card)
        h.setContentsMargins(16, 10, 16, 10)
        dot = QLabel(_DOT.get(c.level, "·"))
        kit_qt.style(dot, f"QLabel{{color:{_LVL.get(c.level, '@subtext@')};font-size:18px;font-weight:700;}}")
        dot.setFixedWidth(22)
        texts = QVBoxLayout()
        title = QLabel(c.title)
        title.setWordWrap(True)
        kit_qt.style(title, "QLabel{font-weight:600;}")
        detail = QLabel(c.detail)
        detail.setObjectName("FieldHint")
        detail.setWordWrap(True)
        texts.addWidget(title)
        texts.addWidget(detail)
        h.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        h.addLayout(texts, 1)
        if c.fix:
            btn = QPushButton(c.fix[0])
            kit_qt.style(btn, _BTN)
            btn.clicked.connect(lambda _=False, fx=c.fix: self.run_fix(fx))
            h.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def run_fix(self, fix: tuple) -> None:
        label, kind, arg = fix
        cmd = sb.fix_command(kind, arg)
        if not cmd:
            return
        if kind == "pkgs":
            box = QMessageBox(self._widget)
            box.setWindowTitle(self.t("snd.confirm_title"))
            box.setText(self.t("snd.confirm_pkgs").format(" ".join(arg)))
            yes = box.addButton(self.t("snd.yes"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(self.t("snd.cancel"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is not yes:
                return
        self.diag_btn.setEnabled(False)
        self.diag_out.setText(self.t("snd.fix_running").format(label))

        def work():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                self.bus.command_done.emit(r.returncode == 0, (r.stdout + r.stderr)[-1500:])
            except (OSError, subprocess.SubprocessError) as e:
                self.bus.command_done.emit(False, str(e))
        _bg(work)

    def _on_command_done(self, ok: bool, output: str) -> None:
        tail = "\n".join(output.strip().splitlines()[-6:])
        self.diag_out.setText((self.t("snd.fix_ok") if ok else self.t("snd.fix_err")) + ("\n" + tail if tail else ""))
        self.refresh()
        self.diagnose()
