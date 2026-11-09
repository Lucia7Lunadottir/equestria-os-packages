"""Compatibility exports for existing embedded consumers; new code imports concrete modules."""
from importlib import import_module

_EXPORTS = {'BUILTIN': 'formats', 'CATS': 'formats', 'CONFIG': 'paths', 'ColorState': 'color', 'DEFAULTS': 'settings', 'DEFAULT_PRIMARY': 'formats', 'DEFAULT_THEME': 'style', 'FormatBook': 'formats', 'FormatDialog': 'format_dialog', 'GrimStep': 'capture', 'HELP_FIELDS': 'formats', 'HueBar': 'widgets', 'HyprpickerStep': 'capture', 'KEYS': 'style', 'MY': 'formats', 'MainWindow': 'window', 'Overlay': 'capture', 'PICK_STEPS': 'capture', 'PORTAL_SCRIPT': 'capture', 'PickStep': 'capture', 'PortalStep': 'capture', 'QSS': 'style', 'SVBox': 'widgets', 'ScreenPicker': 'capture', 'SlurpStep': 'capture', 'Swatch': 'widgets', 'THEME': 'style', 'THEMES': 'style', 'WAYLAND_HELP': 'capture', 'apply_theme': 'style', 'catalog': 'localization', 'contrast': 'color', 'fields': 'color', 'flag': 'widgets', 'fnum': 'color', 'grade': 'color', 'lin': 'color', 'live_i18n': 'localization', 'load_config': 'settings', 'luminance': 'color', 'main': 'app', 'oklch': 'color', 'parse_hex': 'color', 'tr': 'localization', 'try_render': 'color'}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_color_picker_app.{module}"), name)
