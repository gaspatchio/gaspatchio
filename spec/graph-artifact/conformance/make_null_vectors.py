# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Write the null-bearing cases the specification's own null rules state.

Every expected answer below is derived by hand from the clause quoted beside
it and from nothing else. Several are the clause's own worked example copied
digit for digit. **No expected value here was read off the producer**: the
producer is the thing these cases test, and a vector taken from it would only
say that it agrees with itself. Stdlib only, for the same reason -- nothing
here imports gaspatchio, polars or numpy.

Run from ``bindings/python``::

    .venv/bin/python ../../spec/graph-artifact/conformance/make_null_vectors.py
    .venv/bin/python ../../spec/graph-artifact/conformance/make_boundary_review.py
    .venv/bin/python ../../spec/graph-artifact/conformance/build_kit.py

**Which clauses are here, and which are deliberately not.** A null case is
published only where the clause states what a null input does. Section 10
closes with "Behavior those clauses do not specify remains engine-defined;
this type vocabulary does not supply a portable default", so a vector for an
unstated boundary would be this producer's habit published as everyone's
contract.

Stated, and therefore here:

* **11.1.8** ``round``/``floor``/``ceil`` -- "A null value stays null under
  all three."
* **11.1.12** the nine elementary functions -- "A null value stays null under
  all nine."
* **11.1.9** ``cum_prod``/``cum_sum`` -- "A running fold that reaches a
  period carrying no value answers null at that period and at every period
  after it in the direction the fold runs", and the null outer list beside
  it.
* **11.1.14** ``sum`` -- "A null period makes the total null ...
  ``[10.0, null, 30.0, 40.0]`` answers null through all four", the all-null
  run that answers null with it, the empty run that still sums to nought,
  and the null outer list stated for the family.
* **11.1.19** ``projection.cumulative_survival`` -- the same running-fold
  rule, with and without an opening ``start_at``.
* **11.1.15** ``mean`` -- "``[10.0, null, 30.0, 40.0]`` answers null, and
  neither 26.666666666666668 ... nor 20.0."
* **11.1.16** ``min`` -- "a period carrying no value could have been the
  least of them, so ``[10.0, null, 30.0, 40.0]`` answers null."
* **11.1.17** ``max`` -- the same sentence for the greatest, and the all-null
  run that answers null.
* **11.1.20** ``projection.remaining_sum`` -- "A null period makes that
  position and every earlier position null ... ``[10.0, null, 30.0, 40.0]``
  gives ``[null, null, 70.0, 40.0]``."
* **11.1.21** ``projection.prospective_value`` -- the same reverse-fold rule
  for the cashflows' own periods, under either timing.
* **11.1.20** ``projection.accumulate`` -- "A null multiplier or a null
  addend at position ``t`` makes ``s[t]`` and every later position null",
  the null ``initial`` that answers a run of nulls, and the run whose every
  step is null.

Not stated, and therefore not here:

* **A non-finite operand to ``projection.accumulate``** (11.1.20). A NaN
  multiplier is a value the recurrence keeps rather than a period carrying
  none, and the entry's exclusion sentence leaves it outside the clause, so
  a vector for it would publish an answer the clause declines to state. The
  kernel's own tests hold that behaviour, beside the code that has it.
* **A null outer list to ``projection.accumulate``** (11.1.20). Named in the
  same exclusion sentence, and unlike the six folds above it does not answer
  null: the recurrence gives that policy an empty sequence, which is this
  producer's habit rather than a stated rule.
* **A null rate to ``projection.prospective_value``** (11.1.21). That entry's
  rule is about the cashflows' own periods; a null rate is listed with the
  operands the entry excludes.
* **The ``from_survival=true`` survival form.** 11.1.19 states the
  ``from_survival=false`` form and leaves the other outside the entry, so
  the running-fold rule is published for the stated form only even though
  the producer applies it to both.
"""

from __future__ import annotations

import json
from pathlib import Path

VECTORS = (
    Path(__file__).resolve().parents[3] / "bindings/python/gaspatchio/schemas/vectors"
)

# The clause's worked example, and the one every fold below reads.
STATED_RUN = [10.0, None, 30.0, 40.0]

CASES: list[dict] = []


def case(
    identifier: str,
    name: str,
    inputs: dict,
    expected: dict,
    *,
    attrs: dict | None = None,
    atol: float = 0.0,
    covers: str | None = None,
) -> None:
    """Add one value case invoking ``name`` on a single column ``x``."""
    CASES.append(
        {
            "id": identifier,
            "covers": [covers or name],
            "inputs": {"x": inputs},
            "expr": {
                "op": "call",
                "name": name,
                "args": [{"op": "col", "name": "x"}],
                "attrs": attrs or {},
            },
            "producer_check": True,
            "expected": expected,
            "comparison": {"atol": atol, "rtol": 0.0},
            "case_kind": "value",
        }
    )


def scalar(values: list) -> dict:
    return {"dtype": "f64", "values": values}


def periods(values: list) -> dict:
    return {"dtype": "list[f64]", "values": values}


def discounted(
    identifier: str,
    cashflows: list,
    rates: list,
    expected: list,
    *,
    timing: str,
    atol: float = 0.0,
) -> None:
    """Add one ``projection.prospective_value`` case over a cashflow and a rate."""
    CASES.append(
        {
            "id": identifier,
            "covers": ["projection.prospective_value"],
            "inputs": {"x": periods(cashflows), "rate": periods(rates)},
            "expr": {
                "op": "call",
                "name": "projection.prospective_value",
                "args": [{"op": "col", "name": "x"}, {"op": "col", "name": "rate"}],
                "attrs": {"timing": timing, "discount_kind": "rate"},
            },
            "producer_check": True,
            "expected": periods(expected),
            "comparison": {"atol": atol, "rtol": 0.0},
            "case_kind": "value",
        }
    )


def accumulated(
    identifier: str,
    initial: list,
    multiplier: list,
    addend: list,
    expected: list,
) -> None:
    """Add one ``projection.accumulate`` case over an opening state and two steps."""
    CASES.append(
        {
            "id": identifier,
            "covers": ["projection.accumulate"],
            "inputs": {
                "initial": scalar(initial),
                "multiplier": periods(multiplier),
                "addend": periods(addend),
            },
            "expr": {
                "op": "call",
                "name": "projection.accumulate",
                "args": [
                    {"op": "col", "name": "initial"},
                    {"op": "col", "name": "multiplier"},
                    {"op": "col", "name": "addend"},
                ],
                "attrs": {"reverse": False},
            },
            "producer_check": True,
            "expected": periods(expected),
            "comparison": {"atol": 0.0, "rtol": 0.0},
            "case_kind": "value",
        }
    )


# --- 11.1.8 "A null value stays null under all three." ----------------------
#
# Each case is the published bounded case for the same identifier with its
# middle value replaced by a null, so the surviving two answers are the ones
# already reviewed and the only new claim is the clause's own sentence. The
# clause's "One value at a time ... the operation has no view across periods"
# is what makes the neighbours' answers independent of the null beside them.

# ceil is the smallest whole number not below the value: -1.9 -> -1.0 (-1 is
# not below -1.9 and -2 is), 1.9 -> 2.0. The null stays null.
case("null-ceil-scalar", "ceil", scalar([-1.9, None, 1.9]), scalar([-1.0, None, 2.0]))

# floor is the largest whole number not above the value: -1.9 -> -2.0,
# 1.9 -> 1.0. The null stays null.
case("null-floor-scalar", "floor", scalar([-1.9, None, 1.9]), scalar([-2.0, None, 1.0]))

# round to whole numbers under half_to_even: 2.5 ties and goes to the even
# neighbour 2.0; 3.5 ties and goes to the even neighbour 4.0. The null stays
# null, in the per-period form, where the clause's "each period's own value is
# moved" is what keeps the two live periods unmoved by the null between them.
case(
    "null-round-period",
    "round",
    periods([[2.5, None, 3.5]]),
    periods([[2.0, None, 4.0]]),
    attrs={"decimals": 0, "mode": "half_to_even"},
)

# --- 11.1.12 "A null value stays null under all nine." ----------------------
#
# Same construction: the published bounded case with its middle value nulled.
# The tolerance is the published one for each identifier, because the two
# surviving answers are the published answers.

# abs drops the sign: -8 -> 8, 8 -> 8.
case(
    "null-abs-scalar",
    "abs",
    scalar([-8.0, None, 8.0]),
    scalar([8.0, None, 8.0]),
    atol=1e-12,
)

# sign is minus one below zero and one above it: -8 -> -1, 8 -> 1.
case(
    "null-sign-scalar",
    "sign",
    scalar([-8.0, None, 8.0]),
    scalar([-1.0, None, 1.0]),
    atol=1e-12,
)

# sqrt: 0 -> 0, 9 -> 3, because 3 * 3 = 9.
case(
    "null-sqrt-scalar",
    "sqrt",
    scalar([0.0, None, 9.0]),
    scalar([0.0, None, 3.0]),
    atol=1e-12,
)

# cbrt: -8 -> -2 and 27 -> 3, because (-2)^3 = -8 and 3^3 = 27.
case(
    "null-cbrt-scalar",
    "cbrt",
    scalar([-8.0, None, 27.0]),
    scalar([-2.0, None, 3.0]),
    atol=1e-12,
)

# exp: e^-1 and e^1, to the double each is nearest. Both values are the ones
# the published exp case carries for the same two inputs.
case(
    "null-exp-scalar",
    "exp",
    scalar([-1.0, None, 1.0]),
    scalar([0.36787944117144233, None, 2.718281828459045]),
    atol=1e-12,
)

# log is the natural logarithm, and the two inputs are e^0 and e^2 written as
# doubles, so the answers are 0 and 2.
case(
    "null-log-scalar",
    "log",
    scalar([1.0, None, 7.3890560989306495]),
    scalar([0.0, None, 2.0]),
    atol=1e-12,
)

# log10 of 1 is 0 and of 100 is 2.
case(
    "null-log10-scalar",
    "log10",
    scalar([1.0, None, 100.0]),
    scalar([0.0, None, 2.0]),
    atol=1e-12,
)

# log1p is the natural logarithm of one plus the value: 0 -> log(1) = 0, and
# 6.3890560989306495 -> log(7.3890560989306495) = 2.
case(
    "null-log1p-scalar",
    "log1p",
    scalar([0.0, None, 6.3890560989306495]),
    scalar([0.0, None, 2.0]),
    atol=1e-12,
)

# round_sig_figs keeps the leading three significant figures and zeroes the
# rest: 1234 -> 1230 and -1234 -> -1230.
case(
    "null-round_sig_figs-scalar",
    "round_sig_figs",
    scalar([1234.0, None, -1234.0]),
    scalar([1230.0, None, -1230.0]),
    attrs={"digits": 3},
    atol=1e-15,
)

# --- 11.1.14 to 11.1.17: a null period makes the total null -----------------
#
# The clause's own run, and the one answer it now states for all four of them.
# A total is one number and has no room to say a period went missing under it,
# so it says so by being null. The two readings this rule replaced -- a null
# absent to the fold, and a null read as nought -- parted company on min and
# max, and each of those keeps a second run below on values that share nothing
# with the clause's example.

# 11.1.14: "[10.0, null, 30.0, 40.0] answers null through all four." The
# answer that reading the null as absent would give is 10 + 30 + 40 = 80.0,
# which is what this case published before the rule changed.
case(
    "null-sum-period", "sum", periods([STATED_RUN]), {"dtype": "f64", "values": [None]}
)

# 11.1.15: "[10.0, null, 30.0, 40.0] answers null, and neither
# 26.666666666666668 ... nor 20.0." The two numbers the clause names are the
# readings it refuses: 80/3, the average of the periods carrying a value, and
# 80/4, the average a null read as a fourth period of nought would give.
case(
    "null-mean-period",
    "mean",
    periods([STATED_RUN]),
    {"dtype": "f64", "values": [None]},
)

# 11.1.15: "A run of nothing but nulls has no periods to average and answers
# null." The denominator is the count of periods carrying a value, which is 0.
case(
    "null-mean-all-null",
    "mean",
    periods([[None, None]]),
    {"dtype": "f64", "values": [None]},
)

# 11.1.16: "a period carrying no value could have been the least of them, so
# [10.0, null, 30.0, 40.0] answers null." The two readings this replaced would
# have said 10.0, the least of the periods carrying a value, or 0.0, with the
# null competing as a nought.
case(
    "null-min-period", "min", periods([STATED_RUN]), {"dtype": "f64", "values": [None]}
)

# 11.1.16 again, on a shorter run whose values share nothing with the clause's
# example: [2.0, null, 3.0] answers null, where reading the null as absent
# would say 2.0 and reading it as a nought would say 0.0. A rule worth stating
# is worth a second run, and this one was published to separate those two
# readings -- a separation the rule removes by refusing both.
case(
    "null-min-is-not-a-nought",
    "min",
    periods([[2.0, None, 3.0]]),
    {"dtype": "f64", "values": [None]},
)

# 11.1.16: "A run of nothing but nulls has no value to be least and answers
# null."
case(
    "null-min-all-null",
    "min",
    periods([[None, None]]),
    {"dtype": "f64", "values": [None]},
)

# 11.1.17: the same sentence for the greatest. Reading the null as absent
# would have answered 40.0, the greatest of 10, 30 and 40.
case(
    "null-max-period", "max", periods([STATED_RUN]), {"dtype": "f64", "values": [None]}
)

# 11.1.17 below zero, where the two older readings parted company: the
# greatest of -2 and -3 is -2.0, and a null read as a nought would have won
# with 0.0. Neither is the answer now, and the run is kept because it exercises
# the rule on values the clause's own example does not reach.
case(
    "null-max-is-not-a-nought",
    "max",
    periods([[-2.0, None, -3.0]]),
    {"dtype": "f64", "values": [None]},
)

# 11.1.17: "A run of nothing but nulls has no value to be greatest and answers
# null."
case(
    "null-max-all-null",
    "max",
    periods([[None, None]]),
    {"dtype": "f64", "values": [None]},
)

# 11.1.14: "A run whose every period is missing is not a run of no periods, so
# it is not the empty run this entry sums to nought." This case published 0.0
# while sum parted company with its siblings; sum joins them and answers null.
case(
    "null-sum-all-null",
    "sum",
    periods([[None, None]]),
    {"dtype": "f64", "values": [None]},
)

# --- 11.1.9 and 11.1.19: a running fold that loses a period ----------------
#
# The four reductions above answer one number and can say a null period was
# absent to them. A running fold answers one number per period, and from the
# period it lost onward it has no total to report -- so it reports that it has
# none, at that period and at every period the fold would have carried the
# lost value into. The direction of the fold is the direction of that run: a
# reverse scan's nulls go toward period zero.
#
# Every run below is the clause's own [10.0, null, 30.0, 40.0], so the answers
# can be read straight off it and set beside the reductions' answers for the
# same four periods.

# Forward: period 0 is 10.0, reached before the hole. Period 1 is the hole.
# Periods 2 and 3 are after it. A fold that skipped the null and carried on
# would say [10.0, null, 40.0, 80.0], and the difference is the whole rule.
case(
    "null-cum_sum-period",
    "cum_sum",
    periods([STATED_RUN]),
    periods([[10.0, None, None, None]]),
    attrs={"reverse": False},
)

# Reverse: the fold starts at period 3 and runs down. Period 3 is 40.0 and
# period 2 is 30.0 + 40.0 = 70.0, both reached before the hole at period 1;
# periods 1 and 0 are the hole and what lies beyond it in this direction.
case(
    "null-cum_sum-period-reverse",
    "cum_sum",
    periods([STATED_RUN]),
    periods([[None, None, 70.0, 40.0]]),
    attrs={"reverse": True},
)

# Forward product: period 0 is 10.0, and the rest is after the hole.
case(
    "null-cum_prod-period",
    "cum_prod",
    periods([STATED_RUN]),
    periods([[10.0, None, None, None]]),
    attrs={"reverse": False},
)

# Reverse product: period 3 is 40.0 and period 2 is 30.0 * 40.0 = 1200.0.
case(
    "null-cum_prod-period-reverse",
    "cum_prod",
    periods([STATED_RUN]),
    periods([[None, None, 1200.0, 40.0]]),
    attrs={"reverse": True},
)

# 11.1.19, without an opening value. The run is the published survival case's
# [0.1, 0.2, 0.3] with its middle decrement nulled, so the one surviving
# answer is the published answer: c[0] = 1 - 0.1 = 0.9. The decrement at
# period 1 is missing, so the running survival has lost a factor and periods
# 1 and 2 answer null. A fold reading the missing decrement as no decrement
# would say [0.9, 0.9, 0.63], which is a survival curve a reviewer would
# check and find correct.
case(
    "null-survival-period",
    "projection.cumulative_survival",
    periods([[0.1, None, 0.3]]),
    periods([[0.9, None, None]]),
    attrs={"start_at": None, "from_survival": False},
    atol=1e-15,
)

# 11.1.19 with start_at. The opening value is the boundary the projection
# starts from, not a factor in the product, so it is never the thing that went
# missing: the mask goes on the cumulative product first, giving
# [0.9, null, null], and prepending 1.0 and dropping the last element then
# gives [1.0, 0.9, null]. One more period carries a value here than in the
# case above, and that is the shift and not the fold.
case(
    "null-survival-period-start_at",
    "projection.cumulative_survival",
    periods([[0.1, None, 0.3]]),
    periods([[1.0, 0.9, None]]),
    attrs={"start_at": 1.0, "from_survival": False},
    atol=1e-15,
)

# --- A null outer list, through all six folds ------------------------------
#
# A policy whose whole column is null is not a policy with a hole in its
# column: it has no periods at all for the fold to reach, and every one of the
# six answers null for it. The first policy carries the fold's ordinary answer
# beside it, so each case shows the rule without also asserting that a null
# policy silences its neighbour.

OUTER = [[10.0, 30.0], None]

# 10 + 30 = 40.
case(
    "null-sum-outer-list",
    "sum",
    periods(OUTER),
    {"dtype": "f64", "values": [40.0, None]},
)

# 40 / 2 = 20.
case(
    "null-mean-outer-list",
    "mean",
    periods(OUTER),
    {"dtype": "f64", "values": [20.0, None]},
)

# The least of 10 and 30.
case(
    "null-min-outer-list",
    "min",
    periods(OUTER),
    {"dtype": "f64", "values": [10.0, None]},
)

# The greatest of 10 and 30.
case(
    "null-max-outer-list",
    "max",
    periods(OUTER),
    {"dtype": "f64", "values": [30.0, None]},
)

# 10, then 10 + 30 = 40. The null policy answers null rather than an empty
# list: it is a policy with no column, not a policy with no periods.
case(
    "null-cum_sum-outer-list",
    "cum_sum",
    periods(OUTER),
    periods([[10.0, 40.0], None]),
    attrs={"reverse": False},
)

# 10, then 10 * 30 = 300.
case(
    "null-cum_prod-outer-list",
    "cum_prod",
    periods(OUTER),
    periods([[10.0, 300.0], None]),
    attrs={"reverse": False},
)


# --- 11.1.20 and 11.1.21: the two folds that run from the last period -------
#
# These two are reverse folds: each position is the total of that period and
# every period after it, so the fold starts at the last period and works back.
# A period carrying no value therefore loses the fold its total at that
# position and at every EARLIER one -- the nulls run toward period zero, which
# is the direction this fold travels. The runs below are the clause's own
# [10.0, null, 30.0, 40.0] again, so the answers stand beside the reductions'
# and the two scans' answers for the same four periods.

# 11.1.20, the suffix sum. Period 3 is 40.0 and period 2 is 30.0 + 40.0 = 70.0,
# both reached before the fold meets the hole at period 1; periods 1 and 0 are
# the hole and what lies beyond it in this direction. A fold that skipped the
# null and carried on would say [80.0, 70.0, null, 40.0], and the difference is
# the whole rule.
case(
    "null-remaining_sum-period",
    "projection.remaining_sum",
    periods([STATED_RUN]),
    periods([[None, None, 70.0, 40.0]]),
)

# 11.1.20: a run of nothing but nulls has no period the fold reaches with a
# value, so every position is a position it has lost.
case(
    "null-remaining_sum-all-null",
    "projection.remaining_sum",
    periods([[None, None]]),
    periods([[None, None]]),
)

# 11.1.20: a policy whose whole column is null answers null rather than an
# empty list, as it does through the other five folds. The first policy carries
# the fold's ordinary answer -- 10 + 30 = 40, then 30 -- so the case shows the
# rule without also asserting that a null policy silences its neighbour.
case(
    "null-remaining_sum-outer-list",
    "projection.remaining_sum",
    periods(OUTER),
    periods([[40.0, 30.0], None]),
)

# 11.1.21 with every rate nought, so B[t] = 1 at every period and the present
# value is exactly the suffix sum above: the discounting is the identity here
# and the null rule is the whole of the content. Under end_of_period each
# cashflow carries its own period's rate, which at nought is a factor of one.
discounted(
    "null-prospective_value-period",
    [STATED_RUN],
    [[0.0, 0.0, 0.0, 0.0]],
    [[None, None, 70.0, 40.0]],
    timing="end_of_period",
)

# 11.1.21 under the other timing and a rate that is not nought, so the rule is
# shown to be about the fold rather than about the timing or the discount.
# beginning_of_period leaves the current cashflow undiscounted, so position 3
# is its own 40.0, and position 2 is cf[2] + cf[3] * B[3]/B[2] = 30.0 + 40.0/1.05
# = 68.0952380952381. The fold has lost positions 1 and 0, exactly as above.
discounted(
    "null-prospective_value-period-beginning",
    [STATED_RUN],
    [[0.05, 0.05, 0.05, 0.05]],
    [[None, None, 68.0952380952381, 40.0]],
    timing="beginning_of_period",
    atol=1e-12,
)

# 11.1.21: the two closures, on the second reverse fold. Every period of the
# first policy is missing, and the second policy has no column at all.
discounted(
    "null-prospective_value-all-null",
    [[None, None], None],
    [[0.0, 0.0], [0.0, 0.0]],
    [[None, None], None],
    timing="end_of_period",
)


# --- 11.1.20: the recurrence, the one forward fold with two step operands ---
#
# s[-1] is the initial value and s[t] = s[t-1] * multiplier[t] + addend[t].
# The runs below use whole numbers so that every state is exact in a double
# and the case can be pinned at zero tolerance: the clause's own
# [10.0, null, 30.0, 40.0] is a single operand and has no shape here, where
# two lists and an opening state are needed to say anything at all.

# 11.1.20: a null multiplier at position 1. s[0] = 10 * 2 + 1 = 21, which is
# the one period reached before the hole; from there the recurrence has lost a
# growth factor and does not know its state. A fold that skipped the hole and
# carried on would report 21 * 3 + 1 = 64 and 64 * 4 + 1 = 257 -- two account
# values with a period's growth missing from underneath them.
accumulated(
    "null-accumulate-multiplier",
    [10.0],
    [[2.0, None, 3.0, 4.0]],
    [[1.0, 1.0, 1.0, 1.0]],
    [[21.0, None, None, None]],
)

# 11.1.20: a null addend at position 2, so two periods are reached before the
# hole. s[0] = 10 * 2 + 1 = 21 and s[1] = 21 * 2 + 2 = 44. The rule is about
# the period rather than about which of the two step operands went missing,
# which is why the hole is moved as well as swapped between the operands.
accumulated(
    "null-accumulate-addend",
    [10.0],
    [[2.0, 2.0, 2.0, 2.0]],
    [[1.0, 2.0, None, 4.0]],
    [[21.0, 44.0, None, None]],
)

# 11.1.20: the hole at the first period. The fold reaches no state at all, and
# the row keeps its three positions rather than collapsing to an empty one --
# a policy with periods it cannot answer for is not a policy with no periods.
accumulated(
    "null-accumulate-first-period",
    [10.0],
    [[None, 3.0, 4.0]],
    [[1.0, 1.0, 1.0]],
    [[None, None, None]],
)

# 11.1.20: "A null initial answers a run of nulls of the period count, because
# the recurrence has no state to open with." Both steps carry a value, so the
# null is in the opening state alone.
accumulated(
    "null-accumulate-initial",
    [None],
    [[2.0, 3.0]],
    [[1.0, 1.0]],
    [[None, None]],
)

# 11.1.20: a run whose every step is null. The first period is the hole, so
# this is the rule above reaching every position; it is published beside the
# family's all-null runs because a rule worth stating is worth the closure.
accumulated(
    "null-accumulate-all-null",
    [10.0],
    [[None, None]],
    [[1.0, 1.0]],
    [[None, None]],
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
        "family": "Null boundaries the specification states",
        "cases": CASES,
    }
    (VECTORS / "nulls.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n"
    )
    print("null cases", len(CASES))


if __name__ == "__main__":
    main()
