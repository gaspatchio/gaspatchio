# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for for_each_scenario with dict[ID, list[Shock]] shape.
# ABOUTME: Verifies batched scenario-stacked Tables match per-scenario runs.
"""Test for_each_scenario with dict[ID, list[Shock]] shape."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio.assumptions import Table
from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import (
    MultiplicativeShock,
    Sum,
    for_each_scenario,
)


@pytest.fixture
def af() -> ActuarialFrame:
    """Two-policy frame keyed by age, used for shocked-mortality lookups."""
    return ActuarialFrame({"policy_id": [1, 2], "age": [30, 31]})


@pytest.fixture
def mortality_table() -> Table:
    """Build the base mortality table shocked per-scenario by the loop."""
    return _mortality()


def _mortality() -> Table:
    """The base mortality table the model reads and the plan shocks."""
    df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
    return Table(
        name="mortality_for_each_shocks",
        source=df,
        dimensions={"age": "age"},
        value="rate",
    )


def _shock_model(af: ActuarialFrame) -> ActuarialFrame:
    """Look up mortality by age, the model's own read; scale to readable units."""
    af.qx = _mortality().lookup(age=af.age)
    return af.with_columns((pl.col("qx") * 1e6).alias("value"))


def test_shocks_dict_batched_equals_unbatched(
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """batch_size=1 (per-scenario kernel) must agree with batch_size=2 (stacked)."""
    shocks: dict[str, list] = {
        "BASE": [],
        "STRESS": [MultiplicativeShock(factor=2.0, table="mortality_for_each_shocks")],
    }
    one = for_each_scenario(
        af,
        scenarios=shocks,
        model_fn=_shock_model,
        aggregations=(Sum("value").alias("total"),),
        base_tables={"mortality_for_each_shocks": mortality_table},
        batch_size=1,
    )
    two = for_each_scenario(
        af,
        scenarios=shocks,
        model_fn=_shock_model,
        aggregations=(Sum("value").alias("total"),),
        base_tables={"mortality_for_each_shocks": mortality_table},
        batch_size=2,
    )
    assert one.aggregations["total"] == pytest.approx(two.aggregations["total"])


def test_classify_rejects_mixed_dict(
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """Dict with mixed value types raises TypeError."""
    with pytest.raises(TypeError, match="mixed value types"):
        for_each_scenario(
            af,
            scenarios={"A": [], "B": {"driver": 1}},  # list + dict mixed
            model_fn=_shock_model,
            aggregations=(Sum("value").alias("total"),),
            base_tables={"mortality_for_each_shocks": mortality_table},
        )


def test_classify_rejects_non_list_non_dict(
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """Non-list, non-dict scenarios raises TypeError."""
    with pytest.raises(TypeError, match="must be list or dict"):
        for_each_scenario(
            af,
            scenarios="not a valid shape",  # type: ignore[arg-type]
            model_fn=_shock_model,
            aggregations=(Sum("value").alias("total"),),
            base_tables={"mortality_for_each_shocks": mortality_table},
        )


def test_table_scoped_shock_applies_only_to_named_table(
    af: ActuarialFrame,
) -> None:
    """A Shock with table='mortality' is filtered out for other tables."""
    mortality = Table(
        name="mortality",
        source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]}),
        dimensions={"age": "age"},
        value="rate",
    )
    lapse = Table(
        name="lapse",
        source=pl.DataFrame({"age": [30, 31], "rate": [0.05, 0.05]}),
        dimensions={"age": "age"},
        value="rate",
    )

    def _two_table_model(af: ActuarialFrame) -> ActuarialFrame:
        af.qx = mortality.lookup(age=af.age)
        af.lx = lapse.lookup(age=af.age)
        af.value = af.qx + af.lx
        return af

    targeted = MultiplicativeShock(factor=2.0, table="mortality")
    scenarios: dict[str, list] = {"BASE": [], "STRESS": [targeted]}

    result = for_each_scenario(
        af,
        scenarios=scenarios,
        model_fn=_two_table_model,
        aggregations=(Sum("value").alias("total"),),
        base_tables={"mortality": mortality, "lapse": lapse},
        batch_size=2,
    )
    # BASE reads 0.0011 + 0.05 per policy; STRESS doubles mortality alone.
    assert result.aggregations["total"] == pytest.approx(
        (0.001 + 0.0012 + 0.10) + (0.002 + 0.0024 + 0.10)
    )
    assert result.n_scenarios == 2
