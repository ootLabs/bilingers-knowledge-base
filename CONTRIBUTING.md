# Contributing to Bilingers

Read [`AGENTS.md`](AGENTS.md) first - it is the project constitution and routes you to the right documentation. This file covers the mechanics: branches, commits, review.

---

## Language

- **Repository: English.** Code, identifiers, comments, commit messages, documentation.
- **User-facing content: Polish.** UI copy, labels, seed data shown in the product.
- **Chat / discussion: whatever you like.** It never changes the two rules above.

No mixing the two inside one artifact. A Polish comment in English code, or an English label in the Polish UI, gets sent back in review.

---

## Getting set up

```bash
cp .env.example .env
git config core.hooksPath .githooks   # once per clone
docker compose up --build
```

Endpoints are in [`README.md`](README.md). Run everything through Docker; a local Node or Python install is not supported and will drift from what other developers see.

The `core.hooksPath` line enables the pre-commit hook, which blocks a commit when `docs/map/` disagrees with the repository or when a banned typographic character slipped in. Git does not share hooks automatically, so this is per clone. Run it, or both checks are on your honour.

---

## Everyday commands

```bash
docker compose up -d              # start in the background
docker compose logs -f backend    # follow one service's logs
docker compose restart backend    # after a config change
docker compose down               # stop, data survives
docker compose down -v            # stop and wipe the database volume
docker compose exec db psql -U bilingers -d bilingers   # psql shell
```

Rebuilds, because a restart is not enough when dependencies change:

```bash
docker compose up -d --build backend                          # requirements changed
docker compose up -d --build --renew-anon-volumes frontend    # package.json changed
```

The `--renew-anon-volumes` flag matters: `node_modules` lives in an anonymous volume that survives a plain rebuild, so without it the container keeps the old packages and you debug a ghost.

`db/init/*.sql` runs **only** on an empty volume. After changing it, `docker compose down -v` and start again, or the change appears to do nothing.

Tests: [`docs/testing.md`](docs/testing.md). All of them run in CI on every pull request.

---

## Branches

Two branches live forever. Nothing is committed directly to either of them.

| Branch | Role | What lands here |
|---|---|---|
| `main` | Production. Always deployable. | A release merge from `dev`, or a `hotfix/`. Nothing else. |
| `dev` | Integration. The default branch. | Every finished feature branch. |

Everything else is short-lived and **cut from `dev`**:

```
feat/<short>       new functionality
fix/<short>        bug fix
refactor/<short>   behavior-preserving change
chore/<short>      tooling, config, dependencies
docs/<short>       documentation only
```

Short, lowercase, hyphenated: `feat/chat-endpoint`, `fix/cors-origins`.

### Daily flow

```bash
git checkout dev && git pull
git checkout -b feat/chat-endpoint
# work, commit, push
git push -u origin feat/chat-endpoint
# open a pull request into dev
```

### Releasing

Open a pull request from `dev` into `main` and merge it with `--no-ff`. One commit on `main` per release, so `git log main` reads as a release history rather than a stream of individual changes.

### Hotfixes

A production bug that cannot wait for the next release:

```bash
git checkout main && git pull
git checkout -b hotfix/broken-health-probe
# fix, commit, PR into main
```

After it merges to `main`, **merge `main` back into `dev` immediately.** Skip that and the next release quietly reverts the fix. This is the single most common way a two-branch model breaks.

---

## Commits

- One commit = one logical change. Commit often, in small steps.
- Title: `type: short, on-point summary`, ≤ ~60 characters, imperative mood, English, no trailing period.
- Types: `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `perf`.
- **No body** unless the change is large, functionally important, or non-obvious - then 2-4 bullets.

```
feat: chat message endpoint
fix: cors origins parsing
refactor: extract knowledge base loader
chore: bump fastapi to 0.115
```

### Hard rule - no tool or AI authorship

Nothing in this repository may credit or mention an AI assistant or a code-generation tool: not in commit messages, pull requests, code, comments, or documentation. No `Co-Authored-By`, no "generated with". `.claude/settings.json` sets `includeCoAuthoredBy: false`; leave it that way.

---

## Before you open a pull request

1. The change works - you started the stack and exercised it, not just read the diff. `docker compose exec backend pytest` and `docker compose exec frontend npm test` pass, and new behavior has a test. See [`docs/testing.md`](docs/testing.md).
2. `python scripts/check_map.py` exits 0 - the pre-commit hook enforces this. Added, moved, renamed, or deleted a file → its row in `docs/map/` changed in the same commit. Added a whole new top-level directory → teach `AREAS` and `KNOWN_TOP_LEVEL` in the script about it and give it its own `docs/map/` file.
3. Affected files under `docs/` are updated. Stale docs are worse than none.
4. `.env.example` lists any new environment variable (with a safe placeholder, never a real secret).
5. Larger task → one entry at the top of `docs/log.md`, following the format defined there.

A pull request describes **what changed and why**, in a few sentences. Link the issue if there is one. The template in `.github/pull_request_template.md` carries the checklist.

CI runs on every pull request: repository checks, backend tests against real PostgreSQL, frontend typecheck plus tests plus build, and a smoke test that starts all three containers and talks to them over HTTP. A red pipeline means the branch does not merge.

### What is enforced on GitHub

These are repository settings, not files in this repo. They are already applied:

| | `main` | `dev` |
|---|---|---|
| Four CI jobs must pass | yes | yes |
| Pull request required | yes, 0 approvals | no |
| Branch must be up to date before merging | yes | no |
| Force push, deletion | blocked | blocked |
| Rules apply to admins | **yes** | no |
| Conversation resolution required | yes | no |

`main` binds admins too, so nobody, including the owner, can push to production past a red pipeline. Releasing means opening a pull request from `dev` into `main` and merging it there.

On `dev` admins can still push directly, which is the deliberate difference in strictness. Everyone else goes through a pull request with green checks.

If a genuine emergency needs the `main` rules lifted, turn "Include administrators" off in branch protection, do the fix, and turn it back on. Doing that should feel deliberate, which is the point.

---

## Code style

Details in [`docs/conventions.md`](docs/conventions.md). The short version:

- Small files, single responsibility. Past ~300 lines or doing two things → split it.
- One domain = one module. Don't mix UI, logic, and data access in one file.
- Comments explain *why*, never *what*.
- **No em dashes or en dashes**, anywhere, including Polish UI copy. Comma, colon, parentheses, or a plain hyphen. Enforced by `scripts/check_text.py`.
- Check [`docs/map/`](docs/map/README.md) before building - the thing may already exist, and the map finds it faster than a search.

---

## Scope discipline

This repository is intentionally a skeleton. Do not add a vector database, an LLM SDK, model API calls, or authentication without agreeing on it first - see "What is deliberately missing" in the README. Design notes for the AI layer live in [`docs/llm/`](docs/llm/README.md); extend the notes before extending the code.

---

## Secrets

Never commit `.env`, API keys, database dumps, or personal data. `.env.example` documents the *names* of variables and nothing else. The project handles data about families and children - when in doubt, collect less.
