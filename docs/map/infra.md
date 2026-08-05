# Map — infrastructure

Docker Compose runs everything. There is no supported way to run this project outside containers.

| Path | What's in it |
|---|---|
| `docker-compose.yml` | Three services — `db` (postgres:16, healthcheck), `backend` (:8000, `--reload`), `frontend` (:3000, `npm run dev`); `postgres-data` volume |
| `.env.example` | Every configurable variable with safe defaults; copy to `.env` |
| `backend/Dockerfile` | python:3.12-slim, installs `requirements.txt`, runs uvicorn |
| `frontend/Dockerfile` | node:22-alpine, `npm install`, runs `npm run dev` |
| `db/init/01_schema.sql` | Bootstrap SQL — creates `health_probe`; runs **only** on an empty volume |
| `scripts/check_map.py` | Drift check between the repo and `docs/map/*.md`; exit 1 on drift |

## Things that bite

- `db/init/*.sql` runs once, on first start of an empty volume. After editing it: `docker compose down -v`, then `up`.
- `NEXT_PUBLIC_API_URL` is used by the **browser**, so it must be host-reachable (`localhost:8000`) — not the compose service name.
- `DATABASE_URL` is used by the **backend container**, so its host is `db` — the compose service name, which does not resolve from the host.
- `frontend` mounts the host directory but keeps the image's `node_modules` and `.next` as anonymous volumes. Changing `package.json` needs a rebuild, not a restart.
- No `package-lock.json` exists, so the image uses `npm install`. Builds are not reproducible until a lockfile is committed.

## Where new things go

| Adding | Goes in |
|---|---|
| An environment variable | `.env.example` + the service's `environment:` block + `backend/app/config.py` if the backend reads it |
| A new service | `docker-compose.yml` + a row above + a decision line in `../architecture.md` |
| A maintenance script | `scripts/` — standard library only, runnable on the host without setup |
