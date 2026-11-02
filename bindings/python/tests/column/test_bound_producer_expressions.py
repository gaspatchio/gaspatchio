# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every framework producer's expression answers as the column it would become.

``Table.lookup``, ``MortalityTable.at``, ``Curve.discount_factor`` /
``spot_rate`` and ``CompiledRollforward.expr_for`` / ``increment_for`` hand
back a ``ProxyAwareExpr``: a real ``pl.Expr``, so raw Polars interop works.
Its methods used to be Polars' own, so a method chained straight on meant
something other than the same method on the column the expression would be
assigned to -- a ``cum_sum`` that failed at collect on a per-period lookup
and ran down the model points on a per-policy one, a ``shift`` that moved
one policy's timeline onto the next. Each is now bound to the frame it was
read from (or borrowed from its operands), and answers as that frame's
column would.

An expression with no frame in sight -- a ``Schedule.*_expr`` read, a lookup
keyed only by literals -- is a Polars expression until it meets one, as
``pl.col(...)`` is, and keeps Polars' own methods.
"""

from __future__ import annotations

import gc
from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward, when
from gaspatchio.assumptions import Table
from gaspatchio.column._generated_proxy import _GeneratedProxySurface
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.curves import Curve
from gaspatchio.frame._row_operations import _row_operations
from gaspatchio.frame.lowering.methods import (
    ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE,
    DOWN_THE_ROWS,
)
from gaspatchio.mortality import MortalityTable
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Callable


def _frame() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "age": [40, 41],
                "av0": [100.0, 200.0],
                "prem": [[10.0] * 3, [20.0] * 3],
            }
        )
    )
    af = af.projection.set(
        start_date=date(2026, 1, 31), n_periods=3, frequency="annual"
    )
    af.attained_age = af.age + af.month // 12
    af.t = af.projection.t_years()
    return af


def _table() -> Table:
    return Table(
        name="bound_producer_q",
        source=pl.DataFrame(
            {"age": list(range(30, 60)), "rate": [0.01 * i for i in range(30)]}
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _mortality() -> MortalityTable:
    return MortalityTable(
        table=_table(), age_basis="age_last_birthday", structure="aggregate"
    )


def _curve() -> Curve:
    return Curve.from_zero_rates(tenors=[1.0, 5.0], rates=[0.03, 0.04])


def _rollforward(af: ActuarialFrame) -> object:
    rf = af.projection.rollforward(states={"av": af["av0"]}, track_increments=True)
    rf["av"].add(af["prem"], label="premium")
    return compile_rollforward(rf)


# Each producer, read off a frame, with a declared operation that is the
# column's meaning on its per-period answer.
_PRODUCERS: list[tuple[str, Callable[[ActuarialFrame], object], str]] = [
    ("Table.lookup", lambda af: _table().lookup(age=af.attained_age), "cum_sum"),
    ("Table.lookup", lambda af: _table().lookup(age=af.attained_age), "list.get"),
    ("MortalityTable.at", lambda af: _mortality().at(age=af.attained_age), "cum_sum"),
    ("Curve.discount_factor", lambda af: _curve().discount_factor(af.t), "cum_prod"),
    ("Curve.spot_rate", lambda af: _curve().spot_rate(af.t), "list.get"),
    ("expr_for", lambda af: _rollforward(af).expr_for("av"), "cum_sum"),
    ("increment_for", lambda af: _rollforward(af).increment_for("premium"), "list.sum"),
    ("expr_for", lambda af: _rollforward(af).expr_for("av"), "list.get"),
]


def _apply(receiver: object, operation: str) -> object:
    if operation == "list.get":
        return receiver.list.get(0)  # type: ignore[attr-defined]
    if operation == "list.sum":
        return receiver.list.sum()  # type: ignore[attr-defined]
    return getattr(receiver, operation)()


@pytest.mark.parametrize(("name", "producer", "operation"), _PRODUCERS)
def test_a_chained_call_matches_the_assigned_column(
    name: str, producer: Callable[[ActuarialFrame], object], operation: str
) -> None:
    """Written on one line or two, the same formula is one calculation."""
    chained = _frame()
    chained.result = _apply(producer(chained), operation)

    assigned = _frame()
    assigned.stored = producer(assigned)
    assigned.result = _apply(assigned.stored, operation)

    assert (
        chained.collect()["result"].to_list() == assigned.collect()["result"].to_list()
    ), name


def _past_the_escape(message: str, name: str) -> str:
    """Return what a refusal says after it names where the escape goes.

    On a column the escape is the column's own; on a table, curve or
    schedule read it is the stored read's, because the escape on the read
    itself would hide the read in a Polars expression, which the frame
    refuses. What follows -- the axis, the per-period spelling -- is one text.
    """
    for door in (
        f"write .polars_native().{name}.",
        f"_read.polars_native().{name} on that column.",
    ):
        if door in message:
            return message.split(door, 1)[1]
    raise AssertionError(message)


@pytest.mark.parametrize(
    ("name", "producer"),
    [
        ("Table.lookup", lambda af: _table().lookup(age=af.attained_age)),
        ("Curve.discount_factor", lambda af: _curve().discount_factor(af.t)),
        ("expr_for", lambda af: _rollforward(af).expr_for("av")),
    ],
)
def test_shift_is_refused_on_a_per_period_producer_as_on_a_column(
    name: str, producer: Callable[[ActuarialFrame], object]
) -> None:
    """Polars' ``shift`` moved one policy's timeline onto the next, silently."""
    af = _frame()
    af.stored = producer(af)
    with pytest.raises(AttributeError) as on_column:
        af.stored.shift  # noqa: B018 -- the refusal is the attribute read
    with pytest.raises(AttributeError) as on_producer:
        producer(af).shift(1)  # type: ignore[attr-defined]
    assert _past_the_escape(str(on_producer.value), "shift") == _past_the_escape(
        str(on_column.value), "shift"
    ), name
    if name != "expr_for":
        assert "Store the read as its own column first" in str(on_producer.value)
    assert "list.eval" in str(on_producer.value)


def test_a_per_policy_lookup_refuses_a_fold_down_the_model_points() -> None:
    """``lookup(age=af.age).cum_sum()`` summed one policy's rate into the next.

    On the column, ``cum_sum`` of a per-policy value is refused and the row
    fold is the explicit ``polars_native()`` door; the lookup now says the
    same instead of quietly running down the book.
    """
    af = _frame()
    af.stored = _table().lookup(age=af.age)
    with pytest.raises(TypeError) as on_column:
        af.stored.cum_sum()
    with pytest.raises(TypeError) as on_lookup:
        _table().lookup(age=af.age).cum_sum()
    assert "needs a list column" in str(on_lookup.value)
    assert str(on_lookup.value) == str(on_column.value)


# The arguments each row-reading name needs to build a plan on its own.
_ROW_ARGUMENTS: dict[str, tuple[tuple[object, ...], dict[str, object]]] = {
    "cumulative_eval": ((pl.element().first(),), {}),
    "dot": ((pl.lit(1.0),), {}),
    "ewm_mean": ((), {"alpha": 0.5}),
    "ewm_std": ((), {"alpha": 0.5}),
    "ewm_var": ((), {"alpha": 0.5}),
    "filter": ((pl.lit(value=True),), {}),
    "where": ((pl.lit(value=True),), {}),
    "gather": (([0],), {}),
    "get": ((0,), {}),
    "head": ((1,), {}),
    "tail": ((1,), {}),
    "limit": ((1,), {}),
    "slice": ((0, 1), {}),
    "sort_by": ((pl.col("policy_id"),), {}),
    "interpolate_by": ((pl.col("policy_id"),), {}),
    "append": ((pl.lit(0.0),), {}),
    "over": (("policy_id",), {}),
    "extend_constant": ((0.0, 1), {}),
    "gather_every": ((2,), {}),
    "index_of": ((0.0,), {}),
    "max_by": ((pl.col("policy_id"),), {}),
    "min_by": ((pl.col("policy_id"),), {}),
    "top_k_by": ((pl.col("policy_id"), 1), {}),
    "bottom_k_by": ((pl.col("policy_id"), 1), {}),
    "ewm_mean_by": ((pl.col("policy_id"),), {"half_life": "1i"}),
    "qcut": ((2,), {}),
    "quantile": ((0.5,), {}),
    "reshape": (((-1,),), {}),
    "search_sorted": ((0.0,), {}),
    "rolling_quantile": ((), {"quantile": 0.5, "window_size": 1}),
    "rolling_quantile_by": (
        (pl.col("policy_id"),),
        {"quantile": 0.5, "window_size": "1i"},
    ),
}


def _row_call(name: str) -> tuple[tuple[object, ...], dict[str, object]]:
    if name in _ROW_ARGUMENTS:
        return _ROW_ARGUMENTS[name]
    if name.startswith("rolling_") and name.endswith("_by"):
        return (pl.col("policy_id"),), {"window_size": "1i"}
    if name.startswith("rolling_"):
        return (), {"window_size": 1}
    return (), {}


@pytest.mark.parametrize("name", sorted(DOWN_THE_ROWS))
def test_a_per_policy_lookup_refuses_a_polars_name_that_reads_the_rows(
    name: str,
) -> None:
    """``lookup(age=af.age).sum()`` handed every policy the book's total.

    Polars' own method, inherited because the lookup is a ``pl.Expr``, ran
    down the model points; the row guard passes a per-policy operand, and
    the same formula over two lines -- assign, then ``.sum()`` -- was
    refused. Each name now answers as it does on the column.
    """
    af = _frame()
    af.stored = _table().lookup(age=af.age)
    with pytest.raises(AttributeError) as on_column:
        getattr(af.stored, name)
    args, kwargs = _row_call(name)
    with pytest.raises(AttributeError) as on_lookup:
        getattr(_table().lookup(age=af.age), name)(*args, **kwargs)
    assert _past_the_escape(str(on_lookup.value), name) == _past_the_escape(
        str(on_column.value), name
    )
    assert "Store the read as its own column first" in str(on_lookup.value)
    assert "runs down the model points" in str(on_lookup.value)
    assert f"af.<column>_read.polars_native().{name}" in str(on_lookup.value)


# The cross-row names wave 3 found still answering a policy from the rest of
# the book once sum, mean and max were held back: on a bound per-policy
# lookup each of these answered silently, and policy 1's value moved with
# which other policies shared the file and in what order.
_FOUND_AFTER_THE_FOLDS = (
    "product",
    "std",
    "var",
    "quantile",
    "mode",
    "unique",
    "arg_min",
    "arg_sort",
    "top_k_by",
    "bottom_k",
    "max_by",
    "qcut",
    "sample",
    "shuffle",
    "skew",
    "kurtosis",
    "entropy",
    "approx_n_unique",
    "is_sorted",
)


@pytest.mark.parametrize("name", _FOUND_AFTER_THE_FOLDS)
def test_a_per_policy_lookup_refuses_a_statistic_or_pick_across_the_book(
    name: str,
) -> None:
    """``lookup(age=af.age).std()`` answered policy 1 from the other policies.

    With rates 0.01, 0.02 and 0.03 on three policies, policy 1's ``std`` was
    0.01 in the book and null alone, its ``shuffle`` whichever rate the
    shuffle dealt it. Each is refused at the method, as on the column.
    """
    af = _frame()
    args, kwargs = _row_call(name)
    with pytest.raises(AttributeError, match="runs down the model points") as refused:
        getattr(_table().lookup(age=af.age), name)(*args, **kwargs)
    assert f".polars_native().{name}" in str(refused.value)


def test_every_name_the_row_guard_reads_is_held_back() -> None:
    """The set is the measurement: no Polars name the guard reads is left out.

    Each public ``pl.Expr`` method outside the declared vocabulary and the
    five axis names is applied, as Polars' own, to a column; every one whose
    plan the row guard reads as a row operation must be one a bound
    producer answers as its column does.
    """
    declared = {n for n in vars(_GeneratedProxySurface) if not n.startswith("_")}
    unreadable = {"deserialize", "from_json", "register_plugin", "inspect", "pipe"}
    unreadable |= {"map_batches", "map_elements", "rolling_map"}  # Python functions
    read = set()
    for name in dir(pl.Expr):
        if name.startswith("_") or name in declared | unreadable:
            continue
        if name in ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE:
            continue
        if isinstance(getattr(pl.Expr, name), property):
            continue
        args, kwargs = _row_call(name)
        try:
            expr = getattr(pl.col("rate"), name)(*args, **kwargs)
        except (TypeError, ValueError, pl.exceptions.PolarsError):
            continue  # a call this table holds no arguments for
        if isinstance(expr, pl.Expr) and list(_row_operations(expr)):
            read.add(name)

    assert read == set(DOWN_THE_ROWS)


def test_a_per_policy_total_no_longer_changes_with_the_book() -> None:
    """The issue's numbers: policy 1 read 0.06 in a book of three, 0.01 alone."""
    for ages in ([40, 41, 42], [40]):
        af = ActuarialFrame(
            pl.DataFrame({"policy_id": list(range(1, len(ages) + 1)), "age": ages})
        )
        af = af.projection.set(
            start_date=date(2026, 1, 31), n_periods=3, frequency="annual"
        )
        for fold in ("sum", "mean", "min", "max"):
            with pytest.raises(AttributeError, match=rf"\.list\.{fold}\(\)"):
                getattr(_table().lookup(age=af.age), fold)()


def test_a_per_period_lookup_names_the_per_period_fold() -> None:
    """On a per-period value the fold the author meant is the list namespace's."""
    af = _frame()
    with pytest.raises(AttributeError, match=r"write \.list\.sum\(\)") as raised:
        _table().lookup(age=af.attained_age).sum()
    assert "runs down the model points" not in str(raised.value)

    af.pv = _table().lookup(age=af.attained_age).list.sum()
    assert af.collect()["pv"].to_list() == pytest.approx([0.46, 0.50])


def test_the_escape_still_folds_across_the_model_points() -> None:
    """A figure over the book is portfolio work, and the door to it stays open.

    The read is stored first: a lookup inside an escape would be recorded by
    Polars' text, which names no table, so the escape opens on its column.
    """
    af = _frame()
    af.rate = _table().lookup(age=af.age)
    af.book_rate = af.rate.polars_native().sum()
    assert af.collect()["book_rate"].to_list() == pytest.approx([0.21, 0.21])


def test_an_unbound_lookup_keeps_polars_folds() -> None:
    """No frame among the operands: ``sum`` is Polars' own, as on ``pl.col``."""
    expr = _table().lookup(age=40).sum()
    assert pl.select(expr).item() == pytest.approx(0.1)


@pytest.mark.parametrize("name", sorted(DOWN_THE_ROWS))
def test_each_name_held_back_is_a_row_operation_the_guard_reads(name: str) -> None:
    """Membership is measured, not chosen: the row guard reads each as one.

    Each is a Polars method the declared vocabulary does not hold, and not
    one of the five the escape refuses as well.
    """
    declared = {n for n in vars(_GeneratedProxySurface) if not n.startswith("_")}
    assert name not in declared
    assert name not in ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE
    args, kwargs = _row_call(name)
    expr = getattr(pl.col("rate"), name)(*args, **kwargs)
    assert [method for method, _ in _row_operations(expr)], name


def test_a_comparison_on_a_per_period_lookup_reads_each_period() -> None:
    """Polars could not compare a list with a number; the column can."""
    af = _frame()
    af.high = _table().lookup(age=af.attained_age) > 0.115
    af.stored = _table().lookup(age=af.attained_age)
    af.high_stored = af.stored > 0.115
    out = af.collect()
    assert out["high"].to_list() == out["high_stored"].to_list()
    assert out["high"].to_list() == [[0.0, 0.0, 1.0, 1.0], [0.0, 1.0, 1.0, 1.0]]


def test_a_declared_method_answer_is_still_a_polars_expression() -> None:
    """Chained answers stay ``pl.Expr``, so ``.alias`` and raw Polars work."""
    af = _frame()
    rounded = _table().lookup(age=af.age).round(2)
    assert isinstance(rounded, ProxyAwareExpr)
    assert isinstance(rounded, pl.Expr)
    af = af.with_columns(rounded.alias("q"))
    assert af.collect()["q"].to_list() == [0.1, 0.11]


def test_a_rollforward_built_without_the_accessor_borrows_its_states_frame() -> None:
    """``RollforwardBuilder`` used directly binds to the frame its states read."""
    from gaspatchio.rollforward._builder import RollforwardBuilder

    af = _frame()
    rf = RollforwardBuilder(
        states={"av": af["av0"]},
        schedule=Schedule.from_calendar_grid(
            start_date=date(2026, 1, 31), n_periods=3, frequency="1Y"
        ),
    )
    rf["av"].add(af["prem"], label="premium")
    af.av_so_far = compile_rollforward(rf).expr_for("av").cum_sum()
    assert af.collect()["av_so_far"].to_list() == [
        [110.0, 230.0, 360.0],
        [220.0, 460.0, 720.0],
    ]


def test_a_compiled_rollforward_does_not_keep_its_frame_alive() -> None:
    """The binding is weak: compiled rollforwards outlive the run in a registry."""
    import weakref

    af = _frame()
    compiled = _rollforward(af)
    frame = weakref.ref(af)
    del af
    gc.collect()
    assert frame() is None
    # Unbound now, and a Polars expression again.
    assert "_parent" not in compiled.expr_for("av").__dict__  # type: ignore[attr-defined]


def test_a_schedule_expression_keeps_polars_meaning_on_a_raw_frame() -> None:
    """No frame in sight: ``Schedule.*_expr`` is the raw Polars door."""
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31), n_periods=4, frequency="1M"
    )
    frame = pl.DataFrame({"id": ["P1"]}).lazy()
    out = frame.with_columns(
        months=sched.is_in_force_expr().list.sum(),
    ).collect()
    assert out["months"].to_list() == [4]


def test_a_lookup_keyed_only_by_literals_keeps_polars_meaning() -> None:
    """No frame among the operands, so nothing to answer as."""
    expr = _table().lookup(age=40)
    assert "_parent" not in expr.__dict__
    assert pl.select(expr.round(2)).item() == pytest.approx(0.1)


# --- unary operators keep the node and the frame ---------------------------


def test_negation_keeps_the_node_and_the_frame() -> None:
    """``-t_years()`` was a nodeless, unbound expression; a chain after it broke."""
    af = _frame()
    negated = -af.projection.t_years()
    assert negated.__dict__.get("_node") is not None
    assert negated.__dict__.get("_parent") is af
    af.back = negated.cum_sum()
    assert af.collect()["back"][0].to_list() == [0.0, -1.0, -3.0, -6.0]


def test_abs_keeps_the_node_and_the_frame() -> None:
    af = _frame()
    absolute = abs(_table().lookup(age=af.attained_age) * -1)
    assert absolute.__dict__.get("_node") is not None
    assert absolute.__dict__.get("_parent") is af
    af.first = absolute.list.get(0)
    assert af.collect()["first"].to_list() == pytest.approx([0.1, 0.11])


def test_invert_negates_each_period_of_a_per_period_mask() -> None:
    """``~anniversary_mask()`` was refused by Polars as a ``not`` on a list."""
    af = _frame()
    af.inverted = ~af.projection.anniversary_mask()
    af.stored = af.projection.anniversary_mask()
    af.inverted_stored = ~af.stored
    out = af.collect()
    assert out["inverted"].to_list() == out["inverted_stored"].to_list()


def test_an_unbound_negation_keeps_its_node() -> None:
    """With no frame, Polars' value stands and the node is still recorded."""
    expr = -_table().lookup(age=40)
    assert expr.__dict__.get("_node") is not None
    assert pl.select(expr).item() == pytest.approx(-0.1)


# --- mask kind: dispatch is the same however the mask was written ----------

_MASK_OPERATIONS: list[tuple[str, Callable[[ActuarialFrame, object], object]]] = [
    ("invert", lambda _af, mask: ~mask),
    ("and", lambda af, mask: mask & (af.t > 1)),
    ("or", lambda af, mask: (af.t > 1) | mask),
    ("times a column", lambda af, mask: mask * af.av0),
    ("when", lambda af, mask: when(mask).then(af.av0).otherwise(0.0)),
]


@pytest.mark.parametrize("per_policy", [False, True])
@pytest.mark.parametrize(("name", "operation"), _MASK_OPERATIONS)
def test_a_mask_dispatches_the_same_written_inline_or_stored(
    name: str,
    operation: Callable[[ActuarialFrame, object], object],
    *,
    per_policy: bool,
) -> None:
    """A shared grid's mask reads kind ``value`` and dispatches as a mask.

    The kind label is read in one place (``_is_boolean_operand``), which
    falls back to the dtype; nothing dispatches on it. What a user meets is
    the operation, and that is the same inline and stored, on a shared and
    a per-policy grid.
    """

    def frame() -> ActuarialFrame:
        af = ActuarialFrame(pl.DataFrame({"av0": [1.0, 2.0], "years": [3, 3]}))
        if per_policy:
            af = af.projection.set(
                valuation_date=date(2026, 1, 1),
                until="term_years",
                until_value="years",
                frequency="annual",
                per_policy=True,
            )
        else:
            af = af.projection.set(
                start_date=date(2026, 1, 31), n_periods=3, frequency="annual"
            )
        af.t = af.projection.year_fractions().cum_sum()
        return af

    inline = frame()
    inline.result = operation(inline, inline.projection.anniversary_mask())
    stored = frame()
    stored.mask = stored.projection.anniversary_mask()
    stored.result = operation(stored, stored.mask)
    assert (
        inline.collect()["result"].to_list() == stored.collect()["result"].to_list()
    ), name


def test_a_list_method_on_a_per_policy_column_names_the_real_cause() -> None:
    """It said the arguments did not match, when the receiver has no periods."""
    af = ActuarialFrame({"age": [40, 41]})
    with pytest.raises(TypeError) as refused:
        af.age.list.get(0)
    message = str(refused.value)
    assert "holds one value per policy" in message
    assert "arguments supplied do not match" not in message
    assert "polars_native" in message


def test_a_comparison_says_it_can_answer_with_a_predicate() -> None:
    """Annotated as what it returns: a per-period comparison is a predicate."""
    from gaspatchio.column.condition_expression import ConditionExpression

    for name in ("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"):
        returned = getattr(ProxyAwareExpr, name).__annotations__["return"]
        assert "ConditionExpression" in returned, name
    af = _frame()
    assert isinstance(_table().lookup(age=af.attained_age) > 0.1, ConditionExpression)
