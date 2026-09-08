"""Publication and withdrawal (T-88): the moment the panel starts having
consequences for what a parent reads.

The rule that actually bites here is the partial unique index: a document may
have at most one published version, the index is not deferrable, and so
promoting a new version before demoting the old one fails inside the
transaction. The `panel_db` fixture carries that index too (`sqlite_where` sits
beside `postgresql_where` in the model), so the ordering is exercised in the
default run, and an `integration` class proves it on the database it ships on.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import DocumentStatus, DocumentVersion
from app.models.knowledge import KnowledgeBaseVersion
from app.models.panel import PanelUser
from tests.conftest import EDITOR_PASSWORD, auth_header, log_in, make_panel_user

TITLE = "Dwujezycznosc w przedszkolu"


def new_document(client: TestClient, token: str) -> int:
    response = client.post(
        "/api/panel/documents",
        headers=auth_header(token),
        json={"title": TITLE, "content": "Pierwsza tresc."},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def new_version(client: TestClient, token: str, document_id: int, content: str) -> int:
    response = client.post(
        f"/api/panel/documents/{document_id}/versions",
        headers=auth_header(token),
        json={"title": TITLE, "content": content},
    )
    assert response.status_code == 201, response.text
    return response.json()["version_number"]


def publish(client: TestClient, token: str, document_id: int, version_number: int):
    return client.post(
        f"/api/panel/documents/{document_id}/versions/{version_number}/publish",
        headers=auth_header(token),
    )


def withdraw(client: TestClient, token: str, document_id: int, version_number: int):
    return client.post(
        f"/api/panel/documents/{document_id}/versions/{version_number}/withdraw",
        headers=auth_header(token),
    )


class TestPublishing:
    def test_publishing_records_who_and_when_alongside_the_status(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """A published status with no date and no name is a claim, not an answer."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)

        response = publish(panel_client, token, document_id, 1)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "published"
        assert body["published_at"] is not None
        assert body["published_by_email"] == panel_editor.email

    def test_publishing_stamps_the_version_with_a_knowledge_base_version(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """Without it an answer cannot be traced back to the text that produced
        it, which is the whole reason the table exists."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)

        publish(panel_client, token, document_id, 1)

        version = panel_db.execute(select(DocumentVersion)).scalar_one()
        assert version.knowledge_base_version_id is not None
        base_version = panel_db.get(KnowledgeBaseVersion, version.knowledge_base_version_id)
        assert base_version.version == 1
        assert base_version.record_count == 1

    def test_publishing_a_second_version_takes_the_first_one_down_with_it(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """The main trap of this card: the partial unique index is checked per
        statement, so the demotion has to be flushed before the promotion."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)
        publish(panel_client, token, document_id, 1)
        second = new_version(panel_client, token, document_id, "Druga tresc.")

        response = publish(panel_client, token, document_id, second)

        assert response.status_code == 200
        statuses = {
            version.version_number: version.status
            for version in panel_db.execute(select(DocumentVersion)).scalars()
        }
        assert statuses == {1: DocumentStatus.WITHDRAWN, 2: DocumentStatus.PUBLISHED}

    def test_publishing_twice_changes_nothing_the_second_time(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """Silence after a click is what makes an editor click again, so the
        second click has to be harmless rather than an error or a second ingest."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)
        publish(panel_client, token, document_id, 1)

        response = publish(panel_client, token, document_id, 1)

        assert response.status_code == 200
        assert response.json()["status"] == "published"
        assert len(list(panel_db.execute(select(KnowledgeBaseVersion)).scalars())) == 1

    def test_publication_tells_the_index_layer_that_the_set_changed(
        self,
        panel_client: TestClient,
        panel_editor: PanelUser,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The single hook T-21 and T-22 will grow into. Today it only records."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)

        with caplog.at_level(logging.INFO, logger="app.services.knowledge_index"):
            publish(panel_client, token, document_id, 1)

        assert any("knowledge index change: published" in line for line in caplog.messages)

    def test_saving_an_edit_never_publishes_anything(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)
        publish(panel_client, token, document_id, 1)

        second = new_version(panel_client, token, document_id, "Druga tresc.")

        latest = panel_client.get(
            f"/api/panel/documents/{document_id}", headers=auth_header(token)
        ).json()["latest_version"]
        assert second == 2
        assert latest["status"] == "draft"
        assert latest["published_at"] is None


class TestWithdrawing:
    def test_withdrawing_keeps_the_trail_of_what_was_published(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """An answer given last week still has to be traceable to the text that
        produced it, so the knowledge base version stays on the row."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)
        publish(panel_client, token, document_id, 1)

        response = withdraw(panel_client, token, document_id, 1)

        assert response.status_code == 200
        assert response.json()["status"] == "withdrawn"
        version = panel_db.execute(select(DocumentVersion)).scalar_one()
        assert version.knowledge_base_version_id is not None
        assert version.published_by_id == panel_editor.id

    def test_withdrawing_a_draft_is_refused_rather_than_quietly_accepted(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)

        response = withdraw(panel_client, token, document_id, 1)

        assert response.status_code == 409
        assert response.json()["detail"] == "not_published"

    def test_an_unknown_version_is_not_found(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = new_document(panel_client, token)

        assert publish(panel_client, token, document_id, 99).status_code == 404
        assert publish(panel_client, token, 424242, 1).status_code == 404


@pytest.mark.integration
class TestOnPostgres:
    """The switch against the real partial index, which is the rule here.

    On PostgreSQL `document_versions_one_published_per_document` is enforced by
    the database that ships, not by a fixture, so this is the test that says the
    ordering inside the transaction is genuinely correct.
    """

    def test_moving_publication_between_versions_holds(
        self, postgres_panel_client: TestClient, db_session: Session
    ) -> None:
        editor = make_panel_user(
            db_session, email="publikacja@fundacja.test", password=EDITOR_PASSWORD
        )
        db_session.commit()

        token = log_in(postgres_panel_client, editor.email, EDITOR_PASSWORD)
        document_id = new_document(postgres_panel_client, token)
        assert publish(postgres_panel_client, token, document_id, 1).status_code == 200
        second = new_version(postgres_panel_client, token, document_id, "Druga tresc.")

        assert publish(postgres_panel_client, token, document_id, second).status_code == 200

        published = db_session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.status == DocumentStatus.PUBLISHED,
            )
        ).scalars()
        assert [version.version_number for version in published] == [2]
