# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The thirteen calls that read a number read a flag as its 0.0 or 1.0.

``abs``, ``sign``, ``sqrt``, ``cbrt``, ``exp``, ``log``, ``log10``, ``log1p``,
``norm_cdf`` and ``round_sig_figs`` (section 11.1.12), and ``round``,
``floor`` and ``ceil`` (section 11.1.8), over a stored True/False, a
comparison, or a test combined with ``&`` or ``~``, read the flag as the
0.0/1.0 section 11.1.25 reads it as in arithmetic and answer a double, per
policy and per period, on both Polars engines. Before, ``sign``, ``floor``,
``ceil``, ``round``, ``round_sig_figs`` and ``norm_cdf`` failed on a stored
flag in Polars' words, ``abs`` was refused, every one failed on a per-period
comparison, and a comparison carried none of the methods: ``(af.k > 2).round()``
raised Python's own AttributeError. A method a comparison does not answer is
now refused in gaspatchio's words.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

# Each call's answer at 1.0 and at 0.0, by hand: e, ln 2 and Phi(1) are the
# doubles the host's own functions give, and log of nought is minus infinity.
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
        "k": [5, 1, None],
        "x": [2.5, -1.0, 1.0],
        "b": [True, False, None],
        "runs": [[False, True, None], [True, False, False], [True, True, True]],
    }
)

# Each flag, the truth it holds per policy or per period, and whether it is
# per period. A null stays null.
_FLAGS: dict[str, tuple[Callable[[ActuarialFrame], object], list[object], bool]] = {
    "a stored flag": (lambda af: af.b, [True, False, None], False),
    "a comparison": (lambda af: af.k > 2, [True, False, None], False),
    "a mask": (lambda af: (af.k > 2) & (af.x > 0), [True, False, None], False),
    "a negated comparison": (lambda af: ~(af.k > 2), [False, True, None], False),
    "a run of stored flags": (
        lambda af: af.runs,
        [[False, True, None], [True, False, False], [True, True, True]],
        True,
    ),
    "a per-period comparison": (
        lambda af: af.month >= 1,
        [[False, True, True]] * 3,
        True,
    ),
}


def _frame(*, periods: bool) -> ActuarialFrame:
    af = ActuarialFrame(_BOOK)
    if periods:
        af = af.projection.set(
            start_date=dt.date(2025, 1, 1), n_periods=2, frequency="monthly"
        )
    return af


def _hand(name: str, truth: object) -> object:
    if isinstance(truth, list):
        return [_hand(name, cell) for cell in truth]
    if truth is None:
        return None
    one, nought = _HAND[name]
    return one if truth else nought


@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
@pytest.mark.parametrize("flag", sorted(_FLAGS))
@pytest.mark.parametrize("name", sorted(_HAND))
def test_the_call_reads_the_flag_as_its_0_or_1(
    name: str, flag: str, engine: str
) -> None:
    make, truth, periods = _FLAGS[flag]
    af = _frame(periods=periods)
    af.r = getattr(make(af), name)(*_ARGUMENTS.get(name, ()))

    out = af.collect(engine=engine)

    assert out.schema["r"] == (pl.List(pl.Float64) if periods else pl.Float64)
    assert out["r"].to_list() == _hand(name, truth)


@pytest.mark.parametrize("flag", sorted(_FLAGS))
def test_abs_written_as_the_builtin_answers_the_indicator(flag: str) -> None:
    make, truth, periods = _FLAGS[flag]
    af = _frame(periods=periods)
    af.r = abs(make(af))  # type: ignore[arg-type]

    assert af.collect()["r"].to_list() == _hand("abs", truth)


@pytest.mark.parametrize("name", ["fill_null", "is_null", "to_text", "cum_sum"])
def test_a_method_a_comparison_does_not_answer_is_refused_by_name(name: str) -> None:
    af = _frame(periods=False)
    test = af.k > 2

    with pytest.raises(AttributeError, match=f"{name} is not answered on a comparison"):
        getattr(test, name)
    assert not hasattr(test, name)


def test_a_private_name_is_absent_in_python_s_own_words() -> None:
    test = _frame(periods=False).k > 2

    with pytest.raises(AttributeError, match=r"^_not_here$"):
        test._not_here  # noqa: B018, SLF001 - the attribute read is the test
