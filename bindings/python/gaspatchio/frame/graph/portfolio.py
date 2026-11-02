# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Portfolio fold data and its representation on the artifact's policy axis.

Scenario execution supplies the completed totals; this module only formats those
values and their declared cuts. It never executes a model or chooses a batch size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from gaspatchio.frame.graph.value_extractor import one_value_on_the_wire

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import polars as pl


__all__ = [
    "DECLARED_BESIDE_MAIN",
    "PortfolioFold",
    "PortfolioFoldError",
    "axis_entries",
    "written_cut",
]

# The module-level name a model declares its accumulators under. The same
# tuple ``run_aggregated`` takes, so a model already folding its book for a
# scenario sweep hands this over rather than restating it.
DECLARED_BESIDE_MAIN: Final[str] = "AGGREGATIONS"

# How many names a refusal reads back before it stops -- enough to see the
# shape of a column name without printing a schema at somebody.
_SHOWN: Final[int] = 8

# What the command line may name, and what each name becomes on a column
# holding one value per policy and on a column holding one per period. The
# per-period form is a different aggregator with a name of its own, which
# is what the entry then records: a reader is told the fold ran down the
# timeline rather than across the book.
#
# Deliberately shorter than the aggregator set. ``Quantile``, ``Median``
# and ``CTE`` take a level as well as a column, and a flag grammar that
# carried one would be a second way of writing what the model file already
# writes in Python. The module's tuple is the full vocabulary; this is the
# short path for the folds that need nothing but a column.
_BY_NAME: Final[dict[str, tuple[str | None, str]]] = {
    "sum": ("Sum", "PeriodSum"),
    "mean": ("Mean", "PeriodMean"),
    "min": ("Min", "PeriodMin"),
    "max": ("Max", "PeriodMax"),
    "variance": ("Variance", "PeriodVariance"),
    "std": ("Std", "PeriodStd"),
    # ``Count`` counts scenarios and is refused on the policy axis, so the
    # only count a book has is the one taken down each period's column.
    "count": (None, "PeriodCount"),
}

# The names of those that reduce across the book as well as down a timeline,
# for the refusal that has to say which the caller may have meant.
_ACROSS_THE_BOOK: Final[tuple[str, ...]] = tuple(
    sorted(name for name, (across, _) in _BY_NAME.items() if across is not None)
)


def _partitioned() -> Any:  # noqa: ANN401 — the framework's own class, whose shape is its own business
    """Return the framework's own wrapper for an aggregator carrying a cut.

    Fetched on the call rather than imported at module scope: the scenarios
    package imports the frame and the frame imports this, so a module-level
    import here would close that loop at interpreter start.

    Handed back untyped deliberately. An aggregator reaches this module as
    whatever the model declared, and narrowing it against a class the type
    checker only knows as ``type`` would tell the checker the opposite of
    what is true: that the thing on the other side of the test has fewer
    members than before rather than the wrapper's own.
    """
    from gaspatchio.scenarios._metric import _Partitioned  # noqa: PLC0415 — see above

    return _Partitioned


class PortfolioFoldError(ValueError):
    """A fold that names no honest total of the book."""


@dataclass(frozen=True, slots=True)
class PortfolioFold:
    """One fold of the book, as it sits on the artifact's policy axis.

    Attributes:
        aggregation: The fold's own name, as the framework spells the
            aggregator that performed it -- ``sum``, ``period_sum``,
            ``mean``, ``count``. It is what the envelope's ``aggregation``
            carries, widened from the two words section 7 defined before
            there was an aggregator set to name.
        filter: The cut this fold was taken over, written the way a reader
            of section 7 would write it, or None for the whole book. A
            grouped fold's group is a cut of the rows and nothing else, so
            it goes in the member section 7 defines for exactly that
            rather than in one of its own.
        why: The plain sentence saying what this entry is an account of and
            how many policies went into it. It travels into the artifact
            unchanged, as every other entry's does.
        values: What each column came to under this fold, keyed by column
            name. A column not in here is a column the fold did not cover,
            and the artifact writes null at this entry's position rather
            than a figure nothing computed.

    """

    aggregation: str
    filter: str | None
    why: str
    values: dict[str, Any]


def _column_of(agg: Any) -> str:  # noqa: ANN401 — one aggregator, of whichever kind the model declared
    """Return the column an accumulator is a fold of."""
    inner = agg.inner if isinstance(agg, _partitioned()) else agg
    return str(inner.column)


def _spelled(agg: Any) -> str:  # noqa: ANN401 — one aggregator, of whichever kind the model declared
    """Return the fold's name, as the framework spells the aggregator.

    Snake case of the class's own name, which is the one place the name is
    written: ``PeriodSum`` is ``period_sum`` rather than ``sum`` because a
    fold down one policy's timeline and a fold across the book are two
    different statements about a column, and the entry that carries the
    numbers is where a reader is told which one they are reading.
    """
    inner = agg.inner if isinstance(agg, _partitioned()) else agg
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", type(inner).__name__).lower()


def axis_entries(  # noqa: PLR0913 — the outputs, their accumulators, and one parameter per thing a sentence has to be able to count or name
    result: Any,  # noqa: ANN401 — AggregatedResult, imported where the driver is
    aggregations: Sequence[Any],
    *,
    book: pl.DataFrame,
    source: str,
    period: int | None,
    counted_on: pl.DataFrame | None = None,
    scenario_column: str | None = None,
) -> tuple[PortfolioFold, ...]:
    """Return the axis entries a driver's folded outputs come to.

    Keyed on the fold's name and the cut it was taken over, which is the
    pair a reader can act on: two accumulators of one name over one cut are
    one fold covering two columns, and an entry per accumulator would put
    context objects on the axis differing in nothing anybody can see.

    Public because two drivers fold a book in this framework and both write
    the same axis. ``run_aggregated`` folds the policies of one book, and
    ``ScenarioRun.run`` folds a cross-joined one a scenario at a time --
    the second is the ordinary case of the grouped entry this already
    builds, and letting the scenario door write its own would be two
    spellings of one section of the envelope.

    Args:
        result: Whatever the driver handed back, read for its
            ``aggregations`` mapping alone -- keyed by each accumulator's
            alias, as both drivers key it.
        aggregations: The accumulators behind those outputs, in the order
            they were declared. Each must already carry its alias.
        book: The model points the folds were taken over.
        source: The model-point file's own name, for the sentences.
        period: The projection period the document is pinned to, or None.
        counted_on: The frame the model returned over ``book`` -- one row
            per policy, or per policy and scenario on a scenario run -- on
            which each cut's policies are counted, so a cut by a column the
            model computes is counted as exactly as one by a column of the
            book. ``book`` where None.
        scenario_column: The column a scenario run cross-joined the book
            by, or None. A cut that does not name it spans every scenario,
            and its sentence says how many.

    Returns:
        One entry per fold and cut, a grouped fold's entries sorted by
        their cut so two exports of one run compare as written.
    """
    gathered: dict[tuple[str, str | None], dict[str, Any]] = {}
    rows = book if counted_on is None else counted_on
    counted: dict[str | None, _Width] = {}
    for agg in aggregations:
        name = _spelled(agg)
        column = _column_of(agg)
        alias = agg.alias if isinstance(agg, _partitioned()) else agg.alias_
        output = result.aggregations[alias]
        if isinstance(agg, _partitioned()):
            folded = _by_group(output, by=agg.by, alias=alias)
            counted |= _policies_per_group(
                rows, by=agg.by, scenario_column=scenario_column
            )
        else:
            folded = {None: output}
            counted.setdefault(None, _width_of(rows, scenario_column=scenario_column))
        for cut, value in folded.items():
            under = gathered.setdefault((name, cut), {})
            if column in under:
                raise PortfolioFoldError(_two_folds_of_one_column(column, name))
            under[column] = _on_the_wire(value, period=period)
    return tuple(
        PortfolioFold(
            aggregation=name,
            filter=cut,
            why=_why(name, cut, counted.get(cut, _Width(book.height)), source),
            values=values,
        )
        for (name, cut), values in gathered.items()
    )


def _by_group(
    output: pl.DataFrame, *, by: Sequence[str], alias: str
) -> dict[str | None, Any]:
    """Return one group's folded value per cut, the cuts in sorted key order.

    A partitioned scalar aggregator hands back one row per group; a
    partitioned per-period one hands back the tidy frame of group, period
    and value, which is gathered here into the run of numbers a per-period
    sample is written as. Sorted by the key rather than left in the order
    the group-by happened to produce, because an axis whose entries change
    order between two runs of one model is an axis nothing can be compared
    along.
    """
    per_period = "period" in output.columns and "period" not in by
    ordered = output.sort([*by, "period"] if per_period else list(by))
    folded: dict[str | None, Any] = {}
    for row in ordered.iter_rows(named=True):
        cut = _cut(by, row)
        if per_period:
            folded.setdefault(cut, []).append(row[alias])
        else:
            folded[cut] = row[alias]
    return folded


@dataclass(frozen=True)
class _Width:
    """How many policies one cut holds, and how many scenarios it spans."""

    policies: int
    scenarios: int = 1


# Names the counts are taken under, chosen so no grouping column of a model
# can be one of them.
_ROWS: Final[str] = "__gaspatchio_fold_rows"
_SCENARIOS: Final[str] = "__gaspatchio_fold_scenarios"


def _policies_per_group(
    rows: pl.DataFrame, *, by: Sequence[str], scenario_column: str | None
) -> dict[str | None, _Width]:
    """Return how many policies each cut of ``rows`` holds.

    Counted on the frame the fold was taken over rather than asked of the
    driver, which folds values rather than counting rows. On a scenario run
    that frame holds each policy once per scenario, so a cut that does not
    name the scenario column holds each of its policies once per scenario
    it spans, and the count is divided back down to policies. A grouping
    column the frame does not hold has no count, and the caller says the
    book's size.
    """
    if any(column not in rows.columns for column in by):
        return {}
    counts = rows.group_by(list(by)).len(name=_ROWS)
    spanned: dict[str | None, int] = {}
    if (
        scenario_column is not None
        and scenario_column in rows.columns
        and scenario_column not in by
    ):
        per_cut = (
            rows.select([*by, scenario_column])
            .unique()
            .group_by(list(by))
            .len(name=_SCENARIOS)
        )
        spanned = {
            _cut(by, row): int(row[_SCENARIOS]) for row in per_cut.iter_rows(named=True)
        }
    widths: dict[str | None, _Width] = {}
    for row in counts.iter_rows(named=True):
        cut = _cut(by, row)
        scenarios = max(spanned.get(cut, 1), 1)
        widths[cut] = _Width(int(row[_ROWS]) // scenarios, scenarios)
    return widths


def _width_of(rows: pl.DataFrame, *, scenario_column: str | None) -> _Width:
    """Return how many policies and scenarios a fold of the whole of ``rows`` spans."""
    if scenario_column is None or scenario_column not in rows.columns:
        return _Width(rows.height)
    scenarios = max(int(rows.get_column(scenario_column).n_unique()), 1)
    return _Width(rows.height // scenarios, scenarios)


def _cut(by: Sequence[str], row: Mapping[str, Any]) -> str:
    """Return the group as the cut it is, written the way section 7 writes one.

    ``scenario_id == "BASE"``, and two grouping columns joined by ``and``.
    A filter is what the format already calls *the cut the sampled rows had
    been narrowed by*, and a group is exactly that -- so the entry says it
    in the member that means it rather than in a new one that would mean it
    a second time.
    """
    return " and ".join(written_cut(column, row[column]) for column in by)


def written_cut(column: str, value: Any) -> str:  # noqa: ANN401 — one key, of whatever type the column holds
    """Return one column and one value as the cut a reader would write.

    ``scenario_id == "BASE"``. Public because a scenario export writes the
    same cut on its *policy* entries -- a row of a cross-joined frame sits
    in one scenario, and the entry says which -- and two spellings of one
    filter is exactly the disagreement section 7.4 refuses.
    """
    return f"{column} == {_written(value)}"


def _written(value: Any) -> str:  # noqa: ANN401 — one group key, of whatever type the column holds
    """Return one group key as a reader would write it in a filter."""
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _on_the_wire(value: Any, *, period: int | None) -> Any:  # noqa: ANN401 — one folded value, of whatever shape the column holds
    """Return one folded value in the shape and formatting a sample is written in.

    The same formatting every other value in the document is written in,
    because a reader comparing a policy's number with the book's should not
    have to notice that the two were written differently. A pinned period
    takes that period's own number out of a per-period fold, for the reason
    the envelope's ``periods`` exists: the document states which point of
    the timeline it was read at, and every value in it has to be read at
    the same one.
    """
    listed: list[Any] | tuple[Any, ...]
    if isinstance(value, (list, tuple)):
        listed = value
    elif hasattr(value, "tolist"):
        # ``tolist`` before iterating: it is what reads a masked period -- one
        # with no value -- as None, where iterating a masked array would hand
        # over numpy's masked constant.
        listed = value.tolist()
    else:
        return one_value_on_the_wire(value)
    run = [None if one is None else one_value_on_the_wire(float(one)) for one in listed]
    if period is None:
        return run
    return run[period] if 0 <= period < len(run) else None


def _why(name: str, cut: str | None, width: _Width, source: str) -> str:
    """Return the sentence saying what this entry is an account of."""
    noun = "policy" if width.policies == 1 else "policies"
    over = f"folded by {name} over {width.policies:,} {noun} in {source}"
    if width.scenarios > 1:
        over += f", across {width.scenarios:,} scenarios"
    if cut is None:
        return f"the whole book, {over}"
    return f"{cut.replace(' == ', ' ')}, {over}"


def _two_folds_of_one_column(column: str, name: str) -> str:
    """Return the refusal for one column folded twice into one entry."""
    return (
        f"Column {column!r} is folded by {name} twice over the same cut of "
        "the book, and one entry of the policy axis carries one value per "
        "column -- so the second would replace the first with nothing in "
        "the document to say it had. Fold it once, or fold the second over "
        "a different cut with .over(column)."
    )
