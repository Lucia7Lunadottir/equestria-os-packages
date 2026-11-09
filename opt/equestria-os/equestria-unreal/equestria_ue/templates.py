from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from equestria_ue.engines import Engine, read_text
from equestria_ue.kit import tr
from equestria_ue.projects import load_project, set_association


@dataclass
class Template:
    key: str
    name: str
    path: Path
    image: str
    cpp: bool
    builtin: str = ""


TEXT_EXT = {".ini", ".uproject", ".cs", ".h", ".cpp", ".json", ".txt", ".md", ".uplugin"}


def read_templates(eng: Engine) -> list:
    out, seen = [], set()
    for base in (Path(eng.path) / "Templates", Path(eng.path) / "Engine" / "Templates"):
        if not base.is_dir():
            continue
        for t in sorted(base.iterdir()):
            if not t.is_dir() or t.name in seen or not ((t / "TemplateDefs.ini").exists() or any(t.glob("*.uproject"))):
                continue
            seen.add(t.name)
            defs = read_text(t / "TemplateDefs.ini")
            m = re.search(r'LocalizedDisplayNames=\(Language="en"[^)]*?Text="([^"]+)"', defs) or \
                re.search(r'LocalizedDisplayNames=\([^)]*?Text="([^"]+)"', defs)
            imgs = sorted((t / "Media").glob("*.png")) + sorted((t / "Media").glob("*.jpg")) + sorted(t.glob("*.png"))
            out.append(Template(t.name, m.group(1) if m else t.name.replace("TP_", "").replace("_", " "), t,
                                str(imgs[0]) if imgs else "", (t / "Source").is_dir()))
    return out + [Template(k, tr(n), Path(""), "", cpp, k) for k, n, cpp in BUILTIN]


# имена переводятся при чтении (tr в read_templates) — язык можно сменить на лету
BUILTIN = [("blank_bp", "templates.blank_project_blueprint", False),
           ("blank_cpp", "templates.blank_project_c", True),
           ("light", "templates.lightweight_weak_gpus_gtx_10xx", False),
           ("rt", "Ray Tracing + Lumen (RTX)", False)]
BUILTIN_INI = {
    "blank_bp": "",
    "blank_cpp": "",
    "light": """[/Script/Engine.RendererSettings]
r.Nanite.ProjectEnabled=False
r.DynamicGlobalIlluminationMethod=0
r.ReflectionMethod=2
r.Shadow.Virtual.Enable=0
r.AntiAliasingMethod=2
r.DefaultFeature.AutoExposure=False
r.DefaultFeature.MotionBlur=False
""",
    "rt": """[/Script/Engine.RendererSettings]
r.RayTracing=True
r.Lumen.HardwareRayTracing=True
r.DynamicGlobalIlluminationMethod=1
r.ReflectionMethod=1
r.GenerateMeshDistanceFields=True
r.SkinCache.CompileShaders=True
r.Shadow.Virtual.Enable=1
""",
}


def create_builtin(tp: Template, parent: str, name: str, eng: Engine) -> str:
    dest = Path(parent) / name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "Content").mkdir(exist_ok=True)
    (dest / "Config").mkdir(exist_ok=True)
    proj = {"FileVersion": 3, "EngineAssociation": f"{eng.version[0]}.{eng.version[1]}", "Category": "", "Description": ""}
    ini = BUILTIN_INI.get(tp.key, "")
    (dest / "Config" / "DefaultEngine.ini").write_text(ini, encoding="utf-8")
    if tp.cpp:
        proj["Modules"] = [{"Name": name, "Type": "Runtime", "LoadingPhase": "Default"}]
        src = dest / "Source"
        (src / name).mkdir(parents=True, exist_ok=True)
        for kind, typ in (("", "Game"), ("Editor", "Editor")):
            (src / f"{name}{kind}.Target.cs").write_text(
                "using UnrealBuildTool;\nusing System.Collections.Generic;\n\n"
                f"public class {name}{kind}Target : TargetRules\n{{\n"
                f"\tpublic {name}{kind}Target(TargetInfo Target) : base(Target)\n\t{{\n"
                f"\t\tType = TargetType.{typ};\n"
                "\t\tDefaultBuildSettings = BuildSettingsVersion.Latest;\n"
                "\t\tIncludeOrderVersion = EngineIncludeOrderVersion.Latest;\n"
                f"\t\tExtraModuleNames.Add(\"{name}\");\n\t}}\n}}\n", encoding="utf-8")
        (src / name / f"{name}.Build.cs").write_text(
            "using UnrealBuildTool;\n\n"
            f"public class {name} : ModuleRules\n{{\n"
            f"\tpublic {name}(ReadOnlyTargetRules Target) : base(Target)\n\t{{\n"
            "\t\tPCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;\n"
            "\t\tPublicDependencyModuleNames.AddRange(new string[] { \"Core\", \"CoreUObject\", \"Engine\", "
            "\"InputCore\", \"EnhancedInput\" });\n\t}\n}\n", encoding="utf-8")
        (src / name / f"{name}.h").write_text('#pragma once\n\n#include "CoreMinimal.h"\n', encoding="utf-8")
        (src / name / f"{name}.cpp").write_text(
            f'#include "{name}.h"\n#include "Modules/ModuleManager.h"\n\n'
            f'IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, {name}, "{name}");\n', encoding="utf-8")
    up = dest / f"{name}.uproject"
    up.write_text(json.dumps(proj, indent="\t"), encoding="utf-8")
    return str(up)


def create_project(tp: Template, parent: str, name: str, eng: Engine) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        raise ValueError(tr("templates.project_name_latin_letters_digits"))
    dest = Path(parent) / name
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(tr("templates.folder_already_exists_not_empty", dest))
    if tp.builtin:
        return create_builtin(tp, parent, name, eng)
    defs = read_text(tp.path / "TemplateDefs.ini")
    skip_dirs = {"media", "binaries", "intermediate", "saved", "deriveddatacache"} | \
        {x.lower() for x in re.findall(r'FoldersToIgnore="([^"]+)"', defs)}
    skip_files = {"templatedefs.ini", "manifest.json"} | {x.lower() for x in re.findall(r'FilesToIgnore="([^"]+)"', defs)}
    olds = {tp.key} | {u.stem for u in tp.path.glob("*.uproject")}

    def ren(s: str) -> str:
        for o in olds:
            s = s.replace(o, name)
        return s

    for root, dirs, files in os.walk(tp.path):
        dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
        rel = Path(root).relative_to(tp.path)
        out = dest / Path(*[ren(x) for x in rel.parts]) if rel.parts else dest
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.lower() in skip_files:
                continue
            src, dst = Path(root) / f, out / ren(f)
            if src.suffix.lower() in TEXT_EXT:
                txt = src.read_text(encoding="utf-8", errors="ignore")
                for o in olds:
                    txt = txt.replace(o.upper() + "_API", name.upper() + "_API").replace(o, name)
                dst.write_text(txt, encoding="utf-8")
            else:
                shutil.copy2(src, dst)
    ups = list((dest).glob("*.uproject"))
    if not ups:
        raise RuntimeError(tr("templates.no_uproject_found_template"))
    pr = load_project(str(ups[0]))
    if pr:
        set_association(pr, f"{eng.version[0]}.{eng.version[1]}")
    return str(ups[0])
