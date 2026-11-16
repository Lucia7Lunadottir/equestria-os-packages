"""Git integration, like Unity Hub's: clone a repository into a new project, see a project's branch,
open its repository on the web or in a Git client. Day-to-day Git work belongs in a real Git client."""
import json
import re
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import QInputDialog, QMenu

import unity_paths
from formatting import bad_name
from git_info import web_remote  # noqa: F401  (kept importable from here)
from kit import call, tr

# What Git prints when it fails, and what the user can do about it.
GIT_ERRORS = (("please tell me who you are", "git.err.identity"), ("author identity unknown", "git.err.identity"),
              ("could not read username", "git.err.credentials"), ("authentication failed", "git.err.credentials"),
              ("permission denied (publickey)", "git.err.credentials"),
              ("could not resolve host", "git.err.network"), ("unable to access", "git.err.network"),
              ("not possible to fast-forward", "git.err.diverged"), ("diverging branches", "git.err.diverged"),
              ("[rejected]", "git.err.rejected"), ("would be overwritten", "git.err.local_changes"),
              ("has no upstream branch", "git.err.no_upstream"), ("no configured push destination", "git.err.no_remote"))


# Git's messages are recognised by their English wording (explain_git, stopped_on_conflicts), so Git must not
# translate them; the user still reads a translated explanation. No password prompt on a terminal nobody sees.
GIT_ENVIRONMENT = {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


def stopped_on_conflicts(output):
    """A merge that stopped because files conflict: an expected outcome, the panel takes over from here."""
    text = str(output).casefold()
    return "automatic merge failed" in text or "conflict (" in text


def explain_git(output):
    """A sentence about the failure for the dialog; Git's own output stays in the log."""
    text = str(output).casefold()
    key = next((key for needle, key in GIT_ERRORS if needle in text), None)
    return tr(key) if key else output


# Git clients and the arguments that open a given repository in them; the first installed one is used.
CLIENTS = (("opensourcetree", lambda root: [str(root)]), ("gitg", lambda root: [str(root)]),
           ("git-cola", lambda root: ["--repo", str(root)]), ("github-desktop", lambda root: [str(root)]),
           ("gitkraken", lambda root: ["-p", str(root)]))


def git_client():
    """(executable, arguments for a repository root) of the first installed Git client, or None."""
    for name, arguments in CLIENTS:
        exe = unity_paths.executable(name)
        if exe:
            return exe, arguments
    return None


class GitActions:
    def __init__(self, page):
        self.page = page

    def run(self, program, args, label, cwd=None, done=None, capture=False, failed=None, expected=None):
        """expected(output): a failure that is a normal outcome (no warning, `failed` still runs)."""
        exe = unity_paths.executable(program)
        if not exe:
            self.page.warning(tr("git.missing", program))
            return
        def fail(reason):
            if not (expected and expected(reason)):
                self.page.warning(explain_git(reason))
            if failed:
                failed(reason)
        # Never wait for a password on a terminal nobody sees: credentials come from helpers or SSH keys.
        # Talking to a server may take a while, but never forever.
        self.page.jobs.run_process(f"git:{cwd or program}", label, exe, args, done, cwd=cwd, capture=capture,
                                   failed=fail, environment=GIT_ENVIRONMENT,
                                   timeout=0 if args[:1] == ["clone"] else 300)

    def git(self, root, args, label, done=None, failed=None, expected=None):
        self.run("git", ["--no-pager", *args], label, root, done, failed=failed, expected=expected)

    # ---- everyday operations (used by the Git panel) ----------------------------------------------

    # Each step reports to `done` on success and `failed` on failure (after the user saw why).

    def fetch(self, root, done, failed=None):
        """Ask the server what is new, without changing any file here."""
        self.git(root, ["fetch", "--prune"], tr("git.fetch"), done, failed)

    def pull(self, root, done, failed=None):
        """Receive the server's commits; only when that cannot lose anything (fast-forward)."""
        self.git(root, ["pull", "--ff-only"], tr("git.pull"), done, failed)

    def push(self, root, branch, upstream, done, failed=None):
        """Send the commits; a branch new to the server is created there and connected to this one."""
        args = ["push"] if upstream else ["push", "--set-upstream", "origin", branch]
        self.git(root, args, tr("git.push"), done, failed)

    def commit(self, root, paths, message, done, failed=None):
        """Commit exactly the chosen files (new, changed or deleted ones) with the message."""
        def staged(_):
            self.git(root, ["--literal-pathspecs", "commit", "-m", message, "--", *paths], tr("git.commit"),
                     done, failed)
        self.git(root, ["--literal-pathspecs", "add", "--all", "--", *paths], tr("git.commit"), staged, failed)

    def merge_remote(self, root, done, failed=None):
        """Join the server's commits with ours when both sides have new ones: a merge commit, nothing rewritten."""
        self.git(root, ["pull", "--no-rebase", "--no-edit"], tr("git.merge_remote"), done, failed,
                 expected=stopped_on_conflicts)

    def merge_branch(self, root, branch, done, failed=None):
        """Merge another local branch into the current one."""
        self.git(root, ["merge", "--no-edit", branch], tr("git.merge_branch"), done, failed,
                 expected=stopped_on_conflicts)

    def switch(self, root, branch, done, failed=None):
        self.git(root, ["switch", "--", branch], tr("git.switch"), done, failed)

    def new_branch(self, root, name, done, failed=None):
        self.git(root, ["switch", "-c", name], tr("git.new_branch"), done, failed)

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
        if bad_name(name):
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

    def open(self, project):
        """The Git cell or the project menu: the Git panel for a repository, a way to start one otherwise."""
        if project.git is not None:
            from git_panel import GitPanel   # the panel imports this module
            panel = GitPanel(self, project, self.page)
            panel.exec()
            panel.deleteLater()
            return None
        menu = QMenu(self.page)
        call(menu.addAction, tr("git.not_repo")).setEnabled(False)
        menu.addSeparator()
        call(menu.addAction, tr("git.init")).triggered.connect(lambda: self.initialize(project.path))
        return menu

    def open_client(self, client, root):
        exe, arguments = client
        try:
            subprocess.Popen([exe, *arguments(root)], cwd=str(root), start_new_session=True)
        except OSError as error:
            self.page.warning(error)

    def initialize(self, path):
        def done(_):
            self.page.window.catalog.refresh()  # the Git column shows the new repository
        if self.page.confirm("git.confirm_init", path):
            self.run("git", ["init"], tr("git.init"), path, done)
