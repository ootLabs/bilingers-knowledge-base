"""The panel's second factor (T-83).

Taking over an editor's account is a leak of the whole knowledge base, and there
is nothing behind the panel to slow that down. These are the rules that make the
second factor a second factor rather than a formality.
"""

from __future__ import annotations

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelLoginAttempt, PanelUser
from app.models.two_factor import PanelTotpSecret
from app.services.panel_auth import LoginFailure
from tests.conftest import (
    ADMIN_PASSWORD,
    EDITOR_PASSWORD,
    auth_header,
    log_in,
    make_panel_user,
)


@pytest.fixture
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real key, generated per test. There is no default one on purpose."""
    monkeypatch.setattr(
        settings, "panel_totp_encryption_key", Fernet.generate_key().decode("ascii")
    )


def enrol(client: TestClient, token: str) -> str:
    response = client.post("/api/panel/users/me/two-factor", headers=auth_header(token))
    assert response.status_code == 201, response.text
    return response.json()["secret"]


def turn_on(client: TestClient, token: str) -> tuple[str, list[str]]:
    """Enrol and confirm, returning the secret and the printed codes."""
    secret = enrol(client, token)
    response = client.post(
        "/api/panel/users/me/two-factor/confirm",
        headers=auth_header(token),
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert response.status_code == 200, response.text
    return secret, response.json()["codes"]


def sign_in(client: TestClient, email: str, password: str, code: str | None = None):
    body = {"email": email, "password": password}
    if code is not None:
        body["code"] = code
    return client.post("/api/panel/sessions", json=body)


class TestTurningItOn:
    def test_enrolling_does_not_switch_anything_on(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """A secret that gated logins the moment it existed would lock out
        anybody whose authenticator did not end up holding it."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        enrol(panel_client, token)

        assert sign_in(panel_client, panel_editor.email, EDITOR_PASSWORD).status_code == 201

    def test_the_setup_screen_gets_the_key_in_both_forms(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """One for the app to scan or paste, one for a person to type."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        body = panel_client.post(
            "/api/panel/users/me/two-factor", headers=auth_header(token)
        ).json()

        assert body["secret"]
        assert body["otpauth_uri"].startswith("otpauth://totp/")
        assert panel_editor.email in body["otpauth_uri"]

    def test_confirming_prints_the_backup_codes_exactly_once(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        _secret, codes = turn_on(panel_client, token)

        assert len(codes) == settings.panel_backup_code_count
        assert len(set(codes)) == len(codes)
        status = panel_client.get(
            "/api/panel/users/me/two-factor", headers=auth_header(token)
        ).json()
        assert status == {
            "enabled": True,
            "unused_backup_codes": settings.panel_backup_code_count,
        }

    def test_a_wrong_code_does_not_turn_it_on(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        enrol(panel_client, token)

        response = panel_client.post(
            "/api/panel/users/me/two-factor/confirm",
            headers=auth_header(token),
            json={"code": "000000"},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "invalid_code"

    def test_without_a_key_nothing_is_stored_in_the_clear(
        self,
        panel_client: TestClient,
        panel_db: Session,
        panel_editor: PanelUser,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A shared default key is the same as no key, so there is no default."""
        monkeypatch.setattr(settings, "panel_totp_encryption_key", "")
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)

        response = panel_client.post(
            "/api/panel/users/me/two-factor", headers=auth_header(token)
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "two_factor_not_configured"
        assert panel_db.execute(select(PanelTotpSecret)).first() is None


class TestLoggingInWithIt:
    def test_the_password_alone_stops_being_enough(
        self, encryption_key: None, panel_client: TestClient, panel_db: Session,
        panel_editor: PanelUser,
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        turn_on(panel_client, token)

        response = sign_in(panel_client, panel_editor.email, EDITOR_PASSWORD)

        assert response.status_code == 401
        # Its own key, unlike every other refusal: this is only reachable by
        # somebody who already typed the right password, and the form needs to
        # know to ask for a code.
        assert response.json()["detail"] == "second_factor_required"
        reasons = [
            attempt.reason
            for attempt in panel_db.execute(select(PanelLoginAttempt)).scalars()
        ]
        assert LoginFailure.SECOND_FACTOR_REQUIRED in reasons

    def test_a_live_code_gets_in(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token)

        response = sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, pyotp.TOTP(secret).now()
        )

        assert response.status_code == 201
        assert response.json()["token"]

    def test_the_same_six_digits_do_not_work_twice(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """Otherwise anybody who read them over a shoulder gets a second use out
        of them, inside the same 30 second window."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token)
        code = pyotp.TOTP(secret).now()

        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, code
        ).status_code == 201
        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, code
        ).status_code == 401

    def test_a_wrong_code_is_charged_against_the_lockout(
        self, encryption_key: None, panel_client: TestClient, panel_db: Session,
        panel_editor: PanelUser,
    ) -> None:
        """Six digits are guessable in a million tries. Without the lockout
        behind it, a second factor is a weaker one, not a second one."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        turn_on(panel_client, token)

        response = sign_in(panel_client, panel_editor.email, EDITOR_PASSWORD, "000000")

        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_credentials"
        panel_db.refresh(panel_editor)
        assert panel_editor.failed_login_count == 1

    def test_a_printed_code_works_once(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """`used_at` is what makes it single use, and the row is kept rather
        than deleted so a code that turns up twice is visible."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        _secret, codes = turn_on(panel_client, token)

        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, codes[0]
        ).status_code == 201
        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, codes[0]
        ).status_code == 401

    def test_one_editors_printed_code_does_not_open_another_account(
        self, encryption_key: None, panel_client: TestClient, panel_db: Session,
        panel_editor: PanelUser,
    ) -> None:
        """The hash column is unique, so a lookup by hash finds exactly one row.
        Matching a row that belongs to somebody else must still not get in."""
        other = make_panel_user(
            panel_db, email="druga@fundacja.test", password=EDITOR_PASSWORD
        )
        mine = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        _secret, codes = turn_on(panel_client, mine)
        theirs = log_in(panel_client, other.email, EDITOR_PASSWORD)
        turn_on(panel_client, theirs)

        response = sign_in(panel_client, other.email, EDITOR_PASSWORD, codes[0])

        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_credentials"


class TestTurningItOffAndRecovering:
    def test_switching_it_off_needs_a_code(
        self, encryption_key: None, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """A stolen session must not be able to quietly remove the thing that
        makes it useless."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token)

        refused = panel_client.post(
            "/api/panel/users/me/two-factor/disable",
            headers=auth_header(token),
            json={"code": "000000"},
        )
        assert refused.status_code == 422

        accepted = panel_client.post(
            "/api/panel/users/me/two-factor/disable",
            headers=auth_header(token),
            json={"code": pyotp.TOTP(secret).now()},
        )
        assert accepted.status_code == 204

    def test_an_administrator_can_clear_a_lost_authenticator(
        self, encryption_key: None, panel_client: TestClient, panel_db: Session,
        panel_admin: PanelUser, panel_editor: PanelUser,
    ) -> None:
        """A lost phone with the printed codes in the same bag is what this is
        for. Not self-service: a reset anyone with the password could use is not
        a second factor."""
        editor_token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        turn_on(panel_client, editor_token)
        admin_token = log_in(panel_client, panel_admin.email, ADMIN_PASSWORD)

        response = panel_client.post(
            f"/api/panel/users/{panel_editor.id}/two-factor-resets",
            headers=auth_header(admin_token),
        )

        assert response.status_code == 204
        assert sign_in(panel_client, panel_editor.email, EDITOR_PASSWORD).status_code == 201

    def test_an_editor_cannot_clear_somebody_elses(
        self, encryption_key: None, panel_client: TestClient, panel_db: Session,
        panel_admin: PanelUser, panel_editor: PanelUser,
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)

        response = panel_client.post(
            f"/api/panel/users/{panel_admin.id}/two-factor-resets",
            headers=auth_header(token),
        )

        assert response.status_code == 403
