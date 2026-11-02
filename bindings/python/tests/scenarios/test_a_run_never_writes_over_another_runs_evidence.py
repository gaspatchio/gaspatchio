# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A run never writes over another run's evidence without being told to.

``audit=True`` names the record by the run's id, the time to the second and
the plan's sha, so two runs of one plan in one second wrote one file and the
second silently replaced the first. The default name now refuses a file
already there, naming ``audit=PATH``, and leaves the earlier record as it was.
The same holds into a ``sink_dir``, and for ``run_aggregated``'s record; a
full grid written into a ``sink_dir`` that already holds another run's batches
is refused before anything runs, because the second run would overwrite the
batches it reaches and leave the rest, one directory holding two runs.

A path the caller names is theirs: it is replaced, as before.
"""

from __future__ import annotations

import datetime as real_datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import run_aggregated
from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum, for_each_scenario
from gaspatchio.scenarios import _audit as audit_module

if TYPE_CHECKING:
    from pathlib import Path

_ONE_SECOND = real_datetime.datetime(2026, 10, 19, 18, 8, 49, tzinfo=real_datetime.UTC)


@pytest.fixture
def one_second(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hold the run-id clock on one second, as two quick runs meet it."""

    class _Clock:
        @staticmethod
        def now(tz: real_datetime.tzinfo | None = None) -> real_datetime.datetime:
            return _ONE_SECOND.astimezone(tz)

    monkeypatch.setattr(
        audit_module, "dt", SimpleNamespace(datetime=_Clock, UTC=real_datetime.UTC)
    )


def _main(af: ActuarialFrame) -> ActuarialFrame:
    return af.with_columns(pl.col("sum_insured").alias("value"))


def _model_fn(af, *, tables, drivers):  # noqa: ANN202, ARG001
    return _main(af)


def _af() -> ActuarialFrame:
    return ActuarialFrame({"policy_id": [1, 2], "sum_insured": [100.0, 200.0]})


def _plan() -> ScenarioRun:
    return ScenarioRun(shocks={"BASE": []}, aggregations=(Sum("value").alias("total"),))


@pytest.mark.usefixtures("one_second")
def test_a_second_run_in_one_second_does_not_overwrite_the_first_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    first = _plan().run(_af(), _main, batch_size=1, audit=True).audit_path
    assert first is not None
    held = first.read_bytes()

    with pytest.raises(FileExistsError) as refused:
        _plan().run(_af(), _main, batch_size=1, audit=True)

    message = str(refused.value)
    assert str(first) in message
    assert "an earlier run's evidence" in message
    assert "audit=Path('...')" in message
    assert first.read_bytes() == held
    assert sorted(p.name for p in first.parent.iterdir()) == [first.name]


@pytest.mark.usefixtures("one_second")
def test_the_same_holds_for_a_record_written_into_the_sink_dir(tmp_path: Path) -> None:
    sink = tmp_path / "sink"
    first = _plan().run(_af(), _main, batch_size=1, audit=True, sink_dir=sink)
    assert first.audit_path is not None
    assert first.audit_path.parent == sink
    held = first.audit_path.read_bytes()

    with pytest.raises(FileExistsError, match="audit=Path"):
        _plan().run(_af(), _main, batch_size=1, audit=True, sink_dir=sink)
    assert first.audit_path.read_bytes() == held


@pytest.mark.usefixtures("one_second")
def test_the_same_holds_for_run_aggregated_s_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    book = pl.DataFrame({"policy_id": [1, 2], "sum_insured": [100.0, 200.0]})
    aggs = [Sum("value").alias("total")]
    first = run_aggregated(_main, book, aggs, audit=True).audit_path
    assert first is not None
    held = first.read_bytes()

    with pytest.raises(FileExistsError, match="an earlier run's evidence"):
        run_aggregated(_main, book, aggs, audit=True)
    assert first.read_bytes() == held


@pytest.mark.usefixtures("one_second")
def test_a_path_the_caller_names_is_theirs_to_replace(tmp_path: Path) -> None:
    where = tmp_path / "evidence" / "q3.audit.json"
    _plan().run(_af(), _main, batch_size=1, audit=where)
    again = _plan().run(_af(), _main, batch_size=1, audit=where)

    assert again.audit_path == where
    assert where.exists()


def test_a_full_grid_into_a_directory_holding_another_grid_is_refused_first(
    tmp_path: Path,
) -> None:
    sink = tmp_path / "grid"
    for_each_scenario(
        _af(),
        ["BASE", "UP"],
        _model_fn,
        aggregations=(Sum("value").alias("total"),),
        batch_size=1,
        return_full_grid=True,
        sink_dir=sink,
    )
    held = {path.name: path.read_bytes() for path in sink.iterdir()}
    ran: list[str] = []

    def counted(af, *, tables, drivers):  # noqa: ANN202, ARG001
        ran.append("ran")
        return _main(af)

    with pytest.raises(FileExistsError) as refused:
        for_each_scenario(
            _af(),
            ["BASE"],
            counted,
            aggregations=(Sum("value").alias("total"),),
            batch_size=1,
            return_full_grid=True,
            sink_dir=sink,
        )

    message = str(refused.value)
    assert "batch_0000.parquet, batch_0001.parquet" in message
    assert "Nothing was run" in message
    assert ran == []
    assert {path.name: path.read_bytes() for path in sink.iterdir()} == held


def test_a_full_grid_into_a_directory_holding_other_files_runs(tmp_path: Path) -> None:
    """Only another grid's batches are another run's grid."""
    sink = tmp_path / "grid"
    sink.mkdir()
    (sink / "notes.txt").write_text("kept")
    result = for_each_scenario(
        _af(),
        ["BASE"],
        _model_fn,
        aggregations=(Sum("value").alias("total"),),
        batch_size=1,
        return_full_grid=True,
        sink_dir=sink,
    )

    assert result.sink_dir == sink
    assert (sink / "notes.txt").read_text() == "kept"
