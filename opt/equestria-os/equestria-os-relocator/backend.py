"""CLI backend for privileged file relocation.

Usage:
    python3 backend.py src1 [src2 ...] --dest /path/to/destination

Exit codes:
    0  — success
    1  — error (details on stderr)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core


def main():
    args = sys.argv[1:]
    if "--dest" not in args:
        sys.stderr.write("Usage: backend.py src1 [src2 ...] --dest DEST\n")
        sys.exit(1)

    dest_idx = args.index("--dest")
    sources = args[:dest_idx]
    destination = args[dest_idx + 1] if dest_idx + 1 < len(args) else ""

    if not sources or not destination:
        sys.stderr.write("Sources and destination are required.\n")
        sys.exit(1)

    total = len(sources)
    errors = []
    symlinks = 0

    for i, src in enumerate(sources, 1):
        results = core.relocate([src], destination, create_symlink=True)
        r = results[0]
        if r.error:
            errors.append(f"{r.source}: {r.error}")
        else:
            if r.symlink_created:
                symlinks += 1
        sys.stdout.write(f"PROGRESS {i} {total}\n")
        sys.stdout.flush()

    if errors:
        for e in errors:
            sys.stderr.write(e + "\n")
        sys.exit(1)

    sys.stdout.write(f"OK {total} {symlinks}\n")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
