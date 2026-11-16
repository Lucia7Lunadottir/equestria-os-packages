import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QEventLoop, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import editor_launch
import unity_paths
from project_scanner import Project
from equestria_unity import Launcher
from versions import version_key
from releases import ReleaseList
from install_wizard import CONFIRM, MODULES, InstallWizard
from unity_cli import UnityCli
from release_info import ReleaseInfo
from kit import catalog

APP = QApplication.instance() or QApplication([])


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "Project with spaces"
        version_file = self.project / "ProjectSettings/ProjectVersion.txt"
        version_file.parent.mkdir(parents=True)
        version_file.write_text("m_EditorVersion: 6000.6.7f1\n")
        self.editor = self.root / "Hub/6000.6.7f1/Editor/Unity"
        self.editor.parent.mkdir(parents=True)
        self.editor.touch(mode=0o755)
        self.enterContext(patch.object(unity_paths, "HUB", self.root))
        self.enterContext(patch.object(unity_paths, "DEFAULT_ROOT", self.root / "Hub"))
        self.enterContext(patch.dict(os.environ, XDG_CONFIG_HOME=temp.name))
        (self.root / "projects-v1.json").write_text(json.dumps({"data": {str(self.project): {}}}))
        # No real Unity CLI in tests: each test that needs one gives its own fake.
        self.enterContext(patch.object(UnityCli, "executable", return_value=None))
        self.enterContext(patch.object(ReleaseInfo, "request"))  # no network in tests

    def fake_cli(self, reply, *, delay=0.0):
        """A Unity CLI that saves its arguments in self.captured and prints `reply`."""
        cli = self.root / "unity"
        self.captured = self.root / "command"
        cli.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{self.captured}'\nsleep {delay}\n"
                       f"echo '{json.dumps(reply)}'\n")
        cli.chmod(0o755)
        return patch.object(UnityCli, "executable", return_value=str(cli))

    def launcher(self):
        """A window that is really destroyed after the test: closed windows left alive keep restyling."""
        window = Launcher(APP)

        def destroy():
            window.close()
            window.deleteLater()
            QTest.qWait(1)
        self.addCleanup(destroy)
        return window

    def wait_scan(self, window):
        for _ in range(200):
            if not window.catalog.scanning:
                break
            QTest.qWait(10)

    def wait_idle(self, window):
        for _ in range(300):
            if not window.jobs.running and not window.jobs.waiting:
                break
            QTest.qWait(10)
        self.assertFalse(window.jobs.running)

    def test_launch_to_tray_only_on_success_with_available_host(self):
        from PyQt6.QtWidgets import QSystemTrayIcon
        window = self.launcher()
        window.config.set("close_to_tray", False)
        window.show()
        project = Project(self.project, "6000.6.7f1", 0)
        with patch.object(editor_launch, "launch") as launch, patch.object(window.catalog, "touch"), \
                patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True) as host:
            launch.return_value.args = ["Unity"]
            window.projects.start(self.editor, project)
            self.assertTrue(window.isVisible())
            window.config.set("editor_to_tray", True)
            host.return_value = False
            window.projects.start(self.editor, project)
            self.assertTrue(window.isVisible())
            host.return_value = True
            launch.side_effect = OSError("launch failed")
            with patch.object(window.projects, "warning"):
                window.projects.start(self.editor, project)
            self.assertTrue(window.isVisible())
            launch.side_effect = None
            window.projects.start(self.editor, project)
            self.assertTrue(window.isHidden())

    def test_open_without_cli_and_without_account(self):
        with patch("subprocess.Popen") as start:
            window = self.launcher()
            self.wait_scan(window)
            window.projects.table.setCurrentIndex(window.projects.table.model().index(0, 1))
            window.projects.open()
            args, kwargs = start.call_args
            self.assertEqual(args[0], [str(self.editor), "-projectPath", str(self.project)])
            self.assertEqual(kwargs["cwd"], self.project)
            self.assertTrue(kwargs["start_new_session"])
            self.assertFalse(window.jobs.running)

    def test_licenses_are_cards_from_the_cli_json(self):
        from account_views import LicenseCard
        from PyQt6.QtWidgets import QLabel
        window = self.launcher()
        personal = {"product": "Unity Personal", "type": "Assigned", "organization": "", "expires": ""}
        store = {"product": "Asset Store", "type": "Assigned", "organization": "", "expires": "2027-03-01"}
        reply = {"success": True, "data": {"loggedIn": True, "user": {"name": "Twilight Sparkle", "email": "t@e.q"},
                                           "active": True, "licenses": [personal, store, store]}}
        with self.fake_cli(reply):
            window.account_state.load()
            self.wait_idle(window)
        settings = window.pages["settings"]
        cards = settings.findChildren(LicenseCard)
        self.assertEqual(len(cards), 2)  # the repeated Asset Store license is one card with ×2
        texts = [[label.text() for label in card.findChildren(QLabel)] for card in cards]
        self.assertEqual(texts[0][0], "PE")
        self.assertIn("Unity Personal", texts[0])
        self.assertEqual(texts[1][0], "AS")
        self.assertIn("×2", texts[1])
        self.assertEqual(len(window.account.findChildren(LicenseCard)), 2)  # the same state on the Unity ID page
        self.assertEqual(window.account.profile.name.text(), "Twilight Sparkle")
        self.assertFalse(window.account.profile.status.isHidden())

    def test_table_cells_act_like_buttons(self):
        from project_table import GIT, MORE, NAME, STAR, VERSION
        window = self.launcher()
        window.show()
        self.wait_scan(window)
        page = window.projects
        table = page.table
        self.assertEqual(len(table.rows()), 1)
        cell = lambda column: table.visualRect(table.model().index(0, column)).center()
        click = lambda column: QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=cell(column))
        click(STAR)
        self.assertEqual(window.config.get("favorites"), [str(self.project)])
        self.assertTrue(table.rows()[0].starred)
        with patch.object(editor_launch, "launch") as launch:
            launch.return_value.args = ["Unity"]
            click(NAME)
        self.assertEqual(launch.call_args.args[1], self.project)
        with patch("projects.QMenu.exec") as shown:   # one class: the version, ⋯ and Git menus
            click(VERSION)
            click(MORE)
            click(GIT)
        self.assertEqual(shown.call_count, 3)

    def test_packages_are_read_from_the_project_files(self):
        from project_packages import ProjectPackages
        packages = self.project / "Packages"
        packages.mkdir()
        (packages / "manifest.json").write_text(json.dumps({"dependencies": {
            "com.unity.cinemachine": "3.1.0", "com.example.new": "1.0.0"}}))
        (packages / "packages-lock.json").write_text(json.dumps({"dependencies": {
            "com.unity.cinemachine": {"version": "3.1.0", "depth": 0, "source": "registry"},
            "com.unity.splines": {"version": "2.6.0", "depth": 1, "source": "registry"}}}))
        cache = self.project / "Library/PackageCache/com.unity.cinemachine@abc"
        cache.mkdir(parents=True)
        (cache / "package.json").write_text(json.dumps({"displayName": "Cinemachine"}))
        entries = {e.identifier: e for e in ProjectPackages(self.project).entries()}
        self.assertEqual(entries["com.unity.cinemachine"].title, "Cinemachine")
        self.assertTrue(entries["com.unity.cinemachine"].direct)
        self.assertFalse(entries["com.unity.splines"].direct)          # only a dependency
        self.assertEqual(entries["com.example.new"].source, "")         # not resolved by the Editor yet
        window = self.launcher()
        self.wait_scan(window)
        window.go("packages")
        for _ in range(200):
            if window.packages.table.topLevelItemCount():
                break
            QTest.qWait(10)
        self.assertEqual(window.packages.table.topLevelItemCount(), 2)   # dependencies hidden by default
        window.packages.all.setChecked(True)
        self.assertEqual(window.packages.table.topLevelItemCount(), 3)

    def test_unity_registry_comes_from_the_editor_and_adds_to_manifest(self):
        from project_packages import EditorPackageCatalog, ProjectPackages
        manager = self.editor.parent / "Data/Resources/PackageManager"
        (manager / "Editor").mkdir(parents=True)
        (manager / "Editor/manifest.json").write_text(json.dumps({"packages": {
            "com.unity.cinemachine": {"isDiscoverable": True, "version": "3.1.4"},
            "com.unity.shadergraph": {"isDiscoverable": True, "version": "17.6.0"},
            "com.unity.sentis": {"deprecated": "Use com.unity.ai.inference instead."},
            "com.unity.hidden": {"version": "1.0.0"}}}))
        (manager / "BuiltInPackages/com.unity.shadergraph").mkdir(parents=True)
        (manager / "BuiltInPackages/com.unity.shadergraph/package.json").write_text(
            json.dumps({"displayName": "Shader Graph", "description": "Build shaders visually."}))
        catalog = EditorPackageCatalog(self.editor, self.root / "cache")
        entries = {e.identifier: e for e in catalog.entries()}
        self.assertEqual(set(entries), {"com.unity.cinemachine", "com.unity.shadergraph"})
        self.assertEqual(entries["com.unity.shadergraph"].title, "Shader Graph")
        self.assertEqual(entries["com.unity.cinemachine"].title, "Cinemachine")
        self.assertTrue((self.root / "cache" / "packages-6000.6.7f1.json").is_file())   # read once per Editor
        manifest = self.project / "Packages/manifest.json"
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({"dependencies": {"com.unity.ugui": "2.0.0"}}, indent=2))
        ProjectPackages(self.project).add("com.unity.cinemachine", "3.1.4")
        self.assertEqual(list(json.loads(manifest.read_text())["dependencies"]),
                         ["com.unity.ugui", "com.unity.cinemachine"])   # the order of the file is kept

    def test_a_hanging_cli_is_stopped_and_explained(self):
        window = self.launcher()
        cli = self.root / "hanging-unity"
        cli.write_text("#!/bin/sh\nexec sleep 60\n")
        cli.chmod(0o755)
        reasons = []
        with patch.object(UnityCli, "executable", return_value=str(cli)):
            window.cli.run("templates:x", "Templates", ["templates"], structured=True, failed=reasons.append,
                           timeout=1)
            for _ in range(600):
                if not window.jobs.running:
                    break
                QTest.qWait(10)
        self.assertFalse(window.jobs.running)
        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0].code, "TIMEOUT")
        self.assertIn("1", str(reasons[0]))

    def test_signed_out_is_a_state_and_offline_is_explained(self):
        window = self.launcher()
        cli = self.root / "offline-unity"
        replies = {"auth": {"success": False, "data": {"loggedIn": False}, "errors": [
                       {"code": "NOT_SIGNED_IN", "message": "You are not signed in."}]},
                   "license": {"success": False, "data": None, "errors": [
                       {"code": "LICENSING_CLIENT_UNAVAILABLE", "message": "Cannot reach the Unity licensing client."}]}}
        cli.write_text("#!/bin/sh\nfor a; do last2=$prev; prev=$a; done\n"
                       f"if [ \"$last2\" = auth ]; then echo '{json.dumps(replies['auth'])}'; exit 3; fi\n"
                       f"echo '{json.dumps(replies['license'])}'; exit 6\n")
        cli.chmod(0o755)
        with patch.object(UnityCli, "executable", return_value=str(cli)):
            window.account_state.load()
            self.wait_idle(window)
        state = window.account_state
        self.assertFalse(state.signed_in())
        self.assertIsNone(state.problems["auth"])                    # not signed in is not an error
        self.assertEqual(str(state.problems["license"]), str(catalog.tr("cli.err.licensing")))
        self.assertTrue(window.account.profile.problem.isHidden())

    def test_git_panel_commits_and_sends_in_plain_steps(self):
        import subprocess
        from git_info import read_git_with_status
        from git_panel import GitPanel
        from git_tools import explain_git
        def git(*args):
            return subprocess.check_output(["git", *map(str, args)], stderr=subprocess.STDOUT).decode().strip()
        remote = self.root / "server.git"
        work = self.root / "repo"
        git("init", "--bare", "-q", "-b", "main", remote)
        git("clone", "-q", remote, work)
        git("-C", work, "config", "user.email", "pony@example.invalid")
        git("-C", work, "config", "user.name", "Pony")
        game = work / "Game"
        (game / "ProjectSettings").mkdir(parents=True)
        (game / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.6.7f1\n")
        git("-C", work, "add", ".")
        git("-C", work, "commit", "-q", "-m", "start")
        git("-C", work, "push", "-q", "-u", "origin", "main")
        (game / "[new] scene.unity").write_text("data")
        window = self.launcher()
        project = Project(game, "6000.6.7f1", 0, read_git_with_status(game))
        self.assertEqual(len(project.git.status.changes), 1)
        panel = GitPanel(window.projects.git_tools, project, window.projects)
        self.addCleanup(panel.deleteLater)
        settle = lambda: [QTest.qWait(20) for _ in range(150) if panel.busy or window.jobs.running
                          or window.projects.workers]
        settle()
        self.assertEqual(panel.changes.count(), 1)
        self.assertFalse(panel.commit_button.isEnabled())            # a message is needed
        panel.message.setText("Add a scene")
        self.assertTrue(panel.commit_button.isEnabled())
        panel.commit()
        settle()
        self.assertEqual(git("-C", work, "log", "-1", "--format=%s"), "Add a scene")
        self.assertEqual(panel.info.status.ahead, 1)
        self.assertTrue(panel.push_button.isEnabled())
        with patch.object(window.projects, "confirm", return_value=True):
            panel.push()
            settle()
        self.assertEqual(git("-C", remote, "rev-parse", "main"), git("-C", work, "rev-parse", "HEAD"))
        self.assertEqual(panel.info.status.ahead, 0)
        self.assertEqual(str(explain_git("fatal: Author identity unknown")), str(catalog.tr("git.err.identity")))

    def test_x11_create_and_renderer_affect_only_child(self):
        template = self.root / "3D URP.tgz"
        settings = {"editor_profiles": {str(self.editor): {"x11": True, "arguments": "-profiler-enable"}},
                    "renderer": "-force-vulkan", "arguments": '-logFile "log output"',
                    "project_arguments": {str(self.project): '-buildTarget Linux64'}}
        with patch.dict(os.environ, DISPLAY=":1", WAYLAND_DISPLAY="wayland-0"), patch("subprocess.Popen") as start:
            editor_launch.launch(self.editor, self.project, settings, create=True, template=template)
            args, kwargs = start.call_args
            self.assertEqual(args[0], [str(self.editor), "-createProject", str(self.project), "-cloneFromTemplate",
                                       str(template), "-force-vulkan", "-logFile", "log output", "-profiler-enable",
                                       "-buildTarget", "Linux64"])
            self.assertNotIn("WAYLAND_DISPLAY", kwargs["env"])
            self.assertEqual(kwargs["env"]["GDK_BACKEND"], "x11")
            self.assertEqual(os.environ["WAYLAND_DISPLAY"], "wayland-0")

            editor_launch.launch(self.root / "another-editor", self.root, settings)
            args, kwargs = start.call_args
            self.assertEqual(kwargs["env"]["WAYLAND_DISPLAY"], "wayland-0")
            self.assertNotIn("-profiler-enable", args[0])
            self.assertNotIn("-buildTarget", args[0])

    def test_release_button_text_fits_after_results_arrive(self):
        from PyQt6.QtWidgets import QPushButton, QStyle, QStyleOptionButton
        window = self.launcher()
        self.addCleanup(catalog.set_language, catalog.lang, persist=False)
        catalog.set_language("ru", persist=False)
        dialog = ReleaseList([])
        self.addCleanup(dialog.close)
        dialog.timer.stop()
        dialog.show()
        APP.processEvents()
        dialog.add_release({"version": "6000.6.9f1", "releaseNotes": {"url": "https://unity.com"}})
        for width in (880, 1200):
            dialog.resize(width, 560)
            APP.processEvents()
            cell = dialog.rows.itemWidget(dialog.rows.topLevelItem(0), 4)
            buttons = cell.findChildren(QPushButton)
            self.assertEqual(len(buttons), 2)
            for button in buttons:
                option = QStyleOptionButton()
                button.initStyleOption(option)
                content = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
                self.assertGreaterEqual(content.width(), button.fontMetrics().horizontalAdvance(button.text()) + 16)
                self.assertTrue(button.visibleRegion().contains(button.rect()))

    def test_notes_open_version_page_in_browser(self):
        from PyQt6.QtWidgets import QPushButton
        dialog = ReleaseList([])
        self.addCleanup(dialog.close)
        for tab, version, section, notes in (
            (0, "6000.0.1f1", "whats-new", {"url": "https://example.org/notes.md"}),
            (1, "6000.0.0b16", "beta", None),
            (2, "7000.0.0a16", "alpha", None),
        ):
            dialog.tabs.setCurrentIndex(tab)
            dialog.timer.stop()
            dialog.add_release({"version": version, "stream": "BETA" if tab == 1 else "", "releaseNotes": notes})
            cell = dialog.rows.itemWidget(dialog.rows.topLevelItem(0), 4)
            button = cell.findChild(QPushButton, "releaseNotes")
            with patch("releases.QDesktopServices.openUrl", return_value=True) as opener:
                button.click()
            opener.assert_called_once()
            self.assertEqual(opener.call_args.args[0].toString(), f"https://unity.com/releases/editor/{section}/{version}")
            self.assertEqual(dialog.selected, "")

    def test_release_sort_is_numeric(self):
        from PyQt6.QtCore import Qt
        browser = ReleaseList([])
        browser.tabs.setCurrentIndex(2)
        browser.timer.stop()
        for version in ("6000.6.9f1", "6000.6.10f1"):
            browser.add_release({"version": version})
        for order, expected in ((Qt.SortOrder.AscendingOrder, "6000.6.9f1"),
                                (Qt.SortOrder.DescendingOrder, "6000.6.10f1")):
            browser.rows.sortByColumn(0, order)
            self.assertIn(expected, browser.rows.topLevelItem(0).text(0))
        browser.deleteLater()

    def test_project_header_sorts_across_favorites(self):
        from PyQt6.QtCore import Qt, QPoint
        window = self.launcher()
        window.show()
        self.wait_scan(window)
        page = window.projects
        window.catalog.items = [Project(self.root / s, "", 0) for s in ("Zed", "Alpha")]
        page.config.set("favorites", [str(self.root / "Zed")])
        header = page.table.header()
        first = lambda: page.table.rows()[0].project.name
        point = QPoint(header.sectionViewportPosition(1) + 12, header.height() // 2)
        for name in ("Alpha", "Zed"):
            QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=point)
            self.assertEqual(first(), name)
        # The star column is a valid sort too: it used to be rejected by the settings store with an error.
        errors = []
        window.config.failed.connect(errors.append)
        star = QPoint(header.sectionViewportPosition(0) + 12, header.height() // 2)
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=star)
        self.assertEqual(errors, [])
        self.assertEqual(window.config.get("sort_key"), "favorite")
        self.assertEqual(first(), "Zed")

    def test_wizard_plans_with_the_cli_before_installing(self):
        import platform
        from PyQt6.QtCore import Qt
        window = self.launcher()
        arch = "ARM64" if platform.machine().lower() in ("arm64", "aarch64") else "X86_64"
        release = {"downloads": [{"platform": "LINUX", "architecture": arch, "modules": [
            {"id": "android", "name": "Android", "subModules": [{"id": "jdk-17+8", "name": "JDK"}]}]}]}
        reply = {"success": True, "data": {"totalDownloadSize": 1073741824, "modules": []}}
        with self.fake_cli(reply):
            wizard = InstallWizard(window.cli, window.editors, window.installs.tasks, window)
            self.addCleanup(wizard.deleteLater)
            wizard.releases.timer.stop()
            wizard.releases.choose("6000.7.0b9", release)
            self.assertEqual(wizard.step(), MODULES)
            self.assertTrue(wizard.forward.isEnabled())
            wizard.tree.topLevelItem(0).child(0).setCheckState(0, Qt.CheckState.Checked)  # checks its platform too
            wizard.next()
            self.assertEqual(wizard.step(), CONFIRM)
            self.assertFalse(wizard.forward.isEnabled())  # nothing is installed before the plan is known
            self.wait_idle(window)
            plan = self.captured.read_text().splitlines()
            self.assertIn("--dry-run", plan)
            self.assertIn("android", plan)
            self.assertIn("jdk-17+8", plan)
            self.assertNotIn("--accept-eula", plan)
            self.assertIn("1.00 GiB", wizard.summary.text())
            self.assertTrue(wizard.forward.isEnabled())
            with patch.object(window.cli, "install") as install:
                wizard.next()
            install.assert_called_once()
            self.assertEqual(install.call_args.args, ("6000.7.0b9", ["android", "jdk-17+8"]))
            self.assertEqual(install.call_args.kwargs["installed"], False)
            self.assertEqual(wizard.result(), wizard.DialogCode.Accepted)

    def test_wizard_adds_modules_to_installed_editor_only_when_some_are_chosen(self):
        window = self.launcher()
        reply = {"success": True, "data": {"items": [{"id": "android", "name": "Android", "isInstalled": True},
                                                     {"id": "webgl", "name": "Web"}]}}
        with self.fake_cli(reply):
            wizard = InstallWizard(window.cli, window.editors, window.installs.tasks, window, version="6000.6.7f1")
            self.addCleanup(wizard.deleteLater)
            self.assertTrue(wizard.installed)
            self.assertFalse(wizard.back.isVisible() and not wizard.back.isHidden())
            self.wait_idle(window)
            self.assertIn("--list", self.captured.read_text().splitlines())
            self.assertEqual(wizard.tree.topLevelItemCount(), 2)
            wizard.next()
            self.assertEqual(wizard.step(), MODULES)
            self.assertEqual(wizard.status.text(), str(catalog.tr("install.no_modules")))

    def test_install_progress_is_visible_while_cli_runs(self):
        window = self.launcher()
        fake = self.root / "fake-cli"
        fake.write_text("#!/bin/sh\necho 'Downloading: 37%' >&2\nsleep 0.35\n")
        fake.chmod(0o755)
        seen = []
        window.pill.operations.popup(window.pill)
        self.addCleanup(window.pill.operations.hide)
        window.jobs.progress.connect(lambda key, _: seen.append(
            (window.pill.busy.value(), window.pill.notice.text(), window.pill.busy.isHidden(), window.pill.cancel.isHidden(),
             window.pill.operations.bars[key][0].value())))
        with patch.object(UnityCli, "executable", return_value=str(fake)):
            window.cli.run("install", "Unity 6.7", ["install", "test"], progress=True)
            self.wait_idle(window)
        self.assertEqual(seen, [(37, "Unity 6.7 · 37%", False, False, 37)])

    def test_second_install_waits_in_the_queue(self):
        window = self.launcher()
        with self.fake_cli({"success": True, "data": {}}, delay=0.2):
            window.cli.install("6000.6.8f1", [], installed=False, eula=False)
            window.cli.install("6000.6.9f1", ["webgl"], installed=False, eula=False)
            self.assertEqual(len(window.jobs.waiting), 1)
            self.assertTrue(window.jobs.busy())
            self.wait_idle(window)
        self.assertEqual([ok for _, ok, _ in window.jobs.history], [True, True])
        self.assertIn("6000.6.9f1", self.captured.read_text())  # the queued one ran last

    def test_editor_operations_do_not_block_each_other(self):
        window = self.launcher()
        with patch.object(UnityCli, "executable", return_value="/bin/true"), \
                patch.object(window.jobs, "run_process") as start:
            window.cli.install("6000.6.9f1", [], installed=False, eula=False)
            window.cli.uninstall("6000.6.7f1")
            window.cli.set_install_path(str(self.root))
        keys = [call.args[0] for call in start.call_args_list]
        self.assertEqual(len(set(keys)), 3)

    def test_release_channels_and_archive(self):
        browser = ReleaseList([])
        for tab, count in ((0, 1), (1, 1), (2, 3)):
            browser.tabs.setCurrentIndex(tab)
            browser.timer.stop()
            for version, stream in (("6000.6.9f1", "SUPPORTED"), ("6000.6.8f1", "SUPPORTED"),
                                    ("7000.0.0a16", "ALPHA"), (None, None)):
                browser.add_release({"version": version, "stream": stream})
            self.assertEqual(browser.rows.topLevelItemCount(), count)
        browser.deleteLater()

    def test_sample_selection_and_download_command(self):
        window = self.launcher()
        with patch.object(window.cli, "run") as run:
            window.templates.templates("sample")
            page = window.new
            page.fill_remote(page.loaded, {"items": [
                {"name": "com.unity.template.sample", "displayName": "Demo", "type": "SAMPLE"},
                {"name": "com.unity.template.3d", "type": "CORE"}]})
            self.assertEqual(page.grid.count(), 1)
            self.assertIn("Demo", page.grid.item(0).text())
            page.location.setText(str(self.root))
            page.name.setText("Example")
            page.create()
            args = run.call_args.args[2]
            self.assertEqual(args[args.index("--template") + 1], "com.unity.template.sample")
            page.search.setText("no such match")
            self.assertFalse(page.make.isEnabled())
            for _ in range(200):
                if not any(p.workers for p in window.pages.values()):
                    break
                QTest.qWait(10)

    def wait_jobs(self, window):
        loop = QEventLoop()
        window.jobs.activity.connect(loop.quit)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        self.assertFalse(window.jobs.running)

    def test_language_dropdown_matches_welcome_hub(self):
        source = Path(__file__).resolve().parents[1]
        self.enterContext(patch.object(unity_paths, "executable", return_value=None))
        welcome = source.parent / "equestria-os-welcome-hub/locales"
        self.assertEqual({p.name for p in welcome.glob("*.json")},
                         {p.name for p in (source / "locales").glob("*.json")})
        window = self.launcher()
        self.addCleanup(catalog.set_language, catalog.lang, persist=False)
        settings = window.pages["settings"]
        box = settings.find("settings.appearance").language_combo
        window.new.merge()
        window.new.name.setText("My draft")
        with patch.object(catalog, "preference", self.root / "language.json"):
            for path in welcome.glob("*.json"):
                with self.subTest(language=path.stem):
                    entries = json.loads((source / "locales" / path.name).read_text())
                    self.assertEqual(entries.keys(), catalog.translations["en"].keys())
                    index = box.findData(path.stem)
                    self.assertGreaterEqual(index, 0)
                    self.assertEqual(box.itemText(index), json.loads(path.read_text())["_language_name"])
                    box.setCurrentIndex(index)
                    box.activated.emit(index)
                    self.assertEqual(window.nav["projects"].text(), entries["nav.projects"])
                    self.assertEqual(window.projects.table.model().headerData(3, Qt.Orientation.Horizontal), entries["projects.col_version"])
                    self.assertEqual(settings.find("settings.installs").retries.specialValueText(), entries["settings.retries_default"])
                    self.assertEqual(window.new.about.text(), entries["new.empty_hint"])
                    self.assertEqual(window.new.name.text(), "My draft")
                    self.assertEqual(window.account.profile.problem.text(), entries["cli.hint"])
                    self.assertEqual(json.loads(catalog.preference.read_text()), path.stem)

    def test_locale_bindings_and_release_order(self):
        window = self.launcher()
        for lang, expected in (("ru", "Проекты"), ("en", "Projects")):
            catalog.set_language(lang, persist=False)
            self.assertEqual(window.nav["projects"].text(), expected)
        self.assertEqual(catalog.translations["ru"].keys(), catalog.translations["en"].keys())
        self.assertGreater(version_key("6000.6.10f1"), version_key("6000.6.9f9"))
        self.assertGreater(version_key("6000.7.0f1"), version_key("6000.7.0b10"))


if __name__ == "__main__":
    unittest.main()
