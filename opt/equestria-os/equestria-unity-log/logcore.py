# -*- coding: utf-8 -*-
"""
Чтение лога Unity без лагов и без роста памяти (без Qt — можно проверять отдельно).

Как это работает, простыми словами:
  • файл целиком НЕ читается. При открытии берём только последние 256 КБ;
  • потом каждые 0.25 с смотрим, не стал ли файл больше, и читаем только новое;
  • за один раз читаем не больше 2 МБ — даже если Unity выдал гигабайт, мы просто
    перескочим к концу, а не будем «догонять»;
  • если Unity перезапустили и файл начался заново (стал меньше) — читаем с начала.
"""
from __future__ import annotations

import os
import re

START_BYTES = 256 * 1024      # сколько читаем с конца при открытии файла
MAX_READ = 2 * 1024 * 1024    # максимум за один опрос
MAX_LINE = 600                # длинные строки обрезаем (лог бывает с огромными строками)

# ── что считать строкой про шейдеры ───────────────────────────────────────
# Если у вас Unity пишет по-другому — поправьте эти шаблоны, больше ничего менять не надо.
SHADER_RX = re.compile(r"compil\w*.*shader|shader.*compil\w*", re.I)
NAME_RX = re.compile(r'"([^"]+)"')                       # первое слово в кавычках — имя шейдера
PASS_RX = re.compile(r'pass\s+"([^"]+)"', re.I)          # pass "ForwardLit"
PROGRESS_RX = re.compile(r"(\d+)\s*(?:of|/)\s*(\d+)", re.I)   # 14 of 120

SCRIPT_RX = re.compile(r"compiling scripts|reloading assemblies|domain reload|"
                       r"compilation (?:started|finished|succeeded)|assembly-csharp|csc\b", re.I)
BUILD_RX = re.compile(r"build player|building player|buildplayer|build completed|"
                      r"build succeeded|build failed|bee\.|il2cpp|incremental build", re.I)
ERROR_RX = re.compile(r"\berror\b|exception|\bfailed\b|fatal", re.I)
WARN_RX = re.compile(r"\bwarning\b", re.I)


VARIANTS_RX = re.compile(r"(\d+)\s*/\s*(\d+)\s+variants", re.I)   # 8685 / 39168 variants ready


def parse_variants(line: str) -> tuple[int, int] | None:
    m = VARIANTS_RX.search(line)
    if m and 0 < int(m.group(2)):
        return int(m.group(1)), int(m.group(2))
    return None


# Строка стека вызовов («Класс:Метод (аргументы) (at файл:строка)») и «(Filename: …)» — не про работу:
# в них встречаются слова вроде ShaderCompilerData и OnPreprocessShaders.
STACK_RX = re.compile(r"^(?:\(Filename:|[\w.`+<>/]+:[\w.<>`$]+ \(.*\)(?: \(at .*\))?$)")


def classify(line: str) -> str:
    """'progress' | 'shader' | 'script' | 'build' | 'plain' — к какому виду работы относится строка."""
    if STACK_RX.match(line):
        return "plain"
    if "variants" in line and VARIANTS_RX.search(line):
        return "progress"
    if "ompil" in line and SHADER_RX.search(line):
        return "shader"
    if SCRIPT_RX.search(line):
        return "script"
    if BUILD_RX.search(line):
        return "build"
    return "plain"


def level(line: str) -> str:
    """'error' | 'warning' | 'info' — для цвета строки."""
    if ERROR_RX.search(line):
        return "error"
    if WARN_RX.search(line):
        return "warning"
    return "info"


def parse_shader(line: str) -> tuple[str, str, tuple[int, int] | None]:
    """(имя шейдера, подробности, (N, M) или None) из строки компиляции."""
    m = NAME_RX.search(line)
    name = m.group(1) if m else ""
    p = PASS_RX.search(line)
    detail = f'pass "{p.group(1)}"' if p else ""
    pr = PROGRESS_RX.search(line)
    progress = None
    if pr:
        n, total = int(pr.group(1)), int(pr.group(2))
        if 0 < total and n <= total:
            progress = (n, total)
    return name, detail or line, progress


class LogTailer:
    """Хвост файла. poll() возвращает только НОВЫЕ строки с прошлого вызова."""

    def __init__(self, path: str):
        self.path = path
        self.pos = 0
        self.ino: int | None = None
        self.rest = b""          # недописанный кусок последней строки
        self.fresh = True        # ещё ничего не читали
        self.restarted = False   # файл начался заново (Unity перезапущен)

    def poll(self) -> list[str]:
        self.restarted = False
        try:
            st = os.stat(self.path)
        except OSError:
            return []
        size = st.st_size
        if not self.fresh and (st.st_ino != self.ino or size < self.pos):
            self.pos, self.rest, self.fresh = 0, b"", True   # файл пересоздан
            self.restarted = True
        self.ino = st.st_ino
        if size == self.pos and not self.fresh:
            return []

        drop_first = False
        if self.fresh:
            self.fresh = False
            if size > START_BYTES:
                self.pos, drop_first = size - START_BYTES, True
        if size - self.pos > MAX_READ:                    # слишком много нового — прыгаем к концу
            self.pos, self.rest, drop_first = size - MAX_READ, b"", True
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                chunk = f.read(size - self.pos)
        except OSError:
            return []
        self.pos += len(chunk)

        parts = (self.rest + chunk).split(b"\n")
        self.rest = parts.pop()[-8192:]                   # хвост без перевода строки — подождём
        if drop_first and parts:
            parts.pop(0)                                  # первая строка могла начаться не с начала
        out = []
        for raw in parts:
            s = raw.decode("utf-8", "replace").rstrip("\r")
            if s.strip():
                out.append(s[:MAX_LINE])
        return out


# ── «идёт ли билд» — без догадок про секунды ──────────────────────────────
# Строки прогресса в логе приходят раз в минуту-две, поэтому «тишина 3 секунды» ничего
# не значит. Мы считаем, что идёт компиляция, пока (а) не встретился маркер конца билда или
# (б) работают процессы-компиляторы Unity (это видно по загрузке процессора).
# «Pass ForwardLit (fp, dx12) finished in 69.03 seconds. ... compiled 1920 variants (...)»
# Unity пишет это строкой ПОСЛЕ того, как проход скомпилирован; отдельные варианты (набор
# ключевых слов) в лог не попадают — только проход целиком.
PASS_DONE_RX = re.compile(r"^\s*Pass (.+?) \((\w+), (\w+)\) finished in ([\d.]+) seconds.*?compiled (\d+) variants")
SHADER_DONE_RX = re.compile(r"Serialized binary data for shader (.+?) in [\d.]+s")
ELAPSED_RX = re.compile(r"^\s*\[(\d+)s\]")
BUILD_DONE_RX = re.compile(r"Build completed with a result of '([^']+)' in (\d+) seconds")
BUILD_END_RX = re.compile(r"Build Finished, Result: (\w+)")


class BuildTracker:
    STALE_S = 20 * 60   # если в логе тихо дольше и компиляторы не работают — считаем, что всё стоит

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.phase = "idle"          # idle | shaders | done | failed
        self.t_last = 0.0            # когда последний раз пришла строка про шейдеры
        self.batches = 0             # номер порции шейдеров (Unity компилирует порциями)
        self.batch_shaders = 0       # сколько шейдеров в текущей порции
        self.variants: tuple | None = None
        self.result = ""             # 'Succeeded' / 'Failed' ...
        self.duration_s = 0
        self.last_pass: tuple | None = None   # (проход, стадия vp/fp, API, секунд, вариантов)
        self.last_done_shader = ""            # шейдер, который Unity закончил и записал
        self._prog_prev: tuple | None = None  # (секунд с начала порции, готово) — предыдущая строка прогресса
        self._prog_last: tuple | None = None  # (секунд с начала порции, готово, всего, время получения)
        self._seen_progress = False   # после строк прогресса следующий список шейдеров = новая порция

    def feed(self, line: str, kind: str, now: float) -> None:
        if kind == "shader":
            if self.phase != "shaders":
                self.phase, self.batches, self.result, self.duration_s = "shaders", 1, "", 0
                self.batch_shaders = 0
            elif self._seen_progress:                # после прогресса пошёл новый список — новая порция
                self.batches += 1
                self.batch_shaders = 0
                self.variants = None
            self._seen_progress = False
            self.batch_shaders += 1
            self.t_last = now
        elif kind == "progress":
            if self.phase != "shaders":
                self.phase, self.batches, self.batch_shaders = "shaders", 1, 0
                self.result, self.duration_s = "", 0
            self._seen_progress = True
            self.variants = parse_variants(line)
            em = ELAPSED_RX.search(line)
            if self.variants and em:
                if self._prog_last and int(em.group(1)) > self._prog_last[0]:
                    self._prog_prev = self._prog_last[:2]
                elif self._prog_last is None or int(em.group(1)) <= self._prog_last[0]:
                    self._prog_prev = None            # счётчик секунд начался заново — новая порция
                self._prog_last = (int(em.group(1)), self.variants[0], self.variants[1], now)
            self.t_last = now
        else:
            m = PASS_DONE_RX.search(line)
            if m:
                self.last_pass = (m.group(1).strip('"'), m.group(2), m.group(3), float(m.group(4)), int(m.group(5)))
            m = SHADER_DONE_RX.search(line)
            if m:
                self.last_done_shader = m.group(1)
            m = BUILD_DONE_RX.search(line)
            if m:
                self.result, self.duration_s = m.group(1), int(m.group(2))
                self.phase = "done" if m.group(1).lower().startswith("succe") else "failed"
                self.variants = None
            else:
                m = BUILD_END_RX.search(line)
                if m:
                    self.result = "Succeeded" if m.group(1).lower() == "success" else m.group(1)
                    self.phase = "done" if m.group(1).lower() == "success" else "failed"
                    self.variants = None

    def estimate(self, now: float) -> tuple[int, int] | None:
        """Unity пишет прогресс в лог раз в ~70 с, а шкала в самом Unity идёт плавно.
        По двум последним строкам считаем скорость и оцениваем, где Unity сейчас:
        (оценка, возраст последней строки в секундах). Только оценка, не точное число."""
        if not (self._prog_last and self._prog_prev):
            return None
        el0, d0 = self._prog_prev
        el1, d1, total, t1 = self._prog_last
        if el1 <= el0 or d1 < d0:
            return None
        rate = (d1 - d0) / (el1 - el0)
        age = max(0.0, now - t1)
        est = min(total, int(d1 + rate * min(age, 2.0 * (el1 - el0))))
        return est, int(age)

    def shaders_busy(self, now: float, procs_busy: bool) -> bool:
        return self.phase == "shaders" and (procs_busy or now - self.t_last < self.STALE_S)


# ── что компилирует Unity прямо сейчас ────────────────────────────────────
# Editor.log имя шейдера на этом этапе не содержит. Его пишут процессы-компиляторы в соседние
# файлы Logs/shadercompiler-UnityShaderCompiler-N.log: «Cmd: compileSnippet … name=… pass=…».
SNIPPET_RX = re.compile(r"name=(.*?) pass=(\S*) ppOnly=")


class CompilerLogs:
    """Читает хвост самого свежего shadercompiler-*.log рядом с Editor.log (не больше 16 КБ)."""

    TAIL = 16 * 1024
    FRESH_S = 15.0       # лог, который не менялся дольше, считаем старым

    def __init__(self, editor_log: str):
        self.dir = os.path.dirname(os.path.abspath(editor_log))

    def current(self, wall_now: float) -> tuple[str, str] | None:
        """(имя шейдера, проход) того, что компилируется сейчас, или None."""
        newest, newest_t = None, 0.0
        try:
            for e in os.scandir(self.dir):
                if e.name.startswith("shadercompiler-UnityShaderCompiler-") and e.name.endswith(".log"):
                    t = e.stat().st_mtime
                    if t > newest_t:
                        newest, newest_t = e.path, t
        except OSError:
            return None
        if not newest or wall_now - newest_t > self.FRESH_S:
            return None
        try:
            with open(newest, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - self.TAIL))
                text = f.read().decode("utf-8", "replace")
        except OSError:
            return None
        found = SNIPPET_RX.findall(text)
        return (found[-1][0], found[-1][1]) if found else None


class ProcMonitor:
    """Смотрит (Linux, /proc), считают ли что-то процессы-компиляторы Unity.
    Работает дёшево: раз в секунду читает имена процессов и их процессорное время."""

    NAMES = ("UnityShaderCo", "bee_backend", "il2cpp")   # имя процесса в ядре обрезано до 15 символов
    HOLD_S = 3.0                                          # держим «занято» ещё 3 с после активности

    def __init__(self, proc_dir: str = "/proc"):
        self.proc = proc_dir
        self.ticks: dict = {}
        self.t_prev = 0.0
        self.t_active = -1e9
        self.names: dict = {}      # что сейчас работает: {имя: сколько процессов}
        self.hz = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

    def poll(self, now: float) -> bool:
        cur, names = {}, {}
        try:
            entries = os.listdir(self.proc)
        except OSError:
            return False
        for e in entries:
            if not e.isdigit():
                continue
            try:
                with open(f"{self.proc}/{e}/comm", "rb") as f:
                    comm = f.read(32).decode("utf-8", "replace").strip()
                if not comm.startswith(self.NAMES):
                    continue
                with open(f"{self.proc}/{e}/stat", "rb") as f:
                    stat = f.read(1024).decode("utf-8", "replace")
                rest = stat[stat.rindex(")") + 2:].split()
                cur[e] = int(rest[11]) + int(rest[12])       # utime + stime
                names[comm] = names.get(comm, 0) + 1
            except (OSError, ValueError, IndexError):
                continue
        dt = now - self.t_prev
        if self.t_prev and dt > 0:
            used = sum(max(0, t - self.ticks.get(p, t)) for p, t in cur.items()) / self.hz
            if used / dt >= 0.05:        # хотя бы 5% одного ядра
                self.t_active = now
        self.ticks, self.t_prev, self.names = cur, now, names
        return now - self.t_active < self.HOLD_S
