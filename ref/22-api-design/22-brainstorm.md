# Projection API Brainstorming Session
**Date:** 2025-10-23
**Context:** Refining the projection API design from `22-intro.md` based on the critical tension between convention and control.

## Session Goals

Explore how to design an API that:
1. **Reads like a poetic mathematical formula expressed in English**
2. **Allows actuaries to see and verify the actual calculations** (not trust framework magic)
3. **Is discoverable by LLMs** through clear naming, patterns, and rich documentation
4. **Balances convenience with escape hatches** for custom logic

## The Critical Design Tension

### The Problem
See `22-intro.md` sections on "Projection and Inforce Management" - the original vision included higher-level abstractions like:
```python
af = af.projection.project_cashflows(periods=30)
af.inforce_by_year = af.projection.rollforward(initial=1, rate_col=af.annual_persistency)
```

**But actuaries are mathematicians**, not software engineers. They need to:
- **Audit every calculation** for regulatory compliance
- **Understand the formulas** without reading framework source code
- **Modify logic** when edge cases arise (premium holidays, surrender charges, etc.)

**The tension:** "Not code" vs "What is Polars" vs "Just show me the actual calculation"

### The Insight: Worksheet + Domain Methods

Combine:
- **Worksheet metaphor** (familiar from Excel) - column-by-column definitions
- **Domain namespacing** (from `22-intro.md`) - `.projection`, `.mortality`, `.finance`
- **Verb-based method names** that describe actuarial intent

**Result:** Code that reads like building an Excel worksheet, but with clear domain-specific operations.

## The Emerging Pattern: "Excel Columns + Domain Methods"

### Example: Complete Projection Workflow

```python
# Lookup assumptions
af.qx = af.issue_age.mortality.qx(table="BaseMortality")
af.lapse_rate = af.duration.assumptions.lookup(table="LapseRates")

# Calculate cumulative survival: (1-q₀)×(1-q₁)×...×(1-qₜ)
af.survival_to_t = af.qx.projection.cumulative_survival()

# Death benefits = Face Amount × qₜ × Survival to t
af.death_benefit = af.face_amount * af.qx * af.survival_to_t

# Premiums while inforce = Annual Premium × Survival to t
af.premium = af.annual_premium * af.survival_to_t

# Maturity benefit = Face Amount × Survival to end
af.maturity_benefit = af.face_amount * af.survival_to_t.list.last()
```

### Why This Works

### Why This Works

**For Actuaries:**
- ✅ **The math is visible**: `af.face_amount * af.qx * af.survival_to_t` is exactly the formula
- ✅ **Named operations when needed**: `.cumulative_survival()` for complex operations
- ✅ **Simple operators when obvious**: `*` for multiplication, no method calls needed
- ✅ **Reads like a formula**: each line is a mathematical expression
- ✅ **Audit trail**: the calculation IS the code

**For LLMs:**
- ✅ **Pattern-based**: Simple math uses operators, complex operations use methods
- ✅ **Discoverable**: `af.qx.projection.<TAB>` shows available operations
- ✅ **Self-documenting**: `.cumulative_survival()` tells you what it does
- ✅ **Compositional**: Mix operators and methods naturally

**Key Insight:**
- **Complex operations** (cumulative product, discounting) → Use named methods
- **Simple operations** (multiplication, addition) → Use operators directly
- **Result:** Reads like writing formulas in Excel or a textbook

## Deep Dive: Implementation Examples

### Example 1: Simple Cashflows - Just Use Operators

For simple multiplication/division, just write the formula directly:

**The Formula:**
```python
# Death benefits = Face Amount × qₜ × Survival to t
af.death_benefit = af.face_amount * af.qx * af.survival_to_t

# Premiums while inforce = Annual Premium × Survival to t
af.premium = af.annual_premium * af.survival_to_t
```

**Why This Works:**
- The formula IS the code
- No method calls needed for simple math
- List columns are handled automatically (element-wise multiplication)
- Reads exactly like an Excel formula or textbook equation

**Actuarial operators work naturally:**
```python
# Net cashflow
af.net_cashflow = af.premium - af.death_benefit - af.expenses

# Present value
af.pv_cashflow = af.net_cashflow * af.discount_factors

# With loading factor
af.loaded_premium = af.premium * (1 + af.loading_factor)
```

### Example 2: `.cumulative_survival()` - Build Survival Curves

**Usage:**
```python
af.survival_to_t = af.qx.projection.cumulative_survival()
```

**What It Does:**
Converts mortality rates to cumulative survival: `survival[t] = (1-qx[0]) * (1-qx[1]) * ... * (1-qx[t])`

**Internal Implementation:**
```python
def cumulative_survival(self):
    """Calculate cumulative survival probabilities from mortality rates."""
    qx_expr = self._get_base_expr()
    is_list_col = self._is_list_column()

    if is_list_col:
        # For list columns: apply cumulative product within each list
        survival_expr = qx_expr.list.eval(
            (1 - pl.element()).cum_prod()
        )
    else:
        # For scalar columns: apply cumulative product across rows
        # User should chain with .over() if grouping is needed
        survival_expr = (1 - qx_expr).cum_prod()

    return ExpressionProxy(survival_expr, self._parent_frame)
```

**The Polars Expression (List Column Case):**
```python
# Input: [[0.001, 0.0011, 0.0012], [0.002, 0.0022, 0.0024]]

# Step 1: (1 - qx) for each element
# Result: [[0.999, 0.9989, 0.9988], [0.998, 0.9978, 0.9976]]

# Step 2: Cumulative product within each list
# Result: [[0.999, 0.997901, 0.996704], [0.998, 0.995804, 0.993415]]

# Polars expression:
qx_expr.list.eval((1 - pl.element()).cum_prod())
```

**For Scalar Columns (Exploded Data):**
```python
# User must add grouping:
af.survival_to_t = (
    af.qx.projection.cumulative_survival()
    .over("policy_id")  # Partitions cumulative product by policy
)
```

## Evolution from `22-intro.md`

### What Stayed the Same
-  Domain namespacing (`.projection`, `.mortality`, `.finance`)
-  Frame vs column accessors
-  Immutable/functional style
-  LLM-ready design with rich documentation

### What Evolved

| Original Vision (`22-intro.md`) | New Direction (Brainstorming) | Why |
|--------------------------------|------------------------------|-----|
| High-level: `.project_cashflows(periods=30)` | Explicit steps: `.on_decrement()`, `.while_inforce()` | Actuaries need to see each calculation step |
| Abstract: `.rollforward(initial=1, rate_col=...)` | Named patterns: `.cumulative_survival()`, `.cumulative_discount()` | Method names describe actuarial meaning |
| Magic convenience | Transparent formulas | "Show me the calculation" trumps "do it for me" |
| Few big methods | Many small composable methods | Easier to discover, understand, and customize |

**The Shift:** From "Rails magic" to "Excel transparency with domain helpers"

## Escape Hatches: Convention Breaking

When convention doesn't fit, users have clear options:

### Option 1: Custom Column Logic
```python
# Premium holiday in year 5 - just override the column:
af.premium = af.annual_premium.projection.while_inforce(
    inforce=af.survival_to_t
)
# Custom adjustment: set year 5 premiums to zero
af.premium = af.premium.projection.set_at_period(period=5, value=0)
```

### Option 2: Raw Formula Application
```python
# Completely custom logic - just write Polars:
af.complex_benefit = (
    af.face_amount * 1.05.pow(af.t).when(af.t < 10)
    .otherwise(af.face_amount * 2.0)
)
```

### Option 3: Drop to Polars for Power Users
```python
# Full Polars control if needed:
underlying_df = af.to_polars()
underlying_df = underlying_df.with_columns([
    # raw Polars expressions
])
af = ActuarialFrame.from_polars(underlying_df)
```

## Outstanding Questions

### 1. Timing Conventions
**Question:** Should `inforce` in `.on_decrement()` represent:
- **Option A**: Count at START of period (before decrement)?
- **Option B**: Count at END of period (after decrement)?

**Impact:** This affects whether calculations use `inforce[t]` or `inforce[t-1]`.

**Recommendation Needed:** What's the actuarial convention?

### 2. Grouping Strategy for Scalar Columns
**Question:** For `.cumulative_survival()` on scalar columns, should we:
- **Option A**: Return ungrouped (user adds `.over()` as needed) � Currently shown
- **Option B**: Require a `by` parameter: `cumulative_survival(by="policy_id")`
- **Option C**: Auto-detect common grouping columns and warn if not grouped

**Trade-offs:**
- Option A: Most flexible, but user must know to add `.over()`
- Option B: More explicit, but verbose
- Option C: "Magic" detection might surprise users

### 3. Starting Values for Cumulative Calculations
**Question:** Should survival curves start at:
- **Option A**: `[0.999, 0.997901, ...]` (starts after first period mortality) � Current
- **Option B**: `[1.0, 0.999, 0.997901, ...]` (includes starting point before any mortality)

**Impact:** Affects alignment with time indices and premium/benefit calculations.

### 4. Naming Conventions
**Questions:**
- Is `.on_decrement()` clear enough, or `.cashflow_on_decrement()`?
- Is `.cumulative_survival()` good, or `.survival_curve()`, `.tpx()`, `.cumulative_px()`?
- Should we use actuarial notation (`.tpx()`, `.nEx()`) or English (`.survival_probability()`, `.life_annuity()`)?

**Tension:** Actuarial precision vs LLM/beginner friendliness

### 5. Other Projection Methods Needed
Should we add similar methods for:
-  `.on_decrement()` - cashflows when decrement occurs (DONE)
-  `.cumulative_survival()` - build survival curves (DONE)
- � `.while_inforce()` - cashflows while policies are active (premiums)
- � `.at_maturity()` - cashflows at end of term
- � `.on_surrender()` - specific to surrender with cash values
- � `.cumulative_discount()` - compound discount factors
- � `.cumulative_inforce()` - apply all decrements together
- � `.set_at_period()` - override specific periods (premium holidays, etc.)

## What Next

### Immediate Next Steps
1. **Answer Outstanding Questions** - need actuarial SME input on conventions
2. **Complete Accessor Design** - implement the full set of `.projection` methods
3. **Validate with Real Models** - test the API with actual actuarial use cases
4. **Documentation** - write comprehensive docstrings with examples for each method

### Design Documentation Path
Following the brainstorming skill workflow:
-  **Phase 1: Understanding** - Gathered purpose, constraints, criteria
-  **Phase 2: Exploration** - Explored worksheet + domain namespace pattern
-  **Phase 3: Design Presentation** - Validated with concrete examples
- = **Phase 4: Design Documentation** - This document! (22-brainstorm.md)
- � **Phase 5: Worktree Setup** - If implementing, set up isolated workspace
- � **Phase 6: Planning Handoff** - Create detailed implementation plan

### Implementation Approach
If we proceed to implement:
1. Create git worktree for isolated development
2. Start with core projection methods (`.on_decrement()`, `.cumulative_survival()`)
3. Add comprehensive docstring examples (verified by pytest)
4. Build out remaining methods incrementally
5. Test with real actuarial models from gaspatchio-models

## References

- **Original Vision**: `ref/22-api-design/22-intro.md` - Rails-inspired API philosophy
- **Current Codebase**:
  - `gaspatchio_core/frame/base.py` - ActuarialFrame implementation
  - `gaspatchio_core/column/dispatch.py` - Proxy pattern and list shimming
  - `gaspatchio_core/accessors/date.py` - Example accessor implementation
- **Existing Patterns**: Date accessor shows the frame vs column accessor pattern we're extending

## Key Takeaway

**The "code IS the formula" pattern:**

Write actuarial formulas using a natural mix of operators and named methods:

| Formula Type | Code Pattern | Example |
|--------------|--------------|---------|
| **Simple math** (multiply, add, subtract) | Use operators directly | `af.death_benefit = af.face_amount * af.qx * af.survival_to_t` |
| **Complex operations** (cumulative product, discounting) | Use named methods | `af.survival_to_t = af.qx.projection.cumulative_survival()` |
| **Lookups** (assumptions, tables) | Use domain accessors | `af.qx = af.issue_age.mortality.qx(table="BaseMortality")` |

**NOT this (too much abstraction):**
```python
af = af.projection.project_cashflows(periods=30)  # What formula is this?
```

**THIS (the formula IS the code):**
```python
# Cumulative survival: (1-q₀)×(1-q₁)×...×(1-qₜ)
af.survival_to_t = af.qx.projection.cumulative_survival()

# Death benefits: Face Amount × qₜ × Survival to t
af.death_benefit = af.face_amount * af.qx * af.survival_to_t

# Premiums: Annual Premium × Survival to t
af.premium = af.annual_premium * af.survival_to_t

# Net cashflow
af.net_cashflow = af.premium - af.death_benefit - af.expenses
```

**The Pattern:**
- ✅ **Operators for obvious math** - multiplication, division, addition, subtraction
- ✅ **Methods for complex operations** - cumulative products, discounting, rolling forward
- ✅ **Domain accessors for lookups** - mortality tables, lapse rates, assumptions
- ✅ **The code reads like the textbook formula** - no hidden complexity

Each line is:
- **A mathematical expression** - not a method call hiding the formula
- **Auditable** - actuary can verify by reading the code
- **Composable** - mix operators and methods naturally
- **Excel-like** - write formulas the way you think about them

This is the balance between convention and control.
