import os
import shutil
import re

PLASMA_CONFIG = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
PLASMA_SHELLRC = os.path.expanduser("~/.config/plasmashellrc")

_QDBUS_BIN = None

def find_qdbus():
    global _QDBUS_BIN
    if _QDBUS_BIN is not None:
        return _QDBUS_BIN
    for candidate in ("qdbus6", "qdbus-qt6", "qdbus"):
        if shutil.which(candidate):
            _QDBUS_BIN = candidate
            return _QDBUS_BIN
    _QDBUS_BIN = "qdbus6"
    return _QDBUS_BIN

# Заголовок виджета памяти по языкам (тот же список — в fix_sysmon_title.sh,
# который при логине превращает сырую строку в локализуемый Title-блок)
MEMORY_TITLES = {
    "en": "Memory Usage",
    "de": "Speicherauslastung",
    "es": "Uso de la memoria",
    "fr": "Utilisation de la mémoire",
    "ja": "メモリ使用量",
    "pl": "Użycie pamięci",
    "pt": "Utilização da memória",
    "ru": "Использование памяти",
    "uk": "Використання пам'яті",
    "zh": "内存使用",
}

def memory_title_for_locale() -> str:
    """Заголовок «Использование памяти» на текущем языке системы."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if not val:
            continue
        for part in val.split(":"):
            code = part.split(".")[0].split("_")[0].lower()
            if code in MEMORY_TITLES:
                return MEMORY_TITLES[code]
    return MEMORY_TITLES["en"]

def _sysmon_config_js(var: str) -> str:
    """JS-блок конфигурации виджета памяти (ключи из faceproperties)."""
    return (
        f"{var}.currentConfigGroup=['Appearance'];"
        f"{var}.writeConfig('chartFace','org.kde.ksysguard.piechart');"
        f"{var}.writeConfig('title','{memory_title_for_locale()}');"
        f"{var}.currentConfigGroup=['Sensors'];"
        f"""{var}.writeConfig('highPrioritySensorIds','["memory/physical/used"]');"""
        f"""{var}.writeConfig('lowPrioritySensorIds','["memory/physical/total"]');"""
        f"""{var}.writeConfig('totalSensors','["memory/physical/usedPercent"]');"""
    )

def upgrade_script_sysmon(script: str) -> str:
    """Дополняет addWidget системного монитора конфигурацией памяти.

    Скрипты пресетов (включая кастомные, сохранённые старыми версиями и
    хранящиеся только у пользователя) содержат «голый» addWidget — такой
    виджет создаётся пустым: faceproperties применяет только GUI-путь
    добавления. Уже сконфигурированным скриптам повторная запись тех же
    значений не вредит.
    """
    counter = [0]

    def repl(m):
        var, panel, plugin = m.group(1), m.group(2), m.group(3)
        if not var:
            counter[0] += 1
            var = f"eqsm{counter[0]}"
        return f"var {var}={panel}.addWidget('{plugin}');" + _sysmon_config_js(var)

    return re.sub(
        r"(?:var\s+(\w+)\s*=\s*)?(\w+)\.addWidget\('(org\.kde\.plasma\.systemmonitor(?:\.memory)?)'\);",
        repl, script)

def repair_sysmon_in_file(path: str) -> None:
    """Дочиняет пустые виджеты системного монитора в файле конфигурации.

    Захваченные раскладки могли сохранить виджет без сенсоров (если он был
    создан «голым» скриптом старой версии) — при восстановлении такой
    раскладки виджет оставался бы пустым.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    raw_sections = re.split(r'\n(?=\s*\[)', content)
    sections = {}
    order = []
    for chunk in raw_sections:
        if not chunk.strip():
            continue
        lines = chunk.split('\n')
        header = lines[0].strip()
        if header.startswith('[') and header.endswith(']'):
            sections[header] = lines[1:]
            order.append(header)
        else:
            sections.setdefault('', []).extend(lines)
            if '' not in order:
                order.insert(0, '')

    sensor_keys = [
        'highPrioritySensorIds=["memory/physical/used"]',
        'lowPrioritySensorIds=["memory/physical/total"]',
        'totalSensors=["memory/physical/usedPercent"]',
    ]
    changed = False
    for sec in list(order):
        if sec == '' or not any(
                l.strip().startswith('plugin=org.kde.plasma.systemmonitor')
                for l in sections[sec]):
            continue
        base = sec[:-1]
        sensors_sec = f"{base}][Configuration][Sensors]"
        appear_sec = f"{base}][Configuration][Appearance]"

        if sensors_sec in sections:
            if not any(l.strip().startswith('highPrioritySensorIds=')
                       for l in sections[sensors_sec]):
                sections[sensors_sec] = [l for l in sections[sensors_sec] if l.strip()] + sensor_keys
                changed = True
        else:
            sections[sensors_sec] = list(sensor_keys)
            order.insert(order.index(sec) + 1, sensors_sec)
            changed = True

        if appear_sec in sections:
            if not any(l.strip().startswith('chartFace=') for l in sections[appear_sec]):
                sections[appear_sec] = ([l for l in sections[appear_sec] if l.strip()]
                                        + ['chartFace=org.kde.ksysguard.piechart'])
                changed = True
        else:
            sections[appear_sec] = ['chartFace=org.kde.ksysguard.piechart',
                                    f'title={memory_title_for_locale()}']
            order.insert(order.index(sec) + 1, appear_sec)
            changed = True

    if not changed:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            for sec in order:
                if sec == '':
                    f.write('\n'.join(sections[sec]) + '\n')
                else:
                    sec_lines = [l for l in sections[sec] if l.strip() or l == '']
                    f.write(f"{sec}\n" + '\n'.join(sec_lines) + '\n')
    except OSError:
        pass

def localize_script_sysmon_titles(script: str) -> str:
    """Заменяет запечённый в скрипт пресета заголовок виджета памяти
    на вариант для текущего языка пользователя (в момент применения)."""
    title = memory_title_for_locale()
    variants = "|".join(re.escape(t) for t in MEMORY_TITLES.values())
    return re.sub(
        rf"writeConfig\('title',\s*'({variants})'\)",
        f"writeConfig('title','{title}')",
        script,
    )

def validate_launchers_string(launchers_str: str) -> str:
    """Проверяет каждый ярлык в системе. Если приложения нет в XDG — убирает из панели."""
    if not launchers_str: 
        return ""
    
    xdg_dirs = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/share/applications",
        "/usr/local/share/applications",
        "/var/lib/flatpak/exports/share/applications"
    ]
    
    valid_items = []
    for item in launchers_str.split(","):
        item = item.strip()
        if not item: 
            continue
        if item.startswith("preferred://") or item.startswith("file://"):
            valid_items.append(item)
            continue
        if item.startswith("applications:"):
            desktop_name = item.split(":", 1)[1]
            if any(os.path.exists(os.path.join(d, desktop_name)) for d in xdg_dirs):
                valid_items.append(item)
            continue
        if item.endswith(".desktop"):
            if any(os.path.exists(os.path.join(d, item)) for d in xdg_dirs):
                valid_items.append(f"applications:{item}")
            continue
        valid_items.append(item)
        
    return ",".join(valid_items)

def extract_launchers(file_path):
    """Безопасно извлекает launchers из указанного файла конфигурации на основе блоков."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    raw_sections = re.split(r'\n(?=\s*\[)', content)
    sections_dict = {}
    for chunk in raw_sections:
        if not chunk.strip(): continue
        lines = chunk.split('\n')
        header = lines[0].strip()
        if header.startswith('[') and header.endswith(']'):
            sections_dict[header] = lines[1:]

    task_applets = []
    for sec, lines in sections_dict.items():
        for line in lines:
            if line.strip().startswith('plugin='):
                p_val = line.split('=', 1)[1].strip()
                if p_val in ("org.kde.plasma.icontasks", "org.kde.plasma.taskmanager"):
                    task_applets.append(sec)

    for applet in task_applets:
        gen_sec = f"{applet[:-1]}][Configuration][General]"
        if gen_sec in sections_dict:
            for line in sections_dict[gen_sec]:
                if line.strip().startswith('launchers='):
                    return line.split('=', 1)[1].strip()

    # Резервный поиск по всему файлу
    for line in content.split('\n'):
        if line.strip().startswith('launchers='):
            val = line.split('=', 1)[1].strip()
            if val: return val
    return None

def preserve_user_launchers(src_preset_path, dest_live_path):
    """
    Извлекает текущие launchers из dest_live_path, генерирует или обновляет подсекцию 
    [Configuration][General] в структуре src_preset_path и сохраняет результат в dest_live_path.
    """
    if not os.path.exists(src_preset_path):
        return
        
    current_launchers = None
    if os.path.exists(dest_live_path):
        current_launchers = extract_launchers(dest_live_path)
        
    if not current_launchers:
        try:
            shutil.copy2(src_preset_path, dest_live_path)
            # В раскладке пресета ярлыки запечены на момент захвата — часть
            # приложений могла быть удалена; вычищаем несуществующие
            validate_launchers_in_file(dest_live_path)
        except Exception:
            pass
        return

    current_launchers = validate_launchers_string(current_launchers)

    try:
        with open(src_preset_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return

    raw_sections = re.split(r'\n(?=\s*\[)', content)
    sections_dict = {}
    sections_order = []

    for chunk in raw_sections:
        if not chunk.strip(): continue
        lines = chunk.split('\n')
        header = lines[0].strip()
        if header.startswith('[') and header.endswith(']'):
            sections_dict[header] = lines[1:]
            sections_order.append(header)
        else:
            if '' not in sections_dict: sections_dict[''] = []
            sections_dict[''].extend(lines)
            if '' not in sections_order: sections_order.append('')

    task_applets = []
    for sec, lines in sections_dict.items():
        for line in lines:
            if line.strip().startswith('plugin='):
                p_val = line.split('=', 1)[1].strip()
                if p_val in ("org.kde.plasma.icontasks", "org.kde.plasma.taskmanager"):
                    task_applets.append(sec)

    for applet in task_applets:
        gen_sec = f"{applet[:-1]}][Configuration][General]"
        if gen_sec in sections_dict:
            lines = sections_dict[gen_sec]
            new_lines = []
            found_launchers = False
            for line in lines:
                if line.strip().startswith('launchers='):
                    new_lines.append(f"launchers={current_launchers}")
                    found_launchers = True
                else:
                    new_lines.append(line)
            if not found_launchers:
                new_lines.append(f"launchers={current_launchers}")
            sections_dict[gen_sec] = new_lines
        else:
            # Секции не существовало — создаем её с нуля и помещаем сразу за апплетом
            sections_dict[gen_sec] = [f"launchers={current_launchers}"]
            idx = sections_order.index(applet)
            sections_order.insert(idx + 1, gen_sec)

    try:
        with open(dest_live_path, "w", encoding="utf-8") as f:
            for sec in sections_order:
                if sec == '':
                    f.write('\n'.join(sections_dict[sec]) + '\n')
                else:
                    sec_lines = [l for l in sections_dict[sec] if l.strip() or l == '']
                    f.write(f"{sec}\n" + '\n'.join(sec_lines) + '\n')
    except Exception:
        pass

def get_current_launchers():
    val = extract_launchers(PLASMA_CONFIG)
    return validate_launchers_string(val) if val else None

def launchers_inject_script(launchers_str: str) -> str:
    """JS для evaluateScript: прописывает ярлыки во все панели задач.

    Запускается после пересоздания панелей пресетом — иначе новая панель
    задач получает дефолтные ярлыки KDE, а закрепления пользователя теряются.
    """
    safe = str(launchers_str).replace("\\", "").replace("'", "")
    return (
        "var pn=panels();"
        "for(var i=0;i<pn.length;++i){"
        "var ids=pn[i].widgetIds;"
        "for(var j=0;j<ids.length;++j){"
        "var w=pn[i].widgetById(ids[j]);"
        "if(w.type=='org.kde.plasma.icontasks'||w.type=='org.kde.plasma.taskmanager'){"
        "w.currentConfigGroup=['General'];"
        f"w.writeConfig('launchers','{safe}');"
        "if(typeof w.reloadConfig==='function'){w.reloadConfig();}"
        "}}}"
    )

def rewrite_script_launchers(script: str) -> str:
    """Перевалидирует ярлыки, запечённые в скрипт пресета при его сохранении.

    Скрипт хранит launchers статичной строкой: приложение могли удалить
    уже после сохранения пресета — тогда панель закрепляла бы несуществующий
    ярлык. Проверяем каждый по XDG прямо в момент применения.
    """
    def repl(m):
        return f"writeConfig('launchers','{validate_launchers_string(m.group(1))}')"
    return re.sub(r"writeConfig\('launchers',\s*'([^']*)'\)", repl, script)

def validate_launchers_in_file(path: str) -> None:
    """Валидирует строки launchers= в файле конфигурации панелей на месте."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    changed = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("launchers="):
            val = stripped.split("=", 1)[1]
            fixed = validate_launchers_string(val)
            if fixed != val:
                lines[i] = f"launchers={fixed}\n"
                changed = True
    if changed:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except OSError:
            pass

def set_desktop_icons_state(hide: bool) -> bool:
    if not os.path.exists(PLASMA_CONFIG):
        return False
    try:
        with open(PLASMA_CONFIG, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return False
    old_plugin = "org.kde.plasma.folder" if hide else "org.kde.desktopcontainment"
    new_plugin = "org.kde.desktopcontainment" if hide else "org.kde.plasma.folder"
    changed = False
    new_lines = []
    in_containments = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[Containments]"):
            in_containments = True
        elif stripped.startswith("[") and not stripped.startswith("[Containments]"):
            in_containments = False
        if in_containments and stripped == f"plugin={old_plugin}":
            new_lines.append(f"plugin={new_plugin}\n")
            changed = True
        else:
            new_lines.append(line)
    if changed:
        try:
            with open(PLASMA_CONFIG, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except OSError:
            return False
    return changed

def generate_script_from_panels(panels_config):
    LAUNCHER_MAP = {
        "kickoff":    "org.kde.plasma.kickoff",
        "kicker":     "org.kde.plasma.kicker",
        "kickerdash": "org.kde.plasma.kickerdash",
    }
    ICON = "/usr/share/pixmaps/equestria-os-logo.png"
    current_launchers = get_current_launchers()
    parts = ["var a=panels();for(var i=0;i<a.length;i++){a[i].remove();}"]
    for i, p in enumerate(panels_config):
        v = f"p{i}"
        pos      = p.get("position", "bottom")
        height   = p.get("height", 48)
        width_px = p.get("width", 0)
        offset   = p.get("offset", 0)
        align    = p.get("alignment", "center" if p.get("floating") else "left")
        floatP   = p.get("floating", False)
        vis      = p.get("visibilityMode", "none")
        if vis == "windowsbelow": vis = "dodgewindows"
        if vis == "windowscover": vis = "windowsgobelow"
        if p.get("autohide", False) and vis == "none": vis = "autohide"
        lmode    = p.get("lengthMode", "fill")
        launch   = p.get("launcher", "none")
        ww       = p.get("widgets", [])
        parts.append(f"var {v}=new Panel;")
        parts.append(f"{v}.location='{pos}';")
        parts.append(f"{v}.height={height};")
        parts.append(f"{v}.alignment='{align}';")
        if floatP: parts.append(f"{v}.floating=true;")
        parts.append(f"{v}.lengthMode='{lmode}';")
        if width_px > 0: parts.append(f"{v}.minimumLength={width_px};{v}.maximumLength={width_px};")
        if offset != 0: parts.append(f"{v}.offset={offset};")
        if vis != "none": parts.append(f"{v}.hiding='{vis}';")
        has_launcher = launch in LAUNCHER_MAP
        has_taskbar  = "taskbar" in ww
        has_right    = any(x in ww for x in ("pager", "monitor", "systray", "clock"))
        if has_launcher:
            pid = LAUNCHER_MAP[launch]
            parts.append(f"var k{i}={v}.addWidget('{pid}');")
            parts.append(f"k{i}.currentConfigGroup=['General'];")
            parts.append(f"k{i}.writeConfig('icon','{ICON}');")
        if "appmenu" in ww: parts.append(f"{v}.addWidget('org.kde.plasma.appmenu');")
        if has_launcher and (has_taskbar or has_right): parts.append(f"{v}.addWidget('org.kde.plasma.panelspacer');")
        if has_taskbar:
            parts.append(f"var t{i}={v}.addWidget('org.kde.plasma.icontasks');")
            if current_launchers:
                parts.append(f"t{i}.currentConfigGroup=['General'];")
                parts.append(f"t{i}.writeConfig('launchers','{current_launchers}');")
            if has_right: parts.append(f"{v}.addWidget('org.kde.plasma.panelspacer');")
        if "pager"   in ww: parts.append(f"{v}.addWidget('org.kde.plasma.pager');")
        if "monitor" in ww:
            # Пресетные плазмоиды (.memory) при добавлении скриптом НЕ применяют
            # свой faceproperties (это делает только GUI-путь добавления виджета),
            # поэтому сенсоры и вид записываем явно — как в рабочем виджете ISO.
            parts.append(f"var m{i}={v}.addWidget('org.kde.plasma.systemmonitor.memory');")
            parts.append(_sysmon_config_js(f"m{i}"))
        if "systray" in ww: parts.append(f"{v}.addWidget('org.kde.plasma.systemtray');")
        if "clock"   in ww: parts.append(f"{v}.addWidget('org.kde.plasma.digitalclock');")
        parts.append(f"{v}.height={height};")
    return "".join(parts)

def generate_panel_svg(hex_color, opacity_float):
    c = hex_color
    op = f"{opacity_float:.2f}"
    r = 8
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">\n'
        '  <defs>\n'
        f'    <style>rect {{ fill: {c}; fill-opacity: {op}; }}</style>\n'
        '  </defs>\n'
        '\n'
        '  <rect id="hint-stretch-borders" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        f'  <rect id="center"      x="6" y="6" width="88" height="88"/>\n'
        f'  <rect id="top"         x="6" y="0" width="88" height="6"/>\n'
        f'  <rect id="bottom"      x="6" y="94" width="88" height="6"/>\n'
        f'  <rect id="left"        x="0" y="6" width="6" height="88"/>\n'
        f'  <rect id="right"       x="94" y="6" width="6" height="88"/>\n'
        f'  <rect id="topleft"     x="0" y="0" width="6" height="6"/>\n'
        f'  <rect id="topright"    x="94" y="0" width="6" height="6"/>\n'
        f'  <rect id="bottomleft"  x="0" y="94" width="6" height="6"/>\n'
        f'  <rect id="bottomright" x="94" y="94" width="6" height="6"/>\n'
        '\n'
        '  <rect id="shadow-top"         x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-bottom"      x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-left"        x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-right"       x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-topleft"     x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-topright"    x="94" y="0" width="6" height="6" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-bottomleft"  x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-bottomright" x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '\n'
        f'  <rect id="floating-center"      x="{r}" y="{r}" width="{100-2*r}" height="{100-2*r}" rx="{r}" ry="{r}"/>\n'
        f'  <rect id="floating-top"         x="{r}" y="0" width="{100-2*r}" height="{r}"/>\n'
        f'  <rect id="floating-bottom"      x="{r}" y="{100-r}" width="{100-2*r}" height="{r}"/>\n'
        f'  <rect id="floating-left"        x="0" y="{r}" width="{r}" height="{100-2*r}"/>\n'
        f'  <rect id="floating-right"       x="{100-r}" y="{r}" width="{r}" height="{100-2*r}"/>\n'
        f'  <rect id="floating-topleft"     x="0" y="0" width="{r}" height="{r}"/>\n'
        f'  <rect id="floating-topright"    x="{100-r}" y="0" width="{r}" height="{r}"/>\n'
        f'  <rect id="floating-bottomleft"  x="0" y="{100-r}" width="{r}" height="{r}"/>\n'
        f'  <rect id="floating-bottomright" x="{100-r}" y="{100-r}" width="{r}" height="{r}"/>\n'
        '\n'
        '  <rect id="floating-shadow-top"         x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-bottom"      x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-left"        x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-right"       x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-topleft"     x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-topright"    x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-bottomleft"  x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-bottomright" x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '\n'
        f'  <rect id="mask-center"      x="{r}" y="{r}" width="{100-2*r}" height="{100-2*r}" rx="{r}" ry="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-top"         x="{r}" y="0" width="{100-2*r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-bottom"      x="{r}" y="{100-r}" width="{100-2*r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-left"        x="0" y="{r}" width="{r}" height="{100-2*r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-right"       x="{100-r}" y="{r}" width="{r}" height="{100-2*r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-topleft"     x="0" y="0" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-topright"    x="{100-r}" y="0" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-bottomleft"  x="0" y="{100-r}" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-bottomright" x="{100-r}" y="{100-r}" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        '\n'
        '  <rect id="hint-compose-over-border" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '</svg>\n'
    )

def apply_system_theme_fixes():
    desktop_theme_dir = os.path.expanduser("~/.local/share/plasma/desktoptheme/default")
    os.makedirs(desktop_theme_dir, exist_ok=True)
    import configparser
    import json
    kdeglobals_path = os.path.expanduser("~/.config/kdeglobals")
    # interpolation=None: в kdeglobals встречаются значения с '%', на которых
    # интерполяция configparser падает; strict=False терпит дубликаты ключей
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    if os.path.exists(kdeglobals_path):
        try:
            config.read(kdeglobals_path)
        except configparser.Error:
            return
    if 'Colors:Complementary' not in config:
        config.add_section('Colors:Complementary')
    config.set('Colors:Complementary', 'BackgroundNormal', '0,0,0')
    config.set('Colors:Complementary', 'ForegroundNormal', '255,255,255')
    config.set('Colors:Complementary', 'ForegroundInactive', '200,200,200')
    try:
        with open(kdeglobals_path, 'w', encoding='utf-8') as f: config.write(f)
    except OSError: pass
    # KF6/KPackage: metadata.json вместо устаревшего metadata.desktop
    # (KSvg в Plasma 6 читает .desktop только через legacy-путь с предупреждением)
    theme_meta_path = os.path.join(desktop_theme_dir, "metadata.json")
    if not os.path.exists(theme_meta_path):
        try:
            with open(theme_meta_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "KPlugin": {"Id": "default", "Name": "Equestria Fallback"},
                    "X-Plasma-API-Minimum-Version": "6.0",
                }, f, indent=4)
        except OSError: pass
    # подчищаем legacy-файл, оставшийся от старых версий этой утилиты
    legacy_meta = os.path.join(desktop_theme_dir, "metadata.desktop")
    if os.path.exists(legacy_meta):
        try:
            os.remove(legacy_meta)
        except OSError: pass
    settings_path = os.path.join(desktop_theme_dir, "settings")
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            f.write("baseTheme=breeze\nShutdown Dialog=breeze\nLockScreen=breeze\n")
    except OSError: pass
    try:
        import subprocess
        subprocess.run(["systemctl", "--user", "restart", "plasma-powerdevil.service"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception: pass
    qdbus = find_qdbus()
    try:
        import subprocess
        subprocess.run(f"{qdbus} org.kde.KWin /KWin reconfigure", shell=True, check=False)
    except Exception: pass