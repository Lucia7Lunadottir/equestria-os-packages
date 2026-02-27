import QtQuick 2.15
import org.kde.plasma.core 2.0 as PlasmaCore
Item {
    id: root
    anchors.fill: parent
    Image {
        source: "images/background.png"
        anchors.fill: parent
        fillMode: Image.PreserveAspectCrop
    }
    Image {
        source: "images/logo.png"
        anchors.centerIn: parent
        width: 700
        height: 700
        fillMode: Image.PreserveAspectFit
    }
}
