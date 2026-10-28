#!/usr/bin/env python3
"""Check that relative links and images in the Markdown files point at files that exist.

    python scripts/check_links.py            # README.md, CONTRIBUTING.md, SECURITY.md, CHANGELOG.md and docs/**/*.md

Web links are not fetched (no network). A "#section" part is checked against the target file's headings. Links inside code are ignored.
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"""(?:\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\))|(?:(?:src|href)=["']([^"']+)["'])""")
SKIP = ("http://", "https://", "mailto:", "tel:", "data:", "//")


def slug(heading: str) -> str:
    text = re.sub(r"[`*_]|<[^>]+>|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", heading).strip().lower()
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", text))


def anchors(path: Path) -> set[str]:
    found, in_code = set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code and (m := re.match(r"#{1,6}\s+(.*)", line)):
            found.add(slug(m.group(1)))
    return found


def strip_code(text: str) -> str:
    text = re.sub(r"^(\s*)```.*?^\1```", "", text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", text)


def markdown_files() -> list[Path]:
    files = [ROOT / n for n in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "CODE_OF_CONDUCT.md")]
    files += sorted((ROOT / "docs").rglob("*.md"))
    return [f for f in files if f.exists()]


def check(files: list[Path] | None = None) -> list[str]:
    problems = []
    for md in files or markdown_files():
        for match in LINK.finditer(strip_code(md.read_text(encoding="utf-8"))):
            target = match.group(1) or match.group(2)
            if target.startswith(SKIP):
                continue
            raw, _, fragment = target.partition("#")
            dest = md if not raw else (md.parent / unquote(raw)).resolve()
            where = md.relative_to(ROOT)
            if raw and not dest.exists():
                problems.append(f"{where}: {target} does not exist")
            elif fragment and dest.suffix == ".md" and dest.exists() and slug(unquote(fragment)) not in anchors(dest):
                problems.append(f"{where}: {target} has no such heading")
    return problems


if __name__ == "__main__":
    bad = check()
    print("\n".join(bad) if bad else "All relative links resolve.")
    sys.exit(1 if bad else 0)
