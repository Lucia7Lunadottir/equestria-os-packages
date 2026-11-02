from __future__ import annotations

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
        b_cat = small_btn(tr("＋ Установить версию"), name="primary")
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
            e = QLabel(tr("Движки не установлены.\nОткройте «Каталог», чтобы установить Unreal Engine\n"
                          "или добавить готовую сборку."))
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
        big = QLabel(eng.ver)
        big.setObjectName("big")
        big.setMinimumWidth(110)
        col = QVBoxLayout()
        col.setSpacing(4)
        name = QLabel(eng.title)
        name.setObjectName("rowname")
        path = QLabel(eng.path)
        path.setObjectName("hint")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.addWidget(chip(tr("Собран") if eng.built else tr("Не собран"), "ok" if eng.built else "fail"))
        chips.addWidget(chip(tr("из исходников") if eng.git else tr("готовая сборка")))
        has_fab = fab_installed(eng)
        chips.addWidget(chip(tr("Fab установлен") if has_fab else tr("Нет Fab"), "ok" if has_fab else "warn"))
        upd = None
        src = win.versions if eng.git else win.store.builds
        if src:
            lp = latest_patch(src, eng.version)
            if lp and lp > eng.version:
                upd = lp
                chips.addWidget(chip(tr("Доступно {}", vstr(lp)), "warn"))
        chips.addStretch()
        col.addWidget(name)
        col.addWidget(path)
        col.addLayout(chips)
        h.addWidget(big)
        h.addLayout(col, 1)
        run = QPushButton(tr("Запустить редактор"))
        run.setObjectName("primary")
        run.setEnabled(eng.built)
        run.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        run.clicked.connect(lambda: self._run(eng))
        h.addWidget(run)
        if upd:
            ub = QPushButton(tr("Обновить до {}", vstr(upd)))
            ub.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            ub.clicked.connect(lambda: self._update(eng, upd))
            h.addWidget(ub)
        if eng.built and not has_fab:
            fb = QPushButton(tr("Установить Fab"))
            fb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            fb.setToolTip(tr("Fab — магазин ассетов Epic. Плагин добавит в редактор окно Fab "
                             "(кнопка рядом с «Save All» в Content Drawer)."))
            fb.clicked.connect(lambda: self.install_fab(eng))
            h.addWidget(fb)
        more = small_btn("⋯")
        more.clicked.connect(lambda: self._menu(eng, upd).exec(more.mapToGlobal(more.rect().bottomLeft())))
        h.addWidget(more)
        return f

    def _run(self, eng: Engine) -> None:
        err = launch_editor(self.win.cfg, eng)
        if err:
            QMessageBox.warning(self, tr("Не удалось запустить"), err)

    def _update(self, eng: Engine, upd: tuple) -> None:
        win = self.win
        if eng.git:
            win.add_job(Job(tr("Обновление до {}", vstr(upd)), update_steps(win.cfg, eng.path, upd), win.reload_engines), True)
        else:
            win.store.request(upd)      # скачает новую готовую сборку и подключит рядом со старой

    def _menu(self, eng: Engine, upd) -> QMenu:
        m = QMenu(self)
        if upd:
            m.addAction(tr("Обновить до {}", vstr(upd))).triggered.connect(lambda: self._update(eng, upd))
        if eng.git:
            m.addAction(tr("Пересобрать (Setup → Generate → make)")).triggered.connect(
                lambda: self.win.add_job(Job(tr("Сборка {}", eng.title), build_chain(eng.path), self.win.reload_engines), True))
        m.addAction(tr("Переустановить Fab") if fab_installed(eng) else tr("Установить Fab")).triggered.connect(
            lambda: self.install_fab(eng))
        m.addAction(tr("Установить Fab из архива .zip…")).triggered.connect(lambda: self.fab_from_zip(eng))
        m.addAction(tr("Показать в папке")).triggered.connect(lambda: open_folder(eng.path))
        m.addSeparator()
        m.addAction(tr("Убрать из лаунчера (файлы останутся)")).triggered.connect(lambda: self._forget(eng))
        m.addAction(tr("Удалить с диска…")).triggered.connect(lambda: self._delete(eng))
        return m

    def install_fab(self, eng: Engine) -> None:
        st = self.win.store
        if st.fab.get(eng.version[:2]):
            st.request_fab(eng)             # скачает архив с unrealengine.com/linux и поставит плагин
            return
        if HAVE_WEB and st.builds:          # вход есть, но Fab для этой версии на странице не нашёлся
            QMessageBox.information(self, tr("Fab не найден"), tr(
                "На странице Epic для Linux нет архива Fab для Unreal Engine {}. Если он там всё же есть — "
                "скачайте его вручную и выберите «⋯ → Установить Fab из архива .zip…».", eng.short))
            self.win.go("store")
            return
        if HAVE_WEB:
            st.status = tr("Войдите в Epic-аккаунт — лаунчер найдёт на странице архив Fab и снова покажет "
                           "кнопку «Установить Fab» на вкладке «Движки».")
            st.changed.emit()
            self.win.go("store")
            return
        QDesktopServices.openUrl(QUrl("https://www.unrealengine.com/linux"))
        QMessageBox.information(self, tr("Установка Fab"), tr(
            "На открывшейся странице найдите архив Linux_Fab_{}…zip, скачайте его и выберите "
            "«⋯ → Установить Fab из архива .zip…».", eng.short))

    def fab_from_zip(self, eng: Engine) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Архив плагина Fab"), str(Path.home() / "Downloads"),
                                              tr("Архивы Fab (Linux_Fab_*.zip);;Архивы (*.zip)"))
        if not path:
            return
        p = parse_fab_zip(Path(path).name)
        if p and p[0] != eng.version[:2] and QMessageBox.question(self, tr("Другая версия"), tr(
                "Архив сделан для Unreal Engine {}, а движок — {}. Плагин может не загрузиться. Всё равно установить?",
                vstr(p[0]), eng.short)) != QMessageBox.StandardButton.Yes:
            return
        self.win.add_job(Job(tr("Плагин Fab для {}", eng.title), fab_steps(path, eng, False)), True)

    def _forget(self, eng: Engine) -> None:
        self.win.cfg["engines"] = [e for e in self.win.cfg["engines"] if e["id"] != eng.id]
        self.win.cfg.save()
        self.win.reload_engines()

    def _delete(self, eng: Engine) -> None:
        p = Path(eng.path)
        if len(p.parts) < 3 or not (p / "Engine").is_dir():
            QMessageBox.warning(self, tr("Отказ"), tr("Путь выглядит небезопасно для удаления."))
            return
        if QMessageBox.question(self, tr("Удалить движок"),
                                tr("Папка {} будет удалена безвозвратно.\nПроекты в других местах не затронутся.\n\n"
                                   "Удалить?", eng.path)) != QMessageBox.StandardButton.Yes:
            return
        self._forget(eng)
        self.win.add_job(Job(tr("Удаление {}", eng.title), [Step(tr("Удаление файлов"), ["rm", "-rf", eng.path])]), True)
