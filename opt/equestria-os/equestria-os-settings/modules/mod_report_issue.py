"""Report a Problem — sends bug reports to the equestria-os-packages GitHub repo.

No GitHub token is ever stored or shipped in this app: the module builds a
pre-filled "new issue" URL and hands it off to the user's own browser, where
they review it and click Submit while logged into their own account. This
keeps the process safe for mass distribution (an embedded write token would
let anyone extract it from the package and abuse the repo).
"""

import os
import platform
import re
import shutil
import subprocess
import threading
from urllib.parse import quote

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from base_module import BaseModule

_REPO = "Lucia7Lunadottir/equestria-os-packages"
_MAX_BODY_LEN = 6000  # keep the generated URL well under browser/CDN limits

_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
)
_BTN_SEND = (
    "QPushButton{background:rgb(80,55,130);color:white;"
    "border-radius:8px;padding:8px 22px;font-size:14px;font-weight:bold;"
    "border:1px solid rgb(110,80,170);}"
    "QPushButton:hover{background:rgb(110,75,170);"
    "border:1px solid rgb(140,100,210);}"
)
_STATUS_MONO = (
    "QLabel{color:rgb(170,165,195);font-size:12px;font-family:monospace;"
    "background:rgb(20,18,33);border:1px solid rgb(50,47,72);"
    "border-radius:6px;padding:8px 12px;}"
)
_RESULT_ERR = "QLabel{color:rgb(255,130,130);font-size:12px;background:transparent;}"


# ── Diagnostics collection (self-contained, no cross-module imports) ───────

def _read_os_release() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            data = {}
            for line in f:
                if "=" in line:
                    k, _, v = line.strip().partition("=")
                    data[k] = v.strip('"')
        return data.get("PRETTY_NAME") or data.get("NAME") or "Unknown"
    except OSError:
        return "Unknown"


def _read_cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "Unknown"


def _detect_gpu_and_driver() -> tuple[str, str]:
    """Return (gpu_name, kernel_driver) parsed from `lspci -k`. No X/GL needed."""
    if not shutil.which("lspci"):
        return "Unknown", "Unknown"
    try:
        out = subprocess.run(["lspci", "-k"], capture_output=True, text=True, timeout=5)
    except Exception:
        return "Unknown", "Unknown"

    gpu_name, driver = "Unknown", "Unknown"
    lines = out.stdout.splitlines()
    for i, line in enumerate(lines):
        if any(k in line for k in ("VGA", "3D controller", "Display controller")):
            parts = line.split(":", 2)
            gpu_name = parts[-1].strip() if len(parts) >= 2 else line.strip()
            for follow in lines[i + 1:i + 4]:
                if not follow.startswith("\t"):
                    break
                m = re.match(r"\s*Kernel driver in use:\s*(\S+)", follow)
                if m:
                    driver = m.group(1)
                    break
            break
    return gpu_name, driver


def _get_equestria_packages() -> list[str]:
    if not shutil.which("pacman"):
        return []
    try:
        out = subprocess.run(
            ["pacman", "-Qs", "equestria"], capture_output=True, text=True, timeout=5
        )
    except Exception:
        return []
    pkgs = []
    for line in out.stdout.splitlines():
        if line.startswith("local/"):
            parts = line.split()
            if parts:
                pkgs.append(parts[0].replace("local/", ""))
    return pkgs


def _collect_diagnostics() -> dict:
    gpu_name, gpu_driver = _detect_gpu_and_driver()
    return {
        "os": _read_os_release(),
        "kernel": platform.release(),
        "cpu": _read_cpu_model(),
        "gpu": gpu_name,
        "gpu_driver": gpu_driver,
        "packages": _get_equestria_packages(),
    }


def _format_diagnostics(info: dict) -> str:
    lines = [
        f"- OS: {info['os']}",
        f"- Kernel: {info['kernel']}",
        f"- CPU: {info['cpu']}",
        f"- GPU: {info['gpu']}",
        f"- GPU driver: {info['gpu_driver']}",
    ]
    if info["packages"]:
        lines.append(f"- Equestria packages: {', '.join(info['packages'])}")
    return "\n".join(lines)


# ── Worker ───────────────────────────────────────────────────────────────────

class _DiagnosticsWorker(QObject):
    done = pyqtSignal(dict)

    def run(self):
        self.done.emit(_collect_diagnostics())


# ── Module ───────────────────────────────────────────────────────────────────

class ReportIssueModule(BaseModule):
    module_id = "mod_report_issue"
    display_name_key = "module.report_issue.name"
    description_key = "module.report_issue.desc"
    category = "system"
    icon = "🐞"
    sort_order = 90
    required_binary = ""
    package_name = ""

    # ── Build ─────────────────────────────────────────────────────────────────

    def build_widget(self) -> QWidget:
        outer = QWidget()
        outer.setObjectName("ContentPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(outer)
        scroll.setObjectName("ContentPage")

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        self._build_form_card(layout)
        self._build_diagnostics_card(layout)

        layout.addStretch()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    def _build_form_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._form_title_lbl = QLabel(self.t("report_issue.form_title"))
        self._form_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._form_title_lbl)

        self._title_field_lbl = QLabel(self.t("report_issue.title_label"))
        self._title_field_lbl.setObjectName("FieldLabel")
        layout.addWidget(self._title_field_lbl)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText(self.t("report_issue.title_placeholder"))
        layout.addWidget(self._title_edit)

        self._body_field_lbl = QLabel(self.t("report_issue.body_label"))
        self._body_field_lbl.setObjectName("FieldLabel")
        layout.addWidget(self._body_field_lbl)

        self._body_edit = QPlainTextEdit()
        self._body_edit.setPlaceholderText(self.t("report_issue.body_placeholder"))
        self._body_edit.setFixedHeight(140)
        layout.addWidget(self._body_edit)

        self._diag_checkbox = QCheckBox(self.t("report_issue.include_diagnostics"))
        self._diag_checkbox.setChecked(True)
        layout.addWidget(self._diag_checkbox)

        btn_row = QHBoxLayout()
        self._send_btn = QPushButton(self.t("report_issue.send_btn"))
        self._send_btn.setStyleSheet(_BTN_SEND)
        self._send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self._send_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(_RESULT_ERR)
        self._error_lbl.setWordWrap(True)
        self._error_lbl.hide()
        layout.addWidget(self._error_lbl)

        self._hint_lbl = QLabel(self.t("report_issue.browser_hint"))
        self._hint_lbl.setObjectName("FieldHint")
        self._hint_lbl.setWordWrap(True)
        layout.addWidget(self._hint_lbl)

        parent_layout.addWidget(card)

    def _build_diagnostics_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        row = QHBoxLayout()
        self._diag_title_lbl = QLabel(self.t("report_issue.diag_title"))
        self._diag_title_lbl.setObjectName("SectionTitle")
        row.addWidget(self._diag_title_lbl)
        row.addStretch()
        self._diag_refresh_btn = QPushButton(self.t("report_issue.diag_refresh"))
        self._diag_refresh_btn.setStyleSheet(_BTN_ACTION)
        self._diag_refresh_btn.clicked.connect(self._refresh_diagnostics)
        row.addWidget(self._diag_refresh_btn)
        layout.addLayout(row)

        self._diag_lbl = QLabel(self.t("report_issue.diag_loading"))
        self._diag_lbl.setStyleSheet(_STATUS_MONO)
        self._diag_lbl.setWordWrap(True)
        layout.addWidget(self._diag_lbl)

        parent_layout.addWidget(card)
        self._diag_text = ""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_shown(self) -> None:
        self._refresh_diagnostics()

    def apply_language(self) -> None:
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._form_title_lbl.setText(self.t("report_issue.form_title"))
        self._title_field_lbl.setText(self.t("report_issue.title_label"))
        self._title_edit.setPlaceholderText(self.t("report_issue.title_placeholder"))
        self._body_field_lbl.setText(self.t("report_issue.body_label"))
        self._body_edit.setPlaceholderText(self.t("report_issue.body_placeholder"))
        self._diag_checkbox.setText(self.t("report_issue.include_diagnostics"))
        self._send_btn.setText(self.t("report_issue.send_btn"))
        self._hint_lbl.setText(self.t("report_issue.browser_hint"))
        self._diag_title_lbl.setText(self.t("report_issue.diag_title"))
        self._diag_refresh_btn.setText(self.t("report_issue.diag_refresh"))

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def _refresh_diagnostics(self):
        self._diag_lbl.setText(self.t("report_issue.diag_loading"))
        worker = _DiagnosticsWorker()
        worker.done.connect(self._on_diagnostics_ready)
        self._diag_worker = worker
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_diagnostics_ready(self, info: dict):
        self._diag_text = _format_diagnostics(info)
        self._diag_lbl.setText(self._diag_text)

    # ── Send ──────────────────────────────────────────────────────────────────

    def _on_send(self):
        title = self._title_edit.text().strip()
        if not title:
            self._error_lbl.setText(self.t("report_issue.title_required"))
            self._error_lbl.show()
            return
        self._error_lbl.hide()

        body = self._body_edit.toPlainText().strip()
        if self._diag_checkbox.isChecked() and self._diag_text:
            details = (
                f"\n\n<details>\n<summary>{self.t('report_issue.diag_summary')}</summary>\n\n"
                f"{self._diag_text}\n\n</details>"
            )
            body = body + details

        if len(body) > _MAX_BODY_LEN:
            body = body[:_MAX_BODY_LEN] + "\n\n…(truncated)"

        url = (
            f"https://github.com/{_REPO}/issues/new"
            f"?title={quote(title)}&body={quote(body)}"
        )
        QDesktopServices.openUrl(QUrl(url))
