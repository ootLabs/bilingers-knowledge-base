# Architecture - Bilingers

> Overview for humans and for the coding agent. Written in English. Keep it short and concrete; update it when the structure changes.

## Overview

A free educational app for parents and carers raising a bilingual child. The user talks to an AI assistant answering **only** from the Bilingual Future Foundation knowledge base, then optionally takes a quiz that can end in a certificate.

Target flow (most of it not built yet): the user opens the app → reads a short intro → picks one of 3-5 suggested starter questions or types their own → the backend retrieves matching passages from the foundation's knowledge base → the model answers from those passages only → the app proposes 3-5 deeper follow-up questions → after some conversation the user can take a ~10-question quiz → passing issues a certificate.

**What exists today:** three containers, health endpoints, this documentation frame, and (as of T-14) a frontend routing skeleton with a Polish-only translation layer and design tokens from T-03. The chat, quiz, and account routes exist but hold placeholder copy only. Everything about retrieval, models, quiz logic, and certificates is design, not code - see `docs/llm/`.

## Main modules

| Module | Responsibility | Path |
|---|---|---|
| Frontend | UI, conversation view, quiz screens (Polish copy) | `frontend/app/` |
| Backend API | HTTP layer, one router per domain | `backend/app/routers/` |
| Backend config | Environment-driven settings | `backend/app/config.py` |
| Persistence | SQLAlchemy engine + session dependency | `backend/app/db.py` |
| Database bootstrap | SQL run once on an empty volume | `db/init/` |
| Orchestration | Service definitions, ports, volumes, healthchecks | `docker-compose.yml` |

File-level detail lives in [`map/`](map/README.md) - one file per area, so finding code doesn't mean reading this document.

## Data flow

Today:

```
browser → frontend (Next.js, :3000) → backend (FastAPI, :8000) → postgres (:5432)
```

The frontend reaches the backend through `NEXT_PUBLIC_API_URL`, which must be a host-reachable URL because the browser makes the call. Backend → database uses `DATABASE_URL`, whose host is the compose service name `db`, resolvable only inside the compose network.

Planned addition, once the AI layer lands: the backend gains a retrieval step and a model call between the request and the response, plus quota checks before either. Sketched in `docs/llm/retrieval.md` and `docs/llm/cost-control.md`.

## Key decisions (lightweight ADR)

| Date | Decision | Why |
|---|---|---|
| 2026-08-05 | Stack: Next.js + FastAPI + PostgreSQL, orchestrated by Docker Compose | Clean split between UI and AI/data logic; Python is where the retrieval and model tooling lives; one command to start the whole thing on any machine |
| 2026-08-05 | Skeleton first - no vector DB, no LLM SDK, no model calls | Lock the shape of the system before adding moving parts that are expensive to change and expensive to run |
| 2026-08-05 | Plain PostgreSQL, no vector extension | Nothing needs vectors yet. When retrieval arrives, evaluate `pgvector` in this same container before adding a fourth service |
| 2026-08-05 | Dev-mode containers with host bind mounts and hot reload | Fast feedback while the shape is still moving; production images are a separate, later concern |
| 2026-08-05 | Bootstrap SQL in `db/init/`, no migration tool | One table, no history to preserve. Introduce Alembic when the first real schema change appears |
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
