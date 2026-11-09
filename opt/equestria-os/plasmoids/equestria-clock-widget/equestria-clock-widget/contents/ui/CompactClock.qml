// Часы на панели — вёрстка как у часов KDE (plasma-workspace, DigitalClock.qml):
// размер шрифта от высоты панели, ширина по самой широкой цифре (секунды не «прыгают»),
// на тонкой панели дата встаёт рядом со временем, на вертикальной — текст по ширине.
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
    property int dateDisplay: 0             // 0 — адаптивно, 1 — рядом со временем, 2 — под временем
    property bool vertical: false           // вертикальная панель
    property bool horizontal: true          // горизонтальная панель (иначе — рабочий стол)

    readonly property string timeText: now.toLocaleTimeString(Qt.locale(), timeFormat(showSeconds))
    readonly property string dateText: showDate ? formatDate(now, dateFormat) : ""

    // как у KDE: в одну строку, если так выбрано или панель ниже двух строк мелкого шрифта
    readonly property bool oneLine: !vertical && showDate
                                    && (dateDisplay === 1
                                        || (dateDisplay === 0 && horizontal
                                            && height <= 2 * Kirigami.Theme.smallFont.pixelSize))
    readonly property bool twoLines: !vertical && !oneLine
    readonly property real maxPixelSize: 3 * Kirigami.Theme.defaultFont.pixelSize

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

    // ширина времени по самой широкой цифре шрифта — как setupLabels() у KDE
    FontMetrics {
        id: metrics
        font.family: Kirigami.Theme.defaultFont.family
        font.weight: Kirigami.Theme.defaultFont.weight
        font.pixelSize: 100
    }
    readonly property string widestDigit: {
        var best = "0", width = 0
        for (var i = 0; i <= 9; i++) {
            var w = metrics.advanceWidth(String(i))
            if (w > width) { width = w; best = String(i) }
        }
        return best
    }
    function advance(text, pixelSize) {          // ширина текста при данном размере шрифта
        return metrics.advanceWidth(text) * pixelSize / 100
    }
    readonly property string sizeText: timeText.replace(/\d/g, widestDigit)

    // размеры шрифтов: те же доли высоты панели, что у KDE (0.56 / 0.71, дата — 0.8 от времени)
    readonly property real timePixelSize: {
        if (vertical)
            return Math.min(maxPixelSize, 0.9 * width / Math.max(1, advance(sizeText, 1)))
        if (oneLine)
            return Math.min(maxPixelSize, 0.7 * height)
        return Math.max(1, Math.min(maxPixelSize, height * (showDate ? 0.56 : 0.71)))
    }
    readonly property real datePixelSize: {
        if (vertical)
            return Math.min(0.7 * timePixelSize, 1.4 * Kirigami.Theme.defaultFont.pixelSize)
        return oneLine ? timePixelSize : 0.8 * timePixelSize
    }

    readonly property real contentWidth: oneLine
        ? advance(dateText + " ", datePixelSize) + advance(sizeText, timePixelSize)
        : Math.max(advance(sizeText, timePixelSize), advance(dateText, datePixelSize))

    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
    hoverEnabled: true

    Layout.fillHeight: !vertical
    Layout.fillWidth: vertical
    Layout.minimumWidth: vertical ? -1 : Math.ceil(contentWidth) + Kirigami.Units.largeSpacing
    Layout.maximumWidth: vertical ? -1 : Layout.minimumWidth
    Layout.preferredWidth: Layout.minimumWidth
    Layout.minimumHeight: vertical ? layout.implicitHeight : -1
    Layout.maximumHeight: vertical ? Layout.minimumHeight : -1

    GridLayout {
        id: layout
        anchors.centerIn: parent
        width: compact.vertical ? compact.width : implicitWidth
        flow: compact.oneLine ? GridLayout.LeftToRight : GridLayout.TopToBottom
        rows: compact.oneLine ? 1 : 2
        columns: compact.oneLine ? 2 : 1
        rowSpacing: 0
        columnSpacing: compact.advance(" ", compact.timePixelSize)

        // в одну строку дата стоит перед временем, как у KDE
        PlasmaComponents3.Label {
            id: dateBefore
            visible: compact.oneLine
            text: compact.dateText
            font.pixelSize: compact.datePixelSize
            textFormat: Text.PlainText
        }
        PlasmaComponents3.Label {
            id: timeLabel
            Layout.alignment: Qt.AlignHCenter
            // в две строки высота метки = размер шрифта (как у KDE), иначе время и дата не влезают в панель
            Layout.preferredHeight: compact.twoLines ? compact.timePixelSize : -1
            verticalAlignment: Text.AlignVCenter
            text: compact.timeText
            font.pixelSize: compact.timePixelSize
            font.features: { "tnum": 1 }    // цифры одной ширины
            horizontalAlignment: Text.AlignHCenter
            textFormat: Text.PlainText
        }
        PlasmaComponents3.Label {
            id: dateBelow
            visible: compact.showDate && !compact.oneLine
            Layout.alignment: Qt.AlignHCenter
            Layout.maximumWidth: compact.vertical ? compact.width : -1
            Layout.preferredWidth: compact.vertical ? compact.width : -1
            Layout.preferredHeight: compact.twoLines ? compact.datePixelSize : -1
            verticalAlignment: Text.AlignVCenter
            text: compact.dateText
            font.pixelSize: compact.datePixelSize
            horizontalAlignment: Text.AlignHCenter
            // на вертикальной панели — как у KDE: шрифт уменьшается под ширину, длинное — переносится
            fontSizeMode: compact.vertical ? Text.HorizontalFit : Text.FixedSize
            minimumPixelSize: Kirigami.Theme.smallFont.pixelSize * 0.7
            wrapMode: compact.vertical ? Text.WordWrap : Text.NoWrap
            textFormat: Text.PlainText
        }
    }
}
