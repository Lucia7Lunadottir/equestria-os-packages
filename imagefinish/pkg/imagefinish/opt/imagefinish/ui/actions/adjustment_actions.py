from core.locale import tr


class AdjustmentActionsMixin:
    def _show_adj_dialog(self, DialogClass, history_desc: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull(): return
        self._push_history(tr(history_desc))
        import inspect
        sig = inspect.signature(DialogClass.__init__)
        params = [p for p in sig.parameters.values() if p.name != 'self']
        if len(params) >= 3 and params[1].name in ("canvas_refresh", "cb"):
            dlg = DialogClass(layer, self._canvas_refresh, self)
        else:
            dlg = DialogClass(layer.image, parent=self)
            dlg._canvas_refresh = self._canvas_refresh
        dlg.exec()

    def _levels(self):
        from ui.levels_dialog import LevelsDialog
        self._show_adj_dialog(LevelsDialog, "history.before_levels")

    def _brightness_contrast(self):
        from ui.adjustments_dialog import BrightnessContrastDialog
        self._show_adj_dialog(BrightnessContrastDialog, "history.before_bc")

    def _hue_saturation(self):
        from ui.adjustments_dialog import HueSaturationDialog
        self._show_adj_dialog(HueSaturationDialog, "history.before_hs")

    def _invert(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from ui.adjustments_dialog import apply_invert
        self._push_history(tr("history.invert"))
        layer.image = apply_invert(layer.image)
        self._canvas_refresh()

    def _exposure(self):
        from ui.more_adjustments import ExposureDialog
        self._show_adj_dialog(ExposureDialog, "history.before_exposure")

    def _vibrance(self):
        from ui.more_adjustments import VibranceDialog
        self._show_adj_dialog(VibranceDialog, "history.before_vibrance")

    def _black_white(self):
        from ui.more_adjustments import BlackWhiteDialog
        self._show_adj_dialog(BlackWhiteDialog, "history.before_bw")

    def _posterize(self):
        from ui.more_adjustments import PosterizeDialog
        self._show_adj_dialog(PosterizeDialog, "history.before_posterize")

    def _threshold(self):
        from ui.more_adjustments import ThresholdDialog
        self._show_adj_dialog(ThresholdDialog, "history.before_threshold")

    def _channel_mixer(self):
        from ui.more_adjustments import ChannelMixerDialog
        self._show_adj_dialog(ChannelMixerDialog, "history.before_mixer")

    def _selective_color(self):
        from ui.more_adjustments import SelectiveColorDialog
        self._show_adj_dialog(SelectiveColorDialog, "history.before_sel_color")

    def _match_color(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from ui.more_adjustments import MatchColorDialog
        active_idx = self._document.active_layer_index
        sources = [
            (lyr.name, lyr.image)
            for i, lyr in enumerate(self._document.layers)
            if i != active_idx
        ]
        self._push_history(tr("history.before_match_color"))
        import inspect
        sig = inspect.signature(MatchColorDialog.__init__)
        params = [p for p in sig.parameters.values() if p.name != 'self']
        if params and params[0].name == "image":
            dlg = MatchColorDialog(layer.image, sources, parent=self)
            dlg._canvas_refresh = self._canvas_refresh
        else:
            dlg = MatchColorDialog(layer, sources, self._canvas_refresh, self)
        dlg.exec()

    def _shadows_highlights(self):
        from ui.more_adjustments import ShadowsHighlightsDialog
        self._show_adj_dialog(ShadowsHighlightsDialog, "history.before_shadows_hl")

    def _replace_color(self):
        from ui.more_adjustments import ReplaceColorDialog
        self._show_adj_dialog(ReplaceColorDialog, "history.before_replace")

    def _photo_filter(self):
        from ui.more_adjustments import PhotoFilterDialog
        self._show_adj_dialog(PhotoFilterDialog, "history.before_photo_filter")

    def _gradient_map(self):
        from ui.more_adjustments import GradientMapDialog
        self._show_adj_dialog(GradientMapDialog, "history.before_gradient")

    def _color_lookup(self):
        from ui.more_adjustments import ColorLookupDialog
        self._show_adj_dialog(ColorLookupDialog, "history.before_lookup")

    def _equalize(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from ui.more_adjustments import apply_equalize
        self._push_history(tr("history.equalize"))
        layer.image = apply_equalize(layer.image)
        self._canvas_refresh()

    def _hdr_toning(self):
        from core.adjustments.hdr_toning import HDRToningDialog
        self._show_adj_dialog(HDRToningDialog, "history.before_hdr")
