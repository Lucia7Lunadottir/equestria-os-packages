"""Главное окно: собирает панели и запускает очередь."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QProgressBar, QPushButton, QScrollArea, QStackedWidget,
                             QVBoxLayout, QWidget)

from ._kit import card, kit_qt, small_btn, tr
from .localization import catalog
from .audio_page import AudioPage
from .commands import audio_cmd, unique_path, video_cmd
from .convert_queue import ConvertQueue, Job
from .file_list import FileList
from .formats import AUDIO_FORMATS
from .fx import needs_source_rate, output_length
from .presets_panel import PresetsPanel
from .probe import probe_duration, probe_sample_rate
from .style import THEME, apply_theme
from .video_options import VIDEO_FORMATS
from .video_page import VideoPage

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-converter" / "settings.json"


def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, theme: str):
        super().__init__()
        self.cfg, self.theme = cfg, theme
        self.ffmpeg = shutil.which("ffmpeg")
        self.out_dir = str(cfg.get("folder", ""))
        self.mode = int(cfg.get("mode", 0)) if int(cfg.get("mode", 0)) in (0, 1) else 0
        self.last_out: Path | None = None
        self.preview_path = Path(tempfile.gettempdir()) / "equestria-converter-preview.png"

        self.queue = ConvertQueue(self)
        self.queue.job_started.connect(self._job_started)
        self.queue.job_progress.connect(self._job_progress)
        self.queue.job_done.connect(self._job_done)
        self.queue.finished.connect(self._finish)

        self.setWindowTitle("Equestria Converter")
        self.resize(580, 800)
        self.setMinimumSize(520, 620)
        self._build_ui()

    # ── сборка окна ─────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("Equestria Converter")
        title.setObjectName("h2")
        theme_btn = QPushButton(tr("window.theme"))
        theme_btn.setObjectName("small")
        theme_btn.clicked.connect(lambda: kit_qt.theme_menu(self, theme_btn, self.theme, self._set_theme))
        top.addWidget(title)
        top.addStretch()
        self.language_combo = QComboBox()
        self.language_combo.setToolTip(tr("window.language"))
        for code in catalog.languages:
            self.language_combo.addItem(catalog.language_name(code), code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(catalog.lang))
        self.language_combo.activated.connect(self._select_language)
        top.addWidget(self.language_combo)
        top.addWidget(theme_btn)
        root.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(8)
        scroll.setWidget(self.body)
        root.addWidget(scroll, 1)

        # режим
        self.mode_btns = []
        mrow = QHBoxLayout()
        for i, name in enumerate((tr("window.audio"), tr("window.video_from_audio"))):
            b = QPushButton(name)
            b.setObjectName("mode")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=i: self._set_mode(k))
            self.mode_btns.append(b)
            mrow.addWidget(b, 1)
        body.addLayout(mrow)

        # панели
        self.audio = AudioPage(self.cfg)
        self.video = VideoPage(self.cfg)
        self.video.changed.connect(self._save)
        self.video.preview_requested.connect(self._preview)
        self.presets = PresetsPanel(self.cfg, self._current_settings)
        self.presets.applied.connect(self.apply_preset)
        self.presets.changed.connect(self._save)
        self.presets.message.connect(lambda m: self.status.setText(m))
        self.files = FileList()
        body.addWidget(self.presets)
        body.addWidget(card(tr("window.files"), self.files))

        self.norm = small_btn(tr("window.normalize_loudness_14_lufs"), True,
                              tr("window.quiet_loud_recordings_will_sound"))
        self.norm.setChecked(bool(self.cfg.get("norm", False)))
        self.stack = QStackedWidget()
        self.stack.addWidget(self.audio)
        self.stack.addWidget(self.video)
        body.addWidget(self.stack)
        norm_hint = QLabel(tr("window.useful_podcasts_ringtones_compilations_from"))
        norm_hint.setObjectName("hint")
        norm_hint.setWordWrap(True)
        nrow = QHBoxLayout()
        nrow.addWidget(self.norm)
        nrow.addStretch()
        body.addWidget(card(tr("window.loudness"), nrow, norm_hint))

        # куда сохранять
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        pick = QPushButton(tr("window.choose"))
        pick.clicked.connect(self._pick_folder)
        reset = QPushButton("×")
        reset.setObjectName("small")
        reset.setToolTip(tr("window.save_next_source_file"))
        reset.clicked.connect(self._reset_folder)
        orow = QHBoxLayout()
        orow.addWidget(self.out_edit, 1)
        orow.addWidget(pick)
        orow.addWidget(reset)
        body.addWidget(card(tr("window.save"), orow))
        body.addStretch()
        self._show_folder()

        # нижняя панель
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        self.go_btn = QPushButton(tr("window.convert"))
        self.go_btn.setObjectName("primary")
        self.go_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton(tr("window.cancel"))
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.queue.cancel)
        self.open_btn = QPushButton(tr("window.folder"))
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_result)
        brow = QHBoxLayout()
        brow.addWidget(self.go_btn, 3)
        brow.addWidget(self.cancel_btn, 1)
        brow.addWidget(self.open_btn)
        root.addWidget(self.bar)
        root.addWidget(self.status)
        root.addLayout(brow)

        self._set_mode(self.mode)
        if not self.ffmpeg:
            self.go_btn.setEnabled(False)
            self.status.setText(tr("window.ffmpeg_not_found_install_sudo"))
            self.status.setObjectName("warn")
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

    # ── файлы (в том числе открытые через «Открыть с помощью…») ─────────────
    def add_files(self, paths) -> None:
        self.files.add_files(paths)

    # ── настройки, темы, наборы ─────────────────────────────────────────────
    def _current_settings(self) -> dict:
        """Все настройки экспорта (то же, что хранит набор быстрого экспорта)."""
        return dict(mode=self.mode, norm=self.norm.isChecked(),
                    **self.audio.settings(), **self.video.settings())

    def _save(self) -> None:
        self.cfg.update(theme=self.theme, folder=self.out_dir, image=self.video.image,
                        **self._current_settings())
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _select_language(self, index: int) -> None:
        language = self.language_combo.itemData(index)
        if language not in catalog.languages or language == catalog.lang:
            return
        self._save()
        # Preserve transient input and list items (queue jobs refer to those items).
        trim = (self.audio.t_start.text(), self.audio.t_end.text())
        tags = self.audio.tags()
        reverse = self.audio.reverse.isChecked()
        last_br = self.audio._last_br
        ch_before_mono = getattr(self.audio, "_ch_before_mono", 0)
        selected_preset = self.presets.box.currentIndex()
        picture = self.video.pic.pixmap()
        progress = self.bar.value()
        running = self.cancel_btn.isEnabled()
        can_open = self.open_btn.isEnabled()
        scroll = self.centralWidget().findChild(QScrollArea).verticalScrollBar().value()
        items = [(self.files.item(i), self.files.item(i).isSelected())
                 for i in range(self.files.count())]
        while self.files.count():
            self.files.list.takeItem(0)
        old = self.takeCentralWidget()
        catalog.lang = language
        self.cfg["language"] = language
        self._build_ui()
        self.audio.t_start.setText(trim[0])
        self.audio.t_end.setText(trim[1])
        self.audio.reverse.setChecked(reverse)
        self.audio._last_br = last_br
        self.audio._ch_before_mono = ch_before_mono
        for key, value in tags.items():
            self.audio.tag_edits[key].setText(value)
        self.audio.fx()
        self.presets.box.setCurrentIndex(selected_preset)
        for item, selected in items:
            self.files.list.addItem(item)
            item.setSelected(selected)
        self.files._refresh()
        if picture is not None and not picture.isNull():
            self.video.show_pixmap(picture)
        self.bar.setValue(progress)
        self.open_btn.setEnabled(can_open)
        self._running(running)
        self.centralWidget().findChild(QScrollArea).verticalScrollBar().setValue(scroll)
        old.deleteLater()
        self._save()

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self._save()

    def apply_preset(self, st: dict) -> None:
        self.audio.apply(st)
        self.video.apply(st)
        if "norm" in st:
            self.norm.setChecked(bool(st["norm"]))
        if st.get("mode") in (0, 1):
            self._set_mode(st["mode"])  # он же сохраняет настройки
        else:
            self._save()

    def _set_mode(self, i: int) -> None:
        self.mode = i
        for k, b in enumerate(self.mode_btns):
            b.setChecked(k == i)
        self.stack.setCurrentIndex(i)
        self._save()

    # ── папка ───────────────────────────────────────────────────────────────
    def _show_folder(self) -> None:
        self.out_edit.setText(self.out_dir or tr("window.next_source_file"))

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("window.output_folder"), self.out_dir or str(Path.home()))
        if d:
            self.out_dir = d
            self._show_folder()
            self._save()

    def _reset_folder(self) -> None:
        self.out_dir = ""
        self._show_folder()
        self._save()

    def _open_result(self) -> None:
        if self.last_out:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_out.parent)))

    # ── предпросмотр кадра ──────────────────────────────────────────────────
    def _preview(self) -> None:
        if not self.ffmpeg:
            return
        if not self.files.count():
            self.status.setText(tr("window.add_audio_file_frame_built"))
            return
        src = self.files.path(0)
        dur = probe_duration(src)
        at = min(5.0, dur / 2) if dur else 0.0
        self.preview_path.unlink(missing_ok=True)
        cmd = video_cmd(self.ffmpeg, src, dst=str(self.preview_path), preview_at=at,
                        **self.video.video_args(THEME, self.norm.isChecked()))
        self.status.setText(tr("window.building_frame"))
        QApplication.processEvents()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as e:
            self.status.setText(tr("window.could_not_build_frame_fmt", e))
            return
        pm = QPixmap(str(self.preview_path))
        if r.returncode != 0 or pm.isNull():
            lines = [x for x in r.stderr.strip().splitlines() if x.strip()]
            self.status.setText(tr("window.could_not_build_frame") + (lines[-1] if lines else tr("window.status_ffmpeg_error")))
            return
        self.video.show_pixmap(pm)
        self.status.setText(tr("window.how_frame_will_look_picture"))

    # ── конвертация ─────────────────────────────────────────────────────────
    def start(self) -> None:
        n = self.files.count()
        if not n:
            self.status.setText(tr("window.add_files_first"))
            return
        if self.mode == 0 and self.audio.fx() is None:
            self.status.setText(tr("window.check_trim_times_start_end"))
            return
        jobs = []
        for i in range(n):
            src = self.files.path(i)
            sp = Path(src)
            folder = Path(self.out_dir) if self.out_dir else sp.parent
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.status.setText(tr("window.cannot_create_folder", e.strerror))
                return
            dst, build, length = self._job_command(src, folder)
            jobs.append(Job(src=src, dst=dst, name=sp.name, build=build, item=self.files.item(i), length=length))
        self._save()
        self.last_out = None
        self._running(True)
        self.queue.start(jobs)

    def _job_command(self, src: str, folder: Path):
        """(куда сохранить, как построить команду ffmpeg, длина результата) — по текущему режиму."""
        sp = Path(src)
        if self.mode == 0:
            st = self.audio.settings()
            fmt, br, rate, ch = st["fmt"], st["br"], st["rate"], st["ch"]
            norm = self.norm.isChecked()
            fx = self.audio.fx() or {}
            tags = self.audio.tags()
            f = AUDIO_FORMATS[fmt]
            dst = unique_path(folder, sp.stem, f.ext, avoid=sp)
            need_rate = needs_source_rate(fx) or ((norm or bool(f.rates)) and not rate)

            def build(dur):
                return audio_cmd(self.ffmpeg, src, str(dst), fmt, br, rate, ch, norm,
                                 src_rate=probe_sample_rate(src) if need_rate else None,
                                 fx=fx, dur=dur, tags=tags)
            return dst, build, lambda dur: output_length(fx, dur)
        dst = unique_path(folder, sp.stem, VIDEO_FORMATS[self.video.vfmt.currentData()][1], avoid=sp)
        args = self.video.video_args(THEME, self.norm.isChecked())
        return dst, lambda dur: video_cmd(self.ffmpeg, src, dst=str(dst), duration=dur, **args), None

    def _running(self, on: bool) -> None:
        self.body.setEnabled(not on)
        self.go_btn.setEnabled(not on and bool(self.ffmpeg))
        self.cancel_btn.setEnabled(on)

    @staticmethod
    def _set_item(job: Job, state: str) -> None:
        job.item.setText(f"{job.name}    {state}")

    def _job_started(self, index: int, total: int, job: Job) -> None:
        self.bar.setValue(0)
        self.status.setText(tr("window.file", index + 1, total, job.name))
        self._set_item(job, "0%")

    def _job_progress(self, job: Job, pct: int) -> None:
        self.bar.setValue(pct)
        self._set_item(job, f"{pct}%")

    def _job_done(self, job: Job, tail: list) -> None:
        if job.ok:
            self.bar.setValue(100)
            self._set_item(job, tr("window.status_done"))
            self.last_out = job.dst
            self.open_btn.setEnabled(True)
        elif self.queue.cancelled:
            self._set_item(job, tr("window.status_cancelled"))
        else:
            self._set_item(job, tr("window.status_error"))
            job.item.setToolTip("\n".join(tail) or tr("window.ffmpeg_error"))
            self.status.setText(tr("window.error") + (tail[-1] if tail else tr("window.ffmpeg_finished_with_error")))

    def _finish(self) -> None:
        done, failed = self.queue.counts()
        total = len(self.queue.jobs)
        self._running(False)
        if self.queue.cancelled:
            self.status.setText(tr("window.cancelled"))
        elif failed:
            self.status.setText(tr("window.done_failed_hover_over_file",
                                   done, total, failed))
        else:
            self.status.setText(tr("window.done", done, total))

    def closeEvent(self, e) -> None:
        self.queue.cancel()
        self._save()
        e.accept()
