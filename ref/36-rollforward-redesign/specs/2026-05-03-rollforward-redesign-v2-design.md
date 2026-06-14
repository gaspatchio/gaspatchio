# Rollforward Redesign v2 — State-Machine Kernel from Typed Inputs

**Date:** 2026-05-03
**Status:** Design proposal (v2)
**Authors:** Matt Wright, Claude
**Branch:** `gsp-92-rollforward-redesign`
**Drives:** GSP-92 (cross-state arithmetic with mid-period column derivation)
**Aligns with:** GSP-95 (semantic IR + Polars backend boundary; Phases 1–3 shipped on `develop`)
**Supersedes:** [v1 spec (2026-04-30)](./2026-04-30-rollforward-redesign-design.md) for the design-journey context, and the rollforward shipped in GSP-86 (PR #80) for the implementation — wholesale rewrite, no adaptors, no compatibility shims.

**Evidence basis:**
- `research/2026-05-02-validation-pass-summary.md` — first validation pass (synthetic LLM-personas; hypothesis generation, not field validation)
- Real-evidence pass (primary regulations, OSS issue trackers, published industry papers) — synthesis captured in §17.2 of this spec; standalone writeup at `research/2026-05-03-real-evidence-grounding.md` is pending
- `research/2026-05-03-schedule-design.md` — Schedule design pass (QuantLib lineage, actuarial OSS state, jurisdictional conventions, GSP-92 pain probe)

---

## 1. What this is

**gaspatchio is a state-machine rollforward kernel for actuarial projection, composed from typed inputs.**

- Inputs: `Curve`, `Table`, `Schedule`, `MortalityTable`.
- Kernel: `rollforward(states=, schedule=)` with named `(state, point)` transitions.
- Identity: one hash, `spec_fingerprint`, over the engine-portable canonical form.
- Execution: per-policy, vectorised in Rust via Polars streaming.

That is the spec in five lines. Everything in the rest of this document either supports this story or is deliberately not in scope.

**What it isn't.** A complete actuarial platform. IFRS 17 disclosure assembly, Solvency II SCR aggregation, stochastic projection, contract-boundary disclosure templates — each is a sibling concern. The core stays small.

**Pre-release, breaking-change posture.** This is a rewrite, not an evolution. The shipped GSP-86 rollforward (PR #80) is **deleted**, not adapted — no backwards-compatibility shims, no API-stability guarantees, no migration utilities. Existing models that use the old API will fail to import after the 0.4.0 release; this is intentional. gaspatchio is pre-release software, and the redesign exists *because* the v1 surface was wrong. Preserving it is a mistake.

**Who it's for.** Actuaries who need to audit every formula in a model. LLMs generating model code from text descriptions. Teams that want vectorised projection without giving up clarity.

---

## 2. Design principles

The eight principles below govern this design. Six are unchanged from `core/project.md`; two are introduced by GSP-95 and the run-determinism work.

| # | Principle | Source |
|---|-----------|--------|
| 1 | No Python loops in the hot path — all time-stepping inside Rust | `core/project.md` |
| 2 | Polars parallelises across policies; the kernel processes one row at a time | `core/project.md` |
| 3 | Pre-compute what you can in Python; only state-dependent work runs in the kernel | `core/project.md` |
| 4 | The Python API reads like the formula — actuary sees business logic, not implementation | `core/project.md` |
| 5 | Names match what an actuary would say — and what an LLM would search for | `core/project.md` |
| 6 | The spec IS the model — declarative chain is simultaneously executable AND machine-inspectable data | `core/project.md` |
| 7 | The rollforward IR (states, points, transitions, schedule, batch_axes, named operations) is engine-agnostic by construction. Transition bodies use the existing gaspatchio DSL surface (proxies, operators, `when().then().otherwise()`). Polars-specific kernel work lives in `polars_backend/`. | GSP-95 (shipped) |
| 8 | Audit identity is one hash. `spec_fingerprint()` captures the engine-portable canonical form (recipe identity). A minimal `action_key()` extends it with input-data SHA, gaspatchio version, and git SHA — matching ASOP 56's tool-version-string granularity, not Bazel's full platform envelope. | Real-evidence pass |

Principle 4 deserves a note in the context of feedback-loop calculations. Single-line column-vectorised formulas are impossible when state at `t` feeds back into the calculation at `t+1`. The actuarial literature for these cases (Bauer/Kling/Russ, Holz/Kling/Russ) uses a *points-and-transitions* notation: `G(t_k^−)` for the state just before an event, `G(t_k^+)` for just after. Mirroring that notation in the API is faithful to principle 4 — it matches the textbook representation of the problem class.

**`rollforward` vs `accumulate` — when to reach for which.** `rollforward` is for state-machine recurrences with feedback at the period boundary (state at `t` depends on state at `t-1` after one or more transitions). For *linear* recurrences without state-feedback — e.g. term-life reserve as a sum of discounted expected cash flows, with no carry-forward state — the existing `accumulate()` primitive is the right tool and `rollforward` is overkill. §4.3 walks through a Term-Life worked example as a deliberate *not-a-rollforward* case.

---

## 3. The state-machine model

A rollforward is a graph of `(states, points, transitions, schedule, batch_axes)`:

- A **state** is a named accumulator with an initial value (e.g., `"av"`, `"aw"`, `"shadow"`).
- A **point** is a named structural location within a single time period. Every period has implicit `bop` and `eop` points. Additional points (`post_coi`, `after_growth`, `after_payment`, etc.) are declared by the actuary when mid-period state needs to be addressable.
- A **transition** writes one state and is located between two points (or implicitly `bop → eop` if points are not declared). A transition's body is either a named primitive operation (`.add(...)`, `.grow(...)`, `.ratchet(...)`) or — when primitives run out — a semantic-IR expression.
- A **read** of state `S` at point `P` is written `rf["S"].at("P")`. It is a typed reference, resolved by the compiler to a kernel capture slot. There are no string labels in the addressing.
- A **schedule** is a typed `Schedule` value (see §4.16) carrying period boundaries, day-count, and calendar. The kernel reads `dt[t]` from the schedule for time-aware operations like `.grow(rate)`. Default for products that don't need calendar discipline: `Schedule.integer_periods(n_periods, OneTwelfth)` — a constant 1/12 dt with no calendar arithmetic.
- **`batch_axes`** is a tuple of axis names the kernel iterates over. Default: `("policy",)` — Polars parallelises across rows. Future: `("scenario", "policy")` for stochastic projection (Phase 3+ sibling primitive). Phase 1's Polars backend asserts `batch_axes == ("policy",)` and rejects others. The field exists in the IR today as cheap forward-compat for canonical-form stability when the JAX-backed stochastic primitive lands; see §13.3. **Honest framing:** this is speculative forward-compat informed by JAX's `vmap`-over-`scan` pattern, not field-validated as an actuarial primitive. Phase 1 commits to the metadata slot only.

The kernel evaluates one period at a time, walking transitions in declared order. Within a period, the points define a partial order: writes to a state must respect the point sequence, and reads must reference points that have been written or are `bop`.

This is the **same notation Bauer/Kling/Russ use in the literature** for VA living benefits, with `S^−` and `S^+` becoming `rf["S"].at("pre_event")` and `rf["S"].at("post_event")`. The mapping is intentional. Note that Bauer/Kling/Russ is canonical *for VA living benefits*, not for the broader OSS actuarial world — see §17.2.

**Single-state collapse.** When `states` has one entry and no `points` are declared, the API surface collapses to a method chain on the state, identical in feel to today's API. No extra ceremony for simple products.

---

## 4. API reference and worked examples

This section is structured as a *climb*: each example introduces one new typed input. By §4.13 the reader has seen full power. Side-by-side comparisons with the current API are included where the current API can express the calculation.

### 4.1 Constructor

```python
# Single state, no points (the simplest case)
rf = af.projection.rollforward(states={"av": af.av_init})

# Single state with named mid-period points
rf = af.projection.rollforward(
    states={"av": af.av_init},
    points=["bop", "post_coi", "eop"],   # bop and eop are always present
)

# Multi-state with explicit schedule
rf = af.projection.rollforward(
    states={"av": af.av_init, "aw": af.aw_init},
    points=["bop", "after_growth", "after_payment", "eop"],
    schedule=Schedule.from_inception(af.contract_inception, n_periods=240, frequency="1M"),
)

# Increment tracking and lapse condition
rf = af.projection.rollforward(
    states={"av": af.av_init, "guarantee": af.guarantee_init},
    points=["bop", "eop"],
    track_increments=True,
    lapse_when_all_non_positive=["av", "guarantee"],
)
```

### 4.2 Per-state operations

`rf["state_name"]` returns a *state handle*. Operations chain on the handle:

| Method | Formula | Notes |
|---|---|---|
| `.add(amount, label=...)` | `s += amount[t]` | Premiums, additions |
| `.subtract(amount, label=...)` | `s -= amount[t]` | Withdrawals, fees |
| `.charge(rate, label=...)` | `s *= 1 - rate[t]` | M&E charges |
| `.grow(rate, label=...)` | `s *= 1 + rate[t] * dt[t]` | Interest credit; dt from schedule |
| `.grow_capped(rate, *, floor, cap, label=...)` | `s *= 1 + clamp(rate[t], floor, cap) * dt[t]` | IUL crediting |
| `.deduct_nar(coi_rate, *, death_benefit, label=...)` | `s -= coi_rate[t] * (death_benefit[t] - s)` | UL COI |
| `.ratchet(*, to, when=None, label=...)` | `s = max(s, to[t]) if when[t] else s` | GMxB ratchet |
| `.floor(value)` | `s = max(s, value)` | Non-negativity |
| `.between(p1, p2)` | scope-marker | Subsequent ops apply between points `p1` and `p2` |

`rf["av"]` returns a `pl.Expr` — a lazy reference to the rollforward kernel's per-period result for state `"av"`. Assigning it (`af.av = rf["av"]`) registers a column expression in the ActuarialFrame's lazy plan; nothing computes until `af.collect()`. Multiple references to the same rollforward (`rf["av"]`, `rf["av"].at("post_coi")`, `rf.increment("COI")`) share the underlying plugin call **by construction**: the compiler walks every `rf[...]` accessor in the lazy plan, gathers the union of requested fields into a single `captures` kwarg, and emits one plugin Expr that all accessors field-extract from. The kernel is invoked once per chunk by construction — Polars CSE has nothing to fold. See §7 for the Struct-emission shape and §8.3 for what the lazy plan looks like at `af.collect()`.

`rf["state"].at("point")` returns a typed `(state, point)` reference. Compose into expressions with operators (`*`, `+`, `pl.max_horizontal`). Cannot be confused with a column — the compiler checks point validity.

`rf.increment(label)` returns the per-period delta attributed to the operation labelled `label`. Used for IFRS 17 movement-analysis attribution.

### 4.3 Worked example — Term Life (not a rollforward case)

Term life has a linear reserve recurrence with no state-dependent charges. Use `accumulate()`, not `rollforward()`. Confirms that this redesign does not "every problem looks like a rollforward."

```python
# No rollforward needed. Use accumulate() for the linear reserve recurrence.
af.reserve = (
    af.projection
      .accumulate(af.reserve_init, multiply=af.discount_factor, add=af.expected_claims_minus_premium)
)
```

### 4.4 Worked example — Whole Life (introduces `Schedule` and `Curve`)

Simple multiplicative growth with charges and additions. No mid-period state needed. First example to introduce typed period semantics (`Schedule`) and a typed term structure (`Curve`).

```python
schedule = Schedule.from_calendar_grid(
    start_date=af.valuation_date,
    n_periods=240,
    frequency="1M",
    calendar=NullCalendar(),         # default — every day is a business day
    day_count=DayCount.OneTwelfth(), # default — constant 1/12 per month
)

interest = Curve.from_zero_rates(
    tenors=[1, 5, 10, 30],
    rates=af.eur_zero_rates,                  # per-row list column, externally loaded
    day_count=DayCount.actual_actual_isda(),
)

rf = af.projection.rollforward(states={"av": af.cv_init}, schedule=schedule)

(
    rf["av"]
    .add(af.premium, label="Premium")
    .charge(af.expense_rate, label="Expenses")
    .grow(interest.spot_rate(t=schedule.year_fractions()), label="Interest credit")
    .floor(0)
)

af.cv = rf["av"]
```

What's new vs the v1 line count: `schedule` is declared, `interest` is a typed Curve, `.grow` is `dt`-aware. For products that don't care about calendar discipline, drop `schedule=` and you get the implicit integer-period default.

### 4.5 Worked example — Universal Life with COI (introduces `Table` and `MortalityTable`)

The textbook UL case: state-dependent COI charge based on net amount at risk. Introduces `Table` (the existing `gaspatchio_core.assumptions.Table`) and `MortalityTable` (a thin actuarial-convention wrapper).

```python
mortality = MortalityTable(
    table=Table.from_file("CSO_2017_male.parquet", dimensions={"age": "age"}, value="qx"),
    age_basis="age_last_birthday",
    structure="aggregate",
)

expense = Table.from_file("ul_expense.parquet",
                          dimensions={"duration": "policy_year"}, value="rate")

rf = af.projection.rollforward(states={"av": af.av_init}, schedule=monthly_schedule)

(
    rf["av"]
    .add(af.premium, label="Premium")
    .deduct_nar(mortality.at(age=af.attained_age),
                death_benefit=af.sum_assured,
                label="COI")
    .charge(expense.at(duration=af.policy_year), label="Admin")
    .grow(af.interest_rate, label="Interest credit")
    .floor(0)
)

af.av = rf["av"]
```

Side-by-side with v1: identical code shape after the typed inputs are declared. The redesign costs nothing for products that don't need mid-period state, and the typed inputs are pay-as-you-go: you can still pass raw columns (`af.coi_rate`, `af.admin_rate`) if you'd rather skip the typed wrappers.

### 4.6 Worked example — Universal Life with IFRS 17 mid-period attribution

Same UL, but the auditor needs to see the AV value *after* COI, before interest is credited. Today this requires a `.capture("av_post_coi")` step with an audit-fragile label. Redesigned, the actuary names the structural point.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init},
    points=["bop", "post_coi", "eop"],
    schedule=monthly_schedule,
    track_increments=True,
)

rf["av"].between("bop", "post_coi") \
    .add(af.premium, label="Premium") \
    .deduct_nar(mortality.at(age=af.attained_age), death_benefit=af.sum_assured, label="COI")

rf["av"].between("post_coi", "eop") \
    .charge(af.admin_rate, label="Admin") \
    .grow(af.interest_rate, label="Interest credit") \
    .floor(0)

af.av           = rf["av"]                   # default: eop value
af.av_post_coi  = rf["av"].at("post_coi")    # mid-period read — typed, audit-stable
af.coi_amount   = rf.increment("COI")        # increment series for IFRS 17 attribution
```

The reference `rf["av"].at("post_coi")` is a typed `(state, point)` pair. Renaming a step's label cannot break it. Reordering `between(...)` calls cannot break it. Only renaming `"post_coi"` in the `points` list breaks it — and that's a search-and-replace that touches every reference visibly.

### 4.7 Worked example — VA + GMDB ratchet (canonical Bauer/Kling/Russ)

The classical VA living-benefit case. AV grows at fund returns; the death benefit guarantee ratchets to AV high-water-mark on each anniversary.

Bauer/Kling/Russ §3.3.2: `G^D_{t+1} = max{G^D_t · (1+i), A^+_{t+1}}`.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "guarantee": af.av_init},   # guarantee starts at premium
    points=["bop", "after_growth", "eop"],
    schedule=monthly_schedule,
    lapse_when_all_non_positive=["av"],   # only AV; guarantee can persist as a death benefit
)

# Fund: grow at fund return rate
rf["av"].between("bop", "after_growth").grow(af.fund_return, label="Fund return")
rf["av"].between("after_growth", "eop").floor(0)

# Guarantee: roll up at the contractual rate, then ratchet to AV on anniversaries
rf["guarantee"].grow(af.roll_up_rate, label="Roll-up")
rf["guarantee"].ratchet(
    to=rf["av"].at("after_growth"),
    when=monthly_schedule.anniversary_mask(),
    label="GMDB ratchet",
)

af.av           = rf["av"]
af.guarantee    = rf["guarantee"]
af.death_benefit = pl.max_horizontal(af.av, af.guarantee)
```

`.ratchet(to=expr, when=mask)` is the GMxB primitive. The `to` argument is any semantic-IR expression — typically a state read at a point, optionally scaled by a precomputable column. The `when` argument is a boolean mask column gating periodic activation; here it's derived from the schedule (`monthly_schedule.anniversary_mask()` with the schedule's roll convention applied).

### 4.8 Worked example — VA + GLWB (Holz/Kling/Russ)

Guaranteed Lifetime Withdrawal Benefit with anniversary step-up of the income base. The actual withdrawal each period is the **greater of** the stated AW or a formulaic withdrawal.

Holz/Kling/Russ §3.2.2(b): `G^E_{t+} = max(G^E_{t−}, x_W · A^+_t)`.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "aw": af.aw_init},
    points=["bop", "after_growth", "after_payment", "eop"],
    schedule=monthly_schedule,
)

# AV: grow, then deduct the actual payment, then floor at 0
rf["av"].between("bop", "after_growth").grow(af.fund_return)

# Actual payment is max(stated AW, formulaic withdrawal driven by fund × x_W)
withdrawal = pl.max_horizontal(
    rf["aw"].at("bop"),                              # G^E_{t−}
    rf["av"].at("after_growth") * af.x_W,            # x_W · A^+_t
)

rf["av"].between("after_growth", "after_payment").subtract(withdrawal, label="Withdrawal")
rf["av"].between("after_payment", "eop").floor(0)

# AW: anniversary step-up to the formulaic value if it exceeds current AW
rf["aw"].ratchet(
    to=rf["av"].at("after_growth") * af.x_W,
    when=monthly_schedule.anniversary_mask(),
    label="AW step-up",
)

af.av = rf["av"]
af.aw = rf["aw"]
```

The expression for `withdrawal` is exactly Holz/Kling/Russ's notation, transliterated. The actuary auditing this code is checking against the same equation in the paper.

### 4.9 Worked example — GSP-92 VA Illustration (the full hard case)

The product that drove this redesign. Four declared points within each month, two states, an anniversary-gated ratchet, and a "greater of" payment rule. The current 244-line numpy kernel reduces to this:

```python
rf = af.projection.rollforward(
    states={"fund": af.fund_init, "aw": af.aw_init},
    points=["bop", "after_growth", "after_payment", "eop"],
    schedule=Schedule.from_inception(
        af.contract_inception, n_periods=1200, frequency="1M",
        calendar=NullCalendar(), day_count=DayCount.OneTwelfth(),
    ),
)

# Fund: grow at net rate (1 + BA - gib - z), then deduct actual payment
rf["fund"].between("bop", "after_growth") \
    .grow(af.one_plus_ba - af.gib_rate - af.z_rate, label="Net growth")

# Actual payment = (1+BA) · max(stated AW, formulaic = fund · bc_factor / 12)
withdrawal = af.one_plus_ba * pl.max_horizontal(
    rf["aw"].at("bop"),
    rf["fund"].at("after_growth") * af.bc_factor / 12,
)

rf["fund"].between("after_growth", "after_payment").subtract(withdrawal, label="Payment")
rf["fund"].between("after_payment", "eop").floor(0)

# AW: anniversary step-up
rf["aw"].ratchet(
    to=rf["fund"].at("after_growth") * af.bc_factor * af.fac / 12,
    when=rf.schedule.anniversary_mask(),
    label="AW step-up",
)

af.fund = rf["fund"]
af.aw   = rf["aw"]
```

The 244-line numpy kernel becomes ~15 lines of declarative builder code. The acceptance test in `gaspatchio-va` (reconciling 25 list-typed columns to `policy_00000065.parquet` over 1200 periods at `atol ≤ 1e-9`) is the validation gate (subject to the §13.0 Phase 0 prerequisite — confirm the gold file's provenance is independent of the v1 numpy kernel before treating it as a release-blocker).

### 4.10 Worked example — IUL with floor/cap and segment lookback

Indexed Universal Life: crediting is bounded by a floor and cap, applied at segment maturity. A separate "high-water" tracker records the segment's lookback maximum. No cross-state-with-capture is needed — confirms that non-VA products use *components* of the shape, not the whole.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "hwm": af.av_init},
    schedule=monthly_schedule,
)

(
    rf["av"]
    .add(af.premium, label="Premium")
    .charge(af.me_rate, label="M&E")
    .grow_capped(af.index_return, floor=af.crediting_floor, cap=af.crediting_cap, label="Indexed credit")
    .floor(0)
)

# High-water mark: ratchet to AV's end-of-period value with no gating.
# This IS running max — no separate primitive needed.
rf["hwm"].ratchet(to=rf["av"].at("eop"), label="Lookback HWM")

af.av  = rf["av"]
af.hwm = rf["hwm"]
```

### 4.11 Worked example — UL with secondary guarantee (shadow account)

Shadow account that determines no-lapse-guarantee status. The shadow runs independently of the fund AV (per AG 38 mechanics) — cross-state at period boundaries only, no mid-period capture required.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "shadow": af.shadow_init},
    schedule=monthly_schedule,
    lapse_when_all_non_positive=["av"],   # primary lapse on AV alone; shadow gates SG
)

# Fund: standard UL
(
    rf["av"]
    .add(af.premium, label="Premium")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .charge(af.admin_rate, label="Admin")
    .grow(af.interest_rate, label="Interest")
    .floor(0)
)

# Shadow account: independent recurrence with its own COI/loads/credit table
(
    rf["shadow"]
    .add(af.premium, label="Shadow premium")
    .charge(af.shadow_load_rate, label="Shadow load")
    .deduct_nar(af.shadow_coi_rate, death_benefit=af.sum_assured, label="Shadow COI")
    .grow(af.shadow_credit_rate, label="Shadow credit")
)

af.av     = rf["av"]
af.shadow = rf["shadow"]
af.sg_active = rf["shadow"] > 0
```

No cross-state reads inside the kernel; `af.sg_active` is a downstream column comparison after the rollforward returns.

### 4.12 Worked example — IFRS 17 OCI parallelism (two `Curve`s, same kernel)

The OCI option in IFRS 17 requires that the locked-in discount rate (set at initial recognition) and the current discount rate are *both* applied to the same projection cash flows. The CSM is rolled forward at the locked-in curve; OCI captures the current-vs-locked delta.

In v1's spec this would have required state duplication. With typed `Curve` inputs and the schedule discipline, it's two curves and one rollforward run twice with curve substitution — same kernel.

```python
locked_in = Curve.from_zero_rates(
    tenors=af.locked_tenors, rates=af.locked_rates, day_count=DayCount.ActualActualISDA()
)
current = Curve.from_zero_rates(
    tenors=af.current_tenors, rates=af.current_rates, day_count=DayCount.ActualActualISDA()
)

# Same projection logic, two curves
def project(discount_curve: Curve) -> pl.Expr:
    rf = af.projection.rollforward(states={"lrc": af.unearned_premium}, schedule=monthly_schedule)
    rf["lrc"].grow(discount_curve.spot_rate(monthly_schedule.year_fractions()), label="Discount unwind")
    rf["lrc"].add(af.expected_claims, label="Claims")
    rf["lrc"].subtract(af.expected_premium, label="Premium")
    return rf["lrc"]

af.lrc_locked  = project(locked_in)
af.lrc_current = project(current)
af.oci_delta   = af.lrc_current - af.lrc_locked
```

The point: regulatory parallelism is *curve substitution*, not kernel duplication. The IR is unchanged between the two runs — `spec_fingerprint` for the projection function is identical; only the input data SHA differs in `action_key`.

The full IFRS 17 cohort/CSM/coverage-unit/loss-component machinery is **out of Phase 1 scope** — deferred until customer demand surfaces. Whether it eventually extends core, lands in a `gaspatchio-ifrs17` sibling, or stays as third-party recipes is a future decision (see §13.4). Core gives this primitive support today; the disclosure pack assembly does not.

### 4.13 Worked example — Solvency II SCR interest stress (three `Curve`s, same kernel)

SII Standard Formula interest stress is parallel ±100bps shifts from the base RFR. SCR contribution is `max(BEL_up − BEL_base, BEL_down − BEL_base)`.

Same projection function, three curves:

```python
base = Curve.from_zero_rates(
    tenors=[1, 5, 10, 30],
    rates=af.eur_zero_rates_2026q2,
    day_count=DayCount.actual_actual_isda(),
)
up   = base.shift_parallel(bps=+100)
down = base.shift_parallel(bps=-100)

af.bel_base = project(base)
af.bel_up   = project(up)
af.bel_down = project(down)
af.scr_int  = pl.max_horizontal(af.bel_up - af.bel_base, af.bel_down - af.bel_base)
```

Three calls to the same `project(...)` function with the same `spec_fingerprint`; three different `action_key`s differing only in the input curve column SHAs. SCR aggregation across modules (interest × equity × longevity × …) is **out of Phase 1 scope** — deferred (see §13.4); home decision (core extension, `gaspatchio-solvency` sibling, or third-party) follows customer demand.

### 4.14 The `Curve` type

Typed term structure. Phase 1 ships explicit constructors only; regulatory loaders are deferred (see below). Operations preserve the curve's day-count and date metadata.

```python
# Phase 1 constructors — explicit data
curve = Curve.from_zero_rates(
    tenors=[1, 5, 10, 30],            # years
    rates=[0.030, 0.032, 0.035, 0.040],
    day_count=DayCount.ActualActualISDA(),
)

# Or from par rates
curve = Curve.from_par_rates(
    tenors=[1, 5, 10, 30],
    par_rates=[0.030, 0.033, 0.036, 0.041],
    day_count=DayCount.ActualActualISDA(),
)

# Use as a per-period column in any rollforward
spot = curve.spot_rate(monthly_schedule.year_fractions())     # Series
df   = curve.discount_factor(monthly_schedule.year_fractions())
fwd  = curve.forward_rate(t1=schedule.year_fraction(0), t2=schedule.year_fraction(12))

# Shift / stress
up = curve.shift_parallel(bps=+100)
key_rate = curve.key_rate_shift(tenor=10, bps=25)
```

**Why this is in core (honest framing).** Typed yield curves are an ergonomic improvement that the Julia actuarial ecosystem converged on — `FinanceModels.jl` (the JuliaActuary successor to `Yields.jl`), with ~50 issues across the curve-construction / interpolation / parallel-shift orbit. lifelib v0.8 added an `economic_curves` library. The synthetic-validation pass overstated this as a "Pillar 1 blocker" — primary regulations and Big-4 IFRS 17 papers don't name typed curves as a documented gap. The honest position is: **typed curves are a SOTA ergonomic lead we're choosing to take, complementing the column-of-rates surface that remains supported.** Both surfaces co-exist; pay-as-you-go for users who don't want the typed wrapper.

**Phase 1 vs production loaders.** Phase 1 ships explicit constructors only. Regulatory loaders (EIOPA RFR with Smith-Wilson reconstruction and VA/MA hooks, NAIC tables, Fed term-structure publications) involve monthly publication tracking and either live HTTP, bundled-static-data, or file-loader semantics — non-trivial scope that doesn't belong in the typed-input core. Deferred until customer demand surfaces; the home (extending `Curve` directly, a separate package, or a third-party recipe) is a future decision and doesn't gate Phase 1.

**Pattern reference.** `FinanceModels.jl` (JuliaActuary, successor to `Yields.jl`). Real OSS comparator with documented community demand for curve operations.

### 4.15 The `Table` and `MortalityTable` types

`gaspatchio_core.assumptions.Table` already exists in the codebase (see `bindings/python/gaspatchio_core/assumptions/_api.py`). It's a generic typed multi-dimensional assumption table with composable `Dimension` types (`DataDimension`, `MeltDimension`, `CategoricalDimension`, `ComputedDimension`), file loading, registry, shock support, and storage-mode optimisation. This redesign **does not introduce a new primitive** — it integrates the existing `Table` into the rollforward narrative.

```python
# Existing Table API — used in this redesign's worked examples as-is
from gaspatchio_core.assumptions import Table

lapse = Table(
    name="ul_lapse",
    source="ul_lapse.parquet",
    dimensions={"duration": "policy_year", "product": "product_type"},
    value="lapse_rate",
)

# Per-period column for use in rollforward
lapse_rate = lapse.at(duration=af.policy_year, product=af.product_type)
```

`MortalityTable` is a thin actuarial-convention wrapper over `Table`, addressing the documented OSS pain points around mortality-specific conventions ([MortalityTables.jl#107](https://github.com/JuliaActuary/MortalityTables.jl/issues/107) — irregular tables; #119 — age-last vs age-nearest; [heavylight#50](https://github.com/lewisfogden/heavylight/issues/50) — multi-value tables).

```python
mortality = MortalityTable(
    table=Table.from_file("CSO_2017_male.parquet", ...),
    age_basis="age_last_birthday",        # or "age_nearest_birthday"
    structure="aggregate",                 # or "select_ultimate" or "joint"
    select_period=10,                      # optional, for select_ultimate
)

# Convention-aware lookup
qx = mortality.at(age=af.attained_age, duration=af.policy_year)

# Convention-aware lookup is Phase 1; table-conversion utility is Phase 2.
# `with_age_basis(...)` requires choosing a sub-annual mortality assumption (UDD,
# Balducci, or constant-force) — varies by jurisdiction and product. Deferred until
# customer demand surfaces. Phase 1 supports `at(age_basis="...")` for lookup.
```

`MortalityTable` doesn't change the underlying `Table` mechanics — it adds named conventions that an auditor can verify. The existing `Table` continues to work for non-mortality tables (lapse, expense, surrender charges).

**Why this is in core.** `Table` is already there. `MortalityTable` is a thin wrapper addressing real OSS pain points cited above. Together they pair thematically with `Curve` and `Schedule` as the three typed inputs that compose into rollforward.

### 4.16 The `Schedule`, `Calendar`, and `DayCount` types

Period semantics as typed inputs. The design is grounded in `research/2026-05-03-schedule-design.md` — QuantLib lineage for the surface shape, ExperienceAnalysis.jl for the actuarial period boundaries, and US/UK/EU production practice (VM-20/VM-21, Solvency II, IFRS 17) for the conventions and defaults.

```python
from gaspatchio_core import Schedule, Calendar, DayCount

# Default — matches US/UK/EU production practice (~80% of life insurance)
schedule = Schedule.from_calendar_grid(
    start_date=af.valuation_date,
    n_periods=240,
    frequency="1M",
    anchor="month_end",                     # default — normalises start_date to month-end of its month
    calendar=Calendar.null(),               # default — every day is a business day
    # convention defaults: Unadjusted with NullCalendar, ModifiedFollowing with a real calendar
    day_count=DayCount.one_twelfth(),       # default — constant 1/12 per month
)

# Per-policy schedule, anchored on contract inception
schedule = Schedule.from_inception(
    inception_date=af.contract_inception,   # per-row column
    n_periods=360,
    frequency="1M",
    calendar=Calendar.null(),
    day_count=DayCount.one_twelfth(),
)

# Anniversary mask derived from the schedule
mask = schedule.anniversary_mask()

# Year-fraction series for use in transition bodies
yfs = schedule.year_fractions()  # uses the schedule's day_count

# Period boundary dates (for downstream reporting)
dates = schedule.period_dates()  # array of Date values
```

**Convention catalog (Phase 1).** Five day-counts, four calendars, four business-day conventions cover ~95% of real life-insurance production:

| Day-count | Use | Default |
|---|---|---|
| `OneTwelfth` | Constant 1/12 per month, ignore calendar | **Yes** |
| `Actual365Fixed` | UK/sterling, EIOPA-aligned sub-annual | No |
| `Actual360` | USD money-market, asset-side curves | No |
| `Thirty360` (BondBasis) | Legacy bond / mortgage assets | No |
| `ActualActualISDA` | IFRS 17 / general; precise leap-year | No |

| Calendar | Use | Default |
|---|---|---|
| `NullCalendar` | Every day is a business day; matches VM-20/VM-21/IFRS 17 | **Yes** |
| `TARGET` | Eurozone (ECB) settlement | No |
| `UnitedKingdom` | UK PRA reporting | No |
| `UnitedStates` | US calendar for asset side | No |

`JointCalendar(c1, c2)` and `BespokeCalendar(holidays=...)` are escape hatches.

| Business-day convention | Use |
|---|---|
| `Unadjusted` | **Default with `NullCalendar`.** Anniversaries fall where they fall. |
| `ModifiedFollowing` | **Default with a real calendar.** Roll forward, but stay within the same month |
| `Following` | Roll forward |
| `Preceding` | Roll back |

**Construction patterns.** Two named constructors covering the per-policy vs shared-grid distinction:

- `Schedule.from_inception(inception_date, n_periods, frequency, calendar, convention, day_count)` — anchors on a per-policy column. Each row gets its own monthly schedule. Anniversary semantics are intrinsic; no `anchor` parameter — the inception date IS the anchor.
- `Schedule.from_calendar_grid(start_date, n_periods, frequency, anchor, calendar, convention, day_count)` — shared grid for all policies. `anchor` controls how `start_date` is normalised: `"month_end"` (**default**, matches production), `"exact_date"` (no normalisation), `"month_start"`, `"year_end"`. Anniversary becomes a derived per-row mask. Useful for cohort-aggregated reserving / SII reporting.

Both fingerprintable. Both consumed by `rollforward(states=, schedule=)`.

**The default convention (the actuarial reality).** `OneTwelfth + NullCalendar` is the default pair, with month-end anchoring on `from_calendar_grid` — matching what US VM-20/VM-21 practice does, what UK/EU SII practice does, and what IFRS 17 silently allows. Business-day convention defaults **context-dependently**: `Unadjusted` with `NullCalendar` (no holidays exist), `ModifiedFollowing` with any real calendar (production-typical adjustment). The `OneTwelfth` day-count is *not* a QuantLib convention — it's an actuarial simplification that ignores varying month length and is the production default. Phase 1 supports it as the default; QuantLib-style conventions are opt-in.

**Composition with `rollforward`.** The kernel reads `dt[t]` from the schedule and applies it in time-aware operations:

```python
rf["av"].grow(af.spot_rate, label="Interest")
# expands to s *= 1 + spot_rate[t] * schedule.dt[t]
# with OneTwelfth default, dt[t] = 1/12 for all t (equivalent to v1 implicit 1/12)
```

**Leap-year handling.** Canonical actuarial convention: `Date(2020, 2, 29) + 1 year = Date(2021, 2, 28)`. Documented and tested.

**Phase 1 termination semantics.** `lapse_when_all_non_positive` advances a *full* period and zeroes states for remaining periods. There is no partial-`dt` mechanic in Phase 1. This is a documented contract, not a bug. Promote to Phase 2 if real customers need it.

**Phase 1 reporting-grid semantics.** Phase 1 emits per-row schedules from `from_inception` and a shared schedule from `from_calendar_grid`. Aggregation of per-row results onto a separate reporting calendar grid (quarterly QRT, annual IFRS 17 disclosure) is post-processing via existing Polars groupby on `schedule.period_dates()`. A typed `Schedule.aggregate_to(reporting_grid, how=...)` operator is deferred to Phase 2 if customer demand emerges. This is a documented contract, not a gap.

**Fingerprinting.** `Schedule`'s canonical form contains: constructor type (`from_inception` vs `from_calendar_grid`), inception/start date column reference, n_periods, frequency, calendar name, convention, day_count name. All hash into `spec_fingerprint`. Two specs differing only in day-count have different fingerprints — by design.

**The SOTA position.** No OSS actuarial framework currently unifies QuantLib-grade `DayCount` and `Calendar` with actuarial Anniversary semantics. `ExperienceAnalysis.jl` is the closest typed-period comparator (limited to exposure analysis); JuliaActuary's `FinanceModels.jl#155` is an open admission that dates aren't supported. This redesign fills a documented gap.

### 4.17 Contract-boundary primitive

A `contract_boundary` mask is available as an optional kwarg on `rollforward(...)`. It accepts a **closed-subset boolean expression** — the same surface as transition bodies (§7.1) — and follows the same engine-portability discipline (`engine_binding` flag in §6).

```python
rf = af.projection.rollforward(
    states={"reserve": af.reserve_init},
    schedule=schedule,
    contract_boundary=af.is_repriceable,    # closed-subset bool Expr
)

rf["reserve"].grow(af.discount_rate, label="Discount unwind")
rf["reserve"].add(af.expected_claims, label="Claims")
rf["reserve"].subtract(af.expected_premium, label="Premium")

af.reserve = rf["reserve"]
af.contract_boundary_period = rf.first_breach_period()
```

The mask hashes into `spec_fingerprint`. The kernel stops at the first True; subsequent periods produce zeroed states. Composes with `lapse_when_all_non_positive`; whichever fires first wins; `rf.stop_reason()` returns `"lapse" / "contract_boundary" / "horizon"`.

**Domain-specific typed wrappers — deferred.** v1 specified a typed `ContractBoundary(when=, reason=, regulatory_anchor=)` that hashed citation strings into `spec_fingerprint`. The real-evidence pass found this pushes disclosure-pack metadata into core's recipe identity — a halfway position. Domain wrappers (e.g. `IFRS17ContractBoundary`, `SolvencyIIContractBoundary`) would carry their own reason/anchor metadata, hash into a *disclosure-pack-level* fingerprint, and emit a mask Expr for core's kwarg. The home for these wrappers (extending core later, a separate package, or a third-party recipe) is **deferred until customer demand surfaces** — see §13.4. Phase 1 ships the mask kwarg only.

**Honest framing (revised from v1).** Solvency II Article 18, IFRS 17 §33–35, and US LDTI all define a contract boundary. The OSS pattern (lifelib, JuliaActuary, Heavylight) encodes the boundary implicitly via `n_periods`. The real-evidence pass found:

- Regulations require correct *calculation* + *disclosure* — not in-band recording in the model artefact.
- ESMA's October 2024 thematic review found 31% of issuers failed to disclose contract-boundary judgement adequately on first IFRS 17 application — a real *disclosure-side* problem.
- Zero OSS issue-tracker requests for a typed boundary primitive.

**Position:** the mask kwarg is a thin convenience for stopping the kernel at a regulatory boundary. The disclosure-pack assembly that *uses* the boundary lives outside core's Phase 1, where citation metadata can be carried without bloating core's recipe identity.

### 4.18 Coverage gaps acknowledged but deferred

| Primitive | What it would do | Use cases | Phase |
|---|---|---|---|
| `.reset_when(mask, to=expr)` | `state = expr if mask else state` at gate point | IUL segment boundaries, FIA buffer windows | Phase 2 |
| Categorical / status states | Non-numeric state types; transitions over a finite alphabet. Acceptance test: conservation invariant — sum of per-category counts equals initial inforce at every period | Joint-life status, premium-paying status | Phase 3 |
| Sub-period state | Inner ticks within a period | Highest Daily, monthly-averaging IUL | Phase 3 |
| Vector / multi-fund states | Per-element transitions on a `List<Float64>` state | VUL with N sub-accounts | Phase 3 (small-N expressible today) |
| Partial-period `dt` at termination | Year-fraction proration for mid-period lapse | Daily-lapse VAs | Phase 2 |
| GMWB pro-rata withdrawal | Excess-only branch with conditional gate (composes with `.reset_when` + categorical guard) | GMWB pro-rata withdrawal mechanics | Phase 2 |
| Stochastic batch axis | `vmap`-style scenario-axis primitive | AG 43, EV with TVOG, SCR internal model | Phase 3+ |

These are *not* in Phase 1's scope but they share the IR — adding them later requires no breaking change to the canonical form (the `batch_axes` slot is reserved per §3).

---

## 5. Period and ordering semantics

**Period geometry.** A period `t` is a half-open interval `[bop[t], eop[t])` carrying a year-fraction `dt[t]` from the schedule. Time within a period flows from `bop` through any declared mid-period points (in declared order) to `eop`. Across periods, **`bop[t+1]` is identical to `eop[t]`** — no gap, no midnight event.

A transition `.between(p_a, p_b)` is a function: read state at `p_a` (and any cross-state reads at their named points), evaluate the body, write the result at `p_b`. The kernel walks transitions in declared order. "Between" is structural — it identifies which two points the transition reads-from and writes-to, not a duration.

**Discrete vs continuous Ops.** Time-aware Ops (`.grow(rate)`, `.grow_capped(rate, …)`) consume `dt[t]` to scale rates over the period (`s *= 1 + rate[t] * dt[t]`). Discrete Ops (`.add`, `.subtract`, `.charge`, `.ratchet`, `.deduct_nar`, `.floor`) fire instantaneously at a point and ignore `dt`. The schedule's `dt[t]` is the year-fraction of the **whole period**, independent of how many mid-period points partition it. To split the period's accrual across two intervals (rare), declare two `.grow` transitions and pass each a fraction of the rate.

**Period 0.** `bop[0]` is the `init` expression for each state (e.g., `states={"av": af.cv_init}`); `dt[0]` is the schedule's first interval. Phase 1's `Schedule.from_inception` makes period 0 align with the first interval after `contract_inception` — full-period semantics, no proration (terminating-period and inception-period proration deferred to Phase 2 per §4.16).

**Mortality timing.** Phase 1 does not mandate a sub-period mortality assumption (UDD / Balducci / constant force). Models that need a specific assumption express it explicitly in their transition bodies (e.g., `q_x * (1 - q_w / 2)` for "deaths-first under UDD with lapse uniformly distributed"). A typed convention adapter (`MortalityTable.with_subperiod_method(...)` or similar) is deferred to Phase 2 (see §4.15).

**Decrement ordering and timing are convention choices.** Lapse and mortality can fire in either order, at any point you declare. `bop` → mortality → lapse → `eop` is one convention; lapse-first is another; simultaneous-at-mid-period is a third (declare a `mid` point, sum the decrements there). The kernel does not impose a convention — **the actuary's choice of points and transition order *is* the convention**, and `spec_fingerprint` distinguishes them. This is deliberate: there is no industry-universal convention for ordering decrements within a period, and any default would be wrong for half of users. Auditors reading `rf.explain()` see exactly which convention the model uses.

```python
# Convention A — deaths first, then lapses
points=["bop", "post_mort", "post_lapse", "eop"]
rf["fund"].between("bop", "post_mort").subtract(rf["fund"].at("bop") * af.qx, label="Deaths")
rf["fund"].between("post_mort", "post_lapse").subtract(rf["fund"].at("post_mort") * af.qw, label="Lapses")

# Convention B — lapses first, then deaths
points=["bop", "post_lapse", "post_mort", "eop"]
rf["fund"].between("bop", "post_lapse").subtract(rf["fund"].at("bop") * af.qw, label="Lapses")
rf["fund"].between("post_lapse", "post_mort").subtract(rf["fund"].at("post_lapse") * af.qx, label="Deaths")
```

State writes within a period proceed in declared order. State reads within a period:

- `rf["S"].at("P")` — typed `(state, point)` reference. Resolved at compile time. Compile-time error if `P` precedes `S`'s most recent write *to itself* or is unwritten.
- `rf["S"]` (without `.at(...)`) in an expression context — equivalent to `rf["S"].at("eop")`, the current period's end-of-period value. Used in cross-state guarantee comparisons and downstream column expressions.

Cross-period reads (`rf["S"].at("eop", t=t-1)`) are the kernel's *carry* — they're how state advances from period to period. Carrying is implicit; the actuary writes `s += ...` and the kernel handles the period transition. Phase 1 does not expose explicit cross-period reads in the API — they're a Phase 2 escape hatch if a product needs lookback windows beyond what `.ratchet` covers.

Lapse and contract-boundary semantics:
- `lapse_when_all_non_positive=[s1, s2, ...]` — the kernel stops advancing when all named states are ≤ 0 at end-of-period. Subsequent periods produce zeroed states. Carry-forward of zero is explicit; cohort aggregation needs to know which periods are post-lapse so reserve release can be timed correctly.
- `contract_boundary=mask` — the kernel stops advancing when the closed-subset boolean expression `mask` evaluates to true at the period boundary. Subsequent periods produce zeroed states.
- Both can coexist; the kernel stops at whichever fires first. `rf.stop_reason()` returns `"lapse" / "contract_boundary" / "horizon"`.

---

## 6. GSP-95 alignment

GSP-95 (semantic IR + Polars backend boundary) shipped Phases 1–3 on `develop` (PRs #99, #100, #101). The rollforward redesign builds on that foundation.

**Where rollforward sits in GSP-95's layering.** The semantic IR layer owns the rollforward IR's typed structure (states, points, transitions, schedule, batch_axes). Transition bodies are gaspatchio DSL expressions — a closed semantic subset that the GSP-95 layer guarantees is portable. Polars-specific lowering (the actual kernel that walks transitions and accumulates state) lives in `polars_backend/plugins.py` as `rollforward_plugin`, alongside the operator/mask/list-eval routers shipped in #101.

**Engine portability is conditional and self-declared.** The IR canonical form carries an `engine_binding` flag — `'portable'` when every transition body, `Apply.body`, and `contract_boundary` mask uses only the closed semantic subset, or `'polars'` when any expression escapes (raw `pl.Expr`, `pl.max_horizontal`, autopatched Polars methods). `engine_binding` is hashed into `spec_fingerprint`, so a model using `pl.max_horizontal` and an otherwise-identical model using only closed-subset operators produce **different fingerprints**. Phase 3's JAX-backed engine (see §13.3) accepts only IRs with `engine_binding == 'portable'`; this is the audit boundary, not a global guarantee. `action_key` differs across engines (kernel artefact SHA, engine version); `spec_fingerprint` is stable across engines for portable IRs by construction.

**Transition bodies use the existing DSL.** No new expression surface is introduced. Where v1 wrote `gp.max(a, b)`, v2 uses the shipped `pl.max_horizontal(a, b)` directly — a Polars-surface call honestly acknowledged as outside GSP-95's closed semantic subset. Future GSP-95 work may promote scalar `max`/`min` into the closed subset; until then, transition bodies are mostly engine-portable with one or two named exceptions.

**Where the rollforward sits relative to GSP-95's shipped state.**
- Chained `.when().then()...otherwise()` shipped in PR #99 (GSP-87). Used freely in transition bodies.
- Shape source-of-truth + `ColumnTypeDetector` deletion shipped in PR #100. The rollforward consumes `column/shape.py`'s shape information at compile time.
- `polars_backend/` boundary extraction shipped in PR #101. The `rollforward_plugin` lives there.

**Explicit non-goals here.** This redesign does not aim to make every operation engine-portable. The closed semantic subset is the contract; primitives outside it (raw `pl.Expr` calls, autopatched Polars methods, plugin escape hatches) are explicitly Polars-only. A future JAX backend will have to translate the closed subset, not arbitrary Polars expressions.

---

## 7. Kernel architecture (Polars backend)

The kernel lives in `bindings/python/gaspatchio_core/polars_backend/plugins.py` as the `rollforward_plugin` function (already exists in shipped GSP-95 code, in stub form). It receives kwargs:

```python
{
  "ir":          <serialised IR canonical form>,    # JSON-encoded transitions, states, points, schedule
  "captures":    <list of (state, point) captures requested>,
  "track_increments": <bool>,
  "lapse_when_all_non_positive": <list[str]>,
  "contract_boundary": <Optional[ContractBoundary canonical form]>,
}
```

The IR contains typed `Op` objects (see §7.1). The Rust kernel walks the per-period transition list, evaluating each Op against the current state vector. The kernel is `is_elementwise=True` from a Polars perspective: each row's output depends only on that row's inputs (the per-row schedule, per-row inception date, per-row initial states, per-row assumption columns). Streaming-engine compatible; no internal Rayon (per `core/project.md`).

**Struct emission and lazy composition.** The plugin returns a single Polars Struct per row. Fields cover every state's eop value, every `(state, point)` capture extracted via `rf[s].at(p)`, and — when `track_increments=True` — every labelled Op's per-period delta. User-side accessors lower to field extractions on the shared plugin call:

| User code | Lowered Expr |
|---|---|
| `rf["av"]` | `plugin_output.struct.field("av")` |
| `rf["av"].at("post_coi")` | `plugin_output.struct.field("av_post_coi")` |
| `rf.increment("COI")` | `plugin_output.struct.field("coi_amount")` |

`rf["av"]` returns a `pl.Expr`, not a materialised result. Assignments like `af.av = rf["av"]` register a column expression in the ActuarialFrame's lazy plan; nothing computes until `af.collect()`. The compiler emits **one shared plugin Expr per `rollforward(...)` call**: it walks every `rf[...]` accessor in the lazy plan, computes the requested-fields list (the `captures` kwarg) as the union of all requests, and emits a single `register_plugin_function` call. User-side accessors lower to `.struct.field(...)` extractions against that one Expr — so the kernel runs once per chunk by construction even if a model references three states, two captures, and four increments from the same rollforward. Per-row state-carrying inside the kernel is invisible to Polars; the plugin presents row-elementwise externally.

**Per-row state vectors.** For `n_states` states and `n_periods` periods, each row carries an `(n_periods, n_states)` matrix. With monthly 1200-period 2-state, that's 2400 floats per row. Polars list columns with `amortized_iter()` are the storage / iteration primitive (see `core/project.md`).

**Capture slots.** A `(state, point)` capture is emitted as a `List<Float64>` field in the plugin's per-row Struct. The compiler deduplicates capture requests so one slot per unique `(s, p)` pair — multiple user-side `rf[s].at(p)` references to the same pair share a single field.

**Memory at scale.** Per `core/project.md`'s memory notes: model-point batching (GSP-89) is the production path for >100K policies; column pruning (GSP-90) reduces final output. The rollforward kernel doesn't try to solve memory itself — it stays elementwise so streaming works, and downstream batching handles peak RSS.

### 7.1 Op-class vocabulary

Transition bodies compile to typed `Op` objects with construction-time `verify()`. Pattern borrowed from MLIR dialects (Op + Verifier). The Phase 1 op set:

```python
# bindings/python/gaspatchio_core/rollforward/_ops.py

@dataclass(frozen=True)
class Add(Op):
    target: StateRef        # which state this op writes
    expr: Expr              # what to add
    label: str | None

    def verify(self) -> None:
        assert self.expr.dtype == "Float64", "Add expects float-typed expression"

@dataclass(frozen=True)
class Subtract(Op):
    target: StateRef
    expr: Expr
    label: str | None

@dataclass(frozen=True)
class Charge(Op):
    target: StateRef
    rate: Expr
    label: str | None

@dataclass(frozen=True)
class Grow(Op):
    target: StateRef
    rate: Expr
    label: str | None
    # dt comes from the schedule at compile time

@dataclass(frozen=True)
class GrowCapped(Op):
    target: StateRef
    rate: Expr
    floor: Expr
    cap: Expr
    label: str | None

@dataclass(frozen=True)
class DeductNAR(Op):
    target: StateRef
    coi_rate: Expr
    death_benefit: Expr
    label: str | None

@dataclass(frozen=True)
class Ratchet(Op):
    target: StateRef
    to: Expr                # any expression — typically a StateAt or scaled StateAt
    when: Expr | None       # optional gating mask
    label: str | None

@dataclass(frozen=True)
class Floor(Op):
    target: StateRef
    value: float

@dataclass(frozen=True)
class Apply(Op):
    target: StateRef
    body: Expr              # arbitrary semantic-IR expression — escape hatch
    label: str | None
```

`StateRef` is the `(state_name, point)` typed reference. `Expr` is a semantic-IR expression node (proxy, operator, when().then(), …) per GSP-95.

**`Apply.body` and engine-portability.** `Apply.body` is an unbounded `Expr`; users can use closed-subset operators (engine-portable) or Polars-only escape hatches (`pl.max_horizontal`, raw `pl.Expr`, autopatched methods). The static walk in §6 inspects `Apply.body` alongside transition bodies and `contract_boundary` masks: any non-closed-subset operator flips `engine_binding` to `'polars'`, which propagates into `spec_fingerprint`. Models using such escape hatches are explicitly Polars-bound and rejected by the future JAX backend. `Apply` is therefore not a hidden audit-boundary breach — its portability cost is machine-checkable, not silent.

`verify()` runs at construction. Compile-time errors for impossible Ops (point precedence violations, dtype mismatches, missing labels when `track_increments=True`).

---

## 8. Compilation pipeline

The compiler turns the user-facing builder API into the IR canonical form, then lowers the IR into Polars-backend kwargs.

### 8.1 Overview

Builder API call → typed Op list → IR canonical form (engine-portable) → Polars-backend kwargs → kernel call.

The IR canonical form is the artefact `spec_fingerprint` hashes. It's JSON-serialisable and engine-agnostic: a future JAX backend reads the same canonical form and emits JAX-compatible code instead of Polars-backend kwargs.

### 8.2 Pass-based compilation chain (CVXPY pattern)

The compiler is a sequence of named, testable passes. Pattern borrowed from CVXPY's reduction chain.

```python
# bindings/python/gaspatchio_core/rollforward/_compile.py

class Pass(Protocol):
    def name(self) -> str: ...
    def apply(self, ir: IR) -> IR: ...

PHASE_1_PASSES = [
    Validate(),               # per-Op verify(), point/state/schedule consistency
    ResolveStateRefs(),       # rf["S"].at("P") → typed StateRef indices
    FoldConstants(),          # 1.0 + 0.0 → 1.0; pre-compute schedule-derived columns
    AssignCaptureSlots(),     # deduplicate (state, point) reads → slot indices
    LowerToPolarsPlugin(),    # IR → Polars-backend kwargs
]

def compile(builder_state: BuilderState) -> CompiledRollforward:
    ir = builder_state.to_ir()
    for p in PHASE_1_PASSES:
        ir = p.apply(ir)
        ir.log_pass(p.name())  # observable at compile time
    return CompiledRollforward(ir=ir, plugin_kwargs=ir.lowered_kwargs)
```

Each pass produces a structured log line, observable when `LOGURU_LEVEL=TRACE`:

```
[validate]              ok — 12 ops, 3 states, 5 points, schedule=Schedule(from_inception, 240, 1M, OneTwelfth, NullCalendar), batch_axes=('policy',)
[resolve_state_refs]    ok — 8 (state, point) refs resolved
[fold_constants]        ok — 3 sub-expressions folded
[assign_capture_slots]  ok — 6 distinct (s, p) read pairs → 6 slots
[lower_polars]          ok — 12 transitions lowered, 9 input columns
```

**Future engine reuse.** A JAX backend reuses `Validate`, `ResolveStateRefs`, `FoldConstants`, `AssignCaptureSlots` unchanged — they're engine-agnostic. Only `LowerToPolarsPlugin` is replaced by `LowerToJax` (Phase 3). The pass-chain pattern makes that swap clean.

### 8.3 What `_compile()` looks like end-to-end (GSP-92 walkthrough)

For the GSP-92 worked example (§4.9):

1. `Validate` — 7 ops (1 Grow, 2 Subtract via withdrawal, 1 Floor, 1 Ratchet, …); 4 points; 2 states; schedule = `Schedule.from_inception(...)`; batch_axes = `("policy",)`. All verifies pass.
2. `ResolveStateRefs` — `rf["aw"].at("bop")` → `StateRef(state="aw", point="bop", slot=0)`; `rf["fund"].at("after_growth")` → `StateRef(state="fund", point="after_growth", slot=1)`.
3. `FoldConstants` — `af.bc_factor / 12` is a constant column, but `af.bc_factor * af.fac / 12` keeps both mults (both columns); folding doesn't help here. The schedule's `dt[t] = 1/12` is materialised once as a constant column.
4. `AssignCaptureSlots` — 4 unique `(state, point)` reads (`("aw","bop")`, `("fund","after_growth")` — used twice — `("aw","eop")`, `("fund","eop")`). 4 slots.
5. `LowerToPolarsPlugin` — emit kwargs for `rollforward_plugin`, including the typed Op list, capture slot list, schedule canonical form, batch_axes, lapse_when, and contract_boundary.

The final `plugin_kwargs` are JSON-serialisable. The kernel JSON-decodes once, builds the Rust-side Op list, and iterates per row.

**What the Polars plan looks like at `af.collect()`.** For the GSP-92 example with `af.fund = rf["fund"]; af.aw = rf["aw"]`:

    LazyFrame
    ├── ... earlier columns (premium, fund_init, aw_init, schedule-derived dt, ...) ...
    ├── plugin_call = rollforward_plugin(
    │       ir=<canonical form>,
    │       captures=[("fund","after_growth"), ("aw","bop")],
    │       track_increments=False,
    │       ...
    │   )                                              # Struct{fund: List<f64>, aw: List<f64>}
    ├── fund = plugin_call.struct.field("fund")        # field-extraction Expr
    └── aw   = plugin_call.struct.field("aw")          # field-extraction Expr

The two field extractions reference one shared plugin Expr by construction (the compiler emits one `register_plugin_function` call per `rollforward(...)`, see §7). The streaming engine sees `is_elementwise=True` on the plugin, processes the LazyFrame in chunks, invokes the plugin once per chunk, and the two field-extractions slice fields cheaply — at no extra plugin cost. A single `af.collect()` (the existing default `engine="streaming"` per `core/project.md`) triggers the whole evaluation.

**Release-gate verification.** `lf.explain(engine='streaming')` should show exactly one `register_plugin_function` node per `rollforward(...)` call and N field-extraction nodes (one per accessor). If two plugin nodes appear with the same `ir` kwarg, the compiler's accessor-walk is broken — that is the Phase 1 acceptance test for the lazy/Struct contract.

---

## 9. Audit identity

### 9.1 Canonical form

The IR's canonical form is a normalized JSON document. Every spec serializes to a unique canonical-form bytestring; two specs with identical canonical form are guaranteed to produce identical numerical output (modulo `action_key` differences in the engine/data envelope).

Components hashed:
- States (name, init expression's canonical form, dtype)
- Points (declared list, position)
- Transitions (typed Op list, in declared order, with all expressions canonicalized)
- Schedule (constructor type, inception/start ref, n_periods, frequency, calendar name, convention, day_count name)
- batch_axes (the tuple — hashed only when not the engine default `("policy",)`; default value omitted from canonical form so deterministic Phase 1 fingerprints survive into Phase 3 stochastic adoption)
- track_increments (bool)
- lapse_when_all_non_positive (sorted state list)
- contract_boundary (optional canonical form, including `reason` and `regulatory_anchor` strings)
- Labels (when `track_increments=True`; cosmetic-only when `track_increments=False`)
- `engine_binding` (`'portable'` | `'polars'` — derived by static walk of every transition body, `Apply.body`, and `contract_boundary` mask; `'polars'` if any non-closed-subset operator appears, else `'portable'`)

**Why scope label hashing by `track_increments`?** Labels appear in the increment-attribution output (`rf.increment("Net growth")`) only when `track_increments=True`. In that mode, renaming a label is a user-facing API change to the output and must move the fingerprint. With `track_increments=False`, increments aren't computed; labels exist only as Op metadata and don't affect any output, so hashing them would pessimise cosmetic edits without identity-meaning. Note that flipping `track_increments` itself always moves the fingerprint — the flag is a hashed component, and switching it is a genuine recipe change (new output).

Expression canonicalization: column references are name-keyed, not position-keyed. Constants are normalized. Operator precedence is fully parenthesized. Order of commutative-operator operands is sorted by name.

### 9.2 explain() output

`rf.explain()` returns a human-readable description of the canonical form for actuary-visible audit. Example:

```
Rollforward (spec_fingerprint = sha256:a3f9c2e1...e21c)

States:
  fund:  init=af.fund_init           dtype=Float64
  aw:    init=af.aw_init             dtype=Float64

Points:  bop, after_growth, after_payment, eop

Schedule: from_inception(af.contract_inception, 1200, "1M", NullCalendar, Unadjusted, OneTwelfth)
  dt[t] = 1/12 for all t

Transitions (in order):
  fund.between(bop, after_growth):   *= 1 + (af.one_plus_ba - af.gib_rate - af.z_rate) * dt   [label="Net growth"]
  fund.between(after_growth, after_payment): -= af.one_plus_ba * max(aw.at(bop), fund.at(after_growth) * af.bc_factor / 12)  [label="Payment"]
  fund.between(after_payment, eop): floor(0)
  aw.ratchet(to=fund.at(after_growth) * af.bc_factor * af.fac / 12, when=schedule.anniversary_mask(), label="AW step-up")

batch_axes: (policy,)
track_increments: True
lapse_when_all_non_positive: [fund]
contract_boundary: None

Captures requested: 4
  (aw, bop), (fund, after_growth), (aw, eop), (fund, eop)
```

### 9.3 `spec_fingerprint()` — engine-portable spec identity

```python
fp = rf.spec_fingerprint()
# "sha256:a3f9c2e1...e21c"
```

`spec_fingerprint(ir) = sha256(canonical_form(ir))`. Two specs with the same `spec_fingerprint` produce identical output for identical inputs on any future engine that implements the closed semantic subset correctly (Polars today; JAX in Phase 3).

This is the primary audit anchor. ASOP 56 / VM-31 / Solvency II Article 124 all require model documentation sufficient for an independent third party to recreate results — `spec_fingerprint` provides a stable identifier that ties the documentation to a specific recipe.

### 9.4 `action_key()` — minimal Phase 1 hermetic-run identity

```python
ak = rf.action_key(input_data_sha=af.input_data_sha)
# "sha256:b71f2c8...d403"
```

Phase 1's `action_key` is a deliberately minimal closure:

```python
action_key = sha256(
    spec_fingerprint
    || input_data_sha          # ActuarialFrame data columns (user-supplied)
    || typed_input_shas        # sorted concat of source_sha() across IR's typed inputs (compiler-gathered)
    || gaspatchio_version
    || git_sha
)
```

`typed_input_shas` is a sorted concatenation of `source_sha()` returned by every `Curve`, `Table`, `MortalityTable`, and `Schedule` referenced by the IR. The compiler walks the IR's typed inputs at `action_key()` construction time — no user-side bookkeeping. **Phase 1 commitment**: every typed-input class exposes a `source_sha()` method (file SHA for file-loaded inputs, content SHA for in-memory constructors, version-string SHA for bundled regulatory data). This closes a gap in the v1 design where two runs with different `Curve` / `Table` / `MortalityTable` payloads could produce identical `action_key`s — silent cache hazard, broken rerun traceability.

This matches the granularity ASOP 56 / VM-31 documentation already names (tool-version-string identification) and what production actuarial platforms actually advertise (job-traceability at the "which data was used" pointer level, not bytes-equal hashes).

**Honest framing.** The synthetic validation pass proposed a Bazel-style envelope (kernel artefact SHA × Polars version × Rust target triple × fp_mode × LC_NUMERIC). The real-evidence pass found that **no regulator, audit standard, or PCAOB inspection finding requires this envelope.** Phase 1 ships the 5-component minimum (`spec_fingerprint`, frame data, typed-input contents, package version, git SHA); the full envelope is deferred to Phase 2 if a customer attests to deterministic-replay requirements that need it. A `HermeticContext` stub is present so the extension is non-breaking.

```python
# Phase 2 future signature (stub today, populated when needed)
ak = rf.action_key(input_data_sha=..., context=HermeticContext(
    engine_id="polars_backend",
    engine_version="0.4.0",
    kernel_artifact_sha256="...",
    polars_version="1.18.0",
    rust_target_triple="aarch64-apple-darwin",
    fp_mode="ieee-strict",
    lc_numeric="C",
))
```

### 9.5 Contract validation (state-schema type discipline)

State-schema contracts are kept from v1 — they're just type discipline:

```python
rf = af.projection.rollforward(
    states={
        "fund": StateContract(init=af.fund_init, dtype="Float64", non_negative_after_floor=True),
        "aw":   StateContract(init=af.aw_init,   dtype="Float64", non_negative_after_floor=True),
    },
    schedule=schedule,
)
```

Adding a transition that violates a contract fails at compile time:

```
ContractViolation: state "fund" declares constraint "non_negative_after_floor"
but transition `Subtract` between ("after_payment", "eop") could produce
a negative value before the next floor. Add `.floor(0)` after this transition,
or remove the constraint declaration if intentional.
```

This is part of the per-Op `verify()` discipline, not a new artefact. No `manifest.json`, no separate contracts file. The contract lives on the state declaration, where it's read.

**What's NOT in Phase 1 (formerly v1's §9.5).** The dbt-style `gaspatchio_manifest.json` with selective re-run on `state:modified+`, exposures for impact analysis, etc. The real-evidence pass found zero precedent for dbt-style manifests in actuarial workflows; lineage is typically solved at the workflow layer rather than the model layer. Phase 1 ships `spec_fingerprint` and the minimal `action_key`; broader manifest emission is deferred to Phase 2 / sibling if a real customer asks.

---

## 10. Migration

### 10.1 Versioning

This redesign is the breaking 0.4.0 release. The shipped 0.3.x rollforward (`RollforwardBuilder`, label-string captures) is removed — there is no compatibility shim.

### 10.2 What breaks for existing rollforward users

- `RollforwardBuilder` class — removed.
- `.capture("label_string")` — replaced by typed `(state, point)` reads.
- Implicit step labels in fingerprint inputs — replaced by explicit Op `label` arguments.
- The `accumulate()` linear-recurrence helper is unaffected — it stays as the right tool for term-life-class linear cases (see §4.3).

### 10.3 Port plan for `gaspatchio-va`

- Rewrite the 244-line numpy kernel as the §4.9 builder-API form.
- Port the acceptance test (`policy_00000065.parquet`) — but **only after** §13.0 Phase 0 confirms the gold file's provenance is independent of the v1 numpy kernel. Otherwise the acceptance test is unfit for purpose (validates that the redesign preserves the old kernel's bugs, not that it computes the right answer).
- Update tutorials Level-3 (mini-VA) to use the new builder.

### 10.4 What does not break

- `accumulate()` — unchanged.
- All linear / column-vectorised models.
- `assumptions.Table` — unchanged (just integrated into the rollforward narrative).
- Existing GSP-95 surface — `polars_backend/` package, chained `when()`, shape source-of-truth.
- Tutorials Levels 1, 2, 4, 5 — no rollforward usage to break.

---

## 11. Documentation deliverables

The OSS meta-scan identified documentation as the silent #1 issue across every actuarial framework — every repo has open "review docs" issues tagged Hacktoberfest. This redesign treats documentation as a Phase 1 commitment, not an afterthought.

**In `gaspatchio-core` (this repo):**
- §4 worked-example climb (this document is the source of truth; promoted to user-facing docs)
- API reference for `Curve`, `Schedule`, `Calendar`, `DayCount`, `MortalityTable`
- `core/project.md` updates for new typed-input principles
- Per-typed-input "what's actually canonical" pages (e.g., for MortalityTable: age-basis conversion mechanics, select-and-ultimate semantics, joint-life patterns)

**In `gaspatchio-docs` (sibling repo):**
- New tutorial: "From spreadsheet to typed model" — actuary-targeted, walks through Curve/Table/Schedule/MortalityTable/rollforward as a coherent set
- Update Level-3 mini-VA tutorial to use the builder API
- Reference page mapping textbook FAM/SOA notation to API names (addresses the "I can't find the actuarial term" pain)
- Cache-invalidation story page: "I changed an assumption — what's stale?" (uses `spec_fingerprint` diff)

**Cross-cutting:**
- Error-message gallery — the per-Op `verify()` system produces structured errors; gallery shows what each looks like and how to fix
- `/explain()` output style guide for auditors

---

## 12. Testing strategy

### 12.1 Kernel correctness (unit-test level)

Per-Op tests for all 9 Phase 1 Ops (Add, Subtract, Charge, Grow, GrowCapped, DeductNAR, Ratchet, Floor, Apply). Both happy path and edge cases (state at zero, lapse-triggering, point precedence violations).

Schedule tests: the 5 day-counts × 4 calendars × 4 BD conventions × edge cases (leap-year crossings, 30/360 vs Act/365 reconciliation, anniversary mask correctness across roll conventions). Reference values from QuantLib's published day-count tests where applicable.

Curve tests: parallel shifts (commutativity with extraction), interpolation correctness against reference EIOPA RFR data, day-count consistency under conversion.

`spec_fingerprint` stability tests: changing a label changes the fingerprint when `track_increments=True`; doesn't change when `False`. Reordering commutative operands (`a + b` → `b + a` in expression construction) does not change the fingerprint (canonical form sorts).

### 12.2 VA acceptance test (integration)

The `gaspatchio-va` model reconciles 25 list-typed columns to `policy_00000065.parquet` (1200 periods, `atol ≤ 1e-9`). Becomes the integration gate **after** Phase 0 confirms gold-file provenance.

### 12.3 Engine-portability smoke test (forward-looking, Phase 2)

Build a tiny rollforward IR with `engine_binding == 'portable'` (closed-subset operators only). Lower with `LowerToPolarsPlugin`, run; lower with a stubbed `LowerToJax` (Phase 3 work, unimplemented in Phase 1), assert canonical form is identical pre-lowering. Demonstrates the IR is engine-agnostic for portable IRs without yet shipping a JAX engine. **IRs with `engine_binding == 'polars'` are explicitly excluded** — the smoke test asserts portability of the closed-subset path, not universal portability.

### 12.4 Benchmarks

New benchmarks added to `benches/`:
- `rollforward_va_benchmark` — VA + GMDB ratchet, 100K policies × 360 periods. Tracks Polars-streaming throughput.
- `rollforward_schedule_benchmark` — schedule construction + dt materialisation across the 5 day-counts × 4 calendars. Tracks lookup performance.
- `rollforward_curve_benchmark` — Curve construction + `spot_rate` materialisation across the 5 day-counts.

Per `core/project.md`'s memory-at-scale notes, model-point batching (GSP-89) is the production scaling story; benchmarks here measure per-batch throughput, not peak RSS.

---

## 13. Phasing

### 13.0 Phase 0 — Prerequisites (must complete before any code is written)

**Confirm provenance of `policy_00000065.parquet`.** If the gold file was generated by `va_kernel.py` (the v1 numpy kernel), the §12.2 acceptance test merely validates that the redesign preserves the old kernel's behaviour — including any bugs. For a breaking 0.4.0 release that deletes the source kernel, this is not fit-for-purpose.

Action: locate the original Excel illustration or alternative reference data. Either:
- (a) Confirm gold file is independent (e.g., generated from Excel), in which case §12.2 stands as a release-blocking gate.
- (b) Confirm gold file is `va_kernel.py` output, in which case §12.2 is demoted to a regression test, and a new independent reference is required before 0.4.0 ships.

This must complete before Phase 1 implementation begins.

### 13.1 Phase 1 — Core redesign + docs (parallel PRs), real-evidence-aligned

Phase 1 ships as two parallel tracks. **1a** is the core-package PR (kernel + IR + typed inputs); **1b** is documentation work in `gaspatchio-docs`. Neither blocks the other.

#### 13.1a — Core package (one PR)

**In:**
- **Delete the shipped GSP-86 rollforward (PR #80)** — the new kernel replaces it. No adaptor classes, no `from gaspatchio_core.legacy import ...` import paths, no deprecation warnings. Existing tutorials and examples that exercise the old API are rewritten in 1b, not re-pointed at compat layers.
- State-machine IR with typed `(state, point)` references
- Op-class vocabulary (§7.1) — 9 typed Ops with `verify()`
- Pass-based compilation chain (§8.2) — 5 passes
- Polars-backend `rollforward_plugin` (extending the shipped GSP-95 stub)
- `Curve` typed primitive — Phase 1 constructors (`from_zero_rates`, `from_par_rates`), shift/stress (`shift_parallel`, `key_rate_shift`), accessors (`spot_rate`, `discount_factor`, `forward_rate`), `source_sha()`. Both surfaces (typed + column-of-rates) preserved.
- `MortalityTable` thin wrapper around existing `Table`, with `source_sha()` method
- `Schedule` + `Calendar` + `DayCount` primitives — 5 day-counts × 4 calendars × 4 BD conventions, with `OneTwelfth` + `NullCalendar` defaults, month-end anchoring on `from_calendar_grid`, context-dependent BD-convention default; `source_sha()` method on `Schedule`
- `spec_fingerprint()` — canonical-form hash, engine-portable for IRs with `engine_binding == 'portable'`
- `action_key()` — minimal 5-component closure (`spec_fp ‖ input_data_sha ‖ typed_input_shas ‖ gaspatchio_version ‖ git_sha`); typed-input SHAs gathered automatically from the IR; `HermeticContext` stub for Phase 2
- `engine_binding` IR field — derived by static walk of every transition body, `Apply.body`, and `contract_boundary` mask; `'portable'` or `'polars'`; hashed into canonical form
- `contract_boundary=mask` kwarg — closed-subset boolean expression, follows the same engine-portability discipline as transition bodies; hashes into `spec_fingerprint`
- `batch_axes` IR field — defaulted to `("policy",)`, **hash-by-canonical-default** (default value omitted from canonical form); Phase 1 light use for axis naming and error messages
- `explain()` output — actuary-readable canonical-form rendering
- Per-Op `verify()` — structured compile-time errors with fix suggestions

#### 13.1b — Documentation (parallel PR sequence in `gaspatchio-docs`)

Independent of 1a; no blocking dependency.

- Tutorial rewrites for the new typed-input narrative
- FAM-to-API mapping page
- Error-message gallery
- Cache-invalidation story page

**Out (deferred — home decision later):**
- `gaspatchio_manifest.json` (dbt-style) — defer; if customer demand surfaces, lands in Phase 2 or a separate package
- Bazel-style action_key envelope (kernel SHA × Polars version × Rust target × fp_mode × LC_NUMERIC) — defer to Phase 2 if customer attests
- `.reset_when` primitive — Phase 2
- Categorical / sub-period / vector states — Phase 3
- Stochastic primitive (`stochastic_rollforward`) — Phase 3+
- Partial-period `dt` at termination — Phase 2
- Reporting-grid aggregation (`Schedule.aggregate_to(...)`) — Phase 2
- Regulatory `Curve` loaders (EIOPA-RFR with Smith-Wilson, VA/MA hooks; NAIC; Fed) — defer; home decision (core extension, separate package, or third-party recipe) follows customer demand
- Domain-specific contract-boundary typed wrappers (`IFRS17ContractBoundary`, `SolvencyIIContractBoundary`) — defer; mask kwarg in core is sufficient for Phase 1
- IFRS 17 cohort/CSM/coverage-unit/loss-component machinery, Solvency II SCR aggregation, disclosure-pack assembly — defer; home decision follows customer demand

### 13.2 Phase 2 — Hardening + portability proof (follow-up PR)

- `.reset_when(mask, to=expr)` primitive — IUL segment boundaries, FIA buffers
- Partial-period `dt` at termination — for daily-lapse VAs and partial-period reserve release
- `HermeticContext` populated — full Phase-2 action_key envelope when a customer attests
- JAX-backend smoke test — stub `LowerToJax` proves canonical form is engine-agnostic (no JAX engine yet)
- `manifest.json` emission (if customer demand surfaces) — dbt-style impact analysis, selective re-run

### 13.3 Phase 3 — Stochastic sibling (JAX backend)

A separate `gaspatchio-stochastic` sibling package (or Phase 3 internal) implements:
- `stochastic_rollforward(scenarios=N)` — `vmap(rollforward, axis="scenario")` over the same IR
- `batch_axes=("scenario", "policy")` — the IR field reserved in Phase 1 is now exercised
- Common-random-numbers reuse, pathwise sensitivities (delta via `jax.grad`)
- AG 43 / VM-21 / TVOG / EV stochastic workflows

The `LowerToJax` pass replaces `LowerToPolarsPlugin` in this engine; the rest of the compilation chain (Validate, ResolveStateRefs, FoldConstants, AssignCaptureSlots) is reused unchanged. JAX's `lax.scan` over per-policy state with `vmap` over scenarios is the natural lowering.

### 13.4 Extension surface (no commitment to a sibling architecture)

Several capabilities are explicitly out of Phase 1 scope: extended `Curve` loaders (EIOPA RFR with Smith-Wilson / VA/MA, NAIC, Fed), domain-specific contract-boundary typed wrappers (IFRS 17, Solvency II), disclosure-pack assembly, SCR / Risk-Margin aggregation, and stochastic primitives. **The home for each is a decision deferred until customer demand surfaces** — could be:

- An extension of core (e.g. add EIOPA loader to `Curve` later)
- A separate package in this repo or a sibling repo (e.g. a hypothetical `gaspatchio-curves`, `gaspatchio-ifrs17`, `gaspatchio-solvency`, `gaspatchio-stochastic`)
- A third-party recipe outside the gaspatchio org

Phase 1 doesn't commit to a sibling architecture; it just doesn't ship these capabilities. The redesign's typed-input boundary, the closed-subset semantic IR, and `engine_binding` are sufficient for any future extension to plug in without breaking core's recipe identity.

---

## 14. Open questions and non-goals

### 14.1 Open questions

1. **Phase 0 prerequisite.** Is `policy_00000065.parquet` gold-file provenance independent of `va_kernel.py`?
2. **Gaspatchio-docs cross-repo coordination.** Tutorial updates for the new typed-input narrative span this repo and `gaspatchio-docs`. PR coordination?
3. **`MortalityTable` attribute set.** `age_basis` and `structure` are committed; is `select_period` Phase 1 or Phase 2?
4. **`Calendar.us_settlement` vs `Calendar.us_nyse`.** US has multiple market calendars; Phase 1 ships `us_settlement` (general) only?

### 14.2 Explicit non-goals

- A complete actuarial platform. Sibling packages, not in core.
- Backwards compatibility with v1 `RollforwardBuilder`. 0.4.0 is breaking.
- Universal applicability of the Bauer/Kling/Russ kernel. It's canonical for VA living benefits; non-VA products use *components* (see §4.10, §4.11).
- Excel I/O. Real OSS pain but proper docs/sibling concern.
- Aggregation across model points. Downstream of rollforward; lives in `ActuarialFrame.aggregate()`.
- Daily / sub-period state. Phase 3.
- Stochastic projection in core. Phase 3 sibling.
- Disclosure-pack assembly (IFRS 17 §117, ORSA, MD&A). Sibling.
- Replication of QuantLib's full Calendar/DayCount catalog. We support the actuarial subset.

---

## 15. References

**Internal:**
- v1 spec (superseded): [`./2026-04-30-rollforward-redesign-design.md`](./2026-04-30-rollforward-redesign-design.md)
- Validation pass (synthetic-persona): [`../research/2026-05-02-validation-pass-summary.md`](../research/2026-05-02-validation-pass-summary.md)
- Real-evidence grounding pass: synthesis in §17.2 of this spec (standalone file `../research/2026-05-03-real-evidence-grounding.md` is pending writeup)
- Schedule design pass: [`../research/2026-05-03-schedule-design.md`](../research/2026-05-03-schedule-design.md)
- GSP-86 design history: `ref/31-rollforward-api/`
- GSP-95 dispatch refactor (post-implementation guide): `ref/37-dispatch-engine-refactor/ARCHITECTURE.md`
- Recursive-accumulation gap analysis: `ref/30-llm-helpers/recursive-accumulation-gap.md`

**Linear:**
- GSP-92 — driving issue (cross-state arithmetic, mid-period column derivation)
- GSP-95 — engine-agnostic IR direction (Phases 1-3 shipped)
- GSP-86 — original native-Rust-plugin work (now superseded)
- GSP-87 — chained when()/then() (shipped in PR #99)

**External — primary regulations and standards:**
- Solvency II Delegated Regulation 2015/35, Article 18 (contract boundaries)
- IFRS 17 §33–35, §B61–B71 (contract boundaries), §B72–B85 (discount rates), §117 (disclosure)
- NAIC Valuation Manual VM-20 (statutory reserves), VM-21 (variable annuities), VM-31 (PBR Actuarial Report)
- ASOP 56 (Modeling), ASOP 52 (Principle-Based Reserves)
- Fed SR 11-7 (Supervisory Guidance on Model Risk Management); PRA SS3/18, SS1/23
- EIOPA Guidelines on Contract Boundaries (BoS-22/218)
- EIOPA Risk-Free Interest Rate Term Structures Technical Documentation
- ESMA "From black box to open book?" thematic review (October 2024)

**External — academic and industry:**
- Bauer, D., Kling, A., Russ, J. (2008). "A Universal Pricing Framework for Guaranteed Minimum Benefits in Variable Annuities." *ASTIN Bulletin* 38(2), 621–651.
- Holz, D., Kling, A., Russ, J. (2012). "GMWB For Life — An Analysis of Lifelong Withdrawal Guarantees." *ZVersWiss* 101, 305–325.
- ESMA October 2024 thematic review on first IFRS 17 application

**External — software comparators:**
- QuantLib reference: https://www.quantlib.org/reference/
- JuliaActuary org: https://github.com/JuliaActuary
  - `Yields.jl`, `FinanceModels.jl`, `LifeContingencies.jl`, `MortalityTables.jl`, `ExperienceAnalysis.jl`, `EconomicScenarioGenerators.jl`, `DayCounts.jl`, `BusinessDays.jl`
- lifelib (modelx): https://lifelib.io
- Heavylight: https://github.com/lewisfogden/heavylight
- JAX `lax.scan` documentation: https://docs.jax.dev/en/latest/_autosummary/jax.lax.scan.html
- CVXPY reduction chain documentation: https://www.cvxpy.org/
- MLIR dialect documentation: https://mlir.llvm.org/
- dbt manifest documentation: https://docs.getdbt.com/reference/dbt-artifacts
- Bazel action cache documentation: https://bazel.build/remote/caching

---

## 16. Acknowledgements

The validation-pass research agents — synthetic personas (Priya, Marcus, Hannah, Daniel, Aisha, Robert, Elena), coverage probes (IFRS 17 mechanics, living-benefit riders, product mechanics, stochastic & capital, reporting/audit/governance), and SOTA library deep-dives (JAX, MLIR, dbt, CVXPY, Bazel, Substrait) — generated the hypothesis set that this v2 design tested. The real-evidence pass and Schedule design pass agents grounded that hypothesis set against primary regulations, OSS issue trackers, and industry papers. Both passes informed this revision; the synthesis is documented in §17.

The user's pushback that LLM-persona output is hypothesis-generation, not field validation, was the key inflection point. v1's evidence basis confused the two; v2 keeps them honestly distinguished.

The Codex adversarial review of v1 caught four issues (acceptance gate provenance, fingerprint vs labels, lapse semantic naming, mid-period read clarity) that survived into v2's framing. The provenance issue is now §13.0 Phase 0 prerequisite.

---

## 17. Validation history

This section is the honest evidence trail behind the design choices in this v2 spec. It distinguishes synthetic (LLM-persona) findings from real evidence (regulations, OSS state, industry papers).

### 17.1 First validation pass — synthetic-persona (2026-05-02)

18 LLM agents prompted to play actuarial roles + coverage probes + SOTA library studies. Output: `research/2026-05-02-validation-pass-summary.md`.

The pass produced a hypothesis set: which primitives might be missing, which patterns might be worth borrowing, where the spec might be wrong. Verdicts looked authoritative ("Elena would not approve this for QRT submission") but were synthetic — they reflect the LLM's pattern-matching on what such a persona would plausibly say, not field experience.

### 17.2 Real-evidence grounding pass (2026-05-03)

5 research agents grounding the synthetic-derived primitives against primary regulations, OSS issue trackers, and published industry papers. Output: synthesised in §17.2 below; standalone writeup at `research/2026-05-03-real-evidence-grounding.md` is pending.

Headline findings:

| Primitive | Synthetic verdict | Real-evidence verdict |
|---|---|---|
| `Curve` (§4.14) | "Pillar 1 blocker" | WEAK — but STRONG SOTA opportunity. `FinanceModels.jl` (JuliaActuary, successor to `Yields.jl`) validates the typed-curve pattern; reg-tech necessity argument doesn't hold. **Decision: keep in core, both surfaces (typed + column-of-rates), reframe as ergonomic SOTA lead.** |
| `contract_boundary` (§4.17) | "Pillar 1 blocker" | MODERATE-WEAK. ESMA found 31% disclosure failure on first IFRS 17 application — real *disclosure* problem, not modelling. Zero OSS issue requests. **Decision: keep typed primitive, soften framing to "convenience for disclosure-pack assembly," drop "regulatory requirement" claim.** |
| `action_key` envelope (§9.4) | "Auditor blocker" | WEAK/NEGATIVE. ASOP 56 names a tool-version string as the documentation unit; PCAOB findings don't flag this. **Decision: shrink to 4-component minimum (spec_fp ‖ input_data_sha ‖ gaspatchio_version ‖ git_sha); defer Bazel envelope to Phase 2.** |
| `manifest` (former §9.5) | dbt pattern | WEAK/NEGATIVE. Zero precedent for dbt manifests in actuarial. Lineage solved at the workflow layer, not the model layer. **Decision: defer entirely to Phase 2 / sibling.** |
| `batch_axes` (§3) | JAX vmap blocker | WEAK. No published vmap-in-actuarial. Real bottleneck is policy-axis cardinality. **Decision: keep field as cheap forward-compat (Option C — reserve + light validation), mark explicitly as speculative.** |
| `Schedule` / typed dates | Not raised in synthetic pass | STRONG. Genuine gap (no OSS framework unifies QuantLib day-count with actuarial Anniversary). **Decision: full Phase 1 inclusion with OneTwelfth + NullCalendar defaults.** |
| `MortalityTable` | Not raised | STRONG — multiple OSS issues citing age-basis, select-and-ultimate, joint-life pain. **Decision: thin wrapper over existing Table, Phase 1.** |

### 17.3 Schedule design pass (2026-05-03)

4 research agents grounding the Schedule design surface specifically. Output: `research/2026-05-03-schedule-design.md`.

Verdict: **Schedule lands clean for Phase 1.** Phase 1 commits to 5 day-counts × 4 calendars × 4 BD conventions, with `OneTwelfth + NullCalendar + Unadjusted` as defaults matching US/UK/EU production practice. The MVP fallback was defined precisely (in case the typed surface had been too risky) but isn't needed.

### 17.4 Decisions taken

Strategic decisions made during this conversation, reflected in this v2 spec:

1. **Stochastic projection** → Phase 3+ JAX-backed sibling. `batch_axes` reserved in Phase 1 IR (Option C — reserve + light validation).
2. **IFRS 17 / Solvency II** → mixed: `Curve` typed (both surfaces) and `contract_boundary=mask` (closed-subset bool expression) in core; typed `ContractBoundary` wrappers, cohort/CSM/disclosure-pack mechanics, and SCR aggregation are deferred — home decision (core extension, separate package, or third-party) follows customer demand. No sibling-architecture commitment.
3. **Run identity (`spec_fingerprint`/`action_key`/`manifest`)** → minimal Phase 1: spec_fp + 5-component action_key (typed-input SHAs gathered automatically — closes the v1 gap where Curve/Table payload changes were invisible to action_key). IR carries an `engine_binding` flag (`'portable'` or `'polars'`) hashed into spec_fingerprint, so portability claims are machine-checkable, not aspirational. `batch_axes` hashed by canonical default (default value omitted from canonical form) so deterministic Phase 1 fingerprints survive into Phase 3 stochastic adoption. Bazel envelope deferred. Manifest deferred.
4. **Curve typed** → both surfaces in core (typed Curve + column-of-rates) with explicit Phase 1 constructors (`from_zero_rates`, `from_par_rates`, shifts, accessors, `source_sha()`). SOTA lead, not regulatory necessity. Regulatory loaders (EIOPA-RFR / Smith-Wilson / VA/MA, NAIC, Fed) deferred — home decision follows customer demand.
5. **MortalityTable** → thin wrapper over existing Table, Phase 1.
6. **Schedule / Calendar / DayCount** → first-class Phase 1, with `OneTwelfth + NullCalendar` defaults, month-end anchoring on `from_calendar_grid`, and context-dependent BD-convention default (`Unadjusted` with `NullCalendar`, `ModifiedFollowing` with a real calendar). Terminating-period proration and reporting-grid aggregation deferred to Phase 2 as documented contracts.
7. **Documentation** → Phase 1 commitment, not afterthought (silent #1 OSS issue).
8. **GMxB framing** → canonical *for VA living benefits*, not OSS-broad. Honest in §3.

### 17.5 Honest evidence basis (what is real, what is synthetic, what is pending)

**Real evidence in this spec:**
- Primary regulatory text (Solvency II Articles, IFRS 17 paragraphs, NAIC AG numbers, ASOP 56, SR 11-7, EIOPA Guidelines).
- ESMA October 2024 thematic review (real audit finding on IFRS 17 first application).
- OSS framework code we have read (lifelib, JuliaActuary, Heavylight, modelx, this repo's `polars_backend/`).
- OSS issue trackers cited (with verified URLs).
- Pattern-borrowing from real libraries (CVXPY reductions, MLIR dialects, Bazel action keys, dbt manifests, JAX `vmap`, QuantLib Calendar/DayCount, Yields.jl/FinanceModels.jl) — the libraries exist and the patterns work *in their own domains*.

**Synthetic in this spec:**
- All persona verdicts in v1 §17 (now archived in v1's research summary).
- The mapping from "library X has feature Y" to "actuarial domain *needs* feature Y" — validated against real evidence per §17.2 above; rebalanced where the synthetic claim didn't hold.

**What is pending (would strengthen this design):**
- Real customer interviews. The strongest validation step we haven't taken. One Solvency II shop interview > seven LLM personas.
- US/UK/EU production-model survey (formalised). The jurisdictional conventions are validated against published guidance and Big-4 papers; an actual practitioner survey would tighten the defaults.
- Actuarial-society talk / paper presenting the typed-input pattern. If the SOA / IFoA / AAE community responds, that's a different validation class.

This evidence basis is honest about what is field-validated, what is hypothesis-driven, and what would tighten the design further. The Phase 1 commitments above are robust against the real evidence we have; Phase 2-3 commitments are correctly hedged as future work pending more evidence.

### 17.6 Research artefacts

Full agent transcripts (synthetic-persona pass + real-evidence pass + Schedule design pass) are summarised in the three research files cited above. Individual transcripts are in `/private/tmp/claude-501/.../tasks/*.output` (machine-local; not committed).
