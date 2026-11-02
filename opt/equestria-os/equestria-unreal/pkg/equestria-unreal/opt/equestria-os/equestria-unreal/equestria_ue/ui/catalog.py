from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget

from equestria_ue.config import Config
from equestria_ue.engines import find_engine_root
from equestria_ue.fab import engine_for_fab, fab_steps, parse_fab_zip
from equestria_ue.jobs import Job
from equestria_ue.kit import tr
from equestria_ue.steps import download_steps, install_steps, zip_steps
from equestria_ue.ui.widgets import card_frame, chip, scrolled, small_btn, title_row
from equestria_ue.versions import PREBUILT_SEED, PREBUILT_SIZE, STATIC_VERSIONS, explain_git_error, latest_patch, missing_deps, vstr
from equestria_ue.webengine import HAVE_WEB


UE_GITHUB_HELP = "https://www.unrealengine.com/en-US/ue-on-github"


class InstallDialog(QDialog):
    def __init__(self, parent, ver: tuple, default_dir: str, cfg: Config):
        super().__init__(parent)
        self.setWindowTitle(tr("Установка Unreal Engine {}", vstr(ver)))
        self.setMinimumWidth(620)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        t = QLabel(f"Unreal Engine {vstr(ver)}")
        t.setObjectName("title")
        info = QLabel(tr("Движок будет скачан из исходников Epic (git, ветка релиза) и собран на этом компьютере. "
                         "Обычно это 100–200 ГБ на диске и от 1 до нескольких часов — окно можно закрыть, лаунчер "
                         "продолжит работу в фоне."))
        info.setObjectName("hint")
        info.setWordWrap(True)
        self.path = QLineEdit(default_dir)
        browse = small_btn(tr("Обзор…"))
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        self.space = QLabel("")
        self.space.setObjectName("hint")
        miss = missing_deps(ver[0] == 4)
        self.deps = QCheckBox(tr("Установить недостающие пакеты через pacman: {}", ", ".join(miss) if miss else tr("всё уже есть")))
        self.deps.setChecked(bool(miss) and cfg["deps"])
        self.deps.setEnabled(bool(miss))
        btns = QHBoxLayout()
        cancel = QPushButton(tr("Отмена"))
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton(tr("Установить"))
        self.ok.setObjectName("primary")
        self.ok.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        for w in (t, info, QLabel(tr("Папка установки")),):
            v.addWidget(w)
        v.addLayout(row)
        v.addWidget(self.space)
        v.addWidget(self.deps)
        v.addLayout(btns)
        self.path.textChanged.connect(self._check)
        self._check()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Папка установки"), str(Path(self.path.text()).parent))
        if d:
            self.path.setText(d)

    def _check(self) -> None:
        p = Path(self.path.text().strip() or "/nonexistent")
        base = p
        while not base.exists() and base != base.parent:
            base = base.parent
        try:
            free = shutil.disk_usage(base).free / 1e9
        except OSError:
            free = 0
        bad = p.exists() and any(p.iterdir()) and not (p / ".git").exists()
        txt = tr("Свободно на диске: {:.0f} ГБ", free) + (tr("  —  маловато, нужно ≥ 150 ГБ") if free < 150 else "")
        if bad:
            txt = tr("Папка не пуста и не содержит git-репозитория движка — выберите другую.")
        self.space.setText(txt)
        self.ok.setEnabled(not bad and bool(self.path.text().strip()))

    def values(self):
        return self.path.text().strip(), self.deps.isChecked()


class CatalogPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(14)
        v.addLayout(title_row(tr("Каталог версий")))
        hero = card_frame("hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(8)
        t0 = QLabel(tr("Самый простой путь — готовая сборка от Epic (без GitHub)"))
        t0.setObjectName("rowname")
        t0.setWordWrap(True)
        h0 = QLabel(tr("Epic выдаёт готовый архив Unreal Engine для Linux (20+ ГБ) на своём сайте — нужен только "
                       "Epic-аккаунт и принятая лицензия. Нажмите «Скачать» у нужной версии, скачайте архив на сайте — "
                       "лаунчер покажет полоску загрузки и сам предложит распаковать и подключить движок. Можно и "
                       "вставить прямую ссылку — тогда качает сам лаунчер, с докачкой."))
        h0.setObjectName("hint")
        h0.setWordWrap(True)
        self.prebuilt = QPushButton(tr("Войти в Epic / открыть магазин") if HAVE_WEB else tr("Скачать готовую сборку на сайте Epic"))
        self.prebuilt.setObjectName("primary")
        self.prebuilt.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prebuilt.clicked.connect(lambda: win.go("store") if HAVE_WEB else self.open_prebuilt())
        self.watch_lbl = QLabel("")
        self.watch_lbl.setObjectName("hint")
        self.watch_bar = QProgressBar()
        self.watch_bar.setRange(0, 1000)
        self.watch_bar.setVisible(False)
        urlb = small_btn(tr("Скачать по ссылке…"), tr("Правый клик по Download на сайте → «Копировать адрес ссылки»"))
        urlb.clicked.connect(self.from_url)
        zipb = small_btn(tr("Из архива .zip…"))
        zipb.clicked.connect(self.from_zip)
        fold = small_btn(tr("Из готовой папки…"))
        fold.clicked.connect(self.from_folder)
        r0 = QHBoxLayout()
        r0.setSpacing(8)
        for b in (self.prebuilt, urlb, zipb, fold):
            r0.addWidget(b)
        r0.addStretch()
        hl.addWidget(t0)
        hl.addWidget(h0)
        hl.addLayout(r0)
        hl.addWidget(self.watch_lbl)
        hl.addWidget(self.watch_bar)
        sep = QLabel(tr("Другой путь — сборка из исходников (любая версия, нужен доступ к GitHub Epic)"))
        sep.setObjectName("rowname")
        sep.setWordWrap(True)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.check = QPushButton(tr("Проверить доступ и обновить список"))
        self.check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.check.clicked.connect(lambda: win.fetch_versions(True))
        how = small_btn(tr("Как получить доступ"))
        how.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(UE_GITHUB_HELP)))
        for b in (self.check, how):
            row.addWidget(b)
        row.addStretch()
        hl.addSpacing(6)
        hl.addWidget(sep)
        hl.addWidget(self.status)
        hl.addLayout(row)
        v.addWidget(hero)
        self.body = QWidget()
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(0, 0, 8, 0)
        self.lay.setSpacing(8)
        v.addWidget(scrolled(self.body), 1)
        self.rebuild()

    def rebuild(self) -> None:
        win = self.win
        self.check.setEnabled(not win.checking)
        self.check.setText(tr("Проверяю…") if win.checking else tr("Проверить доступ и обновить список"))
        if win.access_ok is True:
            self.status.setText(tr("✓ Доступ к репозиторию Epic есть · найдено версий: {}", len(win.versions or [])))
        elif win.access_ok is False:
            self.status.setText("✗ " + explain_git_error(win.versions_err))
        else:
            self.status.setText(tr("Доступ к GitHub ещё не проверялся. Ниже — встроенный список версий."))
        if HAVE_WEB:
            self.watch_lbl.setText(win.store.status)
            have_v = [e.version for e in win.engines]
            ups = [f"{vstr(h)} → {vstr(b)}" for h in have_v for b in [latest_patch(win.store.builds, h)] if b and b > h]
            if ups:
                self.watch_lbl.setText(tr("⬆ Есть обновления: {} — нажмите «Скачать» у новой версии.", ", ".join(ups)))
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        versions = set(win.versions or STATIC_VERSIONS) | (set(win.store.builds) if win.store.builds else PREBUILT_SEED)
        have = {e.version for e in win.engines}
        major = None
        for ver in sorted(versions, reverse=True):
            if ver[0] != major:
                major = ver[0]
                h = QLabel(f"Unreal Engine {major}")
                h.setObjectName("h2")
                self.lay.addWidget(h)
            self.lay.addWidget(self._row(ver, ver in have))
        self.lay.addStretch()

    def _row(self, ver: tuple, installed: bool) -> QFrame:
        f = card_frame()
        h = QHBoxLayout(f)
        h.setContentsMargins(18, 10, 14, 10)
        h.setSpacing(12)
        n = QLabel(f"Unreal Engine {vstr(ver)}")
        n.setObjectName("rowname")
        h.addWidget(n)
        if installed:
            h.addWidget(chip(tr("Установлен"), "ok"))
        h.addStretch()
        if installed:
            b = small_btn(tr("Установлен"))
            b.setEnabled(False)
            h.addWidget(b)
        else:
            if ver[0] >= 5:
                d = small_btn(tr("Скачать (готовая, ~37 ГБ)"), name="primary")
                d.clicked.connect(lambda: self.get_prebuilt(ver))
                h.addWidget(d)
            b = small_btn(tr("Собрать из исходников"))
            b.clicked.connect(lambda: self.install(ver))
            h.addWidget(b)
        return f

    def get_prebuilt(self, ver: tuple) -> None:
        if HAVE_WEB:
            self.win.store.request(ver)
        else:
            self.open_prebuilt(ver)

    PARTIAL = ("*.crdownload", "*.part", "*.opdownload", "*.download")

    def open_prebuilt(self, ver=None) -> None:
        QDesktopServices.openUrl(QUrl("https://www.unrealengine.com/linux"))
        self.dl_dir = Path.home() / "Downloads"
        self.seen = {p: p.stat().st_size for p in self._zips()}
        self.last = {}
        self.prev = (0, 0.0)
        if not hasattr(self, "timer"):
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._poll)
        self.timer.start(1500)
        want = f" Linux_Unreal_Engine_{vstr(ver)}.zip" if ver else ""
        self.watch_lbl.setText(tr("⏳ Жду загрузку{} в {} — нажмите Download на сайте Epic.", want, self.dl_dir))

    def _zips(self) -> list:
        try:
            return list(self.dl_dir.glob("*.zip"))
        except OSError:
            return []

    def _partials(self) -> list:
        out = []
        try:
            for pat in self.PARTIAL:
                out += [p for p in self.dl_dir.glob(pat) if p.stat().st_size > 0]
        except OSError:
            pass
        return out

    def _poll(self) -> None:
        import time
        parts = self._partials()
        if parts:
            p = max(parts, key=lambda x: x.stat().st_size)
            size = p.stat().st_size
            now = time.time()
            sp = (size - self.prev[0]) / max(now - self.prev[1], 0.1) / 1e6 if self.prev[1] else 0
            self.prev = (size, now)
            self.watch_bar.setVisible(True)
            self.watch_bar.setValue(int(min(size / PREBUILT_SIZE, 1) * 1000))
            self.watch_lbl.setText(tr("⬇ {} — {:.2f} из ≈{:.0f} ГБ · {:.0f} МБ/с", p.name.rsplit(".", 1)[0], size / 1e9,
                                      PREBUILT_SIZE / 1e9, max(sp, 0)))
            return
        self.watch_bar.setVisible(False)
        for p in self._zips():
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if self.seen.get(p) == size or size < 2 * 1024 ** 3:
                continue
            if self.last.get(p) == size:          # размер не меняется — файл докачан
                self.timer.stop()
                self.watch_lbl.setText("")
                self.seen[p] = size
                if QMessageBox.question(self, tr("Архив скачан"),
                                        tr("Найден архив {} ({:.1f} ГБ). Распаковать и подключить как движок?",
                                           p.name, size / 1e9)) == QMessageBox.StandardButton.Yes:
                    self.import_zip(str(p))
                return
            self.last[p] = size

    def from_url(self) -> None:
        from urllib.parse import unquote, urlparse
        from PyQt6.QtWidgets import QInputDialog
        win = self.win
        url, ok = QInputDialog.getText(self, tr("Скачать по ссылке"), tr("Прямая ссылка на архив (zip):"))
        url = url.strip()
        if not ok or not url.startswith("http"):
            return
        name = Path(unquote(urlparse(url).path)).name or "Linux_Unreal_Engine.zip"
        if not name.lower().endswith(".zip"):
            name += ".zip"
        Path(win.cfg["install_dir"]).mkdir(parents=True, exist_ok=True)
        base = QFileDialog.getExistingDirectory(self, tr("Куда скачать и распаковать"), win.cfg["install_dir"])
        if not base:
            return
        zp, dest = str(Path(base) / name), str(Path(base) / Path(name).stem)

        def done():
            root = find_engine_root(dest)
            if not root:
                raise RuntimeError(tr("в архиве не найдена папка Engine"))
            win.register_engine(root)

        win.add_job(Job(tr("Скачивание {}", name), download_steps(url, zp) + zip_steps(zp, dest), done), True)

    def install(self, ver: tuple) -> None:
        win = self.win
        default = str(Path(win.cfg["install_dir"]) / f"UnrealEngine-{vstr(ver)}")
        dlg = InstallDialog(self, ver, default, win.cfg)
        if not dlg.exec():
            return
        dest, deps = dlg.values()
        win.cfg["deps"] = deps
        win.cfg.save()
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        win.add_job(Job(tr("Установка Unreal Engine {}", vstr(ver)), install_steps(win.cfg, ver, dest),
                        lambda: win.register_engine(dest)), True)

    def from_zip(self) -> None:
        win = self.win
        path, _ = QFileDialog.getOpenFileName(self, tr("Архив Unreal Engine для Linux"), str(Path.home() / "Downloads"),
                                              tr("Архивы (*.zip)"))
        if path:
            self.import_zip(path)

    def import_zip(self, path: str) -> None:
        win = self.win
        if parse_fab_zip(Path(path).name):         # это не движок, а плагин Fab к нему
            eng = engine_for_fab(win.engines, Path(path).name)
            if not eng:
                QMessageBox.warning(self, tr("Нет подходящего движка"),
                                    tr("Архив {} — плагин Fab, но движка этой версии в лаунчере нет.", Path(path).name))
                return
            win.add_job(Job(tr("Плагин Fab для {}", eng.title), fab_steps(path, eng, False)), True)
            return
        Path(win.cfg["install_dir"]).mkdir(parents=True, exist_ok=True)
        base = QFileDialog.getExistingDirectory(self, tr("Куда распаковать"), win.cfg["install_dir"])
        if not base:
            return
        dest = str(Path(base) / Path(path).stem)

        def done():
            root = find_engine_root(dest)
            if not root:
                raise RuntimeError(tr("в архиве не найдена папка Engine"))
            win.register_engine(root)

        win.add_job(Job(tr("Распаковка {}", Path(path).name), zip_steps(path, dest), done), True)

    def from_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Папка с готовым Unreal Engine"), str(Path.home()))
        if not d:
            return
        root = find_engine_root(d)
        if not root:
            QMessageBox.warning(self, tr("Не движок"), tr("В этой папке не найдена структура Engine/…"))
            return
        self.win.register_engine(root)
