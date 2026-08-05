# Map - backend

FastAPI service. Layering rule (see [`../conventions.md`](../conventions.md)): router → service → model. A router never touches the database directly beyond a health probe.

| Path | What's in it |
|---|---|
| `backend/app/main.py` | App assembly only: `FastAPI()` instance, CORS middleware, router includes, `GET /` |
| `backend/app/config.py` | `Settings` (pydantic-settings) - env vars, `cors_origin_list`; module-level `settings` singleton |
| `backend/app/db.py` | SQLAlchemy `engine`, `SessionLocal`, `get_session()` FastAPI dependency |
| `backend/app/routers/health.py` | `GET /health` (liveness), `GET /health/db` (database reachability probe) |
| `backend/requirements.txt` | Pinned runtime dependencies |
| `backend/requirements-dev.txt` | Test tooling on top of the runtime pins: pytest, pytest-cov, httpx |
| `backend/pytest.ini` | Test config: `testpaths`, `pythonpath`, coverage gate at 90%, `integration` marker |

## Tests

`docker compose exec backend pytest`. See [`../testing.md`](../testing.md) for the full picture.

| Path | What's in it |
|---|---|
| `backend/tests/conftest.py` | `StubSession`, `client` (database stubbed), `raw_client`, `database_available`, `require_database` |
| `backend/tests/test_config.py` | `Settings` parsing: CORS origin splitting, whitespace, empty entries, defaults |
| `backend/tests/test_health.py` | `/health` and `/health/db` against a stub, plus integration tests against real PostgreSQL |
| `backend/tests/test_app.py` | Root route, OpenAPI schema, CORS headers, route uniqueness, `get_session` lifecycle |

## Where new things go

| Adding | Goes in | Then |
|---|---|---|
| An HTTP endpoint | `backend/app/routers/<domain>.py` | Include the router in `main.py`, add a row above |
| Business logic | `backend/app/services/<domain>.py` | Create the folder with the first file |
| A database table | `backend/app/models/<domain>.py` | Migration story is still open - see `../architecture.md` |
| Request/response shape | `backend/app/schemas/<domain>.py` | Create the folder with the first file |
| A setting | `backend/app/config.py` | Also add it to `.env.example` |

Folders marked "create with the first file" do not exist yet - don't create them empty.
