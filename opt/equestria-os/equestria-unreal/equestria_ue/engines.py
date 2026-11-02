from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass
from pathlib import Path

from equestria_ue.paths import INSTALL_INI


def read_text(p) -> str:
    try:
        return Path(p).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


@dataclass
class Engine:
    id: str
    path: str
    version: tuple = (0, 0, 0)
    branch: str = ""
    editor: str = ""
    built: bool = False
    git: bool = False

    @property
    def ver(self) -> str:
        return ".".join(map(str, self.version)) if self.version[0] else "?"

    @property
    def short(self) -> str:
        return f"{self.version[0]}.{self.version[1]}"

    @property
    def title(self) -> str:
        return f"Unreal Engine {self.ver}"

    @property
    def ue4(self) -> bool:
        return self.version[0] == 4


def inspect_engine(entry: dict) -> Engine | None:
    root = Path(entry["path"])
    if not (root / "Engine").is_dir():
        return None
    e = Engine(entry["id"], str(root))
    try:
        d = json.loads(read_text(root / "Engine/Build/Build.version"))
        e.version = (int(d["MajorVersion"]), int(d["MinorVersion"]), int(d["PatchVersion"]))
        e.branch = d.get("BranchName", "")
    except Exception:
        pass
    for name in ("UnrealEditor", "UE4Editor"):
        p = root / "Engine/Binaries/Linux" / name
        if p.exists():
            e.editor = str(p)
            break
    e.built = bool(e.editor) and os.access(e.editor, os.X_OK)
    e.git = (root / ".git").exists()
    return e


def find_engine_root(base: str) -> str:
    """Папка с Engine/Binaries внутри распакованного архива (до 3 уровней)."""
    b = Path(base)
    for depth in range(4):
        for p in b.glob("/".join(["*"] * depth) + ("/" if depth else "") + "Engine/Build"):
            return str(p.parent.parent)
    return ""


def sync_install_ini(engines: list) -> None:
    """Прописывает движки в Epic-овский Install.ini — так их видят UnrealVersionSelector и другие инструменты."""
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str
    try:
        cp.read(INSTALL_INI, encoding="utf-8")
        if not cp.has_section("Installations"):
            cp.add_section("Installations")
        ours = {e.id for e in engines}
        for k in list(cp["Installations"]):
            if k.startswith("{") and k not in ours and not Path(cp["Installations"][k]).is_dir():
                cp.remove_option("Installations", k)
        for e in engines:
            cp["Installations"][e.id] = e.path
        INSTALL_INI.parent.mkdir(parents=True, exist_ok=True)
        with open(INSTALL_INI, "w", encoding="utf-8") as f:
            cp.write(f)
    except Exception:
        pass


def read_install_ini() -> dict:
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str
    try:
        cp.read(INSTALL_INI, encoding="utf-8")
        return dict(cp["Installations"]) if cp.has_section("Installations") else {}
    except Exception:
        return {}
