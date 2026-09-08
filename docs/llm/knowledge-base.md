# Knowledge base

> Status: **storage exists, content does not.** `documents` and `document_versions` (T-84) hold the schema the content will live in. The content itself is being written on the foundation's side; nothing has been ingested.

## What it is

The substantive material on raising bilingual children, authored and maintained by the Bilingual Future Foundation. It is the **only** source the assistant may answer from. Everything else in the AI layer exists to serve this content accurately.

## Open questions

- ~~**Format we receive it in** - documents, a CMS export, structured articles?~~ **Answered: `.docx`, heading plus text.** Stored as `document_versions.title` and `.content` (T-84).
- **Ownership and update cadence** - who publishes a change, and how often?
- ~~**Review before publishing** - does new content need approval before users see it, and who approves it?~~ **Answered: yes.** `document_versions.status` is a ladder, `draft` -> `in_review` -> `published` -> `withdrawn` (T-84). Who is allowed to move a version along it is not decided yet, and nothing moves it: `status` is a stored value with no way to change it, because no router, service or schema touches `document_versions`.
- ~~**Versioning** - do we need to know which version of the base produced a given answer?~~ **Answered: yes, and it is built.** `knowledge_base_versions` records each ingest (version, ingest time, record count, source checksum), and `queries.knowledge_base_version_id` ties every answer to one. A database check constraint refuses to store an answer that names no version, because the base is expected to keep growing and an untraceable answer cannot be re-examined once it has. Document-level versioning is now built too (T-84): editing a document never updates a row, it inserts a new `document_versions` row, and a partial unique index refuses more than one published version of a document at a time.
- **Granularity** - is the natural unit an article, a section, or a Q&A pair? Affects retrieval quality more than any other choice.

## Shape to aim for

Whatever the source format, the ingested unit should carry enough metadata to be cited and audited:

- stable identifier,
- title and the text itself,
- language,
- source reference (which document/section it came from),
- version or last-updated timestamp,
- topic/tags, if the foundation already organizes content that way.

Admin editing of the base is a planned feature (`Panel administracyjny`), so the storage format must be editable by a non-technical person - not a pile of files only a developer can change.

## Deliberately deferred

- Chunking strategy - belongs with retrieval, see [`retrieval.md`](retrieval.md).
- Embeddings and any vector storage - not until retrieval is actually being built.

## What exists

The ingest ledger described above, in `backend/app/models/knowledge.py`. No content has been ingested and nothing writes to the table yet: ingestion fills it, and the checksum column is what makes "have we already ingested this exact file?" answerable without keeping a copy of it.

Content storage itself now exists too (T-84), in `backend/app/models/document.py`: `Document` is a stable identity, `document_versions` is the actual content, one immutable snapshot per edit, carrying title, content, the editor who wrote it, an optional comment, and a status. Nothing populates it yet: this is schema only, no `.docx` import (T-85), no editor (T-87), no link from a published version to an actual ingest into `knowledge_base_versions` (T-88).

## When this gets built

Filled in by T-84: content is stored as `documents`/`document_versions` in our own PostgreSQL, review-before-publish is the four-status ladder. Still open: the real ingestion path (`.docx` upload, T-85), who can edit (the panel exists, T-82, but no per-document permission model), and how a published change actually reaches users (T-88, chunking and embeddings, T-21/T-22).
