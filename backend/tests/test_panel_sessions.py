"""Session lifetime, and the same panel proven against real PostgreSQL.

Split out of `test_panel_auth.py` (login and the lockout stay there) along an
existing class boundary: what a session's own lifetime looks like once
someone is in, and the handful of guarantees that are specifically
PostgreSQL's and cannot be asserted on the `panel_db` SQLite fixture (the
migration chain, the unique constraint on an address, the role enum stored
by value).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelRole, PanelSession, PanelUser
from app.services.panel_auth import as_utc
from tests.conftest import (
    EDITOR_PASSWORD,
    attempts_for,
    auth_header,
    log_in,
    make_panel_user,
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

    def test_a_nul_byte_in_the_address_never_reaches_the_driver(
        self, postgres_panel_client: TestClient, cheap_password_hashing: None
    ) -> None:
        """The review finding this closes, on the driver that produced it.

        psycopg refuses a NUL byte in a bind parameter, and the address goes
        into the account lookup as one, so before `app.schemas.panel` excluded
        control characters this request answered an unauthenticated caller with
        a 500 (and recorded no attempt). It is not an outage either: 503 would
        invite the same client to retry a request that can never work.
        """
        response = postgres_panel_client.post(
            "/api/panel/sessions",
            json={"email": "magdalena\x00@fundacja.test", "password": "cokolwiek-tutaj"},
        )
        assert response.status_code == 422

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
