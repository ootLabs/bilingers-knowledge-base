"""The per-account lockout: counting failures, locking, and recovering.

Split out of `test_panel_auth.py` along an existing class boundary. That file
answers "does this password open the door"; this one answers "how many wrong
answers does the door take, and what happens to the account afterwards".

The last test here is the one the counter's row lock exists for, in a form
that does not need two threads to be deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelUser
from app.services.panel_auth import LoginFailure
from tests.conftest import EDITOR_PASSWORD, attempts_for, log_in, make_panel_user


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
        assert locked.status_code == 401
        assert locked.json()["detail"] == "invalid_credentials"

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
        assert response.status_code == 401

    def test_a_locked_account_answers_exactly_like_a_wrong_password(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """A distinct status for a locked account would tell an anonymous
        caller which addresses have one after a handful of requests."""
        for _ in range(settings.panel_login_max_attempts):
            self._fail_once(panel_client, panel_editor)

        locked = self._fail_once(panel_client, panel_editor)
        wrong = panel_client.post(
            "/api/panel/sessions",
            json={"email": "nikt@fundacja.test", "password": "cokolwiek-tutaj"},
        )
        assert locked.status_code == wrong.status_code
        assert locked.json() == wrong.json()

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
            assert self._fail_once(panel_client, panel_editor).status_code == 401
        assert panel_editor.locked_until == locked_until

    def test_wrong_passwords_do_not_lock_a_deactivated_account(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        """An account that is switched off cannot be logged into with any
        password, so there is nothing here for the lockout to protect - and
        charging these failures would hand anybody a way to lock an account
        that nothing in the panel can unlock: switching it back on does not
        clear `locked_until`, so its owner would return to a 401 on their own
        correct password.
        """
        user = make_panel_user(
            panel_db, email="byla@fundacja.test", password=EDITOR_PASSWORD, is_active=False
        )
        for _ in range(settings.panel_login_max_attempts):
            assert self._fail_once(panel_client, user).status_code == 401

        assert user.failed_login_count == 0
        assert user.locked_until is None

        user.is_active = True
        panel_db.flush()
        response = panel_client.post(
            "/api/panel/sessions",
            json={"email": user.email, "password": EDITOR_PASSWORD},
        )
        assert response.status_code == 201

    def test_a_wrong_password_on_a_deactivated_account_is_still_recorded(
        self, panel_client: TestClient, cheap_password_hashing: None, panel_db: Session
    ) -> None:
        """Not counting the failure must not mean forgetting it: somebody
        guessing at a switched-off account is exactly what the audit table is
        for, and the reason recorded is the real one, not `inactive_account`."""
        user = make_panel_user(
            panel_db, email="byla@fundacja.test", password=EDITOR_PASSWORD, is_active=False
        )
        self._fail_once(panel_client, user)

        attempts = attempts_for(panel_db, user.email)
        assert [(a.succeeded, a.reason) for a in attempts] == [
            (False, LoginFailure.BAD_PASSWORD)
        ]

    def test_a_successful_login_clears_the_counter(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        for _ in range(settings.panel_login_max_attempts - 1):
            self._fail_once(panel_client, panel_editor)
        log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        assert panel_editor.failed_login_count == 0

    def test_the_counter_is_read_from_the_row_not_from_a_stale_object(
        self, panel_client: TestClient, panel_editor: PanelUser, panel_db: Session
    ) -> None:
        """The deterministic form of the race the row lock exists to close.

        Two concurrent bad passwords both load the account before either
        writes, so one of them holds an object whose `failed_login_count` is
        already behind the row. The `UPDATE` below puts the request's session
        in exactly that state, without needing two threads: it moves the
        column and leaves the mapped object untouched.

        `SELECT ... FOR UPDATE` alone does not fix it. The row it locks is
        already in the session's identity map, and SQLAlchemy hands back the
        attributes it was loaded with unless asked to repopulate them, so the
        increment would land on 1 here instead of 4 and one failure would
        vanish. SQLite ignores the lock itself, which is fine: what is under
        test is which value the increment counts from.
        """
        behind_by = 3
        assert behind_by < settings.panel_login_max_attempts - 1
        panel_db.execute(
            update(PanelUser)
            .where(PanelUser.id == panel_editor.id)
            .values(failed_login_count=behind_by)
            # Without this the ORM would helpfully apply the new value to the
            # mapped object as well, which is precisely the staleness under
            # test: the session has to be left believing the old count.
            .execution_options(synchronize_session=False)
        )

        assert self._fail_once(panel_client, panel_editor).status_code == 401

        counted = panel_db.execute(
            select(PanelUser.failed_login_count).where(PanelUser.id == panel_editor.id)
        ).scalar_one()
        assert counted == behind_by + 1
        assert panel_editor.locked_until is None
