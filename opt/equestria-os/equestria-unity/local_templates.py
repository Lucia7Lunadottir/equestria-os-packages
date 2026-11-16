"""Project templates on disk: shipped with an Editor, downloaded by Unity Hub, or in a folder of the user's."""
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path

import unity_paths

SHORT_WORDS = ("2d", "3d", "vr", "ar", "urp", "hdrp", "xr")


@dataclass
class Template:
    title: str
    description: str
    path: Path | None        # None: downloaded by the Unity CLI when the project is created
    identifier: str = ""
    category: str = ""
    preview: str | bytes = ""


class TemplateArchive:
    """A template .tgz: its display name, description and preview picture, read without unpacking it."""

    def __init__(self, path):
        self.path = Path(path)

    def pretty_name(self):
        stem = re.sub(r"^com\.unity\.template\.", "", Path(self.path.name).stem)
        stem = re.sub(r"-\d+(\.\d+)*(-.*)?$", "", stem)
        words = [w.upper() if w.lower() in SHORT_WORDS else w.capitalize() for w in re.split(r"[-_.]+", stem) if w]
        return " ".join(words) or stem

    def read(self):
        """(displayName, description, preview bytes) from package/package.json and a thumbnail inside."""
        info, preview = {}, b""
        try:
            with tarfile.open(self.path, "r|gz") as tar:
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

    def template(self):
        title, description, preview = self.read()
        return Template(title or self.pretty_name(), description, self.path, preview=preview)


def templates(editor, custom_folder=None):
    """Templates shipped with the Editor plus the ones the Hub downloaded; a custom folder wins on equal names."""
    folders = [editor.parent / "Data/Resources/PackageManager/ProjectTemplates", unity_paths.HUB / "Templates"]
    if custom_folder:
        folders.insert(0, Path(custom_folder))
    archives = {}
    for folder in folders:
        for archive in sorted(folder.glob("*.tgz")):
            archives.setdefault(archive.name, archive)
    return sorted((TemplateArchive(path).template() for path in archives.values()), key=lambda t: t.title.casefold())
