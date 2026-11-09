"""Панель «Быстрый экспорт»: готовые и свои наборы настроек."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QPushButton, QWidget, QVBoxLayout

from ._kit import card, tr
from .presets import BUILTIN_PRESETS
from .widgets import combo


class PresetsPanel(QWidget):
    applied = pyqtSignal(dict)    # набор выбран — подставить настройки
    changed = pyqtSignal()        # свои наборы изменились — сохранить cfg
    message = pyqtSignal(str)     # что показать в строке состояния

    def __init__(self, cfg: dict, get_settings: Callable[[], dict]):
        super().__init__()
        self._cfg = cfg
        self._get_settings = get_settings
        self.box = combo(())
        self.box.activated.connect(lambda _i: self._apply_selected())
        self.box.currentIndexChanged.connect(lambda _i: self._update_buttons())
        save = QPushButton(tr("presets_panel.save_current"))
        save.clicked.connect(self._save)
        self.delete_btn = QPushButton(tr("presets_panel.delete"))
        self.delete_btn.clicked.connect(self._delete)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(self.delete_btn)
        row.addStretch()
        hint = QLabel(tr("presets_panel.preset_fills_all_settings_below"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(card(tr("presets_panel.quick_export"), self.box, row, hint))
        self._fill()

    def _user_presets(self) -> list:
        raw = self._cfg.get("presets")
        if not isinstance(raw, list):
            return []
        return [p for p in raw if isinstance(p, dict) and isinstance(p.get("name"), str)
                and isinstance(p.get("settings"), dict)]

    def _all(self) -> list:
        """[(название, настройки, свой ли)] — встроенные, затем свои."""
        return ([(tr(n), st, False) for n, st in BUILTIN_PRESETS]
                + [(p["name"], p["settings"], True) for p in self._user_presets()])

    def _fill(self, select: str | None = None) -> None:
        self.box.blockSignals(True)
        self.box.clear()
        self.box.addItem(tr("presets_panel.choose_preset"), None)
        for i, (name, _st, user) in enumerate(self._all()):
            self.box.addItem(("★ " if user else "") + name, i)
            if user and name == select:
                self.box.setCurrentIndex(self.box.count() - 1)
        self.box.blockSignals(False)
        self._update_buttons()

    def _selected(self):
        i = self.box.currentData()
        presets = self._all()
        return presets[i] if i is not None and i < len(presets) else None

    def _update_buttons(self) -> None:
        sel = self._selected()
        self.delete_btn.setEnabled(bool(sel and sel[2]))

    def _apply_selected(self) -> None:
        sel = self._selected()
        if sel:
            self.applied.emit(sel[1])
            self.message.emit(tr("presets_panel.preset_applied", sel[0]))

    def _save(self) -> None:
        sel = self._selected()
        name, ok = QInputDialog.getText(self, tr("presets_panel.custom_preset"), tr("presets_panel.preset_name"),
                                        text=sel[0] if sel and sel[2] else "")
        name = name.strip()
        if not ok or not name:
            return
        user = [p for p in self._user_presets() if p["name"] != name]
        user.append({"name": name, "settings": self._get_settings()})
        self._cfg["presets"] = user
        self.changed.emit()
        self._fill(select=name)
        self.message.emit(tr("presets_panel.preset_saved", name))

    def _delete(self) -> None:
        sel = self._selected()
        if not sel or not sel[2]:
            return
        self._cfg["presets"] = [p for p in self._user_presets() if p["name"] != sel[0]]
        self.changed.emit()
        self._fill()
        self.message.emit(tr("presets_panel.preset_deleted", sel[0]))
