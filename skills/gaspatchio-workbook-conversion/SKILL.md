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
One of those caveats bears on every proof below: **xl-marinade 0.4.0 drops edges to blank
cells** — a formula that reads an empty cell can have no row in `agent_dependencies` —
and a read of a blank is the wiring defect a review most needs to see. Take references
from the formula text, not the edge table alone, until a later release says otherwise.

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

## Negative controls: a proof that cannot fail proves nothing

Proof three passing says the numbers agree. It does not say the model is built the
way the workbook is: a closing balance can reconcile in every cell while not reading a
line the workbook builds it from, because on the shipped inputs that line's value
arrives some other way. In one conversion every cell reconciled with exactly that
flaw, and only a mutation of the line exposed it. So once proof three passes, break
the model on purpose and watch the proof fail:

1. **Copy the model beside itself** (`model_mutant.py`, so its relative paths still
   resolve), change **one line**, and re-run the same proof-three script against the
   copy. Delete the copy afterwards; the workbook is never edited.
2. **Mutate every line that feeds a total** with a plausible mistake — drop a term,
   read the wrong period, swap a rate — and **"fix" every quirk you reproduced**.
3. **Every mutation must break what the workbook says depends on it.** List the
   workbook cells downstream of the mutated line (the formula text's references,
   followed forward); each must stop reconciling. A downstream cell that still
   reconciles is a model line that does not read what the workbook builds it from —
   right numbers, wrong structure. Fix the structure so the model line reads what the
   workbook's cell reads, then re-run proof three and the control.
4. **A "fixed" quirk that breaks nothing is invisible on the shipped inputs** — say so
   in the report beside the quirk, with the count, rather than claiming it matters.

`gspio diff` reads the model side of each control: export the base and the mutant with
their results, and it lists the line you edited `(self)` and every line that moved
with it `(inherited)`, policies and first period moved — the total that is missing from
that list is the one that does not read the line.

```bash
gspio calc-graph model.py mp.parquet -o base.audit.json --results base.parquet
gspio calc-graph model_mutant.py mp.parquet -o mutant.audit.json --results mutant.parquet
gspio diff base.audit.json mutant.audit.json      # exit 1: something moved, and which lines
```

Keep the controls as their own script (`negative_controls`) with a table in the
report: mutation, cells that stop reconciling, and whether that is what the workbook's
dependencies predict.

## Read assumptions through defined names, not coordinates

Resolve `face`, `COIs`, `premiums` and their kin from the workbook's own name
table, so the model reads its inputs through the same handles the sheet's
formulas use. A future row insertion moves the data and the names together;
hardcoded offsets silently read the wrong cells.

**When the workbook has no defined names** — many have none, or only stale ones no
formula reads (search the formula text for each name) — read each input by its
labelled coordinate and **assert the label at that coordinate** in the extractor (the
row label beside a rate, the year header above it), so a moved row fails loudly instead
of silently reading its neighbour. Say in the report that the rule had nothing to bind
to, and what you read instead.

**Single-cell inputs are model-point columns, never literals** — a hardcoded scalar
works until the second policy. A model-point column is also what a scenario plan
shocks: a shock names exactly one target, an assumption table by its `Table` name
(`table=`) or a model-point column such as a valuation rate (`column=`), so
`AdditiveShock(delta=0.01, column="valuation_rate")` moves it in that scenario while the
plan runs the model you reconciled, unchanged. A literal in the formula cannot be
shocked at all.

**Never bring a number in with `.item()`.** Read in setup and used as a Python float,
it becomes a literal in the formula: the audit file records no link to the file it came
from (nothing in `reads_assumptions`, nothing in `assumptions`), and `gspio verify
--assumptions` has no table to hold against that file. Keep it a model-point column, or
read it through a `Table` built from the file's path, keyed on the row you want:

```python
from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
import polars as pl

expenses = Table(name="expenses", source="assumptions/expenses.parquet",
                 dimensions={"product": "product"}, value="acquisition")
af = ActuarialFrame(pl.DataFrame({"policy_id": ["P1", "P2"], "pols": [1.0, 2.0]}))
af.acquisition = expenses.lookup(product="TERM")   # a bare string is a dimension value
af.expense = af.pols * af.acquisition              # the record names 'expenses' and its content
```

## Reproduce the source's quirks; don't fix them silently

A faithful twin reproduces the quirk **and flags it for the owner**; a silent
fix diverges the first time the quirk matters, and a silent quirk becomes your
bug later. The ones that recur:

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
- **Excel's normal distribution has no bit-for-bit twin.** `NORM.S.DIST(z, TRUE)`,
  `NORMSDIST(z)` and `NORM.DIST(z, 0, 1, TRUE)` — the N(d1) and N(d2) of a
  guarantee priced as an option — are `z.norm_cdf()`; `z.excel.norm_s_dist()`
  is the same node. `NORM.DIST(x, mean, sd, TRUE)` is
  `((x - mean) / sd).norm_cdf()`. Excel's algorithm is unpublished, so
  reconcile Φ to about 1e-14 relative and say so in the report. Never hand-build
  Φ: the textbook `0.5 * (1 + erf(x / √2))` answers 0.0 at -8.36, and a series
  in an accessor records as engine text. The density, `NORM.S.DIST(z, FALSE)`,
  is `(-z**2 / 2).exp() / (2 * math.pi) ** 0.5`. `NORM.S.INV` is not in 1.0:
  compute a constant such as the 99.5% point in setup with
  `statistics.NormalDist().inv_cdf(0.995)`.
- **Excel's `^` with a whole-number exponent is not `pow`.** The worksheet computes
  `(1+r)^n` by square-and-multiply (in two conversions every cached value matched that
  bit for bit, and `pow` did not); gaspatchio's `**` is the C library's `pow`. Write
  `(1 + af.r) ** af.n` and expect the last bits to differ, more as `n` grows — at most 5
  ulp up to `n = 10`, 79 ulp (1.1e-14 relative) by `n = 120`. It is a residual class
  with that bound, not a formula error.
- **A reference to a blank cell reads 0.** A formula pointing one row or one sheet away
  from its input evaluates to 0 today and stays 0 when the intended input changes.
  Reproduce it as zero-valued wiring, flag it with its cell for the owner, and find
  these from the formula text: xl-marinade 0.4.0 drops exactly these edges.

## Reconcile the full grid, not the headline column

The recursion walks every column in order regardless, so the closing balance
can reconcile exactly while intermediate columns are wrong. Diff **every**
output column over **every** period with a machine comparison — never
eyeballing — and report worst absolute and relative residuals per column. The
one real modelling error across three conversion rounds was invisible to a
closing-balance check and caught instantly by the column-by-column diff: 56
cells, two columns, all post-lapse.

**Every non-zero residual belongs to a named class with a stated bound**, and the
report counts the cells in each: Excel's cosmetic zero (below 2⁻⁴⁸ of the operands —
the discovery reference states the bound), whole-number `^` (by exponent, above), Φ
(about 1e-14 relative), a sum taken in another order (an `NPV` or a long `SUM`; bound
it relative to the largest term), and `t_years()` on a calendar grid against a
workbook's `A/12` (the last bits; a fixed-step axis gives `k/12` exactly). A residual in
no class is a defect until shown otherwise. Never widen the global tolerance to absorb
one class: bound each class where it lives and keep every other cell at the tolerance
the workbook's own rounding justifies.

Branches the shipped inputs never exercise (corridor tests, guarantees,
mass-lapse triggers) have no cached reference at all — which is exactly where
conversion bugs hide. Recalculate the workbook with `formulas` or `pycel` to
manufacture references for them, and validate that second engine against the
cached values before trusting it (the discovery skill's reference covers the
tooling).

## Prove the structure: compare the two graphs by hand

No comparator between a model's graph and a workbook's ships in 1.0. The comparison is
still owed — it is what says the model is built like the sheet, not merely agreeing with
it — so make it by hand, line by line:

- **The model side is the audit file.** Every read in it states which periods it takes:
  a shifted read its `offset` (`-1` is last period), an aggregation its window
  `periods: {from, to}` — each bound a distance from the period being computed or
  `"first"`/`"last"` — and a literal `list.get` its `position`; a read with none of them
  reads the period being computed. `DIRECT` means the value flows into the answer,
  `INDIRECT` a key, a condition or a selection (no window is ever written on it).
- **The workbook side is xl-marinade's cell-level `agent_dependencies`** for one row of
  each column. Read cells, not bindings — a binding can group several columns into one —
  and take the reads of blank cells from the formula text (the 0.4.0 caveat above).
- **Match the reads.** `C5 = C4*(1-B4)` reads its own previous row and last period's
  rate: the window `{first, -1}`, which `cumulative_survival()` records at its default.
  `D5 = SUM($C$2:C5)` is `{first, 0}`. A model line whose window differs from its cell's
  reads is a structural mismatch even when every number agrees.
- **Read the window, never the formula text.** An audit node's `formula` is the source
  line as written; a regex over it is a guess about what the line reads.

```bash
gspio graph precedents model.audit.json surv_bop --json   # each read with its window
gspio graph unused model.audit.json --keep reserve        # calculations nothing reads
```

```text
"reads": [{"source": "q@1", "target": "surv_bop@1",
           "transformations": [{"type": "DIRECT", "subtype": "AGGREGATION",
                                "periods": {"from": "first", "to": -1}}]}]
```

Set `unused` beside the workbook's cells that have no consumers: a computed cell is not
a used cell on either side. Give the comparison its own negative control — run it on a
mutant whose line reads one period more or less; a comparison that reports nothing there
proves nothing.

## Deliverables

1. The model, runnable via `gspio run-model` or a standalone script, with every
   assumption `Table` built from its file's path (not a frame built in code).
2. The three proof scripts (`verify_reader`, `verify_formulas`, `reconcile`) and
   `negative_controls`, each self-reporting pass/fail.
3. A reconciliation report: per-column match counts, worst residuals with each
   residual's class, the quirks reproduced (with their locations in the workbook),
   and the negative-control table.
4. **The audit file, verified.** Export it with the results, then hold every file
   against it; `gspio verify` exits 0 only when every check asked for agrees, and
   library versions and git are evidence that moves no exit status:

   ```bash
   gspio calc-graph model.py mp.parquet -o model.audit.json --results results.parquet
   gspio verify model.audit.json --model model.py --model-points mp.parquet \
       --results results.parquet --assumptions assumptions/
   ```

   `--assumptions` reads each recorded table back from its file (a directory, a
   file, or `NAME=FILE`) — which is why item 1 hands `Table` the path: a table built
   from a frame in code can agree with a file of the same values but never differ from
   one — against a file of other values it verifies *could not be checked* (exit 4).
   The record names the model by identities: `formulas_fingerprint` moves only when a formula moves;
   `graph_fingerprint` moves when a formula or an assumption table's content moves;
   `book.digest` moves when the policy data moves; `Table.fingerprint()` is one
   table's content. `gaspatchio-model-review` holds the full table of which identity
   answers which question.
5. **The structural comparison** — the hand route above, each line's window against
   its cell's reads, with its own negative control — or, where it was not made, a
   sentence saying so.
6. **A one-policy sheet for the reviewer.** `gspio sheet` lays an audit file's
   policies out as an `.xlsx` workbook a reviewer opens in Excel with no Python — a
   README naming the record by its digests, one Timeline per policy (a row per
   period, a column per calculation headed by its formula and tier), then Scalars,
   Nodes, Edges and Assumptions — every number the run's own double and no cell a
   formula. The sheet carries the policies the export sampled, and **`calc-graph`
   samples one policy by default** (`:1`, the first row of the book); pass
   `--policies` for the ones the reviewer should see:

   ```bash
   gspio sheet model.audit.json --results results.parquet -o policy.xlsx
   gspio calc-graph model.py mp.parquet -o all.audit.json --policies all --xlsx all.xlsx
   ```

7. **For every later change, what was edited and what moved.** `gspio diff
   before.audit.json after.audit.json` says what changed — formulas, tables, policy
   data — and, reading the two results files the audit files record, which lines'
   numbers moved, in how many policies, from which period and by how much: the line
   edited `(self)`, the lines that moved with it `(inherited)`. (`gspio compare`
   answers a different question, whether two runs of *one* artifact agree.)
8. `LEARNINGS.md` kept from minute zero — friction recorded when it happens,
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
| "Proof three passed, so the structure is right" | Numbers can agree while a total does not read a line the workbook builds it from. Only a negative control — one mutated line, the proof re-run — shows it. |
| "I'll widen the tolerance so the last few cells pass" | Every residual has a named class and a bound (cosmetic zero, whole-number `^`, Φ, summation order). A residual in no class is a defect; a wider global tolerance hides the next one. |
| "I'll compare the graphs by parsing each node's formula" | The `formula` is source text. Read each read's window (`offset`, `periods`, `position`) from the audit file, and take the workbook's reads from the formula text, not the 0.4.0 edge table alone. |
| "I'll pull that one expense out with `.item()`" | It becomes a literal with no link to its file; `verify --assumptions` cannot hold it and a scenario cannot shock it. Model-point column or `Table` read. |

## COMPLETION GATE

Do not report the conversion as done until every box is checked:

- [ ] Reader validated against raw sheet XML on probe cells spanning every
      value column; all dtypes asserted `Float64`.
- [ ] Every formula pattern re-evaluated bit-exact from cached precedents
      (recursion excluded), or the exceptions listed with reasons.
- [ ] Full-grid reconciliation: every output column, every period, machine
      diff, residuals reported against the workbook's own rounding.
- [ ] Every non-zero residual counted in a named class with its bound.
- [ ] Negative controls run: every line feeding a total mutated and every quirk
      "fixed", each breaking what the workbook's dependencies predict, tabled in the
      report.
- [ ] Assumptions read through defined names — or, with none, by labelled
      coordinates with the label asserted; zero hardcoded coordinates, no `.item()`
      scalars, no scalar literals that belong to the model point.
- [ ] Every reproduced quirk named in the report with its workbook location.
- [ ] The audit file exported with its results, and `gspio verify` with `--model`,
      `--model-points`, `--results` and `--assumptions` exits 0.
- [ ] The structural comparison made by hand (windows against cell reads) with its
      negative control, or its absence stated in the report.
- [ ] The reviewer's sheet written for the policies they asked for (`calc-graph`
      alone samples only the first).
- [ ] The workbook is byte-identical to when you started.
