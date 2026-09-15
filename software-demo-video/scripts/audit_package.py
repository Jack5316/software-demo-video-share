#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

from _common import sha256_file


FORBIDDEN_PARTS = {"node_modules", "__pycache__"}
FORBIDDEN_SUFFIXES = {".pyc", ".mov", ".mp4", ".mp3", ".wav", ".png", ".jpg", ".jpeg"}
CONTENT_PATTERNS = [
    re.compile(rb"/Users/[A-Za-z0-9._-]+"),
    re.compile(rb"sk-api-[A-Za-z0-9_-]+"),
    re.compile(rb"(?:TOKEN|API_KEY)\s*=\s*[\"'][^$<{\"']+", re.I),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a packaged .skill archive for generated/private material.")
    parser.add_argument("package")
    args = parser.parse_args()
    reasons: list[str] = []
    files = 0
    with zipfile.ZipFile(args.package) as archive:
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                reasons.append(f"unsafe path: {info.filename}")
                continue
            if info.is_dir():
                continue
            files += 1
            if FORBIDDEN_PARTS & set(path.parts):
                reasons.append(f"forbidden directory: {info.filename}")
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                reasons.append(f"forbidden generated/media file: {info.filename}")
            data = archive.read(info)
            for pattern in CONTENT_PATTERNS:
                if pattern.search(data):
                    reasons.append(f"private/credential-shaped content: {info.filename}")
                    break
    result = {"status": "PASS" if not reasons else "FAIL", "files": files, "package_sha256": sha256_file(Path(args.package)), "reasons": reasons}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not reasons else 2


if __name__ == "__main__":
    raise SystemExit(main())
