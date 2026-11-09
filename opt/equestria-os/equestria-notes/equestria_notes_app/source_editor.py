"""notes: source editor."""
from __future__ import annotations

import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit
from .markdown import FENCE_RE, HEAD_RE, LIST_RE, TASK_RE, flip_task, line_kind, split_line
from .style import THEME


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
