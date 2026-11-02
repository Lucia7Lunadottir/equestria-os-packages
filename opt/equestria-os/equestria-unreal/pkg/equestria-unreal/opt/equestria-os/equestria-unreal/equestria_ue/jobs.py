from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, QTimer, pyqtSignal

from equestria_ue.engines import read_text
from equestria_ue.kit import tr


@dataclass
class Step:
    label: str
    argv: list
    cwd: str = ""
    env: dict | None = None


@dataclass
class Job:
    title: str
    steps: list
    on_done: object = None
    ok: bool | None = None

def kill_tree(pid: int, sig: int = 15) -> None:
    kids = {}
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                ppid = int(read_text(f"/proc/{p}/stat").rsplit(")", 1)[1].split()[1])
                kids.setdefault(ppid, []).append(int(p))
            except Exception:
                pass
    order, stack = [], [pid]
    while stack:
        x = stack.pop()
        order.append(x)
        stack += kids.get(x, [])
    for x in reversed(order):
        try:
            os.kill(x, sig)
        except OSError:
            pass


def clean_line(s: str) -> str:
    s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)
    return s.split("\r")[-1] if "\r" in s else s


class Worker(QThread):
    """Выполняет функцию в фоне (git ls-remote и т.п.), чтобы не вешать окно."""
    done = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            r = self.fn()
        except Exception as ex:
            r = ex
        self.done.emit(r)


class JobManager(QObject):
    changed = pyqtSignal()
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.queue: list = []
        self.current: Job | None = None
        self.history: list = []
        self.idx = -1
        self.pct = 0.0
        self.proc: QProcess | None = None
        self.buf = ""
        self.cancelled = False

    @property
    def progress(self) -> float:
        if not self.current:
            return 0.0
        return min(100.0, (self.idx + self.pct / 100) / max(len(self.current.steps), 1) * 100)

    @property
    def step_label(self) -> str:
        if not self.current or not (0 <= self.idx < len(self.current.steps)):
            return ""
        return tr("Шаг {}/{}: {}", self.idx + 1, len(self.current.steps), self.current.steps[self.idx].label)

    def add(self, job: Job) -> None:
        self.queue.append(job)
        self.log.emit("\n=== " + tr("В очереди: {}", job.title) + " ===")
        if self.current is None:
            self._next_job()
        self.changed.emit()

    def _next_job(self) -> None:
        if not self.queue:
            self.changed.emit()
            return
        self.current = self.queue.pop(0)
        self.idx, self.cancelled = -1, False
        self.log.emit(f"\n=== {self.current.title} ===")
        self._next_step()

    def _next_step(self) -> None:
        self.idx += 1
        self.pct = 0.0
        job = self.current
        if self.idx >= len(job.steps):
            self._finish(True)
            return
        st = job.steps[self.idx]
        self.log.emit(f"\n[{self.idx + 1}/{len(job.steps)}] {st.label}\n$ " + " ".join(shlex.quote(x) for x in st.argv))
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        if st.cwd:
            p.setWorkingDirectory(st.cwd)
        env = QProcessEnvironment.systemEnvironment()
        for k, v in (st.env or {}).items():
            env.insert(k, v)
        p.setProcessEnvironment(env)
        p.readyReadStandardOutput.connect(self._read)
        p.finished.connect(self._step_done)
        p.errorOccurred.connect(self._err)
        self.proc, self.buf = p, ""
        p.start(st.argv[0], st.argv[1:])
        self.changed.emit()

    def _emit(self, text: str, flush: bool = False) -> None:
        self.buf += text
        lines = self.buf.split("\n")
        self.buf = "" if flush else lines.pop()
        for ln in lines:
            ln = clean_line(ln)
            if not ln.strip():
                continue
            m = re.search(r"\[(\d+)/(\d+)\]", ln)
            m2 = re.search(r"(\d{1,3})(?:\.\d+)?%", ln)
            if m and int(m.group(2)) > 0:
                self.pct = min(100.0, int(m.group(1)) * 100 / int(m.group(2)))
            elif m2:
                self.pct = min(100.0, float(m2.group(1)))
            self.log.emit(ln)
        self.changed.emit()

    def _read(self) -> None:
        if self.proc:
            self._emit(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"))

    def _step_done(self, code, _status) -> None:
        if self.proc:
            self._emit(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"), flush=True)
        if self.cancelled:
            self._finish(False)
        elif code != 0:
            self.log.emit("\n" + tr("✗ Шаг завершился с кодом {}. Исправьте причину (см. выше) и запустите установку снова — "
                                 "уже скачанное будет использовано повторно.", code))
            self._finish(False)
        else:
            self._next_step()

    def _err(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.log.emit(tr("✗ Не удалось запустить команду (не установлена программа?)."))
            self._finish(False)

    def cancel(self) -> None:
        if self.current and self.proc:
            self.cancelled = True
            pid = int(self.proc.processId())
            if pid:
                kill_tree(pid)
                QTimer.singleShot(4000, lambda: kill_tree(pid, 9) if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning else None)

    def _finish(self, ok: bool) -> None:
        job = self.current
        job.ok = ok
        self.log.emit("\n" + (tr("✓ Готово: {}", job.title) if ok else tr("✗ Не выполнено: {}", job.title)))
        if ok and job.on_done:
            try:
                job.on_done()
            except Exception as ex:
                self.log.emit(tr("Ошибка после установки: {}", ex))
        self.history.append(job)
        self.current, self.proc = None, None
        self.changed.emit()
        QTimer.singleShot(0, self._next_job)
