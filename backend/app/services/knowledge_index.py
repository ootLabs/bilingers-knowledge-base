"""The one place publication touches the retrieval index.

Today it records the intent and does nothing else, because there is nothing to
do it to: chunking is T-21, embeddings and the index itself are T-22, and both
are blocked on the first ingest (T-01) and on the NDA (B-09).

This exists as one function rather than an interface with an implementation
behind it. A plug-in point built before there is a second implementation is a
guess at the shape of code nobody has written; a function that gets a body
later is not. When T-22 lands, this is the place it lands, and the two callers
(publish and withdraw) already pass everything it will need.

The cost of an embedding run belongs in the ledger from T-41, and it arrives
with T-22, not here: there is no model call to price yet.
"""

from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class IndexChange(StrEnum):
    """What happened to a version, from the index's point of view."""

    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


def record_index_change(
    change: IndexChange,
    *,
    document_id: int,
    version_number: int,
    knowledge_base_version: int | None = None,
) -> None:
    """Note that the published set changed. Called inside the transaction.

    Deliberately incapable of failing the operation it describes: it writes a
    log line and returns. Once this reaches a vector store, that call has to
    move outside the transaction or be made retriable, because an index write
    that can roll back a publication would mean an editor's click succeeding or
    failing depending on a service that is not the database.
    """
    logger.info(
        "knowledge index change: %s document=%s version=%s knowledge_base_version=%s",
        change.value,
        document_id,
        version_number,
        knowledge_base_version,
    )
