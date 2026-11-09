"""Сборка команд ffmpeg. Здесь нет окон — только списки аргументов."""
from __future__ import annotations

from pathlib import Path

from .formats import AUDIO_FORMATS, VBR_NAMES, target_rate
from .fx import LOUDNORM, audio_filters
from .video_options import (DEFAULT_VIDEO_FORMAT, VIZ_BARS, VIZ_BOTTOM, VIZ_CENTER, VIZ_NONE,
                            VIZ_SIZES, VIZ_TOP)


def unique_path(folder: Path, stem: str, ext: str, avoid: Path | None = None) -> Path:
    """Имя файла, которое не затрёт существующий (и не совпадёт с исходником)."""
    p = folder / f"{stem}.{ext}"
    k = 1
    while p.exists() or (avoid is not None and p == avoid):
        p = folder / f"{stem}_{k}.{ext}"
        k += 1
    return p


def parse_progress(line: str) -> float | None:
    """Строка из `-progress` -> сколько секунд уже обработано."""
    line = line.strip()
    for key in ("out_time_us=", "out_time_ms="):  # обе — в микросекундах
        if line.startswith(key):
            try:
                return max(0.0, int(line[len(key):]) / 1e6)
            except ValueError:
                return None
    return None


def audio_cmd(ffmpeg: str, src: str, dst: str, fmt: str, bitrate: str, rate: int = 0,
              channels: int = 0, normalize: bool = False, src_rate: int | None = None,
              fx: dict | None = None, dur: float | None = None, tags: dict | None = None) -> list[str]:
    """Команда ffmpeg для звука. rate/channels 0 — как в исходнике; fx — обработка
    (start, end, fade_in, fade_out, speed, speed_mode, gain, reverse); tags — теги, пустые не трогаются.
    src_rate (частота исходника) нужен при выравнивании громкости, для режима speed_mode="pitch"
    и для форматов с ограниченным набором частот."""
    f = AUDIO_FORMATS[fmt]
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", src,
           "-vn", "-map", "0:a:0", "-map_metadata", "0", *f.codec]
    if f.bitrates:
        br = bitrate if bitrate in f.bitrates else f.default_br
        cmd += ["-q:a", br[1:]] if br in VBR_NAMES else ["-b:a", br]
    chain = audio_filters(fx or {}, dur, normalize, src_rate)
    if chain:
        cmd += ["-af", ",".join(chain)]
    for key, value in (tags or {}).items():
        if value.strip():
            cmd += ["-metadata", f"{key}={value.strip()}"]
    out_rate = target_rate(f, rate, src_rate if normalize or f.rates else None)
    if out_rate:
        cmd += ["-ar", str(out_rate)]
    ch = 1 if f.mono_only else channels
    if ch:
        cmd += ["-ac", str(ch)]
    return cmd + ["-progress", "pipe:1", "-nostats", dst]


def video_cmd(ffmpeg: str, audio: str, image: str, dst: str, size: tuple[int, int],
              viz: str, viz_size: str, viz_pos: str, viz_color: str, bg: str,
              duration: float | None = None, preview_at: float | None = None,
              vfmt: str = DEFAULT_VIDEO_FORMAT, normalize: bool = False) -> list[str]:
    """Видео из звука и картинки. preview_at задан — получаем один кадр-PNG."""
    W, H = size
    fps = 30 if viz != VIZ_NONE else 10
    bgc = "0x" + bg.lstrip("#")
    vc = "0x" + viz_color.lstrip("#")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    if image:
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", image]
    else:  # без картинки — просто цветной фон
        cmd += ["-f", "lavfi", "-i", f"color=c={bgc}:s={W}x{H}:r={fps}"]
    if preview_at is not None:
        cmd += ["-ss", f"{preview_at:.2f}"]
    cmd += ["-i", audio]
    chain = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
             f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bgc},setsar=1,format=yuv420p")
    if viz == VIZ_NONE:
        fc = chain + "[v]"
    else:
        vw = int(W * 0.8) // 2 * 2
        vh = int(H * VIZ_SIZES[viz_size]) // 2 * 2
        margin = int(H * 0.05)
        y = {VIZ_BOTTOM: f"H-h-{margin}", VIZ_CENTER: "(H-h)/2", VIZ_TOP: str(margin)}[viz_pos]
        if viz == VIZ_BARS:
            gen = (f"showfreqs=s={vw}x{vh}:mode=bar:fscale=log:ascale=sqrt:"
                   f"win_size=4096:rate={fps}:colors={vc}")
        else:
            gen = f"showwaves=s={vw}x{vh}:mode=cline:draw=full:scale=sqrt:rate={fps}:colors={vc}"
        fc = (f"{chain}[bg];[1:a]{gen},format=rgba,colorkey=0x000000:0.15:0.1[viz];"
              f"[bg][viz]overlay=x=(W-w)/2:y={y}:format=auto,format=yuv420p[v]")
    cmd += ["-filter_complex", fc, "-map", "[v]"]
    if preview_at is not None:  # короткий кусок; в файле остаётся последний кадр
        return cmd + ["-t", "0.6", "-update", "1", dst]
    cmd += ["-map", "1:a:0"]
    if vfmt == "webm":
        cmd += ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "33", "-deadline", "good",
                "-cpu-used", "4", "-row-mt", "1", "-r", str(fps)]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(fps)]
        if viz == VIZ_NONE:
            cmd += ["-tune", "stillimage"]
    if normalize:
        cmd += ["-af", LOUDNORM, "-ar", "48000"]
    if vfmt == "webm":
        cmd += ["-c:a", "libopus", "-b:a", "160k"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    if vfmt == "mp4":
        cmd += ["-movflags", "+faststart"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    return cmd + ["-shortest", "-progress", "pipe:1", "-nostats", dst]
