# Recursive Accumulation: The Gap Identified by Tutorial Testing

## How This Was Found

During agent testing of the Level 3 tutorial, an agent role-playing as an actuary correctly identified that gaspatchio's vectorised approach (cumulative_product + previous_period) only works when growth factors are **independent of the accumulated state**. If the output at time t feeds back into the calculation at t+1, the pattern breaks.

This is the most common pattern in actuarial modeling and represents a real limitation.

## The Problem

**Works today** (independent growth factors):
```python
# Growth factor at each period doesn't depend on AV
af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (1.0 + af.inv_return_mth)
af.cumulative_growth = af.combined_growth_factor.cum_prod()
af.av_pp = af.av_pp_init * af.cumulative_growth.projection.previous_period(fill_value=1.0)
```

**Doesn't work** (state-dependent feedback):
```python
# Fee depends on AV, which depends on fee at t-1 — circular
# AV[t] = (AV[t-1] + premium[t] - fee(AV[t-1])) * (1 + return[t])
# fee(AV) = AV * fee_rate  (fee is a function of the current AV)
```

Real-world examples that require this:
- **Dynamic fees** — management fee as percentage of AV, where AV depends on prior fees
- **Cost of Insurance (COI)** — deducted from AV monthly, where COI amount depends on net amount at risk (SA - AV)
- **Universal Life crediting** — credited rate depends on account balance tier
- **Cash value accumulation** — with non-linear surrender charge schedules applied to AV
- **Ratchet death benefits** — track maximum historical AV (requires `max` logic, not just add/mult)

## Current State in Gaspatchio

### What exists
- `projection.previous_period()` / `next_period()` / `at_period()` — list shifting
- `projection.cumulative_survival()` — cumulative product with timing
- Polars `cum_sum()`, `cum_prod()` — fixed recurrence only
- Three Rust plugins: `list_pow`, `list_conditional`, `list_clip` — element-wise, not stateful

### What's been designed but not built

**`ref/26-recursive-accumulation/`** contains two design documents:

- `26-background.md` — comprehensive research establishing:
  - Intra-seriatim calculations (within a policy over time) are inherently sequential
  - Inter-seriatim calculations (across policies) are embarrassingly parallel
  - Polars List columns perfectly match this: rayon parallelises across rows, single thread processes within
  - Performance: Python ~2,300 ns/op vs Rust ~7 ns/op = **330x gap**

- `26-background-review.md` — strategic review that:
  - **Rejects** the initially proposed `accumulate(inflows, outflows, interest)` as too rigid
  - **Proposes** a generic **Linear Recurrence Primitive**: `scan_linear(initial, multiply, add)`
  - Defines a 3-layer architecture (Rust primitive → Python composition → dedicated kernels for edge cases)

## Proposed Solution: `scan_linear` Rust Plugin

### The Mathematical Primitive

Most actuarial accumulations fit the linear recurrence:

```
State[t] = State[t-1] × M[t] + A[t]
```

Where:
- **M[t]** (multiplicative factor): growth component (e.g., `1 + interest_rate`, or survival `1 - qx`)
- **A[t]** (additive term): flow component (e.g., `premium - charges`)

### Rust Implementation (from design doc)

```rust
/// Computes: out[t] = (out[t-1] * mult[t]) + add[t]
pub fn scan_linear(
    initial: &Series,  // Scalar initial state per policy
    multiply: &Series, // List column of multiplicative factors
    add: &Series       // List column of additive terms
) -> PolarsResult<Series>
```

Implementation:
1. Take `initial`, `multiply`, `add` as `Series`, resolve scalar vs list
2. Use `ListChunked::amortized_iter()` to iterate over policies (parallelised by Polars engine)
3. Per policy: tight `for t in 0..len` loop with `state = state * M_t + A_t`
4. Collect per-row chunks into `ListChunked`, return as `Series`

### Python API (Layer 2: Composition)

Python constructs M and A vectors, keeping business logic readable/auditable:

```python
# AV_t = (AV_{t-1} + Prem_t - Fee_t) × (1 + i_t)
# Rearranged: State × M + A where M = (1+i), A = (Prem - Fee) × (1+i)
growth_factor = 1 + af.interest_rate
net_flow_grown = (af.premiums - af.fees) * growth_factor

af.av = af.projection.scan_linear(
    initial=af.av_pp_init,
    multiply=growth_factor,
    add=net_flow_grown,
)
```

### Edge Cases (Layer 3: Beyond Linear)

Three categories of non-linear recursion identified in the design review:

| Category | Example | Proposed Approach |
|---|---|---|
| Piecewise-linear with branches | `COI = rate × max(0, SA - AV)` | Future `scan_linear_with_branches` primitive |
| Mildly implicit | Fee depends weakly on AV | Picard iteration: run `scan_linear`, recompute flows, iterate to convergence |
| Genuinely non-linear | Ratchet benefits, path-dependent options | Dedicated Rust kernel per product type |

## Design Details (from review doc)

### Broadcasting
- `initial`: length-N scalar series (one per policy), broadcasts when len=1
- `multiply` and `add`: accept List series OR scalar-per-row, broadcasting scalars across inner lists (mirroring `list_pow` behaviour)

### Null Semantics
- `initial` null → error or propagate null output list for that row
- `multiply` null → treat as identity (M=1.0) or hard-error
- `add` null → treat as identity (A=0.0) or hard-error
- Must be consistent with other `polars_functions` kernels

### Shape Errors
- Inner list lengths of `multiply` and `add` must agree
- Error on mismatch (don't silently truncate), consistent with `list_pow`

## How appliedlife Works Around It

The reconciled appliedlife model avoids true recursion by pre-computing growth factors independently of AV:

```python
# This works because fee is a FIXED RATE, not a function of AV
af.combined_growth_factor = (1.0 - af.maint_fee_rate / 12.0) * (1.0 + af.inv_return_mth)
af.av_pp = af.av_pp_init * af.combined_growth_factor.cum_prod().projection.previous_period(fill_value=1.0)
```

This is algebraically equivalent to the recursive form ONLY when the fee rate is constant. For products where the fee amount (not rate) depends on AV, or where COI depends on net amount at risk, this workaround doesn't apply.

## Performance Context

For 100,000 policies × 360 months = 36 million iterations:

| Approach | Time | Notes |
|---|---|---|
| Python loop | ~83 seconds | 2,300 ns/op — impractical for production |
| Rust scan_linear | ~0.25 seconds | 7 ns/op — matches gaspatchio performance targets |
| Current workaround (cum_prod) | ~0.01 seconds | Only works for independent factors |

## Implementation Effort

### What exists (can be followed as patterns)
- `core/src/polars_functions/list_pow.rs` — Rust plugin operating on List columns
- `core/src/polars_functions/list_conditional.rs` — similar pattern
- `core/src/polars_functions/list_clip.rs` — similar pattern
- All three use `amortized_iter()` and the plugin registration pattern

### What needs to be built
1. **Rust plugin** `scan_linear` in `core/src/polars_functions/` (~100-200 lines following existing patterns)
2. **Python wrapper** in `gaspatchio_core/accessors/projection.py` (~50 lines)
3. **Type stubs** in `projection.pyi`
4. **Tests** covering: basic recurrence, scalar broadcasting, null handling, shape errors
5. **Documentation** with actuarial examples (AV rollforward, reserve accumulation)

### Products this unblocks
- Universal Life (COI deduction depends on AV)
- Unit-linked with dynamic charges
- Variable Annuities with tiered fees
- Any product where cashflows at t depend on accumulated state at t

## Related Files

- `ref/26-recursive-accumulation/26-background.md` — full research and performance analysis
- `ref/26-recursive-accumulation/26-background-review.md` — API design and layered architecture
- `core/src/polars_functions/` — existing Rust plugin infrastructure (patterns to follow)
- `tutorial/level-3-mini-va/base/model.py` — the independent-growth workaround in practice
- `tutorial/level-3-mini-va/steps/04-dynamic-lapse/model.py` — dynamic lapse uses ITM but avoids full feedback loop
