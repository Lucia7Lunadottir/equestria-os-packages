"""gpu: gpu page."""
from __future__ import annotations

import shutil
from PyQt6.QtCore import QSize, QTimer, Qt
from PyQt6.QtGui import QFontDatabase, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget
)
from equestria_kit.widgets import scrolled, small_btn
from .commands import branch_status, build_branch_cmd, compat
from .descriptions import capabilities, launch_options, overview_rows, tips_for
from .localization import live_i18n, tr
from .models import BRANCHES, BRANCH_GPUS, Gpu, WHY
from .probes import DRIVER_CACHE
from .rules import Check, LVL_ORDER, SYNC
from .widgets import card, dot_icon, lvl_label


class GpuPage(QTabWidget):
    def __init__(self, win, g: Gpu):
        super().__init__()
        self.win, self.g, self.S = win, g, win.S
        self.setDocumentMode(True)
        live_i18n.call(self.addTab, self._overview(), tr("gpu_page.overview"))
        live_i18n.call(self.addTab, self._diag(), tr("gpu_page.diagnostics", sum(c.level in ('fail', 'warn') for c in g.checks)))
        if g.vendor == "nvidia":
            live_i18n.call(self.addTab, self._driver(), tr("gpu_page.driver"))
        live_i18n.call(self.addTab, self._games(), tr("gpu_page.games"))

    # --- обзор
    def _overview(self) -> QWidget:
        g, S = self.g, self.S
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(8)
        for text, lvl in capabilities(g, S):
            row.addWidget(lvl_label(text, lvl))
        row.addStretch()
        v.addLayout(row)
        f, c = card(tr("gpu_page.graphics_card"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(7)
        for i, (k, val) in enumerate(overview_rows(g, S)):
            kl = live_i18n.call(QLabel, k)
            kl.setObjectName("hint")
            vl = live_i18n.call(QLabel, val)
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(vl, i, 1)
        grid.setColumnStretch(1, 1)
        c.addLayout(grid)
        v.addWidget(f)
        v.addStretch()
        return scrolled(body)

    # --- диагностика
    def _diag(self) -> QWidget:
        cs = sorted(self.g.checks, key=lambda c: LVL_ORDER[c.level])
        nf = sum(c.level == "fail" for c in cs)
        nw = sum(c.level == "warn" for c in cs)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(8)
        lvl = "fail" if nf else "warn" if nw else "ok"
        v.addWidget(lvl_label(tr("gpu_page.problems_warnings", nf, nw) if (nf or nw) else tr("gpu_page.everything_fine"), lvl))
        for c in cs:
            v.addWidget(self._row(c))
        v.addStretch()
        return scrolled(body)

    def _row(self, c: Check) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 12, 14, 12)
        h.setSpacing(12)
        h.addWidget(lvl_label("●", c.level, "dot"), 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = live_i18n.call(QLabel, c.title)
        t.setObjectName("rowname")
        t.setWordWrap(True)
        d = live_i18n.call(QLabel, c.detail)
        d.setObjectName("hint")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        h.addLayout(col, 1)
        if c.fix:
            b = small_btn(c.fix[0])
            b.clicked.connect(lambda _=False, fx=c.fix: self.win.do_fix(fx))
            h.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        return f

    # --- драйвер (только NVIDIA)
    def _driver(self) -> QWidget:
        g, S, win = self.g, self.S, self.win
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(12)
        f, c = card(tr("gpu_page.recommended_driver"))
        big = live_i18n.call(QLabel, BRANCHES[g.branch]["label"])
        big.setObjectName("out")
        why = live_i18n.call(QLabel, WHY[g.branch])
        why.setObjectName("hint")
        why.setWordWrap(True)
        c.addWidget(big)
        c.addWidget(why)
        if sum(o.vendor == "nvidia" for o in S.gpus) > 1:
            n = live_i18n.call(QLabel, tr("gpu_page.there_several_nvidia_cards_system"))
            n.setObjectName("hint")
            n.setWordWrap(True)
            c.addWidget(n)
        if not shutil.which("pg-gpu-sync"):
            c.addWidget(lvl_label(tr("gpu_page.pg_gpu_sync_not_installed"), "fail"))
            b = small_btn(tr("gpu_page.install_pg_gpu_sync"))
            b.clicked.connect(lambda: win.do_fix((tr("gpu_page.installing_pg_gpu_sync"), "pkgs", ["pg-gpu-sync"])))
            c.addWidget(b)
        v.addWidget(f)

        f4, c4 = card(tr("gpu_page.driver_selection"))
        h4 = live_i18n.call(QLabel, tr("gpu_page.choose_driver_branch_card_green"))
        h4.setObjectName("hint")
        h4.setWordWrap(True)
        c4.addWidget(h4)
        order = ["open", "580", "470", "390", "none"]
        lst = QListWidget()
        lst.setIconSize(QSize(14, 14))
        lst.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lst.setWordWrap(True)
        lst.setFixedHeight(len(order) * 98 + 8)
        tags = {"rec": tr("gpu_page.recommended_your_card"), "ok": tr("gpu_page.compatible_with_your_card"),
                "no": tr("gpu_page.not_suitable_your_card")}
        for b in order:
            cm = compat(g, b)
            it = live_i18n.call(QListWidgetItem, dot_icon({"rec": "ok", "ok": "warn", "no": "fail"}[cm]),
                                 tr("gpu_page.suitable", BRANCHES[b]['label'], BRANCH_GPUS[b], tags[cm], branch_status(S, b)[0]))
            it.setData(Qt.ItemDataRole.UserRole, b)
            it.setSizeHint(QSize(0, 92))
            live_i18n.call(lst.addItem, it)
        lst.setCurrentRow(order.index(g.branch))
        c4.addWidget(lst)
        pick_btn = live_i18n.call(QPushButton, tr("gpu_page.install_selected_driver"))
        pick_btn.setObjectName("primary")
        pick_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def pick():
            it = lst.currentItem()
            if not it:
                return
            b = it.data(Qt.ItemDataRole.UserRole)
            label = BRANCHES[b]["label"]
            text, ok = branch_status(S, b)
            if not ok:
                QMessageBox.warning(win, tr("gpu_page.driver_unavailable"),
                                    tr("gpu_page.add_packages_repository_put_them", label, text, DRIVER_CACHE))
                return
            if compat(g, b) == "no" and QMessageBox.question(
                    win, tr("gpu_page.driver_not_suitable"),
                    tr("gpu_page.not_recommended_black_screen_kernel", label, g.fam_name or g.name)) != QMessageBox.StandardButton.Yes:
                return
            if b == "none":
                win.do_fix((tr("gpu_page.switching_nouveau"), "sync", ["--nouveau"]))
            elif b == g.branch:
                win.do_fix(SYNC)
            else:
                win.do_fix((tr("gpu_page.installing", label), "raw", build_branch_cmd(S, b, win.opts)))

        pick_btn.clicked.connect(pick)
        c4.addWidget(pick_btn)
        v.addWidget(f4)

        f2, c2 = card(tr("gpu_page.installation_options"))
        for key, text in (("b32", tr("gpu_page.32_bit_libraries_steam_proton")),
                          ("settings", tr("gpu_page.nvidia_settings_panel")),
                          ("nodkms", tr("gpu_page.without_dkms_nvidia_open_package"))):
            cb = live_i18n.call(QCheckBox, text)
            cb.setChecked(win.opts[key])
            cb.toggled.connect(lambda on, k=key: win.opts.__setitem__(k, on))
            c2.addWidget(cb)
        v.addWidget(f2)

        f3, c3 = card(tr("gpu_page.actions"))
        grid = QGridLayout()
        grid.setSpacing(8)
        have = bool(shutil.which("pg-gpu-sync"))
        acts = [(tr("gpu_page.install_repair_driver"), "sync", [], "pg-gpu-sync", True),
                (tr("gpu_page.show_plan_dry_run"), "sync", ["--test"], "pg-gpu-sync --test", False),
                (tr("common.rebuild_dkms_initramfs"), "dkms", [], "dkms autoinstall && mkinitcpio -P", False),
                (tr("gpu_page.switch_nouveau"), "sync", ["--nouveau"], "pg-gpu-sync --nouveau", False),
                (tr("gpu_page.back_automatic_selection"), "sync", ["--reset-mode"], "pg-gpu-sync --reset-mode", False)]
        for i, (text, kind, arg, tip, primary) in enumerate(acts):
            b = live_i18n.call(QPushButton, text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            live_i18n.call(b.setToolTip, tip)
            if primary:
                b.setObjectName("primary")
            b.setEnabled(have or kind != "sync")
            b.clicked.connect(lambda _=False, a=(text, kind, arg): win.do_fix(a))
            grid.addWidget(b, i // 2, i % 2)
        c3.addLayout(grid)
        note = live_i18n.call(QLabel, tr("gpu_page.installation_runs_via_pkexec_asks"))
        note.setObjectName("hint")
        note.setWordWrap(True)
        c3.addWidget(note)
        v.addWidget(f3)
        v.addStretch()
        return scrolled(body)

    # --- игры
    def _games(self) -> QWidget:
        g, S = self.g, self.S
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 8, 12)
        v.setSpacing(12)
        f, c = card(tr("gpu_page.steam_launch_options"))
        out = QLineEdit()
        out.setReadOnly(True)
        out.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        nv = g.vendor == "nvidia"
        specs = [("prime", tr("gpu_page.run_game_card_hybrid_graphics"), len(S.gpus) > 1, len(S.gpus) > 1),
                 ("nvapi", tr("gpu_page.nvapi_dlss_rtx_only"), nv and g.rtx, nv and g.rtx),
                 ("dxr", tr("gpu_page.dx12_ray_tracing_vkd3d_config"), nv and g.rtx, False),
                 ("nod3d12", tr("gpu_page.force_dx11_proton_no_d3d12"), True, False),
                 ("hud", tr("gpu_page.mangohud_fps_overlay"), bool(shutil.which("mangohud")), False),
                 ("gamemode", "GameMode", bool(shutil.which("gamemoderun")), False)]
        boxes = {}

        def update():
            live_i18n.call(out.setText, launch_options(g, S, {k: b.isChecked() for k, b in boxes.items()}))

        for key, text, enabled, checked in specs:
            cb = live_i18n.call(QCheckBox, text)
            cb.setEnabled(bool(enabled))
            cb.setChecked(bool(enabled and checked))
            cb.toggled.connect(lambda _=False: update())
            boxes[key] = cb
            c.addWidget(cb)
        c.addWidget(out)
        cp = live_i18n.call(QPushButton, tr("gpu_page.copy"))
        cp.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def copy():
            live_i18n.call(QGuiApplication.clipboard().setText, out.text())
            live_i18n.call(cp.setText, tr("gpu_page.copied"))
            QTimer.singleShot(1500, lambda: live_i18n.call(cp.setText, tr("gpu_page.copy")))

        cp.clicked.connect(copy)
        c.addWidget(cp)
        v.addWidget(f)
        f2, c2 = card(tr("gpu_page.tips"))
        t = live_i18n.call(QLabel, tips_for(g))
        t.setObjectName("hint")
        t.setWordWrap(True)
        c2.addWidget(t)
        v.addWidget(f2)
        v.addStretch()
        update()
        return scrolled(body)
