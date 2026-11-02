# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Padding beyond a policy's horizon changes nothing before it.

A book of term policies has hundreds of distinct period counts, and one
compiled program per count is a quarter of an hour of compiling. So each
policy's arrays are padded up to a bucket and each policy's own count travels
beside them -- and every operation whose value at one position can depend on a
later or an aggregate position has to be told where that policy stops.

**The witness is the whole argument.** A position-local formula fills the
padded cells with something: ``rate + 0.05`` is 0.05 in every cell past the
horizon, not 0. An operation that folds backwards, reduces, shifts or selects
then reads those cells unless it masks them first, and the answer moves. So
each such identifier is run twice over one two-period case -- once in a
two-cell bucket, where there is no padding at all, and once in a four-cell
bucket, where there is -- and the two published answers have to be the same.

**One witness per identifier, not one per class.** A class is an argument
about what an operation does; a witness is a test of what this engine's
lowering of it does. The two part company one lowering at a time.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl
import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio_jax import horizon as horizon_module
from gaspatchio_jax.capability import CROSSING_CLASSES
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.lowerings import LOWERINGS, load
from tests.conftest import entry, invocation

load()

# Every identifier whose value at a position can depend on a later or an
# aggregate position -- read off the registrations rather than listed here, so
# an identifier registered into a crossing class without a witness fails.
CROSSING = sorted(
    capability.identifier
    for _lowering, capability in LOWERINGS.values()
    if capability.horizon in CROSSING_CLASSES
)

# The two-period operand set each witness runs over. Every one of them is
# built so that the cells beyond the horizon would be **non-neutral** if
# nothing masked them: the per-period operand is a position-local formula over
# the axis, so a padded cell carries 0.05, or 100.0, or 2.0, and not 0.
_AXIS = {"dtype": "list[f64]", "values": [[0.0, 0.0]]}
# A second axis whose two real cells are *not* what the padding is. The three
# witnesses that turn on a value rather than on a count need it: a minimum
# over ``axis + 0.05`` where the axis is all zeros reads the same 0.05 in a
# padded cell as in a real one, so it passes with the masking removed and
# witnesses nothing.
_SPAN = {"dtype": "list[f64]", "values": [[1.0, 2.0]]}
_TERM = {"dtype": "i64", "values": [12]}
_INCEPTION = {"dtype": "date", "values": ["2024-01-31"]}

# A rate of 0.05 at every cell of the bucket: ``axis + 0.05`` over an axis of
# zeros. The padded cells are 0.05 exactly like the real ones, which is what
# a reverse fold or a reduction reads if it does not mask.
_OVER_THE_SPAN = {
    "op": "binop",
    "kind": "add",
    "left": {"op": "col", "name": "span"},
    "right": {"op": "lit", "value": 0.05},
}
# And the same over the span: 1.05 and 2.05 at the real cells, 0.05 at every
# padded one -- so a least that read the padding would answer 0.05 and a
# selection that resolved a position against the bucket would reach it. The
# greatest needs the other sign, because a padded cell has to be *outside* the
# real range in the direction the fold looks: ``0 - span`` is -1 and -2 at the
# real cells and 0 at every padded one.
_UNDER_THE_SPAN = {
    "op": "binop",
    "kind": "sub",
    "left": {"op": "lit", "value": 0.0},
    "right": {"op": "col", "name": "span"},
}
_RATE = {
    "op": "binop",
    "kind": "add",
    "left": {"op": "col", "name": "axis"},
    "right": {"op": "lit", "value": 0.05},
}
# A cashflow of 100.0 at every cell, by the same route.
_CASHFLOW = {
    "op": "binop",
    "kind": "add",
    "left": {"op": "col", "name": "axis"},
    "right": {"op": "lit", "value": 100.0},
}
# The fill a shift puts at the boundary it exposes, written into the formula.
_FILL = {"op": "lit", "value": 0.0}

# A multiplicative operand of 2.0 at every cell, for the products.
_FACTOR = {
    "op": "binop",
    "kind": "add",
    "left": {"op": "col", "name": "axis"},
    "right": {"op": "lit", "value": 2.0},
}


def _sealed_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    """Return one schedule recipe under the digest its own content is hashed to."""
    sealed = entry("schedule", payload)
    return {
        "kind": "schedule",
        "source_sha": sealed["fingerprint"],
        "payload": payload,
    }


# The schedule a generator emits to, in each of its three kinds. Two periods,
# so a four-cell bucket pads by two.
_CALENDAR_SCHEDULE = _sealed_schedule(
    {
        "kind": "from_calendar_grid",
        "anchor": "exact_date",
        "calendar": "NullCalendar",
        "convention": "Unadjusted",
        "day_count": "OneTwelfth",
        "frequency": "6M",
        "n_periods": 2,
        "start_date": "2024-01-31",
    }
)
_INCEPTION_SCHEDULE = _sealed_schedule(
    {
        "kind": "from_inception",
        "calendar": "NullCalendar",
        "convention": "Unadjusted",
        "day_count": "OneTwelfth",
        "frequency": "6M",
        "inception_column": "inception",
        "n_periods": 2,
    }
)
_TERM_SCHEDULE = _sealed_schedule(
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
    }
)


def _call(
    name: str,
    args: list[dict[str, Any]],
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one call tree, as the executable profile writes it."""
    return {"op": "call", "name": name, "args": args, "attrs": attrs or {}}


def _over_the_schedule(
    name: str,
    recipe: dict[str, Any],
    args: list[dict[str, Any]],
    dtype: str,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one schedule-family witness: the call, its inputs and its recipe."""
    inputs: dict[str, Any] = {"axis": dict(_AXIS)}
    if recipe is _INCEPTION_SCHEDULE:
        inputs["inception"] = dict(_INCEPTION)
    if recipe is _TERM_SCHEDULE:
        inputs["term"] = dict(_TERM)
    stated = {"schedule": recipe["source_sha"], **(attrs or {})}
    return {
        "tree": _call(name, args, stated),
        "inputs": inputs,
        "assumptions": [recipe],
        "dtype": dtype,
        "column": "answer",
    }


def _over_the_axis(
    tree: dict[str, Any],
    dtype: str,
    extra: dict[str, Any] | None = None,
    column: str = "answer",
) -> dict[str, Any]:
    """Return one witness over the two-period axis alone."""
    return {
        "tree": tree,
        "inputs": {"axis": dict(_AXIS), **(extra or {})},
        "assumptions": [],
        "dtype": dtype,
        "column": column,
    }


WITNESS: dict[str, dict[str, Any]] = {
    "sum": _over_the_axis(_call("sum", [_CASHFLOW]), "f64"),
    "mean": _over_the_axis(_call("mean", [_CASHFLOW]), "f64"),
    "min": _over_the_axis(
        _call("min", [_OVER_THE_SPAN]), "f64", extra={"span": dict(_SPAN)}
    ),
    "max": _over_the_axis(
        _call("max", [_UNDER_THE_SPAN]), "f64", extra={"span": dict(_SPAN)}
    ),
    "cum_sum": _over_the_axis(
        _call("cum_sum", [_CASHFLOW], {"reverse": True}), "list[f64]"
    ),
    "cum_prod": _over_the_axis(
        _call("cum_prod", [_FACTOR], {"reverse": True}), "list[f64]"
    ),
    "projection.remaining_sum": _over_the_axis(
        _call("projection.remaining_sum", [_CASHFLOW]), "list[f64]"
    ),
    "projection.prospective_value": _over_the_axis(
        _call(
            "projection.prospective_value",
            [_CASHFLOW, _RATE],
            {"discount_kind": "rate", "timing": "beginning_of_period"},
        ),
        "list[f64]",
    ),
    "projection.previous_period": _over_the_axis(
        _call("projection.previous_period", [_CASHFLOW, _FILL]),
        "list[f64]",
    ),
    "projection.next_period": _over_the_axis(
        _call("projection.next_period", [_CASHFLOW, _FILL]),
        "list[f64]",
    ),
    "projection.at_period": _over_the_axis(
        _call("projection.at_period", [_CASHFLOW, _FILL], {"relative_period": 1}),
        "list[f64]",
    ),
    "list.get": _over_the_axis(
        _call("list.get", [_OVER_THE_SPAN, {"op": "lit", "value": -1}]),
        "f64",
        extra={"span": dict(_SPAN)},
    ),
    # Reversed across the bucket, the answer would open on a padded 0.05
    # rather than on the policy's own last period, 2.05.
    "list.reverse": _over_the_axis(
        _call("list.reverse", [_OVER_THE_SPAN]),
        "list[f64]",
        extra={"span": dict(_SPAN)},
    ),
    # Run back from the bucket's last cell without the mask, the carry would
    # step through two padded cells -- growth 0.05, addend 100 -- before it
    # reached the policy's last period, and open there on 100.05 rather than 1.
    "projection.accumulate": _over_the_axis(
        _call(
            "projection.accumulate",
            [{"op": "col", "name": "opening"}, _OVER_THE_SPAN, _CASHFLOW],
            {"reverse": True},
        ),
        "list[f64]",
        extra={"span": dict(_SPAN), "opening": {"dtype": "f64", "values": [1.0]}},
    ),
    "projection.with_period": _over_the_axis(
        _call("projection.with_period", [_CASHFLOW], {"period": -1, "value": 9.0}),
        "list[f64]",
    ),
    "projection.broadcast_to_periods": _over_the_axis(
        _call(
            "projection.broadcast_to_periods",
            [{"op": "lit", "value": 7.0}, {"op": "col", "name": "axis"}],
        ),
        "list[f64]",
    ),
    "projection_set": _over_the_axis(
        _call(
            "projection_set",
            [{"op": "col", "name": "term"}],
            {
                "frequency": "monthly",
                "until": "term_months",
                "until_value": "term",
                "valuation_date": "2024-01-31",
            },
        ),
        "list[i64]",
        extra={"term": {"dtype": "i64", "values": [2]}},
        column="month",
    ),
    "projection_frame.period_dates": _over_the_schedule(
        "projection_frame.period_dates", _CALENDAR_SCHEDULE, [], "list[date]"
    ),
    "projection_frame.year_fractions": _over_the_schedule(
        "projection_frame.year_fractions", _CALENDAR_SCHEDULE, [], "list[f64]"
    ),
    "projection_frame.t_years": _over_the_schedule(
        "projection_frame.t_years", _CALENDAR_SCHEDULE, [], "list[f64]"
    ),
    "projection_frame.anniversary_mask": _over_the_schedule(
        "projection_frame.anniversary_mask", _CALENDAR_SCHEDULE, [], "list[bool]"
    ),
    "schedule.period_dates": _over_the_schedule(
        "schedule.period_dates",
        _INCEPTION_SCHEDULE,
        [{"op": "col", "name": "inception"}],
        "list[date]",
    ),
    "schedule.per_policy_period_dates": _over_the_schedule(
        "schedule.per_policy_period_dates",
        _TERM_SCHEDULE,
        [{"op": "col", "name": "term"}],
        "list[date]",
    ),
    "schedule.per_policy_period_count": _over_the_schedule(
        "schedule.per_policy_period_count",
        _TERM_SCHEDULE,
        [{"op": "col", "name": "term"}],
        "i64",
    ),
    "schedule.year_fractions": _over_the_schedule(
        "schedule.year_fractions", _CALENDAR_SCHEDULE, [], "list[f64]"
    ),
    "schedule.anniversary_mask": _over_the_schedule(
        "schedule.anniversary_mask", _INCEPTION_SCHEDULE, [], "list[bool]"
    ),
    "schedule.is_in_force": _over_the_schedule(
        "schedule.is_in_force",
        _INCEPTION_SCHEDULE,
        [],
        "list[bool]",
        {"end_date_column": None},
    ),
    "schedule.contract_boundary": _over_the_schedule(
        "schedule.contract_boundary",
        _INCEPTION_SCHEDULE,
        [],
        "list[bool]",
        {"end_date_column": None},
    ),
    "date.date_ranges": _over_the_axis(
        _call(
            "date.date_ranges",
            [{"op": "col", "name": "opened"}, {"op": "col", "name": "closed"}],
            {"interval": "6mo", "closed": "both"},
        ),
        "list[date]",
        extra={
            "opened": {"dtype": "date", "values": ["2024-01-31"]},
            "closed": {"dtype": "date", "values": ["2025-01-31"]},
        },
    ),
}


def _at_bucket(width: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix the bucket grid at one width, so padding is this test's choice."""
    monkeypatch.setattr(horizon_module, "BUCKETS", (width,))


def run_one(
    identifier: str,  # noqa: ARG001 -- named so a failure says which witness
    case: dict[str, Any],
    bucket: int,
) -> list[Any]:
    """Return what this engine publishes for one witness at one bucket width."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        _at_bucket(bucket, monkeypatch)
        built = invocation(
            case["tree"],
            case["inputs"],
            case["dtype"],
            assumptions=case["assumptions"],
            output_column=case["column"],
        )
        result = JaxEngine().run(built.document, built.inputs, FrameSink())
        return result.columns[case["column"]].to_list()
    finally:
        monkeypatch.undo()


def trimmed(published: list[Any]) -> str:
    """Return one published column in a form two runs can be compared by.

    Publication already cuts every row to that policy's own periods, so what
    this does is put the answer in one canonical text: a float and its
    repeated decimal expansion compare better as their own digits than as a
    tuple of objects a date and a NaN both live in.
    """
    return json.dumps(published, default=str)


# The directions a registration covers that its one witness does not. 11.1.9
# makes the direction part of the calculation, so the forward fold is a second
# case of the same identifier rather than a second identifier.
ALSO = {
    "cum_sum-forward": _over_the_axis(
        _call("cum_sum", [_CASHFLOW], {"reverse": False}), "list[f64]"
    ),
    "cum_prod-forward": _over_the_axis(
        _call("cum_prod", [_FACTOR], {"reverse": False}), "list[f64]"
    ),
    "projection.accumulate-forward": _over_the_axis(
        _call(
            "projection.accumulate",
            [{"op": "col", "name": "opening"}, _OVER_THE_SPAN, _CASHFLOW],
            {"reverse": False},
        ),
        "list[f64]",
        extra={"span": dict(_SPAN), "opening": {"dtype": "f64", "values": [1.0]}},
    ),
}


@pytest.mark.parametrize("identifier", [*CROSSING, *sorted(ALSO)], ids=str)
def test_padding_beyond_the_horizon_changes_nothing_before_it(identifier: str) -> None:
    """One witness per crossing identifier, at two bucket widths."""
    case = WITNESS.get(identifier) or ALSO[identifier]
    actual = run_one(identifier, case, bucket=2)
    padded = run_one(identifier, case, bucket=4)
    assert trimmed(padded) == trimmed(actual), identifier


def test_the_review_s_model_is_right_in_a_bucket() -> None:
    """A two-period model, against the number the clause itself gives.

    A cashflow of 100 over two periods: the remaining sum is [200, 100] and
    the prospective value at a rate of 0.05, beginning of period, is the
    number the producer computes. The rate is **not** zero, so an engine that
    left the padded rate cells unmasked would divide by a longer product of
    discount factors than the policy has periods and this would move.
    """
    remaining = run_one(
        "projection.remaining_sum", WITNESS["projection.remaining_sum"], bucket=4
    )
    assert remaining == [[200.0, 100.0]]
    value = run_one(
        "projection.prospective_value",
        WITNESS["projection.prospective_value"],
        bucket=4,
    )
    expected = [100.0 + 100.0 / 1.05, 100.0]
    assert value[0] == pytest.approx(expected, abs=1e-12)


def test_reductions_are_sequential_scans() -> None:
    """One masked sum, two bucket widths, bit for bit.

    A reduction whose order XLA is free to choose reassociates differently at
    two static shapes, and a masked sum of these same eighty-three values
    moves one unit in the last place between two buckets when it is free to.
    A sequential scan has one order whatever the shape is, so the two answers
    are the same bits.
    """
    tree = _call(
        "sum",
        [
            {
                "op": "binop",
                "kind": "add",
                "left": {"op": "col", "name": "axis"},
                "right": {"op": "lit", "value": 0.1},
            }
        ],
    )
    case = {
        "tree": tree,
        "inputs": {
            "axis": {
                "dtype": "list[f64]",
                "values": [[float(one) / 7.0 for one in range(83)]],
            }
        },
        "assumptions": [],
        "dtype": "f64",
        "column": "answer",
    }
    narrow = run_one("sum", case, bucket=128)
    wide = run_one("sum", case, bucket=360)
    assert narrow[0].hex() == wide[0].hex()


def test_a_bucket_is_the_smallest_on_the_grid_that_holds_the_horizon() -> None:
    """The grid is a grid: a horizon takes the next width up, never its own."""
    assert horizon_module.bucket_of(1) == horizon_module.BUCKETS[0]
    assert horizon_module.bucket_of(83) == 84
    assert horizon_module.bucket_of(84) == 84
    assert horizon_module.bucket_of(85) == 120
    # Past the grid there is no rounding left to do, and a horizon that long
    # takes its own width rather than one the grid does not carry.
    assert horizon_module.bucket_of(5000) == 5000


def test_every_registration_states_where_it_stands_to_the_period_axis() -> None:
    """A per-period registration is in one of the seven classes, never elsewhere.

    The point of the classification is that it is exhaustive: an identifier
    that produces or reads a per-period value and declares ``local`` is
    claiming that no position of its answer depends on any other position,
    and that claim is made on the registration rather than left inside the
    lowering where nobody reads it.
    """
    for name, (_lowering, capability) in sorted(LOWERINGS.items()):
        admits = capability.shapes is None or any(
            "list" in admitted for admitted in capability.shapes
        )
        if admits and capability.horizon == "local":
            assert name in _POSITION_LOCAL, name
        if capability.horizon != "local":
            assert name not in _POSITION_LOCAL, name


# The per-period identifiers that genuinely are position-local: each cell of
# the answer is a function of that cell of the operands and of nothing else,
# so padding cannot reach a position before the horizon.
_POSITION_LOCAL = frozenset(
    {
        "join",
        "str.to_date",
        "to_text",
        "date.months_between",
        "date.offset_by",
        "date.to_period",
        "excel.days",
        "excel.edate",
        "excel.eomonth",
        "excel.from_excel_serial",
        "excel.pv",
        "add",
        "sub",
        "mul",
        "div",
        "floordiv",
        "mod",
        "pow",
        "lt",
        "le",
        "gt",
        "ge",
        "eq",
        "ne",
        "and",
        "or",
        "not_",
        "abs",
        "sign",
        "sqrt",
        "cbrt",
        "exp",
        "log",
        "log10",
        "log1p",
        "norm_cdf",
        "round_sig_figs",
        "round",
        "floor",
        "ceil",
        "clip",
        "cut",
        "is_in",
        "replace",
        "fill_nan",
        "fill_null",
        "is_null",
        "is_not_null",
        "is_nan",
        "is_not_nan",
        "is_finite",
        "is_infinite",
        "when_then",
        "to_integer",
        "to_float",
        "to_list",
        "lookup",
        "mortality.at",
        "finance.to_monthly",
        "finance.compound",
        "finance.discount",
        "finance.present_value",
        "curve.spot_rate",
        "curve.discount_factor",
        "excel.round",
        "excel.yearfrac",
        "excel.irr",
    }
)


def test_the_witness_set_is_the_crossing_set() -> None:
    """Every crossing identifier has a witness, and no witness is for nothing."""
    assert sorted(WITNESS) == CROSSING


def test_a_horizon_masks_to_the_neutral_the_operation_asks_for() -> None:
    """The mask is the operation's own neutral, not a zero for everything."""
    import jax.numpy as jnp

    from gaspatchio_jax.typed import Value

    axis = horizon_module.Horizon.over(jnp.asarray([2, 1]), bucket=4)
    value = Value(jnp.full((2, 4), 3.0), "f64", "list", "f64", axis)
    summed = horizon_module.mask_to_neutral(value, axis, 0.0)
    multiplied = horizon_module.mask_to_neutral(value, axis, 1.0)
    assert summed.array.sum().item() == pytest.approx(9.0)
    assert multiplied.array.prod(axis=1).tolist() == pytest.approx([9.0, 3.0])


def test_a_published_column_carries_each_policy_s_own_periods() -> None:
    """The bucket is the engine's; what leaves is the policy's own timeline."""
    published = run_one(
        "projection.remaining_sum",
        {
            "tree": _call("projection.remaining_sum", [_CASHFLOW]),
            "inputs": {"axis": {"dtype": "list[f64]", "values": [[0.0, 0.0], [0.0]]}},
            "assumptions": [],
            "dtype": "list[f64]",
            "column": "answer",
        },
        bucket=4,
    )
    assert published == [[200.0, 100.0], [100.0]]
    assert pl.Series(published).dtype == pl.List(pl.Float64)


# One per-period invocation per declared check that a position-local lowering
# can raise, each written so the *real* cells are clean and the padded ones
# would not be. Read off nothing: a check a lowering raises and this list does
# not carry is a check nobody has shown is held to the horizon, so the test
# below asserts the two agree.
OVER_THE_PADDING: dict[str, dict[str, Any]] = {
    "floordiv.zero_divisor": {
        "tree": {
            "op": "binop",
            "kind": "floordiv",
            "left": {"op": "col", "name": "whole"},
            "right": {"op": "col", "name": "divisor"},
        },
        "dtype": "list[i64]",
    },
    "i64.range": {
        "tree": {
            "op": "binop",
            "kind": "mul",
            "left": {"op": "col", "name": "huge"},
            "right": {"op": "col", "name": "huge"},
        },
        "dtype": "list[i64]",
    },
    "to_integer.integral": {
        "tree": _call(
            "to_integer",
            [
                {
                    "op": "binop",
                    "kind": "add",
                    "left": {"op": "col", "name": "half"},
                    "right": {"op": "lit", "value": 0.5},
                }
            ],
        ),
        "dtype": "list[i64]",
    },
    "to_float.exact": {
        "tree": _call("to_float", [{"op": "col", "name": "wide"}]),
        "dtype": "list[f64]",
    },
    # A count one less than ``wide``: 0 and 1 at the two real periods, and -1
    # over every padded cell, where no period is.
    "excel.pv.periods": {
        "tree": _call(
            "excel.pv",
            [
                {"op": "col", "name": "ratio"},
                {
                    "op": "binop",
                    "kind": "sub",
                    "left": {"op": "col", "name": "wide"},
                    "right": {"op": "lit", "value": 1},
                },
                {"op": "col", "name": "half"},
            ],
            {"fv": 50.0, "typ": 0},
        ),
        "dtype": "list[f64]",
    },
    "mixed.2p53": {
        "tree": {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "wide"},
            "right": {"op": "lit", "value": 0.5},
        },
        "dtype": "list[f64]",
    },
    "comparison.unknown": {
        "tree": {
            "op": "when_then",
            "cond": {
                "op": "binop",
                "kind": "lt",
                "left": {"op": "col", "name": "ratio"},
                "right": {"op": "lit", "value": 1.0},
            },
            "then": {"op": "col", "name": "whole"},
            "otherwise": {"op": "col", "name": "divisor"},
        },
        "dtype": "list[i64]",
    },
    "cut.nan": {
        "tree": _call(
            "cut",
            [
                {"op": "col", "name": "ratio"},
                {"op": "lit", "values": [0.3]},
                {"op": "lit", "values": ["low", "high"]},
            ],
            {"left_closed": False, "include_breaks": False},
        ),
        "dtype": "list[str]",
    },
    "excel.round.scale": {
        "tree": _call(
            "excel.round", [{"op": "col", "name": "ratio"}], {"num_digits": 2}
        ),
        "dtype": "list[f64]",
    },
    "excel.round.sixteenth": {
        "tree": _call(
            "excel.round", [{"op": "col", "name": "ratio"}], {"num_digits": 2}
        ),
        "dtype": "list[f64]",
    },
    "excel.irr.bracket": {
        "tree": _call(
            "excel.irr", [{"op": "col", "name": "stream"}], {"default_guess": None}
        ),
        "dtype": "f64",
    },
    "excel.irr.no_sign_change": {
        "tree": _call(
            "excel.irr", [{"op": "col", "name": "stream"}], {"default_guess": None}
        ),
        "dtype": "f64",
    },
    "excel.irr.several_roots": {
        "tree": _call(
            "excel.irr", [{"op": "col", "name": "stream"}], {"default_guess": None}
        ),
        "dtype": "f64",
    },
    "to_monthly.rate": {
        "tree": _call(
            "finance.to_monthly",
            [{"op": "col", "name": "ratio"}],
            {"method": "compound"},
        ),
        "dtype": "list[f64]",
    },
    "pow.integer_exponent": {
        "tree": {
            "op": "binop",
            "kind": "pow",
            "left": {"op": "col", "name": "huge"},
            "right": {"op": "col", "name": "huge"},
        },
        # 11.1.25: every list-shaped power answers f64, whatever it was
        # written over.
        "dtype": "list[f64]",
    },
    "pow.list_exponent_sign": {
        "tree": {
            "op": "binop",
            "kind": "pow",
            "left": {"op": "lit", "value": 2.0},
            "right": {"op": "col", "name": "ratio"},
        },
        "dtype": "list[f64]",
    },
    "predicate.stored_f64": {
        "tree": {
            "op": "when_then",
            "cond": {"op": "col", "name": "indicator"},
            "then": {"op": "lit", "value": 1.0},
            "otherwise": {"op": "lit", "value": 2.0},
        },
        "dtype": "list[f64]",
    },
}

# The book every one of them runs over: two real periods, clean in every
# column, in a bucket that pads them out.
_CLEAN_PERIODS: dict[str, Any] = {
    "whole": {"dtype": "list[i64]", "values": [[-7, 7]]},
    "divisor": {"dtype": "list[i64]", "values": [[3, -3]]},
    "huge": {"dtype": "list[i64]", "values": [[2, 3]]},
    "half": {"dtype": "list[f64]", "values": [[0.5, 1.5]]},
    "wide": {"dtype": "list[i64]", "values": [[1, 2]]},
    "ratio": {"dtype": "list[f64]", "values": [[0.25, 0.5]]},
    "indicator": {"dtype": "list[f64]", "values": [[1.0, 0.0]]},
    "stream": {"dtype": "list[f64]", "values": [[-100.0, 110.0]]},
}


@pytest.mark.parametrize("check", sorted(OVER_THE_PADDING), ids=str)
def test_no_check_is_read_over_a_cell_that_is_not_a_period(check: str) -> None:
    """Every declared check a position-local lowering raises, over the padding.

    A position-local operation does not mask its *values* -- correctly, since
    padding cannot reach a position before the horizon -- so its checks are
    the ones that would see the carrier's own zero in cells nobody wrote: a
    divisor of nought, a half that is not whole, a magnitude at the edge of a
    type. Each case here is clean at every real period and is run in a bucket
    six cells wider than its two, so anything that refuses is refusing about
    the bucket.
    """
    case = OVER_THE_PADDING[check]
    published = run_one(
        check,
        {
            "tree": case["tree"],
            "inputs": _CLEAN_PERIODS,
            "assumptions": [],
            "dtype": case["dtype"],
            "column": "answer",
        },
        bucket=8,
    )
    assert len(published) == 1
    if isinstance(published[0], list):
        assert len(published[0]) == 2


def test_the_checks_over_the_padding_are_the_ones_a_local_lowering_raises() -> None:
    """The list above is the position-local registrations' own declared checks.

    Read off the registrations rather than kept by hand, so a check a new
    position-local lowering declares and this file does not carry fails here
    rather than going unwitnessed.
    """
    declared: set[str] = set()
    for name, (_lowering, capability) in LOWERINGS.items():
        if capability.horizon != "local" or name in _NOT_OVER_PERIODS:
            continue
        declared |= set(capability.checks)
    assert declared - set(OVER_THE_PADDING) == set()


# The position-local registrations whose operands are per policy by
# declaration, so no per-period invocation of them exists to check: the two
# host stages, the three reads that select a row, the two finance
# conversions 11.1.29 states scalar operands only for, and the spreadsheet
# serial 11.1.33 states over one value per policy.
_NOT_OVER_PERIODS = frozenset(
    {
        "excel.from_excel_serial",
        "to_text",
        "str.to_date",
        "lookup",
        "mortality.at",
        "join",
        "finance.discount",
        "finance.present_value",
    }
)


def test_an_axis_minted_inside_a_trace_from_a_traced_count_refuses_to_be_built() -> (
    None
):
    """A width read from a traced value raises; it does not guess one.

    This is the guard behind the whole division between what a program is
    built around and what it is handed. ``t`` may be a traced argument --
    that is what lets one program serve every batch of a group -- but only
    where the caller also hands over the counts read on the host, because the
    bucket and the comparison of two timelines are settled while the program
    is being built. Asked to size an axis from a value only the program will
    know, this refuses rather than picking a width, which is why a
    mis-grouped batch is not a failure mode the engine has.
    """
    import jax
    import jax.numpy as jnp
    import numpy as np

    from gaspatchio_jax.horizon import Horizon

    with pytest.raises(jax.errors.TracerArrayConversionError):
        jax.make_jaxpr(lambda t: Horizon.over(t).active)(jnp.asarray([3, 5]))

    # And with the host counts beside them it builds, over the traced cells.
    built = jax.make_jaxpr(
        lambda t: Horizon.over(t, bucket=12, host=np.asarray([3, 5])).active
    )(jnp.asarray([3, 5]))
    assert built.jaxpr.eqns
