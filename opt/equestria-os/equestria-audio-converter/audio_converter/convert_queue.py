"""Очередь ffmpeg: запускает файлы по одному, читает прогресс, умеет отменять."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QProcess, pyqtSignal
from PyQt6.QtWidgets import QListWidgetItem

from ._kit import tr
from .commands import parse_progress
from .probe import probe_duration


@dataclass
class Job:
    """Один файл очереди. build(длительность) -> команда ffmpeg."""
    src: str
    dst: Path
    name: str
    build: Callable[[float | None], list]
    item: QListWidgetItem | None = None
    length: Callable[[float | None], float | None] | None = None  # длина результата по длине исходника
    dur: float | None = None
    out_dur: float | None = None
    ok: bool | None = None          # None — до этого файла очередь не дошла


class ConvertQueue(QObject):
    """Об окне ничего не знает — сообщает всё сигналами."""
    job_started = pyqtSignal(int, int, object)   # номер файла, всего, Job
    job_progress = pyqtSignal(object, int)       # Job, проценты
    job_done = pyqtSignal(object, list)          # Job (job.ok — итог), последние строки ffmpeg
    finished = pyqtSignal()

    TAIL = 20  # сколько строк вывода ffmpeg хранить для сообщения об ошибке

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs: list[Job] = []
        self.cur = -1
        self.proc: QProcess | None = None
        self.buf = ""
        self.tail: list[str] = []
        self.cancelled = False

    def start(self, jobs: list[Job]) -> None:
        self.jobs = jobs
        self.cancelled = False
        self.cur = 0
        self._start_job()

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc:
            self.proc.kill()

    def counts(self) -> tuple[int, int]:
        """(сколько готово, сколько с ошибкой)."""
        return (sum(1 for j in self.jobs if j.ok),
                sum(1 for j in self.jobs if j.ok is False))

    def _start_job(self) -> None:
        if self.cancelled or self.cur >= len(self.jobs):
            self.finished.emit()
            return
        j = self.jobs[self.cur]
        j.dur = probe_duration(j.src)
        j.out_dur = j.length(j.dur) if j.length else j.dur
        cmd = j.build(j.dur)
        self.buf, self.tail = "", []
        self.job_started.emit(self.cur, len(self.jobs), j)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._proc_error)
        self.proc.start(cmd[0], cmd[1:])

    def _read(self) -> None:
        j = self.jobs[self.cur]
        self.buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines = self.buf.split("\n")
        self.buf = lines.pop()
        for line in lines:
            t = parse_progress(line)
            if t is not None:
                if j.out_dur:
                    self.job_progress.emit(j, min(99, int(t / j.out_dur * 100)))
            elif line.strip() and "=" not in line.split(" ")[0]:
                self.tail.append(line.strip())
                self.tail = self.tail[-self.TAIL:]

    def _proc_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.tail = [tr("convert_queue.ffmpeg_did_not_start")]
            self._done(-1, QProcess.ExitStatus.CrashExit)

    def _done(self, code: int, status) -> None:
        if self.cur >= len(self.jobs) or self.proc is None:
            return
        j = self.jobs[self.cur]
        proc, self.proc = self.proc, None
        proc.deleteLater()
        j.ok = code == 0 and status == QProcess.ExitStatus.NormalExit and not self.cancelled
        if not j.ok:
            Path(j.dst).unlink(missing_ok=True)  # убираем недоделанный файл
        self.job_done.emit(j, list(self.tail))
        self.cur += 1
        self._start_job()
