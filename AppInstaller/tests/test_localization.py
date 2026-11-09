import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
TEMP = tempfile.TemporaryDirectory()
ENV = patch.dict(os.environ, {'XDG_CONFIG_HOME': TEMP.name, 'XDG_DATA_HOME': TEMP.name})
ENV.start()
for app in ('equestria-installer', 'equestria-os-welcome-hub'):
    loc = Path(TEMP.name) / app / 'locales'
    loc.mkdir(parents=True)
    (loc / 'xx_TEST.json').write_text(json.dumps({'_language_name': 'Added file', 'cat.music': 'Test music',
                                                'install_wizard.installation': 'Test installation'}))
sys.path.insert(0, str(ROOT / 'AppInstaller'))
sys.path.insert(0, str(ROOT / 'opt/equestria-os/equestria-os-welcome-hub'))
from PyQt6.QtWidgets import QApplication, QWizard
from PyQt6.QtCore import QProcess
import ui_common
import install_wizard as wizard
import welcome_hub as hub
APP = QApplication.instance() or QApplication([])


class LocalizationTests(unittest.TestCase):
    def test_installer_keeps_pages_selection_and_operations(self):
        with patch.object(QProcess, 'start') as start:
            win = wizard.InstallWizard()
            win.show()
            APP.processEvents()
            APP.processEvents()
            self.assertIsNone(win.sideWidget())
            self.assertGreater(win.language_combo.x(), win.width() // 2)
            self.assertLess(win.language_combo.y(), 60)
            self.assertGreater(win.page(0).width(), win.width() - 50)
            win.resize(860, 600)
            APP.processEvents()
            APP.processEvents()
            self.assertGreater(win.language_combo.x(), 700)
            win.package_path = '/tmp/selected.deb'
            pages = [win.page(i) for i in win.pageIds()]
            apps = win.page(wizard.PAGE_APPS)
            apps.packages = [wizard.InstalledPackage('Example', '1.0', 'deb', 'example', None)]
            apps._fill()
            item = apps.tree.topLevelItem(0)
            item.setSelected(True)
            apps.rb_remove.setChecked(True)
            check = object()
            apps._check = check
            install = win.page(wizard.PAGE_INSTALL)
            install.log_output.setPlainText('Existing installation output')
            self.assertIn('xx_TEST', ui_common.catalog.languages)
            for code in ui_common.catalog.languages:
                box = win.language_combo
                box.setCurrentIndex(box.findData(code))
                box.activated.emit(box.currentIndex())
                self.assertEqual(pages, [win.page(i) for i in win.pageIds()])
                self.assertEqual(win.package_path, '/tmp/selected.deb')
                self.assertIs(apps._check, check)
                self.assertIs(apps.tree.topLevelItem(0), item)
                self.assertTrue(item.isSelected())
                self.assertTrue(apps.rb_remove.isChecked())
                self.assertEqual(item.text(3), str(ui_common.tr('foreign_apps.no_source')))
                self.assertEqual(install.log_output.toPlainText(), 'Existing installation output')
                self.assertEqual(install.title(), str(ui_common.tr('install_wizard.installation')))
                self.assertEqual(install.subTitle(), str(ui_common.tr('install_wizard.installing_package_into_system')))
                self.assertEqual(win.buttonText(QWizard.WizardButton.NextButton), str(ui_common.tr('install_wizard.next')))
            start.assert_not_called()
            self.assertFalse(win.grab().isNull())
            apps._check = None
            win.close()

    def test_hub_keeps_category_cards_and_autostart(self):
        with patch.object(hub.main_app, 'AUTOSTART_PATH', str(Path(TEMP.name) / 'autostart.desktop')), \
             patch.object(hub.main_app, 'LEGACY_AUTOSTART_PATH', str(Path(TEMP.name) / 'legacy.desktop')), \
             patch.object(hub.subprocess, 'Popen') as launch:
            win = hub.main_app()
            win.show()
            APP.processEvents()
            win.nav_container.itemAt(1).widget().click()
            nav = [win.nav_container.itemAt(i).widget() for i in range(win.nav_container.count())]
            cards = [win.content_layout.itemAt(i).widget() for i in range(win.content_layout.count())]
            autostart = win.autostart_checkbox.isChecked()
            self.assertIn('xx_TEST', hub.catalog.languages)
            for code in hub.catalog.languages:
                box = win.lang_combo
                box.setCurrentIndex(box.findData(code))
                box.activated.emit(box.currentIndex())
                self.assertEqual(win.cat_title.text(), str(hub.catalog.tr('cat.music')))
                self.assertEqual(cards, [win.content_layout.itemAt(i).widget() for i in range(win.content_layout.count())])
                self.assertEqual(nav, [win.nav_container.itemAt(i).widget() for i in range(win.nav_container.count())])
                self.assertEqual(win.autostart_checkbox.isChecked(), autostart)
            launch.assert_not_called()
            self.assertFalse(win.grab().isNull())
            self.assertEqual(json.loads(hub.catalog.preference.read_text()), hub.catalog.lang)
            win.close()


def tearDownModule():
    ENV.stop()
    TEMP.cleanup()


if __name__ == '__main__':
    unittest.main()
