"""Asynchronous CLI operations. Keep separate project and account operations independent."""
import json
import re
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from library import executable
from kit import tr


class Jobs(QObject):
    message = pyqtSignal(str)
    activity = pyqtSignal()
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(object, bool)  # title, success: lets the window show the result

    def __init__(self, parent):
        super().__init__(parent)
        self.running = {}
        self.quiet = set()  # status reads: kept out of the top bar and the log

    def active(self):
        return {key: value for key, value in self.running.items() if key not in self.quiet}

    def run(self, key, title, arguments, done=None, *, structured=False, failed=None):
        cli = executable("unity")
        if not cli:
            self.message.emit(str(tr("cli.hint")))
            if failed:
                failed(tr("cli.hint"))
            return
        args = ["--no-pager", "--no-color"]
        if arguments[:2] != ["auth", "login"]:
            args.append("--non-interactive")
        if structured:
            args += ["--format", "json"]
        self.run_process(key, title, cli, args + arguments, done, structured=structured, failed=failed,
                         environment=self.cli_environment())

    def cli_environment(self):
        """Launcher settings that reach the Unity CLI through its environment."""
        config = self.parent().config
        env = {}
        folder = config.get("download_dir")
        if folder:
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
                env.update(TMPDIR=folder, TMP=folder, TEMP=folder)  # the CLI downloads into the temp directory
            except OSError as error:
                self.message.emit(str(error))
        retries = config.get("install_retries")
        if isinstance(retries, int) and retries >= 0:
            env["UNITY_INSTALL_RETRIES"] = str(retries)
        return env

    def run_process(self, key, title, program, arguments, done=None, *, structured=False,
                    capture=False, failed=None, cwd=None, environment=None, quiet=False):
        if key in self.running:
            self.message.emit(self.running[key][0] + " …")
            return
        process = QProcess(self)
        if cwd is not None:
            process.setWorkingDirectory(str(cwd))
        if key.startswith("git:") or environment:
            env = QProcessEnvironment.systemEnvironment()
            if key.startswith("git:"):
                env.insert("GIT_TERMINAL_PROMPT", "0")
            for name, value in (environment or {}).items():
                env.insert(name, value)
            process.setProcessEnvironment(env)
        self.running[key] = (title, process)
        if quiet:
            self.quiet.add(key)
        else:
            self.activity.emit()
        payload = bytearray()

        def report(text):
            if text and not quiet:
                self.message.emit(text)
                if key == "install":
                    percentages = re.findall(r"(?<![\d.])(100|\d{1,2})(?:[.,]\d+)?\s*%", text)
                    if percentages:
                        self.progress.emit(key, int(percentages[-1]))

        def output():
            chunk = bytes(process.readAllStandardOutput())
            if structured or capture:
                payload.extend(chunk)
            elif chunk.strip():
                report(chunk.decode(errors="replace").strip())

        error_tail = ""

        def errors():
            nonlocal error_tail
            chunk = bytes(process.readAllStandardError()).decode(errors="replace").strip()
            if chunk:
                error_tail = (error_tail + "\n" + chunk)[-1800:]
            report(chunk)

        def finish(code, *_):
            if key not in self.running:
                return
            output()
            errors()
            data = bytes(payload) if capture else None
            ok = code == 0
            detail = error_tail.strip()
            if structured:
                try:
                    reply = json.loads(payload)
                    ok = ok and reply["success"]
                    data = reply["data"]
                    for warning in reply.get("warnings", []):
                        self.message.emit(str(warning))
                    for item in reply.get("errors", []):
                        detail = str(item["message"])
                        self.message.emit(detail)
                except (ValueError, KeyError, TypeError):
                    self.message.emit(process.errorString() if not payload else payload.decode(errors="replace")[:1000])
                    ok = False
            del self.running[key]
            self.quiet.discard(key) if quiet else None
            if ok and done:
                try:
                    done(data)
                except (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError) as error:
                    detail = str(error)
                    self.message.emit(detail)
                    ok = False
            if not ok and failed:
                failed(detail or str(code))
            if not quiet:
                self.message.emit(f"{'✓' if ok else '✗'} {title} ({code})")
                self.finished.emit(title, ok)
            process.deleteLater()
            if not quiet:
                self.activity.emit()

        def failure(error):
            if error == QProcess.ProcessError.FailedToStart:
                self.message.emit(process.errorString())
                finish(-1)

        process.readyReadStandardOutput.connect(output)
        process.readyReadStandardError.connect(errors)
        process.finished.connect(finish)
        process.errorOccurred.connect(failure)
        self.message.emit("› " + str(title))
        process.start(program, arguments)
