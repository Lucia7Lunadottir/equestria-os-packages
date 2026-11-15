"""Git actions for a project and account-backed repository pickers."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
                             QLabel, QListWidget, QListWidgetItem, QVBoxLayout)

import library
from kit import call, tr


def web_remote(remote):
    """Convert a normal SSH or HTTPS remote to a credential-free web URL."""
    scp = re.fullmatch(r"(?:[\w.-]+@)?([\w.-]+):([\w./-]+)", remote)
    if scp and "://" not in remote:
        host, path = scp.groups()
    else:
        url = urlsplit(remote)
        if url.scheme not in ("ssh", "https", "http") or not url.hostname:
            return ""
        host, path = url.hostname, url.path.strip("/")
        if url.scheme in ("http", "https") and url.port:
            host += f":{url.port}"
    path = path.removesuffix(".git").strip("/")
    return f"https://{host}/{path}" if "/" in path else ""


def choose_files(parent, root, paths):
    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("git.stage"))
    dialog.resize(640, 440)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(str(root)))
    view = QListWidget()
    layout.addWidget(view)
    for path in paths:
        item = QListWidgetItem(path, view)
        item.setCheckState(Qt.CheckState.Unchecked)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec():
        return [path for i, path in enumerate(paths) if view.item(i).checkState() == Qt.CheckState.Checked]
    return []


class GitActions:
    def __init__(self, page):
        self.page = page

    def run(self, program, args, label, cwd=None, done=None, capture=False):
        exe = library.executable(program)
        if not exe:
            self.page.warning(tr("git.missing", program))
            return
        self.page.window.log.setChecked(True)
        self.page.jobs.run_process(f"git:{cwd or program}", label, exe, args, done, cwd=cwd,
                                   capture=capture, failed=self.page.warning)

    def git(self, root, args, key, done=None, capture=False):
        self.run("git", ["--no-pager", *args], tr(key), root, done, capture)

    def clone(self, program="git", repo=None):
        if repo is None:
            repo = self.page.text("project.git")
        if not repo or repo.startswith("-"):
            return
        if program == "git" and not (repo.startswith(("https://", "ssh://")) or
                                      re.match(r"^[\w.-]+@[\w.-]+:", repo) or Path(repo).is_absolute()):
            self.page.warning(tr("project.git"))
            return
        parent = self.page.folder("project.parent")
        if not parent:
            return
        name = self.page.text("project.new_name", repo.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git"))
        if not name:
            return
        if library.bad_name(name):
            self.page.warning(tr("project.bad_name"))
            return
        dest = Path(parent) / name
        if dest.exists():
            self.page.warning(tr("project.exists"))
            return
        args = ["clone", "--", repo, str(dest)] if program == "git" else ["repo", "clone", repo, str(dest)]
        self.run(program, args, tr("projects.clone"), dest.parent, lambda _: self.page.add_path(dest))

    def repositories(self, provider):
        github = provider == "GitHub"
        program = "gh" if github else "glab"
        def load(page_number):
            args = (["api", f"user/repos?per_page=100&sort=updated&page={page_number}"] if github else
                    ["repo", "list", "--member", "--per-page", "100", "--page", str(page_number), "--output", "json"])

            def choose(data):
                items = json.loads(data)
                names = sorted({item["full_name" if github else "path_with_namespace"] for item in items})
                if not names:
                    self.page.warning(tr("projects.nothing"))
                    return
                more = str(tr("git.more"))
                choices = names + ([more] if len(items) == 100 else [])
                name, ok = QInputDialog.getItem(self.page, provider, tr("git.repo"), choices, editable=False)
                if ok and name == more:
                    load(page_number + 1)
                elif ok:
                    self.clone(program, name)

            self.run(program, args, provider, done=choose, capture=True)
        load(1)

    def add_menu(self, menu, project):
        submenu = menu.addMenu("Git")
        actions = (("git.status", lambda r: self.git(r, ["status", "--short", "--branch"], "git.status")),
                   ("git.history", lambda r: self.git(r, ["log", "-25", "--oneline", "--decorate"], "git.history")),
                   ("git.stage", self.stage), ("git.commit", self.commit),
                   ("git.switch", self.switch), ("git.new_branch", self.new_branch),
                   ("git.remote", self.remote), ("git.fetch", lambda r: self.git(r, ["fetch", "--all"], "git.fetch")),
                   ("git.pull", lambda r: self.git(r, ["pull", "--ff-only"], "git.pull")),
                   ("git.push", self.push), ("git.web", self.browse),
                   ("git.reviews", lambda r: self.browse(r, reviews=True)))
        for key, action in actions:
            call(submenu.addAction, tr(key)).triggered.connect(
                lambda _=False, fn=action: self.git(project.path, ["rev-parse", "--show-toplevel"], "git.repo",
                                                     lambda data: fn(Path(os.fsdecode(data).rstrip("\n"))), True))
        submenu.addSeparator()
        call(submenu.addAction, tr("git.init")).triggered.connect(lambda: self.initialize(project.path))

    def initialize(self, path):
        if self.page.confirm("git.confirm_init", path):
            self.git(path, ["init"], "git.init")

    def stage(self, root):
        def choose(data):
            paths = sorted({os.fsdecode(p) for p in data.split(b"\0") if p})
            if not paths:
                self.page.warning(tr("git.clean"))
                return
            selected = choose_files(self.page, root, paths)
            if selected:
                self.git(root, ["--literal-pathspecs", "add", "--", *selected], "git.stage")
        self.git(root, ["ls-files", "--modified", "--others", "--exclude-standard", "-z"], "git.stage", choose, True)

    def commit(self, root):
        def review(data):
            if not data.strip():
                self.page.warning(tr("git.no_staged"))
                return
            message = self.page.text("git.message")
            if message and self.page.confirm("git.confirm_commit", root, os.fsdecode(data).strip()):
                self.git(root, ["commit", "-m", message], "git.commit")
        self.git(root, ["diff", "--cached", "--name-status"], "git.commit", review, True)

    def switch(self, root):
        def select(data):
            names = os.fsdecode(data).splitlines()
            if names:
                name, ok = QInputDialog.getItem(self.page, "Git", tr("git.switch"), names, editable=False)
                if ok:
                    self.git(root, ["switch", "--", name], "git.switch")
        self.git(root, ["for-each-ref", "--format=%(refname:short)", "refs/heads"], "git.switch", select, True)

    def new_branch(self, root):
        name = self.page.text("git.new_branch")
        if name and not name.startswith("-"):
            self.git(root, ["switch", "-c", name], "git.new_branch")

    def remote(self, root):
        url = self.page.text("project.git")
        if url and web_remote(url):
            self.git(root, ["remote", "add", "origin", url], "git.remote")
        elif url:
            self.page.warning(tr("project.git"))

    def push(self, root):
        def confirm(data):
            branch = os.fsdecode(data).strip()
            if branch and self.page.confirm("git.confirm_push", branch, root):
                self.git(root, ["push", "--set-upstream", "origin", f"refs/heads/{branch}:refs/heads/{branch}"], "git.push")
        self.git(root, ["symbolic-ref", "--short", "HEAD"], "git.push", confirm, True)

    def browse(self, root, reviews=False):
        def opened(data):
            link = web_remote(os.fsdecode(data).strip())
            if link and reviews:
                host = urlsplit(link).hostname
                if host == "github.com":
                    link += "/pulls"
                elif host == "gitlab.com":
                    link += "/-/merge_requests"
                else:
                    self.page.warning(tr("git.no_reviews"))
                    return
            if link:
                QDesktopServices.openUrl(QUrl(link))
            else:
                self.page.warning(tr("git.no_web"))
        self.git(root, ["remote", "get-url", "origin"], "git.web", opened, True)
