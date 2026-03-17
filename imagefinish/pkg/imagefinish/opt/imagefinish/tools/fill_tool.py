import numpy as np
from PyQt6.QtGui import QImage, QColor, QPainter
from PyQt6.QtCore import QPoint
from tools.base_tool import BaseTool


class FillTool(BaseTool):
    name = "Fill"
    icon = "🪣"
    shortcut = "K"

    def on_press(self, pos, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or getattr(layer, "lock_pixels", False):
            return
        tolerance = int(opts.get("fill_tolerance", 32))
        contiguous = bool(opts.get("fill_contiguous", True))
        
        if getattr(layer, "editing_mask", False) and getattr(layer, "mask", None) is not None:
            target_img = layer.mask
            lock_alpha = False
        else:
            target_img = layer.image
            lock_alpha = getattr(layer, "lock_alpha", False)
            
        sel = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None
        local_pos = pos - layer.offset
        self._flood_fill(target_img, local_pos.x(), local_pos.y(), fg, tolerance, sel, contiguous, lock_alpha, layer.offset)

    def on_move(self, pos, doc, fg, bg, opts): pass
    def on_release(self, pos, doc, fg, bg, opts): pass
    def needs_history_push(self) -> bool: return True

    # ---------------------------------------------------------------- Algorithm
    @staticmethod
    def _flood_fill(image: QImage, x: int, y: int, fill_color: QColor,
                    tolerance: int, selection=None, contiguous: bool = True, lock_alpha: bool = False, offset: QPoint = QPoint(0,0)):
        w, h = image.width(), image.height()
        if not (0 <= x < w and 0 <= y < h):
            return

        target_rgba = image.pixel(x, y)
        fill_rgba = fill_color.rgba()
        if target_rgba == fill_rgba:
            return

        # Распаковка целевого цвета
        tr, tg, tb, ta = (target_rgba >> 16) & 0xFF, (target_rgba >> 8) & 0xFF, \
                         target_rgba & 0xFF, (target_rgba >> 24) & 0xFF
                         
        # Нельзя заливать прозрачные пиксели, если альфа заблокирована
        if lock_alpha and ta == 0:
            return

        fr, fg_g, fb, fa = fill_color.red(), fill_color.green(), fill_color.blue(), fill_color.alpha()

        # --- NUMPY ОПТИМИЗАЦИЯ ---
        import ctypes
        bpl = image.bytesPerLine()
        ptr = image.bits()
        buf = (ctypes.c_uint8 * image.sizeInBytes()).from_address(int(ptr))
        arr_full = np.ndarray((h, bpl // 4, 4), dtype=np.uint8, buffer=buf)
        arr = arr_full[:, :w, :]

        B = arr[..., 0].astype(np.int32)
        G = arr[..., 1].astype(np.int32)
        R = arr[..., 2].astype(np.int32)
        A = arr[..., 3].astype(np.int32)

        # Вычисляем квадрат расстояния (с учетом Alpha)
        dist_sq = (R - tr)**2 + (G - tg)**2 + (B - tb)**2 + (A - ta)**2
        tolerance_sq = tolerance**2

        color_mask = dist_sq <= tolerance_sq

        # Если есть выделение, применяем его быстро через QPainter
        if selection:
            sel_img = QImage(w, h, QImage.Format.Format_Grayscale8)
            sel_img.fill(0)
            p = QPainter(sel_img)
            p.translate(-offset)
            p.fillPath(selection, QColor(255))
            p.end()
            
            s_ptr = sel_img.constBits()
            s_buf = (ctypes.c_uint8 * sel_img.sizeInBytes()).from_address(int(s_ptr))
            sel_arr = np.ndarray((h, sel_img.bytesPerLine()), dtype=np.uint8, buffer=s_buf)
            sel_arr = sel_arr[:, :w]
            
            color_mask &= (sel_arr > 0)

        if not color_mask[y, x]:
            return

        if contiguous:
            # 1. ОСНОВНОЙ ПРОХОД (Flood Fill по маске)
            visited = np.zeros((h, w), dtype=bool)
            stack = [(y, x)]
            visited[y, x] = True
            color_mask[y, x] = False

            while stack:
                cy, cx = stack.pop()

                if cy > 0 and color_mask[cy - 1, cx]: visited[cy - 1, cx] = True; color_mask[cy - 1, cx] = False; stack.append((cy - 1, cx))
                if cy < h - 1 and color_mask[cy + 1, cx]: visited[cy + 1, cx] = True; color_mask[cy + 1, cx] = False; stack.append((cy + 1, cx))
                if cx > 0 and color_mask[cy, cx - 1]: visited[cy, cx - 1] = True; color_mask[cy, cx - 1] = False; stack.append((cy, cx - 1))
                if cx < w - 1 and color_mask[cy, cx + 1]: visited[cy, cx + 1] = True; color_mask[cy, cx + 1] = False; stack.append((cy, cx + 1))
        else:
            visited = color_mask.copy()
            visited[y, x] = True

        # 2. ФАЗА "ПОЖИРАНИЯ" ГРАНИЦ (Anti-Halo)
        up = np.roll(visited, 1, axis=0); up[0, :] = False
        down = np.roll(visited, -1, axis=0); down[-1, :] = False
        left = np.roll(visited, 1, axis=1); left[:, 0] = False
        right = np.roll(visited, -1, axis=1); right[:, -1] = False
        
        neighbors = (up | down | left | right) & ~visited
        if selection:
            neighbors &= (sel_arr > 0)
            
        border_tolerance = tolerance * 1.5 + 20
        border_tol_sq = border_tolerance**2
        
        # В оригинале для границ проверялся только RGB
        dist_sq_rgb = (R - tr)**2 + (G - tg)**2 + (B - tb)**2
        border_mask = neighbors & (dist_sq_rgb <= border_tol_sq)
        
        final_fill = visited | border_mask
        if lock_alpha:
            final_fill &= (A > 0)

        # 3. ФИНАЛЬНАЯ ЗАЛИВКА махом
        if lock_alpha:
            existing_a = A[final_fill].astype(np.float32) / 255.0
            arr[final_fill, 0] = (fb * existing_a).astype(np.uint8)
            arr[final_fill, 1] = (fg_g * existing_a).astype(np.uint8)
            arr[final_fill, 2] = (fr * existing_a).astype(np.uint8)
            # Альфу не трогаем!
        else:
            arr[final_fill, 0] = fb
            arr[final_fill, 1] = fg_g
            arr[final_fill, 2] = fr
            arr[final_fill, 3] = fa
