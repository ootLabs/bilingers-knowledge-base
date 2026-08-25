# Bilingers - intelligent knowledge base on bilingualism

A free educational app for parents and carers, built with the Bilingual Future Foundation. Users talk to an AI assistant grounded in the foundation's knowledge base, then check what they learned with a quiz that can end in a certificate.

**Status: skeleton.** Three containers, health endpoints, the core data model with migrations, tests, CI. No vector database, no LLM SDK, no model calls, no authentication. What is deliberately absent and why: [`AGENTS.md`](AGENTS.md).

## Run it

Needs Docker with Compose v2. Nothing else: Node and Python live in the containers.

```bash
cp .env.example .env                  # PowerShell: Copy-Item .env.example .env
git config core.hooksPath .githooks   # once per clone, enables the commit checks
docker compose up --build
```

| | | |
|---|---|---|
| Frontend | Next.js 15 | <http://localhost:3000> |
| Backend | FastAPI, Python 3.12 | <http://localhost:8000> ([docs](http://localhost:8000/docs), [health](http://localhost:8000/health)) |
| Database | PostgreSQL 16 | `localhost:5432` |

Both apps hot reload from the host. Everyday commands and gotchas: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Where everything is

| I need | Read |
|---|---|
| How we work, and the rules | [`AGENTS.md`](AGENTS.md) |
| Which file does what | [`docs/map/`](docs/map/README.md) |
| How the system fits together | [`docs/architecture.md`](docs/architecture.md) |
| Naming, structure, style | [`docs/conventions.md`](docs/conventions.md) |
| Running and writing tests, CI | [`docs/testing.md`](docs/testing.md) |
| The AI layer: RAG, prompts, cost | [`docs/llm/`](docs/llm/README.md) |
| Branches, commits, pull requests | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| What changed recently and why | [`docs/log.md`](docs/log.md) |

`CLAUDE.md` and `.cursor/rules/` both point at `AGENTS.md`, so every agent tool works from one set of rules.

---

Interaktywna baza wiedzy o dwujęzyczności powstała i jest rozwijana dzięki Bilingers.Systems.
