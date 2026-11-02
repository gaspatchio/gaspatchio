# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A full grid is written where the user says, or the run refuses.

``return_full_grid=True`` spills every batch's full projection to parquet --
that is its whole design: the grid on disk, memory bounded by one batch.
With no ``sink_dir`` it chose one itself, ``./scenarios_<epoch>/`` in the
working directory, and said nothing (capital-regimes-r5 found two such
directories after its first runs). The run now refuses before it does any
work and names the argument that fixes it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum, for_each_scenario

if TYPE_CHECKING:
    from pathlib import Path


def _model_fn(af, *, tables, drivers):  # noqa: ANN202, ARG001
    return af.with_columns(pl.col("sum_insured").alias("value"))


def _main(af):  # noqa: ANN202
    """The frame-only model a ScenarioRun runs unchanged."""
    return af.with_columns(pl.col("sum_insured").alias("value"))


def _af() -> ActuarialFrame:
    return ActuarialFrame({"policy_id": [1, 2], "sum_insured": [100.0, 200.0]})


def test_for_each_scenario_refuses_a_full_grid_with_nowhere_to_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No sink_dir: refuse, naming sink_dir, and create nothing in the cwd."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="sink_dir"):
        for_each_scenario(
            _af(),
            ["BASE", "UP"],
            _model_fn,
            aggregations=(Sum("value").alias("total"),),
            batch_size=1,
            return_full_grid=True,
        )
    assert list(tmp_path.iterdir()) == []


def test_scenario_run_refuses_a_full_grid_with_nowhere_to_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ScenarioRun.run carries the same refusal."""
    monkeypatch.chdir(tmp_path)
    plan = ScenarioRun(
        shocks={"BASE": []},
        base_tables={},
        aggregations=(Sum("value").alias("total"),),
    )
    with pytest.raises(ValueError, match="sink_dir"):
        plan.run(_af(), _main, batch_size=1, return_full_grid=True)
    assert list(tmp_path.iterdir()) == []


def test_full_grid_lands_in_the_sink_dir_given(tmp_path: Path) -> None:
    """With sink_dir the grid is written there, one parquet file per batch."""
    sink = tmp_path / "grid"
    result = for_each_scenario(
        _af(),
        ["BASE", "UP"],
        _model_fn,
        aggregations=(Sum("value").alias("total"),),
        batch_size=1,
        return_full_grid=True,
        sink_dir=sink,
    )
    assert result.sink_dir == sink
    assert sorted(p.name for p in sink.iterdir()) == [
        "batch_0000.parquet",
        "batch_0001.parquet",
    ]
