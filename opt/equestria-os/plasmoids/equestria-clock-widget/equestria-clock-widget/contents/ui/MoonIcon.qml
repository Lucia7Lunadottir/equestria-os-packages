// Луна в нужной фазе — так же, как её рисует Equestria Calendar (moon_drawing.py):
// тёмный диск и освещённая часть: половина диска плюс/минус эллипс терминатора.
import QtQuick
import org.kde.kirigami as Kirigami

Canvas {
    id: moon

    property real fraction: 0                    // 0 — новолуние, 0.5 — полнолуние
    property color darkColor: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                                      Kirigami.Theme.textColor.b, 0.22)
    property color lightColor: "#f2ecd0"         // как MOON_LIGHT в приложении календаря

    implicitWidth: Kirigami.Units.iconSizes.small
    implicitHeight: implicitWidth

    onFractionChanged: requestPaint()
    onDarkColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        var r = Math.min(width, height) / 2
        var cx = width / 2, cy = height / 2
        ctx.fillStyle = darkColor
        ctx.beginPath()
        ctx.arc(cx, cy, r, 0, 2 * Math.PI)
        ctx.fill()

        var k = Math.cos(2 * Math.PI * fraction)  // 1 — новолуние, -1 — полнолуние
        var waxing = fraction < 0.5                // растущая освещена справа, убывающая — слева
        var gibbous = k < 0                        // больше половины освещено
        ctx.fillStyle = lightColor
        ctx.beginPath()
        // освещённый край: полуокружность сверху вниз по светлой стороне
        ctx.arc(cx, cy, r, -Math.PI / 2, Math.PI / 2, !waxing)
        // терминатор снизу вверх: полуэллипс, выгнутый в тёмную сторону (больше половины) или в светлую
        ctx.save()
        ctx.translate(cx, cy)
        ctx.scale(Math.max(Math.abs(k), 0.001), 1)
        var bulgeLeft = waxing === gibbous
        if (bulgeLeft)
            ctx.arc(0, 0, r, Math.PI / 2, 3 * Math.PI / 2, false)
        else
            ctx.arc(0, 0, r, Math.PI / 2, -Math.PI / 2, true)
        ctx.restore()
        ctx.closePath()
        ctx.fill()
    }
}
