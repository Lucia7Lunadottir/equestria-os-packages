#!/bin/bash
# Equestria Save Point — automatic snapshot script
# Called by: pacman hook (runs as root) or flatpak wrapper (via pkexec)
# Usage: pacman-snapshot.sh [tag]
#
# Auto-detects the backend:
#   Btrfs root + btrfs-progs  →  btrfs subvolume snapshot (native CoW)
#   Otherwise                 →  restic (must be initialised)

KEEP_FILE="/var/lib/equestria-save-point/hook-config"
TAG="${1:-auto}"

# Read keep_last from config (default: 10)
KEEP=10
if [[ -f "$KEEP_FILE" ]]; then
    val=$(cat "$KEEP_FILE" 2>/dev/null)
    [[ "$val" =~ ^[0-9]+$ ]] && KEEP=$val
fi

# ── Detect root filesystem type ───────────────────────────────────────────────
_fstype=$(awk '$2=="/" {print $3}' /proc/mounts 2>/dev/null | head -1)

# ── Btrfs native path ─────────────────────────────────────────────────────────
if [[ "$_fstype" == "btrfs" ]] && command -v btrfs &>/dev/null; then
    SNAP_DIR="/.snapshots"
    mkdir -p "$SNAP_DIR"
    chmod 755 "$SNAP_DIR"

    # Create read-only snapshot
    btrfs subvolume snapshot -r / "$SNAP_DIR/$(date +%Y-%m-%d_%H-%M-%S)" \
        >/dev/null 2>&1 || exit 0

    # Prune: keep newest KEEP snapshots
    mapfile -t _snaps < <(
        ls -1d "$SNAP_DIR"/????-??-??_??-??-?? 2>/dev/null | sort
    )
    _count=${#_snaps[@]}
    _delete=$(( _count - KEEP ))
    for (( i=0; i<_delete; i++ )); do
        btrfs subvolume delete "${_snaps[$i]}" >/dev/null 2>&1 || true
    done
    exit 0
fi

# ── Restic path ───────────────────────────────────────────────────────────────
REPO="/var/lib/equestria-save-point/restic-repo"
KEY="/var/lib/equestria-save-point/repo.key"
REPO_PATH_FILE="/var/lib/equestria-save-point/repo-path"

# Allow the GUI to override the repository location
if [[ -f "$REPO_PATH_FILE" ]]; then
    _override=$(cat "$REPO_PATH_FILE" 2>/dev/null | tr -d '\n')
    [[ -n "$_override" ]] && REPO="$_override"
fi

# Exit silently if repository is not yet initialised
[[ -f "$KEY" && -d "$REPO" ]] || exit 0

restic -r "$REPO" --password-file "$KEY" \
    backup / \
    --exclude=/proc      \
    --exclude=/sys       \
    --exclude=/dev       \
    --exclude=/run       \
    --exclude=/tmp       \
    --exclude=/var/run   \
    --exclude=/var/tmp   \
    --exclude=/var/cache/pacman/pkg \
    --exclude=/root/.cache          \
    --exclude=/home                 \
    --exclude=/mnt                  \
    --exclude=/media                \
    --exclude=/lost+found           \
    --exclude="$REPO"               \
    --tag "$TAG"         \
    --compression auto   \
    --quiet 2>/dev/null

restic -r "$REPO" --password-file "$KEY" \
    forget --keep-last "$KEEP" --prune \
    --quiet 2>/dev/null

exit 0
