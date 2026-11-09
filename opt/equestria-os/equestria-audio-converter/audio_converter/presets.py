"""Встроенные наборы быстрого экспорта.
Ключи: mode (0 — аудио, 1 — видео), fmt, br, rate, ch, norm, vfmt, res, viz, viz_size, viz_pos,
speed, speed_mode."""
from __future__ import annotations

from .video_options import VIZ_BARS, VIZ_CENTER, VIZ_WAVE

BUILTIN_PRESETS = [
    ("presets.music_mp3_320_kbps", dict(mode=0, fmt="mp3", br="320k", rate=0, ch=0, norm=False)),
    ("presets.podcast_voice_mp3_96_kbps",
     dict(mode=0, fmt="mp3", br="96k", rate=44100, ch=1, norm=True)),
    ("presets.phone_aac_192_kbps", dict(mode=0, fmt="aac", br="192k", rate=0, ch=0, norm=False)),
    ("presets.iphone_ringtone_m4r", dict(mode=0, fmt="m4r", br="256k", rate=44100, ch=0, norm=True)),
    ("presets.web_opus_128_kbps", dict(mode=0, fmt="opus", br="128k", rate=0, ch=0, norm=False)),
    ("presets.lossless_archive_flac", dict(mode=0, fmt="flac", br="", rate=0, ch=0, norm=False)),
    ("presets.editing_wav_24_bit_48", dict(mode=0, fmt="wav24", br="", rate=48000, ch=0, norm=False)),
    ("presets.youtube_1080p_video_with_bars",
     dict(mode=1, vfmt="mp4", res="1920×1080 — YouTube", viz=VIZ_BARS, norm=True)),
    ("presets.shorts_reels_tiktok_vertical_video",
     dict(mode=1, vfmt="mp4", res="common.1080_1920_vertical", viz=VIZ_WAVE, viz_pos=VIZ_CENTER, norm=True)),
]
