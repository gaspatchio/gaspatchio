# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: for_each_scenario -- bounded-memory scenario-loop primitive.
# ABOUTME: Public; ScenarioRun.run() is a thin delegate on top of this.

"""Bounded-memory scenario loop, reducing each aggregator within each scenario.

:func:`for_each_scenario` runs ``model_fn`` once per scenario (or per batch).
For each batch and each aggregator, the loop computes the aggregator's
within-scenario reduction (``agg.within_expr()``) grouped by
``[scenario_id, *partition_keys]``, then folds each reduced row into the
aggregator's accumulator state. Peak memory stays bounded regardless of
the number of scenarios.

Supported ``scenarios`` shapes:

* ``list[ScenarioID]`` -- ids only; ``model_fn(af, *, tables, drivers)``
  receives the un-shocked base tables as ``tables``.
* ``dict[ScenarioID, list[Shock]]`` -- per-scenario shock recipes, run
  against the frame-only model as it was reconciled, ``model_fn(af)``. Each
  read the model makes of a table a shock names is answered with that table
  stacked per scenario, and each ``column=`` shock rewrites its model-point
  column at the frame door (:mod:`gaspatchio.scenarios._binding`,
  :mod:`gaspatchio.scenarios._columns`).
* ``dict[ScenarioID, dict[str, Any]]`` -- per-scenario driver kwargs
  forwarded to ``model_fn(drivers=...)``. Drivers are forwarded only when
  ``batch_size=1``; for ``batch_size>1`` users with drivers must fan out
  by ``scenario_id`` inside ``model_fn``.

When ``master_seed`` is set, a deterministic per-scenario seed is derived
via sha256: a shocks plan hands it to the model as the ``rng_seed`` column
at any batch size; the ids and drivers shapes inject it into
``drivers['rng_seed']`` at ``batch_size=1``.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import inspect
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from loguru import logger

from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio._identity import SHA256_PREFIX
from gaspatchio._scenario_reads import bound_reads
from gaspatchio._semantic.ir import BinOp, Call, WhenThen
from gaspatchio.frame._across_rows import ON_A_SCENARIO_PLAN, frame_is_not_the_book
from gaspatchio.frame.execution import run_model
from gaspatchio.frame.graph.fingerprint import graph_fingerprint
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.mortality._mortality_table import mortality_recipe, recipe_sha
from gaspatchio.scenarios._audit import as_path
from gaspatchio.scenarios._auto_batch import memory_budget_bytes
from gaspatchio.scenarios._batch import _collect_batch, _safe_rss_bytes
from gaspatchio.scenarios._binding import (
    TableBinder,
    keeps_the_axis,
    reads_the_axis,
)
from gaspatchio.scenarios._columns import (
    check_column_conditions_select,
    check_columns,
    check_columns_read,
    columns_the_folds_read,
    shock_columns,
    widened_by_the_plan,
)
from gaspatchio.scenarios._fold import _extract_outputs
from gaspatchio.scenarios._fold import fold_scenario_batch as _fold_batch
from gaspatchio.scenarios._metric import Aggregator, _Partitioned
from gaspatchio.scenarios._result import (
    ScenarioResult,
    SelectionDecision,
)
from gaspatchio.scenarios._search import _search_batches
from gaspatchio.scenarios._spill import safe_write_parquet
from gaspatchio.scenarios._targets import check_shock_targets
from gaspatchio.scenarios._validate import (
    check_no_duplicate_ids,
    check_non_empty,
)
from gaspatchio.scenarios._with_scenarios import (
    composed_alone,
    cross_the_axis,
    scenario_axis,
)

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
    from contextlib import AbstractContextManager
    from pathlib import Path

    import polars as pl

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.assumptions import Table
    from gaspatchio.frame import ActuarialFrame
    from gaspatchio.frame.calculations import SourceSpan
    from gaspatchio.frame.graph.graph_builder import CalcGraph
    from gaspatchio.scenarios.shocks import Shock

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


def _chunks(seq: list[ScenarioID], size: int) -> Iterator[list[ScenarioID]]:
    """Yield successive ``size``-sized slices of ``seq``."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# How many of an earlier grid's batch files a refusal names before counting.
_BATCHES_NAMED: Final = 3


def _refuse_a_grid_directory_holding_a_grid(grid_dir: Path) -> None:
    """Refuse a ``sink_dir`` already holding another run's full grid.

    Batches are named by their index, ``batch_0000.parquet`` on, so a second
    run into one directory writes over the first run's batches one by one and
    leaves any it does not reach: the directory would hold two runs' grids
    read as one, with nothing to say which batch is whose. Refused before
    anything runs.

    Raises:
        FileExistsError: If ``grid_dir`` holds a ``batch_*.parquet`` file.

    """
    if not grid_dir.is_dir():
        return
    held = sorted(path.name for path in grid_dir.glob("batch_*.parquet"))
    if not held:
        return
    shown = ", ".join(held[:_BATCHES_NAMED])
    if len(held) > _BATCHES_NAMED:
        shown += f" and {len(held) - _BATCHES_NAMED} more"
    msg = (
        f"return_full_grid=True would write this run's grid into {grid_dir}, which "
        f"already holds an earlier run's batches ({shown}). Batches are named by "
        "their index, so this run would write over them one by one and leave any "
        "it does not reach, and the directory would read as one grid made of two "
        "runs. Nothing was run. Pass a sink_dir of this run's own, or remove the "
        "earlier batches first."
    )
    raise FileExistsError(msg)


def _write_batch_parquet(frame: pl.DataFrame, path: Path) -> None:
    """Sort by scenario_id only if present (the policy axis has none), then write."""
    if "scenario_id" in frame.columns:
        frame = frame.sort("scenario_id")
    safe_write_parquet(frame, path)


def _graph_stamp(
    frame: ActuarialFrame, read_as: Mapping[str, str] | None = None
) -> str | None:
    """Return the fingerprint of the calculation ``frame`` carries, or None.

    None is the answer where the frame holds a column the graph vocabulary
    has no name for -- a category, a struct, a column of nothing but nulls,
    all of which a plain in-force file produces. Refusing to name such a
    type is right when the question is "export this model"; it is the wrong
    answer to "what did this run fold", because the run has already
    finished and its numbers are real. The record says less, in the shape
    the rest of the run's identity already uses: null exactly where the run
    could not determine it.

    ``read_as`` names each shocked copy a scenario composed alone read with
    the table it copies (:meth:`TableBinder.read_as`). The stamp is taken
    with every read of a copy named as the model named it, so a shock
    reaches its scenario's figure through the table's content alone (the
    artifact specification, section 13.2): a shock that leaves the rates as
    they were leaves BASE's figure, and a shocked scenario's figure is the
    one the model gives run over the shocked rates under the table's own
    name.
    """
    try:
        if not read_as:
            return frame.graph.fingerprint()
        graph = _reads_named_as(fold(frame, refuse_unnamed=False), read_as)
        return f"{SHA256_PREFIX}{graph_fingerprint(graph).hex()}"
    except UnmappedDtypeError as exc:
        logger.debug("graph fingerprint not taken for this frame: {}", exc)
        return None


def _reads_named_as(graph: CalcGraph, read_as: Mapping[str, str]) -> CalcGraph:
    """Return ``graph`` with every read of a renamed table naming its original.

    A table read (``lookup``) and a mortality read (``mortality.at``) carry
    the table's name; a mortality read also carries its wrapper's recipe,
    which states the name, and it is taken again over the original. Nothing
    else in the graph names a table, and its content hash is not touched.
    """
    renamed = copy.copy(graph)
    renamed.op_trees = {
        node_id: _tree_named_as(tree, read_as)
        for node_id, tree in graph.op_trees.items()
    }
    renamed.selection = tuple(
        replace(step, tree=_tree_named_as(step.tree, read_as))
        for step in graph.selection
    )
    return renamed


def _tree_named_as(node: OpNode, read_as: Mapping[str, str]) -> OpNode:
    """Return one op tree with each read of a renamed table naming its original."""
    match node:
        case Call(name=name, args=args, attrs=attrs):
            held = dict(attrs)
            table = held.get("table")
            if isinstance(table, str) and table in read_as:
                held["table"] = read_as[table]
                if name == "mortality.at":
                    held["mortality"] = _mortality_named_as(held)
            return Call(
                name,
                tuple(_tree_named_as(arg, read_as) for arg in args),
                tuple((key, held[key]) for key, _ in attrs),
            )
        case BinOp(op=op, left=left, right=right):
            return BinOp(
                op, _tree_named_as(left, read_as), _tree_named_as(right, read_as)
            )
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            return WhenThen(
                _tree_named_as(cond, read_as),
                _tree_named_as(then, read_as),
                _tree_named_as(otherwise, read_as),
            )
        case _:
            return node


def _mortality_named_as(attrs: Mapping[str, object]) -> str:
    """Return a mortality read's recipe digest, taken over the table it names."""
    dimensions = str(attrs.get("dimensions") or "")
    return recipe_sha(
        mortality_recipe(
            table_name=str(attrs["table"]),
            dimensions=[one for one in dimensions.split(",") if one],
            fingerprint=str(attrs["table_fingerprint"]),
            age_basis=attrs.get("age_basis"),
            structure=attrs.get("structure"),
            select_period=attrs.get("select_period"),
        )
    )


def note_graph(frame: ActuarialFrame, stamps: set[str | None] | None) -> None:
    """Record the fingerprint of the model this batch actually ran.

    ``stamps`` is ``None`` where no audit record was asked for, and nothing
    is computed: fingerprinting is structure-only and cheap, but a run that
    nobody asked to describe itself should not be able to fail while trying.
    The run that *did* ask must not be able to fail either, which is why the
    stamp itself may be None -- see :func:`_graph_stamp`.
    """
    if stamps is not None:
        stamps.add(_graph_stamp(frame))


def agreed_graph(stamps: Iterable[str | None] | None) -> str | None:
    """Return the one graph they all folded, or None where they did not agree.

    The stamps offered are one per *thing that folds its own calculation*:
    one per policy batch on the policy axis, and one per scenario on the
    scenario axis. That distinction is the whole of this function's honesty.
    The policy axis slices a book, and slicing a book does not move the
    digest -- model-point columns are read, never content-hashed -- so its
    batches agree and the run is stamped. The scenario axis composes a
    basis per scenario, and an assumption table's content hash is a section
    of the graph fingerprint by design (the artifact specification, section
    12.4), so a run that shocks a table its model reads folds one
    calculation per scenario and no single stamp is true of it.

    Answering over scenarios rather than over batches is what keeps this
    free of the batch boundary: a two-scenario shocked run reads the same
    here whether the memory search put both scenarios in one batch or one
    in each. Where the scenarios did fold one graph -- an unshocked run, or
    shocks that reach no lookup -- the stamp is the run's, as before. None
    is also the answer where a stamp could not be taken at all.
    """
    distinct = set(stamps) if stamps is not None else set()
    if len(distinct) != 1:
        return None
    (only,) = distinct
    return only


def _note_scenario_graph(
    graphs: dict[ScenarioID, str | None] | None,
    scenario_id: ScenarioID,
    stamp: str | None,
) -> None:
    """Record the calculation one scenario ran, refusing to overwrite a difference.

    One scenario is one basis, so its fingerprint is well-defined and the
    loop reads it once. Should two readings of the same scenario ever
    disagree, that is a defect being witnessed rather than a choice to make:
    the entry becomes None, because a record that says nothing about a
    scenario is recoverable and one that says the wrong thing is not.
    """
    if graphs is None:
        return
    if scenario_id in graphs and graphs[scenario_id] != stamp:
        graphs[scenario_id] = None
        return
    graphs[scenario_id] = stamp


def _note_scenario_graphs(  # noqa: PLR0913 -- the batch, how to compose one, and what it read
    graphs: dict[ScenarioID, str | None] | None,
    batch_sids: list[ScenarioID],
    projection: ActuarialFrame,
    compose_one: Callable[[ScenarioID], ActuarialFrame],
    *,
    alone: bool,
    read_as: Mapping[ScenarioID, Mapping[str, str]] | None = None,
) -> None:
    """Record which calculation each scenario of this batch ran.

    ``alone`` is True on a shocks plan, where a scenario's calculation is the
    one it builds composed on its own -- the reconciled model over the book,
    with no axis and only that scenario's own shocked tables and columns --
    so even a batch of one is composed again: its batch carries the axis
    and the stacked tables, which no scenario run alone would.

    A batch of one scenario has already built exactly the composition that
    scenario runs alone, so its projection is read straight off. A batch of
    several folds one calculation over a basis stacked from all of them,
    and that composite is nobody's: it is not what any of those scenarios
    would fold on its own, and it moves when the batch boundary moves. So
    each scenario's own composition is built once more -- the calculation
    only, never collected -- and stamped. That is the price of an entry
    that means the same thing however the run was cut, and it is paid only
    where a record was asked for.

    ``compose_one`` re-registers this scenario's stacked assumption tables
    under their run-time names, so it must be called after the batch has
    been collected, never between building the batch and collecting it.
    ``read_as`` is what each composition left of the shocked copies it read
    (:func:`_graph_stamp`), filled as ``compose_one`` runs.
    """
    if graphs is None:
        return
    if len(batch_sids) == 1 and not alone:
        _note_scenario_graph(graphs, batch_sids[0], _graph_stamp(projection))
        return
    for sid in batch_sids:
        try:
            own = compose_one(sid)
        except Exception as exc:  # noqa: BLE001 - the run's numbers are already in
            logger.debug("scenario {} could not be composed alone: {}", sid, exc)
            _note_scenario_graph(graphs, sid, None)
        else:
            named = None if read_as is None else read_as.get(sid)
            _note_scenario_graph(graphs, sid, _graph_stamp(own, named))


@dataclass(frozen=True, slots=True)
class _BatchRecipe:
    """What every batch of this run is composed from, held once.

    The frame a batch runs is built from four things that do not move
    between batches -- the scenario definitions, their shape, the base
    tables and the master seed -- and only the scenario ids change. Holding
    them together is what lets the run's own batches and the
    single-scenario compositions the record's per-scenario map needs be
    built by one piece of code instead of two that could drift apart.

    ``site`` is where the record should say the scenario axis arrived, for
    a caller running this plan on a modeller's behalf rather than from
    their own script; None walks the stack out to their ``.run(...)``.

    ``axis`` is every scenario of the run, resolved once here rather than
    per batch. A run of ten thousand scenarios at ``batch_size=1`` composes
    ten thousand times, and rebuilding the list on each of them would put
    an O(n) step inside an O(n) loop for a value that does not move.

    ``bases`` collects, as the shocks plan composes, the content of every
    table a shock moved: what the run record says each shock was applied to.
    """

    scenarios: list[ScenarioID] | dict[ScenarioID, Any]
    shape: Literal["ids", "shocks", "drivers"]
    base_tables: dict[str, Table] | None
    master_seed: int | None
    site: SourceSpan | None = None
    axis: tuple[ScenarioID, ...] = ()
    bases: dict[str, dict[str, Any]] = field(default_factory=dict)
    axis_read: list[bool] = field(default_factory=list)
    folds_read: frozenset[str] | None = None
    widened: list[frozenset[str]] = field(default_factory=list)
    read_as: dict[ScenarioID, dict[str, str]] = field(default_factory=dict)

    def compose(
        self,
        af: ActuarialFrame,
        batch_sids: list[ScenarioID],
        model_fn: Callable[..., ActuarialFrame | None],
    ) -> ActuarialFrame:
        """Return the frame ``model_fn`` builds for ``batch_sids``; nothing collects.

        The axis the record stamps is the run's, not this batch's. A batch
        boundary is how the run was cut for memory, and letting it reach
        the calculation's identity would make every batched run look like
        several different calculations -- which is the opposite of what
        :func:`agreed_graph` is asked.

        On a shocks plan the model is the frame-only model the modeller
        reconciled. The plan rewrites the columns its shocks name at the
        frame door and answers the model's reads of the tables its shocks
        name through a :class:`TableBinder`; it never hands the model a
        table or a driver.
        """
        if self.shape != "shocks":
            af_batch = cross_the_axis(
                af,
                batch_sids,  # type: ignore[arg-type]
                site=self.site,
                axis=self.axis or batch_sids,  # type: ignore[arg-type]
            )
            drivers = _build_drivers(
                self.scenarios, batch_sids, self.shape, self.master_seed
            )
            with _on_the_scenario_axis(af, crossed(af_batch, batch_sids)):
                return cast(
                    "ActuarialFrame",
                    model_fn(af_batch, tables=self.base_tables or {}, drivers=drivers),
                )
        scenarios = cast("dict[ScenarioID, list[Shock]]", self.scenarios)
        axis = self.axis or tuple(batch_sids)
        af_batch = scenario_axis(
            af,
            batch_sids,  # type: ignore[arg-type]
            axis=axis,  # type: ignore[arg-type]
            seeds=self._seeds(batch_sids),
            run_seeds=self._seeds(list(axis)),
            site=self.site,
        )
        if not self.widened:
            self.widened.append(widened_by_the_plan(af, scenarios))
        plans_own = shock_columns(
            af_batch,
            {sid: scenarios[sid] for sid in batch_sids},
            stacked=True,
            site=self.site,
            widened=self.widened[0],
        )
        binder = TableBinder.for_batch(scenarios, batch_sids, self.base_tables)
        with (
            bound_reads(binder),
            _on_the_scenario_axis(af, crossed(af_batch, batch_sids)),
        ):
            projected = run_model(model_fn, af_batch)
        # A shock moves a table only through the model's read of it; one no
        # read reached would leave its scenario equal to BASE.
        binder.check_reached(scenarios)
        # The same of a column shock: one no line of the model reads.
        check_columns_read(
            projected,
            {sid: scenarios[sid] for sid in batch_sids},
            plans_own=plans_own,
            folds_read=self.folds_read,
        )
        keeps_the_axis(projected)
        self.bases.update(binder.bases())
        if not self.axis_read and reads_the_axis(
            projected, bound=binder.built_names(), plans_own=plans_own
        ):
            self.axis_read.append(True)
        return projected

    def compose_alone(
        self,
        af: ActuarialFrame,
        sid: ScenarioID,
        model_fn: Callable[..., ActuarialFrame | None],
    ) -> ActuarialFrame:
        """Return the frame one scenario of a shocks plan builds on its own.

        The reconciled model over the book, with no scenario axis, reading
        each table this scenario shocks with that scenario's shocks applied
        and every other table as the model wrote it, its shocked columns
        rewritten for it alone. BASE's composition is therefore the
        standalone model's, and its fingerprint is that model's fingerprint.

        A model that reads the scenario axis itself -- dispatching on
        ``scenario_id`` to pick a curve -- folds a different calculation per
        scenario with nothing shocked, so composing it with no axis would
        hand every scenario BASE's identity. Such a model is composed alone
        over a one-scenario axis instead, which names the scenario it is.
        """
        scenarios = cast("dict[ScenarioID, list[Shock]]", self.scenarios)
        seeds = self._seeds([sid])
        alone = (
            scenario_axis(
                af,
                [sid],  # type: ignore[arg-type]
                axis=(sid,),  # type: ignore[arg-type]
                seeds=seeds,
                run_seeds=seeds,
                site=self.site,
            )
            if self.axis_read
            else composed_alone(
                af, seed=None if seeds is None else seeds[0], site=self.site
            )
        )
        shock_columns(alone, {sid: scenarios[sid]}, stacked=False, site=self.site)
        binder = TableBinder.for_alone(scenarios, sid, self.base_tables)
        with bound_reads(binder), _on_the_scenario_axis(af):
            composed = run_model(model_fn, alone)
        self.read_as[sid] = binder.read_as()
        return composed

    def _seeds(self, sids: list[ScenarioID]) -> list[int] | None:
        """Return each scenario's derived seed, or None for an unseeded plan."""
        if self.master_seed is None:
            return None
        return [_per_scenario_seed(self.master_seed, sid) for sid in sids]


def crossed(
    af_batch: ActuarialFrame, batch_sids: list[ScenarioID]
) -> pl.LazyFrame | None:
    """Return the crossed frame a batch of several scenarios hands the model.

    Where the batch holds more than one scenario, a frame the model builds
    over values that left the frame is judged against it, as a batch
    runner's policy cut is (spec section 13.2): the collected frame holds
    every scenario's copy of the book, so a read across its rows answers
    from all of them. One scenario's batch is that scenario's whole book,
    and nothing is held.
    """
    return af_batch._df if len(batch_sids) > 1 else None  # noqa: SLF001 -- the plan's own frame


def _on_the_scenario_axis(
    book: ActuarialFrame, batch: pl.LazyFrame | None = None
) -> AbstractContextManager[None]:
    """Return the block a scenario plan calls the model in.

    The plan's frame is every scenario's copy of the book, so a read across
    its rows answers from every scenario together at any batch size, and is
    refused (``frame/_across_rows.py``). A scenario composed alone for its
    record is held to the same rule: the plan's numbers come off the axis.

    ``book`` is the frame the plan was handed, and its columns are the
    book's: what the frame was told by a runner that watched the run begin,
    or else what it arrived with. A frame the model builds inside the block
    keeps them, so its record says which of its columns the book never had.

    ``batch`` is the crossed frame of a batch holding several scenarios
    (:func:`crossed`), which a frame the model builds is judged against.
    """
    columns = book._book_columns or book._bare_arrivals  # noqa: SLF001 -- the plan's own frame
    return frame_is_not_the_book(
        on_a_scenario_axis=True, cut=ON_A_SCENARIO_PLAN, batch=batch, book=columns
    )


def _run_one_batch(
    af: ActuarialFrame,
    batch_sids: list[ScenarioID],
    model_fn: Callable[..., ActuarialFrame | None],
    *,
    recipe: _BatchRecipe,
    engine: Literal["in-memory", "streaming"],
) -> tuple[pl.DataFrame, int, float, ActuarialFrame]:
    """Build + collect one batch; return (frame, peak_bytes, wall_s, projection).

    The projected ``ActuarialFrame`` comes back beside the collected data
    because it is what carries the calculation this batch actually ran; the
    caller is where the decision to record that lives.
    """
    af_proj = recipe.compose(af, batch_sids, model_fn)
    # Pass the requested engine unchanged: auto is not the in-memory floor.
    started = time.perf_counter()
    proj_eager, peak = _collect_batch(af_proj, engine=engine)
    return proj_eager, peak, time.perf_counter() - started, af_proj


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


def refuse_a_door_model(model_fn: Callable[..., object]) -> None:
    """Refuse a shocks plan's model that still takes the plan's old door.

    A shocks plan runs the frame-only model the modeller reconciled -- the
    ``main(af)`` ``gspio run-model`` runs -- and reaches its tables through
    their reads. A function that requires ``tables`` or ``drivers`` keyword
    arguments was written to be handed them, which a shocks plan no longer
    does, so it is refused naming the move rather than called and left to
    fail on a missing argument.

    Raises:
        TypeError: ``model_fn`` requires a ``tables`` or ``drivers`` keyword.

    """
    try:
        parameters = inspect.signature(model_fn).parameters
    except (TypeError, ValueError):
        return
    door = [
        name
        for name in ("tables", "drivers")
        if name in parameters
        and parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        and parameters[name].default is inspect.Parameter.empty
    ]
    if not door:
        return
    named = getattr(model_fn, "__name__", type(model_fn).__name__)
    msg = (
        f"{named} takes {' and '.join(door)}=, the door a scenario plan used to "
        "hand shocked tables through. A shocks plan now runs the model you "
        "reconciled unchanged: pass the frame-only model, "
        "plan.run(af, model.main), and the plan answers the model's own reads "
        "of every table its shocks name. A model still guarding its lookups "
        "with a scenario_id check keeps working: the guard is false on the "
        "model's own table."
    )
    raise TypeError(msg)


def for_each_scenario(  # noqa: C901, PLR0912, PLR0913, PLR0915
    af: ActuarialFrame,
    scenarios: list[ScenarioID]
    | dict[ScenarioID, list[Shock]]
    | dict[ScenarioID, dict[str, Any]],
    model_fn: Callable[..., ActuarialFrame | None],
    *,
    aggregations: Sequence[Aggregator | _Partitioned],
    base_tables: dict[str, Table] | None = None,
    batch_size: int | Literal["auto"] = "auto",
    target_memory_fraction: float = 0.5,
    return_full_grid: bool = False,
    sink_dir: str | os.PathLike[str] | None = None,
    master_seed: int | None = None,
    progress: bool = False,
    on_batch: Callable[[BatchSnapshot], None] | None = None,
    plan_sha: str = "",
    capture_graph_fingerprint: bool = False,
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
    * ``dict[ScenarioID, list[Shock]]`` -- per-scenario shock recipes, run
      against the frame-only model. Its reads of each table a shock names
      are answered with that table stacked per scenario, and ``column=``
      shocks rewrite their model-point column before it runs.
    * ``dict[ScenarioID, dict[str, Any]]`` -- per-scenario driver kwargs
      forwarded to ``model_fn(drivers=...)``. Forwarded only at
      ``batch_size=1``; for ``batch_size>1`` callers must fan out by
      ``scenario_id`` inside ``model_fn``.

    When ``master_seed`` is set, a deterministic per-scenario seed is derived
    via sha256. A shocks plan hands it to the model as the ``rng_seed``
    column, at any batch size; the ids and drivers shapes inject it into
    ``drivers['rng_seed']`` at ``batch_size=1`` only.

    Model function contract:
        On a shocks plan, ``model_fn(af)`` -- the model as reconciled; one
        that requires ``tables=`` or ``drivers=`` is refused, naming the
        move. On the ids and drivers shapes,
        ``model_fn(af, *, tables, drivers) -> ActuarialFrame``.

    Notes:
        On the ids and drivers shapes, per-scenario drivers and the derived
        ``drivers["rng_seed"]`` are delivered to ``model_fn`` only when each
        batch contains a single scenario. A ``ValueError`` is raised when
        ``master_seed`` is set or the drivers-dict shape is used together
        with ``batch_size > 1`` there.

        ArgMin/ArgMax aggregators are special-cased: they require
        ``(scenario_id, value)`` tuples rather than bare values.
        Partitioned aggregators (via ``.over(by)``) wrap their inner
        value in a ``(partition_key, value)`` tuple.

        ``return_full_grid=True`` writes each batch's full projection --
        every scenario, policy and column -- to
        ``<sink_dir>/batch_<idx>.parquet``. ``sink_dir`` is a ``Path``, a
        string or any ``os.PathLike``, and ``result.sink_dir`` is the ``Path``
        it names. The grid goes to disk, never into memory, and only where the
        caller says: without ``sink_dir`` the run raises ``ValueError`` before
        it starts.

        ``capture_graph_fingerprint`` asks the loop to record which
        calculation each *scenario* actually ran, for
        ``result.graph_fingerprint_by_scenario``, and the one every
        scenario agreed on for ``result.graph_fingerprint``. It is off by
        default because a run nobody asked to describe itself should not
        be able to fail while trying, and because it is not free: where a
        batch holds more than one scenario, each of those scenarios has
        its own composition built once more to be stamped -- the
        calculation only, never collected. See :func:`agreed_graph` for
        when the scalar is ``None``.

    Cross-join semantics:
        Every scenario sees every policy. The base ActuarialFrame is
        cross-joined with the batch's ``scenario_id`` column before
        ``model_fn`` runs, so a 1000-policy frame in 100 scenarios yields
        a 100,000-row projection. Custom aggregators receive per-scenario
        within-reductions over the full policy universe -- they do not see
        policy[i] paired with scenario[i]. To produce per-scenario distinct
        values, either:

        * let scenarios differ via table or column shocks (the standard
          pattern),
        * read ``pl.col("scenario_id")`` inside ``model_fn`` and branch on it,
          or
        * use a drivers-dict shape and read ``drivers["scenario_id"]`` (at
          ``batch_size=1``).

    """
    shape = _classify(scenarios)
    if shape == "shocks":
        check_shock_targets(
            cast("dict[ScenarioID, list[Shock]]", scenarios), base_tables or None
        )
        refuse_a_door_model(model_fn)
        check_columns(
            cast("dict[ScenarioID, list[Shock]]", scenarios), af.get_column_order()
        )
        if af._df is not None:  # noqa: SLF001 -- the book the run values
            check_column_conditions_select(
                cast("dict[ScenarioID, list[Shock]]", scenarios),
                af._df,  # noqa: SLF001
            )

    sids = list(scenarios)

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

    if af._df is None:  # noqa: SLF001
        msg = "ActuarialFrame has no underlying frame; cannot run scenarios."
        raise ValueError(msg)

    # Taken as a Path where it comes in: a string or any os.PathLike names a
    # directory as well as a Path does.
    grid_dir = as_path(sink_dir)
    if return_full_grid:
        if grid_dir is None:
            msg = (
                "return_full_grid=True writes every scenario's full projection "
                "to parquet, one file per batch, and needs a directory to write "
                "it to: pass sink_dir=Path('...'). The grid is not held in "
                "memory -- keeping it off the heap is what the option is for. "
                "Leave return_full_grid False to keep only the aggregations."
            )
            raise ValueError(msg)
        _refuse_a_grid_directory_holding_a_grid(grid_dir)
        grid_dir.mkdir(parents=True, exist_ok=True)

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
    folded: list[
        ScenarioID
    ] = []  # scenarios already projected+folded (probe + remainder)
    batch_idx = 0
    selection: SelectionDecision | None = None
    resolution: Literal["manual", "auto_search"]
    winner_engine: Literal["in-memory", "streaming"]
    graphs: dict[ScenarioID, str | None] | None = (
        {} if capture_graph_fingerprint else None
    )
    recipe = _BatchRecipe(
        scenarios=scenarios,
        shape=shape,
        base_tables=base_tables,
        master_seed=master_seed,
        axis=tuple(sids),
        folds_read=columns_the_folds_read(aggregations),
    )

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
        nonlocal peak_rss, baseline_rss, batch_idx
        proj_eager, batch_peak, batch_wall, af_proj = _run_one_batch(
            af,
            batch_sids,
            model_fn,
            recipe=recipe,
            engine=engine,
        )
        # After the collect, never before it: composing a scenario alone
        # re-registers this run's stacked assumption tables under one
        # scenario, and the batch's own numbers must already be in hand.
        _note_scenario_graphs(
            graphs,
            batch_sids,
            af_proj,
            (
                (lambda sid: recipe.compose_alone(af, sid, model_fn))
                if shape == "shocks"
                else (lambda sid: recipe.compose(af, [sid], model_fn))
            ),
            alone=shape == "shocks",
            read_as=recipe.read_as,
        )
        # Pool-reuse floor: a batch that materialises an N-byte frame holds at
        # least N live bytes at peak, even when the allocator served it entirely
        # from retained pools and the RSS sampler saw no growth. In a process
        # that has already run other collects, delta-over-baseline reads ~0 for
        # such a batch (observed live: a probe measured 0 MB, so the gate
        # predicted 0 for every larger rung and let an unaffordable probe
        # through). Mirrors the policy axis, which floors its seed measurement
        # with the frame size for the same reason (_spill/_aggregated).
        batch_peak = max(batch_peak, int(proj_eager.estimated_size()))
        _fold_batch(
            proj_eager,
            aliases=aliases,
            aggregations=aggregations,
            accumulators=accumulators,
            order=batch_sids,
        )
        if return_full_grid and grid_dir is not None:
            _write_batch_parquet(
                proj_eager, grid_dir / f"batch_{batch_idx:04d}.parquet"
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
            _snap_outputs = _extract_outputs(aliases, aggregations, accumulators)
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

    if batch_size == "auto":

        def measure(
            size: int, engine: Literal["streaming", "in-memory"]
        ) -> tuple[int, float]:
            return _process_one(sids[len(folded) : len(folded) + size], engine=engine)

        # A seed reaches a shocks plan's model as a column at any batch size;
        # the three-argument door forwards drivers and seeds at one only.
        forced_one = shape == "drivers" or (
            master_seed is not None and shape != "shocks"
        )
        selection = _search_batches(
            len(sids),
            measure,
            forced_one=forced_one,
            budget_mb=(
                memory_budget_bytes(target_memory_fraction) / 1024**2
                if len(sids) > 1 or forced_one
                else 0.0
            ),
        )
        resolved_size, winner_engine = selection.batch, selection.engine
        resolution = "auto_search"
    else:
        resolved_size, winner_engine, resolution = (
            int(batch_size),
            "in-memory",
            "manual",
        )

    # Explicit batch_size>1 with master_seed / drivers-dict is unsupported (manual path;
    # the auto forced-b1 path above already resolved to 1).
    if master_seed is not None and shape != "shocks" and resolved_size > 1:
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
    for batch_sids in _chunks(sids[len(folded) :], resolved_size):
        _process_one(batch_sids, engine=winner_engine)

    # Report peak_rss_mb as the delta over the baseline RSS at loop entry.
    if peak_rss is not None and baseline_rss is not None:
        peak_rss_mb = max(0, peak_rss - baseline_rss) / (1024 * 1024)
    else:
        peak_rss_mb = None

    return ScenarioResult(
        aggregations=_extract_outputs(aliases, aggregations, accumulators),
        plan_sha=plan_sha,
        n_scenarios=len(sids),
        batch_size=resolved_size,
        batch_size_resolution=resolution,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=peak_rss_mb,
        n_batches=batch_idx,
        sink_dir=grid_dir if return_full_grid else None,
        selection=selection,
        graph_fingerprint=agreed_graph(None if graphs is None else graphs.values()),
        graph_fingerprint_by_scenario=graphs,
        bases=dict(sorted(recipe.bases.items())) if shape == "shocks" else None,
    )


__all__ = ["BatchSnapshot", "ScenarioID", "for_each_scenario"]
