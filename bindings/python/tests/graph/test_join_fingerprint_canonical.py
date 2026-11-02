# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A join's right side is identified by what it holds, not how it was laid out.

Spec section 12.3 puts a join's right side in canonical form before it is
hashed -- columns ascending by name, rows sorted by every column -- so the
same expense table handed over with its columns or rows in another order
carries one ``right_fingerprint``, one ``assumptions`` entry and one graph
fingerprint, and a changed value moves all three.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, diff_artifacts, validate_artifact

_KIT = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"

_EXPENSES = pl.DataFrame(
    {"product": ["A", "B", "C"], "expense": [10.0, 12.0, 9.5], "load": [0.1, 0.2, 0.15]}
)


def _record(right: pl.DataFrame) -> dict[str, Any]:
    af = ActuarialFrame({"product": ["B", "A"], "sum_assured": [1.0, 2.0]})
    af = af.join(right, on="product")
    af.cost = af.expense * af.sum_assured
    document = GraphExporter(af).export(profile="executable", include_tables="all")
    return json.loads(document)


def _stamps(record: dict[str, Any]) -> tuple[str, str, str]:
    (entry,) = [e for e in record["assumptions"] if e["kind"] == "join"]
    (node,) = [
        n
        for n in record["nodes"]
        if (n.get("expr") or {}).get("name") == "join" and n.get("column") == "expense"
    ]
    return (
        entry["fingerprint"],
        node["expr"]["attrs"]["right_fingerprint"],
        record["graph_fingerprint"],
    )


def _kit_identity(payload: dict[str, Any]) -> str:
    program = (
        "import json, sys; sys.path.insert(0, '.');"
        "from reader.tables import table_identity;"
        "print(table_identity(json.load(sys.stdin)))"
    )
    done = subprocess.run(  # noqa: S603 -- this interpreter, the repository's kit
        [sys.executable, "-I", "-c", program],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=_KIT,
        check=True,
    )
    return done.stdout.strip()


def test_a_column_reorder_moves_nothing() -> None:
    published = _record(_EXPENSES)
    reordered = _record(_EXPENSES.select("load", "expense", "product"))

    assert _stamps(published) == _stamps(reordered)
    assert not diff_artifacts(published, reordered).drift


def test_a_row_reorder_moves_nothing() -> None:
    assert _stamps(_record(_EXPENSES)) == _stamps(_record(_EXPENSES.reverse()))


def test_a_changed_value_moves_every_reader() -> None:
    before = _record(_EXPENSES)
    after = _record(
        _EXPENSES.with_columns(
            pl.when(pl.col("product") == "C")
            .then(9.75)
            .otherwise(pl.col("expense"))
            .alias("expense")
        )
    )

    was, now = _stamps(before), _stamps(after)
    assert all(a != b for a, b in zip(was, now, strict=True))
    assert now[0] == now[1]
    assert diff_artifacts(before, after).drift


def test_the_payload_is_carried_in_name_order_and_rehashes() -> None:
    record = _record(_EXPENSES.select("load", "product", "expense"))
    (entry,) = [e for e in record["assumptions"] if e["kind"] == "join"]
    payload = entry["payload"]

    assert [c["name"] for c in payload["columns"]] == ["expense", "load", "product"]
    assert validate_artifact(record, deep=True).ok
    assert _kit_identity(payload) == entry["fingerprint"]


def test_the_join_still_answers_by_name() -> None:
    af = ActuarialFrame({"product": ["B", "A"], "sum_assured": [1.0, 2.0]})
    af = af.join(_EXPENSES.select("load", "expense", "product"), on="product")
    af.cost = af.expense * af.sum_assured

    result = af.collect()
    assert result["cost"].to_list() == [12.0, 20.0]
    assert result["load"].to_list() == [0.2, 0.1]
