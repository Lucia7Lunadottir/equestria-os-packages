"""calendar: calendar views."""
from __future__ import annotations
import calendar
import math
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QTextCharFormat
from PyQt6.QtWidgets import QCalendarWidget, QToolButton, QWidget
from datetime import date, timedelta
from .dates import MONTHS, WD_SHORT, add_months, moon_info, next_phase, short_date
from .localization import live_i18n, tr
from .moon_drawing import draw_moon
from .style import MOON_LIGHT, THEME, alpha, pfont




class MoonCard(QWidget):
    def __init__(self):
        super().__init__()
        self.d = date.today()
        self.setFixedHeight(112)

    def set_date(self, d: date) -> None:
        self.d = d
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.fillPath(path, QColor(THEME["mantle"]))
        mi = moon_info(self.d)
        draw_moon(p, QRectF(16, (self.height() - 72) / 2, 72, 72), mi["f"], THEME, MOON_LIGHT)
        x, w = 104, self.width() - 116
        p.setFont(pfont(16, True))
        p.setPen(QColor(THEME["accent"]))
        live_i18n.call(p.drawText, QRectF(x, 12, w, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, mi["name"])
        p.setFont(pfont(12))
        p.setPen(QColor(THEME["subtext"]))
        lines = [tr("calendar_views.illuminated_age_d", mi['illum'] * 100, mi['age']),
                 tr("calendar_views.full_moon", short_date(next_phase(self.d, 0.5))),
                 tr("calendar_views.new_moon", short_date(next_phase(self.d, 0.0)))]
        for i, t in enumerate(lines):
            live_i18n.call(p.drawText, QRectF(x, 40 + i * 20, w, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, t)


class CalView(QWidget):
    selected = pyqtSignal(object)
    activated = pyqtSignal(object)
    shifted = pyqtSignal(int)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.mode = "month"
        self.sel = date.today()
        self.hover = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(700, 520)

    def start_date(self) -> date:
        fw = 6 if self.app.cfg["sunday_first"] else 0
        base = self.sel if self.mode == "week" else self.sel.replace(day=1)
        return base - timedelta(days=(base.weekday() - fw) % 7)

    def rows(self) -> int:
        return 1 if self.mode == "week" else 6

    def _geom(self):
        wn, hdr = 26, 30
        return wn, hdr, (self.width() - wn) / 7, (self.height() - hdr) / self.rows()

    def date_at(self, pos):
        wn, hdr, cw, ch = self._geom()
        x, y = pos.x() - wn, pos.y() - hdr
        if x < 0 or y < 0:
            return None
        c, r = int(x // cw), int(y // ch)
        if c > 6 or r >= self.rows():
            return None
        return self.start_date() + timedelta(days=r * 7 + c)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th, today = THEME, date.today()
        wn, hdr, cw, ch = self._geom()
        start = self.start_date()
        fw = 6 if self.app.cfg["sunday_first"] else 0
        show_moon = self.app.cfg["show_moon"] and ch >= 64
        f_hdr, f_num, f_chip, f_chip_s = pfont(12, True), pfont(14, True), pfont(12), pfont(12)
        f_chip_s.setStrikeOut(True)
        fm, fm_s = QFontMetrics(f_chip), QFontMetrics(f_chip_s)
        for c in range(7):
            wd = (fw + c) % 7
            p.setFont(f_hdr)
            p.setPen(QColor(th["red"] if wd >= 5 else th["subtext"]))
            live_i18n.call(p.drawText, QRectF(wn + c * cw, 0, cw, hdr), Qt.AlignmentFlag.AlignCenter, WD_SHORT[wd])
        for r in range(self.rows()):
            d0 = start + timedelta(days=r * 7)
            p.setFont(pfont(11))
            p.setPen(alpha(th["subtext"], 150))
            live_i18n.call(p.drawText, QRectF(0, hdr + r * ch + 8, wn - 6, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str((d0 + timedelta(days=3)).isocalendar()[1]))
            for c in range(7):
                d = d0 + timedelta(days=c)
                in_month = self.mode == "week" or d.month == self.sel.month
                cell = QRectF(wn + c * cw + 2, hdr + r * ch + 2, cw - 4, ch - 4)
                bg = th["surface1"] if d == self.hover else (th["surface0"] if in_month else th["mantle"])
                path = QPainterPath()
                path.addRoundedRect(cell, 12, 12)
                p.fillPath(path, QColor(bg))
                if d == self.sel:
                    p.setPen(QPen(QColor(th["accent"]), 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawPath(path)
                num = QRectF(cell.left() + 6, cell.top() + 6, 26, 24)
                p.setFont(f_num)
                if d == today:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(th["accent"]))
                    p.drawEllipse(num)
                    p.setPen(QColor(th["base"]))
                else:
                    p.setPen(QColor(th["text"] if in_month else th["surface2"]))
                live_i18n.call(p.drawText, num, Qt.AlignmentFlag.AlignCenter, str(d.day))
                if show_moon:
                    mi = moon_info(d)
                    size = 20 if mi["major"] else 16
                    draw_moon(p, QRectF(cell.right() - 8 - size, cell.top() + 8 - (size - 16) / 2, size, size), mi["f"], THEME, MOON_LIGHT)
                evs = self.app.events_on(d)
                if not evs:
                    continue
                y, lh = cell.top() + 34, 19
                maxn = max(1, int((cell.bottom() - y - 2) // lh))
                shown = evs if len(evs) <= maxn else evs[:max(1, maxn - 1)]
                for rem in shown:
                    done = self.app.is_done(rem, d)
                    chip = QRectF(cell.left() + 5, y, cell.width() - 10, lh - 3)
                    cp = QPainterPath()
                    cp.addRoundedRect(chip, 6, 6)
                    p.fillPath(cp, alpha(rem["color"], 35 if done else 80))
                    p.fillRect(QRectF(chip.left(), chip.top() + 3, 3, chip.height() - 6), QColor(rem["color"]))
                    label = ("" if rem.get("all_day") else rem["time"] + " ") + rem["title"]
                    p.setFont(f_chip_s if done else f_chip)
                    p.setPen(QColor(th["subtext"] if done else th["text"]))
                    el = (fm_s if done else fm).elidedText(label, Qt.TextElideMode.ElideRight, int(chip.width() - 14))
                    live_i18n.call(p.drawText, chip.adjusted(8, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, el)
                    y += lh
                if len(evs) > len(shown):
                    p.setFont(pfont(11))
                    p.setPen(QColor(th["subtext"]))
                    live_i18n.call(p.drawText, QRectF(cell.left() + 8, y - 1, cell.width() - 12, 16),
                               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                               tr("calendar_views.more", len(evs) - len(shown)))

    def mouseMoveEvent(self, e) -> None:
        d = self.date_at(e.position())
        if d != self.hover:
            self.hover = d
            self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = None
        self.update()

    def mousePressEvent(self, e) -> None:
        self.setFocus()
        d = self.date_at(e.position())
        if d and e.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(d)

    def mouseDoubleClickEvent(self, e) -> None:
        d = self.date_at(e.position())
        if d and e.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(d)
            self.activated.emit(d)

    def wheelEvent(self, e) -> None:
        dy = e.angleDelta().y()
        if dy:
            self.shifted.emit(-1 if dy > 0 else 1)

    def keyPressEvent(self, e) -> None:
        k, d = e.key(), self.sel
        K = Qt.Key
        new = {K.Key_Left: d - timedelta(days=1), K.Key_Right: d + timedelta(days=1),
               K.Key_Up: d - timedelta(days=7), K.Key_Down: d + timedelta(days=7),
               K.Key_PageUp: add_months(d, -1), K.Key_PageDown: add_months(d, 1),
               K.Key_Home: date.today()}.get(k)
        if new:
            self.selected.emit(new)
        elif k in (K.Key_Return, K.Key_Enter):
            self.activated.emit(d)
        else:
            super().keyPressEvent(e)


class YearView(QWidget):
    selected = pyqtSignal(object)
    activated = pyqtSignal(object)
    shifted = pyqtSignal(int)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.sel = date.today()
        self._cells: list = []
        self._titles: list = []
        self.setMinimumSize(700, 520)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th, today, year = THEME, date.today(), self.sel.year
        self._cells, self._titles = [], []
        fw = 6 if self.app.cfg["sunday_first"] else 0
        cols = 4 if self.width() >= 980 else 3
        mw, mh = self.width() / cols, self.height() / (12 // cols)
        cal = calendar.Calendar(fw)
        for i in range(12):
            m = i + 1
            bx = QRectF((i % cols) * mw + 6, (i // cols) * mh + 6, mw - 12, mh - 12)
            path = QPainterPath()
            path.addRoundedRect(bx, 14, 14)
            p.fillPath(path, QColor(th["mantle"]))
            tr = QRectF(bx.left() + 12, bx.top() + 8, bx.width() - 24, 20)
            self._titles.append((tr, m))
            p.setFont(pfont(14, True))
            p.setPen(QColor(th["accent"] if m == self.sel.month else th["text"]))
            live_i18n.call(p.drawText, tr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, MONTHS[i])
            gx, gw = bx.left() + 10, bx.width() - 20
            cw, top = gw / 7, bx.top() + 48
            ch = (bx.bottom() - top - 6) / 6
            p.setFont(pfont(10))
            p.setPen(QColor(th["subtext"]))
            for c in range(7):
                live_i18n.call(p.drawText, QRectF(gx + c * cw, top - 16, cw, 14), Qt.AlignmentFlag.AlignCenter,
                           WD_SHORT[(fw + c) % 7][0])
            for ri, wk in enumerate(cal.monthdayscalendar(year, m)):
                for ci, dd in enumerate(wk):
                    if not dd:
                        continue
                    day = date(year, m, dd)
                    cell = QRectF(gx + ci * cw, top + ri * ch, cw, ch)
                    self._cells.append((cell, day))
                    sq = min(cw, ch) - 2
                    circ = QRectF(cell.center().x() - sq / 2, cell.center().y() - sq / 2, sq, sq)
                    p.setFont(pfont(11, day == today))
                    if day == today:
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QColor(th["accent"]))
                        p.drawEllipse(circ)
                        p.setPen(QColor(th["base"]))
                    else:
                        if day == self.sel:
                            p.setPen(QPen(QColor(th["accent"]), 1.5))
                            p.setBrush(Qt.BrushStyle.NoBrush)
                            p.drawEllipse(circ)
                        p.setPen(QColor(th["red"] if day.weekday() >= 5 else th["text"]))
                    live_i18n.call(p.drawText, cell, Qt.AlignmentFlag.AlignCenter, str(dd))
                    evs = self.app.events_on(day)
                    if evs:
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QColor(evs[0]["color"]))
                        p.drawEllipse(QRectF(cell.center().x() - 2, cell.bottom() - 4, 4, 4))

    def _hit(self, pos):
        pt = pos
        for r, m in self._titles:
            if r.contains(pt):
                return date(self.sel.year, m, 1), True
        for r, d in self._cells:
            if r.contains(pt):
                return d, False
        return None, False

    def mousePressEvent(self, e) -> None:
        d, title = self._hit(e.position())
        if d:
            self.selected.emit(d)
            if title:
                self.activated.emit(d)

    def mouseDoubleClickEvent(self, e) -> None:
        d, title = self._hit(e.position())
        if d:
            self.selected.emit(d)
            self.activated.emit(d)

    def wheelEvent(self, e) -> None:
        dy = e.angleDelta().y()
        if dy:
            self.shifted.emit(-1 if dy > 0 else 1)


def make_calendar(sunday_first: bool) -> QCalendarWidget:
    cal = QCalendarWidget()
    cal.setGridVisible(False)
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setFirstDayOfWeek(Qt.DayOfWeek.Sunday if sunday_first else Qt.DayOfWeek.Monday)
    hf = QTextCharFormat()
    hf.setForeground(QColor(THEME["subtext"]))
    hf.setBackground(QColor(THEME["mantle"]))
    cal.setHeaderTextFormat(hf)
    for dow in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
        f = QTextCharFormat()
        f.setForeground(QColor(THEME["red"]))
        cal.setWeekdayTextFormat(dow, f)
    for name, txt in (("qt_calendar_prevmonth", "◀"), ("qt_calendar_nextmonth", "▶")):
        b = cal.findChild(QToolButton, name)
        if b:
            b.setIcon(QIcon())
            live_i18n.call(b.setText, txt)
    return cal
