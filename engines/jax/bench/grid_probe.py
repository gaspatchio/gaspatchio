# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Which part of the compiled boundary grid is slow on JAX 0.11's CPU backend.

The first run found no single operation slow: the calendar's parts fused
together were (moved_by_months 5.2 s compiled against 0.55 s for its parts).
The calendar now places optimization barriers at its shared intermediates;
the first row under flags times the grid with them replaced by the identity,
so one run compares the two on one machine.

The settle probe found the projection's boundary grid taking 1.72 s compiled
and 0.51 s op by op on the GPU runner's CPU (JAX 0.11.2), against 0.024 s
compiled on a laptop (JAX 0.4.38). This times the grid's parts compiled, one
batch's shape each -- the two calendar conversions, the clamp, and the bare
integer operations they are made of, in 64 and 32 bits -- and the whole grid
again in child processes under each XLA flag worth trying.

Information only. Usage, from ``engines/jax``::

    .venv/bin/python -m bench.grid_probe --report grid.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jax
import jax.numpy as jnp

from gaspatchio_jax.lowerings import dates, schedule

if TYPE_CHECKING:
    from collections.abc import Callable

ROWS = 65_536
BUCKET = 120
TIMINGS = 5

# Flags tried on the whole grid, each in a fresh process. A flag this XLA
# does not know makes it exit, which is recorded rather than raised.
FLAGS = (
    "",
    "--xla_cpu_use_thunk_runtime=false",
    "--xla_cpu_enable_fast_math=true",
    "--xla_backend_optimization_level=0",
)


def _timed(fn: Callable[..., object], *args: object) -> float:
    """Return the median seconds of one compiled call, after a warm-up."""
    jax.block_until_ready(fn(*args))
    took = []
    for _ in range(TIMINGS):
        at = time.perf_counter()
        jax.block_until_ready(fn(*args))
        took.append(time.perf_counter() - at)
    return statistics.median(took)


def _parts() -> dict[str, float]:
    """Time each part of the grid, compiled, on one batch's rectangle."""
    days64 = jnp.broadcast_to(
        jnp.arange(ROWS, dtype=jnp.int64)[:, None] % 40_000 - 10_000,
        (ROWS, BUCKET),
    )
    days32 = days64.astype(jnp.int32)
    steps = jnp.arange(BUCKET, dtype=jnp.int64)[None, :]
    year, month, day = dates.civil_from_days(days64)
    start = jnp.full((ROWS,), 19723, dtype=jnp.int64)
    return {
        "whole grid": _timed(schedule.boundaries_from_original, start, 1, BUCKET),
        "moved_by_months": _timed(jax.jit(dates.moved_by_months), days64, steps),
        "civil_from_days": _timed(jax.jit(dates.civil_from_days), days64),
        "days_from_civil": _timed(jax.jit(dates.days_from_civil), year, month, day),
        "last_day_of": _timed(jax.jit(dates.last_day_of), year, month),
        "floor_divide i64 by 146097": _timed(
            jax.jit(lambda x: jnp.floor_divide(x, 146097)), days64
        ),
        "floor_divide i32 by 146097": _timed(
            jax.jit(lambda x: jnp.floor_divide(x, 146097)), days32
        ),
        "remainder i64 by 400": _timed(jax.jit(lambda x: x % 400), days64),
        "multiply-add i64": _timed(jax.jit(lambda x: x * 153 + 2), days64),
        "lax.div i64 by 146097 (truncating)": _timed(
            jax.jit(lambda x: jax.lax.div(x, jnp.int64(146097))), days64
        ),
    }


def _under_flag(flag: str, *, barriers: bool = True) -> dict[str, Any]:
    """Time the whole grid in a fresh process with one XLA flag set.

    ``barriers=False`` replaces the calendar's optimization barriers with the
    identity before the engine is imported, which is the grid as it was
    compiled before they were added.
    """
    code = (
        "import json, time, statistics, jax, jax.numpy as jnp\n"
        + ("" if barriers else "jax.lax.optimization_barrier = lambda x: x\n")
        + "import gaspatchio_jax\n"
        "from gaspatchio_jax.lowerings import schedule\n"
        f"s = jnp.full(({ROWS},), 19723, dtype=jnp.int64)\n"
        f"f = lambda: schedule.boundaries_from_original(s, 1, {BUCKET})\n"
        "jax.block_until_ready(f())\n"
        "t = []\n"
        f"for _ in range({TIMINGS}):\n"
        "    a = time.perf_counter(); jax.block_until_ready(f())\n"
        "    t.append(time.perf_counter() - a)\n"
        "print(json.dumps(statistics.median(t)))\n"
    )
    env = {**os.environ, "XLA_FLAGS": flag}
    finished = subprocess.run(  # noqa: S603 -- this interpreter, fixed code
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env=env,
    )
    if finished.returncode != 0:
        return {"flag": flag, "barriers": barriers, "failed": finished.stderr[-400:]}
    return {
        "flag": flag,
        "barriers": barriers,
        "seconds": json.loads(finished.stdout.strip().splitlines()[-1]),
    }


def main(argv: list[str] | None = None) -> int:
    """Time the parts and the flags; write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = {
        "jax": jax.__version__,
        "backend": jax.default_backend(),
        "shape": [ROWS, BUCKET],
        "parts_s": _parts(),
        "whole_grid_under_flags": [
            _under_flag("", barriers=False),
            *(_under_flag(flag) for flag in FLAGS),
        ],
    }
    text = json.dumps(summary, indent=2)
    args.report.write_text(text + "\n", encoding="utf-8")
    print(text)  # noqa: T201 -- the report is the output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
