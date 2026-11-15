"""Read local Unity projects, templates and Editor installations without starting the Hub."""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

HUB = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "unityhub"
DEFAULT_ROOT = Path.home() / "Unity/Hub/Editor"
VERSION = re.compile(r"^m_EditorVersion:\s*(\S+)", re.MULTILINE)
DEFAULT_DEPTH = 3
# Folders that never contain a project of their own: skipping them keeps the scan fast.
IGNORED = {"library", "temp", "logs", "obj", "build", "builds", "node_modules", "usersettings",
           "packages", "assets", "projectsettings", "__pycache__", "venv", "site-packages"}


@dataclass
class Project:
    path: Path
    version: str
    modified: float

    @property
    def name(self):
        return self.path.name


@dataclass
class Template:
    title: str
    description: str
    path: Path | None
    identifier: str = ""
    category: str = ""
    preview: str | bytes = ""


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def project_version(path):
    try:
        match = VERSION.search((path / "ProjectSettings/ProjectVersion.txt").read_text())
    except (OSError, UnicodeError):
        return ""
    return match.group(1) if match else ""


# ---- where to look for projects -------------------------------------------------------------

def default_scan_dirs():
    home = Path.home()
    names = ("Unity", "UnityProjects", "Unity Projects", "Projects", "Documents/Unity Projects",
             "Documents/UnityProjects")
    return [str(home / name) for name in names if (home / name).is_dir()]


def scan_dirs(settings):
    """Folders searched for projects. Until the user edits the list, existing common folders are used."""
    chosen = settings.get("scan_dirs")
    return list(chosen) if isinstance(chosen, list) else default_scan_dirs()


def find_projects(roots, depth=DEFAULT_DEPTH, limit=500):
    """Find folders that contain ProjectSettings/ProjectVersion.txt inside the roots."""
    found = []
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        base = len(root.parts)
        for current, dirs, _ in os.walk(root):
            where = Path(current)
            if (where / "ProjectSettings/ProjectVersion.txt").is_file():
                found.append(where)
                dirs[:] = []
                if len(found) >= limit:
                    return found
                continue
            if len(where.parts) - base >= depth:
                dirs[:] = []
            else:
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in IGNORED)
    return found


def modified_time(path, hub_record=None):
    if isinstance(hub_record, dict):
        stamp = hub_record.get("lastModified")
        if isinstance(stamp, (int, float)) and stamp > 0:
            return stamp / 1000 if stamp > 1e11 else float(stamp)
    best = 0.0
    for name in ("Assets", "ProjectSettings/ProjectVersion.txt", "ProjectSettings"):
        try:
            best = max(best, (path / name).stat().st_mtime)
        except OSError:
            pass
    return best


def collect(settings):
    """Every known project: found in search folders, remembered from the Hub, or added by hand."""
    records = read_json(HUB / "projects-v1.json", {})
    records = records.get("data", {}) if isinstance(records, dict) else {}
    if not isinstance(records, dict):
        records = {}
    depth = settings.get("scan_depth")
    paths = {str(p) for p in find_projects(scan_dirs(settings), depth if isinstance(depth, int) else DEFAULT_DEPTH)}
    paths.update(records)
    paths.update(settings.get("projects", []))
    hidden = set(settings.get("hidden", []))
    result = []
    for text in paths - hidden:
        path = Path(text)
        if path.is_dir():
            result.append(Project(path, project_version(path), modified_time(path, records.get(text))))
    return sorted(result, key=lambda p: (p.name.casefold(), str(p.path)))


# ---- editors ---------------------------------------------------------------------------------

def editor_roots(settings):
    secondary = read_json(HUB / "secondaryInstallPath.json", "")
    return [Path(p) for p in (secondary, settings.get("editor_root"), DEFAULT_ROOT)
            if isinstance(p, (str, Path)) and p]


def editors(settings):
    result = {}
    for root in reversed(editor_roots(settings)):
        for exe in root.glob("*/Editor/Unity"):
            if exe.is_file() and os.access(exe, os.X_OK):
                result[exe.parents[1].name] = exe
    for version, path in settings.get("editors", {}).items():
        exe = Path(path)
        if exe.is_file() and os.access(exe, os.X_OK):
            result[version] = exe
    return result


def migrate_editor_profiles(store):
    """Older versions had one global X11 switch; it now lives in each editor's profile."""
    enabled = store.take_legacy("x11")
    if enabled:
        profiles = store.get("editor_profiles")
        for exe in editors(store.snapshot()).values():
            profiles.setdefault(str(exe.resolve()), {}).setdefault("x11", True)
        store.set("editor_profiles", profiles)


def executable(name):
    found = shutil.which(name)
    if not found:
        candidate = Path.home() / ".local/bin" / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            found = str(candidate)
    return found


# ---- templates -------------------------------------------------------------------------------

def _pretty(stem):
    stem = re.sub(r"^com\.unity\.template\.", "", stem)
    stem = re.sub(r"-\d+(\.\d+)*(-.*)?$", "", stem)
    words = [w.upper() if w.lower() in ("2d", "3d", "vr", "ar", "urp", "hdrp", "xr") else w.capitalize()
             for w in re.split(r"[-_.]+", stem) if w]
    return " ".join(words) or stem


def _package_info(archive):
    """displayName and description from package/package.json inside a template .tgz."""
    info, preview = {}, b""
    try:
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                path = member.name.removeprefix("./")
                if path == "package/package.json" and member.size < 1024 * 1024:
                    meta = json.load(tar.extractfile(member))
                    if isinstance(meta, dict):
                        info = meta
                elif (path.startswith("package/ProjectData~/Assets/Welcome/") or
                      Path(path).stem.casefold() in ("thumbnail", "preview")):
                    if path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and member.size < 4 * 1024 * 1024:
                        preview = tar.extractfile(member).read()
                if info and preview:
                    break
    except (OSError, tarfile.TarError, ValueError, EOFError):
        pass
    return str(info.get("displayName") or ""), str(info.get("description") or ""), preview


def templates(editor, custom_folder=None):
    """Templates shipped with the Editor plus the ones the Hub downloaded."""
    folders = [editor.parent / "Data/Resources/PackageManager/ProjectTemplates", HUB / "Templates"]
    if custom_folder:
        folders.insert(0, Path(custom_folder))
    archives = {}
    for folder in folders:
        for archive in sorted(folder.glob("*.tgz")):
            archives.setdefault(archive.name, archive)
    found = []
    for name, archive in archives.items():
        title, description, preview = _package_info(archive)
        found.append(Template(title or _pretty(Path(name).stem), description, archive, preview=preview))
    return sorted(found, key=lambda t: t.title.casefold())


# ---- launching -------------------------------------------------------------------------------

def free_name(parent, base="My project"):
    parent = Path(parent)
    if not (parent / base).exists():
        return base
    for number in range(2, 1000):
        if not (parent / f"{base} {number}").exists():
            return f"{base} {number}"
    return base


def bad_name(name):
    return (not name or name in (".", "..") or Path(name).name != name or name.startswith("-")
            or any(ch in name for ch in '<>:"|?*\0'))


def launch(editor, project, settings, *, create=False, template=None):
    env = os.environ.copy()
    profile = settings.get("editor_profiles", {}).get(str(Path(editor).resolve()), {})
    if profile.get("x11"):
        if not env.get("DISPLAY"):
            raise ValueError("DISPLAY is unavailable (X11 / XWayland).")
        env["GDK_BACKEND"] = "x11"
        env.pop("WAYLAND_DISPLAY", None)
    args = [str(editor), "-createProject" if create else "-projectPath", str(project)]
    if template:
        args.extend(["-cloneFromTemplate", str(template)])
    renderer = settings.get("renderer")
    if renderer in ("-force-vulkan", "-force-glcore"):
        args.append(renderer)
    project_args = settings.get("project_arguments", {}).get(str(Path(project).resolve()), "")
    for arguments in (settings.get("arguments", ""), profile.get("arguments", ""), project_args):
        args.extend(shlex.split(arguments))
    if create:
        Path(project).parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(args, env=env, cwd=project.parent if create else project, start_new_session=True)


def ago_parts(stamp, now=None):
    """(unit, count) for a relative time label, or ('date', 'YYYY-MM-DD')."""
    if not stamp:
        return "none", 0
    seconds = (now or time.time()) - stamp
    if seconds < 60:
        return "now", 0
    if seconds < 3600:
        return "min", int(seconds // 60)
    if seconds < 86400:
        return "hour", int(seconds // 3600)
    if seconds < 30 * 86400:
        return "day", int(seconds // 86400)
    return "date", time.strftime("%Y-%m-%d", time.localtime(stamp))


def seed(text):
    return int(hashlib.md5(text.encode()).hexdigest()[:6], 16)
