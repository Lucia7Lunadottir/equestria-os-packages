from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QMenu, QStatusBar, QFileDialog, QMessageBox, QSplitter, QTabWidget,
                             QStackedWidget)
from PyQt6.QtCore import Qt, QRectF, QRect, QPoint, QPointF, QSettings
from PyQt6.QtGui import QAction, QKeySequence, QColor, QPainterPath, QPainter, QBrush

from ui.canvas_widget    import CanvasWidget
from ui.toolbar          import ToolBar
from ui.tool_options_bar import ToolOptionsBar
from ui.layers_panel     import LayersPanel
from ui.color_panel      import ColorPanel

from ui.actions.file_actions       import FileActionsMixin
from ui.actions.edit_actions       import EditActionsMixin
from ui.actions.layer_actions      import LayerActionsMixin
from ui.actions.image_actions      import ImageActionsMixin
from ui.actions.adjustment_actions import AdjustmentActionsMixin
from ui.actions.filter_actions     import FilterActionsMixin

from core.document import Document
from core.history  import HistoryManager, HistoryState
from core.locale   import tr, available_languages, load as locale_load, current as locale_current


# ── Tool registry ──────────────────────────────────────────────────────────────
def _build_tool_registry(text_parent):
    from tools.brush_tool   import (BrushTool, EraserTool, CloneStampTool, PatternStampTool,
                                    PencilTool, ColorReplacementTool, MixerBrushTool, HistoryBrushTool)
    from tools.fill_tool    import FillTool
    from tools.effect_tools import BlurTool, SharpenTool, SmudgeTool, DodgeTool, BurnTool, SpongeTool
    from tools.other_tools  import (SelectTool, MoveTool, EyedropperTool,
                                    EllipticalSelectTool,
                                    CropTool, TextTool, ShapesTool,
                                    VerticalTypeTool, HorizontalTypeMaskTool,
                                    VerticalTypeMaskTool,
                                    HandTool, ZoomTool, RotateViewTool,
                                    GradientTool, PerspectiveCropTool)
    from tools.lasso_tools import LassoTool, PolygonalLassoTool, MagneticLassoTool
    from tools.measure_tools import ColorSamplerTool, RulerTool
    from tools.advanced_erasers import MagicEraserTool, BackgroundEraserTool
    from tools.magic_wand_tool import MagicWandTool, QuickSelectionTool, ObjectSelectionTool
    from tools.artboard_tool import ArtboardTool
    from tools.warp_tool import WarpTool
    from tools.puppet_warp_tool import PuppetWarpTool
    from tools.perspective_warp_tool import PerspectiveWarpTool
    from tools.slice_tool import SliceTool
    from tools.patch_tool import PatchTool, SpotHealingTool, HealingBrushTool, RedEyeTool
    from tools.pen_tool import (PenTool, FreeformPenTool, CurvaturePenTool, 
                                AddAnchorPointTool, DeleteAnchorPointTool, ConvertPointTool,
                                PathSelectionTool, DirectSelectionTool)
    from tools.frame_tool import FrameTool

    text = TextTool();  text._parent_widget  = text_parent
    textv = VerticalTypeTool(); textv._parent_widget = text_parent
    texthm = HorizontalTypeMaskTool(); texthm._parent_widget = text_parent
    textvm = VerticalTypeMaskTool();   textvm._parent_widget = text_parent
    return {
        "Brush":      BrushTool(),
        "Eraser":           EraserTool(),
        "BackgroundEraser": BackgroundEraserTool(),
        "MagicEraser":      MagicEraserTool(),
        "CloneStamp":       CloneStampTool(),
        "PatternStamp":     PatternStampTool(),
        "Pencil":           PencilTool(),
        "ColorReplacement": ColorReplacementTool(),
        "MixerBrush":       MixerBrushTool(),
        "HistoryBrush":     HistoryBrushTool(),
        "Fill":       FillTool(),
        "Blur":       BlurTool(),
        "Sharpen":    SharpenTool(),
        "Smudge":     SmudgeTool(),
        "Dodge":      DodgeTool(),
        "Burn":       BurnTool(),
        "Sponge":     SpongeTool(),
        "Select":     SelectTool(),
        "EllipseSelect": EllipticalSelectTool(),
        "Move":       MoveTool(),
        "Warp":       WarpTool(),
        "PuppetWarp": PuppetWarpTool(),
        "PerspectiveWarp": PerspectiveWarpTool(),
        "Artboard":   ArtboardTool(),
        "Eyedropper": EyedropperTool(),
        "ColorSampler": ColorSamplerTool(),
        "Ruler":      RulerTool(),
        "Crop":       CropTool(),
        "Perspective Crop": PerspectiveCropTool(),
        "Slice":      SliceTool(),
        "SpotHealing":SpotHealingTool(),
        "HealingBrush":HealingBrushTool(),
        "Patch":      PatchTool(),
        "RedEye":     RedEyeTool(),
        "Text":       text,
        "Pen":        PenTool(),
        "FreeformPen":FreeformPenTool(),
        "CurvaturePen":CurvaturePenTool(),
        "AddAnchor":  AddAnchorPointTool(),
        "DeleteAnchor":DeleteAnchorPointTool(),
        "ConvertPoint":ConvertPointTool(),
        "PathSelection":PathSelectionTool(),
        "DirectSelection":DirectSelectionTool(),
        "Frame":      FrameTool(),
        "TextV":      textv,
        "TextHMask":  texthm,
        "TextVMask":  textvm,
        "Shapes":     ShapesTool(),
        "Gradient":   GradientTool(),
        "Hand":       HandTool(),
        "Zoom":       ZoomTool(),
        "RotateView": RotateViewTool(),
        "Lasso":          LassoTool(),
        "PolygonalLasso": PolygonalLassoTool(),
        "MagneticLasso":  MagneticLassoTool(),
        "MagicWand": MagicWandTool(),
        "QuickSelection": QuickSelectionTool(),
        "ObjectSelection": ObjectSelectionTool(),
    }


# ── Main window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow,
                 FileActionsMixin,
                 EditActionsMixin,
                 LayerActionsMixin,
                 ImageActionsMixin,
                 AdjustmentActionsMixin,
                 FilterActionsMixin):

    @property
    def _canvas(self) -> CanvasWidget:
        if hasattr(self, "_doc_tabs") and self._doc_tabs.count() > 0:
            return self._doc_tabs.currentWidget()
        return None

    @property
    def _document(self):
        c = self._canvas
        return c.document if c else None

    @_document.setter
    def _document(self, val): pass

    @property
    def _history(self):
        c = self._canvas
        return getattr(c, "history", None) if c else None

    @_history.setter
    def _history(self, val): pass

    @property
    def _filepath(self):
        c = self._canvas
        return getattr(c, "filepath", None) if c else None

    @_filepath.setter
    def _filepath(self, path):
        c = self._canvas
        if c:
            c.filepath = path
            self._update_title()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("title.untitled"))

        self._recent_files = []
        self._load_recent_files()

        self.setAcceptDrops(True)
        self._tools    = _build_tool_registry(self)
        self._active_tool_name = "Brush"

        self._all_acts:  list[tuple[str, QAction]] = []
        self._all_menus: list[tuple[str, QMenu]]   = []
        self._lang_acts: dict[str, QAction] = {}

        self._build_ui()

        self._welcome_panel.refresh_recent(self._recent_files)

        self._wire_signals()
        self._activate_tool("Brush")

    # ================================================================== UI Build
    def _build_ui(self):
        from ui.styles import DARK_STYLE
        self.setStyleSheet(DARK_STYLE)
        self.resize(1300, 850)

        self._build_menu_bar()

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(tr("status.ready"))

        self._opts_bar = ToolOptionsBar()

        central = QWidget()
        self.setCentralWidget(central)
        root_v = QVBoxLayout(central)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)
        root_v.addWidget(self._opts_bar)

        body = QWidget()
        body_h = QHBoxLayout(body)
        body_h.setContentsMargins(0, 0, 0, 0)
        body_h.setSpacing(0)

        self._toolbar = ToolBar()
        body_h.addWidget(self._toolbar)

        self._doc_tabs = QTabWidget()
        self._doc_tabs.setTabsClosable(True)
        self._doc_tabs.setMovable(True)
        self._doc_tabs.tabCloseRequested.connect(self._close_tab)
        self._doc_tabs.currentChanged.connect(self._on_tab_changed)
        self._doc_tabs.setObjectName("docTabs")
        self._doc_tabs.setStyleSheet("QTabBar::tab { padding: 6px 14px; background: #1e1e2e; color: #a6adc8; border-right: 1px solid #313244; } QTabBar::tab:selected { background: #313244; color: #cdd6f4; font-weight: bold; }")

        right = QWidget()
        right.setObjectName("panel")
        right.setMinimumWidth(220)
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(0)

        self._color_panel  = ColorPanel()
        self._layers_panel = LayersPanel()

        from ui.channels_panel import ChannelsPanel
        self._channels_panel = ChannelsPanel()

        from ui.history_panel      import HistoryPanel
        from ui.navigator_panel    import NavigatorPanel
        from ui.info_panel         import InfoPanel
        from ui.histogram_panel    import HistogramPanel
        from ui.brushes_panel      import BrushesPanel
        from ui.swatches_panel     import SwatchesPanel
        from ui.paths_panel        import PathsPanel
        from ui.properties_panel   import PropertiesPanel
        from ui.actions_panel      import ActionsPanel
        from ui.tool_presets_panel import ToolPresetsPanel
        from ui.character_panel    import CharacterPanel
        from ui.paragraph_panel    import ParagraphPanel
        from ui.glyphs_panel       import GlyphsPanel

        self._history_panel       = HistoryPanel()
        self._navigator_panel     = NavigatorPanel()
        self._info_panel          = InfoPanel()
        self._histogram_panel     = HistogramPanel()
        self._brushes_panel       = BrushesPanel()
        self._swatches_panel      = SwatchesPanel()
        self._paths_panel         = PathsPanel()
        self._properties_panel    = PropertiesPanel()
        self._actions_panel       = ActionsPanel()
        self._tool_presets_panel  = ToolPresetsPanel()
        self._character_panel     = CharacterPanel()
        self._paragraph_panel     = ParagraphPanel()
        self._glyphs_panel        = GlyphsPanel()

        self._tabs = QTabWidget()
        self._tabs.setObjectName("sidebarTabs")
        self._tabs.tabBar().setUsesScrollButtons(True)
        self._tabs.addTab(self._layers_panel,      tr("panel.layers"))
        self._tabs.addTab(self._channels_panel,    tr("panel.channels"))
        self._tabs.addTab(self._history_panel,     tr("panel.history"))
        self._tabs.addTab(self._navigator_panel,   tr("panel.navigator"))
        self._tabs.addTab(self._info_panel,        tr("panel.info"))
        self._tabs.addTab(self._histogram_panel,   tr("panel.histogram"))
        self._tabs.addTab(self._brushes_panel,     tr("panel.brushes"))
        self._tabs.addTab(self._swatches_panel,    tr("panel.swatches_tab"))
        self._tabs.addTab(self._paths_panel,       tr("panel.paths"))
        self._tabs.addTab(self._properties_panel,  tr("panel.properties"))
        self._tabs.addTab(self._actions_panel,     tr("panel.actions"))
        self._tabs.addTab(self._tool_presets_panel,tr("panel.tool_presets"))
        self._tabs.addTab(self._character_panel,   tr("panel.character"))
        self._tabs.addTab(self._paragraph_panel,   tr("panel.paragraph"))
        self._tabs.addTab(self._glyphs_panel,      tr("panel.glyphs"))

        self._layers_panel._title_lbl.hide()

        # Connect panel signals
        self._history_panel.jump_requested.connect(self._history_jump)
        self._navigator_panel.zoom_changed.connect(self._on_nav_zoom)
        self._swatches_panel.fg_color_selected.connect(self._color_panel.set_fg)
        self._swatches_panel.bg_color_selected.connect(self._color_panel.set_bg)
        self._swatches_panel.add_swatch_requested.connect(
            lambda: self._swatches_panel.add_swatch(self._color_panel._fg))
        self._character_panel.option_changed.connect(self._on_opt_changed)
        self._paragraph_panel.option_changed.connect(self._on_opt_changed)
        self._glyphs_panel.char_inserted.connect(self._on_glyph_inserted)
        self._actions_panel.action_requested.connect(self._on_action_requested)
        self._tool_presets_panel.save_requested.connect(self._on_preset_save_requested)
        self._tool_presets_panel.preset_selected.connect(self._on_preset_selected)
        self._brushes_panel.brush_selected.connect(self._on_brush_selected)
        self._paths_panel.make_selection_requested.connect(self._path_make_selection)
        self._paths_panel.fill_path_requested.connect(self._path_fill)
        self._paths_panel.stroke_path_requested.connect(self._path_stroke)
        self._paths_panel.delete_path_requested.connect(self._path_delete)
        self._properties_panel.transform_changed.connect(self._on_transform_changed)
        self._properties_panel.align_requested.connect(self._do_align_layer)

        right_v.addWidget(self._color_panel)
        right_v.addWidget(self._tabs, 1)

        from ui.welcome_panel import WelcomePanel
        self._welcome_panel = WelcomePanel()
        self._center_stack = QStackedWidget()
        self._center_stack.addWidget(self._welcome_panel)  # index 0
        self._center_stack.addWidget(self._doc_tabs)        # index 1
        self._center_stack.setCurrentIndex(0)

        self._welcome_panel.new_requested.connect(self._new_doc)
        self._welcome_panel.open_requested.connect(self._open_file)
        self._welcome_panel.open_path_requested.connect(self._open_file_path)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._center_stack)
        splitter.addWidget(right)
        splitter.setSizes([self.width() - 260, 260])
        splitter.setStretchFactor(0, 1) # Холст будет растягиваться
        splitter.setStretchFactor(1, 0) # Панель — нет

        body_h.addWidget(splitter, 1)
        root_v.addWidget(body, 1)

    # ================================================================= Menu Bar
    def _build_menu_bar(self):
        mb = self.menuBar()

        # File
        file_m = self._menu(mb, "menu.file")
        self._act(file_m, "menu.new",        self._new_doc,    QKeySequence.StandardKey.New)
        self._act(file_m, "menu.open",       self._open_file,  QKeySequence.StandardKey.Open)
        
        self._recent_menu = self._menu(file_m, "menu.open_recent")
        self._update_recent_menu()
        
        file_m.addSeparator()
        self._act(file_m, "menu.save",       self._save,       QKeySequence.StandardKey.Save)
        self._act(file_m, "menu.save_as",    self._save_as,    QKeySequence("Ctrl+Shift+S"))
        self._act(file_m, "menu.export_png", self._export_png)
        self._act(file_m, "menu.export_slices", self._export_slices)
        file_m.addSeparator()
        self._act(file_m, "menu.quit",       self.close,       QKeySequence.StandardKey.Quit)

        # Edit
        edit_m = self._menu(mb, "menu.edit")
        self._undo_act = self._act(edit_m, "menu.undo", self._undo, QKeySequence("Ctrl+Z"))
        self._redo_act = self._act(edit_m, "menu.redo", self._redo, QKeySequence("Ctrl+Shift+Z"))
        edit_m.addSeparator()
        self._act(edit_m, "menu.cut",             self._cut,   QKeySequence.StandardKey.Cut)
        self._act(edit_m, "menu.copy",            self._copy,  QKeySequence.StandardKey.Copy)
        self._act(edit_m, "menu.paste_new_layer", self._paste, QKeySequence.StandardKey.Paste)
        edit_m.addSeparator()
        self._act(edit_m, "menu.clear_layer",  self._clear_layer, QKeySequence("Delete"))
        edit_m.addSeparator()
        self._act(edit_m, "menu.define_brush", self._define_brush)
        self._act(edit_m, "menu.define_pattern", self._define_pattern)
        self._act(edit_m, "menu.define_shape", self._define_shape)
        # Select
        select_m = self._menu(mb, "menu.select")
        self._act(select_m, "menu.select_all", self._select_all, QKeySequence.StandardKey.SelectAll) # Ctrl+A
        self._act(select_m, "menu.deselect",   self._deselect,   QKeySequence("Ctrl+D"))
        self._act(select_m, "menu.reselect",   self._reselect,   QKeySequence("Shift+Ctrl+D"))
        self._act(select_m, "menu.inverse",    self._inverse_selection, QKeySequence("Shift+Ctrl+I"))
        select_m.addSeparator()
        self._act(select_m, "menu.color_range", self._color_range)
        self._act(select_m, "menu.focus_area", self._focus_area)
        self._act(select_m, "menu.select_subject", self._select_subject)
        self._act(select_m, "menu.select_sky", self._select_sky)
        self._act(select_m, "menu.select_and_mask", self._select_and_mask, QKeySequence("Alt+Ctrl+R"))
        select_m.addSeparator()
        self._act(select_m, "menu.save_selection", self._save_selection)
        self._act(select_m, "menu.load_selection", self._load_selection)
        select_m.addSeparator()
        
        modify_m = self._menu(select_m, "menu.modify")
        self._act(modify_m, "menu.modify.border", lambda: self._modify_selection("border"))
        self._act(modify_m, "menu.modify.smooth", lambda: self._modify_selection("smooth"))
        self._act(modify_m, "menu.modify.expand", lambda: self._modify_selection("expand"))
        self._act(modify_m, "menu.modify.contract", lambda: self._modify_selection("contract"))
        self._act(modify_m, "menu.modify.feather", lambda: self._modify_selection("feather"), QKeySequence("Shift+F6"))
        self._act(select_m, "menu.quick_mask", self._toggle_quick_mask, QKeySequence("Q"))
        edit_m.addSeparator()
        self._act(edit_m, "menu.fill_fg", self._fill_fg, QKeySequence("Alt+Delete"))
        self._act(edit_m, "menu.fill_bg", self._fill_bg, QKeySequence("Ctrl+Delete"))

        # Image
        img_m  = self._menu(mb, "menu.image")
        adj_m  = self._menu(img_m, "menu.adjustments")
        self._act(adj_m, "menu.levels",              self._levels,              QKeySequence("Ctrl+L"))
        self._act(adj_m, "menu.brightness_contrast", self._brightness_contrast)
        self._act(adj_m, "menu.hue_saturation",      self._hue_saturation)
        self._act(adj_m, "menu.exposure",            self._exposure)
        self._act(adj_m, "menu.vibrance",            self._vibrance)
        adj_m.addSeparator()
        self._act(adj_m, "menu.black_white",         self._black_white)
        self._act(adj_m, "menu.posterize",           self._posterize)
        self._act(adj_m, "menu.threshold",           self._threshold)
        adj_m.addSeparator()
        self._act(adj_m, "menu.channel_mixer",       self._channel_mixer)
        self._act(adj_m, "menu.selective_color",     self._selective_color)
        self._act(adj_m, "menu.match_color",         self._match_color)
        adj_m.addSeparator()
        self._act(adj_m, "menu.shadows_highlights",  self._shadows_highlights)
        self._act(adj_m, "menu.replace_color",       self._replace_color)
        adj_m.addSeparator()
        self._act(adj_m, "menu.photo_filter",        self._photo_filter)
        self._act(adj_m, "menu.gradient_map",        self._gradient_map)
        self._act(adj_m, "menu.color_lookup",        self._color_lookup)
        self._act(adj_m, "menu.equalize",            self._equalize)
        adj_m.addSeparator()
        self._act(adj_m, "menu.hdr_toning",          self._hdr_toning)
        adj_m.addSeparator()
        self._act(adj_m, "menu.invert",              self._invert, QKeySequence("Ctrl+I"))
        img_m.addSeparator()
        self._act(img_m, "menu.flip_h",        self._flip_h)
        self._act(img_m, "menu.flip_v",        self._flip_v)
        img_m.addSeparator()
        mode_m = self._menu(img_m, "menu.mode")
        self._act_mode_bitmap = self._act(mode_m, "mode.bitmap", lambda: self._change_color_mode("Bitmap"))
        self._act_mode_gray = self._act(mode_m, "mode.grayscale", lambda: self._change_color_mode("Grayscale"))
        self._act_mode_duo = self._act(mode_m, "mode.duotone", lambda: self._change_color_mode("Duotone"))
        self._act_mode_idx = self._act(mode_m, "mode.indexed", lambda: self._change_color_mode("Indexed"))
        self._act_mode_rgb = self._act(mode_m, "mode.rgb", lambda: self._change_color_mode("RGB"))
        self._act_mode_cmyk = self._act(mode_m, "mode.cmyk", lambda: self._change_color_mode("CMYK"))
        self._act_mode_lab = self._act(mode_m, "mode.lab", lambda: self._change_color_mode("Lab"))
        
        mode_m.addSeparator()
        self._act_depth_8 = self._act(mode_m, "mode.8bit", lambda: self._change_bit_depth(8))
        self._act_depth_16 = self._act(mode_m, "mode.16bit", lambda: self._change_bit_depth(16))
        self._act_depth_32 = self._act(mode_m, "mode.32bit", lambda: self._change_bit_depth(32))
        
        for act in (self._act_mode_bitmap, self._act_mode_gray, self._act_mode_duo, self._act_mode_idx, self._act_mode_rgb, self._act_mode_cmyk, self._act_mode_lab, 
                    self._act_depth_8, self._act_depth_16, self._act_depth_32):
            act.setCheckable(True)
        img_m.addSeparator()
        self._act(img_m, "menu.apply_image",   self._apply_image)
        self._act(img_m, "menu.calculations",  self._calculations)
        img_m.addSeparator()
        self._act(img_m, "menu.image_size",    self._image_size,    QKeySequence("Ctrl+Alt+I"))
        self._act(img_m, "menu.resize_canvas", self._resize_canvas)
        img_m.addSeparator()
        self._act(img_m, "menu.trim",       self._trim)
        self._act(img_m, "menu.reveal_all", self._reveal_all)
        img_m.addSeparator()
        self._act(img_m, "menu.apply_crop",    self._apply_crop)
        self._act(img_m, "menu.apply_perspective_crop", self._apply_perspective_crop)
        img_m.addSeparator()
        self._act(img_m, "menu.flatten",       self._flatten)

        # Layer
        layer_m = self._menu(mb, "menu.layer")
        self._act(layer_m, "menu.new_layer",       self._add_layer,       QKeySequence("Ctrl+Shift+N"))
        self._act(layer_m, "menu.duplicate_layer", self._duplicate_layer, QKeySequence("Ctrl+J"))
        self._act(layer_m, "menu.delete_layer",    self._delete_layer)
        layer_m.addSeparator()
        self._act(layer_m, "menu.export_layer_png", self._export_layer_png)
        layer_m.addSeparator()
        self._act(layer_m, "menu.create_clipping", self._toggle_clipping_mask, QKeySequence("Ctrl+Alt+G"))

        adj_m = self._menu(layer_m, "menu.new_adj_layer")
        self._act(adj_m, "menu.new_adj_bc",     lambda: self._new_adj_layer("brightness_contrast"))
        self._act(adj_m, "menu.new_adj_hs",     lambda: self._new_adj_layer("hue_saturation"))
        self._act(adj_m, "menu.new_adj_invert", lambda: self._new_adj_layer("invert"))
        adj_m.addSeparator()
        self._act(adj_m, "menu.levels",       lambda: self._new_adj_layer("levels"))
        self._act(adj_m, "menu.exposure",     lambda: self._new_adj_layer("exposure"))
        self._act(adj_m, "menu.vibrance",     lambda: self._new_adj_layer("vibrance"))
        self._act(adj_m, "menu.black_white",  lambda: self._new_adj_layer("black_white"))
        self._act(adj_m, "menu.posterize",    lambda: self._new_adj_layer("posterize"))
        self._act(adj_m, "menu.threshold",    lambda: self._new_adj_layer("threshold"))
        self._act(adj_m, "menu.photo_filter", lambda: self._new_adj_layer("photo_filter"))
        self._act(adj_m, "menu.gradient_map", lambda: self._new_adj_layer("gradient_map"))
        self._act(adj_m, "menu.color_lookup", lambda: self._new_adj_layer("color_lookup"))

        fill_m = self._menu(layer_m, "menu.new_fill_layer")
        self._act(fill_m, "menu.new_fill_solid",    lambda: self._new_fill_layer("solid"))
        self._act(fill_m, "menu.new_fill_gradient", lambda: self._new_fill_layer("gradient"))

        layer_m.addSeparator()
        self._act(layer_m, "menu.smart_object",   self._new_smart_object)
        self._act(layer_m, "menu.rasterize_layer", self._rasterize_layer)
        layer_m.addSeparator()
        self._act(layer_m, "menu.move_up",   self._layer_up,   QKeySequence("Ctrl+]"))
        self._act(layer_m, "menu.move_down", self._layer_down, QKeySequence("Ctrl+["))

        # Filter
        filter_m = self._menu(mb, "menu.filter")
        
        self._act(filter_m, "menu.filter.camera_raw",      lambda: self._open_specific_filter("camera_raw"), QKeySequence("Shift+Ctrl+A"))
        self._act(filter_m, "menu.filter.lens_correction", lambda: self._open_specific_filter("lens_correction"), QKeySequence("Shift+Ctrl+R"))
        self._act(filter_m, "menu.filter.liquify",         lambda: self._open_specific_filter("liquify"), QKeySequence("Shift+Ctrl+X"))
        filter_m.addSeparator()
        
        blur_gallery_m = self._menu(filter_m, "menu.blur_gallery")
        self._act(blur_gallery_m, "menu.blur.field",      self._blur_field)
        self._act(blur_gallery_m, "menu.blur.iris",       self._blur_iris)
        self._act(blur_gallery_m, "menu.blur.tilt_shift", self._blur_tilt_shift)
        self._act(blur_gallery_m, "menu.blur.path",       self._blur_path)
        self._act(blur_gallery_m, "menu.blur.spin",       self._blur_spin)
        filter_m.addSeparator()

        blur_m   = self._menu(filter_m, "menu.blur")
        self._act(blur_m, "menu.blur.average",  self._blur_average)
        self._act(blur_m, "menu.blur.blur",     self._blur_simple)
        self._act(blur_m, "menu.blur.more",     self._blur_more)
        blur_m.addSeparator()
        self._act(blur_m, "menu.blur.box",      self._box_blur)
        self._act(blur_m, "menu.blur.gaussian", self._gaussian_blur)
        self._act(blur_m, "menu.blur.motion",   self._motion_blur)
        self._act(blur_m, "menu.blur.radial",   self._radial_blur)
        self._act(blur_m, "menu.blur.smart",    self._smart_blur)
        self._act(blur_m, "menu.blur.surface",  self._surface_blur)
        self._act(blur_m, "menu.blur.shape",    self._shape_blur)
        self._act(blur_m, "menu.blur.lens",     self._lens_blur)
        filter_m.addSeparator()
        
        sharpen_m = self._menu(filter_m, "menu.sharpen_gallery")
        self._act(sharpen_m, "menu.sharpen.sharpen", lambda: self._open_sharpen("sharpen"))
        self._act(sharpen_m, "menu.sharpen.edges",   lambda: self._open_sharpen("edges"))
        self._act(sharpen_m, "menu.sharpen.more",    lambda: self._open_sharpen("more"))
        self._act(sharpen_m, "menu.sharpen.smart",   lambda: self._open_sharpen("smart"))
        self._act(sharpen_m, "menu.sharpen.unsharp", lambda: self._open_sharpen("unsharp"))
        filter_m.addSeparator()

        distort_m = self._menu(filter_m, "menu.distort")
        self._act(distort_m, "menu.distort.displace", lambda: self._open_distort("displace"))
        self._act(distort_m, "menu.distort.pinch",    lambda: self._open_distort("pinch"))
        self._act(distort_m, "menu.distort.polar",    lambda: self._open_distort("polar"))
        self._act(distort_m, "menu.distort.ripple",   lambda: self._open_distort("ripple"))
        self._act(distort_m, "menu.distort.shear",    lambda: self._open_distort("shear"))
        self._act(distort_m, "menu.distort.spherize", lambda: self._open_distort("spherize"))
        self._act(distort_m, "menu.distort.twirl",    lambda: self._open_distort("twirl"))
        self._act(distort_m, "menu.distort.wave",     lambda: self._open_distort("wave"))
        self._act(distort_m, "menu.distort.zigzag",   lambda: self._open_distort("zigzag"))
        
        filter_m.addSeparator()
        noise_m = self._menu(filter_m, "menu.noise")
        self._act(noise_m, "menu.noise.add",      lambda: self._open_noise("add_noise"))
        self._act(noise_m, "menu.noise.despeckle",lambda: self._open_noise("despeckle"))
        self._act(noise_m, "menu.noise.dust",     lambda: self._open_noise("dust_scratches"))
        self._act(noise_m, "menu.noise.median",   lambda: self._open_noise("median"))
        self._act(noise_m, "menu.noise.reduce",   lambda: self._open_noise("reduce_noise"))
        
        filter_m.addSeparator()
        pixelate_m = self._menu(filter_m, "menu.pixelate")
        self._act(pixelate_m, "menu.pixelate.color_halftone", lambda: self._open_pixelate("color_halftone"))
        self._act(pixelate_m, "menu.pixelate.crystallize",    lambda: self._open_pixelate("crystallize"))
        self._act(pixelate_m, "menu.pixelate.facet",          lambda: self._open_pixelate("facet"))
        self._act(pixelate_m, "menu.pixelate.fragment",       lambda: self._open_pixelate("fragment"))
        self._act(pixelate_m, "menu.pixelate.mezzotint",      lambda: self._open_pixelate("mezzotint"))
        self._act(pixelate_m, "menu.pixelate.mosaic",         lambda: self._open_pixelate("mosaic"))
        self._act(pixelate_m, "menu.pixelate.pointillize",    lambda: self._open_pixelate("pointillize"))
        
        filter_m.addSeparator()
        other_m = self._menu(filter_m, "menu.other")
        self._act(other_m, "menu.other.custom",    lambda: self._open_other("custom"))
        self._act(other_m, "menu.other.high_pass", lambda: self._open_other("high_pass"))
        self._act(other_m, "menu.other.maximum",   lambda: self._open_other("maximum"))
        self._act(other_m, "menu.other.minimum",   lambda: self._open_other("minimum"))
        self._act(other_m, "menu.other.offset",    lambda: self._open_other("offset"))
        
        filter_m.addSeparator()
        stylize_m = self._menu(filter_m, "menu.stylize")
        self._act(stylize_m, "menu.stylize.emboss",       lambda: self._open_stylize("emboss"))
        self._act(stylize_m, "menu.stylize.extrude",      lambda: self._open_stylize("extrude"))
        self._act(stylize_m, "menu.stylize.find_edges",   lambda: self._open_stylize("find_edges"))
        self._act(stylize_m, "menu.stylize.oil_paint",    lambda: self._open_stylize("oil_paint"))
        self._act(stylize_m, "menu.stylize.solarize",     lambda: self._open_stylize("solarize"))
        self._act(stylize_m, "menu.stylize.tiles",        lambda: self._open_stylize("tiles"))
        self._act(stylize_m, "menu.stylize.trace_contour",lambda: self._open_stylize("trace_contour"))
        self._act(stylize_m, "menu.stylize.wind",         lambda: self._open_stylize("wind"))
        
        filter_m.addSeparator()
        render_m = self._menu(filter_m, "menu.render_gallery")
        self._act(render_m, "menu.render.clouds",      lambda: self._open_render("clouds"))
        self._act(render_m, "menu.render.diff_clouds", lambda: self._open_render("diff_clouds"))
        self._act(render_m, "menu.render.fibers",      lambda: self._open_render("fibers"))
        self._act(render_m, "menu.render.lens_flare",  lambda: self._open_render("lens_flare"))
        self._act(render_m, "menu.render.lighting",    lambda: self._open_render("lighting"))
        self._act(render_m, "menu.render.wood",        lambda: self._open_render("wood"))
        self._act(render_m, "menu.render.frame",       lambda: self._open_render("frame"))
        self._act(render_m, "menu.render.flame",       lambda: self._open_render("flame"))

        # View
        view_m = self._menu(mb, "menu.view")
        self._act(view_m, "menu.zoom_in",    lambda: self._canvas.zoom_in(),    QKeySequence.StandardKey.ZoomIn)
        self._act(view_m, "menu.zoom_out",   lambda: self._canvas.zoom_out(),   QKeySequence.StandardKey.ZoomOut)
        self._act(view_m, "menu.fit_window", lambda: self._canvas.reset_zoom(), QKeySequence("Ctrl+0"))
        view_m.addSeparator()

        self._act_rulers = self._act(view_m, "menu.rulers", self._toggle_rulers, QKeySequence("Ctrl+R"))
        self._act_rulers.setCheckable(True)
        self._act_rulers.setChecked(False)

        show_m = self._menu(view_m, "menu.show")
        self._act_guides = self._act(show_m, "menu.show_guides", self._toggle_guides, QKeySequence("Ctrl+;"))
        self._act_guides.setCheckable(True); self._act_guides.setChecked(True)
        
        self._act_grid = self._act(show_m, "menu.show_grid", self._toggle_grid, QKeySequence("Ctrl+'"))
        self._act_grid.setCheckable(True); self._act_grid.setChecked(False)
        
        self._act_slices = self._act(show_m, "menu.show_slices", self._toggle_slices)
        self._act_slices.setCheckable(True); self._act_slices.setChecked(True)

        snap_m = self._menu(view_m, "menu.snap")
        self._act_snap = self._act(snap_m, "menu.snap", self._toggle_snap, QKeySequence("Shift+Ctrl+;"))
        self._act_snap.setCheckable(True); self._act_snap.setChecked(True)

        snap_m.addSeparator()
        self._act_snap_guides = self._act(snap_m, "menu.snap_guides", self._toggle_snap_guides)
        self._act_snap_guides.setCheckable(True); self._act_snap_guides.setChecked(True)
        self._act_snap_grid = self._act(snap_m, "menu.snap_grid", self._toggle_snap_grid)
        self._act_snap_grid.setCheckable(True); self._act_snap_grid.setChecked(False)
        self._act_snap_bounds = self._act(snap_m, "menu.snap_bounds", self._toggle_snap_bounds)
        self._act_snap_bounds.setCheckable(True); self._act_snap_bounds.setChecked(True)
        self._act_snap_layers = self._act(snap_m, "menu.snap_layers", self._toggle_snap_layers)
        self._act_snap_layers.setCheckable(True); self._act_snap_layers.setChecked(True)

        view_m.addSeparator()
        self._act(view_m, "menu.clear_guides", self._clear_guides)
        view_m.addSeparator()
        self._build_language_menu(view_m)

        # Window — panel visibility
        win_m = self._menu(mb, "menu.window")
        self._panel_tab_acts: list[tuple[str, QAction]] = []
        _panel_keys = [
            "panel.layers", "panel.channels", "panel.history", "panel.navigator",
            "panel.info", "panel.histogram", "panel.brushes", "panel.swatches_tab",
            "panel.paths", "panel.properties", "panel.actions", "panel.tool_presets",
            "panel.character", "panel.paragraph", "panel.glyphs",
        ]
        for idx, key in enumerate(_panel_keys):
            act = QAction(tr(key), self)
            act.setCheckable(True)
            act.setChecked(True)
            act.toggled.connect(lambda checked, i=idx: self._tabs.tabBar().setTabVisible(i, checked))
            win_m.addAction(act)
            self._panel_tab_acts.append((key, act))

    def _act(self, menu: QMenu, key: str, slot, shortcut=None) -> QAction:
        act = QAction(tr(key), self)
        if shortcut:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        menu.addAction(act)
        self._all_acts.append((key, act))
        return act

    def _menu(self, parent, key: str) -> QMenu:
        m = parent.addMenu(tr(key))
        self._all_menus.append((key, m))
        return m

    # ── Language ───────────────────────────────────────────────────────────────
    def _build_language_menu(self, parent_menu: QMenu):
        lang_m = self._menu(parent_menu, "menu.language")
        cur = locale_current()
        for code, name in available_languages():
            act = QAction(name, self, checkable=True)
            act.setChecked(code == cur)
            act.triggered.connect(lambda checked, c=code: self._set_language(c))
            lang_m.addAction(act)
            self._lang_acts[code] = act

    def _set_language(self, code: str):
        if code == locale_current():
            return
        locale_load(code)
        self._apply_language()

    def _apply_language(self):
        for key, act in self._all_acts:
            act.setText(tr(key))
        for key, menu in self._all_menus:
            menu.setTitle(tr(key))
        cur = locale_current()
        for code, act in self._lang_acts.items():
            act.setChecked(code == cur)
        self._update_mode_menu()
        self._update_recent_menu()
        self._toolbar.retranslate()
        self._opts_bar.retranslate()
        self._layers_panel.retranslate()
        self._color_panel.retranslate()
        self._channels_panel.retranslate()
        self._tabs.setTabText(0,  tr("panel.layers"))
        self._tabs.setTabText(1,  tr("panel.channels"))
        self._tabs.setTabText(2,  tr("panel.history"))
        self._tabs.setTabText(3,  tr("panel.navigator"))
        self._tabs.setTabText(4,  tr("panel.info"))
        self._tabs.setTabText(5,  tr("panel.histogram"))
        self._tabs.setTabText(6,  tr("panel.brushes"))
        self._tabs.setTabText(7,  tr("panel.swatches_tab"))
        self._tabs.setTabText(8,  tr("panel.paths"))
        self._tabs.setTabText(9,  tr("panel.properties"))
        self._tabs.setTabText(10, tr("panel.actions"))
        self._tabs.setTabText(11, tr("panel.tool_presets"))
        self._tabs.setTabText(12, tr("panel.character"))
        self._tabs.setTabText(13, tr("panel.paragraph"))
        self._tabs.setTabText(14, tr("panel.glyphs"))
        for panel in (self._history_panel, self._navigator_panel, self._info_panel,
                      self._histogram_panel, self._brushes_panel, self._swatches_panel,
                      self._paths_panel, self._properties_panel, self._actions_panel,
                      self._tool_presets_panel, self._character_panel,
                      self._paragraph_panel, self._glyphs_panel):
            if hasattr(panel, "retranslate"):
                panel.retranslate()
        if hasattr(self, "_welcome_panel"):
            self._welcome_panel.retranslate()
        if hasattr(self, "_panel_tab_acts"):
            for key, act in self._panel_tab_acts:
                act.setText(tr(key))
        self._refresh_layers()

    def _canvas_refresh(self):
        if self._canvas:
            self._canvas._cache_dirty = True
            self._canvas.update()

    # ================================================================= Signals
    def _wire_signals(self):
        self._toolbar.tool_selected.connect(self._activate_tool)
        self._color_panel.fg_changed.connect(self._on_fg_changed)
        self._color_panel.bg_changed.connect(self._on_bg_changed)
        self._opts_bar.option_changed.connect(self._on_opt_changed)
        self._opts_bar.apply_styles_requested.connect(self._apply_text_styles)
        self._opts_bar.apply_crop_requested.connect(self._on_apply_crop_requested)
        self._layers_panel.layer_selected.connect(self._on_layer_selected_wrap)
        self._layers_panel.layer_added.connect(self._add_layer)
        self._layers_panel.layer_duplicated.connect(self._duplicate_layer)
        self._layers_panel.layer_deleted.connect(self._delete_layer)
        self._layers_panel.layer_renamed.connect(self._rename_layer)
        self._layers_panel.layer_expanded_toggled.connect(self._on_layer_expanded_toggled)
        self._layers_panel.layer_moved.connect(self._move_layer_exact)
        self._layers_panel.layer_moved_up.connect(self._layer_up)
        self._layers_panel.layer_moved_down.connect(self._layer_down)
        self._layers_panel.layer_visibility.connect(self._on_layer_visibility)
        self._layers_panel.layer_opacity.connect(self._on_layer_opacity)
        if hasattr(self._layers_panel, "layer_lock_changed"):
            self._layers_panel.layer_lock_changed.connect(self._on_layer_lock_changed)
        if hasattr(self._layers_panel, "layer_grouped"):
            self._layers_panel.layer_grouped.connect(self._group_layer)
            self._layers_panel.layer_linked.connect(self._link_layer)
        if hasattr(self._layers_panel, "layer_blend_mode"):
            self._layers_panel.layer_blend_mode.connect(self._on_layer_blend_mode)
        if hasattr(self._layers_panel, "layer_target_changed"):
            self._layers_panel.layer_target_changed.connect(self._on_layer_target_changed)
            if hasattr(self._layers_panel, "layer_mask_toggled"):
                self._layers_panel.layer_mask_toggled.connect(self._on_layer_mask_toggled)
            self._layers_panel.layer_add_mask.connect(self._add_mask)
            self._layers_panel.layer_delete_mask.connect(self._delete_mask)
            self._layers_panel.layer_apply_mask.connect(self._apply_mask)
            if hasattr(self._layers_panel, "layer_invert_mask"):
                self._layers_panel.layer_invert_mask.connect(self._invert_mask)
        if hasattr(self._layers_panel, "layer_add_vector_mask"):
            self._layers_panel.layer_add_vector_mask.connect(self._add_vector_mask)
            self._layers_panel.layer_delete_vector_mask.connect(self._delete_vector_mask)
            self._layers_panel.layer_vmask_toggled.connect(self._on_layer_vmask_toggled)
        if hasattr(self._layers_panel, "layer_clipping_toggled"):
            self._layers_panel.layer_clipping_toggled.connect(self._on_layer_clipping_toggled)
        self._layers_panel.layer_merged_down.connect(self._merge_down)
        self._layers_panel.layer_flatten.connect(self._flatten)
        self._layers_panel.layer_edit.connect(self._on_edit_layer)
        self._layers_panel.layer_smart_object.connect(self._new_smart_object)
        self._layers_panel.layer_rasterize.connect(self._rasterize_layer)
        if hasattr(self._layers_panel, "layer_export_png"):
            self._layers_panel.layer_export_png.connect(self._export_layer_png)
        self._layers_panel.layer_styles_requested.connect(self._open_layer_styles)
        if hasattr(self._layers_panel, "layer_clear_smart_filters"):
            self._layers_panel.layer_clear_smart_filters.connect(self._clear_smart_filters)
        self._channels_panel.channel_changed.connect(self._on_channel_changed)
        self._channels_panel.save_requested.connect(self._save_selection)
        self._channels_panel.load_requested.connect(self._load_selection_btn)
        self._channels_panel.delete_requested.connect(self._delete_alpha_channel)

    def _add_tab(self, doc, title, filepath=None):
        canvas = CanvasWidget()
        canvas.set_document(doc)
        from core.history import HistoryManager
        canvas.history = HistoryManager()
        doc.history = canvas.history
        canvas.filepath = filepath
        if hasattr(self, "_doc_tabs") and self._doc_tabs.count() > 0:
            fc = self._doc_tabs.widget(0)
            canvas.tool_opts = dict(fc.tool_opts)
            canvas.fg_color = fc.fg_color
            canvas.bg_color = fc.bg_color
        else:
            cp = getattr(self, "_color_panel", None)
            canvas.fg_color = getattr(cp, "_fg", QColor(0, 0, 0))
            canvas.bg_color = getattr(cp, "_bg", QColor(255, 255, 255))
        canvas.document_changed.connect(self._on_doc_changed)
        canvas.pixels_changed.connect(self._on_pixels_changed)
        canvas.color_picked.connect(self._color_panel.set_fg)
        canvas.tool_state_changed.connect(self._opts_bar.update_tool_state)
        if hasattr(self, "_info_panel"):
            canvas.cursor_info.connect(self._info_panel.update_info)
        tool = self._tools.get(self._active_tool_name)
        canvas.active_tool = tool
        idx = self._doc_tabs.addTab(canvas, title)
        self._doc_tabs.setCurrentIndex(idx)
        if hasattr(self, "_center_stack"):
            self._center_stack.setCurrentIndex(1)
        return canvas

    def _close_tab(self, index: int):
        canvas = self._doc_tabs.widget(index)
        self._doc_tabs.removeTab(index)
        canvas.deleteLater()
        if self._doc_tabs.count() == 0:
            self._welcome_panel.refresh_recent(self._recent_files)
            self._center_stack.setCurrentIndex(0)

    def _on_tab_changed(self, index: int):
        if index < 0: return
        self._refresh_layers()
        self._update_mode_menu()
        self._update_title()
        self._canvas_refresh()
        self._sync_view_actions()
        if self._canvas and self._canvas.active_tool:
            self._canvas._emit_tool_state()
        self._refresh_secondary_panels()
        if hasattr(self, "_brushes_panel"):
            self._brushes_panel.refresh(self._canvas)

    def _sync_view_actions(self):
        """Sync View menu action checked states with the current document/canvas."""
        doc = self._document
        canvas = self._canvas
        if doc:
            self._act_guides.setChecked(getattr(doc, "show_guides", True))
            self._act_grid.setChecked(getattr(doc, "show_grid", False))
            self._act_slices.setChecked(getattr(doc, "show_slices", True))
            snap = getattr(doc, "snap_enabled", True)
            self._act_snap.setChecked(snap)
            self._act_snap_guides.setChecked(getattr(doc, "snap_to_guides", True))
            self._act_snap_guides.setEnabled(snap)
            self._act_snap_grid.setChecked(getattr(doc, "snap_to_grid", False))
            self._act_snap_grid.setEnabled(snap)
            self._act_snap_bounds.setChecked(getattr(doc, "snap_to_bounds", True))
            self._act_snap_bounds.setEnabled(snap)
            self._act_snap_layers.setChecked(getattr(doc, "snap_to_layers", True))
            self._act_snap_layers.setEnabled(snap)
        if canvas:
            self._act_rulers.setChecked(getattr(canvas, "show_rulers", False))

    # ================================================================= Tools
    def _commit_move_transform(self):
        for t_name in ["Move", "Warp", "PuppetWarp", "PerspectiveWarp"]:
            tool = self._tools.get(t_name)
            if tool and getattr(tool, "is_transforming", False):
                from core.history import HistoryState, clone_work_path
                
                # Временно восстанавливаем исходное состояние слоя и выделения для чистого слепка
                layer = self._document.get_active_layer()
                tmp_img, tmp_off, tmp_sel = None, None, None
                tmp_rect = None
                tmp_kids = []
                if layer and hasattr(tool, "_layer_backup") and tool._layer_backup is not None:
                    for kid_data in getattr(tool, "_linked_children", []):
                        kid = kid_data["layer"]
                        tmp_kids.append((kid, QPoint(kid.offset)))
                        kid.offset = kid_data["backup_offset"]
                        
                    tmp_img = layer.image
                    tmp_off = layer.offset
                    tmp_sel = self._document.selection
                    if getattr(layer, "layer_type", "") == "artboard":
                        tmp_rect = QRect(layer.artboard_rect) if layer.artboard_rect else None
                        if t_name == "Move":
                            layer.artboard_rect = QRect(tool._original_rect) if tool._original_rect else None
                    layer.image = tool._layer_backup
                    layer.offset = tool._offset_backup
                    if getattr(tool, "_sel_origin", None):
                        self._document.selection = tool._sel_origin

                pre_state = HistoryState(
                    description=tr("tool.warp") if t_name == "Warp" else tr("tool.move"),
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
                
                # Возвращаем "вырезанную" версию обратно для финального склеивания
                if layer and tmp_img is not None:
                    layer.image = tmp_img
                    layer.offset = tmp_off
                    self._document.selection = tmp_sel
                    if getattr(layer, "layer_type", "") == "artboard" and tmp_rect is not None:
                        layer.artboard_rect = tmp_rect
                        
                for kid, old_off in tmp_kids:
                    kid.offset = old_off

                old_w, old_h = self._document.width, self._document.height
                tool.apply_transform(self._document)
                self._history.push(pre_state)
                if self._document.width != old_w or self._document.height != old_h:
                    self._canvas.reset_zoom()
                self._canvas_refresh()

    def _activate_tool(self, name: str):
        if self._active_tool_name in ("Move", "Warp") and name != self._active_tool_name:
            self._commit_move_transform()
                
        print(f"Activating tool: {name}")
        self._active_tool_name = name
        tool = self._tools.get(name)
        if not tool:
            return
        from tools.other_tools import EyedropperTool
        if isinstance(tool, EyedropperTool):
            tool.color_picked_callback = lambda c: (
                self._color_panel.set_fg(c),
                self._on_fg_changed(c),
            )
        for i in range(self._doc_tabs.count()):
            c = self._doc_tabs.widget(i)
            c.active_tool = tool
            c._update_cursor()
        self._opts_bar.switch_to(name)
        self._toolbar.set_active(name)
        self._opts_bar.update_tool_state(None)

    def _on_layer_selected_wrap(self, index: int):
        self._commit_move_transform()
        if hasattr(self, "_on_layer_selected"):
            self._on_layer_selected(index)

    def _open_layer_styles(self, index: int):
        layer = self._document.layers[index]
        if getattr(layer, "layer_type", "raster") in ("group", "artboard"):
            return
        from ui.layer_style_dialog import LayerStyleDialog
        dlg = LayerStyleDialog(layer, self._canvas_refresh, self)
        if dlg.exec():
            self._push_history("Стили слоя")
            self._refresh_layers()
        else:
            dlg.reject()

    def _rename_layer(self, index: int, new_name: str):
        if 0 <= index < len(self._document.layers):
            layer = self._document.layers[index]
            if layer.name != new_name:
                layer.name = new_name

    def _on_layer_expanded_toggled(self, index: int, expanded: bool):
        if 0 <= index < len(self._document.layers):
            self._document.layers[index].expanded = expanded
            self._refresh_layers()

    def _move_layer_exact(self, from_index: int, to_index: int):
        if 0 <= from_index < len(self._document.layers) and 0 <= to_index < len(self._document.layers):
            layer = self._document.layers[from_index]
            self._document.move_layer(from_index, to_index)
            
            if to_index < len(self._document.layers) - 1:
                layer_above_in_ui = self._document.layers[to_index + 1]
                if getattr(layer_above_in_ui, "layer_type", "raster") in ("group", "artboard"):
                    layer.parent_id = getattr(layer_above_in_ui, "layer_id", None)
                else:
                    layer.parent_id = getattr(layer_above_in_ui, "parent_id", None)
            else:
                layer.parent_id = None
                
            self._push_history(tr("history.layer_moved"))
            self._refresh_layers()
            self._canvas_refresh()

    def _on_channel_changed(self, ch: str):
        if not self._canvas:
            return
        self._canvas.view_channel = ch
        self._canvas_refresh()

    def _save_selection(self):
        sel = self._document.selection
        if not sel or sel.isEmpty():
            return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, tr("menu.save_selection"), tr("dlg.define_name"))
        if ok and name:
            self._push_history(tr("history.save_selection"))
            if not hasattr(self._document, "alpha_channels"):
                self._document.alpha_channels = []
            self._document.alpha_channels.append({"name": name, "path": QPainterPath(sel)})
            self._channels_panel.refresh(self._document)

    def _load_selection(self):
        if not hasattr(self._document, "alpha_channels") or not self._document.alpha_channels:
            return
        from PyQt6.QtWidgets import QInputDialog
        names = [ch["name"] for ch in self._document.alpha_channels]
        name, ok = QInputDialog.getItem(self, tr("menu.load_selection"), "Channel:", names, 0, False)
        if ok and name:
            for ch in self._document.alpha_channels:
                if ch["name"] == name:
                    self._document.selection = QPainterPath(ch["path"])
                    self._push_history(tr("history.load_selection"))
                    self._canvas_refresh()
                    break

    def _load_selection_btn(self, idx):
        if hasattr(self._document, "alpha_channels") and 0 <= idx < len(self._document.alpha_channels):
            self._document.selection = QPainterPath(self._document.alpha_channels[idx]["path"])
            self._push_history(tr("history.load_selection"))
            self._canvas_refresh()

    def _delete_alpha_channel(self, idx):
        if hasattr(self._document, "alpha_channels") and 0 <= idx < len(self._document.alpha_channels):
            self._push_history(tr("history.delete_layer"))
            self._document.alpha_channels.pop(idx)
            self._channels_panel.refresh(self._document)
            if self._canvas.view_channel == f"alpha_{idx}":
                self._canvas.view_channel = "RGB"
                self._canvas_refresh()
            elif self._canvas.view_channel.startswith("alpha_"):
                cur_idx = int(self._canvas.view_channel.split("_")[1])
                if cur_idx > idx:
                    self._canvas.view_channel = f"alpha_{cur_idx - 1}"

    def _refresh_layers(self):
        super()._refresh_layers()
        if hasattr(self, "_channels_panel") and self._document:
            self._channels_panel.refresh(self._document)

    # ================================================================= Events
    def _toggle_rulers(self):
        self._canvas.show_rulers = self._act_rulers.isChecked(); self._canvas.update()
    def _toggle_guides(self):
        if hasattr(self._document, "show_guides"): self._document.show_guides = self._act_guides.isChecked(); self._canvas.update()
    def _toggle_grid(self):
        if hasattr(self._document, "show_grid"): self._document.show_grid = self._act_grid.isChecked(); self._canvas.update()
    def _toggle_slices(self):
        if hasattr(self._document, "show_slices"): self._document.show_slices = self._act_slices.isChecked(); self._canvas.update()
    def _toggle_snap(self):
        enabled = self._act_snap.isChecked()
        self._act_snap_guides.setEnabled(enabled); self._act_snap_grid.setEnabled(enabled)
        self._act_snap_bounds.setEnabled(enabled); self._act_snap_layers.setEnabled(enabled)
        if hasattr(self._document, "snap_enabled"): self._document.snap_enabled = enabled
    def _toggle_snap_guides(self):
        if hasattr(self._document, "snap_to_guides"): self._document.snap_to_guides = self._act_snap_guides.isChecked()
    def _toggle_snap_grid(self):
        if hasattr(self._document, "snap_to_grid"): self._document.snap_to_grid = self._act_snap_grid.isChecked()
    def _toggle_snap_bounds(self):
        if hasattr(self._document, "snap_to_bounds"): self._document.snap_to_bounds = self._act_snap_bounds.isChecked()
    def _toggle_snap_layers(self):
        if hasattr(self._document, "snap_to_layers"): self._document.snap_to_layers = self._act_snap_layers.isChecked()
    
    def _clear_guides(self):
        if hasattr(self._document, "guides_v"): self._document.guides_v.clear()
        if hasattr(self._document, "guides_h"): self._document.guides_h.clear()
        self._canvas.update()

    def _on_pixels_changed(self):
        self._update_status()
        self._refresh_secondary_panels()

    def _on_doc_changed(self):
        self._refresh_layers()
        state = getattr(self._canvas, "_pre_stroke_state", None)
        if state:
            self._history.push(state)
            self._canvas._pre_stroke_state = None
            if state.doc_width != self._document.width or state.doc_height != self._document.height:
                self._canvas.reset_zoom()
        self._update_title()
        self._refresh_secondary_panels()

    def _refresh_secondary_panels(self):
        canvas = self._canvas
        if hasattr(self, "_history_panel"):
            self._history_panel.refresh(canvas)
        if hasattr(self, "_navigator_panel"):
            self._navigator_panel.refresh(canvas)
        if hasattr(self, "_histogram_panel"):
            self._histogram_panel.refresh(canvas)
        if hasattr(self, "_properties_panel"):
            self._properties_panel.refresh(canvas)
        if hasattr(self, "_paths_panel"):
            self._paths_panel.refresh(canvas)

    def _undo(self):
        tool = self._canvas.active_tool
        if hasattr(tool, "is_transforming") and tool.is_transforming:
            tool.cancel_transform(self._document)
            self._canvas_refresh()
            self._opts_bar.update_tool_state(None)
            return
        super()._undo()

    def _redo(self):
        tool = self._canvas.active_tool
        if hasattr(tool, "is_transforming") and tool.is_transforming:
            tool.cancel_transform(self._document)
            self._canvas_refresh()
            self._opts_bar.update_tool_state(None)
            return
        super()._redo()

    def _push_history(self, description: str):
        if not self._document or not self._history:
            return
        from core.history import clone_work_path
        self._history.push(HistoryState(
            description=description,
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

    def _update_status(self, msg: str = ""):
        if not self._document: return
        doc = self._document
        layer = doc.get_active_layer()
        layer_name = layer.name if layer else "—"
        z = int(self._canvas.zoom * 100)
        self._status.showMessage(
            tr("status.info", w=doc.width, h=doc.height, z=z, layer=layer_name)
            + (f"  |  {msg}" if msg else "")
        )

    def _update_title(self):
        if not self._document: return
        mode = getattr(self._document, "color_mode", "RGB")
        depth = getattr(self._document, "bit_depth", 8)
        mode_str = f"{mode}/{depth}"
        fp = self._filepath
        if fp:
            self._add_recent_file(fp)
            name = fp.split("/")[-1]
            self.setWindowTitle(tr("title.with_file", name=name, mode=mode_str))
            if hasattr(self, "_doc_tabs") and self._doc_tabs.currentIndex() >= 0:
                self._doc_tabs.setTabText(self._doc_tabs.currentIndex(), name)
        else:
            self.setWindowTitle(tr("title.canvas", w=self._document.width, h=self._document.height, mode=mode_str))
            if hasattr(self, "_doc_tabs") and self._doc_tabs.currentIndex() >= 0:
                self._doc_tabs.setTabText(self._doc_tabs.currentIndex(), tr("title.untitled"))
            
    def _update_mode_menu(self):
        if not hasattr(self, "_act_mode_rgb"): return
        if not self._document: return
        mode = getattr(self._document, "color_mode", "RGB")
        depth = getattr(self._document, "bit_depth", 8)
        self._act_mode_bitmap.setChecked(mode == "Bitmap")
        self._act_mode_gray.setChecked(mode == "Grayscale")
        self._act_mode_duo.setChecked(mode == "Duotone")
        self._act_mode_idx.setChecked(mode == "Indexed")
        self._act_mode_rgb.setChecked(mode == "RGB")
        self._act_mode_cmyk.setChecked(mode == "CMYK")
        self._act_mode_lab.setChecked(mode == "Lab")
        
        self._act_depth_8.setChecked(depth == 8)
        self._act_depth_16.setChecked(depth == 16)
        self._act_depth_32.setChecked(depth == 32)
        self._update_title()

    def _align_layer(self, alignment: str):
        doc = self._document
        layer = doc.get_active_layer()
        if not layer or layer.locked or getattr(layer, "layer_type", "raster") == "artboard":
            return
            
        linked = [layer]
        target_id = getattr(layer, "layer_id", None)
        visited = set()
        def get_descendants(p_id):
            if not p_id or p_id in visited: return []
            visited.add(p_id)
            res = []
            for l in doc.layers:
                if getattr(l, "parent_id", None) == p_id:
                    res.append(l)
                    res.extend(get_descendants(getattr(l, "layer_id", None)))
            return res
            
        if target_id and getattr(layer, "layer_type", "raster") == "group":
            linked.extend(get_descendants(target_id))
            
        link_id = getattr(layer, "link_id", None)
        if link_id:
            for l in doc.layers:
                if getattr(l, "link_id", None) == link_id and l not in linked:
                    linked.append(l)
                    
        src_rect = QRectF()
        for l in linked:
            if getattr(l, "layer_type", "raster") in ("group", "artboard") or l.image.isNull(): continue
            b = Document._nontransparent_bounds(l.image)
            if not b.isEmpty(): src_rect = src_rect.united(QRectF(b).translated(QPointF(l.offset)))
                
        if src_rect.isEmpty(): return
        
        target_rect = None
        if doc.selection and not doc.selection.isEmpty(): target_rect = doc.selection.boundingRect()
        else:
            p_id = getattr(layer, "parent_id", None)
            while p_id:
                parent = next((l for l in doc.layers if getattr(l, "layer_id", None) == p_id), None)
                if not parent: break
                if getattr(parent, "layer_type", "") == "artboard" and getattr(parent, "artboard_rect", None):
                    target_rect = QRectF(parent.artboard_rect); break
                p_id = getattr(parent, "parent_id", None)
            if not target_rect: target_rect = QRectF(0, 0, doc.width, doc.height)
                
        dx, dy = 0, 0
        if alignment == "left": dx = target_rect.left() - src_rect.left()
        elif alignment == "center_h": dx = target_rect.center().x() - src_rect.center().x()
        elif alignment == "right": dx = target_rect.right() - src_rect.right()
        elif alignment == "top": dy = target_rect.top() - src_rect.top()
        elif alignment == "center_v": dy = target_rect.center().y() - src_rect.center().y()
        elif alignment == "bottom": dy = target_rect.bottom() - src_rect.bottom()
        
        if dx == 0 and dy == 0: return
        self._push_history(tr("history.layer_moved"))
        for l in linked: l.offset = l.offset + QPoint(int(dx), int(dy))
        self._canvas_refresh()

    def _apply_image(self):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull(): return
        
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr("history.apply_image"),
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
        
        from ui.calculations_dialog import ApplyImageDialog
        dlg = ApplyImageDialog(self._document, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
        else:
            dlg.cancel()

    def _calculations(self):
        if not self._document or not self._document.layers: return
        from ui.calculations_dialog import CalculationsDialog
        dlg = CalculationsDialog(self._document, self._canvas_refresh, self)
        if dlg.exec():
            self._push_history(tr("history.calculations"))
            dlg.apply_result(self)

    # ================================================================= Colour / Options
    def _on_fg_changed(self, c: QColor):
        if not hasattr(self, "_doc_tabs"): return
        for i in range(self._doc_tabs.count()):
            self._doc_tabs.widget(i).fg_color = c

    def _on_bg_changed(self, c: QColor):
        if not hasattr(self, "_doc_tabs"): return
        for i in range(self._doc_tabs.count()):
            self._doc_tabs.widget(i).bg_color = c

    def _on_opt_changed(self, key: str, value):
        if key == "align_layer":
            self._align_layer(value)
            return
        if key == "reset_view_rotation":
            self._canvas.reset_rotation()
            return
        if key == "transform_params":
            layer = self._document.get_active_layer()
            if layer and getattr(layer, "layer_type", "raster") == "text":
                if hasattr(self, "_status"):
                    self._status.showMessage(tr("err.text_layer_no_transform"), 3000)
                tool = self._canvas.active_tool
                if hasattr(tool, "cancel_transform"):
                    tool.cancel_transform(self._document)
                    self._canvas_refresh()
                    self._opts_bar.update_tool_state(None)
                return
            tool = self._canvas.active_tool
            if hasattr(tool, "set_transform_params"):
                tool.set_transform_params(self._document, value)
                self._canvas_refresh()
            return
        if key == "sampler_clear":
            tool = self._tools.get("ColorSampler")
            if tool: tool.markers.clear()
            self._canvas_refresh()
            return
        if key == "ruler_clear":
            tool = self._tools.get("Ruler")
            if tool: tool.clear()
            self._canvas_refresh()
            return
        if key == "clear_slices":
            if hasattr(self._document, "slices"):
                self._document.slices.clear()
                self._canvas_refresh()
            return
        if key == "move_apply":
            self._commit_move_transform()
            return
        if key == "move_cancel":
            tool = self._canvas.active_tool
            if hasattr(tool, "is_transforming") and tool.is_transforming:
                tool.cancel_transform(self._document)
                self._canvas_refresh()
                self._opts_bar.update_tool_state(None)
            return
        if key == "pen_action":
            tool = self._canvas.active_tool
            if hasattr(tool, "perform_action"):
                result = tool.perform_action(self._document, value, self._canvas.fg_color)
                if result:
                    action, path = result
                    if action == "selection":
                        self._push_history(tr("history.quick_mask"))
                        self._document.selection = path
                    elif action == "shape":
                        self._push_history("New Vector Shape")
                        from core.layer import Layer
                        n = sum(1 for l in self._document.layers if getattr(l, "layer_type", "raster") == "vector") + 1
                        new_layer = self._document.add_layer(f"Path {n}", self._document.active_layer_index + 1)
                        new_layer.layer_type = "vector"
                        new_layer.vector_mask = QPainterPath(path)
                        new_layer.vector_mask_enabled = True
                        p = QPainter(new_layer.image)
                        p.fillPath(path, QBrush(self._canvas.fg_color))
                        p.end()
                self._refresh_layers()
                self._canvas_refresh()
            return
        if not hasattr(self, "_doc_tabs"): return
        for i in range(self._doc_tabs.count()):
            self._doc_tabs.widget(i).tool_opts[key] = value

    def _on_layer_blend_mode(self, mode: str):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "blend_mode", "SourceOver") != mode:
            layer.blend_mode = mode
            self._push_history(tr("history.layer_blend"))
            self._canvas_refresh()

    def _on_layer_lock_changed(self, lock_type: str, locked: bool):
        layer = self._document.get_active_layer()
        if layer:
            if lock_type == "alpha": layer.lock_alpha = locked
            elif lock_type == "pixels": layer.lock_pixels = locked
            elif lock_type == "position": layer.lock_position = locked
            elif lock_type == "artboard": layer.lock_artboard = locked
            elif lock_type == "all": layer.locked = locked
            self._push_history(tr("history.lock_changed"))
            self._refresh_layers()

    def _group_layer(self):
        idx = self._document.active_layer_index
        group = self._document.add_layer(tr("layer.name.group"), idx + 1)
        group.layer_type = "group"
        layer = self._document.layers[idx]
        layer.parent_id = group.layer_id
        self._push_history(tr("history.new_group"))
        self._refresh_layers()
        
    def _link_layer(self):
        idx = self._document.active_layer_index
        if idx > 0:
            l1 = self._document.layers[idx]
            l2 = self._document.layers[idx - 1]
            import uuid
            new_link = l2.link_id if l2.link_id else str(uuid.uuid4())
            if l1.link_id == new_link: l1.link_id = None
            else: l1.link_id = new_link
            self._push_history(tr("history.link_layers"))
            self._refresh_layers()

    def _on_layer_target_changed(self, index: int, target: str):
        if 0 <= index < len(self._document.layers):
            self._document.active_layer_index = index
            layer = self._document.layers[index]
            layer.editing_mask = (target == "mask")
            self._refresh_layers()

    def _on_layer_mask_toggled(self, index: int):
        if 0 <= index < len(self._document.layers):
            layer = self._document.layers[index]
            if getattr(layer, "mask", None) is not None:
                layer.mask_enabled = not getattr(layer, "mask_enabled", True)
                self._push_history(tr("history.toggle_mask"))
                self._refresh_layers()
                self._canvas_refresh()

    def _add_vector_mask(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "vector_mask", None) is None:
            if self._document.selection and not self._document.selection.isEmpty():
                layer.vector_mask = QPainterPath(self._document.selection)
            else:
                path = QPainterPath()
                path.addRect(QRectF(0, 0, self._document.width, self._document.height))
                layer.vector_mask = path
            layer.vector_mask_enabled = True
            self._push_history(tr("history.add_vector_mask"))
            self._refresh_layers()
            self._canvas_refresh()

    def _delete_vector_mask(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "vector_mask", None) is not None:
            layer.vector_mask = None
            self._push_history(tr("history.delete_vector_mask"))
            self._refresh_layers()
            self._canvas_refresh()

    def _on_layer_vmask_toggled(self, index: int):
        if 0 <= index < len(self._document.layers):
            layer = self._document.layers[index]
            if getattr(layer, "vector_mask", None) is not None:
                layer.vector_mask_enabled = not getattr(layer, "vector_mask_enabled", True)
                self._push_history(tr("history.toggle_vector_mask"))
                self._refresh_layers()
                self._canvas_refresh()
                
    def _toggle_clipping_mask(self):
        if self._document and self._document.get_active_layer():
            self._on_layer_clipping_toggled(self._document.active_layer_index)
            
    def _on_layer_clipping_toggled(self, index: int):
        if 0 < index < len(self._document.layers): # Нельзя применить к самому нижнему слою
            layer = self._document.layers[index]
            self._push_history(tr("history.clipping_mask"))
            layer.clipping = not getattr(layer, "clipping", False)
            self._refresh_layers()
            self._canvas_refresh()

    def _add_mask(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "mask", None) is None:
            from PyQt6.QtGui import QImage, QColor
            layer.mask = QImage(layer.width(), layer.height(), QImage.Format.Format_ARGB32_Premultiplied)
            layer.mask.fill(QColor(255, 255, 255))
            layer.editing_mask = True
            self._push_history(tr("history.add_mask"))
            self._refresh_layers()
            self._canvas_refresh()

    def _delete_mask(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "mask", None) is not None:
            layer.mask = None
            layer.editing_mask = False
            self._push_history(tr("history.delete_mask"))
            self._refresh_layers()
            self._canvas_refresh()

    def _apply_mask(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "mask", None) is not None:
            self._document.apply_layer_mask(layer)
            self._push_history(tr("history.apply_mask"))
            self._refresh_layers()
            self._canvas_refresh()

    def _invert_mask(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "mask", None) is not None:
            layer.mask.invertPixels()
            self._push_history(tr("history.invert_mask"))
            self._refresh_layers()
            self._canvas_refresh()

    def _invert(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "editing_mask", False) and getattr(layer, "mask", None) is not None:
            self._invert_mask()
        elif hasattr(super(), "_invert"):
            super()._invert()

    def _toggle_quick_mask(self):
        if not self._document: return
        
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr("history.quick_mask"),
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
        
        if getattr(self._document, "quick_mask_layer", None) is not None:
            # Выход из режима Быстрой Маски
            qm = self._document.quick_mask_layer.image
            import numpy as np
            from PyQt6.QtGui import QImage, QRegion, QBitmap
            
            ptr = qm.bits(); ptr.setsize(qm.sizeInBytes())
            arr = np.ndarray((qm.height(), qm.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=ptr)[:, :self._document.width, :]
            
            gray = 0.299*arr[..., 2] + 0.587*arr[..., 1] + 0.114*arr[..., 0]
            mask_val = (255 - gray) * (arr[..., 3] / 255.0)
            
            sel_alpha = np.zeros((qm.height(), self._document.width, 4), dtype=np.uint8)
            sel_alpha[mask_val < 128, 3] = 255
            
            sel_img = QImage(sel_alpha.data, self._document.width, qm.height(), self._document.width*4, QImage.Format.Format_RGBA8888)
            path = QPainterPath()
            path.addRegion(QRegion(QBitmap.fromImage(sel_img.createAlphaMask())))
            
            self._document.selection = path.simplified()
            self._document.quick_mask_layer = None
            
            if hasattr(self, "_qm_old_fg"):
                self._color_panel.set_fg(self._qm_old_fg)
                self._canvas.fg_color = self._qm_old_fg
                self._color_panel.set_bg(self._qm_old_bg)
                self._canvas.bg_color = self._qm_old_bg
        else:
            # Вход в режим Быстрой маски
            from core.layer import Layer
            from PyQt6.QtGui import QPainter
            
            layer = Layer("Quick Mask", self._document.width, self._document.height)
            layer.is_quick_mask = True
            
            sel = self._document.selection
            if sel and not sel.isEmpty():
                layer.image.fill(QColor(0, 0, 0))
                p = QPainter(layer.image)
                p.setClipPath(sel)
                p.fillRect(layer.image.rect(), QColor(255, 255, 255))
                p.end()
            else:
                layer.image.fill(QColor(255, 255, 255))
            
            self._document.quick_mask_layer = layer
            
            self._qm_old_fg = self._canvas.fg_color
            self._qm_old_bg = self._canvas.bg_color
            self._color_panel.set_fg(QColor(0, 0, 0))
            self._canvas.fg_color = QColor(0, 0, 0)
            self._color_panel.set_bg(QColor(255, 255, 255))
            self._canvas.bg_color = QColor(255, 255, 255)
            
        self._history.push(pre_state)
        self._canvas_refresh()
        self._refresh_layers()

    def _get_adj_dialog(self, layer, t):
        is_adj = getattr(layer, "layer_type", "raster") == "adjustment"
        if is_adj:
            _saved_adj = layer.adjustment_data
            layer.adjustment_data = {"type": t}
            target_img = self._document.get_composite()
            layer.adjustment_data = _saved_adj
        else:
            target_img = layer.image

        class LayerProxy:
            def __init__(self, real, img):
                self.__dict__["_real"] = real
                self.__dict__["image"] = img
            def __getattr__(self, name):
                return getattr(self._real, name)
            def __setattr__(self, name, value):
                if name == "image":
                    self.__dict__["image"] = value
                    if getattr(self._real, "layer_type", "raster") != "adjustment":
                        self._real.image = value
                elif name == "adjustment_data":
                    self._real.adjustment_data = value
                else:
                    setattr(self._real, name, value)

        proxy = LayerProxy(layer, target_img)
        dlg_ref = [None]

        def scrape_data():
            d = {"type": t}
            dlg = dlg_ref[0]
            if not dlg: return d
            for k, v in dlg.__dict__.items():
                if k == "_lut": d["lut"] = v
                elif hasattr(v, "value") and callable(v.value):
                    try: d[k.lstrip('_')] = v.value()
                    except TypeError: pass
                elif hasattr(v, "color") and callable(v.color):
                    try: d[k.lstrip('_')] = v.color()
                    except TypeError: pass
                elif hasattr(v, "isChecked") and callable(v.isChecked):
                    try: d[k.lstrip('_')] = v.isChecked()
                    except TypeError: pass
            return d

        def wrapped_refresh():
            if is_adj:
                layer.adjustment_data = scrape_data()
            self._canvas_refresh()

        import inspect
        def create_dlg(DialogClass):
            sig = inspect.signature(DialogClass.__init__)
            params = [p for p in sig.parameters.values() if p.name != 'self']
            if len(params) >= 3 and params[1].name in ("canvas_refresh", "cb"):
                return DialogClass(proxy, wrapped_refresh, self)
            else:
                dlg_inst = DialogClass(target_img, self)
                dlg_inst._canvas_refresh = wrapped_refresh
                return dlg_inst

        if t == "levels":
            from ui.levels_dialog import LevelsDialog
            dlg = create_dlg(LevelsDialog)
        elif t == "exposure":
            from ui.more_adjustments import ExposureDialog
            dlg = create_dlg(ExposureDialog)
        elif t == "vibrance":
            from ui.more_adjustments import VibranceDialog
            dlg = create_dlg(VibranceDialog)
        elif t == "black_white":
            from ui.more_adjustments import BlackWhiteDialog
            dlg = create_dlg(BlackWhiteDialog)
        elif t == "posterize":
            from ui.more_adjustments import PosterizeDialog
            dlg = create_dlg(PosterizeDialog)
        elif t == "threshold":
            from ui.more_adjustments import ThresholdDialog
            dlg = create_dlg(ThresholdDialog)
        elif t == "photo_filter":
            from ui.more_adjustments import PhotoFilterDialog
            dlg = create_dlg(PhotoFilterDialog)
        elif t == "gradient_map":
            from ui.more_adjustments import GradientMapDialog
            dlg = create_dlg(GradientMapDialog)
        elif t == "color_lookup":
            from core.adjustments.color_lookup import ColorLookupDialog
            dlg = create_dlg(ColorLookupDialog)
        elif t == "hdr_toning":
            from core.adjustments.hdr_toning import HDRToningDialog
            dlg = create_dlg(HDRToningDialog)
        else:
            from ui.adjustment_layer_dialog import AdjustmentLayerDialog
            return AdjustmentLayerDialog(layer, self._canvas_refresh, self)
            
        dlg_ref[0] = dlg
        if is_adj:
            dlg._is_adj_layer = True
            dlg._layer = layer
            import copy
            dlg._orig_adj_data = copy.deepcopy(layer.adjustment_data) if layer.adjustment_data else {}
            dlg._adj_type = t
            
            layer.adjustment_data = scrape_data()
            
            dlg.accepted.connect(lambda: setattr(layer, "adjustment_data", scrape_data()))
            def on_reject():
                layer.adjustment_data = dlg._orig_adj_data
                self._canvas_refresh()
            dlg.rejected.connect(on_reject)

        return dlg

    def _new_adj_layer(self, adj_type: str):
        if not self._document: return
        idx = self._document.active_layer_index
        self._push_history(tr("history.new_adj_layer"))  # snapshot BEFORE adding
        layer = self._document.add_layer(tr("layer.name.adjustment"), idx + 1)
        layer.layer_type = "adjustment"
        layer.adjustment_data = {"type": adj_type}

        dlg = self._get_adj_dialog(layer, adj_type)
        if dlg and dlg.exec():
            self._refresh_layers()
        else:
            self._history.undo()  # discard the snapshot we just pushed
            self._document.layers.remove(layer)
            self._document.active_layer_index = idx
            self._canvas_refresh()
            self._refresh_layers()

    def _on_edit_layer(self):
        layer = self._document.get_active_layer()
        if not layer:
            return
        ltype = getattr(layer, "layer_type", "raster")
        if ltype == "fill":
            from ui.fill_layer_dialog import FillLayerDialog
            dlg = FillLayerDialog(layer, self._canvas_refresh, self)
            if dlg.exec():
                self._push_history(tr("history.edit_fill_layer"))
                self._refresh_layers()
            else:
                self._canvas_refresh()
        elif ltype == "adjustment":
            t = (layer.adjustment_data or {}).get("type", "")
            dlg = self._get_adj_dialog(layer, t)
            
            if dlg and dlg.exec():
                self._push_history(tr("history.edit_adj_layer"))
                self._refresh_layers()
            else:
                self._canvas_refresh()
        elif hasattr(super(), "_on_edit_layer"):
            super()._on_edit_layer()
            
    def _new_smart_object(self):
        layer = self._document.get_active_layer()
        if not layer or getattr(layer, "layer_type", "raster") == "smart_object":
            return
        self._push_history(tr("history.new_smart_object"))
        layer.layer_type = "smart_object"
        if not hasattr(layer, "smart_data") or layer.smart_data is None:
            layer.smart_data = {}
        layer.smart_data["original"] = layer.image.copy()
        self._refresh_layers()
        self._canvas_refresh()
        
    def _clear_smart_filters(self):
        layer = self._document.get_active_layer()
        if layer and getattr(layer, "layer_type", "raster") == "smart_object":
            if hasattr(layer, "smart_data") and layer.smart_data and "original" in layer.smart_data:
                self._push_history(tr("history.clear_smart_filters"))
                layer.image = layer.smart_data["original"].copy()
                self._canvas_refresh()
                self._refresh_layers()

    def _export_slices(self):
        slices = getattr(self._document, "slices", [])
        if not slices:
            QMessageBox.information(self, "ImageFinish", tr("err.no_slices"))
            return
        dir_path = QFileDialog.getExistingDirectory(self, tr("dlg.export_slices"))
        if not dir_path: return
        comp = self._document.get_composite()
        count = 0
        for i, r in enumerate(slices):
            c = r.intersected(comp.rect())
            if not c.isEmpty():
                comp.copy(c).save(f"{dir_path}/slice_{i+1}.png")
                count += 1
        self._status.showMessage(tr("status.slices_exported", count=count))

    def _export_layer_png(self):
        if not self._document: return
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull(): return
        path, _ = QFileDialog.getSaveFileName(self, tr("menu.export_layer_png"), f"{layer.name}.png", "PNG (*.png)")
        if path:
            layer.image.save(path)
            self._status.showMessage(tr("status.saved", path=path))

    def _get_define_image(self):
        doc = self._document
        comp = doc.get_composite()
        if doc.selection and not doc.selection.isEmpty():
            br = doc.selection.boundingRect().toRect().intersected(comp.rect())
            if not br.isEmpty(): return comp.copy(br)
        return comp.copy()

    def _define_brush(self):
        from PyQt6.QtWidgets import QInputDialog
        import os
        import numpy as np
        from PyQt6.QtGui import QImage, QPainter
        img = self._get_define_image()
        name, ok = QInputDialog.getText(self, tr("dlg.define_brush_title"), tr("dlg.define_name"))
        if not ok or not name.strip(): return
        name = name.strip()
        w, h = img.width(), img.height()
        side = max(w, h)
        sq_img = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        sq_img.fill(0)
        p = QPainter(sq_img)
        p.drawImage((side - w) // 2, (side - h) // 2, img)
        p.end()
        sq_img = sq_img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        ptr = sq_img.constBits()
        ptr.setsize(sq_img.sizeInBytes())
        arr = np.frombuffer(bytearray(ptr), dtype=np.uint8).reshape((side, side, 4))
        del ptr
        luma = (arr[..., 2]*0.299 + arr[..., 1]*0.587 + arr[..., 0]*0.114)
        orig_alpha = arr[..., 3] / 255.0
        brush_img = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        brush_img.fill(0)
        b_ptr = brush_img.bits()
        b_ptr.setsize(brush_img.sizeInBytes())
        b_arr = np.frombuffer(b_ptr, dtype=np.uint8).reshape((side, side, 4))
        b_arr[..., 3] = ((255 - luma) * orig_alpha).astype(np.uint8)
        del b_arr
        del b_ptr
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.join(base_dir, "brushes")
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{name}.png")
        brush_img.save(path)
        brush_page = self._opts_bar._pages.get("Brush")
        if hasattr(brush_page, "add_custom_brush"): brush_page.add_custom_brush(path, name)

    def _define_pattern(self):
        from PyQt6.QtWidgets import QInputDialog
        import os
        img = self._get_define_image()
        name, ok = QInputDialog.getText(self, tr("dlg.define_pattern_title"), tr("dlg.define_name"))
        if not ok or not name.strip(): return
        name = name.strip()
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.join(base_dir, "patterns")
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{name}.png")
        img.save(path)
        pat_page = self._opts_bar._pages.get("PatternStamp")
        if hasattr(pat_page, "add_custom_pattern"): pat_page.add_custom_pattern(path, name)

    def _define_shape(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        import os, json
        doc = self._document
        if not doc.selection or doc.selection.isEmpty():
            QMessageBox.warning(self, tr("err.title.error"), tr("err.no_selection_shape"))
            return
        name, ok = QInputDialog.getText(self, tr("dlg.define_shape_title"), tr("dlg.define_name"))
        if not ok or not name.strip(): return
        name = name.strip()
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.join(base_dir, "shapes")
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{name}.json")
        data = [{"type": int(e.type.value) if hasattr(e.type, 'value') else int(e.type), "x": e.x, "y": e.y} for i in range(doc.selection.elementCount()) for e in [doc.selection.elementAt(i)]]
        with open(path, "w") as f: json.dump(data, f)
        shapes_page = self._opts_bar._pages.get("Shapes")
        if hasattr(shapes_page, "add_custom_shape"): shapes_page.add_custom_shape(path, name)

    def _on_apply_crop_requested(self):
        if self._active_tool_name == "Crop":
            self._apply_crop()
        elif self._active_tool_name == "Perspective Crop":
            self._apply_perspective_crop()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Return or e.key() == Qt.Key.Key_Enter:
            if self._active_tool_name == "Crop":
                self._apply_crop()
            elif self._active_tool_name == "Perspective Crop":
                self._apply_perspective_crop()
            elif self._active_tool_name in ("Move", "Warp", "PuppetWarp", "PerspectiveWarp"):
                self._commit_move_transform()
        elif e.key() == Qt.Key.Key_Escape:
            if self._active_tool_name in ("Move", "Warp", "PuppetWarp", "PerspectiveWarp"):
                tool = self._canvas.active_tool
                if hasattr(tool, "is_transforming") and tool.is_transforming:
                    tool.cancel_transform(self._document)
                    self._canvas_refresh()
        super().keyPressEvent(e)
        
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()
        else:
            super().dragEnterEvent(ev)
            
    def dropEvent(self, ev):
        shift_pressed = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        for url in ev.mimeData().urls():
            path = url.toLocalFile()
            if not path: continue
            if shift_pressed and self._document:
                from PyQt6.QtGui import QImage
                import os
                img = QImage(path)
                if not img.isNull():
                    self._push_history(tr("history.add_layer"))
                    img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                    name = os.path.basename(path)
                    idx = self._document.active_layer_index
                    layer = self._document.add_layer(name, idx + 1)
                    layer.image = img
                    layer.offset = QPoint((self._document.width - img.width()) // 2, (self._document.height - img.height()) // 2)
                    self._refresh_layers()
                    self._canvas_refresh()
                else:
                    self._open_file_path(path)
            else:
                self._open_file_path(path)

    def _apply_text_styles(self):
        from tools.other_tools import _render_text, TextTool
        layer = self._document.get_active_layer()
        if not layer or not getattr(layer, "text_data", None):
            return
        self._push_history(tr("history.apply_text"))
        td   = layer.text_data
        opts = self._canvas.tool_opts
        layer.image.fill(Qt.GlobalColor.transparent)
        sel = self._document.selection
        _render_text(layer.image, td["x"], td["y"], td["text"], opts,
                     sel if (sel and not sel.isEmpty()) else None)
        layer.text_data = {**td, **TextTool._snap_opts(opts)}
        self._canvas_refresh()
        self._refresh_layers()

    # ================================================================= Blur Gallery
    def _open_blur_gallery(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr("menu.blur_gallery") + f" ({mode})",
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
            
        from ui.blur_gallery_dialog import BlurGalleryDialog
        dlg = BlurGalleryDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Specific Filters
    def _open_specific_filter(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(f"menu.filter.{mode}").replace('…', ''),
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
            
        from ui.specific_filters_dialog import SpecificFiltersDialog
        dlg = SpecificFiltersDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Render Gallery
    def _open_render(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(f"menu.render.{mode}").replace('…', ''),
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
            
        from ui.render_dialog import RenderDialog
        dlg = RenderDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Recent Files
    def _load_recent_files(self):
        settings = QSettings("ImageFinish", "RecentFiles")
        self._recent_files = settings.value("recent", [])
        if not isinstance(self._recent_files, list):
            self._recent_files = []

    def _save_recent_files(self):
        settings = QSettings("ImageFinish", "RecentFiles")
        settings.setValue("recent", self._recent_files)

    def _add_recent_file(self, path):
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        if len(self._recent_files) > 30:
            self._recent_files = self._recent_files[:30]
        self._save_recent_files()
        self._update_recent_menu()
        if hasattr(self, "_welcome_panel"):
            self._welcome_panel.refresh_recent(self._recent_files)

    def _remove_recent_file(self, path):
        if path in self._recent_files:
            self._recent_files.remove(path)
            self._save_recent_files()
            self._update_recent_menu()

    def _update_recent_menu(self):
        if not hasattr(self, "_recent_menu"): return
        self._recent_menu.clear()
        if not self._recent_files:
            act = QAction(tr("menu.no_recent"), self)
            act.setEnabled(False)
            self._recent_menu.addAction(act)
        else:
            for path in self._recent_files:
                act = QAction(path, self)
                act.triggered.connect(lambda checked, p=path: self._open_recent(p))
                self._recent_menu.addAction(act)
            self._recent_menu.addSeparator()
            clear_act = QAction(tr("menu.clear_recent"), self)
            clear_act.triggered.connect(self._clear_recent)
            self._recent_menu.addAction(clear_act)

    def _clear_recent(self):
        self._recent_files.clear()
        self._save_recent_files()
        self._update_recent_menu()

    def _open_recent(self, path):
        import os
        if not os.path.exists(path):
            QMessageBox.warning(self, tr("err.title.error"), tr("err.could_not_open").format(path=path))
            self._remove_recent_file(path)
            return
            
        # Если в FileActionsMixin есть готовый метод загрузки, используем его
        if hasattr(self, "_open_file_path"):
            self._open_file_path(path)

    # ================================================================= Sharpen Gallery
    def _open_sharpen(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(f"menu.sharpen.{mode}").replace('…', ''),
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
            
        from ui.sharpen_dialog import SharpenDialog
        dlg = SharpenDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Stylize Gallery
    def _open_stylize(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(f"menu.stylize.{mode}").replace('…', ''),
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
            
        from ui.stylize_dialog import StylizeDialog
        dlg = StylizeDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Other Gallery
    def _open_other(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(f"menu.other.{mode}").replace('…', ''),
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
            
        from ui.other_filters_dialog import OtherFiltersDialog
        dlg = OtherFiltersDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Pixelate Gallery
    def _open_pixelate(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(f"menu.pixelate.{mode}").replace('…', ''),
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
            
        from ui.pixelate_dialog import PixelateDialog
        dlg = PixelateDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Noise Gallery
    def _open_noise(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        desc_key = "menu.noise.add"
        if mode == "despeckle": desc_key = "menu.noise.despeckle"
        elif mode == "dust_scratches": desc_key = "menu.noise.dust"
        elif mode == "median": desc_key = "menu.noise.median"
        elif mode == "reduce_noise": desc_key = "menu.noise.reduce"
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(desc_key).replace('…', ''),
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
            
        from ui.noise_dialog import NoiseDialog
        if NoiseDialog(layer, mode, self._canvas_refresh, self).exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()
            
    def _blur_field(self): self._open_blur_gallery("field")
    def _blur_iris(self): self._open_blur_gallery("iris")
    def _blur_tilt_shift(self): self._open_blur_gallery("tilt_shift")
    def _blur_path(self): self._open_blur_gallery("path")
    def _blur_spin(self): self._open_blur_gallery("spin")

    # ================================================================= Distort Gallery
    def _open_distort(self, mode: str):
        layer = self._document.get_active_layer()
        if not layer or layer.image.isNull() or getattr(layer, "layer_type", "raster") not in ("raster", "smart_object"):
            return
            
        from core.history import HistoryState, clone_work_path
        pre_state = HistoryState(
            description=tr(f"menu.distort.{mode}"),
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
            
        from ui.distort_dialog import DistortDialog
        dlg = DistortDialog(layer, mode, self._canvas_refresh, self)
        if dlg.exec():
            self._history.push(pre_state)
            self._canvas_refresh()
            self._refresh_layers()
        else:
            self._canvas_refresh()

    # ================================================================= Panel handlers

    def _history_jump(self, steps: int):
        """Called by HistoryPanel.jump_requested: positive=undo N, negative=redo N."""
        if not self._canvas:
            return
        if steps > 0:
            for _ in range(steps):
                self._undo()
        elif steps < 0:
            for _ in range(-steps):
                self._redo()

    def _on_nav_zoom(self, zoom_factor: float):
        if not self._canvas:
            return
        current = self._canvas.zoom
        if current > 0:
            self._canvas._apply_zoom(zoom_factor / current, self._canvas.rect().center())

    def _on_glyph_inserted(self, char: str):
        """Insert a glyph character — for now copies to clipboard."""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(char)

    def _on_action_requested(self, action_name: str):
        if not self._canvas or not self._document:
            return
        self._push_history(f"Before {action_name}")
        from PyQt6.QtGui import QImage
        import numpy as np
        doc = self._document
        layer = doc.get_active_layer()

        if action_name == "Invert":
            from ui.adjustments_dialog import apply_invert
            if layer:
                layer.image = apply_invert(layer.image)

        elif action_name in ("Desaturate", "Grayscale Mode"):
            from ui.adjustments_dialog import apply_hue_saturation
            if layer:
                src = layer.image.convertToFormat(QImage.Format.Format_ARGB32)
                layer.image = apply_hue_saturation(src, 0, -100, 0)

        elif action_name == "Sharpen":
            if layer:
                img = layer.image.convertToFormat(QImage.Format.Format_ARGB32)
                try:
                    ptr = img.bits(); ptr.setsize(img.sizeInBytes())
                    arr = np.frombuffer(ptr, dtype=np.uint8).copy().reshape(img.height(), img.width(), 4)
                    kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]], dtype=float)
                    from scipy.ndimage import convolve
                    for c in range(3):
                        arr[...,c] = np.clip(convolve(arr[...,c].astype(float), kernel), 0, 255).astype(np.uint8)
                    out = QImage(arr.tobytes(), img.width(), img.height(), QImage.Format.Format_ARGB32)
                    layer.image = out.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                except Exception:
                    pass

        elif action_name == "Flatten Image":
            self._flatten()
            return

        elif action_name == "Auto Levels":
            if layer:
                img = layer.image.convertToFormat(QImage.Format.Format_ARGB32)
                try:
                    ptr = img.bits(); ptr.setsize(img.sizeInBytes())
                    arr = np.frombuffer(ptr, dtype=np.uint8).copy().reshape(img.height(), img.width(), 4)
                    for c in range(3):
                        ch = arr[...,c]
                        lo, hi = int(ch.min()), int(ch.max())
                        if hi > lo:
                            arr[...,c] = np.clip((ch.astype(float) - lo) * 255 / (hi - lo), 0, 255).astype(np.uint8)
                    out = QImage(arr.tobytes(), img.width(), img.height(), QImage.Format.Format_ARGB32)
                    layer.image = out.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                except Exception:
                    pass

        self._canvas_refresh()
        self._refresh_layers()

    def _on_transform_changed(self, x: int, y: int):
        if not self._canvas:
            return
        self._push_history("Move Layer")
        self._canvas_refresh()
        self._properties_panel.refresh(self._canvas)

    def _do_align_layer(self, direction: str):
        if not self._canvas or not self._document:
            return
        layer = self._document.get_active_layer()
        if not layer:
            return
        doc = self._document
        off = getattr(layer, "offset", QPoint(0, 0))
        lw = layer.image.width() if layer.image and not layer.image.isNull() else 0
        lh = layer.image.height() if layer.image and not layer.image.isNull() else 0
        self._push_history("Align Layer")
        if direction == "left":
            layer.offset = QPoint(0, off.y())
        elif direction == "center_h":
            layer.offset = QPoint((doc.width - lw) // 2, off.y())
        elif direction == "right":
            layer.offset = QPoint(doc.width - lw, off.y())
        elif direction == "top":
            layer.offset = QPoint(off.x(), 0)
        elif direction == "center_v":
            layer.offset = QPoint(off.x(), (doc.height - lh) // 2)
        elif direction == "bottom":
            layer.offset = QPoint(off.x(), doc.height - lh)
        self._canvas_refresh()
        self._properties_panel.refresh(self._canvas)

    def _on_brush_selected(self, mask: str):
        if self._canvas:
            self._canvas.tool_opts["brush_mask"] = mask
            self._opts_bar.update_tool_state({"brush_mask": mask})

    def _on_preset_save_requested(self, name: str):
        if self._canvas:
            opts = dict(self._canvas.tool_opts)
            self._tool_presets_panel.add_preset(name, self._active_tool_name, opts)

    def _on_preset_selected(self, tool_name: str, opts: dict):
        if self._canvas:
            self._canvas.tool_opts.update(opts)
            self._activate_tool(tool_name)
            self._opts_bar.update_tool_state(opts)

    def _path_make_selection(self):
        if not self._document:
            return
        wp = getattr(self._document, "work_path", None)
        if not wp or not wp.get("nodes"):
            return
        from PyQt6.QtGui import QPainterPath
        from PyQt6.QtCore import QPointF
        path = QPainterPath()
        nodes = wp["nodes"]
        if nodes:
            path.moveTo(QPointF(nodes[0]["p"]))
            for i in range(1, len(nodes)):
                path.cubicTo(QPointF(nodes[i-1]["c2"]), QPointF(nodes[i]["c1"]), QPointF(nodes[i]["p"]))
            if wp.get("closed") and len(nodes) > 1:
                path.cubicTo(QPointF(nodes[-1]["c2"]), QPointF(nodes[0]["c1"]), QPointF(nodes[0]["p"]))
                path.closeSubpath()
        self._push_history("Before Make Selection")
        self._document.selection = path
        self._canvas_refresh()

    def _path_fill(self):
        if not self._document:
            return
        self._push_history("Before Fill Path")
        layer = self._document.get_active_layer()
        if layer:
            from PyQt6.QtGui import QPainter, QColor
            p = QPainter(layer.image)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.setBrush(self._canvas.fg_color)
            p.setPen(Qt.PenStyle.NoPen)
            wp = getattr(self._document, "work_path", None)
            if wp and wp.get("nodes"):
                from PyQt6.QtGui import QPainterPath
                from PyQt6.QtCore import QPointF
                path = QPainterPath()
                nodes = wp["nodes"]
                path.moveTo(QPointF(nodes[0]["p"]))
                for i in range(1, len(nodes)):
                    path.cubicTo(QPointF(nodes[i-1]["c2"]), QPointF(nodes[i]["c1"]), QPointF(nodes[i]["p"]))
                if wp.get("closed"):
                    path.closeSubpath()
                p.drawPath(path)
            p.end()
        self._canvas_refresh()

    def _path_stroke(self):
        if not self._document:
            return
        self._push_history("Before Stroke Path")
        layer = self._document.get_active_layer()
        if layer:
            from PyQt6.QtGui import QPainter, QPen
            p = QPainter(layer.image)
            pen = QPen(self._canvas.fg_color, self._canvas.tool_opts.get("brush_size", 2))
            p.setPen(pen)
            wp = getattr(self._document, "work_path", None)
            if wp and wp.get("nodes"):
                from PyQt6.QtGui import QPainterPath
                from PyQt6.QtCore import QPointF
                path = QPainterPath()
                nodes = wp["nodes"]
                path.moveTo(QPointF(nodes[0]["p"]))
                for i in range(1, len(nodes)):
                    path.cubicTo(QPointF(nodes[i-1]["c2"]), QPointF(nodes[i]["c1"]), QPointF(nodes[i]["p"]))
                if wp.get("closed"):
                    path.closeSubpath()
                p.drawPath(path)
            p.end()
        self._canvas_refresh()

    def _path_delete(self):
        if self._document:
            self._push_history("Before Delete Path")
            self._document.work_path = {"nodes": [], "closed": False}
            self._paths_panel.refresh(self._canvas)
            self._canvas_refresh()
