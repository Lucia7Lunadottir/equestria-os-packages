"""Suggest a Feature — posts ideas to the equestria-os-packages GitHub Discussions.

Sibling of mod_report_issue.py, same safety rationale: no GitHub token is
ever stored or shipped in this app. The module builds a pre-filled "new
discussion" URL (category=ideas) and hands it off to the user's own browser,
where they review it and click Submit while logged into their own account.
No system diagnostics are collected here — unlike a bug report, an idea
isn't tied to the reporter's specific hardware.
"""

from urllib.parse import quote

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from base_module import BaseModule

_REPO = "Lucia7Lunadottir/equestria-os-packages"
_CATEGORY = "ideas"
_MAX_BODY_LEN = 6000  # keep the generated URL well under browser/CDN limits

_BTN_SEND = (
    "QPushButton{background:rgb(80,55,130);color:white;"
    "border-radius:8px;padding:8px 22px;font-size:14px;font-weight:bold;"
    "border:1px solid rgb(110,80,170);}"
    "QPushButton:hover{background:rgb(110,75,170);"
    "border:1px solid rgb(140,100,210);}"
)
_RESULT_ERR = "QLabel{color:rgb(255,130,130);font-size:12px;background:transparent;}"


class SuggestFeatureModule(BaseModule):
    module_id = "mod_suggest_feature"
    display_name_key = "module.suggest_feature.name"
    description_key = "module.suggest_feature.desc"
    category = "system"
    icon = "💡"
    sort_order = 91
    required_binary = ""
    package_name = ""

    # ── Build ─────────────────────────────────────────────────────────────────

    def build_widget(self) -> QWidget:
        outer = QWidget()
        outer.setObjectName("ContentPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(outer)
        scroll.setObjectName("ContentPage")

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        self._build_form_card(layout)

        layout.addStretch()

        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        return wrapper

    def _build_form_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("InlineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._form_title_lbl = QLabel(self.t("suggest_feature.form_title"))
        self._form_title_lbl.setObjectName("SectionTitle")
        layout.addWidget(self._form_title_lbl)

        self._title_field_lbl = QLabel(self.t("suggest_feature.title_label"))
        self._title_field_lbl.setObjectName("FieldLabel")
        layout.addWidget(self._title_field_lbl)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText(self.t("suggest_feature.title_placeholder"))
        layout.addWidget(self._title_edit)

        self._body_field_lbl = QLabel(self.t("suggest_feature.body_label"))
        self._body_field_lbl.setObjectName("FieldLabel")
        layout.addWidget(self._body_field_lbl)

        self._body_edit = QPlainTextEdit()
        self._body_edit.setPlaceholderText(self.t("suggest_feature.body_placeholder"))
        self._body_edit.setFixedHeight(140)
        layout.addWidget(self._body_edit)

        btn_row = QHBoxLayout()
        self._send_btn = QPushButton(self.t("suggest_feature.send_btn"))
        self._send_btn.setStyleSheet(_BTN_SEND)
        self._send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self._send_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(_RESULT_ERR)
        self._error_lbl.setWordWrap(True)
        self._error_lbl.hide()
        layout.addWidget(self._error_lbl)

        self._hint_lbl = QLabel(self.t("suggest_feature.browser_hint"))
        self._hint_lbl.setObjectName("FieldHint")
        self._hint_lbl.setWordWrap(True)
        layout.addWidget(self._hint_lbl)

        parent_layout.addWidget(card)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def apply_language(self) -> None:
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._form_title_lbl.setText(self.t("suggest_feature.form_title"))
        self._title_field_lbl.setText(self.t("suggest_feature.title_label"))
        self._title_edit.setPlaceholderText(self.t("suggest_feature.title_placeholder"))
        self._body_field_lbl.setText(self.t("suggest_feature.body_label"))
        self._body_edit.setPlaceholderText(self.t("suggest_feature.body_placeholder"))
        self._send_btn.setText(self.t("suggest_feature.send_btn"))
        self._hint_lbl.setText(self.t("suggest_feature.browser_hint"))

    # ── Send ──────────────────────────────────────────────────────────────────

    def _on_send(self):
        title = self._title_edit.text().strip()
        if not title:
            self._error_lbl.setText(self.t("suggest_feature.title_required"))
            self._error_lbl.show()
            return
        self._error_lbl.hide()

        body = self._body_edit.toPlainText().strip()
        if len(body) > _MAX_BODY_LEN:
            body = body[:_MAX_BODY_LEN] + "\n\n…(truncated)"

        url = (
            f"https://github.com/{_REPO}/discussions/new"
            f"?category={_CATEGORY}&title={quote(title)}&body={quote(body)}"
        )
        QDesktopServices.openUrl(QUrl(url))
