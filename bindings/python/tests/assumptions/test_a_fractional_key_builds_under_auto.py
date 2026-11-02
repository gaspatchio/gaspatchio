# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table keyed by fractional numbers builds under the default storage.

An in-the-money band keyed 0.8 / 1.0 / 1.2, or a half-year duration keyed
0.0 / 0.5 / 1.0, is a valid key (section 11.1.24). The default storage, which
picks a layout, raised the array encoder's own words -- "Float64 keys with
decimals not supported for array storage" -- before it could fall back to
hash storage. It now takes hash storage and answers by value.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table


@pytest.mark.parametrize(
    ("keys", "asked", "answered"),
    [
        ([0.8, 1.0, 1.2], [1.2, 0.8, 1.0], [0.6, 1.5, 1.0]),
        ([0.0, 0.5, 1.0], [1.0, 0.0, 0.5], [0.6, 1.5, 1.0]),
    ],
)
def test_a_fractional_key_answers_by_value(
    keys: list[float], asked: list[float], answered: list[float]
) -> None:
    table = Table(
        name=f"b3_fractional_{keys[1]}",
        source=pl.DataFrame({"itm": keys, "mult": [1.5, 1.0, 0.6]}),
        dimensions={"itm": "itm"},
        value="mult",
    )
    assert table.storage_mode == "hash"
    af = ActuarialFrame(pl.DataFrame({"itm": asked}))
    af.mult = table.lookup(itm=af.itm)

    assert af.collect()["mult"].to_list() == answered
    assert af.collect(engine="streaming")["mult"].to_list() == answered
