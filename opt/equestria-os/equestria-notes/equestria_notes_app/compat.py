"""Compatibility exports for existing embedded consumers; new code imports concrete modules."""
from importlib import import_module

_EXPORTS = {'BULLETS': 'images', 'CONFIG': 'paths', 'DEFAULTS': 'settings', 'DEFAULT_THEME': 'style', 'EMPTY_HINT': 'library', 'EXTS': 'paths', 'FENCE_RE': 'markdown', 'FILES': 'paths', 'FSA': 'images', 'GLOBAL': 'paths', 'HEAD_RE': 'markdown', 'HR_RE': 'markdown', 'IMG_EXTS': 'images', 'KEYS': 'style', 'LIST_RE': 'markdown', 'MK': 'images', 'MainWindow': 'window', 'MdHighlighter': 'source_editor', 'NoteEdit': 'source_editor', 'NoteLibrary': 'library', 'QSS': 'style', 'REFDEF_RE': 'images', 'REFUSE_RE': 'images', 'RichEdit': 'rich_editor', 'TABLE_SEP_RE': 'markdown', 'TASK_RE': 'markdown', 'THEME': 'style', 'THEMES': 'style', 'apply_theme': 'style', 'catalog': 'localization', 'count_tasks': 'markdown', 'css': 'markdown', 'draw_task_box': 'rich_editor', 'flip_task': 'markdown', 'global_dir': 'storage', 'inline': 'markdown', 'line_kind': 'markdown', 'live_i18n': 'localization', 'load_config': 'settings', 'main': 'app', 'md_to_html': 'markdown', 'note_title': 'storage', 'preview_of': 'storage', 'read_text': 'storage', 'resolve_refs': 'images', 'save_data_uri': 'images', 'split_line': 'markdown', 'store_image': 'images', 'store_qimage': 'images', 'tr': 'localization', 'write_text': 'storage'}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_notes_app.{module}"), name)
