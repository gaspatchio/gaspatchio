# Actuarial Scenario Modeling: A Practical Primer

## Table of Contents
1. [Why Scenarios Matter](#why-scenarios-matter)
2. [Types of Scenarios](#types-of-scenarios)
3. [Economic Scenario Generators (ESGs)](#economic-scenario-generators-esgs)
4. [Implementation Considerations](#implementation-considerations)
5. [Common Pitfalls](#common-pitfalls)
6. [GMXB-Specific Considerations](#gmxb-specific-considerations)
7. [Implementing Scenarios in Gaspatchio](#implementing-scenarios-in-gaspatchio)

---

## Why Scenarios Matter

### Risk Measurement

Scenarios are fundamental to modern actuarial risk management because they enable quantification of tail risk through metrics like **Value-at-Risk (VaR)** and **Conditional Tail Expectation (CTE)**.

**Value-at-Risk (VaR)**
- VaR is a quantile of the distribution of aggregate losses
- For example, VaR at the 99% probability level indicates the loss threshold that will be exceeded only 1% of the time
- Simple to understand but has limitations: it doesn't capture what happens beyond the threshold
- Fails to satisfy coherence axioms (not subadditive), which is why actuaries often prefer CTE

**Conditional Tail Expectation (CTE) / Tail Value-at-Risk (TVaR)**
- CTE quantifies the **expected value of the loss given that an event outside a given probability level has occurred**
- Also known as Expected Shortfall (ES) in Europe, or Tail Conditional Expectation (TCE)
- CTE is VaR plus the mean excess loss evaluated at VaR
- **Advantages**: More robust to sampling error, coherent risk measure, provides information about tail severity
- Widely used for stochastic reserves and solvency for US and Canadian equity-linked life insurance

The significance of CTE lies in its ability to provide a more comprehensive picture of risk compared to VaR. While VaR only provides a threshold value, CTE gives an idea of the expected loss beyond that threshold.

### Regulatory Requirements

**Solvency II (Europe)**

The Solvency Capital Requirement (SCR) is given by a 1-year VaR 99.5%: it is the minimum amount of capital that the insurer should have to cover potential losses over a one-year period with a probability of 99.5%.

- **Interest Rate Risk Sub-module**: Upward and downward shocks to the interest term structure
  - Shocks expressed as relative amounts (e.g., 42% shock for a 10-year rate)
  - Minimum absolute shock of 1% applied
  - EIOPA has noted that current standard formulas may underestimate actual risks

- **Equity Risk Sub-module**: Sensitivity to changes in equity prices and volatility
  - Type I equities (EEA/OECD): 39% shock
  - Type II equities (other markets, unlisted, commodities): 49% shock
  - Qualifying infrastructure equities: reduced charges (22%)

- Market SCR is calculated by aggregating risks using correlation matrices in both rising and falling rate regimes, taking the maximum

**US Statutory (C3 Phase II)**

- Introduced in 2005 for variable annuity capital requirements
- Actuarial Guideline XLIII (AG43) introduced in 2009 for statutory reserves
- Uses **Conditional Tail Expectation at 98th percentile (CTE 98)** for Total Asset Requirements
- RBC calculated as excess of Total Asset Requirement above statutory reserves
- Originally required identical 200 scenarios for all companies, with optional second sensitivity test
- Academy Interest Rate Generator (AIRG) historically used for real-world scenarios
- In 2020, NAIC engaged Conning, Inc. to develop new ESG addressing known deficiencies

### Hedging and Asset-Liability Management (ALM)

Scenarios enable insurers to:
- **Test hedge effectiveness** across diverse market conditions
- **Identify portfolio vulnerabilities** to specific risk factor combinations
- **Optimize asset allocation** by understanding downside risks
- **Stress test liquidity** under adverse withdrawal scenarios

For variable annuities with GMXB guarantees, dynamic hedging programs require nested stochastic projections to simulate hedge performance under various market paths.

---

## Types of Scenarios

### Deterministic vs. Stochastic

**Deterministic Scenarios**
- Single, prescribed path for each risk factor
- Examples: "New York 7" scenarios (pop-up, pop-down, gradual rise, etc.)
- Useful for:
  - Model validation (clear, interpretable movements)
  - Benchmarking across companies
  - Simple product testing
- Limitations: Don't capture volatility within each period or probability of extreme events

A deterministic simulation, with varying scenarios for future investment return, does not provide a good way of estimating the cost of providing guarantees because it does not allow for the volatility of investment returns in each future time period.

**Stochastic Scenarios**
- Multiple paths generated with random variation based on statistical models
- Captures underlying variability and extreme events
- Required for accurate guarantee valuation
- Typical counts: 100 to 10,000 scenarios depending on application
- Industry practice (2012 survey):
  - 87% test at least "New York 7" deterministic scenarios
  - 47% use stochastically generated interest rate scenarios (median: 100 scenarios)
  - Some generate 1,000-10,000 scenarios but select representative subsets (50-100)

Stochastic modeling builds volatility and variability (randomness) into the simulation and therefore provides a better representation of real life from more angles.

### Real-World vs. Risk-Neutral

**Real-World (Physical) Measure**
- Reflects realistic patterns of market prices and outcomes
- Used for risk management, capital calculations, reserving
- Incorporates actual risk premiums and historical trends
- The American Academy of Actuaries stresses modeling under real-world probability measures
- While risk-neutral measure is important for pricing, it is not useful when estimating the tails of the distribution which ultimately determines the risk exposure for life insurers

**Risk-Neutral Measure**
- Uses unrealistic assumptions about risk premiums
- No-arbitrage pricing framework
- Used primarily for derivative pricing
- All assets earn the risk-free rate in expectation
- Important for hedging calculations and option valuation

**Nested Stochastic Applications**

For variable annuities with dynamic hedging:
- **Outer loop**: Real-world scenarios for generating realistic distributions
- **Inner loop**: Risk-neutral scenarios for calculating derivative prices under no-arbitrage

### Prescribed Regulatory Scenarios vs. Internal Scenarios

**Prescribed Scenarios**
- Mandated by regulators (e.g., Solvency II standard formula, C3 Phase II AIRG)
- Ensure consistency across industry
- May not capture firm-specific risks
- Example: NAIC prescribed 200 scenarios for PBR calculations (VM-20, VM-21)

**Internal Scenarios**
- Company-generated using proprietary or third-party ESGs
- Tailored to specific portfolio characteristics
- Allow for sensitivity testing beyond regulatory minimum
- Require validation and governance

The prescribed scenario generator allows users to choose from the "full set of 10,000 scenarios," as well as representative scenario subsets of 1,000, 500, 200, and 50 scenarios.

### Interest Rate Scenarios

**Common Patterns**
1. **Parallel shifts**: All rates move up/down by same amount
2. **Steepening/flattening**: Long rates move more than short rates
3. **Twists**: Short and long rates move in opposite directions
4. **Pop-up/pop-down**: Immediate jumps followed by gradual reversion
5. **Gradual rise/fall**: Steady trends over projection period

**New York 7 Scenarios** (historical benchmark)
- Still tested by 87% of appointed actuaries as of 2012
- Provide clear movements useful for model validation
- Pop-down scenario expected to show larger asset prepayments
- Pop-up scenario expected to show larger cash surrenders

### Equity Scenarios

**Components**
- Index levels (S&P 500, international indices, sector funds)
- Dividend yields
- Equity volatility

**Survey findings (2012)**:
- ~33% of respondents include separate account equity return scenarios
- Of those: 40% use deterministic only, 60% use stochastic
- Number of equity indices modeled: 1 to 6+ (most common: 1 or 4)

---

## Economic Scenario Generators (ESGs)

### What They Produce

An ESG is a computer-based model that provides simulated examples of possible future values of various economic and financial variables, including:

1. **Interest rates**: Short rates, term structure, yield curves
2. **Equity indices**: Stock prices, dividend yields, volatility
3. **Credit spreads**: Corporate bonds, mortgage spreads
4. **Foreign exchange rates**
5. **Inflation**: Consumer price index, wage inflation
6. **Volatilities**: Interest rate vol, equity vol (VIX)

Economic scenario generators (ESGs) are comprehensive frameworks that allow actuaries and risk managers to grasp the long-term uncertainty underlying financial market values and economic variables.

### Common Models

**Hull-White Model (1990)**
- One of the most popular short-rate models
- Assumes normal distribution of interest rates
- Mean-reverting process
- Easily calibrated to current term structure
- Can produce negative rates
- **Advantages**: Simple, closed-form solutions exist, stable calibration
- **Calibration**: Uses normal distribution, fits swaptions and caps
- Research shows Hull-White outperforms Black-Karasinski in in-sample pricing tests

**Black-Karasinski Model (1991)**
- Lognormal distribution of interest rates
- Rates cannot go negative (advantageous in low-rate environments)
- Incorporates mean reversion within lognormal framework
- **Advantages**: No negative rates, better for high-volatility environments
- **Disadvantages**: More complex calibration, requires trinomial tree implementation
- Research shows Black-Karasinski is more effective for hedging interest rate risk of Bermudan swaptions

**Calibration Comparison**
- Hull-White: Tends to over-price low-strike options, under-price high-strike options
- Black-Karasinski: Reverse pricing bias
- Hull-White yields slightly more stable calibration over time for developed markets
- Black-Karasinski may be more appropriate for emerging markets with high rates and volatility

**Multi-Factor Models**
- Two-factor Hull-White: Separate factors for short and long rates
- Libor Market Model (LMM): Models forward LIBOR rates directly
- Heath-Jarrow-Morton (HJM): Models entire forward curve evolution

### Major ESG Providers

**a commercial provider Economic Scenario Generator (formerly CHESS)**
- Award-winning solution (Best ESG Software by Insurance ERM)
- State-of-the-art modeling catalog
- High-quality data for market-consistent and real-world applications
- Framework relies on six models: monetary policy, inflation, short rate, term structure, dividend yield, stock returns

**Academy Interest Rate Generator (AIRG)**
- Most commonly used real-world ESG for US actuaries historically
- Can generate 50 to 10,000 scenarios
- User must decide appropriate number for given use case
- Too few (e.g., 50) may not produce sufficient convergence
- Too many (e.g., 10,000) may result in infeasible runtimes
- In 2017, American Academy of Actuaries advised NAIC it could no longer maintain AIRG
- Conning, Inc. engaged in 2020 to develop replacement

**MavenBlue ESG**
- Offers both Risk Neutral and Real World scenario generation
- Vendor option for companies not using prescribed generators

**Conning ESG (New NAIC Standard)**
- In development to replace AIRG
- Anticipated to address known deficiencies in current generators
- Will be prescribed for VM-20, VM-21, and C3 Phase II RBC

### Calibration Considerations

1. **Market data quality**: Term structure, volatility surfaces, historical time series
2. **Calibration instruments**: Swaptions, caps/floors, bond prices
3. **Parameter stability**: Avoid overfitting to recent market movements
4. **Validation**: Backtest against historical scenarios, check tail properties
5. **Correlation structure**: Ensure realistic co-movements between risk factors
   - Most actuaries incorporate correlation in scenario generation using historical data or Academy of Actuaries frameworks
   - Key correlations: short/long rates, interest rates/equity returns, equity indices

6. **Regularization techniques**: For ill-posed calibration problems
   - Tikhonov regularization
   - Landweber iteration

---

## Implementation Considerations

### How Many Scenarios Are Typically Needed?

The answer depends on the application and convergence requirements:

| Application | Typical Range | Considerations |
|-------------|---------------|----------------|
| **Asset adequacy testing** | 100-1,000 | Median: 100 for stochastic testing |
| **PBR reserves (VM-20/VM-21)** | 200-10,000 | Prescribed generator offers subsets of 50, 200, 500, 1,000, 10,000 |
| **Solvency II SCR** | Depends on internal model approval | Standard formula uses prescribed shocks |
| **C3 Phase II RBC** | 200 (prescribed) | Plus optional sensitivity test |
| **Pricing/profitability** | 500-5,000 | Balance accuracy vs. runtime |
| **Model validation** | 7+ deterministic | "New York 7" still common benchmark |

**Convergence Testing**

Some actuaries test convergence by:
1. Running full 10,000 scenarios to establish baseline
2. Testing smaller subsets (e.g., 1,000, 500, 200, 50)
3. Comparing reserves/metrics to determine if smaller set is sufficient
4. Repeating test only when liabilities, assets, or economic environment materially change

**Scenario Reduction Techniques**

When full set is computationally prohibitive:
- **Scenario picker tools**: Embedded in prescribed ESGs (e.g., based on 20-year Treasury rate)
  - Caution: May not be effective for products sensitive to equity or other maturities
- **Random subset selection**: Simple but may miss important tail scenarios
- **Representative subset matching**: Choose subset matching mean, median, range, variance of full set
- **Clustering algorithms**: Group similar scenarios, select representative from each cluster
- **Moment matching**: Ensure subset preserves key statistical properties

**Regulatory Acceptance Criteria (VM-20 Example)**

Scenario reduction acceptable if:
1. Smaller set chosen from larger prescribed set
2. Scenario reserves of representative subset of policies consistent with full set
3. Full set would not result in materially greater reserve

### Computational Efficiency

**Single-Loop Projections**
- Standard actuarial projections: ~seconds to minutes per scenario
- 1,000 scenarios with 100 policies: ~hours on modern hardware
- Embarrassingly parallel: can distribute across cores/machines

**Nested Stochastic Challenges**

The computation of nested stochastic projections for a large VA portfolio is highly computationally intensive and often prohibitive because every policy needs to be projected over many paths for a long time horizon.

**Example Scale**
- 1,000 real-world scenarios (outer loop)
- 1,000 risk-neutral paths (inner loop)
- 30 years of yearly projections
- = 1,000,000 projections per policy

For a 20-year projection with weekly/monthly time steps, new inner level simulations are required at each time step of each scenario, creating a multiplicative increase in dimensionality.

**Mitigation Strategies**

1. **Metamodeling / Proxy Models**
   - Build predictive model on representative policies
   - Use tractable analytic functions to replace inner simulation
   - Significant runtime gains (seconds vs. hours)

2. **Sample Recycling**
   - Identify reference outer scenarios
   - Recycle inner loop samples for similar target scenarios
   - Reduces number of inner simulations needed

3. **Regression Methods**
   - Combine information from different risk factor realizations
   - Standard nested simulation: MSE converges at κ^(-2/3)
   - Regression method: MSE converges at κ^(-1) until hitting asymptotic bias

4. **Dynamic Importance Allocation**
   - Non-uniform allocation of inner simulations
   - Focus computational effort on critical scenarios
   - Balance between efficiency and accuracy

5. **Parallel Processing**
   - Distribute outer scenarios across compute nodes
   - GPU acceleration for inner loops
   - Cloud-based elastic scaling

### Gaspatchio-Specific Efficiency Patterns

From the knowledge base, Gaspatchio recommendations:

**Use Polars' Lazy Evaluation**
- Build computation graphs that optimize across scenarios
- Avoid materializing intermediate results per scenario

**Vectorize Across Scenarios**
- Add scenario dimension to ActuarialFrame
- Process all scenarios in single pipeline
- Leverage Polars' columnar operations

**Avoid Python Loops**
- Never use `map_elements` or Python loops over scenarios
- Express logic as Polars expressions that parallelize automatically

**Scenario as a Dimension**
- Treat scenario_id like any other model point attribute
- Join scenario-specific assumptions (interest rates, equity returns) by scenario_id and projection_period
- Calculate statistics (mean, percentiles, CTE) using group_by operations

---

## Common Pitfalls

### 1. Correlation Assumptions

**The Problem**
- Underestimating correlations in stress scenarios
- Assuming independence when assets are actually correlated
- Using historical correlations that break down in crises

**Best Practices**
- Test correlation assumptions under stress
- Consider non-linear dependence (copulas)
- Recognize that "correlations go to 1 in a crisis"
- Survey results: Most actuaries incorporate correlation using historical data or Academy frameworks
- Key correlations to model: short/long rates, interest/equity, multiple equity indices

### 2. Tail Risk Underestimation

**The Problem**
- Normal distribution assumptions miss fat tails
- Calibration to recent "calm" periods
- 99.5% VaR events happening more frequently than 1-in-200 years
- EIOPA noted Solvency II interest rate shocks underestimate actual movements

**Best Practices**
- Use heavy-tailed distributions when appropriate
- Stress test beyond regulatory minimums
- Consider "black swan" events not in historical data
- Validate tail properties: kurtosis, skewness
- Use CTE instead of VaR to capture tail severity

### 3. Model Risk

**The Problem**
- Over-reliance on single ESG or model specification
- Parameter uncertainty not reflected
- Model may not capture structural shifts (e.g., post-2008 regime change)

**Best Practices**
- Test multiple ESG models or parameterizations
- Ensemble approaches: combine outputs from multiple models
- Regular backtesting against actual market outcomes
- Document model limitations
- Consider "model uncertainty" capital add-ons

### 4. Calibration Drift

**The Problem**
- Parameters fit to historical data become stale
- Market regime changes not reflected
- Volatility calibration during calm periods underestimates crisis volatility

**Best Practices**
- Regular recalibration (quarterly/annually)
- Use rolling windows vs. full history
- Monitor "signposts" for regime changes
- Version control calibration assumptions
- Document rationale for parameter changes

### 5. Ignoring Non-Financial Risks

**The Problem**
- Scenarios focus on market risks
- Operational risks (model errors, fraud) not captured
- Pandemic/catastrophic mortality not in scenarios
- Cyber risks to asset management systems

**Best Practices**
- Integrate operational risk scenarios
- Stress test non-market risks (mortality spikes, expense overruns)
- Consider second-order effects (market crash → operational strain)

### 6. Policyholder Behavior Misspecification

**The Problem**
- Static lapse assumptions when behavior is dynamic
- Rational policyholder assumption may not hold
- Ignoring behavioral segmentation

**Best Practices**
- Implement dynamic lapse formulas
- Test sensitivity to behavior assumptions
- Use predictive analytics for segmentation (covered in next section)

---

## GMXB-Specific Considerations

### Guarantee Types and Stochastic Sensitivity

**GMDB (Guaranteed Minimum Death Benefit)**
- Guarantees minimum lump sum payout upon death
- Varieties: return of premium, 5% annual ratchet, combination benefits
- Highly sensitive to equity scenarios and mortality
- GMDB and GMIB are almost perfectly correlated (limited natural hedging)

**GMAB (Guaranteed Minimum Accumulation Benefit)**
- Guarantees minimum return on investments at contract maturity
- Sensitive to long-term equity performance
- GMAB and GMWB have low correlation (31%), offering natural hedging potential

**GMWB (Guaranteed Minimum Withdrawal Benefit)**
- Guarantees return of entire initial investment regardless of fund performance
- Most complicated rider due to high path-dependency
- Sensitive to sequence of returns, not just terminal values
- Requires nested stochastic for accurate valuation

**GMIB (Guaranteed Minimum Income Benefit)**
- Guarantees minimum level of lifetime income
- Exposed to equity risk, interest rate risk, and longevity risk
- Almost perfectly correlated with GMDB

### How Scenarios Affect Guarantee Costs

**In-the-Money Scenarios**
- Low equity returns → high guarantee value → increased reserves
- Extended periods of poor performance compound liabilities
- Interest rates affect discounting and reinvestment

**Out-of-the-Money Scenarios**
- Strong equity returns → minimal guarantee value
- But high volatility still creates option value

**Volatility Impact**
- Higher volatility increases option value even if expected return unchanged
- Path-dependent features (ratchets, GMWB) extremely sensitive to volatility
- Stochastic models capture this; deterministic models do not

**CTE Calculations**
- Variable annuity reserves use CTE 98 (US) or CTE 95 (Canada)
- Focus on worst 2-5% of scenarios
- These are precisely the scenarios where guarantees are deeply in-the-money
- Small changes in tail assumptions → large reserve impacts

### Dynamic Policyholder Behavior Under Different Scenarios

**The Economics of Surrender**

Dynamic lapses are unexpected lapses primarily influenced by interest rates and/or equity market changes.

Policyholder behavior compares:
- **Value of staying**: Current account value + PV of future guarantee
- **Value of leaving**: Surrender value + alternative investment opportunity

**Dynamic Adjustment Factor (DAF) Framework**

```
DAF = Min{Factor_Cap, Max[Floor_Factor, Y × (AV/GV)^Power]}
```

Where:
- **AV**: Account Value (current market value)
- **GV**: Guarantee Value (what policyholder sees on statements)
- **Factor_Cap**: Typically 1.0 to 2.0
- **Floor_Factor**: Typically 0.5 to 1.0
- **Y**: Multiplier, typically 0.9 to 1.0
- **Power**: Sensitivity exponent

**Scenario-Dependent Behavior Patterns**

1. **Declining Equity Scenarios (AV < GV)**
   - Guarantee is in-the-money
   - Rational policyholder HOLDS (option value)
   - DAF < 1.0 → lower lapse rates
   - Anti-selection risk: healthy lives more likely to hold

2. **Rising Equity Scenarios (AV >> GV)**
   - Guarantee is out-of-the-money
   - Policyholder may surrender to access gains or get better product
   - DAF > 1.0 → higher lapse rates
   - But surrender penalties may deter

3. **Rising Interest Rate Scenarios**
   - Alternative fixed products become more attractive
   - Increased lapses even if AV ≈ GV
   - Reinvestment risk for insurer

4. **Volatile Scenarios**
   - Behavioral inertia may dominate
   - Policyholders may not react rationally to each fluctuation
   - Education level, age, wealth affect response

**Observed Behavior (Recent Studies)**

Recent study of dynamic lapses across 10 companies found that for the first time, significant shifts in interest rates and rapidly evolving equity markets made it possible to directly observe policyholder reactions.

- Policyholders more dynamic when surrender penalties are zero or low
- Behavioral segmentation matters: age, income, financial sophistication
- Historical data shows surrender rates influenced by state of economy

**Modeling Implications**

1. **Predictive Analytics Approach**
   - Set assumptions at granular level
   - Segment by demographics, policy characteristics
   - Better reinvestment opportunities → higher withdrawals, but probability varies by segment

2. **Scenario Testing**
   - Test wide range of DAF parameters
   - Sensitivity to "irrational" behavior (inertia, panic)
   - Consider bimodal behavior: sophisticated vs. unsophisticated policyholders

3. **Liquidity Risk**
   - Dynamic lapse formulas typically at aggregate level
   - Need segment-level analysis to identify liquidity concentrations
   - High-net-worth segment may be more liquid than overall population

### Hedge Effectiveness Testing

**The Hedging Challenge**

Variable annuity guarantees create option-like exposures:
- **Delta**: Sensitivity to equity level
- **Vega**: Sensitivity to volatility
- **Rho**: Sensitivity to interest rates
- **Gamma**: Convexity (delta changes with equity moves)

Insurers hedge using derivatives (futures, options, swaps).

**Why Scenarios Are Critical**

1. **Dynamic Hedging Paths**
   - Hedge ratios change as scenarios evolve
   - Rebalancing frequency and costs vary by scenario
   - Nested stochastic required: outer (real-world) × inner (risk-neutral for hedge pricing)

2. **Basis Risk**
   - Hedge instruments may not perfectly match liabilities
   - S&P 500 futures vs. diverse fund options
   - Correlation breakdowns in stress scenarios

3. **Transaction Costs**
   - More volatile scenarios → more rebalancing → higher costs
   - Costs can offset hedge benefits

4. **Counterparty Risk**
   - Derivatives expose insurer to counterparty default
   - Collateral requirements drain liquidity in stress scenarios

**Testing Framework**

1. **Pre-Hedge vs. Post-Hedge Risk**
   - Run scenarios without hedging: measure CTE
   - Run scenarios with hedging: measure residual CTE
   - Hedge effectiveness = reduction in CTE

2. **Scenario-Specific Performance**
   - Which scenarios have largest hedge errors?
   - Are errors systematic (bias) or random?
   - Do hedges worsen outcomes in any scenarios? (negative gamma trades)

3. **Stress Testing Hedge Program**
   - Extreme volatility scenarios (VIX spike)
   - Liquidity crises (bid-ask spreads widen)
   - Counterparty default mid-program
   - Regulatory constraints (inability to rebalance)

**Risk Management Governance**

- Set hedge effectiveness thresholds (e.g., residual CTE < 50% of pre-hedge)
- Monthly/quarterly backtesting: actual vs. modeled hedge performance
- Escalation triggers if hedge errors exceed tolerance
- Model validation: independent review of hedging assumptions

---

## Implementing Scenarios in Gaspatchio

Based on the Gaspatchio knowledge base, here are practical recommendations for implementing scenario functionality in actuarial models.

### Recommended Architecture

**1. Scenario as a Dimension in ActuarialFrame**

```python
import gaspatchio as gs
from datetime import date

# Load economic scenarios (e.g., from ESG output)
scenarios_df = pl.read_parquet("economic_scenarios.parquet")
# Columns: scenario_id, period, int_rate, equity_return, inflation, etc.

# Load model points
model_points_df = pl.read_parquet("model_points.parquet")

# Cross-join to create scenario × model_point combinations
af = ActuarialFrame(
    model_points_df.join(
        scenarios_df.select("scenario_id").unique(),
        how="cross"
    )
)

# Now af has dimensions: policy_id, scenario_id, ...
```

**2. Scenario-Specific Assumptions via Lookup Tables**

```python
# Create Table for interest rates by scenario and period
interest_table = gs.Table(
    name="interest_rates",
    source=scenarios_df,
    dimensions={
        "scenario_id": "scenario_id",
        "period": "period"
    },
    value="int_rate"
)

# In projection loop
af["discount_rate"] = interest_table.lookup(
    scenario_id=af["scenario_id"],
    period=af["projection_period"]
)
```

**3. Vectorized Projection Across Scenarios**

```python
def main(af: ActuarialFrame) -> ActuarialFrame:
    # Load assumption tables
    tables = load_assumption_tables()

    # Load and cross-join scenarios
    scenarios = load_scenarios()
    af = cross_join_scenarios(af, scenarios)

    # Create timeline (once per policy-scenario combination)
    af = af.date.create_projection_timeline(
        valuation_date=date(2025, 1, 1),
        projection_end_type="maximum_age",
        projection_end_value=99,
        projection_frequency="monthly"
    )

    # Lookup scenario-dependent assumptions
    af["discount_rate"] = tables.int_rates.lookup(
        scenario_id=af["scenario_id"],
        period=af["projection_period"]
    )
    af["equity_growth"] = tables.equity_returns.lookup(
        scenario_id=af["scenario_id"],
        period=af["projection_period"]
    )

    # Run standard calculations (vectorized across all scenarios)
    af["mortality_rate"] = tables.mortality.lookup(age=af["age"])

    # Dynamic lapse with DAF
    af["base_lapse_rate"] = tables.lapse.lookup(
        policy_year=af["policy_year"]
    )
    af["account_value"] = calculate_account_value(af)  # Scenario-dependent
    af["guarantee_value"] = calculate_guarantee_value(af)
    af["DAF"] = calculate_dynamic_adjustment_factor(
        af["account_value"],
        af["guarantee_value"]
    )
    af["lapse_rate"] = af["base_lapse_rate"] * af["DAF"]

    # In-force calculations
    af["P[IF]"] = calculate_inforce(af)

    # Cash flows (scenario-dependent via discount_rate, equity_growth, etc.)
    af["premium_cf"] = af["premium"] * af["P[IF]"]
    af["claims_cf"] = af["sum_assured"] * af["mortality_rate"] * af["P[IF]"]

    # Present values
    af["discount_factor"] = calculate_discount_factor(af["discount_rate"])
    af["pv_premiums"] = af["premium_cf"] * af["discount_factor"]
    af["pv_claims"] = af["claims_cf"] * af["discount_factor"]

    return af
```

**4. Risk Metric Calculation**

```python
# After projection, calculate risk metrics by grouping scenarios
results = af.collect()

# Reserve by scenario (sum across policies and periods)
scenario_reserves = (
    results
    .group_by("scenario_id")
    .agg([
        pl.sum("pv_claims").alias("total_pv_claims"),
        pl.sum("pv_premiums").alias("total_pv_premiums")
    ])
    .with_columns([
        (pl.col("total_pv_claims") - pl.col("total_pv_premiums")).alias("reserve")
    ])
    .sort("reserve", descending=True)
)

# Calculate VaR and CTE
import numpy as np

reserves_array = scenario_reserves["reserve"].to_numpy()
n_scenarios = len(reserves_array)

# VaR at 99.5% (Solvency II)
var_995 = np.percentile(reserves_array, 99.5)

# CTE at 99.5% (mean of worst 0.5%)
threshold_idx = int(np.ceil(n_scenarios * 0.995))
cte_995 = reserves_array[:threshold_idx].mean()

# CTE at 98% (C3 Phase II)
threshold_idx_98 = int(np.ceil(n_scenarios * 0.98))
cte_98 = reserves_array[:threshold_idx_98].mean()

print(f"VaR 99.5%: {var_995:,.0f}")
print(f"CTE 99.5%: {cte_995:,.0f}")
print(f"CTE 98%: {cte_98:,.0f}")
```

**5. Scenario Reduction Example**

```python
def select_representative_scenarios(
    full_scenarios_df: pl.DataFrame,
    n_scenarios: int,
    key_variable: str = "int_rate_20y"
) -> pl.DataFrame:
    """
    Select representative subset matching distribution of key variable.

    Args:
        full_scenarios_df: Full set of scenarios
        n_scenarios: Target number of scenarios
        key_variable: Variable to match distribution (e.g., 20-year rate)

    Returns:
        Subset of scenarios
    """
    # Calculate statistics of full set
    full_stats = full_scenarios_df.select([
        pl.col(key_variable).mean().alias("mean"),
        pl.col(key_variable).std().alias("std"),
        pl.col(key_variable).quantile(0.01).alias("q01"),
        pl.col(key_variable).quantile(0.50).alias("q50"),
        pl.col(key_variable).quantile(0.99).alias("q99")
    ])

    # Sort scenarios by key variable
    sorted_scenarios = full_scenarios_df.sort(key_variable)
    total_scenarios = len(sorted_scenarios)

    # Select evenly-spaced scenarios to cover distribution
    indices = [
        int(i * (total_scenarios - 1) / (n_scenarios - 1))
        for i in range(n_scenarios)
    ]

    subset = sorted_scenarios[indices]

    # Validate subset matches distribution
    subset_stats = subset.select([
        pl.col(key_variable).mean().alias("mean"),
        pl.col(key_variable).std().alias("std"),
        pl.col(key_variable).quantile(0.01).alias("q01"),
        pl.col(key_variable).quantile(0.50).alias("q50"),
        pl.col(key_variable).quantile(0.99).alias("q99")
    ])

    print("Full set statistics:")
    print(full_stats)
    print("\nSubset statistics:")
    print(subset_stats)

    return subset
```

### Performance Best Practices

From Gaspatchio knowledge base:

1. **Never use `map_elements` or Python loops over scenarios**
   - Polars expressions parallelize automatically
   - Express all logic as column operations

2. **Use lazy evaluation**
   - Build entire computation graph before `.collect()`
   - Polars optimizes across scenarios

3. **Minimize intermediate materialization**
   - Don't write intermediate results per scenario to disk
   - Compute risk metrics in single pipeline

4. **Leverage Polars' streaming mode for large scenario sets**
   - For 10,000+ scenarios with many policies
   - Process in chunks without full materialization

5. **Profile and optimize hot paths**
   - Scenario calculations will dominate runtime
   - Focus optimization on innermost loops

### Testing and Validation

**Model Validation Scenarios**

Even when using stochastic scenarios, test against deterministic benchmarks:

```python
def validate_with_new_york_7(model_fn, model_points_df):
    """Validate model using deterministic New York 7 scenarios."""

    ny7_scenarios = create_new_york_7_scenarios()

    results = []
    for scenario_name, scenario_df in ny7_scenarios.items():
        af = ActuarialFrame(model_points_df)
        # Inject deterministic scenario
        af = af.join(scenario_df, how="cross")

        af_result = model_fn(af)
        reserve = calculate_reserve(af_result)

        results.append({
            "scenario": scenario_name,
            "reserve": reserve
        })

        # Check expected behavior
        if scenario_name == "pop_down":
            # Expect larger asset prepayments, lower reserves
            assert reserve < baseline_reserve * 0.95
        elif scenario_name == "pop_up":
            # Expect larger surrenders, potentially higher reserves
            assert reserve > baseline_reserve * 1.05

    return pl.DataFrame(results)
```

**Convergence Testing**

```python
def test_scenario_convergence(af_base, scenario_counts=[50, 100, 200, 500, 1000]):
    """Test reserve convergence with increasing scenario counts."""

    full_scenarios = load_full_scenarios(10000)

    results = []
    for n in scenario_counts:
        subset = select_representative_scenarios(full_scenarios, n)
        af = af_base.join(subset, how="cross")
        af_result = main(af)

        metrics = calculate_risk_metrics(af_result)
        results.append({
            "n_scenarios": n,
            "cte_98": metrics["cte_98"],
            "cte_995": metrics["cte_995"],
            "runtime_seconds": metrics["runtime"]
        })

    results_df = pl.DataFrame(results)

    # Check convergence: CTE should stabilize
    cte_change = (
        results_df["cte_98"].tail(1).item() -
        results_df["cte_98"].tail(2).head(1).item()
    ) / results_df["cte_98"].tail(2).head(1).item()

    if abs(cte_change) < 0.01:  # Less than 1% change
        print(f"Converged at {results_df['n_scenarios'].tail(2).head(1).item()} scenarios")
    else:
        print(f"May need more scenarios. Recent change: {cte_change:.2%}")

    return results_df
```

### Documentation Standards

When implementing scenario functionality:

1. **Document scenario source**
   - ESG vendor and version
   - Calibration date and parameters
   - Whether prescribed or internal

2. **Document scenario count and reduction**
   - Number of scenarios used
   - Reduction method if applicable
   - Validation that subset is adequate

3. **Document key assumptions**
   - Correlations between risk factors
   - Dynamic lapse parameters (DAF formula)
   - Hedge assumptions if applicable

4. **Version control scenarios**
   - Store scenario files with metadata
   - Track recalibrations over time
   - Enable reproducibility of past results

---

## Sources

### Web Search Sources

#### Actuarial Scenario Modeling
- [Finalyse: Actuarial and Risk Modelling Solutions for Insurance](https://www.finalyse.com/actuarial-and-risk-modelling-for-insurance)
- [Stochastic Modeling E-book – International Actuarial Association](https://actuaries.org/product/stochastic-modeling/)
- [Stochastic modelling (insurance) - Wikipedia](https://en.wikipedia.org/wiki/Stochastic_modelling_(insurance))

#### Variable Annuities and GMXB
- [Valuation of variable annuities with guaranteed minimum withdrawal and death benefits via stochastic control optimization - ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0167668715000177)
- [Pricing and Risk Management of Variable Annuities](https://www.soa.org/4a5ea5/globalassets/assets/library/journals/actuarial-practice-forum/2006/october/apf0610_4.pdf)
- [Considerations in Market Risk Benefits - Public Policy White Paper](https://actuary.org/wp-content/uploads/2022/12/MRB_white_Paper.pdf)

#### Economic Scenario Generators
- [a commercial provider Economic Scenario Generator](https://www.a commercial provider.com/en/products/economic-scenario-generator)
- [Economic Scenario Generators - Actuary.org](https://www.actuary.org/content/economic-scenario-generators)
- [Economic Scenario Generators – A Practical Guide | SOA](https://www.soa.org/resources/research-reports/2016/2016-economic-scenario-generators/)
- [Economic Scenario Generators, Part III: In-depth ESG Case Study—Academy Interest Rate Generator](https://www.soa.org/digital-publishing-platform/emerging-topics/economic-scenario-generators-part-iii/)

#### Solvency II
- [The Standard Formula: A Guide to Solvency II – Chapter 8: Capital Requirements | Skadden](https://www.skadden.com/insights/publications/2024/06/the-standard-formula-a-guide-to-solvency-ii-chapter-8)
- [Solvency II solvency capital requirement for life insurance companies based on expected shortfall - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5744639/)

#### US Statutory C3 Phase II
- [C3 Phase II RBC and Reserves Project - Actuary.org](https://www.actuary.org/content/c3-phase-ii-rbc-and-reserves-project)
- [PRACTICE NOTE FOR THE APPLICATION OF C-3 PHASE II](https://actuary.org/wp-content/uploads/2017/11/life_c3.8.pdf)

#### Risk Metrics
- [An Introduction to Risk Measures for Actuarial Applications - CAS](https://www.casact.org/sites/default/files/database/studynotes_hardy4.pdf)
- [Value-at risk and tail-value-at-risk | Topics in Actuarial Modeling](https://actuarialmodelingtopics.wordpress.com/2017/12/28/value-at-risk-and-tail-value-at-risk/)
- [Tail value at risk - Wikipedia](https://en.wikipedia.org/wiki/Tail_value_at_risk)

#### Nested Stochastic Modeling
- [Dynamic importance allocated nested simulation for variable annuity risk measurement | Cambridge Core](https://www.cambridge.org/core/journals/annals-of-actuarial-science/article/dynamic-importance-allocated-nested-simulation-for-variable-annuity-risk-measurement/5BE66160C54CF6F715B4D10954418122)
- [Nested Stochastic Simulations: Bridging Risk & Pricing Models | Numerix](https://www.numerix.com/resources/webinar/nested-stochastic-simulations-bridging-risk-pricing-models)
- [Nested Stochastic Valuation of Large Variable Annuity Portfolios – DOAJ](https://doaj.org/article/57fe793f99f9405bab0c0522d220ae67)

#### Dynamic Policyholder Behavior
- [Considerations Regarding Dynamic Lapses in Actuarial Models](https://www.actuary.org/wp-content/uploads/2025/05/life-paper-dynamic-lapses.pdf)
- [Dynamic surrender assumptions - WTW](https://www.wtwco.com/en-us/insights/2023/05/dynamic-surrender-assumptions)
- [The Policyholder Puzzle: Cracking the code of dynamic lapses](https://www.theactuarymagazine.org/the-policyholder-puzzle/)

#### Interest Rate Models
- [Hull–White model - Wikipedia](https://en.wikipedia.org/wiki/Hull–White_model)
- [Black–Karasinski model - Wikipedia](https://en.wikipedia.org/wiki/Black–Karasinski_model)
- [Short rate models: Hull-White or Black-Karasinski?](https://www.econstor.eu/bitstream/10419/50684/1/584765029.pdf)
- [The Hull-White Model Analyzed (2025): Key Aspects, Mechanics](https://thetradinganalyst.com/hull-white-model/)

### Gaspatchio Knowledge Base

Scenario implementation guidance from `gspio knowledge` command covering:
- ActuarialFrame architecture for multi-scenario projections
- Performance patterns (vectorization, no Python loops, lazy evaluation)
- Assumption table lookups by scenario dimension
- Risk metric calculations using group_by operations

---

## Conclusion

Effective scenario modeling is essential for modern actuarial work, particularly for products with embedded options and guarantees. Key takeaways:

1. **Use sufficient scenarios** to capture tail risk (100-1,000 for most applications, 10,000 for regulatory)
2. **Test both deterministic and stochastic** scenarios for validation and risk measurement
3. **Implement dynamic policyholder behavior** that responds to scenario outcomes
4. **Calibrate and validate ESGs regularly** to ensure they reflect current market conditions
5. **Leverage computational efficiency techniques** (vectorization, scenario reduction, metamodeling) to make nested stochastic feasible
6. **Calculate CTE, not just VaR**, to understand tail severity
7. **In Gaspatchio, treat scenarios as a dimension** in ActuarialFrame for maximum performance

By following these principles, you can build robust actuarial models that accurately measure risk and support sound capital management decisions.
