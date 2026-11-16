"""The pill in the top bar: running operations with their progress, or a short message that fades away."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton

from equestria_kit.live_i18n import format_text, join_text
from kit import call, tr
from operations import OperationsPanel


class JobStatusPill(QFrame):
    def __init__(self, jobs, show_log, window):
        super().__init__()
        self.setObjectName("pill")
        self.jobs = jobs
        self.host = window
        self.operations = OperationsPanel(jobs, show_log, window)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_notice)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 8, 6)
        layout.setSpacing(10)
        self.notice = QLabel()
        layout.addWidget(self.notice)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setFixedWidth(90)
        layout.addWidget(self.busy)
        self.cancel = self.flat(layout, tr("jobs.cancel_short"), self.cancel_job)
        self.details = self.flat(layout, tr("jobs.details"), self.show_operations)
        self.setVisible(False)
        jobs.activity.connect(self.job_status)
        jobs.progress.connect(self.job_progress)
        jobs.finished.connect(self.job_finished)
        self.job_status()

    @staticmethod
    def flat(layout, text, callback):
        button = call(QPushButton, text)
        button.setObjectName("flat")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: callback())
        layout.addWidget(button)
        return button

    def set_level(self, level):
        self.setProperty("lvl", level)
        self.style().unpolish(self)
        self.style().polish(self)

    def notify(self, text, level="", ms=5000):
        """A short message. level: '', 'busy', 'ok' or 'fail'."""
        if self.jobs.active() and level != "fail":
            return  # a running operation owns the pill
        call(self.notice.setText, text)
        self.set_level(level)
        self.busy.setRange(0, 0)
        self.busy.setVisible(level == "busy")
        self.cancel.setVisible(False)
        self.details.setVisible(level == "fail")
        self.setVisible(True)
        self.hide_timer.start(ms)

    def hide_notice(self):
        if not self.jobs.active():
            self.setVisible(False)

    def show_operations(self):
        self.operations.popup(self)

    def job_progress(self, key, percent):
        if key in self.jobs.running:
            self.busy.setRange(0, 100)
            self.busy.setValue(percent)
            call(self.notice.setText, format_text("{} · {}%", self.jobs.running[key][0], percent))

    def job_status(self):
        """Operations in progress are always visible in the top bar, not only in the log."""
        if self.jobs.busy():
            self.busy.setRange(0, 0)
            self.hide_timer.stop()
            names = join_text(" · ", (name for name, _ in self.jobs.active().values()))
            waiting = len(self.jobs.waiting)
            call(self.notice.setText, tr("jobs.working_queue", names, waiting) if waiting else tr("jobs.working", names))
            self.set_level("")
            self.busy.setVisible(True)
            self.cancel.setVisible(True)
            self.details.setVisible(True)
            self.setVisible(True)
        elif self.property("lvl") in (None, "", "busy") and not self.hide_timer.isActive():
            self.setVisible(False)

    def job_finished(self, title, ok):
        self.notify(("✓  " if ok else "✗  ") + title, "ok" if ok else "fail", 6000 if ok else 20000)

    def cancel_job(self):
        """One operation: ask and stop it. Several, or a queue: show them all, each with its own Cancel."""
        active = self.jobs.active()
        if len(active) != 1 or self.jobs.waiting:
            self.show_operations()
            return
        key, (title, _) = next(iter(active.items()))
        if QMessageBox.question(self.host, self.host.windowTitle(), tr("jobs.confirm_cancel", title),
                                defaultButton=QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.jobs.cancel(key)
