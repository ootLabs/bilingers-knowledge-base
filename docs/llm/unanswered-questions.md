# Unanswered questions

> Status: **not implemented**, except the queue itself. `knowledge_gaps` exists (question text, status `new` / `in_progress` / `resolved`, optional link to the query it came from). Nothing writes to it and nothing reads it yet: that is T-33 on the detection side and T-80 on the review side.

## Why this matters

A knowledge base with a clear boundary will be asked things outside it - constantly. Handling that honestly is a feature of this product, not an edge case: it protects users from invented advice, and it feeds the foundation a list of what parents actually want to know.

## The intended flow

1. Retrieval finds nothing above the relevance floor (see [`retrieval.md`](retrieval.md)).
2. The app says plainly that the knowledge base does not cover this, and that a foundation specialist can answer.
3. The question is routed to the foundation - a mailbox is the agreed direction; the address is still to be decided.
4. The specialist answers.
5. The answer is added to the knowledge base, so the next person gets it immediately.

Step 5 is what makes this a growth loop rather than a dead end. It needs the admin panel and the ingestion path from [`knowledge-base.md`](knowledge-base.md).

## Open questions - mostly GDPR

The team explicitly does not want to collect personal data it does not need. That constrains the design:

- **How do we contact the person with the answer?** An email address is the obvious route and the most data we would hold. Is it optional - answer goes to the base regardless, and the address only exists if the user wants a personal reply?
- **Consent wording** for storing an address, and how long it is kept.
- ~~**Can the question be stored without any identity at all?**~~ **The schema already assumes yes.** `knowledge_gaps` keeps its own copy of the question text and links to the originating query with `ON DELETE SET NULL`, so erasing the query, the session, and the person leaves the question standing. "What are parents asking" survives; who asked it does not have to.
- **Free-text questions may contain personal details** about a child, volunteered by the parent. What is retained, and for how long? The columns are already marked as personal data (`queries.question`, `queries.answer`, `knowledge_gaps.question`), so the retention job has a list to work from; the period itself waits on B-07.
- Where do the questions land: a mailbox, an admin queue in the app, or both?
- Rate limiting and spam handling on whatever collects them.

## Design bias

When two designs both work, pick the one holding less personal data. The default should be: store the question, not the person.

## When this gets built

Fill in: the destination address, the exact consent text, retention periods, and the path from a specialist's answer back into the knowledge base.
