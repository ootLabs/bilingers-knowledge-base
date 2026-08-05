# Bilingers — intelligent knowledge base on bilingualism

A free educational app for parents and carers, built with the Bilingual Future Foundation. Users talk to an AI assistant grounded in the foundation's knowledge base, then check what they learned with a quiz that can end in a certificate.

**Status: skeleton.** Three containers that build, start, and talk to each other — nothing more. No vector database, no LLM SDK, no model calls, no API keys. See "What is deliberately missing" below.

---

## Stack

| Service | Technology | Port |
|---|---|---|
| `frontend` | Next.js 15 (App Router, TypeScript) | 3000 |
| `backend` | Python 3.12, FastAPI, SQLAlchemy | 8000 |
| `db` | PostgreSQL 16 | 5432 |

---

## Requirements

- Docker Desktop (or Docker Engine) with Compose v2 — `docker compose version` must work.
- Nothing else. Node and Python run inside the containers.

---

## Run it

```bash
cp .env.example .env      # Windows PowerShell: Copy-Item .env.example .env
docker compose up --build
```

First build takes a few minutes (npm install + pip install). Then:

- Frontend — <http://localhost:3000>
- Backend — <http://localhost:8000>
- API docs (Swagger) — <http://localhost:8000/docs>
- Health — <http://localhost:8000/health>
- Health incl. database — <http://localhost:8000/health/db>

Both services run in dev mode with hot reload: edit a file on the host and the container picks it up.

### Everyday commands

```bash
docker compose up -d              # start in the background
docker compose logs -f backend    # follow one service's logs
docker compose restart backend    # restart after a dependency change
docker compose down               # stop (data survives)
docker compose down -v            # stop and wipe the database volume
docker compose exec db psql -U bilingers -d bilingers   # psql shell
```

`db/init/*.sql` runs **only** on an empty volume. After changing it, use `docker compose down -v` to see the effect.

---

## Repository layout

```
backend/            FastAPI service
  app/
    config.py       settings from environment variables
    db.py           SQLAlchemy engine + session dependency
    main.py         app entrypoint, CORS, router wiring
    routers/        one file per HTTP domain
frontend/           Next.js app (App Router)
  app/              pages, layout, global styles
db/init/            SQL executed on first database start
docs/               architecture, conventions, LLM wiki
docker-compose.yml  the three services
.env.example        every configurable variable
```

Where each feature lives is tracked in `CLAUDE.md` → "Project map". Keep it current.

---

## What is deliberately missing

Not oversights — decisions for this stage. Don't add them without agreeing first:

- vector database, embeddings, RAG retrieval,
- LLM SDK, model API calls, API keys,
- authentication, quiz, certificates, admin panel,
- database migrations (only the bootstrap SQL exists),
- CI, tests, production Docker images.

The intended design of the AI layer is written up in [`docs/llm/`](docs/llm/README.md) — notes, not code.

---

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — how we work + the project map (read first).
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — branches, commits, review.
- [`docs/architecture.md`](docs/architecture.md) — modules, data flow, decisions.
- [`docs/conventions.md`](docs/conventions.md) — naming, structure, style.
- [`docs/llm/`](docs/llm/README.md) — knowledge base, retrieval, prompts, cost control.
- [`AI_NOTES.md`](AI_NOTES.md) — running project journal.

---

Interaktywna baza wiedzy o dwujęzyczności powstała i jest rozwijana dzięki Bilingers.Systems.
