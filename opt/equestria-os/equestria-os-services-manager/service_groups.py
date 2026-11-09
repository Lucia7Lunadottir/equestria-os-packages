"""Деление сервисов на группы по назначению.

Группа — правило «подходит ли сервис» + ключ перевода group.<key>. Порядок в GROUPS — порядок
на экране; сервис попадает в первую подходящую группу. Новая группа — новая запись в GROUPS,
остальной код не меняется.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceGroup:
    key: str                         # id группы и ключ перевода group.<key>
    icon: str                        # значок из темы
    patterns: tuple = ()             # маски имён юнитов (без учёта регистра)
    collapsed: bool = False          # свёрнута, пока пользователь не раскроет

    def matches(self, svc, favorites: set) -> bool:
        name = svc.name.lower()
        return any(fnmatch.fnmatchcase(name, p) for p in self.patterns)


@dataclass(frozen=True)
class FavoritesGroup(ServiceGroup):
    """Закреплённые пользователем — всегда первыми."""

    def matches(self, svc, favorites: set) -> bool:
        return svc.uid in favorites


@dataclass(frozen=True)
class OtherGroup(ServiceGroup):
    """Всё, что не подошло другим группам."""

    def matches(self, svc, favorites: set) -> bool:
        return True


GROUPS: tuple = (
    FavoritesGroup("favorites", "starred-symbolic"),
    ServiceGroup("desktop", "plasma", (
        "plasma-*", "kwin*", "kde*", "org.kde.*", "ksmserver*", "kglobalaccel*", "kactivitymanagerd*",
        "ksystemstats*", "baloo*", "drkonqi*", "xdg-desktop-portal*", "xdg-document-portal*",
        "xdg-permission-store*", "sddm*", "gdm*", "lightdm*", "display-manager*", "dconf*", "gvfs*",
        "at-spi*", "dbus-:*org.kde.*", "xdg-user-dirs*", "gnome-keyring*", "kwallet*", "kio-fuse*",
        "xsettingsd*", "tinysparql*", "glib-pacrunner*")),
    # программы, запущенные сеансом: автозапуск (app-…) и по запросу через D-Bus (dbus-:…)
    ServiceGroup("apps", "system-run", ("app-*", "dbus-:*")),
    ServiceGroup("audio", "audio-volume-high", (
        "pipewire*", "wireplumber*", "pulseaudio*", "alsa-*", "rtkit-daemon*", "filter-chain*", "jack*",
        "canberra*", "sndiod*", "fluidsynth*", "mpris-proxy*")),
    ServiceGroup("network", "network-wired", (
        "networkmanager*", "nm-*", "systemd-networkd*", "systemd-resolved*", "wpa_supplicant*", "iwd*",
        "bluetooth*", "obex*", "modemmanager*", "avahi*", "sshd*", "firewalld*", "ufw*", "nftables*",
        "iptables*", "ip6tables*", "dhcpcd*", "tailscale*", "zerotier*", "wg-quick*", "openvpn*",
        "smb*", "nmb*", "samba*", "warp-svc*", "nordvpn*", "netctl*", "ppp@*", "vpnc@*", "xl2tpd*",
        "teamd@*", "arptables*", "ebtables*", "ipset*", "krb5-*", "gssproxy*", "gssuserproxy*", "rpc-*",
        "auth-rpcgss*", "nslcd*", "winbind*", "ead*", "telnet@*", "rlogin@*", "rsh@*", "talk*")),
    ServiceGroup("devices", "battery", (
        "cups*", "saned*", "colord*", "bolt*", "upower*", "power-profiles-daemon*", "tlp*", "thermald*",
        "smartd*", "fstrim*", "udisks2*", "systemd-rfkill*", "geoclue*", "iio-sensor*", "fprintd*",
        "asusd*", "asus-*", "acpid*", "systemd-backlight*", "rog-control*", "ratbagd*", "openrgb*",
        "auto-cpufreq*", "fancontrol*", "lm_sensors*", "sensord*", "system76-power*", "tuned*", "pcscd*",
        "usb_modeswitch*", "rfkill-*", "configure-printer@*", "hplip-printer@*", "gpm*")),
    ServiceGroup("equestria", "start-here", ("pg-*", "equestria-*")),
    ServiceGroup("gpu", "video-display", (
        "nvidia*", "supergfxd*", "switcheroo-control*", "optimus*", "envycontrol*", "lact*", "corectrl*")),
    ServiceGroup("updates", "system-software-update", (
        "pacman*", "archlinux-keyring*", "reflector*", "paccache*", "flatpak*", "snapd*", "packagekit*",
        "fwupd*", "pamac*", "pkgfile*", "man-db*", "shadow*", "updatedb*", "plocate*")),
    ServiceGroup("system", "preferences-system", (
        "systemd-*", "dbus*", "polkit*", "*getty*", "user@*", "user-runtime-dir@*", "modprobe@*",
        "initrd-*", "emergency*", "rescue*", "kmod-*", "ldconfig*", "lvm2-*", "dm-event*",
        "blk-availability*", "plymouth*", "auditd*", "machine*", "grub*", "mkinitcpio*", "gpg-agent*",
        "dirmngr*", "keyboxd*", "ssh-agent*", "p11-kit*", "sys-*", "dev-*", "proc-*", "tmp.*",
        "cryptsetup*", "zram*", "swap*", "rpcbind*", "nfs*", "boot.*", "kexec*", "halt*", "poweroff*",
        "reboot*", "suspend*", "hibernate*", "sleep*", "console-*", "autovt@*", "container-getty@*",
        "quotaon*", "audit-rules*", "rc-local*", "local-fs*", "remote-fs*", "network-online*",
        "graphical*", "multi-user*", "default*", "basic*", "sockets*", "timers*", "paths*", "slices*",
        "e2scrub*", "lvmlockd*", "debug-shell*", "uuidd*", "dnsmasq*", "ntpd*", "chronyd*",
        "dracut-*", "breakpoint-*", "ostree-*", "md*", "xfs_*", "btrfs-*", "lvm-*", "dmraid*", "ldmtool*",
        "haveged*", "logrotate*", "lastlog2*", "pam_namespace*", "accounts-daemon*", "seatd*", "syslog*",
        "sudo_logsrvd*", "system-update-cleanup*", "capsule@*", "fsidd*", "cxl-*", "daxdev-*", "ndctl-*",
        "rdma-*", "srp_daemon*", "ibacm*", "iwpmd*", "healthd*", "passim*", "gcr-ssh-agent*"),
        collapsed=True),
    # серверные программы и виртуализация — обычно установлены «на всякий случай» и выключены
    ServiceGroup("servers", "network-server", (
        "virt*", "libvirt*", "mariadb*", "mysql*", "postgresql*", "redis*", "nginx*", "httpd*", "named*",
        "ftpd*", "rsyncd*", "snmp*", "git-daemon*", "glances*", "docker*", "containerd*", "podman*",
        "ollama*", "sshd-keygen*", "cockpit*"),
        collapsed=True),
    # развёрнута: у других пользователей сюда попадут их собственные программы — не прятать их
    OtherGroup("other", "applications-other"),
)


def group_of(svc, favorites: set) -> ServiceGroup:
    return next(g for g in GROUPS if g.matches(svc, favorites))


DEFAULT_FAVORITES = (
    "user:plasma-plasmashell.service", "user:pipewire.service", "user:wireplumber.service",
    "system:NetworkManager.service", "system:bluetooth.service",
)
