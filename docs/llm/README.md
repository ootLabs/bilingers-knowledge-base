# LLM wiki — Bilingers

> **Nothing here is implemented.** These are design notes for the AI layer: decisions to make, constraints to respect, and the shape we expect the code to take. Written in English, like the rest of the repo.
>
> Rule of this wiki: **the note comes before the code.** Before building a piece of the AI layer, fill in the matching file — the open questions, the chosen approach, the reason. After building it, update the file to describe what actually exists and link the code from `CLAUDE.md` → "Project map".

## Files

| File | Covers |
|---|---|
| [`knowledge-base.md`](knowledge-base.md) | Source content from the foundation: format, ingestion, updates, ownership |
| [`retrieval.md`](retrieval.md) | Finding the right passages for a question (the "R" in RAG) |
| [`prompts.md`](prompts.md) | System prompt, grounding rules, suggested-questions generation |
| [`cost-control.md`](cost-control.md) | Rate limits, token budgets, caching — the top project risk |
| [`unanswered-questions.md`](unanswered-questions.md) | What happens when the knowledge base has no answer |
| [`quiz-certificate.md`](quiz-certificate.md) | Quiz design, scoring, what the certificate claims |
| [`evaluation.md`](evaluation.md) | How we know the answers are good, and stay good |
| [`i18n.md`](i18n.md) | Multi-language readiness across content, retrieval, and UI |

## The non-negotiables

These come from the product, not from engineering taste. Every design decision in this wiki is checked against them.

1. **Grounded only.** The assistant answers from the foundation's knowledge base and nothing else. No general-knowledge fallback, no plausible-sounding improvisation. Hallucination outside the base is the second-biggest risk in the project.
2. **Honest about not knowing.** "I don't have this in the knowledge base — a foundation specialist can answer" is a correct, expected outcome, not a failure to engineer around.
3. **Cost is bounded by design.** Spend must not scale freely with traffic. Limits are enforced server-side before any model call, not by hoping usage stays small.
4. **Minimal personal data.** GDPR is a hard constraint, and the audience is parents talking about their children. If a feature works without collecting an identity, it collects none.
5. **The certificate is soft.** It attests that someone learned the basics — never that they are a competent parent. Wording matters; see `quiz-certificate.md`.
6. **Multi-language from the start in structure**, Polish first in content. Never hardcode Polish outside the frontend copy layer.

## Current state

| Piece | State |
|---|---|
| Knowledge base content | Being written by the foundation; not in this repo |
| Ingestion pipeline | Not started |
| Retrieval | Not started; no vector database exists |
| Model integration | Not started; no SDK, no API key, no provider chosen |
| Quota / cost controls | Not started |
| Quiz & certificate | Not started; product decisions still open |
