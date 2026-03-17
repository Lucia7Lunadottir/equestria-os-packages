from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QDialogButtonBox, QWidget,
                             QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import (QColor, QPainter, QLinearGradient, QBrush, QPen, QPolygon)
from core.locale import tr


_PAD      = 10   # left/right bar padding
_BAR_H    = 28   # height of the gradient bar
_HDL      = 9    # half-width of each handle triangle
_WIDGET_H = _BAR_H + _HDL * 2 + 14   # total widget height


# ── Gradient Bar ──────────────────────────────────────────────────────────────

class GradientBar(QWidget):
    stops_changed = pyqtSignal(list)    # list[(float, QColor)]
    stop_selected = pyqtSignal(int)     # selected index

    def __init__(self, stops: list, parent=None):
        super().__init__(parent)
        # Internal: list of [float, QColor]  (mutable so we can update in-place)
        self._stops: list = [[float(p), QColor(c)] for p, c in stops]
        self._selected: int = 0
        self._dragging: bool = False
        self.setMinimumSize(280, _WIDGET_H)
        self.setFixedHeight(_WIDGET_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _bar_rect(self) -> QRect:
        return QRect(_PAD, 4, self.width() - 2 * _PAD, _BAR_H)

    def _hx(self, pos: float) -> int:
        r = self._bar_rect()
        return int(r.left() + pos * r.width())

    def _hy(self) -> int:
        return self._bar_rect().bottom() + 6

    def _pos_from_x(self, x: int) -> float:
        r = self._bar_rect()
        return max(0.0, min(1.0, (x - r.left()) / max(r.width(), 1)))

    def _hit(self, x: int, y: int) -> int:
        hy = self._hy()
        for i, (pos, _) in enumerate(self._stops):
            if abs(x - self._hx(pos)) <= _HDL + 2 and abs(y - hy) <= _HDL + 4:
                return i
        return -1

    # ── Public API ────────────────────────────────────────────────────────────

    def get_stops(self) -> list:
        return [(p, QColor(c)) for p, c in sorted(self._stops, key=lambda s: s[0])]

    def set_stops(self, stops: list):
        self._stops = [[float(p), QColor(c)] for p, c in stops]
        self._stops.sort(key=lambda s: s[0])
        self._selected = 0
        self.update()
        self.stops_changed.emit(self.get_stops())
        self.stop_selected.emit(self._selected)

    def set_stop_color(self, index: int, color: QColor):
        if 0 <= index < len(self._stops):
            self._stops[index][1] = QColor(color)
            self.update()
            self.stops_changed.emit(self.get_stops())

    def set_stop_pos(self, index: int, pos: float):
        if 0 <= index < len(self._stops):
            stop = self._stops[index]
            stop[0] = max(0.0, min(1.0, pos))
            self._stops.sort(key=lambda s: s[0])
            self._selected = next(i for i, s in enumerate(self._stops) if s is stop)
            self.update()
            self.stops_changed.emit(self.get_stops())

    def delete_selected(self):
        if len(self._stops) <= 2 or self._selected < 0:
            return
        self._stops.pop(self._selected)
        self._selected = min(self._selected, len(self._stops) - 1)
        self.update()
        self.stops_changed.emit(self.get_stops())
        self.stop_selected.emit(self._selected)

    def select_stop(self, index: int):
        """Выделяет точку градиента по индексу."""
        if 0 <= index < len(self._stops):
            self._selected = index
            self.stop_selected.emit(self._selected)
            self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._bar_rect()

        # Checker (transparency indication)
        tile = 8
        for row in range(r.top(), r.bottom(), tile):
            for col in range(r.left(), r.right(), tile):
                shade = QColor(200, 200, 200) if ((row // tile + col // tile) % 2 == 0) \
                        else QColor(255, 255, 255)
                p.fillRect(col, row,
                           min(tile, r.right() - col),
                           min(tile, r.bottom() - row), shade)

        # Gradient bar
        if len(self._stops) >= 2:
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
            for pos, color in sorted(self._stops, key=lambda s: s[0]):
                grad.setColorAt(pos, color)
            p.fillRect(r, QBrush(grad))

        # Bar border
        p.setPen(QPen(QColor(70, 70, 80), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)

        # Handles
        hy = self._hy()
        for i, (pos, color) in enumerate(self._stops):
            hx = self._hx(pos)
            selected = (i == self._selected)
            tri = QPolygon([
                QPoint(hx,          hy - _HDL),
                QPoint(hx - _HDL,   hy + _HDL),
                QPoint(hx + _HDL,   hy + _HDL),
            ])
            p.setBrush(QBrush(color))
            pen_w = 2 if selected else 1
            pen_c = QColor(255, 220, 80) if selected else QColor(110, 110, 120)
            p.setPen(QPen(pen_c, pen_w))
            p.drawPolygon(tri)

        p.end()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = int(ev.position().x()), int(ev.position().y())
        hit = self._hit(x, y)
        if hit >= 0:
            self._selected = hit
            self._dragging = True
            self.stop_selected.emit(hit)
            self.update()
        else:
            r = self._bar_rect()
            if r.top() <= y <= r.bottom() + _HDL:
                pos = self._pos_from_x(x)
                color = self._interp(pos)
                self._stops.append([pos, color])
                self._stops.sort(key=lambda s: s[0])
                self._selected = next(
                    i for i, (p, _) in enumerate(self._stops) if abs(p - pos) < 1e-6)
                self._dragging = True
                self.stop_selected.emit(self._selected)
                self.stops_changed.emit(self.get_stops())
                self.update()

    def mouseMoveEvent(self, ev):
        if not self._dragging or self._selected < 0:
            return
        stop = self._stops[self._selected]
        pos = self._pos_from_x(int(ev.position().x()))
        stop[0] = pos
        self._stops.sort(key=lambda s: s[0])
        self._selected = next(i for i, s in enumerate(self._stops) if s is stop)
        self.stop_selected.emit(self._selected)
        self.stops_changed.emit(self.get_stops())
        self.update()

    def mouseReleaseEvent(self, ev):
        self._dragging = False

    def mouseDoubleClickEvent(self, ev):
        x, y = int(ev.position().x()), int(ev.position().y())
        hit = self._hit(x, y)
        if hit >= 0:
            self._selected = hit
            self._pick_color(hit)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Delete:
            self.delete_selected()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _pick_color(self, index: int):
        from ui.hsv_picker import ColorPickerDialog
        
        c = ColorPickerDialog.get_color(self._stops[index][1], self)
        if c is not None:
            self._stops[index][1] = c
            self.stops_changed.emit(self.get_stops())
            self.stop_selected.emit(self._selected)
            self.update()

    def _interp(self, pos: float) -> QColor:
        s = sorted(self._stops, key=lambda x: x[0])
        if not s:
            return QColor(128, 128, 128)
        if pos <= s[0][0]:
            return QColor(s[0][1])
        if pos >= s[-1][0]:
            return QColor(s[-1][1])
        for i in range(len(s) - 1):
            p0, c0 = s[i];  p1, c1 = s[i + 1]
            if p0 <= pos <= p1:
                t = (pos - p0) / (p1 - p0) if p1 > p0 else 0.0
                return QColor(
                    int(c0.red()   + t * (c1.red()   - c0.red())),
                    int(c0.green() + t * (c1.green() - c0.green())),
                    int(c0.blue()  + t * (c1.blue()  - c0.blue())),
                    int(c0.alpha() + t * (c1.alpha() - c0.alpha())),
                )
        return QColor(128, 128, 128)


# ── Gradient Preview Widget (toolbar swatch) ─────────────────────────────────

class GradientPreviewWidget(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stops: list = [(0.0, QColor(0, 0, 0)), (1.0, QColor(255, 255, 255))]
        self.setFixedSize(96, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_stops(self, stops: list):
        self._stops = list(stops)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        r = self.rect().adjusted(1, 1, -1, -1)
        tile = 6
        for row in range(r.top(), r.bottom(), tile):
            for col in range(r.left(), r.right(), tile):
                shade = QColor(200, 200, 200) if ((row // tile + col // tile) % 2 == 0) \
                        else QColor(255, 255, 255)
                p.fillRect(col, row,
                           min(tile, r.right() - col),
                           min(tile, r.bottom() - row), shade)
        if len(self._stops) >= 2:
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
            for pos, color in sorted(self._stops, key=lambda s: s[0]):
                grad.setColorAt(pos, color)
            p.fillRect(r, QBrush(grad))
        p.setPen(QPen(QColor(80, 80, 90), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ── Gradient Editor Dialog ────────────────────────────────────────────────────

class GradientEditorDialog(QDialog):

    def __init__(self, stops: list,
                 fg: QColor = None, bg: QColor = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("gradient_editor.title"))
        self.setMinimumWidth(400)

        self._fg = QColor(fg) if fg else QColor(0, 0, 0)
        self._bg = QColor(bg) if bg else QColor(255, 255, 255)
        self._updating = False

        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        # ── Gradient bar ─────────────────────────────────────────────────
        self._bar = GradientBar(stops)
        lo.addWidget(self._bar)

        # ── Selected stop controls ───────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        pos_lbl = QLabel(tr("gradient_editor.position"))
        pos_lbl.setObjectName("optLabel")
        ctrl.addWidget(pos_lbl)

        self._pos_spin = QSpinBox()
        self._pos_spin.setRange(0, 100)
        self._pos_spin.setSuffix("%")
        self._pos_spin.setFixedWidth(64)
        ctrl.addWidget(self._pos_spin)

        clr_lbl = QLabel(tr("gradient_editor.color"))
        clr_lbl.setObjectName("optLabel")
        ctrl.addWidget(clr_lbl)

        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(48, 22)
        ctrl.addWidget(self._color_btn)

    # --- Добавляем элементы для Opacity ---
        op_lbl = QLabel(tr("opts.opacity")) # Используем существующий ключ перевода
        op_lbl.setObjectName("optLabel")
        ctrl.addWidget(op_lbl)

        self._op_spin = QSpinBox()
        self._op_spin.setRange(0, 100)
        self._op_spin.setSuffix("%")
        self._op_spin.setFixedWidth(56)
        ctrl.addWidget(self._op_spin)
        # --------------------------------------


        self._del_btn = QPushButton(tr("gradient_editor.delete"))
        self._del_btn.setObjectName("dangerBtn")
        self._del_btn.setFixedHeight(22)
        ctrl.addWidget(self._del_btn)

        ctrl.addStretch()
        lo.addLayout(ctrl)

        # ── Presets ──────────────────────────────────────────────────────
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        pres_lbl = QLabel(tr("gradient_editor.presets"))
        pres_lbl.setObjectName("optLabel")
        preset_row.addWidget(pres_lbl)

        def _add_preset(label, fn):
            b = QPushButton(label)
            b.setObjectName("smallBtn")
            b.setFixedHeight(22)
            b.clicked.connect(lambda _, f=fn: self._bar.set_stops(f()))
            preset_row.addWidget(b)

        _add_preset("B→W",    lambda: [(0.0, QColor(0,0,0)),   (1.0, QColor(255,255,255))])
        _add_preset("W→B",    lambda: [(0.0, QColor(255,255,255)), (1.0, QColor(0,0,0))])
        _add_preset("FG→BG",  lambda: [(0.0, QColor(self._fg)), (1.0, QColor(self._bg))])
        _add_preset("FG→T",   lambda: [(0.0, QColor(self._fg)),
                                        (1.0, QColor(self._fg.red(), self._fg.green(),
                                                     self._fg.blue(), 0))])
        _add_preset("🌈",     lambda: [
            (0/6, QColor(255, 0, 0)),   (1/6, QColor(255, 165, 0)),
            (2/6, QColor(255, 255, 0)), (3/6, QColor(0, 255, 0)),
            (4/6, QColor(0, 0, 255)),   (5/6, QColor(75, 0, 130)),
            (1.0, QColor(148, 0, 211)),
        ])
        preset_row.addStretch()
        lo.addLayout(preset_row)

        # ── OK / Cancel ──────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lo.addWidget(btns)

        # ── Wiring ───────────────────────────────────────────────────────
        self._bar.stop_selected.connect(self._on_stop_selected)
        self._bar.stops_changed.connect(self._on_stops_changed)
        self._pos_spin.valueChanged.connect(self._on_pos_spin_changed)
        self._color_btn.clicked.connect(self._on_color_btn_clicked)
        self._del_btn.clicked.connect(self._bar.delete_selected)
        self._op_spin.valueChanged.connect(self._on_op_spin_changed)

        # Select first stop
        self._bar.select_stop(0)
        self._on_stop_selected(0)

    # ── Stop display ──────────────────────────────────────────────────────────

    def _on_stop_selected(self, index: int):
        self._updating = True
        stops = self._bar._stops
        if 0 <= index < len(stops):
            pos, color = stops[index]
            self._pos_spin.setValue(int(round(pos * 100)))
            # Обновляем спинбокс прозрачности (извлекаем альфа-канал 0-255 и переводим в 0-100)
            self._op_spin.setValue(int(round(color.alphaF() * 100)))
            self._update_color_swatch(color)
            self._del_btn.setEnabled(len(stops) > 2)
        self._updating = False

    def _on_stops_changed(self, _stops):
        idx = self._bar._selected
        self._on_stop_selected(idx)

    def _update_color_swatch(self, color: QColor):
        # Используем rgba для корректного отображения цвета с прозрачностью на кнопке
        rgba_str = f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF()})"
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background:{rgba_str}; border:1px solid #555; border-radius:3px; }}")
        self._current_color = QColor(color)

    def _on_pos_spin_changed(self, val: int):
        if self._updating:
            return
        self._bar.set_stop_pos(self._bar._selected, val / 100.0)

    def _on_color_btn_clicked(self):
        idx = self._bar._selected
        if idx < 0 or idx >= len(self._bar._stops):
            return
        current = self._bar._stops[idx][1]
        
        from ui.hsv_picker import ColorPickerDialog
        
        new_color = ColorPickerDialog.get_color(current, self)
        if new_color is not None:
            self._bar.set_stop_color(idx, new_color)
            self._update_color_swatch(new_color)


    def _on_op_spin_changed(self, val: int):
        if self._updating:
            return
        idx = self._bar._selected
        if idx < 0 or idx >= len(self._bar._stops):
            return

        # Берем текущий цвет выделенной точки
        current_color = self._bar._stops[idx][1]

        # Создаем новый цвет с обновленным альфа-каналом
        new_color = QColor(current_color)
        new_color.setAlphaF(val / 100.0)

        # Обновляем цвет в баре
        self._bar.set_stop_color(idx, new_color)

        # Обновляем кнопку цвета, чтобы она отражала новую прозрачность (если нужно)
        self._updating = True
        self._update_color_swatch(new_color)
        self._updating = False


    # ── Result ────────────────────────────────────────────────────────────────

    def result_stops(self) -> list:
        return self._bar.get_stops()
