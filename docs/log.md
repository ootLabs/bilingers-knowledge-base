# Project log

Short, dense record of what happened and why. Newest first.

**Read the top 3–5 entries** when picking up work — not the whole file. This is a log, not a manual: durable knowledge belongs in `docs/architecture.md` (decisions), `docs/map/` (where things live), or `docs/conventions.md` (how we write things). If a fact matters in three months, it goes there and gets a pointer here, not a permanent home in this file.

## Format — keep it strict

```
## YYYY-MM-DD — short title
**Done:** what now works, one line.
**Decisions:** what was chosen and why, one line each. Non-obvious only.
**Watch out:** what will bite next time. Omit the line if nothing will.
```

**Cap: 20 entries.** Adding the 21st? Move the oldest to `docs/log-archive/<year>.md` in the same commit. The cap is the point — an unbounded journal is a file nobody reads and every session pays for.

Each entry ≤ 5 lines. Do not narrate process, list files changed (git knows), or restate what the map already says.

---

## 2026-08-05 — map check enforced by a pre-commit hook
**Done:** `.githooks/pre-commit` blocks a commit while the map disagrees with the repo (enable per clone: `git config core.hooksPath .githooks`); `check_map.py` now also fails on a new top-level directory it was never taught to scan.
**Decisions:** Enforce at commit time rather than trusting the definition of done — an unenforced map decays, and a wrong map costs more than no map. The unknown-directory guard turns a silent pass into a loud failure, which was the script's one remaining blind spot.
**Watch out:** Hooks are not shared by git, so every clone needs the `core.hooksPath` line — it is in the README and CONTRIBUTING setup steps.

## 2026-08-05 — agent-facing docs restructure
**Done:** `AGENTS.md` is now the single source of rules (`CLAUDE.md` imports it, `.cursor/rules/` points at it); `docs/map/` splits the repo map by area; `scripts/check_map.py` enforces it; `AI_NOTES.md` replaced by this capped log.
**Decisions:** Split maps by area so a frontend change never loads backend rows — startup context dropped from ~2 370 to ~1 500 tokens with everything else pulled on demand. Map accuracy is enforced by a script, not by good intentions, because an unenforced map goes stale and then actively misleads.
**Watch out:** `check_map.py` scans a hardcoded `AREAS` list — a new top-level source directory needs patterns added there (the guard added the same day makes this fail loudly instead of silently).

## 2026-08-05 — project scaffold
**Done:** Docker Compose with three services (Next.js, FastAPI, PostgreSQL) verified running; health endpoints incl. database probe; README, CONTRIBUTING, architecture, conventions, and the `docs/llm/` design wiki.
**Decisions:** Skeleton only — no vector DB, no LLM SDK, no model calls, by explicit request. Plain Postgres; evaluate `pgvector` in the same container if retrieval needs it, rather than adding a fourth service. Bootstrap SQL instead of a migration tool until the first real schema change.
**Watch out:** No `frontend/package-lock.json`, so the image runs `npm install`, not `npm ci` — builds are not reproducible until a lockfile is committed.
