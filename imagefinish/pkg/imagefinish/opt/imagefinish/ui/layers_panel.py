from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem,
                             QCheckBox, QAbstractItemView, QMenu, QComboBox, QLineEdit)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QPen

from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


def _make_eye_icon(visible: bool) -> QIcon:
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    if visible:
        p.setPen(QColor(200, 200, 220))
        p.drawEllipse(4, 6, 12, 8)
        p.setBrush(QColor(140, 120, 200))
        p.drawEllipse(7, 8, 6, 6)
    else:
        p.setPen(QColor(80, 80, 100))
        p.drawLine(2, 2, 18, 18)
        p.drawEllipse(4, 6, 12, 8)
    p.end()
    return QIcon(pix)


class ClickableLabel(QLabel):
    clicked = pyqtSignal(bool)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.clicked.emit(shift)
        super().mousePressEvent(ev)


class LayerListWidget(QListWidget):
    order_dropped = pyqtSignal(int, int)
    
    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        
    def dropEvent(self, event):
        from_row = self.currentRow()
        pos = event.position().toPoint()
        target_item = self.itemAt(pos)
        to_row = self.row(target_item) if target_item else self.count() - 1
        
        if from_row != to_row and from_row >= 0 and to_row >= 0:
            self.order_dropped.emit(from_row, to_row)
        event.ignore()  # Не даем QListWidget удалить наши кастомные виджеты строк!


class LayerNameEdit(QLineEdit):
    def __init__(self, text):
        super().__init__(text)
        self.setFrame(False)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.editingFinished.connect(self.clearFocus)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setReadOnly(False)
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self.setFocus()
            self.selectAll()
        else:
            super().mouseDoubleClickEvent(ev)

    def focusOutEvent(self, ev):
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setSelection(0, 0)
        super().focusOutEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.clearFocus()
        else:
            super().keyPressEvent(ev)


class LayerItem(QWidget):
    """
    Custom widget for one row in the layers list.
    Shows:  👁 [thumbnail]  Name          [opacity]
    """
    visibility_toggled = pyqtSignal(int, bool)   # (row_index, new_visible)
    selected           = pyqtSignal(int)          # row_index
    name_changed       = pyqtSignal(int, str)     # row_index, new_name
    expanded_toggled   = pyqtSignal(int, bool)    # row_index, is_expanded
    target_clicked     = pyqtSignal(int, str)     # row_index, target ("image" | "mask")
    mask_toggled       = pyqtSignal(int)          # row_index
    vmask_toggled      = pyqtSignal(int)          # row_index
    clipping_toggled   = pyqtSignal(int)          # row_index
    style_requested    = pyqtSignal(int)          # row_index

    def __init__(self, layer, index: int, is_active: bool, depth: int = 0, parent=None):
        super().__init__(parent)
        self._index = index
        lo = QHBoxLayout(self)
        lo.setContentsMargins(4, 2, 4, 2)
        lo.setSpacing(6)

        # Visibility toggle
        self._vis_btn = QPushButton("👁")
        self._vis_btn.setObjectName("smallBtn")
        self._vis_btn.setFixedSize(32, 24)
        self._vis_btn.setCheckable(True)
        self._vis_btn.setChecked(layer.visible)
        self._vis_btn.setToolTip(tr("layer.toggle_visibility"))
        self._vis_btn.clicked.connect(
            lambda checked: self.visibility_toggled.emit(index, checked))
        lo.addWidget(self._vis_btn)

        if getattr(layer, "clipping", False):
            clip_lbl = QLabel("↳")
            clip_lbl.setStyleSheet("color: #a6adc8; font-weight: bold; font-size: 16px;")
            clip_lbl.setFixedWidth(18)
            lo.addWidget(clip_lbl)

        if depth > 0:
            indent = QLabel("")
            indent.setFixedWidth(depth * 16)
            lo.addWidget(indent)
            
        ltype = getattr(layer, "layer_type", "raster")
        if ltype in ("group", "artboard"):
            self._exp_btn = QPushButton("▼" if getattr(layer, "expanded", True) else "▶")
            self._exp_btn.setFixedSize(16, 16)
            self._exp_btn.setStyleSheet("border: none; background: transparent; color: #a6adc8; font-size: 10px; padding: 0;")
            self._exp_btn.clicked.connect(lambda checked=False, idx=index, l=layer: self.expanded_toggled.emit(idx, not getattr(l, "expanded", True)))
            lo.addWidget(self._exp_btn)
        else:
            ph = QLabel("")
            ph.setFixedSize(16, 16)
            lo.addWidget(ph)
            
        if getattr(layer, "link_id", None):
            link_lbl = QLabel("🔗")
            link_lbl.setStyleSheet("color: #a6adc8; font-size: 14px;")
            link_lbl.setFixedWidth(20)
            lo.addWidget(link_lbl)

        # Thumbnail
        self.thumb_lbl = ClickableLabel()
        thumb_pix = QPixmap.fromImage(
            layer.image.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.FastTransformation))
        self.thumb_lbl.setPixmap(thumb_pix)
        self.thumb_lbl.setFixedSize(26, 26)
        self.thumb_lbl.clicked.connect(lambda shift: self.target_clicked.emit(index, "image"))
        lo.addWidget(self.thumb_lbl)

        mask = getattr(layer, "mask", None)
        if mask is not None:
            self.mask_lbl = ClickableLabel()
            mask_pix = QPixmap.fromImage(mask.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
            
            if not getattr(layer, "mask_enabled", True):
                p = QPainter(mask_pix)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(QPen(QColor(220, 50, 50, 200), 2))
                p.drawLine(2, 2, 22, 22)
                p.drawLine(22, 2, 2, 22)
                p.end()
                
            self.mask_lbl.setPixmap(mask_pix)
            self.mask_lbl.setFixedSize(26, 26)
            self.mask_lbl.setToolTip(tr("layer.mask_tooltip"))
            self.mask_lbl.clicked.connect(lambda shift: self.mask_toggled.emit(index) if shift else self.target_clicked.emit(index, "mask"))
            lo.addWidget(self.mask_lbl)
            
            if is_active:
                if getattr(layer, "editing_mask", False):
                    self.thumb_lbl.setStyleSheet("border: 1px solid #45475a; background: white;")
                    self.mask_lbl.setStyleSheet("border: 2px solid #cba6f7; background: white;")
                else:
                    self.thumb_lbl.setStyleSheet("border: 2px solid #cba6f7; background: white;")
                    self.mask_lbl.setStyleSheet("border: 1px solid #45475a; background: white;")
            else:
                self.thumb_lbl.setStyleSheet("border: 1px solid #45475a; background: white;")
                self.mask_lbl.setStyleSheet("border: 1px solid #45475a; background: white;")
        else:
            if is_active:
                self.thumb_lbl.setStyleSheet("border: 2px solid #cba6f7; background: white;")
            else:
                self.thumb_lbl.setStyleSheet("border: 1px solid #45475a; background: white;")

        vmask = getattr(layer, "vector_mask", None)
        if vmask is not None:
            self.vmask_lbl = ClickableLabel()
            vm_pix = QPixmap(24, 24)
            vm_pix.fill(QColor(255, 255, 255))
            p = QPainter(vm_pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            bounds = vmask.boundingRect()
            scale = 1.0
            if not bounds.isEmpty():
                scale = min(20.0 / max(1.0, bounds.width()), 20.0 / max(1.0, bounds.height()))
                p.translate(12, 12)
                p.scale(scale, scale)
                p.translate(-bounds.center())
            p.setBrush(QColor(150, 150, 150))
            p.setPen(QPen(QColor(50, 50, 50), max(1.0, 1.0 / scale)))
            p.drawPath(vmask)
            p.end()
            if not getattr(layer, "vector_mask_enabled", True):
                p = QPainter(vm_pix)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(QPen(QColor(220, 50, 50, 200), 2))
                p.drawLine(2, 2, 22, 22)
                p.drawLine(22, 2, 2, 22)
                p.end()
            self.vmask_lbl.setPixmap(vm_pix)
            self.vmask_lbl.setFixedSize(26, 26)
            self.vmask_lbl.setToolTip(tr("layer.vmask_tooltip"))
            self.vmask_lbl.clicked.connect(lambda shift: self.vmask_toggled.emit(index) if shift else None)
            self.vmask_lbl.setStyleSheet("border: 1px solid #45475a; background: white;")
            lo.addWidget(self.vmask_lbl)

        # Name
        self.name_edit = LayerNameEdit(layer.name)
        if is_active:
            self.name_edit.setStyleSheet("background: transparent; color: #cba6f7; font-weight: bold;")
        else:
            self.name_edit.setStyleSheet("background: transparent; color: #cdd6f4;")
        self.name_edit.editingFinished.connect(lambda: self.name_changed.emit(index, self.name_edit.text()))
        lo.addWidget(self.name_edit, 1)

        # Opacity
        op_lbl = QLabel(f"{int(layer.opacity * 100)}%")
        op_lbl.setStyleSheet("color: #7f849c; font-size: 11px;")
        op_lbl.setFixedWidth(36)
        lo.addWidget(op_lbl)

        # Layer type badge
        ltype = getattr(layer, "layer_type", "raster")
        _BADGES = {
            "text":        ("T", "#89b4fa", "layer.type.text"),
            "vector":      ("V", "#a6e3a1", "layer.type.vector"),
            "adjustment":  ("A", "#fab387", "layer.type.adjustment"),
            "fill":        ("F", "#cba6f7", "layer.type.fill"),
            "smart_object":("S", "#f9e2af", "layer.type.smart_object"),
            "artboard":    ("◩", "#a6adc8", "layer.type.artboard"),
            "frame":       ("⛶", "#89dceb", "layer.type.frame"),
            "group":       ("📁", "#f9e2af", "layer.type.group"),
        }
        if ltype in _BADGES:
            badge_text, badge_color, tip_key = _BADGES[ltype]
            b_lbl = QLabel(badge_text)
            b_lbl.setStyleSheet(
                f"color:{badge_color}; font-weight:bold; font-size:13px;")
            b_lbl.setFixedWidth(20)
            b_lbl.setToolTip(tr(tip_key))
            lo.addWidget(b_lbl)

        # Lock indicator
        if layer.locked:
            lock_lbl = QLabel("🔒")
            lock_lbl.setFixedWidth(18)
            lo.addWidget(lock_lbl)
            
        if getattr(layer, "lock_alpha", False):
            alpha_lock_lbl = QLabel("🏁")
            alpha_lock_lbl.setFixedWidth(18)
            lo.addWidget(alpha_lock_lbl)
            
        if getattr(layer, "layer_styles", None):
            fx_lbl = QLabel("fx")
            fx_lbl.setStyleSheet("color: #a6adc8; font-weight: bold; font-style: italic; font-size: 12px;")
            fx_lbl.setFixedWidth(16)
            lo.addWidget(fx_lbl)
            
    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.style_requested.emit(self._index)
        super().mouseDoubleClickEvent(ev)


class LayersPanel(QWidget):
    """
    Right-side layers panel.
    Emits signals to let the app modify the document.
    """

    layer_selected      = pyqtSignal(int)
    layer_added         = pyqtSignal()
    layer_duplicated    = pyqtSignal()
    layer_deleted       = pyqtSignal()
    layer_renamed       = pyqtSignal(int, str)
    layer_expanded_toggled = pyqtSignal(int, bool)
    layer_moved         = pyqtSignal(int, int)
    layer_moved_up      = pyqtSignal()
    layer_moved_down    = pyqtSignal()
    layer_visibility    = pyqtSignal(int, bool)
    layer_opacity       = pyqtSignal(int, float)
    layer_lock_changed  = pyqtSignal(str, bool)
    layer_grouped       = pyqtSignal()
    layer_linked        = pyqtSignal()
    layer_blend_mode    = pyqtSignal(str)
    layer_target_changed= pyqtSignal(int, str)
    layer_mask_toggled  = pyqtSignal(int)
    layer_add_mask      = pyqtSignal()
    layer_delete_mask   = pyqtSignal()
    layer_apply_mask    = pyqtSignal()
    layer_invert_mask   = pyqtSignal()
    layer_add_vector_mask    = pyqtSignal()
    layer_delete_vector_mask = pyqtSignal()
    layer_vmask_toggled      = pyqtSignal(int)
    layer_clipping_toggled   = pyqtSignal(int)
    layer_merged_down   = pyqtSignal()
    layer_flatten       = pyqtSignal()
    layer_edit          = pyqtSignal()
    layer_smart_object  = pyqtSignal()
    layer_rasterize     = pyqtSignal()
    layer_styles_requested = pyqtSignal(int)
    layer_clear_smart_filters = pyqtSignal()
    layer_export_png          = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title
        self._title_lbl = QLabel(tr("panel.layers"))
        self._title_lbl.setObjectName("panelTitle")
        layout.addWidget(self._title_lbl)

        # Blend mode
        blend_widget = QWidget()
        blend_lo = QHBoxLayout(blend_widget)
        blend_lo.setContentsMargins(8, 2, 8, 2)
        blend_lo.setSpacing(6)
        self._blend_lbl = QLabel(tr("opts.blend_mode"))
        blend_lo.addWidget(self._blend_lbl)
        self._blend_combo = QComboBox()
        modes = [
            ("blend.normal", "SourceOver"), ("blend.multiply", "Multiply"),
            ("blend.screen", "Screen"), ("blend.overlay", "Overlay"),
            ("blend.darken", "Darken"), ("blend.lighten", "Lighten"),
            ("blend.color_dodge", "ColorDodge"), ("blend.color_burn", "ColorBurn"),
            ("blend.hard_light", "HardLight"), ("blend.soft_light", "SoftLight"),
            ("blend.difference", "Difference"), ("blend.exclusion", "Exclusion")
        ]
        for loc_key, val in modes:
            self._blend_combo.addItem(tr(loc_key), val)
        self._blend_combo.activated.connect(lambda idx: self.layer_blend_mode.emit(self._blend_combo.itemData(idx)))
        blend_lo.addWidget(self._blend_combo, 1)
        layout.addWidget(blend_widget)

        # Opacity slider for active layer
        op_widget = QWidget()
        op_lo = QHBoxLayout(op_widget)
        op_lo.setContentsMargins(8, 2, 8, 2)
        op_lo.setSpacing(6)
        self._opacity_lbl = QLabel(tr("panel.opacity"))
        op_lo.addWidget(self._opacity_lbl)
        self._opacity_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        op_lo.addWidget(self._opacity_slider, 1)
        self._opacity_label = QLabel("100%")
        self._opacity_label.setFixedWidth(36)
        self._opacity_label.setStyleSheet("color: #7f849c; font-size:11px;")
        op_lo.addWidget(self._opacity_label)
        layout.addWidget(op_widget)

        locks_widget = QWidget()
        locks_lo = QHBoxLayout(locks_widget)
        locks_lo.setContentsMargins(8, 2, 8, 2)
        locks_lo.setSpacing(4)
        self._lock_lbl = QLabel(tr("panel.lock"))
        self._lock_lbl.setStyleSheet("color: #a6adc8; font-size:12px;")
        locks_lo.addWidget(self._lock_lbl)

        self._btn_lock_pixels = QPushButton("🖌️")
        self._btn_lock_pos = QPushButton("✋")
        self._btn_lock_artboard = QPushButton("🔲")
        self._btn_lock_alpha = QPushButton("🏁")
        self._btn_lock_all = QPushButton("🔒")

        for btn in (self._btn_lock_pixels, self._btn_lock_pos, self._btn_lock_artboard, self._btn_lock_alpha, self._btn_lock_all):
            btn.setCheckable(True)
            btn.setFixedSize(32, 28)
            btn.setObjectName("smallBtn")
            locks_lo.addWidget(btn)

        self._btn_lock_pixels.toggled.connect(lambda v: self.layer_lock_changed.emit("pixels", v))
        self._btn_lock_pos.toggled.connect(lambda v: self.layer_lock_changed.emit("position", v))
        self._btn_lock_artboard.toggled.connect(lambda v: self.layer_lock_changed.emit("artboard", v))
        self._btn_lock_alpha.toggled.connect(lambda v: self.layer_lock_changed.emit("alpha", v))
        self._btn_lock_all.toggled.connect(lambda v: self.layer_lock_changed.emit("all", v))
        locks_lo.addStretch()
        layout.addWidget(locks_widget)

        # Layer list
        self._list = LayerListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        self._list.order_dropped.connect(self._on_layer_drag_drop)
        layout.addWidget(self._list, 1)

        # Bottom buttons
        btn_bar = QWidget()
        btn_lo = QHBoxLayout(btn_bar)
        btn_lo.setContentsMargins(6, 4, 6, 6)
        btn_lo.setSpacing(4)

        def _make_btn(text, tip_key, signal):
            b = QPushButton(text)
            b.setObjectName("smallBtn")
            b.setFixedSize(32, 28)
            b.setToolTip(tr(tip_key))
            b.clicked.connect(signal.emit)
            return b

        self._link_btn = _make_btn("🔗", "layer.btn.link",      self.layer_linked)
        self._grp_btn  = _make_btn("📁", "layer.btn.group",     self.layer_grouped)
        self._add_btn  = _make_btn("+", "layer.btn.new",       self.layer_added)
        self._dup_btn  = _make_btn("⧉", "layer.btn.duplicate", self.layer_duplicated)
        self._up_btn   = _make_btn("↑", "layer.btn.up",        self.layer_moved_up)
        self._down_btn = _make_btn("↓", "layer.btn.down",      self.layer_moved_down)
        btn_lo.addWidget(self._link_btn)
        btn_lo.addWidget(self._grp_btn)
        btn_lo.addWidget(self._add_btn)
        btn_lo.addWidget(self._dup_btn)
        btn_lo.addWidget(self._up_btn)
        btn_lo.addWidget(self._down_btn)

        self._del_btn = QPushButton("🗑")
        self._del_btn.setObjectName("dangerBtn")
        self._del_btn.setFixedSize(32, 28)
        self._del_btn.setToolTip(tr("layer.btn.delete"))
        self._del_btn.clicked.connect(self.layer_deleted.emit)
        btn_lo.addWidget(self._del_btn)

        layout.addWidget(btn_bar)

        self._document = None
        self._updating = False
        
        self.retranslate()

    # ---------------------------------------------------------------- Public
    def refresh(self, document):
        """Rebuild the list from the document."""
        self._document = document
        self._updating = True
        self._list.clear()

        layer_map = {getattr(l, "layer_id", None): l for l in document.layers}

        # Show layers in reverse order (top-most first)
        for i in range(len(document.layers) - 1, -1, -1):
            layer = document.layers[i]
            
            depth = 0
            is_hidden = False
            p_id = getattr(layer, "parent_id", None)
            while p_id:
                depth += 1
                parent = layer_map.get(p_id)
                if not parent: break
                if not getattr(parent, "expanded", True):
                    is_hidden = True
                p_id = getattr(parent, "parent_id", None)

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._list.addItem(item)

            widget = LayerItem(layer, i, i == document.active_layer_index, depth=depth)
            widget.visibility_toggled.connect(self.layer_visibility.emit)
            widget.target_clicked.connect(self.layer_target_changed.emit)
            widget.mask_toggled.connect(self.layer_mask_toggled.emit)
            widget.vmask_toggled.connect(self.layer_vmask_toggled.emit)
            widget.clipping_toggled.connect(self.layer_clipping_toggled.emit)
            widget.name_changed.connect(self.layer_renamed.emit)
            widget.expanded_toggled.connect(self.layer_expanded_toggled.emit)
            widget.style_requested.connect(self.layer_styles_requested.emit)
            item.setSizeHint(widget.sizeHint())
            self._list.setItemWidget(item, widget)
            
            if is_hidden:
                item.setHidden(True)

        # Select active layer row
        active = document.active_layer_index
        # find matching row (list is reversed)
        for row in range(self._list.count()):
            it = self._list.item(row)
            if it.data(Qt.ItemDataRole.UserRole) == active:
                self._list.setCurrentRow(row)
                break

        # Sync opacity slider
        layer = document.get_active_layer()
        if layer:
            self._opacity_slider.blockSignals(True)
            self._opacity_slider.setValue(int(layer.opacity * 100))
            self._opacity_slider.blockSignals(False)
            self._opacity_label.setText(f"{int(layer.opacity * 100)}%")

            for btn in (self._btn_lock_pixels, self._btn_lock_pos, self._btn_lock_artboard, self._btn_lock_alpha, self._btn_lock_all):
                btn.blockSignals(True)

            self._btn_lock_pixels.setChecked(getattr(layer, "lock_pixels", False))
            self._btn_lock_pos.setChecked(getattr(layer, "lock_position", False))
            self._btn_lock_artboard.setChecked(getattr(layer, "lock_artboard", False))
            self._btn_lock_alpha.setChecked(getattr(layer, "lock_alpha", False))
            self._btn_lock_all.setChecked(layer.locked)

            for btn in (self._btn_lock_pixels, self._btn_lock_pos, self._btn_lock_artboard, self._btn_lock_alpha, self._btn_lock_all):
                btn.blockSignals(False)

            self._blend_combo.blockSignals(True)
            mode = getattr(layer, "blend_mode", "SourceOver")
            idx = self._blend_combo.findData(mode)
            if idx >= 0:
                self._blend_combo.setCurrentIndex(idx)
            self._blend_combo.blockSignals(False)

        self._updating = False

    # ---------------------------------------------------------------- Private
    def _on_layer_drag_drop(self, from_row: int, to_row: int):
        if self._document:
            count = len(self._document.layers)
            doc_from = count - 1 - from_row
            doc_to = count - 1 - to_row
            self.layer_moved.emit(doc_from, doc_to)

    def _on_row_changed(self, row: int):
        if self._updating or row < 0:
            return
        item = self._list.item(row)
        if item:
            real_index = item.data(Qt.ItemDataRole.UserRole)
            self.layer_selected.emit(real_index)

    def _on_opacity_changed(self, value: int):
        self._opacity_label.setText(f"{value}%")
        if self._document and not self._updating:
            active = self._document.active_layer_index
            self.layer_opacity.emit(active, value / 100)
            
    def _on_alpha_lock_toggled(self, checked: bool):
        if self._document and not self._updating:
            active = self._document.active_layer_index
            self.layer_alpha_locked.emit(active, checked)

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction(tr("ctx.rename"), self._trigger_rename)
        menu.addAction(tr("ctx.duplicate"),  self.layer_duplicated.emit)
        menu.addAction(tr("ctx.merge_down"), self.layer_merged_down.emit)
        menu.addSeparator()
        menu.addAction(tr("ctx.flatten"),    self.layer_flatten.emit)
        menu.addSeparator()
        del_act = menu.addAction(tr("ctx.delete"))
        del_act.triggered.connect(self.layer_deleted.emit)

        layer = (self._document.get_active_layer()
                 if self._document else None)
        ltype = getattr(layer, "layer_type", "raster") if layer else "raster"

        menu.addSeparator()
        if layer:
            menu.addAction(tr("ctx.blending_options"), lambda: self.layer_styles_requested.emit(self._document.active_layer_index))
            menu.addSeparator()
            active_idx = self._document.active_layer_index
            if getattr(layer, "clipping", False):
                menu.addAction(tr("ctx.release_clipping"), lambda *args, idx=active_idx: self.layer_clipping_toggled.emit(idx))
            else:
                menu.addAction(tr("ctx.create_clipping"), lambda *args, idx=active_idx: self.layer_clipping_toggled.emit(idx))
        
        if layer and getattr(layer, "mask", None) is None:
            menu.addAction(tr("ctx.add_mask"), self.layer_add_mask.emit)
        elif layer:
            active_idx = self._document.active_layer_index
            if getattr(layer, "mask_enabled", True):
                menu.addAction(tr("ctx.disable_mask"), lambda *args, idx=active_idx: self.layer_mask_toggled.emit(idx))
            else:
                menu.addAction(tr("ctx.enable_mask"), lambda *args, idx=active_idx: self.layer_mask_toggled.emit(idx))
            menu.addAction(tr("ctx.delete_mask"), self.layer_delete_mask.emit)
            menu.addAction(tr("ctx.apply_mask"), self.layer_apply_mask.emit)
            menu.addAction(tr("ctx.invert_mask"), self.layer_invert_mask.emit)

        menu.addSeparator()
        if layer and getattr(layer, "vector_mask", None) is None:
            menu.addAction(tr("ctx.add_vector_mask"), self.layer_add_vector_mask.emit)
        elif layer:
            active_idx = self._document.active_layer_index
            if getattr(layer, "vector_mask_enabled", True):
                menu.addAction(tr("ctx.disable_vector_mask"), lambda *args, idx=active_idx: self.layer_vmask_toggled.emit(idx))
            else:
                menu.addAction(tr("ctx.enable_vector_mask"), lambda *args, idx=active_idx: self.layer_vmask_toggled.emit(idx))
            menu.addAction(tr("ctx.delete_vector_mask"), self.layer_delete_vector_mask.emit)

        menu.addSeparator()
        if layer and ltype not in ("adjustment", "fill"):
            exp_act = menu.addAction(tr("ctx.export_png"))
            exp_act.triggered.connect(self.layer_export_png.emit)

        if ltype in ("adjustment", "fill"):
            edit_act = menu.addAction(tr("ctx.edit_layer"))
            edit_act.triggered.connect(self.layer_edit.emit)
        if ltype in ("raster", "text", "vector"):
            so_act = menu.addAction(tr("ctx.smart_object"))
            so_act.triggered.connect(self.layer_smart_object.emit)
        elif ltype == "smart_object":
            clr_act = menu.addAction(tr("ctx.clear_smart_filters"))
            clr_act.triggered.connect(self.layer_clear_smart_filters.emit)
        if ltype != "raster":
            rast_act = menu.addAction(tr("ctx.rasterize"))
            rast_act.triggered.connect(self.layer_rasterize.emit)

        menu.exec(self._list.mapToGlobal(pos))

    def _trigger_rename(self):
        row = self._list.currentRow()
        if row < 0: return
        item = self._list.item(row)
        if item:
            widget = self._list.itemWidget(item)
            if hasattr(widget, "name_edit"):
                widget.name_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                widget.name_edit.setReadOnly(False)
                widget.name_edit.setCursor(Qt.CursorShape.IBeamCursor)
                widget.name_edit.setFocus()
                widget.name_edit.selectAll()

    def retranslate(self):
        """Update all static labels/tooltips to the current locale."""
        self._title_lbl.setText(tr("panel.layers"))
        self._opacity_lbl.setText(tr("panel.opacity"))
        self._blend_lbl.setText(tr("opts.blend_mode"))
        self._lock_lbl.setText(tr("panel.lock"))
        self._btn_lock_pixels.setToolTip(tr("layer.lock_pixels"))
        self._btn_lock_pos.setToolTip(tr("layer.lock_pos"))
        self._btn_lock_artboard.setToolTip(tr("layer.lock_artboard"))
        self._btn_lock_alpha.setToolTip(tr("layer.lock_alpha"))
        self._btn_lock_all.setToolTip(tr("layer.lock_all"))
        modes = [
            "blend.normal", "blend.multiply", "blend.screen", "blend.overlay",
            "blend.darken", "blend.lighten", "blend.color_dodge", "blend.color_burn",
            "blend.hard_light", "blend.soft_light", "blend.difference", "blend.exclusion"
        ]
        for i, loc_key in enumerate(modes):
            self._blend_combo.setItemText(i, tr(loc_key))
        self._link_btn.setToolTip(tr("layer.btn.link"))
        self._grp_btn.setToolTip(tr("layer.btn.group"))
        self._add_btn.setToolTip(tr("layer.btn.new"))
        self._dup_btn.setToolTip(tr("layer.btn.duplicate"))
        self._up_btn.setToolTip(tr("layer.btn.up"))
        self._down_btn.setToolTip(tr("layer.btn.down"))
        self._del_btn.setToolTip(tr("layer.btn.delete"))
