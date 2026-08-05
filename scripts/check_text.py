#!/usr/bin/env python3
"""Ban typographic dashes from the repository.

Em dashes and en dashes are forbidden here: they read as machine-written, they
are a nuisance to type, and they are trivially replaceable by a comma, a colon,
parentheses, or a plain hyphen. This applies everywhere, including user-facing
Polish copy.

Usage:
    python scripts/check_text.py

Exits 1 when a banned character is found, 0 when clean. Standard library only.

The characters are written as escapes on purpose, so this file does not trip
its own check.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BANNED = {
    "\u2014": "em dash",
    "\u2013": "en dash",
    "\u2015": "horizontal bar",
}

SCANNED_SUFFIXES = {
    ".md",
    ".mdc",
    ".py",
    ".ts",
    ".tsx",
    ".css",
    ".yml",
    ".yaml",
    ".sql",
    ".json",
    ".mjs",
    ".txt",
}

# Text files worth scanning that carry no suffix.
EXTRA_FILES = {"Dockerfile", "pre-commit", ".env.example", ".gitignore", ".cursorignore"}

EXCLUDED_DIRS = {
    "node_modules",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    "out",
    "coverage",
    "htmlcov",
}
EXCLUDED_NAMES = {"package-lock.json", "next-env.d.ts"}


def scanned_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if EXCLUDED_DIRS.intersection(path.parts) or path.name in EXCLUDED_NAMES:
            continue
        if path.suffix in SCANNED_SUFFIXES or path.name in EXTRA_FILES:
            files.append(path)
    return sorted(files)


def main() -> int:
    hits: list[str] = []
    for path in scanned_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            for char, name in BANNED.items():
                column = line.find(char)
                if column != -1:
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    hits.append(f"  {rel}:{number}:{column + 1}  {name}")

    if hits:
        print(f"Banned typographic characters found ({len(hits)}):")
        for hit in hits:
            print(hit)
        print()
        print("Replace with a comma, a colon, parentheses, or a plain hyphen '-'.")
        return 1

    print("No banned typographic characters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
