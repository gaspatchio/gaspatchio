# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Where settling a batch spends its time, on whatever device JAX has.

The GPU runner's scaling report showed settling a million level-4 policies
take 80 s on the runner's CPU (JAX 0.11) against 3 s on a laptop CPU (JAX
0.4.38) and under 2 s on the card. This probe answers where: it settles a few
full batches under cProfile, and times the projection's boundary grid both
compiled and run one operation at a time over one batch's own start days --
the change most likely to behave differently on another JAX.

Information only, like the scaling bench. Usage, from ``engines/jax``::

    .venv/bin/python -m bench.settle_probe --report settle.txt
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import statistics
import time
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
import polars as pl

from bench.test_scaling import MODELS_DIR, _artifact, _tiled
from gaspatchio_jax.batching import chunks, grouped
from gaspatchio_jax.lowerings import schedule
from gaspatchio_jax.plan import ExecutionPlan

BATCHES = 4
TIMINGS = 5


def _boundary_grid(months: int, bucket: int, rows: int) -> dict[str, float | bool]:
    """Time the boundary grid compiled and op by op, on one batch's shape."""
    start = jnp.full((rows,), 19723, dtype=jnp.int64)  # 2024-01-01
    compiled = schedule.boundaries_from_original
    plain = compiled.__wrapped__  # type: ignore[attr-defined]
    compiled(start, months, bucket).block_until_ready()
    plain(start, months, bucket).block_until_ready()
    took: dict[str, list[float]] = {"compiled": [], "op_by_op": []}
    for _ in range(TIMINGS):
        for name, one in (("compiled", compiled), ("op_by_op", plain)):
            at = time.perf_counter()
            one(start, months, bucket).block_until_ready()
            took[name].append(time.perf_counter() - at)
    same = bool(
        np.array_equal(
            np.asarray(compiled(start, months, bucket)),
            np.asarray(plain(start, months, bucket)),
        )
    )
    return {
        "compiled_s": statistics.median(took["compiled"]),
        "op_by_op_s": statistics.median(took["op_by_op"]),
        "identical": same,
    }


def main(argv: list[str] | None = None) -> int:
    """Profile settling and time the boundary grid; write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    document = _artifact("level-4")
    book = pl.read_parquet(MODELS_DIR / "level-4.book.parquet")
    plan = ExecutionPlan.stage_inspect(document)
    prepared = plan.stage_prepare(
        plan.stage_validate_inputs(_tiled(book, BATCHES * 65_536))
    )
    group = grouped(prepared.widths, prepared.inputs.rows)[0]
    size = plan._batch_for(prepared, group, 2 * 1024**3)[0]  # noqa: SLF001

    profile = cProfile.Profile()
    settle: list[float] = []
    shape: tuple[int, int] | None = None
    for rows in list(chunks(group, size))[:BATCHES]:
        at = time.perf_counter()
        profile.enable()
        settled = plan.stage_settle(prepared, rows)
        profile.disable()
        settle.append(time.perf_counter() - at)
        shape = (settled.count, max((a.bucket for a in _horizons(settled)), default=0))

    grid = _boundary_grid(1, shape[1] if shape and shape[1] else 120, size)
    listing = io.StringIO()
    pstats.Stats(profile, stream=listing).sort_stats("cumulative").print_stats(30)
    tottime = io.StringIO()
    pstats.Stats(profile, stream=tottime).sort_stats("tottime").print_stats(20)
    summary = {
        "jax": jax.__version__,
        "backend": jax.default_backend(),
        "devices": [one.device_kind for one in jax.devices()],
        "batch": size,
        "settle_s_per_batch": [round(one, 3) for one in settle],
        "boundary_grid_one_batch": grid,
    }
    args.report.write_text(
        json.dumps(summary, indent=2)
        + "\n\n== settle, cumulative ==\n"
        + listing.getvalue()
        + "\n== settle, own time ==\n"
        + tottime.getvalue(),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))  # noqa: T201 -- the report is the output
    return 0


def _horizons(settled: object) -> list[object]:
    """Return the horizons a settled batch carries, for its widest bucket."""
    values = getattr(settled, "values", {})
    return [
        value.horizon
        for value in values.values()
        if getattr(value, "horizon", None) is not None
    ]


if __name__ == "__main__":
    raise SystemExit(main())
