"""Check the prose in this repository against the house style.

Three rules, applied to every tracked text file:

    1. No em dashes or en dashes used as punctuation. Use a comma, a colon,
       or a full stop.
    2. No emoji or decorative symbols.
    3. No filler vocabulary. The list below is the set of words and phrases
       that pad a sentence without adding information.

Run it with `python scripts/check_prose.py`. It exits non-zero on any finding,
so it can sit in a pre-commit hook or in CI next to `check_deck.py`.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories that hold generated or third-party content.
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "exports",
    "assets",
}

TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".txt", ".html", ".scss", ".css", ".toml", ".cfg"}

# Filler and stock phrasing. Each entry is matched case-insensitively on a word
# boundary. Keep this list short and defensible: every entry should be a word
# that can be deleted or replaced without losing meaning.
FILLER = [
    "delve",
    "leverage",
    "seamless",
    "seamlessly",
    "crucially",
    "moreover",
    "furthermore",
    "notably",
    "importantly",
    "essentially",
    "basically",
    "simply put",
    "needless to say",
    "it is worth noting",
    "it's worth noting",
    "in today's",
    "in the realm of",
    "in the landscape of",
    "a testament to",
    "a game changer",
    "game-changing",
    "cutting-edge",
    "state-of-the-art",
    "unlock the",
    "empower",
    "elevate",
    "dive into",
    "deep dive into",
    "navigate the complexities",
    "harness the",
    "pivotal",
    "paramount",
    "myriad",
    "plethora",
    "robust and",
    "powerful and",
    "comprehensive and",
    "tapestry",
    "underscore",
    "underscores",
    "at the end of the day",
    "when it comes to",
]

DASHES = {
    "—": "em dash",
    "–": "en dash",
    "―": "horizontal bar",
}


def is_emoji(char: str) -> bool:
    """Emoji and decorative pictographs, excluding ordinary punctuation."""
    code = ord(char)
    if code < 0x2000:
        return False
    ranges = [
        (0x1F300, 0x1FAFF),  # pictographs, emoticons, symbols
        (0x1F000, 0x1F0FF),  # tiles and cards
        (0x2600, 0x27BF),  # misc symbols and dingbats
        (0x2B00, 0x2BFF),  # arrows and geometric shapes
        (0xFE00, 0xFE0F),  # variation selectors
    ]
    return any(low <= code <= high for low, high in ranges)


def tracked_files() -> list[Path]:
    """Every text file worth checking, excluding this file.

    This module has to spell out the words it bans, so scanning it would report
    the rule list as a violation of itself.
    """
    this_file = Path(__file__).resolve()
    files = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.resolve() == this_file:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(PROJECT_ROOT).parts):
            continue
        files.append(path)
    return sorted(files)


def check(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return findings

    for number, line in enumerate(lines, start=1):
        for char, name in DASHES.items():
            if char in line:
                findings.append((number, name, line.strip()[:90]))

        for char in line:
            if is_emoji(char):
                label = unicodedata.name(char, f"U+{ord(char):04X}")
                findings.append((number, f"emoji ({label})", line.strip()[:90]))
                break

        lowered = line.lower()
        for phrase in FILLER:
            pattern = r"\b" + re.escape(phrase) + r"\b"
            if re.search(pattern, lowered):
                findings.append((number, f"filler ({phrase!r})", line.strip()[:90]))

    return findings


def main() -> int:
    total = 0
    scanned = 0
    for path in tracked_files():
        scanned += 1
        findings = check(path)
        if not findings:
            continue
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        print(f"\n{relative}")
        for number, rule, excerpt in findings:
            print(f"  line {number:>4}  {rule}")
            print(f"             {excerpt}")
            total += 1

    print(f"\nScanned {scanned} files.")
    if total:
        print(f"{total} finding(s).")
        return 1
    print("No findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
