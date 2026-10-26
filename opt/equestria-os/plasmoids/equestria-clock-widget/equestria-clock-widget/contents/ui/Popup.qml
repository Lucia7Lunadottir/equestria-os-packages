// Всплывающая панель, как у часов Windows: крупное время с секундами и полная дата,
// календарь месяца, события выбранного дня из Equestria Calendar, часы других
// часовых поясов и кнопки «Календарь», «Будильник и таймер», «Настройки времени».
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "../code/reminders.js" as Rem

ColumnLayout {
    id: popup

    property date now: new Date()
    property var reminders: []
    property var zones: []              // [{city, offset}] — смещение от UTC в секундах
    property bool weekNumbers: false
    property bool calendarInstalled: true

    property date selected: now

    signal openCalendar()
    signal openClock()
    signal openSettings()

    function timeFormat() {
        var f = Qt.locale().timeFormat(Locale.ShortFormat)
        return f.indexOf("ss") < 0 ? f.replace("mm", "mm:ss") : f
    }
    function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1) }
    function zoneTime(offset) {        // время в другом поясе по смещению от UTC
        var local = -now.getTimezoneOffset() * 60
        return new Date(now.getTime() + (offset - local) * 1000)
    }
    function zoneNote(offset) {
        var local = -now.getTimezoneOffset() * 60
        var diffH = (offset - local) / 3600
        var t = zoneTime(offset)
        var dayShift = Math.round((Date.UTC(t.getFullYear(), t.getMonth(), t.getDate())
                                 - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000)
        var parts = []
        if (dayShift > 0) parts.push(i18n("tomorrow"))
        else if (dayShift < 0) parts.push(i18n("yesterday"))
        if (diffH !== 0) {
            var h = Math.abs(diffH)
            var hs = (h % 1 === 0) ? h.toString() : h.toFixed(1)
            parts.push((diffH > 0 ? "+" : "−") + i18nc("hours offset, e.g. +3 h", "%1 h", hs))
        } else {
            parts.push(i18n("same time"))
        }
        return parts.join(", ")
    }

    readonly property var dayEvents: Rem.forDay(reminders, selected)

    spacing: Kirigami.Units.smallSpacing
    Layout.minimumWidth: Kirigami.Units.gridUnit * 18
    Layout.preferredWidth: Kirigami.Units.gridUnit * 20

    // --- время и дата
    PlasmaComponents3.Label {
        Layout.fillWidth: true
        text: popup.now.toLocaleTimeString(Qt.locale(), popup.timeFormat())
        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 2.8
        font.weight: Font.Light
        font.features: { "tnum": 1 }
    }
    PlasmaComponents3.Label {
        Layout.fillWidth: true
        // toLocale…String — названия дней и месяцев на языке пользователя (Qt.formatDate с шаблоном берёт английские)
        text: popup.capitalize(popup.now.toLocaleDateString(Qt.locale(), Locale.LongFormat))
        color: Kirigami.Theme.highlightColor
        elide: Text.ElideRight
    }

    Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }

    // --- календарь
    MonthView {
        id: monthView
        Layout.fillWidth: true
        today: popup.now
        reminders: popup.reminders
        weekNumbers: popup.weekNumbers
        onDaySelected: (day) => popup.selected = day
    }

    Kirigami.Separator { Layout.fillWidth: true }

    // --- события выбранного дня
    PlasmaComponents3.Label {
        Layout.fillWidth: true
        text: monthView.sameDay(popup.selected, popup.now) ? i18n("Today")
              : popup.capitalize(popup.selected.toLocaleDateString(Qt.locale(), "dddd, d MMMM"))
        font.bold: true
    }
    Repeater {
        model: popup.dayEvents
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            readonly property bool done: Rem.isDone(modelData, popup.selected)
            Rectangle {
                Layout.preferredWidth: 4
                Layout.preferredHeight: Kirigami.Units.gridUnit
                radius: 2
                color: modelData.color || Kirigami.Theme.highlightColor
            }
            PlasmaComponents3.Label {
                text: modelData.all_day ? i18n("All day") : (modelData.time || "")
                opacity: 0.7
                Layout.preferredWidth: Kirigami.Units.gridUnit * 4
                font.features: { "tnum": 1 }
            }
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                text: modelData.title
                elide: Text.ElideRight
                font.strikeout: parent.done
                opacity: parent.done ? 0.5 : 1
            }
        }
    }
    PlasmaComponents3.Label {
        visible: popup.dayEvents.length === 0
        Layout.fillWidth: true
        text: popup.calendarInstalled ? i18n("No events") : i18n("Install Equestria Calendar to see events here")
        opacity: 0.6
        wrapMode: Text.WordWrap
    }

    // --- другие часовые пояса
    Kirigami.Separator { Layout.fillWidth: true; visible: popup.zones.length > 0 }
    Repeater {
        model: popup.zones
        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                text: modelData.city
                elide: Text.ElideRight
            }
            PlasmaComponents3.Label {
                text: popup.zoneNote(modelData.offset)
                opacity: 0.6
                font: Kirigami.Theme.smallFont
            }
            PlasmaComponents3.Label {
                text: popup.zoneTime(modelData.offset).toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
                font.features: { "tnum": 1 }
                font.bold: true
            }
        }
    }

    Item { Layout.fillHeight: true }   // свободное место — над кнопками

    // --- кнопки
    Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }
    RowLayout {
        Layout.fillWidth: true
        PlasmaComponents3.ToolButton {
            icon.name: "view-calendar"
            text: i18n("Calendar")
            onClicked: popup.openCalendar()
        }
        PlasmaComponents3.ToolButton {
            icon.name: "chronometer"
            text: i18n("Alarms and timers")
            onClicked: popup.openClock()
        }
        Item { Layout.fillWidth: true }
        PlasmaComponents3.ToolButton {
            icon.name: "preferences-system-time"
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Date and time settings")
            onClicked: popup.openSettings()
            PlasmaComponents3.ToolTip { text: parent.text }
        }
    }
}
