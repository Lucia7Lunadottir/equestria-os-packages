"""Применение пресета: стиль панели → вид рабочего стола (если меняется) → раскладка."""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from desktop_icons import DesktopIcons
from panel_layout import ConfigureMemoryMonitor, KeepUserLaunchers, LayoutScript, PanelLayout
from panel_style import PanelStyleManager
from plasma import PlasmaShell, ShellRestart
from presets import Preset


class PresetApplier(QObject):
    finished = pyqtSignal(bool, str)  # успех, текст ошибки

    def __init__(self, parent=None):
        super().__init__(parent)
        self.shell = PlasmaShell(self)
        self.style = PanelStyleManager(parent=self)
        self.icons = DesktopIcons()
        self.restart = ShellRestart(self.shell, self)
        self.style.applied.connect(self._after_style)
        self.restart.finished.connect(self._after_restart)
        self.shell.script_finished.connect(self._after_script)
        self._busy = False
        self._pending = None
        self._job = None

    @property
    def busy(self) -> bool:
        return self._busy

    def apply_appearance(self, preset: Preset) -> None:
        """Только цвет и прозрачность — без раскладки."""
        self._start(preset, None, with_layout=False)

    def apply(self, preset: Preset, layout: PanelLayout | None) -> None:
        self._start(preset, layout, with_layout=True)

    def _start(self, preset, layout, with_layout):
        if self._busy:  # быстрые клики подряд: применится последний выбор
            self._pending = (preset, layout, with_layout)
            return
        self._busy = True
        # ярлыки пользователя запоминаем до любых перезапусков
        launchers = None
        if with_layout and self.shell.is_running():
            dump = self.shell.dump_layout()
            launchers = PanelLayout.from_dump(dump).launchers() if dump else None
        self._job = {"preset": preset, "layout": layout, "with_layout": with_layout, "launchers": launchers}
        self.style.apply(preset.color_day, preset.color_night, preset.opacity)

    def _after_style(self):
        job = self._job
        if not job["with_layout"]:
            return self._done(True, "")
        edits = self.icons.edits_for(job["preset"].hide_desktop_icons)
        if edits:
            self.restart.run(edits)
        else:
            self._apply_layout()

    def _after_restart(self, ok: bool):
        if not ok:
            return self._done(False, "plasmashell")
        self._apply_layout()

    def _apply_layout(self):
        job = self._job
        layout, preset = job["layout"], job["preset"]
        if layout and layout.panels:
            patched = layout.copy()
            for patch in (KeepUserLaunchers(job["launchers"]), ConfigureMemoryMonitor()):
                patch.apply(patched)
            self.shell.evaluate(LayoutScript(patched).build())
        elif preset.legacy_script:
            self.shell.evaluate(preset.legacy_script)
        else:
            self._done(True, "")

    def _after_script(self, ok: bool, error: str):
        if self._busy:
            self._done(ok, error)

    def _done(self, ok: bool, error: str):
        self._busy = False
        self._job = None
        self.finished.emit(ok, error)
        if self._pending:
            preset, layout, with_layout = self._pending
            self._pending = None
            self._start(preset, layout, with_layout)
