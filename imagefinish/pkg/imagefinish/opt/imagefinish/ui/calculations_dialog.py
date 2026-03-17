import numpy as np
import ctypes
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QCheckBox, QDialogButtonBox, QWidget)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QRegion, QBitmap, QColor, QPixmap
from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _const_arr, _SliderRow

def _lbl(text):
    l = QLabel(text)
    l.setFixedWidth(100)
    return l

def _get_full_doc_image(doc, layer_idx):
    img = QImage(doc.width, doc.height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    if layer_idx == -1:
        comp = doc.get_composite()
        p = QPainter(img)
        p.drawImage(0, 0, comp)
        p.end()
    else:
        layer = doc.layers[layer_idx]
        p = QPainter(img)
        p.setOpacity(layer.opacity)
        p.drawImage(layer.offset, layer.image)
        p.end()
    return img

def _get_source_array(img, channel_idx):
    argb = _to_argb32(img)
    arr = _const_arr(argb)
    if channel_idx == 0:
        return arr[..., :3].astype(np.float32) / 255.0
    elif channel_idx == 1:
        return arr[..., 2:3].astype(np.float32) / 255.0
    elif channel_idx == 2:
        return arr[..., 1:2].astype(np.float32) / 255.0
    elif channel_idx == 3:
        return arr[..., 0:1].astype(np.float32) / 255.0
    elif channel_idx == 4:
        return arr[..., 3:4].astype(np.float32) / 255.0

def _get_source_gray(img, channel_idx):
    argb = _to_argb32(img)
    arr = _const_arr(argb)
    if channel_idx == 0:
        return (0.299 * arr[..., 2] + 0.587 * arr[..., 1] + 0.114 * arr[..., 0]).astype(np.float32) / 255.0
    elif channel_idx == 1: return arr[..., 2].astype(np.float32) / 255.0
    elif channel_idx == 2: return arr[..., 1].astype(np.float32) / 255.0
    elif channel_idx == 3: return arr[..., 0].astype(np.float32) / 255.0
    elif channel_idx == 4: return arr[..., 3].astype(np.float32) / 255.0

def _blend_arrays(base, blend, mode, opacity):
    if mode == "Normal": res = blend
    elif mode == "Multiply": res = base * blend
    elif mode == "Screen": res = 1.0 - (1.0 - base) * (1.0 - blend)
    elif mode == "Overlay":
        res = np.where(base < 0.5, 2 * base * blend, 1.0 - 2 * (1.0 - base) * (1.0 - blend))
    elif mode == "Add": res = np.clip(base + blend, 0.0, 1.0)
    elif mode == "Subtract": res = np.clip(base - blend, 0.0, 1.0)
    elif mode == "Difference": res = np.abs(base - blend)
    else: res = blend
    return base * (1.0 - opacity) + res * opacity


class ApplyImageDialog(QDialog):
    def __init__(self, document, canvas_refresh, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("menu.apply_image"))
        self.setMinimumWidth(340)
        self.document = document
        self.layer = document.get_active_layer()
        self.canvas_refresh = canvas_refresh
        
        self.original_img = self.layer.image.copy()
        self.original_offset = QPoint(self.layer.offset)
        
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._apply_preview)
        
        self._build_ui()
        self._apply_preview()
        
    def _build_ui(self):
        lo = QVBoxLayout(self)
        
        src_lo = QHBoxLayout()
        src_lo.addWidget(_lbl(tr("calc.layer")))
        self.layer_cb = QComboBox()
        self.layer_cb.addItem(tr("calc.merged"), -1)
        for i, l in enumerate(self.document.layers):
            self.layer_cb.addItem(l.name, i)
        src_lo.addWidget(self.layer_cb, 1)
        lo.addLayout(src_lo)
        
        ch_lo = QHBoxLayout()
        ch_lo.addWidget(_lbl(tr("calc.channel")))
        self.ch_cb = QComboBox()
        self.ch_cb.addItem(tr("ch.rgb"), 0)
        self.ch_cb.addItem(tr("ch.red"), 1)
        self.ch_cb.addItem(tr("ch.green"), 2)
        self.ch_cb.addItem(tr("ch.blue"), 3)
        self.ch_cb.addItem(tr("ch.alpha"), 4)
        ch_lo.addWidget(self.ch_cb, 1)
        
        self.inv_cb = QCheckBox(tr("menu.invert"))
        ch_lo.addWidget(self.inv_cb)
        lo.addLayout(ch_lo)
        
        blend_lo = QHBoxLayout()
        blend_lo.addWidget(_lbl(tr("calc.blending")))
        self.blend_cb = QComboBox()
        for m in ["Normal", "Multiply", "Screen", "Overlay", "Add", "Subtract", "Difference"]:
            self.blend_cb.addItem(tr(f"blend.{m.lower()}"), m)
        blend_lo.addWidget(self.blend_cb, 1)
        lo.addLayout(blend_lo)
        
        self.op_sl = _SliderRow(tr("calc.opacity"), 0, 100, 100)
        lo.addLayout(self.op_sl)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.cancel)
        lo.addWidget(btns)
        
        self.layer_cb.currentIndexChanged.connect(self._trigger)
        self.ch_cb.currentIndexChanged.connect(self._trigger)
        self.inv_cb.stateChanged.connect(self._trigger)
        self.blend_cb.currentIndexChanged.connect(self._trigger)
        self.op_sl.valueChanged.connect(self._trigger)
        
    def _trigger(self):
        self._timer.start()
        
    def _apply_preview(self):
        src_img = _get_full_doc_image(self.document, self.layer_cb.currentData())
        src_arr = _get_source_array(src_img, self.ch_cb.currentData())
        if self.inv_cb.isChecked(): src_arr = 1.0 - src_arr
            
        tgt_img = _get_full_doc_image(self.document, self.document.active_layer_index)
        tgt_arr = _get_source_array(tgt_img, 0)
        
        op = self.op_sl.value() / 100.0
        mode = self.blend_cb.currentData()
        
        res_arr = _blend_arrays(tgt_arr, src_arr, mode, op)
        
        h, w = self.document.height, self.document.width
        out = np.empty((h, w, 4), dtype=np.uint8)
        out[..., :3] = np.clip(res_arr * 255.0, 0, 255).astype(np.uint8)
        
        t_arr = _const_arr(_to_argb32(tgt_img))
        out[..., 3] = t_arr[..., 3]
        
        new_img = QImage(w, h, QImage.Format.Format_ARGB32)
        ctypes.memmove(int(new_img.bits()), out.ctypes.data, new_img.sizeInBytes())
        self.layer.image = new_img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self.layer.offset = QPoint(0, 0)
        self.canvas_refresh()
        
    def cancel(self):
        self._timer.stop()
        self.layer.image = self.original_img
        self.layer.offset = self.original_offset
        self.canvas_refresh()
        self.reject()


class CalculationsDialog(QDialog):
    def __init__(self, document, canvas_refresh, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("menu.calculations"))
        self.document = document
        self.canvas_refresh = canvas_refresh
        self.result_mask = None
        
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._update_preview)
        
        self._build_ui()
        self._update_preview()
        
    def _build_ui(self):
        lo = QVBoxLayout(self)
        
        self.preview_lbl = QLabel()
        self.preview_lbl.setFixedSize(256, 256)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("background-color: #000; border: 1px solid #555;")
        lo.addWidget(self.preview_lbl, 0, Qt.AlignmentFlag.AlignHCenter)
        
        def make_src(title):
            w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
            l.addWidget(QLabel(title, styleSheet="color:#a6adc8; font-weight:bold; margin-top:8px;"))
            
            lay_cb = QComboBox()
            lay_cb.addItem(tr("calc.merged"), -1)
            for i, ly in enumerate(self.document.layers): lay_cb.addItem(ly.name, i)
            l.addWidget(lay_cb)
            
            ch_cb = QComboBox()
            for txt, idx in [(tr("ch.rgb"),0), (tr("ch.red"),1), (tr("ch.green"),2), (tr("ch.blue"),3), (tr("ch.alpha"),4)]:
                ch_cb.addItem(txt, idx)
            
            inv_cb = QCheckBox(tr("menu.invert"))
            chr = QHBoxLayout(); chr.addWidget(ch_cb, 1); chr.addWidget(inv_cb)
            l.addLayout(chr)
            return w, lay_cb, ch_cb, inv_cb
            
        self.w1, self.l1_cb, self.c1_cb, self.i1_cb = make_src(tr("calc.source") + " 1")
        self.w2, self.l2_cb, self.c2_cb, self.i2_cb = make_src(tr("calc.source") + " 2")
        srcs = QHBoxLayout(); srcs.addWidget(self.w1); srcs.addWidget(self.w2); lo.addLayout(srcs)
        
        blend_lo = QHBoxLayout()
        blend_lo.addWidget(_lbl(tr("calc.blending")))
        self.blend_cb = QComboBox()
        for m in ["Normal", "Multiply", "Screen", "Overlay", "Add", "Subtract", "Difference"]:
            self.blend_cb.addItem(tr(f"blend.{m.lower()}"), m)
        blend_lo.addWidget(self.blend_cb, 1)
        lo.addLayout(blend_lo)
        
        self.op_sl = _SliderRow(tr("calc.opacity"), 0, 100, 100)
        lo.addLayout(self.op_sl)
        
        res_lo = QHBoxLayout()
        res_lo.addWidget(_lbl(tr("calc.result")))
        self.res_cb = QComboBox()
        for txt, v in [(tr("calc.res_selection"), "selection"), (tr("calc.res_channel"), "channel"), (tr("sam.out.new_layer"), "layer")]:
            self.res_cb.addItem(txt, v)
        res_lo.addWidget(self.res_cb, 1)
        lo.addLayout(res_lo)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lo.addWidget(btns)
        
        for w in [self.l1_cb, self.c1_cb, self.l2_cb, self.c2_cb, self.blend_cb, self.res_cb]: w.currentIndexChanged.connect(self._trigger)
        for w in [self.i1_cb, self.i2_cb]: w.stateChanged.connect(self._trigger)
        self.op_sl.valueChanged.connect(self._trigger)
        
    def _trigger(self):
        self._timer.start()
        
    def _update_preview(self):
        img1 = _get_full_doc_image(self.document, self.l1_cb.currentData())
        arr1 = _get_source_gray(img1, self.c1_cb.currentData())
        if self.i1_cb.isChecked(): arr1 = 1.0 - arr1
        
        img2 = _get_full_doc_image(self.document, self.l2_cb.currentData())
        arr2 = _get_source_gray(img2, self.c2_cb.currentData())
        if self.i2_cb.isChecked(): arr2 = 1.0 - arr2
        
        op = self.op_sl.value() / 100.0
        mode = self.blend_cb.currentData()
        res_arr = _blend_arrays(arr1, arr2, mode, op)
        
        h, w = res_arr.shape
        self.result_mask = res_arr
        
        preview_img = QImage(w, h, QImage.Format.Format_Grayscale8)
        p_ptr = preview_img.bits()
        p_buf = (ctypes.c_uint8 * preview_img.sizeInBytes()).from_address(int(p_ptr))
        np.ndarray((h, preview_img.bytesPerLine()), dtype=np.uint8, buffer=p_buf)[:, :w] = np.clip(res_arr * 255, 0, 255).astype(np.uint8)
        
        pixmap = QPixmap.fromImage(preview_img).scaled(self.preview_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview_lbl.setPixmap(pixmap)
        
    def apply_result(self, main_window):
        if self.result_mask is None: return
        res = self.res_cb.currentData()
        h, w = self.result_mask.shape
        mask_u8 = np.clip(self.result_mask * 255, 0, 255).astype(np.uint8)
        
        if res in ("selection", "channel"):
            mask_img = QImage(w, h, QImage.Format.Format_RGBA8888)
            mask_img.fill(0)
            m_ptr = mask_img.bits()
            m_buf = (ctypes.c_uint8 * mask_img.sizeInBytes()).from_address(int(m_ptr))
            m_arr = np.ndarray((h, mask_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=m_buf)
            m_arr[:, :w, 3] = mask_u8
            
            path = QPainterPath()
            path.addRegion(QRegion(QBitmap.fromImage(mask_img.createAlphaMask())))
            path = path.simplified()
            
            if res == "selection": self.document.selection = path
            else:
                if not hasattr(self.document, "alpha_channels"): self.document.alpha_channels = []
                self.document.alpha_channels.append({"name": "Alpha " + str(len(self.document.alpha_channels)+1), "path": path})
                if hasattr(main_window, "_channels_panel"): main_window._channels_panel.refresh(self.document)
                
        elif res == "layer":
            new_layer = self.document.add_layer("Calculations", self.document.active_layer_index + 1)
            out = np.empty((h, w, 4), dtype=np.uint8)
            out[..., 0] = out[..., 1] = out[..., 2] = mask_u8
            out[..., 3] = 255
            new_img = QImage(w, h, QImage.Format.Format_ARGB32)
            ctypes.memmove(int(new_img.bits()), out.ctypes.data, new_img.sizeInBytes())
            new_layer.image = new_img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            
        main_window._canvas_refresh()
        main_window._refresh_layers()