"""GPU Settings module — driver management, status, and diagnostics via pg-gpu-sync."""

import os
import shutil
import subprocess
import threading

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from base_module import BaseModule

# ── Styles ────────────────────────────────────────────────────────────────────

_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_BTN_DANGER = (
    "QPushButton{background:rgb(90,40,40);color:rgb(255,180,180);"
    "border-radius:6px;padding:6px 14px;font-size:13px;"
    "border:1px solid rgb(140,60,60);}"
    "QPushButton:hover{background:rgb(140,50,50);color:white;}"
)
_RESULT_OK = "QLabel{color:rgb(140,220,160);font-size:12px;background:transparent;}"
_RESULT_ERR = "QLabel{color:rgb(255,130,130);font-size:12px;background:transparent;}"
_STATUS_MONO = (
    "QLabel{color:rgb(170,165,195);font-size:12px;font-family:monospace;"
    "background:rgb(20,18,33);border:1px solid rgb(50,47,72);"
    "border-radius:6px;padding:8px 12px;}"
)
_WARN_STYLE = "QLabel{color:rgb(220,185,80);font-size:12px;background:transparent;}"

_BLACKLIST_NOUVEAU_FILE = "/etc/modprobe.d/blacklist-nouveau.conf"
_DRIVER_CACHE_DIR = "/usr/share/pg-gpu-sync/drivers"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _detect_gpu() -> tuple[str, str, str]:
    """Return (gpu_name, gpu_family, optimus) from pg-gpu-sync --show-gpu."""
    try:
        out = subprocess.run(
            ["pg-gpu-sync", "--show-gpu"],
            capture_output=True, text=True, timeout=5
        )
        gpu_name = ""
        gpu_family = ""
        optimus = ""
        for line in out.stdout.strip().split("\n"):
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "gpu":
                gpu_name = val
            elif key == "family":
                gpu_family = val
            elif key == "optimus":
                optimus = val
        return gpu_name, gpu_family, optimus
    except Exception:
        return "", "", ""


def _detect_gpu_lspci() -> str:
    """Return the VGA/3D GPU name from lspci."""
    try:
        out = subprocess.run(
            ["lspci"],
            capture_output=True, text=True, timeout=5
        )
        for line in out.stdout.splitlines():
            if any(k in line for k in ("VGA", "3D controller", "Display controller")):
                parts = line.split(":", 2)
                return parts[-1].strip() if len(parts) >= 2 else line.strip()
    except Exception:
        pass
    return ""


def _detect_renderer() -> str:
    """Return current GL renderer string."""
    try:
        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
        out = subprocess.run(
            ["glxinfo", "-B"],
            capture_output=True, text=True, timeout=5, env=env
        )
        for line in out.stdout.split("\n"):
            if "OpenGL renderer" in line:
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    try:
        with open("/proc/driver/nvidia/version") as f:
            first = f.readline().strip()
            if first:
                return f"NVIDIA (kernel: {first.split('Kernel Module')[1].split()[0].strip() if 'Kernel Module' in first else first[:60]})"
    except Exception:
        pass
    return "Unknown"


def _detect_vulkan() -> str:
    """Return Vulkan driver info or empty string."""
    try:
        out = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True, text=True, timeout=8,
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
        )
        if out.returncode != 0:
            return ""
        lines = []
        for line in out.stdout.splitlines():
            low = line.lower()
            if any(k in low for k in ("gpu", "driver", "apiversion", "api version", "devicename", "device name")):
                lines.append(line.strip())
        return "\n".join(lines[:6]) if lines else out.stdout.strip()[:300]
    except FileNotFoundError:
        return "vulkaninfo: not installed"
    except Exception:
        return ""


def _detect_kwin_compositor() -> str:
    """Return KWin compositor backend and status."""
    try:
        out = subprocess.run(
            ["qdbus", "org.kde.KWin", "/Compositor", "org.kde.kwin.Compositing.compositingType"],
            capture_output=True, text=True, timeout=5
        )
        comp_type = out.stdout.strip()
        # 1=OpenGL, 2=XRender, 0=NoCompositing
        type_map = {"1": "OpenGL", "2": "XRender", "0": "Disabled"}
        comp_name = type_map.get(comp_type, comp_type)
    except Exception:
        comp_name = "?"

    try:
        out2 = subprocess.run(
            ["qdbus", "org.kde.KWin", "/Compositor", "org.kde.kwin.Compositing.active"],
            capture_output=True, text=True, timeout=5
        )
        active = out2.stdout.strip().lower() == "true"
    except Exception:
        active = None

    if comp_name == "?" and active is None:
        return ""

    parts = []
    if comp_name and comp_name != "?":
        parts.append(comp_name)
    if active is not None:
        parts.append("active" if active else "inactive")
    return " — ".join(parts) if parts else ""


def _get_dkms_status() -> list[str]:
    try:
        out = subprocess.run(
            ["dkms", "status"],
            capture_output=True, text=True, timeout=10
        )
        return [l for l in out.stdout.strip().split("\n") if "nvidia" in l.lower() and l.strip()]
    except Exception:
        return []


def _get_nouveau_blacklisted() -> bool:
    return os.path.isfile(_BLACKLIST_NOUVEAU_FILE)


def _get_nvidia_module_loaded() -> list[str]:
    try:
        out = subprocess.run(
            ["lsmod"],
            capture_output=True, text=True, timeout=5
        )
        return [
            l for l in out.stdout.splitlines()
            if l.lower().startswith("nvidia")
        ]
    except Exception:
        return []


def _get_nvidia_smi() -> tuple[bool, str]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,temperature.gpu,memory.used,memory.total,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8
        )
        if out.returncode == 0 and out.stdout.strip():
            lines = []
            for row in out.stdout.strip().splitlines():
                parts = [p.strip() for p in row.split(",")]
                if len(parts) >= 5:
                    name, temp, mem_used, mem_total, power = parts[:5]
                    lines.append(f"{name}  |  {temp}°C  |  VRAM: {mem_used}/{mem_total} MiB  |  {power} W")
                elif len(parts) >= 4:
                    name, temp, mem_used, mem_total = parts[:4]
                    lines.append(f"{name}  |  {temp}°C  |  VRAM: {mem_used}/{mem_total} MiB")
                else:
                    lines.append(row)
            return True, "\n".join(lines)
        out2 = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=8
        )
        if out2.returncode == 0:
            return True, out2.stdout.strip()[:400]
        return True, f"nvidia-smi error: {out2.stderr.strip()[:200]}"
    except FileNotFoundError:
        return False, ""
    except Exception as e:
        return True, f"nvidia-smi error: {e}"


def _get_installed_nvidia_pkgs() -> list[str]:
    try:
        out = subprocess.run(
            ["pacman", "-Qs", "nvidia"],
            capture_output=True, text=True, timeout=5
        )
        pkgs = []
        for line in out.stdout.split("\n"):
            if line.startswith("local/"):
                pkgs.append(line.split()[0].replace("local/", ""))
        return pkgs
    except Exception:
        return []


def _get_cached_drivers() -> list[tuple[str, str]]:
    if not os.path.isdir(_DRIVER_CACHE_DIR):
        return []
    result = []
    try:
        for f in sorted(os.listdir(_DRIVER_CACHE_DIR)):
            if f.endswith(".pkg.tar.zst"):
                try:
                    size = os.path.getsize(os.path.join(_DRIVER_CACHE_DIR, f))
                    result.append((f, _fmt_size(size)))
                except OSError:
                    result.append((f, "?"))
    except Exception:
        pass
    return result


def _has_nvidia_settings() -> bool:
    return shutil.which("nvidia-settings") is not None


# ── Worker ────────────────────────────────────────────────────────────────────

class _GpuInfoWorker(QObject):
    done = pyqtSignal(dict)

    def run(self):
        info: dict = {}

        gpu_name_pg, gpu_family, optimus = _detect_gpu()
        gpu_name_lspci = _detect_gpu_lspci()
        info["gpu_name_pg"] = gpu_name_pg
        info["gpu_name_lspci"] = gpu_name_lspci
        info["gpu_family"] = gpu_family
        info["optimus"] = optimus

        info["renderer"] = _detect_renderer()
        info["vulkan"] = _detect_vulkan()
        info["compositor"] = _detect_kwin_compositor()
        info["installed_pkgs"] = _get_installed_nvidia_pkgs()

        info["dkms_lines"] = _get_dkms_status()
        info["nouveau_blacklisted"] = _get_nouveau_blacklisted()
        info["nvidia_modules"] = _get_nvidia_module_loaded()

        smi_avail, smi_out = _get_nvidia_smi()
        info["smi_available"] = smi_avail
        info["smi_output"] = smi_out

        info["cached_drivers"] = _get_cached_drivers()
        info["has_nvidia_settings"] = _has_nvidia_settings()

        self.done.emit(info)


class _CmdWorker(QObject):
    done = pyqtSignal(bool, str)

    def __init__(self, cmd: list[str], timeout: int = 120):
        super().__init__()
        self._cmd = cmd
        self._timeout = timeout

    def run(self):
        try:
            proc = subprocess.run(
                self._cmd,
                capture_output=True, text=True, timeout=self._timeout
            )
            ok = proc.returncode == 0
            out = (proc.stdout + proc.stderr).strip()
            self.done.emit(ok, out)
        except subprocess.TimeoutExpired:
            self.done.emit(False, "Command timed out.")
        except Exception as e:
            self.done.emit(False, str(e))


# ── Module ────────────────────────────────────────────────────────────────────

class GpuModule(BaseModule):
    module_id = "mod_gpu"
    display_name_key = "module.gpu.name"
    description_key = "module.gpu.desc"
    category = "system"
    icon = "🖥"
    sort_order = 15
    required_binary = "/usr/bin/pg-gpu-sync"
    package_name = "pg-gpu-sync"

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

        self._build_gpu_info_card(layout)
        self._build_graphics_status_card(layout)
        self._build_driver_status_card(layout)
        self._build_driver_actions_card(layout)
        self._build_driver_cache_card(layout)

        layout.addStretch()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    # ── GPU Info card ─────────────────────────────────────────────────────────

    def _build_gpu_info_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._info_title_lbl = QLabel(self.t("gpu.info_title"))
        self._info_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._info_title_lbl)

        self._gpu_info_lbl = QLabel(self.t("gpu.loading"))
        self._gpu_info_lbl.setStyleSheet(_STATUS_MONO)
        self._gpu_info_lbl.setWordWrap(True)
        self._gpu_info_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._gpu_info_lbl)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton(self.t("gpu.refresh"))
        self._refresh_btn.setStyleSheet(_BTN_ACTION)
        self._refresh_btn.clicked.connect(self._refresh_all)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    # ── Graphics Status card (Vulkan + Compositor) ────────────────────────────

    def _build_graphics_status_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._gfx_title_lbl = QLabel(self.t("gpu.gfx_title"))
        self._gfx_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._gfx_title_lbl)

        self._gfx_status_lbl = QLabel(self.t("gpu.loading"))
        self._gfx_status_lbl.setStyleSheet(_STATUS_MONO)
        self._gfx_status_lbl.setWordWrap(True)
        self._gfx_status_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._gfx_status_lbl)

        # nvidia-settings button (hidden if not installed)
        btn_row = QHBoxLayout()
        self._nvsettings_btn = QPushButton(self.t("gpu.btn_nvidia_settings"))
        self._nvsettings_btn.setStyleSheet(_BTN_ACTION)
        self._nvsettings_btn.clicked.connect(self._open_nvidia_settings)
        self._nvsettings_btn.hide()
        btn_row.addWidget(self._nvsettings_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    # ── Driver Status card ────────────────────────────────────────────────────

    def _build_driver_status_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._status_title_lbl = QLabel(self.t("gpu.status_title"))
        self._status_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._status_title_lbl)

        self._driver_status_lbl = QLabel(self.t("gpu.loading"))
        self._driver_status_lbl.setStyleSheet(_STATUS_MONO)
        self._driver_status_lbl.setWordWrap(True)
        self._driver_status_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._driver_status_lbl)

        parent_layout.addWidget(card)

    # ── Driver Actions card ───────────────────────────────────────────────────

    def _build_driver_actions_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self._actions_title_lbl = QLabel(self.t("gpu.actions_title"))
        self._actions_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._actions_title_lbl)

        # Row 1: Reconfigure + nvidia-settings
        row1 = QHBoxLayout()

        self._reconfigure_btn = QPushButton(self.t("gpu.btn_reconfigure"))
        self._reconfigure_btn.setStyleSheet(_BTN_ACTION)
        self._reconfigure_btn.clicked.connect(self._run_reconfigure)
        row1.addWidget(self._reconfigure_btn)

        self._test_btn = QPushButton(self.t("gpu.btn_test"))
        self._test_btn.setStyleSheet(_BTN_ACTION)
        self._test_btn.clicked.connect(self._run_test_mode)
        row1.addWidget(self._test_btn)

        row1.addStretch()
        layout.addLayout(row1)

        # Row 2: Nouveau (danger)
        row2 = QHBoxLayout()

        self._nouveau_btn = QPushButton(self.t("gpu.btn_nouveau"))
        self._nouveau_btn.setStyleSheet(_BTN_DANGER)
        self._nouveau_btn.clicked.connect(self._run_switch_nouveau)
        row2.addWidget(self._nouveau_btn)

        row2.addStretch()
        layout.addLayout(row2)

        # Action output area
        self._action_output_lbl = QLabel("")
        self._action_output_lbl.setStyleSheet(_STATUS_MONO)
        self._action_output_lbl.setWordWrap(True)
        self._action_output_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._action_output_lbl.hide()
        layout.addWidget(self._action_output_lbl)

        # Action result label (ok/err)
        self._action_result_lbl = QLabel("")
        self._action_result_lbl.setObjectName("FieldHint")
        self._action_result_lbl.setWordWrap(True)
        layout.addWidget(self._action_result_lbl)

        # Reboot warning
        self._reboot_warn_lbl = QLabel(self.t("gpu.reboot_warning"))
        self._reboot_warn_lbl.setWordWrap(True)
        self._reboot_warn_lbl.setStyleSheet(_WARN_STYLE)
        layout.addWidget(self._reboot_warn_lbl)

        parent_layout.addWidget(card)

    # ── Driver Cache card ─────────────────────────────────────────────────────

    def _build_driver_cache_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._cache_title_lbl = QLabel(self.t("gpu.cache_title"))
        self._cache_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._cache_title_lbl)

        self._cache_hint_lbl = QLabel(f"{_DRIVER_CACHE_DIR}")
        self._cache_hint_lbl.setStyleSheet(
            "QLabel{color:rgb(100,95,130);font-size:11px;font-family:monospace;"
            "background:transparent;}"
        )
        layout.addWidget(self._cache_hint_lbl)

        self._cache_list_lbl = QLabel(self.t("gpu.loading"))
        self._cache_list_lbl.setStyleSheet(_STATUS_MONO)
        self._cache_list_lbl.setWordWrap(True)
        self._cache_list_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._cache_list_lbl)

        parent_layout.addWidget(card)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_shown(self) -> None:
        self._refresh_all()

    def apply_language(self) -> None:
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._info_title_lbl.setText(self.t("gpu.info_title"))
        self._refresh_btn.setText(self.t("gpu.refresh"))
        self._gfx_title_lbl.setText(self.t("gpu.gfx_title"))
        self._nvsettings_btn.setText(self.t("gpu.btn_nvidia_settings"))
        self._status_title_lbl.setText(self.t("gpu.status_title"))
        self._actions_title_lbl.setText(self.t("gpu.actions_title"))
        self._reconfigure_btn.setText(self.t("gpu.btn_reconfigure"))
        self._nouveau_btn.setText(self.t("gpu.btn_nouveau"))
        self._test_btn.setText(self.t("gpu.btn_test"))
        self._reboot_warn_lbl.setText(self.t("gpu.reboot_warning"))
        self._cache_title_lbl.setText(self.t("gpu.cache_title"))
        self._refresh_all()

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_btn.setEnabled(False)
        self._gpu_info_lbl.setText(self.t("gpu.loading"))
        self._gfx_status_lbl.setText(self.t("gpu.loading"))
        self._driver_status_lbl.setText(self.t("gpu.loading"))
        self._cache_list_lbl.setText(self.t("gpu.loading"))

        worker = _GpuInfoWorker()
        worker.done.connect(self._on_info_ready)
        self._info_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_info_ready(self, info: dict):
        self._refresh_btn.setEnabled(True)
        self._populate_gpu_info(info)
        self._populate_graphics_status(info)
        self._populate_driver_status(info)
        self._populate_driver_cache(info)

        if info.get("has_nvidia_settings"):
            self._nvsettings_btn.show()
        else:
            self._nvsettings_btn.hide()

    # ── Populate GPU info card ────────────────────────────────────────────────

    def _populate_gpu_info(self, info: dict):
        lines = []

        gpu_lspci = info.get("gpu_name_lspci", "")
        gpu_pg = info.get("gpu_name_pg", "")
        gpu_family = info.get("gpu_family", "")
        optimus = info.get("optimus", "")
        renderer = info.get("renderer", "Unknown")
        pkgs = info.get("installed_pkgs", [])

        display_name = gpu_pg or gpu_lspci or self.t("gpu.unknown")
        lines.append(f"GPU      : {display_name}")

        if gpu_lspci and gpu_pg and gpu_lspci != gpu_pg:
            lines.append(f"PCI      : {gpu_lspci}")

        if gpu_family:
            lines.append(f"Family   : {gpu_family}")

        if optimus:
            optimus_display = self.t("gpu.optimus_yes") if optimus.lower() in ("yes", "true", "1") else self.t("gpu.optimus_no")
            lines.append(f"Optimus  : {optimus_display}")

        lines.append("")
        lines.append(f"Renderer : {renderer}")

        if pkgs:
            lines.append("")
            lines.append(f"Packages : {', '.join(pkgs)}")
        else:
            lines.append("")
            lines.append(f"Packages : {self.t('gpu.no_packages')}")

        self._gpu_info_lbl.setText("\n".join(lines))

    # ── Populate graphics status card ─────────────────────────────────────────

    def _populate_graphics_status(self, info: dict):
        lines = []

        # Vulkan
        vulkan = info.get("vulkan", "")
        lines.append(f"Vulkan :")
        if vulkan:
            for vl in vulkan.splitlines():
                lines.append(f"  {vl}")
        else:
            lines.append(f"  {self.t('gpu.vulkan_none')}")

        lines.append("")

        # KWin Compositor
        compositor = info.get("compositor", "")
        lines.append(f"{self.t('gpu.compositor')} :")
        if compositor:
            lines.append(f"  {compositor}")
        else:
            lines.append(f"  {self.t('gpu.compositor_unknown')}")

        lines.append("")

        # nvidia-smi
        smi_avail = info.get("smi_available", False)
        smi_out = info.get("smi_output", "")
        if smi_avail:
            lines.append("nvidia-smi :")
            if smi_out:
                for smi_line in smi_out.splitlines():
                    lines.append(f"  {smi_line}")
            else:
                lines.append(f"  {self.t('gpu.smi_no_output')}")
        else:
            lines.append(f"nvidia-smi : {self.t('gpu.smi_not_found')}")

        self._gfx_status_lbl.setText("\n".join(lines))

    # ── Populate driver status card ───────────────────────────────────────────

    def _populate_driver_status(self, info: dict):
        lines = []

        # DKMS
        dkms_lines = info.get("dkms_lines", [])
        if dkms_lines:
            lines.append(self.t("gpu.dkms_status"))
            for dl in dkms_lines:
                lines.append(f"  {dl}")
        else:
            lines.append(f"{self.t('gpu.dkms_status')} : {self.t('gpu.dkms_none')}")

        lines.append("")

        # Nouveau blacklist
        blacklisted = info.get("nouveau_blacklisted", False)
        bl_str = self.t("gpu.blacklist_yes") if blacklisted else self.t("gpu.blacklist_no")
        lines.append(f"{self.t('gpu.blacklist_label')} : {bl_str}")
        if blacklisted:
            lines.append(f"  {_BLACKLIST_NOUVEAU_FILE}")

        lines.append("")

        # Kernel modules
        nvidia_mods = info.get("nvidia_modules", [])
        if nvidia_mods:
            lines.append(self.t("gpu.kmod_loaded"))
            for m in nvidia_mods:
                lines.append(f"  {m}")
        else:
            lines.append(f"{self.t('gpu.kmod_loaded')} : {self.t('gpu.kmod_none')}")

        self._driver_status_lbl.setText("\n".join(lines))

    # ── Populate cache card ───────────────────────────────────────────────────

    def _populate_driver_cache(self, info: dict):
        cached = info.get("cached_drivers", [])
        if not cached:
            self._cache_list_lbl.setText(self.t("gpu.cache_empty"))
            return
        lines = []
        for fname, size_str in cached:
            lines.append(f"{fname}  [{size_str}]")
        self._cache_list_lbl.setText("\n".join(lines))

    # ── Action helpers ────────────────────────────────────────────────────────

    def _set_buttons_enabled(self, enabled: bool):
        self._reconfigure_btn.setEnabled(enabled)
        self._nouveau_btn.setEnabled(enabled)
        self._test_btn.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)

    def _show_action_running(self, msg: str):
        self._action_result_lbl.setText(msg)
        self._action_result_lbl.setStyleSheet("")
        self._action_output_lbl.setText("...")
        self._action_output_lbl.show()
        self._set_buttons_enabled(False)

    def _on_action_done(self, ok: bool, output: str, refresh: bool = True):
        self._set_buttons_enabled(True)
        style = _RESULT_OK if ok else _RESULT_ERR
        result_text = self.t("gpu.action_ok") if ok else self.t("gpu.action_err")
        self._action_result_lbl.setText(result_text)
        self._action_result_lbl.setStyleSheet(style)
        if output:
            self._action_output_lbl.setText(output[:1200])
            self._action_output_lbl.show()
        else:
            self._action_output_lbl.hide()
        if refresh:
            self._refresh_all()

    def _confirm(self, title: str, msg: str) -> bool:
        return QMessageBox.question(
            self._widget, title, msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes

    # ── Open nvidia-settings ──────────────────────────────────────────────────

    def _open_nvidia_settings(self):
        self.launch_app("nvidia-settings")

    # ── Reconfigure GPU driver ────────────────────────────────────────────────

    def _run_reconfigure(self):
        if not self._confirm(
            self.t("gpu.confirm_title"),
            self.t("gpu.confirm_reconfigure")
        ):
            return

        self._show_action_running(self.t("gpu.running_reconfigure"))

        worker = _CmdWorker(
            ["pkexec", "pg-gpu-sync", "--auto", "--32"],
            timeout=300
        )
        worker.done.connect(lambda ok, out: self._on_action_done(ok, out, refresh=True))
        self._reconfigure_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    # ── Switch to Nouveau ─────────────────────────────────────────────────────

    def _run_switch_nouveau(self):
        if not self._confirm(
            self.t("gpu.confirm_title"),
            self.t("gpu.confirm_nouveau")
        ):
            return

        self._show_action_running(self.t("gpu.running_nouveau"))

        worker = _CmdWorker(
            ["pkexec", "pg-gpu-sync", "--nouveau"],
            timeout=120
        )
        worker.done.connect(lambda ok, out: self._on_action_done(ok, out, refresh=True))
        self._nouveau_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    # ── Test / dry-run ────────────────────────────────────────────────────────

    def _run_test_mode(self):
        self._show_action_running(self.t("gpu.running_test"))

        worker = _CmdWorker(
            ["pkexec", "pg-gpu-sync", "--test", "--32"],
            timeout=60
        )
        worker.done.connect(lambda ok, out: self._on_action_done(ok, out, refresh=False))
        self._test_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()
