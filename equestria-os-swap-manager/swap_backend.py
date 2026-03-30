"""
CLI backend for privileged swap operations in Equestria OS.
"""
import sys
import os
import subprocess

FSTAB_PATH = "/etc/fstab"

def remove_from_fstab(path):
    if not os.path.exists(FSTAB_PATH):
        return
    with open(FSTAB_PATH, 'r') as f:
        lines = f.readlines()
    with open(FSTAB_PATH, 'w') as f:
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] == path and parts[2] == "swap":
                continue
            f.write(line)

def disable_swap(path):
    subprocess.run(["swapoff", path], check=False)
    remove_from_fstab(path)
    sys.stdout.write(f"OK: Disabled swap at {path}\n")

def create_swap(path, size_gb, add_to_fstab):
    subprocess.run(["swapoff", path], check=False)
    subprocess.run(["touch", path], check=True)
    subprocess.run(["chattr", "+C", path], check=False)

    size_mb = int(size_gb) * 1024
    subprocess.run(["dd", "if=/dev/zero", f"of={path}", "bs=1M", f"count={size_mb}", "status=none"], check=True)
    subprocess.run(["chmod", "0600", path], check=True)
    subprocess.run(["mkswap", path], check=True)
    subprocess.run(["swapon", path], check=True)

    if add_to_fstab == "yes":
        remove_from_fstab(path)
        with open(FSTAB_PATH, 'a') as f:
            f.write(f"{path}\tnone\tswap\tdefaults\t0\t0\n")

    sys.stdout.write(f"OK: Created and enabled {size_gb}GB swap at {path}\n")

def delete_swap(path):
    disable_swap(path)
    if os.path.exists(path):
        os.remove(path)
        sys.stdout.write(f"OK: Deleted file {path}\n")
    else:
        sys.stdout.write(f"OK: File {path} already deleted\n")

def set_swappiness(value):
    # Применяем на лету
    subprocess.run(["sysctl", f"vm.swappiness={value}"], check=True)
    # Сохраняем перманентно
    conf_dir = "/etc/sysctl.d"
    os.makedirs(conf_dir, exist_ok=True)
    with open(os.path.join(conf_dir, "99-swappiness.conf"), 'w') as f:
        f.write(f"vm.swappiness={value}\n")
    sys.stdout.write(f"OK: Swappiness permanently set to {value}\n")

def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(1)

    cmd = args[0]
    try:
        if cmd == "--create" and len(args) == 4:
            create_swap(args[1], args[2], args[3])
        elif cmd == "--disable" and len(args) == 2:
            disable_swap(args[1])
        elif cmd == "--delete" and len(args) == 2:
            delete_swap(args[1])
        elif cmd == "--swappiness" and len(args) == 2:
            set_swappiness(args[1])
        else:
            sys.stderr.write("Invalid arguments\n")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"Command Error: {e}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
