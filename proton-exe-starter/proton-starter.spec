# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — Equestria OS Proton Starter (unified bundle)
#
# Three tools, one shared Python/Qt6 runtime → single onedir bundle:
#   equestria-proton-settings  (main.py)     — Proton app manager
#   equestria-proton-run       (launcher.py) — .exe file opener
#   equestria-proton-cleaner   (cleaner.py)  — cache cleaner
#
# Build:  pyinstaller proton-starter.spec
# Output: dist/equestria-proton-starter/
#
# Size strategy (target < 100 MB for the whole .pkg.tar.zst)
# ───────────────────────────────────────────────────────────
# System Qt6 libs → declared as deps (qt6-base), NOT bundled.
# System X11/xcb/GL/ICU → same.
# All three apps share ONE Python + PyQt6 runtime.

import os
import sys
import subprocess
from pathlib import Path

project_root = Path(SPECPATH)

# When PyInstaller is installed in an isolated env (e.g. pipx), it may not see
# system-wide packages like PyQt6. Detect the real system site-packages and
# prepend it so Analysis can follow import chains correctly.
try:
    _sys_site = subprocess.check_output(
        ["python3", "-c", "import site; print(site.getsitepackages()[0])"],
        text=True,
    ).strip()
    if _sys_site and _sys_site not in sys.path:
        sys.path.insert(0, _sys_site)
except Exception:
    pass

def _is_system_lib(dest_name, src_path):
    """
    Return True for shared libraries that are provided by system packages
    and should NOT be bundled (they'll be installed as PKGBUILD deps).

    Strategy: exclude everything from /usr/lib/ and /usr/local/lib/ that is
    NOT inside a Python site-packages directory.  This catches Qt6 native
    libs, KDE/GTK libs, codec libs, etc. while keeping PyQt6 Python bindings.
    """
    p = src_path or ""
    if "/site-packages/" in p:
        return False  # PyQt6 bindings, etc. — keep
    if p.startswith("/usr/lib/") or p.startswith("/usr/local/lib/"):
        return True   # system .so — exclude
    return False

# Shared data files for all three apps
_datas = [
    (str(project_root / "localization.csv"),    "."),
    (str(project_root / "style.qss"),           "."),
    (str(project_root / "EquestriaOS-Logo.png"), "."),
]

a = Analysis(
    [str(project_root / "dispatch.py")],
    pathex=[str(project_root)] + ([_sys_site] if "_sys_site" in dir() and _sys_site else []),
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # All three app modules must be importable at runtime
        "main",
        "launcher",
        "cleaner",
        "ui",
        "proton_runner",
        # PyQt6 modules used by the apps
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtNetwork",
    ],
    excludes=[
        # Unused Qt bindings
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
        # Not used here
        "numpy", "pygments",
    ],
    noarchive=False,
)

# Drop system-provided shared libs (declared as PKGBUILD runtime deps)
a.binaries = TOC([
    entry for entry in a.binaries
    if not _is_system_lib(entry[0], entry[1])
])

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="equestria-proton-starter",
    debug=False,
    strip=True,
    upx=False,
    console=False,
    icon=str(project_root / "EquestriaOS-Logo.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name="equestria-proton-starter",
)
