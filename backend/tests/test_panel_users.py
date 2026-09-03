"""Account management: who may create accounts, and creating one.

The rules worth testing here are the ones that are easy to get wrong and
expensive when they are: an editor must not be able to create accounts, and a
duplicate or malformed address must be refused without discarding other
pending work.

Changing an existing account (role, activity, administrator-issued resets)
lives in `test_panel_user_management.py`; `python -m app.cli create-admin` is
a different module and lives in `test_cli.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.panel import PanelRole, PanelUser
from app.schemas.panel import PanelUserUpdateRequest
from app.services.panel_errors import PanelServiceUnavailable
from app.services.panel_users import EmailAlreadyUsed, create_panel_user
from tests.conftest import (
    ADMIN_PASSWORD,
    EDITOR_PASSWORD,
    auth_header,
    log_in,
    make_panel_user,
)

NEW_PASSWORD = "haslo-ustawione-samemu"


class TestUpdateShape:
    """No database: the boundary rejects an update that says nothing."""

    def test_an_empty_update_is_refused(self) -> None:
        with pytest.raises(ValueError):
            PanelUserUpdateRequest()

    def test_one_field_is_enough(self) -> None:
        assert PanelUserUpdateRequest(is_active=False).role is None


class TestWhoMayManageAccounts:
    def test_an_editor_cannot_list_accounts(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.get("/api/panel/users", headers=auth_header(token))
        assert response.status_code == 403
        assert response.json()["detail"] == "admin_required"

    def test_an_editor_cannot_create_accounts(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            "/api/panel/users",
            headers=auth_header(token),
            json={"email": "ktos@fundacja.test", "role": "editor"},
        )
        assert response.status_code == 403

    def test_account_management_needs_a_session_at_all(
        self, panel_client: TestClient
    ) -> None:
        assert panel_client.get("/api/panel/users").status_code == 401


class TestCreatingAnAccount:
    def test_an_administrator_creates_an_account_and_gets_a_setup_token(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        """There is no registration form; this is the only way in."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.post(
            "/api/panel/users",
            headers=auth_header(token),
            json={"email": "Justyna@Fundacja.test", "role": "editor"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "justyna@fundacja.test"
        assert body["user"]["has_password"] is False
        assert body["token"]
        assert body["expires_at"]

    def test_the_new_account_sets_its_own_password_and_logs_in(
        self, panel_client: TestClient, panel_admin: PanelUser, cheap_password_hashing: None
    ) -> None:
        """The administrator never learns the password they handed a token for."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        created = panel_client.post(
            "/api/panel/users",
            headers=auth_header(token),
            json={"email": "justyna@fundacja.test", "role": "editor"},
        ).json()

        assert panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": created["token"], "new_password": NEW_PASSWORD},
        ).status_code == 204
        assert log_in(panel_client, "justyna@fundacja.test", NEW_PASSWORD)

    def test_the_token_comes_back_with_its_own_expiry(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        """Issuing a reset expires the previous one. Reading the expiry back off
        the account's unordered list of resets can return the row just killed,
        which would advertise a live token as already dead."""
        admin_token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        first = panel_client.post(
            f"/api/panel/users/{panel_editor.id}/password-resets",
            headers=auth_header(admin_token),
        ).json()
        second = panel_client.post(
            f"/api/panel/users/{panel_editor.id}/password-resets",
            headers=auth_header(admin_token),
        ).json()
        assert second["expires_at"] >= first["expires_at"]
        assert panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": second["token"], "new_password": NEW_PASSWORD},
        ).status_code == 204

    def test_a_refused_duplicate_does_not_discard_other_pending_work(
        self, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        """The failed insert is undone, nothing else is: a bare rollback here
        would throw away whatever the caller had already written."""
        existing = make_panel_user(panel_db, email="justyna@fundacja.test", password=None)
        with pytest.raises(EmailAlreadyUsed):
            create_panel_user(panel_db, email="justyna@fundacja.test", role=PanelRole.EDITOR)
        assert panel_db.get(PanelUser, existing.id) is not None

    def test_a_duplicate_address_is_refused(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.post(
            "/api/panel/users",
            headers=auth_header(token),
            json={"email": panel_admin.email, "role": "editor"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "email_already_used"

    def test_a_different_constraint_violation_is_not_reported_as_a_duplicate_address(
        self, panel_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the email uniqueness constraint should translate to
        `EmailAlreadyUsed`; anything else about the insert must not, or an
        administrator would be told about a duplicate address that does not
        exist. It comes out as the panel's infrastructure failure (a 503) with
        the original error as its cause, not as a 409 and not as a bare
        `IntegrityError` reaching the router."""

        def _boom() -> None:
            raise IntegrityError(
                "INSERT", {}, Exception("NOT NULL constraint failed: panel_users.role")
            )

        monkeypatch.setattr(panel_db, "flush", _boom)

        with pytest.raises(PanelServiceUnavailable) as refused:
            create_panel_user(panel_db, email="ktos@fundacja.test", role=PanelRole.EDITOR)
        assert isinstance(refused.value.__cause__, IntegrityError)

    def test_a_named_constraint_violation_is_matched_by_name_not_by_substring(
        self, panel_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On PostgreSQL the driver exposes the constraint name directly; a
        future constraint whose name happens to mention "email" must not be
        misread as the uniqueness one just because the word appears."""

        class _FakeDiag:
            constraint_name = "panel_users_email_verified_check"

        class _FakeOrig(Exception):
            diag = _FakeDiag()

        def _boom() -> None:
            raise IntegrityError("INSERT", {}, _FakeOrig("some unrelated email constraint"))

        monkeypatch.setattr(panel_db, "flush", _boom)

        with pytest.raises(PanelServiceUnavailable) as refused:
            create_panel_user(panel_db, email="ktos@fundacja.test", role=PanelRole.EDITOR)
        assert isinstance(refused.value.__cause__, IntegrityError)

    def test_the_named_email_uniqueness_constraint_is_still_recognised(
        self, panel_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The happy path for the named-constraint check: the real PostgreSQL
        constraint name still maps to `EmailAlreadyUsed`."""

        class _FakeDiag:
            constraint_name = "panel_users_email_key"

        class _FakeOrig(Exception):
            diag = _FakeDiag()

        def _boom() -> None:
            raise IntegrityError("INSERT", {}, _FakeOrig("duplicate key value"))

        monkeypatch.setattr(panel_db, "flush", _boom)

        with pytest.raises(EmailAlreadyUsed):
            create_panel_user(panel_db, email="ktos@fundacja.test", role=PanelRole.EDITOR)

    def test_a_malformed_address_is_refused(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.post(
            "/api/panel/users",
            headers=auth_header(token),
            json={"email": "to nie jest adres", "role": "editor"},
        )
        assert response.status_code == 422

    def test_the_listing_shows_every_account(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        listed = panel_client.get("/api/panel/users", headers=auth_header(token)).json()
        assert {row["email"] for row in listed} >= {panel_admin.email, panel_editor.email}
        assert all("password_hash" not in row for row in listed)

