# Dispatch / Broadcasting Refactor — Design

**Date:** 2026-04-30
**Linear:** GSP-95 (architecture proposal), GSP-87 (chained vector `when()` bug)
**Branch:** `gsp-95-dispatch-refactor`
**Status:** Approved design — ready for implementation planning

## Context

This design responds to two pressures on the Python dispatch / broadcasting / conditional surface in `bindings/python/gaspatchio_core/`:

1. **GSP-87.** Multiple chained `.when()` calls raise `NotImplementedError` whenever any condition involves a list (vector) column. The workaround — nesting `.otherwise(when(...).then(...).otherwise(...))` — is ugly and asymmetric with the scalar case.
2. **Maintenance pain.** The shape-detection logic that decides "is this a list column?" is scattered across at least five paths, including a regex over `pl.Expr.__repr__()` and a per-call dummy-frame schema probe. Mode-specific behavior (debug vs optimize) is a downstream symptom of this scatter.

A draft proposal exists on `cursor/dispatch-refactor-design-76e5` (PR #98) that argues for a full semantic IR + backend lowering boundary motivated by future JAX/NumPy/Mojo backends. This design takes the diagnosis from that proposal but explicitly rejects the IR layer for the current scope. JAX is directional, not concrete; building an IR without a forcing function tends to produce Polars-with-extra-steps.

## Decisions made during brainstorm

| Question | Decision |
|---|---|
| Primary driver | GSP-87 (chained vector `when()`) |
| Secondary driver | Maintenance pain in shape detection |
| Directional driver | JAX backend (no concrete timeline, no forcing function) |
| Scope | Three independent PRs: chained `when()` fix, shape source-of-truth, Polars plugin router extraction |
| Bug-fix completeness | Cursor's full matrix — every shape combination, every chain length, both modes |
| JAX-readiness stance | Polars-specific with seams. No semantic IR, no backend-agnostic interface. |
| Shape metadata richness | `shape` + `kind` typed fields on proxies and `ConditionExpression` |
| `_autopatch` policy | Out of scope. Proxy advertises full Polars `Expr` surface; we accept the coupling honestly rather than partial-shrinking it. |
| Sequencing | Chained `when()` → shape SOT → plugin router. Three reviewable PRs. |

## Goal and scope

**Goal.** Land GSP-87 across Cursor's full completeness matrix, and remove the underlying maintenance smells that made GSP-87 hard to fix in the first place — without committing to a semantic-IR layer or a backend-agnostic abstraction.

### In scope

Three independent PRs in the order below.

1. **GSP-87 fix** in `functions/conditional.py` via reverse-fold composition of existing `list_conditional` kernel calls. Full matrix: scalar/vector predicates × scalar/list/mixed branches × `&`/`|`/`~` mask predicates × any chain length.
2. **Shape source-of-truth** on `ColumnProxy` / `ExpressionProxy` / `ConditionExpression`. Typed fields `shape: Literal["scalar", "list", "unknown"]` and `kind: Literal["value", "comparison", "boolean_mask", "unknown"]`. Replaces the current `ColumnTypeDetector` machinery and the duck-typed `_is_boolean_list` flag.
3. **Polars plugin router** extracted from `dispatch.py` into a new `polars_backend/` subpackage. Moves plugin invocations and the boolean-mask arithmetic into one place. `dispatch.py` shrinks to proxy-delegation glue.

### Implicit deliverables (fall out of the above)

- The string-regex shape heuristic (`_expr_references_list_column`) is deleted.
- The `is_expression_list_output` dummy-frame probe is consolidated into a single resolver function.
- The dead `ExpressionProxy._list_broadcast_metadata` channel is deleted.
- The dead `_expr_to_str` / `isinstance(operation.expression, str)` scaffolding in `frame/base.py` is deleted.
- Debug ≡ optimize parity for the dispatch surface is achieved as a side-effect of consolidating shape detection.

### Explicitly out of scope

- **Semantic IR layer.** No `ExprNode` / `ResolvedNode` / `OpKind` / `planner.py`. The proxies are the IR.
- **Backend interface.** No abstract `Backend` class, no `LoweredExpr` wrapper. The plugin router signature returns `pl.Expr` directly.
- **JAX / NumPy / Mojo backends.** Directional only. Architectural seams left, no second backend implemented or stubbed.
- **`_autopatch` changes.** The proxy surface remains "everything `pl.Expr` exposes." The "fake portability" in this surface is acknowledged; shrinking it is a separate user-facing decision for a future ticket.
- **Accessor rewrites.** Date / finance / Excel accessors stay as they are.
- **Rust kernel changes.** The existing `list_conditional`, `list_pow`, `list_clip` kernels handle every case in the completeness matrix. No new kernels.
- **Performance work.** The only performance constraint is "don't regress the `realistic_vector_lookup` benchmark."

### What the seams cover, and what they don't

The "Polars-specific with seams" framing applies to a **narrow, named surface**, not the full proxy API. The seam boundary is intentional and tight; readers should not assume more.

**What the seams DO cover:**

- The named numeric/list operations in `_NUMERIC_UNARY ∪ _NUMERIC_ELEMENTWISE` (~30 ops: `add`, `sub`, `mul`, `pow`, `clip`, `floor`, `ceil`, `round`, `exp`, `log`, etc.).
- The `when().then().otherwise()` conditional surface and its `&`/`|`/`~` mask combinators.
- The shape source-of-truth (`shape`, `kind` properties on proxies and `ConditionExpression`).
- The plugin router (`polars_backend/operators.py`, `polars_backend/masks.py`, `polars_backend/plugins.py`).

For these, the design guarantees: shape resolution goes through one resolver; backend routing decisions live in `polars_backend/`; same DSL text produces equivalent semantics regardless of operand shape.

**What the seams DO NOT cover:**

- Any `pl.Expr` method exposed via `_autopatch` that is not in the named numeric/list set above. Examples: `rolling_mean`, `cumulative_eval`, `set_sorted`, `is_in`, `cum_max`, `interpolate`, `cast`, etc. These pass straight through to Polars via `DelegatorDescriptor.__get__` → `_method_caller` → `_execute_regular`. They do not consult `shape`, do not route through `polars_backend/`, and behave exactly as they do today.
- Polars namespace methods accessed via `GenericNamespaceProxy` (`.dt.year()`, `.list.sum()`, `.str.contains()`, `.struct.field()`). These also pass through unchanged.
- User code that reaches into `proxy._expr` directly and calls `pl.Expr` methods on the unwrapped expression. The proxy-level seams cannot govern this.
- Public Polars APIs we don't currently mirror (`pl.from_pandas`, `pl.scan_parquet`, etc.). Out of frame.

**The honest framing:** the proxy surface is `pl.Expr` plus our additions. The refactor cleans up the routing for the additions and the named numeric/list ops; everything else is a Polars passthrough. Users writing models against the proxy are writing against `pl.Expr` semantics for anything outside the seam-covered set.

### The boundary is documentation, not enforcement (known limitation)

The "what's covered" subsection above is descriptive prose, not an executable manifest. `_autopatch` reflects against `dir(pl.Expr)` at runtime, so the *executable* surface of the proxy can drift whenever Polars changes. The spec lags. This is a known gap.

**Drift scenarios and what each would do:**

| Scenario | Behavior under this design |
|---|---|
| Polars version bump adds a new Boolean-producing method (e.g. `is_in_range`) | **Correctly classified** — the lazy `_kind_from_dtype` fallback inspects the wrapped expression's output dtype. Boolean → `kind="boolean_mask"`. Method works correctly as a `when()` predicate. |
| Polars adds a new list-producing method we don't classify in `_NUMERIC_ELEMENTWISE` | **Misclassified** — proxy still reports correct `shape` (via dtype probe), but the method passes through to Polars without going through the plugin router. If the method needs shape-aware routing (e.g., a hypothetical `list_pow_signed`), it won't get it. Caller has to invoke the plugin directly via `polars_backend.plugins`. |
| Polars renames or removes a method we currently use | **Visible breakage** — proxy raises `AttributeError` at the `_autopatch` reflection point or at descriptor access. Easy to diagnose. |
| Polars changes the semantics of a method we autopatch (e.g. `cum_sum` changes null behavior) | **Silent semantic drift** — passes through, behavior changes invisibly. This is unavoidable without a manifest, and is the same risk gaspatchio runs today against any pinned Polars version. Mitigation: pinned Polars version in `pyproject.toml`; integration tests catch behavior changes on version bumps. |

**Why we accept this:**

Building an executable manifest (classify every `pl.Expr` method as `semantic` / `passthrough` / `forbidden`, fail CI on unclassified Polars deltas, generate the spec subsection from the manifest) is real and defensible work, but it has user-visible scope (effectively shrinking the proxy surface or requiring per-method Gaspatchio decisions on every Polars upgrade). It conflicts with the explicit `_autopatch` decision in this design (option γ — out of scope). The dtype-driven `kind` fallback covers the most common drift case (new Boolean-producing methods); the others are either visibly broken (rename/remove) or already exist as risks today (semantic drift on Polars upgrade).

**Follow-up ticket placeholder:** if drift becomes a recurring problem after this work ships, file a follow-up ticket: *"Replace the seam-coverage prose with an executable manifest; classify every `pl.Expr` method; fail CI on unclassified Polars deltas."* Out of scope for the current refactor.

When/if a future backend (JAX, NumPy, etc.) becomes a concrete project, this list of "what's covered" is what becomes portable. Everything else needs explicit work — either ported, removed, or marked Polars-only. That work is deferred.

## PR 1 — Chained vector `when()` via reverse-fold

**Touches:** `functions/conditional.py` (primary). No Rust changes. No new kernels.

### Strategy

Replace the single `if list_columns and len(self._conditions) > 1: NotImplementedError` block in `_build_scalar_conditional` with a per-case lowering loop driven by the proxy's metadata.

```
def lower_chain(cases, otherwise):
    acc = otherwise_expr
    for (condition, then_value) in reversed(cases):
        acc = lower_one_case(condition, then_value, acc)
    return acc
```

Reverse-fold guarantees first-match-wins semantics naturally.

### Per-case lowering rules

| Predicate flavor | Detection (PR 1) | Lowering |
|---|---|---|
| Scalar comparison | `ConditionExpression`, no condition operand is a list column | `pl.when(cond).then(then).otherwise(acc)` |
| Vector comparison | `ConditionExpression`, at least one operand is a list column | `list_conditional(cond.left, cond.right, then, acc, cond.operator)` |
| Vector boolean mask | `ExpressionProxy` with `_is_boolean_list = True` | `list_conditional(mask_expr, 1.0, then, acc, "eq")` |
| Pre-built `pl.Expr` | bare `pl.Expr` | `pl.when(cond).then(then).otherwise(acc)` |

### Path selection at the chain level (unified)

**All chains (`len(self._conditions) > 1`) lower via reverse-fold.** No scalar/list split.

- Single-`when()` (no chain, `len == 1`) keeps its existing path: `pl.when(cond).then(value).otherwise(otherwise_value)` for scalar predicates, or a single `list_conditional(...)` call for list predicates. There's no fold to do.
- Chained `when()` (any size ≥ 2) reverse-folds, applying the per-case lowering rules above to each `(condition, then)` pair from right to left.

**Why unified, not split.** The original draft of this design proposed a "conservative split" — scalar-only chains keep today's native `pl.when().then()...when().then().otherwise()` form, list-involved chains reverse-fold. That was rejected after adversarial review on the following grounds:

- The whole reason this refactor exists is that shape semantics fragmented across paths today. Preserving a split for chained `when()` lowering repeats the failure mode under a cleaner name.
- A user formula that is identical in DSL text would change behavior whenever an operand happens to be list-typed: result dtype, null handling, and coercion order can all differ between native `pl.when()` chained form and nested-otherwise form. That's a silent correctness hazard.
- "Polars planner may optimize chained `pl.when()` differently than nested" was an unmeasured concern. We measure it via the parity test below; if there's a real regression we revisit.

**Parity guarantee.** A scalar-only chain lowered via reverse-fold (nested `pl.when().then().otherwise(pl.when()...)`) must produce numerically and dtype-identical results to the same chain lowered as today's native `pl.when().then()...when().then().otherwise()`. This is enforced by an explicit parity test (see test matrix below). If parity holds, we ship the unified path. If it doesn't, we document the precise divergence and decide explicitly whether the new behavior is correct — but we do not silently keep two paths.

### Test matrix

Implements Cursor's full completeness matrix.

- **Chain sizes:** 1, 2, 3, 5 cases.
- **Predicate × branch shape:**

| Predicate | Then/else branches | Dependency |
|---|---|---|
| Scalar comparison | both scalar | input columns |
| Scalar comparison | mixed scalar / list | input columns |
| Scalar comparison | both list | input columns |
| Vector comparison | both scalar | input columns |
| Vector comparison | mixed scalar / list | input columns |
| Vector comparison | both list | input columns |
| Vector mask via `&` | mixed | input + computed scalar |
| Vector mask via `|` | mixed | input + computed list |
| Vector mask via `~` | both scalar | input columns |
| Mixed predicate flavors in one chain | mixed | input columns |

- **Mode parity:** every test runs in both `mode="debug"` and `mode="optimize"`, asserts identical results.
- **First-match-wins:** explicit overlap test where two cases match and the earlier wins.
- **Scalar-chain parity test (required, blocks PR 1 merge):** for every scalar-comparison chain at sizes 2, 3, 5, build the same chain twice — once via the new unified reverse-fold path, once via today's native `pl.when().then()...when().then().otherwise()`. Assert numerical equality of `.collect()` outputs and dtype equality of `.collect_schema()`. This proves the unified path is a strict semantic superset of today's behavior. If any test fails, document the divergence in PR 1's commit message before deciding whether to ship.
- **Null-handling matrix:** chain cases that include nulls in operands and branches. Assert behavior matches today's per-case-type semantics (native `pl.when()` for scalar predicates; `list_conditional` for vector predicates). Ensures nulls don't behave differently after reverse-fold.
- **Dedicated chained-conditional benchmark (required, blocks PR 1 merge):** new `bindings/python/tests/benchmarks/test_chained_when_bench.py` measuring scalar `when().then()...otherwise()` trees at chain sizes 2, 3, 5, 10. Compares unified reverse-fold against today's native `pl.when()` chained form. **`TestChainedWhenSlowdownGate` enforces a flat ≤ 50% slowdown at n=100_000** for chain sizes 2, 3, 5, 10. The 10K row case is excluded — at sub-millisecond native runtime the percentage is dominated by fixed Python construction overhead and is meaningless as a regression signal. Rationale: `realistic_vector_lookup` is dominated by lookup paths and would not reliably catch a conditional-planning regression; this benchmark targets the specific scenario where the unified path could regress without showing up in numerical or dtype parity tests.

  **Note (post PR 2):** the original design promised PR 2 would tighten this gate to ≤ 5% by deleting `ColumnTypeDetector` and routing through cached `condition.shape == "list"`. Measured outcome: PR 2 lands the architectural cleanup (detector deleted, mode parity invariant by construction) but the per-case shape probe via `_shape_from_expr_dtype` (`select(expr).collect_schema()`) is *more* expensive than the old name-keyed lookup against the cached `_schema`. Result: the gate stays at ≤ 50% through PR 2; tightening to ≤ 5% is a follow-up perf task (smart fast-paths or memoization) tracked separately. PR 2's correctness wins (single SOT, mode parity, regex/graph deletion) ship without depending on the perf delta.

### What's deleted

- The `len(self._conditions) > 1` guard in `_build_scalar_conditional` (lines 388-394).
- Existing xfail tests on chained vector `when()` are converted into passing tests, or replaced with precise tests for genuinely-unsupported behavior (e.g., mismatched inner-list lengths).

### What's deferred to PR 2

- The `_is_boolean_list` ducktype check stays in PR 1.
- The `ColumnTypeDetector` calls in `_any_condition_has_list_columns` stay in PR 1.
- These are mechanical follow-ups in PR 2; PR 1's tests remain green through PR 2.

### Risks

1. **Intermediate allocation (list chains).** N chained list cases produce N intermediate `List<Float64>` columns inside the Polars planner. Polars *should* fuse these; not currently verified for nested `list_conditional` calls. Mitigation: run `realistic_vector_lookup` and check for regression. If a regression appears at chain size 3-5, log it and decide whether a native `list_conditional_chained` Rust kernel is worth introducing later. Out of scope for this PR.
2. **Scalar chain construction overhead (DSL vs native).** Today's scalar-only chains compile to a single Polars `Function(when_then_else)` node. The unified reverse-fold path produces nested `When/Then/Otherwise` calls. Polars recognizes the nested form and optimizes the resulting plan equivalently, but the DSL still pays per-case shape-probe overhead during construction. Measured 16-21% slowdown in PR 1 (via `ColumnTypeDetector.is_list_column`) and 26-33% slowdown in PR 2 (via `_shape_from_expr_dtype`'s `select(expr).collect_schema()` plan validation). Mitigation:
   - **Numerical/dtype parity** — the scalar-chain parity test catches semantic regression.
   - **Flat slowdown gate** (`TestChainedWhenSlowdownGate`, n=100_000, ≤ 50%): the regression guard; the diagnostic `benchmark` fixtures emit per-config numbers but do not assert.
   - **Tightening to ≤ 5% is a follow-up perf task.** Possible directions: memoize shape probes by `(generation, expr_serialize)` so repeated `pl.col("x")`/`pl.lit(0)` patterns probe once per generation; specialize `resolve_shape` for plain `pl.col(name)` references via `_shape_from_schema(parent, name)` (cached schema lookup) when safe. Both are mechanical local changes that don't touch the architecture; the current 26-33% overhead is in chain *construction time only* — actual `.collect()` plans are equivalent to native, so production model wall-time at 1M+ rows is unaffected.
   - **Decision tree on regression past 50%:** fall back to split lowering — native `pl.when()` chained form for `all_scalar` chains, reverse-fold only for chains involving list columns. The semantic representation stays unified regardless.
3. **Type coercion across cases.** `list_conditional` output is `List<Float64>`. If a chain today would have produced `List<Int64>`, the new path produces `List<Float64>`. Verify in the test matrix; matches existing single-case behavior. For scalar-only chains, the unified path must preserve today's dtype inference — covered by the scalar-chain parity test.
4. **Mixing scalar and vector predicates in one chain.** A chain like `when(scalar_pred).then(...).when(vector_pred).then(...)` reverse-folds, lowering the scalar step via `pl.when().then().otherwise()` and the vector step via `list_conditional`. Result type is `List<Float64>`. Explicit test required.
5. **Null handling parity.** Native `pl.when()` and `list_conditional` may handle nulls differently in operands and branches. Mitigation: explicit null-handling matrix in the test suite (added above). If divergence is found, document and decide.

## PR 2 — Shape source-of-truth

**Touches:** `column/column_proxy.py`, `column/expression_proxy.py`, `column/condition_expression.py`, `column/dispatch.py`, `frame/base.py`, `functions/conditional.py`.

### Typed metadata on proxies and conditions

```python
Shape = Literal["scalar", "list", "unknown"]
Kind = Literal["value", "comparison", "boolean_mask", "unknown"]
```

| Class | `shape` resolution | `kind` resolution |
|---|---|---|
| `ColumnProxy` | property — reads `parent._schema[self.name]` on first access, caches | always `"value"` (literal class attribute, no resolution) |
| `ExpressionProxy` | property — resolves on first access via `resolve_shape(self._expr, parent)`, caches | property — explicitly set by constructors that know it (e.g. boolean mask combinators set `"boolean_mask"`); defaults to `"value"` |
| `ConditionExpression` | property — derives from operand shapes on first access, caches | always `"comparison"` (literal class attribute) |

**Stamping is lazy with caching.** `shape` is a `@property` on each class. First access calls the appropriate resolver; subsequent accesses return the cached value. This is deliberate, not a fallback:

- Proxy construction is reflective and decentralized (`GenericNamespaceProxy.__getattr__`, `_autopatch`'s `DelegatorDescriptor`, namespace adapters). An eager-stamping invariant would make every construction path correctness-critical and one missed site would silently drop metadata. Lazy resolution removes that risk class entirely.
- The "single source of truth" guarantee is about the *resolver*, not the *call site*. There is one `resolve_shape` function. Whether it's called at construction or at access doesn't change SOT.
- Cost is bounded: shape is queried at most once per proxy lifetime; subsequent lookups are an attribute read. For dispatch-heavy workloads that's the same cost profile as eager stamping after the first access.

**`kind` for `ExpressionProxy` is set explicitly by constructors that know it** (e.g. `condition_expression.py`'s `__and__` constructs an `ExpressionProxy` and passes `kind="boolean_mask"`). Constructors that don't pass a `kind` get the default `"value"`. There is no kind inference from the wrapped `pl.Expr` — kind is a frontend declaration, not something to be deduced from the expression tree.

### One resolver function

```python
# bindings/python/gaspatchio_core/column/shape.py (new)
def resolve_shape(value, parent) -> Shape:
    """The single source of shape truth. All callers route through here."""
    if isinstance(value, (ColumnProxy, ExpressionProxy, ConditionExpression)):
        return value.shape
    if isinstance(value, str):
        return _shape_from_schema(parent, value)
    if isinstance(value, pl.Expr):
        return _shape_from_expr_dtype(parent, value)
    if isinstance(value, (int, float, str, bool)):
        return "scalar"
    return "unknown"
```

`_shape_from_schema` reads `parent._schema` (the cached schema). `_shape_from_expr_dtype` is the existing dummy-frame probe — it stays as a fallback for `pl.Expr` inputs constructed without proxy context. The improvement is that the probe lives in *one* place instead of three.

### Property implementation — generation-aware caching

A naïve "resolve once, freeze forever" cache is unsafe because `ExpressionProxy` holds a live `self._parent` reference and the parent mutates `_df` in place on every assignment. A proxy reused across frame mutations could return shape resolved against an old schema state. Today's behavior re-resolves on every dispatch call (no caching at the proxy level); a frozen cache would be a regression.

**Solution: validate the cached value against a per-frame `_schema_generation` counter that increments on every `_df` mutation. Re-resolve on mismatch.**

```python
_UNSET = object()  # module-level sentinel

class ColumnProxy:
    def __init__(self, name, parent):
        self.name = name
        self._parent = parent
        self._shape_cached: tuple[int, Shape] | object = _UNSET

    @property
    def shape(self) -> Shape:
        gen = self._parent._schema_generation
        if self._shape_cached is _UNSET or self._shape_cached[0] != gen:
            self._shape_cached = (gen, resolve_shape(self.name, self._parent))
        return self._shape_cached[1]

    kind: ClassVar[Kind] = "value"


class ExpressionProxy:
    def __init__(self, expr, parent, *, kind: Kind | None = None):
        self._expr = expr
        self._parent = parent
        self._kind_explicit = kind  # None means "fall back to dtype probe"
        self._shape_cached: tuple[int, Shape] | object = _UNSET
        self._kind_cached: tuple[int, Kind] | object = _UNSET

    @property
    def shape(self) -> Shape:
        gen = self._parent._schema_generation if self._parent else 0
        if self._shape_cached is _UNSET or self._shape_cached[0] != gen:
            self._shape_cached = (gen, resolve_shape(self._expr, self._parent))
        return self._shape_cached[1]

    @property
    def kind(self) -> Kind:
        if self._kind_explicit is not None:
            return self._kind_explicit
        gen = self._parent._schema_generation if self._parent else 0
        if self._kind_cached is _UNSET or self._kind_cached[0] != gen:
            self._kind_cached = (gen, _kind_from_dtype(self._expr, self._parent))
        return self._kind_cached[1]


class ConditionExpression:
    def __init__(self, expr, parent, operator, left, right):
        self._expr = expr
        self._parent = parent
        self.operator = operator
        self.left = left
        self.right = right
        self._shape_cached: tuple[int, Shape] | object = _UNSET

    @property
    def shape(self) -> Shape:
        gen = self._parent._schema_generation if self._parent else 0
        if self._shape_cached is _UNSET or self._shape_cached[0] != gen:
            self._shape_cached = (gen, _max_shape(
                resolve_shape(self.left, self._parent),
                resolve_shape(self.right, self._parent),
            ))
        return self._shape_cached[1]

    kind: ClassVar[Kind] = "comparison"
```

The generation counter is a single integer on `ActuarialFrame`; the `_df` setter increments it (see "Cached schema" section below). Proxies use it to detect "the parent's schema changed since I last resolved" and re-resolve transparently. There is no manual invalidation required.

**Lifecycle properties:**
- A proxy used once (the common case in expression construction) does one resolve and caches the result.
- A proxy reused across N frame mutations does at most one resolve per mutation it survives — so reuse cost is bounded by mutations, not accesses.
- A proxy with `self._parent is None` (detached expression, rare) uses generation `0` and caches indefinitely.

### Kind resolution: explicit override + dtype-driven fallback

`kind` resolution has two layers:

**Layer 1 — explicit override.** Constructors that already know the kind pass it explicitly:

- `condition_expression.py::ConditionExpression.__and__` → constructs `ExpressionProxy(expr, parent, kind="boolean_mask")`. Replaces today's `result._is_boolean_list = True` ducktype assignment.
- `condition_expression.py::ConditionExpression.__or__` → same.
- `condition_expression.py::ConditionExpression.__invert__` → same.
- `condition_expression.py::ConditionExpression.__rand__` / `__ror__` → same.

These are the constructors whose result shape and intent are determined entirely by the operation that created them. `kind` is set at construction; subsequent property access returns the explicit value with no probe.

**Layer 2 — dtype-driven fallback.** Every other `ExpressionProxy` is constructed without an explicit `kind` (`kind=None`). On first access of `.kind`, the property runs `_kind_from_dtype(self._expr, self._parent)`:

```python
def _kind_from_dtype(expr: pl.Expr, parent) -> Kind:
    """Infer kind from the wrapped expression's output dtype.

    Boolean dtype (or List<Boolean>) → boolean_mask.
    Anything else → value.
    """
    try:
        if parent is not None and parent._df is not None:
            schema = parent._df.select(expr.alias("_t")).collect_schema()
            dtype = schema.get("_t")
            if dtype == pl.Boolean:
                return "boolean_mask"
            if isinstance(dtype, pl.List) and dtype.inner == pl.Boolean:
                return "boolean_mask"
    except Exception:
        pass
    return "value"
```

This catches predicate-producing methods that we don't classify in an explicit taxonomy: `is_null`, `is_nan`, `is_finite`, `is_in`, `is_unique`, `has_nulls`, etc. — including methods reflectively added by `_autopatch` from `dir(pl.Expr)`. Without this fallback, such methods would silently default to `kind="value"` and route incorrectly through chained `when()`.

**Why dtype-driven and not taxonomy-driven.** Building a static taxonomy of "predicate-producing methods" would require maintaining a registry that drifts every time Polars adds, renames, or changes a method's return type. The dtype probe is dynamic and self-correcting: whatever Polars says the output dtype is, that's what we classify against. The cost is one schema-inference call per proxy lifetime per generation — bounded.

**Tests required for this fallback** (PR 2 test suite):
- `af["x"].is_null()` for scalar `x` → `kind == "boolean_mask"`
- `af["x"].is_null()` for list `x` (via list-shim) → `kind == "boolean_mask"`
- `af["x"].is_in([1, 2, 3])` for scalar `x` → `kind == "boolean_mask"` (autopatched method, no taxonomy entry)
- `af["x"].is_in([1, 2, 3])` for list `x` → `kind == "boolean_mask"`
- `af["x"].abs()` → `kind == "value"`
- `af["x"] + af["y"]` → `kind == "value"`
- Chained `when()` using `is_null` as predicate routes through `list_conditional` for list operands and through scalar path for scalar operands.

### `_max_shape` semantics

```python
def _max_shape(a: Shape, b: Shape) -> Shape:
    if a == "unknown" or b == "unknown":
        return "unknown"
    if a == "list" or b == "list":
        return "list"
    return "scalar"
```

Combining `"list"` and `"scalar"` produces `"list"` (broadcast). Any `"unknown"` operand produces `"unknown"`. `"unknown"` is the "we genuinely couldn't resolve this" outcome — propagating it forces callers to handle the unresolved case explicitly rather than silently treating an unresolved expression as scalar or list.

### Cached schema, refreshed on mutation — mechanically enforced

Today `frame/base.py` has `self._schema` cached but `__setitem__` (lines 287-310) does `self._df = self._df.with_columns(...)` *without* updating it. That's why `ColumnTypeDetector` calls `collect_schema()` itself. The frame mutates `self._df` in many other places too: `add_columns`, `select`, `drop`, `rename`, `with_row_index`, `join`, `filter`, etc. (~14 known sites).

A procedural mitigation ("introduce a `_set_df(new_df)` helper and remember to call it") is too weak. A single missed mutation site silently leaves shape resolution returning stale results, which silently misroutes dispatch. The bug presents as wrong dispatch path, not as an exception. We need mechanical enforcement.

**Solution: convert `_df` to a `@property` with a setter that refreshes `_schema` and bumps `_schema_generation` automatically.**

```python
class ActuarialFrame:
    def __init__(self, ...):
        ...
        self._schema_generation: int = 0
        self._schema: pl.Schema = ...

    @property
    def _df(self) -> pl.LazyFrame:
        return self.__df

    @_df.setter
    def _df(self, new_df: pl.LazyFrame) -> None:
        self.__df = new_df
        self._schema = new_df.collect_schema()
        self._schema_generation += 1
```

Two invariants are enforced atomically by the setter:

1. `self._schema == self._df.collect_schema()` — the cached schema always reflects the current frame.
2. `self._schema_generation` increments on every mutation — proxies cache against this and re-resolve on mismatch (see "Property implementation" above).

Existing call sites (`self._df = self._df.with_columns(...)`, `self._df = self._df.select(...)`, etc.) **work unchanged** — Python's property setter mechanism intercepts the assignment automatically. No call site rewrites needed. Adding new mutation sites cannot bypass the refresh or the generation bump accidentally.

**CI/lint enforcement (defense in depth):** add a Ruff/AST rule that fails on direct writes to `self.__df` (the underlying private attribute) outside `frame/base.py`'s setter implementation. Direct private-attribute access is the only way to bypass the property; banning it ensures the invariant cannot rot.

**Tests required:**
- `tests/test_schema_invalidation.py` — for each known mutation method (`__setitem__`, `add_columns`, `select`, `drop`, `rename`, `filter`, `join`, etc.): assign or call the method, immediately read `parent._schema`, assert it matches `parent._df.collect_schema()`. Catches missed setters when new mutation methods are added.
- `tests/test_proxy_reuse_across_mutations.py` — construct a proxy, read its `.shape`, mutate the frame in a way that changes the column's shape (e.g., `af["x"] = af["x"].cast(pl.List(pl.Float64))`), read the proxy's `.shape` again, assert it returns the new resolved value. Verifies generation-based invalidation works on retained proxies.

`ColumnProxy.shape` reads `parent._schema[self.name]` directly. No more direct `collect_schema()` calls in dispatch — they all become `parent._schema[...]` lookups.

### What gets deleted

| Removed | Where | Reason |
|---|---|---|
| `ColumnTypeDetector` | `dispatch.py:433-547` | Replaced by `resolve_shape` + cached schema |
| `_expr_references_list_column` | `dispatch.py:550-558` | Regex on `pl.Expr.__repr__` is gone |
| `_is_list_in_graph` / `_is_list_in_schema` | `dispatch.py:478-501` | Folded into resolver |
| `is_expression_list_output` | `dispatch.py:503-531` | Folded into resolver |
| `if "list." in expr_str.lower()` | `dispatch.py:595` | String heuristic gone |
| `_unwrap_for_list_eval`'s `'col("' in expr_str` check | `dispatch.py:418-423` | Replaced with `if value.shape == "list"` |
| `ExpressionProxy._list_broadcast_metadata` | `expression_proxy.py:47`, `frame/base.py:287-299` | Already dead, never set |
| `_expr_to_str` and `isinstance(operation.expression, str)` in `collect()` | `frame/base.py:407-422, 508-512` | Dead scaffolding never filled |
| `_is_boolean_list` ducktype attribute | `condition_expression.py:200, 226, 252, 271, 294` and `conditional.py:412` | Replaced by `kind == "boolean_mask"` |
| Per-call `collect_schema()` in dispatch detection | various | Replaced by cached schema |

### Mode parity falls out

The existing `ColumnTypeDetector` queried both schema AND computation graph. In optimize mode the graph is empty; in debug mode it has entries. That asymmetry produced mode-dependent behavior. PR 2 reads schema only — the graph stays as a tracing/debugging aid, never queried for shape decisions. Result: shape detection produces identical answers in both modes by construction.

### Updates to PR 1's chained `when()` fix

Two mechanical follow-ups land in this PR:

```python
# Before (PR 1):
if isinstance(condition, ExpressionProxy) and getattr(condition, "_is_boolean_list", False):

# After (PR 2):
if isinstance(condition, ExpressionProxy) and condition.kind == "boolean_mask":
```

```python
# Before (PR 1):
detector = dispatch.ColumnTypeDetector(self._parent)
return any(detector.is_list_column(cn) for cn in col_names)

# After (PR 2):
return condition.shape == "list"
```

The PR 1 test matrix stays green. No behavior change.

### Risks

1. **`_shape_from_expr_dtype` and `_kind_from_dtype` (dummy-frame probes) still exist.** We are consolidating them into `resolve_shape` and `_kind_from_dtype`, not eliminating them. Needed for cases where an `ExpressionProxy` wraps a raw `pl.Expr` whose shape/kind isn't determinable from explicit metadata. The improvement is consolidation (one place per concern), not elimination.
2. **Cache invalidation correctness.** Generation-counter-based invalidation requires every `_df` mutation to bump the counter. The `@property` setter is the only mutation path; the lint rule banning direct writes to `__df` outside the setter ensures this. Failure mode would be a contributor mutating the underlying `pl.LazyFrame` in place without going through the property — Polars `LazyFrame` is effectively immutable in practice, so this is a low-probability failure. Documented assumption; one explicit test asserts proxy reuse across mutations works correctly.
3. **`_max_shape` semantics for `"unknown"`.** Defined above: any `"unknown"` operand produces `"unknown"`. Forces callers to handle the unresolved case explicitly. The implementation must match the spec exactly; covered by a unit test on `_max_shape` directly.
4. **Third-party code reading `_is_boolean_list`.** Grep the gaspatchio workspace (`gaspatchio-mix`, `gaspatchio-models`) before deleting. If found, expose `kind == "boolean_mask"` as the replacement and leave a deprecation alias on `ExpressionProxy` for one release. Document migration in PR 2's release notes.
5. **`_kind_from_dtype` cost.** First access of `.kind` on an `ExpressionProxy` constructed without explicit kind triggers a `parent._df.select(expr).collect_schema()` call. This is the same cost as today's per-call `ColumnTypeDetector.is_expression_list_output` — and it's cached per generation, so amortizes to zero for steady-state workloads. The `realistic_vector_lookup` benchmark (and the new `bench_when_chained_scalar`) catch any regression.
6. **`_kind_from_dtype` ambiguity.** What about expressions whose output dtype is `Boolean` but whose intent is *value* (e.g., `af["bool_flag_col"]` — a column literally containing booleans, not a predicate to be used as a `when()` condition)? With dtype-driven fallback, this would be classified as `kind="boolean_mask"` and could route through `list_conditional`-style paths inappropriately. Mitigation: in practice, Boolean-typed input columns are rare; tests should cover this case explicitly. If it becomes a real problem, the explicit-kind override always takes precedence — the constructor that knows the value is a column-of-booleans-not-a-predicate can pass `kind="value"`.
7. **Generation-counter integer overflow.** `_schema_generation` is a Python `int` — unbounded. No overflow risk.

## PR 3 — Polars plugin router extraction

**Touches:** `column/dispatch.py`, `column/condition_expression.py`, `functions/vector.py`, `functions/conditional.py`, plus a new `polars_backend/` subpackage. No new behavior; pure relocation + interface tightening.

### Split rule

Language semantics stay in the frontend. Polars implementation details move to `polars_backend/`.

| Thing | Today | After PR 3 |
|---|---|---|
| `_NUMERIC_UNARY`, `_NUMERIC_ELEMENTWISE`, `_NAMESPACES` | `dispatch.py` | stays — operation taxonomy is language semantics |
| `DelegatorDescriptor`, `_make_wrapper`, `_wrap`, `_unwrap`, `_unwrap_for_arithmetic` | `dispatch.py` | stays — proxy delegation is frontend |
| `ErrorEnhancer` | `dispatch.py` | stays — proxy-context error enhancement |
| `_autopatch` | `dispatch.py` | stays (out of scope, see Decisions table above) |
| `_execute_list_pow_plugin` (incl. scalar^list exp/log identity) | `dispatch.py` | → `polars_backend/operators.py` |
| `_execute_list_clip_plugin` | `dispatch.py` | → `polars_backend/operators.py` |
| pow-arg-is-list detection | `dispatch.py:813-820` | → `polars_backend/operators.py` (folded into `execute_list_pow`) |
| `_unwrap_for_list_eval` | `dispatch.py:399-427` | → `polars_backend/list_eval.py` (Polars-specific concept) |
| Boolean-mask arithmetic (`__and__`, `__or__`, `__invert__` bodies) | `condition_expression.py` | → `polars_backend/masks.py`. Operator overload methods stay in `condition_expression.py` and call into `masks.py`. |
| `_to_boolean_expr` body | `condition_expression.py` | → `polars_backend/masks.py` |
| Plugin wrapper functions (`list_pow`, `list_clip`, `list_conditional`, `accumulate`, `fill_series`, `floor`, `round`, `round_to_int`, `rollforward_plugin`) | `functions/vector.py` | → `polars_backend/plugins.py`. `functions/vector.py` becomes a thin re-export so `from gaspatchio_core.functions.vector import accumulate` still works. |
| Duplicated proxy-unwrap pattern in 4 plugin wrappers | `functions/vector.py` | one helper in `polars_backend/plugins.py` |
| Conditional reverse-fold lowering | `functions/conditional.py` | stays in `conditional.py`. Optionally move per-step lowering rules into `polars_backend/conditional.py` if it makes the conditional builder cleaner — judgment call during implementation. |

### New directory

```
bindings/python/gaspatchio_core/
└── polars_backend/
    ├── __init__.py        # re-exports public surface
    ├── plugins.py         # all register_plugin_function wrappers
    ├── operators.py       # execute_list_pow, execute_list_clip
    ├── masks.py           # boolean_and, boolean_or, boolean_not, to_boolean_expr
    └── list_eval.py       # unwrap_for_list_eval and list.eval restrictions
```

Sibling of `column/`, `frame/`, `functions/`, `accessors/`.

### `_method_caller` after PR 3

```python
def _method_caller(*, name, polars_attr, self_proxy, parent_af, base_expr, a, kw):
    if name in _ARITHMETIC_OPS:
        a = tuple(_unwrap_for_arithmetic(arg) for arg in a)
        kw = {k: _unwrap_for_arithmetic(v) for k, v in kw.items()}

    is_list_op = self_proxy.shape == "list" or _any_list_arg(a, kw)

    error_enhancer = ErrorEnhancer(self_proxy)
    try:
        if is_list_op and name in _BACKEND_LIST_OPS:
            result = polars_backend.dispatch_list_op(name, base_expr, a, kw)
        elif is_list_op and name in _NUMERIC_UNARY | _NUMERIC_ELEMENTWISE:
            result = _execute_list_shim(name, base_expr, a, kw, is_unary=...)
        else:
            result = _execute_regular(polars_attr, a, kw)
    except Exception as e:
        raise error_enhancer.enhance_method_error(e, name) from e

    return _wrap(parent_af, result)
```

`_BACKEND_LIST_OPS = {"pow", "clip"}` is the registry of operations with a backend-specific list path. `polars_backend.dispatch_list_op(name, ...)` routes internally to `execute_list_pow` or `execute_list_clip`.

### `condition_expression.py` after PR 3

```python
class ConditionExpression:
    def __init__(self, expr, parent, operator, left, right): ...

    def __and__(self, other):
        from gaspatchio_core.polars_backend import masks
        result_expr = masks.boolean_and(self, other, parent=self._parent)
        return ExpressionProxy(result_expr, self._parent, kind="boolean_mask")

    def __or__(self, other):
        from gaspatchio_core.polars_backend import masks
        result_expr = masks.boolean_or(self, other, parent=self._parent)
        return ExpressionProxy(result_expr, self._parent, kind="boolean_mask")

    def __invert__(self):
        from gaspatchio_core.polars_backend import masks
        return ExpressionProxy(masks.boolean_not(self), self._parent, kind="boolean_mask")
```

The frontend declares "an AND of two conditions produces a boolean-mask `ExpressionProxy`." The arithmetic implementation (`left * right` for AND, `1 - (1-a)*(1-b)` for OR, etc.) is a backend choice the frontend doesn't know about.

### Public API impact

- `from gaspatchio_core.functions.vector import accumulate` — works, re-exported.
- `from gaspatchio_core.functions.vector import list_pow` — works, re-exported.
- `from gaspatchio_core.column.dispatch import ColumnTypeDetector` — already deleted in PR 2.
- Internal helper imports (`_execute_list_pow_plugin`, `_unwrap_for_list_eval`, etc.) — these are SLF-prefixed and treated as private. Anyone reaching into them was on their own.

### Risks

1. **Circular imports.** `condition_expression.py` will import from `polars_backend.masks`. `polars_backend.masks` will import from `polars_backend.plugins` for `list_conditional`. None of `polars_backend/` should import from `column/`. Mitigation: enforce by code review; the directory structure makes accidental cycles obvious.
2. **`from gaspatchio_core.functions.vector import ...` performance.** Re-export adds an extra import step. Negligible — Python imports are cached.
3. **`_BACKEND_LIST_OPS` registry drift.** Today, `pow` and `clip` are inline. With a registry, adding a new backend-specific op requires touching both the taxonomy and the registry. Mitigation: small set today (2 entries). If it grows, introduce a decorator-based registration mechanism.
4. **Tests that import internals.** Any test importing `_execute_list_pow_plugin` directly will need to update its import path. Search-and-replace; covered in the PR.
5. **The "scalar^list" exp/log identity** has subtle correctness branches (`base > 0` / `base == 0` / `base < 0`). Moving it shouldn't change behavior, but currently it's only covered by integration tests in higher-level model code. Add explicit unit tests for each branch when the function moves.

## Validation, performance, cross-PR risks

### Validation strategy

**PR 1.**
- New tests in `tests/test_conditional.py` (or `tests/test_conditional_chained_lists.py`) implementing the full Cursor matrix above.
- Every test runs in both `mode="debug"` and `mode="optimize"`, asserts identical results.
- Existing xfails on chained vector `when()` either pass or are replaced with precise tests for genuinely-unsupported behavior.
- All pre-existing `test_conditional` tests stay green.

**PR 2.**
- All PR 1 tests still pass (the `_is_boolean_list` → `kind == "boolean_mask"` migration is mechanical).
- `tests/test_resolve_shape.py` covering each input type to `resolve_shape` (proxy types, str, `pl.Expr`, scalar literal, unknown).
- `tests/test_kind_from_dtype.py` covering the dtype-driven fallback: `is_null` / `is_nan` / `is_in` / `is_unique` / `has_nulls` produce `kind="boolean_mask"`; arithmetic ops produce `kind="value"`. Cover both scalar and list variants.
- `tests/test_schema_invalidation.py` (mentioned earlier) — for each known frame mutation method, assert `_schema == _df.collect_schema()` afterward. Plus assert `_schema_generation` increments by 1.
- `tests/test_proxy_reuse_across_mutations.py` — construct a proxy, read `.shape`, mutate the frame, read `.shape` again, assert it returns the new resolved value. Verifies generation-based invalidation works on retained proxies. Cover multiple mutation methods (`__setitem__`, `add_columns`, `select`, `drop`, `rename`).
- Mode parity smoke test: a model exercising mixed scalar/list dispatch, debug vs optimize outputs compared at the column level. Single most useful regression test for "shape detection produces consistent answers."
- Targeted dead-code test: assert `ColumnTypeDetector` no longer importable; `_expr_references_list_column`, `_list_broadcast_metadata`, `_expr_to_str` gone.

**PR 3.**
- All PR 1 + PR 2 tests still pass.
- Targeted unit tests for each function moved to `polars_backend/`, especially the "scalar^list" exp/log identity branches.
- Public API import test: `from gaspatchio_core.functions.vector import list_pow, list_clip, list_conditional, accumulate` still work.
- Boolean-mask arithmetic regression tests: `__and__`, `__or__`, `__invert__` produce identical `pl.Expr` to today.

### Performance budget

**Single rule: don't regress the `realistic_vector_lookup` benchmark in `gaspatchio-core/core/benches/`.** Authoritative per `core/project.md`.

Per-PR concerns:

- **PR 1.** Reverse-folded chained `list_conditional` calls produce N intermediate `List<Float64>` columns. Polars *should* fuse these in the streaming engine; verify by running the benchmark with a chained-when() model variant against a single-when() baseline. If a measurable regression appears at chain size 3-5, document it but do not preemptively introduce a native `list_conditional_chained` Rust kernel.
- **PR 2.** Cached-schema reads should be cheaper than today's per-call `collect_schema()` invocations. Expected: small improvement or no change.
- **PR 3.** Pure relocation. Function-call overhead is one extra Python call per dispatch — negligible.

If any PR shows >5% regression on the benchmark, stop and investigate before merging.

### Cross-PR risks

1. **Sequencing dependency.** PR 2 includes mechanical follow-ups to PR 1's code. If PR 1 lands and PR 2 is deferred indefinitely, the codebase carries the duck-typed flag plus a partial source of truth. Mitigation: keep all three PRs in flight as a series.
2. **Schema cache invariant.** PR 2 makes `_df` a `@property` whose setter refreshes `_schema`, plus a lint rule banning direct writes to `__df` outside the setter, plus a test that asserts `_schema == _df.collect_schema()` after every known mutation method. The invariant is mechanically enforced; the remaining risk is a contributor finds a way to bypass the property (e.g. via Polars internals mutating the frame in place). Polars `LazyFrame` is effectively immutable in practice; risk is low.
3. **`polars_backend/` import discipline.** PR 3 introduces "no `polars_backend/` file imports from `column/`." If broken, circular imports or sneaky frontend leakage. Mitigation: code review.
4. **Downstream consumers reading internals.** Anyone in `gaspatchio-models`, `gaspatchio-mix`, or third-party code reading `_is_boolean_list`, `_list_broadcast_metadata`, `ColumnTypeDetector`, `_execute_list_pow_plugin` directly will break. Mitigation: grep the workspace before each PR; deprecation aliases for one release if any consumer is found.
5. **Documentation drift.** PR 1 specifically should add a docs example showing chained vector `when()`. Each PR's checklist includes "search `gaspatchio-docs` for relevant references."

### Rollback story

Each PR is independently revertible:
- PR 1 revert: chained vector `when()` returns to raising `NotImplementedError`. Users go back to nested `.otherwise(when(...))`.
- PR 2 revert: re-introduces `ColumnTypeDetector`, regex heuristics, scattered shape paths. Painful but possible.
- PR 3 revert: `polars_backend/` collapses back into `dispatch.py` and `condition_expression.py`. Public API imports keep working.

Each PR sits on a separate branch off `develop`, gets reviewed, lands. If one is reverted, the next rebases.

### Stop criteria

- After PR 1: GSP-87 closed. Chained-when matrix passes in both modes. Benchmark not regressed. → ship.
- After PR 2: `ColumnTypeDetector` and the regex heuristic deleted. Mode parity smoke test passes. Benchmark not regressed. → ship.
- After PR 3: `dispatch.py` roughly halved. `condition_expression.py` is a thin frontend. `polars_backend/` exists. Benchmark not regressed. → ship. Done with this work.

If any PR fails its stop criterion, hold the next one until the failure is understood.

## What this design explicitly does not do

The Cursor draft (`cursor/dispatch-refactor-design-76e5`) proposes a semantic IR + backend lowering boundary motivated by future JAX/NumPy/Mojo backends. That proposal is rejected for this scope:

- **No `ExprNode` / `ResolvedNode`.** The proxies and `ConditionExpression` already carry the metadata an IR would carry. Promoting `shape` and `kind` into typed fields completes that. A parallel IR alongside the proxies would be redundant.
- **No `Backend` interface, no `LoweredExpr`.** Without a concrete second backend forcing the abstraction, the abstraction would be shaped exactly like Polars. Cursor's own Risk 1 ("fake portability") flags this.
- **No surface-area shrink.** `_autopatch` stays. The proxy honestly advertises the full Polars `Expr` surface; we don't pretend a portable subset that hasn't been built.

When JAX (or any second backend) becomes a concrete project, the seams left by this work — single shape resolver, plugin router behind a function interface, no Polars types in `dispatch.py`'s public surface — make a future IR/backend split a tractable next step. Not a free one. Honest.

## References

- GSP-87 — Support chained `.when()` on list columns
- GSP-95 — Dispatch / broadcasting refactor proposal (Linear)
- `cursor/dispatch-refactor-design-76e5` — Cursor's draft proposal (input, not adopted wholesale)
- `bindings/python/gaspatchio_core/column/dispatch.py` — primary refactor target
- `bindings/python/gaspatchio_core/functions/conditional.py` — primary site of GSP-87 fix
- `bindings/python/gaspatchio_core/column/condition_expression.py` — boolean-mask logic
- `bindings/python/gaspatchio_core/functions/vector.py` — plugin wrappers
- `core/src/polars_functions/list_conditional.rs` — kernel that already supports the required shape combinations
- `core/project.md` — Polars plugin guidelines, `realistic_vector_lookup` as authoritative benchmark
