# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — Equestria OS Software Center
#
# Build:  pyinstaller equestria-os-software-center.spec
# Output: dist/equestria-os-software-center  (single file)
#
# Size strategy (target < 100 MB)
# ────────────────────────────────
# System Qt6 libs → declared as deps (qt6-base, qt6-svg), NOT bundled.
# System X11/xcb/GL/ICU/Wayland → same.
# Unused Qt6 modules → excluded.

import os
import sys
import subprocess
from pathlib import Path

project_root = Path(SPECPATH)

# Ensure system site-packages are visible (when PyInstaller runs in pipx/venv)
try:
    _sys_site = subprocess.check_output(
        ["python3", "-c", "import site; print(site.getsitepackages()[0])"],
        text=True,
    ).strip()
    if _sys_site and _sys_site not in sys.path:
        sys.path.insert(0, _sys_site)
except Exception:
    _sys_site = ""

def _is_system_lib(dest_name, src_path):
    """
    Return True for .so files that live in /usr/lib (system packages).
    PyQt6 bindings live inside site-packages — those are kept.
    """
    p = src_path or ""
    if "/site-packages/" in p:
        return False
    if p.startswith("/usr/lib/") or p.startswith("/usr/local/lib/"):
        return True
    return False

_pathex = [str(project_root)]
if _sys_site:
    _pathex.append(_sys_site)

_datas = [
    (str(project_root / "EquestriaApps.csv"),           "."),
    (str(project_root / "EquestriaLocalizations.csv"),  "."),
    (str(project_root / "equestria_cyrillic.ttf"),       "."),
    (str(project_root / "equestria-os-software-center.png"), "."),
    (str(project_root / "style.qss"),                   "."),
    (str(project_root / "locales"),                     "locales"),
]

a = Analysis(
    [str(project_root / "main.py")],
    pathex=_pathex,
    binaries=[],
    datas=_datas,
    hiddenimports=[
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtNetwork",
        "models",
        "utils",
        "workers",
        "ui_software",
    ],
    excludes=[
        # Unused Qt6 modules
        "PyQt6.QtBluetooth",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtNfc",
        "PyQt6.QtPositioning",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSpatialAudio",
        "PyQt6.QtSql",
        "PyQt6.QtStateMachine",
        "PyQt6.QtTest",
        "PyQt6.QtTextToSpeech",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebSockets",
        "PyQt6.QtXml",
        "PyQt6.QtHelp",
        "PyQt6.QtDesigner",
        "PyQt6.QtOpenGL",
        "PyQt6.QtOpenGLWidgets",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.QtSvg",
        "PyQt6.QtSvgWidgets",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtDBus",
        # Unused stdlib
        "tkinter", "unittest", "distutils", "lib2to3",
        "xmlrpc", "pydoc", "doctest", "turtle", "turtledemo",
        "_msi", "winreg", "winsound", "msvcrt", "ensurepip", "venv", "idlelib",
        "numpy", "pygments",
    ],
    noarchive=False,
)

# Drop system-provided shared libs
a.binaries = TOC([
    entry for entry in a.binaries
    if not _is_system_lib(entry[0], entry[1])
])

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="equestria-os-software-center",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=str(project_root / "equestria-os-software-center.png"),
)
