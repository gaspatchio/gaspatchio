# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the kit's citation cases: comparison reports citing the §12.5 corpus.

Run from ``bindings/python`` with ``.venv/bin/python``. Unlike the readers
beside it, this generator uses the producer: each record is what
``compare_results`` writes when handed the corpus as the document both result
files are results of (section 13.1 has the report carry the corpus's seal
beside its fingerprint). The result files are one synthetic policy holding a
value for every node in the corpus's final schema, the same on both sides, so
every line agrees; the comparison is not the point, the citation is. The
second case is the same report handed another export of one model -- the
corpus written at another time, one fingerprint and another seal -- which a
reader must tell apart from the first. Output is deterministic.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl

from gaspatchio.engines.compare import compare_results
from gaspatchio.engines.protocol import ResultManifest
from gaspatchio.frame.graph.artifact import document_digest_of

KIT = (
    Path(__file__).resolve().parents[3]
    / "bindings/python/gaspatchio/schemas/conformance"
)
CORPUS = KIT / "corpus.json"
DESTINATION = KIT / "citations.json"

_VALUE: dict[str, Any] = {
    "f64": 1.5,
    "date": dt.date(2025, 1, 1),
    "list[f64]": [1.0, 2.0],
}
_POLARS: dict[str, Any] = {
    "f64": pl.Float64,
    "date": pl.Date,
    "list[f64]": pl.List(pl.Float64),
}


def _report(document: dict[str, Any]) -> dict[str, Any]:
    """Return the comparison report the producer writes over ``document``."""
    final = [node for node in document["nodes"] if node["in_final_schema"]]
    frame = pl.DataFrame(
        {
            "policy_id": [1],
            **{
                node["id"]: pl.Series(
                    node["id"], [_VALUE[node["dtype"]]], dtype=_POLARS[node["dtype"]]
                )
                for node in final
            },
        }
    )
    manifest = ResultManifest(
        scope="final-schema",
        columns={node["id"]: node["id"] for node in final},
        dtypes={node["id"]: node["dtype"] for node in final},
        row_identity=("policy_id",),
        graph_fingerprint=document["graph_fingerprint"],
        inputs_digest=document["book"]["digest"],
        producer="polars",
        versions={},
    )
    report = compare_results(
        document, frame, frame, before_manifest=manifest, after_manifest=manifest
    )
    return json.loads(json.dumps(report.to_dict(), allow_nan=False))


def _another_export(document: dict[str, Any]) -> dict[str, Any]:
    """Return the corpus written at another time: one fingerprint, another seal."""
    moved = {k: v for k, v in document.items() if k != "document_digest"}
    moved["created_at"] = "2026-11-01T00:00:00Z"
    moved["document_digest"] = document_digest_of(moved)
    return moved


def main() -> None:
    document = json.loads(CORPUS.read_text())
    other = _another_export(document)
    assert other["graph_fingerprint"] == document["graph_fingerprint"]
    assert other["document_digest"] != document["document_digest"]
    bundle = {
        "schema": "gaspatchio-citation-vectors/v0-preview.1",
        "cites": "corpus.json",
        "cases": [
            {
                "id": "compare-report-cites-the-corpus-by-its-seal",
                "record_kind": "compare-report",
                "record": _report(document),
                "findings": [],
            },
            {
                "id": "compare-report-cites-another-export-of-one-model",
                "record_kind": "compare-report",
                "record": _report(other),
                "findings": ["document_digest"],
            },
        ],
    }
    DESTINATION.write_text(json.dumps(bundle, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
