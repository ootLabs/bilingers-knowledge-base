# Cost control

> Status: **not implemented**, with one exception: the table that records the numbers exists. No model is called, so nothing costs anything yet. This is the project's biggest identified risk and needs a design before the first model call ships.

## The risk

The app is free, public, and promoted by a foundation. Model spend scales with traffic; the budget does not. Without server-side limits, one viral post or one script can produce a bill nobody planned for. Limits are a launch requirement, not an optimization.

## Layers to design

**1. Cheap rejections first.** Retrieval runs before generation, so an off-topic or unanswerable question never reaches the model. This is both a quality feature and a cost feature.

**2. Per-user limits.** Questions per session and per day. The counting unit is now decided and built: `chat_sessions.token`, an opaque identifier, with `user_id` nullable so an anonymous parent is counted the same way as a logged-in one. A quota that only applies to accounts is not a quota. Still open: whether the token is a cookie or client-side storage, and how much trivial resetting is worth tolerating against the GDPR cost of doing better. The token is treated as personal data, because a client identifier can identify a person.

**3. Global budget.** A hard ceiling on spend per day/month across all users, enforced server-side. When it is hit, the app degrades honestly - it tells the user the assistant is temporarily unavailable and points them at the foundation. It never silently fails or quietly keeps spending.

**4. Token bounds per call.** Cap input (how many passages, how much conversation history) and output length. Long histories are the usual source of surprise costs.

**5. Caching.** Parents ask overlapping questions; the knowledge base is fixed. Repeated or near-identical questions should be answerable without a new model call. Likely the single largest saving available.

**6. Model choice.** A smaller model is often enough when answers are grounded in supplied passages - the model is summarizing, not reasoning from scratch. Pick per task rather than defaulting to the largest.

**7. Visibility.** Log tokens and cost per request from day one. A limit you cannot observe is a limit you cannot tune, and the first week of real traffic is when you learn what the real numbers are.

The storage half of this is built: `queries` holds the model used, input and output tokens, cost as `NUMERIC(12,6)`, and duration, one append-only row per question. The measurement columns are nullable on purpose, so a question rejected as off-topic or over quota still gets a row and shows up in the counts. What is missing is anything that writes to it (T-41) and any limit that reads it.

## Non-negotiable

Every one of these is enforced **server-side**. Nothing in the frontend is a limit; it is at most a hint.

## Open questions

- Concrete numbers: questions per user per day, daily global budget, max tokens per call.
- What the app shows when a limit is hit - same message for a personal limit and a global outage, or different?
- Are limits stricter for anonymous users than for someone who has given an email?

## When this gets built

Fill in: the real numbers, where they are configured, how they are enforced, and where usage is logged.
