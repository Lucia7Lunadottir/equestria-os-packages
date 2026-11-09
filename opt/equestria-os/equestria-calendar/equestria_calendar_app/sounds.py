"""calendar: sounds."""
from __future__ import annotations

import math
import os
import struct
import wave
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication
from .paths import CONF_DIR


try:
    from PyQt6.QtMultimedia import QSoundEffect
except Exception:  # нет QtMultimedia — будет системный «бип»
    QSoundEffect = None


SOUND_SPECS = {
    "sounds.bell": dict(notes=[(1046.5, 0, 1.6, 1), (1318.5, .18, 1.6, .9), (1568.0, .36, 1.8, .9),
                               (2093.0, .54, 2.0, .8)], decay=2.6, total=2.8),
    "sounds.soft": dict(notes=[(659.3, 0, 2.0, 1), (880.0, .4, 2.2, .9)], decay=1.8, total=3.0),
    "sounds.beep": dict(notes=[(1000, 0, .2, 1), (1000, .3, .2, 1), (1000, .6, .2, 1)], decay=9.0, total=1.0),
}


def synth_wav(path: str, spec: dict, sr: int = 22050) -> None:
    n = int(sr * spec["total"])
    buf = [0.0] * n
    for freq, t0, dur, amp in spec["notes"]:
        s0 = int(t0 * sr)
        for i in range(int(dur * sr)):
            if s0 + i >= n:
                break
            t = i / sr
            env = math.exp(-t * spec["decay"]) * min(1.0, t * 300)
            buf[s0 + i] += amp * env * (math.sin(2 * math.pi * freq * t)
                                        + 0.35 * math.sin(4 * math.pi * freq * t)
                                        + 0.12 * math.sin(6 * math.pi * freq * t))
    peak = max(1e-9, max(abs(x) for x in buf))
    data = b"".join(struct.pack("<h", int(x / peak * 0.8 * 32767)) for x in buf)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data)


class Sounds:
    def __init__(self):
        self.dir = CONF_DIR / "sounds"
        self.fx: dict = {}

    def path(self, name: str) -> str:
        idx = list(SOUND_SPECS).index(name) if name in SOUND_SPECS else 0
        p = self.dir / f"sound{idx}.wav"
        if not p.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            synth_wav(str(p), list(SOUND_SPECS.values())[idx])
        return str(p)

    def play(self, name: str, volume: int, custom: str = "") -> None:
        try:
            path = custom if custom and os.path.isfile(custom) else self.path(name)
            if QSoundEffect is None:
                QApplication.beep()
                return
            fx = self.fx.get(path)
            if fx is None:
                fx = QSoundEffect()
                fx.setSource(QUrl.fromLocalFile(path))
                self.fx[path] = fx
            fx.setVolume(max(0.0, min(1.0, volume / 100)))
            fx.play()
        except Exception:
            QApplication.beep()
