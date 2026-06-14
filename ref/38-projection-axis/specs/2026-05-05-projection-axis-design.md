# Projection Axis API Unification — Design

**Date:** 2026-05-05
**Status:** Design proposal (awaiting plan)
**Authors:** Matt Wright, Claude
**Branch:** `gsp-92-rollforward-redesign` (continuation)
**Supersedes (on landing):** `af.date.create_projection_timeline(...)` and direct user-facing use of `Schedule.from_*(...)` constructors as the day-to-day projection setup verb.

**Defers (separate Linear tickets):**
- GSP-97 — Native per-policy `n_periods` in the rollforward kernel
- GSP-98 — Mid-period termination semantics

---

## 1. What this is

**One verb on the frame for setting up the projection time axis.**

Today an actuary chooses between two parallel primitives that produce per-policy time axes — `af.date.create_projection_timeline(...)` and `Schedule.from_inception(...)` / `Schedule.from_calendar_grid(...)`. They differ in layer (frame accessor vs typed input), end-time vocabulary, frequency strings, lengths (`N+1` vs `N`), and mutation semantics. The off-by-one alignment trap between them is documented as a known footgun in the typed-input tutorial README.

This refactor unifies them into one user-facing surface — `af.projection.set(...)` — which both the actuary and the rollforward kernel read from. `Schedule` stays public as the typed-input object; `set(...)` accepts either a kwargs path or a pre-built `Schedule`. `create_projection_timeline` is deleted with no shim.

**Pre-release breaking-change posture.** No deprecation warnings, no compatibility layer, no transitional period. The `migration.md` companion shows the rewrite for every tutorial model in the repo.

---

## 2. Design principles applied

The principles below come directly from `core/project.md`. Each is referenced in the design choices that follow.

| # | Principle | Where applied |
|---|-----------|---------------|
| 1 | Lead with the actuarial problem being solved, not the computer science architecture | §3 — "set the projection" reads as the actuary's verb, not "construct a Schedule object" |
| 2 | Names match what an actuary would say — and what an LLM would search for | §3 — `until="maximum_age"`, `frequency="monthly"`, `t_years()`, `is_in_force()` |
| 3 | The Python API reads like the formula | §6 — explicit `contract_boundary=pl.col("contract_boundary")` (materialized from `af.projection.contract_boundary()`) over silent-default magic |
| 4 | Pre-compute what you can in Python; only state-dependent work runs in the kernel | §5 — eager stamp the three scalar columns; lazy-compute the per-period vectors |
| 5 | The spec IS the model | §5 — `af.projection.canonical_form()` and `source_sha()` produce identical bytes whether the projection was built via kwargs or via `schedule=` |

**Pre-release breaking change is fine.** This is the same posture as `ref/36-rollforward-redesign/`: the existing `create_projection_timeline` is *the wrong shape*, not "the legacy shape". Preserving it would compound the inconsistency between layers.

---

## 3. API surface

### 3.1 The verb

```python
import datetime as dt
import polars as pl
from gaspatchio_core import ActuarialFrame

af = ActuarialFrame({
    "policy_id":  ["P001", "P002", "P003"],
    "issue_age":  [30, 45, 60],
    "av_init":    [100_000.0, 250_000.0, 50_000.0],
})

af = af.projection.set(
    valuation_date=dt.date(2025, 1, 1),
    until="maximum_age",
    until_value=100,
    frequency="monthly",
)
```

Two equivalent paths converge inside the accessor:

**Path A — kwargs (lower barrier; tutorials lead with this)**

```python
af = af.projection.set(
    valuation_date=dt.date(2025, 1, 1),
    until="maximum_age",
    until_value=100,
    frequency="monthly",
)
```

**Path B — typed Schedule (sharing across frames; audit anchor; testing fixtures)**

```python
from gaspatchio_core import Schedule

sched = Schedule.from_calendar_grid(
    start_date=dt.date(2025, 12, 31),
    n_periods=240,
    frequency="1M",
)
af_term = af_term.projection.set(schedule=sched)
af_ann  = af_ann.projection.set(schedule=sched)
```

Internally, the kwargs path constructs a Schedule, then both paths converge on the same internal state. `canonical_form()` and `source_sha()` produce identical bytes for equivalent inputs regardless of which path was used.

### 3.2 The `until=` vocabulary

| `until=` value | Meaning | `until_value=` shape |
|---|---|---|
| `"maximum_age"` | Project until each policy reaches target age | `int` (uniform) or `str` (column name) or `pl.Expr` (per-policy) |
| `"term_years"` | Project for N years from valuation | `int` or `str` or `pl.Expr` |
| `"term_months"` | Project for N months from valuation | `int` or `str` or `pl.Expr` |
| `"fixed_date"` | Project to specific calendar date | `dt.date` only (uniform — fixed_date is inherently shared) |
| `"next_anniversary"` | Project until the Nth contract anniversary on/after `valuation_date` | `int` (default 1) or `str` or `pl.Expr` |

`"next_anniversary"` is anchored on each policy's inception date, default column `"policy_inception"` (configurable via `inception_column=` kwarg). `until_value=1` projects to the next anniversary; `until_value=N` for N > 1 projects to the Nth anniversary after that. Useful for term-renewable life, anniversary-trigger riders, group renewable products.

### 3.3 The `frequency=` vocabulary

Two parallel surfaces, both accepted, with one canonical internal form:

**Documented primary surface (used by tutorials, concept docs, docstring examples):**

| Value | Meaning |
|---|---|
| `"monthly"` | 1-month periods |
| `"quarterly"` | 3-month periods |
| `"semi-annual"` | 6-month periods |
| `"annual"` | 1-year periods |
| `"weekly"` | 1-week periods (rare; capital-markets adjacent) |
| `"daily"` | 1-day periods (rare; testing) |

**Schedule-compatible shorthand (accepted; mentioned in API reference only):**

| Value | Equivalent to |
|---|---|
| `"1M"` | `"monthly"` |
| `"3M"` | `"quarterly"` |
| `"6M"` | `"semi-annual"` |
| `"1Y"` | `"annual"` |
| `"1W"` | `"weekly"` |
| `"1D"` | `"daily"` |

The shorthand exists to keep parity with `Schedule.from_*(frequency="1M")` so users mid-migration don't have to translate. Concept pages and tutorial code use the English form throughout. The internal canonical form is the Schedule string (so `source_sha()` is stable across both paths).

**Why both:** prior art is mixed — QuantLib has two parallel types (`Frequency` enum and `Period` strings), pandas had a deprecation cycle on `"M"` → `"ME"`, JuliaActuary uses integers. This spec accepts a pragmatic two-vocabulary surface but documents only one. No third syntax (no integer `frequency=4`, no Polars `"1mo"`).

### 3.4 The synthetic case

For pattern-demo tutorials that have no policy data — the `tutorial/rollforward-patterns/` family:

```python
af = ActuarialFrame({"id": ["demo"]})
af = af.projection.set(
    start_date=dt.date(2025, 1, 31),
    n_periods=10,
    frequency="monthly",
)
```

Same verb, different kwargs. The actuary doesn't have to learn that one path is `from_inception` and the other is `from_calendar_grid` — they're saying "set up the time axis" in both cases.

### 3.5 Mutual exclusion

`schedule=` is mutually exclusive with the kwargs path. Passing both raises:

```
ValueError: schedule= cannot be combined with valuation_date / until / start_date / n_periods.
Pass either a Schedule object OR construction kwargs, not both.
```

### 3.6 Frame mutation semantics

`af.projection.set(...)` **returns a new frame**. The actuary rebinds:

```python
af = af.projection.set(...)   # rebinding required
```

Polars convention. The current `create_projection_timeline` mutates in place — that's the only frame method that does, and is the wart we're fixing.

---

## 4. Frame state after `set()`

### 4.1 Eagerly stamped columns

Three columns are added to the frame on `set()`, visible in `af.collect()`:

| Column | Type | Why eager |
|---|---|---|
| `projection_start_date` | `Date` | Scalar per row. Tiny. Used in 90% of debug sessions. |
| `projection_end_date` | `Date` | Scalar per row. Same. |
| `num_proj_months` | `Int64` | Scalar per row. Used in length checks, sanity prints, contract boundary derivation. |

These three names are kept identical to today's `create_projection_timeline` output for migration ergonomics.

The big list-shaped quantities (`period_dates`, `year_fractions`, `is_in_force`) stay lazy — they would otherwise bloat the frame width by `n_periods × 4-byte float × n_policies` for any column the actuary doesn't end up reading.

### 4.2 Lazy accessor methods

Computed on read; produce `ExpressionProxy` (so they participate in Polars' lazy graph and never go stale):

| Method | Returns | Use |
|---|---|---|
| `af.projection.period_dates()` | `List<Date>` (length `n_periods + 1`) | Cashflow date alignment |
| `af.projection.year_fractions()` | `List<Float64>` (length `n_periods`) | Per-period dt[t] for Curve / mortality / fees |
| `af.projection.t_years()` | `List<Float64>` (length `n_periods + 1`) | Cumulative year-fractions; feeds `Curve.discount_factor(t)` directly |
| `af.projection.anniversary_mask()` | `List<Boolean>` (length `n_periods`) | Ratchet timing, anniversary commissions |
| `af.projection.is_in_force()` | `List<Boolean>` (length `n_periods`) | Active-policy mask (True = in force); for the rollforward boundary use `contract_boundary()` instead |
| `af.projection.contract_boundary()` | `List<Boolean>` (length `n_periods`) | Per-policy boundary mask consumed by rollforward as `contract_boundary=` (True = terminated; the negation of `is_in_force()`) |

Naming choices:
- `t_years()` — matches the variable name actuaries actually use (`t_years` in the typed VA tutorial, in concept docs, in industry papers). Shorter than `cumulative_year_fractions()` and unambiguous.
- `is_in_force()` — actuarial reading. `contract_boundary` is the rollforward's *parameter* name; `is_in_force` is what the *thing* is.

### 4.3 Governance hooks

Return Python values, not Polars expressions:

| Method | Returns | Use |
|---|---|---|
| `af.projection.canonical_form()` | `dict[str, Any]` | Structural recipe — same shape as `Schedule.canonical_form()` today |
| `af.projection.source_sha()` | `str` (`"sha256:<hex>"`) | Audit identifier; identical bytes whether projection was built via kwargs or via `schedule=` |

These mirror Schedule's existing governance methods. The audit chain is unbroken — `CompiledRollforward.fingerprint()` reads `af.projection.source_sha()` for the time-axis component of its identity, matching what it currently reads from `Schedule.source_sha()`.

### 4.4 Internal state

`ActuarialFrame` gains a private slot `_projection: Schedule | None`. The accessor stores the underlying Schedule there. Both API paths converge on this single anchor. From it, every derived expression is computed.

The slot is preserved through frame operations that don't change the time axis (e.g., `with_columns(...)`, `filter(...)`). It is cleared only on operations that conceptually invalidate it (e.g., `join(...)` with a frame that has different policies — TBD in detailed design; default is conservative-clear).

### 4.5 Re-call behaviour

Calling `set()` on a frame that already has projection metadata **replaces** the previous projection. Returns a new frame; old metadata is gone. Documented behaviour, not an error — actuaries iterating in a notebook or running scenario sweeps want this. No warning is emitted.

### 4.6 Staleness contract

The eagerly-stamped columns reflect the projection at the moment `set()` was called. If the actuary then mutates an upstream column (e.g., `with_columns(issue_age=...)` after `set(until="maximum_age")`), the stamps **do not auto-refresh**.

Documented as: "call `set()` after any mutation that affects the time axis."

Lazy methods always recompute from current frame state, so they are never stale.

This is a deliberate trade-off:
- **Auto-refresh** would require dependency tracking from the projection metadata to upstream columns — significant infrastructure for a rare scenario.
- **Forbid mutation post-set** would limit the API in ways that cut against Polars patterns.
- **Document and make easy to refresh** keeps the API simple; the recovery is a single `af = af.projection.set(...)` call.

---

## 5. Rollforward integration

The rollforward kernel reads projection metadata from the frame. The `schedule=` kwarg on `rollforward()` is removed.

### 5.1 The pattern

**Before:**
```python
sched = Schedule.from_inception(inception_column="policy_inception", n_periods=240, frequency="1M")
b = af.projection.rollforward(
    states={"av": pl.col("av_init")},
    schedule=sched,
    contract_boundary=in_force_mask_expr,  # built manually
)
```

**After:**
```python
af = af.projection.set(
    valuation_date=dt.date(2025, 1, 1),
    until="maximum_age",
    until_value=100,
    frequency="monthly",
)
af.contract_boundary = af.projection.contract_boundary()  # materialize as column
b = af.projection.rollforward(
    states={"av": pl.col("av_init")},
    contract_boundary=pl.col("contract_boundary"),
)
```

### 5.2 Specifics

1. **`schedule=` removed from `rollforward()`.** Passing it raises a `TypeError` with a migration message:
   ```
   schedule= is no longer accepted on rollforward().
   Call af.projection.set(...) before rollforward(); the schedule is read from the frame.
   ```

2. **`contract_boundary=` stays explicit.** No silent default. The actuary materializes the boundary mask as a column on the frame and passes a column reference into the rollforward call at every site that needs boundary handling:

   ```python
   af.contract_boundary = af.projection.contract_boundary()
   b = af.projection.rollforward(
       states={"av": pl.col("av_init")},
       contract_boundary=pl.col("contract_boundary"),
   )
   ```

   Reasoning:
   - Reading the rollforward call top-to-bottom shows what bounds the projection
   - Auditor / reviewer answers "what bounds this?" by reading the call, not by grepping upstream
   - Newcomer can `Cmd-click` on `contract_boundary()` and learn what it is
   - The accessor and the kwarg share the same name and the same semantics (True = terminate); `is_in_force()` (True = active) remains available for non-kernel uses such as expected lives in-force or exposure aggregation

   **Constraint:** `contract_boundary=` accepts a column reference (`pl.col("name")`), not a list-literal expression. To use `af.projection.contract_boundary()` (which returns an expression), assign it to a column first: `af.contract_boundary = af.projection.contract_boundary()`, then pass `pl.col("contract_boundary")` to the rollforward call. This is the kernel's IR contract — the boundary needs a single column slot, not a re-evaluated expression.

3. **Calling `rollforward()` without prior `set()` and without explicit `schedule=`** raises:
   ```
   This frame has no projection. Call af.projection.set(...) before rollforward().
   ```

4. **Internal wiring.** `RollforwardBuilder` reads the frame's `_projection` directly. The IR still holds a `Schedule` field — that doesn't change. Only the user-facing kwarg disappears.

5. **Audit chain.** `af.projection.canonical_form()` is what `CompiledRollforward.fingerprint()` reads for the time-axis component. Same SHA as Schedule produced before. The migration does not change the fingerprint of any model whose recipe is unchanged.

### 5.3 What this buys

- One declaration per frame; rollforward, derived columns, and any future projection-aware verb all read from the same anchor
- The actuary's mental model: "set the projection, then everything that needs it picks it up" — no threading the same Schedule through multiple call sites
- Eliminates the off-by-one alignment bug (`PROJECTION_MONTHS + 1` from the typed-input tutorial README) — only one place defines `n_periods`
- Audit story strengthens: one canonical form per frame, accessible from both the rollforward fingerprint and `af.projection.source_sha()`

---

## 6. Migration scope

### 6.1 Breaking changes

| Surface | Old | New |
|---|---|---|
| Projection setup verb | `af.date.create_projection_timeline(valuation_date=..., projection_end_type="maximum_age", projection_end_value=100, projection_frequency="monthly")` | `af.projection.set(valuation_date=..., until="maximum_age", until_value=100, frequency="monthly")` |
| Frame mutation | mutates in place, returns same `af` | returns new frame; rebind required |
| Output column for proj dates | `proj_dates` (eagerly stamped) | `af.projection.period_dates()` (lazy ExpressionProxy) |
| Rollforward `schedule=` | `rollforward(states={...}, schedule=Schedule.from_inception(...))` | `af = af.projection.set(...)`; assign `af.contract_boundary = af.projection.contract_boundary()`; then `rollforward(states={...}, contract_boundary=pl.col("contract_boundary"))` |
| Frequency strings | `"monthly"`, `"quarterly"`, `"semi-annual"`, `"annual"` only | `"monthly"`-family OR `"1M"`-family (both accepted) |
| Schedule construction | unchanged | unchanged |

### 6.2 What does NOT change

- `Schedule`, `Calendar`, `DayCount`, `BusinessDayConvention` — all stay public, all stay at top-level `from gaspatchio_core import ...`
- `af.date.create_timeline(start_col, end_col, freq, ...)` — different verb, different purpose, untouched
- `af.date.add_duration(...)` — untouched
- `af.<col>.projection.accumulate(...)` — separate primitive backed by `accumulate.rs`, untouched
- `af.<col>.projection.cumulative_survival(...)`, `previous_period(...)`, `next_period(...)`, `at_period(...)` — column-level accessors untouched

### 6.3 Removed entirely

- `af.date.create_projection_timeline(...)` — deleted, no shim. Pre-release status; clean break.

### 6.4 Migration scope

**Source code** (in `bindings/python/gaspatchio_core/`):
1. `accessors/projection_frame.py` — add `set()` method, modify `rollforward()` to read from frame, drop `schedule=`
2. `accessors/date.py` — delete `create_projection_timeline`
3. `rollforward/_builder.py` — drop `schedule=` parameter, read from frame
4. `frame/base.py` — add `_projection` slot to `ActuarialFrame`; preserve through frame operations
5. `schedule/_schedule.py` — add `next_anniversary_date()` helper; add `is_in_force_expr()` method
6. `*.pyi` stubs — update accessor signatures

**Tutorials** (in `tutorial/`):
7. `level-1-hello-world/` — spot-check (likely no projection usage)
8. `level-2-assumptions/` — spot-check
9. `level-3-mini-va/` — uses `create_projection_timeline`; rewrite
10. `level-3-mini-va-typed/` — uses `Schedule.from_inception(...)` directly; rewrite to demonstrate `af.projection.set(schedule=sched)` (the `from_inception` constructor stays — just routed through the new verb)
11. `level-4-lifelib/` — check + rewrite
12. `level-5-scenarios/` — uses `create_projection_timeline`; rewrite
13. `level-5-scenarios-typed/` — uses Schedule; rewrite
14. `rollforward-patterns/` — synthetic projection; rewrite to `af.projection.set(start_date=..., n_periods=..., frequency=...)`

**Tests:**
15. `bindings/python/tests/` — every test that builds a Schedule for rollforward needs migration applied; estimate ~20-40 test files

**Documentation** (gaspatchio-docs):
16. `concepts/schedules.md` — rewrite to lead with `af.projection.set(...)`; position Schedule as "the audit-anchor object that backs `af.projection`"
17. `concepts/rollforward/*.md` — examples drop `schedule=`; materialize `af.contract_boundary = af.projection.contract_boundary()` and pass `contract_boundary=pl.col("contract_boundary")`
18. `concepts/calculations.md` — examples updated
19. `api/rollforward.md` — signature change auto-reflects via mkdocstrings
20. `api/schedule.md` — tone shift; Schedule positioned as audit anchor

**Migration companion document:**
21. `ref/38-projection-axis/migration.md` — written from the actual diffs in steps 7-14 and 16-19

### 6.5 What gets simpler downstream

- `level-3-mini-va-typed/README.md` "findings worth reading" section: the off-by-one alignment bullet point disappears entirely
- `level-3-mini-va-typed/` step pages drop the `n_periods = PROJECTION_MONTHS + 1` boilerplate
- Concept pages stop having to explain "Schedule and `create_projection_timeline` are different things"

---

## 7. Implementation order

Each step lands its own commit; tests pass after each.

1. **Schedule extensions** (additive — no breakage yet)
   - Add `next_anniversary_date(valuation_date, n=1)` helper to `Schedule.from_inception`
   - Add `is_in_force_expr()` method that derives the boundary mask from `n_periods` + per-policy `inception_column` + per-policy end conditions
   - Tests for both, no API consumers yet

2. **Add `_projection` slot to `ActuarialFrame`**
   - New private attribute holding `Schedule | None`
   - Plumbed through `_clone_with_df` / equivalent so `with_columns`, `filter`, etc. preserve it
   - Test: round-trip preservation through frame operations

3. **Add `af.projection.set(...)` method on `ProjectionFrameAccessor`**
   - Both paths (kwargs + `schedule=`) converge on storing a Schedule in `af._projection`
   - Stamp the three eager columns (`projection_start_date`, `projection_end_date`, `num_proj_months`)
   - Returns new frame
   - Tests: every `until=` type × per-policy / uniform variants; `schedule=` round-trip; mutual exclusion error; re-call replacement

4. **Add lazy accessor methods on `ProjectionFrameAccessor`**
   - `period_dates()`, `year_fractions()`, `t_years()`, `anniversary_mask()`, `is_in_force()`, `canonical_form()`, `source_sha()`
   - Each delegates to the stored Schedule
   - Tests: each method returns expected shape and content; `source_sha()` matches between kwargs path and `schedule=` path for equivalent inputs

5. **Modify `RollforwardBuilder` to read from frame**
   - Drop `schedule=` parameter; add `TypeError` with migration message if passed
   - Read Schedule from `af._projection`; raise clear error if frame has no projection
   - Tests: every existing rollforward test rewritten to use `af.projection.set(...)` first

6. **Delete `af.date.create_projection_timeline`**
   - Remove method from `DateFrameAccessor`
   - Remove docstring tests
   - No shim — pre-release, clean break

7. **Tutorial migration** (each tutorial its own commit; see §6.4 for the list)

8. **Documentation rewrite** (gaspatchio-docs branch; see §6.4)

9. **Migration doc**
   - `ref/38-projection-axis/migration.md` written from the actual diffs in steps 7-8

---

## 8. Testing strategy

### 8.1 Unit tests

Every new method on `ProjectionFrameAccessor` and `Schedule` gets coverage for:
- Happy path with each input shape (uniform / per-policy / Schedule object)
- Each error branch (mutual exclusion, missing projection, invalid kwargs)

### 8.2 Integration tests

Every existing rollforward test gets rewritten as part of step 5 in §7. This is the regression gate — if any rewritten test produces a different number than the pre-migration version, that is a bug to investigate, not a tolerance to accept.

### 8.3 VA reconciliation

The existing reconcile script (`bindings/python/gaspatchio_core/tutorials/level-3-mini-va-typed/steps/06-reconcile/reconcile.py`) is the headline gate. Numerical agreement to ~1e-9 relative against the untyped baseline must hold before merge.

### 8.4 Source-SHA equivalence

A new test fixture proves `af.projection.source_sha()` produces identical bytes for:
- `af.projection.set(valuation_date=D, until="maximum_age", until_value=100, frequency="monthly")` (kwargs path)
- `af.projection.set(schedule=Schedule.from_inception(inception_column="policy_inception", n_periods=N, frequency="1M"))` for matched parameters (Schedule path)

This locks in the audit-chain promise from §4.3.

### 8.5 Docstring tests

New docstring examples on `af.projection.set(...)` and the lazy methods get the existing `pytest --doctest-modules --doctest-glob="*.pyi"` treatment.

### 8.6 Migration smoke

Pick one tutorial that uses `create_projection_timeline` heavily, copy the pre-migration version into `tests/migration/`, run it, expect a `TypeError` or `AttributeError`. This locks in the breakage so it's audited rather than silent.

---

## 9. Out of scope

The following are deferred to separate Linear tickets, each with its own spec, validation gate, and migration story:

- **GSP-97 — Native per-policy `n_periods` in the rollforward kernel.** Memory optimisation for lapse-heavy portfolios. Kernel-level change with high regression risk. 2-3 weeks. Currently the boundary-mask approach is fine; that approach stays under this spec.

- **GSP-98 — Mid-period termination semantics.** Partial-period `dt` at lapse / contract end. Semantic correctness shift, not additive. Per-regulatory-regime convention research required. 1-2 weeks plus research. Currently full-period only; that semantic stays under this spec.

Both tickets reference back to this spec so the deferral chain is traceable.

---

## 10. Branch strategy

Land on the existing `gsp-92-rollforward-redesign` branch. This is a logical continuation of the typed-input + state-machine work already in flight — same audience, same evergreen-docs posture, same VA reconciliation gate.

---

## 11. Estimated effort

- §7 steps 1-6 (source + tests): ~1 week of focused work
- §7 step 7 (tutorials): ~1-2 days, mostly mechanical
- §7 step 8 (docs): ~1-2 days
- §7 step 9 (migration.md): ~half day, derived from the diffs

**Total: ~2 weeks** for a careful, well-tested landing.

---

## 12. Settled design positions

For traceability, the twelve positions that drove this design:

| # | Position | Resolved in |
|---|---|---|
| 1 | End-type API: kwargs (`until=` / `until_value=`) on a single verb, not named constructors | Last session |
| 2 | Boundary count: `n_periods` for per-period quantities; `n_periods+1` only for `period_dates` (boundaries) | Last session |
| 3 | Per-policy `n_periods` in the kernel: deferred to GSP-97; uniform max + boundary mask under this spec | Last session |
| 4 | Frame mutation: returns new frame (Polars convention) | This session — Q2 |
| 5 | Synthetic case: same verb, different kwargs (`start_date=...` instead of `valuation_date=...`) | Last session |
| 6 | Verb location: `af.projection.set(...)` (extends existing accessor; sits next to `af.projection.rollforward(...)`) | This session — Q1 |
| 7 | Eagerly stamp three scalar columns (`projection_start_date`, `projection_end_date`, `num_proj_months`); lazy-compute the rest | This session — Q3 |
| 8 | Five lazy methods + two governance hooks; names `t_years()` / `is_in_force()` | This session — Q4 |
| 9 | Frequency vocab: English primary (`"monthly"`), Schedule-shorthand secondary (`"1M"`); both accepted; one canonical internal form | This session — Q5 |
| 10 | Rollforward: `schedule=` removed; reads from frame; `contract_boundary=` stays explicit at call site | This session — Q6, revised after Q8 challenge |
| 11 | Schedule stays public; `set(...)` accepts EITHER kwargs OR a pre-built Schedule | This session — Q7 |
| 12 | Anniversary `until="next_anniversary"` pulled into this spec from the deferred list | This session — Q9 |
