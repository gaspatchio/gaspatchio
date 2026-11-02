# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for a NaN put right with a stated value or column.

Section 11.1.13 states ``fill_nan``: the value where it is not NaN -- a
number, an infinity or a null -- and the fill where it is. A null is a
different absence and stays null, because a value that is not there is not
a NaN. The fill is an operand, a value or a column alike, and a per-period
value takes it period for period. Over a whole number there is no NaN to
replace, so every value stands, in the type the value and the fill share.

Every expected answer is worked from that clause by hand, and **none was
read off the producer**: the producer is what these cases test. Every value
is exact in a double, so every case is pinned at zero tolerance. Stdlib only,
for the same reason. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_nan_fill_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** A Boolean, text or date value cannot hold a NaN, and 11.1.13
states no answer over one: a consumer may answer or refuse, so there is no
answer to publish. A per-period fill over a per-policy value would answer a
list for a value that is one number, and is outside the entry.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

CASES: list[dict] = []

NAN = {"nonfinite": "nan"}
PLUS_INF = {"nonfinite": "+inf"}
MINUS_INF = {"nonfinite": "-inf"}


def col(name: str) -> dict:
    return {"op": "col", "name": name}


def lit(value: float) -> dict:
    return {"op": "lit", "value": value}


def filled(operand: dict, fill: dict) -> dict:
    return {"op": "call", "name": "fill_nan", "args": [operand, fill], "attrs": {}}


def add(
    identifier: str,
    expr: dict,
    inputs: dict,
    expected: tuple[str, list],
) -> None:
    """Add one value case, pinned at zero tolerance."""
    dtype, values = expected
    CASES.append(
        {
            "id": identifier,
            "covers": ["fill_nan"],
            "inputs": {
                name: {"dtype": kind, "values": column}
                for name, (kind, column) in inputs.items()
            },
            "expr": expr,
            "producer_check": True,
            "expected": {"dtype": dtype, "values": values},
            "comparison": {"atol": 0.0, "rtol": 0.0},
            "case_kind": "value",
        }
    )


# --- 11.1.13: the NaN replaced, every number beside it kept ----------------

# An infinity is a number an arithmetic named, not a NaN, and is kept.
add(
    "fill-nan-f64-policies",
    filled(col("x"), lit(0.0)),
    {"x": ("f64", [1.5, NAN, PLUS_INF, MINUS_INF])},
    ("f64", [1.5, 0.0, PLUS_INF, MINUS_INF]),
)
# One value at a time inside each policy's own periods, an empty run kept.
add(
    "fill-nan-f64-periods",
    filled(col("x"), lit(0.0)),
    {"x": ("list[f64]", [[0.25, NAN, 0.75], [NAN], []])},
    ("list[f64]", [[0.25, 0.0, 0.75], [0.0], []]),
)

# --- 11.1.13: a null is the other absence, and stays null -------------------

add(
    "fill-nan-null-stays-null-policies",
    filled(col("x"), lit(0.0)),
    {"x": ("f64", [NAN, None, 2.0])},
    ("f64", [0.0, None, 2.0]),
)
# A null period stays a null period, and a null outer list -- a policy with
# no column, not a policy with no periods -- stays null.
add(
    "fill-nan-null-stays-null-periods",
    filled(col("x"), lit(0.0)),
    {"x": ("list[f64]", [[NAN, None], None, [None]])},
    ("list[f64]", [[0.0, None], None, [None]]),
)

# --- 11.1.13: the fill is an operand, a column as readily as a value --------

add(
    "fill-nan-column-fill-policies",
    filled(col("x"), col("fill")),
    {"x": ("f64", [NAN, 2.0, NAN]), "fill": ("f64", [9.0, 8.0, 7.0])},
    ("f64", [9.0, 2.0, 7.0]),
)
# A per-policy fill reaches every NaN period of its own policy (11.1.18).
add(
    "fill-nan-policy-fill-over-periods",
    filled(col("x"), col("fill")),
    {
        "x": ("list[f64]", [[NAN, 0.5, NAN], [0.25, NAN]]),
        "fill": ("f64", [9.0, 8.0]),
    },
    ("list[f64]", [[9.0, 0.5, 9.0], [0.25, 8.0]]),
)
# A per-period fill reaches the same period, and only that one.
add(
    "fill-nan-period-fill-over-periods",
    filled(col("x"), col("fill")),
    {
        "x": ("list[f64]", [[NAN, 0.5, NAN], [0.25, NAN]]),
        "fill": ("list[f64]", [[1.0, 2.0, 3.0], [4.0, 5.0]]),
    },
    ("list[f64]", [[1.0, 0.5, 3.0], [0.25, 5.0]]),
)
# The fill may be a calculation: twice the policy's own fill column.
add(
    "fill-nan-expression-fill-over-periods",
    filled(
        col("x"),
        {"op": "binop", "kind": "mul", "left": col("fill"), "right": lit(2.0)},
    ),
    {
        "x": ("list[f64]", [[NAN, 0.5], [0.25, NAN]]),
        "fill": ("f64", [4.5, 4.0]),
    },
    ("list[f64]", [[9.0, 0.5], [0.25, 8.0]]),
)

# --- 11.1.13: a whole number holds no NaN, so nothing is replaced -----------

# A decimal fill makes the answer a decimal, the values as they stood.
add(
    "fill-nan-i64-decimal-fill",
    filled(col("x"), lit(0.0)),
    {"x": ("i64", [1, -2, 3])},
    ("f64", [1.0, -2.0, 3.0]),
)
# A whole fill over a whole number keeps the whole number.
add(
    "fill-nan-i64-whole-fill",
    filled(col("x"), lit(0)),
    {"x": ("i64", [1, -2, 3])},
    ("i64", [1, -2, 3]),
)
add(
    "fill-nan-i64-periods",
    filled(col("x"), lit(0.0)),
    {"x": ("list[i64]", [[1, 2], [3], []])},
    ("list[f64]", [[1.0, 2.0], [3.0], []]),
)
# A whole fill over a decimal value is the decimal it stands for.
add(
    "fill-nan-whole-fill-over-decimal",
    filled(col("x"), lit(0)),
    {"x": ("f64", [NAN, 1.5])},
    ("f64", [0.0, 1.5]),
)
add(
    "empty-portfolio-fill_nan",
    filled(col("x"), lit(0.0)),
    {"x": ("f64", [])},
    ("f64", []),
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
        "family": "A NaN put right with a stated value or column",
        "cases": CASES,
    }
    (VECTORS / "nan-fill.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("nan-fill cases", len(CASES))


if __name__ == "__main__":
    main()
