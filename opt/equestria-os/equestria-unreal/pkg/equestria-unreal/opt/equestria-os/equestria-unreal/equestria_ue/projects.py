from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from equestria_ue.engines import read_install_ini, read_text


@dataclass
class Project:
    path: str
    name: str
    assoc: str = ""
    cpp: bool = False
    thumb: str = ""
    mtime: float = 0.0


SKIP_DIRS = {"Saved", "Intermediate", "Binaries", "DerivedDataCache", "Content", "Source", "Plugins",
             ".git", ".vs", "Build", "node_modules"}


def load_project(path: str) -> Project | None:
    try:
        d = json.loads(read_text(path))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    p = Path(path)
    thumb = p.parent / "Saved" / "AutoScreenshot.png"
    return Project(str(p), p.stem, str(d.get("EngineAssociation", "")), bool(d.get("Modules")) or (p.parent / "Source").is_dir(),
                   str(thumb) if thumb.exists() else "", p.stat().st_mtime)


def scan_projects(dirs: list, extra: list) -> list:
    found, seen = [], set()
    for d in dirs:
        base = Path(d).expanduser()
        if not base.is_dir():
            continue
        for root, subdirs, files in os.walk(base):
            if "Engine" in subdirs and "Setup.sh" in files:       # папка самого движка — пропускаем
                subdirs[:] = []
                continue
            if Path(root).relative_to(base).parts.__len__() >= 4:
                subdirs[:] = []
            ups = [f for f in files if f.endswith(".uproject")]
            if ups:
                subdirs[:] = [s for s in subdirs if s not in SKIP_DIRS]
            for f in ups:
                full = str(Path(root) / f)
                if full not in seen:
                    seen.add(full)
                    pr = load_project(full)
                    if pr:
                        found.append(pr)
    for full in extra:
        if full not in seen and Path(full).is_file():
            seen.add(full)
            pr = load_project(full)
            if pr:
                found.append(pr)
    return sorted(found, key=lambda p: -p.mtime)


def resolve_engine(pr: Project, engines: list):
    """Какой установленный движок соответствует EngineAssociation проекта."""
    a = pr.assoc.strip()
    if not a:
        return None
    if a.startswith("{"):
        ini = read_install_ini()
        path = next((v for k, v in ini.items() if k.upper() == a.upper()), "")
        for e in engines:
            if e.id.upper() == a.upper() or (path and e.path == path):
                return e
        return None
    m = re.match(r"(\d+)\.(\d+)", a)
    if not m:
        return None
    cands = [e for e in engines if e.version[:2] == (int(m.group(1)), int(m.group(2)))]
    return max(cands, key=lambda e: e.version, default=None)


def set_association(pr: Project, value: str) -> bool:
    try:
        raw = Path(pr.path).read_text(encoding="utf-8")
        d = json.loads(raw)
        shutil.copy2(pr.path, pr.path + ".bak")
        d["EngineAssociation"] = value
        Path(pr.path).write_text(json.dumps(d, indent="\t", ensure_ascii=False) + "\n", encoding="utf-8")
        pr.assoc = value
        return True
    except Exception:
        return False
