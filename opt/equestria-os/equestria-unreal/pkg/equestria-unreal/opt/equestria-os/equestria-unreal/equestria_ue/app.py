from __future__ import annotations

import sys
import threading
import time
import traceback

from PyQt6.QtWidgets import QApplication

from equestria_ue.kit import kit_qt  # noqa: F401 — подключает equestria_kit (и при запуске из исходников)
from equestria_kit.single_instance import SingleInstance
from equestria_ue.theme import install_theme
from equestria_ue.paths import CACHE_DIR
from equestria_ue.ui.main_window import MainWindow


def install_crash_guards() -> None:
    """PyQt6 вызывает abort() на любом необработанном исключении в слоте — лаунчер молча
    исчезал (и из трея тоже). Пишем трейсбек в stderr и crash.log и продолжаем работу."""
    import faulthandler
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fh = open(CACHE_DIR / "crash.log", "a", buffering=1)
        faulthandler.enable(file=fh)
    except OSError:
        fh = None

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.stderr.write(text)
        if fh:
            try:
                fh.write(time.strftime("%F %T ") + text)
            except OSError:
                pass

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)


def main() -> None:
    install_crash_guards()
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Unreal Launcher")
    app.setDesktopFileName("equestria-unreal")
    # одна копия: повторный запуск (лаунчер свёрнут в трей) показывает уже открытое окно
    instance = SingleInstance("equestria-unreal")
    if not instance.claim():
        instance.notify_running()
        return
    app.setQuitOnLastWindowClosed(False)   # окно может прятаться в трей; выход — MainWindow.quit_app
    install_theme(app)
    win = MainWindow()
    instance.on_show(win.show_window)
    win.show()
    code = app.exec()
    instance.release()
    sys.exit(code)


if __name__ == "__main__":
    main()
