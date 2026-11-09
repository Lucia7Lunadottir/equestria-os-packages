"""Отсчёты с микрофона → 16-битные с усилением. Формат = свой класс-декодер (Open/Closed)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from array import array

from PyQt6.QtMultimedia import QAudioFormat


class SampleDecoder(ABC):
    @abstractmethod
    def decode(self, data: bytes, gain: float) -> array:
        """Сырые байты QAudioSource → array('h') с применённым усилением."""


class Int16Decoder(SampleDecoder):
    def decode(self, data: bytes, gain: float) -> array:
        arr = array("h")
        arr.frombytes(data[:len(data) // 2 * 2])
        if gain != 1:
            arr = array("h", (max(-32768, min(32767, int(x * gain))) for x in arr))
        return arr


class FloatDecoder(SampleDecoder):
    def decode(self, data: bytes, gain: float) -> array:
        f = array("f")
        f.frombytes(data[:len(data) // 4 * 4])
        return array("h", (int(max(-1.0, min(1.0, x * gain)) * 32767) for x in f))


_DECODERS = {
    QAudioFormat.SampleFormat.Int16: Int16Decoder,
    QAudioFormat.SampleFormat.Float: FloatDecoder,
}


def decoder_for(fmt: QAudioFormat) -> SampleDecoder | None:
    """Декодер для формата устройства; None — формат не поддерживается."""
    cls = _DECODERS.get(fmt.sampleFormat())
    return cls() if cls else None
