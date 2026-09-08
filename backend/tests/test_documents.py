"""Document content and version guarantees (T-84).

Two invariants the card calls out as easy to get wrong: a version is never
overwritten, only replaced by a new one, and at most one version of a document
may be published at a time. Both are asserted at the mapper level and, for the
one PostgreSQL actually enforces, against a real database too.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_mock_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex

from app.models import Document, DocumentStatus, DocumentVersion, KnowledgeBaseVersion
from tests.conftest import make_panel_user


def column(model: type, name: str):
    return model.__table__.columns[name]


class TestDocumentIdentity:
    def test_document_row_carries_no_updated_at_because_it_never_changes(self) -> None:
        """A document is written once; every change is a new version row."""
        assert "updated_at" not in Document.__table__.columns


class TestVersionShape:
    def test_version_carries_no_updated_at_because_an_edit_is_a_new_row(self) -> None:
        assert "updated_at" not in DocumentVersion.__table__.columns

    def test_version_records_who_changed_what_and_when(self) -> None:
        for name in ("author_id", "change_comment", "created_at"):
            assert name in DocumentVersion.__table__.columns


class TestDocumentStatus:
    def test_status_covers_the_editorial_ladder(self) -> None:
        assert [status.value for status in DocumentStatus] == [
            "draft",
            "in_review",
            "published",
            "withdrawn",
        ]

    def test_status_is_stored_as_values_not_member_names(self) -> None:
        """Without values_callable, Postgres would hold "IN_REVIEW"."""
        assert set(column(DocumentVersion, "status").type.enums) == {
            "draft",
            "in_review",
            "published",
            "withdrawn",
        }


class TestPublishedVersionIsUnique:
    def test_one_published_version_per_document_is_declared(self) -> None:
        """Declared here; that it actually fires is a database-level test below."""
        indexes = {index.name: index for index in DocumentVersion.__table__.indexes}
        assert "document_versions_one_published_per_document" in indexes
        index = indexes["document_versions_one_published_per_document"]
        assert index.unique is True
        assert index.dialect_options["postgresql"]["where"] is not None

    def test_the_index_is_partial_on_every_dialect_we_run_on(self) -> None:
        """A `where` for one dialect only is worse than none: the index still
        compiles elsewhere, just without the condition, so it silently becomes
        an unconditional unique on document_id and a document can hold exactly
        one version. Asserting the compiled DDL rather than the dialect option
        keeps this honest whichever keyword SQLAlchemy expects.
        """
        index = next(
            index
            for index in DocumentVersion.__table__.indexes
            if index.name == "document_versions_one_published_per_document"
        )

        for url in ("postgresql://", "sqlite://"):
            statement = str(CreateIndex(index).compile(create_mock_engine(url, None)))
            assert "where status = 'published'" in statement.lower(), (
                f"the index loses its WHERE on {url}, which turns it into an "
                "unconditional unique on document_id"
            )


class TestVersionNumbering:
    def test_version_numbers_start_at_one(self) -> None:
        """Declared here; that it actually fires is a database-level test below."""
        names = {constraint.name for constraint in DocumentVersion.__table__.constraints}
        assert "document_versions_version_number_positive" in names

    def test_the_foreign_key_needs_no_index_of_its_own(self) -> None:
        """The unique constraint indexes document_id as its leading column, so a
        second index on it would only cost writes on an insert-only table."""
        assert column(DocumentVersion, "document_id").index is not True


class TestVersionProvenance:
    def test_a_referenced_base_version_cannot_be_deleted(self) -> None:
        foreign_key = next(iter(column(DocumentVersion, "knowledge_base_version_id").foreign_keys))
        assert foreign_key.ondelete == "RESTRICT"

    def test_deleting_a_document_takes_its_versions(self) -> None:
        foreign_key = next(iter(column(DocumentVersion, "document_id").foreign_keys))
        assert foreign_key.ondelete == "CASCADE"

    def test_deleting_the_author_account_detaches_the_version_rather_than_erasing_it(self) -> None:
        foreign_key = next(iter(column(DocumentVersion, "author_id").foreign_keys))
        assert foreign_key.ondelete == "SET NULL"


def add_version(session: Session, document: Document, number: int, status: DocumentStatus):
    """One version of `document`, flushed. Title and content carry the number so
    a failure message says which row the database refused."""
    version = DocumentVersion(
        document_id=document.id,
        version_number=number,
        title=f"Wersja {number}",
        content=f"Tresc wersji {number}.",
        status=status,
    )
    session.add(version)
    session.flush()
    return version


class TestPublishedVersionIsUniqueOffPostgres:
    """The same guarantee on the fixture that runs with no stack up.

    `panel_db` is where the services of T-85 and T-87 will be tested, so a
    schema that compiles differently there is not a cosmetic difference: every
    one of those tests would be written against a database the product never
    runs on. This is not hypothetical. With `postgresql_where` alone the WHERE
    was dropped here and the index became an unconditional unique on
    document_id, which forbids a document from having a second version at all.
    """

    def test_a_document_may_hold_many_unpublished_versions(self, panel_db: Session) -> None:
        document = Document()
        panel_db.add(document)
        panel_db.flush()

        add_version(panel_db, document, 1, DocumentStatus.DRAFT)
        add_version(panel_db, document, 2, DocumentStatus.DRAFT)
        add_version(panel_db, document, 3, DocumentStatus.IN_REVIEW)

        assert len(panel_db.scalars(select(DocumentVersion)).all()) == 3

    def test_a_draft_may_sit_alongside_the_published_version(self, panel_db: Session) -> None:
        """The editorial loop is exactly this: publish, then start the next
        revision while readers still see the published one."""
        document = Document()
        panel_db.add(document)
        panel_db.flush()

        add_version(panel_db, document, 1, DocumentStatus.PUBLISHED)
        add_version(panel_db, document, 2, DocumentStatus.DRAFT)
        add_version(panel_db, document, 3, DocumentStatus.WITHDRAWN)

        assert len(panel_db.scalars(select(DocumentVersion)).all()) == 3

    def test_a_second_published_version_is_still_refused(self, panel_db: Session) -> None:
        """SQLite names the column, not the index, so the match is on the
        column list. Distinct version numbers keep it unambiguous: the composite
        unique on (document_id, version_number) cannot be what fired.
        """
        document = Document()
        panel_db.add(document)
        panel_db.flush()

        add_version(panel_db, document, 1, DocumentStatus.PUBLISHED)

        with pytest.raises(
            IntegrityError, match=r"UNIQUE constraint failed: document_versions\.document_id(?!,)"
        ):
            add_version(panel_db, document, 2, DocumentStatus.PUBLISHED)


@pytest.mark.integration
class TestRealSchema:
    def test_new_version_defaults_to_draft(
        self, migrated_database: None, db_session: Session
    ) -> None:
        document = Document()
        db_session.add(document)
        db_session.flush()

        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            title="Dwujezycznosc a rozwoj mowy",
            content="Tresc dokumentu.",
        )
        db_session.add(version)
        db_session.flush()
        db_session.refresh(version)

        assert version.status is DocumentStatus.DRAFT

    def test_the_database_itself_defaults_the_status_without_the_orm(
        self, migrated_database: None, db_session: Session
    ) -> None:
        """`default=` is Python's, `server_default` is the database's, and only
        the second one covers a writer that bypasses the ORM. The .docx import
        (T-85) is exactly such a writer, and `alembic/env.py` does not set
        `compare_server_default`, so a drift here would pass `alembic check`.
        """
        document = Document()
        db_session.add(document)
        db_session.flush()

        db_session.execute(
            text(
                "INSERT INTO document_versions (document_id, version_number, title, content) "
                "VALUES (:document_id, 1, 'Tytul', 'Tresc')"
            ),
            {"document_id": document.id},
        )
        stored = db_session.execute(
            text("SELECT status FROM document_versions WHERE document_id = :document_id"),
            {"document_id": document.id},
        ).scalar_one()

        assert stored == DocumentStatus.DRAFT.value

    def test_database_refuses_a_version_number_below_one(
        self, migrated_database: None, db_session: Session
    ) -> None:
        document = Document()
        db_session.add(document)
        db_session.flush()

        db_session.add(
            DocumentVersion(
                document_id=document.id, version_number=0, title="Wersja zero", content="Tresc"
            )
        )
        with pytest.raises(
            IntegrityError, match="document_versions_version_number_positive"
        ):
            db_session.flush()

    def test_database_refuses_a_second_published_version_of_one_document(
        self, migrated_database: None, db_session: Session
    ) -> None:
        document = Document()
        db_session.add(document)
        db_session.flush()

        db_session.add(
            DocumentVersion(
                document_id=document.id,
                version_number=1,
                title="Wersja 1",
                content="Tresc 1",
                status=DocumentStatus.PUBLISHED,
            )
        )
        db_session.flush()

        db_session.add(
            DocumentVersion(
                document_id=document.id,
                version_number=2,
                title="Wersja 2",
                content="Tresc 2",
                status=DocumentStatus.PUBLISHED,
            )
        )
        # Named, so the test cannot pass because some unrelated rule fired.
        with pytest.raises(
            IntegrityError, match="document_versions_one_published_per_document"
        ):
            db_session.flush()

    def test_a_draft_may_sit_alongside_the_published_version(
        self, migrated_database: None, db_session: Session
    ) -> None:
        """That the index is partial, not merely unique. The test above passes
        either way, because an unconditional unique on document_id also refuses
        a second published version; only an accepted draft proves a published
        document can be revised at all.
        """
        document = Document()
        db_session.add(document)
        db_session.flush()

        for number, status in (
            (1, DocumentStatus.PUBLISHED),
            (2, DocumentStatus.DRAFT),
            (3, DocumentStatus.IN_REVIEW),
            (4, DocumentStatus.WITHDRAWN),
        ):
            db_session.add(
                DocumentVersion(
                    document_id=document.id,
                    version_number=number,
                    title=f"Wersja {number}",
                    content=f"Tresc wersji {number}.",
                    status=status,
                )
            )
        db_session.flush()

        stored = db_session.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        ).all()
        assert len(stored) == 4

    def test_database_refuses_a_duplicate_version_number(
        self, migrated_database: None, db_session: Session
    ) -> None:
        document = Document()
        db_session.add(document)
        db_session.flush()

        db_session.add(
            DocumentVersion(
                document_id=document.id, version_number=1, title="Wersja 1", content="Tresc 1"
            )
        )
        db_session.flush()

        db_session.add(
            DocumentVersion(
                document_id=document.id, version_number=1, title="Wersja 1 bis", content="Tresc"
            )
        )
        with pytest.raises(
            IntegrityError, match="document_versions_document_id_version_number_key"
        ):
            db_session.flush()

    def test_deleting_a_document_removes_its_versions(
        self, migrated_database: None, db_session: Session
    ) -> None:
        document = Document()
        db_session.add(document)
        db_session.flush()

        version = DocumentVersion(
            document_id=document.id, version_number=1, title="Wersja", content="Tresc"
        )
        db_session.add(version)
        db_session.flush()
        version_id = version.id

        db_session.delete(document)
        db_session.flush()

        assert db_session.get(DocumentVersion, version_id) is None

    def test_deleting_a_referenced_base_version_is_refused_through_the_orm(
        self, migrated_database: None, db_session: Session
    ) -> None:
        """The RESTRICT has to survive the ORM, not just exist in the schema.

        Asserting the `ondelete` string passes even when SQLAlchemy nulls the
        foreign key out before the DELETE, which would erase the provenance
        link rather than refuse to. Only the real delete proves otherwise.
        """
        kb_version = KnowledgeBaseVersion(version=9101, record_count=1, source_checksum="c" * 64)
        document = Document()
        db_session.add_all([kb_version, document])
        db_session.flush()

        db_session.add(
            DocumentVersion(
                document_id=document.id,
                version_number=1,
                title="Wersja",
                content="Tresc",
                knowledge_base_version_id=kb_version.id,
            )
        )
        db_session.flush()

        db_session.delete(kb_version)
        with pytest.raises(
            IntegrityError, match="document_versions_knowledge_base_version_id_fkey"
        ):
            db_session.flush()

    def test_deleting_the_author_removes_the_person_but_not_the_version(
        self, migrated_database: None, db_session: Session
    ) -> None:
        author = make_panel_user(db_session, email="redaktor-usuniety@fundacja.test", password=None)
        document = Document()
        db_session.add(document)
        db_session.flush()

        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            title="Wersja",
            content="Tresc",
            author_id=author.id,
        )
        db_session.add(version)
        db_session.flush()
        version_id = version.id

        db_session.delete(author)
        db_session.flush()
        db_session.expire_all()

        surviving = db_session.get(DocumentVersion, version_id)
        assert surviving is not None
        assert surviving.author_id is None
