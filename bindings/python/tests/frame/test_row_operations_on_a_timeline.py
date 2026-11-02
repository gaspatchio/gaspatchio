# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A Polars row operation over a per-period column, assigned to a timeline frame.

On a frame with a projection timeline the rows are policies. A plain Polars
expression that reads neighbouring rows over a per-period column --
``pl.col("reserve").shift(1)``, a forward fill, a ``reverse`` -- moved
values between policies and came back the right shape with no error. The
framework's own surface already refused these (a column, a bound producer
expression, the ``polars_native()`` escape); assignment now refuses the plain
expression the same way, naming the per-period ``list.eval`` form.

This is the period-method guard read the other way round: that one refuses
a period method on a column not known to be per-period on a timeline frame
(``previous_period`` on a per-policy column); this one refuses a row
operation on a column not known to be per-policy there. Both leave a frame
without a timeline alone.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame._row_operations import _row_operations
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Callable


def _timeline() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "age": [40, 41],
                "reserve": [[1.0, None, 3.0], [4.0, 5.0, None]],
            }
        )
    )
    return af.projection.set(
        start_date=date(2026, 1, 31), n_periods=3, frequency="annual"
    )


_ROW_OPERATIONS: list[tuple[str, Callable[[pl.Expr], pl.Expr]]] = [
    ("shift", lambda column: column.shift(1)),
    ("shift", lambda column: column.shift(1, fill_value=0.0)),
    ("diff", lambda column: column.diff()),
    ("forward_fill", lambda column: column.forward_fill()),
    ("backward_fill", lambda column: column.backward_fill()),
    ("fill_null", lambda column: column.fill_null(strategy="mean")),
    ("interpolate", lambda column: column.interpolate()),
    ("cum_sum", lambda column: column.cum_sum()),
    ("cum_prod", lambda column: column.cum_prod()),
    ("cum_max", lambda column: column.cum_max()),
    ("rank", lambda column: column.rank()),
    ("reverse", lambda column: column.reverse()),
    ("first", lambda column: column.first()),
    ("sort", lambda column: column.sort()),
    ("cumulative_eval", lambda column: column.cumulative_eval(pl.element().first())),
]


@pytest.mark.parametrize(("method", "operation"), _ROW_OPERATIONS)
def test_a_row_operation_over_a_per_period_column_is_refused_at_assignment(
    method: str, operation: Callable[[pl.Expr], pl.Expr]
) -> None:
    """Refused at the line, naming the per-period form and the escape."""
    af = _timeline()
    with pytest.raises(ValueError, match="runs down the rows") as refused:
        af.moved = operation(pl.col("reserve"))
    message = str(refused.value)
    assert message.startswith(f"Error setting column 'moved': {method}")
    assert ".list.eval(pl.element()." in message
    assert "polars_native()" in message
    assert "moved" not in af.columns


# The cross-row names the guard did not read until wave 3: a statistic of
# the whole column, a comparison of one row with the rest, a pick, an order
# or a reshape of the rows. On a per-period column each either answered
# policy 1 with another policy's timeline (``shuffle``, ``unique``, ``mode``,
# ``max_by``, ``top_k_by``, ``sample``) or failed later, at collect, with
# Polars' own dtype error or a panic, rather than at the line.
_FOUND_AFTER_THE_FOLDS: dict[str, Callable[[pl.Expr], pl.Expr]] = {
    "product": lambda column: column.product(),
    "std": lambda column: column.std(),
    "var": lambda column: column.var(),
    "quantile": lambda column: column.quantile(0.5),
    "mode": lambda column: column.mode(),
    "unique": lambda column: column.unique(),
    "arg_min": lambda column: column.arg_min(),
    "arg_sort": lambda column: column.arg_sort(),
    "top_k_by": lambda column: column.top_k_by(pl.col("policy_id"), 1),
    "bottom_k": lambda column: column.bottom_k(1),
    "max_by": lambda column: column.max_by(pl.col("policy_id")),
    "qcut": lambda column: column.qcut(2),
    "sample": lambda column: column.sample(1, seed=0),
    "shuffle": lambda column: column.shuffle(seed=0),
    "skew": lambda column: column.skew(),
    "kurtosis": lambda column: column.kurtosis(),
    "entropy": lambda column: column.entropy(),
    "approx_n_unique": lambda column: column.approx_n_unique(),
    "is_sorted": lambda column: column.is_sorted(),
}


@pytest.mark.parametrize(
    "operation", _FOUND_AFTER_THE_FOLDS.values(), ids=_FOUND_AFTER_THE_FOLDS.keys()
)
def test_a_statistic_or_pick_over_a_per_period_column_is_refused_at_assignment(
    operation: Callable[[pl.Expr], pl.Expr], request: pytest.FixtureRequest
) -> None:
    """Refused at the line, naming the method, where it ran across the policies."""
    method = request.node.callspec.id
    af = _timeline()
    with pytest.raises(ValueError, match="runs down the rows") as refused:
        af.moved = operation(pl.col("reserve"))
    assert str(refused.value).startswith(f"Error setting column 'moved': {method} on")
    assert "moved" not in af.columns


@pytest.mark.parametrize(
    "operation", _FOUND_AFTER_THE_FOLDS.values(), ids=_FOUND_AFTER_THE_FOLDS.keys()
)
def test_a_statistic_or_pick_is_left_where_the_rule_leaves_it(
    operation: Callable[[pl.Expr], pl.Expr],
) -> None:
    """The rule is unchanged; only what it reads is wider.

    A frame without a timeline (its rows are the periods), a per-policy
    column (portfolio work), the same method inside one policy's own list,
    and the explicit escape on a stored column are all left to run.
    """
    long_format = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2, 3], "reserve": [1.0, 3.0, 2.0]})
    )
    long_format.summary = operation(pl.col("reserve"))

    af = _timeline()
    af.across_the_book = operation(pl.col("age"))
    af.escaped = operation(af.age.polars_native())
    assert not list(
        _row_operations(pl.col("reserve").list.eval(operation(pl.element())))
    )


def test_with_columns_refuses_it_too() -> None:
    af = _timeline()
    with pytest.raises(ValueError, match="runs down the rows"):
        af.with_columns(pl.col("reserve").shift(1).alias("moved"))


def test_a_shift_used_to_hand_each_policy_the_previous_policys_timeline() -> None:
    """What the refusal replaces: the silent answer, pinned on a long frame.

    Without a timeline the rows are the periods and the shift is the
    calculation, so it runs -- and shows what the same line did to the
    policies of a projected frame.
    """
    long_format = ActuarialFrame(pl.DataFrame({"reserve": [[1.0, 2.0], [3.0, 4.0]]}))
    long_format.moved = pl.col("reserve").shift(1)
    assert long_format.collect()["moved"].to_list() == [None, [1.0, 2.0]]


def test_the_per_period_form_is_accepted() -> None:
    af = _timeline()
    af.moved = pl.col("reserve").list.eval(pl.element().shift(1))
    assert af.collect()["moved"].to_list() == [[None, 1.0, None], [None, 4.0, 5.0]]


def test_a_row_operation_over_a_per_policy_column_is_portfolio_work() -> None:
    """A per-policy column's rows are policies, and ranking them is the point."""
    af = _timeline()
    af.age_rank = pl.col("age").rank()
    af.previous_age = pl.col("age").shift(1)
    out = af.collect()
    assert out["age_rank"].to_list() == [1.0, 2.0]
    assert out["previous_age"].to_list() == [None, 40]


def test_an_elementwise_operation_is_not_a_row_operation() -> None:
    af = _timeline()
    af.doubled = pl.col("reserve") * 2.0
    assert af.collect()["doubled"].to_list()[0] == [2.0, None, 6.0]


def test_the_escape_stays_the_authors_to_open() -> None:
    """``polars_native()`` is not read by this guard; it keeps its own rules."""
    af = _timeline()
    af.previous_age = af.age.polars_native().shift(1)
    assert af.collect()["previous_age"].to_list() == [None, 40]


def test_a_polars_method_continued_from_a_producer_is_read() -> None:
    """A producer's timeline continued by a Polars name it does not declare.

    A frame-independent producer's expression keeps Polars' methods, so the
    continued plan reaches assignment and this guard reads it. A producer
    bound to the frame answers the name as the column does, before any
    assignment (``tests/column/test_bound_producer_expressions.py``).
    """
    af = _timeline()
    unbound = Schedule.from_calendar_grid(
        start_date=date(2026, 1, 31), n_periods=3, frequency="1Y"
    ).is_in_force_expr()
    with pytest.raises(ValueError, match="cum_max on"):
        af.running_max = unbound.cum_max()
    with pytest.raises(AttributeError, match="No 'cum_max' column accessor"):
        af.projection.t_years().cum_max()


def test_a_frame_rebuilt_from_a_collected_projection_still_has_a_timeline() -> None:
    """The per-period ``month`` column is the timeline once the schedule is gone."""
    collected = _timeline().collect()
    rebuilt = ActuarialFrame(collected)
    with pytest.raises(ValueError, match="runs down the rows"):
        rebuilt.moved = pl.col("reserve").shift(1)


@pytest.mark.parametrize("frequency", ["weekly", "daily"])
def test_a_rebuilt_frame_on_an_axis_without_month_still_has_a_timeline(
    frequency: str,
) -> None:
    """A weekly or daily axis stamps no ``month``; ``num_proj_months`` says the same.

    Rebuilt from its own output, such a frame used to read as long format,
    and the shift handed each policy the previous policy's timeline.
    """
    projected = ActuarialFrame(
        pl.DataFrame({"policy_id": [1, 2], "reserve": [[1.0, 2.0], [3.0, 4.0]]})
    )
    projected.projection.set(
        start_date=date(2026, 1, 31), n_periods=1, frequency=frequency
    )
    rebuilt = ActuarialFrame(projected.collect())
    assert "month" not in rebuilt.columns
    with pytest.raises(ValueError, match="runs down the rows"):
        rebuilt.moved = pl.col("reserve").shift(1)


def test_the_two_guards_read_as_one_rule() -> None:
    """A period method needs a per-period column; a row operation, a per-policy one.

    Both on a timeline frame, both refused at the line that wrote them.
    """
    af = _timeline()
    with pytest.raises(ValueError, match="one value per policy"):
        af.previous = af.age.projection.previous_period()
    with pytest.raises(ValueError, match="runs down the rows"):
        af.previous = pl.col("reserve").shift(1)


# --- a raw fragment used as an operand inside a framework formula ----------

_FORMULAS_WITH_A_RAW_FRAGMENT: list[tuple[str, Callable[[ActuarialFrame], object]]] = [
    ("column times fragment", lambda af: af.age * pl.col("reserve").shift(1)),
    ("column less fragment", lambda af: af.reserve - pl.col("reserve").forward_fill()),
    ("in a sum", lambda af: af.reserve + pl.col("reserve").cum_sum()),
    (
        "in a conditional",
        lambda af: when(af.age > 40).then(pl.col("reserve").shift(1)).otherwise(0.0),
    ),
    (
        "under a producer",
        lambda af: af.projection.t_years() * pl.col("reserve").reverse(),
    ),
]


@pytest.mark.parametrize(("where", "formula"), _FORMULAS_WITH_A_RAW_FRAGMENT)
def test_a_raw_row_fragment_inside_a_formula_is_refused(
    where: str, formula: Callable[[ActuarialFrame], object]
) -> None:
    """``af.x * pl.col("t").shift(1)`` ran the shift across the policies."""
    af = _timeline()
    with pytest.raises(ValueError, match="runs down the rows") as refused:
        af.moved = formula(af)
    assert ".list.eval(pl.element()." in str(refused.value), where
    assert "moved" not in af.columns


def test_with_columns_reads_a_formula_s_raw_fragment_too() -> None:
    af = _timeline()
    with pytest.raises(ValueError, match="runs down the rows"):
        af.with_columns(
            (af.projection.t_years() * pl.col("reserve").shift(1)).alias("moved")
        )


def test_a_raw_fragment_over_a_per_policy_column_is_left_to_run() -> None:
    af = _timeline()
    af.previous_age_doubled = af.age * pl.col("age").shift(1)
    assert af.collect()["previous_age_doubled"].to_list() == [None, 1640]


def test_a_raw_per_period_fragment_is_left_to_run() -> None:
    af = _timeline()
    af.moved = af.age * pl.col("reserve").list.eval(pl.element().shift(1))
    assert af.collect()["moved"].to_list()[1] == [None, 164.0, 205.0]


def test_the_escape_inside_a_formula_is_not_marked() -> None:
    """``polars_native()`` mints its node without the raw-operand mark."""
    from gaspatchio.frame.lowering.ingress import raw_operand_expr, to_node

    af = _timeline()
    escaped = af.age.polars_native().shift(1)
    assert raw_operand_expr(escaped._node) is None  # noqa: SLF001
    assert raw_operand_expr(to_node(pl.col("age").shift(1))) is not None  # type: ignore[arg-type]
    af.previous_age_doubled = af.age * escaped
    assert af.collect()["previous_age_doubled"].to_list() == [None, 1640]


def test_a_fold_of_one_policy_s_own_list_is_left_to_run() -> None:
    """``list.agg`` folds one policy's own periods, as ``list.eval`` maps them.

    It was read as the cumulative evaluation, which runs down the rows, and
    refused as one; only the cumulative variant reads other policies.
    """
    af = _timeline()
    af.total = pl.col("reserve").list.agg(pl.element().sum())
    # 1 + null + 3 and 4 + 5 + null, nulls skipped by the sum.
    assert af.collect()["total"].to_list() == [4.0, 9.0]
