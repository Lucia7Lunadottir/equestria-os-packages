"""QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -p test_live_i18n.py"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'equestria-qt-kit'))
# Isolate settings, data, catalog overrides and caches before importing applications.
TEMP = tempfile.TemporaryDirectory()
ENV = patch.dict(os.environ, {key: TEMP.name for key in
                             ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME')})
ENV.start()
for name in ('calc', 'calendar', 'recorder', 'unreal'):
    directory = Path(TEMP.name) / f'equestria-{name}' / 'locales'
    directory.mkdir(parents=True)
    (directory / 'zz_TEST.json').write_text(json.dumps({
        '_language_name': 'Extra language', 'window.theme': 'Test theme',
        'common.settings': 'Test settings', 'window.record': 'Test record'}))
    sys.path.insert(0, str(ROOT / f'equestria-{name}'))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QComboBox
from equestria_kit.live_i18n import Catalog, call
import equestria_calc as calc
import equestria_calendar as calendar
import equestria_recorder as recorder
from equestria_ue import store
from equestria_ue.kit import _catalog as unreal_catalog
from equestria_ue.ui.main_window import MainWindow as UnrealWindow

APP = QApplication.instance() or QApplication([])


def switch(window, catalog, code):
    box = window.language_combo
    box.setCurrentIndex(box.findData(code))
    box.activated.emit(box.currentIndex())
    assert catalog.lang == code


class LiveTranslationTests(unittest.TestCase):
    def test_new_file_and_saved_preference(self):
        for name in ('calc', 'calendar', 'recorder', 'unreal'):
            script = ROOT / f'equestria-{name}' / f'equestria_{name}.py'
            catalog = Catalog(f'equestria-{name}', script)
            self.assertIn('zz_TEST', catalog.languages)
            self.assertEqual(catalog.match('zz-test.UTF-8'), 'zz_TEST')
            catalog.set_language('zz_TEST')
            self.assertEqual(Catalog(f'equestria-{name}', script).lang, 'zz_TEST')
            self.assertEqual(str(catalog.tr('missing {}', 7)), 'missing 7')

    def test_bindings_dynamic_arguments_uppercase_and_combo_repopulation(self):
        catalog = calc.catalog
        catalog.set_language('ru')
        text = catalog.tr('window.theme')
        label = call(QLabel, text.upper())
        box = QComboBox()
        call(box.addItem, text, 'stable-id')
        events = []
        box.currentTextChanged.connect(events.append)
        catalog.set_language('en')
        self.assertEqual(label.text(), str(catalog.tr('window.theme')).upper())
        self.assertEqual(box.currentData(), 'stable-id')
        self.assertEqual(events, [])
        box.clear()
        box.addItem('user text', 'new-id')
        catalog.set_language('de')
        self.assertEqual(box.currentText(), 'user text')
        label.setText('external update')
        catalog.set_language('ru')
        self.assertEqual(label.text(), 'external update')
        label.deleteLater()
        box.deleteLater()

    def test_invalid_file_fallback_and_item_label(self):
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        with tempfile.TemporaryDirectory() as folder:
            here = Path(folder)
            (here / 'locales').mkdir()
            (here / 'locales/xx.json').write_text('{bad JSON')
            (here / 'locales/en.json').write_text(json.dumps({'Count {}': 'Count {}'}))
            (here / 'locales/zz.json').write_text(json.dumps({'Other': 'Other'}))
            with self.assertWarns(UserWarning):
                catalog = Catalog('test-invalid-locales', here / 'main.py')
            self.assertNotIn('xx', catalog.languages)
            catalog.set_language('zz', persist=False)
            self.assertEqual(str(catalog.tr('Count {}', 3)), 'Count 3')
            widget = QListWidget()
            item = call(QListWidgetItem, calc.catalog.tr('window.theme'))
            widget.addItem(item)
            item.setSelected(True)
            calc.catalog.set_language('de')
            self.assertEqual(item.text(), str(calc.catalog.tr('window.theme')))
            self.assertTrue(item.isSelected())
            widget.clear()
            calc.catalog.set_language('ru')  # deleted C++ items must not be updated
            widget.deleteLater()

    def test_calculator_preserves_all_pages_and_conversions(self):
        win = calc.MainWindow(calc.apply_theme(''), 3)
        pages = list(win.pages)
        converter = pages[3]
        converter.cat.setCurrentIndex(2)  # temperature
        converter.inp.setText('37.5')
        pages[0].expr = '123+456'
        pages[4].days.setText('42')
        result = converter.out.text()
        selected = (converter.cat.currentData(), converter.frm.currentData(), converter.to.currentData())
        for code in calc.catalog.languages:
            switch(win, calc.catalog, code)
            self.assertEqual(win.pages, pages)
            self.assertEqual(converter.out.text(), result)
            converter._update()
            self.assertEqual(converter.out.text(), result)
            self.assertEqual(selected, (converter.cat.currentData(), converter.frm.currentData(), converter.to.currentData()))
            self.assertEqual(pages[0].expr, '123+456')
            self.assertEqual(pages[4].days.text(), '42')
            self.assertTrue(any(b.text() == str(calc.tr('window.theme')) for b in win.findChildren(QPushButton)))
        self.assertFalse(win.grab().isNull())
        win.close()

    def test_calendar_preserves_date_reminders_and_open_editor(self):
        from equestria_calendar_app import window as calendar_window
        with patch.object(calendar_window.QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False), patch.object(QTimer, 'singleShot'):
            win = calendar.MainWindow(calendar.Store())
        win.tick_timer.stop()
        import datetime
        date = datetime.date(2027, 3, 15)
        win.set_date(date)
        book = win.book
        dialog = calendar.ReminderDialog(win, None, date)
        from PyQt6.QtWidgets import QLineEdit
        editor = dialog.findChildren(QLineEdit)[0]
        editor.setText('My unfinished reminder')
        for code in calendar.catalog.languages:
            switch(win, calendar.catalog, code)
            self.assertEqual(win.sel, date)
            self.assertIs(win.book, book)
            self.assertEqual(editor.text(), 'My unfinished reminder')
            self.assertEqual(win.view_btns['month'].text(), str(calendar.tr('window.month')))
            self.assertIn(str(calendar.MONTHS_G[2]), win.day_title.text())
        dialog.reject()
        win.quitting = True
        self.assertFalse(win.grab().isNull())
        win.close()

    def test_recorder_keeps_capture_player_and_recording_state(self):
        from equestria_recorder_app import playback as rec_playback, window as rec_window
        with patch.object(rec_playback, 'QAudioOutput'), patch.object(rec_playback, 'QMediaPlayer'), patch.object(rec_window, 'QMediaDevices'), patch.object(recorder.MainWindow, '_fill_devices'), patch.object(recorder.MainWindow, '_scan_folder'):
            win = recorder.MainWindow({'folder': TEMP.name}, recorder.apply_theme(''))
        source, playback, wav = object(), win.playback, object()
        win.capture.src, win.session.wav, win.session.frames = source, wav, 12345
        for state in ('rec', 'pause', 'idle'):
            win.session.state = state
            win._apply_state()
            for code in recorder.catalog.languages:
                switch(win, recorder.catalog, code)
                self.assertIs(win.capture.src, source)
                self.assertIs(win.session.wav, wav)
                self.assertIs(win.playback, playback)
                self.assertEqual(win.session.frames, 12345)
                self.assertEqual(win.session.state, state)
                key = {'rec': 'window.pause', 'pause': 'window.resume', 'idle': 'window.record'}[state]
                self.assertEqual(win.rec_btn.text(), str(recorder.tr(key)))
        win.capture.src = win.session.wav = None
        self.assertFalse(win.grab().isNull())
        win.close()

    def test_unreal_keeps_pages_inputs_store_and_jobs(self):
        with patch.object(store, 'HAVE_WEB', False), patch.object(UnrealWindow, 'reload_engines'), patch.object(UnrealWindow, 'set_tray'), patch.object(QTimer, 'singleShot'):
            win = UnrealWindow()
        pages, jobs, epic = dict(win.pages), win.jobs, win.store
        settings = win.pages['settings']
        settings.inst.setText('/tmp/unfinished engine path')
        win.pages['downloads'].log.setPlainText('build output')
        win.go('settings')
        for code in unreal_catalog.languages:
            win.lang.setCurrentIndex(win.lang.findData(code))
            win.lang.activated.emit(win.lang.currentIndex())
            self.assertEqual(win.pages, pages)
            self.assertIs(win.jobs, jobs)
            self.assertIs(win.store, epic)
            self.assertIs(win.stack.currentWidget(), settings)
            self.assertEqual(settings.inst.text(), '/tmp/unfinished engine path')
            self.assertEqual(win.pages['downloads'].log.toPlainText(), 'build output')
            self.assertEqual(win.nav['settings'].text(), str(unreal_catalog.tr('common.settings')))
        win._quitting = True
        self.assertFalse(win.grab().isNull())
        win.close()


def tearDownModule():
    ENV.stop()
    TEMP.cleanup()


if __name__ == '__main__':
    unittest.main()
