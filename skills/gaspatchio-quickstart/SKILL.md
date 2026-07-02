---
name: gaspatchio-quickstart
description: Use when user is new to gaspatchio, setting up for the first time, or wants to get started quickly with actuarial modeling
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Gaspatchio Quickstart

Announce: "I'm using the gaspatchio quickstart skill to get you started."

## When to Use

- User is new to gaspatchio.
- First time setup or exploring the framework.
- User says "get started", "quickstart", "hello world", "first model".

This skill is standalone — no prerequisites. It routes to tutorials and other skills; it does NOT write model code itself.

---

## Step 1 — Verify Installation

Run:

```bash
uv run gspio --version
```

If this fails:
1. Ensure `uv` is installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. From the project root, install dependencies: `uv sync`
3. Retry `uv run gspio --version`.

Do not proceed until `gspio` runs successfully.

---

## Step 2 — Inspect User Data (if provided)

If the user has data files (parquet, csv, xlsx), run `gspio describe` on each:

```bash
uv run gspio describe --json <file>
```

Read the JSON output and explain to the user:
- **Model points or assumption table?** Check the `table_shape` field.
- **Columns and types**: List what exists and what each column likely represents.
- **Suggested code**: Show the code snippet from the describe output.

**If the user has Excel files (.xlsx):** gaspatchio works with parquet and CSV. Help them convert first:

```python
import polars as pl
df = pl.read_excel("assumptions.xlsx", sheet_name="Mortality")
df.write_parquet("mortality.parquet")
```

Then run `gspio describe --json` on the resulting parquet. This conversion step is a one-time bridge — actuaries migrating from Excel will always start here.

If the user has no data files, skip to Step 3.

---

## NEVER Do This

This skill initializes and runs existing tutorials. It does NOT write model code.

If you catch yourself doing any of the following, STOP and re-read this skill:

- **NEVER write a model from scratch.** Use `gspio tutorial init` to get a working model. The tutorials exist and are tested.
- **NEVER import internal functions** like `list_conditional`, `accumulate`, or anything from `gaspatchio_core.functions.vector`. These are internal implementation details.
- **NEVER use raw Polars patterns** like `af.with_columns(pl.col(...))`. The gaspatchio API uses `af.column_name = expression`.
- **NEVER build projection timelines manually** with `[[i for i in range(n)]] * rows`. Use `af.projection.set(...)`.
- **NEVER skip `gspio tutorial init`** and improvise. If the command fails, diagnose why — do not fall back to writing code.
- **NEVER claim "tutorial files aren't shipped with the package."** They are. If they're missing, the installation is broken.

---

## Step 3 — Route to Tutorial Level

Based on what the user needs, recommend a tutorial:

| User says | Tutorial level | Path |
|-----------|---------------|------|
| "I have policy data and want to project cashflows" | Level 1 — Hello World | `tutorial/level-1-hello-world/base/` |
| "I need assumption tables (mortality, lapse)" | Level 2 — Assumptions | `tutorial/level-2-assumptions/base/` |
| "I want a complete variable annuity model" | Level 3 — Mini VA | `tutorial/level-3-mini-va/base/` |
| "I'm porting from lifelib or another platform" | Level 4 — Lifelib | `tutorial/level-4-lifelib/base/` |
| "I need scenario analysis, stress testing, or a sensitivity sweep" | Level 5 — Scenarios | `tutorial/level-5-scenarios/base/` |
| "I need VaR, CTE, or Solvency II SCR aggregation" | Level 5 — Scenarios | `tutorial/level-5-scenarios/steps/03-sensitivity/` and `04-scenario-comparison/` — the `CTE` and `Quantile` aggregators on `ScenarioRun` cover this directly. |
| "I need Monte Carlo / stochastic scenarios" | Level 5 step 05 — Stochastic | `tutorial/level-5-scenarios/steps/05-stochastic/` — `ScenarioRun(master_seed=…)` injects a deterministic per-scenario RNG seed; `drivers["rng_seed"]` flows to the model. Same API runs deterministic and stochastic alike. |
| "I have UL / IUL / VA with GMxB — charges depend on the running account balance" | Level 3 step 07 + `tutorial/patterns/rollforward-patterns/` | The `af.projection.rollforward(states={…})` state-machine kernel — declare the within-period steps (`.add`, `.charge`, `.grow`, `.deduct_nar`, `.ratchet`); the kernel runs in parallel across every policy. Start with `rollforward-patterns/01_single_state_fund.py`, then `02_multistate_ratchet.py` for VA + GMDB, then `03_lapse_stop.py` for GMWB run-off. L3 step 07 shows the migration from `cum_prod` to rollforward on the L3 mini-VA model. |

**Default**: If no data provided and user is just exploring, recommend **Level 1 base**.

**New to Python?** If the user has actuarial experience but is new to Python, always start at **Level 1** regardless of their data complexity. Level 1 is 60 lines and teaches the four core concepts (ActuarialFrame, column arithmetic, when/then, collect) without requiring Python knowledge. Once they're comfortable with Level 1, route them to the level matching their data. Don't send a Python beginner straight to Level 3 or 4.

Ask the user which level fits, or choose based on the data you inspected in Step 2:
- Data has only basic policy fields (age, sum assured, term) with no assumption files -> Level 1.
- Data includes assumption tables alongside model points -> Level 2.
- Data resembles a VA product with account values and guarantees -> Level 3.
- User explicitly mentions lifelib or platform porting -> Level 4.
- User mentions deterministic scenarios, stress testing, or sensitivity -> Level 5.
- User mentions UL/IUL/VA with COI on NAR, floor/cap on credits, or anniversary ratchets — anything where within-period charges depend on the running balance -> point at `tutorial/patterns/rollforward-patterns/` and L3 step 07.

---

## Step 4 — Initialize and Run

1. Initialize the tutorial into the user's working directory:

```bash
uv run gspio tutorial init <level> --dest ./my-first-model
```

Replace `<level>` with the level chosen in Step 3 (e.g. `level-1`, `level-2`).

If `gspio tutorial init` fails:
- Run `uv run gspio tutorial list` to verify tutorials are available.
- If tutorials are missing, the package may be installed from source without tutorial data. Ask the user to reinstall from a wheel or PyPI.
- Do NOT fall back to writing model code. This skill does not write code.

2. Run the model:

```bash
cd my-first-model
uv run python model.py
```

3. Verify the output matches expected:

```bash
uv run gspio tutorial verify <level>
```

If verification passes, explain the output to the user (proceed to Step 5).
If verification fails, investigate the diff — do NOT claim success.

---

## Step 5 — Swap User Data (if applicable)

If the user provided their own data in Step 2:

1. Replace the tutorial's data loading line with a read from the user's file (e.g., `pl.read_parquet("user_data.parquet")`).
2. If column names differ, rename them to match what the tutorial model expects — do NOT rewrite the model's formulas.
3. If required columns are missing from the user's data, explain what's needed and suggest defaults — do NOT add new calculation logic.
4. Re-run: `uv run python model.py`.
5. Verify the output makes sense for the user's data.

**Boundary rule:** Only change the data loading — do NOT modify the model's calculation logic. If the user's data doesn't fit the tutorial model's schema, explain what columns need to be added or renamed, but leave the model formulas untouched. Custom model code belongs in the `model-building` skill, not here.

---

## Step 6 — Next Steps

Once the user has a running model, route to the appropriate skill:

| Goal | Skill |
|------|-------|
| Design a new model from scratch or vague specs | `gaspatchio-model-discovery` |
| Modify, extend, or debug model code | `gaspatchio-model-building` |
| Match output against a reference (Excel, lifelib) | `gaspatchio-model-reconciliation` |

Also point the user to:
- **Tutorial steps**: Each level has a `steps/` directory with progressive enhancements (e.g., `tutorial/level-1-hello-world/steps/01-projections/`).
- **`gspio docs`**: Search the API documentation from the command line.
- **`gspio knowledge`**: Look up actuarial concepts and regulatory frameworks.

---

## Red Flags — You Are Skipping Quickstart

| Thought | Reality |
|---------|---------|
| "I already know gaspatchio" | Verify with `gspio tutorial verify`. If it fails, you don't know it well enough. |
| "I'll figure it out as I go" | 10 minutes of quickstart saves hours of debugging wrong patterns. |
| "The user wants to jump straight to coding" | Even experienced actuaries benefit from seeing the tutorial output first. |

---

## Integration

**This is typically the first skill invoked.**

**REQUIRED next steps (based on user's goal):**
- New model from scratch or vague specs → **invoke `gaspatchio-model-discovery`**
- Porting from Excel, lifelib, or another system → **invoke `gaspatchio-model-discovery`** (do NOT skip to model-building)
- Modify or extend existing model code → **invoke `gaspatchio-model-building`**
- Match output against a reference → **invoke `gaspatchio-model-reconciliation`**

---

## Completion Gate

This skill is complete when ALL of the following are true:

1. `gspio tutorial init` succeeded — tutorial files are in the user's directory
2. `uv run python model.py` produced output without errors
3. `gspio tutorial verify <level>` confirms output matches expected
4. The user has been walked through what each output section means

If verification fails, investigate the mismatch. Do NOT claim success without a passing verify.
