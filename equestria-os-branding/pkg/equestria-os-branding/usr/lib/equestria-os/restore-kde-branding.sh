#!/bin/bash
# Equestria OS: восстанавливает KDE-брендинг после обновления KDE-пакетов.
# Запускается автоматически pacman-хуком после установки/обновления
# sddm, plasma-workspace, plasma-desktop, breeze или equestria-os-branding.

BRANDING_PREFIX="/usr/share/equestria-os"

# 1. SDDM тема
SDDM_SRC="$BRANDING_PREFIX/sddm/equestria-os-breeze"
SDDM_DST="/usr/share/sddm/themes/equestria-os-breeze"
if [ -d "$SDDM_SRC" ] && [ -d "/usr/share/sddm/themes" ]; then
    cp -rf "$SDDM_SRC" "$SDDM_DST"
fi

# 2. Plasma Look and Feel (сплеш-скрин)
LAF_SRC="$BRANDING_PREFIX/look-and-feel/Equestria-OS"
LAF_DST="/usr/share/plasma/look-and-feel/Equestria-OS"
if [ -d "$LAF_SRC" ]; then
    mkdir -p /usr/share/plasma/look-and-feel
    cp -rf "$LAF_SRC" "$LAF_DST"
fi

# 3. Курсоры
CURSOR_SRC="$BRANDING_PREFIX/icons/Vimix-white-cursors"
CURSOR_DST="/usr/share/icons/Vimix-white-cursors"
if [ -d "$CURSOR_SRC" ] && [ -d "/usr/share/icons" ]; then
    cp -rf "$CURSOR_SRC" "$CURSOR_DST"
fi
