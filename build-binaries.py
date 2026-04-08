#!/usr/bin/env python3
"""Build all Equestria OS Python projects with PyInstaller.
Uses spec files to exclude large system libraries (ICU data, video codecs, KDE icons)
since Equestria OS always has Qt6/KDE installed system-wide.
"""

import os
import subprocess
import sys
import shutil
import textwrap

BASE = "/mnt/NewBaseD/FromSystem/Git Projects/equestria-packages"
DIST = "/mnt/NewBaseD/FromSystem/Git Projects/equestria-packages-builds/bins"
WORK = "/tmp/equestria-build-work"
SPEC_DIR = "/tmp/equestria-build-specs"

PYINSTALLER = "/home/lucial/.local/bin/pyinstaller"
SYSTEM_SITE = "/usr/lib/python3.14/site-packages"
env = os.environ.copy()
existing_pp = env.get("PYTHONPATH", "")
env["PYTHONPATH"] = f"{SYSTEM_SITE}:{existing_pp}" if existing_pp else SYSTEM_SITE

PYTHON_EXCLUDES = [
    'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngine',
    'PyQt6.Qt3DAnimation', 'PyQt6.Qt3DCore', 'PyQt6.Qt3DExtras',
    'PyQt6.Qt3DInput', 'PyQt6.Qt3DLogic', 'PyQt6.Qt3DRender',
    'PyQt6.QtBluetooth', 'PyQt6.QtSql', 'PyQt6.QtMultimedia',
    'PyQt6.QtMultimediaWidgets', 'PyQt6.QtCharts', 'PyQt6.QtDataVisualization',
    'PyQt6.QtDesigner', 'PyQt6.QtHelp', 'PyQt6.QtTest', 'PyQt6.QtXml',
    'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets', 'PyQt6.QtNetwork',
    'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets',
    'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'PyQt6.QtPrintSupport',
    'PyQt6.QtDBus', 'PyQt6.QtNfc', 'PyQt6.QtPositioning',
    'PyQt6.QtLocation', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort',
    'PyQt6.QtTextToSpeech', 'PyQt6.QtSpatialAudio', 'PyQt6.QtRemoteObjects',
    'tkinter', 'unittest', 'numpy', 'scipy', 'pandas', 'matplotlib',
]

def make_spec(name, src_dir, entry, datas, console=False, extra_hiddenimports=None):
    """Generate a PyInstaller spec file for a project."""
    entry_path = os.path.join(src_dir, entry)
    datas_repr = repr(datas)
    excludes_repr = repr(PYTHON_EXCLUDES)
    hidden_repr = repr(extra_hiddenimports or [])
    windowed = 'True' if not console else 'False'

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
# Auto-generated spec for {name}

a = Analysis(
    [{entry_path!r}],
    pathex=[{src_dir!r}],
    binaries=[],
    datas={datas_repr},
    hiddenimports={hidden_repr},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={excludes_repr},
    noarchive=False,
)

# Exclude system-provided .so files from the bundle.
# Equestria OS (Arch/KDE) always has Qt6, KDE libs, codecs, ICU etc. system-wide.
# Keep only Python site-packages bindings (PyQt6 .abi3.so, numpy _core, etc.)
a.binaries = [
    (n, p, t) for n, p, t in a.binaries
    if "/site-packages/" in (p or "")
    or (not (p or "").startswith("/usr/lib/") and not (p or "").startswith("/usr/local/lib/"))
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name={name!r},
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    runtime_tmpdir=None,
    console=not {windowed},
    disable_windowed_traceback=False,
)
'''
    spec_path = os.path.join(SPEC_DIR, f"{name}.spec")
    with open(spec_path, 'w') as f:
        f.write(spec_content)
    return spec_path


def build(name, src_dir, entry, datas=None, console=False, extra_hiddenimports=None):
    """Build a single project using a generated spec file."""
    entry_path = os.path.join(src_dir, entry)
    if not os.path.exists(entry_path):
        print(f"  [SKIP] Entry not found: {entry_path}")
        return False

    if datas is None:
        datas = []

    # Filter out missing data files
    valid_datas = []
    for src, dst in datas:
        if os.path.exists(src):
            valid_datas.append((src, dst))
        else:
            print(f"  [WARN] Missing asset: {src}")
    datas = valid_datas

    spec_path = make_spec(name, src_dir, entry, datas, console, extra_hiddenimports)

    cmd = [
        PYINSTALLER,
        '--noconfirm',
        '--distpath', DIST,
        '--workpath', os.path.join(WORK, name),
        spec_path,
    ]

    print(f"\n{'='*60}")
    print(f"Building: {name}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, cwd=src_dir, env=env)
    if result.returncode != 0:
        print(f"  [FAIL] Build failed for {name}")
        return False

    out = os.path.join(DIST, name)
    if os.path.exists(out):
        size = os.path.getsize(out) / (1024 * 1024)
        status = "OK" if size <= 100 else "OVERSIZE"
        print(f"  [{status}] {name}: {size:.1f} MB")
        if size > 100:
            print(f"  [WARN] Binary exceeds 100 MB!")
    return True


def D(src_dir, *pairs):
    """Build data file list with absolute source paths."""
    result = []
    for src_rel, dst in pairs:
        src = os.path.abspath(os.path.join(src_dir, src_rel))
        result.append((src, dst))
    return result


# ── Setup ─────────────────────────────────────────────────────────
os.makedirs(DIST, exist_ok=True)
os.makedirs(WORK, exist_ok=True)
os.makedirs(SPEC_DIR, exist_ok=True)

results = {}

# ── equestria-os-disk-manager ──────────────────────────────────────
d = f"{BASE}/equestria-os-disk-manager"
results["equestria-os-disk-manager"] = build(
    "equestria-os-disk-manager", d, "disk_app.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."), ("equestria-os-disk-manager.png","."))
)
results["equestria-os-disk-backend"] = build(
    "equestria-os-disk-backend", d, "disk_backend.py", console=True
)

# ── equestria-os-swap-manager ─────────────────────────────────────
d = f"{BASE}/equestria-os-swap-manager"
results["equestria-os-swap-manager"] = build(
    "equestria-os-swap-manager", d, "swap_app.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."),
      ("equestria-os-swap-manager.png","."), ("check_mark.svg","."))
)
results["equestria-os-swap-backend"] = build(
    "equestria-os-swap-backend", d, "swap_backend.py", console=True
)

# ── equestria-os-relocator ────────────────────────────────────────
d = f"{BASE}/equestria-os-relocator"
results["equestria-os-relocator"] = build(
    "equestria-os-relocator", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."), ("equestria-os-relocator.png","."))
)
results["equestria-os-relocator-backend"] = build(
    "equestria-os-relocator-backend", d, "backend.py", console=True
)

# ── equestria-os-tutorial ─────────────────────────────────────────
d = f"{BASE}/equestria-os-tutorial"
results["equestria-os-tutorial"] = build(
    "equestria-os-tutorial", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."),
      ("tutorial.png","."), ("assets","assets"), ("locales","locales"))
)

# ── equestria-os-git-askpass ──────────────────────────────────────
d = f"{BASE}/equestria-os-git-askpass"
results["equestria-os-git-askpass"] = build(
    "equestria-os-git-askpass", d, "equestria-os-git-askpass.py",
    D(d, ("style.qss","."), ("EquestriaOS-Logo.png","."), ("localization.csv","."))
)

# ── equestria-os-package-manager ──────────────────────────────────
d = f"{BASE}/equestria-os-package-manager"
results["equestria-os-package-manager"] = build(
    "equestria-os-package-manager", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."), ("equestria-os-package-manager.png","."))
)

# ── equestria-os-save-point ───────────────────────────────────────
d = f"{BASE}/equestria-os-save-point"
results["equestria-os-save-point"] = build(
    "equestria-os-save-point", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."),
      ("equestria-os-save-point.png","."), ("icons","icons"), ("locales","locales"))
)

# ── equestria-os-services-manager ────────────────────────────────
d = f"{BASE}/equestria-os-services-manager"
results["equestria-os-services-manager"] = build(
    "equestria-os-services-manager", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."), ("equestria-os-services-manager.png","."))
)

# ── equestria-os-software-center ─────────────────────────────────
d = f"{BASE}/equestria-os-software-center"
results["equestria-os-software-center"] = build(
    "equestria-os-software-center", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."),
      ("equestria-os-software-center.png","."),
      ("EquestriaApps.csv","."), ("EquestriaLocalizations.csv","."),
      ("locales","locales"))
)

# ── equestria-os-welcome-hub ──────────────────────────────────────
d = f"{BASE}/equestria-os-welcome-hub"
results["equestria-os-welcome-hub"] = build(
    "equestria-os-welcome-hub", d, "welcome_hub.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."), ("EquestriaOS-Logo.png","."))
)

# ── equestria-os-character-theme ─────────────────────────────────
d = f"{BASE}/equestria-os-character-theme"
results["equestria-os-character-theme"] = build(
    "equestria-os-character-theme", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."),
      ("characters.json","."), ("localization.csv","."),
      ("MLP Cutiemarks","MLP Cutiemarks"), ("Wallpapers","Wallpapers"))
)

# ── equestria-os-task-panel-changer ──────────────────────────────
d = f"{BASE}/equstria-os-task-panel-changer"  # note typo in dir name
results["equestria-os-task-panel-changer"] = build(
    "equestria-os-task-panel-changer", d, "main.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."),
      ("EquestriaOS-Logo.png","."), ("localization.csv","."),
      ("presets.json","."), ("MLP Cutiemarks","MLP Cutiemarks"))
)

# ── equestria-os-builder ─────────────────────────────────────────
d = f"{BASE}/equestria-os-builder"
results["equestria-os-builder"] = build(
    "equestria-os-builder", d, "main.py"
)

# ── proton-exe-starter ────────────────────────────────────────────
d = f"{BASE}/proton-exe-starter"
results["proton-exe-starter"] = build(
    "proton-exe-starter", d, "main.py",
    D(d, ("style.qss","."), ("EquestriaOS-Logo.png","."), ("localization.csv","."))
)
results["proton-launcher"] = build(
    "proton-launcher", d, "launcher.py",
    D(d, ("localization.csv",".")), console=True
)
results["proton-cleaner"] = build(
    "proton-cleaner", d, "cleaner.py",
    D(d, ("localization.csv",".")), console=True
)

# ── equestria-os-rename-helper ────────────────────────────────────
d = f"{BASE}/equestria-os-rename-helper"
results["equestria-os-rename-helper"] = build(
    "equestria-os-rename-helper", d, "rename_app.py",
    D(d, ("style.qss","."), ("equestria_cyrillic.ttf","."))
)


# ── Summary ───────────────────────────────────────────────────────
print("\n" + "="*60)
print("BUILD SUMMARY")
print("="*60)
for name, ok in results.items():
    out = os.path.join(DIST, name)
    if ok and os.path.exists(out):
        size = os.path.getsize(out) / (1024*1024)
        flag = " [OVERSIZE!]" if size > 100 else ""
        print(f"  [OK]   {name}: {size:.1f} MB{flag}")
    else:
        print(f"  [FAIL] {name}")

failed = [n for n, ok in results.items() if not ok]
if failed:
    print(f"\nFailed: {failed}")
    sys.exit(1)
else:
    print("\nAll builds succeeded!")
