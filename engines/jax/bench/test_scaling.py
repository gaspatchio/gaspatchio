# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What this engine costs, measured, on the machine it is meant to run on.

One test, and what it produces is a file rather than a pass: ``bench/
scaling-<sha>.md``, with the environment and the build's own digests in its
header so a reader can place every number in it. It runs behind the
``benchmark`` marker because it takes minutes, and because a number measured
on a laptop that is also compiling something else is a number about the
laptop.

**What is measured, and why each of them separately.** A compiled engine has
four different costs and reporting one of them is reporting none:

* the **cold compile**, which a reader pays once per shape and never again;
* the **cached compile**, which is what the second run of the morning pays;
* the **warm time per batch**, which is the projection itself and the only
  one that scales with the book;
* the **wall**, end to end, which is what an actuary actually waits for --
  pre-flight, the axis, every batch, putting the columns back in the book's
  order, and the Parquet write.

Peak memory is reported the same way: what the run costs before a batch has
run at all, and the kernel's high-water mark for the whole of it, each row in
a process of its own -- because what the batches add on top is what batching
and streaming exist to bound, and a reading taken after a run has finished
is taken with no batch alive.

**The engine's own loop, one batch ahead and one at a time.** Each
region-only size is run twice more through ``stage_batches`` itself -- every
batch settled, dispatched, read back and dropped -- at depth 0, each batch
strictly after the one before it and the CPU's own, and at depth 1, a card's
own, where the host settles the next batch while the card computes this one.
Their wall against each other is what the overlap is worth on the machine,
the host's seconds in each stage say where the rest went, and the device's
peak says what holding two batches' answers at once costs a card.

**Polars beside, through its own command.** ``gspio run-model`` in the core
venv, on the tutorial the artifact was exported from, over the same book --
so the comparison is two engines over one model and not this engine against
a recollection.
"""

from __future__ import annotations

import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
import psutil
import pytest

from gaspatchio.engines.protocol import ParquetSink
from gaspatchio_jax import cache
from gaspatchio_jax.batching import bytes_per_policy
from gaspatchio_jax.plan import ExecutionPlan
from tests.conftest import LOADER_ENVIRONMENT, PROJECT
from tests.models.export import MODELS

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from numpy.typing import ArrayLike

    from gaspatchio.engines.protocol import ArrowStreamExportable
    from gaspatchio_jax.plan import Prepared, Program, Settled

MODELS_DIR = PROJECT / "tests/models"
CORE = PROJECT.parents[1] / "bindings/python"
CORE_GSPIO = CORE / ".venv/bin/gspio"
TUTORIALS = Path("gaspatchio/tutorials")
BOOK = "model_points_1k.parquet"

# The book sizes. Two are run whole, through publication; the two large ones
# are measured for the region pass alone. Not because they could not be
# published -- the engine writes each batch away as it finishes, and a million
# level-4 policies publish on this laptop -- but because the region pass is the
# projection's own cost, and at those sizes a whole run is mostly building and
# writing columns, which the whole rows already measure. The README carries a
# whole million-policy run. GASPATCHIO_SCALING_REGION_ONLY replaces the
# region-only sizes, comma separated, for a machine that can go further -- a
# GPU runner, say.
SIZES: tuple[int, ...] = (1_000, 10_000)
REGION_ONLY: tuple[int, ...] = tuple(
    int(size)
    for size in os.environ.get(
        "GASPATCHIO_SCALING_REGION_ONLY", "100000,1000000"
    ).split(",")
)

# How many times a warm batch is timed. Five, and the median reported: a
# laptop's first call after a compile is not its steady state and its slowest
# is somebody's mail arriving.
WARM_RUNS = 5

# How many times that whole median-of-five is taken, to find out what the
# warm figure's own spread is. Every conclusion drawn from a difference
# between two warm figures is a conclusion about this number first, so it is
# measured here rather than recalled from another run.
NOISE_RUNS = 7

# The size both compilation figures are taken at: one width on the batch
# grid, in two fresh interpreters over an empty cache directory.
COMPILE_AT = 4_096


@dataclass
class Row:
    """One measured run, as the report's table carries it."""

    model: str
    policies: int
    batches: int
    batch: int
    compilations: int
    buckets: str
    per_policy: int
    prepare_s: float
    warm_batch_s: float
    wall_s: float
    rss_fixed_mb: float
    rss_peak_mb: float
    polars_s: float | str = "not attempted"
    note: str = ""
    # Where a region pass's wall went, summed over its batches: settling each
    # batch on the host, finding its compiled program, the program itself, and
    # the bench's own bookkeeping (the memory reading per batch). Only the
    # region-only rows carry it; the whole runs publish, and their wall is
    # the door as well.
    split: dict[str, float] | None = None


@dataclass
class Overlapped:
    """One region-only size run through the engine's own loop, at one depth.

    Attributes:
        model: Which model.
        policies: How many policies.
        depth: How many batches were dispatched ahead of the one read back.
        batches: How many batches the loop ran.
        wall_s: The loop's own wall, from the first settlement to the last
            batch handed over.
        split: The host's seconds in each stage of it: settling a batch,
            finding its program, dispatching it, and reading it back -- the
            last is where the host waits for the card.
        rss_peak_mb: The row's own high-water mark, in a process of its own.
        device_peak_mb: The device's own high-water mark over the row, where
            its backend reports one; None on the CPU. One batch ahead, two
            batches' answers are on the card at once, and the batch budget
            counts one program's temporaries and none of any batch's answers,
            so this is the figure that says what the overlap costs a card.

    """

    model: str
    policies: int
    depth: int
    batches: int
    wall_s: float
    split: dict[str, float]
    rss_peak_mb: float
    device_peak_mb: float | None


@dataclass
class Compilation:
    """What one shape cost to compile, and to load back.

    Its own table and its own row, because both figures are taken at one
    size -- the batch grid's 4,096 -- in two fresh interpreters over a cache
    directory that starts empty. Printed against the sizes of the scaling
    table they would be figures about a shape those rows do not use.
    """

    model: str
    policies: int
    cold_s: float
    cached_s: float


@dataclass
class Report:
    """Everything the file says, gathered before any of it is written."""

    rows: list[Row] = field(default_factory=list)
    overlaps: list[Overlapped] = field(default_factory=list)
    compiles: list[Compilation] = field(default_factory=list)
    scan_cost: dict[str, Any] = field(default_factory=dict)
    noise: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _rss_mb() -> float:
    """Return this process's resident set, in megabytes."""
    return psutil.Process(os.getpid()).memory_info().rss / 1024**2


def _device_peak_mb() -> float | None:
    """Return the device's peak bytes in use, in megabytes, where it reports one.

    The high-water mark since the process started, which is why every row
    that reads it runs in a process of its own.
    """
    import jax

    stats = jax.devices()[0].memory_stats()
    if not stats or "peak_bytes_in_use" not in stats:
        return None
    return float(stats["peak_bytes_in_use"]) / 1024**2


def _peak_mb() -> float:
    """Return this process's high-water mark, in megabytes: the kernel's own.

    ``ru_maxrss`` counts bytes on macOS and kibibytes on Linux.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1024**2 if sys.platform == "darwin" else peak / 1024


def _in_a_fresh_process(call: str, *arguments: str) -> dict[str, Any]:
    """Return what one of this module's rows measures, run in a process of its own.

    Each row in its own interpreter, so the peak it reports is the kernel's
    high-water mark for that row and nothing else. Read in this process it
    would not be: ``ru_maxrss`` never goes down, so every row would carry the
    peak of every row before it; and resident memory read once a run has
    finished is read when no batch is alive, which for a run that streams its
    batches is a fraction of what it held.
    """
    script = (
        "import json, sys\n"
        "from bench import test_scaling\n"
        f"print(json.dumps(test_scaling.{call}(*sys.argv[1:])))\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        one for one in (str(PROJECT), environment.get("PYTHONPATH", "")) if one
    )
    finished = subprocess.run(  # noqa: S603 -- this interpreter, this module
        [sys.executable, "-c", script, *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=7200,
        env=environment,
        cwd=PROJECT,
    )
    if finished.returncode != 0:
        message = f"{call} failed in its own process:\n{finished.stderr[-3000:]}"
        raise RuntimeError(message)
    read: dict[str, Any] = json.loads(finished.stdout.strip().splitlines()[-1])
    return read


def _held_for_a_child(
    document: dict[str, Any], book: pl.DataFrame, out: Path
) -> tuple[Path, Path]:
    """Write one row's artifact and book beside its result, for its process."""
    artifact = out.with_name(f"{out.stem}.artifact.json")
    artifact.write_text(json.dumps(document), encoding="utf-8")
    held = out.with_name(f"{out.stem}.book.parquet")
    book.write_parquet(held)
    return artifact, held


def _tiled(book: pl.DataFrame, policies: int) -> pl.DataFrame:
    """Return the book tiled up to this many policies, with fresh identities."""
    tiles = -(-policies // book.height)
    return (
        pl.concat([book] * tiles, how="vertical")
        .head(policies)
        .with_columns(pl.int_range(1, policies + 1, dtype=pl.Int64).alias("point_id"))
    )


def _artifact(model: str) -> dict[str, Any]:
    read: dict[str, Any] = json.loads(
        (MODELS_DIR / f"{model}.artifact.json").read_text(encoding="utf-8")
    )
    return read


def _settled_batches(
    plan: ExecutionPlan, prepared: Prepared, batch: int | None
) -> Iterator[tuple[Settled, Program]]:
    """Return each batch settled and its program, without keeping any answers."""
    from gaspatchio_jax.batching import chunks, grouped

    for group in grouped(prepared.widths, prepared.inputs.rows):
        size = batch or plan._batch_for(prepared, group, 2 * 1024**3)[0]  # noqa: SLF001
        for rows in chunks(group, size):
            settled = plan.stage_settle(prepared, rows)
            yield settled, plan._program_for(settled)[0]  # noqa: SLF001


# What one fresh process measures: a shape compiled with nothing in the cache
# directory, and the same shape again with the first run's entry in it. Two
# processes, because XLA reads the cache directory when it first compiles and
# never again -- so a cold and a warm figure cannot both be taken here.
_COMPILE_ONCE = """
import json, time

import numpy as np

import gaspatchio_jax
from gaspatchio_jax.plan import ExecutionPlan

import polars as pl

document = json.loads(open({artifact!r}).read())
book = pl.read_parquet({book!r})
plan = ExecutionPlan.stage_inspect(document)
prepared = plan.stage_prepare(plan.stage_validate_inputs(book))
rows = np.arange(book.height)
settled = plan.stage_settle(prepared, rows)
started = time.perf_counter()
program, outcome = plan.compile_for(settled)
print(json.dumps({{
    "seconds": outcome.compile_seconds,
    "wall": time.perf_counter() - started,
    "persistent": outcome.persistent,
}}))
"""


def _compilations(
    model: str, document: dict[str, Any], book: pl.DataFrame, where: Path
) -> tuple[float, float]:
    """Return what one shape costs compiled cold, and loaded from the cache.

    Two fresh interpreters over a cache directory that starts empty. The
    first pays the compiler; the second pays a file read, and the difference
    between the two is the whole reason the persistent cache is turned on at
    import.
    """
    at = where / f"{model}-compile"
    at.mkdir(parents=True, exist_ok=True)
    (at / "book.parquet").write_bytes(b"")
    book.write_parquet(at / "book.parquet")
    (at / "artifact.json").write_text(json.dumps(document), encoding="utf-8")
    script = at / "once.py"
    script.write_text(
        _COMPILE_ONCE.format(
            artifact=str(at / "artifact.json"), book=str(at / "book.parquet")
        ),
        encoding="utf-8",
    )
    read: list[dict[str, Any]] = []
    for _run in range(2):
        finished = subprocess.run(  # noqa: S603 -- this project's own venv
            [str(PROJECT / ".venv/bin/python"), str(script)],
            capture_output=True,
            text=True,
            check=False,
            timeout=1800,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(at),
                "JAX_COMPILATION_CACHE_DIR": str(at / "cache"),
                # This tree's engine, ahead of wherever the venv's editable
                # install points: a worktree's venv can point at another tree.
                "PYTHONPATH": os.pathsep.join([str(PROJECT / "src"), str(PROJECT)]),
                **LOADER_ENVIRONMENT,
            },
        )
        if finished.returncode != 0:
            # Printed rather than swallowed: a zero in the table with no
            # reason beside it reads as a compile that cost nothing.
            print(  # noqa: T201 -- the bench's output is read by a person
                f"{model}: the compile measurement failed\n{finished.stderr[-2000:]}"
            )
            return (0.0, 0.0)
        read.append(json.loads(finished.stdout.strip().splitlines()[-1]))
    return (read[0]["seconds"], read[1]["seconds"])


def _timed_warm(program: Program, settled: Settled) -> float:
    """Return the median wall time of one compiled batch, warm."""
    from gaspatchio_jax.plan import _axes_in

    arrays = tuple(settled.values[name].array for name in program.names)
    counts = tuple(axis.t for axis in _axes_in(settled.values))
    took: list[float] = []
    for _run in range(WARM_RUNS):
        started = time.perf_counter()
        answered = program.compiled(arrays, counts)
        for one in answered[0].values():
            one.block_until_ready()
        took.append(time.perf_counter() - started)
    return statistics.median(took)


def _one_run(
    model: str,
    document: dict[str, Any],
    book: pl.DataFrame,
    out: Path,
) -> Row:
    """Return every figure one book of one model produces.

    The warm batch is timed here; the whole run, through publication, in a
    process of its own (see :func:`_in_a_fresh_process`), which is where its
    memory figures come from.
    """
    started = time.perf_counter()
    plan = ExecutionPlan.stage_inspect(document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(book))
    prepare_s = time.perf_counter() - started

    settled, program = next(iter(_settled_batches(plan, prepared, None)))
    warm = _timed_warm(program, settled)
    per_policy = bytes_per_policy(program.compiled, max(settled.count, 1))

    artifact, held = _held_for_a_child(document, book, out)
    whole = _in_a_fresh_process("whole_run", str(artifact), str(held), str(out))
    sizes: list[int] = whole["sizes"]
    return Row(
        model=model,
        policies=book.height,
        batches=len(sizes),
        batch=max(sizes) if sizes else 0,
        compilations=whole["compilations"],
        buckets=whole["buckets"],
        per_policy=per_policy,
        prepare_s=prepare_s,
        warm_batch_s=warm,
        wall_s=whole["wall_s"],
        rss_fixed_mb=whole["rss_fixed_mb"],
        rss_peak_mb=whole["rss_peak_mb"],
    )


def whole_run(artifact: str, book: str, out: str) -> dict[str, Any]:
    """Run one book through the file door, whole, and say what it cost.

    The body of one whole row, called in a process of its own: the peak it
    reports is this run's and no other's. The wall runs from reading the
    document to the rename into place.
    """
    document = json.loads(Path(artifact).read_text(encoding="utf-8"))
    frame = pl.read_parquet(book)
    started = time.perf_counter()
    whole = ExecutionPlan.stage_inspect(document)
    prepared = whole.stage_prepare(whole.stage_validate_inputs(frame))
    fixed = _rss_mb()
    sink = _Counted(Path(out))
    streamed = whole.stage_stream(prepared, sink)
    whole.stage_complete(streamed, sink, prepared)
    return {
        "wall_s": time.perf_counter() - started,
        "sizes": sink.sizes,
        "compilations": len(whole.programs),
        "buckets": _widths(whole),
        "rss_fixed_mb": fixed,
        "rss_peak_mb": _peak_mb(),
    }


class _Counted(ParquetSink):
    """The file door's sink, remembering how many policies each batch held."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.sizes: list[int] = []

    def write_batch(
        self, frame: ArrowStreamExportable, *, rows: ArrayLike | None = None
    ) -> None:
        super().write_batch(frame, rows=rows)
        self.sizes.append(int(np.asarray(rows).size))


def _region_only(
    model: str, document: dict[str, Any], book: pl.DataFrame, where: Path
) -> Row:
    """Return what the region pass alone costs, with nothing kept.

    Every batch computed and dropped: the projection's own cost, with no
    columns built and nothing published, and honest about what it leaves
    out. A whole run at these sizes publishes too -- the engine writes each
    batch away as it finishes -- but it is mostly building and writing
    columns, which the whole rows measure. Run in a process of its own, for
    the peak's sake (see :func:`_in_a_fresh_process`).
    """
    artifact, held = _held_for_a_child(
        document, book, where / f"{model}-{book.height}-region.parquet"
    )
    return Row(**_in_a_fresh_process("region_pass", model, str(artifact), str(held)))


def region_pass(model: str, artifact: str, book: str) -> dict[str, Any]:
    """Return one region-only row's figures, measured in the calling process.

    The body of :func:`_region_only`, called in a process of its own.
    """
    document = json.loads(Path(artifact).read_text(encoding="utf-8"))
    return asdict(_region_pass(model, document, pl.read_parquet(book)))


def _region_pass(model: str, document: dict[str, Any], book: pl.DataFrame) -> Row:
    """Return what the region pass alone costs, measured here."""
    started = time.perf_counter()
    plan = ExecutionPlan.stage_inspect(document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(book))
    prepare_s = time.perf_counter() - started
    fixed = _rss_mb()
    warm: list[float] = []
    per_policy = 0
    at = time.perf_counter()
    sizes: list[int] = []
    from gaspatchio_jax.batching import chunks, grouped

    split = {"settle": 0.0, "program": 0.0, "compute": 0.0, "bookkeeping": 0.0}
    for group in grouped(prepared.widths, prepared.inputs.rows):
        size = plan._batch_for(prepared, group, 2 * 1024**3)[0]  # noqa: SLF001
        for rows in chunks(group, size):
            taken = time.perf_counter()
            settled = plan.stage_settle(prepared, rows)
            split["settle"] += time.perf_counter() - taken
            taken = time.perf_counter()
            program = plan._program_for(settled)[0]  # noqa: SLF001
            split["program"] += time.perf_counter() - taken
            taken = time.perf_counter()
            answered = program.compiled(
                tuple(settled.values[name].array for name in program.names),
                tuple(axis.t for axis in _axes(settled)),
            )
            for one in answered[0].values():
                one.block_until_ready()
            warm.append(time.perf_counter() - taken)
            split["compute"] += warm[-1]
            sizes.append(settled.count)
            taken = time.perf_counter()
            per_policy = bytes_per_policy(program.compiled, max(settled.count, 1))
            split["bookkeeping"] += time.perf_counter() - taken
    return Row(
        model=model,
        policies=book.height,
        batches=len(warm),
        batch=max(sizes) if sizes else 0,
        compilations=len(plan.programs),
        buckets=_widths(plan),
        per_policy=per_policy,
        prepare_s=prepare_s,
        warm_batch_s=statistics.median(warm) if warm else 0.0,
        wall_s=time.perf_counter() - at,
        rss_fixed_mb=fixed,
        rss_peak_mb=_peak_mb(),
        note="region pass only; nothing published",
        split=split,
    )


def _overlapped(
    model: str, document: dict[str, Any], book: pl.DataFrame, where: Path
) -> list[Overlapped]:
    """Return one size run through the engine's own loop at depth 0 and at 1.

    Each in a process of its own, for the peak's sake, and after the region
    pass above it has compiled the size's programs into the persistent
    cache, so neither depth pays a compiler the other does not.
    """
    artifact, held = _held_for_a_child(
        document, book, where / f"{model}-{book.height}-overlap.parquet"
    )
    return [
        Overlapped(
            **_in_a_fresh_process(
                "overlapped", model, str(artifact), str(held), str(depth)
            )
        )
        for depth in (0, 1)
    ]


def overlapped(model: str, artifact: str, book: str, depth: str) -> dict[str, Any]:
    """Return one size's figures through the engine's own loop, measured here.

    Every batch settled, dispatched, read back and dropped, at one depth; the
    body of :func:`_overlapped`, called in a process of its own.
    """
    from gaspatchio_jax import plan as plan_module

    document = json.loads(Path(artifact).read_text(encoding="utf-8"))
    frame = pl.read_parquet(book)
    plan = ExecutionPlan.stage_inspect(document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(frame))
    split = {"settle": 0.0, "program": 0.0, "dispatch": 0.0, "read_back": 0.0}
    staged = {
        "stage_settle": "settle",
        "_program_for": "program",
        "stage_dispatch": "dispatch",
        "stage_finish": "read_back",
    }
    standing = {name: getattr(plan_module.ExecutionPlan, name) for name in staged}

    def timed(name: str) -> Any:  # noqa: ANN401 -- a stage of the plan's own
        running = standing[name]

        def one(*arguments: Any, **named: Any) -> Any:  # noqa: ANN401 -- passed through
            at = time.perf_counter()
            try:
                return running(*arguments, **named)
            finally:
                split[staged[name]] += time.perf_counter() - at

        return one

    for name in staged:
        setattr(plan_module.ExecutionPlan, name, timed(name))
    try:
        started = time.perf_counter()
        batches = 0
        for batched in plan.stage_batches(prepared, depth=int(depth)):
            batches += 1
            del batched
        wall = time.perf_counter() - started
    finally:
        for name, running in standing.items():
            setattr(plan_module.ExecutionPlan, name, running)
    return asdict(
        Overlapped(
            model=model,
            policies=frame.height,
            depth=int(depth),
            batches=batches,
            wall_s=wall,
            split=split,
            rss_peak_mb=_peak_mb(),
            device_peak_mb=_device_peak_mb(),
        )
    )


def _widths(plan: ExecutionPlan) -> str:
    """Return every width this run compiled a program around, not the first.

    A jagged book meets several, and a column carrying the first batch's
    would say *12* of a book that also ran at 24, 36 and 48.
    """
    found: set[int] = set()
    for program in plan.programs.values():
        found |= set(program.buckets)
    return ",".join(str(one) for one in sorted(found))


def _axes(settled: Settled) -> list[Any]:
    from gaspatchio_jax.plan import _axes_in

    return _axes_in(settled.values)


def _polars_beside(model: str, book: pl.DataFrame, where: Path) -> float | str:
    """Return what Polars takes over the same model and the same book.

    A float where it ran, and the word for what happened where it did not:
    a comparison that was never attempted and one that was attempted and
    failed are two different things to be told, and filing both as "not run"
    would let a broken reference side read as a deliberate omission.
    """
    at = where / f"{model}-polars-book.parquet"
    book.write_parquet(at)
    out = where / f"{model}-polars.parquet"
    started = time.perf_counter()
    finished = subprocess.run(  # noqa: S603 -- the core's own venv and tutorials
        [
            str(CORE_GSPIO),
            "run-model",
            str(CORE / TUTORIALS / MODELS[model] / "base/model.py"),
            str(at),
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=3600,
        cwd=CORE,
    )
    if finished.returncode != 0:
        return "failed"
    return time.perf_counter() - started


def _noise(document: dict[str, Any], book: pl.DataFrame) -> list[float]:
    """Return the warm figure's own spread: one measurement, taken N times.

    Level 4 at ten thousand policies, one warm batch, the median of five --
    the exact quantity the scaling table reports -- repeated. What comes back
    is what "the same measurement" is worth on this machine, and it is the
    band any two warm figures have to differ by before the difference means
    anything.

    **Each reading is taken the way the scan comparison takes its own**: a
    fresh plan, a fresh settled batch and a freshly compiled program, not the
    same executable timed again. The two are only comparable if they are
    measured alike -- and they are not the same quantity. Timing one
    executable seven times measures the machine; building the program again
    measures what a *run* is worth, which is what that comparison's two
    labels are, and it is wider. A verdict read against the narrower band
    would call a difference significant that a second run of the same label
    reproduces.
    """
    sized = _tiled(book, 10_000)
    taken: list[float] = []
    for _run in range(NOISE_RUNS):
        plan = ExecutionPlan.stage_inspect(document)
        prepared = plan.stage_prepare(plan.stage_validate_inputs(sized))
        settled, program = next(iter(_settled_batches(plan, prepared, None)))
        taken.append(_timed_warm(program, settled))
    return taken


def _scan_cost(document: dict[str, Any], book: pl.DataFrame) -> dict[str, Any]:
    """Return what the sequential scan costs against the library reduction.

    The folds are a sequential ``lax.scan``, so that no shape can change their
    order and an integer total is checked term by term rather than wrapped.
    What that choice costs is this: level 4's own ``sum``, warm, with the scan
    and with ``jnp.sum`` in its place, at two sizes.
    """
    import jax.numpy as jnp

    from gaspatchio_jax.lowerings import reduction

    standing = reduction._fold  # noqa: SLF001

    def library(name: str, value: Any, *, reverse: bool = False) -> Any:  # noqa: ANN401
        if name != "sum" or reverse:
            return standing(name, value, reverse=reverse)
        from gaspatchio_jax.horizon import mask_to_neutral, periods_of

        masked = mask_to_neutral(value, periods_of(value), 0.0)
        return jnp.sum(masked.array, axis=1), jnp.cumsum(masked.array, axis=1)

    read: dict[str, Any] = {}
    for policies in (1_000, 10_000):
        sized = _tiled(book, policies)
        for label, folded in (("scan", standing), ("jnp.sum", library)):
            reduction._fold = folded  # type: ignore[assignment]  # noqa: SLF001
            plan = ExecutionPlan.stage_inspect(document)
            prepared = plan.stage_prepare(plan.stage_validate_inputs(sized))
            settled, program = next(iter(_settled_batches(plan, prepared, None)))
            read[f"{label}@{policies}"] = _timed_warm(program, settled)
        reduction._fold = standing  # type: ignore[assignment]  # noqa: SLF001
    return read


def _header(sha: str, *, clean: bool) -> list[str]:
    """Return the lines that let a reader place every number below them."""
    import hashlib

    import jax
    import jaxlib

    from gaspatchio import _internal

    extension = Path(_internal.__file__)
    machine = psutil.virtual_memory()
    return [
        "# The JAX engine, measured",
        "",
        (
            "Measured on the tree that **the commit carrying this file** "
            f"holds, over `{sha}`. The measurement and the code it measures "
            "travel together, which is why this file has no commit in its "
            "name: a name carrying one would point at a tree the code is not "
            "in. Every figure below is one laptop's; what is stable about "
            "them is the ratios and the shapes, not the seconds."
        ),
        "",
        (
            f"- **Over** `{sha}`, tree at HEAD"
            f"{'' if clean else ', with uncommitted changes'}"
        ),
        (
            f"- **Machine** {platform.platform()}, "
            f"{psutil.cpu_count(logical=False)} physical cores, "
            f"{machine.total / 1024**3:.0f} GiB"
        ),
        (
            f"- **Device** {jax.default_backend()}: "
            f"{', '.join(sorted({one.device_kind for one in jax.devices()}))}"
        ),
        f"- **Interpreter** `{_shown(Path(sys.executable))}` {sys.version.split()[0]}",
        (
            f"- **jax** {jax.__version__} / **jaxlib** {jaxlib.__version__} / "
            f"**polars** {pl.__version__} / **numpy** {np.__version__}"
        ),
        (
            f"- **Core extension** `{extension.name}`, sha256 "
            f"`{hashlib.sha256(extension.read_bytes()).hexdigest()}`"
        ),
        f"- **Compilation cache** `{_shown(cache.cache_dir())}`{_which_cache()}",
        "",
    ]


def _shown(path: Path) -> str:
    """Return a path as this file may carry it: never a home directory's.

    Relative to the checkout where it is inside it, and to ``~`` where it is
    under the home directory. The file is checked in, and a path that names
    the maintainer's home resolves on one machine and publishes a name besides.
    """
    checkout = PROJECT.parents[1]
    if path.is_relative_to(checkout):
        return str(path.relative_to(checkout))
    if path.is_relative_to(Path.home()):
        return f"~/{path.relative_to(Path.home())}"
    return str(path)


def _which_cache() -> str:
    """Return whether the cache named is the default one, as the header says it."""
    if "JAX_COMPILATION_CACHE_DIR" in os.environ:
        return " (from JAX_COMPILATION_CACHE_DIR)"
    return " (the default user cache)"


def _clean() -> bool:
    """Return whether the tree measured is the tree a commit would carry.

    Stamped into the header beside the commit it is over, because the two
    together are what place a figure: a reader who can check out the SHA and
    find a different tree needs to be told, and *this* file is written on a
    tree that is about to become a commit rather than one that already is.
    """
    return not subprocess.run(
        ["/usr/bin/git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT,
    ).stdout.strip()


@pytest.mark.benchmark
def test_the_scaling_report(tmp_path: Path) -> None:
    """Measure this engine over three books and two models, and file the table."""
    # The commit this file's own commit will sit on top of, which is the one
    # commit that can be named truthfully now and still be true afterwards.
    # With the measured code not yet committed, that is HEAD: the file lands
    # in the commit that carries the code. With the code committed and this
    # file to be amended into it, it is HEAD's parent.
    clean = _clean()
    sha = subprocess.run(  # noqa: S603 -- git, and one of two fixed revisions
        ["/usr/bin/git", "rev-parse", "--short", "HEAD^" if clean else "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=PROJECT,
    ).stdout.strip()
    report = Report()
    for model in ("level-4", "level-5"):
        document = _artifact(model)
        book = pl.read_parquet(MODELS_DIR / f"{model}.book.parquet")
        cold, cached = _compilations(
            model, document, _tiled(book, COMPILE_AT), tmp_path
        )
        report.compiles.append(
            Compilation(model=model, policies=COMPILE_AT, cold_s=cold, cached_s=cached)
        )
        for policies in SIZES:
            sized = _tiled(book, policies)
            row = _one_run(
                model, document, sized, tmp_path / f"{model}-{policies}.parquet"
            )
            row.polars_s = _polars_beside(model, sized, tmp_path)
            report.rows.append(row)
        for policies in REGION_ONLY:
            sized = _tiled(book, policies)
            report.rows.append(_region_only(model, document, sized, tmp_path))
            report.overlaps.extend(_overlapped(model, document, sized, tmp_path))
    jagged = _jagged(tmp_path)
    if jagged is not None:
        row, compiled = jagged
        report.rows.append(row)
        report.compiles.append(compiled)
    level_4 = _artifact("level-4")
    book_4 = pl.read_parquet(MODELS_DIR / "level-4.book.parquet")
    report.noise = _noise(level_4, book_4)
    report.scan_cost = _scan_cost(level_4, book_4)
    written = PROJECT / "bench" / "scaling.md"
    written.write_text(_rendered(report, sha, clean=clean), encoding="utf-8")
    print(f"written {written}")  # noqa: T201 -- the file is the point of this test
    assert report.rows
    assert report.noise
    assert written.exists()


def _jagged(where: Path) -> tuple[Row, Compilation] | None:
    """Return the jagged term book's row, exported through the core's own gspio."""
    finished = subprocess.run(  # noqa: S603 -- the core's own venv and tutorials
        [
            str(CORE / ".venv/bin/python"),
            "-c",
            (
                f"import sys; sys.path.insert(0, {str(PROJECT)!r})\n"
                "from pathlib import Path\n"
                "from tests.models.export import jagged\n"
                f"print(jagged(Path({str(where / 'jagged')!r}))[0])"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
        cwd=CORE,
    )
    if finished.returncode != 0:
        return None
    artifact = json.loads(
        (where / "jagged/jagged.artifact.json").read_text(encoding="utf-8")
    )
    book = pl.read_parquet(where / "jagged/book.parquet")
    row = _one_run("jagged", artifact, book, where / "jagged.parquet")
    row.note = "terms of one to seven years; four widths in one book"
    cold, cached = _compilations("jagged", artifact, book, where)
    return row, Compilation(
        model="jagged", policies=book.height, cold_s=cold, cached_s=cached
    )


_COLUMNS = (
    ("model", "{0.model}"),
    ("policies", "{0.policies:,}"),
    ("batches", "{0.batches}"),
    ("batch", "{0.batch:,}"),
    ("compiles", "{0.compilations}"),
    ("widths", "{0.buckets}"),
    ("temp B/policy", "{0.per_policy:,}"),
    ("pre-flight s", "{0.prepare_s:.2f}"),
    ("warm batch s", "{0.warm_batch_s:.4f}"),
    ("wall s", "{0.wall_s:.2f}"),
    ("RSS fixed MB", "{0.rss_fixed_mb:.0f}"),
    ("RSS peak MB", "{0.rss_peak_mb:.0f}"),
)

# A ratio inside the warm figure's own spread is a ratio this machine cannot
# tell from one, and the sequential scan stays. Above it the scan's cost is
# material, and bucket invariance may be relaxed from bit-identity to agreement
# within the 1e-12 band.
_INSIDE = "inside the warm figure's own spread"
_ABOVE = "ABOVE the warm figure's own spread"


def _spread(taken: Sequence[float]) -> float:
    """Return how far apart the widest two readings of one measurement were."""
    return (max(taken) - min(taken)) / min(taken) if taken else 0.0


def _rendered(report: Report, sha: str, *, clean: bool) -> str:
    """Return the whole file, header and tables."""
    lines = _header(sha, clean=clean)
    lines += [
        "## Scaling",
        "",
        "| " + " | ".join(name for name, _ in _COLUMNS) + " | Polars s | note |",
        "|" + "---|" * (len(_COLUMNS) + 2),
    ]
    for row in report.rows:
        cells = [spelled.format(row) for _name, spelled in _COLUMNS]
        beside = (
            f"{row.polars_s:.2f}" if isinstance(row.polars_s, float) else row.polars_s
        )
        lines.append("| " + " | ".join([*cells, beside, row.note or ""]) + " |")
    lines += [
        "",
        (
            "A *region pass only* row computes every batch and keeps none: it "
            "measures the projection rather than the door in front of it. A "
            "whole run at those sizes publishes too -- the engine writes each "
            "batch away as it finishes -- but it is mostly building and "
            "writing columns, which the whole rows measure."
        ),
        "",
        (
            "**`RSS peak MB` is the kernel's high-water mark for the row "
            "alone** (`ru_maxrss`): each whole run and each region pass runs "
            "in a process of its own, so no row carries another's peak. "
            "`RSS fixed MB` is that process's resident set once the book is "
            "prepared, before any batch has run."
        ),
        "",
        (
            "**`warm batch s` is the median over every batch of the run, a "
            "tail batch included where the book leaves one.** A row whose "
            "batch count is more than one and whose policies are not a whole "
            "multiple of its batch size therefore averages a full batch with "
            "a shorter one: at 100,000 policies the two batches are 65,536 "
            "and 34,464. The rows that report a full batch's own cost are the "
            "ones where the tail is a sixteenth of the run or less."
        ),
        "",
        "## Inside a region pass",
        "",
        (
            "Where each region-only row's wall went, in seconds summed over its "
            "batches: settling a batch on the host (its inputs, its axis, its "
            "horizons), finding its compiled program, the program itself, and "
            "the bench's own bookkeeping (reading the program's temporaries). "
            "*Other* is the wall less the four."
        ),
        "",
        (
            "| model | policies | settle s | program s | compute s "
            "| bookkeeping s | other s |"
        ),
        "|---|---|---|---|---|---|---|",
        *(
            f"| {row.model} | {row.policies:,} | {row.split['settle']:.2f} | "
            f"{row.split['program']:.2f} | {row.split['compute']:.2f} | "
            f"{row.split['bookkeeping']:.2f} | "
            f"{row.wall_s - sum(row.split.values()):.2f} |"
            for row in report.rows
            if row.split is not None
        ),
        "",
        "## One batch ahead",
        "",
        (
            "Each region-only size again, through the engine's own loop "
            "(`stage_batches`): every batch settled, dispatched, read back and "
            "dropped. At depth 0 each batch runs strictly after the one before "
            "it, as the CPU runs; at depth 1, as a card runs, the host settles "
            "and dispatches the next batch before it reads this one back (item "
            "3). The stage "
            "columns are the host's own seconds in each, summed over the "
            "batches; *read back* is where it waits for the card, and *other* "
            "is the wall less the four. *Device peak* is the card's own "
            "high-water mark over the row: one batch ahead there are two "
            "batches' answers on it at once, which the batch budget -- one "
            "program's temporaries -- does not count. None on the CPU."
        ),
        "",
        (
            "| model | policies | depth | batches | wall s | settle s | "
            "program s | dispatch s | read back s | other s | RSS peak MB "
            "| device peak MB |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
        *(
            f"| {one.model} | {one.policies:,} | {one.depth} | {one.batches} | "
            f"{one.wall_s:.2f} | {one.split['settle']:.2f} | "
            f"{one.split['program']:.2f} | {one.split['dispatch']:.2f} | "
            f"{one.split['read_back']:.2f} | "
            f"{one.wall_s - sum(one.split.values()):.2f} | {one.rss_peak_mb:.0f} | "
            f"{'—' if one.device_peak_mb is None else f'{one.device_peak_mb:.0f}'} |"
            for one in report.overlaps
        ),
        "",
        "## Compilation",
        "",
        (
            "Each figure is taken at the size its own row names — "
            f"{COMPILE_AT:,} policies for the two rectangles, the whole book "
            "for the jagged one — and **each in a fresh interpreter over a "
            "cache directory that starts empty**. They are in a table of "
            "their own because they are figures about one shape, and printing "
            "them against the sizes above would attach them to shapes those "
            "rows do not use."
        ),
        "",
        "| model | policies | cold s | from the cache s | ratio |",
        "|---|---|---|---|---|",
    ]
    for one in report.compiles:
        ratio = one.cold_s / one.cached_s if one.cached_s else 0.0
        lines.append(
            f"| {one.model} | {one.policies:,} | {one.cold_s:.2f} | "
            f"{one.cached_s:.2f} | {ratio:.0f}x |"
        )
    spread = _spread(report.noise)
    lines += [
        "",
        "## What a warm figure is worth",
        "",
        (
            "One measurement — level 4, 10,000 policies, one warm batch, the "
            f"median of {WARM_RUNS} — taken {NOISE_RUNS} times in this run, "
            "**each through a fresh plan, a fresh settled batch and a freshly "
            "compiled program**. Any conclusion drawn from a difference "
            "between two warm figures is a conclusion about this number "
            "first."
        ),
        "",
        "| readings | min s | max s | spread |",
        "|---|---|---|---|",
        (
            f"| {len(report.noise)} | {min(report.noise):.4f} | "
            f"{max(report.noise):.4f} | **{spread * 100:.1f} %** |"
        ),
        "",
        "## The sequential scan's cost",
        "",
        (
            "Level 4's own `sum`, warm, with the sequential `lax.scan` the "
            "folds use and with `jnp.sum` in its place. The verdict column is the "
            "cost against the spread above, and it is read off these numbers "
            "rather than argued."
        ),
        "",
        "| book | scan s | jnp.sum s | cost | verdict |",
        "|---|---|---|---|---|",
    ]
    for policies in (1_000, 10_000):
        scan = report.scan_cost.get(f"scan@{policies}")
        library = report.scan_cost.get(f"jnp.sum@{policies}")
        if scan is None or library is None:
            continue
        cost = scan / library - 1.0
        verdict = _INSIDE if abs(cost) <= spread else _ABOVE
        lines.append(
            f"| {policies:,} | {scan:.4f} | {library:.4f} | "
            f"{cost * 100:+.1f} % | {verdict} |"
        )
    lines += ["", *report.notes, ""]
    return "\n".join(lines) + "\n"
