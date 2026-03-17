"""Levels adjustment dialog — histogram, draggable handles, output levels, Auto."""

import math

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox,
    QPushButton, QSpinBox, QDoubleSpinBox, QWidget,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QImage, QPainter, QColor, QLinearGradient, QBrush, QPen, QPolygon,
)
from core.locale import tr
from ui.adjustments_dialog import _to_argb32


# ── pixel math ───────────────────────────────────────────────────────────────

def compute_histogram(img: QImage) -> list:
    """256-element list: pixel count per luminance bucket (using source image)."""
    argb = _to_argb32(img)
    try:
        import numpy as np
        ptr = argb.constBits()
        ptr.setsize(argb.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((argb.height(), argb.width(), 4))
        
        mask = arr[:, :, 3] > 0
        if not np.any(mask):
            return [0] * 256
            
        b = arr[:, :, 0][mask].astype(np.float32)
        g = arr[:, :, 1][mask].astype(np.float32)
        r = arr[:, :, 2][mask].astype(np.float32)
        
        lum = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)
        counts, _ = np.histogram(lum, bins=256, range=(0, 256))
        return counts.tolist()
    except ImportError:
        hist = [0] * 256
        for y in range(argb.height()):
            for x in range(argb.width()):
                px = argb.pixel(x, y)
                if (px >> 24) & 0xFF > 0:
                    lum = int(0.299 * ((px >> 16) & 0xFF)
                            + 0.587 * ((px >>  8) & 0xFF)
                            + 0.114 * (px & 0xFF))
                    hist[min(255, lum)] += 1
        return hist


def apply_levels(src: QImage,
                 black: int, gamma: float, white: int,
                 out_min: int, out_max: int) -> QImage:
    """Apply input/output levels via an 8-bit LUT."""
    black   = max(0,       min(253,      black))
    white   = max(black+1, min(255,      white))
    gamma   = max(0.01,    min(9.99,     gamma))
    out_min = max(0,       min(254,      out_min))
    out_max = max(out_min+1, min(255,    out_max))

    inv_g    = 1.0 / gamma
    in_span  = white - black
    out_span = out_max - out_min

    lut = bytearray(256)
    for i in range(256):
        v = max(0.0, min(1.0, (i - black) / in_span)) ** inv_g
        lut[i] = int(max(0, min(255, out_min + v * out_span)))

    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((img.height(), img.width(), 4))
        lut_np = np.frombuffer(lut, dtype=np.uint8)
        arr[:, :, :3] = lut_np[arr[:, :, :3]]
        del arr
        del ptr
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        for y in range(img.height()):
            for x in range(img.width()):
                px = img.pixel(x, y)
                a = (px >> 24) & 0xFF
                r = lut[(px >> 16) & 0xFF]
                g = lut[(px >>  8) & 0xFF]
                b = lut[px & 0xFF]
                img.setPixel(x, y, (a << 24) | (r << 16) | (g << 8) | b)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


# ── histogram + input handles widget ─────────────────────────────────────────

class _HistogramWidget(QWidget):
    """
    Draws the histogram and a gradient bar below it.
    Three triangular handles (black / gamma / white) are draggable.

    Gamma handle uses a logarithmic mapping:
        t ∈ [0,1]  →  gamma = 10^((1 - 2t) * LOG_MAX)
        t=0 → gamma=9.99 (far left),  t=0.5 → gamma=1.0,  t=1 → gamma=0.10
    """

    HIST_H  = 120
    GRAD_H  = 14
    HAND_H  = 16
    PAD     = 6          # left / right padding
    LOG_MAX = math.log10(9.99)

    black_changed = pyqtSignal(int)
    gamma_changed = pyqtSignal(float)
    white_changed = pyqtSignal(int)

    def __init__(self, histogram: list, parent=None):
        super().__init__(parent)
        self._hist  = histogram
        self._black = 0
        self._gamma = 1.0
        self._white = 255
        self._drag  = None          # "black" | "gamma" | "white"
        self.setFixedHeight(self.HIST_H + self.GRAD_H + self.HAND_H + 2)
        self.setMinimumWidth(300)
        self.setMouseTracking(True)

    # ── value ↔ x coordinate ─────────────────────────────────────────────────

    def _val_to_x(self, val: int) -> int:
        span = self.width() - 2 * self.PAD
        return self.PAD + int(val * span / 255)

    def _x_to_val(self, x: int) -> int:
        span = max(1, self.width() - 2 * self.PAD)
        return int(max(0, min(255, (x - self.PAD) * 255 / span)))

    def _gamma_x(self) -> int:
        bx = self._val_to_x(self._black)
        wx = self._val_to_x(self._white)
        t  = (1.0 - math.log10(self._gamma) / self.LOG_MAX) / 2.0
        return int(bx + (wx - bx) * t)

    def _x_to_gamma(self, x: int) -> float:
        bx = self._val_to_x(self._black)
        wx = self._val_to_x(self._white)
        span = wx - bx
        if span <= 0:
            return 1.0
        t = max(1e-4, min(1 - 1e-4, (x - bx) / span))
        return max(0.10, min(9.99, 10 ** ((1.0 - 2.0 * t) * self.LOG_MAX)))

    # ── public ───────────────────────────────────────────────────────────────

    def set_values(self, black: int, gamma: float, white: int):
        self._black = black
        self._gamma = gamma
        self._white = white
        self.update()

    # ── painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p   = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W   = self.width()
        bx  = self._val_to_x(self._black)
        wx  = self._val_to_x(self._white)
        gx  = self._gamma_x()

        # ── histogram background ──────────────────────────────────────────
        p.fillRect(0, 0, W, self.HIST_H, QColor(18, 18, 28))

        # bars
        valid_counts = sorted([c for c in self._hist if c > 0])
        if not valid_counts:
            max_c = 1
        else:
            idx = min(len(valid_counts) - 1, int(len(valid_counts) * 0.98))
            max_c = max(1, valid_counts[idx])
            
        bar_w = max(1.0, (W - 2 * self.PAD) / 255.0)
        for i, c in enumerate(self._hist):
            if c == 0:
                continue
            bh = min(self.HIST_H, int(self.HIST_H * c / max_c))
            x  = int(self.PAD + i * (W - 2 * self.PAD) / 255)
            p.fillRect(x, self.HIST_H - bh, max(1, int(bar_w)), bh,
                       QColor(150, 150, 190))

        # dim overlay outside [black, white]
        p.fillRect(0,  0, bx,     self.HIST_H, QColor(0, 0, 0, 130))
        p.fillRect(wx, 0, W - wx, self.HIST_H, QColor(0, 0, 0, 130))

        # faint gamma vertical line inside histogram
        p.setPen(QPen(QColor(200, 200, 200, 60), 1, Qt.PenStyle.DashLine))
        p.drawLine(gx, 0, gx, self.HIST_H)

        # border
        p.setPen(QPen(QColor(60, 60, 80), 1))
        p.drawRect(0, 0, W - 1, self.HIST_H - 1)

        # ── gradient bar ─────────────────────────────────────────────────
        gy = self.HIST_H
        grad = QLinearGradient(0, gy, W, gy)
        grad.setColorAt(0.0, Qt.GlobalColor.black)
        grad.setColorAt(1.0, Qt.GlobalColor.white)
        p.fillRect(0, gy, W, self.GRAD_H, QBrush(grad))

        # ── triangle handles ─────────────────────────────────────────────
        hy = self.HIST_H + self.GRAD_H

        def _tri(cx: int, col: QColor, outline: QColor):
            pts = QPolygon([
                QPoint(cx,     hy),
                QPoint(cx - 6, hy + self.HAND_H),
                QPoint(cx + 6, hy + self.HAND_H),
            ])
            p.setPen(QPen(outline, 1))
            p.setBrush(QBrush(col))
            p.drawPolygon(pts)

        _tri(bx, QColor(20,  20,  20),  QColor(160, 160, 160))
        _tri(wx, QColor(240, 240, 240), QColor(80,  80,  80))
        _tri(gx, QColor(160, 160, 160), QColor(50,  50,  50))

        p.end()

    # ── handle hit-test ───────────────────────────────────────────────────────

    def _handle_at(self, x: int, y: int):
        if y < self.HIST_H + self.GRAD_H - 4:
            return None
        bx, wx, gx = (self._val_to_x(self._black),
                      self._val_to_x(self._white),
                      self._gamma_x())
        candidates = sorted([("black", abs(x-bx)),
                              ("gamma", abs(x-gx)),
                              ("white", abs(x-wx))],
                             key=lambda t: t[1])
        name, dist = candidates[0]
        return name if dist <= 12 else None

    # ── mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = self._handle_at(int(ev.position().x()),
                                         int(ev.position().y()))

    def mouseMoveEvent(self, ev):
        x = int(ev.position().x())
        y = int(ev.position().y())
        if self._drag:
            if self._drag == "black":
                v = max(0, min(self._white - 1, self._x_to_val(x)))
                if v != self._black:
                    self._black = v
                    self.black_changed.emit(v)
                    self.update()
            elif self._drag == "white":
                v = max(self._black + 1, min(255, self._x_to_val(x)))
                if v != self._white:
                    self._white = v
                    self.white_changed.emit(v)
                    self.update()
            elif self._drag == "gamma":
                g = self._x_to_gamma(x)
                self._gamma = g
                self.gamma_changed.emit(g)
                self.update()
        else:
            cur = (Qt.CursorShape.SizeHorCursor
                   if self._handle_at(x, y)
                   else Qt.CursorShape.ArrowCursor)
            self.setCursor(cur)

    def mouseReleaseEvent(self, _):
        self._drag = None


# ── output levels gradient + two handles ─────────────────────────────────────

class _OutputWidget(QWidget):
    """Gradient bar with draggable black / white output handles."""

    GRAD_H = 14
    HAND_H = 16
    PAD    = 6

    out_min_changed = pyqtSignal(int)
    out_max_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._out_min = 0
        self._out_max = 255
        self._drag    = None
        self.setFixedHeight(self.GRAD_H + self.HAND_H + 2)
        self.setMinimumWidth(300)
        self.setMouseTracking(True)

    def set_values(self, out_min: int, out_max: int):
        self._out_min = out_min
        self._out_max = out_max
        self.update()

    def _val_to_x(self, v: int) -> int:
        span = self.width() - 2 * self.PAD
        return self.PAD + int(v * span / 255)

    def _x_to_val(self, x: int) -> int:
        span = max(1, self.width() - 2 * self.PAD)
        return int(max(0, min(255, (x - self.PAD) * 255 / span)))

    def paintEvent(self, _):
        p  = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W  = self.width()

        grad = QLinearGradient(0, 0, W, 0)
        grad.setColorAt(0.0, Qt.GlobalColor.black)
        grad.setColorAt(1.0, Qt.GlobalColor.white)
        p.fillRect(0, 0, W, self.GRAD_H, QBrush(grad))

        hy  = self.GRAD_H
        mnx = self._val_to_x(self._out_min)
        mxx = self._val_to_x(self._out_max)

        def _tri(cx, col, outline):
            pts = QPolygon([QPoint(cx, hy),
                            QPoint(cx-6, hy+self.HAND_H),
                            QPoint(cx+6, hy+self.HAND_H)])
            p.setPen(QPen(outline, 1))
            p.setBrush(QBrush(col))
            p.drawPolygon(pts)

        _tri(mnx, QColor(20,  20,  20),  QColor(160, 160, 160))
        _tri(mxx, QColor(240, 240, 240), QColor(80,  80,  80))
        p.end()

    def _handle_at(self, x: int, y: int):
        if y < self.GRAD_H - 4:
            return None
        mnx = self._val_to_x(self._out_min)
        mxx = self._val_to_x(self._out_max)
        dm  = abs(x - mnx)
        dx  = abs(x - mxx)
        if min(dm, dx) > 12:
            return None
        return "min" if dm <= dx else "max"

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = self._handle_at(int(ev.position().x()),
                                         int(ev.position().y()))

    def mouseMoveEvent(self, ev):
        x = int(ev.position().x())
        y = int(ev.position().y())
        if self._drag:
            v = self._x_to_val(x)
            if self._drag == "min":
                v = max(0, min(self._out_max - 1, v))
                if v != self._out_min:
                    self._out_min = v
                    self.out_min_changed.emit(v)
                    self.update()
            else:
                v = max(self._out_min + 1, min(255, v))
                if v != self._out_max:
                    self._out_max = v
                    self.out_max_changed.emit(v)
                    self.update()
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor
                           if self._handle_at(x, y)
                           else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, _):
        self._drag = None


# ── levels dialog ─────────────────────────────────────────────────────────────

class LevelsDialog(QDialog):
    """Non-destructive Levels dialog with real-time canvas preview."""

    _DEBOUNCE_MS = 40

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("adj.levels.title"))
        self.setModal(True)
        self.setMinimumWidth(460)

        self._image          = image
        self._original       = image.copy()
        self._orig_argb32    = _to_argb32(self._original)

        self._black   = 0
        self._gamma   = 1.0
        self._white   = 255
        self._out_min = 0
        self._out_max = 255

        self._histogram = compute_histogram(self._original)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._DEBOUNCE_MS)
        self._timer.timeout.connect(self._apply_preview)

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(6)

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color: #a6adc8; font-size: 12px;")
            return l

        # ── Input spinboxes ────────────────────────────────────────────────
        lo.addWidget(_lbl(tr("adj.levels.input")))

        spin_row = QHBoxLayout()
        self._black_sp = QSpinBox()
        self._black_sp.setRange(0, 254);  self._black_sp.setValue(0)
        self._black_sp.setFixedWidth(54)

        self._gamma_sp = QDoubleSpinBox()
        self._gamma_sp.setRange(0.10, 9.99)
        self._gamma_sp.setValue(1.00)
        self._gamma_sp.setSingleStep(0.05)
        self._gamma_sp.setDecimals(2)
        self._gamma_sp.setFixedWidth(62)

        self._white_sp = QSpinBox()
        self._white_sp.setRange(1, 255);  self._white_sp.setValue(255)
        self._white_sp.setFixedWidth(54)

        spin_row.addWidget(self._black_sp)
        spin_row.addStretch()
        spin_row.addWidget(self._gamma_sp)
        spin_row.addStretch()
        spin_row.addWidget(self._white_sp)
        lo.addLayout(spin_row)

        # ── Histogram + input handles ──────────────────────────────────────
        self._hist_w = _HistogramWidget(self._histogram)
        lo.addWidget(self._hist_w)

        # ── Output spinboxes ───────────────────────────────────────────────
        lo.addSpacing(4)
        lo.addWidget(_lbl(tr("adj.levels.output")))

        out_row = QHBoxLayout()
        self._out_min_sp = QSpinBox()
        self._out_min_sp.setRange(0, 254);  self._out_min_sp.setValue(0)
        self._out_min_sp.setFixedWidth(54)

        self._out_max_sp = QSpinBox()
        self._out_max_sp.setRange(1, 255);  self._out_max_sp.setValue(255)
        self._out_max_sp.setFixedWidth(54)

        out_row.addWidget(self._out_min_sp)
        out_row.addStretch()
        out_row.addWidget(self._out_max_sp)
        lo.addLayout(out_row)

        # ── Output gradient + handles ──────────────────────────────────────
        self._out_w = _OutputWidget()
        lo.addWidget(self._out_w)

        # ── Buttons ────────────────────────────────────────────────────────
        lo.addSpacing(4)
        btn_row = QHBoxLayout()

        auto_btn = QPushButton(tr("adj.levels.auto"))
        auto_btn.setObjectName("smallBtn")
        auto_btn.setFixedWidth(72)
        auto_btn.clicked.connect(self._auto)

        dlg_btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        dlg_btns.accepted.connect(self.accept)
        dlg_btns.rejected.connect(self.reject)

        btn_row.addWidget(auto_btn)
        btn_row.addStretch()
        btn_row.addWidget(dlg_btns)
        lo.addLayout(btn_row)

        # ── Signal wiring ──────────────────────────────────────────────────
        # histogram handles → spinboxes (one-way, blocked to avoid loops)
        self._hist_w.black_changed.connect(self._from_hist_black)
        self._hist_w.gamma_changed.connect(self._from_hist_gamma)
        self._hist_w.white_changed.connect(self._from_hist_white)

        # spinboxes → histogram widget + timer
        self._black_sp.valueChanged.connect(self._from_sp_black)
        self._gamma_sp.valueChanged.connect(self._from_sp_gamma)
        self._white_sp.valueChanged.connect(self._from_sp_white)

        # output handles → spinboxes
        self._out_w.out_min_changed.connect(self._from_out_min)
        self._out_w.out_max_changed.connect(self._from_out_max)

        # output spinboxes → output widget
        self._out_min_sp.valueChanged.connect(self._from_sp_out_min)
        self._out_max_sp.valueChanged.connect(self._from_sp_out_max)

    # ── slot helpers (widget handles → spinboxes) ─────────────────────────────

    def _from_hist_black(self, v):
        self._black = v
        self._black_sp.blockSignals(True);  self._black_sp.setValue(v)
        self._black_sp.blockSignals(False); self._timer.start()

    def _from_hist_gamma(self, v):
        self._gamma = v
        self._gamma_sp.blockSignals(True);  self._gamma_sp.setValue(round(v, 2))
        self._gamma_sp.blockSignals(False); self._timer.start()

    def _from_hist_white(self, v):
        self._white = v
        self._white_sp.blockSignals(True);  self._white_sp.setValue(v)
        self._white_sp.blockSignals(False); self._timer.start()

    def _from_out_min(self, v):
        self._out_min = v
        self._out_min_sp.blockSignals(True);  self._out_min_sp.setValue(v)
        self._out_min_sp.blockSignals(False); self._timer.start()

    def _from_out_max(self, v):
        self._out_max = v
        self._out_max_sp.blockSignals(True);  self._out_max_sp.setValue(v)
        self._out_max_sp.blockSignals(False); self._timer.start()

    # ── slot helpers (spinboxes → widget) ─────────────────────────────────────

    def _from_sp_black(self, v):
        self._black = min(v, self._white - 1)
        self._hist_w.set_values(self._black, self._gamma, self._white)
        self._timer.start()

    def _from_sp_gamma(self, v):
        self._gamma = v
        self._hist_w.set_values(self._black, self._gamma, self._white)
        self._timer.start()

    def _from_sp_white(self, v):
        self._white = max(v, self._black + 1)
        self._hist_w.set_values(self._black, self._gamma, self._white)
        self._timer.start()

    def _from_sp_out_min(self, v):
        self._out_min = min(v, self._out_max - 1)
        self._out_w.set_values(self._out_min, self._out_max)
        self._timer.start()

    def _from_sp_out_max(self, v):
        self._out_max = max(v, self._out_min + 1)
        self._out_w.set_values(self._out_min, self._out_max)
        self._timer.start()

    # ── preview + apply ───────────────────────────────────────────────────────

    def _apply_preview(self):
        res = apply_levels(
            self._orig_argb32,
            self._black, self._gamma, self._white,
            self._out_min, self._out_max)
            
        if not getattr(self, "_is_adj_layer", False):
            p = QPainter(self._image)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.drawImage(0, 0, res)
            p.end()
            
        if hasattr(self, "_canvas_refresh"): self._canvas_refresh()
        elif self.parent() and hasattr(self.parent(), "_canvas_refresh"): self.parent()._canvas_refresh()

    # ── Auto ──────────────────────────────────────────────────────────────────

    def _auto(self):
        """Clip 0.1 % at each end of the luminance histogram."""
        total = sum(self._histogram)
        clip  = max(1, int(total * 0.001))

        cum = 0
        auto_black = 0
        for i, c in enumerate(self._histogram):
            cum += c
            if cum >= clip:
                auto_black = i
                break

        cum = 0
        auto_white = 255
        for i in range(255, -1, -1):
            cum += self._histogram[i]
            if cum >= clip:
                auto_white = i
                break

        auto_black = min(auto_black, auto_white - 1)
        self._set_all(auto_black, 1.0, auto_white, self._out_min, self._out_max)

    def _set_all(self, black, gamma, white, out_min, out_max):
        self._black, self._gamma, self._white = black, gamma, white
        self._out_min, self._out_max          = out_min, out_max

        for sp, v in [(self._black_sp, black),
                      (self._white_sp, white),
                      (self._out_min_sp, out_min),
                      (self._out_max_sp, out_max)]:
            sp.blockSignals(True);  sp.setValue(v);  sp.blockSignals(False)

        self._gamma_sp.blockSignals(True)
        self._gamma_sp.setValue(round(gamma, 2))
        self._gamma_sp.blockSignals(False)

        self._hist_w.set_values(black, gamma, white)
        self._out_w.set_values(out_min, out_max)
        self._timer.start()

    # ── cancel ────────────────────────────────────────────────────────────────

    def reject(self):
        self._timer.stop()
        if getattr(self, "_is_adj_layer", False) and hasattr(self, "_layer"):
            self._layer.adjustment_data = getattr(self, "_orig_adj_data", {})
        else:
            p = QPainter(self._image)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.drawImage(0, 0, self._original)
            p.end()
            
        if hasattr(self, "_canvas_refresh"): self._canvas_refresh()
        elif self.parent() and hasattr(self.parent(), "_canvas_refresh"): self.parent()._canvas_refresh()
        super().reject()
