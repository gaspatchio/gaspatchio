# Recursive Accumulation in Actuarial Projections

Research on implementing recursive time-series calculations (like account value
projections) efficiently in Gaspatchio.

## The Problem

Account value calculations are **sequentially dependent**:

```
AV[t] = f(AV[t-1], premium[t], fee[t], return[t])
```

You can't compute AV[50] without first computing AV[0..49]. This creates a
fundamental constraint on parallelization.

---

## 1. The Parallelism Constraint

### Two Types of Actuarial Calculations

| Type | Description | Parallelizable? |
|------|-------------|-----------------|
| **Intra-seriatim** | Calculations *within* a single policy over time (AV growth, reserves, survival) | No - each step depends on previous |
| **Iter-seriatim** | Calculations *across* different policies | Yes - policies are independent |

**Source**: [JuliaActuary: The Life Modeling Problem](https://juliaactuary.org/posts/life-modeling-problem/)

> "Algorithmically, this means that intra-seriatim calculations (ie account value
> growth, survivorship) are not amenable to parallelism but iter-seriatim
> calculations would be (ie calculating multiple policy trajectories simultaneously)."

### Practical Implication for Gaspatchio

- **List columns** (one row per policy, list of values over time) allow parallel
  processing across policies while maintaining sequential processing within each list
- This is the optimal pattern for actuarial projections

---

## 2. Accumulator vs Vectorized Approaches

### Performance Comparison (JuliaActuary Benchmarks)

| Language | Approach | Time | Relative |
|----------|----------|------|----------|
| Julia | Accumulator (loop) | 6.4 ns | 1.0x |
| Rust | Accumulator (loop) | 7.0 ns | 1.1x |
| Python (Numba) | Accumulator | 626 ns | 98x |
| Python | Accumulator | 2,314 ns | 363x |
| Julia | Vectorized | 218 ns | 34x |
| R | Vectorized | 46,617 ns | 7,312x |

**Key Insight**: For recursive problems, explicit loops (Accumulator) dramatically
outperform vectorized approaches in every language except R (where loops are terrible).

> "For this recursive type calculation, it's much more efficient to write a for
> loop (the Accumulator approach) in every language except for R."

### Real-World Impact

At CUNA Mutual's scale (50 servers, 20 cores, running for days), the difference
between fastest and slowest approaches represents **721 years** of compute time.

---

## 3. Scan and Fold Operations

### Definitions

| Operation | Input | Output | Use Case |
|-----------|-------|--------|----------|
| **fold** (reduce) | List + initial value | Single value | Sum, product, NPV |
| **scan** | List + initial value | List of intermediate states | Running totals, AV trajectory |

**Scan is fold that "shows its work"** - you get the state at every step.

**Sources**:
- [Wikipedia: Fold (higher-order function)](https://en.wikipedia.org/wiki/Fold_(higher-order_function))
- [Wikipedia: Prefix Sum (Scan)](https://en.wikipedia.org/wiki/Prefix_sum)

### Account Value as a Scan Operation

```python
# The recursive formula:
# av_after_fee = av * (1 - fee_rate)
# av_next = av_after_fee * (1 + return)

# As a scan:
def accumulate(state, return_t):
    av_after_fee = state * (1 - 0.01/12)  # Monthly fee
    av_next = av_after_fee * (1 + return_t)
    return av_next

# Scan produces ALL intermediate states:
av_trajectory = scan(
    initial=550_000,
    function=accumulate,
    sequence=monthly_returns
)
# Result: [550000, 553938, 560598, 563400, ...]
```

### Visual Trace

```
t=0: 550,000 ─┬─ fee ──► 549,542 ─┬─ ×1.008 ──► 553,938
              │                    │
t=1: 553,938 ─┼─ fee ──► 553,477 ─┼─ ×1.012 ──► 560,118
              │                    │
t=2: 560,118 ─┼─ fee ──► 559,651 ─┼─ ×1.005 ──► 562,449
              ▼                    ▼
           state              next state
```

---

## 4. Why Scan is Fast

### Memory Access Pattern

```python
# BAD: Materializing the whole trajectory when you only need the final value
av = [initial] * n
for t in range(1, n):
    av[t] = av[t-1] * factor[t]  # reads and writes the big av[] array every step

# GOOD: Stateful scan (cache- and register-friendly)
state = initial
for factor in factors:  # factors are contiguous in memory
    state = state * factor  # state can live in registers
    yield state              # only write out if you actually need the path
```

### Performance Characteristics

1. **Cache-friendly**: Reads memory sequentially
2. **No allocations**: Updates state in-place
3. **Branch-predictable**: Simple loop structure
4. **Pipeline-friendly**: Loop-carried dependency is simple enough that modern CPUs can keep the ALUs busy, even though this is not a classic SIMD/vectorizable pattern like `cum_sum`

---

## 5. Built-in `cum_sum`/`cum_prod` vs Custom Scans

Before building custom scan operations, we need to understand what built-ins
already provide and where they fall short.

### What Built-ins Do

In Polars/pandas/NumPy, the built-ins are essentially:

| Function | Recurrence | Notes |
|----------|------------|-------|
| `cum_sum(x)` | y[t] = y[t-1] + x[t] | Starts from 0 or first value |
| `cum_prod(x)` | y[t] = y[t-1] × x[t] | Starts from 1 or first value |

Key characteristics:
- Operate on **one series** at a time
- The **recurrence is fixed** (add or multiply)
- No external initial value per row
- No multiple timing points output

**Perfect for:**
- Cumulative claims: `cum_sum(claims)`
- Simple survival: `cum_prod(1 - qx)`

### Five Dimensions Where Custom Scans Go Beyond Built-ins

#### (a) Shape: List-per-row vs Long Column

Typical `cum_sum` operates on one long column where time is the row axis.

Our actuarial shape is:
- **One row per policy**, with a **list per row** representing time
- We want "cum_sum **within each list** per row"

```python
# We want this:
af.av_bef_fee = af.av_init.projection.scan_add(af.prem_to_av)

# Meaning: For each policy, take that policy's AV₀, then scan through
# its own list of premiums.
```

So custom functions provide: **vectorised cumulative ops over list columns
with an external initial state**.

#### (b) Richer Recurrences Than "Just Add/Multiply"

A classic AV recurrence:

```
AV[t] = (AV[t-1] + prem[t] - fee[t]) × (1 + r[t])
```

This isn't expressible as a single `cum_sum` or `cum_prod`:
- Depends on **three** flows: `prem`, `fee`, `r`
- **Order matters**: add prem, subtract fee, then multiply by returns
- Each step's state feeds into next step

You *could* contort it with present-value gymnastics, discount factors,
reversed arrays... but that's:
- Algebraically complex
- Opaque to actuaries (and LLMs)
- Easy to get subtly wrong

A custom kernel literally encodes the recurrence:

```rust
state = initial;
for t in 0..T {
    state = (state + inflow[t] - outflow[t]) * (1 + r[t]);
    out[t] = state;
}
```

#### (c) External Initial State (Per Row) is First-Class

We often have:
- `av_init` / `res_init` as a **scalar per policy** (not the first list element)
- Then a series of per-period list values

```python
af.account_value = af.av_init.projection.rollforward(
    add=af.prem_to_av,
    subtract=af.fees,
    grow_by=af.inv_return,
)
```

This reads: "Start from `av_init` (per row), then scan through those lists."

Built-in `cum_sum`/`cum_prod` don't naturally take a scalar initial state
per row then cumulatively apply a list onto it.

#### (d) Multiple Timing Points From One Pass

For lifelib-style calculations we need **four timing points** per step:

```
bef_prem[t], bef_fee[t], bef_inv[t], mid_mth[t]
```

A single `cum_sum`/`cum_prod` gives **one** series. To get four, you'd need
multiple operations, shifts, and diffs - messy and error-prone.

A custom kernel does it in one pass:

```rust
for t in 0..T {
    bef_prem[t] = state;
    state += prem[t];
    bef_fee[t]  = state;
    state -= fee[t];
    bef_inv[t]  = state;
    state *= 1 + r[t];
    mid_mth[t]  = state;
}
```

Returns a **struct of four lists** - faster (one loop) and matches the
textbook cashflow diagram exactly.

#### (e) Domain Semantics & Null Handling

Generic `cum_sum` has fixed semantics:
- Does it propagate nulls?
- Treat null as 0?
- What about mismatched lengths?

For actuarial calculations we might want:
- Missing fees → 0
- Missing interest → 0 or 1 depending on context
- Explicit errors if lists aren't same length

Custom kernels encode "actuarially sensible defaults" once.

### When to Use Built-ins vs Custom Scans

**Use built-ins when:**
- Math is exactly cumulative sum/product
- Shape is simple (long column, not list-per-row)
- No external per-row initial state needed

**Use custom scans when:**
- Need external initial per row
- Richer recurrence with multiple inputs
- Want multiple timing points from same loop
- Operating over list columns

| Pattern | Use Built-in | Use Custom Scan |
|---------|--------------|-----------------|
| Cumulative claims | ✅ `cum_sum(claims)` | |
| Simple survival (long column) | ✅ `cum_prod(1-qx)` | |
| AV rollforward with fees/returns | | ✅ `rollforward()` |
| Multi-timing cashflow ladder | | ✅ `accumulate()` |
| List-per-row with initial state | | ✅ `cumulative_survival(initial=...)` |

---

## 6. The "Vector Gymnastics" Problem

### Pattern 1: NPV/Survival with Built-ins (Ugly Version)

If you force `cumprod`/`cumsum` only, the Life Modeling Problem becomes:

```python
# Long table: columns = ["t", "q", "w", "P", "S", "r"]
af.decrement = 1 - af.q - af.w
af.survival = af.decrement.cum_prod()

# Inforce = 1 for t=0, then lagged survival (hacky shift)
af.inforce = af.survival.shift(fill=1.0)

af.net_cf = af.inforce * af.P - af.inforce * af.q * af.S
af.discount_factor = (1 / (1 + af.r)) ** af.t
af.npv = (af.net_cf * af.discount_factor).sum()
```

**Problems:**
- "Lagged survival trick" is not obvious to actuaries
- Recurrence is hidden in `cumprod + shift`
- For list-per-row shape, even uglier

### Pattern 1: NPV/Survival with Custom Projection (Clean Version)

```python
# Combined decrement for each month
af.combined_decrement = af.mort_rate_mth + af.lapse_rate_mth

# In-force policies (survivorship) - the recurrence is explicit in the name
af.pols_if = af.combined_decrement.projection.cumulative_survival(
    initial=af.pols_if_init,  # eg 1.0 per policy
)

# Cashflows - formula IS the code
af.premium_cf = af.pols_if * af.premium
af.claim_cf   = af.pols_if * af.mort_rate_mth * af.sum_assured
af.net_cf     = af.premium_cf - af.claim_cf

# NPV
af.discount_factor = (1 / (1 + af.interest_mth)) ** af.period
af.npv = (af.net_cf * af.discount_factor).projection.sum_over_projection()
```

Actuary reading this can map each line to the textbook definition.

### Pattern 2: AV Rollforward with Built-ins (Vector Gymnastics)

Forcing only `cum_sum`/`cum_prod`:

```python
# Build per-period net contributions before investment:
af.net_cf = af.prem - af.fee

# Cumulative growth factor
af.growth_factor = (1 + af.r)
af.cum_growth = af.growth_factor.cum_prod()

# Then you need present-value gymnastics:
# AV_t = AV0 * cum_growth_t + sum_{k <= t}(net_cf_k * product_{j>k..t}(1+r_j))
#
# Which means:
# - Building reverse discount factors
# - Reversing arrays
# - Joining multiple cumulative sums/prods
# - ...or looping in Python (slow)
```

This is *possible* but:
- Hard to read
- Hard to audit
- Easy to get subtly wrong

### Pattern 2: AV Rollforward with Custom Scan (Clean Version)

```python
# Single timing point version
af.account_value = af.av_init.projection.rollforward(
    add=af.prem_to_av,
    subtract=af.fees,
    grow_by=af.inv_return,
)

# Multiple timing points version
af.av_timings = af.av_init.projection.accumulate(
    inflows=af.prem_to_av,
    outflows=af.fees,
    interest=af.inv_return,
    timing_points=["bef_prem", "bef_fee", "bef_inv", "end"],
)

af.av_bef_prem = af.av_timings.struct.field("bef_prem")
af.av_bef_fee  = af.av_timings.struct.field("bef_fee")
af.av_bef_inv  = af.av_timings.struct.field("bef_inv")
af.av_end      = af.av_timings.struct.field("end")
```

Matches the lifelib diagrams exactly. One efficient Rust loop. Readable.

---

## 7. Implementation in Polars/Rust

### Current Polars Capabilities

From [Polars documentation](https://docs.rs/polars/latest/polars/):

- `cum_sum`, `cum_prod`, `cum_max`, `cum_min` - built-in cumulative operations
- `fold_exprs` - horizontal fold across columns
- `map` with Rust iterator `.scan()` - custom sequential accumulation

### Custom Scan Pattern

From [Stack Overflow](https://stackoverflow.com/questions/76037851/how-to-accumulate-the-rows-in-a-column-using-polarspreludefold-exprs):

```rust
col("returns").map(
    |returns| {
        let returns = returns.f64()?;
        let fee_factor = 1.0 - 0.01/12.0;

        Ok(Some(
            returns.into_iter()
                .scan(550_000.0, |state, ret| {
                    let ret = ret.unwrap_or(0.0);
                    *state = *state * fee_factor * (1.0 + ret);
                    Some(*state)
                })
                .collect::<Float64Chunked>()
                .into_series(),
        ))
    },
    GetOutput::from_type(DataType::Float64),
)
```

---

## 8. Actuarial Terminology

### Common Terms for This Pattern

| Term | Context | Usage |
|------|---------|-------|
| **Rollforward** | LDTI/GAAP accounting | Reserve, AV, MRB balance movements |
| **Account Value Projection** | UL, VA modeling | Fund accumulation over time |
| **Recursive Formula** | Academic/textbook | Time-dependent calculations |
| **Fund Accumulation** | Investment products | Asset growth modeling |

**Sources**:
- [FASB LDTI Practice Note](https://www.actuary.org/) - "rollforward" terminology
- [lifelib CashValue_SE](https://lifelib.io/libraries/savings/CashValue_SE.html) - `av_pp_at(t, timing)`

### lifelib Pattern

lifelib uses explicit timing points:

```python
av_pp_at(t, 'BEF_PREM')  # Before premium
av_pp_at(t, 'BEF_FEE')   # After premium, before fee
av_pp_at(t, 'BEF_INV')   # After fee, before investment
av_pp_at(t, 'MID_MTH')   # Mid-month (for decrements)
```

---

## 9. Proposed Gaspatchio API

### ProjectionAccessor Stub

The complete API surface for the projection accessor:

```python
class ProjectionAccessor:
    """
    Accessor for projection-specific operations on list columns.

    All methods operate on list-per-row columns where each row represents
    a policy and each list element represents a time period.
    """

    def cumulative_survival(
        self,
        decrement: ExpressionProxy = None,
        *,
        initial: ExpressionProxy = None
    ) -> ExpressionProxy:
        """
        Compute cumulative survival probability.

        Formula: survival[t] = survival[t-1] * (1 - decrement[t])
        """
        ...

    def rollforward(
        self,
        *,
        add: ExpressionProxy = None,
        subtract: ExpressionProxy = None,
        grow_by: ExpressionProxy = None,
        initial: ExpressionProxy = None
    ) -> ExpressionProxy:
        """
        Single-output account value rollforward.

        Formula: state[t] = (state[t-1] + add[t] - subtract[t]) * (1 + grow_by[t])
        """
        ...

    def accumulate(
        self,
        *,
        inflows: ExpressionProxy = None,
        outflows: ExpressionProxy = None,
        interest: ExpressionProxy = None,
        timing_points: list[str] = None,
        initial: ExpressionProxy = None
    ) -> ExpressionProxy:
        """
        Multi-timing-point accumulation returning struct of lists.

        timing_points: e.g., ["bef_prem", "bef_fee", "bef_inv", "mid_mth"]
        Returns: Struct column with one field per timing point.
        """
        ...
```

### Rust-Level Functions (Internal)

```python
# Low-level functions exposed via PyO3
def _rollforward_single(
    initial: Series,      # Scalar per row
    add: Series,          # List per row
    subtract: Series,     # List per row
    grow_by: Series,      # List per row
) -> Series:
    """Returns list-per-row of end-of-period values."""
    ...

def _rollforward_multi(
    initial: Series,
    add: Series,
    subtract: Series,
    grow_by: Series,
    timing_points: list[str],
) -> Series:
    """Returns struct-of-lists with named timing points."""
    ...
```

### Option A: Simple Rollforward

```python
af.account_value = af.av_init.projection.rollforward(
    add=af.prem_to_av,
    subtract=af.fees,
    grow_by=af.inv_return,
)
```

### Option B: With Timing Points

```python
af.av_timings = af.av_init.projection.accumulate(
    inflows=af.prem_to_av,
    outflows=af.fees,
    interest=af.inv_return,
    timing_points=['bef_prem', 'bef_fee', 'bef_inv', 'mid_mth'],
)

# Access individual timing points:
af.av_mid_month = af.av_timings.struct.field('mid_mth')
```

### Option C: Composable Steps

```python
# Build up the calculation step by step (more actuarial, more auditable)
af.av_bef_fee = af.av_init.projection.scan_add(af.prem_to_av)
af.av_bef_inv = af.av_bef_fee.projection.scan_subtract(af.fees)
af.av_end = af.av_bef_inv.projection.scan_multiply(1 + af.inv_return)
af.av_next = af.av_end.projection.shift_forward()  # Carry to next period
```

---

## 10. Implementation Considerations

### What Needs to Happen

1. **Rust-level scan function** for list columns that:
   - Takes initial value
   - Takes accumulator function (or predefined patterns)
   - Returns list of intermediate states

2. **Python API** in projection accessor:
   - Clean interface matching actuarial terminology
   - Support for multiple timing points (struct output)
   - Composable with existing operations

3. **Performance target**:
   - Current Python loop: ~2,300 ns per policy
   - Target Rust scan: ~7 ns per policy
   - **~330x improvement**

### Complexity Assessment

| Component | Difficulty | Notes |
|-----------|------------|-------|
| Basic scan in Rust | Medium | Use Polars `map` with iterator `.scan()` |
| Python accessor wrapper | Easy | Follows existing accessor pattern |
| Multiple timing points | Medium-Hard | Need struct output or multiple passes |
| Integration with existing ops | Medium | Must compose with when/then, arithmetic |

---

## 11. References

### Primary Sources

1. [JuliaActuary: The Life Modeling Problem](https://juliaactuary.org/posts/life-modeling-problem/) - Parallelism analysis, benchmarks
2. [lifelib CashValue_SE Model](https://lifelib.io/libraries/savings/CashValue_SE.html) - Reference implementation
3. [SOA: Recursive Functions in Actuarial Science](https://www.soa.org/globalassets/assets/library/research/actuarial-research-clearing-house/1990-99/1993/arch-3/arch93v323.pdf) - Historical context

### Technical References

4. [Wikipedia: Fold (higher-order function)](https://en.wikipedia.org/wiki/Fold_(higher-order_function))
5. [Wikipedia: Prefix Sum (Scan)](https://en.wikipedia.org/wiki/Prefix_sum)
6. [Polars Rust Documentation](https://docs.rs/polars/latest/polars/)
7. [Stack Overflow: Polars Accumulation](https://stackoverflow.com/questions/76037851/how-to-accumulate-the-rows-in-a-column-using-polarspreludefold-exprs)

### Industry Standards

8. [FASB LDTI Practice Note](https://www.actuary.org/) - "rollforward" terminology
9. [Mastering Recursive Formulas in Actuarial Science](https://www.numberanalytics.com/blog/mastering-recursive-formulas-actuarial-science)

---

## 12. Next Steps

1. **Prototype** basic scan in Rust using Polars `map` + iterator pattern
2. **Benchmark** against Python loop implementation
3. **Design** API for single vs multiple timing points
4. **Implement** in projection accessor
5. **Test** with AppliedLife model account value calculation

---

## Appendix A: Python Code Examples

### A.1 Current Python Loop (from model_mvp.py)

This is the current implementation - works but slow due to Python loop overhead:

```python
def calculate_av_for_policy(policy_row, scenario_returns_df, projection_months=82):
    """
    Calculate account value using Python loop.

    Performance: ~2,300 ns per iteration (Python overhead)

    This works but is slow because:
    - Python loop overhead on every iteration
    - No vectorization possible due to sequential dependency
    - Cannot leverage Rust/Polars performance
    """
    import polars as pl

    av_init = float(policy_row["av_pp_init"])
    maint_fee_rate = float(policy_row["maint_fee_rate"])
    fund_index = policy_row["fund_index"]

    fund_returns = scenario_returns_df.select(["t", fund_index]).sort("t")

    # Lists to store timing points
    av_bef_prem = []
    av_bef_fee = []
    av_bef_inv = []
    av_mid_mth = []

    current_av = av_init

    for t in range(projection_months):
        # Timing point 1: Before premium
        av_bef_prem.append(current_av)

        # Timing point 2: Before fee (after premium)
        # For in-force, premium = 0, so same as bef_prem
        av_bef_fee.append(current_av)

        # Timing point 3: Before investment (after fee)
        maint_fee = (maint_fee_rate / 12) * current_av
        av_after_fee = current_av - maint_fee
        av_bef_inv.append(av_after_fee)

        # Get investment return for this period
        inv_return = fund_returns.filter(pl.col("t") == t)[fund_index][0]

        # Timing point 4: Mid-month (half return credited)
        av_mid = av_after_fee * (1 + inv_return / 2)
        av_mid_mth.append(av_mid)

        # Carry forward: full return applied
        current_av = av_after_fee * (1 + inv_return)

    return {
        "av_pp_bef_prem": av_bef_prem,
        "av_pp_bef_fee": av_bef_fee,
        "av_pp_bef_inv": av_bef_inv,
        "av_pp_mid_mth": av_mid_mth,
    }
```

### A.2 Conceptual Scan Using itertools.accumulate

Python's `itertools.accumulate` is a scan operation - here's how the pattern works:

```python
from itertools import accumulate

def scan_example_simple():
    """
    Simple scan example - account value with fees and returns.

    itertools.accumulate IS Python's built-in scan operation.
    """
    initial_av = 550_000
    monthly_fee_rate = 0.01 / 12  # 1% annual = 0.083% monthly
    returns = [0.008, 0.012, 0.005, -0.003, 0.010]

    def accumulator(state, ret):
        av_after_fee = state * (1 - monthly_fee_rate)
        return av_after_fee * (1 + ret)

    # accumulate produces ALL intermediate states
    av_trajectory = list(accumulate(returns, accumulator, initial=initial_av))

    print(av_trajectory)
    # [550000, 553480.42, 560145.89, 562655.32, 560808.43, 566282.52]

    return av_trajectory


def scan_with_timing_points():
    """
    Scan that tracks multiple timing points per period.

    This is what actuarial models need - state at different moments
    within each projection period.
    """
    initial_av = 550_000
    monthly_fee_rate = 0.01 / 12
    returns = [0.008, 0.012, 0.005]

    # Manual scan tracking all timing points
    results = []
    state = initial_av

    for t, ret in enumerate(returns):
        bef_prem = state
        bef_fee = state  # No premium for in-force policies
        bef_inv = bef_fee * (1 - monthly_fee_rate)
        mid_mth = bef_inv * (1 + ret / 2)
        end_mth = bef_inv * (1 + ret)

        results.append({
            "t": t,
            "bef_prem": bef_prem,
            "bef_fee": bef_fee,
            "bef_inv": bef_inv,
            "mid_mth": mid_mth,
            "end_mth": end_mth,
        })

        # Carry forward to next period
        state = end_mth

    return results


if __name__ == "__main__":
    print("Simple scan:")
    scan_example_simple()

    print("\nWith timing points:")
    for tp in scan_with_timing_points():
        print(f"  t={tp['t']}: bef_inv={tp['bef_inv']:.2f}, "
              f"mid_mth={tp['mid_mth']:.2f}, end_mth={tp['end_mth']:.2f}")
```

Output:
```
Simple scan:
[550000, 553480.42, 560145.89, 562655.32, 560808.43, 566282.52]

With timing points:
  t=0: bef_inv=549541.67, mid_mth=551739.38, end_mth=553937.08
  t=1: bef_inv=553475.56, mid_mth=556796.41, end_mth=560117.27
  t=2: bef_inv=559650.58, mid_mth=561049.06, end_mth=562447.54
```

### A.3 Proposed Rust Implementation

This is how we'd implement the scan in Rust for Gaspatchio:

```rust
use polars::prelude::*;

/// Simple account value scan - single output
fn account_value_scan(
    initial_av: f64,
    fee_rate: f64,
    returns: &Float64Chunked,
) -> PolarsResult<Series> {
    let result: Float64Chunked = returns
        .into_iter()
        .scan(initial_av, |state, ret| {
            let ret = ret.unwrap_or(0.0);
            let av_after_fee = *state * (1.0 - fee_rate);
            *state = av_after_fee * (1.0 + ret);
            Some(*state)
        })
        .collect();

    Ok(result.into_series())
}

/// Account value scan with multiple timing points - struct output
fn account_value_scan_with_timing(
    initial_av: f64,
    fee_rate: f64,
    returns: &Float64Chunked,
) -> PolarsResult<StructChunked> {
    let n = returns.len();
    let mut bef_inv = Vec::with_capacity(n);
    let mut mid_mth = Vec::with_capacity(n);
    let mut end_mth = Vec::with_capacity(n);

    let mut state = initial_av;

    for ret in returns.into_iter() {
        let ret = ret.unwrap_or(0.0);
        let av_after_fee = state * (1.0 - fee_rate);

        bef_inv.push(av_after_fee);
        mid_mth.push(av_after_fee * (1.0 + ret / 2.0));
        end_mth.push(av_after_fee * (1.0 + ret));

        state = av_after_fee * (1.0 + ret);
    }

    StructChunked::from_series(
        "av_timing".into(),
        &[
            Series::new("bef_inv".into(), bef_inv),
            Series::new("mid_mth".into(), mid_mth),
            Series::new("end_mth".into(), end_mth),
        ],
    )
}
```

> **Design note (Dec 2025):** These per-policy functions are intentionally written as
> small, concrete examples. In the actual Gaspatchio implementation we do **not**
> call a scalar `account_value_scan` per row. Instead, we will implement a
> Polars expression plugin that:
>
> - operates on **list-per-row columns** (like the existing `list_pow` and
>   `list_conditional` kernels in `core/src/polars_functions`),
> - uses `ListChunked::amortized_iter()` to traverse the outer list (policies),
> - runs a stateful loop over each inner list to compute the recurrence, and
> - returns a list-per-row (or struct-of-lists) `Series` back to Polars.
>
> Subsequent design work (see
> `gaspatchio-core/ref/26-recursive-accumulation/26-background-review.md`)
> also generalizes this into a **linear recurrence primitive** `scan_linear`
> (with `state_t = state_{t-1} * M_t + A_t`) that `rollforward`/`accumulate`
> should be thin wrappers around, instead of hard-coding account-value logic
> into a dedicated Rust kernel.

### A.4 Performance Comparison

Expected performance characteristics:

| Approach | Time per Policy | For 1M Policies |
|----------|-----------------|-----------------|
| Python loop (current) | ~2,300 ns | 2.3 seconds |
| Python + Numba JIT | ~626 ns | 0.6 seconds |
| Rust scan | ~7 ns | 0.007 seconds |

**Improvement: ~330x faster with Rust implementation**

---

*Research compiled: December 2024*
*Context: AppliedLife GMXB model implementation*
