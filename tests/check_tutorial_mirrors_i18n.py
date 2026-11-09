"""Run each app in an isolated process: python check_tutorial_mirrors_i18n.py APP_ID."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

app_id = sys.argv[1]
base = Path(__file__).resolve().parents[1] / 'opt/equestria-os' / app_id
with tempfile.TemporaryDirectory() as temporary:
    os.environ.update(QT_QPA_PLATFORM='offscreen', XDG_CONFIG_HOME=temporary + '/config', XDG_DATA_HOME=temporary + '/data')
    extra = Path(temporary) / 'data' / app_id / 'locales'
    extra.mkdir(parents=True)
    data = json.loads((base / 'locales/en.json').read_text())
    data.update({key: 'TEST ' + value for key, value in data.items()})
    (extra / 'eo.json').write_text(json.dumps(data))
    sys.path.insert(0, str(base))
    import main
    from localization import catalog, tr
    from PyQt6.QtWidgets import QApplication
    app = QApplication([])
    with patch.object(main.subprocess, 'run', side_effect=AssertionError('Unexpected external command')), patch.object(main.subprocess, 'Popen', side_effect=AssertionError('Unexpected launch')):
        if app_id == 'equestria-os-tutorial':
            with patch.object(main.TutorialApp, '_autostart_enabled', return_value=True):
                window = main.TutorialApp()
            window.current_slide = len(window.slides_config) - 1
            window.update_navigation_state()
            pages = [window.content_area.widget(i) for i in range(window.content_area.count())]
        else:
            with patch.object(main.main_app, 'load_data'), patch.object(main.main_app, '_check_timer_state'):
                window = main.main_app()
            window.on_countries_loaded([dict(name='Germany', code='DE', mirrors=3), dict(name='France', code='FR', mirrors=2)], '')
            window.search_field.setText('Germany')
            row = window.countries_layout.itemAt(0).widget()
            row.checkbox.setChecked(True)
            window.set_loading(True, tr('ranking'))
            window.btn_apply.setEnabled(False)
            window.on_mirrors_loaded(tr('no_mirrors'))
        assert 'eo' in catalog.languages
        assert window.lang_combo.findData('eo') >= 0
        window.show()
        for code in list(catalog.languages) + ['ru', 'en', 'eo', 'ru']:
            index = window.lang_combo.findData(code)
            window.lang_combo.setCurrentIndex(index)
            window.lang_combo.activated.emit(index)
            app.processEvents()
            assert catalog.lang == code
            if app_id == 'equestria-os-tutorial':
                assert window.btn_next.text() == str(tr('btn_close'))
                assert window.logo_label.text() == str(tr('app_title'))
                for slide in window.slides_data:
                    assert slide['text_widget'].text() == str(tr(slide['text_key']))
                    assert slide['title_widget'].text() == str(tr(slide['title_key']))
                assert window.content_area.currentIndex() == len(pages) - 1
                assert pages == [window.content_area.widget(i) for i in range(len(pages))]
                assert window.autostart_checkbox.isChecked()
            else:
                assert window.countries_layout.itemAt(0).widget() is row
                assert row.lbl_mirrors.text() == str(tr('mirrors_count', 3))
                assert window.lbl_selected_count.text() == str(tr('selected_count', 1))
                assert window.lbl_current_mirrors.text() == str(tr('no_mirrors'))
                assert window.lbl_loading.text() == str(tr('ranking'))
                assert window.search_field.text() == 'Germany'
                assert window.selected_codes == {'DE'}
                assert not window.btn_apply.isEnabled()
        window.grab().save('/tmp/' + app_id + '-localized.png')
        assert json.loads(catalog.preference.read_text()) == 'ru'
        print(app_id, ': PASS,', len(catalog.languages), 'languages, state and bindings preserved')
        window.close()
