# Practical Examples: Rails-Style Improvements for Gaspatchio

This document demonstrates concrete before/after examples showing how Rails principles can improve Gaspatchio's developer experience.

## 1. Convention Over Configuration

### Assumption Table Creation

**Before (Current Verbose Approach)**:
```python
# Lots of explicit configuration required
mort_df = pd.read_csv("mortality.csv")
mort_table = Table(
    name="mortality_2015_vbt",
    source=mort_df,
    dimensions={
        "Age": "Age",
        "Sex": "Sex", 
        "Smoking": "Smoking Status",
        "duration": MeltDimension(
            columns=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            name="duration",
            output_columns=["duration", "rate"]
        ),
    },
    value="rate",
    registry=registry
)
registry.register("mortality_table", mort_table)
```

**After (Rails-Style Convention)**:
```python
# Auto-detects standard actuarial formats
mort_table = MortalityTable.from_csv("mortality.csv")
# Automatically:
# - Detects Age, Sex, Smoking Status columns
# - Recognizes wide-format duration columns (1-10)
# - Registers with standard name based on filename
# - Infers this is select & ultimate format
```

### Timeline Creation

**Before**:
```python
af = af.date.create_projection_timeline(
    valuation_date=datetime(2024, 1, 1),
    projection_end_type="term_months",
    projection_end_value=240,
    projection_frequency="monthly",
    output_column="projection_months",
    filter_after_term=True,
    create_t_column=True,
    t_column_name="t"
)
```

**After**:
```python
# Sensible defaults for monthly projection
af = af.project_monthly(from="2024-01-01", months=240)
# Automatically creates: projection_months, t, and filters to term
```

## 2. Actuarial DSL Shortcuts

### Present Value Calculations

**Before**:
```python
# Calculate PV of death benefits with mortality decrements
af["survival_prob"] = (1 - af["mortality_rate"]).cumprod()
af["discount_factor"] = (1 / (1 + 0.04)) ** af["t"]
af["pv_death_benefit"] = (
    af["death_benefit"] * 
    af["mortality_rate"] * 
    af["survival_prob"] * 
    af["discount_factor"]
).sum()
```

**After**:
```python
# Rails-style declarative approach
af.actuarial.pv_death_benefits(
    benefit="death_benefit",
    mortality="mortality_rate", 
    interest=0.04
)
```

### Decrement Chains

**Before**:
```python
af["annual_prob_death"] = af["mortality_rate"]
af["annual_prob_lapse"] = (1 - af["mortality_rate"]) * af["lapse_rate"]
af["annual_prob_survival"] = (1 - af["mortality_rate"]) * (1 - af["lapse_rate"])
```

**After**:
```python
# Auto-generates standard decrement chain
af.decrements(mortality="mortality_rate", lapse="lapse_rate")
# Creates: prob_death, prob_lapse, prob_survival, prob_inforce
```

## 3. Smart Defaults and Auto-Detection

### Mortality Table Usage

**Before**:
```python
# Manual column mapping
af = af.with_columns([
    mortality_table.lookup(
        age="current_age",
        sex="gender", 
        smoking_status="smoker_flag",
        duration="policy_duration"
    ).alias("mortality_rate")
])
```

**After**:
```python
# Auto-detects columns by standard names
af.apply_mortality("2015-VBT")
# Finds: age/issue_age, sex/gender, smoking/smoker, duration/policy_year
```

### Date Calculations

**Before**:
```python
# Calculate policy year and month
af["policy_year"] = (af["projection_date"].dt.year() - af["issue_date"].dt.year())
af["policy_month"] = (
    (af["projection_date"].dt.year() - af["issue_date"].dt.year()) * 12 + 
    (af["projection_date"].dt.month() - af["issue_date"].dt.month())
)
af["policy_anniversary"] = (
    af["projection_date"].dt.month() == af["issue_date"].dt.month()
) & (
    af["projection_date"].dt.day() == af["issue_date"].dt.day()
)
```

**After**:
```python
# Smart date helpers
af.add_policy_dates()  # Auto-creates policy_year, policy_month, is_anniversary
```

## 4. ActiveRecord-Style Associations

### Model Definition

**Before**:
```python
class TermLifeModel:
    def __init__(self, data, assumptions):
        self.data = data
        self.mortality = assumptions["mortality"]
        self.lapse = assumptions["lapse"]
        self.expenses = assumptions["expenses"]
        
    def calculate(self):
        af = ActuarialFrame(self.data)
        # Manual assumption application...
```

**After**:
```python
class TermLifeModel(ActuarialModel):
    # Declarative associations
    has_assumption :mortality, table: "2015-VBT"
    has_assumption :lapse, table: "SOA-2019-Lapse"
    has_assumption :expenses, inline: {acquisition: 100, maintenance: 10}
    
    def calculate(self):
        # Assumptions auto-loaded and available
        self.apply_assumptions()  # One line applies all
```

## 5. Error Messages That Guide

### Missing Column Error

**Before**:
```
KeyError: 'mortality_rate'
```

**After**:
```
MissingActuarialColumn: Cannot find mortality rates

Did you forget to apply mortality assumptions?
  → af.apply_mortality("2015-VBT")

Or add mortality rates manually:
  → af["mortality_rate"] = ...

Available mortality columns: ['death_rate', 'qx', 'mortality']
```

### Type Mismatch Error

**Before**:
```
TypeError: unsupported operand type(s) for -: 'str' and 'int'
```

**After**:
```
ActuarialTypeError: Cannot subtract int from policy status (str)

Column 'policy_status' contains: ['Active', 'Lapsed', 'Death']
Did you mean to use the numeric 'inforce_flag' column instead?

Common pattern:
  → af["net_amount"] = af["gross_amount"] * af["inforce_flag"]
```

## 6. Testing Improvements

### Model Testing

**Before**:
```python
def test_term_life_calculation():
    data = create_test_data()
    assumptions = load_test_assumptions()
    model = TermLifeModel(data, assumptions)
    result = model.calculate()
    
    # Manual assertions
    assert result["death_benefit"].iloc[0] == 100000
    assert abs(result["premium"].iloc[0] - 1234.56) < 0.01
```

**After**:
```python
class TestTermLife(ActuarialTestCase):
    # Rails-style test helpers
    fixtures :simple_term_policy
    
    def test_death_benefit
        # Auto-loads fixture data
        assert_actuarial_equal(
            model.death_benefit,
            100_000,
            tolerance: 0.01
        )
    end
    
    def test_reserves_positive
        # Domain-specific assertions
        assert_all_positive model.reserves, 
            "Reserves should never be negative"
    end
```

## 7. Progressive Enhancement

### Beginner Mode

```python
# Super simple for beginners
model = TermLife.standard(
    face_amount=100_000,
    issue_age=35,
    term=20
)
results = model.project()  # Uses all defaults
```

### Intermediate Mode

```python
# More control when needed
model = TermLife(
    data=policies,
    mortality="2015-VBT-Smoker-Distinct",
    interest_rate=0.045,
    expense_loading=1.05
)
results = model.project(months=360)
```

### Advanced Mode

```python
# Full control for experts
model = TermLife(data=policies)
model.mortality = CustomMortalityTable(improvement=True)
model.calculation_engine = "rust"  # Direct Rust execution
model.optimize_for("gpu")  # GPU acceleration

# Custom calculation hooks
model.before_mortality do |af|
    af["mortality_adjustment"] = custom_underwriting_factor(af)
end

results = model.project()
```

## 8. File Organization Convention

**Before**: Flat structure, everything in one file

**After**: Rails-style organization
```
models/
  term_life/
    model.py              # Main model class
    calculations/         
      premiums.py         # Premium calculations
      reserves.py         # Reserve calculations
      cashflows.py       # Cashflow projections
    assumptions/
      mortality.csv       # Auto-loaded
      lapse.yaml         # Auto-loaded
      expenses.json      # Auto-loaded
    validations/
      business_rules.py   # Auto-applied
    reports/
      seriatim.py        # Standard output format
      summary.py         # Aggregate reports
    tests/
      test_model.py      # Auto-discovered
      fixtures/          # Test data
```

## 9. Method Chaining Enhancement

**Before**:
```python
# Disjointed operations
af = ActuarialFrame(data)
af = af.date.create_projection_timeline(...)
af["mortality_rate"] = mortality_table.lookup(...)
af["lapse_rate"] = lapse_table.lookup(...)
af["premium"] = premium_table.lookup(...)
af = af.filter(pl.col("t") <= pl.col("term"))
```

**After**:
```python
# Fluent interface
results = (ActuarialFrame(data)
    .project_monthly(240)
    .with_mortality("2015-VBT")
    .with_lapses("SOA-2019")
    .with_premiums(rate_per_thousand=12.50)
    .calculate_cashflows()
    .summarize()
)
```

## 10. Intelligent Bundling

**Before**: Install and configure multiple packages
```python
# Need to manually install and configure:
# - gaspatchio-core
# - numpy 
# - pandas
# - polars
# - various assumption tables
# - testing frameworks
```

**After**: Rails-style bundled experience
```bash
# One command includes everything
$ uv add gaspatchio[actuarial]

# Includes:
# - Core framework
# - Standard mortality tables (SOA, IRS, etc.)
# - Common calculation patterns
# - Testing utilities
# - Example models
# - Documentation
```

## Summary

These examples demonstrate how Rails principles can dramatically improve the Gaspatchio developer experience:

1. **Less Code**: Common patterns require 50-80% less code
2. **Clearer Intent**: Code reads more like actuarial notation
3. **Fewer Errors**: Conventions prevent common mistakes
4. **Faster Development**: Standard patterns accelerate development
5. **Better Onboarding**: Beginners can be productive immediately
6. **Maintained Power**: Advanced features remain available

The key is providing sensible defaults and conventions while maintaining the flexibility that actuaries need for complex calculations.