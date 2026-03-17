from PyQt6.QtGui import QImage, QPainter, QColor, QPainterPath, QLinearGradient, QBrush, qAlpha, QPolygonF, QTransform, QPen
from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QPointF
from .layer import Layer


def _get_composition_mode(mode_str: str) -> QPainter.CompositionMode:
    mapping = {
        "SourceOver": QPainter.CompositionMode.CompositionMode_SourceOver,
        "Multiply": QPainter.CompositionMode.CompositionMode_Multiply,
        "Screen": QPainter.CompositionMode.CompositionMode_Screen,
        "Overlay": QPainter.CompositionMode.CompositionMode_Overlay,
        "Darken": QPainter.CompositionMode.CompositionMode_Darken,
        "Lighten": QPainter.CompositionMode.CompositionMode_Lighten,
        "ColorDodge": QPainter.CompositionMode.CompositionMode_ColorDodge,
        "ColorBurn": QPainter.CompositionMode.CompositionMode_ColorBurn,
        "HardLight": QPainter.CompositionMode.CompositionMode_HardLight,
        "SoftLight": QPainter.CompositionMode.CompositionMode_SoftLight,
        "Difference": QPainter.CompositionMode.CompositionMode_Difference,
        "Exclusion": QPainter.CompositionMode.CompositionMode_Exclusion,
    }
    return mapping.get(mode_str, QPainter.CompositionMode.CompositionMode_SourceOver)

def _apply_layer_adjustment(image: QImage, layer) -> QImage:
    d = layer.adjustment_data or {}
    t = d.get("type", "")
    
    def get_v(keywords, default):
        for kw in keywords:
            if kw in d: return d[kw]
        best_val = default
        for k, v in d.items():
            if not isinstance(v, (int, float)): continue
            kl = k.lower()
            if any(kw in kl for kw in keywords):
                if "max" in keywords[0] and "min" in kl: continue
                if "min" in keywords[0] and "max" in kl: continue
                if "out" in keywords[0] and "in" in kl: continue
                if "in" in keywords[0] and "out" in kl: continue
                best_val = v
                if isinstance(v, float): return v
        return best_val

    try:
        if t == "brightness_contrast":
            from ui.adjustments_dialog import apply_brightness_contrast
            return apply_brightness_contrast(image, int(get_v(["brightness", "bright"], 0)), int(get_v(["contrast", "contr"], 0)))
        elif t == "hue_saturation":
            from ui.adjustments_dialog import apply_hue_saturation
            return apply_hue_saturation(image, int(get_v(["hue"], 0)), int(get_v(["saturation", "sat"], 0)), int(get_v(["lightness", "light"], 0)))
        elif t == "invert":
            from ui.adjustments_dialog import apply_invert
            return apply_invert(image)
        elif t == "levels":
            from ui.levels_dialog import apply_levels
            in_min = int(get_v(["in_min", "in_black", "in_low", "black_sp"], 0))
            in_max = int(get_v(["in_max", "in_white", "in_high", "white_sp"], 255))
            gamma  = float(get_v(["gamma", "mid", "gamma_sp"], 1.0))
            out_min = int(get_v(["out_min", "out_black", "out_low", "out_min_sp"], 0))
            out_max = int(get_v(["out_max", "out_white", "out_high", "out_max_sp"], 255))
            
            if gamma > 5.0: gamma /= 100.0
            if gamma <= 0.0: gamma = 1.0
            if in_max <= in_min: in_max = in_min + 1
            
            return apply_levels(image, in_min, gamma, in_max, out_min, out_max)
        elif t == "exposure":
            from core.adjustments.exposure import apply_exposure
            exp = float(get_v(["exposure", "exp"], 0.0))
            off = float(get_v(["offset", "off"], 0.0))
            gam = float(get_v(["gamma", "gam"], 1.0))
            
            if exp > 20.0 or exp < -20.0: exp /= 100.0
            if off > 1.0 or off < -1.0: off /= 1000.0
            if gam > 5.0: gam /= 100.0
            if gam <= 0.0: gam = 1.0
            
            return apply_exposure(image, exp, off, gam)
        elif t == "vibrance":
            from core.adjustments.vibrance import apply_vibrance
            return apply_vibrance(image, int(get_v(["vibrance", "vib"], 0)), int(get_v(["saturation", "sat"], 0)))
        elif t == "black_white":
            from core.adjustments.black_white import apply_black_white
            return apply_black_white(image, int(get_v(["red"], 40)), int(get_v(["yellow"], 60)), int(get_v(["green"], 40)), int(get_v(["cyan"], 60)), int(get_v(["blue"], 20)), int(get_v(["magenta"], 80)))
        elif t == "posterize":
            from core.adjustments.posterize import apply_posterize
            return apply_posterize(image, int(get_v(["level", "lvl"], 4)))
        elif t == "threshold":
            from core.adjustments.threshold import apply_threshold
            return apply_threshold(image, int(get_v(["threshold", "thresh"], 128)))
        elif t == "photo_filter":
            from core.adjustments.photo_filter import apply_photo_filter
            color = d.get("color", QColor(255, 140, 0))
            return apply_photo_filter(image, color, int(get_v(["density", "dens"], 25)), bool(get_v(["preserve"], True)))
        elif t == "gradient_map":
            from core.adjustments.gradient_map import apply_gradient_map
            return apply_gradient_map(image, d.get("shadows", QColor(0,0,0)), d.get("highlights", QColor(255,255,255)))
        elif t == "color_lookup":
            from core.adjustments.color_lookup import apply_color_lookup
            return apply_color_lookup(image, d.get("lut", None), int(get_v(["intensity"], 100)))
        elif t == "hdr_toning":
            from core.adjustments.hdr_toning import apply_hdr_toning
            return apply_hdr_toning(image, int(get_v(["radius", "rad"], 10)), float(get_v(["strength", "str"], 0.5)), float(get_v(["gamma"], 1.0)), float(get_v(["detail", "det"], 1.0)))
    except Exception as e:
        print(f"Error applying adjustment layer '{t}':", e)
    return image


def _render_fill_layer(layer, w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    d = layer.fill_data or {}
    p = QPainter(img)
    ft = d.get("type", "solid")
    if ft == "solid":
        p.fillRect(img.rect(), d.get("color", QColor(128, 128, 128)))
    elif ft == "gradient":
        c1 = d.get("color1", QColor(0, 0, 0))
        c2 = d.get("color2", QColor(255, 255, 255))
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        p.fillRect(img.rect(), QBrush(grad))
    p.end()
    return img


class Document:
    """
    Holds all layers, document size, and selection state.
    The single source of truth for image data.
    """

    def __init__(self, width: int = 800, height: int = 600, bg_color: QColor = None):
        self.width: int = width
        self.height: int = height
        self.layers: list[Layer] = []
        self.active_layer_index: int = 0
        self.selection: QPainterPath | None = None  # active selection (may be non-rectangular)
        self.quick_mask_layer: Layer | None = None
        
        self.guides_v: list[float] = []
        self.guides_h: list[float] = []
        self.slices: list[QRect] = []
        self.work_path: dict = {"nodes": [], "closed": False}
        self.show_slices: bool = True
        self.show_guides: bool = True
        self.show_grid: bool = False
        self.grid_size: int = 50
        self.snap_enabled: bool = True
        self.snap_to_guides: bool = True
        self.snap_to_grid: bool = False
        self.snap_to_bounds: bool = True
        self.snap_to_layers: bool = True
        self.alpha_channels: list[dict] = []
        self.color_mode: str = "RGB"
        self.bit_depth: int = 8

        # Create default background layer
        bg = bg_color if bg_color else QColor(255, 255, 255)
        self.add_layer(name="Background", fill_color=bg)

    # ------------------------------------------------------------------ Layers
    def add_layer(self, name: str = None, index: int = None,
                  fill_color: QColor = None) -> Layer:
        if name is None:
            name = f"Layer {len(self.layers) + 1}"
            
        parent_id = None
        if self.layers and 0 <= self.active_layer_index < len(self.layers):
            active = self.layers[self.active_layer_index]
            if getattr(active, "layer_type", "raster") in ("artboard", "group"):
                parent_id = getattr(active, "layer_id", None)
                if index is not None and index == self.active_layer_index + 1:
                    # Вставляем ВНУТРЬ группы (то есть на место группы, сдвигая саму группу выше)
                    insert_idx = self.active_layer_index
            else:
                parent_id = getattr(active, "parent_id", None)

        layer = Layer(name, self.width, self.height, fill_color)
        layer.parent_id = parent_id
        
        if index is None:
            self.layers.append(layer)
            self.active_layer_index = len(self.layers) - 1
        else:
            self.layers.insert(index, layer)
            self.active_layer_index = index
        return layer

    def duplicate_layer(self, index: int) -> Layer:
        src = self.layers[index]
        clone = src.copy()
        import uuid
        clone.layer_id = str(uuid.uuid4())
        clone.name = f"{src.name} copy"
        self.layers.insert(index + 1, clone)
        self.active_layer_index = index + 1
        return clone

    def remove_layer(self, index: int):
        if len(self.layers) <= 1:
            return  # always keep at least one layer
        self.layers.pop(index)
        self.active_layer_index = max(0, min(self.active_layer_index, len(self.layers) - 1))

    def move_layer(self, from_index: int, to_index: int):
        """Move layer up/down in the stack."""
        if from_index < 0 or from_index >= len(self.layers):
            return
        to_index = max(0, min(to_index, len(self.layers) - 1))
        layer = self.layers.pop(from_index)
        self.layers.insert(to_index, layer)
        self.active_layer_index = to_index

    def get_active_layer(self) -> Layer | None:
        if getattr(self, "quick_mask_layer", None) is not None:
            return self.quick_mask_layer
        if self.layers and 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index]
        return None

    # ---------------------------------------------------------------- Composite
    def get_composite(self) -> QImage:
        result = QImage(self.width, self.height, QImage.Format.Format_ARGB32_Premultiplied)
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        
        children_map = {}
        for layer in self.layers:
            pid = getattr(layer, "parent_id", None)
            children_map.setdefault(pid, []).append(layer)
            
        state = {'clip_alpha': None}
        
        def render_layer_list(layers, layer_artboard_rect):
            nonlocal painter
            for i, layer in enumerate(layers):
                if not layer.visible:
                    continue
                    
                ltype = getattr(layer, "layer_type", "raster")
                is_clipping = getattr(layer, "clipping", False)
                
                next_clipping = False
                if i + 1 < len(layers):
                    nl = layers[i+1]
                    if getattr(nl, "clipping", False) and nl.visible:
                        next_clipping = True
                
                if ltype == "artboard":
                    ar = getattr(layer, "artboard_rect", None)
                    if ar:
                        painter.fillRect(ar, QColor(255, 255, 255))
                    state['clip_alpha'] = None
                    render_layer_list(children_map.get(getattr(layer, "layer_id", None), []), ar)
                    continue
                    
                if ltype == "group":
                    state['clip_alpha'] = None
                    render_layer_list(children_map.get(getattr(layer, "layer_id", None), []), layer_artboard_rect)
                    continue
                
                if is_clipping and state['clip_alpha'] is None:
                    continue

                if ltype == "adjustment":
                    painter.end()
                    
                    backup = result.copy()
                    adjusted = _apply_layer_adjustment(backup, layer)
                    
                    import numpy as np
                    import ctypes
                    res_ptr = result.bits()
                    res_buf = (ctypes.c_uint8 * result.sizeInBytes()).from_address(int(res_ptr))
                    arr_res = np.ndarray((result.height(), result.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=res_buf)
                    
                    adj_ptr = adjusted.constBits()
                    adj_buf = (ctypes.c_uint8 * adjusted.sizeInBytes()).from_address(int(adj_ptr))
                    arr_adj = np.ndarray((adjusted.height(), adjusted.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=adj_buf)
                    
                    frac = np.full((backup.height(), backup.width()), layer.opacity, dtype=np.float32)
                    
                    has_mask = getattr(layer, "mask", None) is not None and getattr(layer, "mask_enabled", True)
                    if has_mask:
                        m_ptr = layer.mask.constBits()
                        m_buf = (ctypes.c_uint8 * layer.mask.sizeInBytes()).from_address(int(m_ptr))
                        m_arr = np.ndarray((layer.mask.height(), layer.mask.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=m_buf)
                        mw = min(backup.width(), layer.mask.width())
                        mh = min(backup.height(), layer.mask.height())
                        mask_f = m_arr[:mh, :mw, 1].astype(np.float32) / 255.0
                        frac[:mh, :mw] *= mask_f
                        
                    has_vmask = getattr(layer, "vector_mask", None) is not None and getattr(layer, "vector_mask_enabled", True)
                    if has_vmask:
                        vmask_img = QImage(backup.width(), backup.height(), QImage.Format.Format_Grayscale8)
                        vmask_img.fill(0)
                        vp = QPainter(vmask_img)
                        vp.fillPath(layer.vector_mask, QColor(255, 255, 255))
                        vp.end()
                        v_ptr = vmask_img.bits(); v_ptr.setsize(vmask_img.sizeInBytes())
                        v_arr = np.ndarray((backup.height(), vmask_img.bytesPerLine()), dtype=np.uint8, buffer=v_ptr)
                        vmask_f = v_arr[:backup.height(), :backup.width()].astype(np.float32) / 255.0
                        frac *= vmask_f
                        
                    if layer_artboard_rect:
                        ax, ay, aw, ah = layer_artboard_rect.getRect()
                        ax = max(0, min(self.width, ax))
                        ay = max(0, min(self.height, ay))
                        aw = max(0, min(self.width - ax, aw))
                        ah = max(0, min(self.height - ay, ah))
                        mask_art = np.zeros((self.height, self.width), dtype=np.float32)
                        mask_art[ay:ay+ah, ax:ax+aw] = 1.0
                        frac *= mask_art

                    if is_clipping and state['clip_alpha'] is not None:
                        frac *= state['clip_alpha']
                    
                    frac_4 = frac[..., np.newaxis]
                    
                    h_end, w_end = backup.height(), backup.width()
                    roi_a = arr_adj[:h_end, :w_end, :].astype(np.float32)
                    roi_b = arr_res[:h_end, :w_end, :].astype(np.float32)
                    
                    roi_a -= roi_b
                    roi_a *= frac_4.astype(np.float32)
                    roi_a += roi_b
                    arr_res[:h_end, :w_end, :] = roi_a.astype(np.uint8)
                    
                    if not is_clipping:
                        state['clip_alpha'] = None
                    
                    painter = QPainter(result)

                elif ltype == "frame":
                    img_to_draw = layer.image
                    is_empty = (img_to_draw.width() <= 1 and img_to_draw.height() <= 1)
                    fd = getattr(layer, "frame_data", {})
                    f_rect = fd.get("rect", QRectF(0, 0, 100, 100))
                    
                    path = QPainterPath()
                    if fd.get("shape") == "ellipse": path.addEllipse(f_rect)
                    else: path.addRect(f_rect)
                        
                    painter.save()
                    if layer_artboard_rect:
                        painter.setClipRect(layer_artboard_rect)
                        
                    painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
                    
                    if is_empty:
                        painter.fillRect(f_rect, QColor(220, 220, 220))
                        painter.setPen(QPen(QColor(150, 150, 150), 2))
                        if fd.get("shape") == "rect":
                            painter.drawLine(f_rect.topLeft(), f_rect.bottomRight())
                            painter.drawLine(f_rect.topRight(), f_rect.bottomLeft())
                    else:
                        painter.setOpacity(layer.opacity)
                        painter.setCompositionMode(_get_composition_mode(getattr(layer, "blend_mode", "SourceOver")))
                        painter.drawImage(layer.offset, img_to_draw)
                        
                    painter.restore()
                    continue

                else:
                    if ltype == "fill":
                        img_to_draw = _render_fill_layer(layer, self.width, self.height)
                        img_to_draw.is_copy = True
                    else:
                        img_to_draw = layer.image
                        
                    active_stroke = getattr(layer, "active_stroke", None)
                    if active_stroke and not getattr(layer, "editing_mask", False):
                        stroke_img = active_stroke["img"]
                        offset_style = (getattr(layer, "layer_styles", None) or {}).get("offset", {})
                        if offset_style.get("enabled"):
                            dx_pct = offset_style.get("dx_pct", 0)
                            dy_pct = offset_style.get("dy_pct", 0)
                            edge_mode = offset_style.get("edge_mode", "wrap")
                            if dx_pct != 0 or dy_pct != 0:
                                h, w = stroke_img.height(), stroke_img.width()
                                dx = -int(w * dx_pct / 100.0)
                                dy = -int(h * dy_pct / 100.0)
                                import numpy as np, ctypes
                                ptr = stroke_img.constBits()
                                buf = (ctypes.c_uint8 * stroke_img.sizeInBytes()).from_address(int(ptr))
                                arr = np.ndarray((h, stroke_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
                                if edge_mode == "wrap":
                                    res_arr = np.roll(np.roll(arr, dy, axis=0), dx, axis=1)
                                    stroke_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied)
                                    stroke_img.ndarray = res_arr
                                elif edge_mode == "repeat":
                                    Y, X = np.ogrid[:h, :w]
                                    Y = np.clip(Y - dy, 0, h - 1); X = np.clip(X - dx, 0, w - 1)
                                    res_arr = arr[Y, X]
                                    stroke_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied)
                                    stroke_img.ndarray = res_arr
                                else:
                                    res_arr = np.zeros_like(arr)
                                    y1_src, y2_src = max(0, -dy), min(h, h - dy); x1_src, x2_src = max(0, -dx), min(w, w - dx)
                                    y1_dst, y2_dst = max(0, dy), min(h, h + dy); x1_dst, x2_dst = max(0, dx), min(w, w + dx)
                                    if y1_src < y2_src and x1_src < x2_src: res_arr[y1_dst:y2_dst, x1_dst:x2_dst] = arr[y1_src:y2_src, x1_src:x2_src]
                                    stroke_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied)
                                    stroke_img.ndarray = res_arr

                        if not getattr(img_to_draw, "is_copy", False):
                            img_to_draw = img_to_draw.copy()
                            img_to_draw.is_copy = True
                        p = QPainter(img_to_draw)
                        p.setRenderHint(QPainter.RenderHint.Antialiasing)
                        if active_stroke["clip"]:
                            p.setClipPath(active_stroke["clip"].translated(-layer.offset.x(), -layer.offset.y()))
                        p.setCompositionMode(active_stroke["mode"])
                        p.setOpacity(active_stroke["opacity"])
                        p.drawImage(0, 0, stroke_img)
                        p.end()

                    current_offset = layer.offset
                    if getattr(layer, "layer_styles", None):
                        from core.layer_styles import apply_layer_styles
                        img_to_draw, offset_delta = apply_layer_styles(img_to_draw, layer.layer_styles)
                        current_offset = current_offset + offset_delta
                        
                        # Применяем стиль Сдвиг (Offset)
                        offset_style = layer.layer_styles.get("offset", {})
                        if offset_style.get("enabled"):
                            dx_pct = offset_style.get("dx_pct", 0)
                            dy_pct = offset_style.get("dy_pct", 0)
                            edge_mode = offset_style.get("edge_mode", "wrap")
                            if dx_pct != 0 or dy_pct != 0:
                                h, w = img_to_draw.height(), img_to_draw.width()
                                dx = int(w * dx_pct / 100.0)
                                dy = int(h * dy_pct / 100.0)
                                import numpy as np
                                import ctypes
                                ptr = img_to_draw.constBits()
                                buf = (ctypes.c_uint8 * img_to_draw.sizeInBytes()).from_address(int(ptr))
                                arr = np.ndarray((h, img_to_draw.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
                                if edge_mode == "wrap":
                                    res_arr = np.roll(np.roll(arr, dy, axis=0), dx, axis=1)
                                elif edge_mode == "repeat":
                                    Y, X = np.ogrid[:h, :w]
                                    Y = np.clip(Y - dy, 0, h - 1); X = np.clip(X - dx, 0, w - 1)
                                    res_arr = arr[Y, X]
                                else: # transparent
                                    res_arr = np.zeros_like(arr)
                                    y1_src, y2_src = max(0, -dy), min(h, h - dy); x1_src, x2_src = max(0, -dx), min(w, w - dx)
                                    y1_dst, y2_dst = max(0, dy), min(h, h + dy); x1_dst, x2_dst = max(0, dx), min(w, w + dx)
                                    if y1_src < y2_src and x1_src < x2_src: res_arr[y1_dst:y2_dst, x1_dst:x2_dst] = arr[y1_src:y2_src, x1_src:x2_src]
                                img_to_draw = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
                                img_to_draw.is_copy = True

                    has_mask = getattr(layer, "mask", None) is not None and getattr(layer, "mask_enabled", True)
                    
                    if (has_mask or is_clipping) and not getattr(img_to_draw, "is_copy", False):
                        img_to_draw = img_to_draw.copy()
                        img_to_draw.is_copy = True

                    if has_mask or is_clipping:
                        import numpy as np
                        import ctypes
                        ptr = img_to_draw.bits()
                        buf = (ctypes.c_uint8 * img_to_draw.sizeInBytes()).from_address(int(ptr))
                        arr_full = np.ndarray((img_to_draw.height(), img_to_draw.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
                        arr = arr_full[:, :img_to_draw.width(), :]

                        if has_mask:
                            current_mask = layer.mask
                            active_stroke = getattr(layer, "active_stroke", None)
                            if active_stroke and getattr(layer, "editing_mask", False):
                                current_mask = current_mask.copy()
                                p = QPainter(current_mask)
                                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                                if active_stroke["clip"]:
                                    p.setClipPath(active_stroke["clip"].translated(-layer.offset.x(), -layer.offset.y()))
                                p.setCompositionMode(active_stroke["mode"])
                                p.setOpacity(active_stroke["opacity"])
                                p.drawImage(0, 0, active_stroke["img"])
                                p.end()

                            m_ptr = current_mask.constBits()
                            m_buf = (ctypes.c_uint8 * current_mask.sizeInBytes()).from_address(int(m_ptr))
                            m_arr = np.ndarray((current_mask.height(), current_mask.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=m_buf)[:, :img_to_draw.width(), :]
                            
                            mask_f = m_arr[..., 1].astype(np.float32) / 255.0
                            arr[..., 0] = (arr[..., 0] * mask_f).astype(np.uint8)
                            arr[..., 1] = (arr[..., 1] * mask_f).astype(np.uint8)
                            arr[..., 2] = (arr[..., 2] * mask_f).astype(np.uint8)
                            arr[..., 3] = (arr[..., 3] * mask_f).astype(np.uint8)
                            
                        if is_clipping:
                            ox, oy = layer.offset.x(), layer.offset.y()
                            w, h = img_to_draw.width(), img_to_draw.height()
                            dx1, dy1 = max(0, ox), max(0, oy)
                            dx2, dy2 = min(self.width, ox + w), min(self.height, oy + h)
                            
                            clip_mask = np.zeros((h, w), dtype=np.float32)
                            if state.get('clip_alpha') is not None and dx1 < dx2 and dy1 < dy2:
                                sx1, sy1 = dx1 - ox, dy1 - oy
                                sx2, sy2 = sx1 + (dx2 - dx1), sy1 + (dy2 - dy1)
                                clip_mask[sy1:sy2, sx1:sx2] = state['clip_alpha'][dy1:dy2, dx1:dx2]
                                
                            arr[..., 0] = (arr[..., 0] * clip_mask).astype(np.uint8)
                            arr[..., 1] = (arr[..., 1] * clip_mask).astype(np.uint8)
                            arr[..., 2] = (arr[..., 2] * clip_mask).astype(np.uint8)
                            arr[..., 3] = (arr[..., 3] * clip_mask).astype(np.uint8)
                            

                    if not is_clipping and next_clipping:
                        import numpy as np
                        import ctypes
                        base_alpha_img = QImage(self.width, self.height, QImage.Format.Format_ARGB32_Premultiplied)
                        base_alpha_img.fill(0)
                        ap = QPainter(base_alpha_img)
                        if getattr(layer, "vector_mask", None) is not None and getattr(layer, "vector_mask_enabled", True):
                            ap.setClipPath(layer.vector_mask)
                        ap.setOpacity(layer.opacity)
                        ap.drawImage(layer.offset, img_to_draw)
                        ap.end()
                        
                        arr_alpha = np.empty((self.height, base_alpha_img.bytesPerLine() // 4, 4), dtype=np.uint8)
                        ctypes.memmove(arr_alpha.ctypes.data, int(base_alpha_img.constBits()), base_alpha_img.sizeInBytes())
                        state['clip_alpha'] = arr_alpha[:, :self.width, 3].astype(np.float32).copy() / 255.0
                    elif not is_clipping:
                        state['clip_alpha'] = None

                    painter.save()
                    if layer_artboard_rect:
                        painter.setClipRect(layer_artboard_rect)

                    if getattr(layer, "vector_mask", None) is not None and getattr(layer, "vector_mask_enabled", True):
                        painter.setClipPath(layer.vector_mask, Qt.ClipOperation.IntersectClip)
                    painter.setCompositionMode(_get_composition_mode(getattr(layer, "blend_mode", "SourceOver")))
                    painter.setOpacity(layer.opacity)
                    painter.drawImage(current_offset, img_to_draw)
                    painter.restore()

        render_layer_list(children_map.get(None, []), None)

        if painter.isActive():
            painter.end()
            
        if getattr(self, "quick_mask_layer", None) is not None:
            qm = self.quick_mask_layer.image
            import numpy as np
            ptr = qm.bits(); ptr.setsize(qm.sizeInBytes())
            bpl = qm.bytesPerLine()
            arr = np.ndarray((qm.height(), bpl // 4, 4), dtype=np.uint8, buffer=ptr)[:, :self.width, :]
            
            # Чёрный цвет (или альфа=0) станет красной плёнкой, белый — прозрачным
            gray = 0.299*arr[..., 2] + 0.587*arr[..., 1] + 0.114*arr[..., 0]
            mask_val = (255 - gray) * (arr[..., 3] / 255.0)
            
            red_overlay = np.zeros((qm.height(), self.width, 4), dtype=np.uint8)
            alpha = (mask_val * 0.5).astype(np.uint8)
            red_overlay[..., 2] = alpha # R (Premultiplied)
            red_overlay[..., 3] = alpha # A
            
            red_img = QImage(self.width, qm.height(), QImage.Format.Format_ARGB32_Premultiplied)
            r_ptr = red_img.bits()
            r_ptr.setsize(red_img.sizeInBytes())
            r_arr = np.frombuffer(r_ptr, dtype=np.uint8).reshape((qm.height(), self.width, 4))
            r_arr[:] = red_overlay
            del r_arr
            del r_ptr
            p2 = QPainter(result)
            p2.drawImage(0, 0, red_img)
            p2.end()
            
            del arr
            del ptr
            
        return result

    # ----------------------------------------------------------------- History
    def snapshot_layers(self) -> list[Layer]:
        snap = [layer.copy() for layer in self.layers]
        if getattr(self, "quick_mask_layer", None) is not None:
            snap.append(self.quick_mask_layer.copy())
        return snap

    def apply_layer_mask(self, layer):
        if getattr(layer, "mask", None) is None: return
        import numpy as np
        if getattr(layer, "layer_type", "raster") != "raster":
            layer.layer_type = "raster"
        import ctypes
        w, h = layer.width(), layer.height()
        ptr = layer.image.bits()
        buf = (ctypes.c_uint8 * layer.image.sizeInBytes()).from_address(int(ptr))
        bpl = layer.image.bytesPerLine()
        arr_full = np.ndarray((h, bpl // 4, 4), dtype=np.uint8, buffer=buf)
        arr = arr_full[:, :w, :]
        m_ptr = layer.mask.constBits()
        m_buf = (ctypes.c_uint8 * layer.mask.sizeInBytes()).from_address(int(m_ptr))
        m_bpl = layer.mask.bytesPerLine()
        m_arr_full = np.ndarray((h, m_bpl // 4, 4), dtype=np.uint8, buffer=m_buf)
        m_arr = m_arr_full[:, :w, :]
        mask_f = m_arr[..., 1].astype(np.float32) / 255.0
        arr[..., 0] = (arr[..., 0] * mask_f).astype(np.uint8)
        arr[..., 1] = (arr[..., 1] * mask_f).astype(np.uint8)
        arr[..., 2] = (arr[..., 2] * mask_f).astype(np.uint8)
        arr[..., 3] = (arr[..., 3] * mask_f).astype(np.uint8)
        layer.mask = None
        layer.editing_mask = False

    def restore_layers(self, snapshot: list[Layer]):
        self.layers = []
        self.quick_mask_layer = None
        for layer in snapshot:
            if getattr(layer, "is_quick_mask", False):
                self.quick_mask_layer = layer.copy()
            else:
                self.layers.append(layer.copy())

    # ------------------------------------------------------------------- Crop
    def apply_crop(self, rect: QRect):
        if rect.isEmpty():
            return
        tl = rect.topLeft()
        all_layers = self.layers + ([self.quick_mask_layer] if getattr(self, "quick_mask_layer", None) else [])
        for layer in all_layers:
            new_img = QImage(rect.width(), rect.height(), QImage.Format.Format_ARGB32_Premultiplied)
            new_img.fill(Qt.GlobalColor.transparent)
            p = QPainter(new_img)
            # Re-render layer into the cropped coordinate system (doc-space aware)
            p.drawImage(layer.offset - tl, layer.image)
            p.end()
            layer.image = new_img
            layer.offset = QPoint(0, 0)
        self.width = rect.width()
        self.height = rect.height()
        self.selection = None

    def apply_perspective_crop(self, quad: QPolygonF):
        if quad.isEmpty() or quad.count() < 4:
            return

        # Извлекаем 4 точки
        pts = [quad[i] for i in range(4)]

        # Сортируем точки: находим две верхние (с минимальным Y) и две нижние
        pts.sort(key=lambda p: p.y())
        top_pts = pts[:2]
        bottom_pts = pts[2:]

        # Сортируем их по оси X (слева направо)
        top_pts.sort(key=lambda p: p.x())
        bottom_pts.sort(key=lambda p: p.x())

        # Получаем строгий порядок: Лево-Верх, Право-Верх, Лево-Низ, Право-Низ
        tl, tr = top_pts
        bl, br = bottom_pts

        # Вспомогательная функция для расчета расстояния (чтобы не импортировать math)
        def _dist(p1, p2):
            return ((p1.x() - p2.x())**2 + (p1.y() - p2.y())**2) ** 0.5

        # Вычисляем реальные размеры будущего холста без растяжений
        new_w = int(max(_dist(tl, tr), _dist(bl, br)))
        new_h = int(max(_dist(tl, bl), _dist(tr, br)))

        if new_w <= 0 or new_h <= 0:
            return

        # Создаем отсортированный многоугольник-источник (строго по часовой)
        sorted_quad = QPolygonF([tl, tr, br, bl])

        # Явно задаем 4 точки приемника (в том же порядке TL, TR, BR, BL)
        dst_quad = QPolygonF([
            QPointF(0, 0),
            QPointF(new_w, 0),
            QPointF(new_w, new_h),
            QPointF(0, new_h)
        ])

        all_layers = self.layers + ([self.quick_mask_layer] if getattr(self, "quick_mask_layer", None) else [])
        for layer in all_layers:
            new_img = QImage(new_w, new_h, QImage.Format.Format_ARGB32_Premultiplied)
            new_img.fill(Qt.GlobalColor.transparent)

            p = QPainter(new_img)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            src_quad = QPolygonF(sorted_quad)
            src_quad.translate(QPointF(-layer.offset))

            xform = QTransform()
            ok = QTransform.quadToQuad(src_quad, dst_quad, xform)
            if ok:
                p.setTransform(xform)
                p.drawImage(0, 0, layer.image)

            p.end()
            layer.image = new_img
            layer.offset = QPoint(0, 0)

        # Обновляем размеры самого документа
        self.width = new_w
        self.height = new_h
        self.selection = None

    # ------------------------------------------------------------------- Trim / Reveal All
    @staticmethod
    def _nontransparent_bounds(img: QImage) -> QRect:
        """Bounding rect of pixels with alpha > 0. Returns empty QRect if none."""
        w, h = img.width(), img.height()
        if w <= 0 or h <= 0:
            return QRect()

        try:
            import numpy as np
            import ctypes
            ptr = img.constBits()
            buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
            arr = np.ndarray((h, img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :w, :]
            alpha = arr[..., 3].copy()
            rows = np.any(alpha, axis=1)
            if not np.any(rows): return QRect()
            cols = np.any(alpha, axis=0)
            rmin, rmax = np.where(rows)[0][[0, -1]]
            cmin, cmax = np.where(cols)[0][[0, -1]]
            return QRect(int(cmin), int(rmin), int(cmax - cmin + 1), int(rmax - rmin + 1))
        except Exception:
            return QRect(0, 0, w, h)

    def fit_to_artboards(self) -> bool:
        """Оборачивает границы документа строго вокруг всех Артбордов и сдвигает слои при выходе в минус."""
        bounds = None
        has_artboards = False
        for layer in self.layers:
            if getattr(layer, "layer_type", "") == "artboard" and getattr(layer, "artboard_rect", None):
                has_artboards = True
                bounds = layer.artboard_rect if bounds is None else bounds.united(layer.artboard_rect)

        if not has_artboards or bounds is None:
            return False

        shift = bounds.topLeft()
        if shift == QPoint(0, 0) and self.width == bounds.width() and self.height == bounds.height():
            return False

        for layer in self.layers:
            layer.offset = layer.offset - shift
            if getattr(layer, "layer_type", "") == "artboard" and getattr(layer, "artboard_rect", None):
                layer.artboard_rect.translate(-shift)

        self.width = bounds.width()
        self.height = bounds.height()
        self.selection = None
        return True

    def trim_transparent(self) -> bool:
        """Trim document to non-transparent pixels of the composite."""
        comp = self.get_composite()
        br = self._nontransparent_bounds(comp)
        if br.isEmpty() or (br.width() == self.width and br.height() == self.height and br.topLeft() == QPoint(0, 0)):
            return False
        self.apply_crop(br)
        return True

    def reveal_all(self) -> bool:
        """Expand canvas so all layer pixels (incl. offsets) fit inside."""
        bounds: QRect | None = None
        for layer in self.layers:
            # Adjustment layers don't contribute pixels; fill layers typically cover current canvas.
            ltype = getattr(layer, "layer_type", "raster")
            if ltype == "adjustment":
                continue
            br = self._nontransparent_bounds(layer.image)
            if br.isEmpty():
                continue
            br = br.translated(layer.offset)
            bounds = br if bounds is None else bounds.united(br)

        if bounds is None or bounds.isEmpty():
            return False

        # If everything already fits in current canvas (0..w,h), nothing to do.
        canvas = QRect(0, 0, self.width, self.height)
        if canvas.contains(bounds):
            return False

        # New canvas = union of current canvas and pixel bounds
        new_bounds = canvas.united(bounds)
        shift = new_bounds.topLeft()

        # Move all layers so new_bounds top-left becomes (0,0)
        for layer in self.layers:
            layer.offset = layer.offset - shift

        self.width = new_bounds.width()
        self.height = new_bounds.height()
        self.selection = None
        return True

    # ------------------------------------------------------------------ Flatten
    def flatten(self):
        composite = self.get_composite()
        self.layers.clear()
        bg = Layer("Background", self.width, self.height)
        bg.image = composite
        self.layers.append(bg)
        self.active_layer_index = 0

    def save_to_imfn(self, path: str):
        import pickle, gzip
        data = {
            "width": self.width,
            "height": self.height,
            "color_mode": self.color_mode,
            "bit_depth": self.bit_depth,
            "layers": [l.to_dict() for l in self.layers]
        }
        with gzip.open(path, "wb") as f:
            pickle.dump(data, f)

    @classmethod
    def load_from_imfn(cls, path: str):
        import pickle, gzip
        with gzip.open(path, "rb") as f:
            data = pickle.load(f)
        doc = cls(data["width"], data["height"])
        doc.color_mode = data.get("color_mode", "RGB")
        doc.bit_depth = data.get("bit_depth", 8)
        doc.layers = [Layer.from_dict(ld, doc.width, doc.height) for ld in data.get("layers", [])]
        return doc

    def __repr__(self) -> str:
        return f"<Document {self.width}x{self.height} layers={len(self.layers)}>"
