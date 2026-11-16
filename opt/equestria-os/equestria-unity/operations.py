"""The operations panel under the top bar: what is running, what waits in the queue, what has just finished."""
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout

from kit import call, tr


class OperationsPanel(QFrame):
    """Each operation with its own progress and its own Cancel, like the downloads list of Unity Hub."""

    def __init__(self, jobs, show_log, parent):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("operations")
        self.setMinimumWidth(440)
        self.jobs = jobs
        self.show_log = show_log
        self.bars = {}       # key -> (progress bar, status label) of running operations
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        head = QHBoxLayout()
        title = call(QLabel, tr("ops.title"))
        title.setObjectName("rowname")
        head.addWidget(title)
        head.addStretch()
        self.clear = self.flat_button(head, tr("ops.clear"), jobs.clear_history)
        self.flat_button(head, tr("jobs.log"), self.open_log)
        layout.addLayout(head)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(6)
        layout.addLayout(self.rows)
        self.empty = call(QLabel, tr("ops.empty"))
        self.empty.setObjectName("hint")
        layout.addWidget(self.empty)
        jobs.activity.connect(self.rebuild)
        jobs.progress.connect(self.progressed)

    @staticmethod
    def flat_button(layout, text, callback):
        button = call(QPushButton, text)
        button.setObjectName("flat")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: callback())
        layout.addWidget(button)
        return button

    def popup(self, anchor):
        self.rebuild(force=True)
        self.adjustSize()
        self.move(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        self.show()

    def open_log(self):
        self.hide()
        self.show_log()

    # ---- rows -----------------------------------------------------------------------------------

    def rebuild(self, force=False):
        if not (force or self.isVisible()):
            return
        while self.rows.count():
            widget = self.rows.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.bars = {}
        for key, (title, _) in self.jobs.active().items():
            self.add_row(title, tr("ops.running"), lambda k=key, t=title: self.cancel(k, t), key=key)
        for key, title, _ in self.jobs.waiting:
            self.add_row(title, tr("install.queued"), lambda k=key, t=title: self.cancel(k, t, queued=True))
        for title, ok, stamp in reversed(self.jobs.history):
            state = tr("ops.done" if ok else "ops.failed")
            self.add_row(("✓  " if ok else "✗  ") + str(title), f"{state} · {time.strftime('%H:%M', time.localtime(stamp))}",
                         None, level="ok" if ok else "fail")
        self.empty.setVisible(not self.rows.count())
        self.clear.setVisible(bool(self.jobs.history))
        if self.isVisible():
            self.adjustSize()

    def add_row(self, title, status, cancel, *, key=None, level=""):
        row = QFrame()
        row.setObjectName("oprow")
        row.setProperty("lvl", level)
        box = QVBoxLayout(row)
        box.setContentsMargins(12, 8, 8, 8)
        box.setSpacing(6)
        top = QHBoxLayout()
        name = QLabel(str(title))
        name.setObjectName("cellname")
        top.addWidget(name, 1)
        state = QLabel(str(status))
        state.setObjectName("hint")
        top.addWidget(state)
        if cancel:
            stop = QPushButton("✕")
            stop.setObjectName("flat")
            stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            call(stop.setToolTip, tr("jobs.cancel_short"))
            stop.clicked.connect(lambda: cancel())
            top.addWidget(stop)
        box.addLayout(top)
        if key is not None:
            bar = QProgressBar()
            bar.setTextVisible(False)
            percent = self.jobs.percent.get(key)
            bar.setRange(0, 0 if percent is None else 100)
            if percent is not None:
                bar.setValue(percent)
                state.setText(f"{percent}%")
            box.addWidget(bar)
            self.bars[key] = (bar, state)
        self.rows.addWidget(row)

    def progressed(self, key, percent):
        if key in self.bars:
            bar, state = self.bars[key]
            bar.setRange(0, 100)
            bar.setValue(percent)
            state.setText(f"{percent}%")

    def cancel(self, key, title, queued=False):
        self.hide()  # the question below would close the popup anyway
        if QMessageBox.question(self.parentWidget(), self.parentWidget().windowTitle(), tr("jobs.confirm_cancel", title),
                                defaultButton=QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.jobs.cancel(key, title if queued else None)
