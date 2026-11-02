# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for a list-shaped date comparison.

Section 11.1.26 compares a run of dates period by period: in chronological
order, with exact equality and a null element answering null, against a date
-- a column or a literal, on either side -- or another date run of the same
length, and its answer is the per-period 0/1 indicator, ``list[f64]``.

Every expected answer is worked from that clause by hand, and **none was read
off the producer**: the producer is what these cases test. Stdlib only, for
the same reason. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_list_date_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** Two runs of different lengths within one policy are refused
under section 11.1.18, and a date against a number, text or a date and time
is refused while the formula is written, so neither has an evaluation to
publish.
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


def add(identifier: str, expr: dict, inputs: dict, values: list) -> None:
    """Add one value case whose answer is the per-period indicator."""
    CASES.append(
        {
            "id": identifier,
            "covers": [expr["kind"]],
            "inputs": {
                name: {"dtype": dtype, "values": cells}
                for name, (dtype, cells) in inputs.items()
            },
            "expr": expr,
            "producer_check": True,
            "expected": {"dtype": "list[f64]", "values": values},
            "comparison": {"atol": 0.0, "rtol": 0.0},
            "case_kind": "value",
        }
    )


# A run against a date column, one per policy: before, on and after the date,
# and a leap day against itself, which is not before itself.
add(
    "comparison-list-date-scalar",
    {"op": "binop", "kind": "lt", "left": col("a"), "right": col("b")},
    {
        "a": (
            "list[date]",
            [["2020-01-01", "2021-06-01", "2021-07-01"], ["2024-02-29"]],
        ),
        "b": ("date", ["2021-06-01", "2024-02-29"]),
    },
    [[1.0, 0.0, 0.0], [0.0]],
)
# A literal on the left: 1 January 2021 is before only the day after it.
add(
    "comparison-list-date-literal",
    {
        "op": "binop",
        "kind": "lt",
        "left": {"op": "lit", "date": "2021-01-01"},
        "right": col("a"),
    },
    {"a": ("list[date]", [["2020-12-31", "2021-01-01", "2021-01-02"]])},
    [[0.0, 0.0, 1.0]],
)
# Two runs of one length, period by period, a null element answering null.
add(
    "comparison-list-date-runs",
    {"op": "binop", "kind": "eq", "left": col("a"), "right": col("b")},
    {
        "a": ("list[date]", [["2020-01-01", None, "2021-01-01"]]),
        "b": ("list[date]", [["2020-01-01", "2020-01-01", "2021-01-02"]]),
    },
    [[1.0, None, 0.0]],
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
        "family": "List-shaped date comparisons",
        "cases": CASES,
    }
    (VECTORS / "list-dates.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("list-date cases", len(CASES))


if __name__ == "__main__":
    main()
