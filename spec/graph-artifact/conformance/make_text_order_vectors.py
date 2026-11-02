# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for an ordering over text.

Section 11.1.26 orders scalar text lexicographically by Unicode code point,
and list-shaped text period by period under the same rule -- exact equality,
order by code point, a null element answering null -- against a text value or
another text run of the same length. The answer is the 0/1 indicator: ``f64``
per policy, ``list[f64]`` per period.

Code-point order is not a dictionary's order and not a locale's: a capital
sorts before every small letter (``"B" < "a"``), a string before its own
extension (``"ab" < "abc"``), the empty string first, and an accented letter
after every unaccented ASCII one (``"z" < "é"``). The cases are chosen to
tell those apart from a case-folded or collated order.

Every expected answer is worked from that clause by hand, and **none was read
off the producer**: the producer is what these cases test. Stdlib only, for
the same reason. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_text_order_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** Text against a number or a date is refused while the formula is
written, and two runs of different lengths within one policy are refused
under section 11.1.18, so neither has an evaluation to publish.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

CASES: list[dict] = []


def col(name: str) -> dict:
    """Return a reference to the input column ``name``."""
    return {"op": "col", "name": name}


def add(identifier: str, expr: dict, inputs: dict, result: tuple) -> None:
    """Add one value case whose answer is the indicator, of the dtype given."""
    dtype, values = result
    CASES.append(
        {
            "id": identifier,
            "covers": [expr["kind"]],
            "inputs": {
                name: {"dtype": kind, "values": cells}
                for name, (kind, cells) in inputs.items()
            },
            "expr": expr,
            "producer_check": True,
            "expected": {"dtype": dtype, "values": values},
            "comparison": {"atol": 0.0, "rtol": 0.0},
            "case_kind": "value",
        }
    )


# One value per policy against another: the capital before the small letter
# and not after it, a prefix before its extension, the empty string first, an
# accent after "z", and two equal strings, which are not less than each other.
add(
    "comparison-text-order-scalar",
    {"op": "binop", "kind": "lt", "left": col("a"), "right": col("b")},
    {
        "a": ("str", ["B", "a", "ab", "abc", "", "z", "é", "same"]),
        "b": ("str", ["a", "B", "abc", "ab", "a", "é", "z", "same"]),
    },
    ("f64", [1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0]),
)
# A literal on the left, and an ordering that admits equality: "M" is at or
# after "A", "M" and "Z" by code point, and before "a" and "m".
add(
    "comparison-text-order-literal",
    {
        "op": "binop",
        "kind": "ge",
        "left": {"op": "lit", "value": "M"},
        "right": col("a"),
    },
    {"a": ("str", ["A", "M", "Z", "a", "m"])},
    ("f64", [1.0, 1.0, 0.0, 0.0, 0.0]),
)
# Two runs of one length, period by period, on two policies of different
# lengths: "b" after "a", "B" not after "b", "é" after "e"; "" not after "a",
# "zz" after its own prefix "z".
add(
    "comparison-text-order-runs",
    {"op": "binop", "kind": "gt", "left": col("r"), "right": col("s")},
    {
        "r": ("list[str]", [["b", "B", "é"], ["", "zz"]]),
        "s": ("list[str]", [["a", "b", "e"], ["a", "z"]]),
    },
    ("list[f64]", [[1.0, 0.0, 1.0], [0.0, 1.0]]),
)
# A run against one value per policy: each period's string at or before the
# policy's own -- "B" and "Ba" are not at or before "A", and "a" is after "Z".
add(
    "comparison-text-order-run-against-a-policy-value",
    {"op": "binop", "kind": "le", "left": col("r"), "right": col("p")},
    {
        "r": ("list[str]", [["A", "B", "Ba"], ["Z", "a"]]),
        "p": ("str", ["A", "Z"]),
    },
    ("list[f64]", [[1.0, 0.0, 0.0], [1.0, 0.0]]),
)
# A null answers null, on either shape: a null policy value and a null period.
add(
    "comparison-text-order-null",
    {"op": "binop", "kind": "lt", "left": col("r"), "right": col("p")},
    {
        "r": ("list[str]", [["a", None], ["b"]]),
        "p": ("str", ["b", None]),
    },
    ("list[f64]", [[1.0, None], [None]]),
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
        "family": "Orderings over text",
        "cases": CASES,
    }
    (VECTORS / "text-order.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("text-order cases", len(CASES))


if __name__ == "__main__":
    main()
