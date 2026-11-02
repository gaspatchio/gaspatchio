# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Policy-axis parquet spill: write each batch to disk, never co-resident.
# ABOUTME: Refuses RAM-backed targets, preflights disk, renames atomically.

"""Memory-safe full-output spill for run_to_parquet (and the scenario sink fix)."""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import psutil

from gaspatchio._dtypes import with_integers_as_i64
from gaspatchio.frame._across_rows import one_batch_of_several
from gaspatchio.frame.base import _frame_over_the_book
from gaspatchio.scenarios._auto_batch import bounded_seed_size, size_to_budget
from gaspatchio.scenarios._batch import _collect_batch, book_in_hand

if TYPE_CHECKING:
    from collections.abc import Callable

    import polars as pl

    from gaspatchio.frame import ActuarialFrame

_DISK_HEADROOM = 1.10  # require 10% slack over the estimate

_RAM_BACKED = frozenset({"tmpfs", "ramfs"})
_MOUNTS_MIN_FIELDS = 3  # device mountpoint fstype ...


def fstype_for_path(path: str, mounts_text: str) -> str | None:
    """Filesystem type of the longest mountpoint that is a prefix of ``path``.

    ``mounts_text`` is the contents of ``/proc/mounts`` (injected for tests).
    """
    best_len = -1
    best_fs: str | None = None
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < _MOUNTS_MIN_FIELDS:
            continue
        mountpoint, fstype = parts[1], parts[2]
        mp = mountpoint.rstrip("/") or "/"
        is_prefix = path == mp or path.startswith(mp + "/") or mp == "/"
        if is_prefix and len(mp) > best_len:
            best_len, best_fs = len(mp), fstype
    return best_fs


def check_spill_target(
    directory: Path, *, mounts_text: str | None = None, resolved: str | None = None
) -> None:
    """Raise if ``directory`` is RAM-backed (tmpfs/ramfs) — spilling there re-OOMs."""
    resolved = resolved if resolved is not None else str(directory.resolve())
    if mounts_text is None:
        try:
            mounts_text = Path("/proc/mounts").read_text()
        except OSError:
            return  # non-Linux / unreadable -> can't check, allow (best effort)
    fstype = fstype_for_path(resolved, mounts_text)
    if fstype in _RAM_BACKED:
        msg = (
            f"Spill target {directory} is on a RAM-backed filesystem ({fstype}); "
            "writing batches there counts against the same memory cgroup and re-OOMs. "
            "Choose an output_dir on a real disk."
        )
        raise ValueError(msg)


def safe_write_parquet(frame: object, final_path: Path) -> None:
    """Write a Polars DataFrame to ``final_path`` atomically.

    Writes to a temp file in the SAME directory (so ``os.replace`` is a real atomic
    rename — cross-filesystem rename would raise ``EXDEV``), then renames.
    """
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = final_path.with_suffix(final_path.suffix + ".tmp")
    try:
        frame.write_parquet(tmp)  # type: ignore[attr-defined]
        os.replace(tmp, final_path)  # noqa: PTH105 — intentional; Path.replace() doesn't accept a Path target in all Python versions, and we need os.replace for the monkeypatch in tests
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def preflight_disk(directory: Path, *, estimated_bytes: int) -> None:
    """Raise OSError before batch 1 if ``directory``'s filesystem lacks room."""
    free = shutil.disk_usage(directory).free
    needed = int(estimated_bytes * _DISK_HEADROOM)
    if free < needed:
        need_gb = needed / 1024**3
        have_gb = free / 1024**3
        msg = (
            f"insufficient disk for spill at {directory}: "
            f"need ~{need_gb:.1f} GB, have {have_gb:.1f} GB free."
        )
        raise OSError(msg)


@dataclass(frozen=True)
class SpillResult:
    """Manifest of a :func:`run_to_parquet` spill.

    ``n_policies`` is the number of policies the model valued, which is the
    rows written. A model that chooses which policies it values
    (``af.filter``, a semi or anti join) values fewer than the book holds,
    and the count says so.
    """

    output_dir: Path
    n_policies: int
    n_batches: int
    wall_time_s: float
    peak_rss_mb: float | None


def run_to_parquet(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame | pl.LazyFrame,
    output_dir: Path,
    *,
    batch_size: int | Literal["auto"] = "auto",
    mounts_text: str | None = None,
) -> SpillResult:
    """Project all policies in memory-safe batches, writing each batch to parquet.

    For the full per-policy output (C1-tight/C2) that cannot fold to aggregates.
    The working-set cap is OFF here — batching is purely for memory safety.

    Args:
        model_fn: Callable accepting an :class:`ActuarialFrame` and returning one.
        model_points: Polars DataFrame of policy data, or a LazyFrame, which is
            collected first; rows are sliced into batches.
        output_dir: Directory where ``batch_NNNN.parquet`` files are written.
        batch_size: Number of policies per batch.  ``"auto"`` sizes to the memory
            budget (no working-set cap).
        mounts_text: Injected ``/proc/mounts`` text for tests; ``None`` reads the
            real file (or skips on non-Linux).

    Returns:
        :class:`SpillResult` manifest with file count and timing metadata.

    """
    model_points = book_in_hand(model_points, "run_to_parquet")
    n_policies = model_points.height
    if n_policies == 0:
        msg = "model_points is empty."
        raise ValueError(msg)
    # A wide integer column is judged over the book, not over each batch:
    # read as Int64 here where every value in the book fits, and kept in
    # its width where one does not. Each batch is handed on as a plan, so
    # the frame's door does not judge it again over the batch's values alone
    # (section 10).
    model_points = with_integers_as_i64(model_points)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    check_spill_target(output_dir, mounts_text=mounts_text)

    if batch_size == "auto":
        # Size to the memory budget (no working-set cap): seed -> per_cell -> B.
        seed_size = bounded_seed_size(n_policies)
        seed = model_points.slice(0, seed_size)
        with one_batch_of_several(
            runner="run_to_parquet",
            n_policies=n_policies,
            batch_size="auto",
            first=seed_size,
            batch=seed,
        ):
            seed_af = model_fn(_frame_over_the_book(seed.lazy(), judged=True))
        _seed_df, seed_peak = _collect_batch(seed_af, engine="streaming")
        frame_bytes = int(_seed_df.estimated_size())
        # MEMORY sizing floors the measured peak with the frame size: a fast seed
        # collect can complete between RSS samples (seed_peak==0), which would collapse
        # per_cell to 1 byte and size the WHOLE dataset into one batch.
        per_cell = max(1, max(seed_peak, frame_bytes) // max(1, seed_size))
        # DISK preflight estimates from the UNCOMPRESSED output frame, NOT the transient
        # peak RSS (which includes projection intermediates far larger than the written
        # parquet) — using peak would spuriously fail preflight on a roomy disk. Parquet
        # is smaller still, so the frame size is a safe upper bound.
        disk_per_cell = max(1, frame_bytes // max(1, seed_size))
        preflight_disk(output_dir, estimated_bytes=disk_per_cell * n_policies)
        resolved = size_to_budget(per_cell, n_policies)
        del _seed_df
    else:
        resolved = int(batch_size)

    started = time.perf_counter()
    baseline = psutil.Process().memory_info().rss
    peak = baseline
    batch_idx = 0
    # The policies the model valued, which is the rows written: a model that
    # selects (``af.filter``, a semi or anti join) values fewer than the book
    # holds. The seed above only sizes the batches and is not written.
    valued = 0
    for start in range(0, n_policies, resolved):
        batch = model_points.slice(start, resolved)
        with one_batch_of_several(
            runner="run_to_parquet",
            n_policies=n_policies,
            batch_size=batch_size,
            first=resolved,
            batch=batch,
        ):
            out_af = model_fn(_frame_over_the_book(batch.lazy(), judged=True))
        proj, _ = _collect_batch(out_af, engine="streaming")
        safe_write_parquet(proj, output_dir / f"batch_{batch_idx:04d}.parquet")
        valued += proj.height
        del proj
        peak = max(peak, psutil.Process().memory_info().rss)
        batch_idx += 1

    return SpillResult(
        output_dir=output_dir,
        n_policies=valued,
        n_batches=batch_idx,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=max(0, peak - baseline) / (1024 * 1024),
    )


__all__ = [
    "SpillResult",
    "check_spill_target",
    "fstype_for_path",
    "preflight_disk",
    "run_to_parquet",
    "safe_write_parquet",
]
