import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QMessageBox,
    QCheckBox, QProgressBar, QSpinBox, QSlider, QComboBox, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFontDatabase

import privilege
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import live_i18n
from equestria_kit.widgets import font_families

# Переводы лежат в locales/<язык>.json рядом с swap_app.py (ключ -> текст)
CATALOG = live_i18n.Catalog("equestria-os-swap-manager", __file__)

ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKMARK_SVG = os.path.join(ASSETS_DIR, "check_mark.svg")


def generate_assets():
    if os.path.exists(CHECKMARK_SVG):
        return
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path fill="#ffffff" d="M13.485 1.414l1.414 1.414L6.343 11.373 1.1 6.13l1.414-1.414 3.829 3.829z"/>
</svg>"""
    try:
        with open(CHECKMARK_SVG, 'w') as f:
            f.write(svg_content)
    except Exception:
        pass


def _get_ram_gb() -> int:
    """Return total system RAM in whole GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return max(1, kb // 1024 // 1024)
    except Exception:
        pass
    return 8



class SwapWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, command_args):
        super().__init__()
        self.command_args = command_args

    def run(self):
        elevator = privilege.find_elevator()
        if not elevator:
            self.finished.emit(False, "No elevation tool found.")
            return

        if getattr(sys, 'frozen', False):
            backend_script = os.path.join(os.path.dirname(sys.executable), "equestria-os-swap-backend")
            inner = [backend_script] + self.command_args
        else:
            backend_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swap_backend.py")
            inner = [sys.executable, backend_script] + self.command_args

        cmd = [elevator, "--"] + inner if os.path.basename(elevator) == "kdesu" else [elevator] + inner

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            self.finished.emit(True, stdout.strip())
        else:
            self.finished.emit(False, stderr.strip())


class SwapManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = CATALOG.lang or "en"

        self._setup_ui()
        self._load_data()

    def t(self, key):
        return str(CATALOG.tr(key))

    def _change_lang(self, lang):
        self.current_lang = CATALOG.set_language(lang) or lang  # ещё и сохраняет выбор
        idx = self.lang_combo.findData(lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self._refresh_ui()

    def _make_divider(self):
        d = QFrame()
        d.setObjectName("Divider")
        d.setFrameShape(QFrame.Shape.HLine)
        d.setFixedHeight(1)
        return d

    def _setup_ui(self):
        self.setWindowTitle(self.t("title"))
        self.resize(780, 820)

        base_path = os.path.dirname(os.path.abspath(__file__))

        title_font_family = "sans-serif"
        font_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            families = font_families(font_path)
            if families:
                title_font_family = families[0]

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            qss = open(qss_path).read()
            qss = qss.replace("{{CHECKMARK_SVG_PATH}}", CHECKMARK_SVG)
            qss = qss.replace("{{TITLE_FONT}}", f'"{title_font_family}"')
            qss += """
            QSlider::groove:horizontal { border-radius: 4px; height: 6px; background: @surface0@; }
            QSlider::handle:horizontal { background: @accent@; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::handle:horizontal:hover { background: @accent_hover@; }
            QComboBox { background-color: @base@; color: @text@; border: 1px solid @surface1@; border-radius: 6px; padding: 4px 8px; min-height: 28px; }
            QComboBox#LangCombo { min-height: 22px; padding: 2px 8px; font-size: 11px; min-width: 46px; }
            QComboBox QAbstractItemView { background-color: @base@; color: @text@; selection-background-color: @surface0@; border: 1px solid @surface1@; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: @base@; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: @surface1@; border-radius: 4px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { background: @base@; height: 8px; border-radius: 4px; }
            QScrollBar::handle:horizontal { background: @surface1@; border-radius: 4px; min-width: 20px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QLabel#HintLabel { color: @subtext@; font-size: 11px; font-style: italic; }
            QMenu { background-color: @base@; color: @text@; border: 1px solid @surface1@; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: @surface0@; }
            QMenu::separator { height: 1px; background: @surface1@; margin: 4px 8px; }
            QLabel#ZramStatusLabel { color: @green@; font-size: 12px; font-weight: bold; }
            QPushButton#WindowsBtn { background-color: @accent2%25@; border: 2px solid @accent2@; border-radius: 8px; color: @accent2@; font-size: 13px; font-weight: bold; padding: 6px 18px; }
            QPushButton#WindowsBtn:hover { background-color: @accent2%35@; }
            QPushButton#WindowsBtn:pressed { background-color: @accent2%15@; }
            """
            kit_qt.style(self, qss)

        # Outer widget
        central = QWidget()
        central.setObjectName("CentralBg")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area so content is always accessible
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("CentralBg")
        scroll.setWidget(content)
        L = QVBoxLayout(content)
        L.setContentsMargins(30, 20, 30, 20)
        L.setSpacing(12)

        # ── Title & Lang ──────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        self.app_title = QLabel(self.t("title"))
        self.app_title.setObjectName("AppTitle")
        title_row.addWidget(self.app_title)
        title_row.addStretch()

        # Компактный выпадающий список языков вместо ряда кнопок
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        # языки — найденные файлы locales/*.json, названия — из них же (_language_name)
        for code in CATALOG.languages:
            self.lang_combo.addItem(CATALOG.language_name(code), code)
        idx = self.lang_combo.findData(self.current_lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        # activated срабатывает только при выборе пользователем — без рекурсии
        self.lang_combo.activated.connect(
            lambda i: self._change_lang(self.lang_combo.itemData(i)))
        title_row.addWidget(self.lang_combo)
        L.addLayout(title_row)
        L.addWidget(self._make_divider())

        # ── Active Swap Info ──────────────────────────────────────────────────
        info_row = QHBoxLayout()
        self.lbl_current = QLabel(self.t("current_swap"))
        self.lbl_current.setObjectName("SectionLabel")
        info_row.addWidget(self.lbl_current)
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setObjectName("BrowseBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._load_data)
        info_row.addWidget(self.refresh_btn)
        info_row.addStretch()
        L.addLayout(info_row)
        self.info_lbl = QLabel(self.t("no_swap"))
        self.info_lbl.setObjectName("StatusLabel")
        L.addWidget(self.info_lbl)
        L.addWidget(self._make_divider())

        # ── Swap File Settings ────────────────────────────────────────────────
        self.lbl_path = QLabel(self.t("path"))
        self.lbl_path.setObjectName("SectionLabel")
        L.addWidget(self.lbl_path)
        self.path_input = QLineEdit()
        self.path_input.setObjectName("DestEdit")
        self.path_input.setText("/swapfile")
        L.addWidget(self.path_input)

        size_row = QHBoxLayout()
        self.lbl_size = QLabel(self.t("size"))
        self.lbl_size.setObjectName("SectionLabel")
        size_row.addWidget(self.lbl_size)
        self.size_spin = QSpinBox()
        self.size_spin.setObjectName("SourceEdit")
        self.size_spin.setRange(1, 256)
        self.size_spin.setValue(32)
        self.size_spin.setSuffix(" GB")
        self.size_spin.setFixedHeight(34)
        size_row.addWidget(self.size_spin)
        size_row.addStretch()
        L.addLayout(size_row)

        self.fstab_cb = QCheckBox(self.t("fstab_chk"))
        self.fstab_cb.setChecked(True)
        self.fstab_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fstab_cb.setObjectName("SwapCheckBox")
        L.addWidget(self.fstab_cb)

        self.apply_btn = QPushButton(self.t("btn_apply"))
        self.apply_btn.setObjectName("RelocateBtn")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.clicked.connect(self._apply_swap)
        L.addWidget(self.apply_btn)

        action_row = QHBoxLayout()
        self.disable_btn = QPushButton(self.t("btn_disable"))
        self.disable_btn.setObjectName("BrowseBtn")
        self.disable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.disable_btn.clicked.connect(self._disable_swap)
        self.delete_btn = QPushButton(self.t("btn_delete"))
        self.delete_btn.setObjectName("DangerBtn")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(self._delete_swap)
        action_row.addWidget(self.disable_btn)
        action_row.addWidget(self.delete_btn)
        L.addLayout(action_row)
        L.addWidget(self._make_divider())

        # ── Swappiness ────────────────────────────────────────────────────────
        self.lbl_swappiness = QLabel(self.t("swappiness"))
        self.lbl_swappiness.setObjectName("SectionLabel")
        L.addWidget(self.lbl_swappiness)
        swapp_row = QHBoxLayout()
        self.swapp_slider = QSlider(Qt.Orientation.Horizontal)
        self.swapp_slider.setRange(0, 100)
        self.swapp_slider.setValue(60)
        self.swapp_slider.valueChanged.connect(lambda v: self.swapp_val_lbl.setText(str(v)))
        self.swapp_val_lbl = QLabel("60")
        self.swapp_val_lbl.setObjectName("StatusLabel")
        self.swapp_val_lbl.setFixedWidth(30)
        swapp_row.addWidget(self.swapp_slider)
        swapp_row.addWidget(self.swapp_val_lbl)
        L.addLayout(swapp_row)
        self.apply_swapp_btn = QPushButton(self.t("btn_swapp"))
        self.apply_swapp_btn.setObjectName("BrowseBtn")
        self.apply_swapp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_swapp_btn.clicked.connect(self._apply_swappiness)
        L.addWidget(self.apply_swapp_btn)
        L.addWidget(self._make_divider())

        # ── Fast Swap (zram) ──────────────────────────────────────────────────
        self.lbl_zram_section = QLabel(self.t("zram_section"))
        self.lbl_zram_section.setObjectName("SectionLabel")
        L.addWidget(self.lbl_zram_section)

        self.lbl_zram_hint = QLabel(self.t("zram_hint"))
        self.lbl_zram_hint.setObjectName("HintLabel")
        self.lbl_zram_hint.setWordWrap(True)
        L.addWidget(self.lbl_zram_hint)

        zram_status_row = QHBoxLayout()
        self.lbl_zram_status_key = QLabel(self.t("zram_status"))
        self.lbl_zram_status_key.setObjectName("SectionLabel")
        self.lbl_zram_status_val = QLabel(self.t("zram_inactive"))
        self.lbl_zram_status_val.setObjectName("ZramStatusLabel")
        zram_status_row.addWidget(self.lbl_zram_status_key)
        zram_status_row.addWidget(self.lbl_zram_status_val)
        zram_status_row.addStretch()
        L.addLayout(zram_status_row)

        zram_cfg_row = QHBoxLayout()
        self.lbl_zram_size = QLabel(self.t("zram_size_lbl"))
        self.lbl_zram_size.setObjectName("SectionLabel")
        zram_cfg_row.addWidget(self.lbl_zram_size)

        self.zram_size_spin = QSpinBox()
        self.zram_size_spin.setObjectName("SourceEdit")
        self.zram_size_spin.setRange(1, 128)
        default_zram = max(4, _get_ram_gb() // 2)
        self.zram_size_spin.setValue(default_zram)
        self.zram_size_spin.setSuffix(" GB")
        self.zram_size_spin.setFixedHeight(34)
        zram_cfg_row.addWidget(self.zram_size_spin)

        self.lbl_zram_algo = QLabel(self.t("zram_algo_lbl"))
        self.lbl_zram_algo.setObjectName("SectionLabel")
        zram_cfg_row.addWidget(self.lbl_zram_algo)

        self.zram_algo_combo = QComboBox()
        self.zram_algo_combo.addItem("lzo-rle")
        self.zram_algo_combo.addItem("zstd")
        self.zram_algo_combo.addItem("lz4")
        self.zram_algo_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        zram_cfg_row.addWidget(self.zram_algo_combo)
        zram_cfg_row.addStretch()
        L.addLayout(zram_cfg_row)

        zram_btn_row = QHBoxLayout()
        self.zram_enable_btn = QPushButton(self.t("zram_enable"))
        self.zram_enable_btn.setObjectName("BrowseBtn")
        self.zram_enable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zram_enable_btn.clicked.connect(self._enable_zram)
        self.zram_disable_btn = QPushButton(self.t("zram_disable"))
        self.zram_disable_btn.setObjectName("DangerBtn")
        self.zram_disable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zram_disable_btn.clicked.connect(self._disable_zram)
        self.zram_disable_btn.setEnabled(False)
        zram_btn_row.addWidget(self.zram_enable_btn)
        zram_btn_row.addWidget(self.zram_disable_btn)
        L.addLayout(zram_btn_row)
        L.addWidget(self._make_divider())

        # ── Memory Pressure & OOM Killer ──────────────────────────────────────
        self.lbl_oom_section = QLabel(self.t("oom_section"))
        self.lbl_oom_section.setObjectName("SectionLabel")
        L.addWidget(self.lbl_oom_section)

        self.lbl_oom_hint = QLabel(self.t("oom_hint"))
        self.lbl_oom_hint.setObjectName("HintLabel")
        self.lbl_oom_hint.setWordWrap(True)
        L.addWidget(self.lbl_oom_hint)

        overcommit_row = QHBoxLayout()
        self.lbl_overcommit = QLabel(self.t("oom_overcommit"))
        self.lbl_overcommit.setObjectName("SectionLabel")
        overcommit_row.addWidget(self.lbl_overcommit)
        self.overcommit_combo = QComboBox()
        self.overcommit_combo.addItem(self.t("oom_mode_0"))
        self.overcommit_combo.addItem(self.t("oom_mode_1"))
        self.overcommit_combo.addItem(self.t("oom_mode_2"))
        self.overcommit_combo.setMinimumWidth(280)
        self.overcommit_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        overcommit_row.addWidget(self.overcommit_combo)
        overcommit_row.addStretch()
        L.addLayout(overcommit_row)

        # Fix transparent dropdown: style view() directly so global
        # "QWidget { background: transparent }" in style.qss doesn't win.
        _dv = ("background-color: @base@; color: @text@; "
               "selection-background-color: @surface0@; selection-color: @text@; "
               "border: 1px solid @surface1@;")
        kit_qt.style(self.zram_algo_combo.view(), _dv)
        kit_qt.style(self.overcommit_combo.view(), _dv)

        self.oomd_cb = QCheckBox(self.t("oom_oomd_cb"))
        self.oomd_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.oomd_cb.setObjectName("SwapCheckBox")
        L.addWidget(self.oomd_cb)

        self.panic_oom_cb = QCheckBox(self.t("oom_panic_cb"))
        self.panic_oom_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.panic_oom_cb.setObjectName("SwapCheckBox")
        L.addWidget(self.panic_oom_cb)

        self.apply_oom_btn = QPushButton(self.t("oom_apply"))
        self.apply_oom_btn.setObjectName("BrowseBtn")
        self.apply_oom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_oom_btn.clicked.connect(self._apply_oom_settings)
        L.addWidget(self.apply_oom_btn)
        L.addWidget(self._make_divider())

        # ── Windows-like Preset ───────────────────────────────────────────────
        self.lbl_win_section = QLabel(self.t("win_section"))
        self.lbl_win_section.setObjectName("SectionLabel")
        L.addWidget(self.lbl_win_section)

        self.lbl_win_hint = QLabel(self.t("win_hint"))
        self.lbl_win_hint.setObjectName("HintLabel")
        self.lbl_win_hint.setWordWrap(True)
        L.addWidget(self.lbl_win_hint)

        self.win_btn = QPushButton(self.t("win_btn"))
        self.win_btn.setObjectName("WindowsBtn")
        self.win_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.win_btn.clicked.connect(self._apply_windows_preset)
        L.addWidget(self.win_btn)

        L.addStretch()

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("ProgressFrame")
        self.progress_frame.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_frame)
        prog_layout.setContentsMargins(0, 10, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        prog_layout.addWidget(self.progress_bar)
        self.prog_status_lbl = QLabel(self.t("status_app"))
        self.prog_status_lbl.setObjectName("StatusLabel")
        self.prog_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog_layout.addWidget(self.prog_status_lbl)
        L.addWidget(self.progress_frame)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self):
        # Swap files
        try:
            result = subprocess.run(["swapon", "--show=NAME,SIZE,TYPE"], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) <= 1:
                self.info_lbl.setText(self.t("no_swap"))
            else:
                formatted = []
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        formatted.append(f"• {parts[0]}  —  {parts[1]}")
                self.info_lbl.setText("\n".join(formatted))
        except Exception:
            self.info_lbl.setText(self.t("no_swap"))

        # Swappiness
        try:
            with open("/proc/sys/vm/swappiness") as f:
                val = int(f.read().strip())
                self.swapp_slider.setValue(val)
                self.swapp_val_lbl.setText(str(val))
        except Exception:
            pass

        # zram status
        try:
            r = subprocess.run(["swapon", "--show=NAME,SIZE,TYPE"], capture_output=True, text=True)
            zram_line = next((l for l in r.stdout.splitlines() if "/dev/zram" in l), None)
            if zram_line:
                parts = zram_line.split()
                size_info = parts[1] if len(parts) > 1 else "?"
                self.lbl_zram_status_val.setText(self.t("zram_active").format(size_info))
                self.zram_enable_btn.setEnabled(False)
                self.zram_disable_btn.setEnabled(True)
            else:
                self.lbl_zram_status_val.setText(self.t("zram_inactive"))
                self.zram_enable_btn.setEnabled(True)
                self.zram_disable_btn.setEnabled(False)
        except Exception:
            self.lbl_zram_status_val.setText(self.t("zram_inactive"))

        # Overcommit policy
        try:
            with open("/proc/sys/vm/overcommit_memory") as f:
                self.overcommit_combo.setCurrentIndex(max(0, min(2, int(f.read().strip()))))
        except Exception:
            pass

        # systemd-oomd state
        try:
            r = subprocess.run(["systemctl", "is-enabled", "systemd-oomd"], capture_output=True, text=True)
            self.oomd_cb.setChecked(r.stdout.strip() not in ("enabled", "static", "preset"))
        except Exception:
            self.oomd_cb.setChecked(False)

        # panic_on_oom (checked = prevent panic = value is 0)
        # Parameter may not exist on all kernel builds
        _panic_path = "/proc/sys/kernel/panic_on_oom"
        if os.path.exists(_panic_path):
            try:
                with open(_panic_path) as f:
                    self.panic_oom_cb.setChecked(int(f.read().strip()) == 0)
                self.panic_oom_cb.setEnabled(True)
            except Exception:
                self.panic_oom_cb.setChecked(True)
                self.panic_oom_cb.setEnabled(True)
        else:
            self.panic_oom_cb.setChecked(False)
            self.panic_oom_cb.setEnabled(False)
            self.panic_oom_cb.setText(self.t("oom_panic_cb") + " (n/a)")

    # ── Language refresh ──────────────────────────────────────────────────────

    def _refresh_ui(self):
        self.setWindowTitle(self.t("title"))
        self.app_title.setText(self.t("title"))
        self.lbl_current.setText(self.t("current_swap"))
        self.lbl_path.setText(self.t("path"))
        self.lbl_size.setText(self.t("size"))
        self.lbl_swappiness.setText(self.t("swappiness"))
        self.fstab_cb.setText(self.t("fstab_chk"))
        self.apply_btn.setText(self.t("btn_apply"))
        self.apply_swapp_btn.setText(self.t("btn_swapp"))
        self.disable_btn.setText(self.t("btn_disable"))
        self.delete_btn.setText(self.t("btn_delete"))
        self.prog_status_lbl.setText(self.t("status_app"))
        # zram
        self.lbl_zram_section.setText(self.t("zram_section"))
        self.lbl_zram_hint.setText(self.t("zram_hint"))
        self.lbl_zram_status_key.setText(self.t("zram_status"))
        self.lbl_zram_size.setText(self.t("zram_size_lbl"))
        self.lbl_zram_algo.setText(self.t("zram_algo_lbl"))
        self.zram_enable_btn.setText(self.t("zram_enable"))
        self.zram_disable_btn.setText(self.t("zram_disable"))
        # OOM
        self.lbl_oom_section.setText(self.t("oom_section"))
        self.lbl_oom_hint.setText(self.t("oom_hint"))
        self.lbl_overcommit.setText(self.t("oom_overcommit"))
        cur = self.overcommit_combo.currentIndex()
        self.overcommit_combo.setItemText(0, self.t("oom_mode_0"))
        self.overcommit_combo.setItemText(1, self.t("oom_mode_1"))
        self.overcommit_combo.setItemText(2, self.t("oom_mode_2"))
        self.overcommit_combo.setCurrentIndex(cur)
        self.oomd_cb.setText(self.t("oom_oomd_cb"))
        self.panic_oom_cb.setText(self.t("oom_panic_cb"))
        self.apply_oom_btn.setText(self.t("oom_apply"))
        # Windows preset
        self.lbl_win_section.setText(self.t("win_section"))
        self.lbl_win_hint.setText(self.t("win_hint"))
        self.win_btn.setText(self.t("win_btn"))
        self._load_data()

    # ── Backend plumbing ──────────────────────────────────────────────────────

    def _all_interactive(self):
        return (
            self.apply_btn, self.disable_btn, self.delete_btn,
            self.path_input, self.size_spin, self.fstab_cb,
            self.refresh_btn, self.apply_swapp_btn, self.swapp_slider,
            self.zram_enable_btn, self.zram_disable_btn, self.zram_size_spin, self.zram_algo_combo,
            self.overcommit_combo, self.oomd_cb, self.panic_oom_cb, self.apply_oom_btn,
            self.win_btn,
        )

    def _run_backend(self, args):
        for w in self._all_interactive():
            w.setEnabled(False)
        self.progress_frame.setVisible(True)
        self.worker = SwapWorker(args)
        self.worker.finished.connect(self._on_worker_done)
        self.worker.start()

    def _on_worker_done(self, success, message):
        for w in self._all_interactive():
            w.setEnabled(True)
        self.progress_frame.setVisible(False)
        if success:
            QMessageBox.information(self, "Success", self.t("success"))
        else:
            # Only show "failed to get root" prefix for actual privilege errors
            if not message or "elevation" in message.lower() or message == "No elevation tool found.":
                text = f"{self.t('err_elevate')}\n{message}"
            else:
                text = message
            QMessageBox.critical(self, "Error", text)
        self._load_data()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _apply_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        self._run_backend(["--create", path, str(self.size_spin.value()),
                           "yes" if self.fstab_cb.isChecked() else "no"])

    def _disable_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        self._run_backend(["--disable", path])

    def _delete_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        if QMessageBox.question(self, "Confirm Delete", f"Delete {path} completely?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._run_backend(["--delete", path])

    def _apply_swappiness(self):
        self._run_backend(["--swappiness", str(self.swapp_slider.value())])

    def _enable_zram(self):
        self._run_backend([
            "--zram-enable", str(self.zram_size_spin.value()),
            self.zram_algo_combo.currentText(),
        ])

    def _disable_zram(self):
        self._run_backend(["--zram-disable"])

    def _apply_oom_settings(self):
        self._run_backend([
            "--overcommit", str(self.overcommit_combo.currentIndex()),
            "--oomd",       "disable" if self.oomd_cb.isChecked() else "enable",
            "--panic-on-oom", "0" if self.panic_oom_cb.isChecked() else "1",
        ])

    def _apply_windows_preset(self):
        zram_gb = max(4, _get_ram_gb() // 2)
        self._run_backend([
            "--zram-enable", str(zram_gb), "lzo-rle",
            "--overcommit",    "1",
            "--oomd",          "disable",
            "--swappiness",    "80",
            "--panic-on-oom",  "0",
        ])


def main():
    generate_assets()
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    app.setDesktopFileName("equestria-os-swap-manager")
    win = SwapManagerApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
