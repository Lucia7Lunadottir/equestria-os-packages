"""Страница настроек «Видео из аудио»: картинка, формат, гистограмма."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ._kit import card, tr
from .video_options import (DEFAULT_VIDEO_FORMAT, IMAGE_FILTER, RESOLUTIONS, VIDEO_FORMATS, VIZ_BARS,
                            VIZ_BOTTOM, VIZ_COLORS, VIZ_NONE, VIZ_POS, VIZ_SIZES, VIZ_STYLES)
from .widgets import combo, pick_data, pick_text


class VideoPage(QWidget):
    changed = pyqtSignal()             # поменяли картинку — надо сохранить настройки
    preview_requested = pyqtSignal()   # нажали «Предпросмотр кадра»

    def __init__(self, cfg: dict):
        super().__init__()
        self.image = str(cfg.get("image", ""))
        if self.image and not Path(self.image).is_file():
            self.image = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.pic = QLabel(tr("video_page.no_picture_colored_background_will"))
        self.pic.setObjectName("preview")
        self.pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pic.setFixedHeight(170)
        pick = QPushButton(tr("video_page.choose_picture_ellipsis"))
        pick.clicked.connect(self._pick_image)
        drop = QPushButton(tr("common.remove"))
        drop.clicked.connect(self._clear_image)
        prev = QPushButton(tr("video_page.frame_preview"))
        prev.clicked.connect(self.preview_requested)
        prow = QHBoxLayout()
        prow.addWidget(pick, 1)
        prow.addWidget(drop)
        v.addWidget(card(tr("video_page.picture_video"), self.pic, prow, prev))

        self.vfmt = combo(())
        for fid, (name, _ext) in VIDEO_FORMATS.items():
            self.vfmt.addItem(name, fid)
        self.vfmt.setCurrentIndex(max(0, self.vfmt.findData(cfg.get("vfmt", DEFAULT_VIDEO_FORMAT))))
        self.res = combo(RESOLUTIONS, cfg.get("res"))
        vrow = QHBoxLayout()
        vrow.addWidget(self.vfmt, 1)
        vrow.addWidget(self.res, 1)
        v.addWidget(card(tr("video_page.video_format_size"), vrow))

        self.viz = combo(VIZ_STYLES, cfg.get("viz", VIZ_BARS))
        self.viz_size = combo(VIZ_SIZES, cfg.get("viz_size", "common.medium"))
        self.viz_pos = combo(VIZ_POS, cfg.get("viz_pos", VIZ_BOTTOM))
        self.viz_color = combo(())
        for name, key in VIZ_COLORS:
            self.viz_color.addItem(tr(name), key)
        self.viz_color.setCurrentIndex(max(0, self.viz_color.findData(cfg.get("viz_color", "accent"))))
        self.viz.currentIndexChanged.connect(self._viz_changed)
        r1 = QHBoxLayout()
        r1.addWidget(self.viz, 1)
        r1.addWidget(self.viz_color, 1)
        r2 = QHBoxLayout()
        r2.addWidget(self.viz_size, 1)
        r2.addWidget(self.viz_pos, 1)
        v.addWidget(card(tr("video_page.audio_histogram"), r1, r2))
        self._viz_changed()
        if self.image:
            self._show_image()

    # ── картинка ────────────────────────────────────────────────────────────
    def _pick_image(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("video_page.choose_picture"), str(Path.home()), tr(IMAGE_FILTER))
        if p:
            self.image = p
            self._show_image()
            self.changed.emit()

    def _show_image(self) -> None:
        pm = QPixmap(self.image)
        if pm.isNull():
            self._clear_image()
            return
        self.show_pixmap(pm, self.pic.width() or 400)

    def _clear_image(self) -> None:
        self.image = ""
        self.pic.setPixmap(QPixmap())
        self.pic.setText(tr("video_page.no_picture_colored_background_will"))
        self.changed.emit()

    def show_pixmap(self, pm: QPixmap, width: int | None = None) -> None:
        self.pic.setPixmap(pm.scaled(width or self.pic.width(), self.pic.height(),
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))

    def _viz_changed(self) -> None:
        on = self.viz.currentData() != VIZ_NONE
        for w in (self.viz_size, self.viz_pos, self.viz_color):
            w.setEnabled(on)

    # ── сохранение, наборы и аргументы ffmpeg ───────────────────────────────
    def settings(self) -> dict:
        return dict(vfmt=self.vfmt.currentData(), res=self.res.currentData(), viz=self.viz.currentData(),
                    viz_size=self.viz_size.currentData(), viz_pos=self.viz_pos.currentData(),
                    viz_color=self.viz_color.currentData())

    def apply(self, st: dict) -> None:
        if "vfmt" in st:
            pick_data(self.vfmt, st["vfmt"])
        for key, box in (("res", self.res), ("viz", self.viz), ("viz_size", self.viz_size),
                         ("viz_pos", self.viz_pos)):
            if key in st:
                pick_text(box, st[key])
        if "viz_color" in st:
            pick_data(self.viz_color, st["viz_color"])

    def video_args(self, theme: dict, normalize: bool) -> dict:
        """Аргументы для commands.video_cmd (кроме звука и пути результата)."""
        return dict(image=self.image, size=RESOLUTIONS[self.res.currentData()],
                    vfmt=self.vfmt.currentData(), normalize=normalize,
                    viz=self.viz.currentData(), viz_size=self.viz_size.currentData(),
                    viz_pos=self.viz_pos.currentData(), viz_color=theme[self.viz_color.currentData()],
                    bg=theme["base"])
