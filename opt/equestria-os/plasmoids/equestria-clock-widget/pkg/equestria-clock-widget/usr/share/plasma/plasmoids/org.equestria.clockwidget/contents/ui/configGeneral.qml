// Настройки: вид часов на панели, календарь, дополнительные часы, приложения.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_showSeconds: showSeconds.checked
    property alias cfg_showDate: showDate.checked
    property string cfg_dateFormat
    property alias cfg_showWeekNumbers: weekNumbers.checked
    property var cfg_timeZones: []
    property alias cfg_calendarCommand: calendarCommand.text
    property alias cfg_clockCommand: clockCommand.text

    readonly property var formats: ["short", "weekday", "iso"]

    Kirigami.FormLayout {
        QQC2.CheckBox {
            id: showSeconds
            Kirigami.FormData.label: i18n("Panel:")
            text: i18n("Show seconds")
        }
        QQC2.CheckBox {
            id: showDate
            text: i18n("Show date")
        }
        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Date format:")
            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
            enabled: showDate.checked
            readonly property date sample: new Date()
            model: [
                i18n("Short: %1", sample.toLocaleDateString(Qt.locale(), Locale.ShortFormat)),
                i18n("With weekday: %1", sample.toLocaleDateString(Qt.locale(), "ddd, d MMM")),
                i18n("ISO: %1", sample.toLocaleDateString(Qt.locale(), "yyyy-MM-dd"))
            ]
            currentIndex: Math.max(0, formats.indexOf(cfg_dateFormat))
            onActivated: (i) => cfg_dateFormat = formats[i]
        }

        Item { Kirigami.FormData.isSection: true }
        QQC2.CheckBox {
            id: weekNumbers
            Kirigami.FormData.label: i18n("Calendar:")
            text: i18n("Show week numbers")
        }

        Item { Kirigami.FormData.isSection: true }
        QQC2.TextArea {
            id: zones
            Kirigami.FormData.label: i18n("Additional clocks:")
            Layout.preferredWidth: Kirigami.Units.gridUnit * 18
            Layout.preferredHeight: Kirigami.Units.gridUnit * 5
            placeholderText: "Asia/Tokyo\nAmerica/New_York"
            text: (cfg_timeZones || []).join("\n")
            onTextChanged: cfg_timeZones = text.split("\n").map(function (s) { return s.trim() })
                                               .filter(function (s) { return s !== "" })
        }
        QQC2.Label {
            Layout.preferredWidth: Kirigami.Units.gridUnit * 18
            text: i18n("One time zone per line, for example Europe/Moscow, Asia/Tokyo, America/New_York. They appear in the calendar popup and in the tooltip.")
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        Item { Kirigami.FormData.isSection: true }
        QQC2.TextField {
            id: calendarCommand
            Kirigami.FormData.label: i18n("Calendar app:")
            Layout.preferredWidth: Kirigami.Units.gridUnit * 18
        }
        QQC2.TextField {
            id: clockCommand
            Kirigami.FormData.label: i18n("Clock app:")
            Layout.preferredWidth: Kirigami.Units.gridUnit * 18
        }
    }
}
