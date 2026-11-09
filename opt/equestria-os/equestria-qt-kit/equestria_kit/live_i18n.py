"""File-discovered catalogs and explicit, state-preserving Qt text bindings."""
from __future__ import annotations

import json
import os
from pathlib import Path
import warnings
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QLocale, QLibraryInfo, QTranslator, QPersistentModelIndex, QSignalBlocker, QObject
from PyQt6.QtWidgets import QApplication, QComboBox, QListWidgetItem, QTreeWidgetItem, QTreeWidget, QTabWidget


def key(value):
    return value.split('.')[0].split('@')[0].replace('-', '_').strip().casefold()


class Text(str):
    """A string carrying its translation recipe to the Qt setter."""
    def __new__(cls, catalog, render):
        obj = super().__new__(cls, render())
        obj.catalog, obj.render = catalog, render
        return obj

    def __str__(self):
        return self.render()

    def __format__(self, spec):
        return format(self.render(), spec)

    def upper(self):
        return Text(self.catalog, lambda: self.render().upper())

    def lower(self):
        return Text(self.catalog, lambda: self.render().lower())

    def __add__(self, other):
        return Text(self.catalog, lambda: self.render() + str(other))

    def __radd__(self, other):
        return Text(self.catalog, lambda: str(other) + self.render())

    def __getitem__(self, index):
        return Text(self.catalog, lambda: self.render()[index])

    def format(self, *args, **kwargs):
        return Text(self.catalog, lambda: self.render().format(*args, **kwargs))


def format_text(template, *args):
    """Keep translation recipes inside formatted labels without retaining widgets."""
    text = next((arg for arg in args if isinstance(arg, Text)), None)
    render = lambda: template.format(*args)
    return Text(text.catalog, render) if text is not None else render()


def join_text(separator, values):
    values = tuple(values)
    text = next((value for value in values if isinstance(value, Text)), None)
    render = lambda: separator.join(str(value) for value in values)
    return Text(text.catalog, render) if text is not None else render()


def rendered(value):
    if isinstance(value, Text):
        return str(value)
    if isinstance(value, list):
        return [rendered(item) for item in value]
    return value


_CATALOGS = weakref.WeakSet()


def catalogs():
    """Все созданные каталоги (например, чтобы библиотека говорила на языке приложения)."""
    return list(_CATALOGS)


class Catalog:
    def __init__(self, app_id, script_file):
        _CATALOGS.add(self)
        self.app_id = app_id
        self.translations = {}
        self.bindings = {}
        self._translator = None
        here = Path(script_file).resolve().parent
        home = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
        dirs = [home / app_id / 'locales', here / 'locales']
        dirs += [Path(d) / app_id / 'locales' for d in
                 (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':') if d]
        for directory in dirs:
            for path in sorted(directory.glob('*.json')):
                try:
                    entries = json.loads(path.read_text(encoding='utf-8'))
                    if not isinstance(entries, dict) or not all(isinstance(v, str) for v in entries.values()):
                        raise ValueError('expected string translations')
                except (OSError, ValueError) as error:
                    warnings.warn(f'{path}: {error}', stacklevel=2)
                    continue
                self.translations.setdefault(path.stem, entries)
        self.languages = tuple(sorted(self.translations))
        self.preference = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / app_id / 'language.json'
        try:
            saved = json.loads(self.preference.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = ''
        self.lang = self.match(saved) if isinstance(saved, str) else ''
        self.lang = self.lang or self.detect()

    def match(self, value):
        available = {key(code): code for code in self.languages}
        code = key(value)
        while code:
            if code in available:
                return available[code]
            code = code.rsplit('_', 1)[0] if '_' in code else ''
        return ''

    def detect(self):
        for env in ('EQUESTRIA_LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
            for value in os.environ.get(env, '').split(':'):
                if code := self.match(value):
                    return code
        return self.match('en') or next(iter(self.languages), '')

    def tr(self, source, *args, **kwargs):
        def render():
            out = (self.translations.get(self.lang, {}).get(source)
                   or self.translations.get(self.match('en'), {}).get(source) or source)
            if args or kwargs:
                try:
                    return out.format(*args, **kwargs)
                except (ValueError, KeyError, IndexError):
                    return source.format(*args, **kwargs)
            return out
        return Text(self, render)

    def library_text(self, key):
        """Строка самой библиотеки (equestria_kit/locales) на языке этого каталога;
        привязана к этому каталогу, поэтому обновляется при смене его языка."""
        kit = _library_catalog()

        def render():
            kit.lang = kit.match(self.lang) or kit.detect()
            return str(kit.tr(key))
        return Text(self, render)

    def bind(self, obj, prop, text, expected):
        identity = id(obj)
        if identity not in self.bindings:
            ref = weakref.ref(obj, lambda _ref: self.bindings.pop(identity, None))
            self.bindings[identity] = (ref, {})
        self.bindings[identity][1][prop] = (text, expected)

    def set_language(self, code, *, persist=True):
        self.lang = self.match(code) or self.detect()
        app = QApplication.instance()
        if app:
            if self._translator:
                app.removeTranslator(self._translator)
            self._translator = QTranslator(app)
            locale = QLocale(self.lang)
            if self._translator.load(locale, 'qtbase', '_', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
                app.installTranslator(self._translator)
            QLocale.setDefault(locale)
            for widget in app.allWidgets():
                widget.setLocale(locale)
        for ref, properties in list(self.bindings.values()):
            obj = ref()
            if obj is None or sip.isdeleted(obj):
                continue
            owner = obj if isinstance(obj, QObject) else (obj.treeWidget() if isinstance(obj, QTreeWidgetItem) else obj.listWidget())
            blocker = QSignalBlocker(owner) if owner is not None else None
            for prop, (text, expected) in list(properties.items()):
                if isinstance(prop, QPersistentModelIndex):
                    if not prop.isValid():
                        properties.pop(prop, None)
                        continue
                    current = obj.itemText(prop.row())
                    setter = lambda value, row=prop.row(): obj.setItemText(row, value)
                elif prop[0] == 'tab':
                    page = prop[1]()
                    index = obj.indexOf(page) if page is not None and not sip.isdeleted(page) else -1
                    if index < 0:
                        properties.pop(prop, None)
                        continue
                    current = obj.tabText(index)
                    setter = lambda value, i=index: obj.setTabText(i, value)
                elif prop[0] == 'header':
                    column = prop[1]
                    header = obj.headerItem()
                    if column >= header.columnCount():
                        properties.pop(prop, None)
                        continue
                    current = header.text(column)
                    setter = lambda value, c=column: obj.headerItem().setText(c, value)
                elif prop[0] == 'column':
                    column, method = prop[1:]
                    current = getattr(obj, 'text' if method == 'setText' else 'toolTip')(column)
                    setter = lambda value, c=column, method=method: getattr(obj, method)(c, value)
                else:
                    getter, method = prop
                    current = getattr(obj, getter)()
                    setter = getattr(obj, method)
                if current != expected:  # an unbound runtime update superseded this text
                    properties.pop(prop, None)
                    continue
                value = str(text)
                setter(value)
                properties[prop] = (text, value)
            del blocker
        if persist:
            try:
                self.preference.parent.mkdir(parents=True, exist_ok=True)
                self.preference.write_text(json.dumps(self.lang), encoding='utf-8')
            except OSError as error:
                warnings.warn(f'Cannot save language: {error}', stacklevel=2)
        return self.lang

    def language_name(self, code):
        """`_language_name` из файла; без него — родное название языка от Qt."""
        name = self.translations.get(code, {}).get('_language_name')
        if not name:
            locale = QLocale(code)
            native = locale.nativeLanguageName() if locale.language() != QLocale.Language.C else ''
            name = native[:1].upper() + native[1:] if native else code
        return name

    def selector(self, parent, after=None):
        box = QComboBox(parent)
        for code in self.languages:
            box.addItem(self.language_name(code), code)
        box.setCurrentIndex(box.findData(self.lang))
        call(box.setToolTip, self.library_text('kit.language'))
        def change(index):
            self.set_language(box.itemData(index))
            if after:
                after()
        box.activated.connect(change)
        return box


_LIBRARY = None


def _library_catalog():
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = Catalog('equestria-qt-kit', __file__)
    return _LIBRARY


_PROPERTIES = {'setText': ('text', 'setText'), 'setTitle': ('title', 'setTitle'),
               'setWindowTitle': ('windowTitle', 'setWindowTitle'),
               'setToolTip': ('toolTip', 'setToolTip'),
               'setPlaceholderText': ('placeholderText', 'setPlaceholderText'),
               'setStatusTip': ('statusTip', 'setStatusTip')}
_CONSTRUCTORS = {'QLabel', 'QPushButton', 'QCheckBox', 'QRadioButton', 'QAction', 'QToolButton', 'QListWidgetItem'}


def call(fn, *args, **kwargs):
    """Pass translated text to Qt and retain a binding to that exact property."""
    name = getattr(fn, '__name__', '')
    obj = getattr(fn, '__self__', None)
    if name == 'setHeaderLabels' and isinstance(obj, QTreeWidget):
        result = fn([rendered(value) for value in args[0]])
        # привязка к самой таблице: обёртку headerItem() Python тут же отпускает, и привязка к ней терялась
        for column, text in enumerate(args[0]):
            if isinstance(text, Text):
                text.catalog.bind(obj, ('header', column), text, str(text))
        return result
    if name == 'QTreeWidgetItem':
        result = fn(*(rendered(arg) for arg in args), **kwargs)
        values = next((arg for arg in args if isinstance(arg, list)), [])
        for column, text in enumerate(values):
            if isinstance(text, Text):
                text.catalog.bind(result, ('column', column, 'setText'), text, str(text))
        return result
    if name == 'addItems'  and isinstance(obj, QComboBox):
        for value in args[0]:
            call(obj.addItem, value)
        return None
    result = fn(*(rendered(arg) for arg in args), **{k: rendered(v) for k, v in kwargs.items()})
    if name in ('addTab', 'setTabText') and isinstance(obj, QTabWidget):
        page = args[0] if name == 'addTab' else obj.widget(args[0])
        text = next((arg for arg in args if isinstance(arg, Text)), None)
        if isinstance(text, Text):
            text.catalog.bind(obj, ('tab', weakref.ref(page)), text, str(text))
        return result
    if name in ('setText', 'setToolTip') and isinstance(obj, QTreeWidgetItem):
        text = args[1]
        if isinstance(text, Text):
            text.catalog.bind(obj, ('column', args[0], name), text, str(text))
        return result
    if name in _CONSTRUCTORS:
        obj, prop = result, ('text', 'setText')
        text = next((arg for arg in args if isinstance(arg, Text)), None)
    elif name in ('addAction', 'addButton', 'addMenu') and result is not None:
        obj = result
        prop = ('title', 'setTitle') if name == 'addMenu' else ('text', 'setText')
        text = next((arg for arg in args if isinstance(arg, Text)), None)
    elif name in _PROPERTIES:
        prop = _PROPERTIES[name]
        text = args[0] if args else None
    elif name in ('addItem', 'setItemText') and isinstance(obj, QComboBox):
        row = obj.count() - 1 if name == 'addItem' else args[0]
        prop = QPersistentModelIndex(obj.model().index(row, obj.modelColumn()))
        text = next((arg for arg in args if isinstance(arg, Text)), None)
    else:
        return result
    if isinstance(text, Text):
        text.catalog.bind(obj, prop, text, str(text))
    return result
