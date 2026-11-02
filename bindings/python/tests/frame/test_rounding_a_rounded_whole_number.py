# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Rounding a rounded whole number answers, and its plan grows with the calls.

``round_sig_figs`` over an ``Int64`` column is taken in whole-number
arithmetic, counting the figures against eighteen powers of ten, and the
expression wrote the value out at every read: one call over a column was
61,422 characters, a call over another's answer 47.9 MB, and the reporting
pattern "round each component, then the total" --
``(a.round_sig_figs(3) + b.round_sig_figs(3)).round_sig_figs(3)`` -- 93.2 MB,
with no answer in 60 s and 4 GB of memory (audit D1-H1). The value is now
read once, as a struct field, so the plan grows by about the same amount per
call however deep the calls sit, and the answers are as before.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

A = [871, 3299, 149, 77, 329_999, 14, -781_098, 0]
B = [5, 7, 9, 11, 13, 17, -2, 0]


def _sig_figs(value: int, digits: int) -> int:
    """Keep ``digits`` leading figures of a whole number, a tie away from zero."""
    if value == 0:
        return 0
    exponent = Decimal(abs(value)).adjusted() - digits + 1
    if exponent <= 0:
        return value
    step = Decimal(10) ** exponent
    kept = (Decimal(value) / step).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(kept * step)


def _frame(dtype: pl.DataType) -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame({"a": A, "b": B}, schema={"a": dtype, "b": dtype})
    )


@pytest.mark.parametrize("dtype", [pl.Int64, pl.Int32])
def test_a_rounded_total_of_rounded_components_answers(dtype: pl.DataType) -> None:
    af = _frame(dtype)
    total = (af.a.round_sig_figs(3) + af.b.round_sig_figs(3)).round_sig_figs(3)
    # Measured first: the plan that never answered was 93.2 MB, and a run
    # over it would hang the suite rather than fail it.
    assert len(str(af._convert_to_expr(total))) < 1_000_000  # noqa: SLF001
    af.total = total
    twice = af.a.round_sig_figs(3).round_sig_figs(2)
    assert len(str(af._convert_to_expr(twice))) < 1_000_000  # noqa: SLF001
    af.twice = twice
    out = af.collect()
    assert out["total"].to_list() == [
        _sig_figs(_sig_figs(a, 3) + _sig_figs(b, 3), 3)
        for a, b in zip(A, B, strict=True)
    ]
    assert out["twice"].to_list() == [_sig_figs(_sig_figs(a, 3), 2) for a in A]


_FRAME = {
    "i": [871, 3299, 149],
    "f": [871.5, 3299.25, 149.125],
    "li": [[871, 5], [3299, 7], [149, 9]],
    "lf": [[871.5, 5.0], [3299.25, 7.0], [149.125, 9.0]],
}

# Each call over the last one's answer, its operand written once per call.
_CALLS = {
    "round_sig_figs Int64": ("i", lambda _af, x: x.round_sig_figs(3)),
    "round_sig_figs Float64": ("f", lambda _af, x: x.round_sig_figs(3)),
    "round_sig_figs per period": ("li", lambda _af, x: x.round_sig_figs(3)),
    "round(-2) Int64": ("i", lambda _af, x: x.round(-2)),
    "round(-2) Float64": ("f", lambda _af, x: x.round(-2)),
    "round(2, half_to_even) Float64": (
        "f",
        lambda _af, x: x.round(2, mode="half_to_even"),
    ),
    "round(-1) per period": ("lf", lambda _af, x: x.round(-1)),
}


@pytest.mark.parametrize("call", list(_CALLS))
def test_the_plan_grows_with_the_calls_not_with_their_reads(call: str) -> None:
    column, written = _CALLS[call]
    af = ActuarialFrame(_FRAME)
    sizes = []
    x = getattr(af, column)
    for _ in range(4):
        x = written(af, x)
        sizes.append(len(str(af._convert_to_expr(x))))  # noqa: SLF001 -- the lowered plan
    steps = [later - earlier for earlier, later in pairwise(sizes)]
    # Linear: every further call adds about what the first did.
    assert max(steps) <= 2 * sizes[0], sizes
    af.y = x
    assert af.collect().height == len(_FRAME["i"])


def test_per_period_rounding_of_rounding_answers() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"a": [A[:4], A[4:]]}, schema={"a": pl.List(pl.Int64)})
    )
    twice = af.a.round_sig_figs(3).round_sig_figs(2)
    assert len(str(af._convert_to_expr(twice))) < 1_000_000  # noqa: SLF001
    af.twice = twice
    assert af.collect()["twice"].to_list() == [
        [_sig_figs(_sig_figs(a, 3), 2) for a in A[:4]],
        [_sig_figs(_sig_figs(a, 3), 2) for a in A[4:]],
    ]
