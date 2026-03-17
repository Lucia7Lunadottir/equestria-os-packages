from core.locale import tr


class FilterActionsMixin:
    def _blur_average(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import apply_average
        self._push_history(tr("history.average"))
        layer.image = apply_average(layer.image)
        self._canvas_refresh()

    def _blur_simple(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import apply_blur
        self._push_history(tr("history.blur"))
        layer.image = apply_blur(layer.image)
        self._canvas_refresh()

    def _blur_more(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import apply_blur_more
        self._push_history(tr("history.blur_more"))
        layer.image = apply_blur_more(layer.image)
        self._canvas_refresh()

    def _box_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import BoxBlurDialog
        self._push_history(tr("history.before_box_blur"))
        BoxBlurDialog(layer, self._canvas_refresh, self).exec()

    def _gaussian_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import GaussianBlurDialog
        self._push_history(tr("history.before_gaussian"))
        GaussianBlurDialog(layer, self._canvas_refresh, self).exec()

    def _motion_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.motion_blur import MotionBlurDialog
        self._push_history(tr("history.before_motion"))
        MotionBlurDialog(layer, self._canvas_refresh, self).exec()

    def _radial_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.radial_blur import RadialBlurDialog
        self._push_history(tr("history.before_radial"))
        RadialBlurDialog(layer, self._canvas_refresh, self).exec()

    def _smart_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import SmartBlurDialog
        self._push_history(tr("history.before_smart"))
        SmartBlurDialog(layer, self._canvas_refresh, self).exec()

    def _surface_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import SurfaceBlurDialog
        self._push_history(tr("history.before_surface"))
        SurfaceBlurDialog(layer, self._canvas_refresh, self).exec()

    def _shape_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import ShapeBlurDialog
        self._push_history(tr("history.before_shape"))
        ShapeBlurDialog(layer, self._canvas_refresh, self).exec()

    def _lens_blur(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        from core.filters.blur_filters import LensBlurDialog
        self._push_history(tr("history.before_lens"))
        LensBlurDialog(layer, self._canvas_refresh, self).exec()
