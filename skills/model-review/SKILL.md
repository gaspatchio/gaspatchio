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
- **Unintended side effects?** Run the model before and after the change. Compare key outputs. A "small" change to lapse rates can move BEL by double digits.
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

---

## Red Flags — You Are Skipping Review

| Thought | Reality |
|---------|---------|
| "The model runs, so it's fine" | Running != correct. A model with `map_elements` runs but is 100x slower. |
| "I already checked the outputs" | Checking outputs is reconciliation, not review. Code quality and methodology need separate verification. |
| "Review is only for production models" | Catching anti-patterns early is cheaper. Review now. |
| "The model is simple, review is overkill" | Simple models still have scalar/list confusion, missing section headers, and hardcoded assumptions. |
| "I wrote the model, I know it's good" | Self-review is necessary but insufficient. Fresh eyes catch different issues. |

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
- [ ] The review output has been written in the format above

If any Critical or Important issue remains unaddressed, the review is **not complete**.
