---
name: gaspatchio-model-building
description: Use when writing or modifying gaspatchio actuarial model code – enforces ActuarialFrame idioms, mandatory doc lookup, three-phase build pattern, and performance rules. Routes to reference files for detailed patterns.
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Building Gaspatchio Models

## Overview

**The formula IS the code.** Gaspatchio models should read like actuarial formulas, not data plumbing.

This skill provides orientation and routing. Detailed patterns live in `references/` files — load them as needed.

## When to use this skill

This skill can be used standalone. You do NOT need to have run model-discovery first. Use it whenever you are writing or modifying gaspatchio model code.

## Tutorial reference

Every concept in this skill has a worked example in the tutorial:
- Column arithmetic, when/then → Level 1 (`tutorial/level-1-hello-world/`)
- Table.lookup(), dimensions → Level 2 (`tutorial/level-2-assumptions/`)
- Full VA model with all sections → Level 3 base (`tutorial/level-3-mini-va/base/`)
- Data enrichment, BEF_DECR, accumulate → Level 4 (`tutorial/level-4-lifelib/`)
- Scenarios → Level 5 (`tutorial/level-5-scenarios/`)

## When to Use

Use this skill when you create, edit, or debug a `model_*.py` gaspatchio model. Combine with `gaspatchio-discovery` for new models and `gaspatchio-reconciliation` when matching a gold standard.

---

## MANDATORY: Look Up Before You Write

**This is a hard gate, not a suggestion.**

Before using ANY gaspatchio method you haven't verified in this session, run:

```bash
uv run gspio docs "<method or concept>"
```

Before using actuarial terminology you're unsure about:

```bash
uv run gspio knowledge "<concept>" -T <tag>
```

| Situation | Command |
|-----------|---------|
| About to use a method | `uv run gspio docs "prospective_value"` |
| Need an accessor's methods | `uv run gspio docs "projection accessor" -n 20` |
| Want code examples | `uv run gspio docs "cumulative_survival" -t code_example` |
| Need actuarial concept | `uv run gspio knowledge "CSM calculation" -T IFRS17` |
| Analyzing an assumption file | `uv run gspio describe assumptions/mortality.parquet` |

**Do NOT guess method signatures. Do NOT assume you know how a method works. Look it up.**

**Missing a method?** If the calculation you need does not exist as a built-in method, do not implement it inline with raw Python. Invoke the `extending-gaspatchio` skill to create a proper accessor. This ensures the calculation is reusable, vectorized, and follows the framework's performance patterns.

---

## Environment

Always use `uv run` for Python commands — the system Python does not have gaspatchio or polars installed:

```bash
uv run gspio run-model model.py data.parquet              # full run
uv run gspio run-single-policy model.py data.parquet 123   # single policy (POSITIONAL arg, not --policy-id)
uv run gspio run-single-policy model.py data.parquet 123 --output-file /tmp/result.parquet  # save for analysis
uv run python3 -c "import polars as pl; ..."               # inline scripts
```

**Agent workflow**: Always use `--output-file` to save model results as parquet. Read the parquet with `gspio describe --json` or inline Polars for validation. Do NOT parse stdout.

Model directories (e.g., `my-model/`) are NOT Python packages. To import a model file programmatically, use `importlib.util.spec_from_file_location()`.

---

## Model Skeleton

```python
from gaspatchio_core import ActuarialFrame, when
from gaspatchio_core.assumptions import Table, TableBuilder
import polars as pl
import datetime

# Phase 1: Assumption loading (module-level or helper functions)
def load_assumptions():
    mort_df = pl.read_parquet("assumptions/mortality.parquet")
    mort = Table(name="mortality", source=mort_df,
                 dimensions={"age": "age"}, value="rate")
    return {"mortality": mort}

# Phase 2 & 3: Model entry point
def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    tables = load_assumptions()

    # --- PHASE 1: Setup (scalar operations, .collect() OK here) ---
    mp = af.collect()
    mp = mp.with_columns(pl.col("Issue Age").alias("issue_age"))
    af = ActuarialFrame(mp)

    # --- PHASE 2: Projection timeline ---
    af = af.date.create_projection_timeline(
        valuation_date=datetime.date(2025, 1, 1),
        projection_end_type="maximum_age",
        projection_end_value=100,  # NOT 99 — off-by-one is catastrophic
        projection_frequency="monthly",
    )

    # --- PHASE 3: Calculations (lazy — NO .collect() from here) ---
    af.mort_rate = tables["mortality"].lookup(age=af.age)
    af.survival = af.mort_rate.projection.cumulative_survival()
    af.pv_claims = af.claims.projection.prospective_value(discount_rate=0.03)

    return af

# Standalone execution — lets you run `python model.py` directly
if __name__ == "__main__":
    mp = pl.read_parquet("data/model_points.parquet")
    af = ActuarialFrame(mp)
    result = main(af).collect()
    print(result.select(["point_id", "pv_claims"]))
```

Details: [references/model-phases.md](references/model-phases.md)

---

## Column Rules

- **Attribute notation preferred**: `af.mortality_rate` not `af["mortality_rate"]`
- Bracket notation when necessary: `af["Policy Number"]`, `af["class"]`
- **No underscore-prefixed names**: `af._flag` will raise an error — use `af.flag` instead
- **snake_case** for calculated columns; raw input columns may need aliases first

---

## Data enrichment patterns

When model points need parameters from assumption files, join them BEFORE creating the ActuarialFrame:

**Product parameter join:**
```python
mp = mp.join(product_params.select([...]), on=["product_id", "plan_id"], how="left")
```

**Space parameter cross-join:**
```python
gmxb = space_params.filter(pl.col("space") == "GMXB").select(["expense_acq", "expense_maint"])
mp = mp.with_columns([pl.lit(gmxb["expense_acq"].item()).alias("expense_acq")])
```

**Wide-to-long unpivot:**
```python
long = wide_df.unpivot(index="t", on=["FUND1", "FUND2"], variable_name="fund_index", value_name="return")
```

See Level 4 model.py lines 204-277 for the canonical example.

---

## Product-specific formulas

Different products may use different formulas. Use parameter-driven selection:

```python
# WRONG: hardcoded single formula
af.dyn_lapse_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)

# RIGHT: parameter-driven selection
af.dl001_factor = (1.0 - af.M * (1.0 / af.itm - af.D)).clip(af.L, af.U)
af.dl002_factor = (af.Y * af.itm ** af.Power).clip(af.FactorFloor, af.FactorCap)
af.dyn_lapse_factor = when(af.formula_id == "DL001").then(af.dl001_factor).otherwise(af.dl002_factor)
```

See Level 3 Step 06 (Gap 3) and Level 4 Section 7 for examples.

---

## Performance Rules (Non-Negotiable)

| Never | Why |
|-------|-----|
| `map_elements` | ~14x slower; defeats vectorization |
| `for row in ...` / Python loops over policies | Breaks performance entirely |
| `.collect()` during projection phase | Breaks lazy execution — only OK in Phase 1 setup |

---

## Gotcha Quick Reference

These are the top mistakes from real model-building sessions. Each links to the relevant reference file.

| # | Gotcha | What Goes Wrong | Reference |
|---|--------|----------------|-----------|
| 1 | `when().then(scalar).otherwise(list_col)` | Runtime crash: "Unsupported combination of list/scalar inputs" | [conditionals-and-lists.md](references/conditionals-and-lists.md) |
| 2 | `projection_end_value=99` | Truncates final year; ~3% BEL gap | [model-phases.md](references/model-phases.md) |
| 3 | `proj_year` vs `year` confusion | Stress scenarios silently wrong — mass lapse never fires | [timing-and-dates.md](references/timing-and-dates.md) |
| 4 | Assuming `af.t` exists | No built-in period counter — must derive it yourself | [model-phases.md](references/model-phases.md) |
| 5 | `python3` instead of `uv run python3` | `ModuleNotFoundError: No module named 'polars'` | (this file, Environment section) |
| 6 | `--policy-id` flag | It's a positional arg, not a flag. `--policy-id-column` is a different thing | (this file, Environment section) |
| 7 | `prospective_value` timing | "end_of_period" is actually BOP timing (v^t) — names are misleading | [timing-and-dates.md](references/timing-and-dates.md) |
| 8 | `ceil(t/12)` for proj_year | Leap years cause 1-month offset that compounds under stress | [timing-and-dates.md](references/timing-and-dates.md) |
| 9 | Column name case mismatch | Polars is case-sensitive; always check `df.columns` first | [common-mistakes.md](references/common-mistakes.md) |
| 10 | Guessing method signatures | Agents get it wrong ~70% of the time — `gspio docs` first | (this file, MANDATORY section) |
| 11 | `af.month * 0 + CONSTANT` broadcast hack | Confusing — just assign the scalar directly: `af.rate = CONSTANT` | [common-mistakes.md](references/common-mistakes.md) |
| 12 | `(1 + rate) ** af.month` scalar^list | TypeError — use `(af.month * math.log(1 + rate)).exp()` | [common-mistakes.md](references/common-mistakes.md) |
| 13 | Boolean masking in audit code | `value * (condition)` is a programmer's trick — use `when/then` | [conditionals-and-lists.md](references/conditionals-and-lists.md) |

Full list with code examples: [references/common-mistakes.md](references/common-mistakes.md)

---

## Reference Files

Load these when working in the relevant area:

| Topic | File | When to Load |
|-------|------|-------------|
| **Build phases** | [references/model-phases.md](references/model-phases.md) | Setting up a model, projection timeline, calculation order |
| **Assumptions** | [references/assumptions.md](references/assumptions.md) | Loading tables, TableBuilder, MeltDimension, lookups |
| **Conditionals & lists** | [references/conditionals-and-lists.md](references/conditionals-and-lists.md) | `when/then/otherwise`, arithmetic masking, `.list.*` ops |
| **Timing & dates** | [references/timing-and-dates.md](references/timing-and-dates.md) | PV timing, YEARFRAC, proj_year vs year, BOP/EOP |
| **Scenarios** | [references/scenarios.md](references/scenarios.md) | Stress testing, ScenarioParams, term-structure discounting |
| **Common mistakes** | [references/common-mistakes.md](references/common-mistakes.md) | Troubleshooting — full annotated list of real failures |

---

## Validate Incrementally

- Build in **sections**, not entire models at once.
- After each section: `uv run gspio run-single-policy model.py data.parquet 1 --output-file /tmp/result.parquet` and check output for a single policy.
- Only move on when the current section is clearly correct.
- If reconciling, pair with `gaspatchio-reconciliation` and follow its loop strictly.

## Tutorial Reference

The `tutorial/` directory contains progressive models that demonstrate every pattern in this skill:

- **Level 3 base** (`tutorial/level-3-mini-va/base/model.py`): 11-section model with inline data. Shows the realistic section breakdown, `when/then/otherwise`, scalar broadcasting, exp/log identity, `previous_period()`, `cum_prod()`.
- **Level 3 Steps 01-05**: Each adds one feature (parquet files, select mortality, guarantees, dynamic lapse, rate curves).
- **Level 4** (`tutorial/level-4-lifelib/`): 860-line production model, reconciled to 0.0000% against lifelib. Shows table joins, multi-fund returns, product parameterisation.

When building a new model, start from the tutorial level closest to your target and adapt.

---

## Post-build checklist (completion gate)

Before claiming the model is complete, verify ALL of these:
- [ ] No `map_elements` or `apply` calls anywhere in model code
- [ ] No Python for-loops over rows (no `for row in df.iter_rows()`)
- [ ] All sections have header comments (SECTION 1, SECTION 2, etc.)
- [ ] All `Table.lookup()` calls verified with `uv run gspio docs "Table.lookup"`
- [ ] Model runs with `--output-file` without errors: `uv run gspio run-single-policy model.py data.parquet 1 --output-file /tmp/result.parquet`
- [ ] Key outputs have expected signs (claims positive, net_cf can be negative)
- [ ] All assumption Tables created with correct dimensions
- [ ] No hardcoded magic numbers — all rates come from Table lookups or named constants

This checklist is the completion gate for this skill.
