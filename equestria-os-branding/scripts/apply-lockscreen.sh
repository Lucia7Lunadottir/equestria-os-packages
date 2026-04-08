#!/bin/bash
# Equestria OS: применяет кастомный lockscreen поверх plasma-desktop.
# Запускается автоматически pacman-хуком после установки/обновления
# plasma-desktop или equestria-os-branding.

SOURCE="/usr/share/equestria-os/plasma-lockscreen"
TARGET="/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen"

if [ -d "$SOURCE" ] && [ -d "$TARGET" ]; then
    cp -r "$SOURCE/"* "$TARGET/"
fi
