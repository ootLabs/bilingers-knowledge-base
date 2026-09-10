"""Versioning behaviour: what a save, a restore and a listing actually do.

The rules asserted here hold in code alone. Nothing stops a raw `UPDATE
document_versions`, no trigger and no `updated_at` column, so "a version is
immutable" is only true for as long as these tests say it is.

Access control and the concurrency rule live in `test_panel_documents_api.py`,
split along the same class boundary the panel's other test files use.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.document import DocumentStatus, DocumentVersion
from app.models.panel import PanelUser
from tests.conftest import EDITOR_PASSWORD, auth_header, log_in

FIRST_TITLE = "Kiedy zaczac mowic do dziecka w dwoch jezykach"
FIRST_CONTENT = "Pierwsza wersja tresci o dwujezycznosci."
SECOND_CONTENT = "Druga wersja, poprawiona po uwagach prof. Magdaleny."


def editor_token(client: TestClient, editor: PanelUser) -> str:
    return log_in(client, editor.email, EDITOR_PASSWORD)


def create_document(client: TestClient, token: str, *, title: str = FIRST_TITLE) -> int:
    response = client.post(
        "/api/panel/documents",
        headers=auth_header(token),
        json={"title": title, "content": FIRST_CONTENT},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def save_version(client: TestClient, token: str, document_id: int, content: str):
    return client.post(
        f"/api/panel/documents/{document_id}/versions",
        headers=auth_header(token),
        json={"title": FIRST_TITLE, "content": content},
    )


class TestSavingAnEdit:
    def test_a_save_adds_a_row_and_leaves_the_previous_one_untouched(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """The point of the whole model: an edit is an insert, never an update."""
        token = editor_token(panel_client, panel_editor)
        document_id = create_document(panel_client, token)

        before = panel_db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        ).scalar_one()
        original = (before.id, before.title, before.content, before.created_at)

        response = save_version(panel_client, token, document_id, SECOND_CONTENT)
        assert response.status_code == 201
        assert response.json()["version_number"] == 2

        versions = list(
            panel_db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number)
            ).scalars()
        )
        assert len(versions) == 2
        first = versions[0]
        assert (first.id, first.title, first.content, first.created_at) == original
        assert versions[1].content == SECOND_CONTENT

    def test_a_new_version_is_a_draft_even_over_a_published_one(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """Saving must never change what a parent is reading. Publication is a
        separate, deliberate action (T-88)."""
        token = editor_token(panel_client, panel_editor)
        document_id = create_document(panel_client, token)

        published = panel_db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        ).scalar_one()
        published.status = DocumentStatus.PUBLISHED
        panel_db.commit()

        response = save_version(panel_client, token, document_id, SECOND_CONTENT)
        assert response.status_code == 201
        assert response.json()["status"] == "draft"
        assert (
            panel_db.get(DocumentVersion, published.id).status is DocumentStatus.PUBLISHED
        )

    def test_the_reader_sees_the_newest_version(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = editor_token(panel_client, panel_editor)
        document_id = create_document(panel_client, token)
        save_version(panel_client, token, document_id, SECOND_CONTENT)

        latest = panel_client.get(
            f"/api/panel/documents/{document_id}", headers=auth_header(token)
        ).json()["latest_version"]
        assert latest["version_number"] == 2
        assert latest["content"] == SECOND_CONTENT
        assert latest["author_email"] == panel_editor.email


class TestRestoringAVersion:
    def test_restoring_the_first_of_three_creates_a_fourth(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """History never shortens. Restoring copies forward, it does not rewind."""
        token = editor_token(panel_client, panel_editor)
        document_id = create_document(panel_client, token)
        save_version(panel_client, token, document_id, "Wersja druga.")
        save_version(panel_client, token, document_id, "Wersja trzecia.")

        response = panel_client.post(
            f"/api/panel/documents/{document_id}/versions/1/restore",
            headers=auth_header(token),
            json={"change_comment": "Przywrocono tresc z wersji 1"},
        )
        assert response.status_code == 201
        restored = response.json()
        assert restored["version_number"] == 4
        assert restored["content"] == FIRST_CONTENT
        assert restored["status"] == "draft"

        history = panel_client.get(
            f"/api/panel/documents/{document_id}/versions", headers=auth_header(token)
        ).json()
        assert [entry["version_number"] for entry in history] == [4, 3, 2, 1]

    def test_a_restored_version_keeps_the_original_title(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = editor_token(panel_client, panel_editor)
        document_id = create_document(panel_client, token)
        panel_client.post(
            f"/api/panel/documents/{document_id}/versions",
            headers=auth_header(token),
            json={"title": "Zmieniony tytul", "content": SECOND_CONTENT},
        )

        restored = panel_client.post(
            f"/api/panel/documents/{document_id}/versions/1/restore",
            headers=auth_header(token),
            json={},
        ).json()
        assert restored["title"] == FIRST_TITLE


class TestListing:
    def test_twenty_documents_cost_a_constant_number_of_queries(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """The editor's landing screen must not be N plus 1.

        Counted rather than asserted as "one", because the request also
        resolves the session token: the number that matters is that it does not
        grow with the number of documents.
        """
        token = editor_token(panel_client, panel_editor)
        for index in range(20):
            create_document(panel_client, token, title=f"Dokument {index}")

        statements: list[str] = []

        def record(_connection, _cursor, statement, *_rest) -> None:
            statements.append(statement)

        engine = panel_db.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            response = panel_client.get("/api/panel/documents", headers=auth_header(token))
        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert response.status_code == 200
        assert len(response.json()) == 20
        selects = [text for text in statements if text.lstrip().upper().startswith("SELECT")]
        assert len(selects) <= 3, selects

    def test_a_list_row_carries_the_status_and_the_newest_change(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """Everything T-86 needs on screen without opening a document."""
        token = editor_token(panel_client, panel_editor)
        document_id = create_document(panel_client, token)
        save_version(panel_client, token, document_id, SECOND_CONTENT)

        row = panel_client.get("/api/panel/documents", headers=auth_header(token)).json()[0]
        assert row["id"] == document_id
        assert row["latest_version"]["status"] == "draft"
        assert row["latest_version"]["version_number"] == 2
        assert row["latest_version"]["author_email"] == panel_editor.email
        # The list is not the editor: sending every document's full text to
        # draw a list of titles is the cost this shape exists to avoid.
        assert "content" not in row["latest_version"]
