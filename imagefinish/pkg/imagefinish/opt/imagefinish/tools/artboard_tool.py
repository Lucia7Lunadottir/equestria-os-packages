from PyQt6.QtCore import QPoint, Qt, QRect
from PyQt6.QtGui import QImage
from tools.base_tool import BaseTool
from core.locale import tr

class ArtboardTool(BaseTool):
    name = "Artboard"
    icon = "🔲"
    shortcut = "V"

    def __init__(self):
        super().__init__()
        self._start = None
        self._end = None
        self._dragging = False

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        self._start = pos
        self._end = pos
        self._dragging = True

    def on_move(self, pos: QPoint, doc, fg, bg, opts):
        if self._dragging:
            self._end = pos

    def on_release(self, pos: QPoint, doc, fg, bg, opts):
        if not self._dragging: return
        self._dragging = False
        self._end = pos
        rect = QRect(self._start, self._end).normalized()
        if rect.width() < 10 or rect.height() < 10:
            self._start = None
            return

        count = sum(1 for l in doc.layers if getattr(l, "layer_type", "") == "artboard")
        
        if count == 0:
            # Собираем все текущие слои в базовый Артборд 1
            bg_art = doc.add_layer(f"{tr('layer.name.artboard')} 1")
            bg_art.layer_type = "artboard"
            bg_art.parent_id = None
            bg_art.artboard_rect = QRect(0, 0, doc.width, doc.height)
            bg_art.image = QImage(1, 1, QImage.Format.Format_ARGB32)
            bg_art.image.fill(Qt.GlobalColor.transparent)
            
            for l in doc.layers:
                if l is not bg_art and getattr(l, "layer_type", "raster") != "artboard":
                    if not getattr(l, "parent_id", None):
                        l.parent_id = bg_art.layer_id
            
            count = 1

        layer = doc.add_layer(f"{tr('layer.name.artboard')} {count + 1}")
        layer.layer_type = "artboard"
        layer.parent_id = None
        layer.artboard_rect = rect
        layer.image = QImage(1, 1, QImage.Format.Format_ARGB32)
        layer.image.fill(Qt.GlobalColor.transparent)
        
        doc.fit_to_artboards()
        self._start = None

    def artboard_preview(self):
        if self._dragging and self._start and self._end: return QRect(self._start, self._end).normalized()
        return None

    def needs_history_push(self): return True
    def cursor(self): return Qt.CursorShape.CrossCursor