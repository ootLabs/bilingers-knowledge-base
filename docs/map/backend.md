# Map - backend

FastAPI service. Layering rule (see [`../conventions.md`](../conventions.md)): router → service → model. A router never touches the database directly beyond a health probe.

| Path | What's in it |
|---|---|
| `backend/app/main.py` | App assembly only: `FastAPI()` instance, CORS middleware, router includes, `GET /`, and the two exception handlers turning `PanelServiceUnavailable` and `TwoFactorNotConfigured` into `503` (the second carries `X-Second-Factor: not-configured`, which is what tells a missing encryption key apart from a database outage; it is registered here because the same condition is reachable from the login endpoint and from four two-factor routes) |
| `backend/app/config.py` | `Settings` (pydantic-settings) - env vars, `cors_origin_list`; module-level `settings` singleton |
| `backend/app/db.py` | SQLAlchemy `engine`, `SessionLocal`, `get_session()` FastAPI dependency |
| `backend/app/security.py` | `hash_password`, `verify_password`, `new_token`, `hash_token`, `MIN_PASSWORD_LENGTH`, `MAX_PASSWORD_BYTES` - bcrypt and SHA-256 primitives, no domain knowledge |
| `backend/app/dependencies.py` | `bearer_scheme`, `current_panel_session`, `current_panel_user`, `require_admin` - bearer token to account, `401`/`403` |
| `backend/app/cli.py` | `python -m app.cli create-admin <email>` - the only way the first administrator exists |
| `backend/app/routers/health.py` | `GET /health` (liveness), `GET /health/db` (database reachability probe) |
| `backend/app/routers/chat.py` | `POST /chat` - streams an answer; writes the `Query` row before streaming starts, translates `InvalidChatInput` to `422` and `ChatServiceUnavailable` to `503` |
| `backend/app/routers/panel_auth.py` | `POST /api/panel/sessions` (login), `DELETE /api/panel/sessions/current`, `GET /api/panel/users/me`, `POST /api/panel/users/me/password`, `POST /api/panel/password-resets/confirm` |
| `backend/app/routers/panel_users.py` | Administrator only: list, create, `PATCH` role/activity, `POST .../password-resets` under `/api/panel/users` |
| `backend/app/routers/panel_two_factor.py` | `GET/POST /api/panel/users/me/two-factor`, `.../confirm`, `.../disable`, and `POST /api/panel/users/{id}/two-factor-resets` for an administrator clearing somebody's lost authenticator. Disabling is a `POST` because it needs a body: the code is what proves a stolen session cannot remove it |
| `backend/app/routers/panel_audit.py` | `GET /api/panel/audit-events` - the change journal, administrators only, filtered by person and date range. One verb on purpose: there is no endpoint here that writes, edits or deletes a line |
| `backend/app/routers/panel_publishing.py` | `POST .../versions/{n}/publish` and `.../withdraw` under `/api/panel/documents`. Split from `panel_documents.py` along the same seam as the services: that file only ever writes drafts, this one is the decision to change what parents read |
| `backend/app/routers/panel_document_imports.py` | `POST /api/panel/document-imports` - reads one uploaded `.docx` and answers with what it understood, writing nothing. Its own prefix, because a literal segment under `/api/panel/documents/{id}` would be matched as an id. Extension whitelist and size limit are enforced here, not only in the form |
| `backend/app/routers/panel_documents.py` | `/api/panel/documents` for any signed-in editor: list, create, read one, history, one version, save an edit as a new version, restore an old one, publish a version, withdraw it. No `PUT` and no `DELETE` on a version, which is the model rather than an omission |
| `backend/app/services/panel_login_audit.py` | `LoginFailure`, `record_attempt`, `record_throttled_attempt` - writing down every attempt to get in, including for addresses that match no account. Reads no account on purpose, so a refused attempt costs one INSERT; T-89's journal reads these rows rather than copying them. Split from `panel_auth.py` at the size limit |
| `backend/app/services/panel_auth.py` | `login`, `find_by_email`, `AuthenticationFailed`, `SecondFactorRequired`, `utcnow`, `as_utc` - proving who somebody is, plus the per-account lockout the login transaction applies. Every refusal (unknown, wrong password, locked, deactivated) is the same exception and the same timing |
| `backend/app/services/rate_limit.py` | `check`, `reset`, `TooManyAttempts` (carrying `first_in_window`, so a flood is recorded once per window rather than once per request) - in-process sliding-window throttle for login attempts by IP address, ahead of the per-account lockout |
| `backend/app/services/panel_passwords.py` | `issue_password_reset`, `set_password_with_token`, `change_password`, `InvalidPasswordResetToken` |
| `backend/app/services/panel_users.py` | `create_panel_user`, `list_panel_users`, `get_panel_user` (called straight from the two-factor reset route, so it carries the unavailability decorator), `update_panel_user`, `reset_password_for`, `EmailAlreadyUsed`, `PanelUserNotFound`, `PanelUserInactive`, `SelfManagementRefused` |
| `backend/app/services/panel_totp.py` | The cryptography and the codes: `TwoFactorNotConfigured`, `TOTP_INTERVAL`, `TOTP_WINDOW`, `new_secret`, `encrypt_secret`, `decrypt_secret`, `provisioning_uri`, `new_backup_code`, `normalise_code`, `matched_step`. Works on strings and knows nothing about accounts; `matched_step` finds the step the CODE belongs to, which is what makes a spent code stay spent. Split from `panel_two_factor.py` at the size limit |
| `backend/app/services/panel_two_factor.py` | `begin_enrolment`, `confirm_enrolment` (returns the printable codes once), `verify_second_factor` (the one function `panel_auth` calls), `disable_for_self`, `reset_for`, `has_second_factor`, `unused_backup_code_count`, `normalise_code`, `Enrolment`, `TwoFactorNotConfigured`/`TwoFactorAlreadyOn`/`TwoFactorNotEnrolled`/`InvalidSecondFactor`. Fernet at rest, keyed from the environment; no default key on purpose |
| `backend/app/services/panel_sessions.py` | `resolve_session`, `revoke_session`, `revoke_all_sessions` - what happens to a session after it exists. Split out of `panel_auth.py` when the second factor pushed that file past the size limit; depends on it for the time helpers, never the other way round |
| `backend/app/services/panel_audit.py` | `record_event` (never raises: a failed journal write is logged and swallowed, so it cannot fail the operation it describes), `list_events` (merges `panel_audit_events` with `panel_login_attempts`, filtered by person and dates before the merge), `AuditEntry`, `DEFAULT_LIMIT`, `MAX_LIMIT`. The rollback after a failed write is guarded too, because a rollback on a connection that has just dropped raises a second time and would 500 an operation that already committed. Nothing here updates or deletes a row |
| `backend/app/services/panel_columns.py` | `EMAIL_LIMIT`, `IP_ADDRESS_LIMIT`, `USER_AGENT_LIMIT`, `DETAIL_LIMIT`, `truncated`, `required`, `normalise_email` - how the panel's text columns are shaped, in one place: their width, and the canonical lowercase form of an address whose column carries a unique index. Its own module rather than living beside one of its two callers: the login audit and the change journal both write these columns, and neither service may import the other |
| `backend/app/services/panel_errors.py` | `PanelServiceUnavailable`, `unavailable_on_database_failure` - the decorator that keeps a driver exception from crossing the panel's service boundary; every panel service function a router or dependency calls carries it |
| `backend/app/services/document_publishing.py` | `publish_version`, `withdraw_version`, `NotPublished`, `PublicationConflict` - the only code that updates an existing `document_versions` row (`status`, `published_at`, `published_by_id`, `knowledge_base_version_id`). Demotes the previous published version and **flushes** before promoting the new one, because the partial unique index is checked per statement; mints the `KnowledgeBaseVersion` that stamps the publication |
| `backend/app/services/document_queries.py` | The read half of documents: `list_documents` (one windowed query, document plus its newest AND its published version), `get_document`, `list_versions`, `get_version`. The published version is joined in rather than looked up per row, which the partial unique index makes safe; without it the panel reported a served document as unpublished |
| `backend/app/services/knowledge_index.py` | `record_index_change`, `IndexChange` - the one hook publication and withdrawal call. Writes a log line and nothing else until chunking (T-21) and embeddings (T-22) exist |
| `backend/app/services/docx_import.py` | `read_document` (bytes in, title plus body plus a report out), `ImportedDocument`, `SkippedItem`, `UnreadableDocument`, the `REASON_*` keys, and the heading detection that reads both `style.name` and `style.style_id` because one of them is localised. Headings and the proposed title are collapsed to one line, since python-docx reads Word's `<w:tab/>` and `<w:br/>` back as real control characters and `app.schemas.documents` refuses those in a title. One broken paragraph is counted and skipped, never fatal; tables are reported as not imported rather than silently dropped |
| `backend/app/services/documents.py` | The write half of documents plus the shapes both halves use: `create_document`, `add_version`, `restore_version`, the `VersionSummary`/`VersionDetail`/`DocumentSummary`/`DocumentDetail` views with `summary_of`/`detail_of`, `require_document`, `DocumentNotFound`, `VersionNotFound`, `ConcurrentEdit`; version numbering under `SELECT ... FOR UPDATE` with `populate_existing`, and the rule that nothing here ever updates a `document_versions` row |
| `backend/app/services/chat.py` | `get_or_create_chat_session`, `record_query`, `stream_placeholder_answer`, `ChatServiceUnavailable`, `InvalidChatInput` - the streaming pipe from T-12, no RAG/model call yet |
| `backend/app/schemas/panel.py` | `PanelLoginRequest`, `PanelSessionResponse`, `PanelUserResponse`, `PanelUserCreateRequest`, `PanelUserUpdateRequest`, `PasswordResetResponse`, `PasswordResetConfirmRequest`, `PasswordChangeRequest`; password length rules and the address pattern (which excludes control characters, NUL included) live here |
| `backend/app/services/pricing.py` | The configurable price list: `PriceList`, `ModelPrice`, `get_price_list` (the one entry point; re-reads the file when its bytes change), `parse_price_list`, `reset_price_list_cache`, `PricingConfigError`, `UnknownModelPrice` |
| `backend/app/services/usage.py` | Cost ledger writer: `TokenUsage`, `PricedUsage`, `price_usage` (USD and PLN), `record_usage` (one conditional `UPDATE` by query id in a session of its own, so a measurement is never overwritten), `InvalidUsage`, `UsageAlreadyRecorded`, `UsageNotRecorded` |
| `backend/app/schemas/panel_two_factor.py` | `TwoFactorStatusResponse`, `TwoFactorEnrolmentResponse`, `TwoFactorCodeRequest`, `BackupCodesResponse` - one code field for both an app code and a printed one, because the person typing should not have to know which they hold |
| `backend/app/schemas/panel_audit.py` | `AuditEntryResponse` - one journal line. No request schema, because nothing writes one from outside |
| `backend/app/schemas/document_import.py` | `DocumentImportPreviewResponse`, `SkippedItemResponse` - the read-only report a `.docx` upload answers with, before anything is saved |
| `backend/app/schemas/documents.py` | `DocumentContentRequest`, `VersionRestoreRequest`, `DocumentVersionSummaryResponse`, `DocumentVersionDetailResponse`, `DocumentSummaryResponse`, `DocumentDetailResponse`; both document responses carry `published_version` beside `latest_version`, because they are different questions. The 500-character title bound and the control-character rule (line breaks allowed in a body, nowhere else) live here |
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
| `backend/app/models/two_factor.py` | `PanelTotpSecret` (`panel_totp_secrets`, one per account, secret encrypted rather than hashed because a code has to be recomputed from it, `confirmed_at` gating and `last_used_step` against replay), `PanelBackupCode` (`panel_backup_codes`, SHA-256 hashes, `used_at` makes them single use) |
| `backend/app/models/audit.py` | `PanelAuditEvent` (`panel_audit_events`, append only) and `AuditAction`, the action vocabulary as plain values rather than a database enum. Holds what `panel_login_attempts` does not: logging out, and everything done to documents and accounts once inside |
| `backend/app/models/user.py` | `User` (`users`) - email unique in the database, `password_hash`, `email_verified_at` |
| `backend/app/models/chat.py` | `ChatSession` (`chat_sessions`, nullable `user_id` for anonymous use), `Query` (`queries`, the token/cost ledger in USD and PLN, plus the `queries_answer_requires_kb_version`, `queries_cost_requires_model`, `queries_cost_requires_pricing_provenance` and `queries_measurements_non_negative` checks) |
| `backend/app/models/document.py` | `Document` (`documents`, identity only), `DocumentVersion` (`document_versions`, the immutable content snapshot: title, content, author, change comment, status, the `document_versions_one_published_per_document` partial unique index), `DocumentStatus` |
| `backend/app/models/knowledge.py` | `KnowledgeBaseVersion` (`knowledge_base_versions`), `KnowledgeGap` (`knowledge_gaps`), `KnowledgeGapStatus` |

## Migrations

Alembic owns every application table. `db/init/` is container bootstrap and never gains schema - see [`infra.md`](infra.md).

```bash
docker compose exec backend alembic upgrade head          # apply (the backend also does this on start)
docker compose exec backend alembic revision -m "..."     # new revision, then hand-write the ops (never the id)
docker compose exec backend alembic current               # which revision is applied
```

| Path | What's in it |
|---|---|
| `backend/alembic.ini` | Alembic config; `script_location`, `prepend_sys_path`, `file_template` (date in the filename, generated hash as the revision id), logging. No `sqlalchemy.url` on purpose |
| `backend/alembic/env.py` | Reads `DATABASE_URL` via `app.config`, sets `target_metadata` from `app.models.Base` |
| `backend/alembic/versions/0001_core_data_model.py` | First revision: the five tables, the `knowledge_gap_status` enum, indexes and constraints |
| `backend/alembic/versions/20260831_a2363c74818b_cost_ledger_pln_and_report_views.py` | Adds `queries.cost_pln`, `fx_rate_pln_per_usd`, `pricing_version`, the three cost check constraints, and the `query_costs` / `query_costs_monthly` reporting views |
| `backend/alembic/versions/6059ee904da3_panel_authentication.py` | Panel accounts: `panel_users`, `panel_sessions`, `panel_login_attempts`, `panel_password_resets`, the `panel_user_role` enum. Non-numeric revision id, chained onto the cost ledger revision: `feat/cost-ledger` branched from `0001` as well |
| `backend/alembic/versions/20260907_ebedc16a4160_document_content_and_versions.py` | Adds `documents` and `document_versions`, the `document_status` enum, and the `document_versions_one_published_per_document` partial unique index enforcing at most one published version per document |
| `backend/alembic/versions/20260908_c9a4d1f6b820_panel_two_factor.py` | Adds `panel_totp_secrets` (one row per account) and `panel_backup_codes`, both cascading from `panel_users`. Chained onto the audit log revision |
| `backend/alembic/versions/20260908_7b2e5c40a913_panel_audit_log.py` | Adds `panel_audit_events` with its three indexes and the `ON DELETE SET NULL` foreign key to `panel_users`. Chained onto the publication revision |
| `backend/alembic/versions/20260908_4f1c8a2b9d37_document_publication.py` | Adds `document_versions.published_at` and `published_by_id` (foreign key to `panel_users`, `ON DELETE SET NULL`) so who published a version and when survives any pruning of the change journal |

## Tests

`docker compose exec backend pytest`. See [`../testing.md`](../testing.md) for the full picture.

| Path | What's in it |
|---|---|
| `backend/tests/conftest.py` | `StubSession`, `client` (database stubbed), `raw_client`, `database_available`, `require_database`, `db_session` (rolls back), `migrated_database` (skips unless every mapped table is present), `committed_token` and `committed_query` (commit for real, then clean up), `BASELINE_USAGE` + `priced_usage`, `panel_db` (in-memory SQL), `panel_client`, `postgres_panel_client`, `cheap_password_hashing`, `make_panel_user`, `attempts_for`, `log_in` |
| `backend/tests/test_config.py` | `Settings` parsing: CORS origin splitting, whitespace, empty entries, defaults |
| `backend/tests/test_health.py` | `/health` and `/health/db` against a stub, plus integration tests against real PostgreSQL |
| `backend/tests/test_app.py` | Root route, OpenAPI schema, CORS headers, route uniqueness, `get_session` lifecycle |
| `backend/tests/test_models.py` | Schema guarantees: anonymous sessions, answer-needs-a-base-version, personal-data registry, ORM check constraints matching the migrated database, one migration head and no duplicate revision ids, plus integration round trips against real PostgreSQL |
| `backend/tests/test_documents.py` | Document/version guarantees (T-84): status defaults to draft, at most one published version per document, version numbers unique per document, deleting a document takes its versions, a referenced knowledge base version cannot be deleted, deleting an author account detaches the version instead of erasing it |
| `backend/tests/test_panel_two_factor.py` | The second factor (T-83): enrolling changing nothing until it is confirmed, the key returned in both forms, backup codes printed exactly once, a wrong code not turning it on, no encryption key storing nothing in the clear, the password alone stopping being enough, a live code getting in, the same six digits refused twice, a wrong code charged against the lockout, a printed code spent once and not opening another account, disabling needing a code, and the administrator's recovery path |
| `backend/tests/test_panel_audit.py` | The change journal (T-89): what gets recorded (create, save with its version number, publish, log out, a permission change naming who granted what), the login audit being read rather than copied, filtering by person across both sources, administrators only, no verb in the routing table that could change a line, and a failed journal write being logged instead of failing the operation |
| `backend/tests/test_document_publishing.py` | Publication and withdrawal (T-88): who and when recorded beside the status, the knowledge base version stamped onto the row, publishing a second version demoting the first (the flush-ordering trap), a second publish changing nothing, the index hook firing, a save never publishing, withdrawal keeping the provenance, withdrawing a draft refused, plus an `integration` class against the real partial index |
| `backend/tests/test_docx_import.py` | Reading a `.docx` (T-85) on packages the test builds itself with `zipfile`: headings keeping their structure, a paragraph whose style the file never defines still being read, tables reported rather than dropped, a non-docx and an empty file refused as the caller's mistake, the size limit checked before parsing, plus the endpoint's 401/422/413 and the fact that a preview writes nothing |
| `backend/tests/test_panel_documents.py` | Versioning behaviour (T-86/T-87): a save adds a row and leaves the previous one byte for byte, a new version is a draft even over a published one, restoring the first of three creates a fourth, a list row carries status/author/version without the body, and twenty documents cost a constant number of queries |
| `backend/tests/test_panel_columns.py` | That every limit matches the width of the column it names, and the one case the two helpers differ in: `truncated` answers `None` for a blank, `required` keeps a string. Both columns it guards are NOT NULL, where the first would trade an audit row for an IntegrityError |
| `backend/tests/test_panel_document_status.py` | That the published version travels beside the newest one everywhere the panel reports status: a list row and the editor screen carry both after a save, withdrawal clears it, and the join costs no extra query. Split from `test_panel_documents.py` at the size limit |
| `backend/tests/test_panel_documents_api.py` | The document endpoints as HTTP: no token is 401, an editor needs no admin role, the author comes from the token and never from the body, unknown ids answer 404 rather than 500, the input the boundary refuses (blank, over-long, NUL, a line break in a title), and an `integration` class proving two simultaneous saves take different version numbers |
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
| `backend/tests/test_pricing.py` | Price list parsing and refusals, exact decimals, reload after an edit, loud failure on a broken one, the shipped example still parsing |
| `backend/tests/test_usage.py` | Cost arithmetic in USD and PLN, `LedgerSession` double, write-once under concurrency, rollback leaving a row retriable, plus integration tests firing each cost constraint |
| `backend/tests/test_cost_reporting.py` | The `query_costs` and `query_costs_monthly` views: view inventory, no personal data, honest counts, Warsaw-time buckets read from the view itself |

## Where new things go

| Adding | Goes in | Then |
|---|---|---|
| An HTTP endpoint | `backend/app/routers/<domain>.py` | Include the router in `main.py`, add a row above |
| Business logic | `backend/app/services/<domain>.py` | Create the folder with the first file |
| A panel endpoint | `backend/app/routers/panel_*.py` | Guard it with `require_admin` or `current_panel_user` from `app/dependencies.py` |
| A database table | `backend/app/models/<domain>.py` | Import it in `models/__init__.py`, then add an Alembic revision |
| Request/response shape | `backend/app/schemas/<domain>.py` | Create the folder with the first file |
| A setting | `backend/app/config.py` | Also add it to `.env.example` |
| A model price | `backend/pricing.json` (not the code) | Copy the shape from `backend/pricing.example.json`; it reloads with no restart |
| A field holding personal data | wherever it belongs | Mark it `info=PERSONAL_DATA` so `personal_data_columns()` finds it |
