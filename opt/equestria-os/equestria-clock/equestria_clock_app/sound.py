"""clock: sound."""
from __future__ import annotations

import math
import shutil
import sys
import wave
from PyQt6.QtCore import QObject, QProcess, pyqtSignal
from PyQt6.QtWidgets import QApplication
from array import array
from pathlib import Path
from .localization import tr
from .paths import CACHE_DIR


def _seq_classic():
    beeps = [(880.0, 0.12), (0, 0.08)] * 4 + [(0, 0.3)]
    return beeps * 2 + [(0, 0.7)]


BUILTIN_SOUNDS = {
    "chime": (tr("sound.bell"), [
        (659.25, .28), (783.99, .28), (1046.5, .45), (0, .15),
        (783.99, .28), (1046.5, .28), (1318.5, .70), (0, 1.0)], 5.0),
    "classic": (tr("sound.classic_ring"), _seq_classic(), 0.5),
    "rainbow": (tr("sound.rainbow"), [
        (523.25, .18), (587.33, .18), (659.25, .18), (783.99, .18), (880.0, .18),
        (1046.5, .30), (880.0, .18), (783.99, .18), (659.25, .18), (587.33, .18),
        (523.25, .50), (0, 1.0)], 3.0),
}


def make_wav(path: Path, seq, decay: float, rate: int = 44100) -> None:
    samples = array("h")
    for freq, dur in seq:
        n = int(rate * dur)
        if freq == 0:
            samples.extend([0] * n)
            continue
        w = 2 * math.pi * freq
        for i in range(n):
            t = i / rate
            env = (min(1.0, t / 0.008) * min(1.0, (dur - t) / 0.015)
                   * math.exp(-decay * t / dur))
            v = (math.sin(w * t) + 0.35 * math.sin(2 * w * t)
                 + 0.12 * math.sin(3 * w * t)) / 1.47
            samples.append(int(v * env * 0.6 * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(samples.tobytes())


def ensure_builtin(key: str) -> Path:
    path = CACHE_DIR / "sounds" / f"{key}-v1.wav"
    if not path.exists():
        _, seq, decay = BUILTIN_SOUNDS[key]
        make_wav(path, seq, decay)
    return path


def resolve_sound(spec: str | None) -> Path:
    if spec and spec.startswith("builtin:") and spec[8:] in BUILTIN_SOUNDS:
        return ensure_builtin(spec[8:])
    if spec and Path(spec).is_file():
        return Path(spec)
    return ensure_builtin("chime")


class SoundPlayer(QObject):
    """Играет звук через системный pw-play / paplay (без тяжёлого QtMultimedia)."""
    stateChanged = pyqtSignal(bool)  # True — играет

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.volume = 80
        self.loop = False
        self.path = ""
        self._active = False

    @staticmethod
    def _tool():
        for name in ("pw-play", "paplay"):
            if shutil.which(name):
                return name
        return None

    def _set_active(self, on: bool) -> None:
        if on != self._active:
            self._active = on
            self.stateChanged.emit(on)

    def _start(self) -> None:
        tool = self._tool()
        if not tool:
            print("Sound error: neither pw-play nor paplay was found", file=sys.stderr)
            self._set_active(False)
            QApplication.beep()
            return
        v = self.volume / 100
        vol = f"--volume={v:.2f}" if tool == "pw-play" else f"--volume={int(v * 65536)}"
        p = QProcess(self)
        self.proc = p
        p.finished.connect(lambda *_, p=p: self._finished(p))
        p.errorOccurred.connect(lambda *_, p=p: self._failed(p))
        p.start(tool, [vol, self.path])

    def _failed(self, p) -> None:
        if p is self.proc:
            self._set_active(False)
        self._finished(p)

    def _finished(self, p) -> None:
        p.deleteLater()
        if p is not self.proc:
            return
        self.proc = None
        if self._active and self.loop:
            self._start()
        else:
            self._set_active(False)

    def _halt(self) -> None:
        p, self.proc = self.proc, None
        if p is not None:
            p.kill()

    def play(self, spec: str | None, volume: int, loop: bool = True) -> None:
        self._halt()
        self.volume = max(0, min(100, volume))
        self.loop = loop
        self.path = str(resolve_sound(spec))
        self._start()
        self._active = False
        self._set_active(True)

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, volume))  # применится при следующем повторе

    def stop(self) -> None:
        self._halt()
        self._set_active(False)
