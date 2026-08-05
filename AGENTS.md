# Bilingers — agent instructions

Free educational app giving parents reliable knowledge about raising a bilingual child: an AI assistant grounded in the Bilingual Future Foundation knowledge base, plus a quiz and a certificate.

**Stack:** Next.js · FastAPI · PostgreSQL · Docker Compose

> **Single source of truth.** `CLAUDE.md` imports this file and `.cursor/rules/` points at it. Edit **this** file — never duplicate rules into the others.

---

## Current stage

The repository is a **skeleton**. Deliberately absent, not to be added without an explicit request:

no vector database · no embeddings/RAG · no LLM SDK · no model API calls · no API keys · no auth · no quiz · no certificates · no admin panel · no migrations · no CI · no tests

What exists: three containers that build and talk to each other, health endpoints, and the documentation frame. `docs/llm/` describes the intended AI layer — those are design notes, not code.

---

## Where to look — do this instead of exploring

Blind grep is how a five-minute change turns into an hour. Start here every time:

| What you're doing | Read first |
|---|---|
| Finding which file does X | `docs/map/README.md`, then the area map |
| Backend change | `docs/map/backend.md` |
| Frontend change | `docs/map/frontend.md` |
| Docker, database, scripts, env vars | `docs/map/infra.md` |
| Understanding how the system fits together | `docs/architecture.md` |
| Naming, folder structure, patterns, style | `docs/conventions.md` |
| Anything AI: RAG, prompts, cost, quiz, i18n | `docs/llm/README.md` |
| What changed recently and why | `docs/log.md` — **top few entries only** |

**Rule:** the map first, grep second. If the map didn't have it, the map was wrong — fix the map as part of your change.

Load only the area you're touching. Reading all four maps to change one CSS variable is the exact waste this structure exists to prevent.

---

## Language convention (kills "Ponglish")

- **Repository: English.** Code, identifiers, comments, commit messages, documentation — **regardless of the chat language.**
- **User-facing content: Polish.** UI copy, labels, seed data shown in the product.
- **Chat: whatever the person writes in.** It changes nothing above.

---

## Git

- `main` is always working. Branch: `feat/` `fix/` `refactor/` `chore/` `docs/` + short kebab-case.
- Commit = one logical change. Title `type: short summary`, ≤ ~60 chars, English, imperative, no trailing period.
- No body unless the change is large or non-obvious — then 2–4 bullets.
- **No AI or tool authorship anywhere** — not in commits, PRs, code, comments, or docs. No `Co-Authored-By`, no "generated with".

Full workflow: `CONTRIBUTING.md`.

---

## Definition of done

A change is finished when **all** of these hold:

1. The code works — you ran it, you didn't just read the diff.
2. `python scripts/check_map.py` exits 0. Added, moved, renamed, or deleted a file → its map row changed in the same commit.
3. Behavior or structure changed → the matching `docs/` file is updated. Built part of the AI layer → the matching `docs/llm/` note now describes what exists, not what was planned.
4. New environment variable → it is in `.env.example`.
5. Committed.
6. Non-trivial task → one entry added to `docs/log.md` (format and cap are defined in that file).

Steps 2–4 are what keep this repo cheap to work in. Skipping them shifts the cost onto the next session.

---

## Growth rules

- **Small files, single responsibility.** Two jobs or past ~300 lines → split.
- **One domain = one module.** Don't mix UI, logic, and data access.
- **Check the map before building** — the thing may already exist.
- **Don't create empty folders** ahead of need; create them with the first real file.
- **Refactoring is normal work**, committed separately.

---

## Before non-trivial work

Write your reasoning in `<plan> … </plan>` — edge cases, likely bugs, alternatives — then the solution below it. Skip only for genuine one-liners.

## When a session gets long

Context degrades; the model starts looping. Don't push through — dump state, open a fresh session, continue:

> Produce a full technical dump of our current state: 1) what works, 2) what we're stuck on, 3) next steps, 4) key decisions and changed files. Format it to paste into a fresh chat.

Put the same summary in `docs/log.md` before you stop.
