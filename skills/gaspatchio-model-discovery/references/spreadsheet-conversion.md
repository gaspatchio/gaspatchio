# Converting a spreadsheet model

A spreadsheet tells you what it computes. It does not tell you what it *means* in
gaspatchio, and the gap between those two is where silent conversion bugs live.

This file is the translation layer: how to read a workbook's structure, and what each
structural feature implies about the gaspatchio model you should write.

## Extract the structure first — do not read cells by hand

Reading formulas by clicking around a spreadsheet does not scale past a few dozen cells,
and it misses exactly the things that matter: which variables are recursive, which
lookups fall off the end of their table, where rounding happens.

Use [XL Marinade](https://marinade.gaspatchio.dev/), which extracts a workbook into a
SQLite formula graph:

```bash
uv tool install 'xl-marinade[llm,vba]>=0.3.0'   # extras matter: vba is a separate install
marinade --version                              # confirm >= 0.3.0 before extracting
marinade extract model.xlsx -o model.db
```

The 0.3.0 floor is not cosmetic: earlier releases report a mixed binding's *first*
formula rather than its dominant one (xl-marinade#12), have no version surface at all
(#13), and ship a skill documenting a pre-0.2.0 schema (#15) — an extract produced by
an older install differs in ways this file's recipes do not account for.

If the `xl-marinade` skill is available, invoke it — it owns the CLI and query surface
in detail. This file covers only what to do with the results.

Two caveats remain open upstream (verified 2026-08-18):

- **`agent_cells` semantics are a footgun** (xl-marinade#14): numeric cells carry NULL
  `data_type`, values are JSON-stringified, and an empty formula is `''` not NULL — the
  obvious SQL over it is silently wrong. Prefer the `agent_bindings` views; when you
  must query cells directly, read #14 first.
- **Within-column recurrences are invisible to the binding graph** (xl-marinade#16):
  `agent_binding_dependencies` drops intra-binding edges, so a column referencing its
  own previous row shows no self-edge. Never conclude "no recursion" from the binding
  graph alone — check the row-level formulas of any balance-like column.

The stable views are `agent_*` and `marinade_*`; the raw tables are internal. One
blessed exception: `defined_names` is a base table with no `agent_*` view yet — read
it, read-only. The two queries you will use constantly:

```sql
-- the model's variable list, auto-named from the sheet's own header row
SELECT address, label, formula_pattern FROM agent_bindings
WHERE sheet LIKE '%<sheet>%' ORDER BY address;

-- the workbook's defined names, with their ranges
SELECT name, destinations FROM defined_names;
```

`agent_bindings` collapses repeated formulas into model variables — a 2,000-formula
column becomes one binding with one `formula_pattern`. A sheet of 1,997 formulas
routinely reduces to ~20 labelled variables, which *is* your model's variable list.

**`formula_pattern` is one formula and cannot signal a mixed binding.** The schema
stores a single formula id per binding; since 0.3.0 it points at the binding's
*dominant* formula (before that, an arbitrary row's — very often the special case, not
the rule; xl-marinade#12), but a merged binding with exception rows still shows only
that one pattern. Never treat it as authoritative: for every binding that matters, read
the full distribution over the binding's row range before trusting the pattern:

```python
import re
from collections import Counter

# `address` comes straight from the agent_bindings query above — a
# sheet-qualified A1 range like "Projection!J16:J117". agent_cells_light
# stores row/col as 1-based numbers (column J is 10), so parse the range;
# binding the letter "J" matches nothing, silently.
sheet, rng = address.rsplit("!", 1)
col_letters, first_row, last_row = re.match(r"([A-Z]+)(\d+):[A-Z]+(\d+)", rng).groups()
col = sum((ord(c) - 64) * 26**i for i, c in enumerate(reversed(col_letters)))

rows = con.execute(
    "SELECT formula_r1c1 FROM agent_cells_light "
    "WHERE sheet=? AND col=? AND row BETWEEN ? AND ? AND formula_r1c1 IS NOT NULL",
    (sheet, col, int(first_row), int(last_row)),
)
print(Counter(f for (f,) in rows).most_common())
```

One dominant formula plus a handful of outliers is the signature of a special-cased
first row or a gated later block — read the outlier rows in full.

**`.xlsm` files need the `vba` extra.** Without it the VBA tables are silently empty and
you may conclude a workbook has no user-defined functions when it has several.

## The translation table

The middle column is mechanical. The right-hand column is why this file exists — each
of these produces a model that **runs and is wrong**, not a model that fails.

| The workbook has | Write it as | Silent failure if you get it wrong |
|---|---|---|
| A strongly-connected component in the binding graph | a rollforward state | Members that look like plain schedule lookups get written as closed-form columns. See "the lapse gate" below — this is the most common miss. |
| A forward offset into its **own** column (`R[-1]C` — cumulative px, running balances) | `accumulate()` / `cum_prod`-style closed forms | Written as a plain column it reads garbage from an unshifted neighbour — usually loud. The quiet failure is reaching for a full rollforward instead: correct, slow, unreadable. |
| A backward offset into its **own** column (`R[1]C` — PV rollbacks, mean reserves) | a **reversed** accumulation (reverse, accumulate, reverse back) or `next_period()` composition | Written as plain column assignments the model **runs and is wrong** — and in a reserving workbook those columns *are* the reserve. No cycle test can see this shape (gaspatchio#115). |
| A row offset into a **different, independent** column (`R[-1]C[-2]` — claims from last period's deaths) | `previous_period()` / `at_period(n)` on that column — still a plain assignment | Not a recurrence. Routed to `accumulate()` a one-period lag becomes a running total — runs and is wrong. Written unshifted it is off by one period everywhere. |
| No cycle **and no row offset** | plain column assignments | Reaching for a rollforward anyway costs clarity and speed for nothing. *Closed-form by default.* |
| `IF(<prior period cell> > 0, x, 0)` | `lapse_when_all_non_positive=[...]` | The gate makes premium and expense depend on prior state, so they belong **inside** the recursion. Written as columns they are correct until the policy lapses, then silently wrong — and most test policies never lapse. |
| A circular COI reference (NAR depends on the balance the COI reduces) | `deduct_nar(nar_timing=...)` | There are **three** conventions and they agree when rates are constant. The error only appears once rates vary, so it survives testing. Read the timing section below. |
| `ROUND(...,2)` between an opening and closing balance | `.round(2)` **inside** the rollforward | Rounding the final answer instead drifts monotonically — invisible in year 1, material by year 40. It compounds because each rounded balance opens the next period. |
| `VLOOKUP(x, tbl, n)` with no 4th argument | an explicit key cap or overflow strategy | Excel's approximate match silently reuses the last row past the end of a table. `Table.lookup()` is exact-match and **raises** — which is better, but you must expect it rather than assume the model is broken. |
| A wide sheet, e.g. age × {MNS, MS, FNS, FS} | `MeltDimension(columns=[...], name="...")` | — (fails loudly) |
| Defined names over ranges | `Table` dimensions + `value` | — (fails loudly) |
| Single-cell defined names (`face`, `iq`) | model-point columns | Hard-coding them as literals works until the second policy. |
| Two rate assumptions that look interchangeable | two separate arguments | A workbook may carry both a *credited* rate and a separate *rate for discounting COI*. Collapsing them is invisible while they are equal. |

## Finding the recurrences mechanically

You do not have to judge which variables are recursive — but it takes **two** tests,
not one, and order matters.

**Test 1 — the row-offset scan (run this first).** Any formula that reads *another
row* is time-sensitive and this scan finds every one of them. In R1C1 that is exactly
a non-zero row offset — `R[-1]C`, `R[1]C[-2]` — so it is one `LIKE`:

```sql
-- first pass: bindings whose dominant formula reads another row
SELECT address, label, formula_pattern FROM agent_bindings
WHERE formula_pattern LIKE '%R[%';

-- authoritative pass: per column, how many row formulas carry an offset —
-- catches the gated/mixed bindings whose dominant pattern hides it
SELECT sheet, col, COUNT(*) AS n,
       SUM(formula_r1c1 LIKE '%R[%') AS offset_rows
FROM agent_cells_light WHERE formula_r1c1 IS NOT NULL
GROUP BY sheet, col;
```

(`RC[-1]` — same row, different column — has no `R[` and correctly stays closed-form.
A split-off init row often shows a plain pattern while every propagation row beneath it
carries the offset; the second query is what tells you.)

The scan is deliberately broad — a bracketed row offset does not by itself make a
recurrence. Classify each hit by **whose** row it reads:

- **Its own column** (`R[-1]C` — no column bracket): a true recurrence. Forward is a
  rollforward-style accumulation — cumulative products and sums usually have closed
  forms. Backward (`R[1]C`) is a PV rollback, exactly as order-dependent, spelled as a
  *reversed* accumulation (reverse the series, accumulate, reverse back) or
  `next_period()` composition.
- **Another column that is itself state** (the prior period's account value, a running
  balance): the reader belongs **inside** the recursion — this is the lapse gate below.
- **Another, independent column** (`R[-1]C[-2]` into an input, schedule, or closed-form
  neighbour — claims from last period's deaths): not a recurrence at all. Write it as a
  plain assignment on a time-shifted input — `af.deaths.projection.previous_period()`
  (or `at_period(n)`). Forcing it through `accumulate()` turns a one-period lag into a
  running total.

None of these needs the state machine unless a within-period charge also reads the
running balance.

**Test 2 — within-period cycles (the escalation detector).** Strongly-connected
components of the binding dependency graph find the *genuine* cycles — the variables
that must live inside one rollforward state:

```sql
SELECT source_binding_id, target_binding_id FROM agent_binding_dependencies;
```

Feed those edges to Tarjan's algorithm and read off the components.

**The SCC test alone is not the split, and trusting it that way is the bad kind of
wrong.** A VM-20 NPR reserving workbook returns *zero* SCCs of size > 1 at both
binding and cell granularity — verdict "everything is closed-form" — while ten of its
columns, the PV rollbacks that *are* the reserve, carry recurrences (gaspatchio#115).
Two independent reasons: backward recurrences are DAGs, invisible to a cycle test *in
principle*; and the binding graph drops intra-binding edges, so even a forward
self-recurrence cannot form an SCC there (xl-marinade#16). The row-offset scan catches
all of them — including the lapse-gate example below — while the SCC test remains the
right detector for what it is good at: cross-binding within-period cycles.

### The lapse gate — the trap this catches

In one universal life workbook, the SCC contained `Premium` and `Expense Charge`, which
read as pure schedule lookups:

```
E4   VLOOKUP(B4, premiums, 3)                      <- year 1, ungated
E5   IF(R4 > 0, VLOOKUP(B5, premiums, 3), 0)       <- R = prior EOY account value
```

Only row 4 is a plain lookup. Every later row is gated on the prior period's closing
balance, which puts both variables inside the cycle. **Read more than the first data
row** — spreadsheets very often special-case it, and on a merged mixed binding
`formula_pattern` is one row's formula, which can be precisely that special case.
The distribution query above is what tells you; the pattern column cannot.

## Confirm consumption with the edge table before modelling structure

On a bug-for-bug twin, a structure that *looks* per-scenario / per-product / per-region
is a hypothesis, not a fact — **a computed cell is not necessarily a used cell.** One
capital workbook computed a correlation switch per scenario (`D41`/`E41`/`F41`, a
layout that plainly intends per-scenario behaviour), but all three consumers referenced
`$D$41` absolutely; modelling it per-scenario broke one scenario's SCR by ~856k. What
settled it was not re-reading formulas but one query:

```sql
SELECT from_cell, to_cell FROM agent_dependencies
WHERE to_cell IN ('...!D41', '...!E41', '...!F41');
-- three rows, all pointing at D41; E41 and F41 have no consumers
```

Before modelling any structural hypothesis, ask the edge table who actually reads the
cells. And treat **"dead cell adjacent to a wrong reference" as a defect signature** —
the same query pattern exposed a stress-annuity pair where the dead neighbour marked a
mis-pointed formula. Both belong in the conversion report as workbook findings.

## Timing conventions: check, never assume

The framework has three timing-sensitive methods and their defaults are not uniform:

| Method | Parameter | Default |
|---|---|---|
| `prospective_value()` | `timing` | `end_of_period` |
| `cumulative_survival()` | `rate_timing` | `beginning_of_period` |
| `deduct_nar()` | `nar_timing` | `beginning_of_period` |

**With constant rates every convention gives identical answers.** The mistake therefore
survives every test built on flat assumptions and only appears at age boundaries or on a
real curve. Confirm the source model's convention before assuming a difference is an
assumption error.

For the COI specifically there are three conventions, not two:

| Convention | Year-1 COI in one worked example |
|---|---:|
| Explicit: `rate × (DB − s)`, charged where it lands | 105.0200 |
| Simultaneous at the deduction point | 105.0421 |
| End of period, discounted back | 101.9687 |

gaspatchio exposes the first and third by name. If a workbook divides by something that
looks like `(1 + i)` inside its net-amount-at-risk formula, it is using the third.

## Rounding

Two separate questions, and both matter for a tie-out:

**Where.** If `ROUND()` sits between an opening and a closing balance, it is inside the
recursion and must be reproduced there — `b["state"].round(2)` after the op it follows.
Rounding only the final output produces a monotonic drift that looks like a formula
error but is not.

**Which way.** Excel rounds **half away from zero**; polars rounds **half to even**. They
differ only on exact ties, so the bug is invisible until it isn't. The rollforward
`Round` op uses Excel's rule.

## Reference values — and how to get the ones the workbook doesn't ship

A workbook's cached outputs are your gold standard. Extract them to parquet before changing
anything, and reconcile column by column.

**One class of cached value is irreproducible by design: Excel's cosmetic zero.** When
the final add/subtract of two references lands below ~2⁻⁴⁸ *relative to the operands*,
Excel caches an exact `0` where IEEE arithmetic (and any honest engine) says something
like `-1.09e-11`. A strict tie-out should expect this class and bound it —
`|cached − ieee| / max(1, |a|, |b|) ≲ 2⁻⁴⁸` — naming it as an Excel display artifact
rather than loosening the global tolerance to hide it. The divisor floor (`max(1, …)`)
matters: the cosmetic zero itself must not divide by zero in your residual report.

But cached values only cover the one set of inputs the workbook happens to be saved with, and
that is usually not enough. Branches that never fire on the shipped inputs — a corridor test, a
guarantee, a mass-lapse trigger — have no reference at all, which is exactly where conversion
bugs hide.

**You can recalculate the workbook.** `formulas` and `pycel` evaluate a workbook's real formula
text, so you can change an input and get a genuine reference back:

```bash
uv run --no-project --with formulas --with openpyxl --with polars python3 recalc.py
```

```python
import formulas
sol = formulas.ExcelModel().loads("model.xlsx").finish().calculate()
sol["'[model.xlsx]SHEET NAME'!R4"].value[0, 0]   # sheet name uppercased, book name not
```

**`openpyxl` and `xlsxwriter` do not evaluate anything.** They read and write formula *strings*.
A workbook edited with them comes back holding `=MAX(M4,N4)` and no value — so use them to
*write* the variant and a formula engine to *evaluate* it, never openpyxl alone. This is the
trap: the edited file looks right and is empty of answers.

Three rules make the result trustworthy:

1. **Validate the engine before you believe it.** Recalculate the *unmodified* workbook and diff
   every column against its own cached values. If that isn't 0.0, stop — nothing downstream
   counts. (`formulas` reproduced one UL workbook at 0.000e+00 on all 14 columns × 111 rows.)
2. **Change one cell where you can.** Schedules are often one hardcoded cell with `=E3`, `=E4`
   cascading below it, so a whole premium schedule moves by editing a single number.
3. **Build the counterfactual the same way.** To show what your model does *wrong*, edit the
   workbook's formula to match your model's behaviour and recalculate. Both halves of the
   comparison then come from the workbook rather than from your own reimplementation of it.

A reimplementation in Python is a reasonable *exploratory* tool — it is fast enough to sweep a
parameter until a branch fires. Just don't quote its numbers as the reference when the engine
can give you the workbook's own.

Two verified caveats on `formulas` itself:

- **It cannot load a workbook with `%` in a sheet name** — printf interpolation of the
  sheet id raises `ValueError: unsupported format character`. Percentage-named
  regulatory tabs are common (a VM-20 sheet named after the 135% constraint hits it).
  The workaround that preserves gold-standard integrity: copy the workbook to scratch,
  rename the sheet there, rewrite its by-name references, and never open the original
  for writing.
- **It exercises unfired branches; it does not adjudicate Excel's undefined
  behaviour.** On a degenerate approximate-match VLOOKUP over unsorted data it returns
  the sane answer where Excel's cache holds the insane one — so it validates normal
  formulas and cannot arbitrate quirks. When you hit one, take the affected cells as
  *extracted assumptions*: assert their cached values against the extract, reproduce
  them as data, and state the consequence in the report.

## Before writing any model code

1. **Extract**, do not read by hand. `marinade extract`.
2. **Scan for row offsets, then partition into SCCs.** The offset scan catches every
   recurrence (forward *and* backward) — then classify each hit by whose row it reads:
   own column = recurrence, a state column = inside the rollforward, an independent
   column = `previous_period()`, still closed-form. The SCCs find which recurrences
   must share a rollforward state. Together — not the SCC test alone — they are your
   recurrence/closed-form split.
3. **Confirm consumption with the edge table** for any structure you are about to
   model — a computed cell is not necessarily a used cell.
4. **List the defined names.** Single cells are model-point columns; ranges are `Table`s.
5. **Find every `ROUND`**, and note which sit inside a cycle.
6. **Find every approximate-match `VLOOKUP`** and check whether the projection outruns
   its table's range.
7. **Identify the reference values.** A workbook's cached outputs are your gold standard —
   extract them to parquet before changing anything, and reconcile against them column by
   column, not just on the final number. For branches the shipped inputs never exercise,
   recalculate the workbook with a formula engine rather than reimplementing it.
8. **Check whether the workbook models one policy or many.** Most teaching and pricing
   workbooks model exactly one, driven by single-cell inputs. That is fine — but it means
   there is no policy space to test across, so guard the assumptions that only hold for
   that one life with assertions rather than comments.

Then hand off to `gaspatchio-model-building`, and to `gaspatchio-model-reconciliation`
if the workbook's cached values are the target.
