# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The null rule, period by period: a period with no value answers None.

The scalar aggregators skip a null and answer null when they saw nothing but
nulls. The per-period kinds did not: a period whose every value is null came
out of ``PeriodSum`` as ``0.0`` and out of ``PeriodMean``, ``PeriodMin``,
``PeriodMax``, ``PeriodVariance``, ``PeriodStd``, ``PeriodMedian``,
``PeriodQuantile`` and ``PeriodCTE`` as NaN. On the scenario axis the
within-scenario total turned a scenario whose period held only nulls into a
``0.0`` that every kind then counted as a value; and a batch whose period held
only nulls made ``PeriodMin``/``PeriodMax`` NaN for that period even when
another batch had a value there.

A vector cannot hold ``None`` as a float, so the answer is a numpy masked
array: the period is masked, ``.tolist()`` reads ``None`` there, the data
underneath is NaN (never a plausible number), and a partitioned answer's tidy
frame holds null. ``PeriodCount`` counts the values it saw, so it answers 0.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
import pytest

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph.portfolio import _on_the_wire
from gaspatchio.scenarios import (
    PeriodCount,
    PeriodCTE,
    PeriodMax,
    PeriodMean,
    PeriodMedian,
    PeriodMin,
    PeriodQuantile,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    for_each_scenario,
)
from gaspatchio.scenarios._audit import _coerce_outputs_to_json

_ONE_VALUE_KINDS = (
    PeriodSum,
    PeriodMean,
    PeriodMin,
    PeriodMax,
    PeriodMedian,
    PeriodCTE,
)
_SPREAD_KINDS = (PeriodVariance, PeriodStd)


def _with_period(rows: list[list[float | None]]) -> pl.DataFrame:
    return pl.DataFrame({"cf": rows}, schema={"cf": pl.List(pl.Float64)}).with_columns(
        pl.int_ranges(pl.col("cf").list.len()).alias("__period"),
    )


def _fold(agg: Any, *batches: pl.DataFrame) -> Any:  # noqa: ANN401
    state = agg.create_accumulator()
    for batch in batches:
        state = agg.add_input(state, agg.batch_reduce(batch, "__period"))
    return agg.extract_output(state)


@pytest.mark.parametrize("kind", [*_ONE_VALUE_KINDS, *_SPREAD_KINDS])
def test_an_all_null_period_answers_none(kind: type) -> None:
    """Period 0 holds only nulls: None there, a number (or NaN for n=1 spread) after."""
    out = _fold(kind("cf"), _with_period([[None, 1.0, 4.0], [None, 3.0, 4.0]]))
    assert out.tolist()[0] is None
    assert all(value is not None for value in out.tolist()[1:])
    # The data under the mask is NaN, so a plain read never finds a fake 0.0.
    assert np.isnan(np.asarray(out)[0])


def test_period_quantile_answers_none_at_every_level() -> None:
    """Each level's vector is masked at the period with no value."""
    out = _fold(PeriodQuantile("cf", levels=(0.5, 0.9)), _with_period([[None, 1.0]]))
    for level in (0.5, 0.9):
        assert out[level].tolist() == [None, pytest.approx(1.0, rel=1e-3)]


def test_period_count_counts_zero_at_an_all_null_period() -> None:
    """Count counts values: an all-null period counts 0."""
    out = _fold(PeriodCount("cf"), _with_period([[None, 1.0], [None, 2.0]]))
    assert out.tolist() == [0.0, 2.0]


@pytest.mark.parametrize("kind", [PeriodSum, PeriodMin, PeriodMax, PeriodMean])
def test_a_batch_with_no_value_leaves_the_other_batchs_answer(kind: type) -> None:
    """Each period has a value in one batch only: the answer is that value."""
    out = _fold(kind("cf"), _with_period([[None, 1.0]]), _with_period([[5.0, None]]))
    assert out.tolist() == [5.0, 1.0]


# --- the scenario axis --------------------------------------------------------


def _model(af, *, tables, drivers):  # noqa: ANN202, ARG001
    """UP's first period has no value for any policy; BASE's does."""
    return af.with_columns(
        pl.when(pl.col("scenario_id") == "UP")
        .then(pl.col("flows_up"))
        .otherwise(pl.col("flows"))
        .alias("cf")
    )


def _book() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "flows": [[1.0, 2.0], [3.0, 4.0]],
                "flows_up": [[None, 2.0], [None, 4.0]],
            },
            schema={
                "policy_id": pl.Int64,
                "flows": pl.List(pl.Float64),
                "flows_up": pl.List(pl.Float64),
            },
        )
    )


def _run(*aggregations: Any) -> dict[str, Any]:  # noqa: ANN401
    return for_each_scenario(
        _book(),
        ["BASE", "UP"],
        _model,
        aggregations=aggregations,
        batch_size=1,
    ).aggregations


def test_a_scenario_with_no_value_at_a_period_is_null_in_the_tidy_frame() -> None:
    """PeriodSum.over('scenario_id'): UP's period 0 is null, not 0.0."""
    tidy = _run(PeriodSum("cf").alias("total").over("scenario_id"))["total"]
    got = {(row["scenario_id"], row["period"]): row["total"] for row in tidy.to_dicts()}
    assert got == {("BASE", 0): 4.0, ("BASE", 1): 6.0, ("UP", 0): None, ("UP", 1): 6.0}


def test_a_scenario_with_no_value_is_not_counted_across_scenarios() -> None:
    """Across scenarios, UP's empty period 0 is no value: not a 0.0 total."""
    out = _run(
        PeriodCount("cf").alias("n"),
        PeriodMin("cf").alias("least"),
        PeriodMean("cf").alias("mean"),
        PeriodMedian("cf").alias("median"),
    )
    assert out["n"].tolist() == [1.0, 2.0]
    assert out["least"].tolist() == [4.0, 6.0]
    assert out["mean"].tolist() == [4.0, 6.0]
    assert out["median"].tolist()[0] == pytest.approx(4.0, rel=1e-3)


# --- where the answer is written ----------------------------------------------


def test_the_audit_record_writes_null_at_the_masked_period() -> None:
    """The sidecar's JSON holds null, not NaN or 0.0, where the period had no value."""
    out = _fold(PeriodSum("cf"), _with_period([[None, 1.0]]))
    assert _coerce_outputs_to_json({"total": out}) == {"total": [None, 1.0]}


def test_the_policy_axis_entry_writes_null_at_the_masked_period() -> None:
    """A fold's entry on the artifact's policy axis carries null there."""
    out = _fold(PeriodSum("cf"), _with_period([[None, 1.0]]))
    assert _on_the_wire(out, period=None) == [None, 1.0]
    assert _on_the_wire(out, period=0) is None
