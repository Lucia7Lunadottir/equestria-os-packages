from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from controls import Page
from kit import tr


class Services(Page):
    def __init__(self, window):
        super().__init__(window)
        self.title("nav.services")
        row = self.row()
        self.button(row, "template.browse", self.templates)
        self.button(row, "template.sample", lambda: self.templates("sample"))
        self.button(row, "template.create", self.template_from_project)
        self.button(row, "cloud.status", lambda: self.jobs.run("cloud", tr("cloud.status"), ["cloud", "status"]))
        self.button(row, "cloud.link", self.link)
        row.addStretch()
        row = self.row()
        for key, url in (("web.learn", "https://learn.unity.com/"),
                         ("web.assets", "https://assetstore.unity.com/"),
                         ("web.cloud", "https://cloud.unity.com/"),
                         ("web.docs", "https://docs.unity.com/")):
            self.button(row, key, lambda link=url: QDesktopServices.openUrl(QUrl(link)))
        row.addStretch()
        self.layout_box.addStretch()

    def templates(self, category="all"):
        self.window.go("new")
        box = self.window.new.category
        box.setCurrentIndex(box.findData(category))

    def template_from_project(self):
        path = self.folder("project.select")
        if path:
            name = self.text("template.id", "com.example.template.")
            if name and not name.startswith("-"):
                self.jobs.run(path, tr("template.create"), ["templates", "create", path, "--name", name])

    def link(self):
        path = self.folder("project.select")
        if path:
            cloud = self.text("cloud.id")
            if cloud and not cloud.startswith("-"):
                self.jobs.run(path, tr("cloud.link"), ["projects", "link", "cloud", path, "--cloud-project", cloud])
