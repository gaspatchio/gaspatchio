# Actuarial Modeling API Design Research

## Executive Summary

This analysis compares two actuarial modeling libraries—**JuliaActuary** (Julia) and **lifelib** (Python)—evaluating their API design approaches against four critical goals:

1. **Mathematical readability**: Does code read like formulas in English/mathematical notation?
2. **Transparency**: Can actuaries see and verify actual calculations?
3. **Discoverability**: Clear naming and patterns?
4. **Customization**: Balance convenience with escape hatches?

**Key Finding**: JuliaActuary excels at mathematical notation and composability, while lifelib prioritizes spreadsheet-like traceability and dependency tracking. Both reveal important design patterns for Gaspatchio.

---

## 1. JuliaActuary.org

### Overview
- **Language**: Julia
- **Core packages**: LifeContingencies.jl, MortalityTables.jl, ActuaryUtilities.jl
- **Philosophy**: "Math-heavy code looks like math"

### API Examples

#### Basic Life Contingency Calculation
```julia
using LifeContingencies
using MortalityTables
using FinanceModels
import LifeContingencies: V, ä  # Import mathematical notation

# Load mortality table
vbt2001 = MortalityTables.table(
    "2001 VBT Residual Standard Select and Ultimate - Male Nonsmoker, ANB"
)

# Define the life
life = SingleLife(
    mortality = vbt2001.select[30],
    issue_age = 30
)

# Define interest rate
yield = FinanceModels.Yield.Constant(0.05)

# Create life contingency
lc = LifeContingency(life, yield)

# Calculate insurance and annuities
whole_life = Insurance(lc)          # Whole life insurance
term_10 = Insurance(lc, 10)         # 10-year term
annuity = ä(lc)                     # Annuity due
annuity_5 = ä(lc, 5, certain=5, frequency=4)  # 5-year, quarterly

# Extract values
pv = present_value(whole_life)
reserve_t5 = V(lc, 5)               # Reserve at time 5
```

#### Transparent Calculation Components
```julia
# Access intermediate calculation steps
cashflows(ins)        # Unit cashflows vector
timepoints(ins)       # Associated time periods
survival(ins)         # Survival probabilities
benefit(ins)          # Unit benefit amounts
probability(ins)      # Payment probabilities
present_value(ins)    # Final actuarial present value
```

#### Custom Mortality Tables
```julia
# Create custom ultimate mortality
ult_vec = [0.005, 0.008, ..., 0.805, 1.00]
ult = UltimateMortality(ult_vec, start_age=15)

# Create select mortality
select_matrix = [0.001 0.002 ... 0.010; ...]
sel = SelectMortality(select_matrix, ult, start_age=0)

# Build complete table with metadata
my_table = MortalityTable(
    sel, ult,
    metadata = TableMetaData(
        name = "My Table",
        comments = "Rates for Product XYZ"
    )
)
```

#### Parametric Mortality Models
```julia
# Gompertz-Makeham model
gompertz = MortalityTables.Gompertz(a=0.01, b=0.2)

# Calculate survival and decrement
survival(gompertz, 20, 25)    # Survival from age 20 to 25
decrement(gompertz, 20, 25)   # Decrement probability
```

### Evaluation Against Design Goals

#### 1. Mathematical Readability: ★★★★★ (Excellent)
**Strengths:**
- **Unicode notation**: Uses actual mathematical symbols (`ä`, `Ä`, `V`, `A`) that actuaries recognize
- **Dual notation**: Offers both symbols and English (`ä` = `annuity_due`)
- **Natural composition**: Code mirrors mathematical formulas directly

**Example showing readability:**
```julia
# This reads like actuarial notation
ä(lc, 5)                          # äₓ:5̅|
Insurance(lc, 10)                 # Aₓ:10̅|
V(lc, 5)                          # ₅V

# Equivalent long-form names available
annuity_due(lc, 5)
Insurance(lc, 10)
reserve_premium_net(lc, 5)
```

**Quote from documentation**: *"Use functions that look more like the math you are used to (e.g. A, ä) with Unicode support"*

#### 2. Transparency: ★★★★☆ (Very Good)
**Strengths:**
- **Exposed intermediate steps**: Can access `cashflows()`, `survival()`, `benefit()`, `probability()` separately
- **Pure Julia implementation**: All code readable and inspectable (not hidden in C/C++ libraries)
- **Composable components**: Mortality, interest, and benefit structures combine transparently

**Example of transparency:**
```julia
ins = Insurance(lc, 10)

# Audit the calculation components
flows = cashflows(ins)      # [1.0, 1.0, ..., 1.0]
survs = survival(ins)       # [0.998, 0.996, ..., 0.850]
times = timepoints(ins)     # [1, 2, ..., 10]
probs = probability(ins)    # [0.002, 0.002, ..., 0.015]

# Verify present value calculation manually
manual_pv = sum(flows .* probs .* discount_factors)
```

**Limitation**: While components are exposed, the internal implementation of complex calculations (like commutation functions) requires diving into source code.

#### 3. Discoverability: ★★★★☆ (Very Good)
**Strengths:**
- **Consistent naming**: `SingleLife()`, `JointLife()`, `Insurance()`, `AnnuityDue()`, `AnnuityImmediate()`
- **Keyword arguments**: Self-documenting parameters like `mortality=`, `issue_age=`, `certain=`, `frequency=`
- **Namespace management**: Mathematical symbols require explicit import to avoid pollution

**Namespace design:**
```julia
using LifeContingencies              # Imports English names
import LifeContingencies: V, ä       # Explicitly import symbols

# Avoids namespace collisions with short symbols
# Can use module prefix: LifeContingencies.ä(...)
```

**Constructor pattern consistency:**
```julia
# All major types follow same pattern
life = SingleLife(mortality=table, issue_age=30)
joint = JointLife(lives=(l1, l2), contingency=LastSurvivor())
ins = Insurance(lc, 10)
ann = AnnuityDue(lc, 5)
```

**Challenge**: Actuaries unfamiliar with Julia may struggle with the language's conventions (multiple dispatch, type system).

#### 4. Customization: ★★★★★ (Excellent)
**Strengths:**
- **Multiple dispatch**: Extend any function for custom types without modifying core library
- **Flexible interest rates**: Support constants, forwards, stochastic rates
- **Custom mortality tables**: Build tables from vectors or parametric models
- **Modular composition**: Swap mortality/yield/benefit components independently

**Customization examples:**
```julia
# Custom interest rates
yield = Yields.Constant(0.05)                    # Flat rate
yield = Yields.Forward(rand(Normal(μ,σ), 100))   # Stochastic

# Custom mortality with transformations
scaled_mort = min.(table.rates .* 1.3, 1.0)     # 130% with cap

# Extend functions via multiple dispatch
import LifeContingencies: survival
function survival(custom_type::MyCustomLife, t1, t2)
    # Custom implementation
end
```

**Julia's multiple dispatch advantage**: You can extend base functions without wrapper classes or inheritance—just define a method for your type.

### Key Patterns & Design Insights

#### Pattern 1: Dual Notation System
**What they do**: Offer both mathematical symbols and English names
```julia
ä(lc)           # For those who want compact notation
annuity_due(lc) # For those who prefer readability
```

**Lesson for Gaspatchio**: Consider supporting both forms. Actuaries love notation but code reviewers need English.

#### Pattern 2: Explicit Construction → Composition
**What they do**: Build complex objects by composing simpler ones
```julia
# Step-by-step composition
life = SingleLife(mortality=table)          # 1. Define life
yield = Yields.Constant(0.05)               # 2. Define interest
lc = LifeContingency(life, yield)           # 3. Combine
ins = Insurance(lc)                         # 4. Add benefit structure

# Each step is inspectable and swappable
```

**Lesson for Gaspatchio**: Avoid monolithic builders. Let users assemble components explicitly so they can inspect/modify each piece.

#### Pattern 3: Vector Access Patterns
**What they do**: Tables behave like arrays with intuitive indexing
```julia
vbt2001.ultimate[95]           # Single age
vbt2001.select[35][50:end]     # Age 35 issue, ages 50+
table[age]                     # Consistent across all table types
```

**Lesson for Gaspatchio**: Accessing assumptions should feel like array indexing, not method calls.

#### Pattern 4: Parametric Models as First-Class Citizens
**What they do**: Treat parametric models (Gompertz, Makeham) the same as table-based mortality
```julia
# Both are mortality objects
table_mort = UltimateMortality(rates)
param_mort = MortalityTables.Gompertz(a=0.01, b=0.2)

# Both work in same contexts
life1 = SingleLife(mortality=table_mort)
life2 = SingleLife(mortality=param_mort)
```

**Lesson for Gaspatchio**: Don't segregate tables from formulas. They should be interchangeable.

### What JuliaActuary Does Well

1. **Mathematical fidelity**: Code looks like actuarial textbooks
2. **Composability**: Small, focused types that combine naturally
3. **Extensibility**: Multiple dispatch enables seamless customization
4. **Pure Julia**: No hidden C/C++ dependencies to debug
5. **Explicit over implicit**: Clear construction steps

### What Could Be Improved

1. **Julia learning curve**: Requires learning a new language
2. **Documentation gaps**: Some functions lack comprehensive examples
3. **Error messages**: Julia's type system can produce cryptic errors
4. **Limited Python interop**: Hard to integrate with existing Python ecosystems
5. **Intermediate step verbosity**: Requires multiple steps to set up calculations

---

## 2. Lifelib (Python)

### Overview
- **Language**: Python
- **Core framework**: modelx (spreadsheet-like calculation engine)
- **Philosophy**: "Formulas are easy to read, and easy to trace"

### API Examples

#### Basic Model Setup
```python
import modelx as mx
import lifelib

# Create model from template
lifelib.create('simplelife', 'my_project')

# Load existing model
model = mx.read_model('simplelife')

# Access projection for specific policy
proj = model.Projection[1]  # Parametrized space for policy 1

# Calculate present value
pv = proj.PV_NetCashflow(0)
```

#### Cell-Based Formula Definitions
```python
# From BasicTerm_M projection model
def premiums(t):
    """Premium income from t to t+1"""
    return premium_pp() * pols_if(t)

def claims(t):
    """Claims during period from t to t+1"""
    return claim_pp(t) * pols_death(t)

def expenses(t):
    """Acquisition and maintenance expenses"""
    return (t == 0) * expense_acq() * pols_if(t) \
           + pols_if(t) * expense_maint()/12 * inflation_factor(t)

def net_cf(t):
    """Net cashflow"""
    return premiums(t) - claims(t) - expenses(t) - commissions(t)
```

#### Recursive Policy Decrement
```python
def pols_if(t):
    """Number of in-force policies (recursive)"""
    if t == 0:
        return pols_if_init()
    elif t < max_proj_len():
        return pols_if(t-1) - pols_lapse(t-1) - pols_death(t-1) - pols_maturity(t)

def pols_death(t):
    """Deaths occurring at time t"""
    return pols_if(t) * mort_rate_mth(t)

def pols_lapse(t):
    """Lapses occurring at time t"""
    return (pols_if(t) - pols_death(t)) * (1-(1 - lapse_rate(t))**(1/12))
```

#### Present Value Calculations
```python
def pv_premiums():
    """Present value of premiums"""
    result = np.array(list(premiums(t) for t in range(max_proj_len()))).transpose()
    return result @ disc_factors()[:max_proj_len()]

def pv_net_cf():
    """Present value of net cashflows"""
    return pv_premiums() - pv_claims() - pv_expenses() - pv_commissions()
```

#### Formula Customization
```python
# Modify formula by reassigning the formula property
model.Projection.pols_if_init.formula = lambda: 10000

# Add new cell using decorator
import modelx as mx

@mx.defcells
def custom_benefit(x):
    if x < x0 + n:
        return d(x) / l(x0)
    else:
        return 0
```

#### Dependency Tracing
```python
# Trace what a calculation depends on (precedents)
model.Projection[1].pv_net_cf.precedents()

# Trace what depends on a calculation (successors)
model.Projection[1].premiums.succs()

# Visual dependency tree in Spyder plugin (MxAnalyzer)
# Right-click cell → "Analyze Selected"
```

### Evaluation Against Design Goals

#### 1. Mathematical Readability: ★★★☆☆ (Good)
**Strengths:**
- **English function names**: Clear, descriptive (e.g., `premiums()`, `pols_death()`)
- **Formula syntax**: Looks like Python, reads like logic
- **Docstrings**: Each cell has explanation of what it calculates

**Example:**
```python
def net_cf(t):
    """Net cashflow"""
    return premiums(t) - claims(t) - expenses(t) - commissions(t)
```

**Weaknesses:**
- **No mathematical notation**: Can't use `ä` or `V` symbols
- **Spreadsheet naming**: Prefixes like `Pols*`, `Size*`, `Benefit*` feel like Excel columns
- **Verbosity**: More typing than mathematical notation

**Comparison:**
```python
# lifelib
def pv_annuity_due():
    return sum(pols_if(t) * disc_factor(t) for t in range(n))

# vs JuliaActuary
ä(lc, n)
```

The lifelib version is more explicit but less concise.

#### 2. Transparency: ★★★★★ (Excellent)
**Strengths:**
- **Dependency tracing**: Built-in `precedents()` and `succs()` methods show calculation graph
- **Visual tools**: MxAnalyzer provides tree view of dependencies
- **Lazy evaluation**: Values calculated on-demand, can inspect before computing
- **Formula inspection**: `.formula` property shows actual code

**Example of transparency:**
```python
# View formula source
print(model.Projection[1].net_cf.formula)

# Trace dependencies
deps = model.Projection[1].net_cf.precedents()
# Shows: [premiums, claims, expenses, commissions]

# Trace usage
users = model.Projection[1].premiums.succs()
# Shows: [net_cf, pv_premiums, ...]
```

**Quote from documentation**: *"Dependency tracing is an essential feature for checking and validating models—you can check what other values each calculated value is using, and also what other values it is used by."*

**This is lifelib's strongest feature**: The spreadsheet-like dependency tracking is exactly what actuaries need for audit trails.

#### 3. Discoverability: ★★★☆☆ (Good)
**Strengths:**
- **Hierarchical organization**: Model → Space → Cells structure
- **Python familiarity**: Standard Python syntax
- **Parametrized spaces**: `Projection[policy_id]` intuitive for policy-level calculations

**Example structure:**
```python
model.Projection[1].Policy.sum_assured
model.Projection[1].Assumptions.mortality_table
model.Projection[1].premiums(5)
model.Projection[1].PV_NetCashflow(0)
```

**Weaknesses:**
- **Naming conventions inconsistent**: Mix of `snake_case`, `PascalCase`, prefix patterns (`PV_`, `pv_`)
- **Implicit naming**: Must know that `pols_if` means "policies in force"
- **Prefix overload**: `Pols*`, `Size*`, `Benefit*` patterns require learning the system

**Comparison of naming approaches:**
```python
# lifelib prefixes
pols_if()          # Policies in force
pols_death()       # Deaths
pols_lapse()       # Lapses
SizePremium()      # Premium per policy
BenefitDeath()     # Death benefit aggregate

# vs more discoverable names
policies_in_force()
death_count()
lapse_count()
premium_per_policy()
total_death_benefits()
```

The prefix system is compact but requires domain knowledge to decode.

#### 4. Customization: ★★★☆☆ (Good)
**Strengths:**
- **Formula reassignment**: Can override any cell's formula
- **Decorator extension**: Use `@mx.defcells` to add new cells
- **Space composition**: Models built from reusable spaces
- **Python flexibility**: Full Python ecosystem available

**Customization examples:**
```python
# Override a formula
model.Projection.pols_if_init.formula = lambda: 10000

# Add custom cell
@mx.defcells
def custom_calc(t):
    return premiums(t) * 1.05

# Modify at space level
model.Projection.r = 0.03  # Change discount rate
```

**Weaknesses:**
- **No inheritance mechanism**: Can't easily create "subclass" of a Space with modifications
- **Limited type system**: No compile-time checks, easy to break dependencies
- **Global state**: Modifying formulas affects the entire model instance

**Comparison to JuliaActuary:**
```julia
# Julia: Define new method for your type
function survival(my_custom_life::CustomLife, t1, t2)
    # Custom logic
end

# Python/lifelib: Reassign formula
model.Projection.survival.formula = lambda t1, t2: custom_logic()
```

Julia's approach is more modular and testable; lifelib's is more flexible but brittle.

### Key Patterns & Design Insights

#### Pattern 1: Spreadsheet Calculation Model
**What they do**: Treat Python functions as spreadsheet cells with automatic dependency resolution
```python
# Define cells (like Excel formulas)
def premiums(t):
    return premium_pp() * pols_if(t)

def net_cf(t):
    return premiums(t) - claims(t)  # Automatically depends on premiums

# modelx tracks dependencies automatically
```

**Lesson for Gaspatchio**: Consider automatic dependency tracking for audit trails. Actuaries think in spreadsheet terms.

#### Pattern 2: Parametrized Spaces
**What they do**: Create separate calculation contexts for different entities
```python
model.Projection[1]    # Policy 1
model.Projection[2]    # Policy 2
# Each has independent calculations
```

**Lesson for Gaspatchio**: Policy-level isolation is valuable. Consider a similar pattern with `.for_policy(id)` or similar.

#### Pattern 3: Prefix-Based Namespacing
**What they do**: Use prefixes to group related calculations
```python
# Policy counts
pols_if(), pols_death(), pols_lapse()

# Per-policy sizes
SizePremium(), SizeBenefitDeath()

# Present values
pv_premiums(), pv_claims(), PV_NetCashflow()
```

**Lesson for Gaspatchio**: While compact, prefixes reduce discoverability. Consider namespaces instead:
```python
# Instead of prefixes
policies.in_force(t)
policies.deaths(t)
per_policy.premium(t)
pv.premiums()
```

#### Pattern 4: Lazy Evaluation with Memoization
**What they do**: Calculate values only when requested, cache results
```python
# First call computes and caches
result = model.Projection[1].pv_net_cf(0)

# Subsequent calls use cached value
result2 = model.Projection[1].pv_net_cf(0)  # Instant
```

**Lesson for Gaspatchio**: Lazy eval + caching is excellent for exploratory analysis. But be careful with cache invalidation.

### What Lifelib Does Well

1. **Dependency tracing**: Best-in-class transparency for auditing
2. **Spreadsheet familiarity**: Natural for Excel-native actuaries
3. **Python ecosystem**: Access to pandas, numpy, matplotlib
4. **Lazy evaluation**: Calculate only what's needed
5. **Visual tools**: Spyder plugin for interactive exploration

### What Could Be Improved

1. **Naming consistency**: Mix of conventions reduces discoverability
2. **Type safety**: No compile-time checks, easy to introduce bugs
3. **Customization brittleness**: Formula reassignment can break dependencies
4. **Documentation**: Limited examples of advanced patterns
5. **Performance**: Python loop-based calculations slower than vectorized operations
6. **No mathematical notation**: Stuck with verbose English names

---

## Comparative Analysis

### Design Goals Scorecard

| Goal | JuliaActuary | lifelib | Notes |
|------|--------------|---------|-------|
| **Mathematical Readability** | ★★★★★ | ★★★☆☆ | Julia's Unicode notation wins decisively |
| **Transparency** | ★★★★☆ | ★★★★★ | lifelib's dependency tracing is superior |
| **Discoverability** | ★★★★☆ | ★★★☆☆ | Julia's consistency beats lifelib's prefixes |
| **Customization** | ★★★★★ | ★★★☆☆ | Multiple dispatch more powerful than formula reassignment |
| **Overall** | ★★★★½ | ★★★½☆ | JuliaActuary has edge but both strong |

### Philosophy Comparison

#### JuliaActuary: "Code as Mathematics"
- **Core belief**: Math-heavy code should look like math
- **Design priority**: Fidelity to actuarial notation
- **Target user**: Actuary who wants to write formulas, not software
- **Trade-off**: Requires learning Julia

**Representative quote**: *"Math-heavy code looks like math; it's easy to pick up, and quick-to-prototype."*

#### lifelib: "Code as Spreadsheet"
- **Core belief**: Actuaries think in spreadsheets
- **Design priority**: Dependency tracking and traceability
- **Target user**: Actuary who wants Excel-like transparency in Python
- **Trade-off**: Sacrifices notation for familiarity

**Representative quote**: *"Formulas are easy to read, and easy to trace formula dependency and errors."*

### Strengths Matrix

| Dimension | JuliaActuary | lifelib |
|-----------|--------------|---------|
| **Notation** | Mathematical symbols | English names |
| **Composition** | Explicit assembly | Hierarchical spaces |
| **Inspection** | Component access | Dependency graphs |
| **Extension** | Multiple dispatch | Formula override |
| **Learning curve** | Steeper (new language) | Gentler (Python) |
| **Performance** | Fast (compiled Julia) | Moderate (Python) |
| **Ecosystem** | Growing | Mature (Python) |

### Code Comparison: Same Calculation

#### Task: Calculate present value of 10-year term insurance for age 30 male

**JuliaActuary:**
```julia
using LifeContingencies, MortalityTables, FinanceModels

table = MortalityTables.table("2001 VBT...")
life = SingleLife(mortality=table.select[30])
yield = FinanceModels.Yield.Constant(0.05)
lc = LifeContingency(life, yield)
ins = Insurance(lc, 10)
pv = present_value(ins)

# Inspect components
flows = cashflows(ins)
survs = survival(ins)
```

**lifelib:**
```python
import modelx as mx

model = mx.read_model('BasicTerm_M')
proj = model.Projection[policy_id]

# Modify parameters
proj.Policy.issue_age = 30
proj.Policy.policy_term = 10
proj.Assumptions.disc_rate = 0.05
proj.Assumptions.mort_table = "VBT2001"

# Calculate
pv = proj.pv_claims()

# Trace dependencies
deps = proj.pv_claims.precedents()
```

**Analysis:**
- JuliaActuary: 7 lines, explicit composition, mathematical
- lifelib: 9 lines, parameter assignment, familiar
- JuliaActuary feels like writing a formula
- lifelib feels like configuring a spreadsheet

---

## Key Learnings for Gaspatchio

### 1. Notation Matters (from JuliaActuary)

**Learning**: Actuaries love mathematical notation, but it's polarizing.

**Recommendation for Gaspatchio**:
```python
# Support both forms
from gaspatchio import ActuarialFrame

# Mathematical-leaning (but still readable)
af.mortality.survival_from_to(x, x+t)
af.benefit.insurance_present_value(n_years=10)

# NOT recommended: Unicode requires Python 3.5+ and confuses linters
# af.ä(...)  # Don't do this in Python

# But DO provide compact alternatives
af.mort.surv(x, x+t)    # Compact for interactive use
af.benefit.pv_ins(10)   # Compact for interactive use
```

**Key insight**: Find middle ground—shorter than full English but more readable than symbols.

### 2. Expose Intermediate Steps (from JuliaActuary)

**Learning**: Actuaries need to verify calculations, not just get final answers.

**Recommendation for Gaspatchio**:
```python
# Instead of just:
result = af.present_value_benefits()

# Provide:
result = af.benefit_calculator()\
    .with_cashflows()     # Returns cashflows array
    .with_survival()      # Returns survival array
    .with_discount()      # Returns discount factors
    .present_value()      # Returns final PV

# Or as properties:
calc = af.benefit_calculator()
calc.cashflows       # Access intermediate step
calc.survival_probs  # Access another step
calc.present_value   # Access final result
```

**Key insight**: Make the calculation "glass box" not "black box."

### 3. Dependency Tracking is Essential (from lifelib)

**Learning**: Actuaries need audit trails showing what affects what.

**Recommendation for Gaspatchio**:
```python
# Consider adding a trace mode
af.enable_tracing()

result = af.calculate_reserves(t=5)

# Access trace
trace = af.last_calculation_trace()
trace.show_dependencies()   # What was used
trace.show_formula()        # How it was calculated
trace.show_inputs()         # What input values

# Or make it explicit
from gaspatchio import traced

@traced
def custom_calculation(af, t):
    return af.premiums(t) - af.claims(t)

result, trace = custom_calculation(af, 5)
```

**Key insight**: Consider building dependency tracking into the core, not as an afterthought.

### 4. Avoid Prefix Pollution (from lifelib weaknesses)

**Learning**: Prefixes (`pols_*`, `PV_*`) reduce discoverability.

**Recommendation for Gaspatchio**:
```python
# Instead of lifelib's approach:
af.pols_if(t)
af.pols_death(t)
af.pv_premiums()

# Use namespaces:
af.policies.in_force(t)
af.policies.deaths(t)
af.present_values.premiums()

# Or chaining:
af.for_policy(id).in_force(t)
af.for_policy(id).deaths(t)
af.present_values().premiums()
```

**Key insight**: Namespaces are more discoverable than prefixes.

### 5. Composability Over Configuration (from JuliaActuary)

**Learning**: Building from small pieces is more flexible than configuring big objects.

**Recommendation for Gaspatchio**:
```python
# Instead of configuration-heavy:
af = ActuarialFrame(data)
af.set_mortality_table("VBT2001")
af.set_interest_rate(0.05)
af.set_issue_age(30)
result = af.calculate()

# Prefer composition:
mortality = MortalityTable.load("VBT2001").for_age(30)
interest = InterestRate.constant(0.05)
assumptions = Assumptions(mortality=mortality, interest=interest)
result = af.with_assumptions(assumptions).calculate_reserves()

# Each piece is testable, inspectable, swappable
```

**Key insight**: Small composable pieces beat big configurable objects.

### 6. Escape Hatches Should Be Explicit (from JuliaActuary)

**Learning**: Users need to override behavior but it should be clear when they do.

**Recommendation for Gaspatchio**:
```python
# Bad: Implicit override
af.mortality_rate = lambda x: custom_logic()  # Too easy to break

# Good: Explicit override
from gaspatchio.assumptions import MortalityAssumption

class CustomMortality(MortalityAssumption):
    def rate(self, age: int) -> float:
        return custom_logic(age)

af = af.with_mortality(CustomMortality())
# Clear that we're using custom logic
```

**Key insight**: Make customization possible but obvious when it's happening.

### 7. Naming Should Be Discoverable AND Precise (from both)

**Learning**: Balance clarity with brevity.

**Recommendation for Gaspatchio**:
```python
# Full names for primary API
af.survival_probability(from_age=30, to_age=40)
af.present_value_of_benefits(n_years=10)

# Short aliases for interactive use
af.surv(30, 40)      # Alias clearly documented
af.pv_ben(10)        # Alias clearly documented

# Convention: Full names in library code, short aliases in notebooks
```

**Key insight**: Provide both and document when to use each.

### 8. Performance Should Be Default, Not Opt-In (from JuliaActuary)

**Learning**: Actuaries shouldn't think about vectorization—it should just be fast.

**Recommendation for Gaspatchio**:
```python
# Instead of requiring:
af.vectorized_calculate(ages)  # User must know to use this

# Just make it fast by default:
af.calculate(ages)  # Automatically vectorized

# Rust backend + Polars gives us this for free
```

**Key insight**: Gaspatchio's Rust core is our advantage here—lean into it.

---

## Specific Patterns to Adopt

### Pattern 1: Dual Interface (from JuliaActuary)
```python
# Long-form for clarity
result = actuarial_frame.calculate_present_value_of_annuity_due(
    from_age=30,
    duration=10,
    certain_period=5
)

# Short-form for power users
result = actuarial_frame.pvad(x=30, n=10, certain=5)

# Document equivalence clearly
```

### Pattern 2: Builder Chaining (inspired by both)
```python
# Readable, discoverable, fluent
result = (
    ActuarialFrame(data)
    .with_mortality(table="VBT2001", issue_age=30)
    .with_interest(rate=0.05)
    .calculate()
    .present_value()
)

# Each step returns self (or new object), enables inspection
intermediate = ActuarialFrame(data).with_mortality(...)
intermediate.mortality  # Inspect before proceeding
```

### Pattern 3: Trace Context Manager (from lifelib inspiration)
```python
# Enable tracing for a block
with actuarial_frame.trace() as t:
    result = af.calculate_reserves(5)

# Inspect trace
t.dependencies()    # What was used
t.formula()         # How it was calculated
t.as_graph()        # Visual dependency graph
```

### Pattern 4: Assumption Bundles (from JuliaActuary)
```python
# Bundle related assumptions
assumptions = AssumptionSet(
    mortality=MortalityTable.load("VBT2001"),
    interest=InterestRate.constant(0.05),
    lapse=LapseTable.load("2008 IDI"),
    expenses=Expenses(acquisition=0.05, maintenance=0.01)
)

# Apply as unit
af = af.with_assumptions(assumptions)

# Override individual pieces
af = af.with_assumption_override(
    interest=InterestRate.forward_curve(curve)
)
```

### Pattern 5: Namespace Organization (improving on lifelib)
```python
# Clear namespace hierarchy
af.policies.in_force(t)
af.policies.deaths(t)
af.policies.lapses(t)

af.cashflows.premiums(t)
af.cashflows.benefits(t)
af.cashflows.expenses(t)

af.present_values.net_cashflow()
af.reserves.policy(t)

# Discoverable via autocomplete
```

---

## Patterns to Avoid

### Anti-Pattern 1: Prefix-Based Namespacing (from lifelib)
```python
# Don't do this:
af.pols_if(t)
af.pols_death(t)
af.pv_premiums()

# Prefixes reduce discoverability and feel like Excel columns
```

### Anti-Pattern 2: Implicit Formula Overrides (from lifelib)
```python
# Don't do this:
af.some_function.formula = lambda: custom_logic()

# Too easy to break, hard to trace, no type checking
```

### Anti-Pattern 3: Excessive Unicode (from JuliaActuary)
```python
# Don't do this in Python:
af.ä(x, n)     # Hard to type, confuses linters
af.Ä(x, n)     # Even worse

# Python isn't Julia—embrace readable English names
```

### Anti-Pattern 4: Configuration Objects (neither does this, but avoid it)
```python
# Don't do this:
config = {
    "mortality_table": "VBT2001",
    "interest_rate": 0.05,
    "issue_age": 30
}
af.configure(config)
af.calculate()

# Stringly-typed, no autocomplete, error-prone
```

### Anti-Pattern 5: Hidden Magic (neither does this either)
```python
# Don't do this:
@magical_decorator
def calculate_reserves(af):
    # Decorator does too much behind the scenes
    # User can't see what's happening
    pass

# Transparency requires explicitness
```

---

## Final Recommendations for Gaspatchio

### 1. Core API Philosophy
- **Mathematical fidelity** (from JuliaActuary) with **English readability** (both)
- **Explicit composition** (JuliaActuary) with **namespace organization** (improving lifelib)
- **Transparent calculations** (both) with **dependency tracking** (lifelib)
- **Performance by default** (JuliaActuary via our Rust core)

### 2. Naming Convention Standard
```python
# Full names (primary API)
actuarial_frame.calculate_present_value_of_annuity_due(from_age, duration)
actuarial_frame.survival_probability(from_age, to_age)

# Namespaced shortcuts (power user API)
af.pv.annuity_due(x, n)
af.mort.survival(x1, x2)

# Document both, recommend full names for production code
```

### 3. Required Features
Based on both libraries, Gaspatchio MUST support:
1. **Intermediate step access**: Like JuliaActuary's `cashflows()`, `survival()`, etc.
2. **Dependency tracking**: Like lifelib's `precedents()` and `succs()`
3. **Custom assumptions**: Like JuliaActuary's modular composition
4. **Namespace organization**: Better than lifelib's prefix approach
5. **Explicit overrides**: Like JuliaActuary's multiple dispatch pattern

### 4. Differentiation Opportunities
Where Gaspatchio can beat both:
1. **Rust performance** with **Python ergonomics**: Better than both
2. **Modern type hints**: Python 3.10+ with full IDE support
3. **Polars integration**: DataFrame-native calculations
4. **Excel function compatibility**: Neither library prioritizes this
5. **Interactive debugging**: Better than both via trace context managers

---

## Appendix: Full Code Examples

### JuliaActuary: Complete Insurance Calculation
```julia
using LifeContingencies
using MortalityTables
using FinanceModels
import LifeContingencies: V, ä

# Load mortality table
vbt2001 = MortalityTables.table(
    "2001 VBT Residual Standard Select and Ultimate - Male Nonsmoker, ANB"
)

# Define life
life = SingleLife(
    mortality = vbt2001.select[30],
    issue_age = 30
)

# Define interest
yield = FinanceModels.Yield.Constant(0.05)

# Combine into life contingency
lc = LifeContingency(life, yield)

# Calculate various products
whole_life = Insurance(lc)
term_10 = Insurance(lc, 10)
annuity = ä(lc)
annuity_term = ä(lc, 10, certain=5, frequency=4)

# Get present values
pv_wl = present_value(whole_life)
pv_term = present_value(term_10)
pv_ann = present_value(annuity)

# Inspect components
flows = cashflows(term_10)
survs = survival(term_10)
probs = probability(term_10)
benefits = benefit(term_10)

# Calculate reserves
reserve_5 = V(lc, 5)
reserve_10 = V(lc, 10)
```

### lifelib: Complete Projection Model
```python
import modelx as mx
import numpy as np
import pandas as pd

# Read model
model = mx.read_model('BasicTerm_M')

# Access projection for policy 1
proj = model.Projection[1]

# View policy attributes
issue_age = proj.Policy.issue_age
sum_assured = proj.Policy.sum_assured
policy_term = proj.Policy.policy_term

# View assumptions
mort_table = proj.Assumptions.mort_table()
lapse_rates = proj.Assumptions.lapse_rate(5)
expense_acq = proj.Assumptions.expense_acq()

# Calculate cashflows
premiums_t0 = proj.premiums(0)
claims_t0 = proj.claims(0)
expenses_t0 = proj.expenses(0)
net_cf_t0 = proj.net_cf(0)

# Calculate present values
pv_prems = proj.pv_premiums()
pv_claims = proj.pv_claims()
pv_net = proj.pv_net_cf()

# Trace dependencies
deps = proj.pv_net_cf.precedents()
print(f"PV net CF depends on: {deps}")

users = proj.premiums.succs()
print(f"Premiums is used by: {users}")

# Calculate for time series
time_range = range(proj.max_proj_len())
premiums_series = [proj.premiums(t) for t in time_range]
claims_series = [proj.claims(t) for t in time_range]

# Create DataFrame
df = pd.DataFrame({
    'time': time_range,
    'premiums': premiums_series,
    'claims': claims_series,
    'net_cf': [proj.net_cf(t) for t in time_range]
})
```

---

## References

### JuliaActuary
- Website: https://juliaactuary.org/
- GitHub: https://github.com/JuliaActuary
- LifeContingencies.jl: https://github.com/JuliaActuary/LifeContingencies.jl
- MortalityTables.jl: https://github.com/JuliaActuary/MortalityTables.jl
- Community: Zulip chat, GitHub discussions

### lifelib
- Website: https://lifelib.io/
- GitHub: https://github.com/lifelib-dev/lifelib
- modelx: https://modelx.io/
- Documentation: https://lifelib.io/projects/simplelife.html

### Additional Resources
- Julia for Actuaries (SOA): https://www.soa.org/sections/technology/technology-newsletter/2021/october/att-2021-10-loudenback-vanguelov/
- Actuarial modeling best practices: Various industry sources on transparency, auditability, model governance

---

## Document Metadata
- **Created**: 2025-11-10
- **Author**: Research analysis for Gaspatchio project
- **Purpose**: Inform API design decisions for Gaspatchio ActuarialFrame
- **Status**: Complete initial analysis
