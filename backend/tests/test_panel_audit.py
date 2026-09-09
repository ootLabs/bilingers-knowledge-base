"""The panel's change journal (T-89).

The question this answers is the one Justyna asked on the call of 11.08: the
knowledge base is under an NDA (B-09), so the system that opens it has to be
able to say who did what with it.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.main import app
from app.models.audit import AuditAction
from app.models.panel import PanelRole, PanelUser
from app.services.panel_audit import record_event
from tests.conftest import (
    ADMIN_PASSWORD,
    EDITOR_PASSWORD,
    auth_header,
    log_in,
    make_panel_user,
)

TITLE = "Dwujezycznosc w przedszkolu"


def journal(client: TestClient, token: str, **params: str) -> list[dict]:
    response = client.get(
        "/api/panel/audit-events", headers=auth_header(token), params=params
    )
    assert response.status_code == 200, response.text
    return response.json()


def actions(entries: list[dict]) -> list[str]:
    return [entry["action"] for entry in entries]


class TestWhatGetsRecorded:
    def test_creating_and_publishing_a_document_both_land_in_the_journal(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        document_id = panel_client.post(
            "/api/panel/documents",
            headers=auth_header(token),
            json={"title": TITLE, "content": "Tresc."},
        ).json()["id"]
        panel_client.post(
            f"/api/panel/documents/{document_id}/versions/1/publish",
            headers=auth_header(token),
        )

        recorded = actions(journal(panel_client, token))

        assert AuditAction.DOCUMENT_CREATED in recorded
        assert AuditAction.DOCUMENT_PUBLISHED in recorded

    def test_a_saved_edit_says_which_version_it_was(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        document_id = panel_client.post(
            "/api/panel/documents",
            headers=auth_header(token),
            json={"title": TITLE, "content": "Tresc."},
        ).json()["id"]
        panel_client.post(
            f"/api/panel/documents/{document_id}/versions",
            headers=auth_header(token),
            json={"title": TITLE, "content": "Druga tresc."},
        )

        saved = [
            entry
            for entry in journal(panel_client, token)
            if entry["action"] == AuditAction.DOCUMENT_VERSION_SAVED
        ]
        assert saved[0]["detail"] == "version 2"
        assert saved[0]["subject_id"] == document_id

    def test_logging_out_is_recorded_because_nothing_else_records_it(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        """`panel_login_attempts` covers getting in. This is the other half."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        panel_client.delete("/api/panel/sessions/current", headers=auth_header(token))

        second = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        assert AuditAction.LOGGED_OUT in actions(journal(panel_client, second))

    def test_a_permission_change_names_who_granted_what(
        self, panel_client: TestClient, panel_db: Session, panel_admin: PanelUser
    ) -> None:
        editor = make_panel_user(
            panel_db, email="nowa@fundacja.test", password=EDITOR_PASSWORD
        )
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)

        panel_client.patch(
            f"/api/panel/users/{editor.id}",
            headers=auth_header(token),
            json={"role": "admin"},
        )

        changed = [
            entry
            for entry in journal(panel_client, token)
            if entry["action"] == AuditAction.ACCOUNT_CHANGED
        ]
        assert changed[0]["actor_email"] == panel_admin.email
        assert changed[0]["subject_id"] == editor.id
        assert "role=admin" in changed[0]["detail"]


class TestReadingTheLoginAudit:
    def test_the_journal_reads_panel_login_attempts_rather_than_copying_them(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        """One fact, one row, in one place. Two tables recording the same login
        would be two tables that can disagree.
        """
        panel_client.post(
            "/api/panel/sessions",
            json={"email": panel_admin.email, "password": "zle-haslo"},
        )
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)

        entries = journal(panel_client, token)

        assert AuditAction.LOGIN_SUCCEEDED in actions(entries)
        failed = [
            entry for entry in entries if entry["action"] == AuditAction.LOGIN_FAILED
        ]
        # The reason a login was refused is deliberately not returned over HTTP
        # at login time (T-82). It is readable here, by an administrator.
        assert failed[0]["detail"] == "bad_password"

    def test_filtering_by_person_covers_both_sources_at_once(
        self, panel_client: TestClient, panel_db: Session, panel_admin: PanelUser
    ) -> None:
        make_panel_user(panel_db, email="ktos.inny@fundacja.test", password=EDITOR_PASSWORD)
        panel_client.post(
            "/api/panel/sessions",
            json={"email": "ktos.inny@fundacja.test", "password": "zle-haslo"},
        )
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)

        entries = journal(panel_client, token, actor_email="ktos.inny@fundacja.test")

        assert entries != []
        assert {entry["actor_email"] for entry in entries} == {"ktos.inny@fundacja.test"}


class TestReadOnly:
    def test_only_an_administrator_may_read_it(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """An editor does not need her colleagues' movements to write a
        document, and every address in here is personal data (B-07)."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)

        response = panel_client.get("/api/panel/audit-events", headers=auth_header(token))

        assert response.status_code == 403

    def test_no_token_reads_nothing(self, panel_client: TestClient) -> None:
        assert panel_client.get("/api/panel/audit-events").status_code == 401

    def test_the_api_exposes_no_way_to_change_a_journal_line(self) -> None:
        """Not a policy, a fact about the routing table: a journal its own
        subject can edit is not evidence of anything, and the cheapest way to
        guarantee that is not to build the verb."""
        methods: set[str] = set()
        for route in app.routes:
            path = getattr(route, "path", "")
            if path.startswith("/api/panel/audit-events"):
                methods |= getattr(route, "methods", set())

        assert methods <= {"GET", "HEAD"}


class TestTheJournalCannotBreakTheOperation:
    def test_a_failed_write_is_logged_and_swallowed(
        self, panel_db: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A panel that refuses to save a document because it could not write a
        log line is worse than a panel with a gap in its log."""
        actor = make_panel_user(panel_db, email="ktos@fundacja.test", password=None)

        class BrokenSession:
            rolled_back = False

            def add(self, _row: object) -> None:
                pass

            def commit(self) -> None:
                raise OperationalError("INSERT", {}, Exception("connection lost"))

            def rollback(self) -> None:
                self.rolled_back = True

        broken = BrokenSession()
        with caplog.at_level(logging.ERROR, logger="app.services.panel_audit"):
            record_event(broken, actor=actor, action=AuditAction.DOCUMENT_CREATED)

        assert broken.rolled_back is True
        assert any("could not record audit event" in line for line in caplog.messages)

    def test_a_rollback_that_also_fails_is_swallowed(
        self, panel_db: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The operation being described has already committed, so nothing here
        may reach the caller. A rollback on a connection that has just dropped
        raises a second driver exception (the hazard `panel_errors` documents),
        and unguarded it turned a missing log line into a 500 for work that
        actually succeeded."""
        actor = make_panel_user(panel_db, email="ktos@fundacja.test", password=None)

        class DeadSession:
            def add(self, _row: object) -> None:
                pass

            def commit(self) -> None:
                raise OperationalError("INSERT", {}, Exception("connection lost"))

            def rollback(self) -> None:
                raise OperationalError("ROLLBACK", {}, Exception("connection lost"))

        with caplog.at_level(logging.ERROR, logger="app.services.panel_audit"):
            record_event(DeadSession(), actor=actor, action=AuditAction.DOCUMENT_CREATED)

        assert any("could not roll back" in line for line in caplog.messages)

    def test_the_actor_address_is_kept_beside_the_foreign_key(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        """So a row stays readable after the account behind it is gone, the same
        reason `panel_login_attempts` stores the address as typed."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        panel_client.post(
            "/api/panel/documents",
            headers=auth_header(token),
            json={"title": TITLE, "content": "Tresc."},
        )

        created = [
            entry
            for entry in journal(panel_client, token)
            if entry["action"] == AuditAction.DOCUMENT_CREATED
        ]
        assert created[0]["actor_email"] == panel_admin.email
        assert panel_admin.role is PanelRole.ADMIN
