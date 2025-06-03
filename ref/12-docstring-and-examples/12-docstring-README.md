# Gaspatchio Docstring Guidelines

## Quick Reference: Public vs Internal Method Requirements

### Public Methods (no leading underscore)
**REQUIRED for CI/CD to pass:**
- ✅ **Short Description** (first line)
- ✅ **Long Description** (detailed explanation)
- ✅ **When to Use** section (actuarial scenarios)
- ✅ **Examples** section (at least one executable example)
- ✅ **Parameters** (if applicable)
- ✅ **Returns** (if applicable)
- ✅ **All code examples MUST pass ruff linting**
- ✅ **All code examples MUST be executable with exact output**

### Internal Methods (leading underscore: `_method_name`)
**REQUIRED for CI/CD to pass:**
- ✅ **Short Description** (first line)
- ✅ **Long Description** (detailed explanation)
- ❌ **When to Use** section (OPTIONAL)
- ❌ **Examples** section (OPTIONAL)
- ✅ **Parameters** (if applicable)  
- ✅ **Returns** (if applicable)
- ✅ **If examples are included, they MUST pass ruff linting**
- ✅ **If examples are included, they MUST be executable with exact output**

### Internal Method Template (Complete - No Need to Read Further)

```python
def _internal_method_name(self, param1: type, param2: type = default) -> ReturnType:
    """One-line summary of internal method functionality.

    Detailed explanation of what this internal method does, its purpose
    within the class architecture, and any important implementation details
    that other developers should know about.

    Parameters
    ----------
    param1 : type
        Description of the parameter
    param2 : type, default value
        Description with default behavior explained

    Returns
    -------
    ReturnType
        What this returns and its purpose
    """
```

---

## Full Public Method Guidelines

This document provides comprehensive guidelines for writing high-quality docstrings for the Gaspatchio framework, with a focus on life insurance actuarial domain examples.

## Core Principles

1. **Domain Relevance**: All examples should use realistic life insurance actuarial scenarios
2. **Dual Examples**: Provide both scalar (single value) and vector (multiple values/list) examples where applicable
3. **Practical Value**: Examples should demonstrate real actuarial workflows and calculations
4. **Clear Structure**: Follow a consistent format that the docstring parser can process
5. **Executable Accuracy**: All examples MUST be executable and produce the exact output shown

!!! danger "Critical: Executable Examples Required"
    **All code examples will be executed by the CI/CD pipeline and MUST produce the exact output shown in the docstring.** Additionally, **all code will be linted using ruff for correctness and style compliance.** If the expected output doesn't match the actual output or if code fails linting, tests will fail. This means:
    
    - Every code block must be fully runnable
    - Code must pass ruff linting (style, imports, formatting)
    - Output blocks must show exact results (not approximations)
    - Data values must be realistic AND produce expected calculations
    - Import statements must be correct, complete, and properly ordered
    - No hypothetical or placeholder outputs allowed
    - Code must follow Python style guidelines (PEP 8 via ruff)

## Docstring Structure

### Required Sections

1. **Short Description** (First line)
   - One-line summary of what the function/method does
   - Should be clear and actionable

2. **Long Description** (After first line)
   - Detailed explanation of functionality
   - Domain context and use cases
   - Technical details if relevant

3. **When to Use** (Note section)
   - Bullet points of specific actuarial scenarios
   - Real-world applications in life insurance
   - Business value and context

4. **Parameters** (if applicable)
   - Name, type, and description for each parameter
   - Default values clearly stated
   - Domain-specific constraints or expectations

5. **Returns**
   - Type and description of return value
   - What the return represents in actuarial context

6. **Examples**
   - **Scalar Example**: Single policy/value calculations
   - **Vector Example**: Portfolio/batch operations
   - Use realistic data and scenarios

### Example Template

```python
def method_name(self, param1: type, param2: type = default) -> ReturnType:
    """One-line summary focusing on actuarial purpose.

    Detailed explanation of how this method supports actuarial calculations,
    what specific insurance operations it enables, and any important technical
    details about its implementation or behavior.

    !!! note "When to use"
        * **Scenario 1**: Specific actuarial use case (e.g., premium calculation)
        * **Scenario 2**: Another use case (e.g., reserve valuation)
        * **Scenario 3**: Business process it supports (e.g., regulatory reporting)

    Parameters
    ----------
    param1 : type
        Description in actuarial context (e.g., "Annual premium amount")
    param2 : type, default value
        Description with default behavior explained

    Returns
    -------
    ReturnType
        What this represents actuarially (e.g., "Present value of future benefits")

    Examples
    --------
    **Scalar Example: Single Policy Calculation**

    ```python
    from gaspatchio_core import ActuarialFrame

    # Single policy data
    data = {
        "policy_id": ["POL001"],
        "sum_assured": [100000],
        "annual_premium": [1200],
        "policy_year": [5]
    }
    af = ActuarialFrame(data)
    result = af.select(
        calc_value=af["column"].method_name(param1, param2)
    ).collect()
    print(result)
    ```

    ```text
    shape: (1, 1)
    ┌─────────────────┐
    │ calc_value      │
    │ ---             │
    │ f64             │
    ╞═════════════════╡
    │ 12345.67        │
    └─────────────────┘
    ```

    **Vector Example: Portfolio Analysis**

    ```python
    from gaspatchio_core import ActuarialFrame

    # Portfolio of policies
    data = {
        "policy_id": ["POL001", "POL002", "POL003"],
        "product_type": ["TERM", "WHOLE", "UL"],
        "face_amount": [100000, 250000, 500000],
        "duration": [5, 10, 3]
    }
    af = ActuarialFrame(data)
    result = af.group_by("product_type").agg(
        total_exposure=af["face_amount"].method_name().sum()
    ).collect()
    print(result)
    ```

    ```text
    shape: (3, 2)
    ┌──────────────┬────────────────┐
    │ product_type ┆ total_exposure │
    │ ---          ┆ ---            │
    │ str          ┆ f64            │
    ╞══════════════╪════════════════╡
    │ TERM         ┆ 100000.0       │
    │ WHOLE        ┆ 250000.0       │
    │ UL           ┆ 500000.0       │
    └──────────────┴────────────────┘
    ```
    """
```

## Domain-Specific Vocabulary

### Common Actuarial Terms to Use

- **Policies**: policy_id, policy_number, contract_number
- **Products**: TERM (Term Life), WHOLE (Whole Life), UL (Universal Life), VUL (Variable Universal Life), ANNUITY
- **Financial**: premium, sum_assured, face_amount, cash_value, surrender_value, death_benefit
- **Time**: policy_year, duration, issue_date, maturity_date, valuation_date
- **Risk**: mortality_rate, lapse_rate, morbidity_rate, persistency
- **Reserves**: statutory_reserve, GAAP_reserve, best_estimate_liability
- **Assumptions**: discount_rate, interest_rate, expense_assumption
- **Regulatory**: solvency_ratio, risk_based_capital, CSO_table (Commissioner's Standard Ordinary)

### Example Data Patterns

1. **Single Policy (Scalar)**
   ```python
   data = {
       "policy_id": ["POL12345"],
       "issue_age": [35],
       "sum_assured": [500000],
       "annual_premium": [6000],
       "policy_duration": [10]
   }
   ```

2. **Policy Portfolio (Vector)**
   ```python
   data = {
       "policy_id": ["POL001", "POL002", "POL003", "POL004"],
       "product_type": ["TERM", "TERM", "WHOLE", "UL"],
       "issue_age": [30, 45, 35, 50],
       "face_amount": [250000, 500000, 1000000, 750000],
       "premium_frequency": ["ANNUAL", "MONTHLY", "QUARTERLY", "ANNUAL"]
   }
   ```

3. **Time Series (Vector)**
   ```python
   data = {
       "policy_id": ["POL001", "POL001", "POL001"],
       "policy_year": [1, 2, 3],
       "premium_paid": [1200, 1200, 1200],
       "cash_value": [0, 1150, 2350],
       "death_benefit": [100000, 100000, 100000]
   }
   ```

## Specific Guidelines by Method Type

### String Operations

For string methods (like in `string_proxy.py`), focus on:
- Policy identifiers and codes
- Product names and categories
- Beneficiary information
- Underwriting notes and classifications

Example scenarios:
- Standardizing policy numbers
- Extracting rider codes
- Cleaning beneficiary names
- Parsing underwriting decisions

### Numeric Operations

For numeric methods, focus on:
- Premium calculations
- Reserve valuations
- Risk metrics
- Financial projections

Example scenarios:
- Calculating present values
- Aggregating exposures
- Computing loss ratios
- Projecting cash flows

### Date Operations

For date methods, focus on:
- Policy anniversaries
- Valuation dates
- Maturity calculations
- Duration analysis

Example scenarios:
- Calculating policy duration
- Finding next premium due date
- Determining benefit payment dates
- Age calculations

## Code Block Formatting

### Python Code Blocks
```python
# Use proper imports
from gaspatchio_core import ActuarialFrame
import polars as pl

# Include realistic data setup
data = {
    "policy_id": ["TERM-001", "WHOLE-002"],
    "annual_premium": [1200.00, 3500.00],
    "sum_assured": [250000, 500000]
}
af = ActuarialFrame(data)

# Show the operation clearly
result = af.select(
    premium_rate=(af["annual_premium"] / af["sum_assured"] * 1000).alias("rate_per_thousand")
).collect()
```

### Output Blocks
```text
shape: (2, 1)
┌───────────────────┐
│ rate_per_thousand │
│ ---               │
│ f64               │
╞══════════════════╡
│ 4.8              │
│ 7.0              │
└──────────────────┘
```

## Common Patterns

### 1. Risk Classification
```python
# Scalar: Single policy risk assessment
data = {"policy_id": ["POL001"], "age": [45], "smoker": [True]}

# Vector: Portfolio risk segmentation
data = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "age": [25, 45, 65],
    "smoker": [False, True, False]
}
```

### 2. Financial Calculations
```python
# Scalar: Single premium calculation
data = {"sum_assured": [100000], "age": [35], "term": [20]}

# Vector: Portfolio valuation
data = {
    "policy_id": ["P1", "P2", "P3"],
    "reserve": [10000, 25000, 45000],
    "duration": [5, 10, 15]
}
```

### 3. Regulatory Reporting
```python
# Scalar: Single policy statutory calculation
data = {"policy_id": ["POL001"], "net_amount_at_risk": [90000]}

# Vector: Aggregate reporting
data = {
    "line_of_business": ["TERM", "WHOLE", "UL"],
    "total_reserves": [1000000, 5000000, 3000000],
    "required_capital": [100000, 500000, 300000]
}
```

## Quality Checklist

Before submitting a docstring, ensure:

- [ ] Short description is clear and actuarial-focused
- [ ] "When to use" section has at least 3 realistic scenarios
- [ ] Both scalar and vector examples are provided (where applicable)
- [ ] Examples use proper life insurance terminology
- [ ] Data in examples is realistic (ages 20-80, reasonable premiums, etc.)
- [ ] **CRITICAL**: All code examples have been executed and output blocks verified
- [ ] **CRITICAL**: Code passes ruff linting without errors or warnings
- [ ] **CRITICAL**: Import statements are complete, correct, and properly ordered
- [ ] **CRITICAL**: No placeholder or hypothetical outputs used
- [ ] Code blocks are complete and runnable without modification
- [ ] Output formatting matches actual Polars output exactly
- [ ] Parameter descriptions include actuarial context
- [ ] Return value description explains actuarial meaning
- [ ] Numeric precision in outputs matches actual calculation results

## Example: Complete Docstring

Here's a complete example following all guidelines:

```python
def calculate_net_premium(self, mortality_rate: float, interest_rate: float) -> "ExpressionProxy":
    """Calculate net premium using equivalence principle for life insurance.

    Computes the net premium required to fund future death benefits based on
    mortality assumptions and interest rates, following the actuarial equivalence
    principle where present value of premiums equals present value of benefits.

    !!! note "When to use"
        * **Product Pricing**: Determine base premium rates for new life insurance products
        * **Reserve Valuation**: Calculate net premium reserves for statutory reporting
        * **Profitability Analysis**: Assess margin between gross and net premiums
        * **Experience Studies**: Compare actual to expected premiums using updated assumptions
        * **Regulatory Filings**: Compute minimum premiums for state insurance filings
        * **Portfolio Optimization**: Identify underpriced policies needing rate adjustments

    Parameters
    ----------
    mortality_rate : float
        Annual mortality rate (qx) from mortality table, typically between 0.0001 and 0.5
    interest_rate : float
        Annual effective interest rate for discounting, typically between 0.01 and 0.10

    Returns
    -------
    ExpressionProxy
        Net level annual premium per unit of sum assured

    Examples
    --------
    **Scalar Example: Single Term Life Policy Pricing**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["TERM-2024-001"],
        "issue_age": [35],
        "policy_term": [20],
        "sum_assured": [500000],
        "mortality_qx": [0.00142]  # Age 35 male nonsmoker
    }
    af = ActuarialFrame(data)
    result = af.select(
        net_premium_rate=af["sum_assured"].calculate_net_premium(
            mortality_rate=af["mortality_qx"],
            interest_rate=0.035
        ).alias("net_annual_premium") / af["sum_assured"]
    ).collect()
    print(result)
    ```

    ```text
    shape: (1, 1)
    ┌──────────────────┐
    │ net_premium_rate │
    │ ---              │
    │ f64              │
    ╞══════════════════╡
    │ 0.00137          │
    └──────────────────┘
    ```

    **Vector Example: Portfolio Premium Analysis by Product**

    ```python
    from gaspatchio_core import ActuarialFrame

    data = {
        "product_type": ["TERM10", "TERM20", "TERM30", "WHOLE"],
        "avg_issue_age": [30, 35, 40, 45],
        "avg_sum_assured": [250000, 500000, 750000, 1000000],
        "mortality_rate": [0.00089, 0.00142, 0.00245, 0.00421],
        "interest_assumption": [0.04, 0.035, 0.03, 0.025]
    }
    af = ActuarialFrame(data)
    result = af.select(
        af["product_type"],
        net_premium=af["avg_sum_assured"].calculate_net_premium(
            mortality_rate=af["mortality_rate"],
            interest_rate=af["interest_assumption"]
        ),
        premium_rate_per_1000=(
            af["avg_sum_assured"].calculate_net_premium(
                mortality_rate=af["mortality_rate"],
                interest_rate=af["interest_assumption"]
            ) / af["avg_sum_assured"] * 1000
        ).round(2)
    ).collect()
    print(result)
    ```

    ```text
    shape: (4, 3)
    ┌──────────────┬─────────────┬──────────────────────┐
    │ product_type ┆ net_premium ┆ premium_rate_per_1000 │
    │ ---          ┆ ---         ┆ ---                  │
    │ str          ┆ f64         ┆ f64                  │
    ╞══════════════╪═════════════╪══════════════════════╡
    │ TERM10       ┆ 214.66      ┆ 0.86                 │
    │ TERM20       ┆ 684.15      ┆ 1.37                 │
    │ TERM30       ┆ 1785.38     ┆ 2.38                 │
    │ WHOLE        ┆ 4105.26     ┆ 4.11                 │
    └──────────────┴─────────────┴──────────────────────┘
    ```
    """
```

## Final Notes

1. **Consistency**: Use the same terminology and data patterns across related methods
2. **Realism**: Ensure all numeric values are plausible for life insurance
3. **Completeness**: Every example should be self-contained and runnable
4. **Education**: Examples should teach both the method usage and actuarial concepts
5. **Testing**: All code examples MUST be validated by actual execution before submission

## Development Workflow for Docstring Examples

1. **Write the Code**: Create your example with realistic actuarial data
2. **Lint the Code**: Run `ruff check` and `ruff format` to ensure style compliance
3. **Execute Locally**: Run the example and capture the actual output
4. **Copy Exact Output**: Use the precise output format, including spacing and precision
5. **Verify Again**: Run once more to ensure consistency
6. **Final Lint Check**: Ensure the complete docstring passes ruff linting
7. **Submit**: Only after confirming the example executes correctly AND passes linting

!!! warning "Common Pitfalls to Avoid"
    - **Rounding Issues**: Don't round outputs manually - show what Polars actually produces
    - **Linting Failures**: Unused imports, incorrect formatting, or style violations will fail CI/CD
    - **Import Order**: Use ruff's import sorting (generally: stdlib, third-party, local imports)
    - **Import Errors**: Always test imports in isolation
    - **Data Type Mismatches**: Ensure your input data types produce expected calculations
    - **Column Name Typos**: Verify all column references are correct
    - **Output Formatting**: Polars output has specific spacing and alignment - match it exactly
    - **Line Length**: Keep lines under ruff's configured limit (typically 88 or 100 characters)

By following these guidelines, you'll create docstrings that are not only technically correct but also valuable learning resources for actuaries using Gaspatchio.
