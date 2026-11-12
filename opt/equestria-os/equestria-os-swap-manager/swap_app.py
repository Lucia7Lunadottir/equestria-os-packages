import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QMessageBox, QProgressBar, QComboBox,
    QScrollArea, QTabBar, QButtonGroup, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import privilege
import health
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import live_i18n
import panels

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
    """
    Window = header (title, Simple/Professional switch, language) + pages of
    cards from panels.py + the configuration files card, shown on demand.

    Simple mode shows only the Overview page (state, problems with Fix
    buttons, one-click preset). Professional mode adds the Swap and Memory
    pages with every setting. The choice is remembered.
    """

    PAGES = (
        # (tab translation key, card classes)
        ("tab_overview", (panels.StatusCard, panels.HealthCard, panels.PresetCard)),
        ("tab_swap", (panels.ZramCard, panels.SwappinessCard, panels.SwapFileCard)),
        ("tab_memory", (panels.OomCard, panels.TuningCard)),
    )

    def __init__(self):
        super().__init__()
        self.current_lang = CATALOG.lang or "en"
        self.config = kit_qt.JsonConfig("equestria-os-swap-manager", {"pro_mode": False})
        self.worker = None

        self._setup_ui()
        self._apply_mode()
        self._load_data()

    def t(self, key):
        return str(CATALOG.tr(key))

    def _change_lang(self, lang):
        self.current_lang = CATALOG.set_language(lang) or lang  # ещё и сохраняет выбор
        idx = self.lang_combo.findData(lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self._refresh_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle(self.t("title"))
        self.resize(860, 760)
        self.setMinimumWidth(760)  # Settings resets it to 0 when embedding

        qss_path = os.path.join(ASSETS_DIR, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, encoding="utf-8") as f:
                qss = (f.read().replace("{{CHECKMARK_SVG_PATH}}", CHECKMARK_SVG)
                       .replace("{{ASSETS_DIR}}", ASSETS_DIR))
            kit_qt.style(self, qss)

        central = QWidget()
        central.setObjectName("ContentPage")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scroll area so content is always accessible
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # as needed, not off: in a narrow Settings window rows would be cut off
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("ContentPage")
        scroll.setWidget(content)
        L = QVBoxLayout(content)
        L.setContentsMargins(40, 28, 40, 28)
        L.setSpacing(12)

        L.addLayout(self._build_header())

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        prog = QHBoxLayout(self.progress_frame)
        prog.setContentsMargins(0, 0, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.prog_status_lbl = QLabel()
        self.prog_status_lbl.setObjectName("FieldHint")
        prog.addWidget(self.prog_status_lbl)
        prog.addWidget(self.progress_bar, 1)
        L.addWidget(self.progress_frame)

        # ── Pages: a tab bar over plain widgets, so a hidden page takes no space
        self.tab_bar = QTabBar()
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        L.addWidget(self.tab_bar)
        self.cards = []
        self.pages = []
        for key, card_classes in self.PAGES:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(12)
            for cls in card_classes:
                card = (cls(self.t, self._run_backend, self._load_data)
                        if cls is panels.StatusCard else cls(self.t, self._run_backend))
                lay.addWidget(card)
                self.cards.append(card)
            self.tab_bar.addTab("")
            self.pages.append(page)
            L.addWidget(page)
        self.tab_bar.currentChanged.connect(self._show_page)

        # ── Configuration files, on demand ────────────────────────────────────
        self.files_btn = QPushButton()
        self.files_btn.setObjectName("OpenAppBtn")
        self.files_btn.setCheckable(True)
        self.files_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.files_btn.toggled.connect(self._toggle_files)
        files_row = QHBoxLayout()
        files_row.addWidget(self.files_btn)
        files_row.addStretch()
        L.addLayout(files_row)
        self.files_card = panels.ConfigFilesCard(self.t, self._run_backend)
        self.files_card.setVisible(False)
        self.cards.append(self.files_card)
        L.addWidget(self.files_card)

        L.addStretch()
        self._retranslate()

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(4)
        self.app_title = QLabel()
        self.app_title.setObjectName("ModTitle")
        self.app_desc = QLabel()
        # own name, not Settings' #ModDesc: that one has max-width: 480px
        self.app_desc.setObjectName("PageDesc")
        self.app_desc.setWordWrap(True)
        text.addWidget(self.app_title)
        text.addWidget(self.app_desc)
        header.addLayout(text, 1)

        # Simple / Professional — two halves of one switch
        self.mode_group = QButtonGroup(self)
        self.mode_simple = QPushButton()
        self.mode_pro = QPushButton()
        for i, (btn, name) in enumerate(((self.mode_simple, "ModeLeft"), (self.mode_pro, "ModeRight"))):
            btn.setObjectName(name)
            # Fixed: in Settings the page description has a max-width, and
            # Minimum-policy buttons would take all the spare width
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.mode_group.addButton(btn, i)
        self.mode_group.idClicked.connect(self._on_mode_clicked)
        switch = QHBoxLayout()
        switch.setSpacing(0)
        switch.addWidget(self.mode_simple)
        switch.addWidget(self.mode_pro)
        header.addLayout(switch)

        # Компактный выпадающий список языков (в Настройках его прячут)
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
        header.addWidget(self.lang_combo, 0, Qt.AlignmentFlag.AlignTop)
        return header

    # ── Mode / pages ──────────────────────────────────────────────────────────

    @property
    def pro_mode(self):
        return bool(self.config.data.get("pro_mode"))

    def _on_mode_clicked(self, mode_id):
        self.config.data["pro_mode"] = mode_id == 1
        self.config.save()
        self._apply_mode()

    def _apply_mode(self):
        pro = self.pro_mode
        (self.mode_pro if pro else self.mode_simple).setChecked(True)
        self.tab_bar.setVisible(pro)
        if not pro:
            self.tab_bar.setCurrentIndex(0)
        for card in self.cards:
            card.set_pro(pro)
        self._show_page(self.tab_bar.currentIndex())

    def _show_page(self, index):
        for i, page in enumerate(self.pages):
            page.setVisible(i == index)

    def _toggle_files(self, shown):
        self.files_card.setVisible(shown)
        self.files_btn.setText(self.t("files_toggle_hide" if shown else "files_toggle_show"))

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load_data(self):
        state = health.MemoryState.from_system()
        for card in self.cards:
            card.load(state)

    def _retranslate(self):
        self.setWindowTitle(self.t("title"))
        self.app_title.setText(self.t("title"))
        self.app_desc.setText(self.t("app_desc"))
        self.mode_simple.setText(self.t("mode_simple"))
        self.mode_pro.setText(self.t("mode_pro"))
        for i, (key, _) in enumerate(self.PAGES):
            self.tab_bar.setTabText(i, self.t(key))
        self.files_btn.setText(self.t("files_toggle_hide" if self.files_btn.isChecked()
                                      else "files_toggle_show"))
        self.prog_status_lbl.setText(self.t("status_app"))
        for card in self.cards:
            card.retranslate()

    def _refresh_ui(self):
        self._retranslate()
        self._load_data()

    # ── Backend plumbing ──────────────────────────────────────────────────────

    def _all_interactive(self):
        return (
            self.mode_simple, self.mode_pro, self.tab_bar, self.files_btn,
            *(w for card in self.cards for w in card.interactive_widgets()),
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
        # _load_data() below re-disables what doesn't apply right now
        self.progress_frame.setVisible(False)
        if success:
            QMessageBox.information(self, self.t("title"), self.t("success"))
        else:
            # Only show "failed to get root" prefix for actual privilege errors
            if not message or "elevation" in message.lower() or message == "No elevation tool found.":
                text = f"{self.t('err_elevate')}\n{message}"
            else:
                text = message
            QMessageBox.critical(self, self.t("title"), text)
        self._load_data()


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
