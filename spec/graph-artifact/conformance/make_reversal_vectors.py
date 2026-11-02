# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the cases for a backward recurrence and a list turned end for end.

Section 11.1.20 gives ``projection.accumulate`` a ``reverse`` attribute: under
``true`` the recurrence runs from each policy's own last period back to its
first, ``s[t] = s[t + 1] * multiplier[t] + addend[t]`` opening at
``s[T] = initial``, and a period with no multiplier or no addend loses every
earlier position. Section 11.1.41 states ``list.reverse``: position ``t`` of
the answer is the operand's position ``T_i - 1 - t`` within the policy's own
length, a null moving with its position.

Every expected answer is worked from those two clauses by hand, and **none
was read off the producer**: the producer is what these cases test. The
multipliers are halves, wholes and their negatives, so every state is exact in
a double and every case is pinned at zero tolerance; the one workbook-shaped
case uses 0.9 and states the doubles the clause's own example prints. Stdlib
only, for the same reason. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_reversal_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** A non-finite operand and a null outer list to the recurrence
stay outside 11.1.20 in either direction, and a per-policy operand to
``list.reverse`` is outside 11.1.41; neither has an answer to publish.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

CASES: list[dict] = []


def col(name: str) -> dict:
    return {"op": "col", "name": name}


def lit(value: float) -> dict:
    return {"op": "lit", "value": value}


def reversed_list(operand: dict) -> dict:
    return {"op": "call", "name": "list.reverse", "args": [operand], "attrs": {}}


def recurrence(initial: dict, multiplier: dict, addend: dict, *, reverse: bool) -> dict:
    return {
        "op": "call",
        "name": "projection.accumulate",
        "args": [initial, multiplier, addend],
        "attrs": {"reverse": reverse},
    }


def add(
    identifier: str,
    expr: dict,
    inputs: dict,
    expected: tuple[str, list],
    *,
    covers: tuple[str, ...],
) -> None:
    """Add one value case, pinned at zero tolerance."""
    dtype, values = expected
    CASES.append(
        {
            "id": identifier,
            "covers": list(covers),
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


REVERSE = ("list.reverse",)
BACKWARD = ("projection.accumulate",)
OPENING_AND_STEPS = recurrence(
    col("initial"), col("multiplier"), col("addend"), reverse=True
)


# --- 11.1.41: a list turned end for end within each policy ------------------

# Three policies of three lengths: each is reversed within its own, so the
# one-period policy is unchanged and the empty one stays empty.
add(
    "list-reverse-jagged",
    reversed_list(col("x")),
    {"x": ("list[f64]", [[10.0, 20.0, 30.0], [5.0], []])},
    ("list[f64]", [[30.0, 20.0, 10.0], [5.0], []]),
    covers=REVERSE,
)
# The element type is the operand's, whatever it is (section 10).
add(
    "list-reverse-i64",
    reversed_list(col("x")),
    {"x": ("list[i64]", [[1, 2, 3, 4], [7, 8]])},
    ("list[i64]", [[4, 3, 2, 1], [8, 7]]),
    covers=REVERSE,
)
add(
    "list-reverse-bool",
    reversed_list(col("x")),
    {"x": ("list[bool]", [[True, False, False]])},
    ("list[bool]", [[False, False, True]]),
    covers=REVERSE,
)
add(
    "list-reverse-str",
    reversed_list(col("x")),
    {"x": ("list[str]", [["issue", "anniversary", "maturity"]])},
    ("list[str]", [["maturity", "anniversary", "issue"]]),
    covers=REVERSE,
)
add(
    "list-reverse-date",
    reversed_list(col("x")),
    {"x": ("list[date]", [["2025-01-31", "2025-02-28"]])},
    ("list[date]", [["2025-02-28", "2025-01-31"]]),
    covers=REVERSE,
)
# 11.1.41: "a period carrying no value moves with its position and stays a
# period carrying no value". [1, null, 3] answers [3, null, 1], and a run of
# one null is a run of one null -- nothing beside it becomes unknown.
add(
    "list-reverse-null-moves",
    reversed_list(col("x")),
    {"x": ("list[f64]", [[1.0, None, 3.0], [None], [None, 2.0]])},
    ("list[f64]", [[3.0, None, 1.0], [None], [2.0, None]]),
    covers=REVERSE,
)
# 11.1.41: "a null outer list answers null" -- a policy with no column, not a
# policy with no periods, which is the empty list beside it.
add(
    "list-reverse-null-outer",
    reversed_list(col("x")),
    {"x": ("list[f64]", [None, [1.0, 2.0], []])},
    ("list[f64]", [None, [2.0, 1.0], []]),
    covers=REVERSE,
)
add(
    "empty-portfolio-list.reverse",
    reversed_list(col("x")),
    {"x": ("list[f64]", [])},
    ("list[f64]", []),
    covers=REVERSE,
)
# A permutation applied twice is the identity, policy by policy.
add(
    "list-reverse-twice",
    reversed_list(reversed_list(col("x"))),
    {"x": ("list[f64]", [[1.0, 2.0, 3.0], [4.0]])},
    ("list[f64]", [[1.0, 2.0, 3.0], [4.0]]),
    covers=REVERSE,
)


# --- 11.1.20: the recurrence run back from each policy's last period --------

# Policy one: s[3] = 0; s[2] = 0 * 0.5 + 3 = 3; s[1] = 3 * 0.5 + 2 = 3.5;
# s[0] = 3.5 * 0.5 + 1 = 2.75. Policy two has one period and opens at 10:
# 10 * 2 + 1 = 21. Policy three has none. Each opens at its own last period,
# which on a jagged book is three different positions.
add(
    "accumulate-reverse-jagged",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", [0.0, 10.0, 5.0]),
        "multiplier": ("list[f64]", [[0.5, 0.5, 0.5], [2.0], []]),
        "addend": ("list[f64]", [[1.0, 2.0, 3.0], [1.0], []]),
    },
    ("list[f64]", [[2.75, 3.5, 3.0], [21.0], []]),
    covers=BACKWARD,
)
# 11.1.20: "Zero and negative multipliers are ordinary values". From the end:
# s[2] = 4 * 2 + 1 = 9; s[1] = 9 * 0 + 1 = 1; s[0] = 1 * -1 + 1 = 0. A
# division by a cumulative product would have no answer past the zero.
add(
    "accumulate-reverse-zero-and-negative-multiplier",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", [4.0]),
        "multiplier": ("list[f64]", [[-1.0, 0.0, 2.0]]),
        "addend": ("list[f64]", [[1.0, 1.0, 1.0]]),
    },
    ("list[f64]", [[0.0, 1.0, 9.0]]),
    covers=BACKWARD,
)
# A literal multiplier is broadcast along the addend's periods (11.1.18):
# s[1] = 100 * 0.5 + 20 = 70; s[0] = 70 * 0.5 + 10 = 45.
add(
    "accumulate-reverse-literal-multiplier",
    recurrence(col("initial"), lit(0.5), col("addend"), reverse=True),
    {
        "initial": ("f64", [100.0]),
        "addend": ("list[f64]", [[10.0, 20.0]]),
    },
    ("list[f64]", [[45.0, 70.0]]),
    covers=BACKWARD,
)
# And a literal addend along the multiplier's: s[1] = 1 * 3 + 1 = 4;
# s[0] = 4 * 2 + 1 = 9.
add(
    "accumulate-reverse-literal-addend",
    recurrence(col("initial"), col("multiplier"), lit(1.0), reverse=True),
    {
        "initial": ("f64", [1.0]),
        "multiplier": ("list[f64]", [[2.0, 3.0]]),
    },
    ("list[f64]", [[9.0, 4.0]]),
    covers=BACKWARD,
)
# The clause's own workbook rollback: V[t] = 0.9 * V[t+1] + cf[t], opening at
# nought after the last period, printed as the doubles the clause prints --
# 3.0, then 0.9 * 3.0 + 2.0, then 0.9 * that + 1.0, each one IEEE product and
# one IEEE sum, which is the order the recurrence states.
add(
    "accumulate-reverse-workbook-rollback",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", [0.0]),
        "multiplier": ("list[f64]", [[0.9, 0.9, 0.9]]),
        "addend": ("list[f64]", [[1.0, 2.0, 3.0]]),
    },
    ("list[f64]", [[5.23, 4.7, 3.0]]),
    covers=BACKWARD,
)
# 11.1.20, the forward recurrence written between two reversals (11.1.41):
# the steps reversed, run forward from the same opening, and the answer
# reversed back. It is the same doubles as the case above, which is the
# clause's claim that the two spellings are one calculation.
add(
    "accumulate-between-two-reversals",
    reversed_list(
        recurrence(
            col("initial"),
            reversed_list(col("multiplier")),
            reversed_list(col("addend")),
            reverse=False,
        )
    ),
    {
        "initial": ("f64", [0.0, 10.0]),
        "multiplier": ("list[f64]", [[0.9, 0.9, 0.9], [2.0]]),
        "addend": ("list[f64]", [[1.0, 2.0, 3.0], [1.0]]),
    },
    ("list[f64]", [[5.23, 4.7, 3.0], [21.0]]),
    covers=("list.reverse", "projection.accumulate"),
)
add(
    "accumulate-reverse-empty-portfolio",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", []),
        "multiplier": ("list[f64]", []),
        "addend": ("list[f64]", []),
    },
    ("list[f64]", []),
    covers=BACKWARD,
)


# --- 11.1.20 under reverse: a lost step loses every earlier position --------

# The clause's own example. From the end: s[3] = 10 * 4 + 1 = 41 and
# s[2] = 41 * 3 + 1 = 124; position 1 has no multiplier, so it and position 0
# are unknown. A run that skipped the hole would report 124 * 2 + 1 = 249 at
# position 0 -- a reserve with a period's discounting missing from under it.
add(
    "null-accumulate-reverse-multiplier",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", [10.0]),
        "multiplier": ("list[f64]", [[2.0, None, 3.0, 4.0]]),
        "addend": ("list[f64]", [[1.0, 1.0, 1.0, 1.0]]),
    },
    ("list[f64]", [[None, None, 124.0, 41.0]]),
    covers=BACKWARD,
)
# And the addend: s[3] = 10 * 2 + 4 = 24, and position 2 has no addend.
add(
    "null-accumulate-reverse-addend",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", [10.0]),
        "multiplier": ("list[f64]", [[2.0, 2.0, 2.0, 2.0]]),
        "addend": ("list[f64]", [[1.0, 2.0, None, 4.0]]),
    },
    ("list[f64]", [[None, None, None, 24.0]]),
    covers=BACKWARD,
)
# The hole at the last period, where a reverse run starts: it reaches no state.
add(
    "null-accumulate-reverse-last-period",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", [10.0]),
        "multiplier": ("list[f64]", [[3.0, 4.0, None]]),
        "addend": ("list[f64]", [[1.0, 1.0, 1.0]]),
    },
    ("list[f64]", [[None, None, None]]),
    covers=BACKWARD,
)
# "A null initial answers a run of nulls of the period count" in either
# direction: there is no state to open with at either end.
add(
    "null-accumulate-reverse-initial",
    OPENING_AND_STEPS,
    {
        "initial": ("f64", [None]),
        "multiplier": ("list[f64]", [[2.0, 3.0]]),
        "addend": ("list[f64]", [[1.0, 1.0]]),
    },
    ("list[f64]", [[None, None]]),
    covers=BACKWARD,
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
        "family": "A backward recurrence and a list turned end for end",
        "cases": CASES,
    }
    (VECTORS / "reversal.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("reversal cases", len(CASES))


if __name__ == "__main__":
    main()
