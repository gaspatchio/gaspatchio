# Rollforward API Design

## GSP-86: Non-Linear Accumulations via Method-Chain Builder

### Status: Design Review
### Authors: Matt Wright, Claude
### Date: 2026-03-25 (revised)

---

## 1. Problem Statement

GSP-85 delivered `accumulate()` for linear recurrences: `State[t] = State[t-1] × M[t] + A[t]`. This handles products where all inputs are pre-computable — but most real products have **state-dependent charges** where the charge at time *t* depends on the accumulated value at *t*:

- **COI:** `rate[t] × max(0, SA - AV[t])` — net amount at risk changes as AV changes
- **Tiered fees:** fee rate depends on which AV band the policy falls in
- **Dynamic lapse:** lapse rate depends on CSV/guarantee ratio
- **Secondary guarantees:** lapse depends on joint state of AV and shadow account

These cannot be expressed as `State × M + A` because M and A themselves depend on State.

### Constraint

Gaspatchio uses Polars plugins implemented in Rust. The plugin receives `&[Series]` and returns `PolarsResult<Series>`. **No Python callbacks during execution.** All per-timestep logic must be expressible as serializable kwargs that Rust can interpret.

---

## 2. Design Principles

From `core/project.md` and gaspatchio's established patterns:

1. **No Python loops in the hot path** — all time-stepping happens inside Rust
2. **Polars parallelises across policies** — the plugin processes one row at a time, Polars distributes
3. **Pre-compute what you can in Python** — mortality vectors, premium schedules, interest rates
4. **The Python API reads like the formula** — the actuary sees business logic, not implementation
5. **Names match what an actuary would say** — and what an LLM would search for
6. **The spec is the model** — a declarative chain is simultaneously executable AND machine-inspectable data

### The Declarative Advantage

Imperative APIs let the actuary write arbitrary code in a loop. Gaspatchio cannot (Polars plugin constraint). But this constraint enables capabilities that code-based frameworks **structurally cannot offer**:

| Capability | Why declarative enables it | Why imperative can't |
|------------|--------------------------|---------------------|
| **Model fingerprinting** | SHA-256 of canonical JSON for change control | No canonical form for arbitrary code |
| **Single-run AoC** | `track_increments` decomposes by step natively | Requires N+1 model runs for N assumptions |
| **Step composition** | Insert/remove/replace steps as tuple operations | Modifying code requires understanding the full function |
| **Mid-chain assertions** | Validation rules travel with the model | Assertions are separate scripts, disconnected from model logic |
| **Auto-documentation** | The chain IS the specification | Docs drift from code |

> *"Gaspatchio constrains the surface to what an actuary would say — and then proves it's correct."*

---

## 3. API Design

### 3.1 Entry Point: Frame-Level Projection Accessor

The existing `projection` accessor is **column-level** (`af.qx.projection.cumulative_survival()`). The rollforward is a **frame-level** operation — it consumes multiple columns and produces one or more outputs. There is no natural anchor column.

A new `ProjectionFrameAccessor` (registered as `kind="frame"`) provides `af.projection.rollforward()`. This coexists with the column-level `ProjectionColumnAccessor` using the same accessor registry pattern Polars uses for namespaces. The frame-level accessor has a single method (`rollforward`) for now; the column-level accessor retains `cumulative_survival`, `prospective_value`, `accumulate`, etc.

### 3.2 Single-State Rollforward (the 80% case)

```python
af.av = (
    af.projection.rollforward(initial=af.av_init)
    .add(af.premium, "Premium income")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .charge(af.admin_charge_rate, "Monthly admin charge")
    .grow(af.interest_rate, "Interest credit")
    .floor(0, "Non-negative constraint")
)
```

The chain reads top-to-bottom as the within-period calculation order. Each method returns the builder, so they compose naturally. The second argument is an optional label for audit/documentation.

**Entry point:** `af.projection.rollforward(initial=...)` returns a `RollforwardBuilder`. When a single `initial` is passed, the builder operates in single-state mode.

**Terminal:** The builder evaluates lazily. Assignment to `af.av` triggers compilation of the step list into Rust kwargs and registration as a Polars expression.

### 3.3 Multi-State Rollforward (VA riders, secondary guarantees)

When named kwargs are passed instead of `initial`, the builder operates in multi-state mode:

```python
# Style 1: Sticky .on() — terse, groups operations by state visually
rf = (
    af.projection.rollforward(av=af.av_init, guarantee=af.guarantee_init)
    .on("av")
    .add(af.premium)
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured)
    .charge(af.me_rate)
    .grow(af.fund_return)
    .floor(0)
    .on("guarantee")
    .ratchet_to("av")
    .grow(af.roll_up_rate)
    .lapse_when(all_non_positive=["av", "guarantee"])
)

# Style 2: Explicit .on() per step — identical behavior, more defensive
rf = (
    af.projection.rollforward(av=af.av_init, guarantee=af.guarantee_init)
    .on("av").add(af.premium)
    .on("av").deduct_nar(af.coi_rate, death_benefit=af.sum_assured)
    .on("av").charge(af.me_rate)
    .on("av").grow(af.fund_return)
    .on("av").floor(0)
    .on("guarantee").ratchet_to("av")
    .on("guarantee").grow(af.roll_up_rate)
    .lapse_when(all_non_positive=["av", "guarantee"])
)

af.av = rf["av"]
af.guarantee = rf["guarantee"]
```

**`.on(state_name)` is sticky** — it sets the target state for all subsequent steps until another `.on()` changes it. Calling `.on("av")` when already targeting `"av"` is a no-op, so the explicit per-step style works identically.

**Steps execute in declared order across all states** — the guarantee ratchets to the post-growth AV because `.on("av").grow(...)` precedes `.on("guarantee").ratchet_to("av")`.

**Interleaving is natural with sticky `.on()`:**

```python
.on("av").charge(af.rider_fee)
.capture("av_post_charge")                                       # still targeting av
.on("benefit_base").pro_rata_with("av_post_charge", af.withdrawal)
.on("av").grow(af.fund_return)                                   # switch back to av
```

**`.lapse_when(all_non_positive=[...])`** is a cross-state lapse condition. When ALL named states are ≤ 0, all states are zeroed for remaining periods.

**Rust implementation:** Multi-state rollforward returns a Struct column (`StructChunked::from_series()`). Each field is a List<Float64> representing one state's projection.

### 3.4 Cross-State References

For products where one state's step depends on another state's mid-chain value (e.g., GMWB proportional reduction):

```python
rf = (
    af.projection.rollforward(av=af.av_init, benefit_base=af.bb_init)
    .on("av").charge(af.rider_charge_rate)
    .on("av").capture("av_pre_withdrawal")
    .on("av").subtract(af.withdrawal)
    .on("benefit_base").pro_rata_with("av_pre_withdrawal", af.withdrawal)
    .on("av").grow(af.fund_return)
)
```

`.capture(name)` stores the current state value at that point. `.pro_rata_with(ref, amount)` computes `state *= (1 - amount[t] / ref_value)`. Capture names are accessible from any state in the rollforward.

---

## 4. Method Reference

### 4.1 Absolute Operations

| Method | Formula | Use When |
|--------|---------|----------|
| `.add(amount)` | `av += amount[t]` | Premium deposits, bonus additions |
| `.subtract(amount)` | `av -= amount[t]` | Flat dollar fees, withdrawals |

### 4.2 Rate Operations (proportional to current accumulated value)

| Method | Formula | Use When |
|--------|---------|----------|
| `.charge(rate)` | `av *= (1 - rate[t])` | M&E charges, admin fee as % of AV |
| `.grow(rate)` | `av *= (1 + rate[t])` | Interest crediting, fund returns |
| `.grow_capped(rate, *, floor, cap)` | `av *= (1 + clamp(rate[t], floor, cap))` | IUL crediting with floor and cap |

### 4.3 State-Dependent Actuarial Operations

| Method | Formula | Use When |
|--------|---------|----------|
| `.deduct_nar(rate, *, death_benefit)` | `av -= rate[t] × max(0, db[t] - av)` | COI on net amount at risk |
| `.charge_tiered(breakpoints, rates)` | `rate = lookup(av); av *= (1 - rate)` | Tiered management charges |
| `.grow_tiered(breakpoints, rates)` | `rate = lookup(av); av *= (1 + rate)` | Tiered crediting rates |

### 4.4 Bounds

| Method | Formula | Use When |
|--------|---------|----------|
| `.floor(value)` | `av = max(av, value)` | Non-negative AV constraint |
| `.cap(value)` | `av = min(av, value)` | Maximum AV limit |

### 4.5 Cross-State Operations (multi-state only)

| Method | Formula | Use When |
|--------|---------|----------|
| `.ratchet_to(other_state)` | `av = max(av, other.current)` | GMDB high-water mark |
| `.pro_rata_with(capture_ref, amount)` | `av *= (1 - amount[t] / ref_value)` | GMWB proportional reduction |

### 4.6 Control Flow

| Method | Formula | Use When |
|--------|---------|----------|
| `.lapse_if_zero()` | if av ≤ 0: zero remaining | Single-state NF lapse |
| `.lapse_when(all_non_positive=[...])` | if all states ≤ 0: zero remaining | Secondary guarantee lapse |
| `.add_if(condition, amount)` | if condition[t]: av += amount[t] | Conditional premium/bonus |
| `.charge_if(condition, rate)` | if condition[t]: av *= (1 - rate[t]) | Conditional charges |

### 4.7 Metadata and Debug

| Method | Purpose |
|--------|---------|
| `.capture(name)` | Snapshot current value for downstream use or cross-state reference |
| `.on(state_name)` | Switch target state (multi-state only, sticky) |

---

## 5. Naming Decisions

### 5.1 `.charge()` not `.deduct()`

Every reviewer (5/5) flagged `.deduct(rate)` vs `.subtract(amount)` as confusing — in English, "deduct" and "subtract" are synonyms, but the API gives them different semantics (percentage vs absolute).

**`.charge(rate)`** eliminates this: you "charge" a percentage fee, you "subtract" a dollar amount. These are different words with different actuarial meanings.

### 5.2 `.grow()` not `.credit_interest()`

`.grow()` is more general — it covers fund returns, interest credits, and any multiplicative growth.

### 5.3 `.deduct_nar()` with keyword-only `death_benefit`

"NAR" (net amount at risk) is standard actuarial terminology. Keyword-only prevents argument-order errors:

```python
.deduct_nar(af.coi_rate, death_benefit=af.sum_assured)   # works
.deduct_nar(af.coi_rate, af.sum_assured)                  # TypeError
```

### 5.4 `.on()` for multi-state targeting

Reads as English: "on the AV, add premium." Short, unambiguous, does not collide with any Polars method.

---

## 6. Increment Tracking (Audit & IFRS 17)

### 6.1 API

```python
af.av = (
    af.projection.rollforward(initial=af.av_init, track_increments=True)
    .add(af.premium, "Premium income")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .charge(af.admin_rate, "Admin charge")
    .grow(af.interest_rate, "Interest credit")
    .floor(0)
)

af.coi_amount = af.av.increments["COI"]
af.interest_credited = af.av.increments["Interest credit"]
```

### 6.2 Implementation

When `track_increments=True`, the Rust kernel records `value_after - value_before` for each labeled step at each timestep. The kernel returns a **Struct column**:

```
Struct {
    "result": List<Float64>,          // the AV projection
    "Premium income": List<Float64>,  // increment per period
    "COI": List<Float64>,
    "Admin charge": List<Float64>,
    "Interest credit": List<Float64>,
}
```

When `track_increments=False` (default), the kernel returns `List<Float64>` directly — zero overhead.

### 6.3 Lazy Evaluation Integration

The Struct return fits the Polars lazy pipeline:

1. **At assignment** (`af.av = builder`): two lazy `with_columns` — one for the hidden Struct, one extracting `"result"` as the user-facing column
2. **At increment access** (`af.av.increments["COI"]`): another lazy `with_columns` extracting the named field
3. **At collect**: Polars executes the plugin **once**, then extracts fields via zero-copy pointer arithmetic
4. **Hidden columns** (`__rollforward_*`) stripped in `collect()`

### 6.4 Memory

100K policies × 360 months × 5 labeled steps = ~1.7 GB (6× the AV-only cost). Acceptable — without this, the IFRS 17 actuary runs the model 6 times at the same total cost.

### 6.5 Floor Binding

When `.floor(0)` fires, its increment is positive (AV was pushed up). `increment["Floor"] > 0` IS the signal — no separate boolean needed.

---

## 7. Explain Output

```
Rollforward: initial=av_init, 5 steps, 360 periods

  Step  Operation                    Label                Formula
  ────  ─────────────────────────    ───────────────────  ──────────────────────────────────────
  1     Add(premium)                 Premium income       av[t] = av[t] + premium[t]
  2     DeductNAR(coi_rate, sa)      COI                  av[t] = av[t] - coi_rate[t] × max(0, sa[t] - av[t])
  3     Charge(admin_rate)           Admin charge         av[t] = av[t] × (1 - admin_rate[t])
  4     Grow(interest_rate)          Interest credit      av[t] = av[t] × (1 + interest_rate[t])
  5     Floor(0)                     Non-negative         av[t] = max(av[t], 0)
```

---

## 8. Product Coverage

| Product | Steps Used | Covered? |
|---------|-----------|----------|
| Term Life | No AV — `accumulate()` for reserves | GSP-85 |
| Whole Life | add, charge, grow | Phase 1 |
| Universal Life | add, deduct_nar, charge, grow, floor | Phase 1 |
| Variable UL | add, deduct_nar, charge, grow, floor | Phase 1 |
| Indexed UL | add, charge, grow_capped, floor | Phase 1 |
| Variable Annuity | add, charge, grow, floor | Phase 1 |
| VA + GMDB ratchet | Multi-state: av + guarantee, ratchet_to | Phase 1 |
| VA + GMWB | Multi-state: av + benefit_base, pro_rata_with | Phase 1 |
| UL + secondary guarantee | Multi-state: av + shadow, lapse_when | Phase 1 |
| Participating WL | add, grow, charge | Phase 1 |
| Credit Life | charge, grow | Phase 1 |

**Note:** `deduct_nar` implements the standard convention `COI = rate × max(0, SA - AV)`. Non-standard COI formulas (e.g., capped charges, minimum charges) can be approximated using `.charge()` with a pre-computed rate or may require a custom step type in Phase 3.

---

## 9. Rust Implementation Strategy

### 9.1 Kwargs Structure

```rust
#[derive(Deserialize)]
struct RollforwardKwargs {
    states: Vec<StateSpec>,
    steps: Vec<StepSpec>,
    track_increments: bool,
    assertion_mode: Option<AssertionMode>, // None = stripped from steps
    num_captures: usize,                   // pre-computed: how many capture slots to allocate
    lapse_condition: Option<LapseCondition>,
}

#[derive(Deserialize)]
enum AssertionMode { Flag, Warn, Error }

#[derive(Deserialize)]
struct StateSpec {
    name: String,
    initial_col_index: usize,
}

/// target_index is pre-resolved by Python _compile(): state name → index into states Vec.
/// Single-state rollforward always uses target_index: 0.
/// RatchetTo/ProRataWith use other_state_index (also pre-resolved).
/// Capture uses capture_index (pre-resolved slot in a captures Vec<f64>).
#[derive(Deserialize)]
enum StepSpec {
    // Computation steps — expected_input_index enables exp/act decomposition
    Add { target_index: usize, input_index: usize, label: Option<String>, expected_input_index: Option<usize> },
    Subtract { target_index: usize, input_index: usize, label: Option<String>, expected_input_index: Option<usize> },
    Charge { target_index: usize, input_index: usize, label: Option<String>, expected_input_index: Option<usize> },
    Grow { target_index: usize, input_index: usize, label: Option<String>, expected_input_index: Option<usize> },
    GrowCapped { target_index: usize, input_index: usize, rate_floor: f64, rate_cap: f64, label: Option<String>, expected_input_index: Option<usize> },
    DeductNar { target_index: usize, rate_index: usize, db_index: usize, label: Option<String>, expected_input_index: Option<usize> },
    ChargeTiered { target_index: usize, breakpoints: Vec<f64>, rates: Vec<f64>, label: Option<String> },
    GrowTiered { target_index: usize, breakpoints: Vec<f64>, rates: Vec<f64>, label: Option<String> },
    Floor { target_index: usize, value: f64, label: Option<String> },
    Cap { target_index: usize, value: f64, label: Option<String> },
    RatchetTo { target_index: usize, other_state_index: usize, label: Option<String> },
    ProRataWith { target_index: usize, capture_index: usize, amount_index: usize, label: Option<String> },
    Capture { target_index: usize, capture_index: usize },
    LapseIfZero { target_index: usize },
    AddIf { target_index: usize, condition_index: usize, amount_index: usize, label: Option<String> },
    ChargeIf { target_index: usize, condition_index: usize, rate_index: usize, label: Option<String> },

    // Assertion steps — do not modify state
    AssertNonNegative { target_index: usize, label: String },
    AssertPositive { target_index: usize, label: String },
    AssertLessThan { target_index: usize, bound: AssertBound, label: String },
    AssertGreaterThan { target_index: usize, bound: AssertBound, label: String },
    AssertBetween { target_index: usize, low: AssertBound, high: AssertBound, label: String },
    AssertThat { target_index: usize, condition_index: usize, label: String },
}

#[derive(Deserialize)]
enum AssertBound { Scalar(f64), Column(usize) }

#[derive(Deserialize)]
enum LapseCondition {
    AllNonPositive { state_indices: Vec<usize> },  // pre-resolved by _compile()
}
```

### 9.2 Kernel Architecture

Same two-path architecture as `accumulate.rs`:
- **Fast path:** No nulls — direct array access, pre-allocated output buffer
- **Slow path:** Null handling via `amortized_iter()`

### 9.3 Single-State Inner Loop

```rust
for t in 0..projection_length {
    for (step_idx, step) in steps.iter().enumerate() {
        let av_before = state;
        match step {
            StepSpec::Add { input_index, .. } => {
                state += inputs[*input_index][t];
            }
            StepSpec::Charge { input_index, .. } => {
                state *= 1.0 - inputs[*input_index][t];
            }
            StepSpec::DeductNar { rate_index, db_index, .. } => {
                let nar = f64::max(0.0, inputs[*db_index][t] - state);
                state -= inputs[*rate_index][t] * nar;
            }
            // ... etc
        }
        if track_increments && step.has_label() {
            increment_buffers[label_idx].push(state - av_before);
        }
    }
    result_values.push(state);
}
```

### 9.4 Multi-State Inner Loop

The key difference: `state` becomes `states: Vec<f64>` indexed by pre-resolved `target_index`. Every `StepSpec` carries a `target_index: usize` resolved by Python's `_compile()` — no HashMap lookups in the hot loop.

```rust
let num_states = kwargs.states.len();
let mut states: Vec<f64> = kwargs.states.iter()
    .map(|s| initial_values[s.initial_col_index])
    .collect();
let mut captures: Vec<f64> = vec![0.0; kwargs.num_captures];

for t in 0..projection_length {
    for step in &steps {
        let ti = step.target_index();
        let av_before = states[ti];

        match step {
            StepSpec::Add { target_index, input_index, .. } => {
                states[*target_index] += inputs[*input_index][t];
            }
            StepSpec::Charge { target_index, input_index, .. } => {
                states[*target_index] *= 1.0 - inputs[*input_index][t];
            }
            StepSpec::RatchetTo { target_index, other_state_index, .. } => {
                states[*target_index] = f64::max(states[*target_index], states[*other_state_index]);
            }
            StepSpec::ProRataWith { target_index, capture_index, amount_index, .. } => {
                let ref_val = captures[*capture_index];
                if ref_val > 0.0 {
                    states[*target_index] *= 1.0 - inputs[*amount_index][t] / ref_val;
                }
                // ref_val == 0.0: state unchanged (withdrawal against zero AV is a no-op)
            }
            StepSpec::Capture { target_index, capture_index } => {
                captures[*capture_index] = states[*target_index];
            }
            // ... etc
        }

        if track_increments && step.has_label() {
            increment_buffers[label_idx].push(states[ti] - av_before);
        }
    }

    // Record all state values at this timestep
    for i in 0..num_states {
        result_buffers[i].push(states[i]);
    }

    // Check cross-state lapse condition
    if let Some(LapseCondition::AllNonPositive { ref state_indices }) = kwargs.lapse_condition {
        if state_indices.iter().all(|&i| states[i] <= 0.0) {
            // Zero all states for remaining periods
            for _ in (t + 1)..projection_length {
                for buf in result_buffers.iter_mut() { buf.push(0.0); }
                if track_increments {
                    for buf in increment_buffers.iter_mut() { buf.push(0.0); }
                }
            }
            break;
        }
    }
}
```

### 9.5 Multi-State Output

Returns a Struct column with one `List<Float64>` per state, plus increments if tracked:

```
// Without tracking:
Struct { "av": List<Float64>, "guarantee": List<Float64> }

// With tracking:
Struct {
    "av": List<Float64>,
    "guarantee": List<Float64>,
    "Premium": List<Float64>,           // increment (targets av)
    "COI": List<Float64>,               // increment (targets av)
    "M&E charge": List<Float64>,        // increment (targets av)
    "Fund return": List<Float64>,       // increment (targets av)
    "GMDB ratchet": List<Float64>,      // increment (targets guarantee)
    "Roll-up": List<Float64>,           // increment (targets guarantee)
}
```

Python access:
```python
rf = build_va_gmdb_rollforward(af)

af.av = rf["av"]                         # List<Float64> — lazy struct field extract
af.guarantee = rf["guarantee"]           # List<Float64> — lazy struct field extract
af.coi_amount = rf.increments["COI"]     # List<Float64> — lazy struct field extract
```

### 9.6 `_compile()` Algorithm

The builder's `_compile()` converts the Python step list into `(args: list[pl.Expr], kwargs: dict)` for `register_plugin_function`. The key mechanism is column reference deduplication:

```python
def _compile(self) -> tuple[list[pl.Expr], dict]:
    args: list[pl.Expr] = []
    expr_index: dict[str, int] = {}  # column_name → index in args

    def _register(column_ref) -> int:
        """Register a column reference, deduplicating by name. Returns index."""
        expr = self._to_expr(column_ref)  # ColumnProxy → pl.col("name")
        key = column_ref.name if hasattr(column_ref, 'name') else str(expr)
        if key not in expr_index:
            expr_index[key] = len(args)
            args.append(expr)
        return expr_index[key]

    # States: build state name → index mapping + register initial columns
    state_name_to_index = {}
    state_specs = []
    for i, (name, initial_ref) in enumerate(self._states.items()):
        state_name_to_index[name] = i
        state_specs.append({"name": name, "initial_col_index": _register(initial_ref)})

    # Captures: pre-assign indices
    capture_name_to_index = {}
    capture_count = 0
    for step in self._steps:
        if step.operation == "capture":
            capture_name_to_index[step.args[0]] = capture_count
            capture_count += 1

    # Steps: resolve all references to indices
    step_specs = []
    for step in self._steps:
        target_idx = state_name_to_index[step.target or "__default__"]
        match step.operation:
            case "add":
                spec = {"Add": {
                    "target_index": target_idx,
                    "input_index": _register(step.args[0]),
                    "label": step.label,
                    "expected_input_index": _register(step.kwargs["expected"]) if "expected" in step.kwargs else None,
                }}
            case "deduct_nar":
                spec = {"DeductNar": {
                    "target_index": target_idx,
                    "rate_index": _register(step.args[0]),
                    "db_index": _register(step.kwargs["death_benefit"]),
                    "label": step.label,
                    "expected_input_index": _register(step.kwargs["expected"]) if "expected" in step.kwargs else None,
                }}
            case "ratchet_to":
                spec = {"RatchetTo": {
                    "target_index": target_idx,
                    "other_state_index": state_name_to_index[step.args[0]],
                    "label": step.label,
                }}
            case "pro_rata_with":
                spec = {"ProRataWith": {
                    "target_index": target_idx,
                    "capture_index": capture_name_to_index[step.args[0]],
                    "amount_index": _register(step.args[1]),
                    "label": step.label,
                }}
            case "capture":
                spec = {"Capture": {
                    "target_index": target_idx,
                    "capture_index": capture_name_to_index[step.args[0]],
                }}
            # ... etc for each operation type
        step_specs.append(spec)

    # Lapse condition: resolve state names to indices
    lapse = None
    if self._lapse_condition:
        lapse = {"AllNonPositive": {
            "state_indices": [state_name_to_index[n] for n in self._lapse_condition["states"]]
        }}

    kwargs = {
        "states": state_specs,
        "steps": step_specs,
        "track_increments": self._track_increments,
        "assertion_mode": self._assertion_mode,  # serialized as string, Serde deserializes to enum
        "num_captures": capture_count,
        "lapse_condition": lapse,
    }
    return args, kwargs
```

All name-to-index resolution happens in Python at compile time. The Rust kernel receives only integers — no string lookups in the hot loop.

### 9.7 Error Handling

| Condition | When detected | Behavior |
|-----------|--------------|----------|
| Mismatched inner list lengths across input columns | Kernel startup (per row) | `PolarsError::ComputeError` — hard error |
| Null initial value | Kernel startup (per row) | Null output row (same as `accumulate.rs`) |
| Null inner list | Kernel startup (per row) | Empty output (same as `accumulate.rs`) |
| Zero-length projection (empty list) | Inner loop | Zero iterations — produces empty output list |
| `pro_rata_with` reference value is 0.0 | Inner loop | State unchanged — withdrawal against zero AV is a no-op |
| NaN in input data | Inner loop | NaN propagates through all subsequent steps (same as `accumulate.rs`) |
| `floor`/`cap` triggered | Inner loop | Increment captures the clamping amount (positive increment = floor fired) |

Invalid kwargs (e.g., `target_index` out of bounds, `capture_index` out of bounds) are programming errors in `_compile()`, not runtime data errors. These panic in debug builds and are UB in release — the Python builder is responsible for producing valid kwargs. This matches the existing `accumulate.rs` pattern where `inputs[*input_index]` does unchecked array access in the fast path.

### 9.8 `lapse_when` Semantics

`.lapse_when(all_non_positive=["av", "guarantee"])` is a **top-level configuration**, not a step in the step list. It is checked at the end of each timestep, after all steps have executed. The builder enforces:

- At most one `lapse_when` per rollforward (the kwargs field is `Option<LapseCondition>`, not `Vec`)
- Position in the chain does not matter — the builder stores it separately from the step list
- Only valid in multi-state mode (error at build time if used with single `initial=`)
- For single-state lapse, use `.lapse_if_zero()` which IS a step in the step list (checked inline)

### 9.9 `.capture()` in Single-State Mode

`.capture(name)` is useful in single-state mode for exposing intermediate values to Python:

```python
af.av = (
    af.projection.rollforward(initial=af.av_init, track_increments=True)
    .add(af.premium, "Premium")
    .capture("av_after_premium")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .grow(af.interest_rate, "Interest")
    .floor(0)
)

af.av_after_premium = af.av.captures["av_after_premium"]
```

Captures are stored as additional `List<Float64>` fields in the Struct output (same pattern as increments). In multi-state mode, captures additionally enable cross-state references via `pro_rata_with`.

### 9.10 Performance Expectations

- `accumulate()` (GSP-85): ~5 ns/operation/policy
- Single-state rollforward, 5 steps: ~25-40 ns/period/policy
- Multi-state rollforward, 2 states × 7 steps: ~50-70 ns/period/policy
- 100K policies × 360 months (single-state): ~150-250ms with Polars (8 cores)
- 100K policies × 360 months (multi-state): ~250-400ms with Polars (8 cores)

---

## 10. Reviewer Feedback Summary

Five independent reviewers evaluated this design:

| Reviewer | Role | Key Feedback | Incorporated? |
|----------|------|-------------|---------------|
| Senior production-platform actuary | Production model builder | Rename `.deduct()` → `.charge()`; add `.grow_tiered()`; keyword-only params on `.deduct_nar()` | Yes |
| Junior Python actuary | lifelib/modelx user | `.deduct` vs `.subtract` confusing; wants debug mode; ordering transparency is the killer feature | Yes |
| Model validation auditor | Regulatory compliance | Need step-level increments for IFRS 17; `.explain()` must show formulas; Rust backend is a black-box risk | Yes |
| LLM code generation specialist | AI/ML engineer | `.deduct`/`.subtract` ambiguity is #1 LLM error; 8/10 few-shot learnability; decision tree docs needed | Yes |
| Exotic product actuary | VA/IUL specialist | GMWB needs cross-state refs; secondary guarantee needs multi-state lapse; `.apply(fn)` escape hatch desired | Partially — cross-state refs and lapse_when added; `.apply(fn)` impossible in Polars plugin architecture |

---

## 11. Documentation Plan

### 11.1 Decision Tree

```
Is the amount proportional to AV or absolute?
├── Proportional (e.g., "0.15% of account value")
│   ├── Reducing AV → .charge(rate)
│   └── Growing AV  → .grow(rate)
├── Absolute (e.g., "$15 per month")
│   ├── Adding      → .add(amount)
│   └── Removing    → .subtract(amount)
├── Depends on AV and another variable (e.g., "rate × max(0, SA - AV)")
│   └── .deduct_nar(rate, death_benefit=...)
└── Depends on AV tier
    ├── Reducing → .charge_tiered(breakpoints, rates)
    └── Growing  → .grow_tiered(breakpoints, rates)
```

### 11.2 Product Recipes

Complete rollforward examples for: Term Life, Whole Life, Universal Life, Variable UL, Indexed UL, Variable Annuity, VA + GMDB.

### 11.3 Common Mistakes

- Using `.charge()` when you mean `.subtract()` (percentage vs flat dollar)
- Forgetting `.floor(0)` on UL products
- Wrong step ordering (interest before charges)
- Passing annual rates without monthly conversion

---

## 12. Mid-Chain Assertions

Assertions validate business rules at specific points without changing the calculation.

```python
af.av = (
    af.projection.rollforward(initial=af.av_init, track_increments=True, assertions="flag")
    .add(af.premium, "Premium income")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .assert_positive("AV must be positive after COI")
    .charge(af.admin_rate, "Admin charge")
    .grow(af.interest_rate, "Interest credit")
    .floor(0)
)

failures = af.av.assertions  # DataFrame: policy_id, period, step, label, value
```

**6 methods:** `assert_non_negative`, `assert_positive`, `assert_less_than(bound)`, `assert_greater_than(bound)`, `assert_between(low, high)`, `assert_that(condition)` (escape hatch for pre-computed booleans).

**3 modes:** `"flag"` (batch — store failures, continue), `"warn"` (log, continue), `"error"` (raise on first failure). Default when omitted: assertions stripped from kwargs entirely — zero overhead.

---

## 13. Expected-vs-Actual Decomposition

Embeds IFRS 17 experience variance attribution in a single run.

```python
af.av = (
    af.projection.rollforward(initial=af.av_init, track_increments=True)
    .add(af.premium, "Premium", expected=af.scheduled_premium)
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI", expected=af.expected_coi_rate)
    .charge(af.admin_rate, "Admin", expected=af.expected_admin_rate)
    .grow(af.interest_rate, "Interest", expected=af.expected_interest_rate)
    .floor(0)
)

af.coi_expected = af.av.increments["COI:expected"]
af.coi_variance = af.av.increments["COI:variance"]
# Invariant: total == expected + variance (exact)
```

**Approach:** Single path, first-order approximation (sequential marginal decomposition — industry standard). Interaction terms absorbed by step ordering. Requires `track_increments=True`.

**Supported on:** `add`, `subtract`, `charge`, `grow`, `grow_capped`, `deduct_nar`. Not on structural steps (`floor`, `cap`, `ratchet_to`).

---

## 14. Step Composition

Labels are the addressing mechanism. Required-unique, auto-generated from `Operation(column_name)` if omitted.

```python
from gaspatchio_core.rollforward import Step

base_ul = (
    af.projection.rollforward(initial=af.av_init, track_increments=True)
    .add(af.premium, "Premium")
    .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
    .charge(af.admin_rate, "Admin")
    .grow(af.interest_rate, "Interest")
    .floor(0)
)

ul_with_rider = base_ul.insert_before("Interest", Step.charge(af.rider_rate, "Rider Fee"))
ul_tiered = base_ul.replace("Admin", Step.charge_tiered([0, 50000], [0.0015, 0.0008], "Tiered Admin"))
ul_no_admin = base_ul.remove("Admin")
```

**6 methods:** `insert_before`, `insert_after`, `remove`, `replace`, `prepend`, `append`. All return new builders (immutable, tuple-backed). `KeyError` if label not found.

---

## 15. Model Fingerprinting

```python
rf.fingerprint()   # "sha256:a1b2c3d4..."
rf.canonical()     # dict — structural form
```

Canonical form includes step types, ordering, target state names, constant parameters. Excludes column names (environment-dependent aliases), labels, input indices. Trivial to implement since the builder holds the step list.

---

## 16. Multi-State Deep Dive (Phase 2 Roadmap)

### 16.1 What Changes from Phase 1

| Aspect | Phase 1 (single-state) | Phase 2 (multi-state) |
|--------|----------------------|---------------------|
| Constructor | `rollforward(initial=af.av_init)` | `rollforward(av=af.av_init, guarantee=af.guarantee_init)` |
| State storage | Single `f64` | `Vec<f64>` indexed by state name |
| `.on()` | Not needed (single target) | Sticky state targeting |
| Return type | `List<Float64>` or Struct (with tracking) | Always Struct (one field per state + increments) |
| Access | `af.av = result` | `af.av = rf["av"]` |
| Cross-state ops | N/A | `ratchet_to`, `pro_rata_with`, `lapse_when` |
| Captures | Snapshot for downstream Python use | Also accessible cross-state within the kernel |

### 16.2 Builder Changes

The builder needs:
- Constructor overload detection: `initial=` → single-state, named kwargs → multi-state
- `._current_target` attribute (starts as first named state, changed by `.on()`)
- `__getitem__` for `rf["av"]` → lazy Struct field extraction
- `.increments` on the multi-state result needs to scope to the right Struct fields

### 16.3 Rust Kernel Changes

The single-state fast path remains as an optimization: when `states.len() == 1`, skip `HashMap` lookups and use a bare `f64`. The multi-state path adds:

- `Vec<f64>` state array
- `HashMap<&str, usize>` for state name → index
- `HashMap<&str, f64>` for capture storage
- `LapseCondition` check at end of each timestep
- Multiple output buffers (one per state)

### 16.4 Downstream Consumption (Phase 2)

```python
rf = build_va_gmdb(af)

# State projections
af.av = rf["av"]
af.guarantee = rf["guarantee"]

# Increments (per-state, by label)
af.coi = rf.increments["COI"]
af.fund_growth = rf.increments["Fund return"]
af.ratchet_amount = rf.increments["GMDB ratchet"]

# Downstream — same patterns as single-state
af.death_benefit = gp.max(af.av, af.guarantee)
af.pv_death = (af.death_benefit * af.qx * af.survival).projection.prospective_value(discount_rate=af.rate)
```

### 16.5 What Phase 1 Must Get Right for Phase 2

1. **`target: String` on every StepSpec variant** — already done
2. **`states: Vec<StateSpec>` in kwargs** — already done (single-state uses `[{name: "__default__", ...}]`)
3. **Struct output pattern** — Phase 1 introduces this for `track_increments`, Phase 2 extends it for multi-state
4. **`__rollforward_*` hidden column pattern** — Phase 1 introduces this, Phase 2 reuses it
5. **Labels as the universal addressing mechanism** — Phase 1 establishes this for composition + increments

**No breaking changes needed when Phase 2 ships.** The kwargs format, the Struct output pattern, and the Python hidden-column mechanism all extend naturally.

---

## 17. Implementation Phases

### Phase 1 — GSP-86: Rollforward Engine (MVP)

**Rust kernel:**
- Single-state AND multi-state rollforward with step-dispatch inner loop
- Fast path (no nulls) / slow path (null handling)
- Core steps: `add`, `subtract`, `charge`, `grow`, `grow_capped`, `deduct_nar`, `floor`, `cap`
- Multi-state steps: `ratchet_to`, `pro_rata_with`
- Conditionals: `add_if`, `charge_if`, `lapse_if_zero`, `lapse_when`
- `track_increments` with Struct column output
- `.capture()` for intermediate snapshots and cross-state references

**Python builder:**
- `af.projection.rollforward(initial=...)` (single-state) and `rollforward(av=..., guarantee=...)` (multi-state)
- `.on(state_name)` sticky state targeting
- Method-chain builder, immutable (tuple-backed)
- Labels — required-unique, auto-generated if omitted
- Step composition — `insert_before`, `insert_after`, `remove`, `replace`, `prepend`, `append`
- `Step` factory namespace
- `.explain()` with formula table
- `canonical()` and `fingerprint()`

### Phase 2 — Governance Features

**Mid-chain assertions:** 6 assertion StepSpec variants, flag/warn/error modes, zero cost when disabled.

**Expected-vs-actual decomposition:** `expected=` keyword on rate/amount steps, three-way increments (`label`, `label:expected`, `label:variance`).

**Tiered operations:** `charge_tiered`, `grow_tiered`.

**Templates:** `RollforwardTemplate` (unbound, string column names), `.bind(af)`, YAML serialization.

### Phase 3 — On Demand

- `ProductSpec` + `validate_against(spec)` — when a customer has formal model governance
- `rf.diff(other)` — `git diff` on declarative chains is sufficient for now
- `charge_lookup` (mid-loop assumption table access)
- Fund-dimension support (array-valued states)
- Extended branch predicates
- Dual-path expected/actual (if regulatory demand)

---

## 18. Supplementary Design Documents

| Document | Covers |
|----------|--------|
| `31-fingerprint-and-diffing-design.md` | ProductSpec data structures, YAML format, validation algorithm, diffing algorithm, CI integration |
| `31-rollforward-composition.md` | StepDef internals, immutability implementation, Step factory, template binding, column mapping, product library pattern |
