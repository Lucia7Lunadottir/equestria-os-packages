from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QVBoxLayout, QWidget

from equestria_ue.config import DEFAULTS
from equestria_ue.kit import tr
from equestria_ue.launcher import zen_reachable
from equestria_ue.paths import CACHE_DIR
from equestria_ue.ui.widgets import card_frame, scrolled, small_btn, title_row


def setting_card(title: str, hint: str, *widgets) -> QFrame:
    f = card_frame()
    v = QVBoxLayout(f)
    v.setContentsMargins(20, 14, 20, 14)
    v.setSpacing(8)
    t = QLabel(title)
    t.setObjectName("rowname")
    v.addWidget(t)
    if hint:
        h = QLabel(hint)
        h.setObjectName("hint")
        h.setWordWrap(True)
        v.addWidget(h)
    for w in widgets:
        v.addLayout(w) if hasattr(w, "addWidget") else v.addWidget(w)
    return f


class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        cfg = win.cfg
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)
        outer.addLayout(title_row(tr("Настройки")))
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(12)

        self.inst = QLineEdit(cfg["install_dir"])
        self.inst.editingFinished.connect(self._save_paths)
        br = small_btn(tr("Обзор…"))
        br.clicked.connect(self._browse_inst)
        r = QHBoxLayout()
        r.addWidget(self.inst, 1)
        r.addWidget(br)
        v.addWidget(setting_card(tr("Папка установки движков"), tr("Сюда по умолчанию ставятся и распаковываются версии."), r))

        self.dirs = QListWidget()
        self.dirs.setObjectName("grid")
        self.dirs.setFixedHeight(120)
        self.dirs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for d in cfg["project_dirs"]:
            self.dirs.addItem(d)
        add = small_btn(tr("＋ Добавить"))
        add.clicked.connect(self._add_dir)
        rm = small_btn(tr("Убрать выбранную"))
        rm.clicked.connect(self._rm_dir)
        r2 = QHBoxLayout()
        r2.addWidget(add)
        r2.addWidget(rm)
        r2.addStretch()
        v.addWidget(setting_card(tr("Папки с проектами"), tr("Лаунчер ищет в них файлы .uproject (до 4 уровней вглубь)."),
                                 self.dirs, r2))

        access = QComboBox()
        access.addItem(tr("SSH — ключ добавлен в GitHub"), "ssh")
        access.addItem(tr("HTTPS — токен или gh auth setup-git"), "https")
        access.setCurrentIndex(access.findData(cfg["access"]))
        access.activated.connect(lambda i: self._set("access", access.itemData(i)))
        v.addWidget(setting_card(tr("Доступ к GitHub"), tr("Как лаунчер обращается к репозиторию EpicGames/UnrealEngine."), access))

        sdl = QComboBox()
        sdl.addItem(tr("Авто"), "auto")
        sdl.addItem(tr("X11 / Xwayland — рекомендуется на Wayland"), "x11")
        sdl.addItem(tr("Wayland — НЕ использовать: в UE 5.7 падает (сегфолт в Vulkan)"), "wayland")
        sdl.setCurrentIndex(sdl.findData(cfg["sdl"]))
        sdl.activated.connect(lambda i: self._set("sdl", sdl.itemData(i)))
        args = QLineEdit(cfg["args"])
        args.setPlaceholderText(tr("Доп. аргументы редактора, например: -vulkan"))
        args.editingFinished.connect(lambda: self._set("args", args.text().strip()))
        cb5 = QCheckBox(tr("Отключить всплывающие подсказки редактора (лечит «клик со второго раза» на KDE)"))
        cb5.setChecked(cfg["no_tooltips"])
        cb5.toggled.connect(lambda on: self._set("no_tooltips", on))
        v.addWidget(setting_card(tr("Запуск редактора"),
                                 tr("Редактор Unreal под Wayland стабильнее всего работает через Xwayland (SDL_VIDEODRIVER=x11)."),
                                 sdl, args, cb5))

        cb1 = QCheckBox(tr("Записывать движки в Epic Install.ini (видны UnrealVersionSelector и др.)"))
        cb1.setChecked(cfg["sync_ini"])
        cb1.toggled.connect(lambda on: (self._set("sync_ini", on), win.reload_engines()))
        cb2 = QCheckBox(tr("Предлагать установку недостающих пакетов через pacman перед сборкой"))
        cb2.setChecked(cfg["deps"])
        cb2.toggled.connect(lambda on: self._set("deps", on))
        ddc = QLineEdit(cfg["ddc"])
        ddc.editingFinished.connect(lambda: self._set("ddc", ddc.text().strip() or DEFAULTS["ddc"]))
        mode = QComboBox()
        mode.addItem(tr("Авто — Zen, если доступен, иначе папка на диске (рекомендуется)"), "auto")
        mode.addItem(tr("Zen — локальный сервер кеша Unreal (нужен IPv6 на loopback)"), "zen")
        mode.addItem(tr("Папка на диске — указанная ниже"), "files")
        mode.addItem(tr("Только в памяти — шейдеры компилируются заново при каждом запуске"), "memory")
        mode.setCurrentIndex(max(0, mode.findData(cfg["ddc_mode"])))
        mode.activated.connect(lambda i: self._set("ddc_mode", mode.itemData(i)))
        zen = QLabel(tr("Zen доступен.") if zen_reachable() else
                     tr("IPv6 на loopback выключен — Zen недоступен, в режиме «Авто» кеш хранится в папке на диске."))
        zen.setObjectName("hint")
        zen.setWordWrap(True)
        threads = QComboBox()
        threads.addItem(tr("Почти все потоки процессора (быстрее)"), "fast")
        threads.addItem(tr("Как в Unreal по умолчанию (половина потоков)"), "ue")
        threads.setCurrentIndex(max(0, threads.findData(cfg["shader_threads"])))
        threads.activated.connect(lambda i: self._set("shader_threads", threads.itemData(i)))
        v.addWidget(setting_card(tr("Кеш и компиляция шейдеров"),
                                 tr("Скомпилированные шейдеры сохраняются в кеш Derived Data (DDC): при следующем запуске "
                                    "они берутся оттуда, а не компилируются заново. Папка должна быть на диске с правом "
                                    "записи (не NTFS без прав). Журнал редактора: {}", f"{CACHE_DIR}/editor.log"),
                                 mode, zen, ddc, threads))
        rt = QComboBox()
        rt.addItem(tr("Трассировка лучей — как в проекте"), "project")
        rt.addItem(tr("Без трассировки лучей в редакторе (меньше видеопамяти, стабильнее на Vulkan)"), "off")
        rt.setCurrentIndex(max(0, rt.findData(cfg["ray_tracing"])))
        rt.activated.connect(lambda i: self._set("ray_tracing", rt.itemData(i)))
        cb7 = QCheckBox(tr("Встроенный браузер Unreal (окно Fab) — с ускорением на видеокарте"))
        cb7.setChecked(cfg["cef_gpu"])
        cb7.toggled.connect(lambda on: self._set("cef_gpu", on))
        cb4 = QCheckBox(tr("Запускать на дискретной NVIDIA (PRIME offload) — для ноутбуков с двумя видеокартами"))
        cb4.setChecked(cfg["prime"])
        cb4.toggled.connect(lambda on: self._set("prime", on))
        v.addWidget(setting_card(tr("Видеокарта"),
                                 tr("Если вьюпорт пустой или интерфейс тормозит — редактор мог запуститься на встроенной "
                                    "графике или без Vulkan-драйвера (llvmpipe).") + "\n" +
                                 tr("Без трассировки лучей Lumen работает программно: файлы проекта не меняются, "
                                    "шейдеры один раз компилируются заново. Ускорение встроенного браузера выключено, "
                                    "потому что на Linux его GPU-процесс падает по кругу."), cb4, rt, cb7))
        cb6 = QCheckBox(tr("Сворачивать в трей при закрытии окна (загрузки и сборка продолжаются)"))
        cb6.setChecked(cfg["tray"])
        cb6.toggled.connect(lambda on: (self._set("tray", on), win.set_tray(on)))
        v.addWidget(setting_card(tr("Прочее"), tr("Редактор Unreal не закрывается вместе с лаунчером — он запущен отдельно."),
                                 cb6, cb1, cb2))
        v.addStretch()
        outer.addWidget(scrolled(body), 1)

    def _set(self, k, val) -> None:
        self.win.cfg[k] = val
        self.win.cfg.save()

    def _save_paths(self) -> None:
        self._set("install_dir", self.inst.text().strip() or DEFAULTS["install_dir"])

    def _browse_inst(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Папка установки"), self.inst.text())
        if d:
            self.inst.setText(d)
            self._save_paths()

    def _add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Папка с проектами"), str(Path.home()))
        if d and d not in self.win.cfg["project_dirs"]:
            self.dirs.addItem(d)
            self._sync_dirs()

    def _rm_dir(self) -> None:
        for it in self.dirs.selectedItems():
            self.dirs.takeItem(self.dirs.row(it))
        self._sync_dirs()

    def _sync_dirs(self) -> None:
        self._set("project_dirs", [self.dirs.item(i).text() for i in range(self.dirs.count())])
        self.win.reload_projects()
