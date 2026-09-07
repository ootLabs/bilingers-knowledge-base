"""Data model guarantees.

The unit tests here assert the parts of the schema that are load-bearing for a
decision made at the meeting, not the shape of every column. Two of them exist
because the card called them out as easy to get wrong: an anonymous parent must
still be countable (D5), and an answer must name the base version it came from.

The integration tests then prove the same things hold in PostgreSQL, because a
constraint that only exists in Python is not a constraint.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import engine
from app.models import (
    Base,
    ChatSession,
    KnowledgeBaseVersion,
    KnowledgeGap,
    KnowledgeGapStatus,
    Query,
    User,
    personal_data_columns,
)

EXPECTED_TABLES = {
    "users",
    "chat_sessions",
    "queries",
    "knowledge_gaps",
    "knowledge_base_versions",
}


BACKEND_ROOT = Path(__file__).resolve().parent.parent
VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"
# Matches `revision: str = "abc123"` and the plain `revision = "abc123"` form.
REVISION_ID = re.compile(r'^revision(?::\s*str)?\s*=\s*"([^"]+)"', re.MULTILINE)


def script_directory() -> ScriptDirectory:
    """Alembic's view of the migration history, with no database involved.

    Built without `alembic.ini` on purpose: only `script_location` matters here,
    and skipping the file avoids dragging its logging configuration in.
    """
    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def column(model: type, name: str):
    return model.__table__.columns[name]


class TestTables:
    def test_all_five_entities_are_registered(self) -> None:
        assert EXPECTED_TABLES <= set(Base.metadata.tables)

    def test_email_is_unique_in_the_database(self) -> None:
        """A check-then-insert races; a unique constraint does not."""
        assert column(User, "email").unique is True
        assert column(User, "email").nullable is False


class TestAnonymousSessions:
    """D5: a quota that only counts accounts is not a quota."""

    def test_session_needs_no_user(self) -> None:
        assert column(ChatSession, "user_id").nullable is True

    def test_session_always_carries_a_countable_identifier(self) -> None:
        token = column(ChatSession, "token")
        assert token.nullable is False
        assert token.unique is True

    def test_deleting_a_user_detaches_sessions_rather_than_erasing_them(self) -> None:
        """Erasing a person must not erase the cost history of their questions."""
        foreign_key = next(iter(column(ChatSession, "user_id").foreign_keys))
        assert foreign_key.ondelete == "SET NULL"


class TestQueryLedger:
    def test_records_everything_needed_to_report_cost(self) -> None:
        for name in (
            "model",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "cost_pln",
            "fx_rate_pln_per_usd",
            "pricing_version",
            "duration_ms",
        ):
            assert name in Query.__table__.columns

    def test_the_foundation_facing_amount_is_in_pln(self) -> None:
        """USD is kept for reconciling the provider invoice, but the figure the
        foundation approves is in its own currency, not converted at read time."""
        assert column(Query, "cost_pln").type.python_type is Decimal

    def test_cost_is_fixed_point(self) -> None:
        """Money reported to the foundation must not accumulate float error."""
        assert column(Query, "cost_usd").type.python_type is Decimal

    def test_measurements_are_optional(self) -> None:
        """A question rejected off-topic or over quota never reaches a model."""
        assert column(Query, "model").nullable is True
        assert column(Query, "cost_usd").nullable is True

    def test_answer_requires_a_base_version(self) -> None:
        names = {constraint.name for constraint in Query.__table__.constraints}
        assert "queries_answer_requires_kb_version" in names

    def test_cost_carries_its_attribution_and_provenance(self) -> None:
        """Declared here; that each one actually fires is in `test_usage.py`."""
        names = {constraint.name for constraint in Query.__table__.constraints}
        assert {
            "queries_cost_requires_model",
            "queries_cost_requires_pricing_provenance",
            "queries_measurements_non_negative",
        } <= names

    def test_a_referenced_base_version_cannot_be_deleted(self) -> None:
        """Declared here; that it actually fires is a database-level test below."""
        foreign_key = next(iter(column(Query, "knowledge_base_version_id").foreign_keys))
        assert foreign_key.ondelete == "RESTRICT"


class TestKnowledgeGaps:
    def test_status_covers_the_foundation_workflow(self) -> None:
        assert [status.value for status in KnowledgeGapStatus] == [
            "new",
            "in_progress",
            "resolved",
        ]

    def test_status_is_stored_as_values_not_member_names(self) -> None:
        """Without values_callable, Postgres would hold "IN_PROGRESS"."""
        assert set(column(KnowledgeGap, "status").type.enums) == {
            "new",
            "in_progress",
            "resolved",
        }

    def test_gap_outlives_the_query_it_came_from(self) -> None:
        """Store the question, not the person: the queue survives erasure."""
        foreign_key = next(iter(column(KnowledgeGap, "query_id").foreign_keys))
        assert foreign_key.ondelete == "SET NULL"
        assert column(KnowledgeGap, "question").nullable is False


class TestKnowledgeBaseVersions:
    def test_carries_what_an_ingest_has_to_be_identified_by(self) -> None:
        for name in ("version", "ingested_at", "record_count", "source_checksum"):
            assert column(KnowledgeBaseVersion, name).nullable is False
        assert column(KnowledgeBaseVersion, "version").unique is True


class TestPersonalDataRegistry:
    """T-113 needs one authoritative list; B-07 decides how long any of it lives."""

    def test_lists_every_marked_field(self) -> None:
        assert personal_data_columns() == [
            ("chat_sessions", "token"),
            ("knowledge_gaps", "question"),
            ("queries", "answer"),
            ("queries", "question"),
            ("users", "email"),
            ("users", "password_hash"),
        ]

    def test_free_text_written_by_a_parent_counts_as_personal(self) -> None:
        """A parent volunteers details about their child without being asked."""
        assert column(Query, "question").info.get("personal_data") is True
        assert column(KnowledgeGap, "question").info.get("personal_data") is True


class TestMigrationHistory:
    """Guards the two ways parallel branches break the migration chain.

    Both are cheap to cause and expensive to notice: two people cutting from the
    same head reach for the same next identifier, and the damage only shows up
    when the branches meet. Neither test needs a database, so they run even with
    nothing started.
    """

    def test_no_two_migrations_declare_the_same_revision_id(self) -> None:
        """Reads the files rather than asking Alembic, because Alembic is not
        strict about this: a duplicate id is a `UserWarning`, after which one of
        the two migrations quietly disappears from the history and the tables it
        was supposed to create are never made. Nothing else would notice."""
        seen: dict[str, str] = {}
        collisions: list[str] = []
        for path in sorted(VERSIONS_DIR.glob("*.py")):
            match = REVISION_ID.search(path.read_text(encoding="utf-8"))
            assert match is not None, f"{path.name} declares no revision id"
            revision = match.group(1)
            if revision in seen:
                collisions.append(f"{revision} in {seen[revision]} and {path.name}")
            seen[revision] = path.name

        assert collisions == [], (
            "two migrations claim the same revision id; give the newer one its own "
            "and point its down_revision at the other: " + "; ".join(collisions)
        )

    def test_the_history_has_exactly_one_head(self) -> None:
        """Two heads make `alembic upgrade head` fail outright, and the backend
        container runs exactly that before uvicorn, so the symptom is a service
        that never answers and a log repeating the same Alembic error. Happens
        whenever two migrations name the same `down_revision`, even with
        different ids of their own."""
        heads = script_directory().get_heads()

        assert len(heads) == 1, (
            f"migration history has {len(heads)} heads ({', '.join(heads)}); "
            "the one merging second should point its down_revision at the other"
        )


@pytest.mark.integration
class TestMigrations:
    def test_every_table_exists_after_migrating(self, migrated_database: None) -> None:
        """The stack applies migrations on start, with no manual step."""
        present = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES <= present

    def test_migration_state_is_recorded(self, migrated_database: None) -> None:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert revision

    def test_the_check_constraints_on_queries_match_the_model(
        self, migrated_database: None
    ) -> None:
        """Every one of these is written twice: once as a `CheckConstraint` here
        and once as SQL in a migration. `alembic check` does not compare check
        constraints at all, so without this a database built from the metadata
        and one built from migrations could enforce different rules on a figure
        reported to a funder, with both test suites green.
        """
        declared = {
            constraint.name
            for constraint in Query.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }
        with engine.connect() as connection:
            applied = set(
                connection.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'queries'::regclass AND contype = 'c'"
                    )
                ).scalars()
            )

        assert declared == applied

    def test_no_constraint_is_left_unvalidated(self, migrated_database: None) -> None:
        """An unvalidated constraint is enforced going forward but never checked
        against what is already stored, so the model claims a guarantee the
        table does not hold and `pg_dump` stops matching the metadata. Revision
        The cost ledger revision clears the pre-existing partial costs instead."""
        with engine.connect() as connection:
            unvalidated = list(
                connection.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'queries'::regclass AND NOT convalidated"
                    )
                ).scalars()
            )

        assert unvalidated == []


@pytest.mark.integration
class TestRealSchema:
    def test_full_chain_round_trips(
        self, migrated_database: None, db_session: Session
    ) -> None:
        version = KnowledgeBaseVersion(version=9001, record_count=12, source_checksum="a" * 64)
        session_row = ChatSession(token="round-trip-token")
        db_session.add_all([version, session_row])
        db_session.flush()

        query = Query(
            chat_session_id=session_row.id,
            knowledge_base_version_id=version.id,
            question="Czy dwujezycznosc szkodzi dziecku?",
            answer="Nie.",
            model="test-model",
            input_tokens=120,
            output_tokens=40,
            cost_usd=Decimal("0.000345"),
            # The database refuses a partial measurement: an amount in PLN
            # is only reproducible together with the rate and the price list
            # that produced it (queries_cost_requires_pricing_provenance).
            cost_pln=Decimal("0.001397"),
            fx_rate_pln_per_usd=Decimal("4.050000"),
            pricing_version="test-2026-08",
            duration_ms=850,
        )
        db_session.add(query)
        db_session.flush()

        assert query.chat_session.user_id is None
        assert query.knowledge_base_version.version == 9001
        assert query.cost_usd == Decimal("0.000345")

    def test_anonymous_session_is_accepted(
        self, migrated_database: None, db_session: Session
    ) -> None:
        session_row = ChatSession(token="anonymous-token")
        db_session.add(session_row)
        db_session.flush()
        assert session_row.id is not None
        assert session_row.user_id is None

    def test_database_rejects_an_answer_with_no_base_version(
        self, migrated_database: None, db_session: Session
    ) -> None:
        """The acceptance criterion, enforced by PostgreSQL rather than by care."""
        session_row = ChatSession(token="constraint-token")
        db_session.add(session_row)
        db_session.flush()

        db_session.add(
            Query(
                chat_session_id=session_row.id,
                question="Pytanie",
                answer="Odpowiedz bez wersji bazy",
            )
        )
        # Named, so the test cannot pass because some unrelated rule fired.
        with pytest.raises(IntegrityError, match="queries_answer_requires_kb_version"):
            db_session.flush()

    def test_deleting_a_referenced_base_version_is_refused_through_the_orm(
        self, migrated_database: None, db_session: Session
    ) -> None:
        """The RESTRICT has to survive the ORM, not just exist in the schema.

        Asserting the `ondelete` string passes even when SQLAlchemy nulls the
        foreign key out before the DELETE, which would erase the provenance
        link rather than refuse to. Only the real delete proves otherwise.
        """
        version = KnowledgeBaseVersion(version=9002, record_count=1, source_checksum="b" * 64)
        session_row = ChatSession(token="restrict-token")
        db_session.add_all([version, session_row])
        db_session.flush()

        # answer=None on purpose: these rows delete cleanly when the foreign key
        # gets nulled first, so they are the case that fails silently.
        db_session.add(
            Query(
                chat_session_id=session_row.id,
                knowledge_base_version_id=version.id,
                question="Pytanie odrzucone przed generowaniem",
            )
        )
        db_session.flush()

        db_session.delete(version)
        with pytest.raises(IntegrityError, match="queries_knowledge_base_version_id_fkey"):
            db_session.flush()

    def test_gap_defaults_to_new(self, migrated_database: None, db_session: Session) -> None:
        gap = KnowledgeGap(question="Pytanie bez odpowiedzi")
        db_session.add(gap)
        db_session.flush()
        db_session.refresh(gap)
        assert gap.status is KnowledgeGapStatus.NEW

    def test_duplicate_email_is_refused(
        self, migrated_database: None, db_session: Session
    ) -> None:
        db_session.add(User(email="parent@example.com", password_hash="not-a-real-hash"))
        db_session.flush()
        db_session.add(User(email="parent@example.com", password_hash="not-a-real-hash"))
        with pytest.raises(IntegrityError, match="users_email_key"):
            db_session.flush()
