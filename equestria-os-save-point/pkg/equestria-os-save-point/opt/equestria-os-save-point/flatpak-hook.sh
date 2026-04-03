#!/bin/bash
# Equestria Save Point — flatpak auto-snapshot wrapper
# Installed to: /etc/profile.d/60-equestria-save-point.sh
#
# Wraps the `flatpak` command in interactive shells so that a save point is
# created in the background before any install/update/remove operation.
# Works for terminal usage; GUI clients (Discover) are not covered.

_ESP_SCRIPT="/opt/equestria-os-save-point/pacman-snapshot.sh"

if command -v flatpak &>/dev/null && [[ -x "$_ESP_SCRIPT" ]]; then
    flatpak() {
        case "${1:-}" in
            install|update|upgrade|uninstall|remove)
                # Fire snapshot in background via pkexec — doesn't block flatpak
                (pkexec "$_ESP_SCRIPT" "auto:flatpak" &>/dev/null) &
                disown $! 2>/dev/null || true
                ;;
        esac
        command flatpak "$@"
    }
fi
