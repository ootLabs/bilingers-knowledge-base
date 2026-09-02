"""The reporting views: the surface a monthly cost figure is read from.

Kept apart from `test_usage.py` because these guard a different promise. That
file is about writing a correct number; this one is about a report the foundation
can be handed without anyone stripping personal data out of it first, and about
the counts staying honest when a question never reached a model.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.models.chat import ChatSession, Query
from app.services.usage import PricedUsage, record_usage


@pytest.mark.integration
class TestReportingViews:
    def test_the_view_carries_no_personal_data(self, migrated_database: None) -> None:
        """A monthly report goes to the foundation, so the view it is built from
        must not contain the question text or the session token."""
        with SessionLocal() as session:
            columns = {
                row[0]
                for row in session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'query_costs'"
                    )
                )
            }

        assert columns, "the query_costs view is missing; run alembic upgrade head"
        assert "question" not in columns
        assert "answer" not in columns
        assert "token" not in columns
        assert {"report_day", "report_month", "model", "cost_pln", "user_id"} <= columns

    def test_a_priced_query_shows_up_in_the_monthly_total(
        self,
        migrated_database: None,
        committed_query: Callable[[], int],
        priced_usage: Callable[..., PricedUsage],
    ) -> None:
        query_id = committed_query()
        record_usage(query_id, priced_usage())

        with SessionLocal() as session:
            row = session.execute(
                text(
                    "SELECT report_month, model, cost_pln FROM query_costs "
                    "WHERE query_id = :query_id"
                ),
                {"query_id": query_id},
            ).one()
            assert row.model == "small"
            assert row.cost_pln == Decimal("0.001080")

            totals = session.execute(
                text(
                    "SELECT query_count, priced_query_count, cost_pln "
                    "FROM query_costs_monthly WHERE report_month = :month"
                ),
                {"month": row.report_month},
            ).one()

        # Greater or equal, not equal: a developer's database holds other rows,
        # and a test that assumed an empty ledger would fail on the second run.
        assert totals.query_count >= 1
        assert totals.priced_query_count >= 1
        assert totals.cost_pln >= Decimal("0.001080")

    def test_an_unpriced_query_is_counted_but_not_costed(
        self, migrated_database: None, committed_query: Callable[[], int]
    ) -> None:
        """The gap between the two counts is the traffic that never reached a
        model. A report that hid it would look like a month with no questions."""
        query_id = committed_query()

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT model, cost_pln FROM query_costs WHERE query_id = :query_id"),
                {"query_id": query_id},
            ).one()

        assert row.model is None
        assert row.cost_pln is None

    def test_the_migration_creates_exactly_the_expected_views(
        self, migrated_database: None
    ) -> None:
        """These exist only as SQL inside a migration: `Base.metadata` does not
        know them, `alembic check` cannot see them, and
        `test_every_table_exists_after_migrating` checks tables. So this is the
        only thing that would notice one being dropped or renamed."""
        with SessionLocal() as session:
            views = set(
                session.execute(
                    text(
                        "SELECT table_name FROM information_schema.views "
                        "WHERE table_schema = 'public'"
                    )
                ).scalars()
            )

        assert views == {"query_costs", "query_costs_monthly"}

    def test_a_day_and_a_month_are_bucketed_in_warsaw_time(
        self, migrated_database: None, committed_token: Callable[[], str]
    ) -> None:
        """The foundation reads a calendar month in its own timezone. A question
        asked at 01:30 on the first of the month belongs to the new month for
        them; grouping in UTC would file it under the previous one.

        Reads `report_day` and `report_month` out of the view, rather than
        re-evaluating `AT TIME ZONE` against a literal: a test that recomputes
        the expression it is meant to be checking passes just as happily when
        the view is built in UTC.
        """
        # 23:30+00 on the last day of August is 01:30 on 1 September in Warsaw,
        # and 21:59:59+00 on 31 July is still July there, one second short of
        # the boundary.
        instants = {
            "2026-08-31 23:30:00+00": ("2026-09-01", "2026-09-01"),
            "2026-07-31 21:59:59+00": ("2026-07-31", "2026-07-01"),
        }

        with SessionLocal() as setup:
            chat_session = ChatSession(token=committed_token())
            setup.add(chat_session)
            setup.flush()
            ids = {}
            for instant in instants:
                query = Query(
                    chat_session_id=chat_session.id,
                    question="Pytanie na granicy miesiaca",
                    created_at=datetime.fromisoformat(instant),
                )
                setup.add(query)
                setup.flush()
                ids[instant] = query.id
            setup.commit()

        with SessionLocal() as session:
            for instant, (expected_day, expected_month) in instants.items():
                row = session.execute(
                    text(
                        "SELECT report_day, report_month FROM query_costs "
                        "WHERE query_id = :query_id"
                    ),
                    {"query_id": ids[instant]},
                ).one()

                assert row.report_day.isoformat() == expected_day, instant
                assert row.report_month.isoformat() == expected_month, instant
