# Testing

Tests exist here for two audiences. A human needs to know a change is safe. An agent needs a signal it can read without a browser and without asking anyone: run a command, get a verdict. That second audience is why coverage gates and a smoke test are wired in from the skeleton stage rather than "later".

## Run everything

```bash
docker compose exec backend pytest                  # backend, with coverage gate
docker compose exec frontend npm test               # frontend unit tests
docker compose exec frontend npm run typecheck      # TypeScript, no emit
python scripts/smoke_test.py                        # the running stack, end to end
python scripts/check_map.py                         # docs/map matches reality
python scripts/check_text.py                        # no banned characters
```

The last two also run from the pre-commit hook. All of them run in CI on every pull request.

## The layers, and what each one catches

| Layer | Where | Catches | Needs a database |
|---|---|---|---|
| Unit | `backend/tests/test_config.py`, `test_app.py` | Parsing, wiring, resource lifecycle | no |
| API | `backend/tests/test_health.py` (stubbed) | Status codes, payload shapes, CORS | no |
| Panel | `backend/tests/test_panel_*.py`, `test_rate_limit.py` | Login, lockout, per-IP throttle, sessions, resets, roles, and what a dropped connection answers - real SQL, in memory | no |
| Integration | `backend/tests/` marked `integration` | Real SQL, real driver, migrated schema, database constraints | yes |
| Component | `frontend/app/*.test.tsx` | Rendering, Polish copy, config fallbacks | no |
| Type | `npm run typecheck`, `npm run build` | Type errors, broken imports, build failures | no |
| Smoke | `scripts/smoke_test.py` | The stack is genuinely up and answering | yes, running |
| Repository | `scripts/check_map.py`, `check_text.py` | Stale map, banned characters | no |

Most of it runs with nothing else started, which is the point: an agent gets feedback in seconds instead of waiting on containers.

## Integration tests

Marked `@pytest.mark.integration` and dependent on the `require_database` fixture, which **skips** rather than fails when PostgreSQL is unreachable. So `pytest` works on a laptop with nothing running, and still exercises real SQL when the stack is up.

```bash
docker compose exec backend pytest -m "not integration"   # skip them explicitly
docker compose exec backend pytest -m integration         # only them
```

CI always runs them, against a real PostgreSQL service container with `db/init/` applied and `alembic upgrade head` run against an empty database. A skipped integration test in CI would defeat the purpose, and the migration step doubles as the only honest test that migrations work from zero.

Panel authentication is the one area that runs against a database in *both* layers. Its behaviour (who gets in, what a lockout does, which sessions survive a password change) runs on an in-memory SQLite database built from the same models, through the `panel_db` fixture: a stub cannot answer any of those questions, and putting all of it behind `integration` would remove the panel from every run that has nothing started. What is specifically PostgreSQL's (the migration chain, the unique constraint on an address, the role stored as a value rather than a member name, an attempt that survives its own failed login) is asserted against PostgreSQL in the `integration` classes. A rule enforced by the database belongs in the second group, not the first.

Tests that need the migrated schema also depend on a `migrated_database` fixture, which skips with the command to run when the database is up but the tables are not there. It checks every mapped table, not just that `alembic_version` exists: a database migrated by another branch has that table and part of the schema, and the point is an actionable skip rather than a hard failure on a missing table. Same reasoning as above: a laptop with a stale volume gets the skip, while CI always migrates first so nothing is quietly skipped there.

A constraint asserted only in Python is not a constraint, so `test_models.py` checks the important ones twice: once against the mapper (fast, no database) and once by making PostgreSQL reject the bad row. Those integration tests match on the constraint *name*, because a test that passes when some unrelated rule fires is worse than no test.

## Coverage

Backend is gated at 90% in `backend/pytest.ini` and currently sits at 100%. Below the gate, `pytest` fails.

Frontend thresholds are in `frontend/vitest.config.ts`, set just under what the suite achieves so a regression trips the build. The branch threshold is deliberately lower than the rest: v8 counts branches in transpiled JSX that no test can reach, and writing fake tests to satisfy that number would hide more than it reveals.

Coverage is a floor, not a goal. A hundred percent of trivial assertions proves nothing. Cover the thing that breaks.

## Writing a new test

- **A bug fix gets a test that fails without the fix.** Otherwise nothing stops it coming back.
- **Test behavior, not implementation.** Asserting that an endpoint returns the right payload survives refactoring; asserting which private function was called does not.
- **Say why in the docstring** when a test guards something non-obvious, like liveness having to answer while the database is down.
- New backend test file goes in `backend/tests/`, named `test_<module>.py`, with a row in `docs/map/backend.md`.
- New frontend test sits next to its component as `<Name>.test.tsx`, with a row in `docs/map/frontend.md`.

## CI

`.github/workflows/ci.yml` runs four jobs on every pull request: repository checks, backend tests against real PostgreSQL, frontend typecheck plus tests plus production build, and the stack smoke test. The smoke job builds and starts all three containers exactly as a developer would, then talks to them over HTTP. It dumps container logs when it fails, because a red smoke job with no logs tells you nothing.

Making these checks **required** is a GitHub setting, not a file in this repository. Enable branch protection on `main` with all four jobs required, or CI stays advisory and someone will merge past it.

## Not here yet

No end-to-end browser tests (Playwright), no load tests, no contract tests. None are worth their maintenance cost while the product is a skeleton. The moment there is a real chat flow to click through, revisit the browser layer, starting with the one path that matters: ask a question, get a grounded answer.
