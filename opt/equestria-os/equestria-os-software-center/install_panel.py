"""
install_panel.py — in-app progress panel for pacman/flatpak/yay operations.

Replaces every Konsole popup in this app (install/remove, database refresh,
cache cleanup, system update...) with a themed panel that shows the same live
output, plus Cancel and, when something goes wrong, Retry/Repair.

Two things drove the design below:

1. Surviving the app being closed. The previous Konsole-based flows spawned a
   fully detached process on purpose (see the comment that used to sit on
   refresh_pacman_db in main.py) -- closing Software Center, or navigating
   away from it when it's embedded in equestria-os-settings, must not kill a
   database sync or install that's already running. QProcess does not give
   us that: Qt kills the child process when the QProcess object is destroyed.
   So the actual command runs as a plain subprocess.Popen with its output
   redirected to a temp file (never a pipe -- a pipe's reunplugged), and this
   dialog just polls that file with a QTimer. If the dialog/app goes away
   mid-run, the OS process keeps running and finishes on its own, exactly
   like the old detached Konsole did; we simply stop watching it.

2. Cancelling a pkexec-elevated pacman run is not a plain kill(). Once pkexec
   successfully execve()s into pacman as root, the pacman process is owned by
   uid 0, and a kill() sent by our own unprivileged process fails with EPERM
   no matter what (a kernel-level permission rule, not a pkexec quirk). The
   only way to actually stop it is to ask for another elevated action --
   'pkexec kill' -- the same authorization dialog the user already saw when
   the operation started.
"""

import os
import subprocess
import signal
import tempfile

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QProgressBar, QMessageBox,
)

# All code comments inside the script are written in English as requested

PACMAN_LOCK_PATH = "/var/lib/pacman/db.lck"
TEMP_LOG_DIR = os.path.join(tempfile.gettempdir(), "equestria-os-software-center")


def cleanup_old_logs(max_age_seconds=6 * 3600):
    """Best-effort sweep of leftover panel log files from past runs (see
    _start below) -- called once at app startup, same idea as
    utils.cleanup_screenshot_cache."""
    if not os.path.isdir(TEMP_LOG_DIR):
        return
    import time
    cutoff = time.time() - max_age_seconds
    for fname in os.listdir(TEMP_LOG_DIR):
        fpath = os.path.join(TEMP_LOG_DIR, fname)
        try:
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
        except OSError:
            pass


class InstallProgressDialog(QDialog):
    """Runs one program+args as a detached subprocess and tails its output.

    elevated=True means the process itself runs as root via pkexec, which
    changes how Cancel has to work (see module docstring, point 2).
    uses_pacman_db=True enables the post-failure stale-lock check (point 2's
    sibling problem: an interrupted pacman leaves /var/lib/pacman/db.lck
    behind even after the process is gone).
    """

    install_done = pyqtSignal(bool)  # emits True on a clean (exit code 0) finish

    POLL_MS = 150
    CANCEL_KILL_TIMEOUT_MS = 6000
    CANCEL_STUCK_TIMEOUT_MS = 10000
    PLAIN_KILL_TIMEOUT_MS = 3000

    def __init__(self, parent, t, title: str, program: str, args: list,
                 elevated: bool, uses_pacman_db: bool = False):
        super().__init__(parent)
        self.t = t
        self.program = program
        self.args = args
        self.elevated = elevated
        self.uses_pacman_db = uses_pacman_db

        self._proc = None
        self._log_path = None
        self._file_pos = 0
        self._pending = ""
        self._running = False
        self._success = False
        self._cancel_requested = False

        self.setObjectName("InstallProgressDialog")
        self.setWindowTitle(title)
        self.setMinimumSize(520, 360)
        self.setModal(False)
        self._load_stylesheet()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("InstallTitleLabel")
        layout.addWidget(self.lbl_title)

        self.lbl_status = QLabel(self.t("install.status_running"))
        self.lbl_status.setObjectName("InstallStatusLabel")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setObjectName("InstallProgressBar")
        self.progress.setRange(0, 0)  # indeterminate: pacman/flatpak don't give a clean overall %
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("InstallLogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        layout.addWidget(self.log_view, 1)

        buttons = QHBoxLayout()
        self.btn_repair = QPushButton(self.t("install.btn_repair"))
        self.btn_repair.setObjectName("CacheCleanBtn")
        self.btn_repair.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_repair.clicked.connect(self._do_repair)
        self.btn_repair.hide()

        self.btn_retry = QPushButton(self.t("install.btn_retry"))
        self.btn_retry.setObjectName("DetailActionBtn")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.clicked.connect(self._do_retry)
        self.btn_retry.hide()

        self.btn_cancel = QPushButton(self.t("install.btn_cancel"))
        self.btn_cancel.setObjectName("DetailBackBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._confirm_cancel)

        self.btn_close = QPushButton(self.t("install.btn_close"))
        self.btn_close.setObjectName("DetailActionBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)

        buttons.addWidget(self.btn_repair)
        buttons.addWidget(self.btn_retry)
        buttons.addStretch()
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_close)
        layout.addLayout(buttons)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)

        self._start()

    def _load_stylesheet(self):
        base_path = os.path.dirname(os.path.abspath(__file__))
        qss_path = os.path.join(base_path, "style.qss")
        if not os.path.exists(qss_path):
            return
        with open(qss_path, "r", encoding="utf-8") as f:
            base = base_path.replace("\\", "/")
            self.setStyleSheet(f.read().replace("{{BASE_PATH}}", base))

    # -------------------------------------------------------------------
    # Running the command
    # -------------------------------------------------------------------

    def _start(self):
        self._file_pos = 0
        self._pending = ""
        self._cancel_requested = False
        os.makedirs(TEMP_LOG_DIR, exist_ok=True)
        fd, self._log_path = tempfile.mkstemp(dir=TEMP_LOG_DIR, suffix=".log")
        try:
            with os.fdopen(fd, "wb") as log_fh:
                # start_new_session detaches from our controlling terminal/process
                # group -- belt and suspenders alongside not using QProcess, so
                # this survives our own process exiting, not just this dialog.
                self._proc = subprocess.Popen(
                    [self.program] + self.args,
                    stdout=log_fh, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError:
            self._running = False
            self._success = False
            self.lbl_status.setText(self.t("install.status_failed").replace("{0}", self.program))
            self.btn_close.setEnabled(True)
            self.install_done.emit(False)
            return

        self._running = True
        self.poll_timer.start(self.POLL_MS)

    def _poll(self):
        try:
            with open(self._log_path, "rb") as f:
                f.seek(self._file_pos)
                chunk = f.read()
                self._file_pos = f.tell()
        except OSError:
            chunk = b""
        if chunk:
            self._feed(chunk.decode("utf-8", "replace"))

        ret = self._proc.poll()
        if ret is not None:
            self.poll_timer.stop()
            self._finalize(ret)

    def _feed(self, data: str):
        self._pending += data.replace("\r\n", "\n")
        while True:
            idx_n = self._pending.find("\n")
            idx_r = self._pending.find("\r")
            if idx_n == -1 and idx_r == -1:
                break
            if idx_r != -1 and (idx_n == -1 or idx_r < idx_n):
                line, self._pending = self._pending[:idx_r], self._pending[idx_r + 1:]
                self._show_live_line(line)
            else:
                line, self._pending = self._pending[:idx_n], self._pending[idx_n + 1:]
                self._commit_line(line)
        if self._pending:
            self._show_live_line(self._pending)

    def _commit_line(self, line: str):
        if line.strip():
            self.log_view.appendPlainText(line)
            self.lbl_status.setText(line.strip())

    def _show_live_line(self, line: str):
        # Progress-bar-style '\r' updates (download percentages, etc.) -- shown
        # as the current status only, not spammed into the scrollable log.
        if line.strip():
            self.lbl_status.setText(line.strip())

    # -------------------------------------------------------------------
    # Completion
    # -------------------------------------------------------------------

    def _finalize(self, exit_code):
        self._running = False
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)

        if self._cancel_requested:
            self._success = False
            self.lbl_status.setText(self.t("install.status_cancelled"))
            self.lbl_status.setObjectName("InstallStatusWarn")
            self.btn_retry.show()
        elif exit_code == 0:
            self._success = True
            self.lbl_status.setText(self.t("install.status_success"))
            self.lbl_status.setObjectName("InstallStatusOk")
        else:
            self._success = False
            self.lbl_status.setText(self.t("install.status_failed").replace("{0}", str(exit_code)))
            self.lbl_status.setObjectName("InstallStatusError")
            self.btn_retry.show()
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

        if not self._success:
            self._check_recoverable()

        self.install_done.emit(self._success)

    # -------------------------------------------------------------------
    # Stale pacman lock recovery (only relevant after a cancel/failure)
    # -------------------------------------------------------------------

    def _pacman_process_running(self) -> bool:
        try:
            r = subprocess.run(["pgrep", "-x", "pacman"], capture_output=True, timeout=3)
            return r.returncode == 0
        except Exception:
            # Can't verify -- assume it might still be running rather than
            # risk deleting a lock that's actually protecting a live transaction.
            return True

    def _check_recoverable(self):
        if not self.uses_pacman_db:
            return
        if not os.path.exists(PACMAN_LOCK_PATH):
            return
        if self._pacman_process_running():
            return
        self.lbl_status.setText(self.lbl_status.text() + "  " + self.t("install.lock_stale"))
        self.btn_repair.show()

    def _do_repair(self):
        self.btn_repair.setEnabled(False)
        self.log_view.appendPlainText(self.t("install.repairing"))
        try:
            r = subprocess.run(["pkexec", "rm", "-f", PACMAN_LOCK_PATH], timeout=30)
            ok = r.returncode == 0 and not os.path.exists(PACMAN_LOCK_PATH)
        except Exception:
            ok = False

        if ok:
            self.log_view.appendPlainText(self.t("install.repair_done"))
            self.btn_repair.hide()
        else:
            self.log_view.appendPlainText(self.t("install.repair_failed"))
            self.btn_repair.setEnabled(True)

    def _do_retry(self):
        self.btn_retry.hide()
        self.btn_repair.hide()
        self.btn_close.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setRange(0, 0)
        self.log_view.appendPlainText("")
        self.log_view.appendPlainText("--- " + self.t("install.retrying") + " ---")
        self.lbl_status.setObjectName("InstallStatusLabel")
        self.lbl_status.setText(self.t("install.status_running"))
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self._start()

    # -------------------------------------------------------------------
    # Cancel
    # -------------------------------------------------------------------

    def _confirm_cancel(self):
        if not self._running:
            return
        box = QMessageBox(self)
        box.setWindowTitle(self.t("install.cancel_confirm_title"))
        box.setText(self.t("install.cancel_confirm_text"))
        btn_yes = box.addButton(self.t("install.cancel_yes"), QMessageBox.ButtonRole.DestructiveRole)
        btn_no = box.addButton(self.t("install.cancel_no"), QMessageBox.ButtonRole.RejectRole)
        btn_yes.setObjectName("CacheCleanBtn")
        btn_no.setObjectName("DetailBackBtn")
        for b in (btn_yes, btn_no):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumSize(110, 36)
            b.style().unpolish(b)
            b.style().polish(b)
        box.exec()
        if box.clickedButton() is btn_yes:
            self._do_cancel()

    def _do_cancel(self):
        if not self._running or self._proc is None:
            return
        self._cancel_requested = True
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText(self.t("install.cancelling"))

        pid = self._proc.pid
        if self.elevated:
            # See module docstring, point 2: this process runs as root, so
            # stopping it needs its own pkexec call rather than a plain signal.
            subprocess.Popen(["pkexec", "kill", "-TERM", str(pid)])
            QTimer.singleShot(self.CANCEL_KILL_TIMEOUT_MS, lambda: self._escalate_cancel(pid))
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            QTimer.singleShot(self.PLAIN_KILL_TIMEOUT_MS, lambda: self._force_kill(pid))

        # If the elevated kill's own auth prompt gets dismissed/denied, don't
        # leave Cancel stuck disabled forever -- let the user try again.
        QTimer.singleShot(self.CANCEL_STUCK_TIMEOUT_MS, self._reset_cancel_if_still_running)

    def _escalate_cancel(self, pid):
        if self._running:
            subprocess.Popen(["pkexec", "kill", "-KILL", str(pid)])

    def _force_kill(self, pid):
        if self._running:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _reset_cancel_if_still_running(self):
        if self._running:
            self._cancel_requested = False
            self.btn_cancel.setEnabled(True)
            self.lbl_status.setText(self.t("install.status_running"))

    # -------------------------------------------------------------------

    def reject(self):
        # Esc / the window's [X]: the underlying task survives regardless (see
        # module docstring, point 1), so just close the viewer -- no need to
        # confirm anything the way the Cancel button does.
        super().reject()
