"""Прежние имена модуля equestria_recorder для внешних потребителей; внутри пакета не используется."""
from importlib import import_module

_EXPORTS = {
    'CONFIG': 'paths', 'DEFAULT_THEME': 'style', 'KEYS': 'style', 'LevelMeter': 'widgets',
    'MainWindow': 'window', 'QSS': 'style', 'THEME': 'style', 'THEMES': 'style', 'TrimDialog': 'trim_dialog',
    'Waveform': 'widgets', 'apply_theme': 'style', 'card': 'widgets', 'catalog': 'localization',
    'confirm': 'widgets', 'fmt_t': 'formatting', 'fmt_time': 'formatting', 'live_i18n': 'localization',
    'main': 'app', 'to_level': 'levels', 'tr': 'localization', 'wav_len': 'wav_clip',
}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_recorder_app.{module}"), name)
