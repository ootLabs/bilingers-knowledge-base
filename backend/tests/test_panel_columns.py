"""Fitting a value into the column that holds it (T-82, T-89).

Two functions that differ in exactly one case, and that one case is the reason
both exist: a blank value. `truncated` answers `None`, which is right for a
column that permits NULL and wrong for one that does not, where it trades a
harmless empty string for an `IntegrityError`. In the change journal that error
is swallowed by design, so the row would simply vanish, and a missing journal
line is the one thing that module exists to prevent.

Unit tests rather than tests through an endpoint, deliberately. Every caller
today gets its value from a Pydantic schema that already rejects a blank, so
the bug is unreachable over HTTP and a request-level test would prove nothing.
What can be pinned is the contract the next caller will rely on.
"""

from __future__ import annotations

import pytest

from app.models.audit import PanelAuditEvent
from app.models.panel import PanelLoginAttempt
from app.services.panel_columns import (
    DETAIL_LIMIT,
    EMAIL_LIMIT,
    IP_ADDRESS_LIMIT,
    USER_AGENT_LIMIT,
    required,
    truncated,
)


class TestTheLimitsMatchTheColumns:
    """A limit that drifts from its column is worse than no limit at all: it
    looks like a guard while the driver does the refusing."""

    @pytest.mark.parametrize(
        ("limit", "column"),
        [
            (EMAIL_LIMIT, PanelLoginAttempt.__table__.c.email),
            (EMAIL_LIMIT, PanelAuditEvent.__table__.c.actor_email),
            (IP_ADDRESS_LIMIT, PanelLoginAttempt.__table__.c.ip_address),
            (USER_AGENT_LIMIT, PanelLoginAttempt.__table__.c.user_agent),
            (DETAIL_LIMIT, PanelAuditEvent.__table__.c.detail),
        ],
    )
    def test_each_limit_is_its_column_width(self, limit: int, column: object) -> None:
        assert limit == column.type.length  # type: ignore[attr-defined]


class TestTruncatedForANullableColumn:
    def test_a_long_value_is_cut_to_the_limit(self) -> None:
        assert truncated("a" * 400, EMAIL_LIMIT) == "a" * EMAIL_LIMIT

    def test_a_short_value_is_left_alone(self) -> None:
        assert truncated("redaktorka@fundacja.test", EMAIL_LIMIT) == "redaktorka@fundacja.test"

    @pytest.mark.parametrize("blank", [None, ""])
    def test_a_blank_becomes_null(self, blank: str | None) -> None:
        """Right for a column that permits NULL: an empty string is not a fact
        worth storing where nothing is allowed instead."""
        assert truncated(blank, EMAIL_LIMIT) is None


class TestRequiredForANotNullColumn:
    def test_a_long_value_is_cut_to_the_limit(self) -> None:
        assert required("a" * 400, EMAIL_LIMIT) == "a" * EMAIL_LIMIT

    def test_a_blank_stays_a_string(self) -> None:
        """The whole difference between the two functions.

        `truncated` would answer `None` here, and both columns this is used for
        are NOT NULL, so the insert would raise instead of recording an empty
        address. `panel_login_attempts` in particular is written on the
        unauthenticated login path, where the alternative to a row is a 500.
        """
        assert required("", EMAIL_LIMIT) == ""
        assert truncated("", EMAIL_LIMIT) is None

    def test_the_columns_it_is_used_for_really_are_not_null(self) -> None:
        """If either of these ever becomes nullable, `truncated` is the correct
        function again and this whole distinction can go."""
        assert PanelLoginAttempt.__table__.c.email.nullable is False
        assert PanelAuditEvent.__table__.c.actor_email.nullable is False
