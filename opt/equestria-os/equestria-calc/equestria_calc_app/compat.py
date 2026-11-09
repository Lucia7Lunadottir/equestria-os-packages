"""Compatibility exports for existing embedded consumers; new code imports concrete modules."""
from importlib import import_module

_EXPORTS = {'BITS': 'programmer_math', 'CATS': 'units', 'CONFIG': 'paths', 'ConverterPage': 'converter_page', 'DEFAULT_THEME': 'style', 'DIGITS': 'programmer_page', 'DatePage': 'date_page', 'EXPR_TXT': 'expression_page', 'ExprPage': 'expression_page', 'HistoryPanel': 'widgets', 'KEYS': 'style', 'MODES': 'window', 'MainWindow': 'window', 'OPS': 'arithmetic', 'PLUS_OPS': 'expression_page', 'POPS': 'programmer_math', 'PROG_ROWS': 'programmer_page', 'PROG_TXT': 'programmer_page', 'PageBase': 'widgets', 'ProgPage': 'programmer_page', 'QSS': 'style', 'SCI_ROWS': 'expression_page', 'STD_ROWS': 'expression_page', 'THEME': 'style', 'THEMES': 'style', 'WEEKDAYS': 'dates', 'add_months': 'dates', 'apply_theme': 'style', 'catalog': 'localization', 'convert': 'units', 'date_diff': 'dates', 'evaluate': 'arithmetic', 'fit': 'widgets', 'fmt': 'arithmetic', 'fmt_base': 'programmer_math', 'funcs': 'arithmetic', 'group': 'programmer_math', 'live_i18n': 'localization', 'main': 'app', 'mk': 'widgets', 'parse_date': 'dates', 'prog_eval': 'programmer_math', 'right_label': 'widgets', 'single_group': 'widgets', 'toggle_neg': 'widgets', 'tr': 'localization', 'wrap': 'programmer_math'}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_calc_app.{module}"), name)
