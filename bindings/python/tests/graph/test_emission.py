# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for proxy emission: what a formula builds before anything is lowered.

``af.claims = af.sum_assured * af.pols_death`` no longer builds a Polars
expression inside ``__mul__``. It builds ``BinOp("mul", Col("sum_assured"),
Col("pols_death"))`` and hands back a proxy carrying that node; the Polars
expression is derived once, later, by ``lower_polars``. These tests pin
three things about that arrangement:

- **The node a formula emits** -- operand order, operator name, and how a
  raw Polars expression, a plain number, and a reflected operator each
  enter the tree.
- **When lowering happens** -- once per proxy, on first contact, no matter
  how long the operator chain that produced it.
- **The private Polars surface the interop relies on** -- the canary
  battery below. ``ProxyAwareExpr`` subclasses ``pl.Expr`` and reaches into
  ``_from_pyexpr``/``_pyexpr``; every assumption that makes load-bearing is
  asserted here, so a Polars upgrade that moves one fails loudly instead of
  silently changing what a model computes.
"""
# Emission is a private surface by design -- `_node` is what a formula
# builds and `_expr` is what lowering derives from it, and neither is API a
# model author touches. Asserting on them here is the point of the file.

from __future__ import annotations

import datetime
import decimal

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import BinOp, Call, Col, EngineNative, Lit, WhenThen
from gaspatchio.column.condition_expression import ConditionExpression
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.column.proxy_aware_expr import _REFLECTED, ProxyAwareExpr
from gaspatchio.frame.lowering import polars as lowering_module
from gaspatchio.frame.lowering.context import LoweringContext
from gaspatchio.frame.lowering.ingress import NATIVE_REFS, to_node
from gaspatchio.frame.lowering.polars import lower_polars

# =============================================================================
# Fixture
# =============================================================================


def _build_frame() -> ActuarialFrame:
    """Build a small frame carrying both per-policy and per-period columns."""
    return ActuarialFrame(
        {
            "policy_id": [1, 2],
            "sum_assured": [100_000.0, 250_000.0],
            "policy_term": [2, 3],
            "policies_in_force": [[1000.0, 990.0, 980.0], [500.0, 495.0, 490.0]],
            "mortality_rate": [[0.01, 0.02, 0.03], [0.04, 0.05, 0.06]],
            "duration": [[0, 1, 2], [0, 1, 2]],
        }
    )


# =============================================================================
# The node a formula emits
# =============================================================================


def test_multiplying_two_columns_emits_one_binop_node() -> None:
    """The headline case: the formula is the node."""
    af = _build_frame()
    claims = af.sum_assured * af.policies_in_force
    assert claims._node == BinOp(  # noqa: SLF001
        op="mul", left=Col("sum_assured"), right=Col("policies_in_force")
    )


@pytest.mark.parametrize(
    ("formula", "op"),
    [
        (lambda af: af.sum_assured + 1, "add"),
        (lambda af: af.sum_assured - 1, "sub"),
        (lambda af: af.sum_assured * 1, "mul"),
        (lambda af: af.sum_assured / 1, "div"),
        (lambda af: af.sum_assured // 1, "floordiv"),
        (lambda af: af.sum_assured % 1, "mod"),
        (lambda af: af.sum_assured**1, "pow"),
    ],
    ids=["add", "sub", "mul", "div", "floordiv", "mod", "pow"],
)
def test_each_arithmetic_operator_emits_its_own_binop(formula, op) -> None:
    af = _build_frame()
    assert formula(af)._node == BinOp(op=op, left=Col("sum_assured"), right=Lit(1))  # noqa: SLF001


@pytest.mark.parametrize(
    ("formula", "op"),
    [
        (lambda af: 1 + af.sum_assured, "add"),
        (lambda af: 1 - af.sum_assured, "sub"),
        (lambda af: 1 * af.sum_assured, "mul"),
        (lambda af: 1 / af.sum_assured, "div"),
        (lambda af: 1 // af.sum_assured, "floordiv"),
        (lambda af: 1 % af.sum_assured, "mod"),
        (lambda af: 1**af.sum_assured, "pow"),
    ],
    ids=["radd", "rsub", "rmul", "rdiv", "rfloordiv", "rmod", "rpow"],
)
def test_reflected_operator_keeps_the_order_the_author_wrote(formula, op) -> None:
    """``1 - af.column`` is a subtraction *from* one, not the mirror image.

    All seven reflected operators are pinned, not only subtraction: operand
    order is load-bearing for the broadcast rule (which asks whether the
    *left* child is a bare column), so a reflected dunder that quietly
    mirrored its operands would change a per-period plan while still
    producing the right answer on the commutative half of the set.
    """
    af = _build_frame()
    assert formula(af)._node == BinOp(op=op, left=Lit(1), right=Col("sum_assured"))  # noqa: SLF001


def test_negation_emits_multiplication_by_an_integer_minus_one() -> None:
    """Negation stays a multiply so it keeps working on per-period columns.

    The literal must stay an ``int``: -1.0 would widen every integer column
    to Float64, and a widened duration can no longer key an integer
    assumption table.
    """
    af = _build_frame()
    assert (-af.sum_assured)._node == BinOp(  # noqa: SLF001
        op="mul", left=Col("sum_assured"), right=Lit(-1)
    )


def test_comparison_emits_a_binop_inside_a_predicate_wrapper() -> None:
    """A comparison is still a node; the wrapper marks it as a predicate."""
    af = _build_frame()
    predicate = af.duration == af.policy_term
    assert isinstance(predicate, ConditionExpression)
    assert predicate._node == BinOp(  # noqa: SLF001
        op="eq", left=Col("duration"), right=Col("policy_term")
    )
    assert predicate.operator == "eq"


def test_python_reflects_a_comparison_rather_than_calling_a_mirror_dunder() -> None:
    """``12 >= af.duration`` arrives as ``af.duration <= 12``, per Python.

    There is no ``__rge__``; the interpreter swaps the operands and the
    operator itself, so the emitted node reads with the column on the left.
    """
    af = _build_frame()
    assert (12 >= af.duration)._node == BinOp(  # noqa: SIM300, SLF001
        op="le", left=Col("duration"), right=Lit(12)
    )


def test_when_chain_emits_nested_when_then_nodes() -> None:
    """A two-case chain folds to ``WhenThen`` inside ``WhenThen``'s otherwise."""
    af = _build_frame()
    result = (
        when(af.duration == af.policy_term)
        .then(af.sum_assured)
        .when(af.duration == 0)
        .then(1.0)
        .otherwise(0.0)
    )
    assert result._node == WhenThen(  # noqa: SLF001
        cond=BinOp(op="eq", left=Col("duration"), right=Col("policy_term")),
        then=Col("sum_assured"),
        otherwise=WhenThen(
            cond=BinOp(op="eq", left=Col("duration"), right=Lit(0)),
            then=Lit(1.0),
            otherwise=Lit(0.0),
        ),
    )


def test_boolean_combinators_emit_logical_binops() -> None:
    af = _build_frame()
    combined = (af.duration > 0) & (af.duration < 2)
    assert combined._node == BinOp(  # noqa: SLF001
        op="and",
        left=BinOp(op="gt", left=Col("duration"), right=Lit(0)),
        right=BinOp(op="lt", left=Col("duration"), right=Lit(2)),
    )
    either = (af.duration > 0) | (af.duration < 2)
    assert either._node.op == "or"  # noqa: SLF001


# =============================================================================
# Ingress: what a non-proxy operand becomes
# =============================================================================


def test_raw_polars_operand_becomes_an_engine_native_node_naming_its_reads() -> None:
    """The framework has no semantic view of an expression it did not build."""
    af = _build_frame()
    raw = pl.col("mortality_rate").list.sum()
    result = af.sum_assured * raw
    right = result._node.right  # noqa: SLF001
    assert isinstance(right, EngineNative)
    assert right.engine == "polars"
    assert right.deps == ("mortality_rate",)


def test_raw_polars_operand_is_recoverable_from_the_ingress_table() -> None:
    """``NATIVE_REFS`` resolves the node back to the very object it wrapped."""
    af = _build_frame()
    raw = pl.col("mortality_rate").list.sum()
    node = (af.sum_assured * raw)._node.right  # noqa: SLF001
    held_node, held_expr = NATIVE_REFS[id(node)]
    assert held_node is node
    assert held_expr is raw


def test_ingress_table_holds_the_node_so_its_identity_key_stays_valid() -> None:
    """The entry keeps the node alive: an ``id()`` freed for reuse would collide."""
    node = to_node(pl.col("premiums"))
    entry = NATIVE_REFS[id(node)]
    assert entry[0] is node


def test_a_value_with_no_literal_form_enters_as_engine_native() -> None:
    """A value the op-tree cannot spell is not a value it refuses.

    An instant, and no longer a date: the grammar mints a tag for a date and
    none for a ``datetime``, so this is the shape the claim is still about.
    An instant is tested before a date at every door -- ``datetime.datetime``
    is a subclass of ``datetime.date`` -- which is what keeps it on the
    engine path whatever the date switch reads.
    """
    node = to_node(datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC))
    assert isinstance(node, EngineNative)
    assert node.deps == ()


def test_a_python_list_operand_becomes_a_literal_not_engine_text() -> None:
    """A band of boundaries is a literal the tree can spell, so it spells it.

    Handing it to the engine instead threw the values away and kept the
    engine's abbreviated display of them, which is how two different
    bands came to be one calculation.
    """
    node = to_node([45, 50, 55])
    assert node == Lit((45, 50, 55))


def test_a_tuple_operand_is_the_same_literal_as_the_list() -> None:
    """The container the author reached for is not part of what they wrote."""
    assert to_node((45, 50, 55)) == to_node([45, 50, 55])


def test_a_sequence_of_text_is_a_literal_too() -> None:
    """Product codes and gender labels are as much a literal as a rate is."""
    assert to_node(["male", "female"]) == Lit(("male", "female"))


def test_a_list_holding_something_the_tree_has_no_literal_for_stays_engine_native() -> (
    None
):
    """A sequence is only a literal when every member is one.

    The op-tree has no literal form for a date, so a list of dates keeps
    today's path -- the engine holds it, and the tree says honestly that
    it cannot see inside.
    """
    node = to_node([datetime.date(2026, 1, 1)])
    assert isinstance(node, EngineNative)


def test_a_list_holding_a_numpy_number_stays_engine_native_today() -> None:
    """Narrowing reaches a bare NumPy scalar, not one inside a sequence.

    Pinned as *current behaviour*, not endorsed: the "a literal like any
    other" rationale that narrows ``numpy.int64(12)`` on its own would
    argue for narrowing it inside a band too, and this test is where that
    decision gets made if somebody makes it.
    """
    node = to_node([np.int64(45), np.int64(50)])
    assert isinstance(node, EngineNative)


def test_a_band_still_gets_the_explicit_broadcast_engine_text_used_to_get() -> None:
    """A sequence literal is not the scalar Polars broadcasts for itself.

    The ``+``/``-`` pre-broadcast exists because Polars fails supertype
    derivation for a compound scalar against a list, and it exempts the
    leaves Polars does handle -- a bare column, and a literal that is one
    value. A sequence literal is not one of those: to Polars it is a
    list-typed literal. It reached lowering as engine text before and took
    the pre-broadcast; it reaches lowering as a literal now and takes the
    same one, so what the engine is asked to compute is unchanged.
    """
    af = _build_frame()
    per_period = pl.col("mortality_rate")
    band = pl.lit([1.0, 2.0, 3.0])
    expected = per_period.add(band.repeat_by(per_period.list.len()))

    lowered = lower_polars(
        BinOp("add", Col("mortality_rate"), Lit((1.0, 2.0, 3.0))),
        LoweringContext(frame=af),
    )

    assert lowered.meta.serialize() == expected.meta.serialize()


def test_a_per_period_column_plus_a_band_is_refused_the_way_it_always_was() -> None:
    """Adding one value per period to a per-period column stays a refusal.

    The pre-broadcast makes a list of lists on the right, which Polars
    refuses outright -- and a loud refusal is the answer this formula has
    always had. Pinned so that the literal's new identity cannot quietly
    turn it into a silently computed nonsense.
    """
    af = _build_frame()
    band = [1.0, 2.0, 3.0]
    af.answer = af.mortality_rate + band

    with pytest.raises(pl.exceptions.InvalidOperationError, match="cannot add"):
        af.collect()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (np.int64(12), Lit(12)),
        (np.int32(12), Lit(12)),
        (np.float64(1.5), Lit(1.5)),
        (np.float32(0.5), Lit(0.5)),
    ],
    ids=["int64", "int32", "float64", "float32"],
)
def test_a_numpy_number_enters_as_the_literal_it_is(value, expected) -> None:
    """``numpy.int64(12)`` and ``12`` are the same literal, so they are one node.

    Model-point arrays and period counts arrive as NumPy scalars all the
    time. Treating one as an opaque engine value would lose its literal
    form, cost an ingress-table entry that is never freed, and make two
    formulas that wrote the same number compare unequal -- which is the
    thing structural node equality exists to prevent.
    """
    node = to_node(value)
    assert node == expected
    assert type(node.value) is type(expected.value)


def test_a_numpy_boolean_stays_engine_native_today() -> None:
    """``numpy.bool_`` is not a Python ``bool``, and is not narrowed.

    NumPy registers its integer and float scalars with ``numbers``, but
    not ``bool_``: it is neither ``Integral`` nor ``Real`` nor a ``bool``
    subclass, so it falls through to the engine-native branch. Pinned as
    *current behaviour*, not endorsed -- the "a literal like any other"
    rationale would argue for narrowing it too, and this test is where
    that decision gets made if somebody makes it.
    """
    numpy_true = np.array([True])[0]
    assert isinstance(numpy_true, np.bool_)
    node = to_node(numpy_true)
    assert isinstance(node, EngineNative)


def test_a_decimal_is_the_number_it_denotes() -> None:
    """A ``Decimal`` literal is read as the number it denotes, as a book column is.

    Section 10 names no fixed-point decimal, so the record carries the value
    the run computes with: written with places, the double nearest it;
    written with none, the whole number.
    """
    assert to_node(decimal.Decimal("1.5")) == Lit(1.5)
    assert to_node(decimal.Decimal(12)) == Lit(12)
    assert to_node(decimal.Decimal("12.00")) == Lit(12.0)


def test_an_object_carrying_a_non_node_is_refused_by_name() -> None:
    """``_node`` is the op-tree's own attribute, not a name anything may claim.

    ``to_node`` used to trust any object exposing ``_node`` and hand
    whatever it found straight into the tree, where it would surface much
    later as an unlowerable node. The refusal names the offending type.
    """

    class Impostor:
        _node = "not a node at all"

    with pytest.raises(TypeError, match=r"Impostor\._node is a str"):
        to_node(Impostor())


def test_an_op_tree_node_passes_straight_through() -> None:
    """A node is already a node -- a caller that builds one hands it through.

    A frame-level method is where a string genuinely names a column, so
    ``af.finance.discount_factor("rate", "month", "v_t")`` resolves that
    name to a ``Col`` itself rather than letting the default
    string-is-a-literal reading apply.
    """
    node = Col("fee")
    assert to_node(node) is node


def test_multiplying_by_a_non_finite_float_is_refused_at_the_formula_line() -> None:
    """NaN in a formula is a bug upstream, not a value to carry forward."""
    af = _build_frame()
    with pytest.raises(ValueError, match="not finite"):
        _ = af.sum_assured * float("nan")


# =============================================================================
# When lowering happens
# =============================================================================


def test_a_chain_of_ten_operators_lowers_exactly_once(monkeypatch) -> None:
    """Emission is free; lowering happens once, on first contact."""
    calls: list[int] = []
    real_lower = lowering_module.lower_polars

    def counting_lower(node, ctx=None) -> pl.Expr:
        calls.append(1)
        return real_lower(node, ctx)

    monkeypatch.setattr(lowering_module, "lower_polars", counting_lower)

    af = _build_frame()
    chained = af.policies_in_force
    for _ in range(10):
        chained = chained * 1.0
    assert calls == []

    _ = chained._expr  # noqa: SLF001
    assert len(calls) == 1

    _ = chained._expr  # noqa: SLF001
    assert len(calls) == 1, "a second contact must reuse the cached expression"


def test_lowering_is_cached_on_the_proxy_not_recomputed_per_contact() -> None:
    af = _build_frame()
    total = af.sum_assured * af.policies_in_force
    assert total._expr is total._expr  # noqa: SLF001


# =============================================================================
# Shape dispatch relocated into lowering
# =============================================================================


def test_per_period_maturity_conditional_computes_element_wise() -> None:
    """A per-period predicate against a per-policy scalar, end to end."""
    af = _build_frame()
    af.maturity_flag = when(af.duration == af.policy_term).then(1.0).otherwise(0.0)
    result = af.collect()
    assert result["maturity_flag"].to_list() == [[0.0, 0.0, 1.0], [0.0, 0.0, 0.0]]


def test_scalar_times_per_period_column_broadcasts() -> None:
    af = _build_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    result = af.collect()
    assert result["death_claims"].to_list()[0] == pytest.approx(
        [1000.0, 2000.0, 3000.0]
    )


def test_compound_scalar_minus_per_period_column_broadcasts() -> None:
    """The gh#53 shape: a computed scalar against a list needs an explicit repeat."""
    af = _build_frame()
    af.survival = (1.0 - af.mortality_rate) * (af.sum_assured / af.sum_assured)
    result = af.collect()
    assert result["survival"].to_list()[0] == pytest.approx([0.99, 0.98, 0.97])


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        (
            lambda af, compound: af.policies_in_force + compound,
            [1000.0 + 2.0, 990.0 + 2.0, 980.0 + 2.0],
        ),
        (
            lambda af, compound: ProxyAwareExpr.wrap(compound) + af.policies_in_force,
            [2.0 + 1000.0, 2.0 + 990.0, 2.0 + 980.0],
        ),
        (
            lambda af, compound: af.policies_in_force - compound,
            [1000.0 - 2.0, 990.0 - 2.0, 980.0 - 2.0],
        ),
        (
            lambda af, compound: ProxyAwareExpr.wrap(compound) - af.policies_in_force,
            [2.0 - 1000.0, 2.0 - 990.0, 2.0 - 980.0],
        ),
    ],
    ids=["list_plus_raw", "raw_plus_list", "list_minus_raw", "raw_minus_list"],
)
def test_per_period_column_add_sub_a_raw_compound_scalar(formula, expected) -> None:
    """gh#53, with the compound scalar written as a raw Polars expression.

    Before the emission cutover the broadcast rule only fired when the
    compound scalar arrived as a framework proxy; a bare ``pl.Expr`` -- what
    an assumption-table lookup or any escape-hatch calculation hands back --
    got no broadcast and the addition failed on supertype derivation. Under
    the op-tree both arrive as the same node kind, so all four operand
    orders work. Pinned so the four cannot silently regress to "works only
    if you wrote it as a proxy".

    The two raw-on-the-left cases go through ``ProxyAwareExpr.wrap``,
    which is exactly what ``Table.lookup`` hands back: a bare ``pl.Expr``
    on the left raises inside Polars before the framework is ever
    consulted (gh#67), which is the whole reason that wrapper exists.
    """
    af = _build_frame()
    compound = pl.col("policy_term") * pl.lit(1.0) - pl.col("policy_term") + pl.lit(2.0)
    af.adjusted = formula(af, compound)
    result = af.collect()
    assert result["adjusted"].to_list()[0] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("operator_form", "method_form"),
    [
        (lambda column, other: column + other, lambda column, other: column.add(other)),
        (lambda column, other: column - other, lambda column, other: column.sub(other)),
        (lambda column, other: column * other, lambda column, other: column.mul(other)),
        (
            lambda column, other: column / other,
            lambda column, other: column.truediv(other),
        ),
        (
            lambda column, other: column // other,
            lambda column, other: column.floordiv(other),
        ),
        (lambda column, other: column % other, lambda column, other: column.mod(other)),
        (lambda column, other: column**other, lambda column, other: column.pow(other)),
    ],
    ids=["add", "sub", "mul", "truediv", "floordiv", "mod", "pow"],
)
def test_the_named_method_agrees_with_its_operator(operator_form, method_form) -> None:
    """``x.add(y)`` and ``x + y`` are one operation, so they emit one node.

    They used not to be. The named-method surface owned a second copy of
    the arithmetic shape-decision table, and the copies disagreed on
    exactly this shape: a per-period column against a *compound* scalar
    that references two columns. Through ``+`` it worked; through
    ``.add()`` it raised ``SchemaError``. The second copy is gone -- both
    spellings emit the same node and take the same lowering rule -- and
    this pins that they still do, node and value.

    The compound has to be ``col * col``, not ``col * lit``. Only the
    two-column form failed: the old table keyed its broadcast on the
    argument being a framework proxy, and against a *literal* multiplier
    Polars derived a supertype by itself, so ``col * lit`` agreed on both
    paths and would keep agreeing if the second table came back. A fixture
    that never diverged cannot pin a divergence.
    """
    compound = pl.col("policy_term") * pl.col("policy_term")

    operator_af = _build_frame()
    method_af = _build_frame()
    operator_result = operator_form(operator_af.policies_in_force, compound)
    method_result = method_form(method_af.policies_in_force, compound)

    assert operator_result._node == method_result._node  # noqa: SLF001

    operator_af.adjusted = operator_result
    method_af.adjusted = method_result
    assert_frame_equal(
        operator_af.collect().select("adjusted"),
        method_af.collect().select("adjusted"),
        check_exact=True,
    )


@pytest.mark.parametrize(
    ("method", "keyword"),
    [
        ("add", "other"),
        ("sub", "other"),
        ("mul", "other"),
        ("truediv", "other"),
        ("floordiv", "other"),
        ("mod", "other"),
        ("pow", "exponent"),
    ],
)
def test_the_keyword_spelling_of_an_operator_takes_the_same_path(
    method: str, keyword: str
) -> None:
    """``af.rate.pow(exponent=2)`` is ``af.rate.pow(2)`` is ``af.rate ** 2``.

    Polars names the operand ``other`` for six of the seven and
    ``exponent`` for ``pow``, and a model is free to write either
    spelling. Six survive a wrong turn here because Polars broadcasts them
    natively against a per-period column anyway; ``pow`` does not -- it has
    no kernel for a list base at all, so routing the keyword spelling past
    emission raises ``InvalidOperationError`` on exactly the columns
    actuarial projections are made of. Parametrized over all seven rather
    than just ``pow`` so the next operand rename is caught too.
    """
    af = _build_frame()
    positional = getattr(af.mortality_rate, method)(2)
    by_keyword = getattr(af.mortality_rate, method)(**{keyword: 2})

    assert positional._node == by_keyword._node  # noqa: SLF001

    af.positional = positional
    af.by_keyword = by_keyword
    result = af.collect()
    assert result["positional"].to_list() == result["by_keyword"].to_list()


def test_per_period_column_plus_raw_compound_survives_a_null_and_empty_list() -> None:
    """The same broadcast over a null list and an empty one, not just full ones.

    ``repeat_by`` on a null or zero-length list is where an off-by-one in
    the broadcast would show first: a policy with no projected periods (an
    already-matured contract) must come back with no periods, not one.
    """
    af = ActuarialFrame(
        {
            "policy_term": [2.0, 2.0, 2.0],
            "policies_in_force": [[1000.0, 990.0], [], None],
        }
    )
    compound = pl.col("policy_term") * pl.lit(2.0)
    af.adjusted = af.policies_in_force + compound
    result = af.collect()
    assert result["adjusted"].to_list() == [[1004.0, 994.0], [], None]


def test_per_period_column_raised_to_a_scalar_power() -> None:
    af = _build_frame()
    af.monthly_rate = 1 - (1 - af.mortality_rate) ** (1 / 12)
    result = af.collect()
    assert result["monthly_rate"].to_list()[0][0] == pytest.approx(
        1 - (1 - 0.01) ** (1 / 12)
    )


def test_scalar_raised_to_a_per_period_power() -> None:
    af = _build_frame()
    af.inflation_factor = 1.01 ** (af.duration / 12.0)
    result = af.collect()
    assert result["inflation_factor"].to_list()[0] == pytest.approx(
        [1.01 ** (period / 12.0) for period in (0, 1, 2)]
    )


# =============================================================================
# Canary battery: the private Polars surface the interop stands on
# =============================================================================


def test_from_pyexpr_preserves_the_subclass() -> None:
    """``ProxyAwareExpr.wrap`` depends on this; a Polars change here breaks interop."""
    rebuilt = ProxyAwareExpr._from_pyexpr(pl.col("premiums")._pyexpr)  # noqa: SLF001
    assert type(rebuilt) is ProxyAwareExpr


def test_an_inherited_method_returns_a_plain_expression() -> None:
    """The documented evaporation boundary, asserted rather than assumed.

    An expression with no frame keeps Polars' own methods, and each hands
    back a plain ``pl.Expr``, after which a proxy operand raises again --
    which is why the supported idiom is to assign to a frame column first.
    If a Polars change ever made methods preserve the subclass, this test
    fails and the docstring in ``column/proxy_aware_expr.py`` needs
    rewriting. ``alias`` is the one exception: a rename is not a
    calculation, so it keeps the expression and the node it carries.
    """
    wrapped = ProxyAwareExpr.wrap(pl.col("premiums"))
    assert type(wrapped.clip(0.0, 1.0)) is pl.Expr
    assert type(wrapped.alias("renamed")) is ProxyAwareExpr


def test_a_wrapped_expression_is_still_an_expression_to_polars() -> None:
    """``pl.concat_list`` and friends accept it on the isinstance check alone."""
    wrapped = ProxyAwareExpr.wrap(pl.col("premiums"))
    assert isinstance(wrapped, pl.Expr)
    frame = pl.DataFrame({"premiums": [1.0, 2.0], "claims": [3.0, 4.0]})
    combined = frame.select(pl.concat_list([wrapped, pl.col("claims")]).alias("both"))
    assert combined["both"].to_list() == [[1.0, 3.0], [2.0, 4.0]]


def test_truthiness_is_refused() -> None:
    """``if af.rate > 0`` is a modelling mistake, and Polars says so."""
    wrapped = ProxyAwareExpr.wrap(pl.col("premiums"))
    with pytest.raises(TypeError):
        bool(wrapped)


def test_hash_is_inherited_explicitly_despite_a_custom_eq() -> None:
    """Defining ``__eq__`` would otherwise make the class unhashable."""
    assert ProxyAwareExpr.__hash__ is pl.Expr.__hash__


def test_every_forward_operator_has_its_reflected_twin() -> None:
    """The pairing table is what makes ``lookup(...) * af.col`` work either way."""
    for forward, reflected in _REFLECTED.items():
        assert hasattr(ProxyAwareExpr, forward), forward
        assert hasattr(ProxyAwareExpr, reflected), reflected
        assert _REFLECTED[reflected] == forward, (
            f"{forward}/{reflected} do not mirror each other"
        )


# Every public name on ``pl.Expr`` at the pinned Polars version. The proxy
# classes declare their own operations and forward everything else by name
# through ``polars_native()``, while ``ProxyAwareExpr`` inherits every one of
# them and deliberately wraps none (see the evaporation-boundary test above)
# -- so a Polars upgrade that adds or removes a name changes both surfaces at
# once, silently, unless this check fails first. Regenerate deliberately,
# reviewing what moved.
_POLARS_EXPR_PUBLIC_NAMES: frozenset[str] = frozenset(
    (
        "abs",
        "add",
        "agg_groups",
        "alias",
        "all",
        "and_",
        "any",
        "append",
        "approx_n_unique",
        "arccos",
        "arccosh",
        "arcsin",
        "arcsinh",
        "arctan",
        "arctanh",
        "arg_max",
        "arg_min",
        "arg_sort",
        "arg_true",
        "arg_unique",
        "arr",
        "backward_fill",
        "bin",
        "bitwise_and",
        "bitwise_count_ones",
        "bitwise_count_zeros",
        "bitwise_leading_ones",
        "bitwise_leading_zeros",
        "bitwise_or",
        "bitwise_trailing_ones",
        "bitwise_trailing_zeros",
        "bitwise_xor",
        "bottom_k",
        "bottom_k_by",
        "cast",
        "cat",
        "cbrt",
        "ceil",
        "clip",
        "cos",
        "cosh",
        "cot",
        "count",
        "cum_count",
        "cum_max",
        "cum_min",
        "cum_prod",
        "cum_sum",
        "cumulative_eval",
        "cut",
        "degrees",
        "deserialize",
        "diff",
        "dot",
        "drop_nans",
        "drop_nulls",
        "dt",
        "entropy",
        "eq",
        "eq_missing",
        "ewm_mean",
        "ewm_mean_by",
        "ewm_std",
        "ewm_var",
        "exclude",
        "exp",
        "explode",
        "ext",
        "extend_constant",
        "fill_nan",
        "fill_null",
        "filter",
        "first",
        "flatten",
        "floor",
        "floordiv",
        "forward_fill",
        "from_json",
        "gather",
        "gather_every",
        "ge",
        "get",
        "gt",
        "has_nulls",
        "hash",
        "head",
        "hist",
        "implode",
        "index_of",
        "inspect",
        "interpolate",
        "interpolate_by",
        "is_between",
        "is_close",
        "is_duplicated",
        "is_empty",
        "is_finite",
        "is_first_distinct",
        "is_in",
        "is_infinite",
        "is_last_distinct",
        "is_nan",
        "is_not_nan",
        "is_not_null",
        "is_null",
        "is_sorted",
        "is_unique",
        "item",
        "kurtosis",
        "last",
        "le",
        "len",
        "limit",
        "list",
        "log",
        "log10",
        "log1p",
        "lower_bound",
        "lt",
        "map_batches",
        "map_elements",
        "max",
        "max_by",
        "mean",
        "median",
        "meta",
        "min",
        "min_by",
        "mod",
        "mode",
        "mul",
        "n_unique",
        "name",
        "nan_max",
        "nan_min",
        "ne",
        "ne_missing",
        "neg",
        "not_",
        "null_count",
        "or_",
        "over",
        "pct_change",
        "peak_max",
        "peak_min",
        "pipe",
        "pow",
        "product",
        "qcut",
        "quantile",
        "radians",
        "rank",
        "rechunk",
        "register_plugin",
        "reinterpret",
        "repeat_by",
        "replace",
        "replace_strict",
        "reshape",
        "reverse",
        "rle",
        "rle_id",
        "rolling",
        "rolling_kurtosis",
        "rolling_map",
        "rolling_max",
        "rolling_max_by",
        "rolling_mean",
        "rolling_mean_by",
        "rolling_median",
        "rolling_median_by",
        "rolling_min",
        "rolling_min_by",
        "rolling_quantile",
        "rolling_quantile_by",
        "rolling_rank",
        "rolling_rank_by",
        "rolling_skew",
        "rolling_std",
        "rolling_std_by",
        "rolling_sum",
        "rolling_sum_by",
        "rolling_var",
        "rolling_var_by",
        "round",
        "round_sig_figs",
        "sample",
        "search_sorted",
        "set_sorted",
        "shift",
        "shrink_dtype",
        "shuffle",
        "sign",
        "sin",
        "sinh",
        "skew",
        "slice",
        "sort",
        "sort_by",
        "sqrt",
        "std",
        "str",
        "struct",
        "sub",
        "sum",
        "tail",
        "tan",
        "tanh",
        "to_physical",
        "top_k",
        "top_k_by",
        "truediv",
        "truncate",
        "unique",
        "unique_counts",
        "upper_bound",
        "value_counts",
        "var",
        "where",
        "xor",
    )
)


def test_polars_expression_surface_matches_the_reviewed_inventory() -> None:
    """A Polars upgrade that widens the proxied surface fails here first."""
    actual = frozenset(name for name in dir(pl.Expr) if not name.startswith("_"))
    added = sorted(actual - _POLARS_EXPR_PUBLIC_NAMES)
    removed = sorted(_POLARS_EXPR_PUBLIC_NAMES - actual)
    guidance = (
        "polars_native() forwards this surface by name and ProxyAwareExpr "
        "inherits it, so review what each new name does on a list-shaped "
        "column before adding it to _POLARS_EXPR_PUBLIC_NAMES."
    )
    assert not added, f"polars' pl.Expr surface gained {added}. {guidance}"
    assert not removed, f"polars' pl.Expr surface lost {removed}. {guidance}"


def test_expression_proxy_rejects_a_non_expression_construction() -> None:
    """The eager constructor still guards its one argument."""
    with pytest.raises(TypeError, match="Polars expression"):
        ExpressionProxy("not an expression", None)  # type: ignore[arg-type]


# =============================================================================
# The first-party surface emits nodes
# =============================================================================

# Accessor namespaces whose methods have not been cut over yet, and what
# each still hands back. Listed rather than skipped so the remaining work
# is an inventory somebody can shorten, not a silence: a namespace stays
# here only until its expression-building bodies relocate into
# frame/lowering/rules/, and removing an entry is what proves it did.
_NOT_YET_EMITTING: dict[str, str] = {}


def _accessor_classes() -> dict[str, type]:
    """Every registered first-party accessor class, by class name."""
    from gaspatchio.frame.registry import _ACCESSOR_REGISTRY

    classes: dict[str, type] = {}
    for kinds in _ACCESSOR_REGISTRY.values():
        for accessor_cls in kinds.values():
            classes[accessor_cls.__name__] = accessor_cls
    return classes


def _public_methods(accessor_cls: type) -> list[str]:
    """Public method names defined on this accessor class itself."""
    return [
        name
        for name, value in vars(accessor_cls).items()
        if not name.startswith("_") and callable(value)
    ]


def test_every_first_party_accessor_namespace_is_registered() -> None:
    """The walk below covers all five namespaces, not whichever imported first.

    ``_ACCESSOR_REGISTRY`` is populated by import side effect, so a walk
    over it proves nothing unless the expected namespaces are actually
    there. Importing ``gaspatchio`` is what registers them.

    A superset, not an exact set: ``@register_accessor`` is the framework's
    documented extension point and other tests in this suite register their
    own namespaces, so pinning the registry's exact contents would make
    this test depend on what ran before it.
    """
    from gaspatchio.frame.registry import _ACCESSOR_REGISTRY

    assert {"date", "excel", "finance", "projection"} <= set(_ACCESSOR_REGISTRY)


def test_no_first_party_accessor_method_returns_a_bare_expression() -> None:
    """Every cut-over accessor method emits a node; none builds an expression.

    Read from the declared return type rather than by calling each method:
    a method that says it returns a bare ``pl.Expr`` is building an
    expression and handing it over with nothing attached, which is the
    thing the cutover exists to stop. Evaporation to a bare expression is
    reserved for methods the framework does not own -- Polars' own surface
    reached reflectively -- not for the framework's own named operations.

    ``ProxyAwareExpr`` is deliberately *not* an offender. It is the
    frame-independent egress wrapper (``Table.lookup``, the projection
    timeline methods, the rollforward reads): a real ``pl.Expr``, so raw
    Polars interop keeps working, that also carries the node it was
    lowered from. Whether it really carries one is checked by actually
    calling them, in the companion test below -- an annotation cannot
    tell.
    """
    offenders: list[str] = []
    for class_name, accessor_cls in _accessor_classes().items():
        if class_name in _NOT_YET_EMITTING:
            continue  # pragma: no cover - the list is empty; kept as the mechanism
        for method_name in _public_methods(accessor_cls):
            annotations = getattr(
                getattr(accessor_cls, method_name), "__annotations__", {}
            )
            returns = str(annotations.get("return", ""))
            if "pl.Expr" in returns:
                offenders.append(f"{class_name}.{method_name} -> {returns}")
    assert not offenders, (
        "these accessor methods still hand back an engine expression "
        "instead of emitting a node: " + ", ".join(sorted(offenders))
    )


def _projection_frame() -> ActuarialFrame:
    """Build a frame carrying an inception-anchored projection timeline."""
    af = ActuarialFrame(
        {
            "policy_id": [1, 2],
            "inception": [datetime.date(2024, 1, 31), datetime.date(2024, 6, 30)],
            "end_date": [datetime.date(2026, 1, 31), datetime.date(2026, 6, 30)],
        }
    )
    from gaspatchio.schedule import Schedule

    return af.projection.set(
        schedule=Schedule.from_inception(
            inception_column="inception", n_periods=6, frequency="1M"
        )
    )


@pytest.mark.parametrize(
    "read",
    [
        lambda af: af.projection.period_dates(),
        lambda af: af.projection.year_fractions(),
        lambda af: af.projection.t_years(),
        lambda af: af.projection.anniversary_mask(),
        lambda af: af.projection.is_in_force(),
        lambda af: af.projection.contract_boundary(),
    ],
    ids=[
        "period_dates",
        "year_fractions",
        "t_years",
        "anniversary_mask",
        "is_in_force",
        "contract_boundary",
    ],
)
def test_the_projection_timeline_egress_carries_its_node(read) -> None:
    """Each timeline method hands back an expression that knows what it is.

    These are frame-independent: they describe the projection axis, not a
    column on any one frame, so they stay real ``pl.Expr`` objects (the
    tutorial idiom passes them straight to ``pl.concat_list``). Carrying
    the node is what lets an operand that meets one see a timeline
    expression rather than an opaque one.
    """
    result = read(_projection_frame())
    assert isinstance(result, pl.Expr)
    node = getattr(result, "_node", None)
    assert isinstance(node, Call), f"no Call node on {result!r}"
    assert any(key == "schedule" for key, _ in node.attrs)


def test_a_curve_read_on_a_compound_time_keeps_its_broadcast() -> None:
    """A curve borrows the context of the times it is handed.

    ``af.t_base + af.scale * af.scale`` is a per-period column plus a
    *compound* per-policy scalar, which needs the explicit broadcast the
    lowering context is what makes visible. Lowered without one it fails
    supertype derivation instead of computing — and every other curve test
    passes a bare column, which lowers identically either way, so nothing
    else covers this.
    """
    from gaspatchio.curves import Curve

    curve = Curve.from_zero_rates(
        tenors=[1.0, 2.0, 3.0, 5.0, 10.0], rates=[0.02, 0.022, 0.025, 0.028, 0.03]
    )
    af = ActuarialFrame(
        {"t_base": [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]], "scale": [1.0, 1.0]}
    )
    times = af["t_base"] + (af["scale"] * af["scale"])
    af.discount = curve.discount_factor(times)
    af.spot = curve.spot_rate(times)
    result = af.collect()

    # Times are 2.0, 3.0, 4.0 -- the curve read at each shifted time.
    assert result["spot"].to_list()[0] == pytest.approx([0.022, 0.025, 0.0265])
    assert result["discount"].to_list()[0] == pytest.approx(
        [(1.0 + r) ** -t for r, t in [(0.022, 2.0), (0.025, 3.0), (0.0265, 4.0)]]
    )


def test_the_rollforward_escape_hatch_carries_its_node() -> None:
    """``plugin_expr`` emits like the extraction methods, and still works raw.

    It is the documented way to run a rollforward on a plain Polars frame,
    where there is no ``ActuarialFrame`` to materialise a shared hidden
    column. Being the one public rollforward expression with no semantic
    record behind it would have been an odd exception.
    """
    compiled = _compile_simple_rollforward()
    expr = compiled.plugin_expr()

    node = getattr(expr, "_node", None)
    assert isinstance(node, Call)
    assert node.name == "rollforward.struct"

    frame = pl.DataFrame(
        {"av_init": [100.0], "premium": [[10.0, 10.0]], "rate": [[0.01, 0.01]]}
    )
    materialised = frame.with_columns(expr.alias("rf")).with_columns(
        av=pl.col("rf").struct.field("av@eop")
    )
    assert materialised["av"].to_list() == [[108.9, 117.711]]


def _compile_simple_rollforward() -> object:
    """Compile a two-period premium-then-charge rollforward."""
    from gaspatchio.rollforward import compile_rollforward
    from gaspatchio.schedule import Schedule

    af = ActuarialFrame(
        {"av_init": [100.0], "premium": [[10.0, 10.0]], "rate": [[0.01, 0.01]]}
    )
    af = af.projection.set(
        schedule=Schedule.from_calendar_grid(
            start_date=datetime.date(2025, 1, 31), n_periods=2, frequency="1M"
        )
    )
    builder = af.projection.rollforward(states={"av": af["av_init"]})
    builder["av"].add(af["premium"], label="Premium").charge(af["rate"], label="Fee")
    return compile_rollforward(builder)


def test_every_rollforward_operation_is_classified_for_the_record() -> None:
    """Each Op kind declares an implicit balance read or an explicit amount field.

    Exactly one of the two sets, never both and never neither. A new Op
    added to the vocabulary must be classified deliberately: landing
    silently in "does not read the balance" would degrade every record
    that used it, with no signal. The compiler makes the equivalent
    decision loud, and so does this.
    """
    from gaspatchio.frame.lowering.rules.rollforward import (
        _AMOUNT_FIELD,
        _IMPLICIT_RUNNING_BALANCE,
    )
    from gaspatchio.rollforward import _ops
    from gaspatchio.rollforward._ops import Op

    # Scoped to the operations _ops.py actually declares. __subclasses__()
    # is a live global registry, so a subclass defined anywhere else --
    # including the throwaway one the refusal test below builds -- would
    # otherwise join the vocabulary and make this test's result depend on
    # which order the two ran in.
    kinds = {
        subclass.__name__
        for subclass in Op.__subclasses__()
        if subclass.__module__ == _ops.__name__
    }
    assert kinds, "no Op subclasses found -- the vocabulary moved"

    explicit_amounts = set(_AMOUNT_FIELD)
    classified = _IMPLICIT_RUNNING_BALANCE | explicit_amounts
    assert not (kinds - classified), (
        "unclassified rollforward operation(s): "
        f"{sorted(kinds - classified)} -- decide whether each one's "
        "within-period amount depends on the running balance"
    )
    assert not (classified - kinds), (
        f"stale classification entr(ies): {sorted(classified - kinds)}"
    )
    assert not (_IMPLICIT_RUNNING_BALANCE & explicit_amounts)


def test_an_unclassified_operation_is_refused_rather_than_assumed() -> None:
    """The guard fires by name, so a future Op cannot slip through silently."""
    from gaspatchio.frame.lowering.rules.rollforward import _increment
    from gaspatchio.rollforward._ops import Op

    class Rebase(Op):
        """A hypothetical operation nobody has classified yet."""

    with pytest.raises(NotImplementedError, match="Rebase"):
        _increment(Rebase(), set(), set())


@pytest.mark.parametrize(
    "read",
    [
        lambda sched: sched.period_dates_expr(),
        lambda sched: sched.year_fractions_expr(),
        lambda sched: sched.anniversary_mask_expr(),
        lambda sched: sched.is_in_force_expr(),
        lambda sched: sched.contract_boundary_expr(),
    ],
    ids=[
        "period_dates",
        "year_fractions",
        "anniversary_mask",
        "is_in_force",
        "contract_boundary",
    ],
)
def test_the_schedule_expression_family_carries_its_node(read) -> None:
    """The ``Schedule.*_expr`` family emits nodes too, not just the accessor."""
    from gaspatchio.schedule import Schedule

    sched = Schedule.from_inception(
        inception_column="inception", n_periods=6, frequency="1M"
    )
    result = read(sched)
    node = getattr(result, "_node", None)
    assert isinstance(node, Call), f"no Call node on {result!r}"


@pytest.mark.parametrize(
    "read",
    [
        lambda sched: sched.per_policy_period_dates_expr(),
        lambda sched: sched.per_policy_period_count_expr(),
    ],
    ids=["per_policy_period_dates", "per_policy_period_count"],
)
def test_the_jagged_schedule_methods_carry_their_node(read) -> None:
    """The two per-policy methods emit too -- they only exist on a jagged grid.

    A jagged timeline gives each policy its own horizon, so these are the
    only two schedule methods that cannot be reached from a uniform grid
    and would otherwise go untested by the family case above.
    """
    from gaspatchio.schedule import Schedule

    sched = Schedule.from_per_policy_grid(
        start_date=datetime.date(2025, 1, 31),
        frequency="1M",
        until_kind="term_months",
        until_value_column="term_months",
    )
    result = read(sched)
    node = getattr(result, "_node", None)
    assert isinstance(node, Call), f"no Call node on {result!r}"
    assert any(key == "schedule" for key, _ in node.attrs)


def test_the_uncut_accessor_list_stays_honest() -> None:
    """Every name in ``_NOT_YET_EMITTING`` is a real accessor class.

    An entry left behind after its namespace was cut over would silently
    exempt a namespace that no longer needs exempting.
    """
    known = set(_accessor_classes())
    stale = sorted(set(_NOT_YET_EMITTING) - known)
    assert not stale, f"no such accessor class(es): {stale}"


@pytest.mark.parametrize(
    ("build", "expected_name"),
    [
        (
            lambda af: af.mortality_rate.projection.cumulative_survival(),
            "projection.cumulative_survival",
        ),
        (
            lambda af: af.policies_in_force.projection.previous_period(),
            "projection.previous_period",
        ),
        (lambda af: af.sum_assured.finance.to_monthly(), "finance.to_monthly"),
        (lambda af: af.sum_assured.excel.round(2), "excel.round"),
    ],
    ids=["cumulative_survival", "previous_period", "to_monthly", "excel_round"],
)
def test_an_accessor_method_emits_a_call_named_for_itself(build, expected_name) -> None:
    """The node an accessor emits names the operation, in one readable place."""
    af = _build_frame()
    node = build(af)._node  # noqa: SLF001
    assert node.name == expected_name


def test_a_call_with_no_registered_lowering_fails_at_the_authors_line() -> None:
    """A misspelled operation is refused where it was written, not at collect.

    This is the whole point of checking the registry during emission: the
    alternative is a traceback out of ``.collect()``, three phases and
    fifty formulas away from the line that caused it.
    """
    from gaspatchio._authoring import emit

    with pytest.raises(ValueError, match=r"projection\.cumulatve_survival"):
        emit.call_node("projection.cumulatve_survival", ())


def test_accessor_attributes_stay_typed_on_the_node() -> None:
    """An offset of -1 is the integer -1, never the string "-1".

    Typed attributes are what let a lowering hand a value straight to a
    Polars keyword argument, and what lets a future backend read the same
    node without a parsing step.
    """
    af = _build_frame()
    node = af.policies_in_force.projection.at_period(-2)._node  # noqa: SLF001
    assert node.attrs == (("relative_period", -2),)


def test_graph_accessor_keeps_the_runtime_extension_contract() -> None:
    from gaspatchio.accessors.base import BaseFrameAccessor
    from gaspatchio.frame.graph.calc_graph import GraphFrameAccessor
    from gaspatchio.frame.registry import _ACCESSOR_REGISTRY

    frame = _build_frame()
    assert issubclass(GraphFrameAccessor, BaseFrameAccessor)
    assert isinstance(frame.graph, BaseFrameAccessor)
    assert _ACCESSOR_REGISTRY["graph"]["frame"] is GraphFrameAccessor
