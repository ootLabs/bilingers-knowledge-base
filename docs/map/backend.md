# Map - backend

FastAPI service. Layering rule (see [`../conventions.md`](../conventions.md)): router → service → model. A router never touches the database directly beyond a health probe.

| Path | What's in it |
|---|---|
| `backend/app/main.py` | App assembly only: `FastAPI()` instance, CORS middleware, router includes, `GET /`, and the one exception handler turning `PanelServiceUnavailable` into `503` |
| `backend/app/config.py` | `Settings` (pydantic-settings) - env vars, `cors_origin_list`; module-level `settings` singleton |
| `backend/app/db.py` | SQLAlchemy `engine`, `SessionLocal`, `get_session()` FastAPI dependency |
| `backend/app/security.py` | `hash_password`, `verify_password`, `new_token`, `hash_token`, `MIN_PASSWORD_LENGTH`, `MAX_PASSWORD_BYTES` - bcrypt and SHA-256 primitives, no domain knowledge |
| `backend/app/dependencies.py` | `bearer_scheme`, `current_panel_session`, `current_panel_user`, `require_admin` - bearer token to account, `401`/`403` |
| `backend/app/cli.py` | `python -m app.cli create-admin <email>` - the only way the first administrator exists |
| `backend/app/routers/health.py` | `GET /health` (liveness), `GET /health/db` (database reachability probe) |
| `backend/app/routers/chat.py` | `POST /chat` - streams an answer; writes the `Query` row before streaming starts, translates `InvalidChatInput` to `422` and `ChatServiceUnavailable` to `503` |
| `backend/app/routers/panel_auth.py` | `POST /api/panel/sessions` (login), `DELETE /api/panel/sessions/current`, `GET /api/panel/users/me`, `POST /api/panel/users/me/password`, `POST /api/panel/password-resets/confirm` |
| `backend/app/routers/panel_users.py` | Administrator only: list, create, `PATCH` role/activity, `POST .../password-resets` under `/api/panel/users` |
| `backend/app/services/panel_auth.py` | `login`, `resolve_session`, `revoke_session`, `revoke_all_sessions`, `find_by_email`, `record_throttled_attempt`, `LoginFailure`, `AuthenticationFailed`, `normalise_email`, `as_utc` - lockout and the login audit; every refusal (unknown, wrong password, locked, deactivated) is the same exception and the same timing |
| `backend/app/services/rate_limit.py` | `check`, `reset`, `TooManyAttempts` (carrying `first_in_window`, so a flood is recorded once per window rather than once per request) - in-process sliding-window throttle for login attempts by IP address, ahead of the per-account lockout |
| `backend/app/services/panel_passwords.py` | `issue_password_reset`, `set_password_with_token`, `change_password`, `InvalidPasswordResetToken` |
| `backend/app/services/panel_users.py` | `create_panel_user`, `list_panel_users`, `update_panel_user`, `reset_password_for`, `EmailAlreadyUsed`, `PanelUserNotFound`, `PanelUserInactive`, `SelfManagementRefused` |
| `backend/app/services/panel_errors.py` | `PanelServiceUnavailable`, `unavailable_on_database_failure` - the decorator that keeps a driver exception from crossing the panel's service boundary; every panel service function a router or dependency calls carries it |
| `backend/app/services/chat.py` | `get_or_create_chat_session`, `record_query`, `stream_placeholder_answer`, `ChatServiceUnavailable`, `InvalidChatInput` - the streaming pipe from T-12, no RAG/model call yet |
| `backend/app/schemas/panel.py` | `PanelLoginRequest`, `PanelSessionResponse`, `PanelUserResponse`, `PanelUserCreateRequest`, `PanelUserUpdateRequest`, `PasswordResetResponse`, `PasswordResetConfirmRequest`, `PasswordChangeRequest`; password length rules and the address pattern (which excludes control characters, NUL included) live here |
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
| `backend/app/models/panel.py` | `PanelUser` (`panel_users`, nullable `password_hash`, lockout counters), `PanelSession`, `PanelLoginAttempt`, `PanelPasswordReset`, `PanelRole` - the panel's own accounts, separate from `users` |
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
| `backend/alembic/versions/6059ee904da3_panel_authentication.py` | Panel accounts: `panel_users`, `panel_sessions`, `panel_login_attempts`, `panel_password_resets`, the `panel_user_role` enum. Non-numeric revision id: `feat/cost-ledger` also branched from `0001` and claimed `"0002"` first |

## Tests

`docker compose exec backend pytest`. See [`../testing.md`](../testing.md) for the full picture.

| Path | What's in it |
|---|---|
| `backend/tests/conftest.py` | `StubSession`, `client` (database stubbed), `raw_client`, `database_available`, `require_database`, `db_session` (rolls back), `migrated_database` (skips unless every mapped table is present), `panel_db` (in-memory SQL), `panel_client`, `postgres_panel_client`, `cheap_password_hashing`, `make_panel_user`, `attempts_for`, `log_in` |
| `backend/tests/test_config.py` | `Settings` parsing: CORS origin splitting, whitespace, empty entries, defaults |
| `backend/tests/test_health.py` | `/health` and `/health/db` against a stub, plus integration tests against real PostgreSQL |
| `backend/tests/test_app.py` | Root route, OpenAPI schema, CORS headers, route uniqueness, `get_session` lifecycle |
| `backend/tests/test_models.py` | Schema guarantees: anonymous sessions, answer-needs-a-base-version, personal-data registry, plus integration round trips against real PostgreSQL |
| `backend/tests/test_security.py` | Hashing and tokens: salting, the missing-hash case, the bcrypt byte limit |
| `backend/tests/test_panel_auth.py` | Login input rules and credentials: what each kind of account that may not get in answers instead |
| `backend/tests/test_panel_lockout.py` | The per-account lockout: counting failures, locking, recovering, that a deactivated account is never charged (only recorded), and that the counter is read from the locked row rather than from a stale mapped object |
| `backend/tests/test_panel_sessions.py` | Session lifetime, plus a PostgreSQL class for the migrated schema and the unique constraint |
| `backend/tests/test_panel_passwords.py` | Password resets and changing your own password |
| `backend/tests/test_panel_users.py` | Who may create accounts, creating one and setting its first password |
| `backend/tests/test_panel_user_management.py` | Role/activity changes, self-lockout refusal, administrator-issued resets |
| `backend/tests/test_panel_errors.py` | A dropped connection: that every guarded panel service function raises `PanelServiceUnavailable`, and that the HTTP layer answers `503` for it, including when it comes from the session dependency |
| `backend/tests/test_cli.py` | `python -m app.cli create-admin` - the bootstrap command |
| `backend/tests/test_rate_limit.py` | The per-IP login throttle: the sliding window, that stale keys are swept instead of growing the dict forever, and that a throttled flood leaves one audit row per window |
| `backend/tests/test_chat.py` | Validation, the write-before-stream order, `SQLAlchemyError` to `503`, plus integration tests proving real persistence and session reuse |

## Where new things go

| Adding | Goes in | Then |
|---|---|---|
| An HTTP endpoint | `backend/app/routers/<domain>.py` | Include the router in `main.py`, add a row above |
| Business logic | `backend/app/services/<domain>.py` | Create the folder with the first file |
| A panel endpoint | `backend/app/routers/panel_*.py` | Guard it with `require_admin` or `current_panel_user` from `app/dependencies.py` |
| A database table | `backend/app/models/<domain>.py` | Import it in `models/__init__.py`, then add an Alembic revision |
| Request/response shape | `backend/app/schemas/<domain>.py` | Create the folder with the first file |
| A setting | `backend/app/config.py` | Also add it to `.env.example` |
| A field holding personal data | wherever it belongs | Mark it `info=PERSONAL_DATA` so `personal_data_columns()` finds it |
