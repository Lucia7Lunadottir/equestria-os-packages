#!/usr/bin/env python3
import sys
import os
import subprocess

# Указываем правильный путь из твоего PKGBUILD
APP_DIR = "/usr/lib/equestria-os-save-point"
sys.path.append(APP_DIR)

try:
    from backend import detect_backend, BtrfsBackend, ResticBackend, TimeshiftBackend, RESTIC_REPO
except ImportError:
    print(f"Ошибка: Не удалось найти модули Equestria Save Point в {APP_DIR}")
    sys.exit(1)

def main():
    if os.geteuid() != 0:
        print("Ошибка: Эту команду необходимо выполнять от имени root (используйте sudo).")
        sys.exit(1)

    backend_type = detect_backend()
    if backend_type == "none":
        print("Ошибка: Не найдена поддерживаемая файловая система или бэкенд (btrfs/restic).")
        sys.exit(1)

    repo_path = RESTIC_REPO
    repo_cfg = "/var/lib/equestria-save-point/repo-path"
    if os.path.exists(repo_cfg):
        with open(repo_cfg) as f:
            p = f.read().strip()
            if p: repo_path = p

    if backend_type == "btrfs":
        backend = BtrfsBackend()
    elif backend_type == "restic":
        backend = ResticBackend(repo=repo_path)
    elif backend_type == "timeshift":
        backend = TimeshiftBackend()

    snapshots, err = backend.list_snapshots()
    if err or not snapshots:
        print(f"Бэкапы не найдены или произошла ошибка: {err}")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Использование: sudo restore-system <ID> | latest | day\n")
        print("Доступные точки сохранения:")
        for s in snapshots:
            print(f"  {s.snapshot_id}  |  {s.date_str}  |  Тег: {s.tags}")
        sys.exit(0)

    target = sys.argv[1]
    snap_to_restore = None

    if target == "latest":
        snap_to_restore = snapshots[0]
    elif target == "day":
        for s in snapshots:
            if s.tags == "D":
                snap_to_restore = s
                break
    else:
        for s in snapshots:
            if s.snapshot_id == target:
                snap_to_restore = s
                break

    if not snap_to_restore:
        print(f"Точка сохранения '{target}' не найдена.")
        sys.exit(1)

    print(f"Подготовка к восстановлению: {snap_to_restore.snapshot_id} ({snap_to_restore.date_str})")
    cmd = backend.restore_cmd(snap_to_restore.snapshot_id)
    
    try:
        subprocess.run(["bash", "-c", cmd], check=True)
        print("\n✅ Восстановление успешно инициировано.")
        if backend_type == "btrfs":
            print("ВНИМАНИЕ: Для применения изменений Btrfs необходимо перезагрузить систему!")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Ошибка при восстановлении: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()