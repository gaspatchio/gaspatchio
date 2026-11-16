# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for R133, R134 and a horizon named by a maximum age.

R133: section 11.1.8 states that an infinity or a NaN is its own answer under
``floor`` and ``ceil``. R134: section 11.1.21's literal-rate form admits both
timings. Section 11.1.37: with ``until_kind`` ``maximum_age`` a policy's count
is ``max(0, trunc(A - x) * p)`` in whole years.

Every expected answer is worked from those clauses by hand, and **none was
read off the producer**. Every value is exact in a double, so every case is
pinned at zero tolerance: at a rate of 100% each discount factor is a power of
one half. Stdlib only. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_non_finite_and_maximum_age_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py
"""

from __future__ import annotations

import hashlib
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


def add(
    identifier: str,
    covers: str,
    expr: dict,
    inputs: dict,
    expected: tuple[str, list],
    assumptions: list[dict] | None = None,
) -> None:
    """Add one value case, pinned at zero tolerance."""
    dtype, values = expected
    case: dict = {
        "id": identifier,
        "covers": [covers],
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
    if assumptions is not None:
        case["assumptions"] = assumptions
    CASES.append(case)


# --- R133, 11.1.8: an infinity or a NaN is its own answer ------------------

for name in ("floor", "ceil"):
    add(
        f"{name}-non-finite-policies",
        name,
        {"op": "call", "name": name, "args": [col("x")], "attrs": {}},
        {"x": ("f64", [MINUS_INF, PLUS_INF, NAN])},
        ("f64", [MINUS_INF, PLUS_INF, NAN]),
    )
    add(
        f"{name}-non-finite-periods",
        name,
        {"op": "call", "name": name, "args": [col("x")], "attrs": {}},
        {"x": ("list[f64]", [[MINUS_INF, PLUS_INF], [NAN]])},
        ("list[f64]", [[MINUS_INF, PLUS_INF], [NAN]]),
    )


# --- R134, 11.1.21: a literal rate, end of period --------------------------


def present_value(timing: str) -> dict:
    return {
        "op": "call",
        "name": "projection.prospective_value",
        "args": [col("cf"), {"op": "lit", "value": 1.0}],
        "attrs": {"discount_kind": "rate", "timing": timing},
    }


# ord(t) = sum over s >= t of CF[s] * v**(s - t + 1), v = 1/2:
# ord(1) = 20/2 = 10, ord(0) = 10/2 + 20/4 = 10.
add(
    "prospective-value-literal-rate-end-of-period",
    "projection.prospective_value",
    present_value("end_of_period"),
    {"cf": ("list[f64]", [[10.0, 20.0], [8.0]])},
    ("list[f64]", [[10.0, 10.0], [4.0]]),
)
# A hole loses its own position and every earlier one, under this timing too.
add(
    "prospective-value-literal-rate-end-of-period-hole",
    "projection.prospective_value",
    present_value("end_of_period"),
    {"cf": ("list[f64]", [[10.0, None, 8.0]])},
    ("list[f64]", [[None, None, 4.0]]),
)


# --- 11.1.37: a horizon named by a maximum age -----------------------------


def recipe_sha(payload: dict) -> str:
    """Return a recipe's digest under section 12.3's recipe grammar."""
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


AGE_PAYLOAD = {
    "kind": "per_policy_grid",
    "frequency": "1Y",
    "calendar": "NullCalendar",
    "convention": "Unadjusted",
    "day_count": "OneTwelfth",
    "start_date": "2023-11-30",
    "until_kind": "maximum_age",
    "issue_age_column": "age",
    "maximum_age": 102,
}
AGE_SHA = recipe_sha(AGE_PAYLOAD)
AGE_RECIPE = [{"kind": "schedule", "source_sha": AGE_SHA, "payload": AGE_PAYLOAD}]


def on_the_axis(name: str) -> dict:
    return {
        "op": "call",
        "name": f"projection_frame.{name}",
        "args": [col("age")],
        "attrs": {"schedule": AGE_SHA},
    }


# 102 - 99 is three whole years; 102 - 102 and 102 - 103 have no period at all.
add(
    "maximum-age-t-years",
    "projection_frame.t_years",
    on_the_axis("t_years"),
    {"age": ("i64", [99, 102, 103])},
    ("list[f64]", [[0.0, 1.0, 2.0, 3.0], [0.0], [0.0]]),
)
add(
    "maximum-age-period-dates",
    "projection_frame.period_dates",
    on_the_axis("period_dates"),
    {"age": ("i64", [99])},
    ("list[date]", [["2023-11-30", "2024-11-30", "2025-11-30", "2026-11-30"]]),
)
add(
    "maximum-age-anniversary-mask",
    "projection_frame.anniversary_mask",
    on_the_axis("anniversary_mask"),
    {"age": ("i64", [99])},
    ("list[bool]", [[True, True, True]]),
)


def main() -> None:
    """Write the bundle."""
    for case in CASES:
        if "assumptions" not in case and "maximum-age" in case["id"]:
            case["assumptions"] = AGE_RECIPE
    bundle = {
        "schema": "gaspatchio-operation-vectors/v0-preview.1",
        "artifact_schema": "gaspatchio-graph/v0-preview.2",
        "fingerprint_algorithm": "gspv0-preview-3",
        "family": "Non-finite floor and ceil, a literal end-of-period rate, a maximum age",
        "cases": CASES,
    }
    (VECTORS / "non-finite-and-maximum-age.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("non-finite-and-maximum-age cases", len(CASES))


if __name__ == "__main__":
    main()
