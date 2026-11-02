# The audit record: what to ask it before you sign

A reviewer's evidence is the audit file the run wrote, the files it names, and
the answers the record gives without the model being run again. This
reference is the reviewer's half of the record: which identity answers which
question, how to hold the files you were handed against the record, how to see
what changed between two versions, and how to put one policy in front of
someone who does not read Python. Use it during Steps 3b–3d and Change Impact.

---

## Export once, and know what it sampled

```bash
uv run gspio calc-graph model.py data.parquet -o audit.json --results results.parquet
```

`calc-graph` runs the whole book but writes values for the policies it
**samples**, and the default is one: `:1`, the first row of the book. The
export says so (`One policy: row 0 of 3 in mp.parquet, selected by ':1'.`),
and the record's `policies[].why` repeats it. Name the policies a review
needs: `--policies id:POL-000343` (one id), `--policies all`, `':30'` (row
positions), `'spread:5@issue_age'` (five, evenly across the book). `--results`
also writes the finished frame to Parquet and names it in the record by path
and content hash. Every number in the record is the full double the run held;
a `trace` step's prose prints six significant figures as a reading aid.

---

## Which identity answers which question

`formulas_fingerprint` moves only when a formula moves; `graph_fingerprint`
moves when a formula, an assumption table's content or the values of a hole the
frame arrived holding move; `book.digest` moves when the policy data moves; `Table.fingerprint()` is one table's content;
and `document_digest` is the seal over one exported file, new on every export.
**Which policies the model values is part of the logic**: an `af.filter(...)`,
semi join or anti join is a step in the audit file's `selection` list, and
changing its condition moves both fingerprints (spec §7.6).

| Identity | Where | Answers | Moves when |
|---|---|---|---|
| `formulas_fingerprint` | audit file | "Is the logic the same?" | a formula or a selection step changes — a filter's condition, a semi/anti join's key or type (not table, schedule or book data; a rollforward's schedule and a semi join's right-side table are data) |
| `graph_fingerprint` = `af.graph.fingerprint()` | audit file, frame | "Can this number still be what it was?" — the calculation, which policies it values, and its assumption content | a formula, a selection step, a table's content or a schedule's rule changes, or the values of a hole the frame arrived holding (its `content` stamp); **not** the book, except through such a hole |
| `book.digest` | audit file | "Same policy data?" | any model-point value a line or a selection step reads — the in-force flag included, even where the model drops it |
| `Table.fingerprint()` = `assumptions[].fingerprint` | table, audit file | "Same basis?" | a table value; not its name, column or row order, file format |
| `Table.source_sha()` | table | "Same configured table, name included?" | values, name or keys |
| `model.source_sha` | audit file | "Same model file?" | any byte of the model file |
| `document_digest` | audit file | "Is this file untouched since it was sealed?" | every export (it covers `created_at`) |

Measured on one model and book, one change at a time:

```text
change                                  graph_fingerprint  formulas_fingerprint  document_digest  book.digest  model.source_sha  assumptions[mortality].fingerprint
re-export, nothing changed              same               same                  MOVES            same         same              same
table data changed (qx x1.1)            MOVES              same                  MOVES            same         same              MOVES
one formula changed (claims x1.01)      MOVES              MOVES                 MOVES            same         MOVES             same
model points changed (one sum assured)  same               same                  MOVES            MOVES        same              same
in-force filter changed (age < 50 → 55) MOVES              MOVES                 MOVES            same         MOVES             same
side file the setup joined, edited       MOVES              same                  MOVES            same         same              same
```

Two readings a reviewer gets wrong:

- **`graph_fingerprint` does not cover the book.** Two runs with equal
  `graph_fingerprint` over different policy data are the same calculation,
  not the same numbers. Pair it with `book.digest`.
- **A hole moves `graph_fingerprint` with its values.** A column the frame
  arrived holding that nothing accounts for — the 0.9 setup's join, collected
  and rebuilt with `ActuarialFrame(mp)` — carries the `content` stamp of what
  it held, so an edit to the joined file moves `graph_fingerprint` (and every
  run record's) while `formulas_fingerprint` and `book.digest` stay; `gspio
  diff` names it as a `hole` data entry with the two stamps and, with the
  results files read, gives each line under it `cause: "hole"` naming it. A hole
  the setup derived from book columns, such as `gender + rate_class` built in
  Polars, now moves `graph_fingerprint` on a book edit too: an unexplained
  number changed. Write it through the frame and it reads as the book again.
- **A selection is not a mask.** `af.filter(af.status == "IF")` values three
  policies and records a step; `when(af.status == "IF").then(...)` values all
  four and records a node. Both are recorded, as different models. Filtering
  the collected model points and building a new frame from them records no
  step: the new frame *is* the book, so `book.digest` moves instead. A replay
  of the executable artifact (`gspio run-artifact`, any engine) applies the
  recorded steps to the book before it projects.
- **A scenario's fingerprint moves with a column shock, not with its
  factor.** A shock on a model-point column (`column=`) is recorded as an
  assignment at the plan's line, whatever its factor, so an identity column
  shock (`× 1.0`, `+ 0.0`) gives that scenario a fingerprint other than
  BASE's while every number equals BASE's. A table shock reaches the
  fingerprint through the table's content, so an identity table shock leaves
  BASE's (spec §13.2). A moved scenario fingerprint says the calculation was
  composed differently; compare the folds before reading it as a moved number.
- **`Table.source_sha()` is not the file's hash.** It is the table's recipe —
  name, dimensions, value column and content — so renaming a table moves it
  and re-saving the same rates as CSV does not. The content alone is
  `Table.fingerprint()`, which is what the audit file records per table.

`formulas_fingerprint` is read off an exported audit file; there is no
`af.graph.formulas_fingerprint()` in 1.0. Export, then read it.

---

## Hold the files against the record: `gspio verify`

`gspio verify` holds the files you have against the audit file that records
them — results, policy data, the model file and every local module it
imports, each assumption table read back from its file, and the right side of
each join the model made — and exits 0 only when every check asked for agrees;
library versions and git are evidence and move no exit status. Hand `Table`
the file path (not a frame you built) so `--assumptions` can decide it.

```bash
uv run gspio verify audit.json --model model.py --model-points data.parquet \
    --results results.parquet --assumptions assumptions/
```

| Exit | Meaning |
|---|---|
| 0 | every check asked for agrees |
| 1 | a deciding check disagrees |
| 4 | a deciding check is indeterminate — "could not be checked" — and nothing disagrees |
| 2 | a file could not be read |

What each line says, as it prints — here for a model that reads a mortality
table by path, joins `assumptions/products.parquet`, and loads `helpers.py`
with `importlib`, verified with the command above:

```text
? Nothing differs from audit.json, and modules could not be checked

  ✓ seal  agrees  (document_digest)
  ✓ results  agrees  (model.results.fingerprint)
  ✓ results_manifest  agrees  (graph_fingerprint, book.digest)
  ✓ book  agrees  (book.digest)
  - model_points  not asked: the book check decides  (model.model_points.fingerprint)
  ✓ source_sha  agrees  (model.source_sha)
  ? modules  could not be checked  (model.modules)
  - scenarios  not asked: No scenario plan's run script was given.  (model.scenarios)
  ✓ graph  agrees  (graph_fingerprint)
  ✓ holes  agrees  (holes)
  ✓ git  agrees  (model.git.commit)
  ✓ versions  agrees  (producer.versions)
  ✓ assumptions  agrees  (assumptions[name=mortality].fingerprint)
  ✓ assumptions  agrees  (assumptions[name=join:1aa0680a].fingerprint)
```

Exit 4: nothing differs, and the helper loaded by path is not on the record
(below). Each line is followed by its detail, naming the file read and the
digest held against. A table the model built from a frame, with no file given
for it, prints `- assumptions  not asked: …`.

**The graph line decides the model, not only its files.** A stamp says whether
a file moved, not whether the numbers did: a value read with `.item()` from a
parameter file, a JSON config, an environment variable, a module imported
through `sys.path` from outside the model's folder, a plan's shock factor —
each moves a formula while `source_sha` and `modules` still agree. With
`--model` and `--model-points`, verify imports the model and runs it over the
book in a fresh interpreter (no values computed), and holds the rebuilt
`graph_fingerprint` against the record's. A difference is `✗ graph differs`,
naming the line the moved input entered at (`expense_maint@1 (model.py:409):
…`). It runs the model's own code, so it holds **in this environment**: the
files the model reads must be where it reads them. A scenario plan's record
needs the run script too, `--scenarios run_scenarios.py`; a line written with
`map_batches` (a Python function no fingerprint reads inside) holds it open.

**Assumption tables.** `--assumptions` takes a file, a directory, or
`NAME=FILE`, and repeats. A table is found by the file the record says it was
read from, else as `NAME.parquet` / `NAME.csv`, else as named. Once
`--assumptions` is given, **every** recorded table has to be found: naming only
`--assumptions expense=FILE` leaves `mortality` "not found", which is
indeterminate, exit 4. Give the directory, or name each table.

**A table the model built from a frame in its own code** has three outcomes,
never "differs":

| Given | Outcome |
|---|---|
| no file named for it | `not asked` (exit 0 if the rest agrees) |
| a file named for it holding the same values | `agrees` |
| a file named for it holding other values | `could not be checked`, exit 4: nothing records that the frame was that file as it stands |

So a model that hands `Table` a path (`source="assumptions/mortality.parquet"`)
can have its basis decided, and one that builds the frame first cannot. That
is a review finding (Important for a production model): ask for the path.

**Joins.** Each `af.join(...)` the model made has its own `assumptions` line,
under the record's name for the join (`join:<first eight digits>`). Its right
side is read from every Parquet or CSV file given, or from the file named as
`join:1aa0680a=FILE`, and the file whose content is the frame the model joined
agrees:

```text
  ✓ assumptions  agrees  (assumptions[name=join:1aa0680a].fingerprint)
    Join join:1aa0680a, the right side of a join the model made (holding
    prem_rate, product): products.parquet, found by its content among the files
    given, reads as sha256:1aa0680a…, the fingerprint the audit file records.
```

The record names the frame's content and not a file, so a file holding other
values is never "differs": it is `? assumptions  could not be checked`, exit 4,
saying "the file it was read from has changed since, or the model filtered or
derived the frame in code. Name the file as join:1aa0680a=FILE to hold it
against the join." Ask which it was.

**Local modules.** The record's `model.modules` lists each local module the
model imports, with its sha256. `--model` checks each one beside the model
given; an edited helper is `✗ modules differs`, naming the file read and, where
spelled differently, the path recorded:
`c14_edited/helpers.py (recorded as …/c14/helpers.py) is sha256:f5636bbc…, and the audit file records sha256:61435d2b…: it is not the module the model imported when it ran.`
Between two audit files, `gspio diff` names each helper whose sha256 moved in
`source.modules` — stated, never counted as drift, so a comment in a helper
shows without an alarm and an edited constant names its file beside the
calculations it moved.

`model.modules` is read off the import statements, so a helper loaded by path
(`spec_from_file_location`, `exec_module`, `import_module`, `__import__`,
`run_path`, `run_module`, `SourceFileLoader`, `exec`) is not on the record.
`verify` names each such call and holds the line open rather than agreeing with
nothing checked — exit 4:

```text
  ? modules  could not be checked  (model.modules)
    model.py loads code its import statements do not name -- model.py:6
    spec_from_file_location, model.py:7 exec_module -- and model.modules lists
    only what the import statements reach, so a helper loaded that way is not on
    the record and an edit to it would go unseen here. It could not be checked.
```

In a review that is a finding: import the helper by name, so the record lists
it and an edit to it fails `verify`.

**Holes.** Wherever `--model`, `--model-points` or `--assumptions` is given,
`verify` reads the record's `holes` section. A column listed there reached the
record by name, and by the stamp of the values it arrived holding, never by
what made them — the 0.9 setup step that collects, joins a file in Polars and
builds `ActuarialFrame(mp)` is the common case — so an edit to the joined file
moves the numbers and `graph_fingerprint` while the model file, the book and
every assumption line still agree, and the stamp cannot say whether the new
values are right. The line names each hole, its reason and the columns resting
on it, and holds the question open — exit 4:

```text
  ? holes  could not be checked  (holes)
    The audit file lists one column the model cannot account for: load
    (unrecorded; prem and pv_prem rest on it). ... It could not be checked.
```

Close it as `af.graph.holes()` says: `af.join(...)` for the file, or
`ActuarialFrame(mp, continue_from=af)`. A results file checked alone is not
asked about the holes: it is still the file the run wrote. A model that reads
no table passes `--assumptions <dir>` — nothing recorded is nothing to check.

**Versions and git are evidence.** Every audit file states the library that
produced its numbers — core and extension versions, the extension's digest,
Polars, Python, the platform, and the installed packages the model imports —
and the git commit and whether the tree was dirty; `--no-versions` withholds
the versions for a file committed as a golden, and a version difference never
fails `verify`. `model.git` is `null` outside a git working tree, and
`{"omitted": "unavailable", "detail": "<git's sentence>"}` where git could not
answer — `verify` then prints `? git could not be checked`, naming git's
sentence, and holds nothing open. A dirty tree moves no exit status (a results
file written into the repository is enough to make one); `source_sha` pins the
model file.

---

## What changed between two versions: `gspio diff`

`gspio diff` on two audit files says what changed — formulas, tables, policy
data — and, reading the two results files the audit files record, which
lines' numbers moved, in how many policies, from which period and by how
much; `gspio compare` answers a different question, whether two runs of *one*
artifact agree.

```bash
uv run gspio diff before.audit.json after.audit.json
uv run gspio diff git:v2026.Q2:model.audit.json model.audit.json       # the committed one, no checkout
uv run gspio diff before.audit.json after.audit.json --results before.parquet after.parquet
```

```text
! something moved between base.audit.json and c05_after.audit.json
  formulas changed (formulas_fingerprint differs)

Calculations: 3 changes
  changed  claims@1  (self)
  changed  net_cf@1  (inherited)
  changed  pv_net_cf@1  (inherited)
Values: 3 policies compared, rows matched by identity on policy_id
  …
  Moved, largest relative move first:
    claims@1  (self)
      3 of 3 policies · from period 0 · max |change| 11.7 · largest 1% at P2, period 5 …
```

Exit 0 when nothing moved, 1 when something did. `(self)` is a line whose own
formula changed; `(inherited)` moved only because something it reads did. A
table-only change reads `formulas unchanged (formulas_fingerprint equal); data
changed: table mortality, …`, and every moved line is `(inherited)`.
`--no-results` compares the audit files alone; `--policy-id-column` (repeat it
for a second column, such as a scenario's) pairs rows on the columns named,
over whatever identity the results files record; `--floor PCT` trims small moves from the printed list (the
`--json` report keeps every line). A line's `within_band` is True where every
move sits inside the reordering band of the spec's §11.1.12 (it cannot be told
from a difference in the order of arithmetic), False on a line beyond it.

**For a change review this is the evidence.** An edit that should move one
line and moves five, or a "refactor" with `formulas_fingerprint` unchanged that
moves numbers, is the finding.

`gspio compare audit.json before.parquet after.parquet` is for two runs of the
same artifact (a re-run, another machine, another engine): it says whether
they agree. Given two versions' results it refuses and points at `diff`.

---

## Reading the periods each arrow reads

Every read in the audit file states which periods it takes: a shifted read its
`offset` (`-1` is last period), an aggregation its window `periods: {from, to}`
— each bound a distance from the period being computed or `"first"`/`"last"` —
and a literal `list.get` its `position`; read the window, never the formula
text.

| Term | Meaning |
|---|---|
| `DIRECT` | the value flows into the answer |
| `INDIRECT` | a key, a condition or a selection (no window is ever written on it) |
| `TRANSFORMATION` | one period read (a shift carries `offset`, a `list.get` carries `position`) |
| `AGGREGATION` | a run of periods, its `periods` window |

```text
surv_bop@1     <- q@1        DIRECT/AGGREGATION {"periods": {"from": "first", "to": -1}}
surv_eop@1     <- q@1        DIRECT/AGGREGATION {"periods": {"from": "first", "to": 0}}
q_prev@1       <- q@1        DIRECT/TRANSFORMATION {"offset": -1}
q_first@1      <- q@1        DIRECT/TRANSFORMATION {"position": 0}
reserve@1      <- cf@1       DIRECT/AGGREGATION {"periods": {"from": 0, "to": "last"}}
total_cf@1     <- cf@1       DIRECT/AGGREGATION {"periods": {"from": "first", "to": "last"}}
```

The windows sit on each node's
`facets.gaspatchio_column_transformation.reads[].transformations[]`, not on
the top-level `edges[]`. `gspio graph trace` prints them as `(t−1)`,
`(first…t−1)`, `(t…last)`; `gspio graph … --json` carries them whole; the
one-policy workbook's Edges sheet lists them. A survival curve that reads
`{first, 0}` where the specification is beginning-of-period (`{first, -1}`) is
a timing finding you can make without running anything.

---

## One policy, laid out for a reviewer with no Python

`gspio sheet` lays an audit file's policies out as an `.xlsx` workbook a
reviewer opens in Excel with no Python — a README naming the record by its
digests, one Timeline per policy (a row per period, a column per calculation
headed by its formula and tier), then Scalars, Nodes, Edges and Assumptions —
every number the run's own double and no cell a formula.

```bash
uv run gspio sheet audit.json -o policy.xlsx --results results.parquet
uv run gspio calc-graph model.py data.parquet -o audit.json --xlsx policy.xlsx --policies id:POL-000343
```

The workbook carries the policies the export sampled — `calc-graph`'s default
is one (`:1`, the first row) — so export the policy you mean first.
`--results` makes the README state whether the results file agrees with the
record. `--policy P9` naming a policy the record does not carry exits 3 and
says to export again with `--policies id:P9`. From Python:
`af.graph.to_excel("policy.xlsx")`.

---

## The doors out, in Python

**The doors out.** Export the finished frame, read the artifact back, compare two of them:

```python
import json
from gaspatchio.frame.graph import GraphExporter, validate_artifact, diff_artifacts

artifact = GraphExporter(af).export()             # a JSON string — write it out yourself
report = validate_artifact(artifact, deep=True)   # report.ok, report.findings
changes = diff_artifacts(json.loads(before), json.loads(after))  # two artifacts, as dicts
```

`export()` takes `profile="executable"` to carry each node's operation tree as well as its
as-written formula; the default `"audit"` profile is the one a reviewer reads.
`diff_artifacts` separates the model moving (`changes.calculations`) from the data moving
(`changes.data`); `changes.drift` is False for two exports of an unchanged model, because
the comparison is over identities, never over the serialized bytes.

The rest of this reference, from Python — the same answers as the commands
above, from one implementation:

```python
from gaspatchio.frame.graph import diff_with_results, verify_artifact
from gaspatchio.graph import read_artifact

moved = diff_with_results(json.loads(before), json.loads(after), "before.parquet", "after.parquet")
checked = verify_artifact(
    "audit.json", model="model.py", model_points="data.parquet", assumptions=["assumptions/"]
)
doc = read_artifact("audit.json")        # GraphDocument: trace, affected, unused, tiers, ...
af.graph.to_excel("policy.xlsx")         # gspio sheet, from the frame
```

`export(versions="withheld")` is `--no-versions`. Each of `moved.values.lines`
carries `node`, `change` (`self`/`inherited`), `policies_moved`,
`max_relative`, `first_period_moved` and `within_band`; `checked.checks` holds
one line per check, as `gspio verify` prints them.

---

## `gspio graph unused --keep-from`

`--keep a,b` names the model's results on the command line. For CI,
`--keep-from results.toml` reads a TOML file whose top level holds
`keep = ["pv_net_cf", "reserve"]`; the file's shape is provisional in 1.0, and
a file without a top-level `keep` array is refused (exit 2) rather than read
as keeping nothing.

---

## What the record does not do in 1.0

Say these in a review where they bear on a conclusion, rather than letting a
reader assume the record covers them.

- **A band written in raw Polars** (`pl.col(…).is_in([…])`, `.cut([…])`) is
  recorded by Polars' display text, so a change to its values can leave the
  fingerprint unmoved. Bands written with the declared operations on the
  column (`af.x.is_in([…])`, `cut`, `replace`) record their values;
  `af.graph.tiers()` names any raw band (`engine_native`). Treat a raw band
  in a model under change control as Important.
- **`calc-graph` cannot also write every node's values from the same run.**
  For every node's values run `gspio run-model … --every-node --results FILE`
  as a second run.
- **Results files from two machines or two builds differ in bytes** (their
  footer records the platform and versions), so compare values, not file
  hashes: `gspio compare` / `gspio diff --results`. Runs on one machine and
  build write byte-identical files.
- `producer.versions.imports` names installed distributions only: a module
  found only on `PYTHONPATH` is not in it (a local module the model imports is
  in `model.modules`).
- A table whose recipe reshaped what it read, or that was built from a frame
  in code and is matched to a file of other values, verifies indeterminate
  (exit 4).
- On JAX, CPU flushes subnormals, and FMA contraction keeps some lines a few
  ulp from Polars: compare engines by value within a stated tolerance. Below
  the least normal double (about 2.2e-308) a comparison, `sign` or `cbrt` can
  differ outright -- `x == 5e-324` is 1 where `x` is 0.0 -- so no tolerance
  covers values there.
- A rollforward input refusal is reported without naming the failing column
  or policy when the frame goes on to `filter`, or to read a second
  rollforward, after the line that read the failing one. The refusal's own
  lines still name the input column and both lengths.
