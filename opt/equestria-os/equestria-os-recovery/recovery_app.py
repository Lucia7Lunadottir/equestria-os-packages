"""
Equestria OS Recovery — точка входа.

  equestria-recovery              в системе — менеджер образа восстановления,
                                  в live-среде — мастер восстановления
  equestria-recovery --wizard     мастер (в любом случае)
  equestria-recovery --autostart  из автозапуска live-сессии: открыть мастер, только
                                  если загрузились через пункт «Восстановление» в GRUB
"""
import sys

from PyQt6.QtWidgets import QApplication

from recovery_paths import APP_ID, booted_for_recovery, is_live
from recovery_widgets import kit_qt


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--autostart" in argv and not (is_live() and booted_for_recovery()):
        return 0
    app = QApplication(argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS (переключатель персонажей)
    app.setDesktopFileName(APP_ID)
    if is_live() or "--wizard" in argv:
        from recovery_wizard import RescueWizard
        win = RescueWizard()
    else:
        from recovery_manager import RecoveryManagerApp
        win = RecoveryManagerApp()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
