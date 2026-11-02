# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: INP001 - standalone utilities inside a skill payload, not a
# package. The skill directory is copied verbatim into an editor's plugin
# cache, where an __init__.py would claim a package that nothing imports.

"""Fold a run's results file into per-period and per-policy book totals.

The artifact carries one policy. The book is in the Parquet the run wrote --
one row per policy, a list column per per-period result, a plain column per
per-policy result. This folds it: every numeric list column summed (or
averaged) across policies at each projection period, and every numeric plain
column summed across policies.

Timelines may be jagged. A per-policy period index is built from each column's
own list length, so a policy whose projection is shorter contributes to the
periods it has and to no others.

**A total is not automatically a meaning.** Summing a cashflow is arithmetic
the book supports; summing a rate, an attained age or a flag produces a number
with no actuarial reading at all. This writes what it folded and what it
skipped; saying which of the folded columns are worth quoting is the caller's
job, not a guess made here.

**The CSV is safe to open in a spreadsheet.** A text cell or a header that
begins with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return -- a
formula, to Excel and its kin -- is written with a leading ``'``, the standard
neutralisation, so a column named ``=HYPERLINK(...)`` in a book someone else
exported is shown as text rather than run. Numbers are written as they are,
negative ones included; the table and JSON forms are unchanged.

Run it::

    bindings/python/.venv/bin/python portfolio_totals.py results.parquet
    bindings/python/.venv/bin/python portfolio_totals.py results.parquet \
        --aggregate mean --columns net_cf
    bindings/python/.venv/bin/python portfolio_totals.py results.parquet \
        --format json --output totals.json

Import it::

    from portfolio_totals import fold, per_period, scalar_totals
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Sequence

PERIOD_COLUMN = "period"
"""The projection-period label the folded frame is indexed by."""

NUMERIC = (
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
    pl.Float64,
)
"""The dtypes a sum or a mean is defined over. Dates, strings and booleans
are not folded: a summed date is not a date, and a summed flag is a count
wearing the flag's name."""

AGGREGATES = ("sum", "mean")
"""The two folds. ``sum`` is the book's total at each period; ``mean`` is the
average over the policies that reach that period."""


FORMULA_LEAD = r"^[=+\-@\t\r]"
"""The leading characters a spreadsheet reads as the start of a formula."""


def spreadsheet_safe(frame: pl.DataFrame) -> pl.DataFrame:
    """Return ``frame`` with each cell and header a spreadsheet would run made inert.

    A cell or a header that begins with ``=``, ``+``, ``-``, ``@``, a tab or
    a carriage return is a formula to Excel and its kin: a column named
    ``=HYPERLINK("https://...")`` in a book someone else exported becomes a
    live link the moment the CSV opens. Each such text value, and each such
    header, gets a leading ``'`` -- the standard neutralisation, which a
    spreadsheet shows as text and drops from the cell. Numbers are never
    touched: ``-0.25`` in a numeric column is a number, and stays one.

    Args:
        frame: What the CSV is written from.

    Returns:
        The same frame, its text columns and headers neutralised.

    """
    text = [name for name, dtype in frame.schema.items() if dtype == pl.String]
    safe = frame.with_columns(
        pl.when(pl.col(name).str.contains(FORMULA_LEAD))
        .then(pl.concat_str([pl.lit("'"), pl.col(name)]))
        .otherwise(pl.col(name))
        .alias(name)
        for name in text
    )
    lead = re.compile(FORMULA_LEAD)
    return safe.rename({name: f"'{name}" for name in safe.columns if lead.match(name)})


@dataclass(frozen=True, slots=True)
class Fold:
    """What one pass over a results file produced.

    Attributes:
        per_period: One row per projection period, one column per folded list
            column, ``period`` first.
        scalars: One row, one column per folded plain column, each summed
            across policies.
        policy_count: The number of rows the results file holds.
        skipped: The columns no fold is defined over, by name.

    """

    per_period: pl.DataFrame
    scalars: pl.DataFrame
    policy_count: int
    skipped: tuple[str, ...]


def read_results(path: Path) -> pl.DataFrame:
    """Return the results file at ``path``.

    Args:
        path: The Parquet ``gspio calc-graph --output-file`` or
            ``gspio run-model --output-file`` wrote.

    Returns:
        The frame, one row per policy.

    """
    return pl.read_parquet(path)


def _is_numeric(dtype: pl.DataType) -> bool:
    """Say whether a fold is defined over this dtype."""
    return isinstance(dtype, NUMERIC)


def list_columns(frame: pl.DataFrame) -> list[str]:
    """Return the per-period columns a fold is defined over.

    Args:
        frame: A results frame.

    Returns:
        The names of the list columns whose inner dtype is numeric.

    """
    return [
        name
        for name, dtype in frame.schema.items()
        if isinstance(dtype, pl.List) and _is_numeric(dtype.inner)
    ]


def scalar_columns(frame: pl.DataFrame) -> list[str]:
    """Return the per-policy columns a fold is defined over.

    Args:
        frame: A results frame.

    Returns:
        The names of the plain columns whose dtype is numeric.

    """
    return [
        name
        for name, dtype in frame.schema.items()
        if not isinstance(dtype, pl.List) and _is_numeric(dtype)
    ]


def per_period(
    frame: pl.DataFrame,
    columns: Sequence[str],
    *,
    aggregate: str = "sum",
) -> pl.DataFrame:
    """Return each column folded across policies at each projection period.

    Each column is exploded against a period index built from its own list
    length, so a shorter timeline contributes to the periods it has and to no
    others, and grouped on that index. The columns are folded in parallel and
    joined on the period, which keeps a column whose timeline runs longer than
    its neighbours' rather than truncating the frame to the shortest.

    Args:
        frame: A results frame, one row per policy.
        columns: The list columns to fold.
        aggregate: ``sum`` or ``mean``.

    Returns:
        One row per period, ``period`` first, sorted ascending.

    Raises:
        ValueError: If ``aggregate`` is neither fold.

    """
    if aggregate not in AGGREGATES:
        message = f"aggregate must be one of {AGGREGATES}, not {aggregate!r}"
        raise ValueError(message)
    if not columns:
        return pl.DataFrame({PERIOD_COLUMN: []}, schema={PERIOD_COLUMN: pl.Int64})
    plans = [
        frame.lazy()
        .select(
            pl.int_ranges(pl.col(name).list.len()).alias(PERIOD_COLUMN),
            pl.col(name),
        )
        .explode([PERIOD_COLUMN, name], empty_as_null=False)
        .group_by(PERIOD_COLUMN)
        .agg(
            pl.col(name).sum() if aggregate == "sum" else pl.col(name).mean(),
        )
        for name in columns
    ]
    folded = pl.collect_all(plans)
    total = folded[0]
    for other in folded[1:]:
        total = total.join(other, on=PERIOD_COLUMN, how="full", coalesce=True)
    return total.sort(PERIOD_COLUMN)


def scalar_totals(frame: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
    """Return each per-policy column summed across the book.

    The plain columns are summed whichever per-period fold was asked for: a
    per-policy result has no period to average over, and a book total is the
    figure a reconciliation quotes.

    Args:
        frame: A results frame, one row per policy.
        columns: The plain columns to sum.

    Returns:
        A single row, one column per name given.

    """
    if not columns:
        return pl.DataFrame()
    return frame.select(pl.col(name).sum().alias(name) for name in columns)


def fold(
    frame: pl.DataFrame,
    *,
    aggregate: str = "sum",
    columns: Sequence[str] | None = None,
) -> Fold:
    """Return the whole book folded, and the columns left out of it.

    Args:
        frame: A results frame, one row per policy.
        aggregate: ``sum`` or ``mean``, for the per-period fold.
        columns: Fold only these columns, or every numeric column where None.

    Returns:
        The per-period frame, the per-policy sums, the policy count and the
        names of the columns no fold is defined over.

    Raises:
        ValueError: If ``columns`` names a column the frame does not hold.

    """
    if columns is not None:
        missing = [name for name in columns if name not in frame.columns]
        if missing:
            message = (
                f"the results file holds no column named {', '.join(missing)}; "
                f"`gspio describe` lists the ones it does hold"
            )
            raise ValueError(message)
    wanted = set(columns) if columns is not None else None
    lists = [n for n in list_columns(frame) if wanted is None or n in wanted]
    scalars = [n for n in scalar_columns(frame) if wanted is None or n in wanted]
    named = set(lists) | set(scalars)
    skipped = tuple(
        name
        for name in frame.columns
        if name not in named and (wanted is None or name in wanted)
    )
    if skipped:
        logger.info(
            "{count} column(s) carry no fold and are left out: {names}",
            count=len(skipped),
            names=", ".join(skipped),
        )
    return Fold(
        per_period=per_period(frame, lists, aggregate=aggregate),
        scalars=scalar_totals(frame, scalars),
        policy_count=frame.height,
        skipped=skipped,
    )


def render(folded: Fold, form: str, aggregate: str) -> str:
    """Return the fold written in the form asked for.

    Args:
        folded: What the pass produced.
        form: ``table``, ``csv`` (the per-period frame alone) or ``json``.
        aggregate: The fold that was taken, so the output says so.

    Returns:
        The rendered text, newline-terminated.

    """
    if form == "csv":
        return spreadsheet_safe(folded.per_period).write_csv()
    if form == "json":
        return (
            json.dumps(
                {
                    "aggregate": aggregate,
                    "policy_count": folded.policy_count,
                    "per_period": folded.per_period.to_dicts(),
                    "scalar_sums": folded.scalars.to_dicts(),
                    "skipped": list(folded.skipped),
                },
                indent=2,
                default=str,
            )
            + "\n"
        )
    with pl.Config(tbl_rows=-1, tbl_cols=-1):
        return (
            f"per period ({aggregate} over {folded.policy_count} policies)\n"
            f"{folded.per_period}\n\n"
            f"per policy (sum over {folded.policy_count} policies)\n"
            f"{folded.scalars}\n"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Fold a results file and write the totals.

    Args:
        argv: Command-line arguments, the program name excluded.

    Returns:
        The process exit status: 0 on a fold, 1 where a named column is not
        in the file.

    """
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description=(
            "Fold a run's results Parquet into per-period book totals and "
            "per-policy sums. Numeric columns only; a total is arithmetic, "
            "not automatically a meaning."
        ),
    )
    parser.add_argument("results", type=Path, help="the results Parquet to fold")
    parser.add_argument(
        "--aggregate",
        choices=AGGREGATES,
        default="sum",
        help="the per-period fold (default: sum); per-policy columns are summed",
    )
    parser.add_argument(
        "--columns",
        nargs="+",
        default=None,
        help="fold only these columns (default: every numeric column)",
    )
    parser.add_argument(
        "--format",
        dest="form",
        choices=("table", "csv", "json"),
        default="table",
        help="how to write it (default: table; csv writes the per-period frame)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write to this file instead of standard output",
    )
    args = parser.parse_args(argv)

    frame = read_results(args.results)
    try:
        folded = fold(frame, aggregate=args.aggregate, columns=args.columns)
    except ValueError as refusal:
        logger.error(str(refusal))
        return 1
    text = render(folded, args.form, args.aggregate)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
        logger.info(
            "wrote {periods} periods over {policies} policies to {path}",
            periods=folded.per_period.height,
            policies=folded.policy_count,
            path=args.output,
        )
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
