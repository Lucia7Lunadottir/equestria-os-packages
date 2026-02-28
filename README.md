# 🦄 Equestria OS - Custom Packages Repository

Welcome to the official package repository for **Equestria OS**! 

This repository contains the source code, build scripts, and the compiled Arch Linux repository (`x86_64`) for all the unique Unity-powered utilities and theming tools that make Equestria OS magical.

## 📦 What's inside?

Here you will find the core packages built specifically for Equestria OS:

* **`equestria-os-package-manager`**: A custom, Unity-powered GUI for managing system packages without touching the terminal.
* **`equestria-os-character-theme`**: Our unique one-click dynamic theming engine. Changes KDE colors, wallpapers, and terminal configurations (fastfetch cutiemarks) based on your favorite character.
* **`equestria-os-welcome-hub`**: The offline portal containing quick links to MLP games, music (JycRow), and community support.
* **`equestria-os-package-installer`**: An offline driver and popular software installer (includes ASUS ROG Center Control).
* **`equestria-branding` & `equestria-keyring`**: Core system identity, logos, and security keys.
* **`pg-hooks` & `pg-gpu-sync`**: Custom backend scripts to ensure smooth performance and gaming integration.

## ⚙️ How to use this repository on Arch Linux

If you are already running standard Arch Linux or EndeavourOS and want to try our magical Unity utilities without reinstalling your system, you can add this repository!

### Step 1: Open your pacman configuration file

```bash
sudo nano /etc/pacman.conf
```

Step 2: Add our repository
Add the following lines to the very bottom of the file:

```Ini, TOML
[equestria-os]
SigLevel = Optional TrustAll
Server = [https://7Lucia7Lokidottir7.github.io/equestria-os-packages/x86_64/](https://7Lucia7Lokidottir7.github.io/equestria-os-packages/x86_64/)
```

Step 3: Update your package databases

```bash
sudo pacman -Sy
```

Step 4: Install our tools!
For example, to install the Welcome Hub:

```bash
sudo pacman -S equestria-os-welcome-hub
```

💖 A Solo Passion Project
Equestria OS and all the packages in this repository are developed entirely by one person. This is my very first fan-hobby project in the Linux world, and it's the exact same operating system I use every single day as my daily driver!

If you encounter any bugs, have suggestions, or want to contribute, feel free to open an Issue or submit a Pull Request. I kindly ask for your understanding and constructive feedback as I continue to learn and improve this project.

Created for the herd, by Psyche Games.
