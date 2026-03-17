from PyQt6.QtWidgets import QWidget, QHBoxLayout, QStackedWidget, QScrollArea, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt

from .tool_options.brush_options import BrushOptions
from .tool_options.fill_options import FillOptions
from .tool_options.gradient_options import GradientOptions
from .tool_options.select_options import SelectOptions
from .tool_options.shapes_options import ShapesOptions
from .tool_options.text_options import TextOptions
from .tool_options.crop_options import CropOptions
from .tool_options.perspective_crop_options import PerspectiveCropOptions
from .tool_options.effect_options import EffectOptions, SpongeOptions
from .tool_options.rotate_view_options import RotateViewOptions
from .tool_options.empty_options import EmptyOptions
from .tool_options.bg_eraser_options import BackgroundEraserOptions
from .tool_options.pattern_stamp_options import PatternStampOptions
from .tool_options.measure_options import ColorSamplerOptions, RulerOptions
from .tool_options.move_options import MoveOptions
from .tool_options.slice_options import SliceOptions
from .tool_options.patch_options import PatchOptions, SpotHealingOptions, RedEyeOptions
from .tool_options.pen_options import PenOptions
from .tool_options.frame_options import FrameOptions
from .tool_options.magnetic_lasso_options import MagneticLassoOptions

class ToolOptionsBar(QWidget):
    option_changed = pyqtSignal(str, object)
    apply_styles_requested = pyqtSignal()
    apply_crop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolOptionsBar")
        self.setMinimumHeight(46)
        self.setMaximumHeight(64)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._container = QWidget()
        c_layout = QHBoxLayout(self._container)
        c_layout.setContentsMargins(10, 0, 10, 0)
        c_layout.setSpacing(0)

        self._stack = QStackedWidget()
        c_layout.addWidget(self._stack, 1)
        
        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, 1)

        self._pages: dict[str, QWidget] = {}
        self._build_pages()

    def _build_pages(self):
        self._pages["Brush"] = BrushOptions()
        self._pages["Pencil"] = self._pages["Brush"]
        self._pages["ColorReplacement"] = self._pages["Brush"]
        self._pages["MixerBrush"] = self._pages["Brush"]
        self._pages["HistoryBrush"] = self._pages["Brush"]
        self._pages["CloneStamp"] = self._pages["Brush"]
        self._pages["PatternStamp"] = PatternStampOptions()
        self._pages["Fill"] = FillOptions()
        self._pages["Eraser"] = self._pages["Brush"]
        self._pages["BackgroundEraser"] = BackgroundEraserOptions()
        # Magic Eraser использует толерантность, у тебя есть FillOptions, там как раз есть Tolerance
        self._pages["MagicEraser"] = self._pages["Fill"]
        self._pages["Gradient"] = GradientOptions()
        self._pages["Select"] = SelectOptions()
        self._pages["EllipseSelect"] = self._pages["Select"]
        self._pages["Shapes"] = ShapesOptions()
        self._pages["Text"] = TextOptions()
        self._pages["TextV"] = self._pages["Text"]
        self._pages["TextHMask"] = self._pages["Text"]
        self._pages["TextVMask"] = self._pages["Text"]
        self._pages["Move"] = MoveOptions("opts.move_hint")
        
        move_page = self._pages["Move"]
        move_layout = move_page.layout() if callable(move_page.layout) else move_page.layout
        if move_layout is not None:
            from PyQt6.QtWidgets import QCheckBox
            from core.locale import tr
            self._move_auto_cb = QCheckBox(tr("opts.move.auto_select"))
            self._move_auto_cb.stateChanged.connect(lambda v: self.option_changed.emit("move_auto_select", bool(v)))
            move_layout.insertWidget(0, self._move_auto_cb)
        self._pages["Warp"] = MoveOptions("opts.warp_hint")
        self._pages["PuppetWarp"] = MoveOptions("opts.puppet_warp_hint")
        self._pages["PerspectiveWarp"] = MoveOptions("opts.perspective_warp_hint")
        self._pages["Artboard"] = EmptyOptions("tool.artboard")
        self._pages["Eyedropper"] = EmptyOptions("tool.eyedropper")
        self._pages["ColorSampler"] = ColorSamplerOptions()
        self._pages["Patch"] = PatchOptions()
        self._pages["SpotHealing"] = SpotHealingOptions("opts.spot_healing_hint")
        self._pages["HealingBrush"] = SpotHealingOptions("opts.healing_brush_hint")
        self._pages["RedEye"] = RedEyeOptions()
        self._pages["Pen"] = PenOptions()
        self._pages["FreeformPen"] = self._pages["Pen"]
        self._pages["CurvaturePen"] = self._pages["Pen"]
        self._pages["AddAnchor"] = self._pages["Pen"]
        self._pages["DeleteAnchor"] = self._pages["Pen"]
        self._pages["ConvertPoint"] = self._pages["Pen"]
        self._pages["PathSelection"] = self._pages["Pen"]
        self._pages["DirectSelection"] = self._pages["Pen"]
        self._pages["Ruler"] = RulerOptions()
        self._pages["Crop"] = CropOptions()
        self._pages["Perspective Crop"] = PerspectiveCropOptions()
        self._pages["Frame"] = FrameOptions()
        self._pages["Slice"] = SliceOptions()
        self._pages["Blur"] = EffectOptions("opts.effect.blur")
        self._pages["Sharpen"] = EffectOptions("opts.effect.sharpen")
        self._pages["Smudge"] = EffectOptions("opts.effect.smudge")
        self._pages["Dodge"] = EffectOptions("opts.effect.dodge")
        self._pages["Burn"] = EffectOptions("opts.effect.burn")
        self._pages["Sponge"] = SpongeOptions()
        self._pages["Hand"] = EmptyOptions("opts.hand_hint")
        self._pages["Zoom"] = EmptyOptions("opts.zoom_hint")
        self._pages["RotateView"] = RotateViewOptions()
        self._pages["Lasso"] = self._pages["Select"]
        self._pages["PolygonalLasso"] = self._pages["Select"]
        self._pages["MagneticLasso"] = MagneticLassoOptions()
        self._pages["MagicWand"] = self._pages["Fill"]
        self._pages["QuickSelection"] = self._pages["BackgroundEraser"]
        self._pages["ObjectSelection"] = self._pages["Select"]

        for page in set(self._pages.values()):
            page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self._stack.addWidget(page)
            if hasattr(page, "option_changed"):
                page.option_changed.connect(self.option_changed)
            if hasattr(page, "apply_styles_requested"):
                page.apply_styles_requested.connect(self.apply_styles_requested)
            if hasattr(page, "apply_crop_requested"):
                page.apply_crop_requested.connect(self.apply_crop_requested)

    def switch_to(self, tool_name: str):
        page = self._pages.get(tool_name)
        if page:
            current = self._stack.currentWidget()
            if current and current != page:
                current.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self._stack.setCurrentWidget(page)

    def update_tool_state(self, state: object):
        current = self._stack.currentWidget()
        if hasattr(current, "update_params"):
            current.update_params(state)

    def retranslate(self):
        # Используем set, чтобы не обновлять одну и ту же панель (например, BrushOptions) несколько раз
        for page in set(self._pages.values()):
            if hasattr(page, "retranslate"):
                page.retranslate()
        if hasattr(self, "_move_auto_cb"):
            from core.locale import tr
            self._move_auto_cb.setText(tr("opts.move.auto_select"))
