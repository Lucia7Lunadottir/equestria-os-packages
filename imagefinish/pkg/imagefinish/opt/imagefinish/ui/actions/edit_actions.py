import math
from PyQt6.QtCore import Qt, QRectF, QPoint
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from core.locale import tr


class EditActionsMixin:
    def _undo(self):
        # Если активна рамка трансформации, Ctrl+Z работает как Escape (Отмена трансформации)
        tool = self._canvas.active_tool
        if hasattr(tool, "is_transforming") and getattr(tool, "is_transforming", False):
            tool.cancel_transform(self._document)
            self._canvas_refresh()
            return

        from core.history import HistoryState, clone_work_path
        state = self._history.undo()
        if not state:
            return
        self._history.save_for_redo(HistoryState(
            description="redo",
            layers_snapshot=self._document.snapshot_layers(),
            active_layer_index=self._document.active_layer_index,
            doc_width=self._document.width,
            doc_height=self._document.height,
            selection_snapshot=QPainterPath(self._document.selection) if self._document.selection else None,
            work_path_snapshot=clone_work_path(getattr(self._document, "work_path", None)),
            alpha_channels_snapshot=list(getattr(self._document, "alpha_channels", [])),
            color_mode_snapshot=getattr(self._document, "color_mode", "RGB"),
            bit_depth_snapshot=getattr(self._document, "bit_depth", 8)
        ))
        self._document.restore_layers(state.layers_snapshot)
        self._document.active_layer_index = state.active_layer_index
        self._document.selection = QPainterPath(state.selection_snapshot) if state.selection_snapshot else None
        if getattr(state, "work_path_snapshot", None) is not None:
            self._document.work_path = clone_work_path(state.work_path_snapshot)
        if state.doc_width and state.doc_height:
            dims_changed = (self._document.width != state.doc_width or
                            self._document.height != state.doc_height)
            self._document.width  = state.doc_width
            self._document.height = state.doc_height
        if getattr(state, "alpha_channels_snapshot", None) is not None:
            self._document.alpha_channels = list(state.alpha_channels_snapshot)
            if dims_changed:
                self._canvas.reset_zoom()
        if getattr(state, "color_mode_snapshot", None) is not None:
            self._document.color_mode = state.color_mode_snapshot
        if getattr(state, "bit_depth_snapshot", None) is not None:
            self._document.bit_depth = state.bit_depth_snapshot
        if hasattr(self, "_update_mode_menu"): self._update_mode_menu()
        self._refresh_layers()
        self._canvas_refresh()
        self._status.showMessage(tr("status.undo", desc=state.description))

    def _redo(self):
        from core.history import HistoryState, clone_work_path
        state = self._history.redo()
        if not state:
            return
        self._history.push(HistoryState(
            description="undo",
            layers_snapshot=self._document.snapshot_layers(),
            active_layer_index=self._document.active_layer_index,
            doc_width=self._document.width,
            doc_height=self._document.height,
            selection_snapshot=QPainterPath(self._document.selection) if self._document.selection else None,
            work_path_snapshot=clone_work_path(getattr(self._document, "work_path", None)),
            alpha_channels_snapshot=list(getattr(self._document, "alpha_channels", [])),
            color_mode_snapshot=getattr(self._document, "color_mode", "RGB"),
            bit_depth_snapshot=getattr(self._document, "bit_depth", 8)
        ))
        self._document.restore_layers(state.layers_snapshot)
        self._document.active_layer_index = state.active_layer_index
        self._document.selection = QPainterPath(state.selection_snapshot) if state.selection_snapshot else None
        if getattr(state, "work_path_snapshot", None) is not None:
            self._document.work_path = clone_work_path(state.work_path_snapshot)
        if state.doc_width and state.doc_height:
            dims_changed = (self._document.width != state.doc_width or
                            self._document.height != state.doc_height)
            self._document.width  = state.doc_width
            self._document.height = state.doc_height
        if getattr(state, "alpha_channels_snapshot", None) is not None:
            self._document.alpha_channels = list(state.alpha_channels_snapshot)
            if dims_changed:
                self._canvas.reset_zoom()
        if getattr(state, "color_mode_snapshot", None) is not None:
            self._document.color_mode = state.color_mode_snapshot
        if getattr(state, "bit_depth_snapshot", None) is not None:
            self._document.bit_depth = state.bit_depth_snapshot
        if hasattr(self, "_update_mode_menu"): self._update_mode_menu()
        self._refresh_layers()
        self._canvas_refresh()

    def _clear_layer(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
            
        tool = self._canvas.active_tool
        if self._active_tool_name == "Move" and hasattr(tool, "is_transforming") and tool.is_transforming:
            is_float = getattr(tool, "_is_floating", False)
            tool.cancel_transform(self._document)
            self._push_history(tr("history.clear_layer"))
            if is_float:
                sel = self._document.selection
                if sel and not sel.isEmpty():
                    p = QPainter(layer.image)
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                    p.translate(-layer.offset)
                    p.setClipPath(sel)
                    p.fillRect(sel.boundingRect().toRect(), QColor(0, 0, 0, 0))
                    p.end()
                self._document.selection = None
            else:
                layer.image.fill(Qt.GlobalColor.transparent)
            self._canvas_refresh()
            return
            
        self._push_history(tr("history.clear_layer"))
        sel = self._document.selection
        if sel and not sel.isEmpty():
            p = QPainter(layer.image)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.translate(-layer.offset)
            p.setClipPath(sel)
            p.fillRect(sel.boundingRect().toRect(), QColor(0, 0, 0, 0))
            p.end()
        else:
            layer.image.fill(Qt.GlobalColor.transparent)
        self._canvas_refresh()

    def _deselect(self):
        # Сохраняем текущее выделение для функции Reselect
        if self._document.selection and not self._document.selection.isEmpty():
            self._last_selection = QPainterPath(self._document.selection)
            self._push_history(tr("history.deselect"))

        self._document.selection = None
        self._canvas_refresh()

    def _select_all(self):
        self._push_history(tr("history.select_all"))
        p = QPainterPath()
        p.addRect(QRectF(0, 0, self._document.width, self._document.height))
        self._document.selection = p
        self._canvas_refresh()

    def _reselect(self):
        # Восстанавливаем последнее снятое выделение
        if hasattr(self, "_last_selection") and self._last_selection:
            self._push_history(tr("history.reselect"))
            self._document.selection = QPainterPath(self._last_selection)
            self._canvas_refresh()

    def _inverse_selection(self):
        self._push_history(tr("history.inverse"))
        sel = self._document.selection

        if not sel or sel.isEmpty():
            # Если ничего не выделено, инверсия выделяет весь холст
            self._select_all()
        else:
            # Вычитаем текущее выделение из площади всего холста
            full_rect = QPainterPath()
            full_rect.addRect(QRectF(0, 0, self._document.width, self._document.height))
            self._document.selection = full_rect.subtracted(sel)
            self._canvas_refresh()

    def _color_range(self):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull():
            return
        
        from core.history import HistoryState
        pre_state = HistoryState(
            description=tr("history.color_range"),
            layers_snapshot=self._document.snapshot_layers(),
            active_layer_index=self._document.active_layer_index,
            doc_width=self._document.width,
            doc_height=self._document.height,
            selection_snapshot=QPainterPath(self._document.selection) if self._document.selection else None,
            alpha_channels_snapshot=list(getattr(self._document, "alpha_channels", [])),
            color_mode_snapshot=getattr(self._document, "color_mode", "RGB"),
            bit_depth_snapshot=getattr(self._document, "bit_depth", 8)
        )
        
        from ui.color_range_dialog import ColorRangeDialog
        dlg = ColorRangeDialog(self._document, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
        else:
            self._document.selection = pre_state.selection_snapshot
            self._canvas_refresh()
            
    def _apply_np_mask(self, mask, desc: str, offset: QPoint):
        import numpy as np
        if not np.any(mask):
            return
        h, w = mask.shape
        import ctypes
        from PyQt6.QtGui import QImage, QRegion, QBitmap, QPainterPath
        mask_img = QImage(w, h, QImage.Format.Format_RGBA8888)
        mask_img.fill(0)
        m_ptr = mask_img.bits()
        m_buf = (ctypes.c_uint8 * mask_img.sizeInBytes()).from_address(int(m_ptr))
        m_arr = np.ndarray((h, mask_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=m_buf)
        m_arr[:, :w, :][mask, 3] = 255
        
        path = QPainterPath()
        path.addRegion(QRegion(QBitmap.fromImage(mask_img.createAlphaMask())))
        path = path.simplified()
        path.translate(offset.x(), offset.y())
        
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=desc,
            layers_snapshot=self._document.snapshot_layers(),
            active_layer_index=self._document.active_layer_index,
            doc_width=self._document.width,
            doc_height=self._document.height,
            selection_snapshot=QPainterPath(self._document.selection) if self._document.selection else None,
            work_path_snapshot=clone_work_path(getattr(self._document, "work_path", None)),
            alpha_channels_snapshot=list(getattr(self._document, "alpha_channels", [])),
            color_mode_snapshot=getattr(self._document, "color_mode", "RGB"),
            bit_depth_snapshot=getattr(self._document, "bit_depth", 8)
        )
        self._document.selection = path
        self._history.push(pre_state)
        self._canvas_refresh()

    def _select_subject(self):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull(): return
        img = layer.image
        w, h = img.width(), img.height()
        import ctypes, numpy as np
        ptr = img.constBits()
        buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
        arr = np.ndarray((h, img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :w, :]

        # Эвристика: объект в центре, отличающийся от краёв холста
        top = arr[0:max(1, h//20), :, :3].reshape(-1, 3)
        bottom = arr[h-max(1, h//20):h, :, :3].reshape(-1, 3)
        left = arr[:, 0:max(1, w//20), :3].reshape(-1, 3)
        right = arr[:, w-max(1, w//20):w, :3].reshape(-1, 3)
        border_pixels = np.vstack((top, bottom, left, right))
        bg_color = np.median(border_pixels, axis=0)

        Y, X = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((X - w/2)**2 + (Y - h/2)**2)
        max_dist = math.hypot(w/2, h/2)
        dist_norm = dist_from_center / max(1.0, max_dist)

        diff = np.abs(arr[..., :3].astype(np.float32) - bg_color).sum(axis=-1)
        score = diff * (1.0 - dist_norm * 0.5)

        threshold = np.mean(score) + 0.5 * np.std(score)
        mask = (score > threshold) & (arr[..., 3] > 0)
        self._apply_np_mask(mask, tr("history.select_subject"), layer.offset)

    def _select_sky(self):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull(): return
        img = layer.image
        w, h = img.width(), img.height()
        import ctypes, numpy as np
        ptr = img.constBits()
        buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
        arr = np.ndarray((h, img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :w, :]

        B, G, R, A = arr[..., 0].astype(np.float32), arr[..., 1].astype(np.float32), arr[..., 2].astype(np.float32), arr[..., 3]

        # Эвристика: небо сверху, оно синее/голубое или яркое (облака)
        blueness = B - np.maximum(R, G)
        brightness = (R + G + B) / 3.0
        sky_score = np.maximum(blueness * 2, brightness - 130)

        Y, X = np.ogrid[:h, :w]
        y_falloff = np.clip(1.0 - (Y / float(h)) * 1.5, 0.0, 1.0)
        final_score = sky_score * y_falloff

        threshold = np.mean(final_score) + np.std(final_score)
        mask = (final_score > max(10, threshold)) & (A > 0)
        self._apply_np_mask(mask, tr("history.select_sky"), layer.offset)

    def _focus_area(self):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull(): return
        img = layer.image
        w, h = img.width(), img.height()
        import ctypes, numpy as np
        ptr = img.constBits()
        buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
        arr = np.ndarray((h, img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :w, :]

        gray = 0.299 * arr[..., 2] + 0.587 * arr[..., 1] + 0.114 * arr[..., 0]
        dy, dx = np.gradient(gray)
        edges = np.hypot(dx, dy)
        
        edges_3d = edges[..., np.newaxis].astype(np.float32)
        from tools.effect_tools import _box_blur_np
        radius = max(1, min(w, h) // 50)
        blurred_edges = _box_blur_np(edges_3d, radius)[..., 0]
        
        threshold = np.mean(blurred_edges) + 1.0 * np.std(blurred_edges)
        mask = (blurred_edges > threshold) & (arr[..., 3] > 0)
        self._apply_np_mask(mask, tr("history.focus_area"), layer.offset)

    def _select_and_mask(self):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull(): return
        
        from ui.select_and_mask_dialog import SelectAndMaskDialog
        dlg = SelectAndMaskDialog(self._document, self)
        if dlg.exec():
            out_mode, mask_arr = dlg.get_result()
            self._push_history(tr("history.select_and_mask"))
            
            import numpy as np
            import ctypes
            from PyQt6.QtGui import QImage, QRegion, QBitmap, QPainterPath, QPainter
            h, w = mask_arr.shape
            m_img = QImage(w, h, QImage.Format.Format_RGBA8888)
            m_img.fill(0)
            m_ptr = m_img.bits()
            m_buf = (ctypes.c_uint8 * m_img.sizeInBytes()).from_address(int(m_ptr))
            np.ndarray((h, w, 4), dtype=np.uint8, buffer=m_buf)[mask_arr > 0.5, 3] = 255
            
            if out_mode == "selection":
                path = QPainterPath()
                path.addRegion(QRegion(QBitmap.fromImage(m_img.createAlphaMask())))
                path.translate(layer.offset.x(), layer.offset.y())
                self._document.selection = path.simplified()
            elif out_mode == "mask":
                mask_out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                mask_out.fill(QColor(255,255,255))
                out_ptr = mask_out.bits()
                out_buf = (ctypes.c_uint8 * mask_out.sizeInBytes()).from_address(int(out_ptr))
                out_arr = np.ndarray((h, mask_out.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=out_buf)
                v = (mask_arr * 255).astype(np.uint8)
                out_arr[..., 0] = out_arr[..., 1] = out_arr[..., 2] = v
                layer.mask = mask_out
                layer.mask_enabled = True
            else:
                # layer or layer_mask
                nl = layer.copy()
                nl.name = layer.name + " (masked)"
                if out_mode == "layer_mask":
                    mask_out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                    out_ptr = mask_out.bits()
                    out_buf = (ctypes.c_uint8 * mask_out.sizeInBytes()).from_address(int(out_ptr))
                    out_arr = np.ndarray((h, mask_out.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=out_buf)
                    v = (mask_arr * 255).astype(np.uint8)
                    out_arr[..., 0] = out_arr[..., 1] = out_arr[..., 2] = v
                    nl.mask = mask_out
                layer.visible = False
                self._document.layers.insert(self._document.active_layer_index + 1, nl)
                self._document.active_layer_index += 1
            self._refresh_layers(); self._canvas_refresh()

    def _modify_selection(self, mode: str):
        if not self._document.selection or self._document.selection.isEmpty():
            return
            
        from PyQt6.QtWidgets import QInputDialog
        from PyQt6.QtGui import QPainterPathStroker, QPainterPath, QRegion, QBitmap, QImage, QPainter, QColor
        from PyQt6.QtCore import Qt, QRectF
        import numpy as np
        
        val, ok = QInputDialog.getInt(self, tr(f"menu.modify.{mode}").replace("…", ""), tr("opts.radius"), 10, 1, 200, 1)
        if not ok: return
        
        path = self._document.selection
        
        if mode == "expand":
            self._push_history(tr(f"history.modify_{mode}"))
            stroker = QPainterPathStroker()
            stroker.setWidth(val * 2)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroke = stroker.createStroke(path)
            self._document.selection = path.united(stroke).simplified()
            
        elif mode == "contract":
            self._push_history(tr(f"history.modify_{mode}"))
            stroker = QPainterPathStroker()
            stroker.setWidth(val * 2)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroke = stroker.createStroke(path)
            self._document.selection = path.subtracted(stroke).simplified()
            
        elif mode == "border":
            self._push_history(tr(f"history.modify_{mode}"))
            stroker = QPainterPathStroker()
            stroker.setWidth(val)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroke = stroker.createStroke(path)
            self._document.selection = stroke.simplified()
            
        elif mode in ("smooth", "feather"):
            br = path.boundingRect().toRect().adjusted(-val*2, -val*2, val*2, val*2)
            w, h = br.width(), br.height()
            if w <= 0 or h <= 0: return
            
            img = QImage(w, h, QImage.Format.Format_Grayscale8)
            img.fill(0)
            p = QPainter(img)
            p.translate(-br.topLeft())
            p.fillPath(path, QColor(255))
            p.end()
            
            import ctypes
            ptr = img.constBits()
            buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
            arr = np.ndarray((h, img.bytesPerLine()), dtype=np.uint8, buffer=buf)[:, :w]
            
            arr_3d = arr[..., np.newaxis]
            from tools.effect_tools import _box_blur_np
            blurred_3d = _box_blur_np(_box_blur_np(_box_blur_np(arr_3d, val), val), val)
            blurred = blurred_3d[..., 0]
            
            if mode == "smooth":
                mask = blurred >= 128
                self._apply_np_mask(mask, tr("history.modify_smooth"), br.topLeft())
                
            elif mode == "feather":
                self._push_history(tr(f"history.modify_{mode}"))
                if getattr(self._document, "quick_mask_layer", None) is None:
                    self._toggle_quick_mask()
                    
                qm_img = self._document.quick_mask_layer.image
                p = QPainter(qm_img)
                rgb_arr = np.empty((h, w, 4), dtype=np.uint8)
                rgb_arr[..., 0] = rgb_arr[..., 1] = rgb_arr[..., 2] = blurred
                rgb_arr[..., 3] = 255
                blur_qimg = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                ctypes.memmove(int(blur_qimg.bits()), np.ascontiguousarray(rgb_arr).ctypes.data, blur_qimg.sizeInBytes())
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                p.drawImage(br.topLeft(), blur_qimg)
                p.end()
                self._document.selection = None
                
        self._canvas_refresh()
        self._refresh_layers()

    def _cut(self):
        if hasattr(self, "_commit_move_transform"):
            self._commit_move_transform()
        self._copy()
        layer = self._document.get_active_layer()
        if not layer:
            return
        sel = self._document.selection
        if sel and not sel.isEmpty():
            self._push_history(tr("history.cut"))
            p = QPainter(layer.image)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.translate(-layer.offset)
            p.setClipPath(sel)
            p.fillRect(sel.boundingRect().toRect(), QColor(0, 0, 0, 0))
            p.end()
            self._canvas_refresh()

    def _copy(self):
        if hasattr(self, "_commit_move_transform"):
            self._commit_move_transform()
        layer = self._document.get_active_layer()
        if not layer:
            return
        sel = self._document.selection
        if sel and not sel.isEmpty():
            local_br = sel.boundingRect().toRect().translated(-layer.offset).intersected(layer.image.rect())
            if local_br.isEmpty():
                from PyQt6.QtGui import QImage
                self._clipboard = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
                self._clipboard.fill(0)
            else:
                self._clipboard = layer.image.copy(local_br)
        else:
            self._clipboard = layer.image.copy()

    def _paste(self):
        if not hasattr(self, "_clipboard") or self._clipboard is None:
            return
        self._push_history(tr("history.paste"))
        
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "layer_type", "") == "frame":
            fd = getattr(layer, "frame_data", {})
            f_rect = fd.get("rect", QRectF(0,0,100,100))
            
            cw, ch = self._clipboard.width(), self._clipboard.height()
            fw, fh = f_rect.width(), f_rect.height()
            scale = max(fw / cw, fh / ch)
            new_w, new_h = int(cw * scale), int(ch * scale)
            
            scaled = self._clipboard.scaled(new_w, new_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            layer.image = scaled
            cx = f_rect.center().x() - new_w / 2
            cy = f_rect.center().y() - new_h / 2
            layer.offset = QPoint(int(cx), int(cy))
            
            self._refresh_layers()
            self._canvas_refresh()
            return
            
        from core.layer import Layer
        new_layer = Layer(f"Pasted {len(self._document.layers)+1}",
                          self._document.width, self._document.height)
        cx = (self._document.width  - self._clipboard.width())  // 2
        cy = (self._document.height - self._clipboard.height()) // 2
        p = QPainter(new_layer.image)
        p.drawImage(QPoint(cx, cy), self._clipboard)
        p.end()
        self._document.layers.append(new_layer)
        self._document.active_layer_index = len(self._document.layers) - 1
        self._refresh_layers()
        self._canvas_refresh()

    def _fill_fg(self):
        self._fill_with(self._canvas.fg_color)

    def _fill_bg(self):
        self._fill_with(self._canvas.bg_color)

    def _fill_with(self, color: QColor):
        layer = self._document.get_active_layer()
        if not layer:
            return
        self._push_history(tr("history.fill"))
        p = QPainter(layer.image)
        sel = self._document.selection
        if sel and not sel.isEmpty():
            p.translate(-layer.offset)
            p.setClipPath(sel)
            p.fillRect(sel.boundingRect().toRect(), color)
            p.setClipping(False)
        else:
            p.fillRect(layer.image.rect(), color)
        p.end()
        self._canvas_refresh()
