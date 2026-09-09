"""Screen Brightness module.

Fixes brightness sliders that "move but don't darken the screen" — the usual
cause on desktops with an NVIDIA GPU is that the only /sys/class/backlight
entry is a fake nvidia_0 stub that doesn't drive any real hardware. This
module offers three independent brightness paths and shows whichever ones
are actually detected:

  1. DDC/CI (ddcutil)   — real hardware backlight on external monitors,
                           the same control the monitor's own buttons use.
  2. sysfs backlight     — real hardware backlight on laptop/internal panels.
  3. xrandr software dim — a gamma-based dimming filter that always works,
                           used as the universal fallback.
"""

import glob
import os
import re
import shutil
import subprocess
import threading
import time

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from base_module import BaseModule

_BACKLIGHT_DIR = "/sys/class/backlight"
_GRUB_DEFAULT_FILE = "/etc/default/grub"
_GRUB_CFG_OUT = "/boot/grub/grub.cfg"

# (parameter value, i18n key for its short label, i18n key for its description).
# All are real, documented Linux kernel parameters — see the "acpi_backlight="
# entry in Documentation/admin-guide/kernel-parameters.txt for the first four.
_KERNEL_PARAM_CHOICES = [
    ("acpi_backlight=native", "brightness.kparam_opt_native"),
    ("acpi_backlight=vendor", "brightness.kparam_opt_vendor"),
    ("acpi_backlight=video", "brightness.kparam_opt_video"),
    ("acpi_backlight=none", "brightness.kparam_opt_none"),
    ("amdgpu.backlight=0", "brightness.kparam_opt_amdgpu_off"),
]

_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
)
_BTN_APPLY = (
    "QPushButton{background:rgb(80,55,130);color:white;"
    "border-radius:8px;padding:8px 22px;font-size:14px;font-weight:bold;"
    "border:1px solid rgb(110,80,170);}"
    "QPushButton:hover{background:rgb(110,75,170);"
    "border:1px solid rgb(140,100,210);}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_RESULT_OK = "QLabel{color:rgb(140,220,160);font-size:12px;background:transparent;}"
_RESULT_ERR = "QLabel{color:rgb(255,130,130);font-size:12px;background:transparent;}"
_WARN_STYLE = "QLabel{color:rgb(220,185,80);font-size:12px;background:transparent;}"
_STATUS_MONO = (
    "QLabel{color:rgb(170,165,195);font-size:12px;font-family:monospace;"
    "background:rgb(20,18,33);border:1px solid rgb(50,47,72);"
    "border-radius:6px;padding:8px 12px;}"
)


# ── Detection / control helpers ─────────────────────────────────────────────

def _is_wayland_session() -> bool:
    """xrandr talks to XWayland's compatibility X server, not the real Wayland
    compositor — under Wayland its commands succeed but have zero visible
    effect on screen, so the whole "software brightness" path is a no-op."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
        os.environ.get("WAYLAND_DISPLAY")
    )


def _list_xrandr_outputs() -> dict[str, float]:
    """Return {output_name: current_brightness_float} for connected outputs."""
    if _is_wayland_session() or not shutil.which("xrandr"):
        return {}
    try:
        out = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, timeout=5)
    except Exception:
        return {}
    result: dict[str, float] = {}
    current = None
    for line in out.stdout.splitlines():
        if line and not line[0].isspace():
            m = re.match(r"^(\S+) connected", line)
            current = m.group(1) if m else None
        elif current:
            s = line.strip()
            if s.startswith("Brightness:"):
                try:
                    result[current] = float(s.split(":", 1)[1].strip())
                except ValueError:
                    pass
    return result


def _set_xrandr_brightness(output: str, value: float) -> bool:
    try:
        proc = subprocess.run(
            ["xrandr", "--output", output, "--brightness", f"{value:.2f}"],
            capture_output=True, text=True, timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _list_backlight_devices() -> list[tuple[str, int, int]]:
    """Return [(name, current, max)] for real sysfs backlight devices.

    When a native GPU-driver backlight (amdgpu_bl0, intel_backlight, ...)
    coexists with a generic acpi_video* one, the acpi_video entry is dropped:
    it accepts writes but on most AMD/Intel laptops doesn't actually change
    panel brightness, which is the "slider moves, screen doesn't darken" bug.
    """
    if not os.path.isdir(_BACKLIGHT_DIR):
        return []
    result = []
    for name in sorted(os.listdir(_BACKLIGHT_DIR)):
        dev_dir = os.path.join(_BACKLIGHT_DIR, name)
        try:
            with open(os.path.join(dev_dir, "brightness")) as f:
                cur = int(f.read().strip())
            with open(os.path.join(dev_dir, "max_brightness")) as f:
                mx = int(f.read().strip())
            if mx > 0:
                result.append((name, cur, mx))
        except (OSError, ValueError):
            continue

    native = [d for d in result if not d[0].startswith("acpi_video")]
    if native:
        return native
    return result


def _get_logind_session_path() -> str | None:
    """Resolve this process's systemd-logind session D-Bus object path.

    Calling Session.SetBrightness on this path lets the *active session's own
    user* change backlight brightness with no password prompt at all — this
    is the exact mechanism KDE Powerdevil itself uses, and unlike xrandr it
    also works under Wayland.
    """
    try:
        out = subprocess.run(
            ["busctl", "call", "org.freedesktop.login1", "/org/freedesktop/login1",
             "org.freedesktop.login1.Manager", "GetSessionByPID", "u", str(os.getpid())],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            m = re.search(r'"([^"]+)"', out.stdout)
            if m:
                return m.group(1)
    except Exception:
        pass

    # Fallback for the rare case GetSessionByPID can't place our own PID
    # (e.g. cgroup oddities): look up our own seat0 session by username.
    try:
        import getpass
        user = getpass.getuser()
        out = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True, text=True, timeout=5,
        )
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == user and parts[3] == "seat0":
                res = subprocess.run(
                    ["busctl", "call", "org.freedesktop.login1", "/org/freedesktop/login1",
                     "org.freedesktop.login1.Manager", "GetSession", "s", parts[0]],
                    capture_output=True, text=True, timeout=5,
                )
                if res.returncode == 0:
                    m = re.search(r'"([^"]+)"', res.stdout)
                    if m:
                        return m.group(1)
    except Exception:
        pass
    return None


def _set_backlight_via_logind(name: str, target: int) -> bool:
    session_path = _get_logind_session_path()
    if not session_path:
        return False
    try:
        proc = subprocess.run(
            ["busctl", "call", "org.freedesktop.login1", session_path,
             "org.freedesktop.login1.Session", "SetBrightness",
             "ssu", "backlight", name, str(target)],
            capture_output=True, text=True, timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _set_backlight(name: str, percent: int) -> bool:
    """Set sysfs backlight brightness by percent.

    Tries, in order: systemd-logind's own SetBrightness (no password, works
    on Wayland and X11) → brightnessctl → raw sysfs write → pkexec as a last
    resort for setups where none of the above have the right permissions.
    """
    dev_dir = os.path.join(_BACKLIGHT_DIR, name)
    try:
        with open(os.path.join(dev_dir, "max_brightness")) as f:
            mx = int(f.read().strip())
    except (OSError, ValueError):
        mx = None
    target = max(1, round(mx * percent / 100)) if mx else None

    if target is not None and _set_backlight_via_logind(name, target):
        return True

    if shutil.which("brightnessctl"):
        for cmd in (
            ["brightnessctl", "-d", name, "set", f"{percent}%"],
            ["pkexec", "brightnessctl", "-d", name, "set", f"{percent}%"],
        ):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if proc.returncode == 0:
                    return True
            except Exception:
                continue
        return False

    if target is None:
        return False

    try:
        with open(os.path.join(dev_dir, "brightness"), "w") as f:
            f.write(str(target))
        return True
    except (OSError, PermissionError):
        pass

    try:
        proc = subprocess.run(
            ["pkexec", "tee", os.path.join(dev_dir, "brightness")],
            input=str(target), capture_output=True, text=True, timeout=15,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _list_ddc_displays() -> list[tuple[int, str]]:
    """Return [(display_num, model_name)] from `ddcutil detect`."""
    if not shutil.which("ddcutil"):
        return []
    try:
        out = subprocess.run(
            ["ddcutil", "detect", "--brief"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []
    if not out.stdout.strip():
        return []

    result = []
    current_num = None
    model = ""
    for line in out.stdout.splitlines():
        s = line.strip()
        m = re.match(r"Display (\d+)", s)
        if m:
            if current_num is not None:
                result.append((current_num, model or f"Display {current_num}"))
            current_num = int(m.group(1))
            model = ""
        elif s.startswith("Monitor:"):
            parts = s.split(":", 1)[1].strip().split(",")
            model = parts[1].strip() if len(parts) > 1 else s
    if current_num is not None:
        result.append((current_num, model or f"Display {current_num}"))
    return result


def _get_ddc_brightness(display_num: int) -> tuple[int, int] | None:
    if not shutil.which("ddcutil"):
        return None
    try:
        out = subprocess.run(
            ["ddcutil", "--display", str(display_num), "getvcp", "10", "--terse"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    parts = out.stdout.split()
    try:
        idx = parts.index("10")
        return int(parts[idx + 2]), int(parts[idx + 3])
    except (ValueError, IndexError):
        return None


def _set_ddc_brightness(display_num: int, value: int) -> bool:
    for cmd in (
        ["ddcutil", "--display", str(display_num), "setvcp", "10", str(value)],
        ["pkexec", "ddcutil", "--display", str(display_num), "setvcp", "10", str(value)],
    ):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                return True
        except Exception:
            continue
    return False


# ── Kernel boot parameter (GRUB) ────────────────────────────────────────────
#
# Some laptops (this includes AMD Ryzen APUs with Vega/Radeon graphics)
# register *two* backlight interfaces at boot: a real one from the GPU
# driver (amdgpu_bl0, intel_backlight, ...) and a fake one from the generic
# ACPI video module (acpi_video0) that accepts writes but never changes the
# panel. Whichever one KDE's own brightness keys/OSD happen to pick can be
# the fake one — same root cause as this module's own slider bug, just one
# layer deeper. The acpi_backlight=native kernel parameter stops the fake
# interface from being created at all, fixing every consumer at once
# (this module, KDE Powerdevil, brightness keys).

def _is_laptop() -> bool:
    try:
        return any(n.startswith("BAT") for n in os.listdir("/sys/class/power_supply"))
    except OSError:
        return False


def _grub_available() -> bool:
    return os.path.isfile(_GRUB_DEFAULT_FILE) and shutil.which("grub-mkconfig") is not None


def _backlight_param_recommended() -> bool:
    """True when this looks like the "fake + real backlight" duplicate bug."""
    if not _is_laptop():
        return False
    if not os.path.isdir(_BACKLIGHT_DIR):
        return True  # laptop, but no backlight interface exists at all
    try:
        entries = os.listdir(_BACKLIGHT_DIR)
    except OSError:
        return False
    if not entries:
        return True
    native = [e for e in entries if not e.startswith("acpi_video")]
    acpi = [e for e in entries if e.startswith("acpi_video")]
    return bool(native) and bool(acpi)


def _read_grub_cmdline() -> str | None:
    try:
        with open(_GRUB_DEFAULT_FILE, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None
    m = re.search(r'^GRUB_CMDLINE_LINUX_DEFAULT="([^"]*)"', content, re.MULTILINE)
    return m.group(1) if m else ""


def _read_running_cmdline_params() -> set[str]:
    try:
        with open("/proc/cmdline", encoding="utf-8") as f:
            return set(f.read().split())
    except OSError:
        return set()


def _compute_param_status(cmdline: str | None, running_params: set[str], param: str) -> str:
    """Return 'active', 'pending' (configured but not yet booted) or 'absent'."""
    configured = cmdline is not None and param in cmdline.split()
    running = param in running_params
    if configured and running:
        return "active"
    if configured:
        return "pending"
    return "absent"


def _apply_kernel_param(param: str) -> tuple[bool, str]:
    """Back up /etc/default/grub, append `param`, regenerate grub.cfg."""
    try:
        with open(_GRUB_DEFAULT_FILE, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return False, str(e)

    def _sub(m: re.Match) -> str:
        existing = m.group(1)
        if param in existing.split():
            return m.group(0)
        new_val = (existing + " " + param).strip()
        return f'GRUB_CMDLINE_LINUX_DEFAULT="{new_val}"'

    if re.search(r'^GRUB_CMDLINE_LINUX_DEFAULT="[^"]*"', content, re.MULTILINE):
        new_content = re.sub(
            r'^GRUB_CMDLINE_LINUX_DEFAULT="([^"]*)"', _sub, content, count=1, flags=re.MULTILINE
        )
    else:
        new_content = content.rstrip("\n") + f'\nGRUB_CMDLINE_LINUX_DEFAULT="{param}"\n'

    tmp_path = f"/tmp/equestria-grub-{os.getpid()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.chmod(tmp_path, 0o644)
    except OSError as e:
        return False, str(e)

    backup_path = f"{_GRUB_DEFAULT_FILE}.equestria-backup-{time.strftime('%Y%m%d-%H%M%S')}"
    shell_cmd = (
        f"cp {_GRUB_DEFAULT_FILE} {backup_path} && "
        f"cp {tmp_path} {_GRUB_DEFAULT_FILE} && "
        f"grub-mkconfig -o {_GRUB_CFG_OUT}"
    )
    try:
        proc = subprocess.run(
            ["pkexec", "sh", "-c", shell_cmd],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        return False, str(e)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if proc.returncode != 0:
        return False, (proc.stdout + proc.stderr).strip()
    return True, backup_path


def _list_grub_backups() -> list[str]:
    """Return backup files created by this module, newest first."""
    pattern = f"{_GRUB_DEFAULT_FILE}.equestria-backup-*"
    return sorted(glob.glob(pattern), reverse=True)


def _restore_grub_backup(backup_path: str) -> tuple[bool, str]:
    """Copy a backup back over /etc/default/grub and regenerate grub.cfg."""
    if backup_path not in _list_grub_backups():
        return False, "Unknown backup file"

    shell_cmd = f"cp {backup_path} {_GRUB_DEFAULT_FILE} && grub-mkconfig -o {_GRUB_CFG_OUT}"
    try:
        proc = subprocess.run(
            ["pkexec", "sh", "-c", shell_cmd],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        return False, str(e)

    if proc.returncode != 0:
        return False, (proc.stdout + proc.stderr).strip()
    return True, backup_path


# ── Worker ───────────────────────────────────────────────────────────────────

class _DetectWorker(QObject):
    done = pyqtSignal(dict)

    def run(self):
        info: dict = {
            "backlight": _list_backlight_devices(),
            "xrandr": _list_xrandr_outputs(),
            "is_wayland": _is_wayland_session(),
            "ddc": [],
            "grub_available": _grub_available(),
            "grub_recommended": _backlight_param_recommended(),
            "grub_cmdline": _read_grub_cmdline(),
            "grub_running_params": _read_running_cmdline_params(),
            "grub_backups": _list_grub_backups(),
        }
        for num, model in _list_ddc_displays():
            got = _get_ddc_brightness(num)
            if got is not None:
                cur, mx = got
                info["ddc"].append((num, model, cur, mx))
        self.done.emit(info)


class _ApplyKernelParamWorker(QObject):
    done = pyqtSignal(bool, str)

    def __init__(self, param: str):
        super().__init__()
        self._param = param

    def run(self):
        ok, msg = _apply_kernel_param(self._param)
        self.done.emit(ok, msg)


class _RestoreBackupWorker(QObject):
    done = pyqtSignal(bool, str)

    def __init__(self, backup_path: str):
        super().__init__()
        self._path = backup_path

    def run(self):
        ok, msg = _restore_grub_backup(self._path)
        self.done.emit(ok, msg)


# ── Module ───────────────────────────────────────────────────────────────────

class BrightnessModule(BaseModule):
    module_id = "mod_brightness"
    display_name_key = "module.brightness.name"
    description_key = "module.brightness.desc"
    category = "system"
    icon = "🔆"
    sort_order = 17
    required_binary = ""
    package_name = ""

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

        header_row = QHBoxLayout()
        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        header_row.addWidget(self._title_lbl)
        header_row.addStretch()
        self._refresh_btn = QPushButton(self.t("brightness.refresh"))
        self._refresh_btn.setStyleSheet(_BTN_ACTION)
        self._refresh_btn.clicked.connect(self._refresh)
        header_row.addWidget(self._refresh_btn)
        layout.addLayout(header_row)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(20)
        layout.addLayout(self._cards_layout)

        self._empty_lbl = QLabel(self.t("brightness.loading"))
        self._empty_lbl.setObjectName("FieldHint")
        self._empty_lbl.setWordWrap(True)
        layout.addWidget(self._empty_lbl)

        layout.addStretch()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_shown(self) -> None:
        self._refresh()

    def apply_language(self) -> None:
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._refresh_btn.setText(self.t("brightness.refresh"))
        self._refresh()

    # ── Refresh / detect ─────────────────────────────────────────────────────

    def _clear_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _refresh(self):
        self._refresh_btn.setEnabled(False)
        self._empty_lbl.setText(self.t("brightness.loading"))
        self._empty_lbl.show()
        self._clear_cards()

        worker = _DetectWorker()
        worker.done.connect(self._on_detected)
        self._detect_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_detected(self, info: dict):
        self._refresh_btn.setEnabled(True)
        self._clear_cards()
        any_section = False

        if info["ddc"]:
            any_section = True
            self._build_ddc_card(info["ddc"])
        if info["backlight"]:
            any_section = True
            self._build_backlight_card(info["backlight"])
        if info["is_wayland"]:
            any_section = True
            self._build_software_unavailable_card()
        elif info["xrandr"]:
            any_section = True
            self._build_xrandr_card(info["xrandr"])

        if info["grub_available"]:
            self._build_kernel_param_card(
                info["grub_cmdline"],
                info["grub_running_params"],
                info["grub_backups"],
                info["grub_recommended"],
            )

        self._empty_lbl.setVisible(not any_section)
        if not any_section:
            self._empty_lbl.setText(self.t("brightness.none_found"))

    # ── Slider row helper ────────────────────────────────────────────────────

    def _make_slider_row(self, parent_layout, label_text: str, initial_percent: int, apply_fn):
        row = QHBoxLayout()

        name_lbl = QLabel(label_text)
        name_lbl.setObjectName("FieldLabel")
        name_lbl.setMinimumWidth(160)
        row.addWidget(name_lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(1, 100)
        slider.setValue(max(1, min(100, initial_percent)))
        row.addWidget(slider, stretch=1)

        value_lbl = QLabel(f"{slider.value()}%")
        value_lbl.setObjectName("FieldLabel")
        value_lbl.setMinimumWidth(40)
        row.addWidget(value_lbl)

        debounce = QTimer(slider)
        debounce.setSingleShot(True)
        debounce.setInterval(150)

        def _apply():
            threading.Thread(target=apply_fn, args=(slider.value(),), daemon=True).start()

        debounce.timeout.connect(_apply)

        def _on_value_changed(v: int):
            value_lbl.setText(f"{v}%")
            debounce.start()

        slider.valueChanged.connect(_on_value_changed)
        parent_layout.addLayout(row)

    # ── DDC/CI card ───────────────────────────────────────────────────────────

    def _build_ddc_card(self, ddc_list: list[tuple[int, str, int, int]]):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel(self.t("brightness.ddc_title"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(self.t("brightness.ddc_hint"))
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for num, model, cur, mx in ddc_list:
            percent = round(cur * 100 / mx) if mx else cur

            def _apply(v: int, n: int = num):
                _set_ddc_brightness(n, v)

            self._make_slider_row(layout, model, percent, _apply)

        self._cards_layout.addWidget(card)

    # ── Backlight card ───────────────────────────────────────────────────────

    def _build_backlight_card(self, devices: list[tuple[str, int, int]]):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel(self.t("brightness.backlight_title"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(self.t("brightness.backlight_hint"))
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for name, cur, mx in devices:
            percent = round(cur * 100 / mx) if mx else cur

            def _apply(v: int, n: str = name):
                _set_backlight(n, v)

            self._make_slider_row(layout, name, percent, _apply)

        self._cards_layout.addWidget(card)

    # ── Software (xrandr) card ───────────────────────────────────────────────

    def _build_xrandr_card(self, xrandr_map: dict[str, float]):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel(self.t("brightness.software_title"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(self.t("brightness.software_hint"))
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for output, current in sorted(xrandr_map.items()):
            percent = round(max(0.1, min(1.0, current)) * 100)

            def _apply(v: int, o: str = output):
                _set_xrandr_brightness(o, v / 100)

            self._make_slider_row(layout, output, percent, _apply)

        self._cards_layout.addWidget(card)

    # ── Software unavailable (Wayland) card ──────────────────────────────────

    def _build_software_unavailable_card(self):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel(self.t("brightness.software_title"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(self.t("brightness.software_wayland_hint"))
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._cards_layout.addWidget(card)

    # ── Kernel boot parameter card ───────────────────────────────────────────

    def _build_kernel_param_card(
        self, cmdline: str | None, running_params: set[str], backups: list[str], recommended: bool
    ):
        self._kparam_cmdline = cmdline
        self._kparam_running = running_params

        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel(self.t("brightness.kernel_param_title"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(self.t("brightness.kernel_param_hint"))
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        if recommended:
            recommended_lbl = QLabel(self.t("brightness.kernel_param_recommended_hint"))
            recommended_lbl.setStyleSheet(_WARN_STYLE)
            recommended_lbl.setWordWrap(True)
            layout.addWidget(recommended_lbl)

        # -- parameter choice --
        choice_lbl = QLabel(self.t("brightness.kparam_choice_label"))
        choice_lbl.setObjectName("FieldLabel")
        layout.addWidget(choice_lbl)

        self._kparam_combo = QComboBox()
        for value, label_key in _KERNEL_PARAM_CHOICES:
            self._kparam_combo.addItem(f"{value} — {self.t(label_key)}", value)

        # Pre-select whichever of the known parameters is already configured,
        # so the combo reflects reality instead of always resetting to the
        # first entry — otherwise it would silently hide an already-applied
        # non-default choice.
        initial_idx = 0
        configured = set((cmdline or "").split())
        for i, (value, _label_key) in enumerate(_KERNEL_PARAM_CHOICES):
            if value in configured:
                initial_idx = i
                break
        self._kparam_combo.setCurrentIndex(initial_idx)

        self._kparam_combo.currentIndexChanged.connect(self._refresh_kparam_preview)
        layout.addWidget(self._kparam_combo)

        # -- live before/after preview, so Apply never acts on unseen data --
        self._kparam_preview_lbl = QLabel()
        self._kparam_preview_lbl.setStyleSheet(_STATUS_MONO)
        self._kparam_preview_lbl.setWordWrap(True)
        layout.addWidget(self._kparam_preview_lbl)

        self._kparam_status_lbl = QLabel()
        self._kparam_status_lbl.setWordWrap(True)
        layout.addWidget(self._kparam_status_lbl)

        row = QHBoxLayout()
        self._kparam_apply_btn = QPushButton(self.t("brightness.kernel_param_apply_btn"))
        self._kparam_apply_btn.setStyleSheet(_BTN_APPLY)
        self._kparam_apply_btn.clicked.connect(self._on_apply_kernel_param)
        row.addWidget(self._kparam_apply_btn)
        row.addStretch()
        layout.addLayout(row)

        self._kparam_result_lbl = QLabel("")
        self._kparam_result_lbl.setWordWrap(True)
        self._kparam_result_lbl.hide()
        layout.addWidget(self._kparam_result_lbl)

        self._refresh_kparam_preview()

        # -- backups: view/restore what this module has changed before --
        backups_title = QLabel(self.t("brightness.kparam_backups_title"))
        backups_title.setObjectName("SectionTitle")
        layout.addWidget(backups_title)

        if backups:
            self._kparam_backup_combo = QComboBox()
            for path in backups:
                self._kparam_backup_combo.addItem(os.path.basename(path), path)
            layout.addWidget(self._kparam_backup_combo)

            restore_row = QHBoxLayout()
            self._kparam_restore_btn = QPushButton(self.t("brightness.kparam_restore_btn"))
            self._kparam_restore_btn.setStyleSheet(_BTN_ACTION)
            self._kparam_restore_btn.clicked.connect(self._on_restore_backup)
            restore_row.addWidget(self._kparam_restore_btn)
            restore_row.addStretch()
            layout.addLayout(restore_row)
        else:
            self._kparam_backup_combo = None
            no_backups_lbl = QLabel(self.t("brightness.kparam_no_backups"))
            no_backups_lbl.setObjectName("FieldHint")
            no_backups_lbl.setWordWrap(True)
            layout.addWidget(no_backups_lbl)

        self._kparam_restore_result_lbl = QLabel("")
        self._kparam_restore_result_lbl.setWordWrap(True)
        self._kparam_restore_result_lbl.hide()
        layout.addWidget(self._kparam_restore_result_lbl)

        self._cards_layout.addWidget(card)

    def _selected_kparam(self) -> str:
        idx = self._kparam_combo.currentIndex()
        return _KERNEL_PARAM_CHOICES[idx][0]

    def _refresh_kparam_preview(self):
        idx = self._kparam_combo.currentIndex()
        if idx < 0:
            return
        value, label_key = _KERNEL_PARAM_CHOICES[idx]
        self._kparam_option_hint_text = self.t(f"{label_key}_desc")

        current = self._kparam_cmdline or ""
        after = current if value in current.split() else (current + " " + value).strip()
        self._kparam_preview_lbl.setText(
            f"{self._kparam_option_hint_text}\n\n"
            f'{self.t("brightness.kparam_preview_before")}: GRUB_CMDLINE_LINUX_DEFAULT="{current}"\n'
            f'{self.t("brightness.kparam_preview_after")}:  GRUB_CMDLINE_LINUX_DEFAULT="{after}"'
        )

        status = _compute_param_status(self._kparam_cmdline, self._kparam_running, value)
        self._set_kernel_param_status(status)

    def _set_kernel_param_status(self, status: str):
        if status == "active":
            self._kparam_status_lbl.setText(self.t("brightness.kernel_param_status_active"))
            self._kparam_status_lbl.setStyleSheet(_RESULT_OK)
            self._kparam_apply_btn.setEnabled(False)
        elif status == "pending":
            self._kparam_status_lbl.setText(self.t("brightness.kernel_param_status_pending"))
            self._kparam_status_lbl.setStyleSheet(_WARN_STYLE)
            self._kparam_apply_btn.setEnabled(False)
        else:
            self._kparam_status_lbl.setText(self.t("brightness.kernel_param_status_absent"))
            self._kparam_status_lbl.setStyleSheet("")
            self._kparam_apply_btn.setEnabled(True)

    def _on_apply_kernel_param(self):
        value = self._selected_kparam()
        current = self._kparam_cmdline or ""
        after = current if value in current.split() else (current + " " + value).strip()

        confirm_text = (
            self.t("brightness.kernel_param_confirm_text")
            .replace("{0}", _GRUB_DEFAULT_FILE)
            .replace("{1}", value)
            .replace("{2}", current)
            .replace("{3}", after)
        )
        reply = QMessageBox.question(
            self._widget,
            self.t("brightness.kernel_param_confirm_title"),
            confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._kparam_apply_btn.setEnabled(False)
        self._kparam_result_lbl.setText(self.t("brightness.kernel_param_applying"))
        self._kparam_result_lbl.setStyleSheet("")
        self._kparam_result_lbl.show()

        worker = _ApplyKernelParamWorker(value)
        worker.done.connect(self._on_kernel_param_applied)
        self._kparam_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_kernel_param_applied(self, ok: bool, message: str):
        if ok:
            text = self.t("brightness.kernel_param_ok").replace("{0}", message)
            QMessageBox.information(self._widget, self.t("brightness.kernel_param_confirm_title"), text)
            self._refresh()
        else:
            self._kparam_apply_btn.setEnabled(True)
            text = self.t("brightness.kernel_param_err")
            if message:
                text += f"\n{message[:400]}"
            self._kparam_result_lbl.setText(text)
            self._kparam_result_lbl.setStyleSheet(_RESULT_ERR)

    # ── Backup restore ────────────────────────────────────────────────────────

    def _on_restore_backup(self):
        if not self._kparam_backup_combo:
            return
        path = self._kparam_backup_combo.currentData()
        if not path:
            return

        confirm_text = self.t("brightness.kparam_restore_confirm_text").replace(
            "{0}", os.path.basename(path)
        )
        reply = QMessageBox.question(
            self._widget,
            self.t("brightness.kernel_param_confirm_title"),
            confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._kparam_restore_btn.setEnabled(False)
        self._kparam_restore_result_lbl.setText(self.t("brightness.kparam_restoring"))
        self._kparam_restore_result_lbl.setStyleSheet("")
        self._kparam_restore_result_lbl.show()

        worker = _RestoreBackupWorker(path)
        worker.done.connect(self._on_backup_restored)
        self._kparam_restore_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_backup_restored(self, ok: bool, message: str):
        if ok:
            QMessageBox.information(
                self._widget,
                self.t("brightness.kernel_param_confirm_title"),
                self.t("brightness.kparam_restore_ok"),
            )
            self._refresh()
        else:
            self._kparam_restore_btn.setEnabled(True)
            text = self.t("brightness.kparam_restore_err")
            if message:
                text += f"\n{message[:400]}"
            self._kparam_restore_result_lbl.setText(text)
            self._kparam_restore_result_lbl.setStyleSheet(_RESULT_ERR)
