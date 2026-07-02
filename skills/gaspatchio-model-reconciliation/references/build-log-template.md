# <Model Name> Build Log

This document details the step-by-step process of building and reconciling the `<model_name>` gaspatchio model against a <source system> source model.

## Objective

State the exact reconciliation target(s) for the primary specimen policy:
- Primary headline metric(s): <e.g. PV profit / BEL / reserve> with target number(s)
- Target tolerance: <exact match | abs tol | rel tol>
- Specimen policy ID + key point attributes

---

## Phase 1: Initial Model Structure

### Step 1: Identify Target Policy
Show how you found it, and include the model point row as a table.

### Step 2: Understand Assumption Tables
List each assumption file/table, key columns/dimensions, and any non-obvious mappings.
Include any `gspio describe ...` findings that matter.

### Step 3: Create Initial Model Skeleton
Describe the build order (assumptions → timeline → indexing → lookups → decrements → cashflows → outputs).
Record the first "wrong-but-running" metric result for the specimen policy.

---

## Phase 2: Reconciliation Fixes

For each fix, use this EXACT narrative template:

### Fix N: <short name>
**Problem**: What didn't match (which variable, which time(s), how big)?

**Investigation**: What you compared and how (diff output, traced Excel formula, inspected assumption values).
Include a small table of before/after or a couple of key rows/periods.
Include any Tier 2/3 diagnostic results (regression stats, PCA loadings, heatmap observations).

**Root Cause**: The single concrete reason for the mismatch (timing convention, offset, rounding, data quality, etc.).

**Fix**: The exact code change (small snippet) + where it lives (file/function).

**Result**: What moved numerically (old → new), and whether it now matches (include delta).

Add `---` separators between fixes.

---

## Phase 3: Code Cleanup (after numbers match)
Summarize refactors that did NOT change results (structure, naming, removing debugging hacks).
Use a small before/after table if useful.

---

## Final Model Statistics
- Lines of code (rough)
- Projection length and frequency
- Output columns (rough)
- Match-to-target summary (delta, tolerance)

---

## Improvements

### Things I Wish I Had Known Earlier
Bullet list of gotchas (timing conventions, assumption quirks, target-data structure pitfalls).

### What I Learned
Bullet list: reconciliation process improvements and reusable patterns.

### How Gaspatchio Could Improve (optional)
Only include if you found genuine framework friction (APIs, docs, ergonomics).

---

## Appendix: Key Formulas
Put the core formulas and timing conventions in one place.
