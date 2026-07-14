# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lookups mixing per-row column keys with pl.lit() literal keys.

Regression tests for the batch-cliff bug: ``Table.lookup(col_key, pl.lit(x))``
failed with "lengths don't match: key columns not equal length" once the
frame no longer fit in a single streaming morsel (N depends on core count),
and at every N under the in-memory engine. The plugin must broadcast
unit-length literal key series to the batch length.
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table

BANDS = ["18-30", "31-45", "46-65"]
LIFE_RATES = {"18-30": 0.00012, "31-45": 0.00025, "46-65": 0.00072}


def _make_table(storage_mode: str) -> Table:
    return Table(
        name=f"lit_key_premium_rates_{storage_mode}",
        source=pl.DataFrame(
            {
                "age_band": ["18-30", "18-30", "31-45", "31-45", "46-65", "46-65"],
                "benefit": ["Life", "TPD", "Life", "TPD", "Life", "TPD"],
                "rate": [0.00012, 0.00035, 0.00025, 0.00081, 0.00072, 0.00204],
            }
        ),
        dimensions={"age_band": "age_band", "benefit": "benefit"},
        value="rate",
        storage_mode=storage_mode,
    )


def _make_portfolio(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": list(range(n)),
            "age_band": [BANDS[i % 3] for i in range(n)],
        }
    )


@pytest.mark.parametrize("storage_mode", ["auto", "hash"])
@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
@pytest.mark.parametrize("n", [2, 15, 100, 1000])
def test_column_key_with_literal_key(n: int, engine: str, storage_mode: str) -> None:
    table = _make_table(storage_mode)
    af = ActuarialFrame(_make_portfolio(n))
    af.rate = table.lookup(age_band=af["age_band"], benefit=pl.lit("Life"))
    out = af.collect(engine=engine)
    assert out.height == n
    expected = [LIFE_RATES[BANDS[i % 3]] for i in range(n)]
    assert out["rate"].to_list() == pytest.approx(expected)


def test_both_keys_literal() -> None:
    table = _make_table("auto")
    af = ActuarialFrame(_make_portfolio(100))
    af.rate = table.lookup(age_band=pl.lit("31-45"), benefit=pl.lit("Life"))
    out = af.collect()
    assert out["rate"].to_list() == pytest.approx([0.00025] * 100)
