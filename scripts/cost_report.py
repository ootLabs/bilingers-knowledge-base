#!/usr/bin/env python3
"""What the assistant has cost so far, summed the four ways the card asks for.

This is the reporting half of the cost ledger. The numbers it prints are the
ones that correct the calculation the foundation approves (T-02.2, D11): a
price list multiplied by a guess is a guess, and this reads real rows instead.

Usage:
    python scripts/cost_report.py                    # every month, plus the latest in detail
    python scripts/cost_report.py --month 2026-08    # detail for one month
    python scripts/cost_report.py --csv              # one row per query, for the spreadsheet

Environment:
    POSTGRES_USER  default bilingers
    POSTGRES_DB    default bilingers
    DB_SERVICE     compose service holding PostgreSQL, default db

Reads through `docker compose exec db psql`, so it needs the stack running and
nothing installed on the host. Standard library only.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime

POSTGRES_USER = os.environ.get("POSTGRES_USER", "bilingers")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "bilingers")
DB_SERVICE = os.environ.get("DB_SERVICE", "db")

# Must match the zone the views bucket in (see the cost ledger revision): a filter and
# a grouping that disagree would report a month the report itself cannot show.
REPORT_TIMEZONE = "Europe/Warsaw"

# Ordered here, not in the view: PostgreSQL does not carry a view's ORDER BY
# into the query that selects from it, so months could print out of sequence
# and read as a data problem.
MONTHLY = "SELECT * FROM query_costs_monthly ORDER BY report_month"

# `count(*)` next to `count(cost_pln)` in every section, because the difference
# is the traffic that never reached a model. Hiding it would make a month of
# working cheap rejections look like a month with barely any questions.
PER_MODEL = """
SELECT
    coalesce(model, '(no model call)') AS model,
    count(*) AS queries,
    count(cost_pln) AS priced,
    coalesce(sum(input_tokens), 0) AS input_tokens,
    coalesce(sum(output_tokens), 0) AS output_tokens,
    coalesce(sum(cost_pln), 0) AS cost_pln
FROM query_costs
{where}
GROUP BY 1
ORDER BY cost_pln DESC, model
"""

PER_DAY = """
SELECT
    report_day,
    count(*) AS queries,
    count(cost_pln) AS priced,
    coalesce(sum(cost_pln), 0) AS cost_pln
FROM query_costs
{where}
GROUP BY 1
ORDER BY 1
"""

# Grouped by account, with anonymous traffic kept as one bucket rather than
# dropped: the quota in D5 counts anonymous parents, so the cost report has to
# show them too, or the two numbers describe different populations.
# Capped, because a per-account listing grows with the userbase and this is a
# terminal report. The heading says how many accounts exist, so a truncated
# listing never reads as the whole picture.
PER_USER_LIMIT = 50

PER_USER = """
SELECT
    coalesce(user_id::text, '(anonymous)') AS account,
    count(DISTINCT chat_session_id) AS sessions,
    count(*) AS queries,
    coalesce(sum(cost_pln), 0) AS cost_pln
FROM query_costs
{where}
GROUP BY 1
ORDER BY cost_pln DESC, account
LIMIT {limit}
"""

ACCOUNT_COUNT = """
SELECT count(*) FROM (
    SELECT DISTINCT coalesce(user_id::text, '(anonymous)') FROM query_costs {where}
) AS accounts
"""

# No question text and no session token: `query_costs` carries none, so this
# export can go into a spreadsheet the foundation sees without a scrubbing step.
PER_QUERY_CSV = "SELECT * FROM query_costs {where} ORDER BY created_at, query_id"


def psql(sql: str, csv: bool = False) -> str:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        DB_SERVICE,
        "psql",
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DB,
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
    ]
    if csv:
        command.append("--csv")
    command += ["-c", sql]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        sys.exit(
            f"psql failed. Is the stack up and migrated?\n"
            f"  docker compose up -d\n"
            f"  docker compose exec backend alembic upgrade head\n\n{detail}"
        )
    return result.stdout


def month_filter(month: str | None) -> str:
    """A validated WHERE clause. Validated, because psql -c takes no parameters.

    A half-open range over `created_at` rather than `report_month = DATE '...'`,
    even though the second reads better. `report_month` is computed by the view,
    so a predicate on it can only ever be a filter applied to every row of
    `queries`, an append-only table that grows by one row per question forever.
    The range form is an index condition on `ix_queries_created_at`, which
    revision 0001 already created, so this costs no new index.

    The bounds are `TIMESTAMP` literals, not `DATE` ones, and that is not
    cosmetic. `DATE 'x' AT TIME ZONE zone` resolves to the timestamptz overload,
    which reads the date in the *session* zone and converts it to a naive local
    timestamp: with the session in UTC that is 02:00 Warsaw, four hours past the
    boundary the view buckets on. `TIMESTAMP 'x' AT TIME ZONE zone` takes the
    other overload, reading the literal as Warsaw wall clock and yielding the
    instant the month actually starts.
    """
    if month is None:
        return ""
    try:
        first_day = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        sys.exit(f"--month wants YYYY-MM, got {month!r}")
    start = f"TIMESTAMP '{first_day.isoformat()}'"
    return (
        f"WHERE created_at >= ({start} AT TIME ZONE '{REPORT_TIMEZONE}') "
        f"AND created_at < (({start} + INTERVAL '1 month') AT TIME ZONE '{REPORT_TIMEZONE}')"
    )


def scalar(sql: str) -> str | None:
    """One value from a one-row, one-column query, or None when there is none.

    The first line back is the column header. An empty result gives nothing
    after it, which is how an untouched ledger reports itself.
    """
    lines = [line.strip() for line in psql(sql, csv=True).splitlines()[1:] if line.strip()]
    return lines[0] if lines else None


def latest_month() -> str | None:
    """The most recent month with any traffic, as YYYY-MM.

    PostgreSQL formats it, rather than this script slicing the first seven
    characters off whatever psql printed: the text form of a date follows the
    server's DateStyle setting, so parsing it here would be right by luck and
    wrong on a server configured for, say, DMY.
    """
    return scalar("SELECT to_char(max(report_month), 'YYYY-MM') FROM query_costs")


def account_count(where: str) -> int:
    return int(scalar(ACCOUNT_COUNT.format(where=where)) or 0)


def section(title: str, sql: str) -> None:
    print(title)
    print("=" * len(title))
    print(psql(sql).rstrip())
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", help="restrict the detail sections to one YYYY-MM")
    parser.add_argument(
        "--csv",
        action="store_true",
        help="print one row per query as CSV instead of the summary sections",
    )
    args = parser.parse_args()

    # Before any output. A bad --month used to be reported after the monthly
    # table had already printed, leaving the operator unsure whether the numbers
    # above it were the ones they asked for.
    requested = month_filter(args.month)

    if args.csv:
        # Straight to stdout, so it pipes into a file without the headings.
        sys.stdout.write(psql(PER_QUERY_CSV.format(where=requested), csv=True))
        return 0

    section("Cost per month, all traffic", MONTHLY)

    month = args.month or latest_month()
    if month is None:
        print("No queries recorded yet, so there is nothing to break down.")
        print("The ledger fills up once a model is actually called (T-30/T-40).")
        return 0

    where = month_filter(month)
    section(f"Cost per model, {month}", PER_MODEL.format(where=where))
    section(f"Cost per day, {month}", PER_DAY.format(where=where))

    accounts = account_count(where)
    shown = (
        f"top {PER_USER_LIMIT} of {accounts} by cost"
        if accounts > PER_USER_LIMIT
        else f"{accounts} in total"
    )
    section(
        f"Cost per account, {month} ({shown})",
        PER_USER.format(where=where, limit=PER_USER_LIMIT),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
