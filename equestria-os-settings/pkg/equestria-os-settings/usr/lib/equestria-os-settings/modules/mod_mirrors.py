"""Mirror Manager module — inline view + launch for pg-rankmirrors."""

import subprocess

_BTN_ACTION = (
    "QPushButton{background:rgb(45,42,68);color:rgb(200,190,220);"
    "border-radius:6px;padding:6px 18px;font-size:13px;"
    "border:1px solid rgb(80,75,110);}"
    "QPushButton:hover{background:rgb(65,60,95);color:white;}"
    "QPushButton:disabled{background:rgb(35,33,52);color:rgb(90,85,110);}"
)
_BTN_OPEN = (
    "QPushButton{background:transparent;color:rgb(180,160,220);"
    "border:1px solid rgb(80,70,115);border-radius:6px;"
    "padding:4px 14px;font-size:12px;}"
    "QPushButton:hover{background:rgb(45,42,68);color:rgb(210,190,245);}"
)

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from base_module import BaseModule

_MIRRORLIST = "/etc/pacman.d/mirrorlist"


class MirrorsModule(BaseModule):
    module_id = "mod_mirrors"
    display_name_key = "module.mirrors.name"
    description_key = "module.mirrors.desc"
    category = "system"
    icon = "🌐"
    sort_order = 20
    required_binary = "/usr/bin/pg-rankmirrors"
    package_name = "pg-rankmirrors"

    def build_widget(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("ContentPage")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        # Current mirrors preview
        mirrors_card = QFrame()
        mirrors_card.setObjectName("InlineCard")
        mc_layout = QVBoxLayout(mirrors_card)
        mc_layout.setContentsMargins(16, 12, 16, 12)
        mc_layout.setSpacing(8)

        self._mirrors_title = QLabel(self.t("mirrors.current"))
        self._mirrors_title.setObjectName("SectionTitle")
        mc_layout.addWidget(self._mirrors_title)

        self._mirrors_lbl = QLabel()
        self._mirrors_lbl.setObjectName("MirrorText")
        self._mirrors_lbl.setWordWrap(True)
        self._mirrors_lbl.setTextInteractionFlags(
            self._mirrors_lbl.textInteractionFlags()
        )
        mc_layout.addWidget(self._mirrors_lbl)
        layout.addWidget(mirrors_card)

        # Country + rank button
        action_card = QFrame()
        action_card.setObjectName("InlineCard")
        ac_layout = QVBoxLayout(action_card)
        ac_layout.setContentsMargins(20, 16, 20, 16)
        ac_layout.setSpacing(12)

        country_row = QHBoxLayout()
        self._country_lbl = QLabel(self.t("mirrors.country_label"))
        self._country_lbl.setObjectName("FieldLabel")
        country_row.addWidget(self._country_lbl)
        self._country_edit = QLineEdit()
        self._country_edit.setStyleSheet(
            "QLineEdit{background:rgb(40,35,60);color:rgb(220,210,240);"
            "border:1px solid rgb(100,80,150);border-radius:6px;padding:5px 10px;}"
            "QLineEdit:focus{border:1px solid rgb(160,120,220);}"
        )
        self._country_edit.setPlaceholderText("DE, US, PL, …")
        self._country_edit.setFixedWidth(160)
        country_row.addWidget(self._country_edit)
        country_row.addStretch()
        ac_layout.addLayout(country_row)

        btn_row = QHBoxLayout()
        self._rank_btn = QPushButton(self.t("mirrors.rank_btn"))
        self._rank_btn.setObjectName("ActionBtn")
        self._rank_btn.setStyleSheet(_BTN_ACTION)
        self._rank_btn.clicked.connect(self._rank_mirrors)
        btn_row.addWidget(self._rank_btn)

        self._open_btn = QPushButton(self.t("mirrors.open_btn"))
        self._open_btn.setObjectName("OpenAppBtn")
        self._open_btn.setStyleSheet(_BTN_OPEN)
        self._open_btn.clicked.connect(
            lambda: self.launch_app("/usr/bin/pg-rankmirrors")
        )
        btn_row.addWidget(self._open_btn)
        btn_row.addStretch()
        ac_layout.addLayout(btn_row)
        layout.addWidget(action_card)

        layout.addStretch()

        self._refresh_mirrors()
        return widget

    def on_shown(self):
        self._refresh_mirrors()

    def apply_language(self):
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._mirrors_title.setText(self.t("mirrors.current"))
        self._country_lbl.setText(self.t("mirrors.country_label"))
        self._rank_btn.setText(self.t("mirrors.rank_btn"))
        self._open_btn.setText(self.t("mirrors.open_btn"))

    def _refresh_mirrors(self):
        try:
            with open(_MIRRORLIST) as f:
                lines = [l.rstrip() for l in f if l.strip() and not l.startswith("#")][:6]
            self._mirrors_lbl.setText("\n".join(lines) if lines else "—")
        except Exception:
            self._mirrors_lbl.setText("—")

    def _rank_mirrors(self):
        country = self._country_edit.text().strip()
        cmd = ["/usr/bin/pg-rankmirrors"]
        if country:
            cmd += ["--country", country]
        self.launch_in_terminal(cmd)
