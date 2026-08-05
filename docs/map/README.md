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

It reports files missing from the map, rows pointing at deleted files, and rows filed under the wrong area. Exit code 1 means drift.

**The rule:** add, rename, move, or delete a file → update the map row **in the same commit**. Run the check before committing. A change is not done while the check fails.
