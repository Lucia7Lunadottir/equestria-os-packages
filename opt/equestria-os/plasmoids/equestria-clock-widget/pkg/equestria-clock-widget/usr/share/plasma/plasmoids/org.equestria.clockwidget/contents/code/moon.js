// Фазы луны — та же формула, что в Equestria Calendar (equestria_calendar_app/dates.py):
// средний синодический месяц от опорного новолуния, фаза «в этот день» — ±12 часов от полудня.
.pragma library

var SYN = 29.530588853                          // синодический месяц, дней
var NEW_MOON_REF = Date.UTC(2000, 0, 6, 18, 14) // опорное новолуние
var DAY_MS = 86400000
var NEAR = 0.5 / SYN

function noon(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12)
}

// доля лунного месяца 0..1: 0 — новолуние, 0.5 — полнолуние
function fraction(t) {
    var days = (t.getTime() - NEW_MOON_REF) / DAY_MS
    return (((days % SYN) + SYN) % SYN) / SYN
}

// phase — ключ фазы (название переводится в QML), major — одна из четырёх главных фаз
function info(d) {
    var f = fraction(noon(d))
    var phase
    if (f < NEAR || f > 1 - NEAR) phase = "new"
    else if (Math.abs(f - 0.25) < NEAR) phase = "firstQuarter"
    else if (Math.abs(f - 0.5) < NEAR) phase = "full"
    else if (Math.abs(f - 0.75) < NEAR) phase = "lastQuarter"
    else if (f < 0.25) phase = "waxingCrescent"
    else if (f < 0.5) phase = "waxingGibbous"
    else if (f < 0.75) phase = "waningGibbous"
    else phase = "waningCrescent"
    return {
        f: f,
        phase: phase,
        major: phase === "new" || phase === "firstQuarter" || phase === "full" || phase === "lastQuarter",
        illum: (1 - Math.cos(2 * Math.PI * f)) / 2,
        age: f * SYN
    }
}

// ближайшая дата фазы target (0 — новолуние, 0.5 — полнолуние), начиная с d
function nextPhase(d, target) {
    var n = noon(d)
    var f = fraction(n)
    if (Math.abs((((f - target + 0.5) % 1) + 1) % 1 - 0.5) < NEAR)
        return n
    var ahead = ((target - f) % 1 + 1) % 1
    return new Date(n.getTime() + ahead * SYN * DAY_MS)
}
