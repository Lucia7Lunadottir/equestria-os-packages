#!/usr/bin/env python3
import sys
import subprocess

sys.path.append("/usr/lib/equestria-os-save-point")
from backend import detect_backend, BtrfsBackend, ResticBackend, TimeshiftBackend, RESTIC_REPO

def run():
    backend_type = detect_backend()
    if backend_type == "none":
        sys.exit(1) # Остановка: бэкенд не найден

    if backend_type == "btrfs":
        backend = BtrfsBackend()
    elif backend_type == "restic":
        backend = ResticBackend(repo=RESTIC_REPO)
    elif backend_type == "timeshift":
        backend = TimeshiftBackend()

    snapshots, err = backend.list_snapshots()
    if err or not snapshots:
        sys.exit(1) # Остановка: бэкапы не найдены или ошибка

    latest_snap = snapshots[0]
    cmd = backend.restore_cmd(latest_snap.snapshot_id)
    
    try:
        # check=True вызовет ошибку, если команда восстановления упадет
        subprocess.run(["bash", "-c", cmd], check=True)
    except subprocess.CalledProcessError:
        sys.exit(1) # Остановка: само восстановление сломалось

if __name__ == "__main__":
    run()