"""Микрофон: открыть устройство, читать отсчёты, усиливать."""
from __future__ import annotations

from array import array

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudioDevice, QAudioFormat, QAudioSource

from .localization import tr
from .samples import SampleDecoder, decoder_for


class MicrophoneCapture(QObject):
    """chunk(array('h')) — очередная порция 16-битных отсчётов с усилением."""
    chunk = pyqtSignal(object)

    def __init__(self, parent=None, gain: float = 1.0):
        super().__init__(parent)
        self.gain = gain
        self.fmt: QAudioFormat | None = None
        self.src: QAudioSource | None = None
        self.io = None
        self.decoder: SampleDecoder | None = None

    @property
    def is_open(self) -> bool:
        return bool(self.fmt and self.io)

    @property
    def channels(self) -> int:
        return self.fmt.channelCount()

    @property
    def sample_rate(self) -> int:
        return self.fmt.sampleRate()

    @staticmethod
    def _format_for(device: QAudioDevice) -> QAudioFormat:
        fmt = QAudioFormat()
        fmt.setSampleRate(44100)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        return fmt if device.isFormatSupported(fmt) else device.preferredFormat()

    def open(self, device: QAudioDevice):
        """Начать чтение; вернуть текст ошибки (уже переведённый) или None."""
        self.close()
        fmt = self._format_for(device)
        decoder = decoder_for(fmt)
        if decoder is None:
            return tr("capture.microphone_produces_unsupported_format")
        self.fmt, self.decoder = fmt, decoder
        self.src = QAudioSource(device, fmt, self)
        self.io = self.src.start()
        if self.io is None:
            return tr("capture.could_not_open_microphone_check")
        self.io.readyRead.connect(self._on_ready)
        return None

    def close(self) -> None:
        if self.src:
            self.src.stop()
            self.src.deleteLater()
        self.src = self.io = None

    def _on_ready(self) -> None:
        data = bytes(self.io.readAll())
        if not data:
            return
        samples: array = self.decoder.decode(data, self.gain)
        if samples:
            self.chunk.emit(samples)
