# Evaluation

> Status: **not implemented.** Worth designing early - retrieval and prompt changes are impossible to judge by feel.

## What we need to know

- **Is the answer grounded?** Every claim traceable to the supplied passages, nothing invented.
- **Did retrieval find the right passages?** Most bad answers are retrieval failures wearing a generation costume.
- **Does it refuse when it should?** A knowledge base with a boundary must produce refusals. Zero refusals means the relevance floor is too low and the model is improvising.
- **Is the tone right?** Warm, plain, non-judgmental, no jargon, no medical or psychological advice.

## The cheapest thing that works

A fixed set of test questions with expected behavior, run before shipping a retrieval or prompt change:

- questions the base clearly answers → correct, grounded answer,
- questions near the boundary → answered or refused, consistently,
- questions clearly outside → refusal plus handoff, never an improvised answer,
- questions that invite advice we must not give (medical, diagnostic) → declined.

Build this set from real questions as they arrive, including the ones from [`unanswered-questions.md`](unanswered-questions.md). A handful of well-chosen cases beats an elaborate harness nobody runs.

## Open questions

- Who judges correctness - the foundation's experts, presumably, but at what cadence?
- Is there a feedback control in the UI ("this answer didn't help"), and does that collect anything personal?
- How do we notice regressions after a knowledge base update, not just after a code change?

## When this gets built

Fill in: where the test set lives, how it is run, what "passing" means, and who reviews the results.
