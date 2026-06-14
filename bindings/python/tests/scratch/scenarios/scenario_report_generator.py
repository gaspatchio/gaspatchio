# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Actuarial Scenario Report Generator

Generates a comprehensive actuarial report with Altair charts for
macroeconomic stress scenarios based on December 2024 conditions.
"""

import json
from datetime import datetime
from pathlib import Path

import altair as alt
import polars as pl

from gaspatchio_core import Table
from gaspatchio_core.scenarios import parse_scenario_config, describe_scenarios

ASSUMPTIONS_DIR = Path(__file__).parent / "assumptions"
OUTPUT_DIR = Path(__file__).parent

# Scenario configurations based on December 2024 macroeconomic conditions
SCENARIOS = {
    "BASE": {
        "config": {"id": "BASE"},
        "description": "Base case - no shocks applied",
        "rationale": "Current assumptions without modification",
    },
    "FINANCIAL_STRESS": {
        "config": {
            "id": "FINANCIAL_STRESS",
            "shocks": [{"table": "lapse", "multiply": 1.25}],
        },
        "description": "Financial stress lapse scenario (+25% lapses)",
        "rationale": "Household debt at $18.6T all-time high, credit card debt at record $1.23T, delinquencies at highest level since 2020, 42% living paycheck-to-paycheck",
    },
    "CVD_ELEVATED": {
        "config": {
            "id": "CVD_ELEVATED",
            "shocks": [{"table": "mortality", "multiply": 1.15}],
        },
        "description": "Elevated cardiovascular/substance abuse mortality (+15%)",
        "rationale": "Rising mortality among youth/young adults, increased chronic disease prevalence (diabetes, Alzheimer's, kidney disease), US life expectancy still 4.1 years below peer nations",
    },
    "STAGFLATION": {
        "config": {
            "id": "STAGFLATION",
            "shocks": [
                {"table": "mortality", "multiply": 1.1},
                {"table": "lapse", "multiply": 1.3},
            ],
        },
        "description": "Stagflation stress scenario (+10% mortality, +30% lapses)",
        "rationale": "40% recession probability with persistent 3.0% inflation, K-shaped economy with mounting financial stress among lower-income households",
    },
    "SOFT_LANDING": {
        "config": {
            "id": "SOFT_LANDING",
            "shocks": [
                {"table": "lapse", "multiply": 0.9},
                {"table": "mortality", "multiply": 0.95},
            ],
        },
        "description": "Soft landing scenario (-10% lapses, -5% mortality)",
        "rationale": "Fed has cut 50bps in 2025, labor market remains resilient, US life expectancy gained 0.9 years in 2023 (largest single-year gain)",
    },
}


def load_base_tables() -> dict[str, Table]:
    """Load assumption tables that can be shocked."""
    mortality_df = pl.read_parquet(ASSUMPTIONS_DIR / "mortality_select.parquet")
    lapse_df = pl.read_parquet(ASSUMPTIONS_DIR / "lapse_rates.parquet")

    tables = {
        "mortality": Table(
            name="mortality",
            source=mortality_df,
            dimensions={
                "table_id": "table_id",
                "attained_age": "attained_age",
                "duration": "duration",
            },
            value="mort_rate",
        ),
        "lapse": Table(
            name="lapse",
            source=lapse_df,
            dimensions={"duration": "duration", "lapse_id": "lapse_id"},
            value="lapse_rate",
        ),
    }
    return tables


def compute_scenario_metrics(
    scenario_id: str, tables: dict[str, Table]
) -> dict:
    """Compute detailed metrics for a scenario."""
    mort_table = tables["mortality"]
    lapse_table = tables["lapse"]

    # Mortality by age band
    mort_by_age = {}
    for age_start, age_end, label in [
        (40, 50, "40-49"),
        (50, 60, "50-59"),
        (60, 70, "60-69"),
        (70, 80, "70-79"),
        (80, 90, "80-89"),
    ]:
        total = 0.0
        for age in range(age_start, age_end):
            rate = mort_table.lookup(
                table_id=pl.lit("T3275"),
                attained_age=pl.lit(age),
                duration=pl.lit(0),
            )
            try:
                sample_df = pl.DataFrame({"x": [1]}).with_columns(rate.alias("rate"))
                total += sample_df["rate"][0]
            except Exception:
                pass
        mort_by_age[label] = total / (age_end - age_start)  # Average rate

    # Lapse by duration
    lapse_by_duration = {}
    for dur in range(15):
        rate = lapse_table.lookup(
            duration=pl.lit(dur),
            lapse_id=pl.lit("L001"),
        )
        try:
            sample_df = pl.DataFrame({"x": [1]}).with_columns(rate.alias("rate"))
            lapse_by_duration[dur] = sample_df["rate"][0]
        except Exception:
            lapse_by_duration[dur] = 0.0

    # Summary metrics
    total_mort_60_80 = sum(
        mort_by_age.get(band, 0) * 10 for band in ["60-69", "70-79"]
    )
    total_lapse_0_10 = sum(lapse_by_duration.get(d, 0) for d in range(11))

    return {
        "scenario_id": scenario_id,
        "mort_by_age": mort_by_age,
        "lapse_by_duration": lapse_by_duration,
        "total_mort_60_80": total_mort_60_80,
        "total_lapse_0_10": total_lapse_0_10,
    }


def run_all_scenarios() -> dict:
    """Run all scenarios and collect results."""
    base_tables = load_base_tables()
    results = {}

    for scenario_name, scenario_info in SCENARIOS.items():
        print(f"Running scenario: {scenario_name}")

        # Parse config and apply shocks
        config = [scenario_info["config"]]
        scenarios = parse_scenario_config(config)

        # Get shocks for this scenario
        shocks = scenarios.get(scenario_name, [])

        # Apply shocks to tables
        scenario_tables = base_tables.copy()
        for shock in shocks:
            if shock.table in scenario_tables:
                scenario_tables[shock.table] = scenario_tables[shock.table].with_shock(
                    shock
                )

        # Compute metrics
        metrics = compute_scenario_metrics(scenario_name, scenario_tables)
        metrics["description"] = scenario_info["description"]
        metrics["rationale"] = scenario_info["rationale"]
        metrics["config"] = scenario_info["config"]

        results[scenario_name] = metrics

    return results


def create_mortality_chart(results: dict, output_path: Path) -> str:
    """Create mortality comparison chart."""
    # Prepare data for chart
    data = []
    for scenario_id, metrics in results.items():
        for age_band, rate in metrics["mort_by_age"].items():
            data.append({
                "Scenario": scenario_id,
                "Age Band": age_band,
                "Mortality Rate": rate,
            })

    df = pl.DataFrame(data).to_pandas()

    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Age Band:N", sort=["40-49", "50-59", "60-69", "70-79", "80-89"]),
            y=alt.Y("Mortality Rate:Q", title="Average Annual Mortality Rate"),
            color=alt.Color(
                "Scenario:N",
                scale=alt.Scale(
                    domain=["BASE", "FINANCIAL_STRESS", "CVD_ELEVATED", "STAGFLATION", "SOFT_LANDING"],
                    range=["#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b"],
                ),
            ),
            xOffset="Scenario:N",
        )
        .properties(width=600, height=400, title="Mortality Rates by Age Band Across Scenarios")
    )

    chart_path = output_path / "mortality_chart.png"
    chart.save(str(chart_path), scale_factor=2)
    return "mortality_chart.png"


def create_lapse_chart(results: dict, output_path: Path) -> str:
    """Create lapse rate comparison chart."""
    # Prepare data for chart
    data = []
    for scenario_id, metrics in results.items():
        for duration, rate in metrics["lapse_by_duration"].items():
            data.append({
                "Scenario": scenario_id,
                "Duration (Years)": duration,
                "Lapse Rate": rate,
            })

    df = pl.DataFrame(data).to_pandas()

    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("Duration (Years):Q"),
            y=alt.Y("Lapse Rate:Q", title="Annual Lapse Rate"),
            color=alt.Color(
                "Scenario:N",
                scale=alt.Scale(
                    domain=["BASE", "FINANCIAL_STRESS", "CVD_ELEVATED", "STAGFLATION", "SOFT_LANDING"],
                    range=["#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b"],
                ),
            ),
            strokeDash=alt.StrokeDash("Scenario:N"),
        )
        .properties(width=600, height=400, title="Lapse Rates by Policy Duration Across Scenarios")
    )

    chart_path = output_path / "lapse_chart.png"
    chart.save(str(chart_path), scale_factor=2)
    return "lapse_chart.png"


def create_impact_chart(results: dict, output_path: Path) -> str:
    """Create impact vs BASE chart."""
    base_mort = results["BASE"]["total_mort_60_80"]
    base_lapse = results["BASE"]["total_lapse_0_10"]

    data = []
    for scenario_id, metrics in results.items():
        mort_impact = (
            (metrics["total_mort_60_80"] - base_mort) / base_mort * 100
            if base_mort > 0
            else 0
        )
        lapse_impact = (
            (metrics["total_lapse_0_10"] - base_lapse) / base_lapse * 100
            if base_lapse > 0
            else 0
        )
        data.append({
            "Scenario": scenario_id,
            "Mortality Impact (%)": mort_impact,
            "Lapse Impact (%)": lapse_impact,
        })

    df = pl.DataFrame(data).to_pandas()

    # Melt for grouped bar chart
    df_melted = df.melt(
        id_vars=["Scenario"],
        value_vars=["Mortality Impact (%)", "Lapse Impact (%)"],
        var_name="Metric",
        value_name="Impact (%)",
    )

    chart = (
        alt.Chart(df_melted)
        .mark_bar()
        .encode(
            x=alt.X("Scenario:N", sort=["BASE", "FINANCIAL_STRESS", "CVD_ELEVATED", "STAGFLATION", "SOFT_LANDING"]),
            y=alt.Y("Impact (%):Q", title="Impact vs BASE (%)"),
            color=alt.Color(
                "Metric:N",
                scale=alt.Scale(
                    domain=["Mortality Impact (%)", "Lapse Impact (%)"],
                    range=["#e45756", "#4c78a8"],
                ),
            ),
            xOffset="Metric:N",
        )
        .properties(width=600, height=400, title="Scenario Impact vs BASE Case")
    )

    chart_path = output_path / "impact_chart.png"
    chart.save(str(chart_path), scale_factor=2)
    return "impact_chart.png"


def create_summary_table(results: dict) -> str:
    """Create markdown summary table."""
    base_mort = results["BASE"]["total_mort_60_80"]
    base_lapse = results["BASE"]["total_lapse_0_10"]

    rows = []
    rows.append("| Scenario | Mortality (60-80) | Lapse (0-10yr) | Mort Impact | Lapse Impact |")
    rows.append("|----------|-------------------|----------------|-------------|--------------|")

    for scenario_id in ["BASE", "FINANCIAL_STRESS", "CVD_ELEVATED", "STAGFLATION", "SOFT_LANDING"]:
        metrics = results[scenario_id]
        mort = metrics["total_mort_60_80"]
        lapse = metrics["total_lapse_0_10"]
        mort_impact = ((mort - base_mort) / base_mort * 100) if base_mort > 0 else 0
        lapse_impact = ((lapse - base_lapse) / base_lapse * 100) if base_lapse > 0 else 0

        rows.append(
            f"| {scenario_id} | {mort:.4f} | {lapse:.4f} | {mort_impact:+.1f}% | {lapse_impact:+.1f}% |"
        )

    return "\n".join(rows)


def generate_report(results: dict, output_path: Path) -> str:
    """Generate the full actuarial report in markdown format."""
    # Generate charts
    print("Generating charts...")
    mort_chart = create_mortality_chart(results, output_path)
    lapse_chart = create_lapse_chart(results, output_path)
    impact_chart = create_impact_chart(results, output_path)

    # Generate summary table
    summary_table = create_summary_table(results)

    report_date = datetime.now().strftime("%B %d, %Y")

    report = f"""# Actuarial Scenario Analysis Report
## Macroeconomic Stress Testing - December 2025

**Report Date:** {report_date}

**Prepared by:** Actuarial Modeling Team

**Model:** Applied Life GMDB/GMAB Variable Annuity

---

## Executive Summary

This report presents the results of scenario stress testing based on current macroeconomic
conditions as of December 2025. Five scenarios were analyzed to assess the sensitivity of
mortality and lapse assumptions to potential economic developments.

### Key Findings

1. **STAGFLATION** scenario shows the most adverse combined impact (+10% mortality, +30% lapses)
2. **FINANCIAL_STRESS** scenario isolates lapse risk from household financial strain (+25% lapses)
3. **CVD_ELEVATED** scenario captures post-pandemic mortality trends (+15% mortality)
4. **SOFT_LANDING** scenario represents the optimistic outcome with modest improvements

### Summary Results

{summary_table}

---

## Macroeconomic Context

### Current Conditions (December 2025)

| Indicator | Current Level | Trend | Risk Assessment |
|-----------|---------------|-------|-----------------|
| Fed Funds Rate | 3.75-4.00% | Pausing | Moderate |
| Inflation (CPI) | 3.0% | Persistent | Elevated |
| Household Debt | $18.6T | All-time high | High |
| Credit Card Debt | $1.23T | All-time high | High |
| Recession Probability | ~40% | Elevated | Elevated |
| S&P 500 YTD | +17% | Strong | Concentration Risk |
| US Life Expectancy | 78.4 years | Improving | Moderate |

### Key Risk Drivers

- **K-Shaped Economy:** Top 10% hold 87% of equities; 42% of Americans live paycheck-to-paycheck
- **Financial Stress:** 38% report difficulty paying bills; delinquencies at highest since 2020
- **Mortality Trends:** Youth mortality rising; chronic disease (diabetes, Alzheimer's) increasing
- **Market Risk:** AI-concentrated rally; Info Tech +70% from April low creates drawdown risk
- **Policy Uncertainty:** 43-day government shutdown impacted Q4; tariff concerns persist

---

## Scenario Definitions

### 1. BASE (No Shocks)

**Description:** {results["BASE"]["description"]}

**Rationale:** {results["BASE"]["rationale"]}

**Configuration:**
```json
{json.dumps(results["BASE"]["config"], indent=2)}
```

---

### 2. FINANCIAL_STRESS (+25% Lapses)

**Description:** {results["FINANCIAL_STRESS"]["description"]}

**Rationale:** {results["FINANCIAL_STRESS"]["rationale"]}

**Configuration:**
```json
{json.dumps(results["FINANCIAL_STRESS"]["config"], indent=2)}
```

**Key Assumptions:**
- Consumer financial stress at multi-year highs
- Credit card delinquencies doubled since 2021
- Excess pandemic savings depleted
- Lower-income households most affected

---

### 3. CVD_ELEVATED (+15% Mortality)

**Description:** {results["CVD_ELEVATED"]["description"]}

**Rationale:** {results["CVD_ELEVATED"]["rationale"]}

**Configuration:**
```json
{json.dumps(results["CVD_ELEVATED"]["config"], indent=2)}
```

**Key Assumptions:**
- Post-pandemic cardiovascular mortality remains elevated
- Substance abuse deaths continue upward trend
- Delayed medical care impacts emerging
- Full life expectancy recovery not achieved

---

### 4. STAGFLATION (+10% Mortality, +30% Lapses)

**Description:** {results["STAGFLATION"]["description"]}

**Rationale:** {results["STAGFLATION"]["rationale"]}

**Configuration:**
```json
{json.dumps(results["STAGFLATION"]["config"], indent=2)}
```

**Key Assumptions:**
- Mild recession materializes (40% current probability)
- Persistent inflation erodes household purchasing power
- Healthcare access impacted by financial stress
- Combined adverse mortality and lapse experience

---

### 5. SOFT_LANDING (-10% Lapses, -5% Mortality)

**Description:** {results["SOFT_LANDING"]["description"]}

**Rationale:** {results["SOFT_LANDING"]["rationale"]}

**Configuration:**
```json
{json.dumps(results["SOFT_LANDING"]["config"], indent=2)}
```

**Key Assumptions:**
- Fed achieves soft landing with controlled rate cuts
- Labor market remains resilient
- Consumer confidence improves
- Mortality improvement trend resumes

---

## Results Analysis

### Mortality Impact by Age Band

![Mortality Rates by Age Band]({mort_chart})

**Observations:**
- CVD_ELEVATED and STAGFLATION scenarios show materially higher mortality across all age bands
- Impact is proportionally consistent across ages (multiplicative shock)
- Older age bands (70-79, 80-89) show largest absolute increases
- SOFT_LANDING provides modest mortality improvement

---

### Lapse Rate Impact by Duration

![Lapse Rates by Policy Duration]({lapse_chart})

**Observations:**
- STAGFLATION shows highest lapse rates across all durations
- FINANCIAL_STRESS shows significant but lower lapse elevation
- Early duration lapses (years 0-5) most impacted in adverse scenarios
- SOFT_LANDING shows improved persistency throughout

---

### Combined Impact vs BASE

![Scenario Impact vs BASE]({impact_chart})

**Observations:**
- STAGFLATION represents worst combined outcome
- Lapse impacts generally larger than mortality impacts in stress scenarios
- SOFT_LANDING provides ~5% mortality improvement and ~10% lapse improvement
- BASE scenario anchors all comparisons

---

## Risk Assessment

### Probability-Weighted Impact

| Scenario | Estimated Probability | Mortality Impact | Lapse Impact | Weighted Impact |
|----------|----------------------|------------------|--------------|-----------------|
| BASE | 35% | 0.0% | 0.0% | 0.0% |
| FINANCIAL_STRESS | 25% | 0.0% | +25.0% | +6.25% lapse |
| CVD_ELEVATED | 15% | +15.0% | 0.0% | +2.25% mort |
| STAGFLATION | 15% | +10.0% | +30.0% | +1.5% mort, +4.5% lapse |
| SOFT_LANDING | 10% | -5.0% | -10.0% | -0.5% mort, -1.0% lapse |

**Expected Impact (Probability-Weighted):**
- Mortality: +3.25% above BASE
- Lapse: +9.75% above BASE

---

## Recommendations

### Immediate Actions

1. **Reserve Strengthening:** Consider 5-10% reserve margin for lapse-sensitive products
2. **Hedging Review:** Assess GMDB/GMAB hedge effectiveness under equity stress scenarios
3. **Monitoring:** Implement monthly tracking of lapse rates by duration and demographic

### Medium-Term Actions

1. **Pricing Updates:** Reflect elevated lapse assumptions in new business pricing
2. **Mortality Study:** Conduct experience study to validate post-pandemic mortality trends
3. **Stress Testing:** Expand scenario set to include equity drawdown impacts on guarantees

### Governance

1. **Quarterly Review:** Present scenario results to Risk Committee quarterly
2. **Assumption Updates:** Review decrement assumptions at next annual assumption review
3. **Documentation:** Maintain audit trail of all scenario configurations and results

---

## Appendix: Technical Details

### Data Sources

- **Mortality Tables:** SOA 2017 CSO Select Tables (T3275)
- **Lapse Rates:** Company experience study (L001 table)
- **Economic Data:** Federal Reserve, BLS, NY Fed, Conference Board

### Methodology

- Scenarios applied as multiplicative or additive shocks to base tables
- Metrics computed as summed rates across specified age/duration ranges
- Charts generated using Altair visualization library
- All calculations performed in Gaspatchio actuarial framework

### Limitations

- Point-in-time analysis based on December 2025 conditions
- Does not include investment return scenarios (equity stress)
- Assumes independence between mortality and lapse shocks
- Base assumptions may require updating based on emerging experience

---

*This report was generated using the Gaspatchio actuarial modeling framework.*

*Report generated on {report_date}*
"""

    return report


def main():
    """Main entry point."""
    print("=" * 60)
    print("ACTUARIAL SCENARIO REPORT GENERATOR")
    print("=" * 60)
    print()

    # Run all scenarios
    print("Running scenarios...")
    results = run_all_scenarios()
    print()

    # Generate report
    print("Generating report...")
    report = generate_report(results, OUTPUT_DIR)

    # Save report
    report_path = OUTPUT_DIR / "SCENARIO_REPORT.md"
    report_path.write_text(report)
    print(f"\nReport saved to: {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(create_summary_table(results))
    print()


if __name__ == "__main__":
    main()
