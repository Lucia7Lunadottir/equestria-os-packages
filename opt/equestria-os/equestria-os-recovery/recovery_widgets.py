"""
Общее для обоих окон: переводы, карточки в стиле страниц Настроек,
шапка окна и запуск root-команд (pkexec в системе, sudo в live-среде).
"""
import os
import shutil
import sys

from PyQt6.QtCore import QObject, QProcess, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников без установленного equestria-qt-kit
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import live_i18n

from recovery_paths import APP_DIR, APP_ID, is_live

CATALOG = live_i18n.Catalog(APP_ID, __file__)
CHECKMARK_SVG = os.path.join(APP_DIR, "check_mark.svg")


def t(key, *args) -> str:
    text = str(CATALOG.tr(key))
    if args:
        try:
            return text.format(*args)
        except (IndexError, KeyError, ValueError):
            return text
    return text


def error_text(stderr: str) -> str:
    """«error <ключ> [подробности]» от бэкенда → понятный текст."""
    for line in reversed(stderr.strip().splitlines()):
        if line.startswith("error "):
            parts = line.split(" ", 2)
            key = parts[1] if len(parts) > 1 else ""
            detail = parts[2] if len(parts) > 2 else ""
            text = t(key) if key.startswith("error.") else line
            return f"{text}\n{detail}".strip() if detail and text != line else text
    return stderr.strip() or t("error.unknown")


_DECIMAL_COMMA = ("ru", "uk", "de", "fr", "es", "pt", "pl")


def number(value: float, digits: int = 1) -> str:
    """Дробное число с разделителем языка окна: 5,5 по-русски, 5.5 по-английски."""
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if CATALOG.lang in _DECIMAL_COMMA else text


def human_size(n: int, binary: bool = False) -> str:
    """Файлы — в десятичных ГБ (как на SourceForge и в файловом менеджере),
    память — в двоичных (как её называют: 16 ГБ, 32 ГБ)."""
    return t("size.gib", number(n / (1024 ** 3 if binary else 1e9)))


# ── виджеты ──────────────────────────────────────────────────────────────────

def label(text="", name="FieldLabel", wrap=True):
    lbl = QLabel(text)
    lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def button(text, slot, name="ActionBtn"):
    btn = QPushButton(text)
    btn.setObjectName(name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    btn.clicked.connect(slot)
    return btn


def row(*items):
    lay = QHBoxLayout()
    lay.setSpacing(8)
    for item in items:
        lay.addWidget(item)
    lay.addStretch()
    return lay


class Card(QFrame):
    """Одна секция #InlineCard; заголовок + self.body."""

    def __init__(self, title_key=""):
        super().__init__()
        self.setObjectName("InlineCard")
        self.title_key = title_key
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 14, 18, 14)
        self.body.setSpacing(8)
        self.title = label(name="CardTitle")
        if title_key:
            self.body.addWidget(self.title)

    def retranslate(self):
        if self.title_key:
            self.title.setText(t(self.title_key))


class PageWindow(QMainWindow):
    """Окно = прокручиваемая страница с шапкой (заголовок, описание, язык).
    Подклассы заполняют self.content (QVBoxLayout) и реализуют retranslate()."""

    title_key = "app.title"
    desc_key = "app.desc"

    def __init__(self):
        super().__init__()
        self.resize(860, 720)
        self.setMinimumWidth(720)  # Настройки обнуляют при встраивании
        qss_path = os.path.join(APP_DIR, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, encoding="utf-8") as f:
                qss = (f.read().replace("{{CHECKMARK_SVG_PATH}}", CHECKMARK_SVG)
                       .replace("{{ASSETS_DIR}}", APP_DIR))
            kit_qt.style(self, qss)

        central = QWidget()
        central.setObjectName("ContentPage")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        page = QWidget()
        page.setObjectName("ContentPage")
        scroll.setWidget(page)
        self.content = QVBoxLayout(page)
        self.content.setContentsMargins(40, 28, 40, 28)
        self.content.setSpacing(12)

        header = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(4)
        self.app_title = label(name="ModTitle")
        self.app_desc = label(name="PageDesc")
        text.addWidget(self.app_title)
        text.addWidget(self.app_desc)
        header.addLayout(text, 1)
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        for code in CATALOG.languages:
            self.lang_combo.addItem(CATALOG.language_name(code), code)
        idx = self.lang_combo.findData(CATALOG.lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.activated.connect(lambda i: self._change_lang(self.lang_combo.itemData(i)))
        header.addWidget(self.lang_combo, 0, Qt.AlignmentFlag.AlignTop)
        self.content.addLayout(header)

    # Настройки вызывают при смене языка (EmbeddedAppModule, _LANG_METHOD_1ARG)
    def _change_lang(self, lang):
        CATALOG.set_language(lang)
        idx = self.lang_combo.findData(CATALOG.lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(t(self.title_key))
        self.app_title.setText(t(self.title_key))
        self.app_desc.setText(t(self.desc_key))


# ── root-команды ─────────────────────────────────────────────────────────────

def _tool(wrapper: str, script: str) -> list:
    """Установленный пакет — обёртка из /usr/bin (её имя видно в окне пароля pkexec);
    запуск из исходников — python + скрипт рядом."""
    if APP_DIR.startswith("/opt/") and shutil.which(wrapper):
        return [shutil.which(wrapper)]
    return [sys.executable, os.path.join(APP_DIR, script)]


def backend_cmd(*args) -> list:
    return _elevator() + _tool("equestria-recovery-backend", "recovery_backend.py") + list(args)


def rescue_cmd(*args) -> list:
    return _elevator() + _tool("equestria-recovery-rescue", "recovery_rescue.py") + list(args)


def _elevator() -> list:
    if os.geteuid() == 0:
        return []
    if is_live() and shutil.which("sudo"):
        return ["sudo", "-n"]          # у liveuser sudo без пароля
    return [shutil.which("pkexec") or "pkexec"]


class PrivilegedTask(QObject):
    """Root-команда с построчным выводом. line(str) — каждая строка stdout,
    done(код, весь stdout, весь stderr) — по завершении."""

    line = pyqtSignal(str)
    done = pyqtSignal(int, str, str)

    def __init__(self, cmd: list, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.proc = QProcess(self)
        self._out, self._err, self._buf = [], [], ""
        self.proc.readyReadStandardOutput.connect(self._read_out)
        self.proc.readyReadStandardError.connect(self._read_err)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._failed)

    def start(self):
        self.proc.start(self.cmd[0], self.cmd[1:])

    def _read_out(self):
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buf = self._buf.split("\n")
        for ln in lines:
            self._out.append(ln)
            self.line.emit(ln)

    def _read_err(self):
        text = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        self._err.append(text)

    def _finished(self, code, _status):
        self._read_out()
        if self._buf:
            self._out.append(self._buf)
            self.line.emit(self._buf)
            self._buf = ""
        self.done.emit(code, "\n".join(self._out), "".join(self._err))

    def _failed(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.done.emit(127, "", f"error error.elevate {self.cmd[0]}")


def json_result(stdout: str):
    """Последняя строка `json …` из вывода rescue-команды."""
    import json
    for ln in reversed(stdout.splitlines()):
        if ln.startswith("json "):
            try:
                return json.loads(ln[5:])
            except ValueError:
                return None
    return None
