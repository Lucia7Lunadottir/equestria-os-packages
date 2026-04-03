"""
Backend abstraction for Equestria Save Point.

Selection strategy:
  Btrfs  → BtrfsBackend  (native CoW via btrfs-progs, instant, zero extra space)
  Others → Restic         (chunked dedup + compression, best for ext4/xfs/etc.)
  Fallback: Timeshift     (rsync mode, if installed)
"""

import os, subprocess, json, re, shlex
from datetime import datetime

RESTIC_DIR  = "/var/lib/equestria-save-point"
RESTIC_REPO = f"{RESTIC_DIR}/restic-repo"
RESTIC_KEY  = f"{RESTIC_DIR}/repo.key"

RESTIC_EXCLUDES = [
    # Virtual/runtime — never needed
    "/proc", "/sys", "/dev", "/run", "/tmp", "/var/run",

    # Large caches — waste of space
    "/var/cache/pacman/pkg",
    "/var/cache/apt",
    "/var/tmp",
    "/root/.cache",

    # External/removable — not part of this system
    "/mnt", "/media", "/lost+found",

    # Repo itself — would cause infinite recursion
    RESTIC_DIR,

    # User home directories — personal files are NOT a system save point.
    # Back up /home separately with a dedicated backup tool.
    "/home",

    # Large game/app data
    "/root/.local/share/Steam",
    "/opt/steam",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(size_bytes: int) -> str:
    """Format bytes as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _dir_size(path: str) -> int:
    """Recursively sum file sizes under path (skips symlinks & unreadable)."""
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for fname in files:
                fpath = os.path.join(root, fname)
                if not os.path.islink(fpath):
                    try:
                        total += os.path.getsize(fpath)
                    except OSError:
                        pass
    except OSError:
        pass
    return total


# ── Data ──────────────────────────────────────────────────────────────────────

class SnapshotData:
    """Unified snapshot descriptor shared by all backends."""
    def __init__(self, num, date_str, snapshot_id, tags, comment, fs_id=None):
        self.num         = num
        self.date_str    = date_str
        self.snapshot_id = snapshot_id   # ID used to restore
        self.tags        = tags          # single-char code for badge
        self.comment     = comment
        self.fs_id       = fs_id or snapshot_id  # YYYY-MM-DD_HH-MM-SS for screenshot lookup


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
    """Return 'btrfs', 'restic', 'timeshift', or 'none'."""
    fs       = detect_root_fstype()
    have_bt  = _exists("btrfs")
    have_rs  = _exists("restic")
    have_ts  = _exists("timeshift")

    if fs == "btrfs" and have_bt:
        return "btrfs"       # Native CoW: instant + zero overhead, no extra dep
    if have_rs:
        return "restic"      # Best for ext4/xfs/f2fs/…
    if have_ts:
        return "timeshift"   # Rsync fallback
    return "none"


# ── Timeshift backend ─────────────────────────────────────────────────────────

class TimeshiftBackend:
    """Wraps timeshift CLI (handles both Btrfs CoW and rsync modes)."""

    def list_snapshots(self) -> tuple[list[SnapshotData], str]:
        try:
            r = subprocess.run(["timeshift", "--list"],
                               capture_output=True, text=True, timeout=30)
            snaps = _parse_timeshift(r.stdout)
            if not snaps:
                r2 = subprocess.run(["pkexec", "timeshift", "--list"],
                                    capture_output=True, text=True, timeout=30)
                if r2.returncode == 0:
                    snaps = _parse_timeshift(r2.stdout)
                else:
                    return [], (r2.stderr or r.stderr).strip()
            return snaps, ""
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                return [], "err.timeshift_not_found"
            if isinstance(e, subprocess.TimeoutExpired):
                return [], "err.timeout"
            return [], str(e)

    def create_cmd(self) -> str:
        return "timeshift --create --comments 'User Point'"

    def restore_cmd(self, snap_id: str) -> str:
        return f"timeshift --restore --snapshot {shlex.quote(snap_id)}"

    def build_prune_cmd(self, snapshots: list, keep_last: int) -> str:
        """
        Generate deletion commands for snapshots beyond keep_last.
        snapshots is sorted newest-first; after the new snapshot is created
        there will be len(snapshots)+1 total, so we keep keep_last-1 of the
        existing ones and delete the rest.
        """
        to_delete = snapshots[max(0, keep_last - 1):]
        if not to_delete:
            return ""
        cmds = [
            f"timeshift --delete --snapshot {shlex.quote(s.snapshot_id)}"
            for s in to_delete
        ]
        return " && ".join(cmds)

    def get_repo_size(self) -> str:
        for path in ["/timeshift/snapshots", "/timeshift"]:
            if os.path.isdir(path):
                size = _dir_size(path)
                if size > 0:
                    return _fmt_size(size)
        return ""

    def get_snapshot_size(self, snap_id: str) -> str:
        for base in ["/timeshift/snapshots", "/run/timeshift/backup/timeshift/snapshots"]:
            path = os.path.join(base, snap_id)
            if os.path.isdir(path):
                size = _dir_size(path)
                return _fmt_size(size) if size > 0 else ""
        return ""

    def delete_cmd(self, snap_id: str) -> str:
        return f"timeshift --delete --snapshot {shlex.quote(snap_id)}"

    def fstype_label(self) -> str:
        return "Btrfs CoW" if detect_root_fstype() == "btrfs" else "rsync"


def _parse_timeshift(output: str) -> list[SnapshotData]:
    result = []
    pat = re.compile(
        r'^\s*(\d+)\s*>?\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S*)\s*(.*?)\s*$')
    for line in output.splitlines():
        m = pat.match(line)
        if m:
            date_str = m.group(2).strip()
            snap_id  = date_str.replace(" ", "_").replace(":", "-")
            result.append(SnapshotData(
                m.group(1), date_str, snap_id,
                m.group(3).strip(), m.group(4).strip()))
    return result


# ── Btrfs native backend ──────────────────────────────────────────────────────

BTRFS_SNAP_DIR = "/.snapshots"


class BtrfsBackend:
    """
    Native Btrfs CoW snapshots using btrfs-progs.
    Requires: btrfs-progs (always present on Btrfs systems).

    Snapshots are stored as read-only subvolumes under snap_dir (default /.snapshots).
    Restore swaps the root subvolume at the Btrfs top-level; reboot needed.
    """

    def __init__(self, snap_dir: str = None):
        self.snap_dir = snap_dir or BTRFS_SNAP_DIR

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
        return result, ""

    def create_cmd(self) -> str:
        d = shlex.quote(self.snap_dir)
        return (
            f"mkdir -p {d} && chmod 755 {d} && "
            f"btrfs subvolume snapshot -r / {d}/$(date +%Y-%m-%d_%H-%M-%S)"
        )

    def restore_cmd(self, snap_id: str) -> str:
        snap_rel = self.snap_dir.lstrip("/")   # e.g. ".snapshots"
        # findmnt gives the subvolume path within the Btrfs volume, e.g. "/@" → "@"
        # We create a writable snapshot from the selected snapshot, rename it
        # to the current root subvolume name, and rename the old root aside.
        # btrfs subvolume delete cannot run on a live (mounted) subvolume, so
        # the old root is left as @_old_DATE; delete it manually after reboot.
        return (
            f"set -e; "
            f"DEV=$(df --output=source / | tail -1); "
            f"MNT=$(mktemp -d); "
            f"mount -o subvol=/ \"$DEV\" \"$MNT\"; "
            f"SUBVOL=$(findmnt -n -o FSROOT /); "
            f"SUBVOL=${{SUBVOL#/}}; "
            f"SNAP_PATH=\"$MNT/$SUBVOL/{snap_rel}/{snap_id}\"; "
            f"NEW=\"$MNT/${{SUBVOL}}_restore_$(date +%Y%m%d%H%M%S)\"; "
            f"btrfs subvolume snapshot \"$SNAP_PATH\" \"$NEW\"; "
            f"OLD=\"$MNT/${{SUBVOL}}_old_$(date +%Y%m%d%H%M%S)\"; "
            f"mv \"$MNT/$SUBVOL\" \"$OLD\"; "
            f"mv \"$NEW\" \"$MNT/$SUBVOL\"; "
            f"umount \"$MNT\"; rmdir \"$MNT\"; "
            f"echo '✓ Restore prepared. Reboot to apply changes.'; "
            f"echo 'The old root is kept as ${{SUBVOL}}_old_* — delete after reboot if no longer needed.'"
        )

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
        path = shlex.quote(os.path.join(self.snap_dir, snap_id))
        return f"btrfs subvolume delete {path}"

    def get_repo_size(self) -> str:
        # CoW snapshots share blocks — raw du is misleading. Skip.
        return ""

    def get_snapshot_size(self, snap_id: str) -> str:
        return ""

    def fstype_label(self) -> str:
        return "Btrfs CoW"


# ── Restic backend ────────────────────────────────────────────────────────────

class ResticBackend:
    """
    Content-addressable, chunked-dedup backup via Restic.
    Works on any filesystem (ext4, xfs, f2fs, NTFS, …).

    Repository : configurable, default /var/lib/equestria-save-point/restic-repo
    Password   : /var/lib/equestria-save-point/repo.key  (auto-generated, root-only)
    """

    def __init__(self, repo: str = None, key: str = None):
        self.repo = repo or RESTIC_REPO
        self.key  = key  or RESTIC_KEY
        # Rebuild excludes: replace the default RESTIC_DIR entry with
        # the parent of the actual repo so we never recurse into it.
        repo_dir = os.path.dirname(self.repo)
        self._excludes = [e for e in RESTIC_EXCLUDES if e != RESTIC_DIR] + [repo_dir]

    def _cmd(self, *args) -> list[str]:
        return ["pkexec", "restic",
                "-r", self.repo,
                "--password-file", self.key, *args]

    def is_initialized(self) -> bool:
        if not os.path.isfile(self.key) or not os.path.isdir(self.repo):
            return False
        r = subprocess.run(self._cmd("cat", "config"),
                           capture_output=True, timeout=10)
        return r.returncode == 0

    def init_cmd(self) -> str:
        """Shell fragment that creates the repo (must be run as root)."""
        d = shlex.quote(RESTIC_DIR)
        k = shlex.quote(self.key)
        r = shlex.quote(self.repo)
        repo_parent = shlex.quote(os.path.dirname(self.repo))
        return (
            f"mkdir -p {d} && "
            f"chmod 755 {d} && "   # world-readable dir so du works without root
            f"mkdir -p {repo_parent} && "
            f"chmod 755 {repo_parent} && "
            f"openssl rand -base64 32 > {k} && "
            f"chmod 600 {k} && "   # key stays root-only
            f"restic init -r {r} --password-file {k}"
        )

    def list_snapshots(self) -> tuple[list[SnapshotData], str]:
        try:
            r = subprocess.run(
                self._cmd("snapshots", "--json"),
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return [], r.stderr.strip()
            raw = json.loads(r.stdout or "[]")
            result = []
            for i, s in enumerate(raw):
                snap_id  = s["short_id"]
                raw_time = s.get("time", "")
                try:
                    dt       = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                    date_str = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                    fs_id    = dt.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
                except Exception:
                    date_str = raw_time[:19]
                    fs_id    = snap_id
                comment = ", ".join(s.get("tags") or [])
                result.append(SnapshotData(
                    str(i), date_str, snap_id, "R", comment, fs_id=fs_id))
            return result[::-1], ""   # newest first
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                return [], "err.restic_not_found"
            if isinstance(e, subprocess.TimeoutExpired):
                return [], "err.timeout"
            return [], str(e)

    def create_cmd(self) -> str:
        excl = " ".join(f"--exclude={shlex.quote(e)}" for e in self._excludes)
        r = shlex.quote(self.repo)
        k = shlex.quote(self.key)
        return (
            f"restic -r {r} --password-file {k} "
            f"backup / {excl} "
            f"--tag 'User Point' --compression auto"
        )

    def build_prune_cmd(self, snapshots: list, keep_last: int) -> str:
        r = shlex.quote(self.repo)
        k = shlex.quote(self.key)
        return (
            f"restic -r {r} --password-file {k} "
            f"forget --keep-last {keep_last} --prune"
        )

    def get_repo_size(self) -> str:
        if not os.path.isdir(self.repo):
            return ""
        size = _dir_size(self.repo)
        return _fmt_size(size) if size > 0 else ""

    def get_snapshot_size(self, snap_id: str) -> str:
        # Restic's logical size equals the whole system size — misleading.
        # Actual disk usage is shared across snapshots via dedup; see repo total.
        return ""

    def delete_cmd(self, snap_id: str) -> str:
        r = shlex.quote(self.repo)
        k = shlex.quote(self.key)
        s = shlex.quote(snap_id)
        return f"restic -r {r} --password-file {k} forget {s} --prune"

    def restore_cmd(self, snap_id: str) -> str:
        r = shlex.quote(self.repo)
        k = shlex.quote(self.key)
        s = shlex.quote(snap_id)
        return (
            f"restic -r {r} --password-file {k} "
            f"restore {s} --target /"
        )

    def fstype_label(self) -> str:
        return f"Restic ({detect_root_fstype()})"
