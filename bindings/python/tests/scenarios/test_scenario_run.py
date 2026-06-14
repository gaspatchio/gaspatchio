# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""GSP-101 ScenarioRun aggregator identity + audit wiring."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import Mean, Sum
from gaspatchio_core.scenarios._run import ScenarioRun

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def mortality_table() -> Table:
    """Two-row mortality assumption table keyed by age."""
    data = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
    return Table(
        name="mortality",
        source=data,
        dimensions={"age": "age"},
        value="rate",
    )


@pytest.fixture
def af() -> ActuarialFrame:
    """Tiny two-policy frame used as the input to ``ScenarioRun.run``."""
    return ActuarialFrame(
        {"policy_id": [1, 2], "age": [30, 31], "sum_insured": [100.0, 200.0]},
    )


def _model_fn(af, *, tables, drivers):  # noqa: ANN202, ARG001
    return af.with_columns(pl.col("sum_insured").alias("value"))


def test_aggregations_is_tuple(mortality_table: Table) -> None:
    """ScenarioRun.aggregations is a tuple, not a dict."""
    plan = ScenarioRun(
        shocks={"BASE": []},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum(column="value").alias("total"),),
    )
    assert isinstance(plan.aggregations, tuple)
    assert len(plan.aggregations) == 1


def test_empty_aggregations_raises(mortality_table: Table) -> None:
    """Empty tuple raises at construction."""
    with pytest.raises(ValueError, match="aggregations"):
        ScenarioRun(
            shocks={"BASE": []},
            base_tables={"mortality": mortality_table},
            aggregations=(),
        )


def test_duplicate_aliases_raises(mortality_table: Table) -> None:
    """Duplicate aliases raise at construction."""
    with pytest.raises(ValueError, match="alias"):
        ScenarioRun(
            shocks={"BASE": []},
            base_tables={"mortality": mortality_table},
            aggregations=(
                Sum(column="value").alias("total"),
                Mean(column="value").alias("total"),
            ),
        )


def test_aggregator_missing_alias_raises(mortality_table: Table) -> None:
    """All aggregators must have .alias() before passing to ScenarioRun."""
    with pytest.raises(ValueError, match="alias"):
        ScenarioRun(
            shocks={"BASE": []},
            base_tables={"mortality": mortality_table},
            aggregations=(Sum(column="value"),),  # no .alias()
        )


def test_canonical_form_is_sorted_by_alias(mortality_table: Table) -> None:
    """canonical_form's aggregations list is sorted by alias for deterministic SHA."""
    p1 = ScenarioRun(
        shocks={"BASE": []},
        base_tables={"mortality": mortality_table},
        aggregations=(
            Sum(column="value").alias("z"),
            Mean(column="value").alias("a"),
        ),
    )
    p2 = ScenarioRun(
        shocks={"BASE": []},
        base_tables={"mortality": mortality_table},
        aggregations=(
            Mean(column="value").alias("a"),
            Sum(column="value").alias("z"),
        ),
    )
    assert p1.source_sha() == p2.source_sha()


def test_run_returns_typed_aggregations(
    af: ActuarialFrame,
    mortality_table: Table,
) -> None:
    """ScenarioRun.run() delegates to for_each_scenario; aliases survive as keys."""
    plan = ScenarioRun(
        shocks={"A": [], "B": []},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum(column="value").alias("total"),),
    )
    result = plan.run(af, _model_fn)
    assert "total" in result.aggregations


def test_run_no_audit_by_default(
    af: ActuarialFrame,
    mortality_table: Table,
    tmp_path: Path,
) -> None:
    """Default audit=False -> no sidecar written, audit_path is None."""
    os.chdir(tmp_path)  # so the default location is under tmp_path
    plan = ScenarioRun(
        shocks={"A": []},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum(column="value").alias("total"),),
    )
    result = plan.run(af, _model_fn)
    assert result.audit_path is None
    # No directory was created
    assert not (tmp_path / "gaspatchio_audit").exists()


def test_run_audit_true_writes_default_location(
    af: ActuarialFrame,
    mortality_table: Table,
    tmp_path: Path,
) -> None:
    """audit=True writes <cwd>/gaspatchio_audit/<run_id>.audit.json."""
    os.chdir(tmp_path)
    plan = ScenarioRun(
        shocks={"A": []},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum(column="value").alias("total"),),
    )
    result = plan.run(af, _model_fn, audit=True)
    assert result.audit_path is not None
    assert result.audit_path.exists()
    # Path is inside ./gaspatchio_audit/
    assert result.audit_path.parent.name == "gaspatchio_audit"
    # JSON contains expected top-level fields
    data = json.loads(result.audit_path.read_text())
    assert "schema_version" in data
    assert "source_sha" in data
    assert "plan_canonical_form" in data
    assert "aggregator_outputs" in data
    assert data["aggregator_outputs"]["total"] == result.aggregations["total"]


def test_run_audit_explicit_path(
    af: ActuarialFrame,
    mortality_table: Table,
    tmp_path: Path,
) -> None:
    """audit=Path(...) writes to that specific path."""
    plan = ScenarioRun(
        shocks={"A": []},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum(column="value").alias("total"),),
    )
    audit_path = tmp_path / "custom_audit.json"
    result = plan.run(af, _model_fn, audit=audit_path)
    assert result.audit_path == audit_path
    assert audit_path.exists()


def test_with_extra_aggregations_variadic(mortality_table: Table) -> None:
    """with_extra_aggregations now takes variadic aggregators."""
    plan = ScenarioRun(
        shocks={"BASE": []},
        base_tables={"mortality": mortality_table},
        aggregations=(Sum(column="value").alias("total"),),
    )
    extended = plan.with_extra_aggregations(Mean(column="value").alias("avg"))
    assert len(plan.aggregations) == 1
    assert len(extended.aggregations) == 2
    aliases: set[str] = set()
    for agg in extended.aggregations:
        # _BaseAggregator stores alias on .alias_ (bare attribute); .alias is a method.
        # _Partitioned stores alias on .alias (bare str attribute).
        alias_attr = getattr(agg, "alias_", None)
        if alias_attr is None:
            alias_attr = getattr(agg, "alias", None)
        assert isinstance(alias_attr, str)
        aliases.add(alias_attr)
    assert aliases == {"total", "avg"}
