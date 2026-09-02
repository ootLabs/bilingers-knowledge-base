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

## 2026-09-02 - chat UI states: loading, error, empty, limit (T-63)
**Done:** `/chat` stops being a placeholder route: a question box posts to `POST /chat` through the new `lib/api-client.ts`, and `app/chat/ChatPanel.tsx` drives the four states. `components/StatusMessage.tsx` is the shared "what happened plus one way onward" block reused by all five state screens, including the new `app/not-found.tsx` (404) and `app/error.tsx` (500). Copy is Polish, in `pl.ts`. 63 frontend tests pass, typecheck and production build clean.
**Decisions:** Every HTTP failure collapses into one of four `ChatFailure` keys before any component sees it, and a failed response's body is never read (it can name the provider or quote the system prompt). `app/error.tsx` deliberately never binds the `Error` Next hands it, for the same reason. 429 is mapped to the limit state before anything emits it, so the state is reachable and tested ahead of the T-71/T-73 counter. Tone is a left border, never colored text, because `--color-primary` already fails AA on white. The four cards' details are in `docs/architecture.md`.
**Watch out:** The backend streams translation keys one per line, not prose, and a chunk boundary can fall mid-key, so `ChatPanel` buffers whole lines before resolving them and stays in the typing state until something resolves; a key the dictionary lacks is dropped rather than printed, since a raw identifier on screen is exactly what this card forbids, and a stream where nothing resolves fails instead of showing a blank answer. `chat.placeholder_answer.*` in `pl.ts` is an API contract, not our naming: renaming a chunk key silently deletes part of the answer. Scope stops at the states, the conversation itself (history, follow-up threads, T-61's entry screen with its self-description and suggested openers) is T-62, which this card unblocks.

## 2026-08-26 - streaming chat endpoint skeleton (T-12)
**Done:** `POST /chat` accepts `{question, session_token}`, upserts a `ChatSession` by token, writes and commits a `Query` row, then streams a fixed sequence of opaque placeholder chunks (`text/plain`). No retrieval, model call, or orchestration yet. `backend/app/services/`, `backend/app/schemas/` created with their first files. 73 backend tests at 100% coverage.
**Decisions:** `get_or_create_chat_session` only flushes a new row inside a SAVEPOINT (`session.begin_nested()`); `record_query`'s commit makes both it and the query durable together, so a failure between the two never leaves an orphaned session, and a lost insert race is recovered by re-reading the row (and bumping `last_active_at` on it) without discarding any other pending work in the same transaction. `answer` stays NULL throughout: no model runs, and the `queries_answer_requires_kb_version` constraint would reject a non-null answer with no knowledge base version anyway. Service failures raise `ChatServiceUnavailable` (503, infra) or `InvalidChatInput` (422, only for a `DataError` such as a NUL byte); an `IntegrityError` on `record_query`'s commit is deliberately treated as infra (503), since the only constraint it can realistically violate is the `chat_session_id` foreign key, meaning the session vanished mid-request rather than the client sending something wrong. Placeholder chunks are opaque keys, not prose: `docs/llm/i18n.md` bans hardcoded Polish in the backend, and `docs/conventions.md` bans sentences in general, in any language. `session_token` requires 32-64 lowercase hex characters, closing a collision/quota-bypass gap a one-character token would have left open on data marked `PERSONAL_DATA`. Moved `db_session`/`migrated_database` test fixtures from `test_models.py` into `conftest.py`, now matching `SessionLocal`'s `autoflush=False, expire_on_commit=False` so the fixture's semantics match production traffic.
**Watch out:** `ChatRequest` relies on `ConfigDict(str_strip_whitespace=True)` so stripping happens before `max_length` is checked; a hand-rolled `field_validator` would run after Field-level constraints and reject valid, merely padded input. The `Depends(get_session)` session closes as soon as the sync handler returns the `StreamingResponse`, before any bytes are actually sent - harmless while `stream_placeholder_answer` never touches the database, but whatever adds real per-chunk work later (T-40/T-41) needs its own session opened inside the generator, not this one.

## 2026-08-21 - frontend skeleton: routing, i18n layer, design tokens (T-14)
**Done:** App Router routes for landing, chat, quiz, and account (quiz and account are intentionally placeholder); `frontend/lib/i18n/` adds a dependency-free dictionary translation layer, Polish only; design tokens as CSS variables in `globals.css`; mobile first layout with a `:focus-visible` outline; Poppins loaded via `next/font/google`; `SiteHeader` nav shared across routes.
**Decisions:** Custom translation layer instead of a library, a second locale is one file in `lib/i18n/locales/` plus one line in `translations.ts`, and TypeScript rejects a partial translation because its type is derived from `locales/pl.ts`. Brand color, font, and button radius tokens are the Bilingers based palette proposed in T-03, marked provisional in a comment at the top of `globals.css`, not final.
**Watch out:** Provisional tokens will change once T-03's two open client questions land (whose brand the chat is, and which of two conflicting visual variants, live sites vs. 2023/24 Yellow House assets, is current), do not treat current hex values as frozen. `next/font/google` needed a mock in `vitest.setup.ts`, it relies on Next's build pipeline, not Vite's. The `@/*` import alias needed a matching `resolve.alias` in `vitest.config.ts`, tsconfig alone only satisfies `tsc`, not Vitest.

## 2026-08-25 - core data model and Alembic (T-11)
**Done:** Five tables (`users`, `chat_sessions`, `queries`, `knowledge_base_versions`, `knowledge_gaps`) in `backend/app/models/`, under Alembic revision 0001, applied by the backend container before uvicorn starts. 46 backend tests at 100% coverage; verified on a wiped volume and through a full downgrade/upgrade cycle.
**Decisions:** Two acceptance criteria are database constraints rather than conventions: `chat_sessions.user_id` is nullable so anonymous parents are countable (D5), and `queries` carries `CHECK (answer IS NULL OR knowledge_base_version_id IS NOT NULL)` so no answer can outlive knowledge of the base version behind it. Personal-data columns are marked `info=PERSONAL_DATA` and enumerated by `personal_data_columns()`; retention periods are deliberately absent, they wait on B-07. Erasure is designed as scrubbing marked columns, with person-facing foreign keys clearing (`SET NULL`) instead of cascading, so the cost ledger and the unanswered-question queue survive a deletion request.
**Watch out:** `db/init/` is now the health probe only, and Alembic owns application schema. A table added to `db/init/` exists on your machine and nowhere else, because it runs only on an empty volume. `check_map.py` scans `backend/*.ini` (was `backend/pytest.ini`), otherwise `alembic.ini` reported as stale rather than unmapped.

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
