from dataclasses import dataclass

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy, QToolButton, QMenu
from PyQt6.QtCore import pyqtSignal, Qt

from core.locale import tr


@dataclass(frozen=True)
class _ToolDef:
    name: str
    icon: str
    shortcut: str
    tr_key: str


class ToolBar(QWidget):
    """
    Vertical toolbar on the left side.
    Emits tool_selected(tool_name) when a button is clicked.
    """

    tool_selected = pyqtSignal(str)

    _TOOL_DEFS: dict[str, _ToolDef] = {
        "Move":          _ToolDef("Move",          "✋",  "V", "tool.move"),
        "Artboard":      _ToolDef("Artboard",      "🔲", "V", "tool.artboard"),
        "Warp":          _ToolDef("Warp",          "🕸️", "V", "tool.warp"),
        "PuppetWarp":    _ToolDef("PuppetWarp",    "📌", "V", "tool.puppet_warp"),
        "PerspectiveWarp":_ToolDef("PerspectiveWarp","🗺️", "V", "tool.perspective_warp"),
        "Brush":         _ToolDef("Brush",         "🖌️", "B", "tool.brush"),
        "Pencil":        _ToolDef("Pencil",        "✏️", "B", "tool.pencil"),
        "ColorReplacement":_ToolDef("ColorReplacement", "🖌️🎨", "B", "tool.color_replacement"),
        "MixerBrush":    _ToolDef("MixerBrush",    "🖌️💧", "B", "tool.mixer_brush"),
        "HistoryBrush":  _ToolDef("HistoryBrush",  "🕰️", "Y", "tool.history_brush"),
        "CloneStamp":    _ToolDef("CloneStamp",    "⎘",  "S", "tool.clone_stamp"),
        "PatternStamp":  _ToolDef("PatternStamp",  "💠", "S", "tool.pattern_stamp"),
        "SpotHealing":   _ToolDef("SpotHealing",   "🩹✨", "J", "tool.spot_healing"),
        "HealingBrush":  _ToolDef("HealingBrush",  "🩹🖌️", "J", "tool.healing_brush"),
        "Patch":         _ToolDef("Patch",         "🩹", "J", "tool.patch"),
        "RedEye":        _ToolDef("RedEye",        "👁️", "J", "tool.red_eye"),
        "Eraser":        _ToolDef("Eraser",        "🧹",  "E", "tool.eraser"),
        "BackgroundEraser": _ToolDef("BackgroundEraser", "✂️", "E", "tool.bg_eraser"),
        "MagicEraser":      _ToolDef("MagicEraser",      "🎇", "E", "tool.magic_eraser"),
        "Fill":          _ToolDef("Fill",          "🪣",  "K", "tool.fill"),
        "Gradient":      _ToolDef("Gradient",      "🌈",  "G", "tool.gradient"),
        "Blur":          _ToolDef("Blur",          "💧",  "R", "tool.blur"),
        "Sharpen":       _ToolDef("Sharpen",       "🔺",  "Y", "tool.sharpen"),
        "Smudge":        _ToolDef("Smudge",        "👆",  "W", "tool.smudge"),
        "Dodge":         _ToolDef("Dodge",         "🌔",  "O", "tool.dodge"),
        "Burn":          _ToolDef("Burn",          "🌒",  "O", "tool.burn"),
        "Sponge":        _ToolDef("Sponge",        "🧽",  "O", "tool.sponge"),
        "Select":        _ToolDef("Select",        "⬜",  "M", "tool.select"),
        "EllipseSelect": _ToolDef("EllipseSelect", "⭕",  "",  "tool.ellipse_select"),
        "Shapes":        _ToolDef("Shapes",        "🔷",  "U", "tool.shapes"),
        "Pen":           _ToolDef("Pen",           "✒️", "P", "tool.pen"),
        "FreeformPen":   _ToolDef("FreeformPen",   "✍️", "P", "tool.freeform_pen"),
        "CurvaturePen":  _ToolDef("CurvaturePen",  "〰️", "P", "tool.curvature_pen"),
        "AddAnchor":     _ToolDef("AddAnchor",     "✒️+", "", "tool.add_anchor"),
        "DeleteAnchor":  _ToolDef("DeleteAnchor",  "✒️-", "", "tool.delete_anchor"),
        "ConvertPoint":  _ToolDef("ConvertPoint",  "^",  "", "tool.convert_point"),
        "PathSelection": _ToolDef("PathSelection", "↖", "A", "tool.path_selection"),
        "DirectSelection":_ToolDef("DirectSelection","↗", "A", "tool.direct_selection"),
        "Text":          _ToolDef("Text",          "T",   "T", "tool.text"),
        "TextV":         _ToolDef("TextV",         "Tv",  "",  "tool.text_v"),
        "TextHMask":     _ToolDef("TextHMask",     "Tm",  "",  "tool.text_h_mask"),
        "TextVMask":     _ToolDef("TextVMask",     "Vm",  "",  "tool.text_v_mask"),
        "Eyedropper":    _ToolDef("Eyedropper",    "💉",  "I", "tool.eyedropper"),
        "ColorSampler":  _ToolDef("ColorSampler",  "🎯",  "I", "tool.color_sampler"),
        "Ruler":         _ToolDef("Ruler",         "📏",  "I", "tool.ruler"),
        "Crop":          _ToolDef("Crop",          "✂️",  "C", "tool.crop"),
        "Perspective Crop": _ToolDef("Perspective Crop", "📐", "", "tool.perspective_crop"),
        "Slice":         _ToolDef("Slice",         "🔪", "C", "tool.slice"),
        "Frame":         _ToolDef("Frame",         "⛶", "K", "tool.frame"),
        "Hand":          _ToolDef("Hand",          "🖐",  "H", "tool.hand"),
        "Zoom":          _ToolDef("Zoom",          "🔍",  "Z", "tool.zoom"),
        "RotateView":    _ToolDef("RotateView",    "🔄",  "",  "tool.rotate_view"),
        "Lasso":          _ToolDef("Lasso",          "➰", "L", "tool.lasso"),
        "PolygonalLasso": _ToolDef("PolygonalLasso", "⬡",  "",  "tool.poly_lasso"),
        "MagneticLasso":  _ToolDef("MagneticLasso",  "🧲", "",  "tool.mag_lasso"),
        "MagicWand":     _ToolDef("MagicWand",     "🪄", "W", "tool.magic_wand"),
        "QuickSelection": _ToolDef("QuickSelection", "🖌️✨", "W", "tool.quick_selection"),
        "ObjectSelection":_ToolDef("ObjectSelection", "📦",  "W", "tool.object_selection"),
    }

    # Order/structure of the toolbar. Groups behave like Photoshop dropdown tools.
    _LAYOUT = [
        ("MoveGroup", ["Move", "Artboard", "Warp", "PuppetWarp", "PerspectiveWarp"]),
        ("HealingGroup", ["SpotHealing", "HealingBrush", "Patch", "RedEye", "CloneStamp", "PatternStamp"]),
        ("BrushGroup", ["Brush", "Pencil", "ColorReplacement", "MixerBrush", "HistoryBrush"]),
        ("EraserGroup", ["Eraser", "BackgroundEraser", "MagicEraser"]),
        "Fill",
        "Gradient",
        ("Effects", ["Blur", "Sharpen", "Smudge"]),
        ("ToningGroup", ["Dodge", "Burn", "Sponge"]),
        ("Marquee", ["Select", "EllipseSelect"]),
        ("PathSelectGroup", ["PathSelection", "DirectSelection"]),
        ("PenGroup", ["Pen", "FreeformPen", "CurvaturePen", "AddAnchor", "DeleteAnchor", "ConvertPoint"]),
        "Shapes",
        ("Type", ["Text", "TextV", "TextHMask", "TextVMask"]),
        ("EyedropperGroup", ["Eyedropper", "ColorSampler", "Ruler"]),
        ("Crop", ["Crop", "Perspective Crop", "Slice", "Frame"]),
        ("Nav", ["Hand", "Zoom", "RotateView"]),
        ("LassoGroup", ["Lasso", "PolygonalLasso", "MagneticLasso"]),
        ("WandGroup", ["MagicWand", "QuickSelection", "ObjectSelection"]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setFixedWidth(62)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._buttons: dict[str, QWidget] = {}          # tool_name -> widget (button or group button)
        self._groups: dict[str, QToolButton] = {}       # group_id -> QToolButton
        self._group_tools: dict[str, list[str]] = {}    # group_id -> list of tool names
        self._tool_to_group: dict[str, str] = {}        # tool_name -> group_id
        self._group_active_tool: dict[str, str] = {}    # group_id -> current tool_name

        for item in self._LAYOUT:
            if isinstance(item, tuple):
                group_id, tool_names = item
                btn = self._make_group_button(group_id, tool_names)
                layout.addWidget(btn)
                continue

            tool_name = item
            td = self._TOOL_DEFS[tool_name]
            btn = QPushButton(td.icon)
            btn.setObjectName("toolBtn")
            btn.setToolTip(self._make_tip(td.tr_key, td.shortcut))
            btn.setCheckable(False)
            btn.setFixedSize(46, 38)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _, n=tool_name: self._on_click(n))
            layout.addWidget(btn)
            self._buttons[tool_name] = btn

        layout.addStretch()

        self.set_active("Brush")

    @staticmethod
    def _make_tip(key: str, shortcut: str) -> str:
        label = tr(key)
        return f"{label}  [{shortcut}]" if shortcut else label

    def retranslate(self):
        """Update all button tooltips to the current locale."""
        for tool_name, w in self._buttons.items():
            td = self._TOOL_DEFS.get(tool_name)
            if isinstance(w, QPushButton) and td:
                w.setToolTip(self._make_tip(td.tr_key, td.shortcut))

        # Group menus/tooltips
        for gid, gbtn in self._groups.items():
            active_tool = self._group_active_tool.get(gid)
            td = self._TOOL_DEFS.get(active_tool) if active_tool else None
            if td:
                gbtn.setToolTip(self._make_tip(td.tr_key, td.shortcut))
            menu = gbtn.menu()
            if menu:
                menu.clear()
                for tname in self._group_tools.get(gid, []):
                    tdef = self._TOOL_DEFS[tname]
                    act = menu.addAction(tdef.icon + "  " + tr(tdef.tr_key))
                    act.setData(tname)
                    act.triggered.connect(lambda checked=False, n=tname: self._on_click(n))

    def set_active(self, tool_name: str):
        # Standalone tools
        for name, w in self._buttons.items():
            if isinstance(w, QPushButton):
                w.setProperty("active", name == tool_name)
                w.style().unpolish(w)
                w.style().polish(w)

        # Group tools
        gid = self._tool_to_group.get(tool_name)
        for group_id, gbtn in self._groups.items():
            gbtn.setProperty("active", group_id == gid)
            gbtn.style().unpolish(gbtn)
            gbtn.style().polish(gbtn)

        if gid:
            self._group_active_tool[gid] = tool_name
            td = self._TOOL_DEFS.get(tool_name)
            if td:
                self._groups[gid].setText(td.icon)
                self._groups[gid].setToolTip(self._make_tip(td.tr_key, td.shortcut))

    def _on_click(self, name: str):
        self.set_active(name)
        self.tool_selected.emit(name)

    def _make_group_button(self, group_id: str, tool_names: list[str]) -> QToolButton:
        # Default = first tool in the group
        default_tool = tool_names[0]
        self._group_tools[group_id] = list(tool_names)
        for t in tool_names:
            self._tool_to_group[t] = group_id
        self._group_active_tool[group_id] = default_tool

        td = self._TOOL_DEFS[default_tool]
        btn = QToolButton()
        btn.setObjectName("toolBtn")
        btn.setText(td.icon)
        btn.setToolTip(self._make_tip(td.tr_key, td.shortcut))
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup)
        btn.setFixedSize(46, 38)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, b=btn: b.menu().exec(b.mapToGlobal(pos)))

        menu = QMenu(btn)
        for tname in tool_names:
            tdef = self._TOOL_DEFS[tname]
            act = menu.addAction(tdef.icon + "  " + tr(tdef.tr_key))
            act.setData(tname)
            act.triggered.connect(lambda checked=False, n=tname: self._on_click(n))
        btn.setMenu(menu)

        # Main click selects the currently active tool in the group
        btn.clicked.connect(lambda checked=False, gid=group_id: self._on_click(self._group_active_tool.get(gid, default_tool)))

        self._groups[group_id] = btn
        return btn
