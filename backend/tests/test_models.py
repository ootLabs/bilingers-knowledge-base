"""Data model guarantees.

The unit tests here assert the parts of the schema that are load-bearing for a
decision made at the meeting, not the shape of every column. Two of them exist
because the card called them out as easy to get wrong: an anonymous parent must
still be countable (D5), and an answer must name the base version it came from.

The integration tests then prove the same things hold in PostgreSQL, because a
constraint that only exists in Python is not a constraint.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
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
        for name in ("model", "input_tokens", "output_tokens", "cost_usd", "duration_ms"):
            assert name in Query.__table__.columns

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
