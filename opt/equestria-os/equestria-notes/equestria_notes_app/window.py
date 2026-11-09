"""notes: window."""
from __future__ import annotations

import json
import os
from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut, QTextCursor, QTextListFormat
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget
)
from datetime import datetime
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import small_btn
from pathlib import Path
from .images import MK, store_image
from .library import EMPTY_HINT, NoteLibrary
from .localization import catalog, live_i18n, tr
from .markdown import count_tasks
from .paths import CONFIG, FILES, GLOBAL
from .rich_editor import RichEdit
from .source_editor import MdHighlighter, NoteEdit
from .storage import global_dir, note_title, read_text, write_text
from .style import apply_theme


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.gdir = global_dir()
        try:
            self.gdir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.cur_path = None
        self.cur_mtime = 0.0
        self.dirty = False
        self.loading = False
        self.mode = cfg["mode"]
        self.hide_done = False
        self.lib = NoteLibrary(cfg, self.gdir)
        self.save_timer = QTimer(self, singleShot=True, interval=1500)
        self.save_timer.timeout.connect(self.save_note)
        self.prev_timer = QTimer(self, singleShot=True, interval=500)
        self.prev_timer.timeout.connect(self._update_progress)
        self.cfg_timer = QTimer(self, singleShot=True, interval=400)
        self.cfg_timer.timeout.connect(self.save_cfg)
        self.say_timer = QTimer(self, singleShot=True, interval=4000)
        self.say_timer.timeout.connect(self._status_idle)
        live_i18n.call(self.setWindowTitle, "Equestria Notes")
        self.setMinimumSize(980, 640)
        self.resize(1180, 760)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = live_i18n.call(QLabel, "Equestria Notes")
        title.setObjectName("h2")
        theme_btn = small_btn(tr("window.theme"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        self.language_combo = catalog.selector(self)
        top.addWidget(self.language_combo)
        top.addWidget(theme_btn)
        root.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)

        # ---- левая колонка: источники и список заметок
        left = QVBoxLayout()
        left.setSpacing(8)
        self.new_btn = live_i18n.call(QPushButton, tr("common.new_note"))
        self.new_btn.setObjectName("primary")
        self.new_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.new_btn.clicked.connect(self.new_note)
        left.addWidget(self.new_btn)
        srow = QHBoxLayout()
        self.src = QComboBox()
        live_i18n.call(self.src.setToolTip, tr("window.where_look_notes"))
        self.src.currentIndexChanged.connect(self._src_changed)
        more = small_btn("⋯", tip=tr("window.actions_source"))
        more.clicked.connect(lambda: self._src_menu(more))
        srow.addWidget(self.src, 1)
        srow.addWidget(more)
        left.addLayout(srow)
        arow = QHBoxLayout()
        add_dir = small_btn(tr("window.folder"), tip=tr("window.add_your_own_notes_folder"))
        add_dir.clicked.connect(self.add_folder)
        add_file = small_btn(tr("window.file"), tip=tr("window.open_separate_files_they_will"))
        add_file.clicked.connect(self.add_files)
        arow.addWidget(add_dir)
        arow.addWidget(add_file)
        arow.addStretch()
        left.addLayout(arow)
        self.search = QLineEdit()
        live_i18n.call(self.search.setPlaceholderText, tr("window.search_by_title_text"))
        self.search.textChanged.connect(self.refresh_list)
        left.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._on_select)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        left.addWidget(self.list, 1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(330)
        body.addWidget(lw)

        # ---- правая колонка: заголовок, панель, редактор/просмотр
        right = QVBoxLayout()
        right.setSpacing(8)
        hrow = QHBoxLayout()
        self.d_title = live_i18n.call(QLabel, EMPTY_HINT)
        self.d_title.setObjectName("out")
        self.d_title.setWordWrap(True)
        hrow.addWidget(self.d_title, 1)
        self.mode_btns = {}
        for mode, label in (("visual", tr("window.visual")), ("source", "Markdown")):
            b = small_btn(label, True, tr("window.ctrl_e_switch_mode"))
            b.clicked.connect(lambda _=False, m=mode: self._set_mode(m))
            self.mode_btns[mode] = b
            hrow.addWidget(b)
        self.save_btn = small_btn(tr("window.save"), tip=tr("window.save_ctrl_s"))
        self.save_btn.clicked.connect(self.save_note)
        self.revert_btn = small_btn(tr("window.revert"), tip=tr("window.discard_edits_restore_saved_file"))
        self.revert_btn.clicked.connect(self.revert_note)
        hrow.addWidget(self.save_btn)
        hrow.addWidget(self.revert_btn)
        right.addLayout(hrow)
        frow = QHBoxLayout()
        frow.setSpacing(6)
        self.fmt_btns = []
        for label, tip, key in (
                ("B", tr("window.bold_ctrl_b"), "b"), ("I", tr("window.italic_ctrl_i"), "i"),
                ("S", tr("window.strikethrough"), "s"), ("<>", tr("window.code"), "c"),
                ("H", tr("window.heading_click_change_level"), "h"),
                ("•", tr("window.bulleted_list_tab_nested"), "ul"),
                ("☑", tr("window.checklist_ctrl_shift_l"), "task"),
                ("1.", tr("window.numbered_list"), "ol"), ("❝", tr("window.quote"), "quote"),
                (tr("common.link"), tr("window.link_ctrl_k_open_ctrl"), "link"),
                ("🖼", tr("window.insert_picture_you_can_paste"), "img")):
            b = small_btn(label, tip=tip)
            b.clicked.connect(lambda _=False, k=key: self._fmt(k))
            self.fmt_btns.append(b)
            frow.addWidget(b)
        frow.addStretch()
        self.progress = live_i18n.call(QLabel, "")
        self.progress.setObjectName("hint")
        frow.addWidget(self.progress)
        right.addLayout(frow)

        self.editor = NoteEdit()  # режим «Markdown» (исходник)
        live_i18n.call(self.editor.setPlaceholderText, tr("window.write_here_task_checkbox_item"))
        self.editor.setTabStopDistance(32)
        self.editor.textChanged.connect(self._text_changed)
        self.hl = MdHighlighter(self.editor.document())
        self.rich = RichEdit()  # визуальный режим
        self.rich.textChanged.connect(self._text_changed)
        self.active = self.rich
        right.addWidget(self.editor, 1)
        right.addWidget(self.rich, 1)
        self.status = live_i18n.call(QLabel, "")
        self.status.setObjectName("hint")
        right.addWidget(self.status)
        body.addLayout(right, 1)

        # горячие клавиши
        def sc(seq, fn, widget=None):
            s = QShortcut(QKeySequence(seq), widget or self)
            if widget is not None:
                s.setContext(Qt.ShortcutContext.WidgetShortcut)
            s.activated.connect(fn)
        sc("Ctrl+N", self.new_note)
        sc("Ctrl+S", self.save_note)
        sc("Ctrl+F", lambda: self.search.setFocus())
        sc("Ctrl+E", self._cycle_mode)
        for w in (self.editor, self.rich):
            sc("Ctrl+B", lambda: self._fmt("b"), w)
            sc("Ctrl+I", lambda: self._fmt("i"), w)
            sc("Ctrl+K", lambda: self._fmt("link"), w)
            sc("Ctrl+Shift+L", lambda: self._fmt("task"), w)
            sc("Ctrl+Return", self._toggle_here, w)
            sc("Ctrl+Enter", self._toggle_here, w)

        self.timer = QTimer(self, interval=4000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._rebuild_sources()
        self._set_mode(self.mode, save=False)
        self._editor_enabled(False)
        self.refresh_list()
        last = cfg.get("last")
        if last and os.path.isfile(last) and self._select_in_list(last):
            self.open_note(last)

    # --- вспомогательное
    def _say(self, text: str) -> None:
        live_i18n.call(self.status.setText, text)
        self.say_timer.start()

    def _status_idle(self) -> None:
        live_i18n.call(self.status.setText, tr("window.not_saved") if self.dirty else (tr("window.saved") if self.cur_path else ""))

    def _editor_enabled(self, on: bool) -> None:
        for ed in (self.editor, self.rich):
            ed.setReadOnly(not on)
        for b in self.fmt_btns:
            b.setEnabled(on)
        self.save_btn.setEnabled(False)
        self.revert_btn.setEnabled(False)
        if not on:
            live_i18n.call(self.d_title.setText, EMPTY_HINT)
            live_i18n.call(self.progress.setText, "")
            live_i18n.call(self.status.setText, "")
            for ed in (self.editor, self.rich):
                ed.blockSignals(True)
                ed.clear()
                ed.blockSignals(False)

    def _get_text(self) -> str:
        return self.rich.markdown() if self.active is self.rich else self.editor.toPlainText()

    def _put_text(self, text: str, path: str) -> None:
        self.rich.base_dir = os.path.dirname(path)
        if self.active is self.rich:
            self.rich.set_markdown(text)
        else:
            self.editor.setPlainText(text)

    def _fmt(self, k: str) -> None:
        ed = self.active
        if k == "img":
            self.add_image()
            return
        if ed is self.rich:
            L = QTextListFormat.Style
            if k == "quote" and not ed.toggle_quote():
                self._say(tr("window.qt_version_does_not_support"))
            acts = {"b": ed.toggle_bold, "i": ed.toggle_italic, "s": ed.toggle_strike, "c": ed.toggle_code,
                    "h": ed.cycle_heading, "ul": lambda: ed.set_list(L.ListDisc),
                    "task": ed.toggle_task, "ol": lambda: ed.set_list(L.ListDecimal),
                    "link": ed.insert_link}
        else:
            acts = {"b": lambda: ed.wrap("**"), "i": lambda: ed.wrap("*"), "s": lambda: ed.wrap("~~"),
                    "c": lambda: ed.wrap("`"), "h": lambda: ed.apply_marker("h"),
                    "ul": lambda: ed.apply_marker("ul"), "task": lambda: ed.apply_marker("task"),
                    "ol": lambda: ed.apply_marker("ol"), "quote": lambda: ed.apply_marker("quote"),
                    "link": ed.insert_link}
        if k in acts:
            acts[k]()
        ed.setFocus()

    def _toggle_here(self) -> None:
        if self.active is self.rich:
            self.rich.toggle_check_here()
        else:
            self.editor.toggle_task_here()

    def add_image(self) -> None:
        if not self.cur_path:
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("window.pictures"), str(Path.home()), tr("window.images_png_jpg_jpeg_gif"))
        d = os.path.dirname(self.cur_path)
        for p in files:
            try:
                rel = store_image(p, d)
            except OSError as e:
                self._say(tr("window.could_not_copy_picture", e.strerror or e))
                continue
            if self.active is self.rich:
                self.rich.insert_image_rel(rel)
            else:
                self.editor.insertPlainText(live_i18n.format_text('![]({0})\n', rel))
        self.active.setFocus()

    # --- источники
    def _src_id(self) -> str:
        return self.lib.source

    def _src_dir(self):
        return self.lib.source_dir()

    def _rebuild_sources(self) -> None:
        self.src.blockSignals(True)
        self.src.clear()
        for label, sid, tip in self.lib.source_entries():
            live_i18n.call(self.src.addItem, label, sid)
            if tip:
                self.src.setItemData(self.src.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        idx = self.src.findData(self._src_id())
        if idx < 0:
            self.lib.source = GLOBAL
            idx = 0
        self.src.setCurrentIndex(idx)
        self.src.blockSignals(False)

    def _src_changed(self, _i) -> None:
        if not self._leave_ok():
            self.src.blockSignals(True)
            self.src.setCurrentIndex(max(0, self.src.findData(self.cfg['source'])))
            self.src.blockSignals(False)
            return
        self.lib.source = self.src.currentData()
        self.cfg_timer.start()
        self.refresh_list()

    def _src_menu(self, btn: QPushButton) -> None:
        menu = QMenu(self)
        d = self._src_dir()
        if d:
            live_i18n.call(menu.addAction, tr("window.open_folder_file_manager")).triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(d)))
        if self._src_id() not in (GLOBAL, FILES):
            live_i18n.call(menu.addAction, tr("window.remove_folder_from_list_files")).triggered.connect(self._remove_folder)
        if self._src_id() == FILES and self.lib.cfg["files"]:
            live_i18n.call(menu.addAction, tr("window.clear_file_history")).triggered.connect(self._clear_files)
        if not menu.actions():
            return
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _remove_folder(self) -> None:
        self.lib.remove_current_folder()
        self._rebuild_sources()
        self.cfg_timer.start()
        self.refresh_list()

    def _clear_files(self) -> None:
        self.lib.clear_files()
        self.cfg_timer.start()
        self.refresh_list()

    def add_folder(self) -> None:
        start = self._src_dir() or str(self.gdir)
        d = QFileDialog.getExistingDirectory(self, tr("window.notes_folder"), start)
        if not d:
            return
        self.lib.add_folder(d)
        self._rebuild_sources()
        self.cfg_timer.start()
        self.refresh_list()

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("window.choose_files"), str(self.gdir),
            tr("window.text_markdown_md_markdown_txt"))
        if not files:
            return
        if not self._leave_ok():
            return
        for p in reversed(files):
            self._remember_file(os.path.normpath(p))
        self.lib.source = FILES
        self._rebuild_sources()
        self.refresh_list()
        first = os.path.normpath(files[0])
        if self._select_in_list(first):
            self.open_note(first)

    def _remember_file(self, p: str) -> None:
        self.lib.remember_file(p)
        self.cfg_timer.start()

    # --- список заметок
    def refresh_list(self, *_) -> None:
        src = self._src_id()
        q = self.search.text().strip().lower()
        infos = self.lib.notes(q)
        sb = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        cur_item = None
        for i in infos:
            if i["missing"]:
                text = tr("window.file_not_found", i['title'], os.path.dirname(i['path']))
            else:
                done, total = i["tasks"]
                prog = live_i18n.format_text('☑ {0}/{1} · ', done, total) if total else ""
                date = datetime.fromtimestamp(i["mtime"]).strftime("%d.%m.%Y %H:%M")
                text = live_i18n.format_text('{0}\n{1} · {2}{3}', i['title'], date, prog, i['preview'])
            it = live_i18n.call(QListWidgetItem, text)
            it.setData(Qt.ItemDataRole.UserRole, i["path"])
            live_i18n.call(it.setToolTip, i["path"])
            live_i18n.call(self.list.addItem, it)
            if i["path"] == self.cur_path:
                cur_item = it
        if not infos:
            msg = (tr("window.nothing_found") if q else
                   tr("window.history_empty_add_files_with") if src == FILES else
                   tr("window.there_no_notes_here_yet"))
            it = live_i18n.call(QListWidgetItem, msg)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            live_i18n.call(self.list.addItem, it)
        if cur_item:
            self.list.setCurrentItem(cur_item)
        self.list.blockSignals(False)
        self.list.verticalScrollBar().setValue(sb)

    def _select_in_list(self, path: str) -> bool:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                self.list.blockSignals(True)
                self.list.setCurrentRow(i)
                self.list.blockSignals(False)
                self.list.scrollToItem(self.list.item(i))
                return True
        return False

    def _on_select(self) -> None:
        items = self.list.selectedItems()
        path = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        if path and path != self.cur_path:
            self.open_note(path)

    def _tick(self) -> None:
        self.refresh_list()
        if self.cur_path and not self.dirty:
            try:
                m = os.stat(self.cur_path).st_mtime
            except OSError:
                return
            if m != self.cur_mtime:  # файл изменили снаружи
                self.open_note(self.cur_path, keep_cursor=True)

    # --- открыть / сохранить
    def open_note(self, path: str, keep_cursor: bool = False) -> None:
        if path != self.cur_path and not self._leave_ok():
            if self.cur_path:
                self._select_in_list(self.cur_path)
            return
        try:
            text = read_text(path)
            mtime = os.stat(path).st_mtime
        except OSError as e:
            self._say(tr("window.could_not_open", e.strerror or e))
            return
        ed = self.active
        pos = ed.textCursor().position() if keep_cursor else 0
        sb = ed.verticalScrollBar().value() if keep_cursor else 0
        self.loading = True
        self._editor_enabled(True)
        self._put_text(text, path)
        self.loading = False
        cur = ed.textCursor()
        cur.setPosition(min(pos, max(0, ed.document().characterCount() - 1)))
        ed.setTextCursor(cur)
        ed.verticalScrollBar().setValue(sb)
        self.cur_path, self.cur_mtime, self.dirty = path, mtime, False
        self.cfg["last"] = path
        if self._src_id() == FILES:
            self._remember_file(path)
        self.cfg_timer.start()
        live_i18n.call(self.d_title.setText, note_title(path))
        live_i18n.call(self.setWindowTitle, live_i18n.format_text('{0} — Equestria Notes', note_title(path)))
        self._update_progress()
        self._status_idle()
        self._select_in_list(path)

    def _text_changed(self) -> None:
        if self.loading or not self.cur_path or self.rich.fitting:
            return
        self.dirty = True
        live_i18n.call(self.status.setText, tr("window.not_saved"))
        self.save_btn.setEnabled(True)
        self.revert_btn.setEnabled(True)
        self.prev_timer.start()

    def _leave_ok(self) -> bool:
        if not (self.cur_path and self.dirty):
            return True
        box = QMessageBox(self)
        live_i18n.call(box.setWindowTitle, tr("window.unsaved_changes"))
        live_i18n.call(box.setText, tr("window.save_changes", note_title(self.cur_path)))
        save = live_i18n.call(box.addButton, tr("window.save"), QMessageBox.ButtonRole.AcceptRole)
        drop = live_i18n.call(box.addButton, tr("window.don_t_save"), QMessageBox.ButtonRole.DestructiveRole)
        live_i18n.call(box.addButton, tr("window.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        b = box.clickedButton()
        if b is save:
            self.save_note()
            return not self.dirty
        if b is drop:
            self.dirty = False
            self.open_note(self.cur_path)  # вернуть в редактор сохранённый текст
            return True
        return False

    def revert_note(self) -> None:
        if not (self.cur_path and self.dirty):
            return
        box = QMessageBox(self)
        live_i18n.call(box.setWindowTitle, tr("window.revert"))
        live_i18n.call(box.setText, tr("window.discard_all_unsaved_edits_restore"))
        yes = live_i18n.call(box.addButton, tr("window.revert"), QMessageBox.ButtonRole.DestructiveRole)
        no = live_i18n.call(box.addButton, tr("window.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() is yes:
            self.dirty = False
            self.open_note(self.cur_path, keep_cursor=True)

    def save_note(self) -> None:
        if not self.cur_path or not self.dirty:
            return
        try:
            write_text(self.cur_path, self._get_text())
            self.cur_mtime = os.stat(self.cur_path).st_mtime
        except OSError as e:
            self._say(tr("window.save_error", e.strerror or e))
            return
        self.dirty = False
        self.save_btn.setEnabled(False)
        self.revert_btn.setEnabled(False)
        live_i18n.call(self.status.setText, tr("window.saved"))
        self.refresh_list()

    def _update_progress(self) -> None:
        if not self.cur_path:
            return
        if self.active is self.rich:
            done = total = 0
            b = self.rich.document().begin()
            while b.isValid():
                m = b.blockFormat().marker()
                if m != MK.NoMarker:
                    total += 1
                    done += m == MK.Checked
                b = b.next()
        else:
            done, total = count_tasks(self.editor.toPlainText())
        live_i18n.call(self.progress.setText, tr("window.tasks", done, total) if total else "")

    def _set_mode(self, mode: str, save: bool = True) -> None:
        new = self.rich if mode == "visual" else self.editor
        if new is not self.active and self.cur_path:
            text = self._get_text()
            self.active = new
            self.loading = True
            self._put_text(text, self.cur_path)
            self.loading = False
            self._update_progress()
        self.active = new
        self.mode = mode
        for m, b in self.mode_btns.items():
            b.setChecked(m == mode)
        self.rich.setVisible(mode == "visual")
        self.editor.setVisible(mode == "source")
        if self.cur_path:
            new.setFocus()
        if save:
            self.cfg["mode"] = mode
            self.cfg_timer.start()

    def _cycle_mode(self) -> None:
        self._set_mode("source" if self.mode == "visual" else "visual")

    # --- создание, переименование, удаление
    def new_note(self) -> None:
        if not self._leave_ok():
            return
        src_before = self.lib.source
        try:
            path = self.lib.create_note()
        except OSError as e:
            self._say(tr("window.could_not_create_file", e.strerror or e))
            return
        if self.lib.source != src_before:   # папки источника нет — заметка ушла в «Заметки»
            self._rebuild_sources()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.refresh_list()
        self.open_note(path)
        self.active.setFocus()
        cur = self.active.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.active.setTextCursor(cur)

    def _list_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        path = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not path:
            return
        menu = QMenu(self)
        live_i18n.call(menu.addAction, tr("window.rename_ellipsis")).triggered.connect(lambda: self.rename_note(path))
        live_i18n.call(menu.addAction, tr("window.show_folder")).triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
        live_i18n.call(menu.addAction, tr("window.copy_path")).triggered.connect(lambda: live_i18n.call(QApplication.clipboard().setText, path))
        if self._src_id() == FILES:
            live_i18n.call(menu.addAction, tr("window.remove_from_history")).triggered.connect(lambda: self._forget_file(path))
        menu.addSeparator()
        live_i18n.call(menu.addAction, tr("window.delete_file_ellipsis")).triggered.connect(lambda: self.delete_note(path))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def _forget_file(self, path: str) -> None:
        if path == self.cur_path and not self._leave_ok():
            return
        self.lib.forget_file(path)
        self.cfg_timer.start()
        if path == self.cur_path:
            self.cur_path = None
            self._editor_enabled(False)
        self.refresh_list()

    def rename_note(self, path: str) -> None:
        old = os.path.basename(path)
        stem, ext = os.path.splitext(old)
        name, ok = QInputDialog.getText(self, tr("window.rename"), tr("window.new_name"), text=stem)
        name = NoteLibrary.safe_name(name)
        if not ok or not name or name == stem:
            return
        if path == self.cur_path and not self._leave_ok():
            return
        try:
            new = self.lib.rename(path, name)
        except FileExistsError:
            self._say(tr("window.file_with_name_already_exists"))
            return
        except OSError as e:
            self._say(tr("window.could_not_rename", e.strerror or e))
            return
        if path == self.cur_path:
            self.cur_path = new
            live_i18n.call(self.d_title.setText, note_title(new))
            live_i18n.call(self.setWindowTitle, live_i18n.format_text('{0} — Equestria Notes', note_title(new)))
        self.cfg_timer.start()
        self.refresh_list()

    def delete_note(self, path: str) -> None:
        box = QMessageBox(self)
        live_i18n.call(box.setWindowTitle, tr("window.delete_file"))
        live_i18n.call(box.setText, tr("window.move_trash", note_title(path)))
        yes = live_i18n.call(box.addButton, tr("window.trash"), QMessageBox.ButtonRole.AcceptRole)
        no = live_i18n.call(box.addButton, tr("window.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() is not yes:
            return
        if path == self.cur_path:
            self.dirty = False
            self.save_timer.stop()
        try:
            self.lib.delete(path)  # корзины нет — удаляется напрямую (подтверждение уже было)
        except OSError as e:
            self._say(tr("window.could_not_delete", e.strerror or e))
            return
        if path == self.cur_path:
            self.cur_path = None
            self._editor_enabled(False)
            live_i18n.call(self.setWindowTitle, "Equestria Notes")
        self.cfg_timer.start()
        self.refresh_list()

    # --- тема / настройки
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
        self.hl.rehighlight()
        if self.cur_path and self.active is self.rich:
            self.loading = True
            self._put_text(self._get_text(), self.cur_path)
            self.loading = False
        self.save_cfg()

    def save_cfg(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def closeEvent(self, e) -> None:
        if not self._leave_ok():
            e.ignore()
            return
        self.save_cfg()
        super().closeEvent(e)
