#!/usr/bin/env python3
"""Equestria OS foreign package bridge — installs .deb/.rpm without pacman or AUR tools.

Extracts files only; never runs embedded maintainer scripts/scriptlets.
Tracks installed files in its own manifest so packages can be cleanly removed.
"""
import json
import os
import posixpath
import re
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

MANIFEST_DIR = "/var/lib/equestria-installer/foreign"
PACMAN_SYNC_DIR = "/var/lib/pacman/sync"

# Real system library directories — a candidate package is only trusted to
# fix a missing .so if it ships the file directly here. Without this, a
# package that happens to bundle its own private copy of a common library
# somewhere under its own install prefix (e.g. "usr/lib/somenapp/libxml2.so.2")
# could be mistaken for the actual system dependency and pulled in instead —
# possibly a huge, unrelated download for a one-line library name match.
_SYSTEM_LIB_DIRS = ("usr/lib/", "usr/lib32/", "usr/lib64/")

_SIZE_UNITS = {"B": 1, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3, "TIB": 1024 ** 4}

PROTECTED_PREFIXES = (
    "/boot",
    "/etc/passwd", "/etc/shadow", "/etc/gshadow", "/etc/sudoers", "/etc/sudoers.d",
    "/etc/pacman.conf", "/etc/pacman.d",
    "/usr/bin/sudo", "/usr/bin/pkexec", "/usr/bin/su", "/usr/bin/pacman",
    "/usr/lib/systemd", "/var/lib/pacman",
)


class BridgeError(Exception):
    pass


def log(msg):
    print(msg, flush=True)


def normalize_member(name: str) -> str:
    """Resolve a tar/rpm member path to an absolute filesystem target, rejecting escapes."""
    name = name.lstrip("./")
    if name.startswith("/"):
        raise BridgeError(f"refusing absolute path in package: {name}")
    target = posixpath.normpath(posixpath.join("/", name))
    if target == "/" or not target.startswith("/"):
        raise BridgeError(f"refusing suspicious path in package: {name}")
    for prefix in PROTECTED_PREFIXES:
        if target == prefix or target.startswith(prefix.rstrip("/") + "/"):
            raise BridgeError(f"package attempts to modify protected system path: {target}")
    return target


def parse_ar(data: bytes) -> dict:
    if data[:8] != b"!<arch>\n":
        raise BridgeError("not a valid .deb (bad ar magic)")
    members = {}
    pos = 8
    n = len(data)
    while pos + 60 <= n:
        header = data[pos:pos + 60]
        name = header[0:16].decode("ascii", "replace").strip().rstrip("/")
        size = int(header[48:58].decode("ascii", "replace").strip())
        pos += 60
        members[name] = data[pos:pos + size]
        pos += size + (size % 2)
    return members


def run(cmd, **kwargs):
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise BridgeError(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout


def elf_needed_libs(path: str) -> set:
    """Read DT_NEEDED entries straight from the ELF dynamic section.

    Deliberately never runs the file (unlike `ldd`, whose man page warns that
    tracing an untrusted binary can execute arbitrary code from it) — this is
    a pure byte-level parse of the ELF64-LE header and program headers.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return set()

    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return set()  # not ELF, or not 64-bit little-endian (only class this OS targets)

    try:
        (_, _, _, _, e_phoff, _, _, _, e_phentsize, e_phnum, _, _, _
         ) = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    except struct.error:
        return set()

    load_segments = []
    dyn_offset = dyn_size = None
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if off + 56 > len(data):
            break
        p_type, _, p_offset, p_vaddr, _, p_filesz, _, _ = struct.unpack_from("<IIQQQQQQ", data, off)
        if p_type == 1:  # PT_LOAD
            load_segments.append((p_vaddr, p_filesz, p_offset))
        elif p_type == 2:  # PT_DYNAMIC
            dyn_offset, dyn_size = p_offset, p_filesz

    if dyn_offset is None:
        return set()  # statically linked — nothing to resolve

    needed_offsets = []
    strtab_vaddr = None
    for i in range(dyn_size // 16):
        off = dyn_offset + i * 16
        if off + 16 > len(data):
            break
        tag, val = struct.unpack_from("<QQ", data, off)
        if tag == 0:  # DT_NULL
            break
        elif tag == 1:  # DT_NEEDED
            needed_offsets.append(val)
        elif tag == 5:  # DT_STRTAB
            strtab_vaddr = val

    if strtab_vaddr is None:
        return set()

    strtab_file_offset = None
    for vaddr, filesz, offset in load_segments:
        if vaddr <= strtab_vaddr < vaddr + filesz:
            strtab_file_offset = offset + (strtab_vaddr - vaddr)
            break
    if strtab_file_offset is None:
        return set()

    names = set()
    for rel_off in needed_offsets:
        start = strtab_file_offset + rel_off
        end = data.find(b"\x00", start)
        if start < len(data) and end != -1:
            try:
                names.add(data[start:end].decode("ascii"))
            except UnicodeDecodeError:
                pass
    return names


def cached_library_names() -> set:
    """Shared libraries the dynamic linker can already resolve on this system."""
    try:
        output = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True).stdout
    except OSError:
        return set()
    return set(re.findall(r"^\s*(\S+)\s*\(", output, re.MULTILINE))


def file_db_ready() -> bool:
    return os.path.isdir(PACMAN_SYNC_DIR) and any(
        f.endswith(".files") for f in os.listdir(PACMAN_SYNC_DIR))


def owning_packages(filename: str):
    """Arch packages that ship `filename` directly inside a real system
    library directory (see _SYSTEM_LIB_DIRS) — one entry per candidate
    package, so an ambiguous match can be shown to the user instead of
    silently picking whichever one pacman happened to list first."""
    try:
        result = subprocess.run(["pacman", "-F", "--machinereadable", filename],
                                 capture_output=True, text=True)
    except OSError:
        return []
    if result.returncode != 0:
        return []

    seen = set()
    candidates = []
    for line in result.stdout.splitlines():
        fields = line.split("\x00")
        if len(fields) != 4:
            continue
        repo, pkg, version, filepath = fields
        if filepath not in (d + filename for d in _SYSTEM_LIB_DIRS):
            continue
        if pkg in seen:
            continue
        seen.add(pkg)
        candidates.append({"repo": repo, "pkg": pkg, "version": version})
    return candidates


def _parse_size(text: str):
    parts = text.split()
    if len(parts) != 2:
        return None
    try:
        value = float(parts[0])
    except ValueError:
        return None
    multiplier = _SIZE_UNITS.get(parts[1].upper())
    return int(value * multiplier) if multiplier else None


def package_download_size(pkg: str):
    """Download size in bytes for `pkg`, straight from `pacman -Si`.

    Forces LC_ALL=C so the "Download Size" label is parseable regardless
    of the system's configured locale (pacman's own output is translated).
    """
    try:
        result = subprocess.run(["pacman", "-Si", pkg], capture_output=True,
                                 text=True, env={**os.environ, "LC_ALL": "C"})
    except OSError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("Download Size"):
            return _parse_size(line.split(":", 1)[1].strip())
    return None


def build_dependency_plan(targets, extracted_root):
    """Inspect newly-extracted ELF binaries for missing shared libraries and
    look up which package(s) could supply each one — without installing
    anything. The caller (the installer GUI) shows this to the user for
    approval before a single package is downloaded; see apply_dependency_selection().
    """
    needed = set()
    for member_path in targets:
        local = os.path.join(extracted_root, member_path.lstrip("/"))
        if os.path.isfile(local) and not os.path.islink(local):
            needed |= elf_needed_libs(local)

    missing = sorted(needed - cached_library_names())
    plan = {"missing": {}, "unresolved": [], "file_db_stale": False}
    if not missing:
        return plan

    if not file_db_ready():
        plan["file_db_stale"] = True
        plan["unresolved"] = missing
        return plan

    for lib in missing:
        candidates = owning_packages(lib)
        if not candidates:
            plan["unresolved"].append(lib)
            continue
        for c in candidates:
            c["size"] = package_download_size(c["pkg"])
        plan["missing"][lib] = candidates
    return plan


def apply_dependency_selection(approved_deps):
    """Install exactly the dependency packages the user reviewed and ticked
    in the GUI's confirmation panel. Never queries or resolves anything
    itself — that already happened in build_dependency_plan(), shown to the
    user, and approved. Extraction has already succeeded regardless of what
    happens here."""
    if not approved_deps:
        return
    log(f"Installing approved dependencies: {', '.join(approved_deps)}")
    result = subprocess.run(["pacman", "-S", "--needed", "--noconfirm", *approved_deps],
                             capture_output=True, text=True)
    if result.returncode != 0:
        log(f"WARNING: failed to install some dependencies: {result.stderr.strip()}")


def _extract_deb(path: str, dest_dir: str):
    """Parse a .deb's control info and extract its data archive into
    dest_dir. Shared by the real install (dest_dir="/") and by planning
    (dest_dir=a throwaway temp dir, so nothing touches the real filesystem
    before the user has approved any dependency downloads)."""
    with open(path, "rb") as f:
        members = parse_ar(f.read())

    control_name = next((n for n in members if n.startswith("control.tar")), None)
    data_name = next((n for n in members if n.startswith("data.tar")), None)
    if not control_name or not data_name:
        raise BridgeError(".deb is missing control.tar or data.tar member")

    with tempfile.TemporaryDirectory(prefix="equestria-deb-") as tmp:
        control_archive = os.path.join(tmp, control_name)
        data_archive = os.path.join(tmp, data_name)
        control_dir = os.path.join(tmp, "control")
        os.makedirs(control_dir)

        with open(control_archive, "wb") as f:
            f.write(members[control_name])
        with open(data_archive, "wb") as f:
            f.write(members[data_name])

        run(["tar", "-xaf", control_archive, "-C", control_dir])

        pkg_name, pkg_version = "unknown", "0"
        control_file = os.path.join(control_dir, "control")
        if os.path.isfile(control_file):
            with open(control_file, "r", errors="replace") as f:
                text = f.read()
            m = re.search(r"^Package:\s*(\S+)", text, re.MULTILINE)
            if m:
                pkg_name = m.group(1)
            m = re.search(r"^Version:\s*(\S+)", text, re.MULTILINE)
            if m:
                pkg_version = m.group(1)

        member_list = run(["tar", "-taf", data_archive]).splitlines()
        targets = [normalize_member(m) for m in member_list if m.strip() and not m.strip().endswith("/")]

        run(["tar", "-xaf", data_archive, "-C", dest_dir])

    return pkg_name, pkg_version, targets


def _extract_rpm(path: str, dest_dir: str, preserve_perms: bool = True):
    filename = os.path.basename(path)
    m = re.match(r"^(.+)-([^-]+)-([^-]+)\.[^.]+\.rpm$", filename)
    pkg_name, pkg_version = (m.group(1), m.group(2)) if m else (filename, "0")

    member_list = run(["bsdtar", "-tf", path]).splitlines()
    targets = [normalize_member(m) for m in member_list if m.strip() and not m.strip().endswith("/")]

    flags = "-xpf" if preserve_perms else "-xf"
    run(["bsdtar", flags, path, "-C", dest_dir])

    return pkg_name, pkg_version, targets


def install_deb(path: str, approved_deps=None):
    pkg_name, pkg_version, targets = _extract_deb(path, "/")
    log(f"Package: {pkg_name} {pkg_version}")
    log(f"Extracted {len(targets)} files.")
    apply_dependency_selection(approved_deps)
    write_manifest(pkg_name, pkg_version, "deb", targets)
    log(f"Installed {pkg_name} {pkg_version} ({len(targets)} files)")


def install_rpm(path: str, approved_deps=None):
    pkg_name, pkg_version, targets = _extract_rpm(path, "/")
    log(f"Package: {pkg_name} {pkg_version}")
    log(f"Extracted {len(targets)} files.")
    apply_dependency_selection(approved_deps)
    write_manifest(pkg_name, pkg_version, "rpm", targets)
    log(f"Installed {pkg_name} {pkg_version} ({len(targets)} files)")


def plan_package(path: str):
    """Extract `path` into a scratch directory (never touching the real
    filesystem) and report its files plus any missing runtime dependencies
    and their candidate packages, as a single JSON line on stdout prefixed
    with "PLAN_JSON:". Called unprivileged, before any pkexec install step —
    nothing is downloaded or installed here."""
    with tempfile.TemporaryDirectory(prefix="equestria-plan-") as tmp:
        if path.endswith(".deb"):
            pkg_name, pkg_version, targets = _extract_deb(path, tmp)
        elif path.endswith(".rpm"):
            pkg_name, pkg_version, targets = _extract_rpm(path, tmp, preserve_perms=False)
        else:
            raise BridgeError(f"unsupported package type: {path}")

        log(f"Package: {pkg_name} {pkg_version} ({len(targets)} files)")
        plan = build_dependency_plan(targets, tmp)

    plan["name"] = pkg_name
    plan["version"] = pkg_version
    plan["file_count"] = len(targets)
    print("PLAN_JSON:" + json.dumps(plan), flush=True)


def write_manifest(name, version, fmt, files):
    os.makedirs(MANIFEST_DIR, exist_ok=True, mode=0o755)
    manifest = {
        "name": name,
        "version": version,
        "format": fmt,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "files": sorted(set(files)),
    }
    manifest_path = os.path.join(MANIFEST_DIR, f"{name}.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    update_app_database()

def update_app_database():
    subprocess.run(["kbuildsycoca6", "--noincremental"], capture_output=True, check=False)


def uninstall(name: str):
    manifest_path = os.path.join(MANIFEST_DIR, f"{name}.json")
    if not os.path.isfile(manifest_path):
        raise BridgeError(f"no manifest found for '{name}'")
    with open(manifest_path) as f:
        manifest = json.load(f)

    removed = 0
    for target in manifest["files"]:
        try:
            os.remove(target)
            removed += 1
        except FileNotFoundError:
            pass
        except IsADirectoryError:
            pass

    for target in sorted(manifest["files"], key=len, reverse=True):
        parent = os.path.dirname(target)
        try:
            os.rmdir(parent)
        except OSError:
            pass

    os.remove(manifest_path)
    log(f"Removed {name} ({removed} files)")


def list_installed():
    if not os.path.isdir(MANIFEST_DIR):
        return
    for entry in sorted(os.listdir(MANIFEST_DIR)):
        with open(os.path.join(MANIFEST_DIR, entry)) as f:
            manifest = json.load(f)
        log(f"{manifest['name']}\t{manifest['version']}\t{manifest['format']}\t{len(manifest['files'])} files")


USAGE = ("usage: equestria-foreign-bridge install <file> [approved,deps,...] "
         "| plan <file> | sync-file-db | uninstall <name> | list")


def main():
    if len(sys.argv) < 2:
        print(USAGE, file=sys.stderr)
        return 1

    command = sys.argv[1]
    try:
        if command == "install" and len(sys.argv) in (3, 4):
            path = sys.argv[2]
            approved_deps = [d for d in sys.argv[3].split(",") if d] if len(sys.argv) == 4 else []
            if path.endswith(".deb"):
                install_deb(path, approved_deps)
            elif path.endswith(".rpm"):
                install_rpm(path, approved_deps)
            else:
                raise BridgeError(f"unsupported package type: {path}")
        elif command == "plan" and len(sys.argv) == 3:
            plan_package(sys.argv[2])
        elif command == "sync-file-db":
            subprocess.run(["pacman", "-Fy"], capture_output=True)
            log("File database synced.")
        elif command == "uninstall" and len(sys.argv) == 3:
            uninstall(sys.argv[2])
        elif command == "list":
            list_installed()
        else:
            print(USAGE, file=sys.stderr)
            return 1
    except BridgeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
