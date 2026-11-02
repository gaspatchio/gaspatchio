# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``lower_polars``: the sole producer of Polars expressions.

``gaspatchio.frame.lowering.polars`` turns one semantic op-tree node (see
``gaspatchio._semantic.ir``) into the ``pl.Expr`` that computes it. These
tests pin the core, engine-agnostic rules this module ships: ``Col``/``Lit``
leaves, all fifteen ``BinOp`` operators, nested ``WhenThen`` conditionals,
the two module-level registries (``LOWERINGS``, ``NATIVE_REFS``) and how
``lower_polars`` dispatches through them, and the loud ``LoweringError``
refusal for every node this backend cannot lower -- an unregistered
``Call``, a bare ``State`` reference, or an ``EngineNative`` node with no
held runtime expression or an unsupported engine.

Every case here calls ``lower_polars(node)`` with **no lowering context**,
which is the shape-blind contract: every column shape reads ``"unknown"``,
so every shape-dependent rule takes its plain-engine branch. The
shape-aware branches -- ``list_conditional``, ``list_pow``, the
``repeat_by`` broadcast -- are pinned against real frames in
``test_emission.py`` and ``test_reconciliation.py``, where a frame with
real dtypes exists to make them meaningful.

Every plan-equality assertion compares ``Expr.meta.serialize()`` against a
hand-built Polars expression rather than trusting ``__eq__`` or ``repr`` --
the same evidence-first discipline the framework asks of a reconciliation
run, applied here to the lowering layer's own output.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Literal

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    State,
    WhenThen,
)
from gaspatchio.frame.lowering.polars import (
    LOWERINGS,
    NATIVE_REFS,
    LoweringError,
    ensure_rules_loaded,
    lower_polars,
    register_lowering,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# The same closed set of operator names as BinOp.op in
# gaspatchio._semantic.ir, duplicated here (rather than imported) so this
# file can annotate its own parametrized values precisely.
BinOpKind = Literal[
    "add",
    "sub",
    "mul",
    "div",
    "floordiv",
    "mod",
    "pow",
    "lt",
    "le",
    "gt",
    "ge",
    "eq",
    "ne",
    "and",
    "or",
]


# --- The Call registry -------------------------------------------------------


def test_every_registered_lowering_takes_the_node_and_the_frame_context() -> None:
    """A lowering rule's contract is ``(Call, LoweringContext | None) -> pl.Expr``.

    The context argument is not optional decoration: an accessor body is
    routinely shape-dependent (``cumulative_survival`` cumulates inside
    each policy's list for a per-period column and down the column for a
    per-policy one), and shape is a fact about the frame. A rule
    registered with the wrong arity fails here rather than at the first
    model that calls it.

    ``NATIVE_REFS`` is deliberately not asserted empty alongside this. It
    is the ingress side table, and every raw ``pl.Expr`` that becomes an
    operand of a proxy operator records an entry there, so by the time any
    other test in this suite has run a formula it is populated -- which is
    the table working, not a leak of test state.
    """
    ensure_rules_loaded()
    assert LOWERINGS, "no lowering rules registered -- rules/load() did nothing"
    for name, rule in LOWERINGS.items():
        parameters = inspect.signature(rule).parameters
        assert len(parameters) == 2, (
            f"{name!r}'s lowering takes {len(parameters)} argument(s); a "
            "lowering rule takes the Call node and the lowering context"
        )


def test_a_failed_rule_import_does_not_latch_a_half_populated_registry(
    monkeypatch,
) -> None:
    """If loading the rules blows up, the next attempt tries again.

    The flag that says "rules are loaded" is set only after ``load()``
    returns. Setting it first would mean one bad import -- a typo in a
    rule module, a missing dependency in a worker process -- permanently
    latching a half-populated registry, after which every unregistered
    operation would report "no lowering exists" instead of the ImportError
    that actually caused it. That failure is silent and misleading in a
    way the ImportError is not.
    """
    from gaspatchio.frame.lowering import polars as lowering_module
    from gaspatchio.frame.lowering import rules

    monkeypatch.setattr(lowering_module, "_RULES_LOADED", False)
    monkeypatch.setattr(lowering_module, "_RULES_LOADING", False)

    attempts: list[int] = []

    def _explode() -> None:
        attempts.append(1)
        msg = "rule module is broken"
        raise ImportError(msg)

    monkeypatch.setattr(rules, "load", _explode)

    with pytest.raises(ImportError, match="rule module is broken"):
        ensure_rules_loaded()
    assert lowering_module._RULES_LOADED is False  # noqa: SLF001
    assert lowering_module._RULES_LOADING is False  # noqa: SLF001

    # The second attempt reaches load() again rather than reporting success.
    with pytest.raises(ImportError, match="rule module is broken"):
        ensure_rules_loaded()
    assert attempts == [1, 1]


def test_registering_the_same_name_twice_is_refused() -> None:
    """Two rules for one operation would leave one of them unreachable."""
    name = "twice_registered_probe"

    @register_lowering(name)
    def _first(node: Call, ctx: object) -> pl.Expr:  # noqa: ARG001
        return pl.lit(1)

    try:
        with pytest.raises(ValueError, match=name):

            @register_lowering(name)
            def _second(node: Call, ctx: object) -> pl.Expr:  # noqa: ARG001
                return pl.lit(2)

    finally:
        del LOWERINGS[name]


# --- Col, Lit ----------------------------------------------------------------


def test_col_lowers_to_pl_col_matching_hand_built_plan() -> None:
    """Col(name) lowers to pl.col(name)."""
    lowered = lower_polars(Col("policies_in_force"))
    expected = pl.col("policies_in_force")
    assert lowered.meta.serialize() == expected.meta.serialize()


@pytest.mark.parametrize(
    "value",
    [1, 1.0, True, "level_premium"],
    ids=["int", "float", "bool", "str"],
)
def test_lit_preserves_value_and_type_through_lowering(
    *,
    value: float | bool | str,
) -> None:
    """Lit(value) lowers to pl.lit(value) for every allowed value type.

    A whole number is typed ``Int64``, the ``i64`` section 10 names it:
    Polars' own untyped integer literal settles on ``Int32`` where nothing
    beside it sets the type.
    """
    lowered = lower_polars(Lit(value))
    expected = pl.lit(value, dtype=pl.Int64) if type(value) is int else pl.lit(value)
    assert lowered.meta.serialize() == expected.meta.serialize()


def test_lit_int_and_float_lower_to_distinct_plans() -> None:
    """1 and 1.0 compare equal as values but are not the same Polars literal.

    Pins the case a careless implementation could get wrong: coercing every
    numeric Lit to float would make this test fail while every other
    single-value plan-equality test kept passing.
    """
    int_plan = lower_polars(Lit(1)).meta.serialize()
    float_plan = lower_polars(Lit(1.0)).meta.serialize()
    assert int_plan == pl.lit(1, dtype=pl.Int64).meta.serialize()
    assert float_plan == pl.lit(1.0).meta.serialize()
    assert int_plan != float_plan


def test_a_sequence_literal_lowers_to_the_expression_it_always_did() -> None:
    """A band of boundaries reaches Polars as the list literal it is.

    The op-tree learned to hold the values so it could identify them; what
    the engine is asked to compute is unchanged, which is what makes this
    a change to identity alone and not to any model's numbers.
    """
    lowered = lower_polars(Lit((45, 50, 55)))
    expected = pl.lit([45, 50, 55])
    assert lowered.meta.serialize() == expected.meta.serialize()


def test_a_sequence_literal_of_text_lowers_to_its_own_list() -> None:
    """The same for a band of product codes."""
    lowered = lower_polars(Lit(("male", "female")))
    expected = pl.lit(["male", "female"])
    assert lowered.meta.serialize() == expected.meta.serialize()


def test_a_one_member_sequence_does_not_lower_to_the_scalar_it_holds() -> None:
    """``[45]`` is a one-element list to Polars, never the number 45."""
    sequence_plan = lower_polars(Lit((45,))).meta.serialize()
    scalar_plan = lower_polars(Lit(45)).meta.serialize()
    assert sequence_plan == pl.lit([45]).meta.serialize()
    assert sequence_plan != scalar_plan


# --- BinOp ---------------------------------------------------------------


def test_binop_mul_of_col_and_lit_matches_hand_built_plan() -> None:
    """BinOp("mul", Col, Lit) -- the headline case: a rate applied to a count."""
    node = BinOp(op="mul", left=Col("policies_in_force"), right=Lit(0.0025))
    lowered = lower_polars(node)
    expected = pl.col("policies_in_force") * pl.lit(0.0025)
    assert lowered.meta.serialize() == expected.meta.serialize()


def test_binop_nested_arithmetic_matches_hand_built_plan() -> None:
    """Claim amount: sum_assured * (policies_in_force * mortality_rate)."""
    node = BinOp(
        op="mul",
        left=Col("sum_assured"),
        right=BinOp(
            op="mul", left=Col("policies_in_force"), right=Col("mortality_rate")
        ),
    )
    lowered = lower_polars(node)
    expected = pl.col("sum_assured") * (
        pl.col("policies_in_force") * pl.col("mortality_rate")
    )
    assert lowered.meta.serialize() == expected.meta.serialize()


# Every BinOp.op value paired with the Python operator that should produce
# an identical Polars plan when applied directly to the same two Expr.
# Spelled out as lambdas rather than the stdlib operator module: several of
# its functions (truediv, pow, and_, or_) carry imprecise stubs that read as
# partially-unknown types under a strict type checker, which a plain `a / b`
# does not.
_BINOP_CASES: tuple[tuple[BinOpKind, Callable[[pl.Expr, pl.Expr], pl.Expr]], ...] = (
    ("add", lambda left, right: left + right),
    ("sub", lambda left, right: left - right),
    ("mul", lambda left, right: left * right),
    ("div", lambda left, right: left / right),
    ("floordiv", lambda left, right: left // right),
    ("mod", lambda left, right: left % right),
    ("pow", lambda left, right: left**right),
    ("lt", lambda left, right: left < right),
    ("le", lambda left, right: left <= right),
    ("gt", lambda left, right: left > right),
    ("ge", lambda left, right: left >= right),
    ("eq", lambda left, right: left == right),
    ("ne", lambda left, right: left != right),
    ("and", lambda left, right: left & right),
    ("or", lambda left, right: left | right),
)


@pytest.mark.parametrize(
    ("op", "python_operator"),
    _BINOP_CASES,
    ids=[case[0] for case in _BINOP_CASES],
)
def test_binop_lowers_every_operator_to_its_polars_equivalent(
    op: BinOpKind,
    python_operator: Callable[[pl.Expr, pl.Expr], pl.Expr],
) -> None:
    """Each of the fifteen BinOp operators lowers to its Polars equivalent.

    Covers arithmetic (add/sub/mul/div/floordiv/mod/pow), every comparison
    (lt/le/gt/ge/eq/ne), and both logical operators (and/or) in one
    parametrized sweep.
    """
    node = BinOp(op=op, left=Col("policies_in_force"), right=Col("mortality_rate"))
    lowered = lower_polars(node)
    expected = python_operator(pl.col("policies_in_force"), pl.col("mortality_rate"))
    assert lowered.meta.serialize() == expected.meta.serialize()


# --- WhenThen ----------------------------------------------------------------


def test_whenthen_matches_hand_built_plan() -> None:
    """when(policies_in_force > 0).then(death_claims).otherwise(0.0)."""
    node = WhenThen(
        cond=BinOp(op="gt", left=Col("policies_in_force"), right=Lit(0)),
        then=Col("death_claims"),
        otherwise=Lit(0.0),
    )
    lowered = lower_polars(node)
    expected = (
        pl.when(pl.col("policies_in_force") > pl.lit(0, dtype=pl.Int64))
        .then(pl.col("death_claims"))
        .otherwise(pl.lit(0.0))
    )
    assert lowered.meta.serialize() == expected.meta.serialize()


def test_whenthen_nested_in_then_branch_matches_hand_built_plan() -> None:
    """A WhenThen nested inside another WhenThen's then-branch lowers recursively."""
    inner = WhenThen(
        cond=BinOp(op="gt", left=Col("mortality_rate"), right=Lit(0.0)),
        then=Col("mortality_rate"),
        otherwise=Lit(0.0),
    )
    outer = WhenThen(
        cond=BinOp(op="gt", left=Col("policies_in_force"), right=Lit(0)),
        then=inner,
        otherwise=Lit(0.0),
    )
    lowered = lower_polars(outer)
    expected = (
        pl.when(pl.col("policies_in_force") > pl.lit(0, dtype=pl.Int64))
        .then(
            pl.when(pl.col("mortality_rate") > pl.lit(0.0))
            .then(pl.col("mortality_rate"))
            .otherwise(pl.lit(0.0))
        )
        .otherwise(pl.lit(0.0))
    )
    assert lowered.meta.serialize() == expected.meta.serialize()


def test_deep_mixed_tree_matches_hand_built_plan_and_executes_identically() -> None:
    """WhenThen over BinOps over Col/Lit -- checked by plan AND by execution.

    when(policies_in_force > 0).then(policies_in_force * mortality_rate)
    .otherwise(0.0) exercises a comparison BinOp, an arithmetic BinOp, Col,
    Lit, and WhenThen together. Plan equality confirms the two expressions
    were built the same way; running both against a tiny DataFrame and
    comparing results is the sanity check that the plan actually computes
    what it looks like it computes.
    """
    node = WhenThen(
        cond=BinOp(op="gt", left=Col("policies_in_force"), right=Lit(0)),
        then=BinOp(
            op="mul", left=Col("policies_in_force"), right=Col("mortality_rate")
        ),
        otherwise=Lit(0.0),
    )
    lowered = lower_polars(node)
    expected = (
        pl.when(pl.col("policies_in_force") > pl.lit(0, dtype=pl.Int64))
        .then(pl.col("policies_in_force") * pl.col("mortality_rate"))
        .otherwise(pl.lit(0.0))
    )
    assert lowered.meta.serialize() == expected.meta.serialize()

    frame = pl.DataFrame(
        {
            "policies_in_force": [100, 0, 50],
            "mortality_rate": [0.01, 0.02, 0.03],
        }
    )
    lowered_result = frame.select(lowered.alias("death_claims"))
    expected_result = frame.select(expected.alias("death_claims"))
    assert_frame_equal(lowered_result, expected_result)


# --- Call ----------------------------------------------------------------


def test_call_with_unregistered_name_raises_lowering_error_naming_it() -> None:
    """An unregistered Call.name raises LoweringError naming that call."""
    node = Call(name="no_such_actuarial_operation", args=(Col("mortality_rate"),))
    assert "no_such_actuarial_operation" not in LOWERINGS

    with pytest.raises(LoweringError, match="no_such_actuarial_operation") as excinfo:
        lower_polars(node)

    assert excinfo.value.node is node


def test_call_dispatches_to_its_registered_lowering() -> None:
    """A LOWERINGS entry receives the Call node and the context; its result wins."""
    seen: list[object] = []

    def _double(call: Call, ctx: object) -> pl.Expr:
        seen.append(ctx)
        (arg,) = call.args
        return lower_polars(arg) * 2

    node = Call(name="double_mortality_rate", args=(Col("mortality_rate"),))
    LOWERINGS["double_mortality_rate"] = _double  # type: ignore[assignment]
    try:
        lowered = lower_polars(node)
    finally:
        del LOWERINGS["double_mortality_rate"]

    expected = pl.col("mortality_rate") * 2
    assert lowered.meta.serialize() == expected.meta.serialize()
    assert seen == [None], "the shape-blind call should pass a None context"


# --- State ---------------------------------------------------------------


def test_state_reference_has_no_polars_lowering() -> None:
    """A rollforward State reference refuses -- it has no bare Polars meaning."""
    node = State("account_value")

    with pytest.raises(LoweringError, match="account_value") as excinfo:
        lower_polars(node)

    assert excinfo.value.node is node
    assert "rollforward" in excinfo.value.reason


# --- EngineNative ----------------------------------------------------------


def test_engine_native_polars_hit_returns_the_held_expression() -> None:
    """A NATIVE_REFS entry for engine='polars' resolves to its stored pl.Expr."""
    node = EngineNative(
        engine="polars",
        text="pl.col('mortality_rate').cum_prod()",
        deps=("mortality_rate",),
    )
    held_expr = pl.col("mortality_rate").cum_prod()
    NATIVE_REFS[id(node)] = (node, held_expr)
    try:
        lowered = lower_polars(node)
    finally:
        del NATIVE_REFS[id(node)]

    assert lowered.meta.serialize() == held_expr.meta.serialize()


def test_engine_native_polars_miss_raises_lowering_error() -> None:
    """No NATIVE_REFS entry for this node's id: the runtime object is gone."""
    node = EngineNative(
        engine="polars",
        text="pl.col('mortality_rate').cum_prod()",
        deps=("mortality_rate",),
    )
    assert id(node) not in NATIVE_REFS

    with pytest.raises(LoweringError, match="re-supplied") as excinfo:
        lower_polars(node)

    assert excinfo.value.node is node


def test_engine_native_jax_engine_has_no_polars_lowering() -> None:
    """engine='jax' always refuses -- there is no Polars lowering for it."""
    node = EngineNative(
        engine="jax",
        text="jnp.cumprod(mortality_rate)",
        deps=("mortality_rate",),
    )

    with pytest.raises(LoweringError, match="jax") as excinfo:
        lower_polars(node)

    assert excinfo.value.node is node


def test_engine_native_python_engine_has_no_polars_lowering() -> None:
    """engine='python' always refuses -- there is no Polars lowering for it."""
    node = EngineNative(
        engine="python",
        text="math.prod(mortality_rate)",
        deps=("mortality_rate",),
    )

    with pytest.raises(LoweringError, match="python") as excinfo:
        lower_polars(node)

    assert excinfo.value.node is node


# --- LoweringError -----------------------------------------------------------


def test_lowering_error_carries_node_and_reason_as_attributes() -> None:
    """LoweringError exposes the refusing node and the reason programmatically."""
    node = State("account_value")

    with pytest.raises(LoweringError) as excinfo:
        lower_polars(node)

    assert excinfo.value.node is node
    assert isinstance(excinfo.value.reason, str)
    assert excinfo.value.reason in str(excinfo.value)
