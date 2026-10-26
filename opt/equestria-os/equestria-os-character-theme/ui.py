from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QStackedWidget, QLineEdit, QGridLayout)
from PyQt6.QtCore import Qt

# Вшитые стили с увеличенными размерами шрифтов (font-size)
APP_STYLE = """
/* Цвета — роли общей темы (equestria_kit): приложение само окрашивается
   в цвета выбранного персонажа. */
QWidget#root {
    background-color: @base@;
}
QLabel[cssClass="title"] {
    font-size: 28px;
    color: @accent@;
    font-weight: bold;
    margin-bottom: 8px;
}
QLabel[cssClass="subtitle"] {
    font-size: 16px;
    color: @subtext@;
    margin-bottom: 24px;
}
/* Language Dropdown.
   No ::drop-down/::down-arrow rules here on purpose: declaring them makes
   Qt stop drawing the native arrow. */
QComboBox#LangCombo {
    background-color: @surface0@;
    color: @text@;
    border: 1px solid @surface1@;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 14px;
    min-width: 52px;
}
QComboBox#LangCombo:hover {
    border: 1px solid @accent@;
}
QComboBox QAbstractItemView {
    background-color: @surface0@;
    color: @text@;
    selection-background-color: @accent@;
    selection-color: @on_accent@;
    border: 1px solid @surface1@;
    outline: none;
}
/* Status Bar */
QWidget[cssClass="status-bar"] {
    background-color: @mantle@;
    border-radius: 12px;
}
QLabel[cssClass="status-label"] {
    font-size: 16px;
    color: @subtext@;
    padding-left: 10px;
}
QPushButton[cssClass="open-terminal-btn"] {
    background-color: @accent@;
    border: 1px solid @accent@;
    border-radius: 8px;
    color: @on_accent@;
    padding: 8px 20px;
    font-size: 14px;
}
QPushButton[cssClass="open-terminal-btn"]:hover {
    background-color: @accent_hover@;
}
/* Нижняя панель выбора персонажа — компактные кнопки, чтобы подписи не обрезались */
QWidget[cssClass="status-bar"] QPushButton[cssClass="open-terminal-btn"] {
    padding: 5px 12px;
    font-size: 13px;
    border-radius: 7px;
}
QWidget[cssClass="status-bar"] QLabel[cssClass="status-label"] {
    font-size: 14px;
}
/* Editor Fields */
QWidget[cssClass="editor-scroll"] {
    background-color: @mantle@;
    border-radius: 12px;
}
QLabel[cssClass="editor-label"] {
    min-width: 150px;
    font-size: 15px;
    color: @subtext@;
}
QLineEdit[cssClass="editor-input"] {
    background-color: @crust@;
    border: 1px solid @surface0@;
    border-radius: 4px;
    color: @text@;
    padding: 6px;
    font-size: 14px;
}
QLabel[cssClass="char-name"] {
    font-size: 15px;
    font-weight: bold;
    color: @text@;
    margin-top: 10px;
}
/* Варианты кнопок вместо цветов в коде: setProperty("variant", ...) */
QPushButton[variant="danger"] { background-color: @red@; border-color: @red@; color: @on_red@; }
QPushButton[variant="danger"]:hover { background-color: @red%85@; }
QPushButton[variant="success"] { background-color: @green@; border-color: @green@; color: @on_green@; }
QPushButton[variant="success"]:hover { background-color: @green%85@; }
QPushButton[variant="neutral"] { background-color: @surface2@; border-color: @surface2@; color: @text@; }
QPushButton[variant="neutral"]:hover { background-color: @surface1@; }
/* ✎ в углу карточки персонажа */
QPushButton#CardEditBtn {
    background-color: @crust/180@; border: 1px solid @surface1@; border-radius: 13px;
    color: @text@; font-size: 13px; padding: 0;
}
QPushButton#CardEditBtn:hover { background-color: @accent@; border-color: @accent@; color: @on_accent@; }
"""

class Ui_MainWindow:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1100, 800) # Чуть увеличил окно по умолчанию

        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName("root")
        MainWindow.setCentralWidget(self.centralwidget)

        self.main_layout = QVBoxLayout(self.centralwidget)
        self.main_layout.setContentsMargins(32, 32, 32, 32)

        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        # --- MAIN VIEW ---
        self.page_main = QWidget()
        self.page_main_layout = QVBoxLayout(self.page_main)
        self.page_main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lbl_title = QLabel("✨ Equestria OS Character Theme")
        self.lbl_title.setProperty("cssClass", "title")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.page_main_layout.addWidget(self.lbl_title)

        self.lang_container = QWidget()
        self.lang_layout = QHBoxLayout(self.lang_container)
        self.lang_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.lang_layout.setContentsMargins(0, 0, 0, 24)
        self.page_main_layout.addWidget(self.lang_container)

        self.lbl_subtitle = QLabel("Select character")
        self.lbl_subtitle.setProperty("cssClass", "subtitle")
        self.page_main_layout.addWidget(self.lbl_subtitle)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(24) # Увеличили отступы между персонажами
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.scroll_area.setWidget(self.grid_container)
        self.page_main_layout.addWidget(self.scroll_area, 1)

        self.status_bar = QWidget()
        self.status_bar.setProperty("cssClass", "status-bar")
        self.status_layout = QHBoxLayout(self.status_bar)

        self.lbl_status = QLabel("Active: —")
        self.lbl_status.setProperty("cssClass", "status-label")
        self.status_layout.addWidget(self.lbl_status)
        self.status_layout.addStretch()

        self.btn_theme_toggle = QPushButton("☀️ Light / 🌙 Dark")

        self.btn_restore = QPushButton("Restore Defaults")
        self.btn_restore.setProperty("variant", "danger")
        self.btn_open_folder = QPushButton("Open Files")
        # «Создать» — компактная кнопка «＋» (подпись живёт в тултипе);
        # «Изменить» переехало на карточки (✎), «Дублировать» — в редактор
        self.btn_create = QPushButton("+")
        self.btn_create.setFixedWidth(36)
        # обычный «+» + крупный кегль: полноширинный юникод-плюс «＋»
        # в системном шрифте рисуется вертикальной палкой
        self.btn_create.setStyleSheet("font-size: 17px; font-weight: bold; padding: 1px 0px;")
        self.btn_import = QPushButton("📥")
        self.btn_import.setFixedWidth(36)
        # без override паддинга общий стиль (padding 8px 20px) при ширине 44px
        # обрезает глиф до узкой полоски
        self.btn_import.setStyleSheet("font-size: 13px; padding: 3px 0px;")
        self.btn_terminal = QPushButton("Open Terminal")

        for btn in [self.btn_theme_toggle, self.btn_restore, self.btn_open_folder, self.btn_create, self.btn_import, self.btn_terminal]:
            btn.setProperty("cssClass", "open-terminal-btn")
            self.status_layout.addWidget(btn)



        self.page_main_layout.addWidget(self.status_bar)
        self.stacked_widget.addWidget(self.page_main)

        # --- EDITOR VIEW ---
        self.page_editor = QWidget()
        self.page_editor_layout = QVBoxLayout(self.page_editor)

        self.lbl_ed_title = QLabel("Theme Editor")
        self.lbl_ed_title.setProperty("cssClass", "title")
        self.page_editor_layout.addWidget(self.lbl_ed_title)

        self.ed_scroll = QScrollArea()
        self.ed_scroll.setWidgetResizable(True)
        self.ed_scroll.setProperty("cssClass", "editor-scroll")
        self.ed_container = QWidget()
        self.ed_form_layout = QVBoxLayout(self.ed_container)

        def add_field(label_text):
            row = QWidget()
            lo = QHBoxLayout(row)
            lo.setContentsMargins(0, 0, 0, 12)
            lbl = QLabel(label_text)
            lbl.setProperty("cssClass", "editor-label")
            inp = QLineEdit()
            inp.setProperty("cssClass", "editor-input")
            lo.addWidget(lbl)
            lo.addWidget(inp)
            self.ed_form_layout.addWidget(row)
            return lbl, inp

        self.lbl_fld_id, self.fld_id = add_field("Character ID")
        self.lbl_fld_name, self.fld_name = add_field("Display Name")

        def add_file_picker(label_text):
            row = QWidget()
            lo = QHBoxLayout(row)
            lo.setContentsMargins(0,0,0,12)
            lbl = QLabel(label_text)
            lbl.setProperty("cssClass", "editor-label")
            inp = QLineEdit()
            inp.setProperty("cssClass", "editor-input")
            btn = QPushButton("...")
            btn.setProperty("cssClass", "open-terminal-btn")
            btn.setFixedWidth(40)
            lo.addWidget(lbl)
            lo.addWidget(inp)
            lo.addWidget(btn)
            self.ed_form_layout.addWidget(row)
            return lbl, inp, btn

        self.lbl_fld_wallpaper, self.fld_wallpaper, self.btn_browse_wall = add_file_picker("Wallpaper Path")
        self.lbl_fld_icon, self.fld_icon, self.btn_browse_icon = add_file_picker("Cutiemark Path")

        self.lbl_ui_colors = QLabel("UI Colors (Hex)")
        self.lbl_ui_colors.setProperty("cssClass", "subtitle")
        self.ed_form_layout.addWidget(self.lbl_ui_colors)

        self.ui_colors_container = QWidget()
        self.ui_colors_layout = QGridLayout(self.ui_colors_container)
        self.ui_colors_layout.setHorizontalSpacing(16)
        self.ed_form_layout.addWidget(self.ui_colors_container)

        self.lbl_konsole_colors = QLabel("Konsole Colors (RGB)")
        self.lbl_konsole_colors.setProperty("cssClass", "subtitle")
        self.ed_form_layout.addWidget(self.lbl_konsole_colors)

        self.konsole_colors_container = QWidget()
        self.konsole_colors_layout = QGridLayout(self.konsole_colors_container)
        self.konsole_colors_layout.setHorizontalSpacing(16)
        self.konsole_colors_layout.setVerticalSpacing(8)
        self.ed_form_layout.addWidget(self.konsole_colors_container)

        self.ed_scroll.setWidget(self.ed_container)
        self.page_editor_layout.addWidget(self.ed_scroll)

        self.ed_status_bar = QWidget()
        self.ed_status_bar.setProperty("cssClass", "status-bar")
        self.ed_status_layout = QHBoxLayout(self.ed_status_bar)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setProperty("cssClass", "open-terminal-btn")
        self.btn_delete.setProperty("variant", "danger")
        self.ed_status_layout.addWidget(self.btn_delete)

        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_duplicate.setProperty("cssClass", "open-terminal-btn")
        self.ed_status_layout.addWidget(self.btn_duplicate)

        self.btn_export = QPushButton("Export")
        self.btn_export.setProperty("cssClass", "open-terminal-btn")
        self.ed_status_layout.addWidget(self.btn_export)

        self.ed_status_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setProperty("cssClass", "open-terminal-btn")
        self.btn_cancel.setProperty("variant", "neutral")
        self.btn_save = QPushButton("Save")
        self.btn_save.setProperty("cssClass", "open-terminal-btn")
        self.btn_save.setProperty("variant", "success")

        self.ed_status_layout.addWidget(self.btn_cancel)
        self.ed_status_layout.addWidget(self.btn_save)

        self.page_editor_layout.addWidget(self.ed_status_bar)
        self.stacked_widget.addWidget(self.page_editor)
