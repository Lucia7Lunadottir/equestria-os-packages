"""color-picker: capture."""
from __future__ import annotations

import os
import re
import shutil
import sys
from PyQt6.QtCore import QObject, QPointF, QProcess, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen
from PyQt6.QtWidgets import QWidget
from .localization import live_i18n, tr


PORTAL_SCRIPT = r'''
import os, sys
try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = "eqpick%d" % os.getpid()
    path = "/org/freedesktop/portal/desktop/request/%s/%s" % (bus.get_unique_name()[1:].replace(".", "_"), token)
    loop = GLib.MainLoop()
    out = {"code": 1}
    def on_resp(conn, sender, obj, iface, sig, params):
        code, res = params.unpack()
        if code == 0 and "color" in res:
            r, g, b = res["color"]
            print(r, g, b)
            out["code"] = 0
        elif code == 1:
            out["code"] = 2
        loop.quit()
    bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                         path, None, Gio.DBusSignalFlags.NONE, on_resp)
    bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                  "org.freedesktop.portal.Screenshot", "PickColor",
                  GLib.Variant("(sa{sv})", ("", {"handle_token": GLib.Variant("s", token)})),
                  None, Gio.DBusCallFlags.NONE, -1, None)
    loop.run()
    sys.exit(out["code"])
except Exception:
    sys.exit(1)
'''


WAYLAND_HELP = (tr("capture.could_not_pick_color_from"))


class PickStep:
    """Один способ взять цвет с экрана в Wayland. Новый способ = новый подкласс в PICK_STEPS."""
    kind = ""

    def available(self) -> bool:
        return True

    def command(self) -> list:
        raise NotImplementedError

    def handle(self, picker: "ScreenPicker", code: int, out: bytes) -> None:
        """Разобрать ответ программы: picker.picked / cancelled / failed / next_step / run."""
        raise NotImplementedError


class PortalStep(PickStep):
    """xdg-desktop-portal (GNOME, KDE и др.), нужен python3-gobject."""
    kind = "portal"

    def command(self) -> list:
        py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else (shutil.which("python3") or sys.executable)
        return [py, "-c", PORTAL_SCRIPT]

    def handle(self, picker, code, out):
        try:
            r, g, b = (float(x) for x in out.decode().split()[:3])
            if code == 0:
                picker.picked.emit(QColor.fromRgbF(r, g, b))
                return
        except ValueError:
            pass
        if code == 2:
            picker.cancelled.emit()
        else:
            picker.next_step()


class HyprpickerStep(PickStep):
    kind = "hypr"

    def available(self) -> bool:
        return bool(shutil.which("hyprpicker"))

    def command(self) -> list:
        return ["hyprpicker", "-f", "hex"]

    def handle(self, picker, code, out):
        m = re.search(rb"#?([0-9a-fA-F]{6})", out)
        if m:
            picker.picked.emit(QColor("#" + m.group(1).decode()))
        else:
            picker.cancelled.emit()


class SlurpStep(PickStep):
    """slurp выбирает точку, затем grim снимает этот пиксель."""
    kind = "slurp"

    def available(self) -> bool:
        return bool(shutil.which("slurp") and shutil.which("grim"))

    def command(self) -> list:
        return ["slurp", "-p"]

    def handle(self, picker, code, out):
        geom = out.decode(errors="ignore").strip()
        if code != 0 or not geom:
            picker.cancelled.emit()
        else:
            picker.run(GrimStep(geom))


class GrimStep(PickStep):
    kind = "grim"

    def __init__(self, geom: str):
        self.geom = geom

    def command(self) -> list:
        return ["grim", "-g", self.geom, "-t", "ppm", "-"]

    def handle(self, picker, code, out):
        if out.startswith(b"P6") and len(out) >= 3:
            r, g, b = out[-3], out[-2], out[-1]
            picker.picked.emit(QColor(r, g, b))
        else:
            picker.failed.emit(WAYLAND_HELP)


PICK_STEPS = (PortalStep, HyprpickerStep, SlurpStep)  # порядок = порядок попыток


class ScreenPicker(QObject):
    """Пипетка для Wayland: пробует способы из PICK_STEPS по очереди, пока один не сработает."""
    picked = pyqtSignal(QColor)
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: list = []
        self.procs: list = []

    def start(self) -> None:
        self.steps = [step for step in (cls() for cls in PICK_STEPS) if step.available()]
        self.next_step()

    def run(self, step: PickStep) -> None:
        cmd = step.command()
        proc = QProcess(self)
        proc.setProperty("handled", False)
        proc.finished.connect(lambda code, _st, p=proc, st=step: self._finished(p, st, code))
        proc.errorOccurred.connect(lambda err, p=proc: self._error(p, err))
        self.procs.append(proc)
        proc.start(cmd[0], cmd[1:])

    def next_step(self) -> None:
        if not self.steps:
            self.failed.emit(WAYLAND_HELP)
            return
        self.run(self.steps.pop(0))

    def _error(self, proc: QProcess, err) -> None:
        if err == QProcess.ProcessError.FailedToStart and not proc.property("handled"):
            proc.setProperty("handled", True)
            self.next_step()

    def _finished(self, proc: QProcess, step: PickStep, code: int) -> None:
        if proc.property("handled"):
            return
        proc.setProperty("handled", True)
        step.handle(self, code, bytes(proc.readAllStandardOutput()))


class Overlay(QWidget):
    """Пипетка с лупой для X11/Windows/macOS: полноэкранный снимок + клик."""
    picked = pyqtSignal(QColor)
    cancelled = pyqtSignal()

    def __init__(self, screen):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.shot = screen.grabWindow(0)
        self.img = self.shot.toImage()
        self.dpr = self.shot.devicePixelRatio() or 1.0
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.pos_ = self.mapFromGlobal(QCursor.pos())
        self._done = False

    def color_at(self, pt) -> QColor:
        x = min(max(int(pt.x() * self.dpr), 0), self.img.width() - 1)
        y = min(max(int(pt.y() * self.dpr), 0), self.img.height() - 1)
        return self.img.pixelColor(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        n, zoom = 9, 12
        size = n * zoom
        x = self.pos_.x() + 24
        y = self.pos_.y() + 24
        if x + size > self.width():
            x = self.pos_.x() - 24 - size
        if y + size + 28 > self.height():
            y = self.pos_.y() - 24 - size - 28
        for j in range(n):
            for i in range(n):
                c = self.color_at(QPointF(self.pos_.x() + i - n // 2, self.pos_.y() + j - n // 2))
                p.fillRect(int(x + i * zoom), int(y + j * zoom), zoom, zoom, c)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawRect(int(x + (n // 2) * zoom), int(y + (n // 2) * zoom), zoom, zoom)
        p.setPen(QPen(QColor("#000000"), 1))
        p.drawRect(int(x), int(y), size, size)
        cur = self.color_at(self.pos_)
        p.fillRect(int(x), int(y + size), size, 28, QColor(0, 0, 0, 200))
        p.setPen(QColor("#ffffff"))
        live_i18n.call(p.drawText, int(x), int(y + size), size, 28, Qt.AlignmentFlag.AlignCenter, cur.name().upper())

    def mouseMoveEvent(self, e):
        self.pos_ = e.position().toPoint()
        self.update()

    def mousePressEvent(self, e):
        if self._done:
            return
        self._done = True
        if e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.color_at(e.position().toPoint()))
        else:
            self.cancelled.emit()
        self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and not self._done:
            self._done = True
            self.cancelled.emit()
            self.close()
