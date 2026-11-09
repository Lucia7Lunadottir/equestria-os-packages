#!/usr/bin/env python3
"""Откат корня Btrfs к точке сохранения и автооткат, когда система не загружается.

    rollback.py restore <ID>   откатить корень к точке <ID> (так работает и кнопка «Восстановить»)
    rollback.py boot-guard     в начале каждой загрузки (equestria-boot-guard.service)
    rollback.py boot-ok        загрузка удалась: экран входа работает 2 минуты (equestria-boot-ok.timer)
                               или систему штатно выключили после его запуска (equestria-boot-ok-shutdown.service)
    rollback.py notice         после входа: сообщить, если был автооткат (автозапуск в сеансе)

Автооткат срабатывает, только если система FAILED_BOOTS раз подряд не дошла до экрана
входа. Берётся самая ранняя точка сохранения после последней удачной загрузки — то есть
состояние, в котором система точно загружалась. Прежний корень не удаляется, а
переименовывается в <subvol>_old_<время>. Повторного отката по кругу не бывает: если и
после отката система не загрузилась, guard ничего больше не трогает.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

APP_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, APP_DIR)

from backend import BTRFS_SNAP_DIR, BtrfsBackend, SnapshotData, detect_root_fstype  # noqa: E402

FAILED_BOOTS = 3
STATE_DIR = Path("/var/lib/equestria-save-point")
DISABLE_FILE = Path("/etc/equestria-save-point/no-auto-rollback")
TS_FORMAT = "%Y-%m-%d_%H-%M-%S"   # как в именах точек сохранения


def log(msg: str):
    print(f"equestria-save-point: {msg}", flush=True)   # из службы попадает в journalctl


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def _mountpoint(path: str) -> bool:
    return subprocess.run(["mountpoint", "-q", path]).returncode == 0


# ── состояние загрузок ────────────────────────────────────────────────────────

class BootState:
    """Счётчик неудачных загрузок, время последней удачной и отметка об автооткате.

    Лежит в /var/lib/equestria-save-point. Если /var — часть корня, после отката файл
    вернулся бы из снимка, поэтому откат записывает состояние прямо в новый корень
    (см. for_root)."""

    FILE = "boot-state.json"

    def __init__(self, directory: Path = STATE_DIR):
        self.path = directory / self.FILE
        try:
            self.data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}

    @classmethod
    def for_root(cls, new_root: Path) -> "BootState":
        """Состояние, которое увидит система, загрузившись из new_root."""
        if _mountpoint("/var"):          # /var — отдельный том: откат его не меняет
            return cls()
        return cls(new_root / STATE_DIR.relative_to("/"))

    failed = property(lambda self: int(self.data.get("failed", 0)))
    last_good = property(lambda self: self.data.get("last_good", ""))
    rolled_back = property(lambda self: self.data.get("rolled_back"))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1)
            f.flush()
            os.fsync(f.fileno())    # следующая загрузка может оказаться аварийной
        os.replace(tmp, self.path)


# ── откат корня ───────────────────────────────────────────────────────────────

class RootRollback:
    """Заменяет subvolume корня копией точки сохранения.

    Точки лежат в /.snapshots внутри самого корня. Раньше они уезжали вместе со старым
    корнем в <subvol>_old_*, и после отката список точек оказывался пустым; теперь их
    subvolume переносятся в новый корень (переименование subvolume между subvolume
    допускается и ничего не копирует)."""

    def __init__(self, snap_dir: str = BTRFS_SNAP_DIR):
        self.snap_dir = snap_dir

    def run(self, snap_id: str, on_new_root=None) -> str:
        source = os.path.join(self.snap_dir, snap_id)
        if not os.path.isdir(source):
            raise FileNotFoundError(f"restore point not found: {source}")
        device = _run("findmnt", "-n", "-o", "SOURCE", "/").split("[")[0]
        subvol = _run("findmnt", "-n", "-o", "FSROOT", "/").lstrip("/")
        if not subvol:
            raise RuntimeError("root is the top-level Btrfs volume, nothing to swap")
        stamp = time.strftime("%Y%m%d%H%M%S")
        top = Path(tempfile.mkdtemp(prefix="save-point-"))
        subprocess.run(["mount", "-o", "subvol=/", device, str(top)], check=True)
        try:
            current, new, old = top / subvol, top / f"{subvol}_restore_{stamp}", top / f"{subvol}_old_{stamp}"
            subprocess.run(["btrfs", "subvolume", "snapshot", source, str(new)], check=True,
                           stdout=subprocess.DEVNULL)
            if not _mountpoint(self.snap_dir):
                self._move_snapshots(current / self.snap_dir.lstrip("/"), new / self.snap_dir.lstrip("/"))
            if on_new_root:
                on_new_root(new)
            os.rename(current, old)
            os.rename(new, current)
        finally:
            subprocess.run(["umount", str(top)])
            top.rmdir()
        return f"{subvol}_old_{stamp}"

    @staticmethod
    def _move_snapshots(old_dir: Path, new_dir: Path):
        """Перенести subvolume точек из старого корня в новый. В копии корня на их месте
        пустые каталоги-заглушки — их убираем."""
        if not old_dir.is_dir():
            return
        for parent in (Path("."), Path("daily")):
            src_parent, dst_parent = old_dir / parent, new_dir / parent
            if not src_parent.is_dir():
                continue
            dst_parent.mkdir(parents=True, exist_ok=True)
            for entry in sorted(src_parent.iterdir()):
                if entry.name == "daily" or not entry.is_dir():
                    continue
                target = dst_parent / entry.name
                if target.is_dir():
                    try:
                        target.rmdir()
                    except OSError:
                        continue    # не заглушка — не трогаем
                os.rename(entry, target)


# ── выбор точки и сама служба ─────────────────────────────────────────────────

def _snapshot_time(s: SnapshotData) -> datetime | None:
    try:
        return datetime.strptime(s.fs_id, TS_FORMAT)
    except (TypeError, ValueError):
        return None


def pick_snapshot(snapshots: list[SnapshotData], last_good: str) -> SnapshotData | None:
    """Самая ранняя точка после последней удачной загрузки: снята перед первым изменением
    системы, которое ещё не проверялось перезагрузкой. Если таких нет — самая новая."""
    dated = [(t, s) for s in snapshots if (t := _snapshot_time(s))]
    if not dated:
        return None
    try:
        good = datetime.strptime(last_good, TS_FORMAT)
    except ValueError:
        good = None
    after = sorted((p for p in dated if good and p[0] >= good), key=lambda p: p[0])
    return after[0][1] if after else max(dated, key=lambda p: p[0])[1]


class BootGuard:
    def __init__(self):
        self.state = BootState()

    @staticmethod
    def counted_boot() -> bool:
        """Считаем только обычную загрузку в графику: не ручной выбор режима в загрузчике."""
        if not Path("/etc/systemd/system/display-manager.service").exists():
            return False    # без экрана входа (startx и т.п.) удачу загрузки не определить
        cmdline = Path("/proc/cmdline").read_text().split()
        if any(a.startswith("systemd.unit=") or a in ("single", "emergency", "rescue", "1", "3") for a in cmdline):
            return False
        try:
            return _run("systemctl", "get-default") == "graphical.target"
        except (OSError, subprocess.CalledProcessError):
            return False

    def run(self) -> int:
        if detect_root_fstype() != "btrfs" or DISABLE_FILE.exists() or not self.counted_boot():
            return 0
        self.state.data["failed"] = self.state.failed + 1
        self.state.save()
        if self.state.failed < FAILED_BOOTS:
            return 0
        if self.state.rolled_back:
            log(f"system still does not boot after the automatic rollback to "
                f"{self.state.rolled_back.get('snapshot')}; not rolling back again")
            return 0
        snapshots, err = BtrfsBackend().list_snapshots()
        snap = pick_snapshot(snapshots, self.state.last_good)
        if not snap:
            log(f"{self.state.failed} failed boots in a row, but there is no restore point {err}")
            return 0
        log(f"{self.state.failed} boots in a row did not reach the login screen; "
            f"rolling back to restore point {snap.snapshot_id}")

        def mark(new_root: Path):
            st = BootState.for_root(new_root)
            st.data.update(failed=0, last_good=self.state.last_good,
                           rolled_back={"snapshot": snap.snapshot_id, "date": snap.date_str,
                                        "at": time.strftime(TS_FORMAT)})
            st.save()

        try:
            old = RootRollback().run(snap.snapshot_id, on_new_root=mark)
        except Exception as e:  # noqa: BLE001 — откат не удался: система остаётся как была
            log(f"automatic rollback failed: {e}")
            return 1
        log(f"rollback done, previous root kept as {old}; rebooting")
        subprocess.run(["systemctl", "reboot"])
        return 0


def boot_ok() -> int:
    """Экран входа работает — загрузка удалась. Вызывается и при штатном выключении:
    перезагрузка из работающей системы — не сбой загрузки, даже если прошло меньше 2 минут."""
    if subprocess.run(["systemctl", "is-active", "--quiet", "display-manager.service"]).returncode != 0:
        return 0
    state = BootState()
    state.data.update(failed=0, last_good=time.strftime(TS_FORMAT))
    if state.rolled_back:   # откат помог; дальше guard снова может откатывать
        state.data["notice"] = state.data.pop("rolled_back")
    state.save()
    return 0


def restore(snap_id: str) -> int:
    def keep_state(new_root: Path):
        # ручной откат: счётчик сбрасываем, чтобы guard не принял его за сбой
        st = BootState.for_root(new_root)
        st.data.update(failed=0)
        st.data.pop("rolled_back", None)
        st.save()
    old = RootRollback().run(snap_id, on_new_root=keep_state)
    print("✓ Restore prepared. Reboot to apply changes.")
    print(f"The old root is kept as {old} — delete it after reboot if no longer needed.")
    return 0


def notice() -> int:
    """Окно в сеансе пользователя: что произошло и где лежит прежняя система."""
    info = BootState().data.get("notice")
    # файл состояния пишет root, поэтому «уже показано» каждый пользователь помнит у себя
    seen = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "equestria-os-save-point" / "rollback-notice"
    if not info or (seen.exists() and seen.read_text() == info.get("at", "")):
        return 0
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from equestria_kit import qt as kit_qt
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)
    from equestria_kit import live_i18n
    # тот же каталог и выбранный язык, что у окна Save Point
    tr = live_i18n.Catalog("equestria-os-save-point", os.path.join(APP_DIR, "main.py")).tr
    QMessageBox.information(None, str(tr("rollback.notice_title")),
                            str(tr("rollback.notice_body", n=FAILED_BOOTS, date=info.get("date", "?"))))
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.write_text(info.get("at", ""))
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "restore" and len(args) == 1:
        return restore(args[0])
    if cmd == "boot-guard":
        return BootGuard().run()
    if cmd == "boot-ok":
        return boot_ok()
    if cmd == "notice":
        return notice()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
