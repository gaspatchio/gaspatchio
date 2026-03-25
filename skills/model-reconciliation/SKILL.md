---
name: gaspatchio-model-reconciliation
description: Use when matching a gaspatchio model to an existing "gold standard" (Excel, lifelib, vendor model) and success means numbers match - enforces variable-by-variable reconciliation, evidence-first diffs, tiered diagnostic escalation (regression, PCA, cohort analysis, waterfall), and a required markdown build log so mismatches get fixed immediately and stay fixed.
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Gaspatchio Model Reconciliation

## When to use this skill

This skill can be used standalone — it does NOT require model-building or model-review to have been run first. Use it whenever you need to match a model against a reference implementation (Excel, lifelib, another model).

## Overview

You are not building a "similar" model; you are building a **reproducer**.

This skill enforces a strict reconciliation workflow so your gaspatchio model matches an existing "gold standard" implementation (Excel, lifelib, or other systems) **exactly** (or within an agreed numeric tolerance), variable by variable.

## When to Use

Use this skill when:

- The user says "reconcile", "match Excel", "match lifelib", "replicate", or "compare to existing model".
- There is a clear source model considered "truth".
- Success is defined as "numbers match", not just "logic looks reasonable".

If you cannot name the source model and show a single-policy output from it, **you are not doing reconciliation yet.**

## Learning reconciliation

If you're new to reconciliation, start with the 4-gap exercise in `tutorial/level-3-mini-va/steps/06-reconcile/`:

1. Run `model_with_gaps.py` → see 0/8 points pass (2.5%–51.7% differences)
2. Run `reconcile.py --model gaps` → see which points fail and by how much
3. Fix each gap one at a time:
   - Gap 1: Replace `cum_prod` with `accumulate()` for AV
   - Gap 2: Add BEF_DECR decrement ordering
   - Gap 3: Add DL002 formula selection for GMAB products
   - Gap 4: Switch to closed-form discount factors
4. Run `reconcile.py --model fixed` → see 8/8 pass at 0.0000%

This teaches reconciliation through experience. Each gap is a real actuarial issue, not a toy example.

## Core Rules

- **You MUST be able to run the source model and see its output** for at least one policy before writing serious gaspatchio logic.
- **Reconcile in small steps** (variables or tight groups), not whole-model at once.
- **Do not move on with known unexplained differences.** Every mismatch is a bug until proven otherwise.
- **Test across policy space**, not just a cherry-picked example.

## Quick Reference (what "good" looks like)

Keep this loop tight. If you can't do one of these, you're not reconciling yet.

```text
Reconciliation Loop (per variable / small group)
- [ ] Pick next variable(s) and state expected direction/sign/magnitude (briefly)
- [ ] Run source + gaspatchio on SAME specimen policy input
- [ ] Export comparable outputs
- [ ] Diff ONLY the variable(s) you just touched (column + time-step)
- [ ] If mismatch: isolate → inputs → formula → timing → rounding → edges
- [ ] If mismatch persists: escalate through Diagnostic Toolkit (Tier 1 → 2 → 3)
- [ ] Record the fix in the build log (Problem/Investigation/Root Cause/Fix/Result)
- [ ] Re-run diff and only then proceed
```

## Matching intermediates, not just aggregates

Passing PVs is necessary but not sufficient. A model can give the right PVs for the wrong reasons (errors that cancel out).

Always compare intermediate variables per timestep:
- `mort_rate`, `mort_rate_mth` — are mortality rates correct at every time step?
- `pols_if`, `pols_death`, `pols_lapse` — are policy counts tracking correctly?
- `av_pp_mid_mth` — is the account value decomposition right?
- `claims_death`, `claims_lapse` — are claims using the right AV timing?

Use `gspio run-single-policy --output-file` to capture ALL variables, then compare per-timestep:
```bash
uv run gspio run-single-policy model.py data.parquet 1 --output-file /tmp/result.parquet
uv run gspio describe --json /tmp/result.parquet
```

The Level 4 full reconciliation (`tutorial/level-4-lifelib/reconcile_full.py`) compares 25 intermediate variables per point per timestep — this is the gold standard.

---

## Diagnostic Toolkit

When a mismatch isn't immediately obvious from direct inspection, use this toolkit to diagnose systematically. **Always start at Tier 1. STOP as soon as you identify the root cause.**

### Tier 1 — Direct Inspection (do this EVERY time)

1. **Sign check**: is the value positive/negative as expected?
2. **Magnitude check**: is it in the right order of magnitude?
3. **Single-cell trace**: for one policy, one period, compare every input to the formula
4. If root cause found: fix it, record in build log, re-run diff

Details: [references/technique-quick-checks.md](references/technique-quick-checks.md)

### Tier 2 — Pattern Detection (if Tier 1 doesn't explain it)

1. **Scatter plot**: gaspatchio value (y) vs gold standard value (x) for all policies at a representative time step
2. **Residual histogram**: distribution of (gaspatchio - gold standard) across policies
3. **Quick cohort grouping**: mean absolute error by age band, product type, duration bucket

Details: [references/technique-pattern-detection.md](references/technique-pattern-detection.md)

### Tier 3 — Statistical Diagnostics (only when Tier 2 shows systematic patterns)

Consult the selection table below. Read the appropriate reference file. Execute one technique at a time.

### Technique Selection Table

| What You Observe | Technique | What It Reveals | Reference |
|---|---|---|---|
| Scatter shows linear trend but slope != 1 or intercept != 0 | Linear regression | Proportional or additive bias in a variable | [technique-linear-regression.md](references/technique-linear-regression.md) |
| Residuals cluster by age, product, or duration | Cohort analysis | Cohort-specific bug (lookup, rate, boundary) | [technique-cohort-analysis.md](references/technique-cohort-analysis.md) |
| Error grows steadily over projection time | Time-series residual | Compounding error or timing drift | [technique-timeseries-residual.md](references/technique-timeseries-residual.md) |
| Aggregate metric off but individual variables unclear | Waterfall decomposition | Which variable contributes most to total error | [technique-waterfall.md](references/technique-waterfall.md) |
| No clear single pattern; error seems multivariate | PCA on residual matrix | Which dimensions explain most error variance | [technique-pca.md](references/technique-pca.md) |
| Need to see WHERE errors concentrate (policy x time) | Error heatmap | Visual identification of error clusters | [technique-heatmap.md](references/technique-heatmap.md) |

### Diagnostic Rules

- **One technique at a time.** Run one, interpret results, decide next step.
- **Record every diagnostic in the build log** under the current Fix entry's Investigation section.
- **Negative results are still evidence.** Record: "Ran regression: slope=1.001, R^2=0.999 — no proportional bias detected."
- **Do not run Tier 3 techniques speculatively.** Each costs time and context. Only run when Tier 2 points you there.

### Libraries (already installed, no new dependencies)

| Need | Use | Import |
|---|---|---|
| Linear regression | `scipy.stats.linregress` | `from scipy import stats` |
| PCA | `numpy.linalg.svd` | `import numpy as np` |
| Visualization | `altair` (accepts Polars directly) | `import altair as alt` |
| Statistical tests | `scipy.stats` (KS, Shapiro, t-test) | `from scipy import stats` |

Do NOT add scikit-learn, statsmodels, matplotlib, seaborn, or plotly. Everything is covered by scipy + numpy + altair.

### Team Coordination for Diagnostics

When diagnostics reveal specific types of issues, engage the right specialist:

| Finding | Engage | Ask For |
|---|---|---|
| Excel formula appears different from gaspatchio | spreadsheet-expert | Trace formula chain for the specific cell/variable |
| Gaspatchio API producing unexpected results | docs-expert | Verify API behavior, parameters, timing conventions |
| Actuarial methodology question | actuary | Confirm interpretation of rates, timing, conventions |
| Code change needed | model-dev | Implement the fix based on your root cause finding |

You are the diagnostician, not the fixer. Identify the problem precisely, then route to the right specialist.

### Tolerance Tiers (when to accept vs investigate)

| Level | Threshold | Use Case | Action if Breached |
|---|---|---|---|
| **Exact** | <0.01% | Inputs, t=0 values, policy counts | Mandatory fix |
| **Tight** | <1% | Per-policy cashflows, early periods | Investigate root cause; document if accepted |
| **Reasonable** | <5% | Aggregate BEL, complex stress scenarios | Investigate major drivers; may accept with justification |
| **Directional** | Sign + order of magnitude | Extreme stress, known methodology gaps | Document known differences; flag for future work |

---

## Reconciliation Build Log (Markdown report) — REQUIRED

You MUST maintain a human-readable reconciliation report as you work, similar in style and granularity to `mystery_model/model_build.md` in this repo.

This is not "nice to have": it is how you make reconciliation auditable, teachable, and fast to debug when it breaks later.

### What to write

Create a single markdown file (a "build log") in the model folder, e.g.:

- `MODEL_NAME/model_build.md` (recommended, matches the repo precedent)

Update it continuously as you reconcile. Each time you make a reconciliation change, add an entry.

### Report structure

Use the template in [references/build-log-template.md](references/build-log-template.md). Copy it into your model directory as `model_build.md` and update it continuously as you reconcile.

### Evidence rules (this is what makes the report "real")

Reconciliation reports without evidence devolve into vibes. Don't do that.

- **Every Fix MUST cite a concrete mismatch**: variable name + time index (month/period) + source value + gaspatchio value + delta.
- **Every Fix MUST include the comparison method**: e.g. "diffed parquet outputs in Polars", "traced Excel formula for deaths", etc.
- **If you claim timing**: include the exact timing formula (t vs t-1, begin vs end of period) in the appendix and/or fix entry.
- **If you used a diagnostic technique**: include the key output (regression slope, PCA variance explained, heatmap observation) in the Investigation section.

### Default diff tool (provide a deterministic comparison)

Default to a machine diff (Polars/Pandas), not eyeballing Excel.
If you must compare in Excel, still export a machine-readable diff or table snippet into the build log.

### Minimum content requirements (non-negotiable)

- **Specimen policy table**: the exact model point row you reconciled first.
- **Exact targets**: at least one explicit numeric target (and where it comes from).
- **At least one variable-level diff**: show a column+time-step mismatch and its resolution (not just "total metric").
- **Explicit timing conventions**: beginning vs end of period, month 0 rules, and any rate-shifting you used.
- **Assumption parity notes**: offsets, corrupted values, dimension mapping quirks, rounding.

### Style rules (make it useful, not pretty)

- Prefer short, factual entries with numbers.
- Include code snippets that show the *actual* fix (not pseudo-code).
- When a change impacts results, record "before → after" values for the headline metric and the key intermediate variable you were targeting.
- If you accept tolerances, record them once at the top and always report deltas.

### Red flags — STOP and fix your process

If any of these happen, you're about to waste time:

- "Portfolio matches, single policy doesn't" (single policy is truth for debugging).
- "It's probably rounding" (prove it: show where rounding happens and reconcile).
- "It's close enough, we'll revisit" (you won't; mismatches compound).
- "We changed 10 things, now it matches" (you can't attribute; revert and do one change).
- "We can't run the source model, but..." (not reconciliation).

## Step 1: Understand and Run the Source Model

Before writing or changing gaspatchio code, answer:

1. **"How do I run the source model?"**
   - Excel: which file, which sheet(s), which cell/range is the canonical output?
   - Lifelib: which model, which script or notebook, and the exact command to run.
   - Other systems: entrypoint, config, and output location.

2. **"Can you show me output for a single policy?"**
   - Get a **single, concrete policy** with:
     - Full input row (model point)
     - Full projection or key result variables
   - This becomes your primary reconciliation specimen.

3. **"What tool will we use to compare outputs?"**
   - Excel diff, CSV comparison, Python/Pandas/Polars diff, or parquet compare.
   - Agree upfront so "match" has an operational definition.

**Do not proceed until you can run the source model and see its output.**

## Step 2: Build in Reconciliation Order

### 2.1 Import all assumptions FIRST

- Load all assumption tables into gaspatchio **before** any calculations.
- Verify table dimensions, keys, and spot-check values directly against source.
- Treat assumption parity as non-negotiable: if assumptions differ, everything downstream is noise.

### 2.2 Start with a minimal MVP

Build the **simplest possible model** that still produces the first 1-2 variables you care about:

- Timeline variables only:
  - `month`, `duration`, `age`, `policy_year`, etc.
- No cashflows, reserves, or PVs yet.

Reconcile those exactly before adding anything else.

### 2.3 Reconcile 100% before moving on

For each variable (or tight group):

1. Run both models on the same policy (or small set of policies).
2. Export comparable outputs (CSV/Parquet).
3. Diff the specific variable(s) only.
4. Investigate **any** difference (even "tiny" ones) immediately.

**Every unexplained mismatch is a bug.** Do not accumulate "small" differences.

### 2.4 Test across policy space

Once variables match for the first policy, challenge them:

- Young vs old ages
- Short term vs long term
- New business vs in-force
- Edge cases:
  - duration = 0
  - maturity month
  - policy start/end around valuation date
  - partial months / irregular first period if applicable

Reconciliation is fragile; edge cases find the cracks.

## Step 3: Iterate Variable by Variable

Workflow for each new variable (or small business-logic group):

```text
Reconciliation Loop
- [ ] 1. Identify next variable(s) to add
- [ ] 2. Implement in gaspatchio
- [ ] 3. Compare to source for primary policy
- [ ] 4. Fix until 100% match (or justified numeric tolerance)
- [ ] 5. If mismatch persists, escalate through Diagnostic Toolkit
- [ ] 6. Re-test across policy space
- [ ] 7. Only then move on
```

Examples of good grouping:

- Timing scaffolding group: `month`, `duration`, `age`, `policy_year`.
- Death-related group: `q_x`, `pols_if`, `pols_death`, death benefit cashflow.
- Premium-related group: gross premium, modalization, premium cashflows.

Avoid adding more than one logical group per iteration.

## Reconciliation Anti-Patterns

| Don't | Do |
|-------|----|
| Build whole model then "see how close" | Reconcile in tiny steps, fixing as you go |
| Assume small differences are OK | Investigate every mismatch until explained |
| Only test one policy | Test multiple policies and edge cases |
| Move on with known differences | Fix before writing new logic |
| Batch many variables before checking | Reconcile after each variable/section |
| Run all diagnostic techniques speculatively | Escalate through tiers; stop when root cause found |
| Guess at the error pattern | Use scatter plots and histograms to see it first |

Treat these anti-patterns as red flags. If you see one, stop and back up.

## Debugging Mismatches

When a value doesn't match between source and gaspatchio, debug in this order:

1. **Isolate the variable**
   - Confirm which exact variable and which time point differ.
2. **Check inputs**
   - Are all input columns (model points + assumptions) identical?
   - Are derived indexing variables (`age`, `duration`, `policy_year`) aligned?
3. **Check formula**
   - Is the business logic exactly the same (including caps/floors/options)?
4. **Check timing**
   - Beginning vs end of period? Mid-month conventions? Effective date vs valuation date?
5. **Check rounding**
   - When and where is rounding applied in the source model vs gaspatchio?
6. **Check edge cases**
   - What happens on boundary periods: issue, first premium, last premium, maturity, lapse/death months?
7. **Escalate to Diagnostic Toolkit**
   - If steps 1-6 don't explain the mismatch, escalate through Tier 2 and Tier 3 diagnostics.

Do not "explain away" differences with hand-wavy reasoning; either align the model or explicitly document a justified, **agreed** tolerance.

## Running Comparisons

```bash
# Run single policy — ALWAYS use --output-file for machine-readable output
uv run gspio run-single-policy model.py data.parquet POLICY_ID --output-file /tmp/result.parquet

# Run all policies
uv run gspio run-model model.py data.parquet --output-file /tmp/results.parquet

# Inspect structure of result
uv run gspio describe /tmp/result.parquet --json
```

### Inspecting model output

After running with `--output-file`, inspect the output structure:
```bash
uv run gspio describe --json /tmp/result.parquet
```
This shows schema, column types, detected dimensions, and sample rows. Use it to understand the output before writing comparison code.

**Always use `--output-file`**. Do NOT parse stdout for reconciliation — use parquet (typed, schema-preserved) for machine diffs.

Use Polars to compare the gaspatchio outputs to the source model outputs at the **column + time-step** level.

## Example: Level 4 Tutorial Reconciliation

**Canonical example**: Level 4 reconciliation — 0.0000% across 1,016 model points, 35 variables, ~9 million data points. See `tutorial/level-4-lifelib/reconciliation_report.md` for the full breakdown including upstream lifelib bugs found.

The `tutorial/level-4-lifelib/` directory demonstrates a complete reconciliation:
- `reconciliation_report.md` — My Model-style report: 8/8 points, 10/10 variables, 0.0000% difference
- `reconcile.py` — one-command verification script
- `reference/lifelib_reference.parquet` — gold standard output

Use this as a template for your own reconciliation reports.

## Success Criteria

Reconciliation is complete when:

- All agreed variables match across:
  - Primary specimen policy
  - A set of diverse test policies
  - Edge cases that stress timing and options
- No unexplained differences remain.
- Any remaining tiny differences (if allowed) are:
  - Explicitly documented
  - Numerically bounded
  - Considered acceptable by the stakeholder
  - Classified using the Tolerance Tiers table above

At that point, you can treat the gaspatchio model as a faithful reproduction of the source.
