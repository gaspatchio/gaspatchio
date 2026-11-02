# bindings/python/gaspatchio/scenarios/_aggregated.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: run_aggregated -- policy-axis aggregate driver (bounded memory).
# ABOUTME: Mirrors for_each_scenario's loop over policy row-slices; AggregatedResult.

"""Bounded-memory per-period aggregation for a single (non-scenario) run."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import polars as pl

from gaspatchio._dtypes import with_integers_as_i64
from gaspatchio._identity import source_sha_of
from gaspatchio.frame._across_rows import one_batch_of_several
from gaspatchio.frame.base import _frame_over_the_book
from gaspatchio.scenarios._aggregators import Count
from gaspatchio.scenarios._audit import (
    VERSIONS_WITHHELD,
    audit_destination,
    checked_versions,
    default_audit_path,
    graph_fingerprint_map,
    library_versions,
    model_points_fingerprint,
    write_audit,
)
from gaspatchio.scenarios._auto_batch import bounded_seed_size, size_to_budget
from gaspatchio.scenarios._batch import _collect_batch, book_in_hand
from gaspatchio.scenarios._fold import (
    _extract_outputs,
    _fold_vector,
    _inner,
    refuse_a_period_fold_over_policies,
    refuse_a_policy_fold_over_periods,
    refuse_a_sum_over_a_wide_integer,
)
from gaspatchio.scenarios._for_each import agreed_graph, note_graph
from gaspatchio.scenarios._metric import _Partitioned, refuse_a_multi_level_over

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Mapping, Sequence

    from gaspatchio.engines.protocol import Producer
    from gaspatchio.frame import ActuarialFrame


@dataclass(frozen=True)
class AggregatedResult:
    """Typed output of :func:`run_aggregated`. Aliases are attribute-accessible.

    ``n_policies`` is the number of policies the model valued -- the rows the
    totals were folded over -- on every engine. A model that chooses which
    policies it values (``af.filter``, a semi or anti join) values fewer than
    the book holds, and the count says so.

    ``audit_path`` is set when :func:`run_aggregated` was asked for an audit
    record and is ``None`` otherwise; it points at the JSON sidecar written by
    :mod:`gaspatchio.scenarios._audit`, the same document a scenario run
    writes.

    ``produced_by`` is set when a second engine folded the book
    (``run_aggregated(engine=...)``) and is ``None`` on the Polars path. The
    totals arrive without the rows that made them, so this is what keeps them
    placeable: the engine, every version it ran under, the graph it ran and
    the book it read. The audit record writes it out.
    """

    aggregations: dict[str, Any]
    n_policies: int
    n_periods: int
    batch_size: int
    wall_time_s: float
    peak_rss_mb: float | None
    audit_path: Path | None = None
    produced_by: Producer | None = None

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        # Only consulted when normal attribute lookup misses (i.e. for aliases).
        if name.startswith("__"):
            raise AttributeError(name)
        aggregations = object.__getattribute__(self, "aggregations")
        if name in aggregations:
            return aggregations[name]
        raise AttributeError(name)


def _alias_of(agg: Any) -> str:  # noqa: ANN401
    """Return the alias set on an aggregator (handles _Partitioned), else raise."""
    if isinstance(agg, _Partitioned):
        return agg.alias
    name: str | None = getattr(agg, "alias_", None)
    if not name:
        msg = f"Aggregator {type(agg).__name__} needs .alias(name) for run_aggregated."
        raise ValueError(msg)
    return name


def _reject_multi_level_over(aggregations: Sequence[Any]) -> None:
    """Reject a multi-level quantile under ``.over()`` before any computation.

    ``Quantile`` and ``PeriodQuantile`` produce a ``{level: ...}`` dict — there is
    no single-column tidy form, so the tidy reshape used for all other vector
    ``.over()`` aggregators cannot represent it. ``.over()`` already refuses
    one where it is written; this is the same refusal for an engine that
    reads the aggregation contract through ``engines.aggregation``.
    """
    for agg in aggregations:
        if isinstance(agg, _Partitioned):
            refuse_a_multi_level_over(agg.inner, agg.alias)


def _reject_scenario_axis_only(aggregations: Sequence[Any]) -> None:
    """Reject aggregators only well-defined on the scenario axis.

    ``Count`` (counts scenarios) and ``ArgMin``/``ArgMax`` (need scenario identity)
    are inapplicable to the policy axis, with or without ``.over()``. ``.over()``
    partitioning itself IS supported (handled in _fold_batch).
    """
    for agg in aggregations:
        inner = agg.inner if isinstance(agg, _Partitioned) else agg
        if getattr(inner, "requires_scenario_id", False):
            msg = (
                f"{type(inner).__name__} needs a scenario axis (scenario_id) "
                "and is not applicable to run_aggregated; use for_each_scenario."
            )
            raise ValueError(msg)
        if isinstance(inner, Count):
            msg = (
                "Count counts scenarios and is not applicable to run_aggregated (the "
                "policy axis has no scenarios); use Sum/Period* aggregators instead."
            )
            raise ValueError(msg)  # noqa: TRY004 — usage error on the policy axis
        if getattr(inner, "within_expr_override", None) is not None:
            # No allowlist is sound here: batch-invariance requires the
            # within-expression to be decomposable w.r.t. the outer fold
            # (Sum.of(additive), Min.of(min-decomposable), ...), which cannot
            # be verified on an arbitrary Polars expression — Min.of(sum) and
            # Sum.of(mean) are both silently batch-size-dependent.
            msg = (
                f"{type(inner).__name__}.of(...) is not supported on the policy "
                "axis: the within-expression reduces each batch to a single "
                "value, so the result depends on batch_size (e.g. "
                "Min.of(col.sum()) returns a different number for 1 batch than "
                "for 2). Compute the quantity as a model column and aggregate "
                "it directly, or use .of() on the scenario axis "
                "(for_each_scenario), where each scenario is reduced whole."
            )
            raise ValueError(msg)
        within = getattr(inner, "within", "sum")
        if within != "sum":
            msg = (
                f"{type(inner).__name__}({getattr(inner, 'column', None)!r}, "
                f"within={within!r}) "
                "is not supported on the policy axis: within= reduces each "
                "scenario's policies before the statistic is taken across "
                "scenarios, and run_aggregated has no scenarios, so it would "
                "be dropped and the statistic taken over the policies. Leave "
                "within= out here, or use it on the scenario axis "
                "(for_each_scenario), where each scenario is reduced whole."
            )
            raise ValueError(msg)


def _max_period_len(frame: pl.DataFrame) -> int:
    """Longest List(Float64) length across all such columns (0 if none / all-null).

    Guards the n_periods scan against an all-null List(Float64) column, whose
    ``list.len().max()`` is None (which would crash ``int(None)``).
    """
    list_cols = [c for c, dt in frame.schema.items() if dt == pl.List(pl.Float64)]
    if not list_cols:
        return 0
    val = frame.select(
        pl.max_horizontal([pl.col(c).list.len() for c in list_cols]).max()
    ).item()
    return int(val) if val is not None else 0


def _fold_batch(
    proj: pl.DataFrame,
    aggregations: Sequence[Any],
    accumulators: dict[str, Any],
) -> None:
    """Fold one collected batch frame into every aggregator's accumulator."""
    refuse_a_policy_fold_over_periods(proj.schema, aggregations)
    refuse_a_period_fold_over_policies(proj.schema, aggregations)
    refuse_a_sum_over_a_wide_integer(proj, aggregations)
    for agg in aggregations:
        alias = _alias_of(agg)
        if hasattr(_inner(agg), "batch_reduce"):
            _fold_vector(proj, agg, accumulators, alias)
        else:
            _fold_one_value_per_policy(proj, agg, accumulators, alias)


def _fold_one_value_per_policy(
    proj: pl.DataFrame,
    agg: Any,  # noqa: ANN401 -- an aggregator of one value per policy, of any kind
    accumulators: dict[str, Any],
    alias: str,
) -> None:
    """Fold one aggregator's column, one value per policy, into its accumulator.

    ``.over(by)`` groups the batch by its partition columns and folds each
    group into a fresh accumulator before merging, so a partition is one data
    point per policy and never one per batch.
    """
    inner = _inner(agg)
    if isinstance(agg, _Partitioned):
        # One data point per policy, never per batch. Iterate partitions;
        # each add_batch reduces its column in Polars where supported.
        scalar = cast("Any", inner)
        batch_state = {
            key if isinstance(key, tuple) else (key,): scalar.add_batch(
                scalar.create_accumulator(), group.get_column(scalar.column)
            )
            for key, group in proj.group_by(agg.by)
        }
        accumulators[alias] = agg.merge_accumulators(accumulators[alias], batch_state)
    else:
        accumulators[alias] = agg.add_batch(
            accumulators[alias], proj.get_column(agg.column)
        )


def _fold_per_policy(
    frame: pl.DataFrame,
    aggregations: Sequence[Any],
    accumulators: dict[str, Any],
) -> None:
    """Fold a batch's per-policy columns into aggregators of one value per policy.

    The half of :func:`_fold_batch` an engine may ask for. Its per-period
    half explodes the batch's per-period columns and groups them by period
    in Polars; an engine that reduces on its own device computes those
    partials itself, and a door that offered this half would let it ask
    Polars for them instead -- which is the one thing an engine exists not to
    do. So a per-period kind is refused here, before anything is folded.

    Raises:
        TypeError: If any aggregator folds per period (it has ``batch_reduce``).

    """
    for agg in aggregations:
        inner = _inner(agg)
        if hasattr(inner, "batch_reduce"):
            msg = (
                f"{type(inner).__name__} folds one value per period, and this fold "
                "takes aggregators of one value per policy: reduce its partial "
                "where the column was computed and hand it to the aggregator's "
                "own add_input"
            )
            raise TypeError(msg)
    refuse_a_policy_fold_over_periods(frame.schema, aggregations)
    refuse_a_sum_over_a_wide_integer(frame, aggregations)
    for agg in aggregations:
        _fold_one_value_per_policy(frame, agg, accumulators, _alias_of(agg))


def _check_period_origin(af: ActuarialFrame, align: str | None) -> None:
    """Reject inception-aligned (per-policy-origin) timelines unless align='duration'.

    Index-aligned summation is calendar-correct only when policies share a period
    origin (from_calendar_grid / per_policy_grid). from_inception's index is policy
    DURATION; summing across policies then mixes calendar periods.

    Args:
        af: The ActuarialFrame returned by the first batch of ``model_fn``.
        align: The ``align`` argument passed to :func:`run_aggregated`.

    Raises:
        ValueError: When the schedule kind is ``"from_inception"`` and
            ``align != "duration"``.

    """
    schedule = getattr(af, "_projection", None)
    kind = getattr(schedule, "_kind", None)
    if kind == "from_inception" and align != "duration":
        msg = (
            "Inception-aligned timeline: the period index is policy DURATION, not "
            "calendar time, so summing across policies mixes calendar periods. Pass "
            "align='duration' to aggregate by duration, or rebuild the projection with "
            "a shared valuation grid (per_policy=False, its horizon a number "
            "where the book runs in batches) for calendar totals."
        )
        raise ValueError(msg)


def _check_document_origin(document: Mapping[str, Any], align: str | None) -> None:
    """Reject an inception-aligned artifact unless align='duration', as a frame is.

    The file door folds a document and has no frame to ask, so it asks the
    document, which records the same fact in two places, and either is
    enough. A ``schedule`` assumption whose payload is ``from_inception``
    (the artifact specification, section 15) is carried only where a node
    reads the schedule; the ``projection_set`` call is always carried, and
    section 11.1.1's schedule form writes ``start`` only where the schedule
    has a shared start date and ``until`` only where it is a per-policy
    horizon grid -- so a schedule with neither, and no ``valuation_date``, is
    anchored on each policy's own inception. What is refused and why are the
    frame's: the period index is then policy duration rather than calendar
    time, and a total across policies at one index mixes calendar months.

    Args:
        document: The executable artifact about to be folded.
        align: ``"duration"`` where the caller asked for totals by duration.

    Raises:
        ValueError: When the projection is ``from_inception`` and ``align`` is
            not ``"duration"``.

    """
    inception = any(
        isinstance(entry, dict)
        and entry.get("kind") == "schedule"
        and isinstance(entry.get("payload"), dict)
        and entry["payload"].get("kind") == "from_inception"
        for entry in document.get("assumptions") or ()
    ) or any(
        _anchored_on_inception(node.get("expr"))
        for node in document.get("nodes") or ()
        if isinstance(node, dict)
    )
    if inception and align != "duration":
        msg = (
            "Inception-aligned timeline: this artifact's schedule is "
            "from_inception, so the period index is policy DURATION, not "
            "calendar time, and summing across policies mixes calendar periods. "
            "Aggregate by duration with align='duration' (--align duration at "
            "the command line), or re-export the model with a shared valuation "
            "grid (per_policy=False, its horizon a number where the book runs "
            "in batches) for calendar totals."
        )
        raise ValueError(msg)


def _anchored_on_inception(tree: object) -> bool:
    """Return whether an operation tree declares an axis from each policy's inception.

    A ``projection_set`` call in section 11.1.1's schedule form -- it names
    ``schedule_source_sha`` -- with no shared ``start``, no horizon ``until``
    and no ``valuation_date``. Searched through the whole tree, because the
    call stands inside every column the declaration mints.
    """
    if isinstance(tree, list):
        return any(_anchored_on_inception(one) for one in tree)
    if not isinstance(tree, dict):
        return False
    attrs = tree.get("attrs")
    if (
        tree.get("op") == "call"
        and tree.get("name") == "projection_set"
        and isinstance(attrs, dict)
        and attrs.get("schedule_source_sha") is not None
        and all(attrs.get(key) is None for key in ("start", "until", "valuation_date"))
    ):
        return True
    return any(_anchored_on_inception(value) for value in tree.values())


def _resolve_auto(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
) -> tuple[int, ActuarialFrame, pl.DataFrame, int]:
    """Run one seed batch (~10 % of policies, ≥1), measure per-policy peak, return B.

    The seed batch is REAL work — its ActuarialFrame and collected DataFrame are
    returned to the caller to be folded exactly once (not re-run). ``B`` is the
    largest batch that fits the memory budget (:func:`size_to_budget`); there is no
    working-set cap — the policy axis is monotonic, so the budget alone governs.

    Args:
        model_fn: The same callable passed to :func:`run_aggregated`.
        model_points: Full policy table.

    Returns:
        ``(B, seed_af, seed_proj, seed_size)`` where ``B`` is the resolved batch
        size for the remainder, ``seed_af`` is the unreduced ``ActuarialFrame``
        (needed by the origin guard), ``seed_proj`` is the collected seed frame
        (ready to fold), and ``seed_size`` is the number of rows in the seed.

    """
    n_policies = model_points.height
    seed_size = bounded_seed_size(n_policies)
    seed = model_points.slice(0, seed_size)
    with one_batch_of_several(
        runner="run_aggregated",
        n_policies=n_policies,
        batch_size="auto",
        first=seed_size,
        batch=seed,
    ):
        seed_af = model_fn(_frame_over_the_book(seed.lazy(), judged=True))
    seed_proj, seed_peak = _collect_batch(seed_af, engine="streaming")
    # per-cell cost: bytes per policy. Floor the measured peak with the materialised
    # frame size: a fast seed collect can complete between RSS samples (seed_peak==0),
    # which would otherwise collapse per_cell to 1 byte and size the WHOLE dataset
    # into one batch — defeating the bounded-memory guarantee.
    effective_peak = max(seed_peak, int(seed_proj.estimated_size()))
    per_cell = max(1, effective_peak // max(1, seed_size))
    return int(size_to_budget(per_cell, n_policies)), seed_af, seed_proj, seed_size


def _plan_canonical_form(
    aliases: Sequence[str],
    aggregations: Sequence[Any],
) -> dict[str, Any]:
    """Return what stands in for a plan on the policy axis.

    A scenario run has a ``ScenarioRun`` to name -- shocks, base tables,
    aggregations, seed. A plain aggregation has no such object: what it was
    asked to do IS the list of aggregators, so that list, each under its own
    alias, is the recipe the record names and the bytes the run's
    ``source_sha`` is taken over.
    """
    return {
        "kind": "run_aggregated",
        "aggregations": dict(
            sorted(
                (alias, agg.canonical_form())
                for alias, agg in zip(aliases, aggregations, strict=True)
            )
        ),
    }


def _with_audit_record(  # noqa: PLR0913
    result: AggregatedResult,
    *,
    audit: bool | Path,
    aliases: Sequence[str],
    aggregations: Sequence[Any],
    model_points: pl.DataFrame,
    stamps: set[str | None] | None,
    versions: Literal["recorded", "withheld"] = "recorded",
) -> AggregatedResult:
    """Return ``result``, having written its audit record where one was asked for."""
    if audit is False:
        return result

    plan_canonical_form = _plan_canonical_form(aliases, aggregations)
    source_sha = source_sha_of(plan_canonical_form)
    path = audit if isinstance(audit, Path) else default_audit_path(source_sha, None)

    write_audit(
        path,
        named_by_the_run=not isinstance(audit, Path),
        source_sha=source_sha,
        plan_canonical_form=plan_canonical_form,
        run_metadata={
            "wall_time_s": result.wall_time_s,
            "n_policies": result.n_policies,
            "n_periods": result.n_periods,
            "batch_size": result.batch_size,
            **library_versions(versions),
            **_engine_metadata(result.produced_by, versions=versions),
        },
        aggregator_outputs=result.aggregations,
        aggregator_identity=plan_canonical_form["aggregations"],
        graph_fingerprint=agreed_graph(stamps),
        # No scenario axis, so no scenario to key a map by: the one helper
        # both writers go through answers None rather than inventing a shape.
        graph_fingerprint_by_scenario=graph_fingerprint_map(None),
        input_data_fingerprint=model_points_fingerprint(model_points),
    )
    return replace(result, audit_path=path)


def _engine_metadata(
    produced_by: Producer | None,
    *,
    versions: Literal["recorded", "withheld"] = "recorded",
) -> dict[str, Any]:
    """Return what a second engine adds to the record's run metadata.

    Nothing on the Polars path, so a record that engine never touched reads
    exactly as it always has. Where an engine folded the book, the record
    names it and every version it reports running under -- for the JAX
    engine, its jax and jaxlib, the platform and the extension's digest --
    beside the book as that engine digested it, and whatever the run wanted
    said: a total that moved between two quarters moved either because the
    book did or because what produced it did, and only the second of those is
    otherwise invisible. Withheld, ``engine_versions`` is section 6.1's form,
    as the library's own keys are.
    """
    if produced_by is None:
        return {}
    return {
        "engine": produced_by.engine,
        "engine_versions": (
            {"omitted": VERSIONS_WITHHELD}
            if versions == VERSIONS_WITHHELD
            else dict(produced_by.versions)
        ),
        "inputs_digest": produced_by.inputs_digest,
        "engine_notes": list(produced_by.notes),
    }


def _aggregated_on_engine(  # noqa: PLR0913
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
    aggregations: Sequence[Any],
    aliases: Sequence[str],
    *,
    engine: str,
    batch_size: int | Literal["auto"],
    align: Literal["calendar", "duration"] | None,
    audit: bool | Path,
    versions: Literal["recorded", "withheld"] = "recorded",
) -> AggregatedResult:
    """Build the model once, export it, and let a second engine fold the book.

    The frame door's route, taken for a fold: ``model_fn`` runs once over the
    whole book and builds a plan without computing it, and the frame hands
    over what it hands ``collect(engine=...)`` -- the executable artifact and
    the columns it arrived with -- through the one method both doors call.
    So a setup phase that collected the model points and derived a column
    before building the frame folds here exactly as it collects there, and
    the result's ``inputs_digest`` describes the same book whichever door
    ran. The engine never sees the model's source and this function never
    sees a computed value -- so what reaches the audit record is the
    engine's answer about the artifact, with nothing of Polars' in it.

    The engine is found, and asked whether it folds, before the model is
    built: an engine that cannot aggregate is a refusal that costs the reader
    nothing. The alignment guard is Polars' own and reads the same frame.
    """
    from gaspatchio.engines import engine_named  # noqa: PLC0415 -- reached lazily
    from gaspatchio.engines.aggregation import aggregating  # noqa: PLC0415 -- as above

    started = time.perf_counter()
    folding = aggregating(engine_named(engine), engine)
    af = model_fn(_frame_over_the_book(model_points))
    _check_period_origin(af, align)
    document, inputs = af._for_an_engine()  # noqa: SLF001 -- the frame door's own
    result = folding.aggregate(
        document,
        inputs,
        aggregations,
        batch=None if batch_size == "auto" else int(batch_size),
    )
    # The door's own wall rather than the engine's: building the plan and
    # exporting it are part of what the reader waited for.
    result = replace(result, wall_time_s=time.perf_counter() - started)
    stamp = (
        result.produced_by.graph_fingerprint
        if result.produced_by is not None
        else str(document.get("graph_fingerprint") or "") or None
    )
    return _with_audit_record(
        result,
        audit=audit,
        aliases=aliases,
        aggregations=aggregations,
        model_points=model_points,
        stamps={stamp} if audit is not False else None,
        versions=versions,
    )


def run_aggregated(  # noqa: PLR0913
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame | pl.LazyFrame,
    aggregations: Sequence[Any],
    *,
    batch_size: int | Literal["auto"] = "auto",
    align: Literal["calendar", "duration"] | None = None,
    audit: bool | str | os.PathLike[str] = False,
    engine: str | None = None,
    versions: Literal["recorded", "withheld"] = "recorded",
) -> AggregatedResult:
    """Run ``model_fn`` over policy batches; fold each to per-period aggregates.

    ``aggregations`` is a list of aliased aggregators (same shape as
    ``for_each_scenario``); vector ``Period*`` aggregators yield per-period
    ndarrays -- numpy masked arrays, masked (``None`` in ``.tolist()``) at a
    period that held no value -- and scalar aggregators (e.g. ``Sum``) yield
    portfolio scalars, ``None`` where they saw no value.

    **Reproducibility contract.** At one stated integer ``batch_size`` a run
    answers the same bits every time. Across batch sizes the answers agree
    only to floating-point reassociation: each batch totals its own slice of
    the policies and the slices are then combined, so a different batch size
    groups the sum over policies differently and can move the last bits of a
    ``Sum``, ``Mean``, ``Variance``, ``Std`` or ``Period*`` figure (the
    sketch-based quantiles, ``Min``, ``Max`` and counts do not move). Over a
    whole-number column none of them moves: its totals, counts and totals of
    squares are exact, and each figure is the double nearest the exact one,
    or a total past ``i64`` is refused by name. Under
    ``"auto"`` the size follows the memory budget, so state an integer
    ``batch_size`` where a figure must reproduce to the bit on another
    machine. The scenario axis does not have this limit: a scenario run folds
    each scenario on its own rows, in the run's order, and is bit-identical
    at every batch size.

    Args:
        model_fn: Callable accepting an ``ActuarialFrame`` and returning one.
        model_points: Polars DataFrame of policy data, or a LazyFrame, which is
            collected first; rows are sliced into batches.
        aggregations: Sequence of aliased aggregators (call ``.alias(name)``).
            An aggregator may be partitioned with ``agg.over(by)`` (one or more
            column names) to split results by a low-cardinality dimension: scalar
            aggregators yield a ``{*by, alias}`` DataFrame; ``Period*`` aggregators
            yield a tidy ``{*by, period, alias}`` DataFrame under that alias.
            ``Count``, ``ArgMin``, and ``ArgMax`` are not supported on the policy
            axis; a multi-level ``Quantile`` or ``PeriodQuantile`` under
            ``.over()`` is not yet supported.
        batch_size: Number of policies per batch. ``"auto"`` sizes to the
            cgroup-aware memory budget via :func:`size_to_budget` — the largest
            policy batch whose predicted peak fits the budget (a bounded seed
            measures per-policy cost; the policy axis is monotonic, so the
            budget alone governs, with no working-set cap).
        align: Alignment mode guard. Pass ``"duration"`` for inception-aligned
            (per-policy-origin) timelines; otherwise a ``ValueError`` is raised
            when inception-aligned output is detected.
        audit: Whether to write the run's audit record beside its output, and
            where. The record is the one a scenario run writes -- the recipe
            the run folded, the identity taken over it, what the run cost,
            and the numbers it produced -- so "show me how the per-policy
            reserves became the reported total" has a document on this axis
            too. ``True`` writes to
            ``./gaspatchio_audit/<run_id>.audit.json``; a path -- a ``Path``,
            a string or any ``os.PathLike`` -- writes to exactly that path;
            ``False`` (the default) writes nothing. The path lands on
            ``result.audit_path``.
        engine: Which engine folds the book. ``None`` (the default) is the
            Polars path described above, unchanged. The name of a registered
            engine that aggregates -- ``"jax"``, with the JAX extra installed
            -- builds the model once over the whole book without computing
            it, and hands that engine what ``collect(engine=...)`` hands it
            -- the executable artifact and the columns the frame arrived with
            -- with these aggregators. It folds each batch as it is
            computed, on its own device, and lets it go before the next,
            never building a per-policy frame: a book of ten million
            policies comes back as its totals, and what is held at once is
            one batch's values beside the accumulators. The same
            aggregators are
            accepted and refused as here; ``Period*`` kinds whose partial is
            not a closed form (``PeriodQuantile``, ``PeriodMedian``,
            ``PeriodCTE``) are refused by name, pointing back to Polars.
            The answer agrees with Polars under the specification's
            agreement rule (section 11.1.12), where the only permitted
            difference is the order floating-point additions were made in. An
            integer ``batch_size`` becomes the engine's batch, ``"auto"`` lets
            the engine size batches from its compiled program, and ``align``
            and ``audit`` behave as they do on Polars -- the audit record
            also names the engine, every version it ran under and the device
            it ran on, because
            totals that arrive without their rows are placeable only by what
            produced them. A refusal raises
            :class:`~gaspatchio.engines.report.EngineRefusal` and returns
            nothing, and an engine that cannot aggregate at all is refused by
            name. The worked example is in the JAX engine's README rather
            than here: it needs the extra, and this module's examples run
            without it.

        versions: What the audit record states about the library the run
            ran under, as :meth:`ScenarioRun.run` takes it: ``"recorded"``,
            the default, or ``"withheld"``, which writes each version key --
            and, on a second engine, its ``engine_versions`` -- as
            ``{"omitted": "withheld"}``, for a record committed as a golden.
            Never the default; any other value is refused before the run.

    Returns:
        :class:`AggregatedResult` with per-alias outputs plus metadata.

    Raises:
        EngineRefusal: Where ``engine`` names an engine that refuses the
            fold, or one that cannot aggregate at all.

    """
    model_points = book_in_hand(model_points, "run_aggregated")
    if model_points.height == 0:
        msg = "model_points is empty."
        raise ValueError(msg)

    _reject_scenario_axis_only(aggregations)
    _reject_multi_level_over(aggregations)
    checked_versions(versions)
    record = audit_destination(audit)
    aliases = [_alias_of(a) for a in aggregations]
    if len(set(aliases)) != len(aliases):
        msg = f"Aggregator aliases must be unique; got {aliases}."
        raise ValueError(msg)

    if engine is not None:
        return _aggregated_on_engine(
            model_fn,
            model_points,
            aggregations,
            aliases,
            engine=engine,
            batch_size=batch_size,
            align=align,
            audit=record,
            versions=versions,
        )

    # A wide integer column is judged over the book, not over each batch:
    # read as Int64 here where every value in the book fits, and kept in
    # its width where one does not. Each batch is handed on as a plan, so
    # the frame's door does not judge it again over the batch's values alone
    # (section 10).
    model_points = with_integers_as_i64(model_points)
    n_policies = model_points.height
    # The policies the model valued, which is the rows the folds saw: a model
    # that selects (``af.filter``, a semi or anti join) values fewer than the
    # book holds, and a total is a total over those.
    valued = 0
    accumulators: dict[str, Any] = {
        a: agg.create_accumulator()
        for a, agg in zip(aliases, aggregations, strict=True)
    }

    started = time.perf_counter()
    n_periods = 0
    max_batch_peak = 0
    stamps: set[str | None] | None = set() if record is not False else None

    if batch_size == "auto":
        # --- auto path: run+measure the seed, fold it, then loop the remainder ---
        resolved, seed_af, seed_proj, seed_size = _resolve_auto(model_fn, model_points)
        # Origin guard runs on the seed ActuarialFrame (schedule lives on the frame).
        _check_period_origin(seed_af, align)
        note_graph(seed_af, stamps)
        # Account for seed's n_periods contribution.
        n_periods = max(n_periods, _max_period_len(seed_proj))
        # Fold the seed EXACTLY ONCE.
        valued += seed_proj.height
        _fold_batch(seed_proj, aggregations, accumulators)
        del seed_proj
        # Loop the REMAINDER (rows [seed_size, n_policies)) in steps of resolved.
        loop_start = seed_size
    else:
        # --- explicit-int path: unchanged, loop from 0 ---
        resolved = int(batch_size)
        loop_start = 0

    # The first batch's size says whether the book is cut at all: under
    # "auto" the seed is the first batch, and a seed short of the book means
    # the remainder runs in batches of its own.
    first = bounded_seed_size(n_policies) if batch_size == "auto" else resolved
    for start in range(loop_start, n_policies, resolved):
        batch = model_points.slice(start, resolved)
        with one_batch_of_several(
            runner="run_aggregated",
            n_policies=n_policies,
            batch_size=batch_size,
            first=first,
            batch=batch,
        ):
            out_af = model_fn(_frame_over_the_book(batch.lazy(), judged=True))
        if batch_size != "auto" and start == 0:
            # explicit-int: guard on the first batch's frame
            _check_period_origin(out_af, align)
        note_graph(out_af, stamps)
        proj, batch_peak = _collect_batch(out_af, engine="streaming")
        max_batch_peak = max(max_batch_peak, batch_peak)
        # n_periods = max list length across ALL List(Float64) columns (all-null safe).
        n_periods = max(n_periods, _max_period_len(proj))
        valued += proj.height
        _fold_batch(proj, aggregations, accumulators)
        del proj

    result = AggregatedResult(
        aggregations=_extract_outputs(aliases, aggregations, accumulators),
        n_policies=valued,
        n_periods=n_periods,
        batch_size=resolved,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=(max_batch_peak / (1024 * 1024)) if max_batch_peak else None,
    )
    return _with_audit_record(
        result,
        audit=record,
        aliases=aliases,
        aggregations=aggregations,
        model_points=model_points,
        stamps=stamps,
        versions=versions,
    )


__all__ = [
    "AggregatedResult",
    "run_aggregated",
]
