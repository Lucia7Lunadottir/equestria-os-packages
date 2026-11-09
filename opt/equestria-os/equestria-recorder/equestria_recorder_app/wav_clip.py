"""16-битный WAV целиком в памяти: волна для экрана, вырезка фрагмента, запись."""
from __future__ import annotations

import wave
from array import array
from pathlib import Path

from .formatting import fmt_time
from .localization import tr


class WavClip:
    SAMPLE_WIDTH = 2

    def __init__(self, channels: int, rate: int, data: bytes):
        self.channels, self.rate = channels, rate
        self.frame_width = self.SAMPLE_WIDTH * channels
        self.nframes = len(data) // self.frame_width
        self.data = data[:self.nframes * self.frame_width]

    @classmethod
    def load(cls, path: Path) -> "WavClip":
        """ValueError — не 16 бит или пустой файл (текст ошибки уже переведён)."""
        with wave.open(str(path), "rb") as w:
            channels, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            if width != cls.SAMPLE_WIDTH:
                raise ValueError(tr("wav_clip.only_16_bit_wav_supported"))
            data = w.readframes(n)
        clip = cls(channels, rate, data)
        if clip.nframes == 0:
            raise ValueError(tr("wav_clip.file_empty"))
        return clip

    @property
    def duration(self) -> float:
        return self.nframes / self.rate

    def peaks(self, max_bins: int = 700) -> list:
        """Пики первого канала по столбикам (0..1, со сжатием тихих мест)."""
        arr = array("h")
        arr.frombytes(self.data)
        ch = arr[0::self.channels]
        length, bins = len(ch), min(max_bins, max(50, len(ch)))
        out = []
        for i in range(bins):
            a, b = i * length // bins, (i + 1) * length // bins
            seg = ch[a:b:max(1, (b - a) // 64)]
            pk = max(max(seg), -min(seg)) if len(seg) else 0
            out.append((pk / 32768) ** 0.6)
        return out

    def slice(self, start: float, end: float, cut: bool) -> bytes:
        """Кадры от start до end (доли 0..1); cut=True — всё, кроме этого отрезка."""
        si, ei, fw = int(start * self.nframes), int(end * self.nframes), self.frame_width
        return (self.data[:si * fw] + self.data[ei * fw:]) if cut else self.data[si * fw:ei * fw]

    def write(self, path: Path, frames: bytes) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(self.SAMPLE_WIDTH)
            w.setframerate(self.rate)
            w.writeframes(frames)


def wav_len(path: Path) -> str:
    """Длительность файла текстом; «?» — не читается."""
    try:
        with wave.open(str(path), "rb") as w:
            return fmt_time(w.getnframes() / w.getframerate())
    except Exception:
        return "?"


def free_copy_path(path: Path, suffix: str = "_trim") -> Path:
    """Свободное имя рядом: name_trim.wav, name_trim2.wav, …"""
    new = path.with_name(f"{path.stem}{suffix}.wav")
    k = 2
    while new.exists():
        new = path.with_name(f"{path.stem}{suffix}{k}.wav")
        k += 1
    return new
