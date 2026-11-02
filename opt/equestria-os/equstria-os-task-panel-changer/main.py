"""Equestria OS — стили панели задач.

Окно только связывает интерфейс с модулями:
  presets.py         пресеты и снятые раскладки
  preset_applier.py  применение: стиль → вид рабочего стола → раскладка
  panel_style.py     цвет/прозрачность панели (дневной и ночной Plasma-стиль)
  panel_layout.py    раскладка панелей (формат KDE) и скрипт Plasma
  plasma.py          D-Bus plasmashell, kreadconfig6/kwriteconfig6, день/ночь
"""
import json
import os
import sys
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import (QApplication, QColorDialog, QComboBox, QFileDialog, QHBoxLayout,
                             QMainWindow, QMessageBox, QWidget)

from localization import Localizer
from panel_layout import PanelLayout
from panel_style import LegacyThemeCleanup
from plasma import DayNight
from preset_applier import PresetApplier
from presets import DEFAULT_DAY, DEFAULT_NIGHT, USER_DIR, Preset, PresetStore, SYSTEM_DIR
from ui import Ui_MainWindow
from widgets import PresetCard

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, os.path.join(os.path.dirname(SYSTEM_DIR), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import font_families

APPEARANCE_FILE = os.path.join(USER_DIR, "appearance.json")
MAX_COLS = 4


class EditorState:
    """Значения редактора, пока пресет не сохранён."""

    def __init__(self, preset: Preset | None):
        self.color_day = preset.color_day if preset else DEFAULT_DAY
        self.color_night = preset.color_night if preset else DEFAULT_NIGHT
        self.opacity = preset.opacity if preset else 90
        self.captured = preset.layout_captured if preset else ""


class TaskPanelApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Equestria OS Task Panel Styles")

        self.loc = Localizer(os.path.join(SYSTEM_DIR, "localization.csv"))
        self.store = PresetStore()
        self.store.load()
        self.applier = PresetApplier(self)
        self.applier.finished.connect(self._on_applied)

        LegacyThemeCleanup().run()  # следы старых версий, ломавшие экран блокировки
        self.active_id = self._load_active()
        self.editing_id: str | None = None
        self.editor: EditorState | None = None
        self.cards: dict[str, PresetCard] = {}
        self._status_extra = ""

        self._build_language_selector()
        self._build_cards()
        self._bind_events()
        self._retranslate()

    # ── активный пресет ──
    def _load_active(self):
        try:
            with open(APPEARANCE_FILE, encoding="utf-8") as f:
                pid = json.load(f).get("active_preset")
        except (OSError, ValueError):
            pid = None
        return pid if pid and self.store.get(pid) else None

    def _save_active(self):
        os.makedirs(USER_DIR, exist_ok=True)
        with open(APPEARANCE_FILE, "w", encoding="utf-8") as f:
            json.dump({"active_preset": self.active_id}, f)

    # ── тексты пресета ──
    def _name(self, p: Preset) -> str:
        return p.name or p.id

    def _desc(self, p: Preset) -> str:
        return self.loc.t(p.desc_key) if p.desc_key and self.loc.has(p.desc_key) else (p.desc or "")

    @staticmethod
    def _icon_path(p: Preset) -> str:
        if not p.icon:
            return ""
        return p.icon if os.path.isabs(p.icon) else os.path.join(SYSTEM_DIR, p.icon)

    @staticmethod
    def _shown_color(p: Preset) -> str:
        return p.color_night if DayNight.is_dark_now() else p.color_day

    # ── построение интерфейса ──
    def _build_language_selector(self):
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        for code in self.loc.languages:
            self.lang_combo.addItem(code.upper(), code)
        idx = self.lang_combo.findData(self.loc.lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.activated.connect(lambda i: self.set_language(self.lang_combo.itemData(i)))
        self.ui.lang_layout.addWidget(self.lang_combo)

    def _build_cards(self):
        while self.ui.grid_layout.count():
            item = self.ui.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards.clear()
        cards = []
        for p in self.store.presets:
            layout = self.store.layout_for(p)
            card = PresetCard(p.id, self._name(p), self._desc(p), self._icon_path(p),
                              panels=layout.panels if layout else [])
            card.update_appearance(self._shown_color(p), p.opacity)
            card.set_active_state(p.id == self.active_id)
            card.clicked.connect(lambda _checked, pid=p.id: self.select_preset(pid))
            self.cards[p.id] = card
            cards.append(card)
        for start in range(0, len(cards), MAX_COLS):
            row = QWidget()
            row_lo = QHBoxLayout(row)
            row_lo.setContentsMargins(0, 0, 0, 0)
            row_lo.setSpacing(14)
            row_lo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            for card in cards[start:start + MAX_COLS]:
                row_lo.addWidget(card)
            self.ui.grid_layout.addWidget(row)

    def _bind_events(self):
        ui = self.ui
        ui.btn_edit.clicked.connect(lambda: self.open_editor(self.active_id))
        ui.btn_new_preset.clicked.connect(lambda: self.open_editor(None))
        ui.btn_restore_all.clicked.connect(self.restore_all)
        ui.btn_ed_color_dark.clicked.connect(lambda: self.pick_color(night=True))
        ui.btn_ed_color_light.clicked.connect(lambda: self.pick_color(night=False))
        ui.sld_ed_opacity.valueChanged.connect(self.on_opacity_changed)
        ui.btn_ed_icon.clicked.connect(self.pick_icon)
        ui.btn_ed_open_kde.clicked.connect(self.applier.shell.set_edit_mode)
        ui.btn_ed_capture.clicked.connect(self.capture_panels)
        ui.btn_ed_restore.clicked.connect(self.restore_default)
        ui.btn_ed_delete.clicked.connect(self.delete_preset)
        ui.btn_ed_cancel.clicked.connect(self.cancel_editor)
        ui.btn_ed_save.clicked.connect(self.save_editor)

    def set_language(self, code):
        self.loc.lang = code
        self._build_cards()
        self._retranslate()

    def _retranslate(self):
        t, ui = self.loc.t, self.ui
        ui.lbl_title.setText(t("ui.title"))
        ui.lbl_subtitle.setText(t("ui.subtitle"))
        ui.btn_edit.setText(t("ui.btn_edit"))
        ui.btn_new_preset.setText(t("ui.btn_new"))
        ui.btn_restore_all.setText(t("ui.btn_restore_all"))
        ui.lbl_ed_id_row.setText(t("ui.ed_preset_id"))
        ui.lbl_ed_name_row.setText(t("ui.ed_name_label"))
        ui.lbl_ed_desc_row.setText(t("ui.ed_desc_label"))
        ui.lbl_ed_icon_row.setText(t("ui.ed_icon_label"))
        ui.lbl_ed_color_row.setText(t("ui.ed_color_label"))
        ui.lbl_ed_opacity_row.setText(t("ui.ed_opacity_label"))
        ui.lbl_ed_layout_row.setText(t("ui.ed_layout_label"))
        ui.lbl_ed_hide_icons_row.setText(t("ui.ed_hide_icons_label"))
        ui.chk_ed_hide_icons.setText(t("ui.hide_icons"))
        ui.lbl_ed_kde_row.setText(t("ui.ed_kde_label"))
        ui.btn_ed_open_kde.setText(t("ui.ed_open_kde_btn"))
        ui.btn_ed_color_dark.setToolTip(t("ui.color_night"))
        ui.btn_ed_color_light.setToolTip(t("ui.color_day"))
        ui.help_ed_color.set_help_text(t("help.ed_color"))
        ui.help_ed_hide_icons.set_help_text(t("help.ed_hide_icons"))
        ui.help_ed_kde.set_help_text(t("help.ed_kde"))
        ui.help_ed_layout.set_help_text(t("help.ed_layout"))
        ui.btn_ed_capture.setText(t("ui.ed_capture_btn"))
        ui.btn_ed_restore.setText(t("ui.btn_restore_default"))
        ui.btn_ed_delete.setText(t("ui.btn_delete"))
        ui.btn_ed_cancel.setText(t("ui.btn_cancel"))
        ui.btn_ed_save.setText(t("ui.btn_save"))
        self._refresh_status()
        self._refresh_capture_label()

    def _refresh_status(self):
        preset = self.store.get(self.active_id) if self.active_id else None
        text = self.loc.t("ui.active_preset", self._name(preset)) if preset else self.loc.t("ui.active_none")
        self.ui.lbl_status.setText(text + self._status_extra)
        self.ui.btn_edit.setEnabled(preset is not None)

    def _refresh_capture_label(self):
        captured = self.editor.captured if self.editor else ""
        self.ui.lbl_ed_capture_status.setText(
            self.loc.t("ui.ed_capture_done", captured) if captured else self.loc.t("ui.ed_capture_none"))

    # ── применение ──
    def select_preset(self, preset_id):
        preset = self.store.get(preset_id)
        if not preset:
            return
        self.active_id = preset_id
        self._save_active()
        for pid, card in self.cards.items():
            card.set_active_state(pid == preset_id)
        self._set_busy(True)
        self.applier.apply(preset, self.store.layout_for(preset))

    def _set_busy(self, busy: bool):
        self._status_extra = "  ·  " + self.loc.t("ui.applying") if busy else ""
        self._refresh_status()

    def _on_applied(self, ok: bool, error: str):
        self._set_busy(False)
        if not ok:
            QMessageBox.warning(self, self.loc.t("ui.title"), self.loc.t("ui.err_plasma", error))

    # ── редактор ──
    def _swatch(self, button, color):
        kit_qt.style(button, f"background-color: {color};")

    def open_editor(self, preset_id):
        preset = self.store.get(preset_id) if preset_id else None
        if preset_id and not preset:
            return
        self.editing_id = preset_id
        self.editor = EditorState(preset)
        ui, t = self.ui, self.loc.t
        ui.lbl_ed_title.setText(t("ui.ed_title_edit", self._name(preset)) if preset else t("ui.ed_title_new"))
        ui.fld_ed_id.setText(preset.id if preset else "")
        ui.fld_ed_id.setReadOnly(preset is not None)
        ui.fld_ed_name.setText(self._name(preset) if preset else "")
        ui.fld_ed_desc.setText(self._desc(preset) if preset else "")
        ui.fld_ed_icon.setText(preset.icon if preset else "")
        ui.chk_ed_hide_icons.setChecked(preset.hide_desktop_icons if preset else False)
        ui.btn_ed_restore.setEnabled(bool(preset) and self.store.has_default(preset.id))
        ui.btn_ed_delete.setVisible(preset is not None)
        self._swatch(ui.btn_ed_color_dark, self.editor.color_night)
        self._swatch(ui.btn_ed_color_light, self.editor.color_day)
        ui.sld_ed_opacity.setValue(self.editor.opacity)
        ui.lbl_ed_opacity_val.setText(f"{self.editor.opacity}%")
        self._refresh_capture_label()
        ui.stacked_widget.setCurrentIndex(1)

    def pick_color(self, night: bool):
        current = self.editor.color_night if night else self.editor.color_day
        color = QColorDialog.getColor(QColor(current), self, self.loc.t("ui.cp_title"))
        if not color.isValid():
            return
        if night:
            self.editor.color_night = color.name()
            self._swatch(self.ui.btn_ed_color_dark, self.editor.color_night)
        else:
            self.editor.color_day = color.name()
            self._swatch(self.ui.btn_ed_color_light, self.editor.color_day)

    def on_opacity_changed(self, value):
        if self.editor:
            self.editor.opacity = value
        self.ui.lbl_ed_opacity_val.setText(f"{value}%")

    def pick_icon(self):
        current = self.ui.fld_ed_icon.text().strip()
        start = SYSTEM_DIR
        if current:
            full = current if os.path.isabs(current) else os.path.join(SYSTEM_DIR, current)
            start = os.path.dirname(full)
        path, _ = QFileDialog.getOpenFileName(self, self.loc.t("ui.ed_icon_label"), start,
                                              "Images (*.png *.jpg *.svg *.xpm *.ico)")
        if path:
            rel = os.path.relpath(path, SYSTEM_DIR)
            self.ui.fld_ed_icon.setText(rel if not rel.startswith("..") else path)

    def _editor_id(self) -> str:
        return self.editing_id or self.ui.fld_ed_id.text().strip()

    def capture_panels(self):
        pid = self._editor_id()
        if not pid:
            QMessageBox.warning(self, "", self.loc.t("ui.err_empty_id"))
            return
        dump = self.applier.shell.dump_layout()
        layout = PanelLayout.from_dump(dump) if dump else None
        if not layout or not layout.panels:
            QMessageBox.warning(self, "", self.loc.t("ui.err_capture"))
            return
        self.editor.captured = self.store.save_captured(pid, layout)
        self._refresh_capture_label()

    def save_editor(self):
        ui, ed = self.ui, self.editor
        is_new = self.editing_id is None
        if is_new:
            pid = ui.fld_ed_id.text().strip()
            if not pid:
                QMessageBox.warning(self, "", self.loc.t("ui.err_empty_id"))
                return
            if self.store.get(pid):
                QMessageBox.warning(self, "", self.loc.t("ui.err_duplicate_id", pid))
                return
            preset = Preset(id=pid)
        else:
            preset = self.store.get(self.editing_id)
        before = (preset.hide_desktop_icons, preset.layout_captured)

        preset.color_day, preset.color_night, preset.opacity = ed.color_day, ed.color_night, ed.opacity
        preset.hide_desktop_icons = ui.chk_ed_hide_icons.isChecked()
        preset.layout_captured = ed.captured
        preset.name = ui.fld_ed_name.text().strip() or preset.name
        preset.icon = ui.fld_ed_icon.text().strip()
        desc = ui.fld_ed_desc.text().strip()
        if desc != self._desc(preset):  # описание изменили — своё вместо переводимого
            preset.desc, preset.desc_key = desc, ""

        if is_new:
            self.store.add(preset)
        else:
            self.store.save()
        self._build_cards()
        ui.stacked_widget.setCurrentIndex(0)

        if preset.id == self.active_id:
            self._set_busy(True)
            if before == (preset.hide_desktop_icons, preset.layout_captured):
                self.applier.apply_appearance(preset)
            else:
                self.applier.apply(preset, self.store.layout_for(preset))

    def cancel_editor(self):
        # раскладка, снятая для так и не созданного пресета, не нужна
        pid = self._editor_id()
        if self.editing_id is None and pid and not self.store.get(pid):
            self.store.drop_captured(pid)
        self.ui.stacked_widget.setCurrentIndex(0)

    def restore_default(self):
        if self.editing_id and self.store.restore_default(self.editing_id):
            self._build_cards()
            self.open_editor(self.editing_id)

    def delete_preset(self):
        if not self.editing_id:
            return
        reply = QMessageBox.question(self, self.loc.t("ui.delete_confirm_title"), self.loc.t("ui.delete_confirm_msg"))
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(self.editing_id)
        if self.active_id == self.editing_id:
            self.active_id = None
            self._save_active()
        self._build_cards()
        self._refresh_status()
        self.ui.stacked_widget.setCurrentIndex(0)

    def restore_all(self):
        reply = QMessageBox.question(self, self.loc.t("ui.restore_all_title"), self.loc.t("ui.restore_all_msg"))
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.store.restore_all()
        if self.active_id and not self.store.get(self.active_id):
            self.active_id = None
            self._save_active()
        self._build_cards()
        self._refresh_status()


def install_excepthook():
    """Исключение в слоте Qt без этого молча завершает PyQt6-приложение.
    Теперь — запись в ~/.cache/equestria-os-task-panel-changer/error.log и окно с текстом."""
    log_dir = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                           "equestria-os-task-panel-changer")

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.stderr.write(text)
        try:
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "error.log"), "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        if QApplication.instance():
            QMessageBox.critical(None, "Equestria OS Task Panel Styles", text[-1500:])

    sys.excepthook = hook


def main():
    install_excepthook()
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    app.setDesktopFileName("equestria-os-task-panel-changer")
    icon_path = "/usr/share/pixmaps/equestria-os-logo.png"
    app.setWindowIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon.fromTheme("preferences-desktop-theme"))
    font_families(os.path.join(SYSTEM_DIR, "equestria_cyrillic.ttf"))  # шрифт Эквестрии для заголовков
    app.setFont(QFont("sans-serif", 11))
    qss_path = os.path.join(SYSTEM_DIR, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, encoding="utf-8") as f:
            kit_qt.app_style(f.read())
    window = TaskPanelApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
