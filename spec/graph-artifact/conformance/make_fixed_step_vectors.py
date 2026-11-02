# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for 11.1.1's fourth form, an axis of fixed steps in years.

A fixed-step axis is ``T`` steps of a fixed number of years with no calendar
under it, written ``step_years`` (the step in years) or ``steps_per_year``
(the whole steps a year makes). Section 11.1.1 states the columns its
declaration mints -- ``step`` ``0..T``, ``num_proj_months`` ``T + 1``, and
``month`` ``k * 12 / n`` only where ``steps_per_year`` makes a step whole
months -- and section 11.1.37 states its time: ``k * step_years`` or
``k / steps_per_year``, one IEEE binary64 operation per boundary, **exact**.

Every expected answer is worked from those clauses here, in Python's own
binary64 arithmetic -- which is the clause's arithmetic -- and **none was read
off the producer**. The two time cases are pinned at zero tolerance and are
chosen to discriminate over their twelve steps: ``k * 0.1`` parts from
``k / 10`` at ``k = 3`` and from a running sum of ``0.1`` at ``k = 6``, and
``k / 12`` parts from ``k * (1 / 12)`` and from a running sum of a twelfth at
``k = 5``. A reader that took the other spelling, a running sum, or a product
by a rounded reciprocal fails them. Stdlib only. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_fixed_step_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** The dated readings of a fixed-step axis, and an anniversary on
one written as ``step_years``, are refusals 11.1.37 states; a refusal is not a
value and this bundle publishes values.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

CASES: list[dict] = []

# Two policies, so that every answer is shown to be the one shared axis.
BOOK = {"policy_id": {"dtype": "i64", "values": [1, 2]}}


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


def declaration(n_periods: int, step: dict) -> dict:
    """Return the ``projection_set`` call 11.1.1's fixed-step form writes."""
    return {
        "op": "call",
        "name": "projection_set",
        "args": [],
        "attrs": {
            "frequency": None,
            "until": None,
            "until_value": None,
            "valuation_date": None,
            "n_periods": n_periods,
            **step,
        },
    }


def door(
    identifier: str, n_periods: int, step: dict, column: str, values: list
) -> None:
    """Add one recording-door case: a column the declaration mints."""
    CASES.append(
        {
            "id": identifier,
            "covers": ["projection_set"],
            "inputs": BOOK,
            "expr": declaration(n_periods, step),
            "producer_check": True,
            "case_kind": "recording-door-value",
            "output_column": column,
            "producer_setup": {
                "kind": "projection_set",
                "n_periods": n_periods,
                **step,
            },
            "expected": {"dtype": "list[i64]", "values": [values, values]},
            "comparison": {"atol": 0.0, "rtol": 0.0},
        }
    )


def time(identifier: str, n_periods: int, step: dict, values: list[float]) -> None:
    """Add one ``projection_frame.t_years`` case on a fixed-step recipe, exact."""
    payload = {"kind": "fixed_step", "n_periods": n_periods, **step}
    sha = recipe_sha(payload)
    CASES.append(
        {
            "id": identifier,
            "covers": ["projection_frame.t_years"],
            "inputs": BOOK,
            "expr": {
                "op": "call",
                "name": "projection_frame.t_years",
                "args": [],
                "attrs": {"schedule": sha},
            },
            "producer_check": True,
            "expected": {"dtype": "list[f64]", "values": [values, values]},
            "comparison": {"atol": 0.0, "rtol": 0.0},
            "case_kind": "value",
            "assumptions": [
                {"kind": "schedule", "source_sha": sha, "payload": payload}
            ],
        }
    )


# The multi-state room's Quiz tab steps 0.1 years: its step column, 0..T.
door("door-projection_set-fixed-step", 4, {"step_years": 0.1}, "step", [0, 1, 2, 3, 4])
# A quarter a step is three whole months, so month is minted: k * 12 / 4.
door(
    "door-projection_set-fixed-step-month",
    4,
    {"steps_per_year": 4},
    "month",
    [0, 3, 6, 9, 12],
)

# Time at each boundary, one operation each. k * 0.1 at k = 3 is
# 0.30000000000000004 where k / 10 is 0.3, and at k = 8 it is 0.8 where a
# running sum of 0.1 has reached 0.7999999999999999.
STEPS = 12
time(
    "fixed-step-t-years-step-years",
    STEPS,
    {"step_years": 0.1},
    [k * 0.1 for k in range(STEPS + 1)],
)
# k / 12 at k = 5 is 0.4166666666666667, where k * (1 / 12) is
# 0.41666666666666663, and so is a running sum of a twelfth.
time(
    "fixed-step-t-years-steps-per-year",
    STEPS,
    {"steps_per_year": 12},
    [k / 12 for k in range(STEPS + 1)],
)


def _running(step: float) -> list[float]:
    """Return a running sum of ``step`` from nought, the spelling refused."""
    total, out = 0.0, []
    for _ in range(STEPS + 1):
        out.append(total)
        total += step
    return out


# The cases discriminate, or they prove nothing about the spelling.
assert [k * 0.1 for k in range(STEPS + 1)] != [k / 10 for k in range(STEPS + 1)]
assert [k * 0.1 for k in range(STEPS + 1)] != _running(0.1)
assert [k / 12 for k in range(STEPS + 1)] != [k * (1 / 12) for k in range(STEPS + 1)]
assert [k / 12 for k in range(STEPS + 1)] != _running(1 / 12)


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
        "family": "An axis of fixed steps in years, with no calendar under it",
        "cases": CASES,
    }
    (VECTORS / "fixed-step.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("fixed-step cases", len(CASES))


if __name__ == "__main__":
    main()
