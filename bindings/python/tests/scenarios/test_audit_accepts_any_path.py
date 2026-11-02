# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``audit=`` takes a path however the caller spells it.

``audit`` was ``bool | Path``: ``True`` writes the record to the default
location, a ``Path`` writes it there. A string -- how most people write a
path -- was read as truthy, so ``audit="record.json"`` wrote the record to
``./gaspatchio_audit/<run_id>.audit.json`` and left nothing where the caller
asked. A string or any ``os.PathLike`` is now the path, exactly as a ``Path``
is, on both ``ScenarioRun.run`` and ``run_aggregated``.
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
import pytest

from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum, run_aggregated


class _Spelled(os.PathLike):  # type: ignore[type-arg]
    """A path-like that is neither ``str`` nor ``Path``."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __fspath__(self) -> str:
        return str(self._path)


def _scenario_model(af):  # noqa: ANN202
    return af.with_columns(pl.col("sum_insured").alias("value"))


def _policy_model(af: ActuarialFrame) -> ActuarialFrame:
    return af.with_columns(pl.col("sum_insured").alias("value"))


_BOOK = {"policy_id": [1, 2], "sum_insured": [100.0, 200.0]}


@pytest.mark.parametrize("spell", [str, _Spelled, Path])
def test_scenario_run_writes_its_record_where_a_path_like_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spell: type
) -> None:
    """str, os.PathLike and Path all name the record's file; nothing else is written."""
    monkeypatch.chdir(tmp_path)
    where = tmp_path / "records" / "plan.audit.json"
    plan = ScenarioRun(
        shocks={"BASE": []},
        base_tables={},
        aggregations=(Sum("value").alias("total"),),
    )
    result = plan.run(
        ActuarialFrame(_BOOK), _scenario_model, batch_size=1, audit=spell(where)
    )
    assert result.audit_path == where
    assert isinstance(result.audit_path, Path)
    assert where.exists()
    assert not (tmp_path / "gaspatchio_audit").exists()


@pytest.mark.parametrize("spell", [str, _Spelled, Path])
def test_run_aggregated_writes_its_record_where_a_path_like_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spell: type
) -> None:
    """The policy axis takes the same spellings."""
    monkeypatch.chdir(tmp_path)
    where = tmp_path / "book.audit.json"
    result = run_aggregated(
        _policy_model,
        pl.DataFrame(_BOOK),
        [Sum("value").alias("total")],
        batch_size=1,
        audit=spell(where),
    )
    assert result.audit_path == where
    assert where.exists()
    assert not (tmp_path / "gaspatchio_audit").exists()


def test_true_and_false_keep_their_meaning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """True is the default location and False writes nothing, as before."""
    monkeypatch.chdir(tmp_path)
    book = pl.DataFrame(_BOOK)
    aggs = [Sum("value").alias("total")]
    assert run_aggregated(_policy_model, book, aggs, audit=False).audit_path is None
    written = run_aggregated(_policy_model, book, aggs, audit=True).audit_path
    assert written is not None
    assert written.parent == Path("gaspatchio_audit")
