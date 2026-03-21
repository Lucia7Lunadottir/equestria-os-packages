#!/bin/bash
# Saves the current KDE Plasma 6 panel layout to a backup file.
# Backup location: ~/.local/share/EquestriaOS/PanelBackup/

BACKUP_DIR="$HOME/.local/share/EquestriaOS/PanelBackup"
CONFIG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"

if [ ! -f "$CONFIG" ]; then
    echo "Error: config file not found: $CONFIG"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
DATED="$BACKUP_DIR/panel_$TIMESTAMP.bak"
LATEST="$BACKUP_DIR/latest.bak"

cp "$CONFIG" "$DATED"
cp "$CONFIG" "$LATEST"

echo "Panel layout saved:"
echo "  $DATED"
echo "  $LATEST  ← (used by restore_panel.sh)"
