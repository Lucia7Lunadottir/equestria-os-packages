"""Run with QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from audio_converter import window
from audio_converter.localization import catalog, load_catalog
from audio_converter.style import apply_theme, THEME


class LanguageSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_config = window.CONFIG
        self.old_language = catalog.lang
        window.CONFIG = Path(self.tmp.name) / 'equestria-converter/settings.json'
        catalog.lang = 'en'
        self.win = window.MainWindow({}, apply_theme(''))

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        self.app.processEvents()
        window.CONFIG = self.old_config
        catalog.lang = self.old_language
        self.tmp.cleanup()

    def switch(self, code):
        box = self.win.language_combo
        box.setCurrentIndex(box.findData(code))
        box.activated.emit(box.currentIndex())
        self.app.processEvents()

    def test_live_switch_preserves_input_and_video_arguments(self):
        w = self.win
        path = Path(self.tmp.name) / 'audio.wav'
        path.touch()
        w.add_files([str(path)])
        item = w.files.item(0)
        item.setSelected(True)
        w.audio.t_start.setText('0:12')
        w.audio.t_end.setText('broken input')
        w.audio.tag_edits['artist'].setText('Artist')
        w.audio.reverse.setChecked(True)
        w.audio.speed.setValue(0.63)
        w.video.res.setCurrentIndex(6)
        w.video.viz.setCurrentIndex(2)
        before = w.video.video_args(THEME, False)
        for language in ('ru', 'de', 'en'):
            self.switch(language)
            self.assertEqual(catalog.lang, language)
            self.assertEqual(w.go_btn.text(), catalog.tr('window.convert'))
            self.assertEqual(w.audio.fmt.itemText(w.audio.fmt.findData('flac')), catalog.tr('formats.flac_lossless'))
            self.assertEqual(w.video.video_args(THEME, False), before)
            self.assertIs(w.files.item(0), item)
            self.assertTrue(item.isSelected())
            self.assertEqual(w.audio.t_end.text(), 'broken input')
            self.assertEqual(w.audio.t_start.text(), '0:12')
            self.assertEqual(w.audio.tags()['artist'], 'Artist')
            self.assertTrue(w.audio.reverse.isChecked())
            self.assertEqual(w.audio.speed.value(), 0.63)
            self.assertEqual(window.load_config()['language'], language)

    def test_running_controls_and_item_references_survive(self):
        w = self.win
        w._running(True)
        w.bar.setValue(37)
        self.switch('ru')
        self.assertFalse(w.body.isEnabled())
        self.assertTrue(w.cancel_btn.isEnabled())
        self.assertEqual(w.bar.value(), 37)
        w._running(False)

    def test_old_translated_video_settings(self):
        w = self.win
        w.video.apply({'viz': catalog.translations['de']['video_options.wave'],
                       'res': catalog.translations['en']['common.1080_1920_vertical']})
        self.assertEqual(w.video.settings()['viz'], 'video_options.wave')
        self.assertEqual(w.video.video_args(THEME, False)['size'], (1080, 1920))

    def test_saved_language_is_loaded_on_next_launch(self):
        self.switch('ru')
        from unittest.mock import patch
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': self.tmp.name}):
            self.assertEqual(load_catalog().lang, 'ru')


if __name__ == '__main__':
    unittest.main()
