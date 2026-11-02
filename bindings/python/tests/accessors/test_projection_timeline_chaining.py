# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A method chained on a projection timeline means what it means on the column.

``af.projection.year_fractions().cum_sum()`` used to run Polars' own
``cum_sum`` on the timeline: on a shared grid that timeline is a literal list,
so the chain was accepted with shape ``scalar`` and failed at collect ("cum_sum
operation not supported for dtype list[f64]"), or further on with a refusal
blaming another line ("this column has one value per policy", a ``list.get``
argument error). Assigning the timeline to a column first gave the right
answer. Found in four independently built models.

Also here: ``list.head`` was refused on a column but accepted on
``af.projection.t_years()`` (ul-r7). Both now answer by the declared
vocabulary.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr

if TYPE_CHECKING:
    from collections.abc import Callable

# Every frame-level projection method that returns a per-period expression,
# with a declared operation that is meaningful on its dtype.
_TIMELINES: list[tuple[str, Callable[[ActuarialFrame], object], str]] = [
    ("period_dates", lambda af: af.projection.period_dates(), "list.get"),
    ("year_fractions", lambda af: af.projection.year_fractions(), "cum_sum"),
    ("t_years", lambda af: af.projection.t_years(), "cum_sum"),
    ("anniversary_mask", lambda af: af.projection.anniversary_mask(), "cum_sum"),
    ("is_in_force", lambda af: af.projection.is_in_force(), "cum_sum"),
    ("contract_boundary", lambda af: af.projection.contract_boundary(), "list.get"),
]


def _shared_grid() -> ActuarialFrame:
    """Two policies on one uniform grid -- the timeline lowers to a literal."""
    af = ActuarialFrame({"policy_id": ["P1", "P2"], "scale": [1.0, 2.0]})
    return af.projection.set(
        start_date=date(2026, 1, 31), n_periods=5, frequency="annual"
    )


def _per_policy_grid() -> ActuarialFrame:
    """Two policies with their own horizons -- the timeline reads columns."""
    af = ActuarialFrame({"policy_id": ["short", "long"], "years": [3, 5]})
    return af.projection.set(
        valuation_date=date(2026, 1, 1),
        until="term_years",
        until_value="years",
        frequency="annual",
        per_policy=True,
    )


def _apply(receiver: object, operation: str) -> object:
    if operation == "list.get":
        return receiver.list.get(0)  # type: ignore[attr-defined]
    return receiver.cum_sum()  # type: ignore[attr-defined]


@pytest.mark.parametrize("grid", [_shared_grid, _per_policy_grid])
@pytest.mark.parametrize(("name", "timeline", "operation"), _TIMELINES)
def test_a_chained_call_matches_the_assigned_column(
    grid: Callable[[], ActuarialFrame],
    name: str,
    timeline: Callable[[ActuarialFrame], object],
    operation: str,
) -> None:
    """Chained straight on, or after assigning first: the same calculation."""
    chained = grid()
    chained.result = _apply(timeline(chained), operation)

    assigned = grid()
    assigned.stored = timeline(assigned)
    assigned.result = _apply(assigned.stored, operation)

    assert chained["result"].shape == assigned["result"].shape, name
    assert (
        chained.collect()["result"].to_list() == assigned.collect()["result"].to_list()
    ), name


@pytest.mark.parametrize(("name", "timeline", "operation"), _TIMELINES)
def test_every_timeline_is_list_shaped_on_a_shared_grid(
    name: str,
    timeline: Callable[[ActuarialFrame], object],
    operation: str,
) -> None:
    """A shared grid's timeline is one value per period, not per policy."""
    del operation
    expr = timeline(_shared_grid())
    assert expr.shape == "list", name  # type: ignore[attr-defined]
    # Still a real pl.Expr: raw Polars interop is untouched.
    assert isinstance(expr, ProxyAwareExpr), name
    assert isinstance(expr, pl.Expr), name


def test_year_fractions_cum_sum_is_the_policy_year() -> None:
    """The room's own line: ``policy_year = year_fractions().cum_sum()``."""
    af = _shared_grid()
    af.policy_year = af.projection.year_fractions().cum_sum()
    assert af["policy_year"].shape == "list"
    assert af.collect()["policy_year"].to_list() == [[1.0, 2.0, 3.0, 4.0, 5.0]] * 2


def test_a_mask_count_feeds_cumulative_survival() -> None:
    """vm20-r5: refused downstream as "one value per policy" before the fix."""
    af = _shared_grid()
    af.t = af.projection.anniversary_mask().cum_sum()
    af.rate = af.t * 0.01
    af.surv = af.rate.projection.cumulative_survival()
    surv = af.collect()["surv"][0].to_list()
    assert surv == pytest.approx([1.0, 0.99, 0.9702, 0.941094, 0.90345024])


def test_a_lookup_keyed_by_the_chained_year_reads_by_period() -> None:
    """ifrs17-r5: ``list.get`` on the lookup failed with an argument error."""
    rates = pl.DataFrame(
        {
            "year": [float(y) for y in range(1, 21)],
            "rate": [0.01 * y for y in range(1, 21)],
        }
    )
    table = Table(name="rate", source=rates, dimensions={"year": "year"}, value="rate")
    af = _shared_grid()
    af.policy_year = af.projection.year_fractions().cum_sum()
    af.rate = table.lookup(year=af.policy_year)
    af.first = af.rate.list.get(0)
    out = af.collect()
    assert out["rate"][0].to_list() == pytest.approx([0.01, 0.02, 0.03, 0.04, 0.05])
    assert out["first"].to_list() == pytest.approx([0.01, 0.01])


def test_an_operator_over_a_literal_keeps_the_timeline() -> None:
    """``(t_years() * 12).cum_sum()`` still folds along the periods."""
    af = _shared_grid()
    af.months_so_far = (af.projection.t_years() * 12).cum_sum()
    assert af.collect()["months_so_far"][0].to_list() == [
        0.0,
        12.0,
        36.0,
        72.0,
        120.0,
        180.0,
    ]


def test_list_head_is_refused_on_a_timeline_as_on_a_column() -> None:
    """ul-r7: the declared-operation rule answers both the same way."""
    af = _shared_grid()
    af.t = af.projection.t_years()
    with pytest.raises(AttributeError) as on_column:
        af.t.list.head(5)
    with pytest.raises(AttributeError) as on_timeline:
        af.projection.t_years().list.head(5)
    assert str(on_timeline.value) == str(on_column.value)
    assert "list.head is not a declared gaspatchio operation" in str(on_timeline.value)


def test_the_named_escape_reaches_list_head_on_a_timeline() -> None:
    """The door the refusal names works on the timeline, once it is a column.

    The schedule read is stored first: inside the escape it would be
    recorded by Polars' text, which does not name the schedule.
    """
    af = _shared_grid()
    af.t = af.projection.t_years()
    af.first_five = af.t.polars_native().list.head(5)
    assert af.collect()["first_five"][0].to_list() == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_an_undeclared_polars_name_keeps_its_polars_meaning() -> None:
    """``alias`` renames as Polars' does -- what ``af.with_columns(...)`` needs.

    It also keeps the timeline's node, so the column records the schedule
    read it is rather than an engine fragment.
    """
    af = _shared_grid()
    af = af.with_columns(af.projection.year_fractions().alias("dt"))
    assert af.collect()["dt"][0].to_list() == [1.0] * 5


@pytest.mark.parametrize(
    "name", ["backward_fill", "diff", "forward_fill", "interpolate", "shift"]
)
def test_an_axis_name_is_refused_on_a_timeline_as_on_a_column(name: str) -> None:
    """``year_fractions().shift(1)`` answered null in every row, silently.

    Polars' ``shift`` on a shared grid's literal timeline moves the literal,
    not each policy's periods. A column refuses the five names whose meaning
    is the axis they run along and names the per-period spelling; a
    timeline now says the same.
    """
    af = _shared_grid()
    af.stored = af.projection.year_fractions()
    with pytest.raises(AttributeError) as on_column:
        getattr(af.stored, name)
    with pytest.raises(AttributeError) as on_timeline:
        getattr(af.projection.year_fractions(), name)()
    # The escape on the timeline read itself hides the schedule read in a
    # Polars expression, which the frame refuses: the move is the stored
    # column's escape. What the refusal says after it is the column's text.
    door = f"_read.polars_native().{name} on that column."
    assert "Store the read as its own column first" in str(on_timeline.value)
    assert (
        str(on_timeline.value).split(door, 1)[1]
        == str(on_column.value).split(f"write .polars_native().{name}.", 1)[1]
    )
    assert "list.eval" in str(on_timeline.value)
