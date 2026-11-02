---
name: gaspatchio-model-review
description: Use when reviewing changes to a gaspatchio model, validating model quality, or preparing a model for production use. Covers both gaspatchio code quality and actuarial professional standards (ASOP 56).
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Gaspatchio Model Review

I'm using the gaspatchio model review skill.

## When to use this skill

This is the most commonly used skill standalone. Use it:

- After completing model building (whether from scratch or from a tutorial)
- When reviewing changes to an existing model (yours or someone else's)
- Before merging model changes to production
- When preparing a model for regulatory review or peer sign-off

This skill does NOT require any other skill to have been run first. It can be invoked at any point in the model lifecycle.

## Hard gate

All **Critical** and **Important** issues must be addressed before the review is considered complete. Minor issues should be logged but do not block completion.

---

## How to Review

### Step 1: Read the model code

If reviewing changes, read the git diff. If reviewing a full model, read the model file(s) end to end.

```bash
# For change review
git diff main -- model.py

# For full model review
# Read the model file(s) directly
```

### Step 2: Run the model

```bash
uv run gspio run-single-policy model.py data.parquet 1 --output-file /tmp/result.parquet
```

Do NOT skip this step. A model that doesn't run has Critical issues by definition.

### Step 3: Inspect the output

```bash
uv run gspio describe --json /tmp/result.parquet
```

Check that:
- Output columns exist and have expected types
- No null/NaN values in key outputs (unless intentional)
- Projection length is correct
- Signs are correct (claims positive, net cashflows can be negative, survival in [0,1])

### Step 3b: Ask the model what it uses, and what it cannot account for

Every model can say, without running again, what each column read, what reads
it, and what nothing reads. Export the audit file once and ask it — or ask
`af.graph` on the live frame; the answers are the same, from one
implementation.

```bash
uv run gspio calc-graph model.py data.parquet -o /tmp/audit.json --results /tmp/results.parquet

# What nothing reads, each under one class. Name the model's results in --keep.
uv run gspio graph unused /tmp/audit.json --keep pv_net_cf,reserve

# Columns the model cannot account for, and lines outside the core vocabulary
uv run gspio graph holes /tmp/audit.json
uv run gspio graph tiers /tmp/audit.json

# Everything behind a result, each arrow with the period it read (t−1, first…t)
uv run gspio graph trace /tmp/audit.json reserve --depth 2

# What moves if an assumption table moves
uv run gspio graph affected /tmp/audit.json --assumption mortality
```

The same questions in Python, on the frame or on the file:

```python
af.graph.unused(keep=["pv_net_cf", "reserve"])
af.graph.trace("reserve", depth=2)
af.graph.affected(assumption="mortality")

from gaspatchio.graph import read_artifact
read_artifact("/tmp/audit.json").unused(keep=["pv_net_cf", "reserve"])
```

How to classify what `unused` reports:

| Class | What it is | Severity |
|---|---|---|
| `superseded` | A definition a later line replaced, never read. Dead code. | Important |
| `terminal` (not kept) | A live calculation nothing reads: a result, or dead code. Ask the author which; keep the results. | Important until answered |
| `data` | An input column nothing reads. | Minor (unless the spec says it should be used — then Critical) |
| `stamp` | A projection column nothing reads. | Not an issue |
| `length_only` | Read only for its length (`broadcast_to_periods(like=...)`). | Not an issue |

Any hole from `gspio graph holes` is **Important**: a column the model cannot
account for is a number nobody can audit. In CI, `--fail-on superseded,terminal`
exits 1 when either class is not empty; `--keep-from results.toml` reads the
results from a top-level `keep = [...]` array (a provisional file shape in 1.0).

`calc-graph` runs the whole book but writes values for the policies it samples,
and the default is **one** — `:1`, the first row. Name the policies the review
needs (`--policies id:POL-000343`, `--policies all`); the export says which it
took. Each arrow of `trace` states the periods it read (`(t−1)`, `(first…t−1)`,
`(t…last)`): read the window, never the formula text. The glossary of a read's
kinds (`DIRECT`, `INDIRECT`, `TRANSFORMATION`, `AGGREGATION`) is in
[references/audit-record.md](references/audit-record.md).

### Step 3c: Hold the files you were handed against the record

`gspio verify` holds the files you have against the audit file that records
them — results, policy data, the model file and every local module it
imports, and each assumption table read back from its file — and exits 0 only
when every check asked for agrees; library versions and git are evidence and
move no exit status. Hand `Table` the file path (not a frame you built) so
`--assumptions` can decide it.

```bash
uv run gspio verify /tmp/audit.json --model model.py --model-points data.parquet \
    --results /tmp/results.parquet --assumptions assumptions/
# exit 0 agrees · 1 a check disagrees · 4 a check could not be made · 2 a file could not be read
```

With `--model` and `--model-points` it also rebuilds the model's graph from
the files in hand and decides on it: a value read from a parameter file, a
config, an environment variable or a module outside the model's folder that
moved is `✗ graph differs`, naming the line, even where every file stamp
agrees. A scenario plan's record needs `--scenarios run_scenarios.py` too.

Exit 4 is not a pass. Its usual causes: `--assumptions NAME=FILE` given for one
table, which leaves every other recorded table "not found" (give the
directory); a table the model built from a frame in its own code, matched
to a file of other values — nothing records that the frame was that file, so
it cannot be decided; and a record whose `holes` section is not empty — a
column joined or written past the frame reached the record by name only, so
`? holes could not be checked` names it and what rests on it. Which identity answers which question —
`graph_fingerprint` (formulas and table content, **not** the book),
`formulas_fingerprint`, `book.digest`, `Table.fingerprint()`, `source_sha`,
`document_digest` — is the table in
[references/audit-record.md](references/audit-record.md).

### Step 3d: For a change, say which numbers moved

```bash
uv run gspio diff before.audit.json after.audit.json            # formulas, tables, data; and values
uv run gspio diff git:main:model.audit.json /tmp/audit.json     # against the committed record
```

`gspio diff` on two audit files says what changed — formulas, tables, policy
data — and, reading the two results files the audit files record, which
lines' numbers moved, in how many policies, from which period and by how
much; `gspio compare` answers a different question, whether two runs of *one*
artifact agree. Give `--results BEFORE AFTER` where the audit files record no
results file. Put the moved lines in the review: a line marked `(self)` whose
formula the change did not mean to touch, or numbers that move under an
unchanged `formulas_fingerprint` with no table or data change, is a finding.

For a scenario run, the BASE scenario must be the reconciled model:
`result.fingerprint("BASE") == model.main(af).graph.fingerprint()`. If it is
not, BASE is not the model that was reconciled — Critical.

To hand one policy to a reviewer who does not read Python:
`uv run gspio sheet /tmp/audit.json -o policy.xlsx --results /tmp/results.parquet`
(one Timeline per sampled policy, every formula and tier, every number the
run's own double, no cell a formula).

### Step 4: Classify issues

Every issue gets a file:line reference, a severity, and a concrete description. See the Issue Classification section below.

---

## Layer 1: Gaspatchio Code Quality

Check for anti-patterns against the reference file: [references/gaspatchio-antipatterns.md](references/gaspatchio-antipatterns.md)

| Anti-pattern | Severity | What to look for |
|---|---|---|
| `map_elements` / `apply` in model code | Critical | Any use of `.map_elements()` or `.apply()` in projection code. If the logic is reusable, recommend rewriting as an accessor using `gaspatchio-extending` skill. |
| Python for-loops over data rows | Critical | `for row in df.iter_rows()`, `for i in range(len(df))`, etc. If the loop implements a reusable calculation, route to `gaspatchio-extending` skill for proper accessor implementation. |
| Scalar/list confusion | Critical | Passing a scalar where a list column is expected, or vice versa |
| Inline Polars instead of `Table.lookup()` | Important | Raw `df.filter()` / `df.join()` instead of the Table API |
| Guessed API signatures (not verified via `gspio docs`) | Important | Method calls with wrong parameters or invented methods |
| Model tested by parsing stdout | Important | Save results to parquet and inspect with `gspio describe --json`, not stdout parsing |
| Wrong projection accessor | Important | Using `.list.sum()` where `.projection.cumulative_survival()` is needed |
| Hardcoded assumptions (magic numbers) | Important | Literal numbers like `0.015` instead of `Table.lookup()` or named constants |
| Missing `when/then/otherwise` for conditionals | Minor | Boolean masking like `value * (condition)` instead of explicit conditionals |
| No section header comments | Minor | Model code without `# SECTION N: DESCRIPTION` headers |
| Dead code | Important | `gspio graph unused` lists a `superseded` definition, or a `terminal` the author cannot name as a result |
| A line through `.polars_native()` | Important | It records as `engine_native`: it runs only on Polars, and so does every calculation that reads it. `gspio graph tiers` names the line; `gspio validate audit.json --engine jax` names it and every calculation that reads it. Ask for the declared form where one exists (`fill_nan(0.0)`, `list.reverse()`, `norm_cdf()`, `accumulate(reverse=True)`, `(af.x >= lo) & (af.x <= hi)` for `is_between`); where none exists, the escape is the honest line — record why |
| A band written in raw Polars | Important | `pl.col("x").is_in([...])`, `.cut([...])` record Polars' display text, so a change to the values can leave the fingerprint unmoved. Use `af.x.is_in([...])` / `af.x.cut(...)`, which record their values |
| An escape that works around a refusal | Important | The framework refuses a table, curve or schedule read inside an undeclared engine expression (the fingerprint would not move with the table), and refuses a line that would convert one kind into another (a number filled with text, branches of two kinds, a date compared with a number). A model that casts or escapes past either has hidden what the refusal named: check the read is stored as its own column first, and the conversion is written (`.to_text()`, `.to_float()`) where it is meant |
| Assumption table built from a frame in code | Important (production) | `Table(source=df)` with `df` built or filtered in the model: `gspio verify --assumptions` cannot decide it. Hand `Table` the file path |

### Anti-Pattern Check: Python Loops Over Data

Grep the model code for these patterns:
- `for.*in.*iter_rows` — should use AF column operations
- `for.*in.*range` — should use list columns + `accumulate`
- `for.*enumerate` — should use vectorised Polars/AF operations
- `results.append` — should use AF column assignments
- `math.ceil` or `math.floor` — should use `af.col.ceil()` / `af.col.floor()`
- `import math` — check if any math functions have AF equivalents

For each match found:
1. Check if there is a gaspatchio equivalent (`accumulate`, `previous_period`, `ceil`, etc.)
2. If yes, flag it: "This loop/stdlib call could use gaspatchio's `<method>` — consider refactoring"
3. If no gaspatchio equivalent exists, verify the loop is justified and scoped to the minimum necessary

---

## Layer 2: Actuarial Methodology (ASOP 56-informed)

Reference: [references/asop56-checklist.md](references/asop56-checklist.md)

### Correctness (Critical)

These issues produce wrong numbers. Every one must be verified:

- **Formulas mathematically correct?** Trace each formula back to the specification or source model. Check operator precedence, parenthesization, and sign conventions.
- **Lookup table references correct?** Verify that each `Table.lookup()` maps the right dimension columns to the right table. A mortality table keyed by attained age must not receive issue age.
- **Calculation order correct?** Decrements must apply before dependent cashflows. Account values must update before claims that reference them. Check that no variable uses a value that hasn't been computed yet.
- **Multiplicative vs additive operations correct?** Survival is multiplicative (`cum_prod`). Reserve changes are additive. Mixing these up produces subtly wrong results that pass sign checks but fail magnitude checks.
- **Decrement timing consistent (BOP vs mid-month vs EOP)?** All decrements in a model must use the same timing convention. Mixed timing is a common source of 1-5% reconciliation gaps.

### Assumption Integrity (Important)

- **Changed assumptions consistent with unchanged ones?** If mortality rates changed, did lapse rates also need updating? Are economic assumptions internally consistent (discount rate vs inflation)?
- **Sources documented?** Every assumption table should trace to a named source (experience study, regulatory table, pricing basis). Undocumented assumptions are audit findings.
- **Aggregate assumptions reasonable?** Spot-check: are mortality rates in the expected range for the age band? Are lapse rates declining with duration as expected? Do expense assumptions scale reasonably?
- **Dimension mappings correct?** Verify that lookup dimensions match the model point fields. A table with `attained_age` as a key should not be looked up with `issue_age`.

### Change Impact (Important)

These apply when reviewing changes to an existing model:

- **Change propagated to all dependent locations?** If a mortality rate formula changed, did all downstream variables (deaths, claims, reserves, PVs) get re-validated?
- **Unintended side effects?** Export the model before and after the change and run `gspio diff before.audit.json after.audit.json` (Step 3d): it names every line whose numbers moved, by how much and from which period. A "small" change to lapse rates can move BEL by double digits.
- **Analysis of change plausible?** The direction and magnitude of output changes should make actuarial sense. If increasing mortality rates causes reserves to decrease, something is wrong.
- **Boundary conditions preserved?** Edge cases (duration 0, maturity month, zero account value) should still behave correctly after the change.

### Documentation (Minor)

- **Change rationale documented?** Commit messages, code comments, or a build log should explain WHY the change was made, not just WHAT changed.
- **Material limitations disclosed?** If the model makes simplifying assumptions (e.g., no dynamic policyholder behavior, flat yield curve), these should be documented.
- **Methodology description current?** If the model has an accompanying methodology document, it should reflect the current code.

---

## Issue Classification

| Severity | Definition | Action |
|---|---|---|
| **Critical** | Will produce wrong numbers or crash at runtime | Must fix before proceeding. Review is blocked. |
| **Important** | Methodology deviation, code quality issue, or maintainability risk | Must fix before production. Review is blocked. |
| **Minor** | Documentation gap, style issue, or potential improvement | Fix when convenient. Does not block review. |

### Severity guidance

- If you're unsure whether something is Critical or Important, it's Critical.
- If you're unsure whether something is Important or Minor, it's Important.
- Err on the side of higher severity. Downgrading is easy; missing a real issue is expensive.

---

## Distrust-Based Review

The reviewer should adopt a posture of constructive skepticism. Do NOT trust:

- **"Results look reasonable"** -- Run the model and check quantitatively. "Reasonable" is not a number. Compare against expected ranges, source data, or a previous model run.
- **"This assumption is close enough"** -- Compare against the source data. Show the actual values side by side. Quantify "close enough" with a tolerance threshold.
- **"We already checked this"** -- Verify the evidence exists. If there's no recorded comparison (diff output, reconciliation log entry), it wasn't checked.
- **"The change is small"** -- Small changes can have large downstream effects. A 0.1% change in monthly mortality compounds over 30 years of projection. Run before/after comparisons.
- **"The formula is standard"** -- Standard formulas have implementation variants (continuous vs discrete, BOP vs EOP, annual vs monthly). Verify which variant this model uses.

This is not about distrust of people. It is about distrust of unverified claims. Every assertion should be backed by evidence that can be inspected.

---

## Review Output Format

Present review findings in this structure:

```markdown
## Model Review: [model name]

### Summary
[1-2 sentences: overall assessment — pass, pass with conditions, or fail]

### Critical Issues
- [file:line] [description] [why it matters]

### Important Issues
- [file:line] [description] [recommendation]

### Minor Issues
- [file:line] [description]

### Positive Observations
- [what the model does well — good patterns, clear structure, thorough assumption handling]
```

### Output rules

- Every issue MUST have a file:line reference. "The model has magic numbers" is not actionable. "`model.py:47` hardcodes `0.015` instead of looking up the discount rate" is.
- Critical and Important issues MUST include a recommendation or fix direction.
- Positive observations are not filler. Call out genuinely good practices so they get reinforced.
- If the model passes with no Critical or Important issues, say so clearly.

---

## Reference Files

| Topic | File | When to Load |
|---|---|---|
| **Gaspatchio anti-patterns** | [references/gaspatchio-antipatterns.md](references/gaspatchio-antipatterns.md) | When checking code quality (Layer 1) |
| **ASOP 56 checklist** | [references/asop56-checklist.md](references/asop56-checklist.md) | When checking actuarial methodology (Layer 2) |
| **The audit record** | [references/audit-record.md](references/audit-record.md) | Steps 3b–3d: which identity answers what, `gspio verify`, `gspio diff`, read windows, the one-policy workbook, the Python doors, what 1.0 does not do |

---

## Red Flags — You Are Skipping Review

| Thought | Reality |
|---------|---------|
| "The model runs, so it's fine" | Running != correct. A model with `map_elements` runs but is 100x slower. |
| "I already checked the outputs" | Checking outputs is reconciliation, not review. Code quality and methodology need separate verification. |
| "Review is only for production models" | Catching anti-patterns early is cheaper. Review now. |
| "The model is simple, review is overkill" | Simple models still have scalar/list confusion, missing section headers, and hardcoded assumptions. |
| "I wrote the model, I know it's good" | Self-review is necessary but insufficient. Fresh eyes catch different issues. |
| "`verify` didn't say differs, so it passed" | Exit 4 is "could not be checked", not agreement. Find what it could not decide and make it decidable. |
| "The graph fingerprints match, so the numbers match" | `graph_fingerprint` does not cover the policy data. Check `book.digest` too, or `verify --model-points`. |
| "The refusal is in the way; `.polars_native()` gets past it" | The refusal named what the line would hide. Escaping it makes the line Polars-only and can take its table out of the fingerprint. |
| "The artifact shows one policy, so that's the book's shape" | `calc-graph` samples one policy by default (`:1`). Say whose numbers you read, or export the ones you mean. |

---

## Integration

**Called after:**
- `gaspatchio-model-building` — **REQUIRED** after model building is complete
- `gaspatchio-model-reconciliation` — optional, after reconciliation confirms numerical correctness

**Routes to when issues found:**
- `gaspatchio-extending` — when `map_elements` or Python for-loops should be rewritten as proper accessors
- `gaspatchio-model-building` — when structural issues require model refactoring

**Called by:**
- `gaspatchio-model-building` — Integration section routes here as a required next step

---

## Completion Gate

The review is complete when:

- [ ] All Critical issues have been fixed and verified (re-run the model)
- [ ] All Important issues have been fixed or have an agreed remediation plan with a deadline
- [ ] Minor issues have been logged (fix not required to pass review)
- [ ] The model runs successfully: `uv run gspio run-single-policy model.py data.parquet 1`
- [ ] `gspio graph unused` and `gspio graph holes` were run, and every `superseded`, unkept `terminal` and hole is in the review
- [ ] `gspio verify` was run on the audit file against the files reviewed, and exited 0 — or every indeterminate line is in the review with its cause
- [ ] For a change: `gspio diff` on the before and after audit files is in the review, and every moved line is explained
- [ ] For a scenario run: `result.fingerprint("BASE")` equals the standalone model's `graph.fingerprint()`
- [ ] The review output has been written in the format above

If any Critical or Important issue remains unaddressed, the review is **not complete**.
