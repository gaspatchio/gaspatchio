# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Reducing a book on the card: the aggregators ``run_aggregated`` takes.

A reserve run over ten million policies is wanted as a handful of numbers --
a best estimate, a cashflow term structure, the same split by product -- and
the per-policy rows that make them are hundreds of gigabytes that nobody
reads. So this engine folds each batch where it computed it and hands back
the totals, never building the per-policy frame. The aggregators are the
caller's own objects, the ones the Polars path takes unchanged, and the
answer is the core's own :class:`AggregatedResult`, agreeing with Polars'
fold to 1e-12 of its scale (section 11.1.12): the order floating-point
additions were made in is the only permitted difference.

**Two kinds of fold, split by what crosses back to the host.**

- *A scalar aggregator over a per-policy column* -- ``Sum``, ``Min``,
  ``Max``, ``Mean``, ``Variance``, ``Std``, and the sketch-backed
  ``Quantile``, ``Median``, ``CTE`` and ``QuantileRank`` -- pulls that one
  column for the batch, one value per policy, and folds it through the
  Polars path's own batch fold. ``.over(by)`` groups on the host exactly as
  that fold groups, because it *is* that fold. The accumulators are the
  core's, so a sketch is the core's sketch and a Welford merge the core's.
- *A per-period aggregator over a per-period column* -- the seven ``Period*``
  kinds whose batch partial is a closed form -- computes on the device the
  partial the core's ``_assemble_partial`` would have built from the
  exploded frame, each policy masked to its own horizon, and hands it to the
  aggregator's own ``add_input``. What crosses back is one value per period
  per partition. ``.over(by)`` sorts the book into partitions on the host
  before anything runs, and each batch reduces by segment on the device.

**The fold is a function of one batch, and the loop that feeds it is one
function too** (:func:`fed`). The plan hands each batch over the moment it
finishes -- on a card, with the next batch already computing
-- and the fold reduces it, keeps its findings and lets it go. Its
per-period partials were queued on the device beside its own program when
it was dispatched (:func:`queued_beside`), so reading them back waits for
that program and not the next. A batch's program returns only the columns
folded, and what the run holds at any moment is at most two batches of those
-- the one being folded and the one on the card -- beside the accumulators,
so a book's size moves the time a fold takes and not its peak.

**Refusals are the run's, in the run's report.** An aggregator this engine
cannot fold is refused by name before the book is read, alongside every tree
refusal the document earns: ``Count``, ``ArgMin``, ``ArgMax``, ``.of()`` and a
multi-level quantile under ``.over()``, exactly as ``run_aggregated`` refuses
them before it starts, and the three
per-period kinds that keep a sketch per period (``PeriodQuantile``,
``PeriodMedian``, ``PeriodCTE``), pointing back to Polars. A check the trace
carried refuses at completion as it does for ``run``, and no total is
returned.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Final, Literal

import jax
import jax.numpy as jnp
import numpy as np
import polars as pl

from gaspatchio.engines.aggregation import (
    AggregatedResult,
    Partitioned,
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    alias_of,
    extract_outputs,
    fold_per_policy,
    inner_of,
    reject_multi_level_over,
    reject_scenario_axis_only,
)
from gaspatchio.engines.protocol import VALUE_BEARING, Producer
from gaspatchio.engines.report import EngineRefusal, Refusal, RunReport

from .horizon import periods_of
from .lowerings.rollforward import STATE_KIND
from .plan import ENGINE_NAME, ExecutionPlan, _as_series, _refuses, checked_depth
from .preflight import findings_of, merged_findings
from .typed import INT64_MAX, INT64_MIN, cell_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from .capability import NodeRecord
    from .plan import Batched, Dispatched, Prepared
    from .preflight import Finding

__all__ = [
    "Fold",
    "Folding",
    "Partitions",
    "Queued",
    "aggregate",
    "completed",
    "fed",
    "fold_batch_on_the_device",
    "folded",
    "partitions_of",
    "queued_beside",
    "read_folds",
]

# What a fold totals: numbers. A text or date column has no sum, and the
# Polars path fails on one mid-run where this refuses it before the book is
# read.
_NUMERIC: Final[frozenset[str]] = frozenset({"f64", "i64", "bool"})

# A total of whole numbers crosses back as two arrays, the high and the low
# 32 bits of its cells summed apart.
_HALVES: Final[int] = 2

# A total of squares of whole numbers crosses back as the totals of the
# products of each cell's four 16-bit limbs, one array per pair of limbs.
_LIMB_BITS: Final[int] = 16
_LIMB_PAIRS: Final[tuple[tuple[int, int], ...]] = tuple(
    (j, k) for j in range(4) for k in range(j, 4)
)

# How many arrays a whole-number partial crosses back as, per kind: the
# halves of the total, beside the count for a mean, and beside the count and
# the limb products for the two moment kinds.
_WHOLE_ARRAYS: Final[dict[str, int]] = {
    "sum": _HALVES,
    "mean": _HALVES + 1,
    "moment": 1 + _HALVES + len(_LIMB_PAIRS),
}

# The shape a partial takes, per closed-form per-period kind: the partial the
# core's ``_assemble_partial`` builds for that kind, and nothing else. The
# three sketch-backed kinds have no closed form and are absent on purpose.
Partial = Literal["sum", "count", "min", "max", "mean", "moment"]
_PARTIAL_OF: Final[dict[type, Partial]] = {
    PeriodSum: "sum",
    PeriodCount: "count",
    PeriodMin: "min",
    PeriodMax: "max",
    PeriodMean: "mean",
    PeriodVariance: "moment",
    PeriodStd: "moment",
}


@dataclass(frozen=True, slots=True)
class Fold:
    """One aggregator, read against the artifact it will fold.

    Attributes:
        alias: What the caller reads the answer under.
        aggregator: The caller's own object, partitioned or not; every
            accumulator this run keeps is one it created.
        node_id: The final-schema node the aggregator's column comes from.
        column: That column's name, as the model ends on it.
        carrier: What the column's cells are held in: ``f64``, ``i64`` or
            ``bool``.
        partial: The closed-form partial a per-period kind folds into, or
            None for an aggregator of one value per policy.
        by: The partition columns of ``.over(by)``, or ``()``.

    """

    alias: str
    aggregator: Any
    node_id: str
    column: str
    carrier: str
    partial: Partial | None
    by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Partitions:
    """The book sorted into the partitions one ``.over(by)`` names.

    Attributes:
        codes: Each policy's partition, as a position into ``keys``.
        keys: Each partition's key, spelled exactly as Polars spells a group
            key -- a tuple of the book's own Python values, one per ``by``
            column -- so a partition folded here lands in the same slot of
            the accumulator a Polars fold would have put it in.

    """

    codes: np.ndarray
    keys: tuple[tuple[object, ...], ...]


@dataclass(slots=True)
class Folding:
    """What the run has folded so far, and what its batches have said.

    Attributes:
        accumulators: Alias to the core accumulator it folds into.
        host: What the host stage's own checks caught, over the whole book,
            which completion reads in front of every batch's.
        findings: Every batch's findings, which are small and are judged
            together at completion exactly as ``run`` judges them.
        n_periods: The longest per-period ``f64`` column any batch carried,
            which is what ``run_aggregated`` reports as ``n_periods``.
        largest: The most policies any one batch held.
        refused: Whether the findings so far already refuse the run, read as
            completion reads them. No later batch is folded: the answer is
            the refusal, and folding values it withholds could only put a
            fault in front of it.
        fault: The first fault a fold met, held so that a refusal can still
            be the run's answer, and raised at completion where none is.

    """

    accumulators: dict[str, Any]
    host: tuple[Finding, ...] = ()
    findings: list[Finding] = field(default_factory=list)
    n_periods: int = 0
    largest: int = 0
    refused: bool = False
    fault: Exception | None = None


def _refused(alias: str, what: str, move: str) -> Refusal:
    """Return one aggregation refusal, in the group nothing ran in.

    It cites no clause, and neither does the empty book's. A fold is outside
    the artifact -- section 4 of the specification leaves every aggregate out
    of it -- so no section states what ``run_aggregated`` folds, and the
    refusal's own sentence carries the reason instead.
    """
    return Refusal(
        group="tree", where=alias, count=None, what=what, move=move, clause=None
    )


def _final_schema(plan: ExecutionPlan) -> dict[str, str]:
    """Return every column the model ends on, and the node it comes from."""
    return {
        record.column: node_id
        for node_id, record in plan.records.items()
        if record.in_final_schema
        and record.kind in VALUE_BEARING
        and record.column is not None
    }


def _carrier_of(record: NodeRecord) -> str | None:
    """Return what one node's cells are held in, reading a running state's contract.

    A running state records ``unknown`` for its canonical identity, and 16.1
    fixes what it physically is: one ``list[f64]`` per policy. The record is
    the authority wherever it says something.
    """
    if record.kind == STATE_KIND and record.dtype == "unknown":
        return "f64"
    return cell_of(record.dtype)


def _per_period(record: NodeRecord) -> bool:
    """Return whether one node holds a value per period rather than per policy."""
    return record.shape == "list" or (
        record.kind == STATE_KIND and record.dtype == "unknown"
    )


def read_folds(
    plan: ExecutionPlan, aggregations: Sequence[Any]
) -> tuple[list[Fold], list[Refusal]]:
    """Read each aggregator against the artifact, refusing what cannot be folded.

    Every refusal is found, not the first: an aggregation list with two
    problems in it is one report with two lines, and a reader fixing one
    should not be sent round again for the other.

    Returns:
        The folds, in the order the caller listed them, and every refusal.

    """
    folds: list[Fold] = []
    refusals: list[Refusal] = []
    schema = _final_schema(plan)
    seen: set[str] = set()
    for position, aggregator in enumerate(aggregations):
        try:
            alias = alias_of(aggregator)
        except ValueError as unnamed:
            refusals.append(
                _refused(
                    f"aggregation {position + 1}",
                    str(unnamed),
                    "name every aggregator with .alias(name): the alias is what "
                    "the answer is read under",
                )
            )
            continue
        if alias in seen:
            refusals.append(
                _refused(
                    alias,
                    f"two aggregators share the alias {alias!r}",
                    "give each aggregator an alias of its own",
                )
            )
            continue
        seen.add(alias)
        try:
            reject_scenario_axis_only([aggregator])
            reject_multi_level_over([aggregator])
        except (ValueError, NotImplementedError) as off_axis:
            what, move = _off_the_policy_axis(aggregator, str(off_axis))
            refusals.append(_refused(alias, what, move))
            continue
        # The caller's aggregator, of whatever kind: the protocol states what
        # the drivers call, and the column it folds is an attribute beside it.
        inner: Any = inner_of(aggregator)
        per_period = hasattr(inner, "batch_reduce")
        kind = type(inner).__name__
        folded: Partial | None = _PARTIAL_OF.get(type(inner)) if per_period else None
        if per_period and folded is None:
            refusals.append(
                _refused(
                    alias,
                    f"{kind} keeps a whole distribution per period, which has no "
                    "partial this engine can compute where it computed the "
                    "column",
                    "fold it on Polars (run_aggregated without engine=), or use "
                    f"a closed-form kind: {_CLOSED_FORMS}",
                )
            )
            continue
        column = str(inner.column)
        node_id = schema.get(column)
        if node_id is None:
            refusals.append(
                _refused(
                    alias,
                    f"{kind} folds {column!r}, which is not a column of this "
                    "model's final schema",
                    "name a column the model ends on",
                )
            )
            continue
        record = plan.records[node_id]
        if per_period != _per_period(record):
            refusals.append(
                _refused(
                    alias,
                    (
                        f"{kind} folds one value per period and {column!r} "
                        "holds one value per policy"
                        if per_period
                        else f"{kind} folds one value per policy and {column!r} "
                        "holds one value per period"
                    ),
                    (
                        f"fold a per-period column, or use {kind[len('Period') :]}"
                        if per_period
                        else f"fold a per-policy column, or use Period{kind}"
                    ),
                )
            )
            continue
        carrier = _carrier_of(record)
        if carrier not in _NUMERIC:
            refusals.append(
                _refused(
                    alias,
                    f"{column!r} holds {record.dtype}, and a fold totals numbers",
                    "fold a numeric column: f64, i64 or a Boolean indicator",
                )
            )
            continue
        by = aggregator.by if isinstance(aggregator, Partitioned) else ()
        standing = [_partition_refusal(alias, name, schema, plan) for name in by]
        if any(standing):
            refusals.extend(one for one in standing if one is not None)
            continue
        folds.append(
            Fold(
                alias=alias,
                aggregator=aggregator,
                node_id=node_id,
                column=column,
                carrier=str(carrier),
                partial=folded,
                by=tuple(by),
            )
        )
    return folds, refusals


# The closed-form per-period kinds, as a reader would list them.
_CLOSED_FORMS: Final = (
    "PeriodSum, PeriodCount, PeriodMin, PeriodMax, PeriodMean, PeriodVariance "
    "or PeriodStd"
)


def _off_the_policy_axis(aggregator: Any, said: str) -> tuple[str, str]:  # noqa: ANN401 -- an aggregator of any kind
    """Return what a refused aggregator asks of a book, and what to fold instead.

    ``run_aggregated``'s own guards decide *whether* an aggregator is
    refused, so the two engines refuse exactly the same set; this decides only
    the words, in the order those guards test. A reader is owed a next step
    that works on this engine, not the observation that Polars refuses it too.
    A guard added later that this does not know keeps its own sentence.
    """
    inner = inner_of(aggregator)
    kind = type(inner).__name__
    if getattr(inner, "requires_scenario_id", False):
        found = kind.removeprefix("Arg")
        return (
            (
                f"{kind} answers which scenario held the value, and a book has "
                "no scenarios"
            ),
            (
                f"fold {found} for the value itself, or find the scenario with "
                "for_each_scenario"
                if found != kind
                else "fold it on the scenario axis with for_each_scenario"
            ),
        )
    if kind == "Count":
        return (
            "Count counts the scenarios that contributed, and a book has none",
            (
                "count the policies each period holds with PeriodCount, or "
                "count scenarios with for_each_scenario"
            ),
        )
    if getattr(inner, "within_expr_override", None) is not None:
        return (
            (
                f"{kind}.of(...) reduces each batch to one value before folding, "
                "so its answer would depend on how the book was batched"
            ),
            "write the quantity as a column of the model and aggregate that column",
        )
    if isinstance(aggregator, Partitioned) and hasattr(inner, "levels"):
        return (
            (
                f"{kind} answers several levels at once, and a result partitioned "
                "with .over() holds one value per partition"
            ),
            (
                f"fold {kind} without .over() on Polars (run_aggregated without "
                f"engine=), or partition a closed-form kind here: {_CLOSED_FORMS}"
                if hasattr(inner, "batch_reduce")
                else "partition Median, CTE or QuantileRank with .over(), or fold "
                f"{kind} without .over()"
            ),
        )
    return (said, "fold a form of it run_aggregated accepts on the policy axis")


def _partition_refusal(
    alias: str, name: str, schema: Mapping[str, str], plan: ExecutionPlan
) -> Refusal | None:
    """Return why one partition column cannot sort this book, or None.

    A partition is a column that arrived with the book. The book is sorted
    into partitions on the host before anything is computed, so a column the
    model calculates has no values yet when the sorting is done -- and the
    alternative, sorting after the fact, would mean holding every policy's
    per-period values until it was known which partition each one was in.
    """
    node_id = schema.get(name)
    if node_id is None:
        return _refused(
            alias,
            f"the partition column {name!r} is not a column of this model's "
            "final schema",
            "partition by a column the model ends on",
        )
    record = plan.records[node_id]
    if record.kind != "input":
        return _refused(
            alias,
            f"the partition column {name!r} is calculated by the model, and "
            "this engine sorts the book into partitions before it calculates "
            "anything",
            "partition by a column that arrived with the book, or fold this "
            "one on Polars (run_aggregated without engine=)",
        )
    if record.shape == "list":
        return _refused(
            alias,
            f"the partition column {name!r} holds a value per period, and a "
            "partition is one value per policy",
            "partition by a per-policy column",
        )
    return None


def partitions_of(prepared: Prepared, by: tuple[str, ...]) -> Partitions:
    """Sort the whole book into the partitions ``by`` names, once, on the host.

    From the columns as the engine carried them in -- text as its interned
    codes, dates as day counts, numbers as themselves -- so the sort is whole
    array arithmetic rather than a walk over a million Python values, and the
    partition count is fixed before any batch runs. Each partition's key is
    then read back off the book as the caller handed it in, at the first
    policy standing in it.
    """
    rows = prepared.inputs.rows
    key = np.zeros(rows, dtype=np.int64)
    for name in by:
        cells = np.asarray(prepared.inputs.columns[name].array)
        _distinct, inverse = np.unique(cells, return_inverse=True)
        many = int(_distinct.size)
        # Renumbered after every column rather than folded into one wide
        # number, so no count of columns or of distinct values can overflow.
        _combined, key = np.unique(
            key * many + np.asarray(inverse).reshape(-1), return_inverse=True
        )
        key = np.asarray(key, dtype=np.int64).reshape(-1)
    _distinct_keys, first = np.unique(key, return_index=True)
    frame = prepared.inputs.frame
    keys = tuple(tuple(frame[name][int(row)] for name in by) for row in first)
    return Partitions(codes=key.astype(np.int32), keys=keys)


def fed(  # noqa: PLR0913 -- the plan's loop, and what the fold asks of it
    plan: ExecutionPlan,
    prepared: Prepared,
    batch: int | None,
    *,
    depth: int | None = None,
    returns: frozenset[str] | None = None,
    on_dispatch: Callable[[Dispatched], object] | None = None,
) -> Iterator[Batched]:
    """Return the batches the fold is fed, each handed over as it finishes.

    **The one place the loop's source lives:** the plan's own
    ``stage_batches``, the stream ``run`` publishes from, which
    dispatches the next batch while this one is folded and hands
    each over in the order it was dispatched. ``returns`` is the columns
    each batch's program hands back -- the fold's own -- and ``on_dispatch``
    is what the fold queues on the device beside each batch's program
    (:func:`queued_beside`).
    """
    return plan.stage_batches(
        prepared,
        batch=batch,
        depth=depth,
        returns=returns,
        on_dispatch=on_dispatch,
    )


@dataclass(frozen=True, slots=True)
class Queued:
    """What the fold queued on the device beside one batch's program.

    Attributes:
        partials: Each per-period fold's partial for the batch, by alias,
            still on the device.
        fault: What queuing one of them met, held for the batch's own turn:
            the batch before it may yet refuse, and a refusal is the run's
            real answer.
        faulted: The alias whose partial met the fault. Nothing after it in
            the fold's order was queued, and the fault is raised where that
            partial is read, exactly where it was met when each batch was
            folded straight after its program.

    """

    partials: dict[str, tuple[jax.Array, ...]] = field(default_factory=dict)
    fault: Exception | None = None
    faulted: str | None = None


def queued_beside(
    dispatched: Dispatched,
    folds: Sequence[Fold],
    folding: Folding,
    partitions: Mapping[tuple[str, ...], Partitions],
) -> Queued | None:
    """Queue one batch's per-period partials on the device, behind its own program.

    The next batch's program is dispatched before this batch is folded, so a
    partial queued when the batch is folded would wait for that program as
    well as its own -- the card would finish the next batch before the host
    could read this one's partial back. Queued the moment the batch is
    dispatched, it waits for nothing but the batch it reduces.

    Nothing is queued once the run already refuses or holds a fault: such a
    batch runs for its findings only. A fault met here is held, not raised,
    and becomes the run's at the batch's own turn (:func:`folded`), which is
    where it was met when every batch ran after the one before it.
    """
    if folding.refused or folding.fault is not None:
        return None
    partials: dict[str, tuple[jax.Array, ...]] = {}
    for one in folds:
        if one.partial is None:
            continue
        try:
            partials[one.alias] = _partial_on_the_device(
                one,
                *dispatched.per_period(one.node_id),
                dispatched.rows,
                partitions.get(one.by),
            )
        except Exception as error:  # noqa: BLE001 -- held for the batch's own turn, as a fold's fault is
            return Queued(partials=partials, fault=error, faulted=one.alias)
    return Queued(partials=partials)


def folded(
    batches: Iterator[Batched],
    prepared: Prepared,
    folds: Sequence[Fold],
    folding: Folding,
    partitions: Mapping[tuple[str, ...], Partitions],
) -> Folding:
    """Fold every batch as it arrives, keeping its findings and letting it go.

    The stream's own discipline, for a reader that reduces rather than
    writes. Every batch's findings are kept whatever happens, because they
    are what completion judges. Once the findings so far refuse -- read as
    completion will read them -- nothing more is folded, and the remaining
    batches run for their findings only. A fault met folding a batch -- or
    queuing its partials when it was dispatched -- is held rather than
    raised, with the frames it passed through cleared so that it does not
    keep that batch alive, because a later batch may yet refuse and a refusal
    is the run's real answer. And each batch is let go of once folded, before
    any batch after the one on the card is dispatched.
    """
    for batched in batches:
        folding.findings.extend(batched.findings)
        folding.refused = folding.refused or _refuses(
            [*folding.host, *folding.findings]
        )
        if not folding.refused and folding.fault is None:
            try:
                fold_batch_on_the_device(batched, prepared, folds, folding, partitions)
            except Exception as error:  # noqa: BLE001 -- held for completion, which raises it unless a refusal is the answer
                # Held without the batch it was folding: the frames the fault
                # passed through would otherwise keep that batch's values
                # alive while every later batch runs.
                traceback.clear_frames(error.__traceback__)
                folding.fault = error
        # Let go of this batch before the one after the next is dispatched;
        # the loop's own name would otherwise hold its values through it.
        del batched
    return folding


def fold_batch_on_the_device(
    batched: Batched,
    prepared: Prepared,
    folds: Sequence[Fold],
    folding: Folding,
    partitions: Mapping[tuple[str, ...], Partitions],
) -> None:
    """Fold one batch into every aggregator, holding nothing of it afterwards.

    A function of this one batch and the accumulators, and nothing else: the
    findings, the refusal and any fault are the loop's (:func:`folded`), and
    no part of the batch outlives the call. The per-period partials are the
    ones queued beside the batch's program when it was dispatched
    (:func:`queued_beside`): the fold is fed with them, and only with them.

    Raises:
        TypeError: If the batch arrived without partials queued beside its
            program -- a fold fed some other way, which is a defect.

    """
    queued = batched.queued
    if not isinstance(queued, Queued):  # pragma: no cover -- a defect, not a refusal
        message = (
            "a batch reached the fold without the partials queued beside its "
            "program: feed the fold through queued_beside"
        )
        raise TypeError(message)
    folding.largest = max(folding.largest, int(batched.rows.size))
    # What ``run_aggregated`` reports as its period count: the longest
    # per-period double of the final schema, read off the batch's own
    # timelines -- the columns themselves never left the card.
    folding.n_periods = max(folding.n_periods, batched.longest)
    _fold_scalars(
        batched,
        prepared,
        [one for one in folds if one.partial is None],
        folding.accumulators,
    )
    for one in folds:
        if one.partial is None:
            continue
        if queued.fault is not None and queued.faulted == one.alias:
            # Met queuing this partial; its turn is now.
            raise queued.fault
        _fold_periods(
            batched,
            one,
            partitions.get(one.by),
            folding.accumulators,
            queued.partials[one.alias],
        )


def _fold_scalars(
    batched: Batched,
    prepared: Prepared,
    folds: Sequence[Fold],
    accumulators: dict[str, Any],
) -> None:
    """Fold one value per policy into every scalar aggregator, grouping as Polars does.

    The frame handed over holds the handful of per-policy columns these
    aggregators read -- the folded columns off the device, the partition
    columns off the book as it arrived -- and it goes through the Polars
    path's own batch fold. One frame of a few scalar columns, never the
    per-policy result.
    """
    if not folds:
        return
    held: dict[str, pl.Series] = {}
    for one in folds:
        for name in one.by:
            held[name] = prepared.inputs.frame[name].gather(batched.rows)
    for one in folds:
        held[one.column] = _as_series(
            one.column, batched.values[one.node_id], batched.dictionary
        )
    fold_per_policy(
        pl.DataFrame(list(held.values())),
        [one.aggregator for one in folds],
        accumulators,
    )


def _fold_periods(
    batched: Batched,
    one: Fold,
    partitions: Partitions | None,
    accumulators: dict[str, Any],
    partial: tuple[jax.Array, ...],
) -> None:
    """Fold one per-period column's batch partial into its aggregator.

    The partial was computed where the column is, queued beside the batch's
    program when it was dispatched, and what comes back is one row of periods
    per partition. Each row is then cut to the longest timeline among that
    partition's policies in this batch, because that is how many periods the
    exploded frame would have held for it -- a partial one period too long
    would move every later batch's periods by one.
    """
    lengths = np.asarray(periods_of(batched.values[one.node_id]).lengths)
    segments, codes = _segments(partitions, batched.rows)
    kind = one.partial
    if kind is None:  # pragma: no cover -- only per-period folds reach here
        message = f"{one.alias} has no partial to fold"
        raise AssertionError(message)
    arrays = [np.asarray(array) for array in partial]
    longest = np.zeros(segments, dtype=np.int64)
    np.maximum.at(longest, codes, lengths)
    if partitions is None:
        accumulators[one.alias] = one.aggregator.add_input(
            accumulators[one.alias], _assembled(kind, arrays, 0, int(longest[0]))
        )
        return
    present = np.bincount(codes, minlength=segments) > 0
    for segment in np.flatnonzero(present & (longest > 0)):
        at = int(segment)
        accumulators[one.alias] = one.aggregator.add_input(
            accumulators[one.alias],
            (partitions.keys[at], _assembled(kind, arrays, at, int(longest[at]))),
        )


def _segments(
    partitions: Partitions | None, rows: np.ndarray
) -> tuple[int, np.ndarray]:
    """Return how many partitions a batch reduces into, and each policy's own."""
    if partitions is None:
        return 1, np.zeros(rows.size, dtype=np.int32)
    return len(partitions.keys), partitions.codes[rows]


def _partial_on_the_device(
    one: Fold,
    cells: jax.Array,
    counts: jax.Array,
    rows: np.ndarray,
    partitions: Partitions | None,
) -> tuple[jax.Array, ...]:
    """Queue one per-period fold's partial for a batch, and return it unread.

    ``cells`` and ``counts`` are the column and its policies' period counts
    as the device holds them; nothing here waits for either.
    """
    kind = one.partial
    if kind is None:  # pragma: no cover -- only per-period folds reach here
        message = f"{one.alias} has no partial to fold"
        raise AssertionError(message)
    segments, codes = _segments(partitions, rows)
    queued: tuple[jax.Array, ...] = _partials(
        cells,
        counts,
        jnp.asarray(codes),
        kind=kind,
        segments=segments,
        integral=one.carrier != "f64",
        whole=one.carrier == "i64",
    )
    return queued


def _joined(high: np.ndarray, low: np.ndarray) -> np.ndarray:
    """Return the exact totals two ``int64`` halves add up to, as Python ints."""
    exact = np.empty(high.shape[0], dtype=object)
    exact[:] = [(int(h) << 32) + int(lo) for h, lo in zip(high, low, strict=True)]
    return exact


def _squares_joined(products: Sequence[np.ndarray]) -> np.ndarray:
    """Return the exact totals of squares the limb-pair product totals add up to."""
    exact = np.zeros(products[0].shape[0], dtype=object)
    for (j, k), total in zip(_LIMB_PAIRS, products, strict=True):
        weight = (1 if j == k else 2) << (_LIMB_BITS * (j + k))
        exact += np.array([weight * int(cell) for cell in total], dtype=object)
    return exact


def _assembled(
    kind: Partial, arrays: Sequence[np.ndarray], segment: int, length: int
) -> object:
    """Return one partition's partial, in the shape ``_assemble_partial`` builds.

    A vector of doubles for the four one-number kinds, a sum beside a count
    for a mean, and a count, a mean and a sum of squared deviations for the
    two moment kinds -- the last with ``nan_to_num`` applied exactly where
    the core applies it, so a period's moments merge the way the core's do.
    A total of whole numbers arrives as its two ``int64`` halves and is
    joined into exact Python ints, the partial the core builds from its
    ``Int128`` total; a mean's beside its count, and the two moment kinds'
    as the count, the exact total and the exact total of squares, which
    the core builds from the same column the same way.
    """
    cut = [np.asarray(array[segment, :length]) for array in arrays]
    if len(arrays) == _WHOLE_ARRAYS.get(kind):
        if kind == "sum":
            exact = _joined(cut[0], cut[1])
            return np.ma.MaskedArray(exact, mask=np.zeros(length, dtype=bool))
        if kind == "mean":
            exact = _joined(cut[0], cut[1])
            return (
                np.ma.MaskedArray(exact, mask=np.zeros(length, dtype=bool)),
                cut[2].astype(np.float64),
            )
        return (
            cut[0].astype(np.float64),
            _joined(cut[1], cut[2]),
            _squares_joined(cut[3:]),
        )
    doubles = [one.astype(np.float64) for one in cut]
    if kind == "mean":
        return (doubles[0], doubles[1])
    if kind == "moment":
        return (doubles[0], doubles[1], np.nan_to_num(doubles[2]))
    return doubles[0]


def _reduced(
    cells: jax.Array,
    codes: jax.Array,
    segments: int,
    how: Literal["sum", "min", "max"],
) -> jax.Array:
    """Return one reduction over the policies of a batch, one row per partition.

    A plain reduction where there is one partition, which XLA orders the same
    way on every run of one shape; a segment reduction where there are more,
    which is one pass over the batch however many partitions it holds.
    """
    if segments == 1:
        if how == "sum":
            return jnp.sum(cells, axis=0, keepdims=True)
        # Each extremum starts from its own identity, so a batch the model's
        # selection emptied folds to that identity rather than failing in
        # numpy's words over a reduction of nothing (11.1.1: zero periods
        # over zero rows, and no failure).
        if jnp.issubdtype(cells.dtype, jnp.floating):
            least, greatest = jnp.inf, -jnp.inf
        else:
            info = np.iinfo(cells.dtype)
            least, greatest = info.max, info.min
        if how == "min":
            return jnp.min(cells, axis=0, keepdims=True, initial=least)
        return jnp.max(cells, axis=0, keepdims=True, initial=greatest)
    if how == "sum":
        return jax.ops.segment_sum(cells, codes, num_segments=segments)
    if how == "min":
        return jax.ops.segment_min(cells, codes, num_segments=segments)
    return jax.ops.segment_max(cells, codes, num_segments=segments)


@partial(jax.jit, static_argnames=("kind", "segments", "integral", "whole"))
def _partials(  # noqa: PLR0913 -- three arrays, and the four facts a program is built around
    cells: jax.Array,
    counts: jax.Array,
    codes: jax.Array,
    *,
    kind: Partial,
    segments: int,
    integral: bool,
    whole: bool = False,
) -> tuple[jax.Array, ...]:
    """Return one batch's partial for one per-period kind, per partition.

    Every cell past a policy's own horizon is masked to the reduction's
    neutral element first -- nought for a total, the far end of the type for
    an extremum -- so the bucket the engine padded to cannot reach a total.

    A total of whole numbers or indicators is taken in two ``int64`` halves
    -- each cell's high 32 bits and its low 32 bits, summed apart -- which
    no batch of fewer than 2**31 policies can wrap, and the host joins them
    into the exact total, as the Polars partial totals in ``Int128``. A
    total in one ``int64`` wrapped past it: 2**62, 2**62 and 5 summed to
    -9.2e18. A mean's total is taken the same way, beside its count: in one
    ``int64`` 2**62 and 2**62 averaged -4.6e18 two policies a batch. Over an
    ``i64`` column (``whole``) the two moment kinds take the count, the total
    in halves, and the total of squares as the totals of the products of each
    cell's four 16-bit limbs -- ten of them, each product under 2**32 -- so
    the host joins exact figures, as the Polars partial totals in ``Int128``;
    in doubles 2**53 + 1, + 2, + 3 and + 5 had a variance that moved with the
    batching. Over doubles and indicators they work in doubles, as Polars'
    mean and variance do. An extremum
    over doubles passes over a NaN unless a period holds nothing else, where
    it answers NaN -- which is what Polars' own ``min`` and ``max`` do inside
    one group.
    """
    width = cells.shape[1]
    active = jnp.arange(width, dtype=jnp.int32)[None, :] < counts[:, None]
    present = _reduced(active.astype(jnp.int64), codes, segments, "sum")
    if kind == "count":
        return (present,)
    held = cells.astype(jnp.int64) if integral else cells.astype(jnp.float64)
    if kind in ("sum", "mean") and integral:
        halves = _halves_reduced(jnp.where(active, held, 0), codes, segments)
        return halves if kind == "sum" else (*halves, present)
    if kind == "moment" and whole:
        cut = jnp.where(active, held, 0)
        limbs = [
            jnp.bitwise_and(jnp.right_shift(cut, _LIMB_BITS * at), 0xFFFF)
            for at in range(3)
        ]
        limbs.append(jnp.right_shift(cut, _LIMB_BITS * 3))
        products = tuple(
            _reduced(limbs[j] * limbs[k], codes, segments, "sum")
            for j, k in _LIMB_PAIRS
        )
        return (present, *_halves_reduced(cut, codes, segments), *products)
    if kind in ("sum", "mean"):
        total = _reduced(jnp.where(active, held, 0), codes, segments, "sum")
        return (total,) if kind == "sum" else (total, present)
    if kind in ("min", "max"):
        return (
            _extremum(
                held,
                active,
                present,
                codes,
                segments=segments,
                kind=kind,
                integral=integral,
            ),
        )
    doubles = held.astype(jnp.float64)
    total = _reduced(jnp.where(active, doubles, 0.0), codes, segments, "sum")
    mean = total / jnp.where(present > 0, present, 1).astype(jnp.float64)
    centred = doubles - (mean[codes] if segments > 1 else mean)
    squares = _reduced(
        jnp.where(active, centred * centred, 0.0), codes, segments, "sum"
    )
    return (present, mean, squares)


def _halves_reduced(
    cut: jax.Array, codes: jax.Array, segments: int
) -> tuple[jax.Array, jax.Array]:
    """Return the totals of each cell's high and low 32 bits, summed apart."""
    high = jnp.right_shift(cut, 32)
    low = cut - jnp.left_shift(high, 32)
    return (
        _reduced(high, codes, segments, "sum"),
        _reduced(low, codes, segments, "sum"),
    )


def _extremum(  # noqa: PLR0913 -- the cells, where they count, and how to fold them
    held: jax.Array,
    active: jax.Array,
    present: jax.Array,
    codes: jax.Array,
    *,
    segments: int,
    kind: Literal["min", "max"],
    integral: bool,
) -> jax.Array:
    """Return the least or greatest cell per period, passing over NaN as Polars does.

    ``present`` is how many policies each period has in each partition, which
    the caller has already counted for the partial's own count.
    """
    if integral:
        fill = INT64_MAX if kind == "min" else INT64_MIN
        return _reduced(jnp.where(active, held, fill), codes, segments, kind)
    valid = active & ~jnp.isnan(held)
    fill_value = jnp.inf if kind == "min" else -jnp.inf
    extreme = _reduced(jnp.where(valid, held, fill_value), codes, segments, kind)
    numbers = _reduced(valid.astype(jnp.int64), codes, segments, "sum")
    return jnp.where((present > 0) & (numbers == 0), jnp.nan, extreme)


def _sketch_notes(folds: Sequence[Fold]) -> tuple[str, ...]:
    """Say, for each fold kept in a quantile sketch, how far it agrees with Polars.

    ``Quantile``, ``Median``, ``CTE`` and ``QuantileRank`` fold into the
    core's own DDSketch on both paths, so they are only as exact as the
    sketch is. The engine's per-policy values match Polars' within the
    agreement band, 1e-12 of the line's scale, but not always to the last
    bit, and a value on a bucket's edge can land in the next bucket and move
    the answer by about twice the sketch's accuracy. The agreement that
    holds is the sketch's, not the band's, and the record says so beside the
    number.
    """
    notes: list[str] = []
    for one in folds:
        accuracy = getattr(inner_of(one.aggregator), "relative_accuracy", None)
        if accuracy is None:
            continue
        notes.append(
            f"{one.alias}: folded through the core's quantile sketch (relative "
            f"accuracy {accuracy:g}), so it agrees with the Polars path within "
            "the sketch's accuracy rather than to the last digit"
        )
    return tuple(notes)


def _empty_book() -> EngineRefusal:
    """Return the refusal an aggregation over no policies takes.

    ``run_aggregated`` refuses an empty book on Polars before it starts, and
    this does the same: a total over no policies is a number nobody asked
    for, and a mean over none is not a number at all.
    """
    return EngineRefusal(
        RunReport(
            refusals=(
                Refusal(
                    group="inputs",
                    where=ENGINE_NAME,
                    count=0,
                    what="the book holds no policies, so there is nothing to fold",
                    move="hand the aggregation a book of at least one policy, as "
                    "run_aggregated asks",
                    clause=None,
                ),
            ),
            notes=(),
        )
    )


def aggregate(  # noqa: PLR0913 -- the door's three, and the bench's own two
    document: dict[str, Any],
    inputs: pl.DataFrame,
    aggregations: Sequence[Any],
    *,
    batch: int | None = None,
    depth: int | None = None,
    folded_only: bool = True,
) -> AggregatedResult:
    """Fold the document's final schema over the book into these aggregators.

    The same stages as ``run`` and in the same order -- inspection, the
    book's validation, host preparation, the batches, completion -- with the
    aggregators read against the artifact beside the tree, so every refusal
    that needs no book arrives in one report before the book is opened.

    **Each batch's program returns the columns folded and nothing else.**
    Every node is still traced and every check still carried, so what
    refuses still refuses; but a column no aggregator reads never leaves the
    card. Folding a best estimate and a cashflow term structure of level 4,
    two columns leave it where the final schema holds a hundred and
    twenty-eight (:meth:`ExecutionPlan.compile_for`).

    ``depth`` is how many batches are dispatched ahead of the one being
    folded -- the device's own where None: one on a card, nought on the CPU
    (:func:`~gaspatchio_jax.plan.depth_on`) -- and ``folded_only`` is whether
    each program returns only the columns folded or, as before, every
    final-schema column. Both are the engine's own choices, taken here only
    so the bench can measure what each is worth; ``JaxEngine.aggregate``
    takes neither.

    Raises:
        EngineRefusal: If the tree, an aggregator, the book, or a check the
            trace carried refuses the run. Nothing is returned.
        ValueError: If ``batch`` is not a positive number of policies, or
            ``depth`` is named and is neither 0 nor 1. Either is refused
            before the book is read.

    """
    if batch is not None and batch < 1:
        message = f"batch is a number of policies, at least one; got {batch}"
        raise ValueError(message)
    depth = checked_depth(depth)
    started = time.perf_counter()
    plan = ExecutionPlan.stage_inspect(document)
    folds, refusals = read_folds(plan, aggregations)
    tree = (*plan.tree_refusals, *refusals)
    if tree:
        raise EngineRefusal(RunReport(refusals=tree, notes=tuple(plan.notes)))
    if inputs.height == 0:
        raise _empty_book()
    prepared = plan.stage_prepare(plan.stage_validate_inputs(inputs))
    partitions = {
        one.by: partitions_of(prepared, one.by)
        for one in folds
        if one.by and one.partial is not None
    }
    folding = Folding(
        accumulators={one.alias: one.aggregator.create_accumulator() for one in folds},
        host=findings_of(prepared.flags),
    )
    queue = partial(queued_beside, folds=folds, folding=folding, partitions=partitions)
    returns = frozenset(one.node_id for one in folds) if folded_only else None
    folded(
        fed(plan, prepared, batch, depth=depth, returns=returns, on_dispatch=queue),
        prepared,
        folds,
        folding,
        partitions,
    )
    return completed(plan, prepared, folds, folding, started)


def completed(
    plan: ExecutionPlan,
    prepared: Prepared,
    folds: Sequence[Fold],
    folding: Folding,
    started: float,
) -> AggregatedResult:
    """Read every batch's findings together, and answer only if none refused.

    Completion as ``run`` has it, in the same order: the host's findings in
    front of every batch's, a refusal raised if any refuses, then a fault a
    fold met, and only then the totals. The stage every batch ends in, and
    where no batch's values may still be alive.

    Raises:
        EngineRefusal: If any check caught a cell outside its domain.
        Exception: The fault held while a batch was folded, where nothing
            refused.

    """
    found = merged_findings([*folding.host, *folding.findings])
    refused = [one.refusal() for one in found if one.refuses]
    if refused:
        raise EngineRefusal(RunReport(refusals=tuple(refused), notes=()))
    if folding.fault is not None:
        raise folding.fault
    notes = (
        *plan.notes,
        *_sketch_notes(folds),
        *(one.sentence() for one in found if not one.refuses),
    )
    identity = plan.manifest_of(prepared.inputs, {})
    return AggregatedResult(
        aggregations=extract_outputs(
            [one.alias for one in folds],
            [one.aggregator for one in folds],
            folding.accumulators,
        ),
        n_policies=prepared.inputs.rows,
        n_periods=folding.n_periods,
        batch_size=folding.largest,
        wall_time_s=time.perf_counter() - started,
        # The host's resident set says nothing about a card's memory, and a
        # figure that measured the wrong device would be worse than none.
        peak_rss_mb=None,
        produced_by=Producer(
            engine=ENGINE_NAME,
            versions=dict(identity.versions),
            graph_fingerprint=identity.graph_fingerprint,
            inputs_digest=identity.inputs_digest,
            notes=notes,
        ),
    )
