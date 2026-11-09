"""closer: window."""
from __future__ import annotations

import json
import os
import signal
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget
)
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import small_btn
from .backends import REVEAL_FAILED, REVEAL_NO_REPLY, REVEAL_NO_WINDOW, REVEAL_SHOWN, detect_backend
from .entries import build_entries
from .localization import catalog, live_i18n, tr
from .paths import CONFIG
from .picker import WindowPicker
from .processes import STATE_MARK, cmdline, proc_cwd, prune_gui_cache, scan_procs, send_signal, tree_pids
from .style import apply_theme


HINT = tr("window.select_window_left_close_politely")


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.wm = detect_backend()          # стратегия работы с окнами для этой среды
        self.picker = WindowPicker(self.wm, self)
        self.picker.finished.connect(self._pick_done)
        self.mode = cfg["view"]
        self.procs: dict = {}
        self.windows: list = []
        self.entries: list = []
        self.by_key: dict = {}
        self.sel_key = None
        self._tree_sig = None
        self._refreshing = False
        self.save_timer = QTimer(self, singleShot=True, interval=400)
        self.save_timer.timeout.connect(self.save)
        self.toast_timer = QTimer(self, singleShot=True, interval=5000)
        live_i18n.call(self.setWindowTitle, "Equestria Closer")
        self.setMinimumSize(940, 640)
        self.resize(1060, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        root.addLayout(self._build_header())
        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)
        body.addWidget(self._build_list_column())
        body.addLayout(self._build_details_column(), 1)
        self._bind_shortcuts()

        self.timer = QTimer(self, interval=3000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self._set_mode(self.mode, save=False)

    @property
    def picking(self) -> bool:
        return self.picker.running

    # --- построение окна
    def _build_header(self) -> QHBoxLayout:
        top = QHBoxLayout()
        title = live_i18n.call(QLabel, "Equestria Closer")
        title.setObjectName("h2")
        theme_btn = small_btn(tr("window.theme"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        self.language_combo = catalog.selector(self)
        top.addWidget(self.language_combo)
        top.addWidget(theme_btn)
        return top

    def _build_list_column(self) -> QWidget:
        """Левая колонка: выбор окна, режимы, поиск и список."""
        left = QVBoxLayout()
        left.setSpacing(8)
        row = QHBoxLayout()
        self.pick_btn = live_i18n.call(QPushButton, tr("window.pick_window"))
        self.pick_btn.setObjectName("primary")
        self.pick_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        live_i18n.call(self.pick_btn.setToolTip, tr("window.x11_click_window_wayland_3"))
        self.pick_btn.clicked.connect(self.start_pick)
        self.refresh_btn = live_i18n.call(QPushButton, tr("window.refresh"))
        self.refresh_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.pick_btn, 1)
        row.addWidget(self.refresh_btn, 1)
        left.addLayout(row)
        mrow = QHBoxLayout()
        self.mode_btns = {}
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for mode, label, tip in (("apps", tr("window.applications"), tr("window.programs_with_windows_like_system")),
                                 ("windows", tr("window.windows"), tr("window.only_windows_window_manager_sees")),
                                 ("procs", tr("window.all_processes"), tr("window.all_your_processes"))):
            b = small_btn(label, True, tip)
            live_i18n.call(grp.addButton, b)
            mrow.addWidget(b)
            b.clicked.connect(lambda _=False, m=mode: self._set_mode(m))
            self.mode_btns[mode] = b
        mrow.addStretch()
        left.addLayout(mrow)
        self.search = QLineEdit()
        live_i18n.call(self.search.setPlaceholderText, tr("window.search_by_title_class_pid"))
        self.search.textChanged.connect(self._rebuild_list)
        left.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._on_select)
        self.list.itemClicked.connect(lambda _it: self._on_click())
        left.addWidget(self.list, 1)
        self.src_label = live_i18n.call(QLabel, "")
        self.src_label.setObjectName("hint")
        self.src_label.setWordWrap(True)
        left.addWidget(self.src_label)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(400)
        return lw

    def _build_details_column(self) -> QVBoxLayout:
        """Правая колонка: сведения о выбранном, дерево процессов, параметры и действия."""
        right = QVBoxLayout()
        right.setSpacing(8)
        self.d_title = live_i18n.call(QLabel, tr("window.no_window_selected"))
        self.d_title.setObjectName("out")
        self.d_title.setWordWrap(True)
        self.d_info = live_i18n.call(QLabel, "")
        self.d_info.setObjectName("hint")
        self.d_info.setWordWrap(True)
        self.d_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.d_title)
        right.addWidget(self.d_info)
        trow = QHBoxLayout()
        tl = live_i18n.call(QLabel, tr("window.process_tree"))
        tl.setObjectName("h2")
        self.tree_count = live_i18n.call(QLabel, "")
        self.tree_count.setObjectName("hint")
        trow.addWidget(tl)
        trow.addStretch()
        trow.addWidget(self.tree_count)
        right.addLayout(trow)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        live_i18n.call(self.tree.setHeaderLabels, [tr("window.process_title"), "PID", tr("window.command")])
        self.tree.setColumnWidth(0, 210)
        self.tree.setColumnWidth(1, 70)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        right.addWidget(self.tree, 1)
        orow = QHBoxLayout()
        orow.setSpacing(6)
        self.tree_btn = small_btn(tr("window.including_process_tree"), True,
                                  tr("window.action_applies_window_s_process"))
        self.hide_btn = small_btn(tr("window.hide_window_while_picking"), True,
                                  tr("window.window_hides_while_picking_comes"))
        self.confirm_btn = small_btn(tr("window.ask_confirmation"), True,
                                     tr("window.forced_closing_closing_tree"))
        self.reveal_btn_opt = small_btn(tr("window.show_window_click"), True,
                                        tr("window.clicking_list_item_brings_window"))
        orow2 = QHBoxLayout()
        orow2.setSpacing(6)
        for b, key, lay in ((self.reveal_btn_opt, "reveal", orow), (self.tree_btn, "tree", orow),
                            (self.hide_btn, "hide", orow2), (self.confirm_btn, "confirm", orow2)):
            b.setChecked(bool(self.cfg[key]))
            b.toggled.connect(lambda on, k=key: self._opt(k, on))
            lay.addWidget(b)
        orow.addStretch()
        orow2.addStretch()
        right.addLayout(orow)
        right.addLayout(orow2)
        arow = QHBoxLayout()
        arow.setSpacing(10)
        self.show_btn = live_i18n.call(QPushButton, tr("window.show_window"))
        self.show_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        live_i18n.call(self.show_btn.setToolTip, tr("window.bring_window_front_so_you"))
        self.show_btn.clicked.connect(lambda: self.reveal(True))
        arow.addWidget(self.show_btn, 1)
        self.close_btn = live_i18n.call(QPushButton, tr("window.close"))
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(lambda: self.act(False))
        self.kill_btn = live_i18n.call(QPushButton, tr("window.force"))
        self.kill_btn.setObjectName("danger")
        self.kill_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.kill_btn.clicked.connect(lambda: self.act(True))
        arow.addWidget(self.close_btn, 1)
        arow.addWidget(self.kill_btn, 1)
        right.addLayout(arow)
        self.toast = live_i18n.call(QLabel, HINT)
        self.toast.setObjectName("hint")
        self.toast.setWordWrap(True)
        self.toast_timer.timeout.connect(lambda: live_i18n.call(self.toast.setText, HINT))
        right.addWidget(self.toast)
        return right

    def _bind_shortcuts(self) -> None:
        # горячие клавиши работают только когда фокус в списке (чтобы Delete в поиске ничего не закрыл)
        for seq, force in (("Delete", False), ("Shift+Delete", True)):
            sc = QShortcut(QKeySequence(seq), self.list)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(lambda f=force: self.act(f))
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(lambda: self.search.setFocus())

    # --- режимы и список
    def _set_mode(self, mode: str, save: bool = True) -> None:
        self.mode = mode
        self.mode_btns[mode].setChecked(True)
        self.sel_key = None
        live_i18n.call(self.src_label.setText, {
            "apps": tr("window.programs_with_graphics_like_system")
                    + self.wm.label(),
            "windows": self.wm.label(),
            "procs": tr("window.all_your_processes_have_launch"),
        }[mode])
        if save:
            self.cfg["view"] = mode
            self.save_timer.start()
        self.refresh()

    def refresh(self) -> None:
        if self.picking:
            return
        self.procs = scan_procs()
        prune_gui_cache(self.procs)
        self._refreshing = True       # ответ, пришедший сразу, попадёт в ближайший _build
        self.wm.request_windows(self._windows_arrived)
        self._refreshing = False
        self._build()

    def _windows_arrived(self, wins) -> None:
        if wins is None or wins == self.windows:
            return
        self.windows = wins
        if not self._refreshing and not self.picking:
            self._build()  # асинхронный ответ (KDE) — список уже показан, обновляем

    def _build(self) -> None:
        self.entries = build_entries(self.mode, self.procs, self.windows)
        self.by_key = {e["key"]: e for e in self.entries}
        self._rebuild_list()

    def _rebuild_list(self, *_) -> None:
        q = self.search.text().strip().lower()
        sb = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        cur = None
        for e in self.entries:
            hay = live_i18n.format_text('{0} {1} {2} {3} {4}', e['title'], e['cls'], e['pid'] or '', e['cmd'], e.get('wtitles', '')).lower()
            if q and q not in hay:
                continue
            it = live_i18n.call(QListWidgetItem, e["text"])
            it.setData(Qt.ItemDataRole.UserRole, e["key"])
            live_i18n.call(self.list.addItem, it)
            if e["key"] == self.sel_key:
                cur = it
        if cur:
            self.list.setCurrentItem(cur)
        self.list.blockSignals(False)
        self.list.verticalScrollBar().setValue(sb)
        if self.sel_key not in self.by_key:
            self.sel_key = None
        self._show_details()

    def _on_select(self) -> None:
        items = self.list.selectedItems()
        self.sel_key = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        self._show_details()

    def _show_details(self) -> None:
        e = self.by_key.get(self.sel_key)
        tree_on = self.tree_btn.isChecked()
        live_i18n.call(self.close_btn.setText, tr("window.close_whole_tree") if tree_on else tr("window.close"))
        live_i18n.call(self.kill_btn.setText, tr("window.kill_whole_tree") if tree_on else tr("window.force"))
        if not e:
            live_i18n.call(self.d_title.setText, tr("window.no_window_selected") if self.mode == "windows" else tr("window.no_process_selected"))
            live_i18n.call(self.d_info.setText, "")
            self._clear_tree()
            self.close_btn.setEnabled(False)
            self.kill_btn.setEnabled(False)
            self.show_btn.setEnabled(False)
            return
        pid = e["pid"]
        p = self.procs.get(pid) if pid else None
        live_i18n.call(self.d_title.setText, e["title"] or p["name"] if p else (e["title"] or tr("common.untitled")))
        live_i18n.call(self.d_info.setText, self._details_text(e, p))
        self.show_btn.setEnabled(True)
        alive = bool(p)
        self.close_btn.setEnabled(alive or e["wid"] is not None)
        self.kill_btn.setEnabled(alive)
        if alive:
            self._fill_tree(pid)
        else:
            self._clear_tree()

    def _details_text(self, e: dict, p) -> str:
        pid = e["pid"]
        head = live_i18n.format_text('PID: {0}', pid or tr('window.pid_unknown'))
        if p:
            head += tr("window.process", p['name'])
            if p["state"] in STATE_MARK:
                head += STATE_MARK[p["state"]]
        if e["cls"]:
            head += tr("window.class", e['cls'])
        lines = [head]
        if pid:
            lines.append(tr("window.command_label") + (cmdline(pid)[:300] or "—"))
            cwd = proc_cwd(pid)
            if cwd:
                lines.append(tr("window.working_folder") + cwd)
        else:
            lines.append(tr("window.pid_unknown_only_polite_window"))
        if e.get("wtitles"):
            lines.append(tr("window.windows_label") + e["wtitles"][:200])
        return live_i18n.join_text('\n', (lines))

    def _clear_tree(self) -> None:
        self.tree.clear()
        live_i18n.call(self.tree_count.setText, "")
        self._tree_sig = None

    def _fill_tree(self, pid: int) -> None:
        pids = tree_pids(pid, self.procs)
        live_i18n.call(self.tree_count.setText, tr("window.total_processes", len(pids)))
        sig = (pid, tuple(pids))
        if sig == self._tree_sig:
            return  # дерево не изменилось — не перестраиваем (сохраняется прокрутка и выделение)
        self._tree_sig = sig
        self.tree.clear()
        nodes: dict = {}
        for q in pids[:600]:
            pr = self.procs[q]
            it = live_i18n.call(QTreeWidgetItem, [pr["name"], str(q), cmdline(q)[:200]])
            parent = nodes.get(pr["ppid"])
            if parent is not None and q != pid:
                parent.addChild(it)
            else:
                self.tree.addTopLevelItem(it)
            nodes[q] = it
        self.tree.expandAll()

    # --- показать окно выбранного пункта
    def _on_click(self) -> None:
        if self.cfg["reveal"]:
            self.reveal(False)

    def reveal(self, explicit: bool) -> None:
        e = self.by_key.get(self.sel_key)
        if not e:
            return
        pid = e["pid"]
        label = e["label"] or e["cls"] or pid
        tree = tree_pids(pid, self.procs) if pid in self.procs else []

        def done(result) -> None:
            if result == REVEAL_SHOWN:
                self._toast(tr("window.window_shown", label))
            elif result == REVEAL_NO_REPLY:
                self._toast(tr("window.kwin_did_not_respond_could"))
            elif result == REVEAL_NO_WINDOW:
                self._toast(tr("window.has_no_open_window_may", label))
            elif result == REVEAL_FAILED or explicit:
                self._toast(tr("window.could_not_bring_window_front"))
            else:
                self._toast(tr("window.program_s_window_not_visible"))
        self.wm.request_reveal(e["wid"], pid, tree, self.windows, done)

    # --- выбор окна
    def start_pick(self) -> None:
        if self.mode == "procs":
            self._set_mode("apps")
        if not self.wm.has_windows:
            self._toast(tr("window.picking_window_by_click_not"))
            return
        hide = bool(self.cfg["hide"])
        self.pick_btn.setEnabled(False)
        if self.wm.can_pick_by_click():
            self._toast(tr("window.click_window_you_need"))
        else:
            self._toast(tr("window.click_window_you_need_program"))
        if hide:
            self.hide()
        self.picker.start(hide)

    def _pick_done(self, info) -> None:
        wid = info["wid"] if info else None
        self.pick_btn.setEnabled(True)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.refresh()
        pid = (info or {}).get("pid")
        if pid is None and wid is not None:
            pid = next((w["pid"] for w in self.windows if w["wid"] == wid), None)
        if pid is None and wid is not None:
            pid = self.wm.pid_of(wid)  # кликнули по дочернему окну — узнаём процесс
        if pid == os.getpid():
            self._toast(tr("window.program_s_own_window_was"))
            return
        key = self._entry_for(wid, pid)
        if key not in self.by_key:
            self._toast(tr("window.window_not_identified_try_again"))
            return
        self.sel_key = key
        self._rebuild_list()
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.list.scrollToItem(self.list.item(i))
                break
        self._toast(tr("window.selected", self.by_key[key]['label'] or self.by_key[key]['cls']))

    def _entry_for(self, wid, pid):
        """Ключ пункта списка, к которому относится выбранное окно (или None)."""
        if self.mode == "windows":
            return live_i18n.format_text('w:{0}', wid) if live_i18n.format_text('w:{0}', wid) in self.by_key else None
        if pid:
            cand = [e for e in self.entries if e["pid"] and pid in tree_pids(e["pid"], self.procs)]
            return cand[0]["key"] if cand else None
        return None

    # --- закрытие
    def _ask(self, text: str) -> bool:
        box = QMessageBox(self)
        live_i18n.call(box.setWindowTitle, tr("window.confirmation"))
        live_i18n.call(box.setText, text)
        yes = live_i18n.call(box.addButton, tr("window.yes"), QMessageBox.ButtonRole.AcceptRole)
        no = live_i18n.call(box.addButton, tr("window.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no)
        box.exec()
        return box.clickedButton() is yes

    def act(self, force: bool) -> None:
        e = self.by_key.get(self.sel_key)
        if not e:
            self._toast(tr("window.first_select_window_process_list"))
            return
        tree = self.tree_btn.isChecked()
        pid = e["pid"]
        pname = (self.procs.get(pid) or {}).get("name", "")
        name = e["title"] or pname or tr("window.process_word")
        if len(name) > 60:
            name = name[:57] + "…"
        if not force and not tree and e["wid"] is not None:
            self._close_window(e["wid"], pid, name)
        else:
            self._signal_processes(pid, name, force, tree)

    def _close_window(self, wid, pid, name: str) -> None:
        """Вежливое закрытие одного окна — как нажатие на крестик; не вышло — SIGTERM процессу."""
        def done(ok: bool) -> None:
            if ok:
                self._toast(tr("window.window_was_asked_close_if", name))
            elif pid in self.procs:
                send_signal([pid], signal.SIGTERM)
                self._toast(tr("window.could_not_close_window_directly", name))
            else:
                self._toast(tr("window.could_not_close_window"))
            QTimer.singleShot(1200, self.refresh)
        self.wm.request_close(wid, done)

    def _signal_processes(self, pid, name: str, force: bool, tree: bool) -> None:
        if not pid or pid not in self.procs:
            self._toast(tr("window.process_not_found_may_have"))
            self.refresh()
            return
        pids = tree_pids(pid, self.procs) if tree else [pid]
        me = os.getpid()
        pids = [p for p in pids if p > 1 and p != me]
        if not pids:
            self._toast(tr("window.program_itself_system_process_not"))
            return
        sig = signal.SIGKILL if force else signal.SIGTERM
        if (force or tree) and self.cfg["confirm"]:
            msg = (tr("window.force_terminate") if force else tr("window.ask_terminate")) + live_i18n.format_text(' «{0}» (PID {1})', name, pid)
            if len(pids) > 1:
                msg += tr("window.more_child_processes", len(pids) - 1)
            msg += "?" + (tr("window.unsaved_data_will_lost") if force else "")
            if not self._ask(msg):
                return
        ok, denied = send_signal(pids, sig)
        text = tr("window.sent_proc", 'SIGKILL' if force else 'SIGTERM', ok)
        if denied:
            text += tr("window.no_permission_pid", live_i18n.join_text(', ', (map(str, denied[:5]))))
        if not force:
            text += tr("window.if_did_not_close_use")
        self._toast(text)
        QTimer.singleShot(900, self.refresh)

    def _toast(self, text: str) -> None:
        live_i18n.call(self.toast.setText, text if len(text) <= 200 else text[:197] + "…")
        self.toast_timer.start()

    # --- тема / настройки
    def _opt(self, key: str, val) -> None:
        self.cfg[key] = val
        self.save_timer.start()
        if key == "tree":
            self._show_details()

    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
        self.save()

    def save(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def closeEvent(self, e) -> None:
        self.save()
        super().closeEvent(e)
