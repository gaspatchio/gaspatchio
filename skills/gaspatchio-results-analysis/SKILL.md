---
name: gaspatchio-results-analysis
description: Use when the user asks for a chart, a table, a summary or a comparison built from a gaspatchio run that has already happened - "chart the net cashflow", "what is the portfolio total", "show me policy 1's account value over time", "put the results in a report" - or when a calculation-graph artifact (graph.json) or a results Parquet is handed over and the ask is to read it.
allowed-tools: Bash(uv:*,gspio:*) Read Write Grep Glob
---

# Gaspatchio Results Analysis

I'm using the gaspatchio results analysis skill.

## When to use this skill

This skill is standalone. It needs no other skill to have been run first, and
it does not write or change model code. It reads what a run already produced.

Use it when the ask is about numbers a run has already computed:

- "Chart the book's net cashflow by period."
- "What is the present value across the portfolio?"
- "Show me policy 1's account value over the projection."
- "Which numbers moved between these two runs?" (`gspio diff`, Recipe 5 - never
  a hand-rolled diff of two Parquets)
- "Give me policy 1 in a spreadsheet I can check." (`gspio sheet`, Recipe 1)
- "Put the results into a short report I can send on."

Do **not** use it to produce numbers that do not exist yet. If the ask needs a
column the run never computed, the model has to change first - that is
`gaspatchio-model-building`, and this skill picks up again once the new run
has been made.

**The two inputs.** A run leaves two files, and this skill reads both:

| File | Written by | What it holds |
|---|---|---|
| `graph.json` | `uv run gspio calc-graph model.py points.parquet -o graph.json` | The whole model as written: every formula, every assumption table, and the values of the policies it **sampled** - by default one, `:1`, the first row of the book (`--policies id:<id>` names another) |
| `results.parquet` | the same command with `--results results.parquet` (also spelled `--output-file`) | **Every policy**, one row each |

If only one exists, say so and work from it. If neither exists, run the export
first - one command writes both.

---

## Where the numbers are

### The artifact carries one policy and every formula

`gspio calc-graph` writes a JSON document. These are the members to read, by
name. Nothing else is needed to draw a single-policy chart.

| Member | What it is |
|---|---|
| `model.results.path` | The results Parquet this run wrote, **relative to the model's root** |
| `model.results.fingerprint` | `sha256:<hex>` over that file's own bytes |
| `model.source_path`, `model.source_sha`, `model.git` | The model file, its content hash, the revision it sat at |
| `enrichment.policy_id` | Which policy the values belong to |
| `policies` | The axis the values are read along, one entry per policy the file carries, with the book's own folds ahead of them where the export asked for one; `enrichment` is its first entry with `why` added. **These recipes read a file carrying one.** With more than one, every `value_sample` and `trace` is an array along this axis and `artifact_timeline.py` refuses rather than reading the first as a projection |
| `policies[].why` | How that policy came to be in the file — the row and the id both. `"row 0 of 1,000"` is a policy nobody chose |
| `enrichment.periods` | Which projection periods were read; `null` means every one |
| `enrichment.aggregation` | The fold this entry is an account of, named as the framework spells the aggregator — `sum`, `period_sum`, `mean` — and `null` where the values are one policy's. An entry stating one is the **book's own fold**, written by `--portfolio`: its `policy_id` is null, its values are the portfolio's, and a column no accumulator covered is null under it |
| `nodes[].value_sample` | A `list` node's whole timeline, or a `scalar` node's single value - each the full double the run held, so it matches the results file to the bit. Only a `trace` step's prose rounds (six significant figures, a reading aid) |
| `nodes[].facets.gaspatchio_column_transformation.reads[]` | What each node read, and over which periods: a shift's `offset` (`-1` is last period), an aggregation's window `periods: {from, to}` (each bound a distance from the period computed, or `"first"`/`"last"`), a `list.get`'s `position`. Read the window, never the formula text |
| `nodes[].formula` | The line as the model wrote it. An input column has none |
| `nodes[].shape` | `list` (one value per period) or `scalar` (one per policy) |
| `nodes[].settings` | The options an accumulation was run under, where it has any |
| `nodes[].tier`, `nodes[].source_location` | Which vocabulary tier, and `file.py:line` |
| `assumptions` | Every table the run used, inline, each with its own fingerprint |
| `graph_fingerprint` | One `sha256:` string standing for the formulas and the assumption tables' content - **not** the policy data |
| `formulas_fingerprint` | Moves only when a formula moves, not when a table or the book does |
| `book.digest` | The policy data's content |
| `producer.versions` | The library that produced the numbers - core and extension versions, the extension's digest, Polars, Python, the platform, and the installed packages the model imports; `{"omitted": "withheld"}` on a file exported with `--no-versions` |

**Resolving `model.results.path`.** Every path in the artifact is written
relative to the model's root: the directory the model file sits in, or the
root of the repository it sits in where `model.git` is present. The root is
not carried in the file - a reader holding the artifact holds the model, and
`model.git` says which of the two bases applied. Join the path onto that root;
never onto the directory you happen to be standing in.

### The results Parquet carries every policy

One row per policy. Two kinds of column:

- **List columns** - one value per projection period, in period order. On the
  level-4 tutorial model at 1,000 policies that is 70 of the 128 columns, 83
  values each.
- **Plain columns** - one value per policy: model-point fields, and the
  per-policy results the model computed (present values, totals).

**Timelines can be jagged.** `until="maximum_age"` runs each policy to its own horizon: `until_value` less its issue age, in whole years, so every life stops at attained age `until_value` whoever shares the run.
So two rows can carry lists of different lengths. Any fold
across policies has to build its period index from each row's own list length.
The bundled utility does; a hand-rolled `list.get(i)` does not.

### Read the two files before you read the numbers

```bash
uv run gspio validate graph.json          # schema, structure, and the file's own seal
uv run gspio describe --json results.parquet   # rows, columns, dtypes
```

`validate` answers "is this a whole, self-consistent artifact". `describe`
answers "what columns are actually in this Parquet, spelled how". Polars is
case-sensitive and a guessed column name is the most common way this work goes
wrong. Both commands take seconds; run them.

---

## Recipe 1 - the declared policy's timeline, from the artifact alone

The artifact already holds the sampled policy's whole projection. **For a
person, hand over the workbook**; for a chart or a computation, read the frame.

`gspio sheet` lays an audit file's policies out as an `.xlsx` workbook a
reviewer opens in Excel with no Python - a README naming the record by its
digests, one Timeline per policy (a row per period, a column per calculation
headed by its formula and tier), then Scalars, Nodes, Edges and Assumptions -
every number the run's own double and no cell a formula.

```bash
mkdir -p report                     # the workbook's directory has to exist first
uv run gspio sheet graph.json -o report/policy.xlsx --results results.parquet
uv run gspio calc-graph model.py points.parquet -o graph.json --results results.parquet \
    --policies id:POL-000343 --xlsx report/policy.xlsx          # export and lay out in one run
```

`--results` makes the README say whether the results file agrees with the
record. The workbook carries the policies the export sampled; asking for one it
does not carry (`--policy P9`) exits 3 and says to export it. From Python:
`af.graph.to_excel("report/policy.xlsx")`.

Laid side by side, the `list` nodes are a frame: one row per point of the time
axis, one column per node.

```bash
uv run python scripts/artifact_timeline.py graph.json
uv run python scripts/artifact_timeline.py graph.json --format csv --output policy1.csv
uv run python scripts/artifact_timeline.py graph.json --what nodes      # id, formula, shape, tier
```

Or import it:

```python
from artifact_timeline import read_artifact, timeline, nodes_table

document = read_artifact(Path("graph.json"))
frame = timeline(document)          # period + one column per list node
who = document["enrichment"]["policy_id"]
```

Columns are named by node identifier (`net_cf@1`), not by bare column name, so
a column the model wrote twice keeps its two versions apart. `period` is the
row index; `month@1` is the framework's own elapsed-month label where the run
stamped one.

**A blank last row is the final boundary, not a period.** On a projection the
time axis (`month@1`) holds `n_periods + 1` values - the start, then the end
of each period. A node holding one value per period instead, as a compiled
rollforward's balances do, is one value shorter, so its last row is blank; the
script names every such node and its length in a warning. The workbook lays
the record out the same way. Do not chart or total that row as a period.

**This is one policy.** Say which one on anything you produce. A single
policy's shape is not the book's shape, and a chart that does not say whose
line it is will be read as the book's.

**Lineage questions go to the record, not to a parse of the formulas.**
`uv run gspio graph trace graph.json pv_net_cf` lists everything behind a
column, each arrow with the periods it read (`(t−1)`, `(first…t−1)`,
`(t…last)`); `gspio graph affected graph.json --assumption mortality` lists
what a table moves. In Python, `from gaspatchio.graph import read_artifact`
returns a `GraphDocument` answering `trace`, `affected`, `precedents`,
`dependents` and `unused` - a different function from this skill's
`artifact_timeline.read_artifact`, which returns the parsed JSON.

---

## Recipe 2 - portfolio totals, from the results Parquet

The book is not in the artifact. It is in the Parquet, and folding it is one
pass in Polars.

```bash
uv run python scripts/portfolio_totals.py results.parquet
uv run python scripts/portfolio_totals.py results.parquet --aggregate mean
uv run python scripts/portfolio_totals.py results.parquet --columns net_cf claims \
    --format json --output totals.json
```

```python
from portfolio_totals import read_results, fold

folded = fold(read_results(Path("results.parquet")), aggregate="sum")
folded.per_period      # one row per period, one column per numeric list column
folded.scalars         # one row: each numeric per-policy column summed
folded.policy_count    # how many policies stand behind every figure
folded.skipped         # the columns no fold is defined over
```

The fold explodes each list column against a period index built from that
column's own length, groups on the period, and joins the results - so jagged
timelines are handled and a policy contributes to the periods it has. Measured
on the level-4 model at 1,000 policies, 128 columns: **0.161 s** for the sum,
0.074 s for the mean.

`--aggregate` governs the **per-period** fold. The per-policy columns are
summed either way: a per-policy result has no period to average over, and the
book total is the figure a reconciliation quotes.

### Which columns a total is meaningful for

The utility folds every numeric column because it cannot know what they mean.
**You** say which of them is worth quoting, and you say it from the column's
definition, not from its name.

| Column kind | Sum | Mean | Why |
|---|---|---|---|
| Cashflows - premiums, claims, expenses, `net_cf` | **Yes** | Per-policy average | Money is additive across a book |
| Present values, reserves, account values | **Yes** | Per-policy average | Same |
| Policy counts, deaths, lapses, survivors | **Yes** | Rarely useful | Counts are additive |
| Rates - mortality, lapse, discount, interest | **No** | Only exposure-weighted | An unweighted mean of rates is not the book's rate |
| Ages, durations, terms | **No** | Sometimes, as a profile | A summed age is nothing |
| Flags, identifiers, scenario labels | **No** | **No** | A summed flag is a count wearing the flag's name |

The utility names what it skipped (dates, strings, booleans) and what it
folded. Where you quote a rate or an age, take it from the artifact's declared
policy instead, and say that is what you did.

---

## Recipe 3 - a chart and a table

Altair, from recipe 1's frame or recipe 2's. It is already a dependency and it
is the library the other gaspatchio skills use.

```python
import altair as alt

chart = (
    alt.Chart(folded.per_period.select("period", "net_cf"))
    .mark_line()
    .encode(
        x=alt.X("period:Q", title="projection period (months from the valuation date)"),
        y=alt.Y("net_cf:Q", title="net cashflow, book total"),
    )
    .properties(title="Net cashflow by period", width=640, height=280)
)
chart.save("report/net_cf_by_period.html")   # interactive, opens anywhere
chart.save("report/net_cf_by_period.png")    # for embedding in a note
```

Altair takes a Polars frame directly - no conversion step.

| The ask | The chart |
|---|---|
| A cashflow or a reserve over time | Line, period on x |
| The same for one policy and the book | Two lines, or two panels, each labelled with whose it is |
| Composition of a total by period | Stacked area, and state the stacking order |
| Per-policy spread of one figure | Histogram, or a box plot by cohort |
| Two runs compared | Line per run, both digests in the caption |

Write a short Markdown note beside the files. It is what makes the chart
readable six months on:

```markdown
# Net cashflow by period

![](net_cf_by_period.png)

Book total, 1,000 policies, 83 monthly periods.

- Model: `model.py` at `sha256:a267a4eb...`
- Graph fingerprint: `sha256:5d28b0c1...`
- Results file: `level4-v11.parquet`, `sha256:c0edf3f2...`, digest checked
- Aggregation: sum across policies at each period
```

Charts and notes go in a directory of their own (`report/`). Do not write them
next to the artifact where they can be mistaken for part of it.

---

## Recipe 4 - cite the run, and check it first

Two digests identify what you read. **Both go on every chart, table and note
you produce**, and the results file's digest is checked *before* anything is
read out of it.

```bash
uv run python scripts/check_results_digest.py graph.json --root path/to/model/root
# exit 0  the file on disk is the one the artifact was written against
# exit 1  the digests differ
# exit 2  nothing to check - no results block, or the file is not there
```

```python
from check_results_digest import check, read_artifact

outcome = check(read_artifact(Path("graph.json")), root)
if outcome.status != 0:
    raise SystemExit(outcome.message)
```

**A mismatch is a stop, not a warning.** It means the artifact and the Parquet
came from different runs - a later run overwrote the output, or two quarters
ended up in one directory. Every number you would draw from that pair is a
number from one run wearing another run's identity. Say what you found, say
which two digests disagree, and ask for the matching pair. Do not chart it
with a caveat.

What to cite:

| On the output | From |
|---|---|
| The model and its revision | `model.source_path`, `model.source_sha`, `model.git` |
| The calculation's identity | `graph_fingerprint` (formulas and table content) and `book.digest` (the policy data) - one does not stand for the other |
| The library that produced it | `producer.versions` - core, extension, Polars, Python, platform |
| The results file | `model.results.path` and `model.results.fingerprint` |
| Which policy, or which fold | `enrichment.policy_id`, or "sum over N policies" |
| The digest check | that it was run, and that it passed |

Which identity answers which question - `formulas_fingerprint`,
`graph_fingerprint`, `book.digest`, `Table.fingerprint()`, `source_sha`,
`document_digest` - is the table in
[../gaspatchio-model-review/references/audit-record.md](../gaspatchio-model-review/references/audit-record.md).
To hold every file - results, policy data, model, assumption tables - against
the record in one pass, `uv run gspio verify graph.json --results results.parquet
--model model.py --model-points points.parquet --assumptions assumptions/`
(exit 0 only when every check agrees; 4 is "could not be checked", not a pass).

---

## Recipe 5 - two runs compared

Two runs are compared by the commands that know what a row and a line are,
not by joining two Parquets by hand.

```bash
# Two versions of the model: what changed, and which lines' numbers moved
uv run gspio diff before/graph.json after/graph.json
uv run gspio diff before/graph.json after/graph.json --results before/results.parquet after/results.parquet

# Two runs of one version (a re-run, another machine): do they agree?
uv run gspio compare graph.json run1.parquet run2.parquet

# Ids that repeat across cohorts or scenarios: name every column a row is known by
uv run gspio compare graph.json run1.parquet run2.parquet \
    --policy-id-column policy_id --policy-id-column cohort
```

`gspio diff` on two audit files says what changed - formulas, tables, policy
data - and, reading the two results files the audit files record, which
lines' numbers moved, in how many policies, from which period and by how
much; `gspio compare` answers a different question, whether two runs of *one*
artifact agree. `--json` writes the report for a table or a chart; in Python,
`gaspatchio.frame.graph.diff_with_results(before, after, before_results,
after_results)` returns it, each of `report.values.lines` carrying `node`,
`change` (`self` for a line whose formula changed, `inherited` for one that
moved because what it reads did), `policies_moved`, `max_relative` and
`first_period_moved`. Cite both runs' `graph_fingerprint` and results-file
fingerprints on anything drawn from the comparison. Results files from two
machines or builds differ in bytes (their footer records the versions), so
compare values with these commands, never file hashes.

---

## What this skill never does

- **Never edit the artifact**, or an exported viewer HTML file. It is the
  model's own account of itself; a document someone edited is a document
  nobody can check. Produce a new file beside it instead.
- **Never recompute a model number from a formula.** `nodes[].formula` is
  there to be read and quoted, not evaluated. If a figure is missing, the run
  produces it - not you.
- **Never read a Parquet the artifact does not name** without saying plainly
  that it is a different file and why you went to it.
- **Never hand over a chart without its digests.** An uncited chart is a
  picture of a number nobody can trace back.
- **Never guess a column name.** `gspio describe --json` lists them.
- **Never write a model file.** If the ask needs a new column, route to
  `gaspatchio-model-building`.

---

## Red Flags - you are about to publish something untraceable

| Thought | Reality |
|---------|---------|
| "The Parquet is right there, I'll just read it" | Then the chart cites nothing. Read the artifact first; it names the file and stamps it. |
| "The digests are a formality, the file is obviously the right one" | That is exactly the assumption the check exists to test. It takes under a second on a 17 MB file. |
| "I'll sum every column and let the user pick" | A summed rate and a summed age are numbers with no reading. Label what a total means, or leave it out. |
| "The artifact has values, so I can chart the book from it" | It carries the policies it **sampled** - by default one. The book is in the Parquet. |
| "I'll join the two Parquets and subtract" | `gspio diff` knows which lines a change edited and which inherited the move, and `gspio compare` pairs rows on the identity the files record. |
| "The last row is all blank, so the projection ran one period short" | It is the time axis's final boundary beside a per-period node. The script's warning names the nodes. |
| "I'll edit the exported HTML to add my chart" | Then it is no longer the model's account. Build the chart beside it. |
| "The formula is right there, I'll evaluate it for the period they asked about" | Recomputing a number outside the run is how two answers start to exist. Re-export instead. |
| "One policy's line looks representative" | Say whose line it is. A reader will assume it is the book's unless told. |
| "The column is called `rate`, so it is a rate" | Read its formula in the artifact. Names drift; formulas do not. |

---

## Integration

**Called by:**
- `gaspatchio-model-building` - when a run is finished and the ask turns to
  reading its output
- `gaspatchio-model-scenarios` - for charts and tables drawn from a scenario
  run's results file, alongside that skill's own report requirements

**Routes to when needed:**
- The viewer (`gspio calc-graph ... --html`) - when the question is lineage
  rather than magnitude: what feeds this column, what the substitution was,
  where the formula is written. The viewer shows the artifact; this skill
  works the numbers.
- `gaspatchio-model-scenarios` - when the ask turns from "what did this run
  produce" to "what if the assumption were different". A what-if needs a new
  run, not a new reading.
- `gaspatchio-model-reconciliation` - when a figure disagrees with a reference
  and the work becomes finding out why.
- `gaspatchio-model-building` - when the ask needs a column the run never
  computed.

**This skill does not require any other skill first**, and nothing is required
after it.

---

## Completion checklist

The analysis is finished when all of these are true:

- [ ] `uv run gspio validate graph.json` passed on the artifact that was read
- [ ] `check_results_digest.py` exited 0 before any number was read out of the
      results file - or the artifact names no results file and the output says so
- [ ] Every chart, table and note states the `graph_fingerprint` and the
      results file's `fingerprint`
- [ ] Every figure drawn from one policy says which policy; every figure
      drawn from the book says the fold and the policy count
- [ ] No column was totalled whose total has no reading (rates, ages, flags),
      or the output says what the total means
- [ ] The artifact and any exported HTML are byte-identical to what the run
      wrote - nothing was edited
- [ ] Outputs were written to their own directory, not beside the artifact
- [ ] Any comparison of two runs came from `gspio diff` or `gspio compare`, and
      cites both runs' digests
- [ ] No model number was recomputed outside the run

If a digest check failed, the analysis is **not** finished and no chart from
that pair should be handed over.
