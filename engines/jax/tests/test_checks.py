# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The check inventory, its stages, and the coarse-flag protocol."""

from __future__ import annotations

import time
from typing import Final

import jax.numpy as jnp
import pytest

from gaspatchio_jax.checks import (
    CHECKS,
    FlagBook,
    Flagged,
    flag,
    outside_i64,
    recording,
    to_the_horizon,
)
from gaspatchio_jax.lowerings import LOWERINGS, load
from tests.conftest import answered, invocation, run_scalar


def test_every_check_a_registration_names_is_in_the_inventory() -> None:
    load()
    for name, (_lowering, capability) in LOWERINGS.items():
        for check in capability.checks:
            assert check in CHECKS, (name, check)


def test_a_check_on_an_operand_that_arrived_answers_before_anything_is_compiled() -> (
    None
):
    check = CHECKS["to_integer.integral"]
    assert check.stage_for(operand_is_computed=False) == "inputs"
    assert check.stage_for(operand_is_computed=True) == "completion"


def test_a_flag_raised_outside_a_run_is_refused_rather_than_dropped() -> None:
    with pytest.raises(RuntimeError, match="outside a run"):
        flag("i64.range", jnp.asarray([True]))


def test_a_flag_nobody_declared_is_refused() -> None:
    with recording(), pytest.raises(LookupError, match="not a declared check"):
        flag("made.up", jnp.asarray([True]))


def test_a_run_collects_its_flags_and_names_the_node_they_came_from() -> None:
    with recording() as book:
        from gaspatchio_jax.checks import about

        with about("answer@1"):
            flag("i64.range", jnp.asarray([False, True]))
    assert len(book.entries) == 1
    assert book.entries[0].where == "answer@1"
    assert book.entries[0].caught() == [1]


def test_a_flag_over_a_rectangle_two_axes_share_is_held_to_both_of_them() -> None:
    """Two axes of one rectangle are two horizons, and neither of them is dropped.

    A boundary sequence is one cell longer than the period values beside it,
    so a bucket wide enough for both makes the two arrays the same shape. A
    cell that is a period under either axis is a cell somebody wrote, and only
    a cell that is padding under every axis of the node is padding -- so the
    fold is a union. A fold that kept one of the two instead would clear a
    real finding on nothing but the order the axes arrived in, which is why
    both orders are asserted here.
    """
    wide = jnp.asarray([[True, True, True, False]])
    narrow = jnp.asarray([[True, True, False, False]])
    # Caught at the third cell, which is a period under ``wide`` alone, and at
    # the fourth, which is padding under both.
    caught = jnp.asarray([[False, False, True, True]])
    for axes in ((wide, narrow), (narrow, wide)):
        book = FlagBook(
            [Flagged(name="floordiv.zero_divisor", where="answer@1", mask=caught)]
        )
        to_the_horizon(book, 0, axes)
        assert book.entries[0].caught() == [2]


def test_a_coarse_flag_keeps_only_the_cells_the_host_confirms() -> None:
    """2^62 times 2 leaves i64; 2^62 times 1 does not, and both are flagged."""
    left = jnp.asarray([2**62, 2**62], dtype=jnp.int64)
    right = jnp.asarray([2, 1], dtype=jnp.int64)
    entry = Flagged(
        name="i64.range",
        where="answer@1",
        mask=jnp.asarray([True, True]),
        judgement="mul",
        operands=(left, right),
    )
    assert entry.caught() == [0, 1]
    assert entry.confirmed() == [0]


def test_a_coarse_flag_reads_a_per_policy_operand_where_the_caught_cell_stands() -> (
    None
):
    """A per-policy operand is one cell a policy, repeated along the periods.

    Policy 0's second period is 2^62 times 4, which has left i64; policy 1's
    third is 1 times 3, which has not. Read at each cell's flat position in
    the per-policy operand as stored, the first was set against policy 1's
    value -- 1 times 4 -- and judged inside, and the second was past the
    operand's own two cells.
    """
    per_policy = jnp.asarray([[2**62], [1]], dtype=jnp.int64)
    per_period = jnp.asarray([[1, 4, 1, 1], [1, 1, 3, 1]], dtype=jnp.int64)
    caught = jnp.asarray([[False, True, False, False], [False, False, True, False]])
    for operands in ((per_policy, per_period), (per_period, per_policy)):
        entry = Flagged(
            name="i64.range",
            where="answer@1",
            mask=caught,
            judgement="mul",
            operands=operands,
        )
        assert entry.caught() == [1, 6]
        assert entry.confirmed() == [1]


@pytest.mark.parametrize(
    ("per_policy", "per_period", "first"),
    [
        (
            [2**62, 1, 1],
            [[1, 4, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]],
            "policy 0, period 1",
        ),
        (
            [1, 1, 2**62],
            [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 4, 1]],
            "policy 2, period 2",
        ),
    ],
    ids=["inside the operand's own length", "past it"],
)
def test_a_per_policy_integer_times_a_per_period_one_refuses_where_it_overflows(
    per_policy: list[int], per_period: list[list[int]], first: str
) -> None:
    """11.1.25 end to end: 2^62 times 4 has left i64, whichever policy it is in.

    Inside the per-policy operand's own length, the wrapped product -- nought
    -- was published as a number rather than refused; past it, the run raised
    an index error rather than a refusal. An integer power meets no such
    pair: 11.1.25 promises it only over two operands of one shape, and one
    over a per-policy and a per-period operand is a double.
    """
    outcome = answered(
        invocation(
            {
                "op": "binop",
                "kind": "mul",
                "left": {"op": "col", "name": "a"},
                "right": {"op": "col", "name": "b"},
            },
            {
                "a": {"dtype": "i64", "values": per_policy},
                "b": {"dtype": "list[i64]", "values": per_period},
            },
            "list[i64]",
        )
    )
    assert outcome.refused_with == "i64.range"
    assert f"first at {first}" in outcome.report
    assert "No results were published." in outcome.report


@pytest.mark.parametrize(
    ("base", "exponent", "outside"),
    [
        (2, 2**31, True),
        (-2, 63, False),
        (-2, 64, True),
        (2, 62, False),
        (2, 63, True),
        (3, 39, False),
        (3, 40, True),
        (1, 2**31, False),
        (-1, 2**31, False),
        (0, 5, False),
    ],
)
def test_a_power_is_judged_by_magnitude_before_it_is_built(
    base: int, exponent: int, *, outside: bool
) -> None:
    """``(-2) ** 63`` is exactly INT64_MIN, which a magnitude rule alone refuses."""
    assert outside_i64("pow", base, exponent) is outside


def test_a_power_no_machine_could_hold_is_decided_without_holding_it() -> None:
    started = time.perf_counter()
    assert outside_i64("pow", 2, 2**31) is True
    assert time.perf_counter() - started < 0.1


def test_the_engine_refuses_that_power_end_to_end_in_the_same_breath() -> None:
    started = time.perf_counter()
    assert run_scalar("pow", 2, 2**31).refused_with == "i64.range"
    assert time.perf_counter() - started < 30


def test_a_completion_refusal_names_the_check_the_count_and_the_first_row() -> None:
    outcome = answered(
        invocation(
            {
                "op": "binop",
                "kind": "add",
                "left": {"op": "col", "name": "a"},
                "right": {"op": "col", "name": "b"},
            },
            {
                "a": {"dtype": "i64", "values": [1, 2**63 - 1, 2**63 - 1]},
                "b": {"dtype": "i64", "values": [1, 1, 1]},
            },
            "i64",
        )
    )
    assert outcome.refused_with == "i64.range"
    assert "first at row 1" in outcome.report
    assert "No results were published." in outcome.report


def test_a_stored_floating_point_predicate_off_zero_and_one_refuses_by_name() -> None:
    outcome = answered(
        invocation(
            {
                "op": "when_then",
                "cond": {"op": "col", "name": "flag"},
                "then": {"op": "lit", "value": 1.0},
                "otherwise": {"op": "lit", "value": 0.0},
            },
            {"flag": {"dtype": "f64", "values": [0.5]}},
            "f64",
        )
    )
    assert outcome.refused_with == "predicate.stored_f64"


def test_a_stored_flag_a_nan_left_without_a_truth_value_refuses() -> None:
    """A NaN comparison has no truth value; a stored flag holds no NaN (11.1.26).

    The producer stores a null there, which this engine does not carry.
    """
    outcome = answered(
        invocation(
            {
                "op": "binop",
                "kind": "lt",
                "left": {"op": "col", "name": "a"},
                "right": {"op": "lit", "value": 1.0},
            },
            {"a": {"dtype": "f64", "values": [{"nonfinite": "nan"}]}},
            "bool",
        )
    )
    assert outcome.refused_with == "comparison.unknown"


def test_an_integer_division_by_zero_refuses_rather_than_minting_a_null() -> None:
    assert run_scalar("floordiv", 1, 0).refused_with == "floordiv.zero_divisor"


def test_every_check_is_declared_on_some_registration() -> None:
    """An inventory row nobody claims is a check nobody can be held to.

    The runtime already refuses a flag raised under a name the inventory does
    not carry; this is the other direction, and it is what makes the coverage
    manifest's claim about an identifier complete: the checks an operation
    owes are the checks its registration names.

    What is asserted here is the union over every registration, and no more
    than that -- which registration a row belongs to is the next test's.
    """
    from gaspatchio_jax.checks import CHECKS
    from gaspatchio_jax.lowerings import LOWERINGS, load

    load()
    declared: set[str] = set()
    for _lowering, capability in LOWERINGS.values():
        declared |= set(capability.checks)
    assert set(CHECKS) - declared == _NOT_LOWERED_YET


def test_every_check_a_lowering_raises_is_declared_beside_it() -> None:
    """A declared union says a check is claimed; this says *who* claims it.

    A row can be declared on a registration that never raises it while the
    operation that does raise it declares nothing, and the union above reads
    the same either way -- so a reader who went from a refusal's name to the
    coverage row it belongs to would be sent to the wrong operation. Read off
    the source rather than the runtime, because a check name is written where
    the operation is written and not anywhere the registration table can be
    asked for: every check name a module spells is declared on a registration
    written in the family module of the same name.

    **Every module under the package, not only ``lowerings/``.** Two of the
    modules that raise a check are not family modules at all --
    ``tables.py`` raises ``lookup.key_range`` for the three reads that select
    a row, and ``typed.py`` raises ``mixed.2p53`` for the arithmetic family
    -- and a scan that looked only at ``lowerings/`` would have read those two
    as raised by nobody. :data:`_RAISES_FOR` says which family module a
    reader following each of their names would look in, and that is where the
    declaration has to be.

    **Two spellings, because there are two.** Most raises name the check at
    the call site -- ``flag("floordiv.zero_divisor", ...)``. The reads that
    select a row do not: they are handed a ``Miss`` record and raise
    ``miss.check`` and ``miss.blank``, so the names are spelled where that
    record is built, as ``check=`` and ``blank=``. A reading that took only
    the first spelling would say nothing about either of those two.
    """
    import ast

    from gaspatchio_jax.lowerings import LOWERINGS, load
    from tests.conftest import SOURCE

    load()
    declared: dict[str, set[str]] = {}
    for lowering, capability in LOWERINGS.values():
        module = lowering.__module__.rsplit(".", 1)[-1]
        declared.setdefault(module, set()).update(capability.checks)
    seen: set[str] = set()
    for path in sorted(SOURCE.rglob("*.py")):
        raised: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id in _RAISES_A_FLAG:
                spelled: list[ast.expr] = node.args[:1]
            elif node.func.id in _CARRIES_A_CHECK:
                spelled = [
                    given.value for given in node.keywords if given.arg in _NAMES_ONE
                ]
            else:
                continue
            raised |= {
                one.value
                for one in spelled
                if isinstance(one, ast.Constant) and isinstance(one.value, str)
            }
        seen |= raised
        family: set[str] = set()
        for stem in _RAISES_FOR.get(path.stem, (path.stem,)):
            family |= declared.get(stem, set())
        assert raised - family == set(), path.stem
    # A reading that found nothing would pass every line above it, so what the
    # reading found is asserted too: one name from each of the three spellings
    # below, so a rename of any of them leaves this failing rather than vacuous.
    assert {
        "floordiv.zero_divisor",
        "to_monthly.rate",
        "join.unmatched",
        # The two raised outside ``lowerings/``, which is why the scan reaches
        # the whole package: a rename that moved either out of view would
        # leave this line failing.
        "lookup.key_range",
        "mixed.2p53",
    } <= seen


# The modules that raise a check on a family's behalf rather than their own,
# and the family modules whose registrations therefore have to declare it. A
# support module carries no registration of its own, so keying it by its own
# file name would ask an empty set to contain something.
_RAISES_FOR: Final[dict[str, tuple[str, ...]]] = {
    # Preparation raises the same declared predicates as these numerical families.
    "domains": (
        "conversion",
        "conditional",
        "projection",
        "comparisons",
        "maths",
        "banding",
        "selection",
    ),
    # The three reads that select a row all go through one address
    # computation, and it is the one that judges whether a key is a number
    # the basis could carry.
    "tables": ("tables",),
    # The typed path widens an integer operand to a double for whichever
    # family asked, and 11.1.25's ±2^53 is owed by every one of them.
    "typed": ("maths", "comparisons", "conditional"),
    # The run refuses a formula or a fold that reads a left join's kept miss
    # unfilled; the miss is the join's, and the join declares it.
    "plan": ("tables", "comparisons"),
}


# How a lowering spells a check name. Two are calls that raise one: the
# runtime's own, and the one wrapper the finance module puts in front of it.
# The third is the record a read that selects a row is handed, which carries
# the two names that read may raise. A spelling this file does not name would
# make the test above read less than it should, which is why they are here
# rather than inside the loop.
_RAISES_A_FLAG = frozenset({"flag", "_caught"})
_CARRIES_A_CHECK = frozenset({"Miss"})
_NAMES_ONE = frozenset({"check", "blank"})


# Empty, and asserted as such rather than deleted: the inventory is derived
# from the clauses rather than from what happens to be registered, so the
# question "is there a check nobody claims" stays worth asking even on the
# day the answer is no. 16.1's compiled rollforward was the last row to be
# claimed, by the scan that lowers it.
_NOT_LOWERED_YET: Final[frozenset[str]] = frozenset()
