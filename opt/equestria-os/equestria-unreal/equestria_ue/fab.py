"""Плагин Fab (магазин ассетов Epic) для Linux.

В архив движка для Linux он не входит, а Epic Games Launcher, который ставит его на
Windows/Mac, под Linux нет. Epic выкладывает плагин отдельным архивом на той же странице
https://www.unrealengine.com/linux, например Linux_Fab_5.8.0_0.0.13.zip — по одному на
версию движка (major.minor). Содержимое — Engine/Plugins/Fab, его кладём в движок."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from equestria_ue.engines import Engine
from equestria_ue.jobs import Step
from equestria_ue.kit import tr
from equestria_ue.steps import zip_steps


FAB_RX = re.compile(r"Linux_Fab_(\d+)\.(\d+)\.(\d+)(?:_([\d.]+))?\.zip$")
# Где плагин может лежать: так ставит наш лаунчер и так — Epic Games Launcher
PLUGIN_DIRS = ("Engine/Plugins/Fab", "Engine/Plugins/Marketplace/Fab")


def parse_fab_zip(name: str):
    """Имя архива → ((major, minor), сортируемая версия) или None."""
    m = FAB_RX.search(name)
    if not m:
        return None
    plugin = tuple(int(x) for x in (m.group(4) or "0").split(".") if x)
    return (int(m.group(1)), int(m.group(2))), (int(m.group(3)),) + plugin


def fab_installed(eng: Engine) -> bool:
    return any((Path(eng.path) / d / "Fab.uplugin").exists() for d in PLUGIN_DIRS)


def engine_for_fab(engines: list, name: str):
    """Установленный движок той же версии major.minor, что и архив Fab (самый новый патч)."""
    p = parse_fab_zip(name)
    if not p:
        return None
    same = [e for e in engines if e.version[:2] == p[0]]
    return max(same, key=lambda e: e.version, default=None)


INSTALL_SCRIPT = r'''
import json, os, shutil, subprocess, sys
src_root, engine, label_build, label_done, label_missing = sys.argv[1:6]
up = None
for d, _dirs, files in os.walk(src_root):
    if "Fab.uplugin" in files:
        up = os.path.join(d, "Fab.uplugin")
        break
if not up:
    print(label_missing, flush=True)
    sys.exit(2)
src = os.path.dirname(up)
if not os.path.isdir(os.path.join(src, "Binaries", "Linux")):
    # в архиве только исходники — собираем плагин тем же движком
    print(label_build, flush=True)
    out = src_root.rstrip("/") + "-built"
    shutil.rmtree(out, ignore_errors=True)
    r = subprocess.run(["bash", os.path.join(engine, "Engine/Build/BatchFiles/RunUAT.sh"), "BuildPlugin",
                        "-Plugin=" + up, "-Package=" + out, "-TargetPlatforms=Linux"])
    if r.returncode:
        sys.exit(r.returncode)
    src = out
dst = os.path.join(engine, "Engine", "Plugins", "Fab")
shutil.rmtree(dst, ignore_errors=True)
shutil.copytree(src, dst)
# включаем для всех проектов этого движка — иначе его нужно искать в окне Plugins
p = os.path.join(dst, "Fab.uplugin")
with open(p, encoding="utf-8-sig") as f:
    d = json.load(f)
d["EnabledByDefault"] = True
d["Installed"] = True
with open(p, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=4)
print(label_done + " " + dst, flush=True)
'''


def fab_steps(zip_path: str, eng: Engine, delete_zip: bool) -> list:
    tmp = str(Path(zip_path).with_suffix("")) + "-unpacked"
    steps = [Step(tr("fab.cleaning_temporary_folder"), ["rm", "-rf", tmp, tmp + "-built"])]
    steps += zip_steps(zip_path, tmp)
    steps.append(Step(tr("fab.installing_fab_plugin_into", eng.title),
                      [sys.executable, "-c", INSTALL_SCRIPT, tmp, eng.path,
                       tr("fab.archive_contains_only_sources_building"),
                       tr("fab.fab_plugin_installed"), tr("fab.fab_uplugin_not_found_archive")]))
    steps.append(Step(tr("fab.deleting_temporary_files"), ["rm", "-rf", tmp, tmp + "-built"] + ([zip_path] if delete_zip else [])))
    return steps
