"""calc: dates."""
from __future__ import annotations

import calendar
import datetime as dt
from .localization import tr


WEEKDAYS = [tr("dates.monday"), tr("dates.tuesday"), tr("dates.wednesday"), tr("dates.thursday"), tr("dates.friday"), tr("dates.saturday"), tr("dates.sunday")]


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s.strip(), "%d.%m.%Y").date()


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return dt.date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def date_diff(a: dt.date, b: dt.date):
    if a > b:
        a, b = b, a
    total = (b.year - a.year) * 12 + b.month - a.month
    if add_months(a, total) > b:
        total -= 1
    rest = (b - add_months(a, total)).days
    y, m = divmod(total, 12)
    return (b - a).days, y, m, rest
