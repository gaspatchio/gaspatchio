# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: End-to-end audit-chain integration test for v0.2 ScenarioRun.
# ABOUTME: Pins SHA stability, batch-equiv, YAML round-trip, audit sidecar.
# ruff: noqa: PD901
"""End-to-end v0.2 audit-chain integration test (GSP-101)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

if TYPE_CHECKING:
    from pathlib import Path

from gaspatchio_core.assumptions import Table
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import (
    ArgMax,
    Mean,
    Sum,
)
from gaspatchio_core.scenarios._audit import read_audit
from gaspatchio_core.scenarios._run import ScenarioRun
from gaspatchio_core.scenarios.shocks import MultiplicativeShock


@pytest.fixture
def mortality_table() -> Table:
    """Three-row mortality table shared across the integration test."""
    df = pl.DataFrame({"age": [30, 31, 32], "rate": [0.001, 0.0012, 0.0015]})
    return Table(name="mortality", source=df, dimensions={"age": "age"}, value="rate")


@pytest.fixture
def af() -> ActuarialFrame:
    """Eight-policy frame with cycling LOB to exercise partition aggregator."""
    return ActuarialFrame({
        "policy_id": list(range(1, 9)),
        "age": [30, 31, 32, 30, 31, 32, 30, 31],
        "premium": [100.0, 200.0, 300.0, 150.0, 250.0, 350.0, 175.0, 225.0],
    })


def _model_fn(
    af: ActuarialFrame,
    *,
    tables: dict[str, Table] | None = None,  # noqa: ARG001
    drivers: dict[str, Any] | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Add a deterministic ``lob`` column + ``loss`` projection."""
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
    assert one.aggregations["by_lob"].sort("lob").equals(
        two.aggregations["by_lob"].sort("lob"),
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
    assert rerun.aggregations["by_lob"].sort("lob").equals(
        original.aggregations["by_lob"].sort("lob"),
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
    assert payload["schema_version"] == "2.0"
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
    """The audit sidecar carries the batch-search selection at schema 2.0."""
    from gaspatchio_core.scenarios._audit import AUDIT_SCHEMA_VERSION, read_audit

    assert AUDIT_SCHEMA_VERSION == "2.0"

    frame = ActuarialFrame(pl.DataFrame({"policy_id": range(50), "v": [1.0] * 50}))

    def model_fn(a: ActuarialFrame, *, tables: object = None, drivers: object = None) -> ActuarialFrame:  # noqa: ARG001
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

    from gaspatchio_core.scenarios._audit import _coerce_outputs_to_json

    outputs = {
        "period_total": np.array([1.0, 2.0, 3.0]),
        "period_q": {0.5: np.array([10.0, 20.0])},
    }
    coerced = _coerce_outputs_to_json(outputs)
    # Plain json.dumps (no default=str) must succeed -> values are real lists/numbers.
    reloaded = json.loads(json.dumps(coerced))
    assert reloaded["period_total"] == [1.0, 2.0, 3.0]
    assert reloaded["period_q"]["0.5"] == [10.0, 20.0]  # float key -> str in JSON
