## What and why

<!-- A few sentences. What changed, and what problem it solves. -->

## Checklist

- [ ] I ran it. The stack starts and the change works, verified, not just read.
- [ ] `docker compose exec backend pytest` passes.
- [ ] `docker compose exec frontend npm test` passes.
- [ ] New behavior has a test. A bug fix has a test that fails without the fix.
- [ ] `python scripts/check_map.py` exits 0. Files added, moved, or deleted have their `docs/map/` row updated.
- [ ] `python scripts/check_text.py` exits 0. No em dashes, no en dashes.
- [ ] Affected `docs/` updated. New environment variable is in `.env.example`.
- [ ] Non-trivial change has an entry at the top of `docs/log.md`.
- [ ] No AI or tool authorship anywhere in the commits, code, or docs.

## Anything reviewers should know

<!-- Open questions, deliberate omissions, follow-up work. Delete if none. -->
