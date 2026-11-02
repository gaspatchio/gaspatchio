# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period flag is a run of Booleans, and every line that reads one agrees.

``when(af.month < af.term).then(True).otherwise(af.rider_active)`` is an
in-force flag per period. Three things about such a run used to depend on the
route the line took rather than on what it meant:

- a conditional with two Boolean branches came back as 0/1 doubles on every
  per-period route, where the per-policy route (``pl.when``) and the second
  engine keep a Boolean, as section 11.1.28 types it;
- arithmetic over a per-period flag refused with "failed to materialize
  unknown type" for ``flag * 1.0`` and ``flag - 0.5``, worked for
  ``1.0 * flag``, and gave Int32 for ``flag + 1`` and UInt64 for
  ``flag * flag``;
- a period shift filled the run's edge with its numeric default and failed
  with the same opaque sentence.

Now the conditional keeps its Booleans, arithmetic reads a flag as 0.0 or 1.0
whatever the operator or operand order, and a shift asks for a flag to fill
with, by name.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Final

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

# A flag written into a formula, named so the line reads as a model line does.
ON: Final = True
OFF: Final = False

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio.column.expression_proxy import ExpressionProxy


def _a_book() -> ActuarialFrame:
    """Return one policy over four periods, holding a per-period flag."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["A"],
                "rider": [True],
                "x": [2.0],
                "flags": [[True, False, True, True]],
            }
        )
    )
    return af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )


# --- a conditional over two Boolean branches ---------------------------------


@pytest.mark.parametrize(
    ("route", "line", "expected"),
    [
        (
            "comparison",
            lambda af: when(af.month > 1).then(ON).otherwise(af.rider),
            [True, True, True, True],
        ),
        (
            "stored mask",
            lambda af: when(af.flags).then(OFF).otherwise(af.rider),
            [False, True, False, False],
        ),
        (
            "per-policy test, per-period branch",
            lambda af: when(af.rider).then(af.flags).otherwise(OFF),
            [True, False, True, True],
        ),
    ],
)
def test_two_boolean_branches_stay_boolean_on_every_per_period_route(
    route: str,
    line: Callable[[ActuarialFrame], ExpressionProxy],
    expected: list[bool],
) -> None:
    """The run holds flags, as the per-policy route and the tree say it does."""
    af = _a_book()
    af.picked = line(af)

    held = af.collect()

    assert held.schema["picked"] == pl.List(pl.Boolean), route
    assert held["picked"].to_list() == [expected], route


def test_a_comparison_written_as_a_branch_stays_an_indicator() -> None:
    """A comparison in value position is the 0/1 double the frame stores for one."""
    af = _a_book()
    af.picked = when(af.rider).then(af.month > 1).otherwise(OFF)

    assert af.collect().schema["picked"] == pl.List(pl.Float64)


# --- arithmetic over a per-period flag ---------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (lambda af: af.flags * 1.0, [1.0, 0.0, 1.0, 1.0]),
        (lambda af: 1.0 * af.flags, [1.0, 0.0, 1.0, 1.0]),
        (lambda af: af.flags - 0.5, [0.5, -0.5, 0.5, 0.5]),
        (lambda af: af.flags + 1, [2.0, 1.0, 2.0, 2.0]),
        (lambda af: 1 - af.flags, [0.0, 1.0, 0.0, 0.0]),
        (lambda af: af.flags * af.flags, [1.0, 0.0, 1.0, 1.0]),
        (lambda af: af.flags * af.x, [2.0, 0.0, 2.0, 2.0]),
        (lambda af: af.flags / 2, [0.5, 0.0, 0.5, 0.5]),
        (lambda af: af.flags // 2, [0.0, 0.0, 0.0, 0.0]),
        (lambda af: af.flags % 2, [1.0, 0.0, 1.0, 1.0]),
        (lambda af: af.flags**2, [1.0, 0.0, 1.0, 1.0]),
    ],
    ids=[
        "flag-times-float",
        "float-times-flag",
        "flag-minus-float",
        "flag-plus-int",
        "int-minus-flag",
        "flag-times-flag",
        "flag-times-column",
        "flag-over-int",
        "flag-floordiv-int",
        "flag-mod-int",
        "flag-power",
    ],
)
def test_a_per_period_flag_reads_as_zero_or_one_in_arithmetic(
    line: Callable[[ActuarialFrame], ExpressionProxy], expected: list[float]
) -> None:
    """One reading, whatever the operator and whichever side the flag is on."""
    af = _a_book()
    af.amount = line(af)

    held = af.collect()

    assert held.schema["amount"] == pl.List(pl.Float64)
    assert held["amount"].to_list() == [expected]


def test_a_flag_a_conditional_produced_reads_as_zero_or_one_too() -> None:
    """The run a Boolean conditional now holds is read the same way."""
    af = _a_book()
    af.in_force = when(af.month < 2).then(ON).otherwise(OFF)
    af.premium = af.in_force * 100.0

    assert af.collect()["premium"].to_list() == [[100.0, 100.0, 0.0, 0.0]]


# --- a period shift over a per-period flag -----------------------------------


@pytest.mark.parametrize(
    ("line", "method"),
    [
        (lambda af: af.flags.projection.previous_period(), "previous_period()"),
        (lambda af: af.flags.projection.next_period(), "next_period()"),
        (lambda af: af.flags.projection.at_period(-2), "at_period()"),
        (
            lambda af: af.flags.projection.previous_period(fill_value=0.0),
            "previous_period()",
        ),
    ],
    ids=["previous", "next", "at", "previous-explicit-number"],
)
def test_a_numeric_fill_on_a_run_of_flags_is_refused_by_name(
    line: Callable[[ActuarialFrame], ExpressionProxy], method: str
) -> None:
    """The default fill is 0.0, and a flag is not a number: the shift says so."""
    af = _a_book()

    with pytest.raises(TypeError) as refused:
        af.shifted = line(af)

    message = str(refused.value)
    assert method in message
    assert "fill_value=False" in message


def test_a_flag_fill_shifts_a_run_of_flags() -> None:
    """The move the refusal names is one the shift accepts."""
    af = _a_book()
    af.before = af.flags.projection.previous_period(fill_value=False)

    held = af.collect()

    assert held.schema["before"] == pl.List(pl.Boolean)
    assert held["before"].to_list() == [[False, True, False, True]]
