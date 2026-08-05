#!/usr/bin/env python3
"""Detect drift between the repository and the maps in docs/map/.

A map nobody enforces goes stale, and a stale map is worse than none: it sends
agents to files that moved. This script is the enforcement.

Reports two kinds of drift:
  - unmapped: a source file exists but no map row points at it
  - stale:    a map row points at a file that no longer exists

Usage:
    python scripts/check_map.py

Exits 1 on drift, 0 when clean. Standard library only; no install needed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_DIR = REPO_ROOT / "docs" / "map"

# First match wins, so list the explicit infra paths before the broad globs.
AREAS: list[tuple[str, list[str]]] = [
    (
        "infra",
        [
            "docker-compose.yml",
            ".env.example",
            "backend/Dockerfile",
            "frontend/Dockerfile",
            "db/init/*.sql",
            "scripts/*.py",
            ".githooks/*",
            ".github/workflows/*.yml",
        ],
    ),
    (
        "backend",
        [
            "backend/**/*.py",
            "backend/requirements*.txt",
            "backend/pytest.ini",
        ],
    ),
    (
        "frontend",
        [
            "frontend/**/*.ts",
            "frontend/**/*.tsx",
            "frontend/**/*.css",
            "frontend/**/*.mjs",
            "frontend/package.json",
            "frontend/tsconfig.json",
        ],
    ),
]

# Directory names that never contain files worth mapping.
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

# Generated or lock files: real, but nothing an agent needs a description of.
EXCLUDED_NAMES = {"next-env.d.ts", "package-lock.json"}

# Top-level directories AREAS already covers, plus those holding no mappable
# source. A new directory outside this set means the patterns above have a hole:
# the script would happily report "in sync" while ignoring every file in it.
# That silent pass is the failure mode this guard exists to prevent.
KNOWN_TOP_LEVEL = {
    "backend",
    "frontend",
    "db",
    "scripts",
    ".githooks",
    "docs",
    ".cursor",
    ".claude",
    ".github",
    ".git",
    "postgres-data",
}

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".mjs", ".sql", ".yml", ".yaml"}

# Matches a table row whose first cell is a backticked path: | `path/to/file` | ... |
MAP_ROW = re.compile(r"^\|\s*`([^`]+)`")


def is_excluded(path: Path) -> bool:
    if path.name in EXCLUDED_NAMES:
        return True
    if EXCLUDED_DIRS.intersection(path.parts):
        return True
    # Empty package markers carry no information worth a map row.
    return path.name == "__init__.py" and path.stat().st_size == 0


def files_on_disk() -> dict[str, str]:
    """Map every mappable file to the area it belongs to."""
    found: dict[str, str] = {}
    for area, patterns in AREAS:
        for pattern in patterns:
            for path in REPO_ROOT.glob(pattern):
                if not path.is_file() or is_excluded(path):
                    continue
                rel = path.relative_to(REPO_ROOT).as_posix()
                found.setdefault(rel, area)
    return found


def files_in_maps() -> dict[str, str]:
    """Map every path listed in docs/map/*.md to the map file that lists it."""
    listed: dict[str, str] = {}
    if not MAP_DIR.is_dir():
        sys.exit(f"error: {MAP_DIR.relative_to(REPO_ROOT)} does not exist")
    for map_file in sorted(MAP_DIR.glob("*.md")):
        if map_file.stem == "README":
            continue
        for line in map_file.read_text(encoding="utf-8").splitlines():
            match = MAP_ROW.match(line)
            if match:
                listed.setdefault(match.group(1).strip(), map_file.stem)
    return listed


def unknown_areas() -> list[str]:
    """Top-level directories holding source that no AREAS pattern reaches."""
    found = []
    for entry in sorted(REPO_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in KNOWN_TOP_LEVEL or entry.name in EXCLUDED_DIRS:
            continue
        has_source = any(
            path.is_file() and path.suffix in SOURCE_SUFFIXES and not is_excluded(path)
            for path in entry.rglob("*")
        )
        if has_source:
            found.append(entry.name)
    return found


def main() -> int:
    unknown = unknown_areas()
    if unknown:
        print("New top-level directories the map does not cover:")
        for name in unknown:
            print(f"  {name}/")
        print()
        print(
            "Teach the script about them: add patterns to AREAS and a name to\n"
            "KNOWN_TOP_LEVEL in scripts/check_map.py, then create the matching\n"
            "docs/map/ file. Until then their files are invisible to the map."
        )
        return 1

    on_disk = files_on_disk()
    in_maps = files_in_maps()

    unmapped = sorted(set(on_disk) - set(in_maps))
    stale = sorted(set(in_maps) - set(on_disk))
    misfiled = sorted(
        path for path in set(on_disk) & set(in_maps) if on_disk[path] != in_maps[path]
    )

    if unmapped:
        print("Missing from the map (add a row describing what the file does):")
        for path in unmapped:
            print(f"  {path}  ->  docs/map/{on_disk[path]}.md")
        print()

    if stale:
        print("Listed in the map but not on disk (remove or fix the row):")
        for path in stale:
            print(f"  {path}  (in docs/map/{in_maps[path]}.md)")
        print()

    if misfiled:
        print("Listed in the wrong area map (move the row):")
        for path in misfiled:
            print(f"  {path}  is in {in_maps[path]}.md, belongs in {on_disk[path]}.md")
        print()

    if unmapped or stale or misfiled:
        print("Map is out of date. Fix it in the same commit as the code change.")
        return 1

    print(f"Map is in sync: {len(on_disk)} files mapped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
