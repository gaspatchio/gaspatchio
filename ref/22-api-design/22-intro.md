# Gaspatchio Life Insurance API – Rails-Inspired Design

## Introduction & Philosophy

Gaspatchio is a high-performance actuarial modeling framework that pairs Python’s simplicity with Rust’s speed. The goal of its API is to be “actuary-native” — intuitive for actuaries much like Ruby on Rails feels natural to web developers. A Rails-inspired approach emphasizes convention over configuration, sensible defaults, and expressive syntax. In Gaspatchio, this means an API that meets actuaries where they work (spreadsheets, life tables, cash flow models) and reads like the formulas they know.

- **Great Defaults & Convention**: Common actuarial tasks should work out-of-the-box with minimal setup. For example, assumption tables can be loaded in whatever format you have — the system auto-detects keys and values without heavy ETL prep. If you follow standard naming or structures, Gaspatchio will “just do the right thing,” like Rails scaffolding.
- **Expressiveness & Readability**: API methods use clear actuarial terminology. Code should be self-explanatory, reading like English or well-known notation. An actuary should recognize `.survival_probability()`, `.present_value()`, or `.qx()` at a glance. The syntax favors fluent chaining and formula-like expressions over boilerplate.
- **Discoverability & Intuition**: Functions are grouped into logical domains (mortality, finance, reserves, projection, etc.) so you can guess where to find what you need. Namespaces like `af.mortality` or `af.reserves` make the API highly discoverable with clear autocompletion cues.
- **LLM-Ready Design**: Every public method is richly documented with actuarial examples and verified outputs, and the API offers introspection utilities (e.g., `af.help()`, `af.mortality.guide()`). Error messages and trace outputs are explanatory, enabling both humans and tools to debug or build models. A debug mode can produce a step-by-step breakdown of formula calculations — an audit trail for computed values.

In short, the Gaspatchio Life Insurance API is designed to be an expressive DSL for actuaries that hides performance complexities, encourages best practices, and is as welcoming as Rails’ scaffolding — without forcing actuaries to learn a new language. Python code can read like textbook actuarial math or Excel formulas, while Gaspatchio handles the heavy lifting.

### Core API Structure — ActuarialFrame and Domain Accessors

At the heart of Gaspatchio is the ActuarialFrame, a DataFrame tailored for actuarial modeling. It behaves like Pandas/Polars but with domain-specific capabilities. ActuarialFrame supports both column-level and frame-level operations via namespaced accessors. In practice this means the frame has attributes for each domain (e.g., `.mortality`, `.finance`, `.reserves`, `.projection`), and each column also exposes these as sub-properties for fluent chaining.

```python
# Frame-level operation: add timeline columns based on dates
af = af.date.create_timeline("issue_date", "expiry_date", freq="M")

# Column-level operations: use domain methods on specific columns
af["valuation_date"] = af["issue_date"].date.add_months(af["duration"])  # add months to a date column
af["pv_cashflow"]    = af["cashflow"].finance.discount(rate=0.05, periods=af["t"])  # present value of cashflow column
```

Domain namespacing keeps the API organized and mirrors how actuaries compartmentalize tasks (mortality, interest, lapse, etc.). Accessors are registered for strong autocompletion: type `af.mortality.` and your IDE can list available methods.

**Frame vs Column Context**: Many functions come in two flavors — frame-level (creating new columns or summary results) and column-level (transforming a single column). Call `af.projection.*` for frame-level projection outputs; call `af["col"].date.*` to transform one column. Operations are functional/immutable by default to align with Polars-style lazy transformations and to avoid unintended side effects.

Finally, ActuarialFrame supports two execution modes: a debug mode for step-by-step traces and an optimized mode for batched high-performance execution. The API stays the same; you can instantiate `af = ActuarialFrame(data, mode="debug")` for development and switch to `mode="optimize"` for production. Introspection (e.g., `.trace()`) is available without changing your modeling code.

---

### Mortality and Survival Models (`af.mortality`)

Life insurance modeling starts with mortality. The `af.mortality` namespace provides actuary-friendly functions for common survival model calculations: one-year death/survival probabilities (qₓ/pₓ), multi-period survival, life expectancy, and life table generation. Use English-like functions or classic notation — both styles yield the same results.

- **`qx(table=..., **keys)`**: One-year mortality rate qₓ.
- **`px(table=..., **keys)`**: One-year survival rate pₓ = 1 − qₓ.
- **`survival_probability(table=..., from_age=..., years=n)`**: n-year survival probability from a starting age.
- **`life_expectancy(table=..., age=x)`**: Expected future lifetime eₓ.
- **`life_table(table=..., radix=100000)`** (frame-level): Generate a complete life table with lₓ, dₓ, qₓ, pₓ, etc.

Examples:

```python
# English-like usage: clear and descriptive
af["five_year_survival"] = af.mortality.survival_probability(
    table="BaseMortality",
    from_age=af["issue_age"],
    years=5,
)
```

```python
# Shorthand usage: using px() in a chain for the same result
af["five_year_survival"] = af["issue_age"].mortality.px(table="BaseMortality", years=5)
```

```python
# Fetch one-year mortality and survival and then compute multi-year survival explicitly
af["qx"] = af["issue_age"].mortality.qx(table="BaseMortality")
af["px"] = af["issue_age"].mortality.px(table="BaseMortality")
af["five_year_survival_manual"] = af["px"] ** 5  # simplified illustration
```

```python
# Life expectancy at issue
af["life_expectancy_at_issue"] = af.mortality.life_expectancy(
    table="BaseMortality",
    age=af["issue_age"],
)
```

---

### Financial Functions and Reserves (`af.finance` & `af.reserves`)

Financial calculations — present values, discount factors, accumulating interest — are central to pricing and valuation. `af.finance` offers time value of money operations; `af.reserves` combines cash flows with mortality to compute reserves and premiums.

Finance key functions:

- **`discount(rate, periods)`**: Compute discount factor(s); element-wise for columns or arrays.
- **`accumulate(rate, periods)`**: Growth factor calculation (inverse of discount).
- **`npv(rate, cashflow_list)`** (frame-level): Net present value of periodic cash flows.
- **`irr(cashflow_list)`** (frame-level): Internal rate of return for a series of cash flows.

Reserves key functions:

- **`net_single_premium(amount, mortality_table, interest_rate)`**: PV of benefit (death/maturity) — the net single premium.
- **`level_premium(benefit_stream, mortality_table, interest_rate, term=n)`**: Solve for constant premium that funds a given benefit stream.
- **`gross_premium_reserve(benefits, premiums, rate, mortality_table=None, duration=t)`**: Prospective reserve at duration t: PV(benefits) − PV(premiums).

Examples:

```python
# Present value of list cashflows
af["PV_cashflows"] = af["cashflows"].finance.present_value(rate=0.03)  # synonym of npv
```

```python
# Net single premium at issue (present value of death benefit)
af["NSP"] = af.reserves.net_single_premium(
    amount=af["face_amount"],
    mortality_table="BaseMortality",
    interest_rate=0.03,
)

# Reserve at year 5 (prospective): PV of future benefits - PV of future premiums at t=5
af["reserve_5"] = af.reserves.gross_premium_reserve(
    benefits=af["benefit_cashflows"],
    premiums=af["premium_cashflows"],
    rate=0.03,
    duration=5,
)
```

Both namespaces favor returning new data (not modifying in place) to keep lineage clear and reproducible.

---

### Projection and Inforce Management (`af.projection` and `af.date`)

Projection of cash flows and inforce counts is core to reserving, pricing, and ALM. `af.date` helps generate time indices and manage dates; `af.projection` simulates or aggregates values across time steps. Defaults avoid exploding data and leverage Polars list operations for vectorized iteration.

Key functions:

- **`date.create_timeline(start_col, end_col, freq)`** (frame-level): Generate timeline indices or list-of-period structures.
- **`rollforward(initial, rate_col=None, periods=n)`** (frame/column): Declaratively roll forward a value through periods given survival/retention or growth rates.
- **`project_cashflows(assumptions=..., periods=n)`** (frame-level): High-level method to generate premium/benefit (and related) cash flow arrays using assumptions.

Examples:

```python
# 1. Create a timeline of years in force for each policy (from issue to expiry)
af = af.date.create_timeline("issue_date", "expiry_date", freq="Y")  # yearly timeline

# 2. Roll forward inforce count, starting at 1, using persistency rates
af["inforce_by_year"] = af.projection.rollforward(initial=1, rate_col=af["annual_persistency"])
```

```python
# High-level projection of premiums and claims for 30 years (or until earlier termination)
af = af.projection.project_cashflows(periods=30)
```

```python
# Override year 5 premium to zero for policies with a premium holiday
af["premium_cashflows"] = af["premium_cashflows"].arr.set(5, 0)
```

These tools align with time-based vector operations; conceptually iterative calculations compile down to optimized Polars expressions for scale.

---

### Product Design and Pricing (`af.product`)

The `af.product` namespace provides higher-level routines to calculate premiums, profitability metrics, and perform what-if analyses.

Key functions:

- **`calculate_premium(**parameters)`**: Flexible premium calculation; vectorizes over frame columns.
- **`profit_metrics(premium, assumptions=...)`**: Compute loss ratio, PV of profits, IRR, payback, etc.
- **`sensitivity_analysis(param, ±delta)`** (frame-level): Quick sensitivity to parameter changes.
- **`pricing_report(**inputs)`** (frame-level): One-off structured premium/profit breakdown for a policy or product line.

Examples:

```python
af["level_premium"] = af.product.calculate_premium(
    face_amount=af["face_amount"],
    term=af["policy_term"],
    mortality_table="BaseMortality",
    interest_rate=0.035,
)
```

```python
# First compute net cashflow per period (premiums minus claims minus expenses)
af["net_cashflow"] = (
    af["premium_cashflows"]
    - af["death_benefit_cashflows"]
    - af["expense_cashflows"]
)

# Now calculate IRR and profit margin given the priced premium
profit_results = af.product.profit_metrics(
    premium=af["level_premium"],
    cashflows=af["net_cashflow"],
)
print(profit_results)
```

```python
# How does the premium change if mortality rates worsen by 10%?
af.product.sensitivity_analysis(param="mortality_table", delta="*1.1", target=af["level_premium"])
```

---

### Reinsurance and Risk Sharing (`af.reinsurance`)

Apply common reinsurance arrangements to model cash flows and sums at risk. Instantly transform gross results into net-of-reinsurance (and reinsurer’s) views with minimal changes.

Key functions:

- **`quota_share(percentage, cols=[...])`**: Split specified columns into retained/ceded by proportion.
- **`surplus(retention, cols=[...])`**: Cede amounts above a retention per-policy to the reinsurer.
- **`stop_loss(attachment_point, cols=[...])`**: Cap aggregate losses and allocate excess to reinsurer.

Examples:

```python
af = af.reinsurance.quota_share(0.5, cols=["death_benefit_cashflows", "premium_cashflows"])
```

```python
af = af.reinsurance.surplus(retention=100000, cols=["death_benefit_cashflows"])
```

Functions return a new `ActuarialFrame`, making scenario comparisons straightforward.

---

### Experience Analysis and Assumption Management (`af.experience` and Assumptions API)

Gaspatchio supports A/E analysis and robust assumption table management with simple loading, vectorized lookups, and metadata.

Assumptions management:

- **`load_assumptions(name, source, **options)`**: Load tables (mortality, lapse, yield curves, etc.). Auto-detect keys/values; wide-to-long reshaping handled internally; indexed for fast lookup.
- **`assumption_lookup(key1, key2, ..., table_name)`**: O(1)-style hash lookups, vectorized over columns (no explosive joins); clear errors for missing keys.
- **Metadata & Listing**: `list_tables()`, `get_table_metadata(name)` to inspect loaded assumptions.

Experience analysis:

- **`actual_vs_expected(actual_col, expected_rate_col, exposure_col=None, by=...)`**: Compute A/E ratios and related statistics; supports grouping.
- **`exposure_analysis(event_col, count_col, by=...)`**: Compute exposures and incidence rates (e.g., lapse by duration).
- **`unlock_table(table_name, new_data)`**: Update/append to an assumption table (e.g., post-study adjustments).

Examples:

```python
# Load assumptions at the start (mortality and lapse tables, for example)
gas.load_assumptions("BaseMortality", "mortality_table.csv")  # auto-detects Age as key, q as value
gas.load_assumptions("LapseRates", lapse_df, id="Duration", value="lapse_rate")  # explicitly specifying columns

# Use those assumptions in the model
af["mortality_rate"]   = gas.assumption_lookup(af["age"],      table_name="BaseMortality")
af["lapse_rate"]       = gas.assumption_lookup(af["duration"], table_name="LapseRates")
af["annual_persistency"] = (1 - af["mortality_rate"]) * (1 - af["lapse_rate"])  # combined survival for the year
```

```python
# Calculate actual vs expected mortality by issue age
mortality_experience = af.experience.actual_vs_expected(
    actual="actual_deaths",
    expected_rate="mortality_rate",
    exposure="exposure",
    by="issue_age",
)
print(mortality_experience.head())
```

```python
# Suppose we want to scale mortality at ages 30–40 by 1.1 (based on high A/E)
tbl = gaspatchio_core.assumptions.TableBuilder.from_table("BaseMortality")
tbl.scale(lambda row: 1.1 if 30 <= row["Age"] <= 40 else 1.0)
gas.load_assumptions("BaseMortality_adj", tbl.to_frame())
```

Documentation is introspectable (`help(ActuarialFrame.mortality.survival_probability)`, `dir(af.mortality)`), with examples and recipes built-in to support IDEs and AI assistants.

---

### Conclusion

The Gaspatchio actuary API marries the domain specificity of actuarial science with the developer ergonomics of a Rails-like framework. Organized namespaces (`af.mortality`, `af.finance`, `af.reserves`, etc.), sensible defaults (auto-detected assumption schemas, default frequencies/units), and expressive, chainable syntax enable complex life insurance models to be written clearly and concisely.

The design is forward-looking and anticipates AI-assisted modeling. Rich metadata and explainability (e.g., trace outputs) make it feasible for tooling and LLMs to assist in writing, explaining, and auditing models. Focus on life insurance use cases ensures the familiar toolkit — life tables, present values, premiums, projections, reserves, and experience analysis — is first-class, scalable, and performant.
