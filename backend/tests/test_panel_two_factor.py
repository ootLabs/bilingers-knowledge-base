"""The panel's second factor (T-83).

Taking over an editor's account is a leak of the whole knowledge base, and there
is nothing behind the panel to slow that down. These are the rules that make the
second factor a second factor rather than a formality.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import unquote, urlparse

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelLoginAttempt, PanelUser
from app.models.two_factor import PanelTotpSecret
from app.services import panel_totp, panel_two_factor
from app.services.panel_login_audit import LoginFailure
from app.services.panel_totp import TOTP_INTERVAL
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


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    """A clock the test moves by hand, for both halves of the service.

    Reaching the step either side of the current one is the whole point of the
    replay rule, and waiting half a minute inside a test is not an option.
    `pyotp` keeps its own reference to `datetime`, so codes are still generated
    against the real clock and the test says which moment it wants one for.

    Both modules are patched, and that matters: `panel_totp.matched_step` is
    what decides which step a code belongs to, and `panel_two_factor` is what
    stamps a spent backup code. Freezing only one of them leaves the tests
    reading two different clocks, which passes until a run happens to straddle
    a real 30 second boundary.
    """
    state = {"now": datetime.now(UTC)}

    class Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return state["now"]

    monkeypatch.setattr(panel_two_factor, "datetime", Clock)
    monkeypatch.setattr(panel_totp, "datetime", Clock)
    return state


def enrol(client: TestClient, token: str) -> str:
    response = client.post("/api/panel/users/me/two-factor", headers=auth_header(token))
    assert response.status_code == 201, response.text
    return response.json()["secret"]


def turn_on(
    client: TestClient, token: str, moment: datetime | None = None
) -> tuple[str, list[str]]:
    """Enrol and confirm, returning the secret and the printed codes.

    `moment` is which step the confirming code belongs to. It matters because
    confirming spends that step, so a test that then signs in has to move the
    clock and ask for a code at the new moment; passing the same one back would
    be asking for the code that was just used up.
    """
    secret = enrol(client, token)
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    response = client.post(
        "/api/panel/users/me/two-factor/confirm",
        headers=auth_header(token),
        json={"code": totp.at(moment) if moment is not None else totp.now()},
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
        # The label is percent-encoded, as the Key URI format requires and as
        # every authenticator app expects, so the address is only there once the
        # path is decoded. Asserting on the raw URI would be asserting that the
        # encoding is missing.
        label = unquote(urlparse(body["otpauth_uri"]).path.lstrip("/"))
        assert label == f"{settings.panel_totp_issuer}:{panel_editor.email}"

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
        # The header is what tells this 503 apart from a database outage on the
        # same endpoint, for a frontend that never reads a failed response's
        # body. Without it the editor is told to wait for something that will
        # not fix itself.
        assert response.headers["X-Second-Factor"] == "not-configured"
        assert panel_db.execute(select(PanelTotpSecret)).first() is None

    def test_a_rotated_key_says_so_on_the_login_endpoint_too(
        self,
        encryption_key: None,
        panel_client: TestClient,
        panel_editor: PanelUser,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An enrolled account whose secret can no longer be decrypted is the
        one place this condition reaches somebody who is not in the settings
        screen. It has to carry the same header: without it the frontend reads
        the 503 as a database outage and tells the editor to try again in a
        moment, which is advice about something that will never fix itself."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token)
        monkeypatch.setattr(
            settings, "panel_totp_encryption_key", Fernet.generate_key().decode("ascii")
        )

        response = sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, pyotp.TOTP(secret).now()
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "two_factor_not_configured"
        assert response.headers["X-Second-Factor"] == "not-configured"


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
        self,
        encryption_key: None,
        frozen_clock: dict[str, datetime],
        panel_client: TestClient,
        panel_editor: PanelUser,
    ) -> None:
        """A step later than the one confirmation spent, which is how a real
        login looks: the setup screen is finished before anybody signs in."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token, frozen_clock["now"])

        frozen_clock["now"] += timedelta(seconds=TOTP_INTERVAL)
        response = sign_in(
            panel_client,
            panel_editor.email,
            EDITOR_PASSWORD,
            pyotp.TOTP(secret, interval=TOTP_INTERVAL).at(frozen_clock["now"]),
        )

        assert response.status_code == 201
        assert response.json()["token"]

    def test_the_code_that_switched_it_on_cannot_then_log_in(
        self,
        encryption_key: None,
        frozen_clock: dict[str, datetime],
        panel_client: TestClient,
        panel_editor: PanelUser,
    ) -> None:
        """Confirmation is a use like any other, so it spends the code.

        This is the one code the panel ever puts on a screen, next to the key
        somebody may be reading over a shoulder. Leaving it unspent made it the
        only code that worked twice."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token, frozen_clock["now"])
        used = pyotp.TOTP(secret, interval=TOTP_INTERVAL).at(frozen_clock["now"])

        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, used
        ).status_code == 401

    def test_the_same_six_digits_do_not_work_twice(
        self,
        encryption_key: None,
        frozen_clock: dict[str, datetime],
        panel_client: TestClient,
        panel_editor: PanelUser,
    ) -> None:
        """Otherwise anybody who read them over a shoulder gets a second use out
        of them, inside the same 30 second window."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token, frozen_clock["now"])
        frozen_clock["now"] += timedelta(seconds=TOTP_INTERVAL)
        code = pyotp.TOTP(secret, interval=TOTP_INTERVAL).at(frozen_clock["now"])

        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, code
        ).status_code == 201
        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, code
        ).status_code == 401

    def test_a_spent_code_stays_spent_once_the_clock_rolls_over(
        self,
        encryption_key: None,
        frozen_clock: dict[str, datetime],
        panel_client: TestClient,
        panel_editor: PanelUser,
    ) -> None:
        """The step recorded has to be the step the CODE belongs to, not the one
        the clock happens to be in. `valid_window=1` keeps six digits verifiable
        for the step either side of their own, so recording the clock's step let
        the same digits back in the moment it rolled over: spent at step N, and
        at N+1 they verified again and N+1 > N passed the replay check. Sixty
        seconds of reuse for something the module promises is single use."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token, frozen_clock["now"])
        frozen_clock["now"] += timedelta(seconds=TOTP_INTERVAL)
        code = pyotp.TOTP(secret, interval=TOTP_INTERVAL).at(frozen_clock["now"])

        assert sign_in(
            panel_client, panel_editor.email, EDITOR_PASSWORD, code
        ).status_code == 201

        frozen_clock["now"] += timedelta(seconds=TOTP_INTERVAL)
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
        self,
        encryption_key: None,
        frozen_clock: dict[str, datetime],
        panel_client: TestClient,
        panel_editor: PanelUser,
    ) -> None:
        """A stolen session must not be able to quietly remove the thing that
        makes it useless."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        secret, _codes = turn_on(panel_client, token, frozen_clock["now"])

        refused = panel_client.post(
            "/api/panel/users/me/two-factor/disable",
            headers=auth_header(token),
            json={"code": "000000"},
        )
        assert refused.status_code == 422

        # A fresh step, because confirming spent the previous one.
        frozen_clock["now"] += timedelta(seconds=TOTP_INTERVAL)
        accepted = panel_client.post(
            "/api/panel/users/me/two-factor/disable",
            headers=auth_header(token),
            json={"code": pyotp.TOTP(secret, interval=TOTP_INTERVAL).at(frozen_clock["now"])},
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
