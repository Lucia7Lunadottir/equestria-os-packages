from __future__ import annotations

from equestria_kit import live_i18n

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
    t = live_i18n.call(QLabel, title)
    t.setObjectName("rowname")
    v.addWidget(t)
    if hint:
        h = live_i18n.call(QLabel, hint)
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
        outer.addLayout(title_row(tr("common.settings")))
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(12)

        self.inst = QLineEdit(cfg["install_dir"])
        self.inst.editingFinished.connect(self._save_paths)
        br = small_btn(tr("common.browse"))
        br.clicked.connect(self._browse_inst)
        r = QHBoxLayout()
        r.addWidget(self.inst, 1)
        r.addWidget(br)
        v.addWidget(setting_card(tr("settings.engine_installation_folder"), tr("settings.versions_installed_unpacked_here_by"), r))

        self.dirs = QListWidget()
        self.dirs.setObjectName("grid")
        self.dirs.setFixedHeight(120)
        self.dirs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for d in cfg["project_dirs"]:
            live_i18n.call(self.dirs.addItem, d)
        add = small_btn(tr("settings.add"))
        add.clicked.connect(self._add_dir)
        rm = small_btn(tr("settings.remove_selected"))
        rm.clicked.connect(self._rm_dir)
        r2 = QHBoxLayout()
        r2.addWidget(add)
        r2.addWidget(rm)
        r2.addStretch()
        v.addWidget(setting_card(tr("settings.project_folders"), tr("settings.launcher_looks_uproject_files_them"),
                                 self.dirs, r2))

        access = QComboBox()
        live_i18n.call(access.addItem, tr("settings.ssh_key_added_github"), "ssh")
        live_i18n.call(access.addItem, tr("settings.https_token_gh_auth_setup"), "https")
        access.setCurrentIndex(access.findData(cfg["access"]))
        access.activated.connect(lambda i: self._set("access", access.itemData(i)))
        v.addWidget(setting_card(tr("settings.github_access"), tr("settings.how_launcher_accesses_epicgames_unrealengine"), access))

        sdl = QComboBox()
        live_i18n.call(sdl.addItem, tr("settings.auto"), "auto")
        live_i18n.call(sdl.addItem, tr("settings.x11_xwayland_recommended_wayland"), "x11")
        live_i18n.call(sdl.addItem, tr("settings.wayland_do_not_use_ue"), "wayland")
        sdl.setCurrentIndex(sdl.findData(cfg["sdl"]))
        sdl.activated.connect(lambda i: self._set("sdl", sdl.itemData(i)))
        args = QLineEdit(cfg["args"])
        live_i18n.call(args.setPlaceholderText, tr("settings.extra_editor_arguments_e_g"))
        args.editingFinished.connect(lambda: self._set("args", args.text().strip()))
        cb5 = live_i18n.call(QCheckBox, tr("settings.disable_editor_tooltips_fixes_click"))
        cb5.setChecked(cfg["no_tooltips"])
        cb5.toggled.connect(lambda on: self._set("no_tooltips", on))
        v.addWidget(setting_card(tr("settings.editor_launch"),
                                 tr("settings.under_wayland_unreal_editor_works"),
                                 sdl, args, cb5))

        cb1 = live_i18n.call(QCheckBox, tr("settings.write_engines_epic_install_ini"))
        cb1.setChecked(cfg["sync_ini"])
        cb1.toggled.connect(lambda on: (self._set("sync_ini", on), win.reload_engines()))
        cb2 = live_i18n.call(QCheckBox, tr("settings.offer_install_missing_packages_via"))
        cb2.setChecked(cfg["deps"])
        cb2.toggled.connect(lambda on: self._set("deps", on))
        ddc = QLineEdit(cfg["ddc"])
        ddc.editingFinished.connect(lambda: self._set("ddc", ddc.text().strip() or DEFAULTS["ddc"]))
        mode = QComboBox()
        live_i18n.call(mode.addItem, tr("settings.auto_zen_if_available_otherwise"), "auto")
        live_i18n.call(mode.addItem, tr("settings.zen_unreal_s_local_cache"), "zen")
        live_i18n.call(mode.addItem, tr("settings.folder_disk_one_below"), "files")
        live_i18n.call(mode.addItem, tr("settings.memory_only_shaders_recompiled_every"), "memory")
        mode.setCurrentIndex(max(0, mode.findData(cfg["ddc_mode"])))
        mode.activated.connect(lambda i: self._set("ddc_mode", mode.itemData(i)))
        zen = live_i18n.call(QLabel, tr("settings.zen_available") if zen_reachable() else
                     tr("settings.ipv6_loopback_disabled_zen_unavailable"))
        zen.setObjectName("hint")
        zen.setWordWrap(True)
        threads = QComboBox()
        live_i18n.call(threads.addItem, tr("settings.almost_all_cpu_threads_faster"), "fast")
        live_i18n.call(threads.addItem, tr("settings.unreal_default_half_threads"), "ue")
        threads.setCurrentIndex(max(0, threads.findData(cfg["shader_threads"])))
        threads.activated.connect(lambda i: self._set("shader_threads", threads.itemData(i)))
        v.addWidget(setting_card(tr("settings.cache_shader_compilation"),
                                 tr("settings.compiled_shaders_stored_derived_data", f"{CACHE_DIR}/editor.log"),
                                 mode, zen, ddc, threads))
        rt = QComboBox()
        live_i18n.call(rt.addItem, tr("settings.ray_tracing_as_project"), "project")
        live_i18n.call(rt.addItem, tr("settings.no_ray_tracing_editor_less"), "off")
        rt.setCurrentIndex(max(0, rt.findData(cfg["ray_tracing"])))
        rt.activated.connect(lambda i: self._set("ray_tracing", rt.itemData(i)))
        cb7 = live_i18n.call(QCheckBox, tr("settings.unreal_s_built_browser_fab"))
        cb7.setChecked(cfg["cef_gpu"])
        cb7.toggled.connect(lambda on: self._set("cef_gpu", on))
        cb4 = live_i18n.call(QCheckBox, tr("settings.run_discrete_nvidia_gpu_prime"))
        cb4.setChecked(cfg["prime"])
        cb4.toggled.connect(lambda on: self._set("prime", on))
        v.addWidget(setting_card(tr("settings.graphics_card"),
                                 tr("settings.if_viewport_empty_ui_sluggish") + "\n" +
                                 tr("settings.without_ray_tracing_lumen_runs"), cb4, rt, cb7))
        cb6 = live_i18n.call(QCheckBox, tr("settings.minimize_tray_when_window_closed"))
        cb6.setChecked(cfg["tray"])
        cb6.toggled.connect(lambda on: (self._set("tray", on), win.set_tray(on)))
        v.addWidget(setting_card(tr("settings.other"), tr("settings.unreal_editor_does_not_close"),
                                 cb6, cb1, cb2))
        v.addStretch()
        outer.addWidget(scrolled(body), 1)

    def _set(self, k, val) -> None:
        self.win.cfg[k] = val
        self.win.cfg.save()

    def _save_paths(self) -> None:
        self._set("install_dir", self.inst.text().strip() or DEFAULTS["install_dir"])

    def _browse_inst(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("common.installation_folder"), self.inst.text())
        if d:
            live_i18n.call(self.inst.setText, d)
            self._save_paths()

    def _add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("common.projects_folder"), str(Path.home()))
        if d and d not in self.win.cfg["project_dirs"]:
            live_i18n.call(self.dirs.addItem, d)
            self._sync_dirs()

    def _rm_dir(self) -> None:
        for it in self.dirs.selectedItems():
            self.dirs.takeItem(self.dirs.row(it))
        self._sync_dirs()

    def _sync_dirs(self) -> None:
        self._set("project_dirs", [self.dirs.item(i).text() for i in range(self.dirs.count())])
        self.win.reload_projects()
