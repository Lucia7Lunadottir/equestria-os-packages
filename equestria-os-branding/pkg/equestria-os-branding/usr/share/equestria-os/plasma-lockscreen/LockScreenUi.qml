/*
 *   SPDX-FileCopyrightText: 2014 Aleix Pol Gonzalez <aleixpol@blue-systems.com>
 *   SPDX-License-Identifier: GPL-2.0-or-later
 */

import QtQml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Qt5Compat.GraphicalEffects

import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.workspace.components as PW
import org.kde.plasma.private.keyboardindicator as KeyboardIndicator
import org.kde.kirigami as Kirigami
import org.kde.kscreenlocker as ScreenLocker

import org.kde.plasma.private.sessions
import org.kde.breeze.components

Item {
    id: lockScreenUi

    readonly property bool softwareRendering: GraphicsInfo.api === GraphicsInfo.Software

    function handleMessage(msg) {
        if (!root.notification) {
            root.notification += msg;
        } else if (root.notification.includes(msg)) {
            root.notificationRepeated();
        } else {
            root.notification += "\n" + msg
        }
    }

    // Изоляция темы: Белый текст по умолчанию
    Kirigami.Theme.inherit: false
    Kirigami.Theme.colorSet: Kirigami.Theme.Complementary
    Kirigami.Theme.textColor: "#ffffff"

    Connections {
        target: authenticator
        function onFailed(kind) {
            if (kind != 0) return;
            const msg = i18ndc("plasma_shell_org.kde.plasma.desktop", "@info:status", "Unlocking failed");
            lockScreenUi.handleMessage(msg);
            graceLockTimer.restart();
            notificationRemoveTimer.restart();
            rejectPasswordAnimation.start();
        }

        function onSucceeded() {
            if (authenticator.hadPrompt) {
                Qt.quit();
            } else {
                mainStack.replace(null, Qt.resolvedUrl("NoPasswordUnlock.qml"),
                                  { userListModel: users },
                                  StackView.Immediate);
                mainStack.forceActiveFocus();
            }
        }
        function onInfoMessageChanged() { lockScreenUi.handleMessage(authenticator.infoMessage); }
        function onErrorMessageChanged() { lockScreenUi.handleMessage(authenticator.errorMessage); }
        function onPromptChanged(msg) { lockScreenUi.handleMessage(authenticator.prompt); }
        function onPromptForSecretChanged(msg) {
            mainBlock.showPassword = false;
            mainBlock.mainPasswordBox.forceActiveFocus();
        }
    }

    SessionManagement { id: sessionManagement }
    KeyboardIndicator.KeyState { id: capsLockState; key: Qt.Key_CapsLock }

    Connections {
        target: sessionManagement
        function onAboutToSuspend() { root.clearPassword(); }
    }

    RejectPasswordAnimation { id: rejectPasswordAnimation; target: mainBlock }

    MouseArea {
        id: lockScreenRoot
        property bool uiVisible: false
        property bool seenPositionChange: false
        property bool blockUI: containsMouse && (mainStack.depth > 1 || mainBlock.mainPasswordBox.text.length > 0 || inputPanel.keyboardActive)

        anchors.fill: parent
        hoverEnabled: true
        cursorShape: uiVisible ? Qt.ArrowCursor : Qt.BlankCursor
        onPressed: uiVisible = true;
        onPositionChanged: {
            uiVisible = seenPositionChange;
            seenPositionChange = true;
        }
        onUiVisibleChanged: {
            if (uiVisible) Window.window.requestActivate();
            if (blockUI) fadeoutTimer.running = false;
            else if (uiVisible) fadeoutTimer.restart();
            authenticator.startAuthenticating();
        }
        onBlockUIChanged: {
            if (blockUI) { fadeoutTimer.running = false; uiVisible = true; }
            else fadeoutTimer.restart();
        }
        onExited: uiVisible = false;
        Keys.onEscapePressed: {
            if (uiVisible) {
                uiVisible = false;
                if (inputPanel.keyboardActive) inputPanel.showHide();
                root.clearPassword();
            }
        }
        Keys.onPressed: event => { uiVisible = true; event.accepted = false; }

        Timer { id: fadeoutTimer; interval: 10000; onTriggered: { if (!lockScreenRoot.blockUI) { mainBlock.mainPasswordBox.showPassword = false; lockScreenRoot.uiVisible = false; } } }
        Timer { id: notificationRemoveTimer; interval: 3000; onTriggered: root.notification = "" }
        Timer { id: graceLockTimer; interval: 3000; onTriggered: { root.clearPassword(); authenticator.startAuthenticating(); } }

        PropertyAnimation { id: launchAnimation; target: lockScreenRoot; property: "opacity"; from: 0; to: 1; duration: Kirigami.Units.veryLongDuration * 2 }
        Component.onCompleted: launchAnimation.start();

        WallpaperFader {
            id: wallpaperFader
            anchors.fill: parent
            source: wallpaper
            mainStack: mainStack
            footer: footer
            clock: clock
            alwaysShowClock: config.alwaysShowClock && !config.hideClockWhenIdle

            // ИСПРАВЛЕНИЕ: Привязываем state к uiVisible, чтобы mainStack и footer
            // корректно исчезали при неактивности, оставляя только часы.
            state: lockScreenRoot.uiVisible ? "on" : "off"

            // ЗАТЕМНЕНИЕ: Чем активнее UI, тем темнее фон
            Rectangle {
                anchors.fill: parent
                color: "black"
                opacity: lockScreenRoot.uiVisible ? 0.75 : 0.25
                z: parent.z + 1
                Behavior on opacity { NumberAnimation { duration: Kirigami.Units.longDuration } }
            }
        }

        // КОРРЕКТНЫЕ ЧАСЫ (вынесены отдельно для видимости)
        Item {
            id: clockContainer
            anchors.fill: parent
            visible: config.alwaysShowClock

            Clock {
                id: clock
                anchors.horizontalCenter: parent.horizontalCenter
                y: parent.height * 0.15 // Позиция сверху

                // Эффекты для текста (обводка и тень)
                layer.enabled: true
                layer.effect: DropShadow {
                    transparentBorder: true
                    radius: 12
                    samples: 24
                    color: "black"
                    opacity: 1
                }

                // Принудительная передача цвета в Label внутри Clock
                Kirigami.Theme.textColor: "#ffffff"
            }
        }

        ListModel {
            id: users
            Component.onCompleted: {
                users.append({
                    name: kscreenlocker_userName,
                    realName: kscreenlocker_userName,
                    icon: kscreenlocker_userImage !== ""
                    ? "file://" + kscreenlocker_userImage.split("/").map(encodeURIComponent).join("/")
                    : "",
                })
            }
        }

        StackView {
            id: mainStack
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: lockScreenRoot.height * 0.5
            focus: true
            visible: opacity > 0

            initialItem: MainBlock {
                id: mainBlock
                lockScreenUiVisible: lockScreenRoot.uiVisible
                showUserList: true
                enabled: !graceLockTimer.running
                userListModel: users

                Kirigami.Theme.textColor: "#ffffff"

                onPasswordResult: password => { authenticator.respond(password) }

                actionItems: [
                    ActionButton {
                        text: i18ndc("plasma_shell_org.kde.plasma.desktop", "@action:button", "Slee&p")
                        icon.name: "system-suspend"
                        onClicked: root.suspendToRam()
                        visible: root.suspendToRamSupported
                    },
                    ActionButton {
                        text: i18ndc("plasma_shell_org.kde.plasma.desktop", "@action:button", "&Hibernate")
                        icon.name: "system-suspend-hibernate"
                        onClicked: root.suspendToDisk()
                        visible: root.suspendToDiskSupported
                    },
                    ActionButton {
                        text: i18ndc("plasma_shell_org.kde.plasma.desktop", "@action:button", "Switch &User")
                        icon.name: "system-switch-user"
                        onClicked: { sessionManagement.switchUser(); }
                        visible: sessionManagement.canSwitchUser
                    }
                ]

                Loader {
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    Layout.fillWidth: true
                    Layout.preferredHeight: item ? item.implicitHeight : 0
                    active: config.showMediaControls
                    source: "MediaControls.qml"
                }
            }
        }

        // ТЕНЬ ДЛЯ ПОЛЯ ВВОДА
        DropShadow {
            anchors.fill: mainStack
            source: mainStack
            radius: 10
            samples: 20
            color: "black"
            visible: mainStack.visible && !lockScreenUi.softwareRendering
            opacity: mainStack.opacity
        }

        VirtualKeyboardLoader {
            id: inputPanel
            z: 10
            screenRoot: lockScreenRoot
            mainStack: mainStack
            mainBlock: mainBlock
            passwordField: mainBlock.mainPasswordBox
        }

        RowLayout {
            id: footer
            anchors {
                bottom: parent.bottom
                left: parent.left
                right: parent.right
                margins: Kirigami.Units.gridUnit
            }
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.ToolButton {
                id: virtualKeyboardButton
                icon.name: inputPanel.keyboardActive ? "input-keyboard-virtual-on" : "input-keyboard-virtual-off"
                onClicked: {
                    mainBlock.mainPasswordBox.forceActiveFocus();
                    inputPanel.showHide()
                }
                visible: inputPanel.status === Loader.Ready
            }

            PlasmaComponents3.ToolButton {
                id: keyboardButton
                icon.name: "input-keyboard"
                PW.KeyboardLayoutSwitcher { id: keyboardLayoutSwitcher; anchors.fill: parent; acceptedButtons: Qt.NoButton }
                text: keyboardLayoutSwitcher.layoutNames.shortName
                onClicked: keyboardLayoutSwitcher.keyboardLayout.switchToNextLayout()
                visible: keyboardLayoutSwitcher.hasMultipleKeyboardLayouts
            }

            Item { Layout.fillWidth: true }
            Battery {}
        }
    }
}
