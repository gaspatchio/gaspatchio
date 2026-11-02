# Recursive & Path-Dependent Patterns

Values at time *t* depend on accumulated state at *t-1*. Two primitives cover this in gaspatchio — pick by asking one question:

**"Do the within-period charges depend on the running balance?"**

- **No** — the recurrence collapses to a single multiply-and-add. Use **`accumulate()`** (this page).
- **Yes** — the running balance is needed *during* the period to compute later steps within the same period. Use the **rollforward kernel** (`af.projection.rollforward(states={…})`). See [Rollforward](../../../../gaspatchio-docs/docs/concepts/rollforward/index.md) for the concept page and [`tutorial/patterns/rollforward-patterns/`](../../../bindings/python/gaspatchio/tutorials/patterns/rollforward-patterns/) for runnable patterns.

| Product mechanic | Primitive |
|---|---|
| Fund grown by a list-column return + flat-dollar fee deduction | `accumulate` |
| Survival probability cumulative product, discount factor power | `cum_prod`, list arithmetic |
| Term-life reserve roll, deterministic interest | `accumulate` |
| Reserve rolled back from the last period, `V[t] = v[t]·V[t+1] + cf[t]` | `accumulate(reverse=True)` (Pattern 5) |
| Multi-state occupancy — disability with recovery, levels of care | one `accumulate` per state on the fixed-step axis (Pattern 6) — **not** the rollforward |
| Backward recursion with a floor, `V[t] = max(floor, a[t] + b[t]·V[t+1])` | no named form in 1.0 — a doubling scan in core operations (Pattern 7) |
| UL fund with COI on net amount at risk | rollforward kernel |
| IUL fund with floor/cap on the period's index credit | rollforward kernel |
| VA + GMDB anniversary ratchet to the AV high-water mark | rollforward kernel (two balances: the ratchet reads the fund) |
| GMWB run-off with lapse stop on fund exhaustion | rollforward kernel (`lapse_when_all_non_positive`) |

The rest of this page documents the `accumulate()` primitive — the linear-recurrence half — and the recipes built from it. For the state-machine half, the rollforward concept doc + tutorial scripts are the canonical reference.

## Core Primitive: `accumulate()`

```
state[t] = state[t-1] * multiplier[t] + addend[t]
```

This is a linear recurrence. Many recursive actuarial calculations can be rewritten into this form; the ones that can't need rollforward.

**Always look up before using:** `uv run gspio docs "accumulate" -t code_example`

**What position `t` holds.** Position `t` of a forward `accumulate` is the state *after*
step `t`: `state[0] = initial * multiplier[0] + addend[0]`, and the opening value is not in
the list. Read a workbook column that starts at its opening value against
`[initial, after 0, after 1, …]`, which is one shift away:
`.projection.previous_period(fill_value=initial)` — the same shift Patterns 1 and 6 use.
Compared without it, every period sits one step out.

Under `reverse=True` the recurrence runs from each policy's own last period back:
`state[t] = state[t+1] * multiplier[t] + addend[t]`, and `initial` is the value *after* the
last period (Pattern 5).

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

# Shift growth: multiplier[t] = growth[t-1] (we grow by PRIOR period's rate)
af.shifted_growth = af.growth.projection.previous_period(fill_value=1.0)

# Premium: deposited at entry only
af.prem_to_av = af.premium * (af.duration_mth_t == 0)

# Accumulate!
af.account_value = af.shifted_growth.projection.accumulate(
    initial=af.opening_av,
    multiplier=af.shifted_growth,
    addend=af.prem_to_av,
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

This IS a linear recurrence: `multiplier = (1 + rate)`, `addend = cum_fixed * rate`.

```python
# Fixed component: cumulative interest + fees (no feedback)
af.cum_fixed = (af.interest + af.fees).cum_sum()

# Appreciation rate per period
af.rate = af.hpi_pct  # from assumption table

# Linear recurrence on cumulative gain
af.cum_gain = af.rate.projection.accumulate(
    initial=0.0,                          # no gain at t=0
    multiplier=(1.0 + af.rate),           # prior gains also appreciate
    addend=af.cum_fixed * af.rate,        # new base appreciates
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
    multiplier=af.growth,
    addend=af.net_flow,
)
```

---

## Pattern 4: Running Balance with Variable Flows

Cash balance with irregular deposits and withdrawals:

```
cash[t] = cash[t-1] + inflows[t] - outflows[t]
```

With no growth on the balance this is not a recursion at all — the closed
form is a cumulative sum (*Closed-form by default*), and `cum_sum()` applies
within each policy's list:

```python
af.net_flow = af.inflows - af.outflows

af.cash_balance = af.opening_cash + af.net_flow.cum_sum()
```

Reach for `accumulate()` only when the balance genuinely grows (`multiplier`
≠ 1). Its `multiplier` takes a list (one factor per period) or a scalar —
a bare `multiplier=1.02` broadcasts to each policy's own timeline. A
growth-free `multiplier=1` still reads better as the `cum_sum()` closed form above.

---

## Pattern 5: Rolling a Reserve Back from the Last Period

A workbook column whose row reads the row *below* it, `V[t] = v[t]·V[t+1] + cf[t]`, is one
line — `accumulate(initial=…, multiplier=v, addend=cf, reverse=True)`, rolled back from each
policy's own last period — and `list.reverse()` is a declared operation:

```python
af.reserve = af.cf.projection.accumulate(
    initial=0.0,              # the value after the last period
    multiplier=af.v,
    addend=af.cf,
    reverse=True,
)
af.cf_rev = af.cf.list.reverse()    # declared: portable, recorded as itself
```

With `cf = [1, 2, 3]` and `v = 0.9` this gives `reserve = [5.23, 4.7, 3.0]`: `V[2] = 3`,
`V[1] = 0.9·3 + 2`, `V[0] = 0.9·4.7 + 1`. A policy with a shorter timeline rolls back from its
own last period. `prospective_value()` is the special case of pure discounting; reach for
`reverse=True` when the recursion carries anything else.

---

## Pattern 6: Multi-State Occupancy (Probability Moving Between States)

Multi-state occupancy — probability moving between states, such as disability with recovery
or levels of care — is not a rollforward. Write one `accumulate()` per state on the fixed-step
axis, ordered so each state's inflow reads only states already computed; with recovery, repeat
those calls in sweeps until a sweep changes nothing. The rollforward is for running balances
(one account, or several, as a GMDB ratchet reads the fund) whose within-period charges depend
on the balance.

Multi-state occupancy has no named form in 1.0, and the rollforward is not it: a rollforward
step that adds a share of another state (`p0@bop * mu01`) is refused, because the kernel
fetches named columns and computes no arithmetic of its own.

**No recovery** (healthy → sick → dead, healthy → dead): order the states so each reads only
those before it. An Euler step of `h` years on the fixed-step axis (see
[model-phases.md](model-phases.md)):

```python
H, N = 0.1, 200                       # steps of 0.1 years, 20 years
af = ActuarialFrame(pl.DataFrame({"policy_id": ["A", "B"], "x": [40.0, 55.0]}))
af = af.projection.set(n_periods=N, step_years=H)
af.age = af.x + af.projection.t_years()
af.mu01 = 0.0004 * (0.08 * af.age).exp()      # healthy -> sick
af.mu02 = 0.0002 * (0.09 * af.age).exp()      # healthy -> dead
af.mu12 = 0.0010 * (0.08 * af.age).exp()      # sick -> dead

# healthy reads no other state: a running product, opened at 1.0
af.p0 = (1 - H * (af.mu01 + af.mu02)).projection.previous_period(fill_value=1.0).cum_prod()
# sick reads healthy: p1[k+1] = p1[k] * (1 - h*mu12[k]) + h*mu01[k]*p0[k]
af.p1_after = af.mu12.projection.accumulate(
    initial=0.0, multiplier=(1 - H * af.mu12), addend=H * af.mu01 * af.p0
)
af.p1 = af.p1_after.projection.previous_period(fill_value=0.0)   # open at 0.0
af.p2 = 1 - af.p0 - af.p1                                         # dead
```

Each state holds one value per boundary, `0..N`, bit-equal to a hand-written Euler loop over
the same intensities, and every line records as a core operation. The intensities come from
wherever the basis keeps them — a `Table.lookup` keyed on `af.step` or the attained age works
the same.

**With recovery** (healthy ⇄ sick, both → dead) no order reads only computed states, so
iterate: start from a guess for one state and recompute both in sweeps. The Python loop runs
when the model is *built* — it writes the expression, it does not touch rows:

```python
H, N = 0.1, 50
mu01, mu02, mu10, mu12 = 0.05, 0.01, 0.30, 0.20     # constant here; columns work the same
af = ActuarialFrame(pl.DataFrame({"policy_id": ["A"]}))
af = af.projection.set(n_periods=N, step_years=H)
af.zero = af.projection.t_years() * 0.0
af.p1 = af.zero                                       # first guess: nobody sick
for _ in range(SWEEPS):
    af.p0_after = af.zero.projection.accumulate(
        initial=1.0, multiplier=(1 - H * (mu01 + mu02)), addend=H * mu10 * af.p1
    )
    af.p0 = af.p0_after.projection.previous_period(fill_value=1.0)
    af.p1_after = af.zero.projection.accumulate(
        initial=0.0, multiplier=(1 - H * (mu10 + mu12)), addend=H * mu01 * af.p0
    )
    af.p1 = af.p1_after.projection.previous_period(fill_value=0.0)
```

**Precision, stated.** Sweep `k` is exact at least through step `k`. On this example, 5
sweeps are bit-exact through step 13 of 50 (largest error 2.8e-10) and 10 sweeps are bit-exact
at every step; more sweeps change nothing. Check convergence on your own basis — build with
`k` and `k + 1` sweeps and compare — because the sweep count is a convergence setting for the
basis, not a property of the product. Every sweep leaves a superseded definition per state on
the record (`af.graph.versions("p0")` lists them).

---

## Pattern 7: Backward Recursion with a Floor

A floored backward recursion (`MAX(floor, …R[1]C…)`) has no named form in 1.0. `accumulate`
cannot carry the `max`, and the reverse running maximum some floors reduce to
(`cum_max(reverse=True)`) is not declared — through `.polars_native()` it records
`engine_native`, which runs only on Polars. The portable route is a **doubling scan** in core
operations: each period holds the map `x ↦ max(c, α + β·x)`, and each pass composes it with
the map `2^j` periods on, so ⌈log₂ T⌉ passes give every period its value.

```python
# V[t] = max(floor, a[t] + b[t] * V[t+1]), with V = 0 after the last period.
af.c = af.floor.projection.broadcast_to_periods(like=af.a)
af.al = af.a
af.be = af.b
T = 1200                           # at least the longest policy's period count
k = 1
while k < T:                       # ceil(log2 T) passes, written at build time
    c2 = af.c.projection.at_period(k, fill_value=0.0)    # past the end: the constant 0 map
    al2 = af.al.projection.at_period(k, fill_value=0.0)
    be2 = af.be.projection.at_period(k, fill_value=0.0)
    cand = af.al + af.be * c2
    af.c_next = when(af.c >= cand).then(af.c).otherwise(cand)   # a tie keeps the floor
    af.al_next = af.al + af.be * al2
    af.be_next = af.be * be2
    af.c, af.al, af.be = af.c_next, af.al_next, af.be_next
    k *= 2
af.V = when(af.c >= af.al).then(af.c).otherwise(af.al)
```

Here `a` is the period's net amount and `b` its `v·p`. Against a plain loop the scan agrees to
1e-14 relative at 600 periods and 1e-12 at 1,200, and floors in the same periods; it drifts
slowly with the horizon, so state the tolerance you reconcile to. A tie at the floor must
prefer the floor (`>=`). For a non-zero value after the last period, the past-the-end map is
that constant, not `fill_value=0.0`.

---

## When `accumulate` Doesn't Fit

Some recurrences can't be expressed as `state[t] = state[t-1] * multiplier[t] + addend[t]`:

- **Charges that depend on the running balance** (COI on net amount at risk, IUL floor/cap on the in-period credit, AV-banded fees, GMDB ratchets) — use the rollforward kernel (`af.projection.rollforward`).
- **Probability moving between states** (disability with recovery, levels of care) — not the rollforward: one `accumulate` per state, Pattern 6.
- **A backward recursion with a floor or a max** — the doubling scan, Pattern 7.
- **Newton-Raphson or solver-based calculations** (IRR, implied volatility) — iterative solvers, not projection patterns.
- **Discrete-state staging transitions** (IFRS 9 stage 1→2→3) — `when/then/otherwise` chains, not `accumulate`.
- **Nested stochastic** (outer × inner scenarios) — framework-level feature, not model-level.

If you're not sure: try to write the recurrence as `state[t] = state[t-1] * f(inputs[t]) + g(inputs[t])`. If `f` and `g` truly don't depend on `state`, it's linear → `accumulate`. If either depends on the running balance (even via a max/min/clip), it's a state-machine → rollforward kernel.
