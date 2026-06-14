# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for the policy-axis parquet spill sink."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core.scenarios._spill import (
    check_spill_target,
    fstype_for_path,
    safe_write_parquet,
)

_MOUNTS = (
    "proc /proc proc rw 0 0\n"
    "/dev/disk1 / ext4 rw 0 0\n"
    "tmpfs /tmp tmpfs rw 0 0\n"
    "/dev/disk2 /data ext4 rw 0 0\n"
)


def test_fstype_picks_longest_matching_mount():
    assert fstype_for_path("/tmp/x/y", _MOUNTS) == "tmpfs"
    assert fstype_for_path("/data/out", _MOUNTS) == "ext4"
    assert fstype_for_path("/home/u", _MOUNTS) == "ext4"  # falls back to '/'


def test_check_spill_target_refuses_tmpfs(tmp_path):
    with pytest.raises(ValueError, match="RAM-backed"):
        check_spill_target(tmp_path, mounts_text=_MOUNTS, resolved="/tmp/run")


def test_check_spill_target_allows_real_disk(tmp_path):
    # ext4 mount -> OK (returns None)
    check_spill_target(tmp_path, mounts_text=_MOUNTS, resolved="/data/run")


def test_safe_write_creates_final_and_no_temp(tmp_path):
    frame = pl.DataFrame({"a": [1, 2, 3]})
    final = tmp_path / "batch_0000.parquet"
    safe_write_parquet(frame, final)
    assert final.exists()
    assert pl.read_parquet(final)["a"].to_list() == [1, 2, 3]
    # no leftover temp files in the directory
    assert list(tmp_path.glob("*.tmp")) == []


def test_safe_write_temp_is_same_directory(tmp_path, monkeypatch):
    seen: dict[str, Path] = {}
    real_replace = __import__("os").replace

    def spy(src: object, dst: object) -> None:
        seen["src_parent"] = Path(str(src)).parent
        seen["dst_parent"] = Path(str(dst)).parent
        real_replace(src, dst)

    monkeypatch.setattr("gaspatchio_core.scenarios._spill.os.replace", spy)
    safe_write_parquet(pl.DataFrame({"a": [1]}), tmp_path / "x.parquet")
    assert seen["src_parent"] == seen["dst_parent"]  # same FS -> atomic rename works


from gaspatchio_core.scenarios._spill import preflight_disk


def test_preflight_passes_when_room(tmp_path):
    preflight_disk(tmp_path, estimated_bytes=1)  # ~unlimited vs 1 byte -> OK


def test_preflight_fails_loud_when_insufficient(tmp_path, monkeypatch):
    import shutil

    monkeypatch.setattr(
        "gaspatchio_core.scenarios._spill.shutil.disk_usage",
        lambda _p: shutil._ntuple_diskusage(total=10, used=9, free=1),  # noqa: SLF001
    )
    with pytest.raises(OSError, match="insufficient disk"):
        preflight_disk(tmp_path, estimated_bytes=1_000_000)


from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios._spill import run_to_parquet


def _toy_full_model(af: ActuarialFrame) -> ActuarialFrame:
    df = af._df.with_columns((pl.col("value") * 10).alias("scaled"))  # noqa: SLF001
    return ActuarialFrame(df)


def test_run_to_parquet_writes_all_policies(tmp_path):
    mp = pl.DataFrame({"value": [float(i) for i in range(1, 11)]})  # 10 policies
    out = run_to_parquet(_toy_full_model, mp, tmp_path / "out", batch_size=3)
    # 10 policies / 3 -> 4 batch files
    files = sorted((tmp_path / "out").glob("batch_*.parquet"))
    assert len(files) == 4
    combined = pl.concat([pl.read_parquet(f) for f in files]).sort("value")
    assert combined["scaled"].to_list() == [v * 10 for v in range(1, 11)]
    assert out.n_policies == 10
    assert out.n_batches == 4


def test_for_each_sink_does_not_require_scenario_id(tmp_path):
    """A frame with NO scenario_id column must spill without a KeyError."""
    df = pl.DataFrame({"policy": [1, 2, 3], "v": [1.0, 2.0, 3.0]})
    from gaspatchio_core.scenarios._for_each import _write_batch_parquet

    _write_batch_parquet(df, tmp_path / "b0.parquet")  # must not raise
    assert pl.read_parquet(tmp_path / "b0.parquet")["policy"].to_list() == [1, 2, 3]


def test_run_to_parquet_top_level_export():
    import gaspatchio_core as gsp

    assert hasattr(gsp, "run_to_parquet")


def test_run_to_parquet_auto_batches_to_budget(tmp_path, monkeypatch):
    """auto path: the shared sizer's B drives the number of batch files."""
    import gaspatchio_core.scenarios._spill as spill

    mp = pl.DataFrame({"value": [float(i) for i in range(1, 11)]})  # 10 policies
    monkeypatch.setattr(spill, "size_to_budget", lambda *a, **k: 4)
    out = run_to_parquet(
        _toy_full_model,
        mp,
        tmp_path / "out",
        batch_size="auto",
        mounts_text="/dev/disk1 / ext4 rw 0 0\n",  # mark target as real disk
    )
    files = sorted((tmp_path / "out").glob("batch_*.parquet"))
    assert len(files) == 3  # 10 / 4 -> [4, 4, 2]
    assert out.n_batches == 3


def test_preflight_disk_uses_frame_size_not_peak_rss(tmp_path, monkeypatch):
    """Disk preflight estimates from the output frame, not the peak RSS (#15)."""
    import gaspatchio_core.scenarios._spill as spill

    captured: dict[str, int] = {}
    real_collect = spill._collect_with_peak  # noqa: SLF001

    def _huge_peak(lazy: object, *, engine: str | None = None) -> object:
        frame, _peak = real_collect(lazy, engine=engine)
        return frame, 10 * 1024**3  # 10 GB transient peak, far above the tiny frame

    def _spy_preflight(_directory: object, *, estimated_bytes: int) -> None:
        captured["estimated_bytes"] = estimated_bytes  # capture, don't raise

    monkeypatch.setattr(spill, "_collect_with_peak", _huge_peak)
    monkeypatch.setattr(spill, "preflight_disk", _spy_preflight)
    monkeypatch.setattr(spill, "size_to_budget", lambda *a, **k: 10)  # noqa: ARG005
    mp = pl.DataFrame({"value": [float(i) for i in range(1, 5)]})  # 4 policies
    run_to_parquet(
        _toy_full_model,
        mp,
        tmp_path / "out",
        batch_size="auto",
        mounts_text="/dev/disk1 / ext4 rw 0 0\n",
    )
    # Frame-size-derived estimate is tiny; the peak-derived one would be ~tens of GB.
    assert captured["estimated_bytes"] < 1024**2  # < 1 MB, nowhere near 10 GB/policy
