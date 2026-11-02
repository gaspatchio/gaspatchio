# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: End-to-end audit-chain integration test for v0.2 ScenarioRun.
# ABOUTME: Pins SHA stability, batch-equiv, YAML round-trip, audit sidecar.
"""End-to-end v0.2 audit-chain integration test (GSP-101)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

from gaspatchio.assumptions import Table
from gaspatchio.frame import ActuarialFrame
from gaspatchio.scenarios import (
    ArgMax,
    Mean,
    Sum,
)
from gaspatchio.scenarios._audit import read_audit
from gaspatchio.scenarios._run import ScenarioRun
from gaspatchio.scenarios.shocks import MultiplicativeShock


def _mortality() -> Table:
    """Three-row mortality table: the model builds its own, as a model does."""
    df = pl.DataFrame({"age": [30, 31, 32], "rate": [0.001, 0.0012, 0.0015]})
    return Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")


@pytest.fixture
def mortality_table() -> Table:
    """The same table the model reads, as the plan states it."""
    return _mortality()


@pytest.fixture
def af() -> ActuarialFrame:
    """Eight-policy frame with cycling LOB to exercise partition aggregator."""
    return ActuarialFrame(
        {
            "policy_id": list(range(1, 9)),
            "age": [30, 31, 32, 30, 31, 32, 30, 31],
            "premium": [100.0, 200.0, 300.0, 150.0, 250.0, 350.0, 175.0, 225.0],
        }
    )


def _model_fn(af: ActuarialFrame) -> ActuarialFrame:
    """Add a deterministic ``lob`` column + ``loss`` projection.

    The plan shocks ``mortality``, so the model reads it -- its own table,
    through its own lookup: a shock on a table no read reaches is refused
    rather than folded as BASE.
    """
    af.mort_rate = _mortality().lookup(age=af.age)
    return af.with_columns(
        pl.when(pl.col("policy_id") % 2 == 0)
        .then(pl.lit("home"))
        .otherwise(pl.lit("motor"))
        .alias("lob"),
        pl.col("premium").alias("loss"),
    )


def _make_plan(mortality_table: Table) -> ScenarioRun:
    """Build the canonical multi-aggregator plan used across the test."""
    return ScenarioRun(
        shocks={
            "BASE": [],
            "STRESS": [MultiplicativeShock(factor=1.5, table="mortality")],
        },
        base_tables={"mortality": mortality_table},
        aggregations=(
            Sum("loss").alias("total"),
            Mean("loss").alias("avg"),
            ArgMax("loss").alias("worst"),
            Sum("loss").alias("by_lob").over("lob"),
        ),
    )


def test_sha_stable_across_insertion_orders(mortality_table: Table) -> None:
    """source_sha is invariant under dict insertion order on shocks + base_tables."""
    p1 = ScenarioRun(
        shocks={"A": [], "B": [MultiplicativeShock(factor=1.2, table="mortality")]},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum("loss").alias("total"),),
    )
    p2 = ScenarioRun(
        shocks={"B": [MultiplicativeShock(factor=1.2, table="mortality")], "A": []},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum("loss").alias("total"),),
    )
    assert p1.source_sha() == p2.source_sha()


def test_e2e_batch_equivalence(af: ActuarialFrame, mortality_table: Table) -> None:
    """Multi-aggregator plan: batch_size=1 and batch_size=2 yield equal output."""
    plan = _make_plan(mortality_table)
    one = plan.run(af, _model_fn, batch_size=1)
    two = plan.run(af, _model_fn, batch_size=2)

    assert one.aggregations["total"] == pytest.approx(two.aggregations["total"])
    assert one.aggregations["avg"] == pytest.approx(two.aggregations["avg"])
    assert one.aggregations["worst"] == two.aggregations["worst"]
    assert (
        one.aggregations["by_lob"]
        .sort("lob")
        .equals(
            two.aggregations["by_lob"].sort("lob"),
        )
    )


def test_yaml_round_trip_preserves_sha_and_aggregations(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """to_yaml/from_yaml preserves SHA + reruns produce identical aggregations."""
    plan = _make_plan(mortality_table)
    yaml_path = tmp_path / "plan.yaml"
    plan.to_yaml(yaml_path)
    reloaded = ScenarioRun.from_yaml(
        yaml_path,
        base_tables={"mortality": mortality_table},
    )

    assert reloaded.source_sha() == plan.source_sha()

    original = plan.run(af, _model_fn, batch_size=1)
    rerun = reloaded.run(af, _model_fn, batch_size=1)

    # Scalar aggregators: bit-exact (Sum is integer-addition; Mean uses Welford
    # which is order-dependent in general but order is fixed here).
    assert rerun.aggregations["total"] == original.aggregations["total"]
    assert rerun.aggregations["avg"] == original.aggregations["avg"]
    assert rerun.aggregations["worst"] == original.aggregations["worst"]

    # Partitioned: DataFrame equality after sort.
    assert (
        rerun.aggregations["by_lob"]
        .sort("lob")
        .equals(
            original.aggregations["by_lob"].sort("lob"),
        )
    )


def test_audit_sidecar_round_trip(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """audit=True writes a sidecar; reading it back yields the same SHA + outputs."""
    plan = _make_plan(mortality_table)
    audit_path = tmp_path / "run.audit.json"

    result = plan.run(af, _model_fn, batch_size=1, audit=audit_path)
    assert result.audit_path == audit_path
    assert audit_path.exists()

    payload = read_audit(audit_path)
    assert payload["schema_version"] == "2.1"
    assert payload["source_sha"] == plan.source_sha()
    assert "plan_canonical_form" in payload
    assert "run_metadata" in payload
    assert "aggregator_outputs" in payload

    # Scalar outputs land as raw scalars.
    assert payload["aggregator_outputs"]["total"] == result.aggregations["total"]
    assert payload["aggregator_outputs"]["avg"] == result.aggregations["avg"]
    assert payload["aggregator_outputs"]["worst"] == result.aggregations["worst"]

    # Partitioned output is coerced to list-of-row-dicts.
    audited_by_lob = payload["aggregator_outputs"]["by_lob"]
    assert isinstance(audited_by_lob, list)
    expected_rows = result.aggregations["by_lob"].sort("lob").to_dicts()
    assert sorted(audited_by_lob, key=lambda r: r["lob"]) == expected_rows


def test_audit_sidecar_survives_yaml_reload(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """YAML reload + rerun with audit produces matching SHA + same scalar outputs."""
    plan = _make_plan(mortality_table)
    yaml_path = tmp_path / "plan.yaml"
    plan.to_yaml(yaml_path)
    reloaded = ScenarioRun.from_yaml(
        yaml_path,
        base_tables={"mortality": mortality_table},
    )

    audit_a = tmp_path / "a.audit.json"
    audit_b = tmp_path / "b.audit.json"

    result_a = plan.run(af, _model_fn, batch_size=1, audit=audit_a)
    result_b = reloaded.run(af, _model_fn, batch_size=1, audit=audit_b)

    payload_a = read_audit(audit_a)
    payload_b = read_audit(audit_b)

    assert payload_a["source_sha"] == payload_b["source_sha"]
    agg_a = payload_a["aggregator_outputs"]
    agg_b = payload_b["aggregator_outputs"]
    assert agg_a["total"] == agg_b["total"]
    assert agg_a["avg"] == agg_b["avg"]
    assert agg_a["worst"] == agg_b["worst"]
    # by_lob list-of-dicts: comparable after sort.
    rows_a = sorted(agg_a["by_lob"], key=lambda r: r["lob"])
    rows_b = sorted(agg_b["by_lob"], key=lambda r: r["lob"])
    assert rows_a == rows_b

    # Also belt-and-braces: the in-memory result_a/result_b match.
    assert result_a.aggregations["total"] == result_b.aggregations["total"]


def test_audit_records_selection_and_v2_schema(tmp_path: Path) -> None:
    """The audit sidecar carries the batch-search selection at schema 2.1."""
    from gaspatchio.scenarios._audit import AUDIT_SCHEMA_VERSION, read_audit

    assert AUDIT_SCHEMA_VERSION == "2.1"

    frame = ActuarialFrame(pl.DataFrame({"policy_id": range(50), "v": [1.0] * 50}))

    def model_fn(
        a: ActuarialFrame, *, tables: object = None, drivers: object = None
    ) -> ActuarialFrame:  # noqa: ARG001
        a.payoff = a.v * 2.0
        return a

    plan = ScenarioRun(
        shocks={f"s{i}": [] for i in range(20)},
        base_tables={},
        aggregations=(Sum("payoff").alias("total").over("scenario_id"),),
    )
    out = tmp_path / "sel.audit.json"
    res = plan.run(frame, model_fn, audit=out)
    meta = read_audit(res.audit_path)["run_metadata"]
    assert meta["batch_size_resolution"] == "auto_search"
    assert meta["selection_engine"] in ("streaming", "in-memory")
    assert isinstance(meta["selection_probed"], list)


def test_audit_coerces_ndarray_outputs_to_reloadable_json() -> None:
    """Period* ndarray / dict outputs become reloadable JSON, not repr strings (#12)."""
    import json

    import numpy as np

    from gaspatchio.scenarios._audit import _coerce_outputs_to_json

    outputs = {
        "period_total": np.array([1.0, 2.0, 3.0]),
        "period_q": {0.5: np.array([10.0, 20.0])},
    }
    coerced = _coerce_outputs_to_json(outputs)
    # Plain json.dumps (no default=str) must succeed -> values are real lists/numbers.
    reloaded = json.loads(json.dumps(coerced))
    assert reloaded["period_total"] == [1.0, 2.0, 3.0]
    assert reloaded["period_q"]["0.5"] == [10.0, 20.0]  # float key -> str in JSON


# --- the policy axis writes the same record (GSP-127) -----------------------


def _policy_model(af: ActuarialFrame) -> ActuarialFrame:
    """One-line policy-axis model: the loss column the aggregators fold."""
    af.loss = af.premium * 0.01
    return af


def _policy_book() -> pl.DataFrame:
    """Eight policies on the policy axis (no scenario axis)."""
    premiums = [100.0, 200.0, 300.0, 150.0, 250.0, 350.0, 175.0, 225.0]
    return pl.DataFrame({"policy_id": list(range(1, 9)), "premium": premiums})


def test_the_plain_aggregation_run_writes_an_audit_record(tmp_path: Path) -> None:
    """run_aggregated(audit=...) writes the record the plan path already writes."""
    from gaspatchio._identity import source_sha_of
    from gaspatchio.scenarios import run_aggregated

    audit_path = tmp_path / "aggregated.audit.json"
    result = run_aggregated(
        _policy_model,
        _policy_book(),
        [Sum("loss").alias("total"), Mean("loss").alias("avg")],
        batch_size=3,
        audit=audit_path,
    )

    assert result.audit_path == audit_path
    assert audit_path.exists()

    payload = read_audit(audit_path)
    assert payload["plan_canonical_form"]["kind"] == "run_aggregated"
    assert sorted(payload["plan_canonical_form"]["aggregations"]) == ["avg", "total"]
    assert payload["source_sha"] == source_sha_of(payload["plan_canonical_form"])
    assert payload["aggregator_outputs"]["total"] == result.aggregations["total"]

    meta = payload["run_metadata"]
    assert (meta["n_policies"], meta["batch_size"]) == (8, 3)
    assert meta["wall_time_s"] == result.wall_time_s
    assert "polars_version" in meta


def test_the_aggregation_sidecar_lands_where_the_plan_path_puts_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """audit=True derives <run_id>.audit.json under ./gaspatchio_audit."""
    import pathlib

    from gaspatchio.scenarios import run_aggregated

    monkeypatch.chdir(tmp_path)
    result = run_aggregated(
        _policy_model,
        _policy_book(),
        [Sum("loss").alias("total")],
        batch_size=4,
        audit=True,
    )
    assert result.audit_path is not None
    assert result.audit_path.parent == pathlib.Path("gaspatchio_audit")
    assert result.audit_path.name.endswith(".audit.json")
    assert result.audit_path.exists()


def test_an_aggregation_run_asked_for_no_record_writes_none() -> None:
    """No record is asked for by default: nothing is written, audit_path is None."""
    from gaspatchio.scenarios import run_aggregated

    result = run_aggregated(
        _policy_model,
        _policy_book(),
        [Sum("loss").alias("total")],
        batch_size=4,
    )
    assert result.audit_path is None


# --- the record names the graph it folded and the data it read (GSP-127) ----


def _fingerprinting_model(
    seen: list[str],
) -> Callable[..., ActuarialFrame]:
    """Return a scenario model that records its own graph fingerprint per batch."""

    def model_fn(
        af: ActuarialFrame,
        *,
        tables: dict[str, Table] | None = None,  # noqa: ARG001
        drivers: dict[str, Any] | None = None,  # noqa: ARG001
    ) -> ActuarialFrame:
        af.loss = af.premium * 0.01
        seen.append(af.graph.fingerprint())
        return af

    return model_fn


def _frame_like(af: ActuarialFrame) -> ActuarialFrame:
    """Return a fresh frame over the same book, for the model run standalone."""
    return ActuarialFrame(af.collect())


def _unshocked_plan() -> ScenarioRun:
    """Two scenarios, no base tables: every batch folds one and the same graph."""
    return ScenarioRun(
        shocks={"BASE": [], "STRESS": []},
        base_tables={},
        aggregations=(Sum("loss").alias("total"),),
    )


def test_the_scenario_record_names_the_graph_it_folded(
    tmp_path: Path,
    af: ActuarialFrame,
) -> None:
    """The sidecar's graph_fingerprint is the reconciled model's own stamp.

    Each scenario's calculation is the one it builds composed on its own --
    the model over the book, with no scenario axis -- so an unshocked run
    names the standalone model's fingerprint: BASE is checked to be the
    reconciled model rather than measured.
    """
    seen: list[str] = []
    audit_path = tmp_path / "scenario.audit.json"
    result = _unshocked_plan().run(
        af,
        _fingerprinting_model(seen),
        batch_size=1,
        audit=audit_path,
    )
    standalone = _fingerprinting_model([])(_frame_like(af)).graph.fingerprint()

    assert standalone in seen, "each scenario's own composition is the model alone"
    assert result.graph_fingerprint == standalone
    assert read_audit(audit_path)["graph_fingerprint"] == standalone


def test_the_aggregation_record_names_the_graph_it_folded(tmp_path: Path) -> None:
    """The policy axis carries the same linkage the scenario axis does."""
    from gaspatchio.scenarios import run_aggregated

    seen: list[str] = []

    def model_fn(af: ActuarialFrame) -> ActuarialFrame:
        af.loss = af.premium * 0.01
        seen.append(af.graph.fingerprint())
        return af

    audit_path = tmp_path / "policy.audit.json"
    run_aggregated(
        model_fn,
        _policy_book(),
        [Sum("loss").alias("total")],
        batch_size=3,
        audit=audit_path,
    )

    assert len(set(seen)) == 1, "every policy batch folded the same graph"
    assert read_audit(audit_path)["graph_fingerprint"] == seen[0]


def test_a_run_that_folded_more_than_one_graph_says_so_rather_than_picking_one(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """Shocked bases reach the digest, so no single stamp stands for the run."""
    seen: list[str] = []

    def model_fn(frame: ActuarialFrame) -> ActuarialFrame:
        frame.mort_rate = _mortality().lookup(age=frame.age)
        frame.loss = frame.premium * frame.mort_rate
        seen.append(frame.graph.fingerprint())
        return frame

    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "STRESS": [MultiplicativeShock(factor=1.5, table="mortality")],
        },
        base_tables={"mortality": mortality_table},
        aggregations=(Sum("loss").alias("total"),),
    )
    audit_path = tmp_path / "shocked.audit.json"
    result = plan.run(af, model_fn, batch_size=1, audit=audit_path)

    assert len(set(seen)) > 1, "each batch read its own shocked basis"
    assert result.graph_fingerprint is None
    assert read_audit(audit_path)["graph_fingerprint"] is None


def test_the_record_names_what_each_number_was_folded_from(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """aggregator_identity names every alias beside the numbers it produced."""
    audit_path = tmp_path / "identity.audit.json"
    _make_plan(mortality_table).run(af, _model_fn, batch_size=1, audit=audit_path)

    payload = read_audit(audit_path)
    identity = payload["aggregator_identity"]
    assert set(identity) == set(payload["aggregator_outputs"])
    assert identity["total"] == {"kind": "Sum", "column": "loss", "within": "sum"}
    assert identity["worst"]["kind"] == "ArgMax"
    assert identity["by_lob"]["kind"] == "_Partitioned"
    assert identity["by_lob"]["by"] == ["lob"]
    assert identity["by_lob"]["inner"]["column"] == "loss"


def test_the_aggregation_record_names_what_each_number_was_folded_from(
    tmp_path: Path,
) -> None:
    """The policy axis carries the same alias-to-fold map."""
    from gaspatchio.scenarios import run_aggregated

    audit_path = tmp_path / "policy_identity.audit.json"
    run_aggregated(
        _policy_model,
        _policy_book(),
        [Sum("loss").alias("total"), Mean("loss").alias("avg")],
        batch_size=4,
        audit=audit_path,
    )

    identity = read_audit(audit_path)["aggregator_identity"]
    assert set(identity) == {"total", "avg"}
    assert identity["avg"]["kind"] == "Mean"
    assert identity["avg"]["column"] == "loss"


def test_the_record_stamps_the_policy_data_with_the_frameworks_own_grammar(
    tmp_path: Path,
) -> None:
    """input_data_fingerprint carries the content stamp, not an empty dict."""
    from gaspatchio._identity import content_sha_of
    from gaspatchio.scenarios import run_aggregated

    book = _policy_book()
    audit_path = tmp_path / "data.audit.json"
    run_aggregated(
        _policy_model,
        book,
        [Sum("loss").alias("total")],
        batch_size=4,
        audit=audit_path,
    )

    stamped = read_audit(audit_path)["input_data_fingerprint"]
    assert stamped["model_points"] == content_sha_of(book)


def test_the_data_stamp_moves_with_the_book_and_holds_without_it(
    tmp_path: Path,
) -> None:
    """One changed premium moves the stamp; a repeat on the same book does not."""
    from gaspatchio.scenarios import run_aggregated

    def stamp_of(book: pl.DataFrame, path: Path) -> str:
        run_aggregated(
            _policy_model,
            book,
            [Sum("loss").alias("total")],
            batch_size=4,
            audit=path,
        )
        return str(read_audit(path)["input_data_fingerprint"]["model_points"])

    book = _policy_book()
    first = stamp_of(book, tmp_path / "a.audit.json")
    again = stamp_of(_policy_book(), tmp_path / "b.audit.json")
    moved = book.with_columns(
        pl.when(pl.col("policy_id") == 1)
        .then(pl.lit(101.0))
        .otherwise(pl.col("premium"))
        .alias("premium")
    )
    after = stamp_of(moved, tmp_path / "c.audit.json")

    assert first == again
    assert first != after


def test_the_scenario_record_stamps_the_policy_data_it_read(
    tmp_path: Path,
    af: ActuarialFrame,
) -> None:
    """The scenario axis stamps its policy book under the same grammar."""
    from gaspatchio._identity import content_sha_of

    audit_path = tmp_path / "scenario_data.audit.json"
    _unshocked_plan().run(
        af,
        _fingerprinting_model([]),
        batch_size=2,
        audit=audit_path,
    )

    stamped = read_audit(audit_path)["input_data_fingerprint"]
    assert stamped["model_points"] == content_sha_of(af.collect())


def test_a_two_point_zero_record_still_reads_at_two_point_one(
    tmp_path: Path,
    af: ActuarialFrame,
) -> None:
    """The bump is additive: 2.0's fields all survive, and 2.0 files still load."""
    import json

    from gaspatchio.scenarios._audit import AUDIT_SCHEMA_VERSION

    assert AUDIT_SCHEMA_VERSION == "2.1"

    legacy = {
        "schema_version": "2.0",
        "source_sha": f"sha256:{'0' * 64}",
        "plan_canonical_form": {"kind": "ScenarioRun"},
        "run_metadata": {"wall_time_s": 1.0},
        "aggregator_outputs": {"total": 42.0},
        "input_data_fingerprint": {},
    }
    legacy_path = tmp_path / "legacy.audit.json"
    legacy_path.write_text(json.dumps(legacy))
    assert read_audit(legacy_path) == legacy

    fresh_path = tmp_path / "fresh.audit.json"
    _unshocked_plan().run(
        af,
        _fingerprinting_model([]),
        batch_size=2,
        audit=fresh_path,
    )
    fresh = read_audit(fresh_path)
    assert set(legacy) <= set(fresh)
    assert fresh["schema_version"] == "2.1"


# --- the record names every graph a shocked run folded (GSP-127) ------------


def _reading_model(frame: ActuarialFrame) -> ActuarialFrame:
    """Read the shocked table, so each scenario's basis reaches the digest."""
    frame.mort_rate = _mortality().lookup(age=frame.age)
    frame.loss = frame.premium * frame.mort_rate
    return frame


def _shocked_plan(mortality_table: Table, *ids: str) -> ScenarioRun:
    """Return a plan over the named bases: BASE untouched, STRESS with mortality up."""
    recipes: dict[str, list[Any]] = {
        "BASE": [],
        "STRESS": [MultiplicativeShock(factor=1.5, table="mortality")],
    }
    return ScenarioRun(
        shocks={sid: recipes[sid] for sid in ids},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum("loss").alias("total"),),
    )


def _record_of(
    plan: ScenarioRun,
    af: ActuarialFrame,
    path: Path,
    batch_size: int | str = "auto",
) -> dict[str, Any]:
    """Run ``plan`` with a record asked for and hand back what it wrote."""
    plan.run(af, _reading_model, batch_size=batch_size, audit=path)  # type: ignore[arg-type]
    return read_audit(path)


def test_a_shocked_run_names_the_graph_every_scenario_folded(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """Two shocked bases are two calculations, and the record names both.

    The comparison is inside one plan rather than across two. A run's
    scenario axis is a column handed to the model, stamped with the
    identifiers the run declared, so a plan of one scenario and a plan of
    two hand the model two different axes and their entries are not each
    other's. What this map has to say is that this run's two bases are two
    calculations and that it names both. That an entry does not move with
    the batch boundary -- the property the field documents -- is the
    neighbouring case's, and it holds within one plan where it means
    something.
    """
    alone = {
        sid: _record_of(
            _shocked_plan(mortality_table, sid),
            af,
            tmp_path / f"{sid}.audit.json",
            batch_size=1,
        )["graph_fingerprint"]
        for sid in ("BASE", "STRESS")
    }
    together = _record_of(
        _shocked_plan(mortality_table, "BASE", "STRESS"),
        af,
        tmp_path / "both.audit.json",
        batch_size=2,
    )["graph_fingerprint_by_scenario"]

    assert alone["BASE"] != alone["STRESS"], "each basis is its own calculation"
    assert set(together) == {"BASE", "STRESS"}, "the map names every scenario"
    assert together["BASE"] != together["STRESS"], "and separates them too"
    assert all(stamp is not None for stamp in together.values())


def test_the_per_scenario_map_does_not_move_with_the_batch_boundary(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """A scenario's basis is its own, so how the run was cut cannot move it."""
    maps = [
        _record_of(
            _shocked_plan(mortality_table, "BASE", "STRESS"),
            af,
            tmp_path / f"cut_{label}.audit.json",
            batch_size=size,
        )["graph_fingerprint_by_scenario"]
        for label, size in (("one", 1), ("two", 2), ("auto", "auto"))
    ]

    assert maps[0] == maps[1] == maps[2]
    assert len(set(maps[0].values())) == 2, "the two bases folded two graphs"


def test_the_run_stamp_no_longer_moves_with_the_batch_boundary(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """The scalar answers over scenarios, not over however memory cut the run."""
    stamps = [
        _record_of(
            _shocked_plan(mortality_table, "BASE", "STRESS"),
            af,
            tmp_path / f"scalar_{label}.audit.json",
            batch_size=size,
        )["graph_fingerprint"]
        for label, size in (("one", 1), ("two", 2), ("auto", "auto"))
    ]

    assert stamps == [None, None, None]


def test_an_unshocked_scenario_run_names_one_graph_for_every_scenario(
    tmp_path: Path,
    af: ActuarialFrame,
) -> None:
    """Leave the bases alone and every scenario folds the same calculation."""
    seen: list[str] = []
    audit_path = tmp_path / "unshocked.audit.json"
    result = _unshocked_plan().run(
        af,
        _fingerprinting_model(seen),
        batch_size=2,
        audit=audit_path,
    )

    standalone = _fingerprinting_model([])(_frame_like(af)).graph.fingerprint()
    payload = read_audit(audit_path)
    assert payload["graph_fingerprint_by_scenario"] == {
        "BASE": standalone,
        "STRESS": standalone,
    }
    assert payload["graph_fingerprint"] == standalone
    assert result.graph_fingerprint == standalone
    assert result.graph_fingerprint_by_scenario == {
        "BASE": standalone,
        "STRESS": standalone,
    }


def test_the_policy_axis_record_carries_no_per_scenario_map(tmp_path: Path) -> None:
    """A run with no scenario axis has no scenario to key a map by."""
    from gaspatchio.scenarios import run_aggregated

    audit_path = tmp_path / "policy_map.audit.json"
    run_aggregated(
        _policy_model,
        _policy_book(),
        [Sum("loss").alias("total")],
        batch_size=3,
        audit=audit_path,
    )

    payload = read_audit(audit_path)
    assert payload["graph_fingerprint_by_scenario"] is None
    assert payload["graph_fingerprint"] is not None


def test_two_readings_of_one_scenario_that_disagree_are_no_reading() -> None:
    """A scenario's basis is constant, so a disagreement is a defect, not a stamp."""
    from gaspatchio.scenarios._for_each import _note_scenario_graph

    graphs: dict[str | int, str | None] = {}
    _note_scenario_graph(graphs, "STRESS", f"sha256:{'a' * 64}")
    _note_scenario_graph(graphs, "STRESS", f"sha256:{'b' * 64}")
    assert graphs == {"STRESS": None}


def test_a_scenario_named_by_a_number_is_keyed_by_that_name_in_the_record() -> None:
    """JSON has string keys only, so the record says so rather than losing entries."""
    from gaspatchio.scenarios._audit import graph_fingerprint_map

    stamped = graph_fingerprint_map({1: "sha256:x", 2: None})
    assert stamped == {"1": "sha256:x", "2": None}
    assert graph_fingerprint_map(None) is None


# --- a record asked for never costs the run its numbers (GSP-127) -----------


def _book_carrying(extra: pl.Series) -> pl.DataFrame:
    """Return the policy book with one column the graph vocabulary cannot name."""
    return pl.DataFrame(
        {
            "policy_id": list(range(1, 5)),
            "premium": [100.0, 200.0, 300.0, 150.0],
        }
    ).with_columns(extra)


_UNNAMEABLE = [
    pytest.param(
        pl.Series("product", ["term", "wl", "term", "wl"], dtype=pl.Categorical),
        id="categorical",
    ),
    pytest.param(
        pl.Series("rider", [{"kind": "waiver", "amount": 1.0}] * 4),
        id="struct",
    ),
    pytest.param(
        pl.Series("reinsurance_id", [None] * 4, dtype=pl.Null),
        id="all_null",
    ),
]


@pytest.mark.parametrize("extra", _UNNAMEABLE)
def test_a_column_the_record_cannot_name_makes_it_say_less_not_the_run_say_nothing(
    tmp_path: Path,
    extra: pl.Series,
) -> None:
    """An unnameable column drops out of the stamp; the run still hands back numbers."""
    from gaspatchio._identity import content_sha_of
    from gaspatchio.scenarios import run_aggregated

    book = _book_carrying(extra)
    audit_path = tmp_path / "unnameable.audit.json"
    quiet = run_aggregated(
        _policy_model, book, [Sum("loss").alias("total")], batch_size=2
    )
    recorded = run_aggregated(
        _policy_model,
        book,
        [Sum("loss").alias("total")],
        batch_size=2,
        audit=audit_path,
    )

    assert recorded.aggregations["total"] == quiet.aggregations["total"]
    payload = read_audit(audit_path)
    assert payload["graph_fingerprint"] is None
    stamped = payload["input_data_fingerprint"]["model_points"]
    assert stamped["content_sha"] == content_sha_of(book.drop(extra.name))
    assert stamped["columns_not_stamped"] == [
        {"column": extra.name, "dtype": str(extra.dtype)}
    ]
    assert payload["aggregator_outputs"]["total"] == quiet.aggregations["total"]


def test_the_scenario_record_over_an_unnameable_column_keeps_the_run_alive(
    tmp_path: Path,
) -> None:
    """The scenario axis stamps what it can the same way the policy axis does."""
    from gaspatchio._identity import content_sha_of

    book = _book_carrying(
        pl.Series("product", ["term", "wl", "term", "wl"], dtype=pl.Categorical)
    )
    audit_path = tmp_path / "scenario_unnameable.audit.json"

    def model_fn(
        frame: ActuarialFrame,
        *,
        tables: dict[str, Table] | None = None,  # noqa: ARG001
        drivers: dict[str, Any] | None = None,  # noqa: ARG001
    ) -> ActuarialFrame:
        frame.loss = frame.premium * 0.01
        return frame

    result = _unshocked_plan().run(
        ActuarialFrame(book),
        model_fn,
        batch_size=2,
        audit=audit_path,
    )

    payload = read_audit(audit_path)
    assert payload["graph_fingerprint"] is None
    assert payload["graph_fingerprint_by_scenario"] == {"BASE": None, "STRESS": None}
    stamped = payload["input_data_fingerprint"]["model_points"]
    assert stamped["content_sha"] == content_sha_of(book.drop("product"))
    assert stamped["columns_not_stamped"] == [
        {"column": "product", "dtype": "Categorical"}
    ]
    assert result.aggregations["total"] == pytest.approx(15.0)


def test_asking_a_shocked_run_for_a_record_does_not_move_its_numbers(
    tmp_path: Path,
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """Stamping each scenario alone re-reads its bases; the fold must not see it."""
    plan = _shocked_plan(mortality_table, "BASE", "STRESS")
    quiet = plan.run(af, _reading_model, batch_size=2)
    split = plan.run(af, _reading_model, batch_size=1, audit=tmp_path / "one.json")
    stacked = plan.run(af, _reading_model, batch_size=2, audit=tmp_path / "two.json")

    assert split.aggregations["total"] == pytest.approx(quiet.aggregations["total"])
    assert stacked.aggregations["total"] == pytest.approx(quiet.aggregations["total"])


# --- the data stamp covers what it can and names what it cannot -------------


def _stamped(book: pl.DataFrame) -> Any:  # noqa: ANN401 - a digest or an object
    """Return what the record's ``model_points`` key carries for this book."""
    from gaspatchio.scenarios._audit import model_points_fingerprint

    return model_points_fingerprint(book)["model_points"]


def _wide_book() -> pl.DataFrame:
    """Return a book with one column of every type the grammar can name."""
    return _policy_book().with_columns(
        pl.Series("issue_date", ["2020-01-01"] * 8).str.to_date(),
        pl.Series("policy_term", [10] * 8, dtype=pl.Int32),
        pl.Series("sum_assured", [50_000.0] * 8, dtype=pl.Float32),
        pl.Series("lob", ["motor", "home"] * 4),
        pl.Series("smoker", [True, False] * 4),
        pl.Series("account_value", [[1.0, 2.0, 3.0]] * 8),
    )


def test_a_book_with_no_unnameable_column_stamps_exactly_what_it_always_did() -> None:
    """The ordinary book answers with the bare digest, unmoved to the byte."""
    from gaspatchio._identity import content_sha_of

    book = _wide_book()
    stamped = _stamped(book)

    assert isinstance(stamped, str)
    assert stamped == content_sha_of(book)


def test_a_category_leaves_every_other_column_stamped_and_names_itself() -> None:
    """One column the grammar cannot name no longer takes the whole book's answer."""
    from gaspatchio._identity import content_sha_of

    book = _wide_book().with_columns(
        pl.Series("product", ["term", "wl"] * 4, dtype=pl.Categorical)
    )
    stamped = _stamped(book)

    assert stamped["content_sha"] == content_sha_of(_wide_book())
    assert stamped["columns_not_stamped"] == [
        {"column": "product", "dtype": "Categorical"}
    ]


def test_the_same_book_with_the_category_as_text_stamps_every_column() -> None:
    """Casting the one refused column away returns the book to a whole claim."""
    from gaspatchio._identity import content_sha_of

    book = _wide_book().with_columns(
        pl.Series("product", ["term", "wl"] * 4, dtype=pl.Categorical)
    )
    as_text = book.with_columns(pl.col("product").cast(pl.String))
    stamped = _stamped(as_text)

    assert isinstance(stamped, str)
    assert stamped == content_sha_of(as_text)
    assert stamped != _stamped(book)["content_sha"]


def test_an_unsigned_column_whose_values_fit_is_stamped_as_the_cast_would_be() -> None:
    """The graph leaf names it i64, so the stamp does -- the same bytes."""
    from gaspatchio._identity import content_sha_of

    book = _wide_book().with_columns(
        pl.Series("member_no", list(range(1, 9)), dtype=pl.UInt64)
    )
    by_hand = book.with_columns(pl.col("member_no").cast(pl.Int64))
    stamped = _stamped(book)

    assert isinstance(stamped, str)
    assert stamped == content_sha_of(by_hand)


def test_an_unsigned_value_past_the_signed_maximum_names_that_column_instead() -> None:
    """No exact name is left for the number, so the column is recorded, not stamped."""
    from gaspatchio._identity import content_sha_of

    values = [*range(1, 8), 2**63]
    book = _wide_book().with_columns(pl.Series("member_no", values, dtype=pl.UInt64))
    stamped = _stamped(book)

    assert stamped["content_sha"] == content_sha_of(_wide_book())
    assert stamped["columns_not_stamped"] == [
        {"column": "member_no", "dtype": "UInt64"}
    ]


def test_a_book_with_nothing_stampable_has_no_digest_and_names_them_all() -> None:
    """A run asked to describe itself cannot die trying, and says why it said little."""
    book = pl.DataFrame(
        {
            "product": pl.Series("product", ["term", "wl"], dtype=pl.Categorical),
            "rider": pl.Series("rider", [{"kind": "waiver"}] * 2),
            "reinsurance_id": pl.Series("reinsurance_id", [None] * 2, dtype=pl.Null),
        }
    )
    stamped = _stamped(book)

    assert stamped["content_sha"] is None
    assert [skipped["column"] for skipped in stamped["columns_not_stamped"]] == [
        "product",
        "rider",
        "reinsurance_id",
    ]


def test_the_written_record_carries_the_digest_beside_what_it_left_out(
    tmp_path: Path,
) -> None:
    """The two travel as one JSON value, so a bare digest cannot be read off it."""
    from gaspatchio._identity import content_sha_of
    from gaspatchio.scenarios import run_aggregated

    book = _policy_book().with_columns(
        pl.Series("product", ["term", "wl"] * 4, dtype=pl.Categorical),
        pl.Series("member_no", list(range(1, 9)), dtype=pl.UInt64),
    )
    audit_path = tmp_path / "partial.audit.json"
    run_aggregated(
        _policy_model,
        book,
        [Sum("loss").alias("total")],
        batch_size=4,
        audit=audit_path,
    )

    stamped = read_audit(audit_path)["input_data_fingerprint"]["model_points"]
    signed = _policy_book().with_columns(
        pl.Series("member_no", list(range(1, 9)), dtype=pl.Int64)
    )
    assert stamped == {
        "content_sha": content_sha_of(signed),
        "columns_not_stamped": [{"column": "product", "dtype": "Categorical"}],
    }


def test_read_audit_refuses_a_file_that_is_not_an_audit(tmp_path: Path) -> None:
    """An audit sidecar is a JSON object; any other JSON is refused by name.

    read_audit returned whatever the file held, so a list came back as though
    it were an audit and failed later, at the first key a caller read.
    """
    not_an_audit = tmp_path / "results.json"
    not_an_audit.write_text("[1, 2, 3]")

    with pytest.raises(ValueError, match="not an object"):
        read_audit(not_an_audit)


@pytest.mark.parametrize(
    ("document", "named"),
    [
        ("[1, 2, 3]", "an array"),
        ('"audit"', "a string"),
        ("5", "a number"),
        ("2.5", "a number"),
        ("true", "a boolean"),
        ("null", "null"),
    ],
)
def test_read_audit_names_the_json_value_it_found(
    tmp_path: Path, document: str, named: str
) -> None:
    """The refusal names the JSON value the file holds, not a Python type.

    It said "a int" and "a NoneType": the class Python parsed the value into,
    which a reader of the JSON file never wrote.
    """
    not_an_audit = tmp_path / "results.json"
    not_an_audit.write_text(document)

    with pytest.raises(ValueError, match=f"its JSON is {named}, not an object"):
        read_audit(not_an_audit)
