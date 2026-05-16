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

# ── Screenshot helper ─────────────────────────────────────────────────────────
# Finds the active graphical user, takes a screenshot as them, saves to their
# cache directory. Runs fully in the background; never blocks snapshot creation.
_take_screenshot() {
    local snap_ts="$1"   # YYYY-MM-DD_HH-MM-SS — must match the snapshot fs_id

    # Find the first non-root user with an active graphical session
    local _user=""
    while IFS= read -r _sess_line; do
        local _su _si _st
        _su=$(awk '{print $3}' <<< "$_sess_line")
        [[ -z "$_su" || "$_su" == "root" ]] && continue
        _si=$(awk '{print $1}' <<< "$_sess_line")
        _st=$(loginctl show-session "$_si" -p Type 2>/dev/null | cut -d= -f2)
        if [[ "$_st" == "x11" || "$_st" == "wayland" || "$_st" == "mir" ]]; then
            _user="$_su"; break
        fi
    done < <(loginctl list-sessions --no-legend 2>/dev/null)

    [[ -z "$_user" ]] && return 0

    local _uid
    _uid=$(id -u "$_user" 2>/dev/null) || return 0

    # Collect DISPLAY / WAYLAND_DISPLAY from the user's running processes
    local _display="" _wayland=""
    for _pid in $(pgrep -u "$_user" 2>/dev/null | head -40); do
        local _env
        _env=$(tr '\0' '\n' < "/proc/$_pid/environ" 2>/dev/null)
        [[ -z "$_display" ]]  && _display=$(grep  '^DISPLAY='         <<< "$_env" | head -1 | cut -d= -f2-)
        [[ -z "$_wayland" ]]  && _wayland=$(grep '^WAYLAND_DISPLAY=' <<< "$_env" | head -1 | cut -d= -f2-)
        [[ -n "$_display" && -n "$_wayland" ]] && break
    done

    [[ -z "$_display" && -z "$_wayland" ]] && return 0

    local _home _screenshots_dir
    _home=$(eval echo "~$_user")
    _screenshots_dir="$_home/.cache/equestria-os-save-point/screenshots"
    mkdir -p "$_screenshots_dir"
    chown "$_user" "$_screenshots_dir" 2>/dev/null

    # Run in background — don't block the snapshot
    (
    su -s /bin/bash "$_user" -- << SCREENSHOT_EOF
export DISPLAY="$_display"
export WAYLAND_DISPLAY="$_wayland"
export XDG_RUNTIME_DIR="/run/user/$_uid"
export HOME="$_home"

_tmp=\$(mktemp /tmp/esp-snap-XXXXXX.png)

for _tool in \
    "spectacle -b -f -n -o \"\$_tmp\"" \
    "grim \"\$_tmp\"" \
    "scrot \"\$_tmp\"" \
    "import -window root \"\$_tmp\""
do
    eval \$_tool 2>/dev/null && [[ -s "\$_tmp" ]] && break
done

if [[ -s "\$_tmp" ]]; then
    _out="$_screenshots_dir/$snap_ts.webp"
    ffmpeg -y -i "\$_tmp" -vf "scale=800:450" -codec:v libwebp -quality 82 "\$_out" 2>/dev/null || \
    convert "\$_tmp" -resize "800x450!" "\$_out" 2>/dev/null
fi
rm -f "\$_tmp"
SCREENSHOT_EOF
    ) &>/dev/null &
}

# ── Detect root filesystem type ───────────────────────────────────────────────
_fstype=$(awk '$2=="/" {print $3}' /proc/mounts 2>/dev/null | head -1)

# ── Btrfs native path ─────────────────────────────────────────────────────────
if [[ "$_fstype" == "btrfs" ]] && command -v btrfs &>/dev/null; then
    SNAP_DIR="/.snapshots"
    mkdir -p "$SNAP_DIR"
    chmod 755 "$SNAP_DIR"

    # ── Daily protected path (TAG="D") ────────────────────────────────────────
    if [[ "$TAG" == "D" ]]; then
        DAILY_DIR="$SNAP_DIR/daily"
        TODAY=$(date +%Y-%m-%d)
        SNAP_TS=$(date +%Y-%m-%d_%H-%M-%S)
        mkdir -p "$DAILY_DIR"
        chmod 755 "$DAILY_DIR"

        # Idempotent: only one snapshot per calendar day
        if ! ls -1d "$DAILY_DIR"/daily-${TODAY}_* 2>/dev/null | grep -q .; then
            _take_screenshot "$SNAP_TS"
            btrfs subvolume snapshot -r / "$DAILY_DIR/daily-$SNAP_TS" \
                >/dev/null 2>&1 || exit 0
        fi

        # Keep only the 7 most recent daily snapshots
        mapfile -t _dailys < <(
            ls -1d "$DAILY_DIR"/daily-????-??-??_??-??-?? 2>/dev/null | sort
        )
        _dcount=${#_dailys[@]}
        _ddelete=$(( _dcount - 7 ))
        for (( i=0; i<_ddelete; i++ )); do
            btrfs subvolume delete "${_dailys[$i]}" >/dev/null 2>&1 || true
        done
        exit 0
    fi

    # ── Regular snapshot path ─────────────────────────────────────────────────
    SNAP_TS=$(date +%Y-%m-%d_%H-%M-%S)
    _take_screenshot "$SNAP_TS"
    btrfs subvolume snapshot -r / "$SNAP_DIR/$SNAP_TS" \
        >/dev/null 2>&1 || exit 0

    # Prune: keep newest KEEP snapshots (daily/ subdirectory is not touched)
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

# ── Restic daily protected path (TAG="D") ────────────────────────────────────
if [[ "$TAG" == "D" ]]; then
    _today=$(date +%Y-%m-%d)
    _snap_ts=$(date +%Y-%m-%d_%H-%M-%S)

    # Idempotent: only create if no daily-protected snapshot exists for today
    _existing=$(restic -r "$REPO" --password-file "$KEY" \
        snapshots --tag daily-protected --json --quiet 2>/dev/null \
        | python3 -c "
import sys, json
try:
    snaps = json.load(sys.stdin)
    print(any(s.get('time','')[:10] == '$_today' for s in snaps))
except Exception:
    print(False)
" 2>/dev/null)

    if [[ "$_existing" != "True" ]]; then
        _take_screenshot "$_snap_ts"
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
            --tag daily-protected \
            --compression auto    \
            --quiet 2>/dev/null
    fi

    # Keep only 7 daily-protected snapshots — delete the oldest if more exist
    restic -r "$REPO" --password-file "$KEY" \
        snapshots --tag daily-protected --json --quiet 2>/dev/null \
        | python3 -c "
import sys, json, subprocess
try:
    snaps = sorted(json.load(sys.stdin), key=lambda s: s.get('time',''))
    to_del = snaps[:-7] if len(snaps) > 7 else []
    for s in to_del:
        subprocess.run(
            ['restic', '-r', '$REPO', '--password-file', '$KEY',
             'forget', s['id'], '--prune', '--quiet'],
            capture_output=True)
except Exception:
    pass
" 2>/dev/null
    exit 0
fi

# ── Restic regular snapshot path ─────────────────────────────────────────────
_snap_ts=$(date +%Y-%m-%d_%H-%M-%S)
_take_screenshot "$_snap_ts"

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

# Prune regular snapshots; always preserve daily-protected ones
restic -r "$REPO" --password-file "$KEY" \
    forget --keep-last "$KEEP" --keep-tag daily-protected --prune \
    --quiet 2>/dev/null

exit 0
