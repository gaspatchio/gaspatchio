# Tutorial Levels 1 & 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tutorial Levels 1 (Hello World) and 2 (Assumptions) with base models and progressive steps that bridge to Level 3.

**Architecture:** Each level has `base/model.py` (runnable on-ramp) and `steps/NN-name/` (incremental additions). All models follow the same section structure as L3/L4, use `def main(af) -> ActuarialFrame` for CLI compatibility, and include `if __name__ == "__main__"` for standalone execution. Models use inline data (no external files) except where a step specifically teaches file loading.

**Tech Stack:** Python, gaspatchio_core (ActuarialFrame, Table, when/then/otherwise, projection accessor), Polars

**Reference files:**
- `tutorial/level-3-mini-va/base/model.py` — section structure and docstring pattern to follow
- `tutorial/README.md` — top-level tutorial README to update
- `bindings/python/tests/scratch/models/intro_docs_example.py` — existing simple example

---

## Task 1: L1 Base — Hello World (scalar portfolio)

**Files:**
- Create: `tutorial/level-1-hello-world/base/model.py`
- Create: `tutorial/level-1-hello-world/README.md`

**What this model does:** 3 term life policies, scalar arithmetic, no projections. Computes expected claims, net premium, profit, loss ratio, and a `when/then/otherwise` profitability flag.

- [ ] **Step 1: Create L1 base model**

Create `tutorial/level-1-hello-world/base/model.py` with:
- Docstring explaining ActuarialFrame, column assignment, operators, `when`, `.collect()`
- Inline data: 3 policies with `policy_id`, `age`, `sex`, `sum_assured`, `annual_premium`, `mortality_rate` (hardcoded per policy), `expense_rate`
- `def main(af)` that computes:
  - `af.expected_claims = af.sum_assured * af.mortality_rate`
  - `af.expenses = af.annual_premium * af.expense_rate`
  - `af.net_premium = af.annual_premium - af.expenses`
  - `af.profit = af.net_premium - af.expected_claims`
  - `af.loss_ratio = af.expected_claims / af.annual_premium`
  - `af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")`
- `if __name__` block that creates AF from inline data, runs main, collects and prints
- Import: `from gaspatchio_core import ActuarialFrame, when`
- ~60 lines total

Data values (realistic term life):
```python
data = {
    "policy_id": ["POL001", "POL002", "POL003"],
    "age": [30, 45, 60],
    "sex": ["M", "F", "M"],
    "sum_assured": [500000, 250000, 100000],
    "annual_premium": [450, 1200, 2800],
    "mortality_rate": [0.001, 0.004, 0.015],  # qx for age
    "expense_rate": [0.10, 0.10, 0.10],       # 10% of premium
}
```

- [ ] **Step 2: Run model to verify**

Run: `cd tutorial/level-1-hello-world/base && uv run python model.py`
Expected: prints 3-row DataFrame with all computed columns.

- [ ] **Step 3: Create L1 README**

Create `tutorial/level-1-hello-world/README.md`:
- Overview (2 sentences)
- What it teaches (bullet list: ActuarialFrame, column arithmetic, when/then, collect)
- How to run (`python model.py` or `gspio run-model`)
- What to look for in the output
- Next: Steps 01-03, then Level 2

- [ ] **Step 4: Commit**

```
feat(tutorial): add Level 1 Hello World base model
```

---

## Task 2: L1 Step 01 — Projections

**Files:**
- Create: `tutorial/level-1-hello-world/steps/01-projections/model.py`
- Create: `tutorial/level-1-hello-world/steps/01-projections/README.md`

**What changes from base:** Introduces time dimension. Adds `create_projection_timeline()` and `fill_series()` to create a 12-month projection. Shows list column arithmetic.

- [ ] **Step 1: Create Step 01 model**

Start from L1 base, add:
- `import datetime` and a `VALUATION_DATE`
- `af.entry_date_parsed = af.entry_date.str.to_date("%Y/%m/%d")` (add entry_date to inline data)
- `af.month = af.entry_date_parsed.create_projection_timeline(step="MS", projection_start_value=0, projection_end_value=12)`
- `af.monthly_premium = af.annual_premium / 12.0` (scalar → used in list arithmetic)
- `af.premium_income = af.monthly_premium * 1.0` (broadcast scalar to list — show that scalar * list works)
- `af.monthly_mortality = af.mortality_rate / 12.0`
- `af.expected_claims_monthly = af.sum_assured * af.monthly_mortality`
- Keep the `when/then/otherwise` from base

README explains: what list columns are, how `create_projection_timeline` works, how scalar * list broadcasts.

- [ ] **Step 2: Run and verify**

Run: `uv run python model.py`
Expected: DataFrame with list columns (12 elements each).

- [ ] **Step 3: Commit**

```
feat(tutorial): add L1 Step 01 — projections and list columns
```

---

## Task 3: L1 Step 02 — Survival

**Files:**
- Create: `tutorial/level-1-hello-world/steps/02-survival/model.py`
- Create: `tutorial/level-1-hello-world/steps/02-survival/README.md`

**What changes from Step 01:** Introduces `.projection.cumulative_survival()` to compute policies in force over time from a fixed decrement rate.

- [ ] **Step 1: Create Step 02 model**

Build on Step 01, add:
- `af.combined_decrement = af.monthly_mortality + af.monthly_lapse` (add `lapse_rate` to inline data, compute monthly)
- `af.pols_if = af.combined_decrement.projection.cumulative_survival()` — the key new concept
- `af.expected_claims = af.sum_assured * af.monthly_mortality * af.pols_if`
- `af.premium_income = af.monthly_premium * af.pols_if`

README explains: what cumulative_survival does (cumulative product of `1 - decrement`), why it starts at 1.0, the actuarial meaning.

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

```
feat(tutorial): add L1 Step 02 — cumulative survival
```

---

## Task 4: L1 Step 03 — Time Shifting

**Files:**
- Create: `tutorial/level-1-hello-world/steps/03-time-shifting/model.py`
- Create: `tutorial/level-1-hello-world/steps/03-time-shifting/README.md`

**What changes from Step 02:** Introduces `.projection.previous_period()` to compute deaths per period (not just expected claims).

- [ ] **Step 1: Create Step 03 model**

Build on Step 02, add:
- `af.pols_if_prev = af.pols_if.projection.previous_period(fill_value=1.0)`
- `af.pols_death = af.pols_if_prev * af.monthly_mortality`
- `af.pols_lapse = (af.pols_if_prev - af.pols_death) * af.monthly_lapse`
- `af.claims_death = af.sum_assured * af.pols_death`
- `af.net_cf = af.premium_income - af.claims_death - af.expenses`
- Show `af.net_cf.list.sum()` to get total net cashflow per policy

README explains: what previous_period does, why fill_value=1.0 at t=0, the death/lapse ordering, how this is the foundation for L2's Table-driven model.

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

```
feat(tutorial): add L1 Step 03 — time shifting and per-period deaths
```

---

## Task 5: L2 Base — Assumptions

**Files:**
- Create: `tutorial/level-2-assumptions/base/model.py`
- Create: `tutorial/level-2-assumptions/README.md`

**What this model does:** Same 3-policy term life projection as L1 Step 03, but mortality comes from a `Table` with age dimension instead of hardcoded rates.

- [ ] **Step 1: Create L2 base model**

Create `tutorial/level-2-assumptions/base/model.py` with:
- Docstring explaining Table, lookup, dimensions
- Inline mortality table as dict → DataFrame → `Table(name, source, dimensions, value)`
- 12-month projection (same as L1 Step 03)
- `af.mortality_rate = mort_table.lookup(age=af.age)` — the key new concept
- Rest of model follows L1 Step 03 pattern (cumulative_survival, previous_period, deaths, claims, net_cf)
- ~100 lines

Inline mortality table:
```python
mort_data = pl.DataFrame({
    "age": [25, 30, 35, 40, 45, 50, 55, 60, 65, 70],
    "qx": [0.0005, 0.0008, 0.0011, 0.0020, 0.0040, 0.0065, 0.0100, 0.0150, 0.0230, 0.0350],
})
mort_table = Table(name="mortality", source=mort_data, dimensions={"age": "age"}, value="qx")
```

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Create L2 README**

- [ ] **Step 4: Commit**

```
feat(tutorial): add Level 2 Assumptions base model
```

---

## Task 6: L2 Step 01 — Multi-Dimension Table

**Files:**
- Create: `tutorial/level-2-assumptions/steps/01-multi-dimension/model.py`
- Create: `tutorial/level-2-assumptions/steps/01-multi-dimension/README.md`

**What changes from base:** Mortality table gains a sex dimension. Lookup uses two keys.

- [ ] **Step 1: Create Step 01 model**

Expand inline mortality table to have `age × sex` entries:
```python
mort_data = pl.DataFrame({
    "age": [30, 30, 45, 45, 60, 60, ...],
    "sex": ["M", "F", "M", "F", "M", "F", ...],
    "qx": [0.0010, 0.0006, 0.0040, 0.0025, 0.0150, 0.0095, ...],
})
mort_table = Table(name="mortality", source=mort_data, dimensions={"age": "age", "sex": "sex"}, value="qx")
```

Lookup: `af.mortality_rate = mort_table.lookup(age=af.age, sex=af.sex)`

README explains: multi-key lookup, how dimensions map to model point columns.

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

```
feat(tutorial): add L2 Step 01 — multi-dimension mortality table
```

---

## Task 7: L2 Step 02 — External Files

**Files:**
- Create: `tutorial/level-2-assumptions/steps/02-from-files/model.py`
- Create: `tutorial/level-2-assumptions/steps/02-from-files/data/mortality.parquet`
- Create: `tutorial/level-2-assumptions/steps/02-from-files/data/model_points.parquet`
- Create: `tutorial/level-2-assumptions/steps/02-from-files/README.md`

**What changes from Step 01:** Move inline data to parquet files. Model reads from files instead of inline dicts.

- [ ] **Step 1: Create parquet files from inline data**

Write a small script or inline code that saves the mortality table and model points as parquet.

- [ ] **Step 2: Create Step 02 model**

Same logic as Step 01, but:
- `mp = pl.read_parquet(DATA_DIR / "model_points.parquet")`
- `mort_data = pl.read_parquet(DATA_DIR / "mortality.parquet")`
- Model receives `af = ActuarialFrame(mp)` with external data

README explains: why parquet (types preserved, fast, Polars-native), the separation of data from model logic.

- [ ] **Step 3: Run and verify**

- [ ] **Step 4: Commit**

```
feat(tutorial): add L2 Step 02 — external parquet files
```

---

## Task 8: L2 Step 03 — Lapse Rates

**Files:**
- Create: `tutorial/level-2-assumptions/steps/03-lapse/model.py`
- Create: `tutorial/level-2-assumptions/steps/03-lapse/data/` (mortality.parquet, lapse.parquet, model_points.parquet)
- Create: `tutorial/level-2-assumptions/steps/03-lapse/README.md`

**What changes from Step 02:** Add a second Table for lapse rates by duration. Compute combined decrement from two independent rates.

- [ ] **Step 1: Create lapse table**

```python
lapse_data = pl.DataFrame({
    "duration": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "lapse_rate_annual": [0.15, 0.10, 0.08, 0.06, 0.05, 0.04, 0.04, 0.03, 0.03, 0.03, 0.02, 0.02],
})
```

- [ ] **Step 2: Create Step 03 model**

Add:
- `af.duration = af.month // 12` (or just use month as duration for 12-month projection)
- `af.base_lapse_rate = lapse_table.lookup(duration=af.duration)`
- `af.lapse_rate_mth = 1 - (1 - af.base_lapse_rate) ** (1/12)`
- Combined decrement: `af.combined_decrement = 1 - (1 - af.mort_rate_mth) * (1 - af.lapse_rate_mth)`

README explains: multiple Tables, combined decrements, annual-to-monthly conversion.

- [ ] **Step 3: Run and verify**

- [ ] **Step 4: Commit**

```
feat(tutorial): add L2 Step 03 — lapse rates and combined decrements
```

---

## Task 9: L2 Step 04 — Conditionals on Lists

**Files:**
- Create: `tutorial/level-2-assumptions/steps/04-conditionals/model.py`
- Create: `tutorial/level-2-assumptions/steps/04-conditionals/data/` (copy from Step 03)
- Create: `tutorial/level-2-assumptions/steps/04-conditionals/README.md`

**What changes from Step 03:** Add `when/then/otherwise` on list columns — zero policies after maturity, first-year commission.

- [ ] **Step 1: Create Step 04 model**

Add `policy_term` to model points. Add:
- `af.maturity_month = af.policy_term * 12`
- `af.pols_if = when(af.month < af.maturity_month).then(af.pols_if_raw).otherwise(0.0)`
- `af.commissions = when(af.month < 12).then(af.premium_income * 0.5).otherwise(0.0)` (50% first year)
- Full net_cf with premiums, claims, expenses, commissions

README explains: how `when` works on list columns (element-wise), comparison with Excel IF(), the maturity zeroing pattern.

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

```
feat(tutorial): add L2 Step 04 — conditionals on list columns
```

---

## Task 10: Update Top-Level Tutorial README

**Files:**
- Modify: `tutorial/README.md`

- [ ] **Step 1: Update level table**

Change L1 and L2 from "Coming soon" to "Ready". Update descriptions.

- [ ] **Step 2: Update quick start**

Change "Levels 1 and 2 are not yet built. Start with Level 3 base." to recommend starting at Level 1.

- [ ] **Step 3: Commit**

```
docs(tutorial): update README for L1 and L2 availability
```

---

## Parallelization Notes

Tasks 1-4 (L1) and Tasks 5-9 (L2) are **independent** — L2 doesn't depend on L1 files, only on the same concepts. They can be built in parallel by two subagents.

Task 10 depends on both L1 and L2 being complete.
