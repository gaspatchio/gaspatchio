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

from gaspatchio_core._identity import source_sha_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio_core.assumptions import Table
    from gaspatchio_core.frame import ActuarialFrame
    from gaspatchio_core.scenarios._for_each import BatchSnapshot
    from gaspatchio_core.scenarios._metric import Aggregator, _Partitioned
    from gaspatchio_core.scenarios._result import ScenarioResult
    from gaspatchio_core.scenarios.shocks import Shock


def _alias_of(agg: Any) -> str | None:  # noqa: ANN401
    """Return the alias of an aggregator or _Partitioned wrapper, if any."""
    # _Partitioned exposes ``alias`` as a direct dataclass attribute (str).
    # _BaseAggregator exposes ``alias_`` (str | None) and ``alias`` is a method.
    alias_attr = getattr(agg, "alias_", None)
    if alias_attr is not None:
        return alias_attr
    # _Partitioned: alias is a str attribute (not callable).
    alias = getattr(agg, "alias", None)
    if isinstance(alias, str):
        return alias
    return None


@dataclass(frozen=True)
class ScenarioRun:
    """Reusable, auditable stochastic-run plan.

    Captures shocks, base tables, aggregation recipes, and (optionally) a
    master seed. Identity surface (``canonical_form``, ``source_sha``,
    ``describe``) mirrors Schedule / Curve / MortalityTable. Run via
    ``.run()`` or convert to dict/YAML for governance archives.

    ``aggregations`` is a tuple of aggregator instances (each carrying its
    own alias via ``.alias(name)``). Every aggregator must have an explicit
    alias and aliases must be unique across the tuple; both invariants are
    enforced at construction time.
    """

    shocks: dict[str, list[Shock]]
    base_tables: dict[str, Table]
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
        model_fn: Callable[..., ActuarialFrame],
        *,
        batch_size: int | Literal["auto"] = "auto",
        target_memory_fraction: float = 0.5,
        return_full_grid: bool = False,
        sink_dir: Path | None = None,
        progress: bool = False,
        on_batch: Callable[[BatchSnapshot], None] | None = None,
        audit: bool | Path = False,
    ) -> ScenarioResult:
        """Run the plan via ``for_each_scenario``.

        The result's ``plan_sha`` field is stamped with this plan's
        ``source_sha()`` so downstream consumers can verify input identity.
        When ``audit`` is truthy, a JSON audit sidecar is written and the
        path stored on ``result.audit_path``:

        * ``audit=True`` (default location): the sidecar is written to
          ``<sink_dir>/<run_id>.audit.json`` when ``sink_dir`` is provided,
          otherwise to ``./gaspatchio_audit/<run_id>.audit.json``.
        * ``audit=Path(...)``: the sidecar is written to that exact path.
        * ``audit=False`` (default): no sidecar is written.

        ``run_id`` is ``<utc-iso-timestamp>_<short-sha>`` (filename-safe).

        Model function contract:
            ``model_fn`` is called once per batch with the signature
            ``model_fn(af, *, tables, drivers) -> ActuarialFrame``:

            * ``af``: ``ActuarialFrame`` cross-joined with the batch's
              ``scenario_id`` column.
            * ``tables``: ``dict[str, Table]`` - per-batch base tables. For
              shocks-shape scenarios these are stacked with a ``scenario_id``
              dimension so a single ``Table.lookup`` resolves the shocked
              value; for ids-only and drivers shapes the plain base tables
              pass through unchanged.
            * ``drivers``: ``dict[str, Any]`` - per-scenario kwargs (drivers
              shape) plus the derived ``drivers["rng_seed"]`` (when
              ``master_seed`` is set). Only forwarded at ``batch_size=1``.

            Return an ``ActuarialFrame`` carrying whatever columns the
            aggregators need. If you don't use tables or drivers, accept
            them as keyword args anyway - the dispatcher always passes both.

        Streaming (``progress`` / ``on_batch``) is a **live observation
        channel** and does not change the run's identity: ``source_sha()``,
        ``canonical_form()``, and the audit sidecar are unaffected by
        ``on_batch``. To persist a convergence trace, write it from the
        callback. Under ``batch_size="auto"`` the batch boundaries (and thus
        the trace) are not reproducible.

        """
        from gaspatchio_core.scenarios._for_each import for_each_scenario

        plan_sha = self.source_sha()
        result = for_each_scenario(
            af,
            scenarios=self.shocks,  # type: ignore[arg-type]
            model_fn=model_fn,
            aggregations=self.aggregations,
            base_tables=self.base_tables,
            batch_size=batch_size,
            target_memory_fraction=target_memory_fraction,
            return_full_grid=return_full_grid,
            sink_dir=sink_dir,
            master_seed=self.master_seed,
            progress=progress,
            on_batch=on_batch,
            plan_sha=plan_sha,
        )

        # plan_sha is already set by for_each_scenario; re-stamp defensively.
        result = replace(result, plan_sha=plan_sha)

        # Audit sidecar (opt-in).
        if audit is not False:
            audit_path = self._write_audit_sidecar(
                audit=audit,
                result=result,
                sink_dir=sink_dir,
                plan_sha=plan_sha,
            )
            result = replace(result, audit_path=audit_path)

        return result

    def _write_audit_sidecar(
        self,
        *,
        audit: bool | Path,
        result: ScenarioResult,
        sink_dir: Path | None,
        plan_sha: str,
    ) -> Path:
        """Write the audit JSON sidecar; return the path it was written to."""
        import datetime as _dt
        import sys

        import polars as pl

        import gaspatchio_core
        from gaspatchio_core.scenarios._audit import write_audit

        if isinstance(audit, Path):
            path = audit
        else:
            # audit is True; derive default location.
            timestamp = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
            short = plan_sha.split(":", 1)[-1][:8] if ":" in plan_sha else plan_sha[:8]
            run_id = f"{timestamp}_{short}"
            default_dir = (
                sink_dir if sink_dir is not None else Path("./gaspatchio_audit")
            )
            path = default_dir / f"{run_id}.audit.json"

        try:
            import ddsketch  # type: ignore[import-not-found]

            ddsketch_version = getattr(ddsketch, "__version__", "unknown")
        except ImportError:
            ddsketch_version = "unavailable"

        write_audit(
            path,
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
                "library_version": getattr(gaspatchio_core, "__version__", "unknown"),
                "polars_version": pl.__version__,
                "ddsketch_version": ddsketch_version,
                "python_version": ".".join(map(str, sys.version_info[:3])),
                "master_seed": self.master_seed,
            },
            aggregator_outputs=result.aggregations,
            input_data_fingerprint={},  # left empty in v0.2 minimal; future follow-up.
        )
        return path

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-serialisable dict recipe for this plan.

        Base tables are **not** serialised - they live elsewhere and must be
        supplied explicitly to ``from_dict`` / ``from_yaml``.
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
        """Write this plan to ``path`` as YAML (recipe only, no base tables)."""
        import yaml

        with Path(path).open("w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, sort_keys=True)

    @classmethod
    def from_dict(
        cls,
        config: dict[str, Any],
        *,
        base_tables: dict[str, Table],
    ) -> ScenarioRun:
        """Reconstruct a plan from a dict produced by ``to_dict``.

        ``base_tables`` is supplied explicitly - Tables carry data and live
        outside the YAML recipe.
        """
        from gaspatchio_core.scenarios._config import (
            parse_aggregations,
            parse_scenario_config,
        )

        shocks = parse_scenario_config(config.get("scenarios", []))
        aggregations = parse_aggregations(config.get("aggregations", []))
        return cls(
            shocks=shocks,  # type: ignore[arg-type]
            base_tables=base_tables,
            aggregations=aggregations,
            master_seed=config.get("master_seed"),
        )

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        base_tables: dict[str, Table],
    ) -> ScenarioRun:
        """Reconstruct a plan from a YAML file produced by ``to_yaml``."""
        import yaml

        with Path(path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls.from_dict(config, base_tables=base_tables)


def _shock_to_dict(shock: Shock) -> dict[str, Any]:
    """Convert a Shock to the operation-keyed dict consumed by parse_shock_config.

    Supports the basic shock types (Multiplicative, Additive, Override) used
    in v0.2 of ScenarioRun YAML round-trip. Nested / composed shocks are not
    yet supported - they will be added in a follow-up task once parse_shock_config
    grows symmetric coverage.
    """
    from gaspatchio_core.scenarios.shocks import (
        AdditiveShock,
        MultiplicativeShock,
        OverrideShock,
    )

    out: dict[str, Any] = {}
    if shock.table is not None:
        out["table"] = shock.table
    if shock.column is not None:
        out["column"] = shock.column

    if isinstance(shock, MultiplicativeShock):
        out["multiply"] = shock.factor
        return out
    if isinstance(shock, AdditiveShock):
        out["add"] = shock.delta
        return out
    if isinstance(shock, OverrideShock):
        out["set"] = shock.value
        return out

    msg = (
        f"_shock_to_dict does not yet support {type(shock).__name__}. "
        f"v0.2 round-trip covers MultiplicativeShock, AdditiveShock, OverrideShock."
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
    from gaspatchio_core.scenarios._metric import _Partitioned

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
