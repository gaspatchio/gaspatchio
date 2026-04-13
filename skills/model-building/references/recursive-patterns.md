# Recursive & Path-Dependent Patterns

Values at time t depend on accumulated state at t-1. This is the #1 reason agents abandon gaspatchio for Python loops — but `accumulate()` handles it.

## Core Primitive: `accumulate()`

```
state[t] = state[t-1] * multiply[t] + add[t]
```

This is a linear recurrence. Most recursive actuarial calculations can be rewritten into this form.

**Always look up before using:** `uv run gspio docs "accumulate" -t code_example`

---

## Pattern 1: Account Value Rollforward

The most common recursive pattern. Account value grows by investment return and receives premium deposits:

```
av[t] = av[t-1] * (1 - fee/12) * (1 + return[t]) + premium[t]
```

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

Some recurrences are genuinely non-linear and can't be expressed as `state * M + A`:

- **Newton-Raphson or solver-based calculations** (e.g., IRR, implied volatility) — these need iterative solvers, not projection patterns
- **State machines with discrete state transitions** (e.g., IFRS 9 staging 1→2→3) — use `when/then/otherwise` chains, not `accumulate`
- **Nested stochastic** (outer × inner scenarios) — framework-level feature, not model-level

If you believe your recurrence can't be linearised, check by trying to write it as `state[t] = state[t-1] * f(inputs[t]) + g(inputs[t])`. If `f` and `g` don't depend on `state`, it's linear and `accumulate` works.
