"""The in-process login throttle: the window itself, that it does not grow
forever, and what a throttled login leaves behind over HTTP.

The whole subject lives here rather than half of it in `test_panel_auth.py`:
that file owns the door (input rules and credentials), `test_panel_lockout.py`
owns what happens to an account that keeps failing, and this one owns the
limiter standing in front of both.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.services import rate_limit
from app.services.panel_auth import LoginFailure
from tests.conftest import attempts_for


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    rate_limit.reset()
    yield
    rate_limit.reset()


class TestCheck:
    def test_allows_attempts_under_the_limit(self) -> None:
        for _ in range(3):
            rate_limit.check("1.2.3.4", max_attempts=3, window_minutes=5)

    def test_refuses_once_the_limit_is_reached(self) -> None:
        for _ in range(3):
            rate_limit.check("1.2.3.4", max_attempts=3, window_minutes=5)
        with pytest.raises(rate_limit.TooManyAttempts):
            rate_limit.check("1.2.3.4", max_attempts=3, window_minutes=5)

    def test_different_keys_do_not_share_a_budget(self) -> None:
        for _ in range(3):
            rate_limit.check("1.2.3.4", max_attempts=3, window_minutes=5)
        rate_limit.check("5.6.7.8", max_attempts=3, window_minutes=5)

    def test_only_the_first_refusal_in_a_window_is_flagged_for_reporting(self) -> None:
        """A flood is refused once per request but only worth recording once:
        the caller writes an audit row when this flag is set, and a row per
        refused request would make the audit table the flood's target."""
        rate_limit.check("1.2.3.4", max_attempts=1, window_minutes=5)

        flags: list[bool] = []
        for _ in range(3):
            with pytest.raises(rate_limit.TooManyAttempts) as excinfo:
                rate_limit.check("1.2.3.4", max_attempts=1, window_minutes=5)
            flags.append(excinfo.value.first_in_window)
        assert flags == [True, False, False]

    def test_a_later_window_is_reported_again(self) -> None:
        """Otherwise a second attack on the same address, days later, would be
        the one flood that leaves no trace at all.

        The state is set directly rather than by waiting out a window: the
        shortest one this is configured with is five minutes.
        """
        now = datetime.now(UTC)
        rate_limit._attempts["1.2.3.4"] = [now]
        rate_limit._reported["1.2.3.4"] = now - timedelta(hours=1)

        with pytest.raises(rate_limit.TooManyAttempts) as excinfo:
            rate_limit.check("1.2.3.4", max_attempts=1, window_minutes=5)
        assert excinfo.value.first_in_window is True

    def test_retry_after_is_positive_and_bounded_by_the_window(self) -> None:
        for _ in range(3):
            rate_limit.check("1.2.3.4", max_attempts=3, window_minutes=5)
        with pytest.raises(rate_limit.TooManyAttempts) as excinfo:
            rate_limit.check("1.2.3.4", max_attempts=3, window_minutes=5)
        assert 0 < excinfo.value.retry_after_seconds <= 5 * 60


class TestSweeping:
    def test_stale_keys_are_dropped_after_enough_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A flood of distinct one-off addresses must not grow the dict
        forever: `check` only ever prunes the key it was called with, so
        nothing else would ever remove an address seen once and never again."""
        monkeypatch.setattr(rate_limit, "_SWEEP_EVERY", 5)
        rate_limit._attempts["stale"] = [datetime.now(UTC) - timedelta(hours=1)]
        # Swept on the same schedule: an address refused once and never seen
        # again would otherwise keep an entry here forever, which is the leak
        # the sweep above exists to prevent, just in the other dict.
        rate_limit._reported["stale"] = datetime.now(UTC) - timedelta(hours=1)

        for index in range(5):
            rate_limit.check(f"fresh-{index}", max_attempts=100, window_minutes=5)

        assert "stale" not in rate_limit._attempts
        assert "stale" not in rate_limit._reported
        assert "fresh-0" in rate_limit._attempts


class TestIpRateLimiting:
    def test_too_many_attempts_from_one_address_are_throttled(
        self, panel_client: TestClient, panel_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Thrown before `login` runs, so a flood does not pay for bcrypt."""
        monkeypatch.setattr(settings, "panel_login_ip_max_attempts", 3)

        for _ in range(3):
            response = panel_client.post(
                "/api/panel/sessions",
                json={"email": "ktos@fundacja.test", "password": "cokolwiek"},
            )
            assert response.status_code == 401

        throttled = panel_client.post(
            "/api/panel/sessions",
            json={"email": "ktos@fundacja.test", "password": "cokolwiek"},
        )
        assert throttled.status_code == 429
        assert int(throttled.headers["retry-after"]) > 0
        # Three attempts plus one row for the refusal itself. The fourth
        # request never reached `login`, so its row is the throttle's own.
        attempts = attempts_for(panel_db, "ktos@fundacja.test")
        assert [attempt.reason for attempt in attempts] == [
            LoginFailure.UNKNOWN_ACCOUNT,
            LoginFailure.UNKNOWN_ACCOUNT,
            LoginFailure.UNKNOWN_ACCOUNT,
            LoginFailure.IP_THROTTLED,
        ]
        assert attempts[-1].succeeded is False
        assert attempts[-1].panel_user_id is None

    def test_a_throttled_flood_is_recorded_once_per_window(
        self,
        panel_client: TestClient,
        panel_db: Session,
        cheap_password_hashing: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The audit table has to show that a flood happened without becoming
        the thing the flood fills up: retention is still an open question
        (B-07), and the thousandth row says nothing the first did not."""
        monkeypatch.setattr(settings, "panel_login_ip_max_attempts", 1)

        for _ in range(20):
            panel_client.post(
                "/api/panel/sessions",
                json={"email": "ktos@fundacja.test", "password": "cokolwiek"},
            )

        reasons = [attempt.reason for attempt in attempts_for(panel_db, "ktos@fundacja.test")]
        assert reasons.count(LoginFailure.IP_THROTTLED) == 1
