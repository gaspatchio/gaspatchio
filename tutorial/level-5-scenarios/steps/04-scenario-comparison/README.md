# Step 04 -- Scenario Comparison & Regulatory Reporting

The capstone of Level 5.  This step combines multiple named scenarios into a
regulatory-style stress test suite and produces a comprehensive report that
an actuary could present to a board or submit for an ORSA filing.

## What you will learn

- **Named scenarios as economic narratives** -- each scenario tells a story
  (pandemic, rate shock, mass lapse), not just "multiply table X by 1.2"
- **Multi-shock combinations** -- the COMBINED_STRESS scenario applies mortality,
  rate, expense, and lapse shocks simultaneously, revealing compounding vs
  diversification effects
- **`describe_scenarios()` for governance** -- auto-generate audit trails that
  document exactly what was changed and why, satisfying model governance requirements
- **Regulatory context** -- the report structure mirrors what regulators expect
  in ORSA (Own Risk and Solvency Assessment) submissions and IFRS 17 sensitivity
  disclosures

## Scenarios

| ID | Description | Shocks |
|---|---|---|
| BASE | Current best-estimate assumptions | None |
| PANDEMIC | Severe pandemic event | Mortality +50% ages 65+, +20% younger; lapses -30% |
| RATE_SHOCK | Sudden rate environment collapse | Risk-free rates -200bp |
| MASS_LAPSE | Policyholder confidence crisis | Lapse rates doubled |
| COMBINED_STRESS | Multi-factor adverse scenario | Mortality +30%, rates -100bp, expenses +20%, lapses +30% |

These scenarios are defined declaratively in `scenarios.json`.  The
`parse_scenario_config()` function converts them into executable shock objects.

## How to run

```bash
uv run python tutorial/level-5-scenarios/steps/04-scenario-comparison/run_scenarios.py
```

This creates `report/` containing:

- `scenario_comparison.png` -- grouped bar chart of PV net cashflows by scenario
  and product
- `report.md` -- the full regulatory stress test report

## Report structure

The generated report includes more sections than any previous step:

1. **Executive Summary** -- three auto-generated sentences covering the number
   of scenarios, worst case, and product-level sensitivity
2. **Scenario Configuration** -- table with scenario ID, narrative description,
   and parameter changes (from `describe_scenarios()`)
3. **Results Summary** -- all PV metrics across all scenarios with % change
   from base
4. **Per-Product Breakdown** -- separate tables for GMDB and GMAB products,
   revealing which product type is more affected by each scenario
5. **Scenario Comparison Chart** -- the grouped bar chart
6. **Key Risk Indicators** -- flags scenarios that exceed 10% (warning) or
   20% (breach) impact thresholds
7. **Key Findings** -- auto-generated bullet points including diversification
   analysis and threshold breach counts
8. **Audit Trail** -- timestamp, model metadata, projection length, and the
   full `describe_scenarios()` output

## What to look for

- **COMBINED_STRESS should be the worst-case scenario** -- when multiple
  adverse factors act together, the combined impact typically exceeds any
  single factor
- **GMAB products should be more sensitive to rate shocks** -- guaranteed
  maturity benefits have longer effective duration, making their present
  value more sensitive to discount rate changes
- **Diversification effects** -- compare the combined stress impact to the
  sum of individual stress impacts; the difference reveals whether risks
  compound or partially offset
- **Threshold breaches** -- the Key Risk Indicators section shows which
  scenarios exceed governance limits

## Regulatory context

### ORSA (Own Risk and Solvency Assessment)

Solvency II requires insurers to assess their own risk profile through
scenario analysis.  The structure of this report -- named scenarios with
narratives, threshold monitoring, and audit trails -- mirrors ORSA
requirements.

### IFRS 17 sensitivity disclosures

IFRS 17 paragraph 128 requires disclosure of "the effect of changes in
assumptions and estimates" on insurance contract liabilities.  The per-product
breakdown and scenario comparison tables directly support these disclosures.

## Key APIs used

| API | Purpose |
|---|---|
| `parse_scenario_config()` | Load scenario definitions from JSON |
| `Table.with_shock()` | Apply shocks to assumption tables |
| `describe_scenarios(format="markdown")` | Generate audit trail |
| `describe_scenarios(format="dict")` | Programmatic access to shock descriptions |
| `charts.scenario_bar_chart()` | Grouped bar chart |
| `charts.write_report()` | Assemble markdown report with tables and charts |
