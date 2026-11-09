"""gpu: panel."""
from __future__ import annotations

import shutil
import threading
import weakref
from PyQt6 import sip
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget
)
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import small_btn
from .commands import build_cmd
from .gpu_page import GpuPage
from .localization import live_i18n, tr
from .models import Sys
from .probes import VENDOR_LABEL, probe_system
from .run_dialog import RunDialog
from .style import QSS
from .widgets import dot_icon


class GpuPanel(QWidget):
    """Содержимое менеджера: список видеокарт слева, страница выбранной справа,
    действия с драйвером. Один и тот же виджет — в отдельном окне Equestria GPU
    и в «Настройки → Видеокарта».

    embedded=True — внутри чужого окна: стиль ставится только на сам виджет
    (на приложение его ставит хозяин окна), как у остальных модулей «Настроек»."""
    scanned = pyqtSignal(object)

    def __init__(self, embedded: bool = False, parent=None):
        super().__init__(parent)
        self.opts = {"b32": True, "settings": True, "nodkms": False}
        self.S = Sys()
        self._scanning = False
        root = QHBoxLayout(self)
        root.setContentsMargins(*((0, 8, 0, 0) if embedded else (18, 16, 18, 16)))
        root.setSpacing(16)

        side = QVBoxLayout()
        side.setSpacing(8)
        if not embedded:
            title = live_i18n.call(QLabel, "Equestria GPU")
            title.setObjectName("title")
            sub = live_i18n.call(QLabel, tr("panel.graphics_driver_manager"))
            sub.setObjectName("hint")
            side.addWidget(title)
            side.addWidget(sub)
        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.currentRowChanged.connect(self._select)
        self.sys_label = live_i18n.call(QLabel, "")
        self.sys_label.setObjectName("hint")
        self.sys_label.setWordWrap(True)
        self.buttons = QHBoxLayout()
        self.refresh_btn = small_btn(tr("panel.refresh"))
        self.refresh_btn.clicked.connect(self.refresh)
        self.buttons.addWidget(self.refresh_btn)
        side.addWidget(self.list, 1)
        side.addWidget(self.sys_label)
        side.addLayout(self.buttons)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(280 if embedded else 300)
        root.addWidget(sw)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        if embedded:
            kit_qt.style(self, QSS)
            # значки состояния нарисованы в цветах темы — перерисовать при её смене;
            # слабая ссылка: удалённая панель просто пропускается
            ref = weakref.ref(self)

            def _theme_changed(_theme):
                w = ref()
                if w is not None and not sip.isdeleted(w) and w.S.gpus:
                    w.rebuild()
            kit_qt.on_theme_change(_theme_changed)
        self.scanned.connect(self._scan_done)
        self.refresh()

    # --- данные: опрос системы занимает секунды (vulkaninfo до 25 с) — в фоне
    def refresh(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self.refresh_btn.setEnabled(False)
        live_i18n.call(self.sys_label.setText, tr("panel.querying_graphics_cards"))
        if not self.S.gpus:
            self._show_message(tr("panel.querying_graphics_cards"))
        threading.Thread(target=lambda: self.scanned.emit(probe_system()), daemon=True).start()

    def _scan_done(self, S) -> None:
        self._scanning = False
        self.refresh_btn.setEnabled(True)
        self.S = S
        self.rebuild()

    def _show_message(self, text: str) -> None:
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        msg = live_i18n.call(QLabel, text)
        msg.setObjectName("hint")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(msg)

    def rebuild(self) -> None:
        keep = max(0, self.list.currentRow())
        self.list.blockSignals(True)
        self.list.clear()
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        S = self.S
        if not S.gpus:
            self._show_message(tr("panel.no_graphics_cards_found_install"))
        for g in S.gpus:
            sub = g.fam_name or VENDOR_LABEL[g.vendor]
            it = live_i18n.call(QListWidgetItem, dot_icon(g.worst), live_i18n.format_text('{0}\n{1}', g.name, sub))
            it.setSizeHint(QSize(0, 58))
            live_i18n.call(self.list.addItem, it)
            self.stack.addWidget(GpuPage(self, g))
        live_i18n.call(self.sys_label.setText, tr("panel.kernel_session", S.kernel, S.session)
                               + ("" if shutil.which("pg-gpu-sync") else tr("panel.pg_gpu_sync_not_found")))
        self.list.blockSignals(False)
        if S.gpus:
            self.list.setCurrentRow(min(keep, len(S.gpus) - 1))
            self.stack.setCurrentIndex(self.list.currentRow())

    def _select(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    # --- действия
    def do_fix(self, fix: tuple) -> None:
        label, kind, arg = fix
        if kind == "sync" and not shutil.which("pg-gpu-sync"):
            QMessageBox.information(self, tr("panel.pg_gpu_sync_not_found_2"),
                                    tr("panel.install_pg_gpu_sync_package"))
            return
        cmd = build_cmd(kind, arg, self.opts)
        if not cmd:
            return
        RunDialog(self, label, cmd).exec()
        self.refresh()
