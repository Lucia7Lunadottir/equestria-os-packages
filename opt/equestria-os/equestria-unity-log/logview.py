"""Live filters for the bounded, unfiltered Unity log history."""
from collections import deque
from itertools import islice

from PyQt6.QtGui import QColor, QBrush, QFontDatabase
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout, QWidget)

from localization import live_i18n, tr

HISTORY_SIZE = 2000
MAX_ROWS = 200
MODES = ("all", "no_shaders", "error", "warning", "shader", "script", "build")


def matches(mode, kind, severity):
    if mode in ("error", "warning"):
        return mode == severity
    if mode == "no_shaders":
        return kind not in ("shader", "progress")
    if mode == "shader":
        return kind in ("shader", "progress")
    return mode == "all" or mode == kind


class LogView(QWidget):
    def __init__(self, cfg, manager):
        super().__init__()
        self.cfg = cfg
        self.manager = manager
        self.history = deque(maxlen=HISTORY_SIZE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        layout.addLayout(bar)
        self.enabled = live_i18n.call(QCheckBox, tr("filter.enabled"))
        self.enabled.setChecked(bool(cfg.data.get("filter_enabled", cfg.data.get("hide_shader_lines", True))))
        bar.addWidget(self.enabled)
        self.mode = QComboBox()
        for mode in MODES:
            live_i18n.call(self.mode.addItem, tr("filter." + mode), mode)
        saved = cfg.data.get("filter_mode", "no_shaders")
        self.mode.setCurrentIndex(MODES.index(saved) if saved in MODES else MODES.index("no_shaders"))
        bar.addWidget(self.mode)
        self.query = QLineEdit()
        self.query.setClearButtonEnabled(True)
        live_i18n.call(self.query.setPlaceholderText, tr("filter.search"))
        bar.addWidget(self.query, 1)
        self.count = QSpinBox()
        self.count.setRange(1, MAX_ROWS)
        saved_count = cfg.data.get("line_count", 5)
        self.count.setValue(saved_count if type(saved_count) is int and 1 <= saved_count <= MAX_ROWS else 5)
        label = live_i18n.call(QLabel, tr("filter.rows"))
        label.setBuddy(self.count)
        bar.addWidget(label)
        bar.addWidget(self.count)
        self.lines = QListWidget()
        self.lines.setUniformItemSizes(True)
        self.lines.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.lines)
        self.empty = live_i18n.call(QLabel, tr("filter.empty"))
        layout.addWidget(self.empty)
        self.enabled.toggled.connect(self.options_changed)
        self.mode.currentIndexChanged.connect(self.options_changed)
        self.count.valueChanged.connect(self.options_changed)
        self.query.textChanged.connect(self.refresh)
        manager.on_change(lambda _: self.refresh())
        self.refresh()

    def options_changed(self):
        self.cfg.data.update(filter_enabled=self.enabled.isChecked(), filter_mode=self.mode.currentData(),
                             line_count=self.count.value())
        self.cfg.save()
        self.refresh()

    def refresh(self):
        enabled = self.enabled.isChecked()
        self.query.setEnabled(enabled)
        self.mode.setEnabled(enabled)
        mode = self.mode.currentData() if enabled else "all"
        query = self.query.text().casefold() if enabled else ""
        found = ((text, severity) for text, kind, severity in reversed(self.history)
                 if matches(mode, kind, severity) and (not query or query in text.casefold()))
        rows = list(islice(found, self.count.value()))
        self.empty.setVisible(not rows)
        scroll = self.lines.verticalScrollBar()
        follow = scroll.value() == scroll.maximum()
        while self.lines.count() > len(rows):
            self.lines.takeItem(self.lines.count() - 1)
        for index, (text, severity) in enumerate(reversed(rows)):
            item = self.lines.item(index)
            if item is None:
                item = QListWidgetItem(self.lines)
            if item.text() != text:
                item.setText(text)
                item.setToolTip(text)
            role = {"error": "red", "warning": "yellow"}.get(severity, "text")
            item.setForeground(QBrush(QColor(self.manager.theme[role])))
        if follow:
            self.lines.scrollToBottom()
