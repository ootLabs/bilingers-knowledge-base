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
| Integration | `backend/tests/` marked `integration` | Real SQL, real driver, bootstrap schema | yes |
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

CI always runs them, against a real PostgreSQL service container with `db/init/` applied. A skipped integration test in CI would defeat the purpose.

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
