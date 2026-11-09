"""State-preserving localization and module-boundary regressions for seven apps."""
import ast
import datetime as dt
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / 'opt/equestria-os'
APPS = ('calc', 'calendar', 'clock', 'closer', 'color-picker', 'gpu', 'notes')
TMP = tempfile.TemporaryDirectory()
ENV = patch.dict(os.environ, {'XDG_CONFIG_HOME': TMP.name, 'XDG_DATA_HOME': TMP.name,
                             'XDG_CACHE_HOME': TMP.name, 'QT_QPA_PLATFORM': 'offscreen'})
ENV.start()
for name in APPS:
    sys.path.insert(0, str(BASE / f'equestria-{name}'))
    loc = Path(TMP.name) / f'equestria-{name}/locales'
    loc.mkdir(parents=True)
    (loc / 'xx_NEW.json').write_text(json.dumps({'_language_name': 'New file', 'window.theme': 'Extra theme'}))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QTabWidget, QTreeWidget, QTreeWidgetItem
MODS = {name: importlib.import_module('equestria_' + name.replace('-', '_')) for name in APPS}
APP = QApplication.instance() or QApplication([])


def package(name, module):
    return importlib.import_module('equestria_' + name.replace('-', '_') + '_app.' + module)


class ModularAppsTest(unittest.TestCase):
    def make_window(self, name):
        m, wmod = MODS[name], package(name, 'window')
        with ExitStack() as stack:
            stack.enter_context(patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False))
            stack.enter_context(patch.object(QTimer, 'singleShot'))
            if name == 'calc':
                return m.MainWindow(m.apply_theme(''), 0)
            if name == 'calendar':
                return m.MainWindow(m.Store())
            if name == 'clock':
                stack.enter_context(patch.object(wmod, 'SoundPlayer'))
                return m.MainWindow(m.Settings())
            if name == 'closer':
                stack.enter_context(patch.object(wmod, 'detect_backend', return_value=m.NoBackend()))
                stack.enter_context(patch.object(m.MainWindow, 'refresh'))
                return m.MainWindow(m.load_config())
            if name == 'gpu':
                stack.enter_context(patch.object(m.GpuPanel, 'refresh'))
                return m.MainWindow({'theme': m.DEFAULT_THEME})
            if name == 'notes':
                stack.enter_context(patch.object(wmod, 'global_dir', return_value=Path(TMP.name)/'notes'))
                return m.MainWindow(m.load_config())
            return m.MainWindow(m.load_config())

    def test_every_language_preserves_state(self):
        for name in APPS:
            with self.subTest(app=name):
                m = MODS[name]
                win = self.make_window(name)
                for timer in win.findChildren(QTimer):
                    timer.stop()
                central = win.centralWidget()
                if name == 'calc':
                    win.pages[0].expr = '123+456'
                    win.pages[3].inp.setText('12.5')
                    before = win.pages[3].out.text()
                elif name == 'calendar':
                    win.set_date(dt.date(2028, 2, 29))
                elif name == 'clock':
                    win.timer_tab.state = 'running'
                    win.timer_tab.end = 123456.0
                    win.sw_tab.base_ms = 9876.0
                    win.settings['alarms'] = [{'time': '12:34', 'days': [0, 4], 'label': 'My alarm', 'enabled': False, 'sound': ''}]
                elif name == 'color-picker':
                    win.color.load_hex('#12ABCD')
                    before = win.color.hex() if hasattr(win.color, 'hex') else dict(win.color.__dict__)
                    primary = win.book.primary
                elif name == 'notes':
                    path = Path(TMP.name)/'note.md'
                    path.write_text('# Test\n- [ ] preserved\n')
                    win._set_mode('source', save=False)
                    win.open_note(str(path))
                    win.editor.setPlainText('# Unsaved\n- [x] content\n')
                    win.save_timer.stop()
                    before = win.editor.toPlainText()
                self.assertIn('xx_NEW', m.catalog.languages)
                for code in m.catalog.languages:
                    box = win.language_combo
                    box.setCurrentIndex(box.findData(code))
                    box.activated.emit(box.currentIndex())
                    self.assertEqual(m.catalog.lang, code)
                    self.assertIs(win.centralWidget(), central)
                    if name == 'calc':
                        self.assertEqual(win.pages[0].expr, '123+456')
                        self.assertEqual(win.pages[3].out.text(), before)
                    elif name == 'calendar':
                        self.assertEqual(win.sel, dt.date(2028, 2, 29))
                    elif name == 'clock':
                        self.assertEqual(win.timer_tab.state, 'running')
                        self.assertEqual(win.timer_tab.end, 123456.0)
                        self.assertEqual(win.sw_tab.base_ms, 9876.0)
                        self.assertEqual(win.settings['alarms'][0]['label'], 'My alarm')
                        self.assertEqual(win.tabs.tabText(0), str(m.tr('common.alarm')))
                    elif name == 'color-picker':
                        now = win.color.hex() if hasattr(win.color, 'hex') else dict(win.color.__dict__)
                        self.assertEqual(now, before)
                        self.assertEqual(win.book.primary, primary)
                        self.assertGreater(win.list.count(), 0)
                    elif name == 'notes':
                        self.assertEqual(win.editor.toPlainText(), before)
                        self.assertTrue(win.dirty)
                        self.assertEqual(path.read_text(), '# Test\n- [ ] preserved\n')
                self.assertFalse(win.grab().isNull())
                if name == 'notes':
                    win.save_note()
                    self.assertEqual(path.read_text(), before)
                win.hide()
                win.deleteLater()

    def test_domain_behaviors(self):
        calc = MODS['calc']
        self.assertEqual(calc.evaluate('2+3*4', False), 14)
        self.assertAlmostEqual(calc.convert('units.temperature', 100, '°C', '°F'), 212)
        self.assertEqual(calc.date_diff(dt.date(2024, 2, 28), dt.date(2024, 3, 1))[0], 2)
        clock = MODS['clock']
        now = dt.datetime(2026, 11, 9, 12, 0)
        alarm = {'time': '11:00', 'enabled': True, 'days': [0]}
        self.assertEqual(clock.next_fire([alarm], now)[1], dt.datetime(2026, 11, 16, 11, 0))
        self.assertRegex(MODS['notes'].md_to_html('**bold**', MODS['notes'].THEME), '<(b|strong)>bold</(b|strong)>')

    def test_source_imports_form_acyclic_graph(self):
        for name in APPS:
            root = BASE / f'equestria-{name}' / ('equestria_'+name.replace('-', '_')+'_app')
            graph = {}
            for path in root.glob('*.py'):
                graph[path.stem] = {node.module for node in ast.parse(path.read_text()).body
                                    if isinstance(node, ast.ImportFrom) and node.level and node.module}
            def visit(module, chain):
                self.assertNotIn(module, chain, (name, chain, module))
                for child in graph.get(module, ()):
                    visit(child, chain + [module])
            for module in graph:
                visit(module, [])

    def test_tab_and_tree_binding_preserves_data(self):
        from equestria_kit import live_i18n
        catalog = MODS['clock'].catalog
        tabs, tree = QTabWidget(), QTreeWidget()
        from PyQt6.QtWidgets import QWidget
        page = QWidget()
        live_i18n.call(tabs.addTab, page, catalog.tr('common.timer'))
        live_i18n.call(tree.setHeaderLabels, [catalog.tr('window.settings')])
        item = live_i18n.call(QTreeWidgetItem, [catalog.tr('common.timer')])
        tree.addTopLevelItem(item)
        item.setSelected(True)
        for lang in ('ru', 'de', 'en'):
            catalog.set_language(lang)
            self.assertEqual(tabs.tabText(0), str(catalog.tr('common.timer')))
            self.assertEqual(item.text(0), str(catalog.tr('common.timer')))
            self.assertTrue(item.isSelected())
        tabs.deleteLater()
        tree.deleteLater()


def tearDownModule():
    ENV.stop()
    TMP.cleanup()

if __name__ == '__main__':
    unittest.main()
