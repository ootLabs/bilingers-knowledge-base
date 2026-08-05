# Retrieval

> Status: **not implemented.** No vector database, no embeddings, no search of any kind exists in this repo.

## The job

Given a user's question, find the passages from the foundation's knowledge base that actually answer it - and nothing else. The generation step can only be as good as this step; a grounded model with the wrong passages gives a confidently wrong answer.

## Decisions still open

- **Method.** Keyword/full-text search, vector similarity, or both (hybrid)? Don't assume vectors are required - a small, well-structured knowledge base often does better with full-text search plus good metadata, and it is far cheaper to run and debug.
- **Where it lives.** PostgreSQL already runs in this project. Full-text search is built in; `pgvector` is an extension to the same container. Adding a separate vector service is a last resort, not a starting point.
- **Chunk size.** Depends on the content's natural granularity - see [`knowledge-base.md`](knowledge-base.md).
- **How many passages** to pass to the model, and what to do when the best match is still weak.
- **Relevance floor.** Below what score do we treat the question as unanswerable? This is the switch that triggers [`unanswered-questions.md`](unanswered-questions.md), and setting it too low is how hallucination gets in.
- **Language handling.** Retrieval must not mix languages silently - see [`i18n.md`](i18n.md).

## Constraints

- Passages returned to the generation step must carry their source reference, so answers can cite and so a bad answer can be traced back.
- Retrieval runs **before** any model call, so a question with no good match costs nothing at the provider.
- The relevance floor is a product decision as much as a technical one: refusing to answer is the correct behavior, and it must be cheap and easy to tune.

## When this gets built

Fill in: the chosen method and why, chunking rules, the relevance threshold and how it was calibrated, and where the code lives.
