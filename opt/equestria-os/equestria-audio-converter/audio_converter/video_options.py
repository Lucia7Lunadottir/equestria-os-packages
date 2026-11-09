"""Варианты для видео: формат, размеры, гистограмма."""
from __future__ import annotations


VIDEO_FORMATS = {  # id -> (название, расширение)
    "mp4": ("MP4 (H.264 + AAC)", "mp4"),
    "webm": ("WebM (VP9 + Opus)", "webm"),
    "mkv": ("MKV (H.264 + AAC)", "mkv"),
}
DEFAULT_VIDEO_FORMAT = "mp4"
RESOLUTIONS = {
    "1920×1080 — YouTube": (1920, 1080),
    "3840×2160 — 4K": (3840, 2160),
    "2560×1440": (2560, 1440),
    "1280×720": (1280, 720),
    "854×480": (854, 480),
    "video_options.1080_1080_square": (1080, 1080),
    "common.1080_1920_vertical": (1080, 1920),
}
VIZ_NONE = "video_options.none"
VIZ_BARS = "video_options.bars"
VIZ_WAVE = "video_options.wave"
VIZ_STYLES = [VIZ_NONE, VIZ_BARS, VIZ_WAVE]
VIZ_SIZES = {"video_options.low": 0.18, "common.medium": 0.28, "video_options.high": 0.42}
VIZ_TOP, VIZ_CENTER, VIZ_BOTTOM = "video_options.top", "video_options.center", "video_options.bottom"
VIZ_POS = [VIZ_BOTTOM, VIZ_CENTER, VIZ_TOP]
VIZ_COLORS = [("video_options.theme_color_accent", "accent"), ("video_options.light", "text"), ("video_options.green", "green"),
              ("video_options.red", "red"), ("video_options.yellow", "yellow")]
IMAGE_FILTER = "video_options.images_png_jpg_jpeg_webp"
