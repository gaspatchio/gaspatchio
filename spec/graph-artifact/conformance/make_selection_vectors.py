# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for a recorded selection, applied to the book before the answer.

Section 7.6 records each step that chose which rows a model values -- a
filter, a semi join, an anti join -- and a consumer replaying a document
applies them to the book, in order, before it computes anything. A
``selection-value`` case states the book under ``inputs``, the steps under
``selection`` exactly as a document's entries carry them (``kind`` and the
predicate's ``expr``; for a join, the right side it matched against under
``right``), and an ``expr`` evaluated over the rows the steps keep. The
answer is that column over the kept rows, in the book's order.

Every expected answer is worked from section 7.6 by hand, and **none was read
off the producer**: the producer is what these cases test. A filter keeps a
row where its predicate is true and drops it where the predicate is false or
null; a semi join keeps a row whose key the right side holds, an anti join one
whose key it does not; the steps compose in order. Stdlib only, for the same
reason. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_selection_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**The one value not worked here** is a join's ``right_fingerprint``: section
12.3's content grammar over the right side in canonical form, which a
standard-library generator does not carry. The two digests below were taken
by the producer over ``{"product": ["A", "C"]}`` and ``{"product": ["C"]}``,
and the producer's own check of every case (``tests/graph/test_operation_
vectors.py``) asserts the step it records carries the same one, so a digest
copied wrong here fails there.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)
RIGHT_A_C = "sha256:1c6fb6fbefabc32dd0361dc4c0c700989a3eaa238b1299b41f4292f9a825c8c0"
RIGHT_C = "sha256:22a18773d21d67da3989d15eed43f41406fd796a63ed0337da7918cca5671f18"

# Four policies, the fourth lapsed: the shape of the adversarial review's book.
BOOK = {
    "policy_id": ("i64", [1, 2, 3, 4]),
    "status": ("str", ["IF", "IF", "IF", "LAPSED"]),
    "issue_age": ("i64", [30, 45, 60, 52]),
    "product": ("str", ["A", "B", "C", "A"]),
    "sum_assured": ("f64", [100000.0, 250000.0, 50000.0, 80000.0]),
}

CASES: list[dict] = []


def col(name: str) -> dict:
    return {"op": "col", "name": name}


def lit(value: object) -> dict:
    return {"op": "lit", "value": value}


def binop(kind: str, left: dict, right: dict) -> dict:
    return {"op": "binop", "kind": kind, "left": left, "right": right}


def in_force() -> dict:
    return {"kind": "filter", "expr": binop("eq", col("status"), lit("IF"))}


def matched(how: str, right: dict, fingerprint: str) -> dict:
    """Return a semi or anti join step on ``product`` against ``right``."""
    return {
        "kind": how,
        "expr": {
            "op": "call",
            "name": "join",
            "args": [],
            "attrs": {"on": "product", "how": how, "right_fingerprint": fingerprint},
        },
        "right": right,
    }


def add(  # noqa: PLR0913 -- one argument per field of the case
    identifier: str,
    covers: tuple[str, ...],
    selection: list[dict],
    expected: tuple[str, list[object]],
    *,
    book: dict | None = None,
    answer: str = "policy_id",
) -> None:
    """Add one case: the book, its steps, and the answer column over the kept rows."""
    dtype, values = expected
    CASES.append(
        {
            "id": identifier,
            "covers": list(covers),
            "inputs": {
                name: {"dtype": d, "values": v}
                for name, (d, v) in (book or BOOK).items()
            },
            "selection": selection,
            "expr": col(answer),
            "producer_check": True,
            "case_kind": "selection-value",
            "expected": {"dtype": dtype, "values": values},
            "comparison": {"atol": 0.0, "rtol": 0.0},
        }
    )


# A filter keeps the rows its predicate holds for: P4 is lapsed.
add("selection-filter-in-force", ("eq",), [in_force()], ("i64", [1, 2, 3]))
add(
    "selection-filter-in-force-sum-assured",
    ("eq",),
    [in_force()],
    ("f64", [100000.0, 250000.0, 50000.0]),
    answer="sum_assured",
)
# A null answer keeps nothing: the second policy's status is missing.
add(
    "selection-filter-null-is-not-kept",
    ("eq",),
    [in_force()],
    ("i64", [1, 3]),
    book={**BOOK, "status": ("str", ["IF", None, "IF", "LAPSED"])},
)
# A compound predicate, in the forms a row predicate is written in.
add(
    "selection-filter-compound",
    ("lt", "and", "is_in"),
    [
        {
            "kind": "filter",
            "expr": binop(
                "and",
                binop("lt", col("issue_age"), lit(50)),
                {
                    "op": "call",
                    "name": "is_in",
                    "args": [col("status"), {"op": "lit", "values": ["IF"]}],
                    "attrs": {"nulls_equal": False},
                },
            ),
        }
    ],
    ("i64", [1, 2]),
)
# A semi join keeps the rows whose key the right side holds; an anti join the rest.
add(
    "selection-semi-join",
    ("join",),
    [matched("semi", {"product": ["A", "C"]}, RIGHT_A_C)],
    ("i64", [1, 3, 4]),
)
add(
    "selection-anti-join",
    ("join",),
    [matched("anti", {"product": ["A", "C"]}, RIGHT_A_C)],
    ("i64", [2]),
)
# Steps compose in the order the model took them.
add(
    "selection-two-steps-in-order",
    ("eq", "join"),
    [in_force(), matched("anti", {"product": ["C"]}, RIGHT_C)],
    ("i64", [1, 2]),
)
# A selection that keeps nothing values nothing.
add(
    "selection-keeps-no-policy",
    ("eq",),
    [{"kind": "filter", "expr": binop("eq", col("status"), lit("PAID_UP"))}],
    ("i64", []),
)


def main() -> None:
    """Write the bundle, refusing a duplicate identifier before it ships."""
    ids = [entry["id"] for entry in CASES]
    if len(ids) != len(set(ids)):
        msg = "case identifiers must be unique within the bundle"
        raise ValueError(msg)
    bundle = {
        "schema": "gaspatchio-operation-vectors/v0-preview.1",
        "artifact_schema": "gaspatchio-graph/v0-preview.2",
        "fingerprint_algorithm": "gspv0-preview-3",
        "family": "Recorded selection applied to the book",
        "cases": CASES,
    }
    (VECTORS / "selection.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("selection cases", len(CASES))


if __name__ == "__main__":
    main()
