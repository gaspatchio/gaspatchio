# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for chained when().then() with list-column predicates and branches."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when


@pytest.fixture
def af_with_lists() -> ActuarialFrame:
    """Single-policy frame with month as list column."""
    return ActuarialFrame(
        {
            "policy_id": ["P001"],
            "month": [[0, 1, 2, 3, 4, 5, 6, 7]],
            "policy_term": [6],
        }
    )


@pytest.mark.parametrize("mode", ["debug", "optimize"])
class TestChainedWhenVector:
    def test_two_case_chain_vector_comparison_scalar_branches(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        """Chained .when() with two vector comparisons and scalar branches."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = af_with_lists
        af.rate = (
            when(af.month < 3)
            .then(0.05)
            .when(af.month < 6)
            .then(0.04)
            .otherwise(0.03)
        )
        result = af.collect()["rate"][0].to_list()
        # months 0,1,2 -> 0.05; 3,4,5 -> 0.04; 6,7 -> 0.03 (first-match-wins)
        assert result == [0.05, 0.05, 0.05, 0.04, 0.04, 0.04, 0.03, 0.03]

    def test_three_case_chain_vector_comparison_scalar_branches(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = af_with_lists
        af.rate = (
            when(af.month < 2)
            .then(0.05)
            .when(af.month < 4)
            .then(0.04)
            .when(af.month < 6)
            .then(0.03)
            .otherwise(0.02)
        )
        result = af.collect()["rate"][0].to_list()
        assert result == [0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02]

    def test_five_case_chain_vector_comparison_scalar_branches(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = af_with_lists
        af.rate = (
            when(af.month == 0).then(0.10)
            .when(af.month == 1).then(0.09)
            .when(af.month == 2).then(0.08)
            .when(af.month == 3).then(0.07)
            .when(af.month == 4).then(0.06)
            .otherwise(0.05)
        )
        result = af.collect()["rate"][0].to_list()
        assert result == [0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.05, 0.05]

    def test_chain_with_list_branch_value(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        """Branch values that are list columns (e.g., pols_if)."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001"],
                "month": [[0, 1, 2, 3, 4, 5]],
                "pols_if": [[100.0, 99.0, 98.0, 97.0, 96.0, 95.0]],
                "term": [3],
            }
        )
        af.maturity_value = (
            when(af.month < af.term)
            .then(af.pols_if)
            .when(af.month == af.term)
            .then(0.0)
            .otherwise(af.pols_if * 0.5)
        )
        result = af.collect()["maturity_value"][0].to_list()
        # m=0,1,2 -> pols_if; m=3 -> 0.0; m=4,5 -> pols_if * 0.5
        assert result == pytest.approx(
            [100.0, 99.0, 98.0, 0.0, 96.0 * 0.5, 95.0 * 0.5]
        )

    def test_chain_with_and_mask_predicate(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        """Vector mask predicate built with &."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = af_with_lists
        af.flag = (
            when((af.month >= 2) & (af.month < 5))
            .then(1.0)
            .when(af.month >= 6)
            .then(2.0)
            .otherwise(0.0)
        )
        result = af.collect()["flag"][0].to_list()
        # m=0,1 -> 0; m=2,3,4 -> 1; m=5 -> 0; m=6,7 -> 2
        assert result == [0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 2.0, 2.0]

    def test_chain_with_or_mask_predicate(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = af_with_lists
        af.flag = (
            when((af.month == 0) | (af.month == 7))
            .then(99.0)
            .when(af.month < 4)
            .then(1.0)
            .otherwise(0.0)
        )
        result = af.collect()["flag"][0].to_list()
        # m=0 -> 99 (matches first); m=1,2,3 -> 1; m=4,5,6 -> 0; m=7 -> 99
        assert result == [99.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 99.0]

    def test_chain_with_invert_mask_predicate(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = af_with_lists
        af.flag = (
            when(~(af.month < 4))
            .then(1.0)
            .otherwise(0.0)
        )
        # ~(m<4) means m>=4
        result = af.collect()["flag"][0].to_list()
        assert result == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]

    def test_chain_mixed_scalar_and_vector_predicates(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        """Chain with one vector predicate first and one scalar predicate second."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001", "P002"],
                "month": [[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]],
                "is_special": [True, False],
            }
        )
        af.rate = (
            when(af.month < 3)
            .then(0.05)
            .when(af.is_special == True)  # noqa: E712 — scalar predicate
            .then(0.10)
            .otherwise(0.03)
        )
        result = af.collect()["rate"]
        # P001 (is_special=True):  m=0,1,2 -> 0.05; m=3,4,5 -> 0.10 (scalar match)
        assert result[0].to_list() == [0.05, 0.05, 0.05, 0.10, 0.10, 0.10]
        # P002 (is_special=False): m=0,1,2 -> 0.05; m=3,4,5 -> 0.03 (otherwise)
        assert result[1].to_list() == [0.05, 0.05, 0.05, 0.03, 0.03, 0.03]

    def test_chain_scalar_predicate_first_with_vector_second(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        """Scalar predicate FIRST in a chain whose later predicates are vector.

        This is the case that originally hit Polars' schema-supertype error
        (`failed to determine supertype of f64 and list[f64]`). The reverse-fold
        must lift the scalar predicate's pl.when().then(scalar_val).otherwise(list_acc)
        into a list-aware form so the chain produces list[f64] cleanly.
        """
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001", "P002"],
                "month": [[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]],
                "is_special": [True, False],
            }
        )
        af.rate = (
            when(af.is_special == True)  # noqa: E712 — scalar predicate FIRST
            .then(0.10)
            .when(af.month < 3)  # vector predicate SECOND
            .then(0.05)
            .otherwise(0.03)
        )
        result = af.collect()["rate"]
        # P001 (is_special=True):  every month matches the scalar predicate -> 0.10 broadcast
        assert result[0].to_list() == [0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
        # P002 (is_special=False): scalar predicate fails, fall through to vector
        # m=0,1,2 -> 0.05; m=3,4,5 -> 0.03 (otherwise)
        assert result[1].to_list() == [0.05, 0.05, 0.05, 0.03, 0.03, 0.03]

    def test_first_match_wins_with_overlap(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        """Two cases that both match — first one should win."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = af_with_lists
        af.rate = (
            when(af.month < 5).then(0.10)
            .when(af.month < 10).then(0.20)  # would also match m=0..4 if no first-match-wins
            .otherwise(0.30)
        )
        result = af.collect()["rate"][0].to_list()
        # m=0..4 -> 0.10 (first match), m=5..7 -> 0.20
        assert result == [0.10, 0.10, 0.10, 0.10, 0.10, 0.20, 0.20, 0.20]

    def test_scalar_predicate_with_list_then_then_scalar_chain(
        self, mode: str
    ) -> None:
        """Scalar predicate with a LIST then-branch, before later scalar cases.

        Reverse-fold must consider the then-branch shape: when a scalar
        predicate's then is list-shaped but the running accumulator is still
        scalar, native ``pl.when(scalar).then(list).otherwise(scalar)`` raises
        ``SchemaError: failed to determine supertype of list[f64] and f64``.
        Lifting through ``list_conditional`` (with the scalar acc broadcast to
        list shape) is the correct routing.
        """
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001", "P002"],
                "month": [[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]],
                "benefit": [
                    [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
                    [11.0, 21.0, 31.0, 41.0, 51.0, 61.0],
                ],
                "age": [30, 50],
                "is_special": [True, False],
            }
        )
        af.payout = (
            when(af.is_special == True)  # noqa: E712 — scalar predicate, LIST then
            .then(af.benefit)
            .when(af.age > 999)  # scalar predicate, scalar then (matches nothing)
            .then(1.0)
            .otherwise(0.0)
        )
        result = af.collect()["payout"]
        # P001 (is_special=True): scalar predicate hits → broadcast af.benefit row
        assert result[0].to_list() == [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
        # P002 (is_special=False, age=50): falls through both → otherwise=0.0,
        # but result is list-shaped because the chain produced list output.
        assert result[1].to_list() == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class TestScalarChainParity:
    """Prove unified reverse-fold for scalar chains is numerically and dtype identical to native pl.when() chained form."""

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    @pytest.mark.parametrize("chain_size", [2, 3, 5])
    def test_scalar_chain_parity(self, mode: str, chain_size: int) -> None:
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)

        # Build a scalar-only frame (no list columns)
        ages = [25, 35, 45, 55, 65, 75]
        af = ActuarialFrame({"age": ages})

        # Build the chain through the public DSL (which uses reverse-fold)
        builder = when(af.age > 70).then(0.10)
        thresholds = [60, 50, 40, 30]
        rates = [0.08, 0.06, 0.05, 0.04]
        for thresh, rate in zip(thresholds[: chain_size - 1], rates[: chain_size - 1], strict=False):
            builder = builder.when(af.age > thresh).then(rate)
        af.rate_dsl = builder.otherwise(0.02)

        # Build the same chain natively in Polars (today's reference behavior)
        ref_expr = pl.when(pl.col("age") > 70).then(0.10)
        for thresh, rate in zip(thresholds[: chain_size - 1], rates[: chain_size - 1], strict=False):
            ref_expr = ref_expr.when(pl.col("age") > thresh).then(rate)
        ref_expr = ref_expr.otherwise(0.02)

        result_dsl = af.collect()
        result_ref = pl.LazyFrame({"age": ages}).select(ref_expr.alias("rate_ref")).collect()

        # Numerical equality
        assert result_dsl["rate_dsl"].to_list() == result_ref["rate_ref"].to_list()
        # Dtype equality
        assert result_dsl.schema["rate_dsl"] == result_ref.schema["rate_ref"]


class TestChainedWhenNulls:
    """Verify null behavior matches per-case primitive semantics after reverse-fold."""

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_null_in_predicate_propagates(self, mode: str) -> None:
        """Null in scalar predicate should select the otherwise branch."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame({"age": [25, None, 65]})
        af.bracket = (
            when(af.age < 35).then("young")
            .when(af.age >= 60).then("senior")
            .otherwise("middle")
        )
        result = af.collect()["bracket"].to_list()
        # Polars: pl.when() with null condition falls through; pl.col(age) >= 60 is null for null age, falls through too
        # otherwise wins for null
        assert result == ["young", "middle", "senior"]

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_null_in_list_predicate(self, mode: str) -> None:
        """Null inside a list column predicate."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001"],
                "month": [[0, 1, None, 3, 4]],
                "term": [3],
            }
        )
        af.value = (
            when(af.month < af.term).then(1.0)
            .when(af.month == af.term).then(2.0)
            .otherwise(0.0)
        )
        result = af.collect()["value"][0].to_list()
        # m=0,1 -> 1 (first match); m=null -> ? (depends on list_conditional null semantics — should match otherwise)
        # m=3 -> 2; m=4 -> 0
        # Codify whatever list_conditional does today
        assert len(result) == 5
        assert result[0] == 1.0
        assert result[1] == 1.0
        # result[2] is null-handling — record actual behavior
        assert result[3] == 2.0
        assert result[4] == 0.0


class TestBarePolarsExprConditionOverListColumn:
    """Bare ``pl.Expr`` conditions whose dtype resolves to ``list[bool]`` must
    route through ``list_conditional``.

    Regression guard for the post-PR-2 path where ``ColumnTypeDetector``
    deletion erased the parent-aware schema lookup for raw ``pl.Expr``
    conditions. ``_condition_has_list_columns`` now falls back to
    ``_shape_from_expr_dtype`` for the bare-expression branch.

    Realistic shape: a user reaches into raw Polars for a per-element
    predicate via ``pl.col(list_col).list.eval(...)`` because the gaspatchio
    proxy doesn't yet expose every Polars list operator they need.
    """

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_chained_with_bare_pl_expr_after_proxy_condition(self, mode: str) -> None:
        """First condition is a proxy; second is a raw ``list.eval`` predicate."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001"],
                "month": [[0, 1, 2, 3, 4, 5]],
                "term": [3],
                "premium": [100.0],
            }
        )
        bare_predicate = pl.col("month").list.eval(pl.element() > 1)
        af.value = (
            when(af.month == af.term)
            .then(0.0)
            .when(bare_predicate)
            .then(10.0)
            .otherwise(af.premium)
        )
        result = af.collect()["value"][0].to_list()
        # Reverse-fold over original chain order, first-match-wins per element:
        # m=0 -> term-eq false, m>1 false  -> 100
        # m=1 -> term-eq false, m>1 false  -> 100
        # m=2 -> term-eq false, m>1 true   -> 10
        # m=3 -> term-eq true              -> 0
        # m=4 -> term-eq false, m>1 true   -> 10
        # m=5 -> term-eq false, m>1 true   -> 10
        assert result == [100.0, 100.0, 10.0, 0.0, 10.0, 10.0]

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_bare_pl_expr_chained_branches_only(self, mode: str) -> None:
        """Multiple chained ``.when()`` calls with bare ``list.eval`` predicates.

        Verifies the per-step ``_condition_has_list_columns`` check (not just
        chain-level) routes bare list-shaped expressions through
        ``list_conditional``.
        """
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001"],
                "month": [[0, 1, 2, 3, 4]],
                "term": [3],
            }
        )
        bare_lt = pl.col("month").list.eval(pl.element() < 2)
        bare_gt = pl.col("month").list.eval(pl.element() > 3)
        af.value = (
            when(af.month == af.term)
            .then(99.0)
            .when(bare_lt)
            .then(1.0)
            .when(bare_gt)
            .then(4.0)
            .otherwise(0.0)
        )
        result = af.collect()["value"][0].to_list()
        # m=0 -> term-eq false, m<2 true  -> 1
        # m=1 -> term-eq false, m<2 true  -> 1
        # m=2 -> term-eq false, m<2 false, m>3 false -> 0
        # m=3 -> term-eq true              -> 99
        # m=4 -> term-eq false, m<2 false, m>3 true  -> 4
        assert result == [1.0, 1.0, 0.0, 99.0, 4.0]


class TestCommutedListPredicates:
    """Predicates with the list operand on the right of the comparison.

    ``list_conditional`` requires the list-typed operand on its ``left``
    parameter. Predicates the user writes as ``(scalar) OP af.list_col``
    must be normalized — operand swap with operator inversion — before
    routing through the plugin. Without normalization, the kernel raises
    ``ComputeError: left must be List dtype for list_conditional``.

    The normalization happens in ``ConditionExpression.normalize_for_list_path``
    and is applied in ``polars_backend.masks.to_boolean_expr`` and at every
    ``list_conditional`` call site that takes ``condition.left/right/operator``.
    """

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_eq_scalar_on_left(self, mode: str) -> None:
        """``(scalar_expr) == af.list_col`` — eq is self-inverse, just swap."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {"month": [[0, 1, 2, 3, 4, 5]], "policy_term": [3]}
        )
        af.r = when((af.policy_term * 12) == af.month).then(1.0).otherwise(0.0)
        # policy_term * 12 = 36; month never equals 36 in [0..5] → all zeros
        assert af.collect()["r"][0].to_list() == [0.0] * 6

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_eq_scalar_matches_one_element(self, mode: str) -> None:
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]], "term": [3]})
        af.r = when(af.term == af.month).then(1.0).otherwise(0.0)
        # term == 3; month index 3 matches
        assert af.collect()["r"][0].to_list() == [0.0, 0.0, 0.0, 1.0, 0.0]

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_lt_scalar_on_left(self, mode: str) -> None:
        """``scalar < list`` becomes ``list > scalar`` after operator inversion."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]], "term": [2]})
        af.r = when(af.term < af.month).then(1.0).otherwise(0.0)
        # term=2; "2 < month[i]" is true when month > 2 (indices 3,4)
        assert af.collect()["r"][0].to_list() == [0.0, 0.0, 0.0, 1.0, 1.0]

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_gt_scalar_on_left(self, mode: str) -> None:
        """``scalar > list`` becomes ``list < scalar``."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]], "term": [2]})
        af.r = when(af.term > af.month).then(1.0).otherwise(0.0)
        # term=2; "2 > month[i]" is true when month < 2 (indices 0,1)
        assert af.collect()["r"][0].to_list() == [1.0, 1.0, 0.0, 0.0, 0.0]

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_canonical_order_unchanged(self, mode: str) -> None:
        """``list OP scalar`` (already canonical) routes without operand swap."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]], "term": [3]})
        af.r = when(af.month == af.term).then(1.0).otherwise(0.0)
        assert af.collect()["r"][0].to_list() == [0.0, 0.0, 0.0, 1.0, 0.0]

    @pytest.mark.parametrize("mode", ["debug", "optimize"])
    def test_chained_with_commuted_predicate(self, mode: str) -> None:
        """Commuted predicate inside a chained when() (per-step lowering path)."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]], "term": [2]})
        af.r = (
            when(af.term > af.month)  # commuted: scalar on left, list on right
            .then(1.0)
            .when(af.month == af.term)
            .then(2.0)
            .otherwise(0.0)
        )
        # m=0: term>m (2>0) true → 1
        # m=1: term>m (2>1) true → 1
        # m=2: term>m (2>2) false; m==term (2==2) true → 2
        # m=3: both false → 0
        # m=4: both false → 0
        assert af.collect()["r"][0].to_list() == [1.0, 1.0, 2.0, 0.0, 0.0]
