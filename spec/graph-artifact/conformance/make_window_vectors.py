# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the perturbation vectors: one per window section 9 states.

Section 9 has every aggregation read state the periods it reads,
``periods: {from, to}``, and a literal ``list.get`` the ``position`` it
reads. A window is a bound, and this bundle is how an engine is held to it:
each windowed identifier gets a base case and at least one case that moves
one cell of one operand. The moved case names its base, the operand, the
policy and the period it moved, and the window the read states, in its
``perturbation`` member. Then:

- every period of the answer whose window excludes the moved period has
  the base's value, and so does every other policy's answer -- a window is
  within the policy's own run;
- and where some period's window includes it, at least one such period
  moved -- the case would otherwise prove nothing about the inside.

Every expected answer is worked from the clauses by hand, and **none was
read off the producer**: the producer and the engines are what these cases
test. The numbers are halves, wholes and powers of two, so every cell is
exact in a double and every case but the internal rate's is pinned at zero
tolerance; the rate keeps the 1e-7 budget 11.1.36 gives its solver. Stdlib
only. Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_window_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Not here.** A window the members cannot state is not stated, and a
case for it would test nothing: a scalar operand, a prospective value's
factor form, the period operand of a forward discount factor. Nulls are
11.1.9's question and ``nulls.json``'s, not this bundle's.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

CASES: list[dict] = []
BY_ID: dict[str, dict] = {}

FIRST_TO_NOW = {"periods": {"from": "first", "to": 0}}
BEFORE_NOW = {"periods": {"from": "first", "to": -1}}
NOW_TO_LAST = {"periods": {"from": 0, "to": "last"}}
WHOLE_RUN = {"periods": {"from": "first", "to": "last"}}


def col(name: str) -> dict:
    return {"op": "col", "name": name}


def lit(value: float) -> dict:
    return {"op": "lit", "value": value}


def call(name: str, *args: dict, **attrs: object) -> dict:
    return {"op": "call", "name": name, "args": list(args), "attrs": attrs}


def base(
    identifier: str,
    expr: dict,
    inputs: dict,
    expected: tuple[str, list],
    *,
    covers: tuple[str, ...],
    atol: float = 0.0,
    extra: dict | None = None,
) -> None:
    """Add one base case: the invocation every moved case beside it departs from."""
    dtype, values = expected
    case = {
        "id": identifier,
        "covers": list(covers),
        "inputs": {
            name: {"dtype": kind, "values": column}
            for name, (kind, column) in inputs.items()
        },
        "expr": expr,
        "producer_check": True,
        "expected": {"dtype": dtype, "values": values},
        "comparison": {"atol": atol, "rtol": 0.0},
        "case_kind": "value",
    }
    case.update(copy.deepcopy(extra or {}))
    CASES.append(case)
    BY_ID[identifier] = case


def moved(
    identifier: str,
    of: str,
    *,
    operand: str,
    policy: int,
    period: int,
    value: float,
    expected: list,
    window: dict,
) -> None:
    """Add the base case ``of`` with one cell of ``operand`` moved to ``value``."""
    case = copy.deepcopy(BY_ID[of])
    case["id"] = identifier
    case["inputs"][operand]["values"][policy][period] = value
    case["expected"]["values"] = expected
    case["perturbation"] = {
        "of": of,
        "operand": operand,
        "policy": policy,
        "period": period,
        "window": window,
    }
    CASES.append(case)
    BY_ID[identifier] = case


# A run of four periods and a run of three, so "last" is each policy's own.
RUN = ("list[f64]", [[1.0, 2.0, 4.0, 8.0], [16.0, 32.0, 64.0]])


# --- 11.1.9: the two scans, in both directions ------------------------------

# Period t is the sum of 0..t: moving period 2 leaves periods 0 and 1.
base(
    "window-cum_sum",
    call("cum_sum", col("x"), reverse=False),
    {"x": RUN},
    ("list[f64]", [[1.0, 3.0, 7.0, 15.0], [16.0, 48.0, 112.0]]),
    covers=("cum_sum",),
)
moved(
    "window-cum_sum-moved",
    "window-cum_sum",
    operand="x",
    policy=0,
    period=2,
    value=104.0,
    expected=[[1.0, 3.0, 107.0, 115.0], [16.0, 48.0, 112.0]],
    window=FIRST_TO_NOW,
)
# Under reverse, period t is the sum of t..n-1: moving period 1 leaves 2 and 3.
base(
    "window-cum_sum-reverse",
    call("cum_sum", col("x"), reverse=True),
    {"x": RUN},
    ("list[f64]", [[15.0, 14.0, 12.0, 8.0], [112.0, 96.0, 64.0]]),
    covers=("cum_sum",),
)
moved(
    "window-cum_sum-reverse-moved",
    "window-cum_sum-reverse",
    operand="x",
    policy=0,
    period=1,
    value=102.0,
    expected=[[115.0, 114.0, 12.0, 8.0], [112.0, 96.0, 64.0]],
    window=NOW_TO_LAST,
)
GROWTH = ("list[f64]", [[2.0, 2.0, 2.0, 2.0], [0.5, 0.5, 0.5]])
base(
    "window-cum_prod",
    call("cum_prod", col("x"), reverse=False),
    {"x": GROWTH},
    ("list[f64]", [[2.0, 4.0, 8.0, 16.0], [0.5, 0.25, 0.125]]),
    covers=("cum_prod",),
)
moved(
    "window-cum_prod-moved",
    "window-cum_prod",
    operand="x",
    policy=0,
    period=2,
    value=3.0,
    expected=[[2.0, 4.0, 12.0, 24.0], [0.5, 0.25, 0.125]],
    window=FIRST_TO_NOW,
)
base(
    "window-cum_prod-reverse",
    call("cum_prod", col("x"), reverse=True),
    {"x": GROWTH},
    ("list[f64]", [[16.0, 8.0, 4.0, 2.0], [0.125, 0.25, 0.5]]),
    covers=("cum_prod",),
)
moved(
    "window-cum_prod-reverse-moved",
    "window-cum_prod-reverse",
    operand="x",
    policy=0,
    period=1,
    value=3.0,
    expected=[[24.0, 12.0, 4.0, 2.0], [0.125, 0.25, 0.5]],
    window=NOW_TO_LAST,
)


# --- 11.1.19: the survival fold, with and without an opening value ----------

DECREMENT = ("list[f64]", [[0.5, 0.5, 0.5, 0.5], [0.25, 0.5, 0.75]])
# c[t] = product of (1 - q[u]) over u = 0..t.
base(
    "window-survival",
    call(
        "projection.cumulative_survival", col("q"), start_at=None, from_survival=False
    ),
    {"q": DECREMENT},
    ("list[f64]", [[0.5, 0.25, 0.125, 0.0625], [0.75, 0.375, 0.09375]]),
    covers=("projection.cumulative_survival",),
)
moved(
    "window-survival-moved",
    "window-survival",
    operand="q",
    policy=0,
    period=2,
    value=0.75,
    expected=[[0.5, 0.25, 0.0625, 0.03125], [0.75, 0.375, 0.09375]],
    window=FIRST_TO_NOW,
)
# Under start_at the answer is [a, c[0], ..., c[T-2]]: period t reads 0..t-1,
# so the decrement at period 1 first reaches period 2.
base(
    "window-survival-start_at",
    call("projection.cumulative_survival", col("q"), start_at=1.0, from_survival=False),
    {"q": DECREMENT},
    ("list[f64]", [[1.0, 0.5, 0.25, 0.125], [1.0, 0.75, 0.375]]),
    covers=("projection.cumulative_survival",),
)
moved(
    "window-survival-start_at-moved",
    "window-survival-start_at",
    operand="q",
    policy=0,
    period=1,
    value=0.75,
    expected=[[1.0, 0.5, 0.125, 0.0625], [1.0, 0.75, 0.375]],
    window=BEFORE_NOW,
)


# --- 11.1.20: the recurrence, both directions, both step operands -----------

STEPS = {
    "initial": ("f64", [10.0, 1.0]),
    "multiplier": ("list[f64]", [[2.0, 2.0, 2.0, 2.0], [0.5, 0.5, 0.5]]),
    "addend": ("list[f64]", [[1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]),
}
# Forward: 10*2+1 = 21, 43, 87, 175; and 1*0.5+1 = 1.5, 1.75, 1.875.
base(
    "window-accumulate",
    call(
        "projection.accumulate",
        col("initial"),
        col("multiplier"),
        col("addend"),
        reverse=False,
    ),
    STEPS,
    ("list[f64]", [[21.0, 43.0, 87.0, 175.0], [1.5, 1.75, 1.875]]),
    covers=("projection.accumulate",),
)
moved(
    "window-accumulate-moved-multiplier",
    "window-accumulate",
    operand="multiplier",
    policy=0,
    period=2,
    value=3.0,
    expected=[[21.0, 43.0, 130.0, 261.0], [1.5, 1.75, 1.875]],
    window=FIRST_TO_NOW,
)
moved(
    "window-accumulate-moved-addend",
    "window-accumulate",
    operand="addend",
    policy=0,
    period=1,
    value=5.0,
    expected=[[21.0, 47.0, 95.0, 191.0], [1.5, 1.75, 1.875]],
    window=FIRST_TO_NOW,
)
# Backward, from each policy's own last period: the same states laid the
# other way, and a step moves the periods at and before it.
base(
    "window-accumulate-reverse",
    call(
        "projection.accumulate",
        col("initial"),
        col("multiplier"),
        col("addend"),
        reverse=True,
    ),
    STEPS,
    ("list[f64]", [[175.0, 87.0, 43.0, 21.0], [1.875, 1.75, 1.5]]),
    covers=("projection.accumulate",),
)
moved(
    "window-accumulate-reverse-moved-multiplier",
    "window-accumulate-reverse",
    operand="multiplier",
    policy=0,
    period=1,
    value=3.0,
    expected=[[261.0, 130.0, 43.0, 21.0], [1.875, 1.75, 1.5]],
    window=NOW_TO_LAST,
)
moved(
    "window-accumulate-reverse-moved-addend",
    "window-accumulate-reverse",
    operand="addend",
    policy=0,
    period=2,
    value=5.0,
    expected=[[191.0, 95.0, 47.0, 21.0], [1.875, 1.75, 1.5]],
    window=NOW_TO_LAST,
)


# --- 11.1.20: the suffix sum ------------------------------------------------

base(
    "window-remaining_sum",
    call("projection.remaining_sum", col("x")),
    {"x": RUN},
    ("list[f64]", [[15.0, 14.0, 12.0, 8.0], [112.0, 96.0, 64.0]]),
    covers=("projection.remaining_sum",),
)
moved(
    "window-remaining_sum-moved",
    "window-remaining_sum",
    operand="x",
    policy=0,
    period=1,
    value=102.0,
    expected=[[115.0, 114.0, 12.0, 8.0], [112.0, 96.0, 64.0]],
    window=NOW_TO_LAST,
)


# --- 11.1.21: a prospective value's cashflows and its list rate -------------

# A rate of 1 is a discount of a half, a rate of 3 a quarter, and nought none.
PV_INPUTS = {
    "cf": ("list[f64]", [[8.0, 8.0, 8.0, 8.0], [4.0, 4.0, 4.0]]),
    "rate": ("list[f64]", [[1.0, 1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]),
}
# End of period: each cashflow carries its own period's discount, so
# t=3: 8/2 = 4; t=2: 4 + 8/4 = 6; t=1: 7; t=0: 7.5.
base(
    "window-prospective_value",
    call(
        "projection.prospective_value",
        col("cf"),
        col("rate"),
        timing="end_of_period",
        discount_kind="rate",
    ),
    PV_INPUTS,
    ("list[f64]", [[7.5, 7.0, 6.0, 4.0], [12.0, 8.0, 4.0]]),
    covers=("projection.prospective_value",),
)
# The cashflow at period 2, doubled: t=2: 16/2 + 8/4 = 10; t=1: 4 + 4 + 1 = 9;
# t=0: 4 + 2 + 2 + 0.5 = 8.5; t=3 reads only itself and is still 4.
moved(
    "window-prospective_value-moved-cashflow",
    "window-prospective_value",
    operand="cf",
    policy=0,
    period=2,
    value=16.0,
    expected=[[8.5, 9.0, 10.0, 4.0], [12.0, 8.0, 4.0]],
    window=NOW_TO_LAST,
)
# The rate at period 1 at three, a discount of a quarter there:
# t=1: 8/4 + 8/8 + 8/16 = 3.5; t=0: 4 + 1 + 0.5 + 0.25 = 5.75.
moved(
    "window-prospective_value-moved-rate",
    "window-prospective_value",
    operand="rate",
    policy=0,
    period=1,
    value=3.0,
    expected=[[5.75, 3.5, 6.0, 4.0], [12.0, 8.0, 4.0]],
    window=NOW_TO_LAST,
)
# Beginning of period: the current cashflow is undiscounted, so
# t=3: 8; t=2: 8 + 4 = 12; t=1: 14; t=0: 15.
base(
    "window-prospective_value-beginning",
    call(
        "projection.prospective_value",
        col("cf"),
        col("rate"),
        timing="beginning_of_period",
        discount_kind="rate",
    ),
    PV_INPUTS,
    ("list[f64]", [[15.0, 14.0, 12.0, 8.0], [12.0, 8.0, 4.0]]),
    covers=("projection.prospective_value",),
)
# The rate at period 1 discounts what follows it: t=1: 8 + 2 + 1 = 11;
# t=0: 8 + 4 + 1 + 0.5 = 13.5.
moved(
    "window-prospective_value-beginning-moved-rate",
    "window-prospective_value-beginning",
    operand="rate",
    policy=0,
    period=1,
    value=3.0,
    expected=[[13.5, 11.0, 12.0, 8.0], [12.0, 8.0, 4.0]],
    window=NOW_TO_LAST,
)


# --- 11.1.14-11.1.17: the four reductions -----------------------------------

base(
    "window-sum",
    call("sum", col("x")),
    {"x": RUN},
    ("f64", [15.0, 112.0]),
    covers=("sum",),
)
moved(
    "window-sum-moved",
    "window-sum",
    operand="x",
    policy=0,
    period=2,
    value=104.0,
    expected=[115.0, 112.0],
    window=WHOLE_RUN,
)
base(
    "window-mean",
    call("mean", col("x")),
    {"x": ("list[f64]", [[1.0, 2.0, 3.0, 6.0], [2.0, 4.0, 6.0]])},
    ("f64", [3.0, 4.0]),
    covers=("mean",),
)
moved(
    "window-mean-moved",
    "window-mean",
    operand="x",
    policy=0,
    period=3,
    value=10.0,
    expected=[4.0, 4.0],
    window=WHOLE_RUN,
)
EXTREMES = ("list[f64]", [[4.0, 3.0, 2.0, 5.0], [7.0, 8.0, 9.0]])
base(
    "window-min",
    call("min", col("x")),
    {"x": EXTREMES},
    ("f64", [2.0, 7.0]),
    covers=("min",),
)
moved(
    "window-min-moved",
    "window-min",
    operand="x",
    policy=0,
    period=2,
    value=1.0,
    expected=[1.0, 7.0],
    window=WHOLE_RUN,
)
base(
    "window-max",
    call("max", col("x")),
    {"x": EXTREMES},
    ("f64", [5.0, 9.0]),
    covers=("max",),
)
moved(
    "window-max-moved",
    "window-max",
    operand="x",
    policy=0,
    period=3,
    value=6.0,
    expected=[6.0, 9.0],
    window=WHOLE_RUN,
)


# --- 11.1.36: the internal rate solves over the whole stream ----------------

# -100 now and 100 a period on is a rate of nought; 110 a period on is 0.1.
base(
    "window-irr",
    call("excel.irr", col("cf"), default_guess=None),
    {"cf": ("list[f64]", [[-100.0, 100.0], [-100.0, 0.0, 100.0]])},
    ("f64", [0.0, 0.0]),
    covers=("excel.irr",),
    atol=1e-7,
)
moved(
    "window-irr-moved",
    "window-irr",
    operand="cf",
    policy=0,
    period=1,
    value=110.0,
    expected=[0.1, 0.0],
    window=WHOLE_RUN,
)


# --- 11.1.41: a reversal reads the whole run --------------------------------

base(
    "window-list-reverse",
    call("list.reverse", col("x")),
    {"x": ("list[f64]", [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0]])},
    ("list[f64]", [[4.0, 3.0, 2.0, 1.0], [7.0, 6.0, 5.0]]),
    covers=("list.reverse",),
)
moved(
    "window-list-reverse-moved",
    "window-list-reverse",
    operand="x",
    policy=0,
    period=0,
    value=10.0,
    expected=[[4.0, 3.0, 2.0, 10.0], [7.0, 6.0, 5.0]],
    window=WHOLE_RUN,
)


# --- 11.1.30: a forward discount factor reads the rates before this period --

# d[0] = 1 and d[t] = product of 1/(1 + r[u]) over u = 0..t-1.
base(
    "window-discount_factor-forward",
    call("finance.discount_factor", col("rate"), col("period"), method="forward"),
    {
        "rate": ("list[f64]", [[1.0, 1.0, 1.0, 1.0], [3.0, 3.0, 3.0]]),
        "period": ("list[f64]", [[0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0]]),
    },
    ("list[f64]", [[1.0, 0.5, 0.25, 0.125], [1.0, 0.25, 0.0625]]),
    covers=("finance.discount_factor",),
)
# The rate at period 1 first discounts period 2: periods 0 and 1 stand.
moved(
    "window-discount_factor-forward-moved",
    "window-discount_factor-forward",
    operand="rate",
    policy=0,
    period=1,
    value=3.0,
    expected=[[1.0, 0.5, 0.125, 0.0625], [1.0, 0.25, 0.0625]],
    window=BEFORE_NOW,
)


# --- 11.1.22: a literal position reads that one position --------------------

base(
    "window-list-get",
    call("list.get", col("x"), lit(1)),
    {"x": RUN},
    ("f64", [2.0, 32.0]),
    covers=("list.get",),
)
moved(
    "window-list-get-moved-at-the-position",
    "window-list-get",
    operand="x",
    policy=0,
    period=1,
    value=3.0,
    expected=[3.0, 32.0],
    window={"position": 1},
)
moved(
    "window-list-get-moved-elsewhere",
    "window-list-get",
    operand="x",
    policy=0,
    period=3,
    value=100.0,
    expected=[2.0, 32.0],
    window={"position": 1},
)
# A negative position counts back from the policy's own length: the last
# period of a three-period run is its period 2, not the grid's period 3.
base(
    "window-list-get-last",
    call("list.get", col("x"), lit(-1)),
    {"x": RUN},
    ("f64", [8.0, 64.0]),
    covers=("list.get",),
)
moved(
    "window-list-get-last-moved",
    "window-list-get-last",
    operand="x",
    policy=1,
    period=2,
    value=65.0,
    expected=[8.0, 65.0],
    window={"position": -1},
)


# --- section 9: a window through two operations -----------------------------

# The run to date of last period's value: previous_period then cum_sum reads
# x over 0..t-1, so moving period 1 first reaches period 2.
base(
    "window-cum_sum-of-previous_period",
    call(
        "cum_sum",
        call("projection.previous_period", col("x"), lit(0.0)),
        reverse=False,
    ),
    {"x": RUN},
    ("list[f64]", [[0.0, 1.0, 3.0, 7.0], [0.0, 16.0, 48.0]]),
    covers=("cum_sum", "projection.previous_period"),
)
moved(
    "window-cum_sum-of-previous_period-moved",
    "window-cum_sum-of-previous_period",
    operand="x",
    policy=0,
    period=1,
    value=102.0,
    expected=[[0.0, 1.0, 103.0, 107.0], [0.0, 16.0, 48.0]],
    window=BEFORE_NOW,
)


# --- section 16: a compiled rollforward reads its operands up to now --------

# The bounded fund of rollforward.json's ``rollforward-bounded-state``, its
# compilation, schedule and builder recipe taken whole -- the fingerprint is
# the compilation's and not the book's -- over a book of halves and quarters:
# the fund at the end of a period is (fund + credit) * (1 - rate).
# Policy one: (100 + 10) * 0.5 = 55, then 55 * 0.75 = 41.25. Policy two:
# 200 * 0.5 = 100, then (100 + 5) * 1 = 105. A credit at period 1 reaches
# period 1 and leaves period 0: (55 + 20) * 0.75 = 56.25.
ROLLFORWARD = json.loads((VECTORS / "rollforward.json").read_text())
FUND = next(
    case for case in ROLLFORWARD["cases"] if case["id"] == "rollforward-bounded-state"
)
base(
    "window-rollforward",
    FUND["expr"],
    {
        "initial": ("f64", [100.0, 200.0]),
        "credit": ("list[f64]", [[10.0, 0.0], [0.0, 5.0]]),
        "rate": ("list[f64]", [[0.5, 0.25], [0.5, 0.0]]),
    },
    ("list[f64]", [[55.0, 41.25], [100.0, 105.0]]),
    covers=("rollforward.state",),
    extra={
        "assumptions": FUND["assumptions"],
        "compilations": FUND["compilations"],
        "producer_build": FUND["producer_build"],
        "structural_covers": ["rollforward"],
    },
)
moved(
    "window-rollforward-moved",
    "window-rollforward",
    operand="credit",
    policy=0,
    period=1,
    value=20.0,
    expected=[[55.0, 56.25], [100.0, 105.0]],
    window=FIRST_TO_NOW,
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
        "family": "The periods each aggregation reads, held by moving one cell",
        "cases": CASES,
    }
    (VECTORS / "windows.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("window cases", len(CASES))


if __name__ == "__main__":
    main()
