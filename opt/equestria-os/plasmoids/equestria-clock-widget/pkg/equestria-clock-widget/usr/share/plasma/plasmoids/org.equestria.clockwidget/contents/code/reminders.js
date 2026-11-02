// Напоминания Equestria Calendar (~/.config/equestria-calendar/calendar.json).
// Правило повторения — то же, что occurs_on() в equestria_calendar.py,
// чтобы точки в виджете совпадали с самим календарём.
.pragma library

function iso(d) {
    function p(n) { return (n < 10 ? "0" : "") + n }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate())
}

function parseIso(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || "")
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null
}

function daysBetween(a, b) {   // b - a, в днях (без учёта перехода на летнее время)
    return Math.round((Date.UTC(b.getFullYear(), b.getMonth(), b.getDate())
                     - Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())) / 86400000)
}

function weekdayMon0(d) { return (d.getDay() + 6) % 7 }   // как Python: понедельник = 0

function daysInMonth(y, m) { return new Date(y, m + 1, 0).getDate() }

function occursOn(rem, d) {
    var s = parseIso(rem.date)
    if (!s || daysBetween(s, d) < 0)
        return false
    if ((rem.skip || []).indexOf(iso(d)) >= 0)
        return false
    var until = parseIso(rem.until)
    if (until && daysBetween(until, d) > 0)
        return false
    var rep = rem.repeat || "none"
    var n = Math.max(1, parseInt(rem.every || 1))
    if (rep === "none")
        return daysBetween(s, d) === 0
    if (rep === "daily")
        return daysBetween(s, d) % n === 0
    if (rep === "weekly") {
        var wd = (rem.wdays && rem.wdays.length) ? rem.wdays : [weekdayMon0(s)]
        if (wd.indexOf(weekdayMon0(d)) < 0)
            return false
        var w0 = new Date(s.getFullYear(), s.getMonth(), s.getDate() - weekdayMon0(s))
        return Math.floor(daysBetween(w0, d) / 7) % n === 0
    }
    if (rep === "monthly") {
        if (((d.getFullYear() - s.getFullYear()) * 12 + d.getMonth() - s.getMonth()) % n)
            return false
        return d.getDate() === Math.min(s.getDate(), daysInMonth(d.getFullYear(), d.getMonth()))
    }
    if (rep === "yearly") {
        if ((d.getFullYear() - s.getFullYear()) % n || d.getMonth() !== s.getMonth())
            return false
        return d.getDate() === Math.min(s.getDate(), daysInMonth(d.getFullYear(), d.getMonth()))
    }
    return false
}

function forDay(reminders, d) {
    var out = []
    for (var i = 0; i < reminders.length; i++)
        if (occursOn(reminders[i], d))
            out.push(reminders[i])
    out.sort(function (a, b) {
        var ka = a.all_day ? "" : (a.time || ""), kb = b.all_day ? "" : (b.time || "")
        return ka < kb ? -1 : ka > kb ? 1 : 0
    })
    return out
}

function isDone(rem, d) { return (rem.done || []).indexOf(iso(d)) >= 0 }

function parse(text) {
    try {
        var data = JSON.parse(text)
        var list = (data && data.reminders) || []
        return list.filter(function (r) { return r && r.id && r.date })
    } catch (e) {
        return []
    }
}

// ISO-номер недели
function isoWeek(d) {
    var t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
    var day = t.getUTCDay() || 7
    t.setUTCDate(t.getUTCDate() + 4 - day)
    var y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1))
    return Math.ceil(((t - y0) / 86400000 + 1) / 7)
}
