"""Compatibility exports for existing embedded consumers; new code imports concrete modules."""
from importlib import import_module

_EXPORTS = {'ALL_THEMES': 'style', 'APP_NAME': 'paths', 'AlarmDialog': 'dialogs', 'AlarmRow': 'alarms', 'AlarmTab': 'alarms', 'BUILTIN_SOUNDS': 'sound', 'CACHE_DIR': 'paths', 'CONFIG_DIR': 'paths', 'DAYS_SHORT': 'schedule', 'DEFAULT_SETTINGS': 'settings', 'DEFAULT_THEME': 'style', 'MONTHS': 'schedule', 'MainWindow': 'window', 'PadSpin': 'widgets', 'QSS': 'style', 'RingDialog': 'dialogs', 'RingWidget': 'widgets', 'Settings': 'settings', 'SettingsTab': 'settings_page', 'SoundPicker': 'widgets', 'SoundPlayer': 'sound', 'StopwatchTab': 'stopwatch', 'Switch': 'widgets', 'THEME': 'style', 'THEMES': 'style', 'TimeField': 'widgets', 'TimerTab': 'timer', 'WEEKDAYS': 'schedule', 'apply_theme': 'style', 'card_row': 'widgets', 'catalog': 'localization', 'describe_days': 'schedule', 'ensure_builtin': 'sound', 'fmt_hms': 'schedule', 'fmt_in': 'schedule', 'fmt_sw': 'schedule', 'live_i18n': 'localization', 'load_all_themes': 'style', 'main': 'app', 'make_arrow_png': 'style', 'make_icon': 'style', 'make_wav': 'sound', 'next_fire': 'schedule', 'resolve_sound': 'sound', 'tr': 'localization'}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_clock_app.{module}"), name)
