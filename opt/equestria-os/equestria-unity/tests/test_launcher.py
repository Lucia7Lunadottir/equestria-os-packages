import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import library
from equestria_unity import Launcher
from installs import version_key
from releases import ReleaseBrowser
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
        self.enterContext(patch.object(library, "HUB", self.root))
        self.enterContext(patch.object(library, "DEFAULT_ROOT", self.root / "Hub"))
        self.enterContext(patch.dict(os.environ, XDG_CONFIG_HOME=temp.name))
        (self.root / "projects-v1.json").write_text(json.dumps({"data": {str(self.project): {}}}))

    def test_launch_to_tray_only_on_success_with_available_host(self):
        from PyQt6.QtWidgets import QSystemTrayIcon
        window = Launcher(APP)
        self.addCleanup(window.close)
        window.config.data["close_to_tray"] = False
        window.show()
        project = library.Project(self.project, "6000.6.7f1", 0)
        with patch.object(library, "launch") as launch, patch.object(window.projects, "touch"), \
                patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True) as host:
            launch.return_value.args = ["Unity"]
            window.projects.start(self.editor, project)
            self.assertTrue(window.isVisible())
            window.config.data["editor_to_tray"] = True
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
        with patch("subprocess.Popen") as start, patch("jobs.executable", return_value=None):
            window = Launcher(APP)
            self.addCleanup(window.close)
            for _ in range(200):
                if not window.projects.scanning:
                    break
                QTest.qWait(10)
            window.projects.tree.setCurrentItem(window.projects.tree.topLevelItem(0))
            window.projects.open()
            args, kwargs = start.call_args
            self.assertEqual(args[0], [str(self.editor), "-projectPath", str(self.project)])
            self.assertEqual(kwargs["cwd"], self.project)
            self.assertTrue(kwargs["start_new_session"])
            self.assertFalse(window.jobs.running)

    def test_x11_create_and_renderer_affect_only_child(self):
        template = self.root / "3D URP.tgz"
        settings = {"editor_profiles": {str(self.editor): {"x11": True, "arguments": "-profiler-enable"}},
                    "renderer": "-force-vulkan", "arguments": '-logFile "log output"',
                    "project_arguments": {str(self.project): '-buildTarget Linux64'}}
        with patch.dict(os.environ, DISPLAY=":1", WAYLAND_DISPLAY="wayland-0"), patch("subprocess.Popen") as start:
            library.launch(self.editor, self.project, settings, create=True, template=template)
            args, kwargs = start.call_args
            self.assertEqual(args[0], [str(self.editor), "-createProject", str(self.project), "-cloneFromTemplate",
                                       str(template), "-force-vulkan", "-logFile", "log output", "-profiler-enable",
                                       "-buildTarget", "Linux64"])
            self.assertNotIn("WAYLAND_DISPLAY", kwargs["env"])
            self.assertEqual(kwargs["env"]["GDK_BACKEND"], "x11")
            self.assertEqual(os.environ["WAYLAND_DISPLAY"], "wayland-0")

            library.launch(self.root / "another-editor", self.root, settings)
            args, kwargs = start.call_args
            self.assertEqual(kwargs["env"]["WAYLAND_DISPLAY"], "wayland-0")
            self.assertNotIn("-profiler-enable", args[0])
            self.assertNotIn("-buildTarget", args[0])

    def test_release_button_text_fits_after_results_arrive(self):
        from PyQt6.QtWidgets import QPushButton, QStyle, QStyleOptionButton
        window = Launcher(APP)
        self.addCleanup(window.close)
        self.addCleanup(catalog.set_language, catalog.lang, persist=False)
        catalog.set_language("ru", persist=False)
        dialog = ReleaseBrowser([], window)
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
        dialog = ReleaseBrowser([], None)
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
        browser = ReleaseBrowser([], None)
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
        window = Launcher(APP)
        self.addCleanup(window.close)
        window.show()
        for _ in range(200):
            if not window.projects.scanning:
                break
            QTest.qWait(10)
        page = window.projects
        page.items = [library.Project(self.root / s, "", 0) for s in ("Zed", "Alpha")]
        page.config.data["favorites"] = [str(self.root / "Zed")]
        page.render()
        header = page.tree.header()
        point = QPoint(header.sectionViewportPosition(1) + 12, header.height() // 2)
        for name in ("Alpha", "Zed"):
            QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=point)
            self.assertEqual(Path(page.tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole)).name, name)

    def test_async_catalog_and_install_plan(self):
        window = Launcher(APP)
        self.addCleanup(window.close)
        cli = self.root / "unity"
        captured = self.root / "command"
        cli.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE\"\n"
                       "echo '{\"success\":true,\"data\":{\"items\":[{\"version\":\"6000.6.9f1\"}]}}'\n")
        cli.chmod(0o755)
        with patch("jobs.executable", return_value=str(cli)), patch.dict(os.environ, CAPTURE=str(captured)):
            with patch.object(window.installs, "pick_modules") as pick, patch.object(ReleaseBrowser, "exec", lambda dialog: (dialog.choose("6000.6.9f1") or 1)):
                window.installs.releases()
            pick.assert_called_once_with("6000.6.9f1", {}, review=True)
            self.assertEqual(window.installs.version.currentText(), "6000.6.9f1")
            window.installs.install("preview")
            self.wait_jobs(window)
            self.assertIn("--dry-run", captured.read_text().splitlines())
            self.assertNotIn("--accept-eula", captured.read_text())
            self.assertFalse(window.jobs.running)

    def test_install_needs_component_selection_and_final_consent(self):
        from install_plan import Components
        from PyQt6.QtCore import Qt
        window = Launcher(APP)
        self.addCleanup(window.close)
        page = window.installs
        version = "6000.7.0b9"
        page.version.setEditText(version)
        import platform
        arch = "ARM64" if platform.machine().lower() in ("arm64", "aarch64") else "X86_64"
        release = {"downloads": [{"platform": "LINUX", "architecture": arch, "modules": [
            {"id": "android", "name": "Android", "subModules": [{"id": "jdk-17+8", "name": "JDK"}]}]}]}
        def select(dialog):
            dialog.tree.topLevelItem(0).child(0).setCheckState(0, Qt.CheckState.Checked)
            return 1
        with patch.object(page.jobs, "run") as run:
            with patch.object(Components, "exec", return_value=0):
                page.pick_modules(version, release, review=True)
                run.assert_not_called()
            with patch.object(Components, "exec", select):
                page.pick_modules(version, release, review=True)
            plan = run.call_args.args
            self.assertIn("--dry-run", plan[2])
            self.assertIn("jdk-17+8", plan[2])
            self.assertIn("android", plan[2])
            result = {"totalDownloadSize": 1073741824, "modules": []}
            with patch.object(page, "confirm", return_value=False) as confirm:
                plan[3](result)
                self.assertIn("1.00 GiB", str(confirm.call_args.args[1]))
                self.assertEqual(run.call_count, 1)
            with patch.object(page, "confirm", return_value=True):
                plan[3](result)
                self.assertEqual(run.call_count, 2)
                self.assertNotIn("--dry-run", run.call_args.args[2])
                self.assertTrue(window.log.isChecked())

    def test_install_progress_is_visible_while_cli_runs(self):
        window = Launcher(APP)
        self.addCleanup(window.close)
        fake = self.root / "fake-cli"
        fake.write_text("#!/bin/sh\necho 'Downloading: 37%' >&2\nsleep 0.35\n")
        fake.chmod(0o755)
        seen = []
        window.jobs.progress.connect(lambda *_: seen.append(
            (window.busy.value(), window.notice.text(), window.busy.isHidden(), window.cancel.isHidden())))
        with patch("jobs.executable", return_value=str(fake)):
            window.jobs.run("install", "Unity 6.7", ["install", "test"])
            self.wait_jobs(window)
        self.assertEqual(seen, [(37, "Unity 6.7 · 37%", False, False)])

    def test_release_channels_and_archive(self):
        browser = ReleaseBrowser([], None)
        for tab, count in ((0, 1), (1, 1), (2, 3)):
            browser.tabs.setCurrentIndex(tab)
            browser.timer.stop()
            for version, stream in (("6000.6.9f1", "SUPPORTED"), ("6000.6.8f1", "SUPPORTED"),
                                    ("7000.0.0a16", "ALPHA"), (None, None)):
                browser.add_release({"version": version, "stream": stream})
            self.assertEqual(browser.rows.topLevelItemCount(), count)
        browser.deleteLater()

    def test_sample_selection_and_download_command(self):
        window = Launcher(APP)
        self.addCleanup(window.close)
        with patch.object(window.jobs, "run") as run:
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
        self.enterContext(patch.object(library, "executable", return_value=None))
        welcome = source.parent / "equestria-os-welcome-hub/locales"
        self.assertEqual({p.name for p in welcome.glob("*.json")},
                         {p.name for p in (source / "locales").glob("*.json")})
        window = Launcher(APP)
        self.addCleanup(window.close)
        self.addCleanup(catalog.set_language, catalog.lang, persist=False)
        settings = window.pages["settings"]
        box = settings.language_combo
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
                    self.assertEqual(window.projects.tree.headerItem().text(2), entries["projects.col_version"])
                    self.assertEqual(settings.retries.specialValueText(), entries["settings.default"])
                    self.assertEqual(window.new.about.text(), entries["new.empty_hint"])
                    self.assertEqual(window.new.name.text(), "My draft")
                    self.assertEqual(window.account.auth_view.toPlainText(), entries["cli.hint"])
                    self.assertEqual(json.loads(catalog.preference.read_text()), path.stem)

    def test_locale_bindings_and_release_order(self):
        window = Launcher(APP)
        self.addCleanup(window.close)
        for lang, expected in (("ru", "Проекты"), ("en", "Projects")):
            catalog.set_language(lang, persist=False)
            self.assertEqual(window.nav["projects"].text(), expected)
        self.assertEqual(catalog.translations["ru"].keys(), catalog.translations["en"].keys())
        self.assertGreater(version_key("6000.6.10f1"), version_key("6000.6.9f9"))
        self.assertGreater(version_key("6000.7.0f1"), version_key("6000.7.0b10"))


if __name__ == "__main__":
    unittest.main()
