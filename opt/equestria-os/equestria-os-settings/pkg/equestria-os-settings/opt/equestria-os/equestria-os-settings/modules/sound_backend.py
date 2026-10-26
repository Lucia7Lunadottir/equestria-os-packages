"""Звук без Qt: устройства, громкость и профили через pactl (PipeWire или
PulseAudio — команда одна и та же) и диагностика звуковой системы.

Модуль «Звук» (mod_sound.py) только показывает это и вызывает действия.

Диагностика устроена как в менеджере видеокарт: каждое правило — отдельный
класс в RULES (новая проверка = новый класс, остальные не трогаются).
Исправление — кортеж (подпись, вид, аргумент):
    ("…", "pkgs", ["пакет", …])   поставить пакеты (pkexec pacman)
    ("…", "restart", None)         перезапустить звуковые службы пользователя
    ("…", "profile", (карта, профиль))  включить профиль звуковой карты
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

SERVICES = ("pipewire", "pipewire-pulse", "wireplumber")
TEST_SOUND = "/usr/share/sounds/freedesktop/stereo/audio-test-signal.oga"
# пакеты, состояние которых нужно правилам
WATCHED_PKGS = ("pipewire", "pipewire-pulse", "pipewire-alsa", "pipewire-audio", "pipewire-jack", "wireplumber",
                "pulseaudio", "pulseaudio-alsa", "sof-firmware", "alsa-ucm-conf", "alsa-firmware", "alsa-utils",
                "lib32-pipewire", "lib32-libpulse", "steam", "rtkit", "bluez")


def run(cmd: list, timeout: int = 6) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return -1, ""


def _json(*args):
    code, out = run(["pactl", "-f", "json", *args])
    if code != 0 or not out.strip():
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


# ════════════════════════════════════════════════════════════════════════════
#  СНИМОК ЗВУКОВОЙ СИСТЕМЫ
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Port:
    name: str
    description: str
    available: bool = True


@dataclass
class Device:
    """Устройство вывода (sink) или ввода (source)."""
    kind: str                 # "sink" | "source"
    name: str
    description: str
    volume: int = 0           # %, среднее по каналам
    mute: bool = False
    ports: list = field(default_factory=list)
    active_port: str = ""
    card: int | None = None
    is_default: bool = False


@dataclass
class Profile:
    name: str
    description: str
    available: bool = True
    outputs: int = 0
    inputs: int = 0
    priority: int = 0


@dataclass
class Card:
    index: int
    name: str
    description: str
    bus: str = ""             # pci | usb | bluetooth
    profiles: list = field(default_factory=list)
    active_profile: str = ""

    def output_profiles(self) -> list:
        """Доступные профили с выходом, лучший — первым (HDMI без монитора недоступен)."""
        # pro-audio — служебный профиль «сырых» каналов для студийных программ, не обычный выход
        return sorted((p for p in self.profiles if p.outputs and p.available and p.name != "pro-audio"),
                      key=lambda p: -p.priority)


@dataclass
class Snapshot:
    ok: bool = False          # звуковой сервер ответил
    server: str = ""          # «PulseAudio (on PipeWire 1.6.9)»
    sinks: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    cards: list = field(default_factory=list)

    @property
    def on_pipewire(self) -> bool:
        return "pipewire" in self.server.lower()

    @property
    def pipewire_version(self) -> str:
        m = re.search(r"PipeWire\s+([\d.]+)", self.server)
        return m.group(1) if m else ""


def _avg_percent(volume: dict) -> int:
    vals = []
    for ch in (volume or {}).values():
        m = re.match(r"(\d+)%", str(ch.get("value_percent", "")))
        if m:
            vals.append(int(m.group(1)))
    return round(sum(vals) / len(vals)) if vals else 0


def _device(kind: str, d: dict, default: str) -> Device:
    ports = [Port(p.get("name", ""), p.get("description", "") or p.get("name", ""),
                  p.get("availability", "") != "not available") for p in d.get("ports") or []]
    card = d.get("card")
    return Device(kind, d.get("name", ""), d.get("description", "") or d.get("name", ""), _avg_percent(d.get("volume")),
                  bool(d.get("mute")), ports, d.get("active_port") or "",
                  card if isinstance(card, int) and card >= 0 else None, d.get("name") == default)


def _is_monitor(d: dict) -> bool:
    props = d.get("properties") or {}
    return props.get("device.class") == "monitor" or d.get("name", "").endswith(".monitor") or bool(d.get("monitor_of_sink"))


def snapshot() -> Snapshot:
    info = _json("info")
    if not isinstance(info, dict):
        return Snapshot()
    snap = Snapshot(ok=True, server=f"{info.get('server_name', '')}")
    if info.get("server_version") and "PipeWire" not in snap.server:
        snap.server += f" {info['server_version']}"
    ds, dsrc = info.get("default_sink_name", ""), info.get("default_source_name", "")
    snap.sinks = [_device("sink", d, ds) for d in _json("list", "sinks") or []]
    snap.sources = [_device("source", d, dsrc) for d in _json("list", "sources") or [] if not _is_monitor(d)]
    for c in _json("list", "cards") or []:
        props = c.get("properties") or {}
        profiles = [Profile(n, p.get("description", n), bool(p.get("available", True)),
                            int(p.get("sinks", 0) or 0), int(p.get("sources", 0) or 0), int(p.get("priority", 0) or 0))
                    for n, p in (c.get("profiles") or {}).items()]
        snap.cards.append(Card(int(c.get("index", -1)), c.get("name", ""),
                               props.get("device.description") or c.get("name", ""),
                               props.get("device.bus", ""), profiles, c.get("active_profile") or ""))
    return snap


# ════════════════════════════════════════════════════════════════════════════
#  ДЕЙСТВИЯ
# ════════════════════════════════════════════════════════════════════════════
def set_default(dev: Device) -> bool:
    return run(["pactl", f"set-default-{dev.kind}", dev.name])[0] == 0


def set_volume(dev: Device, percent: int) -> bool:
    percent = max(0, min(150, int(percent)))
    return run(["pactl", f"set-{dev.kind}-volume", dev.name, f"{percent}%"])[0] == 0


def set_mute(dev: Device, on: bool) -> bool:
    return run(["pactl", f"set-{dev.kind}-mute", dev.name, "1" if on else "0"])[0] == 0


def set_port(dev: Device, port: str) -> bool:
    return run(["pactl", f"set-{dev.kind}-port", dev.name, port])[0] == 0


def set_profile(card: str, profile: str) -> bool:
    return run(["pactl", "set-card-profile", card, profile])[0] == 0


def test_sound_cmd(dev: Device) -> list | None:
    """Команда проигрывания тестового сигнала на конкретном устройстве вывода."""
    if not os.path.isfile(TEST_SOUND):
        return None
    if shutil.which("pw-play"):
        return ["pw-play", "--target", dev.name, TEST_SOUND]
    if shutil.which("paplay"):
        return ["paplay", "-d", dev.name, TEST_SOUND]
    return None


def fix_command(kind: str, arg) -> list | None:
    if kind == "pkgs":
        # yes: при замене pulseaudio на pipewire-pulse pacman спрашивает про конфликт
        return ["pkexec", "sh", "-c", 'yes | pacman -S --needed "$@"', "sh", *arg]
    if kind == "restart":
        return ["systemctl", "--user", "restart", *SERVICES]
    if kind == "profile":
        card, profile = arg
        return ["pactl", "set-card-profile", card, profile]
    return None


# ════════════════════════════════════════════════════════════════════════════
#  ДИАГНОСТИКА
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Check:
    level: str                # fail | warn | info | ok
    title: str
    detail: str
    fix: tuple | None = None


@dataclass
class AudioHw:
    """Звуковое железо по lspci: «8086:51ca», драйвер ядра, название."""
    vid: str
    did: str
    name: str
    driver: str = ""


@dataclass
class System:
    snap: Snapshot = field(default_factory=Snapshot)
    pkgs: dict = field(default_factory=dict)        # имя -> версия
    services: dict = field(default_factory=dict)    # служба -> active/inactive/…
    hw: list = field(default_factory=list)          # AudioHw
    alsa_cards: int = 0
    modules: set = field(default_factory=set)       # загруженные модули ядра
    multilib: bool = False
    bluetooth: bool = False

    def has(self, pkg: str) -> bool:
        return pkg in self.pkgs

    def pkgver(self, pkg: str) -> str:
        v = self.pkgs.get(pkg, "")
        return re.sub(r"^\d+:", "", v).rsplit("-", 1)[0] if v else ""


def probe_hw() -> list:
    out, cur = [], None
    for line in run(["lspci", "-nnk"], 10)[1].splitlines():
        if line and not line[0].isspace():
            cur = None
            m = re.search(r"(Audio device|Multimedia audio controller|Multimedia controller)\s*\[04\w\w\]:\s*(.+?)\s*\[(\w{4}):(\w{4})\]", line)
            if m:
                cur = AudioHw(m.group(3).lower(), m.group(4).lower(), m.group(2))
                out.append(cur)
        elif cur and "Kernel driver in use:" in line:
            cur.driver = line.split(":", 1)[1].strip()
    return out


def probe(snap: Snapshot | None = None) -> System:
    S = System(snap=snap if snap is not None else snapshot())
    code, out = run(["pacman", "-Q", *WATCHED_PKGS], 15)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            S.pkgs[parts[0]] = parts[1]
    for svc in SERVICES:
        S.services[svc] = run(["systemctl", "--user", "is-active", svc])[1].strip() or "unknown"
    S.hw = probe_hw()
    try:
        cards = open("/proc/asound/cards", encoding="utf-8", errors="ignore").read()
        S.alsa_cards = len(re.findall(r"^\s*\d+\s+\[", cards, re.M))
    except OSError:
        pass
    try:
        S.modules = {l.split()[0] for l in open("/proc/modules", encoding="utf-8", errors="ignore") if l.strip()}
    except OSError:
        pass
    try:
        S.multilib = bool(re.search(r"^\s*\[multilib\]", open("/etc/pacman.conf", encoding="utf-8").read(), re.M))
    except OSError:
        pass
    S.bluetooth = os.path.isdir("/sys/class/bluetooth") and bool(os.listdir("/sys/class/bluetooth"))
    return S


class Rule(ABC):
    @abstractmethod
    def run(self, S: System, tr) -> list: ...


class ServerRule(Rule):
    """Отвечает ли звуковой сервер и какой он: PipeWire или старый PulseAudio."""

    def run(self, S, tr):
        if not S.snap.ok:
            return [Check("fail", tr("snd.chk_no_server"), tr("snd.chk_no_server_d"), (tr("snd.fix_restart"), "restart", None))]
        if not S.snap.on_pipewire:
            return [Check("warn", tr("snd.chk_pulseaudio"), tr("snd.chk_pulseaudio_d"),
                          (tr("snd.fix_to_pipewire"), "pkgs", ["pipewire-pulse", "pipewire-alsa", "wireplumber"]))]
        return [Check("ok", tr("snd.chk_server_ok").format(S.snap.pipewire_version), tr("snd.chk_server_ok_d"))]


class ServicesRule(Rule):
    def run(self, S, tr):
        if not S.snap.on_pipewire and S.snap.ok:
            return []
        dead = [s for s, st in S.services.items() if st != "active"]
        if dead:
            return [Check("fail", tr("snd.chk_services_down"), ", ".join(dead), (tr("snd.fix_restart"), "restart", None))]
        return []


class VersionRule(Rule):
    """Пакет PipeWire обновился, а работает ещё старая версия — до перезапуска возможны сбои."""

    def run(self, S, tr):
        running, installed = S.snap.pipewire_version, S.pkgver("pipewire")
        if running and installed and running != installed:
            return [Check("warn", tr("snd.chk_version").format(running, installed), tr("snd.chk_version_d"),
                          (tr("snd.fix_restart"), "restart", None))]
        return []


class NoCardsRule(Rule):
    """Звуковое железо есть, а ALSA не видит ни одной карты — почти всегда нет прошивки."""

    def run(self, S, tr):
        if S.alsa_cards or not S.hw:
            return []
        fix_pkgs = [p for p in ("sof-firmware", "alsa-firmware", "alsa-ucm-conf") if not S.has(p)]
        return [Check("fail", tr("snd.chk_no_cards"), tr("snd.chk_no_cards_d"),
                      (tr("snd.fix_firmware"), "pkgs", fix_pkgs) if fix_pkgs else None)]


class SofRule(Rule):
    """Современные ноутбуки (Intel SOF: встроенные микрофоны-решётки) без прошивки и профилей UCM
    теряют микрофон или весь звук."""

    def run(self, S, tr):
        # модули snd_sof ядро грузит всегда — смотрим, какой драйвер реально обслуживает устройство
        sof = any(h.driver.startswith("sof") for h in S.hw)
        if not sof:
            return []
        missing = [p for p in ("sof-firmware", "alsa-ucm-conf") if not S.has(p)]
        if missing:
            return [Check("fail", tr("snd.chk_sof_missing"), ", ".join(missing),
                          (tr("snd.fix_firmware"), "pkgs", missing))]
        return [Check("ok", tr("snd.chk_sof_ok"), tr("snd.chk_sof_ok_d"))]


class DummyOutputRule(Rule):
    """Только «Пустой выход» (auto_null), хотя карты есть."""

    def run(self, S, tr):
        real = [d for d in S.snap.sinks if d.name != "auto_null"]
        if not S.snap.ok or real or not S.snap.cards:
            return []
        for c in S.snap.cards:
            outs = c.output_profiles()
            if outs:
                best = outs[0]
                return [Check("fail", tr("snd.chk_dummy"), tr("snd.chk_dummy_d").format(c.description),
                              (tr("snd.fix_profile").format(best.description), "profile", (c.name, best.name)))]
        return [Check("fail", tr("snd.chk_dummy"), tr("snd.chk_dummy_none"), (tr("snd.fix_restart"), "restart", None))]


class ProfileOffRule(Rule):
    """Карта выключена (профиль «off»), хотя у неё есть доступный выход: подключено, но не звучит.
    HDMI без монитора сюда не попадает — его профили недоступны."""

    def run(self, S, tr):
        if not [d for d in S.snap.sinks if d.name != "auto_null"]:
            return []  # совсем без выходов — это «Пустой выход», о нём говорит DummyOutputRule
        res = []
        for c in S.snap.cards:
            outs = c.output_profiles()
            if c.active_profile == "off" and outs:
                res.append(Check("warn", tr("snd.chk_card_off").format(c.description), tr("snd.chk_card_off_d"),
                                 (tr("snd.fix_profile").format(outs[0].description), "profile", (c.name, outs[0].name))))
        return res


class AlsaBridgeRule(Rule):
    """Программы, которые пишут прямо в ALSA (старые игры, Wine без pulse), идут мимо PipeWire."""

    def run(self, S, tr):
        if S.snap.on_pipewire and not S.has("pipewire-alsa"):
            return [Check("warn", tr("snd.chk_alsa_bridge"), tr("snd.chk_alsa_bridge_d"),
                          (tr("snd.fix_install").format("pipewire-alsa"), "pkgs", ["pipewire-alsa"]))]
        return []


class GamesRule(Rule):
    """32-битные игры и Steam: без 32-битного libpulse у Steam Web Helper и части игр пропадает звук."""

    def run(self, S, tr):
        if not S.multilib or not S.has("steam"):
            return []
        missing = [p for p in ("lib32-libpulse", "lib32-pipewire") if not S.has(p)]
        if missing:
            return [Check("warn", tr("snd.chk_games"), tr("snd.chk_games_d").format(", ".join(missing)),
                          (tr("snd.fix_install").format(", ".join(missing)), "pkgs", missing))]
        return [Check("ok", tr("snd.chk_games_ok"), "lib32-libpulse, lib32-pipewire")]


class BluetoothRule(Rule):
    def run(self, S, tr):
        if not S.bluetooth or not S.snap.on_pipewire:
            return []
        missing = [p for p in ("pipewire-audio", "bluez") if not S.has(p)]
        if missing:
            return [Check("warn", tr("snd.chk_bt"), tr("snd.chk_bt_d"),
                          (tr("snd.fix_install").format(", ".join(missing)), "pkgs", missing))]
        return []


class LatencyRule(Rule):
    """rtkit даёт звуку приоритет реального времени — меньше треска под нагрузкой (игры, сборка)."""

    def run(self, S, tr):
        if S.snap.on_pipewire and not S.has("rtkit"):
            return [Check("info", tr("snd.chk_rtkit"), tr("snd.chk_rtkit_d"),
                          (tr("snd.fix_install").format("rtkit"), "pkgs", ["rtkit"]))]
        return []


class HdmiRule(Rule):
    """Звук по HDMI/DisplayPort идёт через видеокарту — его карта обычно выключена, пока нет монитора."""

    def run(self, S, tr):
        gpu_audio = [h for h in S.hw if h.vid in ("10de", "1002") or "hdmi" in h.name.lower()]
        if gpu_audio:
            return [Check("info", tr("snd.chk_hdmi"), tr("snd.chk_hdmi_d"))]
        return []


RULES: tuple = (ServerRule(), ServicesRule(), VersionRule(), NoCardsRule(), SofRule(), DummyOutputRule(),
                ProfileOffRule(), AlsaBridgeRule(), GamesRule(), BluetoothRule(), LatencyRule(), HdmiRule())
LVL_ORDER = {"fail": 0, "warn": 1, "info": 2, "ok": 3}


def diagnose(S: System, tr) -> list:
    res = []
    for rule in RULES:
        res += rule.run(S, tr)
    return sorted(res, key=lambda c: LVL_ORDER.get(c.level, 9))
