"""
Self-contained sections of the Swap Manager window.

Each panel builds its own widgets and talks to the window through two
callables: t(key) for translations and run_backend(args) for root actions.
The window calls load(state) after every refresh and retranslate() on a
language change.
"""
import os
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QSpinBox, QComboBox, QFrame,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

from equestria_kit import qt as kit_qt

import health
from memory_config import KNOBS, CONFIG_FILES

# Same fix as in swap_app.py: style the popup directly so the global
# "QWidget { background: transparent }" doesn't make it see-through.
COMBO_VIEW_QSS = ("background-color: @base@; color: @text@; "
                  "selection-background-color: @surface0@; selection-color: @text@; "
                  "border: 1px solid @surface1@;")


def _label(text="", name="SectionLabel", wrap=False):
    lbl = QLabel(text)
    lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def _button(text, name, slot):
    btn = QPushButton(text)
    btn.setObjectName(name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(slot)
    return btn


class Panel(QWidget):
    def __init__(self, t, run_backend):
        super().__init__()
        self.t = t
        self.run_backend = run_backend
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(10)

    def load(self, state):
        pass

    def retranslate(self):
        pass

    def interactive_widgets(self) -> tuple:
        return ()


# ── System check ──────────────────────────────────────────────────────────────

class HealthPanel(Panel):
    """Problems found by health.run_checks, each with its own Fix button."""

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self._issues = []
        self._buttons = []
        self.title = _label()
        self.layout_.addWidget(self.title)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        self.layout_.addLayout(self.rows)
        self.fix_all_btn = _button("", "RelocateBtn",
                                   lambda: self.run_backend(health.combined_fix(self._issues)))
        self.layout_.addWidget(self.fix_all_btn)
        self.retranslate()

    def load(self, state):
        self._issues = health.run_checks(state)
        self._rebuild()

    def retranslate(self):
        self.title.setText(self.t("health_section"))
        self.fix_all_btn.setText(self.t("health_fix_all"))
        self._rebuild()

    def interactive_widgets(self) -> tuple:
        return (*self._buttons, self.fix_all_btn)

    @classmethod
    def _clear(cls, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            child, widget = item.layout(), item.widget()
            if child is not None:
                cls._clear(child)
            elif widget is not None:
                widget.deleteLater()

    def _rebuild(self):
        self._clear(self.rows)
        self._buttons = []

        if not self._issues:
            self.rows.addWidget(_label(self.t("health_ok"), "ZramStatusLabel", wrap=True))
        for issue in self._issues:
            row = QHBoxLayout()
            name = "HealthWarn" if issue.severity == "warn" else "HealthInfo"
            row.addWidget(_label(self.t(issue.key).format(*issue.args), name, wrap=True), 1)
            btn = _button(self.t("health_fix"), "BrowseBtn",
                          lambda _=False, fix=issue.fix: self.run_backend(fix))
            self._buttons.append(btn)
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            self.rows.addLayout(row)
        self.fix_all_btn.setVisible(len(self._issues) > 1)


# ── Fine memory tuning ────────────────────────────────────────────────────────

class TuningPanel(Panel):
    """Extra kernel memory settings from memory_config.KNOBS.
    Only values the user actually changed are sent to the backend."""

    SPINS = (
        # knob name, suffix
        ("vfs_cache_pressure", ""),
        ("watermark_boost_factor", ""),
        ("watermark_scale_factor", ""),
        ("dirty_background_mb", " MiB"),
        ("dirty_mb", " MiB"),
    )
    COMBOS = ("thp", "thp_defrag")

    # What the Windows-like preset / zram guides recommend.
    RECOMMENDED = {
        "vfs_cache_pressure": 100, "watermark_boost_factor": 0,
        "watermark_scale_factor": 125, "dirty_background_mb": 256,
        "dirty_mb": 1024, "thp": "madvise", "thp_defrag": "madvise",
    }

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self._loaded = {}
        self._labels = {}
        self._hints = {}
        self.controls = {}

        self.title = _label()
        self.hint = _label(name="HintLabel", wrap=True)
        self.layout_.addWidget(self.title)
        self.layout_.addWidget(self.hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        row = 0
        for name, suffix in self.SPINS:
            knob = KNOBS[name]
            spin = QSpinBox()
            spin.setObjectName("SourceEdit")
            spin.setRange(knob.minimum, knob.maximum)
            spin.setSuffix(suffix)
            spin.setFixedHeight(34)
            spin.setMinimumWidth(150)
            self.controls[name] = spin
            row = self._add_row(grid, row, name, spin)
        for name in self.COMBOS:
            combo = QComboBox()
            combo.setCursor(Qt.CursorShape.PointingHandCursor)
            combo.setMinimumWidth(150)
            for choice in KNOBS[name].choices:
                combo.addItem(choice, choice)
            view = combo.view()
            if view is not None:
                kit_qt.style(view, COMBO_VIEW_QSS)
            self.controls[name] = combo
            row = self._add_row(grid, row, name, combo)
        grid.setColumnStretch(2, 1)
        self.layout_.addLayout(grid)

        buttons = QHBoxLayout()
        self.recommended_btn = _button("", "BrowseBtn", lambda: self._fill(self.RECOMMENDED))
        self.defaults_btn = _button("", "BrowseBtn", lambda: self._fill(
            {name: KNOBS[name].default for name in self.controls}))
        self.apply_btn = _button("", "RelocateBtn", self._apply)
        buttons.addWidget(self.recommended_btn)
        buttons.addWidget(self.defaults_btn)
        buttons.addStretch()
        self.layout_.addLayout(buttons)
        self.layout_.addWidget(self.apply_btn)
        self.retranslate()

    def _add_row(self, grid, row, name, control):
        label = _label()
        hint = _label(name="HintLabel", wrap=True)
        self._labels[name] = label
        self._hints[name] = hint
        grid.addWidget(label, row, 0)
        grid.addWidget(control, row, 1)
        grid.addWidget(hint, row + 1, 0, 1, 3)
        return row + 2

    def load(self, state):
        self._loaded = {}
        for name, control in self.controls.items():
            value = state.values.get(name)
            available = value is not None
            control.setEnabled(available)
            if not available:
                continue
            self._loaded[name] = value
            self._set(control, value)

    def retranslate(self):
        self.title.setText(self.t("tune_section"))
        self.hint.setText(self.t("tune_hint"))
        for name, label in self._labels.items():
            label.setText(self.t(f"tune_{name}"))
            self._hints[name].setText(self.t(f"tune_{name}_hint"))
        for name in ("dirty_background_mb", "dirty_mb"):
            self.controls[name].setSpecialValueText(self.t("tune_auto"))
        self.recommended_btn.setText(self.t("tune_recommended"))
        self.defaults_btn.setText(self.t("tune_defaults"))
        self.apply_btn.setText(self.t("tune_apply"))

    def interactive_widgets(self) -> tuple:
        return (*self.controls.values(), self.recommended_btn, self.defaults_btn, self.apply_btn)

    @staticmethod
    def _set(control, value):
        if isinstance(control, QSpinBox):
            control.setValue(int(value))
        else:
            idx = control.findData(value)
            if idx != -1:
                control.setCurrentIndex(idx)

    @staticmethod
    def _get(control):
        return control.value() if isinstance(control, QSpinBox) else control.currentData()

    def _fill(self, values):
        for name, value in values.items():
            control = self.controls[name]
            if control.isEnabled():
                self._set(control, value)

    def _apply(self):
        args = []
        for name, control in self.controls.items():
            if name in self._loaded and self._get(control) != self._loaded[name]:
                args += ["--set", name, str(self._get(control))]
        if args:
            self.run_backend(args)


# ── Configuration files ───────────────────────────────────────────────────────

class ConfigFilesPanel(Panel):
    """Every file the app writes (plus the ones it reads), with its path and
    buttons to open it or show it in the file manager — to read the settings
    outside the GUI."""

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self.title = _label()
        self.hint = _label(name="HintLabel", wrap=True)
        self.layout_.addWidget(self.title)
        self.layout_.addWidget(self.hint)
        self._rows = []
        for key, path in CONFIG_FILES:
            box = QFrame()
            box.setObjectName("FileRow")
            lay = QVBoxLayout(box)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.setSpacing(4)
            desc = _label()
            path_lbl = _label(path, "FilePath", wrap=True)
            path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            buttons = QHBoxLayout()
            open_btn = _button("", "BrowseBtn", lambda _=False, p=path: self._open(p))
            show_btn = _button("", "BrowseBtn", lambda _=False, p=path: self._show(p))
            buttons.addWidget(open_btn)
            buttons.addWidget(show_btn)
            buttons.addStretch()
            lay.addWidget(desc)
            lay.addWidget(path_lbl)
            lay.addLayout(buttons)
            self.layout_.addWidget(box)
            self._rows.append((key, path, desc, path_lbl, open_btn, show_btn))
        self.retranslate()

    def load(self, state):
        self.retranslate()

    def retranslate(self):
        self.title.setText(self.t("files_section"))
        self.hint.setText(self.t("files_hint"))
        for key, path, desc, path_lbl, open_btn, show_btn in self._rows:
            exists = os.path.exists(path)
            desc.setText(self.t(key))
            path_lbl.setText(path if exists else f"{path}  —  {self.t('files_missing')}")
            open_btn.setText(self.t("files_open"))
            show_btn.setText(self.t("files_show"))
            open_btn.setEnabled(exists)
            # the folder may exist even when the file doesn't yet
            show_btn.setEnabled(os.path.isdir(os.path.dirname(path)))

    @staticmethod
    def _open(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @staticmethod
    def _show(path):
        """Open the folder with the file selected (Dolphin and other
        FileManager1 implementations); plain folder as a fallback."""
        target = path if os.path.exists(path) else os.path.dirname(path)
        uri = QUrl.fromLocalFile(target).toString(QUrl.ComponentFormattingOption.FullyEncoded)
        try:
            r = subprocess.run(
                ["dbus-send", "--session", "--print-reply",
                 "--dest=org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                 "org.freedesktop.FileManager1.ShowItems", f"array:string:{uri}", "string:"],
                capture_output=True, timeout=5)
            if r.returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
