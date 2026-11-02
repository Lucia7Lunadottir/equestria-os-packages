from __future__ import annotations


from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget

from equestria_ue.kit import tr
from equestria_ue.ui.widgets import card_frame, small_btn, title_row
from equestria_ue.versions import PREBUILT_SIZE


class DownloadsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.jobs = win.jobs
        self.store = win.store
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(14)
        clear = small_btn(tr("Очистить журнал"))
        v.addLayout(title_row(tr("Загрузки и сборка"), clear))
        hero = card_frame("hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(8)
        self.job = QLabel("")
        self.job.setObjectName("rowname")
        self.step = QLabel("")
        self.step.setObjectName("hint")
        self.step.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.queue = QLabel("")
        self.queue.setObjectName("hint")
        self.cancel = QPushButton(tr("Отменить"))
        self.cancel.setObjectName("danger")
        self.cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel.clicked.connect(lambda: (self.store.cancel(), self.jobs.cancel()))
        self.pause = QPushButton(tr("Пауза"))
        self.pause.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pause.clicked.connect(self.store.toggle_pause)
        row = QHBoxLayout()
        row.addWidget(self.queue, 1)
        row.addWidget(self.pause)
        row.addWidget(self.cancel)
        for w in (self.job, self.step, self.bar):
            hl.addWidget(w)
        hl.addLayout(row)
        v.addWidget(hero)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(20000)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log.setPlaceholderText(tr("Здесь появится журнал установки и сборки."))
        v.addWidget(self.log, 1)
        clear.clicked.connect(self.log.clear)
        self.jobs.log.connect(self.log.appendPlainText)
        self.jobs.changed.connect(self.refresh)
        self.store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        j, d = self.jobs, self.store.dl
        if d:
            tot = d["total"] or PREBUILT_SIZE
            self.pause.setVisible(True)
            self.pause.setText(tr("Продолжить") if d.get("paused") else tr("Пауза"))
            self.job.setText((tr("⏸ Пауза") if d.get("paused") else tr("Скачивание")) + f" · {d['name']}")
            sp = tr(" · {:.0f} МБ/с", d["speed"] / 1e6) if d["speed"] else ""
            left = tr(" · осталось ≈{} мин", int((tot - d["recv"]) / d["speed"] / 60)) if d["speed"] > 1e5 else ""
            self.step.setText(tr("{:.2f} из {:.2f} ГБ", d["recv"] / 1e9, tot / 1e9) + sp + left)
            self.bar.setValue(int(min(d["recv"] / tot, 1) * 100))
            self.cancel.setEnabled(True)
            self.queue.setText("")
            return
        self.pause.setVisible(False)
        self.job.setText(j.current.title if j.current else tr("Нет активных задач"))
        self.step.setText(j.step_label if j.current else
                          (tr("Последняя: {} — {}", j.history[-1].title, tr("готово") if j.history[-1].ok else tr("не выполнено"))
                           if j.history else ""))
        self.bar.setValue(int(j.progress) if j.current else 0)
        self.cancel.setEnabled(j.current is not None)
        self.queue.setText(tr("В очереди: {}", len(j.queue)) if j.queue else "")
