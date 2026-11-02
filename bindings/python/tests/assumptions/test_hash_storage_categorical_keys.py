# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A categorical or Enum key reads a hash-stored text table by its label.

Array storage places a categorical or Enum key by the label it holds. Hash
storage hashed its physical index instead -- a number from the key's own
dictionary, not the text the table was hashed by -- so the same lookup
missed: a silent NaN under ``on_missing="nan"`` and the fill value under a
fill, where array storage answered the rate. A table falls to hash storage by
request, or when its keys are too sparse for an array, so the answer
depended on a storage choice the model never sees.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

_KEYS = {
    "text": pl.Series(["F", "M"]),
    "categorical": pl.Series(["F", "M"], dtype=pl.Categorical),
    "categorical_own_dictionary": pl.Series(
        ["F", "M"], dtype=pl.Categorical(pl.Categories("hash_key_test"))
    ),
    "enum": pl.Series(["F", "M"], dtype=pl.Enum(["M", "F"])),
}


def _table(name: str, on_missing: str | float) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"sex": ["M", "F"], "q": [0.1, 0.2]}),
        dimensions={"sex": "sex"},
        value="q",
        storage_mode="hash",
        on_missing=on_missing,
    )


@pytest.mark.parametrize("key", sorted(_KEYS))
@pytest.mark.parametrize("on_missing", ["raise", "nan", 0.0])
def test_a_dictionary_encoded_key_reads_a_hash_table_by_label(
    key: str, on_missing: str | float
) -> None:
    table = _table(f"hash_label_{key}_{on_missing}", on_missing)
    af = ActuarialFrame(pl.DataFrame({"s": _KEYS[key]}))
    af.q = table.lookup(sex=af.s)

    assert af.collect()["q"].to_list() == [0.2, 0.1]


@pytest.mark.parametrize("key", ["categorical", "enum"])
def test_a_per_period_dictionary_encoded_key_reads_a_hash_table_by_label(
    key: str,
) -> None:
    table = _table(f"hash_label_per_period_{key}", "nan")
    af = ActuarialFrame(pl.DataFrame({"s": _KEYS[key]}))
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 31), n_periods=1, frequency="annual"
    )
    af.s_t = af.s.projection.broadcast_to_periods()
    af.q = table.lookup(sex=af.s_t)

    assert af.collect()["q"].to_list() == [[0.2, 0.2], [0.1, 0.1]]
