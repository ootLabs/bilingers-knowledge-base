# Architecture — Bilingers

> Overview for humans and for the coding agent. Written in English. Keep it short and concrete; update it when the structure changes.

## Overview

A free educational app for parents and carers raising a bilingual child. The user talks to an AI assistant answering **only** from the Bilingual Future Foundation knowledge base, then optionally takes a quiz that can end in a certificate.

Target flow (most of it not built yet): the user opens the app → reads a short intro → picks one of 3–5 suggested starter questions or types their own → the backend retrieves matching passages from the foundation's knowledge base → the model answers from those passages only → the app proposes 3–5 deeper follow-up questions → after some conversation the user can take a ~10-question quiz → passing issues a certificate.

**What exists today:** three containers, health endpoints, and this documentation frame. Everything about retrieval, models, quiz, and certificates is design, not code — see `docs/llm/`.

## Main modules

| Module | Responsibility | Path |
|---|---|---|
| Frontend | UI, conversation view, quiz screens (Polish copy) | `frontend/app/` |
| Backend API | HTTP layer, one router per domain | `backend/app/routers/` |
| Backend config | Environment-driven settings | `backend/app/config.py` |
| Persistence | SQLAlchemy engine + session dependency | `backend/app/db.py` |
| Database bootstrap | SQL run once on an empty volume | `db/init/` |
| Orchestration | Service definitions, ports, volumes, healthchecks | `docker-compose.yml` |

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
| 2026-08-05 | Skeleton first — no vector DB, no LLM SDK, no model calls | Lock the shape of the system before adding moving parts that are expensive to change and expensive to run |
| 2026-08-05 | Plain PostgreSQL, no vector extension | Nothing needs vectors yet. When retrieval arrives, evaluate `pgvector` in this same container before adding a fourth service |
| 2026-08-05 | Dev-mode containers with host bind mounts and hot reload | Fast feedback while the shape is still moving; production images are a separate, later concern |
| 2026-08-05 | Bootstrap SQL in `db/init/`, no migration tool | One table, no history to preserve. Introduce Alembic when the first real schema change appears |

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
- Where does the app live — standalone domain or part of an existing Bilingers property?
