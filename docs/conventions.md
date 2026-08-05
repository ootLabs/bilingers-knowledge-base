# Conventions — Bilingers

> Decide once, follow always. Consistency beats personal preference. Written in English.

## Naming

| Thing | Convention | Example |
|---|---|---|
| Python files / modules | `snake_case` | `knowledge_base.py` |
| Python functions / variables | `snake_case` | `get_session` |
| Python classes | `PascalCase` | `Settings` |
| TypeScript files (non-component) | `kebab-case` | `api-client.ts` |
| React components (file and symbol) | `PascalCase` | `ChatMessage.tsx` |
| TS functions / variables | `camelCase` | `sendMessage` |
| Constants (both languages) | `UPPER_SNAKE` | `NEXT_PUBLIC_API_URL` |
| Database tables / columns | `snake_case`, tables plural | `chat_messages.created_at` |
| Branches | `type/kebab-case` | `feat/chat-endpoint` |
| API paths | lowercase, plural nouns, hyphens | `/api/chat-sessions` |

## Folder structure

**Backend — layered, one file per domain.**

```
backend/app/
  config.py     settings
  db.py         engine + session dependency
  main.py       app assembly only: middleware, routers. No business logic.
  routers/      HTTP layer: request/response, validation, no business logic
  services/     business logic (create when the first one appears)
  models/       SQLAlchemy models (create when the first one appears)
  schemas/      Pydantic request/response models (create when the first one appears)
```

A router calls a service; a service uses models. Never the other way round, and never a router touching the database directly beyond a health probe.

**Frontend — Next.js App Router, feature-first.**

```
frontend/app/
  layout.tsx        shell, metadata
  page.tsx          landing
  <feature>/        one folder per feature route
components/         shared components (create when something is reused twice)
lib/                API client, helpers
```

Don't create empty folders ahead of need. Create them with the first file that belongs there, and add a row to the matching file in [`map/`](map/README.md).

## Patterns

- **Configuration:** every setting comes from an environment variable, read in `backend/app/config.py` (backend) or `process.env.NEXT_PUBLIC_*` (frontend). No magic values in code. Every new variable is added to `.env.example` with a safe placeholder.
- **Database access:** through the `get_session` dependency. No module-level sessions, no connections opened inside request handlers.
- **Errors:** raise `HTTPException` at the router boundary; services raise domain exceptions and let the router translate them. Never return a `200` with an error body.
- **Validation:** Pydantic schemas at the boundary. Anything past the router is assumed valid.
- **Async:** endpoints are sync until something is genuinely I/O-bound and async-capable. Don't mark a handler `async` while calling blocking code inside it.
- **One way to do one thing.** Found two ways in the codebase? Pick one, refactor the other, commit it separately.

## Code style

- **Python:** PEP 8, type hints on public functions, 4-space indent. No formatter is wired in yet — if you add one, use `ruff` and commit the config.
- **TypeScript:** `strict` is on and stays on. No `any` without a comment explaining why.
- **Comments** explain *why*, never *what*. No references to AI or tooling anywhere.
- **File size:** past ~300 lines, or doing two things → split it.

## Tests

None yet. When the first one is written:

- **What we test:** business logic and critical paths (retrieval correctness, quota enforcement, quiz scoring). Not framework glue.
- **Backend:** `pytest`, tests in `backend/tests/`, mirroring the `app/` layout, files named `test_<module>.py`. Run with `docker compose exec backend pytest`.
- **Frontend:** only once there is logic worth testing; UI snapshots are not it.

Update this section in the same commit that introduces the test setup.

## User-facing text

All copy shown to users is **Polish** and lives in the frontend, never hardcoded in the backend — the backend returns data and keys, not sentences. The architecture must stay ready for more languages; see `docs/llm/i18n.md`.
