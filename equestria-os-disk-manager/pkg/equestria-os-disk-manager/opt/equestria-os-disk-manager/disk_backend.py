"""
CLI backend for privileged disk operations in Equestria OS.
"""
import sys
import os
import subprocess

FSTAB_PATH = "/etc/fstab"


def remove_from_fstab(uuid):
    if not os.path.exists(FSTAB_PATH):
        return
    with open(FSTAB_PATH, 'r') as f:
        lines = f.readlines()
    with open(FSTAB_PATH, 'w') as f:
        for line in lines:
            if not line.strip().startswith(f"UUID={uuid}"):
                f.write(line)
    sys.stdout.write(f"OK: Removed {uuid} from fstab\n")


def add_to_fstab(uuid, mountpoint, fstype, options):
    remove_from_fstab(uuid)
    os.makedirs(mountpoint, exist_ok=True)
    safe_mp = mountpoint.replace(" ", "\\040")
    with open(FSTAB_PATH, 'a') as f:
        f.write(f"UUID={uuid}\t{safe_mp}\t{fstype}\t{options}\t0\t2\n")
    subprocess.run(["mount", mountpoint], check=False)
    sys.stdout.write(f"OK: Added {uuid} and mounted to {mountpoint}\n")


def mount_partition(device, mountpoint):
    os.makedirs(mountpoint, exist_ok=True)
    subprocess.run(["mount", f"/dev/{device}", mountpoint], check=True)
    sys.stdout.write(f"OK: Mounted /dev/{device} to {mountpoint}\n")


def umount_partition(mountpoint):
    subprocess.run(["umount", mountpoint], check=True)
    sys.stdout.write(f"OK: Unmounted {mountpoint}\n")


def fix_permissions(mountpoint, username, recursive=False):
    if not os.path.ismount(mountpoint):
        subprocess.run(["mount", mountpoint], check=False)
    if not os.path.exists(mountpoint):
        sys.stderr.write(f"Error: Mountpoint {mountpoint} does not exist\n")
        sys.exit(1)

    chown_cmd = ["chown"]
    chmod_cmd = ["chmod"]
    if recursive:
        chown_cmd.append("-R")
        chmod_cmd.append("-R")
    chown_cmd.extend([f"{username}:{username}", mountpoint])
    chmod_cmd.extend(["u+rwX", mountpoint])

    subprocess.run(chown_cmd, check=True)
    subprocess.run(chmod_cmd, check=True)
    sys.stdout.write(f"OK: Permissions fixed for {mountpoint} (owner: {username})\n")


def set_label(device, fstype, label):
    dev = f"/dev/{device}"
    if fstype in ("ext2", "ext3", "ext4"):
        subprocess.run(["e2label", dev, label], check=True)
    elif fstype == "btrfs":
        subprocess.run(["btrfs", "filesystem", "label", dev, label], check=True)
    elif fstype in ("ntfs", "ntfs-3g"):
        subprocess.run(["ntfslabel", dev, label], check=True)
    elif fstype == "exfat":
        subprocess.run(["exfatlabel", dev, label], check=True)
    elif fstype in ("vfat", "fat32"):
        subprocess.run(["fatlabel", dev, label], check=True)
    else:
        sys.stderr.write(f"Error: Setting label not supported for {fstype}\n")
        sys.exit(1)
    sys.stdout.write(f"OK: Label set to '{label}' on {dev}\n")


def format_partition(device, fstype, label=None):
    dev = f"/dev/{device}"
    if fstype == "ext4":
        cmd = ["mkfs.ext4", "-F"] + (["-L", label] if label else []) + [dev]
    elif fstype == "ext3":
        cmd = ["mkfs.ext3", "-F"] + (["-L", label] if label else []) + [dev]
    elif fstype == "ext2":
        cmd = ["mkfs.ext2", "-F"] + (["-L", label] if label else []) + [dev]
    elif fstype == "btrfs":
        cmd = ["mkfs.btrfs", "-f"] + (["-L", label] if label else []) + [dev]
    elif fstype == "ntfs":
        cmd = ["mkfs.ntfs", "-f"] + (["-L", label] if label else []) + [dev]
    elif fstype == "exfat":
        cmd = ["mkfs.exfat"] + (["-n", label] if label else []) + [dev]
    elif fstype in ("fat32", "vfat"):
        cmd = ["mkfs.vfat", "-F", "32"] + (["-n", label] if label else []) + [dev]
    else:
        sys.stderr.write(f"Error: Unsupported filesystem: {fstype}\n")
        sys.exit(1)

    subprocess.run(cmd, check=True)
    sys.stdout.write(f"OK: Formatted {dev} as {fstype}\n")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(1)

    cmd = args[0]
    try:
        if cmd == "--rm-fstab" and len(args) == 2:
            remove_from_fstab(args[1])
        elif cmd == "--add-fstab" and len(args) == 5:
            add_to_fstab(args[1], args[2], args[3], args[4])
        elif cmd == "--mount" and len(args) == 3:
            mount_partition(args[1], args[2])
        elif cmd == "--umount" and len(args) == 2:
            umount_partition(args[1])
        elif cmd == "--fix-perms" and len(args) >= 3:
            fix_permissions(args[1], args[2], recursive="--recursive" in args)
        elif cmd == "--set-label" and len(args) == 4:
            set_label(args[1], args[2], args[3])
        elif cmd == "--format" and len(args) >= 3:
            format_partition(args[1], args[2], args[3] if len(args) >= 4 else None)
        else:
            sys.stderr.write("Invalid arguments\n")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
