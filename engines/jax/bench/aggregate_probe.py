# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An aggregated level-4 run on whatever device JAX has: time, memory, agreement.

Reducing on the card is what turns the card's calculation speed into
an answer at a large book: the totals come back and the per-policy rows never
do. This probe measures that, as information, like the other probes here.

**Sizes** -- one and ten million policies by default, each in a fresh
interpreter so that its peak memory is its own. Level 4's committed artifact
over its book tiled to that many policies, folded by ``JaxEngine.aggregate``
into ``Sum("pv_net_cf")`` and ``PeriodSum("net_cf")``. Recorded per size: the
wall of the fold, the process's peak resident set, the device's peak bytes in
use where the backend reports it, the batch the engine took and its batching
note -- or, where a size did not fit, what stopped it.

**Agreement at ten thousand** -- the same two aggregators folded by Polars
(``run_aggregated`` with no engine, on the tutorial model in the tree), by the
engine on the committed artifact, and by ``run_aggregated(engine="jax")``. The
ratio printed is each total's largest difference from Polars' over that
total's own largest magnitude, which is the agreement rule's reduced scale: a
total inside 1e-12 of it agrees under any larger scale the column's values
would supply.

**What a size costs is a batch or two, not the book.** The fold is fed the
plan's own stream, which hands each batch over as it finishes and lets it go
-- on a card with the next batch already computing -- and
each batch's program returns only the columns folded and its checks'
counts. So a size's peak is at most two batches of those beside the
accumulators, and the book's size moves the time and not the peak.
``--batch`` pins the batch where the budget would otherwise size it.

**Four ways of folding each size, with ``--variants``.** On a card
the engine dispatches a batch ahead, so the host settles the next batch while
the card computes this one; on the CPU it runs each batch after the one
before it. Either way each batch's program returns only the columns folded.
The bench can choose both, and nothing else can: ``depth`` 0 or 1, and
``folded_only=False`` to return every final-schema column. So one run gives the
before and the after on one machine -- depth 0 and 1, each returning every
column and only the folded ones -- each in a fresh interpreter, so each
device peak is its own. Before them, each kind of program is compiled once
over a book of the same batch shapes (``warm_up``), so that no variant pays
a compiler the others load from the persistent cache.

**Where a fold's time went.** Per row: the fold itself (``fold_s``); the loop
over the batches (``loop_s``), which is what dispatching a batch ahead moves;
the inputs digest (``digest_s``), which completion takes over the whole book
and whose encoder is the Rust core's -- so the fold is reported with it and
without it (``without_digest_s``); and the host's own seconds in each stage of
the loop (``host_s``): settling, finding programs, dispatching, reading back,
queuing the partials beside a program, and folding. Reading back is where the
host waits for the card, and the stages' sum against ``loop_s`` is how much of
the loop the host spent doing anything at all.

**Every size is a row, whatever happened to it.** ``measured``, or
``out-of-memory`` (the device refused an allocation, or the operating system
killed the interpreter), ``timeout`` or ``failed``, each with what was said.
The report is rewritten after every size and after the agreement, so a
runner that dies part way still leaves every row it reached.

Usage, from ``engines/jax``::

    .venv/bin/python -m bench.aggregate_probe --report aggregate.json
    .venv/bin/python -m bench.aggregate_probe --sizes 100000 --agree-at 1000
    .venv/bin/python -m bench.aggregate_probe --variants --sizes 1000000
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import resource
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jax
import numpy as np
import polars as pl

from bench.test_scaling import MODELS_DIR, _artifact, _device_peak_mb, _tiled

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from gaspatchio import ActuarialFrame

PROJECT = Path(__file__).resolve().parents[1]
TUTORIAL = (
    PROJECT.parents[1]
    / "bindings/python/gaspatchio/tutorials/level-4-lifelib/base/model.py"
)
SIZES = (1_000_000, 10_000_000)
AGREE_AT = 10_000
# The agreement band: 1e-12 of a line's scale (specification section 11.1.12).
BAND = 1e-12
# How long one size may take before it is recorded as a timeout, in seconds.
TIMEOUT_S = 7200

# What a device or an interpreter says when it has run out of memory, as
# XLA, NumPy and Python each spell it.
_OUT_OF_MEMORY = ("resource_exhausted", "out of memory", "memoryerror")

# The four ways --variants folds each size, as (depth, folded_only): the fold
# with no batch dispatched ahead and every column returned first, and a card's
# own last (the CPU's own is the third, one batch at a time returning the
# columns folded).
VARIANTS: tuple[tuple[int, bool], ...] = (
    (0, False),
    (1, False),
    (0, True),
    (1, True),
)

# The stages the loop's host time is split into: where each is looked up,
# its name there, and what the report calls it.
_STAGES: tuple[tuple[str, str, str], ...] = (
    ("plan", "stage_settle", "settle"),
    ("plan", "_program_for", "program"),
    ("plan", "stage_dispatch", "dispatch"),
    ("plan", "stage_finish", "read_back"),
    ("aggregate", "queued_beside", "queue"),
    ("aggregate", "fold_batch_on_the_device", "fold"),
)


def _aggregations() -> list[Any]:
    """Return the two aggregators the probe folds: a total and a term structure."""
    from gaspatchio.scenarios import PeriodSum, Sum

    return [Sum("pv_net_cf").alias("bel"), PeriodSum("net_cf").alias("net_cf")]


def _device() -> dict[str, Any]:
    """Return what JAX is running on."""
    return {
        "backend": jax.default_backend(),
        "devices": [f"{one.platform}:{one.device_kind}" for one in jax.devices()],
        "jax": jax.__version__,
    }


def _peak_rss_mb() -> float:
    """Return this process's peak resident set, in megabytes, on either platform."""
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports kilobytes and macOS bytes.
    return peak / 1024**2 if platform.system() == "Darwin" else peak / 1024


@contextmanager
def _timed() -> Iterator[dict[str, float]]:
    """Add up the seconds the fold spends in its loop, its stages and its digest.

    Each is wrapped where the fold looks it up and put back afterwards, so
    what is measured is the engine's own code path; a stage called inside
    another -- a settlement inside the first sizing of a group -- is counted
    once, under its own name.
    """
    from gaspatchio_jax import aggregate as aggregate_module
    from gaspatchio_jax import plan as plan_module

    owners = {"plan": plan_module.ExecutionPlan, "aggregate": aggregate_module}
    spent: dict[str, float] = {}
    standing: list[tuple[object, str, object]] = []

    def wrap(owner: object, name: str, label: str) -> None:
        running = getattr(owner, name)
        spent[label] = 0.0

        def timed(*arguments: Any, **named: Any) -> Any:  # noqa: ANN401 -- passed through
            at = time.perf_counter()
            try:
                return running(*arguments, **named)
            finally:
                spent[label] += time.perf_counter() - at

        standing.append((owner, name, running))
        setattr(owner, name, timed)

    wrap(aggregate_module, "folded", "loop")
    wrap(plan_module, "digest_of_inputs", "digest")
    for owner, name, label in _STAGES:
        wrap(owners[owner], name, label)
    try:
        yield spent
    finally:
        for owner, name, running in reversed(standing):
            setattr(owner, name, running)


def _variant(depth: int, *, folded_only: bool) -> str:
    """Return how the report names one way of folding."""
    return f"depth {depth}, {'folded columns' if folded_only else 'every column'}"


def one_size(
    policies: int,
    batch: int | None = None,
    depth: int | None = None,
    *,
    folded_only: bool = True,
) -> dict[str, Any]:
    """Fold level 4 tiled to ``policies`` and return what it cost.

    ``batch`` pins the batch size; ``None`` lets the engine read it off the
    compiled program's temporaries, as a run does. ``depth`` and
    ``folded_only`` are the engine's own choices by default, and the other
    variants' where ``--variants`` asks for them.
    """
    # Imported here, in the interpreter that measures: importing it turns x64
    # on and configures the compile cache, which is part of what a size costs.
    from gaspatchio_jax import aggregate as aggregate_module
    from gaspatchio_jax.plan import depth_on

    depth = depth_on(jax.default_backend()) if depth is None else depth
    document = _artifact("level-4")
    shape = {
        "policies": policies,
        "depth": depth,
        "returns": "folded columns" if folded_only else "every column",
    }
    started = time.perf_counter()
    try:
        book = _tiled(pl.read_parquet(MODELS_DIR / "level-4.book.parquet"), policies)
        tiled = time.perf_counter()
        with _timed() as spent:
            result = aggregate_module.aggregate(
                document,
                book,
                _aggregations(),
                batch=batch,
                depth=depth,
                folded_only=folded_only,
            )
        fold_s = time.perf_counter() - tiled
    except Exception as error:  # noqa: BLE001 -- a size that did not fit is a row
        said = f"{type(error).__name__}: {str(error)[:2000]}"
        return {
            **shape,
            "outcome": _outcome(said),
            "error": said,
            "seconds": round(time.perf_counter() - started, 3),
            "peak_rss_mb": round(_peak_rss_mb(), 1),
            "device_peak_mb": _device_peak_mb(),
        }
    seconds = time.perf_counter() - started
    notes = result.produced_by.notes if result.produced_by is not None else ()
    return {
        **shape,
        "outcome": "measured",
        "seconds": round(seconds, 3),
        "fold_s": round(fold_s, 3),
        "loop_s": round(spent["loop"], 3),
        "digest_s": round(spent["digest"], 3),
        "without_digest_s": round(fold_s - spent["digest"], 3),
        "host_s": {label: round(spent[label], 3) for _o, _n, label in _STAGES},
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "device_peak_mb": _device_peak_mb(),
        "batch_size": result.batch_size,
        "n_periods": result.n_periods,
        "bel": result.bel,
        "batching": [note for note in notes if note.startswith("batching:")],
        "compilations": [note for note in notes if note.startswith("compile cache:")],
    }


def _outcome(said: str) -> str:
    """Return whether what a size said is a memory ceiling or another failure."""
    lowered = said.lower()
    return (
        "out-of-memory" if any(sign in lowered for sign in _OUT_OF_MEMORY) else "failed"
    )


def _in_a_fresh_interpreter(
    policies: int,
    timeout_s: int,
    batch: int | None,
    depth: int | None = None,
    *,
    folded_only: bool = True,
) -> dict[str, Any]:
    """Run one size in its own process, so its peak memory is its own.

    Whatever becomes of the process is a row: a size that ran out of time,
    one the operating system killed -- which on a runner is its out-of-memory
    killer -- and one that failed some other way are each recorded as such,
    with what the process said, rather than taking the report down with them.
    """
    shape: dict[str, Any] = {"policies": policies}
    if depth is not None:
        shape |= {
            "depth": depth,
            "returns": "folded columns" if folded_only else "every column",
        }
    started = time.perf_counter()
    try:
        finished = subprocess.run(  # noqa: S603 -- this interpreter and this module
            [
                sys.executable,
                "-m",
                "bench.aggregate_probe",
                "--one",
                str(policies),
                *(() if batch is None else ("--batch", str(batch))),
                *(() if depth is None else ("--depth", str(depth))),
                *(() if folded_only else ("--every-column",)),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {
            **shape,
            "outcome": "timeout",
            "error": f"no answer within {timeout_s} s",
            "seconds": round(time.perf_counter() - started, 3),
        }
    lines = [line for line in finished.stdout.splitlines() if line.startswith("{")]
    if finished.returncode == 0 and lines:
        read: dict[str, Any] = json.loads(lines[-1])
        return read
    said = f"exit {finished.returncode}: {finished.stderr[-2000:]}"
    return {
        **shape,
        "outcome": "out-of-memory" if finished.returncode < 0 else _outcome(said),
        "error": said,
        "seconds": round(time.perf_counter() - started, 3),
    }


def _warmed(size: int, timeout_s: int, batch: int | None) -> list[dict[str, Any]]:
    """Compile each kind of program a size's variants run, before any is measured.

    A book of one full batch and the size's own last batch compiles exactly
    the programs the size runs -- the batch shapes are what they are keyed
    by -- so the variants that follow all load them from the persistent
    cache, and a comparison between two of them is not a comparison between
    a compiler and a file read.
    """
    from gaspatchio_jax.batching import BATCH_GRID

    width = batch or BATCH_GRID[-1]
    warm = min(size, width + size % width)
    return [
        _in_a_fresh_interpreter(warm, timeout_s, batch, 1, folded_only=folded_only)
        for folded_only in (False, True)
    ]


def _compared(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return each size's variants side by side, the figures dispatching ahead moves.

    The whole fold, the fold without the inputs digest, the loop alone, the
    host's reading back -- where it waits for the card -- and the device
    peak, per way of folding.
    """
    compared: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("outcome") != "measured" or "depth" not in row:
            continue
        folded_only = row["returns"] == "folded columns"
        compared.setdefault(str(row["policies"]), {})[
            _variant(row["depth"], folded_only=folded_only)
        ] = {
            "fold_s": row["fold_s"],
            "without_digest_s": row["without_digest_s"],
            "loop_s": row["loop_s"],
            "read_back_s": row["host_s"]["read_back"],
            "device_peak_mb": row["device_peak_mb"],
            "peak_rss_mb": row["peak_rss_mb"],
        }
    return compared


def _tutorial() -> Callable[[ActuarialFrame], ActuarialFrame]:
    """Return the tree's level-4 tutorial model with its assumptions loaded once."""
    spec = importlib.util.spec_from_file_location("aggregate_probe_level_4", TUTORIAL)
    if spec is None or spec.loader is None:
        message = f"the level-4 tutorial is not at {TUTORIAL}"
        raise RuntimeError(message)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assumptions = module.load_assumptions()

    def model_fn(af: ActuarialFrame) -> ActuarialFrame:
        return module.main(af, assumptions_override=assumptions)  # type: ignore[no-any-return]

    return model_fn


def _reduced_ratio(expected: object, got: object) -> float:
    """Return the largest difference over the total's own largest magnitude."""
    a = np.asarray(expected, dtype=np.float64)
    b = np.asarray(got, dtype=np.float64)
    if a.shape != b.shape:
        return float("inf")
    difference = float(np.max(np.abs(a - b))) if a.size else 0.0
    scale = max(float(np.max(np.abs(a))), float(np.max(np.abs(b)))) if a.size else 0.0
    if difference == 0.0:
        return 0.0
    return difference / scale if scale else float("inf")


def agreement(policies: int) -> dict[str, Any]:
    """Fold ``policies`` of level 4 by Polars and by both engine doors, and compare."""
    from gaspatchio.scenarios import run_aggregated
    from gaspatchio_jax.engine import JaxEngine

    book = _tiled(pl.read_parquet(MODELS_DIR / "level-4.book.parquet"), policies)
    model_fn = _tutorial()
    started = time.perf_counter()
    polars = run_aggregated(model_fn, book, _aggregations(), batch_size=book.height)
    polars_s = time.perf_counter() - started
    started = time.perf_counter()
    engine = JaxEngine().aggregate(_artifact("level-4"), book, _aggregations())
    engine_s = time.perf_counter() - started
    door = run_aggregated(model_fn, book, _aggregations(), engine="jax")
    ratios = {
        f"{side}:{alias}": _reduced_ratio(
            polars.aggregations[alias], answer.aggregations[alias]
        )
        for side, answer in (("engine", engine), ("door", door))
        for alias in polars.aggregations
    }
    worst = max(ratios.values())
    return {
        "policies": policies,
        "ratios": ratios,
        "worst_ratio": worst,
        "verdict": "agree" if worst < BAND else "indeterminate at the reduced scale",
        "seconds": {"polars": round(polars_s, 3), "engine": round(engine_s, 3)},
    }


def _agreement_or_why(policies: int) -> dict[str, Any]:
    """Return the agreement, or what stopped it, as the report's last section."""
    try:
        return agreement(policies)
    except Exception as error:  # noqa: BLE001 -- a failed comparison is still a finding
        return {
            "policies": policies,
            "outcome": "failed",
            "error": f"{type(error).__name__}: {str(error)[:2000]}",
        }


def _written(report: Path | None, summary: dict[str, Any]) -> None:
    """Write the report as it stands, whole, beside the destination and renamed."""
    if report is None:
        return
    working = report.with_name(f"{report.name}.unpublished")
    working.write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    working.replace(report)


def main(argv: Sequence[str] | None = None) -> int:
    """Measure every size, then the agreement; write the report after each step."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--sizes",
        default=",".join(str(size) for size in SIZES),
        help="comma-separated policy counts, each folded in a fresh interpreter",
    )
    parser.add_argument("--agree-at", type=int, default=AGREE_AT)
    parser.add_argument(
        "--timeout", type=int, default=TIMEOUT_S, help="seconds one size may take"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="pin the batch size; by default the engine sizes it",
    )
    parser.add_argument(
        "--variants",
        action="store_true",
        help=(
            "fold each size four ways -- depth 0 and 1, returning every column "
            "and only the folded ones -- each in a fresh interpreter"
        ),
    )
    parser.add_argument("--one", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--depth", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--every-column", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.one is not None:
        measured = one_size(
            args.one, args.batch, args.depth, folded_only=not args.every_column
        )
        print(json.dumps(measured))  # noqa: T201 -- the parent reads it
        return 0

    import gaspatchio_jax  # noqa: F401 -- turns x64 on before the device is read

    sizes = [int(size) for size in str(args.sizes).split(",") if size.strip()]
    summary: dict[str, Any] = {
        "device": _device(),
        "sizes": [],
        "compared": {},
        "warm_up": [],
        "agreement": None,
        "note": "information only; a T4 runs float64 at about a thirty-second rate",
    }
    _written(args.report, summary)
    for size in sizes:
        if args.variants:
            summary["warm_up"].extend(_warmed(size, args.timeout, args.batch))
            _written(args.report, summary)
        for depth, folded_only in VARIANTS if args.variants else ((None, True),):
            summary["sizes"].append(
                _in_a_fresh_interpreter(
                    size, args.timeout, args.batch, depth, folded_only=folded_only
                )
            )
            summary["compared"] = _compared(summary["sizes"])
            _written(args.report, summary)
    if args.agree_at > 0:
        summary["agreement"] = _agreement_or_why(args.agree_at)
        _written(args.report, summary)
    print(json.dumps(summary, indent=2, default=str))  # noqa: T201 -- the report is the output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
