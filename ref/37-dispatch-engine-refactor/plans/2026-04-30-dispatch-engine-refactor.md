# Dispatch / Broadcasting Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land GSP-87 (chained vector `when()` correctness) and remove the underlying maintenance smells (scattered shape detection, scattered Polars-specific routing) without committing to a semantic IR or backend-agnostic interface.

**Architecture:** Three independent, sequenced PRs against `gsp-95-dispatch-refactor`:

1. **PR 1** — chained vector `when()` via reverse-fold composition of `list_conditional`. Touches `functions/conditional.py` only.
2. **PR 2** — shape source-of-truth via `shape`/`kind` `@property` on proxies with generation-aware caching. Frame `_df` becomes a property whose setter bumps a generation counter. Replaces `ColumnTypeDetector` and the `_is_boolean_list` ducktype.
3. **PR 3** — extract Polars-specific implementation into a new `polars_backend/` subpackage. `dispatch.py` shrinks to proxy-delegation glue.

**Tech Stack:** Python 3 (`uv` + `maturin`), Polars (`pl.LazyFrame`, `pl.Expr`, plugins via `register_plugin_function`), Rust (Polars plugin kernels), pytest, criterion.

**Spec:** `ref/37-dispatch-engine-refactor/specs/2026-04-30-dispatch-engine-refactor-design.md` — read this first; the plan does not re-derive design decisions.

**Linear:** GSP-87 (the bug we're fixing) · GSP-95 (the architecture work)

---

## File map (all phases combined)

### Files created

- `bindings/python/gaspatchio_core/column/shape.py` (PR 2) — `Shape`/`Kind` types, `_UNSET` sentinel, `resolve_shape()`, `_shape_from_schema()`, `_shape_from_expr_dtype()`, `_kind_from_dtype()`, `_max_shape()`.
- `bindings/python/gaspatchio_core/polars_backend/__init__.py` (PR 3) — package marker; re-exports public surface.
- `bindings/python/gaspatchio_core/polars_backend/plugins.py` (PR 3) — relocated plugin wrappers (`list_pow`, `list_clip`, `list_conditional`, `accumulate`, `fill_series`, `floor`, `round`, `round_to_int`, `rollforward_plugin`).
- `bindings/python/gaspatchio_core/polars_backend/operators.py` (PR 3) — `execute_list_pow`, `execute_list_clip`, `dispatch_list_op`.
- `bindings/python/gaspatchio_core/polars_backend/masks.py` (PR 3) — `boolean_and`, `boolean_or`, `boolean_not`, `to_boolean_expr`.
- `bindings/python/gaspatchio_core/polars_backend/list_eval.py` (PR 3) — `unwrap_for_list_eval`.
- `bindings/python/tests/column/test_resolve_shape.py` (PR 2)
- `bindings/python/tests/column/test_kind_from_dtype.py` (PR 2)
- `bindings/python/tests/column/test_proxy_reuse_across_mutations.py` (PR 2)
- `bindings/python/tests/frame/test_schema_invalidation.py` (PR 2)
- `bindings/python/tests/functions/test_conditional_chained_lists.py` (PR 1)
- `bindings/python/tests/benchmarks/test_chained_when_bench.py` (PR 1) — pytest-benchmark
- `bindings/python/tests/polars_backend/test_operators.py` (PR 3)
- `bindings/python/tests/polars_backend/test_masks.py` (PR 3)
- `bindings/python/tests/polars_backend/test_public_api.py` (PR 3)

### Files modified

- `bindings/python/gaspatchio_core/functions/conditional.py` (PR 1, PR 2) — reverse-fold lowering; later read `condition.kind` instead of `_is_boolean_list`.
- `bindings/python/gaspatchio_core/column/dispatch.py` (PR 2, PR 3) — delete `ColumnTypeDetector` + heuristics; route through `polars_backend`.
- `bindings/python/gaspatchio_core/column/condition_expression.py` (PR 2, PR 3) — pass `kind="boolean_mask"` instead of setting `_is_boolean_list`; call `polars_backend.masks` for arithmetic-as-logic.
- `bindings/python/gaspatchio_core/column/column_proxy.py` (PR 2) — add `shape`/`kind` properties.
- `bindings/python/gaspatchio_core/column/expression_proxy.py` (PR 2) — add `shape`/`kind` properties; remove `_list_broadcast_metadata`.
- `bindings/python/gaspatchio_core/frame/base.py` (PR 2) — `_df` property + setter, `_schema_generation` counter, delete dead string-eager scaffolding.
- `bindings/python/gaspatchio_core/functions/vector.py` (PR 3) — convert to thin re-export shim.
- `bindings/python/tests/functions/test_conditional.py` (PR 1) — remove/convert any chained-vector-when xfails.

### Files deleted (logically — code removed but file may stay)

- `dispatch.py::ColumnTypeDetector` class (lines 433-547)
- `dispatch.py::_expr_references_list_column` (lines 550-558)
- `dispatch.py::_is_list_in_graph` / `_is_list_in_schema` (lines 478-501)
- `dispatch.py::is_expression_list_output` (lines 503-531)
- `dispatch.py::_unwrap_for_list_eval` body (relocated to `polars_backend/list_eval.py`)
- `dispatch.py::_execute_list_pow_plugin` body (relocated)
- `dispatch.py::_execute_list_clip_plugin` body (relocated)
- `expression_proxy.py::_list_broadcast_metadata` (line 47)
- `frame/base.py::_expr_to_str` (lines 407-422)
- `frame/base.py::isinstance(operation.expression, str)` branch in `collect()` (lines 508-512)

---

# Phase 1 — PR 1: Chained vector `when()` via reverse-fold

**Goal:** Land GSP-87. Chained `when().then().otherwise()` on list columns works for the full Cursor matrix in both modes.

**Branch:** `gsp-95-pr1-chained-when` off `gsp-95-dispatch-refactor`.

**Stop criterion:** GSP-87 closed; full matrix passes in `mode="debug"` and `mode="optimize"`; scalar parity test passes; chained-conditional benchmark within 5% of native baseline.

## Task 1.1: Audit existing chained-when tests

**Files:**
- Read: `bindings/python/tests/functions/test_conditional.py` (676 lines)
- Search: tests that mention "chained", "NotImplementedError", or `xfail` in the conditional area.

- [ ] **Step 1: Survey existing chained tests**

```bash
cd bindings/python
rg -n "chained|NotImplementedError|xfail|Multiple chained" tests/functions/test_conditional.py
```

Expected: list of matching lines. Note any tests that currently expect `NotImplementedError` for chained vector `when()`. These will be converted to passing assertions in later tasks.

- [ ] **Step 2: Verify reproduction of GSP-87**

```bash
cd bindings/python
uv run python -c "
from gaspatchio_core import ActuarialFrame, when
af = ActuarialFrame({'policy_id': ['P001'], 'month': [[0, 1, 2, 3, 4, 5, 6, 7]]})
af.rate = (
    when(af.month < 3).then(0.05)
    .when(af.month < 6).then(0.04)
    .otherwise(0.03)
)
print(af.collect())
"
```

Expected: `NotImplementedError: Multiple chained .when() not yet supported with list columns.`

If the error doesn't appear, stop and investigate — the bug may have already been fixed by another PR.

- [ ] **Step 3: Commit (no code change yet, just notes)**

No commit needed. Record findings in your scratchpad for later tasks.

## Task 1.2: Add the first failing test (smallest possible chain)

**Files:**
- Create: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Write the failing test**

Create `bindings/python/tests/functions/test_conditional_chained_lists.py`:

```python
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
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py::TestChainedWhenVector::test_two_case_chain_vector_comparison_scalar_branches -v
```

Expected: FAIL with `NotImplementedError: Multiple chained .when() not yet supported with list columns.`

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): failing test for two-case chained vector when()"
```

## Task 1.3: Implement reverse-fold for the simplest case

**Files:**
- Modify: `bindings/python/gaspatchio_core/functions/conditional.py:373-460` (the `_build_scalar_conditional` method)

- [ ] **Step 1: Read the current implementation**

Open `bindings/python/gaspatchio_core/functions/conditional.py`. Locate `_build_scalar_conditional` (around line 373). Identify:
- The `_any_condition_has_list_columns()` check
- The `len(self._conditions) > 1` guard that raises `NotImplementedError`
- The single-case list path (1a/1b/1c)
- The scalar chained path

- [ ] **Step 2: Add the per-case lowering helper**

Add this method to the `ConditionalProxy` class (place above `_build_scalar_conditional`):

```python
def _lower_one_case(
    self,
    condition: Any,  # noqa: ANN401
    then_val: pl.Expr,
    acc: pl.Expr,
) -> pl.Expr:
    """Lower a single (condition, then, else=acc) tuple to a Polars expression.

    Routes per the design's per-case lowering rules:
    - ConditionExpression involving a list column -> list_conditional kernel
    - ExpressionProxy with _is_boolean_list -> list_conditional with mask
    - Otherwise -> native pl.when().then().otherwise()
    """
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.functions.vector import list_conditional

    if isinstance(condition, ConditionExpression):
        if self._condition_has_list_columns(condition):
            return list_conditional(
                left=condition.left,
                right=condition.right,
                then_val=then_val,
                otherwise_val=acc,
                operator=condition.operator,
            )
        return pl.when(condition._expr).then(then_val).otherwise(acc)  # noqa: SLF001

    if isinstance(condition, ExpressionProxy) and getattr(
        condition, "_is_boolean_list", False
    ):
        return list_conditional(
            left=condition._expr,  # noqa: SLF001
            right=pl.lit(1.0),
            then_val=then_val,
            otherwise_val=acc,
            operator="eq",
        )

    if isinstance(condition, ExpressionProxy):
        return pl.when(condition._expr).then(then_val).otherwise(acc)  # noqa: SLF001

    if isinstance(condition, pl.Expr):
        return pl.when(condition).then(then_val).otherwise(acc)

    msg = f"Unexpected condition type {type(condition)} in chained when() lowering"
    raise TypeError(msg)
```

- [ ] **Step 3: Replace the chain handling in `_build_scalar_conditional`**

Replace the body of `_build_scalar_conditional` (the method that currently raises `NotImplementedError` for multi-case list chains) with:

```python
def _build_scalar_conditional(self, otherwise_expr: pl.Expr) -> pl.Expr:
    """Build conditional expression with per-case lowering and reverse-fold.

    Single-when() (no chain) keeps the existing native paths.
    Chained when() (>=2 cases) uses unified reverse-fold over per-case lowering.
    """
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.functions.vector import list_conditional

    has_list = self._any_condition_has_list_columns()
    is_chained = len(self._conditions) > 1

    if is_chained:
        # Unified reverse-fold for any chain (scalar, list, or mixed)
        acc = otherwise_expr
        for cond, then_val in reversed(
            list(zip(self._conditions, self._values, strict=True))
        ):
            acc = self._lower_one_case(cond, then_val, acc)
        return acc

    # Single-when() path: keep existing single-case behavior
    condition = self._conditions[0]
    then_val = self._values[0]

    if has_list:
        if isinstance(condition, ConditionExpression):
            return list_conditional(
                left=condition.left,
                right=condition.right,
                then_val=then_val,
                otherwise_val=otherwise_expr,
                operator=condition.operator,
            )
        if isinstance(condition, ExpressionProxy) and hasattr(
            condition, "_is_boolean_list"
        ):
            return list_conditional(
                left=condition._expr,  # noqa: SLF001
                right=pl.lit(1.0),
                then_val=then_val,
                otherwise_val=otherwise_expr,
                operator="eq",
            )
        msg = (
            f"Unexpected condition type {type(condition)} with list columns. "
            "Please use a comparison expression (e.g., af.month == af.term)."
        )
        raise TypeError(msg)

    # Scalar single-when()
    if isinstance(condition, (ConditionExpression, ExpressionProxy)):
        cond_expr = condition._expr  # noqa: SLF001
    else:
        cond_expr = condition
    return pl.when(cond_expr).then(then_val).otherwise(otherwise_expr)
```

- [ ] **Step 4: Run the failing test, confirm it passes**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py::TestChainedWhenVector::test_two_case_chain_vector_comparison_scalar_branches -v
```

Expected: PASS in both `mode="debug"` and `mode="optimize"`.

- [ ] **Step 5: Run the full conditional test suite to ensure nothing regressed**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/functions/conditional.py
git commit -m "feat(conditional): reverse-fold lowering for chained when() with list columns

Implements GSP-87 by unifying chained .when().then().otherwise() lowering
through reverse-fold composition of list_conditional and pl.when() primitives.
Scalar-only chains continue to use the native chained pl.when() form via the
single-when path; multi-case chains lower per-case via the new helper.
Single-case behavior unchanged."
```

## Task 1.4: Extend test matrix — chain sizes 3 and 5

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Add test for 3-case chain with vector comparisons and scalar branches**

Append to the `TestChainedWhenVector` class:

```python
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
```

- [ ] **Step 2: Run the new tests, confirm they pass**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py -v
```

Expected: all four tests pass (2 chain sizes × 2 modes).

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): chain sizes 3 and 5 with scalar branches"
```

## Task 1.5: Test list-valued branches

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Add tests for list-valued branches**

Append to `TestChainedWhenVector`:

```python
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
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): chained when() with list-valued branches"
```

## Task 1.6: Test boolean-mask predicates (`&`, `|`, `~`)

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Add tests for mask predicates**

Append to `TestChainedWhenVector`:

```python
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
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py -v
```

Expected: all mask predicate tests pass.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): chained when() with &/|/~ mask predicates"
```

## Task 1.7: Test mixed scalar/vector predicates in one chain

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Add mixed-predicate test**

```python
    def test_chain_mixed_scalar_and_vector_predicates(
        self, af_with_lists: ActuarialFrame, mode: str
    ) -> None:
        """Chain with one scalar predicate and one vector predicate."""
        from gaspatchio_core.util import set_default_mode

        set_default_mode(mode)
        af = ActuarialFrame(
            {
                "policy_id": ["P001"],
                "month": [[0, 1, 2, 3, 4, 5]],
                "is_special": [True],
            }
        )
        af.rate = (
            when(af.is_special == True)  # noqa: E712 — scalar predicate
            .then(0.10)
            .when(af.month < 3)
            .then(0.05)
            .otherwise(0.03)
        )
        # is_special is True for the row, so first case matches every element
        result = af.collect()["rate"][0].to_list()
        assert result == [0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py::TestChainedWhenVector::test_chain_mixed_scalar_and_vector_predicates -v
```

Expected: PASS in both modes.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): mixed scalar+vector predicates in one chain"
```

## Task 1.8: First-match-wins overlap test

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Add overlap test**

```python
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
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py::TestChainedWhenVector::test_first_match_wins_with_overlap -v
```

Expected: PASS in both modes.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): first-match-wins overlap"
```

## Task 1.9: Scalar parity test (BLOCKS PR 1 MERGE)

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Add scalar parity test class**

Append to the test file:

```python
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
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py::TestScalarChainParity -v
```

Expected: 6 tests pass (3 sizes × 2 modes).

If any test fails, do NOT proceed. The failure means the unified reverse-fold path produces semantically different results from today's native chained pl.when() — investigate and either fix or document the divergence in a commit message before continuing.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): scalar-chain parity with native pl.when() chained form"
```

## Task 1.10: Null-handling matrix

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional_chained_lists.py`

- [ ] **Step 1: Add null-handling tests**

```python
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
```

The null-in-list-predicate test asserts behavior we don't yet know exactly — it codifies today's `list_conditional` semantics. If the assertion fails, examine `list_conditional`'s null handling, decide whether the behavior is correct, and update either the test (if behavior is correct) or `list_conditional.rs` (if it's a kernel bug).

- [ ] **Step 2: Run, confirm pass (or document divergence)**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional_chained_lists.py::TestChainedWhenNulls -v
```

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional_chained_lists.py
git commit -m "test(conditional): null-handling matrix for chained when()"
```

## Task 1.11: Convert any existing chained-vector-when xfails

**Files:**
- Modify: `bindings/python/tests/functions/test_conditional.py`

- [ ] **Step 1: Find xfails or NotImplementedError expectations related to chained vector when()**

```bash
cd bindings/python
rg -n "xfail|NotImplementedError|Multiple chained" tests/functions/test_conditional.py
```

Each match:
- If it's an `@pytest.mark.xfail` for chained vector when() → remove the decorator and assert the correct result instead.
- If it's a `pytest.raises(NotImplementedError, match=...)` → remove the `raises` context, replace with the correct positive assertion of the chain's output.
- If it's a docstring or comment about `NotImplementedError` → update to reflect the new working behavior.

- [ ] **Step 2: Run the updated tests**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional.py -v
```

Expected: all tests pass — both new and converted.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/functions/test_conditional.py
git commit -m "test(conditional): convert chained-vector-when xfails to passing assertions"
```

## Task 1.12: Add the chained-conditional pytest-benchmark

**Files:**
- Create: `bindings/python/tests/benchmarks/test_chained_when_bench.py`

- [ ] **Step 1: Write the benchmark file**

Create `bindings/python/tests/benchmarks/test_chained_when_bench.py`:

```python
"""Benchmark for chained scalar when() — unified reverse-fold vs native pl.when().

PR 1 acceptance threshold: unified path must be ≤ 5% slower than native baseline
on each chain size at 10K and 100K rows.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when


@pytest.fixture
def small_frame() -> tuple[ActuarialFrame, pl.LazyFrame]:
    """10K-row scalar frame for benchmark."""
    n = 10_000
    rows = list(range(n))
    af = ActuarialFrame({"x": rows})
    lf = pl.LazyFrame({"x": rows})
    return af, lf


@pytest.fixture
def large_frame() -> tuple[ActuarialFrame, pl.LazyFrame]:
    """100K-row scalar frame for benchmark."""
    n = 100_000
    rows = list(range(n))
    af = ActuarialFrame({"x": rows})
    lf = pl.LazyFrame({"x": rows})
    return af, lf


def _build_dsl_chain(af: ActuarialFrame, size: int) -> ActuarialFrame:
    builder = when(af.x < 0).then(0)
    for i in range(1, size):
        builder = builder.when(af.x < i * 100).then(i)
    af.bracket = builder.otherwise(size)
    return af


def _build_native_chain(lf: pl.LazyFrame, size: int) -> pl.LazyFrame:
    expr = pl.when(pl.col("x") < 0).then(0)
    for i in range(1, size):
        expr = expr.when(pl.col("x") < i * 100).then(i)
    return lf.select(expr.otherwise(size).alias("bracket"))


@pytest.mark.parametrize("size", [2, 3, 5, 10])
class TestChainedWhenBenchmarkSmall:
    def test_dsl_unified(self, benchmark, small_frame, size: int) -> None:
        af, _ = small_frame

        def run() -> pl.DataFrame:
            return _build_dsl_chain(af, size).collect()

        benchmark(run)

    def test_native_baseline(self, benchmark, small_frame, size: int) -> None:
        _, lf = small_frame

        def run() -> pl.DataFrame:
            return _build_native_chain(lf, size).collect()

        benchmark(run)


@pytest.mark.parametrize("size", [2, 3, 5, 10])
class TestChainedWhenBenchmarkLarge:
    def test_dsl_unified(self, benchmark, large_frame, size: int) -> None:
        af, _ = large_frame

        def run() -> pl.DataFrame:
            return _build_dsl_chain(af, size).collect()

        benchmark(run)

    def test_native_baseline(self, benchmark, large_frame, size: int) -> None:
        _, lf = large_frame

        def run() -> pl.DataFrame:
            return _build_native_chain(lf, size).collect()

        benchmark(run)
```

- [ ] **Step 2: Ensure pytest-benchmark is available**

```bash
cd bindings/python
uv add --dev pytest-benchmark
```

- [ ] **Step 3: Run the benchmark**

```bash
cd bindings/python
uv run pytest tests/benchmarks/test_chained_when_bench.py --benchmark-only -v
```

Capture the output. For each `size` and frame size, compare `dsl_unified` mean against `native_baseline` mean. Compute the slowdown as `(dsl_unified.mean / native_baseline.mean - 1) * 100`.

**Acceptance:** every (size, frame size) pair must show ≤ 5% slowdown.

If any pair exceeds 5%, document the regression and either:
- Accept the regression (record in PR commit message)
- Roll back to the split-path strategy (keep native scalar lowering for `len(conditions) > 1 ∧ all_scalar`, unify only at semantic level — see spec PR 1 Risk #2 decision tree)

- [ ] **Step 4: Commit benchmark + results**

```bash
git add bindings/python/tests/benchmarks/test_chained_when_bench.py bindings/python/pyproject.toml
git commit -m "bench(conditional): chained when() unified vs native baseline

Acceptance threshold: unified reverse-fold path ≤ 5% slower than native
pl.when() chained form. Verified at chain sizes 2/3/5/10, frame sizes 10K/100K."
```

## Task 1.13: Run `realistic_vector_lookup` to ensure no regression

**Files:**
- Run: `core/benches/realistic_vector_lookup.rs`

- [ ] **Step 1: Run the authoritative benchmark**

```bash
cd ../gaspatchio-core-gsp-95-dispatch-refactor/core
cargo bench --bench realistic_vector_lookup
```

Expected: results similar to baseline (recorded in `core/benches/perf_results.md`). Ignore noise; flag only changes >5%.

- [ ] **Step 2: Document any change**

If results show >5% movement, append a note to `core/benches/perf_results.md`:

```markdown
## 2026-04-30 — PR 1 (chained when reverse-fold)
- realistic_vector_lookup: <baseline> → <new> (<delta>%)
- Notes: <any context>
```

- [ ] **Step 3: Commit (only if perf notes were updated)**

```bash
git add core/benches/perf_results.md
git commit -m "bench: record PR 1 impact on realistic_vector_lookup"
```

If no change worth recording, skip the commit.

## Task 1.14: Update gaspatchio-docs with chained-vector-when example

**Files:**
- Modify: docs in `gaspatchio-docs/` — find the conditional / `when()` reference page.

- [ ] **Step 1: Locate the conditional documentation**

```bash
cd ..
rg -l "when().then().otherwise|chained .when" gaspatchio-docs/
```

- [ ] **Step 2: Add a chained vector example**

In the located file, add a code example like:

````markdown
### Chained `.when()` on list columns

For policy projections, you can now chain multiple `.when()` clauses with vector conditions:

```python
af.rate = (
    when(af.month < 6).then(0.05)
    .when(af.month < 12).then(0.04)
    .otherwise(0.03)
)
```

First-match-wins semantics apply: month 0–5 receives 0.05, 6–11 receives 0.04, ≥12 receives 0.03.
````

- [ ] **Step 3: Commit (in gaspatchio-docs if it's a separate repo)**

If `gaspatchio-docs` is a sibling repo, commit the change there separately. If it's a subdirectory of this repo, commit alongside PR 1.

```bash
git add gaspatchio-docs/...
git commit -m "docs: chained .when() example on list columns"
```

## Task 1.15: Open PR for Phase 1

**Files:**
- Branch: `gsp-95-pr1-chained-when` → target `develop`

- [ ] **Step 1: Push the branch**

```bash
git push -u origin gsp-95-pr1-chained-when
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat: chained .when() on list columns (GSP-87)" --body "$(cat <<'EOF'
## Summary

Implements GSP-87 by unifying chained `.when().then().otherwise()` lowering through reverse-fold composition of `list_conditional` and `pl.when()` primitives. Resolves the `NotImplementedError: Multiple chained .when() not yet supported with list columns.` failure for any chain size.

Single-when() (no chain) keeps existing native paths. Chained when() (≥2 cases) uses unified reverse-fold over per-case lowering. Scalar-only chains preserve numerical and dtype identity with the native `pl.when()` chained form (proven by parity test).

## Test plan

- [x] Full Cursor matrix: chain sizes 2/3/5; scalar/vector predicates; scalar/list/mixed branches; `&`/`|`/`~` mask predicates; mixed scalar+vector predicates in one chain
- [x] First-match-wins overlap test
- [x] Scalar-chain parity test against native `pl.when()` chained form (sizes 2/3/5)
- [x] Null-handling matrix
- [x] All tests run in both `mode="debug"` and `mode="optimize"`
- [x] Chained-conditional benchmark within 5% of native baseline (sizes 2/3/5/10 at 10K and 100K rows)
- [x] `realistic_vector_lookup` not regressed
- [x] Existing chained-vector-when xfails converted to passing assertions
- [x] Docs updated with chained-vector-when example

Closes GSP-87.
EOF
)"
```

- [ ] **Step 3: Wait for review and merge**

After merge, the branch `gsp-95-dispatch-refactor` rebases on the merged `develop` to pick up PR 1.

---

# Phase 2 — PR 2: Shape source-of-truth

**Goal:** Replace `ColumnTypeDetector` and the `_is_boolean_list` ducktype with typed `shape`/`kind` properties on proxies + `ConditionExpression`. Schema cache is mechanically enforced via `_df` property setter and a generation counter that invalidates proxy caches on mutation. Predicate-producing methods (including autopatched ones) are correctly classified via dtype-driven kind fallback.

**Branch:** `gsp-95-pr2-shape-sot` off `gsp-95-dispatch-refactor` (rebased on PR 1 merge).

**Stop criterion:** `ColumnTypeDetector` and the regex heuristic are deleted; mode parity smoke test passes; benchmark not regressed; PR 1 tests still pass.

## Task 2.1: Create `column/shape.py` skeleton with types and sentinel

**Files:**
- Create: `bindings/python/gaspatchio_core/column/shape.py`

- [ ] **Step 1: Write the skeleton**

Create `bindings/python/gaspatchio_core/column/shape.py`:

```python
"""Single source of truth for shape and kind metadata on proxy objects.

This module defines:
- `Shape` and `Kind` typed literals
- `_UNSET` sentinel distinguishing "not yet computed" from "computed and got Unknown"
- `resolve_shape()`: the one resolver that all callers route through
- `_max_shape()`: combiner for binary operations
- `_kind_from_dtype()`: dtype-driven fallback for kind classification

This is the only place shape and kind inference logic lives. All other code
reads `shape` and `kind` as properties on proxies, never re-derives them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Union

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame


Shape = Literal["scalar", "list", "unknown"]
Kind = Literal["value", "comparison", "boolean_mask", "unknown"]


_UNSET = object()  # module-level sentinel
```

- [ ] **Step 2: Run a smoke test that the module imports**

```bash
cd bindings/python
uv run python -c "from gaspatchio_core.column import shape; print(shape.Shape, shape.Kind, shape._UNSET)"
```

Expected: prints the literal type values and the sentinel object.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/gaspatchio_core/column/shape.py
git commit -m "feat(column): scaffold column/shape.py with Shape/Kind types and sentinel"
```

## Task 2.2: Write failing tests for `_max_shape`

**Files:**
- Create: `bindings/python/tests/column/test_resolve_shape.py`

- [ ] **Step 1: Write the test file (initial)**

Create `bindings/python/tests/column/__init__.py` if it doesn't exist (empty file).

Create `bindings/python/tests/column/test_resolve_shape.py`:

```python
"""Tests for column/shape.py — _max_shape, resolve_shape, _kind_from_dtype."""

from __future__ import annotations

import pytest


class TestMaxShape:
    def test_two_scalars_is_scalar(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("scalar", "scalar") == "scalar"

    def test_scalar_and_list_is_list(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("scalar", "list") == "list"
        assert _max_shape("list", "scalar") == "list"

    def test_two_lists_is_list(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("list", "list") == "list"

    def test_unknown_propagates(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("unknown", "scalar") == "unknown"
        assert _max_shape("scalar", "unknown") == "unknown"
        assert _max_shape("unknown", "list") == "unknown"
        assert _max_shape("list", "unknown") == "unknown"
        assert _max_shape("unknown", "unknown") == "unknown"
```

- [ ] **Step 2: Run, confirm fail (function not defined)**

```bash
cd bindings/python
uv run pytest tests/column/test_resolve_shape.py::TestMaxShape -v
```

Expected: FAIL with `ImportError: cannot import name '_max_shape'` or similar.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/column/__init__.py bindings/python/tests/column/test_resolve_shape.py
git commit -m "test(column): failing tests for _max_shape"
```

## Task 2.3: Implement `_max_shape`

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/shape.py`

- [ ] **Step 1: Add `_max_shape` to shape.py**

Append to `bindings/python/gaspatchio_core/column/shape.py`:

```python
def _max_shape(a: Shape, b: Shape) -> Shape:
    """Combine two shapes per binary-op semantics.

    Combining list and scalar produces list (broadcast).
    Any unknown operand produces unknown (forces explicit handling).
    """
    if a == "unknown" or b == "unknown":
        return "unknown"
    if a == "list" or b == "list":
        return "list"
    return "scalar"
```

- [ ] **Step 2: Run the failing tests, confirm they pass**

```bash
cd bindings/python
uv run pytest tests/column/test_resolve_shape.py::TestMaxShape -v
```

Expected: all 4 tests pass.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/gaspatchio_core/column/shape.py
git commit -m "feat(column): _max_shape combiner"
```

## Task 2.4: Tests + implementation for `_shape_from_schema` and literal scalar shapes

**Files:**
- Modify: `bindings/python/tests/column/test_resolve_shape.py`
- Modify: `bindings/python/gaspatchio_core/column/shape.py`

- [ ] **Step 1: Write failing tests for `resolve_shape` on simple inputs**

Append to `bindings/python/tests/column/test_resolve_shape.py`:

```python
class TestResolveShapeBasics:
    def test_scalar_literal_int(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape(42, parent=None) == "scalar"

    def test_scalar_literal_float(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape(3.14, parent=None) == "scalar"

    def test_scalar_literal_str(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape("hello", parent=None) == "unknown"
        # Strings are AMBIGUOUS — could be a column name or a literal. resolve_shape
        # treats them as scalar literals only when called via known-literal contexts;
        # for raw resolve_shape() with a string, return unknown until a parent
        # context disambiguates. Callers that know the string is a column name use
        # _shape_from_schema directly.

    def test_scalar_literal_bool(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape(True, parent=None) == "scalar"
        assert resolve_shape(False, parent=None) == "scalar"

    def test_unknown_for_arbitrary_object(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        class Foo:
            pass

        assert resolve_shape(Foo(), parent=None) == "unknown"


class TestShapeFromSchema:
    def test_scalar_column(self) -> None:
        import polars as pl

        from gaspatchio_core.column.shape import _shape_from_schema

        # Mock parent with a cached schema
        class FakeParent:
            _schema = pl.Schema({"age": pl.Int64})

        assert _shape_from_schema(FakeParent(), "age") == "scalar"

    def test_list_column(self) -> None:
        import polars as pl

        from gaspatchio_core.column.shape import _shape_from_schema

        class FakeParent:
            _schema = pl.Schema({"month": pl.List(pl.Int64)})

        assert _shape_from_schema(FakeParent(), "month") == "list"

    def test_missing_column_returns_unknown(self) -> None:
        import polars as pl

        from gaspatchio_core.column.shape import _shape_from_schema

        class FakeParent:
            _schema = pl.Schema({"age": pl.Int64})

        assert _shape_from_schema(FakeParent(), "nonexistent") == "unknown"

    def test_no_parent_returns_unknown(self) -> None:
        from gaspatchio_core.column.shape import _shape_from_schema

        assert _shape_from_schema(None, "any") == "unknown"
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd bindings/python
uv run pytest tests/column/test_resolve_shape.py::TestResolveShapeBasics tests/column/test_resolve_shape.py::TestShapeFromSchema -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `_shape_from_schema` and `resolve_shape` (basics only)**

Append to `bindings/python/gaspatchio_core/column/shape.py`:

```python
def _shape_from_schema(parent: ActuarialFrame | None, column_name: str) -> Shape:
    """Read shape from the parent frame's cached schema."""
    if parent is None:
        return "unknown"
    schema = getattr(parent, "_schema", None)
    if schema is None:
        return "unknown"
    dtype = schema.get(column_name)
    if dtype is None:
        return "unknown"
    if isinstance(dtype, pl.List):
        return "list"
    return "scalar"


def resolve_shape(value: object, parent: ActuarialFrame | None) -> Shape:
    """The single source of shape truth. All callers route through here.

    Note: a bare string is treated as `unknown` — it's ambiguous between
    "literal scalar" and "column name". Callers that know which use the
    appropriate helper directly (`_shape_from_schema` for column names).
    """
    # Defer proxy imports to avoid circular imports
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(value, (ColumnProxy, ExpressionProxy, ConditionExpression)):
        return value.shape
    if isinstance(value, pl.Expr):
        return _shape_from_expr_dtype(parent, value)
    if isinstance(value, bool):
        return "scalar"
    if isinstance(value, (int, float)):
        return "scalar"
    if isinstance(value, str):
        # Ambiguous — could be column name or literal. Caller must disambiguate.
        return "unknown"
    return "unknown"


def _shape_from_expr_dtype(parent: ActuarialFrame | None, expr: pl.Expr) -> Shape:
    """Fall back: probe the wrapped expression's output dtype via parent frame."""
    if parent is None or getattr(parent, "_df", None) is None:
        return "unknown"
    try:
        schema = parent._df.select(expr.alias("_t")).collect_schema()  # noqa: SLF001
        dtype = schema.get("_t")
    except Exception:  # noqa: BLE001
        return "unknown"
    if dtype is None:
        return "unknown"
    if isinstance(dtype, pl.List):
        return "list"
    return "scalar"
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/column/test_resolve_shape.py::TestResolveShapeBasics tests/column/test_resolve_shape.py::TestShapeFromSchema -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/column/shape.py bindings/python/tests/column/test_resolve_shape.py
git commit -m "feat(column): resolve_shape, _shape_from_schema, _shape_from_expr_dtype"
```

## Task 2.5: Tests + implementation for `_kind_from_dtype`

**Files:**
- Create: `bindings/python/tests/column/test_kind_from_dtype.py`
- Modify: `bindings/python/gaspatchio_core/column/shape.py`

- [ ] **Step 1: Write failing tests**

Create `bindings/python/tests/column/test_kind_from_dtype.py`:

```python
"""Tests for _kind_from_dtype — dtype-driven kind classification."""

from __future__ import annotations

import polars as pl
import pytest


class TestKindFromDtype:
    def test_boolean_scalar_is_boolean_mask(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        class FakeParent:
            _df = pl.LazyFrame({"x": [1, 2, 3]})

        # is_null produces Boolean
        assert _kind_from_dtype(pl.col("x").is_null(), FakeParent()) == "boolean_mask"

    def test_boolean_list_is_boolean_mask(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        class FakeParent:
            _df = pl.LazyFrame({"m": [[1, 2, 3]]})

        # list.eval(is_null) produces List<Boolean>
        expr = pl.col("m").list.eval(pl.element().is_null())
        assert _kind_from_dtype(expr, FakeParent()) == "boolean_mask"

    def test_numeric_is_value(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        class FakeParent:
            _df = pl.LazyFrame({"x": [1.0, 2.0, 3.0]})

        assert _kind_from_dtype(pl.col("x") + 1.0, FakeParent()) == "value"

    def test_no_parent_returns_value(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        # Without a parent, can't probe dtype; fall back to value
        assert _kind_from_dtype(pl.col("x"), None) == "value"

    def test_probe_failure_returns_value(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        # Reference a column that doesn't exist
        class FakeParent:
            _df = pl.LazyFrame({"x": [1, 2, 3]})

        # collect_schema on pl.col("does_not_exist") raises
        result = _kind_from_dtype(pl.col("does_not_exist"), FakeParent())
        # Either probe fails -> "value", or schema is permissive -> "value"
        assert result == "value"
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd bindings/python
uv run pytest tests/column/test_kind_from_dtype.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `_kind_from_dtype`**

Append to `bindings/python/gaspatchio_core/column/shape.py`:

```python
def _kind_from_dtype(expr: pl.Expr, parent: ActuarialFrame | None) -> Kind:
    """Infer kind from the wrapped expression's output dtype.

    Boolean dtype (or List<Boolean>) -> boolean_mask.
    Anything else -> value.

    Used as the fallback when an ExpressionProxy is constructed without an
    explicit kind (i.e. from autopatched dispatch or `_wrap` calls). Catches
    predicate-producing methods (is_null, is_in, is_unique, etc.) including
    those reflectively added by _autopatch.
    """
    if parent is None or getattr(parent, "_df", None) is None:
        return "value"
    try:
        schema = parent._df.select(expr.alias("_t")).collect_schema()  # noqa: SLF001
        dtype = schema.get("_t")
    except Exception:  # noqa: BLE001
        return "value"
    if dtype == pl.Boolean:
        return "boolean_mask"
    if isinstance(dtype, pl.List) and dtype.inner == pl.Boolean:
        return "boolean_mask"
    return "value"
```

- [ ] **Step 4: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/column/test_kind_from_dtype.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/column/shape.py bindings/python/tests/column/test_kind_from_dtype.py
git commit -m "feat(column): _kind_from_dtype dtype-driven kind classification"
```

## Task 2.6: Add `_schema_generation` to `ActuarialFrame.__init__`

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/base.py`

- [ ] **Step 1: Locate the `__init__` of `ActuarialFrame`**

```bash
cd bindings/python
rg -n "def __init__" gaspatchio_core/frame/base.py | head
```

Open the file and find the `__init__` method.

- [ ] **Step 2: Add `_schema_generation`**

In `ActuarialFrame.__init__`, near where `_schema` is initialized, add:

```python
self._schema_generation: int = 0
```

Place it adjacent to existing `self._schema = ...` initialization. If the line `self._schema = ...` doesn't exist directly (it's set during init of `_df`), still add `self._schema_generation = 0` early in `__init__`.

- [ ] **Step 3: Smoke test**

```bash
cd bindings/python
uv run python -c "
from gaspatchio_core import ActuarialFrame
af = ActuarialFrame({'x': [1,2,3]})
print(af._schema_generation)
"
```

Expected: prints `0`.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/base.py
git commit -m "feat(frame): add _schema_generation counter to ActuarialFrame.__init__"
```

## Task 2.7: Convert `_df` to a property with setter

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/base.py`

- [ ] **Step 1: Find every `self._df` assignment site**

```bash
cd bindings/python
rg -n "self._df\s*=" gaspatchio_core/frame/base.py
```

Note the line numbers. These all need to keep working after the property conversion.

- [ ] **Step 2: Rename the underlying attribute**

In `ActuarialFrame.__init__`, where `self._df = ...` first appears, change to `self.__df = ...` (double underscore — Python name-mangles to `_ActuarialFrame__df`).

If `_df` is documented as a public attribute in the class docstring, update accordingly.

- [ ] **Step 3: Add the property and setter**

In the `ActuarialFrame` class body, near the top of methods (after `__init__`), add:

```python
@property
def _df(self) -> pl.LazyFrame:
    """The underlying Polars LazyFrame."""
    return self.__df

@_df.setter
def _df(self, new_df: pl.LazyFrame) -> None:
    """Replace _df, refresh the cached schema, bump the generation counter.

    All mutation paths must go through this setter — the lint rule in CI
    bans direct writes to __df outside this method.
    """
    self.__df = new_df
    self._schema = new_df.collect_schema()
    self._schema_generation += 1
```

- [ ] **Step 4: Smoke test**

```bash
cd bindings/python
uv run python -c "
from gaspatchio_core import ActuarialFrame
af = ActuarialFrame({'x': [1,2,3]})
gen0 = af._schema_generation
af['y'] = af['x'] * 2
gen1 = af._schema_generation
print(f'gen0={gen0}, gen1={gen1}')
assert gen1 == gen0 + 1, 'generation should increment'
print('OK')
"
```

Expected: `gen0=0, gen1=1` then `OK`.

- [ ] **Step 5: Run the full test suite to verify no regression from the refactor**

```bash
cd bindings/python
uv run pytest tests/ -x -q
```

Expected: all tests pass. The property conversion should be transparent.

- [ ] **Step 6: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/base.py
git commit -m "feat(frame): convert _df to property, refresh _schema and bump generation on set

All existing self._df = ... assignments are intercepted by the property setter
which atomically refreshes the cached schema and increments _schema_generation."
```

## Task 2.8: Schema-invalidation tests

**Files:**
- Create: `bindings/python/tests/frame/test_schema_invalidation.py`

- [ ] **Step 1: Write the test**

Create `bindings/python/tests/frame/__init__.py` if missing.

Create `bindings/python/tests/frame/test_schema_invalidation.py`:

```python
"""Verify _schema and _schema_generation are kept in sync with _df after every mutation."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


@pytest.fixture
def af() -> ActuarialFrame:
    return ActuarialFrame({"x": [1, 2, 3], "y": [10, 20, 30]})


class TestSchemaInvalidation:
    def test_setitem_refreshes_schema_and_bumps_generation(
        self, af: ActuarialFrame
    ) -> None:
        gen0 = af._schema_generation
        af["z"] = af["x"] + af["y"]
        assert af._schema_generation == gen0 + 1
        assert af._schema == af._df.collect_schema()
        assert "z" in af._schema

    def test_setattr_refreshes_schema_and_bumps_generation(
        self, af: ActuarialFrame
    ) -> None:
        gen0 = af._schema_generation
        af.z = af["x"] * 2
        assert af._schema_generation == gen0 + 1
        assert af._schema == af._df.collect_schema()
        assert "z" in af._schema

    @pytest.mark.parametrize("method", ["with_columns", "select", "drop", "rename"])
    def test_each_mutation_method(self, af: ActuarialFrame, method: str) -> None:
        """Every method that ends up reassigning self._df must trigger the setter."""
        gen0 = af._schema_generation

        if method == "with_columns":
            af._df = af._df.with_columns(pl.col("x").alias("z"))
        elif method == "select":
            af._df = af._df.select("x")
        elif method == "drop":
            af._df = af._df.drop("y")
        elif method == "rename":
            af._df = af._df.rename({"x": "x_renamed"})
        else:
            pytest.fail(f"unhandled method {method}")

        assert af._schema_generation == gen0 + 1
        assert af._schema == af._df.collect_schema()
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/frame/test_schema_invalidation.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/frame/__init__.py bindings/python/tests/frame/test_schema_invalidation.py
git commit -m "test(frame): _schema and _schema_generation invariants across mutation methods"
```

## Task 2.9: Add `shape` property to `ColumnProxy`

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/column_proxy.py`

- [ ] **Step 1: Add the property**

In `ColumnProxy.__init__`, after existing initialization, add:

```python
self._shape_cached: tuple[int, str] | object = _UNSET
```

Add the import at the top of `column_proxy.py`:

```python
from gaspatchio_core.column.shape import _UNSET, resolve_shape
```

In the `ColumnProxy` class body, add the property:

```python
@property
def shape(self) -> str:
    """Resolved shape of this column reference (`scalar`, `list`, or `unknown`)."""
    gen = getattr(self._parent, "_schema_generation", 0)
    if self._shape_cached is _UNSET or self._shape_cached[0] != gen:  # type: ignore[index]
        from gaspatchio_core.column.shape import _shape_from_schema

        self._shape_cached = (gen, _shape_from_schema(self._parent, self.name))
    return self._shape_cached[1]  # type: ignore[index]

kind: ClassVar[str] = "value"
```

Add `from typing import ClassVar` if not already imported.

- [ ] **Step 2: Smoke test**

```bash
cd bindings/python
uv run python -c "
from gaspatchio_core import ActuarialFrame
af = ActuarialFrame({'x': [1,2,3], 'm': [[10,20,30]]})
print('x:', af['x'].shape, af['x'].kind)
print('m:', af['m'].shape, af['m'].kind)
"
```

Expected:
```
x: scalar value
m: list value
```

- [ ] **Step 3: Run column tests to ensure no regression**

```bash
cd bindings/python
uv run pytest tests/column/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/column/column_proxy.py
git commit -m "feat(column): shape and kind properties on ColumnProxy with generation-aware caching"
```

## Task 2.10: Add `shape` and `kind` properties to `ExpressionProxy`

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/expression_proxy.py`

- [ ] **Step 1: Update `__init__` to accept optional `kind`**

Locate `ExpressionProxy.__init__`. Change its signature from:

```python
def __init__(self, expr: pl.Expr, parent: ActuarialFrame | None):
```

to:

```python
def __init__(
    self,
    expr: pl.Expr,
    parent: ActuarialFrame | None,
    *,
    kind: str | None = None,
):
```

In the body, after existing assignments:

```python
self._kind_explicit: str | None = kind
self._shape_cached: tuple[int, str] | object = _UNSET
self._kind_cached: tuple[int, str] | object = _UNSET
```

Remove the existing line `self._list_broadcast_metadata: dict[str, Any] | None = None` — this attribute is dead.

Add imports at the top:

```python
from gaspatchio_core.column.shape import _UNSET, _kind_from_dtype, _shape_from_expr_dtype
```

- [ ] **Step 2: Add `shape` and `kind` properties**

In the `ExpressionProxy` class body, add:

```python
@property
def shape(self) -> str:
    """Resolved shape of this expression."""
    gen = getattr(self._parent, "_schema_generation", 0) if self._parent else 0
    if self._shape_cached is _UNSET or self._shape_cached[0] != gen:  # type: ignore[index]
        self._shape_cached = (gen, _shape_from_expr_dtype(self._parent, self._expr))
    return self._shape_cached[1]  # type: ignore[index]

@property
def kind(self) -> str:
    """Resolved kind: explicit override > dtype-driven fallback > value."""
    if self._kind_explicit is not None:
        return self._kind_explicit
    gen = getattr(self._parent, "_schema_generation", 0) if self._parent else 0
    if self._kind_cached is _UNSET or self._kind_cached[0] != gen:  # type: ignore[index]
        self._kind_cached = (gen, _kind_from_dtype(self._expr, self._parent))
    return self._kind_cached[1]  # type: ignore[index]
```

- [ ] **Step 3: Smoke test**

```bash
cd bindings/python
uv run python -c "
from gaspatchio_core import ActuarialFrame
af = ActuarialFrame({'x': [1,2,3], 'm': [[10,20,30]]})
e1 = af['x'] + af['x']
e2 = af['x'].is_null()
print('e1:', e1.shape, e1.kind)
print('e2:', e2.shape, e2.kind)
"
```

Expected:
```
e1: scalar value
e2: scalar boolean_mask
```

- [ ] **Step 4: Run column tests**

```bash
cd bindings/python
uv run pytest tests/column/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/column/expression_proxy.py
git commit -m "feat(column): shape and kind properties on ExpressionProxy

shape is generation-aware lazy. kind has explicit-override > dtype-fallback > value.
The dead _list_broadcast_metadata channel is removed."
```

## Task 2.11: Add `shape` to `ConditionExpression`

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/condition_expression.py`

- [ ] **Step 1: Update `__init__`**

In `ConditionExpression.__init__`, add at the end:

```python
self._shape_cached: tuple[int, str] | object = _UNSET
```

Add imports at the top:

```python
from typing import ClassVar
from gaspatchio_core.column.shape import _UNSET, _max_shape, resolve_shape
```

- [ ] **Step 2: Add `shape` property and `kind` class attribute**

In the `ConditionExpression` class body:

```python
@property
def shape(self) -> str:
    """Resolved shape of this comparison — the max of operand shapes."""
    gen = getattr(self._parent, "_schema_generation", 0) if self._parent else 0
    if self._shape_cached is _UNSET or self._shape_cached[0] != gen:  # type: ignore[index]
        self._shape_cached = (gen, _max_shape(
            resolve_shape(self.left, self._parent),
            resolve_shape(self.right, self._parent),
        ))
    return self._shape_cached[1]  # type: ignore[index]

kind: ClassVar[str] = "comparison"
```

- [ ] **Step 3: Smoke test**

```bash
cd bindings/python
uv run python -c "
from gaspatchio_core import ActuarialFrame
af = ActuarialFrame({'x': [1,2,3], 'm': [[10,20,30]]})
c1 = af['x'] == 2  # scalar comparison
c2 = af['m'] == 20  # vector comparison
print('c1:', c1.shape, c1.kind)
print('c2:', c2.shape, c2.kind)
"
```

Expected:
```
c1: scalar comparison
c2: list comparison
```

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/column/condition_expression.py
git commit -m "feat(column): shape property and kind=comparison on ConditionExpression"
```

## Task 2.12: Replace `_is_boolean_list` ducktype with `kind="boolean_mask"` in `condition_expression.py`

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/condition_expression.py`

- [ ] **Step 1: Find every `_is_boolean_list = True` assignment**

```bash
cd bindings/python
rg -n "_is_boolean_list" gaspatchio_core/column/condition_expression.py
```

- [ ] **Step 2: Replace each assignment with kind kwarg in the constructor**

For each occurrence (in `__and__`, `__rand__`, `__or__`, `__ror__`, `__invert__`), change patterns like:

```python
result = ExpressionProxy(combined, self._parent)
result._is_boolean_list = True  # type: ignore[attr-defined]
return result
```

to:

```python
return ExpressionProxy(combined, self._parent, kind="boolean_mask")
```

Apply to all five operator overloads. Remove all `_is_boolean_list` assignments and `# type: ignore[attr-defined]` comments associated with them.

- [ ] **Step 3: Smoke test (chained mask predicates work)**

```bash
cd bindings/python
uv run python -c "
from gaspatchio_core import ActuarialFrame, when
af = ActuarialFrame({'policy_id': ['P001'], 'month': [[0,1,2,3,4,5]]})
af.flag = (
    when((af.month >= 2) & (af.month < 4))
    .then(1.0)
    .otherwise(0.0)
)
print(af.collect()['flag'][0].to_list())
"
```

Expected: `[0.0, 0.0, 1.0, 1.0, 0.0, 0.0]`.

- [ ] **Step 4: Run conditional tests**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional.py tests/functions/test_conditional_chained_lists.py -v
```

Expected: all pass — including the PR 1 chained-when tests.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/column/condition_expression.py
git commit -m "refactor(column): replace _is_boolean_list ducktype with kind=boolean_mask"
```

## Task 2.13: Update `conditional.py` to read `condition.kind == "boolean_mask"`

**Files:**
- Modify: `bindings/python/gaspatchio_core/functions/conditional.py`

- [ ] **Step 1: Find every `_is_boolean_list` read**

```bash
cd bindings/python
rg -n "_is_boolean_list" gaspatchio_core/functions/conditional.py
```

- [ ] **Step 2: Replace reads with `kind` checks**

In `_lower_one_case` and `_build_scalar_conditional`, replace patterns like:

```python
if isinstance(condition, ExpressionProxy) and getattr(
    condition, "_is_boolean_list", False
):
```

with:

```python
if isinstance(condition, ExpressionProxy) and condition.kind == "boolean_mask":
```

Also update `when()` (function at module level) similarly:

```python
# Before:
if isinstance(condition, ExpressionProxy) and getattr(
    condition, "_is_boolean_list", False
):
    return ConditionalProxy(condition, parent)

# After:
if isinstance(condition, ExpressionProxy) and condition.kind == "boolean_mask":
    return ConditionalProxy(condition, parent)
```

- [ ] **Step 3: Run conditional test suite**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional.py tests/functions/test_conditional_chained_lists.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/functions/conditional.py
git commit -m "refactor(conditional): read condition.kind instead of _is_boolean_list ducktype"
```

## Task 2.14: Replace `_any_condition_has_list_columns` with `condition.shape == "list"`

**Files:**
- Modify: `bindings/python/gaspatchio_core/functions/conditional.py`

- [ ] **Step 1: Find the helper**

Locate `_any_condition_has_list_columns` and `_condition_has_list_columns` in `conditional.py`.

- [ ] **Step 2: Simplify**

Replace the body of both helpers. Replace `_condition_has_list_columns`:

```python
def _condition_has_list_columns(self, condition: Any) -> bool:  # noqa: ANN401
    """Check whether a condition involves a list-shaped operand.

    Reads the resolved shape from the condition (or its operands) directly,
    via the proxy's `shape` property. No more inspecting expr.meta.root_names()
    or calling ColumnTypeDetector.
    """
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(condition, (ConditionExpression, ExpressionProxy)):
        return condition.shape == "list"
    return False  # bare pl.Expr — not list-shaped without proxy context
```

The `_any_condition_has_list_columns` body stays the same (it loops `_condition_has_list_columns` over `self._conditions`).

- [ ] **Step 3: Run conditional tests**

```bash
cd bindings/python
uv run pytest tests/functions/test_conditional.py tests/functions/test_conditional_chained_lists.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/functions/conditional.py
git commit -m "refactor(conditional): replace ColumnTypeDetector calls with proxy.shape reads"
```

## Task 2.15: Proxy reuse across mutations test

**Files:**
- Create: `bindings/python/tests/column/test_proxy_reuse_across_mutations.py`

- [ ] **Step 1: Write the test**

```python
"""Verify shape/kind cached on a retained proxy re-resolves after frame mutations."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


class TestProxyReuseAcrossMutations:
    def test_column_proxy_shape_re_resolves_after_setitem(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3]})
        proxy = af["x"]
        assert proxy.shape == "scalar"

        # Mutate frame: replace x with a list column
        af["x"] = af._df.select(pl.col("x").alias("x_inner")).select(
            pl.concat_list(pl.col("x_inner")).alias("x")
        )

        # Re-acquire (most natural path) — shape reflects new schema
        proxy_new = af["x"]
        assert proxy_new.shape == "list"

    def test_expression_proxy_shape_invalidates_on_mutation(self) -> None:
        af = ActuarialFrame({"x": [1.0, 2.0, 3.0]})
        expr_proxy = af["x"] * 2.0
        gen0 = af._schema_generation
        # First access — caches shape against gen0
        shape_a = expr_proxy.shape
        assert shape_a == "scalar"

        # Mutate frame
        af["new_col"] = af["x"] + 1.0
        gen1 = af._schema_generation
        assert gen1 == gen0 + 1

        # Access again — cache is now stale (gen0 != gen1), re-resolves
        # The wrapped pl.Expr (col(x) * 2.0) still resolves to scalar
        shape_b = expr_proxy.shape
        assert shape_b == "scalar"
        # Internal cache should now reflect gen1
        assert expr_proxy._shape_cached[0] == gen1  # type: ignore[index]

    def test_kind_invalidates_on_mutation(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3]})
        is_null_proxy = af["x"].is_null()
        gen0 = af._schema_generation
        kind_a = is_null_proxy.kind
        assert kind_a == "boolean_mask"

        af["y"] = af["x"] + 1
        # Cache invalidates; re-resolution still says boolean_mask
        kind_b = is_null_proxy.kind
        assert kind_b == "boolean_mask"
        assert is_null_proxy._kind_cached[0] == af._schema_generation  # type: ignore[index]
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/column/test_proxy_reuse_across_mutations.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/column/test_proxy_reuse_across_mutations.py
git commit -m "test(column): proxy shape/kind re-resolves after frame mutations"
```

## Task 2.16: Delete `ColumnTypeDetector` and dependents

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/dispatch.py`
- Modify: `bindings/python/gaspatchio_core/column/condition_expression.py` (had a use)

- [ ] **Step 1: Find all usages of `ColumnTypeDetector`**

```bash
cd bindings/python
rg -n "ColumnTypeDetector" gaspatchio_core/ tests/
```

- [ ] **Step 2: Replace each usage with `value.shape == "list"` or equivalent**

For each call site:
- `detector.is_list_column(name)` → use `proxy.shape == "list"` if you have a proxy, or `_shape_from_schema(parent, name) == "list"` if you have just a name.
- `detector.is_expression_list_output(expr)` → use `_shape_from_expr_dtype(parent, expr) == "list"`.
- `detector.get_all_list_columns()` → fold into the shape resolver if any caller still needs this; otherwise delete the call.

In `_should_use_list_shim` (still in dispatch.py for now), refactor it to call the new helpers instead of constructing a detector.

- [ ] **Step 3: Delete the class**

In `dispatch.py`, delete the `ColumnTypeDetector` class entirely. Also delete `_expr_references_list_column` and the `_get_list_columns_from_graph` helper.

```bash
cd bindings/python
rg -n "ColumnTypeDetector|_expr_references_list_column|_get_list_columns_from_graph" gaspatchio_core/
```

Expected: no matches.

- [ ] **Step 4: Run full test suite**

```bash
cd bindings/python
uv run pytest tests/ -x -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/column/dispatch.py bindings/python/gaspatchio_core/column/condition_expression.py
git commit -m "refactor(column): delete ColumnTypeDetector, regex heuristic, graph dtype probe

All shape detection now flows through column/shape.py::resolve_shape and the
generation-aware caching on proxies. The in-place computation-graph dtype probe,
the dummy-frame select() probe, and the regex over pl.Expr.__repr__ are gone."
```

## Task 2.17: Replace `_unwrap_for_list_eval` string check with `shape`

**Files:**
- Modify: `bindings/python/gaspatchio_core/column/dispatch.py`

- [ ] **Step 1: Locate `_unwrap_for_list_eval`**

```bash
rg -n "_unwrap_for_list_eval" gaspatchio_core/column/dispatch.py
```

- [ ] **Step 2: Replace `'col("' in expr_str` check**

In the function body, find:

```python
if isinstance(arg, pl.Expr):
    expr_str = str(arg)
    if 'col("' in expr_str:
        msg = "Cannot use expressions with named columns inside list.eval."
        raise TypeError(msg)
```

Replace with a check that uses `meta.root_names()` (which is structural, not string-based):

```python
if isinstance(arg, pl.Expr):
    try:
        roots = arg.meta.root_names()
    except Exception:  # noqa: BLE001
        roots = []
    if roots:
        msg = "Cannot use expressions with named columns inside list.eval."
        raise TypeError(msg)
```

- [ ] **Step 3: Run dispatch tests**

```bash
cd bindings/python
uv run pytest tests/ -x -q -k dispatch
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/column/dispatch.py
git commit -m "refactor(dispatch): replace 'col(\"' string check with meta.root_names()"
```

## Task 2.18: Delete `_list_broadcast_metadata` dead branch

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/base.py`

- [ ] **Step 1: Find the branch**

```bash
rg -n "_list_broadcast_metadata" gaspatchio_core/frame/base.py
```

- [ ] **Step 2: Delete the no-op branch in `__setitem__`**

Locate the block (around lines 287-299) that checks for `_list_broadcast_metadata`:

```python
if (
    hasattr(value, "_list_broadcast_metadata")
    and value._list_broadcast_metadata is not None
    and value._list_broadcast_metadata.get("element_wise")
):
    expr = self._convert_to_expr(value)
    if self._tracing:
        append_operation_to_graph(self, key, expr)
        self._df = self._df.with_columns(expr.alias(key))
    else:
        self._df = self._df.with_columns(expr.alias(key))
    return
```

Delete it. The fallback branch below it is functionally identical and handles all cases.

- [ ] **Step 3: Run frame tests**

```bash
cd bindings/python
uv run pytest tests/frame/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/base.py
git commit -m "refactor(frame): delete dead _list_broadcast_metadata branch in __setitem__

The branch and its fallback did identical work. Removing the check simplifies
__setitem__ to a single code path."
```

## Task 2.19: Delete `_expr_to_str` and string-eager `collect()` scaffolding

**Files:**
- Modify: `bindings/python/gaspatchio_core/frame/base.py`

- [ ] **Step 1: Find dead string scaffolding**

```bash
rg -n "_expr_to_str|isinstance.*operation.expression.*str" gaspatchio_core/frame/base.py
```

- [ ] **Step 2: Delete `_expr_to_str` method**

Around lines 407-422, delete the `_expr_to_str` method entirely.

- [ ] **Step 3: Delete the string-eager skip in `collect()`**

Around lines 508-512, delete the block:

```python
if isinstance(operation.expression, str):
    logger.trace(
        f"Skipping '{operation.alias}' - already executed eagerly"
    )
    continue
```

This skip path is unreachable since no code populates string expressions into the computation graph.

- [ ] **Step 4: Run full test suite**

```bash
cd bindings/python
uv run pytest tests/ -x -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/frame/base.py
git commit -m "refactor(frame): delete _expr_to_str and string-eager collect() skip path

These were dead scaffolding never populated by any code path. Removing them
simplifies the collect() loop and the operation-graph contract."
```

## Task 2.20: Mode parity smoke test

**Files:**
- Create: `bindings/python/tests/integration/test_mode_parity_smoke.py`

- [ ] **Step 1: Write the test**

```python
"""Smoke test: model with mixed scalar/list dispatch produces identical output in debug and optimize modes."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.util import set_default_mode


@pytest.fixture
def af() -> ActuarialFrame:
    return ActuarialFrame(
        {
            "policy_id": ["P001", "P002"],
            "age": [35, 65],
            "month": [list(range(12)), list(range(24))],
            "premium_term": [12, 24],
            "base_premium": [100.0, 200.0],
        }
    )


def _build_mixed_model(af: ActuarialFrame) -> ActuarialFrame:
    af.is_active = af.month < af.premium_term
    af.premium_due = (
        when(af.is_active == False).then(0.0)  # noqa: E712
        .when(af.age > 60).then(af.base_premium * 1.2)
        .otherwise(af.base_premium)
    )
    af.cumulative = af.premium_due  # placeholder for any ops we want to exercise
    return af


class TestModeParity:
    def test_mixed_scalar_list_dispatch_parity(self, af: ActuarialFrame) -> None:
        set_default_mode("debug")
        debug_result = _build_mixed_model(af).collect()

        # Reset the frame
        af2 = ActuarialFrame(
            {
                "policy_id": ["P001", "P002"],
                "age": [35, 65],
                "month": [list(range(12)), list(range(24))],
                "premium_term": [12, 24],
                "base_premium": [100.0, 200.0],
            }
        )
        set_default_mode("optimize")
        optimize_result = _build_mixed_model(af2).collect()

        # Same columns, same values
        assert debug_result.columns == optimize_result.columns
        for col in debug_result.columns:
            assert debug_result[col].to_list() == optimize_result[col].to_list(), (
                f"Column {col} differs between debug and optimize modes"
            )
        # Schemas match
        assert debug_result.schema == optimize_result.schema
```

Create `bindings/python/tests/integration/__init__.py` if missing.

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/integration/test_mode_parity_smoke.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/integration/__init__.py bindings/python/tests/integration/test_mode_parity_smoke.py
git commit -m "test(integration): mode parity smoke test for mixed scalar/list dispatch"
```

## Task 2.21: Targeted dead-code-deletion test

**Files:**
- Create: `bindings/python/tests/test_dead_code_removed.py`

- [ ] **Step 1: Write the test**

```python
"""Tests that prevent regression of removed dead code."""

from __future__ import annotations

import pytest


def test_columntypedetector_removed() -> None:
    """ColumnTypeDetector should no longer be importable."""
    with pytest.raises(ImportError):
        from gaspatchio_core.column.dispatch import ColumnTypeDetector  # noqa: F401


def test_expr_references_list_column_removed() -> None:
    with pytest.raises(ImportError):
        from gaspatchio_core.column.dispatch import _expr_references_list_column  # noqa: F401


def test_is_expression_list_output_removed() -> None:
    """is_expression_list_output is now folded into _shape_from_expr_dtype."""
    with pytest.raises(ImportError):
        from gaspatchio_core.column.dispatch import is_expression_list_output  # noqa: F401


def test_list_broadcast_metadata_removed() -> None:
    """ExpressionProxy no longer has the _list_broadcast_metadata channel."""
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    import polars as pl

    proxy = ExpressionProxy(pl.lit(1), parent=None)
    assert not hasattr(proxy, "_list_broadcast_metadata")


def test_expr_to_str_removed() -> None:
    """frame/base.py::_expr_to_str is gone."""
    from gaspatchio_core.frame import base

    assert not hasattr(base.ActuarialFrame, "_expr_to_str")


def test_is_boolean_list_attribute_not_set() -> None:
    """ConditionExpression.__and__ no longer sets _is_boolean_list."""
    from gaspatchio_core import ActuarialFrame

    af = ActuarialFrame({"x": [1, 2, 3]})
    cond = (af["x"] > 1) & (af["x"] < 3)
    # Use kind property instead
    assert cond.kind == "boolean_mask"
    assert not hasattr(cond, "_is_boolean_list") or not cond._is_boolean_list
```

- [ ] **Step 2: Run, confirm pass**

```bash
cd bindings/python
uv run pytest tests/test_dead_code_removed.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add bindings/python/tests/test_dead_code_removed.py
git commit -m "test: assert removed dead code stays removed (regression guard)"
```

## Task 2.22: CI lint rule banning direct `__df` writes

**Files:**
- Modify: `bindings/python/pyproject.toml` (or wherever Ruff config lives)

- [ ] **Step 1: Identify Ruff config**

```bash
rg -n "ruff" ../gaspatchio-core-gsp-95-dispatch-refactor/pyproject.toml ../gaspatchio-core-gsp-95-dispatch-refactor/bindings/python/pyproject.toml 2>/dev/null
```

- [ ] **Step 2: Add a custom Ruff `noqa`-style or simple grep-based check**

Ruff doesn't have a built-in rule for "ban this exact attribute write." Use a pre-commit hook or pytest-based smoke test instead.

Add to `bindings/python/tests/test_dead_code_removed.py`:

```python
def test_no_direct_underlying_df_writes_outside_property() -> None:
    """Defense in depth: no other code may write to self._ActuarialFrame__df directly."""
    import re
    from pathlib import Path

    base_py = (
        Path(__file__).parent.parent / "gaspatchio_core" / "frame" / "base.py"
    )
    pattern = re.compile(r"self\._ActuarialFrame__df\s*=")
    src = base_py.read_text()

    # Allowed only inside the @_df.setter method body. Find all matches and verify
    # each one is inside the setter (the line above the match should be the setter).
    matches = list(pattern.finditer(src))
    # Realistic upper bound: 1 inside the setter, 1 inside __init__ (initial assignment)
    assert len(matches) <= 2, (
        f"Too many direct __df writes ({len(matches)}). "
        "All mutations must go through the @_df.setter property."
    )
```

This guards against drift. If a contributor adds a third direct write, the test fails.

- [ ] **Step 3: Run**

```bash
cd bindings/python
uv run pytest tests/test_dead_code_removed.py::test_no_direct_underlying_df_writes_outside_property -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/tests/test_dead_code_removed.py
git commit -m "test: limit direct __df writes to the property setter and __init__"
```

## Task 2.23: Run full benchmark suite, verify no regression

**Files:**
- Run: `realistic_vector_lookup`, the chained-conditional benchmark

- [ ] **Step 1: Run `realistic_vector_lookup`**

```bash
cd ../gaspatchio-core-gsp-95-dispatch-refactor/core
cargo bench --bench realistic_vector_lookup
```

Expected: ≤ 5% regression vs PR 1 baseline. Record results.

- [ ] **Step 2: Run chained-conditional benchmark**

```bash
cd ../gaspatchio-core-gsp-95-dispatch-refactor/bindings/python
uv run pytest tests/benchmarks/test_chained_when_bench.py --benchmark-only -v
```

Expected: ≤ 5% slowdown vs PR 1 baseline.

- [ ] **Step 3: Document any change**

If results show >5% movement (either benchmark), append to `core/benches/perf_results.md`:

```markdown
## 2026-04-30 — PR 2 (shape SOT + property setter)
- realistic_vector_lookup: <baseline> → <new> (<delta>%)
- bench_when_chained_scalar: <baseline> → <new> (<delta>%)
- Notes: <any context>
```

- [ ] **Step 4: Commit (if perf notes were updated)**

```bash
git add core/benches/perf_results.md
git commit -m "bench: record PR 2 performance impact"
```

## Task 2.24: Open PR for Phase 2

**Files:**
- Branch: `gsp-95-pr2-shape-sot` → target `develop` (or `gsp-95-dispatch-refactor` if working in series)

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin gsp-95-pr2-shape-sot
gh pr create --title "refactor: shape source-of-truth via typed proxy properties" --body "$(cat <<'EOF'
## Summary

Replaces ColumnTypeDetector and the _is_boolean_list ducktype with typed shape/kind @properties on ColumnProxy, ExpressionProxy, and ConditionExpression. Schema cache is mechanically enforced via _df property setter and a generation counter that invalidates proxy caches on mutation.

Predicate-producing methods (is_null, is_in, is_unique, etc., including those autopatched from pl.Expr) are correctly classified as kind="boolean_mask" via dtype-driven fallback.

## Test plan

- [x] All PR 1 tests still pass
- [x] tests/column/test_resolve_shape.py — _max_shape, resolve_shape, _shape_from_schema, _shape_from_expr_dtype
- [x] tests/column/test_kind_from_dtype.py — Boolean/list-Boolean/numeric/no-parent/probe-failure cases
- [x] tests/column/test_proxy_reuse_across_mutations.py — generation invalidation works on retained proxies
- [x] tests/frame/test_schema_invalidation.py — _schema and _schema_generation invariants across mutation methods
- [x] tests/integration/test_mode_parity_smoke.py — debug == optimize for mixed scalar/list models
- [x] tests/test_dead_code_removed.py — ColumnTypeDetector and friends gone
- [x] realistic_vector_lookup not regressed
- [x] bench_when_chained_scalar within 5% of PR 1 baseline

Refs GSP-95.
EOF
)"
```

- [ ] **Step 2: After merge, prepare for Phase 3**

After PR 2 merges, create the PR 3 branch:

```bash
git checkout gsp-95-dispatch-refactor
git pull origin gsp-95-dispatch-refactor
git checkout -b gsp-95-pr3-plugin-router
```

---

# Phase 3 — PR 3: Polars plugin router extraction

**Goal:** Extract Polars-specific implementation from `dispatch.py` and `condition_expression.py` into a new `polars_backend/` subpackage. `dispatch.py` shrinks to proxy-delegation glue. `condition_expression.py` becomes a thin frontend.

**Branch:** `gsp-95-pr3-plugin-router` off `gsp-95-dispatch-refactor` (rebased on PR 2 merge).

**Stop criterion:** `polars_backend/` subpackage exists with `plugins.py`, `operators.py`, `masks.py`, `list_eval.py`; boolean-mask arithmetic, plugin invocations, and `list.eval` unwrapping live in `polars_backend/`, not in `column/`; `condition_expression.py` `__and__`/`__or__`/`__invert__` are thin stubs that delegate to `polars_backend.masks`; all PR 1 + PR 2 tests pass; benchmarks within 5% of PR 2 baseline.

**Out of scope (intentional):** `column/shape.py` is *not* relocated by PR 3. It is the frontend's shape resolver — its public interface (`resolve_shape`, `_max_shape`, `Shape`, `Kind`) is language semantics. The Polars probe inside `_shape_from_expr_dtype` (`df.select(expr.alias("_t")).collect_schema()`) is an implementation detail of how the frontend answers "what shape is this expression?", not a dispatch routing decision. Moving it would split the SOT across two packages.

**LOC note:** "shrinks `dispatch.py`" is a content claim, not a size claim. Today `dispatch.py` is 821 LOC; after extracting `_execute_list_pow_plugin` (~50), `_execute_list_clip_plugin` (~40), and `_unwrap_for_list_eval` (~40) it will be roughly 690 LOC. The win is *what* leaves, not *how much*. Do not gate the PR on a LOC threshold.

## Task 3.1: Create `polars_backend/` directory and `__init__.py`

**Files:**
- Create: `bindings/python/gaspatchio_core/polars_backend/__init__.py`

- [ ] **Step 1: Create the directory and stub file**

```bash
mkdir -p bindings/python/gaspatchio_core/polars_backend
```

Create `bindings/python/gaspatchio_core/polars_backend/__init__.py`:

```python
"""Polars-specific lowering for Gaspatchio's DSL.

This subpackage contains everything that knows about Polars:
- plugin function wrappers (register_plugin_function)
- list-aware operator implementations (list_pow, list_clip)
- boolean-mask arithmetic-as-logic
- list.eval restrictions

The frontend (column/, frame/, functions/) imports from here when it needs to
emit Polars expressions; nothing in polars_backend imports from column/ — that
direction would create circular dependencies and leak frontend concerns.
"""

# Re-exports from submodules for ease of use
from gaspatchio_core.polars_backend.list_eval import unwrap_for_list_eval
from gaspatchio_core.polars_backend.masks import (
    boolean_and,
    boolean_not,
    boolean_or,
    to_boolean_expr,
)
from gaspatchio_core.polars_backend.operators import (
    dispatch_list_op,
    execute_list_clip,
    execute_list_pow,
)
from gaspatchio_core.polars_backend.plugins import (
    accumulate,
    fill_series,
    floor,
    list_clip,
    list_conditional,
    list_pow,
    rollforward_plugin,
    round,
    round_to_int,
)

__all__ = [
    "accumulate",
    "boolean_and",
    "boolean_not",
    "boolean_or",
    "dispatch_list_op",
    "execute_list_clip",
    "execute_list_pow",
    "fill_series",
    "floor",
    "list_clip",
    "list_conditional",
    "list_pow",
    "rollforward_plugin",
    "round",
    "round_to_int",
    "to_boolean_expr",
    "unwrap_for_list_eval",
]
```

This will fail on import since the submodules don't exist yet — that's expected. We'll add them in subsequent tasks.

- [ ] **Step 2: Don't run anything yet (subsequent tasks add the submodules)**

- [ ] **Step 3: Commit (as scaffold)**

```bash
git add bindings/python/gaspatchio_core/polars_backend/__init__.py
git commit -m "scaffold(polars_backend): create subpackage skeleton with re-export plan"
```

## Task 3.2: Move plugin wrappers to `polars_backend/plugins.py`

**Files:**
- Create: `bindings/python/gaspatchio_core/polars_backend/plugins.py`
- Modify: `bindings/python/gaspatchio_core/functions/vector.py`
- Create: `bindings/python/tests/polars_backend/test_public_api.py`

- [ ] **Step 1: Move the body**

Copy the entire body of `bindings/python/gaspatchio_core/functions/vector.py` to a new file `bindings/python/gaspatchio_core/polars_backend/plugins.py`. Add a one-line proxy-unwrap helper to DRY the duplicated `if hasattr(expr, "name") and hasattr(expr, "_parent")` pattern that appears in 4 wrappers:

```python
def _unwrap_proxy(expr: Any) -> pl.Expr | Any:  # noqa: ANN401
    """Unwrap ColumnProxy / ExpressionProxy to underlying pl.Expr.

    Defined locally instead of importing from column/ to keep the
    polars_backend -> column/ direction empty (no circular imports).
    """
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        return pl.col(expr.name)
    if hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        return expr._expr  # noqa: SLF001
    return expr
```

Replace each duplicated `if hasattr...elif hasattr...` block in the moved file with `expr = _unwrap_proxy(expr)`.

- [ ] **Step 2: Convert `bindings/python/gaspatchio_core/functions/vector.py` to a re-export shim**

Replace the entire content with:

```python
"""Backwards-compatible re-exports of plugin wrappers.

The actual implementations live in `gaspatchio_core.polars_backend.plugins`.
This module exists to preserve the public import path
`from gaspatchio_core.functions.vector import accumulate` (et al.) for users
of older Gaspatchio versions.
"""

from gaspatchio_core.polars_backend.plugins import (
    accumulate,
    fill_series,
    floor,
    list_clip,
    list_conditional,
    list_pow,
    rollforward_plugin,
    round,
    round_to_int,
)

__all__ = [
    "accumulate",
    "fill_series",
    "floor",
    "list_clip",
    "list_conditional",
    "list_pow",
    "rollforward_plugin",
    "round",
    "round_to_int",
]
```

- [ ] **Step 3: Write a public-API import test**

Create `bindings/python/tests/polars_backend/__init__.py` (empty) and `bindings/python/tests/polars_backend/test_public_api.py`:

```python
"""Verify all public plugin imports continue to work after relocation."""

from __future__ import annotations


def test_functions_vector_imports_still_work() -> None:
    """Old import path remains stable."""
    from gaspatchio_core.functions.vector import (  # noqa: F401
        accumulate,
        fill_series,
        floor,
        list_clip,
        list_conditional,
        list_pow,
        rollforward_plugin,
        round,
        round_to_int,
    )


def test_polars_backend_imports() -> None:
    """New canonical import path works."""
    from gaspatchio_core.polars_backend import (  # noqa: F401
        accumulate,
        fill_series,
        floor,
        list_clip,
        list_conditional,
        list_pow,
        rollforward_plugin,
        round,
        round_to_int,
    )


def test_re_exports_are_same_function() -> None:
    """Old and new paths reach the same callable, not a copy."""
    from gaspatchio_core.functions.vector import accumulate as old_accumulate
    from gaspatchio_core.polars_backend.plugins import accumulate as new_accumulate

    assert old_accumulate is new_accumulate
```

- [ ] **Step 4: Run tests**

```bash
cd bindings/python
uv run pytest tests/polars_backend/test_public_api.py -v
uv run pytest tests/ -x -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/polars_backend/plugins.py \
        bindings/python/gaspatchio_core/functions/vector.py \
        bindings/python/tests/polars_backend/__init__.py \
        bindings/python/tests/polars_backend/test_public_api.py
git commit -m "refactor: move plugin wrappers to polars_backend/plugins.py with re-export shim"
```

## Task 3.3: Move `_execute_list_pow` and `_execute_list_clip` to `polars_backend/operators.py`

**Files:**
- Create: `bindings/python/gaspatchio_core/polars_backend/operators.py`
- Modify: `bindings/python/gaspatchio_core/column/dispatch.py`
- Create: `bindings/python/tests/polars_backend/test_operators.py`

- [ ] **Step 1: Create `polars_backend/operators.py`**

Create `bindings/python/gaspatchio_core/polars_backend/operators.py`:

```python
"""Backend implementations for shape-aware named operations.

Each operation here corresponds to an entry in `dispatch.py`'s `_BACKEND_LIST_OPS`
registry. Dispatch resolves the proxy's shape, decides the op needs backend
routing, and calls `dispatch_list_op(name, ...)`.
"""

from __future__ import annotations

from typing import Any

import polars as pl
from loguru import logger

from gaspatchio_core.polars_backend.plugins import list_clip, list_pow


def execute_list_pow(
    base_expr: pl.Expr,
    args: tuple,
    *,
    base_is_list: bool = True,
) -> pl.Expr:
    """Execute pow using Rust list_pow for list columns with column exponents.

    Three cases:
    - list ** list: direct list_pow call
    - list ** scalar: direct list_pow call (plugin handles broadcasting)
    - scalar ** list: uses exp/log identity since list_pow requires list base
    """
    if not args:
        msg = "pow requires an exponent argument"
        raise ValueError(msg)

    exp_arg = args[0]
    exp_expr = _unwrap_for_pow(exp_arg)
    if not isinstance(exp_expr, pl.Expr):
        exp_expr = pl.lit(exp_expr)

    if base_is_list:
        logger.trace(f"Using list_pow plugin: base={base_expr}, exp={exp_expr}")
        return list_pow(base_expr, exp_expr)

    # scalar ** list: use exp/log identity (scalar^list = exp(list * log(scalar)))
    logger.trace("Using guarded exp/log identity for scalar**list pow")
    exp_log_result = (exp_expr * base_expr.log()).list.eval(pl.element().exp())
    return (
        pl.when(base_expr > 0)
        .then(exp_log_result)
        .when(base_expr.eq(0))
        .then(
            exp_expr.list.eval(
                pl.when(pl.element() > 0).then(0.0)
                .when(pl.element().eq(0)).then(1.0)
                .otherwise(pl.lit(float("nan")))
            )
        )
        .otherwise(pl.lit(None))
    )


_CLIP_UPPER_ARG_INDEX = 2


def execute_list_clip(
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
) -> pl.Expr:
    """Execute clip using Rust list_clip for list columns with column bounds."""
    lower_arg = None
    upper_arg = None

    if len(args) >= 1:
        lower_arg = args[0]
    if len(args) >= _CLIP_UPPER_ARG_INDEX:
        upper_arg = args[1]

    if "lower_bound" in kwargs:
        lower_arg = kwargs["lower_bound"]
    if "upper_bound" in kwargs:
        upper_arg = kwargs["upper_bound"]

    lower_expr = _unwrap_for_pow(lower_arg) if lower_arg is not None else pl.lit(float("-inf"))
    upper_expr = _unwrap_for_pow(upper_arg) if upper_arg is not None else pl.lit(float("inf"))

    if not isinstance(lower_expr, pl.Expr):
        lower_expr = pl.lit(lower_expr)
    if not isinstance(upper_expr, pl.Expr):
        upper_expr = pl.lit(upper_expr)

    logger.trace(
        f"Using list_clip plugin: values={base_expr}, "
        f"lower={lower_expr}, upper={upper_expr}"
    )
    return list_clip(base_expr, lower_expr, upper_expr)


def dispatch_list_op(
    name: str,
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
    *,
    base_is_list: bool = True,
) -> pl.Expr:
    """Single entry point for backend-specific list operations.

    Dispatch in column/dispatch.py decides whether to call this based on
    `_BACKEND_LIST_OPS`. The router itself stays minimal: name → handler.
    """
    if name == "pow":
        return execute_list_pow(base_expr, args, base_is_list=base_is_list)
    if name == "clip":
        return execute_list_clip(base_expr, args, kwargs)
    msg = f"No backend handler for list op: {name}"
    raise NotImplementedError(msg)


def _unwrap_for_pow(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap proxy types to underlying pl.Expr (local helper to avoid frontend imports)."""
    if hasattr(arg, "name") and hasattr(arg, "_parent"):
        return pl.col(arg.name)
    if hasattr(arg, "_expr") and hasattr(arg, "_parent"):
        return arg._expr  # noqa: SLF001
    return arg
```

- [ ] **Step 2: Update `dispatch.py` to call the router**

In `dispatch.py`, locate `_method_caller` and `_execute_list_pow_plugin` / `_execute_list_clip_plugin`. Delete the local helper definitions (they've moved). Update `_method_caller` to call the router:

```python
# At the top, add the registry:
_BACKEND_LIST_OPS: set[str] = {"pow", "clip"}

# In _method_caller, replace the pow/clip special-case routing with:
if should_use_list_shim and name in _BACKEND_LIST_OPS:
    from gaspatchio_core.polars_backend.operators import dispatch_list_op

    logger.trace(f"Routing {name} to polars_backend dispatch_list_op")
    result = dispatch_list_op(
        name, base_expr, a, kw, base_is_list=pow_base_is_list
    )
elif should_use_list_shim:
    # Existing list-shim logic for the rest of _NUMERIC_UNARY/_ELEMENTWISE
    try:
        result = _execute_list_shim(name, base_expr, a, kw, is_unary=is_unary)
    except (TypeError, ValueError):
        result = _execute_regular(polars_attr, a, kw)
else:
    result = _execute_regular(polars_attr, a, kw)
```

Delete `_execute_list_pow_plugin` and `_execute_list_clip_plugin` from `dispatch.py` entirely.

- [ ] **Step 3: Write unit tests for the moved operators**

Create `bindings/python/tests/polars_backend/test_operators.py`:

```python
"""Unit tests for polars_backend.operators — especially the scalar^list identity branches."""

from __future__ import annotations

import pytest


class TestScalarPowList:
    """The scalar^list = exp(list * log(scalar)) identity has 3 branches."""

    @pytest.mark.parametrize(
        "base,expected_present",
        [(2.0, True), (0.0, True), (-2.0, False)],
    )
    def test_branch_for_each_base_sign(self, base: float, expected_present: bool) -> None:
        import polars as pl

        from gaspatchio_core.polars_backend.operators import execute_list_pow

        # base scalar 2^[1,2,3] -> [2,4,8]
        # base scalar 0^[1,2,3] -> [0, 0, 0]
        # base scalar -2^[1,2,3] -> null (undefined for fractional)
        df = pl.DataFrame({"base": [base], "exp": [[1.0, 2.0, 3.0]]})
        result = df.lazy().select(
            execute_list_pow(
                pl.col("base"), (pl.col("exp"),), base_is_list=False
            ).alias("r")
        ).collect()
        result_list = result["r"][0]
        if expected_present:
            assert result_list is not None
        else:
            # negative base with fractional exponent -> all-null list or null list
            # implementation-defined: assert it's at least not equal to [-2, 4, -8]
            if result_list is not None:
                values = result_list.to_list()
                # must not be the naive negative-power result
                assert values != [-2.0, 4.0, -8.0]


class TestListPowList:
    def test_list_pow_list_works(self) -> None:
        import polars as pl

        from gaspatchio_core.polars_backend.operators import execute_list_pow

        df = pl.DataFrame({"base": [[2.0, 3.0]], "exp": [[2.0, 3.0]]})
        result = df.lazy().select(
            execute_list_pow(
                pl.col("base"), (pl.col("exp"),), base_is_list=True
            ).alias("r")
        ).collect()
        assert result["r"][0].to_list() == pytest.approx([4.0, 27.0])


class TestListClip:
    def test_list_clip_with_scalar_bounds(self) -> None:
        import polars as pl

        from gaspatchio_core.polars_backend.operators import execute_list_clip

        df = pl.DataFrame({"v": [[0.5, 1.5, 2.5, 3.5]]})
        result = df.lazy().select(
            execute_list_clip(
                pl.col("v"),
                (pl.lit(1.0), pl.lit(3.0)),
                {},
            ).alias("r")
        ).collect()
        assert result["r"][0].to_list() == pytest.approx([1.0, 1.5, 2.5, 3.0])
```

- [ ] **Step 4: Run tests**

```bash
cd bindings/python
uv run pytest tests/polars_backend/test_operators.py -v
uv run pytest tests/ -x -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/polars_backend/operators.py \
        bindings/python/gaspatchio_core/column/dispatch.py \
        bindings/python/tests/polars_backend/test_operators.py
git commit -m "refactor: move execute_list_pow, execute_list_clip to polars_backend/operators.py

dispatch.py routes through dispatch_list_op for ops in _BACKEND_LIST_OPS.
Adds explicit unit tests for the scalar^list exp/log identity branches that
were previously only exercised through integration tests."
```

## Task 3.4: Move boolean-mask arithmetic to `polars_backend/masks.py`

**Files:**
- Create: `bindings/python/gaspatchio_core/polars_backend/masks.py`
- Modify: `bindings/python/gaspatchio_core/column/condition_expression.py`
- Create: `bindings/python/tests/polars_backend/test_masks.py`

- [ ] **Step 1: Create `masks.py`**

Create `bindings/python/gaspatchio_core/polars_backend/masks.py`:

```python
"""Polars-backend implementations of boolean-mask combinators and predicate-to-bool conversion.

The frontend (`column/condition_expression.py`) declares that AND/OR/NOT of
conditions produces a boolean_mask ExpressionProxy. The arithmetic-as-logic
implementation (`left * right` for AND, `1 - (1-a)*(1-b)` for OR, etc.) lives
here as an implementation detail of the Polars backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio_core.polars_backend.plugins import list_conditional

if TYPE_CHECKING:
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy


def to_boolean_expr(condition: ConditionExpression) -> pl.Expr:
    """Convert a ConditionExpression to a Float64 0/1 expression.

    Uses list_conditional for list-shaped conditions; native Polars cast for scalar.
    """
    if condition.shape == "list":
        return list_conditional(
            condition.left, condition.right, pl.lit(1.0), pl.lit(0.0), condition.operator
        )
    return condition._expr.cast(pl.Float64)  # noqa: SLF001


def boolean_and(
    left: ConditionExpression,
    right: Any,  # noqa: ANN401
    parent: Any,  # noqa: ANN401
) -> pl.Expr:
    """Combine two predicates with element-wise AND."""
    has_list = left.shape == "list" or _other_has_list(right)
    if has_list:
        left_bool = to_boolean_expr(left)
        right_bool = _other_to_boolean_expr(right)
        return left_bool * right_bool
    # Scalar path: native Polars boolean AND
    return left._expr & _other_to_native_expr(right)  # noqa: SLF001


def boolean_or(
    left: ConditionExpression,
    right: Any,  # noqa: ANN401
    parent: Any,  # noqa: ANN401
) -> pl.Expr:
    """Combine two predicates with element-wise OR via 1 - (1-a)(1-b)."""
    left_bool = to_boolean_expr(left)
    right_bool = _other_to_boolean_expr(right)
    return pl.lit(1.0) - ((pl.lit(1.0) - left_bool) * (pl.lit(1.0) - right_bool))


def boolean_not(condition: ConditionExpression) -> pl.Expr:
    """Negate a predicate: 1 - bool."""
    bool_expr = to_boolean_expr(condition)
    return pl.lit(1.0) - bool_expr


def _other_to_boolean_expr(other: Any) -> pl.Expr:  # noqa: ANN401
    """Convert the second operand of AND/OR to a Float64 0/1 expression."""
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(other, ConditionExpression):
        return to_boolean_expr(other)
    if isinstance(other, ColumnProxy):
        return other._to_expr().cast(pl.Float64)  # noqa: SLF001
    if isinstance(other, ExpressionProxy):
        return other._expr  # noqa: SLF001
    return other


def _other_to_native_expr(other: Any) -> pl.Expr:  # noqa: ANN401
    """Used in scalar path to coerce the second AND operand to a native pl.Expr."""
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(other, ConditionExpression):
        return other._expr  # noqa: SLF001
    if isinstance(other, ColumnProxy):
        return other._to_expr()  # noqa: SLF001
    if isinstance(other, ExpressionProxy):
        return other._expr  # noqa: SLF001
    return other


def _other_has_list(other: Any) -> bool:  # noqa: ANN401
    """Inspect operand shape — used to decide list path vs scalar path for AND."""
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(other, (ConditionExpression, ColumnProxy, ExpressionProxy)):
        return other.shape == "list"
    return False
```

Note: the `_other_to_*` helpers do import from `column/`, which is the only place `polars_backend/` reaches into the frontend. That's a controlled exception — these helpers are coercing user-facing types into Polars. Keep them small.

- [ ] **Step 2: Update `condition_expression.py` operator overloads**

Replace the bodies of `__and__`, `__rand__`, `__or__`, `__ror__`, `__invert__` to delegate to `polars_backend.masks`:

```python
def __and__(self, other: ConditionExpression) -> ExpressionProxy:
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.polars_backend import masks

    combined = masks.boolean_and(self, other, parent=self._parent)
    return ExpressionProxy(combined, self._parent, kind="boolean_mask")


def __rand__(self, other: ExpressionProxy) -> ExpressionProxy:
    """ExpressionProxy & ConditionExpression."""
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.polars_backend.masks import to_boolean_expr

    left_bool = other._expr  # noqa: SLF001
    right_bool = to_boolean_expr(self)
    combined = left_bool * right_bool
    return ExpressionProxy(combined, self._parent, kind="boolean_mask")


def __or__(self, other: ConditionExpression) -> ExpressionProxy:
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.polars_backend import masks

    combined = masks.boolean_or(self, other, parent=self._parent)
    return ExpressionProxy(combined, self._parent, kind="boolean_mask")


def __ror__(self, other: ExpressionProxy) -> ExpressionProxy:
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.polars_backend.masks import to_boolean_expr

    left_bool = other._expr  # noqa: SLF001
    right_bool = to_boolean_expr(self)
    combined = pl.lit(1.0) - ((pl.lit(1.0) - left_bool) * (pl.lit(1.0) - right_bool))
    return ExpressionProxy(combined, self._parent, kind="boolean_mask")


def __invert__(self) -> ExpressionProxy:
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.polars_backend import masks

    negated = masks.boolean_not(self)
    return ExpressionProxy(negated, self._parent, kind="boolean_mask")
```

Also replace the `_to_boolean_expr` method body to delegate:

```python
def _to_boolean_expr(self) -> pl.Expr:
    from gaspatchio_core.polars_backend.masks import to_boolean_expr

    return to_boolean_expr(self)
```

- [ ] **Step 3: Write tests for masks**

Create `bindings/python/tests/polars_backend/test_masks.py`:

```python
"""Unit tests for polars_backend.masks — boolean-mask arithmetic identities."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


class TestBooleanAndOr:
    def test_and_scalar_path(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3, 4]})
        af.flag = ((af["x"] > 1) & (af["x"] < 4)).cast(pl.Float64) if False else None
        # Use a typical mask in a when() to verify behavior
        from gaspatchio_core import when

        af.r = (
            when((af["x"] > 1) & (af["x"] < 4))
            .then(1.0)
            .otherwise(0.0)
        )
        result = af.collect()["r"].to_list()
        assert result == [0.0, 1.0, 1.0, 0.0]

    def test_or_scalar_path(self) -> None:
        from gaspatchio_core import when

        af = ActuarialFrame({"x": [1, 2, 3, 4]})
        af.r = (
            when((af["x"] == 1) | (af["x"] == 4))
            .then(1.0)
            .otherwise(0.0)
        )
        assert af.collect()["r"].to_list() == [1.0, 0.0, 0.0, 1.0]

    def test_invert_scalar(self) -> None:
        from gaspatchio_core import when

        af = ActuarialFrame({"x": [1, 2, 3, 4]})
        af.r = when(~(af["x"] > 2)).then(1.0).otherwise(0.0)
        assert af.collect()["r"].to_list() == [1.0, 1.0, 0.0, 0.0]
```

- [ ] **Step 4: Run tests**

```bash
cd bindings/python
uv run pytest tests/polars_backend/test_masks.py -v
uv run pytest tests/functions/test_conditional.py tests/functions/test_conditional_chained_lists.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/gaspatchio_core/polars_backend/masks.py \
        bindings/python/gaspatchio_core/column/condition_expression.py \
        bindings/python/tests/polars_backend/test_masks.py
git commit -m "refactor: move boolean-mask arithmetic to polars_backend/masks.py

condition_expression.py operator overloads (&, |, ~) become thin frontend
declarations that call into polars_backend.masks. The arithmetic-as-logic
identities (1*1, 1-(1-a)(1-b), 1-bool) move with the rest of Polars-specific
implementation."
```

## Task 3.5: Move `_unwrap_for_list_eval` to `polars_backend/list_eval.py`

**Files:**
- Create: `bindings/python/gaspatchio_core/polars_backend/list_eval.py`
- Modify: `bindings/python/gaspatchio_core/column/dispatch.py`

- [ ] **Step 1: Create `list_eval.py` with the function**

Create `bindings/python/gaspatchio_core/polars_backend/list_eval.py`:

```python
"""Restrictions and helpers for working inside Polars `list.eval()` contexts.

Inside `list.eval`, you cannot reference named columns — the evaluation context
is per-element, not per-frame. This module enforces that constraint when
unwrapping arguments destined for `list.eval` calls.
"""

from __future__ import annotations

from typing import Any

import polars as pl


def unwrap_for_list_eval(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap an argument for use inside `list.eval(...)` context.

    Inside list.eval, named-column references are illegal. Detect them via
    structural meta.root_names() (not string inspection) and raise.
    """
    # Defer proxy imports to avoid frontend dependency cycles
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        msg = f"Cannot reference column '{arg.name}' inside list.eval context."
        raise TypeError(msg)
    if isinstance(arg, ExpressionProxy):
        msg = "Cannot use complex expressions inside list.eval context."
        raise TypeError(msg)
    if isinstance(arg, pl.Expr):
        try:
            roots = arg.meta.root_names()
        except Exception:  # noqa: BLE001
            roots = []
        if roots:
            msg = "Cannot use expressions with named columns inside list.eval."
            raise TypeError(msg)
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return arg
```

- [ ] **Step 2: Replace usages in `dispatch.py`**

In `dispatch.py`:
- Delete `_unwrap_for_list_eval` (replaced by the polars_backend version).
- Replace any imports/calls of the old function with `from gaspatchio_core.polars_backend.list_eval import unwrap_for_list_eval` and use `unwrap_for_list_eval` directly.

- [ ] **Step 3: Run tests**

```bash
cd bindings/python
uv run pytest tests/ -x -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add bindings/python/gaspatchio_core/polars_backend/list_eval.py \
        bindings/python/gaspatchio_core/column/dispatch.py
git commit -m "refactor: move unwrap_for_list_eval to polars_backend/list_eval.py"
```

## Task 3.6: Run full benchmarks, verify no regression

**Files:**
- Run: `realistic_vector_lookup`, `bench_when_chained_scalar`

- [ ] **Step 1: Run both benchmarks**

```bash
cd ../gaspatchio-core-gsp-95-dispatch-refactor/core
cargo bench --bench realistic_vector_lookup

cd ../gaspatchio-core-gsp-95-dispatch-refactor/bindings/python
uv run pytest tests/benchmarks/test_chained_when_bench.py --benchmark-only -v
```

Expected: ≤ 5% regression vs PR 2 baseline on each.

- [ ] **Step 2: Document any change**

If movement >5% on either, append to `core/benches/perf_results.md`:

```markdown
## 2026-04-30 — PR 3 (plugin router extraction)
- realistic_vector_lookup: <baseline> → <new> (<delta>%)
- bench_when_chained_scalar: <baseline> → <new> (<delta>%)
- Notes: <any context>
```

- [ ] **Step 3: Commit (if perf notes were updated)**

```bash
git add core/benches/perf_results.md
git commit -m "bench: record PR 3 performance impact"
```

## Task 3.7: Verify `dispatch.py` content boundaries

**Files:**
- Read: `bindings/python/gaspatchio_core/column/dispatch.py`

This task gates on *what* lives in `dispatch.py`, not *how big* it is. A LOC reduction is a side-effect of moving backend code out, not the goal. Don't fail this task on a size threshold.

- [ ] **Step 1: Sanity-check the size delta**

```bash
wc -l bindings/python/gaspatchio_core/column/dispatch.py
```

Reference: `dispatch.py` was 821 LOC at the start of PR 3 (post-PR-2). Extracting `_execute_list_pow_plugin` (~50), `_execute_list_clip_plugin` (~40), and `_unwrap_for_list_eval` (~40) removes ~130 LOC, landing roughly 680–700. If the file is *larger* than the pre-PR-3 baseline, that's a red flag — check whether new code accidentally landed here instead of in `polars_backend/`.

- [ ] **Step 2: Survey what remains (the real check)**

```bash
rg -n "^def |^class " bindings/python/gaspatchio_core/column/dispatch.py | head
```

Expected remainders:
- `DelegatorDescriptor`
- `_make_wrapper`, `_method_caller`, `_create_method_wrapper`
- `_wrap`, `_unwrap`, `_unwrap_for_arithmetic`, `_ensure_polars_expr_or_literal`
- `_should_use_list_shim`, `_execute_list_shim`, `_execute_regular`
- `_has_column_operands`
- `ErrorEnhancer`
- `_NUMERIC_UNARY`, `_NUMERIC_ELEMENTWISE`, `_NAMESPACES`, `_BACKEND_LIST_OPS`
- `GenericNamespaceProxy`, `SPECIALIZED_NAMESPACES`
- `_autopatch`

NOT present anymore:
- `ColumnTypeDetector`
- `_expr_references_list_column`
- `_unwrap_for_list_eval` (moved)
- `_execute_list_pow_plugin` / `_execute_list_clip_plugin` (moved)
- `is_expression_list_output` (folded into shape resolver)

- [ ] **Step 3: Commit (if any final cleanup)**

If `dispatch.py` has dead code or stale comments referring to removed things, clean them up and commit:

```bash
git add bindings/python/gaspatchio_core/column/dispatch.py
git commit -m "chore(dispatch): clean up stale comments and dead imports after extraction"
```

## Task 3.8: Open PR for Phase 3

**Files:**
- Branch: `gsp-95-pr3-plugin-router` → target `develop`

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin gsp-95-pr3-plugin-router
gh pr create --title "refactor: extract Polars plugin router into polars_backend/ subpackage" --body "$(cat <<'EOF'
## Summary

Extracts Polars-specific implementation from dispatch.py and condition_expression.py into a new polars_backend/ subpackage:

- polars_backend/plugins.py — relocated plugin wrappers (functions/vector.py is now a thin re-export shim)
- polars_backend/operators.py — execute_list_pow, execute_list_clip, dispatch_list_op router
- polars_backend/masks.py — boolean-mask arithmetic-as-logic
- polars_backend/list_eval.py — list.eval restrictions

dispatch.py drops by ~130 LOC (821 → ~690 post-PR-3) and now contains only proxy delegation, taxonomy, and the autopatch system — the LOC delta is a side-effect; the real claim is that boolean-mask arithmetic, plugin wrappers, and `list.eval` unwrapping no longer live in column/. condition_expression.py becomes a thin frontend whose operator overloads delegate to polars_backend.masks.

No new behavior. Pure relocation + interface tightening.

## Test plan

- [x] All PR 1 + PR 2 tests still pass
- [x] tests/polars_backend/test_public_api.py — `from gaspatchio_core.functions.vector import ...` still works
- [x] tests/polars_backend/test_operators.py — explicit unit tests for scalar^list exp/log identity branches (base > 0 / == 0 / < 0)
- [x] tests/polars_backend/test_masks.py — AND, OR, NOT scalar-path tests
- [x] realistic_vector_lookup not regressed
- [x] bench_when_chained_scalar within 5% of PR 2 baseline
- [x] `from gaspatchio_core.column.dispatch import ColumnTypeDetector` still raises ImportError (PR 2)
- [x] dispatch.py no longer defines `_execute_list_pow_plugin`, `_execute_list_clip_plugin`, or `_unwrap_for_list_eval`
- [x] condition_expression.py `__and__`/`__or__`/`__invert__` are thin stubs that delegate to `polars_backend.masks`
- [x] column/shape.py is unchanged (intentionally not relocated — see plan)

Refs GSP-95.
EOF
)"
```

- [ ] **Step 2: After merge, the dispatch refactor is complete**

After PR 3 merges, all three PRs are landed. The work scoped by GSP-95 / GSP-87 is done.

---

# Stop criteria summary

| PR | Closes | Stops when |
|---|---|---|
| PR 1 | GSP-87 | Chained when() matrix passes in both modes; scalar parity test passes; chained-conditional benchmark within 5% of native baseline; existing xfails converted; docs updated. |
| PR 2 | — (refs GSP-95) | ColumnTypeDetector + regex heuristic deleted; mode parity smoke passes; proxy reuse across mutations works; benchmarks within 5% of PR 1 baseline. |
| PR 3 | — (refs GSP-95) | polars_backend/ exists with plugins/operators/masks/list_eval; boolean-mask arithmetic, plugin wrappers, and `list.eval` unwrapping no longer live in column/; condition_expression.py operator overloads delegate to polars_backend.masks; column/shape.py unchanged; benchmarks within 5% of PR 2 baseline. |

If any PR fails its stop criterion, hold the next one until the failure is understood.
