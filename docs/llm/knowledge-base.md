# Knowledge base

> Status: **not implemented.** The content itself is being written on the foundation's side; nothing has been ingested.

## What it is

The substantive material on raising bilingual children, authored and maintained by the Bilingual Future Foundation. It is the **only** source the assistant may answer from. Everything else in the AI layer exists to serve this content accurately.

## Open questions

- **Format we receive it in** — documents, a CMS export, structured articles? This drives the whole ingestion design.
- **Ownership and update cadence** — who publishes a change, and how often?
- **Review before publishing** — does new content need approval before users see it, and who approves it?
- **Versioning** — do we need to know which version of the base produced a given answer? (Useful when a wrong answer is reported.)
- **Granularity** — is the natural unit an article, a section, or a Q&A pair? Affects retrieval quality more than any other choice.

## Shape to aim for

Whatever the source format, the ingested unit should carry enough metadata to be cited and audited:

- stable identifier,
- title and the text itself,
- language,
- source reference (which document/section it came from),
- version or last-updated timestamp,
- topic/tags, if the foundation already organizes content that way.

Admin editing of the base is a planned feature (`Panel administracyjny`), so the storage format must be editable by a non-technical person — not a pile of files only a developer can change.

## Deliberately deferred

- Chunking strategy — belongs with retrieval, see [`retrieval.md`](retrieval.md).
- Embeddings and any vector storage — not until retrieval is actually being built.

## When this gets built

Fill in: the real format, where the content is stored, how ingestion runs, who can edit it, and how a change reaches users. Then add the rows to `docs/map/backend.md`.
