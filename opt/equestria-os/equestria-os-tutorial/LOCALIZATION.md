# Localization

`localization.py` connects `equestria_kit.live_i18n.Catalog`. The application retains semantic keys and binds widget properties with `call(setter, tr(key, ...))`. No application-owned language list or language-change redraw is needed.

Add a UTF-8 JSON object of string keys and values to `locales/<locale>.json`, using `en.json` as a template. Restart the application to discover the new file; it appears in the top-right selector without code changes. Optional `_language_name` supplies its display name. Missing translations fall back to English. The shared package saves the selected language in the application's XDG configuration.

User catalogs can also be placed in `$XDG_DATA_HOME/APP_ID/locales/` (default `~/.local/share/APP_ID/locales/`); replace APP_ID with this application's directory name.

Switching language updates existing widgets and preserves application state. Tutorial's `rich_text.py` adapts HTML to the shared text binding; the mirror manager preserves translated messages across worker signals using object signals.

Requires the existing equestria-qt-kit 1.3 live_i18n API. Source checkouts use the sibling package; installed applications use the system package.
