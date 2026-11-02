#!/usr/bin/env python3
import sys
import os
import subprocess

# Указываем правильный путь из твоего PKGBUILD
APP_DIR = "/opt/equestria-os/equestria-os-save-point"
sys.path.append(APP_DIR)

try:
    from backend import detect_backend, BtrfsBackend
except ImportError:
    print(f"Ошибка: Не удалось найти модули Equestria Save Point в {APP_DIR}")
    sys.exit(1)

def main():
    if os.geteuid() != 0:
        print("Ошибка: Эту команду необходимо выполнять от имени root (используйте sudo).")
        sys.exit(1)

    backend_type = detect_backend()
    if backend_type == "unsupported":
        print("Ошибка: точки сохранения работают только на Btrfs. Поддержка ext4 и других "
              "файловых систем удалена из-за нестабильности резервных копий.")
        sys.exit(1)
    if backend_type == "none":
        print("Ошибка: не найден btrfs-progs (установите пакет btrfs-progs).")
        sys.exit(1)
    backend = BtrfsBackend()

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
            if s.protected:
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
        print("ВНИМАНИЕ: Для применения изменений Btrfs необходимо перезагрузить систему!")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Ошибка при восстановлении: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()