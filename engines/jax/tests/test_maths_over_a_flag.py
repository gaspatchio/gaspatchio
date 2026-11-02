# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The thirteen calls that read a number answer a flag's 0.0 or 1.0 here too.

Sections 11.1.8 and 11.1.12 read a flag -- a stored Boolean, a comparison, a
test combined with ``&`` -- as the 0.0/1.0 section 11.1.25 reads it as, and
answer a double. This engine refused every one of them over a Boolean by name,
and ``floor``, ``ceil`` and ``round`` over a comparison named ``round`` for
all three; it now answers each as the producer does, to the bit, per policy
and per period.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import TYPE_CHECKING

import polars as pl
import pytest
from polars.testing import assert_series_equal

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

# Each call's answer at 1.0 and at 0.0, by hand.
_HAND: dict[str, tuple[float, float]] = {
    "abs": (1.0, 0.0),
    "sign": (1.0, 0.0),
    "sqrt": (1.0, 0.0),
    "cbrt": (1.0, 0.0),
    "exp": (math.e, 1.0),
    "log": (0.0, -math.inf),
    "log10": (0.0, -math.inf),
    "log1p": (math.log(2.0), 0.0),
    "norm_cdf": (0.5 * math.erfc(-1.0 / math.sqrt(2.0)), 0.5),
    "round_sig_figs": (1.0, 0.0),
    "round": (1.0, 0.0),
    "floor": (1.0, 0.0),
    "ceil": (1.0, 0.0),
}
_ARGUMENTS: dict[str, tuple[int, ...]] = {"round_sig_figs": (2,), "round": (0,)}
_BOOK = pl.DataFrame(
    {
        "k": [5, 1],
        "x": [2.5, -1.0],
        "b": [True, False],
        "runs": [[False, True, True], [True, False, False]],
    }
)
_FLAGS: dict[str, tuple[Callable[[ActuarialFrame], object], list[object]]] = {
    "a stored flag": (lambda af: af.b, [True, False]),
    "a comparison": (lambda af: af.k > 2, [True, False]),
    "a mask": (lambda af: (af.k > 2) & (af.x > 0), [True, False]),
    "a run of stored flags": (
        lambda af: af.runs,
        [[False, True, True], [True, False, False]],
    ),
    "a per-period comparison": (lambda af: af.month >= 1, [[False, True, True]] * 2),
}


def _hand(name: str, truth: object) -> object:
    if isinstance(truth, list):
        return [_hand(name, cell) for cell in truth]
    one, nought = _HAND[name]
    return one if truth else nought


@pytest.mark.parametrize("flag", sorted(_FLAGS))
@pytest.mark.parametrize("name", sorted(_HAND))
def test_the_call_answers_the_flag_as_the_producer_does(name: str, flag: str) -> None:
    make, truth = _FLAGS[flag]
    af = ActuarialFrame(_BOOK).projection.set(
        start_date=dt.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.r = getattr(make(af), name)(*_ARGUMENTS.get(name, ()))

    reference, engine = af.collect(), af.collect(engine="jax")

    assert engine["r"].to_list() == _hand(name, truth)
    assert_series_equal(engine["r"], reference["r"], check_exact=True)
