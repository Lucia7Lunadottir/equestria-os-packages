"""
Backend for Equestria Save Point.

Only Btrfs is supported: snapshots are native CoW via btrfs-progs
(instant, atomic restore by swapping subvolumes).

Restic (ext4/xfs/…) and Timeshift backends were removed: backing up the
whole root before every pacman transaction made installs very slow, and
restoring files over a running system was unreliable.
"""

import os, subprocess, re, shlex
from datetime import datetime

# ── Data ──────────────────────────────────────────────────────────────────────

class SnapshotData:
    """Unified snapshot descriptor shared by all backends."""
    def __init__(self, num, date_str, snapshot_id, tags, comment, fs_id=None, protected=False):
        self.num         = num
        self.date_str    = date_str
        self.snapshot_id = snapshot_id   # ID used to restore
        self.tags        = tags          # single-char code for badge
        self.comment     = comment
        self.fs_id       = fs_id or snapshot_id  # YYYY-MM-DD_HH-MM-SS for screenshot lookup
        self.protected   = protected     # True = daily protected, cannot be deleted


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_root_fstype() -> str:
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "/":
                    return parts[2].lower()
    except OSError:
        pass
    return "unknown"


def _exists(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


def detect_backend() -> str:
    """Return 'btrfs', 'unsupported' (root is not Btrfs) or 'none' (no btrfs-progs)."""
    if detect_root_fstype() != "btrfs":
        return "unsupported"
    return "btrfs" if _exists("btrfs") else "none"


# ── Btrfs native backend ──────────────────────────────────────────────────────

BTRFS_SNAP_DIR   = "/.snapshots"
BTRFS_DAILY_DIR  = "/.snapshots/daily"


class BtrfsBackend:
    """
    Native Btrfs CoW snapshots using btrfs-progs.
    """

    def __init__(self, snap_dir: str = None):
        self.snap_dir  = snap_dir or BTRFS_SNAP_DIR
        self.daily_dir = os.path.join(self.snap_dir, "daily")

    def list_snapshots(self) -> tuple[list[SnapshotData], str]:
        if not os.path.isdir(self.snap_dir):
            return [], ""
        try:
            entries = sorted(os.listdir(self.snap_dir), reverse=True)
        except PermissionError:
            try:
                r = subprocess.run(
                    ["pkexec", "ls", self.snap_dir],
                    capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    return [], r.stderr.strip()
                entries = sorted(r.stdout.splitlines(), reverse=True)
            except Exception as e:
                return [], str(e)
        except Exception as e:
            return [], str(e)

        pat = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})$")
        result = []
        for i, name in enumerate(entries):
            if not pat.match(name):
                continue
            try:
                dt = datetime.strptime(name, "%Y-%m-%d_%H-%M-%S")
                date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                date_str = name
            result.append(SnapshotData(str(i), date_str, name, "S", "", fs_id=name))

        pat_daily = re.compile(r"^daily-(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})$")
        if os.path.isdir(self.daily_dir):
            try:
                daily_entries = sorted(os.listdir(self.daily_dir), reverse=True)
            except Exception:
                daily_entries = []
            for name in daily_entries:
                m = pat_daily.match(name)
                if not m:
                    continue
                ts = m.group(1)
                try:
                    dt       = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
                    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    date_str = ts
                snap_id = "daily/" + name
                result.append(SnapshotData(
                    str(len(result)), date_str, snap_id, "P", "",
                    fs_id=ts, protected=True))

        return result, ""

    def create_cmd(self) -> str:
        d = shlex.quote(self.snap_dir)
        return (
            f"mkdir -p {d} && chmod 755 {d} && "
            f"btrfs subvolume snapshot -r / {d}/$(date +%Y-%m-%d_%H-%M-%S)"
        )

    def restore_cmd(self, snap_id: str) -> str:
        # Вся работа — в rollback.py (та же логика, что у автоотката): копия точки встаёт
        # на место корня, старый корень остаётся как <subvol>_old_<время>, а сами точки
        # сохранения переезжают в новый корень, а не пропадают вместе со старым.
        script = os.path.join(os.path.dirname(os.path.realpath(__file__)), "rollback.py")
        return f"python3 {shlex.quote(script)} restore {shlex.quote(snap_id)}"

    def build_prune_cmd(self, snapshots: list, keep_last: int) -> str:
        to_delete = snapshots[max(0, keep_last - 1):]
        if not to_delete:
            return ""
        cmds = [
            f"btrfs subvolume delete {shlex.quote(os.path.join(self.snap_dir, s.snapshot_id))}"
            for s in to_delete
        ]
        return " && ".join(cmds)

    def delete_cmd(self, snap_id: str) -> str:
        if snap_id.startswith("daily/"):
            return "echo 'Protected daily snapshot cannot be deleted'"
        path = shlex.quote(os.path.join(self.snap_dir, snap_id))
        return f"btrfs subvolume delete {path}"

    def delete_multiple_cmd(self, snap_ids: list) -> str:
        paths = [
            shlex.quote(os.path.join(self.snap_dir, s))
            for s in snap_ids
            if not s.startswith("daily/")
        ]
        if not paths:
            return "echo 'Nothing to delete'"
        return "btrfs subvolume delete " + " ".join(paths)

    def get_repo_size(self) -> str:
        return ""

    def get_snapshot_size(self, snap_id: str) -> str:
        return ""

    def fstype_label(self) -> str:
        return "Btrfs CoW"
