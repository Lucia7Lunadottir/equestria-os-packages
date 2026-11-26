"""
Root-бэкенд установленной системы (вызывается через pkexec из окна).

  equestria-recovery-backend install <iso> [--move] [--md5 M] [--verify] [--source S] [--lang L]
  equestria-recovery-backend refresh [--lang L]     переписать пункт GRUB из текущего ISO
  equestria-recovery-backend remove                 удалить образ и пункт меню
  equestria-recovery-backend location <default|точка монтирования> [--lang L]
                                                    где хранить образ (перенести, если он уже есть)
  equestria-recovery-backend auto <on|off>          открывать восстановление после неудачных загрузок
  equestria-recovery-backend one-shot               следующая загрузка — в восстановление
  equestria-recovery-backend clear-one-shot         отменить это
  equestria-recovery-backend boot-ok                система загрузилась (служба equestria-recovery-boot-ok,
                                                    и после выхода из гибернации)
  equestria-recovery-backend import-live --root R [--lang L]
                                                    из установщика: положить ISO, с которого запущена
                                                    live-среда, в новую систему R

Вывод для окна — строки stdout:  `progress <готово> <всего>`, `verify` и `ok`.
Ошибка — `error <ключ перевода> [подробности]` в stderr и код выхода 2.
"""
import argparse
import datetime
import json
import os
import stat
import subprocess
import sys

from recovery_paths import (
    STATE_DIR, ISO_NAME, STATE_FILE, GRUB_CFG, GRUB_ENTRY_CFG, APP_DIR,
    FAIL_LIMIT, FAIL_LIMIT_WITH_SAVE_POINT,
)
from recovery_image import IsoInfo, IsoInspector, IsoError, RecoveryState, version_from_filename
from recovery_grub import GrubIntegration, GrubError
from recovery_storage import StorageLocations, mount_of, free_bytes
from recovery_livemedia import LiveMedium, MediumError, RootfsVerifier

COPY_CHUNK = 4 * 1024 * 1024
SAVE_POINT_ROLLBACK = "/opt/equestria-os/equestria-os-save-point/rollback.py"
SAVE_POINT_DISABLE = "/etc/equestria-save-point/no-auto-rollback"
# установщик кладёт образ, только если после него в системе останется столько места
INSTALL_RESERVE = 10 * 1024 ** 3


class BackendError(Exception):
    pass


def _say(*parts) -> None:
    print(*parts, flush=True)


def _lang_code(lang: str) -> str:
    try:
        from equestria_kit.i18n import normalize
        return normalize(lang) or ""
    except ImportError:
        return (lang or "")[:2]


def grub_titles(lang: str) -> dict:
    """Названия пунктов меню. Не-латиница — только если GRUB грузит шрифт,
    иначе вместо букв были бы квадратики."""
    def load(code):
        try:
            with open(os.path.join(APP_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}
    en = load("en")
    tr = load(lang) if lang else {}
    titles = {"ram": tr.get("grub.entry_ram") or en.get("grub.entry_ram", "Equestria OS Recovery"),
              "noram": tr.get("grub.entry_noram") or en.get("grub.entry_noram",
                                                             "Equestria OS Recovery (low memory)")}
    if not all(t.isascii() for t in titles.values()) and not _grub_has_font():
        titles = {"ram": en.get("grub.entry_ram", "Equestria OS Recovery"),
                  "noram": en.get("grub.entry_noram", "Equestria OS Recovery (low memory)")}
    return titles


def _grub_has_font() -> bool:
    try:
        with open(GRUB_CFG, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    return "loadfont" in text or "set theme=" in text


def save_point_rolls_back() -> bool:
    """Save Point сам откатывает систему после неудачных загрузок (только Btrfs)."""
    if not os.path.isfile(SAVE_POINT_ROLLBACK) or os.path.exists(SAVE_POINT_DISABLE):
        return False
    if mount_of("/").get("fstype") != "btrfs":
        return False
    r = subprocess.run(["systemctl", "is-enabled", "--quiet", "equestria-boot-guard.service"],
                       capture_output=True)
    return r.returncode == 0


def fail_limit(state: RecoveryState) -> int:
    if not state.auto_fallback:
        return 0
    return FAIL_LIMIT_WITH_SAVE_POINT if save_point_rolls_back() else FAIL_LIMIT


class IsoDir:
    """Папка с образом. На чужом разделе — скрытая папка root:root 0755; все операции
    идут относительно открытого дескриптора папки (O_NOFOLLOW), чтобы подмена папки
    ссылкой не увела запись в другое место."""

    TMP = ISO_NAME + ".tmp"

    def __init__(self, directory: str):
        self.directory = directory
        self.fd = -1

    def __enter__(self) -> "IsoDir":
        if self.directory == STATE_DIR:
            os.makedirs(STATE_DIR, mode=0o755, exist_ok=True)
        else:
            try:
                os.mkdir(self.directory, 0o755)
            except FileExistsError:
                pass
        self.fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        st = os.fstat(self.fd)
        if st.st_uid != 0 or not stat.S_ISDIR(st.st_mode):
            os.close(self.fd)
            raise BackendError("error.location_unsafe", self.directory)
        os.fchmod(self.fd, 0o755)
        return self

    def __exit__(self, *exc) -> None:
        if self.fd >= 0:
            os.close(self.fd)

    @property
    def iso_path(self) -> str:
        return os.path.join(self.directory, ISO_NAME)

    @property
    def tmp_path(self) -> str:
        return os.path.join(self.directory, self.TMP)

    def same_fs(self, path: str) -> bool:
        return os.stat(path).st_dev == os.fstat(self.fd).st_dev

    def free(self) -> int:
        st = os.fstatvfs(self.fd)
        return st.f_bavail * st.f_frsize

    def adopt(self, src: str) -> None:
        """Перенести файл на том же разделе (мгновенно)."""
        os.replace(src, self.TMP, dst_dir_fd=self.fd)

    def write_from(self, src: str, size: int | None = None) -> None:
        """Скопировать src (файл или устройство; size — сколько байт) во временный файл."""
        total = size if size is not None else os.path.getsize(src)
        done = 0
        out = os.open(self.TMP, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644,
                      dir_fd=self.fd)
        try:
            with open(src, "rb") as fin, os.fdopen(out, "wb") as fout:
                while done < total:
                    block = fin.read(min(COPY_CHUNK, total - done))
                    if not block:
                        raise BackendError("error.incomplete")
                    fout.write(block)
                    done += len(block)
                    _say("progress", done, total)
                fout.flush()
                os.fsync(fout.fileno())
        except BaseException:
            self.discard_tmp()
            raise

    def commit(self) -> None:
        """Временный файл → образ (старый заменяется только готовым новым)."""
        os.chown(self.TMP, 0, 0, dir_fd=self.fd, follow_symlinks=False)
        os.chmod(self.TMP, 0o644, dir_fd=self.fd, follow_symlinks=False)
        os.replace(self.TMP, ISO_NAME, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)

    def discard_tmp(self) -> None:
        try:
            os.unlink(self.TMP, dir_fd=self.fd)
        except OSError:
            pass

    def remove_iso(self) -> None:
        for name in (ISO_NAME, self.TMP):
            try:
                os.unlink(name, dir_fd=self.fd)
            except FileNotFoundError:
                pass


def verify_image(path: str, inspector: IsoInspector) -> IsoInfo:
    info = inspector.inspect(path)
    _say("verify")
    if RootfsVerifier().verify(path) is False:
        raise BackendError("error.checksum")
    return info


class ImageInstaller:
    """Кладёт проверенный ISO на место и регистрирует его в GRUB."""

    def __init__(self, grub: GrubIntegration | None = None, inspector: IsoInspector | None = None):
        self.grub = grub or GrubIntegration()
        self.inspector = inspector or IsoInspector()

    def install(self, src: str, move: bool, md5: str, source: str, lang: str, verify: bool) -> None:
        state = RecoveryState.load()
        src = os.path.realpath(src)
        if src == os.path.realpath(state.iso_path):
            raise BackendError("error.same_file")
        info = self.inspector.inspect(src)           # до копирования: не тащим 5 ГБ мусора
        with IsoDir(state.directory) as d:
            self._place(d, src, move)
            if verify:
                try:
                    verify_image(d.tmp_path, self.inspector)
                except BaseException:
                    d.discard_tmp()
                    raise
            d.commit()
        state.version = info.version or version_from_filename(source or src)
        state.size = os.path.getsize(state.iso_path)
        state.md5, state.source = md5, source or os.path.basename(src)
        state.installed_at = datetime.datetime.now().isoformat(timespec="seconds")
        state.rootfs_size = info.rootfs_size
        self._register(state, info, lang)

    def refresh(self, lang: str) -> None:
        state = RecoveryState.load()
        if not os.path.isfile(state.iso_path):
            raise BackendError("error.iso_missing")
        info = self.inspector.inspect(state.iso_path)
        state.rootfs_size = info.rootfs_size
        self._register(state, info, lang)

    def remove(self) -> None:
        state = RecoveryState.load()
        self.grub.remove_entry()
        if os.path.isdir(state.directory):
            with IsoDir(state.directory) as d:
                d.remove_iso()
            if state.iso_dir:
                try:
                    os.rmdir(state.iso_dir)
                except OSError:
                    pass
        fresh = RecoveryState(iso_dir=state.iso_dir, auto_fallback=state.auto_fallback)
        fresh.save()

    def relocate(self, key: str, lang: str) -> None:
        """Сменить место хранения; готовый образ переезжает туда же."""
        loc = StorageLocations().find(key)
        if loc is None:
            raise BackendError("error.location_invalid", key)
        state = RecoveryState.load()
        new_dir = loc.directory
        if os.path.normpath(new_dir) == os.path.normpath(state.directory):
            return
        old_path, old_dir_setting = state.iso_path, state.iso_dir
        has_image = os.path.isfile(old_path)
        with IsoDir(new_dir) as d:
            if has_image:
                size = os.path.getsize(old_path)
                if d.free() < size + 512 * 1024 ** 2:
                    raise BackendError("error.no_space")
                d.write_from(old_path)
                d.commit()
        state.iso_dir = "" if loc.key == "default" else new_dir
        if has_image:
            info = self.inspector.inspect(old_path)
            try:
                self._register(state, info, lang)
            except (BackendError, GrubError):
                # новое место GRUB не читает — возвращаем всё как было
                with IsoDir(new_dir) as d:
                    d.remove_iso()
                state.iso_dir = old_dir_setting
                try:
                    self._register(state, info, lang)
                except (BackendError, GrubError):
                    pass
                raise
            os.remove(old_path)
            old_dir = os.path.dirname(old_path)
            if old_dir != STATE_DIR:
                try:
                    os.rmdir(old_dir)
                except OSError:
                    pass
        else:
            state.save()

    def set_auto(self, enabled: bool) -> None:
        state = RecoveryState.load()
        state.auto_fallback = enabled
        state.save()
        self.grub.set_limit(fail_limit(state))

    def boot_ok(self) -> None:
        if not os.path.isfile(GRUB_ENTRY_CFG):
            return
        self.grub.boot_ok(fail_limit(RecoveryState.load()))

    def _register(self, state: RecoveryState, info, lang: str) -> None:
        try:
            result = self.grub.install_entry(state.iso_path, info, grub_titles(lang), fail_limit(state))
            state.grub_error = ""
            state.env_file = result["env"]
            state.one_shot_ok, state.auto_ok = result["one_shot"], result["auto"]
        except GrubError as e:
            state.grub_error = e.args[0]
        state.save()
        if state.grub_error:
            raise BackendError(state.grub_error)

    @staticmethod
    def _place(d: IsoDir, src: str, move: bool) -> None:
        if move and d.same_fs(src):
            d.adopt(src)                            # мгновенно, места не нужно
            return
        need = os.path.getsize(src)
        # старый образ удаляется только после копирования нового — его место не считаем
        if d.free() < need + 512 * 1024 ** 2:
            raise BackendError("error.no_space")
        d.write_from(src)
        if move:
            os.remove(src)


class LiveImporter:
    """Из установщика: ISO, с которого запущена live-среда, — в новую систему.
    Выполняется в live-среде (не в chroot); пункт GRUB пишет уже бэкенд внутри
    новой системы (chroot), где видны её grub.cfg и разделы."""

    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        # пункт GRUB пишет бэкенд уже внутри новой системы (там её grub.cfg и разделы)
        self.register_cmd = ["chroot", self.root, "/usr/bin/equestria-recovery-backend", "refresh"]

    def run(self, lang: str) -> None:
        if self.root == "/" or not os.path.isdir(os.path.join(self.root, "etc")):
            raise BackendError("error.location_invalid", self.root)
        medium = LiveMedium.detect()
        target = os.path.join(self.root, STATE_DIR.lstrip("/"))
        try:
            os.makedirs(target, mode=0o755, exist_ok=True)
            if free_bytes(target) < medium.size + INSTALL_RESERVE:
                raise BackendError("error.no_space")
            inspector = IsoInspector()
            with IsoDir(target) as d:
                d.write_from(medium.path, medium.size)
                try:
                    info = verify_image(d.tmp_path, inspector)
                except BaseException:
                    d.discard_tmp()
                    raise
                d.commit()
        finally:
            medium.release()
        state = RecoveryState(
            version=info.version, size=medium.size, source=f"live-{medium.kind}",
            installed_at=datetime.datetime.now().isoformat(timespec="seconds"),
            rootfs_size=info.rootfs_size)
        state.save(os.path.join(target, os.path.basename(STATE_FILE)))
        r = subprocess.run(self.register_cmd + ["--lang", lang or self._target_lang()])
        if r.returncode != 0:
            raise BackendError("error.grub_probe")

    def _target_lang(self) -> str:
        try:
            with open(os.path.join(self.root, "etc/locale.conf"), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("LANG="):
                        return _lang_code(line.split("=", 1)[1].strip().strip('"'))
        except OSError:
            pass
        return ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="equestria-recovery-backend")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("iso")
    i.add_argument("--move", action="store_true")
    i.add_argument("--md5", default="")
    i.add_argument("--verify", action="store_true")
    i.add_argument("--source", default="")
    i.add_argument("--lang", default="")
    r = sub.add_parser("refresh")
    r.add_argument("--lang", default="")
    sub.add_parser("remove")
    loc = sub.add_parser("location")
    loc.add_argument("key")
    loc.add_argument("--lang", default="")
    a = sub.add_parser("auto")
    a.add_argument("mode", choices=("on", "off"))
    sub.add_parser("one-shot")
    sub.add_parser("clear-one-shot")
    sub.add_parser("boot-ok")
    imp = sub.add_parser("import-live")
    imp.add_argument("--root", required=True)
    imp.add_argument("--lang", default="")
    args = p.parse_args(argv)

    if os.geteuid() != 0:
        print("error error.not_root", file=sys.stderr)
        return 2
    installer = ImageInstaller()
    try:
        if args.cmd == "install":
            installer.install(args.iso, args.move, args.md5, args.source, args.lang, args.verify)
        elif args.cmd == "refresh":
            installer.refresh(args.lang)
        elif args.cmd == "remove":
            installer.remove()
        elif args.cmd == "location":
            installer.relocate(args.key, args.lang)
        elif args.cmd == "auto":
            installer.set_auto(args.mode == "on")
        elif args.cmd == "one-shot":
            if not os.path.isfile(RecoveryState.load().iso_path):
                raise BackendError("error.iso_missing")
            installer.grub.set_one_shot()
        elif args.cmd == "clear-one-shot":
            installer.grub.clear_one_shot()
        elif args.cmd == "boot-ok":
            installer.boot_ok()
        elif args.cmd == "import-live":
            LiveImporter(args.root).run(_lang_code(args.lang))
    except (BackendError, IsoError, GrubError, MediumError) as e:
        print("error", *e.args, file=sys.stderr)
        return 2
    except OSError as e:
        print("error error.os", e, file=sys.stderr)
        return 2
    _say("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
