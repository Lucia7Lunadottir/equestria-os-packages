from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QImage, QPolygonF, QColor
from core.locale import tr


class ImageActionsMixin:

    def _image_size(self):
        from ui.image_size_dialog import ImageSizeDialog
        dlg = ImageSizeDialog(self._document.width, self._document.height, self)
        if not dlg.exec():
            return
        new_w, new_h = dlg.result_size()
        mode         = dlg.result_transform()
        if new_w == self._document.width and new_h == self._document.height:
            return
        self._push_history(tr("history.image_size"))
        for layer in self._document.layers:
            src = (layer.smart_data["original"]
                   if getattr(layer, "smart_data", None) else layer.image)
            scaled = src.scaled(new_w, new_h,
                                Qt.AspectRatioMode.IgnoreAspectRatio, mode)
            layer.image = scaled
            if getattr(layer, "smart_data", None):
                layer.smart_data["original"] = src
        self._document.width  = new_w
        self._document.height = new_h
        self._canvas_refresh()
        self._canvas.reset_zoom()
        self._refresh_layers()

    def _flip_h(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        self._push_history(tr("history.flip_h"))
        layer.image = layer.image.mirrored(horizontal=True, vertical=False)
        self._canvas_refresh()

    def _flip_v(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        self._push_history(tr("history.flip_v"))
        layer.image = layer.image.mirrored(horizontal=False, vertical=True)
        self._canvas_refresh()

    def _resize_canvas(self):
        from utils.new_document_dialog import NewDocumentDialog
        dlg = NewDocumentDialog(self)
        dlg.setWindowTitle(tr("dlg.resize_canvas"))
        dlg._width_spin.setValue(self._document.width)
        dlg._height_spin.setValue(self._document.height)
        if dlg.exec():
            self._push_history(tr("history.resize_canvas"))
            new_w, new_h = dlg.get_width(), dlg.get_height()
            for layer in self._document.layers:
                lw, lh = layer.image.width(), layer.image.height()
                if new_w > lw or new_h > lh:
                    new_img = QImage(max(new_w, lw), max(new_h, lh),
                                     QImage.Format.Format_ARGB32_Premultiplied)
                    new_img.fill(Qt.GlobalColor.transparent)
                    p = QPainter(new_img)
                    p.drawImage(0, 0, layer.image)
                    p.end()
                    layer.image = new_img
            self._document.width  = new_w
            self._document.height = new_h
            self._canvas_refresh()
            self._canvas.reset_zoom()
            self._refresh_layers()

    def _apply_crop(self):
        from tools.other_tools import CropTool
        tool = self._tools.get("Crop")
        if isinstance(tool, CropTool) and tool.pending_rect:
            self._push_history(tr("history.crop"))
            self._document.apply_crop(tool.pending_rect)
            tool.pending_rect = None
            self._canvas_refresh()
            self._canvas.reset_zoom()
            self._refresh_layers()

    def _apply_perspective_crop(self):
        from tools.other_tools import PerspectiveCropTool
        tool = self._tools.get("Perspective Crop")
        if isinstance(tool, PerspectiveCropTool) and tool.pending_quad:
            self._push_history(tr("history.perspective_crop"))
            self._document.apply_perspective_crop(QPolygonF([QPointF(p) for p in tool.pending_quad]))
            tool.pending_quad = None
            tool.points = []
            self._canvas_refresh()
            self._canvas.reset_zoom()
            self._refresh_layers()

    def _trim(self):
        self._push_history(tr("history.trim"))
        changed = self._document.trim_transparent()
        if changed:
            self._canvas_refresh()
            self._canvas.reset_zoom()
            self._refresh_layers()

    def _change_color_mode(self, new_mode: str):
        current_mode = getattr(self._document, "color_mode", "RGB")
        if current_mode == new_mode:
            return
            
        from PyQt6.QtWidgets import QMessageBox, QColorDialog
        import numpy as np
        import ctypes
        
        duo_color = None
        if new_mode == "Duotone":
            color = QColorDialog.getColor(QColor(128, 100, 50), self, tr("adj.choose_color"))
            if not color.isValid():
                self._update_mode_menu()
                return
            duo_color = color
            
        reply = QMessageBox.question(self, "ImageFinish", tr("msg.merge_layers_mode"), 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Cancel:
            self._update_mode_menu()
            return
            
        self._push_history(tr("history.color_mode"))
        
        if reply == QMessageBox.StandardButton.Yes:
            self._document.flatten()
            
        self._document.color_mode = new_mode
        
        for layer in self._document.layers:
            if layer.image.isNull() or getattr(layer, "layer_type", "raster") != "raster":
                continue
                
            img = layer.image.copy()
            w, h = img.width(), img.height()
            
            if new_mode == "Indexed":
                img = img.convertToFormat(QImage.Format.Format_Indexed8).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                layer.image = img
                continue
                
            ptr = img.bits()
            buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
            arr = np.ndarray((h, img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :w]
            
            B = arr[..., 0].astype(np.float32)
            G = arr[..., 1].astype(np.float32)
            R = arr[..., 2].astype(np.float32)
            
            if new_mode in ("Grayscale", "Bitmap", "Duotone"):
                gray = 0.299 * R + 0.587 * G + 0.114 * B
                
                if new_mode == "Bitmap":
                    gray = np.where(gray >= 128, 255.0, 0.0)
                    arr[..., 0] = gray.astype(np.uint8)
                    arr[..., 1] = gray.astype(np.uint8)
                    arr[..., 2] = gray.astype(np.uint8)
                elif new_mode == "Grayscale":
                    arr[..., 0] = gray.astype(np.uint8)
                    arr[..., 1] = gray.astype(np.uint8)
                    arr[..., 2] = gray.astype(np.uint8)
                elif new_mode == "Duotone" and duo_color:
                    dr, dg, db = duo_color.red(), duo_color.green(), duo_color.blue()
                    t = gray / 255.0
                    arr[..., 2] = np.clip(dr * (1 - t) + 255 * t, 0, 255).astype(np.uint8)
                    arr[..., 1] = np.clip(dg * (1 - t) + 255 * t, 0, 255).astype(np.uint8)
                    arr[..., 0] = np.clip(db * (1 - t) + 255 * t, 0, 255).astype(np.uint8)
                    
            elif new_mode == "CMYK":
                C = 1.0 - R / 255.0
                M = 1.0 - G / 255.0
                Y_ = 1.0 - B / 255.0
                K = np.minimum(C, np.minimum(M, Y_))
                
                inv_K = 1.0 - K
                arr[..., 2] = np.clip((1.0 - C) * inv_K * 255, 0, 255).astype(np.uint8)
                arr[..., 1] = np.clip((1.0 - M) * inv_K * 255, 0, 255).astype(np.uint8)
                arr[..., 0] = np.clip((1.0 - Y_) * inv_K * 255, 0, 255).astype(np.uint8)
                
            layer.image = img
            
        self._update_mode_menu()
        self._canvas_refresh()
        self._refresh_layers()

    def _change_bit_depth(self, new_depth: int):
        current_depth = getattr(self._document, "bit_depth", 8)
        if current_depth == new_depth:
            return
            
        self._push_history(tr("history.bit_depth"))
        self._document.bit_depth = new_depth
        self._update_mode_menu()

    def _reveal_all(self):
        self._push_history(tr("history.reveal_all"))
        changed = self._document.reveal_all()
        if changed:
            self._canvas_refresh()
            self._canvas.reset_zoom()
            self._refresh_layers()
