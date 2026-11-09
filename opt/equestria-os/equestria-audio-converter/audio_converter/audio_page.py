"""Страница настроек «Аудио»: формат, обработка, теги."""
from __future__ import annotations

from PyQt6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ._kit import card, small_btn, tr
from .formats import AUDIO_FORMATS, CHANNELS, SAMPLE_RATES, TAG_KEYS, format_id
from .fx import (DEFAULT_SPEED_MODE, FADES, GAINS, SPEED_MAX, SPEED_MIN, SPEED_MODES,
                 parse_time)
from .widgets import combo, pick_data, set_error


class AudioPage(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._cfg = cfg
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._format_card())
        v.addWidget(self._fx_card())
        v.addWidget(self._tags_card())
        self._fmt_changed(rate=cfg.get("rate", 0))

    # ── формат ──────────────────────────────────────────────────────────────
    def _format_card(self) -> QWidget:
        cfg = self._cfg
        self.fmt = combo(())
        for fid, f in AUDIO_FORMATS.items():
            self.fmt.addItem(tr(f.name), fid)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(format_id(cfg.get("fmt")))))
        self._last_br = str(cfg.get("br") or "192k")
        self.br = combo(())
        self.br.activated.connect(lambda _i: setattr(self, "_last_br", self.br.currentData() or self._last_br))
        self.rate = combo(())
        self.ch = combo(())
        for k, name in CHANNELS.items():
            self.ch.addItem(tr(name), k)
        self.ch.setCurrentIndex(max(0, self.ch.findData(cfg.get("ch", 0))))
        self.fmt.currentIndexChanged.connect(lambda _i: self._fmt_changed())
        row = QHBoxLayout()
        row.addWidget(self.fmt, 2)
        row.addWidget(self.br, 1)
        row2 = QHBoxLayout()
        row2.addWidget(self.rate, 1)
        row2.addWidget(self.ch, 1)
        hint = QLabel(tr("audio_page.right_quality_bitrate_video_files"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        return card(tr("audio_page.audio_format"), row, row2, hint)

    def _fmt_changed(self, br: str | None = None, rate=None) -> None:
        """Списки битрейта и частоты — только то, что умеет выбранный формат."""
        f = AUDIO_FORMATS[self.fmt.currentData()]
        want_br = br or self._last_br
        want_rate = self.rate.currentData() if rate is None else rate
        self.br.blockSignals(True)
        self.br.clear()
        if f.bitrates:
            for b in f.bitrates:
                self.br.addItem(tr("audio_page.kbps", b[:-1]), b)
            self.br.setCurrentIndex(max(0, self.br.findData(want_br if want_br in f.bitrates else f.default_br)))
            if want_br in f.bitrates:
                self._last_br = want_br
        else:
            self.br.addItem(tr("audio_page.lossless"), "")
        self.br.setEnabled(bool(f.bitrates))
        self.br.blockSignals(False)
        self.rate.clear()
        self.rate.addItem(tr("audio_page.sample_rate_as_source"), 0)
        for r in f.rates or SAMPLE_RATES:
            self.rate.addItem(tr("audio_page.khz", f"{r / 1000:g}"), r)
        self.rate.setCurrentIndex(max(0, self.rate.findData(want_rate)))
        if f.mono_only and self.ch.isEnabled():
            self._ch_before_mono = self.ch.currentData()  # вернём, когда формат снова позволит
            self.ch.setCurrentIndex(self.ch.findData(1))
        elif not f.mono_only and not self.ch.isEnabled():
            self.ch.setCurrentIndex(max(0, self.ch.findData(getattr(self, "_ch_before_mono", 0))))
        self.ch.setEnabled(not f.mono_only)

    # ── обработка ───────────────────────────────────────────────────────────
    def _fx_card(self) -> QWidget:
        cfg = self._cfg
        self.t_start = QLineEdit()
        self.t_start.setPlaceholderText(tr("audio_page.start_0_00"))
        self.t_end = QLineEdit()
        self.t_end.setPlaceholderText(tr("audio_page.end_end_file"))
        for e in (self.t_start, self.t_end):
            e.setToolTip(tr("audio_page.time_seconds_90_minutes_seconds"))
            e.textEdited.connect(lambda _t: self.fx())

        self.fade_in = combo(())
        self.fade_out = combo(())
        for box, none in ((self.fade_in, tr("audio_page.no_fade")), (self.fade_out, tr("audio_page.no_fade_out"))):
            for sec in FADES:
                box.addItem(none if not sec else (tr("audio_page.fade_s", sec) if box is self.fade_in
                                                  else tr("audio_page.fade_out_s", sec)), sec)
        self.gain = combo(())
        for g in GAINS:
            self.gain.addItem(tr("audio_page.no_gain") if not g else tr("audio_page.volume_db", f"{g:+d}"), g)
        for box, key, default in ((self.fade_in, "fade_in", 0), (self.fade_out, "fade_out", 0),
                                  (self.gain, "gain", 0)):
            box.setCurrentIndex(max(0, box.findData(cfg.get(key, default))))

        # скорость: произвольный числовой множитель
        self.speed = QDoubleSpinBox()
        self.speed.setRange(SPEED_MIN, SPEED_MAX)
        self.speed.setDecimals(2)
        self.speed.setSingleStep(0.01)
        self.speed.setSuffix("×")
        self.speed.setMinimumHeight(34)
        self.speed.setToolTip(tr("audio_page.1_00_unchanged_you_can"))
        self.speed.setValue(self._float(cfg.get("speed"), 1.0))
        self.speed_mode = combo(())
        for key, name in SPEED_MODES.items():
            self.speed_mode.addItem(tr(name), key)
        pick_data(self.speed_mode, cfg.get("speed_mode", DEFAULT_SPEED_MODE))

        self.reverse = small_btn(tr("audio_page.reverse"), True)
        reset = small_btn(tr("audio_page.reset"))
        reset.clicked.connect(self.reset_fx)
        r1 = QHBoxLayout()
        r1.addWidget(self.t_start, 1)
        r1.addWidget(self.t_end, 1)
        r2 = QHBoxLayout()
        r2.addWidget(self.fade_in, 1)
        r2.addWidget(self.fade_out, 1)
        r3 = QHBoxLayout()
        r3.addWidget(self.speed, 1)
        r3.addWidget(self.speed_mode, 2)
        speed_hint = QLabel(tr("audio_page.when_speed_pitch_change_together"))
        speed_hint.setObjectName("hint")
        speed_hint.setWordWrap(True)
        r4 = QHBoxLayout()
        r4.addWidget(self.gain, 1)
        r4.addWidget(self.reverse)
        r5 = QHBoxLayout()
        r5.addStretch()
        r5.addWidget(reset)
        return card(tr("audio_page.processing"), r1, r2, r3, speed_hint, r4, r5)

    @staticmethod
    def _float(value, default: float) -> float:
        try:
            return min(SPEED_MAX, max(SPEED_MIN, float(value)))
        except (TypeError, ValueError):
            return default

    def fx(self) -> dict | None:
        """Обработка из полей; None — время введено с ошибкой (поле подсвечивается)."""
        start, end = parse_time(self.t_start.text()), parse_time(self.t_end.text())
        bad_end = end is None or (bool(end) and start is not None and end <= start)
        set_error(self.t_start, start is None)
        set_error(self.t_end, bad_end)
        if start is None or bad_end:
            return None
        return dict(start=start, end=end, fade_in=self.fade_in.currentData(), fade_out=self.fade_out.currentData(),
                    speed=round(self.speed.value(), 2), speed_mode=self.speed_mode.currentData(),
                    gain=self.gain.currentData(), reverse=self.reverse.isChecked())

    def reset_fx(self) -> None:
        self.t_start.clear()
        self.t_end.clear()
        for box, value in ((self.fade_in, 0), (self.fade_out, 0), (self.gain, 0)):
            box.setCurrentIndex(box.findData(value))
        self.speed.setValue(1.0)
        self.reverse.setChecked(False)
        self.fx()

    # ── теги ────────────────────────────────────────────────────────────────
    def _tags_card(self) -> QWidget:
        self.tag_edits: dict[str, QLineEdit] = {}
        labels = {"artist": tr("audio_page.artist"), "album": tr("audio_page.album"), "date": tr("audio_page.year"), "genre": tr("audio_page.genre")}
        rows = (QHBoxLayout(), QHBoxLayout())
        for i, key in enumerate(TAG_KEYS):
            e = QLineEdit()
            e.setPlaceholderText(labels[key])
            self.tag_edits[key] = e
            rows[i // 2].addWidget(e, 1)
        hint = QLabel(tr("audio_page.empty_fields_keep_tags_from"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        return card(tr("audio_page.tags"), *rows, hint)

    def tags(self) -> dict:
        return {k: e.text() for k, e in self.tag_edits.items()}

    # ── сохранение и наборы ─────────────────────────────────────────────────
    def settings(self) -> dict:
        return dict(fmt=self.fmt.currentData(), br=self.br.currentData() or self._last_br,
                    rate=self.rate.currentData(), ch=self.ch.currentData(),
                    fade_in=self.fade_in.currentData(), fade_out=self.fade_out.currentData(),
                    speed=round(self.speed.value(), 2), speed_mode=self.speed_mode.currentData(),
                    gain=self.gain.currentData())

    def apply(self, st: dict) -> None:
        """Подставить настройки набора; чего в наборе нет — остаётся как есть."""
        if "fmt" in st:
            self.fmt.blockSignals(True)
            pick_data(self.fmt, format_id(st["fmt"]))
            self.fmt.blockSignals(False)
            self._fmt_changed(br=st.get("br") or None, rate=st.get("rate", 0))
        for key, box in (("ch", self.ch), ("fade_in", self.fade_in), ("fade_out", self.fade_out),
                         ("gain", self.gain), ("speed_mode", self.speed_mode)):
            if key in st:
                pick_data(box, st[key])
        if "speed" in st:
            self.speed.setValue(self._float(st["speed"], 1.0))
