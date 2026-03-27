import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QFrame, QComboBox, QListView)
from PyQt6.QtGui import QPainter, QColor, QPixmap, QFont
from PyQt6.QtCore import Qt, pyqtSignal

PANEL_LAYOUTS = {
    "sunset":    [{"pos": "bottom", "w": 0.62, "h": 0.28, "float": True}],
    "twilight":  [{"pos": "bottom", "w": 1.0,  "h": 0.22, "float": False}],
    "rainbow":   [{"pos": "top",    "w": 1.0,  "h": 0.16, "float": False},
                  {"pos": "bottom", "w": 0.45, "h": 0.26, "float": True}],
    "rarity":    [{"pos": "top",    "w": 1.0,  "h": 0.14, "float": False},
                  {"pos": "bottom", "w": 0.38, "h": 0.30, "float": True}],
    "applejack": [{"pos": "bottom", "w": 1.0,  "h": 0.26, "float": False}],
    "fluttershy":[{"pos": "bottom", "w": 0.70, "h": 0.22, "float": True}],
    "pinkie":    [{"pos": "bottom", "w": 1.0,  "h": 0.24, "float": False}],
}

class SafeCheckBox(QPushButton):
    """Кастомный чекбокс, который не ломается стилями QSS."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setStyleSheet("text-align: left; background: transparent; border: none; color: rgb(200, 190, 230); font-family: sans-serif;")
        self.toggled.connect(self._refresh)
        self._lbl = ""
        self._refresh()

    def setText(self, text):
        self._lbl = text
        self._refresh()

    def _refresh(self):
        super().setText(f"☑  {self._lbl}" if self.isChecked() else f"☐  {self._lbl}")

class PanelPreviewWidget(QWidget):
    def __init__(self, preset_id, panel_color="#1e1e2e", panel_opacity=90, parent=None):
        super().__init__(parent)
        self.preset_id = preset_id
        self.panel_color = panel_color
        self.panel_opacity = panel_opacity
        self.layout_configs = PANEL_LAYOUTS.get(preset_id, [])

    def set_appearance(self, color, opacity):
        self.panel_color = color
        self.panel_opacity = opacity
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(44, 42, 68))
        painter.drawRoundedRect(0, 0, w, h, 4, 4)

        for cfg in self.layout_configs:
            pw = int(w * cfg["w"])
            ph = int(h * cfg["h"])
            x = (w - pw) // 2
            y = h - ph if cfg["pos"] == "bottom" else 0

            color = QColor(self.panel_color)
            color.setAlphaF(max(self.panel_opacity / 100.0, 0.70))
            painter.setBrush(color)

            radius = 5 if cfg.get("float") else 0
            painter.drawRoundedRect(x, y, pw, ph, radius, radius)

        painter.end()

class PresetCard(QPushButton):
    def __init__(self, preset_id, char_name, desc_text, icon_path, parent=None):
        super().__init__(parent)
        self.preset_id = preset_id
        self.setFixedSize(160, 158)
        self.setProperty("cssClass", "preset-card")
        self.setProperty("active", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        px = QPixmap(icon_path)
        if not px.isNull():
            icon_lbl.setPixmap(px.scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        name_lbl = QLabel(char_name)
        name_lbl.setProperty("cssClass", "char-name")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        desc_lbl = QLabel(desc_text)
        desc_lbl.setProperty("cssClass", "layout-desc")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.preview_widget = PanelPreviewWidget(preset_id)
        self.preview_widget.setFixedSize(96, 34)
        self.preview_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(icon_lbl)
        layout.addWidget(name_lbl)
        layout.addWidget(desc_lbl)
        layout.addWidget(self.preview_widget, 0, Qt.AlignmentFlag.AlignCenter)

    def set_active_state(self, is_active: bool):
        self.setProperty("active", "true" if is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def update_appearance(self, color, opacity):
        self.preview_widget.set_appearance(color, opacity)

class PanelRowWidget(QFrame):
    """Editor row for a single KDE panel — 3-line layout."""
    remove_requested    = pyqtSignal(object)
    move_up_requested   = pyqtSignal(object)
    move_down_requested = pyqtSignal(object)

    _POSITIONS  = ["bottom", "top", "left", "right"]
    _LAUNCHERS  = ["none", "kickoff", "kicker", "kickerdash"]
    _LENGTHS    = ["fill", "fit"]
    _ALIGNMENTS = ["left", "center", "right"]
    # Имена параметров строго по API KDE Plasma 6:
    _VISIBILITY_MODES = ["none", "autohide", "dodgewindows", "windowsgobelow"]

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        cfg = cfg or {}
        self.setObjectName("PanelRow")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet('''
            QFrame#PanelRow { background-color: rgb(26, 22, 40); border: 1px solid rgb(70, 60, 100); border-radius: 8px; }
            QLabel { color: rgb(160, 150, 195); font-size: 12px; border: none; }
            QComboBox { background-color: rgb(18, 14, 28); border: 1px solid rgb(58, 52, 88); border-radius: 5px; color: rgb(200, 190, 230); padding: 3px 6px; font-size: 12px; min-height: 22px; }
            QComboBox:hover { border: 1px solid rgb(110, 80, 160); }
            QComboBox::drop-down { background: rgb(40, 32, 65); border-left: 1px solid rgb(58, 52, 88); border-top-right-radius: 5px; border-bottom-right-radius: 5px; width: 18px; }
            QComboBox QAbstractItemView { background-color: rgb(25, 20, 40); color: rgb(200, 190, 230); border: 1px solid rgb(80, 65, 115); selection-background-color: rgb(100, 60, 160); selection-color: white; outline: none; }
            QSpinBox { background-color: rgb(18, 14, 28); border: 2px solid rgb(100, 80, 140); border-radius: 5px; color: rgb(200, 190, 230); padding: 5px 8px; font-size: 14px; min-height: 32px; }
            QSpinBox:hover { border-color: rgb(140, 100, 200); }
            QSpinBox::up-button, QSpinBox::down-button { background-color: rgb(42, 34, 68); border-left: 2px solid rgb(100, 80, 140); width: 22px; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: rgb(100, 60, 160); }
        ''')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(6)

        def sl():
            l = QLabel()
            l.setProperty("cssClass", "status-label")
            return l

        def spinbox(lo, hi, val, suffix=" px", w=72):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setSuffix(suffix)
            s.setValue(val)
            s.setFixedWidth(w)
            return s

        # Row 1: position / size / alignment / order
        r1 = QHBoxLayout()
        r1.setSpacing(8)

        self.cmb_pos = QComboBox()
        self.cmb_pos.addItems(["Bottom", "Top", "Left", "Right"])
        pos = cfg.get("position", "bottom")
        self.cmb_pos.setCurrentIndex(self._POSITIONS.index(pos) if pos in self._POSITIONS else 0)
        self._lbl_pos = sl()
        r1.addWidget(self._lbl_pos)
        r1.addWidget(self.cmb_pos)

        self.spn_h = spinbox(20, 200, cfg.get("height", 48))
        self._lbl_h = sl()
        r1.addWidget(self._lbl_h)
        r1.addWidget(self.spn_h)

        self.spn_w = spinbox(0, 9999, cfg.get("width", 0))
        self.spn_w.setSpecialValueText("Auto")
        self._lbl_w = sl()
        r1.addWidget(self._lbl_w)
        r1.addWidget(self.spn_w)

        self.spn_offset = spinbox(-9999, 9999, cfg.get("offset", 0))
        self._lbl_offset = sl()
        r1.addWidget(self._lbl_offset)
        r1.addWidget(self.spn_offset)

        self.cmb_align = QComboBox()
        self.cmb_align.addItems(["Left", "Center", "Right"])
        align = cfg.get("alignment", "center")
        self.cmb_align.setCurrentIndex(self._ALIGNMENTS.index(align) if align in self._ALIGNMENTS else 1)
        self._lbl_align = sl()
        r1.addWidget(self._lbl_align)
        r1.addWidget(self.cmb_align)

        r1.addStretch()
        icon_font = QFont("sans-serif", 16)
        icon_font.setBold(True)
        btn_up = QPushButton("↑")
        btn_up.setFont(icon_font)
        btn_up.setObjectName("PanelMoveBtn")
        btn_up.setFixedSize(22, 22)
        btn_up.clicked.connect(lambda: self.move_up_requested.emit(self))
        btn_dn = QPushButton("↓")
        btn_dn.setFont(icon_font)
        btn_dn.setObjectName("PanelMoveBtn")
        btn_dn.setFixedSize(22, 22)
        btn_dn.clicked.connect(lambda: self.move_down_requested.emit(self))
        btn_rm = QPushButton("✕")
        btn_rm.setFont(icon_font)
        btn_rm.setObjectName("PanelRemoveBtn")
        btn_rm.setFixedSize(22, 22)
        btn_rm.clicked.connect(lambda: self.remove_requested.emit(self))
        r1.addWidget(btn_up)
        r1.addWidget(btn_dn)
        r1.addWidget(btn_rm)
        outer.addLayout(r1)

        # Row 2: behaviour / launcher
        r2 = QHBoxLayout()
        r2.setSpacing(8)

        self.chk_float = SafeCheckBox()
        self.chk_float.setChecked(cfg.get("floating", False))
        r2.addWidget(self.chk_float)

        self.cmb_vis = QComboBox()
        # Временные элементы, будут заменены в retranslate
        self.cmb_vis.addItems(["Always visible", "Auto hide", "Dodge windows", "Windows go below"])

        vis = cfg.get("visibilityMode", "none")
        # Конвертация ошибочных названий из старых сохранений
        if vis == "windowsbelow": vis = "dodgewindows"
        if vis == "windowscover": vis = "windowsgobelow"
        if cfg.get("autohide", False) and vis == "none":
            vis = "autohide"

        self.cmb_vis.setCurrentIndex(self._VISIBILITY_MODES.index(vis) if vis in self._VISIBILITY_MODES else 0)
        self._lbl_vis = sl()
        r2.addWidget(self._lbl_vis)
        r2.addWidget(self.cmb_vis)

        self.cmb_len = QComboBox()
        self.cmb_len.addItems(["Fill width", "Fit content"])
        lm = cfg.get("lengthMode", "fill")
        self.cmb_len.setCurrentIndex(self._LENGTHS.index(lm) if lm in self._LENGTHS else 0)
        self._lbl_len = sl()
        r2.addWidget(self._lbl_len)
        r2.addWidget(self.cmb_len)

        self.cmb_launcher = QComboBox()
        self.cmb_launcher.addItems(["None", "Kickoff", "Kicker (classic)", "KickerDash (fullscreen)"])
        launcher = cfg.get("launcher", "none")
        self.cmb_launcher.setCurrentIndex(self._LAUNCHERS.index(launcher) if launcher in self._LAUNCHERS else 0)
        self._lbl_launcher = sl()
        r2.addWidget(self._lbl_launcher)
        r2.addWidget(self.cmb_launcher)

        r2.addStretch()
        outer.addLayout(r2)

        # Row 3: widgets
        r3 = QHBoxLayout()
        r3.setSpacing(10)
        self._lbl_widgets = sl()
        r3.addWidget(self._lbl_widgets)
        ww = cfg.get("widgets", [])
        self.chk_taskbar = SafeCheckBox()
        self.chk_taskbar.setChecked("taskbar" in ww)
        self.chk_systray = SafeCheckBox()
        self.chk_systray.setChecked("systray" in ww)
        self.chk_clock   = SafeCheckBox()
        self.chk_clock.setChecked("clock" in ww)
        self.chk_pager   = SafeCheckBox()
        self.chk_pager.setChecked("pager" in ww)
        self.chk_monitor = SafeCheckBox()
        self.chk_monitor.setChecked("monitor" in ww)
        for c in (self.chk_taskbar, self.chk_systray, self.chk_clock,
                  self.chk_pager, self.chk_monitor):
            r3.addWidget(c)
        r3.addStretch()
        outer.addLayout(r3)

        self.cmb_pos.setView(QListView())
        self.cmb_align.setView(QListView())
        self.cmb_len.setView(QListView())
        self.cmb_launcher.setView(QListView())
        self.cmb_vis.setView(QListView())

        self.retranslate(lambda k: k)

    def retranslate(self, t):
        self._lbl_pos.setText(t("ui.pr_position"))
        self._lbl_h.setText(t("ui.pr_height"))
        self._lbl_w.setText(t("ui.pr_width"))
        self._lbl_offset.setText(t("ui.pr_offset"))
        self._lbl_align.setText(t("ui.pr_align"))
        self._lbl_len.setText(t("ui.pr_length"))
        self._lbl_launcher.setText(t("ui.pr_launcher"))
        self._lbl_widgets.setText(t("ui.pr_widgets"))
        self.chk_float.setText(t("ui.pr_floating"))
        self.chk_taskbar.setText(t("ui.pr_taskbar"))
        self.chk_systray.setText(t("ui.pr_systray"))
        self.chk_clock.setText(t("ui.pr_clock"))
        self.chk_pager.setText(t("ui.pr_pager"))
        self.chk_monitor.setText(t("ui.pr_monitor"))

        self._lbl_vis.setText(t("ui.pr_visibility"))
        current_vis_idx = self.cmb_vis.currentIndex()
        self.cmb_vis.blockSignals(True)
        self.cmb_vis.clear()
        self.cmb_vis.addItems([
            t("ui.vis_always"),
            t("ui.vis_auto"),
            t("ui.vis_dodge"),
            t("ui.vis_below")
        ])
        self.cmb_vis.setCurrentIndex(current_vis_idx)
        self.cmb_vis.blockSignals(False)

    def get_config(self):
        widgets = []
        if self.chk_taskbar.isChecked(): widgets.append("taskbar")
        if self.chk_systray.isChecked(): widgets.append("systray")
        if self.chk_clock.isChecked():   widgets.append("clock")
        if self.chk_pager.isChecked():   widgets.append("pager")
        if self.chk_monitor.isChecked(): widgets.append("monitor")
        return {
            "position":   self._POSITIONS[self.cmb_pos.currentIndex()],
            "height":     self.spn_h.value(),
            "width":      self.spn_w.value(),
            "offset":     self.spn_offset.value(),
            "alignment":  self._ALIGNMENTS[self.cmb_align.currentIndex()],
            "floating":   self.chk_float.isChecked(),
            "visibilityMode": self._VISIBILITY_MODES[self.cmb_vis.currentIndex()],
            "lengthMode": self._LENGTHS[self.cmb_len.currentIndex()],
            "launcher":   self._LAUNCHERS[self.cmb_launcher.currentIndex()],
            "widgets":    widgets,
        }
