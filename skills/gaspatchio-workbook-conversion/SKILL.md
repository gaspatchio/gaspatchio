---
name: gaspatchio-workbook-conversion
description: Use when converting an Excel workbook to a gaspatchio model – enforces the reader trust boundary, the three-proof reconciliation structure, defined-name assumption extraction, and faithful-quirk rules, so every claim the conversion makes carries an executable proof.
allowed-tools: Bash(uv:*,gspio:*,marinade:*) Read Grep Glob
---

# Converting a Workbook to a Gaspatchio Model

## Overview

A conversion's output is not just a model — it is a set of **claims**: the gold
standard was read losslessly, the Excel semantics were translated correctly, the
recursion reproduces the source. This skill makes each claim carry its own
executable proof, so that when a number is off, the failure localises to one
proof instead of dissolving into "somewhere in the model".

Distilled from three independent conversions of the same UL workbook (two of
them clean-room), which converged on the same discipline from opposite starting
points.

## When to use this skill

Standalone — it does not require any other skill to have been run first. Use it
whenever a workbook's cached values are the gold standard you must match.

Related skills, and what this one deliberately does not repeat:

| Skill | Owns |
|---|---|
| `gaspatchio-model-discovery` | Structure extraction (xl-marinade), the workbook→gaspatchio translation table, SCC/state-machine detection — read its `references/spreadsheet-conversion.md` **first** |
| `gaspatchio-model-building` | The ActuarialFrame idioms the model is written in |
| `gaspatchio-model-reconciliation` | Diff techniques once both sides produce numbers |
| **This skill** | The conversion *discipline*: what to trust, what to prove, in what order |

Tooling: the extraction stack is [xl-marinade](https://marinade.gaspatchio.dev/) —
`uv tool install 'xl-marinade[llm,vba]>=0.3.0'`, then `marinade extract`. The discovery
skill's `references/spreadsheet-conversion.md` owns the usage detail, the 0.3.0 floor
rationale, and the open upstream caveats; install and version-check before extracting.

## HARD GATE: the value reader is inside the trust boundary

**Never treat an Excel reader as trusted infrastructure for a value proof.**

`fastexcel`/calamine silently truncates floats to ~9 significant figures when a
column's dtype infers as `String` — a text header row above the data block is
enough to trigger it. From an executed clean-room repro:

```
read A dtypes[8]  = String    (header row left in)
read B dtypes[8]  = Float64   (header rows skipped)

cell  xml (truth)              read A (String)      read B (Float64)       A_ok  B_ok
J4    0.970873786407767        0.970873786          0.970873786407767      False True
M4    497761.77773510211       497761.777735102     497761.7777351021      False True
R4    2238.2200000000003       2238.22              2238.2200000000003     False True
```

Two of three probe cells wrong in the 10th significant figure — small enough to
hide under a careless tolerance, large enough to make an "exact" claim false.
Before any reader output becomes your gold standard:

1. **Skip text headers** when reading so the data block infers `Float64`.
2. **Assert dtypes after load** — a `String` column among your values is a bug.
3. **Validate the reader against the raw sheet XML `<v>` values** on a probe
   set spanning every value column. This is proof one, below.

## The three-proof structure

Build the proofs in order; each isolates one question, so any residual has
exactly one place to live:

| # | Proof | Question it isolates |
|---|---|---|
| 1 | **Verify the reader** — reader output vs raw sheet XML `<v>` values | Is the gold standard read losslessly? |
| 2 | **Verify formulas from cached precedents** — re-evaluate each formula pattern feeding it the workbook's own cached inputs | Are the Excel semantics right, recursion excluded? |
| 3 | **Reconcile the full model** — gaspatchio output vs cached values, column by column, period by period | Is the recursion right? |

The middle proof is what makes the headline number interpretable: when every
formula is bit-exact from the workbook's own cached inputs, any residual in the
full run is recursion drift and nothing else. Skipping it collapses proofs 2 and
3 into one undiagnosable comparison.

Each proof is its own runnable script committed with the model. The workbook
itself is read-only throughout — extract values out; commit nothing back.

## Read assumptions through defined names, not coordinates

Resolve `face`, `COIs`, `premiums` and their kin from the workbook's own name
table, so the model reads its inputs through the same handles the sheet's
formulas use. A future row insertion moves the data and the names together;
hardcoded offsets silently read the wrong cells. Single-cell defined names are
model-point columns, never literals — a hardcoded scalar works until the second
policy.

## Reproduce the source's quirks; don't fix them silently

A faithful twin reproduces the quirk **and flags it for the owner**; a silent
fix diverges the first time the quirk matters, and a silent quirk becomes your
bug later. The three that recur:

- **VLOOKUP approximate-match clamps past table end.** Reproduce the clamp
  (`.clip()` on the key, or an overflow strategy), and note it in the report —
  the sheet is reading its last row for ages it never priced.
- **Charges computed but never applied post-lapse.** Model the notional and the
  applied quantity **separately**. Deriving flows from state differences
  conflates "no charge" with "nothing left to charge against" — in one
  clean-room run that derivation was silently wrong for 55 of 111 projection
  years while the closing balance reconciled exactly.
- **Rounding placement inside the recursion.** `ROUND(charge)` applied to an
  unrounded balance and `round(balance)` agree only while the balance is an
  exact multiple of the rounding unit. Match the sheet's placement
  (`round_charge=` on the op for the former, `.round()` on the state for the
  latter), and say which one the sheet uses in the report.

## Reconcile the full grid, not the headline column

The recursion walks every column in order regardless, so the closing balance
can reconcile exactly while intermediate columns are wrong. Diff **every**
output column over **every** period with a machine comparison — never
eyeballing — and report worst absolute and relative residuals per column. The
one real modelling error across three conversion rounds was invisible to a
closing-balance check and caught instantly by the column-by-column diff: 56
cells, two columns, all post-lapse.

Branches the shipped inputs never exercise (corridor tests, guarantees,
mass-lapse triggers) have no cached reference at all — which is exactly where
conversion bugs hide. Recalculate the workbook with `formulas` or `pycel` to
manufacture references for them, and validate that second engine against the
cached values before trusting it (the discovery skill's reference covers the
tooling).

## Deliverables

1. The model, runnable via `gspio run-model` or a standalone script.
2. The three proof scripts (`verify_reader`, `verify_formulas`, `reconcile`),
   each self-reporting pass/fail.
3. A reconciliation report: per-column match counts, worst residuals, and the
   quirks reproduced (with their locations in the workbook).
4. `LEARNINGS.md` kept from minute zero — friction recorded when it happens,
   with an executed repro before anything is called a bug.

## Integration

- **Called by:** `gaspatchio-model-discovery` — once discovery has extracted the
  workbook's structure and classified the model, this skill governs how the
  conversion is proven. It can equally be invoked standalone when the task
  arrives as "convert this workbook".
- **Routes to:** `gaspatchio-model-building` for writing the model itself;
  `gaspatchio-model-reconciliation` for diff techniques inside proof three;
  `gaspatchio-extending` if a workbook function has no framework equivalent.
- **Required next:** `gaspatchio-model-review` before the conversion is
  reported as complete — the completion gate below is necessary, not
  sufficient.

## Red Flags — stop if you catch yourself thinking

| Rationalization | Reality |
|---|---|
| "The reader is a standard library; its output is fine" | The reader is *inside the trust boundary*. Two of three probe cells were wrong in the 10th significant figure in a real run. Prove it against the raw XML. |
| "The closing balance reconciles, so the model is right" | The recursion walks every column regardless. The one real error in three rounds was invisible to the closing balance and obvious in the full grid. |
| "I'll reconcile at the end instead of building the proofs first" | Without proof two, a residual could be a reader artefact, a semantics error, or recursion drift — you will debug all three at once. |
| "The sheet's VLOOKUP clamp / notional charge / rounding spot is obviously a bug — I'll just fix it" | A silent fix diverges the first time the quirk matters. Reproduce it, flag it, let the owner decide. |
| "These cells are close enough" | Name the tolerance and justify it against the workbook's own rounding. "Close" without a number is how reader truncation hides. |

## COMPLETION GATE

Do not report the conversion as done until every box is checked:

- [ ] Reader validated against raw sheet XML on probe cells spanning every
      value column; all dtypes asserted `Float64`.
- [ ] Every formula pattern re-evaluated bit-exact from cached precedents
      (recursion excluded), or the exceptions listed with reasons.
- [ ] Full-grid reconciliation: every output column, every period, machine
      diff, residuals reported against the workbook's own rounding.
- [ ] Assumptions read through defined names; zero hardcoded coordinates or
      scalar literals that belong to the model point.
- [ ] Every reproduced quirk named in the report with its workbook location.
- [ ] The workbook is byte-identical to when you started.
