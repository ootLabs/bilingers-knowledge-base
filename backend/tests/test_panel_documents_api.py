"""The document endpoints as HTTP: who may call them, and what they refuse.

Split from `test_panel_documents.py`, which owns the versioning behaviour
itself. Everything here is about the boundary: the token, the identifiers, the
input, and the one race the model can actually lose.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.document import Document, DocumentVersion
from app.models.panel import PanelUser
from app.services.documents import add_version, create_document
from tests.conftest import EDITOR_PASSWORD, auth_header, log_in, make_panel_user

TITLE = "Dwujezycznosc w wieku przedszkolnym"
CONTENT = "Tresc dokumentu bazy wiedzy fundacji."


def a_document(client: TestClient, token: str) -> int:
    response = client.post(
        "/api/panel/documents",
        headers=auth_header(token),
        json={"title": TITLE, "content": CONTENT},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestWhoMayCall:
    def test_no_token_is_refused_before_anything_is_read(
        self, panel_client: TestClient
    ) -> None:
        response = panel_client.get("/api/panel/documents")
        assert response.status_code == 401
        assert response.json()["detail"] == "not_authenticated"

    def test_an_editor_does_not_need_the_administrator_role(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """Writing the knowledge base is the editor's job, not a privilege."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        assert panel_client.get(
            "/api/panel/documents", headers=auth_header(token)
        ).status_code == 200

    def test_a_save_is_signed_by_the_token_not_by_the_body(
        self, panel_client: TestClient, panel_db: Session, panel_editor: PanelUser
    ) -> None:
        """One editor must not be able to put another's name on a change.

        The journal (T-89) is read from these rows during an incident, so an
        author field a caller can set would make it worthless.
        """
        other = make_panel_user(
            panel_db, email="justyna@fundacja.test", password=EDITOR_PASSWORD
        )
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = a_document(panel_client, token)

        response = panel_client.post(
            f"/api/panel/documents/{document_id}/versions",
            headers=auth_header(token),
            json={
                "title": TITLE,
                "content": "Zmieniona tresc.",
                "author_id": other.id,
                "author_email": other.email,
            },
        )
        assert response.status_code == 201
        assert response.json()["author_email"] == panel_editor.email

        stored = panel_db.execute(
            select(DocumentVersion).where(DocumentVersion.version_number == 2)
        ).scalar_one()
        assert stored.author_id == panel_editor.id


class TestUnknownIdentifiers:
    """An identifier that is not ours answers 404, never 500."""

    def test_an_unknown_document_is_not_found(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.get("/api/panel/documents/424242", headers=auth_header(token))
        assert response.status_code == 404
        assert response.json()["detail"] == "document_not_found"

    def test_an_unknown_version_of_a_real_document_is_its_own_answer(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        document_id = a_document(panel_client, token)
        response = panel_client.get(
            f"/api/panel/documents/{document_id}/versions/99", headers=auth_header(token)
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "version_not_found"

    def test_saving_into_an_unknown_document_is_not_found(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            "/api/panel/documents/424242/versions",
            headers=auth_header(token),
            json={"title": TITLE, "content": CONTENT},
        )
        assert response.status_code == 404


class TestInputTheBoundaryRefuses:
    @pytest.mark.parametrize(
        "payload",
        [
            {"title": "", "content": CONTENT},
            {"title": "   ", "content": CONTENT},
            {"title": TITLE, "content": "   "},
            {"title": "x" * 501, "content": CONTENT},
            {"title": "Tytul\x00z NUL", "content": CONTENT},
            {"title": TITLE, "content": "Tresc\x00z NUL"},
            {"title": "Tytul\nw dwoch liniach", "content": CONTENT},
        ],
    )
    def test_refused_as_the_callers_mistake_not_as_a_server_fault(
        self, panel_client: TestClient, panel_editor: PanelUser, payload: dict[str, str]
    ) -> None:
        """A NUL byte reaching psycopg would answer 500 with a traceback for
        something the caller can plainly fix."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            "/api/panel/documents", headers=auth_header(token), json=payload
        )
        assert response.status_code == 422

    def test_a_body_with_line_breaks_is_kept(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """Paragraphs are the content, so the control-character rule has to let
        them through."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            "/api/panel/documents",
            headers=auth_header(token),
            json={"title": TITLE, "content": "Akapit pierwszy.\n\nAkapit drugi."},
        )
        assert response.status_code == 201
        assert response.json()["latest_version"]["content"] == (
            "Akapit pierwszy.\n\nAkapit drugi."
        )


@pytest.mark.integration
class TestTwoSavesAtOnce:
    """The version numbering race, which only PostgreSQL can actually show.

    `with_for_update` is ignored on SQLite, so on `panel_db` this would pass
    whether the lock were there or not.
    """

    def test_simultaneous_saves_take_different_numbers(
        self, migrated_database: None
    ) -> None:
        with SessionLocal() as setup:
            author = make_panel_user(
                setup, email="wyscig@fundacja.test", password=EDITOR_PASSWORD
            )
            setup.commit()
            document = create_document(setup, author=author, title=TITLE, content=CONTENT)
            document_id = document.id
            author_id = author.id

        start = threading.Barrier(2)
        results: list[int | str] = []
        lock = threading.Lock()

        def save(content: str) -> None:
            with SessionLocal() as session:
                writer = session.get(PanelUser, author_id)
                start.wait(timeout=10)
                try:
                    version = add_version(
                        session,
                        document_id=document_id,
                        author=writer,
                        title=TITLE,
                        content=content,
                    )
                    outcome: int | str = version.version_number
                except Exception as error:  # noqa: BLE001 - the point is which one
                    outcome = type(error).__name__
                with lock:
                    results.append(outcome)

        threads = [
            threading.Thread(target=save, args=(f"Zapis rownolegly {index}",))
            for index in range(2)
        ]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)

            # Both saves land, with different numbers: the row lock serialised
            # them rather than letting one lose its work to the unique
            # constraint. A `ConcurrentEdit` here would mean the lock did not
            # hold.
            assert all(isinstance(outcome, int) for outcome in results), results
            assert sorted(results) == [2, 3], results
        finally:
            with SessionLocal() as cleanup:
                cleanup.execute(delete(Document).where(Document.id == document_id))
                cleanup.execute(delete(PanelUser).where(PanelUser.id == author_id))
                cleanup.commit()
