import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from logwatch import APP_ID, QApplication, QSS, Window, kit_qt

APP = QApplication.instance() or QApplication([])


class FiltersTest(unittest.TestCase):
    def test_refilter_existing_rows_and_follow_new_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, XDG_CONFIG_HOME=folder):
            path = Path(folder) / "Editor.log"
            path.write_text('warning: alpha\nCompiling shader "Ice"\nerror: ALPHA\nerror: beta\n')
            cfg = kit_qt.JsonConfig(APP_ID, {"hide_shader_lines": True})
            window = Window(str(path), cfg, kit_qt.ThemeManager(APP, QSS))
            self.addCleanup(window.close)
            view = window.log_view

            def rows():
                return [view.lines.item(i).text() for i in range(view.lines.count())]

            self.assertEqual(rows(), ["warning: alpha", "error: ALPHA", "error: beta"])
            view.mode.setCurrentIndex(view.mode.findData("shader"))
            self.assertEqual(rows(), ['Compiling shader "Ice"'])
            view.mode.setCurrentIndex(view.mode.findData("error"))
            view.query.setText("AlPhA")
            self.assertEqual(rows(), ["error: ALPHA"])
            view.count.setValue(2)
            view.enabled.setChecked(False)
            self.assertEqual(rows(), ["error: ALPHA", "error: beta"])
            view.enabled.setChecked(True)
            self.assertEqual(rows(), ["error: ALPHA"])
            with path.open("a") as stream:
                stream.write("error: alpha two\nerror: alpha three\n")
            window.tick()
            self.assertEqual(rows(), ["error: alpha two", "error: alpha three"])
            view.count.setValue(3)
            self.assertEqual(len(rows()), 3)
            saved = kit_qt.JsonConfig(APP_ID).data
            self.assertEqual((saved["filter_enabled"], saved["filter_mode"], saved["line_count"]), (True, "error", 3))
            path.write_text("warning: new file\n")
            window.tick()
            self.assertEqual(rows(), [])
            view.enabled.setChecked(False)
            self.assertEqual(rows(), ["warning: new file"])
