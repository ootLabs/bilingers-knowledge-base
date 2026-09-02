"""The in-process login throttle: the window itself, and that it does not
grow forever.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services import rate_limit


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

        for index in range(5):
            rate_limit.check(f"fresh-{index}", max_attempts=100, window_minutes=5)

        assert "stale" not in rate_limit._attempts
        assert "fresh-0" in rate_limit._attempts
