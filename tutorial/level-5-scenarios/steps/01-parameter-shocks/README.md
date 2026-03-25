# Level 5 Step 01 -- Parameter Shocks

## What this step teaches

Parameter shocks are the simplest form of scenario analysis: apply a
multiplicative or additive change to an entire assumption table and
re-run the model. This step demonstrates the declarative JSON config
approach, where scenarios and their shocks are defined in a single
`scenarios.json` file.

## How scenarios.json works

Each entry in the JSON array is either a bare `{"id": "BASE"}` (no shocks)
or a scenario with a `shocks` list. Each shock targets a named assumption
table and specifies one operation:

| Key        | Meaning                                         |
|------------|-------------------------------------------------|
| `table`    | Name of the assumption table to shock            |
| `multiply` | Multiply all values by this factor               |
| `add`      | Add a constant to all values (e.g. +50 bps)      |
| `column`   | Target a specific column in a plain DataFrame     |

Example -- increase mortality by 20%:

```json
{
  "id": "MORT_UP_20",
  "shocks": [{"table": "mortality_select", "multiply": 1.2}]
}
```

## How to run

```bash
uv run python tutorial/level-5-scenarios/steps/01-parameter-shocks/run_scenarios.py
```

This produces a `report/` directory containing `tornado.png` and `report.md`.

## Key concepts

| API                        | Purpose                                          |
|----------------------------|--------------------------------------------------|
| `parse_scenario_config()`  | Convert JSON list into `dict[str, list[Shock]]`   |
| `Table.with_shock(shock)`  | Create a shocked copy of an assumption Table       |
| `assumptions_override`     | Pass shocked assumptions into `model.main()`       |
| `describe_scenarios()`     | Generate audit-trail markdown from shock specs     |

## What to look for in the tornado chart

The tornado chart ranks each scenario by the absolute change in total PV
of net cashflows versus BASE. Look for:

- **Which assumption has the biggest impact?** Interest rate shocks
  typically dominate because they affect both discount factors and
  investment income simultaneously.
- **Asymmetry in rate shocks:** The UP and DOWN rate scenarios may not
  have symmetric impacts due to the convexity of discounting.
- **Relative scale of mortality vs. lapse vs. expenses:** This helps
  prioritise which assumptions deserve the most attention in model
  calibration and governance.
