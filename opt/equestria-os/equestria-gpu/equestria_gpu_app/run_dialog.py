"""gpu: run dialog."""
from __future__ import annotations

import shlex
from PyQt6.QtCore import QProcess
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout
from .localization import live_i18n, tr
from .widgets import clean_line


class RunDialog(QDialog):
    """Окно журнала: запускает команду и показывает вывод в реальном времени."""

    def __init__(self, parent, title: str, cmd: list):
        super().__init__(parent)
        live_i18n.call(self.setWindowTitle, title)
        self.resize(820, 540)
        self.buf = ""
        self.running = True
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)
        head = live_i18n.call(QLabel, title)
        head.setObjectName("title")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(6000)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.status = live_i18n.call(QLabel, tr("run_dialog.running_system_will_ask_administrator"))
        self.status.setObjectName("hint")
        self.btn = live_i18n.call(QPushButton, tr("run_dialog.cancel"))
        self.btn.clicked.connect(self._click)
        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(self.btn)
        v.addWidget(head)
        v.addWidget(self.log, 1)
        v.addLayout(row)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self.log.appendPlainText("$ " + live_i18n.join_text(' ', ((shlex.quote(x) for x in cmd))))
        self.proc.start(cmd[0], cmd[1:])

    def _emit(self, text: str, flush: bool = False) -> None:
        self.buf += text
        lines = self.buf.split("\n")
        self.buf = "" if flush else lines.pop()
        for ln in lines:
            ln = clean_line(ln)
            if ln.strip() or flush:
                self.log.appendPlainText(ln)

    def _read(self) -> None:
        self._emit(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"))

    def _finished(self, code, _status) -> None:
        self._emit(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"), flush=True)
        self.running = False
        live_i18n.call(self.btn.setText, tr("run_dialog.close"))
        if code == 0:
            live_i18n.call(self.status.setText, tr("run_dialog.done_if_driver_was_changed"))
        elif code in (126, 127):
            live_i18n.call(self.status.setText, tr("run_dialog.authorization_was_rejected_pkexec_unavailable"))
        else:
            live_i18n.call(self.status.setText, tr("run_dialog.finished_with_code_details_log", code))

    def _error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.running = False
            self.log.appendPlainText(tr("run_dialog.could_not_start_pkexec_install"))
            live_i18n.call(self.btn.setText, tr("run_dialog.close"))
            live_i18n.call(self.status.setText, tr("run_dialog.launch_error"))

    def _click(self) -> None:
        if self.running:
            self.proc.terminate()
        else:
            self.accept()

    def reject(self) -> None:
        if self.running:
            self.proc.terminate()
            self.proc.waitForFinished(1500)
        super().reject()
