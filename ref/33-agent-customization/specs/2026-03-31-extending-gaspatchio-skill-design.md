# Extending Gaspatchio: Skill and Registry Improvements

**Date**: 2026-03-31
**Status**: Draft
**Branch**: `cursor/agent-customization-plugin-arch`
**Supersedes**: `2026-03-30-agent-customization-plugin-architecture-design.md` (defers packaging/native plugin infrastructure; focuses on the agent glide path)

## Problem

Gaspatchio has working extension primitives — `register_accessor`, `BaseColumnAccessor`, `BaseFrameAccessor` — but no guidance for agents on how to use them correctly. An agent asked to "add Macaulay duration" will reach for `map_elements` or a Python for-loop before it discovers the accessor pattern. This produces code that is 50-1000x slower than the equivalent Polars expression composition.

The gap is not infrastructure. The gap is teaching.

## Goal

Give agents a reliable glide path for extending Gaspatchio that steers them toward performance-safe patterns and away from anti-patterns. Specifically:

1. A new skill (`extending-gaspatchio`) that teaches agents where calculations belong, how to write accessors, and what never to do
2. Small registry improvements that make the extension path more robust
3. Cross-references from existing skills so agents discover the extension path naturally

## Non-Goals

- Entry-point discovery for installable plugin packages (deferred)
- Native Rust plugin loading from external packages (deferred)
- CLI commands for plugin management (deferred)
- Plugin manifests or compatibility checking (deferred)
- Directory auto-scanning for local plugins (deferred)

Nothing in this design blocks any of the above. All extension paths funnel through `register_accessor`, which is the stable contract. Discovery mechanisms are different ways of finding classes to feed into it.

## Deliverables

### 1. New Skill: `extending-gaspatchio`

#### Location

```
skills/extending-gaspatchio/
├── SKILL.md
└── references/
    ├── accessor-template.md
    ├── performance-ladder.md
    └── anti-patterns.md
```

#### SKILL.md Structure

Follows the established skill conventions:

- **Frontmatter**: `name: gaspatchio-extending`, `description`, `allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob`
- **Directory**: `skills/extending-gaspatchio/` (follows `gaspatchio-` prefix convention in `name` field; directory omits the prefix like `model-building` → `gaspatchio-model-building`)
- **Section order**: When to use → Hard gate → Overview → Core content → References table → Completion gate

#### When to Use

Triggers when an agent is asked to:

- Add custom calculations or methods to Gaspatchio
- Create a new accessor namespace (e.g., `af.risk`, `af["col"].insurance`)
- Add methods to an existing accessor namespace
- Write reusable domain-specific functions that operate on ActuarialFrame or column data
- Port functions from other actuarial libraries (JuliaActuary, lifelib, etc.)

Does NOT trigger when:

- Writing model code that uses existing accessors (that is `model-building`)
- Reviewing model quality (that is `model-review`)
- The calculation is a one-off inline formula in a model (just use operators)

#### Hard Gate

Do NOT write extension code until you have:

1. Determined where the calculation belongs (setup utility, column accessor, or frame accessor) using the performance ladder
2. Verified no existing accessor already provides the functionality (`uv run gspio docs "<method>"`)
3. Identified whether the calculation operates on scalar columns, list columns, or both

#### Core Content: The Performance Ladder

Decision tree taught by the skill:

| Question | Answer | Action |
|----------|--------|--------|
| Does a built-in method already exist? | Yes | Use it. Do not reimplement. |
| Is it a one-off formula in a model? | Yes | Use operators inline. Not an accessor. |
| Does it run once per model (curve fitting, table prep, data loading)? | Yes | Python utility function in model setup. Not an accessor. |
| Does it need scipy/numpy (optimization, interpolation, linear algebra)? | Yes | Python helper function. Not an accessor. |
| Is it reusable element-wise arithmetic on a column? | Yes | Column accessor returning `ExpressionProxy`. |
| Does it operate on the whole frame (adds/transforms multiple columns)? | Yes | Frame accessor returning `ActuarialFrame`. |
| Does it need raw performance at scale (Monte Carlo, inner loops to omega)? | Yes | Flag for Rust contribution. Do not attempt in Python. |

**Examples of correct placement:**

| Calculation | Placement | Why |
|-------------|-----------|-----|
| Nelson-Siegel-Svensson curve fitting | Python utility in model setup | Runs once, needs scipy, shared across all policies |
| Macaulay duration | Column accessor (`finance.duration_macaulay()`) | Element-wise arithmetic on list columns, reusable |
| Rate conversion (continuous to periodic) | Column accessor (`finance.to_continuous()`) | 1-3 lines of `exp`/`log`, reusable |
| Monte Carlo rate simulation | Flag for Rust | Billions of ops at scale |
| Product code to expense loading mapping | Not an accessor — use `when/then` or `Table.lookup()` | Model-specific logic, not reusable framework code |

#### Core Content: The Accessor Pattern

The skill points agents to `references/accessor-template.md` which contains:

**Column accessor template** (the most common case):

- Inherit from `BaseColumnAccessor`
- Register with `@register_accessor("name", kind="column")`
- Accept `proxy: ColumnProxy | ExpressionProxy` in `__init__`
- Detect list vs scalar columns via `ColumnTypeDetector`
- Return `ExpressionProxy` from every method
- Include docstring with a working example (tested by pytest)

**Frame accessor template** (less common):

- Inherit from `BaseFrameAccessor`
- Register with `@register_accessor("name", kind="frame")`
- Accept `frame: ActuarialFrame` in `__init__`
- Return `ActuarialFrame` from methods that transform the frame
- Can also return `ExpressionProxy` for methods that produce a single expression

Both templates are extracted from the existing `finance.py` accessor pattern — real code, not hypothetical.

#### Core Content: Non-Negotiable Rules

1. Every method must compose Polars expressions. No `map_elements`, `apply`, `iter_rows`, or Python for-loops.
2. Handle both scalar and list columns. Use `ColumnTypeDetector` to branch. Never assume one or the other.
3. Return the correct type. Column methods return `ExpressionProxy`. Frame methods return `ActuarialFrame`.
4. Include a docstring with a working example. These are tested by `uv run pytest --doctest-modules`.
5. Look up existing methods before writing. `uv run gspio docs "<method>"` is mandatory before starting.
6. Import and registration in a single edit. The on-save hook runs `ruff` which strips unused imports.

#### Core Content: Anti-Patterns

The skill points agents to `references/anti-patterns.md` which contains 7 concrete examples:

| Anti-Pattern | Actuarial Example | Speedup from Correct Approach |
|-------------|-------------------|-------------------------------|
| Python for-loop over time | Reserve recursion | 100-500x |
| if/else per policy | Product-specific logic | 50-200x |
| Dict lookup per row | Mortality table query | 200-1000x |
| Iterative running totals | Account value accumulation | 100-500x |
| `for policy in policies` | Any per-policy loop | 1000x+ |
| `map_elements` with lambda | String categorization | 20-100x |
| Python datetime loops | Duration calculation | 50-200x |

Each entry includes: the naive code an agent would write, why it is slow, the correct Gaspatchio approach, and the performance difference.

#### References Table

| Topic | File | When to Load |
|-------|------|--------------|
| Column and frame accessor templates | [references/accessor-template.md](references/accessor-template.md) | Before writing any accessor code |
| Performance ladder decision tree | [references/performance-ladder.md](references/performance-ladder.md) | Before deciding where a calculation belongs |
| Anti-patterns with before/after | [references/anti-patterns.md](references/anti-patterns.md) | Before writing any extension code |

#### Completion Gate

Extension is complete when:

- [ ] Calculation placement determined using performance ladder
- [ ] Existing methods checked via `uv run gspio docs`
- [ ] Accessor inherits from correct base class (`BaseColumnAccessor` or `BaseFrameAccessor`)
- [ ] Registration uses `@register_accessor` with correct name and kind
- [ ] All methods compose Polars expressions (no `map_elements`, `apply`, for-loops)
- [ ] Both scalar and list columns handled (verified with `ColumnTypeDetector`)
- [ ] Return types are correct (`ExpressionProxy` for column, `ActuarialFrame` for frame)
- [ ] Docstring includes working example
- [ ] Tests pass: `uv run pytest` including docstring validation
- [ ] No anti-patterns from the anti-patterns reference

If any method uses `map_elements`, `apply`, `iter_rows`, or a Python for-loop over policies or timesteps, the extension is **not complete**.

#### Routing to Other Skills

| Situation | Route to |
|-----------|----------|
| Writing model code that uses the new accessor | `gaspatchio-model-building` |
| Reviewing extension quality | `gaspatchio-model-review` |
| Matching output against a reference implementation | `gaspatchio-model-reconciliation` |

### 2. Registry Improvements

Three small changes to `bindings/python/gaspatchio_core/frame/registry.py`:

#### 2a. Idempotent Same-Class Registration

**Current behavior**: `register_accessor` raises `ValueError` if an accessor name+kind is already registered.

**New behavior**: If the same class is re-registered with the same name+kind, succeed silently. If a different class tries to claim the same name+kind, raise `ValueError` with a message naming both the existing and conflicting classes.

**Why**: Prevents breakage when the same module is imported twice (e.g., user imports their accessor module explicitly, and it is also imported via entry points in a future version). Does not weaken conflict detection.

#### 2b. Registration Validation

Add validation in `register_accessor` that checks:

- The decorated class inherits from `BaseFrameAccessor` (for `kind="frame"`) or `BaseColumnAccessor` (for `kind="column"`)
- The class has an `__init__` method

If validation fails, raise `TypeError` with a message explaining what is wrong and how to fix it.

**Why**: Agents writing incorrect accessor classes currently get generic Python errors at runtime (when the accessor is first accessed). Catching errors at registration time gives immediate, actionable feedback.

#### 2c. `list_registered_accessors()` Helper

Add a public function:

```python
def list_registered_accessors() -> dict[str, dict[str, type]]:
    """Return the current accessor registry.

    Returns a dict mapping accessor names to their registered kinds and classes.
    Example: {"finance": {"frame": FinanceFrameAccessor, "column": FinanceColumnAccessor}}
    """
    return dict(_ACCESSOR_REGISTRY)
```

**Why**: Enables agents to inspect what is available. Lays groundwork for a future `gspio plugins list` command without requiring it now.

### 3. Cross-References

#### 3a. AGENTS.md Addition

Add a section to the existing `AGENTS.md`:

```markdown
## Extending Gaspatchio

To add custom calculations or accessor methods, use the `extending-gaspatchio` skill.
Do not write raw Python loops or `map_elements` — compose Polars expressions.
The accessor pattern (`@register_accessor` + base classes) is the primary extension mechanism.
```

#### 3b. model-building Routing Note

Add a paragraph to the existing `model-building` SKILL.md, in the section where it discusses API usage:

> If the calculation you need does not exist as a built-in method, do not implement it inline with raw Python. Invoke the `extending-gaspatchio` skill to create a proper accessor. This ensures the calculation is reusable, vectorized, and follows the framework's performance patterns.

### 4. Validation Test Cases

The following functions from JuliaActuary serve as validation cases for the skill. If an agent can correctly implement these after reading the skill, the skill works.

#### Should Succeed (Column Accessor)

| Function | Formula | Complexity |
|----------|---------|------------|
| `finance.to_continuous()` | `ln(1 + annual_rate)` | 1 line of Polars `log` |
| `finance.to_effective_annual(n)` | `(1 + r/n)^n - 1` | 1 line of Polars `pow` |
| `finance.duration_macaulay(cashflows, rate)` | `sum(t * cf * v^t) / sum(cf * v^t)` | List column reduction |
| `finance.duration_modified(cashflows, rate)` | `macaulay / (1 + y)` | Wrapper around macaulay |
| `finance.convexity(cashflows, rate)` | `sum(t*(t+1) * cf * v^t) / (P * (1+y)^2)` | Same pattern as macaulay |
| `finance.forward_rate(disc_factors, t1, t2)` | `ln(df1/df2) / (t2-t1)` | Simple log arithmetic |

#### Should Flag for Different Approach

| Function | Why Not an Accessor | What the Agent Should Do Instead |
|----------|---------------------|----------------------------------|
| Nelson-Siegel-Svensson fitting | Needs scipy optimization. Runs once, shared across all policies. | Write a Python utility function in the model's setup phase. Pre-compute the rate vector and store as an assumption column. |
| Monte Carlo simulation | Billions of ops at scale. | Tell the user this needs a Rust kernel contribution. Do not attempt in Python. |
| Life-contingent annuity (full mortality) | Inner loop to omega per policy across millions of policies. | Tell the user this needs a Rust kernel. Suggest using existing `cumulative_survival` + `prospective_value` if the use case fits. |
| Product code categorization | Model-specific logic, not reusable framework code. | Use `when/then/otherwise` or `Table.lookup()` inline in the model. Not an accessor. |

## Deferred Work (Door Left Open)

These items are explicitly out of scope. Nothing in this design blocks them:

| Item | Why Deferred | Prerequisites |
|------|-------------|---------------|
| Entry-point discovery (`gaspatchio.accessors` group) | No demand yet. Current decorator system works. | None — add `discover_accessors()` in `__init__.py` |
| Directory auto-scanning (`gaspatchio_plugins/`) | Simpler than entry points but still packaging infra. | None — add scanner in `__init__.py` |
| `gspio plugin` CLI commands | No plugins to manage yet. | `list_registered_accessors()` (delivered here) |
| Native plugin loading (external `.so` files) | No demand for external Rust plugins. | New `gaspatchio_core.plugins.native` module |
| Plugin manifests (`plugin.toml`) | Only needed for distribution/compatibility. | Entry-point discovery or native plugin loading |

The architectural decision: all extension paths funnel through `register_accessor`. That is the stable contract. Discovery mechanisms are just different ways of finding classes to feed into it.

## Agent Testing Results

The skill was tested against 10 parallel agents with varying tasks. Results:

**10/10 correct performance ladder decisions.** Every agent routed to the correct level.

| Task | Expected | Actual | Result |
|------|----------|--------|--------|
| `to_continuous()` | Level 4 accessor | Level 4 | Pass |
| `duration_macaulay()` | Level 4 accessor | Level 4 | Pass |
| NSS curve fitting | Level 3 setup utility | Level 3 | Pass |
| Monte Carlo simulation | Level 6 flag for Rust | Level 6 | Pass |
| `annuity_due()` | Level 4 accessor | Level 4 | Pass |
| New `risk` namespace | Level 4 new accessor file | Level 4 | Pass |
| Product categorization | Level 2 not accessor | Level 2 | Pass |
| `forward_rate()` | Level 4 accessor | Level 4 | Pass |
| Reserve recursion | Level 1 already exists | Level 1 | Pass |
| Local accessor file | Level 4 local file | Level 4 | Pass |

**Fixes applied from test findings:**

1. Template `ColumnTypeDetector` import path corrected (was `type_detector`, real path is `dispatch`)
2. Template now uses `_get_polars_expr()` helper instead of direct `self._proxy._expr`
3. Template uses `self._proxy.name` (not `._name`)
4. `_parent is None` guard added to template
5. Docstring style corrected to NumPy (was Google)
6. Added `# noqa: SLF001` and `# noqa: N806` suppression guidance
7. Added list-to-scalar reduction pattern (`list.eval(...).list.first()`)
8. Added adjacent-element pattern (`list.eval(pl.element().shift())`)
9. Added `list.eval` external column limitation documentation
10. Expanded local accessor section (was 2 lines, now full worked example with testing)
11. Added early exit path in hard gate for Level 1/2/3/6 decisions
12. Split completion gate: non-accessor vs accessor paths
13. Added mathematical correctness check to completion gate
14. Added sequential dependency decision table (check for existing Rust kernels before flagging)
15. Added reserve recursion and forward rate as decision examples

## Success Criteria

1. An agent reading the `extending-gaspatchio` skill can correctly implement `finance.to_continuous()` as a column accessor without additional guidance — **validated**
2. An agent reading the skill correctly identifies that NSS curve fitting is NOT an accessor — it belongs in model setup — **validated**
3. An agent reading the skill correctly flags Monte Carlo simulation as a Rust contribution, not a Python accessor — **validated**
4. The registry improvements catch incorrect accessor classes at registration time with actionable error messages
5. `list_registered_accessors()` returns the full registry state for inspection
6. The `model-building` skill routes agents to `extending-gaspatchio` when they need a calculation that does not exist
