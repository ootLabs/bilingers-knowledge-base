# Prompts

> Status: **not implemented.** No prompt is used anywhere in this repo; no provider or model has been chosen.

## Prompts we will need

| Prompt | Purpose |
|---|---|
| System / grounding | Defines the assistant's role, tone, and the hard rule that it answers only from the supplied passages |
| Answer generation | Turns retrieved passages + the user's question into an answer, with sources |
| Starter questions | The 3–5 general questions offered before the conversation begins |
| Follow-up questions | The 3–5 contextual, deepening questions offered after each answer |
| Quiz generation *(if generated rather than hand-written)* | See [`quiz-certificate.md`](quiz-certificate.md) |

## Grounding rules the system prompt must enforce

- Answer **only** from the passages supplied in the request. No outside knowledge, no filling gaps with plausible general advice.
- If the passages do not cover the question, say so plainly and hand off to a foundation specialist — never guess. Falling back to general knowledge is the failure mode this whole project has to avoid.
- Never present the model's own inference as the foundation's position.
- No medical, psychological, or legal advice, and no diagnosis. The audience is parents worried about their children; a confident wrong answer here does real harm.
- Cite which part of the knowledge base an answer came from.
- Warm, plain, non-judgmental tone. The user is a parent, not a linguist — no jargon without explanation.
- Answer in the user's language; see [`i18n.md`](i18n.md).

## The suggested-questions mechanic

The product's UX rests on it: a short intro, then 3–5 general questions pointing at useful directions, with a free-text option; after each answer, 3–5 contextual follow-ups that go deeper.

Open: are these generated per turn, or picked from a curated set the foundation maintains? Curated is cheaper, safer, and controllable by the foundation; generated adapts better to an unusual conversation. A hybrid — curated starters, generated follow-ups — is the likely answer, but it is not decided.

## Where prompts should live

In version control, as files, reviewable in a diff — never inline string literals scattered across the code, and never only in a database. A prompt change is a behavior change and belongs in a commit.

## When this gets built

Fill in: the actual prompt files and their location, the chosen model and provider, and how prompt changes are reviewed.
