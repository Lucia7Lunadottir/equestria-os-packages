// Equestria Clock Widget — часы на панели и всплывающий календарь, как в Windows.
// Здесь связка с Plasma: время, часовые пояса, напоминания Equestria Calendar,
// запуск приложений, настройки. Внешний вид — CompactClock.qml и Popup.qml.
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import "../code/reminders.js" as Rem

PlasmoidItem {
    id: root

    property date now: new Date()
    property var reminders: []
    property bool calendarInstalled: true
    readonly property var cfg: Plasmoid.configuration
    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical

    // --- время: каждую секунду, только когда секунды видны; иначе — на границе минуты
    function tick() {
        now = new Date()
        clock.interval = (cfg.showSeconds || root.expanded) ? 1000 - now.getMilliseconds() + 5
                                                            : 60000 - now.getSeconds() * 1000 - now.getMilliseconds() + 50
        clock.restart()
    }
    Timer { id: clock; repeat: false; onTriggered: root.tick() }
    Component.onCompleted: { tick(); loadReminders() }
    onExpandedChanged: { tick(); if (root.expanded) loadReminders() }
    Connections { target: Plasmoid.configuration; function onShowSecondsChanged() { root.tick() } }

    // --- часовые пояса: смещения даёт сам Plasma (источник «time»)
    P5Support.DataSource {
        id: timeSource
        engine: "time"
        connectedSources: (cfg.timeZones || []).filter(function (z) { return z.trim() !== "" })
        interval: 60000
    }
    readonly property var zones: {
        var out = []
        var list = timeSource.connectedSources
        for (var i = 0; i < list.length; i++) {
            var d = timeSource.data[list[i]]
            if (d && d["Offset"] !== undefined)
                out.push({ city: d["Timezone City"] || list[i].split("/").pop().replace(/_/g, " "), offset: d["Offset"] })
        }
        return out
    }

    // --- напоминания Equestria Calendar (тот же файл, что у приложения)
    P5Support.DataSource {
        id: shell
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            if (source === root.readCmd) {
                var out = data["stdout"] || ""
                root.calendarInstalled = out.indexOf("@@INSTALLED@@") === 0
                root.reminders = Rem.parse(out.replace("@@INSTALLED@@", ""))
            }
            disconnectSource(source)
        }
    }
    readonly property string readCmd: "if command -v equestria-calendar >/dev/null 2>&1; then printf @@INSTALLED@@; fi; "
                                      + "cat \"${XDG_CONFIG_HOME:-$HOME/.config}/equestria-calendar/calendar.json\" 2>/dev/null"
    function loadReminders() { shell.connectSource(readCmd) }
    Timer { interval: 300000; running: true; repeat: true; onTriggered: root.loadReminders() }

    function launch(cmd) {
        if (cmd && cmd.trim() !== "") {
            shell.connectSource("setsid -f " + cmd + " >/dev/null 2>&1")
            root.expanded = false
        }
    }

    // --- подсказка: полная дата и часы других поясов
    toolTipMainText: now.toLocaleDateString(Qt.locale(), Locale.LongFormat)
    toolTipSubText: {
        var lines = []
        var today = Rem.forDay(reminders, now)
        if (today.length)
            lines.push(i18np("%1 event today", "%1 events today", today.length))
        for (var i = 0; i < zones.length; i++) {
            var t = new Date(now.getTime() + (zones[i].offset + now.getTimezoneOffset() * 60) * 1000)
            lines.push(zones[i].city + "  " + t.toLocaleTimeString(Qt.locale(), Locale.ShortFormat))
        }
        return lines.join("\n")
    }

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Open Equestria Calendar")
            icon.name: "view-calendar"
            onTriggered: root.launch(cfg.calendarCommand)
        },
        PlasmaCore.Action {
            text: i18n("Alarms, timer and stopwatch")
            icon.name: "chronometer"
            onTriggered: root.launch(cfg.clockCommand)
        },
        PlasmaCore.Action {
            text: i18n("Date and time settings")
            icon.name: "preferences-system-time"
            onTriggered: root.launch("systemsettings kcm_clock")
        }
    ]

    compactRepresentation: CompactClock {
        now: root.now
        showSeconds: cfg.showSeconds
        showDate: cfg.showDate
        dateFormat: cfg.dateFormat
        vertical: root.vertical
        onClicked: (mouse) => {
            if (mouse.button === Qt.MiddleButton)
                root.launch(cfg.clockCommand)
            else
                root.expanded = !root.expanded
        }
    }

    fullRepresentation: Popup {
        now: root.now
        reminders: root.reminders
        zones: root.zones
        weekNumbers: cfg.showWeekNumbers
        calendarInstalled: root.calendarInstalled
        onOpenCalendar: root.launch(cfg.calendarCommand)
        onOpenClock: root.launch(cfg.clockCommand)
        onOpenSettings: root.launch("systemsettings kcm_clock")
    }
}
