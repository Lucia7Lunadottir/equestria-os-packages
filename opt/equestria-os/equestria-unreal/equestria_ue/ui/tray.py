from __future__ import annotations

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from equestria_ue.kit import tr
from equestria_ue.launcher import launch_editor
from equestria_ue.projects import resolve_engine
from equestria_ue.ui.vram_check import confirm_launch

RECENT = 6   # сколько последних проектов показывать в меню трея


def app_icon() -> QIcon:
    """Значок из темы; если в теме его нет — буква U (у трея пустой значок недопустим)."""
    icon = QIcon.fromTheme("applications-games", QIcon.fromTheme("applications-development"))
    if not icon.isNull():
        return icon
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#1f2430"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 60, 60)
    p.setPen(QColor("white"))
    p.setFont(QFont("sans-serif", 30, QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "U")
    p.end()
    return QIcon(pm)


class LauncherTray(QObject):
    """Значок в трее: лаунчер продолжает загрузки и сборку, когда окно закрыто.

    Меню: показать окно, быстрый запуск последних проектов, выход.
    Редактор Unreal от лаунчера не зависит (отдельный сеанс процессов) —
    выход из лаунчера его не закрывает."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._hint_shown = False
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._fill)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.update_tooltip()
        self.icon.show()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def remove(self) -> None:
        self.icon.hide()
        self.deleteLater()

    def update_tooltip(self, status: str = "") -> None:
        self.icon.setToolTip("Equestria · Unreal Launcher" + (f"\n{status}" if status else ""))

    def hidden_hint(self) -> None:
        """Подсказка при первом сворачивании в трей за сеанс."""
        if not self._hint_shown:
            self._hint_shown = True
            self.icon.showMessage(tr("Unreal Launcher продолжает работать"),
                                  tr("Загрузки и сборка идут дальше. Значок в трее — открыть окно или выйти."))

    # --- меню
    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.win.show_window()

    def _fill(self) -> None:
        self.menu.clear()
        show = QAction(tr("Показать лаунчер"), self.menu)
        show.triggered.connect(self.win.show_window)
        self.menu.addAction(show)
        self.menu.addSeparator()
        recent = self.win.projects[:RECENT]
        if recent:
            title = QAction(tr("Последние проекты"), self.menu)
            title.setEnabled(False)
            self.menu.addAction(title)
            for pr in recent:
                act = QAction(pr.name, self.menu)
                act.triggered.connect(lambda _=False, p=pr: self._launch(p))
                self.menu.addAction(act)
            self.menu.addSeparator()
        quit_ = QAction(tr("Выйти"), self.menu)
        quit_.triggered.connect(self.win.quit_app)
        self.menu.addAction(quit_)

    def _launch(self, pr) -> None:
        built = sorted((e for e in self.win.engines if e.built), key=lambda e: e.version, reverse=True)
        eng = resolve_engine(pr, self.win.engines) or (built[0] if built else None)
        if not eng:
            self.win.show_window()
            QMessageBox.information(self.win, tr("Нет движка"), tr("Сначала установите Unreal Engine на вкладке «Каталог»."))
            return
        if not confirm_launch(self.win):
            return
        err = launch_editor(self.win.cfg, eng, pr.path)
        if err:
            self.win.show_window()
            QMessageBox.warning(self.win, tr("Не удалось запустить"), err)
