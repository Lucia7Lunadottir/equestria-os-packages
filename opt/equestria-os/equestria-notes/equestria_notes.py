#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equestria Notes — заметки в Markdown с галочками (PyQt6).

• Заметки — обычные файлы .md / .txt. Главная папка: Документы/Заметки.
• Можно добавить сколько угодно своих папок (для разных тем) и отдельные файлы — они попадают в историю.
• Markdown: заголовки, **жирный**, *курсив*, ~~зачёркнутый~~, `код`, ссылки, картинки, цитаты, таблицы.
• Списки с галочками: «- [ ] дело». В просмотре галочки нажимаются мышью, в редакторе — Ctrl+Enter.
"""
from __future__ import annotations

import base64
import hashlib
import html as _html
import json
import os
import re
import shutil
import sys
from urllib.parse import unquote
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QFile, QStandardPaths, Qt, QTimer, QUrl
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QFont, QImage, QImageReader, QKeySequence,
                         QPalette, QShortcut, QSyntaxHighlighter, QTextBlockFormat, QTextCharFormat, QTextCursor,
                         QTextDocument, QTextFormat, QTextImageFormat, QTextListFormat)
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QInputDialog,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                             QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                             QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainter, QPen, QPolygonF
from equestria_kit.widgets import load_typed_config, small_btn
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-notes", __file__)

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-notes" / "settings.json"
EXTS = (".md", ".markdown", ".txt")
GLOBAL, FILES = "global", "@files"

# ════════════════════════════════════════════════════════════════════════════
#  ТЕМЫ / СТИЛЬ
# ════════════════════════════════════════════════════════════════════════════

# Темы общие для всех приложений Equestria OS: см. equestria_kit/themes.py.
# Свои темы — файлы ~/.config/equestria-os/themes/*.json.
KEYS = kit_themes.KEYS
THEMES = kit_themes.THEMES
DEFAULT_THEME = kit_themes.DEFAULT_THEME
THEME: dict = dict(THEMES[DEFAULT_THEME])

QSS = """
QMainWindow, QDialog, QMessageBox, QInputDialog { background: @base@; }
QWidget { color: @text@; font-size: 15px; }
QLabel { background: transparent; }
QLabel#hint { color: @subtext@; font-size: 13px; }
QLabel#h2 { color: @accent@; font-size: 14px; font-weight: 700; }
QLabel#out { font-size: 18px; font-weight: 700; }
QPushButton { background: @surface0@; border: none; border-radius: 10px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#primary { background: @accent@; color: @base@; }
QPushButton#primary:hover { background: @accent_hover@; }
QPushButton#primary:disabled { background: @surface1@; color: @surface2@; }
QPushButton#small { padding: 6px 12px; font-size: 13px; border-radius: 9px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 9px;
    padding: 7px 10px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QComboBox { background: @surface0@; border: none; border-radius: 9px; padding: 7px 12px; }
QComboBox:hover { background: @surface1@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: @mantle@; border: 1px solid @surface1@; outline: 0;
    selection-background-color: @surface1@; selection-color: @text@; padding: 4px; }
QPlainTextEdit, QTextBrowser, QTextEdit { background: @mantle@; border: none; border-radius: 12px; padding: 10px;
    selection-background-color: @accent@; selection-color: @base@; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { background: @surface0@; border-radius: 9px; padding: 7px 12px; margin: 2px 0; }
QListWidget::item:hover { background: @surface1@; }
QListWidget::item:selected { background: @surface2@; color: @text@; }
QSplitter::handle { background: transparent; width: 12px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @surface1@; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


# ════════════════════════════════════════════════════════════════════════════
#  MARKDOWN → HTML  (свой небольшой разборщик: так галочки можно нажимать)
# ════════════════════════════════════════════════════════════════════════════
TASK_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+\[([ xX])\]\s?(.*)$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def count_tasks(src: str):
    """(сделано, всего) — без учёта блоков кода."""
    done = total = 0
    fence = False
    for line in src.split("\n"):
        if FENCE_RE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        m = TASK_RE.match(line)
        if m:
            total += 1
            done += m.group(3) in "xX"
    return done, total


def flip_task(line: str) -> str:
    return re.sub(r"\[([ xX])\]", lambda m: "[ ]" if m.group(1) in "xX" else "[x]", line, count=1)


def inline(s: str, th: dict, img_size=None) -> str:
    stash: list = []

    def keep(h: str) -> str:
        stash.append(h)
        return f"\x00{len(stash) - 1}\x00"

    s = _html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", lambda m: keep(
        f'<span style="font-family:monospace; background-color:{th["surface1"]}; color:{th["green"]};">'
        f'&nbsp;{m.group(1)}&nbsp;</span>'), s)

    def image(m):
        src = m.group(2)
        w = ""
        if img_size:
            size = img_size(src)
            if size and size[0] > 560:
                w = ' width="560"'
        return keep(f'<img src="{src}"{w}>')
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: keep(f'<a href="{m.group(2)}">{m.group(1)}</a>'), s)
    s = re.sub(r"(?<![\w\"=>])(https?://[^\s<]+[^\s<.,;:!?)\]])",
               lambda m: keep(f'<a href="{m.group(1)}">{m.group(1)}</a>'), s)
    s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])", r"<b>\1</b>", s)
    s = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<s>\1</s>", s)
    s = re.sub(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])", r"<i>\1</i>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], s)


def css(th: dict) -> str:
    return (f"body {{ color:{th['text']}; }} "
            f"h1 {{ color:{th['accent']}; font-size:27px; }} h2 {{ color:{th['accent']}; font-size:22px; }} "
            f"h3 {{ color:{th['text']}; font-size:18px; }} h4, h5, h6 {{ color:{th['subtext']}; }} "
            f"a {{ color:{th['accent']}; }} p {{ margin-top:4px; margin-bottom:4px; }}")


def md_to_html(src: str, th: dict, hide_done: bool = False, img_size=None) -> str:
    lines = src.replace("\r\n", "\n").split("\n")
    n = len(lines)
    out: list = []
    para: list = []
    i = 0

    def flush() -> None:
        if para:
            out.append("<p>" + "<br>".join(inline(l, th, img_size) for l in para) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]
        fm = FENCE_RE.match(line)
        if fm:
            flush()
            fence = fm.group(1)
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith(fence):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f'<table width="100%" cellspacing="0" cellpadding="10"><tr><td bgcolor="{th["crust"]}">'
                       f'<pre style="color:{th["green"]};">{_html.escape(chr(10).join(code), quote=False)}</pre>'
                       f'</td></tr></table>')
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        m = HEAD_RE.match(line)
        if m:
            flush()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2), th, img_size)}</h{lvl}>")
            i += 1
            continue
        if HR_RE.match(line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith(">"):
            flush()
            q = []
            while i < n and lines[i].lstrip().startswith(">"):
                q.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f'<table width="100%" cellspacing="0" cellpadding="6"><tr><td width="4" bgcolor="{th["accent"]}">'
                       f'</td><td style="color:{th["subtext"]};"><i>'
                       + "<br>".join(inline(l, th, img_size) for l in q) + "</i></td></tr></table>")
            continue
        if "|" in line and i + 1 < n and "-" in lines[i + 1] and TABLE_SEP_RE.match(lines[i + 1]):
            flush()

            def cells(row: str) -> list:
                row = row.strip()
                row = row[1:] if row.startswith("|") else row
                row = row[:-1] if row.endswith("|") else row
                return [c.strip() for c in row.split("|")]
            head = cells(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]))
                i += 1
            t = f'<table border="1" cellspacing="0" cellpadding="6" width="100%"><tr>'
            t += "".join(f'<th bgcolor="{th["surface1"]}">{inline(c, th, img_size)}</th>' for c in head) + "</tr>"
            for r in rows:
                t += "<tr>" + "".join(f"<td>{inline(c, th, img_size)}</td>" for c in r) + "</tr>"
            out.append(t + "</table>")
            continue
        if LIST_RE.match(line):
            flush()
            rows = []
            stack: list = []
            while i < n and LIST_RE.match(lines[i]) and not HR_RE.match(lines[i]):
                tm = TASK_RE.match(lines[i])
                lm = LIST_RE.match(lines[i])
                indent = len(lm.group(1).expandtabs(4))
                while stack and indent < stack[-1]:
                    stack.pop()
                if not stack or indent > stack[-1]:
                    stack.append(indent)
                level = len(stack) - 1
                if tm:
                    done = tm.group(3) in "xX"
                    text = inline(tm.group(4), th, img_size)
                    if done and hide_done:
                        i += 1
                        continue
                    box = ("☑" if done else "☐")
                    color = th["green"] if done else th["accent"]
                    marker = (f'<a href="toggle:{i}" style="text-decoration:none; color:{color};">'
                              f'<span style="font-size:19px;">{box}</span></a>')
                    body = f'<span style="color:{th["subtext"]};"><s>{text}</s></span>' if done else text
                else:
                    bullet = lm.group(2)
                    marker = ["•", "◦", "▪"][min(level, 2)] if bullet in "-*+" else _html.escape(bullet)
                    marker = f'<span style="color:{th["accent"]};">{marker}</span>'
                    body = inline(lm.group(3), th, img_size)
                rows.append(f'<tr><td width="{level * 22 + 4}">&nbsp;</td>'
                            f'<td width="26" valign="top">{marker}</td><td>{body}</td></tr>')
                i += 1
            if rows:
                out.append('<table cellspacing="0" cellpadding="2" width="100%">' + "".join(rows) + "</table>")
            continue
        para.append(line)
        i += 1
    flush()
    return "<html><body>" + "\n".join(out) + "</body></html>"


# ════════════════════════════════════════════════════════════════════════════
#  РЕДАКТОР
# ════════════════════════════════════════════════════════════════════════════
def line_kind(t: str) -> str:
    if TASK_RE.match(t):
        return "task"
    if re.match(r"^\s*[-*+]\s+", t):
        return "ul"
    if re.match(r"^\s*\d+[.)]\s+", t):
        return "ol"
    if re.match(r"^\s*>\s?", t):
        return "quote"
    m = re.match(r"^(#{1,6})\s", t)
    return f"h{len(m.group(1))}" if m else "none"


def split_line(t: str):
    m = re.match(r"^(\s*)(?:[-*+]\s+\[[ xX]\]\s?|[-*+]\s+|\d+[.)]\s+|>\s?|#{1,6}\s+)?(.*)$", t)
    return m.group(1), m.group(2)


class MdHighlighter(QSyntaxHighlighter):
    RULES = (
        (re.compile(r"`[^`]+`"), dict(color="green", mono=True)),
        (re.compile(r"\*\*(?=\S).+?(?<=\S)\*\*"), dict(bold=True)),
        (re.compile(r"(?<![\w*])\*(?![\s*]).+?(?<![\s*])\*(?![\w*])"), dict(italic=True)),
        (re.compile(r"~~.+?~~"), dict(strike=True, color="subtext")),
        (re.compile(r"!?\[[^\]]*\]\([^)]*\)"), dict(color="accent", underline=True)),
    )

    @staticmethod
    def fmt(color=None, bold=False, italic=False, strike=False, mono=False, underline=False) -> QTextCharFormat:
        f = QTextCharFormat()
        if color:
            f.setForeground(QColor(THEME.get(color, color)))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        f.setFontItalic(italic)
        f.setFontStrikeOut(strike)
        f.setFontUnderline(underline)
        if mono:
            f.setFontFamilies(["monospace"])
        return f

    def highlightBlock(self, text: str) -> None:
        F = self.fmt
        in_code = self.previousBlockState() == 1
        if FENCE_RE.match(text):
            self.setFormat(0, len(text), F("subtext"))
            self.setCurrentBlockState(0 if in_code else 1)
            return
        if in_code:
            self.setFormat(0, len(text), F("green", mono=True))
            self.setCurrentBlockState(1)
            return
        self.setCurrentBlockState(0)
        if HEAD_RE.match(text):
            self.setFormat(0, len(text), F("accent", bold=True))
            return
        if text.lstrip().startswith(">"):
            self.setFormat(0, len(text), F("subtext", italic=True))
            return
        tm = TASK_RE.match(text)
        if tm:
            done = tm.group(3) in "xX"
            self.setFormat(tm.start(2), tm.end(3) + 1 - tm.start(2), F("green" if done else "yellow", bold=True))
            if done:
                self.setFormat(tm.start(4), len(text) - tm.start(4), F("subtext", strike=True))
        else:
            lm = LIST_RE.match(text)
            if lm:
                self.setFormat(lm.start(2), len(lm.group(2)), F("accent", bold=True))
        for rx, kw in self.RULES:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), F(**kw))


class NoteEdit(QPlainTextEdit):
    """Редактор: Enter продолжает список, Tab сдвигает пункты."""

    def _block_numbers(self) -> list:
        cur = self.textCursor()
        doc = self.document()
        a, b = cur.selectionStart(), cur.selectionEnd()
        first, last = doc.findBlock(a).blockNumber(), doc.findBlock(b).blockNumber()
        if b > a and doc.findBlock(b).position() == b and last > first:
            last -= 1
        return list(range(first, last + 1))

    def _set_block(self, num: int, text: str) -> None:
        c = QTextCursor(self.document().findBlockByNumber(num))
        c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        c.insertText(text)

    def _continue_list(self) -> bool:
        cur = self.textCursor()
        if cur.hasSelection():
            return False
        text = cur.block().text()
        if cur.positionInBlock() != len(text):
            return False
        tm, lm = TASK_RE.match(text), LIST_RE.match(text)
        if tm:
            empty, nxt = not tm.group(4).strip(), f"{tm.group(1)}{tm.group(2)} [ ] "
            if re.match(r"\d", tm.group(2)):
                nxt = f"{tm.group(1)}{int(re.match(r'\d+', tm.group(2)).group(0)) + 1}{tm.group(2)[-1]} [ ] "
        elif lm:
            empty = not lm.group(3).strip()
            mk = lm.group(2)
            if re.match(r"\d", mk):
                mk = f"{int(re.match(r'\d+', mk).group(0)) + 1}{mk[-1]}"
            nxt = f"{lm.group(1)}{mk} "
        else:
            return False
        cur.beginEditBlock()
        if empty:  # пустой пункт — выходим из списка
            cur.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
        else:
            cur.insertText("\n" + nxt)
        cur.endEditBlock()
        self.setTextCursor(cur)
        return True

    def _shift(self, delta: int) -> None:
        cur = self.textCursor()
        cur.beginEditBlock()
        for num in self._block_numbers():
            t = self.document().findBlockByNumber(num).text()
            if delta > 0:
                self._set_block(num, "  " * delta + t)
            else:
                strip = len(t) - len(t.lstrip(" "))
                self._set_block(num, t[min(strip, 2):])
        cur.endEditBlock()

    def keyPressEvent(self, e) -> None:
        k, mods = e.key(), e.modifiers()
        plain = not (mods & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier))
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and plain and self._continue_list():
            return
        if k == Qt.Key.Key_Tab and not (mods & Qt.KeyboardModifier.ControlModifier):
            cur = self.textCursor()
            if cur.hasSelection() or line_kind(cur.block().text()) in ("task", "ul", "ol"):
                self._shift(1)
            else:
                cur.insertText("    ")
            return
        if k == Qt.Key.Key_Backtab:
            self._shift(-1)
            return
        super().keyPressEvent(e)

    def apply_marker(self, kind: str) -> None:
        nums = self._block_numbers()
        doc = self.document()
        first_kind = line_kind(doc.findBlockByNumber(nums[0]).text())
        edit = QTextCursor(doc)
        edit.beginEditBlock()
        if kind == "h":
            level = (int(first_kind[1]) + 1) % 4 if first_kind.startswith("h") else 1
            for num in nums:
                _ind, content = split_line(doc.findBlockByNumber(num).text())
                self._set_block(num, ("#" * level + " " + content) if level else content)
        else:
            remove = first_kind == kind
            for count, num in enumerate(nums, 1):
                ind, content = split_line(doc.findBlockByNumber(num).text())
                pref = {"ul": "- ", "task": "- [ ] ", "quote": "> ", "ol": f"{count}. "}[kind]
                self._set_block(num, ind + content if remove else ind + pref + content)
        edit.endEditBlock()

    def wrap(self, marker: str) -> None:
        cur = self.textCursor()
        if cur.hasSelection():
            cur.insertText(marker + cur.selectedText() + marker)
        else:
            cur.insertText(marker + marker)
            cur.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(marker))
        self.setTextCursor(cur)

    def insert_link(self) -> None:
        cur = self.textCursor()
        label = cur.selectedText() if cur.hasSelection() else ""
        cur.insertText(f"[{label}](https://)")
        cur.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        cur.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 8)
        self.setTextCursor(cur)

    def toggle_task_here(self) -> None:
        block = self.textCursor().block()
        if TASK_RE.match(block.text()):
            self._set_block(block.blockNumber(), flip_task(block.text()))
        else:
            self.apply_marker("task")


# ════════════════════════════════════════════════════════════════════════════
#  ФАЙЛЫ
# ════════════════════════════════════════════════════════════════════════════
IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
BULLETS = (QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle, QTextListFormat.Style.ListSquare)
MK = QTextBlockFormat.MarkerType
FSA = QTextFormat.Property.FontSizeAdjustment.value


def _unique(d: str, name: str) -> str:
    stem, ext = os.path.splitext(name)
    p, n = os.path.join(d, name), 1
    while os.path.exists(p):
        n += 1
        p = os.path.join(d, f"{stem}-{n}{ext}")
    return p


def store_image(src: str, note_dir: str) -> str:
    d = os.path.join(note_dir, "assets")
    os.makedirs(d, exist_ok=True)
    name = re.sub(r"[^\w.-]", "_", os.path.basename(src))
    dst = os.path.join(d, name)
    if os.path.abspath(src) != os.path.abspath(dst):
        dst = _unique(d, name)
        shutil.copyfile(src, dst)
    return "assets/" + os.path.basename(dst)


REFDEF_RE = re.compile(r"^[ ]{0,3}\[([^\]\n]+)\]:[ \t]*<?([^\s>]+)>?[ \t]*$", re.M)
REFUSE_RE = re.compile(r"(!?)\[([^\]\n]*)\]\[([^\]\n]*)\]")


def save_data_uri(uri: str, note_dir: str) -> str:
    m = re.match(r"data:image/([\w+.-]+);base64,(.*)$", uri, re.S)
    if not m:
        return uri
    try:
        raw = base64.b64decode(m.group(2))
        ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(m.group(1), m.group(1))
        d = os.path.join(note_dir, "assets")
        os.makedirs(d, exist_ok=True)
        name = f"img-{hashlib.sha1(raw).hexdigest()[:10]}.{ext}"
        p = os.path.join(d, name)
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(raw)
        return "assets/" + name
    except (OSError, ValueError):
        return uri


def resolve_refs(text: str, note_dir: str) -> str:
    """![][image1] / [текст][ref] + определения внизу → обычные ![](url) / [текст](url)."""
    defs: dict = {}

    def grab(m):
        defs[m.group(1).strip().lower()] = m.group(2)
        return ""
    body = REFDEF_RE.sub(grab, text)
    if not defs:
        return text

    def use(m):
        key = (m.group(3) or m.group(2)).strip().lower()
        if key not in defs:
            return m.group(0)
        url = defs[key]
        if url.startswith("data:image/"):
            url = save_data_uri(url, note_dir)
        return f"{m.group(1)}[{m.group(2)}]({url})"
    return REFUSE_RE.sub(use, body).rstrip("\n") + "\n"


def store_qimage(img: QImage, note_dir: str) -> str:
    d = os.path.join(note_dir, "assets")
    os.makedirs(d, exist_ok=True)
    dst = _unique(d, f"img-{datetime.now():%Y%m%d-%H%M%S}.png")
    img.save(dst, "PNG")
    return "assets/" + os.path.basename(dst)


def draw_task_box(painter: QPainter, r: QRectF, checked: bool) -> None:
    """Отметка пункта «- [ ] / - [x]» как в Google Docs: скруглённый квадрат,
    у сделанного — заливка акцентом темы и галочка."""
    side = r.width()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    acc = QColor(THEME.get("accent", "#cba6f7"))
    if checked:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(acc)
    else:
        painter.setPen(QPen(QColor(THEME.get("subtext", "#a6adc8")), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(r.adjusted(0.75, 0.75, -0.75, -0.75), side * 0.22, side * 0.22)
    if checked:
        tick = QColor(kit_qt.derived_colors(THEME)["on_accent"]) if "base" in THEME else QColor("#ffffff")
        pen = QPen(tick, max(1.6, side * 0.13))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        x, y = r.left(), r.top()
        painter.drawPolyline(QPolygonF([QPointF(x + side * 0.24, y + side * 0.53), QPointF(x + side * 0.43, y + side * 0.72),
                                        QPointF(x + side * 0.77, y + side * 0.30)]))
    painter.restore()


class RichEdit(QTextEdit):
    """Редактор «как есть»: Markdown грузится в документ Qt и сохраняется обратно."""
    # Qt 6 при чтении Markdown выбрасывает картинки с пустым описанием «![](файл)».
    # Пока заметка открыта в визуальном режиме, у таких картинок служебное описание,
    # при сохранении оно убирается — файл остаётся байт в байт прежним.
    NOALT = "eq-noalt"

    def __init__(self):
        super().__init__()
        self.base_dir = ""
        self.fitting = False   # подгонка размера картинок — не правка текста
        self._fit_timer = QTimer(self, singleShot=True, interval=120)
        self._fit_timer.timeout.connect(self.relayout)
        self.setAcceptRichText(True)
        self.setTabStopDistance(32)
        self.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoBulletList)
        self.document().setDocumentMargin(0)   # поля задаёт relayout() — как у страницы в Google Docs

    # --- загрузка
    def set_markdown(self, text: str) -> None:
        doc = self.document()
        base = QUrl.fromLocalFile(self.base_dir.rstrip("/\\") + "/")
        self.setUpdatesEnabled(False)
        doc.setBaseUrl(base)
        md = re.sub(r"!\[\]\(", f"![{self.NOALT}](", resolve_refs(text, self.base_dir))
        self.setMarkdown(md)
        doc.setBaseUrl(base)
        self._restyle()
        self.relayout()
        doc.clearUndoRedoStacks()
        self.setUpdatesEnabled(True)

    def _restyle(self) -> None:
        doc, jobs = self.document(), []
        b = doc.begin()
        while b.isValid():
            lvl = b.blockFormat().headingLevel()
            it = b.begin()
            while not it.atEnd():
                fr = it.fragment()
                f = fr.charFormat()
                nf = None
                if f.isAnchor():
                    nf = QTextCharFormat()
                    nf.setForeground(QColor(THEME["accent"]))
                    nf.setFontUnderline(True)
                elif 0 < lvl <= 2:
                    nf = QTextCharFormat()
                    nf.setForeground(QColor(THEME["accent"]))
                if nf is not None:
                    jobs.append((fr.position(), fr.length(), nf))
                it += 1
            b = b.next()
        if jobs:
            c = QTextCursor(doc)
            c.beginEditBlock()
            for pos, ln, nf in jobs:
                c.setPosition(pos)
                c.setPosition(pos + ln, QTextCursor.MoveMode.KeepAnchor)
                c.mergeCharFormat(nf)
            c.endEditBlock()

    def loadResource(self, rtype, name):
        try:
            s = name.toString()
            if s.startswith("data:image/"):
                m = re.match(r"data:image/[\w+.-]+;base64,(.*)$", s, re.S)
                img = QImage.fromData(base64.b64decode(m.group(1))) if m else QImage()
                if not img.isNull():
                    return img
            elif name.scheme() in ("", "file"):
                p = name.toLocalFile() if name.scheme() == "file" else os.path.join(self.base_dir, unquote(s))
                if os.path.isfile(p):
                    img = QImage(p)
                    if not img.isNull():
                        return img
        except Exception:
            pass
        return super().loadResource(rtype, name)

    # --- картинки
    def markdown(self) -> str:
        """Markdown документа без служебных описаний картинок."""
        return self.toMarkdown().replace(f"![{self.NOALT}](", "![](")

    # --- картинки: по ширине текста, как в Okular (но не больше натурального размера)
    def _natural_size(self, name: str):
        if name.startswith("data:image/"):
            img = self.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl(name))
            return img.size() if isinstance(img, QImage) else None
        if "://" in name and not name.startswith("file://"):
            return None
        path = QUrl(name).toLocalFile() if name.startswith("file://") else os.path.join(self.base_dir, unquote(name))
        sz = QImageReader(path).size()
        return sz if sz.isValid() else None

    # --- вёрстка «как в Google Docs / Okular»: колонка по центру, поля, воздух между абзацами
    TEXT_WIDTH = 760          # максимальная ширина строки, px
    SIDE_MIN, TOP, BOTTOM = 28, 28, 48

    def _content_width(self) -> int:
        return max(160, min(self.TEXT_WIDTH, self.viewport().width() - 2 * self.SIDE_MIN))

    def _max_image_width(self) -> int:
        return self._content_width()

    def relayout(self) -> None:
        """Поля страницы под текущую ширину окна + интервалы абзацев + размер картинок.
        Только отображение: в Markdown не попадает и правкой не считается."""
        doc = self.document()
        side = max(self.SIDE_MIN, (self.viewport().width() - self._content_width()) // 2)
        self.fitting = True
        try:
            root = doc.rootFrame()
            ff = root.frameFormat()
            if (ff.leftMargin(), ff.rightMargin(), ff.topMargin()) != (side, side, self.TOP):
                ff.setLeftMargin(side)
                ff.setRightMargin(side)
                ff.setTopMargin(self.TOP)
                ff.setBottomMargin(self.BOTTOM)
                root.setFrameFormat(ff)
            self._space_blocks()
        finally:
            self.fitting = False
        self.fit_images()

    def _space_blocks(self) -> None:
        c = QTextCursor(self.document())
        b = self.document().begin()
        while b.isValid():
            bf = b.blockFormat()
            lvl = bf.headingLevel()
            if lvl:
                top, bottom = (22, 10) if lvl <= 2 else (16, 6)
            elif b.textList() is not None:
                top, bottom = 0, 4
            else:
                top, bottom = 0, 12
            # +6 px между строками (а не «150 %»: процент раздувал строки с картинками)
            want_lh = QTextBlockFormat.LineHeightTypes.LineDistanceHeight.value
            if (bf.topMargin(), bf.bottomMargin(), bf.lineHeightType(), bf.lineHeight()) != (top, bottom, want_lh, 6):
                nf = QTextBlockFormat()
                nf.setTopMargin(top)
                nf.setBottomMargin(bottom)
                nf.setLineHeight(6, want_lh)
                c.setPosition(b.position())
                c.mergeBlockFormat(nf)
            b = b.next()

    def fit_images(self) -> None:
        doc, maxw, jobs = self.document(), self._max_image_width(), []
        b = doc.begin()
        while b.isValid():
            it = b.begin()
            while not it.atEnd():
                fr = it.fragment()
                if fr.charFormat().isImageFormat():
                    imf = fr.charFormat().toImageFormat()
                    sz = self._natural_size(imf.name())
                    if sz and sz.width() > 0:
                        w = min(sz.width(), maxw)
                        h = sz.height() * w / sz.width()
                        if abs(imf.width() - w) > 0.5 or abs(imf.height() - h) > 0.5:
                            imf.setWidth(w)
                            imf.setHeight(h)
                            jobs.append((fr.position(), fr.length(), imf))
                it += 1
            b = b.next()
        if not jobs:
            return
        self.fitting = True
        try:
            c = QTextCursor(doc)
            for pos, ln, imf in jobs:
                c.setPosition(pos)
                c.setPosition(pos + ln, QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(imf)
        finally:
            self.fitting = False

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._fit_timer.start()   # поля и картинки — под новую ширину

    # --- отметки списка дел: Qt 6 рисует их сам, в обход стилей (квадрат с крестиком),
    # поэтому поверх его отметки рисуем свою — на том же месте, клики работают как прежде
    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        self._paint_task_marks()

    def _paint_task_marks(self) -> None:
        vp = self.viewport()
        dx, dy = -self.horizontalScrollBar().value(), -self.verticalScrollBar().value()
        bg = QColor(THEME.get("mantle", "#181825"))
        painter = None
        b = self.document().begin()
        while b.isValid():
            mk = b.blockFormat().marker()
            lay = b.layout()
            if mk in (MK.Checked, MK.Unchecked) and lay is not None and lay.lineCount():
                line = lay.lineAt(0)
                tx = lay.position().x() + line.x() + dx
                ty = lay.position().y() + line.y() + dy
                if ty > vp.height():
                    break
                if ty + line.height() >= 0:
                    painter = painter or QPainter(vp)
                    size = max(10.0, round(line.ascent() * 0.82))
                    painter.fillRect(QRectF(tx - size * 1.9, ty, size * 1.9 - 1, line.height()), bg)
                    draw_task_box(painter, QRectF(tx - size * 1.3, ty + line.ascent() - size, size, size),
                                  mk == MK.Checked)
            b = b.next()
        if painter is not None:
            painter.end()

    def insert_image_rel(self, rel: str) -> None:
        fmt = QTextImageFormat()
        fmt.setName(rel)
        fmt.setProperty(QTextFormat.Property.ImageAltText, self.NOALT)   # иначе после сохранения картинка «пропадёт»
        self.textCursor().insertImage(fmt)
        self.fit_images()

    def insertFromMimeData(self, src) -> None:
        if self.base_dir:
            try:
                if src.hasUrls():
                    imgs = [u.toLocalFile() for u in src.urls()
                            if u.isLocalFile() and u.toLocalFile().lower().endswith(IMG_EXTS)]
                    if imgs:
                        for p in imgs:
                            self.insert_image_rel(store_image(p, self.base_dir))
                        return
                elif src.hasImage():
                    img = src.imageData()
                    if isinstance(img, QImage) and not img.isNull():
                        self.insert_image_rel(store_qimage(img, self.base_dir))
                        return
            except OSError:
                pass
        super().insertFromMimeData(src)

    # --- выбор блоков
    def _sel_blocks(self) -> list:
        c, doc = self.textCursor(), self.document()
        blk = doc.findBlock(c.selectionStart())
        end = doc.findBlock(c.selectionEnd()).blockNumber()
        out = []
        while blk.isValid() and blk.blockNumber() <= end:
            out.append(blk)
            blk = blk.next()
        return out

    def _set_bf(self, b, **kw) -> None:
        bf = b.blockFormat()
        if "marker" in kw:
            bf.setMarker(kw["marker"])
        if "indent" in kw:
            bf.setIndent(kw["indent"])
        QTextCursor(b).setBlockFormat(bf)

    # --- символьное форматирование
    def toggle_bold(self) -> None:
        f = QTextCharFormat()
        f.setFontWeight(QFont.Weight.Normal if self.fontWeight() > 500 else QFont.Weight.Bold)
        self.mergeCurrentCharFormat(f)

    def toggle_italic(self) -> None:
        f = QTextCharFormat()
        f.setFontItalic(not self.fontItalic())
        self.mergeCurrentCharFormat(f)

    def toggle_strike(self) -> None:
        f = QTextCharFormat()
        f.setFontStrikeOut(not self.currentCharFormat().fontStrikeOut())
        self.mergeCurrentCharFormat(f)

    def toggle_code(self) -> None:
        on = not self.currentCharFormat().fontFixedPitch()
        f = QTextCharFormat()
        f.setFontFixedPitch(on)
        f.setFontFamilies(["monospace"] if on else [self.document().defaultFont().family()])
        f.setForeground(QColor(THEME["green" if on else "text"]))
        self.mergeCurrentCharFormat(f)

    def insert_link(self) -> None:
        url, ok = QInputDialog.getText(self, tr("Ссылка"), tr("Адрес:"), text="https://")
        url = url.strip()
        if not ok or not url:
            return
        f = QTextCharFormat()
        f.setAnchor(True)
        f.setAnchorHref(url)
        f.setForeground(QColor(THEME["accent"]))
        f.setFontUnderline(True)
        c = self.textCursor()
        if c.hasSelection():
            c.mergeCharFormat(f)
        else:
            c.insertText(url, f)
        self.setTextCursor(c)

    # --- блоки
    def cycle_heading(self) -> None:
        lvl = (self.textCursor().blockFormat().headingLevel() + 1) % 4
        c = self.textCursor()
        c.beginEditBlock()
        for b in self._sel_blocks():
            bf = b.blockFormat()
            bf.setHeadingLevel(lvl)
            bc = QTextCursor(b)
            bc.setBlockFormat(bf)
            bc.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            bc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            f = QTextCharFormat()
            f.setFontWeight(QFont.Weight.Bold if lvl else QFont.Weight.Normal)
            f.setProperty(FSA, 4 - lvl if lvl else 0)
            f.setForeground(QColor(THEME["accent"] if 0 < lvl <= 2 else THEME["text"]))
            bc.mergeCharFormat(f)
        c.endEditBlock()

    def toggle_quote(self) -> bool:
        prop = getattr(QTextFormat.Property, "BlockQuoteLevel", None)
        if prop is None:
            return False
        blocks = self._sel_blocks()
        on = not blocks[0].blockFormat().intProperty(prop.value)
        for b in blocks:
            bf = b.blockFormat()
            bf.setProperty(prop.value, 1 if on else 0)
            bf.setLeftMargin(18 if on else 0)
            QTextCursor(b).setBlockFormat(bf)
        return True

    def _make_list(self, blocks: list, style) -> None:
        lst = QTextCursor(blocks[0]).createList(style)
        for b in blocks[1:]:
            lst.add(b)

    def set_list(self, style) -> None:
        blocks = self._sel_blocks()
        cur = blocks[0].textList()
        same = cur and (cur.format().style() == style or
                        (style in BULLETS and cur.format().style() in BULLETS))
        self.textCursor().beginEditBlock()
        if same:
            for b in blocks:
                if b.textList():
                    b.textList().remove(b)
                self._set_bf(b, indent=0, marker=MK.NoMarker)
        else:
            self._make_list(blocks, style)
        self.textCursor().endEditBlock()

    def toggle_task(self) -> None:
        blocks = self._sel_blocks()
        on = blocks[0].blockFormat().marker() == MK.NoMarker
        self.textCursor().beginEditBlock()
        if on and not all(b.textList() for b in blocks):
            self._make_list(blocks, BULLETS[0])
        for b in blocks:
            self._set_bf(b, marker=MK.Unchecked if on else MK.NoMarker)
        self.textCursor().endEditBlock()

    def _flip(self, b) -> None:
        self._set_bf(b, marker=MK.Unchecked if b.blockFormat().marker() == MK.Checked else MK.Checked)

    def toggle_check_here(self) -> None:
        b = self.textCursor().block()
        if b.blockFormat().marker() == MK.NoMarker:
            self.toggle_task()
        else:
            self._flip(b)

    def _indent(self, d: int) -> None:
        c = self.textCursor()
        c.beginEditBlock()
        for b in self._sel_blocks():
            lst = b.textList()
            if not lst:
                continue
            old = lst.format()
            ind = old.indent() + d
            if ind < 1 or ind > 8:
                continue
            mk = b.blockFormat().marker()
            lf = QTextListFormat()
            lf.setIndent(ind)
            lf.setStyle(BULLETS[(ind - 1) % 3] if old.style() in BULLETS else old.style())
            bc = QTextCursor(b)
            bc.createList(lf)
            prev = b.previous()
            pl = prev.textList() if prev.isValid() else None
            if pl and pl.format().indent() == ind:
                pl.add(b)
            self._set_bf(b, marker=mk)
        c.endEditBlock()

    def keyPressEvent(self, e) -> None:
        k, mods = e.key(), e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        c = self.textCursor()
        if k == Qt.Key.Key_Tab and not ctrl and c.currentList():
            self._indent(1)
            return
        if k == Qt.Key.Key_Backtab and c.currentList():
            self._indent(-1)
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not ctrl:
            b = c.block()
            if b.textList() and not b.text().strip() and not c.hasSelection():
                if b.textList().format().indent() > 1:
                    self._indent(-1)
                else:
                    b.textList().remove(b)
                    self._set_bf(b, indent=0, marker=MK.NoMarker)
                return
            super().keyPressEvent(e)
            nb = self.textCursor().block()
            if nb.blockFormat().marker() == MK.Checked:
                self._set_bf(nb, marker=MK.Unchecked)
            return
        super().keyPressEvent(e)

    # --- мышь: галочки и ссылки
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            b = self.cursorForPosition(pos).block()
            if b.blockFormat().marker() != MK.NoMarker:
                r = self.cursorRect(QTextCursor(b))
                if pos.x() < r.left() and r.top() - 2 <= pos.y() <= r.bottom() + 2:
                    self._flip(b)
                    return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            a = self.anchorAt(e.position().toPoint())
            if a:
                u = QUrl(a)
                if u.scheme() in ("http", "https", "mailto", "file"):
                    QDesktopServices.openUrl(u)
                else:
                    p = os.path.join(self.base_dir, unquote(a))
                    if os.path.isfile(p):
                        QDesktopServices.openUrl(QUrl.fromLocalFile(p))
                return
        super().mouseReleaseEvent(e)


def global_dir() -> Path:
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    base = Path(docs) if docs else Path.home() / "Documents"
    legacy = base / "Заметки"  # папка, созданная до локализации, — не терять заметки
    return legacy if legacy.exists() else base / tr("Заметки")


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().replace("\r\n", "\n")


def write_text(path: str, text: str) -> None:
    tmp = path + ".tmp~"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def note_title(path: str) -> str:
    name = os.path.basename(path)
    return name[:-3] if name.lower().endswith(".md") else name


def preview_of(text: str) -> str:
    for line in text.split("\n"):
        t = re.sub(r"^\s*(#{1,6}\s+|[-*+]\s+(\[[ xX]\]\s+)?|\d+[.)]\s+|>\s*)", "", line)
        t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t).strip()   # картинки в превью не показываем
        if t:
            return t[:70]
    return ""


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
EMPTY_HINT = tr("Выберите заметку слева или создайте новую.")


class NoteLibrary:
    """Заметки без интерфейса: источники (папка «Заметки», свои папки, история
    отдельных файлов), список заметок с кэшем и поиском, создание, переименование
    и удаление файлов. Окно (MainWindow) только показывает это и задаёт вопросы."""

    def __init__(self, cfg: dict, gdir):
        self.cfg, self.gdir = cfg, gdir
        self.cache: dict = {}

    # --- источники
    @property
    def source(self) -> str:
        return self.cfg["source"]

    @source.setter
    def source(self, value: str) -> None:
        self.cfg["source"] = value or GLOBAL

    def source_dir(self):
        """Папка текущего источника; None — для истории отдельных файлов."""
        s = self.source
        return str(self.gdir) if s == GLOBAL else (None if s == FILES else s)

    def source_entries(self) -> list:
        """[(подпись, id, подсказка)] для выпадающего списка источников."""
        names: dict = {}
        for p in self.cfg["folders"]:
            names.setdefault(os.path.basename(p.rstrip("/")) or p, []).append(p)
        out = [(tr("Заметки (Документы)"), GLOBAL, str(self.gdir))]
        for p in self.cfg["folders"]:
            base = os.path.basename(p.rstrip("/")) or p
            label = base if len(names[base]) == 1 else f"{base} ({os.path.basename(os.path.dirname(p.rstrip('/')))})"
            out.append(("⚠ " + label if not os.path.isdir(p) else label, p, p))
        out.append((tr("Отдельные файлы (история)"), FILES, None))
        return out

    def add_folder(self, d: str) -> None:
        d = os.path.normpath(d)
        if os.path.normpath(str(self.gdir)) == d:
            self.source = GLOBAL
        else:
            if d not in self.cfg["folders"]:
                self.cfg["folders"].append(d)
            self.source = d

    def remove_current_folder(self) -> None:
        p = self.source
        self.cfg["folders"] = [f for f in self.cfg["folders"] if f != p]
        self.source = GLOBAL

    def clear_files(self) -> None:
        self.cfg["files"] = []

    def remember_file(self, p: str) -> None:
        self.cfg["files"] = ([p] + [f for f in self.cfg["files"] if f != p])[:100]

    def forget_file(self, p: str) -> None:
        self.cfg["files"] = [f for f in self.cfg["files"] if f != p]

    # --- список заметок
    def info(self, path: str) -> dict:
        try:
            st = os.stat(path)
        except OSError:
            return {"path": path, "title": note_title(path), "missing": True, "mtime": 0, "tasks": (0, 0),
                    "preview": "", "text_l": ""}
        c = self.cache.get(path)
        if c and c[0] == st.st_mtime and c[1] == st.st_size:
            return c[2]
        text = ""
        if st.st_size <= 1_000_000:
            try:
                text = read_text(path)
            except OSError:
                pass
        info = {"path": path, "title": note_title(path), "missing": False, "mtime": st.st_mtime,
                "tasks": count_tasks(text), "preview": preview_of(text), "text_l": text[:200_000].lower()}
        self.cache[path] = (st.st_mtime, st.st_size, info)
        return info

    def notes(self, query: str = "") -> list:
        """Заметки текущего источника (папки — свежие сверху, история — по порядку)."""
        src = self.source
        paths: list = []
        if src == FILES:
            paths = list(self.cfg["files"])
        else:
            d = str(self.gdir) if src == GLOBAL else src
            try:
                for e in os.scandir(d):
                    if e.is_file() and not e.name.startswith(".") and e.name.lower().endswith(EXTS):
                        paths.append(e.path)
            except OSError:
                pass
        infos = [self.info(p) for p in paths]
        if src != FILES:
            infos.sort(key=lambda i: i["mtime"], reverse=True)
        q = query.strip().lower()
        if q:
            infos = [i for i in infos if q in i["title"].lower() or q in i["text_l"]]
        return infos

    # --- файлы
    def create_note(self) -> str:
        """Новая заметка в текущей папке (или в «Заметках»). Путь к файлу; OSError — не вышло."""
        d = self.source_dir()
        if d is None or not os.path.isdir(d):
            d = str(self.gdir)
            self.source = GLOBAL
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        base, n = tr("Новая заметка"), 1
        path = os.path.join(d, base + ".md")
        while os.path.exists(path):
            n += 1
            path = os.path.join(d, f"{base} {n}.md")
        write_text(path, tr("# Новая заметка\n\n"))
        return path

    @staticmethod
    def safe_name(name: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', "_", name).strip()

    def rename(self, path: str, new_stem: str) -> str:
        """Переименовать файл; FileExistsError — имя занято, OSError — ошибка ФС."""
        new = os.path.join(os.path.dirname(path), new_stem + os.path.splitext(path)[1])
        if os.path.exists(new):
            raise FileExistsError(new)
        os.rename(path, new)
        self.cfg["files"] = [new if f == path else f for f in self.cfg["files"]]
        if self.cfg.get("last") == path:
            self.cfg["last"] = new
        return new

    def delete(self, path: str) -> None:
        """В корзину, а если корзины нет — удалить (подтверждение спрашивает окно). OSError — не вышло."""
        res = QFile.moveToTrash(path)
        ok = res[0] if isinstance(res, tuple) else bool(res)
        if not ok:
            os.remove(path)
        self.forget_file(path)


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.gdir = global_dir()
        try:
            self.gdir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.cur_path = None
        self.cur_mtime = 0.0
        self.dirty = False
        self.loading = False
        self.mode = cfg["mode"]
        self.hide_done = False
        self.lib = NoteLibrary(cfg, self.gdir)
        self.save_timer = QTimer(self, singleShot=True, interval=1500)
        self.save_timer.timeout.connect(self.save_note)
        self.prev_timer = QTimer(self, singleShot=True, interval=500)
        self.prev_timer.timeout.connect(self._update_progress)
        self.cfg_timer = QTimer(self, singleShot=True, interval=400)
        self.cfg_timer.timeout.connect(self.save_cfg)
        self.say_timer = QTimer(self, singleShot=True, interval=4000)
        self.say_timer.timeout.connect(self._status_idle)
        self.setWindowTitle("Equestria Notes")
        self.setMinimumSize(980, 640)
        self.resize(1180, 760)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("Equestria Notes")
        title.setObjectName("h2")
        theme_btn = small_btn(tr("Тема"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        top.addWidget(theme_btn)
        root.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)

        # ---- левая колонка: источники и список заметок
        left = QVBoxLayout()
        left.setSpacing(8)
        self.new_btn = QPushButton(tr("Новая заметка"))
        self.new_btn.setObjectName("primary")
        self.new_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.new_btn.clicked.connect(self.new_note)
        left.addWidget(self.new_btn)
        srow = QHBoxLayout()
        self.src = QComboBox()
        self.src.setToolTip(tr("Где искать заметки"))
        self.src.currentIndexChanged.connect(self._src_changed)
        more = small_btn("⋯", tip=tr("Действия с этим источником"))
        more.clicked.connect(lambda: self._src_menu(more))
        srow.addWidget(self.src, 1)
        srow.addWidget(more)
        left.addLayout(srow)
        arow = QHBoxLayout()
        add_dir = small_btn(tr("＋ Папка"), tip=tr("Добавить свою папку с заметками"))
        add_dir.clicked.connect(self.add_folder)
        add_file = small_btn(tr("＋ Файл"), tip=tr("Открыть отдельные файлы — они попадут в историю"))
        add_file.clicked.connect(self.add_files)
        arow.addWidget(add_dir)
        arow.addWidget(add_file)
        arow.addStretch()
        left.addLayout(arow)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Поиск по названию и тексту…"))
        self.search.textChanged.connect(self.refresh_list)
        left.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._on_select)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        left.addWidget(self.list, 1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(330)
        body.addWidget(lw)

        # ---- правая колонка: заголовок, панель, редактор/просмотр
        right = QVBoxLayout()
        right.setSpacing(8)
        hrow = QHBoxLayout()
        self.d_title = QLabel(EMPTY_HINT)
        self.d_title.setObjectName("out")
        self.d_title.setWordWrap(True)
        hrow.addWidget(self.d_title, 1)
        self.mode_btns = {}
        for mode, label in (("visual", tr("Визуальный")), ("source", "Markdown")):
            b = small_btn(label, True, tr("Ctrl+E — переключить режим"))
            b.clicked.connect(lambda _=False, m=mode: self._set_mode(m))
            self.mode_btns[mode] = b
            hrow.addWidget(b)
        self.save_btn = small_btn(tr("Сохранить"), tip=tr("Сохранить (Ctrl+S)"))
        self.save_btn.clicked.connect(self.save_note)
        self.revert_btn = small_btn(tr("Откатить"), tip=tr("Отбросить правки и вернуть сохранённый файл"))
        self.revert_btn.clicked.connect(self.revert_note)
        hrow.addWidget(self.save_btn)
        hrow.addWidget(self.revert_btn)
        right.addLayout(hrow)
        frow = QHBoxLayout()
        frow.setSpacing(6)
        self.fmt_btns = []
        for label, tip, key in (
                ("B", tr("Жирный (Ctrl+B)"), "b"), ("I", tr("Курсив (Ctrl+I)"), "i"),
                ("S", tr("Зачёркнутый"), "s"), ("<>", tr("Код"), "c"),
                ("H", tr("Заголовок: нажимайте, чтобы менять уровень"), "h"),
                ("•", tr("Маркированный список (Tab — вложенный)"), "ul"),
                ("☑", tr("Список с галочками (Ctrl+Shift+L)"), "task"),
                ("1.", tr("Нумерованный список"), "ol"), ("❝", tr("Цитата"), "quote"),
                (tr("Ссылка"), tr("Ссылка (Ctrl+K; открыть — Ctrl+клик)"), "link"),
                ("🖼", tr("Вставить картинку (можно вставить из буфера или перетащить)"), "img")):
            b = small_btn(label, tip=tip)
            b.clicked.connect(lambda _=False, k=key: self._fmt(k))
            self.fmt_btns.append(b)
            frow.addWidget(b)
        frow.addStretch()
        self.progress = QLabel("")
        self.progress.setObjectName("hint")
        frow.addWidget(self.progress)
        right.addLayout(frow)

        self.editor = NoteEdit()  # режим «Markdown» (исходник)
        self.editor.setPlaceholderText(tr("Пишите здесь. «- [ ] дело» — пункт с галочкой."))
        self.editor.setTabStopDistance(32)
        self.editor.textChanged.connect(self._text_changed)
        self.hl = MdHighlighter(self.editor.document())
        self.rich = RichEdit()  # визуальный режим
        self.rich.textChanged.connect(self._text_changed)
        self.active = self.rich
        right.addWidget(self.editor, 1)
        right.addWidget(self.rich, 1)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        right.addWidget(self.status)
        body.addLayout(right, 1)

        # горячие клавиши
        def sc(seq, fn, widget=None):
            s = QShortcut(QKeySequence(seq), widget or self)
            if widget is not None:
                s.setContext(Qt.ShortcutContext.WidgetShortcut)
            s.activated.connect(fn)
        sc("Ctrl+N", self.new_note)
        sc("Ctrl+S", self.save_note)
        sc("Ctrl+F", lambda: self.search.setFocus())
        sc("Ctrl+E", self._cycle_mode)
        for w in (self.editor, self.rich):
            sc("Ctrl+B", lambda: self._fmt("b"), w)
            sc("Ctrl+I", lambda: self._fmt("i"), w)
            sc("Ctrl+K", lambda: self._fmt("link"), w)
            sc("Ctrl+Shift+L", lambda: self._fmt("task"), w)
            sc("Ctrl+Return", self._toggle_here, w)
            sc("Ctrl+Enter", self._toggle_here, w)

        self.timer = QTimer(self, interval=4000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._rebuild_sources()
        self._set_mode(self.mode, save=False)
        self._editor_enabled(False)
        self.refresh_list()
        last = cfg.get("last")
        if last and os.path.isfile(last) and self._select_in_list(last):
            self.open_note(last)

    # --- вспомогательное
    def _say(self, text: str) -> None:
        self.status.setText(text)
        self.say_timer.start()

    def _status_idle(self) -> None:
        self.status.setText(tr("● не сохранено…") if self.dirty else (tr("Сохранено ✓") if self.cur_path else ""))

    def _editor_enabled(self, on: bool) -> None:
        for ed in (self.editor, self.rich):
            ed.setReadOnly(not on)
        for b in self.fmt_btns:
            b.setEnabled(on)
        self.save_btn.setEnabled(False)
        self.revert_btn.setEnabled(False)
        if not on:
            self.d_title.setText(EMPTY_HINT)
            self.progress.setText("")
            self.status.setText("")
            for ed in (self.editor, self.rich):
                ed.blockSignals(True)
                ed.clear()
                ed.blockSignals(False)

    def _get_text(self) -> str:
        return self.rich.markdown() if self.active is self.rich else self.editor.toPlainText()

    def _put_text(self, text: str, path: str) -> None:
        self.rich.base_dir = os.path.dirname(path)
        if self.active is self.rich:
            self.rich.set_markdown(text)
        else:
            self.editor.setPlainText(text)

    def _fmt(self, k: str) -> None:
        ed = self.active
        if k == "img":
            self.add_image()
            return
        if ed is self.rich:
            L = QTextListFormat.Style
            if k == "quote" and not ed.toggle_quote():
                self._say(tr("Цитаты в визуальном режиме не поддерживает эта версия Qt — используйте режим Markdown."))
            acts = {"b": ed.toggle_bold, "i": ed.toggle_italic, "s": ed.toggle_strike, "c": ed.toggle_code,
                    "h": ed.cycle_heading, "ul": lambda: ed.set_list(L.ListDisc),
                    "task": ed.toggle_task, "ol": lambda: ed.set_list(L.ListDecimal),
                    "link": ed.insert_link}
        else:
            acts = {"b": lambda: ed.wrap("**"), "i": lambda: ed.wrap("*"), "s": lambda: ed.wrap("~~"),
                    "c": lambda: ed.wrap("`"), "h": lambda: ed.apply_marker("h"),
                    "ul": lambda: ed.apply_marker("ul"), "task": lambda: ed.apply_marker("task"),
                    "ol": lambda: ed.apply_marker("ol"), "quote": lambda: ed.apply_marker("quote"),
                    "link": ed.insert_link}
        if k in acts:
            acts[k]()
        ed.setFocus()

    def _toggle_here(self) -> None:
        if self.active is self.rich:
            self.rich.toggle_check_here()
        else:
            self.editor.toggle_task_here()

    def add_image(self) -> None:
        if not self.cur_path:
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Картинки"), str(Path.home()), tr("Изображения (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;Все файлы (*)"))
        d = os.path.dirname(self.cur_path)
        for p in files:
            try:
                rel = store_image(p, d)
            except OSError as e:
                self._say(tr("Не удалось скопировать картинку: {}", e.strerror or e))
                continue
            if self.active is self.rich:
                self.rich.insert_image_rel(rel)
            else:
                self.editor.insertPlainText(f"![]({rel})\n")
        self.active.setFocus()

    # --- источники
    def _src_id(self) -> str:
        return self.lib.source

    def _src_dir(self):
        return self.lib.source_dir()

    def _rebuild_sources(self) -> None:
        self.src.blockSignals(True)
        self.src.clear()
        for label, sid, tip in self.lib.source_entries():
            self.src.addItem(label, sid)
            if tip:
                self.src.setItemData(self.src.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        idx = self.src.findData(self._src_id())
        if idx < 0:
            self.lib.source = GLOBAL
            idx = 0
        self.src.setCurrentIndex(idx)
        self.src.blockSignals(False)

    def _src_changed(self, _i) -> None:
        if not self._leave_ok():
            self.src.blockSignals(True)
            self.src.setCurrentIndex(max(0, self.src.findData(self.cfg['source'])))
            self.src.blockSignals(False)
            return
        self.lib.source = self.src.currentData()
        self.cfg_timer.start()
        self.refresh_list()

    def _src_menu(self, btn: QPushButton) -> None:
        menu = QMenu(self)
        d = self._src_dir()
        if d:
            menu.addAction(tr("Открыть папку в файловом менеджере")).triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(d)))
        if self._src_id() not in (GLOBAL, FILES):
            menu.addAction(tr("Убрать папку из списка (файлы останутся)")).triggered.connect(self._remove_folder)
        if self._src_id() == FILES and self.lib.cfg["files"]:
            menu.addAction(tr("Очистить историю файлов")).triggered.connect(self._clear_files)
        if not menu.actions():
            return
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _remove_folder(self) -> None:
        self.lib.remove_current_folder()
        self._rebuild_sources()
        self.cfg_timer.start()
        self.refresh_list()

    def _clear_files(self) -> None:
        self.lib.clear_files()
        self.cfg_timer.start()
        self.refresh_list()

    def add_folder(self) -> None:
        start = self._src_dir() or str(self.gdir)
        d = QFileDialog.getExistingDirectory(self, tr("Папка с заметками"), start)
        if not d:
            return
        self.lib.add_folder(d)
        self._rebuild_sources()
        self.cfg_timer.start()
        self.refresh_list()

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Выберите файлы"), str(self.gdir),
            tr("Текст и Markdown (*.md *.markdown *.txt);;Все файлы (*)"))
        if not files:
            return
        if not self._leave_ok():
            return
        for p in reversed(files):
            self._remember_file(os.path.normpath(p))
        self.lib.source = FILES
        self._rebuild_sources()
        self.refresh_list()
        first = os.path.normpath(files[0])
        if self._select_in_list(first):
            self.open_note(first)

    def _remember_file(self, p: str) -> None:
        self.lib.remember_file(p)
        self.cfg_timer.start()

    # --- список заметок
    def refresh_list(self, *_) -> None:
        src = self._src_id()
        q = self.search.text().strip().lower()
        infos = self.lib.notes(q)
        sb = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        cur_item = None
        for i in infos:
            if i["missing"]:
                text = tr("⚠ {}\nфайл не найден · {}", i['title'], os.path.dirname(i['path']))
            else:
                done, total = i["tasks"]
                prog = f"☑ {done}/{total} · " if total else ""
                date = datetime.fromtimestamp(i["mtime"]).strftime("%d.%m.%Y %H:%M")
                text = f"{i['title']}\n{date} · {prog}{i['preview']}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, i["path"])
            it.setToolTip(i["path"])
            self.list.addItem(it)
            if i["path"] == self.cur_path:
                cur_item = it
        if not infos:
            msg = (tr("Ничего не найдено.") if q else
                   tr("История пуста — добавьте файлы кнопкой «＋ Файл».") if src == FILES else
                   tr("Здесь пока нет заметок. Нажмите «Новая заметка»."))
            it = QListWidgetItem(msg)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(it)
        if cur_item:
            self.list.setCurrentItem(cur_item)
        self.list.blockSignals(False)
        self.list.verticalScrollBar().setValue(sb)

    def _select_in_list(self, path: str) -> bool:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                self.list.blockSignals(True)
                self.list.setCurrentRow(i)
                self.list.blockSignals(False)
                self.list.scrollToItem(self.list.item(i))
                return True
        return False

    def _on_select(self) -> None:
        items = self.list.selectedItems()
        path = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        if path and path != self.cur_path:
            self.open_note(path)

    def _tick(self) -> None:
        self.refresh_list()
        if self.cur_path and not self.dirty:
            try:
                m = os.stat(self.cur_path).st_mtime
            except OSError:
                return
            if m != self.cur_mtime:  # файл изменили снаружи
                self.open_note(self.cur_path, keep_cursor=True)

    # --- открыть / сохранить
    def open_note(self, path: str, keep_cursor: bool = False) -> None:
        if path != self.cur_path and not self._leave_ok():
            if self.cur_path:
                self._select_in_list(self.cur_path)
            return
        try:
            text = read_text(path)
            mtime = os.stat(path).st_mtime
        except OSError as e:
            self._say(tr("Не удалось открыть: {}", e.strerror or e))
            return
        ed = self.active
        pos = ed.textCursor().position() if keep_cursor else 0
        sb = ed.verticalScrollBar().value() if keep_cursor else 0
        self.loading = True
        self._editor_enabled(True)
        self._put_text(text, path)
        self.loading = False
        cur = ed.textCursor()
        cur.setPosition(min(pos, max(0, ed.document().characterCount() - 1)))
        ed.setTextCursor(cur)
        ed.verticalScrollBar().setValue(sb)
        self.cur_path, self.cur_mtime, self.dirty = path, mtime, False
        self.cfg["last"] = path
        if self._src_id() == FILES:
            self._remember_file(path)
        self.cfg_timer.start()
        self.d_title.setText(note_title(path))
        self.setWindowTitle(f"{note_title(path)} — Equestria Notes")
        self._update_progress()
        self._status_idle()
        self._select_in_list(path)

    def _text_changed(self) -> None:
        if self.loading or not self.cur_path or self.rich.fitting:
            return
        self.dirty = True
        self.status.setText(tr("● не сохранено…"))
        self.save_btn.setEnabled(True)
        self.revert_btn.setEnabled(True)
        self.prev_timer.start()

    def _leave_ok(self) -> bool:
        if not (self.cur_path and self.dirty):
            return True
        box = QMessageBox(self)
        box.setWindowTitle(tr("Несохранённые изменения"))
        box.setText(tr("Сохранить изменения в «{}»?", note_title(self.cur_path)))
        save = box.addButton(tr("Сохранить"), QMessageBox.ButtonRole.AcceptRole)
        drop = box.addButton(tr("Не сохранять"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Отмена"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        b = box.clickedButton()
        if b is save:
            self.save_note()
            return not self.dirty
        if b is drop:
            self.dirty = False
            self.open_note(self.cur_path)  # вернуть в редактор сохранённый текст
            return True
        return False

    def revert_note(self) -> None:
        if not (self.cur_path and self.dirty):
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("Откатить"))
        box.setText(tr("Отбросить все несохранённые правки и вернуть файл как он сохранён?"))
        yes = box.addButton(tr("Откатить"), QMessageBox.ButtonRole.DestructiveRole)
        no = box.addButton(tr("Отмена"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() is yes:
            self.dirty = False
            self.open_note(self.cur_path, keep_cursor=True)

    def save_note(self) -> None:
        if not self.cur_path or not self.dirty:
            return
        try:
            write_text(self.cur_path, self._get_text())
            self.cur_mtime = os.stat(self.cur_path).st_mtime
        except OSError as e:
            self._say(tr("Ошибка сохранения: {}", e.strerror or e))
            return
        self.dirty = False
        self.save_btn.setEnabled(False)
        self.revert_btn.setEnabled(False)
        self.status.setText(tr("Сохранено ✓"))
        self.refresh_list()

    def _update_progress(self) -> None:
        if not self.cur_path:
            return
        if self.active is self.rich:
            done = total = 0
            b = self.rich.document().begin()
            while b.isValid():
                m = b.blockFormat().marker()
                if m != MK.NoMarker:
                    total += 1
                    done += m == MK.Checked
                b = b.next()
        else:
            done, total = count_tasks(self.editor.toPlainText())
        self.progress.setText(tr("Задачи: {} из {}", done, total) if total else "")

    def _set_mode(self, mode: str, save: bool = True) -> None:
        new = self.rich if mode == "visual" else self.editor
        if new is not self.active and self.cur_path:
            text = self._get_text()
            self.active = new
            self.loading = True
            self._put_text(text, self.cur_path)
            self.loading = False
            self._update_progress()
        self.active = new
        self.mode = mode
        for m, b in self.mode_btns.items():
            b.setChecked(m == mode)
        self.rich.setVisible(mode == "visual")
        self.editor.setVisible(mode == "source")
        if self.cur_path:
            new.setFocus()
        if save:
            self.cfg["mode"] = mode
            self.cfg_timer.start()

    def _cycle_mode(self) -> None:
        self._set_mode("source" if self.mode == "visual" else "visual")

    # --- создание, переименование, удаление
    def new_note(self) -> None:
        if not self._leave_ok():
            return
        src_before = self.lib.source
        try:
            path = self.lib.create_note()
        except OSError as e:
            self._say(tr("Не удалось создать файл: {}", e.strerror or e))
            return
        if self.lib.source != src_before:   # папки источника нет — заметка ушла в «Заметки»
            self._rebuild_sources()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.refresh_list()
        self.open_note(path)
        self.active.setFocus()
        cur = self.active.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.active.setTextCursor(cur)

    def _list_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        path = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not path:
            return
        menu = QMenu(self)
        menu.addAction(tr("Переименовать…")).triggered.connect(lambda: self.rename_note(path))
        menu.addAction(tr("Показать в папке")).triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
        menu.addAction(tr("Копировать путь")).triggered.connect(lambda: QApplication.clipboard().setText(path))
        if self._src_id() == FILES:
            menu.addAction(tr("Убрать из истории")).triggered.connect(lambda: self._forget_file(path))
        menu.addSeparator()
        menu.addAction(tr("Удалить файл…")).triggered.connect(lambda: self.delete_note(path))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def _forget_file(self, path: str) -> None:
        if path == self.cur_path and not self._leave_ok():
            return
        self.lib.forget_file(path)
        self.cfg_timer.start()
        if path == self.cur_path:
            self.cur_path = None
            self._editor_enabled(False)
        self.refresh_list()

    def rename_note(self, path: str) -> None:
        old = os.path.basename(path)
        stem, ext = os.path.splitext(old)
        name, ok = QInputDialog.getText(self, tr("Переименовать"), tr("Новое имя:"), text=stem)
        name = NoteLibrary.safe_name(name)
        if not ok or not name or name == stem:
            return
        if path == self.cur_path and not self._leave_ok():
            return
        try:
            new = self.lib.rename(path, name)
        except FileExistsError:
            self._say(tr("Файл с таким именем уже есть."))
            return
        except OSError as e:
            self._say(tr("Не удалось переименовать: {}", e.strerror or e))
            return
        if path == self.cur_path:
            self.cur_path = new
            self.d_title.setText(note_title(new))
            self.setWindowTitle(f"{note_title(new)} — Equestria Notes")
        self.cfg_timer.start()
        self.refresh_list()

    def delete_note(self, path: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("Удалить файл"))
        box.setText(tr("Переместить «{}» в корзину?", note_title(path)))
        yes = box.addButton(tr("В корзину"), QMessageBox.ButtonRole.AcceptRole)
        no = box.addButton(tr("Отмена"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() is not yes:
            return
        if path == self.cur_path:
            self.dirty = False
            self.save_timer.stop()
        try:
            self.lib.delete(path)  # корзины нет — удаляется напрямую (подтверждение уже было)
        except OSError as e:
            self._say(tr("Не удалось удалить: {}", e.strerror or e))
            return
        if path == self.cur_path:
            self.cur_path = None
            self._editor_enabled(False)
            self.setWindowTitle("Equestria Notes")
        self.cfg_timer.start()
        self.refresh_list()

    # --- тема / настройки
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
        self.hl.rehighlight()
        if self.cur_path and self.active is self.rich:
            self.loading = True
            self._put_text(self._get_text(), self.cur_path)
            self.loading = False
        self.save_cfg()

    def save_cfg(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def closeEvent(self, e) -> None:
        if not self._leave_ok():
            e.ignore()
            return
        self.save_cfg()
        super().closeEvent(e)


DEFAULTS = {"theme": DEFAULT_THEME, "mode": "visual", "source": GLOBAL, "folders": [], "files": [], "last": ""}


def load_config() -> dict:
    cfg = load_typed_config(CONFIG, DEFAULTS)
    cfg["folders"] = [p for p in cfg["folders"] if isinstance(p, str)]
    cfg["files"] = [p for p in cfg["files"] if isinstance(p, str)]
    if cfg["mode"] not in ("visual", "source"):
        cfg["mode"] = "visual"
    return cfg


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Notes")
    app.setDesktopFileName("equestria-notes")
    app.setStyle("Fusion")
    cfg = load_config()
    cfg["theme"] = apply_theme(kit_themes.current_name())
    win = MainWindow(cfg)
    kit_themes.follow(win._set_theme, lambda: win.theme)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())