import json

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem,
                             QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import QSettings
from core.locale import tr

BTN_STYLE = ("QPushButton{background:#313244;color:#cdd6f4;border:none;padding:4px 10px;border-radius:4px;}"
             "QPushButton:hover{background:#45475a;}"
             "QPushButton:pressed{background:#585b70;}")
DANGER_BTN_STYLE = ("QPushButton{background:#8b1a1a;color:#f38ba8;border:none;padding:4px 10px;border-radius:4px;}"
                    "QPushButton:hover{background:#a03030;}"
                    "QPushButton:pressed{background:#c03030;}")
HEADER_STYLE = "color:#7f849c;font-size:10px;font-weight:bold;letter-spacing:1px;background:transparent;padding:8px 10px 4px 10px;"


class ToolPresetsPanel(QWidget):
    preset_selected = pyqtSignal(str, dict)   # (tool_name, opts_dict)
    save_requested  = pyqtSignal(str)         # preset name — main_window calls add_preset() back

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        self._presets: list[dict] = []  # [{"name": str, "tool": str, "opts": dict}, ...]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        self._title_lbl = QLabel("TOOL PRESETS")
        self._title_lbl.setObjectName("panelTitle")
        self._title_lbl.setStyleSheet(HEADER_STYLE)
        layout.addWidget(self._title_lbl)

        # List
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{background:#1e1e2e;border:none;color:#cdd6f4;}"
            "QListWidget::item{padding:6px 8px;}"
            "QListWidget::item:selected{background:#313244;color:#cba6f7;}"
            "QListWidget::item:hover{background:#282838;}"
        )
        layout.addWidget(self._list, 1)

        # Button bar
        btn_bar = QWidget()
        btn_lo = QHBoxLayout(btn_bar)
        btn_lo.setContentsMargins(8, 6, 8, 8)
        btn_lo.setSpacing(6)

        self._save_btn = QPushButton("Save Current")
        self._save_btn.setStyleSheet(BTN_STYLE)
        self._save_btn.clicked.connect(self._on_save)

        self._load_btn = QPushButton("Load")
        self._load_btn.setStyleSheet(BTN_STYLE)
        self._load_btn.clicked.connect(self._on_load)

        self._del_btn = QPushButton("Delete")
        self._del_btn.setStyleSheet(DANGER_BTN_STYLE)
        self._del_btn.clicked.connect(self._on_delete)

        btn_lo.addWidget(self._save_btn)
        btn_lo.addWidget(self._load_btn)
        btn_lo.addStretch()
        btn_lo.addWidget(self._del_btn)

        layout.addWidget(btn_bar)

        self._load_presets()

    # ---------------------------------------------------------------- Public

    def add_preset(self, name: str, tool: str, opts: dict):
        """Called by main_window to actually store the preset."""
        # Overwrite if same name+tool exists
        for p in self._presets:
            if p["name"] == name and p["tool"] == tool:
                p["opts"] = dict(opts)
                self._save_presets()
                self._refresh_list()
                return
        self._presets.append({"name": name, "tool": tool, "opts": dict(opts)})
        self._save_presets()
        self._refresh_list()

    # ---------------------------------------------------------------- Private

    def _on_save(self):
        name, ok = QInputDialog.getText(
            self,
            tr("presets.save_title") if tr("presets.save_title") != "presets.save_title" else "Save Preset",
            tr("presets.save_prompt") if tr("presets.save_prompt") != "presets.save_prompt" else "Preset name:",
        )
        if ok and name.strip():
            self.save_requested.emit(name.strip())

    def _on_load(self):
        item = self._list.currentItem()
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or not (0 <= idx < len(self._presets)):
            return
        preset = self._presets[idx]
        self.preset_selected.emit(preset["tool"], dict(preset["opts"]))

    def _on_delete(self):
        item = self._list.currentItem()
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or not (0 <= idx < len(self._presets)):
            return
        preset = self._presets[idx]
        reply = QMessageBox.question(
            self,
            tr("presets.delete_title") if tr("presets.delete_title") != "presets.delete_title" else "Delete Preset",
            (tr("presets.delete_prompt") if tr("presets.delete_prompt") != "presets.delete_prompt"
             else f"Delete preset '{preset['name']}'?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._presets.pop(idx)
            self._save_presets()
            self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        for idx, preset in enumerate(self._presets):
            tool = preset.get("tool", "")
            name = preset.get("name", "")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, idx)
            # Set display text with tool name in muted color via HTML is not supported
            # in QListWidget natively — use composite text with separator
            item.setText(f"[{tool}]  {name}")
            # Colour the tool part is not straightforward; set tooltip instead
            item.setToolTip(f"Tool: {tool}\nName: {name}")
            self._list.addItem(item)

    def _load_presets(self):
        settings = QSettings("ImageFinish", "ToolPresets")
        raw = settings.value("presets", None)
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    self._presets = data
            except Exception:
                self._presets = []
        else:
            self._presets = []
        self._refresh_list()

    def _save_presets(self):
        settings = QSettings("ImageFinish", "ToolPresets")
        try:
            # opts values may contain QColor — convert to strings
            serializable = []
            for p in self._presets:
                opts_copy = {}
                for k, v in p.get("opts", {}).items():
                    if hasattr(v, "name"):  # QColor
                        opts_copy[k] = v.name()
                    else:
                        opts_copy[k] = v
                serializable.append({
                    "name": p["name"],
                    "tool": p["tool"],
                    "opts": opts_copy,
                })
            settings.setValue("presets", json.dumps(serializable))
        except Exception:
            pass

    def retranslate(self):
        self._title_lbl.setText(
            tr("presets.title") if tr("presets.title") != "presets.title" else "TOOL PRESETS"
        )
        self._save_btn.setText(
            tr("presets.save_btn") if tr("presets.save_btn") != "presets.save_btn" else "Save Current"
        )
        self._load_btn.setText(
            tr("presets.load_btn") if tr("presets.load_btn") != "presets.load_btn" else "Load"
        )
        self._del_btn.setText(
            tr("presets.delete_btn") if tr("presets.delete_btn") != "presets.delete_btn" else "Delete"
        )
