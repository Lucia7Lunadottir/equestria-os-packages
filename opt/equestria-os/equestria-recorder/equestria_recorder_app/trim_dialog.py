"""Окно обрезки записи: выделение на волне или секундами, прослушивание, сохранение."""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from equestria_kit import live_i18n

from .formatting import fmt_t
from .localization import tr
from .playback import Playback
from .wav_clip import WavClip, free_copy_path
from .widgets import Waveform, confirm


class TrimDialog(QDialog):
    def __init__(self, parent, path: Path, playback: Playback):
        super().__init__(parent)
        self.path, self.playback = path, playback
        self.result_path: Path | None = None
        self.ok = False
        self.playing = False
        self.seen_playing = False
        live_i18n.call(self.setWindowTitle, tr("trim_dialog.trim_recording"))
        self.setMinimumWidth(540)
        try:
            self.clip = WavClip.load(path)
        except Exception as e:
            QMessageBox.warning(parent, tr("trim_dialog.trimming"), tr("trim_dialog.could_not_open_file", e))
            return
        self.dur = self.clip.duration
        self.ok = True
        self._build()
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._update_info()

    def _build(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        title = live_i18n.call(QLabel, self.path.name)
        title.setObjectName("h2")
        v.addWidget(title)
        hint = live_i18n.call(QLabel, tr("trim_dialog.drag_markers_waveform_enter_seconds"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.wave = Waveform(self.clip.peaks())
        self.wave.changed.connect(self._from_wave)
        v.addWidget(self.wave)

        self.sp_s, self.sp_e = self._spin(0.0), self._spin(self.dur)
        self.sp_s.editingFinished.connect(self._from_spins)
        self.sp_e.editingFinished.connect(self._from_spins)
        row = QHBoxLayout()
        for cap, sp in ((tr("trim_dialog.start_s"), self.sp_s), (tr("trim_dialog.end_s"), self.sp_e)):
            col = QVBoxLayout()
            col.setSpacing(2)
            lab = live_i18n.call(QLabel, cap)
            lab.setObjectName("hint")
            col.addWidget(lab)
            col.addWidget(sp)
            row.addLayout(col, 1)
        v.addLayout(row)

        self.keep_btn = live_i18n.call(QPushButton, tr("trim_dialog.keep_selection"))
        self.cut_btn = live_i18n.call(QPushButton, tr("trim_dialog.cut_selection"))
        for b, cut in ((self.keep_btn, False), (self.cut_btn, True)):
            b.setObjectName("small")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, c=cut: self._set_mode(c))
        self.keep_btn.setChecked(True)
        mrow = QHBoxLayout()
        mrow.addWidget(self.keep_btn)
        mrow.addWidget(self.cut_btn)
        v.addLayout(mrow)
        self.info = live_i18n.call(QLabel, "")
        self.info.setObjectName("hint")
        v.addWidget(self.info)

        self.prev_btn = live_i18n.call(QPushButton, tr("trim_dialog.play_selection"))
        self.prev_btn.clicked.connect(self._toggle_preview)
        v.addWidget(self.prev_btn)
        brow = QHBoxLayout()
        cancel = live_i18n.call(QPushButton, tr("common.cancel"))
        cancel.clicked.connect(self.reject)
        repl = live_i18n.call(QPushButton, tr("trim_dialog.replace_original"))
        repl.clicked.connect(lambda: self._save(True))
        save = live_i18n.call(QPushButton, tr("trim_dialog.save_as_copy"))
        save.setObjectName("primary")
        save.clicked.connect(lambda: self._save(False))
        brow.addWidget(cancel)
        brow.addStretch()
        brow.addWidget(repl)
        brow.addWidget(save)
        v.addLayout(brow)

    def _spin(self, value: float) -> QLineEdit:
        """Поле для секунд (обычное текстовое поле: со спинбоксами QSS глючит)."""
        e = QLineEdit(f"{value:.2f}")
        e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return e

    def _num(self, edit: QLineEdit, fallback: float) -> float:
        try:
            v = float(edit.text().replace(",", ".").strip())
        except ValueError:
            return fallback
        return max(0.0, min(self.dur, v))

    # --- синхронизация
    def _from_wave(self) -> None:
        for sp, f in ((self.sp_s, self.wave.s), (self.sp_e, self.wave.e)):
            live_i18n.call(sp.setText, f"{f * self.dur:.2f}")
        self._update_info()

    def _from_spins(self) -> None:
        s = self._num(self.sp_s, self.wave.s * self.dur)
        e = self._num(self.sp_e, self.wave.e * self.dur)
        self.wave.set_range(s / self.dur, e / self.dur)
        self._from_wave()

    def _set_mode(self, cut: bool) -> None:
        self.cut_btn.setChecked(cut)
        self.keep_btn.setChecked(not cut)
        self.wave.cut = cut
        self.wave.update()
        self._update_info()

    def _update_info(self) -> None:
        sel = (self.wave.e - self.wave.s) * self.dur
        rest = self.dur - sel if self.wave.cut else sel
        live_i18n.call(self.info.setText, tr("trim_dialog.was_selected_will_remain", fmt_t(self.dur), fmt_t(sel), fmt_t(rest)))

    # --- прослушивание
    def _toggle_preview(self) -> None:
        if self.playing:
            self._stop_preview()
            return
        self.playing, self.seen_playing = True, False
        live_i18n.call(self.prev_btn.setText, tr("common.stop"))
        self.playback.play(self.path, int(self.wave.s * self.dur * 1000))

    def _stop_preview(self) -> None:
        self.playing = False
        self.playback.stop()
        self.wave.play = None
        self.wave.update()
        live_i18n.call(self.prev_btn.setText, tr("trim_dialog.play_selection"))

    def _tick(self) -> None:
        if not self.playing or self.playback.loading:
            return
        pos = self.playback.position()
        if self.playback.is_playing():
            self.seen_playing = True
        elif self.seen_playing:
            self._stop_preview()
            return
        if pos >= self.wave.e * self.dur:
            self._stop_preview()
            return
        self.wave.play = pos / self.dur
        self.wave.update()

    # --- сохранение
    def _save(self, replace: bool) -> None:
        out = self.clip.slice(self.wave.s, self.wave.e, self.wave.cut)
        if not out:
            QMessageBox.warning(self, tr("trim_dialog.trimming"), tr("trim_dialog.result_would_empty_file_change"))
            return
        self._stop_preview()
        try:
            if replace:
                if not confirm(self, tr("trim_dialog.original_will_overwritten_cannot_restored"),
                               tr("trim_dialog.replace")):
                    return
                tmp = self.path.with_name(self.path.stem + ".tmp")
                self.clip.write(tmp, out)
                os.replace(tmp, self.path)
                self.result_path = self.path
            else:
                new = free_copy_path(self.path)
                self.clip.write(new, out)
                self.result_path = new
        except OSError as e:
            QMessageBox.warning(self, tr("trim_dialog.trimming"), tr("trim_dialog.could_not_save", e.strerror))
            return
        self.accept()

    def done(self, r: int) -> None:
        if self.ok:
            self._stop_preview()
        super().done(r)
