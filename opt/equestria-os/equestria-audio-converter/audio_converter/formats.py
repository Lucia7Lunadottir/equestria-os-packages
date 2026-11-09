"""Аудиоформаты и всё, что от них зависит (битрейты, частоты, каналы)."""
from __future__ import annotations

from dataclasses import dataclass



@dataclass(frozen=True)
class AudioFormat:
    """Формат звука на выходе. bitrates пуст — формат без потерь (битрейт не выбирается)."""
    name: str
    ext: str
    codec: tuple                 # параметры ffmpeg: кодек (и, если надо, контейнер)
    bitrates: tuple = ()
    default_br: str = ""
    rates: tuple = ()            # допустимые частоты, Гц; () — любая
    mono_only: bool = False


LOSSY_BR = ("320k", "256k", "192k", "160k", "128k", "96k", "64k")
AUDIO_FORMATS = {  # id -> формат; порядок = порядок в списке. id хранится в настройках.
    "mp3": AudioFormat("MP3", "mp3", ("-c:a", "libmp3lame"), ("V0", "V2", "V4") + LOSSY_BR + ("48k", "32k"), "192k",
                       (48000, 44100, 32000, 24000, 22050, 16000)),
    "aac": AudioFormat("AAC (M4A)", "m4a", ("-c:a", "aac"), LOSSY_BR, "192k"),
    "opus": AudioFormat("Opus", "opus", ("-c:a", "libopus"),
                        ("256k", "192k", "160k", "128k", "96k", "64k", "48k", "32k", "24k"), "128k",
                        (48000, 24000, 16000, 12000, 8000)),
    "ogg": AudioFormat("OGG Vorbis", "ogg", ("-c:a", "libvorbis"), LOSSY_BR, "192k"),
    "m4r": AudioFormat("formats.iphone_ringtone_m4r", "m4r", ("-c:a", "aac", "-f", "ipod"), LOSSY_BR, "256k"),
    "wma": AudioFormat("WMA", "wma", ("-c:a", "wmav2"), LOSSY_BR, "192k",
                       (48000, 44100, 32000, 22050, 16000, 11025, 8000)),
    "ac3": AudioFormat("AC3 (Dolby Digital)", "ac3", ("-c:a", "ac3"),
                       ("640k", "448k", "384k", "256k", "192k", "128k"), "448k", (48000, 44100, 32000)),
    "eac3": AudioFormat("E-AC3 (Dolby Digital Plus)", "eac3", ("-c:a", "eac3"),
                        ("640k", "448k", "384k", "256k", "192k", "128k"), "384k", (48000, 44100, 32000)),
    "mp2": AudioFormat("MP2", "mp2", ("-c:a", "mp2"), ("384k", "320k", "256k", "192k", "128k"), "256k",
                       (48000, 44100, 32000)),
    "amr": AudioFormat("formats.amr_voice_old_phones", "amr", ("-c:a", "libopencore_amrnb"),
                       ("12.2k", "10.2k", "7.95k", "7.4k", "6.7k", "5.9k", "5.15k", "4.75k"), "12.2k",
                       (8000,), mono_only=True),
    "flac": AudioFormat("formats.flac_lossless", "flac", ("-c:a", "flac")),
    "alac": AudioFormat("formats.alac_apple_lossless_m4a", "m4a", ("-c:a", "alac")),
    "wavpack": AudioFormat("formats.wavpack_lossless", "wv", ("-c:a", "wavpack")),
    "wav": AudioFormat("formats.wav_16_bit_lossless", "wav", ("-c:a", "pcm_s16le")),
    "wav24": AudioFormat("formats.wav_24_bit_lossless", "wav", ("-c:a", "pcm_s24le")),
    "wav32f": AudioFormat("formats.wav_32_bit_float_lossless", "wav", ("-c:a", "pcm_f32le")),
    "aiff": AudioFormat("formats.aiff_lossless", "aiff", ("-c:a", "pcm_s16be")),
}
DEFAULT_FORMAT = "mp3"
SAMPLE_RATES = (8000, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000)
CHANNELS = {0: "formats.channels_as_source", 1: "formats.mono", 2: "formats.stereo"}

# Переменный битрейт MP3 (LAME -q:a): размер подстраивается под сложность звука
VBR_NAMES = {"V0": "formats.variable_best_v0", "V2": "formats.variable_high_v2",
             "V4": "formats.variable_medium_v4"}
TAG_KEYS = ("artist", "album", "date", "genre")


def format_id(value) -> str:
    """id формата из настроек; старые версии хранили название («MP3», «FLAC (без потерь)»)."""
    if value in AUDIO_FORMATS:
        return value
    for fid, f in AUDIO_FORMATS.items():
        if value == f.name:
            return fid
    return {"formats.flac_lossless": "flac", "formats.wav_lossless": "wav", "AAC (M4A)": "aac"}.get(value, DEFAULT_FORMAT)


def target_rate(f: AudioFormat, rate: int, src_rate: int | None) -> int:
    """Частота на выходе: выбранная (0 — как в исходнике), но из допустимых для формата."""
    want = rate or src_rate or 0
    if not f.rates:
        return want
    if want in f.rates:
        return want
    if not want:  # ffmpeg сам возьмёт подходящую — кроме кодеков с единственной частотой (AMR)
        return f.rates[0] if len(f.rates) == 1 else 0
    return min(f.rates, key=lambda r: (abs(r - want), -r))
