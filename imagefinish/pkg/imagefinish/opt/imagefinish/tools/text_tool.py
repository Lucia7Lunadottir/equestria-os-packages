from PyQt6.QtCore import Qt
from PyQt6.QtGui import (QColor, QPainter, QImage, QPainterPath,
                         QFont, QFontMetrics, QBrush, QPen as _QPen, QPixmap)
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QPlainTextEdit,
                             QDialogButtonBox, QLabel)
from tools.base_tool import BaseTool
from core.locale import tr


# ── Font helpers ───────────────────────────────────────────────────────────────

def _build_font(opts: dict) -> QFont:
    font = QFont(opts.get("font_family", "Sans Serif"),
                 int(opts.get("font_size", 24)))
    font.setBold(bool(opts.get("font_bold", False)))
    font.setItalic(bool(opts.get("font_italic", False)))
    font.setUnderline(bool(opts.get("font_underline", False)))
    font.setStrikeOut(bool(opts.get("font_strikeout", False)))
    return font


def _render_text(image, x: int, y: int, text: str, opts: dict, clip_path=None):
    font        = _build_font(opts)
    metrics     = QFontMetrics(font)
    line_h      = metrics.lineSpacing()
    lines       = text.split("\n")
    text_color   = opts.get("text_color",       QColor(0, 0, 0))
    stroke_w     = int(opts.get("text_stroke_w",   0))
    stroke_color = opts.get("text_stroke_color", QColor(0, 0, 0))
    shadow       = bool(opts.get("text_shadow",  False))
    shadow_color = opts.get("text_shadow_color", QColor(0, 0, 0, 160))
    sdx          = int(opts.get("text_shadow_dx", 3))
    sdy          = int(opts.get("text_shadow_dy", 3))

    def make_path(dx=0, dy=0) -> QPainterPath:
        path = QPainterPath()
        baseline = metrics.ascent()
        for i, line in enumerate(lines):
            if line:
                path.addText(x + dx, y + dy + baseline + i * line_h, font, line)
        return path

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if clip_path and not clip_path.isEmpty():
        painter.setClipPath(clip_path)
    if shadow:
        painter.fillPath(make_path(sdx, sdy), QBrush(shadow_color))
    main_path = make_path()
    if stroke_w > 0:
        pen = _QPen(stroke_color, stroke_w * 2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(main_path, pen)
    painter.fillPath(main_path, QBrush(text_color))
    painter.end()


def _render_text_vertical(image, x: int, y: int, text: str, opts: dict, clip_path=None):
    font    = _build_font(opts)
    metrics = QFontMetrics(font)
    col_w   = metrics.maxWidth() + 4
    char_h  = metrics.height()
    cols    = text.split("\n")
    text_color   = opts.get("text_color",       QColor(0, 0, 0))
    stroke_w     = int(opts.get("text_stroke_w",   0))
    stroke_color = opts.get("text_stroke_color", QColor(0, 0, 0))
    shadow       = bool(opts.get("text_shadow",  False))
    shadow_color = opts.get("text_shadow_color", QColor(0, 0, 0, 160))
    sdx          = int(opts.get("text_shadow_dx", 3))
    sdy          = int(opts.get("text_shadow_dy", 3))

    def make_path(dx=0, dy=0) -> QPainterPath:
        path = QPainterPath()
        for ci, col_text in enumerate(cols):
            cx = x + dx + ci * col_w
            for ri, ch in enumerate(col_text):
                if ch.strip():
                    cy = y + dy + metrics.ascent() + ri * char_h
                    path.addText(cx, cy, font, ch)
        return path

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if clip_path and not clip_path.isEmpty():
        painter.setClipPath(clip_path)
    if shadow:
        painter.fillPath(make_path(sdx, sdy), QBrush(shadow_color))
    main_path = make_path()
    if stroke_w > 0:
        pen = _QPen(stroke_color, stroke_w * 2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(main_path, pen)
    painter.fillPath(main_path, QBrush(text_color))
    painter.end()


def _text_path_h(pos, text: str, opts: dict) -> QPainterPath:
    font     = _build_font(opts)
    metrics  = QFontMetrics(font)
    line_h   = metrics.lineSpacing()
    lines    = text.split("\n")
    x, y     = pos.x(), pos.y()
    path     = QPainterPath()
    baseline = metrics.ascent()
    for i, line in enumerate(lines):
        if line:
            path.addText(x, y + baseline + i * line_h, font, line)
    return path


def _text_path_v(pos, text: str, opts: dict) -> QPainterPath:
    font    = _build_font(opts)
    metrics = QFontMetrics(font)
    col_w   = metrics.maxWidth() + 4
    char_h  = metrics.height()
    cols    = text.split("\n")
    x, y    = pos.x(), pos.y()
    path    = QPainterPath()
    for ci, col_text in enumerate(cols):
        cx = x + ci * col_w
        for ri, ch in enumerate(col_text):
            if ch.strip():
                cy = y + metrics.ascent() + ri * char_h
                path.addText(cx, cy, font, ch)
    return path


# ── Text dialog ────────────────────────────────────────────────────────────────

class _TextDialog(QDialog):
    _PREVIEW_H = 80
    _PREVIEW_W = 480

    def __init__(self, initial_text: str = "", opts: dict = None,
                 layer_name: str = None, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QFontComboBox, QSpinBox, QPushButton, QHBoxLayout
        title = tr("text_dlg.edit_title", name=layer_name) if layer_name else tr("text_dlg.new_title")
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self._base_opts = dict(opts) if opts else {}

        lo = QVBoxLayout(self)
        lo.setSpacing(6)

        font_row = QHBoxLayout()
        font_row.setSpacing(6)

        self._font_combo = QFontComboBox()
        self._font_combo.setFixedWidth(300)
        self._font_combo.setCurrentFont(QFont(self._base_opts.get("font_family", "Sans Serif")))

        self._size_sp = QSpinBox()
        self._size_sp.setRange(4, 500)
        self._size_sp.setValue(int(self._base_opts.get("font_size", 24)))
        self._size_sp.setFixedWidth(60)
        self._size_sp.setSuffix(" pt")

        bold_f = QFont(); bold_f.setBold(True)
        ital_f = QFont(); ital_f.setItalic(True)

        self._btn_b = QPushButton("B")
        self._btn_b.setFont(bold_f)
        self._btn_b.setCheckable(True)
        self._btn_b.setChecked(bool(self._base_opts.get("font_bold", False)))
        self._btn_b.setFixedSize(28, 28)

        self._btn_i = QPushButton("I")
        self._btn_i.setFont(ital_f)
        self._btn_i.setCheckable(True)
        self._btn_i.setChecked(bool(self._base_opts.get("font_italic", False)))
        self._btn_i.setFixedSize(28, 28)

        font_row.addWidget(self._font_combo)
        font_row.addWidget(self._size_sp)
        font_row.addWidget(self._btn_b)
        font_row.addWidget(self._btn_i)
        font_row.addStretch()
        lo.addLayout(font_row)

        self._preview = QLabel()
        self._preview.setFixedHeight(self._PREVIEW_H)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            "background:#ffffff; border:1px solid #45475a; border-radius:4px;")
        lo.addWidget(self._preview)

        self._edit = QPlainTextEdit(initial_text)
        self._edit.setPlaceholderText(tr("text_dlg.placeholder"))
        lo.addWidget(self._edit, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lo.addWidget(btns)

        self._font_combo.currentFontChanged.connect(self._update_preview)
        self._size_sp.valueChanged.connect(self._update_preview)
        self._btn_b.toggled.connect(self._update_preview)
        self._btn_i.toggled.connect(self._update_preview)
        self._edit.textChanged.connect(self._update_preview)

        self._update_preview()
        self._edit.setFocus()

    def _current_opts(self) -> dict:
        opts = dict(self._base_opts)
        opts["font_family"] = self._font_combo.currentFont().family()
        opts["font_size"]   = self._size_sp.value()
        opts["font_bold"]   = self._btn_b.isChecked()
        opts["font_italic"] = self._btn_i.isChecked()
        return opts

    def _update_preview(self, *_):
        text = self._edit.toPlainText() or tr("text_dlg.preview")
        w, h = self._PREVIEW_W, self._PREVIEW_H - 2
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(255, 255, 255))
        cur_opts = self._current_opts()
        cur_opts["font_size"] = min(cur_opts["font_size"], h - 16)
        _render_text(img, 8, 8, text, cur_opts)
        self._preview.setPixmap(QPixmap.fromImage(img))

    def get_text(self) -> str:
        return self._edit.toPlainText()

    def get_font_opts(self) -> dict:
        return {
            "font_family": self._font_combo.currentFont().family(),
            "font_size":   self._size_sp.value(),
            "font_bold":   self._btn_b.isChecked(),
            "font_italic": self._btn_i.isChecked(),
        }


# ── Text tools ─────────────────────────────────────────────────────────────────

class TextTool(BaseTool):
    name = "Text"
    icon = "T"
    shortcut = "T"
    needs_immediate_commit = True

    def __init__(self):
        self._parent_widget = None

    def on_press(self, pos, doc, fg, bg, opts):
        layer      = doc.get_active_layer()
        re_edit    = layer and getattr(layer, "text_data", None) is not None
        layer_name = layer.name if re_edit else None
        initial    = layer.text_data.get("text", "") if re_edit else ""

        dlg = _TextDialog(initial, opts, layer_name, self._parent_widget)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = dlg.get_text().strip()
        if not text:
            return

        opts.update(dlg.get_font_opts())

        if re_edit:
            layer.image.fill(Qt.GlobalColor.transparent)
            td = layer.text_data
            _render_text(layer.image, td["x"], td["y"], text, opts,
                         doc.selection if (doc.selection and not doc.selection.isEmpty()) else None)
            layer.text_data = {**td, "text": text, **self._snap_opts(opts)}
        else:
            from core.layer import Layer as _Layer
            n = sum(1 for l in doc.layers if l.text_data) + 1
            new_layer = _Layer(f"Text {n}", doc.width, doc.height)
            new_layer.layer_type = "text"
            _render_text(new_layer.image, pos.x(), pos.y(), text, opts,
                         doc.selection if (doc.selection and not doc.selection.isEmpty()) else None)
            new_layer.text_data = {"text": text, "x": pos.x(), "y": pos.y(),
                                   **self._snap_opts(opts)}
            doc.layers.append(new_layer)
            doc.active_layer_index = len(doc.layers) - 1

    @staticmethod
    def _snap_opts(opts: dict) -> dict:
        return {k: opts[k] for k in (
            "font_family", "font_size", "font_bold", "font_italic",
            "font_underline", "font_strikeout",
            "text_color", "text_stroke_w", "text_stroke_color",
            "text_shadow", "text_shadow_color", "text_shadow_dx", "text_shadow_dy",
        ) if k in opts}

    def needs_history_push(self) -> bool:
        return True

    def cursor(self):
        return Qt.CursorShape.IBeamCursor


class VerticalTypeTool(BaseTool):
    name = "TextV"
    icon = "Tv"
    shortcut = ""
    needs_immediate_commit = True

    def __init__(self):
        self._parent_widget = None

    def on_press(self, pos, doc, fg, bg, opts):
        layer      = doc.get_active_layer()
        re_edit    = (layer and getattr(layer, "text_data", None) is not None
                      and layer.text_data.get("vertical", False))
        layer_name = layer.name if re_edit else None
        initial    = layer.text_data.get("text", "") if re_edit else ""

        dlg = _TextDialog(initial, opts, layer_name, self._parent_widget)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = dlg.get_text().strip()
        if not text:
            return

        opts.update(dlg.get_font_opts())
        clip = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None

        if re_edit:
            layer.image.fill(Qt.GlobalColor.transparent)
            td = layer.text_data
            _render_text_vertical(layer.image, td["x"], td["y"], text, opts, clip)
            layer.text_data = {**td, "text": text, "vertical": True,
                               **TextTool._snap_opts(opts)}
        else:
            from core.layer import Layer as _Layer
            n = sum(1 for l in doc.layers if l.text_data) + 1
            new_layer = _Layer(f"Text {n}", doc.width, doc.height)
            new_layer.layer_type = "text"
            _render_text_vertical(new_layer.image, pos.x(), pos.y(), text, opts, clip)
            new_layer.text_data = {"text": text, "x": pos.x(), "y": pos.y(),
                                   "vertical": True, **TextTool._snap_opts(opts)}
            doc.layers.append(new_layer)
            doc.active_layer_index = len(doc.layers) - 1

    def needs_history_push(self):
        return True

    def cursor(self):
        return Qt.CursorShape.IBeamCursor


class HorizontalTypeMaskTool(BaseTool):
    name = "TextHMask"
    icon = "Tm"
    shortcut = ""
    needs_immediate_commit = True

    def __init__(self):
        self._parent_widget = None

    def on_press(self, pos, doc, fg, bg, opts):
        dlg = _TextDialog("", opts, None, self._parent_widget)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = dlg.get_text().strip()
        if not text:
            return
        opts.update(dlg.get_font_opts())
        doc.selection = _text_path_h(pos, text, opts)

    def needs_history_push(self):
        return False

    def cursor(self):
        return Qt.CursorShape.IBeamCursor


class VerticalTypeMaskTool(BaseTool):
    name = "TextVMask"
    icon = "Vm"
    shortcut = ""
    needs_immediate_commit = True

    def __init__(self):
        self._parent_widget = None

    def on_press(self, pos, doc, fg, bg, opts):
        dlg = _TextDialog("", opts, None, self._parent_widget)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = dlg.get_text().strip()
        if not text:
            return
        opts.update(dlg.get_font_opts())
        doc.selection = _text_path_v(pos, text, opts)

    def needs_history_push(self):
        return False

    def cursor(self):
        return Qt.CursorShape.IBeamCursor
