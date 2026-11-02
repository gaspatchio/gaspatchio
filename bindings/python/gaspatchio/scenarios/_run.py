# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: ScenarioRun typed plan dataclass + identity + immutable composers + .run().
# ABOUTME: Audit chain rolls up shocks, base_tables, aggregations, master_seed.

"""ScenarioRun - typed, auditable stochastic-run plan."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

from gaspatchio._identity import source_sha_of
from gaspatchio.scenarios._audit import (
    as_path,
    audit_destination,
    checked_versions,
    default_audit_path,
    graph_fingerprint_map,
    library_versions,
    model_points_fingerprint,
    write_audit,
)
from gaspatchio.scenarios._config import parse_aggregations, parse_scenario_config
from gaspatchio.scenarios._for_each import _classify, for_each_scenario
from gaspatchio.scenarios._metric import _Partitioned
from gaspatchio.scenarios._targets import check_shock_targets
from gaspatchio.scenarios.shocks import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
    TimeConditionalShock,
)

if TYPE_CHECKING:
    import os
    from collections.abc import Callable

    from gaspatchio.assumptions import Table
    from gaspatchio.frame import ActuarialFrame
    from gaspatchio.scenarios._for_each import BatchSnapshot
    from gaspatchio.scenarios._metric import Aggregator
    from gaspatchio.scenarios._result import ScenarioResult
    from gaspatchio.scenarios.shocks import Shock


def _alias_of(agg: Any) -> str | None:  # noqa: ANN401
    """Return the alias of an aggregator or _Partitioned wrapper, if any.

    Raises:
        TypeError: If the alias is set to something other than a string. An
            alias names the output it writes, so it is a name; a number given
            as one is refused as what it is, rather than as no alias at all.

    """
    # _Partitioned exposes ``alias`` as a direct dataclass attribute (str).
    # _BaseAggregator exposes ``alias_`` (str | None) and ``alias`` is a method.
    alias_attr = getattr(agg, "alias_", None)
    if alias_attr is None:
        # _Partitioned: alias is a str attribute (not callable).
        alias = getattr(agg, "alias", None)
        alias_attr = None if callable(alias) else alias
    if alias_attr is None or isinstance(alias_attr, str):
        return alias_attr
    msg = (
        "An aggregator's alias names the output it writes, so .alias() takes "
        f"a string; {type(agg).__name__} was given {alias_attr!r}."
    )
    raise TypeError(msg)


@dataclass(frozen=True)
class ScenarioRun:
    """Reusable, auditable scenario plan over the model you reconciled.

    Captures shocks, aggregation recipes, and (optionally) the base tables
    it states it shocks and a master seed. Identity surface
    (``canonical_form``, ``source_sha``, ``describe``) mirrors Schedule /
    Curve / MortalityTable. Run via ``.run(af, model.main)`` or write it
    down with ``to_yaml`` for governance archives; every shock kind writes
    and reads back to the same ``source_sha()``.

    Every shock names exactly one target. ``table=`` names an assumption
    table by the name its ``Table`` was built with: inside the run, the
    model's own reads of that table are answered with it shocked per
    scenario. ``column=`` names a model-point column -- a valuation rate, an
    expense, a solved premium -- rewritten per scenario before the model
    runs. The model itself is not changed.

    ``base_tables`` is optional. Given, it is the plan's statement of the
    tables it shocks, keyed by each table's own name, and the run refuses a
    model whose table of that name differs by content.

    ``aggregations`` is a tuple of aggregator instances (each carrying its
    own alias via ``.alias(name)``). Every aggregator must have an explicit
    alias and aliases must be unique across the tuple; both invariants are
    enforced at construction time.
    """

    shocks: dict[str, list[Shock]]
    base_tables: dict[str, Table] = field(default_factory=dict)
    aggregations: tuple[Aggregator | _Partitioned, ...] = field(default=())
    master_seed: int | None = None

    def __post_init__(self) -> None:
        if not self.aggregations:
            msg = "ScenarioRun.aggregations must be a non-empty tuple of aggregators."
            raise ValueError(msg)
        aliases: list[str] = []
        for agg in self.aggregations:
            alias = _alias_of(agg)
            if not alias:
                msg = (
                    f"Every aggregator in ScenarioRun.aggregations must have an "
                    f"explicit .alias(name); got aggregator "
                    f"{type(agg).__name__} without alias."
                )
                raise ValueError(msg)
            aliases.append(alias)
        if len(aliases) != len(set(aliases)):
            seen: set[str] = set()
            dups: set[str] = set()
            for a in aliases:
                if a in seen:
                    dups.add(a)
                else:
                    seen.add(a)
            msg = f"ScenarioRun.aggregations has duplicate aliases: {sorted(dups)}"
            raise ValueError(msg)
        for key, table in self.base_tables.items():
            if key != table.name:
                msg = (
                    f"base_tables names {table.name!r} under the key {key!r}. A "
                    "shock names a table by the name its Table was built with, "
                    "and the run matches the model's reads by that name, so the "
                    f"key is the table's own name: base_tables={{{table.name!r}: ...}}."
                )
                raise ValueError(msg)
        # A plan whose shock names no target, two targets, a table its stated
        # base tables do not hold, or a time condition on a column is refused
        # here, before it has an identity.
        if _classify(self.shocks) == "shocks":
            check_shock_targets(self.shocks, self.base_tables or None)

    def canonical_form(self) -> dict[str, Any]:
        """Return the JSON-encodable canonical descriptor (every dict sorted)."""
        aliases_to_agg: dict[str, dict[str, Any]] = {}
        for agg in self.aggregations:
            alias = _alias_of(agg)
            assert alias is not None  # noqa: S101 - guaranteed by __post_init__
            aliases_to_agg[alias] = agg.canonical_form()
        return {
            "kind": "ScenarioRun",
            "shocks": {
                sid: [s.canonical_form() for s in shocks]
                for sid, shocks in sorted(self.shocks.items())
            },
            "base_tables": {
                name: table.canonical_form()
                for name, table in sorted(self.base_tables.items())
            },
            "aggregations": dict(sorted(aliases_to_agg.items())),
            "master_seed": self.master_seed,
        }

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the plan's canonical_form."""
        return source_sha_of(self.canonical_form())

    def describe(self) -> str:
        """Return a short human-readable summary including the plan SHA."""
        n_shocks = sum(len(v) for v in self.shocks.values())
        aliases = sorted(a for a in (_alias_of(agg) for agg in self.aggregations) if a)
        return (
            f"ScenarioRun(scenarios={len(self.shocks)}, "
            f"total_shocks={n_shocks}, "
            f"tables={sorted(self.base_tables.keys())}, "
            f"aggregations={aliases}, "
            f"master_seed={self.master_seed}, "
            f"sha={self.source_sha()})"
        )

    def with_extra_shocks(self, more: dict[str, list[Shock]]) -> ScenarioRun:
        """Return a new plan with additional scenarios merged in."""
        return replace(self, shocks={**self.shocks, **more})

    def with_extra_aggregations(
        self,
        *more: Aggregator | _Partitioned,
    ) -> ScenarioRun:
        """Return a new plan with additional aggregators appended."""
        return replace(self, aggregations=self.aggregations + tuple(more))

    def with_master_seed(self, seed: int) -> ScenarioRun:
        """Return a new plan stamped with the given master seed."""
        return replace(self, master_seed=seed)

    def run(  # noqa: PLR0913
        self,
        af: ActuarialFrame,
        model_fn: Callable[[ActuarialFrame], ActuarialFrame | None],
        *,
        batch_size: int | Literal["auto"] = "auto",
        target_memory_fraction: float = 0.5,
        return_full_grid: bool = False,
        sink_dir: str | os.PathLike[str] | None = None,
        progress: bool = False,
        on_batch: Callable[[BatchSnapshot], None] | None = None,
        audit: bool | str | os.PathLike[str] = False,
        versions: Literal["recorded", "withheld"] = "recorded",
    ) -> ScenarioResult:
        """Run the plan via ``for_each_scenario``.

        The result's ``plan_sha`` field is stamped with this plan's
        ``source_sha()`` so downstream consumers can verify input identity.
        When ``audit`` is truthy, a JSON audit sidecar is written and the
        path stored on ``result.audit_path``:

        * ``audit=True`` (default location): the sidecar is written to
          ``<sink_dir>/<run_id>.audit.json`` when ``sink_dir`` is provided,
          otherwise to ``./gaspatchio_audit/<run_id>.audit.json``.
        * ``audit=<path>``: the sidecar is written to that exact path, given
          as a ``Path``, a string or any ``os.PathLike``.
        * ``audit=False`` (default): no sidecar is written.

        ``run_id`` is ``<utc-iso-timestamp>_<short-sha>`` (filename-safe).

        ``versions`` is what the sidecar states about the library the run
        ran under. ``"recorded"``, the default, writes the core and
        extension versions, the extension's digest, Polars, Python, the
        platform and ddsketch. ``"withheld"`` writes each of those keys as
        ``{"omitted": "withheld"}``, for a record committed as a golden,
        whose strings must not move with the machine that wrote it; it is
        never the default. Any other value is refused before the run starts.

        ``return_full_grid=True`` writes each batch's full projection to
        ``<sink_dir>/batch_<idx>.parquet``; it needs ``sink_dir`` and raises
        ``ValueError`` without one. The grid is never held in memory.
        ``sink_dir`` is a ``Path``, a string or any ``os.PathLike``.

        Model contract:
            ``model_fn`` is the frame-only model you reconciled -- the
            ``main(af)`` that ``gspio run-model`` runs -- called once per
            batch as ``model_fn(af)``, unchanged:

            * ``af`` is the model points cross-joined with the batch's
              ``scenario_id`` column, with every ``column=`` shock already
              applied to its column for each scenario's rows.
            * The model's own ``Table.lookup`` and ``MortalityTable.at``
              reads of a table a shock names are answered with that table
              shocked per scenario; every other read is left as written.
            * A seeded plan (``master_seed``) hands each scenario its seed as
              the ``rng_seed`` column, at any batch size.

            Return the ``ActuarialFrame`` the model built (``None`` keeps the
            input frame), carrying whatever columns the aggregators need and
            the ``scenario_id`` column. A model still guarding its lookups with
            ``"scenario_id" in table.dimensions`` keeps working: the guard is
            false on the model's own table. A function that requires the old
            ``tables=``/``drivers=`` keywords is refused, naming the move; the
            three-argument form stays on ``for_each_scenario`` for the ids and
            drivers shapes.

        Refusals, each naming the next move: a shock on a table no read of
        the model reached (after the first batch, naming the tables it did
        read); a ``column=`` the model points do not hold; a model table that
        differs by content from the one ``base_tables`` states; a frame that
        dropped the scenario axis; ``to_dataframe()`` of a shocked table
        inside the run, whose rows differ by scenario.

        Streaming (``progress`` / ``on_batch``) is a **live observation
        channel** and does not change the run's identity: ``source_sha()``,
        ``canonical_form()``, and the audit sidecar are unaffected by
        ``on_batch``. To persist a convergence trace, write it from the
        callback. Under ``batch_size="auto"`` the batch boundaries (and thus
        the trace) are not reproducible.

        """
        checked_versions(versions)
        plan_sha = self.source_sha()
        out_dir = as_path(sink_dir)
        record = audit_destination(audit)
        result = for_each_scenario(
            af,
            scenarios=self.shocks,  # type: ignore[arg-type]
            model_fn=model_fn,
            aggregations=self.aggregations,
            base_tables=self.base_tables,
            batch_size=batch_size,
            target_memory_fraction=target_memory_fraction,
            return_full_grid=return_full_grid,
            sink_dir=out_dir,
            master_seed=self.master_seed,
            progress=progress,
            on_batch=on_batch,
            plan_sha=plan_sha,
            capture_graph_fingerprint=record is not False,
        )

        # plan_sha is already set by for_each_scenario; re-stamp defensively.
        result = replace(result, plan_sha=plan_sha)

        # Audit sidecar (opt-in).
        if record is not False:
            audit_path = self._write_audit_sidecar(
                audit=record,
                af=af,
                result=result,
                sink_dir=out_dir,
                plan_sha=plan_sha,
                versions=versions,
            )
            result = replace(result, audit_path=audit_path)

        return result

    def _write_audit_sidecar(  # noqa: PLR0913 — the record states one more setting the run was given
        self,
        *,
        audit: bool | Path,
        af: ActuarialFrame,
        result: ScenarioResult,
        sink_dir: Path | None,
        plan_sha: str,
        versions: Literal["recorded", "withheld"],
    ) -> Path:
        """Write the audit JSON sidecar; return the path it was written to."""
        path = (
            audit if isinstance(audit, Path) else default_audit_path(plan_sha, sink_dir)
        )

        write_audit(
            path,
            named_by_the_run=not isinstance(audit, Path),
            source_sha=plan_sha,
            plan_canonical_form=self.canonical_form(),
            run_metadata={
                "wall_time_s": result.wall_time_s,
                "n_scenarios": result.n_scenarios,
                "batch_size": result.batch_size,
                "batch_size_resolution": result.batch_size_resolution,
                "selection_engine": (
                    result.selection.engine if result.selection else None
                ),
                "selection_reason": (
                    result.selection.reason if result.selection else None
                ),
                "selection_probed": [
                    {
                        "batch": p.batch,
                        "engine": p.engine,
                        "per_sc_s": p.per_sc_s,
                        "peak_mb": p.peak_mb,
                        "fits": p.fits,
                    }
                    for p in (result.selection.probed if result.selection else [])
                ],
                **library_versions(versions),
                "master_seed": self.master_seed,
            },
            aggregator_outputs=result.aggregations,
            aggregator_identity=self.canonical_form()["aggregations"],
            graph_fingerprint=result.graph_fingerprint,
            graph_fingerprint_by_scenario=graph_fingerprint_map(
                result.graph_fingerprint_by_scenario
            ),
            input_data_fingerprint=model_points_fingerprint(af.collect()),
            bases=result.bases,
        )
        return path

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-serialisable dict recipe for this plan.

        Every shock kind is written, operation-keyed (``multiply``, ``add``,
        ``set``, ``clip``, ``pipeline``, ``max``, ``min``, ``where``,
        ``when``), its target (``table:`` or ``column:``) on the outermost
        shock only, so ``from_dict(to_dict(p)).source_sha()`` equals
        ``p.source_sha()``. Base tables are **not** serialised -- they carry
        data -- so a plan that states them is read back with the same
        ``base_tables=``.
        """
        scenarios: list[dict[str, Any]] = []
        for sid, shocks in sorted(self.shocks.items()):
            entry: dict[str, Any] = {"id": sid}
            if shocks:
                entry["shocks"] = [_shock_to_dict(s) for s in shocks]
            scenarios.append(entry)

        aggregations = [_agg_to_dict(agg) for agg in self.aggregations]

        out: dict[str, Any] = {
            "scenarios": scenarios,
            "aggregations": aggregations,
        }
        if self.master_seed is not None:
            out["master_seed"] = self.master_seed
        return out

    def to_yaml(self, path: Path) -> None:
        """Write this plan to ``path`` as YAML (recipe only, no base tables).

        Every shock kind round-trips:
        ``ScenarioRun.from_yaml(path).source_sha() == plan.source_sha()``.
        The whole recipe is built before ``path`` is opened, so a plan the
        recipe cannot hold -- an aggregator built with ``.of(expr)`` -- raises
        ``NotImplementedError`` and leaves ``path`` as it was: no empty file,
        and an existing recipe not truncated.
        """
        text = yaml.safe_dump(self.to_dict(), sort_keys=True)
        Path(path).write_text(text, encoding="utf-8")

    @classmethod
    def from_dict(
        cls,
        config: dict[str, Any],
        *,
        base_tables: dict[str, Table] | None = None,
    ) -> ScenarioRun:
        """Reconstruct a plan from a dict produced by ``to_dict``.

        ``base_tables`` is optional, as it is on the plan: Tables carry data
        and live outside the recipe, so a plan that stated them is read back
        with the same ones.
        """
        shocks = parse_scenario_config(config.get("scenarios", []))
        aggregations = parse_aggregations(config.get("aggregations", []))
        return cls(
            shocks=shocks,
            base_tables=base_tables or {},
            aggregations=aggregations,
            master_seed=config.get("master_seed"),
        )

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        base_tables: dict[str, Table] | None = None,
    ) -> ScenarioRun:
        """Reconstruct a plan from a YAML file produced by ``to_yaml``."""
        with Path(path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls.from_dict(config, base_tables=base_tables)


def _shock_to_dict(shock: Shock) -> dict[str, Any]:
    """Convert a Shock to the operation-keyed dict consumed by parse_shock_config.

    The target is written on the outermost shock only: a nested shock moves
    its outer shock's target, which is also how the canonical form reads it,
    so writing and reading back keeps the plan's SHA.
    """
    out = _operation(shock)
    if shock.table is not None:
        out["table"] = shock.table
    if shock.column is not None:
        out["column"] = shock.column
    return out


def _operation(shock: Shock) -> dict[str, Any]:  # noqa: C901, PLR0911 -- one per kind
    """Return ``shock``'s operation, with no target, in the recipe's own keys.

    A ``where`` or ``when`` sits beside the operation it confines, the way
    an author writes it, wherever that reads back as the same shock; where
    it would not -- a filter around a shock already filtered or timed -- the
    confined shock is written under ``shock:`` instead.
    """
    if isinstance(shock, MultiplicativeShock):
        return {"multiply": shock.factor}
    if isinstance(shock, AdditiveShock):
        return {"add": shock.delta}
    if isinstance(shock, OverrideShock):
        return {"set": shock.value}
    if isinstance(shock, ClipShock):
        bounds = {"min": shock.min_value, "max": shock.max_value}
        return {"clip": {k: v for k, v in bounds.items() if v is not None}}
    if isinstance(shock, PipelineShock):
        return {"pipeline": [_operation(step) for step in shock.shocks]}
    if isinstance(shock, MaxShock):
        return {"max": [_operation(shock.shock_a), _operation(shock.shock_b)]}
    if isinstance(shock, MinShock):
        return {"min": [_operation(shock.shock_a), _operation(shock.shock_b)]}
    if isinstance(shock, FilteredShock):
        inner = _operation(shock.shock)
        if "where" in inner or "when" in inner:
            return {"where": shock.where, "shock": inner}
        return {**inner, "where": shock.where}
    if isinstance(shock, TimeConditionalShock):
        inner = _operation(shock.shock)
        if "when" in inner:
            return {"when": shock.when, "shock": inner}
        return {**inner, "when": shock.when}
    msg = (
        f"A {type(shock).__name__} has no recipe form: a recipe writes "
        "multiply, add, set, clip, pipeline, max, min, where and when."
    )
    raise NotImplementedError(msg)


def _agg_to_dict(agg: Aggregator | _Partitioned) -> dict[str, Any]:
    """Serialise an aggregator (or _Partitioned wrapper) to a recipe dict.

    The result is consumable by ``parse_aggregations``: it carries ``kind``,
    ``alias``, plus the aggregator's constructor fields. ``_Partitioned``
    wrappers add ``by`` and a nested ``inner`` recipe.

    Raises ``NotImplementedError`` if any aggregator was built with the
    ``.of(pl.Expr)`` escape hatch -- the polars expression is not
    round-trippable through YAML/dict.
    """
    if isinstance(agg, _Partitioned):
        return {
            "kind": "_Partitioned",
            "by": list(agg.by),
            "alias": agg.alias,
            "inner": _agg_to_dict_inner(agg.inner),
        }
    _check_serialisable(agg)
    cf = dict(agg.canonical_form())
    alias = getattr(agg, "alias_", None)
    if alias is not None:
        cf["alias"] = alias
    return cf


def _agg_to_dict_inner(agg: Aggregator) -> dict[str, Any]:
    """Serialise the inner aggregator of a _Partitioned wrapper (no alias)."""
    _check_serialisable(agg)
    return dict(agg.canonical_form())


def _check_serialisable(agg: Aggregator) -> None:
    """Raise if an aggregator carries a polars-expression override.

    ``.of(pl.Expr)`` overrides the within-scenario reduction with a raw
    polars expression that is not serialisable into a recipe dict. Fail
    loudly at write time so an auditor never receives a YAML they cannot
    reload.
    """
    if getattr(agg, "within_expr_override", None) is not None:
        msg = (
            f"Aggregator {type(agg).__name__!r} built with .of(expr) cannot "
            "be serialised to YAML/dict: the polars expression is not "
            "round-trippable. Reconstruct .of() aggregators in code after "
            "reload."
        )
        raise NotImplementedError(msg)


__all__ = ["ScenarioRun"]
