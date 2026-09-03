# Architecture - Bilingers

> Overview for humans and for the coding agent. Written in English. Keep it short and concrete; update it when the structure changes.

## Overview

A free educational app for parents and carers raising a bilingual child. The user talks to an AI assistant answering **only** from the Bilingual Future Foundation knowledge base, then optionally takes a quiz that can end in a certificate.

Target flow (most of it not built yet): the user opens the app → reads a short intro → picks one of 3-5 suggested starter questions or types their own → the backend retrieves matching passages from the foundation's knowledge base → the model answers from those passages only → the app proposes 3-5 deeper follow-up questions → after some conversation the user can take a ~10-question quiz → passing issues a certificate.

**What exists today:** three containers, health endpoints, the core relational data model with migrations, a stubbed streaming `POST /chat`, a frontend routing skeleton with a Polish-only translation layer and design tokens, and this documentation frame. The chat, quiz, and account routes exist but hold placeholder copy only. Everything about retrieval, real model calls, quiz logic, and certificates is design, not code - see `docs/llm/`.

## Main modules

| Module | Responsibility | Path |
|---|---|---|
| Frontend | UI, conversation view, quiz screens (Polish copy) | `frontend/app/` |
| Frontend API client | The only browser-to-backend call site, and the failure vocabulary every screen reacts to | `frontend/lib/api-client.ts` |
| Backend API | HTTP layer, one router per domain | `backend/app/routers/` |
| Backend config | Environment-driven settings | `backend/app/config.py` |
| Persistence | SQLAlchemy engine + session dependency | `backend/app/db.py` |
| Panel authentication | Editor accounts, roles, sessions, password resets | `backend/app/services/panel_*.py` |
| Data model | Tables, constraints, personal-data marking | `backend/app/models/` |
| Migrations | Schema history; applied before the app starts | `backend/alembic/` |
| Database bootstrap | Health probe only, run once on an empty volume | `db/init/` |
| Orchestration | Service definitions, ports, volumes, healthchecks | `docker-compose.yml` |

File-level detail lives in [`map/`](map/README.md) - one file per area, so finding code doesn't mean reading this document.

## Data flow

Today:

```
browser → frontend (Next.js, :3000) → backend (FastAPI, :8000) → postgres (:5432)
```

The frontend reaches the backend through `NEXT_PUBLIC_API_URL`, which must be a host-reachable URL because the browser makes the call. Backend → database uses `DATABASE_URL`, whose host is the compose service name `db`, resolvable only inside the compose network.

`POST /chat` exists but is plumbing, not the AI layer: it writes the question to `queries`, then streams back a fixed placeholder string, chunk by chunk. No retrieval, no model call, no orchestration - see `docs/llm/README.md`'s non-negotiables. Planned addition, once the AI layer lands: retrieval and a real model call replace the placeholder, plus quota checks before either. Sketched in `docs/llm/retrieval.md` and `docs/llm/cost-control.md`.

On the browser side the stream is consumed by `frontend/lib/api-client.ts` and rendered by
`app/chat/ChatPanel.tsx`. Because the backend streams translation keys rather than prose, the
frontend copy layer is what turns an answer into Polish; a key it cannot resolve is dropped
rather than printed, and a stream in which nothing at all resolves becomes a failure rather
than a blank reply. Every HTTP failure collapses into one of four `ChatFailure` values before
any component sees it, and the body of a failed response is never read.

## Data model

Five tables, in `backend/app/models/`. Each one exists because a product decision needs it, not because it rounds out a diagram.

| Table | Exists for | Notes |
|---|---|---|
| `users` | The larger question quota for someone with an account | Email uniqueness is a database constraint. No authentication logic yet |
| `chat_sessions` | Counting questions, account or not | `user_id` is nullable; the opaque `token` is what gets counted |
| `queries` | Cost reporting and quality regression | Append-only. Question, answer, model, tokens, cost, duration |
| `knowledge_base_versions` | Tracing an answer to the exact content behind it | Version, ingest time, record count, source checksum |
| `knowledge_gaps` | The queue of what the base could not answer | Survives deletion of the query it came from |

```
users 1--0..n chat_sessions 1--0..n queries 0..1--1 knowledge_gaps
                                       n--0..1 knowledge_base_versions
```

Two constraints carry decisions rather than hygiene, so they live in the database instead of in application code:

- `chat_sessions.user_id` is **nullable**. Anonymous parents have to be countable or the quota is decorative.
- `queries` carries `CHECK (answer IS NULL OR knowledge_base_version_id IS NOT NULL)`. An answer that cannot name the base version behind it becomes unexplainable the moment the base changes, and the base is expected to change indefinitely.

**Personal data** is marked at the column level with `info=PERSONAL_DATA`, and `personal_data_columns()` derives the list from the metadata. Retention periods are deliberately not implemented: they depend on GDPR decisions that have not been made yet.

The intended erasure model is **scrubbing marked columns rather than deleting rows**, because spending and "what are parents asking" are facts about the service, not about the individual. The foreign keys pointing at a person already follow it: deleting a `users` row clears `chat_sessions.user_id`, and deleting a `queries` row clears `knowledge_gaps.query_id`, in both cases leaving the surrounding record intact. `queries.chat_session_id` cascades instead, which is safe only because deleting a session row is administrative cleanup and not how a person's data is erased.

## Key decisions (lightweight ADR)

| Date | Decision | Why |
|---|---|---|
| 2026-08-05 | Stack: Next.js + FastAPI + PostgreSQL, orchestrated by Docker Compose | Clean split between UI and AI/data logic; Python is where the retrieval and model tooling lives; one command to start the whole thing on any machine |
| 2026-08-05 | Skeleton first - no vector DB, no LLM SDK, no model calls | Lock the shape of the system before adding moving parts that are expensive to change and expensive to run |
| 2026-08-05 | Plain PostgreSQL, no vector extension | Nothing needs vectors yet. When retrieval arrives, evaluate `pgvector` in this same container before adding a fourth service |
| 2026-08-05 | Dev-mode containers with host bind mounts and hot reload | Fast feedback while the shape is still moving; production images are a separate, later concern |
| 2026-08-05 | Bootstrap SQL in `db/init/`, no migration tool | One table, no history to preserve. Introduce Alembic when the first real schema change appears. **Superseded 2026-08-25** |
| 2026-08-05 | Stay on FastAPI rather than Django/DRF | The core interaction is a streamed chat response over async I/O, which Starlette does natively; Django's main draw here was the free admin panel, and that is one secondary screen, buildable in Next.js against the same API |
| 2026-08-05 | `AGENTS.md` as the single source of agent rules; `CLAUDE.md` imports it, `.cursor/rules/` points at it | Duplicated rules drift apart silently, and then each tool behaves differently on the same repo |
| 2026-08-05 | Repository map split by area in `docs/map/`, enforced by `scripts/check_map.py` | A single map file forces a frontend change to load backend rows; an unenforced map goes stale and then actively misdirects |
| 2026-08-05 | Capped log (`docs/log.md`, 20 entries) instead of an unbounded journal | The journal was auto-loaded every session and grows without limit - ~35k tokens per session at 100 entries, paid even to edit one CSS variable |
| 2026-08-05 | Tests and CI from the skeleton stage, with coverage gates | Agents need a signal they can read without a human; a suite added "later" never covers the foundations |
| 2026-08-05 | Integration tests skip instead of failing when PostgreSQL is unreachable | Keeps the suite usable with nothing running, while CI always has a real database so nothing is quietly skipped there |
| 2026-08-05 | Smoke test drives the real containers over HTTP | Unit tests pass on a machine where nothing starts; this is the check that answers "it works on my machine" |
| 2026-08-05 | Two long-lived branches: `main` as production, `dev` as integration | Keeps `main` a readable release history and gives changes somewhere to accumulate and be tested together before they are called a release |
| 2026-08-21 | Frontend translation layer is a custom dictionary lookup (`lib/i18n/`), not a library like `next-intl` | Only one locale ships today and no runtime locale switch exists yet; a library buys nothing the app uses. Adding a locale is one file plus one registry line in `translations.ts`, and TypeScript rejects a translation file whose keys do not match `locales/pl.ts` |
| 2026-08-21 | Design tokens in `globals.css` use the Bilingers-based palette proposed in T-03, marked provisional in a comment at the top of the file | T-03 left open whether the chat's brand is the foundation, Bilingers, or both, and both the foundation and Bilingers have two conflicting visual variants in the source material. Bilingers was picked as the working default because T-03 frames the chat as that app's vestibule, not because the question is resolved |
| 2026-08-25 | Alembic, applied by the backend container on start | The first real schema change arrived, which is the trigger the 2026-08-05 decision named. Running it as part of the start command is what makes "works on a clean database with no manual steps" true rather than aspirational |
| 2026-08-25 | Alembic owns every application table; `db/init/` keeps only the health probe | Two mechanisms defining schema is two sources of truth. `db/init/` cannot be the one that wins: it runs only on an empty volume, so it silently does nothing on every machine that already has data |
| 2026-08-25 | Cost stored as `NUMERIC(12,6)`, never a float | This figure goes to the foundation for approval (D11). Accumulated float error in a number someone is asked to sign off on is not acceptable |
| 2026-08-25 | Personal data marked in the model with `info=PERSONAL_DATA`, retention unimplemented | Marking is cheap now and expensive to retrofit across a grown schema. Retention periods depend on GDPR answers nobody has yet, and inventing them would look like compliance without being it |
| 2026-08-25 | GDPR erasure scrubs marked columns; person-facing foreign keys clear rather than cascade | Deleting a person must not delete the spending record or the list of what parents ask. Those are aggregate facts about the service, not facts about the individual |
| 2026-08-26 | `POST /chat` writes its `Query` row and commits before the response starts streaming | A connection dropped mid-answer must not leave the question unlogged for T-41's cost ledger; committing before any bytes stream is what guarantees that regardless of how the stream ends |
| 2026-08-26 | `/chat` streams a fixed sequence of opaque placeholder chunks rather than calling a model | T-12 is explicitly the pipe, not the engine (no RAG, no orchestration, no guardrails yet); the `answer` column also cannot be set without a `knowledge_base_version_id`, which does not exist until ingestion (T-01) runs. Keys, not prose, so the placeholder does not itself violate "the backend returns data and keys, not sentences" while it is standing in for a real answer |
| 2026-08-26 | `app.services.chat` raises `ChatServiceUnavailable` or `InvalidChatInput` instead of letting `SQLAlchemyError` reach the router | Sets the precedent for every future DB-backed router: `docs/conventions.md` requires services to raise domain exceptions and routers to translate them. The two exceptions map to different HTTP statuses (503 vs 422) because a bad connection and a rejected question are not the same failure and should not both cause a client to retry blindly |
| 2026-08-28 | Panel accounts live in `panel_users`, separate from the parent-facing `users` table | Same word, different threat model: a parent's account unlocks a question quota, an editor's unlocks 30 years of research under an NDA. One table would make any bug on the quota path a knowledge base leak |
| 2026-08-28 | Panel sessions are opaque tokens in an `Authorization: Bearer` header, stored only as a SHA-256 hash, with an absolute 12 hour expiry | A hash means a database dump does not hand over live sessions. A header rather than a cookie because the panel frontend does not exist yet (T-86), so the CSRF and SameSite decisions that come with a cookie can be made when there is a client to make them for. Absolute rather than idle expiry: a sliding window writes to the database on every request to the most sensitive screen in the system |
| 2026-08-28 | No registration form and no self-service password reset; an administrator creates accounts and issues one-time tokens | The panel holds three to five accounts for the life of the project, so a registration form is attack surface bought for nothing. A "forgot my password" endpoint would mint a token with no way to deliver it: there is no mail path yet. Revisit the second half when mail exists |
| 2026-08-28 | Five failed logins lock the account for fifteen minutes; every attempt is recorded, including for addresses that match no account | An attack on a five-account panel looks like repeated failures against addresses that do not exist, and that pattern is invisible if only real accounts are logged. The counter lives on the account, not in the audit table, so pruning the audit cannot quietly disable the limit. **Superseded 2026-09-02** |
| 2026-08-26 | `ChatRequest.session_token` requires 32-64 lowercase hex characters | The token is the only key to a conversation and a future D5 quota; `min_length=1` let two unrelated clients collide into the same `ChatSession` and its `PERSONAL_DATA`-marked questions by both picking a short token |
| 2026-09-02 | The frontend reduces every backend failure to a closed set of four `ChatFailure` keys, and never reads a failed response's body | A failing backend's body can name the model provider or quote the system prompt, which T-63 forbids showing a parent and T-52 treats as an attack surface. A status the backend starts returning that is not in the set degrades to `unreachable` instead of reaching the screen as an unhandled shape |
| 2026-09-02 | `app/error.tsx` never binds the thrown `Error` it is handed | Its message and digest are the likeliest carriers of a stack trace, an internal hostname or a provider name anywhere in the frontend. Not destructuring it is a structural guarantee; remembering not to render it is not |
| 2026-09-02 | 429 is mapped to the limit state before anything emits it | The anonymous quota is T-71/T-73, but T-63 owns what a parent sees when it trips, and a state nobody can reach is a state nobody has tested. The counter lands later without touching the client |
| 2026-09-02 | State tone is a left border plus copy, never colored text; `--color-danger` is border-only | `--color-primary` already fails WCAG AA on white (see the note at the top of `globals.css`), so tinting status text would spread that debt rather than contain it. Border-only use also means the 3:1 non-text threshold applies, which the token clears in both light and dark |

## Integrations / external dependencies

None yet. No third-party API is called and no API key exists in the project.

Expected later, each needing its own section here when it lands:

- an LLM provider for the assistant,
- a mail path for questions the knowledge base cannot answer (address to be agreed),
- links out to Bilingers.app and the shop.

## Open questions

Product decisions still unsettled; they affect what gets built:

- Is the certificate itself valuable to a parent, or is the knowledge the whole value?
- How are contact details collected for unanswered questions, under GDPR, while collecting as little personal data as possible?
- Where does the app live - standalone domain or part of an existing Bilingers property?
- Which mail path delivers a panel password reset, so an editor stops depending on an administrator to hand them a token?
