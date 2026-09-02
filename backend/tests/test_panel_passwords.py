"""Password resets and changing your own password.

Split out of `test_panel_auth.py` (login and the lockout stay there) along an
existing class boundary: everything here is about setting or replacing a
credential, not about proving one at the door.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelUser
from app.services.panel_passwords import issue_password_reset
from tests.conftest import ADMIN_PASSWORD, EDITOR_PASSWORD, auth_header, log_in, make_panel_user

NEW_PASSWORD = "zupelnie-nowe-haslo"


class TestPasswordReset:
    def test_a_token_lets_its_holder_set_a_password(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        user = make_panel_user(panel_db, email="nowa@fundacja.test", password=None)
        _, token = issue_password_reset(panel_db, user)
        panel_db.flush()

        response = panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 204
        assert log_in(panel_client, user.email, NEW_PASSWORD)

    def test_a_token_works_only_once(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        user = make_panel_user(panel_db, email="nowa@fundacja.test", password=None)
        _, token = issue_password_reset(panel_db, user)
        panel_db.flush()

        payload = {"token": token, "new_password": NEW_PASSWORD}
        assert panel_client.post("/api/panel/password-resets/confirm", json=payload).status_code == 204
        second = panel_client.post("/api/panel/password-resets/confirm", json=payload)
        assert second.status_code == 400
        assert second.json()["detail"] == "invalid_reset_token"

    def test_an_expired_token_is_refused(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        user = make_panel_user(panel_db, email="nowa@fundacja.test", password=None)
        reset, token = issue_password_reset(panel_db, user)
        reset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        panel_db.flush()

        response = panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 400

    def test_an_invented_token_is_refused(self, panel_client: TestClient) -> None:
        response = panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": "nie-taki-token", "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 400

    def test_a_superseded_token_is_marked_used_not_merely_expired(
        self, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """A token that shows up twice must be visible as spent, not
        indistinguishable from one nobody ever touched."""
        first_reset, _ = issue_password_reset(panel_db, panel_editor)
        issue_password_reset(panel_db, panel_editor)
        panel_db.flush()

        assert first_reset.used_at is not None

    def test_changing_your_password_invalidates_a_live_reset_token(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """A reset token handed out before the change must not survive it."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        _, reset_token = issue_password_reset(panel_db, panel_editor)
        panel_db.flush()

        changed = panel_client.post(
            "/api/panel/users/me/password",
            json={"current_password": EDITOR_PASSWORD, "new_password": NEW_PASSWORD},
            headers=auth_header(token),
        )
        assert changed.status_code == 204

        confirm = panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": reset_token, "new_password": "jeszcze-inne-haslo"},
        )
        assert confirm.status_code == 400

    def test_spending_a_token_ends_every_session_of_that_account(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """Whoever resets a password may be doing it because it leaked."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        _, reset_token = issue_password_reset(panel_db, panel_editor)
        panel_db.flush()

        panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": reset_token, "new_password": NEW_PASSWORD},
        )
        assert panel_client.get("/api/panel/users/me", headers=auth_header(token)).status_code == 401

    def test_a_new_token_invalidates_the_one_issued_before_it(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """Two live tokens means the older one still works after someone
        believes they replaced it."""
        _, first = issue_password_reset(panel_db, panel_editor)
        _, second = issue_password_reset(panel_db, panel_editor)
        panel_db.flush()

        assert panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": first, "new_password": NEW_PASSWORD},
        ).status_code == 400
        assert panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": second, "new_password": NEW_PASSWORD},
        ).status_code == 204

    def test_setting_a_password_unlocks_a_locked_account(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """Someone who was locked out has just proved they hold the reset token."""
        for _ in range(settings.panel_login_max_attempts):
            panel_client.post(
                "/api/panel/sessions",
                json={"email": panel_editor.email, "password": "wciaz-nie-to-haslo"},
            )
        _, token = issue_password_reset(panel_db, panel_editor)
        panel_db.flush()

        panel_client.post(
            "/api/panel/password-resets/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert panel_editor.locked_until is None
        assert log_in(panel_client, panel_editor.email, NEW_PASSWORD)


class TestChangingYourOwnPassword:
    def test_the_current_password_has_to_be_right(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            "/api/panel/users/me/password",
            headers=auth_header(token),
            json={"current_password": "nie-to-haslo-wcale", "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_credentials"

    def test_the_new_password_replaces_the_old_one(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.post(
            "/api/panel/users/me/password",
            headers=auth_header(token),
            json={"current_password": EDITOR_PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 204
        assert log_in(panel_client, panel_editor.email, NEW_PASSWORD)

    def test_other_sessions_end_but_this_one_survives(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """Changing a password because it leaked has to close the other tabs;
        throwing the person out of the tab they are typing in is just rude."""
        other = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        current = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)

        panel_client.post(
            "/api/panel/users/me/password",
            headers=auth_header(current),
            json={"current_password": EDITOR_PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert panel_client.get("/api/panel/users/me", headers=auth_header(other)).status_code == 401
        assert panel_client.get(
            "/api/panel/users/me", headers=auth_header(current)
        ).status_code == 200

    def test_an_editor_may_change_their_own_password(
        self, panel_client: TestClient, panel_admin: PanelUser
    ) -> None:
        """Nothing here is administrator-only: it is your own account."""
        token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)
        assert panel_client.post(
            "/api/panel/users/me/password",
            headers=auth_header(token),
            json={"current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD},
        ).status_code == 204
