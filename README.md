# 🦄 Equestria OS - Custom Packages Repository

Welcome to the official package repository for **Equestria OS**!

This repository contains the source code, build scripts, and the compiled Arch Linux repository (`x86_64`) for every native tool, driver helper, and theming package that makes Equestria OS what it is.

## 📦 What's inside?

### Core identity
* **`equestria-os-branding`**: Official visual style — SDDM, GRUB theme, Plasma splash, cutiemarks.
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

## ⚙️ How to use this repository on Arch Linux

If you are already running standard Arch Linux or EndeavourOS and want to try our Unity-powered utilities without reinstalling your system, you can add this repository!

### Step 1: Open your pacman configuration file

```bash
sudo nano /etc/pacman.conf
```

### Step 2: Add our repository

Add the following lines to the very bottom of the file:

```ini
[equestria-os]
SigLevel = Optional TrustAll
Server = https://Lucia7Lunadottir.github.io/equestria-os-packages/x86_64
```

### Step 3: Update your package databases

```bash
sudo pacman -Sy
```

### Step 4: Install our tools!

For example, to install the Welcome Hub:

```bash
sudo pacman -S equestria-os-welcome-hub
```

## 💖 A Solo Passion Project

Equestria OS and all the packages in this repository are developed entirely by one person. This is my very first fan-hobby project in the Linux world, and it's the exact same operating system I use every single day as my daily driver!

If you encounter any bugs, have suggestions, or want to contribute, feel free to open an Issue or submit a Pull Request. I kindly ask for your understanding and constructive feedback as I continue to learn and improve this project.

Created for the herd, by Psyche Games.
