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


def owning_package(filename: str):
    """Which Arch package ships a file with this exact name, per pacman's file database."""
    try:
        result = subprocess.run(["pacman", "-F", filename], capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line and not line[0].isspace() and "/" in line:
            return line.split("/", 1)[1].split()[0]
    return None


def resolve_dependencies(targets):
    """Best-effort: find missing .so files needed by newly installed ELF binaries
    and auto-install whichever Arch package provides each one. Never fatal —
    file extraction already succeeded regardless of what happens here."""
    try:
        needed = set()
        for path in targets:
            if os.path.isfile(path) and not os.path.islink(path):
                needed |= elf_needed_libs(path)
        if not needed:
            return

        missing = needed - cached_library_names()
        if not missing:
            log("All runtime dependencies already present.")
            return

        if not os.path.isdir(PACMAN_SYNC_DIR) or not any(
                f.endswith(".files") for f in os.listdir(PACMAN_SYNC_DIR)):
            log("Syncing pacman file database (one-time, may take a while)...")
            subprocess.run(["pacman", "-Fy"], capture_output=True)

        to_install, unresolved = set(), []
        for lib in sorted(missing):
            pkg = owning_package(lib)
            (to_install.add(pkg) if pkg else unresolved.append(lib))

        if to_install:
            log(f"Installing missing dependencies: {', '.join(sorted(to_install))}")
            subprocess.run(["pacman", "-S", "--needed", "--noconfirm", *sorted(to_install)])

        if unresolved:
            log(f"WARNING: no Arch package found for: {', '.join(unresolved)} — the app may not start.")
    except Exception as e:
        log(f"WARNING: dependency check failed ({e}), continuing anyway.")


def install_deb(path: str):
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

        log(f"Package: {pkg_name} {pkg_version}")

        member_list = run(["tar", "-taf", data_archive]).splitlines()
        targets = [normalize_member(m) for m in member_list if m.strip() and not m.strip().endswith("/")]

        log(f"Extracting {len(targets)} files...")
        run(["tar", "-xaf", data_archive, "-C", "/"])

    resolve_dependencies(targets)
    write_manifest(pkg_name, pkg_version, "deb", targets)
    log(f"Installed {pkg_name} {pkg_version} ({len(targets)} files)")


def install_rpm(path: str):
    filename = os.path.basename(path)
    m = re.match(r"^(.+)-([^-]+)-([^-]+)\.[^.]+\.rpm$", filename)
    pkg_name, pkg_version = (m.group(1), m.group(2)) if m else (filename, "0")

    log(f"Package: {pkg_name} {pkg_version}")

    member_list = run(["bsdtar", "-tf", path]).splitlines()
    targets = [normalize_member(m) for m in member_list if m.strip() and not m.strip().endswith("/")]

    log(f"Extracting {len(targets)} files...")
    run(["bsdtar", "-xpf", path, "-C", "/"])

    resolve_dependencies(targets)
    write_manifest(pkg_name, pkg_version, "rpm", targets)
    log(f"Installed {pkg_name} {pkg_version} ({len(targets)} files)")


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


def main():
    if len(sys.argv) < 2:
        print("usage: equestria-foreign-bridge install <file> | uninstall <name> | list", file=sys.stderr)
        return 1

    command = sys.argv[1]
    try:
        if command == "install" and len(sys.argv) == 3:
            path = sys.argv[2]
            if path.endswith(".deb"):
                install_deb(path)
            elif path.endswith(".rpm"):
                install_rpm(path)
            else:
                raise BridgeError(f"unsupported package type: {path}")
        elif command == "uninstall" and len(sys.argv) == 3:
            uninstall(sys.argv[2])
        elif command == "list":
            list_installed()
        else:
            print("usage: equestria-foreign-bridge install <file> | uninstall <name> | list", file=sys.stderr)
            return 1
    except BridgeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
