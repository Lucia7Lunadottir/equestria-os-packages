#!/bin/bash
# Restores KDE Plasma 6 panel layout from the last save made by save_panel.sh.

BACKUP_DIR="$HOME/.local/share/EquestriaOS/PanelBackup"
LATEST="$BACKUP_DIR/latest.bak"
CONFIG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"

if [ ! -f "$LATEST" ]; then
    echo "Error: no backup found."
    echo "Run save_panel.sh first."
    exit 1
fi

echo "Restoring panel layout from:"
echo "  $LATEST"

# Stop plasmashell, restore config, restart
kquitapp6 plasmashell 2>/dev/null
sleep 1

cp "$LATEST" "$CONFIG"

nohup plasmashell &>/dev/null &
disown

echo "Done. Panel restored."
