# Knowledge base

> Status: **the editing system exists, the content does not.** The foundation can now create, edit, version, import and publish documents through the panel. Nothing has been ingested yet, and a published document still does not reach the assistant, because chunking (T-21) and embeddings (T-22) are blocked on T-01 and the NDA (B-09).

## What it is

The substantive material on raising bilingual children, authored and maintained by the Bilingual Future Foundation. It is the **only** source the assistant may answer from. Everything else in the AI layer exists to serve this content accurately.

## What exists now

Not a plan any more, this is what is in the code.

**Storage.** `backend/app/models/document.py`: a `Document` is a stable identity carrying nothing but an id and a creation date; `document_versions` holds the content, one immutable snapshot per edit, with title, text, the account that wrote it, an optional change comment, a status, and (once published) who published it and when.

**Editing.** `app/services/documents.py` writes and `app/services/document_queries.py` reads. Editing never updates a row: `add_version` inserts the next snapshot, `restore_version` copies an old one forward as a new one, and the history therefore only ever grows. Version numbers are taken under `SELECT ... FOR UPDATE` on the document row, with the unique constraint as the backstop; two simultaneous saves take two numbers rather than one overwriting the other.

**Statuses.** `draft` -> `in_review` -> `published` -> `withdrawn`, and they are no longer a stored value nothing can change. `app/services/document_publishing.py` is the one and only place that moves a version along the ladder, and it is the only code in the system that updates an existing `document_versions` row at all.

**Publication.** Publishing demotes the previously published version to `withdrawn`, promotes the new one, and mints a `knowledge_base_versions` row stamped onto it, all in one transaction. The order matters: `document_versions_one_published_per_document` is a partial unique index checked per statement, so the demotion is flushed before the promotion. `record_count` is how many published versions exist afterwards, `source_checksum` is the SHA-256 of the text that went live.

**Import.** `app/services/docx_import.py` reads a `.docx` into headings plus text, in memory, never touching the filesystem and never using the uploaded filename for anything but an extension check. One unreadable paragraph is counted and skipped rather than ending the import, and tables are reported as not imported rather than silently dropped. The result is a preview: the editor sees what the system understood and accepts or rejects it before anything is stored.

**The panel.** `frontend/app/panel/` is where all of this is done by a person: the document list with its status pills, the editor, the version history with a line-by-line comparison and restore, the import screen, and the publication controls.

## What still does not exist

- **Any content.** The base is empty. First ingest is T-01, and it is blocked on the foundation.
- **Anything reaching the assistant.** Publishing sets a status and writes a log line through `app/services/knowledge_index.py`. That function is the single point where chunking (T-21) and embeddings (T-22) will attach; today it does nothing else, so `/chat` still streams placeholders and would not answer from a published document even if one existed.
- **Per-document permissions.** Every panel account can edit and publish every document. With three to five accounts that is deliberate; it stops being deliberate the moment the panel has more.
- **Export.** The change journal (T-89) has an action name reserved for it, and nothing emits it, because there is nothing to export from.

## Open questions

- **Ownership and update cadence** - who publishes a change, and how often? The system now records who did, which is half the answer.
- **Granularity** - is the natural unit an article, a section, or a Q&A pair? Affects retrieval quality more than any other choice, and it is the input T-21 needs. The `.docx` reader currently preserves heading structure as markdown-style markers, which keeps that decision open.
- ~~**Format we receive it in**~~ **Answered: `.docx`, heading plus text**, and it is now read automatically (T-85).
- ~~**Review before publishing**~~ **Answered and built:** the status ladder plus the publish and withdraw actions (T-88).
- ~~**Versioning**~~ **Answered and built:** `knowledge_base_versions` per publication, `document_versions` per edit, and `queries.knowledge_base_version_id` tying an answer to the base that produced it.

## Shape to aim for

The ingested unit still needs enough metadata to be cited and audited: stable identifier, title and text, language, source reference, version, and topic tags if the foundation organizes content that way. Documents and versions supply the first five; tags do not exist and are the one field to add when T-21 says what retrieval needs.

## Deliberately deferred

- Chunking strategy, see [`retrieval.md`](retrieval.md).
- Embeddings and any vector storage, and the cost of running them (that lands in the ledger from T-41 with T-22, not before).
- Removing a withdrawn document's chunks from the index, which cannot be built before the index is.
