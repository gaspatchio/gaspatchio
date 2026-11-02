# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for a stored indicator standing as a logical operand.

Section 11.1.27 takes a direct reference to a column declared ``f64`` or
``list[f64]`` as an operand of ``and``, ``or`` and ``not_``, read under
section 11.1.18's stored-predicate rule: every value finite, non-null and
exactly ``0.0`` or ``1.0``, a negative zero being zero, and anything else a
refusal at evaluation. A per-policy one stands for its Boolean, so an
all-scalar result is ``bool``; a per-period one is its own 0/1 indicator, so
the result is ``list[f64]`` under the entry's per-position null rule, which a
Boolean operand can still reach.

Every expected answer is worked from those two clauses by hand, and **none
was read off the producer**: the producer is what these cases test. Stdlib
only, for the same reason. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_logical_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** An ``i64`` operand, a numeric literal and an arithmetic result
stay outside the clause, and the producer refuses each while the formula is
written rather than at evaluation, so there is no evaluation to publish.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)
NAN = {"nonfinite": "nan"}
INFINITY = {"nonfinite": "+inf"}

CASES: list[dict] = []


def col(name: str) -> dict:
    return {"op": "col", "name": name}


def both(kind: str) -> dict:
    """Return ``a <kind> b`` over the two input columns."""
    return {"op": "binop", "kind": kind, "left": col("a"), "right": col("b")}


def negated() -> dict:
    return {"op": "call", "name": "not_", "args": [col("a")], "attrs": {}}


def add(
    identifier: str,
    expr: dict,
    inputs: dict,
    *,
    expected: dict | None = None,
    covers: tuple[str, ...] | None = None,
) -> None:
    """Add one case; without ``expected`` it is the stored-predicate refusal."""
    entry: dict = {
        "id": identifier,
        "covers": list(covers or (expr.get("kind") or expr["name"],)),
        "inputs": {name: {"dtype": d, "values": v} for name, (d, v) in inputs.items()},
        "expr": expr,
        "producer_check": True,
    }
    if expected is None:
        entry["refusal"] = "stored-numeric-predicate"
        entry["case_kind"] = "portable-domain-refusal"
    else:
        entry["expected"] = expected
        entry["comparison"] = {"atol": 0.0, "rtol": 0.0}
        entry["case_kind"] = "value"
    CASES.append(entry)


# --- per policy: the stored indicator stands for its Boolean ----------------

# 1.0 is true and 0.0 false; -0.0 is zero, so false. Every Boolean row of the
# truth table the stored column can reach, since a stored indicator is never
# null: 1&T, 1&F, 0&T, 0&F, -0&T.
add(
    "logical-stored-float-and-scalar",
    both("and"),
    {
        "a": ("f64", [1.0, 1.0, 0.0, 0.0, -0.0]),
        "b": ("bool", [True, False, True, False, True]),
    },
    expected={"dtype": "bool", "values": [True, False, False, False, False]},
)
# Two stored indicators meet: 1|0, 0|0, 0|1, -0|0.
add(
    "logical-stored-float-or-scalar",
    both("or"),
    {"a": ("f64", [1.0, 0.0, 0.0, -0.0]), "b": ("f64", [0.0, 0.0, 1.0, 0.0])},
    expected={"dtype": "bool", "values": [True, False, True, False]},
)
add(
    "logical-stored-float-not-scalar",
    negated(),
    {"a": ("f64", [1.0, 0.0, -0.0])},
    expected={"dtype": "bool", "values": [False, True, True]},
)
# Three-valued logic still reaches the Boolean side: false AND null is false.
add(
    "logical-stored-float-and-null-boolean",
    both("and"),
    {"a": ("f64", [0.0, 1.0]), "b": ("bool", [None, None])},
    expected={"dtype": "bool", "values": [False, None]},
)
add(
    "logical-stored-float-empty-portfolio",
    both("and"),
    {"a": ("f64", []), "b": ("bool", [])},
    expected={"dtype": "bool", "values": []},
)

# --- per period: the stored indicator is its own 0/1 run --------------------

# Position by position: 1&T, 1&F, 0&T, and -0 against a null Boolean, which is
# the per-position null rule -- a null operand yields null, even beside zero.
add(
    "logical-stored-float-and-list",
    both("and"),
    {
        "a": ("list[f64]", [[1.0, 1.0, 0.0, -0.0]]),
        "b": ("list[bool]", [[True, False, True, None]]),
    },
    expected={"dtype": "list[f64]", "values": [[1.0, 0.0, 0.0, None]]},
)
# A per-policy indicator repeats along each policy's own periods (11.1.18).
add(
    "logical-stored-float-or-across-shapes",
    both("or"),
    {
        "a": ("f64", [1.0, 0.0]),
        "b": ("list[bool]", [[False, True], [False, True, False]]),
    },
    expected={"dtype": "list[f64]", "values": [[1.0, 1.0], [0.0, 1.0, 0.0]]},
)
add(
    "logical-stored-float-not-list",
    negated(),
    {"a": ("list[f64]", [[1.0, 0.0, -0.0], []])},
    expected={"dtype": "list[f64]", "values": [[0.0, 1.0, 1.0], []]},
)
# The result is a predicate: it stands as a condition directly.
add(
    "logical-stored-float-as-condition",
    {
        "op": "when_then",
        "cond": both("and"),
        "then": {"op": "lit", "value": 10.0},
        "otherwise": {"op": "lit", "value": 20.0},
    },
    {"a": ("f64", [1.0, 1.0, 0.0]), "b": ("bool", [True, False, True])},
    expected={"dtype": "f64", "values": [10.0, 20.0, 20.0]},
    covers=("and", "when_then"),
)

# --- refusals: anything but exactly 0.0 or 1.0 -----------------------------

add(
    "logical-stored-float-two-refuses",
    both("and"),
    {"a": ("f64", [1.0, 2.0]), "b": ("bool", [True, True])},
)
# Not reached by truth: true OR anything is true, and the 0.5 still refuses.
add(
    "logical-stored-float-half-refuses",
    both("or"),
    {"a": ("bool", [True]), "b": ("f64", [0.5])},
)
add("logical-stored-float-nan-refuses", negated(), {"a": ("f64", [NAN])})
add(
    "logical-stored-float-infinity-refuses",
    both("and"),
    {"a": ("list[f64]", [[1.0, INFINITY]]), "b": ("list[bool]", [[True, True]])},
)
# The narrowing 11.1.27 states: a null in a stored indicator is a refusal, not
# the per-position null a Boolean operand earns.
add(
    "logical-stored-float-null-refuses",
    both("or"),
    {"a": ("list[f64]", [[0.0, None]]), "b": ("list[bool]", [[True, False]])},
)
add(
    "logical-stored-float-null-scalar-refuses",
    negated(),
    {"a": ("f64", [None])},
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
        "family": "Stored indicators as logical operands",
        "cases": CASES,
    }
    (VECTORS / "logical.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("logical cases", len(CASES))


if __name__ == "__main__":
    main()
