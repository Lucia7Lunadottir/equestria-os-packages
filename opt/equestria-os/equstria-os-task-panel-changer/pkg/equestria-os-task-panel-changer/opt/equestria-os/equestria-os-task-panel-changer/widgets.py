import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPainterPath
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, pyqtProperty, QRectF, QSize, QPoint
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt


class HelpPopup(QLabel):
    """Собственное всплывающее окно с текстом подсказки.

    Нативный QToolTip под Wayland иногда определяет не тот экран/геометрию
    (известный баг KDE/Qt: bugs.kde.org #432860, #494338) и растягивается
    почти на весь монитор вместо того чтобы обернуться по тексту. Рисуем
    подсказку сами — фиксированная максимальная ширина с переносом строк,
    позиционирование через mapToGlobal самой кнопки, без угадывания экрана."""

    _MAX_WIDTH = 320

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.setMaximumWidth(self._MAX_WIDTH)
        kit_qt.style(self, 
            "QLabel {"
            "background-color: @base@;"
            "color: @text@;"
            "border: 1px solid @accent%55@;"
            "border-radius: 6px;"
            "padding: 6px 10px;"
            "}"
        )

    def show_near(self, anchor: QWidget):
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = anchor.screen()
        if screen:
            avail = screen.availableGeometry()
            max_x = avail.right() - self.width() - 4
            if pos.x() > max_x:
                pos.setX(max(max_x, avail.left() + 4))
            max_y = avail.bottom() - self.height() - 4
            if pos.y() > max_y:
                pos.setY(anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() - 4)
        self.move(pos)
        self.show()


class HelpButton(QWidget):
    """Маленькая круглая кнопка-подсказка ('?'), рисуется вручную через
    QPainter — border-radius у QPushButton на части систем/стилей KDE
    игнорируется или перекрывается нативным оформлением кнопки, из-за чего
    рамка и фон не были видны. Текст показывается сразу (без задержки
    нативного QToolTip) и по ховеру, и по клику (для тача/клавиатуры, где
    ховера не бывает)."""

    _SIZE = 18
    _BG = kit_qt.theme_color("surface1")
    _BG_HOVER = kit_qt.theme_color("accent%75")
    _BORDER = kit_qt.theme_color("subtext")
    _BORDER_HOVER = kit_qt.theme_color("accent")
    _TEXT = kit_qt.theme_color("accent_hover")
    _TEXT_HOVER = QColor(230, 220, 255)

    def __init__(self, help_text="", parent=None):
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._help_text = help_text
        self._hover = False
        self._popup = HelpPopup()

    def set_help_text(self, text):
        self._help_text = text

    def enterEvent(self, event):
        self._hover = True
        self.update()
        self._popup.setText(self._help_text)
        self._popup.show_near(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        self._popup.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._popup.setText(self._help_text)
        self._popup.show_near(self)
        super().mousePressEvent(event)

    def hideEvent(self, event):
        self._popup.hide()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self._SIZE - 2, self._SIZE - 2)
        p.setBrush(self._BG_HOVER if self._hover else self._BG)
        p.setPen(self._BORDER_HOVER if self._hover else self._BORDER)
        p.drawEllipse(rect)
        font = p.font()
        font.setBold(True)
        font.setPointSize(9)
        p.setFont(font)
        p.setPen(self._TEXT_HOVER if self._hover else self._TEXT)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "?")
        p.end()

class SafeCheckBox(QWidget):
    """Красивый анимированный Toggle-переключатель с текстом справа."""
    toggled = pyqtSignal(bool)

    _COLOR_ON  = kit_qt.theme_color("accent")
    _COLOR_OFF = kit_qt.theme_color("surface2")
    _COLOR_KNOB = QColor(230, 220, 255)

    _TRACK_W = 38
    _TRACK_H = 20
    _KNOB_D  = 14
    _PADDING = 3
    _LEFT_PAD = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._label = ""

        self._knob_x = float(self._PADDING)
        self._anim = QPropertyAnimation(self, b"knob_x", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.setMinimumHeight(self._TRACK_H + 4)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _get_knob_x(self): return self._knob_x
    def _set_knob_x(self, val):
        self._knob_x = val
        self.update()

    knob_x = pyqtProperty(float, _get_knob_x, _set_knob_x)

    def isChecked(self): return self._checked
    def setChecked(self, checked: bool):
        if self._checked == checked: return
        self._checked = checked
        self._animate_to(checked)

    def setText(self, text):
        self._label = text
        self.update()
        self.updateGeometry()

    def text(self): return self._label

    def _animate_to(self, on: bool):
        target = float(self._TRACK_W - self._PADDING - self._KNOB_D) if on else float(self._PADDING)
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(target)
        self._anim.start()

    def _toggle(self):
        self._checked = not self._checked
        self._animate_to(self._checked)
        self.toggled.emit(self._checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self._toggle()

    def sizeHint(self):
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self._label) + 8 if self._label else 0
        return QSize(self._LEFT_PAD + self._TRACK_W + 6 + text_w, max(self._TRACK_H + 4, fm.height() + 4))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        track_y = (h - self._TRACK_H) / 2
        lp = self._LEFT_PAD

        t = (self._knob_x - self._PADDING) / max(self._TRACK_W - 2 * self._PADDING - self._KNOB_D, 1)
        t = max(0.0, min(1.0, t))
        r = int(self._COLOR_OFF.red()   + t * (self._COLOR_ON.red()   - self._COLOR_OFF.red()))
        g = int(self._COLOR_OFF.green() + t * (self._COLOR_ON.green() - self._COLOR_OFF.green()))
        b = int(self._COLOR_OFF.blue()  + t * (self._COLOR_ON.blue()  - self._COLOR_OFF.blue()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(r, g, b))
        
        path = QPainterPath()
        path.addRoundedRect(QRectF(lp, track_y, self._TRACK_W, self._TRACK_H), self._TRACK_H / 2, self._TRACK_H / 2)
        p.drawPath(path)

        p.setBrush(self._COLOR_KNOB)
        p.drawEllipse(QRectF(lp + self._knob_x, track_y + (self._TRACK_H - self._KNOB_D) / 2, self._KNOB_D, self._KNOB_D))

        if self._label:
            p.setPen(kit_qt.theme_color("accent_hover"))
            p.drawText(int(lp + self._TRACK_W + 6), 0, self.width() - int(lp + self._TRACK_W + 6), h,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)
        p.end()

class PanelPreviewWidget(QWidget):
    """Мини-схема раскладки: экран и панели на нём (по данным пресета)."""

    def __init__(self, panels=None, panel_color="#313060", panel_opacity=90, parent=None):
        super().__init__(parent)
        self.panels = panels or []
        self.panel_color = panel_color
        self.panel_opacity = panel_opacity

    def set_appearance(self, color, opacity):
        self.panel_color = color
        self.panel_opacity = opacity
        self.update()

    def set_panels(self, panels):
        self.panels = panels or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        clip_path = QPainterPath()
        clip_path.addRoundedRect(0, 0, w, h, 4, 4)
        painter.setClipPath(clip_path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(kit_qt.theme_color("surface1"))
        painter.drawRect(0, 0, w, h)

        color = QColor(self.panel_color)
        color.setAlphaF(max(self.panel_opacity / 100.0, 0.70))
        painter.setBrush(color)
        for p in self.panels:
            vertical = p.get("location") in ("left", "right")
            along, across = (h, w) if vertical else (w, h)
            # толщина: высота в gridUnit → доля схемы (панель 2.5 gridUnit ≈ четверть)
            thick = max(3, int(across * min(0.34, float(p.get("height", 2.5)) * 0.1)))
            length = along if p.get("lengthMode", "fill") == "fill" else int(along * 0.55)
            gap = 2 if p.get("floating") else 0
            align = p.get("alignment", "center")
            start = {"left": gap, "right": along - length - gap}.get(align, (along - length) // 2)
            near = p.get("location") in ("top", "left")
            edge = gap if near else across - thick - gap
            x, y, pw, ph = (edge, start, thick, length) if vertical else (start, edge, length, thick)
            radius = 4 if p.get("floating") else 0
            painter.drawRoundedRect(x, y, pw, ph, radius, radius)
        painter.end()

class PresetCard(QPushButton):
    def __init__(self, preset_id, char_name, desc_text, icon_path, panels=None, parent=None):
        super().__init__(parent)
        self.preset_id = preset_id
        self.setMinimumSize(170, 230)
        self.setProperty("cssClass", "preset-card")
        self.setProperty("active", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 12)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        px = QPixmap(icon_path)
        if not px.isNull():
            icon_lbl.setPixmap(px.scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        name_lbl = QLabel(char_name)
        name_lbl.setProperty("cssClass", "char-name")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        desc_lbl = QLabel(desc_text)
        desc_lbl.setProperty("cssClass", "layout-desc")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.preview_widget = PanelPreviewWidget(panels)
        self.preview_widget.setFixedSize(96, 34)
        self.preview_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(icon_lbl)
        layout.addWidget(name_lbl)
        layout.addWidget(desc_lbl)
        layout.addWidget(self.preview_widget, 0, Qt.AlignmentFlag.AlignCenter)

    def sizeHint(self): return QSize(170, 230)
    def set_active_state(self, is_active: bool):
        self.setProperty("active", "true" if is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def update_appearance(self, color, opacity):
        self.preview_widget.set_appearance(color, opacity)