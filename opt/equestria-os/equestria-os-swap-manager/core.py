import os
import shutil
from dataclasses import dataclass, field


def detect_ntfs(path: str) -> bool:
    """Return True if path resides on an NTFS filesystem."""
    try:
        with open("/proc/mounts") as f:
            mounts = f.readlines()
    except OSError:
        return False

    best_prefix = ""
    best_fstype = ""
    for line in mounts:
        parts = line.split()
        if len(parts) < 3:
            continue
        mount_point = parts[1]
        fstype = parts[2]
        if path.startswith(mount_point) and len(mount_point) > len(best_prefix):
            best_prefix = mount_point
            best_fstype = fstype

    return best_fstype in ("ntfs", "ntfs-3g", "fuseblk")


def check_writable(path: str) -> bool:
    """Return True if path (or its first existing ancestor) is writable."""
    candidate = path
    while candidate and candidate != os.path.dirname(candidate):
        if os.path.exists(candidate):
            return os.access(candidate, os.W_OK)
        candidate = os.path.dirname(candidate)
    return False


@dataclass
class RelocateResult:
    source: str
    final_destination: str = ""
    symlink_created: bool = False
    error: str = ""


def relocate(sources: list, destination: str, create_symlink: bool) -> list:
    """Move each source to destination, optionally creating a symlink at the original path."""
    results = []
    os.makedirs(destination, exist_ok=True)

    for src in sources:
        src = src.rstrip("/")
        basename = os.path.basename(src)
        dest_path = os.path.join(destination, basename)
        result = RelocateResult(source=src, final_destination=dest_path)

        try:
            shutil.move(src, dest_path)
        except Exception as e:
            result.error = f"Move failed: {e}"
            results.append(result)
            continue

        if create_symlink:
            try:
                os.symlink(dest_path, src)  # target, link_name
                result.symlink_created = True
            except Exception as e:
                result.error = f"Moved OK but symlink failed: {e}"

        results.append(result)

    return results
