"""Logging into the panel: sessions, the lockout, and password changes.

The panel is the only screen someone outside the team logs into, and it is the
door to material covered by an NDA. So these tests are about refusals as much
as about access: what a wrong password answers, what a locked account answers,
what happens to live sessions when a password changes or an account is
switched off.

Every test here runs against real SQL (see the `panel_db` fixture): a stub
would only prove that the router calls something. The last class repeats the
core of it against PostgreSQL, because the panel runs on PostgreSQL and a
schema that only exists in SQLAlchemy is not the schema in production.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelLoginAttempt, PanelRole, PanelSession, PanelUser
from app.schemas.panel import PanelLoginRequest, PanelUserResponse, PasswordResetConfirmRequest
from app.services.panel_auth import LoginFailure, as_utc, normalise_email
from app.services.panel_passwords import issue_password_reset
from tests.conftest import (
    ADMIN_PASSWORD,
    EDITOR_PASSWORD,
    auth_header,
    log_in,
    make_panel_user,
)

NEW_PASSWORD = "zupelnie-nowe-haslo"


def attempts_for(session: Session, email: str) -> list[PanelLoginAttempt]:
    return list(
        session.execute(
            select(PanelLoginAttempt)
            .where(PanelLoginAttempt.email == email)
            .order_by(PanelLoginAttempt.id)
        ).scalars()
    )


def live_sessions_of(session: Session, user: PanelUser) -> list[PanelSession]:
    return list(
        session.execute(
            select(PanelSession).where(
                PanelSession.panel_user_id == user.id,
                PanelSession.revoked_at.is_(None),
            )
        ).scalars()
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

    def test_a_successful_login_is_recorded_with_its_account(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        attempt = attempts_for(panel_db, panel_editor.email)[-1]
        assert attempt.succeeded is True
        assert attempt.panel_user_id == panel_editor.id
        assert attempt.reason is None
        assert panel_editor.last_login_at is not None


class TestLockout:
    def _fail_once(self, client: TestClient, user: PanelUser):
        return client.post(
            "/api/panel/sessions",
            json={"email": user.email, "password": "wciaz-nie-to-haslo"},
        )

    def test_the_account_locks_after_the_configured_number_of_failures(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        for _ in range(settings.panel_login_max_attempts):
            assert self._fail_once(panel_client, panel_editor).status_code == 401

        locked = self._fail_once(panel_client, panel_editor)
        assert locked.status_code == 423
        assert locked.json()["detail"] == "account_locked"

    def test_the_lock_is_advertised_as_a_delay_not_a_moment_in_time(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """`Retry-After` counts seconds (RFC 9110). A timestamp there reads as
        a delay of decades, and a client that honours it never comes back."""
        for _ in range(settings.panel_login_max_attempts):
            self._fail_once(panel_client, panel_editor)

        locked = self._fail_once(panel_client, panel_editor)
        retry_after = int(locked.headers["retry-after"])
        assert 0 < retry_after <= settings.panel_login_lockout_minutes * 60

    def test_the_right_password_is_refused_while_the_account_is_locked(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """Otherwise the limit only slows down an attacker who guesses wrong."""
        for _ in range(settings.panel_login_max_attempts):
            self._fail_once(panel_client, panel_editor)

        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": panel_editor.email, "password": EDITOR_PASSWORD},
        )
        assert response.status_code == 423

    def test_a_locked_account_recovers_on_its_own(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """An editor locked out mid-afternoon must not need an administrator."""
        for _ in range(settings.panel_login_max_attempts):
            self._fail_once(panel_client, panel_editor)

        panel_editor.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        panel_db.flush()

        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": panel_editor.email, "password": EDITOR_PASSWORD},
        )
        assert response.status_code == 201
        assert panel_editor.locked_until is None
        assert panel_editor.failed_login_count == 0

    def test_hammering_a_locked_account_does_not_extend_the_lock(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """Otherwise anyone could keep the real owner out indefinitely."""
        for _ in range(settings.panel_login_max_attempts):
            self._fail_once(panel_client, panel_editor)
        locked_until = panel_editor.locked_until

        for _ in range(3):
            assert self._fail_once(panel_client, panel_editor).status_code == 423
        assert panel_editor.locked_until == locked_until

    def test_a_successful_login_clears_the_counter(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        for _ in range(settings.panel_login_max_attempts - 1):
            self._fail_once(panel_client, panel_editor)
        log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        assert panel_editor.failed_login_count == 0


class TestSessionLifetime:
    def test_no_token_is_a_401_that_says_how_to_authenticate(
        self, panel_client: TestClient
    ) -> None:
        response = panel_client.get("/api/panel/users/me")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["detail"] == "not_authenticated"

    def test_an_invented_token_is_refused_the_same_way(self, panel_client: TestClient) -> None:
        response = panel_client.get("/api/panel/users/me", headers=auth_header("nie-taki-token"))
        assert response.status_code == 401
        assert response.json()["detail"] == "not_authenticated"

    def test_logging_out_ends_the_session(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        assert panel_client.delete(
            "/api/panel/sessions/current", headers=auth_header(token)
        ).status_code == 204
        assert panel_client.get("/api/panel/users/me", headers=auth_header(token)).status_code == 401

    def test_an_expired_session_stops_working(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        session_row = live_sessions_of(panel_db, panel_editor)[0]
        session_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        panel_db.flush()

        assert panel_client.get("/api/panel/users/me", headers=auth_header(token)).status_code == 401

    def test_a_session_expires_after_the_configured_lifetime(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        session_row = live_sessions_of(panel_db, panel_editor)[0]
        lifetime = as_utc(session_row.expires_at) - as_utc(session_row.created_at)
        assert abs(
            lifetime - timedelta(minutes=settings.panel_session_ttl_minutes)
        ) < timedelta(minutes=1)

    def test_the_token_is_never_stored_in_readable_form(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """A database dump must not hand over live sessions."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        session_row = live_sessions_of(panel_db, panel_editor)[0]
        assert token not in session_row.token_hash

    def test_a_session_dies_with_the_account_even_if_nobody_revoked_it(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """Deactivating through the API revokes sessions, but access must not
        depend on that having happened: a row switched off straight in SQL has
        to stop working too."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        panel_editor.is_active = False
        panel_db.flush()

        assert panel_client.get("/api/panel/users/me", headers=auth_header(token)).status_code == 401

    def test_the_login_is_recorded_with_where_it_came_from(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        session_row = live_sessions_of(panel_db, panel_editor)[0]
        assert session_row.ip_address
        assert session_row.user_agent


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


@pytest.mark.integration
class TestAgainstRealPostgres:
    """The same panel, on the database it actually runs on.

    Not a copy of everything above: just the path that has to work end to end,
    plus the rules PostgreSQL enforces and SQLAlchemy alone cannot.
    """

    def test_the_whole_login_and_logout_path_works(
        self,
        postgres_panel_client: TestClient,
        cheap_password_hashing: None,
        db_session: Session,
    ) -> None:
        user = make_panel_user(
            db_session, email="magdalena@fundacja.test", password=EDITOR_PASSWORD
        )
        token = log_in(postgres_panel_client, user.email, EDITOR_PASSWORD)

        assert postgres_panel_client.get(
            "/api/panel/users/me", headers=auth_header(token)
        ).status_code == 200
        assert postgres_panel_client.delete(
            "/api/panel/sessions/current", headers=auth_header(token)
        ).status_code == 204
        assert postgres_panel_client.get(
            "/api/panel/users/me", headers=auth_header(token)
        ).status_code == 401

    def test_two_accounts_cannot_share_an_address(
        self, migrated_database: None, cheap_password_hashing: None, db_session: Session
    ) -> None:
        """A check-then-insert races; the unique constraint is what holds."""
        make_panel_user(db_session, email="magdalena@fundacja.test", password=None)
        with pytest.raises(IntegrityError):
            make_panel_user(db_session, email="magdalena@fundacja.test", password=None)

    def test_the_role_is_stored_as_its_value_not_its_member_name(
        self, migrated_database: None, cheap_password_hashing: None, db_session: Session
    ) -> None:
        """Postgres storing "ADMIN" would break every client reading "admin"."""
        user = make_panel_user(
            db_session, email="magdalena@fundacja.test", password=None, role=PanelRole.ADMIN
        )
        db_session.flush()
        stored = db_session.execute(
            text("SELECT role::text FROM panel_users WHERE id = :id"), {"id": user.id}
        ).scalar_one()
        assert stored == "admin"

    def test_a_failed_attempt_survives_the_failed_login(
        self, postgres_panel_client: TestClient, cheap_password_hashing: None, db_session: Session
    ) -> None:
        """The attempt and the lockout counter are committed even though the
        request itself ends in a 401; rolling them back would make the
        brute-force limit unenforceable."""
        user = make_panel_user(
            db_session, email="magdalena@fundacja.test", password=EDITOR_PASSWORD
        )
        postgres_panel_client.post(
            "/api/panel/sessions",
            json={"email": user.email, "password": "nie-to-haslo-wcale"},
        )
        assert attempts_for(db_session, user.email)
        assert user.failed_login_count == 1
