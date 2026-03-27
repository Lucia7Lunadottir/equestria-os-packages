from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QSlider, QStackedWidget,
                             QLineEdit, QFrame)
from PyQt6.QtCore import Qt
from widgets import SafeCheckBox

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

        self.fld_ed_id = QLineEdit()
        self.fld_ed_id.setObjectName("EditorField")
        self.fld_ed_id.setStyleSheet("QLineEdit { background-color: rgb(15, 12, 25); border: 2px solid rgb(90, 80, 130); border-radius: 6px; color: rgb(220, 200, 255); padding: 4px 7px; font-size: 13px; } QLineEdit:focus { border: 2px solid rgb(140, 90, 200); } QLineEdit[readOnly=\"true\"] { color: rgb(120, 110, 150); border: 2px solid rgb(60, 55, 90); }")
        self.fld_ed_id.setFixedWidth(220)
        self.row_ed_id, self.lbl_ed_id_row = add_row("Preset ID:", self.fld_ed_id)

        self.fld_ed_name = QLineEdit()
        self.fld_ed_name.setObjectName("EditorField")
        self.fld_ed_name.setStyleSheet(self.fld_ed_id.styleSheet())
        self.fld_ed_name.setFixedWidth(220)
        _, self.lbl_ed_name_row = add_row("Display Name:", self.fld_ed_name)

        self.fld_ed_desc = QLineEdit()
        self.fld_ed_desc.setObjectName("EditorField")
        self.fld_ed_desc.setStyleSheet(self.fld_ed_id.styleSheet())
        self.fld_ed_desc.setFixedWidth(320)
        _, self.lbl_ed_desc_row = add_row("Description:", self.fld_ed_desc)

        icon_w = QWidget()
        icon_lo = QHBoxLayout(icon_w)
        icon_lo.setContentsMargins(0, 0, 0, 0)
        icon_lo.setSpacing(6)
        self.fld_ed_icon = QLineEdit()
        self.fld_ed_icon.setObjectName("EditorField")
        self.fld_ed_icon.setStyleSheet(self.fld_ed_id.styleSheet())
        self.fld_ed_icon.setFixedWidth(260)
        self.btn_ed_icon = QPushButton("…")
        self.btn_ed_icon.setObjectName("BrowseBtn")
        self.btn_ed_icon.setFixedSize(28, 24)
        icon_lo.addWidget(self.fld_ed_icon)
        icon_lo.addWidget(self.btn_ed_icon)
        _, self.lbl_ed_icon_row = add_row("Icon:", icon_w)

        self.btn_ed_color = QPushButton()
        self.btn_ed_color.setObjectName("ColorSwatchBtn")
        self.btn_ed_color.setFixedSize(40, 24)
        _, self.lbl_ed_color_row = add_row("Panel Color:", self.btn_ed_color)

        panels_hdr = QWidget()
        panels_hdr_lo = QHBoxLayout(panels_hdr)
        panels_hdr_lo.setContentsMargins(0, 0, 0, 0)
        panels_hdr_lo.setSpacing(8)
        self.lbl_ed_panels = QLabel("Panels:")
        self.lbl_ed_panels.setProperty("cssClass", "status-label")
        self.lbl_ed_panels.setFixedWidth(150)
        self.btn_ed_add_panel = QPushButton("+ Add Panel")
        self.btn_ed_add_panel.setProperty("cssClass", "action-btn")
        self.btn_ed_add_panel.setStyleSheet("QPushButton { background-color: rgb(60, 45, 90); border: 1px solid rgb(90, 80, 130); padding: 5px 12px; font-size: 11px; } QPushButton:hover { background-color: rgb(80, 65, 120); border: 1px solid rgb(110, 100, 150); }")
        panels_hdr_lo.addWidget(self.lbl_ed_panels)
        panels_hdr_lo.addWidget(self.btn_ed_add_panel)
        panels_hdr_lo.addStretch()
        ed_form.addWidget(panels_hdr)

        self.ed_panels_container = QWidget()
        self.ed_panels_layout = QVBoxLayout(self.ed_panels_container)
        self.ed_panels_layout.setSpacing(6)
        self.ed_panels_layout.setContentsMargins(0, 0, 0, 0)
        ed_form.addWidget(self.ed_panels_container)

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

        self.chk_ed_hide_icons = SafeCheckBox()
        _, self.lbl_ed_hide_icons_row = add_row("Desktop Icons:", self.chk_ed_hide_icons)

        self.btn_ed_theme = QPushButton("🌙 Dark text")
        self.btn_ed_theme.setProperty("cssClass", "action-btn")
        _, self.lbl_ed_theme_row = add_row("Text Color:", self.btn_ed_theme)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("EditorDivider")
        ed_form.addWidget(line)

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

        self.btn_ed_delete = QPushButton("Delete")
        self.btn_ed_delete.setProperty("cssClass", "action-btn")
        self.btn_ed_delete.setStyleSheet("""
            QPushButton { background-color: rgb(130, 40, 60); border: 1px solid rgb(170, 60, 80); }
            QPushButton:hover { background-color: rgb(160, 50, 75); }
        """)
        ed_status_lo.addWidget(self.btn_ed_delete)

        ed_status_lo.addStretch()

        self.btn_ed_cancel = QPushButton("Cancel")
        self.btn_ed_cancel.setProperty("cssClass", "action-btn")
        ed_status_lo.addWidget(self.btn_ed_cancel)

        self.btn_ed_save = QPushButton("Save")
        self.btn_ed_save.setProperty("cssClass", "action-btn")
        ed_status_lo.addWidget(self.btn_ed_save)

        ed_layout.addWidget(ed_status)
        self.stacked_widget.addWidget(self.page_editor)
