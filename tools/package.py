#!/usr/bin/env python3
"""Package the course as a zip a student can download and run.

Includes everything the course needs to run from a folder and leaves out
student state, source PDFs, tests, caches, and version-control files. The
integrity check runs first and the build stops if it fails, so a broken
course is never packaged.

Usage, from the course folder:
    python3 tools/package.py                  # dist/part107-course-<date>.zip
    python3 tools/package.py --allow-incomplete   # while content is still being written
"""

import argparse
import datetime
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXCLUDE_DIRS = {"progress", "tests", "dist", "__pycache__", ".git", ".github"}
EXCLUDE_UNDER = {os.path.join("knowledge-base", "pdfs")}
EXCLUDE_FILES = {".DS_Store"}
EXCLUDE_SUFFIXES = (".pyc", ".pdf")


def wanted(relative):
    parts = relative.split(os.sep)
    if parts[0] in EXCLUDE_DIRS or parts[-1] in EXCLUDE_FILES:
        return False
    if any(relative.startswith(prefix + os.sep) for prefix in EXCLUDE_UNDER):
        return False
    if relative.endswith(EXCLUDE_SUFFIXES):
        return False
    return True


def build(allow_incomplete):
    check = [sys.executable, os.path.join(ROOT, "tools", "check_integrity.py")]
    if allow_incomplete:
        check.append("--allow-incomplete")
    if subprocess.run(check).returncode != 0:
        sys.exit("integrity check failed; nothing packaged")

    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    stamp = datetime.date.today().isoformat()
    out = os.path.join(ROOT, "dist", "part107-course-%s.zip" % stamp)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for name in files:
                path = os.path.join(folder, name)
                relative = os.path.relpath(path, ROOT)
                if not wanted(relative):
                    continue
                info = zipfile.ZipInfo(os.path.join("part107-course", relative))
                info.date_time = datetime.datetime.now().timetuple()[:6]
                info.compress_type = zipfile.ZIP_DEFLATED
                # Keep start.sh executable when the zip is extracted on macOS or Linux.
                info.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
                with open(path, "rb") as handle:
                    archive.writestr(info, handle.read())
                count += 1
    print("packaged %d files into %s" % (count, os.path.relpath(out, ROOT)))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    build(args.allow_incomplete)


if __name__ == "__main__":
    main()
