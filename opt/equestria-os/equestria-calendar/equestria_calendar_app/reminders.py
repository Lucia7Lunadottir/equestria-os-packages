"""calendar: reminders."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from .dates import occ_dt, occurs_on, sort_key


class ReminderBook:
    """Напоминания без интерфейса: что в какой день, выполнено ли, пропуски,
    «Отложить», какие напоминания пора показать и когда проверять снова.
    Окно только показывает всплывающие окна и играет звук (fire)."""

    def __init__(self, st: "Store", cfg: dict):
        self.st, self.cfg = st, cfg

    def allday_time(self) -> dtime:
        try:
            return dtime.fromisoformat(self.cfg["allday_time"])
        except ValueError:
            return dtime(9, 0)

    def events_on(self, d: date) -> list:
        return sorted((r for r in self.st.reminders if occurs_on(r, d)), key=sort_key)

    @staticmethod
    def is_done(rem: dict, d: date) -> bool:
        return d.isoformat() in rem.get("done", [])

    def find(self, rid: str):
        return next((r for r in self.st.reminders if r["id"] == rid), None)

    @staticmethod
    def set_done(rem: dict, d: date, on: bool) -> None:
        lst = rem.setdefault("done", [])
        iso = d.isoformat()
        if on and iso not in lst:
            lst.append(iso)
        elif not on and iso in lst:
            lst.remove(iso)

    @staticmethod
    def skip(rem: dict, d: date) -> None:
        rem.setdefault("skip", []).append(d.isoformat())

    def delete(self, rem: dict, with_snoozes: bool = True) -> None:
        self.st.reminders = [r for r in self.st.reminders if r["id"] != rem["id"]]
        if with_snoozes:
            self.st.snoozed = [s for s in self.st.snoozed if s.get("id") != rem["id"]]

    def upsert(self, old, new: dict) -> None:
        """Заменить old на new (или добавить new) и не звонить о прошедшем."""
        if old:
            self.st.reminders[self.st.reminders.index(old)] = new
        else:
            self.st.reminders.append(new)
        self.mark_past_fired(new)

    def mark_past_fired(self, rem: dict) -> None:
        """Не звонить сразу о том, что уже в прошлом (при создании/изменении)."""
        now, at = datetime.now(), self.allday_time()
        for key in [k for k in self.st.fired if k.startswith(rem["id"] + "|")]:
            del self.st.fired[key]
        for k in range(-2, 3):
            d = now.date() + timedelta(days=k)
            if occurs_on(rem, d) and occ_dt(rem, d, at) - timedelta(minutes=rem.get("advance", 0)) <= now:
                self.st.fired[f"{rem['id']}|{d.isoformat()}"] = now.isoformat(timespec="seconds")

    def snooze(self, rem: dict, d: date, mins: int) -> None:
        """mins < 0 — «До завтра» (время напоминаний «на весь день»)."""
        if mins < 0:
            at = datetime.combine(date.today() + timedelta(days=1), self.allday_time())
        else:
            at = datetime.now() + timedelta(minutes=mins)
        self.st.snoozed.append({"id": rem["id"], "date": d.isoformat(), "at": at.isoformat(timespec="seconds")})

    def due(self, now: datetime) -> tuple:
        """Что пора показать: ([(напоминание, день, момент)], нужно_сохранить).
        Сначала наступившие «Отложить», затем обычные; показанное помечается."""
        at, st = self.allday_time(), self.st
        out = []
        due = [s for s in st.snoozed if datetime.fromisoformat(s["at"]) <= now]
        if due:
            st.snoozed = [s for s in st.snoozed if s not in due]
            for s in due:
                rem = self.find(s["id"])
                if rem:
                    d = date.fromisoformat(s["date"])
                    out.append((rem, d, occ_dt(rem, d, at)))
        dirty = bool(due)
        for rem in list(st.reminders):
            if not rem.get("alert", True):
                continue
            adv = timedelta(minutes=rem.get("advance", 0))
            for k in range(-2, 3):
                d = now.date() + timedelta(days=k)
                if not occurs_on(rem, d) or self.is_done(rem, d):
                    continue
                key = f"{rem['id']}|{d.isoformat()}"
                if key in st.fired:
                    continue
                occ = occ_dt(rem, d, at)
                if occ - adv <= now and now - occ < timedelta(hours=24):
                    st.fired[key] = now.isoformat(timespec="seconds")
                    dirty = True
                    out.append((rem, d, occ))
        old = (now.date() - timedelta(days=10)).isoformat()
        for key in [k for k in st.fired if k.split("|")[-1] < old]:
            del st.fired[key]
            dirty = True
        return out, dirty

    def next_check(self, now: datetime) -> datetime:
        """Следующая проверка: граница минуты или ближайшее «Отложить»."""
        nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for snz in self.st.snoozed:
            try:
                nxt = min(nxt, max(now, datetime.fromisoformat(snz["at"])))
            except (KeyError, ValueError):
                pass
        return nxt
