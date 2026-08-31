"""Account management: the administrator's half of the panel.

The rules worth testing here are the ones that are easy to get wrong and
expensive when they are: an editor must not be able to create accounts, a
deactivated account must lose access immediately rather than when its session
happens to expire, and an administrator must not be able to lock themselves
out of a panel that has no other way in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import cli
from app.models.panel import PanelRole, PanelUser
from app.schemas.panel import PanelUserUpdateRequest
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


class TestChangingAnAccount:
    def test_a_role_can_be_changed(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.patch(
            f"/api/panel/users/{panel_editor.id}",
            headers=auth_header(token),
            json={"role": "admin"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_deactivating_an_account_ends_its_sessions_at_once(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        """An account that keeps working after being switched off has not been
        switched off."""
        editor_token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        admin_token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)

        panel_client.patch(
            f"/api/panel/users/{panel_editor.id}",
            headers=auth_header(admin_token),
            json={"is_active": False},
        )
        assert panel_client.get(
            "/api/panel/users/me", headers=auth_header(editor_token)
        ).status_code == 401

    def test_an_administrator_cannot_deactivate_themselves(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        """With one or two administrators, this is the difference between a
        misclick and a panel nobody can administer."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.patch(
            f"/api/panel/users/{panel_admin.id}",
            headers=auth_header(token),
            json={"is_active": False},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "self_lockout_refused"
        assert panel_admin.is_active is True

    def test_an_administrator_cannot_demote_themselves(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.patch(
            f"/api/panel/users/{panel_admin.id}",
            headers=auth_header(token),
            json={"role": "editor"},
        )
        assert response.status_code == 403
        assert panel_admin.role is PanelRole.ADMIN

    def test_an_administrator_may_still_edit_their_own_account_harmlessly(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        """Only the two changes that lock the panel are refused, not every self-edit."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.patch(
            f"/api/panel/users/{panel_admin.id}",
            headers=auth_header(token),
            json={"role": "admin", "is_active": True},
        )
        assert response.status_code == 200

    def test_an_unknown_account_is_a_404(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.patch(
            "/api/panel/users/999999",
            headers=auth_header(token),
            json={"is_active": False},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "panel_user_not_found"


class TestAdministratorIssuedResets:
    def test_an_administrator_can_issue_a_reset_token(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        """There is no mail path yet, so the token comes back in the response
        and the administrator hands it over."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.post(
            f"/api/panel/users/{panel_editor.id}/password-resets",
            headers=auth_header(token),
        )
        assert response.status_code == 201
        assert response.json()["token"]

    def test_issuing_a_reset_does_not_throw_the_person_out(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        """A token is not proof anything is wrong; sessions end when it is spent."""
        editor_token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        admin_token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)

        panel_client.post(
            f"/api/panel/users/{panel_editor.id}/password-resets",
            headers=auth_header(admin_token),
        )
        assert panel_client.get(
            "/api/panel/users/me", headers=auth_header(editor_token)
        ).status_code == 200

    def test_an_issued_reset_can_be_spent(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        admin_token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        issued = panel_client.post(
            f"/api/panel/users/{panel_editor.id}/password-resets",
            headers=auth_header(admin_token),
        ).json()

        assert panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": issued["token"], "new_password": NEW_PASSWORD},
        ).status_code == 204
        assert log_in(panel_client, panel_editor.email, NEW_PASSWORD)

    def test_a_reset_for_an_unknown_account_is_a_404(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        response = panel_client.post(
            "/api/panel/users/999999/password-resets", headers=auth_header(token)
        )
        assert response.status_code == 404

    def test_an_editor_cannot_issue_a_reset_for_somebody_else(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            f"/api/panel/users/{panel_admin.id}/password-resets", headers=auth_header(token)
        )
        assert response.status_code == 403


class TestBootstrapCommand:
    """`python -m app.cli create-admin` is how the first account exists at all.

    Runs on `panel_db` like the rest: asking for `migrated_database` here would
    skip the only path to the first administrator in exactly the run that has
    no database, which is the run this suite exists to stay useful in.
    """

    def test_it_creates_an_administrator_and_prints_a_token(
        self,
        cheap_password_hashing: None,
        panel_db: Session,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert cli.main(["create-admin", "pierwsza@fundacja.test"], lambda: panel_db) == 0

        printed = capsys.readouterr().out
        assert "pierwsza@fundacja.test" in printed
        assert "One-time setup token:" in printed

    def test_the_account_it_creates_is_an_administrator_with_no_password(
        self,
        cheap_password_hashing: None,
        panel_db: Session,
        panel_client: TestClient,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cli.main(["create-admin", "pierwsza@fundacja.test"], lambda: panel_db)
        token = capsys.readouterr().out.split("One-time setup token: ")[1].split("\n")[0]

        assert panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        ).status_code == 204

        session_token = log_in(panel_client, "pierwsza@fundacja.test", NEW_PASSWORD)
        me = panel_client.get("/api/panel/users/me", headers=auth_header(session_token)).json()
        assert me["role"] == "admin"

    def test_it_refuses_to_create_a_second_account_for_one_address(
        self,
        cheap_password_hashing: None,
        panel_db: Session,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_panel_user(panel_db, email="pierwsza@fundacja.test", password=None)
        assert cli.main(["create-admin", "pierwsza@fundacja.test"], lambda: panel_db) == 1
        assert "already exists" in capsys.readouterr().out
