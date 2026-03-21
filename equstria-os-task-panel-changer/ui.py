import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QSlider, QStackedWidget,
                             QLineEdit, QSpinBox, QFrame)
from PyQt6.QtGui import QPainter, QColor, QPixmap
from PyQt6.QtCore import Qt

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


class Ui_MainWindow:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(960, 550)
        MainWindow.setMinimumSize(640, 440)

        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName("root")
        MainWindow.setCentralWidget(self.centralwidget)

        root_layout = QVBoxLayout(self.centralwidget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.stacked_widget = QStackedWidget()
        root_layout.addWidget(self.stacked_widget)

        self._setup_main_page()
        self._setup_editor_page()

    # ─────────────────────── PAGE 0: MAIN ───────────────────────

    def _setup_main_page(self):
        self.page_main = QWidget()
        self.main_layout = QVBoxLayout(self.page_main)
        self.main_layout.setContentsMargins(28, 28, 28, 20)
        self.main_layout.setSpacing(0)

        # Title row
        title_row = QWidget()
        title_row_lo = QHBoxLayout(title_row)
        title_row_lo.setContentsMargins(0, 0, 0, 4)

        self.lbl_title = QLabel("Equestria OS Task Panel Styles")
        self.lbl_title.setProperty("cssClass", "title")
        title_row_lo.addWidget(self.lbl_title)
        title_row_lo.addStretch()

        self.lang_container = QWidget()
        self.lang_layout = QHBoxLayout(self.lang_container)
        self.lang_layout.setContentsMargins(0, 0, 0, 0)
        self.lang_layout.setSpacing(4)
        self.lang_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row_lo.addWidget(self.lang_container)

        self.main_layout.addWidget(title_row)

        # Subtitle
        self.lbl_subtitle = QLabel("Select a layout preset")
        self.lbl_subtitle.setProperty("cssClass", "subtitle")
        self.main_layout.addWidget(self.lbl_subtitle)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.grid_container = QWidget()
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setContentsMargins(0, 8, 0, 8)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.grid_container)
        self.main_layout.addWidget(self.scroll_area, 1)

        # Status bar
        self.status_bar = QWidget()
        self.status_bar.setProperty("cssClass", "status-bar")
        self.status_layout = QHBoxLayout(self.status_bar)
        self.status_layout.setContentsMargins(14, 8, 14, 8)
        self.status_layout.setSpacing(8)

        self.lbl_status = QLabel("Active: —")
        self.lbl_status.setProperty("cssClass", "status-label")
        self.lbl_status.setMaximumWidth(200)
        self.status_layout.addWidget(self.lbl_status)
        self.status_layout.addStretch()

        self.lbl_panel_color = QLabel("Panel color:")
        self.lbl_panel_color.setProperty("cssClass", "status-label")
        self.status_layout.addWidget(self.lbl_panel_color)

        self.btn_color_swatch = QPushButton()
        self.btn_color_swatch.setObjectName("ColorSwatchBtn")
        self.status_layout.addWidget(self.btn_color_swatch)

        self.btn_panel_theme = QPushButton("🌙")
        self.btn_panel_theme.setProperty("cssClass", "action-btn")
        self.status_layout.addWidget(self.btn_panel_theme)

        self.lbl_opacity_label = QLabel("Opacity:")
        self.lbl_opacity_label.setProperty("cssClass", "status-label")
        self.status_layout.addWidget(self.lbl_opacity_label)

        self.sld_opacity = QSlider(Qt.Orientation.Horizontal)
        self.sld_opacity.setRange(0, 100)
        self.sld_opacity.setValue(90)
        self.sld_opacity.setFixedWidth(100)
        self.status_layout.addWidget(self.sld_opacity)

        self.lbl_opacity_val = QLabel("90%")
        self.lbl_opacity_val.setProperty("cssClass", "status-label")
        self.lbl_opacity_val.setFixedWidth(38)
        self.status_layout.addWidget(self.lbl_opacity_val)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setProperty("cssClass", "action-btn")
        self.btn_edit.setEnabled(False)
        self.status_layout.addWidget(self.btn_edit)

        self.btn_new_preset = QPushButton("New")
        self.btn_new_preset.setProperty("cssClass", "action-btn")
        self.status_layout.addWidget(self.btn_new_preset)

        self.btn_restore_all = QPushButton("Restore All")
        self.btn_restore_all.setProperty("cssClass", "action-btn")
        self.status_layout.addWidget(self.btn_restore_all)

        self.main_layout.addWidget(self.status_bar)
        self.stacked_widget.addWidget(self.page_main)

    # ─────────────────────── PAGE 1: EDITOR ───────────────────────

    def _setup_editor_page(self):
        self.page_editor = QWidget()
        ed_layout = QVBoxLayout(self.page_editor)
        ed_layout.setContentsMargins(28, 28, 28, 20)
        ed_layout.setSpacing(16)

        self.lbl_ed_title = QLabel("Edit Preset")
        self.lbl_ed_title.setProperty("cssClass", "title")
        ed_layout.addWidget(self.lbl_ed_title)

        ed_scroll = QScrollArea()
        ed_scroll.setWidgetResizable(True)
        ed_scroll.setStyleSheet("background: transparent; border: none;")

        ed_container = QWidget()
        ed_form = QVBoxLayout(ed_container)
        ed_form.setSpacing(14)
        ed_form.setContentsMargins(0, 0, 0, 0)
        ed_form.setAlignment(Qt.AlignmentFlag.AlignTop)

        def add_row(label_text, widget):
            row = QWidget()
            lo = QHBoxLayout(row)
            lo.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label_text)
            lbl.setProperty("cssClass", "status-label")
            lbl.setFixedWidth(150)
            lo.addWidget(lbl)
            lo.addWidget(widget)
            lo.addStretch()
            ed_form.addWidget(row)
            return row, lbl

        # Preset ID
        self.fld_ed_id = QLineEdit()
        self.fld_ed_id.setObjectName("EditorField")
        self.fld_ed_id.setFixedWidth(220)
        self.row_ed_id, self.lbl_ed_id_row = add_row("Preset ID:", self.fld_ed_id)

        # Display name
        self.fld_ed_name = QLineEdit()
        self.fld_ed_name.setObjectName("EditorField")
        self.fld_ed_name.setFixedWidth(220)
        _, self.lbl_ed_name_row = add_row("Display Name:", self.fld_ed_name)

        # Icon path + browse button
        icon_w = QWidget()
        icon_lo = QHBoxLayout(icon_w)
        icon_lo.setContentsMargins(0, 0, 0, 0)
        icon_lo.setSpacing(6)
        self.fld_ed_icon = QLineEdit()
        self.fld_ed_icon.setObjectName("EditorField")
        self.fld_ed_icon.setFixedWidth(260)
        self.btn_ed_icon = QPushButton("…")
        self.btn_ed_icon.setObjectName("BrowseBtn")
        self.btn_ed_icon.setFixedSize(28, 24)
        icon_lo.addWidget(self.fld_ed_icon)
        icon_lo.addWidget(self.btn_ed_icon)
        _, self.lbl_ed_icon_row = add_row("Icon:", icon_w)

        # Panel color swatch
        self.btn_ed_color = QPushButton()
        self.btn_ed_color.setObjectName("ColorSwatchBtn")
        self.btn_ed_color.setFixedSize(40, 24)
        _, self.lbl_ed_color_row = add_row("Panel Color:", self.btn_ed_color)

        # Panel height spinbox
        self.spn_ed_height = QSpinBox()
        self.spn_ed_height.setObjectName("EditorSpinBox")
        self.spn_ed_height.setRange(20, 120)
        self.spn_ed_height.setSuffix(" px")
        self.spn_ed_height.setFixedWidth(90)
        _, self.lbl_ed_height_row = add_row("Panel Height:", self.spn_ed_height)

        # Opacity slider
        opacity_w = QWidget()
        opacity_lo = QHBoxLayout(opacity_w)
        opacity_lo.setContentsMargins(0, 0, 0, 0)
        opacity_lo.setSpacing(8)
        self.sld_ed_opacity = QSlider(Qt.Orientation.Horizontal)
        self.sld_ed_opacity.setRange(0, 100)
        self.sld_ed_opacity.setFixedWidth(180)
        self.lbl_ed_opacity_val = QLabel("90%")
        self.lbl_ed_opacity_val.setProperty("cssClass", "status-label")
        self.lbl_ed_opacity_val.setFixedWidth(40)
        opacity_lo.addWidget(self.sld_ed_opacity)
        opacity_lo.addWidget(self.lbl_ed_opacity_val)
        _, self.lbl_ed_opacity_row = add_row("Opacity:", opacity_w)

        # Dark/light text toggle
        self.btn_ed_theme = QPushButton("🌙 Dark text")
        self.btn_ed_theme.setProperty("cssClass", "action-btn")
        _, self.lbl_ed_theme_row = add_row("Text Color:", self.btn_ed_theme)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("EditorDivider")
        ed_form.addWidget(line)

        # Panel layout capture section
        layout_w = QWidget()
        layout_lo = QHBoxLayout(layout_w)
        layout_lo.setContentsMargins(0, 0, 0, 0)
        layout_lo.setSpacing(10)
        self.btn_ed_capture = QPushButton("📸 Capture current panels")
        self.btn_ed_capture.setProperty("cssClass", "action-btn")
        self.lbl_ed_capture_status = QLabel("Not captured")
        self.lbl_ed_capture_status.setProperty("cssClass", "capture-status")
        layout_lo.addWidget(self.btn_ed_capture)
        layout_lo.addWidget(self.lbl_ed_capture_status)
        layout_lo.addStretch()
        _, self.lbl_ed_layout_row = add_row("Panel Layout:", layout_w)

        ed_scroll.setWidget(ed_container)
        ed_layout.addWidget(ed_scroll, 1)

        # Editor bottom bar
        ed_status = QWidget()
        ed_status.setProperty("cssClass", "status-bar")
        ed_status_lo = QHBoxLayout(ed_status)
        ed_status_lo.setContentsMargins(14, 8, 14, 8)
        ed_status_lo.setSpacing(8)

        self.btn_ed_restore = QPushButton("Restore Default")
        self.btn_ed_restore.setProperty("cssClass", "action-btn")
        ed_status_lo.addWidget(self.btn_ed_restore)
        ed_status_lo.addStretch()

        self.btn_ed_cancel = QPushButton("Cancel")
        self.btn_ed_cancel.setProperty("cssClass", "action-btn")
        ed_status_lo.addWidget(self.btn_ed_cancel)

        self.btn_ed_save = QPushButton("Save")
        self.btn_ed_save.setProperty("cssClass", "action-btn")
        ed_status_lo.addWidget(self.btn_ed_save)

        ed_layout.addWidget(ed_status)
        self.stacked_widget.addWidget(self.page_editor)
