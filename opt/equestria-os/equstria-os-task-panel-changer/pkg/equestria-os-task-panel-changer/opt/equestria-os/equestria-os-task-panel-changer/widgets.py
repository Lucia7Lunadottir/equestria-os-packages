import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPainterPath
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, pyqtProperty, QRectF, QSize

PANEL_LAYOUTS = {
    "sunset":    [{"pos": "bottom", "w": 0.62, "h": 0.28, "float": True}],
    "twilight":  [{"pos": "bottom", "w": 1.0,  "h": 0.22, "float": False}],
    "rainbow":   [{"pos": "top",    "w": 1.0,  "h": 0.16, "float": False},
                  {"pos": "bottom", "w": 0.45, "h": 0.26, "float": True}],
    "rarity":    [{"pos": "top",    "w": 1.0,  "h": 0.14, "float": False},
                  {"pos": "bottom", "w": 0.38, "h": 0.30, "float": True}],
    "applejack": [{"pos": "bottom", "w": 1.0,  "h": 0.26, "float": False}],
    "fluttershy":[{"pos": "bottom", "w": 0.70, "h": 0.22, "float": True}],
    "pinkie":    [{"pos": "bottom", "w": 1.0,  "h": 0.24, "float": False}],
}

class SafeCheckBox(QWidget):
    """Красивый анимированный Toggle-переключатель с текстом справа."""
    toggled = pyqtSignal(bool)

    _COLOR_ON  = QColor(120, 80, 200)
    _COLOR_OFF = QColor(55, 48, 80)
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
            p.setPen(QColor(200, 190, 230))
            p.drawText(int(lp + self._TRACK_W + 6), 0, self.width() - int(lp + self._TRACK_W + 6), h,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)
        p.end()

class PanelPreviewWidget(QWidget):
    def __init__(self, preset_id, panel_color="#1e1e2e", panel_opacity=90, parent=None):
        super().__init__(parent)
        self.preset_id = preset_id
        self.panel_color = panel_color
        self.panel_opacity = panel_opacity
        self.layout_configs = PANEL_LAYOUTS.get(preset_id, [])

    def set_appearance(self, color, opacity):
        self.panel_color = color
        self.panel_opacity = opacity
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        clip_path = QPainterPath()
        clip_path.addRoundedRect(0, 0, w, h, 4, 4)
        painter.setClipPath(clip_path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(44, 42, 68))
        painter.drawRect(0, 0, w, h)

        for cfg in self.layout_configs:
            pw, ph = int(w * cfg["w"]), int(h * cfg["h"])
            x = (w - pw) // 2
            y = h - ph if cfg["pos"] == "bottom" else 0
            color = QColor(self.panel_color)
            color.setAlphaF(max(self.panel_opacity / 100.0, 0.70))
            painter.setBrush(color)
            radius = 5 if cfg.get("float") else 0
            painter.drawRoundedRect(x, y, pw, ph, radius, radius)
        painter.end()

class PresetCard(QPushButton):
    def __init__(self, preset_id, char_name, desc_text, icon_path, parent=None):
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

        self.preview_widget = PanelPreviewWidget(preset_id)
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