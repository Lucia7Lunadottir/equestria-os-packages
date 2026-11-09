from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from equestria_ue.config import Config
from equestria_ue.engines import Engine
from equestria_ue.kit import tr
from equestria_ue.paths import CACHE_DIR


def launch_env(cfg: Config) -> dict:
    env = os.environ.copy()
    if cfg["sdl"] != "auto":
        env["SDL_VIDEODRIVER"] = cfg["sdl"]
    env.setdefault("SDL_MOUSE_FOCUS_CLICKTHROUGH", "1")       # клик, возвращающий фокус окну, не теряется
    if cfg["prime"]:
        env.update({"__NV_PRIME_RENDER_OFFLOAD": "1", "__VK_LAYER_NV_optimus": "NVIDIA_only",
                    "__GLX_VENDOR_LIBRARY_NAME": "nvidia", "DRI_PRIME": "1"})
    env["UE-LocalDataCachePath"] = cfg["ddc"]       # папка файлового кеша (узел Local в графах без Zen)
    return env


def ddc_writable(path: str) -> bool:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        t = Path(path) / ".w"
        t.write_text("1")
        t.unlink()
        return True
    except OSError:
        return False


def zen_reachable() -> bool:
    """Редактор обращается к локальному Zen по [::1]. Если IPv6 на loopback выключен,
    Zen недоступен, а файловый кеш в стандартном графе только чистится (DeleteOnly) —
    писать кеш некуда, редактор падает или каждый раз заново компилирует все шейдеры."""
    try:
        return Path("/proc/sys/net/ipv6/conf/lo/disable_ipv6").read_text().strip() == "0"
    except OSError:
        return False


class DdcPolicy:
    """Где редактор хранит Derived Data Cache (скомпилированные шейдеры, обработанные ассеты).

    zen    — стандарт UE 5.4+: локальный сервер Zen;
    files  — обычная папка cfg["ddc"] (граф *NoZenLocalFallback из BaseEngine.ini);
    memory — только в памяти: после закрытия редактора всё компилируется заново.
    auto   — zen, если он достижим, иначе files."""

    MODES = ("auto", "zen", "files", "memory")
    FALLBACK = {"zen": "files", "files": "memory"}     # куда отступать, если редактор упал из-за кеша

    def __init__(self, cfg: Config, eng: Engine):
        self.cfg, self.eng = cfg, eng

    def resolve(self) -> str:
        mode = self.cfg["ddc_mode"] if self.cfg["ddc_mode"] in self.MODES else "auto"
        if mode == "auto":
            mode = "zen" if zen_reachable() else "files"
        if mode == "files" and not ddc_writable(self.cfg["ddc"]):
            mode = "memory"
        return mode

    def args(self, mode: str) -> list:
        if mode == "memory":
            return ["-DDC-ForceMemoryCache"]
        if mode == "files":
            installed = (Path(self.eng.path) / "Engine" / "Build" / "InstalledBuild.txt").exists()
            return ["-ddc=InstalledNoZenLocalFallback" if installed else "-ddc=NoZenLocalFallback"]
        return []


class ShaderThreads:
    """Сколько потоков отдать ShaderCompileWorker. На машинах от 12 потоков Unreal по умолчанию
    резервирует половину ядер (PercentageUnusedShaderCompilingThreads=50) — компиляция идёт вдвое медленнее."""

    MODES = ("fast", "ue")

    @staticmethod
    def overrides(mode: str) -> list:
        if mode != "fast":
            return []
        return ["[DevOptions.Shaders]:PercentageUnusedShaderCompilingThreads=20",
                "[DevOptions.Shaders]:NumUnusedShaderCompilingThreads=2"]


class RayTracing:
    """Трассировка лучей в редакторе. Файлы проекта не меняются — настройки переопределяются
    при запуске. Без неё Lumen работает программно: видеопамяти нужно заметно меньше, а
    трассировка лучей через Vulkan на Linux — самая нестабильная часть VulkanRHI.
    При переключении шейдеры компилируются заново (один раз)."""

    MODES = ("project", "off")
    SECTION = "[/Script/Engine.RendererSettings]"

    @classmethod
    def overrides(cls, mode: str) -> list:
        if mode != "off":
            return []
        return [f"{cls.SECTION}:r.RayTracing=False", f"{cls.SECTION}:r.Lumen.HardwareRayTracing=False"]


def editor_command(cfg: Config, eng: Engine, uproject: str, ddc_mode: str) -> list:
    cmd = [eng.editor] + ([uproject] if uproject else []) + shlex.split(cfg["args"])
    engine_ini = ShaderThreads.overrides(cfg["shader_threads"])
    if cfg["no_tooltips"]:
        engine_ini.append("[SystemSettings]:Slate.EnableTooltips=False")
    if not cfg["cef_gpu"]:
        # GPU-процесс встроенного браузера (EpicWebHelper/CEF) не поднимает Vulkan через ANGLE
        # и перезапускается каждые несколько секунд; программная отрисовка стабильна
        engine_ini.append("[SystemSettings]:r.CEFGPUAcceleration=0")
    engine_ini += RayTracing.overrides(cfg["ray_tracing"])
    if engine_ini:
        cmd.append("-ini:Engine:" + ",".join(engine_ini))
    return cmd + DdcPolicy(cfg, eng).args(ddc_mode)


class RunningEditors:
    """Какие проекты сейчас открыты в редакторе — по командным строкам процессов
    UnrealEditor в /proc. Видит и редакторы, запущенные до старта лаунчера."""

    EDITOR_NAMES = ("UnrealEditor", "UE4Editor")

    @classmethod
    def projects(cls) -> set[Path]:
        found = set()
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            if not args or Path(os.fsdecode(args[0])).name not in cls.EDITOR_NAMES:
                continue
            for a in args[1:]:
                a = os.fsdecode(a)
                if a.lower().endswith(".uproject"):
                    path = Path(a)
                    if not path.is_absolute():   # запущен из терминала с относительным путём
                        try:
                            path = Path(os.readlink(f"/proc/{pid}/cwd")) / path
                        except OSError:
                            continue
                    found.add(path.resolve())
        return found

    @classmethod
    def is_open(cls, uproject: str) -> bool:
        return bool(uproject) and Path(uproject).resolve() in cls.projects()


def already_open_message(uproject: str) -> str:
    return tr("launcher.project_already_open_unreal_engine", Path(uproject).stem)


def launch_editor(cfg: Config, eng: Engine, uproject: str = "") -> str:
    """Запускает редактор отдельным процессом. Возвращает текст ошибки или ''."""
    if not eng.built:
        return tr("launcher.editor_engine_has_not_been")
    if RunningEditors.is_open(uproject):
        return already_open_message(uproject)
    mode = DdcPolicy(cfg, eng).resolve()
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logp = CACHE_DIR / "editor.log"
        log_start = logp.stat().st_size if logp.exists() else 0
        proc = _spawn(editor_command(cfg, eng, uproject, mode), eng, cfg, logp)
        _watch_ddc(proc, mode, eng, cfg, uproject, logp, log_start)
    except OSError as ex:
        return str(ex)
    return ""


def _spawn(cmd, eng, cfg, logp):
    with open(logp, "ab") as log:
        log.write(f"\n[launcher] {shlex.join(cmd)}\n".encode())
        return subprocess.Popen(cmd, cwd=str(Path(eng.editor).parent), env=launch_env(cfg), start_new_session=True,
                                stdout=log, stderr=log)


class CrashCause:
    """Почему редактор завершился — по коду выхода и журналу этого запуска.

    Перезапуск с другим кешем помогает только при сбое самого кеша (Zen/DDC). Раньше
    лаунчер перезапускал редактор после любого падения в первые 2 минуты — в том числе
    после нехватки видеопамяти и после ручного «убить», и редактор будто открывался сам
    снова и снова."""

    USER_SIGNALS = (-9, -15, -2, -1)    # SIGKILL, SIGTERM, SIGINT, SIGHUP: завершили вручную или сеанс
    DDC_MARKERS = ("LogZenServiceInstance: Error", "LogZenServiceInstance: Warning: Unable to reach",
                   "LogDerivedDataCache: Error", "LogDerivedDataCache: Fatal", "Failed to launch zenserver")
    VRAM_MARKERS = ("Out of memory on Vulkan", "VulkanRHI::FMemoryManager", "Failed to allocate Device Memory")

    def __init__(self, code: int, log_text: str):
        self.code, self.log = code, log_text

    @classmethod
    def read(cls, code: int, logp: Path, start: int) -> "CrashCause":
        try:
            with open(logp, "rb") as f:
                f.seek(start)
                text = f.read().decode("utf-8", "replace")
        except OSError:
            text = ""
        return cls(code, text)

    @property
    def ddc_failure(self) -> bool:
        if self.code == 0 or self.code in self.USER_SIGNALS:
            return False
        if any(m in self.log for m in self.VRAM_MARKERS):
            return False
        return any(m in self.log for m in self.DDC_MARKERS)


def _watch_ddc(proc, mode, eng, cfg, uproject, logp, log_start=0) -> None:
    """Если редактор упал на старте из-за кеша DDC — один раз перезапускаем со следующим
    по надёжности кешем. Запоминаем только файловый кеш: кеш в памяти навсегда означал
    бы полную перекомпиляцию шейдеров при каждом запуске."""
    import threading
    import time

    nxt = DdcPolicy.FALLBACK.get(mode)
    if not nxt:
        return

    def run():
        t0 = time.time()
        code = proc.wait()
        if time.time() - t0 > 120 or not CrashCause.read(code, logp, log_start).ddc_failure:
            return
        with open(logp, "ab") as f:
            f.write(f"\n[launcher] editor exited after {time.time() - t0:.0f} s (code {code}) because of the "
                    f"derived data cache; retrying once with DDC mode '{nxt}'\n".encode())
        try:
            p2 = _spawn(editor_command(cfg, eng, uproject, nxt), eng, cfg, logp)
        except OSError:
            return
        t1 = time.time()
        p2.wait()
        if nxt == "files" and time.time() - t1 > 120:      # файловый кеш работает — дальше сразу так
            cfg["ddc_mode"] = "files"
            cfg.save()

    threading.Thread(target=run, daemon=True).start()
