# Map - backend

FastAPI service. Layering rule (see [`../conventions.md`](../conventions.md)): router → service → model. A router never touches the database directly beyond a health probe.

| Path | What's in it |
|---|---|
| `backend/app/main.py` | App assembly only: `FastAPI()` instance, CORS middleware, router includes, `GET /` |
| `backend/app/config.py` | `Settings` (pydantic-settings) - env vars, `cors_origin_list`; module-level `settings` singleton |
| `backend/app/db.py` | SQLAlchemy `engine`, `SessionLocal`, `get_session()` FastAPI dependency |
| `backend/app/routers/health.py` | `GET /health` (liveness), `GET /health/db` (database reachability probe) |
| `backend/app/routers/chat.py` | `POST /chat` - streams an answer; writes the `Query` row before streaming starts, translates `ChatServiceUnavailable` to `503` |
| `backend/app/services/chat.py` | `get_or_create_chat_session`, `record_query`, `stream_placeholder_answer`, `ChatServiceUnavailable` - the streaming pipe from T-12, no RAG/model call yet |
| `backend/app/schemas/chat.py` | `ChatRequest` (`question`, `session_token`); rejects blank/oversized input |
| `backend/requirements.txt` | Pinned runtime dependencies |
| `backend/requirements-dev.txt` | Test tooling on top of the runtime pins: pytest, pytest-cov, httpx |
| `backend/pytest.ini` | Test config: `testpaths`, `pythonpath`, coverage gate at 90%, `integration` marker |

## Models

Every table lives here; nothing outside `models/` defines schema. Importing the package is what registers tables on the metadata, so a new module goes into `models/__init__.py` or migrations cannot see it.

| Path | What's in it |
|---|---|
| `backend/app/models/__init__.py` | Imports every model so `Base.metadata` is complete; re-exports the public names |
| `backend/app/models/base.py` | `Base`, `TimestampMixin`, the `PERSONAL_DATA` column marker, `personal_data_columns()` |
| `backend/app/models/user.py` | `User` (`users`) - email unique in the database, `password_hash`, `email_verified_at` |
| `backend/app/models/chat.py` | `ChatSession` (`chat_sessions`, nullable `user_id` for anonymous use), `Query` (`queries`, the token/cost ledger and the `queries_answer_requires_kb_version` check) |
| `backend/app/models/knowledge.py` | `KnowledgeBaseVersion` (`knowledge_base_versions`), `KnowledgeGap` (`knowledge_gaps`), `KnowledgeGapStatus` |

## Migrations

Alembic owns every application table. `db/init/` is container bootstrap and never gains schema - see [`infra.md`](infra.md).

```bash
docker compose exec backend alembic upgrade head          # apply (the backend also does this on start)
docker compose exec backend alembic revision -m "..."     # new revision, then hand-write the ops
docker compose exec backend alembic current               # which revision is applied
```

| Path | What's in it |
|---|---|
| `backend/alembic.ini` | Alembic config; `script_location`, `prepend_sys_path`, logging. No `sqlalchemy.url` on purpose |
| `backend/alembic/env.py` | Reads `DATABASE_URL` via `app.config`, sets `target_metadata` from `app.models.Base` |
| `backend/alembic/versions/0001_core_data_model.py` | First revision: the five tables, the `knowledge_gap_status` enum, indexes and constraints |

## Tests

`docker compose exec backend pytest`. See [`../testing.md`](../testing.md) for the full picture.

| Path | What's in it |
|---|---|
| `backend/tests/conftest.py` | `StubSession`, `client` (database stubbed), `raw_client`, `database_available`, `require_database`, `db_session` (rolls back), `migrated_database` |
| `backend/tests/test_config.py` | `Settings` parsing: CORS origin splitting, whitespace, empty entries, defaults |
| `backend/tests/test_health.py` | `/health` and `/health/db` against a stub, plus integration tests against real PostgreSQL |
| `backend/tests/test_app.py` | Root route, OpenAPI schema, CORS headers, route uniqueness, `get_session` lifecycle |
| `backend/tests/test_models.py` | Schema guarantees: anonymous sessions, answer-needs-a-base-version, personal-data registry, plus integration round trips against real PostgreSQL |
| `backend/tests/test_chat.py` | Validation, the write-before-stream order, `SQLAlchemyError` to `503`, plus integration tests proving real persistence and session reuse |

## Where new things go

| Adding | Goes in | Then |
|---|---|---|
| An HTTP endpoint | `backend/app/routers/<domain>.py` | Include the router in `main.py`, add a row above |
| Business logic | `backend/app/services/<domain>.py` | Create the folder with the first file |
| A database table | `backend/app/models/<domain>.py` | Import it in `models/__init__.py`, then add an Alembic revision |
| Request/response shape | `backend/app/schemas/<domain>.py` | Create the folder with the first file |
| A setting | `backend/app/config.py` | Also add it to `.env.example` |
| A field holding personal data | wherever it belongs | Mark it `info=PERSONAL_DATA` so `personal_data_columns()` finds it |
