import re

RELEASE = re.compile(r"(\d+)\.(\d+)\.(\d+)([abfp])(\d+)(?:c(\d+))?")


def version_key(version):
    # Unity orders prereleases before the final build and patch releases after it.
    match = RELEASE.fullmatch(version)
    if not match:
        return ()
    major, minor, patch, stage, build, china = match.groups()
    return int(major), int(minor), int(patch), "abfp".index(stage), int(build), int(china or 0)


def release_title(version):
    """Unity's marketing name of a release: 6000.6.9f1 -> Unity 6.6, 2022.3.1f1 -> Unity 2022.3."""
    match = RELEASE.fullmatch(version)
    if not match:
        return f"Unity {version}"
    major, minor = int(match.group(1)), match.group(2)
    return f"Unity {major // 1000 if major >= 6000 else major}.{minor}"
