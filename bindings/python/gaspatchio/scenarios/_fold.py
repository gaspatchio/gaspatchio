# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared folds and output shaping for the two aggregation axes.

The scenario axis folds each batch in the run's own order, one scenario at a
time, so a statistic across scenarios is the same bits at every batch size
and on every run (:func:`fold_scenario_batch`). The policy axis folds batch
partials, so it is the same bits at one batch size and agrees across sizes to
floating-point reassociation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, cast

import numpy as np
import polars as pl

from gaspatchio.scenarios._aggregators import (
    _AGGREGATOR_REGISTRY,
    _sum_or_null,
    _total_and_count,
    exact_mean,
)
from gaspatchio.scenarios._metric import Aggregator, _Partitioned
from gaspatchio.scenarios._period_aggregators import _tidy_partitioned_vector

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio.scenarios._for_each import ScenarioID
    from gaspatchio.scenarios._period_aggregators import VectorAggregator


def _inner(agg: Aggregator | _Partitioned) -> Aggregator:
    """Return the partition-blind aggregator."""
    return agg.inner if isinstance(agg, _Partitioned) else agg


def refuse_a_sum_over_a_wide_integer(
    frame: pl.DataFrame,
    aggregations: Sequence[Aggregator | _Partitioned],
    *,
    within_reduces: bool = False,
) -> None:
    """Refuse a sum over a column holding a whole number past ``i64``.

    A fold sums a batch's column in the width the column holds, so a
    ``UInt64`` policy number of 7 beside one of 2**64 - 1 summed to 6 in one
    batch and to 1.8446744073709552e19 across two -- a total that moved with
    ``batch_size`` and was wrong at both. Section 10 reads such a column as
    the ``Int64`` its values fit, and keeps the width only where one does not;
    there a sum would wrap, so it is refused by name, as arithmetic on the
    column is. A ``Sum``, a ``PeriodSum``, and on the scenario axis any
    statistic reduced ``within="sum"``, sum the column; the rest do not.

    Raises:
        ValueError: If a summing aggregator names a column holding a value
            outside ``[-2**63, 2**63 - 1]``.

    """
    from gaspatchio._dtypes import wider_than_i64_at  # noqa: PLC0415 -- kept local
    from gaspatchio.errors.formatting_errors import (  # noqa: PLC0415 -- as above
        wide_read_refusal,
    )

    for agg in aggregations:
        inner = _inner(agg)
        column = getattr(inner, "column", None)
        if not isinstance(column, str) or column not in frame.columns:
            continue
        sums = type(inner).__name__ in {"Sum", "PeriodSum"} or (
            within_reduces and getattr(inner, "within", None) == "sum"
        )
        depth = wider_than_i64_at(frame.schema[column])
        if not sums or depth is None:
            continue
        values = frame.get_column(column)
        for _ in range(depth):
            values = values.explode()
        if values.cast(pl.Int64, strict=False).null_count() > values.null_count():
            raise ValueError(wide_read_refusal(column, "sum"))


def refuse_a_policy_fold_over_periods(
    schema: pl.Schema,
    aggregations: Sequence[Aggregator | _Partitioned],
    *,
    within_reduces: bool = False,
) -> None:
    """Refuse an aggregator of one value per policy named on a per-period column.

    ``Sum("net_cf")`` over a column holding one value per period reached
    Polars' grouped ``sum`` and failed there, in Polars' words ("`sum`
    operation not supported for dtype `list[f64]`"), mid-run; ``within="max"``
    answered null for every scenario without a word. The kind that folds a
    per-period column is its ``Period`` form, and the refusal names it before
    anything is folded.

    ``within_reduces`` is the scenario axis, where each scenario's policies
    are first reduced by ``within``: there ``within="count"`` counts the
    policies, which a per-period column answers as well as any, and is left
    to run. The policy axis folds the column itself and has no such step.

    Raises:
        ValueError: If an aggregator of one value per policy names a column
            the batch holds as one value per period.

    """
    for agg in aggregations:
        inner = _inner(agg)
        if hasattr(inner, "batch_reduce"):
            continue
        if getattr(inner, "within_expr_override", None) is not None:
            continue
        if within_reduces and getattr(inner, "within", None) == "count":
            continue
        column = getattr(inner, "column", None)
        if not isinstance(column, str) or not isinstance(schema.get(column), pl.List):
            continue
        kind = type(inner).__name__
        period_kind = f"Period{kind}"
        move = (
            f"Fold it period by period with {period_kind}({column!r}), or fold a "
            "per-policy column"
            if period_kind in _AGGREGATOR_REGISTRY
            else "Fold a per-policy column"
        )
        msg = (
            f"{kind}({column!r}) folds one value per policy, and {column!r} "
            "holds one value per period, so there is no one number per policy to "
            f"fold. {move} -- a present value, or the value at one period, "
            f"such as af.{column}.list.get(0)."
        )
        raise ValueError(msg)


def refuse_a_period_fold_over_policies(
    schema: pl.Schema,
    aggregations: Sequence[Aggregator | _Partitioned],
) -> None:
    """Refuse a per-period aggregator named on a column of one value per policy.

    ``PeriodSum("n_pols")`` over a column holding one value per policy reached
    Polars' ``list.len`` and failed there, in Polars' words ("expected List
    data type for list operation"); the JAX engine refused it by name. A
    column held per period is folded whatever its numbers are -- whole
    numbers, decimals or flags -- and whether or not any other column of the
    model holds decimals.

    Raises:
        ValueError: If a per-period aggregator names a column the batch holds
            as one value per policy.

    """
    for agg in aggregations:
        inner = _inner(agg)
        if not hasattr(inner, "batch_reduce"):
            continue
        column = getattr(inner, "column", None)
        held = schema.get(column) if isinstance(column, str) else None
        if held is None or isinstance(held, pl.List):
            continue
        kind = type(inner).__name__
        plain = kind.removeprefix("Period")
        msg = (
            f"{kind}({column!r}) folds one value per period, and {column!r} "
            f"holds one value per policy. Fold a per-period column with {kind}, "
            f"or fold this one with {plain}({column!r})."
        )
        raise ValueError(msg)


def _fold_vector(
    frame: pl.DataFrame,
    agg: Aggregator | _Partitioned,
    accumulators: dict[str, Any],
    alias: str,
    *,
    within: tuple[str, ...] = (),
) -> None:
    """Reduce periods using this column's lengths and the caller's explicit axis.

    Scenario folds first total policies within each scenario. A partition naming
    that axis already selects a scenario, so it reduces policies directly instead.
    Policy folds pass no within-axis, even if their data has a scenario_id column.
    """
    vec = cast("VectorAggregator", _inner(agg))
    period = "__period"
    frame = frame.with_columns(
        pl.int_ranges(pl.col(vec.column).list.len()).alias(period)
    )
    if isinstance(agg, _Partitioned):
        reduce_within = within and not all(key in agg.by for key in within)
        if within and not reduce_within:
            _refuse_within_over_the_scenario(vec, agg.by)
        parts = (
            vec.batch_reduce_over_within(frame, period, agg.by, within)
            if reduce_within
            else vec.batch_reduce_over(frame, period, agg.by)
        )
        for key, partial in parts.items():
            accumulators[alias] = agg.add_input(accumulators[alias], (key, partial))
        return
    partial = (
        vec.batch_reduce_within(frame, period, within)
        if within
        else vec.batch_reduce(frame, period)
    )
    accumulators[alias] = agg.add_input(accumulators[alias], partial)


def _refuse_within_over_the_scenario(vec: Any, by: Sequence[str]) -> None:  # noqa: ANN401 -- a vector aggregator
    """Refuse ``within=`` on a per-period statistic partitioned by the scenario.

    A partition naming the scenario axis holds one scenario, whose policies
    the statistic is taken over directly; nothing is left for ``within=`` to
    reduce first, so it would be dropped.

    Raises:
        ValueError: ``vec`` asks for a ``within`` other than the total.

    """
    within = getattr(vec, "within", "sum")
    if within == "sum":
        return
    msg = (
        f"{type(vec).__name__}({vec.column!r}, within={within!r}) is "
        f"partitioned over {', '.join(by)}, which names one scenario per "
        "partition, so the statistic is taken over that scenario's policies "
        "and within= would be dropped. Leave within= out, or partition by "
        "other columns and let within= reduce each scenario's policies first."
    )
    raise ValueError(msg)


def _extract_outputs(
    aliases: Sequence[str],
    aggregations: Sequence[Aggregator | _Partitioned],
    accumulators: dict[str, Any],
) -> dict[str, Any]:
    """Extract ordinary outputs and tidy partitioned vectors for either driver."""
    outputs: dict[str, Any] = {}
    for alias, agg in zip(aliases, aggregations, strict=True):
        raw = agg.extract_output(accumulators[alias])
        if isinstance(agg, _Partitioned) and hasattr(agg.inner, "batch_reduce"):
            raw = _tidy_partitioned_vector(raw, by=agg.by, alias=alias)
        outputs[alias] = raw
    return outputs


# The columns the fold adds to a batch to put its rows in one order: the
# scenario's position in the run, the row's position in the batch, and the
# group a row's sorted run of keys falls in.
_POS: Final[str] = "__fold_position"
_ROW: Final[str] = "__fold_row"
_GROUP: Final[str] = "__fold_group"
_PERIOD: Final[str] = "__fold_period"


def fold_scenario_batch(
    proj_eager: pl.DataFrame,
    *,
    aliases: list[str],
    aggregations: Sequence[Aggregator | _Partitioned],
    accumulators: dict[str, Any],
    order: Sequence[ScenarioID],
) -> None:
    """Fold a batch's scenarios into ``accumulators`` in run order (in place).

    **A fold answers the same bits however the run was batched, and on every
    run.** Floating-point addition is not associative, so two things used to
    move the last bits of a cross-scenario statistic. The fold took a batch's
    scenarios in the order a ``group_by`` returned them, which Polars does not
    fix, so a ``Mean`` across scenarios differed between identical runs. And
    each scenario's total over its policies was a grouped sum over the whole
    batch frame, which Polars reassociates by the frame it is handed, so the
    same scenario summed its policies to different bits at batch size 1 and 10.

    Both are now fixed by construction, in one vectorised pass per batch. The
    batch is sorted by each row's scenario position in ``order`` (the run's
    own order), its partition keys and its row, so every group's rows are one
    contiguous slice in the order they arrived -- the same sequence whichever
    batch the scenario sits in -- and each group is reduced as that slice.
    The reduced rows are then folded in that sorted order, so the
    accumulators see one sequence of inputs at every batch size. A per-period
    statistic folds each scenario's per-period total as one observation, in
    the same order. Probe and remainder batches share these reductions.
    """
    refuse_a_policy_fold_over_periods(
        proj_eager.schema, aggregations, within_reduces=True
    )
    refuse_a_period_fold_over_policies(proj_eager.schema, aggregations)
    refuse_a_sum_over_a_wide_integer(proj_eager, aggregations, within_reduces=True)
    position = {sid: index for index, sid in enumerate(order)}
    frame = (
        proj_eager.with_row_index(_ROW)
        .with_columns(
            pl.col("scenario_id")
            .replace_strict(position, return_dtype=pl.UInt32)
            .alias(_POS)
        )
        .sort([_POS, _ROW])
    )
    groups: dict[tuple[str, ...], list[tuple[str, Aggregator | _Partitioned]]] = {}
    for alias, agg in zip(aliases, aggregations, strict=True):
        inner = _inner(agg)
        if not hasattr(inner, "batch_reduce"):
            signature = agg.by if isinstance(agg, _Partitioned) else ()
            groups.setdefault(signature, []).append((alias, agg))
        elif _folds_by_observation(inner):
            _fold_vector_in_order(frame, agg, accumulators, alias)
        else:
            # A sketch counts its inputs into buckets, so the order they
            # arrive in cannot move what it answers.
            _fold_vector(proj_eager, agg, accumulators, alias, within=("scenario_id",))

    for partition_signature, group_members in groups.items():
        # scenario_id is always implicit in the group key; if the user
        # explicitly partitioned by it via .over("scenario_id"), don't add it
        # twice (polars rejects duplicate group_by keys).
        extra_keys = [k for k in partition_signature if k != "scenario_id"]
        within_exprs = [
            _within_exactly(_inner(member_agg), proj_eager.schema).alias(member_alias)
            for member_alias, member_agg in group_members
        ]
        reduced = (
            _in_slices(frame, [_POS, *extra_keys], [_ROW])
            .group_by(_GROUP, maintain_order=True)
            .agg(
                pl.first("scenario_id"),
                *[pl.first(key) for key in extra_keys],
                *within_exprs,
            )
        )
        refuse_a_scenario_total_past_i64(reduced, group_members, proj_eager.schema)
        reduced = _with_exact_means(reduced, group_members, proj_eager.schema)
        _fold_reduced(reduced, partition_signature, group_members, accumulators)


def _reduces_whole_numbers(inner: Aggregator, schema: pl.Schema, within: str) -> bool:
    """Say whether ``within`` reduces a scenario's policies over an integer column."""
    column = getattr(inner, "column", None)
    return (
        getattr(inner, "within_expr_override", None) is None
        and getattr(inner, "within", None) == within
        and isinstance(column, str)
        and column in schema
        and schema[column].is_integer()
    )


def _sums_whole_numbers(inner: Aggregator, schema: pl.Schema) -> bool:
    """Say whether ``within`` sums a scenario's policies over an integer column."""
    return _reduces_whole_numbers(inner, schema, "sum")


def _within_exactly(inner: Aggregator, schema: pl.Schema) -> pl.Expr:
    """Return the within reduction, summing or averaging an integer column exactly.

    Polars sums an ``Int64`` group in ``Int64`` and wraps a total past it:
    2**62, 2**62 and 5 summed to -9.2e18 for one scenario. Summed in
    ``Int128`` the scenario's total is exact, and the fold below refuses it
    where no ``i64`` holds it. A mean is that exact total beside the count,
    divided once by :func:`_with_exact_means`; Polars' own mean added the
    values as doubles. Every other reduction is the aggregator's own: a
    least, greatest, first or last value is one the column holds, and a
    count is exact.
    """
    column = cast("str", getattr(inner, "column", None))
    if _reduces_whole_numbers(inner, schema, "mean"):
        return _total_and_count(column)
    if not _sums_whole_numbers(inner, schema):
        return inner.within_expr()
    return _sum_or_null(column, whole=True)


def _with_exact_means(
    reduced: pl.DataFrame,
    members: Sequence[tuple[str, Aggregator | _Partitioned]],
    schema: pl.Schema,
) -> pl.DataFrame:
    """Return ``reduced`` with each whole-number mean read from its total and count.

    The reduced frame holds one row per scenario and partition, so the
    division is done row by row in Python, where one ``int`` over another is
    correctly rounded: 2**63 - 1, -2**63 and 5 average to 4/3.
    """
    for alias, agg in members:
        if not _reduces_whole_numbers(_inner(agg), schema, "mean"):
            continue
        means = [exact_mean(parts) for parts in reduced.get_column(alias).to_list()]
        reduced = reduced.with_columns(pl.Series(alias, means, dtype=pl.Float64))
    return reduced


def refuse_a_scenario_total_past_i64(
    reduced: pl.DataFrame,
    members: Sequence[tuple[str, Aggregator | _Partitioned]],
    schema: pl.Schema,
) -> None:
    """Refuse a scenario's total of an integer column that no ``i64`` holds.

    Raises:
        ValueError: If a scenario's policies sum, by ``within="sum"``, to a
            whole number outside ``[-2**63, 2**63 - 1]``, naming the column,
            the exact total and the scenario.

    """
    from gaspatchio._dtypes import I64_MAX, I64_MIN  # noqa: PLC0415 -- kept local
    from gaspatchio.errors.formatting_errors import (  # noqa: PLC0415 -- as above
        integer_total_refusal,
    )

    for alias, agg in members:
        inner = _inner(agg)
        if not _sums_whole_numbers(inner, schema):
            continue
        past = reduced.filter(
            (pl.col(alias) < I64_MIN) | (pl.col(alias) > I64_MAX)
        ).select("scenario_id", alias)
        if past.height:
            scenario, total = past.row(0)
            column = cast("str", getattr(inner, "column", None))
            where = f" in scenario {scenario!r}"
            raise ValueError(integer_total_refusal(column, int(total), where))


def _in_slices(frame: pl.DataFrame, keys: list[str], then: list[str]) -> pl.DataFrame:
    """Return ``frame`` sorted by ``keys`` then ``then``, each run of keys one group.

    The group column is sorted and marked so, which makes every group a
    contiguous slice that a reduction takes in row order: measured on one
    scenario's rows, a grouped float ``sum`` over a hash-gathered group
    answered different last bits depending on the batch frame, where the same
    rows reduced as a slice answered the same bits as a ``select`` over the
    scenario's own rows.
    """
    ordered = frame.sort([*keys, *then], nulls_last=True, maintain_order=True)
    changed = pl.any_horizontal(
        [pl.col(key).ne_missing(pl.col(key).shift(1)) for key in keys]
    ).fill_null(value=True)
    return ordered.with_columns(
        changed.cast(pl.UInt32).cum_sum().set_sorted().alias(_GROUP)
    )


def _folds_by_observation(vec: Any) -> bool:  # noqa: ANN401 -- a vector aggregator
    """Return whether a per-period kind is assembled from ``_period_aggs`` partials."""
    from gaspatchio.scenarios._period_aggregators import (  # noqa: PLC0415 -- cycle
        VectorAggregator,
    )

    kind = type(vec)
    return (
        kind._period_aggs is not VectorAggregator._period_aggs  # noqa: SLF001
        and kind._assemble_partial is not VectorAggregator._assemble_partial  # noqa: SLF001
    )


def _fold_vector_in_order(
    frame: pl.DataFrame,
    agg: Aggregator | _Partitioned,
    accumulators: dict[str, Any],
    alias: str,
) -> None:
    """Fold a per-period statistic one scenario at a time, in run order.

    Stage 1 totals the column per scenario, partition and period, each total
    reduced as one slice of the scenario's rows. Across scenarios, a
    statistic takes those totals as observations, so each scenario folds as
    one: its partial is the statistic over its own totals, added to the
    accumulator in the run's order. A partition naming the scenario axis
    already selects one scenario, so it reduces the scenario's cells
    directly, as it always did.

    A scenario's total of whole numbers at a period is summed in ``Int128``
    and refused, naming the scenario and the period, where no ``i64`` holds
    it; a ``PeriodSum`` reduces its whole numbers in ``Int128`` throughout.
    """
    from gaspatchio.scenarios._period_aggregators import (  # noqa: PLC0415 -- cycle
        PeriodSum,
        holds_whole_numbers,
        refuse_a_period_total_past_i64,
    )

    vec = cast("Any", _inner(agg))
    by = tuple(agg.by) if isinstance(agg, _Partitioned) else ()
    if "scenario_id" in by:
        _refuse_within_over_the_scenario(vec, by)
    extra = [key for key in by if key != "scenario_id"]
    whole = holds_whole_numbers(frame.schema.get(vec.column))
    within = vec.within
    cells = (
        frame.select(_POS, _ROW, "scenario_id", *extra, vec.column)
        .with_columns(pl.int_ranges(pl.col(vec.column).list.len()).alias(_PERIOD))
        .explode([_PERIOD, vec.column])
        .filter(pl.col(_PERIOD).is_not_null())
    )
    keys = [_POS, *extra, _PERIOD]
    observations = cells
    if "scenario_id" not in by and within != "sum":
        observations, whole = _within_observations(
            cells, keys, vec.column, within, whole=whole
        )
    elif "scenario_id" not in by:
        observations = (
            _in_slices(cells, keys, [_ROW])
            .group_by(_GROUP, maintain_order=True)
            .agg(
                *[pl.first(key) for key in [*keys, "scenario_id"]],
                _sum_or_null(vec.column, whole=whole),
            )
        )
        if whole:
            refuse_a_period_total_past_i64(
                observations, vec.column, period=_PERIOD, scenario="scenario_id"
            )
            observations = observations.with_columns(pl.col(vec.column).cast(pl.Int64))
    if whole and vec.totals_whole_numbers:
        observations = observations.with_columns(pl.col(vec.column).cast(pl.Int128))
    partials = (
        _in_slices(observations, keys, [])
        .group_by(_GROUP, maintain_order=True)
        .agg(
            *[pl.first(key) for key in [*keys, "scenario_id"]],
            *vec._period_aggs(whole=whole),  # noqa: SLF001
        )
    )
    # A partition naming the scenario totals each scenario's own policies;
    # only a total answers a figure that could lie past i64.
    if whole and isinstance(vec, PeriodSum) and "scenario_id" in by:
        refuse_a_period_total_past_i64(
            partials, vec.column, period=_PERIOD, scenario="scenario_id"
        )
    # The partials are in (position, partition, period) order, so each
    # scenario's -- and each partition's -- is one run of rows. Built-in kinds
    # assemble row by row, so one assembly over the whole frame is cut at the
    # runs; a kind whose partial is not row-shaped assembles each run's slice.
    runs = _in_slices(partials, [_POS, *extra], [])
    group = runs[_GROUP].to_numpy()
    starts = np.flatnonzero(np.r_[True, group[1:] != group[:-1]])
    ends = np.r_[starts[1:], group.shape[0]]
    whole = vec._assemble_partial(runs)  # noqa: SLF001
    row_shaped = _row_shaped(whole, runs.height)
    keys_at = runs.select(*by)[starts].rows() if by else []
    for index, (start, end) in enumerate(zip(starts, ends, strict=True)):
        partial = (
            _cut(whole, int(start), int(end))
            if row_shaped
            else vec._assemble_partial(runs.slice(int(start), int(end - start)))  # noqa: SLF001
        )
        value = (keys_at[index], partial) if isinstance(agg, _Partitioned) else partial
        accumulators[alias] = agg.add_input(accumulators[alias], value)


def _within_observations(
    cells: pl.DataFrame, keys: list[str], column: str, within: str, *, whole: bool
) -> tuple[pl.DataFrame, bool]:
    """Reduce each scenario's cells per period by ``within``, as one slice each.

    The observation a per-period statistic takes across scenarios is then
    that reduction -- the largest policy, the mean policy -- not the total.
    A mean is a double; any other reduction of whole numbers is whole and
    handed on as ``Int64``. Returns the observations and whether they hold
    whole numbers.
    """
    from gaspatchio.scenarios._aggregators import (  # noqa: PLC0415 -- cycle
        _within_to_expr,
    )

    observations = (
        _in_slices(cells, keys, [_ROW])
        .group_by(_GROUP, maintain_order=True)
        .agg(
            *[pl.first(key) for key in [*keys, "scenario_id"]],
            _within_to_expr(column, within),
        )
    )
    if within == "mean":
        return observations.with_columns(pl.col(column).cast(pl.Float64)), False
    if within == "count" or whole:
        observations = observations.with_columns(pl.col(column).cast(pl.Int64))
    return observations, whole


def _row_shaped(partial: Any, rows: int) -> bool:  # noqa: ANN401 -- an array or a tuple of them
    """Return whether ``partial`` holds one entry per row, as an array or a tuple."""
    parts = partial if isinstance(partial, tuple) else (partial,)
    return all(isinstance(p, np.ndarray) and p.shape[:1] == (rows,) for p in parts)


def _cut(partial: Any, start: int, end: int) -> Any:  # noqa: ANN401 -- as above
    """Return the rows ``start:end`` of a row-shaped partial, keeping its shape."""
    if isinstance(partial, tuple):
        return tuple(p[start:end] for p in partial)
    return partial[start:end]


def _fold_reduced(
    reduced: pl.DataFrame,
    partition_signature: tuple[str, ...],
    group_members: list[tuple[str, Aggregator | _Partitioned]],
    accumulators: dict[str, Any],
) -> None:
    """Feed scenario totals with the requested identity and partition payloads."""
    # Pre-resolve column positions for fast positional row iteration.
    col_positions = {name: i for i, name in enumerate(reduced.columns)}
    sid_pos = col_positions["scenario_id"]
    partition_positions = [col_positions[k] for k in partition_signature]
    alias_positions = [
        (
            member_alias,
            member_agg,
            col_positions[member_alias],
            getattr(_inner(member_agg), "requires_scenario_id", False),
        )
        for member_alias, member_agg in group_members
    ]

    for row in reduced.iter_rows():
        scenario_id = row[sid_pos]
        partition_key = tuple(row[p] for p in partition_positions)
        for member_alias, member_agg, value_pos, needs_sid in alias_positions:
            value = row[value_pos]
            payload = (scenario_id, value) if needs_sid else value
            if isinstance(member_agg, _Partitioned):
                payload = (partition_key, payload)
            accumulators[member_alias] = member_agg.add_input(
                accumulators[member_alias],
                payload,
            )
