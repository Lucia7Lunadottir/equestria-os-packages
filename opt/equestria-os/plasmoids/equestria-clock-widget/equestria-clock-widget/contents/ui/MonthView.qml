// Календарь, как у KDE, в трёх видах: дни месяца, месяцы года и годы десятилетия.
// Щелчок по заголовку — вид крупнее, щелчок по месяцу или году — обратно; стрелки листают
// текущий вид, кнопка «сегодня» возвращает к сегодняшнему дню.
// Сегодня — кружок цвета выделения, выбранный день — рамка, дни (и месяцы) с напоминаниями — точка,
// дни главных фаз луны (новолуние, четверти, полнолуние) — маленькая луна в углу.
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "../code/reminders.js" as Rem
import "../code/moon.js" as Moon

ColumnLayout {
    id: month

    property date today: new Date()
    property date shown: new Date(today.getFullYear(), today.getMonth(), 1)
    property date selected: today
    property var reminders: []
    property bool weekNumbers: false
    property bool showMoon: true
    property int view: 0                // 0 — дни месяца, 1 — месяцы года, 2 — годы десятилетия
    readonly property int decadeStart: shown.getFullYear() - shown.getFullYear() % 10

    readonly property int firstDay: Qt.locale().firstDayOfWeek          // 0 = воскресенье
    readonly property date gridStart: {
        var lead = (shown.getDay() - firstDay + 7) % 7
        return new Date(shown.getFullYear(), shown.getMonth(), 1 - lead)
    }

    signal daySelected(date day)

    function sameDay(a, b) {
        return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
    }
    // шаг стрелок: месяц, год или десятилетие — смотря какой вид открыт
    function shift(steps) {
        var months = steps * (view === 0 ? 1 : view === 1 ? 12 : 120)
        shown = new Date(shown.getFullYear(), shown.getMonth() + months, 1)
    }
    function openMonth(y, m) { shown = new Date(y, m, 1); view = 0 }
    function openYear(y) { shown = new Date(y, shown.getMonth(), 1); view = 1 }
    function goToday() {
        view = 0
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
                if (month.view === 2)
                    return month.decadeStart + " – " + (month.decadeStart + 9)
                if (month.view === 1)
                    return String(month.shown.getFullYear())
                var t = Qt.locale().standaloneMonthName(month.shown.getMonth(), Locale.LongFormat) + " " + month.shown.getFullYear()
                return t.charAt(0).toUpperCase() + t.slice(1)
            }
            font.bold: true
            enabled: month.view < 2
            onClicked: month.view++
            PlasmaComponents3.ToolTip { text: month.view === 0 ? i18n("Show months") : i18n("Show years") }
        }
        PlasmaComponents3.ToolButton {
            icon.name: "go-jump-today"
            onClicked: month.goToday()
            PlasmaComponents3.ToolTip { text: i18n("Back to today") }
        }
        PlasmaComponents3.ToolButton {
            icon.name: "go-up"
            onClicked: month.shift(-1)
            PlasmaComponents3.ToolTip {
                text: month.view === 0 ? i18n("Previous month") : month.view === 1 ? i18n("Previous year") : i18n("Previous decade")
            }
        }
        PlasmaComponents3.ToolButton {
            icon.name: "go-down"
            onClicked: month.shift(1)
            PlasmaComponents3.ToolTip {
                text: month.view === 0 ? i18n("Next month") : month.view === 1 ? i18n("Next year") : i18n("Next decade")
            }
        }
    }

    // все три вида в одном StackLayout — высота календаря не прыгает при переключении
    StackLayout {
        Layout.fillWidth: true
        currentIndex: month.view

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

        // месяцы года: 4 ряда по 3, точка — в месяце есть напоминания
        GridLayout {
            columns: 3
            rowSpacing: 2
            columnSpacing: 2
            Repeater {
                model: 12
                delegate: PeriodCell {
                    text: {
                        var t = Qt.locale().standaloneMonthName(index, Locale.LongFormat)
                        return t.charAt(0).toUpperCase() + t.slice(1)
                    }
                    current: month.today.getFullYear() === month.shown.getFullYear() && month.today.getMonth() === index
                    chosen: month.selected.getFullYear() === month.shown.getFullYear() && month.selected.getMonth() === index
                    marked: month.view === 1 && Rem.anyInMonth(month.reminders, month.shown.getFullYear(), index)
                    onClicked: month.openMonth(month.shown.getFullYear(), index)
                }
            }
        }

        // годы: десятилетие и по году с краёв (как у KDE), крайние — бледнее
        GridLayout {
            columns: 3
            rowSpacing: 2
            columnSpacing: 2
            Repeater {
                model: 12
                delegate: PeriodCell {
                    readonly property int year: month.decadeStart - 1 + index
                    text: String(year)
                    current: month.today.getFullYear() === year
                    chosen: month.selected.getFullYear() === year
                    dimmed: index === 0 || index === 11
                    onClicked: month.openYear(year)
                }
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
            readonly property var moon: month.showMoon ? Moon.info(day) : null
            hoverEnabled: true
            onClicked: { month.selected = day; month.daySelected(day) }

            Rectangle {
                id: dayCircle
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
            MoonIcon {    // главная фаза луны в этот день
                visible: cell.moon !== null && cell.moon.major
                fraction: cell.moon ? cell.moon.f : 0
                width: Math.round(Kirigami.Units.gridUnit * 0.55)
                height: width
                // в правом верхнем углу кружка дня — рядом с числом, а не у края широкой ячейки
                anchors.top: dayCircle.top
                anchors.right: dayCircle.right
                anchors.rightMargin: -width / 4
                opacity: cell.inMonth ? 1 : 0.4
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

    // ячейка месяца или года: сегодняшний — заливка, выбранный — рамка, как у дней
    component PeriodCell: MouseArea {
        id: period
        property alias text: periodLabel.text
        property bool current: false
        property bool chosen: false
        property bool marked: false
        property bool dimmed: false
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.preferredWidth: Kirigami.Units.gridUnit * 4
        Layout.preferredHeight: Kirigami.Units.gridUnit * 2
        hoverEnabled: true

        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: Kirigami.Units.cornerRadius
            color: period.current ? Kirigami.Theme.highlightColor
                   : (period.containsMouse ? Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g,
                                                    Kirigami.Theme.highlightColor.b, 0.2) : "transparent")
            border.width: period.chosen && !period.current ? 2 : 0
            border.color: Kirigami.Theme.highlightColor
        }
        PlasmaComponents3.Label {
            id: periodLabel
            anchors.centerIn: parent
            color: period.current ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
            opacity: period.dimmed ? 0.4 : 1
            font.bold: period.current
        }
        Rectangle {
            visible: period.marked
            width: 5; height: 5; radius: 2.5
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 4
            color: period.current ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.highlightColor
        }
    }
}
