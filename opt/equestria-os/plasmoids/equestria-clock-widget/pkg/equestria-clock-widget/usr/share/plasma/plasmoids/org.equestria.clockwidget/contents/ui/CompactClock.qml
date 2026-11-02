// Часы на панели: время сверху, дата снизу — как в панели задач Windows.
// Только внешний вид: данные и щелчки приходят из main.qml.
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

MouseArea {
    id: compact

    property date now: new Date()
    property bool showSeconds: false
    property bool showDate: true
    property string dateFormat: "short"     // short | weekday | iso
    property bool vertical: false           // вертикальная панель

    readonly property string timeText: now.toLocaleTimeString(Qt.locale(), timeFormat(showSeconds))
    readonly property string dateText: formatDate(now, dateFormat)

    function timeFormat(seconds) {
        var f = Qt.locale().timeFormat(Locale.ShortFormat)
        return seconds && f.indexOf("ss") < 0 ? f.replace("mm", "mm:ss") : f
    }

    function formatDate(d, kind) {
        if (kind === "iso")
            return d.toLocaleDateString(Qt.locale(), "yyyy-MM-dd")
        if (kind === "weekday")
            return d.toLocaleDateString(Qt.locale(), "ddd, d MMM")
        return d.toLocaleDateString(Qt.locale(), Locale.ShortFormat)
    }

    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
    hoverEnabled: true

    // ширина по тексту — время с секундами не «прыгает»: берём ширину по самым широким цифрам
    TextMetrics { id: timeMetrics; font: timeLabel.font; text: compact.timeText.replace(/\d/g, "0") }
    TextMetrics { id: dateMetrics; font: dateLabel.font; text: compact.dateText }

    Layout.minimumWidth: vertical ? -1 : Math.ceil(Math.max(timeMetrics.width, showDate ? dateMetrics.width : 0)) + Kirigami.Units.largeSpacing
    Layout.preferredWidth: Layout.minimumWidth
    Layout.minimumHeight: vertical ? column.implicitHeight : -1

    Rectangle {   // подсветка при наведении, как у кнопок панели
        anchors.fill: parent
        radius: Kirigami.Units.cornerRadius
        color: Kirigami.Theme.highlightColor
        opacity: compact.containsMouse ? 0.15 : 0
        Behavior on opacity { NumberAnimation { duration: Kirigami.Units.shortDuration } }
    }

    ColumnLayout {
        id: column
        anchors.centerIn: parent
        spacing: 0

        PlasmaComponents3.Label {
            id: timeLabel
            Layout.alignment: Qt.AlignHCenter
            text: compact.timeText
            font.pixelSize: compact.vertical ? Kirigami.Theme.defaultFont.pixelSize
                          : Math.max(9, Math.round(compact.height * (compact.showDate ? 0.36 : 0.5)))
            font.features: { "tnum": 1 }    // цифры одной ширины
        }
        PlasmaComponents3.Label {
            id: dateLabel
            visible: compact.showDate
            Layout.alignment: Qt.AlignHCenter
            text: compact.dateText
            opacity: 0.85
            font.pixelSize: compact.vertical ? Kirigami.Theme.smallFont.pixelSize
                          : Math.max(8, Math.round(compact.height * 0.28))
        }
    }
}
