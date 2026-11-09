"""Compatibility exports for existing embedded consumers; new code imports concrete modules."""
from importlib import import_module

_EXPORTS = {'BACKENDS': 'backends', 'CONFIG': 'paths', 'DEFAULTS': 'settings', 'DEFAULT_THEME': 'style', 'HAVE_DBUS': 'backends', 'HINT': 'window', 'HyprlandBackend': 'backends', 'KEYS': 'style', 'KWIN_JS': 'backends', 'KWinBridge': 'backends', 'KdeBackend': 'backends', 'MODES': 'entries', 'MainWindow': 'window', 'NoBackend': 'backends', 'QDBusConnection': 'backends', 'QDBusInterface': 'backends', 'QSS': 'style', 'REVEAL_FAILED': 'backends', 'REVEAL_INVISIBLE': 'backends', 'REVEAL_NO_REPLY': 'backends', 'REVEAL_NO_WINDOW': 'backends', 'REVEAL_SHOWN': 'backends', 'STATE_MARK': 'processes', 'SwayBackend': 'backends', 'THEME': 'style', 'THEMES': 'style', 'WindowBackend': 'backends', 'WindowPicker': 'picker', 'X11Backend': 'backends', 'app_label': 'processes', 'apply_theme': 'style', 'build_entries': 'entries', 'catalog': 'localization', 'cmd_args': 'processes', 'cmdline': 'processes', 'detect_backend': 'backends', 'is_gui': 'processes', 'kde_available': 'backends', 'live_i18n': 'localization', 'load_config': 'settings', 'main': 'app', 'proc_cwd': 'processes', 'prune_gui_cache': 'processes', 'run': 'backends', 'scan_procs': 'processes', 'send_signal': 'processes', 'tr': 'localization', 'tree_pids': 'processes'}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_closer_app.{module}"), name)
