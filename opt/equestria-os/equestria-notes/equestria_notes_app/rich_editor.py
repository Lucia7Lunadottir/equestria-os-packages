"""notes: rich editor."""
from __future__ import annotations

import base64
import os
import re
from PyQt6.QtCore import QPointF, QRectF, QTimer, QUrl, Qt
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QImage,
    QImageReader,
    QPainter,
    QPen,
    QPolygonF,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextImageFormat,
    QTextListFormat
)
from PyQt6.QtWidgets import QInputDialog, QTextEdit
from equestria_kit import qt as kit_qt
from urllib.parse import unquote
from .images import BULLETS, FSA, IMG_EXTS, MK, resolve_refs, store_image, store_qimage
from .localization import tr
from .style import THEME


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
        url, ok = QInputDialog.getText(self, tr("common.link"), tr("rich_editor.address"), text="https://")
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
