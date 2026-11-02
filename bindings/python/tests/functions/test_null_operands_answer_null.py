# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A null operand of a power or a clip answers null, as the spec states.

On the base, for policy P2 (three periods):

- ``af.x ** af.e`` with ``e`` null for P2 refused the whole run, ``rhs
  scalar at row 1 is null`` (``row 0`` streaming). Section 11.1.25: "A null
  element on either side yields null at that position", so P2 answers null
  in each of its periods.
- ``af.x.clip(af.lo, af.hi)`` with ``x`` null for P3 answered ``[]``, a policy
  with no periods, which a later sum reads as nought. Section 11.1.3: "a
  null value stays null", which is what the same clip with literal bounds
  (Polars' own ``clip``) already answered.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.lowering._polars.plugins import list_pow

_ENGINES = ("streaming", "in-memory")


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x": [[1.0, 2.0], [1.0, 2.0, 3.0], None],
            "e": [2.0, None, 2.0],
            "lo": [1.5, 0.0, 0.0],
            "hi": [9.0, 2.5, 9.0],
        },
        schema={
            "x": pl.List(pl.Float64),
            "e": pl.Float64,
            "lo": pl.Float64,
            "hi": pl.Float64,
        },
    )


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_null_exponent_is_null_in_each_of_its_policys_periods(engine: str) -> None:
    """The policy with the null exponent is null per period; the others raise."""
    af = ActuarialFrame(_book())
    af.out = af.x**af.e

    assert af.collect(engine=engine)["out"].to_list() == [
        [1.0, 4.0],
        [None, None, None],
        None,
    ]


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_null_policy_clipped_by_column_bounds_stays_null(engine: str) -> None:
    """Column bounds take the kernel, literal bounds the engine: both say null."""
    af = ActuarialFrame(_book())
    af.by_columns = af.x.clip(af.lo, af.hi)
    af.by_literals = af.x.clip(1.5, 2.5)

    out = af.collect(engine=engine)
    assert out["by_columns"].to_list() == [[1.5, 2.0], [1.0, 2.0, 2.5], None]
    assert out["by_literals"].to_list()[2] is None


_TEXT_BOOK = pl.DataFrame(
    {
        "fv": [[1000.0, 1100.0], [2000.0, 2200.0]],
        "code": ["A", "B"],
        "codes": [["A", "B"], ["C", "D"]],
        "e": [2.0, 3.0],
    }
)


@pytest.mark.parametrize(
    "formula",
    [lambda af: af.fv**af.code, lambda af: af.fv**af.codes, lambda af: af.codes**af.e],
    ids=["text per policy", "text per period", "text base"],
)
def test_a_text_operand_of_a_power_is_refused_not_nulled(formula: object) -> None:
    """Text is not a null exponent: ``**`` refuses it by name, where it is written.

    The kernel casts to Float64, which turns text into nulls. On an earlier
    base two of these answered ``[[None, None], [None, None]]`` and the third
    refused only because that null exponent refused; the kernel then refused
    all three by name when the frame ran, and the frame now refuses the line
    itself, as it does any arithmetic between text and a number.
    """
    af = ActuarialFrame(_TEXT_BOOK)

    with pytest.raises(TypeError, match="arithmetic reads numbers"):
        af.out = formula(af)  # type: ignore[operator]


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(
    ("base", "exponent", "holds"),
    [
        ("fv", "code", "this column holds str"),
        ("fv", "codes", "these lists hold str"),
        ("codes", "e", "these lists hold str"),
    ],
    ids=["text per policy", "text per period", "text base"],
)
def test_the_kernel_itself_refuses_text_by_name(
    base: str, exponent: str, holds: str, engine: str
) -> None:
    """An engine fragment calling the power kernel over text meets its refusal."""
    af = ActuarialFrame(_TEXT_BOOK)
    af.out = list_pow(pl.col(base), pl.col(exponent))

    with pytest.raises(pl.exceptions.ComputeError, match="list_pow works on numbers"):
        af.collect(engine=engine)
    with pytest.raises(pl.exceptions.ComputeError, match=holds):
        af.collect(engine=engine)
