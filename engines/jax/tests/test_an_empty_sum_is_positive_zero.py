# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An empty sum is +0.0, and one period of -0.0 sums to -0.0 (11.1.14).

The sign decides a division by the total, and 11.1.12 compares which way an
infinity points: Polars' list kernel gave -0.0 for an empty run, where this
engine gave +0.0; and this engine started its sum from +0.0, which turned a
single -0.0 period positive where Polars kept it (audit D1-P15).
"""

from __future__ import annotations

import polars as pl

from gaspatchio import ActuarialFrame


def test_the_sign_of_a_total_and_of_its_reciprocal_agree_on_both_engines() -> None:
    af = ActuarialFrame(pl.DataFrame({"r": [[], [1.0, -1.0], [-0.0], [2.5]]}))
    af.q = 4.0 / af.r.list.sum()
    want = [float("inf"), float("inf"), float("-inf"), 1.6]
    assert af.collect()["q"].to_list() == want
    assert af.collect(engine="jax")["q"].to_list() == want
