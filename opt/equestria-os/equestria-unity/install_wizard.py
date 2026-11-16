"""Install an Editor or add modules in three steps, like Unity Hub: version → modules → confirmation."""
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget,
                             QVBoxLayout, QWidget)

from install_plan import ModuleTree, fetch_manifest, linux_download, size_text
from kit import call, tr
from equestria_kit.live_i18n import format_text
from releases import ARCHIVE, ReleaseList
from versions import RELEASE, release_title

VERSION, MODULES, CONFIRM = range(3)
STEPS = ("install.step_version", "install.step_modules", "install.step_confirm")


def repolish(widget, name):
    widget.setObjectName(name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class InstallWizard(QDialog):
    def __init__(self, cli, editors, tasks, parent, *, version=None, release=None, search="", failed=None):
        """editors: EditorRegistry. tasks: Background of a page that outlives this dialog.
        version: start on the modules step (adding modules, a version a project needs).
        search: open the archive filtered by this version prefix (patch updates of one line).
        failed: called with the reason if the started installation fails."""
        super().__init__(parent)
        self.cli, self.editors, self.tasks, self.failed = cli, editors, tasks, failed
        self.version = ""
        self.release = {}
        self.installed = False
        self.modules = []
        self.loaded = False      # the module list of self.version is shown
        self.planned = False     # the CLI confirmed what it will download
        self.request = 0         # answers to an older request are ignored
        self.fixed = bool(version)
        call(self.setWindowTitle, tr("editor.install_title"))
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        steps = QHBoxLayout()
        steps.setSpacing(10)
        self.step_labels = []
        for index, key in enumerate(STEPS):
            if index:
                arrow = QLabel("›")
                arrow.setObjectName("hint")
                steps.addWidget(arrow)
            label = call(QLabel, format_text("{}  {}", index + 1, tr(key)))
            label.setObjectName("step")
            steps.addWidget(label)
            self.step_labels.append(label)
        steps.addStretch()
        layout.addLayout(steps)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        first = QWidget()
        box = QVBoxLayout(first)
        box.setContentsMargins(0, 0, 0, 0)
        self.releases = ReleaseList(editors.versions(), first, tab=ARCHIVE if search else 0, search=search)
        self.releases.chosen.connect(self.choose)
        box.addWidget(self.releases, 1)
        manual = QHBoxLayout()
        manual.addWidget(call(QLabel, tr("install.other_version")))
        self.manual = QLineEdit()
        self.manual.setPlaceholderText("6000.6.9f1")
        self.manual.textChanged.connect(self.update_buttons)
        self.manual.returnPressed.connect(self.next)
        manual.addWidget(self.manual, 1)
        box.addLayout(manual)
        self.stack.addWidget(first)

        second = QWidget()
        box = QVBoxLayout(second)
        box.setContentsMargins(0, 0, 0, 0)
        self.heading = QLabel()
        self.heading.setObjectName("h2")
        box.addWidget(self.heading)
        self.adding = call(QLabel, tr("install.adding"))
        self.adding.setObjectName("hint")
        self.adding.setWordWrap(True)
        box.addWidget(self.adding)
        hint = call(QLabel, tr("install.choose"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.tree = ModuleTree(second)
        box.addWidget(self.tree, 1)
        self.eula = call(QCheckBox, tr("editor.eula"))
        box.addWidget(self.eula)
        self.stack.addWidget(second)

        third = QWidget()
        box = QVBoxLayout(third)
        box.setContentsMargins(0, 0, 0, 0)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        card = QFrame()
        card.setObjectName("card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(18, 16, 18, 16)
        self.summary = QLabel()
        self.summary.setObjectName("rowname")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(self.summary)
        box.addWidget(card)
        self.stack.addWidget(third)

        bottom = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.back = call(QPushButton, tr("install.back"))
        self.back.setObjectName("small")
        self.back.clicked.connect(self.previous)
        self.forward = QPushButton()
        self.forward.setObjectName("primary")
        self.forward.clicked.connect(self.next)
        cancel = call(QPushButton, tr("jobs.cancel_short"))
        cancel.setObjectName("small")
        cancel.clicked.connect(self.reject)
        for button in (self.back, self.forward, cancel):
            button.setAutoDefault(False)
            bottom.addWidget(button)
        layout.addLayout(bottom)

        if version:
            self.choose(version, release or {})
        else:
            self.show_step(VERSION)

    # ---- navigation -----------------------------------------------------------------------------

    def step(self):
        return self.stack.currentIndex()

    def show_step(self, step):
        self.stack.setCurrentIndex(step)
        for index, label in enumerate(self.step_labels):
            repolish(label, "stepOn" if index == step else "step")
        self.back.setVisible(step > (MODULES if self.fixed else VERSION))
        call(self.forward.setText, tr("install.start" if step == CONFIRM else "install.next"))
        self.update_buttons()

    def update_buttons(self, *_):
        step = self.step()
        if step == VERSION:
            ready = bool(RELEASE.fullmatch(self.manual.text().strip()))
        elif step == MODULES:
            ready = self.loaded
        else:
            ready = self.planned
        self.forward.setEnabled(ready)

    def set_status(self, text, error=False):
        self.status.setText(str(text))
        repolish(self.status, "err" if error else "hint")

    def previous(self):
        self.request += 1
        self.set_status("")
        self.show_step(self.step() - 1)

    def next(self):
        step = self.step()
        if step == VERSION:
            version = self.manual.text().strip()
            if RELEASE.fullmatch(version):
                self.choose(version, {})
        elif step == MODULES:
            modules = self.tree.selection()
            if self.installed and not modules:
                self.set_status(tr("install.no_modules"), True)
                return
            self.modules = modules
            self.show_step(CONFIRM)
            self.plan()
        elif self.planned:
            self.cli.install(self.version, self.modules, installed=self.installed, eula=self.eula.isChecked(),
                             done=lambda _: self.editors.reload(), failed=self.failed)
            self.accept()

    def stale(self, token):
        """An answer that arrived after the dialog was closed or after the user moved on."""
        return sip.isdeleted(self) or token != self.request

    # ---- step 2: modules ------------------------------------------------------------------------

    def choose(self, version, release):
        if version != self.version:
            self.modules = []
            self.eula.setChecked(False)
        self.version, self.release = version, release or {}
        self.installed = version in self.editors
        self.heading.setText(f"{release_title(version)}  ({version})")
        self.adding.setVisible(self.installed)
        self.loaded = False
        self.tree.show_modules([])
        self.show_step(MODULES)
        self.set_status(tr("release.loading"))
        self.request += 1
        token = self.request

        def show(modules):
            if self.stale(token):
                return
            self.tree.show_modules(modules, self.modules)
            self.loaded = True
            self.set_status("")
            self.update_buttons()

        def fail(reason):
            if self.stale(token):
                return
            # Without a module list a new Editor can still be installed on its own; modules need the list.
            self.loaded = not self.installed
            self.set_status(tr("release.error", reason), True)
            self.update_buttons()

        if self.installed:
            self.cli.module_list(version, show, fail)
        elif self.release.get("downloads"):
            try:
                show(linux_download(self.release)["modules"])
            except ValueError as error:
                fail(error)
        else:
            self.tasks.run(lambda: fetch_manifest(version)["modules"],
                           lambda result: fail(result) if isinstance(result, Exception) else show(result))

    # ---- step 3: what will be downloaded --------------------------------------------------------

    def plan(self):
        self.planned = False
        self.summary.setText("")
        self.set_status(tr("install.planning"))
        self.update_buttons()
        self.request += 1
        token = self.request
        modules = list(self.modules)

        def planned(data):
            if self.stale(token):
                return
            size = size_text(data.get("totalDownloadSize"))
            components = [str(m.get("name") or m.get("id")) for m in (data.get("modules") or [])
                          if isinstance(m, dict) and (m.get("name") or m.get("id"))]
            names = ", ".join(dict.fromkeys([*self.tree.names(modules), *components])) or str(tr("install.editor_only"))
            self.summary.setText(str(tr("install.summary", self.version, names, size)))
            self.planned = True
            self.set_status(tr("install.ready"))
            self.update_buttons()

        def failed(reason):
            if not self.stale(token):
                self.set_status(tr("install.plan_failed", reason), True)

        self.cli.plan(self.version, modules, installed=self.installed, eula=self.eula.isChecked(),
                      done=planned, failed=failed)
