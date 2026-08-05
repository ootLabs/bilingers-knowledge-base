# Project log

Short, dense record of what happened and why. Newest first.

**Read the top 3-5 entries** when picking up work - not the whole file. This is a log, not a manual: durable knowledge belongs in `docs/architecture.md` (decisions), `docs/map/` (where things live), or `docs/conventions.md` (how we write things). If a fact matters in three months, it goes there and gets a pointer here, not a permanent home in this file.

## Format - keep it strict

```
## YYYY-MM-DD - short title
**Done:** what now works, one line.
**Decisions:** what was chosen and why, one line each. Non-obvious only.
**Watch out:** what will bite next time. Omit the line if nothing will.
```

**Cap: 20 entries.** Adding the 21st? Move the oldest to `docs/log-archive/<year>.md` in the same commit. The cap is the point - an unbounded journal is a file nobody reads and every session pays for.

Each entry ≤ 5 lines. Do not narrate process, list files changed (git knows), or restate what the map already says.

---

## 2026-08-05 - branch model: main as production, dev as integration
**Done:** `dev` created from `main`; branch rules rewritten in `AGENTS.md`, `CONTRIBUTING.md`, and the Cursor rules; CI now also triggers on pushes to `dev`. First real CI run on GitHub passed all four jobs in 63s.
**Decisions:** Feature branches cut from `dev` and merge back there; `main` only takes release merges and hotfixes, with `--no-ff` so its log reads as releases rather than individual commits.
**Watch out:** After a `hotfix/` merges to `main`, merge `main` back into `dev` at once or the next release reverts the fix. Branch protection and the default branch are GitHub settings nobody can commit; until they are set, CI is advisory.

## 2026-08-05 - test suite, coverage gates, and CI
**Done:** 23 backend tests (unit, API, 2 integration) at 100% coverage with a 90% gate; 8 frontend tests via Vitest plus a typecheck; `scripts/smoke_test.py` drives the running stack over HTTP; `.github/workflows/ci.yml` runs all of it on every PR; `docs/testing.md` explains the layers; `frontend/package-lock.json` finally exists so Docker and CI both use `npm ci`.
**Decisions:** Integration tests skip rather than fail without a database, so the suite is usable with nothing running, while CI always provides real PostgreSQL. Frontend branch-coverage threshold is set lower than the rest because v8 counts unreachable branches in transpiled JSX, and faking tests to hit a number hides more than it reveals.
**Watch out:** GitHub service containers do not run `db/init/`, so CI applies it with psql; a new bootstrap file needs no change, but a move away from `db/init/` does. Branch protection making the four jobs required is a repo setting nobody can commit, and without it CI is only advice.

## 2026-08-05 - em dashes banned repo-wide
**Done:** 160 em/en dashes removed from 25 files; `scripts/check_text.py` bans them and the pre-commit hook now runs it alongside the map check.
**Decisions:** Enforce rather than document, same reasoning as the map: a style rule nobody checks is a style rule agents forget by the third session. The ban covers Polish UI copy too, despite Polish typography normally using an en dash.
**Watch out:** `check_text.py` stores the banned characters as `\u` escapes so it does not flag its own source. Keep it that way when editing. Arrow characters were left alone; they carry meaning as notation rather than being decorative punctuation. Say so if you want them gone too.

## 2026-08-05 - map check enforced by a pre-commit hook
**Done:** `.githooks/pre-commit` blocks a commit while the map disagrees with the repo (enable per clone: `git config core.hooksPath .githooks`); `check_map.py` now also fails on a new top-level directory it was never taught to scan.
**Decisions:** Enforce at commit time rather than trusting the definition of done - an unenforced map decays, and a wrong map costs more than no map. The unknown-directory guard turns a silent pass into a loud failure, which was the script's one remaining blind spot.
**Watch out:** Hooks are not shared by git, so every clone needs the `core.hooksPath` line - it is in the README and CONTRIBUTING setup steps.

## 2026-08-05 - agent-facing docs restructure
**Done:** `AGENTS.md` is now the single source of rules (`CLAUDE.md` imports it, `.cursor/rules/` points at it); `docs/map/` splits the repo map by area; `scripts/check_map.py` enforces it; `AI_NOTES.md` replaced by this capped log.
**Decisions:** Split maps by area so a frontend change never loads backend rows - startup context dropped from ~2 370 to ~1 500 tokens with everything else pulled on demand. Map accuracy is enforced by a script, not by good intentions, because an unenforced map goes stale and then actively misleads.
**Watch out:** `check_map.py` scans a hardcoded `AREAS` list - a new top-level source directory needs patterns added there (the guard added the same day makes this fail loudly instead of silently).

## 2026-08-05 - project scaffold
**Done:** Docker Compose with three services (Next.js, FastAPI, PostgreSQL) verified running; health endpoints incl. database probe; README, CONTRIBUTING, architecture, conventions, and the `docs/llm/` design wiki.
**Decisions:** Skeleton only - no vector DB, no LLM SDK, no model calls, by explicit request. Plain Postgres; evaluate `pgvector` in the same container if retrieval needs it, rather than adding a fourth service. Bootstrap SQL instead of a migration tool until the first real schema change.
**Watch out:** No `frontend/package-lock.json`, so the image runs `npm install`, not `npm ci` - builds are not reproducible until a lockfile is committed.
