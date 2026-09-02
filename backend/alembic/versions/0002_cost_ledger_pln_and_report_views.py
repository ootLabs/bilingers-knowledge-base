"""Cost ledger in PLN, its provenance columns, and the reporting views

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The foundation is Polish and reports by calendar month, so a day and a month
# are bucketed in Warsaw local time, not UTC. In summer that is a two-hour
# offset: a question asked at 01:30 on the first belongs to the new month for
# the reader, and grouping in UTC would file it under the previous one.
REPORT_TIMEZONE = "Europe/Warsaw"

# Flat, one row per query, joined to its session so cost is attributable per
# user. Deliberately carries no personal data: no session token and no question
# text, only ids and numbers. That is what makes it safe to hand a monthly
# report to the foundation without an extraction step that strips things first.
QUERY_COSTS_VIEW = f"""
CREATE VIEW query_costs AS
SELECT
    q.id AS query_id,
    q.created_at,
    (q.created_at AT TIME ZONE '{REPORT_TIMEZONE}')::date AS report_day,
    date_trunc('month', q.created_at AT TIME ZONE '{REPORT_TIMEZONE}')::date AS report_month,
    q.chat_session_id,
    s.user_id,
    q.model,
    q.input_tokens,
    q.output_tokens,
    q.cost_usd,
    q.cost_pln,
    q.fx_rate_pln_per_usd,
    q.pricing_version,
    q.duration_ms
-- LEFT, though `queries.chat_session_id` is NOT NULL with a foreign key to
-- `chat_sessions.id`, so exactly one row matches and the result is identical to
-- an inner join. PostgreSQL has no inner-join removal, but it does remove a
-- left join to a unique key when nothing above it reads the nullable side, so
-- every rollup that does not group by account skips the join entirely instead
-- of hashing the whole session table for a column it never selects.
FROM queries q
LEFT JOIN chat_sessions s ON s.id = q.chat_session_id
"""

# The month total, which is the number D11 asks the foundation to approve.
# Deliberately unordered: an ORDER BY inside a view is not carried into the
# query that selects from it, so having one here would only look like a
# guarantee. Every consumer orders for itself.
# `query_count` and `priced_query_count` are both reported on purpose: the gap
# between them is the traffic that never reached a model (off topic, over quota,
# or today's placeholder), and a report that hid it would look like a month with
# suspiciously few questions rather than one with cheap rejections working.
QUERY_COSTS_MONTHLY_VIEW = """
CREATE VIEW query_costs_monthly AS
SELECT
    report_month,
    count(*) AS query_count,
    count(cost_pln) AS priced_query_count,
    coalesce(sum(input_tokens), 0) AS input_tokens,
    coalesce(sum(output_tokens), 0) AS output_tokens,
    coalesce(sum(cost_usd), 0)::numeric(14, 6) AS cost_usd,
    coalesce(sum(cost_pln), 0)::numeric(14, 6) AS cost_pln
FROM query_costs
GROUP BY report_month
"""


def upgrade() -> None:
    op.add_column("queries", sa.Column("cost_pln", sa.Numeric(precision=12, scale=6), nullable=True))
    op.add_column(
        "queries",
        sa.Column("fx_rate_pln_per_usd", sa.Numeric(precision=12, scale=6), nullable=True),
    )
    op.add_column("queries", sa.Column("pricing_version", sa.String(length=50), nullable=True))

    # Summing per model is an acceptance criterion, so an unattributable cost is
    # rejected by the database rather than left to a convention someone forgets.
    op.create_check_constraint(
        "queries_cost_requires_model",
        "queries",
        "cost_pln IS NULL OR (model IS NOT NULL "
        "AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL)",
    )
    # Revision 0001 shipped `cost_usd` as the only cost column, so a row left
    # over from an experiment can hold a cost with no PLN amount, rate or price
    # list beside it - a shape the constraint below forbids. Those figures are
    # cleared rather than grandfathered: a cost with no rate and no price list
    # version cannot be reproduced or reported, so by this project's own
    # standard it was never evidence, and inventing a retroactive exchange rate
    # to keep the number would manufacture some. Outside a developer's machine
    # this is a no-op, because nothing has ever written a measurement.
    #
    # The alternative, adding the constraint NOT VALID, would leave
    # `convalidated = false` forever: `pg_dump` would then disagree with what
    # `app.models.chat` declares, so a database built from the metadata and one
    # built from migrations would enforce subtly different rules, with nothing
    # able to tell them apart.
    op.execute(
        "UPDATE queries SET cost_usd = NULL "
        "WHERE cost_usd IS NOT NULL AND cost_pln IS NULL"
    )

    # Prices and the exchange rate both move, so a PLN figure without the rate
    # and the price list version behind it cannot be reproduced later.
    op.create_check_constraint(
        "queries_cost_requires_pricing_provenance",
        "queries",
        "(cost_pln IS NULL AND cost_usd IS NULL "
        "AND fx_rate_pln_per_usd IS NULL AND pricing_version IS NULL) "
        "OR (cost_pln IS NOT NULL AND cost_usd IS NOT NULL "
        "AND fx_rate_pln_per_usd IS NOT NULL AND pricing_version IS NOT NULL)",
    )

    # No cleanup needed ahead of this one: a negative token count or duration
    # is corrupt data rather than an old shape, and an upgrade is the right
    # place to find out about it.
    op.create_check_constraint(
        "queries_measurements_non_negative",
        "queries",
        "(input_tokens IS NULL OR input_tokens >= 0) "
        "AND (output_tokens IS NULL OR output_tokens >= 0) "
        "AND (cost_usd IS NULL OR cost_usd >= 0) "
        "AND (cost_pln IS NULL OR cost_pln >= 0) "
        "AND (fx_rate_pln_per_usd IS NULL OR fx_rate_pln_per_usd > 0) "
        "AND (duration_ms IS NULL OR duration_ms >= 0)",
    )

    op.execute(QUERY_COSTS_VIEW)
    op.execute(QUERY_COSTS_MONTHLY_VIEW)


def downgrade() -> None:
    # Monthly reads the flat view, so it goes first.
    op.execute("DROP VIEW IF EXISTS query_costs_monthly")
    op.execute("DROP VIEW IF EXISTS query_costs")

    op.drop_constraint("queries_measurements_non_negative", "queries", type_="check")
    op.drop_constraint("queries_cost_requires_pricing_provenance", "queries", type_="check")
    op.drop_constraint("queries_cost_requires_model", "queries", type_="check")

    op.drop_column("queries", "pricing_version")
    op.drop_column("queries", "fx_rate_pln_per_usd")
    op.drop_column("queries", "cost_pln")
