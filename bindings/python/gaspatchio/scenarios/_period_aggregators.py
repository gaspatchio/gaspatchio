# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Per-period (vector) aggregators sharing the Aggregator Protocol.
# ABOUTME: batch_reduce(frame, period) -> length-n_periods vector; merges pad-and-add.

"""Per-period vector aggregators.

These are first-class aggregators (same ``create/add/merge/extract`` Protocol as
``Sum``/``Mean``) with vector-valued state. The one new seam, ``batch_reduce``,
reduces a batch frame to a per-period vector via ``explode -> group_by(period)``;
it is axis-agnostic, so the same aggregator works over policy batches
(``run_aggregated``) and scenario batches (``for_each_scenario``).

**A null is a missing value, period by period, and never becomes a number.**
The rule the scalar aggregators follow, applied at each period: a null is
skipped where it is read -- in the within-scenario total and in the fold across
scenarios or policies alike -- and a period that saw nothing but nulls has no
answer. A vector of floats cannot hold ``None``, so the answer is a numpy
masked array (an ``ndarray``): that period is masked, ``.tolist()`` reads
``None`` there, a partitioned answer's tidy frame holds null, the audit record
writes null, and the data under the mask is NaN, so a plain ``np.asarray``
read meets NaN rather than a plausible ``0.0``. A vector with a value at every
period has no mask set and reads exactly as a plain array. ``PeriodCount``
counts the values it saw, so it answers ``0`` at such a period and is a plain
array. A NaN is a value the model computed and could not determine, and is
not masked.

**A per-period total of whole numbers is exact.** ``PeriodSum`` over an
integer column totals each period in ``Int128`` and carries the exact totals
as Python ints from batch to batch, so the answer is the same at every
``batch_size``. Summed in the column's own width, 2**62, 2**62 and 5 answered
9.2e18 one policy at a time and -9.2e18 two at a time. A period whose total
lies outside ``[-2**63, 2**63 - 1]`` is refused by its column, its exact total
and its period; one inside it answers the double nearest the exact total. On
the scenario axis each scenario's total at a period is taken the same way,
for every per-period kind, and refused naming the scenario as well.

**So is every per-period statistic read from totals.** ``PeriodMean`` carries
each period's exact total beside its count and answers the double nearest
their ratio; ``PeriodVariance`` and ``PeriodStd`` carry each period's exact
count, total and total of squares and read the variance once from them. Their
answers are the same at every ``batch_size``, where a total in the column's
own width wrapped -- 2**62 and 2**62 averaged 4.6e18 one policy a batch and
-4.6e18 two -- and moments in doubles moved with the batching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import polars as pl

from gaspatchio._dtypes import I64_MAX, I64_MIN
from gaspatchio.errors.formatting_errors import integer_total_refusal
from gaspatchio.scenarios._aggregators import (
    _BaseAggregator,
    _sum_or_null,
    _whole_moment_sums,
    _within_to_expr,
    nearest_root,
    scenario_aggregator,
    total_of_squares,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray


def _pad_add(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Element-wise add two vectors of possibly-unequal length (zero-pad shorter)."""
    n = max(a.shape[0], b.shape[0])
    out = np.zeros(n, dtype=np.float64)
    out[: a.shape[0]] += a
    out[: b.shape[0]] += b
    return out


def _pad_combine(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    op: Callable[[NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]],
    fill: float,
) -> NDArray[np.float64]:
    """Element-wise combine via ``op`` (np.minimum/np.maximum); ``fill`` pads the gap.

    A period present in only one operand keeps that operand's value (the other side
    is the identity ``fill``: +inf for min, -inf for max).
    """
    n = max(a.shape[0], b.shape[0])
    ap = np.full(n, fill, dtype=np.float64)
    bp = np.full(n, fill, dtype=np.float64)
    ap[: a.shape[0]] = a
    bp[: b.shape[0]] = b
    return op(ap, bp)


def _no_value() -> np.ma.MaskedArray:
    """Return the empty per-period vector a value-masked fold starts from."""
    return np.ma.MaskedArray(np.zeros(0, dtype=np.float64), mask=np.zeros(0, bool))


def _values_and_presence(
    vector: Any,  # noqa: ANN401 — a plain or masked vector of doubles
    length: int,
) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    """Return ``vector`` padded to ``length``, and where it holds a value.

    A plain array -- what an engine computing a partial on its own device
    hands over -- holds a value at every period it has; a masked one holds
    none where it is masked. A period past the vector's end holds none.
    """
    masked = np.ma.asarray(vector, dtype=np.float64)
    values = np.full(length, np.nan, dtype=np.float64)
    present = np.zeros(length, dtype=bool)
    values[: masked.shape[0]] = np.ma.getdata(masked)
    present[: masked.shape[0]] = ~np.ma.getmaskarray(masked)
    return values, present


def _masked_where_absent(
    values: NDArray[np.float64], present: NDArray[np.bool_]
) -> np.ma.MaskedArray:
    """Return ``values`` masked, with NaN under the mask, where ``present`` is False."""
    return np.ma.MaskedArray(np.where(present, values, np.nan), mask=~present)


def _combine_present(
    a: Any,  # noqa: ANN401 — a plain or masked vector of doubles
    b: Any,  # noqa: ANN401 — likewise
    op: Callable[[NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]],
) -> np.ma.MaskedArray:
    """Combine two per-period vectors with ``op`` where both hold a value.

    Where only one holds a value at a period, that value is the answer; where
    neither does, the period stays masked. Unequal lengths pad the shorter
    with periods holding no value, which is what the padding has always meant:
    a period present in only one operand keeps that operand's value.
    """
    n = max(np.shape(a)[0], np.shape(b)[0])
    av, ah = _values_and_presence(a, n)
    bv, bh = _values_and_presence(b, n)
    out = np.where(ah, av, bv)
    both = ah & bh
    out[both] = op(av[both], bv[both])
    return _masked_where_absent(out, ah | bh)


def _from_column(column: pl.Series) -> np.ma.MaskedArray:
    """Return a reduced per-period column as a vector masked where it is null."""
    present = column.is_not_null().to_numpy()
    values = column.cast(pl.Float64).fill_null(np.nan).to_numpy().astype(np.float64)
    return _masked_where_absent(values, present)


def holds_whole_numbers(dtype: pl.DataType | None) -> bool:
    """Say whether a per-period column holds whole numbers, not decimals or flags."""
    return isinstance(dtype, pl.List) and dtype.inner.is_integer()


def _whole_from_column(column: pl.Series) -> np.ma.MaskedArray:
    """Return a reduced per-period integer column as exact Python ints.

    A period that is null is masked, with nought under the mask; every other
    period holds its total as a Python int, which no width can wrap.
    """
    values = column.to_list()
    present = np.array([value is not None for value in values], dtype=bool)
    data = np.empty(len(values), dtype=object)
    data[:] = [0 if value is None else int(value) for value in values]
    return np.ma.MaskedArray(data, mask=~present)


def _is_whole(vector: Any) -> bool:  # noqa: ANN401 -- a plain or masked vector
    """Say whether a per-period vector holds exact whole-number totals."""
    return np.ma.asarray(vector).dtype == object


def _add_whole(a: Any, b: Any) -> np.ma.MaskedArray:  # noqa: ANN401 -- two exact vectors
    """Add two exact per-period vectors, period by period, as Python ints.

    A period present in only one keeps that one's total; a period in neither
    stays masked. Unequal lengths pad the shorter with absent periods.
    """
    n = max(np.shape(a)[0], np.shape(b)[0])
    data = np.empty(n, dtype=object)
    data[:] = [0] * n
    present = np.zeros(n, dtype=bool)
    for vector in (a, b):
        masked = np.ma.asarray(vector)
        held = ~np.ma.getmaskarray(masked)
        values = np.ma.getdata(masked)
        for index in np.flatnonzero(held):
            data[index] = data[index] + int(values[index])
        present[: held.shape[0]] |= held
    return np.ma.MaskedArray(data, mask=~present)


def _as_doubles(vector: Any) -> np.ma.MaskedArray:  # noqa: ANN401 -- an exact vector
    """Return an exact per-period vector as the nearest doubles, NaN under the mask."""
    masked = np.ma.asarray(vector)
    present = ~np.ma.getmaskarray(masked)
    values = np.array(
        [float(int(value)) for value in np.ma.getdata(masked)], dtype=np.float64
    )
    return _masked_where_absent(values, present)


def _pad_add_whole(a: Any, b: Any) -> NDArray[np.object_]:  # noqa: ANN401 -- two exact vectors
    """Add two unmasked vectors of exact totals by period; zero-pad the shorter."""
    n = max(np.shape(a)[0], np.shape(b)[0])
    out = np.zeros(n, dtype=object)
    out[: np.shape(a)[0]] += np.asarray(a, dtype=object)
    out[: np.shape(b)[0]] += np.asarray(b, dtype=object)
    return out


def _ratio(numerator: Any, denominator: Any) -> float:  # noqa: ANN401 -- two whole numbers
    """Return the double nearest an exact ratio of whole numbers, rounded once."""
    return int(numerator) / int(denominator)


def refuse_a_period_total_past_i64(
    totals: pl.DataFrame,
    column: str,
    *,
    period: str,
    scenario: str | None = None,
) -> None:
    """Refuse a per-period total of whole numbers that no ``i64`` holds.

    ``totals`` holds one total per row in ``column``, summed in ``Int128``,
    beside its period index and, on the scenario axis, its scenario.

    Raises:
        ValueError: If a total lies outside ``[-2**63, 2**63 - 1]``, naming
            the column, the exact total, the period and the scenario.

    """
    past = totals.filter((pl.col(column) < I64_MIN) | (pl.col(column) > I64_MAX)).sort(
        period
    )
    if not past.height:
        return
    row = past.row(0, named=True)
    where = f" at period {row[period]}"
    if scenario is not None:
        where = f" in scenario {row[scenario]!r}{where}"
    raise ValueError(integer_total_refusal(column, int(row[column]), where))


def _reduce_by_period(
    frame: pl.DataFrame, period: str, column: str, *aggs: pl.Expr
) -> pl.DataFrame:
    """Explode the ``(period, column)`` lists and reduce per period, sorted by period.

    An empty ``[]`` projection explodes to a single ``(null, null)`` row, which would
    sort FIRST and insert a phantom leading bucket that shifts every period by one.
    Dropping null periods removes that phantom; the period index is built from
    ``int_ranges(list.len())`` so it is never null for real data.
    """
    return (
        frame.lazy()
        .select(pl.col(period), pl.col(column))
        .explode([period, column])
        .filter(pl.col(period).is_not_null())
        .group_by(period)
        .agg(*aggs)
        .sort(period)
        .collect()
    )


def _reduce_by_period_over(
    frame: pl.DataFrame,
    period: str,
    column: str,
    by: tuple[str, ...],
    *aggs: pl.Expr,
) -> dict[tuple[Any, ...], pl.DataFrame]:
    """Partitioned per-period reduce — returns ``{partition_tuple: per-period frame}``.

    Like :func:`_reduce_by_period` but the partition column(s) ``by`` join the group key
    (``group_by([*by, period])``). The ``by`` columns are scalar-per-policy, so they
    ride the existing explode. Returns the reduced rows partitioned by ``by`` (key
    columns dropped), each sub-frame sorted by ``period`` — ready to feed
    ``_Partitioned``.
    """
    reduced = (
        frame.lazy()
        .select(*[pl.col(b) for b in by], pl.col(period), pl.col(column))
        .explode([period, column])
        .filter(pl.col(period).is_not_null())
        .group_by([*by, period])
        .agg(*aggs)
        .sort([*by, period])
        .collect()
    )
    return reduced.partition_by(*by, as_dict=True, include_key=False)


def _reduce_by_period_within(
    frame: pl.DataFrame,
    period: str,
    column: str,
    within_by: tuple[str, ...],
    *aggs: pl.Expr,
    within: str = "sum",
) -> pl.DataFrame:
    """Two-stage per-period reduce for the scenario axis (reduce ACROSS scenarios).

    Stage 1 collapses the inner axis (policies) by SUMMING ``column`` within each
    ``within_by`` group (``scenario_id``) per period, giving each scenario its
    per-period total. Stage 2 applies ``aggs`` ACROSS those per-scenario totals per
    period. So a ``Period*`` aggregator on the scenario axis computes its statistic
    across scenarios of each scenario's per-period total — mirroring the scalar
    aggregator convention (which groups by ``scenario_id`` first) — instead of
    reducing over every policy x scenario cell.

    ``within_by`` groups are disjoint across batches (every scenario appears in
    exactly one batch and sees every policy), so stage 1 fully reduces each scenario
    within its batch; the per-period partials then fold across batches correctly via
    the aggregator's own ``add_input``/``merge_accumulators``.

    Null periods (from an empty ``[]`` projection) are dropped exactly as in
    :func:`_reduce_by_period`, so no phantom leading bucket is inserted. Stage 1
    sums the column, so its output keeps the name ``column`` and the caller's
    ``aggs`` (written against ``pl.col(column)``) apply unchanged in stage 2.
    A scenario whose every value at a period is null totals null there, not
    ``0.0``, so stage 2 skips it as it skips any null. A scenario's total of
    whole numbers is exact, and refused by name past ``i64``
    (:func:`_scenario_totals`). ``within`` names stage 1's reduction where it
    is not the total: the largest policy per scenario and period is
    ``within="max"``.
    """
    stage1 = (
        frame.lazy()
        .select(*[pl.col(b) for b in within_by], pl.col(period), pl.col(column))
        .explode([period, column])
        .filter(pl.col(period).is_not_null())
    )
    totals = _scenario_totals(
        stage1,
        [*within_by, period],
        column,
        schema=frame.schema,
        period=period,
        within_by=within_by,
        within=within,
    )
    return totals.group_by(period).agg(*aggs).sort(period).collect()


def _scenario_totals(  # noqa: PLR0913 -- the cells, how they group, and what to name
    cells: pl.LazyFrame,
    keys: list[str],
    column: str,
    *,
    schema: pl.Schema,
    period: str,
    within_by: tuple[str, ...],
    within: str = "sum",
) -> pl.LazyFrame:
    """Total each scenario's cells per period, exactly where they are whole numbers.

    Summed in the column's own width, a scenario's total past ``i64`` wrapped:
    2**62, 2**62 and 5 totalled -9.2e18. A whole-number column is summed in
    ``Int128``, a total outside ``i64`` is refused naming its scenario and its
    period, and the totals, which then all fit, are handed on as ``Int64``.

    ``within`` other than ``"sum"`` reduces each scenario's cells by that
    statistic instead (``mean``, ``max``, ``min``, ``count``, ``first``,
    ``last``): a mean is a double; the others of whole numbers are whole and
    handed on as ``Int64``, as a total is.
    """
    if within != "sum":
        reduced = cells.group_by(keys).agg(_within_to_expr(column, within))
        if within == "mean":
            return reduced.with_columns(pl.col(column).cast(pl.Float64))
        if within == "count" or holds_whole_numbers(schema.get(column)):
            return reduced.with_columns(pl.col(column).cast(pl.Int64))
        return reduced
    if not holds_whole_numbers(schema.get(column)):
        return cells.group_by(keys).agg(_sum_or_null(column))
    totals = cells.group_by(keys).agg(_sum_or_null(column, whole=True)).collect()
    scenario = within_by[0] if within_by else None
    refuse_a_period_total_past_i64(totals, column, period=period, scenario=scenario)
    return totals.lazy().with_columns(pl.col(column).cast(pl.Int64))


def _reduce_by_period_over_within(  # noqa: PLR0913 -- the frame, its axes, the reduction
    frame: pl.DataFrame,
    period: str,
    column: str,
    by: tuple[str, ...],
    within_by: tuple[str, ...],
    *aggs: pl.Expr,
    within: str = "sum",
) -> dict[tuple[Any, ...], pl.DataFrame]:
    """Partitioned two-stage reduce for the scenario axis.

    :func:`_reduce_by_period_within` with a partition key: stage 1 sums
    ``column`` per (``by``, ``within_by``, period), so each partition sees
    per-scenario totals; stage 2 applies ``aggs`` across those totals per
    (``by``, period). Returns the same ``{partition_tuple: per-period frame}``
    shape as :func:`_reduce_by_period_over`.
    """
    stage1 = (
        frame.lazy()
        .select(
            *[pl.col(b) for b in by],
            *[pl.col(w) for w in within_by],
            pl.col(period),
            pl.col(column),
        )
        .explode([period, column])
        .filter(pl.col(period).is_not_null())
    )
    totals = _scenario_totals(
        stage1,
        [*by, *within_by, period],
        column,
        schema=frame.schema,
        period=period,
        within_by=within_by,
        within=within,
    )
    reduced = totals.group_by([*by, period]).agg(*aggs).sort([*by, period]).collect()
    return reduced.partition_by(*by, as_dict=True, include_key=False)


def _tidy_partitioned_vector(
    df: pl.DataFrame, *, by: tuple[str, ...], alias: str
) -> pl.DataFrame:
    """Explode a ``{by..., alias:<vector>}`` frame to tidy ``{by..., period, alias}``.

    A vector `.over()` output has one row per partition where the ``alias`` column
    holds a per-period array (numpy ndarray / Python list). This helper casts that
    cell value to ``List(Float64)``, annotates each element with its period index,
    then explodes to one row per (partition, period). Shared by both drivers'
    finalise (run_aggregated and for_each_scenario).
    """
    return (
        df.with_columns(pl.col(alias).cast(pl.List(pl.Float64)))
        .with_columns(pl.int_ranges(pl.col(alias).list.len()).alias("period"))
        .explode([alias, "period"])
        .select([*by, "period", alias])
    )


@dataclass(frozen=True)
class VectorAggregator(_BaseAggregator):
    """Aggregator with per-period vector state.

    Shares the Protocol; the driver dispatches on the presence of ``batch_reduce``.
    ``within_expr`` is intentionally unsupported (the vector path never calls it).

    Subclasses implement two seams:
    - ``_period_aggs()``: the Polars aggregation expressions used in the group_by step.
    - ``_assemble_partial(reduced)``: converts the period-sorted reduced frame into the
      partial value (e.g., numpy array or tuple of arrays).

    Both ``batch_reduce`` and ``batch_reduce_over`` are composed from these two seams.

    ``totals_whole_numbers`` marks a kind whose partial is built from totals:
    its whole-number column is reduced in ``Int128``
    (:meth:`_exact_where_whole`), so a period's totals are exact however many
    policies they sum, and ``_period_aggs`` is told the column holds whole
    numbers (``whole``) so that a kind needing more than one total can ask
    for them.
    """

    totals_whole_numbers: ClassVar[bool] = False

    def _exact_where_whole(self, frame: pl.DataFrame) -> pl.DataFrame:
        """Return ``frame`` with its totalled whole-number column in ``Int128``."""
        if not (
            self.totals_whole_numbers
            and holds_whole_numbers(frame.schema.get(self.column))
        ):
            return frame
        return frame.with_columns(pl.col(self.column).cast(pl.List(pl.Int128)))

    def _period_aggs(self, *, whole: bool = False) -> list[pl.Expr]:
        """Per-period aggregation expression(s) for this aggregator. Override.

        ``whole`` says the reduced column holds whole numbers.
        """
        raise NotImplementedError

    def _holds_whole_numbers(self, frame: pl.DataFrame) -> bool:
        """Say whether ``frame``'s column for this aggregator holds whole numbers."""
        return holds_whole_numbers(frame.schema.get(self.column))

    def _whole_within(self, frame: pl.DataFrame) -> bool:
        """Say whether each scenario's stage-1 reduction holds whole numbers.

        A mean of whole numbers is a double; every other ``within`` of whole
        numbers is whole.
        """
        return self._holds_whole_numbers(frame) and self.within != "mean"

    def _canonical(self, form: dict[str, Any]) -> dict[str, Any]:
        """Return ``form`` with ``within`` beside it where it is not the total.

        Left out at the default, so a plan that never wrote ``within`` keeps
        the canonical form, and the identity, it had.
        """
        if self.within == "sum":
            return form
        return {**form, "within": self.within}

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        """Turn a period-sorted reduced frame into this aggregator's partial.

        Override in subclasses.
        """
        raise NotImplementedError

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        return self._assemble_partial(
            _reduce_by_period(
                self._exact_where_whole(frame),
                period,
                self.column,
                *self._period_aggs(whole=self._holds_whole_numbers(frame)),
            )
        )

    def batch_reduce_over(
        self, frame: pl.DataFrame, period: str, by: tuple[str, ...]
    ) -> dict[tuple[Any, ...], Any]:
        """Partitioned reduce: ``{partition_tuple: partial}`` (one group_by pass)."""
        parts = _reduce_by_period_over(
            self._exact_where_whole(frame),
            period,
            self.column,
            by,
            *self._period_aggs(whole=self._holds_whole_numbers(frame)),
        )
        return {key: self._assemble_partial(sub) for key, sub in parts.items()}

    def batch_reduce_within(
        self, frame: pl.DataFrame, period: str, within_by: tuple[str, ...]
    ) -> Any:  # noqa: ANN401
        """Reduce ACROSS ``within_by`` groups per period after summing within each.

        Stage 1 sums ``column`` within each ``within_by`` group (``scenario_id``)
        per period; stage 2 applies this aggregator's per-period statistic across
        those per-group totals. Used on the scenario axis so ``Period*`` reduces
        across scenarios of each scenario's per-period total, not over every
        policy x scenario cell. See :func:`_reduce_by_period_within`.
        """
        return self._assemble_partial(
            _reduce_by_period_within(
                self._exact_where_whole(frame),
                period,
                self.column,
                within_by,
                *self._period_aggs(whole=self._whole_within(frame)),
                within=self.within,
            )
        )

    def batch_reduce_over_within(
        self,
        frame: pl.DataFrame,
        period: str,
        by: tuple[str, ...],
        within_by: tuple[str, ...],
    ) -> dict[tuple[Any, ...], Any]:
        """Partitioned two-stage reduce (scenario axis): ``{partition: partial}``.

        Per ``by`` partition, the statistic reduces ACROSS ``within_by``
        (scenario) totals per period — the partitioned counterpart of
        :meth:`batch_reduce_within`.
        """
        parts = _reduce_by_period_over_within(
            self._exact_where_whole(frame),
            period,
            self.column,
            by,
            within_by,
            *self._period_aggs(whole=self._whole_within(frame)),
            within=self.within,
        )
        return {key: self._assemble_partial(sub) for key, sub in parts.items()}

    def within_expr(self) -> pl.Expr:
        """Not supported — vector aggregators reduce via batch_reduce()."""
        msg = "VectorAggregator reduces via batch_reduce(), not within_expr()."
        raise NotImplementedError(msg)


@scenario_aggregator("PeriodSum")
@dataclass(frozen=True)
class PeriodSum(VectorAggregator):
    """Per-period portfolio total: sum across the batched axis at each period index.

    Nulls are skipped; a period that saw nothing but nulls is masked (``None``),
    not ``0.0``.

    **Whole numbers are totalled exactly.** An integer column is summed per
    period in ``Int128`` and the state carries each period's exact total as a
    Python int, so the answer is the same at every ``batch_size``. A period
    whose total lies outside ``[-2**63, 2**63 - 1]`` is refused by name, with
    its period, when the answer is read out; every other period answers the
    double nearest its exact total.
    """

    totals_whole_numbers: ClassVar[bool] = True

    def _period_aggs(self, *, whole: bool = False) -> list[pl.Expr]:  # noqa: ARG002 -- an Int128 column totals exactly as it is
        return [_sum_or_null(self.column)]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        totals = reduced[self.column]
        if totals.dtype.is_integer():
            return _whole_from_column(totals)
        return _from_column(totals)

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return _no_value()

    def _add(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        """Add two per-period totals, exactly where both are whole numbers."""
        whole_a = _is_whole(a) or np.shape(a)[0] == 0
        whole_b = _is_whole(b) or np.shape(b)[0] == 0
        if (_is_whole(a) or _is_whole(b)) and whole_a and whole_b:
            return _add_whole(a, b)
        doubles = [_as_doubles(v) if _is_whole(v) else v for v in (a, b)]
        return _combine_present(doubles[0], doubles[1], np.add)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return self._add(state, value)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return self._add(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        if not _is_whole(state):
            return state
        masked = np.ma.asarray(state)
        values = np.ma.getdata(masked)
        for index in np.flatnonzero(~np.ma.getmaskarray(masked)):
            total = int(values[index])
            if not I64_MIN <= total <= I64_MAX:
                where = f" at period {int(index)}"
                raise ValueError(integer_total_refusal(self.column, total, where))
        return _as_doubles(state)

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical({"kind": "PeriodSum", "column": self.column})


@scenario_aggregator("PeriodCount")
@dataclass(frozen=True)
class PeriodCount(VectorAggregator):
    """Per-period count of contributing (non-null) values across the batched axis.

    A null is not a value, so a period that saw nothing but nulls counts ``0``;
    on the scenario axis a scenario whose period holds only nulls is not
    counted. The answer is a plain array: a count of nothing is ``0``.
    """

    def _period_aggs(self, *, whole: bool = False) -> list[pl.Expr]:  # noqa: ARG002 -- a count is a count
        return [pl.col(self.column).count()]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return reduced[self.column].to_numpy().astype(np.float64)

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return np.zeros(0, dtype=np.float64)

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _pad_add(state, np.asarray(value, dtype=np.float64))

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _pad_add(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical({"kind": "PeriodCount", "column": self.column})


@dataclass(frozen=True)
class _PeriodExtremum(VectorAggregator):
    """Shared min/max logic.

    Subclasses override ``_reduce_expr`` and ``_combine``.
    """

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return _no_value()

    def _reduce_expr(self, col: str) -> pl.Expr:
        """Return the Polars aggregation expression for this extremum type."""
        raise NotImplementedError

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        """Pad-combine two accumulators using the appropriate extremum operation."""
        raise NotImplementedError

    def _period_aggs(self, *, whole: bool = False) -> list[pl.Expr]:  # noqa: ARG002 -- an extremum is one of the values
        return [self._reduce_expr(self.column)]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        return _from_column(reduced[self.column])

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return self._combine(state, value)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return self._combine(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return state


@scenario_aggregator("PeriodMin")
@dataclass(frozen=True)
class PeriodMin(_PeriodExtremum):
    """Per-period minimum across the batched axis.

    Nulls are skipped; a period that saw nothing but nulls is masked (``None``).
    A batch with no value at a period leaves the other batches' answer there.
    """

    def _reduce_expr(self, col: str) -> pl.Expr:
        return pl.col(col).min()

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _combine_present(a, b, np.minimum)

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical({"kind": "PeriodMin", "column": self.column})


@scenario_aggregator("PeriodMax")
@dataclass(frozen=True)
class PeriodMax(_PeriodExtremum):
    """Per-period maximum across the batched axis.

    Nulls are skipped; a period that saw nothing but nulls is masked (``None``).
    A batch with no value at a period leaves the other batches' answer there.
    """

    def _reduce_expr(self, col: str) -> pl.Expr:
        return pl.col(col).max()

    def _combine(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _combine_present(a, b, np.maximum)

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical({"kind": "PeriodMax", "column": self.column})


@scenario_aggregator("PeriodMean")
@dataclass(frozen=True)
class PeriodMean(VectorAggregator):
    """Per-period mean across the batched axis.

    State is ``(sum_vec, count_vec)`` — both exactly additive — so the result is
    batch-size-invariant (no Welford needed; mean is extracted as sum/count).
    Nulls are skipped; a period with a count of nought is masked (``None``).

    **Whole numbers are averaged exactly.** An integer column's totals are
    taken in ``Int128`` and carried as Python ints, as ``PeriodSum`` carries
    them, and each period answers the double nearest its exact total over its
    count. Totalled in the column's own width, 2**62 and 2**62 averaged 4.6e18
    one policy a batch and -4.6e18 two. A mean of ``i64`` values lies between
    them, so none is refused.
    """

    totals_whole_numbers: ClassVar[bool] = True

    def _period_aggs(self, *, whole: bool = False) -> list[pl.Expr]:  # noqa: ARG002 -- an Int128 column totals exactly as it is
        return [
            pl.col(self.column).sum().alias("s"),
            pl.col(self.column).count().alias("c"),
        ]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        totals = reduced["s"]
        return (
            _whole_from_column(totals)
            if totals.dtype.is_integer()
            else totals.to_numpy().astype(np.float64),
            reduced["c"].to_numpy().astype(np.float64),
        )

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return (np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64))

    def _add(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        """Add two ``(sum_vec, count_vec)`` partials, exactly where both are whole."""
        (sa, ca), (sb, cb) = a, b
        if (_is_whole(sa) or _is_whole(sb)) and all(
            _is_whole(v) or np.shape(v)[0] == 0 for v in (sa, sb)
        ):
            return (_add_whole(sa, sb), _pad_add(ca, cb))
        doubles = [
            np.ma.filled(_as_doubles(v), 0.0) if _is_whole(v) else v for v in (sa, sb)
        ]
        return (_pad_add(doubles[0], doubles[1]), _pad_add(ca, cb))

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return self._add(state, value)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return self._add(a, b)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        s, c = state
        out = np.full(c.shape[0], np.nan, dtype=np.float64)
        nonzero = c > 0
        if _is_whole(s):
            totals = np.ma.getdata(np.ma.asarray(s))
            for index in np.flatnonzero(nonzero):
                out[index] = _ratio(totals[index], c[index])
        else:
            out[nonzero] = s[nonzero] / c[nonzero]
        return _masked_where_absent(out, nonzero)

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical({"kind": "PeriodMean", "column": self.column})


_MIN_SAMPLE_VAR: int = 2  # ddof=1 requires at least 2 observations per period


def _welford_merge_vec(a: Any, b: Any) -> Any:  # noqa: ANN401
    """Elementwise Welford-Chan merge of two ``(n, mean, m2)`` vector states.

    Padding with zeros is the identity: a period present in only one operand keeps
    that operand's moments (the other side has n=0).
    """
    (na, ma, m2a), (nb, mb, m2b) = a, b
    length = max(na.shape[0], nb.shape[0])

    def _fit(x: Any) -> Any:  # noqa: ANN401
        out = np.zeros(length, dtype=np.float64)
        out[: x.shape[0]] = x
        return out

    na, ma, m2a = _fit(na), _fit(ma), _fit(m2a)
    nb, mb, m2b = _fit(nb), _fit(mb), _fit(m2b)
    # A period with n==0 in one operand carries mean=NaN (Polars mean() of an empty
    # group). It contributes nothing, but NaN*0 = NaN would still poison `delta`, so
    # replace those means with the identity 0.0 before combining.
    ma = np.where(na > 0, ma, 0.0)
    mb = np.where(nb > 0, mb, 0.0)
    n = na + nb
    safe = n > 0
    delta = mb - ma
    ratio_b = np.divide(nb, n, out=np.zeros(length), where=safe)
    ratio_ab = np.divide(na * nb, n, out=np.zeros(length), where=safe)
    mean = ma + delta * ratio_b
    m2 = m2a + m2b + delta * delta * ratio_ab
    return (n, mean, m2)


def _exact_moments_vec(state: Any) -> bool:  # noqa: ANN401 -- a moment partial
    """Say whether a per-period moment state carries exact ``(n, s1, s2)`` totals."""
    return _is_whole(state[1])


def _moments_vec_as_doubles(state: Any) -> Any:  # noqa: ANN401 -- a moment partial
    """Return a per-period moment state as Welford's ``(n, mean, m2)`` doubles."""
    if not _exact_moments_vec(state):
        return state
    n, s1, s2 = state
    mean = np.zeros(n.shape[0], dtype=np.float64)
    m2 = np.zeros(n.shape[0], dtype=np.float64)
    for index in np.flatnonzero(n > 0):
        count = int(n[index])
        total = int(s1[index])
        mean[index] = _ratio(total, count)
        m2[index] = _ratio(count * int(s2[index]) - total * total, count)
    return (n, mean, m2)


def _merge_moments_vec(a: Any, b: Any) -> Any:  # noqa: ANN401
    """Merge two per-period moment states, exactly where both hold whole numbers."""
    if not (_exact_moments_vec(a) or _exact_moments_vec(b)):
        return _welford_merge_vec(a, b)
    if all(_exact_moments_vec(v) or np.shape(v[0])[0] == 0 for v in (a, b)):
        return (
            _pad_add(a[0], b[0]),
            _pad_add_whole(a[1], b[1]),
            _pad_add_whole(a[2], b[2]),
        )
    return _welford_merge_vec(_moments_vec_as_doubles(a), _moments_vec_as_doubles(b))


@dataclass(frozen=True)
class _PeriodMoment(VectorAggregator):
    """Shared per-period moment state for Variance/Std.

    Over decimals the state is Welford's ``(n, mean, m2)``. Over whole numbers
    it is ``(n, s1, s2)``: each period's count, exact total and exact total of
    squares, taken in ``Int128`` (:func:`_whole_moment_sums`) and carried as
    Python ints, so the variance is read once from exact figures at every
    ``batch_size``. Folded as doubles, 2**53 + 1, 2**53 + 2, 2**53 + 3 and
    2**53 + 5 -- variance 2.9166... -- answered 5.22, 6.67 or 3.67 by batch.
    """

    totals_whole_numbers: ClassVar[bool] = True

    def _period_aggs(self, *, whole: bool = False) -> list[pl.Expr]:
        if whole:
            return _whole_moment_sums(self.column)
        return [
            pl.col(self.column).count().alias("n"),
            pl.col(self.column).mean().alias("mean"),
            (pl.col(self.column).var(ddof=0) * pl.col(self.column).count()).alias("m2"),
        ]

    def _assemble_partial(self, reduced: pl.DataFrame) -> Any:  # noqa: ANN401
        if "s1" in reduced.columns:
            s1 = np.empty(reduced.height, dtype=object)
            s1[:] = [int(total) for total in reduced["s1"].to_list()]
            s2 = np.empty(reduced.height, dtype=object)
            s2[:] = [
                total_of_squares(hh, hl, ll)
                for hh, hl, ll in zip(
                    reduced["hh"].to_list(),
                    reduced["hl"].to_list(),
                    reduced["ll"].to_list(),
                    strict=True,
                )
            ]
            return (reduced["n"].to_numpy().astype(np.float64), s1, s2)
        # var(ddof=0) is null at count==1; nan_to_num -> 0.0 (correct: m2=0 for n=1).
        return (
            reduced["n"].to_numpy().astype(np.float64),
            reduced["mean"].to_numpy().astype(np.float64),
            np.nan_to_num(reduced["m2"].to_numpy().astype(np.float64)),
        )

    def create_accumulator(self) -> Any:  # noqa: ANN401
        z = np.zeros(0, dtype=np.float64)
        return (z, z.copy(), z.copy())

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _merge_moments_vec(state, value)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _merge_moments_vec(a, b)

    def _spread(self, state: Any, *, root: bool) -> Any:  # noqa: ANN401
        """Return each period's sample variance, or its root, masked where no value."""
        n = state[0]
        out = np.full(n.shape[0], np.nan, dtype=np.float64)
        ok = n >= _MIN_SAMPLE_VAR
        if _exact_moments_vec(state):
            _n, s1, s2 = state
            for index in np.flatnonzero(ok):
                count = int(n[index])
                total = int(s1[index])
                spread = count * int(s2[index]) - total * total
                ways = count * (count - 1)
                out[index] = (
                    nearest_root(spread, ways) if root else _ratio(spread, ways)
                )
        else:
            _n, _mean, m2 = state
            variance = m2[ok] / (n[ok] - 1)
            out[ok] = np.sqrt(variance) if root else variance
        return np.ma.MaskedArray(out, mask=n == 0)


@scenario_aggregator("PeriodVariance")
@dataclass(frozen=True)
class PeriodVariance(_PeriodMoment):
    """Per-period sample variance (ddof=1) across the batched axis.

    Nulls are skipped. A period with no value is masked (``None``); one with a
    single value is NaN, because a sample variance of one observation is
    undefined.
    """

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return self._spread(state, root=False)

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical({"kind": "PeriodVariance", "column": self.column})


@scenario_aggregator("PeriodStd")
@dataclass(frozen=True)
class PeriodStd(_PeriodMoment):
    """Per-period sample standard deviation across the batched axis.

    Nulls are skipped. A period with no value is masked (``None``); one with a
    single value is NaN, as for :class:`PeriodVariance`.
    """

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return self._spread(state, root=True)

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical({"kind": "PeriodStd", "column": self.column})


__all__ = [
    "PeriodCount",
    "PeriodMax",
    "PeriodMean",
    "PeriodMin",
    "PeriodStd",
    "PeriodSum",
    "PeriodVariance",
    "VectorAggregator",
    "_pad_add",
    "_pad_combine",
]
