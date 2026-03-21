"""
Тест парсинга строк fstab без реального железа.
Запуск: python3 test_fstab_parse.py
"""

TEST_LINES = [
    # (описание, строка fstab, ожидаемая точка монтирования, ожидаемые опции)
    (
        "Обычный путь без пробелов",
        "UUID=aaaa-bbbb\t/mnt/data\text4\tdefaults,noatime\t0\t2",
        "/mnt/data",
        "defaults,noatime",
    ),
    (
        "Путь с пробелами (Documents Photo and Video)",
        "UUID=cccc-dddd\t/run/media/lucial/Documents Photo and Video\tntfs-3g\tuid=1000,gid=1000,fmask=022,dmask=022,noatime,nofail\t0\t2",
        "/run/media/lucial/Documents Photo and Video",
        "uid=1000,gid=1000,fmask=022,dmask=022,noatime,nofail",
    ),
    (
        "Путь с \\040 (fstab-экранирование пробелов)",
        "UUID=eeee-ffff\t/run/media/lucial/Documents\\040Photo\\040and\\040Video\tntfs-3g\tdefaults,nofail\t0\t2",
        "/run/media/lucial/Documents Photo and Video",
        "defaults,nofail",
    ),
    (
        "Один пробел в названии",
        "UUID=1111-2222\t/mnt/My Drive\tbtrfs\tcompress=zstd,noatime\t0\t2",
        "/mnt/My Drive",
        "compress=zstd,noatime",
    ),
    (
        "swap (без точки монтирования)",
        "UUID=3333-4444\tnone\tswap\tsw\t0\t0",
        "none",
        "sw",
    ),
]


def parse_fstab_line(line):
    """Та же логика, что теперь в disk_app.py."""
    raw_parts = line.strip().split()
    if len(raw_parts) >= 6:
        mount_point = " ".join(raw_parts[1:-4]).replace("\\040", " ")
        options = raw_parts[-3]
    elif len(raw_parts) == 5:
        mount_point = raw_parts[1].replace("\\040", " ")
        options = raw_parts[3]
    elif len(raw_parts) >= 4:
        mount_point = raw_parts[1].replace("\\040", " ")
        options = raw_parts[3]
    else:
        return None, None
    return mount_point, options


def run_tests():
    passed = 0
    failed = 0
    for desc, line, expected_mp, expected_opts in TEST_LINES:
        mp, opts = parse_fstab_line(line)
        ok_mp   = mp   == expected_mp
        ok_opts = opts == expected_opts
        status = "OK" if (ok_mp and ok_opts) else "FAIL"
        if ok_mp and ok_opts:
            passed += 1
        else:
            failed += 1
        print(f"[{status}] {desc}")
        if not ok_mp:
            print(f"       mount_point: получили={mp!r}")
            print(f"                    ожидали ={expected_mp!r}")
        if not ok_opts:
            print(f"       options:     получили={opts!r}")
            print(f"                    ожидали ={expected_opts!r}")

    print(f"\nИтого: {passed} прошло, {failed} упало")


if __name__ == "__main__":
    run_tests()
