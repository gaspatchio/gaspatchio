# Project.md

This file provides guidance when working with code in this repository.

## Project API Philosophy and guidelines 


Explore how to design an API that:
1. **Reads like a poetic mathematical formula expressed in English**
2. **Allows actuaries to see and verify the actual calculations** (not trust framework magic)
3. **Is discoverable by LLMs** through clear naming, patterns, and rich documentation
4. **Balances convenience with escape hatches** for custom logic

## The Critical Design Tension
**But actuaries are mathematicians**, not software engineers. They need to:
- **Audit every calculation** for regulatory compliance
- **Understand the formulas** without reading framework source code
- **Modify logic** when edge cases arise (premium holidays, surrender charges, etc.)

**The tension:** "Not code" vs "What is Polars" vs "Just show me the actual calculation"

### The Insight: Worksheet + Domain Methods

Combine:
- **Worksheet metaphor** (familiar from Excel) - column-by-column definitions
- **Domain namespacing** - `.projection`, `.mortality`, `.finance`
- **Verb-based method names** that describe actuarial intent

**Result:** Code that reads like building an Excel worksheet, but with clear domain-specific operations.

## The Emerging Pattern: "Excel Columns + Domain Methods"

### Example: Real Term Insurance Projection Model

Below are real examples from a production term insurance model (`basic_term/model_projection.py`) demonstrating how the API enables actuaries to write calculations that read like textbook formulas:

#### Pattern 1: Complex Operations Use Named Methods

**Cumulative Survival Calculation** (model_projection.py:83)
```python
# Calculate cumulative survival probability using projection API
# cumulative_survival() with default start_at=1.0 gives beginning-of-period values
# This applies: [1.0, (1-qx[0]), (1-qx[0])*(1-qx[1]), ...]
af.pols_if_before_maturity = af.combined_decrement.projection.cumulative_survival()
```

**Why This Works:**
- `.cumulative_survival()` clearly states the actuarial intent
- The method handles the complex cumulative product logic internally
- Actuary sees what the calculation does without needing to read framework source
- Comment explains the formula being applied: `tpx[t] = (1-qx[0]) × (1-qx[1]) × ... × (1-qx[t])`

**Time-Shifting with Previous Period** (model_projection.py:100, 103)
```python
# Get previous period values for policy rollforward
pols_if_prev = af.pols_if_before_maturity.projection.previous_period()
pols_death_prev = pols_death_temp.projection.previous_period()

# Calculate surviving policies at each time period
af.surviving_at_t = pols_if_prev - pols_lapse_prev - pols_death_prev
```

**Why This Works:**
- `.previous_period()` is instantly recognizable as the t-1 reference actuaries use
- More intuitive than Polars' `.shift(1)` which requires understanding shift direction
- Automatically handles boundary conditions (fills with 0 by default)
- The rollforward formula is transparent and auditable

**Converting Annual to Monthly Rates** (model_projection.py - finance accessor pattern)
```python
# Convert annual interest rate to monthly equivalent
af.disc_rate_mth = af.disc_rate_ann.finance.to_monthly(method="compound")
# This applies: (1 + annual_rate)^(1/12) - 1
```

**Why This Works:**
- `.finance.to_monthly()` uses domain namespace - clearly financial operation
- Method name describes the transformation being performed
- Compound vs simple interest is explicit via parameter, not hidden in implementation
- Actuary can audit the conversion methodology

#### Pattern 2: Simple Math Uses Operators Directly

**Death and Lapse Calculations** (model_projection.py:126-127)
```python
# Now calculate final pols_death and pols_lapse using the final pols_if (after maturity)
af.pols_death = af.pols_if * af.mort_rate_mth
af.pols_lapse = (af.pols_if - af.pols_death) * af.lapse_rate_mth
```

**Why This Works:**
- The formula **IS** the code - no hidden framework magic
- Actuary can verify correctness by reading the line
- Reads exactly like the textbook formula or Excel cell
- List columns are handled automatically (element-wise multiplication)

**Claim Amount Calculation** (model_projection.py:188)
```python
# Calculate claim amounts: sum_assured * pols_death
# Uses Gaspatchio's list shimming for scalar * list broadcasting
af.claims = af.sum_assured * af.pols_death
```

**Why This Works:**
- Multiplying scalar `sum_assured` by list `pols_death` just works
- Framework handles the broadcasting automatically
- Actuary writes the formula naturally without thinking about implementation
- No method call needed - it's just multiplication

**Premium Calculation** (model_projection.py:244)
```python
# Calculate premiums(t) = premium_pp * pols_if(t)
# Uses Gaspatchio's list shimming for scalar * list broadcasting
af.premiums = af.premium_pp * af.pols_if
```

**Net Cashflow Formula** (model_projection.py:299)
```python
# Calculate net cashflow: premiums - claims - expenses - commissions
# Uses Gaspatchio's list shimming for element-wise arithmetic
af.net_cf = af.premiums - af.claims - af.expenses - af.commissions
```

**Why This Works:**
- The actuarial formula is written exactly as it appears in documentation
- Multiple list columns combined with natural operators (+, -, *)
- No framework ceremony - just write the math
- Self-documenting code that actuaries can audit

#### Pattern 3: Conditionals Read Like Excel IF()

**Maturity Detection** (model_projection.py:112-114)
```python
# Calculate maturity using Gaspatchio's when() conditional broadcasting
# Maturity occurs when month == policy_term * 12
# Uses the new when() API that supports conditional broadcasting on list columns
af.pols_maturity = (
    when(af.month == af.policy_term * 12).then(af.surviving_at_t).otherwise(0.0)
)
```

**Why This Works:**
- `when().then().otherwise()` mirrors Excel's IF() function structure
- Reads naturally in English: "when month equals term, then use surviving, otherwise zero"
- Works seamlessly on list columns (applies element-wise automatically)
- Actuary can verify the maturity logic without understanding framework internals

**Zeroing After Maturity** (model_projection.py:119-123)
```python
# Now create the final pols_if by zeroing out AT and after maturity
# pols_if should be zero for all months >= policy_term * 12 (at maturity month and beyond)
# Uses when() conditional broadcasting: keep values before maturity, zero after
af.pols_if = (
    when(af.month < af.policy_term * 12)
    .then(af.pols_if_before_maturity)
    .otherwise(0.0)
)
```

**Why This Works:**
- The business logic is front and center: "before maturity keep values, after maturity zero"
- List broadcasting happens automatically - actuary doesn't need to think about it
- Works in both debug and optimize modes seamlessly
- Clear audit trail of when policies stop being inforce

**Commission Calculation** (model_projection.py:292)
```python
# Calculate commissions: 100% of premiums in first year (duration 0), 0 otherwise
# Uses when() conditional broadcasting
af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)
```

**Why This Works:**
- Business rule stated clearly: "100% first year, nothing after"
- Conditional applies element-wise to projection periods automatically
- No loops, no map functions, no framework complexity
- Reads like describing the commission schedule to a colleague

### Why This API Design Succeeds

**For Actuaries:**
- ✅ **The math is completely visible**: Every formula in the model code exactly matches the actuarial calculation
- ✅ **Operators for obvious operations**: Multiplication, addition, subtraction use `*`, `+`, `-` naturally
- ✅ **Methods for complex operations**: `.cumulative_survival()`, `.previous_period()`, `.to_monthly()` handle intricate logic with clear names
- ✅ **Conditionals that read like English**: `when().then().otherwise()` mirrors Excel IF() that actuaries already know
- ✅ **Complete audit trail**: The calculation **IS** the code - no hidden framework magic to verify
- ✅ **Modify with confidence**: Actuary can adjust formulas (add premium holidays, change maturity logic) without understanding framework internals

**For LLMs:**
- ✅ **Pattern-based**: Simple math = operators, complex operations = named methods, business rules = conditionals
- ✅ **Discoverable**: `af.qx.projection.<TAB>` reveals available actuarial operations via domain namespaces
- ✅ **Self-documenting**: Method names describe actuarial intent (`.cumulative_survival()` not `.compute_1()`)
- ✅ **Compositional**: Mix operators, methods, and conditionals naturally in the same expression
- ✅ **Rich documentation**: Every method has docstrings with examples matching real actuarial use cases

**Key Insight:**
- **Complex operations** (cumulative products, time-shifting, rate conversions) → **Named methods with domain namespaces**
- **Simple operations** (multiplication, addition, subtraction) → **Operators directly**
- **Business logic** (maturity rules, commission schedules) → **when/then/otherwise conditionals**
- **Result:** Code reads like Excel formulas written in an actuarial textbook

### The Anti-Pattern: What We Avoid

**NOT this** (too much abstraction hides the calculation):
```python
af = af.projection.project_cashflows(periods=30)  # What formula is this?
af.pols_if = af.projection.rollforward(initial=1, rate=af.decrement)  # What's happening?
```

**THIS** (the formula IS the code):
```python
# Cumulative survival: (1-qx[0]) × (1-qx[1]) × ... × (1-qx[t])
af.pols_if = af.combined_decrement.projection.cumulative_survival()

# Death claims: Sum Assured × Deaths
af.claims = af.sum_assured * af.pols_death

# Net cashflow: Premiums - Claims - Expenses - Commissions
af.net_cf = af.premiums - af.claims - af.expenses - af.commissions
```

Each line is:
- **A mathematical expression** - not a method call hiding the formula
- **Auditable** - actuary can verify by reading the code
- **Composable** - mix operators and methods naturally
- **Excel-like** - write formulas the way you think about them

This is the balance between convention (helpful methods) and control (transparent calculations).


## Python Bindings Development Commands

- How to build and install the Python bindings
  ```bash
  # Build Rust extensions with maturin (required after Rust changes)
  maturin build -uv

  # Install all workspace dependencies
  uv sync
  ```

### Linter Behavior Note

**IMPORTANT:** The on-save hook runs `ruff` which automatically removes unused imports. When adding a new library import, you MUST add both the import AND the code that uses it in a single edit. Otherwise the linter will strip the import before you can use it.

**Bad** (import gets stripped):
```python
# Edit 1: Add import
from loguru import logger  # <- Linter removes this!

# Edit 2: Add usage
logger.debug("message")  # <- Error: logger not defined
```

**Good** (import and usage together):
```python
# Single edit: Add import AND usage
from loguru import logger

logger.debug("message")  # <- Works!
```

### Testing
```bash
# Run all Python tests
uv run pytest

# Run tests with docstring validation (important for API docs)
uv run pytest --doctest-modules --doctest-glob="*.pyi"

# Run specific test categories
uv run pytest -m "not benchmark"  # Skip slow benchmarks
uv run pytest -m performance      # Only performance tests

# Type checking (both tools should pass)
uv run mypy gaspatchio_core
uv run pyright gaspatchio_core

# Validate type stubs match implementation
uv run python -m mypy.stubtest gaspatchio_core

# Update docstring test expectations
uv run pytest gaspatchio_core/accessors/excel.py --doctest-modules --accept
```

### Model Execution
```bash
# Run actuarial model
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-model model.py data.parquet

# Debug single policy
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-single-policy model.py data.parquet "PolicyID" --policy-id-column "Policy number"

# Run single policy
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true uv run gspio run-single-policy ../../../gaspatchio-models/models/my-model/model_calculation.py ../../../gaspatchio-models/models/my-model/model-points.parquet 1 --policy-id-column "Policy number"

# Run model
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true uv run gspio run-model ../../../gaspatchio-models/models/my-model/model_calculation.py ../../../gaspatchio-models/models/my-model/model-points.parquet

# Run with debug mode (more output rows)
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-model model.py data.parquet --mode debug -r 50

# Output to file
LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true gspio run-model model.py data.parquet --output-file results.parquet
```

## High-Level Architecture

### Python Package Structure
The Python bindings wrap the Rust core library via PyO3:

- **gaspatchio_core._internal**: PyO3 module built from Rust (see _internal.pyi for API)
- **ActuarialFrame**: Main DataFrame-like structure for actuarial calculations
  - Wraps Polars DataFrames with actuarial-specific operations
  - Supports method chaining via proxy pattern
  - Lazy evaluation for performance
  
- **Proxy Pattern**: ColumnProxy/ExpressionProxy enable fluent API
  - `af["column"].excel.pv(...)` - Excel functions via accessor
  - `af["column"].dt.year_frac(...)` - Date functions via accessor
  - Chain operations before execution for optimization

### Time-Shifting Operations

The projection accessor provides actuarial-friendly methods for accessing values from other time periods:

```python
# Previous period (t-1) - most common case
af.reserve_prev = af.reserve.projection.previous_period()
af.pols_death_prev = af.pols_death.projection.previous_period(fill_value=0)

# Next period (t+1) - for forward-looking calculations
af.rate_next = af.interest_rate.projection.next_period()

# Arbitrary period offsets using mathematical t notation
af.reserve_t2 = af.reserve.projection.at_period(-2)  # t-2 (two periods ago)
af.projected = af.value.projection.at_period(3)      # t+3 (three periods ahead)
```

**Design Philosophy:**
- Use mathematical `t-1`, `t-2` notation (negative = prior, positive = future)
- Default `fill_value=0` for missing boundary values
- Methods make time-shifting transparent and auditable
- Replaces confusing `.shift()` with actuarial-friendly API

- **Assumption Tables**: Table/TableBuilder for rate lookups
  - Multiple join strategies (age/duration, select/ultimate)
  - Efficient batch lookups via Polars joins

### Critical Implementation Details

1. **Docstring Examples Are Tests**: Examples in docstrings are validated by pytest. When modifying examples, run with `--accept` to update expected outputs.

2. **Type Stubs Required**: The `_internal.pyi` file must match Rust exports exactly. Use `mypy.stubtest` to verify.

3. **Performance Warnings**: The codebase emits warnings for suboptimal patterns (e.g., iterating over policies). Always use vectorized operations.

4. **Error Formatting**: Custom error formatter (`errors/formatter.py`) provides clear error messages with context. Preserve error handling patterns.

5. **Telemetry Integration**: Logfire telemetry is configured but optional. Set `LOGFIRE_TOKEN` to enable.

### Testing Philosophy

- **Docstring-Driven**: Public API examples in docstrings serve as tests
- **Type Safety**: Both mypy and pyright must pass in strict mode
- **Performance**: Benchmarks track regression (see `tests/test_performance.py`)
- **Integration**: Example models in `tests/examples/` validate end-to-end functionality

### Development Workflow

1. For new Excel functions: Add to `accessors/excel.py` with docstring examples
2. For new vector operations: Add to `functions/vector.py` 
3. Always run type checkers and tests before committing
4. Use `gspio` CLI to validate changes with real models
5. Check parent `CLAUDE.md` for broader project guidelines

@prompts/python/core.md
@prompts/python/style.md
@prompts/python/typing.md
@prompts/python/uv.md
