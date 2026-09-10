# Architecture - Bilingers

> Overview for humans and for the coding agent. Written in English. Keep it short and concrete; update it when the structure changes.

## Overview

A free educational app for parents and carers raising a bilingual child. The user talks to an AI assistant answering **only** from the Bilingual Future Foundation knowledge base, then optionally takes a quiz that can end in a certificate.

Target flow (most of it not built yet): the user opens the app → reads a short intro → picks one of 3-5 suggested starter questions or types their own → the backend retrieves matching passages from the foundation's knowledge base → the model answers from those passages only → the app proposes 3-5 deeper follow-up questions → after some conversation the user can take a ~10-question quiz → passing issues a certificate.

**What exists today:** three containers, health endpoints, the core relational data model with migrations, a stubbed streaming `POST /chat`, a frontend routing skeleton with a Polish-only translation layer and design tokens, and this documentation frame. The chat, quiz, and account routes exist but hold placeholder copy only. Everything about retrieval, real model calls, quiz logic, and certificates is design, not code - see `docs/llm/`.

## Main modules

| Module | Responsibility | Path |
|---|---|---|
| Frontend | UI, conversation view, quiz screens (Polish copy) | `frontend/app/` |
| Frontend API client | The only browser-to-backend call site, and the failure vocabulary every screen reacts to | `frontend/lib/api-client.ts` |
| Backend API | HTTP layer, one router per domain | `backend/app/routers/` |
| Backend config | Environment-driven settings | `backend/app/config.py` |
| Persistence | SQLAlchemy engine + session dependency | `backend/app/db.py` |
| Panel authentication | Editor accounts, roles, sessions, password resets, the second factor | `backend/app/services/panel_*.py` |
| Knowledge base editing | Documents and their immutable versions: writing, reading, publishing, importing a `.docx` | `backend/app/services/document*.py`, `docx_import.py` |
| Change journal | Who did what in the panel, read-only, merged with the login audit | `backend/app/services/panel_audit.py` |
| Panel frontend | The foundation's own screens: login, documents, editor, history, import, journal, second factor | `frontend/app/panel/`, `frontend/lib/panel-*.ts` |
| Data model | Tables, constraints, personal-data marking | `backend/app/models/` |
| Migrations | Schema history; applied before the app starts | `backend/alembic/` |
| Database bootstrap | Health probe only, run once on an empty volume | `db/init/` |
| Orchestration | Service definitions, ports, volumes, healthchecks | `docker-compose.yml` |

File-level detail lives in [`map/`](map/README.md) - one file per area, so finding code doesn't mean reading this document.

## Data flow

Today:

```
browser → frontend (Next.js, :3000) → backend (FastAPI, :8000) → postgres (:5432)
```

The frontend reaches the backend through `NEXT_PUBLIC_API_URL`, which must be a host-reachable URL because the browser makes the call. Backend → database uses `DATABASE_URL`, whose host is the compose service name `db`, resolvable only inside the compose network.

`POST /chat` exists but is plumbing, not the AI layer: it writes the question to `queries`, then streams back a fixed placeholder string, chunk by chunk. No retrieval, no model call, no orchestration - see `docs/llm/README.md`'s non-negotiables. Planned addition, once the AI layer lands: retrieval and a real model call replace the placeholder, plus quota checks before either. Sketched in `docs/llm/retrieval.md` and `docs/llm/cost-control.md`.

On the browser side the stream is consumed by `frontend/lib/api-client.ts` and rendered by
`app/chat/ChatPanel.tsx`. Because the backend streams translation keys rather than prose, the
frontend copy layer is what turns an answer into Polish; a key it cannot resolve is dropped
rather than printed, and a stream in which nothing at all resolves becomes a failure rather
than a blank reply. Every HTTP failure collapses into one of four `ChatFailure` values before
any component sees it, and the body of a failed response is never read.

## Data model

Seven tables, in `backend/app/models/`. Each one exists because a product decision needs it, not because it rounds out a diagram. (Panel accounts add four more, documented separately through the ADR entries below rather than in this table.)

| Table | Exists for | Notes |
|---|---|---|
| `users` | The larger question quota for someone with an account | Email uniqueness is a database constraint. No authentication logic yet |
| `chat_sessions` | Counting questions, account or not | `user_id` is nullable; the opaque `token` is what gets counted |
| `queries` | Cost reporting and quality regression | Append-only. Question, answer, model, tokens, cost in USD and PLN with the rate and price list behind it, duration |
| `knowledge_base_versions` | Tracing an answer to the exact content behind it | Version, ingest time, record count, source checksum |
| `knowledge_gaps` | The queue of what the base could not answer | Survives deletion of the query it came from |
| `documents` | A document's stable identity | Never updated; append-only, `created_at` alone |
| `document_versions` | The document's actual content, one immutable snapshot per edit | Title, content, author, change comment, status (`draft`/`in_review`/`published`/`withdrawn`), optional link to the `knowledge_base_versions` ingest that published it |

```
users 1--0..n chat_sessions 1--0..n queries 0..1--1 knowledge_gaps
                                       n--0..1 knowledge_base_versions
documents 1--0..n document_versions n--0..1 knowledge_base_versions
```

Several constraints carry decisions rather than hygiene, so they live in the database instead of in application code:

- `chat_sessions.user_id` is **nullable**. Anonymous parents have to be countable or the quota is decorative.
- `queries` carries `CHECK (answer IS NULL OR knowledge_base_version_id IS NOT NULL)`. An answer that cannot name the base version behind it becomes unexplainable the moment the base changes, and the base is expected to change indefinitely.
- `queries` also refuses a cost with no model to attribute it to (`queries_cost_requires_model`), a cost without the rate and price list that produced it (`queries_cost_requires_pricing_provenance`), and any negative measurement (`queries_measurements_non_negative`). "Summable per model" and "reproducible in PLN" are promises the report makes to the foundation, so they are enforced where the rows are, not where the writer is.
- `document_versions` carries a partial unique index, `document_versions_one_published_per_document` (`UNIQUE (document_id) WHERE status = 'published'`). At most one version of a document may be published at a time, which is what makes "the chat reads only published content" (T-88) a question the database answers rather than a rule a service has to remember. A `published_version_id` pointer on `documents` was rejected: it would need a circular foreign key between the two tables and a second place the same fact could go stale.

Two views, `query_costs` and `query_costs_monthly`, are the read side. They carry no personal data by construction, so a monthly figure can be handed to the foundation without a stripping step. See `docs/llm/cost-control.md`.

**Personal data** is marked at the column level with `info=PERSONAL_DATA`, and `personal_data_columns()` derives the list from the metadata. Retention periods are deliberately not implemented: they depend on GDPR decisions that have not been made yet.

The intended erasure model is **scrubbing marked columns rather than deleting rows**, because spending and "what are parents asking" are facts about the service, not about the individual. The foreign keys pointing at a person already follow it: deleting a `users` row clears `chat_sessions.user_id`, and deleting a `queries` row clears `knowledge_gaps.query_id`, in both cases leaving the surrounding record intact. `queries.chat_session_id` cascades instead, which is safe only because deleting a session row is administrative cleanup and not how a person's data is erased.

## Key decisions (lightweight ADR)

| Date | Decision | Why |
|---|---|---|
| 2026-08-05 | Stack: Next.js + FastAPI + PostgreSQL, orchestrated by Docker Compose | Clean split between UI and AI/data logic; Python is where the retrieval and model tooling lives; one command to start the whole thing on any machine |
| 2026-08-05 | Skeleton first - no vector DB, no LLM SDK, no model calls | Lock the shape of the system before adding moving parts that are expensive to change and expensive to run |
| 2026-08-05 | Plain PostgreSQL, no vector extension | Nothing needs vectors yet. When retrieval arrives, evaluate `pgvector` in this same container before adding a fourth service |
| 2026-08-05 | Dev-mode containers with host bind mounts and hot reload | Fast feedback while the shape is still moving; production images are a separate, later concern |
| 2026-08-05 | Bootstrap SQL in `db/init/`, no migration tool | One table, no history to preserve. Introduce Alembic when the first real schema change appears. **Superseded 2026-08-25** |
| 2026-08-05 | Stay on FastAPI rather than Django/DRF | The core interaction is a streamed chat response over async I/O, which Starlette does natively; Django's main draw here was the free admin panel, and that is one secondary screen, buildable in Next.js against the same API |
| 2026-08-05 | `AGENTS.md` as the single source of agent rules; `CLAUDE.md` imports it, `.cursor/rules/` points at it | Duplicated rules drift apart silently, and then each tool behaves differently on the same repo |
| 2026-08-05 | Repository map split by area in `docs/map/`, enforced by `scripts/check_map.py` | A single map file forces a frontend change to load backend rows; an unenforced map goes stale and then actively misdirects |
| 2026-08-05 | Capped log (`docs/log.md`, 20 entries) instead of an unbounded journal | The journal was auto-loaded every session and grows without limit - ~35k tokens per session at 100 entries, paid even to edit one CSS variable |
| 2026-08-05 | Tests and CI from the skeleton stage, with coverage gates | Agents need a signal they can read without a human; a suite added "later" never covers the foundations |
| 2026-08-05 | Integration tests skip instead of failing when PostgreSQL is unreachable | Keeps the suite usable with nothing running, while CI always has a real database so nothing is quietly skipped there |
| 2026-08-05 | Smoke test drives the real containers over HTTP | Unit tests pass on a machine where nothing starts; this is the check that answers "it works on my machine" |
| 2026-08-05 | Two long-lived branches: `main` as production, `dev` as integration | Keeps `main` a readable release history and gives changes somewhere to accumulate and be tested together before they are called a release |
| 2026-08-21 | Frontend translation layer is a custom dictionary lookup (`lib/i18n/`), not a library like `next-intl` | Only one locale ships today and no runtime locale switch exists yet; a library buys nothing the app uses. Adding a locale is one file plus one registry line in `translations.ts`, and TypeScript rejects a translation file whose keys do not match `locales/pl/` |
| 2026-08-21 | Design tokens in `globals.css` use the Bilingers-based palette proposed in T-03, marked provisional in a comment at the top of the file | T-03 left open whether the chat's brand is the foundation, Bilingers, or both, and both the foundation and Bilingers have two conflicting visual variants in the source material. Bilingers was picked as the working default because T-03 frames the chat as that app's vestibule, not because the question is resolved |
| 2026-08-25 | Alembic, applied by the backend container on start | The first real schema change arrived, which is the trigger the 2026-08-05 decision named. Running it as part of the start command is what makes "works on a clean database with no manual steps" true rather than aspirational |
| 2026-08-25 | Alembic owns every application table; `db/init/` keeps only the health probe | Two mechanisms defining schema is two sources of truth. `db/init/` cannot be the one that wins: it runs only on an empty volume, so it silently does nothing on every machine that already has data |
| 2026-08-25 | Cost stored as `NUMERIC(12,6)`, never a float | This figure goes to the foundation for approval (D11). Accumulated float error in a number someone is asked to sign off on is not acceptable |
| 2026-08-25 | Personal data marked in the model with `info=PERSONAL_DATA`, retention unimplemented | Marking is cheap now and expensive to retrofit across a grown schema. Retention periods depend on GDPR answers nobody has yet, and inventing them would look like compliance without being it |
| 2026-08-25 | GDPR erasure scrubs marked columns; person-facing foreign keys clear rather than cascade | Deleting a person must not delete the spending record or the list of what parents ask. Those are aggregate facts about the service, not facts about the individual |
| 2026-08-26 | `POST /chat` writes its `Query` row and commits before the response starts streaming | A connection dropped mid-answer must not leave the question unlogged for T-41's cost ledger; committing before any bytes stream is what guarantees that regardless of how the stream ends |
| 2026-08-26 | `/chat` streams a fixed sequence of opaque placeholder chunks rather than calling a model | T-12 is explicitly the pipe, not the engine (no RAG, no orchestration, no guardrails yet); the `answer` column also cannot be set without a `knowledge_base_version_id`, which does not exist until ingestion (T-01) runs. Keys, not prose, so the placeholder does not itself violate "the backend returns data and keys, not sentences" while it is standing in for a real answer |
| 2026-08-26 | `app.services.chat` raises `ChatServiceUnavailable` or `InvalidChatInput` instead of letting `SQLAlchemyError` reach the router | Sets the precedent for every future DB-backed router: `docs/conventions.md` requires services to raise domain exceptions and routers to translate them. The two exceptions map to different HTTP statuses (503 vs 422) because a bad connection and a rejected question are not the same failure and should not both cause a client to retry blindly |
| 2026-08-28 | Panel accounts live in `panel_users`, separate from the parent-facing `users` table | Same word, different threat model: a parent's account unlocks a question quota, an editor's unlocks 30 years of research under an NDA. One table would make any bug on the quota path a knowledge base leak |
| 2026-08-28 | Panel sessions are opaque tokens in an `Authorization: Bearer` header, stored only as a SHA-256 hash, with an absolute 12 hour expiry | A hash means a database dump does not hand over live sessions. A header rather than a cookie because the panel frontend does not exist yet (T-86), so the CSRF and SameSite decisions that come with a cookie can be made when there is a client to make them for. Absolute rather than idle expiry: a sliding window writes to the database on every request to the most sensitive screen in the system |
| 2026-08-28 | No registration form and no self-service password reset; an administrator creates accounts and issues one-time tokens | The panel holds three to five accounts for the life of the project, so a registration form is attack surface bought for nothing. A "forgot my password" endpoint would mint a token with no way to deliver it: there is no mail path yet. Revisit the second half when mail exists |
| 2026-08-28 | Five failed logins lock the account for fifteen minutes; every attempt is recorded, including for addresses that match no account | An attack on a five-account panel looks like repeated failures against addresses that do not exist, and that pattern is invisible if only real accounts are logged. The counter lives on the account, not in the audit table, so pruning the audit cannot quietly disable the limit. **Superseded 2026-09-02** |
| 2026-08-26 | `ChatRequest.session_token` requires 32-64 lowercase hex characters | The token is the only key to a conversation and a future D5 quota; `min_length=1` let two unrelated clients collide into the same `ChatSession` and its `PERSONAL_DATA`-marked questions by both picking a short token |
| 2026-08-31 | Cost stored in both USD and PLN, with the exchange rate and price list version on every row | The provider invoices in USD and the foundation approves PLN (D11), so both are real figures rather than one derived from the other. Converting at report time would silently restate history, because the rate moves; the row keeps the rate that actually applied |
| 2026-08-31 | Model prices live in a JSON file read at runtime, not in code or a database table | A provider price change must not need a deploy, and a table would need an admin surface that does not exist. The file re-reads on change; a broken edit fails the next request loudly instead of quietly serving the prices it replaced |
| 2026-08-31 | A measurement is written by one conditional `UPDATE`, in a session the writer owns | A read-then-write guard lets two concurrent writers both pass it and one silently replace a cost that was already reported; the `UPDATE`'s own `WHERE` cannot be raced. The session is not the caller's, because usage is only known after the stream ends, when the request session is closed, and committing or rolling back someone else's transaction would discard whatever they had pending |
| 2026-08-31 | The cost ledger revision clears pre-existing costs that have no rate behind them, rather than adding the provenance constraint `NOT VALID` | A cost with no rate and no price list version cannot be reproduced, so it was never evidence and nothing is lost by clearing it, whereas inventing a retroactive rate would manufacture some. An unvalidated constraint would also leave `pg_dump` permanently disagreeing with `app.models.chat`, so a database built from metadata and one built from migrations would enforce different rules |
| 2026-08-31 | Reporting is SQL views plus a script, not an API endpoint | There is no admin panel and no auth, so an endpoint exposing spend would be a public one. A view is also what the foundation's own calculation (T-02.2) can be corrected from, via `scripts/cost_report.py --csv` |
| 2026-09-02 | The frontend reduces every backend failure to a closed set of four `ChatFailure` keys, and never reads a failed response's body | A failing backend's body can name the model provider or quote the system prompt, which T-63 forbids showing a parent and T-52 treats as an attack surface. A status the backend starts returning that is not in the set degrades to `unreachable` instead of reaching the screen as an unhandled shape |
| 2026-09-02 | `app/error.tsx` never binds the thrown `Error` it is handed | Its message and digest are the likeliest carriers of a stack trace, an internal hostname or a provider name anywhere in the frontend. Not destructuring it is a structural guarantee; remembering not to render it is not |
| 2026-09-02 | 429 is mapped to the limit state before anything emits it | The anonymous quota is T-71/T-73, but T-63 owns what a parent sees when it trips, and a state nobody can reach is a state nobody has tested. The counter lands later without touching the client |
| 2026-09-02 | State tone is a left border plus copy, never colored text; `--color-danger` is border-only | `--color-primary` already fails WCAG AA on white (see the note at the top of `globals.css`), so tinting status text would spread that debt rather than contain it. Border-only use also means the 3:1 non-text threshold applies, which the token clears in both light and dark |
| 2026-09-07 | Document content lives on `document_versions`, not `documents`; `documents` carries only an id and `created_at` | A version is the immutable snapshot the card requires, so title and content have to live where editing them means inserting a new row, not updating an existing one. A status or title on `documents` too would be a second place the same fact could disagree with the version that actually holds it |
| 2026-09-08 | The panel's second factor is TOTP, and the code travels in the same request as the password rather than behind a challenge token | TOTP costs nothing, depends on no operator, and stores no phone number, which matters in a project where GDPR work has not started (B-07). Sending the code with the password means every attempt at it is a full login attempt, so the per-IP throttle and the per-account lockout that already guard that endpoint apply to it automatically; a separate challenge endpoint would have needed both reimplemented, and six digits with no limit behind them is a weaker factor, not a second one. No 2FA for parents: their accounts unlock a question quota, and the friction would cost the conversion D5 depends on |
| 2026-09-08 | TOTP secrets are encrypted with a key from the environment, and there is no default key | A secret has to be readable to verify a code, so hashing it is impossible; encryption is what stops a database dump alone handing over the second factor. A default key shipped in the repo would be the same as no encryption while looking like some, so an empty `PANEL_TOTP_ENCRYPTION_KEY` refuses enrolment outright rather than storing a secret in the clear. Backup codes go the other way: they are 60-bit tokens, so SHA-256 like a session token, which also makes verification one indexed lookup instead of ten bcrypt comparisons |
| 2026-09-08 | Everything the panel's error copy needs from a failed response travels in the `X-Second-Factor` header, not in the error body: `required` for "this account needs a second factor", `not-configured` for "this deployment has no encryption key" | The frontend never reads a failed response's body (2026-09-02), and that rule is worth more than the convenience of reading `detail`. The cost is one entry in the CORS `expose_headers` list, which is visible in `app/main.py` rather than hidden in a client that quietly started parsing error payloads. The second value exists because a missing key and a database outage are both 503 on the same endpoints, and the copy differs in what it asks the editor to do: wait, or write to whoever runs the system. Status alone cannot carry that, and a 500 or a bespoke status for a configuration fault would be lying about whose fault it is |
| 2026-09-08 | Publication is the only thing allowed to update an existing `document_versions` row, and only its `status`, `published_at`, `published_by_id` and `knowledge_base_version_id` columns | The content of a version stays immutable, which is what makes a factual error rollable back at all. But "published" is a state a row moves through, not a new snapshot: minting a copy of the text to record that it went live would double every document and leave two rows claiming to be the same version. Keeping that update in one module (`app.services.document_publishing`) is what stops the exception spreading; `app.services.documents` still writes nothing but INSERTs |
| 2026-09-08 | Who published a version and when live on `document_versions`, not only in the change journal | Same reasoning as the login counters sitting on `panel_users` rather than being counted from `panel_login_attempts`: the journal's retention is an open GDPR question (B-07), and "who put this in front of parents" must not stop being answerable the day it is pruned |
| 2026-09-08 | T-88 leaves one function (`app.services.knowledge_index.record_index_change`) where the retrieval index will attach, doing nothing today but writing a log line | Chunking (T-21) and embeddings (T-22) are blocked on the first ingest (T-01) and on the NDA (B-09). An interface with one implementation behind it would be a guess at the shape of code nobody has written; a function that gains a body later is not. It is called inside the publication transaction today, and moving it out is part of T-22, because an index write that can roll back a publication would make an editor's click depend on a service that is not the database |
| 2026-09-08 | The panel holds its session token in `sessionStorage` and sends it as `Authorization: Bearer`, rather than in an HttpOnly cookie | T-82 deferred the CSRF and SameSite questions until a panel client existed to make them for, and this is that client. A bearer header keeps the backend exactly as it was built and carries no CSRF surface of its own, because nothing is sent automatically with a cross-site request. What it costs is XSS exposure: any script running on the page can read the token, which an HttpOnly cookie would prevent. `sessionStorage` rather than `localStorage` narrows that to the life of the tab, so a shared machine does not keep a live session for the next person. Moving to a cookie needs the backend to set, read and expire one, plus a CSRF token and a SameSite policy, so it is its own card and is queued with T-83 |
| 2026-09-08 | The panel's failure vocabulary is a second closed union (`PanelFailure`), in its own client file, rather than an extension of `ChatFailure` | The two paths refuse for different reasons: 401, 403 and 409 are real answers in the panel and meaningless to a parent, and the parent's quota (429 as `limit_reached`) does not exist in the panel at all. One union covering both would have every screen handling keys it can never see. `API_URL` is imported from `lib/api-client.ts` rather than redefined, because two copies of that fallback would let the panel and the landing page point at different backends |
| 2026-09-07 | A document version's author is a foreign key to `panel_users`, not free text | `panel_users` (T-82) already exists and its own model commits to this: accounts are deactivated rather than deleted specifically so the audit trail (T-89) can keep pointing at a real account. `ON DELETE SET NULL` matches the existing `panel_login_attempts.panel_user_id` precedent: the content must outlive the account that wrote it |
| 2026-09-09 | Both document responses carry `published_version` beside `latest_version`, and the panel's status pill reports the state of the DOCUMENT rather than of its newest version | They are different questions with different answers from the first save onwards, and a screen that answers only the second one lies about the first. Reporting the newest version alone meant one edit to a published document flipped the pill to "szkic", removed the warning about editing what parents read, and had the publication controls state that parents could not see a document that was still being served. The published version is joined into the list query rather than fetched per row, which the partial unique index makes safe: at most one published version per document, so the join cannot multiply a row |

## Integrations / external dependencies

None yet. No third-party API is called and no API key exists in the project.

Expected later, each needing its own section here when it lands:

- an LLM provider for the assistant,
- a mail path for questions the knowledge base cannot answer (address to be agreed),
- links out to Bilingers.app and the shop.

## Open questions

Product decisions still unsettled; they affect what gets built:

- Is the certificate itself valuable to a parent, or is the knowledge the whole value?
- How are contact details collected for unanswered questions, under GDPR, while collecting as little personal data as possible?
- Where does the app live - standalone domain or part of an existing Bilingers property?
- Which mail path delivers a panel password reset, so an editor stops depending on an administrator to hand them a token?
