"""Changing an existing account: role, activity, and administrator-issued resets.

Split out of `test_panel_users.py` along an existing class boundary:
everything here acts on an account that already exists, as opposed to that
file's creation and listing rules.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.panel import PanelRole, PanelUser
from tests.conftest import ADMIN_PASSWORD, EDITOR_PASSWORD, auth_header, log_in

NEW_PASSWORD = "haslo-ustawione-samemu"


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

    def test_a_reset_for_a_deactivated_account_is_refused(
        self, panel_client: TestClient, panel_admin: PanelUser, panel_editor: PanelUser
    ) -> None:
        """A token issued anyway would come back to `set_password_with_token`
        as a plain invalid-token 400, with nothing telling anyone why."""
        admin_token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        panel_client.patch(
            f"/api/panel/users/{panel_editor.id}",
            headers=auth_header(admin_token),
            json={"is_active": False},
        )

        response = panel_client.post(
            f"/api/panel/users/{panel_editor.id}/password-resets",
            headers=auth_header(admin_token),
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "panel_user_inactive"

    def test_an_editor_cannot_issue_a_reset_for_somebody_else(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_admin: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            f"/api/panel/users/{panel_admin.id}/password-resets", headers=auth_header(token)
        )
        assert response.status_code == 403
