# Repository map

The map answers one question fast: **which file do I open to change X?** Read the map for the area you're touching — not the whole repo, and not a blind grep.

| Area | File | Covers |
|---|---|---|
| Backend | [`backend.md`](backend.md) | FastAPI service — routers, services, models, config |
| Frontend | [`frontend.md`](frontend.md) | Next.js app — pages, components, client-side logic |
| Infrastructure | [`infra.md`](infra.md) | Docker, database bootstrap, scripts, environment |

Split by area on purpose: a frontend change should never pull backend rows into context.

## Format

One row per file. The description says **what the file does and what lives in it** — the symbols someone would search for — in one line. Not prose, not a changelog.

```
| `backend/app/routers/health.py` | `GET /health` (liveness), `GET /health/db` (database probe) |
```

Rules:
- Path in backticks, repo-relative, forward slashes. `scripts/check_map.py` parses this and will fail on anything else.
- One line per file. If a file needs a paragraph, it is doing too much — split the file, not the row.
- Group rows under a `###` heading per directory once an area passes ~20 files.
- Generated files (`node_modules/`, `.next/`, lock files, empty `__init__.py`) are never mapped.

## Keeping it accurate — this is the part that matters

A stale map is worse than no map: it sends the next agent to a file that moved. So the map is not maintained by good intentions, it is checked:

```bash
python scripts/check_map.py
```

It reports files missing from the map, rows pointing at deleted files, rows filed under the wrong area, and new top-level directories it was never taught to scan. Exit code 1 means drift.

You do not have to remember to run it: `.githooks/pre-commit` blocks the commit on drift, enabled once per clone with `git config core.hooksPath .githooks`.

**The rule:** add, rename, move, or delete a file → update the map row **in the same commit**. A change is not done while the check fails.

Adding a whole new top-level directory (say `worker/`) needs one extra step: add its patterns to `AREAS` and its name to `KNOWN_TOP_LEVEL` in the script, and give it a `docs/map/<area>.md`. The script refuses to pass until you do — otherwise it would report "in sync" while ignoring every file in there.
