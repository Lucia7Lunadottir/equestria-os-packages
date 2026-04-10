#!/usr/bin/env python3
"""
Equestria OS App Builder — GUI frontend for PyInstaller.
Builds any Python project into a standalone executable.
"""

import json
import os
import shutil
import subprocess
import sys

from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtGui import QColor, QFont, QIcon, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox,
    QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QSplitter, QStatusBar, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
STYLE = """
QWidget {
    background-color: rgb(18, 18, 28);
    color: rgb(220, 200, 255);
    font-size: 13px;
}
QGroupBox {
    border: 1px solid rgb(69, 71, 90);
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 22px;
    font-weight: bold;
    color: rgb(180, 170, 210);
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
}
QPushButton {
    background-color: rgb(40, 35, 60);
    color: rgb(220, 200, 255);
    border: 1px solid rgb(69, 71, 90);
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover  { background-color: rgb(60, 50, 90); }
QPushButton:disabled { color: rgb(90, 80, 110); border-color: rgb(40, 38, 58); }
QPushButton#btnBuild {
    background-color: rgb(46, 139, 87);
    border: 1px solid rgb(60, 170, 100);
    font-weight: bold;
    padding: 8px 28px;
}
QPushButton#btnBuild:hover    { background-color: rgb(60, 170, 100); }
QPushButton#btnBuild:disabled { background-color: rgb(28, 75, 50); border-color: rgb(40, 90, 60); }
QPushButton#btnDanger {
    background-color: rgb(140, 40, 40);
    border: 1px solid rgb(180, 50, 50);
}
QPushButton#btnDanger:hover { background-color: rgb(180, 50, 50); }
QPushButton#btnSave {
    background-color: rgb(46, 139, 87);
    border: 1px solid rgb(60, 170, 100);
}
QPushButton#btnSave:hover    { background-color: rgb(60, 170, 100); }
QPushButton#btnSave:disabled { background-color: rgb(28, 75, 50); border-color: rgb(40, 90, 60); }
QPushButton#btnCancel {
    background-color: rgb(110, 70, 20);
    border: 1px solid rgb(150, 100, 30);
}
QPushButton#btnCancel:hover { background-color: rgb(150, 100, 30); }
QLineEdit {
    background-color: rgb(25, 22, 38);
    border: 1px solid rgb(69, 71, 90);
    border-radius: 4px;
    padding: 4px 6px;
}
QLineEdit:focus { border-color: rgb(100, 60, 160); }
QTextEdit {
    background-color: rgb(11, 11, 18);
    border: 1px solid rgb(49, 50, 68);
    border-radius: 4px;
    font-family: monospace;
    font-size: 11px;
    color: rgb(205, 214, 244);
}
QTableWidget {
    background-color: rgb(20, 18, 32);
    border: 1px solid rgb(69, 71, 90);
    border-radius: 4px;
    gridline-color: rgb(40, 40, 60);
}
QTableWidget::item { padding: 3px 6px; }
QTableWidget::item:selected { background-color: rgb(60, 50, 100); }
QHeaderView::section {
    background-color: rgb(28, 26, 42);
    border: none;
    border-bottom: 1px solid rgb(69, 71, 90);
    padding: 4px 8px;
    color: rgb(180, 170, 210);
}
QRadioButton, QCheckBox { spacing: 6px; }
QRadioButton::indicator, QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid rgb(100, 60, 160);
    border-radius: 7px;
    background: rgb(25, 22, 38);
}
QCheckBox::indicator { border-radius: 3px; }
QRadioButton::indicator:checked,
QCheckBox::indicator:checked { background: rgb(100, 60, 160); }
QSplitter::handle { background-color: rgb(49, 50, 68); }
QSplitter::handle:horizontal { width: 2px; }
QScrollBar:vertical {
    background: rgb(18, 18, 28); width: 8px; margin: 0; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: rgb(69, 71, 90); min-height: 24px; border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: rgb(100, 60, 160); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: rgb(18, 18, 28); height: 8px; margin: 0; border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: rgb(69, 71, 90); min-width: 24px; border-radius: 4px;
}
QScrollBar::handle:horizontal:hover { background: rgb(100, 60, 160); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QStatusBar { border-top: 1px solid rgb(49, 50, 68); color: rgb(130, 120, 160); }
"""

LOG_COLORS = {
    "error":   "#f38ba8",
    "warning": "#fab387",
    "success": "#a6e3a1",
    "dim":     "#585b70",
    "default": "#cdd6f4",
}


# ---------------------------------------------------------------------------
# Assets table widget
# ---------------------------------------------------------------------------
class AssetsTable(QWidget):
    """Editable source → dest table for --add-data entries."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Source  (file or folder)", "Dest in bundle"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(110)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_file = QPushButton("+ File")
        btn_dir  = QPushButton("+ Folder")
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setObjectName("btnDanger")
        btn_file.clicked.connect(self._add_file)
        btn_dir.clicked.connect(self._add_dir)
        self.btn_remove.clicked.connect(self._remove_selected)
        btn_row.addWidget(btn_file)
        btn_row.addWidget(btn_dir)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_remove)
        layout.addLayout(btn_row)

    # ---- internal ----

    def _insert(self, src: str, dest: str = "."):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(src))
        self.table.setItem(row, 1, QTableWidgetItem(dest))

    def _add_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select asset file")
        if path:
            self._insert(path)

    def _add_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select asset folder")
        if path:
            self._insert(path, os.path.basename(path))

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    # ---- public ----

    def get_pairs(self) -> list[tuple[str, str]]:
        result = []
        for r in range(self.table.rowCount()):
            src  = (self.table.item(r, 0) or QTableWidgetItem("")).text().strip()
            dest = (self.table.item(r, 1) or QTableWidgetItem(".")).text().strip() or "."
            if src:
                result.append((src, dest))
        return result

    def set_pairs(self, pairs: list[dict]):
        self.table.setRowCount(0)
        for p in pairs:
            self._insert(p.get("src", ""), p.get("dest", "."))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class BuilderWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Equestria OS App Builder")
        self.setMinimumSize(960, 660)
        self._process: QProcess | None = None
        self._project_path: str | None = None
        self._installing = False
        self._pyinstaller_ok = False
        self._pyinstaller_cmd: list[str] = []
        self._setup_ui()
        self._check_pyinstaller()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("Equestria OS App Builder")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: rgb(137, 180, 250);")
        header.addWidget(title)
        header.addStretch()
        for text, slot in [("New", self._new_project),
                            ("Load project…", self._load_project),
                            ("Save project…", self._save_project)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            header.addWidget(btn)
        root.addLayout(header)

        # ── Splitter: left = config scroll, right = log ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- Config panel (inside scroll area) ----
        config_inner = QWidget()
        config_layout = QVBoxLayout(config_inner)
        config_layout.setContentsMargins(4, 4, 4, 4)
        config_layout.setSpacing(8)

        # Entry point
        grp_entry = QGroupBox("Entry point")
        g = QVBoxLayout(grp_entry)
        row = QHBoxLayout()
        self.txt_script = QLineEdit()
        self.txt_script.setPlaceholderText("Path to main .py script…")
        btn_browse_script = QPushButton("…")
        btn_browse_script.setFixedWidth(32)
        btn_browse_script.clicked.connect(self._browse_script)
        row.addWidget(self.txt_script)
        row.addWidget(btn_browse_script)
        g.addLayout(row)
        config_layout.addWidget(grp_entry)

        # Output settings
        grp_out = QGroupBox("Output")
        g2 = QVBoxLayout(grp_out)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("App name:"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("my-application")
        name_row.addWidget(self.txt_name)
        g2.addLayout(name_row)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Output dir:"))
        self.txt_outdir = QLineEdit(os.path.expanduser("~/Desktop"))
        btn_browse_out = QPushButton("…")
        btn_browse_out.setFixedWidth(32)
        btn_browse_out.clicked.connect(self._browse_outdir)
        dir_row.addWidget(self.txt_outdir)
        dir_row.addWidget(btn_browse_out)
        g2.addLayout(dir_row)

        mode_row = QHBoxLayout()
        self.radio_onefile = QRadioButton("One file")
        self.radio_onedir  = QRadioButton("One directory")
        self.radio_onefile.setChecked(True)
        grp_mode = QButtonGroup(self)
        grp_mode.addButton(self.radio_onefile)
        grp_mode.addButton(self.radio_onedir)
        self.chk_windowed = QCheckBox("No console window")
        mode_row.addWidget(self.radio_onefile)
        mode_row.addWidget(self.radio_onedir)
        mode_row.addStretch()
        mode_row.addWidget(self.chk_windowed)
        g2.addLayout(mode_row)

        config_layout.addWidget(grp_out)

        # Assets
        grp_assets = QGroupBox("Data files / assets")
        ga = QVBoxLayout(grp_assets)
        self.assets_table = AssetsTable()
        ga.addWidget(self.assets_table)
        config_layout.addWidget(grp_assets)

        # Hidden imports
        grp_hidden = QGroupBox("Hidden imports  (comma-separated)")
        gh = QVBoxLayout(grp_hidden)
        self.txt_hidden = QLineEdit()
        self.txt_hidden.setPlaceholderText("PyQt6.sip, some.module, …")
        gh.addWidget(self.txt_hidden)
        config_layout.addWidget(grp_hidden)

        # Extra PyInstaller flags
        grp_extra = QGroupBox("Extra PyInstaller flags  (one per line)")
        ge = QVBoxLayout(grp_extra)
        self.txt_extra = QTextEdit()
        self.txt_extra.setPlaceholderText("--strip\n--upx-dir /path/to/upx\n…")
        self.txt_extra.setFixedHeight(72)
        ge.addWidget(self.txt_extra)
        config_layout.addWidget(grp_extra)

        config_layout.addStretch()

        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        config_scroll.setWidget(config_inner)

        # ---- Log panel ----
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(6, 0, 0, 0)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_label = QLabel("Build log")
        log_label.setStyleSheet("font-weight: bold; color: rgb(180, 170, 210);")
        btn_clear_log = QPushButton("Clear")
        btn_clear_log.clicked.connect(self._log_view_clear)
        log_header.addWidget(log_label)
        log_header.addStretch()
        log_header.addWidget(btn_clear_log)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("monospace", 11))

        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_view)

        splitter.addWidget(config_scroll)
        splitter.addWidget(log_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        # ── Bottom bar ──
        bottom = QHBoxLayout()
        self.btn_build = QPushButton("▶  Build")
        self.btn_build.setObjectName("btnBuild")
        self.btn_build.setEnabled(False)
        self.btn_build.clicked.connect(self._start_build)

        self.btn_install_pyi = QPushButton("Install PyInstaller")
        self.btn_install_pyi.setObjectName("btnSave")
        self.btn_install_pyi.clicked.connect(self._install_pyinstaller)

        self.btn_clean = QPushButton("Clean output dir")
        self.btn_clean.setObjectName("btnDanger")
        self.btn_clean.clicked.connect(self._clean_output)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_build)

        self.lbl_pyi_status = QLabel()

        self.btn_open = QPushButton("Open output folder")
        self.btn_open.clicked.connect(self._open_output)

        bottom.addWidget(self.btn_build)
        bottom.addWidget(self.btn_install_pyi)
        bottom.addWidget(self.btn_clean)
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.lbl_pyi_status)
        bottom.addStretch()
        bottom.addWidget(self.btn_open)
        root.addLayout(bottom)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------
    # Known frameworks that need --collect-all to bundle properly
    _COLLECT_ALL_PATTERNS = {
        "PyQt6":   "import PyQt6",
        "PyQt5":   "import PyQt5",
        "PySide6": "import PySide6",
        "PySide2": "import PySide2",
        "tkinter": "import tkinter",
        "wx":      "import wx",
        "kivy":    "import kivy",
        "pygame":  "import pygame",
    }

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select entry-point script", filter="Python scripts (*.py);;All files (*)"
        )
        if not path:
            return
        self.txt_script.setText(path)
        if not self.txt_name.text().strip():
            self.txt_name.setText(os.path.splitext(os.path.basename(path))[0])
        self._auto_detect_frameworks(path)

    def _auto_detect_frameworks(self, script_path: str):
        """Scan the script for known GUI frameworks and add --collect-all flags."""
        try:
            with open(script_path, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except OSError:
            return

        detected = [
            name for name, pattern in self._COLLECT_ALL_PATTERNS.items()
            if pattern in source
        ]
        if not detected:
            return

        existing = self.txt_extra.toPlainText().strip()
        new_flags = "\n".join(f"--collect-all {name}" for name in detected)
        # Avoid duplicates
        lines = existing.splitlines() if existing else []
        for flag in new_flags.splitlines():
            if flag not in lines:
                lines.append(flag)
        self.txt_extra.setPlainText("\n".join(lines))
        self.status_bar.showMessage(f"Auto-detected: {', '.join(detected)}")

    def _browse_outdir(self):
        path = QFileDialog.getExistingDirectory(self, "Select output directory")
        if path:
            self.txt_outdir.setText(path)

    # ------------------------------------------------------------------
    # Project save / load
    # ------------------------------------------------------------------
    def _to_dict(self) -> dict:
        return {
            "script":         self.txt_script.text().strip(),
            "name":           self.txt_name.text().strip(),
            "output_dir":     self.txt_outdir.text().strip(),
            "mode":           "onefile" if self.radio_onefile.isChecked() else "onedir",
            "windowed":       self.chk_windowed.isChecked(),
            "hidden_imports": self.txt_hidden.text().strip(),
            "extra_flags":    self.txt_extra.toPlainText().strip(),
            "assets":         [{"src": s, "dest": d} for s, d in self.assets_table.get_pairs()],
        }

    def _from_dict(self, d: dict):
        self.txt_script.setText(d.get("script", ""))
        self.txt_name.setText(d.get("name", ""))
        self.txt_outdir.setText(d.get("output_dir", os.path.expanduser("~/Desktop")))
        if d.get("mode", "onefile") == "onedir":
            self.radio_onedir.setChecked(True)
        else:
            self.radio_onefile.setChecked(True)
        self.chk_windowed.setChecked(bool(d.get("windowed", False)))
        self.txt_hidden.setText(d.get("hidden_imports", ""))
        self.txt_extra.setPlainText(d.get("extra_flags", ""))
        self.assets_table.set_pairs(d.get("assets", []))

    def _new_project(self):
        self._from_dict({})
        self._project_path = None
        self.setWindowTitle("Equestria OS App Builder")

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load project",
            filter="Builder project (*.ebuilder);;JSON (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._from_dict(json.load(f))
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))
            return
        self._project_path = path
        self._update_title()
        self.status_bar.showMessage(f"Loaded: {path}")

    def _save_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save project",
            filter="Builder project (*.ebuilder);;JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._to_dict(), f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))
            return
        self._project_path = path
        self._update_title()
        self.status_bar.showMessage(f"Saved: {path}")

    def _update_title(self):
        if self._project_path:
            self.setWindowTitle(f"Equestria OS App Builder — {os.path.basename(self._project_path)}")
        else:
            self.setWindowTitle("Equestria OS App Builder")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build_command(self) -> list[str] | None:
        script = self.txt_script.text().strip()
        if not script or not os.path.isfile(script):
            QMessageBox.warning(self, "No script", "Select a valid Python entry-point script first.")
            return None

        name    = self.txt_name.text().strip() or os.path.splitext(os.path.basename(script))[0]
        out_dir = self.txt_outdir.text().strip() or os.path.expanduser("~/Desktop")

        cmd = self._pyinstaller_cmd + ["--noconfirm"]
        cmd += ["--onefile"] if self.radio_onefile.isChecked() else ["--onedir"]
        if self.chk_windowed.isChecked():
            cmd += ["--windowed"]
        cmd += ["--name", name, "--distpath", out_dir]

        for src, dest in self.assets_table.get_pairs():
            if not os.path.exists(src):
                self._log(f"WARNING: asset not found, skipping: {src}\n", "warning")
                continue
            cmd += ["--add-data", f"{src}:{dest}"]

        for imp in self.txt_hidden.text().split(","):
            imp = imp.strip()
            if imp:
                cmd += ["--hidden-import", imp]

        for flag in self.txt_extra.toPlainText().splitlines():
            flag = flag.strip()
            if flag:
                cmd.append(flag)

        cmd.append(script)
        return cmd

    # ------------------------------------------------------------------
    # PyInstaller check / install
    # ------------------------------------------------------------------
    def _check_pyinstaller(self):
        """Try to locate PyInstaller: first in PATH (pipx), then as a Python module."""
        # 1. Binary in PATH (installed via pipx or system package)
        binary = shutil.which("pyinstaller")
        if binary:
            result = subprocess.run([binary, "--version"], capture_output=True)
            if result.returncode == 0:
                ver = result.stdout.decode().strip()
                self._pyinstaller_cmd = [binary]
                self._set_pyi_found(ver)
                return

        # 2. Python module (installed via pacman as python-pyinstaller)
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
        )
        if result.returncode == 0:
            ver = result.stdout.decode().strip()
            self._pyinstaller_cmd = [sys.executable, "-m", "PyInstaller"]
            self._set_pyi_found(ver)
            return

        # Not found
        self._pyinstaller_cmd = []
        self._pyinstaller_ok = False
        self.lbl_pyi_status.setText("PyInstaller not installed")
        self.lbl_pyi_status.setStyleSheet("color: #f38ba8; font-size: 11px;")
        self.btn_install_pyi.setVisible(True)
        self.btn_build.setEnabled(False)

    def _set_pyi_found(self, ver: str):
        self._pyinstaller_ok = True
        self.lbl_pyi_status.setText(f"PyInstaller {ver} ✓")
        self.lbl_pyi_status.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        self.btn_install_pyi.setVisible(False)
        self.btn_build.setEnabled(True)

    def _install_pyinstaller(self):
        """Install PyInstaller: try pipx first, then pkexec pacman."""
        self.log_view.clear()

        # Prefer pipx — avoids the externally-managed-environment error
        if shutil.which("pipx"):
            cmd = ["pipx", "install", "pyinstaller"]
        elif shutil.which("pkexec") and shutil.which("pacman"):
            cmd = ["pkexec", "pacman", "-S", "--noconfirm", "python-pyinstaller"]
        else:
            self._log(
                "Cannot install automatically.\n\n"
                "Please run one of these in a terminal:\n"
                "  pipx install pyinstaller\n"
                "  sudo pacman -S python-pyinstaller\n",
                "warning",
            )
            return

        self._log("$ " + " ".join(cmd) + "\n\n", "dim")
        self._installing = True
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyRead.connect(self._on_output)
        self._process.finished.connect(self._on_finished)

        self.btn_install_pyi.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.status_bar.showMessage("Installing PyInstaller…")
        self._process.start(cmd[0], cmd[1:])

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _start_build(self):
        cmd = self._build_command()
        if cmd is None:
            return

        self.log_view.clear()
        self._log("$ " + " ".join(cmd) + "\n\n", "dim")

        script = self.txt_script.text().strip()
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.setWorkingDirectory(os.path.dirname(script))
        self._process.readyRead.connect(self._on_output)
        self._process.finished.connect(self._on_finished)

        self.btn_build.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.status_bar.showMessage("Building…")

        self._process.start(cmd[0], cmd[1:])

    def _on_output(self):
        raw  = bytes(self._process.readAll())
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines(keepends=True):
            ll = line.lower()
            if "error" in ll:
                self._log(line, "error")
            elif "warn" in ll:
                self._log(line, "warning")
            else:
                self._log(line)

    def _on_finished(self, exit_code: int, _status):
        self.btn_cancel.setEnabled(False)
        self._process = None

        if self._installing:
            self._installing = False
            self.btn_install_pyi.setEnabled(True)
            if exit_code == 0:
                self._log("\n✓  PyInstaller installed successfully.\n", "success")
                self.status_bar.showMessage("PyInstaller installed.")
            else:
                self._log(f"\n✗  Installation failed (exit code {exit_code})\n", "error")
                self.status_bar.showMessage(f"Installation failed (code {exit_code})")
            self._check_pyinstaller()
            return

        self.btn_build.setEnabled(True)
        name = self.txt_name.text().strip()
        if exit_code == 0:
            self._log(f"\n✓  Build succeeded: {name}\n", "success")
            self.status_bar.showMessage(f"Build succeeded: {name}")
        else:
            self._log(f"\n✗  Build failed (exit code {exit_code})\n", "error")
            self.status_bar.showMessage(f"Build failed (code {exit_code})")

    def _cancel_build(self):
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
        if self._installing:
            self._installing = False
            self.btn_install_pyi.setEnabled(True)
        self.btn_build.setEnabled(self._pyinstaller_ok)
        self.btn_cancel.setEnabled(False)
        self._log("\n— Cancelled.\n", "dim")
        self.status_bar.showMessage("Cancelled.")

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def _log(self, text: str, color: str = ""):
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(LOG_COLORS.get(color, LOG_COLORS["default"])))
        cursor.insertText(text, fmt)
        self.log_view.setTextCursor(cursor)
        self.log_view.ensureCursorVisible()

    def _log_view_clear(self):
        self.log_view.clear()

    # ------------------------------------------------------------------
    # Output directory helpers
    # ------------------------------------------------------------------
    def _clean_output(self):
        out_dir = self.txt_outdir.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            QMessageBox.information(self, "Nothing to clean", f"Directory does not exist:\n{out_dir}")
            return
        reply = QMessageBox.question(
            self, "Clean output directory",
            f"Delete all contents of:\n{out_dir}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            shutil.rmtree(out_dir)
            os.makedirs(out_dir)
            self.status_bar.showMessage(f"Cleaned: {out_dir}")

    def _open_output(self):
        out_dir = self.txt_outdir.text().strip() or os.path.expanduser("~/Desktop")
        if os.path.isdir(out_dir):
            subprocess.Popen(["xdg-open", out_dir])
        else:
            QMessageBox.information(self, "Not found", f"Directory does not exist:\n{out_dir}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)

    for candidate in (
        "/usr/share/pixmaps/equestria-os-proton-starter.png",
        "/usr/share/pixmaps/equestria-os.png",
    ):
        if os.path.exists(candidate):
            app.setWindowIcon(QIcon(candidate))
            break

    window = BuilderWindow()
    window.show()
    sys.exit(app.exec())
