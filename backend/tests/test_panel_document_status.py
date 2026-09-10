"""What a parent is reading, as the panel reports it (T-86, T-88).

Split from `test_panel_documents.py` when that file passed the size limit,
along the seam that was already there: everything there is about writing and
reading versions, everything here is about the one question the list and the
editor answer wrongly if the published version is left out.

The document helpers come from that module rather than being copied, so a
change to how a document is created in a test lands in one place.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.panel import PanelUser
from tests.conftest import auth_header
from tests.test_panel_documents import (
    SECOND_CONTENT,
    create_document,
    editor_token,
    save_version,
)


@pytest.fixture
def token_and_published(
    panel_client: TestClient, panel_editor: PanelUser
) -> tuple[str, int]:
    """A signed-in editor and a document whose version 1 is published."""
    token = editor_token(panel_client, panel_editor)
    document_id = create_document(panel_client, token)
    response = panel_client.post(
        f"/api/panel/documents/{document_id}/versions/1/publish",
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return token, document_id

class TestWhatParentsAreReading:
    """The published version travels beside the newest one, always.

    These are two different questions and after any save they have two
    different answers. Reporting only the newest version let the panel tell an
    editor that nothing was published while the older published version was
    still the one being served, which is the opposite of what the status is
    for.
    """

    def test_a_row_carries_the_published_version_and_the_newer_draft(
        self, panel_client: TestClient, token_and_published: tuple[str, int]
    ) -> None:
        token, document_id = token_and_published
        save_version(panel_client, token, document_id, SECOND_CONTENT)

        row = panel_client.get("/api/panel/documents", headers=auth_header(token)).json()[0]

        assert row["latest_version"]["version_number"] == 2
        assert row["latest_version"]["status"] == "draft"
        assert row["published_version"]["version_number"] == 1
        assert row["published_version"]["status"] == "published"
        assert row["published_version"]["published_by_email"] is not None
        assert row["id"] == document_id

    def test_the_editor_screen_carries_it_too(
        self, panel_client: TestClient, token_and_published: tuple[str, int]
    ) -> None:
        token, document_id = token_and_published
        save_version(panel_client, token, document_id, SECOND_CONTENT)

        body = panel_client.get(
            f"/api/panel/documents/{document_id}", headers=auth_header(token)
        ).json()

        assert body["latest_version"]["version_number"] == 2
        assert body["published_version"]["version_number"] == 1
        # A summary, not a detail: the editor says which version is live, it
        # does not show its text next to the one being edited.
        assert "content" not in body["published_version"]

    def test_nothing_published_reads_as_nothing_published(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = editor_token(panel_client, panel_editor)
        create_document(panel_client, token)

        row = panel_client.get("/api/panel/documents", headers=auth_header(token)).json()[0]

        assert row["published_version"] is None

    def test_withdrawing_takes_the_document_out_of_what_parents_read(
        self, panel_client: TestClient, token_and_published: tuple[str, int]
    ) -> None:
        """Withdrawal is the other half: the pill has to stop claiming it."""
        token, document_id = token_and_published
        assert panel_client.post(
            f"/api/panel/documents/{document_id}/versions/1/withdraw",
            headers=auth_header(token),
        ).status_code == 200

        row = panel_client.get("/api/panel/documents", headers=auth_header(token)).json()[0]

        assert row["published_version"] is None
        assert row["latest_version"]["status"] == "withdrawn"

    def test_the_extra_answer_costs_no_extra_query(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """A join, not a lookup per row. The published version is joined into
        the same statement, which the partial unique index makes safe: at most
        one published version per document, so no row can be multiplied."""
        token = editor_token(panel_client, panel_editor)
        for index in range(20):
            document_id = create_document(panel_client, token, title=f"Dokument {index}")
            panel_client.post(
                f"/api/panel/documents/{document_id}/versions/1/publish",
                headers=auth_header(token),
            )

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
        assert all(row["published_version"] is not None for row in response.json())
        selects = [text for text in statements if text.lstrip().upper().startswith("SELECT")]
        assert len(selects) <= 3, selects
