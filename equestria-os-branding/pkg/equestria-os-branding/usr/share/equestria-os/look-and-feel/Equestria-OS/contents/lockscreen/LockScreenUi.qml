import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls 2.15 as QQC2
import Qt5Compat.GraphicalEffects
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components 3.0 as PlasmaComponents3
import org.kde.kirigami 2.20 as Kirigami
import org.kde.kscreenlocker 1.0 as ScreenLocker

Item {
    id: root

    // Изоляция от кривых системных палитр
    Kirigami.Theme.inherit: false
    Kirigami.Theme.colorSet: Kirigami.Theme.Complementary
    Kirigami.Theme.textColor: "#ffffff"

    property bool uiVisible: false

    // Затемняющий оверлей
    Rectangle {
        id: dimmingOverlay
        anchors.fill: parent
        color: "black"
        opacity: root.uiVisible ? 0.2 : 0.6
        Behavior on opacity {
            NumberAnimation { duration: 250; easing.type: Easing.InOutQuad }
        }
    }

    // Запрещаем мгновенное включение пароля и скачок яркости
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onClicked: wakeUpUi()
        onPositionChanged: wakeUpUi()
    }

    Keys.onPressed: (event) => {
        wakeUpUi()
        if (event.key === Qt.Key_Escape) {
            root.uiVisible = false
        }
    }

    function wakeUpUi() {
        if (!root.uiVisible) {
            root.uiVisible = true
            authenticator.startAuthentication()
        }
    }

    ScreenLocker.Authenticator {
        id: authenticator
    }

    Item {
        id: mainUiContainer
        anchors.fill: parent
        opacity: root.uiVisible ? 1.0 : 0.0
        visible: opacity > 0
        Behavior on opacity {
            NumberAnimation { duration: 300; easing.type: Easing.OutCubic }
        }

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 12

            // --- ЧАСЫ: БЕЛЫЙ ТЕКСТ С ЧЕРНОЙ ОБВОДКОЙ ---
            PlasmaComponents3.Label {
                id: clockLabel
                Layout.alignment: Qt.AlignHCenter
                text: Qt.formatTime(new Date(), "hh:mm")
                font.pointSize: 72
                font.weight: Font.Light

                color: "#ffffff"               // Жестко белый цвет
                style: Text.Outline            // Включаем режим обводки
                styleColor: "#000000"          // Цвет обводки (черный)
            }

            // --- ЧАСЫ: ТЕНЬ ДЛЯ ДОПОЛНИТЕЛЬНОГО КОНТРАСТА ---
            DropShadow {
                anchors.fill: clockLabel
                horizontalOffset: 0
                verticalOffset: 2
                radius: 8
                samples: 16
                color: Qt.rgba(0, 0, 0, 0.85)  // Интенсивная черная тень
                source: clockLabel
            }

            // --- ПОЛЕ ВВОДА ПАРОЛЯ ---
            PlasmaComponents3.TextField {
                id: passwordField
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 320
                placeholderText: i18n("Password...")
                echoMode: TextInput.Password

                color: "#ffffff"               // Белые символы при вводе

                onAccepted: {
                    authenticator.respond(passwordField.text)
                    passwordField.text = ""
                }
            }

            // --- ПОЛЕ ВВОДА: ТЕНЬ (ЧТОБЫ НЕ СЛИВАЛОСЬ С ФОНОМ) ---
            DropShadow {
                anchors.fill: passwordField
                horizontalOffset: 0
                verticalOffset: 2
                radius: 6
                samples: 12
                color: Qt.rgba(0, 0, 0, 0.9)
                source: passwordField
            }
        }
    }
}
