"""
CLI backend for privileged swap and memory operations in Equestria OS.

Supports multiple commands in a single invocation:
  python3 swap_backend.py --create /swapfile 32 yes
  python3 swap_backend.py --swappiness 80
  python3 swap_backend.py --zram-enable 8 lzo-rle --overcommit 1 --oomd disable --panic-on-oom 0
"""
import sys
import os
import subprocess

FSTAB_PATH  = "/etc/fstab"
SYSCTL_DIR  = "/etc/sysctl.d"
ZRAM_SERVICE = "/etc/systemd/system/equestria-zram.service"


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


# ── swap file commands ────────────────────────────────────────────────────────

def disable_swap(path):
    subprocess.run(["swapoff", path], check=False)
    remove_from_fstab(path)
    sys.stdout.write(f"OK: Disabled swap at {path}\n")


def create_swap(path, size_gb, add_to_fstab):
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

def enable_zram(size_gb, algorithm):
    """
    Set up zram swap in RAM:
      1. Load the zram kernel module
      2. Use 'zramctl --find' to create the next available device
      3. Format and activate with priority 100 (higher than disk swap)
      4. Persist via a systemd oneshot service
      5. Set vm.page-cluster=0 (optimal for in-RAM swap)
    """
    size_str = f"{size_gb}G"

    # Ensure module is loaded (ignore error if already loaded)
    subprocess.run(["modprobe", "zram"], check=False)

    # Swapoff and reset any existing equestria-managed zram devices
    r = subprocess.run(["swapon", "--show=NAME,TYPE"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        parts = line.split()
        if parts and "/dev/zram" in parts[0]:
            subprocess.run(["swapoff", parts[0]], check=False)
            subprocess.run(["zramctl", "--reset", parts[0]], check=False)

    # --find creates the next free zram device, sets size+algorithm atomically,
    # and prints the device path — no manual /dev/zramN guessing needed.
    result = subprocess.run(
        ["zramctl", "--find", "--size", size_str, "--algorithm", algorithm],
        capture_output=True, text=True, check=True,
    )
    zram_dev = result.stdout.strip() or "/dev/zram0"

    subprocess.run(["mkswap", zram_dev], check=True)
    subprocess.run(["swapon", "-p", "100", zram_dev], check=True)

    # Persist via systemd service (uses --find on every boot too)
    service = f"""[Unit]
Description=Equestria OS Fast Swap (zram)
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/sh -c 'modprobe zram; \\
    DEV=$(zramctl --find --size {size_str} --algorithm {algorithm}) && \\
    mkswap "$DEV" && \\
    swapon -p 100 "$DEV"'
ExecStop=/usr/bin/sh -c 'for d in /dev/zram*; do swapoff "$d" 2>/dev/null; zramctl --reset "$d" 2>/dev/null; done; true'

[Install]
WantedBy=multi-user.target
"""
    with open(ZRAM_SERVICE, "w") as f:
        f.write(service)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "equestria-zram.service"], check=False)

    # page-cluster=0: kernel reads one page at a time from zram instead of
    # clusters — much better latency for compressed in-RAM swap.
    _sysctl_set("vm.page-cluster", "0")
    _sysctl_persist("99-zram.conf", "vm.page-cluster", "0")

    sys.stdout.write(f"OK: zram enabled ({size_gb}G, {algorithm}) on {zram_dev}\n")


def disable_zram():
    """Remove zram swap and its persistence."""
    subprocess.run(["swapoff", "/dev/zram0"], check=False)
    subprocess.run(["zramctl", "--reset", "/dev/zram0"], check=False)

    # Restore page-cluster to default (3)
    _sysctl_set("vm.page-cluster", "3")
    zram_conf = os.path.join(SYSCTL_DIR, "99-zram.conf")
    if os.path.exists(zram_conf):
        os.remove(zram_conf)

    # Remove service
    subprocess.run(["systemctl", "disable", "--now", "equestria-zram.service"], check=False)
    if os.path.exists(ZRAM_SERVICE):
        os.remove(ZRAM_SERVICE)
    subprocess.run(["systemctl", "daemon-reload"], check=False)

    sys.stdout.write("OK: zram disabled\n")


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
                enable_zram(args[i+1], args[i+2])
                i += 3

            elif cmd == "--zram-disable":
                disable_zram()
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
