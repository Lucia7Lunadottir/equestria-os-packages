"""Прослушивание записей (в том числе с середины — для обрезки)."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer


class Playback(QObject):
    """playing_changed(bool) — началось/закончилось; error(str) — сообщение плеера."""
    playing_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        self.pending_start: int | None = None   # позиция, с которой начать после загрузки файла
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._error)

    @property
    def loading(self) -> bool:
        return self.pending_start is not None

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def position(self) -> float:
        """Текущая позиция в секундах."""
        return self.player.position() / 1000

    def refresh_output(self) -> None:
        """Всегда играть на текущем устройстве вывода (наушники могли отключить)."""
        self.output.setDevice(QMediaDevices.defaultAudioOutput())

    def play(self, path: Path, start_ms: int = 0) -> None:
        self.refresh_output()
        self.player.stop()
        self.player.setSource(QUrl())  # сброс, чтобы тот же файл загрузился заново
        self.pending_start = start_ms if start_ms > 0 else None
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        if self.pending_start is None:
            self.player.play()

    def stop(self) -> None:
        self.player.stop()

    def _media_status(self, status) -> None:
        loaded = status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)
        if self.pending_start is not None and loaded:
            ms, self.pending_start = self.pending_start, None
            self.player.setPosition(ms)
            self.player.play()

    def _state_changed(self, state) -> None:
        self.playing_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _error(self, _err, message: str) -> None:
        self.error.emit(message)
