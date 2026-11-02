# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``sink_dir`` takes a directory however the caller spells it.

A string is how most people write a directory, and ``os.PathLike`` is how
the rest of Python hands one over. Typed ``Path`` and used as one,
``sink_dir="grid"`` failed with ``AttributeError: 'str' object has no
attribute 'mkdir'`` on a full grid and with a ``TypeError`` on the audit
record's path. It is now made a ``Path`` where it comes in, and
``result.sink_dir`` is that ``Path``.
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
import pytest

from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum, for_each_scenario


class _Spelled(os.PathLike):  # type: ignore[type-arg]
    """A path-like that is neither ``str`` nor ``Path``."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __fspath__(self) -> str:
        return str(self._path)


def _model_fn(af, *, tables, drivers):  # noqa: ANN202, ARG001
    return af.with_columns(pl.col("sum_insured").alias("value"))


def _main(af):  # noqa: ANN202
    """The frame-only model a ScenarioRun runs unchanged."""
    return af.with_columns(pl.col("sum_insured").alias("value"))


def _af() -> ActuarialFrame:
    return ActuarialFrame({"policy_id": [1, 2], "sum_insured": [100.0, 200.0]})


@pytest.mark.parametrize("spell", [str, _Spelled, Path])
def test_a_full_grid_lands_in_a_sink_dir_spelled_any_way(
    tmp_path: Path, spell: type
) -> None:
    """str, os.PathLike and Path all name the directory the grid is written to."""
    where = tmp_path / "grid"
    result = for_each_scenario(
        _af(),
        ["BASE", "UP"],
        _model_fn,
        aggregations=(Sum("value").alias("total"),),
        batch_size=1,
        return_full_grid=True,
        sink_dir=spell(where),
    )
    assert result.sink_dir == where
    assert isinstance(result.sink_dir, Path)
    assert sorted(p.name for p in where.iterdir()) == [
        "batch_0000.parquet",
        "batch_0001.parquet",
    ]


@pytest.mark.parametrize("spell", [str, _Spelled])
def test_the_audit_record_goes_to_a_sink_dir_given_as_text(
    tmp_path: Path, spell: type
) -> None:
    """ScenarioRun.run(audit=True) writes its record into a sink_dir given as text."""
    where = tmp_path / "out"
    plan = ScenarioRun(
        shocks={"BASE": []},
        base_tables={},
        aggregations=(Sum("value").alias("total"),),
    )
    result = plan.run(
        _af(),
        _main,
        batch_size=1,
        sink_dir=spell(where),
        audit=True,
    )
    assert result.audit_path is not None
    assert result.audit_path.parent == where
    assert result.audit_path.exists()
