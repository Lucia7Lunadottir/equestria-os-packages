"""Asynchronous operations (Unity CLI, Git). Keep separate project and account operations independent.

A running program is a Job; how its standard output is read is an Output strategy:
TextOutput shows it in the log, CaptureOutput hands the bytes over, JsonEnvelopeOutput reads the Unity CLI's
`{"success", "data", "errors", "warnings"}` reply."""
import json
import re
import time
from collections import deque

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from cli_errors import TIMEOUT, CliError

PERCENT = re.compile(r"(?<![\d.])(100|\d{1,2})(?:[.,]\d+)?\s*%")


# ---- what a job does with its standard output -------------------------------------------------------

class Output:
    def feed(self, chunk):
        """A piece of stdout arrived. Returns text for the log, or "" to keep it."""
        return ""

    def finish(self, ok, detail, report):
        """(ok, data handed to `done`, detail) once the program has ended."""
        return ok, None, detail


class TextOutput(Output):
    def __init__(self):
        self.tail = ""

    def feed(self, chunk):
        text = chunk.decode(errors="replace").strip()
        self.tail = (self.tail + "\n" + text)[-1800:]
        return text

    def finish(self, ok, detail, report):
        # Some programs explain a failure on stdout (git: "CONFLICT … Automatic merge failed").
        return ok, None, detail or self.tail.strip()


class CaptureOutput(Output):
    def __init__(self):
        self.payload = bytearray()

    def feed(self, chunk):
        self.payload.extend(chunk)
        return ""

    def finish(self, ok, detail, report):
        return ok, bytes(self.payload), detail


class JsonEnvelopeOutput(CaptureOutput):
    def finish(self, ok, detail, report):
        try:
            reply = json.loads(self.payload)
            for warning in reply.get("warnings", []):
                report(str(warning))
            for item in reply.get("errors", []):
                detail = CliError(str(item["message"]), str(item.get("code") or ""))
                report(detail)
            return ok and reply["success"], reply["data"], detail
        except (ValueError, KeyError, TypeError):
            detail = detail or self.payload.decode(errors="replace")[:1000]
            report(detail)
            return False, None, detail


class Job(QObject):
    """One program run. `ended(ok, data, detail, code)` is emitted once, after the last output was read."""
    text = pyqtSignal(str)            # a line for the log
    percent = pyqtSignal(int)
    ended = pyqtSignal(bool, object, object, int)   # ok, data, detail (str or CliError), exit code

    def __init__(self, title, program, arguments, output, *, cwd=None, environment=None, progress=False,
                 timeout=0, parent=None):
        """timeout: seconds after which a program that has not ended is stopped (0: never)."""
        super().__init__(parent)
        self.timeout = timeout
        self.timed_out = False
        self.title = title
        self.program = program
        self.arguments = arguments
        self.output = output
        self.progress = progress
        self.error_tail = ""
        self.done_once = False
        self.process = QProcess(self)
        if cwd is not None:
            self.process.setWorkingDirectory(str(cwd))
        if environment:
            env = QProcessEnvironment.systemEnvironment()
            for name, value in environment.items():
                env.insert(name, value)
            self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.finished.connect(lambda code, *_: self.finish(code))
        self.process.errorOccurred.connect(self.failure)

    def start(self):
        self.process.start(self.program, self.arguments)
        if self.timeout:
            QTimer.singleShot(self.timeout * 1000, self.expire)

    def expire(self):
        """A program that hangs (a Unity service that does not answer) must not block the launcher forever."""
        if self.done_once or self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.timed_out = True
        self.process.terminate()
        QTimer.singleShot(3000, lambda: self.done_once or self.process.kill())

    def terminate(self):
        self.process.terminate()

    def report(self, text):
        if text:
            self.text.emit(text)
            if self.progress:
                found = PERCENT.findall(text)
                if found:
                    self.percent.emit(int(found[-1]))

    def read_output(self):
        chunk = bytes(self.process.readAllStandardOutput())
        if chunk.strip():
            self.report(self.output.feed(chunk))

    def read_errors(self):
        chunk = bytes(self.process.readAllStandardError()).decode(errors="replace").strip()
        if chunk:
            self.error_tail = (self.error_tail + "\n" + chunk)[-1800:]
        self.report(chunk)

    def failure(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.report(self.process.errorString())
            self.error_tail = self.error_tail or self.process.errorString()
            self.finish(-1)

    def finish(self, code):
        if self.done_once:
            return
        self.done_once = True
        self.read_output()
        self.read_errors()
        ok, data, detail = self.output.finish(code == 0, self.error_tail.strip(), self.report)
        if self.timed_out:
            ok, detail = False, CliError(f"timeout {self.timeout}", TIMEOUT)
        self.ended.emit(ok, data, detail, code)


class Jobs(QObject):
    message = pyqtSignal(str)
    activity = pyqtSignal()               # something started, finished, was queued or cancelled
    progress = pyqtSignal(str, int)       # key, percent
    finished = pyqtSignal(object, bool)   # title, success: lets the window show the result

    def __init__(self, parent):
        super().__init__(parent)
        self.running = {}                 # key -> (title, job)
        self.quiet = set()                # status reads: kept out of the top bar and the log
        self.percent = {}                 # key -> last percent the program reported
        self.waiting = []                 # (key, title, start) of queued operations, oldest first
        self.history = deque(maxlen=12)   # (title, ok, time) of finished operations, newest last

    def active(self):
        return {key: value for key, value in self.running.items() if key not in self.quiet}

    def busy(self):
        """Running or queued operations the user started."""
        return bool(self.active() or self.waiting)

    def cancel(self, key, title=None):
        """Stop a running operation, or take a queued one (identified by its title) out of the queue."""
        if title is not None:
            self.waiting = [entry for entry in self.waiting if not (entry[0] == key and entry[1] == title)]
            self.activity.emit()
        elif key in self.running:
            self.running[key][1].terminate()

    def clear_history(self):
        self.history.clear()
        self.activity.emit()

    def run_process(self, key, title, program, arguments, done=None, *, structured=False, capture=False,
                    failed=None, cwd=None, environment=None, quiet=False, progress=False, queue=False, timeout=0):
        """structured: stdout is the CLI's JSON envelope; capture: stdout bytes go to `done`;
        progress: percentages in the output are reported; queue: wait for a running operation with the same key;
        quiet: a status read that stays out of the log and the top bar."""
        if key in self.running:
            if queue:
                start = lambda: self.run_process(key, title, program, arguments, done, structured=structured,
                                                 capture=capture, failed=failed, cwd=cwd, environment=environment,
                                                 quiet=quiet, progress=progress, timeout=timeout)
                self.waiting.append((key, title, start))
                self.message.emit(f"⏸ {title}")
                self.activity.emit()
            elif not quiet:
                self.message.emit(self.running[key][0] + " …")
            return
        output = JsonEnvelopeOutput() if structured else CaptureOutput() if capture else TextOutput()
        job = Job(title, program, arguments, output, cwd=cwd, environment=environment, progress=progress,
                  timeout=timeout, parent=self)
        self.running[key] = (title, job)
        if quiet:
            self.quiet.add(key)
        else:
            job.text.connect(self.message)
            job.percent.connect(lambda value: self.reported(key, value))
            self.message.emit("› " + str(title))
            self.activity.emit()
        job.ended.connect(lambda ok, data, detail, code: self.ended(key, job, ok, data, detail, code, done, failed))
        job.start()

    def reported(self, key, value):
        self.percent[key] = value
        self.progress.emit(key, value)

    def ended(self, key, job, ok, data, detail, code, done, failed):
        quiet = key in self.quiet
        del self.running[key]
        self.percent.pop(key, None)
        self.quiet.discard(key)
        if ok and done:
            try:
                done(data)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError) as error:
                detail = str(error)
                if not quiet:
                    self.message.emit(detail)
                ok = False
        if not ok and failed:
            failed(detail or str(code))
        if not quiet:
            self.message.emit(f"{'✓' if ok else '✗'} {job.title} ({code})")
            self.history.append((job.title, ok, time.time()))
            self.finished.emit(job.title, ok)
        job.deleteLater()
        following = next((entry for entry in self.waiting if entry[0] == key), None)
        if following:
            self.waiting.remove(following)
            following[2]()
        elif not quiet:
            self.activity.emit()
