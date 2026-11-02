# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A numeric call that reads a number out of a duration is refused where it is written.

``af.term = af.maturity - af.issue`` is a duration, and the vocabulary has no
time-delta type (section 10). ``sign``, ``round``, ``floor``, ``ceil``,
``round_sig_figs``, ``norm_cdf``, ``cum_prod`` and ``cumulative_survival``
over one failed only when the frame ran, in Polars' words (``floor can only
be used on numeric types``); ``sqrt``, ``cbrt``, ``exp``, ``log``, ``log10``
and ``log1p`` read the duration as its count in Polars' own storage unit, so
the root of five years was 12563948.4, the root of a count of microseconds.
Each is refused at the line, naming the duration and the count to write
instead, as text and dates are. A call whose answer is itself a duration --
``abs``, a total, a running total, the least, the greatest, the average --
keeps answering, in days by hand below.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2],
        "start": [dt.date(2020, 1, 1), dt.date(2021, 6, 1)],
        "end": [dt.date(2025, 1, 1), dt.date(2025, 1, 1)],
    }
)


def _per_policy() -> ActuarialFrame:
    af = ActuarialFrame(_BOOK)
    af.dd = af.end - af.start  # 1827 and 1310 days
    return af


def _per_period() -> ActuarialFrame:
    af = ActuarialFrame(_BOOK).projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value=2,
        frequency="monthly",
    )
    af.dd = pl.concat_list(
        pl.col("end") - pl.col("start"),
        pl.col("end") - pl.lit(dt.date(2024, 1, 1)),
        pl.col("end") - pl.lit(dt.date(2024, 12, 1)),
    )  # [1827, 366, 31] and [1310, 366, 31] days
    return af


_REFUSED: dict[str, Callable[[Any], Any]] = {
    "sign()": lambda dd: dd.sign(),
    "round()": lambda dd: dd.round(2),
    "floor()": lambda dd: dd.floor(),
    "ceil()": lambda dd: dd.ceil(),
    "sqrt()": lambda dd: dd.sqrt(),
    "cbrt()": lambda dd: dd.cbrt(),
    "exp()": lambda dd: dd.exp(),
    "log()": lambda dd: dd.log(),
    "log10()": lambda dd: dd.log10(),
    "log1p()": lambda dd: dd.log1p(),
    "round_sig_figs()": lambda dd: dd.round_sig_figs(2),
    "norm_cdf()": lambda dd: dd.norm_cdf(),
    "cumulative_survival()": lambda dd: dd.projection.cumulative_survival(),
}


@pytest.mark.parametrize("shape", ["per policy", "per period"])
@pytest.mark.parametrize("call", list(_REFUSED))
def test_a_call_reading_a_number_out_of_a_duration_is_refused(
    call: str, shape: str
) -> None:
    af = _per_policy() if shape == "per policy" else _per_period()

    with pytest.raises(TypeError) as refused:
        af.r = _REFUSED[call](af.dd)

    message = " ".join(str(refused.value).split())
    assert f"{call}: the value it reads -- the column 'dd' -- is a duration" in message
    assert ".polars_native().dt.total_days()" in message


def test_a_running_product_of_durations_is_refused() -> None:
    af = _per_period()

    with pytest.raises(TypeError, match=r"cum_prod\(\): the value it reads"):
        af.r = af.dd.cum_prod()


def _days(*days: float) -> list[dt.timedelta]:
    return [dt.timedelta(days=d) for d in days]


def test_abs_of_a_duration_is_the_duration() -> None:
    af = _per_policy()
    af.r = af.dd.abs()

    assert af.collect()["r"].to_list() == _days(1827, 1310)


# By hand from [1827, 366, 31] and [1310, 366, 31] days.
_ANSWERED: list[tuple[str, Callable[[Any], Any], list[object]]] = [
    (
        "cum_sum",
        lambda dd: dd.cum_sum(),
        [_days(1827, 2193, 2224), _days(1310, 1676, 1707)],
    ),
    (
        "remaining_sum",
        lambda dd: dd.projection.remaining_sum(),
        [_days(2224, 397, 31), _days(1707, 397, 31)],
    ),
    ("sum", lambda dd: dd.list.sum(), _days(2224, 1707)),
    (
        "mean",
        lambda dd: dd.list.mean(),
        [dt.timedelta(days=2224 / 3), dt.timedelta(days=569)],
    ),
    ("min", lambda dd: dd.list.min(), _days(31, 31)),
    ("max", lambda dd: dd.list.max(), _days(1827, 1310)),
]


@pytest.mark.parametrize(
    ("name", "line", "hand"), _ANSWERED, ids=[x[0] for x in _ANSWERED]
)
def test_a_call_answering_a_duration_still_answers(
    name: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    hand: list[object],
) -> None:
    af = _per_period()
    af.r = line(af.dd)

    assert af.collect()["r"].to_list() == hand
