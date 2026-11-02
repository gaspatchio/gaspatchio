# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the semantic op-tree IR: construction, walk, and col_refs.

``gaspatchio._semantic.ir`` is the engine-free layer every lowering
backend builds on: a closed, frozen set of node types plus two pure
traversal functions. These tests pin that contract down -- construction,
immutability, structural equality/hashability (including use as dict
keys and set members), pre-order ``walk``, and ``col_refs`` column-name
extraction -- so the vocabulary cannot silently widen or narrow later.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    OpNode,
    State,
    WhenThen,
    col_refs,
    walk,
)

# One instance of every node kind in the closed vocabulary. Reused to
# prove frozen-ness and hashability hold uniformly across the whole set,
# rather than one node type at a time.
ALL_NODE_KINDS: tuple[OpNode, ...] = (
    Col("policies_in_force"),
    Lit(0.0025),
    BinOp(op="mul", left=Col("policies_in_force"), right=Col("mortality_rate")),
    Call(name="cumulative_survival", args=(Col("mortality_rate"),)),
    WhenThen(
        cond=Col("policies_in_force"),
        then=Col("death_claims"),
        otherwise=Lit(0.0),
    ),
    State("account_value"),
    EngineNative(
        engine="polars",
        text="pl.col('mortality_rate').cum_prod()",
        deps=("mortality_rate",),
    ),
)


# --- Construction ------------------------------------------------------


def test_col_holds_a_column_name() -> None:
    """Col stores the referenced column name verbatim."""
    assert Col("policies_in_force").name == "policies_in_force"


def test_lit_holds_a_scalar_value_of_any_allowed_type() -> None:
    """Lit stores its scalar payload verbatim for each allowed value type."""
    assert Lit(0.0025).value == 0.0025
    assert Lit(1).value == 1
    assert Lit(value=True).value is True
    assert Lit("annuity").value == "annuity"


def test_lit_holds_a_sequence_of_scalars_as_a_tuple() -> None:
    """A band of age boundaries is one literal, and it keeps every boundary.

    ``Table.lookup(band=[18, 35, 55])`` writes a sequence into a formula
    the same way it writes a number into one. Storing it as a tuple is
    what keeps the node frozen, hashable and compared by its values.
    """
    node = Lit((18, 35, 55))
    assert node.value == (18, 35, 55)
    assert Lit((0.01, 0.02)).value == (0.01, 0.02)
    assert Lit(("male", "female")).value == ("male", "female")


def test_two_sequence_literals_with_the_same_values_are_one_node() -> None:
    """Structural equality reaches inside the sequence, and so does the hash."""
    assert Lit((18, 35, 55)) == Lit((18, 35, 55))
    assert hash(Lit((18, 35, 55))) == hash(Lit((18, 35, 55)))
    assert Lit((18, 35, 55)) != Lit((18, 35, 56))
    assert Lit((18, 35)) != Lit((35, 18))


def test_a_sequence_of_one_is_not_the_scalar_it_holds() -> None:
    """A band with one boundary is a band, not the boundary."""
    assert Lit((45,)) != Lit(45)


def test_binop_holds_operator_and_both_children() -> None:
    """BinOp stores the op name plus the left/right operand nodes."""
    node = BinOp(op="mul", left=Col("policies_in_force"), right=Col("mortality_rate"))
    assert node.op == "mul"
    assert node.left == Col("policies_in_force")
    assert node.right == Col("mortality_rate")


def test_call_attrs_default_to_empty_tuple() -> None:
    """Call.attrs defaults to () when a call carries no keyword attributes."""
    node = Call(name="cumulative_survival", args=(Col("mortality_rate"),))
    assert node.name == "cumulative_survival"
    assert node.args == (Col("mortality_rate"),)
    assert node.attrs == ()


def test_whenthen_holds_condition_and_both_branches() -> None:
    """WhenThen stores cond/then/otherwise as three independent op-nodes."""
    node = WhenThen(
        cond=Col("policies_in_force"),
        then=Col("death_claims"),
        otherwise=Lit(0.0),
    )
    assert node.cond == Col("policies_in_force")
    assert node.then == Col("death_claims")
    assert node.otherwise == Lit(0.0)


def test_state_holds_a_rollforward_state_name() -> None:
    """State stores the name of the rollforward state it references."""
    assert State("account_value").name == "account_value"


def test_engine_native_holds_engine_source_text_and_deps() -> None:
    """EngineNative stores its target engine, native source text, and deps."""
    node = EngineNative(
        engine="polars",
        text="pl.col('mortality_rate').cum_prod()",
        deps=("mortality_rate",),
    )
    assert node.engine == "polars"
    assert node.text == "pl.col('mortality_rate').cum_prod()"
    assert node.deps == ("mortality_rate",)


# --- Frozen-ness ---------------------------------------------------------


@pytest.mark.parametrize("node", ALL_NODE_KINDS, ids=lambda node: type(node).__name__)
def test_every_node_kind_is_frozen(node: OpNode) -> None:
    """Every node in the closed vocabulary rejects attribute assignment."""
    with pytest.raises(FrozenInstanceError):
        node.something = 42  # type: ignore[union-attr]


# --- Equality and hashability ---------------------------------------------


def test_equal_value_nodes_compare_equal_and_hash_equal() -> None:
    """Two nodes built from the same values are equal and hash-equal."""
    first = BinOp(op="mul", left=Col("policies_in_force"), right=Col("mortality_rate"))
    second = BinOp(op="mul", left=Col("policies_in_force"), right=Col("mortality_rate"))
    assert first == second
    assert hash(first) == hash(second)


def test_different_value_nodes_compare_unequal() -> None:
    """Nodes differing in any field compare unequal."""
    assert Col("policies_in_force") != Col("mortality_rate")
    assert Lit(1) != Lit(2)
    left, right = Lit(1), Lit(2)
    assert BinOp(op="add", left=left, right=right) != BinOp(
        op="sub", left=left, right=right
    )


def test_lit_true_equals_lit_one_because_bool_is_an_int_subclass() -> None:
    """Lit(True) == Lit(1): bool is an int subclass under plain dataclass eq.

    Value-precision identity (keeping True distinct from 1) is a later
    layer's job, not this node's -- see the module docstring.
    """
    assert Lit(value=True) == Lit(value=1)
    assert hash(Lit(value=True)) == hash(Lit(value=1))


def test_nodes_are_usable_as_dict_keys_and_set_members() -> None:
    """Every node kind, including a Call carrying typed attrs, is hashable."""
    call_with_attrs = Call(
        name="at_period",
        args=(Col("reserve"),),
        attrs=(("offset", -1),),
    )
    node_set = {*ALL_NODE_KINDS, call_with_attrs}
    assert len(node_set) == len(ALL_NODE_KINDS) + 1

    label_by_node = {node: type(node).__name__ for node in ALL_NODE_KINDS}
    label_by_node[call_with_attrs] = "Call"
    assert label_by_node[call_with_attrs] == "Call"
    assert label_by_node[Col("policies_in_force")] == "Col"


def test_call_attrs_hold_typed_values_not_stringified() -> None:
    """Call.attrs values keep their Python type -- -1 stays an int."""
    node = Call(
        name="at_period",
        args=(Col("reserve"),),
        attrs=(("offset", -1),),
    )
    attr_name, attr_value = node.attrs[0]
    assert attr_name == "offset"
    assert attr_value == -1
    assert isinstance(attr_value, int)


# --- walk(): pre-order traversal ------------------------------------------


def test_walk_a_leaf_yields_only_itself() -> None:
    """walk() on a Col/Lit/State/EngineNative leaf yields just that node."""
    leaf = Col("policies_in_force")
    assert list(walk(leaf)) == [leaf]


def test_walk_binop_visits_node_then_left_then_right() -> None:
    """walk() on BinOp yields the node, then left, then right."""
    left = Col("policies_in_force")
    right = Col("mortality_rate")
    node = BinOp(op="mul", left=left, right=right)
    assert list(walk(node)) == [node, left, right]


def test_walk_call_visits_args_in_declared_order() -> None:
    """walk() on Call yields the node, then each arg in call order."""
    first_arg = Col("mortality_rate")
    second_arg = Lit(-1)
    node = Call(name="at_period", args=(first_arg, second_arg))
    assert list(walk(node)) == [node, first_arg, second_arg]


def test_walk_whenthen_visits_cond_then_branch_then_otherwise() -> None:
    """walk() on WhenThen yields node, cond, then, otherwise -- in order."""
    cond = Col("policies_in_force")
    then_branch = Col("death_claims")
    otherwise_branch = Lit(0.0)
    node = WhenThen(cond=cond, then=then_branch, otherwise=otherwise_branch)
    assert list(walk(node)) == [node, cond, then_branch, otherwise_branch]


def test_walk_nested_tree_is_fully_pre_order() -> None:
    """A mixed tree walks node-first, children-in-field-order, recursively.

    Builds ``when(policies_in_force).then(sum_assured * (policies_in_force
    * mortality_rate)).otherwise(0.0)`` and checks the exact pre-order
    sequence across BinOp, WhenThen, Col, and Lit together.
    """
    mortality_rate = Col("mortality_rate")
    policies_in_force = Col("policies_in_force")
    death_claims = BinOp(op="mul", left=policies_in_force, right=mortality_rate)
    sum_assured = Col("sum_assured")
    claim_amount = BinOp(op="mul", left=death_claims, right=sum_assured)
    zero = Lit(0.0)
    node = WhenThen(cond=policies_in_force, then=claim_amount, otherwise=zero)

    assert list(walk(node)) == [
        node,
        policies_in_force,
        claim_amount,
        death_claims,
        policies_in_force,
        mortality_rate,
        sum_assured,
        zero,
    ]


# --- col_refs(): column-name extraction ------------------------------------


def test_col_refs_of_a_single_col_is_its_name() -> None:
    """col_refs() on a bare Col returns a one-tuple of its name."""
    assert col_refs(Col("policies_in_force")) == ("policies_in_force",)


def test_col_refs_returns_a_tuple() -> None:
    """col_refs() returns tuple[str, ...], not a list."""
    assert isinstance(col_refs(Col("premiums")), tuple)


def test_col_refs_deduplicates_preserving_first_occurrence_order() -> None:
    """A Col referenced twice keeps only its first position in the result."""
    node = BinOp(
        op="sub",
        left=BinOp(
            op="mul",
            left=Col("policies_in_force"),
            right=Col("mortality_rate"),
        ),
        right=Col("policies_in_force"),
    )
    assert col_refs(node) == ("policies_in_force", "mortality_rate")


def test_col_refs_includes_engine_native_deps() -> None:
    """col_refs() reports EngineNative.deps alongside ordinary Col names."""
    node = BinOp(
        op="add",
        left=Col("policies_in_force"),
        right=EngineNative(
            engine="polars",
            text="pl.col('mortality_rate').cum_prod()",
            deps=("mortality_rate", "duration"),
        ),
    )
    assert col_refs(node) == ("policies_in_force", "mortality_rate", "duration")


def test_col_refs_deduplicates_across_col_and_engine_native() -> None:
    """A name already seen via Col is not repeated when EngineNative also deps it."""
    node = BinOp(
        op="add",
        left=Col("mortality_rate"),
        right=EngineNative(
            engine="polars",
            text="pl.col('mortality_rate')",
            deps=("mortality_rate",),
        ),
    )
    assert col_refs(node) == ("mortality_rate",)


def test_col_refs_excludes_state_names() -> None:
    """A rollforward State reference is not a column read."""
    node = BinOp(op="add", left=Col("premiums"), right=State("account_value"))
    assert col_refs(node) == ("premiums",)


def test_col_refs_of_a_bare_state_is_empty() -> None:
    """col_refs() on a lone State node reports no column names at all."""
    assert col_refs(State("account_value")) == ()


# --- Lit non-finite rejection ------------------------------------------------


def test_lit_rejects_nan() -> None:
    """Lit(nan) raises ValueError: a non-finite literal is a bug, not a value."""
    with pytest.raises(ValueError, match="not finite"):
        Lit(float("nan"))


def test_lit_rejects_positive_infinity() -> None:
    """Lit(inf) raises ValueError."""
    with pytest.raises(ValueError, match="not finite"):
        Lit(float("inf"))


def test_lit_rejects_negative_infinity() -> None:
    """Lit(-inf) raises ValueError."""
    with pytest.raises(ValueError, match="not finite"):
        Lit(float("-inf"))


def test_lit_error_names_the_value_and_points_upstream() -> None:
    """The message names the offending value and points at the upstream fix.

    ``Lit`` has no column parameter to report -- the node layer has no
    column context, so the message cannot and does not fabricate one.
    """
    with pytest.raises(ValueError, match="not finite") as excinfo:
        Lit(float("nan"))
    message = str(excinfo.value)
    assert message.startswith("nan is not finite:")
    assert "bug" in message.lower()
    assert "upstream" in message.lower()


def test_a_non_finite_number_inside_a_sequence_is_refused() -> None:
    """A NaN buried in a band is refused, and the message says where it is.

    The top-level gate alone would wave this through: the value is a
    tuple, not a float. A band boundary that arrived as NaN is the same
    upstream bug wherever in the sequence it sits, so the message names
    the position rather than leaving it to be hunted. It names the member
    bare, too -- the literal under construction is
    ``Lit((0.01, nan, 0.03))``, so a message reading ``Lit(nan)`` would
    point at a node the tree never built.
    """
    with pytest.raises(ValueError, match="position 1") as excinfo:
        Lit((0.01, float("nan"), 0.03))

    assert str(excinfo.value).startswith("nan is not finite at position 1:")


def test_every_non_finite_kind_inside_a_sequence_is_refused() -> None:
    """The two infinities are refused inside a sequence exactly as NaN is."""
    for bad in (float("inf"), -float("inf"), float("nan")):
        with pytest.raises(ValueError, match="position 2"):
            Lit((0.01, 0.02, bad))


def test_a_sequence_of_ordinary_values_constructs() -> None:
    """Finite numbers, whole numbers, flags and text all pass the gate."""
    assert Lit((0.0, -1_000_000.5)).value == (0.0, -1_000_000.5)
    assert Lit((18, 35, 55)).value == (18, 35, 55)
    assert Lit((True, False)).value == (True, False)
    assert Lit(("level_premium", "single_premium")).value == (
        "level_premium",
        "single_premium",
    )
    assert Lit(()).value == ()


def test_lit_accepts_ordinary_finite_values() -> None:
    """Finite floats, ints, bools, and strings all construct without error."""
    assert Lit(0.0).value == 0.0
    assert Lit(-1_000_000.5).value == -1_000_000.5
    assert Lit(0).value == 0
    assert Lit(value=False).value is False
    assert Lit("level_premium").value == "level_premium"
