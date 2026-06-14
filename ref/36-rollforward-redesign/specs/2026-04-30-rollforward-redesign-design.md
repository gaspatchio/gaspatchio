# Rollforward Redesign — State-Machine Model with Engine-Agnostic IR

**Date:** 2026-04-30
**Status:** ⚠️ **SUPERSEDED** by [`2026-05-03-rollforward-redesign-v2-design.md`](./2026-05-03-rollforward-redesign-v2-design.md). Kept for archaeology of the design journey. The v2 spec is the live design.
**Authors:** Matt Wright, Claude
**Branch:** `gsp-92-rollforward-redesign`
**Drives:** GSP-92 (cross-state arithmetic with mid-period column derivation)
**Aligns with:** GSP-95 (semantic IR + Polars backend boundary)
**Supersedes:** the rollforward shipped in GSP-86 (PR #80)
**Superseded by:** [v2 design (2026-05-03)](./2026-05-03-rollforward-redesign-v2-design.md), following the real-evidence grounding pass that re-weighted the synthetic-persona findings. See `research/2026-05-03-real-evidence-grounding.md` for the basis of the revision.

---

## 1. Problem statement

The shipped rollforward (PR #80, on `develop` and `main`) cannot express VA living-benefit recurrences and has internal smells that block clean extension. Three pieces of evidence drive this redesign.

**The wall (GSP-92).** A deferred-VA product (`gaspatchio-va`) with GMDB + GIB + I4L riders and a periodic min-payment ratchet escapes into a 244-line numpy `for t in range(n_periods)` kernel. The cross-state arithmetic `state op (max/min of (other_state, captured_V × column))` — gated by anniversary masks — is structurally outside the existing 14 primitives.

**The shape is canonical, not idiosyncratic.** Bauer/Kling/Russ (2008, *ASTIN Bulletin*) and Holz/Kling/Russ (2012, *ZVersWiss*) define the entire GMxB family using exactly this kernel: `G_{t+} = max(G_{t−}, x_W · A^+_t)`. GMDB ratchet, GMIB step-up, GMWB ratchet, GLWB, Highest Daily — every living-benefit rider instantiates this shape. Adding it once covers the family; not adding it leaves the family permanently outside gaspatchio.

**Outside VA, the shape is rare.** Cross-product research (April 2026) confirmed the three sub-features (cross-state, mid-period capture, periodic gating) decouple in non-VA products: ULSG shadow accounts and EIA high-water-marks each need only a subset. The right move is to surface gating, running-max, and cross-state-with-capture as composable primitives, not one monolithic operation.

**Internal smells we'd carry forward without a redesign:**
- Single-state and multi-state kernel paths are 90% duplicated (~340 LOC each); single-state panics on multi-state ops (`rollforward.rs:647-651`).
- Captures are addressed by step *label* (`_compile.py:134`) — renaming a label silently breaks `pro_rata_with` references. Audit-fragile.
- The fingerprint canonical form excludes column wiring and step ordering of inputs.
- No tutorial uses the API; the only known consumer is `gaspatchio-va` pinned to 0.3.1. Installed base is one product in a sibling repo, so we have free hand to redesign.

**GSP-95 (Phases 1–3 shipped on develop as of 2026-05-02) frames the language refactor.** Its semantic-IR + Polars-backend boundary direction has now landed:
- **Phase 1 (PR #99)** — chained `when().then().otherwise()` on list columns with first-match-wins reverse-fold lowering.
- **Phase 2 (PR #100)** — schema-as-source-of-truth for shape/kind, deletion of `ColumnTypeDetector`, mode parity by construction.
- **Phase 3 (PR #101)** — `polars_backend/` subpackage extracted; the existing rollforward kernel wrapper already lives there as `polars_backend.plugins.rollforward_plugin`.

Architecture details: see `ref/37-dispatch-engine-refactor/ARCHITECTURE.md`. The rollforward redesign builds on this shipped foundation rather than coordinating with a future direction.

---

## 2. Design principles

The six principles in `core/project.md` continue to apply. One is added from GSP-95.

| # | Principle | Source |
|---|-----------|--------|
| 1 | No Python loops in the hot path — all time-stepping inside Rust | `core/project.md` |
| 2 | Polars parallelises across policies; the kernel processes one row at a time | `core/project.md` |
| 3 | Pre-compute what you can in Python; only state-dependent work runs in the kernel | `core/project.md` |
| 4 | The Python API reads like the formula — actuary sees business logic, not implementation | `core/project.md` |
| 5 | Names match what an actuary would say — and what an LLM would search for | `core/project.md` |
| 6 | The spec IS the model — declarative chain is simultaneously executable AND machine-inspectable data | `core/project.md` |
| 7 | **The rollforward IR (states, points, transitions, named operations) is engine-agnostic by construction. Transition bodies use the existing gaspatchio DSL surface (proxies, operators, `when().then().otherwise()`). Polars-specific kernel work lives in `polars_backend/`.** | GSP-95 (shipped) |
| 8 | **Reproducibility is run-grade, not recipe-grade.** Two distinct artefacts: `spec_fingerprint()` identifies the IR (engine-portable, audit anchor); `action_key()` identifies the run (spec ⊕ inputs ⊕ engine version ⊕ kernel build digest ⊕ Polars version ⊕ FP mode ⊕ locale). Same key ⇒ byte-identical output guaranteed. | Bazel action-cache (validation pass) |

Principle 4 deserves a note in the context of feedback-loop calculations. Single-line column-vectorised formulas are impossible when state at `t` feeds back into the calculation at `t+1`. The actuarial literature for these cases (Bauer/Kling/Russ, Holz/Kling/Russ) uses a *points-and-transitions* notation: `G(t_k^−)` for the state just before an event, `G(t_k^+)` for just after. Mirroring that notation in the API is faithful to principle 4 — it matches the textbook representation of the problem class.

---

## 3. The state-machine model

A rollforward is a graph of `(states, points, transitions, batch_axes)`:

- A **state** is a named accumulator with an initial value (e.g., `"av"`, `"aw"`, `"shadow"`).
- A **point** is a named structural location within a single time period. Every period has implicit `bop` and `eop` points. Additional points (`post_coi`, `after_growth`, `after_payment`, etc.) are declared by the actuary when mid-period state needs to be addressable.
- A **transition** writes one state and is located between two points (or implicitly `bop → eop` if points are not declared). A transition's body is either a named primitive operation (`.add(...)`, `.grow(...)`, `.ratchet(...)`) or — when primitives run out — a semantic-IR expression.
- A **read** of state `S` at point `P` is written `rf["S"].at("P")`. It is a typed reference, resolved by the compiler to a kernel capture slot. There are no string labels in the addressing.
- **`batch_axes`** is a tuple of axis names the kernel iterates over. Default: `("policy",)` — Polars parallelises across rows. Future: `("scenario", "policy")` for stochastic projection (Phase 3+ sibling primitive). Phase 1's Polars backend asserts `batch_axes == ("policy",)` and rejects others. The field exists in the IR today purely so future backends don't require an IR-breaking change to introduce a scenario axis. See §15 (research findings) for the JAX `vmap`-over-`scan` pattern this borrows.

The kernel evaluates one period at a time, walking transitions in declared order. Within a period, the points define a partial order: writes to a state must respect the point sequence, and reads must reference points that have been written or are `bop`.

This is the **same notation Bauer/Kling/Russ use in the literature**, with `S^−` and `S^+` becoming `rf["S"].at("pre_event")` and `rf["S"].at("post_event")`. The mapping is intentional.

**Single-state collapse.** When `states` has one entry and no `points` are declared, the API surface collapses to a method chain on the state, identical in feel to today's API. No extra ceremony for simple products.

---

## 4. API reference and worked examples

This section is deliberately heavy on examples — the audience is actuaries, not framework authors. Side-by-side comparisons with the current API are included where the current API can express the calculation.

### 4.1 Constructor

```python
# Single state, no points (the simplest case)
rf = af.projection.rollforward(states={"av": af.av_init})

# Single state with named mid-period points
rf = af.projection.rollforward(
    states={"av": af.av_init},
    points=["bop", "post_coi", "eop"],   # bop and eop are always present
)

# Multi-state
rf = af.projection.rollforward(
    states={"av": af.av_init, "aw": af.aw_init},
    points=["bop", "after_growth", "after_payment", "eop"],
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
| `.grow(rate, label=...)` | `s *= 1 + rate[t]` | Interest credit |
| `.grow_capped(rate, *, floor, cap, label=...)` | `s *= 1 + clamp(rate[t], floor, cap)` | IUL crediting |
| `.deduct_nar(rate, *, death_benefit, label=...)` | `s -= rate[t] · max(0, db[t] - s)` | COI on net amount at risk |
| `.floor(value, label=...)` | `s = max(s, value)` | Non-negativity |
| `.cap(value, label=...)` | `s = min(s, value)` | Upper bound |
| `.ratchet(to=expr, when=mask, label=...)` | `s = max(s, expr[t])` (when mask is True) | **GMxB primitive** — covers GMDB ratchet, GMIB step-up, GMWB ratchet, GLWB, HD. Running-max-over-time is `.ratchet(to=rf["self"].at("eop"))` — no separate primitive needed. |
| `.lapse_if_zero(label=...)` | If `s ≤ 0`, zero remaining periods | Single-state non-forfeiture |
| `.between(p1, p2)` | Scopes the next chain to write between two points | Required when points are declared |
| `.at(p)` | Returns a typed read-reference to this state at point `p` | Replaces label-based captures |
| `.when(condition).<op>` | Gated single-period operation | Replaces `add_if`/`charge_if` |

**Drop list (vs current API):**
- `capture(label)` — replaced by `.at(point)` reads
- `ratchet_to(other_state)` — subsumed by `.ratchet(to=rf["other"].at("eop"))`
- `pro_rata_with(label, amount)` — write the expression directly. The current `state *= 1 - amount/capture_value` becomes:
  ```python
  rf["benefit_base"].subtract(
      rf["benefit_base"].at("bop") * af.withdrawal / rf["av"].at("bop")
  )
  ```
- `add_if(condition, amount)` / `charge_if(condition, rate)` — replaced by `.when(condition).add(amount)` / `.when(condition).charge(rate)` chain syntax, which composes with any operation, not just two specific ones.

**Transition body expressions** use the existing gaspatchio DSL surface — same surface used elsewhere in the framework:

| Need | Use |
|---|---|
| Arithmetic (`+`, `-`, `*`, `/`) | Operators on proxies (build `ExpressionProxy` with shape/kind tracked) |
| Conditional | `from gaspatchio_core import when` → `when(cond).then(value).otherwise(default)` (chained, list-aware after PR #99) |
| Element-wise max/min of two values | `pl.max_horizontal(a, b)` / `pl.min_horizontal(a, b)` |
| Literals | Bare Python numbers work directly; the framework wraps internally |
| Comparisons | Operators (`==`, `<`, `<=`, etc.) on proxies build `ConditionExpression` with operator metadata |
| Cross-state, mid-period reads | `rf["state"].at("point")` — typed marker resolved by the rollforward compiler to a kernel capture slot |

**On portability boundaries.** Per `ref/37-dispatch-engine-refactor/ARCHITECTURE.md`, the closed semantic subset includes arithmetic, comparisons, conditionals, broadcasting, and selected accessors. `pl.max_horizontal` is currently outside that closed subset (it's autopatched-through Polars surface). The rollforward IR's engine-agnosticism is in the **(states, points, transitions, op types) graph** — transition body portability inherits whatever engine-portability the broader DSL has at any given time. As GSP-95's closed subset grows, transition bodies become more portable for free.

### 4.3 Worked example — Term Life (not a rollforward case)

Term life has no account value. Reserves come from `accumulate()` (linear recurrence). Included only to mark the scope boundary.

```python
# No rollforward needed. Use accumulate() for the linear reserve recurrence.
af.reserve = af.projection.accumulate(
    initial=0,
    multiply=1 / (1 + af.interest_rate),
    add=af.expected_claims - af.premiums,
)
```

### 4.4 Worked example — Whole Life

Simple multiplicative growth with charges and additions. No mid-period state needed.

```python
rf = af.projection.rollforward(states={"av": af.cv_init})

(
    rf["av"]
    .add(af.premium, label="Premium")
    .charge(af.expense_rate, label="Expenses")
    .grow(af.interest_rate, label="Interest credit")
    .floor(0)
)

af.cv = rf["av"]
```

Identical in line count to the current API.

### 4.5 Worked example — Universal Life with COI

The textbook UL case: state-dependent COI charge based on net amount at risk. No mid-period state needed.

```python
rf = af.projection.rollforward(states={"av": af.av_init})

(
    rf["av"]
    .add(af.premium, label="Premium")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .charge(af.admin_rate, label="Admin")
    .grow(af.interest_rate, label="Interest credit")
    .floor(0)
)

af.av = rf["av"]
```

Side-by-side with the current API: identical code shape. The redesign costs nothing for products that don't need mid-period state.

### 4.6 Worked example — Universal Life with IFRS 17 mid-period attribution

Same UL, but the auditor needs to see the AV value *after* COI, before interest is credited. Today this requires a `.capture("av_post_coi")` step with an audit-fragile label. Redesigned, the actuary names the structural point.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init},
    points=["bop", "post_coi", "eop"],
    track_increments=True,
)

rf["av"].between("bop", "post_coi") \
    .add(af.premium, label="Premium") \
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")

rf["av"].between("post_coi", "eop") \
    .charge(af.admin_rate, label="Admin") \
    .grow(af.interest_rate, label="Interest credit") \
    .floor(0)

af.av           = rf["av"]                  # default: eop value
af.av_post_coi  = rf["av"].at("post_coi")   # mid-period read — typed, audit-stable
af.coi_amount   = rf.increment("COI")       # increment series for IFRS 17 attribution
```

The reference `rf["av"].at("post_coi")` is a typed `(state, point)` pair. Renaming a step's label cannot break it. Reordering `between(...)` calls cannot break it. Only renaming `"post_coi"` in the `points` list breaks it — and that's a search-and-replace that touches every reference visibly.

### 4.7 Worked example — VA + GMDB ratchet (canonical Bauer/Kling/Russ)

The classical VA living-benefit case. AV grows at fund returns; the death benefit guarantee ratchets to AV high-water-mark on each anniversary.

Bauer/Kling/Russ §3.3.2: `G^D_{t+1} = max{G^D_t · (1+i), A^+_{t+1}}`.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "guarantee": af.av_init},   # guarantee starts at premium
    points=["bop", "after_growth", "eop"],
    lapse_when_all_non_positive=["av"],   # only AV; guarantee can persist as a death benefit
)

# Fund: grow at fund return rate
rf["av"].between("bop", "after_growth").grow(af.fund_return, label="Fund return")
rf["av"].between("after_growth", "eop").floor(0)

# Guarantee: roll up at the contractual rate, then ratchet to AV on anniversaries
rf["guarantee"].grow(af.roll_up_rate, label="Roll-up")
rf["guarantee"].ratchet(
    to=rf["av"].at("after_growth"),
    when=af.anniversary_mask,
    label="GMDB ratchet",
)

af.av           = rf["av"]
af.guarantee    = rf["guarantee"]
af.death_benefit = pl.max_horizontal(af.av, af.guarantee)
```

`.ratchet(to=expr, when=mask)` is the GMxB primitive. The `to` argument is any semantic-IR expression — typically a state read at a point, optionally scaled by a precomputable column. The `when` argument is a boolean mask column gating periodic activation.

### 4.8 Worked example — VA + GLWB (Holz/Kling/Russ)

Guaranteed Lifetime Withdrawal Benefit with anniversary step-up of the income base. The actual withdrawal each period is the **greater of** the stated AW or a formulaic withdrawal.

Holz/Kling/Russ §3.2.2(b): `G^E_{t+} = max(G^E_{t−}, x_W · A^+_t)`.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "aw": af.aw_init},
    points=["bop", "after_growth", "after_payment", "eop"],
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
    when=af.anniversary_mask,
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
)

# Fund: grow at net rate (1 + BA - gib - z), then deduct actual payment
rf["fund"].between("bop", "after_growth") \
    .grow(af.one_plus_ba - af.gib_rate - af.z_rate, label="Net growth")

# Actual payment = (1+BA) · max(stated AW, formulaic = fund · bc_factor / 12)
withdrawal = af.one_plus_ba * pl.max_horizontal(
    rf["aw"].at("bop"),
    rf["fund"].at("after_growth") * af.bc_factor / 12,
)

rf["fund"].between("after_growth", "after_payment") \
    .subtract(withdrawal, label="Payment")

rf["fund"].between("after_payment", "eop").floor(0)

# AW: anniversary step-up
rf["aw"].ratchet(
    to=rf["fund"].at("after_growth") * af.bc_factor * af.fac / 12,
    when=af.ratchet_active_mask,
    label="AW step-up",
)

af.fund = rf["fund"]
af.aw   = rf["aw"]
```

The 244-line numpy kernel becomes ~15 lines of declarative builder code. The acceptance test in `gaspatchio-va` (reconciling 25 list-typed columns to `policy_00000065.parquet` over 1200 periods at `atol ≤ 1e-9`) becomes the validation gate.

### 4.10 Worked example — IUL with floor/cap and segment lookback

Indexed Universal Life: crediting is bounded by a floor and cap, applied at segment maturity. A separate "high-water" tracker records the segment's lookback maximum. No cross-state-with-capture is needed — confirms the research finding that non-VA products use *components* of the shape, not the whole.

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "hwm": af.av_init},
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

### 4.12 The `Curve` type

**Why this is in core.** Every reg-tech use case (Solvency II BEL, IFRS 17 discount-at-locked-in-rate, US LDTI net-premium-ratio, MCEV, statutory CRVM) needs to discount or accrue against a *term structure*, not a scalar rate. Elena (Solvency II persona) flagged this as a blocking gap: "Where does an EIOPA risk-free curve with VA live? `accumulate()` takes a scalar `multiply` argument; that's wrong for any reg-tech use." A scalar-only API forces every consumer to flatten a curve to a per-period scalar, losing the term-structure semantics that auditors and regulators expect.

**What it solves.** A first-class `Curve` type lets actuaries write the discounting concept the way they think about it: `Curve.eiopa("EUR", as_of=2026_03_31, va_adjustment=10)` produces an object that knows its term structure. Discounting becomes `curve.discount_factor(t)` or `curve.forward_rate(t)`, both as columns the rollforward consumes natively. Audit reports cite the curve construction by name and parameters, not by an opaque scalar column.

**Pattern + library.** Borrowed from **QuantLib's `TermStructure` family** (validation pass — Bazel-pattern doc and the broader QuantLib reference). QuantLib uses an observer pattern with global evaluation date — we deliberately do *not* copy that part (§5 of QuantLib catalogue: "Heavy use of GoF Observer/Visitor with implicit global state makes audit-stable fingerprinting nearly impossible"). What we *do* borrow: the typed wrapper around (term, rate, adjustments) with named constructors per regulatory regime. Curves participate in `spec_fingerprint()` by their canonical-form serialisation.

**Worked example — building and using a curve:**

```python
from gaspatchio_core import Curve

# EIOPA EUR risk-free with Volatility Adjustment, as of valuation date
rfr = Curve.eiopa(
    currency="EUR",
    as_of=date(2026, 3, 31),
    va_adjustment_bps=10,           # 10bps VA per EIOPA publication
    extrapolation="smith_wilson",    # default: UFR convergence
)

# Or build manually from a term/rate dataframe
custom = Curve.from_table(
    af.curve_terms,    # column: years to maturity
    af.curve_rates,    # column: spot rates
    interpolation="linear_in_log_df",
)

# Use as a per-period column in any rollforward
af.discount_factor = rfr.discount_factor(af.t)
af.forward_rate    = rfr.forward_rate(af.t)
af.spot_rate       = rfr.spot_rate(af.t)

# Solvency II BEL accumulation against the curve
af.bel = af.projection.accumulate(
    initial=0,
    multiply=1 / (1 + af.forward_rate),
    add=af.expected_claims - af.expected_premium,
)
```

**Worked example — stress overlay on a curve:**

```python
# Solvency II SF interest stress: parallel +/-100bps shifts from anchor
rfr_up   = rfr.shift_parallel(bps=+100)
rfr_down = rfr.shift_parallel(bps=-100)

# Three projections: base, up, down — share IR, differ only in the curve column
af.bel_base = build_bel(af, curve=rfr)
af.bel_up   = build_bel(af, curve=rfr_up)
af.bel_down = build_bel(af, curve=rfr_down)

# SCR interest = max stressed BEL change
af.scr_interest = pl.max_horizontal(
    af.bel_up - af.bel_base,
    af.bel_down - af.bel_base,
)
```

**Worked example — IFRS 17 OCI option (locked-in vs current curve, side-by-side):**

```python
# Two curves co-exist in the same projection
rfr_locked  = Curve.eiopa(currency="EUR", as_of=cohort.issue_date)
rfr_current = Curve.eiopa(currency="EUR", as_of=valuation_date)

af.df_locked  = rfr_locked.discount_factor(af.t)
af.df_current = rfr_current.discount_factor(af.t)

# CSM rolls forward at locked-in rates; OCI captures the current-vs-locked delta
# (full IFRS 17 cohort/CSM mechanics live in gaspatchio-ifrs17 sibling — this is the
# minimum core support to express the rate parallelism)
```

**Curves and the audit fingerprint.** A `Curve` instance has a stable canonical form: `(constructor_name, kwargs_sorted)` for predefined curves (`Curve.eiopa(...)`) or `(table_hash, interpolation_method)` for `from_table` curves. `spec_fingerprint()` includes the curve's canonical form when it appears in a transition body. The actual rate values feed `action_key()` via the input-data hash.

### 4.13 Contract-boundary primitive

**Why this is in core.** Solvency II Article 18, IFRS 17 paragraphs 33–35, and US LDTI all define a *contract boundary* — the projection horizon at which the insurer can no longer be compelled to provide cover or where they can reprice unilaterally. This is **not** the same as the spec's existing `lapse_when_all_non_positive` (which is non-forfeiture lapse — AV exhaustion). Elena's review: "A term-life policy with no AV has a contract boundary defined by *reviewability of premiums*, not state non-positivity. There's no API for 'stop projecting at month 60 because the insurer can reprice.'" Without an explicit primitive, every reg-tech consumer reinvents the contract-boundary check and the audit trail loses *why* a projection stopped.

**What it solves.** Two things: (a) makes the projection horizon a declared property of the rollforward, not an implicit consequence of `n_periods` × `lapse_*`. (b) Records *why* projection stopped at period N — for the actuarial function report (Solvency II) and IFRS 17 disclosure 132(b).

**Pattern + library.** Borrowed from **dbt's `exposures` declaration pattern** (validation pass — dbt deep-dive). The contract boundary is a *declared, named, typed reason for stopping* — the rollforward analogue of dbt's "this model serves this downstream consumer." It also has a flavour of MLIR's `terminator` Op (every Region has an explicit terminator that documents why control left).

**Worked example — explicit contract boundary on a term-life projection:**

```python
rf = af.projection.rollforward(
    states={"reserve": af.reserve_init},
    contract_boundary=ContractBoundary(
        when=af.is_repriceable,            # boolean column: True when insurer can reprice
        reason="Solvency II Art. 18 — premium-reviewability boundary",
        regulatory_anchor="EIOPA-Guidelines-CB-2015",
    ),
)

rf["reserve"].grow(af.discount_rate, label="Discount unwind")
rf["reserve"].add(af.expected_claims, label="Claims")
rf["reserve"].subtract(af.expected_premium, label="Premium")

af.reserve = rf["reserve"]
af.contract_boundary_period = rf.contract_boundary.first_breach_period()
af.contract_boundary_reason = rf.contract_boundary.reason  # documented
```

**Worked example — IFRS 17 contract boundary (different reason for same insurer):**

```python
rf = af.projection.rollforward(
    states={"lrc": af.unearned_premium},
    contract_boundary=ContractBoundary(
        when=af.no_substantive_obligation,
        reason="IFRS 17.33–35 — substantive-obligation boundary",
        regulatory_anchor="IFRS-17-Standard-2023",
    ),
)
```

**Worked example — VA with a non-mechanical boundary (utilisation election):**

```python
# A VA with an annuitisation election: contract boundary at the period the
# policyholder can elect, since post-election cashflows are a different contract
rf = af.projection.rollforward(
    states={"av": af.av_init},
    contract_boundary=ContractBoundary(
        when=af.policyholder_can_elect_annuitisation,
        reason="Annuitisation election — contractual phase change",
    ),
)
```

**Composition with `lapse_when_all_non_positive`.** The two are independent and both can be present:

```python
rf = af.projection.rollforward(
    states={"av": af.av_init, "guarantee": af.g_init},
    lapse_when_all_non_positive=["av", "guarantee"],   # mechanical exhaustion
    contract_boundary=ContractBoundary(                # regulatory horizon
        when=af.is_repriceable,
        reason="SII Art. 18",
    ),
)
```

The kernel stops at whichever fires first, and the rollforward output records both the period and the reason via `rf.stop_reason()` (`"lapse"` / `"contract_boundary"` / `"horizon"`).

**Contract boundary and the audit fingerprint.** The `ContractBoundary` declaration is part of the IR canonical form (its `reason` and `regulatory_anchor` strings are captured). Renaming the reason changes the spec_fingerprint — the audit trail is preserved.

### 4.14 Coverage gaps acknowledged but deferred

The validation pass (§17) surfaced four primitive families the design *could* support but does not in Phase 1. Documenting them here so that workarounds in Phase 1 don't paint the API into a corner.

| Primitive | What it would do | Use cases | Phase |
|---|---|---|---|
| `.reset_when(mask, to=expr)` | `state = expr if mask else state` at gate point | IUL segment boundaries, FIA buffer windows, multi-segment structured-outcome annuities | Phase 2 |
| **Categorical / status states** | non-numeric state types; transitions over a finite alphabet | Joint-life status (BB/AD/BD/DD), premium-paying status, dividend-option election | Phase 3 |
| **Sub-period state** | inner ticks within a period (e.g., daily within monthly) | Highest Daily, monthly-averaging IUL, daily-balance VUL fees | Phase 3 |
| **Vector / multi-fund states** | per-element transitions on a `List<Float64>` state | VUL with N sub-accounts, multi-fund VA | Phase 3 — small-N expressible today via N parallel scalar states |

These are *not* in Phase 1's scope but they share the IR — adding them later requires no breaking change to the canonical form.

---

## 5. Read/ordering semantics

This section is short but load-bearing for the audit story.

**Points are partially ordered.** The `points` list in the constructor declares a sequence. `bop` is implicitly first; `eop` is implicitly last. Other declared points sit between them in declared order. The kernel cannot execute a transition `between(p2, p3)` until all transitions that *write* anything addressable from `p3` and earlier have completed for that period.

**Transitions execute in declared order.** Within the order constraints from points, the actuary's chain order is preserved. Two transitions writing different states with no shared point dependency execute as written.

**Reads see written values.** `rf["S"].at("P")` resolves to S's value at the moment point P was reached. If P is `bop`, the read is the initial value (broadcast for the period). If P is `eop`, the read is the final value of S at the end of the period. If P is a mid-period point, the read is whatever S held when control passed through P.

**Every state has a defined value at every point — including untouched ones.** When the kernel passes through a point P, *every* state's current value is captured at P, regardless of whether any transition writing to that state ends at P. This is the carry-forward rule: a state with no mid-period transitions has the same value at every mid-period point, equal to its `bop` or last-written value. Reading `rf["S"].at("P")` is therefore always defined as long as P is a declared point — it is never undefined or backend-dependent.

**Forward references are illegal.** A transition writing state A between `(p1, p2)` may only read other states at points `≤ p1`. Reading a state at a point that hasn't been written yet (in the current period) is a compile-time error. This is detectable from the IR without running the kernel.

**Cross-period reads are not supported in transition bodies.** `rf["S"].at("P")` always means "this period's value." For previous-period reads, use the existing `.projection.previous_period()` accessor on the output column.

**Lapse resolution.** After all transitions for a period complete, `lapse_when_all_non_positive=[...]` is checked. The condition fires when every named state satisfies `state ≤ 0.0` — strict non-positivity, not strict equality to zero. Floating-point near-zeros (e.g., `-1e-15` from accumulated subtraction) trigger lapse. If the condition fires, all states are zeroed for the remaining periods. The boundary semantic (`≤ 0.0`) matches the shipped kernel; tests must cover exactly-zero, slightly-negative, and mixed-sign cases to lock the contract.

**The audit invariants this gives us:**
1. No silent breakage from label renames (no labels in addressing).
2. No race conditions or ordering ambiguity (declared order + point partial order).
3. The graph is statically analysable — `explain()` can show the order, `fingerprint()` can canonicalise it, lints can catch forward references.

---

## 6. GSP-95 alignment and the apply() escape hatch

### 6.1 Where the rollforward sits in GSP-95's layering

GSP-95 proposes three layers: DSL facade → semantic IR → backend lowering. The rollforward redesign aligns with this directly:

- **DSL facade.** `af.projection.rollforward(...)`, the state-handle methods, `.between()`, `.at()`, `.ratchet()`, `.when()`. User-facing.
- **Semantic IR.** A `(states, points, transitions)` graph. Each transition is a `TransitionSpec` with a target state, a from-point, a to-point, and a body. The body is either a named operation (`AddOp`, `GrowOp`, `RatchetOp`, ...) or a semantic-IR expression tree. Engine-agnostic. **This is the closed semantic subset for rollforward.**
- **Polars backend lowering.** The Rust kernel called via `register_plugin_function`. Owns the kwargs serialization, `pl.Expr` materialization, list buffer management. Named explicitly as `rollforward.PolarsBackend` in code organisation.

### 6.2 Engine portability is real, not aspirational

Because the IR is engine-agnostic by construction, lowering the same rollforward graph to a different engine is a tractable project — not a rewrite. A `NumpyBackend` (pure Python, no Rust required) is the natural smoke test: takes the same IR, runs a Python loop, returns the same numbers as the Rust kernel. This isn't shipped in the redesign — it's a follow-up — but the IR is designed so that the smoke test is achievable.

### 6.3 Transition bodies use the existing gaspatchio DSL surface

A transition body uses the same expression surface every other gaspatchio model uses — operators on proxies (`+`, `-`, `*`, `/`), comparisons (`==`, `<`, `<=`), `when().then().otherwise()`, and accessors. After PR #99, chained `when()` is list-aware with first-match-wins semantics.

```python
from gaspatchio_core import when

# Conditional inside a transition body:
adjusted = when(af.is_anniversary).then(af.bonus_rate).otherwise(af.base_rate)

# Two-arg max is currently pl.max_horizontal — a Polars-surface call,
# acknowledged as outside GSP-95's closed semantic subset for now:
withdrawal = pl.max_horizontal(rf["aw"].at("bop"), formulaic_amount)
```

What's *new* in transition bodies (vs writing the same expression at column-vectorised top level): two extensions handled by the rollforward compiler:
- **State reads at named points** — `rf["state"].at("point")` resolves to a kernel capture-slot reference.
- **Implicit "this period" indexing** — there is no `[t]` to write; the kernel handles per-period evaluation.

Everything else in the transition body is just gaspatchio expressions. There is no third DSL to learn.

### 6.4 The apply() escape hatch

When the named primitives don't fit a product's shape, the actuary writes the transition body as an expression directly using the surface above. There is no separate `.apply(fn)` escape — the expression language already in use IS the escape hatch. The named primitives (`.add`, `.grow`, `.ratchet`, ...) are sugar for common shapes; when those run out, the actuary drops down to the expression layer.

The GSP-92 VA Illustration's hard branch (§4.9 — the `(1+BA) · max(AW, V·bc_factor/12)` payment) is the canonical example: no special primitive, no `apply()`, just a polars-shaped expression with two state-at-point markers.

### 6.5 Where the rollforward sits relative to GSP-95's shipped state

GSP-95 Phases 1–3 are merged. The pieces this design rests on:

- **`polars_backend/` exists** (PR #101). The new Rust kernel's Python wrapper replaces the existing `polars_backend.plugins.rollforward_plugin` in place. No new directory is introduced.
- **Schema-as-source-of-truth for shape/kind** (PR #100). Transition bodies and `rf["state"].at("point")` markers compose with `proxy.shape` and `proxy.kind` consistently.
- **Chained list-aware `when()`** (PR #99). Used directly in transition bodies — no special handling required.

What the rollforward redesign **does not** depend on: any future GSP-95 phase. The closed semantic subset is currently Polars-shaped; that's fine — the rollforward IR is engine-agnostic in its structure (states, points, transitions, op types), and transition body portability tracks the broader DSL's portability over time.

### 6.6 Explicit non-goals here

The rollforward redesign does **not** take on:
- Refactoring `bindings/python/gaspatchio_core/column/dispatch.py`.
- Building a `JaxBackend` or `NumpyBackend`.
- Broadening the semantic IR beyond what rollforward needs.
- Removing the Polars `_autopatch()` mechanism.

Those are GSP-95's job. The rollforward design just slots into the direction.

---

## 7. Kernel architecture (Polars backend)

**Where it lives.** The Python wrapper that calls the kernel already exists at `bindings/python/gaspatchio_core/polars_backend/plugins.py` as `rollforward_plugin(args, kwargs)` returning `pl.Expr`. The redesign replaces the kernel implementation in place — no new package or import path is introduced. The Rust kernel source remains at `core/src/polars_functions/rollforward.rs` (the kernel module name is unchanged for stability of the FFI symbol).

The Rust kernel collapses to **a single execution path**. The shipped kernel's separate single-state and multi-state functions (~340 LOC each, ~90% duplicated) become one function parameterised by `num_states`. Single-state is the case `num_states == 1` with no cross-state reads.

**Inputs (kwargs from Python compile step):**
- `states: Vec<StateSpec>` — one entry per state, with name and initial-column index.
- `points: Vec<PointSpec>` — one entry per point, in declared order.
- `transitions: Vec<TransitionSpec>` — one entry per transition. Each carries a target state index, a from-point index, a to-point index, an optional gating column index, an optional label, and a body.
- `body: TransitionBody` — either a named operation enum (`Add { input_index }`, `Grow { input_index }`, `DeductNar { rate_index, db_index }`, `Ratchet { target_expr, gate_index? }`, ...) or an `ExprTree` AST for free-form expressions.
- `track_increments: bool`.
- `lapse_when_all_non_positive: Option<Vec<usize>>`.
- `contract_boundary: Option<ContractBoundarySpec>` — optional gating + reason recording. Phase 1 inclusion per §4.13.
- `batch_axes: Vec<String>` — Phase 1 Polars backend asserts `["policy"]` and rejects others. Field exists in IR for forward-compatibility with Phase 3+ stochastic sibling primitive.

**Inner loop, sketch:**

```rust
for t in 0..n_periods {
    // For each declared point in order, execute all transitions whose
    // to_point is this point, then snapshot ALL states at this point —
    // not just the ones written to by a transition. This implements the
    // carry-forward rule from §5: every state has a defined value at
    // every declared point, regardless of whether anything wrote to it.
    for point_idx in 0..points.len() {
        for transition in transitions_writing_to(point_idx) {
            let target = transition.target_index;
            let value_before = states[target];

            // Apply gating mask if present (skip the entire transition if gated off)
            if let Some(gate) = transition.gate_index {
                if input_columns[gate][t] == 0.0 {
                    continue;
                }
            }

            // Resolve state reads in the body using captured (state, earlier_point)
            // values plus current `states[]` for same-point reads.
            let new_value = evaluate(transition.body, &states, &captures, t);
            states[target] = new_value;

            if track_increments && let Some(label_idx) = transition.label_idx {
                increment_buffers[label_idx].push(states[target] - value_before);
            }
        }

        // Carry-forward: snapshot every state at this point, not only ones written.
        for state_idx in 0..num_states {
            captures[(state_idx, point_idx)] = states[state_idx];
        }
    }

    for i in 0..num_states { result_buffers[i].push(states[i]); }

    if let Some(ref lapse_indices) = lapse_when_all_non_positive {
        if lapse_indices.iter().all(|&i| states[i] <= 0.0) {
            zero_remaining_periods(...);
            break;
        }
    }
}
```

**Key changes from shipped kernel:**
- One function instead of two; the `num_states == 1` fast path is a branch, not a separate function.
- Captures are addressed by `(state_idx, point_idx)` pairs, not by string label. Both indices are pre-resolved by the Python compile step.
- The body is either a named-op variant (constant-time dispatch) or a small expression AST evaluated per period. The AST evaluator is a recursive `match` over a Rust enum — no allocations after construction.
- Periodic gating is a transition-level optional column index, not a separate `add_if`/`charge_if` step type. Eliminates two enum variants.
- Contract-boundary check sits alongside lapse check at end-of-period; whichever fires first writes the stop-reason and zeroes remaining periods.

### 7.1 Op-class vocabulary (MLIR dialect-shape pattern)

**Why this is in core.** Every transition body operation is a distinct *kind of thing* — `Add` and `Ratchet` have different validation rules, different argument shapes, different lowering paths. Today's spec encodes them as enum variants with implicit invariants. Per the validation pass, MLIR's dialect-shape vocabulary makes those invariants explicit and testable.

**What it solves.** Three things: (a) construction-time validation moves out of `_compile()` and into per-Op `verify()` methods (catches errors with the offending Op visible, not at the end of compilation); (b) the named-Op set becomes self-documenting (each Op declares its shape, its label policy, its formula); (c) future engines (Phase 2 NumpyBackend) get a clean dispatch surface — one `lower_to_numpy()` method per Op, zero shared global state.

**Pattern + library.** **MLIR's dialect + Op-with-verifier pattern** (validation pass — MLIR deep-dive). We borrow the *shape* (typed Op classes, per-Op `verify()`, one named lowering pass per backend) without the C++/TableGen ceremony. One dialect, ~14 Ops, plain Python `@dataclass` Op classes.

**Worked example — Op class shape:**

```python
# bindings/python/gaspatchio_core/rollforward/_ops.py
from dataclasses import dataclass, field
from gaspatchio_core.rollforward._verify import VerifyError

@dataclass(frozen=True, slots=True)
class RatchetOp:
    """GMxB ratchet: state = max(state, expr) gated by mask."""
    target: StateRef            # typed (state_idx, point_idx)
    expr: ExprTree              # semantic-IR expression
    gate: Optional[ColumnRef]   # boolean column or None
    label: Optional[str]

    def verify(self, ctx: VerifyContext) -> None:
        # Forward reference check (read of state at later point)
        for ref in self.expr.state_reads():
            if ref.point_idx > self.target.point_idx:
                raise VerifyError(
                    f"RatchetOp at {self.target}: reads {ref.state} at later point "
                    f"{ctx.point_name(ref.point_idx)}; only earlier or same-point reads allowed."
                )
        # Gate column dtype check
        if self.gate is not None and ctx.dtype_of(self.gate) != "boolean":
            raise VerifyError(
                f"RatchetOp at {self.target}: gate column has dtype "
                f"{ctx.dtype_of(self.gate)}; must be boolean."
            )
        # Track-increment label requirement
        if ctx.track_increments and self.label is None:
            raise VerifyError(
                f"RatchetOp at {self.target}: track_increments=True but no label set; "
                f"increment Struct field would be unnamed."
            )

    def lower_to_polars(self, ctx: LoweringContext) -> dict:
        return {"Ratchet": {
            "target_state": ctx.state_idx(self.target.state),
            "target_point": ctx.point_idx(self.target.point),
            "expr": self.expr.lower_to_polars(ctx),
            "gate_index": ctx.column_idx(self.gate) if self.gate else None,
            "label": self.label,
        }}
```

Every Op (Add, Subtract, Charge, Grow, GrowCapped, DeductNar, Floor, Cap, Ratchet, LapseIfZero, Capture-replacement, AddIf, ChargeIf, …) gets the same shape: `verify(ctx)`, `lower_to_polars(ctx)`, and (Phase 2) `lower_to_numpy(ctx)`.

**Worked example — error message before vs after:**

Before (today, monolithic `_compile()`):
```
ValueError: invalid kwargs: state at index 1 has unresolved capture reference
```

After (per-Op verifier):
```
RatchetOp at ("guarantee", "eop"): reads state "av" at later point "after_payment";
only earlier or same-point reads allowed. The transition writing "guarantee" between
"bop"→"eop" cannot reference "av" at a point that hasn't been written yet for this
period.
                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                         You probably want rf["av"].at("after_growth")
                                         instead, since "after_growth" is written before
                                         "eop" in the period.
```

This is what Aisha (junior persona) and Marcus (validation persona) both asked for — actionable errors with the offending source location and a remediation hint.

**Performance.** The kernel will be benchmarked. Targets are not specified numerically here; the goal is "fast" — same order of magnitude as the shipped kernel for products both can express, with regressions detected by Criterion benchmarks tracked in CI. The single-path collapse may improve cache behaviour modestly; the AST-evaluator overhead for free-form transition bodies is the main place to watch.

---

## 8. Compilation pipeline

### 8.1 Overview

```
RollforwardBuilder (Python)
    ↓ build (chain calls accumulate Op classes in tuple-backed immutable storage)
RollforwardIR (Python — engine-agnostic semantic representation)
    ↓ Pass chain (validate → resolve → fold → assign-slots → lower)
(args: list[pl.Expr], kwargs: dict)
    ↓ register_plugin_function (Polars boundary)
Rust kernel
    ↓ evaluate
Struct<List<Float64>>  ← one field per state, plus increments and per-(state,point) captures
    ↓ Python wrapper
Lazy Polars columns assigned to ActuarialFrame
```

### 8.2 Pass-based compilation chain (CVXPY pattern)

**Why a chain instead of a monolithic `_compile()`.** CVXPY's `Reduction` chain is the validation-pass canonical reference: the same problem object threads through a sequence of named, testable passes — each one a `(IR → IR)` function with a documented invariant. CVXPY uses this to support 10+ solver backends; gaspatchio uses it to support Polars today, NumPy/JAX/Mojo later. Without it, every backend addition is a 200-line patch to a god-function. With it, every backend is a new terminal pass; the upstream chain is shared and reused.

**What it solves.** Three things: (a) error messages improve dramatically because each pass owns a narrow class of failures (the validation pass agents flagged this — Aisha and Marcus both wanted actionable errors); (b) GSP-92's cross-state arithmetic adds as one pass, not a patch; (c) Phase 2's `NumpyBackend` smoke test reuses 4 of 5 passes, swapping only the terminal lowering.

**Pattern + library.** **CVXPY's `Reduction` chain** (validation pass — CVXPY deep-dive). Augmented with **MLIR's pass-manager naming** (each pass has a name, runs in declared order, can be inspected, can be unit-tested in isolation).

**Worked example — the chain shape:**

```python
# bindings/python/gaspatchio_core/rollforward/_compile.py
from typing import Protocol
from dataclasses import dataclass

class Pass(Protocol):
    name: str
    def apply(self, ir: RollforwardIR) -> RollforwardIR: ...

@dataclass(slots=True)
class Validate:
    """Run each Op's verify() method. Catches all construction-time invariants."""
    name: str = "validate"
    def apply(self, ir):
        ctx = VerifyContext(states=ir.states, points=ir.points,
                            track_increments=ir.track_increments)
        for op in ir.transitions:
            op.verify(ctx)            # raises VerifyError with offending Op
        # Top-level invariants: every state reaches eop, labels unique, etc.
        _check_completeness(ir)
        _check_label_uniqueness(ir)
        _check_batch_axes(ir)         # batch_axes == ("policy",) in Phase 1
        return ir

@dataclass(slots=True)
class ResolveStateRefs:
    """rf['av'].at('post_growth') → typed (state_idx, point_idx)."""
    name: str = "resolve_state_refs"
    def apply(self, ir):
        return ir.map_ops(lambda op: op.resolve_state_refs(ir.state_to_idx, ir.point_to_idx))

@dataclass(slots=True)
class FoldConstants:
    """1 + 0*x → 1; eliminates dead branches in when().then().otherwise()."""
    name: str = "fold_constants"
    def apply(self, ir):
        return ir.map_ops(lambda op: op.map_exprs(_fold))

@dataclass(slots=True)
class AssignCaptureSlots:
    """(state_idx, point_idx) pairs that are read → kernel slot indices."""
    name: str = "assign_capture_slots"
    def apply(self, ir):
        slots = _collect_read_pairs(ir)            # set of (s, p) referenced
        return ir.with_capture_slots(slots)

@dataclass(slots=True)
class LowerToPolarsPlugin:
    """Terminal pass for Polars backend: emit (args, kwargs) for the plugin call."""
    name: str = "lower_polars"
    def apply(self, ir):
        ctx = LoweringContext(ir)
        kwargs = {
            "states": [s.lower_polars(ctx) for s in ir.states],
            "points": [p.lower_polars(ctx) for p in ir.points],
            "transitions": [op.lower_to_polars(ctx) for op in ir.transitions],
            "track_increments": ir.track_increments,
            "lapse_when_all_non_positive": ir.lapse_states,
            "contract_boundary": ir.contract_boundary.lower_polars(ctx) if ir.contract_boundary else None,
            "batch_axes": list(ir.batch_axes),
        }
        return ir.with_lowered(args=ctx.input_columns, kwargs=kwargs)

# Polars chain assembly
POLARS_CHAIN: list[Pass] = [
    Validate(),
    ResolveStateRefs(),
    FoldConstants(),
    AssignCaptureSlots(),
    LowerToPolarsPlugin(),
]

def compile_rollforward(builder: RollforwardBuilder, chain: list[Pass] = POLARS_CHAIN) -> CompiledIR:
    ir = builder.to_ir()
    for p in chain:
        ir = p.apply(ir)              # tracing span = p.name for observability
    return ir.compiled
```

**Worked example — Phase 2 NumpyBackend reuses the chain:**

```python
# Same Validate, ResolveStateRefs, FoldConstants, AssignCaptureSlots — different terminal pass.
@dataclass(slots=True)
class LowerToNumpy:
    name: str = "lower_numpy"
    def apply(self, ir):
        ...  # emit a numpy-loop-shaped function from the IR

NUMPY_CHAIN = [
    Validate(),                       # SAME instance
    ResolveStateRefs(),               # SAME instance
    FoldConstants(),                  # SAME instance
    AssignCaptureSlots(),             # SAME instance
    LowerToNumpy(),                   # NEW terminal pass
]
```

The 4 upstream passes are engine-agnostic by construction. Adding a new backend is one new pass class, not a fork of `_compile()`.

**Worked example — debug-tracing the chain:**

```python
# Each pass produces a structured log line, observable at compile time
ir = compile_rollforward(builder, chain=POLARS_CHAIN)
# stdout (LOGURU_LEVEL=TRACE):
# [validate]            ok — 12 ops, 3 states, 5 points, batch_axes=('policy',)
# [resolve_state_refs]  ok — 8 (state, point) refs resolved
# [fold_constants]      ok — 3 sub-expressions folded
# [assign_capture_slots] ok — 6 distinct (s, p) read pairs → 6 slots
# [lower_polars]        ok — 12 transitions lowered, 9 input columns
```

### 8.3 What `_compile()` looks like end-to-end (GSP-92 walkthrough)

For the GSP-92 VA Illustration (§4.9):

1. **Validate** — `RatchetOp(target=("aw","eop"), expr=rf["fund"].at("after_growth")*..., gate=af.ratchet_active_mask, label="AW step-up")` runs `verify()`. Confirms `after_growth` is declared, sits before `eop`, gate column is boolean, label set (because `track_increments` defaults False but the actuary may have set it).
2. **ResolveStateRefs** — `rf["fund"].at("after_growth")` → `StateRef(state_idx=0, point_idx=1)`.
3. **FoldConstants** — `af.bc_factor * af.fac / 12` (all column refs, no folding) — pass-through.
4. **AssignCaptureSlots** — `(fund, after_growth)` is read by both the `fund` `subtract` transition and the `aw` `ratchet`; one slot allocated, both ops point to it.
5. **LowerToPolarsPlugin** — emits `args=[af.fund_init, af.aw_init, af.one_plus_ba, af.gib_rate, af.z_rate, af.bc_factor, af.fac, af.ratchet_active_mask]` and the kwargs Struct above.

Each step is independently testable, observable, and replaceable.

---

## 9. Fingerprint, action key, manifest, audit trail

### 9.1 Canonical form

The canonical form is the JSON serialisation of the rollforward IR with column names elided to positional indices (so two structurally identical builders against different ActuarialFrames produce the same fingerprint).

```jsonc
{
  "states": ["av", "aw"],
  "points": ["bop", "after_growth", "after_payment", "eop"],
  "transitions": [
    {"target": "av", "from": "bop", "to": "after_growth", "body": {"op": "Grow", "input": 0}, "label": "Net growth"},
    {"target": "av", "from": "after_growth", "to": "after_payment",
     "body": {"expr": {"binary": "subtract", "lhs": "state", "rhs": {...}}}, "label": "Payment"},
    {"target": "av", "from": "after_payment", "to": "eop", "body": {"op": "Floor", "value": 0.0}},
    {"target": "aw", "from": "bop", "to": "eop",
     "body": {"op": "Ratchet", "target_expr": {...}}, "gate": 4, "label": "AW step-up"}
  ],
  "track_increments": true,
  "lapse_when_all_non_positive": null
}
```

**Strictly more meaningful than today's canonical form.** Today's form excludes column wiring and step input ordering. The redesigned form includes:
- The full graph structure (states, points, transitions in order).
- Every operation and its parameters.
- Expression trees for free-form bodies.
- The gating wiring (presence/absence and which input column).
- The lapse condition.

**Labels are NOT cosmetic when increment tracking is enabled.** When `track_increments=True`, the labels of *tracked* transitions are part of the externally observable contract — they are the keys for `rf.increment("Premium")`, `rf.increment("COI")`, and the field names in the increment Struct columns. Renaming a label changes the public output schema. Therefore:

- When `track_increments=True`, the canonical form **includes** the label of every transition that has a label. Renaming a label changes the fingerprint.
- When `track_increments=False`, transition labels are cosmetic (used only by `explain()` output). The canonical form **excludes** them.

This keeps the fingerprint a faithful audit anchor: two rollforwards with the same fingerprint are guaranteed to produce identically-shaped output, including increment column names.

What's still always excluded: column *names* on inputs (positional indices instead, since column names are environment-dependent), and the actual data values.

### 9.2 explain() output

A formatted table per period, showing each transition in execution order with its formula. Mid-period points are visible. The actuary auditing the model reads `explain()` to verify the calculation order matches the spec.

```
Rollforward: 2 states (av, aw), 4 points (bop, after_growth, after_payment, eop)

  Step  Target  From → To                Operation        Formula
  ────  ──────  ─────────────────────    ──────────────  ──────────────────────────────────────
  1     av      bop → after_growth       Grow            av *= (1 + (one_plus_ba - gib - z))
  2     av      after_growth → after_pay Subtract        av -= one_plus_ba * max(aw_at_bop, av_at_after_growth * bc_factor / 12)
  3     av      after_payment → eop      Floor           av = max(av, 0)
  4     aw      bop → eop                Ratchet [gated] if ratchet_active: aw = max(aw, av_at_after_growth * bc_factor * fac / 12)
```

### 9.3 spec_fingerprint() — engine-portable spec identity

`sha256:<hex>` of the canonical JSON from §9.1. Engine-portable: the same builder produces the same spec fingerprint regardless of which backend (PolarsBackend, future NumpyBackend, etc.) ran it. This is the *recipe* identity — "two builders with this fingerprint encode the same calculation."

```python
fp = rf.spec_fingerprint()
# "sha256:a3f9c2e1...e21c"
```

**What it answers:** "Is this the same model as last quarter's reserve calculation?" — yes, if the fingerprints match.

**What it does NOT answer:** "Will this run produce the same numbers as last quarter?" — that requires `action_key()`.

### 9.4 action_key() — full hermetic run identity (Bazel pattern)

**Why this is in core.** Marcus (validation persona, SR 11-7) and Robert (Big-4 auditor) both flagged this as a blocking gap: the existing fingerprint hashes the IR, but two runs of the same IR can produce different bytes if the kernel is rebuilt with a different rustc, the Polars version drifts, FP mode changes, or the locale parses parquet differently. Robert: "I would NOT accept this for an unqualified opinion in current form" — citing the recipe-vs-result distinction explicitly.

**What it solves.** Binds a fingerprint to a *specific run*. Same `action_key()` ⇒ byte-identical output guaranteed across machines, threads, and time. Becomes the audit anchor for "this number came from this IR with these inputs in this execution context."

**Pattern + library.** **Bazel's content-addressed action cache** (validation pass — Bazel deep-dive). Bazel's `ActionKey` is a SHA-256 over the closure of *everything that could affect the output*: inputs, command, environment, tool digests, platform descriptor. We borrow the formulation; we do not need the cache infrastructure (Phase 3+).

**Worked example — `action_key()` composition:**

```python
from gaspatchio_core.audit import action_key, HermeticContext, RunInputs
from hashlib import sha256
import json, pathlib, polars as pl

# 1. Spec fingerprint (recipe)
spec_fp = rf.spec_fingerprint()                      # "sha256:a3f9...e21c"

# 2. Run inputs (data)
inputs = RunInputs(
    model_points_sha256=sha256(pathlib.Path("mp.parquet").read_bytes()).hexdigest(),
    assumption_tables={
        "mortality": "sha256:7b2c...91af",
        "lapse":     "sha256:c4e8...3a01",
        "expense":   "sha256:0192...77fd",
    },
)

# 3. Hermetic execution context (kernel and runtime)
ctx = HermeticContext.current()                      # introspects the running env
# ctx == HermeticContext(
#     engine_id="polars_backend",
#     engine_version="0.4.0",
#     kernel_artifact_sha256="...",     # digest of the .so/.dylib
#     polars_version="1.18.0",
#     rust_target_triple="aarch64-apple-darwin",
#     fp_mode="ieee-strict",
#     lc_numeric="C",
# )

# 4. Compose
ak = action_key(spec_fp, inputs, ctx)
# "sha256:b71f2c8...d403"

# Same ak across runs ⇒ byte-identical output. Bind this to the reserve number
# in the audit log; six months later, audit_replay(ak) recomputes and verifies.
```

**Worked example — what changes the action_key (and what doesn't):**

| Change | `spec_fingerprint` | `action_key` |
|---|---|---|
| Add a transition | ✓ changes | ✓ changes |
| Rename a tracked label (`track_increments=True`) | ✓ changes | ✓ changes |
| Rename an untracked label | — same | — same |
| Use a different mortality table (different SHA) | — same | ✓ changes |
| Upgrade Polars 1.18 → 1.19 | — same | ✓ changes |
| Rebuild Rust kernel with new optimization flags | — same | ✓ changes |
| Run on x86_64 vs aarch64 | — same | ✓ changes |
| Same code, same inputs, different machine, identical kernel build | — same | — same |

The split lets you audit "is this the same recipe?" (spec_fp) and "is this the same execution?" (ak) independently. Robert (auditor): a deterministic-replay request hashes to the same `ak`; auditor recomputes; bytes match.

### 9.5 Manifest emission (dbt pattern)

**Why this is in core.** The Reporting/Audit/Governance probe surfaced this directly: "There is no built-in concept of a `Run` artifact bundling: model fingerprint + assumption-set fingerprint + input-data hash + library version + git SHA + user identity + wall-clock + result hash." Operationally: a quarterly close cannot be reproduced months later with confidence, regulatory submission has no documented bill of materials, and selective re-run on assumption changes requires manual change-impact analysis.

**What it solves.** Five things: (a) regulatory submission packaging — one JSON file documenting every run; (b) selective re-run via `state:modified+`-style change detection; (c) impact analysis — declare downstream consumers (IFRS 17 disclosure, capital report) and find affected nodes when an upstream rollforward changes; (d) cross-team contracts — a rollforward declares its output schema and its consumers; (e) input-bill-of-materials for sample-test reproducibility.

**Pattern + library.** **dbt's `manifest.json` + `state:modified+` selector + exposures + contracts** (validation pass — dbt deep-dive). One JSON file emitted at compile time, content-addressed, language-agnostic, queryable.

**Worked example — `gaspatchio_manifest.json`:**

```jsonc
{
  "gaspatchio_version": "0.4.0",
  "manifest_schema_version": 1,
  "generated_at": "2026-05-02T14:22:00Z",
  "project_name": "gaspatchio_va",
  "nodes": {
    "rollforward.gaspatchio_va.va_illustration": {
      "unique_id": "rollforward.gaspatchio_va.va_illustration",
      "resource_type": "rollforward",
      "fqn": ["gaspatchio_va", "rollforward", "va_illustration"],
      "spec_fingerprint": "sha256:a3f9...e21c",
      "canonical_ir": { /* §9.1 form */ },
      "states": ["fund", "aw"],
      "points": ["bop", "after_growth", "after_payment", "eop"],
      "depends_on": {
        "columns": [
          "af.fund_init", "af.aw_init", "af.one_plus_ba",
          "af.gib_rate", "af.z_rate", "af.bc_factor",
          "af.fac", "af.ratchet_active_mask"
        ],
        "nodes": []
      },
      "produces": {
        "columns": ["af.fund", "af.aw"],
        "increments": ["Net growth", "Payment", "AW step-up"]
      },
      "contract": {
        "enforced": true,
        "states": [
          {"name": "fund", "dtype": "f64", "constraints": ["non_negative_after_floor"]},
          {"name": "aw",   "dtype": "f64", "constraints": ["monotonic_non_decreasing"]}
        ]
      }
    },
    "exposure.gaspatchio_va.ifrs17_csm_disclosure": {
      "unique_id": "exposure.gaspatchio_va.ifrs17_csm_disclosure",
      "resource_type": "exposure",
      "owner": {"team": "ifrs17", "email": "matt@opioinc.com"},
      "depends_on": {"nodes": ["rollforward.gaspatchio_va.va_illustration"]}
    }
  },
  "child_map": {
    "rollforward.gaspatchio_va.va_illustration": [
      "exposure.gaspatchio_va.ifrs17_csm_disclosure"
    ]
  }
}
```

**Worked example — `state:modified+` selector for selective re-run:**

```python
from gaspatchio_core.audit import diff_manifests, select_modified

last_quarter = json.loads(pathlib.Path("manifest_q1.json").read_text())
this_quarter = json.loads(pathlib.Path("manifest_q2.json").read_text())

# Compute change set
changed = diff_manifests(last_quarter, this_quarter)
# DiffResult(
#     added=[],
#     removed=[],
#     modified=["rollforward.gaspatchio_va.va_illustration"],
#     # The mortality table SHA changed → assumption_table dependency triggers
#     # rollforward.va_illustration to be considered "modified"
# )

# Re-run only modified nodes plus their downstream
to_run = select_modified(this_quarter, changed, downstream=True)
# {"rollforward.gaspatchio_va.va_illustration",
#  "exposure.gaspatchio_va.ifrs17_csm_disclosure"}    # downstream impact

# For 10M-policy actuarial portfolios this is the difference between
# 4-hour quarter close and 4-minute quarter close.
```

**Worked example — declaring an exposure (impact analysis):**

```python
from gaspatchio_core import Exposure

# Declare that the IFRS 17 CSM disclosure is a downstream consumer
csm_disclosure = Exposure(
    name="ifrs17_csm_disclosure",
    description="Quarterly IFRS 17 disclosure note 101A — CSM movement table",
    owner={"team": "ifrs17", "email": "matt@opioinc.com"},
    depends_on=[rf],
    regulatory_anchor="IFRS 17.100-105",
)

# When manifest_diff shows the rollforward changed, the impact report
# automatically names the IFRS 17 disclosure as affected.
```

**Worked example — contract enforcement (dbt-style construction-time validation):**

```python
rf = af.projection.rollforward(
    states={
        "fund": StateContract(init=af.fund_init, dtype="f64",
                              constraints=["non_negative_after_floor"]),
        "aw":   StateContract(init=af.aw_init, dtype="f64",
                              constraints=["monotonic_non_decreasing"]),
    },
    points=["bop", "after_growth", "after_payment", "eop"],
)

# Adding a transition that violates the contract fails at build time:
rf["fund"].subtract(huge_amount)   # might violate non_negative_after_floor
# At compile time:
# ContractViolation: state "fund" declares constraint "non_negative_after_floor"
# but transition `Subtract` between ("after_payment", "eop") could produce
# a negative value before the next floor. Add `.floor(0)` after this transition,
# or remove the constraint declaration if intentional.
```

### 9.6 explain() output

A formatted table per period, showing each transition in execution order with its formula. Mid-period points are visible. The actuary auditing the model reads `explain()` to verify the calculation order matches the spec.

```
Rollforward: 2 states (av, aw), 4 points (bop, after_growth, after_payment, eop)
spec_fingerprint: sha256:a3f9...e21c

  Step  Target  From → To                Operation        Formula
  ────  ──────  ─────────────────────    ──────────────  ──────────────────────────────────────
  1     av      bop → after_growth       Grow            av *= (1 + (one_plus_ba - gib - z))
  2     av      after_growth → after_pay Subtract        av -= one_plus_ba * max(aw_at_bop, av_at_after_growth * bc_factor / 12)
  3     av      after_payment → eop      Floor           av = max(av, 0)
  4     aw      bop → eop                Ratchet [gated] if ratchet_active: aw = max(aw, av_at_after_growth * bc_factor * fac / 12)

Run identity (when executed):
  action_key:  sha256:b71f2c8...d403
  inputs:      mp.parquet (sha256:7e3...), 3 assumption tables
  context:     polars_backend@0.4.0, polars 1.18.0, aarch64-apple-darwin
```

---

## 10. Migration

### 10.1 Versioning

`gaspatchio-core` 0.3.x → **0.4.0**. The redesign is a single breaking change. The 0.3.x line is end-of-life on 0.4.0 release.

### 10.2 What breaks for existing rollforward users

The only known consumer is `gaspatchio-va` pinned to 0.3.1. Breaks:
- `af.projection.rollforward(initial=...)` → `af.projection.rollforward(states={"av": ...})`.
- `.capture("name")` → `.at(point_name)` reads. Requires declaring `points=` in the constructor.
- `.ratchet_to(other_state)` → `.ratchet(to=rf["other_state"].at("eop"))`.
- `.pro_rata_with("capture", amount)` → write the expression directly using `rf[...].at(...)` reads.
- `.lapse_when(all_non_positive=[...])` builder method → `lapse_when_all_non_positive=[...]` constructor kwarg. Semantics identical, moved to the constructor because it's top-level configuration, not a step.
- Increment access: `af.av.increments["COI"]` → `rf.increment("COI")`.

### 10.3 Port plan for `gaspatchio-va`

1. Update the wheel pin from `gaspatchio-0.3.1-...whl` to `gaspatchio-0.4.0-...whl`.
2. Rewrite `model_va.py`'s rollforward block using the new API. Estimated ~30 minutes given the worked example in §4.9 maps almost line-for-line.
3. Delete `va_kernel.py` (the 244-line numpy escape) and the `apply_kernel` call in `model_va.py:258`.
4. Run `uv run pytest tests/test_kernel_replacement.py` to validate against `policy_00000065.parquet`. **Note:** the provenance of this gold file is a Phase-0 prerequisite — see §13.0. The port plan above only proceeds once the gold file is confirmed (or regenerated) as an independent source of truth.

### 10.4 What does not break

- `accumulate()` (the linear primitive) is unchanged.
- `af.projection.cumulative_survival()`, `previous_period()`, `next_period()`, `at_period()` are unchanged.
- All column-vectorised tutorial code (Levels 3, 4, 5) is unchanged — none of it uses rollforward.
- Increment-tracking semantics are unchanged (same labels-as-keys, same Struct output shape from the user's view).

---

## 11. Documentation deliverables

The redesign requires updates in the **gaspatchio-docs** repo (`../../../gaspatchio-docs`). Cross-repo dependency, not part of the gaspatchio-core diff but coupled to it.

| Doc | Update |
|---|---|
| `docs/concepts/rollforward/index.md` | Rewrite around the state-machine model. Lead with the simple UL example; introduce points-and-transitions only when needed. |
| `docs/concepts/rollforward/products/` | Refresh all eight product recipes. Add three new ones: VA + GMDB ratchet, VA + GLWB, IUL with lookback. |
| `docs/concepts/rollforward/audit-and-fingerprint.md` | New page. Cover the typed-capture audit invariants and engine-portable fingerprint. |
| `docs/concepts/rollforward/multi-state.md` | Rewrite. The current page says "VA guaranteed benefits are mentioned but deferred to multi-state documentation" — fulfil that promise with the new examples. |
| `docs/migration/0.4.0.md` | New page. The 0.3.x → 0.4.0 break list with sed-friendly before/after snippets. |
| `docs/concepts/rollforward/extending.md` | New page. When the named primitives run out, how to drop into expression-body bodies without leaving auditable territory. |

The `gaspatchio-docs` PR ships at the same time as the `gaspatchio-core` 0.4.0 release.

---

## 12. Testing strategy

Three tiers, weighted by what we want to learn.

### 12.1 Kernel correctness (unit-test level)

Carry over the existing tests from `bindings/python/tests/rollforward/`. Most can be ported with renamed arguments. New tests:

- `test_state_machine_constructor.py` — exercise points-opt-in, points-declared, multi-state, lapse condition.
- `test_at_reads.py` — verify `(state, point)` reads compile correctly, fail correctly on forward references, deduplicate correctly when the same `(state, point)` is read twice.
- `test_carry_forward_reads.py` — **untouched-state semantics**: declare a point, write only state A at it, then read state B at the same point. Must return B's value-as-of-the-previous-point (i.e., its `bop` value if no prior writes). Cover same-point B-write-after-A read, mid-period reads of states with no transitions ending at that point, and cross-state reads at every declared point.
- `test_ratchet_primitive.py` — the GMxB primitive against synthetic data with known step-up trajectories.
- `test_when_gating.py` — periodic gating produces expected sparse activation.
- `test_lapse_boundary.py` — lapse semantics at the `≤ 0` boundary: states at exactly zero, slightly negative (`-1e-15`), positive-but-trending, and mixed-sign cases. Lock the contract.
- `test_compile_to_ir.py` — round-trip a builder through the IR and back to canonical JSON.
- `test_fingerprint_label_sensitivity.py` — when `track_increments=True`, renaming a tracked label changes the fingerprint. When `track_increments=False`, renaming a label does not change the fingerprint.

### 12.2 VA acceptance test (integration)

The acceptance test from GSP-92 is the redesign's gate. Lives in `gaspatchio-va` (sibling repo). The test reconciles 25 list-typed columns to `policy_00000065.parquet` for `pol_num == 65` at `atol ≤ 1e-9` over 1200 periods. **Prerequisite (see §13.0):** the gold file must be confirmed as an independent source of truth (or regenerated from Excel) before this gate is meaningful. No Phase 1 code lands until that's resolved.

### 12.3 Engine-portability smoke test (forward-looking)

A minimal `NumpyBackend` (pure Python, no Rust) that lowers the same rollforward IR to a numpy loop and produces the same numbers as the Rust kernel. Not for production; purely a smoke test that the IR is genuinely engine-agnostic.

This is the GSP-95 alignment proof. It establishes that the redesign's claim of engine-portability is real, not aspirational.

### 12.4 Benchmarks

Criterion benchmarks for the Rust kernel go into `core/benches/`. No specific numerical targets — the goal is "fast" and tracked-against-regressions. Suite covers: simple UL, multi-state VA, with/without increment tracking, with/without gating, with/without expression-body transitions.

The Polars `realistic_vector_lookup` benchmark remains the authoritative measure for non-rollforward operations and is unaffected by this work.

---

## 13. Phasing

### 13.0 Phase 0 — Prerequisites (must complete before any code is written)

These items are gates, not work. Phase 1 does not start until they resolve.

1. **Confirm the provenance of `policy_00000065.parquet`.** The acceptance gate is only meaningful if the gold file is an *independent* source of truth — i.e., generated from the Excel model, not from `va_kernel.py`. Possible outcomes:
   - **Gold is from Excel.** Acceptance test stands as written; proceed to Phase 1.
   - **Gold is from `va_kernel.py`.** Regenerate from Excel before Phase 1. The redesigned kernel must reconcile to a baseline that does not depend on the kernel being replaced; otherwise the test merely confirms bug-for-bug parity with code we are deleting.
   - **Gold cannot be regenerated from Excel within the project window.** Phase 1 does not ship. Surface this to GSP-92 stakeholders and re-scope.
   This is a hard precondition: deleting `va_kernel.py` while the only release gate validates against `va_kernel.py`'s output is unacceptable for a breaking 0.4.0 release.

2. **State-read marker mechanism (decided, not a spike).** Per `ref/37-dispatch-engine-refactor/ARCHITECTURE.md`, GSP-95 explicitly chose not to bet on Polars custom-expression-node registration ("arbitrary autopatched Polars `Expr` methods are not treated as future-engine portable"). The rollforward compiler walks expressions itself: `rf["state"].at("point")` is a small typed marker class returning a sentinel `pl.Expr` (or wrapper) that the compiler intercepts during `_compile()`, substituting kernel capture-slot references. No reliance on a Polars extension API.

### 13.1 Phase 1 — Core redesign (one PR), validation-pass-aligned

The validation pass (§17) expanded Phase 1's scope from the original draft. New items are flagged **[NEW]**.

**Kernel + IR**
- New Rust kernel: single execution path, points-and-transitions, expression-body evaluator, carry-forward state captures at every point, periodic gating, increment tracking.
- **[NEW]** `batch_axes` field in IR with Phase 1 assertion `== ("policy",)` — paves the way for Phase 3+ stochastic sibling without IR-breaking change.
- **[NEW]** `contract_boundary` optional kwarg with regulatory-anchor reason recording (§4.13).

**Python builder + compilation**
- New Python builder: state-machine model, all primitives in §4.2, IR-and-canonical-form.
- **[NEW]** Pass-based `_compile()` chain (§8.2) — `Validate → ResolveStateRefs → FoldConstants → AssignCaptureSlots → LowerToPolarsPlugin`. Each pass independently testable, observable.
- **[NEW]** Per-Op `verify()` methods (§7.1) — actionable construction-time errors with offending Op visible.
- **[NEW]** `Curve` type as first-class primitive (§4.12) — EIOPA/custom curves with stress-shift methods.

**Audit + reproducibility**
- **[NEW]** `spec_fingerprint()` and `action_key()` — split per §9.3, §9.4 (Bazel pattern).
- **[NEW]** `gaspatchio_manifest.json` emission at compile time (§9.5, dbt pattern). Includes nodes, lineage, contracts, exposures.
- **[NEW]** `Exposure` declarations for downstream-consumer impact analysis (§9.5).

**Validation + tests**
- Test suite ported and extended (incl. carry-forward semantics, lapse boundary, fingerprint label-sensitivity — see §12.1).
- **[NEW]** Determinism contract — CI matrix proves `action_key`-keyed runs are bit-identical across at least two architectures (x86_64 Linux, aarch64 macOS).
- **[NEW]** `state:modified+` selector test — manifest diff round-trip with selective re-run validation.

**Migration + ship**
- `gaspatchio-va` ported, `va_kernel.py` deleted, acceptance test passes against the **independently provenanced** gold file (Phase 0 prerequisite).
- `gaspatchio-docs` updates (cross-repo PR, lands at the same time) — incl. `Curve` type, `ContractBoundary` semantics, manifest format.
- 0.4.0 release.

**Estimated scope.** ~10–15% growth over the draft Phase 1 surface. The new items are individually small (each ~50–200 LOC) but compound: action_key + manifest = audit story; pass chain + per-Op verify = error-message story; Curve + contract_boundary = reg-tech foundation.

### 13.2 Phase 2 — Engine portability proof + governance polish (follow-up PR)

- `NumpyBackend` smoke test (validates IR engine-agnosticism by construction).
- **[NEW]** `.reset_when(mask, to=expr)` primitive — IUL segment boundaries, FIA buffer windows.
- **[NEW]** `RollforwardTemplate` (unbound, YAML-serialisable, GSP-87 governance use case).
- **[NEW]** Op rewrite passes for canonicalisation — e.g., fold consecutive `add` ops on the same target between identical points (MLIR pattern).
- Reuse-or-merge with GSP-95's broader semantic IR depending on which lands first.

### 13.3 Phase 3 — Stochastic sibling + categorical states + sub-period state

The stochastic decision (Q1 of validation pass) commits this phase to the sibling primitive:

- **[NEW]** `af.projection.stochastic_rollforward(states=..., scenarios=N)` sibling sharing the rollforward IR with `batch_axes = ("scenario", "policy")`. Reuses Polars backend with row-major scenario broadcast OR a future `JaxBackend` with true `vmap`-over-`scan`.
- **[NEW]** Tail aggregators on the scenario axis: `rf.cte(level=0.7)`, `rf.var(level=0.995)`, `rf.tail_mean(...)`.
- **[NEW]** Pathwise greeks scaffold: `af.greeks.bump(input=..., shock=..., common_random_numbers=True)`.
- **[NEW]** Categorical / status states for joint-life mechanics (BB / AD / BD / DD alphabet).
- **[NEW]** Sub-period state primitives — `sub_periods=N` constructor kwarg and `.ratchet_over(tape_column)` for daily-granularity ratchets within monthly periods (Highest Daily, monthly-averaging IUL).
- Mid-chain assertions (deferred from the shipped design; transition-level optional kwarg).
- `validate_against(spec)` and `rf.diff(other)` from GSP-87.
- URI-keyed op identity migration (Substrait pattern) — `ratchet` → `gaspatchio.ops.v1.ratchet` in canonical form.

### 13.4 Sibling packages (separate repos, deferred until customer demand)

Per the reg-tech scope decision (Q2), the following live in dedicated sibling packages, NOT in `gaspatchio-core`:

- **`gaspatchio-ifrs17`** — cohorts as first-class dimension, CSM rollforward conventions (BBA / VFA / PAA), risk-adjustment release patterns, coverage-unit allocation, OCI option, loss-component bifurcation, movement-analysis primitives.
- **`gaspatchio-solvency`** — SCR sub-modules, MA/VA-aware curves on top of the `Curve` type, ORSA scenario harness, internal-model integration.
- **`gaspatchio-ldti`** — net-premium-ratio, MRB fair value, cohort-level remeasurement.

Core provides the kernel + Curve + contract_boundary; siblings provide the regulatory wrappers. This keeps gaspatchio-core a kernel rather than a regulatory platform.

---

## 14. Open questions and non-goals

### 14.1 Open questions

**RILA / FIA-GLWB hint.** Cross-product research flagged Registered Index-Linked Annuities and Fixed-Indexed Annuities with GLWB riders as adjacent product families inheriting the VA pattern. The redesign covers them by construction but no test product validates this. If a customer brings one, it's a strong signal to add a worked example.

**Performance ceiling for expression-body transitions.** The AST evaluator has per-period overhead (recursive match dispatch). For named primitives (`Add`, `Grow`, `Ratchet`, ...) the dispatch is constant-time. For free-form expression bodies, overhead scales with AST size. Benchmarks will show whether this is meaningful at production scale; mitigation if needed is an optional bytecode-style flat representation.

### 14.2 Explicit non-goals

- **Mid-chain assertions** — design preserves space (transition-level optional kwarg, currently no-op) but doesn't ship them. Phase 3.
- **`RollforwardTemplate`** (unbound + YAML, for GSP-87 governance) — Phase 2.
- **`validate_against` / `rf.diff`** — Phase 3, falls out of manifest-diff naturally.
- **Building a non-Polars backend in production** — Phase 2 ships a smoke-test `NumpyBackend` only. Production engines are GSP-95's territory.
- **Refactoring `dispatch.py`** — GSP-95.
- **Removing Polars `_autopatch()`** — GSP-95.
- **Cross-period reads inside transition bodies** — `rf["S"].at("P")` is always "this period." Previous-period values are accessed via the existing `.projection.previous_period()` accessor on output columns.
- **Stochastic / nested projections in Phase 1** — Phase 3 sibling primitive (`stochastic_rollforward`); Phase 1 reserves `batch_axes` IR slot for forward-compat.
- **IFRS 17, Solvency II, US LDTI in core** — sibling packages only (§13.4). Core provides `Curve` and `contract_boundary` as the regulatory-anchor primitives; everything else lives downstream.
- **Pathwise sensitivities via AAD** — separate engineering effort, not in scope for any phase here.
- **Replicating portfolio fitting** — downstream consumer of the rollforward, not a kernel concern.
- **Categorical / status states** — Phase 3 (joint-life).
- **Sub-period state granularity** — Phase 3 (Highest Daily, monthly-averaging IUL).
- **Vector / multi-fund states** — Phase 3+ (small-N expressible today via N parallel scalar states).

---

## 15. References

1. Bauer, D., Kling, A., Russ, J. (2008). *A Universal Pricing Framework for Guaranteed Minimum Benefits in Variable Annuities*. ASTIN Bulletin 38(2). Establishes the unifying `max{G, A}` kernel for GMxB riders.
2. Holz, D., Kling, A., Russ, J. (2012). *GMWB For Life — An Analysis of Lifelong Withdrawal Guarantees*. ZVersWiss. §3.2.2 contains the GLWB transition equation `G^E_{t+} = max(G^E_{t−}, x_W · A^+_t)`.
3. Piscopo, G., Haberman, S. (2011). *The Valuation of Guaranteed Lifelong Withdrawal Benefit Options in Variable Annuity Contracts*. NAAJ. §2 step-up condition.
4. NAIC, *Actuarial Guideline XXXVIII (AG 38)* — ULSG shadow account mechanics.
5. GSP-92 (Linear) — "Multi-state rollforward: missing primitives for cross-state arithmetic with mid-period column derivation."
6. GSP-95 (Linear) — "Dispatch / broadcasting refactor (semantic IR + Polars backend boundary)." Phases 1–3 merged into develop as PRs #99, #100, #101.
7. `ref/37-dispatch-engine-refactor/ARCHITECTURE.md` — post-implementation architecture guide for the dispatch / boundary surface this redesign builds on. **Read this before the spec.**
8. `ref/37-dispatch-engine-refactor/specs/2026-04-30-dispatch-engine-refactor-design.md` — the GSP-95 design as shipped (preserved as written).
9. `ref/31-rollforward-api/31-rollforward-design.md` — original GSP-86 design (now superseded).
10. `ref/26-recursive-accumulation/26-background-review.md` — earlier `scan_linear` primitive proposal.
11. `core/project.md` — design principles (formula-faithful API, no Python loops in hot path, etc.).
12. `core/src/polars_functions/rollforward.rs` — current kernel (will be replaced in place).
13. `bindings/python/gaspatchio_core/polars_backend/plugins.py` — the Python wrapper that calls the kernel; `rollforward_plugin` already exists.

---

## 16. Acknowledgements

This design is informed by three parallel research investigations into (a) the canonicality of the VA living-benefit kernel across riders, (b) the recurrence of the cross-state-with-capture shape in non-VA products, and (c) how open-source actuarial frameworks (lifelib, modelx, Heavylight, JuliaActuary) structure projection APIs. The recurring lesson from those frameworks — that lifelib's `CashValue_ME` reaches 80+ interdependent cells with string-keyed timing, exactly the Christmas-tree pattern we want to avoid — drove the decision to make points typed and structural rather than label-addressed.

The §17 validation pass added a second wave of research: 7 actuary-persona simulations, 5 use-case coverage probes against a domain taxonomy, and 6 SOTA library deep-dives across adjacent design domains (JAX, MLIR, dbt, CVXPY, Bazel, Substrait). All seven personas, five probes, and six deep-dives are sourced in §17 with their findings.

---

## 17. Validation pass — research findings and scope decisions

This section is the audit trail for *why* the spec evolved between its initial draft (committed `aad0b22`, 2026-04-30) and the current revision (committed 2026-05-02). It records the research methodology, the cross-cutting findings, and the three scope decisions taken in response.

### 17.1 Research methodology

A three-stream parallel research investigation, dispatched as 18 sub-agents:

**Phase 0 — Scoping (3 prelim agents).** A roles-inventory agent identified the universe of actuarial roles that would interact with the framework and recommended a 7-persona shortlist. A use-case-taxonomy agent enumerated the practical projection workflows across product types, accounting frameworks (IFRS 17, US LDTI, Statutory, MCEV), capital regimes (Solvency II, LICAT, RBC, HKICO), pricing/profitability, ALM, risk, and reporting cycles. A library-shortlist agent surveyed adjacent-domain OSS (quant finance, declarative compute IRs, audit/governance, DAG engines, DSLs with pluggable backends) and ranked the top 6 for deep-dive.

**Phase 1 — Three streams (15 deep agents in parallel).** Stream 1 was 7 actuary-persona cold-reads of the spec (Priya — Sr Pricing VA/GMxB; Marcus — Model Validation SR 11-7; Hannah — IFRS 17 Lead; Daniel — Stochastic VA Hedging; Aisha — Junior Reserving; Robert — Big-4 External Auditor; Elena — Solvency II Pillar 1). Stream 2 was 5 coverage probes against the use-case taxonomy (IFRS 17 mechanics; living-benefit & exotic riders; product-mechanic features; stochastic & capital; reporting & audit & governance). Stream 3 was 6 SOTA deep-dives (JAX `lax.scan`; MLIR dialects; dbt manifest+lineage; CVXPY reduction chain; Bazel action cache; Substrait IR design).

Total ~1.2M tokens, ~30 minutes wall time, fully parallel.

### 17.2 Cross-cutting findings

Three concerns recurred with high consensus across personas and probes:

**A. Determinism + audit-trail is recipe-only, not result-grade.** Marcus (validation, SR 11-7) and Robert (Big-4 auditor) both gave conditional or no sign-off. The original spec fingerprinted the *graph* but the actual *run* (engine version, Rust kernel build hash, Polars version, FP mode, locale, input-data hash, user/timestamp) was unspecified. Robert: "I would NOT accept this for an unqualified opinion in current form." Resolved in this revision via the `spec_fingerprint()` / `action_key()` split (§9.3, §9.4) and the `gaspatchio_manifest.json` artefact (§9.5).

**B. Scenario / batch axis is not first-class.** Daniel (stochastic VA hedging) and Priya (Sr Pricing) flagged: VA pricing committee work, AG 43, EV with TVOG, and dynamic hedging are blocked because the original `with_scenarios` cross-join is the wrong cost model at 5K paths × 100K policies. Spec §14.2 explicitly deferred stochastic; the personas argued this *is the daily work*. Resolved: stochastic stays a Phase 3+ sibling (per scope decision), but Phase 1 IR carries `batch_axes` (§3) so future backends don't need an IR-breaking change.

**C. IFRS 17 + Solvency II are structurally different problems.** Hannah and Elena both ended with "this is good for what it is, but not the platform I need." Specific gaps: cohorts as a dimension (Hannah), locked-in vs current rate parallelism for OCI option (Hannah), loss-component routing on negative CSM (Hannah), coverage unit allocation (Hannah), yield curves as first-class objects with VA/MA (Elena), contract boundary as a regulatory concept distinct from non-forfeiture lapse (Elena), stress overlay composition (Elena). Resolved: `Curve` and `contract_boundary` land in core (§4.12, §4.13); cohorts/CSM/coverage-units live in sibling packages (§13.4).

### 17.3 Coverage gaps surfaced (Stream 2)

Beyond the cross-cutting findings, Stream 2 surfaced primitive-level gaps documented in §4.14:

- **State reset (`.reset_when`)** — IUL segment boundaries, FIA buffer windows, structured-outcome annuities. Phase 2.
- **Categorical / status states** — joint-life mechanics (last-survivor, first-to-die), premium-paying status, dividend-option election. Phase 3.
- **Sub-period state granularity** — Highest Daily, monthly-averaging IUL, daily-balance VUL fees. Phase 3.
- **Vector / multi-fund states** — VUL with N sub-accounts. Phase 3+ (small-N expressible today).
- **GLWB no-withdrawal bonus interaction** with `.ratchet`'s `when=` kwarg — needs a worked example to lock the semantics.
- **GLWB lifetime payment after AV exhaustion** — `lapse_when_all_non_positive` zeroes all states, but GLWB income should continue. Phase 1: documented as a known caveat; Phase 3: explicit per-state `lapse=False` flag.

### 17.4 SOTA patterns adopted (Stream 3)

| Library | Pattern adopted | Spec section |
|---|---|---|
| **JAX `lax.scan`** | Carry-vs-emitted separation, batch-axis metadata, PyTree IR | §3 (`batch_axes`), §13.3 (stochastic sibling) |
| **MLIR dialects** | Typed Op classes with per-Op `verify()`, named lowering passes, rewrite-pass framework | §7.1 (Op vocabulary), §13.2 (canonicalisation) |
| **dbt manifest + lineage** | `gaspatchio_manifest.json`, `state:modified+`, contracts, exposures | §9.5 |
| **CVXPY reduction chain** | Pass-based `_compile()` chain with named, testable passes | §8.2 |
| **Bazel action cache** | `spec_fingerprint()` / `action_key()` split, hermetic-input boundary | §9.3, §9.4 |
| **Substrait** | URI-keyed op identity (deferred to Phase 3, IR-compatible today) | §13.3 |

### 17.5 Scope decisions

Three explicit decisions taken to bound the redesign:

**Q1. Stochastic projection** — Phase 3+ sibling primitive. Phase 1 reserves the IR slot (`batch_axes`) but ships no stochastic functionality. Avoids the wrong-cost-model trap of cross-join while keeping the door open for the JAX `vmap`-over-`scan` pattern.

**Q2. IFRS 17 / Solvency II** — Mixed scope. `Curve` type and `contract_boundary` primitive land in core (they are general primitives that multiple regulatory regimes share). Cohorts, CSM mechanics, coverage units, OCI option, MRB FV, capital sub-modules all live in sibling packages (`gaspatchio-ifrs17`, `gaspatchio-solvency`, `gaspatchio-ldti`) and ship only on customer demand.

**Q3. Run manifest + action_key** — Phase 1, both. Adds ~10% scope to Phase 1 but unblocks audit sign-off from day one (Marcus / Robert blocking concerns).

### 17.6 What the validation pass did NOT recommend

Three things deliberately rejected:

- **Redesign from scratch.** All 6 SOTA agents agreed the existing IR is structurally sound — JAX, MLIR, CVXPY all describe the same `(states, points, transitions)` shape gaspatchio already has. The verdict was "evolve, not restart."
- **Adopting MLIR-the-library or Substrait-the-protobuf.** Borrow the *shape* of dialects + URIs without the C++/protobuf ceremony. Phase 1 stays Python-native.
- **Committing to AAD / pathwise greeks / nested stochastic.** Stochastic-as-sibling does not commit to these. They remain separate engineering work.

### 17.7 Persona verdicts in summary

| Persona | Trust verdict | Phase 1 unblocks them? |
|---|---|---|
| Priya — Sr Pricing (VA/GMxB) | Conditional yes for deterministic profit-test. No for VA pricing under risk-neutral. | Partial — VA pricing waits for Phase 3 stochastic. |
| Marcus — Model Validation (SR 11-7) | Conditional sign-off after action_key + manifest. | Yes — addressed by `action_key()` + manifest. |
| Hannah — IFRS 17 Lead | No as platform. Yes as kernel underneath `gaspatchio-ifrs17`. | Yes for the kernel role. Sibling package is its own milestone. |
| Daniel — Stochastic Modeller | No for hedging or AG 43. | No — Phase 3 stochastic sibling. |
| Aisha — Junior Reserving | Not unsupervised. Needs FAM textbook bridge. | Improves with per-Op verifier error messages + docs. |
| Robert — Big-4 Auditor | Would not accept for unqualified opinion as drafted. | Yes — addressed by `action_key()` + manifest + determinism contract. |
| Elena — Solvency II Pillar 1 | Not for QRT today. | Partial — `Curve` + `contract_boundary` unblock the kernel; SCR overlays live in sibling. |

### 17.8 Research artefacts

The full agent transcripts (Phase 0 + Stream 1 + Stream 2 + Stream 3) are summarised in `ref/36-rollforward-redesign/research/2026-05-02-validation-pass-summary.md`. Individual transcripts are in `/private/tmp/claude-501/.../tasks/*.output` (machine-local; not committed).
