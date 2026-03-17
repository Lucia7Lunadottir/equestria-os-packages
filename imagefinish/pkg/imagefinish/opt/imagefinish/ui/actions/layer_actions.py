from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QPainter, QColor
from core.locale import tr


class LayerActionsMixin:
    def _refresh_layers(self):
        if not self._document:
            return
        self._layers_panel.refresh(self._document)
        self._update_status()

    def _on_layer_selected(self, index: int):
        self._document.active_layer_index = index
        self._refresh_layers()

    def _on_layer_visibility(self, index: int, visible: bool):
        self._document.layers[index].visible = visible
        self._canvas_refresh()

    def _on_layer_opacity(self, index: int, opacity: float):
        self._document.layers[index].opacity = opacity
        self._canvas_refresh()
        self._refresh_layers()

    def _add_layer(self):
        self._push_history(tr("history.add_layer"))
        self._document.add_layer()
        self._refresh_layers()
        self._canvas_refresh()

    def _duplicate_layer(self):
        self._push_history(tr("history.duplicate_layer"))
        self._document.duplicate_layer(self._document.active_layer_index)
        self._refresh_layers()
        self._canvas_refresh()

    def _delete_layer(self):
        if len(self._document.layers) <= 1:
            QMessageBox.warning(self, tr("err.title.delete_layer"), tr("err.delete_last_layer"))
            return
        self._push_history(tr("history.delete_layer"))
        self._document.remove_layer(self._document.active_layer_index)
        self._refresh_layers()
        self._canvas_refresh()

    def _layer_up(self):
        i = self._document.active_layer_index
        self._push_history(tr("history.layer_up"))
        self._document.move_layer(i, i + 1)
        self._refresh_layers()
        self._canvas_refresh()

    def _layer_down(self):
        i = self._document.active_layer_index
        self._push_history(tr("history.layer_down"))
        self._document.move_layer(i, i - 1)
        self._refresh_layers()
        self._canvas_refresh()

    def _merge_down(self):
        i = self._document.active_layer_index
        if i == 0:
            return
        self._push_history(tr("history.merge_down"))
        bottom = self._document.layers[i - 1]
        top    = self._document.layers[i]
        p = QPainter(bottom.image)
        p.setOpacity(top.opacity)
        p.drawImage(top.offset, top.image)
        p.end()
        self._document.remove_layer(i)
        self._refresh_layers()
        self._canvas_refresh()

    def _flatten(self):
        self._push_history(tr("history.flatten"))
        self._document.flatten()
        self._refresh_layers()
        self._canvas_refresh()

    # ── Adjustment layers ─────────────────────────────────────────────────

    def _new_adj_layer(self, adj_type: str = "brightness_contrast"):
        from ui.adjustment_layer_dialog import AdjustmentLayerDialog
        from core.layer import Layer
        init = {"type": adj_type}
        dlg = AdjustmentLayerDialog(init, self)
        if not dlg.exec():
            return
        self._push_history(tr("history.new_adj_layer"))
        data = dlg.result_data()
        layer = Layer(tr("layer.name.adjustment"), self._document.width, self._document.height)
        layer.layer_type = "adjustment"
        layer.adjustment_data = data
        i = self._document.active_layer_index + 1
        self._document.layers.insert(i, layer)
        self._document.active_layer_index = i
        self._refresh_layers()
        self._canvas_refresh()

    def _edit_adj_layer(self):
        layer = self._document.get_active_layer()
        if not layer or layer.layer_type != "adjustment":
            return
        from ui.adjustment_layer_dialog import AdjustmentLayerDialog
        dlg = AdjustmentLayerDialog(layer.adjustment_data, self)
        if not dlg.exec():
            return
        self._push_history(tr("history.edit_adj_layer"))
        layer.adjustment_data = dlg.result_data()
        self._canvas_refresh()

    # ── Fill layers ───────────────────────────────────────────────────────

    def _new_fill_layer(self, fill_type: str = "solid"):
        from ui.fill_layer_dialog import FillLayerDialog
        from core.layer import Layer
        init = {"type": fill_type, "color": QColor(128, 128, 128)}
        dlg = FillLayerDialog(init, self)
        if not dlg.exec():
            return
        self._push_history(tr("history.new_fill_layer"))
        data = dlg.result_data()
        layer = Layer(tr("layer.name.fill"), self._document.width, self._document.height)
        layer.layer_type = "fill"
        layer.fill_data = data
        i = self._document.active_layer_index + 1
        self._document.layers.insert(i, layer)
        self._document.active_layer_index = i
        self._refresh_layers()
        self._canvas_refresh()

    def _edit_fill_layer(self):
        layer = self._document.get_active_layer()
        if not layer or layer.layer_type != "fill":
            return
        from ui.fill_layer_dialog import FillLayerDialog
        dlg = FillLayerDialog(layer.fill_data, self)
        if not dlg.exec():
            return
        self._push_history(tr("history.edit_fill_layer"))
        layer.fill_data = dlg.result_data()
        self._canvas_refresh()

    def _on_edit_layer(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        if layer.layer_type == "adjustment":
            self._edit_adj_layer()
        elif layer.layer_type == "fill":
            self._edit_fill_layer()

    # ── Smart objects ─────────────────────────────────────────────────────

    def _new_smart_object(self):
        layer = self._document.get_active_layer()
        if not layer or layer.layer_type == "smart_object":
            return
        self._push_history(tr("history.new_smart_object"))
        layer.smart_data = {"original": layer.image.copy()}
        layer.layer_type = "smart_object"
        self._refresh_layers()

    def _rasterize_layer(self):
        layer = self._document.get_active_layer()
        if not layer or layer.layer_type == "raster":
            return
        self._push_history(tr("history.rasterize_layer"))
        ltype = layer.layer_type
        if ltype == "fill":
            from core.document import _render_fill_layer
            layer.image = _render_fill_layer(layer, self._document.width,
                                             self._document.height)
        elif ltype == "adjustment":
            layer.image.fill(0)
        layer.layer_type = "raster"
        layer.adjustment_data = None
        layer.fill_data = None
        layer.shape_data = None
        layer.text_data = None
        layer.smart_data = None
        self._refresh_layers()
        self._canvas_refresh()
