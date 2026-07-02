# Scenario Modeling — Quick Reference

This reference covers actuarial details that come up when wiring a model
to scenario analysis: term-structure discounting, BEL composition, and
population scope checks. **For the scenario-running mechanics
themselves — `ScenarioRun`, shocks, aggregators, audit chain, the
two-script pattern — use the `gaspatchio-model-scenarios` skill.**

---

## Designing the Model for Scenario Runs

A model that wants to be runnable across scenarios needs one design hook:
an optional `assumptions_override` parameter so a `ScenarioRun.run()`
wrapper can hand shocked assumption tables back in.

```python
def main(af, assumptions_override=None):
    assumptions = assumptions_override or load_assumptions()
    ...
```

Keep the model function pure — per-policy calculations only. Population-level
operations (filtering, cross-portfolio aggregation, scenario orchestration)
belong in `run_scenarios.py`. See the `gaspatchio-model-scenarios` skill
for the full two-script pattern and the `ScenarioRun` plan.

---

## Term-Structure Discounting

For yield-curve scenarios, you don't pass a single flat rate — you build a
`Curve` and read discount factors off it.

### Flat Rate (Simple Case)

A flat curve is just a one-tenor curve:

```python
from gaspatchio_core import Curve

curve = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.025, 0.025])
# Inside the model:
af.df = curve.discount_factor(t=af["t_years"])
```

### Yield Curve (Term Structure)

```python
from datetime import date

from gaspatchio_core import Curve, Schedule

# Build the curve from a sparse zero-rate grid; Curve interpolates linearly
# on the rate between knot tenors.
curve = Curve.from_zero_rates(
    tenors=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
    rates=[0.04, 0.041, 0.042, 0.044, 0.046, 0.045, 0.044],
)

# Pull period-end year-fractions from the bound Schedule
sched = Schedule.from_calendar_grid(
    start_date=date(2025, 1, 31), n_periods=240, frequency="1M"
)
t_years = sched.cumulative_year_fractions()[1:]  # drop leading 0 to align
disc_factors = curve.discount_factor(t=t_years)
```

### Critical Details

- **`cumulative_year_fractions()` returns `n_periods + 1` values** — the
  leading 0 is the period start. Slice to `[1:]` to align with `n_periods`
  period-end cashflows.
- **At t=0, v(0) = 1.0 always** (no discounting at the first period).
- **Rate capping**: regulatory rate shocks often cap at a level (`MIN(rate + shock, cap)`).
  Check the basis before assuming the additive shock applies directly to the curve.
- **`Curve.discount_factor` accepts a Python list, `pl.Series`, `pl.Expr`,
  or `af["col"]`** — pick whichever fits the call site.

---

## Population Scope

When comparing against regulatory targets (EBS, BSCR), always verify the
population scope:

```python
# Excel EBS targets may only cover in-force policies
mp = mp.filter(pl.col("Policy number") <= 36)  # 36 in-force, not all 540
```

Running all policies against a 36-policy target produces ~50× inflated BEL.
Document the scope prominently in `run_scenarios.py`.

---

## BEL Composition

```python
bel = (
    pv_claims_death.sum()
    + pv_surrender_benefit.sum()
    + pv_total_expense.sum()
    - pv_premium_subtotal.sum()   # negative (income), so −sum() is positive
)
```

**Use `pv_premium_subtotal` not `pv_premium_paid`** — subtotal includes
SVER (surrender-value excess reserve). Missing SVER causes a systematic
~5% gap for policies with surrender values.

---

## Looking Up the Scenario Surface

For the canonical scenario API and patterns, invoke the
`gaspatchio-model-scenarios` skill. For one-off lookups:

```bash
uv run gspio docs "ScenarioRun" -t code_example
uv run gspio docs "for_each_scenario"
uv run gspio docs "MultiplicativeShock"
uv run gspio docs "Sum.over"
```
