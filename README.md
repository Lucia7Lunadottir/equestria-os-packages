# 🦄 Equestria OS

### The Ultimate My Little Pony Linux Distribution

**Equestria OS** is an Arch Linux-based desktop distribution built around a highly customized KDE Plasma 6, with its own graphical installer (Calamares), its own branding, and a full suite of custom GUI tools that make everyday things — GPU drivers, Windows games, disks, backups — just work through a dialog instead of a terminal command.

You don't need to be an MLP fan to use it: under the theming is a genuinely fast, no-bloat Arch install with full AUR compatibility — the pony branding is the personality, not the point.

This repository, **`equestria-os-packages`**, is the source code and package repository behind it: every native tool, driver helper, and theming package that makes Equestria OS what it is, built for `x86_64` and installable both as part of the full OS and as an add-on repo on plain Arch/EndeavourOS.

### Contents

* [Why Equestria OS?](#-why-equestria-os)
* [Get Equestria OS](#-get-equestria-os)
* [GPU & driver handling](#-gpu--driver-handling)
* [What's inside this repo](#-whats-inside-this-repo)
* [Community](#-community)
* [Contributing](#-contributing)
* [A Solo Passion Project](#-a-solo-passion-project)
* [Trademark & Legal](#-trademark--legal)

## 🌈 Why Equestria OS?

Arch Linux is famous for being powerful and famously unfriendly to newcomers — everything is a config file, a wiki page, and a terminal command away. Equestria OS keeps the Arch base (rolling release, huge package ecosystem, AUR-compatible) but wraps the parts that usually mean trial-and-error into an actual GUI:

* **No terminal required for day-to-day maintenance.** Mounting a drive, resizing a partition, switching GPU drivers, managing swap, rolling back a bad update, enabling a systemd service — all of it is a dialog in **Equestria OS Settings**, not a manual `pacman`/`mount`/`systemctl` incantation.
* **Driver detection that just works.** The installer and `pg-gpu-sync` figure out your NVIDIA generation and wire up the right driver branch automatically — see [GPU & driver handling](#-gpu--driver-handling) below.
* **A real daily driver, not a tech demo.** This is the exact system the maintainer uses every day — bugs that would only show up in daily use (driver quirks, brightness controls, Optimus laptops) get found and fixed because they're lived with, not just tested once.
* **Themed, not just reskinned.** My Little Pony branding runs through the boot screen, login screen, GRUB, wallpapers, and a per-character KDE color theme switcher — cohesive rather than a wallpaper slapped on stock KDE.
* **Zero pre-installed junk.** No trial software, no vendor bloat — what ships is either a system essential or a tool built specifically for this OS.

More screenshots and a full feature walkthrough live on the [official site](https://psyche-games.com/equestria-os.php).

## 💿 Get Equestria OS

There are two ways to run it, depending on how much of your system you want to hand over:

### Option 1 — Install the full OS

Equestria OS ships as a bootable ISO (built with `archiso`) with the **Calamares** graphical installer — download, boot, install, done, no terminal required.

* **Download:** [sourceforge.net/projects/equestria-os](https://sourceforge.net/projects/equestria-os/)
* **Desktop:** KDE Plasma 6 (SDDM login, Plymouth boot screen)
* **Boot support:** BIOS (Syslinux), UEFI (GRUB or systemd-boot)
* **Recommended requirements:** 64-bit (x86_64) CPU, 4 GB RAM minimum (8+ GB recommended), 30 GB free storage (SSD recommended), OpenGL 3.3-capable graphics. The installer itself only hard-blocks below 1 GB RAM / 5.5 GB storage, but that's a bare technical floor, not a comfortable daily-use system.
* **Bundled apps:** Firefox, ImageFinish (a Photoshop-inspired image editor), Light Image (a Lightroom-style RAW photo manager), Filelight, and the full Equestria OS tool suite below — all pre-installed and pre-themed

### Option 2 — Add the repo to your existing Arch or EndeavourOS install

If you're already running standard Arch Linux or EndeavourOS and just want our tools without reinstalling, add this repository to pacman.

**Step 1: Open your pacman configuration file**

```bash
sudo nano /etc/pacman.conf
```

**Step 2: Add our repository** — add the following to the very bottom of the file:

```ini
[equestria-os]
SigLevel = Optional TrustAll
Server = https://Lucia7Lunadottir.github.io/equestria-os-packages/x86_64
```

**Step 3: Update your package databases**

```bash
sudo pacman -Sy
```

**Step 4: Install a tool** — for example, the Welcome Hub:

```bash
sudo pacman -S equestria-os-welcome-hub
```

## 🖥️ GPU & driver handling

Graphics drivers are set up automatically, on both fresh installs and live systems:

* **Turing and newer NVIDIA GPUs** work out of the box with the current proprietary driver.
* **Pascal, Maxwell, and Volta GPUs** (e.g. GTX 10-series) are handled by `pg-gpu-sync`, which detects the card and switches to the legacy `580.x` driver branch (`equestria-nvidia-580xx`) from an offline package cache — no manual driver hunting needed.
* Mesa, Vulkan (loader + open ICDs), VA-API hardware video decoding, and both Wayland and X11 sessions are supported out of the box.

## 📦 What's inside this repo

### Core identity
* **`equestria-os-branding`**: Official visual style — SDDM, GRUB theme, Plymouth boot screen, Plasma splash, cutiemarks.
* **`equestria-os-keyring`**: Digital trust keys for the Equestria OS package repository.

### Control center
* **`equestria-os-settings`**: Unified settings panel — every tool below is embedded here as a module.

### Software management
* **`equestria-os-software-center`**: Software Center with an Essentials tab, a Pacman/AUR/Flatpak app store, and integrity checks.
* **`equestria-os-package-manager`**: Uninstall, manage, and clean leftover app data.
* **`equestria-installer`** *(AppInstaller)*: Graphical local package installer (double-click a `.pkg.tar.zst` to install it).

### Gaming
* **`proton-exe-starter`**: Native `.exe` launcher via Proton — double-click support, Proton version manager, Xbox 360 gamepad mode.

### Hardware & drivers
* **`pg-gpu-sync`**: NVIDIA driver manager — detects your GPU at boot and configures the right driver and KDE compositor settings automatically.
* **`pg-nvidia-hook`**: Rebuilds the initramfs automatically after NVIDIA driver updates.
* **`equestria-nvidia-580xx`**: Proprietary NVIDIA 580.x driver branch (utils, DKMS, compute, OptiX) for legacy Pascal/Maxwell/Volta GPUs.
* **`equestria-nvidia-dkms`**: Self-updating proprietary NVIDIA modules (fallback path) for Pascal/Maxwell/Volta.
* **`lib32-equestria-nvidia-580xx`**: 32-bit userspace libraries for the 580.x branch (Steam/Proton support).

### System maintenance
* **`pg-hooks`**: Pacman hooks that keep distro branding intact after system updates.
* **`pg-update`**: KDE notifications when updates are available.
* **`pg-reboot-notify`**: KDE notification when a reboot is needed after updates.
* **`pg-rankmirrors`**: Mirror manager with country selection.
* **`equestria-os-save-point`**: System snapshot manager (Btrfs/Restic/Timeshift).
* **`equestria-os-swap-manager`**: Manage swap files, partitions, and swappiness.
* **`equestria-os-disk-manager`**: Mount points, fstab, permissions, labels, formatting, and partitioning.
* **`equestria-os-services-manager`**: Enable, disable, start, and stop systemd services.

### Desktop & appearance
* **`equestria-os-character-theme`**: One-click theming engine — KDE colors, wallpapers, and Konsole themes per Equestria character.
* **`equestria-os-task-panel-changer`**: Task panel style manager for KDE Plasma 6.

### Utilities
* **`equestria-os-git-askpass`**: Native GUI Git credential prompt (fixes Unity/Git integration errors).
* **`equestria-os-relocator`**: Move files/folders and leave a symlink behind at the original location.
* **`equestria-os-rename-helper`**: Bulk file renaming with Find and Replace.
* **`desktop-editor-ui`**: Quickly create and edit `.desktop` files.
* **`equestria-os-welcome-hub`**: Welcome Center and community portal.
* **`equestria-os-tutorial`**: Interactive tour for new Equestria OS users.

## 🌐 Community

* **[Official site](https://psyche-games.com/equestria-os.php)** — screenshots, feature overview, and news.
* **[Equestria Net](https://equestria-net.psyche-games.com)** — the project's own social network, linked right from the Welcome Hub app that ships with the OS.
* **[GitHub Issues](https://github.com/Lucia7Lunadottir/equestria-os-packages/issues)** — bug reports, driver quirks on your specific hardware, and feature requests all go here, on this repository.
* **Pull Requests** — welcome, see [Contributing](#-contributing) below for where to start.
* The in-OS **Welcome Hub** also links out to the wider brony community (fan music channels, r/mylittlepony, fan games) for anyone new to the fandom side of things, not just the Linux side.

## 🤝 Contributing

Equestria OS is one person's hobby project, which means there's more to do than there is time to do it — genuinely useful place for another pair of hands, whether that's one PR or an ongoing thing.

**Repo layout, if you're getting oriented:**
* Each top-level directory (`pg-gpu-sync/`, `equestria-os-branding/`, etc.) is a single Arch package with its own `PKGBUILD`. Build and test one in isolation with `makepkg -si` from inside its folder.
* GUI applications live under `opt/equestria-os/<package-name>/` — that's the actual installed path on a running system, so it doubles as the source tree.
* `docs/x86_64/` is the built pacman repository, served via GitHub Pages at the URL used in the [Get Equestria OS](#-get-equestria-os) instructions above — it's generated, not hand-edited.

**Tech stack:** almost all GUI tools are Python + PyQt6, sharing a common dark-theme `style.qss` per app. System-level glue (pacman hooks, driver switching, initramfs rebuilds) is Bash. Packaging is standard Arch `PKGBUILD`s throughout — if you know Arch packaging, you already know most of what you need here.

**If you want to add a feature to Settings specifically:** it's a plugin architecture — `equestria-os-settings/base_module.py` defines a `BaseModule` base class, and any `modules/mod_*.py` file with exactly one class inheriting it gets auto-discovered at startup. No registration step, no central list to edit.

**Concrete ways to help, in order of how quick they are to pick up:**
1. **Bug reports** — especially with your exact GPU model, laptop model, and whether you're on Wayland or X11. A lot of the trickiest bugs here are hardware-specific (Optimus laptops, specific NVIDIA generations) and hard to catch without a wide range of real machines testing them.
2. **Translation review** — every app ships in 10 languages (en, ru, de, fr, es, pt, pl, uk, zh, ja). Russian and English are maintained by hand; native-speaker review of the other eight is genuinely wanted.
3. **Hardware testing** — AMD and Intel GPU users in particular; a lot of the driver-handling code has historically been NVIDIA-first.
4. **Code contributions** — new Settings modules, fixes, or extending existing tools. Open an Issue first for anything non-trivial so we're aligned before you sink time into it.

I kindly ask for your understanding and constructive feedback as I continue to learn and improve this project — I'm learning a lot of this as I go.

## 💖 A Solo Passion Project

Equestria OS and all the packages in this repository are developed entirely by one person. This is my very first fan-hobby project in the Linux world, and it's the exact same operating system I use every single day as my daily driver!

*"Make Your Computer Feel Like Home."*

Created for the herd, by Psyche Games.

## ⚖️ Trademark & Legal

Equestria OS is an independent, fan-created Linux distribution. It is not affiliated with, endorsed by, or sponsored by Hasbro. "My Little Pony" and "Equestria Girls" are registered trademarks of Hasbro. The custom software and architecture in this repository are copyright Psyche Games.
