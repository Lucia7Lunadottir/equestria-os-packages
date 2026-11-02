"""Карточка персонажа в сетке выбора темы.

Рисуется вручную, чтобы состояния менялись плавно, а не скачком через QSS:
  • наведение — подсветка цветом персонажа + лёгкое увеличение значка (160 мс);
  • нажатие   — короткое «вдавливание» карточки (90 мс);
  • выбор     — мягкое свечение и галочка (220 мс).
Толщина рамки во всех состояниях одна и та же, поэтому содержимое не дёргается,
а смена выбора не требует перестраивать сетку (set_selected на месте).
"""

from PyQt6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QAbstractButton

from equestria_kit.qt import readable, theme_color, text_color


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t),
                  round(a.alpha() + (b.alpha() - a.alpha()) * t))


class _Tween:
    """Плавное значение 0…1 с анимацией; при изменении перерисовывает владельца."""

    def __init__(self, owner, duration: int, curve=QEasingCurve.Type.OutCubic):
        self.value = 0.0
        self.anim = QVariantAnimation(owner)
        self.anim.setDuration(duration)
        self.anim.setEasingCurve(curve)
        self.anim.valueChanged.connect(lambda v: (setattr(self, "value", float(v)), owner.update()))

    def to(self, target: float, animate: bool = True) -> None:
        self.anim.stop()
        if not animate:
            self.value = target
            return
        self.anim.setStartValue(self.value)
        self.anim.setEndValue(float(target))
        self.anim.start()


class CharacterCard(QAbstractButton):
    SIZE = QSize(190, 150)
    RADIUS = 16
    BORDER = 2

    def __init__(self, name: str, accent: str, icon_path: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name = name
        self.accent = QColor(accent) if QColor(accent).isValid() else theme_color("accent")
        self.pixmap = QPixmap(icon_path)
        self.hover = _Tween(self, 160)
        self.press = _Tween(self, 90)
        self.sel = _Tween(self, 220)
        self._selected = False

    # --- состояния -----------------------------------------------------------
    def set_selected(self, on: bool, animate: bool = True) -> None:
        if on != self._selected:
            self._selected = on
            self.sel.to(1.0 if on else 0.0, animate and self.isVisible())

    def is_selected(self) -> bool:
        return self._selected

    def enterEvent(self, e):
        self.hover.to(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover.to(0.0)
        self.press.to(0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.press.to(1.0)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self.press.to(0.0)
        super().mouseReleaseEvent(e)

    # --- отрисовка -------------------------------------------------------------
    def paintEvent(self, _e):
        h, pr, sl = self.hover.value, self.press.value, self.sel.value
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # «Вдавливание»: вся карточка чуть уменьшается вокруг центра
        scale = 1.0 - 0.03 * pr
        c = QRectF(self.rect()).center()
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)

        m = 4.0  # место под свечение выбранной карточки
        r = QRectF(self.rect()).adjusted(m, m, -m, -m)

        if sl > 0:  # свечение выбора
            for i, alpha in ((3.0, 50), (1.5, 90)):
                glow = QColor(self.accent)
                glow.setAlpha(round(alpha * sl))
                p.setPen(QPen(glow, i * 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, self.RADIUS, self.RADIUS)

        base = theme_color("surface0")
        tint = QColor(self.accent)
        bg = _mix(base, tint, 0.10 * h + 0.16 * sl)
        bg = _mix(bg, theme_color("crust"), 0.12 * pr)
        border = QColor(self.accent)
        border.setAlpha(round(110 + 145 * max(h, sl)))
        p.setPen(QPen(border, self.BORDER))
        p.setBrush(bg)
        inner = r.adjusted(self.BORDER / 2, self.BORDER / 2, -self.BORDER / 2, -self.BORDER / 2)
        p.drawRoundedRect(inner, self.RADIUS, self.RADIUS)

        # Значок: при наведении чуть крупнее
        icon_side = 84 * (1.0 + 0.06 * h)
        if not self.pixmap.isNull():
            pm = self.pixmap.scaled(round(icon_side), round(icon_side),
                                    Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
            x = r.center().x() - pm.width() / 2
            y = r.top() + 14 + (84 - pm.height()) / 2
            p.drawPixmap(round(x), round(y), pm)

        # Имя
        f = QFont(self.font())
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        name_sel = QColor(readable(self.accent.name(), theme_color("surface1").name()))
        p.setPen(_mix(text_color("text"), name_sel, 0.6 * sl))
        p.drawText(QRectF(r.left() + 6, r.bottom() - 40, r.width() - 12, 30),
                   Qt.AlignmentFlag.AlignCenter, self.name)

        # Галочка выбранного персонажа
        if sl > 0.01:
            d = 22.0
            badge = QRectF(r.left() + 10, r.top() + 10, d, d)
            fill = QColor(self.accent)
            fill.setAlpha(round(255 * sl))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawEllipse(badge)
            from equestria_kit.qt import contrast
            tick = QColor("#ffffff" if contrast("#ffffff", self.accent.name()) >= contrast("#111111", self.accent.name()) else "#111111")
            tick.setAlpha(round(255 * sl))
            pen = QPen(tick, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(badge.left() + 6, badge.center().y() + 0.5)
            path.lineTo(badge.left() + 9.5, badge.bottom() - 6.5)
            path.lineTo(badge.right() - 5.5, badge.top() + 7)
            p.drawPath(path)
