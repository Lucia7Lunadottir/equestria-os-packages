from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from account_views import AccountCard, LicenseList
from controls import Page, chip
from kit import VERSION, call, tr
from projects import FoldersPanel
from settings_sections import SECTIONS


class Settings(Page):
    """Settings window laid out like Unity Hub: section list on the left, the chosen section on the right."""

    def __init__(self, window):
        super().__init__(window)
        self.layout_box.setContentsMargins(0, 0, 0, 0)
        self.layout_box.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(24, 18, 18, 14)
        head.setSpacing(12)
        title = call(QLabel, tr("nav.settings"))
        title.setObjectName("title")
        head.addWidget(title)
        head.addWidget(chip(f"Equestria Unity {VERSION}"))
        head.addStretch()
        close = QPushButton("✕")
        close.setObjectName("flat")
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(lambda: window.settings_dialog.close())
        head.addWidget(close)
        self.layout_box.addLayout(head)
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        self.layout_box.addWidget(line)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.layout_box.addLayout(body, 1)
        side_box = QVBoxLayout()
        side_box.setContentsMargins(12, 14, 12, 12)
        side_box.setSpacing(2)
        side_box.setAlignment(Qt.AlignmentFlag.AlignTop)
        side = QWidget()
        side.setFixedWidth(220)
        side.setLayout(side_box)
        body.addWidget(side)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.sections = {}
        self.tabs = {}
        for kind in SECTIONS:
            section = kind(self)
            tab = call(QPushButton, tr(kind.KEY))
            tab.setObjectName("nav")
            tab.setCheckable(True)
            tab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tab.clicked.connect(lambda _=False, k=kind.KEY: self.select(k))
            side_box.addWidget(tab)
            self.stack.addWidget(section)
            self.sections[kind.KEY] = section
            self.tabs[kind.KEY] = tab
        self.select("settings.appearance")
        self.config.changed.connect(lambda _key: self.refresh())

    def find(self, key):
        return self.sections[key]

    def select(self, key):
        self.stack.setCurrentWidget(self.sections[key])
        for name, tab in self.tabs.items():
            tab.setChecked(name == key)
        self.sections[key].opened()
        self.refresh()

    def refresh(self):
        for section in self.sections.values():
            section.refresh()

    def language_changed(self):
        self.refresh()
        self.window.new.show_cards()
        self.window.projects.redraw()  # column titles come from the table model
        for panel in self.findChildren(FoldersPanel):
            panel.update_tooltips()


class Account(Page):
    """Unity ID and licenses. Both cards draw the shared AccountState, as Settings → Licenses does."""

    def __init__(self, window):
        super().__init__(window)
        self.state = window.account_state
        self.title("nav.account")
        self.label(self.layout_box, "account.heading", "rowname")
        self.profile = AccountCard(self.state)
        self.layout_box.addWidget(self.profile)
        actions = QHBoxLayout()
        self.layout_box.addLayout(actions)
        self.login = self.button(actions, "account.login", lambda: self.cli.login(self.load), "primary")
        manage = call(QPushButton, tr("account.manage"))
        manage.setObjectName("small")
        menu = QMenu(manage)
        call(menu.addAction, tr("account.accounts")).triggered.connect(lambda: self.cli.accounts(self.load))
        call(menu.addAction, tr("account.switch")).triggered.connect(self.switch)
        menu.addSeparator()
        call(menu.addAction, tr("account.logout")).triggered.connect(self.logout)
        manage.setMenu(menu)
        actions.addWidget(manage)
        self.button(actions, "license.refresh", self.load)
        actions.addStretch()

        head = QHBoxLayout()
        self.label(head, "license.status", "rowname")
        head.addStretch()
        self.button(head, "license.personal", self.activate)
        self.button(head, "license.file", self.license_file)
        self.layout_box.addSpacing(8)
        self.layout_box.addLayout(head)
        self.layout_box.addWidget(LicenseList(self.state))
        self.layout_box.addStretch()
        self.state.changed.connect(lambda: self.login.setVisible(not self.state.signed_in()))

    def refresh(self):
        self.load()

    def load(self):
        self.state.load()

    # Account commands re-read the state afterwards (self.load), so no screen shows old data.

    def switch(self):
        account = self.text("account.email")
        if account and not account.startswith("-"):
            self.cli.switch_account(account, self.load)

    def logout(self):
        if self.confirm("account.confirm_logout"):
            self.cli.logout(self.load)

    def activate(self):
        if self.confirm("license.confirm"):
            self.cli.activate_personal(self.load)

    def license_file(self):
        path = QFileDialog.getOpenFileName(self, tr("license.file"), "", "Unity (*.ulf *.xml)")[0]
        if path:
            self.cli.activate_file(path, self.load)
