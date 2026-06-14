# Design Document: Rust Plugins for List Operations Performance

**Status**: Approved
**Date**: 2025-11-11
**Authors:** Matt Wright, Claude
**Issue**: GSP-8 - Performance bottleneck in discount_factor() and conditionals at scale

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Plugin 1: list_pow](#plugin-1-list_pow)
3. [Plugin 2: list_conditional](#plugin-2-list_conditional)
4. [Plugin Architecture Details](#plugin-architecture-details)
5. [Implementation Plan](#implementation-plan)
6. [Success Metrics](#success-metrics)

---

## Architecture Overview

### Problem Statement

Element-wise operations on two list columns cause severe performance bottlenecks in actuarial projections. At 1,000 model points, EXPLODE/GROUP_BY operations consume 95.4% of execution time (5.93ms). At 10,000 points, the system hangs with 55GB memory usage.

### Root Cause

Polars lacks native support for:

1. **Power operations on list columns** (`list ** list`) - [Polars Issue #19349](https://github.com/pola-rs/polars/issues/19349)
2. **Element-wise conditionals** requiring list broadcasting in `when().then().otherwise()`

Current workaround uses EXPLODE/GROUP_BY pattern:
- Explodes 1,000 rows × 240 periods = 240,000 intermediate rows per operation
- 7 operations = ~1.68M total row operations
- At 10K scale: ~16.8M row operations causing memory bloat

### Solution Architecture

Build two specialized Rust plugins using pyo3-polars:

1. **`list_pow`** - Element-wise power operations `base ** exp`
2. **`list_conditional`** - Element-wise when/then/otherwise with comparison

These plugins operate directly on list inner values without exploding to rows, eliminating the performance bottleneck.

### Expected Performance Impact

- Eliminates 69.9% of current EXPLODE/GROUP_BY time
- `discount_factor`: 22.6% → near-zero (50-100x faster)
- 4 conditionals: 47.3% → near-zero (50-100x faster)
- Memory: 553MB at 1K → ~100MB (5x reduction)
- Unlocks 10K+ scale processing (currently hangs)

### Performance Breakdown from Profiling

**Current bottleneck (1,000 model points, 6.21ms total):**

| Operation | Time (ms) | % of Total | Source |
|-----------|----------|------------|--------|
| discount_factor EXPLODE | 1.41 | 22.6% | finance.py:157-162 |
| maturity_when EXPLODE | 1.12 | 18.1% | model:112-114 |
| pols_if_when EXPLODE | 0.70 | 11.3% | model:119-123 |
| acq_expense_when EXPLODE | 0.70 | 11.3% | model:209 |
| commissions_when EXPLODE | 0.41 | 6.6% | model:224 |
| **EXPLODE subtotal** | **4.42** | **71.1%** | |
| **GROUP_BY subtotal** | **1.51** | **24.3%** | |
| **Combined bottleneck** | **5.93** | **95.4%** | |

---

## Plugin 1: list_pow

### Plugin Purpose

Implement element-wise power operation `base ** exp` for list columns, mirroring how Polars implements `list * list`, `list / list`, etc.

### Rust Implementation Pattern

Following the Polars plugin example pattern:

```rust
#[polars_expr(output_type_func=pow_output)]
fn list_pow(inputs: &[Series]) -> PolarsResult<Series>
```

### Key Design Decisions

1. **Type Handling**: Always promote to Float64 (matches Polars pow behavior)
2. **Broadcasting Support**:
   - `list ** list` (pairwise, same lengths per row)
   - `list ** scalar` (broadcast scalar to all elements)
3. **Null Handling**: Preserve nulls in either operand
4. **Length Validation**: Error on mismatched inner list lengths

### Core Algorithm

```rust
// For list ** list case
let result: ListChunked = unsafe {
    lhs_list.zip_and_apply_amortized_same_type(&rhs_list, |lhs_inner, rhs_inner| {
        match (lhs_inner, rhs_inner) {
            (Some(lhs_series), Some(rhs_series)) => {
                // Cast to Float64
                let l = lhs_series.cast(&DataType::Float64)?;
                let r = rhs_series.cast(&DataType::Float64)?;

                // Element-wise pow
                let l_ca = l.f64().unwrap();
                let r_ca = r.f64().unwrap();

                let out: Vec<Option<f64>> = l_ca.iter()
                    .zip(r_ca.iter())
                    .map(|(a, b)| match (a, b) {
                        (Some(base), Some(exp)) => Some(base.powf(exp)),
                        _ => None,
                    })
                    .collect();

                Ok(Float64Chunked::from_iter(out).into_series())
            }
            _ => Ok(Series::new_empty("", &DataType::Float64)),
        }
    })?
};
```

- Use `zip_and_apply_amortized_same_type()` for list-list case
- Use `apply_amortized()` for list-scalar case
- Element-wise `powf()` on Float64 values
- No EXPLODE/GROUP_BY - operates directly on Arrow child arrays

### Python Wrapper in finance.py

```python
# Internal use - not exposed to actuaries
from gaspatchio_core.functions.vector import list_pow

def discount_factor(self, rate_col, periods_col, output_col, method="spot"):
    if method == "spot":
        # Prepare inputs with native Polars (fast SIMD ops)
        rate_plus_one = pl.col(rate_col) + 1.0
        period_neg = pl.col(periods_col) * -1.0

        # Call Rust plugin (eliminates EXPLODE)
        discount_expr = list_pow(rate_plus_one, period_neg).alias(output_col)

        result = self._frame._df.with_columns([discount_expr])
        return ActuarialFrame(result)
```

### Actuaries Still See

```python
# Clean domain API unchanged
af = af.finance.discount_factor(
    rate_col="disc_rate_mth",
    periods_col="month",
    output_col="disc_factors",
    method="spot"
)
```

---

## Plugin 2: list_conditional

### Plugin Purpose

Implement element-wise conditional operations with comparison built-in, eliminating EXPLODE for `when().then().otherwise()` patterns on list columns.

### Operations to Support

From the profiling, we need to handle these 4 conditional patterns:

1. `when(month == policy_term * 12)` - equality comparison (18.1%)
2. `when(month < policy_term * 12)` - less than comparison (11.3%)
3. `when(month == 0)` - equality with scalar (11.3%)
4. `when(duration == 0)` - equality with scalar (6.6%)

### Rust Implementation Signature

```rust
#[polars_expr(output_type_func=conditional_output)]
fn list_conditional(inputs: &[Series], kwargs: ConditionalKwargs) -> PolarsResult<Series>
```

### ConditionalKwargs Structure

```rust
#[derive(Deserialize)]
pub struct ConditionalKwargs {
    pub operator: String,  // "eq", "lt", "gt", "lte", "gte", "ne"
}
```

### Input Structure

```rust
// inputs[0]: left_col (list column for comparison)
// inputs[1]: right_col (list or scalar for comparison)
// inputs[2]: then_col (list or scalar - value when true)
// inputs[3]: otherwise_col (list or scalar - value when false)
```

### Core Algorithm

1. Compare `left[i] op right[i]` → boolean result
2. Select: `if bool_result { then[i] } else { otherwise[i] }`
3. Handle broadcasting for scalar inputs
4. Use `zip_and_apply_amortized_same_type()` pattern from list_pow

**Comparison Logic:**

```rust
fn compare(left: f64, right: f64, op: &str) -> bool {
    match op {
        "eq" => left == right,
        "ne" => left != right,
        "lt" => left < right,
        "lte" => left <= right,
        "gt" => left > right,
        "gte" => left >= right,
        _ => panic!("Unknown operator: {}", op),
    }
}
```

**Selection Logic:**

```rust
let result = if compare(left_val, right_val, &kwargs.operator) {
    then_val
} else {
    otherwise_val
};
```

### Python Wrapper in conditional.py

The `when().then().otherwise()` API stays unchanged for actuaries, but internally:

```python
# In ConditionalProxy.otherwise() method
def otherwise(self, value):
    # Detect list columns
    if self._list_columns:
        # Extract comparison details from condition expression
        left_col, right_col, operator = self._extract_comparison(self._conditions[0])

        # Build expression using Rust plugin
        from gaspatchio_core.functions.vector import list_conditional

        expr = list_conditional(
            left=left_col,
            right=right_col,
            then_val=self._values[0],
            else_val=value,
            operator=operator
        )
        return ExpressionProxy(expr, self._parent)
```

### Actuaries Still See

```python
# Clean conditional API unchanged
af.pols_maturity = (
    when(af.month == af.policy_term * 12)
    .then(af.surviving_at_t)
    .otherwise(0.0)
)
```

---

## Plugin Architecture Details

### Two-Layer Architecture

Following the existing Gaspatchio structure with clean separation:

**Layer 1: Pure Rust Core** (`gaspatchio-core/core/`)

```
core/
├── src/
│   ├── polars_functions/
│   │   ├── mod.rs              # Re-exports
│   │   ├── vector.rs           # Existing fill_series
│   │   ├── list_pow.rs         # NEW: Pure Rust list_pow
│   │   └── list_conditional.rs # NEW: Pure Rust list_conditional
│   └── lib.rs                  # Public API
├── benches/
│   ├── list_pow.rs             # NEW: Criterion benchmarks
│   └── list_conditional.rs     # NEW: Criterion benchmarks
└── Cargo.toml                  # No Python dependencies
```

**Layer 2: PyO3 Bindings** (`gaspatchio-core/bindings/python/src/`)

```
src/
├── lib.rs                      # PyO3 module registration
├── vector.rs                   # PyO3 expression wrappers
│   # Add #[polars_expr] wrappers for:
│   #   - list_pow
│   #   - list_conditional
├── assumptions.rs              # Existing
└── excel/                      # Existing
```

### Why This Matters

1. **Core Rust is Python-agnostic**: Can be used by other Rust projects
2. **PyO3 layer is thin**: Just wraps core functions with `#[polars_expr]`
3. **Testing separation**: Core Rust tests don't need Python
4. **Clear boundaries**: Business logic in core, Python integration in bindings

### Implementation Pattern

Following the existing `fill_series` pattern:

```rust
// core/src/polars_functions/list_pow.rs
// Pure Rust implementation
pub fn list_pow(inputs: &[Series]) -> PolarsResult<Series> {
    // Full implementation here
}

// bindings/python/src/vector.rs
// PyO3 wrapper
fn pow_output(fields: &[Field]) -> PolarsResult<Field> {
    // Output type logic
}

#[polars_expr(output_type_func = pow_output)]
pub fn list_pow(inputs: &[Series]) -> PolarsResult<Series> {
    gaspatchio_core_lib::polars_functions::vector::list_pow(inputs)
}
```

### Reference Implementation

Based on Polars' list arithmetic implementation pattern:

**Polars list arithmetic (for reference):**
- Entry point: `NumOpsDispatchInner` for `ListType`
- Operators: `add_to`, `sub_to`, `mul_to`, `div_to`, `rem_to`, `floordiv_to`
- Kernels: `ArithmeticKernel::wrapping_*` for each operation
- Broadcasting: Scalar and list-vs-list supported
- Type promotion: Division promotes to float

**Our plugins mirror this pattern:**
- Use same `zip_and_apply_amortized_same_type()` approach
- Handle broadcasting for scalar operands
- Type promotion to Float64 for pow
- Preserve null handling semantics

---

## Implementation Plan

### Phase 1: list_pow Plugin (Week 1)

**Goal**: Solve the single biggest bottleneck (22.6%)

**Tasks:**

1. Create `core/src/polars_functions/list_pow.rs` with pure Rust implementation
2. Add PyO3 wrapper in `bindings/python/src/vector.rs`
3. Update `core/src/polars_functions/mod.rs` to export list_pow
4. Update `bindings/python/src/lib.rs` to register plugin
5. **Write Rust benchmarks in `core/benches/list_pow.rs`** using Criterion:
   - Benchmark list**list at various sizes (100, 1K, 10K elements)
   - Benchmark list**scalar broadcasting
   - Compare vs EXPLODE/GROUP_BY baseline
6. Write Rust unit tests in core
7. Modify `finance.py::discount_factor()` to use list_pow
8. Write Python integration tests
9. Profile and compare: expect 1.41ms → <0.1ms (14x speedup)

**Acceptance Criteria:**

- ✅ Rust tests pass for list**list and list**scalar
- ✅ **Rust benchmarks show >10x speedup vs EXPLODE baseline**
- ✅ `discount_factor()` executes without EXPLODE operations
- ✅ Profiler shows EXPLODE count reduced from 7 → 6
- ✅ Performance: 22.6% time reclaimed (6.21ms → 4.8ms at 1K points)
- ✅ No regressions in numerical accuracy

### Phase 2: list_conditional Plugin (Week 2)

**Goal**: Solve the 4 conditional operations (47.3%)

**Tasks:**

1. Create `core/src/polars_functions/list_conditional.rs`
2. Add PyO3 wrapper in `bindings/python/src/vector.rs`
3. Update module exports
4. **Write Rust benchmarks in `core/benches/list_conditional.rs`**:
   - Benchmark each operator (eq, lt, gt, etc.)
   - Benchmark list-list vs list-scalar comparisons
   - Benchmark then/otherwise value selection performance
   - Compare vs EXPLODE/GROUP_BY baseline
5. Write Rust unit tests for all 6 operators (eq, lt, gt, lte, gte, ne)
6. Modify `conditional.py::ConditionalProxy.otherwise()` to detect list columns and use plugin
7. Write Python integration tests for each conditional pattern
8. Profile and compare: expect 2.94ms → <0.2ms (15x speedup)

**Acceptance Criteria:**

- ✅ All 6 comparison operators work correctly
- ✅ **Rust benchmarks confirm >10x speedup per operation**
- ✅ 4 model conditionals execute without EXPLODE
- ✅ Profiler shows EXPLODE count reduced from 6 → 2
- ✅ Performance: 47.3% time reclaimed (4.8ms → 1.9ms at 1K points)
- ✅ Conditional broadcasting works (scalar and list combinations)

### Phase 3: Scale Testing & Optimization (Week 3)

**Goal**: Validate at production scale (10K+ points)

**Tasks:**

1. Run profiler at 10K points (currently hangs)
2. **Run Rust benchmarks at scale (10K, 100K elements)**
3. Benchmark memory usage (target: <10GB at 10K)
4. Test at 100K points (stretch goal)
5. Performance regression tests
6. **Add benchmark CI checks** (fail if performance regresses >10%)
7. Documentation updates

**Acceptance Criteria:**

- ✅ 10K points complete in <5 seconds (vs current timeout)
- ✅ Memory usage ≤ 10GB at 10K points (vs 55GB)
- ✅ **Criterion benchmarks show consistent performance at scale**
- ✅ 95% EXPLODE/GROUP_BY time eliminated
- ✅ Integration tests pass at scale

### Benchmark Structure

```rust
// core/benches/list_pow.rs
use criterion::{criterion_group, criterion_main, Criterion, BenchmarkId};
use polars::prelude::*;
use gaspatchio_core_lib::polars_functions::vector::list_pow;

fn bench_list_pow(c: &mut Criterion) {
    let mut group = c.benchmark_group("list_pow");

    for size in [100, 1_000, 10_000] {
        group.bench_with_input(
            BenchmarkId::new("list_pow_list_list", size),
            &size,
            |b, &size| {
                // Setup: Create two list columns of `size` rows, 240 elements each
                let base_data: Vec<Vec<f64>> = (0..size)
                    .map(|_| (0..240).map(|i| i as f64 * 0.004).collect())
                    .collect();
                let exp_data: Vec<Vec<f64>> = (0..size)
                    .map(|_| (0..240).map(|i| -(i as f64)).collect())
                    .collect();

                let base_series = Series::new("base", base_data);
                let exp_series = Series::new("exp", exp_data);

                b.iter(|| {
                    list_pow(&[base_series.clone(), exp_series.clone()]).unwrap()
                });
            }
        );

        group.bench_with_input(
            BenchmarkId::new("list_pow_list_scalar", size),
            &size,
            |b, &size| {
                let base_data: Vec<Vec<f64>> = (0..size)
                    .map(|_| (0..240).map(|i| i as f64 * 0.004).collect())
                    .collect();
                let base_series = Series::new("base", base_data);
                let exp_series = Series::new("exp", vec![-2.0; size]);

                b.iter(|| {
                    list_pow(&[base_series.clone(), exp_series.clone()]).unwrap()
                });
            }
        );
    }

    group.finish();
}

criterion_group!(benches, bench_list_pow);
criterion_main!(benches);
```

---

## Success Metrics

### Performance Targets

| Metric | Current (1K) | Target (1K) | Target (10K) |
|--------|--------------|-------------|--------------|
| Total execution time | 6.21 ms | <2 ms | <50 ms |
| EXPLODE operations | 7 ops, 4.42 ms (71%) | 2 ops, <0.5 ms (<25%) | 2 ops, <5 ms |
| GROUP_BY operations | 7 ops, 1.51 ms (24%) | 2 ops, <0.3 ms (<15%) | 2 ops, <3 ms |
| Memory usage | 553 MB | <150 MB | <10 GB |
| Bottleneck % | 95.4% | <40% | <40% |

### Phase-by-Phase Improvements

**After Phase 1 (list_pow only):**
- Execution: 6.21ms → 4.8ms (23% faster)
- EXPLODE: 7 ops → 6 ops
- Memory: 553MB → 450MB

**After Phase 2 (list_pow + list_conditional):**
- Execution: 4.8ms → 1.9ms (69% faster vs baseline)
- EXPLODE: 6 ops → 2 ops (71% reduction)
- Memory: 450MB → 150MB

**After Phase 3 (scale validation):**
- 10K points: Timeout/55GB → <5s/<10GB
- 100K points: Impossible → <50s/<100GB

### Risk Mitigation

1. **Numerical accuracy**: Comprehensive reconciliation tests against current implementation
2. **Edge cases**: Null handling, empty lists, mismatched lengths
3. **Type compatibility**: Ensure Float64 promotion matches Polars behavior
4. **Performance regression**: Criterion benchmarks in CI with tolerance thresholds
5. **Backward compatibility**: Actuaries see no API changes

### Documentation Deliverables

1. **Design doc** in `ref/24-list-pow-list-performance/24-list-pow-list-performance-design.md` ✓
2. **Rust API docs**: Inline documentation for both plugins
3. **Performance report**: Before/after profiling with charts
4. **Migration guide**: Internal - how other operations could use plugins

### Next Steps After Design Approval

1. ✓ Create directory: `ref/24-list-pow-list-performance`
2. ✓ Save this design document
3. Commit design to git
4. Use `superpowers:writing-plans` to create detailed implementation plan
5. Use `superpowers:using-git-worktrees` to create isolated workspace
6. Begin Phase 1 implementation

### Success Criteria Summary

✅ 69.9% of EXPLODE/GROUP_BY bottleneck eliminated
✅ 10K+ model points processing unlocked
✅ Memory usage reduced 5-10x
✅ Zero API changes for actuaries
✅ Rust benchmarks prove performance gains
✅ Production-ready code quality

---

## References

- [Polars Issue #19349: Support pow operation for list dtype](https://github.com/pola-rs/polars/issues/19349)
- [Polars Issue #7210: Allow list.eval to reference named columns](https://github.com/pola-rs/polars/issues/7210)
- [Polars Plugin User Guide](https://docs.pola.rs/user-guide/expressions/plugins/)
- Profiling data: `gaspatchio-models/basic_term/scratch/profile_for_devs.py`
- GSP-8: Performance EXPLODE/GROUP_BY bottleneck in discount_factor() at scale
