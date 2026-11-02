# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``/``, ``//``, ``%`` and ``**`` mean IEEE arithmetic on every shape and engine.

Polars' float kernels, handed a single divisor for a whole array, multiply by
its reciprocal instead of dividing: ``135.021 / 1000`` is
``0.13502099999999997`` but ``135.021 * (1 / 1000)`` is ``0.135021``. Which
formulas met that kernel depended on the engine and on how it split the rows:
a list column over a literal always (inside ``list.eval``), a per-policy or
per-period column over a literal or a constant column on the in-memory engine
-- the one ``profile()``, and so ``gspio run-model --mode debug``, runs -- and
on streaming too once a frame was portfolio-sized. So the same formula gave
different floats by mode and by size. Every numeric quotient now goes through
one kernel that divides each element by its own divisor. A scalar base raised
to a list exponent went through ``exp(e * ln b)``, which reads ``10 ** 14`` as
``100000000000000.12``. The formula is the code: ``/`` is division and ``**``
is power.
"""

from __future__ import annotations

import datetime
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

K = 135.021
D = 1000.0
IEEE = K / D  # 0.13502099999999997
RECIPROCAL = K * (1 / D)  # 0.135021 -- the wrong answer

_ENGINES = ("streaming", "in-memory", "profile")


def _run(af: ActuarialFrame, engine: str) -> pl.DataFrame:
    if engine == "profile":
        return af.profile()[0]
    return af.collect(engine=engine)


def test_the_reciprocal_really_is_a_different_number() -> None:
    """Guard the fixture: without this the tests below could pass vacuously."""
    assert IEEE != RECIPROCAL


@pytest.mark.parametrize("periods", [1, 2, 8])
@pytest.mark.parametrize("divisor", [1000, 1000.0])
@pytest.mark.parametrize("engine", _ENGINES)
def test_list_divided_by_a_literal_is_ieee_division(
    periods: int, divisor: float, engine: str
) -> None:
    af = ActuarialFrame(pl.DataFrame({"k": [[K] * periods] * 3}))
    af.q = af.k / divisor
    out = _run(af, engine)
    assert out["q"].to_list() == [[IEEE] * periods] * 3


@pytest.mark.parametrize("engine", _ENGINES)
def test_list_divided_by_a_constant_column_is_ieee_division(engine: str) -> None:
    """A unit set once for the whole frame (``af.unit = 1000.0``) is the debug-mode trigger."""
    af = ActuarialFrame(pl.DataFrame({"k": [[K] * 4] * 3}))
    af.unit = 1000.0
    af.q = af.k / af.unit
    out = _run(af, engine)
    assert out["q"].to_list() == [[IEEE] * 4] * 3


@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_list_quotients_stay_ieee_on_a_portfolio_sized_frame(engine: str) -> None:
    """How Polars splits the rows decides which kernel a single divisor meets.

    Three policies divided exactly on the streaming engine while a portfolio
    did not, so the small-frame tests above are not enough on their own.
    """
    policies = 50_000
    af = ActuarialFrame(pl.DataFrame({"k": [[K, K]] * policies}))
    af.unit = 1000.0
    af.by_literal = af.k / 1000
    af.by_constant = af.k / af.unit
    out = af.collect(engine=engine)
    for column in ("by_literal", "by_constant"):
        flat = out[column].list.explode(empty_as_null=False)
        assert flat.len() == 2 * policies
        assert (flat == IEEE).all(), column


@pytest.mark.parametrize("policies", [3, 50_000])
@pytest.mark.parametrize("engine", _ENGINES)
def test_per_policy_column_divided_by_a_number_is_ieee_division(
    policies: int, engine: str
) -> None:
    """``af.annual / 12`` and ``af.x / af.unit``: the per-policy half of the defect."""
    af = ActuarialFrame(pl.DataFrame({"x": [K] * policies, "r": [0.03] * policies}))
    af.unit = 1000.0
    af.by_literal = af.x / 1000
    af.by_constant = af.x / af.unit
    af.monthly = af.r / 12
    out = _run(af, engine)
    assert (out["by_literal"] == IEEE).all()
    assert (out["by_constant"] == IEEE).all()
    assert 0.03 / 12 != 0.03 * (1 / 12)
    assert (out["monthly"] == 0.03 / 12).all()


@pytest.mark.parametrize("engine", _ENGINES)
def test_integer_months_over_twelve_divide_exactly(engine: str) -> None:
    """``af.month / 12.0`` -- 5 / 12 is 0.4166666666666667, 5 * (1/12) is ...63."""
    months = list(range(30))
    af = ActuarialFrame(pl.DataFrame({"m": [months] * 3, "n": [5] * 3}))
    af.years = af.m / 12.0
    af.n_years = af.n / 12
    out = _run(af, engine)
    assert out["years"].to_list() == [[m / 12 for m in months]] * 3
    assert out["n_years"].to_list() == [5 / 12] * 3


@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_an_aggregate_divided_by_a_number_keeps_its_length(engine: str) -> None:
    """One value over one value stays one value: a select keeps one row, a column broadcasts."""
    xs = [135.021, 1.892, 0.3]
    total = pl.Series(xs).sum()
    af = ActuarialFrame(pl.DataFrame({"x": xs}))
    af.share = af.x / af.x.polars_native().sum()
    af.total_k = af.x.polars_native().sum() / 1000
    out = af.collect(engine=engine)
    assert out["share"].to_list() == [x / total for x in xs]
    assert out["total_k"].to_list() == [total / 1000] * 3

    selected = ActuarialFrame(pl.DataFrame({"x": xs}))
    one = selected.select(per_unit=selected.x.polars_native().sum() / 1000).collect()
    assert one.height == 1
    assert one["per_unit"][0] == total / 1000


def test_a_duration_divided_by_a_number_keeps_its_polars_meaning() -> None:
    """Not a number: the native operator, and a duration back."""
    af = ActuarialFrame(pl.DataFrame({"gap": [datetime.timedelta(days=4)]}))
    af.half = af.gap / 2
    out = af.collect()
    assert out.schema["half"] == pl.Duration("us")
    assert out["half"][0] == datetime.timedelta(days=2)


@pytest.mark.parametrize("engine", _ENGINES)
def test_rule_bodies_divide_exactly(engine: str) -> None:
    """Rate conversions and discounting inside the accessors use the same division."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "r": [0.03, 0.06],
                "rl": [[0.03, 0.06, 0.04]] * 2,
                "cf": [K, K],
                "x": [1250.0, -1349.0],
            }
        )
    )
    af.zero = 0.0
    af.one = 1.0
    af.r_m = af.r.finance.to_monthly(method="simple")
    af.rl_m = af.rl.finance.to_monthly(method="simple")
    # (1 + 0) ** 1 is a constant divisor of one: K / 1 is K, on any kernel,
    # so the guard is that the rule still answers -- and answers exactly.
    af.pv = af.cf.finance.discount(af.zero, af.one)
    af.hundreds = af.x.excel.round(-2)
    out = _run(af, engine)
    assert out["r_m"].to_list() == [0.03 / 12, 0.06 / 12]
    assert out["rl_m"].to_list() == [[0.03 / 12, 0.06 / 12, 0.04 / 12]] * 2
    assert out["pv"].to_list() == [K, K]
    assert out["hundreds"].to_list() == [1300.0, -1300.0]


@pytest.mark.parametrize("engine", _ENGINES)
def test_list_divided_by_a_compound_scalar_is_ieee_division(engine: str) -> None:
    af = ActuarialFrame(pl.DataFrame({"k": [[K] * 4] * 3, "half": [500.0] * 3}))
    af.q = af.k / (af.half * 2)
    out = _run(af, engine)
    assert out["q"].to_list() == [[IEEE] * 4] * 3


@pytest.mark.parametrize("engine", _ENGINES)
def test_list_floordiv_and_mod_by_a_literal_use_the_ieee_quotient(engine: str) -> None:
    """``0.3 / 0.1`` is 2.9999999999999996; ``0.3 * (1 / 0.1)`` is 3.0000000000000004.

    The reciprocal moved the floor to 3 and left a negative remainder. The
    contract's float ``mod`` is ``x - c * floor(x / c)`` in binary64.
    """
    xs = [0.3, 0.7]
    af = ActuarialFrame(pl.DataFrame({"x": [xs] * 3}))
    af.f = af.x // 0.1
    af.m = af.x % 0.1
    out = _run(af, engine)
    floors = [float(math.floor(x / 0.1)) for x in xs]
    assert floors == [2.0, 6.0]
    assert out["f"].to_list() == [floors] * 3
    assert out["m"].to_list() == [[x - 0.1 * f for x, f in zip(xs, floors)]] * 3


def test_integer_period_floordiv_keeps_its_integer_answer() -> None:
    """``af.month // 12`` -- the duration-year idiom -- is untouched by the layout."""
    af = ActuarialFrame(pl.DataFrame({"month": [[0, 11, 12, 25]] * 3}))
    af.year = af.month // 12
    af.rem = af.month % 12
    out = af.collect()
    assert out.schema["year"] == pl.List(pl.Int64)
    assert out["year"].to_list() == [[0, 0, 1, 2]] * 3
    assert out["rem"].to_list() == [[0, 11, 0, 1]] * 3


def test_list_quotient_keeps_nulls_and_empty_lists() -> None:
    """A null element, an empty list, a null list and a null divisor answer as before."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "k": [[K, None], [], None, [K]],
                "d": [D, D, D, None],
            }
        )
    )
    af.q = af.k / af.d
    af.r = af.k / 1000
    out = af.collect()
    assert out["q"].to_list() == [[IEEE, None], [], None, [None]]
    assert out["r"].to_list() == [[IEEE, None], [], None, [IEEE]]


@pytest.mark.parametrize("engine", _ENGINES)
def test_scalar_base_raised_to_a_list_exponent_is_exact(engine: str) -> None:
    af = ActuarialFrame(pl.DataFrame({"e": [[14.0, 13.0, 0.5]] * 2, "b": [10.0, 2.0]}))
    af.lit_int = 10**af.e
    af.lit_float = 10.0**af.e
    af.column = af.b**af.e
    out = _run(af, engine)
    tens = [1e14, 1e13, math.pow(10.0, 0.5)]
    assert out["lit_int"].to_list() == [tens, tens]
    assert out["lit_float"].to_list() == [tens, tens]
    assert out["column"].to_list() == [tens, [2.0**14, 2.0**13, math.pow(2.0, 0.5)]]


def test_scalar_base_list_exponent_domain_is_unchanged() -> None:
    """Zero and negative bases, and a null exponent list, keep their stated answers."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "b": [0.0, -2.0, 3.0],
                "e": [[2.0, 0.0, -1.0], [2.0, 3.0], None],
            }
        )
    )
    af.p = af.b**af.e
    out = af.collect()["p"].to_list()
    assert out[0][:2] == [0.0, 1.0]
    assert math.isnan(out[0][2])
    assert out[1] is None
    assert out[2] is None


def test_the_quotient_kernel_is_portable_in_a_rollforward_body() -> None:
    """A lowered quotient keeps a rollforward as portable as ``TrueDivide`` did."""
    from gaspatchio.frame.lowering._polars.plugins import ieee_quotient
    from gaspatchio.rollforward._engine_binding import (
        _expr_is_closed_subset,
        node_identities,
    )

    expr = ieee_quotient(pl.col("x"), pl.lit(12))
    assert ("Function", "FfiPlugin", "ieee_div") in node_identities(expr)
    assert _expr_is_closed_subset(expr)
