"""Pricing a model call and writing it to the ledger.

Two things are worth testing here and one is not obvious. The arithmetic,
because a wrong figure goes straight into a budget the foundation approves. And
the storage rules, because "summable per model" and "a PLN figure that can be
reproduced" are claims the report makes, so they are asserted against real
PostgreSQL constraints rather than trusted to the service that writes them.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.chat import ChatSession, Query
from app.services import usage as usage_module
from app.services.pricing import ModelPrice, PriceList, UnknownModelPrice
from app.services.usage import (
    InvalidUsage,
    PricedUsage,
    TokenUsage,
    UsageAlreadyRecorded,
    UsageNotRecorded,
    price_usage,
    record_usage,
)

PRICES = PriceList(
    version="test-2026-08",
    currency="USD",
    fx_rate_pln_per_usd=Decimal("4.000000"),
    models={
        "small": ModelPrice(
            input_per_million=Decimal("0.150000"),
            output_per_million=Decimal("0.600000"),
        ),
        # Priced so one input token costs 0.00000125 USD, half a unit of the
        # stored scale. Used to prove PLN is not derived from a rounded USD.
        "half-unit": ModelPrice(
            input_per_million=Decimal("1.250000"),
            output_per_million=Decimal("0"),
        ),
    },
)


class TestPriceUsage:
    def test_prices_input_and_output_separately(self) -> None:
        priced = price_usage(TokenUsage("small", 1000, 200, duration_ms=900), PRICES)

        # 1000 * 0.15/1e6 + 200 * 0.60/1e6 = 0.00015 + 0.00012
        assert priced.cost_usd == Decimal("0.000270")
        assert priced.cost_pln == Decimal("0.001080")
        assert priced.duration_ms == 900

    def test_carries_the_rate_and_the_price_list_version(self) -> None:
        """Without both, a figure reported months ago cannot be reproduced."""
        priced = price_usage(TokenUsage("small", 10, 10), PRICES)

        assert priced.fx_rate_pln_per_usd == Decimal("4.000000")
        assert priced.pricing_version == "test-2026-08"

    def test_pln_is_not_a_rounded_usd_figure_rounded_again(self) -> None:
        """One input token costs 0.00000125 USD here, half a unit of the scale.

        Converting the already-rounded 0.000001 USD would give 0.000004 PLN.
        Converting the unrounded amount gives 0.000005, which is the honest one.
        """
        priced = price_usage(TokenUsage("half-unit", 1, 0), PRICES)

        assert priced.cost_usd == Decimal("0.000001")
        assert priced.cost_pln == Decimal("0.000005")

    def test_a_call_that_used_nothing_costs_nothing(self) -> None:
        priced = price_usage(TokenUsage("small", 0, 0), PRICES)

        assert priced.cost_usd == Decimal("0")
        assert priced.cost_pln == Decimal("0")

    @pytest.mark.parametrize(
        "usage",
        [
            pytest.param(TokenUsage("small", -1, 0), id="negative input"),
            pytest.param(TokenUsage("small", 0, -1), id="negative output"),
            pytest.param(TokenUsage("small", 1, 1, duration_ms=-5), id="negative duration"),
        ],
    )
    def test_refuses_usage_that_cannot_be_true(self, usage: TokenUsage) -> None:
        with pytest.raises(InvalidUsage):
            price_usage(usage, PRICES)

    def test_an_unpriced_model_is_not_costed_at_zero(self) -> None:
        with pytest.raises(UnknownModelPrice):
            price_usage(TokenUsage("a-model-nobody-priced", 10, 10), PRICES)

    def test_reads_the_configured_price_list_when_none_is_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The normal path: the file may have been edited since the last call."""
        monkeypatch.setattr(usage_module, "get_price_list", lambda: PRICES)

        assert price_usage(TokenUsage("small", 1000, 200)).cost_pln == Decimal("0.001080")


class LedgerSession:
    """The slice of `Session` that `record_usage` touches, with a scripted outcome.

    Handed over through `session_factory`, which is the only reason that
    parameter exists: production never supplies a session, because the writer
    owns its transaction.

    One configurable double rather than a class per failure point. Deliberately
    not `conftest.StubSession`, which stands in for a liveness probe and has no
    `commit`, `rollback`, or row count. `FailingSession` in `test_chat.py` is a
    third double for a third `Session` surface; folding all three into one
    parametrised fake is worth doing, and is its own refactor.
    """

    def __init__(
        self,
        rowcount: int = 1,
        on_execute: Exception | None = None,
        on_commit: Exception | None = None,
        row: object | None = None,
    ) -> None:
        self._rowcount = rowcount
        self._on_execute = on_execute
        self._on_commit = on_commit
        self._row = row
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, _statement: object) -> SimpleNamespace:
        """Serves both statements `record_usage` issues: the conditional UPDATE
        reads `rowcount`, and the existence check reads `scalar_one_or_none`."""
        if self._on_execute is not None:
            raise self._on_execute
        return SimpleNamespace(
            rowcount=self._rowcount, scalar_one_or_none=lambda: self._row
        )

    def commit(self) -> None:
        if self._on_commit is not None:
            raise self._on_commit
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class TestRecordUsageWithoutADatabase:
    def test_a_failed_commit_rolls_back_so_the_same_write_can_be_retried(
        self, priced_usage: Callable[..., PricedUsage]
    ) -> None:
        """Leaving the fields set behind a failed commit would make the retry
        look like an overwrite of a cost that was never actually stored."""
        session = LedgerSession(on_commit=SQLAlchemyError("connection gone"))

        with pytest.raises(UsageNotRecorded):
            record_usage(1, priced_usage(), session_factory=lambda: session)  # type: ignore[arg-type]

        assert session.rolled_back is True

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(IntegrityError("stmt", {}, Exception("check violation")), id="constraint"),
            pytest.param(DataError("stmt", {}, Exception("value out of range")), id="bad value"),
        ],
    )
    def test_a_rejected_measurement_is_not_reported_as_transient(
        self, error: Exception, priced_usage: Callable[..., PricedUsage]
    ) -> None:
        """`UsageNotRecorded` invites a retry, and a measurement the database
        refuses will be refused identically next time. That is `InvalidUsage`."""
        session = LedgerSession(on_execute=error)

        with pytest.raises(InvalidUsage):
            record_usage(1, priced_usage(), session_factory=lambda: session)  # type: ignore[arg-type]

        assert session.rolled_back is True

    def test_a_generic_driver_failure_stays_transient(
        self, priced_usage: Callable[..., PricedUsage]
    ) -> None:
        session = LedgerSession(on_execute=SQLAlchemyError("connection reset"))

        with pytest.raises(UsageNotRecorded):
            record_usage(1, priced_usage(), session_factory=lambda: session)  # type: ignore[arg-type]

    def test_matching_no_row_with_the_row_present_means_already_measured(
        self, priced_usage: Callable[..., PricedUsage]
    ) -> None:
        """An edited ledger is not evidence, and a retry must not double-count."""
        session = LedgerSession(rowcount=0, row=1)

        with pytest.raises(UsageAlreadyRecorded):
            record_usage(1, priced_usage(), session_factory=lambda: session)  # type: ignore[arg-type]

        assert session.committed is False

    def test_matching_no_row_with_the_row_gone_means_it_vanished(
        self, priced_usage: Callable[..., PricedUsage]
    ) -> None:
        session = LedgerSession(rowcount=0, row=None)

        with pytest.raises(UsageNotRecorded):
            record_usage(1, priced_usage(), session_factory=lambda: session)  # type: ignore[arg-type]


@pytest.mark.integration
class TestLedgerAgainstRealDatabase:
    def test_the_measurement_is_persisted(
        self,
        migrated_database: None,
        committed_query: Callable[[], int],
        priced_usage: Callable[..., PricedUsage],
    ) -> None:
        query_id = committed_query()

        record_usage(query_id, priced_usage())

        with SessionLocal() as session:
            saved = session.get(Query, query_id)
            assert saved is not None
            assert saved.model == "small"
            assert saved.input_tokens == 1000
            assert saved.output_tokens == 200
            assert saved.cost_usd == Decimal("0.000270")
            assert saved.cost_pln == Decimal("0.001080")
            assert saved.fx_rate_pln_per_usd == Decimal("4.000000")
            assert saved.pricing_version == "test-2026-08"
            assert saved.duration_ms == 900

    def test_a_second_write_is_refused(
        self,
        migrated_database: None,
        committed_query: Callable[[], int],
        priced_usage: Callable[..., PricedUsage],
    ) -> None:
        """The refusal has to come from the write, not from a read before it.

        The second call opens a session of its own and never looks at the row,
        exactly like the loser of a real race whose lookup happened before the
        winner committed. Only the conditional UPDATE can reject it, so this
        fails if the guard is ever turned back into a read-then-write.
        """
        query_id = committed_query()
        record_usage(query_id, priced_usage())

        with pytest.raises(UsageAlreadyRecorded):
            record_usage(query_id, priced_usage(cost_pln=Decimal("9.000000")))

        with SessionLocal() as verify:
            saved = verify.get(Query, query_id)
            assert saved is not None
            assert saved.cost_pln == Decimal("0.001080")

    def test_a_model_recorded_without_a_cost_can_still_be_measured(
        self,
        migrated_database: None,
        committed_token: Callable[[], str],
        priced_usage: Callable[..., PricedUsage],
    ) -> None:
        """Unmeasured means no cost, not "no model".

        `queries_cost_requires_model` only fires once a cost is present, so a
        row naming the model it chose before pricing succeeded is legal. Matching
        on `model IS NULL` as well would refuse that row and report it as already
        measured, throwing away a cost that was really spent.

        Committed for real, not through `db_session`: the writer opens its own
        connection, which cannot see another transaction's uncommitted rows.
        """
        with SessionLocal() as setup:
            chat_session = ChatSession(token=committed_token())
            setup.add(chat_session)
            setup.flush()
            query = Query(chat_session_id=chat_session.id, question="Pytanie", model="small")
            setup.add(query)
            setup.commit()
            query_id = query.id

        record_usage(query_id, priced_usage())

        with SessionLocal() as verify:
            saved = verify.get(Query, query_id)
            assert saved is not None
            assert saved.cost_pln == Decimal("0.001080")

    def test_a_rejected_measurement_leaves_the_row_writable(
        self,
        migrated_database: None,
        committed_query: Callable[[], int],
        priced_usage: Callable[..., PricedUsage],
    ) -> None:
        """A measurement the database refuses must not consume the row.

        `queries_cost_requires_model` fires here, because a cost with no model
        cannot be attributed. If the failed attempt left the fields set, the
        correct measurement that follows would be rejected as an overwrite of a
        cost that was never stored in the first place.
        """
        query_id = committed_query()

        with pytest.raises(InvalidUsage):
            record_usage(query_id, priced_usage(model=None))

        with SessionLocal() as verify:
            saved = verify.get(Query, query_id)
            assert saved is not None
            assert saved.cost_pln is None

        record_usage(query_id, priced_usage())

        with SessionLocal() as verify:
            saved = verify.get(Query, query_id)
            assert saved is not None
            assert saved.cost_pln == Decimal("0.001080")

    def test_a_vanished_query_is_reported_not_silently_dropped(
        self, migrated_database: None, priced_usage: Callable[..., PricedUsage]
    ) -> None:
        """The stream may outlive the row; the cost still has to be accounted for."""
        with pytest.raises(UsageNotRecorded):
            record_usage(-1, priced_usage())

    def test_a_cost_with_no_model_is_rejected(
        self, migrated_database: None, db_session: Session, committed_token: Callable[[], str]
    ) -> None:
        """Otherwise the row falls out of every per-model sum, unnoticed."""
        chat_session = ChatSession(token=committed_token())
        db_session.add(chat_session)
        db_session.flush()

        db_session.add(
            Query(
                chat_session_id=chat_session.id,
                question="Pytanie",
                cost_usd=Decimal("0.000270"),
                cost_pln=Decimal("0.001080"),
                fx_rate_pln_per_usd=Decimal("4.000000"),
                pricing_version="test-2026-08",
            )
        )
        with pytest.raises(IntegrityError, match="queries_cost_requires_model"):
            db_session.flush()

    def test_a_cost_with_no_rate_behind_it_is_rejected(
        self, migrated_database: None, db_session: Session, committed_token: Callable[[], str]
    ) -> None:
        """A PLN figure with no rate cannot be reproduced once the rate moves."""
        chat_session = ChatSession(token=committed_token())
        db_session.add(chat_session)
        db_session.flush()

        db_session.add(
            Query(
                chat_session_id=chat_session.id,
                question="Pytanie",
                model="small",
                input_tokens=10,
                output_tokens=10,
                cost_pln=Decimal("0.001080"),
            )
        )
        with pytest.raises(IntegrityError, match="queries_cost_requires_pricing_provenance"):
            db_session.flush()

    def test_negative_measurements_are_rejected(
        self, migrated_database: None, db_session: Session, committed_token: Callable[[], str]
    ) -> None:
        """A negative figure in a budget report hides another one by cancelling it."""
        chat_session = ChatSession(token=committed_token())
        db_session.add(chat_session)
        db_session.flush()

        db_session.add(Query(chat_session_id=chat_session.id, question="Pytanie", input_tokens=-1))
        with pytest.raises(IntegrityError, match="queries_measurements_non_negative"):
            db_session.flush()

    def test_an_unmeasured_question_is_still_a_valid_row(
        self, migrated_database: None, db_session: Session, committed_token: Callable[[], str]
    ) -> None:
        """Off topic, over quota, or today's placeholder: no model ran, and the
        row has to survive anyway or the counts describe less than the traffic."""
        chat_session = ChatSession(token=committed_token())
        db_session.add(chat_session)
        db_session.flush()

        query = Query(chat_session_id=chat_session.id, question="Pytanie")
        db_session.add(query)
        db_session.flush()

        assert query.id is not None
        assert query.cost_pln is None
