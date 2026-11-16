"""Find Unity projects on disk: in the search folders, in Unity Hub's list and the ones added by hand."""
import os
import re
from dataclasses import dataclass
from pathlib import Path

import unity_paths
from git_info import read_git_with_status

VERSION = re.compile(r"^m_EditorVersion:\s*(\S+)", re.MULTILINE)
DEFAULT_DEPTH = 3
# Folders that never contain a project of their own: skipping them keeps the scan fast.
IGNORED = {"library", "temp", "logs", "obj", "build", "builds", "node_modules", "usersettings",
           "packages", "assets", "projectsettings", "__pycache__", "venv", "site-packages"}
COMMON_FOLDERS = ("Unity", "UnityProjects", "Unity Projects", "Projects", "Documents/Unity Projects",
                  "Documents/UnityProjects")


@dataclass
class Project:
    path: Path
    version: str
    modified: float
    git: object = None   # GitInfo of the repository the project is in, None outside Git

    @property
    def name(self):
        return self.path.name


def project_version(path):
    """The Editor version a project was saved with, or "" if the folder is not a Unity project."""
    try:
        match = VERSION.search((Path(path) / "ProjectSettings/ProjectVersion.txt").read_text())
    except (OSError, UnicodeError):
        return ""
    return match.group(1) if match else ""


def scan_dirs(settings):
    """Folders searched for projects. Until the user edits the list, existing common folders are used."""
    chosen = settings.get("scan_dirs")
    if isinstance(chosen, list):
        return list(chosen)
    home = Path.home()
    return [str(home / name) for name in COMMON_FOLDERS if (home / name).is_dir()]


class ProjectScanner:
    """One scan with a snapshot of the settings; safe to run off the interface thread."""

    def __init__(self, settings, limit=500):
        self.roots = scan_dirs(settings)
        depth = settings.get("scan_depth")
        self.depth = depth if isinstance(depth, int) else DEFAULT_DEPTH
        self.manual = settings.get("projects", [])
        self.hidden = set(settings.get("hidden", []))
        self.limit = limit

    def find(self):
        """Folders that contain ProjectSettings/ProjectVersion.txt inside the roots."""
        found = []
        for root in self.roots:
            root = Path(root).expanduser()
            if not root.is_dir():
                continue
            base = len(root.parts)
            for current, dirs, _ in os.walk(root):
                where = Path(current)
                if (where / "ProjectSettings/ProjectVersion.txt").is_file():
                    found.append(where)
                    dirs[:] = []
                    if len(found) >= self.limit:
                        return found
                    continue
                if len(where.parts) - base >= self.depth:
                    dirs[:] = []
                else:
                    dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in IGNORED)
        return found

    @staticmethod
    def hub_records():
        records = unity_paths.read_json(unity_paths.HUB / "projects-v1.json", {})
        records = records.get("data", {}) if isinstance(records, dict) else {}
        return records if isinstance(records, dict) else {}

    @staticmethod
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

    def collect(self):
        """Every known project: found in search folders, remembered from the Hub, or added by hand."""
        records = self.hub_records()
        paths = {str(p) for p in self.find()}
        paths.update(records)
        paths.update(self.manual)
        result = []
        repositories = {}   # several projects can live in one repository: its status is read once
        for text in paths - self.hidden:
            path = Path(text)
            if path.is_dir():
                result.append(Project(path, project_version(path), self.modified_time(path, records.get(text)),
                                      read_git_with_status(path, repositories)))
        return sorted(result, key=lambda p: (p.name.casefold(), str(p.path)))
