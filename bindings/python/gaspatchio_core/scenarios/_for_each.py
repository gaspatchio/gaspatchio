# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: for_each_scenario -- bounded-memory scenario-loop primitive.
# ABOUTME: Public; ScenarioRun.run() is a thin delegate on top of this.

"""Bounded-memory scenario loop (GSP-101 per-aggregator within-reduction).

:func:`for_each_scenario` runs ``model_fn`` once per scenario (or per batch).
For each batch and each aggregator, the loop computes the aggregator's
within-scenario reduction (``agg.within_expr()``) grouped by
``[scenario_id, *partition_keys]``, then folds each reduced row into the
aggregator's accumulator state. Peak memory stays bounded regardless of
the number of scenarios.

Supported ``scenarios`` shapes:

* ``list[ScenarioID]`` -- ids only; ``model_fn`` receives the un-shocked
  base tables as ``tables``.
* ``dict[ScenarioID, list[Shock]]`` -- per-scenario shock recipes; each
  batch's base tables are stacked with a ``scenario_id`` dimension and
  shocks composed per scenario via :func:`stack_shocked_table`.
* ``dict[ScenarioID, dict[str, Any]]`` -- per-scenario driver kwargs
  forwarded to ``model_fn(drivers=...)``. Drivers are forwarded only when
  ``batch_size=1``; for ``batch_size>1`` users with drivers must fan out
  by ``scenario_id`` inside ``model_fn``.

When ``master_seed`` is set, a deterministic per-scenario seed is derived
via sha256 and injected into ``drivers['rng_seed']`` (also only at
``batch_size=1``).
"""

from __future__ import annotations

import contextlib
import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

import polars as pl
from loguru import logger

from gaspatchio_core.scenarios._auto_batch import (
    _SAFETY_CEILING,
    memory_budget_bytes,
    process_rss_bytes,
)
from gaspatchio_core.scenarios._memory import DEFAULTS, IrreducibleCellError
from gaspatchio_core.scenarios._metric import Aggregator, _Partitioned
from gaspatchio_core.scenarios._period_aggregators import _tidy_partitioned_vector
from gaspatchio_core.scenarios._result import (
    ProbeResult,
    ScenarioResult,
    SelectionDecision,
)
from gaspatchio_core.scenarios._search import build_ladder, decide_winner
from gaspatchio_core.scenarios._stack import stack_shocked_table
from gaspatchio_core.scenarios._validate import (
    check_no_duplicate_ids,
    check_non_empty,
)
from gaspatchio_core.scenarios._with_scenarios import with_scenarios

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.frame import ActuarialFrame
    from gaspatchio_core.scenarios._period_aggregators import VectorAggregator
    from gaspatchio_core.scenarios.shocks import Shock

T = TypeVar("T", str, int)
ScenarioID = str | int


def _fmt_duration(seconds: float) -> str:
    """Render a wall-clock duration compactly: '45s', '3m12s', '1h04m'."""
    total = int(seconds)
    if total < 60:  # noqa: PLR2004
        return f"{total}s"
    if total < 3600:  # noqa: PLR2004
        minutes, secs = divmod(total, 60)
        return f"{minutes}m{secs:02d}s"
    hours, remainder = divmod(total, 3600)
    return f"{hours}h{remainder // 60:02d}m"


@dataclass(frozen=True, slots=True)
class BatchSnapshot:
    """Immutable convergence snapshot emitted after each batch folds.

    Passed to the ``on_batch`` callback of :func:`for_each_scenario` at the
    end of every batch iteration. Carries the cumulative running partials so a
    caller can render a convergence trace (CTE/quantile drift, filling
    histograms) as the loop streams scenarios.

    Attributes:
        batch_idx: 0-based batch index (equals the loop ``enumerate`` index).
        scenarios_done: Cumulative count of real scenarios folded so far,
            inclusive of this batch. Probe scenarios are never counted.
        total_scenarios: Total scenarios in the run (``len(sids)``).
        outputs: ``{alias: agg.extract_output(running_accumulator)}`` — the
            running partial per aggregator. Scalar for plain aggregators, a
            :class:`polars.DataFrame` for partitioned (``.over(...)``) ones.
            These are *materialised* extracts, not raw accumulator state, so
            a later batch cannot retro-mutate an already-emitted snapshot.
        peak_rss_mb: Peak RSS over baseline in MiB at the end of this batch,
            or ``None`` when RSS is unreadable (e.g. some sandboxes).
        elapsed_s: Wall seconds since the run started, at the end of this
            batch. Combined with ``scenarios_done``/``total_scenarios`` it
            drives ``fraction_done``, ``eta_s`` and ``throughput``.

    """

    batch_idx: int
    scenarios_done: int
    total_scenarios: int
    outputs: dict[str, Any]
    peak_rss_mb: float | None
    elapsed_s: float

    @property
    def fraction_done(self) -> float:
        """Fraction of real scenarios folded so far, in [0, 1]."""
        if self.total_scenarios == 0:
            return 0.0
        return self.scenarios_done / self.total_scenarios

    @property
    def eta_s(self) -> float | None:
        """Rough estimated seconds remaining; None before any progress.

        Linear extrapolation from elapsed wall time and fraction done. A guide
        only: under ``batch_size='auto'`` batch sizes vary (and the streaming
        search probes deliberately differ), so this is approximate. ``elapsed_s``
        includes probe time while ``scenarios_done`` excludes probe scenarios.
        """
        if self.scenarios_done >= self.total_scenarios:
            return 0.0
        if self.scenarios_done <= 0:
            return None
        return self.elapsed_s * (self.total_scenarios / self.scenarios_done - 1.0)

    @property
    def throughput(self) -> float | None:
        """Real scenarios folded per second so far; None if no time elapsed."""
        if self.elapsed_s <= 0:
            return None
        return self.scenarios_done / self.elapsed_s


def _resolve_sids(
    shape: Literal["ids", "shocks", "drivers"],
    scenarios: list[ScenarioID]
    | dict[ScenarioID, list[Shock]]
    | dict[ScenarioID, dict[str, Any]],
) -> list[ScenarioID]:
    """Return the scenario_id list for the given shape."""
    if shape == "ids":
        return list(scenarios)
    return list(scenarios.keys())  # type: ignore[union-attr]


def _build_stacked_tables(
    scenarios: dict[ScenarioID, list[Shock]],
    batch_sids: list[ScenarioID],
    base_tables: dict[str, Table] | None,
) -> dict[str, Table]:
    """Build per-batch stacked tables for the shocks-dict shape.

    For each base table, gather the per-scenario shock lists filtered to those
    targeting that table (or untargeted), then stack via
    :func:`stack_shocked_table`.
    """
    return {
        name: stack_shocked_table(
            base,
            {
                sid: [  # type: ignore[misc]
                    s
                    for s in scenarios[sid]
                    if getattr(s, "table", None) in (name, None)
                ]
                for sid in batch_sids
            },
        )
        for name, base in (base_tables or {}).items()
    }


def _classify(scenarios: object) -> Literal["ids", "shocks", "drivers"]:
    """Classify the scenarios input to dispatch to the right shape handler."""
    if isinstance(scenarios, list):
        return "ids"
    if isinstance(scenarios, dict):
        values = list(scenarios.values())
        if not values:
            # Empty dict; downstream non-empty check raises a clearer error.
            return "ids"
        types = {type(v) for v in values}
        if types == {list}:
            return "shocks"
        if types == {dict}:
            return "drivers"
        msg = (
            f"scenarios dict has mixed value types {types}; "
            "expected all-list (shocks) or all-dict (drivers)"
        )
        raise TypeError(msg)
    msg = f"scenarios must be list or dict, got {type(scenarios).__name__}"
    raise TypeError(msg)


def _per_scenario_seed(master_seed: int, scenario_id: ScenarioID) -> int:
    """Derive a deterministic 32-bit seed from ``(master_seed, scenario_id)``.

    Uses sha256 (NOT Python's ``hash()``) because ``PYTHONHASHSEED`` randomises
    string hashing across processes. Same inputs produce the same output
    across machines and Python versions.
    """
    payload = f"gsp-100|{master_seed}|{scenario_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _build_drivers(
    scenarios: list[ScenarioID]
    | dict[ScenarioID, list[Shock]]
    | dict[ScenarioID, dict[str, Any]],
    batch_sids: list[ScenarioID],
    shape: Literal["ids", "shocks", "drivers"],
    master_seed: int | None,
) -> dict[str, Any]:
    """Build the drivers dict passed to ``model_fn`` for this batch.

    For ``batch_size=1`` (single sid in batch), forwards the scenario's
    drivers (drivers shape only) and/or the derived ``rng_seed`` (when
    ``master_seed`` is set). For ``batch_size>1``, drivers are per-scenario:
    they are intentionally not forwarded here, and callers that need them
    must fan out by ``scenario_id`` inside ``model_fn``.
    """
    out: dict[str, Any] = {}

    if shape == "drivers" and len(batch_sids) == 1:
        out.update(scenarios[batch_sids[0]])  # type: ignore[index,arg-type]

    if master_seed is not None and len(batch_sids) == 1:
        out["rng_seed"] = _per_scenario_seed(master_seed, batch_sids[0])

    return out


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
      with small batches; peak grows with batch size and, at high policy counts, inflates
      *above* the in-memory engine (the Polars cross-join streaming hazard, #20786) — which
      is why ``in-mem@b1`` is the memory floor the search falls back to when no streaming
      batch fits the budget.
    """
    holder: dict[str, pl.DataFrame] = {}

    def _work() -> None:
        holder["frame"] = (
            lazy.collect() if engine is None else lazy.collect(engine=engine)
        )

    peak = _measure_peak_delta(_work)
    return holder["frame"], peak


def _chunks(seq: list[T], size: int) -> Iterator[list[T]]:
    """Yield successive ``size``-sized slices of ``seq``."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _write_batch_parquet(frame: pl.DataFrame, path: Path) -> None:
    """Sort by scenario_id only if present (the policy axis has none), then write."""
    # local import: avoids _for_each <-> _spill load-time circular dependency
    from gaspatchio_core.scenarios._spill import safe_write_parquet

    if "scenario_id" in frame.columns:
        frame = frame.sort("scenario_id")
    safe_write_parquet(frame, path)


def _needs_scenario_id(agg: Aggregator | _Partitioned) -> bool:
    """Return True if the aggregator opts in via ``requires_scenario_id``.

    For ``_Partitioned``, look at the inner aggregator. Aggregators that
    need to see the scenario identity (e.g. ArgMin/ArgMax) set
    ``requires_scenario_id: ClassVar[bool] = True``; the loop then packs
    ``(scenario_id, value)`` tuples into ``add_input`` rather than bare
    values.
    """
    inner = agg.inner if isinstance(agg, _Partitioned) else agg
    return getattr(inner, "requires_scenario_id", False)


def _fold_vector_aggregators(
    proj_eager: pl.DataFrame,
    *,
    aliases: list[str],
    aggregations: Sequence[Aggregator | _Partitioned],
    accumulators: dict[str, Any],
) -> None:
    """Fold the vector (Period*) aggregators of one batch into ``accumulators``.

    VectorAggregators carry ``batch_reduce``; the ``__period`` index is built from
    each aggregator's own list column (jagged columns each get the right index), then
    the whole batch folds together (the accumulator accumulates across batches). A
    ``.over()`` aggregator folds per partition via ``batch_reduce_over``.

    Axis-awareness: on the scenario axis a non-partitioned ``Period*`` must reduce
    ACROSS scenarios of each scenario's per-period total (two-stage), not over every
    policy x scenario cell — otherwise ``PeriodMean``/``PeriodCount`` blow up by the
    policy count. The scenario axis is detected by the presence of a ``scenario_id``
    column (``for_each_scenario`` always cross-joins it in; the policy-axis
    ``run_aggregated`` has no such column and uses its own fold that calls
    ``batch_reduce`` directly, so it is unaffected).
    """
    period = "__period"
    for alias, agg in zip(aliases, aggregations, strict=True):
        inner_agg = agg.inner if isinstance(agg, _Partitioned) else agg
        if not hasattr(inner_agg, "batch_reduce"):
            continue
        vec = cast("VectorAggregator", inner_agg)
        proj_p = proj_eager.with_columns(
            pl.int_ranges(pl.col(vec.column).list.len()).alias(period),
        )
        if isinstance(agg, _Partitioned):
            # vector .over(): per-partition partial -> _Partitioned.add_input per key
            for key, partial in vec.batch_reduce_over(proj_p, period, agg.by).items():
                accumulators[alias] = agg.add_input(accumulators[alias], (key, partial))
        else:
            if "scenario_id" in proj_p.columns:
                partial = vec.batch_reduce_within(proj_p, period, ("scenario_id",))
            else:
                partial = vec.batch_reduce(proj_p, period)
            accumulators[alias] = inner_agg.add_input(accumulators[alias], partial)


def _fold_batch(
    proj_eager: pl.DataFrame,
    *,
    aliases: list[str],
    aggregations: Sequence[Aggregator | _Partitioned],
    accumulators: dict[str, Any],
) -> None:
    """Fold one collected batch's within-reductions into ``accumulators`` (in place).

    Extracted verbatim from the inline loop body so the probe phase and the remainder
    phase can share one fold implementation. Behaviour is unchanged.
    """
    # Vector (Period*) aggregators fold first via their own helper (kept out of this
    # function to bound its complexity); the scalar group_by fold follows.
    _fold_vector_aggregators(
        proj_eager,
        aliases=aliases,
        aggregations=aggregations,
        accumulators=accumulators,
    )

    # Group aggregators by partition-key signature so each signature is
    # reduced in a single combined group_by call per batch. With N scalar
    # aggregators (signature ``()``) this collapses N hash-aggregations
    # of the same projection into one.
    # Note: vector aggregators (batch_reduce present) are excluded here —
    # they were already folded above and within_expr() raises for them.
    groups: dict[tuple[str, ...], list[tuple[str, Aggregator | _Partitioned]]] = {}
    for alias, agg in zip(aliases, aggregations, strict=True):
        inner_agg = agg.inner if isinstance(agg, _Partitioned) else agg
        if hasattr(inner_agg, "batch_reduce"):
            continue  # already handled above
        partition_keys = list(agg.by) if isinstance(agg, _Partitioned) else []
        sig = tuple(partition_keys)
        groups.setdefault(sig, []).append((alias, agg))

    for partition_signature, group_members in groups.items():
        # scenario_id is always implicit in the per-batch group key;
        # if the user explicitly partitioned by it via .over("scenario_id"),
        # don't add it twice (polars rejects duplicate group_by keys).
        extra_keys = [k for k in partition_signature if k != "scenario_id"]
        group_keys = ["scenario_id", *extra_keys]
        within_exprs = [
            (member_agg.inner if isinstance(member_agg, _Partitioned) else member_agg)
            .within_expr()
            .alias(member_alias)
            for member_alias, member_agg in group_members
        ]
        reduced = proj_eager.group_by(group_keys).agg(*within_exprs)

        # Pre-resolve column positions for fast positional row iteration.
        col_positions = {name: i for i, name in enumerate(reduced.columns)}
        sid_pos = col_positions["scenario_id"]
        partition_positions = [col_positions[k] for k in partition_signature]
        alias_positions = [
            (member_alias, member_agg, col_positions[member_alias])
            for member_alias, member_agg in group_members
        ]
        has_partition = bool(partition_signature)

        for row in reduced.iter_rows():
            scenario_id = row[sid_pos]
            partition_key = (
                tuple(row[p] for p in partition_positions) if has_partition else ()
            )
            for member_alias, member_agg, value_pos in alias_positions:
                value = row[value_pos]
                needs_sid = _needs_scenario_id(member_agg)

                if isinstance(member_agg, _Partitioned):
                    inner_value = (scenario_id, value) if needs_sid else value
                    accumulators[member_alias] = member_agg.add_input(
                        accumulators[member_alias],
                        (partition_key, inner_value),
                    )
                else:
                    payload = (scenario_id, value) if needs_sid else value
                    accumulators[member_alias] = member_agg.add_input(
                        accumulators[member_alias],
                        payload,
                    )


def _run_one_batch(
    af: ActuarialFrame,
    batch_sids: list[ScenarioID],
    model_fn: Callable[..., ActuarialFrame],
    *,
    scenarios: Any,
    shape: Literal["ids", "shocks", "drivers"],
    base_tables: dict[str, Table] | None,
    master_seed: int | None,
    engine: Literal["in-memory", "streaming"],
) -> tuple[pl.DataFrame, int, float]:
    """Build + collect one batch under ``engine``; return (frame, peak_bytes, wall_s)."""
    af_batch = with_scenarios(af, batch_sids)  # type: ignore[arg-type]
    if shape == "shocks":
        tables = _build_stacked_tables(scenarios, batch_sids, base_tables)
    else:
        tables = base_tables or {}
    drivers = _build_drivers(scenarios, batch_sids, shape, master_seed)
    af_proj = model_fn(af_batch, tables=tables, drivers=drivers)
    if af_proj._df is None:  # noqa: SLF001
        msg = (
            "model_fn returned an ActuarialFrame with no underlying frame; "
            "this is a contract violation."
        )
        raise ValueError(msg)
    # Pass the requested engine straight through. Mapping "in-memory" to None made
    # _collect_with_peak fall back to lazy.collect()'s default ("auto"), so the
    # in-memory floor / single-scenario / manual paths never actually ran in-memory
    # and could re-select streaming — the cross-join inflation the floor avoids.
    started = time.perf_counter()
    proj_eager, peak = _collect_with_peak(af_proj._df, engine=engine)  # noqa: SLF001
    return proj_eager, peak, time.perf_counter() - started


def _agg_alias(agg: Aggregator | _Partitioned) -> str:
    """Return the public alias for an aggregator (used as the output key)."""
    if isinstance(agg, _Partitioned):
        # _Partitioned.__post_init__ guarantees a non-empty alias.
        return agg.alias
    alias_ = getattr(agg, "alias_", None)
    if not alias_:
        msg = (
            f"Aggregator {type(agg).__name__} has no alias; call "
            ".alias(name) on every aggregator passed to for_each_scenario."
        )
        raise ValueError(msg)
    return cast("str", alias_)


def for_each_scenario(  # noqa: C901, PLR0912, PLR0913, PLR0915
    af: ActuarialFrame,
    scenarios: list[ScenarioID]
    | dict[ScenarioID, list[Shock]]
    | dict[ScenarioID, dict[str, Any]],
    model_fn: Callable[..., ActuarialFrame],
    *,
    aggregations: Sequence[Aggregator | _Partitioned],
    base_tables: dict[str, Table] | None = None,
    batch_size: int | Literal["auto"] = "auto",
    target_memory_fraction: float = 0.5,
    return_full_grid: bool = False,
    sink_dir: Path | None = None,
    master_seed: int | None = None,
    progress: bool = False,
    on_batch: Callable[[BatchSnapshot], None] | None = None,
    plan_sha: str = "",
) -> ScenarioResult:
    """Run ``model_fn`` per scenario; fold per-aggregator within-reductions.

    Each aggregator in ``aggregations`` carries its own within-scenario
    reduction expression (``agg.within_expr()``). For each batch and each
    aggregator, the loop groups the projection by
    ``[scenario_id, *agg.by]`` (``agg.by`` is empty for non-partitioned
    aggregators), applies the within reduction, and folds each reduced
    row into the aggregator's accumulator state via ``add_input``.

    Supports three ``scenarios`` shapes:

    * ``list[ScenarioID]`` -- ids only; ``model_fn`` sees the un-shocked
      ``base_tables`` as ``tables``.
    * ``dict[ScenarioID, list[Shock]]`` -- per-scenario shock recipes; each
      batch's base tables are stacked with a ``scenario_id`` dimension and
      shocks composed per scenario via :func:`stack_shocked_table`.
    * ``dict[ScenarioID, dict[str, Any]]`` -- per-scenario driver kwargs
      forwarded to ``model_fn(drivers=...)``. Forwarded only at
      ``batch_size=1``; for ``batch_size>1`` callers must fan out by
      ``scenario_id`` inside ``model_fn``.

    When ``master_seed`` is set, a deterministic per-scenario seed is derived
    via sha256 and injected into ``drivers['rng_seed']``; also only at
    ``batch_size=1``.

    Model function contract:
        ``model_fn`` is called once per batch with the signature
        ``model_fn(af, *, tables, drivers) -> ActuarialFrame``.

    Notes:
        Per-scenario drivers and the derived ``drivers["rng_seed"]`` are
        delivered to ``model_fn`` only when each batch contains a single
        scenario. A ``ValueError`` is raised when ``master_seed`` is set
        or the drivers-dict shape is used together with ``batch_size > 1``.

        ArgMin/ArgMax aggregators are special-cased: they require
        ``(scenario_id, value)`` tuples rather than bare values.
        Partitioned aggregators (via ``.over(by)``) wrap their inner
        value in a ``(partition_key, value)`` tuple.

    Cross-join semantics:
        Every scenario sees every policy. The base ActuarialFrame is
        cross-joined with the batch's ``scenario_id`` column before
        ``model_fn`` runs, so a 1000-policy frame in 100 scenarios yields
        a 100,000-row projection. Custom aggregators receive per-scenario
        within-reductions over the full policy universe -- they do not see
        policy[i] paired with scenario[i]. To produce per-scenario distinct
        values, either:

        * let scenarios differ via base-table shocks (the standard pattern),
        * read ``pl.col("scenario_id")`` inside ``model_fn`` and branch on it,
          or
        * use a drivers-dict shape and read ``drivers["scenario_id"]`` (at
          ``batch_size=1``).

    """
    shape = _classify(scenarios)

    sids = _resolve_sids(shape, scenarios)

    check_non_empty(sids)
    check_no_duplicate_ids(sids)

    if not aggregations:
        msg = "for_each_scenario requires at least one aggregator."
        raise ValueError(msg)

    # Each aggregator must have an alias; collect them and check for collisions.
    aliases = [_agg_alias(agg) for agg in aggregations]
    if len(set(aliases)) != len(aliases):
        msg = f"Aggregator aliases must be unique; got duplicates in {aliases}."
        raise ValueError(msg)

    # PeriodQuantile.over() has a multi-level {level: vector} output with no tidy
    # single-column form; defer it (PeriodMedian/PeriodCTE.over() cover tail metrics).
    for alias, agg in zip(aliases, aggregations, strict=True):
        if isinstance(agg, _Partitioned) and hasattr(agg.inner, "levels"):
            msg = (
                f"PeriodQuantile.over() ({alias!r}) is not yet supported; use "
                "PeriodMedian/PeriodCTE with .over(), or PeriodQuantile "
                "without .over()."
            )
            raise NotImplementedError(msg)

    if af._df is None:  # noqa: SLF001
        msg = "ActuarialFrame has no underlying frame; cannot run scenarios."
        raise ValueError(msg)

    if return_full_grid:
        sink_dir = sink_dir or Path(f"./scenarios_{int(time.time())}")
        sink_dir.mkdir(parents=True, exist_ok=True)

    if progress and on_batch is None:
        # progress=True installs a built-in loguru-logging hook. If the user
        # ALSO passed an on_batch, their callback wins silently (no raise) and
        # progress is ignored — handled by the `and on_batch is None` guard.
        def _default_progress(snap: BatchSnapshot) -> None:
            eta = snap.eta_s
            tail = f" · ETA {_fmt_duration(eta)}" if eta is not None and eta > 0 else ""
            logger.info(
                "scenarios {}/{} ({:.0%}){}",
                snap.scenarios_done,
                snap.total_scenarios,
                snap.fraction_done,
                tail,
            )

        on_batch = _default_progress

    # One accumulator per aggregator, keyed by alias.
    accumulators: dict[str, Any] = {
        alias: agg.create_accumulator()
        for alias, agg in zip(aliases, aggregations, strict=True)
    }

    started = time.perf_counter()
    baseline_rss = _safe_rss_bytes()
    peak_rss = baseline_rss
    max_batch_peak = 0  # max transient collect peak across batches
    folded: list[
        ScenarioID
    ] = []  # scenarios already projected+folded (probe + remainder)
    batch_idx = 0
    selection: SelectionDecision | None = None
    resolution: Literal["manual", "auto_search"]
    winner_engine: Literal["in-memory", "streaming"]
    probed: list[ProbeResult] = []
    floor: ProbeResult | None = None

    def _process_one(
        batch_sids: list[ScenarioID],
        *,
        engine: Literal["in-memory", "streaming"],
    ) -> tuple[int, float]:
        """Build+collect+fold one batch under ``engine``; return (peak_bytes, wall_s).

        Each batch -- whether a search probe or a remainder batch -- folds its
        scenarios into the accumulators exactly once and advances
        ``folded``/``batch_idx``. The remainder is always ``sids[len(folded):]``,
        so nothing is re-folded or double-counted. Updates the RSS high-water
        tracking and fires ``on_batch`` after the fold.
        """
        nonlocal peak_rss, baseline_rss, max_batch_peak, batch_idx
        proj_eager, batch_peak, batch_wall = _run_one_batch(
            af,
            batch_sids,
            model_fn,
            scenarios=scenarios,
            shape=shape,
            base_tables=base_tables,
            master_seed=master_seed,
            engine=engine,
        )
        max_batch_peak = max(max_batch_peak, batch_peak)
        _fold_batch(
            proj_eager,
            aliases=aliases,
            aggregations=aggregations,
            accumulators=accumulators,
        )
        if return_full_grid and sink_dir is not None:
            _write_batch_parquet(
                proj_eager, sink_dir / f"batch_{batch_idx:04d}.parquet"
            )
        del proj_eager
        folded.extend(batch_sids)
        current_rss = _safe_rss_bytes()
        if current_rss is not None:
            if baseline_rss is None:
                baseline_rss = current_rss
                peak_rss = current_rss
            elif peak_rss is None:
                peak_rss = current_rss
            else:
                peak_rss = max(peak_rss, current_rss)
        if on_batch is not None:
            if peak_rss is not None and baseline_rss is not None:
                _snap_peak_mb = max(0, peak_rss - baseline_rss) / (1024 * 1024)
            else:
                _snap_peak_mb = None
            _snap_outputs = {}
            for alias, agg in zip(aliases, aggregations, strict=True):
                _raw = agg.extract_output(accumulators[alias])
                if isinstance(agg, _Partitioned) and hasattr(agg.inner, "batch_reduce"):
                    _raw = _tidy_partitioned_vector(_raw, by=agg.by, alias=alias)
                _snap_outputs[alias] = _raw
            with contextlib.suppress(Exception):
                on_batch(
                    BatchSnapshot(
                        batch_idx=batch_idx,
                        scenarios_done=len(folded),
                        total_scenarios=len(sids),
                        outputs=_snap_outputs,
                        peak_rss_mb=_snap_peak_mb,
                        elapsed_s=time.perf_counter() - started,
                    )
                )
        batch_idx += 1
        return batch_peak, batch_wall

    def _peak_fits(peak_bytes: int, budget_mb: float) -> bool:
        return peak_bytes / 1024**2 * DEFAULTS.safety_margin <= budget_mb

    if batch_size != "auto":
        # Manual batch size: in-memory, no search; user override respected.
        resolved_size, resolution, winner_engine = (
            int(batch_size),
            "manual",
            "in-memory",
        )
    elif master_seed is not None or shape == "drivers":
        # Forced batch_size=1 (seeds/drivers inject only at b=1): engine-only choice,
        # each candidate feasibility-gated.
        resolved_size, resolution, winner_engine = 1, "auto_search", "in-memory"
        budget_mb = memory_budget_bytes(target_memory_fraction) / 1024**2
        for eng in ("streaming", "in-memory"):
            remaining = sids[len(folded) :]
            if not remaining:
                break
            peak, wall = _process_one(remaining[:1], engine=eng)
            probed.append(
                ProbeResult(
                    1, eng, wall, peak / 1024**2, fits=_peak_fits(peak, budget_mb)
                )
            )
        remainder = sids[len(folded) :]
        feasible = [p for p in probed if p.fits]
        if feasible:
            win = min(feasible, key=lambda p: p.per_sc_s)
        elif not remainder:
            # The probes already folded every scenario -- the run completed, so report the
            # faster engine without raising (there is no remainder left to protect from OOM).
            win = min(probed, key=lambda p: p.per_sc_s)
        else:
            msg = (
                "Forced batch_size=1 (master_seed / drivers-dict): neither the streaming "
                "nor the in-memory engine fits the memory budget at batch_size=1. Reduce "
                "policies, shorten the horizon, raise target_memory_fraction, or run on a "
                "box with more memory."
            )
            raise IrreducibleCellError(msg)
        winner_engine = win.engine
        selection = SelectionDecision(win.engine, 1, "forced_b1", probed)
    elif len(sids) == 1:
        # Single scenario: no search is possible. Run it once on the in-memory floor -- the
        # lightest engine (streaming inflates the cross-join peak at high policy counts), so the
        # degenerate single-pass case never OOMs from streaming inflation, and speed for one pass
        # is immaterial. The remainder loop below folds the one scenario exactly once.
        resolved_size, resolution, winner_engine = 1, "auto_search", "in-memory"
        selection = SelectionDecision("in-memory", 1, "single_scenario", [])
    else:
        # Auto: coarse streaming-batch search on real folded passes. Rungs after the
        # first are gated by linear extrapolation from the last measured rung, so the
        # search never launches a probe it can predict is unaffordable. Residual risk:
        # the FIRST rung (streaming b=1) has no prior measurement to predict from; if
        # even that exceeds physical memory the kernel kills the process before the
        # search can back off (a seed-slice estimator, as on the policy axis, would be
        # the escalation if that case is ever observed in practice).
        resolution = "auto_search"
        budget_mb = memory_budget_bytes(target_memory_fraction) / 1024**2
        ladder = build_ladder(
            n_scenarios=len(sids), ladder=DEFAULTS.ladder, ceiling=_SAFETY_CEILING
        )
        for b in ladder:
            nxt = sids[len(folded) : len(folded) + b]
            if len(nxt) < b:  # not enough scenarios left to measure this rung honestly
                break
            if probed:
                # Gate: predict this rung from the last measured one before running it.
                # A rung whose predicted peak already fails the fits test could never be
                # selected -- probing it would pay an unbounded memory cost for zero
                # information, and is exactly the kernel-OOM path: a probe that exceeds
                # physical memory dies mid-collect, before its peak is ever recorded and
                # before any back-off logic can run.
                # The prediction is linear-in-batch TIMES streaming_batch_inflation:
                # under the streaming engine the scenario cross-join peak is super-linear
                # in batch at high policy counts (Polars #20786). Measured on the CI
                # 10sc x 100K cell: b=1 ~1.3 GB but b=4 ~11.5 GB -- 8.6x for a 4x batch
                # step, 2.2x above linear -- so a bare linear gate passed b=4 against a
                # 7.7 GB budget and the probe killed a 16 GB runner. Over-predicting
                # costs at most a smaller batch; under-predicting costs the process.
                # peak_mb is None only for a rung that could not be measured, and
                # such a rung is fits=False, which breaks the loop before a next
                # iteration -- so this is unreachable in practice; it satisfies the
                # ProbeResult type and degrades to "no gate" if that ever changes.
                last = probed[-1]
                if last.peak_mb is not None:
                    predicted_mb = (
                        last.peak_mb
                        * (b / last.batch)
                        * DEFAULTS.streaming_batch_inflation
                    )
                    if predicted_mb * DEFAULTS.safety_margin > budget_mb:
                        break  # larger rungs are heavier -> nothing above fits either
            peak, wall = _process_one(nxt, engine="streaming")
            pr = ProbeResult(
                b,
                "streaming",
                wall / b,
                peak / 1024**2,
                fits=_peak_fits(peak, budget_mb),
            )
            probed.append(pr)
            if not pr.fits:  # larger rungs are heavier -> stop probing
                break
        remainder = sids[len(folded) :]
        if not remainder:
            # Probes folded every scenario -- the run completed. Report the fastest probed rung;
            # do not raise on "fit" (there is no remainder left to protect from OOM).
            best = min(probed, key=lambda p: p.per_sc_s)
            selection = SelectionDecision(
                "streaming", best.batch, "fastest_fitting", probed
            )
            resolved_size, winner_engine = best.batch, "streaming"
        else:
            if not any(p.fits for p in probed):
                fpeak, fwall = _process_one(remainder[:1], engine="in-memory")
                floor = ProbeResult(
                    1,
                    "in-memory",
                    fwall,
                    fpeak / 1024**2,
                    fits=_peak_fits(fpeak, budget_mb),
                )
            selection = decide_winner(
                probed,
                budget_mb=budget_mb,
                safety_margin=DEFAULTS.safety_margin,
                floor=floor,
            )
            resolved_size, winner_engine = selection.batch, selection.engine

    # Explicit batch_size>1 with master_seed / drivers-dict is unsupported (manual path;
    # the auto forced-b1 path above already resolved to 1).
    if master_seed is not None and resolved_size > 1:
        msg = (
            "master_seed currently injects rng_seed only at batch_size=1; "
            "batched runs (batch_size > 1) do not pass per-scenario seeds to "
            "model_fn. Use batch_size=1 if you need deterministic "
            "per-scenario seeding, or fan out by scenario_id inside model_fn "
            "using a seed of your own choosing."
        )
        raise ValueError(msg)

    if shape == "drivers" and resolved_size > 1:
        msg = (
            "drivers-dict scenario shape currently forwards per-scenario "
            "drivers only at batch_size=1; batched runs (batch_size > 1) "
            "would pass an empty drivers dict to model_fn. Use batch_size=1 "
            "or fan out by scenario_id inside model_fn."
        )
        raise ValueError(msg)

    # Remainder: run the un-folded scenarios under the winning (engine, batch).
    for batch_sids in _chunks(sids[len(folded) :], resolved_size):  # type: ignore[type-var]
        _process_one(batch_sids, engine=winner_engine)

    # Report peak_rss_mb as the delta over the baseline RSS at loop entry.
    if peak_rss is not None and baseline_rss is not None:
        peak_rss_mb = max(0, peak_rss - baseline_rss) / (1024 * 1024)
    else:
        peak_rss_mb = None

    # Finalise: extract output per aggregator (tidy partitioned-vector outputs).
    final: dict[str, Any] = {}
    for alias, agg in zip(aliases, aggregations, strict=True):
        raw = agg.extract_output(accumulators[alias])
        if isinstance(agg, _Partitioned) and hasattr(agg.inner, "batch_reduce"):
            raw = _tidy_partitioned_vector(raw, by=agg.by, alias=alias)
        final[alias] = raw

    return ScenarioResult(
        aggregations=final,
        plan_sha=plan_sha,
        n_scenarios=len(sids),
        batch_size=resolved_size,
        batch_size_resolution=resolution,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=peak_rss_mb,
        n_batches=batch_idx,
        sink_dir=sink_dir if return_full_grid else None,
        selection=selection,
    )


__all__ = ["BatchSnapshot", "ScenarioID", "for_each_scenario"]
