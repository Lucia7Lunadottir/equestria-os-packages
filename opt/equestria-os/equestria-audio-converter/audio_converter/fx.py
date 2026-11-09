"""Обработка звука: обрезка, скорость, усиление, нарастание/затухание → фильтры ffmpeg."""
from __future__ import annotations


# Выравнивание громкости по EBU R128: −14 LUFS — как на стримингах и YouTube
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"

FADES = (0, 1, 2, 3, 5, 10)
GAINS = (-12, -9, -6, -3, 0, 3, 6, 9, 12)

# Два способа менять скорость:
#   pitch — скорость и высота тона меняются вместе
#   tempo — меняется только скорость, тон остаётся прежним
SPEED_MODES = {
    "tempo": "fx.speed_only_keep_pitch_unchanged",
    "pitch": "fx.speed_pitch_together",
}
DEFAULT_SPEED_MODE = "tempo"
SPEED_MIN, SPEED_MAX = 0.1, 4.0


def parse_time(text: str) -> float | None:
    """«90», «1:30», «1:02:03.5» → секунды; пусто → 0; ошибка → None."""
    t = text.strip().replace(",", ".")
    if not t:
        return 0.0
    try:
        parts = [float(x) for x in t.split(":")]
    except ValueError:
        return None
    if len(parts) > 3 or any(x < 0 for x in parts) or any(x >= 60 for x in parts[1:]):
        return None
    sec = 0.0
    for x in parts:
        sec = sec * 60 + x
    return sec


def output_length(fx: dict, dur: float | None) -> float | None:
    """Длина результата после обрезки и смены скорости (None — неизвестна)."""
    start, end = fx.get("start", 0.0), fx.get("end", 0.0)
    if end:
        length = end - start if not dur else min(end, dur) - start
    elif dur:
        length = dur - start
    else:
        return None
    return max(0.0, length) / (fx.get("speed") or 1.0)


def tempo_filters(speed: float) -> list[str]:
    """atempo умеет только 0.5…2.0 за раз — для остального ставим несколько подряд."""
    out = []
    while speed < 0.5:
        out.append("atempo=0.5")
        speed /= 0.5
    while speed > 2.0:
        out.append("atempo=2.0")
        speed /= 2.0
    out.append(f"atempo={speed:.6g}")
    return out


def speed_filters(speed: float, mode: str, src_rate: int | None) -> list[str]:
    """Фильтры смены скорости. Режиму pitch нужна частота исходника."""
    if speed == 1.0:
        return []
    if mode == "pitch" and src_rate:
        # «Проигрываем» файл с другой частотой, затем возвращаем обычную: скорость и тон меняются вместе
        return [f"asetrate={round(src_rate * speed)}", f"aresample={src_rate}"]
    return tempo_filters(speed)


def audio_filters(fx: dict, dur: float | None, normalize: bool, src_rate: int | None = None) -> list[str]:
    """Цепочка: обрезка → задом наперёд → скорость → усиление → громкость → нарастание/затухание."""
    chain = []
    start, end = fx.get("start", 0.0), fx.get("end", 0.0)
    if start or end:
        chain.append("atrim=" + ":".join(([f"start={start:g}"] if start else []) + ([f"end={end:g}"] if end else [])))
        chain.append("asetpts=PTS-STARTPTS")
    if fx.get("reverse"):
        chain.append("areverse")
    chain += speed_filters(fx.get("speed") or 1.0, fx.get("speed_mode", DEFAULT_SPEED_MODE), src_rate)
    if fx.get("gain"):
        chain.append(f"volume={fx['gain']:g}dB")
    if normalize:
        chain.append(LOUDNORM)
    if fx.get("fade_in"):
        chain.append(f"afade=t=in:st=0:d={fx['fade_in']:g}")
    length = output_length(fx, dur)
    if fx.get("fade_out") and length:
        d = min(fx["fade_out"], length)
        chain.append(f"afade=t=out:st={max(0.0, length - d):.3f}:d={d:g}")
    return chain


def needs_source_rate(fx: dict) -> bool:
    """Для совместного изменения скорости и тона нужна частота исходного файла."""
    return fx.get("speed_mode") == "pitch" and (fx.get("speed") or 1.0) != 1.0
