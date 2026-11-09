"""One JSON file per language; available languages come exclusively from disk."""
from __future__ import annotations

import json
import os
from pathlib import Path
import warnings


def locale_key(value: str) -> str:
    return value.split('.')[0].split('@')[0].strip().replace('-', '_').casefold()


class Catalog:
    def __init__(self, directories, language: str | None = None):
        self.translations = {}
        for directory in directories:
            for path in sorted(Path(directory).glob('*.json')):
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    if not isinstance(data, dict) or not all(
                        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
                    ):
                        raise ValueError('expected an object with string translations')
                except (OSError, ValueError) as error:
                    warnings.warn(f'Cannot load locale {path}: {error}', stacklevel=2)
                    continue
                self.translations.setdefault(path.stem, data)
        self.languages = tuple(sorted(self.translations))
        preferences = [language] if language else []
        for variable in ('EQUESTRIA_LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
            preferences.extend(os.environ.get(variable, '').split(':'))
        self.lang = next((code for value in preferences if (code := self.match(value))),
                         self.match('en') or next(iter(self.languages), ''))

    def match(self, value: str) -> str:
        available = {locale_key(code): code for code in self.languages}
        key = locale_key(value)
        while key:
            if key in available:
                return available[key]
            key = key.rsplit('_', 1)[0] if '_' in key else ''
        return ''

    def language_name(self, code: str) -> str:
        return self.translations[code].get('_language_name') or code

    def tr(self, text: str, *args, **kwargs) -> str:
        translated = (self.translations.get(self.lang, {}).get(text)
                      or self.translations.get(self.match('en'), {}).get(text) or text)
        if args or kwargs:
            try:
                return translated.format(*args, **kwargs)
            except (IndexError, KeyError, ValueError):
                return text.format(*args, **kwargs)
        return translated


def load_catalog() -> Catalog:
    here = Path(__file__).resolve().parents[1]
    data_home = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    data_dirs = (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':')
    directories = [data_home / 'equestria-audio-converter/locales', here / 'locales']
    directories.extend(Path(d) / 'equestria-audio-converter/locales' for d in data_dirs if d)
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    try:
        settings = json.loads((config / 'equestria-converter/settings.json').read_text(encoding='utf-8'))
        language = settings.get('language') if isinstance(settings, dict) else None
    except (OSError, ValueError):
        language = None
    return Catalog(directories, language if isinstance(language, str) else None)


# Shared catalog; UI text is resolved when widgets are built.
catalog = load_catalog()
