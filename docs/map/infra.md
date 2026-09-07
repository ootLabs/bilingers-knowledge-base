# Map - infrastructure

Docker Compose runs everything. There is no supported way to run this project outside containers.

| Path | What's in it |
|---|---|
| `docker-compose.yml` | Three services - `db` (postgres:16, healthcheck), `backend` (:8000, `alembic upgrade head` then `--reload`), `frontend` (:3000, `npm run dev`); `postgres-data` volume |
| `.env.example` | Every configurable variable with safe defaults; copy to `.env` |
| `backend/pricing.example.json` | The shape of the model price list: `version`, `currency`, `fx_rate_pln_per_usd`, per-model prices per million tokens. Copy to `backend/pricing.json` (gitignored) and put the real numbers there |
| `backend/Dockerfile` | python:3.12-slim, installs `requirements.txt`, runs uvicorn |
| `frontend/Dockerfile` | node:22-alpine, `npm install`, runs `npm run dev` |
| `db/init/01_schema.sql` | Bootstrap SQL - creates `health_probe`; runs **only** on an empty volume. Holds no application schema: that is Alembic's, see [`backend.md`](backend.md) |
| `scripts/check_map.py` | Drift check between the repo and `docs/map/*.md`; exit 1 on drift. `AREAS` + `KNOWN_TOP_LEVEL` define what it scans |
| `scripts/check_text.py` | Bans em dashes and en dashes across the repo; `BANNED` holds the characters as escapes so the file does not trip itself |
| `scripts/smoke_test.py` | End-to-end check against the running stack over HTTP; used locally and by CI |
| `scripts/cost_report.py` | Cost summed per month, model, day and account, read through `docker compose exec db psql`; `--csv` exports one row per query. Filters on `created_at` so the month range uses `ix_queries_created_at` |
| `.githooks/pre-commit` | Runs both checks and blocks the commit on failure; needs `git config core.hooksPath .githooks` once per clone |
| `.github/workflows/ci.yml` | CI: repo checks, backend pytest against real PostgreSQL, frontend typecheck/tests/build, stack smoke test |

Everyday commands live in [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md), test commands in [`../testing.md`](../testing.md).

## Things that bite

- `db/init/*.sql` runs once, on first start of an empty volume. After editing it: `docker compose down -v`, then `up`. Application tables never go here, so this almost never needs editing.
- The `backend` service runs `alembic upgrade head` before uvicorn, so it never serves against a half-built schema. A failing migration exits, and `restart: unless-stopped` then retries it forever: the symptom is a backend that never answers and a log repeating the same Alembic error. Check `docker compose logs backend` first.
- `NEXT_PUBLIC_API_URL` is used by the **browser**, so it must be host-reachable (`localhost:8000`) - not the compose service name.
- `DATABASE_URL` is used by the **backend container**, so its host is `db` - the compose service name, which does not resolve from the host.
- `frontend` mounts the host directory but keeps the image's `node_modules` and `.next` as anonymous volumes. Changing `package.json` needs a rebuild, not a restart.
- No `package-lock.json` exists, so the image uses `npm install`. Builds are not reproducible until a lockfile is committed.
- `PRICING_FILE` points **inside** the backend container (`/app/pricing.json`), which the `./backend` mount maps to `backend/pricing.json` on the host. It is gitignored and absent on a fresh clone: nothing reads it until a model is actually called, and when something does, a missing file is an error naming the example to copy rather than a silent cost of zero.
- Editing the price list needs neither a restart nor a rebuild. `app.services.pricing` reads the file on every call and re-parses it when the contents change, deliberately not trusting `stat()`, and a broken edit fails the next request loudly instead of quietly serving the list it replaced.

## Where new things go

| Adding | Goes in |
|---|---|
| An environment variable | `.env.example` + the service's `environment:` block + `backend/app/config.py` if the backend reads it |
| A model price or a new exchange rate | `backend/pricing.json` on the host. Never the code, never a migration |
| A new service | `docker-compose.yml` + a row above + a decision line in `../architecture.md` |
| A maintenance script | `scripts/` - standard library only, runnable on the host without setup |
| A database table | An Alembic revision, never `db/init/` - see [`backend.md`](backend.md) |
