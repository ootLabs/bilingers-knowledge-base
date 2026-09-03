"""Logging into the panel: input rules and credentials.

The panel is the only screen someone outside the team logs into, and it is the
door to material covered by an NDA. So these tests are about refusals as much
as about access: what a wrong password answers, and what each kind of account
that may not get in answers instead.

Every test here runs against real SQL (see the `panel_db` fixture): a stub
would only prove that the router calls something. Session lifetime and the
PostgreSQL-specific guarantees live in `test_panel_sessions.py`; password
resets and changing your own password live in `test_panel_passwords.py`, the
lockout in `test_panel_lockout.py`, and the per-IP throttle in front of all of
it in `test_rate_limit.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.panel import PanelUser
from app.schemas.panel import PanelLoginRequest, PanelUserResponse, PasswordResetConfirmRequest
from app.services.panel_auth import LoginFailure, as_utc, normalise_email
from tests.conftest import (
    EDITOR_PASSWORD,
    attempts_for,
    auth_header,
    log_in,
    make_panel_user,
)


class TestInputRules:
    """No database needed: the boundary rejects these before anything runs."""

    def test_an_address_is_normalised_so_one_person_gets_one_account(self) -> None:
        assert normalise_email("  Magdalena@Fundacja.TEST ") == "magdalena@fundacja.test"

    def test_a_naive_timestamp_is_read_as_utc(self) -> None:
        """Comparing a naive timestamp with an aware one raises, so expiry
        checks would break on a row that has not been through the database."""
        naive = datetime(2026, 8, 28, 12, 0)
        assert as_utc(naive).tzinfo is UTC
        aware = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
        assert as_utc(aware) is aware

    def test_login_accepts_any_password_length(self) -> None:
        """The rule for a new password does not belong on the login form:
        rejecting a short one there tells an attacker the real one is longer."""
        assert PanelLoginRequest(email="a@b.test", password="x").password == "x"

    def test_a_new_password_below_the_floor_is_refused(self) -> None:
        with pytest.raises(ValueError):
            PasswordResetConfirmRequest(token="t", new_password="krotkie")

    def test_a_new_password_bcrypt_would_truncate_is_refused(self) -> None:
        with pytest.raises(ValueError):
            PasswordResetConfirmRequest(token="t", new_password="ą" * 40)

    def test_the_account_shape_carries_no_credential(self) -> None:
        """The panel shows accounts; a hash must never reach the browser."""
        assert "password_hash" not in PanelUserResponse.model_fields
        assert "has_password" in PanelUserResponse.model_fields


class TestLogin:
    def test_valid_credentials_open_a_session(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": panel_editor.email, "password": EDITOR_PASSWORD},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == panel_editor.email
        assert body["user"]["role"] == "editor"
        assert body["token"]
        assert "password_hash" not in body["user"]

    def test_the_address_is_matched_case_insensitively(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": panel_editor.email.upper(), "password": EDITOR_PASSWORD},
        )
        assert response.status_code == 201

    def test_the_token_identifies_its_owner(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        response = panel_client.get("/api/panel/users/me", headers=auth_header(token))
        assert response.status_code == 200
        assert response.json()["email"] == panel_editor.email

    def test_a_wrong_password_is_refused_and_recorded(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": panel_editor.email, "password": "nie-to-haslo-wcale"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_credentials"

        attempts = attempts_for(panel_db, panel_editor.email)
        assert [(a.succeeded, a.reason) for a in attempts] == [
            (False, LoginFailure.BAD_PASSWORD)
        ]

    def test_an_unknown_address_is_recorded_too(
        self, panel_client: TestClient, panel_db: Session
    ) -> None:
        """An attack on a five-account panel is mostly failures against
        addresses that do not exist. Logging only real accounts hides it."""
        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": "nikt@fundacja.test", "password": "cokolwiek-tutaj"},
        )
        assert response.status_code == 401

        attempts = attempts_for(panel_db, "nikt@fundacja.test")
        assert [(a.succeeded, a.reason, a.panel_user_id) for a in attempts] == [
            (False, LoginFailure.UNKNOWN_ACCOUNT, None)
        ]

    def test_an_unknown_address_answers_exactly_like_a_wrong_password(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        unknown = panel_client.post(
            "/api/panel/sessions",
            json={"email": "nikt@fundacja.test", "password": "cokolwiek-tutaj"},
        )
        wrong = panel_client.post(
            "/api/panel/sessions",
            json={"email": panel_editor.email, "password": "cokolwiek-tutaj"},
        )
        assert unknown.status_code == wrong.status_code
        assert unknown.json() == wrong.json()

    def test_an_account_with_no_password_cannot_log_in(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        """The state a freshly created account is in until its owner sets one."""
        user = make_panel_user(panel_db, email="nowa@fundacja.test", password=None)
        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": user.email, "password": "cokolwiek-tutaj"},
        )
        assert response.status_code == 401
        assert attempts_for(panel_db, user.email)[0].reason == LoginFailure.NO_PASSWORD_SET

    def test_a_deactivated_account_cannot_log_in(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        user = make_panel_user(
            panel_db, email="byla@fundacja.test", password=EDITOR_PASSWORD, is_active=False
        )
        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": user.email, "password": EDITOR_PASSWORD},
        )
        assert response.status_code == 401
        assert attempts_for(panel_db, user.email)[0].reason == LoginFailure.INACTIVE_ACCOUNT

    def test_the_right_password_on_a_deactivated_account_does_not_count_as_a_failure(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        """Otherwise reactivating the account leaves it locked on its own
        correct password, with no operation in the panel to clear that."""
        user = make_panel_user(
            panel_db, email="byla@fundacja.test", password=EDITOR_PASSWORD, is_active=False
        )
        panel_client.post(
            "/api/panel/sessions",
            json={"email": user.email, "password": EDITOR_PASSWORD},
        )
        assert user.failed_login_count == 0
        assert user.locked_until is None

    def test_a_successful_login_is_recorded_with_its_account(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        attempt = attempts_for(panel_db, panel_editor.email)[-1]
        assert attempt.succeeded is True
        assert attempt.panel_user_id == panel_editor.id
        assert attempt.reason is None
        assert panel_editor.last_login_at is not None
