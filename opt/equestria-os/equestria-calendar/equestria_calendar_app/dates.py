"""calendar: dates."""
from __future__ import annotations

import calendar
import math
import re
from datetime import date, datetime, time as dtime, timedelta, timezone
from .localization import live_i18n, tr


MONTHS = [tr("dates.january"), tr("dates.february"), tr("dates.march"), tr("dates.april"), tr("dates.may"), tr("dates.june"), tr("dates.july"), tr("dates.august"),
          tr("dates.september"), tr("dates.october"), tr("dates.november"), tr("dates.december")]


MONTHS_G = [tr("dates.january_genitive"), tr("dates.february_genitive"), tr("dates.march_genitive"), tr("dates.april_genitive"), tr("dates.may_genitive"), tr("dates.june_genitive"), tr("dates.july_genitive"), tr("dates.august_genitive"),
            tr("dates.september_genitive"), tr("dates.october_genitive"), tr("dates.november_genitive"), tr("dates.december_genitive")]


WD_SHORT = [tr("dates.mo"), tr("dates.tu"), tr("dates.we"), tr("dates.th"), tr("dates.fr"), tr("dates.sa"), tr("dates.su")]


WD_LONG = [tr("dates.monday"), tr("dates.tuesday"), tr("dates.wednesday"), tr("dates.thursday"), tr("dates.friday"), tr("dates.saturday"), tr("dates.sunday")]


REPEATS = [("none", tr("dates.do_not_repeat")), ("daily", tr("dates.every_day")), ("weekly", tr("dates.every_week")),
           ("monthly", tr("dates.every_month")), ("yearly", tr("dates.every_year"))]


SYN = 29.530588853


NEW_MOON_REF = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12).astimezone(timezone.utc)


def moon_frac(dt: datetime) -> float:
    return (((dt - NEW_MOON_REF).total_seconds() / 86400.0) % SYN) / SYN


def moon_info(d: date) -> dict:
    f = moon_frac(moon_noon(d))
    near = 0.5 / SYN  # фаза «в этот день» — ±12 часов от полудня
    if f < near or f > 1 - near:
        name = tr("dates.new_moon")
    elif abs(f - 0.25) < near:
        name = tr("dates.first_quarter")
    elif abs(f - 0.5) < near:
        name = tr("dates.full_moon")
    elif abs(f - 0.75) < near:
        name = tr("dates.last_quarter")
    elif f < 0.25:
        name = tr("dates.waxing_crescent")
    elif f < 0.5:
        name = tr("dates.waxing_gibbous")
    elif f < 0.75:
        name = tr("dates.waning_gibbous")
    else:
        name = tr("dates.waning_crescent")
    major = name in (tr("dates.new_moon"), tr("dates.first_quarter"), tr("dates.full_moon"), tr("dates.last_quarter"))
    return {"f": f, "name": name, "major": major,
            "illum": (1 - math.cos(2 * math.pi * f)) / 2, "age": f * SYN}


def next_phase(d: date, target: float) -> date:
    """Ближайшая дата фазы (target: 0 новолуние, .25, .5 полнолуние, .75) — средняя, ±полдня."""
    f = moon_frac(moon_noon(d))
    if abs(((f - target + 0.5) % 1.0) - 0.5) < 0.5 / SYN:
        return d
    return (moon_noon(d) + timedelta(days=((target - f) % 1.0) * SYN)).astimezone().date()


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def occurs_on(rem: dict, d: date) -> bool:
    s = date.fromisoformat(rem["date"])
    if d < s or d.isoformat() in rem.get("skip", []):
        return False
    if rem.get("until") and d > date.fromisoformat(rem["until"]):
        return False
    rep, n = rem.get("repeat", "none"), max(1, int(rem.get("every", 1)))
    if rep == "none":
        return d == s
    if rep == "daily":
        return (d - s).days % n == 0
    if rep == "weekly":
        wd = rem.get("wdays") or [s.weekday()]
        if d.weekday() not in wd:
            return False
        w0 = s - timedelta(days=s.weekday())
        return ((d - w0).days // 7) % n == 0
    if rep == "monthly":
        if ((d.year - s.year) * 12 + d.month - s.month) % n:
            return False
        return d.day == min(s.day, calendar.monthrange(d.year, d.month)[1])
    if rep == "yearly":
        if (d.year - s.year) % n or d.month != s.month:
            return False
        return d.day == min(s.day, calendar.monthrange(d.year, d.month)[1])
    return False


def occ_dt(rem: dict, d: date, allday_t: dtime) -> datetime:
    t = allday_t if rem.get("all_day") else dtime.fromisoformat(rem.get("time", "09:00"))
    return datetime.combine(d, t)


def parse_time(text: str, fallback: str = "09:00") -> str:
    m = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?", text.strip().replace(".", ":").replace(" ", ""))
    if not m:
        return fallback
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else fallback


def sort_key(rem: dict):
    return (0, "") if rem.get("all_day") else (1, rem.get("time", ""))


def short_date(d: date) -> str:
    return live_i18n.format_text('{0} {1}', d.day, MONTHS_G[d.month - 1][:3])
