## Performance Ladder: Where Does This Calculation Belong?

Every calculation has a correct home. Using the wrong one causes either unnecessary complexity or catastrophic performance loss. Work through this ladder top to bottom.

### Level 1: Already Exists — Use It

Before writing anything, check:

```bash
uv run gspio docs "<method or concept>"
```

Gaspatchio already provides:

**Accessor namespaces** (column and frame level):

| Namespace | Key Methods |
|-----------|-------------|
| `finance` | `discount_factor`, `present_value`, `to_monthly`, `compound`, `discount` |
| `projection` | `cumulative_survival`, `previous_period`, `next_period`, `at_period`, `accumulate`, `prospective_value`, `rollforward`, `remaining_sum` |
| `date` | `create_projection_timeline`, `year_frac`, `months_between`, `num_proj_months` |
| `excel` | `pv`, `irr`, `yearfrac`, `edate` |

**Frame-level methods** (on `ActuarialFrame` directly, not via accessors):

| Method | What It Does |
|--------|-------------|
| `af.quantile(q)` | Percentile / VaR calculation across policies |
| `af.collect()` | Materialize lazy frame |
| `af.select(cols)` | Select columns |
| `af.join(other, on=...)` | Join with assumption/parameter tables |
| `af.filter(predicate)` | Filter to in-force policies |
| `af.rename(mapping)` | Rename columns to snake_case |
| `af.drop(*cols)` | Remove temporary columns |
| `af.sort(by)` | Order rows for reconciliation |

**Scenario/shock system** (`gaspatchio_core/scenarios/shocks`):

| Composable | What It Does |
|-----------|-------------|
| `MultiplicativeShock(factor)` | Multiply assumption by factor |
| `AdditiveShock(amount)` | Add constant to assumption |
| `OverrideShock(value)` | Replace assumption with constant |
| `ClipShock(max_value)` | Cap assumption at maximum |
| `PipelineShock([shock1, shock2])` | Chain shocks sequentially |
| `FilteredShock(shock, when)` | Apply shock conditionally |

If it exists, use it. Do not reimplement.

### Level 2: One-Off Model Formula or Too Simple — Use Operators

If the calculation is specific to one model, or if the formula is a single arithmetic operator (even if reusable), write it inline with operators:

```python
# Good: inline formula in model code
af.net_cf = af.premiums - af.claims - af.expenses
af.pols_death = af.pols_if * af.mort_rate_mth

# Good: even though "reusable", a single operator is too simple for an accessor
af.pv_perpetuity = af.payment / af.rate
```

**Complexity floor for accessors:** If the formula is a single operator (`a / b`, `a * b`, `a + b`), prefer inline operators even if the formula is technically reusable. Accessors are justified when the formula has branching logic, multiple parameters, convention choices, list column handling, or would not be obvious to write from memory.

This is not an accessor. This is model code. Use the `gaspatchio-model-building` skill.

### Level 3: Setup Calculation — Python Utility

Calculations that run once per model (not per policy, not per timestep):

- **Yield curve fitting** (Nelson-Siegel, SmithWilson)
- **Table preparation** (loading, cleaning, reshaping)
- **Parameter calibration** (fitting distributions, optimizing parameters)
- **Data loading and validation**

These belong in the model's setup phase (Phase 1) as plain Python functions. They may use scipy, numpy, or any other library. They are NOT accessors.

```python
# Good: setup utility
def fit_nss_curve(market_rates: pl.DataFrame) -> dict[str, float]:
    """Fit Nelson-Siegel-Svensson curve to market data.

    Returns dict with keys: beta0, beta1, beta2, beta3, tau1, tau2.
    """
    from scipy.optimize import minimize
    # ... fitting logic ...
    return {"beta0": ..., "beta1": ..., ...}

def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    # Phase 1: Setup
    curve_params = fit_nss_curve(market_data)
    # Pre-compute monthly discount rates from fitted curve
    monthly_rates = [nss_rate(t/12, **curve_params) for t in range(720)]
    # Store as assumption for use in Phase 3
    ...
```

### Level 4: Needs Rust — Flag It

**Check this BEFORE considering accessors.** If a calculation involves per-policy sequential work, Monte Carlo simulation, or inner loops to omega, it cannot be a Python accessor regardless of how many columns it touches.

Calculations that cannot be efficiently expressed as Polars expressions:

| Calculation | Why Rust |
|-------------|----------|
| Monte Carlo simulation (Vasicek, CIR, Hull-White) | Billions of random draws |
| Life-contingent annuities with full mortality projection | Inner loop to omega per policy, millions of policies |
| Complex iterative solvers per policy | Sequential dependency that can't be vectorized |

**What to do**: Tell the user this needs a Rust kernel contribution. Do not attempt it in Python. Suggest existing Gaspatchio methods that might approximate the need (e.g., `cumulative_survival` + `prospective_value` for many life-contingent calculations).

**Stochastic vs deterministic:** "Random walk" or "stochastic model" does not automatically mean Rust. Distinguish:
- **Deterministic best-estimate projection** (single expected path, no random draws) → Level 3 Python utility
- **Stochastic Monte Carlo** (N scenario paths with random draws) → Level 4 Rust

### Level 5: Reusable Column Operation — Column Accessor

Calculations that:
- Are element-wise arithmetic on column values
- Will be used across multiple models
- Can be expressed entirely as vectorized Polars expressions

These are column accessors. Examples:

| Function | Formula | Why It's an Accessor |
|----------|---------|---------------------|
| `finance.to_continuous()` | `ln(1 + r)` | Reusable, 1 line of Polars |
| `finance.duration_macaulay()` | `sum(t * cf * v^t) / sum(cf * v^t)` | Reusable, list column reduction |
| `finance.convexity()` | `sum(t*(t+1)*cf*v^t) / (P*(1+y)^2)` | Reusable, same pattern |
| `finance.forward_rate()` | `ln(df1/df2) / (t2-t1)` | Reusable, simple arithmetic |
| `risk.hazard_gompertz()` | `a * exp(b * age) + c` | Reusable, single formula |

See [accessor-template.md](accessor-template.md) for implementation patterns.

### Level 6: Reusable Frame Operation — Frame Accessor

Calculations that operate on the entire frame using vectorized Polars expressions (add multiple columns, transform structure):

| Function | What It Does | Why Frame-Level |
|----------|-------------|-----------------|
| `reporting.add_net_cashflow()` | Adds net_cf from premiums, claims, expenses | Reads multiple columns |
| `ifrs17.compute_csm()` | Adds CSM-related columns to frame | Adds several interdependent columns |

These are less common than column accessors. Most reusable calculations operate on single columns.

---

## Decision Examples

### "Add duration calculation"
- Level 1: Check `uv run gspio docs "duration"` — does it exist? If yes, use it.
- Level 5: If not, it's reusable element-wise arithmetic → column accessor.

### "Add Nelson-Siegel curve fitting"
- Level 3: Runs once per model, needs scipy → Python utility in setup. NOT an accessor.

### "Add Monte Carlo interest rate paths"
- Level 4: Billions of ops → Flag for Rust.

### "Calculate net cashflow for this model"
- Level 2: One-off formula → Use operators inline. NOT an accessor.

### "Add a Gompertz mortality hazard function"
- Level 1: Check if it exists. If not:
- Level 5: Single formula, reusable → column accessor.

### "Map product codes to expense loadings"
- Level 2: Model-specific → Use `when/then/otherwise` or `Table.lookup()` inline. NOT an accessor.

### "Add backward reserve recursion V(t) = v * (q * benefit + p * V(t+1))"
- Level 1: Check `uv run gspio docs "prospective_value"` and `uv run gspio docs "accumulate"`.
- `projection.prospective_value()` is purpose-built for this.
- `projection.accumulate()` handles the general linear recurrence `state[t] = state[t-1] * M[t] + A[t]` (reverse inputs for backward recursion).
- Both run in Rust, parallelized across policies. Do NOT write a Python for-loop.

### "Add forward rates from discount factors"
- Level 1: Check if it exists.
- Level 5: If not, it uses `list.eval(pl.element().shift(1))` for adjacent elements — reusable column accessor.

### "Apply Solvency II mass lapse stress"
- Level 1: The `scenarios/shocks` system already handles this: `PipelineShock([MultiplicativeShock(1.4), ClipShock(1.0)])`. NOT an accessor.

### "Add perpetuity PV calculation"
- Level 2: `af.pv = af.payment / af.rate` — single operator, too simple for an accessor. Use inline.

### "Calculate VaR at 99.5%"
- Level 1: `af.quantile(0.995)` already exists as a frame method. NOT an accessor.

### "Build Lee-Carter stochastic mortality model"
- Level 3: SVD fitting (`numpy.linalg.svd`) → Python setup utility.
- Level 3: Deterministic k(t) projection (single drift path) → Python utility.
- Level 4: Stochastic k(t) Monte Carlo (N paths with random draws) → Flag for Rust.

---

## Sequential Dependencies: Check Before Flagging for Rust

If your calculation has the form `state[t] = f(state[t-1])` or `state[t] = f(state[t+1])`, it cannot be a pure Polars expression accessor. But Gaspatchio may already have a Rust kernel for it:

| Pattern | Existing Kernel | Method |
|---------|----------------|--------|
| Forward accumulation: `state[t] = state[t-1] * M + A` | Yes | `projection.accumulate()` |
| Backward recursion: `V(t) = f(V(t+1))` | Yes | `projection.prospective_value()` |
| Cumulative product: `tpx[t] = prod(1-qx[0..t])` | Yes | `projection.cumulative_survival()` |
| Multi-step rollforward: AV with charges, credits, premiums | Yes | `projection.rollforward()` |
| Custom recurrence not matching above | No | Flag for Rust (Level 6) |

**Rule:** Always check for an existing kernel before flagging for Rust. The most common actuarial sequential calculations already have Rust implementations.
