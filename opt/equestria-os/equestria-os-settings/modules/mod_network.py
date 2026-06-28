"""Network & Internet module — DNS, TCP tuning, WiFi power-save, speed diagnostics."""

import json
import os
import re
import shutil
import subprocess
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
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
_BTN_INSTALL = (
    "QPushButton{background:rgb(55,40,80);color:rgb(200,170,240);"
    "border-radius:6px;padding:4px 14px;font-size:12px;"
    "border:1px solid rgb(90,65,130);}"
    "QPushButton:hover{background:rgb(75,55,110);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_RESULT_OK = (
    "QLabel{color:rgb(140,220,160);font-size:12px;background:transparent;}"
)
_RESULT_ERR = (
    "QLabel{color:rgb(255,130,130);font-size:12px;background:transparent;}"
)
_STATUS_MONO = (
    "QLabel{color:rgb(170,165,195);font-size:12px;font-family:monospace;"
    "background:rgb(20,18,33);border:1px solid rgb(50,47,72);"
    "border-radius:6px;padding:8px 12px;}"
)
_SYSCTL_VALUE_STYLE = (
    "QLabel{color:rgb(150,145,180);font-size:11px;font-family:monospace;"
    "background:transparent;}"
)
_SYSCTL_VALUE_CHANGED = (
    "QLabel{color:rgb(140,220,160);font-size:11px;font-family:monospace;"
    "background:transparent;}"
)

# ── DNS presets ───────────────────────────────────────────────────────────────

_DNS_PRESETS = [
    ("auto",       "Auto (DHCP)",         [],                                   []),
    ("cloudflare", "Cloudflare",          ["1.1.1.1", "1.0.0.1"],              ["2606:4700:4700::1111", "2606:4700:4700::1001"]),
    ("google",     "Google",              ["8.8.8.8", "8.8.4.4"],              ["2001:4860:4860::8888", "2001:4860:4860::8844"]),
    ("quad9",      "Quad9",               ["9.9.9.9", "149.112.112.112"],      ["2620:fe::fe", "2620:fe::9"]),
    ("opendns",    "OpenDNS",             ["208.67.222.222", "208.67.220.220"],["2620:119:35::35", "2620:119:53::53"]),
    ("adguard",    "AdGuard (ad-block)",  ["94.140.14.14", "94.140.15.15"],    ["2a10:50c0::ad1:ff", "2a10:50c0::ad2:ff"]),
    ("custom",     "Custom",              [],                                   []),
]

# All known DNS IPs mapped back to preset key
_DNS_IP_TO_PRESET: dict[str, str] = {}
for _key, _, _v4, _v6 in _DNS_PRESETS:
    for _ip in _v4 + _v6:
        _DNS_IP_TO_PRESET[_ip] = _key

# ── sysctl TCP/network optimizations (grouped) ──────────────────────────────

_SYSCTL_GROUPS = [
    {
        "id": "bbr",
        "label_key": "network.tcp_opt_bbr",
        "desc_key": "network.tcp_opt_bbr_desc",
        "params": {
            "net.core.default_qdisc": "fq",
            "net.ipv4.tcp_congestion_control": "bbr",
        },
    },
    {
        "id": "buffers",
        "label_key": "network.tcp_opt_buffers",
        "desc_key": "network.tcp_opt_buffers_desc",
        "params": {
            "net.core.rmem_max": "16777216",
            "net.core.wmem_max": "16777216",
            "net.ipv4.tcp_rmem": "4096 131072 16777216",
            "net.ipv4.tcp_wmem": "4096 16384 16777216",
        },
    },
    {
        "id": "keepalive",
        "label_key": "network.tcp_opt_keepalive",
        "desc_key": "network.tcp_opt_keepalive_desc",
        "params": {
            "net.ipv4.tcp_keepalive_time": "60",
            "net.ipv4.tcp_keepalive_intvl": "10",
            "net.ipv4.tcp_keepalive_probes": "6",
        },
    },
    {
        "id": "tweaks",
        "label_key": "network.tcp_opt_tweaks",
        "desc_key": "network.tcp_opt_tweaks_desc",
        "params": {
            "net.ipv4.tcp_fastopen": "3",
            "net.ipv4.tcp_mtu_probing": "1",
            "net.ipv4.tcp_slow_start_after_idle": "0",
            "net.core.netdev_max_backlog": "16384",
        },
    },
]

_SYSCTL_FILE = "/etc/sysctl.d/99-equestria-network.conf"
_WIFI_POWERSAVE_FILE = "/etc/NetworkManager/conf.d/99-equestria-wifi-powersave.conf"
_WIFI_DRIVER_FILE = "/etc/modprobe.d/99-equestria-wifi.conf"

# ── WiFi driver parameter presets ─────────────────────────────────────────────
# Each driver has known parameters that fix speed drops / disconnects on Linux.
# Windows drivers enable these by default — Linux doesn't.

_WIFI_DRIVER_PARAMS = {
    "iwlwifi": {
        "label": "Intel WiFi (iwlwifi)",
        "params": {
            "power_save": ("0", "network.drv_p_iwlwifi_ps"),
            "uapsd_disable": ("1", "network.drv_p_iwlwifi_uapsd"),
            "11n_disable": ("8", "network.drv_p_iwlwifi_11n"),
        },
    },
    "iwlmvm": {
        "label": "Intel WiFi (iwlmvm)",
        "params": {
            "power_scheme": ("1", "network.drv_p_iwlmvm_scheme"),
        },
    },
    "rtw88_pci": {
        "label": "Realtek WiFi (rtw88)",
        "params": {
            "disable_lps_deep": ("Y", "network.drv_p_rtw88_lps"),
        },
    },
    "rtw89_pci": {
        "label": "Realtek WiFi (rtw89)",
        "params": {
            "disable_ps_mode": ("Y", "network.drv_p_rtw89_ps"),
        },
    },
    "ath9k": {
        "label": "Atheros WiFi (ath9k)",
        "params": {
            "ps_enable": ("0", "network.drv_p_ath9k_ps"),
            "nohwcrypt": ("1", "network.drv_p_ath9k_hwcrypt"),
        },
    },
    "ath10k_pci": {
        "label": "Qualcomm WiFi (ath10k)",
        "params": {},
    },
    "ath11k_pci": {
        "label": "Qualcomm WiFi (ath11k)",
        "params": {},
    },
    "mt7921e": {
        "label": "MediaTek WiFi (mt7921)",
        "params": {},
    },
    "brcmfmac": {
        "label": "Broadcom WiFi (brcmfmac)",
        "params": {
            "roamoff": ("1", "network.drv_p_brcm_roam"),
        },
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_wifi_interfaces() -> list[str]:
    """Detect WiFi interfaces via /sys/class/net/*/wireless (no external tools)."""
    wifi = []
    try:
        for iface in os.listdir("/sys/class/net"):
            if os.path.isdir(f"/sys/class/net/{iface}/wireless"):
                wifi.append(iface)
    except Exception:
        pass
    return wifi


def _get_wifi_powersave(iface: str) -> bool | None:
    """Check power-save status for a specific interface. Returns None if unknown."""
    try:
        r = subprocess.run(
            ["iw", "dev", iface, "get", "power_save"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            return "on" in r.stdout.lower()
    except Exception:
        pass
    # Fallback: try iwconfig
    try:
        r = subprocess.run(
            ["iwconfig", iface],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if "Power Management" in line:
                return "on" in line.lower()
    except Exception:
        pass
    return None


def _read_sysctl(key: str) -> str:
    """Read a single sysctl value."""
    try:
        r = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "?"


def _detect_wifi_driver(iface: str) -> str:
    """Get the kernel driver name for a WiFi interface."""
    try:
        link = os.path.realpath(f"/sys/class/net/{iface}/device/driver")
        return os.path.basename(link)
    except Exception:
        pass
    return ""


def _get_driver_current_params(driver: str) -> dict[str, str]:
    """Read current module parameters from /sys/module/<driver>/parameters/."""
    params = {}
    param_dir = f"/sys/module/{driver}/parameters"
    if not os.path.isdir(param_dir):
        return params
    try:
        for name in os.listdir(param_dir):
            fpath = os.path.join(param_dir, name)
            if os.path.isfile(fpath):
                try:
                    with open(fpath) as f:
                        params[name] = f.read().strip()
                except (PermissionError, OSError):
                    params[name] = "?"
    except Exception:
        pass
    return params


def _get_current_dns_ips() -> list[str]:
    """Get current DNS IPs from nmcli or resolvectl."""
    ips = []
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "IP4.DNS", "device", "show"],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if line.startswith("IP4.DNS"):
                ip = line.split(":", 1)[-1].strip()
                if ip:
                    ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            r = subprocess.run(
                ["resolvectl", "dns"],
                capture_output=True, text=True, timeout=5
            )
            for part in r.stdout.split():
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', part) or ":" in part:
                    ips.append(part)
        except Exception:
            pass
    return ips


# ── Workers ───────────────────────────────────────────────────────────────────

class _NetInfoWorker(QObject):
    done = pyqtSignal(dict)

    def run(self):
        info = {}
        try:
            r = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE,STATE", "con", "show", "--active"],
                capture_output=True, text=True, timeout=5
            )
            info["connections"] = r.stdout.strip()
        except Exception:
            info["connections"] = ""

        # DNS
        info["dns_ips"] = _get_current_dns_ips()
        try:
            r = subprocess.run(
                ["resolvectl", "dns"],
                capture_output=True, text=True, timeout=5
            )
            info["dns_display"] = r.stdout.strip()
        except Exception:
            info["dns_display"] = ", ".join(info["dns_ips"]) if info["dns_ips"] else ""

        # WiFi
        wifi_ifaces = _detect_wifi_interfaces()
        info["wifi_interfaces"] = wifi_ifaces
        if wifi_ifaces:
            ps = _get_wifi_powersave(wifi_ifaces[0])
            if ps is not None:
                info["wifi_powersave"] = ps
        info["wifi_conf_exists"] = os.path.exists(_WIFI_POWERSAVE_FILE)

        # WiFi driver info
        wifi_drivers = {}
        for iface in wifi_ifaces:
            drv = _detect_wifi_driver(iface)
            if drv:
                wifi_drivers[iface] = drv
        info["wifi_drivers"] = wifi_drivers

        # Current driver module params
        driver_params = {}
        seen_drivers = set()
        for iface, drv in wifi_drivers.items():
            if drv not in seen_drivers:
                seen_drivers.add(drv)
                driver_params[drv] = _get_driver_current_params(drv)
                # Also check companion driver (e.g. iwlmvm for iwlwifi)
                if drv == "iwlwifi":
                    driver_params["iwlmvm"] = _get_driver_current_params("iwlmvm")
        info["driver_params"] = driver_params
        info["driver_conf_exists"] = os.path.exists(_WIFI_DRIVER_FILE)

        # Read ALL sysctl current values
        sysctl_current = {}
        for group in _SYSCTL_GROUPS:
            for key in group["params"]:
                sysctl_current[key] = _read_sysctl(key)
        info["sysctl_current"] = sysctl_current
        info["sysctl_applied"] = os.path.exists(_SYSCTL_FILE)

        # TCP congestion control
        info["tcp_cc"] = sysctl_current.get("net.ipv4.tcp_congestion_control", "?")

        # IPv6
        try:
            r = subprocess.run(
                ["sysctl", "-n", "net.ipv6.conf.all.disable_ipv6"],
                capture_output=True, text=True, timeout=3
            )
            info["ipv6_disabled"] = r.stdout.strip() == "1"
        except Exception:
            info["ipv6_disabled"] = False

        # Interfaces
        try:
            r = subprocess.run(
                ["ip", "-brief", "addr"],
                capture_output=True, text=True, timeout=5
            )
            info["interfaces"] = r.stdout.strip()
        except Exception:
            info["interfaces"] = ""

        self.done.emit(info)


class _SpeedTestWorker(QObject):
    progress = pyqtSignal(str)
    done = pyqtSignal(str)

    def run(self):
        # Try speedtest-cli first, then curl-based fallback
        if shutil.which("speedtest-cli"):
            try:
                self.progress.emit("speedtest-cli...")
                r = subprocess.run(
                    ["speedtest-cli", "--simple"],
                    capture_output=True, text=True, timeout=60
                )
                if r.returncode == 0 and r.stdout.strip():
                    self.done.emit(r.stdout.strip())
                    return
            except Exception:
                pass

        if shutil.which("speedtest"):
            try:
                self.progress.emit("speedtest (Ookla)...")
                r = subprocess.run(
                    ["speedtest", "--simple"],
                    capture_output=True, text=True, timeout=60
                )
                if r.returncode == 0 and r.stdout.strip():
                    self.done.emit(r.stdout.strip())
                    return
            except Exception:
                pass

        # curl-based fallback — test download speed
        try:
            self.progress.emit("download test...")
            r = subprocess.run(
                ["curl", "-so", "/dev/null", "-w",
                 "%{speed_download} %{time_total}",
                 "https://speed.cloudflare.com/__down?bytes=25000000"],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split()
                if len(parts) >= 2:
                    bps = float(parts[0])
                    time_s = float(parts[1])
                    mbps = bps * 8 / 1_000_000
                    self.done.emit(
                        f"Download: {mbps:.1f} Mbit/s  ({bps / 1_000_000:.1f} MB/s)\n"
                        f"Time: {time_s:.1f}s  |  25 MB test file (Cloudflare)"
                    )
                    return
        except Exception:
            pass

        # curl upload test
        try:
            self.progress.emit("upload test...")
            r = subprocess.run(
                ["curl", "-so", "/dev/null", "-w", "%{speed_upload} %{time_total}",
                 "-X", "POST",
                 "--data-binary", "@/dev/zero",
                 "--max-time", "10",
                 "https://speed.cloudflare.com/__up"],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split()
                if len(parts) >= 2:
                    bps = float(parts[0])
                    mbps = bps * 8 / 1_000_000
                    self.done.emit(f"Upload: {mbps:.1f} Mbit/s  ({bps / 1_000_000:.1f} MB/s)")
                    return
        except Exception:
            pass

        self.done.emit("ERROR: no speed-test tool found")


# ── Module ────────────────────────────────────────────────────────────────────

class NetworkModule(BaseModule):
    module_id = "mod_network"
    display_name_key = "module.network.name"
    description_key = "module.network.desc"
    category = "system"
    icon = "🌐"
    sort_order = 15

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

        # Title
        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        self._build_status_card(layout)
        self._build_wifi_driver_card(layout)
        self._build_dns_card(layout)
        self._build_tcp_card(layout)
        self._build_wifi_card(layout)
        self._build_ipv6_card(layout)
        self._build_speedtest_card(layout)

        layout.addStretch()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    # ── Status card ───────────────────────────────────────────────────────────

    def _build_status_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._status_title_lbl = QLabel(self.t("network.status_title"))
        self._status_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._status_title_lbl)

        self._net_status_lbl = QLabel("...")
        self._net_status_lbl.setStyleSheet(_STATUS_MONO)
        self._net_status_lbl.setWordWrap(True)
        self._net_status_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._net_status_lbl)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton(self.t("network.refresh"))
        self._refresh_btn.setObjectName("ActionBtn")
        self._refresh_btn.setStyleSheet(_BTN_ACTION)
        self._refresh_btn.clicked.connect(self._refresh_status)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    # ── DNS card ──────────────────────────────────────────────────────────────

    def _build_dns_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self._dns_title_lbl = QLabel(self.t("network.dns_title"))
        self._dns_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._dns_title_lbl)

        self._dns_hint_lbl = QLabel(self.t("network.dns_hint"))
        self._dns_hint_lbl.setObjectName("FieldHint")
        self._dns_hint_lbl.setWordWrap(True)
        layout.addWidget(self._dns_hint_lbl)

        # Current DNS display
        self._dns_current_lbl = QLabel("")
        self._dns_current_lbl.setStyleSheet(_STATUS_MONO)
        self._dns_current_lbl.setWordWrap(True)
        self._dns_current_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._dns_current_lbl)

        # Preset selector
        preset_row = QHBoxLayout()
        self._dns_preset_lbl = QLabel(self.t("network.dns_preset"))
        self._dns_preset_lbl.setObjectName("FieldLabel")
        preset_row.addWidget(self._dns_preset_lbl)

        self._dns_combo = QComboBox()
        for key, label, _, _ in _DNS_PRESETS:
            self._dns_combo.addItem(label, key)
        self._dns_combo.currentIndexChanged.connect(self._on_dns_preset_changed)
        preset_row.addWidget(self._dns_combo)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        # Custom DNS fields
        self._dns_custom_frame = QFrame()
        custom_layout = QVBoxLayout(self._dns_custom_frame)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(6)

        custom_row1 = QHBoxLayout()
        self._dns_primary_lbl = QLabel(self.t("network.dns_primary"))
        self._dns_primary_lbl.setObjectName("FieldLabel")
        custom_row1.addWidget(self._dns_primary_lbl)
        self._dns_primary = QLineEdit()
        self._dns_primary.setPlaceholderText("1.1.1.1")
        self._dns_primary.setMaximumWidth(200)
        custom_row1.addWidget(self._dns_primary)
        custom_row1.addStretch()
        custom_layout.addLayout(custom_row1)

        custom_row2 = QHBoxLayout()
        self._dns_secondary_lbl = QLabel(self.t("network.dns_secondary"))
        self._dns_secondary_lbl.setObjectName("FieldLabel")
        custom_row2.addWidget(self._dns_secondary_lbl)
        self._dns_secondary = QLineEdit()
        self._dns_secondary.setPlaceholderText("1.0.0.1")
        self._dns_secondary.setMaximumWidth(200)
        custom_row2.addWidget(self._dns_secondary)
        custom_row2.addStretch()
        custom_layout.addLayout(custom_row2)

        self._dns_custom_frame.hide()
        layout.addWidget(self._dns_custom_frame)

        # Apply button
        btn_row = QHBoxLayout()
        self._dns_apply_btn = QPushButton(self.t("network.dns_apply"))
        self._dns_apply_btn.setObjectName("ActionBtn")
        self._dns_apply_btn.setStyleSheet(_BTN_ACTION)
        self._dns_apply_btn.clicked.connect(self._apply_dns)
        btn_row.addWidget(self._dns_apply_btn)

        self._dns_status_lbl = QLabel("")
        self._dns_status_lbl.setObjectName("FieldHint")
        btn_row.addWidget(self._dns_status_lbl)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    def _on_dns_preset_changed(self, idx):
        key = self._dns_combo.itemData(idx)
        if key == "custom":
            self._dns_custom_frame.show()
        else:
            self._dns_custom_frame.hide()

    def _sync_dns_combo(self, dns_ips: list[str]):
        """Set DNS combo to match the currently active DNS."""
        matched_preset = None
        for ip in dns_ips:
            p = _DNS_IP_TO_PRESET.get(ip)
            if p:
                if matched_preset is None:
                    matched_preset = p
                elif p != matched_preset:
                    matched_preset = None
                    break

        self._dns_combo.blockSignals(True)
        if matched_preset:
            for i in range(self._dns_combo.count()):
                if self._dns_combo.itemData(i) == matched_preset:
                    self._dns_combo.setCurrentIndex(i)
                    self._dns_custom_frame.hide()
                    break
        else:
            # No preset matched — check if it looks like auto/DHCP or custom
            if not dns_ips:
                self._dns_combo.setCurrentIndex(0)  # auto
                self._dns_custom_frame.hide()
            else:
                # Set to custom, fill fields
                for i in range(self._dns_combo.count()):
                    if self._dns_combo.itemData(i) == "custom":
                        self._dns_combo.setCurrentIndex(i)
                        break
                self._dns_primary.setText(dns_ips[0] if dns_ips else "")
                self._dns_secondary.setText(dns_ips[1] if len(dns_ips) > 1 else "")
                self._dns_custom_frame.show()
        self._dns_combo.blockSignals(False)

    # ── WiFi Driver card ─────────────────────────────────────────────────────

    def _build_wifi_driver_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        self._drv_card = card
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._drv_title_lbl = QLabel(self.t("network.drv_title"))
        self._drv_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._drv_title_lbl)

        self._drv_hint_lbl = QLabel(self.t("network.drv_hint"))
        self._drv_hint_lbl.setObjectName("FieldHint")
        self._drv_hint_lbl.setWordWrap(True)
        layout.addWidget(self._drv_hint_lbl)

        # Detected driver info
        self._drv_info_lbl = QLabel("")
        self._drv_info_lbl.setStyleSheet(_STATUS_MONO)
        self._drv_info_lbl.setWordWrap(True)
        self._drv_info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._drv_info_lbl)

        # Checkboxes for driver params — built dynamically
        self._drv_params_frame = QFrame()
        self._drv_params_layout = QVBoxLayout(self._drv_params_frame)
        self._drv_params_layout.setContentsMargins(0, 0, 0, 0)
        self._drv_params_layout.setSpacing(4)
        layout.addWidget(self._drv_params_frame)
        self._drv_checkboxes: list[tuple[QCheckBox, str, str, str]] = []  # (cb, driver, param, value)

        # File path
        self._drv_file_lbl = QLabel("")
        self._drv_file_lbl.setStyleSheet(
            "QLabel{color:rgb(100,95,130);font-size:11px;font-family:monospace;background:transparent;}"
        )
        layout.addWidget(self._drv_file_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        self._drv_apply_btn = QPushButton(self.t("network.drv_apply"))
        self._drv_apply_btn.setObjectName("ActionBtn")
        self._drv_apply_btn.setStyleSheet(_BTN_ACTION)
        self._drv_apply_btn.clicked.connect(self._apply_driver_params)
        btn_row.addWidget(self._drv_apply_btn)

        self._drv_remove_btn = QPushButton(self.t("network.drv_remove"))
        self._drv_remove_btn.setObjectName("ActionBtn")
        self._drv_remove_btn.setStyleSheet(_BTN_ACTION)
        self._drv_remove_btn.clicked.connect(self._remove_driver_params)
        btn_row.addWidget(self._drv_remove_btn)

        self._drv_reload_btn = QPushButton(self.t("network.drv_reload"))
        self._drv_reload_btn.setObjectName("ActionBtn")
        self._drv_reload_btn.setStyleSheet(_BTN_ACTION)
        self._drv_reload_btn.clicked.connect(self._reload_wifi_module)
        btn_row.addWidget(self._drv_reload_btn)

        self._drv_reconnect_btn = QPushButton(self.t("network.drv_reconnect"))
        self._drv_reconnect_btn.setObjectName("ActionBtn")
        self._drv_reconnect_btn.setStyleSheet(_BTN_ACTION)
        self._drv_reconnect_btn.clicked.connect(self._reconnect_wifi)
        btn_row.addWidget(self._drv_reconnect_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._drv_result_lbl = QLabel("")
        self._drv_result_lbl.setObjectName("FieldHint")
        layout.addWidget(self._drv_result_lbl)

        # Reboot hint
        self._drv_reboot_lbl = QLabel(self.t("network.drv_reboot_hint"))
        self._drv_reboot_lbl.setObjectName("FieldHint")
        self._drv_reboot_lbl.setWordWrap(True)
        self._drv_reboot_lbl.setStyleSheet(
            "QLabel{color:rgb(180,160,100);font-size:12px;background:transparent;}"
        )
        layout.addWidget(self._drv_reboot_lbl)

        parent_layout.addWidget(card)

    def _update_driver_ui(self, info: dict):
        """Rebuild driver card based on detected WiFi driver."""
        wifi_drivers: dict = info.get("wifi_drivers", {})
        driver_params: dict = info.get("driver_params", {})
        conf_exists = info.get("driver_conf_exists", False)

        if not wifi_drivers:
            self._drv_info_lbl.setText(self.t("network.wifi_not_detected"))
            self._drv_file_lbl.setText("")
            self._drv_apply_btn.setEnabled(False)
            self._drv_reload_btn.setEnabled(False)
            self._drv_reconnect_btn.setEnabled(False)
            self._drv_reboot_lbl.hide()
            # Clear checkboxes
            while self._drv_params_layout.count():
                item = self._drv_params_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._drv_checkboxes.clear()
            return

        self._drv_apply_btn.setEnabled(True)
        self._drv_reload_btn.setEnabled(True)
        self._drv_reconnect_btn.setEnabled(True)
        self._drv_reboot_lbl.show()

        # Build info text — show current params vs recommended
        info_lines = []
        all_optimal = True
        for iface, drv in wifi_drivers.items():
            preset = _WIFI_DRIVER_PARAMS.get(drv, {})
            label = preset.get("label", drv) if preset else drv
            info_lines.append(f"{iface}: {label}")

            current = driver_params.get(drv, {})
            preset_params = preset.get("params", {}) if preset else {}
            for pname, (pval, pdesc_key) in preset_params.items():
                cur = current.get(pname, "?")
                if str(cur) == str(pval):
                    info_lines.append(f"  {pname} = {cur}  ✓")
                else:
                    info_lines.append(f"  {pname} = {cur}  →  {pval}")
                    all_optimal = False

            # iwlmvm companion
            if drv == "iwlwifi" and "iwlmvm" in driver_params:
                mvm_preset = _WIFI_DRIVER_PARAMS.get("iwlmvm", {}).get("params", {})
                mvm_current = driver_params.get("iwlmvm", {})
                for pname, (pval, pdesc_key) in mvm_preset.items():
                    cur = mvm_current.get(pname, "?")
                    if str(cur) == str(pval):
                        info_lines.append(f"  {pname} = {cur}  ✓  (iwlmvm)")
                    else:
                        info_lines.append(f"  {pname} = {cur}  →  {pval}  (iwlmvm)")
                        all_optimal = False

        if all_optimal:
            info_lines.append("")
            info_lines.append(f"✓ {self.t('network.drv_all_optimal')}")

        self._drv_info_lbl.setText("\n".join(info_lines))

        # File path
        if conf_exists:
            self._drv_file_lbl.setText(f"{_WIFI_DRIVER_FILE}  [{self.t('network.wifi_conf_applied')}]")
        else:
            self._drv_file_lbl.setText(f"{_WIFI_DRIVER_FILE}  [{self.t('network.file_not_exists')}]")

        # Rebuild checkboxes with translated descriptions
        while self._drv_params_layout.count():
            item = self._drv_params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._drv_checkboxes.clear()

        seen_drivers = set()
        for iface, drv in wifi_drivers.items():
            drivers_to_check = [drv]
            if drv == "iwlwifi":
                drivers_to_check.append("iwlmvm")

            for d in drivers_to_check:
                if d in seen_drivers:
                    continue
                seen_drivers.add(d)

                preset = _WIFI_DRIVER_PARAMS.get(d)
                if not preset or not preset.get("params"):
                    continue

                current = driver_params.get(d, {})
                for pname, (pval, pdesc_key) in preset["params"].items():
                    cur = current.get(pname, "?")
                    already_set = str(cur) == str(pval)
                    cb = QCheckBox(f"{d}.{pname} = {pval}")
                    cb.setChecked(True)
                    translated_desc = self.t(pdesc_key)
                    cb.setToolTip(translated_desc)
                    self._drv_params_layout.addWidget(cb)

                    status = "✓" if already_set else f"→ {pval}"
                    desc_lbl = QLabel(
                        f"  {translated_desc}\n"
                        f"  [{self.t('network.drv_current')}: {cur} {status}]"
                    )
                    desc_lbl.setObjectName("FieldHint")
                    desc_lbl.setWordWrap(True)
                    desc_lbl.setContentsMargins(26, 0, 0, 4)
                    if already_set:
                        desc_lbl.setStyleSheet(_RESULT_OK)
                    self._drv_params_layout.addWidget(desc_lbl)

                    self._drv_checkboxes.append((cb, d, pname, pval))

    def _apply_driver_params(self):
        """Write selected driver params to /etc/modprobe.d/."""
        # Collect checked params grouped by driver
        by_driver: dict[str, dict[str, str]] = {}
        for cb, drv, pname, pval in self._drv_checkboxes:
            if cb.isChecked():
                by_driver.setdefault(drv, {})[pname] = pval

        if not by_driver:
            self._drv_result_lbl.setText(self.t("network.drv_nothing_selected"))
            self._drv_result_lbl.setStyleSheet(_RESULT_ERR)
            return

        lines = [
            "# Equestria OS — WiFi driver performance tuning",
            "# Managed by equestria-os-settings. Reboot or reload module to apply.",
            "",
        ]
        for drv, params in by_driver.items():
            opts = " ".join(f"{k}={v}" for k, v in params.items())
            lines.append(f"options {drv} {opts}")

        content = "\n".join(lines) + "\n"

        self._drv_apply_btn.setEnabled(False)
        self._drv_result_lbl.setText(self.t("network.applying"))
        self._drv_result_lbl.setStyleSheet("")

        def do_apply():
            try:
                proc = subprocess.run(
                    ["pkexec", "tee", _WIFI_DRIVER_FILE],
                    input=content, capture_output=True, text=True, timeout=30
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                return True, self.t("network.drv_applied")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_apply()
            self._drv_apply_btn.setEnabled(True)
            self._drv_result_lbl.setText(msg)
            self._drv_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    def _remove_driver_params(self):
        self._drv_remove_btn.setEnabled(False)
        self._drv_result_lbl.setText(self.t("network.applying"))

        def do_remove():
            try:
                proc = subprocess.run(
                    ["pkexec", "rm", "-f", _WIFI_DRIVER_FILE],
                    capture_output=True, text=True, timeout=15
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                return True, self.t("network.drv_removed")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_remove()
            self._drv_remove_btn.setEnabled(True)
            self._drv_result_lbl.setText(msg)
            self._drv_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    def _reconnect_wifi(self):
        """Quick reconnect — deactivate and reactivate WiFi connections."""
        self._drv_reconnect_btn.setEnabled(False)
        self._drv_result_lbl.setText(self.t("network.drv_reconnecting"))
        self._drv_result_lbl.setStyleSheet("")

        def do_reconnect():
            try:
                # Get active WiFi connections
                r = subprocess.run(
                    ["nmcli", "-t", "-f", "NAME,TYPE", "con", "show", "--active"],
                    capture_output=True, text=True, timeout=5
                )
                wifi_cons = []
                for line in r.stdout.strip().splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2 and "wireless" in parts[1]:
                        wifi_cons.append(parts[0])

                if not wifi_cons:
                    return False, self.t("network.drv_no_wifi_conn")

                import time
                for conn in wifi_cons:
                    subprocess.run(
                        ["nmcli", "con", "down", conn],
                        capture_output=True, timeout=10
                    )
                time.sleep(1)
                for conn in wifi_cons:
                    subprocess.run(
                        ["nmcli", "con", "up", conn],
                        capture_output=True, timeout=15
                    )

                return True, self.t("network.drv_reconnected")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_reconnect()
            self._drv_reconnect_btn.setEnabled(True)
            self._drv_result_lbl.setText(msg)
            self._drv_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                import time
                time.sleep(2)
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    def _reload_wifi_module(self):
        """Reload WiFi kernel module so modprobe.d changes take effect immediately."""
        self._drv_reload_btn.setEnabled(False)
        self._drv_result_lbl.setText(self.t("network.drv_reloading"))
        self._drv_result_lbl.setStyleSheet("")

        def do_reload():
            try:
                wifi_ifaces = _detect_wifi_interfaces()
                if not wifi_ifaces:
                    return False, self.t("network.wifi_not_detected")

                drivers = []
                for iface in wifi_ifaces:
                    drv = _detect_wifi_driver(iface)
                    if drv and drv not in drivers:
                        drivers.append(drv)

                if not drivers:
                    return False, self.t("network.wifi_not_detected")

                for drv in drivers:
                    # iwlwifi needs companion modules unloaded first
                    if drv == "iwlwifi":
                        script = "modprobe -r iwlmvm 2>/dev/null; modprobe -r iwlwifi && modprobe iwlwifi"
                    else:
                        script = f"modprobe -r {drv} && modprobe {drv}"

                    proc = subprocess.run(
                        ["pkexec", "bash", "-c", script],
                        capture_output=True, text=True, timeout=30
                    )
                    if proc.returncode != 0:
                        return False, proc.stderr.strip() or self.t("network.drv_reload_fail")

                return True, self.t("network.drv_reloaded")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_reload()
            self._drv_reload_btn.setEnabled(True)
            self._drv_result_lbl.setText(msg)
            self._drv_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                import time
                time.sleep(4)
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    # ── TCP card ──────────────────────────────────────────────────────────────

    def _build_tcp_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._tcp_title_lbl = QLabel(self.t("network.tcp_title"))
        self._tcp_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._tcp_title_lbl)

        self._tcp_hint_lbl = QLabel(self.t("network.tcp_hint"))
        self._tcp_hint_lbl.setObjectName("FieldHint")
        self._tcp_hint_lbl.setWordWrap(True)
        layout.addWidget(self._tcp_hint_lbl)

        # Status
        self._tcp_status_lbl = QLabel("")
        self._tcp_status_lbl.setObjectName("FieldHint")
        layout.addWidget(self._tcp_status_lbl)

        # File path hint
        self._tcp_file_lbl = QLabel(f"{_SYSCTL_FILE}")
        self._tcp_file_lbl.setStyleSheet(
            "QLabel{color:rgb(100,95,130);font-size:11px;font-family:monospace;background:transparent;}"
        )
        layout.addWidget(self._tcp_file_lbl)

        # Individual group checkboxes + value grid
        self._tcp_checkboxes: list[tuple[QCheckBox, dict, QLabel]] = []
        for group in _SYSCTL_GROUPS:
            cb = QCheckBox(self.t(group["label_key"]))
            cb.setChecked(True)
            cb.setToolTip(self.t(group["desc_key"]))
            layout.addWidget(cb)

            desc_lbl = QLabel(self.t(group["desc_key"]))
            desc_lbl.setObjectName("FieldHint")
            desc_lbl.setWordWrap(True)
            desc_lbl.setContentsMargins(26, 0, 0, 0)
            layout.addWidget(desc_lbl)

            # Current/proposed values
            values_lbl = QLabel("")
            values_lbl.setStyleSheet(_SYSCTL_VALUE_STYLE)
            values_lbl.setWordWrap(True)
            values_lbl.setContentsMargins(26, 0, 0, 4)
            layout.addWidget(values_lbl)

            self._tcp_checkboxes.append((cb, group, values_lbl))

        # Buttons
        btn_row = QHBoxLayout()
        self._tcp_apply_btn = QPushButton(self.t("network.tcp_apply"))
        self._tcp_apply_btn.setObjectName("ActionBtn")
        self._tcp_apply_btn.setStyleSheet(_BTN_ACTION)
        self._tcp_apply_btn.clicked.connect(self._apply_tcp)
        btn_row.addWidget(self._tcp_apply_btn)

        self._tcp_remove_btn = QPushButton(self.t("network.tcp_remove"))
        self._tcp_remove_btn.setObjectName("ActionBtn")
        self._tcp_remove_btn.setStyleSheet(_BTN_ACTION)
        self._tcp_remove_btn.clicked.connect(self._remove_tcp)
        btn_row.addWidget(self._tcp_remove_btn)

        self._tcp_result_lbl = QLabel("")
        self._tcp_result_lbl.setObjectName("FieldHint")
        btn_row.addWidget(self._tcp_result_lbl)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    def _update_tcp_values(self, sysctl_current: dict):
        """Update the current/proposed value labels for each TCP group."""
        all_match = True
        for cb, group, values_lbl in self._tcp_checkboxes:
            lines = []
            group_match = True
            for key, proposed in group["params"].items():
                current = sysctl_current.get(key, "?")
                if current == proposed:
                    lines.append(f"  {key} = {current}")
                else:
                    lines.append(f"  {key} = {current}  →  {proposed}")
                    group_match = False
            values_lbl.setText("\n".join(lines))
            if group_match:
                values_lbl.setStyleSheet(_SYSCTL_VALUE_CHANGED)
                cb.setChecked(True)
            else:
                values_lbl.setStyleSheet(_SYSCTL_VALUE_STYLE)
                cb.setChecked(True)
                all_match = False
        return all_match

    # ── WiFi card ─────────────────────────────────────────────────────────────

    def _build_wifi_card(self, parent_layout):
        self._wifi_card = QFrame()
        self._wifi_card.setObjectName("InlineCard")
        layout = QVBoxLayout(self._wifi_card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._wifi_title_lbl = QLabel(self.t("network.wifi_title"))
        self._wifi_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._wifi_title_lbl)

        self._wifi_hint_lbl = QLabel(self.t("network.wifi_hint"))
        self._wifi_hint_lbl.setObjectName("FieldHint")
        self._wifi_hint_lbl.setWordWrap(True)
        layout.addWidget(self._wifi_hint_lbl)

        self._wifi_status_lbl = QLabel("")
        self._wifi_status_lbl.setObjectName("FieldHint")
        layout.addWidget(self._wifi_status_lbl)

        # Config file info
        self._wifi_conf_lbl = QLabel("")
        self._wifi_conf_lbl.setStyleSheet(
            "QLabel{color:rgb(100,95,130);font-size:11px;font-family:monospace;background:transparent;}"
        )
        layout.addWidget(self._wifi_conf_lbl)

        self._wifi_btn_row = QHBoxLayout()
        self._wifi_disable_btn = QPushButton(self.t("network.wifi_disable_powersave"))
        self._wifi_disable_btn.setObjectName("ActionBtn")
        self._wifi_disable_btn.setStyleSheet(_BTN_ACTION)
        self._wifi_disable_btn.clicked.connect(self._disable_wifi_powersave)
        self._wifi_btn_row.addWidget(self._wifi_disable_btn)

        self._wifi_enable_btn = QPushButton(self.t("network.wifi_enable_powersave"))
        self._wifi_enable_btn.setObjectName("ActionBtn")
        self._wifi_enable_btn.setStyleSheet(_BTN_ACTION)
        self._wifi_enable_btn.clicked.connect(self._enable_wifi_powersave)
        self._wifi_btn_row.addWidget(self._wifi_enable_btn)

        self._wifi_result_lbl = QLabel("")
        self._wifi_result_lbl.setObjectName("FieldHint")
        self._wifi_btn_row.addWidget(self._wifi_result_lbl)
        self._wifi_btn_row.addStretch()
        layout.addLayout(self._wifi_btn_row)

        # "No WiFi" label (hidden by default)
        self._wifi_no_adapter_lbl = QLabel(self.t("network.wifi_not_detected"))
        self._wifi_no_adapter_lbl.setObjectName("FieldHint")
        self._wifi_no_adapter_lbl.hide()
        layout.addWidget(self._wifi_no_adapter_lbl)

        parent_layout.addWidget(self._wifi_card)

    def _update_wifi_ui(self, info: dict):
        """Update WiFi card based on detected state."""
        wifi_ifaces = info.get("wifi_interfaces", [])
        has_wifi = len(wifi_ifaces) > 0
        conf_exists = info.get("wifi_conf_exists", False)

        if has_wifi:
            self._wifi_no_adapter_lbl.hide()
            self._wifi_disable_btn.show()
            self._wifi_enable_btn.show()

            if "wifi_powersave" in info:
                ps_key = "network.wifi_status_on" if info["wifi_powersave"] else "network.wifi_status_off"
                iface_str = ", ".join(wifi_ifaces)
                self._wifi_status_lbl.setText(f"{self.t(ps_key)}  [{iface_str}]")
            else:
                self._wifi_status_lbl.setText(
                    f"WiFi: {', '.join(wifi_ifaces)} — "
                    f"{self.t('network.wifi_conf_applied') if conf_exists else self.t('network.wifi_conf_not_applied')}"
                )
        else:
            # No WiFi — but still show config file status (Ethernet-only systems may
            # still want to pre-configure for future WiFi use)
            self._wifi_no_adapter_lbl.show()
            self._wifi_disable_btn.hide()
            self._wifi_enable_btn.hide()
            self._wifi_status_lbl.setText("")

        if conf_exists:
            self._wifi_conf_lbl.setText(f"{_WIFI_POWERSAVE_FILE}  [wifi.powersave = 2]")
        else:
            self._wifi_conf_lbl.setText(f"{_WIFI_POWERSAVE_FILE}  [{self.t('network.file_not_exists')}]")

    # ── IPv6 card ─────────────────────────────────────────────────────────────

    def _build_ipv6_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._ipv6_title_lbl = QLabel(self.t("network.ipv6_title"))
        self._ipv6_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._ipv6_title_lbl)

        self._ipv6_hint_lbl = QLabel(self.t("network.ipv6_hint"))
        self._ipv6_hint_lbl.setObjectName("FieldHint")
        self._ipv6_hint_lbl.setWordWrap(True)
        layout.addWidget(self._ipv6_hint_lbl)

        self._ipv6_status_lbl = QLabel("")
        self._ipv6_status_lbl.setObjectName("FieldHint")
        layout.addWidget(self._ipv6_status_lbl)

        btn_row = QHBoxLayout()
        self._ipv6_disable_btn = QPushButton(self.t("network.ipv6_disable"))
        self._ipv6_disable_btn.setObjectName("ActionBtn")
        self._ipv6_disable_btn.setStyleSheet(_BTN_ACTION)
        self._ipv6_disable_btn.clicked.connect(self._disable_ipv6)
        btn_row.addWidget(self._ipv6_disable_btn)

        self._ipv6_enable_btn = QPushButton(self.t("network.ipv6_enable"))
        self._ipv6_enable_btn.setObjectName("ActionBtn")
        self._ipv6_enable_btn.setStyleSheet(_BTN_ACTION)
        self._ipv6_enable_btn.clicked.connect(self._enable_ipv6)
        btn_row.addWidget(self._ipv6_enable_btn)

        self._ipv6_result_lbl = QLabel("")
        self._ipv6_result_lbl.setObjectName("FieldHint")
        btn_row.addWidget(self._ipv6_result_lbl)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    # ── Speed Test card ───────────────────────────────────────────────────────

    def _build_speedtest_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._speed_title_lbl = QLabel(self.t("network.speed_title"))
        self._speed_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._speed_title_lbl)

        self._speed_hint_lbl = QLabel(self.t("network.speed_hint"))
        self._speed_hint_lbl.setObjectName("FieldHint")
        self._speed_hint_lbl.setWordWrap(True)
        layout.addWidget(self._speed_hint_lbl)

        self._speed_result_lbl = QLabel("")
        self._speed_result_lbl.setStyleSheet(_STATUS_MONO)
        self._speed_result_lbl.setWordWrap(True)
        self._speed_result_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._speed_result_lbl.hide()
        layout.addWidget(self._speed_result_lbl)

        btn_row = QHBoxLayout()
        self._speed_btn = QPushButton(self.t("network.speed_run"))
        self._speed_btn.setObjectName("ActionBtn")
        self._speed_btn.setStyleSheet(_BTN_ACTION)
        self._speed_btn.clicked.connect(self._run_speedtest)
        btn_row.addWidget(self._speed_btn)

        self._speed_install_btn = QPushButton(self.t("network.speed_install"))
        self._speed_install_btn.setStyleSheet(_BTN_INSTALL)
        self._speed_install_btn.clicked.connect(
            lambda: self._install_pkg("speedtest-cli")
        )
        if shutil.which("speedtest-cli") or shutil.which("speedtest"):
            self._speed_install_btn.hide()
        btn_row.addWidget(self._speed_install_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(card)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_shown(self):
        self._refresh_status()

    def apply_language(self):
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._status_title_lbl.setText(self.t("network.status_title"))
        self._refresh_btn.setText(self.t("network.refresh"))
        self._dns_title_lbl.setText(self.t("network.dns_title"))
        self._dns_hint_lbl.setText(self.t("network.dns_hint"))
        self._dns_preset_lbl.setText(self.t("network.dns_preset"))
        self._dns_primary_lbl.setText(self.t("network.dns_primary"))
        self._dns_secondary_lbl.setText(self.t("network.dns_secondary"))
        self._dns_apply_btn.setText(self.t("network.dns_apply"))
        self._tcp_title_lbl.setText(self.t("network.tcp_title"))
        self._tcp_hint_lbl.setText(self.t("network.tcp_hint"))
        self._tcp_apply_btn.setText(self.t("network.tcp_apply"))
        self._tcp_remove_btn.setText(self.t("network.tcp_remove"))
        for cb, group, _ in self._tcp_checkboxes:
            cb.setText(self.t(group["label_key"]))
        self._wifi_title_lbl.setText(self.t("network.wifi_title"))
        self._wifi_hint_lbl.setText(self.t("network.wifi_hint"))
        self._wifi_disable_btn.setText(self.t("network.wifi_disable_powersave"))
        self._wifi_enable_btn.setText(self.t("network.wifi_enable_powersave"))
        self._wifi_no_adapter_lbl.setText(self.t("network.wifi_not_detected"))
        self._ipv6_title_lbl.setText(self.t("network.ipv6_title"))
        self._ipv6_hint_lbl.setText(self.t("network.ipv6_hint"))
        self._ipv6_disable_btn.setText(self.t("network.ipv6_disable"))
        self._ipv6_enable_btn.setText(self.t("network.ipv6_enable"))
        self._speed_title_lbl.setText(self.t("network.speed_title"))
        self._speed_hint_lbl.setText(self.t("network.speed_hint"))
        self._speed_btn.setText(self.t("network.speed_run"))
        self._speed_install_btn.setText(self.t("network.speed_install"))
        self._drv_title_lbl.setText(self.t("network.drv_title"))
        self._drv_hint_lbl.setText(self.t("network.drv_hint"))
        self._drv_apply_btn.setText(self.t("network.drv_apply"))
        self._drv_remove_btn.setText(self.t("network.drv_remove"))
        self._drv_reload_btn.setText(self.t("network.drv_reload"))
        self._drv_reconnect_btn.setText(self.t("network.drv_reconnect"))
        self._drv_reboot_lbl.setText(self.t("network.drv_reboot_hint"))

    # ── Refresh status ────────────────────────────────────────────────────────

    def _refresh_status(self):
        self._net_status_lbl.setText(self.t("network.loading"))
        self._refresh_btn.setEnabled(False)
        worker = _NetInfoWorker()
        worker.done.connect(self._on_status_ready)
        self._info_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_status_ready(self, info: dict):
        self._refresh_btn.setEnabled(True)

        lines = []

        # Connections
        if info.get("connections"):
            lines.append(self.t("network.stat_connections"))
            for conn in info["connections"].splitlines():
                parts = conn.split(":")
                if len(parts) >= 4:
                    lines.append(f"  {parts[0]}  ({parts[1]})  {parts[2]}  [{parts[3]}]")
                else:
                    lines.append(f"  {conn}")

        # Interfaces
        if info.get("interfaces"):
            lines.append("")
            lines.append(self.t("network.stat_interfaces"))
            for iface in info["interfaces"].splitlines():
                lines.append(f"  {iface}")

        # DNS
        dns_ips = info.get("dns_ips", [])
        if dns_ips:
            lines.append("")
            lines.append(f"{self.t('network.stat_dns')}  {', '.join(dns_ips)}")
        elif info.get("dns_display"):
            lines.append("")
            lines.append(self.t("network.stat_dns"))
            for line in info["dns_display"].splitlines():
                lines.append(f"  {line}")

        # TCP congestion
        lines.append("")
        lines.append(f"TCP: {info.get('tcp_cc', '?')}"
                     + (f"  [{self.t('network.tcp_status_applied')}]"
                        if info.get("sysctl_applied") else ""))

        # WiFi
        wifi_ifaces = info.get("wifi_interfaces", [])
        if wifi_ifaces:
            lines.append("")
            ps = info.get("wifi_powersave")
            ps_str = "ON" if ps else ("OFF" if ps is False else "?")
            lines.append(f"WiFi: {', '.join(wifi_ifaces)}  Power Save: {ps_str}")

        # IPv6
        lines.append("")
        ipv6 = self.t("network.ipv6_off") if info.get("ipv6_disabled") else self.t("network.ipv6_on")
        lines.append(f"IPv6: {ipv6}")

        self._net_status_lbl.setText("\n".join(lines))

        # ── Update sub-cards ──────────────────────────────────────────────────

        # DNS: sync combo to current state
        self._sync_dns_combo(dns_ips)
        if dns_ips:
            self._dns_current_lbl.setText(", ".join(dns_ips))
            self._dns_current_lbl.show()
        else:
            self._dns_current_lbl.setText("Auto (DHCP)")
            self._dns_current_lbl.show()

        # TCP: update values
        sysctl_current = info.get("sysctl_current", {})
        all_match = self._update_tcp_values(sysctl_current)
        cc = info.get("tcp_cc", "?")
        applied = info.get("sysctl_applied", False)
        if applied:
            self._tcp_status_lbl.setText(
                f"{self.t('network.tcp_status_current')}: {cc} — {self.t('network.tcp_status_applied')}"
            )
            self._tcp_status_lbl.setStyleSheet(_RESULT_OK)
        else:
            self._tcp_status_lbl.setText(
                f"{self.t('network.tcp_status_current')}: {cc} — {self.t('network.tcp_status_not_applied')}"
            )
            self._tcp_status_lbl.setStyleSheet("")

        # WiFi
        self._update_wifi_ui(info)

        # WiFi driver
        self._update_driver_ui(info)

        # Driver info in status card
        wifi_drivers = info.get("wifi_drivers", {})
        if wifi_drivers:
            lines_extra = []
            for iface, drv in wifi_drivers.items():
                preset = _WIFI_DRIVER_PARAMS.get(drv, {})
                label = preset.get("label", drv) if preset else drv
                lines_extra.append(f"  {iface}: {label}")
            conf_str = self.t("network.wifi_conf_applied") if info.get("driver_conf_exists") else self.t("network.file_not_exists")
            current_text = self._net_status_lbl.text()
            driver_block = f"\n{self.t('network.drv_title')}:\n" + "\n".join(lines_extra) + f"\n  {_WIFI_DRIVER_FILE}  [{conf_str}]"
            self._net_status_lbl.setText(current_text + driver_block)

        # IPv6
        ipv6_key = "network.ipv6_status_off" if info.get("ipv6_disabled") else "network.ipv6_status_on"
        self._ipv6_status_lbl.setText(self.t(ipv6_key))

    # ── DNS actions ───────────────────────────────────────────────────────────

    def _apply_dns(self):
        idx = self._dns_combo.currentIndex()
        key = self._dns_combo.itemData(idx)

        if key == "auto":
            self._run_dns_revert()
            return

        if key == "custom":
            dns4 = [s.strip() for s in [self._dns_primary.text(), self._dns_secondary.text()] if s.strip()]
            dns6 = []
        else:
            for k, _, v4, v6 in _DNS_PRESETS:
                if k == key:
                    dns4 = v4
                    dns6 = v6
                    break
            else:
                return

        if not dns4:
            self._dns_status_lbl.setText(self.t("network.dns_empty"))
            self._dns_status_lbl.setStyleSheet(_RESULT_ERR)
            return

        self._dns_apply_btn.setEnabled(False)
        self._dns_status_lbl.setText(self.t("network.applying"))
        self._dns_status_lbl.setStyleSheet("")

        def do_apply():
            try:
                r = subprocess.run(
                    ["nmcli", "-t", "-f", "NAME,DEVICE", "con", "show", "--active"],
                    capture_output=True, text=True, timeout=5
                )
                connections = []
                for line in r.stdout.strip().splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2 and parts[1] and parts[1] != "lo":
                        connections.append(parts[0])

                if not connections:
                    return False, self.t("network.dns_no_connections")

                all_dns = " ".join(dns4 + dns6)
                for conn in connections:
                    subprocess.run(
                        ["nmcli", "con", "mod", conn, "ipv4.dns", " ".join(dns4)],
                        capture_output=True, timeout=10
                    )
                    subprocess.run(
                        ["nmcli", "con", "mod", conn, "ipv4.ignore-auto-dns", "yes"],
                        capture_output=True, timeout=10
                    )
                    if dns6:
                        subprocess.run(
                            ["nmcli", "con", "mod", conn, "ipv6.dns", " ".join(dns6)],
                            capture_output=True, timeout=10
                        )
                        subprocess.run(
                            ["nmcli", "con", "mod", conn, "ipv6.ignore-auto-dns", "yes"],
                            capture_output=True, timeout=10
                        )
                    subprocess.run(
                        ["nmcli", "con", "up", conn],
                        capture_output=True, timeout=15
                    )

                return True, f"DNS → {all_dns}"
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_apply()
            self._dns_apply_btn.setEnabled(True)
            if ok:
                self._dns_status_lbl.setText(msg)
                self._dns_status_lbl.setStyleSheet(_RESULT_OK)
                self._refresh_status()
            else:
                self._dns_status_lbl.setText(msg)
                self._dns_status_lbl.setStyleSheet(_RESULT_ERR)

        threading.Thread(target=run_and_emit, daemon=True).start()

    def _run_dns_revert(self):
        self._dns_apply_btn.setEnabled(False)
        self._dns_status_lbl.setText(self.t("network.applying"))

        def do_revert():
            try:
                r = subprocess.run(
                    ["nmcli", "-t", "-f", "NAME,DEVICE", "con", "show", "--active"],
                    capture_output=True, text=True, timeout=5
                )
                for line in r.stdout.strip().splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2 and parts[1] and parts[1] != "lo":
                        conn = parts[0]
                        subprocess.run(
                            ["nmcli", "con", "mod", conn, "ipv4.dns", ""],
                            capture_output=True, timeout=10
                        )
                        subprocess.run(
                            ["nmcli", "con", "mod", conn, "ipv4.ignore-auto-dns", "no"],
                            capture_output=True, timeout=10
                        )
                        subprocess.run(
                            ["nmcli", "con", "mod", conn, "ipv6.dns", ""],
                            capture_output=True, timeout=10
                        )
                        subprocess.run(
                            ["nmcli", "con", "mod", conn, "ipv6.ignore-auto-dns", "no"],
                            capture_output=True, timeout=10
                        )
                        subprocess.run(
                            ["nmcli", "con", "up", conn],
                            capture_output=True, timeout=15
                        )
                self._dns_apply_btn.setEnabled(True)
                self._dns_status_lbl.setText(self.t("network.dns_reverted"))
                self._dns_status_lbl.setStyleSheet(_RESULT_OK)
                self._refresh_status()
            except Exception as e:
                self._dns_apply_btn.setEnabled(True)
                self._dns_status_lbl.setText(str(e))
                self._dns_status_lbl.setStyleSheet(_RESULT_ERR)

        threading.Thread(target=do_revert, daemon=True).start()

    # ── TCP actions ───────────────────────────────────────────────────────────

    def _apply_tcp(self):
        # Collect only checked groups
        selected_params = {}
        for cb, group, _ in self._tcp_checkboxes:
            if cb.isChecked():
                selected_params.update(group["params"])

        if not selected_params:
            self._tcp_result_lbl.setText(self.t("network.tcp_nothing_selected"))
            self._tcp_result_lbl.setStyleSheet(_RESULT_ERR)
            return

        lines = [
            "# Equestria OS — network performance optimizations",
            "# Managed by equestria-os-settings. Edit groups via the Settings app.",
            "",
        ]
        for key, val in selected_params.items():
            lines.append(f"{key} = {val}")

        content = "\n".join(lines) + "\n"

        self._tcp_apply_btn.setEnabled(False)
        self._tcp_result_lbl.setText(self.t("network.applying"))
        self._tcp_result_lbl.setStyleSheet("")

        def do_apply():
            try:
                proc = subprocess.run(
                    ["pkexec", "tee", _SYSCTL_FILE],
                    input=content, capture_output=True, text=True, timeout=30
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                proc = subprocess.run(
                    ["pkexec", "sysctl", "--system"],
                    capture_output=True, text=True, timeout=15
                )
                return True, self.t("network.tcp_applied")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_apply()
            self._tcp_apply_btn.setEnabled(True)
            self._tcp_result_lbl.setText(msg)
            self._tcp_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    def _remove_tcp(self):
        self._tcp_remove_btn.setEnabled(False)
        self._tcp_result_lbl.setText(self.t("network.applying"))

        def do_remove():
            try:
                proc = subprocess.run(
                    ["pkexec", "rm", "-f", _SYSCTL_FILE],
                    capture_output=True, text=True, timeout=15
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                subprocess.run(
                    ["pkexec", "sysctl", "--system"],
                    capture_output=True, text=True, timeout=15
                )
                return True, self.t("network.tcp_removed")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_remove()
            self._tcp_remove_btn.setEnabled(True)
            self._tcp_result_lbl.setText(msg)
            self._tcp_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    # ── WiFi actions ──────────────────────────────────────────────────────────

    def _disable_wifi_powersave(self):
        content = "[connection]\nwifi.powersave = 2\n"
        self._wifi_disable_btn.setEnabled(False)
        self._wifi_result_lbl.setText(self.t("network.applying"))
        self._wifi_result_lbl.setStyleSheet("")

        def do_apply():
            try:
                proc = subprocess.run(
                    ["pkexec", "tee", _WIFI_POWERSAVE_FILE],
                    input=content, capture_output=True, text=True, timeout=15
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                subprocess.run(
                    ["pkexec", "systemctl", "restart", "NetworkManager"],
                    capture_output=True, timeout=15
                )
                return True, self.t("network.wifi_powersave_disabled")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_apply()
            self._wifi_disable_btn.setEnabled(True)
            self._wifi_result_lbl.setText(msg)
            self._wifi_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                import time
                time.sleep(2)
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    def _enable_wifi_powersave(self):
        self._wifi_enable_btn.setEnabled(False)
        self._wifi_result_lbl.setText(self.t("network.applying"))

        def do_apply():
            try:
                proc = subprocess.run(
                    ["pkexec", "rm", "-f", _WIFI_POWERSAVE_FILE],
                    capture_output=True, text=True, timeout=15
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                subprocess.run(
                    ["pkexec", "systemctl", "restart", "NetworkManager"],
                    capture_output=True, timeout=15
                )
                return True, self.t("network.wifi_powersave_enabled")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_apply()
            self._wifi_enable_btn.setEnabled(True)
            self._wifi_result_lbl.setText(msg)
            self._wifi_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                import time
                time.sleep(2)
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    # ── IPv6 actions ──────────────────────────────────────────────────────────

    def _disable_ipv6(self):
        content = (
            "# Equestria OS — disable IPv6\n"
            "net.ipv6.conf.all.disable_ipv6 = 1\n"
            "net.ipv6.conf.default.disable_ipv6 = 1\n"
            "net.ipv6.conf.lo.disable_ipv6 = 1\n"
        )
        sysctl_file = "/etc/sysctl.d/99-equestria-ipv6.conf"

        self._ipv6_disable_btn.setEnabled(False)
        self._ipv6_result_lbl.setText(self.t("network.applying"))
        self._ipv6_result_lbl.setStyleSheet("")

        def do_apply():
            try:
                proc = subprocess.run(
                    ["pkexec", "tee", sysctl_file],
                    input=content, capture_output=True, text=True, timeout=15
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                subprocess.run(
                    ["pkexec", "sysctl", "--system"],
                    capture_output=True, text=True, timeout=15
                )
                return True, self.t("network.ipv6_disabled_ok")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_apply()
            self._ipv6_disable_btn.setEnabled(True)
            self._ipv6_result_lbl.setText(msg)
            self._ipv6_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    def _enable_ipv6(self):
        sysctl_file = "/etc/sysctl.d/99-equestria-ipv6.conf"

        self._ipv6_enable_btn.setEnabled(False)
        self._ipv6_result_lbl.setText(self.t("network.applying"))

        def do_apply():
            try:
                proc = subprocess.run(
                    ["pkexec", "rm", "-f", sysctl_file],
                    capture_output=True, text=True, timeout=15
                )
                if proc.returncode != 0:
                    return False, proc.stderr.strip()
                subprocess.run(
                    ["pkexec", "sysctl", "--system"],
                    capture_output=True, text=True, timeout=15
                )
                return True, self.t("network.ipv6_enabled_ok")
            except Exception as e:
                return False, str(e)

        def run_and_emit():
            ok, msg = do_apply()
            self._ipv6_enable_btn.setEnabled(True)
            self._ipv6_result_lbl.setText(msg)
            self._ipv6_result_lbl.setStyleSheet(_RESULT_OK if ok else _RESULT_ERR)
            if ok:
                self._refresh_status()

        threading.Thread(target=run_and_emit, daemon=True).start()

    # ── Speed test ────────────────────────────────────────────────────────────

    def _run_speedtest(self):
        self._speed_btn.setEnabled(False)
        self._speed_btn.setText(self.t("network.speed_running"))
        self._speed_result_lbl.setText("...")
        self._speed_result_lbl.show()

        worker = _SpeedTestWorker()
        worker.progress.connect(lambda msg: self._speed_btn.setText(
            f"{self.t('network.speed_running')} ({msg})"
        ))
        worker.done.connect(self._on_speedtest_done)
        self._speed_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_speedtest_done(self, result: str):
        self._speed_btn.setEnabled(True)
        self._speed_btn.setText(self.t("network.speed_run"))
        if result.startswith("ERROR"):
            self._speed_result_lbl.setStyleSheet(_RESULT_ERR)
            self._speed_result_lbl.setText(result)
            self._speed_install_btn.show()
        else:
            self._speed_result_lbl.setStyleSheet(_STATUS_MONO)
            self._speed_result_lbl.setText(result)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _install_pkg(self, pkg: str):
        for term in [["konsole", "-e"], ["xterm", "-e"], ["gnome-terminal", "--"]]:
            if shutil.which(term[0]):
                subprocess.Popen(term + ["yay", "-S", pkg], start_new_session=True)
                return
