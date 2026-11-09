"""Сеанс записи в WAV: запись → пауза → продолжение → стоп."""
from __future__ import annotations

import datetime as dt
import wave
from array import array
from pathlib import Path

IDLE, REC, PAUSE = "idle", "rec", "pause"


class RecordingSession:
    def __init__(self):
        self.state = IDLE
        self.path: Path | None = None   # последний файл (остаётся и после стопа)
        self.frames = 0
        self.wav = None
        self.channels = 1
        self.rate = 44100

    @property
    def idle(self) -> bool:
        return self.state == IDLE

    @property
    def seconds(self) -> float:
        return self.frames / self.rate

    def start(self, folder: Path, channels: int, rate: int) -> Path:
        """Новый файл recording_<дата>.wav в folder; OSError — не создать."""
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"recording_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.wav"
        wav = wave.open(str(path), "wb")
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        self.path, self.wav, self.channels, self.rate = path, wav, channels, rate
        self.frames, self.state = 0, REC
        return path

    def toggle_pause(self) -> None:
        if self.state == REC:
            self.state = PAUSE
        elif self.state == PAUSE:
            self.state = REC

    def write(self, samples: array) -> bool:
        """Дописать отсчёты, если идёт запись; True — записано."""
        if self.state != REC or not self.wav:
            return False
        self.wav.writeframes(samples.tobytes())
        self.frames += len(samples) // self.channels
        return True

    def stop(self) -> Path | None:
        """Закрыть файл; вернуть его путь (None — запись не шла)."""
        if self.idle:
            return None
        if self.wav:
            self.wav.close()
            self.wav = None
        self.state = IDLE
        return self.path
