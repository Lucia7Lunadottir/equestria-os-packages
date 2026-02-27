#!/bin/bash
# setup_fastfetch_eg_png.sh — PNG кьютимарки через chafa
# fastfetch 2.59.0, EndeavourOS/Arch

FF_DIR="$HOME/.config/fastfetch"
CM_DIR="/usr/share/equestria-os/cutiemarks"
mkdir -p "$FF_DIR"

# Проверяем chafa
if ! command -v chafa &>/dev/null; then
    echo "Устанавливаю chafa..."
    sudo pacman -S --noconfirm chafa
fi

# Создаём системную папку и копируем PNG
# Запусти один раз с sudo чтобы скопировать файлы:
# sudo mkdir -p /usr/share/equestria-os/cutiemarks
# sudo cp ~/path/to/cutiemarks/* /usr/share/equestria-os/cutiemarks/

make_config() {
    local ID="$1" PNG="$2" COLOR1="$3"
    cat > "$FF_DIR/config_${ID}.jsonc" << JSONC
{
    "logo": {
        "source": "${PNG}",
        "type": "chafa",
        "width": 18,
        "height": 8,
        "padding": { "right": 2 }
    },
    "display": {
        "separator": "  ",
        "color": { "keys": "${COLOR1}", "title": "${COLOR1}" }
    },
    "modules": [
        "title", "separator",
        { "type": "os",       "key": "  OS"       },
        { "type": "kernel",   "key": "  Kernel"   },
        { "type": "de",       "key": "  DE"       },
        { "type": "shell",    "key": "  Shell"    },
        { "type": "terminal", "key": "  Terminal" },
        { "type": "cpu",      "key": "  CPU"      },
        { "type": "gpu",      "key": "  GPU"      },
        { "type": "memory",   "key": "  RAM"      },
        { "type": "disk",     "key": "  Disk"     },
        { "type": "uptime",   "key": "  Uptime"   },
        "separator",
        { "type": "colors",   "symbol": "circle"  }
    ]
}
JSONC
    echo "OK config_${ID}.jsonc"
}

echo "Создаю конфиги..."

make_config "sunset" "/usr/share/equestria-os/cutiemarks/sunset_shimmer.png" "red"
make_config "twilight" "/usr/share/equestria-os/cutiemarks/twilight_sparkle.png" "magenta"
make_config "rainbow" "/usr/share/equestria-os/cutiemarks/rainbow_dash.png" "cyan"
make_config "rarity" "/usr/share/equestria-os/cutiemarks/rarity.png" "bright_cyan"
make_config "applejack" "/usr/share/equestria-os/cutiemarks/applejack.png" "yellow"
make_config "fluttershy" "/usr/share/equestria-os/cutiemarks/fluttershy.png" "green"
make_config "pinkie" "/usr/share/equestria-os/cutiemarks/pinkie_pie.png" "magenta"

echo ""
echo "Готово! Проверяй:"
echo ""
echo "  fastfetch --config ~/.config/fastfetch/config_sunset.jsonc"
echo "  fastfetch --config ~/.config/fastfetch/config_twilight.jsonc"
echo "  fastfetch --config ~/.config/fastfetch/config_rainbow.jsonc"
echo "  fastfetch --config ~/.config/fastfetch/config_rarity.jsonc"
echo "  fastfetch --config ~/.config/fastfetch/config_applejack.jsonc"
echo "  fastfetch --config ~/.config/fastfetch/config_fluttershy.jsonc"
echo "  fastfetch --config ~/.config/fastfetch/config_pinkie.jsonc"
echo ""
