"""Главное окно: собирает интерфейс и связывает микрофон, запись, воспроизведение и настройки."""
from __future__ import annotations

from array import array
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QPushButton, QSlider, QVBoxLayout, QWidget)

from equestria_kit import live_i18n, qt as kit_qt

from .capture import MicrophoneCapture
from .formatting import fmt_time
from .levels import CLIP_PEAK, peak_db, peak_of, to_level
from .localization import catalog, tr
from .paths import CONFIG, default_folder
from .playback import Playback
from .recording import IDLE, PAUSE, REC, RecordingSession
from .settings import SettingsStore
from .style import apply_theme
from .trim_dialog import TrimDialog
from .wav_clip import wav_len
from .widgets import LevelMeter, card


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, theme: str, settings: SettingsStore | None = None):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.cfg, self.theme = cfg, theme
        self.settings = settings or SettingsStore(CONFIG)
        self.folder = Path(cfg.get("folder") or default_folder())
        live_i18n.call(self.setWindowTitle, "Equestria Recorder")
        self.resize(480, 820)
        self.setMinimumSize(440, 720)

        self.capture = MicrophoneCapture(self, gain=int(cfg.get("gain", 100)) / 100)
        self.capture.chunk.connect(self._on_chunk)
        self.session = RecordingSession()
        self.playback = Playback(self)
        self.playback.playing_changed.connect(self._play_state)
        self.playback.error.connect(self._play_error)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)
        root.addLayout(self._build_header())
        root.addWidget(self._build_device_card())
        root.addWidget(self._build_level_card())
        root.addWidget(self._build_gain_card())
        root.addWidget(self._build_folder_card())
        self._build_record_controls(root)
        self._build_recordings(root)

        self.devices = QMediaDevices(self)
        self.devices.audioOutputsChanged.connect(self.playback.refresh_output)
        self.devices.audioInputsChanged.connect(self._fill_devices)
        self._fill_devices()
        self._scan_folder()

    # --- построение интерфейса
    def _build_header(self) -> QHBoxLayout:
        top = QHBoxLayout()
        title = live_i18n.call(QLabel, "Equestria Recorder")
        title.setObjectName("h2")
        theme_btn = live_i18n.call(QPushButton, tr("window.theme"))
        theme_btn.setObjectName("small")
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        self.language_combo = catalog.selector(self, None)
        top.addWidget(self.language_combo)
        top.addWidget(theme_btn)
        return top

    def _build_device_card(self) -> QWidget:
        self.dev = QComboBox()
        self.dev.setMinimumHeight(34)
        self.dev.currentIndexChanged.connect(self._device_changed)
        refresh = live_i18n.call(QPushButton, "⟳")
        refresh.setObjectName("small")
        live_i18n.call(refresh.setToolTip, tr("window.refresh_microphone_list"))
        refresh.setFixedSize(40, 34)
        refresh.clicked.connect(self._fill_devices)
        row = QHBoxLayout()
        row.addWidget(self.dev, 1)
        row.addWidget(refresh)
        return card(tr("window.microphone"), row)

    def _build_level_card(self) -> QWidget:
        self.meter = LevelMeter()
        self.db_label = live_i18n.call(QLabel, tr("window.db_silence"))
        self.db_label.setObjectName("db")
        self.db_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row = QHBoxLayout()
        row.addWidget(self.meter, 1)
        row.addWidget(self.db_label)
        self.warn = live_i18n.call(QLabel, "")
        self.warn.setObjectName("warn")
        return card(tr("window.signal_level"), row, header=self.warn)

    def _build_gain_card(self) -> QWidget:
        percent = int(self.capture.gain * 100)
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(0, 300)
        self.gain_slider.setValue(percent)
        self.gain_label = live_i18n.call(QLabel, f"{percent}%")
        self.gain_label.setMinimumWidth(48)
        self.gain_slider.valueChanged.connect(self._gain_changed)
        row = QHBoxLayout()
        row.addWidget(self.gain_slider, 1)
        row.addWidget(self.gain_label)
        return card(tr("window.microphone_volume_gain"), row)

    def _build_folder_card(self) -> QWidget:
        self.folder_edit = QLineEdit(str(self.folder))
        self.folder_edit.setReadOnly(True)
        pick = live_i18n.call(QPushButton, tr("window.choose"))
        pick.clicked.connect(self._pick_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder_edit, 1)
        row.addWidget(pick)
        return card(tr("window.save"), row)

    def _build_record_controls(self, root: QVBoxLayout) -> None:
        self.time_label = live_i18n.call(QLabel, "00:00")
        self.time_label.setObjectName("time")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = live_i18n.call(QLabel, tr("window.ready_record"))
        self.status.setObjectName("hint")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rec_btn = live_i18n.call(QPushButton, tr("window.record"))
        self.rec_btn.setObjectName("rec")
        self.rec_btn.clicked.connect(self.toggle)
        self.stop_btn = live_i18n.call(QPushButton, tr("common.stop"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        row = QHBoxLayout()
        row.addWidget(self.rec_btn, 2)
        row.addWidget(self.stop_btn, 1)
        root.addWidget(self.time_label)
        root.addWidget(self.status)
        root.addLayout(row)

    def _build_recordings(self, root: QVBoxLayout) -> None:
        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        self.play_btn = live_i18n.call(QPushButton, tr("window.play"))
        self.play_btn.clicked.connect(self.play_selected)
        trim_btn = live_i18n.call(QPushButton, tr("window.trim"))
        trim_btn.clicked.connect(self.trim_selected)
        open_btn = live_i18n.call(QPushButton, tr("window.folder"))
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder))))
        row = QHBoxLayout()
        row.addWidget(self.play_btn, 1)
        row.addWidget(trim_btn, 1)
        row.addWidget(open_btn)
        lab = live_i18n.call(QLabel, tr("window.recordings"))
        lab.setObjectName("h2")
        root.addWidget(lab)
        root.addWidget(self.list, 1)
        root.addLayout(row)

    # --- темы и настройки
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        for w in self.findChildren(QWidget):
            w.update()
        self._save()

    def _save(self) -> None:
        device = self.dev.currentData()
        self.cfg.update(theme=self.theme, folder=str(self.folder), gain=int(self.capture.gain * 100),
                        device=device.description() if device else "")
        self.settings.save(self.cfg)

    # --- микрофон
    def _fill_devices(self) -> None:
        if not self.session.idle:
            return
        self.dev.blockSignals(True)
        self.dev.clear()
        devs = QMediaDevices.audioInputs()
        default = QMediaDevices.defaultAudioInput()
        want = self.cfg.get("device", "")
        sel = 0
        for i, d in enumerate(devs):
            live_i18n.call(self.dev.addItem, d.description(), d)
            if (want and d.description() == want) or (not want and d.id() == default.id()):
                sel = i
        self.dev.setCurrentIndex(sel if devs else -1)
        self.dev.blockSignals(False)
        if not devs:
            live_i18n.call(self.status.setText, tr("window.microphone_not_found"))
        self._device_changed()

    def _device_changed(self) -> None:
        self.capture.close()
        device = self.dev.currentData()
        if not device:
            return
        error = self.capture.open(device)
        if error:
            live_i18n.call(self.status.setText, error)
            return
        if self.session.idle:
            live_i18n.call(self.status.setText, tr("window.ready_record"))
        self._save()

    def _gain_changed(self, v: int) -> None:
        self.capture.gain = v / 100
        live_i18n.call(self.gain_label.setText, f"{v}%")
        self._save()

    def _on_chunk(self, samples: array) -> None:
        peak = peak_of(samples)
        self.meter.set_level(to_level(peak))
        db = peak_db(peak)
        live_i18n.call(self.db_label.setText, tr("window.db", db) if db is not None else tr("window.db_silence"))
        live_i18n.call(self.warn.setText, tr("window.clipping") if peak >= CLIP_PEAK else "")
        if self.session.write(samples):
            live_i18n.call(self.time_label.setText, fmt_time(self.session.seconds))

    # --- запись
    def toggle(self) -> None:
        if self.session.idle:
            if not self.capture.is_open:
                return
            try:
                self.session.start(self.folder, self.capture.channels, self.capture.sample_rate)
            except OSError as e:
                live_i18n.call(self.status.setText, tr("window.cannot_create_file", e.strerror))
                return
        else:
            self.session.toggle_pause()
        self._apply_state()

    def _apply_state(self) -> None:
        state = self.session.state
        busy = state != IDLE
        live_i18n.call(self.rec_btn.setText, {IDLE: tr("window.record"), REC: tr("window.pause"), PAUSE: tr("window.resume")}[state])
        self.stop_btn.setEnabled(busy)
        self.dev.setEnabled(not busy)
        live_i18n.call(self.status.setText, {IDLE: tr("window.ready_record"), REC: tr("window.recording"),
                                             PAUSE: tr("window.paused")}[state])

    def stop(self) -> None:
        if self.session.idle:
            return
        path = self.session.stop()
        self._apply_state()
        if path:
            self._add_item(path, top=True)
            live_i18n.call(self.status.setText, tr("window.saved", path.name))
        live_i18n.call(self.time_label.setText, "00:00")

    # --- папка и список
    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("window.recordings_folder"), str(self.folder))
        if d:
            self.folder = Path(d)
            live_i18n.call(self.folder_edit.setText, d)
            self._save()
            self._scan_folder()

    def _add_item(self, path: Path, top: bool = False) -> None:
        it = live_i18n.call(QListWidgetItem, f"{path.name}    {wav_len(path)}")
        it.setData(Qt.ItemDataRole.UserRole, str(path))
        self.list.insertItem(0, it) if top else live_i18n.call(self.list.addItem, it)
        if top:
            self.list.setCurrentItem(it)

    def _scan_folder(self) -> None:
        self.list.clear()
        try:
            files = sorted(self.folder.glob("recording_*.wav"), reverse=True)[:20]
        except OSError:
            files = []
        for f in files:
            self._add_item(f)

    def _selected_path(self) -> Path | None:
        it = self.list.currentItem()
        if it:
            return Path(it.data(Qt.ItemDataRole.UserRole))
        live_i18n.call(self.status.setText, tr("window.select_recording_list"))
        return None

    # --- воспроизведение
    def play_selected(self) -> None:
        if self.playback.is_playing():
            self.playback.stop()
            return
        path = self._selected_path()
        if path:
            self.playback.play(path)

    def _play_state(self, playing: bool) -> None:
        live_i18n.call(self.play_btn.setText, tr("common.stop") if playing else tr("window.play"))

    def _play_error(self, message: str) -> None:
        live_i18n.call(self.status.setText, tr("window.playback_error", message))

    # --- обрезка
    def trim_selected(self) -> None:
        path = self._selected_path()
        if not path:
            return
        self.playback.stop()
        dlg = TrimDialog(self, path, self.playback)
        if not dlg.ok:
            return
        if dlg.exec() and dlg.result_path:
            self._scan_folder()
            for i in range(self.list.count()):
                item = self.list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == str(dlg.result_path):
                    self.list.setCurrentItem(item)
            live_i18n.call(self.status.setText, tr("window.saved", dlg.result_path.name))

    def closeEvent(self, e) -> None:
        self.stop()
        self.playback.stop()
        self.capture.close()
        self._save()
        e.accept()
