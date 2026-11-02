# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: The forward discount factor is one over one plus the rate, an IEEE quotient
# ABOUTME: Not pow(1 + r, -1), which darwin's libm does not round correctly
"""Forward discount factors are ``product(1 / (1 + r[u]), u < t)``, to the bit.

Section 11.1.30 states the forward factor as one over one plus the rate.
It was computed as ``(1 + r) ** -1`` through the power kernel, which is a
libm ``pow``: correctly rounded on glibc, and on darwin not -- one rate in
six hundred came back a unit in the last place off ``1 / (1 + r)``, and every
factor after it in the running product carried the difference. The corpus
is the rates where this machine's ``pow`` and the quotient differ, so on
darwin it discriminates; on a platform whose ``pow`` is correctly rounded it
is empty, and the quotient is still the answer.
"""

import sys
import zlib

import numpy as np
import polars as pl

from gaspatchio import ActuarialFrame

_PERIODS = 12
_POLICIES = 48


def _forward(rate: list[float]) -> list[float]:
    """Return 11.1.30's forward factors in Python's binary64."""
    factors = [1.0]
    for r in rate[:-1]:
        factors.append(factors[-1] * (1.0 / (1.0 + r)))
    return factors


def test_forward_factors_are_a_running_product_of_exact_quotients() -> None:
    rng = np.random.default_rng(zlib.crc32(b"forward"))
    draws = [float(r) for r in rng.uniform(0.0, 0.2, 400_000)]
    moved = [r for r in draws if (1.0 + r) ** -1.0 != 1.0 / (1.0 + r)]
    if sys.platform == "darwin":
        assert len(moved) >= _PERIODS * _POLICIES, len(moved)
    corpus = (moved + draws)[: _PERIODS * _POLICIES]
    rates = [corpus[i : i + _PERIODS] for i in range(0, len(corpus), _PERIODS)]
    af = ActuarialFrame(
        pl.DataFrame({"r": rates, "t": [list(range(_PERIODS))] * len(rates)})
    )
    af = af.finance.discount_factor(
        rate_col="r", periods_col="t", output_col="d", method="forward"
    )
    got = af.collect()["d"].to_list()
    assert got == [_forward(rate) for rate in rates]


def test_the_forward_factor_keeps_its_length_and_its_opening_one() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"r": [[0.1, 0.2, 0.3], []], "t": [[0, 1, 2], []]})
    )
    af = af.finance.discount_factor(
        rate_col="r", periods_col="t", output_col="d", method="forward"
    )
    assert af.collect()["d"].to_list() == [
        [1.0, 1.0 / 1.1, (1.0 / 1.1) * (1.0 / 1.2)],
        [],
    ]
