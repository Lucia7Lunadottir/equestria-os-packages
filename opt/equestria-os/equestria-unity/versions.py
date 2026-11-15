import re

RELEASE = re.compile(r"(\d+)\.(\d+)\.(\d+)([abfp])(\d+)(?:c(\d+))?")


def version_key(version):
    # Unity orders prereleases before the final build and patch releases after it.
    match = RELEASE.fullmatch(version)
    if not match:
        return ()
    major, minor, patch, stage, build, china = match.groups()
    return int(major), int(minor), int(patch), "abfp".index(stage), int(build), int(china or 0)
