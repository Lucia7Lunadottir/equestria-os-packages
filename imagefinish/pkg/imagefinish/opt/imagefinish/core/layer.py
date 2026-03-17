from PyQt6.QtGui import QImage, QColor, QPainterPath
from PyQt6.QtCore import Qt, QPoint, QRect, QRectF
import uuid


class Layer:
    """Represents a single layer in the document."""

    BLEND_MODES = ["Normal", "Multiply", "Screen", "Overlay"]

    def __init__(self, name: str, width: int, height: int, fill_color: QColor = None):
        self.name = name
        self.layer_id = str(uuid.uuid4())
        self.parent_id: str | None = None
        self.expanded: bool = True
        self.link_id: str | None = None
        self.visible: bool = True
        self.locked: bool = False
        self.lock_alpha: bool = False
        self.lock_pixels: bool = False
        self.lock_position: bool = False
        self.lock_artboard: bool = False
        self.mask: QImage | None = None
        self.mask_enabled: bool = True
        self.editing_mask: bool = False
        self.vector_mask: QPainterPath | None = None
        self.vector_mask_enabled: bool = True
        self.clipping: bool = False
        self.is_quick_mask: bool = False
        self.opacity: float = 1.0
        self.blend_mode: str = "Normal"
        self.offset: QPoint = QPoint(0, 0)

        # "raster" | "text" | "vector" | "adjustment" | "fill" | "smart_object" | "artboard" | "group" | "frame"
        self.layer_type: str = "raster"

        self.image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        if fill_color:
            self.image.fill(fill_color)
        else:
            self.image.fill(Qt.GlobalColor.transparent)

        self.text_data: dict | None = None        # text layer params
        self.shape_data: dict | None = None       # vector layer params
        self.adjustment_data: dict | None = None  # adjustment layer params
        self.fill_data: dict | None = None        # fill layer params
        self.smart_data: dict | None = None       # smart object (stores original QImage)
        self.layer_styles: dict | None = None     # layer styles / blending options
        self.artboard_rect: QRect | None = None   # For Artboards
        self.frame_data: dict | None = None       # {"shape": "rect"|"ellipse", "rect": QRectF}

    # ------------------------------------------------------------------
    def copy(self) -> "Layer":
        clone = Layer.__new__(Layer)
        clone.name = self.name
        clone.layer_id = getattr(self, "layer_id", str(uuid.uuid4()))
        clone.parent_id = getattr(self, "parent_id", None)
        clone.expanded = getattr(self, "expanded", True)
        clone.link_id = getattr(self, "link_id", None)
        clone.visible = self.visible
        clone.locked = self.locked
        clone.lock_alpha = getattr(self, "lock_alpha", False)
        clone.lock_pixels = getattr(self, "lock_pixels", False)
        clone.lock_position = getattr(self, "lock_position", False)
        clone.lock_artboard = getattr(self, "lock_artboard", False)
        if getattr(self, "mask", None) is not None:
            clone.mask = self.mask.copy()
        else:
            clone.mask = None
        clone.mask_enabled = getattr(self, "mask_enabled", True)
        clone.editing_mask = getattr(self, "editing_mask", False)
        if getattr(self, "vector_mask", None) is not None:
            clone.vector_mask = QPainterPath(self.vector_mask)
        else:
            clone.vector_mask = None
        clone.vector_mask_enabled = getattr(self, "vector_mask_enabled", True)
        clone.clipping = getattr(self, "clipping", False)
        clone.is_quick_mask = getattr(self, "is_quick_mask", False)
        clone.opacity = self.opacity
        clone.blend_mode = self.blend_mode
        clone.offset = QPoint(self.offset)
        clone.image = self.image.copy()
        clone.layer_type = getattr(self, "layer_type", "raster")
        if getattr(self, "artboard_rect", None) is not None:
            clone.artboard_rect = QRect(self.artboard_rect)
        else:
            clone.artboard_rect = None
        fd = getattr(self, "frame_data", None)
        if fd:
            clone.frame_data = {"shape": fd.get("shape", "rect"), "rect": QRectF(fd.get("rect", QRectF()))}
        else:
            clone.frame_data = None
        td = getattr(self, "text_data", None)
        clone.text_data = dict(td) if td else None
        sd = getattr(self, "shape_data", None)
        clone.shape_data = dict(sd) if sd else None
        ad = getattr(self, "adjustment_data", None)
        clone.adjustment_data = dict(ad) if ad else None
        fd = getattr(self, "fill_data", None)
        clone.fill_data = dict(fd) if fd else None
        smd = getattr(self, "smart_data", None)
        if smd:
            clone.smart_data = {"original": smd["original"].copy()}
        else:
            clone.smart_data = None
            
        import copy
        clone.layer_styles = copy.deepcopy(getattr(self, "layer_styles", None))
        return clone

    def to_dict(self):
        from PyQt6.QtCore import QBuffer, QIODevice, QByteArray
        def img_to_bytes(img):
            if not img or img.isNull(): return None
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            return ba.data()

        d = {
            "name": self.name,
            "layer_type": getattr(self, "layer_type", "raster"),
            "visible": self.visible,
            "locked": self.locked,
            "lock_alpha": getattr(self, "lock_alpha", False),
            "lock_pixels": getattr(self, "lock_pixels", False),
            "lock_position": getattr(self, "lock_position", False),
            "opacity": self.opacity,
            "blend_mode": self.blend_mode,
            "offset": (self.offset.x(), self.offset.y()),
            "image": img_to_bytes(self.image),
            "mask": img_to_bytes(self.mask),
            "mask_enabled": getattr(self, "mask_enabled", True),
            "layer_styles": getattr(self, "layer_styles", None),
            "adjustment_data": getattr(self, "adjustment_data", None),
            "fill_data": getattr(self, "fill_data", None),
            "text_data": getattr(self, "text_data", None),
            "shape_data": getattr(self, "shape_data", None),
            "frame_data": getattr(self, "frame_data", None),
            "clipping": getattr(self, "clipping", False),
            "expanded": getattr(self, "expanded", True)
        }
        if getattr(self, "smart_data", None) and "original" in self.smart_data:
            d["smart_data_original"] = img_to_bytes(self.smart_data["original"])
        return d

    @classmethod
    def from_dict(cls, d, w, h):
        from PyQt6.QtGui import QImage
        from PyQt6.QtCore import QPoint, QRect, QRectF
        def bytes_to_img(b):
            if not b: return None
            img = QImage()
            img.loadFromData(b, "PNG")
            return img
            
        layer = cls(d["name"], w, h)
        layer.layer_type = d.get("layer_type", "raster")
        layer.visible = d.get("visible", True)
        layer.locked = d.get("locked", False)
        layer.lock_alpha = d.get("lock_alpha", False)
        layer.lock_pixels = d.get("lock_pixels", False)
        layer.lock_position = d.get("lock_position", False)
        layer.opacity = d.get("opacity", 1.0)
        layer.blend_mode = d.get("blend_mode", "Normal")
        layer.clipping = d.get("clipping", False)
        layer.expanded = d.get("expanded", True)
        ox, oy = d.get("offset", (0,0))
        layer.offset = QPoint(ox, oy)
        
        img = bytes_to_img(d.get("image"))
        if img: layer.image = img
        
        layer.mask = bytes_to_img(d.get("mask"))
        layer.mask_enabled = d.get("mask_enabled", True)
        
        layer.layer_styles = d.get("layer_styles", None)
        layer.adjustment_data = d.get("adjustment_data", None)
        layer.fill_data = d.get("fill_data", None)
        layer.text_data = d.get("text_data", None)
        layer.shape_data = d.get("shape_data", None)
        layer.frame_data = d.get("frame_data", None)
        
        smd_b = d.get("smart_data_original")
        if smd_b:
            layer.smart_data = {"original": bytes_to_img(smd_b)}
            
        return layer

    def width(self) -> int:
        return self.image.width()

    def height(self) -> int:
        return self.image.height()

    def __repr__(self) -> str:
        return f"<Layer '{self.name}' {self.width()}x{self.height()} visible={self.visible}>"
