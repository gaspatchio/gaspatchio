# Recursive & Path-Dependent Patterns

Values at time *t* depend on accumulated state at *t-1*. Two primitives cover this in gaspatchio — pick by asking one question:

**"Do the within-period charges depend on the running balance?"**

- **No** — the recurrence collapses to a single multiply-and-add. Use **`accumulate()`** (this page).
- **Yes** — the running balance is needed *during* the period to compute later steps within the same period. Use the **rollforward kernel** (`af.projection.rollforward(states={…})`). See [Rollforward](../../../gaspatchio-docs/docs/concepts/rollforward/index.md) for the concept page and [`tutorial/patterns/rollforward-patterns/`](../../../bindings/python/gaspatchio_core/tutorials/patterns/rollforward-patterns/) for runnable patterns.

| Product mechanic | Primitive |
|---|---|
| Fund grown by a list-column return + flat-dollar fee deduction | `accumulate` |
| Survival probability cumulative product, discount factor power | `cum_prod`, list arithmetic |
| Term-life reserve roll, deterministic interest | `accumulate` |
| UL fund with COI on net amount at risk | rollforward kernel |
| IUL fund with floor/cap on the period's index credit | rollforward kernel |
| VA + GMDB anniversary ratchet to the AV high-water mark | rollforward kernel (multi-state) |
| GMWB run-off with lapse stop on fund exhaustion | rollforward kernel (`lapse_when_all_non_positive`) |

The rest of this page documents the `accumulate()` primitive — the linear-recurrence half. For the state-machine half, the rollforward concept doc + tutorial scripts are the canonical reference.

## Core Primitive: `accumulate()`

```
state[t] = state[t-1] * multiply[t] + add[t]
```

This is a linear recurrence. Many recursive actuarial calculations can be rewritten into this form; the ones that can't need rollforward.

**Always look up before using:** `uv run gspio docs "accumulate" -t code_example`

---

## Pattern 1: Account Value Rollforward (linear case)

A specific *linear* case. Account value grows by investment return and receives premium deposits — the within-period charge is a flat rate, not a charge on the running balance:

```
av[t] = av[t-1] * (1 - fee/12) * (1 + return[t]) + premium[t]
```

This collapses to a single multiply-and-add because the fee rate doesn't depend on AV. If your AV has COI on net amount at risk, an IUL floor/cap, or any other within-period charge that needs to see the running balance, this pattern doesn't fit — escalate to the rollforward kernel (see L3 step 07 for the migration recipe).

Gaspatchio approach:

```python
# Pre-compute the multiplicative growth factor
af.growth = (1.0 - af.fee_rate / 12.0) * (1.0 + af.inv_return)

# Shift growth: multiply[t] = growth[t-1] (we grow by PRIOR period's rate)
af.shifted_growth = af.growth.projection.previous_period(fill_value=1.0)

# Premium: deposited at entry only
af.prem_to_av = af.premium * (af.duration_mth_t == 0)

# Accumulate!
af.account_value = af.shifted_growth.projection.accumulate(
    initial=af.opening_av,
    multiply=af.shifted_growth,
    add=af.prem_to_av,
)
```

See: Level 4 model.py SECTION 5, Level 3 Step 06 FIX 1.

---

## Pattern 2: Cumulative Gains with Feedback

Values where the gain at time t depends on cumulative prior gains. Example: unrealised capital gain on a property portfolio where the gain base includes prior gains.

```
base[t] = cumsum(interest + fees)[t] + cumsum(gain[1:t-1])
gain[t] = base[t] * appreciation_rate[t]
```

This looks non-linear because gain appears on both sides. But expand it:

```
cum_gain[t] = cum_gain[t-1] + (cum_fixed[t] + cum_gain[t-1]) * rate[t]
            = cum_gain[t-1] * (1 + rate[t]) + cum_fixed[t] * rate[t]
```

This IS a linear recurrence: `multiply = (1 + rate)`, `add = cum_fixed * rate`.

```python
# Fixed component: cumulative interest + fees (no feedback)
af.cum_fixed = (af.interest + af.fees).list.cumsum()

# Appreciation rate per period
af.rate = af.hpi_pct  # from assumption table

# Linear recurrence on cumulative gain
af.cum_gain = af.rate.projection.accumulate(
    initial=0.0,                          # no gain at t=0
    multiply=(1.0 + af.rate),             # prior gains also appreciate
    add=af.cum_fixed * af.rate,           # new base appreciates
)

# Per-period gain is the difference
af.gain = af.cum_gain - af.cum_gain.projection.previous_period(fill_value=0.0)
```

---

## Pattern 3: Reserve Rollforward

Reserve at time t depends on reserve at t-1, decrements, and cashflows:

```
reserve[t] = (reserve[t-1] + premium[t]) * (1+i) - claims[t] - expenses[t]
```

Rearrange into linear recurrence form:

```python
af.growth = 1.0 + af.interest_rate
af.net_flow = af.premium * af.growth - af.claims - af.expenses

af.reserve = af.growth.projection.accumulate(
    initial=af.opening_reserve,
    multiply=af.growth,
    add=af.net_flow,
)
```

---

## Pattern 4: Running Balance with Variable Flows

Cash balance with irregular deposits and withdrawals:

```
cash[t] = cash[t-1] + inflows[t] - outflows[t]
```

This is `accumulate` with `multiply=1.0`:

```python
af.net_flow = af.inflows - af.outflows

af.cash_balance = af.net_flow.projection.accumulate(
    initial=af.opening_cash,
    multiply=1.0,        # no growth — just sum
    add=af.net_flow,
)
```

---

## When `accumulate` Doesn't Fit

Some recurrences can't be expressed as `state[t] = state[t-1] * multiply[t] + add[t]`:

- **Charges that depend on the running balance** (COI on net amount at risk, IUL floor/cap on the in-period credit, AV-banded fees, GMDB ratchets, multi-state products) — use the rollforward kernel (`af.projection.rollforward`).
- **Newton-Raphson or solver-based calculations** (IRR, implied volatility) — iterative solvers, not projection patterns.
- **Discrete-state staging transitions** (IFRS 9 stage 1→2→3) — `when/then/otherwise` chains, not `accumulate`.
- **Nested stochastic** (outer × inner scenarios) — framework-level feature, not model-level.

If you're not sure: try to write the recurrence as `state[t] = state[t-1] * f(inputs[t]) + g(inputs[t])`. If `f` and `g` truly don't depend on `state`, it's linear → `accumulate`. If either depends on the running balance (even via a max/min/clip), it's a state-machine → rollforward kernel.
