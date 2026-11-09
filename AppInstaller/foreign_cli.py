"""Обновление программ DEB/RPM без окна — для Software Center и терминала.

    equestria-installer --list-foreign-updates     JSON-строки: {"name", "installed", "latest"}
    equestria-installer --update-foreign [имя ...]  обновить все (или указанные) программы

Шаги те же, что в мастере: скачать с сайта производителя, сверить SHA256, план
зависимостей (foreign_bridge.py plan), установка через pkexec. Недостающие
библиотеки ставятся по первому кандидату — как флажки по умолчанию в мастере.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import sources
from foreign_apps import InstalledPackage, check_updates
from ui_common import BRIDGE, CACHE_DIR, tr


def pending_updates() -> list[InstalledPackage]:
    packages = InstalledPackage.load_all()
    check_updates(packages)
    return [p for p in packages if p.has_update]


def list_updates() -> int:
    for p in pending_updates():
        print(json.dumps({"name": p.name, "installed": p.display_version, "latest": p.latest.version},
                         ensure_ascii=False), flush=True)
    return 0


def _plan_deps(path: str) -> list[str]:
    out = subprocess.run([sys.executable, BRIDGE, "plan", path], capture_output=True, text=True).stdout
    plan = next((json.loads(l[len("PLAN_JSON:"):]) for l in out.splitlines() if l.startswith("PLAN_JSON:")), {})
    for lib in plan.get("unresolved", []):
        print(tr("common.no_package_found_app_may", lib), flush=True)
    return list(dict.fromkeys(c[0]["pkg"] for c in plan.get("missing", {}).values() if c))


def update(names: list[str]) -> int:
    todo = [p for p in pending_updates() if not names or p.name in names]
    if not todo:
        print(tr("common.all_apps_up_date"), flush=True)
        return 0
    failed = 0
    for p in todo:
        print(f"-- {p.name}: {p.display_version} → {p.latest.version}", flush=True)
        try:
            path = sources.download(p.latest, Path(CACHE_DIR) / "updates")
        except OSError as e:
            print(tr("common.could_not_download", e), flush=True)
            failed += 1
            continue
        args = ["pkexec", sys.executable, BRIDGE, "install", str(path)]
        deps = _plan_deps(str(path))
        if deps:
            args.append(",".join(deps))
        code = subprocess.run(args).returncode
        os.remove(path)
        print(tr("common.installation_completed_successfully") if code == 0 else tr("common.installation_error_code", code), flush=True)
        failed += code != 0
    if any(True for _ in todo) and subprocess.run(["which", "kbuildsycoca6"], capture_output=True).returncode == 0:
        subprocess.Popen(["kbuildsycoca6", "--noincremental"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 1 if failed else 0


def main(argv: list[str]) -> int | None:
    """None — это не команда без окна, нужно открыть мастер."""
    if argv and argv[0] == "--list-foreign-updates":
        return list_updates()
    if argv and argv[0] == "--update-foreign":
        return update(argv[1:])
    return None
