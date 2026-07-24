"""
Equestria OS Proton — profiles for known-problematic native Windows software
(Adobe, Microsoft Office). These are not games: they need Windows-version
spoofing and a handful of runtime dependencies (fonts, VC++, .NET) that
umu-run/Proton does not install by default. Detected automatically from the
installer's file name, applied once per prefix.
"""

import os
import re
import shutil
import subprocess
import time

# Куда umu кладёт сборки Proton (см. umu_consts.py: STEAM_COMPAT и UMU_COMPAT)
PROTON_COMPAT_DIRS = (
    os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    os.path.expanduser("~/.local/share/umu/compatibilitytools"),
)


def _proton_sort_key(name):
    # Натуральная сортировка версий, как в самом umu (GE-Proton9-4 < GE-Proton10-1)
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def installed_protons():
    """[(имя, абсолютный путь)] всех установленных сборок Proton, новые сверху."""
    found = {}
    for base in PROTON_COMPAT_DIRS:
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            path = os.path.join(base, entry)
            if os.path.isfile(os.path.join(path, "proton")):
                found.setdefault(entry, path)
    return sorted(found.items(), key=lambda kv: _proton_sort_key(kv[0]), reverse=True)


def latest_proton(prefix=""):
    """Путь к самой новой установленной сборке, начинающейся с prefix, или ""."""
    paths = [p for n, p in installed_protons() if n.startswith(prefix)]
    return paths[0] if paths else ""

ADOBE_RE = re.compile(
    r"adobe|creativecloud|photoshop|illustrator|premiere|lightroom|acrobat|"
    r"aftereffects|indesign|audition|animate\.exe|bridge|dimension|xd_setup",
    re.IGNORECASE,
)

OFFICE_RE = re.compile(
    r"officesetup|officedeploymenttool|setup.*office|office.*setup|"
    r"winword|excel\.exe|powerpnt|outlook\.exe|msaccess|visio|onenote",
    re.IGNORECASE,
)

# Installed unconditionally for every prefix: Proton's own accessibility helper
# (xalia.exe) needs a real .NET Framework — Wine Mono isn't enough for it — and
# shows a ".NET Framework v4.0 required" dialog on EVERY launch (any app, not
# just Adobe/Office) until this is installed once per prefix.
BASE_PROFILE = {
    "winetricks": ["corefonts", "dotnet48"],
}

# Verb lists may safely overlap with BASE_PROFILE or each other: verbs are
# installed one at a time (see ensure_dependencies) and skipped individually
# if winetricks.log already shows them installed, so an already-installed
# verb never blocks any other verb from being attempted.
PROFILES = {
    "adobe": {
        "match": ADOBE_RE,
        "win_version": "win10",
        "dll_overrides": "winemenubuilder.exe=d",
        "winetricks": ["vcrun2022", "gdiplus", "msxml6"],
    },
    "office": {
        "match": OFFICE_RE,
        "win_version": "win10",
        "dll_overrides": "winemenubuilder.exe=d",
        "winetricks": ["riched20", "riched30", "msxml3", "msxml6", "vcrun2019", "gdiplus"],
    },
}

# Generous but finite: dotnet48/vcrun installers under Wine can genuinely take
# several minutes, but must never hang forever (seen in practice when
# winetricks' own update-check or a stalled download blocks indefinitely).
DEFAULT_TIMEOUT = 20 * 60


def detect_profile(exe_path: str):
    # Search the full path, not just the file name: Adobe/Office installers are
    # very often literally named "setup.exe" — the vendor hint lives in the
    # parent directory name (e.g. ".../adobe-after-effects-26-0/packages/setup.exe").
    for profile_id, profile in PROFILES.items():
        if profile["match"].search(exe_path):
            return profile_id, profile
    return None, None


def apply_profile_env(env: dict, profile: dict):
    overrides = profile.get("dll_overrides")
    if overrides:
        existing = env.get("WINEDLLOVERRIDES", "")
        env["WINEDLLOVERRIDES"] = f"{existing};{overrides}" if existing else overrides
    return env


def _list_installed_verbs(env: dict) -> set:
    """Спрашивает у самого winetricks, какие verb-ы уже стоят в префиксе
    (winetricks list-installed), через umu-run и тот же env (WINEPREFIX),
    которым будет выполняться сама установка — так проверка смотрит ровно
    в тот префикс, в который реально ставим, а не в дефолтный ~/.wine.
    Не парсим winetricks.log руками: формат строк лога — не документированный
    стабильный контракт, и ошибка в этом предположении тихо приводила бы либо
    к вечному повтору уже поставленных verb-ов, либо к пропуску непоставленных."""
    try:
        result = subprocess.run(
            ["umu-run", "winetricks", "list-installed"],
            env=env, capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return set()  # неизвестно -> считаем, что ничего не стоит (безопасно: не пропустим лишнего)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


# winetricks засчитывает dotnet40/dotnet45/.../dotnet48 как успешно
# установленные (пишет verb в winetricks.log), даже если сам инсталлятор
# ничего не поставил — это происходит, когда Proton уже создал в реестре
# записи ".NET Framework Setup", инсталлятор видит их и решает "уже стоит
# более новая версия", молча завершаясь с кодом успеха (см. Winetricks#2367
# и несколько независимых issue про "installed file ... not found" при
# формально успешном dotnet-verb). Поэтому для dotnet-verb-ов winetricks.log
# недостаточно — дополнительно проверяем, что ключевой файл .NET реально
# лежит на диске в префиксе.
_DOTNET_MARKER_FILE = os.path.join(
    "drive_c", "windows", "Microsoft.NET", "Framework64", "v4.0.30319", "mscorlib.dll"
)


def _dotnet_actually_installed(prefix_path: str) -> bool:
    """True, если файлы .NET Framework 4.x реально присутствуют в префиксе
    (а не просто числятся в winetricks.log как установленные)."""
    return os.path.isfile(os.path.join(prefix_path, "pfx", _DOTNET_MARKER_FILE))


def _installroot_configured(prefix_path: str) -> bool:
    """True, если ключ InstallRoot реально прописан в реестре префикса — в
    ОБОИХ view реестра (обычном и Wow6432Node), т.к. ensure_dependencies
    ниже прописывает оба и разным .NET-приложениям (32- и 64-битным) нужен
    свой соответствующий ключ.

    Даже когда файлы .NET Framework установлены по-настоящему, любое
    .NET-приложение в префиксе (включая xalia.exe — accessibility-помощник
    самого Proton) падает с "Please set registry key
    ...\\.NETFramework\\InstallRoot to point to the .NET Framework install
    location", если этот ключ не прописан явно — winetricks/dotnet-инсталлятор
    под Wine не всегда делает это сам (широко задокументированная отдельная
    проблема, не связанная с тем, реально ли установлены сами файлы).

    HKEY_LOCAL_MACHINE хранится Wine в текстовом файле system.reg внутри
    префикса — читаем его напрямую вместо вызова umu-run reg query, это и
    быстрее, и не требует рабочего Proton только чтобы проверить состояние."""
    system_reg = os.path.join(prefix_path, "pfx", "system.reg")
    try:
        with open(system_reg, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return False
    # Секции system.reg выглядят как [Software\\Microsoft\\.NETFramework] ...,
    # с key=value строками до следующей секции '['. Ищем обе нужные секции
    # (обычную и Wow6432Node) и в каждой — непустое значение InstallRoot.
    for section_path in (
        r"Software\\\\Microsoft\\\\\.NETFramework",
        r"Software\\\\Wow6432Node\\\\Microsoft\\\\\.NETFramework",
    ):
        section_re = re.compile(
            rf"^\[{section_path}\].*?(?=^\[|\Z)", re.MULTILINE | re.DOTALL,
        )
        match = section_re.search(content)
        if not match or not re.search(r'^"InstallRoot"="[^"]+"', match.group(0), re.MULTILINE):
            return False
    return True


def _dotnet_fully_ready(prefix_path: str) -> bool:
    """True, только если .NET и реально установлен (файлы на диске), И
    правильно сконфигурирован для приложений (InstallRoot в реестре).
    Обе проверки нужны независимо: winetricks может засчитать verb без
    реальной установки (_dotnet_actually_installed), а сама установка
    может пройти, но без InstallRoot приложения всё равно не найдут .NET
    (_installroot_configured) — см. докстринги обеих функций."""
    return _dotnet_actually_installed(prefix_path) and _installroot_configured(prefix_path)


def _verb_really_installed(prefix_path: str, verb: str, log_installed: set) -> bool:
    """Учитывает известный обман winetricks.log для dotnet-verb-ов: verb
    из этой группы считается установленным только если ЕЩЁ И .NET реально
    полностью готов (файлы + InstallRoot), а не только записан в логе как
    успешный."""
    if verb not in log_installed:
        return False
    if verb.startswith("dotnet"):
        return _dotnet_fully_ready(prefix_path)
    return True


def needs_bootstrap(prefix_path: str, profile_id: str, profile: dict, env: dict) -> bool:
    """True if ensure_dependencies would actually do work (so callers can show a wait UI)."""
    marker = os.path.join(prefix_path, f".equestria-profile-{profile_id}-done")
    if os.path.exists(marker):
        # Даже если маркер профиля уже стоит, поверх него проверяем dotnet-verb-ы
        # на реальное наличие файлов: маркер мог быть создан раньше — в том числе
        # старым кодом или до фикса реестровых ключей — когда winetricks уже
        # записал dotnet-verb как "успешный", хотя фактическая установка не
        # прошла (см. _verb_really_installed). Не-dotnet verb-ы маркеру доверяем.
        dotnet_verbs = [v for v in (profile.get("winetricks") or []) if v.startswith("dotnet")]
        if not dotnet_verbs:
            return False
        return not _dotnet_fully_ready(prefix_path)
    verbs = profile.get("winetricks") or []
    if not (verbs and shutil.which("winetricks")):
        return False
    installed = _list_installed_verbs(env)
    return any(not _verb_really_installed(prefix_path, v, installed) for v in verbs)


def _run_with_timeout(cmd, env, log_file, timeout, cancel_event):
    """Run cmd streaming to log_file. Returns True iff it exited 0 before the
    timeout/cancel; kills the process group otherwise instead of blocking forever."""
    log_file.write(f"$ {' '.join(cmd)}\n")
    log_file.flush()
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=log_file, stderr=subprocess.STDOUT)
    except Exception as exc:
        log_file.write(f"[failed to start: {exc}]\n")
        return False

    deadline = time.monotonic() + timeout
    while True:
        try:
            return proc.wait(timeout=1) == 0
        except subprocess.TimeoutExpired:
            if (cancel_event is not None and cancel_event.is_set()) or time.monotonic() > deadline:
                log_file.write("\n[cancelled/timed out — killing process]\n")
                proc.kill()
                proc.wait()
                return False


def ensure_dependencies(prefix_path: str, profile_id: str, profile: dict, env: dict,
                         log_path: str, cancel_event=None, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """
    Best-effort, one-time (per prefix) setup: Windows-version spoof + winetricks
    verbs. Never blocks forever — every step has a hard timeout and can be
    aborted via cancel_event. Returns True if the profile is (now) fully applied.
    """
    marker = os.path.join(prefix_path, f".equestria-profile-{profile_id}-done")
    marker_exists = os.path.exists(marker)
    verbs = profile.get("winetricks") or []
    dotnet_verbs = [v for v in verbs if v.startswith("dotnet")]

    if marker_exists:
        # Маркер профиля мог быть создан раньше (в т.ч. до фикса реестровых
        # ключей ниже), когда winetricks уже засчитал dotnet-verb как успешный,
        # хотя реальные файлы .NET не были установлены (см. комментарий у
        # _verb_really_installed). Если для этого профиля нет dotnet-verb-ов,
        # или .NET реально стоит на диске — маркеру можно доверять полностью.
        if not dotnet_verbs or _dotnet_actually_installed(prefix_path):
            return True
        # Иначе — не возвращаем True сразу, а продолжаем ниже и переустанавливаем
        # именно недостающие dotnet-verb-ы, не трогая остальные (уже отмеченные
        # маркером и реально установленные) verb-ы профиля.

    run_env = dict(env)
    # winetricks phones home to check its own version on every run; if the network
    # is slow/unreachable this can stall the whole install for a long time.
    run_env["WINETRICKS_LATEST_VERSION_CHECK"] = "disabled"

    # Shared deadline across every verb in this call: a verb that uses up most
    # of the budget leaves the rest less time rather than none, but every
    # remaining verb still gets attempted individually instead of being
    # skipped as a block.
    deadline = time.monotonic() + timeout

    ok = True
    with open(log_path, "a", encoding="utf-8") as log_file:
        win_version = profile.get("win_version")
        if win_version:
            _run_with_timeout(
                ["umu-run", "reg", "add", r"HKCU\Software\Wine", "/v", "Version",
                 "/d", win_version, "/f"],
                run_env, log_file, 60, cancel_event,
            )  # best-effort; a failure here shouldn't block winetricks below

        verbs = profile.get("winetricks") or []
        if verbs and shutil.which("winetricks"):
            installed = _list_installed_verbs(run_env)
            for verb in verbs:
                # Проверяем через _verb_really_installed, а не голым
                # "verb in installed": для dotnet-verb-ов запись в
                # winetricks.log недостаточна (см. её докстринг) — нужно
                # ещё реальное наличие файла .NET на диске. Это и есть
                # механизм самовосстановления: если в прошлый раз verb был
                # ложно засчитан как успешный, здесь мы это обнаружим и
                # переустановим, без ручного вмешательства пользователя.
                if _verb_really_installed(prefix_path, verb, installed):
                    log_file.write(f"[skip: {verb} already installed]\n")
                    continue
                if (
                    verb.startswith("dotnet")
                    and verb in installed
                    and _dotnet_actually_installed(prefix_path)
                    and not _installroot_configured(prefix_path)
                ):
                    # Файлы .NET реально стоят, не хватает только InstallRoot —
                    # чиним точечно, без переустановки всего .NET заново.
                    for reg_path, install_dir in (
                        (r"HKLM\Software\Microsoft\.NETFramework",
                         r"C:\windows\Microsoft.NET\Framework64\\"),
                        (r"HKLM\Software\Wow6432Node\Microsoft\.NETFramework",
                         r"C:\windows\Microsoft.NET\Framework\\"),
                    ):
                        _run_with_timeout(
                            ["umu-run", "reg", "add", reg_path, "/v", "InstallRoot",
                             "/d", install_dir, "/f"],
                            run_env, log_file, 30, cancel_event,
                        )
                    if _installroot_configured(prefix_path):
                        log_file.write(f"[fixed: InstallRoot for {verb}]\n")
                        continue
                    log_file.write(f"[{verb}: InstallRoot still not configured after fix attempt]\n")
                    ok = False
                    continue
                if verb in installed:
                    log_file.write(
                        f"[{verb} in winetricks.log but files missing on disk — reinstalling]\n"
                    )
                    # winetricks сам проверяет свой log и молча пропускает verb,
                    # если тот уже там числится ("already installed, skipping"),
                    # независимо от реального состояния файлов — поэтому нужно
                    # убрать именно эту строку из лога перед повторным вызовом,
                    # иначе следующая попытка установки ничего не сделает.
                    winetricks_log = os.path.join(prefix_path, "pfx", "winetricks.log")
                    try:
                        with open(winetricks_log, "r", encoding="utf-8", errors="ignore") as wf:
                            lines = [ln for ln in wf if ln.strip() != verb]
                        with open(winetricks_log, "w", encoding="utf-8") as wf:
                            wf.writelines(lines)
                    except OSError as exc:
                        log_file.write(f"[couldn't clean winetricks.log: {exc}]\n")

                if (cancel_event is not None and cancel_event.is_set()):
                    log_file.write("[cancelled before all verbs installed]\n")
                    ok = False
                    break

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    log_file.write(f"[timed out before installing: {verb}]\n")
                    ok = False
                    break

                if verb.startswith("dotnet"):
                    # Proton заранее создаёт в реестре записи о "своей" версии
                    # .NET Framework Setup. dotnet-инсталлятор их видит,
                    # решает "уже стоит более новая версия" и завершается с
                    # кодом успеха, НИЧЕГО реально не установив — а winetricks
                    # всё равно засчитывает verb как выполненный и пишет его
                    # в winetricks.log. Итог: verb "готов" по логу, а реальных
                    # файлов .NET нет, и xalia.exe продолжает требовать
                    # установку при каждом запуске (см. Winetricks#2367).
                    # Удаляем эти ключи перед установкой, best-effort — их
                    # отсутствие не должно блокировать сам verb ниже.
                    for hive_key in (
                        r"HKLM\Software\Wow6432Node\Microsoft\NET Framework Setup\NDP\v4",
                        r"HKLM\Software\Wow6432Node\Microsoft\NET Framework Setup\NDP\v3.5",
                    ):
                        _run_with_timeout(
                            ["umu-run", "reg", "delete", hive_key, "/f"],
                            run_env, log_file, 30, cancel_event,
                        )

                # One verb per subprocess call: if this verb fails or times out,
                # every other verb (already-installed or not-yet-attempted) is
                # still tried on its own, rather than the whole batch aborting.
                verb_ok = _run_with_timeout(
                    ["umu-run", "winetricks", "-q", verb],
                    run_env, log_file, remaining, cancel_event,
                )
                if verb_ok and verb.startswith("dotnet"):
                    if not _dotnet_actually_installed(prefix_path):
                        # winetricks вернул успех, но реального файла всё ещё нет —
                        # значит инсталлятор опять молча пропустил установку
                        # (см. комментарий выше про NDP\v4/v3.5). Не считаем verb
                        # установленным, чтобы следующий запуск программы честно
                        # попробовал снова, а не оставлял пользователя навсегда с
                        # диалогом xalia.exe про отсутствующий .NET.
                        log_file.write(
                            f"[{verb} reported success but {_DOTNET_MARKER_FILE} still missing]\n"
                        )
                        verb_ok = False
                    else:
                        # Файлы .NET на месте, но приложения (в т.ч. xalia.exe)
                        # находят их через реестровый ключ InstallRoot, который
                        # dotnet-инсталлятор под Wine прописывает не всегда —
                        # без него любое .NET-приложение в префиксе падает с
                        # "Please set registry key ...\.NETFramework\InstallRoot
                        # to point to the .NET Framework install location",
                        # даже когда сами файлы .NET реально установлены
                        # (распространённый, отдельно задокументированный
                        # баг именно этого ключа, а не факта установки).
                        # Прописываем оба view реестра (32- и 64-битный),
                        # т.к. разным .NET-приложениям нужен свой.
                        for reg_path, install_dir in (
                            (r"HKLM\Software\Microsoft\.NETFramework",
                             r"C:\windows\Microsoft.NET\Framework64\\"),
                            (r"HKLM\Software\Wow6432Node\Microsoft\.NETFramework",
                             r"C:\windows\Microsoft.NET\Framework\\"),
                        ):
                            _run_with_timeout(
                                ["umu-run", "reg", "add", reg_path, "/v", "InstallRoot",
                                 "/d", install_dir, "/f"],
                                run_env, log_file, 30, cancel_event,
                            )
                        if not _installroot_configured(prefix_path):
                            # Не удалось прописать InstallRoot — не считаем
                            # verb полностью готовым, чтобы следующий запуск
                            # честно попробовал снова, а не оставлял диалог
                            # xalia.exe навсегда.
                            log_file.write(f"[{verb}: InstallRoot still not configured]\n")
                            verb_ok = False
                if verb_ok:
                    installed.add(verb)
                else:
                    log_file.write(f"[failed: {verb}]\n")
                    ok = False
                    # keep going — later verbs are independent and may still succeed

    if ok:
        try:
            os.makedirs(prefix_path, exist_ok=True)
            open(marker, "w").close()
        except Exception:
            pass
    return ok