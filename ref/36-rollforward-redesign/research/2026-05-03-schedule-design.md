# Schedule Design Pass — Real-Evidence Grounding (2026-05-03)

A focused design-risk pass for the typed `Schedule` / `Calendar` / `DayCount` primitives proposed for Phase 1 of the rollforward redesign. The pass was triggered by the user's instinct that Schedule carried more design risk than the other typed inputs (`Curve`, `Table`, `MortalityTable`) — period semantics, day-count conventions, and business-day handling are rife with footguns, and a Schedule type that becomes load-bearing in `spec_fingerprint` would be expensive to retrofit.

The pass ran 4 parallel research agents:

- **Agent A** — QuantLib lineage. Identify the *minimum useful public surface* of QuantLib's `Calendar`, `DayCounter`, `Schedule`, and `BusinessDayConvention` types. What's load-bearing vs vestigial for actuarial use.
- **Agent B** — Actuarial OSS state of the art. How do lifelib, JuliaActuary, Heavylight, modelx, pyliferisk handle dates and period boundaries today? What patterns have they converged on, and what gaps remain?
- **Agent C** — Jurisdictional conventions. What day-counts and period semantics do real US/UK/EU life insurers actually use in production, per VM-20/VM-21 (NAIC), Solvency II (EIOPA), IFRS 17 (IASB), and Big-4 implementation guidance?
- **Agent D** — GSP-92 VA pain probe. Walk through the GSP-92 VA Illustration (the canonical hard case the redesign exists to enable) and enumerate the date / period-semantic gotchas a real Schedule would have to handle.

This document captures the findings, the cross-cutting synthesis, and the Phase 1 design commitments that emerged.

---

## Findings

### Agent A — QuantLib lineage

**`Calendar` minimum useful surface.** ~10 methods total: `isBusinessDay(d)`, `isHoliday(d)`, `isWeekend(w)`, `adjust(d, BusinessDayConvention)`, `advance(d, n, TimeUnit, conv, endOfMonth)`, `holidayList(from, to, includeWeekEnds)`, `endOfMonth(d)`, `isEndOfMonth(d)`, plus identity (`name()`, `operator==`).

Calendars actuaries actually need (~7 cover real use): `NullCalendar`, `WeekendsOnly`, `UnitedStates(Settlement)`, `UnitedKingdom(Settlement)`, `TARGET`, `JointCalendar`, `BespokeCalendar`. Other country calendars exist but are second-tier.

**`DayCounter` minimum useful surface.** Just three methods: `name()`, `dayCount(d1, d2)`, `yearFraction(d1, d2, refStart, refEnd)`. The reference-period args are `ActualActual::ISMA`-only; everything else ignores them. Five conventions cover real use:

- `Actual365Fixed` — ISDA Act/365F (load-bearing)
- `Actual360` — money-market (load-bearing)
- `Thirty360` with `BondBasis` and `European` enum values (the rest are aliases)
- `ActualActual` with `ISDA` and `ISMA` variants (the rest are vestigial)
- `Business252(Calendar)` — Brazilian/business-day denominator (calendar-parameterised)

The longer QuantLib catalog (`Actual364`, `Actual36525`, `Thirty365`, `OneDayCounter`, `SimpleDayCounter`, etc.) is vestigial.

**`Schedule` minimum useful surface.** Two constructors — raw `vector<Date>` or rule-based `(effective, termination, tenor, calendar, convention, terminationConvention, DateGeneration::Rule, endOfMonth, firstDate, nextToLastDate)`. `MakeSchedule` is the fluent builder. Element access is STL-style (`size()`, `operator[](i)`, `at(i)`, iterators). Stub handling via `firstDate` (front stub) / `nextToLastDate` (back stub) plus `DateGeneration::Rule` enum — only `Backward`, `Forward`, `Zero` matter for actuarial use.

**Critical observation:** `Schedule` *holds* `Calendar` but does *not* hold `DayCounter`. DayCounter is passed separately to pricing engines / accrual code. The composition in real QuantLib is `cal → schedule`, then `(schedule, dc) → accrual`.

**`BusinessDayConvention` enum.** Seven values total in the catalog; only four matter for actuarial use: `Following`, `ModifiedFollowing`, `Preceding`, `Unadjusted`. The rest (`ModifiedPreceding`, `HalfMonthModifiedFollowing`, `Nearest`) are fixed-income edge cases.

**Composition pattern.** Build Calendar → MakeSchedule with calendar+convention+rule → iterate `(d_prev, d_next)` pairs → consumer (e.g., rollforward kernel) holds DayCounter and computes `dt = dc.yearFraction(d_prev, d_next)`.

### Agent B — Actuarial OSS state of the art

**lifelib** — Mixed picture. The educational examples (`BasicTerm_M`, `BasicTerm_S`) use **pure integer monthly `t`** with `duration(t) = t//12` and no calendar at all. The "industrial" examples (`BasicTermASL_ME`, `BasicBonds`, `appliedlife/IntegratedLife`) hand-roll real dates via `pandas.Timestamp` and `pd.offsets.MonthEnd(1)` / `YearEnd(1)`, with a recursive `date_(i) = date_(i-1) + offset(i-1)` cell and bespoke helpers like `next_anniversary(i, freq_id)`, `last_part(i)`, `next_part(i)` to split a calendar month around a mid-month anniversary. Day counts in `BasicBonds` are delegated to **QuantLib** (`ql.Actual360()`). No first-class `Schedule` / `Calendar` / `DayCount` type — every model re-derives the same logic.

**JuliaActuary** — Most mature, but explicitly **punts on dates**. `FinanceCore.jl` / `FinanceModels.jl` operate on `Float64` time. The FAQ tells users: *"Currently, you must convert the `Date` into a real-valued timepoint for use within the models and contracts."* Day counts are delegated to a separate package `DayCounts.jl`; business days to `BusinessDays.jl`. Open tracking issue [`FinanceModels.jl#155 — Allow handling of Dates`](https://github.com/JuliaActuary/FinanceModels.jl/issues/155) admits the gap. The mature comparator in this org is `ExperienceAnalysis.jl`, which **does** have first-class typed period boundaries: `abstract type ExposurePeriod`, `Anniversary(::DatePeriod)`, `Calendar(::DatePeriod)`, `AnniversaryCalendar{T,U}`, with explicit leap-day handling for Feb-29 issue dates.

**Heavylight** — Pure integer `t` only. `RunModel` is literally `for t in range(proj_len)`. No date, calendar, or day-count concept anywhere in the core.

**modelx** — Graph engine, not actuarial DSL. No opinion on dates. Lifelib (built on modelx) shows what that means in practice — the model author owns date semantics entirely.

**pyliferisk / R lifecontingencies** — Both pure integer years/ages. No dates, no day counts, no business days.

**Cross-cutting observations:**
- **Universal pattern:** integer time index `t` (months or years) is the lingua franca; everyone defaults to it.
- **Universally absent:** a typed `Schedule` object that owns frequency + roll convention + anchor date + day-count, the way QuantLib does. Nobody offers `Schedule.from_anniversary(issue_date, "1M", count=360)` returning a typed sequence.
- **Day-count pattern:** when needed, every framework either delegates (lifelib → QuantLib; JuliaActuary → DayCounts.jl) or omits it. Nobody bundles it.
- **Anniversary vs calendar tension is real:** lifelib's `BasicTermASL_ME` re-implements the same `last_part / next_part / next_anniversary` machinery that ExperienceAnalysis encodes once as `AnniversaryCalendar`. Duplicated logic across the OSS landscape.
- **Leap-year handling:** only `ExperienceAnalysis.jl` treats it as a first-class concern, with a documented arithmetic bug ([#18](https://github.com/JuliaActuary/ExperienceAnalysis.jl/issues/18)) that demonstrates how subtle this gets.

**Closest comparator:** `ExperienceAnalysis.jl` is the closest thing to QuantLib-grade typed schedules in the actuarial OSS world — typed period boundaries, leap-day handling, anniversary/calendar split semantics, and an issue tracker showing it's been hardened against real edge cases. Limitations: scope is exposure analysis only (not projection schedules); no day-count abstraction (delegated to DayCounts.jl); no business-day calendar (delegated to BusinessDays.jl); no roll conventions. The Julia ecosystem's answer is **composition of three small packages** (`Dates` + `DayCounts.jl` + `BusinessDays.jl`) rather than a unified `Schedule`.

**The genuine gap:** no OSS actuarial framework unifies QuantLib-grade `DayCount` and `BusinessDayConvention` with actuarial `Anniversary` / `Calendar` / `AnniversaryCalendar` boundaries. This is what gaspatchio's typed Schedule fills.

### Agent C — Jurisdictional conventions

**US (NAIC VM-20, VM-21).** The Valuation Manual is **deliberately silent on day-count**. VM-20 defines "projection interval" as "the time interval used in the cash-flow model to project the cash-flow amounts (e.g., monthly, quarterly, annually)" with no required time step; the AAA practice note confirms actuaries "commonly use monthly, quarterly, or annual time steps." Net premium reserve interest rates are quoted as annual rates rounded to the nearest one-quarter percent — discounting mechanics (Act/365 vs 30/360, mid-period vs end-period) are entity choice, governed by ASOP 52 reasonableness. **In practice, US life models overwhelmingly use monthly time steps with calendar month-end anchoring and a constant 1/12 year fraction for interest accumulation.**

**UK / EU (Solvency II).** EIOPA publishes the RFR as a tabular term structure of **annually compounded zero-coupon spot rates indexed by integer year maturities** (1y, 2y, …, 150y), reconstructed via Smith-Wilson. The Delegated Regulation does not mandate a day-count for cash-flow projection. Practice is to project monthly or quarterly with a **1/12 year fraction** and discount by `(1 + s_t)^(-t)` where `t` is in fractional years; interpolation of integer-year spots to fractional `t` is typically log-linear on discount factors. Calendar month-end is the dominant anchor.

**IFRS 17 (§B72-B85).** **Principles-based and silent on day-count.** B72-B85 require discount rates that "reflect the time value of money, the characteristics of the cash flows and the liquidity characteristics of the insurance contracts" but do not specify Act/365 vs 30/360, nor whether discounting is continuous, annually compounded, or monthly compounded. De facto practice mirrors local statutory conventions.

**Industry papers from large actuarial consultancies.** None publish a single mandated convention. Consistent message: **time step matters more than day-count**; monthly is the de facto production default for life and annuity; daily is rare except for short-term GMxB hedge replication or unit-linked fund accounting; quarterly/annual remains common for legacy traditional blocks.

**De facto defaults (right ~80% of the time for life insurance):**
- Time step: monthly, anchored to **calendar month-end** (not policy anniversary)
- Year fraction: constant **1/12 per month** (ignore varying month length)
- Day-count for sub-annual interpolation when needed: **Act/365 fixed**
- Annual rates: **annually compounded**
- No weekend / business-day adjustment for premium-due, lapse, or death

**Practitioner gotchas:**
1. **Leap-year crossings** — mixing `t = (date - val_date) / 365.25` for one block and `t = months/12` for another causes NPV reconciliation drift of 5-15 bps over 30-year projections.
2. **Anniversary vs calendar-month-end conflation** — UL crediting and term renewal use policy anniversary; reserves/IFRS 17 use calendar month-end. Most production models maintain *both* clocks and reconcile at month-end.
3. **Partial periods at issue and termination** — the single largest source of reconciliation noise across major vendor platforms, each of which handles the issue/termination stub differently.
4. **EIOPA curve interpolation below 1y** — entity choice; can shift BEL by basis points.
5. **30/360 in asset side, Act/365 in liability side** — recurring audit finding when the asset/liability boundary is crossed without explicit conversion.

### Agent D — GSP-92 VA pain probe

**Current state of the spec:** structurally **integer-period only**. `t` is `0..n_periods`, anniversary firing is a precomputed boolean `anniversary_mask`, lapse zeroes remaining periods, `dt` is implicit (assumed 1/12). No `Schedule`, no calendar, no day-count.

**Seven gotchas a real Schedule would have to handle:**

1. **Per-policy anchoring vs shared grid.** Inception 2024-03-15 (pol A) and 2024-08-22 (pol B) on a shared monthly grid means `anniversary_mask[t=12]` is true for A but t=17 for B — anniversary becomes a per-row event. With per-policy grids the kernel runs `n_policies` independent calendars; cross-policy aggregation requires re-bucketing onto a common reporting calendar.

2. **Leap-day anniversaries.** Inception 2020-02-29 → anniversary in 2021 is 2021-02-28 or 2021-03-01? Both are defensible and produce different payouts. 1200-period (100yr) projections cross 24 leap years.

3. **Weekend / holiday roll.** Anniversary 2025-03-15 falls on a Saturday. Modified-following pushes it to 2025-03-17, which moves the ratchet read of `rf["fund"].at("after_growth")` to a different fund value (different two days of returns).

4. **Mid-period events vs declared points.** The §4.9 model has 4 points (`bop`, `after_growth`, `after_payment`, `eop`) but they are *structural*, not dated. A premium-due-on-monthiversary that arrives day 17 of a calendar-anchored month has no place to live — must either be conventionally collapsed to a point or force sub-period state (deferred to Phase 3).

5. **Day-count in `grow(rate)`.** Spec uses `s *= 1 + rate[t]`; there is no `dt`. Months Feb (28d) and Aug (31d) get the same growth factor. For GSP-92 reconciliation against an Excel gold file this is fine *only if Excel did the same thing*. For IFRS 17 OCI parallelism (locked-in vs current curve discounting identical cashflows) any `dt` asymmetry between curves produces spurious OCI.

6. **Mid-period termination.** `lapse_when_all_non_positive` zeroes states for remaining periods *after a full period advance*. If AV exhausts day 8 of month 47, the kernel still applied a full month of growth, full payment, full charges. There is no partial-`dt` mechanic.

7. **Period-360 horizon.** For inception 2024-03-15 monthly × 360, period 360 EOP is 2054-03-15 under "fixed-monthiversary" anchoring vs 2054-02-28/29 under "calendar-month-end" anchoring. The two differ by up to 16 days of accrual on the final cashflow.

**Schedule API requirements (from Agent D):**
1. Per-row inception date column propagated into the IR
2. Typed `dt[t]` series consumed by `.grow` / discount transitions (not constant 1/12)
3. Declarative anniversary-mask constructor (rule + roll convention) instead of pre-computed boolean
4. Day-count convention as a Schedule attribute, fingerprinted into `spec_fingerprint()` so two curves discounting the same cashflows under different conventions are distinguishable
5. Partial-period `dt` for the lapse / contract-boundary stopping period
6. Join semantic between per-policy schedules and a reporting calendar grid

**Demote-to-MVP escape hatch (if Schedule design risk is too high):** keep the existing integer-`t` IR; require the actuary to pre-compute `anniversary_mask`, `dt` (default 1/12), and any per-policy date column *upstream* of `rollforward(...)`. Add a single `dt=` kwarg on `.grow(rate, dt=...)` that defaults to 1.0. Lock down "lapse zeroes the *full* terminating period" as a documented contract.

---

## Synthesis — what gaspatchio is uniquely placed to do

Three convergent observations from the four agents:

1. **The QuantLib surface is small.** The minimum useful public API is ~10 Calendar methods, 1 DayCount method (year_fraction), eager-vector Schedule, and 4 BusinessDayConventions. A first-class actuarial typed Schedule is *not* a wholesale clone of QuantLib — it's a focused subset.

2. **Actuarial OSS has converged on integer-`t` and delegates day-count when needed.** Nobody unifies typed Schedule with day-count. `ExperienceAnalysis.jl` is the closest typed-period comparator but is scope-limited to exposure analysis. JuliaActuary's `FinanceModels.jl#155` is an open admission that dates aren't supported.

3. **The actuarial default is the OneTwelfth simplification.** US/UK/EU production life insurance overwhelmingly runs monthly + calendar-month-end + constant-1/12 + no business-day adjustment. This is *not* a QuantLib convention — it's an actuarial reality. Phase 1's typed Schedule must default to OneTwelfth + NullCalendar to match production practice.

The gap gaspatchio fills is the **unification of QuantLib-grade DayCount and Calendar with actuarial Anniversary semantics, with the OneTwelfth simplification as the default convention.** No other OSS actuarial framework does this. It is genuinely SOTA.

---

## Verdict

**Phase 1 typed Schedule LANDS CLEAN.**

The design surface is small, the conventions are clear, the production defaults are documented, and the MVP fallback (per Agent D) is defined precisely if needed. There is no need to demote — the typed surface is tractable.

---

## Phase 1 design commitments

### Day-count conventions to support (5)

| Convention | Use | Default? |
|---|---|---|
| `OneTwelfth` | Constant 1/12 per month, ignore calendar | **Yes — default** |
| `Actual365Fixed` | UK / sterling, EIOPA-aligned practice; sub-annual interpolation | No |
| `Actual360` | USD money-market, asset-side curves | No |
| `Thirty360` (BondBasis) | Legacy bond / mortgage assets | No |
| `ActualActualISDA` | IFRS 17 / general; precise leap-year handling | No |

### Calendars to support (4)

| Calendar | Use | Default? |
|---|---|---|
| `NullCalendar` | Every day is a business day; matches VM-20/VM-21 / IFRS 17 production practice | **Yes — default** |
| `TARGET` | Eurozone (ECB) settlement; SII reporting cycles | No |
| `UnitedKingdom` | UK PRA reporting | No |
| `UnitedStates` | US calendar for asset side | No |

`JointCalendar(c1, c2)` and `BespokeCalendar` (user-defined holidays) available as escape hatches but not in the curated set.

### Business-day conventions to support (4)

`Following`, `ModifiedFollowing`, `Preceding`, `Unadjusted`. Default: **Unadjusted** (matches the actuarial reality that no one adjusts for weekends in life-insurance projection).

### Schedule construction patterns

Two named constructors covering the per-policy vs shared-grid distinction:

- `Schedule.from_inception(inception_date, n_periods, frequency, calendar, convention, day_count)` — anchors on a per-policy column. Each row gets its own monthly schedule. Anniversary semantics are intrinsic.
- `Schedule.from_calendar_grid(start_date, n_periods, frequency, calendar, convention, day_count)` — shared grid for all policies. Anniversary becomes a derived per-row mask. Useful for cohort-aggregated reserving / SII reporting.

Both fingerprintable. Both consumed by `rollforward(states=, schedule=)`.

### Composition with rollforward

- `Schedule` holds `Calendar`. `DayCount` is held by the Schedule too (deviating from QuantLib's pattern but matching actuarial intuition — the day-count is part of the period semantics).
- Rollforward kernel reads `dt[t]` from the Schedule and applies to `.grow(rate)` as `s *= 1 + rate[t] * dt[t]`. With `OneTwelfth` default, `dt[t] = 1/12` for all `t` — backward-compatible with v1 spec's implicit 1/12.
- Anniversary masks are derivable: `schedule.anniversary_mask(rule="modified_following")` returns the per-period boolean. Replaces v1's pre-computed `af.anniversary_mask`.

### Open design questions resolved

- **Leap-year handling.** `Date(2020, 2, 29) + 1 year = Date(2021, 2, 28)` (canonical actuarial convention). Documented; tested explicitly.
- **Anniversary roll convention default.** Modified-Following when a calendar other than `NullCalendar` is supplied; Unadjusted otherwise.
- **Partial-period `dt` at termination.** Phase 1 does not support; lapse/contract-boundary always advances a full period and zeroes states. Add to §13.2 / Phase 2 follow-up if customers need it. Locked as a documented contract per Agent D's MVP recommendation.
- **Per-policy vs shared grid.** Both supported via the two constructors. `from_inception` is per-policy; `from_calendar_grid` is shared. Models pick the one that matches their reserving convention.

### Fingerprinting

`Schedule`'s canonical form contains: constructor type (`from_inception` vs `from_calendar_grid`), inception/start date column reference, n_periods, frequency, calendar name, convention, day_count name. All hash into `spec_fingerprint`. Two specs differing only in day-count convention have different fingerprints — by design (per the GSP-92 pain probe finding 5).

### Out of scope for Phase 1

- Sub-period state (deferred to Phase 3 per v1 §4.14)
- Partial-period `dt` at termination (deferred to Phase 2)
- Stub period handling beyond `Backward` rule (deferred — most life insurance models don't have stubs)
- Calendar arithmetic on non-business-day inputs beyond the 4 supported conventions
- Holiday-aware premium-due dates (out-of-scope: premium dates aggregate to monthly in production)

---

## Implications for the v2 spec

**§4.x Schedule section:** writeable as designed (not a placeholder).

**§3 IR field for `schedule`:** add to the (states, points, transitions, batch_axes, schedule) tuple. Optional; defaults to `Schedule.integer_periods(n_periods, OneTwelfth)` for products that don't need calendar discipline.

**§4.4 Whole Life worked example:** introduces `Schedule.from_calendar_grid(start, 240, "1M", calendar=NullCalendar, day_count=OneTwelfth)`. First place actuaries see the pattern.

**§4.7 / §4.9 VA examples:** switch from `af.anniversary_mask` (pre-computed) to `schedule.anniversary_mask()` (derived from typed Schedule). Net code is shorter and less audit-fragile.

**§7 kernel:** `dt[t]` is materialised once per row as a Polars column when the Schedule is constructed; `.grow(rate)` reads it. No new plugin work.

**§9.1 canonical form:** add Schedule fingerprint contribution.

**§13.1 Phase 1 commitments:** include 5 day-counts × 4 calendars × 4 BD conventions = ~13 typed objects. All testable against published reference values (QuantLib's day-count tests are public).

---

## Files referenced

- `ref/36-rollforward-redesign/specs/2026-04-30-rollforward-redesign-design.md` — v1 spec (now superseded)
- `ref/30-llm-helpers/recursive-accumulation-gap.md` — original GSP-86 gap analysis
- `bindings/python/gaspatchio_core/tutorials/level-3-mini-va/base/model.py` — confirms current integer-`t` shape

## Citations

- QuantLib reference: https://www.quantlib.org/reference/ (`Calendar`, `DayCounter`, `Schedule`, `BusinessDayConvention`)
- JuliaActuary FAQ on dates: https://github.com/JuliaActuary/FinanceCore.jl
- `FinanceModels.jl#155 — Allow handling of Dates`: https://github.com/JuliaActuary/FinanceModels.jl/issues/155
- `ExperienceAnalysis.jl#18 — leap-year arithmetic bug`: https://github.com/JuliaActuary/ExperienceAnalysis.jl/issues/18
- `ExperienceAnalysis.jl#17 — deaths on policy anniversary`: https://github.com/JuliaActuary/ExperienceAnalysis.jl/issues/17
- NAIC Valuation Manual (current edition): https://content.naic.org/sites/default/files/pbr_data_valuation_manual_current_edition.pdf
- AAA VM-20 Practice Note 2020: https://www.actuary.org/sites/default/files/2020-04/VM-20_PN_2020_Version_0.pdf
- AAA VM-21 Practice Note Supplement 2022: https://actuary.org/wp-content/uploads/2022/02/VA_PN_Supplement_Final.pdf
- EIOPA RFR Technical Documentation (Oct 2025): https://www.eiopa.europa.eu/system/files/2025-10/EIOPA-BoS-25-471-RFR%20Technical%20Documentation-October-2025.pdf
- IFRS 17 standard (§B72-B85): https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2022/issued/part-a/ifrs-17-insurance-contracts.pdf
- ACT Learning: Day count conventions: https://learning.treasurers.org/how-to-apply-day-count-conventions
