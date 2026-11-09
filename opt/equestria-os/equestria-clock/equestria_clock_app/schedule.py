"""clock: schedule."""
from __future__ import annotations
from .localization import live_i18n

import datetime as dt
from .localization import tr


DAYS_SHORT = [tr("schedule.mo"), tr("schedule.tu"), tr("schedule.we"), tr("schedule.th"), tr("schedule.fr"), tr("schedule.sa"), tr("schedule.su")]


WEEKDAYS = [tr("schedule.monday"), tr("schedule.tuesday"), tr("schedule.wednesday"), tr("schedule.thursday"), tr("schedule.friday"), tr("schedule.saturday"), tr("schedule.sunday")]


MONTHS = [tr("schedule.january"), tr("schedule.february"), tr("schedule.march"), tr("schedule.april"), tr("schedule.may"), tr("schedule.june"), tr("schedule.july"), tr("schedule.august"),
          tr("schedule.september"), tr("schedule.october"), tr("schedule.november"), tr("schedule.december")]


def describe_days(days) -> str:
    s = set(days)
    if not s:
        return tr("schedule.once")
    if len(s) == 7:
        return tr("schedule.every_day")
    if s == {0, 1, 2, 3, 4}:
        return tr("schedule.weekdays")
    if s == {5, 6}:
        return tr("schedule.weekends")
    return live_i18n.join_text(' ', ((DAYS_SHORT[d] for d in sorted(s))))


def next_fire(alarms, now: dt.datetime):
    best = None
    for a in alarms:
        if not a["enabled"]:
            continue
        h, m = map(int, a["time"].split(":"))
        for off in range(8):
            cand = dt.datetime.combine(now.date() + dt.timedelta(days=off), dt.time(h, m))
            if cand > now and (not a["days"] or cand.weekday() in a["days"]):
                if best is None or cand < best[1]:
                    best = (a, cand)
                break
    return best


def fmt_in(minutes: int) -> str:
    d, rem = divmod(minutes, 1440)
    h, m = divmod(rem, 60)
    parts = []
    if d:
        parts.append(tr("schedule.d", d))
    if h:
        parts.append(tr("schedule.h", h))
    if m or not parts:
        parts.append(tr("common.min", m))
    return tr("schedule.in") + live_i18n.join_text(' ', (parts))


def fmt_hms(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return live_i18n.format_text('{0}:{1:02d}:{2:02d}', h, m, s) if h else live_i18n.format_text('{0:02d}:{1:02d}', m, s)


def fmt_sw(ms: float) -> str:
    cs = int(ms // 10)
    s, cs = divmod(cs, 100)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return live_i18n.format_text('{0}:{1:02d}:{2:02d}.{3:02d}', h, m, s, cs) if h else live_i18n.format_text('{0:02d}:{1:02d}.{2:02d}', m, s, cs)
