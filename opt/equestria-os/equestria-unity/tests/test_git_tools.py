import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from git_tools import GitActions, web_remote
from jobs import Jobs

APP = QApplication.instance() or QApplication([])


class GitTests(unittest.TestCase):
    def test_host_links(self):
        for url in ("git@gitlab.com:group/sub/project.git", "ssh://git@gitlab.com/group/sub/project",
                    "https://gitlab.com/group/sub/project.git"):
            self.assertEqual(web_remote(url), "https://gitlab.com/group/sub/project")
        self.assertEqual(web_remote("https://github.com/acme/game.git"), "https://github.com/acme/game")
        self.assertEqual(web_remote("/tmp/bare"), "")

    def test_provider_picker(self):
        for provider, program, field in (("GitHub", "gh", "full_name"), ("GitLab", "glab", "path_with_namespace")):
            from PyQt6.QtWidgets import QWidget
            actions = GitActions(QWidget())
            with patch.object(actions, "run") as run, patch.object(actions, "clone") as clone:
                actions.repositories(provider)
                self.assertEqual(run.call_args.args[0], program)
                with patch("git_tools.QInputDialog.getItem", return_value=("group/game", True)):
                    run.call_args.kwargs["done"](json.dumps([{field: "group/game"}]).encode())
                clone.assert_called_once_with(program, "group/game")

    def test_branch_and_remote_are_read_from_git_files_and_clone_adds_project(self):
        from git_info import read_git
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work = root / "my game"
            remote = root / "origin.git"
            def git(*args):
                return subprocess.check_output(["git", *map(str, args)], stderr=subprocess.STDOUT)
            git("init", "-q", "-b", "develop", work)
            git("init", "--bare", "-q", "-b", "main", remote)
            git("-C", work, "remote", "add", "origin", "git@github.com:acme/game.git")
            project = work / "Unity" / "Game"   # a project in a subfolder of the repository
            project.mkdir(parents=True)
            info = read_git(project)
            self.assertEqual((info.root, info.branch), (work, "develop"))
            self.assertEqual(info.web, "https://github.com/acme/game")
            self.assertEqual(info.reviews, "https://github.com/acme/game/pulls")
            self.assertIsNone(read_git(root))
            page = SimpleNamespace(jobs=Jobs(None), window=Mock(), warning=Mock(), confirm=Mock(return_value=True),
                                   text=Mock(return_value="cloned game"), folder=Mock(return_value=str(root)),
                                   add_path=Mock())
            GitActions(page).clone(repo=str(remote))
            for _ in range(500):
                if not page.jobs.running:
                    break
                QTest.qWait(10)
            page.warning.assert_not_called()
            page.add_path.assert_called_once_with(root / "cloned game")
            self.assertEqual(read_git(root / "cloned game").remote, str(remote))
