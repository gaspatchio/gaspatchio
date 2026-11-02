# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A number written where a rollforward step takes an amount.

A number cannot be a column name, so there is nothing to guess: the builder
reads it as the literal ``pl.lit(value)`` would be. It used to pass the
number through untouched, and compiling then failed with ``AttributeError:
'float' object has no attribute 'meta'``. A compiled rollforward reads each
amount from a column of the frame, so a literal is refused at compile time,
in words about a number, with the move that puts it in a column. A bare
string could be a name or a value, and is refused at the builder.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.rollforward import compile_rollforward

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio.rollforward._builder import RollforwardBuilder


def _frame() -> ActuarialFrame:
    af = ActuarialFrame(
        {
            "av_init": [100.0],
            "rate": [[0.01, 0.01]],
            "level": [[150.0, 150.0]],
            "anniversary": [[False, True]],
        }
    )
    return af.projection.set(
        start_date=date(2025, 1, 31), n_periods=2, frequency="monthly"
    )


def _builder(af: ActuarialFrame) -> RollforwardBuilder:
    return af.projection.rollforward(states={"av": af["av_init"]})


@pytest.mark.parametrize(
    ("step", "field", "shown"),
    [
        (lambda _af, h: h.add(5.0), "Add.expr", "5.0"),
        (lambda _af, h: h.subtract(5), "Subtract.expr", "5"),
        (lambda _af, h: h.add(pl.lit(5.0)), "Add.expr", "5.0"),
        (lambda _af, h: h.add(pl.lit(5.0).alias("x")), "Add.expr", "5.0"),
        (lambda _af, h: h.charge(0.01), "Charge.rate", "0.01"),
        (lambda _af, h: h.grow(0.01), "Grow.rate", "0.01"),
        (
            lambda af, h: h.grow_capped(af["rate"], floor=0.0, cap=af["rate"]),
            "GrowCapped.floor",
            "0.0",
        ),
        (
            lambda af, h: h.deduct_nar(af["rate"], death_benefit=1000.0),
            "DeductNAR.death_benefit",
            "1000.0",
        ),
        (lambda _af, h: h.ratchet(to=150.0), "Ratchet.to", "150.0"),
        (
            lambda af, h: h.ratchet(to=af["level"], when=True),
            "Ratchet.when",
            "True",
        ),
    ],
    ids=[
        "add-float",
        "subtract-int",
        "add-pl-lit",
        "add-pl-lit-under-an-alias",
        "charge",
        "grow",
        "grow_capped-floor",
        "deduct_nar-death_benefit",
        "ratchet-to",
        "ratchet-when",
    ],
)
def test_a_number_is_read_as_a_literal_and_refused_at_compile_by_name(
    step: Callable[[ActuarialFrame, object], object], field: str, shown: str
) -> None:
    af = _frame()
    b = _builder(af)
    step(af, b["av"])

    with pytest.raises(NotImplementedError, match="reads each amount") as refusal:
        compile_rollforward(b)

    message = str(refusal.value)
    assert f"{field} is the value {shown}" in message
    assert "Put it in a column of the frame first" in message


def test_the_move_the_refusal_names_runs() -> None:
    """A number in a column is an amount the kernel reads each period."""
    af = _frame()
    af.flat_fee = 5.0
    b = _builder(af)
    b["av"].subtract(af["flat_fee"], label="fee")
    af.av = compile_rollforward(b).expr_for("av")

    assert af.collect()["av"].to_list() == [[95.0, 90.0]]


def test_a_negative_charge_rate_is_pointed_at_a_column() -> None:
    """It used to say "use Add for credits", and a number given to add() is refused."""
    af = _frame()
    b = _builder(af)

    with pytest.raises(ValueError, match=r"has the rate -0\.01") as refusal:
        b["av"].charge(-0.01, label="credit")

    message = str(refusal.value)
    assert "af['rate'] = 0.01" in message
    assert ".charge(af['rate'])" in message
    assert ".grow(af['rate'])" in message
    assert "use Add" not in message

    af["rate"] = 0.01
    b["av"].grow(af["rate"], label="credit")
    af.av = compile_rollforward(b).expr_for("av")

    assert af.collect()["av"].to_list()[0] == pytest.approx([101.0, 102.01])


def test_a_ratchet_that_fires_every_period_is_told_to_leave_when_out() -> None:
    af = _frame()
    b = _builder(af)
    b["av"].ratchet(to=af["level"], when=True)

    with pytest.raises(NotImplementedError, match=r"Ratchet\.when") as refusal:
        compile_rollforward(b)

    assert "fires every period takes no when=" in str(refusal.value)


def test_a_bare_string_amount_is_refused_at_the_step() -> None:
    af = _frame()

    with pytest.raises(TypeError, match="bare string") as refusal:
        _builder(af)["av"].subtract("rate")

    message = str(refusal.value)
    assert 'af["rate"]' in message
    assert "a column holding the value" in message


def test_a_number_still_opens_a_state() -> None:
    """An opening value takes a number already; that is unchanged."""
    af = _frame()
    b = af.projection.rollforward(states={"av": 1000.0})
    b["av"].grow(af["rate"], label="growth")
    af.av = compile_rollforward(b).expr_for("av")

    assert af.collect()["av"].to_list()[0] == pytest.approx([1010.0, 1020.1])
