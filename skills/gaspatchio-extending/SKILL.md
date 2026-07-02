---
name: gaspatchio-extending
description: Use when adding custom calculations, new accessor methods, or porting functions from other actuarial libraries (JuliaActuary, lifelib, QuantLib) to the Gaspatchio framework. Also use when model-review flags map_elements or Python for-loops that should be rewritten as proper accessors.
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Extending Gaspatchio

## Overview

Gaspatchio is extended through **accessor methods** that compose Polars expressions. Every extension must be vectorized — no Python loops, no `map_elements`, no exceptions.

This skill provides the decision framework and templates. Detailed patterns live in `references/` files — load them as needed.

## When to Use

Use this skill when you are asked to:

- Add custom calculations or methods to Gaspatchio
- Create a new accessor namespace (e.g., `af.risk`, `af["col"].insurance`)
- Add methods to an existing accessor namespace (e.g., adding `duration_macaulay()` to `finance`)
- Write reusable domain-specific functions that operate on ActuarialFrame or column data
- Port functions from other actuarial libraries (JuliaActuary, lifelib, QuantLib, etc.)

Do NOT use this skill when:

- Writing model code that uses existing accessors — use `gaspatchio-model-building`
- Reviewing model quality — use `gaspatchio-model-review`
- The calculation is a one-off inline formula in a model — just use operators directly

This skill can be used standalone. Combine with `gaspatchio-model-review` for quality review of the extension.

---

## Hard Gate

**Do NOT write extension code until you have completed ALL three steps:**

1. Determined where the calculation belongs using the performance ladder (see below)
2. Verified no existing accessor already provides the functionality:
   ```bash
   uv run gspio docs "<method or concept>"
   ```
   If the command returns no results, that confirms the method does not exist — proceed to the ladder. If the CLI is unavailable, search the accessor files directly with grep.
3. Identified whether the calculation operates on scalar columns, list columns, or both

**Do NOT guess. Do NOT skip the lookup. Do NOT assume you know what methods exist.**

**Early exit:** If the performance ladder places your calculation at Level 1 (already exists), Level 2 (one-off formula), Level 3 (setup utility), or Level 6 (needs Rust), you are done with this skill. Route to the appropriate next step — do not proceed to the accessor pattern or completion gate.

---

## The Performance Ladder

Before writing anything, determine where your calculation belongs. Work through this table top to bottom — stop at the first match.

| Question | If Yes | Action |
|----------|--------|--------|
| Does a built-in method already exist? | Stop | Use it. Do not reimplement. Check accessors AND frame-level methods (`quantile`, `sum`, `mean`). |
| Is it a scenario stress or shock to an assumption? | Stop | Use the `scenarios/shocks` composables. Not an accessor. The current set is `MultiplicativeShock`, `AdditiveShock`, `OverrideShock`, `ClipShock`, `FilteredShock` (WHERE), `TimeConditionalShock` (WHEN), `PipelineShock` (chain), `MaxShock`, `MinShock`, `RelativeFloorShock`, `ParameterShock` — most stresses compose from these. |
| Is it a custom mergeable aggregator (skewness, weighted TVaR, a portfolio Sharpe ratio)? | Stop | Subclass `BaseAggregator` with the `@scenario_aggregator("Name")` decorator. Not an accessor. The aggregator carries its own column, alias, `.over()` partition, `.of()` polars escape, and survives YAML round-trip + parallel merge for free. See `concepts/scenarios/custom-aggregators.md` for the contract. |
| Is it within-period state-machine logic (COI on NAR, IUL floor/cap, GMDB ratchet)? | Stop | Use `af.projection.rollforward(states={…})`. Not an accessor. The kernel handles the within-period balance dependency the loop was working around. |
| Is it a one-off formula in a single model? | Stop | Use operators inline (`af.x * af.y`). Not an accessor. |
| Is it too simple for an accessor (single operator like `a / b`)? | Stop | Use operators inline. Accessors are for formulas with branching, parameters, or non-obvious logic. |
| Does it run once per model (curve fitting, table prep, data loading)? | Stop | Write a Python utility function in the model's setup phase. Not an accessor. |
| Does it need scipy/numpy (optimization, interpolation, linear algebra)? | Stop | Write a Python helper function. Not an accessor. |
| Does it need raw performance at scale (Monte Carlo, inner loops to omega, per-policy sequential work)? | Stop | Flag for Rust kernel contribution. Do not attempt in Python. |
| Is it reusable element-wise arithmetic on a column, expressible as Polars expressions? | **Build it** | Column accessor returning `ExpressionProxy`. |
| Does it operate on the whole frame (adds/transforms multiple columns) using vectorized Polars expressions? | **Build it** | Frame accessor returning `ActuarialFrame`. |

**Examples of correct placement:**

| Calculation | Placement | Why |
|-------------|-----------|-----|
| Nelson-Siegel-Svensson curve fitting | Python utility in model setup | Runs once, needs scipy, shared across all policies |
| Macaulay duration | Column accessor (`finance.duration_macaulay()`) | Element-wise arithmetic on list columns, reusable |
| Rate conversion (continuous to periodic) | Column accessor (`finance.to_continuous()`) | 1-3 lines of `exp`/`log`, reusable |
| Monte Carlo rate simulation | Flag for Rust | Billions of ops at scale |
| Product code to expense loading | Not an accessor — use `when/then` or `Table.lookup()` | Model-specific logic, not reusable |
| Annuity certain (due/immediate) | Column accessor (`finance.annuity_due()`) | Closed-form formula, reusable |
| Life-contingent annuity with full mortality | Flag for Rust | Inner loop to omega per policy across millions |
| Gompertz/Makeham hazard rate | Column accessor | Single formula: `a * exp(b * age) + c` |
| Solvency II lapse stress | Not an accessor — use `scenarios/shocks` | `PipelineShock(MultiplicativeShock(1.4), ClipShock(1.0))` |
| Perpetuity PV (`payment / rate`) | Not an accessor — use operators inline | Single operator, too simple for accessor overhead |
| Solvency II VaR at 99.5% | Not an accessor — use `af.quantile(0.995)` | Already exists as a frame method |

Details: [references/performance-ladder.md](references/performance-ladder.md)

---

## The Accessor Pattern

Gaspatchio has two accessor types. Load the templates before writing code.

### Column Accessor (most common)

For methods that operate on a single column or expression. The user calls it as `af.column_name.namespace.method()`.

Key rules:
- Inherit from `BaseColumnAccessor`
- Register with `@register_accessor("name", kind="column")`
- Accept `proxy: ColumnProxy | ExpressionProxy` in `__init__`
- Return `ExpressionProxy` from every method
- Handle both scalar and list columns by reading the proxy's cached `.shape` (`proxy.shape == "list"`)

### Frame Accessor (less common)

For methods that operate on the entire frame. The user calls it as `af.namespace.method()`.

Key rules:
- Inherit from `BaseFrameAccessor`
- Register with `@register_accessor("name", kind="frame")`
- Accept `frame: ActuarialFrame` in `__init__`
- Return `ActuarialFrame` from methods that transform the frame

Templates with real code: [references/accessor-template.md](references/accessor-template.md)

---

## Non-Negotiable Rules

1. **Compose Polars expressions.** No `map_elements`, `apply`, `iter_rows`, or Python for-loops. Ever.
2. **Handle both scalar and list columns.** Read the proxy's cached shape (`proxy.shape == "list"`) to detect and branch. Never assume one or the other.
3. **Return the correct type.** Column methods return `ExpressionProxy`. Frame methods return `ActuarialFrame`.
4. **Include a docstring with a working example.** These are tested by `uv run pytest --doctest-modules`.
5. **Look up existing methods first.** `uv run gspio docs "<method>"` is mandatory before you start writing.
6. **Import and registration in a single edit.** The on-save hook runs `ruff` which strips unused imports. Add the import AND the code that uses it in the same edit.

---

## Anti-Patterns

These are the patterns that will make your extension 50-1000x slower. Every one of them is tempting. Every one of them is wrong.

| Anti-Pattern | Actuarial Example | Slowdown |
|-------------|-------------------|----------|
| Python for-loop over time | Reserve recursion, AV rollforward | 100-500x slower |
| if/else per policy | Product-specific formulas | 50-200x slower |
| Dict lookup per row | Mortality table query | 200-1000x slower |
| Iterative running totals | Account value accumulation | 100-500x slower |
| `for policy in policies` | Any per-policy processing | 1000x+ slower |
| `map_elements` with lambda | String categorization, product mapping | 20-100x slower |
| Python datetime loops | Duration calculation, attained age | 50-200x slower |

Each entry has naive code, why it is slow, and the correct approach: [references/anti-patterns.md](references/anti-patterns.md)

---

## Environment

Always use `uv run` — the system Python does not have gaspatchio or polars installed:

```bash
uv run gspio docs "<method>"                    # look up API
uv run pytest                                   # run tests including docstrings
uv run pytest --doctest-modules                 # validate docstring examples
uv run python3 -c "import gaspatchio_core; ..."  # inline scripts
```

---

## Reference Files

Load these when working in the relevant area:

| Topic | File | When to Load |
|-------|------|-------------|
| **Accessor templates** | [references/accessor-template.md](references/accessor-template.md) | Before writing any accessor code |
| **Performance ladder** | [references/performance-ladder.md](references/performance-ladder.md) | Before deciding where a calculation belongs |
| **Anti-patterns** | [references/anti-patterns.md](references/anti-patterns.md) | Before writing any extension code |

---

## Red Flags — You Are Writing the Wrong Thing

| Thought | Reality |
|---------|---------|
| "I'll use map_elements, it's just one function" | map_elements is 14-100x slower. Compose Polars expressions. Always. |
| "This is a one-off, not worth an accessor" | If the formula has branching, parameters, or non-obvious logic, it IS worth an accessor. |
| "I'll add the accessor later" | Later never comes. Write it now while you understand the pattern. |
| "The performance ladder is overkill for this" | 20/20 test agents followed the ladder correctly. You should too. |
| "I need a for-loop for this sequential calculation" | Check for existing Rust kernels first (accumulate, prospective_value, cumulative_survival). |
| "This stress test should be an accessor" | Stresses belong in `scenarios/shocks` composables, not accessors. Invoke `gaspatchio-model-scenarios`. |

---

## Integration

**Called by:**
- `gaspatchio-model-building` — when a needed method doesn't exist
- `gaspatchio-model-review` — when `map_elements` or Python for-loops should be rewritten as accessors

**REQUIRED next steps:**
- `gaspatchio-model-building` — to use the new accessor in model code
- `gaspatchio-model-review` — to review the extension for quality

**Routes to when needed:**
- `gaspatchio-model-reconciliation` — when verifying the accessor against a reference implementation

---

## Completion Gate

### For non-accessor placements (Levels 1, 2, 3, 6)

If the performance ladder placed the calculation outside accessor territory, the gate is:

- [ ] Calculation placement determined and documented
- [ ] User informed of the correct approach (use existing method, write inline, write setup utility, or flag for Rust)
- [ ] If Level 3 (setup utility): function is typed, has docstring, and is called in the model's setup phase (Phase 1)
- [ ] If Level 6 (Rust): user told this needs a core contribution, with suggestion of existing methods that may approximate the need

### For accessor implementations (Levels 4, 5)

Extension is complete when:

- [ ] Calculation placement determined using performance ladder
- [ ] Existing methods checked via `uv run gspio docs`
- [ ] Accessor inherits from correct base class (`BaseColumnAccessor` or `BaseFrameAccessor`)
- [ ] Registration uses `@register_accessor` with correct name and kind
- [ ] `_get_polars_expr()` helper defined (for column accessors) — handles both `ColumnProxy` and `ExpressionProxy`
- [ ] `_parent is None` guard present with clear error message
- [ ] All methods compose Polars expressions (no `map_elements`, `apply`, for-loops)
- [ ] Both scalar and list columns handled (verified via `proxy.shape == "list"` against `ColumnProxy`/`ExpressionProxy`)
- [ ] Return types are correct (`ExpressionProxy` for column, `ActuarialFrame` for frame)
- [ ] Docstring uses NumPy style with working example
- [ ] Mathematical correctness verified against a known reference value
- [ ] Tests pass: `uv run pytest` including docstring validation
- [ ] No anti-patterns from the anti-patterns reference

If any method uses `map_elements`, `apply`, `iter_rows`, or a Python for-loop over policies or timesteps, the extension is **not complete**.
