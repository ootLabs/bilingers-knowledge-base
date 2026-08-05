# AI Notes — Bilingers

> Running journal for whoever works on this project.
> **Read this file at the start of every session** — it's the memory that survives between sessions and context resets.
> At the end of every larger task, add a dated entry at the top (newest first): what was done, key architectural decisions, and what to watch out for next time. Keep entries short.

<!-- Copy this block for each new entry, newest on top:

## YYYY-MM-DD — <short task title>
- **Done:** what now works.
- **Decisions:** architectural choices made and why (one line each).
- **Watch out:** gotchas, debts, or things that will bite next time.

-->

## 2026-08-05 — project scaffold
- **Done:** repository initialized; Docker Compose with three services (Next.js frontend, FastAPI backend, PostgreSQL); backend health endpoints incl. a database probe; `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, `docs/architecture.md`, `docs/conventions.md`, and the `docs/llm/` design wiki.
- **Decisions:** stack — Next.js + FastAPI + PostgreSQL on Docker Compose; repo language — English; UI language — Polish; skeleton only — no vector DB, no LLM SDK, no model calls, no auth, by explicit request; dev-mode containers with bind mounts and hot reload; plain Postgres (evaluate `pgvector` in the same container if and when retrieval needs it); bootstrap SQL instead of a migration tool.
- **Watch out:**
  - `docker compose up --build` has not been run yet — the first build is unverified, and `frontend/package-lock.json` does not exist (the image uses `npm install`, not `npm ci`).
  - `db/init/*.sql` only runs on an empty volume; use `docker compose down -v` after changing it.
  - `NEXT_PUBLIC_API_URL` is used by the browser, so it must be host-reachable (`localhost:8000`), not the compose service name.
  - Everything in `docs/llm/` is design notes, not implementation. Fill the note in before writing the matching code.
  - Several product decisions are still open (certificate value, unanswered-question contact flow under GDPR, where the app lives) — see the end of `docs/architecture.md`.
