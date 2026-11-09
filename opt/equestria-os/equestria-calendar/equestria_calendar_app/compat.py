"""Compatibility exports for existing embedded consumers; new code imports concrete modules."""
from importlib import import_module

_EXPORTS = {'CONF_DIR': 'paths', 'CalView': 'calendar_views', 'DATA_FILE': 'paths', 'DEFAULT_SETTINGS': 'storage', 'DEFAULT_THEME': 'style', 'KEYS': 'style', 'MONTHS': 'dates', 'MONTHS_G': 'dates', 'MOON_LIGHT': 'style', 'MainWindow': 'window', 'MoonCard': 'calendar_views', 'NEW_MOON_REF': 'dates', 'QSS': 'style', 'QSoundEffect': 'sounds', 'REPEATS': 'dates', 'ReminderBook': 'reminders', 'ReminderDialog': 'reminder_dialog', 'ReminderPopup': 'reminder_popup', 'SOUND_SPECS': 'sounds', 'SWATCHES': 'style', 'SYN': 'dates', 'Sounds': 'sounds', 'Store': 'storage', 'THEME': 'style', 'THEMES': 'style', 'WD_LONG': 'dates', 'WD_SHORT': 'dates', 'YearView': 'calendar_views', 'add_months': 'dates', 'alpha': 'style', 'apply_theme': 'style', 'catalog': 'localization', 'draw_moon': 'calendar_views', 'live_i18n': 'localization', 'main': 'app', 'make_calendar': 'calendar_views', 'make_check_icons': 'style', 'make_icon': 'style', 'moon_frac': 'dates', 'moon_info': 'dates', 'moon_noon': 'dates', 'next_phase': 'dates', 'occ_dt': 'dates', 'occurs_on': 'dates', 'parse_time': 'dates', 'pfont': 'style', 'short_date': 'dates', 'sort_key': 'dates', 'synth_wav': 'sounds', 'tr': 'localization'}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_calendar_app.{module}"), name)
