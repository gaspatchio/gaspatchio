# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An integer raised to an integer column past 0 to 2**32 - 1 names to_float().

Two integers have an integer power only for an exponent from 0 to 2**32 - 1
(section 11.1.25). An exponent written in the line is seen where the line is
written, and one outside the range already makes the power a double. One held
in a column is seen only when the run reaches it, so ``af.a ** af.k`` with a
negative ``k`` failed inside Polars with ``conversion from `i64` to `u32`
failed in column 'k'``, a sentence about types naming neither the power nor
the move. The gaspatchio sentence now comes first, naming ``to_float()`` on
either operand, with the engine's text kept underneath. The answer type of
the line is unchanged: a power in range is still an integer.

The hand values, with a = [2, 3] and k = [-1, 2]: a ** k as doubles is
[0.5, 9.0], and 2 ** k is [0.5, 4.0].
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import Sum, run_aggregated

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"policy_id": ["P1", "P2"], "a": [2, 3], "k": [-1, 2]})
_WHY = "Two integers have an integer power only for an exponent from 0 to 2**32 - 1"

_SPELLINGS: dict[str, tuple[Callable[[ActuarialFrame], Any], list[int], str, str]] = {
    "a column base": (
        lambda af: af.a**af.k,
        [-1, 2],
        "af.a ** af.k raises an integer",
        "af.a.to_float() ** af.k, or af.a ** af.k.to_float()",
    ),
    "past 2**32": (
        lambda af: af.a**af.k,
        [2**33, 2],
        "af.a ** af.k raises an integer",
        "af.a.to_float() ** af.k, or af.a ** af.k.to_float()",
    ),
    "the method": (
        lambda af: af.a.pow(af.k),
        [-1, 2],
        "af.a ** af.k raises an integer",
        "af.a.to_float() ** af.k, or af.a ** af.k.to_float()",
    ),
    "a literal base": (
        lambda af: 2**af.k,
        [-1, 2],
        "2 ** af.k raises an integer",
        "2.0 ** af.k, or 2 ** af.k.to_float()",
    ),
    "an exponent calculated in the line": (
        lambda af: af.a ** (af.k - 3),
        [1, 2],
        "An integer is raised",
        "af.a.to_float() ** exponent, or af.a ** exponent.to_float()",
    ),
}


def _frame(k: list[int]) -> ActuarialFrame:
    return ActuarialFrame(_BOOK.with_columns(pl.Series("k", k)))


@pytest.mark.parametrize("mode", [None, "enhanced", "basic"])
@pytest.mark.parametrize("case", list(_SPELLINGS), ids=list(_SPELLINGS))
def test_the_failure_says_to_write_to_float_on_either_operand(
    monkeypatch: pytest.MonkeyPatch, case: str, mode: str | None
) -> None:
    if mode is None:
        monkeypatch.delenv("AF_ERROR_MODE", raising=False)
    else:
        monkeypatch.setenv("AF_ERROR_MODE", mode)
    power, k, headline, moves = _SPELLINGS[case]
    af = _frame(k)
    af.p = power(af)
    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        af.collect()
    message = str(raised.value)
    assert message.startswith(
        f"{headline} to an integer exponent that holds a value outside 0 to "
        "2**32 - 1.\n\n"
    )
    assert _WHY in message
    assert (
        "Write to_float() on either operand and the power is the floating-point "
        f"one, which takes any exponent: {moves}." in message
    )
    # The engine's own text stays beneath, with its expression.
    assert "failed in column 'k'" in message
    assert ".pow([" in message
    assert message.count(_WHY) == 1


@pytest.mark.parametrize(
    ("written", "answer"),
    [
        (lambda af: af.a.to_float() ** af.k, [0.5, 9.0]),
        (lambda af: af.a ** af.k.to_float(), [0.5, 9.0]),
        (lambda af: 2.0**af.k, [0.5, 4.0]),
        (lambda af: 2 ** af.k.to_float(), [0.5, 4.0]),
    ],
    ids=["base to_float", "exponent to_float", "a double literal", "literal base"],
)
def test_each_named_move_answers_the_double(
    written: Callable[[ActuarialFrame], Any], answer: list[float]
) -> None:
    af = _frame([-1, 2])
    af.p = written(af)
    out = af.collect()["p"]
    assert out.dtype == pl.Float64
    assert out.to_list() == answer


def test_a_power_in_range_is_still_an_integer() -> None:
    af = _frame([1, 2])
    af.p = af.a**af.k
    out = af.collect()["p"]
    assert out.dtype == pl.Int64
    assert out.to_list() == [2, 9]


def test_a_batched_fold_says_it_too() -> None:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.p = af.a**af.k
        return af

    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        run_aggregated(model, _BOOK, [Sum("p").alias("p")], batch_size=1)
    assert str(raised.value).startswith("af.a ** af.k raises an integer")


def test_off_hands_the_engine_s_message_over_as_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _frame([-1, 2])
    af.p = af.a**af.k
    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        af.collect()
    assert str(raised.value).startswith("conversion from `i64` to `u32` failed")
    assert _WHY not in str(raised.value)


def test_polars_still_words_the_integer_power_failure_this_way() -> None:
    """The lift keys on this hint; a Polars that rewords it turns the lift off."""
    with pytest.raises(pl.exceptions.InvalidOperationError) as raised:
        pl.DataFrame({"a": [2], "k": [-1]}).select(pl.col("a").pow(pl.col("k")))
    message = str(raised.value)
    assert "conversion from `i64` to `u32` failed in column 'k'" in message
    assert "if you were trying to raise an integer to a negative integer power" in (
        message
    )
