"""
Cards of the Swap Manager window, in the look of Equestria OS Settings pages
(#InlineCard frames, compact rows, buttons sized to their text).

Each card builds its own widgets and talks to the window through two
callables: t(key) for translations and run_backend(args) for root actions.
The window calls load(state) after every refresh, retranslate() on a
language change and set_pro(bool) when the Simple/Professional mode changes.
"""
import os
import subprocess

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QSpinBox, QComboBox, QLineEdit, QCheckBox, QSlider, QMessageBox,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

from equestria_kit import qt as kit_qt

import health
from memory_config import KNOBS, CONFIG_FILES, ZRAM_ALGORITHMS

# Style the popup directly so the global "QWidget { background: transparent }"
# doesn't make it see-through.
COMBO_VIEW_QSS = ("background-color: @surface0@; color: @text@; "
                  "selection-background-color: @accent%55@; selection-color: @text@; "
                  "border: 1px solid @accent%75@;")


def label(text="", name="FieldLabel", wrap=False):
    lbl = QLabel(text)
    lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def button(text, slot, name="ActionBtn"):
    btn = QPushButton(text)
    btn.setObjectName(name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(slot)
    return btn


def combo():
    box = QComboBox()
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    view = box.view()
    if view is not None:
        kit_qt.style(view, COMBO_VIEW_QSS)
    return box


def row(*items, stretch=True):
    """Widgets side by side, left-aligned (buttons keep their natural width)."""
    lay = QHBoxLayout()
    lay.setSpacing(8)
    for item in items:
        lay.addWidget(item)
    if stretch:
        lay.addStretch()
    return lay


class Card(QFrame):
    """One #InlineCard section. Subclasses fill self.body."""

    title_key = ""

    def __init__(self, t, run_backend):
        super().__init__()
        self.setObjectName("InlineCard")
        self.t = t
        self.run_backend = run_backend
        self.pro = False
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 14, 18, 14)
        self.body.setSpacing(8)
        self.header = QHBoxLayout()
        self.title = label(name="CardTitle")
        self.header.addWidget(self.title)
        self.header.addStretch()
        self.body.addLayout(self.header)

    def load(self, state):
        pass

    def retranslate(self):
        self.title.setText(self.t(self.title_key))

    def set_pro(self, pro):
        self.pro = pro

    def interactive_widgets(self) -> tuple:
        return ()


# ── Overview ──────────────────────────────────────────────────────────────────

class StatusCard(Card):
    """Memory use and every active swap area at a glance."""

    title_key = "status_title"

    def __init__(self, t, run_backend, refresh):
        super().__init__(t, run_backend)
        self.refresh_btn = button("⟳", refresh, "OpenAppBtn")
        self.header.addWidget(self.refresh_btn)
        self.memory = label()
        self.swaps = label(name="FieldHint", wrap=True)
        self.body.addWidget(self.memory)
        self.body.addWidget(self.swaps)
        self._state = None

    def load(self, state):
        self._state = state
        self.retranslate()

    def retranslate(self):
        super().retranslate()
        state = self._state
        if state is None:
            return
        self.memory.setText(self.t("status_memory").format(
            f"{state.mem_used_gib:.1f}", f"{state.mem_total_gib:.1f}"))
        if not state.swaps:
            self.swaps.setText(self.t("no_swap"))
            return
        zram = {d.path: d for d in state.zram}
        lines = []
        for area in state.swaps:
            info = [area.size, self.t("status_used").format(area.used)]
            dev = zram.get(area.name)
            if dev is not None:
                if dev.algorithm:
                    info.append(dev.algorithm)
                if dev.ratio:
                    info.append(self.t("zram_ratio").format(f"{dev.ratio:.1f}"))
            lines.append(f"{area.name}  ·  " + "  ·  ".join(info))
        self.swaps.setText("\n".join(lines))

    def interactive_widgets(self):
        return (self.refresh_btn,)


class HealthCard(Card):
    """Problems found by health.run_checks, each with its own Fix button."""

    title_key = "health_section"

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self._issues = []
        self._buttons = []
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        self.body.addLayout(self.rows)
        self.fix_all_btn = button("", lambda: self.run_backend(health.combined_fix(self._issues)),
                                  "PrimaryBtn")
        self.header.addWidget(self.fix_all_btn)

    def load(self, state):
        self._issues = health.run_checks(state)
        self._rebuild()

    def retranslate(self):
        super().retranslate()
        self.fix_all_btn.setText(self.t("health_fix_all"))
        self._rebuild()

    def interactive_widgets(self):
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
                # hide right away: until deleteLater runs, an unlinked widget
                # would be drawn at the card's top-left corner
                widget.hide()
                widget.deleteLater()

    def _rebuild(self):
        self._clear(self.rows)
        self._buttons = []
        if not self._issues:
            self.rows.addWidget(label(self.t("health_ok"), "HealthOk", wrap=True))
        for issue in self._issues:
            line = QHBoxLayout()
            name = "HealthWarn" if issue.severity == "warn" else "HealthInfo"
            line.addWidget(label(self.t(issue.key).format(*issue.args), name, wrap=True), 1)
            btn = button(self.t("health_fix"), lambda _=False, fix=issue.fix: self.run_backend(fix))
            self._buttons.append(btn)
            line.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            self.rows.addLayout(line)
        self.fix_all_btn.setVisible(len(self._issues) > 1)


class PresetCard(Card):
    """One button that sets everything up; the full list only in Professional mode."""

    title_key = "win_section"

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self.hint = label(name="FieldHint", wrap=True)
        self.apply_btn = button("", self._apply, "PrimaryBtn")
        self.body.addWidget(self.hint)
        self.body.addLayout(row(self.apply_btn))

    def retranslate(self):
        super().retranslate()
        self.hint.setText(self.t("win_hint" if self.pro else "win_short"))
        self.apply_btn.setText(self.t("win_btn"))

    def set_pro(self, pro):
        super().set_pro(pro)
        self.retranslate()

    def interactive_widgets(self):
        return (self.apply_btn,)

    def _apply(self):
        zram_gb = health.recommended_zram_gb(health.read_ram_gb())
        self.run_backend([
            "--zram-enable", str(zram_gb), health.RECOMMENDED_ALGORITHM,
            "--overcommit",    "1",
            "--oomd",          "disable",
            "--swappiness",    str(health.RECOMMENDED_SWAPPINESS),
            "--panic-on-oom",  "0",
            # recommended for zram: no reclaim bursts, earlier background reclaim,
            # no compaction stalls on every allocation
            "--set", "watermark_boost_factor", "0",
            "--set", "watermark_scale_factor", "125",
            "--set", "thp", "madvise",
        ])


# ── Swap ──────────────────────────────────────────────────────────────────────

class SwapFileCard(Card):
    title_key = "swapfile_section"

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self.path_lbl = label()
        self.path_input = QLineEdit("/swapfile")
        self.path_input.setObjectName("PathEdit")
        self.size_lbl = label()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 256)
        self.size_spin.setValue(32)
        self.size_spin.setSuffix(" GB")
        self.fstab_cb = QCheckBox()
        self.fstab_cb.setObjectName("SwapCheckBox")
        self.fstab_cb.setChecked(True)
        self.fstab_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn = button("", self._apply, "PrimaryBtn")
        self.disable_btn = button("", self._disable)
        self.delete_btn = button("", self._delete, "DeleteBtn")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(self.path_lbl, 0, 0)
        grid.addWidget(self.path_input, 0, 1)
        grid.addWidget(self.size_lbl, 1, 0)
        grid.addLayout(row(self.size_spin, self.fstab_cb), 1, 1)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)
        self.body.addLayout(row(self.apply_btn, self.disable_btn, self.delete_btn))

    def retranslate(self):
        super().retranslate()
        self.path_lbl.setText(self.t("path"))
        self.size_lbl.setText(self.t("size"))
        self.fstab_cb.setText(self.t("fstab_chk"))
        self.apply_btn.setText(self.t("btn_apply"))
        self.disable_btn.setText(self.t("btn_disable"))
        self.delete_btn.setText(self.t("btn_delete"))

    def interactive_widgets(self):
        return (self.path_input, self.size_spin, self.fstab_cb,
                self.apply_btn, self.disable_btn, self.delete_btn)

    def _path(self):
        return self.path_input.text().strip()

    def _apply(self):
        if self._path():
            self.run_backend(["--create", self._path(), str(self.size_spin.value()),
                              "yes" if self.fstab_cb.isChecked() else "no"])

    def _disable(self):
        if self._path():
            self.run_backend(["--disable", self._path()])

    def _delete(self):
        path = self._path()
        if not path:
            return
        answer = QMessageBox.question(
            self, self.t("btn_delete"), self.t("confirm_delete").format(path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.run_backend(["--delete", path])


class SwappinessCard(Card):
    title_key = "swappiness"

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self.hint = label(name="FieldHint", wrap=True)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        # Kernel accepts 0–200 since 5.8; >100 favours swap over dropping
        # file cache, which is what zram wants.
        self.slider.setRange(0, 200)
        self.value = label("60")
        self.value.setMinimumWidth(32)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider.valueChanged.connect(lambda v: self.value.setText(str(v)))
        self.apply_btn = button("", lambda: self.run_backend(
            ["--swappiness", str(self.slider.value())]))
        line = QHBoxLayout()
        line.setSpacing(12)
        line.addWidget(self.slider, 1)
        line.addWidget(self.value)
        line.addWidget(self.apply_btn)
        self.body.addWidget(self.hint)
        self.body.addLayout(line)

    def load(self, state):
        value = state.values.get("swappiness")
        if value is not None:
            self.slider.setValue(value)

    def retranslate(self):
        super().retranslate()
        self.hint.setText(self.t("swappiness_hint"))
        self.apply_btn.setText(self.t("btn_swapp"))

    def interactive_widgets(self):
        return (self.slider, self.apply_btn)


class ZramCard(Card):
    title_key = "zram_section"

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self.status = label(name="ZramStatusLabel")
        self.header.insertWidget(1, self.status)
        self.hint = label(name="FieldHint", wrap=True)
        self.size_lbl = label()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 128)
        self.size_spin.setSuffix(" GB")
        self.algo_lbl = label()
        self.algo_combo = combo()
        self.algo_combo.setMinimumWidth(120)
        for algo in ZRAM_ALGORITHMS:
            self.algo_combo.addItem(algo)
        # Always available: applies a new size/algorithm to a running zram too
        self.apply_btn = button("", lambda: self.run_backend(
            ["--zram-enable", str(self.size_spin.value()), self.algo_combo.currentText()]),
            "PrimaryBtn")
        self.disable_btn = button("", lambda: self.run_backend(["--zram-disable"]), "DeleteBtn")
        self._can_disable = False
        self._state = None
        self.body.addWidget(self.hint)
        self.body.addLayout(row(self.size_lbl, self.size_spin, self.algo_lbl, self.algo_combo))
        self.body.addLayout(row(self.apply_btn, self.disable_btn))

    def load(self, state):
        self._state = state
        size_gb, algo = state.zram_target()
        self.size_spin.setValue(size_gb)
        idx = self.algo_combo.findText(algo)
        if idx != -1:
            self.algo_combo.setCurrentIndex(idx)
        self._can_disable = state.zram_active or bool(state.dropin and state.dropin[0] > 0)
        self.disable_btn.setEnabled(self._can_disable)
        self._show_status()

    def _show_status(self):
        state = self._state
        if state is None or not state.zram:
            self.status.setText(self.t("zram_inactive"))
            return
        dev = state.zram[0]
        info = [dev.size] + ([dev.algorithm] if dev.algorithm else [])
        self.status.setText(self.t("zram_active").format(" · ".join(info)))

    def retranslate(self):
        super().retranslate()
        self.hint.setText(self.t("zram_hint"))
        self.size_lbl.setText(self.t("zram_size_lbl"))
        self.algo_lbl.setText(self.t("zram_algo_lbl"))
        self.apply_btn.setText(self.t("zram_apply"))
        self.disable_btn.setText(self.t("zram_disable"))
        self._show_status()

    def interactive_widgets(self):
        return (self.size_spin, self.algo_combo, self.apply_btn, self.disable_btn)


# ── Memory ────────────────────────────────────────────────────────────────────

class OomCard(Card):
    title_key = "oom_section"

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self.hint = label(name="FieldHint", wrap=True)
        self.overcommit_lbl = label()
        self.overcommit = combo()
        self.overcommit.setMinimumWidth(280)
        for _ in range(3):
            self.overcommit.addItem("")
        self.oomd_cb = QCheckBox()
        self.oomd_cb.setObjectName("SwapCheckBox")
        self.panic_cb = QCheckBox()
        self.panic_cb.setObjectName("SwapCheckBox")
        for cb in (self.oomd_cb, self.panic_cb):
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn = button("", self._apply)
        self._panic_available = True
        self.body.addWidget(self.hint)
        self.body.addLayout(row(self.overcommit_lbl, self.overcommit))
        self.body.addWidget(self.oomd_cb)
        self.body.addWidget(self.panic_cb)
        self.body.addLayout(row(self.apply_btn))

    def load(self, state):
        overcommit = state.values.get("overcommit")
        if overcommit is not None:
            self.overcommit.setCurrentIndex(max(0, min(2, overcommit)))
        # checked = systemd-oomd is off
        self.oomd_cb.setChecked(not state.oomd_enabled)
        # checked = prevent panic = value is 0; the parameter may be missing
        panic = state.values.get("panic_on_oom")
        self._panic_available = panic is not None
        self.panic_cb.setChecked(panic == 0)
        self.panic_cb.setEnabled(self._panic_available)
        self._panic_text()

    def _panic_text(self):
        text = self.t("oom_panic_cb")
        self.panic_cb.setText(text if self._panic_available else f"{text} (n/a)")

    def retranslate(self):
        super().retranslate()
        self.hint.setText(self.t("oom_hint"))
        self.overcommit_lbl.setText(self.t("oom_overcommit"))
        for i in range(3):
            self.overcommit.setItemText(i, self.t(f"oom_mode_{i}"))
        self.oomd_cb.setText(self.t("oom_oomd_cb"))
        self._panic_text()
        self.apply_btn.setText(self.t("oom_apply"))

    def interactive_widgets(self):
        return (self.overcommit, self.oomd_cb, self.panic_cb, self.apply_btn)

    def _apply(self):
        self.run_backend([
            "--overcommit", str(self.overcommit.currentIndex()),
            "--oomd", "disable" if self.oomd_cb.isChecked() else "enable",
            "--panic-on-oom", "0" if self.panic_cb.isChecked() else "1",
        ])


class TuningCard(Card):
    """Extra kernel memory settings from memory_config.KNOBS.
    Only values the user actually changed are sent to the backend."""

    title_key = "tune_section"

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
        self.hint = label(name="FieldHint", wrap=True)
        self.body.addWidget(self.hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        line = 0
        for name, suffix in self.SPINS:
            knob = KNOBS[name]
            spin = QSpinBox()
            spin.setRange(knob.minimum, knob.maximum)
            spin.setSuffix(suffix)
            spin.setMinimumWidth(140)
            self.controls[name] = spin
            line = self._add_line(grid, line, name, spin)
        for name in self.COMBOS:
            box = combo()
            box.setMinimumWidth(140)
            for choice in KNOBS[name].choices:
                box.addItem(choice, choice)
            self.controls[name] = box
            line = self._add_line(grid, line, name, box)
        grid.setColumnStretch(2, 1)
        self.body.addLayout(grid)

        self.recommended_btn = button("", lambda: self._fill(self.RECOMMENDED))
        self.defaults_btn = button("", lambda: self._fill(
            {name: KNOBS[name].default for name in self.controls}))
        self.apply_btn = button("", self._apply, "PrimaryBtn")
        self.body.addLayout(row(self.apply_btn, self.recommended_btn, self.defaults_btn))

    def _add_line(self, grid, line, name, control):
        name_lbl = label()
        hint = label(name="FieldHint", wrap=True)
        self._labels[name] = name_lbl
        self._hints[name] = hint
        grid.addWidget(name_lbl, line, 0)
        grid.addWidget(control, line, 1)
        grid.addWidget(hint, line + 1, 0, 1, 3)
        grid.setRowMinimumHeight(line + 2, 6)
        return line + 3

    def load(self, state):
        self._loaded = {}
        for name, control in self.controls.items():
            value = state.values.get(name)
            control.setEnabled(value is not None)
            if value is None:
                continue
            self._loaded[name] = value
            self._set(control, value)

    def retranslate(self):
        super().retranslate()
        self.hint.setText(self.t("tune_hint"))
        for name, name_lbl in self._labels.items():
            name_lbl.setText(self.t(f"tune_{name}"))
            self._hints[name].setText(self.t(f"tune_{name}_hint"))
        for name in ("dirty_background_mb", "dirty_mb"):
            self.controls[name].setSpecialValueText(self.t("tune_auto"))
        self.recommended_btn.setText(self.t("tune_recommended"))
        self.defaults_btn.setText(self.t("tune_defaults"))
        self.apply_btn.setText(self.t("tune_apply"))

    def interactive_widgets(self):
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

class ConfigFilesCard(Card):
    """Every file the app writes (plus the ones it reads), with its path and
    buttons to open it or show it in the file manager — to read the settings
    outside the GUI."""

    title_key = "files_section"

    def __init__(self, t, run_backend):
        super().__init__(t, run_backend)
        self.hint = label(name="FieldHint", wrap=True)
        self.body.addWidget(self.hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        self._rows = []
        for i, (key, path) in enumerate(CONFIG_FILES):
            text = QVBoxLayout()
            text.setSpacing(0)
            desc = label()
            path_lbl = label(path, "FilePath", wrap=True)
            path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.addWidget(desc)
            text.addWidget(path_lbl)
            open_btn = button("", lambda _=False, p=path: self._open(p), "OpenAppBtn")
            show_btn = button("", lambda _=False, p=path: self._show(p), "OpenAppBtn")
            grid.addLayout(text, i, 0)
            grid.addWidget(open_btn, i, 1, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(show_btn, i, 2, Qt.AlignmentFlag.AlignVCenter)
            self._rows.append((key, path, desc, path_lbl, open_btn, show_btn))
        grid.setColumnStretch(0, 1)
        self.body.addLayout(grid)

    def load(self, state):
        self.retranslate()

    def retranslate(self):
        super().retranslate()
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
