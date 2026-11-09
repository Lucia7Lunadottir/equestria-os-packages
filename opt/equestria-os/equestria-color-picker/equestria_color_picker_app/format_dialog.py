"""color-picker: format dialog."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
from .color import try_render
from .formats import HELP_FIELDS
from .localization import live_i18n, tr
from .widgets import flag


class FormatDialog(QDialog):
    def __init__(self, parent, fields_fn, name: str = "", tpl: str = ""):
        super().__init__(parent)
        self.fields_fn = fields_fn
        live_i18n.call(self.setWindowTitle, tr("format_dialog.custom_format"))
        self.setMinimumWidth(600)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        self.name = QLineEdit(name)
        live_i18n.call(self.name.setPlaceholderText, tr("format_dialog.name_example_my_game"))
        self.tpl = QLineEdit(tpl)
        live_i18n.call(self.tpl.setPlaceholderText, tr("format_dialog.template_example_new_color_f"))
        hint = live_i18n.call(QLabel, HELP_FIELDS)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.preview = live_i18n.call(QLabel, "")
        self.preview.setObjectName("out")
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        cancel = live_i18n.call(QPushButton, tr("format_dialog.cancel"))
        cancel.clicked.connect(self.reject)
        self.ok = live_i18n.call(QPushButton, tr("format_dialog.save"))
        self.ok.setObjectName("primary")
        self.ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(self.ok)
        for w in (self.name, self.tpl, hint, self.preview):
            v.addWidget(w)
        v.addLayout(row)
        self.name.textChanged.connect(self._update)
        self.tpl.textChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        res = try_render(self.tpl.text(), self.fields_fn()) if self.tpl.text() else None
        live_i18n.call(self.preview.setText, res if res is not None else (tr("format_dialog.enter_template") if not self.tpl.text()
                                                          else tr("format_dialog.template_error_unknown_field_braces")))
        flag(self.tpl, bool(self.tpl.text()) and res is None)
        self.ok.setEnabled(res is not None and bool(self.name.text().strip()))

    def result_data(self):
        return self.name.text().strip(), self.tpl.text()
