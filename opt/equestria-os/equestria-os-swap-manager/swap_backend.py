"""
CLI backend for privileged swap and memory operations in Equestria OS.

Supports multiple commands in a single invocation:
  python3 swap_backend.py --create /swapfile 32 yes
  python3 swap_backend.py --swappiness 80
  python3 swap_backend.py --zram-enable 8 lzo-rle --overcommit 1 --oomd disable --panic-on-oom 0
"""
import sys
import os
import shutil
import subprocess

FSTAB_PATH  = "/etc/fstab"
SYSCTL_DIR  = "/etc/sysctl.d"
# zram is configured through zram-generator (one device, zram0) via our own
# drop-in, so it can't collide with a system-wide zram-generator.conf.
ZRAM_GENERATOR = "/usr/lib/systemd/system-generators/zram-generator"
ZRAM_DROPIN = "/etc/systemd/zram-generator.conf.d/90-equestria-swap-manager.conf"
ZRAM_DEVICE = "zram0"
# Old versions created their own device with this service — on top of
# zram-generator's, giving two zram devices at once.
LEGACY_ZRAM_SERVICE = "/etc/systemd/system/equestria-zram.service"
ZSWAP_PARAM = "/sys/module/zswap/parameters/enabled"
ZSWAP_TMPFILES = "/etc/tmpfiles.d/equestria-swap-manager-zswap.conf"
BTRFS_SWAP_SUBVOL = "/swap"


# ── helpers ──────────────────────────────────────────────────────────────────

def _sysctl_set(key, value):
    subprocess.run(["sysctl", f"{key}={value}"], check=True)


def _sysctl_persist(filename, key, value):
    """Write/replace a single key in /etc/sysctl.d/<filename>."""
    os.makedirs(SYSCTL_DIR, exist_ok=True)
    path = os.path.join(SYSCTL_DIR, filename)
    lines = []
    if os.path.exists(path):
        with open(path) as f:
            lines = [l for l in f.readlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}\n")
    with open(path, "w") as f:
        f.writelines(lines)


def remove_from_fstab(path):
    if not os.path.exists(FSTAB_PATH):
        return
    with open(FSTAB_PATH) as f:
        lines = f.readlines()
    with open(FSTAB_PATH, "w") as f:
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] == path and parts[2] == "swap":
                continue
            f.write(line)


def _subvolume_id(path):
    """Btrfs subvolume ID of `path`, or None if `path` isn't on Btrfs."""
    r = subprocess.run(["btrfs", "subvolume", "show", path],
                        capture_output=True, text=True)
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("Subvolume ID:"):
            return line.split(":", 1)[1].strip()
    return None


def _resolve_swap_path(path, create_subvol=False):
    """
    Map a user-chosen swapfile path to where it should actually live.

    Btrfs refuses to snapshot a subvolume that contains an active
    swapfile — so a swapfile placed directly inside the '/' subvolume
    would silently block every future snapshot of the root filesystem
    (timeshift, snapper, equestria-os-save-point, ...). If that's where
    `path` would land, relocate it (keeping only its filename) into a
    dedicated subvolume so '/' stays snapshot-able.

    On every other filesystem — or when the file is already outside the
    '/' subvolume — this is a no-op and returns `path` unchanged.
    """
    if not shutil.which("btrfs"):
        return path

    parent = os.path.dirname(os.path.abspath(path)) or "/"
    ancestor = parent
    while not os.path.exists(ancestor):
        ancestor = os.path.dirname(ancestor) or "/"
        if ancestor == "/":
            break

    root_id = _subvolume_id("/")
    if root_id is None or _subvolume_id(ancestor) != root_id:
        return path  # not Btrfs, or already outside the '/' subvolume

    if create_subvol and not os.path.exists(BTRFS_SWAP_SUBVOL):
        subprocess.run(["btrfs", "subvolume", "create", BTRFS_SWAP_SUBVOL], check=True)
    return os.path.join(BTRFS_SWAP_SUBVOL, os.path.basename(path))


# ── swap file commands ────────────────────────────────────────────────────────

def disable_swap(path):
    path = _resolve_swap_path(path)
    subprocess.run(["swapoff", path], check=False)
    remove_from_fstab(path)
    sys.stdout.write(f"OK: Disabled swap at {path}\n")


def create_swap(path, size_gb, add_to_fstab):
    path = _resolve_swap_path(path, create_subvol=True)
    subprocess.run(["swapoff", path], check=False)
    subprocess.run(["touch", path], check=True)
    subprocess.run(["chattr", "+C", path], check=False)
    size_mb = int(size_gb) * 1024
    subprocess.run(["dd", "if=/dev/zero", f"of={path}", "bs=1M",
                    f"count={size_mb}", "status=none"], check=True)
    subprocess.run(["chmod", "0600", path], check=True)
    subprocess.run(["mkswap", path], check=True)
    subprocess.run(["swapon", path], check=True)
    if add_to_fstab == "yes":
        remove_from_fstab(path)
        with open(FSTAB_PATH, "a") as f:
            f.write(f"{path}\tnone\tswap\tdefaults\t0\t0\n")
    sys.stdout.write(f"OK: Created and enabled {size_gb}GB swap at {path}\n")


def delete_swap(path):
    path = _resolve_swap_path(path)
    disable_swap(path)
    if os.path.exists(path):
        os.remove(path)
        sys.stdout.write(f"OK: Deleted file {path}\n")
    else:
        sys.stdout.write(f"OK: File {path} already gone\n")


# ── kernel param commands ─────────────────────────────────────────────────────

def set_swappiness(value):
    _sysctl_set("vm.swappiness", value)
    _sysctl_persist("99-swappiness.conf", "vm.swappiness", value)
    sys.stdout.write(f"OK: swappiness set to {value}\n")


def set_overcommit(value):
    _sysctl_set("vm.overcommit_memory", value)
    _sysctl_persist("99-memory.conf", "vm.overcommit_memory", value)
    sys.stdout.write(f"OK: overcommit_memory set to {value}\n")


def set_panic_on_oom(value):
    if not os.path.exists("/proc/sys/kernel/panic_on_oom"):
        # Not compiled into this kernel build — skip silently
        sys.stdout.write("OK: panic_on_oom not available on this kernel, skipped\n")
        return
    _sysctl_set("kernel.panic_on_oom", value)
    _sysctl_persist("99-memory.conf", "kernel.panic_on_oom", value)
    sys.stdout.write(f"OK: panic_on_oom set to {value}\n")


def set_oomd(state):
    action = "enable" if state == "enable" else "disable"
    subprocess.run(["systemctl", action, "--now", "systemd-oomd"], check=False)
    sys.stdout.write(f"OK: systemd-oomd {action}d\n")


# ── zram commands ─────────────────────────────────────────────────────────────

class ZramSetup:
    """
    zram swap via zram-generator.

    The size/algorithm go into a drop-in that overrides the [zram0] section
    of any /etc/systemd/zram-generator.conf (the base file itself is never
    touched). "Off" is the same drop-in with zram-size = 0 — zram-generator
    then creates no device.

    zswap is switched off while zram is on: it would otherwise compress the
    same pages a second time and keep its own pool (up to 20% of RAM) in front
    of zram.
    """

    def enable(self, size_gb, algorithm):
        self._require_generator()
        self._remove_legacy_service()
        self._write_dropin(int(size_gb) * 1024, algorithm)
        self._reload_device(start=True)
        self._set_zswap(False)

        # page-cluster=0: kernel reads one page at a time from zram instead of
        # clusters — much better latency for compressed in-RAM swap.
        _sysctl_set("vm.page-cluster", "0")
        _sysctl_persist("99-zram.conf", "vm.page-cluster", "0")

        sys.stdout.write(f"OK: zram enabled ({size_gb}G, {algorithm}) on /dev/{ZRAM_DEVICE}\n")

    def disable(self):
        self._remove_legacy_service()
        if os.path.exists(ZRAM_GENERATOR):
            self._write_dropin(0, None)
            self._reload_device(start=False)
        self._set_zswap(True)

        # Restore page-cluster to default (3)
        _sysctl_set("vm.page-cluster", "3")
        zram_conf = os.path.join(SYSCTL_DIR, "99-zram.conf")
        if os.path.exists(zram_conf):
            os.remove(zram_conf)

        sys.stdout.write("OK: zram disabled\n")

    # ── internals ──

    @staticmethod
    def _require_generator():
        if not os.path.exists(ZRAM_GENERATOR):
            raise RuntimeError("zram-generator is not installed (pacman -S zram-generator)")

    @staticmethod
    def _write_dropin(size_mb, algorithm):
        lines = [f"[{ZRAM_DEVICE}]", f"zram-size = {size_mb}"]
        if algorithm:
            lines += [f"compression-algorithm = {algorithm}",
                      "swap-priority = 100",
                      "fs-type = swap"]
        os.makedirs(os.path.dirname(ZRAM_DROPIN), exist_ok=True)
        with open(ZRAM_DROPIN, "w") as f:
            f.write("# Managed by Equestria OS Swap Manager\n" + "\n".join(lines) + "\n")

    @staticmethod
    def _reload_device(start):
        """Re-run the generator and recreate zram0 with the new settings."""
        swap_unit = f"dev-{ZRAM_DEVICE}.swap"
        setup_unit = f"systemd-zram-setup@{ZRAM_DEVICE}.service"
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        # Stopping the setup unit resets the device, so the next start
        # applies the new size/algorithm.
        subprocess.run(["systemctl", "stop", swap_unit, setup_unit], check=False)
        if start:
            subprocess.run(["systemctl", "start", swap_unit], check=True)

    @staticmethod
    def _remove_legacy_service():
        if not os.path.exists(LEGACY_ZRAM_SERVICE):
            return
        # Its ExecStop resets every /dev/zram*; harmless here, zram0 is
        # recreated (or intentionally left off) right after.
        subprocess.run(["systemctl", "disable", "--now",
                        os.path.basename(LEGACY_ZRAM_SERVICE)], check=False)
        os.remove(LEGACY_ZRAM_SERVICE)
        subprocess.run(["systemctl", "daemon-reload"], check=False)

    @staticmethod
    def _set_zswap(enabled):
        if not os.path.exists(ZSWAP_PARAM):
            return
        if enabled:
            # Only undo what we did ourselves — zswap may be off on purpose.
            if not os.path.exists(ZSWAP_TMPFILES):
                return
            os.remove(ZSWAP_TMPFILES)
        else:
            # tmpfiles.d re-applies it on every boot.
            os.makedirs(os.path.dirname(ZSWAP_TMPFILES), exist_ok=True)
            with open(ZSWAP_TMPFILES, "w") as f:
                f.write("# Managed by Equestria OS Swap Manager: zswap off while zram is on\n"
                        f"w {ZSWAP_PARAM} - - - - N\n")
        with open(ZSWAP_PARAM, "w") as f:
            f.write("Y" if enabled else "N")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        sys.stderr.write("No arguments provided\n")
        sys.exit(1)

    i = 0
    try:
        while i < len(args):
            cmd = args[i]

            if cmd == "--create" and i + 3 < len(args):
                create_swap(args[i+1], args[i+2], args[i+3])
                i += 4

            elif cmd == "--disable" and i + 1 < len(args):
                disable_swap(args[i+1])
                i += 2

            elif cmd == "--delete" and i + 1 < len(args):
                delete_swap(args[i+1])
                i += 2

            elif cmd == "--swappiness" and i + 1 < len(args):
                set_swappiness(args[i+1])
                i += 2

            elif cmd == "--overcommit" and i + 1 < len(args):
                set_overcommit(args[i+1])
                i += 2

            elif cmd == "--oomd" and i + 1 < len(args):
                set_oomd(args[i+1])
                i += 2

            elif cmd == "--panic-on-oom" and i + 1 < len(args):
                set_panic_on_oom(args[i+1])
                i += 2

            elif cmd == "--zram-enable" and i + 2 < len(args):
                ZramSetup().enable(args[i+1], args[i+2])
                i += 3

            elif cmd == "--zram-disable":
                ZramSetup().disable()
                i += 1

            else:
                sys.stderr.write(f"Unknown or incomplete command at position {i}: {cmd}\n")
                sys.exit(1)

    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"Command failed: {e}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
