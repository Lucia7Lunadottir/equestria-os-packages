# Equestria OS: подключает каталог брендинговых XDG-переопределений.
# Он встаёт в XDG_DATA_DIRS раньше /usr/share, поэтому иконки с теми же
# именами и путями, что в breeze (например start-here-kde для Kickoff),
# перекрываются логотипом системы — без изменения файлов пакета breeze-icons.
case ":${XDG_DATA_DIRS:=/usr/local/share:/usr/share}:" in
    *:/usr/share/equestria-os/xdg:*) ;;
    *) export XDG_DATA_DIRS="/usr/share/equestria-os/xdg:$XDG_DATA_DIRS" ;;
esac
