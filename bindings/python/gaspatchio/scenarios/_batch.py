# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Measured collection shared by bounded scenario, aggregate and disk runners."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Literal

import polars as pl
import polars.selectors as cs

from gaspatchio.errors import _handle_execution_error
from gaspatchio.rollforward import _registry as _rollforward_registry
from gaspatchio.scenarios._auto_batch import process_rss_bytes

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio.frame import ActuarialFrame


def book_in_hand(model_points: object, runner: str) -> pl.DataFrame:
    """Return the model points a policy-axis runner cuts into batches, as a DataFrame.

    A runner slices the book into batches by row and judges a wide integer
    column over the whole of it, so it needs the rows in hand. A book handed
    over as a ``LazyFrame`` -- what ``pl.scan_parquet`` returns -- is
    collected here, at the door, as an ``ActuarialFrame`` collects one for a
    scenario plan; it used to fail inside the runner with ``'LazyFrame'
    object has no attribute 'height'``. Anything else is refused by name.

    Raises:
        TypeError: If ``model_points`` is neither a DataFrame nor a LazyFrame.

    """
    if isinstance(model_points, pl.LazyFrame):
        return model_points.collect()
    if isinstance(model_points, pl.DataFrame):
        return model_points
    msg = (
        f"{runner}() takes the model points as a Polars DataFrame or LazyFrame, "
        f"and got a {type(model_points).__name__}. Read the book with "
        "pl.read_parquet or pl.scan_parquet and pass that."
    )
    raise TypeError(msg)


def _safe_rss_bytes() -> int | None:
    """Return current RSS in bytes, or None if psutil cannot read the process.

    Measurement must never abort a scenario run; on sandboxes or platforms
    where RSS is unreadable, callers should treat None as "unknown" and
    continue without high-water-mark tracking.
    """
    try:
        return process_rss_bytes()
    except (OSError, AttributeError):
        return None


def _measure_peak_delta(
    work: Callable[[], object],
    *,
    rss_reader: Callable[[], int | None] = _safe_rss_bytes,
    interval: float = 0.005,
) -> int:
    """Run ``work`` while sampling RSS; return peak-over-baseline in bytes.

    The auto-probe needs the *transient* peak working set of a batch — the
    spike Polars allocates during materialisation, which risks OOM — not the
    steady-state RSS that lingers after those temporaries are freed. Reading
    ``rss_after - rss_before`` misses that spike entirely (it is gone by the
    time ``rss_after`` is read), so a background thread samples RSS during the
    call and the maximum is returned.

    Measurement must never abort a run: if RSS is unreadable (``None``), this
    returns 0 and the caller falls back to its noise floor.
    """
    before = rss_reader()
    peak = before if before is not None else 0
    stop = threading.Event()

    def _sample() -> None:
        nonlocal peak
        while not stop.is_set():
            reading = rss_reader()
            if reading is not None and reading > peak:
                peak = reading
            stop.wait(interval)

    sampler = threading.Thread(target=_sample, daemon=True)
    sampler.start()
    try:
        work()
    finally:
        stop.set()
        sampler.join(timeout=1.0)

    after = rss_reader()
    if after is not None and after > peak:
        peak = after
    if before is None:
        return 0
    return max(0, peak - before)


def _without_working_columns(lazy: pl.LazyFrame, af: ActuarialFrame) -> pl.LazyFrame:
    """Return ``lazy`` without either family of columns the frame works in.

    Two kinds of column ride a model's plan without being columns of the
    model. A column written twice leaves its first output under a hidden
    name, so that an export can say what the column held before the override
    (``ActuarialFrame.collect``); a compiled rollforward materialises one
    scratch struct so its kernel runs once however many states are read back
    out of it. ``collect()`` takes both off the frame it hands over, and the
    frame's own ``schema`` lists neither.

    None of the memory-safe drivers goes through ``collect()``: what comes
    out of them is folded into aggregates, written to parquet, or handed back
    as a scenario grid, and a producer's working in any of those is a column
    of nobody's model -- in the worst case a column of somebody's parquet
    file, where the struct is not even a number.

    Taken off the plan rather than off the result, so nothing is materialised
    for a reader that does not exist, and taken without a schema resolve --
    which would also move an invalid plan's failure out of the collect that
    reports it well. The two families are reached differently because the
    frame records them differently: the superseded names come from its own
    record of what it minted, and the scratch struct, which it keeps no such
    record of, comes off by the prefix its names are minted under, resolved
    by the engine rather than here.

    Both are guarded by a truth test, and the two guards are not scoped alike.
    The superseded one asks this frame what it minted, so a model that writes
    no column twice pays a truth test and nothing else. The rollforward one
    asks whether anything in the *process* has compiled one, and that record
    is never cleared -- so once any model in the session compiles a
    rollforward, every later plan carries the drop, matching nothing and
    costing no schema resolve, but carried all the same. It is a plan node,
    not a resolve, which is the cost this helper exists to avoid.
    """
    held = af._retained_columns  # noqa: SLF001 -- the frame's own record
    if held:
        lazy = lazy.drop(held, strict=False)
    if _rollforward_registry.has_entries():
        lazy = lazy.drop(cs.starts_with(_rollforward_registry.HIDDEN_PREFIX))
    return lazy


def _collect_with_peak(
    lazy: pl.LazyFrame,
    *,
    engine: Literal["auto", "in-memory", "streaming"] | None = None,
) -> tuple[pl.DataFrame, int]:
    """Collect ``lazy`` while sampling RSS; return (frame, peak-over-baseline).

    Captures the transient materialisation peak (the per-batch memory cost the
    streaming-batch search compares against the budget) alongside the collected frame.

    ``engine`` selects the Polars execution engine, and is axis-dependent:

    * **Policy-axis** drivers (``run_aggregated`` / ``run_to_parquet``) pass
      ``engine="streaming"`` — for their per-policy *slice* plans (no join) the
      streaming engine is ~5.5x faster AND lower-peak than the in-memory engine
      (L4 @ 100K: 1.7s/3.1GB vs 9.5s/3.5GB); ``engine="auto"`` does NOT pick it.
    * **Scenario-axis** (``for_each_scenario``): the streaming-batch search passes
      ``engine="streaming"`` for its probe and operating batches. Streaming pairs safely
      with small batches; peak grows with batch size and, at high policy counts,
      inflates *above* the in-memory engine (Polars cross-join hazard #20786).
      Thus ``in-mem@b1`` is the floor when no streaming batch fits the budget.
    """
    holder: dict[str, pl.DataFrame] = {}

    def _work() -> None:
        holder["frame"] = (
            lazy.collect() if engine is None else lazy.collect(engine=engine)
        )

    peak = _measure_peak_delta(_work)
    return holder["frame"], peak


def _collect_batch(
    af: ActuarialFrame,
    *,
    engine: Literal["auto", "in-memory", "streaming"],
) -> tuple[pl.DataFrame, int]:
    """Collect one built batch without retaining values on its authoring frame.

    The caller owns composition, sizing, folding and publication. This boundary
    owns plan validation, removal of working columns, peak measurement and error
    attribution. It deliberately does not call ordinary frame completion.
    """
    lazy = af._df  # noqa: SLF001 -- bounded execution reads the frame's plan
    if lazy is None:
        msg = "model_fn returned an ActuarialFrame with no underlying frame."
        raise ValueError(msg)
    try:
        return _collect_with_peak(_without_working_columns(lazy, af), engine=engine)
    except Exception as error:
        _handle_execution_error(af, error)
        raise  # Preserve the original failure if a custom handler returns.
