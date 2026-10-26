// Календарь месяца: стрелки, щелчок по названию месяца — вернуться к сегодняшнему дню,
// сегодня — кружок цвета выделения, выбранный день — рамка, дни с напоминаниями — точка.
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "../code/reminders.js" as Rem

ColumnLayout {
    id: month

    property date today: new Date()
    property date shown: new Date(today.getFullYear(), today.getMonth(), 1)
    property date selected: today
    property var reminders: []
    property bool weekNumbers: false

    readonly property int firstDay: Qt.locale().firstDayOfWeek          // 0 = воскресенье
    readonly property date gridStart: {
        var lead = (shown.getDay() - firstDay + 7) % 7
        return new Date(shown.getFullYear(), shown.getMonth(), 1 - lead)
    }

    signal daySelected(date day)

    function sameDay(a, b) {
        return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
    }
    function shift(months) { shown = new Date(shown.getFullYear(), shown.getMonth() + months, 1) }
    function goToday() {
        shown = new Date(today.getFullYear(), today.getMonth(), 1)
        selected = today
        daySelected(today)
    }

    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        Layout.fillWidth: true
        PlasmaComponents3.ToolButton {
            id: monthTitle
            Layout.fillWidth: true
            text: {
                var t = Qt.locale().standaloneMonthName(month.shown.getMonth(), Locale.LongFormat) + " " + month.shown.getFullYear()
                return t.charAt(0).toUpperCase() + t.slice(1)
            }
            font.bold: true
            onClicked: month.goToday()
            PlasmaComponents3.ToolTip { text: i18n("Back to today") }
        }
        PlasmaComponents3.ToolButton {
            icon.name: "go-up"
            onClicked: month.shift(-1)
            PlasmaComponents3.ToolTip { text: i18n("Previous month") }
        }
        PlasmaComponents3.ToolButton {
            icon.name: "go-down"
            onClicked: month.shift(1)
            PlasmaComponents3.ToolTip { text: i18n("Next month") }
        }
    }

    GridLayout {
        id: grid
        Layout.fillWidth: true
        columns: month.weekNumbers ? 8 : 7
        rowSpacing: 2
        columnSpacing: 2

        // шапка: дни недели в порядке, принятом в стране пользователя
        Item { visible: month.weekNumbers; Layout.preferredWidth: Kirigami.Units.gridUnit * 1.4; Layout.preferredHeight: 1 }
        Repeater {
            model: 7
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: Qt.locale().standaloneDayName((month.firstDay + index) % 7, Locale.ShortFormat)
                opacity: 0.6
                font: Kirigami.Theme.smallFont
            }
        }

        Repeater {
            model: 6 * (month.weekNumbers ? 8 : 7)
            delegate: Loader {
                readonly property int row: Math.floor(index / grid.columns)
                readonly property int col: index % grid.columns
                readonly property bool isWeek: month.weekNumbers && col === 0
                readonly property int dayIndex: row * 7 + (month.weekNumbers ? col - 1 : col)
                Layout.fillWidth: true
                Layout.preferredWidth: isWeek ? Kirigami.Units.gridUnit * 1.4 : Kirigami.Units.gridUnit * 2
                Layout.preferredHeight: Kirigami.Units.gridUnit * 2
                sourceComponent: isWeek ? weekCell : dayCell
                property date day: new Date(month.gridStart.getFullYear(), month.gridStart.getMonth(),
                                            month.gridStart.getDate() + dayIndex)
            }
        }
    }

    Component {
        id: weekCell
        PlasmaComponents3.Label {
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: Rem.isoWeek(parent.day)
            opacity: 0.45
            font: Kirigami.Theme.smallFont
        }
    }

    Component {
        id: dayCell
        MouseArea {
            id: cell
            readonly property date day: parent.day
            readonly property bool inMonth: day.getMonth() === month.shown.getMonth()
            readonly property bool isToday: month.sameDay(day, month.today)
            readonly property bool isSelected: month.sameDay(day, month.selected)
            readonly property var events: Rem.forDay(month.reminders, day)
            hoverEnabled: true
            onClicked: { month.selected = day; month.daySelected(day) }

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(parent.width, parent.height) - 2
                height: width
                radius: width / 2
                color: cell.isToday ? Kirigami.Theme.highlightColor
                       : (cell.containsMouse ? Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g,
                                                        Kirigami.Theme.highlightColor.b, 0.2) : "transparent")
                border.width: cell.isSelected && !cell.isToday ? 2 : 0
                border.color: Kirigami.Theme.highlightColor
            }
            PlasmaComponents3.Label {
                anchors.centerIn: parent
                text: cell.day.getDate()
                color: cell.isToday ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                opacity: cell.inMonth ? 1 : 0.4
                font.bold: cell.isToday
            }
            Rectangle {   // точка: в этот день есть напоминания (цвет первого)
                visible: cell.events.length > 0
                width: 5; height: 5; radius: 2.5
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 3
                color: cell.isToday ? Kirigami.Theme.highlightedTextColor
                       : (cell.events.length ? (cell.events[0].color || Kirigami.Theme.highlightColor) : "transparent")
            }
        }
    }
}
