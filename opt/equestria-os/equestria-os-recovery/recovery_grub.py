"""
Пункт «Восстановление Equestria OS» в меню GRUB.

Как это устроено
----------------
* Сам ISO лежит обычным файлом (в /var/lib/equestria-recovery или на другом
  разделе). GRUB открывает его через `loopback` и грузит ядро и initramfs прямо из
  образа — поэтому среда восстановления не зависит от /boot/initramfs-*.img системы
  (они как раз могут быть сломаны).
* initramfs образа (хук archiso_loop_mnt) по `img_dev=` + `img_loop=` сам находит
  раздел с ISO и монтирует его только на чтение. С `copytoram=y` образ целиком
  копируется в память, раздел отпускается, и его можно чинить (fsck, запись).
* Пункты меню — в отдельном файле /boot/grub/equestria-recovery.cfg. grub.cfg
  только подключает его (блок между маркерами); меню системы мы не пересобираем.
  Тот же блок выдаёт /etc/grub.d/42_equestria-recovery, чтобы он пережил
  следующий grub-mkconfig.
* Своё окружение GRUB (EnvFile) — в /boot/grub или на EFI-разделе:
  - «Перезагрузиться в восстановление» — флаг, который GRUB сам стирает при первой
    же загрузке (как grub-reboot, но без GRUB_DEFAULT=saved);
  - счётчик неудачных загрузок (как в Windows): каждый обычный пункт Linux вызывает
    функцию load_video — мы её переопределяем (то же тело + «попытка загрузки +1»).
    Служба equestria-recovery-boot-ok обнуляет счётчик, когда система загрузилась.
    Дошёл до предела — GRUB сам выбирает восстановление и показывает меню.
    Windows и прочие пункты load_video не вызывают — их загрузки не считаются.
"""
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from recovery_paths import (
    GRUB_CFG, GRUB_ENTRY_CFG, GRUB_BLOCK_BEGIN, GRUB_BLOCK_END, ONE_SHOT_VAR, FAILS_VAR,
    LIMIT_VAR, ENTRY_ID, ENTRY_ID_NORAM, CMDLINE_FLAG, REASON_ARG,
)
from recovery_image import IsoInfo, copytoram_fits
from recovery_storage import env_location

_UNSUPPORTED_ABSTRACTIONS = ("cryptodisk", "luks", "luks2", "geli", "lvm", "mdraid1x", "mdraid09")
FAILS_CAP = 9          # дальше не считаем: GRUB не умеет складывать, счёт идёт цепочкой if

HOOK_BLOCK = f"""{GRUB_BLOCK_BEGIN}
if [ -n "${{config_directory}}" ]; then
  eqrec_cfg="${{config_directory}}/equestria-recovery.cfg"
else
  eqrec_cfg="${{prefix}}/equestria-recovery.cfg"
fi
if [ -f "${{eqrec_cfg}}" ]; then
  source "${{eqrec_cfg}}"
fi
{GRUB_BLOCK_END}
"""

# Тело load_video из 00_header (GRUB 2.12), если в grub.cfg его найти не удалось
_DEFAULT_VIDEO_BODY = """  if [ x$grub_platform = xefi ]; then
    insmod efi_gop
  elif [ x$feature_all_video_module = xy ]; then
    insmod all_video
  else
    insmod efi_gop
    insmod ieee1275_fb
    insmod vbe
    insmod vga
    insmod video_bochs
    insmod video_cirrus
  fi"""


class GrubError(Exception):
    """args[0] — ключ перевода."""


def _run(*cmd) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise GrubError("error.grub_probe")
    return r.stdout.strip()


@dataclass
class GrubPath:
    """Файл с точки зрения GRUB: UUID раздела, модуль ФС и путь от корня ФС."""
    uuid: str
    fs: str              # имя модуля GRUB: ext2, btrfs, xfs, fat…
    relpath: str         # путь от корня ФС (для Btrfs — с подтомом, например /@/var/…)

    @classmethod
    def probe(cls, path: str) -> "GrubPath":
        if not shutil.which("grub-probe"):
            raise GrubError("error.no_grub")
        abstraction = subprocess.run(["grub-probe", "--target=abstraction", path],
                                     capture_output=True, text=True).stdout.split()
        if any(a in _UNSUPPORTED_ABSTRACTIONS for a in abstraction):
            raise GrubError("error.encrypted")
        return cls(uuid=_run("grub-probe", "--target=fs_uuid", path),
                   fs=_run("grub-probe", "--target=fs", path),
                   relpath=_run("grub-mkrelpath", path))

    @property
    def mount_flags(self) -> str:
        # relpath у Btrfs считается от верхнего тома, а не от подтома по умолчанию
        return "subvolid=5" if self.fs == "btrfs" else ""


IsoLocation = GrubPath      # прежнее имя (тесты, старый код)


def _grub_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def video_body_from(grub_cfg: str) -> str:
    """Тело `function load_video { … }` из grub.cfg системы."""
    m = re.search(r"^function load_video \{\n(.*?)\n\}", grub_cfg, re.S | re.M)
    return m.group(1).rstrip() if m else ""


def entries_call_load_video(grub_cfg: str) -> bool:
    """Пункты Linux вызывают load_video (нет — при GRUB_GFXPAYLOAD_LINUX=text);
    иначе загрузки не посчитать."""
    in_entry = False
    for line in grub_cfg.splitlines():
        stripped = line.strip()
        if stripped.startswith("menuentry "):
            in_entry = True
        elif in_entry and stripped == "load_video":
            return True
    return False


class EntryRenderer:
    """Текст equestria-recovery.cfg. Чистая функция от данных — легко проверить тестом."""

    def render(self, info: IsoInfo, loc: GrubPath, titles: dict, ram: int | None = None,
               env: GrubPath | None = None, video_body: str | None = None) -> str:
        """env — файл окружения (None — без разового перехода и счётчика);
        video_body — тело load_video системы (None — счётчик выключен)."""
        copy_first = copytoram_fits(info.rootfs_size, ram)
        entries = [
            (ENTRY_ID, titles["ram"], "copytoram=y"),
            (ENTRY_ID_NORAM, titles["noram"], "copytoram=n"),
        ]
        if not copy_first:
            # памяти мало: первым (и целью «перезагрузиться в восстановление») — без копирования
            entries = [(ENTRY_ID, titles["noram"], "copytoram=n"),
                       (ENTRY_ID_NORAM, titles["ram"], "copytoram=y")]
        modules = ["part_gpt", "part_msdos", loc.fs]
        if env and env.fs not in modules:
            modules.append(env.fs)
        out = [
            "# Equestria OS Recovery — файл создаётся автоматически при каждой",
            "# установке/обновлении образа восстановления. Правки будут потеряны.",
            f"# version {info.version}",
            *(f"insmod {m}" for m in modules),
            "insmod loopback",
            "insmod iso9660",
            "",
        ]
        if env:
            out += self._env_block(env, counting=video_body is not None)
        if env and video_body is not None:
            out += self._counter_block(video_body or _DEFAULT_VIDEO_BODY)
        flags = f" img_flags={loc.mount_flags}" if loc.mount_flags else ""
        initrd = " ".join(f"(eqrec){p}" for p in info.initrds)
        for entry_id, title, ram_opt in entries:
            out.append(f"menuentry {_grub_quote(title)} --class recovery --class equestria "
                       f"--class gnu-linux --id {entry_id} {{")
            if env:
                # попали в восстановление — счёт неудач начинается заново
                out += ['  if [ -n "${eqrec_env}" ]; then',
                        f'    set {FAILS_VAR}=""',
                        f'    save_env --file "${{eqrec_env}}" {FAILS_VAR}',
                        "  fi"]
            out += [
                f"  set eqrec_iso={_grub_quote(loc.relpath)}",
                f"  search --no-floppy --fs-uuid --set=eqrec_root {loc.uuid}",
                '  loopback eqrec "(${eqrec_root})${eqrec_iso}"',
                "  set gfxpayload=keep",
                f'  linux (eqrec){info.kernel} archisobasedir=arch img_dev=UUID={loc.uuid}'
                f' img_loop="${{eqrec_iso}}"{flags} {ram_opt} {CMDLINE_FLAG}'
                f' {REASON_ARG}${{eqrec_reason}} {info.options}'.rstrip(),
                f"  initrd {initrd}",
                "}",
                "",
            ]
        return "\n".join(out)

    @staticmethod
    def _env_block(env: GrubPath, counting: bool) -> list:
        lines = [
            'set eqrec_env=""',
            'set eqrec_envdev=""',
            f'set {ONE_SHOT_VAR}=""',
            f'set {FAILS_VAR}=""',
            f'set {LIMIT_VAR}=""',
            'set eqrec_reason=""',
            f"search --no-floppy --fs-uuid --set=eqrec_envdev {env.uuid}",
            'if [ -n "${eqrec_envdev}" ]; then',
            f'  set eqrec_env="(${{eqrec_envdev}}){env.relpath}"',
            '  if [ -f "${eqrec_env}" ]; then',
            f'    load_env --file "${{eqrec_env}}" {ONE_SHOT_VAR} {FAILS_VAR} {LIMIT_VAR}',
            "  else",
            '    set eqrec_env=""',
            "  fi",
            "fi",
            # пункты меню выполняются в своём окружении: видят только экспортированное
            "export eqrec_env",
            f"export {FAILS_VAR}",
            f"export {LIMIT_VAR}",
            "export eqrec_reason",
            "",
            f'if [ "${{{ONE_SHOT_VAR}}}" = "1" ]; then',
            f'  set {ONE_SHOT_VAR}=""',
            f'  save_env --file "${{eqrec_env}}" {ONE_SHOT_VAR}',
            f'  set default="{ENTRY_ID}"',
            '  set eqrec_reason="manual"',
        ]
        if counting:
            lines += [
                f'elif [ -n "${{{FAILS_VAR}}}" -a -n "${{{LIMIT_VAR}}}" ]; then',
                f'  if [ "${{{LIMIT_VAR}}}" -gt 0 ]; then',
                f'    if [ "${{{FAILS_VAR}}}" -ge "${{{LIMIT_VAR}}}" ]; then',
                f'      set default="{ENTRY_ID}"',
                '      set eqrec_reason="auto"',
                # меню могло быть скрыто — человек должен видеть, что происходит
                "      set timeout_style=menu",
                '      if [ "${timeout}" = "0" -o -z "${timeout}" ]; then',
                "        set timeout=10",
                "      fi",
                "    fi",
                "  fi",
            ]
        lines += ["fi", ""]
        return lines

    @staticmethod
    def _counter_block(video_body: str) -> list:
        steps = []
        for n in range(1, FAILS_CAP + 1):
            prev = '-z "${%s}"' % FAILS_VAR if n == 1 else f'"${{{FAILS_VAR}}}" = "{n - 1}"'
            steps.append(f"    {'if' if n == 1 else 'elif'} [ {prev} ]; then")
            steps.append(f'      set {FAILS_VAR}="{n}"')
        return [
            "# Каждая загрузка обычного пункта Linux проходит через load_video: то же тело,",
            "# что в grub.cfg, плюс отметка «попытка загрузки». Удачная загрузка её снимает.",
            "function eqrec_count_boot {",
            '  if [ -n "${eqrec_env}" -a -n "${%s}" ]; then' % LIMIT_VAR,
            f'    if [ "${{{LIMIT_VAR}}}" -gt 0 ]; then',
            *("  " + s for s in steps),
            "      fi",
            f'      save_env --file "${{eqrec_env}}" {FAILS_VAR}',
            "    fi",
            "  fi",
            "}",
            "function load_video {",
            video_body,
            "  eqrec_count_boot",
            "}",
            "",
        ]


class EnvFile:
    """Наш файл окружения GRUB (через grub-editenv). path — путь в системе."""

    def __init__(self, path: str):
        self.path = path

    def exists(self) -> bool:
        return bool(self.path) and os.path.isfile(self.path)

    def create(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not self.exists():
            self._editenv("create")

    def values(self) -> dict:
        if not self.exists() or not shutil.which("grub-editenv"):
            return {}
        out = subprocess.run(["grub-editenv", self.path, "list"], capture_output=True, text=True).stdout
        return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)

    def set(self, **values) -> None:
        current = self.values()
        changed = {k: str(v) for k, v in values.items() if current.get(k) != str(v)}
        if changed:
            self._editenv("set", *(f"{k}={v}" for k, v in changed.items()))

    def unset(self, *names) -> bool:
        present = [n for n in names if n in self.values()]
        if present:
            self._editenv("unset", *present)
        return bool(present)

    def remove(self) -> None:
        try:
            os.remove(self.path)
            os.rmdir(os.path.dirname(self.path))   # только наша папка на ESP, если пуста
        except OSError:
            pass

    def _editenv(self, *args) -> None:
        r = subprocess.run(["grub-editenv", self.path, *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise GrubError("error.grubenv")


class GrubIntegration:
    """Запись/удаление пункта меню, разовый переход и счётчик. Вызывается только от root."""

    def __init__(self, renderer: EntryRenderer | None = None, env_path: str | None = None):
        self.renderer = renderer or EntryRenderer()
        self.env = EnvFile(env_location() if env_path is None else env_path)

    @staticmethod
    def available() -> bool:
        return os.path.isfile(GRUB_CFG) and bool(shutil.which("grub-probe"))

    def install_entry(self, iso_path: str, info: IsoInfo, titles: dict, fail_limit: int) -> dict:
        """Записать пункты и подготовить окружение. Возвращает, что получилось:
        {"one_shot": bool, "auto": bool, "env": путь}."""
        if not self.available():
            raise GrubError("error.no_grub")
        loc = GrubPath.probe(iso_path)
        env_loc, video_body = None, None
        if self.env.path:
            try:
                self.env.create()
                env_loc = GrubPath.probe(self.env.path)
            except (GrubError, OSError):
                env_loc = None
        if env_loc:
            with open(GRUB_CFG, encoding="utf-8", errors="replace") as f:
                cfg = f.read()
            if entries_call_load_video(cfg):
                video_body = video_body_from(cfg)
        text = self.renderer.render(info, loc, titles, env=env_loc, video_body=video_body)
        tmp = GRUB_ENTRY_CFG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, GRUB_ENTRY_CFG)
        self.ensure_hooked()
        if env_loc:
            self.env.set(**{LIMIT_VAR: fail_limit})
        return {"one_shot": bool(env_loc), "auto": bool(env_loc and video_body is not None),
                "env": self.env.path if env_loc else ""}

    def remove_entry(self) -> None:
        try:
            os.remove(GRUB_ENTRY_CFG)
        except FileNotFoundError:
            pass
        self.env.remove()
        # блок в grub.cfg оставляем: без файла он ничего не делает, а grub.cfg не трогаем лишний раз

    @staticmethod
    def ensure_hooked() -> None:
        """Подключить equestria-recovery.cfg в grub.cfg, если ещё не подключён.
        Дописываем блок в конец, остальное меню не меняется; копия — рядом."""
        with open(GRUB_CFG, encoding="utf-8", errors="surrogateescape") as f:
            text = f.read()
        if GRUB_BLOCK_BEGIN in text:
            return
        backup = GRUB_CFG + ".before-equestria-recovery"
        if not os.path.exists(backup):
            shutil.copy2(GRUB_CFG, backup)
        mode = os.stat(GRUB_CFG).st_mode & 0o777
        tmp = GRUB_CFG + ".equestria-recovery.tmp"
        with open(tmp, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(text.rstrip("\n") + "\n\n" + HOOK_BLOCK)
        os.chmod(tmp, mode)
        os.replace(tmp, GRUB_CFG)

    # ── разовый переход и счётчик ────────────────────────────────────────────

    @staticmethod
    def one_shot_supported() -> bool:
        # findmnt, а не grub-probe: окно работает без root, а grub-probe без root диск не читает
        return bool(shutil.which("grub-editenv")) and bool(env_location())

    def set_one_shot(self) -> None:
        if not self.env.exists():
            raise GrubError("error.one_shot_fs")
        self.env.set(**{ONE_SHOT_VAR: 1})

    def clear_one_shot(self) -> bool:
        """Стереть флаг (страховка, если GRUB сам не смог). True — флаг был."""
        return self.env.unset(ONE_SHOT_VAR)

    def boot_ok(self, fail_limit: int) -> None:
        """Система загрузилась: счёт неудач с нуля, разовый флаг снят, предел актуален."""
        if not self.env.exists():
            return
        self.env.unset(ONE_SHOT_VAR, FAILS_VAR)
        self.env.set(**{LIMIT_VAR: fail_limit})

    def set_limit(self, fail_limit: int) -> None:
        if self.env.exists():
            self.env.set(**{LIMIT_VAR: fail_limit})
