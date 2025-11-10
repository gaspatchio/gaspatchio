# ProjectionColumnAccessor Design Brainstorming
**Date:** 2025-11-10
**Focus:** Deep dive into accessor naming, method design, and API philosophy
**Related:** `22-brainstorm.md`, `22-implementation-plan.md`

## Research: JuliaActuary's Approach

### What We Learned from LifeContingencies.jl

**1. Dual-Naming Strategy**
- **Long-form:** `AnnuityDue()`, `Insurance()`, `premium_net()`
- **Unicode shorthand:** `ä()`, `A`, `V()`, `P`
- **Philosophy:** Avoid namespace collisions while enabling mathematical elegance

**2. Function Organization**
```julia
# They use plain functions, not accessors:
survival(ins)              # Full survival vector
survival(ins, time)        # Survivorship through specific time
survival(mort, from, to)   # Survival between ages

decrement(mort, from, to)  # Decrement between ages

# Present value operations
present_value(ins)         # APV from time zero
present_value(ins, time)   # APV from specified time
```

**3. Key Design Principles**
- ✅ **Mathematical notation alignment** - Unicode enables textbook-like expressions
- ✅ **Lazy evaluation** - Return generators for memory efficiency
- ✅ **Modularity** - Separate mortality (`MortalityTables.jl`), interest (`FinanceModels.jl`), and contingencies
- ✅ **Explicit imports** - Users opt-in to shorthand: `import LifeContingencies: V, ä`
- ✅ **Plain English names** - `survival()` and `decrement()` vs traditional `tpx`, `qx` notation

**4. What They DON'T Use**
- ❌ No `.projection` namespace
- ❌ No method chaining like `af.qx.projection.cumulative_survival()`
- ❌ No accessor pattern (they use standalone functions)
- ❌ Limited use of traditional actuarial notation (`tpx`, `qx`) - prefer English

**5. Commutation Functions**
- They do provide `D(x)`, `M(x)`, `N(x)`, `C(x)`, `l(x)` for traditional actuaries
- BUT these are not the primary API - they're secondary helpers

---

## Our Design Goals (Revisited)

1. **Reads like a poetic mathematical formula expressed in English**
   - Code should read like textbook formulas
   - Prefer `af.death_benefit = af.face_amount * af.qx * af.survival` over magic methods

2. **Allows actuaries to see and verify the actual calculations**
   - No hidden framework magic
   - Each step should be explicit and auditable

3. **Is discoverable by LLMs**
   - Clear naming patterns
   - Rich documentation
   - Autocomplete-friendly namespaces

4. **Balances convenience with escape hatches**
   - Convention: helpers for common patterns
   - Escape: can always drop to Polars expressions

---

## The Fundamental Question: What IS This Accessor About?

Let's brainstorm: what is the **essence** of what we're building?

### Option A: `.projection` - Projection Operations

**Rationale:** Methods for projecting values forward in time
```python
af.survival_to_t = af.qx.projection.cumulative_survival()
af.discount_factors = af.interest_rate.projection.cumulative_discount()
af.premium_holiday = af.premium.projection.set_at_period(5, 0)
```

**Pros:**
- Clearly about temporal operations
- Intuitive for "projecting into the future"
- Aligns with "projection period" terminology

**Cons:**
- "Projection" is a bit generic
- Could be confused with "projecting" as in selecting columns
- Doesn't capture the "cumulative" nature of some operations

---

### Option B: `.survival` - Survival Analysis Operations

**Rationale:** Inspired by JuliaActuary's `survival()` function
```python
af.survival_to_t = af.qx.survival.cumulative()
af.survival_prob_10y = af.qx.survival.through(periods=10)
```

**Pros:**
- **Very clear** - this is about survival probabilities
- Matches statistical survival analysis terminology
- JuliaActuary validation

**Cons:**
- Too narrow - what about discount factors? Premium holidays?
- Doesn't cover all the methods we need
- Might confuse actuaries vs statisticians

---

### Option C: `.series` - Time Series Operations

**Rationale:** Operations on series of values over time
```python
af.survival_to_t = af.qx.series.cumulative_product(transform=lambda x: 1-x)
af.discount_factors = af.rates.series.cumulative_discount()
af.adjusted = af.premiums.series.set_at(period=5, value=0)
```

**Pros:**
- Accurately describes what we're doing (time series ops)
- Flexible for various operations
- Familiar to data scientists

**Cons:**
- Less actuarial - generic data science term
- Loses domain specificity
- `.series.cumulative_product(transform=lambda x: 1-x)` is NOT poetic

---

### Option D: `.cumulative` - Cumulative Operations

**Rationale:** Focus on cumulative calculations
```python
af.survival_to_t = af.qx.cumulative.survival()
af.discount_factors = af.rates.cumulative.discount()
af.present_value = af.cashflows.cumulative.discounted_sum()
```

**Pros:**
- Describes the main operation type
- Clear that values accumulate
- Short and memorable

**Cons:**
- What about non-cumulative operations like `set_at_period()`?
- Doesn't capture the projection/time aspect
- Might be confused with cumulative sum

---

### Option E: `.lifecycle` - Policy/Life Lifecycle Operations

**Rationale:** Operations across the lifecycle of a policy or life
```python
af.survival_to_t = af.qx.lifecycle.cumulative_survival()
af.inforce = af.qx.lifecycle.decrement_based_inforce()
af.maturity_benefit = af.face_amount.lifecycle.at_maturity()
```

**Pros:**
- Captures the temporal nature
- Very intuitive for insurance contexts
- Encompasses birth-to-death or issue-to-maturity

**Cons:**
- Might be confused with product lifecycle (different concept)
- Longer word
- Less mathematical, more business-oriented

---

### Option F: No Accessor - Plain Methods on Column

**Rationale:** Like JuliaActuary, just have methods directly on the column proxy
```python
af.survival_to_t = af.qx.cumulative_survival()
af.discount_factors = af.rates.cumulative_discount()
af.at_maturity = af.face_amount.terminal_value()
```

**Pros:**
- Simplest - no namespace needed
- Most direct - fewer dots
- JuliaActuary-style

**Cons:**
- **Namespace pollution** - all methods on every column
- **Discoverability issues** - hard to know what's available
- **Conflicts** - `cumulative_survival()` on a premium column?
- **No organization** - methods scattered

---

### Option G: `.actuarial` - Actuarial Operations

**Rationale:** General namespace for actuarial-specific operations
```python
af.survival_to_t = af.qx.actuarial.cumulative_survival()
af.tpx = af.qx.actuarial.t_year_survival(t=10)
af.present_value = af.cashflows.actuarial.discount(rates=af.v)
```

**Pros:**
- Clear domain signal
- Flexible for various actuarial operations
- Professional and familiar

**Cons:**
- Too broad - what ISN'T actuarial in an actuarial framework?
- Doesn't help with discoverability (too many things could be "actuarial")
- Redundant - the whole framework is actuarial

---

## Comparison Matrix

| Accessor Name | Semantic Clarity | Scope Fit | Discoverable | Poetic | Actuarial Fit |
|--------------|------------------|-----------|--------------|--------|---------------|
| `.projection` | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| `.survival` | ⭐⭐⭐⭐⭐ | ⭐⭐ (too narrow) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| `.series` | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| `.cumulative` | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| `.lifecycle` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| No accessor | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| `.actuarial` | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## Method Naming: Traditional vs Modern

### The Traditional Actuarial Notation

**Classic symbols:**
- `tpx` - probability age x survives t years
- `qx` - probability of death at age x
- `px` - probability of survival at age x
- `lx` - number living at age x
- `dx` - number dying at age x
- `nEx` - n-year endowment factor
- `ä` - annuity due
- `A` - insurance present value

**Pros:**
- ✅ Familiar to trained actuaries
- ✅ Concise
- ✅ Mathematically precise

**Cons:**
- ❌ Opaque to non-actuaries
- ❌ Hard for LLMs to reason about
- ❌ Difficult to autocomplete
- ❌ Not self-documenting

### The Modern English Approach

**JuliaActuary style:**
- `survival(mort, from, to)` instead of `tpx`
- `decrement(mort, from, to)` instead of `qx`
- `present_value(ins)` instead of `A`
- `premium_net(lc)` instead of `P`

**Hybrid approach (they do both):**
- Long form: `AnnuityDue()`, `Insurance()`
- Shorthand: `ä()`, `A`

**Pros:**
- ✅ Self-documenting
- ✅ LLM-friendly
- ✅ Discoverable via autocomplete
- ✅ Approachable for Python developers

**Cons:**
- ❌ Longer to type
- ❌ Less concise than traditional notation
- ❌ Some actuaries may prefer traditional

---

## Proposed Method Names - Detailed Exploration

### Method 1: Cumulative Survival

**What it does:** Converts mortality rates (qx) into cumulative survival probabilities

**Formula:** `survival[t] = (1-qx[0]) × (1-qx[1]) × ... × (1-qx[t])`

**Options:**

#### Option 1a: `cumulative_survival()`
```python
af.survival_to_t = af.qx.projection.cumulative_survival()
```
**Assessment:**
- ✅ Very clear what it does
- ✅ Self-documenting
- ✅ Discoverable
- ⚠️ Verbose

#### Option 1b: `survival()`
```python
af.survival_to_t = af.qx.projection.survival()
```
**Assessment:**
- ✅ Concise
- ✅ Matches JuliaActuary
- ⚠️ Ambiguous - survival probability at one age or cumulative?
- ⚠️ Needs context from accessor name

#### Option 1c: `to_survival_curve()`
```python
af.survival_curve = af.qx.projection.to_survival_curve()
```
**Assessment:**
- ✅ Very descriptive
- ✅ Clear about creating a curve/series
- ✅ Matches statistical terminology
- ⚠️ Long

#### Option 1d: `survive()` (verb form)
```python
af.survival_to_t = af.qx.projection.survive()
```
**Assessment:**
- ✅ Natural English verb
- ✅ Short
- ⚠️ Might be confused with a filter operation
- ⚠️ Less precise than "cumulative_survival"

#### Option 1e: `tpx()` (traditional notation)
```python
af.tpx = af.qx.projection.tpx()
```
**Assessment:**
- ✅ Familiar to actuaries
- ✅ Very concise
- ❌ Opaque to non-actuaries
- ❌ Not LLM-friendly

---

### Method 2: Cashflows on Decrement

**What it does:** Calculate cashflows that occur when a decrement happens

**Formula:** `cashflow × inforce × decrement_rate`

**Options:**

#### Option 2a: `on_decrement(inforce)`
```python
af.death_benefit = af.face_amount.projection.on_decrement(af.survival_to_t) * af.qx
```
**Assessment:**
- ✅ Very clear timing ("on" decrement = when it happens)
- ✅ Grammatically natural
- ⚠️ Requires caller to multiply by decrement rate

#### Option 2b: `at_decrement(inforce, rate)`
```python
af.death_benefit = af.face_amount.projection.at_decrement(af.survival_to_t, af.qx)
```
**Assessment:**
- ✅ Even clearer timing
- ✅ More complete (includes rate)
- ⚠️ More parameters

#### Option 2c: `decrement_benefit(inforce, rate)`
```python
af.death_benefit = af.face_amount.projection.decrement_benefit(af.survival_to_t, af.qx)
```
**Assessment:**
- ✅ Very explicit about purpose
- ✅ Self-contained
- ⚠️ Assumes "benefit" - what about expenses on decrement?

#### Option 2d: `when_decrement(inforce)`
```python
af.death_benefit = af.face_amount.projection.when_decrement(af.survival_to_t) * af.qx
```
**Assessment:**
- ✅ Most natural English
- ✅ Reads poetically: "face amount when decrement occurs"
- ✅ Flexible (works for benefits or expenses)
- ⚠️ Requires multiplication by rate

---

### Method 3: Cashflows While Inforce

**What it does:** Calculate cashflows that occur while policies are active

**Formula:** `cashflow × inforce`

**Options:**

#### Option 3a: `while_inforce(inforce)`
```python
af.premium = af.annual_premium.projection.while_inforce(af.survival_to_t)
```
**Assessment:**
- ✅ Crystal clear timing
- ✅ Reads like English: "annual premium while inforce"
- ✅ Grammatically correct

#### Option 3b: `when_inforce(inforce)`
```python
af.premium = af.annual_premium.projection.when_inforce(af.survival_to_t)
```
**Assessment:**
- ✅ Also clear
- ⚠️ Less specific than "while" (could mean a single point vs duration)

#### Option 3c: `apply_inforce(inforce)`
```python
af.premium = af.annual_premium.projection.apply_inforce(af.survival_to_t)
```
**Assessment:**
- ✅ Functional/technical
- ⚠️ Less poetic
- ⚠️ "Apply" is vague

#### Option 3d: Just use multiplication (no method)
```python
af.premium = af.annual_premium * af.survival_to_t
```
**Assessment:**
- ✅ Most concise
- ✅ Very clear (it's just multiplication)
- ✅ Follows our "simple math = operators" principle
- ✅✅✅ **THIS IS THE WAY** - no method needed!

---

### Method 4: Cumulative Discount

**What it does:** Calculate cumulative discount factors

**Formula:** `discount[t] = 1/(1+r[0]) × 1/(1+r[1]) × ... × 1/(1+r[t])`

**Options:**

#### Option 4a: `cumulative_discount()`
```python
af.discount_factors = af.interest_rate.projection.cumulative_discount()
```
**Assessment:**
- ✅ Clear and descriptive
- ✅ Parallel to `cumulative_survival()`

#### Option 4b: `to_discount_factors()`
```python
af.discount_factors = af.interest_rate.projection.to_discount_factors()
```
**Assessment:**
- ✅ Describes transformation
- ✅ Clear output

#### Option 4c: `vt()` (traditional notation)
```python
af.vt = af.interest_rate.projection.vt()
```
**Assessment:**
- ✅ Familiar to actuaries (v = discount factor)
- ❌ Opaque to others

#### Option 4d: `discount()` (simple form)
```python
af.discount_factors = af.interest_rate.projection.discount()
```
**Assessment:**
- ✅ Concise
- ⚠️ Ambiguous - single period or cumulative?

---

### Method 5: Value at Maturity/Terminal

**What it does:** Extract the last value from a series

**Formula:** For list columns: `list.last()`, for scalar: use with grouping

**Options:**

#### Option 5a: `at_maturity()`
```python
af.maturity_benefit = af.face_amount.projection.at_maturity()
```
**Assessment:**
- ✅ Very clear timing
- ✅ Insurance-specific terminology
- ⚠️ Assumes maturity context

#### Option 5b: `terminal_value()`
```python
af.terminal_value = af.benefit.projection.terminal_value()
```
**Assessment:**
- ✅ Finance-standard term
- ✅ More general than "maturity"
- ✅ Works for any ending value

#### Option 5c: `final()`
```python
af.final_benefit = af.benefit.projection.final()
```
**Assessment:**
- ✅ Very concise
- ✅ Clear
- ⚠️ Generic

#### Option 5d: Just use `.list.last()`
```python
af.maturity_benefit = af.face_amount.list.last()
```
**Assessment:**
- ✅ Most direct
- ✅ Leverages existing Polars functionality
- ✅ No new method needed
- ✅✅✅ **THIS IS THE WAY** - use Polars directly!

---

### Method 6: Set Value at Specific Period

**What it does:** Override a value at a specific time period

**Use case:** Premium holidays, benefit changes

**Options:**

#### Option 6a: `set_at_period(period, value)`
```python
af.premium_adjusted = af.premium.projection.set_at_period(5, 0)
```
**Assessment:**
- ✅ Very explicit
- ✅ Clear parameters
- ⚠️ Verbose

#### Option 6b: `override_at(period, value)`
```python
af.premium_adjusted = af.premium.projection.override_at(5, 0)
```
**Assessment:**
- ✅ "Override" clearly indicates replacing
- ✅ Concise

#### Option 6c: `adjust(period, value)`
```python
af.premium_adjusted = af.premium.projection.adjust(5, 0)
```
**Assessment:**
- ✅ Short
- ⚠️ "Adjust" is ambiguous (set or modify?)

#### Option 6d: `with_period(period, value)`
```python
af.premium_adjusted = af.premium.projection.with_period(5, 0)
```
**Assessment:**
- ✅ Reads naturally: "premium with period 5 set to 0"
- ✅ Functional style (with_*)
- ✅ Common pattern in many APIs

---

## Recommended Design: The "Poetic Formula" Approach

After analyzing JuliaActuary and considering our design goals, here's my recommendation:

### Accessor Name: `.projection`

**Why:**
1. ✅ Clear domain - it's about projecting values through time
2. ✅ Familiar to actuaries - "projection period" is standard terminology
3. ✅ Broad enough to encompass all our methods
4. ✅ Specific enough to be meaningful
5. ✅ Discoverable - `af.qx.projection.<TAB>` shows relevant operations

**Alternative considered:** `.lifecycle` is a close second, but "projection" is more mathematically precise.

---

### Method Names: Hybrid Approach

**Principle:** Use clear English names by default, but optimize for readability

#### Core Methods (KEEP):

1. **`cumulative_survival()`** - Convert qx to cumulative survival
   ```python
   af.survival_to_t = af.qx.projection.cumulative_survival()
   ```
   - ✅ Clear and self-documenting
   - ✅ Discoverable
   - ✅ The extra length is worth the clarity

2. **`cumulative_discount()`** - Convert rates to discount factors
   ```python
   af.discount_factors = af.interest_rate.projection.cumulative_discount()
   ```
   - ✅ Parallel naming to `cumulative_survival()`
   - ✅ Clear transformation

3. **`with_period(period, value)`** - Override value at period
   ```python
   af.premium_holiday = af.premium.projection.with_period(5, 0)
   ```
   - ✅ Reads poetically
   - ✅ Functional style
   - ✅ Common pattern

#### Methods to REMOVE (use operators/Polars instead):

1. ~~`while_inforce()`~~ → Just use multiplication
   ```python
   # Instead of: af.premium = af.annual_premium.projection.while_inforce(af.survival)
   # Use:
   af.premium = af.annual_premium * af.survival_to_t
   ```
   - ✅ Simpler
   - ✅ More transparent
   - ✅ Follows "simple math = operators" principle

2. ~~`on_decrement()`~~ → Just use multiplication
   ```python
   # Instead of: af.death_benefit = af.face.projection.on_decrement(af.survival) * af.qx
   # Use:
   af.death_benefit = af.face_amount * af.survival_to_t * af.qx
   ```
   - ✅ The formula IS the code
   - ✅ Completely transparent
   - ✅ Auditable

3. ~~`at_maturity()`~~ → Use `.list.last()` or `.list.get(-1)`
   ```python
   # Instead of: af.maturity_benefit = af.face.projection.at_maturity()
   # Use:
   af.maturity_benefit = af.face_amount.list.last()
   ```
   - ✅ Leverages Polars
   - ✅ No new method needed
   - ✅ Clear intent

---

## The Minimal Viable API

Based on the "poetic formula" principle, here's what we ACTUALLY need:

### ProjectionColumnAccessor - Final Design

```python
@register_accessor("projection", kind="column")
class ProjectionColumnAccessor(BaseColumnAccessor):
    """
    Actuarial projection operations for time-series calculations.

    This accessor provides methods for transforming rates and probabilities
    into cumulative values over projection periods. For simple operations like
    multiplication or taking the last value, use standard operators and
    Polars methods instead.

    Examples:
        ```python
        # Cumulative survival from mortality rates
        af.survival_to_t = af.qx.projection.cumulative_survival()

        # Cumulative discount factors from interest rates
        af.discount_factors = af.rate.projection.cumulative_discount()

        # Premium holiday at period 5
        af.premium_adj = af.premium.projection.with_period(5, value=0)

        # Simple operations use operators:
        af.death_benefit = af.face_amount * af.survival_to_t * af.qx
        af.premium = af.annual_premium * af.survival_to_t

        # Terminal values use Polars:
        af.maturity_benefit = af.face_amount.list.last()
        ```
    """

    def cumulative_survival(self) -> ExpressionProxy:
        """Convert mortality rates to cumulative survival probabilities.

        Applies the formula: survival[t] = (1-qx[0]) × (1-qx[1]) × ... × (1-qx[t])

        For list columns, applies element-wise within each list.
        For scalar columns, applies across rows (use .over() for grouping).

        Returns:
            ExpressionProxy: Cumulative survival probabilities

        Examples:
            ```python
            from gaspatchio_core import ActuarialFrame

            data = {
                "qx": [[0.001, 0.0011, 0.0012], [0.002, 0.0022, 0.0024]]
            }
            af = ActuarialFrame(data)

            af.survival_to_t = af.qx.projection.cumulative_survival()

            # Use in cashflow calculations:
            af.death_benefit = af.face_amount * af.qx * af.survival_to_t
            af.premium = af.annual_premium * af.survival_to_t
            ```
        """
        pass

    def cumulative_discount(self, mode: Literal["compound", "simple"] = "compound") -> ExpressionProxy:
        """Convert interest rates to cumulative discount factors.

        Applies the formula:
        - Compound: discount[t] = 1/[(1+r[0]) × (1+r[1]) × ... × (1+r[t])]
        - Simple: discount[t] = 1/(1 + r × t)

        For list columns, applies element-wise within each list.
        For scalar columns, applies across rows (use .over() for grouping).

        Args:
            mode: "compound" for compound interest (default), "simple" for simple interest

        Returns:
            ExpressionProxy: Cumulative discount factors

        Examples:
            ```python
            from gaspatchio_core import ActuarialFrame

            data = {
                "interest_rate": [[0.05, 0.05, 0.05]]  # 5% per period
            }
            af = ActuarialFrame(data)

            af.v = af.interest_rate.projection.cumulative_discount()

            # Apply to cashflows:
            af.pv_cashflow = af.net_cashflow * af.v
            ```
        """
        pass

    def with_period(self, period: int, value: Any) -> ExpressionProxy:
        """Override value at a specific period (zero-indexed).

        Creates a modified version of the series with a specific period
        set to a new value. Useful for modeling discontinuities like
        premium holidays, benefit changes, or other events at known times.

        Args:
            period: Zero-based index of period to modify
            value: Value to set at that period

        Returns:
            ExpressionProxy: Modified series with value changed at specified period

        Examples:
            ```python
            from gaspatchio_core import ActuarialFrame

            data = {
                "premium": [[1000, 1000, 1000, 1000, 1000]]
            }
            af = ActuarialFrame(data)

            # Premium holiday in period 3 (4th element)
            af.premium_with_holiday = af.premium.projection.with_period(3, value=0)

            print(af.collect())
            # premium_with_holiday: [1000, 1000, 1000, 0, 1000]
            ```
        """
        pass

    def with_periods(self, updates: dict[int, Any]) -> ExpressionProxy:
        """Override values at multiple specific periods.

        Like with_period() but accepts a dictionary of period->value mappings
        for multiple updates in one operation.

        Args:
            updates: Dictionary mapping period indices to new values

        Returns:
            ExpressionProxy: Modified series with values changed at specified periods

        Examples:
            ```python
            from gaspatchio_core import ActuarialFrame

            data = {
                "premium": [[1000, 1000, 1000, 1000, 1000]]
            }
            af = ActuarialFrame(data)

            # Premium holidays in periods 2 and 4
            af.premium_adj = af.premium.projection.with_periods({2: 0, 4: 0})

            print(af.collect())
            # premium_adj: [1000, 1000, 0, 1000, 0]
            ```
        """
        pass
```

---

## What We're NOT Building (And Why)

### ❌ `.projection.on_decrement()`

**Reason:** It's just multiplication. The formula IS the code:
```python
# Not this:
af.death_benefit = af.face_amount.projection.on_decrement(af.survival_to_t) * af.qx

# This:
af.death_benefit = af.face_amount * af.survival_to_t * af.qx
```

### ❌ `.projection.while_inforce()`

**Reason:** Also just multiplication:
```python
# Not this:
af.premium = af.annual_premium.projection.while_inforce(af.survival_to_t)

# This:
af.premium = af.annual_premium * af.survival_to_t
```

### ❌ `.projection.at_maturity()`

**Reason:** Polars already has this:
```python
# Not this:
af.maturity_benefit = af.face_amount.projection.at_maturity()

# This:
af.maturity_benefit = af.face_amount.list.last()
```

### ❌ `.projection.sum_over_periods()`

**Reason:** Polars has `.list.sum()`:
```python
# Not this:
af.total_premium = af.premium.projection.sum_over_periods()

# This:
af.total_premium = af.premium.list.sum()
```

---

## Complete Example: Term Life Insurance Projection

Here's how the final API would look in practice:

```python
import datetime
from gaspatchio_core import ActuarialFrame

# Setup policy data
data = {
    "policy_id": [1, 2],
    "issue_age": [30, 45],
    "face_amount": [100000, 250000],
    "annual_premium": [500, 1250],
    "policy_term": [20, 15]
}
af = ActuarialFrame(data)

# Create projection timeline
af = af.date.create_projection_timeline(
    valuation_date=datetime.date(2024, 1, 1),
    projection_end_type="term_years",
    projection_end_value=20,
    projection_frequency="annual"
)

# Lookup assumptions (future accessor)
af.qx = af.issue_age.mortality.qx(table="2015VBT")
af.interest_rate = af.duration.assumptions.lookup(table="InterestRates")

# Calculate cumulative values using .projection accessor
af.survival_to_t = af.qx.projection.cumulative_survival()
af.discount_factors = af.interest_rate.projection.cumulative_discount()

# Calculate cashflows using simple operators (the formula IS the code)
af.death_benefit = af.face_amount * af.qx * af.survival_to_t
af.premium = af.annual_premium * af.survival_to_t

# Model premium holiday in year 5
af.premium = af.premium.projection.with_period(5, value=0)

# Net cashflow (operators!)
af.net_cashflow = af.premium - af.death_benefit

# Present value (operators!)
af.pv_cashflow = af.net_cashflow * af.discount_factors

# Maturity benefit (Polars!)
af.maturity_benefit = af.face_amount * af.survival_to_t.list.last()

# Aggregate results
total_pv = af.select(
    af.policy_id,
    total_pv=af.pv_cashflow.list.sum()
).collect()
```

**What we see:**
1. ✅ `.projection.cumulative_survival()` - complex operation, needs a method
2. ✅ `.projection.cumulative_discount()` - complex operation, needs a method
3. ✅ `.projection.with_period()` - list manipulation, needs a method
4. ✅ `af.face_amount * af.qx * af.survival_to_t` - simple math, use operators
5. ✅ `.list.last()` - Polars has it, use it directly
6. ✅ `.list.sum()` - Polars has it, use it directly

---

## Implementation Plan for ProjectionColumnAccessor

### Phase 1: Core Methods (Week 1)

**Files to create:**
- `gaspatchio_core/accessors/projection.py`
- `tests/accessors/test_projection.py`

**Methods to implement:**
1. ✅ `cumulative_survival()`
2. ✅ `cumulative_discount()`
3. ✅ `with_period()`
4. ✅ `with_periods()` (bonus - multiple updates)

**Tasks:**
1. Create accessor file with registration decorator
2. Implement each method following the pattern from `DateColumnAccessor`
3. Write comprehensive docstrings with examples
4. Write unit tests for list and scalar columns
5. Test with real actuarial data

**Acceptance Criteria:**
- All 4 methods working
- List column shimming automatic
- Scalar column support with grouping
- Tests passing
- Docstrings with executable examples

---

## Naming Alternatives Summary

For reference, here are the final naming decisions:

| Concept | Chosen Name | Alternatives Considered | Reason |
|---------|-------------|-------------------------|--------|
| Accessor | `.projection` | `.survival`, `.lifecycle`, `.series`, `.cumulative` | Best balance of specificity and scope |
| Cumulative survival | `cumulative_survival()` | `survival()`, `to_survival_curve()`, `tpx()` | Clarity over brevity |
| Cumulative discount | `cumulative_discount()` | `to_discount_factors()`, `vt()`, `discount()` | Parallel to cumulative_survival |
| Set at period | `with_period()` | `set_at_period()`, `override_at()`, `adjust()` | Functional style, reads well |
| Multiple periods | `with_periods()` | `set_periods()`, `override_periods()` | Plural form of with_period |

---

## Next Steps

1. **Get approval on naming** - Confirm `.projection` accessor and method names
2. **Implement core methods** - Start with `cumulative_survival()`
3. **Test thoroughly** - Both list and scalar columns
4. **Document with examples** - Executable docstrings
5. **Iterate based on usage** - Refine as we build real models

**Key Insight:** By removing unnecessary methods and leveraging operators + Polars, we have a minimal, powerful API that reads like mathematical formulas while staying discoverable and auditable.
