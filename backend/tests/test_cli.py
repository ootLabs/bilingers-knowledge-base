"""`python -m app.cli create-admin` - the only way the first account exists.

Split out of `test_panel_users.py`: this is the one thing in `app.cli`, a
different module from the HTTP account management it otherwise tests.

Runs on `panel_db` like the rest: asking for `migrated_database` here would
skip the only path to the first administrator in exactly the run that has no
database, which is the run this suite exists to stay useful in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import cli
from app.services.panel_users import list_panel_users
from tests.conftest import auth_header, log_in, make_panel_user

NEW_PASSWORD = "haslo-ustawione-samemu"


class TestBootstrapCommand:
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

    def test_it_refuses_a_malformed_address(
        self,
        panel_db: Session,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The only route to the first administrator; a typo here is otherwise
        permanent, unlike a normal account created through the API."""
        assert cli.main(["create-admin", "Adam Nowak"], lambda: panel_db) == 1
        assert "is not a valid email address" in capsys.readouterr().out
        assert list_panel_users(panel_db) == []

    def test_it_refuses_to_create_a_second_account_for_one_address(
        self,
        cheap_password_hashing: None,
        panel_db: Session,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_panel_user(panel_db, email="pierwsza@fundacja.test", password=None)
        assert cli.main(["create-admin", "pierwsza@fundacja.test"], lambda: panel_db) == 1
        assert "already exists" in capsys.readouterr().out
