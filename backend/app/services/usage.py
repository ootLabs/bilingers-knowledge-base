"""Pricing one model call and writing it to the cost ledger.

This is the writer half of cost control: `docs/llm/cost-control.md` describes
the limits that will read these numbers, and none of them can be tuned before
something records what real traffic actually costs.

Nothing calls this yet, because no model is called yet (see `AGENTS.md`:
no SDK, no API key, no model calls). The measurement columns therefore stay
NULL for the placeholder stream, which is the truthful record: no model ran and
nothing was spent. Retrieval and orchestration (T-30/T-40) supply the first
real `TokenUsage`, and the call site they need is `record_usage`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.chat import Query
from app.services.pricing import TOKENS_PER_PRICE_UNIT, PriceList, get_price_list

# `queries.cost_usd` and `queries.cost_pln` are NUMERIC(12,6), so quantize to
# the column's scale here rather than letting the driver decide. Rounding half
# up, not banker's rounding: an invoice-shaped figure rounds the way a person
# checking it by hand would.
COST_SCALE = Decimal("0.000001")


class InvalidUsage(Exception):
    """The reported usage cannot be true, or the ledger refused to store it.

    Covers both the checks made here (negative tokens, for instance) and the
    database rejecting the measurement itself: a cost with no model to attribute
    it to, or one without the rate behind it, violates a check constraint on
    `queries`. Those are the caller handing over a malformed measurement, and
    retrying the identical write would fail the same way, so they are kept apart
    from `UsageNotRecorded`, which a caller may reasonably retry.
    """


class UsageAlreadyRecorded(Exception):
    """This query already carries a measurement.

    The ledger is append-only (see the `Query` docstring in `app.models.chat`):
    filling the measurement in once is completing a row, overwriting it is
    editing evidence. Refused, so a retry loop cannot double-count or quietly
    replace a cost that was already reported.

    The refusal is enforced by the write itself, not by a read taken before it.
    A read-then-write would let two concurrent writers both see an unmeasured
    row and both proceed; see `record_usage`.
    """


class UsageNotRecorded(Exception):
    """The measurement could not be written: the database was unreachable, or
    the query row is gone. Infrastructure, not the caller's fault, and worth
    retrying. A measurement the database actively rejected raises
    `InvalidUsage` instead, because that one will fail again unchanged.
    """


@dataclass(frozen=True)
class TokenUsage:
    """What a single model call consumed, as reported by the provider."""

    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int | None = None


@dataclass(frozen=True)
class PricedUsage:
    """`TokenUsage` plus what it cost, and enough provenance to explain it later.

    `fx_rate_pln_per_usd` and `pricing_version` travel with the amounts on
    purpose: without them a PLN figure from three months ago cannot be
    reproduced, because both the provider's prices and the exchange rate move.
    """

    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int | None
    cost_usd: Decimal
    cost_pln: Decimal
    fx_rate_pln_per_usd: Decimal
    pricing_version: str


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(COST_SCALE, rounding=ROUND_HALF_UP)


def price_usage(usage: TokenUsage, price_list: PriceList | None = None) -> PricedUsage:
    """Turn a token count into a cost in USD and in PLN.

    Both amounts are derived from the same unrounded intermediate value, so the
    PLN figure is not a rounded USD figure rounded a second time. Passing
    `price_list` explicitly pins one list across a batch of calls; omitting it
    reads the configured file, which may have changed since the last call.
    """
    if usage.input_tokens < 0 or usage.output_tokens < 0:
        raise InvalidUsage("token counts cannot be negative")
    if usage.duration_ms is not None and usage.duration_ms < 0:
        raise InvalidUsage("duration cannot be negative")

    prices = price_list if price_list is not None else get_price_list()
    price = prices.price_for(usage.model)

    exact_usd = (
        usage.input_tokens * price.input_per_million
        + usage.output_tokens * price.output_per_million
    ) / TOKENS_PER_PRICE_UNIT

    return PricedUsage(
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        duration_ms=usage.duration_ms,
        cost_usd=_quantize(exact_usd),
        cost_pln=_quantize(exact_usd * prices.fx_rate_pln_per_usd),
        fx_rate_pln_per_usd=prices.fx_rate_pln_per_usd,
        pricing_version=prices.version,
    )


def _nothing_to_measure(session: Session, query_id: int) -> Exception:
    """Tell "someone else measured it first" apart from "the row is gone".

    Selects the id alone rather than loading the row: `queries.question` and
    `queries.answer` are marked `PERSONAL_DATA`, and an existence check has no
    business pulling a parent's question over the wire to then discard it.
    """
    present = session.execute(
        select(Query.id).where(Query.id == query_id)
    ).scalar_one_or_none()
    if present is None:
        return UsageNotRecorded(f"query {query_id} no longer exists")
    return UsageAlreadyRecorded(f"query {query_id} already carries a measurement")


def record_usage(
    query_id: int,
    priced: PricedUsage,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """Complete a ledger row with what answering it cost, in its own transaction.

    The row itself was written before the answer started streaming
    (`app.services.chat.record_query`), so this only fills in the measurement.

    **The session is this function's own, deliberately.** The usage of a
    streamed answer is only known once the stream has finished, and by then the
    request's `Depends(get_session)` session is long closed: its cleanup runs
    when the handler returns the `StreamingResponse`, not when ASGI finishes
    sending the body. So there is no caller-supplied session to join, and
    accepting one would be worse than pointless: this function commits and rolls
    back, and doing either to a session it does not own would discard whatever
    else the caller had pending. `session_factory` exists so tests can supply a
    double, not so production can hand over a live transaction.

    **One conditional `UPDATE`**, matching only a row whose cost is still NULL,
    rather than a read followed by a write. That is what makes "a reported cost
    is never replaced" true under concurrency: two writers racing on the same
    query would both pass a prior read, but the second `UPDATE` waits for the
    first to commit and then matches no row, so it raises rather than
    double-counting. Unmeasured means `cost_pln IS NULL` and nothing else, the
    same definition `query_costs_monthly` counts by: a row carrying a model with
    no cost yet is legal (`queries_cost_requires_model` only fires once a cost
    is present), so narrowing the match to `model IS NULL` as well would refuse
    such a row and report it as already measured when it is not.

    The database enforces that the measurement arrives whole:
    `queries_cost_requires_model` and
    `queries_cost_requires_pricing_provenance` reject a cost with no model
    behind it or no rate to explain it, which is what keeps "sum per model" and
    a reproducible PLN figure true at the storage layer rather than by
    convention. Either rejection is `InvalidUsage`, not a transient failure.

    Any failure rolls back, so the row is left exactly as it was and the same
    measurement can be written again once the cause is fixed.
    """
    values: dict[str, object] = {
        "model": priced.model,
        "input_tokens": priced.input_tokens,
        "output_tokens": priced.output_tokens,
        "cost_usd": priced.cost_usd,
        "cost_pln": priced.cost_pln,
        "fx_rate_pln_per_usd": priced.fx_rate_pln_per_usd,
        "pricing_version": priced.pricing_version,
    }
    if priced.duration_ms is not None:
        values["duration_ms"] = priced.duration_ms

    session = session_factory()
    try:
        result = session.execute(
            update(Query)
            .where(Query.id == query_id, Query.cost_pln.is_(None))
            .values(**values)
        )
        if result.rowcount != 1:
            session.rollback()
            raise _nothing_to_measure(session, query_id)
        session.commit()
    except (DataError, IntegrityError) as error:
        # The measurement itself is the problem, so say so: a check constraint
        # fired, or the driver refuses a value outright. Retrying it unchanged
        # would fail identically.
        session.rollback()
        raise InvalidUsage(f"the measurement for query {query_id} was rejected") from error
    except SQLAlchemyError as error:
        session.rollback()
        raise UsageNotRecorded(f"could not record usage for query {query_id}") from error
    finally:
        session.close()
