import QtQuick 2.15

Item {
    id: root
    anchors.fill: parent

    Image {
        id: background
        anchors.fill: parent
        source: "images/background.png"
        fillMode: Image.PreserveAspectCrop
        smooth: true
    }

    Image {
        id: logo
        anchors.centerIn: parent
        source: "images/logo.png"
        width: 700
        height: 700
        fillMode: Image.PreserveAspectFit
        smooth: true
    }
}
