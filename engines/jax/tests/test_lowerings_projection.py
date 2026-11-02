# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The period families against their clauses, case by case.

The padding witnesses in ``test_horizon.py`` pin that a bucket cannot change
an answer. These pin what the answers *are*: the clause's own worked numbers
where it states one, the shape of a boundary sequence against the period
values beside it, and the three rules that are wrong in a way no arithmetic
test would catch -- a mean's denominator, a survival's opening boundary, and
a recurrence that must not be a division by a cumulative product.

Two of these are evidence for lowerings the published kit does not reach on
its value path: every ``excel.irr`` and ``excel.yearfrac`` case in the kit
carries a null somewhere, so this engine refuses it at the door and the solver and the
five day-count bases would otherwise be code with nothing standing behind it.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from gaspatchio.engines.protocol import EngineResult, FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.engine import JaxEngine
from tests.conftest import entry, invocation


def _call(
    name: str, args: list[dict[str, Any]], attrs: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return one call tree, as the executable profile writes it."""
    return {"op": "call", "name": name, "args": args, "attrs": attrs or {}}


def _column(name: str) -> dict[str, Any]:
    """Return one column read."""
    return {"op": "col", "name": name}


def answered(
    tree: dict[str, Any],
    inputs: dict[str, Any],
    dtype: str,
    assumptions: list[dict[str, Any]] | None = None,
    column: str = "answer",
) -> list[Any]:
    """Return what this engine publishes for one invocation."""
    one = invocation(tree, inputs, dtype, assumptions=assumptions, output_column=column)
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    return result.columns[column].to_list()


def refused(
    tree: dict[str, Any],
    inputs: dict[str, Any],
    dtype: str,
    assumptions: list[dict[str, Any]] | None = None,
) -> str:
    """Return the report one invocation refuses with.

    Raises:
        AssertionError: If the engine answered where a refusal was expected.

    """
    one = invocation(tree, inputs, dtype, assumptions=assumptions)
    try:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    except EngineRefusal as refusal:
        return refusal.report.render()
    message = "the engine answered where a refusal was expected"
    raise AssertionError(message)


# One jagged per-period column: three periods, one, and none at all. Every
# rule below that resolves against "that policy's own" length is wrong for
# two of these three if it resolves against the grid instead.
JAGGED = {"dtype": "list[f64]", "values": [[10.0, 20.0, 30.0], [40.0], []]}


def test_a_mean_divides_by_that_policy_s_own_periods() -> None:
    """11.1.15's denominator, which a level timeline hides."""
    answers = answered(
        _call("mean", [_column("x")]),
        {"x": {"dtype": "list[f64]", "values": [[10.0, 20.0, 30.0], [40.0]]}},
        "f64",
    )
    assert answers == [20.0, 40.0]


def test_a_fold_over_a_run_of_no_periods_sums_to_nought_and_averages_to_nothing() -> (
    None
):
    """11.1.14's empty run against 11.1.15's, which are different answers.

    A fold that reached no period has lost none, so the total is nought; there
    is no value to be the average, the least or the greatest of, so those
    three answer null -- and a null is a value this engine states no answer
    over, so it names the policies and counts them.
    """
    empty = {"dtype": "list[f64]", "values": [[10.0], []]}
    assert answered(_call("sum", [_column("x")]), {"x": empty}, "f64") == [10.0, 0.0]
    for name in ("mean", "min", "max"):
        report = refused(_call(name, [_column("x")]), {"x": empty}, "f64")
        assert "reduction.no_periods" in report
        assert "first at row 1" in report


def test_a_survival_s_start_at_is_the_opening_boundary_and_not_a_factor() -> None:
    """11.1.19: ``[a, c[0], ..., c[T-2]]``, never ``a`` times every later product."""
    decrements = {"dtype": "list[f64]", "values": [[0.1, 0.2, 0.3], []]}
    plain = answered(
        _call(
            "projection.cumulative_survival",
            [_column("x")],
            {"start_at": None, "from_survival": False},
        ),
        {"x": decrements},
        "list[f64]",
    )
    assert plain[0] == pytest.approx([0.9, 0.72, 0.504])
    assert plain[1] == []
    opened = answered(
        _call(
            "projection.cumulative_survival",
            [_column("x")],
            {"start_at": 1.0, "from_survival": False},
        ),
        {"x": decrements},
        "list[f64]",
    )
    assert opened[0] == pytest.approx([1.0, 0.9, 0.72])


def test_a_shift_fills_at_that_policy_s_own_boundary() -> None:
    """11.1.19's three shifts, over a jagged column.

    The one-period policy is the case: its ``next_period`` is the fill at its
    only position, because its own last period is position 0 -- and the cell
    at position 1 of the bucket is padding rather than a period of it.
    """
    for name, attrs, expected in (
        ("projection.previous_period", {}, [[0.0, 10.0, 20.0], [0.0], []]),
        ("projection.next_period", {}, [[20.0, 30.0, 0.0], [0.0], []]),
        (
            "projection.at_period",
            {"relative_period": -2},
            [[0.0, 0.0, 10.0], [0.0], []],
        ),
    ):
        assert (
            answered(
                _call(name, [_column("x"), {"op": "lit", "value": 0.0}], attrs),
                {"x": JAGGED},
                "list[f64]",
            )
            == expected
        )


def test_a_recurrence_is_stepped_and_not_divided_back_out() -> None:
    """11.1.20's own exclusion, witnessed by a multiplier of nought.

    ``s[t] = s[t-1] * m[t] + a[t]``. A cumulative product divided back out
    gives a division by nought at the third period here and loses the whole
    policy; the recurrence carries on from the state it actually has.
    """
    answers = answered(
        _call(
            "projection.accumulate",
            [_column("initial"), _column("multiplier"), _column("addend")],
        ),
        {
            "initial": {"dtype": "f64", "values": [100.0]},
            "multiplier": {"dtype": "list[f64]", "values": [[2.0, 0.0, 2.0]]},
            "addend": {"dtype": "list[f64]", "values": [[1.0, 5.0, 3.0]]},
        },
        "list[f64]",
    )
    assert answers[0] == pytest.approx([201.0, 5.0, 13.0])


def test_the_two_valuations_are_the_clause_s_own_worked_numbers() -> None:
    """11.1.20's suffix sum and 11.1.21's end-of-period valuation."""
    assert answered(
        _call("projection.remaining_sum", [_column("x")]),
        {"x": {"dtype": "list[f64]", "values": [[10.0, 20.0, 30.0], []]}},
        "list[f64]",
    ) == [[60.0, 50.0, 30.0], []]
    valued = answered(
        _call(
            "projection.prospective_value",
            [_column("x"), _column("rate")],
            {"timing": "end_of_period", "discount_kind": "rate"},
        ),
        {
            "x": {"dtype": "list[f64]", "values": [[110.0, 120.0], []]},
            "rate": {"dtype": "list[f64]", "values": [[0.1, 0.2], []]},
        },
        "list[f64]",
    )
    assert valued[0] == pytest.approx([190.9090909090909, 100.0])
    assert valued[1] == []


def test_a_padded_rate_of_minus_one_reaches_no_answer_before_the_horizon() -> None:
    """The rate mask, and the one padded value that would carry into the answers.

    A rate of exactly -1 makes its discount factor infinite. The factor at a
    padded cell is in no ``B[t]`` a policy has -- 11.1.21 builds ``B[t]`` out
    of the rates strictly before ``t`` -- but the *weighted* cashflow at that
    cell is ``0 x inf``, which is a NaN, and the suffix sums run backwards
    through it into every earlier period. So the rate goes to nought beyond
    the horizon with the cashflow, and both masks are load-bearing.

    Here the rate is ``axis - 1`` over an axis of ones: nought at every period
    a policy has, and -1 at every padded cell of the wider bucket the
    three-period policy sets.
    """
    valued = answered(
        _call(
            "projection.prospective_value",
            [
                _column("x"),
                _call("sub", [_column("axis"), {"op": "lit", "value": 1.0}]),
            ],
            {"timing": "beginning_of_period", "discount_kind": "rate"},
        ),
        {
            "x": {"dtype": "list[f64]", "values": [[100.0, 100.0, 100.0], [100.0]]},
            "axis": {"dtype": "list[f64]", "values": [[1.0, 1.0, 1.0], [1.0]]},
        },
        "list[f64]",
    )
    assert valued == [[300.0, 200.0, 100.0], [100.0]]


def test_a_position_counts_back_from_that_policy_s_own_length() -> None:
    """11.1.22: ``-1`` is the last period the policy has, not the bucket's."""
    assert answered(
        _call("list.get", [_column("x"), {"op": "lit", "value": -1}]),
        {"x": {"dtype": "list[f64]", "values": [[10.0, 20.0, 30.0], [40.0]]}},
        "f64",
    ) == [30.0, 40.0]
    report = refused(
        _call("list.get", [_column("x"), {"op": "lit", "value": 2}]),
        {"x": {"dtype": "list[f64]", "values": [[10.0, 20.0, 30.0], [40.0]]}},
        "f64",
    )
    assert "list_get.bounds" in report
    assert "Nothing was computed." in report


def test_an_override_never_extends_a_shorter_policy() -> None:
    """11.1.32: a cell that does not exist is not minted by naming it."""
    assert answered(
        _call("projection.with_period", [_column("x")], {"period": 2, "value": 9.0}),
        {"x": {"dtype": "list[f64]", "values": [[1.0, 2.0, 3.0], [1.0]]}},
        "list[f64]",
    ) == [[1.0, 2.0, 9.0], [1.0]]


def test_a_broadcast_repeats_once_per_cell_of_its_own_axis() -> None:
    """11.1.32: only the axis operand's length matters, never its values."""
    assert answered(
        _call(
            "projection.broadcast_to_periods",
            [_column("value"), _column("axis")],
        ),
        {
            "value": {"dtype": "i64", "values": [7, 8]},
            "axis": {"dtype": "list[i64]", "values": [[0, 1], []]},
        },
        "list[i64]",
    ) == [[7, 7], []]


def test_the_two_discount_factor_conventions_part_at_the_second_position() -> None:
    """11.1.30's own worked pair, which is why a reader may not infer one."""
    rates = {"dtype": "list[f64]", "values": [[0.1, 0.2, 0.3]]}
    periods = {"dtype": "list[f64]", "values": [[0.0, 1.0, 2.0]]}
    spot = answered(
        _call(
            "finance.discount_factor",
            [_column("rate"), _column("period")],
            {"method": "spot"},
        ),
        {"rate": rates, "period": periods},
        "list[f64]",
    )
    forward = answered(
        _call(
            "finance.discount_factor",
            [_column("rate"), _column("period")],
            {"method": "forward"},
        ),
        {"rate": rates, "period": periods},
        "list[f64]",
    )
    assert spot[0] == pytest.approx([1.0, 1 / 1.2, 1 / 1.3**2])
    assert forward[0] == pytest.approx([1.0, 1 / 1.1, 1 / (1.1 * 1.2)])


def test_a_knot_curve_is_linear_between_the_knots_and_flat_outside_them() -> None:
    """11.1.31's bounded evaluation, and its refusal of any other recipe."""
    recipe = entry(
        "curve",
        {
            "kind": "Curve",
            "tenors": [1.0, 3.0],
            "rates": [0.02, 0.06],
            "day_count": "ActualActualISDA",
            "interpolation": "linear",
        },
    )
    carried = {
        "kind": "curve",
        "source_sha": recipe["fingerprint"],
        "payload": recipe["payload"],
    }
    assert answered(
        _call("curve.spot_rate", [_column("t")], {"curve": recipe["fingerprint"]}),
        {"t": {"dtype": "f64", "values": [0.0, 1.0, 2.0, 3.0, 5.0]}},
        "f64",
        [carried],
    ) == pytest.approx([0.02, 0.02, 0.04, 0.06, 0.06])


def test_a_schedule_answers_boundaries_and_periods_apart() -> None:
    """11.1.37: ``T + 1`` boundary cells and ``T`` period cells, per policy."""
    recipe = entry(
        "schedule",
        {
            "kind": "per_policy_grid",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
            "frequency": "6M",
            "n_periods": 2,
            "start_date": "2024-01-31",
            "until_kind": "term_months",
            "until_value_column": "term",
        },
    )
    carried = {
        "kind": "schedule",
        "source_sha": recipe["fingerprint"],
        "payload": recipe["payload"],
    }
    book = {"term": {"dtype": "i64", "values": [0, 6, 15]}}
    boundaries = answered(
        _call(
            "projection_frame.period_dates",
            [_column("term")],
            {"schedule": recipe["fingerprint"]},
        ),
        book,
        "list[date]",
        [carried],
    )
    assert boundaries == [
        [datetime.date(2024, 1, 31)],
        [datetime.date(2024, 1, 31), datetime.date(2024, 7, 31)],
        [
            datetime.date(2024, 1, 31),
            datetime.date(2024, 7, 31),
            datetime.date(2025, 1, 31),
        ],
    ]
    assert answered(
        _call(
            "projection_frame.year_fractions",
            [_column("term")],
            {"schedule": recipe["fingerprint"]},
        ),
        book,
        "list[f64]",
        [carried],
    ) == [[], [0.5], [0.5, 0.5]]


def test_a_shared_calendar_grid_steps_and_an_inception_grid_offsets() -> None:
    """11.1.37's own distinction, on the day it shows: the 31st of January.

    A quarterly shared grid runs 30 April then 30 July, because each boundary
    is the previous one advanced and re-clamped; an inception grid runs 30
    April then 31 July, because every boundary is offset from the original
    start. Neither re-anchors to month end.
    """
    shared = entry(
        "schedule",
        {
            "kind": "from_calendar_grid",
            "anchor": "exact_date",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
            "frequency": "3M",
            "n_periods": 2,
            "start_date": "2024-01-31",
        },
    )
    inception = entry(
        "schedule",
        {
            "kind": "from_inception",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
            "frequency": "3M",
            "inception_column": "issued",
            "n_periods": 2,
        },
    )
    for recipe, args, expected in (
        (shared, [], [2024, 4, 30, 2024, 7, 30]),
        (inception, [_column("issued")], [2024, 4, 30, 2024, 7, 31]),
    ):
        answers = answered(
            _call(
                "projection_frame.period_dates",
                args,
                {"schedule": recipe["fingerprint"]},
            ),
            {"issued": {"dtype": "date", "values": ["2024-01-31"]}},
            "list[date]",
            [
                {
                    "kind": "schedule",
                    "source_sha": recipe["fingerprint"],
                    "payload": recipe["payload"],
                }
            ],
        )
        assert answers[0][1] == datetime.date(*expected[:3])
        assert answers[0][2] == datetime.date(*expected[3:])


def test_an_inception_column_the_run_does_not_hold_is_refused_naming_the_schedule() -> (
    None
):
    """11.1.37: the refusal says what named the column -- the schedule, as its start.

    A schedule names its inception column in its recipe, not as an operand,
    so the column the run cannot find is the schedule's to explain; a reader
    told only that "this call" named it has to go and find which call.
    """
    inception = entry(
        "schedule",
        {
            "kind": "from_inception",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
            "frequency": "3M",
            "inception_column": "issued",
            "n_periods": 2,
        },
    )

    said = refused(
        _call(
            "projection_frame.period_dates", [], {"schedule": inception["fingerprint"]}
        ),
        {"entered": {"dtype": "date", "values": ["2024-01-31"]}},
        "list[date]",
        [
            {
                "kind": "schedule",
                "source_sha": inception["fingerprint"],
                "payload": inception["payload"],
            }
        ],
    )

    assert "the schedule names 'issued' as its inception date" in said
    assert "this call" not in said


def test_the_projection_axis_yields_the_boundary_count_the_attributes_state() -> None:
    """Measured: a term horizon named by a column, one boundary per period.

    ``month`` is elapsed whole months from that row's own first boundary, of
    length ``T + 1``; ``num_proj_months`` is that count; and a policy whose
    term is shorter than a period projects nowhere and carries one boundary.
    """
    attrs = {
        "frequency": "quarterly",
        "until": "term_months",
        "until_value": "term",
        "valuation_date": "2024-01-31",
    }
    book = {"term": {"dtype": "i64", "values": [12, 2]}}
    assert answered(
        _call("projection_set", [_column("term")], attrs),
        book,
        "list[i64]",
        column="month",
    ) == [[0, 3, 6, 9, 12], [0]]
    assert answered(
        _call("projection_set", [_column("term")], attrs),
        book,
        "i64",
        column="num_proj_months",
    ) == [5, 1]
    assert answered(
        _call("projection_set", [_column("term")], attrs),
        book,
        "date",
        column="projection_end_date",
    ) == [datetime.date(2025, 1, 31), datetime.date(2024, 1, 31)]


def test_an_axis_the_record_does_not_determine_refuses_by_name() -> None:
    """11.1.1's own first warning: a horizon sized from the portfolio.

    Two runs of one configuration over two books carry the same attributes and
    the same node identity and lay axes of different lengths, so an engine
    that laid one from the attributes would be answering a different model's
    axis under this one's fingerprint.
    """
    report = refused(
        _call(
            "projection_set",
            [],
            {
                "frequency": "monthly",
                "until": "maximum_age",
                "until_value": 100,
                "valuation_date": "2024-01-31",
            },
        ),
        {"term": {"dtype": "i64", "values": [12]}},
        "list[i64]",
    )
    assert "its length is not on the record" in report


def test_next_anniversary_is_no_horizon_this_engine_lays() -> None:
    """11.1.1 has no ``next_anniversary``; a record naming it is refused.

    It answered ``term_years``'s count, ``k`` years at ``p`` periods a year,
    under a name promising each policy's own contract anniversary.
    """
    report = refused(
        _call(
            "projection_set",
            [],
            {
                "frequency": "monthly",
                "until": "next_anniversary",
                "until_value": 1,
                "valuation_date": "2024-01-31",
            },
        ),
        {"term": {"dtype": "i64", "values": [12]}},
        "list[i64]",
    )
    assert "'next_anniversary'" in report


def test_the_calendar_clamps_the_day_every_month_move_lands_on() -> None:
    """11.1.33's clamp, shared by every operation in this family."""
    days = {"dtype": "date", "values": ["2024-01-31", "2024-02-29"]}
    months = {"dtype": "i64", "values": [1, 12]}
    assert answered(
        _call("excel.edate", [_column("d"), _column("m")]),
        {"d": days, "m": months},
        "date",
    ) == [datetime.date(2024, 2, 29), datetime.date(2025, 2, 28)]
    assert answered(
        _call("excel.eomonth", [_column("d"), _column("m")]),
        {"d": days, "m": months},
        "date",
    ) == [datetime.date(2024, 2, 29), datetime.date(2025, 2, 28)]
    assert answered(
        _call("date.offset_by", [_column("d")], {"duration": "1mo"}),
        {"d": days},
        "date",
    ) == [datetime.date(2024, 2, 29), datetime.date(2024, 3, 29)]


def test_a_spreadsheet_serial_reads_the_phantom_leap_day_as_the_28th() -> None:
    """11.1.33's 1900 system, which has a 29 February that never happened."""
    assert answered(
        _call("excel.from_excel_serial", [_column("s")], {"epoch": "1900"}),
        {"s": {"dtype": "f64", "values": [1.0, 59.0, 60.0, 60.5, 61.0]}},
        "date",
    ) == [
        datetime.date(1900, 1, 1),
        datetime.date(1900, 2, 28),
        datetime.date(1900, 2, 28),
        datetime.date(1900, 2, 28),
        datetime.date(1900, 3, 1),
    ]
    assert answered(
        _call("excel.from_excel_serial", [_column("s")], {"epoch": "1904"}),
        {"s": {"dtype": "f64", "values": [1.0, 59.0, 60.0, 61.0]}},
        "date",
    ) == [
        datetime.date(1904, 1, 2),
        datetime.date(1904, 2, 29),
        datetime.date(1904, 3, 1),
        datetime.date(1904, 3, 2),
    ]


@pytest.mark.parametrize(
    ("basis", "expected"),
    [
        # February's last day becomes 30, and the 31st that ends it stays 31.
        (0, 0.08611111111111111),
        (1, 0.08469945355191257),
        (2, 0.08611111111111111),
        (3, 0.08493150684931507),
        (4, 0.08611111111111111),
    ],
)
def test_every_day_count_basis_answers_the_published_number(
    basis: int, expected: float
) -> None:
    """11.1.34's five bases over one pair of dates, and the pair reversed.

    Reversed, each basis answers the same number: Excel's YEARFRAC takes the
    earlier date as the start, and no answer is negative.

    The kit's own ``yearfrac-feb-end`` dates, without its third row: that row
    carries a null start and refuses at the door, which would leave
    the five bases with nothing standing behind them.
    """
    answers = answered(
        _call("excel.yearfrac", [_column("start"), _column("end")], {"basis": basis}),
        {
            "start": {"dtype": "date", "values": ["2024-02-29", "2024-03-31"]},
            "end": {"dtype": "date", "values": ["2024-03-31", "2024-02-29"]},
        },
        "f64",
    )
    assert answers == pytest.approx([expected, expected])


def test_a_leap_anniversary_is_365_over_366_under_actual_actual() -> None:
    """28 February is on the 29 February anniversary, and holds 2024's leap day."""
    assert answered(
        _call("excel.yearfrac", [_column("start"), _column("end")], {"basis": 1}),
        {
            "start": {"dtype": "date", "values": ["2024-02-29"]},
            "end": {"dtype": "date", "values": ["2025-02-28"]},
        },
        "f64",
    ) == [365 / 366]


def test_a_present_value_carries_the_timing_flag_the_spreadsheet_does() -> None:
    """11.1.35's annuity, at both timings and at a rate of nought."""
    book = {
        "rate": {"dtype": "f64", "values": [0.1, 0.0]},
        "nper": {"dtype": "f64", "values": [2.0, 2.0]},
        "pmt": {"dtype": "f64", "values": [100.0, 100.0]},
    }
    args = [_column("rate"), _column("nper"), _column("pmt")]
    assert answered(
        _call("excel.pv", args, {"fv": 50.0, "typ": 0}), book, "f64"
    ) == pytest.approx([-214.87603305785132, -250.0])
    assert answered(
        _call("excel.pv", args, {"fv": 50.0, "typ": 1}), book, "f64"
    ) == pytest.approx([-232.23140495867779, -250.0])


def test_a_rate_of_return_is_the_root_and_a_stream_with_several_refuses() -> None:
    """11.1.36's bounded solver, and the streams it puts outside itself."""
    assert answered(
        _call("excel.irr", [_column("cf")], {"default_guess": None}),
        {
            "cf": {
                "dtype": "list[f64]",
                "values": [[-100.0, 110.0], [-100.0, 90.0], [-100.0, 100.0]],
            }
        },
        "f64",
    ) == pytest.approx([0.1, -0.1, 0.0], abs=1e-7)
    several = refused(
        _call("excel.irr", [_column("cf")], {"default_guess": None}),
        {"cf": {"dtype": "list[f64]", "values": [[-100.0, 230.0, -132.0]]}},
        "f64",
    )
    assert "excel.irr.several_roots" in several
    assert "split the stream" in several
    assert "11.1.36" in several
    # And the other stream, which is a different finding with a different next
    # move: one that never turns has no rate at all rather than several.
    none = refused(
        _call("excel.irr", [_column("cf")], {"default_guess": None}),
        {"cf": {"dtype": "list[f64]", "values": [[100.0, 230.0, 132.0]]}},
        "f64",
    )
    assert "excel.irr.no_sign_change" in none
    assert "a cashflow paid and a cashflow received" in none


def test_a_range_offsets_every_candidate_from_the_original_start() -> None:
    """11.1.33: a monthly range from 31 January runs 29 February, then 31 March."""
    assert answered(
        _call(
            "date.date_ranges",
            [_column("start"), _column("end")],
            {"interval": "1mo", "closed": "both"},
        ),
        {
            "start": {"dtype": "date", "values": ["2024-01-31", "2024-02-01"]},
            "end": {"dtype": "date", "values": ["2024-04-01", "2024-01-01"]},
        },
        "list[date]",
    ) == [
        [
            datetime.date(2024, 1, 31),
            datetime.date(2024, 2, 29),
            datetime.date(2024, 3, 31),
        ],
        [],
    ]


def test_the_endpoint_rule_drops_the_endpoints_it_names() -> None:
    """11.1.33's four closures over one three-day range."""
    endpoints = {
        "start": {"dtype": "date", "values": ["2024-02-28"]},
        "end": {"dtype": "date", "values": ["2024-03-01"]},
    }
    for closed, expected in (
        ("both", [(2024, 2, 28), (2024, 2, 29), (2024, 3, 1)]),
        ("left", [(2024, 2, 28), (2024, 2, 29)]),
        ("right", [(2024, 2, 29), (2024, 3, 1)]),
        ("none", [(2024, 2, 29)]),
    ):
        assert answered(
            _call(
                "date.date_ranges",
                [_column("start"), _column("end")],
                {"interval": "1d", "closed": closed},
            ),
            endpoints,
            "list[date]",
        ) == [[datetime.date(*one) for one in expected]]


def test_a_month_difference_ignores_the_days() -> None:
    """11.1.33: 31 January to 1 February is one month."""
    assert answered(
        _call("date.months_between", [_column("start"), _column("end")]),
        {
            "start": {"dtype": "date", "values": ["2024-01-31", "2025-01-01"]},
            "end": {"dtype": "date", "values": ["2024-02-01", "2024-12-31"]},
        },
        "i64",
    ) == [1, -1]


def test_a_null_in_a_column_read_only_as_a_key_is_a_miss_and_not_a_refusal() -> None:
    """The null refusal, narrowed for a key: the guarded surrender-charge read.

    The key column carries nothing for the policies whose plan has no
    schedule at all. Under a miss policy the read states an answer for, that
    is a miss and the ``when_then`` in front of it never selects the branch;
    under ``raise`` it is a refusal naming the key. Both halves, because a
    door that let one through and not the other would be two rules.
    """
    basis = entry(
        "table",
        {
            "columns": [
                {"name": "plan", "dtype": "str"},
                {"name": "rate", "dtype": "f64"},
            ],
            "dimensions": ["plan"],
            "rows": [["A", 0.05], ["B", 0.03]],
            "value": "rate",
        },
        name="charges",
    )
    carried = [
        {
            "kind": "table",
            "name": "charges",
            "fingerprint": basis["fingerprint"],
            "payload": basis["payload"],
        }
    ]
    book = {
        "guard": {"dtype": "bool", "values": [True, False]},
        "plan": {"dtype": "str", "values": ["A", None]},
    }

    def guarded(policy: str) -> dict[str, Any]:
        return {
            "op": "when_then",
            "cond": _column("guard"),
            "then": _call(
                "lookup",
                [_column("plan")],
                {
                    "table": "charges",
                    "table_fingerprint": basis["fingerprint"],
                    "on_missing": policy,
                    "fill_value": -0.25 if policy == "fill" else None,
                },
            ),
            "otherwise": {"op": "lit", "value": 0.0},
        }

    assert answered(guarded("nan"), book, "f64", carried) == [0.05, 0.0]
    assert answered(guarded("fill"), book, "f64", carried) == [0.05, 0.0]
    report = refused(guarded("raise"), book, "f64", carried)
    assert "lookup.miss_raise" in report
    assert "plan=None" in report


def test_a_join_that_brings_an_empty_text_cell_reports_rather_than_refuses() -> None:
    """11.1.2's null is for an unmatched key, and a blank cell is not one.

    Level 4's right side is the case: a surrender-charge identifier that is
    not there on the two plans with no schedule. The key matched; the arriving
    column is null for those policies, and text carries that honestly as the
    absent code -- which publishes a null and misses any read keyed on it.
    """
    right = entry(
        "join",
        {
            "columns": [
                {"name": "plan", "dtype": "str"},
                {"name": "charge_id", "dtype": "str"},
            ],
            "rows": [["A", "SC001"], ["B", None]],
        },
    )
    one = invocation(
        _call(
            "join",
            [],
            {"on": "plan", "how": "left", "right_fingerprint": right["fingerprint"]},
        ),
        {"plan": {"dtype": "str", "values": ["A", "B"]}},
        "str",
        assumptions=[
            {
                "kind": "join",
                "source_sha": right["fingerprint"],
                "payload": right["payload"],
            }
        ],
        output_column="charge_id",
    )
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    assert result.columns["charge_id"].to_list() == ["SC001", None]
    assert any("is not there" in note for note in result.report.notes)


def test_the_host_stage_refuses_a_computed_operand_with_its_own_gate_neutered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The computed-text guard in the host stage, reached by removing the one in front.

    Two halves state one rule: the capability refuses a text-producing
    operation whose operand a calculation produced, and the host stage refuses
    it again where the operand resolves to a computed node. The second is
    behind the first and nothing in the ordinary suite reaches it -- so the
    gate is neutered here, and what is pinned is that the stage itself still
    refuses rather than publishing the values the column held before the model
    wrote over it -- under the clause the capability refuses the same operand
    under, the operation's own, so the two halves cite one section.
    """
    from gaspatchio_jax import capability
    from gaspatchio_jax.lowerings import conversion
    from gaspatchio_jax.typed import DomainRefused

    monkeypatch.setattr(capability, "_is_computed", lambda *_args: False)
    record = capability.NodeRecord(
        node_id="answer@1",
        column="answer",
        version=1,
        kind="computed",
        dtype="str",
        shape="scalar",
        reads=("duration@1",),
        expr=_call("to_text", [_column("duration")]),
        in_final_schema=True,
        arriving_columns=frozenset({"duration"}),
        read_dtypes={"duration": "i64"},
        read_kinds={"duration": "computed"},
    )

    with pytest.raises(DomainRefused) as refusal:
        # Refused before the book or the dictionary is read, so neither is built.
        conversion.on_the_host(record, prepared=None, dictionary=None)
    assert "which a calculation produced" in refusal.value.what
    assert refusal.value.clause == "11.1.39"


def test_a_discount_factor_takes_either_operand_per_period_and_neither_neither() -> (
    None
):
    """11.1.30's disjunction, which a shape domain cannot state and so is pinned.

    "This entry states forms with at least one list." A per-period rate
    against a per-policy period and a per-policy rate against a per-period one
    are both the operation; two per-policy operands are not, and the shape
    domain -- one admitted set per position -- has no way to say so. So the
    three forms stand here instead of in the sweep.
    """
    spot = {"method": "spot"}
    per_period_rate = answered(
        _call("finance.discount_factor", [_column("rate"), _column("period")], spot),
        {
            "rate": {"dtype": "list[f64]", "values": [[0.1, 0.2]]},
            "period": {"dtype": "f64", "values": [2.0]},
        },
        "list[f64]",
    )
    assert per_period_rate[0] == pytest.approx([1 / 1.1**2, 1 / 1.2**2])
    per_period_time = answered(
        _call("finance.discount_factor", [_column("rate"), _column("period")], spot),
        {
            "rate": {"dtype": "f64", "values": [0.1]},
            "period": {"dtype": "list[f64]", "values": [[0.0, 1.0, 2.0]]},
        },
        "list[f64]",
    )
    assert per_period_time[0] == pytest.approx([1.0, 1 / 1.1, 1 / 1.1**2])
    report = refused(
        _call("finance.discount_factor", [_column("rate"), _column("period")], spot),
        {
            "rate": {"dtype": "f64", "values": [0.1]},
            "period": {"dtype": "f64", "values": [2.0]},
        },
        "f64",
    )
    assert "at least one per-period operand" in report


def test_a_check_is_read_over_the_periods_a_policy_has_and_not_the_padding() -> None:
    """A position-local check over a per-period column, twice.

    Neither line has anything wrong with it. The divisors are four non-zero
    whole numbers and both sums are whole. What used to refuse them was the
    bucket: a position-local operation does not mask -- correctly, because
    padding cannot reach a position before the horizon -- so its *checks* saw
    cells nobody wrote, and a divisor of nought and a half that is not whole
    are exactly what the carrier's zero looks like to those two checks.
    """
    periods = {
        "a": {"dtype": "list[i64]", "values": [[-7, -1, 3, 7]]},
        "b": {"dtype": "list[i64]", "values": [[3, 2, -2, -3]]},
    }
    assert answered(
        {
            "op": "binop",
            "kind": "floordiv",
            "left": _column("a"),
            "right": _column("b"),
        },
        periods,
        "list[i64]",
    ) == [[-3, -1, -2, -3]]
    assert answered(
        {"op": "binop", "kind": "mod", "left": _column("a"), "right": _column("b")},
        periods,
        "list[i64]",
    ) == [[2, 1, -1, -2]]
    assert answered(
        _call(
            "to_integer",
            [
                {
                    "op": "binop",
                    "kind": "add",
                    "left": _column("x"),
                    "right": {"op": "lit", "value": 0.5},
                }
            ],
        ),
        {"x": {"dtype": "list[f64]", "values": [[0.5, 1.5]]}},
        "list[i64]",
    ) == [[1, 2]]


def test_a_check_still_refuses_a_cell_that_is_a_period() -> None:
    """The masking is the padding's, not an amnesty: a real zero still refuses."""
    report = refused(
        {
            "op": "binop",
            "kind": "floordiv",
            "left": _column("a"),
            "right": _column("b"),
        },
        {
            "a": {"dtype": "list[i64]", "values": [[7, 7]]},
            "b": {"dtype": "list[i64]", "values": [[2, 0]]},
        },
        "list[i64]",
    )
    assert "floordiv.zero_divisor" in report
    assert "policy 0, period 1" in report


def test_two_per_period_operands_of_one_length_meet_whatever_bucket_they_stand_in() -> (
    None
):
    """A bucket is this engine's padding and no part of the model.

    The schedule family sizes its bucket from a boundary count and an arriving
    column from its own cells, so twelve year fractions and a twelve-period
    cashflow stand in buckets of twenty-four and twelve. They are the same
    timeline and the line that multiplies them is an ordinary one.
    """
    recipe = entry(
        "schedule",
        {
            "kind": "from_calendar_grid",
            "anchor": "exact_date",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
            "frequency": "1M",
            "n_periods": 12,
            "start_date": "2024-01-31",
        },
    )
    carried = [
        {
            "kind": "schedule",
            "source_sha": recipe["fingerprint"],
            "payload": recipe["payload"],
        }
    ]
    answers = answered(
        {
            "op": "binop",
            "kind": "mul",
            "left": _call(
                "projection_frame.year_fractions",
                [],
                {"schedule": recipe["fingerprint"]},
            ),
            "right": _column("cash"),
        },
        {"cash": {"dtype": "list[f64]", "values": [[12.0] * 12]}},
        "list[f64]",
        carried,
    )
    assert answers == [[1.0] * 12]


def test_two_per_period_operands_of_different_lengths_still_refuse() -> None:
    """And 11.1.18's sentence is kept for the case it is true of."""
    report = refused(
        {"op": "binop", "kind": "mul", "left": _column("a"), "right": _column("b")},
        {
            "a": {"dtype": "list[f64]", "values": [[1.0, 2.0, 3.0]]},
            "b": {"dtype": "list[f64]", "values": [[1.0, 2.0]]},
        },
        "list[f64]",
    )
    assert "different numbers of periods within a policy" in report
    assert "11.1.18" in report


def test_a_fold_of_whole_numbers_answers_a_whole_number() -> None:
    """11.1.14's total of a run of integers is an integer, as the producer says.

    The record declares ``i64`` because the producer answers ``Int64``; an
    engine that widened to a double answered a type the record does not carry
    and then blamed the record for it.
    """
    periods = {"x": {"dtype": "list[i64]", "values": [[1, 2, 3], [10]]}}
    assert answered(_call("sum", [_column("x")]), periods, "i64") == [6, 10]
    assert answered(_call("min", [_column("x")]), periods, "i64") == [1, 10]
    assert answered(_call("max", [_column("x")]), periods, "i64") == [3, 10]
    assert answered(
        _call("cum_sum", [_column("x")], {"reverse": False}), periods, "list[i64]"
    ) == [[1, 3, 6], [10]]
    assert answered(
        _call("cum_prod", [_column("x")], {"reverse": False}), periods, "list[i64]"
    ) == [[1, 2, 6], [10]]
    # And the average of whole numbers is a decimal, which is why it is the
    # one of the six that states its answer's carrier.
    assert answered(_call("mean", [_column("x")]), periods, "f64") == [2.0, 10.0]


def test_an_integer_fold_that_leaves_the_range_refuses_rather_than_wrapping() -> None:
    """The checked arithmetic the typed path already has, inside the scan."""
    report = refused(
        _call("sum", [_column("x")]),
        {"x": {"dtype": "list[i64]", "values": [[2**62, 2**62, 2**62]]}},
        "i64",
    )
    assert "i64.range" in report
    assert "No results were published." in report


def test_a_null_in_a_numeric_key_column_refuses_and_says_which() -> None:
    """The narrowed door is text's, and the other carriers are told why.

    Section 11.1.24 makes a null key a miss, and a miss needs a value the
    basis cannot carry. Text has one -- the absent code, which no string is
    ever minted onto. A number has none: every value a number could take is
    a key some basis could legitimately hold.
    """
    basis = entry(
        "table",
        {
            "columns": [
                {"name": "age", "dtype": "f64"},
                {"name": "rate", "dtype": "f64"},
            ],
            "dimensions": ["age"],
            "rows": [[45.0, 0.01], [55.0, 0.02]],
            "value": "rate",
        },
        name="rates",
    )
    report = refused(
        _call(
            "lookup",
            [_column("age")],
            {
                "table": "rates",
                "table_fingerprint": basis["fingerprint"],
                "on_missing": "nan",
                "fill_value": None,
            },
        ),
        {"age": {"dtype": "f64", "values": [45.0, None]}},
        "f64",
        [
            {
                "kind": "table",
                "name": "rates",
                "fingerprint": basis["fingerprint"],
                "payload": basis["payload"],
            }
        ],
    )
    assert "read only as a key" in report
    assert "only text has" in report
    # 11.1.24 makes a null query key a miss its read's own policy answers, so
    # citing it would tell a reader the input is valid. It is, and the refusal
    # is this engine's own limit: the line says so and cites no clause.
    assert "a limit of this engine and not a fault in the model" in report
    assert "11.1.24" not in report


def test_a_join_with_a_computed_key_and_a_blank_cell_notes_rather_than_refuses() -> (
    None
):
    """The completion path treats a blank arriving cell as the inputs path does.

    The key here is a calculation, so the finding waits for completion; what
    it finds is a matched row whose arriving column is empty, which is the
    column being null there rather than a key the right side does not carry.
    """
    right = entry(
        "join",
        {
            "columns": [
                {"name": "plan", "dtype": "str"},
                {"name": "charge_id", "dtype": "str"},
            ],
            "rows": [["AX", "SC001"], ["BX", None]],
        },
    )
    one = invocation(
        _call(
            "join",
            [],
            {
                "on": "plan",
                "how": "left",
                "right_fingerprint": right["fingerprint"],
            },
        ),
        {"plan_in": {"dtype": "str", "values": ["A", "B"]}},
        "str",
        assumptions=[
            {
                "kind": "join",
                "source_sha": right["fingerprint"],
                "payload": right["payload"],
            }
        ],
        output_column="charge_id",
    )
    # 11.1.2's own rule: a join node reads the key it was matched on, bound
    # to the definition the key held when the join ran -- here a calculation,
    # which is what puts the finding at completion rather than at the door.
    one.document["nodes"][-1]["reads"] = ["plan@1"]
    one.document["nodes"].insert(
        1,
        {
            **one.document["nodes"][0],
            "id": "plan@1",
            "column": "plan",
            "version": 1,
            "kind": "computed",
            "tier": "core",
            "engines": [],
            "provenance": "assignment",
            "reads": ["plan_in"],
            "expr": {
                "op": "call",
                "name": "replace",
                "args": [
                    _column("plan_in"),
                    {"op": "lit", "values": ["A", "B"]},
                    {"op": "lit", "values": ["AX", "BX"]},
                ],
                "attrs": {},
            },
        },
    )
    one.document["edges"] = [
        {"source": "plan_in", "target": "plan@1", "relationship": "DIRECT"},
        {"source": "plan@1", "target": "charge_id@1", "relationship": "INDIRECT"},
    ]
    from gaspatchio_jax.vectors import (
        _sealed,
    )

    result = JaxEngine().run(_sealed(one.document), one.inputs, FrameSink())
    assert result.columns["charge_id"].to_list() == ["SC001", None]
    assert any("is not there" in note for note in result.report.notes)


def test_a_check_in_the_horizon_column_s_ancestry_is_held_to_its_own_periods() -> None:
    """A horizon column is an ordinary calculation and may stand on a per-period one.

    ``max(a // b)`` is a term in months read off a per-period column, and the
    axis stage lowers it before anything else runs. Its ``floordiv`` is
    position-local and does not mask -- so its zero-divisor check sees the
    carrier's own nought in every cell past the fourth, exactly as the main
    pass's checks did before they were held. The two answers are the same
    line: as an ordinary column it answers -1, and as the column a projection
    axis is sized from it has to answer -1 as well.
    """
    periods = {
        "a": {"dtype": "list[i64]", "values": [[-7, -1, 3, 7]]},
        "b": {"dtype": "list[i64]", "values": [[3, 2, -2, -3]]},
    }
    assert answered(_TERM_IN_MONTHS, periods, "i64") == [-1]
    result = _sized_from_a_term(periods)
    # A term of -1 months projects nowhere, which is one boundary.
    assert result.columns["num_proj_months"].to_list() == [1]


def test_a_check_in_the_horizon_column_s_ancestry_still_refuses_a_real_period() -> None:
    """The other direction of the same hold, which is the one that can hide a fault.

    Holding a flag to a node's own periods is the padding's amnesty and no
    part of the model's: a divisor of nought at a period the policy really has
    is a line somebody wrote, and it refuses from the axis stage exactly as it
    does from the main pass. Held to nothing at all the run would answer here,
    with the axis sized off a division this engine had already caught.
    """
    periods = {
        "a": {"dtype": "list[i64]", "values": [[7, 7]]},
        "b": {"dtype": "list[i64]", "values": [[2, 0]]},
    }
    try:
        _sized_from_a_term(periods)
    except EngineRefusal as refusal:
        report = refusal.report.render()
    else:
        message = "the engine answered where a refusal was expected"
        raise AssertionError(message)
    assert "floordiv.zero_divisor" in report
    assert "policy 0, period 1" in report
    assert "term@1" in report


# A term in months read off a per-period column: the horizon column of the two
# tests above, whose own ``floordiv`` is position-local and therefore does not
# mask, so its zero-divisor check is the one that sees the carrier's nought in
# the padding.
_TERM_IN_MONTHS: dict[str, Any] = _call(
    "max",
    [{"op": "binop", "kind": "floordiv", "left": _column("a"), "right": _column("b")}],
)


def _sized_from_a_term(periods: dict[str, Any]) -> EngineResult:
    """Run a projection whose ``until_value`` column is ``_TERM_IN_MONTHS``.

    Raises:
        EngineRefusal: If anything in the axis stage or the main pass refuses.

    """
    from gaspatchio_jax.vectors import _sealed

    one = invocation(
        _call(
            "projection_set",
            [_column("term")],
            {
                "frequency": "monthly",
                "until": "term_months",
                "until_value": "term",
                "valuation_date": "2024-01-31",
            },
        ),
        periods,
        "i64",
        output_column="num_proj_months",
    )
    one.document["nodes"].insert(
        -1,
        {
            **one.document["nodes"][0],
            "id": "term@1",
            "column": "term",
            "version": 1,
            "kind": "computed",
            "tier": "core",
            "engines": [],
            "dtype": "i64",
            "shape": "scalar",
            "provenance": "assignment",
            "in_final_schema": False,
            "reads": ["a", "b"],
            "expr": _TERM_IN_MONTHS,
        },
    )
    one.document["nodes"][-1]["reads"] = ["term@1"]
    one.document["edges"] = [
        {"source": "a", "target": "term@1", "relationship": "DIRECT"},
        {"source": "b", "target": "term@1", "relationship": "DIRECT"},
        {"source": "term@1", "target": "num_proj_months@1", "relationship": "DIRECT"},
    ]
    return JaxEngine().run(_sealed(one.document), one.inputs, FrameSink())


def test_a_conditional_selects_between_two_of_one_type_whatever_that_type_is() -> None:
    """11.1.28's matched pair, over the three the numeric bound left out.

    A bare Boolean condition and two branches of one type: two pieces of text,
    two calendar days, two truth values. The condition is a truth value and
    stands in no family with either branch, which is why the family rule is
    about positions 1 and 2 -- a rule that took the condition in refused a
    mortality table chosen by sex for "comparing a number and text".
    """
    guard = {"guard": {"dtype": "bool", "values": [True, False]}}
    assert answered(
        {
            "op": "when_then",
            "cond": _column("guard"),
            "then": _column("male"),
            "otherwise": _column("female"),
        },
        {
            **guard,
            "male": {"dtype": "str", "values": ["T3275", "T3275"]},
            "female": {"dtype": "str", "values": ["T3276", "T3276"]},
        },
        "str",
    ) == ["T3275", "T3276"]
    assert answered(
        {
            "op": "when_then",
            "cond": _column("guard"),
            "then": _column("opened"),
            "otherwise": _column("closed"),
        },
        {
            **guard,
            "opened": {"dtype": "date", "values": ["2024-01-31", "2024-01-31"]},
            "closed": {"dtype": "date", "values": ["2025-01-31", "2025-01-31"]},
        },
        "date",
    ) == [datetime.date(2024, 1, 31), datetime.date(2025, 1, 31)]


def test_a_conditional_across_two_families_refuses_and_names_the_branches() -> None:
    """And the crossed pair the clause puts outside itself."""
    report = refused(
        {
            "op": "when_then",
            "cond": _column("guard"),
            "then": _column("count"),
            "otherwise": _column("name"),
        },
        {
            "guard": {"dtype": "bool", "values": [True, False]},
            "count": {"dtype": "i64", "values": [1, 2]},
            "name": {"dtype": "str", "values": ["a", "b"]},
        },
        "str",
    )
    assert "when_then selects between a number and text" in report
    assert "states no common type for them" in report


def test_a_join_with_a_computed_key_and_a_blank_numeric_cell_refuses_by_name() -> None:
    """The other half of it: a carrier this engine holds no absent value for.

    Text carries an empty arriving cell honestly, because the absent code is a
    code no string is ever minted onto. A number has no such value -- every
    number is a number some right side could legitimately hold -- so a blank
    numeric cell is a finding, and on a computed key it is one that waits for
    completion with its count.
    """
    from gaspatchio_jax.vectors import (
        _sealed,
    )

    right = entry(
        "join",
        {
            "columns": [
                {"name": "plan", "dtype": "str"},
                {"name": "fee_rate", "dtype": "f64"},
            ],
            "rows": [["AX", 0.01], ["BX", None]],
        },
    )
    one = invocation(
        _call(
            "join",
            [],
            {
                "on": "plan",
                "how": "left",
                "right_fingerprint": right["fingerprint"],
            },
        ),
        {"plan_in": {"dtype": "str", "values": ["A", "B"]}},
        "f64",
        assumptions=[
            {
                "kind": "join",
                "source_sha": right["fingerprint"],
                "payload": right["payload"],
            }
        ],
        output_column="fee_rate",
    )
    # 11.1.2: the join reads the key it was matched on, the model's own line.
    one.document["nodes"][-1]["reads"] = ["plan@1"]
    one.document["nodes"].insert(
        1,
        {
            **one.document["nodes"][0],
            "id": "plan@1",
            "column": "plan",
            "version": 1,
            "kind": "computed",
            "tier": "core",
            "engines": [],
            "provenance": "assignment",
            "reads": ["plan_in"],
            "expr": {
                "op": "call",
                "name": "replace",
                "args": [
                    _column("plan_in"),
                    {"op": "lit", "values": ["A", "B"]},
                    {"op": "lit", "values": ["AX", "BX"]},
                ],
                "attrs": {},
            },
        },
    )
    one.document["edges"] = [
        {"source": "plan_in", "target": "plan@1", "relationship": "DIRECT"},
        {"source": "plan@1", "target": "fee_rate@1", "relationship": "INDIRECT"},
    ]
    sealed = _sealed(one.document)
    with pytest.raises(EngineRefusal) as refusal:
        JaxEngine().run(sealed, one.inputs, FrameSink())
    report = refusal.value.report
    assert "join.blank_arriving" in report.render()
    assert "No results were published." in report.render()
    assert [one.count for one in report.refusals] == [1]


def test_the_two_scalar_valuations_refuse_a_nested_per_period_operand() -> None:
    """11.1.29's bound, kept where a declaration cannot reach.

    A shape domain is read one level deep, so an operand that is a nested
    expression has no declared shape and the declaration passes it through.
    That is where the clause's own sentence has to be kept -- and it was not:
    the two published a condition saying "one value per policy" while the
    runtime answered the per-period form the clause names ``prospective_value``
    for.
    """
    book = {
        "cf": {"dtype": "list[f64]", "values": [[100.0, 200.0]]},
        "r": {"dtype": "f64", "values": [0.05]},
        "t": {"dtype": "f64", "values": [1.0]},
    }
    nested = {
        "op": "binop",
        "kind": "mul",
        "left": _column("cf"),
        "right": {"op": "lit", "value": 1.0},
    }
    for name in ("finance.discount", "finance.present_value"):
        report = refused(
            _call(name, [nested, _column("r"), _column("t")]),
            book,
            "list[f64]",
        )
        assert f"{name} is written over one value per period" in report
        assert "projection.prospective_value" in report
        assert "11.1.29" in report


def test_a_record_disagreement_names_the_side_it_knows() -> None:
    """And names both where it cannot know which of them moved.

    Telling a reader to report a widening against the record sends them to
    argue with the producer about this engine's own arithmetic. Where the
    engine's answer is the wider carrier, the engine is what moved; where
    neither is a widening of the other, the two disagree about what the
    operation answers at all and neither can be named alone.
    """
    from gaspatchio_jax.plan import _who_to_tell  # the engine's one reading

    widened = _who_to_tell("f64", "i64")
    assert "against this engine's package" in widened
    assert "this engine widened it" in widened
    crossed = _who_to_tell("date", "f64")
    assert "against this engine's package and against" in crossed
    assert "the producer that wrote the record" in crossed


def test_a_record_disagreement_reaches_the_reader_through_a_run() -> None:
    """The same two sentences where a reader meets them, which is a refused run.

    A reading asserted only by calling it can be disconnected from the report
    and stay green: the sentence is still correct and nothing carries it. So
    both directions are taken end to end, through a document whose record
    states a type the lowering does not answer -- a division of two doubles,
    recorded as a whole number and as a calendar day.
    """
    halved = {
        "op": "binop",
        "kind": "div",
        "left": _column("a"),
        "right": _column("b"),
    }
    book = {
        "a": {"dtype": "f64", "values": [1.0]},
        "b": {"dtype": "f64", "values": [2.0]},
    }
    widened = refused(halved, book, "i64")
    assert "answer@1 is recorded as i64" in widened
    assert "this engine widened it" in widened
    assert "8.2" in widened
    crossed = refused(halved, book, "date")
    assert "answer@1 is recorded as date" in crossed
    assert "and against the producer that wrote the record" in crossed
    assert "8.2" in crossed
