# Cost control

> Status: **measurement is built, limits are not.** The ledger, the configurable price list, the writer and the reports exist (T-41). No model is called yet, so every row still has NULL measurements and the reports honestly total zero. The limits below remain a design, and they are what still has to land before the first model call ships.

## The risk

The app is free, public, and promoted by a foundation. Model spend scales with traffic; the budget does not. Without server-side limits, one viral post or one script can produce a bill nobody planned for. Limits are a launch requirement, not an optimization.

## Layers to design

**1. Cheap rejections first.** Retrieval runs before generation, so an off-topic or unanswerable question never reaches the model. This is both a quality feature and a cost feature.

**2. Per-user limits.** Questions per session and per day. The counting unit is now decided and built: `chat_sessions.token`, an opaque identifier, with `user_id` nullable so an anonymous parent is counted the same way as a logged-in one. A quota that only applies to accounts is not a quota. Still open: whether the token is a cookie or client-side storage, and how much trivial resetting is worth tolerating against the GDPR cost of doing better. The token is treated as personal data, because a client identifier can identify a person.

**3. Global budget.** A hard ceiling on spend per day/month across all users, enforced server-side. When it is hit, the app degrades honestly - it tells the user the assistant is temporarily unavailable and points them at the foundation. It never silently fails or quietly keeps spending.

**4. Token bounds per call.** Cap input (how many passages, how much conversation history) and output length. Long histories are the usual source of surprise costs.

**5. Caching.** Parents ask overlapping questions; the knowledge base is fixed. Repeated or near-identical questions should be answerable without a new model call. Likely the single largest saving available.

**6. Model choice.** A smaller model is often enough when answers are grounded in supplied passages - the model is summarizing, not reasoning from scratch. Pick per task rather than defaulting to the largest.

**7. Visibility.** Log tokens and cost per request from day one. A limit you cannot observe is a limit you cannot tune, and the first week of real traffic is when you learn what the real numbers are. **This one is built**, and the rest of this file describes it.

## What exists: the cost ledger

One append-only row per question in `queries`, holding the model, input and output tokens, duration, and the cost twice over: `cost_usd` and `cost_pln`, both `NUMERIC(12,6)`.

Both currencies, because they answer different questions. The provider invoices in USD, so that column is what reconciles against the bill. The foundation approves and reads PLN (D11). Converting at report time would be wrong, not merely redundant: the rate moves, so the only honest PLN figure is the one from the day of the query. That is why `fx_rate_pln_per_usd` and `pricing_version` sit on the row too, and why the database refuses a cost that arrives without them.

Three check constraints carry rules that would otherwise be conventions someone forgets:

| Constraint | What it prevents |
|---|---|
| `queries_cost_requires_model` | A cost nobody can attribute, which silently drops out of every per-model sum |
| `queries_cost_requires_pricing_provenance` | A cost with no rate or price list behind it, which cannot be reproduced later |
| `queries_measurements_non_negative` | A negative figure, which hides another figure by cancelling it |

A measurement is written once. `record_usage` is a single conditional `UPDATE` that matches only a row with no measurement yet, so two writers racing on the same query end with one cost recorded and the other raising, rather than one silently replacing the other. Any failure rolls back, which leaves the row writable so the same measurement can be retried.

Unmeasured means `cost_pln IS NULL`, the same definition `query_costs_monthly` counts by. A row that names the model it chose before pricing succeeded is legal and still measurable, because `queries_cost_requires_model` only fires once a cost is present.

Revision 0001 shipped `cost_usd` as the only cost column, so a row from before this change can hold a cost with no rate beside it. The migration clears those figures rather than grandfathering them: a cost with no rate and no price list version cannot be reproduced or reported, so by this project's own standard it was never evidence, and inventing a retroactive rate to keep the number would manufacture some. Every environment then ends on the same schema, with all four constraints validated.

The measurement columns stay nullable on purpose. A question rejected as off-topic or over quota never reaches a model, and it still gets a row: the count of questions and the count of priced questions are both reported, and the gap between them is the cheap-rejection layer working.

**Nothing writes measurements yet**, because nothing calls a model. `app.services.usage.record_usage` is the call site retrieval and orchestration (T-30/T-40) plug into. It opens a session of its own, deliberately: usage is only known once the stream has finished, and by then the request's session is closed, so there is no caller transaction to join and none to commit or roll back on someone else's behalf.

## What exists: the price list

Prices are not in the code and must never be. They live in a JSON file whose path comes from `PRICING_FILE` (default `/app/pricing.json`, which the backend mount maps to `backend/pricing.json` on the host). `backend/pricing.example.json` documents the shape; the real file is gitignored, because it holds an operational rate and real provider prices.

```json
{
  "version": "2026-08-31",
  "currency": "USD",
  "fx_rate_pln_per_usd": "4.050000",
  "models": {
    "some-model": { "input_per_million": "0.150000", "output_per_million": "0.600000" }
  }
}
```

Four properties, each of which was a decision:

- **Amounts are strings**, parsed as `Decimal`. A JSON float reintroduces binary rounding into a figure the foundation signs off on.
- **An edit needs no deploy and no restart.** The file is read on every call and the cache is keyed by its contents, not by `stat()`. Timestamps are not trustworthy here: a bind mount or a network filesystem may report mtime only to the whole second, so a same-second edit that kept the byte count identical would be invisible.
- **A broken edit fails loudly** on the next request instead of falling back to the list it replaced. Quietly pricing traffic with superseded numbers corrupts the ledger for as long as nobody looks; a typo that breaks the next request gets found in seconds.
- **A model with no price is an error**, not a free call. Costing it at zero would understate exactly the report the foundation reads.

The exchange rate is set by the operator, not fetched. An auto-updated rate would make a figure reported last month impossible to reproduce this month.

## What exists: reading the numbers back

Two views, created by migration 0002. Both are free of personal data by construction: no question text, no session token, only ids and numbers, so a monthly report can be handed over without a scrubbing step first.

| View | Holds |
|---|---|
| `query_costs` | One row per query, joined to its session, with `report_day` and `report_month` |
| `query_costs_monthly` | The month total, which is the number D11 asks the foundation to approve |

Days and months are bucketed in `Europe/Warsaw`, not UTC. The reader's calendar month is the one that matters, and in summer a question asked at 01:30 on the first would otherwise be filed under the previous month.

```bash
python scripts/cost_report.py                  # per month, then the latest month per model, day and account
python scripts/cost_report.py --month 2026-09  # one month in detail
python scripts/cost_report.py --csv            # one row per query, for the T-02.2 spreadsheet
```

The `--csv` export is the feedback loop the card asks for: T-02.2 is a calculation for the foundation, and it is corrected by real rows rather than rewritten from the price list. The correction can only start once a model is actually called, so today the export runs and returns a ledger with no costs in it.

## Non-negotiable

Every one of these is enforced **server-side**. Nothing in the frontend is a limit; it is at most a hint.

## Open questions

- Concrete numbers: questions per user per day, daily global budget, max tokens per call.
- What the app shows when a limit is hit - same message for a personal limit and a global outage, or different?
- Are limits stricter for anonymous users than for someone who has given an email?

## When the limits get built

Measurement is in place, so fill in for each limit: the real number, where it is configured, how it is enforced server-side, and what the user sees when it fires. The numbers themselves come from T-02.3 and need the foundation's approval before anything reads them (D11).
