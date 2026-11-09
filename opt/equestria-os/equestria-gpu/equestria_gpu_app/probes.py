"""gpu: probes."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path
from .localization import tr
from .models import BRANCH_PKGS, Gpu, Sys, nv_family
from .rules import checks_for


def sh(cmd: list, timeout: int = 10) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def read(path: str) -> str:
    try:
        return Path(path).read_text(errors="ignore")
    except OSError:
        return ""


VENDORS = {"10de": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel"}


VENDOR_LABEL = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "other": tr("probes.other")}


def probe_gpus() -> list:
    gpus, cur = [], None
    rx = re.compile(r"(\S+)\s+.+?\s+\[(03[0-9a-f]{2})\]:\s+(.+?)\s+\[([0-9a-f]{4}):([0-9a-f]{4})\]")
    for line in sh(["lspci", "-nnDk"]).splitlines():
        if line and not line[0].isspace():
            cur = None
            m = rx.match(line)
            if not m or m.group(2) not in ("0300", "0302", "0380"):
                continue
            desc, vid, did = m.group(3), m.group(4), m.group(5)
            mk = re.search(r"\[([^\[\]]+)\]\s*$", desc)
            chip = ""
            if vid == "10de":
                cm = re.search(r"NVIDIA Corporation\s+(\S+)", desc)
                chip = cm.group(1) if cm else ""
            g = Gpu(m.group(1), vid, did, VENDORS.get(vid, "other"), mk.group(1) if mk else desc, chip)
            g.boot = read(f"/sys/bus/pci/devices/{g.addr}/boot_vga").strip() == "1"
            if g.vendor == "nvidia":
                g.fam = nv_family(chip)
                n = g.name.upper()
                g.rtx = g.fam in ("GA", "AD", "GB") or (g.fam == "TU" and "RTX" in n)
            gpus.append(g)
            cur = g
        elif cur is not None:
            s = line.strip()
            if s.startswith("Kernel driver in use:"):
                cur.driver = s.split(":", 1)[1].strip()
            elif s.startswith("Kernel modules:"):
                cur.modules = [x.strip() for x in s.split(":", 1)[1].split(",")]
    return gpus


def probe_vulkan() -> list:
    devs, cur = [], None
    for line in sh(["vulkaninfo", "--summary"], 25).splitlines():
        if re.match(r"\s*GPU\d+:", line):
            cur = {}
            devs.append(cur)
        elif cur is not None:
            m = re.match(r"\s*(\w+)\s*=\s*(.+)", line)
            if m:
                cur[m.group(1)] = m.group(2).strip()
    return devs


def probe_smi() -> dict:
    keys = ("bus", "name", "driver", "vram", "temp", "power", "util", "clock", "pstate")
    q = "pci.bus_id,name,driver_version,memory.total,temperature.gpu,power.draw,utilization.gpu,clocks.gr,pstate"
    res = {}
    for line in sh(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"], 8).splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= len(keys):
            res[p[0][-7:].lower()] = dict(zip(keys, p))
    return res


def probe_env() -> dict:
    files = ["/etc/environment"] + sorted(glob.glob("/etc/environment.d/*.conf")) \
        + sorted(glob.glob(str(Path.home() / ".config/environment.d/*.conf")))
    env = {}
    for f in files:
        for line in read(f).splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)=(.*)", line)
            if m and not line.lstrip().startswith("#"):
                env[m.group(1)] = m.group(2).strip().strip("\"'")
    for k in ("VK_ICD_FILENAMES", "VK_DRIVER_FILES", "__GLX_VENDOR_LIBRARY_NAME", "GBM_BACKEND"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


DRIVER_CACHE = "/usr/share/pg-gpu-sync/drivers"


def cached_pkg(name: str) -> str:
    files = sorted(glob.glob(f"{DRIVER_CACHE}/{name}-[0-9]*.pkg.tar.zst"), key=os.path.getmtime)
    return files[-1] if files else ""


def probe_avail(S: Sys) -> dict:
    """Откуда можно взять каждый пакет драйвера: installed / repo / cache / ''."""
    names = sorted({p for s in BRANCH_PKGS.values() for p in s})
    found = set(re.findall(r"^Name\s*:\s*(\S+)", sh(["pacman", "-Si", *names], 20), re.M))
    return {p: ("installed" if p in S.pkgs else "repo" if p in found else "cache" if cached_pkg(p) else "")
            for p in names}


def probe_system() -> Sys:
    S = Sys()
    S.kernel = os.uname().release
    S.session = os.environ.get("XDG_SESSION_TYPE", "?")
    for line in sh(["pacman", "-Q"], 20).splitlines():
        a = line.split(None, 1)
        if len(a) == 2:
            S.pkgs[a[0]] = a[1]
    S.multilib = bool(re.search(r"^\[multilib\]", read("/etc/pacman.conf"), re.M))
    for line in sh(["dkms", "status"]).splitlines():
        m = re.match(r"(\S+?)/(\S+?),\s*(\S+?),\s*(\S+?):\s*(\w+)", line.strip())
        if m:
            S.dkms.append((m.group(1), m.group(2), m.group(3), m.group(5)))
    S.vk_tool = bool(shutil.which("vulkaninfo"))
    S.vk = probe_vulkan() if S.vk_tool else []
    S.smi = probe_smi() if shutil.which("nvidia-smi") else {}
    first = (read("/proc/driver/nvidia/version").splitlines() or [""])[0]
    m = re.search(r"(\d{3}\.\d+(?:\.\d+)?)", first)
    S.nv_version = m.group(1) if m else ""
    S.modeset = read("/sys/module/nvidia_drm/parameters/modeset").strip()
    S.env = probe_env()
    S.avail = probe_avail(S)
    S.gpus = probe_gpus()
    for g in S.gpus:
        g.checks = checks_for(g, S)
    return S
