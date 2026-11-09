from __future__ import annotations

from equestria_kit import live_i18n

from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget

from equestria_ue.engines import Engine
from equestria_ue.fab import fab_installed, fab_steps, parse_fab_zip
from equestria_ue.jobs import Job, Step
from equestria_ue.kit import tr
from equestria_ue.launcher import launch_editor
from equestria_ue.steps import build_chain, update_steps
from equestria_ue.ui.widgets import card_frame, chip, open_folder, scrolled, small_btn, title_row
from equestria_ue.versions import latest_patch, vstr
from equestria_ue.webengine import HAVE_WEB


class EnginesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(14)
        b_cat = small_btn(tr("engines_page.install_version"), name="primary")
        b_cat.clicked.connect(lambda: win.go("catalog"))
        v.addLayout(title_row("Unreal Engine", b_cat))
        self.body = QWidget()
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(0, 0, 8, 0)
        self.lay.setSpacing(12)
        v.addWidget(scrolled(self.body), 1)
        self.rebuild()

    def rebuild(self) -> None:
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.win.engines:
            e = live_i18n.call(QLabel, tr("engines_page.no_engines_installed_open_catalog"))
            e.setObjectName("hint")
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lay.addWidget(e)
        for eng in sorted(self.win.engines, key=lambda e: e.version, reverse=True):
            self.lay.addWidget(self._card(eng))
        self.lay.addStretch()

    def _card(self, eng: Engine) -> QFrame:
        win = self.win
        f = card_frame()
        h = QHBoxLayout(f)
        h.setContentsMargins(20, 16, 20, 16)
        h.setSpacing(16)
        big = live_i18n.call(QLabel, eng.ver)
        big.setObjectName("big")
        big.setMinimumWidth(110)
        col = QVBoxLayout()
        col.setSpacing(4)
        name = live_i18n.call(QLabel, eng.title)
        name.setObjectName("rowname")
        path = live_i18n.call(QLabel, eng.path)
        path.setObjectName("hint")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.addWidget(chip(tr("engines_page.built") if eng.built else tr("engines_page.not_built"), "ok" if eng.built else "fail"))
        chips.addWidget(chip(tr("engines_page.from_source") if eng.git else tr("engines_page.prebuilt")))
        has_fab = fab_installed(eng)
        chips.addWidget(chip(tr("engines_page.fab_installed") if has_fab else tr("engines_page.no_fab"), "ok" if has_fab else "warn"))
        upd = None
        src = win.versions if eng.git else win.store.builds
        if src:
            lp = latest_patch(src, eng.version)
            if lp and lp > eng.version:
                upd = lp
                chips.addWidget(chip(tr("engines_page.available", vstr(lp)), "warn"))
        chips.addStretch()
        col.addWidget(name)
        col.addWidget(path)
        col.addLayout(chips)
        h.addWidget(big)
        h.addLayout(col, 1)
        run = live_i18n.call(QPushButton, tr("engines_page.launch_editor"))
        run.setObjectName("primary")
        run.setEnabled(eng.built)
        run.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        run.clicked.connect(lambda: self._run(eng))
        h.addWidget(run)
        if upd:
            ub = live_i18n.call(QPushButton, tr("engines_page.update", vstr(upd)))
            ub.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            ub.clicked.connect(lambda: self._update(eng, upd))
            h.addWidget(ub)
        if eng.built and not has_fab:
            fb = live_i18n.call(QPushButton, tr("engines_page.install_fab"))
            fb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            live_i18n.call(fb.setToolTip, tr("engines_page.fab_epic_s_asset_store"))
            fb.clicked.connect(lambda: self.install_fab(eng))
            h.addWidget(fb)
        more = small_btn("⋯")
        more.clicked.connect(lambda: self._menu(eng, upd).exec(more.mapToGlobal(more.rect().bottomLeft())))
        h.addWidget(more)
        return f

    def _run(self, eng: Engine) -> None:
        err = launch_editor(self.win.cfg, eng)
        if err:
            QMessageBox.warning(self, tr("common.could_not_launch"), err)

    def _update(self, eng: Engine, upd: tuple) -> None:
        win = self.win
        if eng.git:
            win.add_job(Job(tr("engines_page.updating", vstr(upd)), update_steps(win.cfg, eng.path, upd), win.reload_engines), True)
        else:
            win.store.request(upd)      # скачает новую готовую сборку и подключит рядом со старой

    def _menu(self, eng: Engine, upd) -> QMenu:
        m = QMenu(self)
        if upd:
            live_i18n.call(m.addAction, tr("engines_page.update", vstr(upd))).triggered.connect(lambda: self._update(eng, upd))
        if eng.git:
            live_i18n.call(m.addAction, tr("engines_page.rebuild_setup_generate_make")).triggered.connect(
                lambda: self.win.add_job(Job(tr("common.building", eng.title), build_chain(eng.path), self.win.reload_engines), True))
        live_i18n.call(m.addAction, tr("engines_page.reinstall_fab") if fab_installed(eng) else tr("engines_page.install_fab")).triggered.connect(
            lambda: self.install_fab(eng))
        live_i18n.call(m.addAction, tr("engines_page.install_fab_from_zip_archive")).triggered.connect(lambda: self.fab_from_zip(eng))
        live_i18n.call(m.addAction, tr("common.show_folder")).triggered.connect(lambda: open_folder(eng.path))
        m.addSeparator()
        live_i18n.call(m.addAction, tr("engines_page.remove_from_launcher_files_stay")).triggered.connect(lambda: self._forget(eng))
        live_i18n.call(m.addAction, tr("engines_page.delete_from_disk")).triggered.connect(lambda: self._delete(eng))
        return m

    def install_fab(self, eng: Engine) -> None:
        st = self.win.store
        if st.fab.get(eng.version[:2]):
            st.request_fab(eng)             # скачает архив с unrealengine.com/linux и поставит плагин
            return
        if HAVE_WEB and st.builds:          # вход есть, но Fab для этой версии на странице не нашёлся
            QMessageBox.information(self, tr("engines_page.fab_not_found"), tr(
                "engines_page.epic_linux_page_has_no", eng.short))
            self.win.go("store")
            return
        if HAVE_WEB:
            st.status = tr("engines_page.sign_your_epic_account_launcher")
            st.changed.emit()
            self.win.go("store")
            return
        QDesktopServices.openUrl(QUrl("https://www.unrealengine.com/linux"))
        QMessageBox.information(self, tr("engines_page.installing_fab"), tr(
            "engines_page.page_opens_find_linux_fab", eng.short))

    def fab_from_zip(self, eng: Engine) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("engines_page.fab_plugin_archive"), str(Path.home() / "Downloads"),
                                              tr("engines_page.fab_archives_linux_fab_zip"))
        if not path:
            return
        p = parse_fab_zip(Path(path).name)
        if p and p[0] != eng.version[:2] and QMessageBox.question(self, tr("engines_page.different_version"), tr(
                "engines_page.archive_made_unreal_engine_but",
                vstr(p[0]), eng.short)) != QMessageBox.StandardButton.Yes:
            return
        self.win.add_job(Job(tr("common.fab_plugin", eng.title), fab_steps(path, eng, False)), True)

    def _forget(self, eng: Engine) -> None:
        self.win.cfg["engines"] = [e for e in self.win.cfg["engines"] if e["id"] != eng.id]
        self.win.cfg.save()
        self.win.reload_engines()

    def _delete(self, eng: Engine) -> None:
        p = Path(eng.path)
        if len(p.parts) < 3 or not (p / "Engine").is_dir():
            QMessageBox.warning(self, tr("engines_page.refused"), tr("engines_page.path_looks_unsafe_delete"))
            return
        if QMessageBox.question(self, tr("engines_page.delete_engine"),
                                tr("engines_page.folder_will_deleted_permanently_projects", eng.path)) != QMessageBox.StandardButton.Yes:
            return
        self._forget(eng)
        self.win.add_job(Job(tr("engines_page.deleting", eng.title), [Step(tr("engines_page.deleting_files"), ["rm", "-rf", eng.path])]), True)
