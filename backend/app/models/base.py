"""Declarative base, shared columns, and the personal-data registry.

Retention periods are deliberately absent: they depend on GDPR decisions still
open on the foundation's side (blocker B-07). What this module does provide is
the *marking*, so the retention work (T-113) can enumerate every field holding
personal data instead of rediscovering them by reading models one by one.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Placed in a column's `info` dict. A column carrying it holds personal data and
# is therefore subject to retention rules once B-07 is answered. Treat as
# read-only: SQLAlchemy stores the reference, it does not copy it.
PERSONAL_DATA = {"personal_data": True}


class Base(DeclarativeBase):
    """Shared declarative base. Every model registers its table here."""


class TimestampMixin:
    """`created_at` and `updated_at` for rows that genuinely change.

    Append-only tables declare `created_at` alone rather than carrying an
    `updated_at` that never moves.

    The defaults are database-side, but `updated_at` is bumped by SQLAlchemy on
    update, not by a trigger. A write that bypasses the ORM (psql, a bulk
    UPDATE) leaves it stale. That matters for `knowledge_gaps`, which a review
    queue would sort by, so a trigger belongs here if the panel (T-86, T-87)
    ever writes status outside the ORM.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def personal_data_columns() -> list[tuple[str, str]]:
    """Every `(table, column)` marked as holding personal data.

    Derived from the mapper metadata rather than kept as a hand-written list,
    so a new personal field cannot drift out of it: marking the column is the
    same edit as adding it.
    """
    return sorted(
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if column.info.get("personal_data")
    )
