#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Equestria Unity Log — маленькое окошко, которое смотрит в лог Unity и говорит,
как дела: какой шейдер компилируется прямо сейчас и что было в последних строках.
Unity при этом не трогается — программа только читает файл лога.

Запуск:   python3 logwatch.py                 (спросит файл лога)
          python3 logwatch.py /путь/Editor.log (без вопроса)
Зависимость: PyQt6. Цвета — из общих тем Equestria OS (папка equestria_kit).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics, QIcon
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout,
                             QLabel, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from localization import APP_ID, catalog, live_i18n, tr
from equestria_kit import qt as kit_qt
from logview import LogView
from logcore import BuildTracker, LogTailer, ProcMonitor, classify, level, parse_shader

POLL_MS = 250          # как часто смотрим в файл
SHADER_ACTIVE_S = 3.0  # столько секунд после строки про шейдер считаем, что компиляция идёт
WORK_ACTIVE_S = 5.0    # то же для скриптов и билда
ERROR_SHOW_S = 10.0    # столько секунд после ошибки точка красная

QSS = """
QWidget { background: @base@; color: @text@; font-size: 13px; }
QLabel { background: transparent; }
QToolTip { background: @surface1@; color: @text@; border: 1px solid @surface2@; padding: 4px; }
#card { background: @surface0@; border-radius: 12px; }
#h2 { color: @subtext@; font-size: 11px; font-weight: 600; }
#shader { color: @accent@; font-size: 20px; font-weight: 700; }
#shader[stale="true"] { color: @subtext@; }
#detail, #path { color: @subtext@; }
#status { font-weight: 600; }
QLabel#dot { font-size: 16px; color: @surface2@; }
QLabel#dot[state="busy"] { color: @yellow@; }
QLabel#dot[state="idle"] { color: @green@; }
QLabel#dot[state="error"] { color: @red@; }
QListWidget { background: @surface0@; border: 0; }
QScrollBar { background: @surface0@; border: none; margin: 0; }
QScrollBar:vertical { width: 10px; }
QScrollBar:horizontal { height: 10px; }
QScrollBar::handle { background: @surface2@; border-radius: 5px; }
QScrollBar::handle:vertical { min-height: 28px; }
QScrollBar::handle:horizontal { min-width: 28px; }
QScrollBar::handle:hover, QScrollBar::handle:pressed { background: @accent@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QPushButton { background: @surface1@; border: none; border-radius: 8px; padding: 6px 12px; }
QPushButton:hover { background: @surface2@; }
QProgressBar { background: @surface1@; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }
QProgressBar::chunk { background: @accent@; border-radius: 4px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked { image: url(@icon:cb_unchecked@); }
QCheckBox::indicator:unchecked:hover { image: url(@icon:cb_unchecked_hover@); }
QCheckBox::indicator:checked { image: url(@icon:cb_checked@); }
"""


class ElideLabel(QLabel):
    """Одна строка, которая не раздувает окно: длинный текст обрезается «…»."""

    def __init__(self, text: str = "", elide=Qt.TextElideMode.ElideRight):
        super().__init__()
        self._full, self._mode = "", elide
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self.set_full(text)

    def set_full(self, text: str) -> None:
        if text != self._full or not self.text():
            self._full = text
            self.setToolTip(text if len(text) > 40 else "")
            self._apply()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._apply()

    def _apply(self) -> None:
        shown = QFontMetrics(self.font()).elidedText(self._full, self._mode, max(10, self.width()))
        if shown != self.text():
            self.setText(shown)


def set_prop(w: QWidget, name: str, value: str) -> None:
    """Поменять свойство для QSS-селектора [name="value"] и перекрасить виджет."""
    if w.property(name) != value:
        w.setProperty(name, value)
        w.style().unpolish(w)
        w.style().polish(w)


class Window(QWidget):
    def __init__(self, path: str, cfg: kit_qt.JsonConfig, manager: kit_qt.ThemeManager):
        super().__init__()
        self.cfg, self.manager = cfg, manager
        self.setWindowTitle("Equestria Unity Log")
        self.resize(620, 380)
        self.tailer = LogTailer(path)
        self.procs = ProcMonitor()
        self.procs_busy = False
        self._proc_t = 0.0
        self._reset_state()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # верх: путь к файлу + кнопки
        top = QHBoxLayout()
        self.path_label = ElideLabel(path, Qt.TextElideMode.ElideLeft)
        self.path_label.setObjectName("path")
        top.addWidget(self.path_label, 1)
        for text, fn in ((tr("ui.file"), self.choose_file), (tr("ui.theme"), self.pick_theme)):
            b = live_i18n.call(QPushButton, text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, f=fn, btn=b: f(btn))
            top.addWidget(b)
        top.addWidget(catalog.selector(self, lambda: self._render(time.monotonic(), False)))
        root.addLayout(top)

        # карточка шейдера
        shader_card = QFrame()
        shader_card.setObjectName("card")
        sv = QVBoxLayout(shader_card)
        sv.setContentsMargins(16, 12, 16, 14)
        sv.setSpacing(6)
        head = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setObjectName("dot")
        self.status = QLabel(tr("status.waiting"))
        self.status.setObjectName("status")
        self.counter = QLabel("")
        self.counter.setObjectName("detail")
        head.addWidget(self.dot)
        head.addWidget(self.status)
        head.addStretch()
        head.addWidget(self.counter)
        sv.addLayout(head)
        self.shader_title = QLabel(tr("shader.heading"))
        self.shader_title.setObjectName("h2")
        sv.addWidget(self.shader_title)
        self.shader_name = ElideLabel("—")
        self.shader_name.setObjectName("shader")
        self.shader_detail = ElideLabel("")
        self.shader_detail.setObjectName("detail")
        self.pass_detail = ElideLabel("")      # последний завершённый проход (ForwardLit, GBuffer…)
        self.pass_detail.setObjectName("detail")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        sv.addWidget(self.shader_name)
        sv.addWidget(self.shader_detail)
        sv.addWidget(self.pass_detail)
        sv.addWidget(self.progress)
        root.addWidget(shader_card)

        # карточка последних строк
        log_card = QFrame()
        log_card.setObjectName("card")
        lv = QVBoxLayout(log_card)
        lv.setContentsMargins(16, 12, 16, 14)
        lv.setSpacing(4)
        title = live_i18n.call(QLabel, tr("log.recent"))
        title.setObjectName("h2")
        lv.addWidget(title)
        self.log_view = LogView(cfg, manager)
        lv.addWidget(self.log_view)
        root.addWidget(log_card, 1)

        # низ: настройки
        bottom = QHBoxLayout()
        self.top_cb = live_i18n.call(QCheckBox, tr("options.on_top"))
        self.top_cb.setChecked(bool(cfg.data.get("always_on_top", False)))
        self.top_cb.toggled.connect(self._on_top_toggled)
        bottom.addStretch()
        bottom.addWidget(self.top_cb)
        root.addLayout(bottom)
        if self.top_cb.isChecked():
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(POLL_MS)
        self.tick()

    # ── состояние ─────────────────────────────────────────────────────────
    def _reset_state(self) -> None:
        self.shader_line = ""
        self.shader_count = 0
        self.shader_time = 0.0
        self.tracker = BuildTracker()        # фаза билда, номер порции шейдеров, «N / M variants»
        self.work_kind = ""        # 'script' или 'build'
        self.work_time = 0.0
        self.error_time = 0.0

    def _on_top_toggled(self, on: bool) -> None:
        self.cfg.data["always_on_top"] = on
        self.cfg.save()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        self.show()   # после смены флага окно надо показать заново

    # ── главный цикл: раз в 250 мс ────────────────────────────────────────
    def tick(self) -> None:
        now = time.monotonic()
        lines = self.tailer.poll()
        if self.tailer.restarted:
            self._reset_state()
            self.log_view.history.clear()
        if now - self._proc_t >= 1.0:          # раз в секунду: работают ли компиляторы Unity
            self._proc_t = now
            self.procs_busy = self.procs.poll(now)
        for line in lines:
            kind = classify(line)
            self.tracker.feed(line, kind, now)
            if kind == "shader":
                self.shader_line, self.shader_time = line, now
                self.shader_count += 1
            elif kind == "progress":
                self.shader_time = now
            elif kind in ("script", "build"):
                self.work_kind, self.work_time = kind, now
            lvl = level(line)
            if lvl == "error":
                self.error_time = now
            self.log_view.history.append((line, kind, lvl))
        self._render(now, bool(lines) or self.tailer.restarted)

    def _render(self, now: float, changed: bool) -> None:
        bt = self.tracker
        shader_busy = bt.shaders_busy(now, self.procs_busy)
        work_busy = self.work_kind and now - self.work_time < WORK_ACTIVE_S
        if shader_busy:
            state, text = "busy", tr("status.shader_batch", bt.batches)
        elif self.procs_busy:
            state, text = "busy", tr("status.compilers")
        elif work_busy:
            state = "busy"
            text = tr("status.scripts") if self.work_kind == "script" else tr("status.build")
        elif bt.phase == "done":
            m, sec = divmod(bt.duration_s, 60)
            state, text = "idle", tr("status.done", bt.result) + (tr("status.duration", m, sec) if bt.duration_s else "")
        elif bt.phase == "failed":
            state, text = "error", tr("status.failed", bt.result)
        elif now - self.error_time < ERROR_SHOW_S:
            state, text = "error", tr("status.error")
        else:
            state, text = "idle", tr("status.idle")
        set_prop(self.dot, "state", state)
        if self.status.text() != text:
            self.status.setText(text)

        # карточка шейдера
        if self.shader_line:
            name, detail, prog = parse_shader(self.shader_line)
            self.shader_name.set_full(name or detail)
            self.shader_detail.set_full(detail if name else "")
            prog = prog or bt.variants
        else:
            self.shader_name.set_full("—")
            self.shader_detail.set_full(tr("shader.empty"))
            prog = bt.variants
        if prog and shader_busy:
            est = bt.estimate(now)            # Unity пишет прогресс раз в ~70 с — оцениваем, где он сейчас
            shown = est[0] if est and est[0] > prog[0] else prog[0]
            self.progress.setRange(0, prog[1])
            self.progress.setValue(min(shown, prog[1]))
            self.progress.setVisible(True)
            text = tr("shader.variants", prog[0], prog[1], prog[0] * 100 // prog[1])
            if est and est[0] > prog[0]:
                text += tr("shader.estimate", est[0], est[1])
            self.shader_detail.set_full(text)
        else:
            self.progress.setVisible(False)
        if bt.last_pass and bt.phase == "shaders":
            name, stage, api, secs, n = bt.last_pass
            ptxt = tr("shader.last_pass", name, stage, api, n, int(secs))
            if bt.last_done_shader:
                ptxt += tr("shader.finished", bt.last_done_shader)
            self.pass_detail.set_full(ptxt)
        else:
            self.pass_detail.set_full("")
        set_prop(self.shader_name, "stale", "false" if shader_busy else "true")
        if shader_busy and bt.variants:    # Unity пишет общий счётчик порции, а не текущий шейдер
            title = tr("shader.batch_heading")
        elif shader_busy:
            title = tr("shader.current")
        else:
            title = tr("shader.last")
        if self.shader_title.text() != title:
            self.shader_title.setText(title)
        if bt.phase == "shaders":
            counter = tr("shader.batch_count", bt.batches, bt.batch_shaders)
        else:
            counter = tr("shader.total", self.shader_count) if self.shader_count else ""
        if self.counter.text() != counter:
            self.counter.setText(counter)

        if changed:
            self.log_view.refresh()

    # ── кнопки ────────────────────────────────────────────────────────────
    def choose_file(self, _btn=None) -> None:
        path = ask_log_file(self, self.cfg)
        if path:
            self.tailer = LogTailer(path)
            self._reset_state()
            self.path_label.set_full(path)
            self.log_view.history.clear()
            self.log_view.refresh()
            self.tick()

    def pick_theme(self, btn: QPushButton) -> None:
        kit_qt.theme_menu(self, btn, self.manager.name, self.manager.apply)


def ask_log_file(parent, cfg: kit_qt.JsonConfig) -> str:
    """Окно «выберите лог». Открывается там, где вы были в прошлый раз."""
    last = Path(str(cfg.data.get("last_path", "")))
    start = last.parent if last.parent.is_dir() else Path.home() / ".config" / "unity3d"
    if not start.is_dir():
        start = Path.home()
    path, _ = QFileDialog.getOpenFileName(
        parent, tr("dialog.title"), str(start),
        tr("dialog.filter"))
    if path:
        cfg.data["last_path"] = path
        cfg.save()
    return path


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Unity Log")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().with_name(f"{APP_ID}.svg"))))
    catalog.set_language(catalog.lang, persist=False)
    cfg = kit_qt.JsonConfig(APP_ID, {"hide_shader_lines": True, "always_on_top": False})
    manager = kit_qt.ThemeManager(app, QSS)

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    path = args[0] if args and Path(args[0]).is_file() else ask_log_file(None, cfg)
    if not path:
        return 0   # нажали «Отмена» — выходим
    win = Window(path, cfg, manager)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
