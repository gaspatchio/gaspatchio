# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every integer operation against a Python-integer oracle, over the boundaries.

Python's integers have no range, so they are the oracle: for every pair from
the grid below, this engine either answers exactly what Python answers or
refuses by name. There is no third outcome, and in particular there is no
wrapped answer -- which is the whole of what section 11.1.25's "a consumer
claiming only this domain must refuse it" asks for.

The grid is the boundaries and nothing between them: the type's two ends and
their neighbours, the double's ±2⁵³, the coarse product flag's 2⁶², the two
widths an actuary's own integers live at, and the small signs.
"""

from __future__ import annotations

import itertools
import operator

import pytest

from gaspatchio_jax.typed import INT64_MAX, INT64_MIN
from tests.conftest import ScalarOutcome, answered, invocation, run_scalar, run_unary
from tests.test_quotients import on_a_card, power_held

ORACLE = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "floordiv": operator.floordiv,
    "mod": operator.mod,
}

BOUNDARY = [
    INT64_MIN,
    INT64_MIN + 1,
    -(2**62),
    -1,
    0,
    1,
    2**31,
    2**32 + 1,
    2**53 - 1,
    2**53,
    2**62,
    INT64_MAX - 1,
    INT64_MAX,
]


@pytest.mark.parametrize("op", ["add", "sub", "mul", "floordiv", "mod"])
def test_every_binary_integer_operation_matches_a_python_integer_oracle_or_refuses(
    op: str,
) -> None:
    for a, b in itertools.product(BOUNDARY, repeat=2):
        if op in ("floordiv", "mod") and b == 0:
            continue  # the zero-divisor case has its own test
        expected = ORACLE[op](a, b)
        outcome = run_scalar(op, a, b)
        if INT64_MIN <= expected <= INT64_MAX:
            assert outcome.value == expected, (op, a, b, outcome.report)
        else:
            assert outcome.refused_with == "i64.range", (op, a, b, outcome.report)


def test_int64_min_floordiv_minus_one_refuses() -> None:
    assert run_scalar("floordiv", INT64_MIN, -1).refused_with == "i64.range"


def test_a_zero_divisor_refuses_rather_than_minting_a_null() -> None:
    for op in ("floordiv", "mod"):
        outcome = run_scalar(op, 7, 0)
        assert outcome.refused_with == "floordiv.zero_divisor", (op, outcome.report)


def test_int64_min_neg_and_abs_refuse() -> None:
    assert run_unary("abs", INT64_MIN).refused_with == "i64.range"
    assert run_scalar("sub", 0, INT64_MIN).refused_with == "i64.range"


def test_a_nested_overflow_refuses_even_where_the_final_value_fits() -> None:
    """(INT64_MAX + 1) - 1 fits, and the step that made it did not."""
    from tests.conftest import answered, invocation

    outcome = answered(
        invocation(
            {
                "op": "binop",
                "kind": "sub",
                "left": {
                    "op": "binop",
                    "kind": "add",
                    "left": {"op": "col", "name": "a"},
                    "right": {"op": "lit", "value": 1},
                },
                "right": {"op": "lit", "value": 1},
            },
            {"a": {"dtype": "i64", "values": [INT64_MAX]}},
            "i64",
        )
    )
    assert outcome.refused_with == "i64.range"


def test_pow_with_integer_exponent_matches_the_oracle_or_refuses() -> None:
    assert run_scalar("pow", 3, 39).value == 3**39
    assert run_scalar("pow", 3, 40).refused_with == "i64.range"
    assert run_scalar("pow", 2, 62).value == 2**62
    assert run_scalar("pow", 2, 63).refused_with == "i64.range"
    assert run_scalar("pow", 1, 2**33).refused_with == "pow.integer_exponent"
    assert run_scalar("pow", 2, -1).refused_with == "pow.integer_exponent"


def _raised_to_a_written(exponent: int, base: int = 2) -> ScalarOutcome:
    """Return ``a ** <literal>`` over one i64 policy, the record's type as stated."""
    return answered(
        invocation(
            {
                "op": "binop",
                "kind": "pow",
                "left": {"op": "col", "name": "a"},
                "right": {"op": "lit", "value": exponent},
            },
            {"a": {"dtype": "i64", "values": [base]}},
            "f64",
        )
    )


def test_an_integer_raised_to_a_written_negative_exponent_is_a_double() -> None:
    """11.1.25 keeps an integer power only for an exponent in [0, 2**32 - 1].

    A literal exponent outside it is in the record, so the answer is the
    binary64 power, as the reference producer's ``af.a ** -1`` answers it:
    the exponent written as a column still takes the integer rule above.

    The answer is that power: the producer's to the bit on the CPU, and on a
    card within 11.1.25's relative 1e-12 for a power, the device's ``pow``
    sitting a place from the library's (a T4 answered ``4 ** -2`` as
    ``0.06249999999999999``).
    """
    cases = [((-1, 2), 0.5), ((-2, 4), 0.0625), ((-1, 3), 1 / 3), ((2**32, 1), 1.0)]
    got = [
        _raised_to_a_written(exponent, base=base).value for (exponent, base), _ in cases
    ]
    assert all(isinstance(value, float) for value in got), got
    assert power_held(got, [want for _, want in cases], card=on_a_card()), got


@pytest.mark.parametrize(("base", "exponent"), [(2, -1), (1, 2**33)])
def test_an_exponent_column_past_the_range_names_to_float_on_either_operand(
    base: int, exponent: int
) -> None:
    """The refusal's move is the one the Polars path names: to_float() on an operand.

    The answer type of ``a ** k`` over two integer columns is still i64, so
    the engine refuses rather than answering a double the record does not
    state; what the author writes instead is the floating-point power.
    """
    outcome = run_scalar("pow", base, exponent)
    assert outcome.refused_with == "pow.integer_exponent"
    assert (
        "write to_float() on either operand -- base.to_float() ** exponent, "
        "or base ** exponent.to_float() --" in outcome.report
    )


def test_a_coarse_product_flag_that_the_host_clears_publishes_its_value() -> None:
    """2^62 times 1 trips the coarse threshold and is exactly in range."""
    assert run_scalar("mul", 2**62, 1).value == 2**62


def test_floor_is_not_truncation_at_the_signs() -> None:
    assert run_scalar("floordiv", -7, 3).value == -3
    assert run_scalar("mod", -7, 3).value == 2
    assert run_scalar("mod", 7, -3).value == -2
