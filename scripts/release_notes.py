#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md, for the GitHub release notes.

    python scripts/release_notes.py v0.1.0

The section starts at a heading like "## 0.1.0 - 2026-11-01" (or "## [0.1.0] - ...") and runs to the next "## " heading. A clear error and exit
status 1 when the version is missing, empty, or its heading still says "unreleased draft" (set the real date before tagging).
"""
import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


class ReleaseNotesError(Exception):
    pass


def extract(text: str, version: str) -> str:
    version = version.strip().removeprefix("v").removeprefix("V")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise ReleaseNotesError(f"'{version}' is not a version like 1.2.3 (a tag is written v1.2.3).")
    heading = re.compile(rf"^##\s+\[?{re.escape(version)}\]?(?:\s*[-\u2013\u2014]\s*(.*))?\s*$")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ReleaseNotesError(f"CHANGELOG.md has no section headed '## {version} - <date>'. Add one before tagging v{version}.")
    suffix = heading.match(lines[start]).group(1) or ""
    if "unreleased" in suffix.lower() or "draft" in suffix.lower():
        raise ReleaseNotesError(f"The heading for {version} still says '{suffix}'. Replace it with the release date (YYYY-MM-DD) before tagging.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = "\n".join(lines[start + 1 : end]).strip()
    if not body:
        raise ReleaseNotesError(f"The section for {version} in CHANGELOG.md is empty.")
    return body + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/release_notes.py v1.2.3", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(extract(CHANGELOG.read_text(encoding="utf-8"), argv[1]))
    except (ReleaseNotesError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
