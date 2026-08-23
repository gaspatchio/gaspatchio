# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Excel-style column rounding: half away from zero, list-aware.

There was no working way to round a per-period column (gh#68): polars'
``.round()`` raises on a list column, and the ``plugins.round`` wrapper
panicked on a Rust symbol that does not exist. ``.excel.round()`` provides
the working path, and names its convention: Excel's half away from zero,
the same rule as the rollforward's ``Round`` op — while polars' ``.round()``
keeps banker's rounding. The inconsistency of gh#70 becomes two documented
conventions, each requested explicitly.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward


def test_scalar_ties_round_away_from_zero() -> None:
    """0.125 -> 0.13 (Excel), not 0.12 (banker's); sign is preserved."""
    af = ActuarialFrame({"x": [0.125, -0.125, 7558.485]})
    af.rounded = af.x.excel.round(2)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [0.13, -0.13, 7558.49]


def test_list_column_rounds_element_wise() -> None:
    """The gh#68 case: a per-period list column, rounded to cents."""
    af = ActuarialFrame({"coi": [[10.125, 7558.485], [0.005, -0.005]]})
    af.rounded = af.coi.excel.round(2)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [
        [10.13, 7558.49],
        [0.01, -0.01],
    ]


def test_default_rounds_to_whole_units() -> None:
    af = ActuarialFrame({"x": [2.5, -2.5, 2.4]})
    af.rounded = af.x.excel.round()
    out = af.collect()
    assert out.get_column("rounded").to_list() == [3.0, -3.0, 2.0]


def test_negative_digits_round_left_of_the_decimal() -> None:
    """ROUND(1250, -2) = 1300 — Excel's negative num_digits."""
    af = ActuarialFrame({"face": [1250.0, 1249.0, -1250.0]})
    af.banded = af.face.excel.round(-2)
    out = af.collect()
    assert out.get_column("banded").to_list() == [1300.0, 1200.0, -1300.0]


def test_polars_native_round_still_bankers() -> None:
    """The two conventions coexist, each by name — polars stays half-to-even."""
    assert pl.select(pl.lit(0.125).round(2)).item() == 0.12


def test_matches_the_rollforward_round_op() -> None:
    """Column-side excel.round and the kernel's Round op are the same rule.

    Grow a balance, round it in the kernel each period; reproduce the same
    figures column-side from the unrounded closing balances' inputs. The two
    surfaces must agree to the cent on the tie-heavy rate chosen here.
    """
    af = ActuarialFrame({"p": [1], "init": [1000.0], "rate": [[0.0125] * 3]})
    af = af.projection.set(
        start_date=date(2025, 12, 31), n_periods=3, frequency="annual"
    )
    rf = af.projection.rollforward(states={"av": af["init"]})
    rf["av"].grow(af["rate"])
    rf["av"].round(2)
    af.kernel = compile_rollforward(rf).expr_for("av")
    out = af.collect()

    balance = 1000.0
    expected = []
    for _ in range(3):
        grown = ActuarialFrame({"x": [balance * 1.0125]})
        grown.r = grown.x.excel.round(2)
        balance = grown.collect().get_column("r").to_list()[0]
        expected.append(balance)
    assert out.get_column("kernel").to_list()[0] == expected


def test_dead_plugin_wrappers_are_gone() -> None:
    """floor/round/round_to_int panicked on a missing Rust symbol; they are
    removed rather than left as landmines.
    """
    from gaspatchio.polars_backend import plugins

    assert not hasattr(plugins, "round")
    assert not hasattr(plugins, "round_to_int")
    assert not hasattr(plugins, "floor")
    with pytest.raises(ImportError):
        # The import IS the assertion: the dead wrapper must stay gone, so
        # importing it must fail. Not unused, not dead — do not "fix" it away.
        from gaspatchio.functions.vector import round  # noqa: A004, F401


def test_composed_list_expression_rounds_element_wise() -> None:
    """A composed per-period expression must take the element-wise path.

    The shape gate keys off ``shape``, not the proxy's concrete type, so a
    list-valued ExpressionProxy (here ``coi * factor``) rounds inside the
    list rather than hitting scalar ``Expr.round`` and failing at collect.
    """
    af = ActuarialFrame({"coi": [[10.124, 7558.484]], "factor": [1.0001]})
    af.rounded = (af.coi * af.factor).excel.round(2)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [[10.13, 7559.24]]


def test_extreme_negative_digits_round_to_zero() -> None:
    """ROUND(x, -309) is 0 for every finite float — not an OverflowError.

    10**309 is not representable, but no finite value is within half of it
    (max double is under 1.8e308), so the result is exactly zero, sign
    normalised; nulls stay null.
    """
    af = ActuarialFrame({"x": [1.7e308, -1.7e308, 123.45, None]})
    af.rounded = af.x.excel.round(-309)
    af.rounded_more = af.x.excel.round(-400)
    out = af.collect()
    assert out.get_column("rounded").to_list() == [0.0, 0.0, 0.0, None]
    assert out.get_column("rounded_more").to_list() == [0.0, 0.0, 0.0, None]
