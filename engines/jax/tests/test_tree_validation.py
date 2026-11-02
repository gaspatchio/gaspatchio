# SPDX-FileCopyrightText: 2026 Opio Inc.
# SPDX-License-Identifier: Apache-2.0

"""Inputs-free portability preserves structured inspection and payload refusals."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any  # Heterogeneous artifact JSON.

import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph.validate import validate_artifact
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.vectors import _sealed
from tests.conftest import invocation
from tests.test_lowerings_tables import _rates, _read

if TYPE_CHECKING:
    from pathlib import Path


def document_for(domain: str) -> dict[str, Any]:
    if domain in {
        "duplicate-table",
        "null-table-key",
        "fractional-table-key",
        "missing-answer",
    }:
        payload = _rates()
        if domain == "duplicate-table":
            payload["rows"].append(payload["rows"][0])
        elif domain == "null-table-key":
            payload["rows"][0][0] = None
        elif domain == "fractional-table-key":
            payload["rows"][0][0] = 45.5
        else:
            payload["value"] = "absent"
        return _read(([45.0], [1.0]), payload=payload).document
    one = invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "lit", "value": 1},
        },
        {"a": {"dtype": "i64", "values": [1]}},
        "i64",
    )
    document = copy.deepcopy(one.document)
    if domain.startswith("unknown"):
        node = document["nodes"][0 if domain == "unknown-input" else -1]
        node["dtype"] = "unknown"
        node["in_final_schema"] = False
    else:
        node = document["nodes"][-1]
        node["expr"] = {
            "op": "engine_native",
            "engine": "polars",
            "text": "opaque",
            "deps": ["a"],
        }
        node["tier"] = "engine_native"
        node["engines"] = ["polars"]
    return _sealed(document)


@pytest.mark.parametrize(
    "domain",
    [
        "engine-native",
        "unknown-input",
        "unknown-computed",
        "duplicate-table",
        "null-table-key",
        "fractional-table-key",
        "missing-answer",
    ],
)
def test_tree_and_public_json_preserve_refusals(domain: str, tmp_path: Path) -> None:
    document = document_for(domain)
    assert validate_artifact(document, deep=True).ok
    statuses = JaxEngine().validate_tree(document)
    refused = [status for status in statuses if status.status == "refused"]
    assert refused, domain
    assert all(
        status.node_id and status.condition and status.clause for status in refused
    )
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(document))
    result = CliRunner().invoke(
        app, ["validate", str(artifact), "--engine", "jax", "--json"]
    )
    assert result.exit_code != 0, result.output
    report = json.loads(result.output)
    assert report["engine"]["refused"] == len(refused)
    assert [row for row in report["engine"]["nodes"] if row["status"] == "refused"]
