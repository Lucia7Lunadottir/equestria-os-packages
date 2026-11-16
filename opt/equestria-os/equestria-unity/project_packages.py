"""The UPM packages of a project, read from its files: no Editor has to be open.
Packages/manifest.json lists what the project asks for; Packages/packages-lock.json what Unity resolved."""
import json
import os
import re
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path

CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "equestria-unity"


@dataclass
class PackageEntry:
    identifier: str
    version: str
    source: str        # registry, builtin, git, local, embedded, local-tarball ("" when unknown)
    direct: bool       # asked for in the manifest, not only pulled in by another package
    title: str         # displayName from the package's own package.json, or the identifier
    description: str = ""


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class ProjectPackages:
    def __init__(self, project):
        self.project = Path(project)
        self.manifest_path = self.project / "Packages/manifest.json"

    def exists(self):
        return self.manifest_path.is_file()

    def title(self, identifier):
        """displayName from the package cache, the embedded copy or the Editor's built-in package; else the ID."""
        places = [self.project / "Packages" / identifier / "package.json",
                  *sorted((self.project / "Library/PackageCache").glob(f"{identifier}@*/package.json"))]
        for place in places:
            data = read_json(place)
            if data and isinstance(data.get("displayName"), str) and data["displayName"].strip():
                return data["displayName"].strip()
        return identifier

    def wanted(self):
        """identifier -> version asked for in manifest.json."""
        dependencies = (read_json(self.manifest_path) or {}).get("dependencies")
        return dependencies if isinstance(dependencies, dict) else {}

    def add(self, identifier, version):
        """Ask for a package in manifest.json; Unity installs it when the project is opened (or at once if it is).
        The file keeps its order and Unity's own formatting (two spaces)."""
        manifest = read_json(self.manifest_path)
        if manifest is None:
            raise ValueError(str(self.manifest_path))
        dependencies = manifest.setdefault("dependencies", {})
        dependencies[identifier] = version
        self.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def entries(self):
        manifest = read_json(self.manifest_path) or {}
        wanted = manifest.get("dependencies")
        wanted = wanted if isinstance(wanted, dict) else {}
        lock = (read_json(self.project / "Packages/packages-lock.json") or {}).get("dependencies")
        lock = lock if isinstance(lock, dict) else {}
        result = {}
        for identifier, info in lock.items():
            if isinstance(info, dict):
                result[identifier] = PackageEntry(identifier, str(info.get("version") or ""),
                                                  str(info.get("source") or ""),
                                                  identifier in wanted or info.get("depth") == 0, "")
        for identifier, version in wanted.items():
            if identifier not in result:   # asked for but not resolved yet (the Editor has not opened it since)
                result[identifier] = PackageEntry(identifier, str(version), "", True, "")
        for entry in result.values():
            entry.title = self.title(entry.identifier)
        return sorted(result.values(), key=lambda e: (not e.direct, e.title.casefold()))


def pretty_name(identifier):
    """com.unity.render-pipelines.universal -> Render Pipelines Universal (when the package has no displayName at hand)."""
    words = re.split(r"[.\-_]+", re.sub(r"^com\.unity\.", "", identifier))
    return " ".join(w.upper() if w in ("2d", "3d", "ui", "ai", "xr", "ar", "vr", "ecs") else w.capitalize() for w in words if w)


class EditorPackageCatalog:
    """The packages Unity's Package Manager lists under “Unity Registry” for one Editor version, with the version
    recommended for it. Read from the Editor's own files, so it works offline and without opening the Editor."""

    def __init__(self, editor, cache=None):
        self.root = Path(editor).parent / "Data/Resources/PackageManager"
        self.version = Path(editor).parents[1].name
        self.cache = Path(cache or CACHE) / f"packages-{self.version}.json"

    def shipped(self):
        """identifier -> package.json of packages the Editor carries: built in, or as .tgz archives."""
        found = {}
        for meta in (self.root / "BuiltInPackages").glob("*/package.json"):
            data = read_json(meta)
            if data:
                found[meta.parent.name] = data
        for archive in (self.root / "Editor").glob("*.tgz"):
            identifier = re.sub(r"-\d+(\.\d+)*(-[\w.]+)?$", "", archive.name.removesuffix(".tgz"))
            if identifier in found:
                continue
            try:
                with tarfile.open(archive, "r|gz") as tar:
                    for member in tar:
                        if member.name.removeprefix("./") == "package/package.json":
                            data = json.load(tar.extractfile(member))
                            if isinstance(data, dict):
                                found[identifier] = data
                            break
            except (OSError, tarfile.TarError, ValueError, EOFError):
                pass
        return found

    def entries(self):
        """Read once per Editor (names hide inside big .tgz archives) and kept in the cache folder after that."""
        stamp = self.stamp()
        cached = read_json(self.cache)
        if cached and cached.get("stamp") == stamp and isinstance(cached.get("entries"), list):
            try:
                return [PackageEntry(**entry) for entry in cached["entries"]]
            except TypeError:
                pass
        entries = self.read()
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(json.dumps({"stamp": stamp, "entries": [asdict(e) for e in entries]}), encoding="utf-8")
        except OSError:
            pass  # only slower next time
        return entries

    def stamp(self):
        try:
            return (self.root / "Editor/manifest.json").stat().st_mtime
        except OSError:
            return 0

    def read(self):
        listed = (read_json(self.root / "Editor/manifest.json") or {}).get("packages")
        if not isinstance(listed, dict):
            return []
        shipped = self.shipped()
        result = []
        for identifier, info in listed.items():
            if not isinstance(info, dict) or not info.get("isDiscoverable") or info.get("deprecated"):
                continue
            meta = shipped.get(identifier, {})
            title = meta.get("displayName") if isinstance(meta.get("displayName"), str) else ""
            description = meta.get("description") if isinstance(meta.get("description"), str) else ""
            result.append(PackageEntry(identifier, str(info.get("version") or meta.get("version") or ""), "registry",
                                       False, title.strip() or pretty_name(identifier), description.strip()))
        return sorted(result, key=lambda e: e.title.casefold())
