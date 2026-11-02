# Changelog

## [1.0.0rc1] — 2026-11-02 — A model shows its work (release candidate)

gaspatchio 1.0 is the release in which a model shows its work. A model can be
exported as a calculation-graph artifact -- every column's formula, what it
read, the assumption tables and the book behind it, and a fingerprint of each
-- which a reviewer can validate, compare with last quarter's, and open in a
viewer. The same artifact runs on a second engine, JAX, on a laptop or a GPU.
And it is 1.0: what is stable is now stated, and every change that breaks
code written for 0.9.0 is listed below.

**New in 1.0, and how to install it**

- **Graph artifacts and the diff**, in the core: `pip install gaspatchio`.
  `gspio calc-graph model.py points.parquet --artifact model.json` exports a
  model; `gspio validate model.json` reads it back against its schema and its
  own structure; `gspio diff before.json after.json` says what changed
  between two versions of the model -- formulas, tables, policy data -- and,
  reading the results files the two record (or `--results BEFORE AFTER`),
  which lines' numbers moved, in how many policies, from which period and by
  how much. `gaspatchio.frame.graph.diff_artifacts(before, after)` and
  `diff_with_results` answer the same in Python. `gspio compare` answers a
  different question: whether two runs of one artifact agree. `af.graph`
  asks a model in memory how each of its columns was made.
- **The record checks itself.** `gspio verify model.audit.json --results
  results.parquet --model-points points.parquet --model model.py
  --assumptions assumptions/` answers "are these the files this audit file
  records?" one check at a time -- results, policy data, the model file and
  every local module it imports, and each assumption table read back from
  its file -- and exits 0, 1, 4 or 2 for a pipeline to branch on;
  `verify_artifact` answers the same in Python. Every audit file states the
  library that produced its numbers and the git commit it was exported from;
  both are evidence and move no exit status, and `--no-versions` withholds
  the versions for a file committed as a golden. `gspio run-model --results`
  and `gspio calc-graph --results` write the model's fingerprint, the book's
  digest and the library versions into the results file itself. An export
  from Python names its model file, commit and data with
  `GraphExportConfig(model=ModelIdentity.of("model.py",
  model_points="points.parquet"))`, as `calc-graph` does. `af.graph.tiers()`
  says which calculations are written in the format's own vocabulary and
  which reach into one engine's.
- **One figure for each question.** `formulas_fingerprint` moves only when a
  formula moves; `graph_fingerprint` moves when a formula or an assumption
  table's content moves; `book.digest` moves when the policy data moves;
  `Table.fingerprint()` is one table's content, whatever its column order,
  row order, file format or name; and `document_digest` is the seal over one
  exported file, new on every export.
- **Ask the audit file, or open it in Excel.** `gspio graph trace
  model.audit.json reserve` -- and `precedents`, `dependents`, `affected`,
  `unused`, `holes` and `tiers` -- answers from the file alone what
  `af.graph` answers on a frame; `gaspatchio.graph.read_artifact` does the
  same in Python. Every read in the file states the periods it takes: a
  shift its offset, an aggregation its window `periods: {from, to}`, a
  literal `list.get` its position. `gspio sheet model.audit.json`, or
  `calc-graph --xlsx`, lays the record's policies out as an `.xlsx` workbook
  a reviewer opens without Python, every number the run's own double and no
  cell a formula.
- **A scenario plan runs the model you reconciled, unchanged.**
  `plan.run(af, model.main)`: each shock names exactly one target -- an
  assumption table by the name its `Table` was built with (`table=`), or a
  model-point column such as a valuation rate (`column=`) -- and the plan
  answers the model's own reads of that target per scenario, so
  `result.fingerprint("BASE")` is the reconciled model's own fingerprint.
  Every shock kind writes itself to YAML and reads back as the same plan.
- **Workbook shapes that had no portable line have one.** `af.z.norm_cdf()`,
  or `af.z.excel.norm_s_dist()`, is the standard normal distribution
  function to 1e-12 relative. `af.cf.projection.accumulate(initial=0.0,
  multiplier=af.v, addend=af.cf, reverse=True)` is a workbook rollback,
  `V[t] = v[t] * V[t+1] + cf[t]`, and `list.reverse()` is declared.
  `fill_nan(0.0)` cleans a table read in one line that keeps the table's
  identity. And `projection.set(n_periods=T, step_years=h)`, or
  `steps_per_year=n`, lays a fixed-step axis with no calendar under it -- a
  teaching sheet, a Thiele or Kolmogorov solution -- whose `t_years()` is
  `k * h` exactly.
- **The JAX engine**: `pip install "gaspatchio[jax]"`. It runs a model's
  executable artifact: export with `--profile executable`, then
  `gspio run-artifact model.json points.parquet --engine jax --results
  results.parquet`, or in Python `af.collect(engine="jax")` and
  `run_aggregated(..., engine="jax")`. For a GPU, add jax's CUDA wheels,
  `pip install "jax[cuda12]"`.
- **The viewer**: `pip install "gaspatchio[viewer]"`. `gspio calc-graph ...
  --html review.html` writes one self-contained page that a reviewer opens by
  double-clicking, and `gspio diff before.json after.json --html
  changes.html` writes the comparison as one.
- **The extras pin exactly.** `gaspatchio[jax]` installs `gaspatchio-jax`
  0.1.0 and `gaspatchio[viewer]` installs `gaspatchio-viewer` 0.1.0, and
  `gaspatchio-jax` requires exactly `gaspatchio==1.0.0`, so an engine and a
  core arrive as the pair they were qualified as. Both distributions are new
  on PyPI with this release. Without them the core installs no JavaScript and
  no jax.

**Breaking changes.** Each is set out in full under *Breaking* and *Removed*
below. In brief:

- The `gaspatchio_core` import name is removed, as its deprecation warning
  has said since 0.9.0: `import gaspatchio`.
- Also removed: `RollforwardCollector` (call the compiled rollforward's own
  `expr_for` and `increment_for`), `gaspatchio.functions.vector` and
  `.utils`, `gaspatchio.polars_backend`,
  `gaspatchio.accessors.excel_functions`, `gaspatchio.column.dispatch` and
  `gaspatchio.column.namespaces`, `gaspatchio.registry` (use
  `gaspatchio.assumptions.Table`), `gaspatchio.errors.metadata`, and
  `TracedOperation`, `capture_source_context`, `OperationMetadata` and
  `ErrorBoundaryFinder` from `gaspatchio.errors`.
- Internals that were importable are gone or have changed shape, each named
  under *Removed*: three `SuggestionType` members and other members of the
  `gaspatchio.errors` models, 0.9.0's graph model `DataSource` and fields of
  `GraphNode`, `NodeData` and `GraphEdge`, the models behind
  `gspio describe --json` in `gaspatchio.cli`, and a handful of helpers and
  constructor keywords.
- A scenario plan calls the frame-only model, `ScenarioRun.run(af,
  model.main)`. A model that takes `tables=` or `drivers=` is refused,
  naming the move, and so is a shock that names no target or two.
  `ParameterShock` (write `AdditiveShock(0.01, column="infl_rate")`),
  `RelativeFloorShock` and `TimeConditionalShock(time_column=...)` are
  removed.
- `CalculationGraph` is replaced by `CalcGraph`, and `gspio calc-graph`
  writes the versioned artifact `gaspatchio-graph/v0-preview.3` in place of
  0.9.0's graph JSON. It refuses a model whose frame holds a column of a type
  the artifact has no name for -- a duration, a categorical, a struct, a
  fixed-width array, among others -- and names the conversion.
- `accumulate` takes `multiplier=` and `addend=`, not `multiply=` and `add=`.
- A column answers gaspatchio's own operations; the rest of Polars is reached
  through `.polars_native()`, and on a per-period column that escape runs
  down the model points, not along a policy's periods.
- `projection.set()`, `finance.discount_factor()`, `date.create_timeline()`
  and `date.add_duration()` change the frame they are called on and hand the
  same frame back.
- `ActuarialFrame.join` keeps the calling frame's rows first and in their
  order unless `maintain_order` says otherwise, and refuses a key whose name
  holds `,` or `=`. `with_scenarios` returns model points major and
  scenarios minor under the default streaming collect, where 0.9.0 returned
  scenarios major.
- A missing period is unknown from there on. The running folds, the four
  totals, `remaining_sum` and `prospective_value` answer null where they used
  to fold past it, and `.fill_null(0.0)` before the fold brings the old
  answer back; `accumulate` answers null from the lost period onward, where
  it answered null there and NaN after.
- A NaN in a scenario column makes every statistic over it NaN, `Min` and
  `Max` included; `Count` still counts it.
- `excel.yearfrac` is Excel's YEARFRAC: the order of the two dates no longer
  matters and nothing is negative, and its leap-day and one-year rules are
  Excel's. A per-policy flag in arithmetic answers a double (`af.smoker + 1`
  is `2.0`). An integer narrower than 64 bits -- a book column, `month`,
  `step`, `num_proj_months` -- is read as `Int64`, so an `Int32` sum assured
  times 100 is 2,500,000,000 rather than a wrapped negative, and a results
  file carries `Int64` where 0.9.0 wrote `Int32`. A `UInt64`, `Int128` or
  `UInt128` column is read as `Int64` where every value fits, and arithmetic
  on one holding a value past that range is refused rather than wrapped, as
  are a sum, a running fold and a rollforward over one. An integer literal
  past that range is refused where it is written, and `2 ** af.n` answers
  `Int64` where it answered `Int32`. A whole number written into a formula
  is an `Int64` wherever it sets a column's type: `af.c = 5` and
  `when(...).then(70000).otherwise(0)` stored `Int32`, and times 70,000 wrapped.
  A per-period conditional answers its branches' type and every value they
  hold: a `None` branch takes the other branch's type, so beside a
  `list[i64]` run it is `list[i64]`, not `list[f64]`, and whole numbers past
  2**53 are selected without loss. So are two dates and times, in their unit
  and zone, a duration, a decimal and a 128-bit whole number at any size, and
  two `None` branches answer a null of no type, as the per-policy form does.
  A per-period comparison of whole numbers, dates and times or durations is
  exact past 2**53, as the per-policy one is, and the JAX engine compares an
  `i64` run the same way; two dates and times in different units compare in
  the finer unit on both routes.
  `run_aggregated`'s `Sum` of an integer column is exact, and a total past
  `i64` is refused rather than wrapped by batch; so is each period of a
  `PeriodSum`, and a scenario's per-period total of an integer column.
  `Mean`, `Variance`, `Std` and their `Period` forms over an integer column
  are read from exact totals, so they no longer wrap or move with
  `batch_size`, and so is a scenario's `within="mean"` of its policies.
  A shift under a decimal fill, `prospective_value` and `cumulative_survival`
  widen a whole-number run on the record as `accumulate` does.
  `round_sig_figs` of a whole number is exact (781,098 to one figure is
  800,000, not 799,999), and that of a double rounds the fifteen figures a
  spreadsheet shows (0.285 to two figures is 0.29, and 781098.0 to one is
  800000.0, not 799999.9999999999). `.round()` reads a double the same way
  under either tie rule, so near-ties move: 1.005 away from zero is 1.01, and
  2.675 to the even neighbour is 2.68.
- On a per-period column, `is_in` and `replace` answer each period, where
  0.9.0 gave one `is_in` per policy and left `replace` unapplied, and a
  `clip` whose bounds are columns answers crossed bounds and a NaN as Polars'
  own `clip` does.
- Every content stamp -- an assumption table's, a join's right side's, a
  `source_sha` -- is taken over the values under the specification's content
  grammar, and an assumption table is hashed in one canonical form, so each
  moves once from 0.9.0's. With the same numbers behind them, every
  `projection.accumulate` node's digest moves once, because it records
  `reverse`, and so does every compiled rollforward's fingerprint and
  `rollforward:` id, which is now its machine alone, its schedule recorded as
  data. Some numbers move in their last digits because they are now exact: a
  division by a literal or by a constant column divides (`5 / 12` is
  `0.4166666666666667`, not `0.41666666666666663`), `10 ** af.t` is a power
  per element, and a forward discount factor is one division per period.
  `.excel.round()` and a rollforward's `round_charge=` round the 15-digit
  value a cell shows, as Excel does: `2.675` to two places is `2.68`.
- Code that ran, and answered wrongly or failed later, now refuses at the
  line that wrote it: assigning to one of the frame's own names (`af.sum =
  ...`; write `af["sum"] = ...`) or to a registered accessor's name, `and`,
  `or`, `not` or `bool()` on a column (write `&`, `|`, `~`), a bare string
  where a column-level operand belongs, a NaN or infinite literal in a
  formula or an assignment, a column of Python objects, arithmetic between
  two per-policy flags (`af.a * af.b`; write `af.a & af.b`, or the
  conversion to an amount), `projection.set()` given both of its argument
  forms, a labelled `cut` whose breakpoints run
  downward or whose labels do not match its bands, a column named under the
  frame's working prefixes `__rollforward_` or `__gaspatchio_retained__`
  (0.9.0 dropped it at collect, and a batch file 0.9.0 wrote carries the
  kernel's own such column, which `df.drop(...)` removes), and a
  rollforward's `.apply()`, refused when the rollforward is compiled rather
  than in every collect. Year fractions under `OneTwelfth` on a weekly or
  daily axis, which counted a month for the one period that crossed a month
  end and nothing for the rest, are refused, naming a day count that counts
  days.
- `select` takes one expression per column: an expression that yields several
  columns, `af.select(pl.col("a", "b") * 2)` or
  `af.select(pl.all().name.suffix("_out"))`, which 0.9.0 ran, is refused,
  naming the columns, so each can be recorded.
- `accumulate` takes numbers. A date, a time or a duration, which 0.9.0 read
  as its stored count, a category, which it read as its codes, text, which
  it parsed, and a Boolean are each refused at the assignment, naming the
  operand and the conversion to write.
- A line that would make Polars convert one kind of value into another is
  refused where it is written, naming the conversion to write instead: a
  number filled with text, `when` branches of two kinds, a shift's
  `fill_value`, a `replace`, a `clip` bound or an `is_in` member of another
  kind, a date compared with a number, and `fill_nan` over text or a flag. A
  flag in arithmetic reads 1.0 or 0.0.
- A table, mortality, curve or schedule read written inside a Polars
  expression -- continued by an undeclared method such as `.cast(...)`,
  handed to a Polars function, or opened with `.polars_native()` -- is
  refused, because the record would not name the table and the model's
  fingerprint would not move with it. Continue with a declared operation
  (`to_float()`, `fill_nan(0.0)`), or store the read as its own column first.
- On a frame with a projection timeline, `cumulative_survival`,
  `previous_period`, `next_period` and `at_period` refuse a column with one
  value per policy, which 0.9.0 ran down the rows -- across the policies --
  and `remaining_sum` and `prospective_value` refuse it by name. Look the
  column up with a per-period key, or repeat it across the timeline with
  `.projection.broadcast_to_periods()`; a frame without a timeline keeps
  running them down its rows.
- The other way round, on the same frames: a Polars row operation --
  `shift`, `diff`, the fills, `interpolate`, the `cum_*` folds, `rank`,
  `reverse`, a sort, an aggregation -- written over a per-period column and
  assigned to the frame, or used as an operand inside a framework formula
  (`af.x * pl.col("t").shift(1)`), is refused, where 0.9.0 ran it across
  the policies.
  Write it inside each policy's list, `.list.eval(pl.element().shift(1))`,
  or with the declared operation on the column. So is a statistic or another
  row-reading Polars name taken straight off a table read,
  `table.lookup(age=af.age).sum()`.
- A `with_columns` or `select` expression with no name of its own that would
  overwrite the column it reads is refused, naming the column:
  `af.with_columns(table.lookup(age=af.age))` wrote the rate over `age`.
- `&`, `|` and `~` take Boolean operands only. In 0.9.0 they did bit
  arithmetic on whole numbers -- `af.i & af.j` over `[6, 3]` and `[3, 5]`
  gave `[2, 1]`, `(af.i > 4) | af.j` gave `[3, 5]`, and `af.a & af.b` over
  two 0/1 flag columns gave 0s and 1s -- and a per-period comparison beside a
  number did arithmetic on its 0/1 indicator; 1.0.0 refuses each at the line
  that wrote it. Compare flags explicitly, `(af.a == 1) & (af.b == 1)` or
  `(af.i > 4) | (af.j == 1)`, and reach bit arithmetic through
  `af.i.polars_native().and_(af.j)`, `.or_(...)` and `.not_()`.
- Two forms of `&` and `|` that answered in 0.9.0 answer in another type.
  `|` with a Boolean expression on its left and a comparison on its right --
  `(af.a & af.b) | (af.i > 4)`, `af.x.is_null() | (af.i > 4)` -- answers
  `True` and `False` where it answered 1.0 and 0.0, and can answer `True`
  where a null operand made it null; a per-period Boolean `& True` answers
  0/1 indicators where it answered Booleans.
- A lookup built before its table was registered again with other data
  refuses at collect, where 0.9.0 read the new values.
- `register_accessor` refuses a name the frame already carries, a Python
  keyword and a name that is not an identifier. A rollforward step's label
  may not contain `@`, and a tracked rollforward reports a movement for every
  step, floors and rounds included.
- `finance.discount_factor()` refuses a `rate_col` or `periods_col` the frame
  does not carry at the call, rather than at collect.
- A `TypeError` or `KeyError` raised inside a function gaspatchio validates
  arrives as a `ValidationError`, which is a `ValueError`.
- `graph`, `schema`, `dtypes` and `materialize` are the frame's own names now:
  a data column called one of them is `af["schema"]`, not `af.schema`. On a
  fixed-step axis `step` is reserved, as `month` is on a calendar one.
- `af.trace(...)` follows the mode its frame was built with.
- A column written twice keeps its first definition's values until the
  collect, by default, so an export can carry them;
  `ActuarialFrame(..., retain_superseded=False)` declines the memory that
  costs.
- `gspio describe` and `analyze_table` no longer describe a 1,000-row sample
  or name a value column the file does not hold. `describe --json` says how
  much of the file it read and which rule chose its value column, and each
  dimension's sample values are its five lowest.
- `pyarrow` 16 or later is required, and `executing` and `jsonschema` are new
  runtime dependencies.

**What 1.0 promises.** The documented Python API -- what the API reference at
[gaspatchio.dev](https://gaspatchio.dev/) documents -- is stable, and from
1.0.0 it changes by semantic versioning: a public name is deprecated in a 1.x
release before it is removed in 2.0. Four things are previews outside that
promise, and each change to them is recorded here: the graph artifact's
schema, `gaspatchio-graph/v0-preview.3`, with its byte grammar
`gspv0-preview-3`, its specification and its conformance kit; the engine
protocol, `gaspatchio.engines` and the modules under it,
`gaspatchio.engines.format` among them; and the two 0.1.0 distributions,
`gaspatchio-jax` and `gaspatchio-viewer`.

**What the JAX engine promises.** Agreement with the Polars engine on the CPU
is the contract, under the specification's agreement rule (section 11.1.12 of
`spec/graph-artifact/v0-preview.md`): two finite results agree when they
differ by no more than 1e-12 of the line's scale, and integers, Booleans,
dates and text agree exactly. The engine is also qualified on an NVIDIA T4.
There, every node of levels 4 and 5 over a thousand policies agreed with
Polars within the rule, the worst line differing by 2.0e-14 of its scale. A
ten-million-policy level-4 book folded on the card in 17.8 s, and the fold's
own check against Polars, run at ten thousand policies, agreed to 7.9e-16.
Choosing the engine does not choose a GPU; JAX's own configuration does. A
book too big to hold is folded on the card: `run_aggregated(...,
engine="jax")` and `gspio run-artifact --engine jax --aggregate` hand back
its totals, never its rows.

**Built on Polars 1.42.1.** 1.0.0 ships on Python Polars 1.42.1 and the
Polars crates at 0.53. A panic in Polars' Arrow export, when a sliced
fixed-width `Array` column with a null in its window crosses into the Rust
extension, is fixed upstream in Python Polars 1.43.2 and the crates' 0.55.1.
This release steps around it in its own code instead: content stamps hand
arrays over as lists, and the assumption-table registry carries the same
guard. The move to Polars 2 is a release of its own.

**Credits.** The viewer draws its graph with React Flow (`@xyflow/react`,
MIT, from xyflow), laid out by dagre (`@dagrejs/dagre`, MIT). The page keeps
React Flow's attribution link on its canvas, as xyflow asks of projects
without a React Flow Pro subscription. Every package the page bundles is
listed with its licence in the viewer wheel's `third-party-notices.txt`, and
every page `--html` writes carries the same notices at its end. The core's
extension is built on 284 Rust crates, Polars and PyO3 among them, and on the
Rust standard library; the core's wheels and sdist carry the licence and
notices of each in a `third-party-notices.txt` of their own.

The detailed entries follow.

### Added

- **`af.graph` — ask a model how each of its columns was made.** Eight
  questions, answered off the model's own calculation record without running
  anything: `precedents` (what a column read), `dependents` (what read it),
  `trace` (everything behind it, all the way down), `affected` (everything
  ahead of it, all the way to the outputs — if this assumption moves, what
  moves with it), `versions` and `latest` (a name written twice is two
  worksheet columns wearing one Python name, and these say which is which),
  `holes` (columns the model cannot account for), and `fingerprint` (the
  model's content-addressed identity). `precedents` and `dependents` are the
  worksheet's own audit-arrow pair, named as the worksheet names them, and
  `trace` and `affected` are those same two directions walked all the way.
  Answers are node ids rather than column names, because that is
  the point: `precedents("death_claims")` naming `policies_in_force@1` says
  which definition the claims were taken on, which a column name cannot.
  Asking about a name the model has never held is refused by name, with the
  versions or the nearest columns that do exist — an empty tuple would read as
  "nothing depends on it", which is a different and much more comfortable
  answer. `graph` joins `date` and `projection` as a reserved attribute on the
  frame; a data column genuinely called `graph` is still reached as
  `af["graph"]`.

- **Content fingerprints, per calculation and per model.** Every node carries
  a `sha256:` stamp over what it computes, and a second one folding in the
  stamps of everything it reads; `af.graph.fingerprint()` gives one stamp for
  the whole model, covering the assumption tables it reads, the values
  injected into it, and the columns it cannot account for. What is hashed of
  a calculation is the calculation and nothing else — not its formatting, not
  the line it was written on, not the name it was assigned to — so
  reformatting a model does not move a fingerprint, and a renamed column is
  recognisably the same calculation rather than one reserve deleted and an
  identical one invented in the same quarter. A horizon extended from 99 to
  100 shows one changed timeline and the tail that inherited the movement,
  not a model rewritten end to end.

- **A column the framework cannot account for is now named, not omitted.**
  Every column a finished model holds should be a calculation it recorded, a
  field the data arrived with, or values injected at a line it can point to.
  Anything else — a column written straight into the query plan, say — used
  to be left out of the calculation graph entirely, so a reserve could be
  exported as reading a column the graph did not contain. Those columns now
  appear as nodes of their own kind, each carrying its name and a hint naming
  the next move: assign it through the frame so the calculation is recorded,
  or load it with the model points so it arrives as an input.
  `af.graph.holes()` lists them and `gspio calc-graph` counts them. This
  marks rather than refuses — the numbers from such a run are fine, and what
  is incomplete is the account of how they were made.

- **A column written straight into the query plan over one the model
  accounted for is a hole, where the write happened.** A write to `af._df`
  that redefines a recorded column, or one the data arrived with, left the
  replaced formula showing while `collect()` returned what the write computed.
  The frame now reads the write off Polars' plan and logs the column as
  overwritten at the write's line: `af.graph.holes()` gives the reason
  `overwritten`, the audit file carries a definition of its own
  (`reserve@2`) that later calculations read, `gspio diff` reports it, and a
  second engine refuses it, naming the line. A write the frame cannot read
  reports every accounted column the plan still holds; reordering, filtering
  or moving whole rows, marking a column sorted, and handing columns back
  unchanged report nothing; and `af._df = af._df.collect().lazy()` is pointed
  at `af.materialize()`. Reading a write costs in proportion to the plan
  underneath it, so a model that writes straight into the plan pays about
  12 ms a write on the level-4 tutorial model; see *Known limits*. A model
  that only uses the frame's own doors reads nothing and pays nothing.

- **A frame built over another frame's collected values names the columns it
  cannot account for.** A column whose memory belongs to a calculated column
  of values still held -- by that frame or by whoever called `collect()` -- is
  a `rebuilt` hole, naming the definition and line and
  `ActuarialFrame(df, continue_from=af)` as the fix. Copied values, an input
  handed back unchanged and values nobody still holds arrive as data, and the
  template's setup step, which collects before any calculation, says nothing.
  The hole reasons are `unrecorded`, `overwritten` and `rebuilt`, and
  `gspio validate` holds every hole to the shape its reason requires and the
  holes section to the hole nodes.

- **`af.graph.tiers()` counts every calculation at its tier.** An empty
  `holes()` says every column is accounted for; it does not say every line is
  written in the format's own vocabulary. The census does: it returns a
  `TierCensus` naming each calculation by node id at `core`, `engine_native`
  (a fragment of one engine's own expression language, such as
  `.polars_native()`) or `opaque`, with `counts` stating all three, zeros
  included. It agrees node for node with each node's `tier` in the exported
  document, and `gspio calc-graph` prints it under its node count.

- **`af.materialize()` — freeze the setup phase without losing its history.**
  At the end of Phase 1, once the model points are joined, renamed and
  enriched, everything the setup computed is still a recipe Polars re-derives
  on every collect, and the projection is planned on top of it.
  `materialize()` turns it into values, so the projection builds over settled
  model points. It replaces the `af = ActuarialFrame(af.collect())`
  round-trip, which froze the values and threw away everything else the frame
  knew — how each column was calculated, which projection axis it was on,
  which columns arrived with the data. The calculation record survives
  intact, with a boundary in it marking where the freeze happened, and a
  column's assignment count carries on across it: a reserve written before
  the freeze and again after it is still one column written twice, not two
  first assignments.

- **One artifact can carry more than one policy, on an axis the envelope
  declares — and nothing picks the policies for you.** Until now a
  calculation-graph document held one model point, so two questions a
  reviewer always asks had no answer in it: *how does this policy differ from
  that one?*, and *which of these is the one I was shown?* A single policy
  with no account of how it was chosen reads as a policy somebody chose, and
  on the overwhelmingly common export nobody did — it is the first row of the
  file.

  `gspio calc-graph` gains `--policies`, repeatable and unioned. Five forms,
  read by the term's own shape: `:30`, `3:40`, `::10` and `-5:` name row
  positions with Python's own slice semantics; `all` is every policy;
  `spread:5@sum_assured` orders the book by one column and walks it at even
  spacing; `id:POL-000343` names one policy verbatim; and anything else is an
  id, or a comma-separated run of them. The escape is what makes the rest
  safe — a book whose ids look like `3:40` or `all` still has every policy
  reachable — and deciding by shape rather than by what the book holds is
  what keeps one command line meaning one thing on two books. `--policy-id 7`
  still works and is `--policies 7`. `--max-size` guards the finished
  document in bytes, defaulting to 25 MiB, because per-policy bytes vary by
  model by a factor of several and a count of policies would be the wrong
  number on every model but the one it was chosen on.

  **Nothing is automatic.** No ranking column is inferred, no cohorts are
  built, no anomaly rule fires. A selection that picks badly is worse than a
  visibly arbitrary one, because a clever rule looks authoritative: "row 0 of
  1,000" tells you exactly how much to read into the policy in front of you.
  Every entry on the axis carries `why`, a plain sentence recording the row
  and the id both, and every refusal says which of the things that can be
  wrong is wrong — an id the book does not hold, an id two rows answer to, a
  slice that lands on nothing, a `spread` column that is missing, per-period
  or too coarse, a document over the ceiling.

  **A selection chooses which policies are sampled, never which are
  computed.** The model runs the whole book whatever is selected, so a
  twenty-policy export of a hundred-thousand-policy book costs what a
  single-policy export of that book already cost, and `--output-file` still
  writes the book's numbers. The reason is not speed: a model with a
  cross-row step — a scenario axis is a cross-join on the model points, and a
  fold over one reads across rows — would give a policy one answer in a
  narrowed export and another in the run the actuary performed, and the whole
  claim this document makes is that every number in it is a quotation of a
  run that was performed. `--filter` is the option that narrows rows, and the
  envelope records it on every entry of the axis; the two are different
  things and the document says them separately.

- **An aggregation's edge says which periods it read.** "Does the model's
  reserve read the same periods as the workbook's column?" was answered from
  the formula text: an edge into `cum_sum`, `remaining_sum` or `list.sum()`
  said `AGGREGATION` and nothing about which run. The audit file's narrowing
  facet now states it, quoted from each operation's own attributes:
  `"periods": {"from": "first", "to": 0}` for a cumulative sum, a survival
  fold, a forward recurrence and every column a compiled rollforward reads;
  `{"from": 0, "to": "last"}` under `reverse=True`, for a remaining sum and
  for a prospective value's cashflows and list rate; `{"from": "first",
  "to": -1}` for a survival fold with `start_at` and a forward discount
  factor's rate; `{"from": "first", "to": "last"}` for the four reductions,
  `excel.irr` and `list.reverse`. A literal `list.get(k)` states
  `"position": k`. A window through two operations is composed where it can
  be written exactly -- `cum_sum` of `previous_period` reads `{first, -1}` --
  and stated nowhere it cannot; a per-policy column states none. A name read
  through two windows in one formula now writes one `transformations` entry
  per window, strongest first, so `cum_sum(x) - x` says both that it read
  this period and the run to date. No digest moves. The viewer labels the
  window on the cone's loop, outlines every cell of it in the grid and names
  it on the proof panel's line. The conformance kit gains
  `vectors/windows.json`: a perturbation vector per windowed operation, which
  moves one cell of an operand and holds Polars and JAX to leaving every
  period outside the stated window where it was.

  Serves *Audit by default*, *Sharp knives, no magic* and *LLM-shaped from the
  inside out*: the file answers a timing question without anyone parsing a
  formula. Strains nothing named beyond the 1.0 scope it took.

- **An audit file exported from Python says which model it is an account of.**
  `GraphExportConfig(model=ModelIdentity.of("model.py",
  model_points="points.parquet", results="results.parquet"))` fills in the
  version block from the files: the source's path and sha256, the git commit
  and whether the tree was clean, and a path and sha256 for each file named.
  `gspio calc-graph` calls the same helper, so the two routes write one block
  and write every node's location against one root -- the repository the model
  sits in, or the model file's own directory -- and no absolute path. A file
  named that is not there is refused, and so is an identity whose relative
  paths have lost their root. A model file the commit does not hold is
  recorded with `dirty: true`.

- **A results file says what produced it.** `gspio run-model --results`,
  `gspio calc-graph --results` and `gspio run-single-policy --results` write
  the result manifest into the Parquet file's own metadata: the model's
  fingerprint, the digest of the book it ran over, each final-schema line's
  column and type, and the library versions. The columns keep the model's own
  names. `calc-graph`'s manifest states the fingerprint and book digest its
  audit file states, and `gspio compare` compares such a file with an engine's
  results. Where a fact cannot be vouched for, the file carries no manifest
  and one line says what, and why. Writing it costs about 0.6 s per million
  policies, and 0.14 s once per command to state the versions.

- **`af.graph.last_run.versions`** states the library versions a collection
  ran on: the core package's version and the version compiled into its
  extension -- one number in a release wheel, stated apart where an install
  holds them apart -- Polars, Python, the platform and the extension's digest,
  or, for an engine's run, the versions its own manifest names under the same
  keys. They are read when first asked for, so a collect pays nothing, and
  where the extension changed on disk after the process loaded it the digest
  says so rather than naming the new file.

- **`Table.fingerprint()` returns a table's content identity,** the hash the
  calculation graph records as the table's `assumptions[].fingerprint` and
  every lookup's `table_fingerprint`. It depends on the values alone.
  `Table.source_sha()` stays the identity of the configured table -- name,
  dimensions, value column and that fingerprint -- and both docstrings say
  which is which. `MortalityTable.fingerprint()` returns the same identity for
  the rates a mortality wrapper reads.

- **`gspio verify` checks the files in hand against the audit file that
  records them.** A reviewer holding an audit file, a results file, the policy
  data and the model source asks one question -- are these the files this
  audit file is an account of? -- and the command answers it check by check.
  Four checks decide: the audit file's seal, the results file's sha256 against
  `model.results`, the policy data's content against `book.digest`, and the
  model source against `model.source_sha`. Three add evidence where there is
  some: the results file's own manifest (its model fingerprint, and its book
  digest where the engine was handed the book itself), the policy data file's
  stamp where the audit file states no book digest, and the checkout's
  revision against `model.git`. Each check answers `agree`, `disagree` or
  `indeterminate` -- the words `gspio compare` uses, the last for a check that
  decides with nothing recorded to check against -- or `not_asked`; the
  command exits 2 where a file cannot be read, 1 where any check disagrees, 4
  where any is indeterminate, and 0 otherwise. A policy data file re-encoded,
  or written as CSV, or carrying a column the model does not read, is the same
  book and agrees. A recorded dirty tree is stated and moves no status: the
  source check pins the model file itself. The seal shows the document has not
  changed since it was sealed; it is evidence against a copy kept apart, not a
  signature. `--json` and `--output-file` store the report, and
  `gaspatchio.frame.graph.verify_artifact` answers the same in Python.

- **`gspio verify --assumptions` checks the assumption tables, and `--model`
  the helpers the model imports.** `--assumptions` takes table files and
  directories of them (repeat it; `NAME=FILE` names a table's file outright).
  Each table the audit file records is found by the file it records the table
  read from, else by its own name, read as that table through its recorded
  keys and answer column, and held against its fingerprint -- the one
  `Table.fingerprint()` gives, so a file re-saved as CSV with its columns in
  another order still agrees and a moved rate does not. A difference
  disagrees only where the audit file names the file the table was a plain
  read of. A table whose recipe reshaped what it read -- a column renamed,
  cast, melted, set or computed -- is never read back from a file, and one the
  model built from a frame (`Table(source=pl.read_parquet(...))`) that reads
  differently from the file matched to it is `indeterminate`, because rows
  filtered in code and an edit to the file read alike; hand `Table` the path
  to have a difference decide. A frame-built table with no file named for it
  is `not_asked`; a file not found is `indeterminate`. A table too large to
  inline (over 1 MiB) is still checked: the stand-in for its values keeps its
  roles. `--model` now also holds each local module the model
  imports -- the file of that name beside the model given -- against the
  sha256 the audit file records, so an edited helper fails as an edited model
  does. The audit file carries what both need: `model.modules`, every local
  module the model imports with the sha256 of its bytes, read off the
  model's import statements so a Python export and `calc-graph` write one
  list; and on each table entry `source_file`, the file it was read from or
  null where the model built it from a frame, `shaped_by`, each step of its
  recipe that reshaped what it read, and `roles` in the stand-in where its
  values are left out for their size. `ModelIdentity.of` fills in `modules`.

- **`gspio diff` says what moved between two versions of a model, and by how
  much.** Where both audit files record the results file their run wrote, and
  each is still where it was written with the checksum recorded, the command
  reads the two files beside the two audit files and the report gains a
  `values` member: for each line the two versions share, whether its numbers
  moved, in how many policies, from which period, the largest absolute and
  relative move (a move out of zero said as "from 0", never divided), and the
  policy and period it is at with both values. Its headline is the table
  seven workbook conversions each built by hand: edited lines that moved and
  that moved no number, inherited lines that moved and whose numbers held,
  lines that moved under definitions that did not -- put down to the book,
  the producer, or nothing the record states -- and the policies only one
  book holds, counted and named as joined or left rather than refused. A
  value has moved when it is unequal; a move inside section 11.1.12's band is
  still listed, labelled as indistinguishable from arithmetic. `--results
  EARLIER LATER` names two files instead, `--no-results` reads none,
  `--policy-id-column` pairs the policies (again for a scenario column), and
  `--floor` trims the printed list and never the JSON. A line whose
  definition did not move and whose numbers did, beyond the band, over the
  same book and producer, is drift. `--html` carries the book-wide reading
  into the page, and `diff_with_results(before, after, q1, q2)` answers the
  same in Python. The report grammar is `gaspatchio-graph-diff/v0-preview.2`.
  `gspio compare`, which asks whether two runs of one calculation agree,
  names this command when it refuses two versions' results, and so does the
  diff's own line under a results file that moved, where it used to say to
  join the two files by hand.

- **`gspio diff` compares the results file each run recorded.** Two audit
  files of one model over one book used to compare as nothing moved over two
  different results files -- which is what a change the audit file does not
  carry produces: a run on other library versions that moves a number, or a
  write that goes around even the frame's own handle on its plan. Where both
  documents record their
  results file (`calc-graph --results`, or `ModelIdentity.of(...,
  results=...)`), a difference in `model.results` is a `data` entry of kind
  `results`, and it is drift, so the command exits 1. The entry says the file
  moved, not that any number did: a results file records the library versions
  and platform that wrote it, and `gspio compare` says whether the two results
  agree. Where only one run recorded a results file's checksum, one line says
  which, and the status is unchanged. `diff_artifacts` and `gspio diff --html`
  give the same answer.

- **`gspio diff` reads an audit file as a past revision committed it.**
  Either side may be `git:REV:path`: `gspio diff
  git:v2026.Q2:model.audit.json model.audit.json` compares last quarter's
  committed audit file with today's, read from the repository the command
  runs in, without a checkout and without running the model again. The
  revision is anything git resolves without a warning -- a tag, a commit, a
  branch, `HEAD~1` -- and `@{date}`, which reads this clone's own reflog, is
  refused where git can only guess, naming a tag or `git log -1
  --until=DATE BRANCH` instead. The path is git's: from the repository's
  root, or from the current directory with `./` or `../`, and a plain path
  that would name a different file from a subdirectory is refused, naming
  both. Reading runs git and nothing else: nothing is fetched, no one is
  asked for a password, replace refs and grafts are ignored, and a hook's
  quarantined objects are read. A symbolic link, a submodule, a tag of a
  tree, a shallow or partial clone and a Git LFS pointer each get a refusal
  of their own that names the next move.

- **The audit file answers `af.graph`'s questions on its own: `gspio graph`
  and `gaspatchio.graph.read_artifact`.** A reviewer handed only the file
  asks it what `af.graph` answers on a frame -- `gspio graph precedents`,
  `dependents`, `trace`, `affected`, `unused`, `holes` and `tiers`, each
  `af.graph`'s method under its own name -- and in Python
  `read_artifact("audit.json").trace("reserve")`. Both are answered by one
  walk over one structure, so the file and the frame give the same node ids
  in the same order, and the same refusal for a column neither holds: every
  question about every node of each shipped model is compared in the suite.
  `gspio graph trace audit.json reserve --depth 2` prints each node after
  everything it reads, each arrow with the period it read (`t−1`,
  `first…t`, `t…last`, `position 0`) taken from the file's narrowing facet.
  `af.graph.affected(assumption="mortality")` and `gspio graph affected
  audit.json --assumption mortality` open the cone at every calculation that
  looked the table up; `trace` and `affected` take `depth=` / `--depth N`
  and run to the end by default. `af.graph.unused()` and `gspio graph
  unused` put every node nothing reads under one class the record states:
  `superseded` (a definition replaced before anything read it), `data`,
  `stamp` (a projection column), `length_only` (read only for its length)
  and `terminal` (a live calculation nothing reads: a result or dead code,
  which the model does not say). `--keep a,b`, `--keep-from results.toml`
  (`keep = [...]`) and `unused(keep=[...])` move named results to `kept`,
  and `--fail-on superseded,terminal` exits 1 for CI. Text by default,
  `--json` and `-o` as `diff` and `verify` have them; an unreadable file or
  a column the file does not hold exits 2 in `af.graph`'s own words.

  Serves *Audit by default* (the file answers for itself) and *LLM-shaped
  from the inside out* (one vocabulary in Python and at the shell). Strains
  scope: a command group of seven subcommands to keep.

- **A policy laid out as a spreadsheet, every cell the record's own double.**
  `gspio calc-graph model.py points.parquet --policies id:POL-7 --xlsx
  policy.xlsx` also writes the audit file's policy as an `.xlsx` workbook a
  reviewer opens in Excel or LibreOffice without Python. README names the record by
  its `document_digest`, `graph_fingerprint`, `formulas_fingerprint` and
  `source_sha`, the book's digest, the policy and why it is in the record,
  the library versions that produced it and, given the results file, whether
  it is the one the record names. Timeline has a row per period and a column
  per per-period calculation in the order the model made them, each headed by
  its node, its formula and its tier; Scalars, Nodes, Edges (each read's
  offset and period window) and Assumptions (fingerprint, `source_file`,
  `shaped_by`) follow. A record carrying several policies gives each a
  Timeline sheet of its own. `gspio sheet model.audit.json --policy POL-7`
  lays out a record already on disk, or `git:REV:path`, and in Python
  `af.graph.to_excel("policy.xlsx", df)` and
  `gaspatchio.frame.graph.render_xlsx(record)` do the same. Every number is
  written as the shortest decimal that reads back to the record's double, up
  to 17 significant digits. xlsxwriter and openpyxl write 16, so 0.1 + 0.2
  arrives as 0.3; measured over 10,001 random doubles, 4,512 came back from
  either as another number, and none from this writer.
  NaN and the infinities are the record's own words as text, a whole number
  past 2^53 is its digits as text, and a date is its ISO text. No cell holds
  a spreadsheet formula. The file is a function of the record alone, stored
  rather than compressed and dated by the record's `created_at`, so one
  record lays out to the same bytes on any machine. A record whose seal does
  not hold is refused, and so is a policy the record carries no values for
  (`gspio sheet` exits 3). `run-single-policy --help` points here.

  Serves *Meet you where you are* (the reviewer's own tool), *Audit by
  default* (the workbook names its record by digest and quotes its every
  value) and *No vendor lock-in*. Strains scope: the project now owns a small
  OOXML writer, and that Excel reads every 17-digit cell back as the same
  double is still to be confirmed by hand (see *Known limits*).

- **Every page the viewer writes carries the notices of what it bundles.** A
  page from `gspio calc-graph --html` or `gspio diff --html` holds React,
  React Flow, dagre and the rest of the viewer's bundle, and three font faces,
  each licensed on the condition that its notice travels with it -- and a page
  travels without the wheel it came from. Each page now ends, after
  `</html>`, with the viewer's `third-party-notices.txt` in a comment. Two
  hyphens together could close a comment, and a licence text may hold them,
  so the comment first says how its text is escaped: each backslash is
  written as two, and each hyphen that follows a hyphen has a backslash
  before it. Undoing that gives the file back byte for byte, which the tests
  check from the file in Python and from the parsed page in Chromium and
  WebKit. The notices add 33,801 bytes to every page, about 4 KB gzipped, and
  none of it reaches the screen. `gaspatchio_viewer.notices()` returns the
  same text, and a page built from `bundle()` and `styles()` some other way
  has to carry it too, as their docstrings now say. Both commands now write
  the page as UTF-8 on every platform, as the page says it is, and `gspio
  diff` and `gspio validate` read an artifact as UTF-8, which JSON is: the
  notices hold characters that a Windows code page would write as other
  bytes, or not at all, and a producer's UTF-8 read as one would be misread.

  Serves *No vendor lock-in* and *Audit by default*: a page says what it
  contains wherever it is sent. Strains *Optimize for the laptop* by those
  33,801 bytes on every page.

- **The Audit View states the tier census.** Its strip says how many
  calculations sit at each tier -- `core`, `engine_native` and `opaque`,
  zeros included -- and names the ones below core, each taking the reader to
  its node; the Model tab states the same under the holes line, so "every
  column is accounted for" is not read as "every line is in the format's own
  vocabulary". A file that records no tiers states none, and `gspio
  validate` refuses a calculation that states no tier.

- **The comparison page names a cause only where the record supports one.** A
  line whose values moved while its definition did not is said to move with
  the book only where the two books differ; a change of producer between the
  runs is shown as a possible explanation, not the cause; a move within the
  specification's agreement tolerance reads as agreement; and otherwise the
  page says nothing in the record explains the move, and names the check that
  finds it: recompute the model from its audit file on a second engine and
  compare the two runs.

- **`gspio diff --html` names each side.** The comparison page shows the
  label each document came with beside its date -- the path as typed, or
  `model.audit.json at v2026.Q2` for a revision -- so a reader handed the page
  alone can tell which is which. `render_html` and `gaspatchio_viewer.render`
  take `label=` and `second_label=`.

- **The viewer's row labels stick as one column,** where each was a
  compositing layer of its own: a level-4 page carries 18 layers where it
  carried 49, or 81 at period 40, and the labels stay level with their rows
  at any zoom.

- **A scenario plan runs the model you reconciled, unchanged, and shocks its
  tables and model-point columns itself.** `plan.run(af, model.main)` runs the
  frame-only `main(af)` that `gspio run-model` runs: no
  `assumptions_override=`, no `model_fn(af, *, tables, drivers)` wrapper, no
  scenario guard at each lookup. A shock names its target by name. With
  `table="mortality_select"`, the model's own `Table.lookup` and
  `MortalityTable.at` reads of the table built under that name are answered
  with it shocked per scenario, stacked with the scenario axis as a key in a
  batch. The lookup node is byte for byte the one a model handed the stacked
  table by hand would write, and a table no shock names is read exactly as
  written. With `column="valuation_rate"`, a single number the model reads
  off each policy is rewritten per scenario before the model runs, so
  scalars stay the model-point columns the conversion skill makes them:
  `AdditiveShock(0.01, column="valuation_rate")`, or a solved premium as
  `OverrideShock(1234.56, column="annual_premium")`. The rewrite is
  recorded as an `assignment` at the plan's line, its formula the shock's
  recipe. Within a batch, an affine sweep (multiply, add, set, and pipelines
  of them, on a float column) reads per-scenario factors keyed by the axis,
  exactly; any other column shock is a `when` chain. Measured at 1000
  policies, the chain cost 20 times the factor read to collect at 200
  scenarios in one batch, and at 1000 it was too deep to build. Each scenario's fingerprint is now the scenario composed on its
  own, so `result.fingerprint("BASE")` equals the standalone model's
  `af.graph.fingerprint()`: a check where it used to be a measurement. A
  model that dispatches on `scenario_id` itself is composed alone over a
  one-scenario axis, so each scenario keeps an identity of its own. A seeded
  plan hands each scenario its seed as the `rng_seed` column, at any batch
  size. The run record gains `bases`: per shocked table, the content
  fingerprint the shock was applied to and the file it came from.

- **A scenario plan writes itself down, every shock kind.** `to_yaml`
  refused filtered, time-conditional, pipeline, max, min and clip shocks, so
  five of seven plans could not be written down and pinned a SHA instead.
  Every kind now writes in the operation-keyed form (`multiply`, `add`,
  `set`, `clip`, `pipeline`, `max`, `min`, `where`, `when`, target `table:`
  or `column:` on the outermost shock) and reads back to the same plan:
  `ScenarioRun.from_yaml(path).source_sha() == plan.source_sha()`.
  Hand-written sugar, such as `{table: lapse, multiply: 1.5, where: ...}`,
  parses to the same identity as the object, and a key a shock does not take
  is refused rather than ignored.

- **Three named conversions — `to_float`, `to_text` and `to_list` — so every
  type the framework names has a declared door.** A type assertion used to be
  reachable only through `.polars_native().cast(...)`, because `cast` is not a
  declared operation: the escaped node then exported with no engine list, and
  every column composed on it was warned. Three refusals in the audit export
  taught that escape by name. They now name an operation instead, and each new
  operation states what it refuses so that no lossy form hides behind an
  identifier a reviewer reads off the trace.

  `af.policy_number.to_text()` writes a value out losing nothing — an integer
  by its digits whatever width it is stored in, a floating-point value by the
  shortest decimal that reads back to the same number, a boolean as `true` or
  `false`, a date as ISO `YYYY-MM-DD`, text and categories unchanged, a null
  carried. It is the answer for a warehouse identifier or a `.hash()` column
  past 2⁶³, where the artifact's vocabulary has no exact numeric name left.
  `af.units.to_float()` widens a whole number to a double and refuses one
  outside `[-2⁵³, 2⁵³]`, where two neighbouring whole numbers would arrive as
  the same value and read as equal ever after; a double comes back unchanged
  and a null is carried rather than refused. `af.charges.to_list()` gives up a
  fixed-width array's width and keeps its elements in order; a column that is
  already a list is refused rather than passed through, so the node means one
  thing wherever it is read. There is deliberately no generic `cast(type)`:
  one identifier over every pair of types would put the conversions that lose
  nothing behind the same name as the ones that lose digits.

  `to_integer` widens with them. An integer stored in a width wider than
  `i64` — unsigned, or 128-bit — is an integer for that call and is judged on
  its value rather than refused on its type, which is the rule the audit
  export already applies to the same widths. A value inside
  `[-2⁶³, 2⁶³ - 1]` converts; one outside it refuses by a sentence of its
  own, because a whole number too wide is whole and the advice to round it is
  advice about a defect it does not have. That refusal names `to_text()`.

  Sections 11.1.38, 11.1.39 and 11.1.40 of the format specification state the
  three, 11.1.23 restates its accepted types, and one 14.1 line carries the
  disclosure — additive vocabulary growth plus one widened accepted domain,
  with no field, tag, attribute or byte encoding moved. Thirty-nine vectors
  join a new `conversions.json`, every expected value hand-derived from the clause
  rather than read off the producer, and no existing bundle changes a byte.
  The published vector envelope gains five names on inputs only — `u64`,
  `i128`, `u128`, `categorical` and `array[<element>,<n>]` — because three of
  these clauses exist to convert a column out of a type the vocabulary cannot
  name, and a case could not otherwise state one. The independent reader
  shipped in `reader.pyz` implements all three.

  Serves *Sharp knives, no magic* — a named conversion is auditable where a
  generic cast is a matrix — and *Audit by default*: every conversion is now a
  node on the record with a sentence a reviewer can read. Strains *Meet you
  where you are*: a Polars user who writes `.cast` is still refused, now
  pointed at a name.

- **`fill_nan(value)` is a declared operation, so a table read cleaned of its
  NaN is one line that names its table.** `af.q =
  lapse.lookup(duration=af.duration).fill_nan(0.0)` records one `core` node,
  a fill over the lookup, whose fingerprint moves when the table does. Without
  it the line was refused for hiding the table inside an engine fragment (see
  *Breaking*, a table read written inside a Polars expression), and
  `af.q0.fill_nan(0.0)` on a stored column was refused as a name the
  vocabulary did not hold. It replaces a NaN and nothing else: an infinity and
  a null are kept, and a null is `fill_null`'s to fill. The fill is an operand
  -- a value, a column or an expression -- and over a per-period column a
  per-policy fill reaches every NaN period of its policy and a per-period fill
  the same period. Over a whole-number column it replaces nothing, in the type
  the column shares with the fill; over a Boolean, text or date column it is
  refused. `fill_nan(None)`, which turns a NaN into a null, stays on
  `.polars_native()`, and `.polars_native().fill_nan(0.0)` is refused and
  names the declared spelling. Spec section 11.1.13 states it, the conformance
  kit carries `vectors/nan-fill.json`, and the JAX engine lowers it to Polars'
  own doubles.

  Serves *Meet you where you are* (the commonest clean-up of a lookup is one
  line again) and *Audit by default* (the line keeps the table's identity).

- **`norm_cdf()` is the standard normal distribution function, Φ.** A GMDB
  or GMMB valued as a Black-Scholes put needs N(-d1) and N(-d2), and a
  workbook writes them as `NORM.S.DIST(z, TRUE)`, `NORMSDIST(z)` or
  `NORM.DIST(z, 0, 1, TRUE)`. Write them as `(-af.d2).norm_cdf()`.
  `af.z.excel.norm_s_dist()` is the Excel spelling of the same operation: it
  records the same node, so a converted workbook and a model written from the
  textbook publish the same fingerprint. `NORM.DIST(x, mean, sd, TRUE)` is
  `((x - mean) / sd).norm_cdf()`. A native elementwise kernel computes
  `0.5 * erfc(-x / √2)`, on per-policy and per-period columns alike, and the
  streaming engine keeps running. The result agrees with the true Φ to 1e-12
  relative wherever Φ is a normal double (x ≥ -37.5); measured, the worst
  error is 6e-15 where |x| ≤ 6 and 1.8e-13 near -37. Null, NaN and the two
  infinities are exact. It does not try to reproduce Excel's own bits, which
  sit within about 1e-14 of Φ, so reconcile at that order. The node is
  `core`, and the JAX engine runs it as `ndtr`. Until now the one model in
  evidence hand-built Φ from about 190 nested operations in an accessor: it
  was engine text, took about a minute a call at 100,000 policies, and took
  the whole valuation out of the portable set with it. The textbook form
  `0.5 * (1 + erf(x / √2))` answers 0.0 at -8.36. `excel.norm_s_dist(cumulative=False)`
  is refused, and the message gives the density in core operations. The
  inverse is not in 1.0; `norm_inv` is reserved, and its refusal points to
  `statistics.NormalDist().inv_cdf` for a constant fixed in setup.

  Serves *Optimize for the laptop*, *No vendor lock-in* and *Sharp knives,
  no magic*: one function with one identity, behind two doors.

- **A projection axis of fixed steps in years, with no calendar under it.**
  A teaching workbook, a numerical solution of Thiele's or Kolmogorov's
  equations, or a continuous-time product discretised for valuation steps
  `k × h` years and has no dates; the only way to build one before was to
  carry the step index as model-point data, with no projection -- so a period
  method on a per-policy column ran down the policies (three policies with
  `q` of 0.1, 0.2 and 0.3 gave `previous_period` `[0.0, 0.1, 0.2]`), and there
  was no rollforward and no `t_years()`. Now
  `af.projection.set(n_periods=2947, step_years=0.1)` or
  `af.projection.set(n_periods=240, steps_per_year=12)` lays the axis, and
  `Schedule.fixed_step(...)` builds the same one for `schedule=`. It stamps
  `step` (`0..T`, Int64), `num_proj_months` (`T + 1`) and, only where a step
  is whole months (`steps_per_year` of 1, 2, 3, 4, 6 or 12), `month`; it
  stamps no dates. `t_years()` there is `k × step_years` or
  `k ÷ steps_per_year`, one rounding per boundary, so
  `af.issue_age + af.projection.t_years()` is a workbook's `x + A*h` or
  `x + A/12` bit for bit in the spelling the model chose (the other spelling
  differs at about a third of the boundaries, a running sum at nearly all of
  them). `year_fractions()` is the step each period; `anniversary_mask()`
  falls on every n-th step under `steps_per_year` and refuses under
  `step_years`, naming `steps_per_year`; `period_dates()`, `end_date_column`,
  and `start_date`, `valuation_date`, `frequency` or `until=` beside the step
  refuse, naming the calendar form. The period-method guard holds on the axis,
  and on a frame rebuilt from its output by its `step` column; the
  rollforward, `broadcast_to_periods()` and the JAX engine run on it, JAX to
  the reference producer's bit. A calendar axis is unchanged, and its
  `t_years()` docstring now says a monthly grid's running sum differs from
  `k/12` in the last bits. Specification sections 11.1.1, 11.1.37,
  15, 16.1 and 17 state the form, and the conformance kit gains
  `vectors/fixed-step.json`.

  Serves *Meet you where you are* (the workbook's own step, in both of its
  spellings) and *Sharp knives, no magic* (no invented dates, months or
  anniversaries). Strains scope: a fourth axis form, and a second definition
  of `t_years()` documented beside the first.

- **The projection family's value semantics are stated in the format
  specification.** Four normative clauses joined section 11.1 of
  `spec/graph-artifact/v0-preview.md`, and they are what an independent
  consumer needs to execute a projection artifact rather than guess at one.
  **11.1.18** states the shapes every other clause rests on: the outer axis
  of a column is the model-point row, position `t` of a list column is that
  policy's period `t`, a scalar broadcasts along one policy's periods and
  never across policies, two lists must match in length within a policy, and
  policies need not share a period count — a backend that needs one
  rectangular grid may refuse such a run as its own limitation, but it may
  not call the artifact invalid for that reason. It also states the stored
  Float64 predicate at its deliberately narrow width: a `when_then` condition
  that directly references an `f64` or `list[f64]` column must be exactly
  `0.0` or `1.0` at that boundary, and any other numeric value is a refusal
  rather than truthiness. **11.1.19** states `cumulative_survival` where
  `from_survival` is false — the cumulative product, and `start_at` as the
  value at the opening boundary rather than an extra factor in every later
  product — with `previous_period`, `next_period` and `at_period` beside it.
  **11.1.20** states the `accumulate` recurrence
  `s[t] = s[t-1] * multiplier[t] + addend[t]`, where zero and negative
  multipliers are ordinary values an implementation must not replace with a
  division by a cumulative product, and `remaining_sum` as the inclusive
  suffix sum. **11.1.21** states `prospective_value` under
  `discount_kind="rate"` with both timings written out, so the convention a
  present value was taken on is readable from the artifact instead of
  inferred. Each clause names the forms it leaves outside itself, so a
  consumer knows where to refuse rather than guess. The four went out under a
  commit message that named the `list.get`, `to_integer`, `lookup` and
  `rollforward.state` clauses landing beside them and not these, and the
  format's own change log at section 14.1 carried lines for those and none
  for these; both now say so, and the change-log line sits where the clauses
  landed rather than at the end. Nothing a model computes changes and no
  digest moves: these are prose contracts over operations the vocabulary
  already held, and no tag, field or byte encoding is touched.

- **The specification defines the scenario run record, and states the domains
  the library already ran.** Section 13.2 of `spec/graph-artifact/v0-preview.md`
  defines the record `ScenarioRun.run(..., audit=...)` and
  `run_aggregated(..., audit=...)` write beside their output (`schema_version`
  "2.1"): every member, the library keys it shares with the calculation-graph
  audit file (not `imports`, not git), and that its `graph_fingerprint` and
  `graph_fingerprint_by_scenario` are calculation identities, not citations of
  a document. The specification no longer says the two timing conventions
  agree at constant rates, and its stated domains now cover what the library
  already did: per-period Boolean arithmetic, list-shaped text comparison and
  table keys declared as text. The conformance kit's identity reader now
  recomputes `formulas_fingerprint`.

- **An engine reads the artifact through a public module:
  `gaspatchio.engines.format`.** It publishes what a second engine needs
  to run a calculation-graph document: the formula node classes, the operation
  vocabulary, `op_node_from_json`, `inspect_execution`, `document_digest_of`,
  and the producer's own fingerprint grammar (`canonical_bytes`,
  `local_fingerprint`, `fingerprint`, `encode_text`, `encode_sequence`). A
  second engine then checks identity with the function that stamped it, not a
  re-implementation. The module is a preview tied to `SCHEMA_ID`
  (`gaspatchio-graph/v0-preview.3`): a name here changes only with a schema bump
  and a line in this changelog. It is not imported by `gaspatchio.engines`, so
  discovering an engine loads nothing new. The JAX engine now imports only
  `gaspatchio.engines.*` and the native extension, enforced by an allow-list.
  The JSON document and its specification remain the standard; an engine in
  another language needs none of this.

- **Reduce on the card: `run_aggregated(..., engine="jax")` folds a book on the
  JAX engine and hands back totals, never rows.** A reserve run over ten
  million policies is wanted as a handful of numbers, and the per-policy rows
  that make them are hundreds of gigabytes nobody reads. With `engine=` named,
  `run_aggregated` builds the model once over the book without computing it,
  hands the engine the executable artifact and the columns the frame arrived
  with -- exactly what `collect(engine=...)` hands it -- and your own
  aggregators, and the engine folds each batch as it is computed and lets it
  go before the next, never building the per-policy frame: a book of ten
  million policies comes back as its totals. What it holds at once is a batch
  of the columns it folds -- on a card, and the batch computing beside it
  (see *Changed*, item 3) -- beside the accumulators, so the book's size moves
  the time a fold takes and not its peak. With the batch pinned at 2,000, peak
  resident memory was 445, 449, 452 and 483 MiB at 2,000, 8,000, 24,000 and
  96,000 policies (level 4, on the Intel laptop on 2026-09-24, each in a fresh
  process, when a batch still returned every final-schema column: 46 KiB a
  policy), where the fold before it rode the stream reached 433, 716,
  1,453 and 2,845 MiB. `PeriodSum`, `PeriodCount`, `PeriodMin`, `PeriodMax`, `PeriodMean`, `PeriodVariance` and
  `PeriodStd` are reduced on the device, so what crosses back is one value per
  period; `Sum`, `Min`, `Max`, `Mean`, `Variance`, `Std`, `Quantile`, `Median`,
  `CTE` and `QuantileRank` bring back the one column they read, one value per
  policy, and fold it into the core's own accumulators. Each works with or
  without `.over(by)`, except `Quantile`, whose several levels
  `run_aggregated` refuses under `.over()` on either path. The answer is the
  same `AggregatedResult`, agreeing with the Polars fold under the
  specification's agreement rule -- the order floating-point additions
  were made in is the only permitted difference; on levels 4 and 5 the worst
  ratio is 4.8e-15 and counts are exact. The quantile family is the exception:
  `Quantile`, `Median`, `CTE` and `QuantileRank` fold into the core's DDSketch
  on both paths, so they agree within the sketch's accuracy (1e-4 by default)
  rather than to the agreement rule. They were identical on levels 4 and 5,
  but a value on a bucket's edge can move one by about twice that, and the
  result's record
  says so beside each. `engine=None`, the default, is the Polars path,
  unchanged.

  What the engine cannot fold it refuses in words before the book is read:
  `Count`, `ArgMin`, `ArgMax`, `.of()` and a multi-level quantile under
  `.over()` exactly as `run_aggregated` already refuses them, and the three
  per-period kinds that keep a sketch per period (`PeriodQuantile`,
  `PeriodMedian`, `PeriodCTE`), pointing you back to Polars. A partition
  column has to have arrived with the book. An engine that cannot aggregate at
  all is refused by name. `batch_size` becomes the engine's batch and `align`
  is the same guard; the audit record now names the engine, every version it
  ran under and the device it ran on, because totals without their rows are
  placeable only by what produced them, and `AggregatedResult.produced_by`
  carries the same.

  The file door folds too: `gspio run-artifact ARTIFACT BOOK --engine jax
  --aggregate SPEC.json` reads a JSON list of aggregators -- each one's
  canonical form beside its alias, with `"over"` to partition one -- and
  writes the audit record's JSON to `--results` (default `results.json`),
  whole or not at all: each alias's value, what each value is, the artifact's
  fingerprint, the book's stamp and the engine with its versions. An
  inception-aligned artifact is refused unless `--align duration`, as
  `run_aggregated`'s `align` refuses one. `parse_aggregations` reads the same
  `over` key, and refuses a malformed recipe with a `ValueError` naming what is
  wrong. An engine that folds implements
  `gaspatchio.engines.aggregation.AggregatingEngine`, an optional capability
  beside `Engine`, and reads the aggregation contract through the same door,
  which publishes the core's own result type, per-policy fold, refusals and
  closed-form kinds -- and not the Polars path's per-period fold, which an
  engine exists to do itself. The capability lives in that door rather than in
  `gaspatchio.engines.protocol`, because it answers the core's own result type
  and the engine protocol does not depend on model execution.

- **A sink takes any Arrow stream, not only a Polars frame.** The engine
  protocol's `Sink.write_batch` is typed against the new
  `gaspatchio.engines.protocol.ArrowStreamExportable`: anything with
  `__arrow_c_stream__` -- a `polars.DataFrame`, a `pyarrow.Table` or
  `RecordBatchReader`, or a batch built by an engine outside Python. Both
  sinks read it as a Polars frame by borrowing its buffers, not copying them.
  The JAX engine still hands Polars frames; nothing about its results
  changes. `EngineResult.columns` stays a `polars.DataFrame`, which is itself
  an Arrow stream. `pyarrow` is now `>=16`, the first release that reads the
  `string_view` columns Polars exports.

- **A sink is told where each batch's rows stand in the book, and keeps the
  book's order itself.** `Sink.write_batch(frame, *, rows=None)`: `rows` is
  the book positions of the batch's rows, counted from zero and ascending
  within the batch, and batches may arrive in any order. Both sinks put every
  row back where its policy stood when they publish -- `FrameSink` with one
  gather, `ParquetSink` a block at a time as it writes the file -- so an
  engine that computes a book in an order of its own can hand each batch
  over the moment it finishes. `None` keeps the old meaning, the book's next
  rows; a run uses one form throughout. At publication the positions must be
  the book's rows exactly once each. A position missing or held twice is a
  defect in the engine, not a refusal of the model: the sink removes
  everything it holds and raises `ValueError`, saying how many. A batch whose
  columns are not the first batch's is refused as it is written, with
  Polars' own `SchemaError` or `ShapeError`, the same from both sinks. A sink
  that has published, or been abandoned, is closed and takes no more batches
  until it is opened again, so nothing publishes twice or publishes what a
  failed run left behind; opening a file sink that is still open abandons it
  first. An error the merge's own source meets comes out as itself -- a key
  pressed as `KeyboardInterrupt` -- not as the `ComputeError` Polars wraps
  round anything its source raises; a full disk, which Polars' writer meets
  itself, comes out as the `ComputeError` Polars raises for it, naming the
  operating system's error. `write_with_manifest` takes `row_group_size=`.

- **`gaspatchio.__version__` says the installed version,** the same value
  `gspio --version` reports.

- **`af.filter` takes a condition written from the frame's columns.**
  `af.filter(af.status == "IF")` used to fail with Polars' "invalid
  predicate"; it now runs, and records the same selection step as
  `af.filter(pl.col("status") == "IF")`, one fingerprint for both spellings.
  `gspio diff`'s JSON report gains `source` -- the model file's own digests,
  where the two runs record different ones -- and the text report prints it on
  a line of its own under the headline; it is never counted as drift.

- **`.round()` with a negative `decimals` rounds to tens, hundreds and
  coarser, as a spreadsheet's `ROUND(x, -2)` does, on both engines and in the
  reference reader.** `af.sum_assured.round(-3)` bands to the thousand.
  A double is read as its fifteen significant figures and moved to the
  nearest multiple of `10**n` by the mode: 1234.5 to hundreds is 1200.0, and
  25.0 to tens is 20.0 to the even neighbour and 30.0 away from zero. A
  whole-number column is rounded exactly in whole numbers and keeps its type:
  25 to tens is 20 or 30, -25 away from zero is -30, and `2**53 + 13` away
  from zero is 9007199254741010, which a double would have made
  9007199254741000. An answer no `i64` holds -- `2**63 - 1` to tens -- is
  refused by name where 0.9.0 raised Python's own `OverflowError` at the
  line. The JAX engine, which refused the record by name, answers it, the same
  double on both engines past 22 places and past `10**37`; the reference
  reader rounds a whole number where it answered it unmoved. Past `10**308`
  no step is a double and every finite value answers a nought of its sign.
  The JAX engine's `round` of a value below the least normal double keeps its
  sign, `-0.0`, as the frame's does, where it answered `0.0`. Two sweeps of
  36,000 doubles within three units of a half, and 5,414 whole numbers near
  one, at one to six places left of the point and at both type limits,
  match Python's decimal arithmetic with no misses on either engine or in
  the reader, per policy and per period. The conformance kit gains nine
  cases (710 published).

- **The JAX engine answers `excel.pv` over a value held per period.** A rate,
  a period count or a payment held per period -- a PV taken down a column of
  periods -- is answered cell by cell, as the Polars engine and the reference
  reader already answered it: per-period operands paired period by period, a
  per-policy one read as that policy's value in every period, the
  near-nought `exp(-n·log1p(r))` form in each period, and two per-period
  operands of different lengths refused by name. The JAX engine refused it,
  naming Polars. §11.1.35 now states the per-period shape where it placed list
  operands outside the entry; on the JAX engine each period answers what the
  same operands answer per policy, to the bit. The conformance kit gains
  eleven cases (877 published).

### Breaking

- **A compiled rollforward's identity is the machine the file publishes, so
  an edited machine no longer replays under the old name.** An executable
  artifact carries the account-value machine in the
  `gaspatchio_rollforward_ir` facet, keyed by the compiled fingerprint, and
  that fingerprint was taken over Polars' rendering of each expression, which
  the file does not hold. A floor edited from 0.0 to a billion, or a charge
  read as a growth, resealed, kept every identity, passed `gspio validate
  --deep` and `verify`, and the JAX engine replayed 1,000,000,000.0 and
  101,101.0 for the fund pattern's 100,899.0. The compiled fingerprint is now
  the section 12.3 recipe-grammar hash of the published body, less its
  `schedule` (§12.1), so a reader recomputes it from the file; `validate
  --deep` reports a body that does not hash to its key, or a node whose
  movement summary disagrees with its body, as an error, and `run-artifact`
  refuses either. A compilation the file does not carry (every one, in the
  `audit` profile) is read as published and named in the deep report.
  `CompiledRollforward.canonical_form()` returns that body. No value moves;
  every compiled fingerprint and `rollforward:` id moves once, and with them
  the digests of every line reading one and the `graph_fingerprint` and
  `formulas_fingerprint` of every model holding one. `fingerprint_algorithm`
  is unchanged.

- **A per-policy grid's identity is its rule, so another policy's term no
  longer moves a model's `graph_fingerprint`.** On a per-policy axis -- a term
  column, or `until="maximum_age"` -- the schedule recorded the book's longest
  horizon as `n_periods`, and every line that reads the schedule (`t_years()`,
  `year_fractions()`, `period_dates()`, `anniversary_mask()`, a compiled
  rollforward) folded it into its digest. So correcting one policy's term, or
  running one policy alone, moved the figure of every other policy and `gspio
  diff` reported a calculation change with no number moved; and a batched
  `run_aggregated(audit=)` wrote `graph_fingerprint: null` for a model with no
  hole, at every batch size short of the whole book. The `per_policy_grid`
  recipe now states no `n_periods` (§11.1.37): its identity is the kind,
  cadence, calendar, start date, horizon kind and the column or age, and the
  figure is one across books, samples and batch sizes, while a change of the
  column, cadence or age still moves it. The longest horizon is a fact of the
  run, in `run_metadata.n_periods` as before. `Schedule.from_per_policy_grid`
  takes no `n_periods` argument and the grid's `n_periods` is `None`. No value
  moves; every per-policy-grid model's `graph_fingerprint` moves once (the
  level-4 and level-5 tutorials among the shipped ones), and
  `fingerprint_algorithm` is unchanged.

- **A NaN has no place in an order: one answer per operation, on both shapes
  and every engine.** 0/0 is NaN (§11.1.25) -- an in-the-money ratio over a
  nought guarantee is one -- and each operation over it answered by a rule of
  its own, different by shape and by engine. `[0.0, NaN, 0.2].list.min()`
  answered 0.0 on Polars and NaN on the JAX engine; per policy `NaN > 1.0` was
  1.0 (Polars orders NaN above every number) and per period 0.0, while the JAX
  engine and the reader refused the whole run, even a model whose guard sat in
  the unselected branch; `cut` filed a NaN in the lowest band on the JAX engine
  and the reader; the reader's `sign(NaN)` was 0.0 and its `min`/`max`
  depended on where the NaN stood. Now (§11.1.4, 11.1.12, 11.1.16-17,
  11.1.26-28): `min` and `max` over a run holding a NaN answer NaN; `sign(NaN)`
  is NaN; a comparison with a NaN operand stores a NaN indicator, a `when` over
  it answers NaN (null where its answer is text, a whole number or a date), and
  `&`, `|` and `~` over it have no truth value either (null where stored as a
  Boolean per policy); `cut` places a NaN in no band, a null; ±infinity is
  ordered as IEEE orders it on every side, where the JAX engine and the reader
  refused it. A Polars run holding a NaN moves; no shipped model does. The JAX
  engine refuses by name, as `comparison.unknown` or `cut.nan`, only the cells
  whose answer is a null, which it carries none of. A NaN `cut` placed in no
  band is skipped by a portfolio fold as any null is: test with `is_nan` first
  where it must count.

- **A per-policy `&`, `|` or `~` a NaN left without a truth value is a null
  flag wherever it is read, so a `when` over it answers its otherwise.**
  `when(flag & (ratio > 1.0)).then(1.0).otherwise(0.0)` with the ratio 0/0
  answered NaN on every side, while the same test stored first, `b = flag &
  (ratio > 1.0)`, then `when(b)`, answered 0.0; read inline, `is_null` was
  true on Polars and false on the kit's reader, and `== True` and `* 1.0`
  null on Polars and NaN on the reader and the JAX engine. A value does not
  change by being named (§11.1.27): the result is a Boolean, null there,
  stored or inline, and every reader reads that null -- a `when` selects its
  otherwise (a null element where the conditional is per period), an
  enclosing `&` or `|` uses three-valued logic (false AND it is false, where
  it was unknown before), `is_null` is true, `fill_null` fills it, `is_in`,
  a comparison and arithmetic answer null. The JAX engine answers the `when`
  and the enclosing `&`/`|` and refuses the rest by name
  (`comparison.unknown`), carrying no null. A per-period result is unchanged:
  its indicator stays NaN. A model that reads such a test inline moves where
  a NaN reaches it; no shipped model does. Nine kit cases; 894 published.

- **A left join refuses a policy whose key matches no row; `on_missing="null"`
  keeps today's null.** `af.join(products, on="prod")` with a book key
  `"Term20"` against a table holding `"TERM20"` gave that policy null
  parameters, and every total that skips nulls left it out without a word:
  1,460 where the hand total was 2,220, on every Polars door, while
  `Table.lookup` and the JAX engine refused the same data. A left join now
  refuses where it is written, naming how many policies missed, the first of
  them and its key, the line, and the two moves; a null key is a miss.
  `on_missing="null"` keeps the policy with null in every arriving column and
  says so on the record (§11.1.2's new `on_missing` attribute, written only
  then, so no existing record moves); fill it on the next line,
  `af.rate = af.rate.fill_null(0.0)`, for it to count. The JAX engine answers
  that model, publishes the null where the column is published as it stands,
  and refuses a formula or a fold that reads it unfilled. Inner, semi, anti,
  full and right joins keep their own meaning and take only `"raise"`. Every
  shipped tutorial's joins match every key.

- **A fixed-point `Decimal` is read as the number it denotes where it enters
  the frame, so `1000.00 / 12` is 83.333..., not 83.33, and results store
  `Float64`.** A book drawn from a database carries money as `Decimal(12, 2)`;
  kept in that type, a line answered at the decimal's own places: `prem / 12`
  was 83.33 and 0.00 for 1000.00 and 0.05, `prem / 12 * 12` came back 999.96,
  `prem * rate` kept three places (0.035 x 0.035 was 0.001), and
  `round_sig_figs` fell to the engine's own rounding (0.05 to two figures was
  0.06, 6.50 to one was 6). The record has no decimal type, so such a book had
  no record, no JAX run and no `verify`. A `Decimal` column -- a book column, a
  column a join brings, a table's answer column, a Series assigned as a column,
  or a `Decimal` written into a formula -- is now read where it enters as the
  `Float64` nearest each value, and one of no places as the `Int64` it is
  (kept wide and judged on its values past `i64`, as an `Int128` is), at the
  producer's door and the JAX engine's. Every line then answers as the same
  line over doubles, the book exports and runs on both engines, and the book's
  digest reads the double the value entered as. A value past fifteen or
  sixteen significant figures is read as its nearest double and loses the
  digits a double does not hold (9007199254740993 is 9007199254740992); none
  of 200,000 two-place money values below 10**11 lost one. Results that
  stored a decimal type store `Float64`, and 1.0's exact comparison and
  selection of two decimals, its refusal of a decimal under `round(-n)` and
  its keeping a run of decimals beside a written number in the decimal type
  are withdrawn with the type: no line meets a decimal. Reading the column
  costs 19.7 ms per 1,000,000 rows.

- **A numeric call that reads a number out of a duration is refused where it
  is written.** `af.term = af.maturity - af.issue` is a duration, and the
  vocabulary has no time-delta type (10). `af.term.sqrt()`, `cbrt`, `exp`,
  `log`, `log10` and `log1p` answered on 0.9.0 by reading the duration as a
  count of microseconds (the root of five years was 12563948.4), and `sign`,
  `round`, `floor`, `ceil`, `round_sig_figs`, `norm_cdf`, `cum_prod` and
  `projection.cumulative_survival` failed only when the frame ran, in
  Polars' words (`floor can only be used on numeric types`). Each is now
  refused at the line, per policy and per period, naming the duration and
  the count to write instead (`.polars_native().dt.total_days()`), as text
  and dates are. `abs`, `cum_sum`, `remaining_sum` and a run's `sum`,
  `mean`, `min` and `max` answer a duration and still do.

- **A `when` that reads a policy with no run answers null for that policy,
  wherever the run stands.** A null outer list in a branch was read as a
  null in each period: `when(af.in_force).then(af.gmdb).otherwise(af.av)`,
  with one policy's `gmdb` absent, answered that policy's `av` in the
  periods the condition did not select and nulls in those it did, and with
  a per-policy condition the answer turned on which branch held the run. A
  null outer list is a policy with no periods (11.1.18), so the line now
  answers null for it whenever any run in it is null -- in the condition,
  in either branch, selected or not, and in any level of a chain -- on both
  Polars engines, as the reference reader already answered (11.1.28). The
  JAX engine refuses a book carrying a null by name, as before. The
  walk-through a record carries, and every fingerprint, are unchanged.

- **A comparison on a per-policy table lookup, assigned as a column, stores
  the 0.0 or 1.0 indicator a comparison on a column stores.** `af.r =
  table.lookup(age=af.age) > 60` stored `True`/`False`, typed `bool` in the
  record, and the JAX engine followed it, while `af.r = af.age > 60` stores
  `1.0`/`0.0` typed `f64` (11.1.26) and the reference reader read both as
  the indicator, against a record that said otherwise. The lookup's test is
  now stored as the column's is: `Float64` on both Polars engines, `f64` in
  the record, and the JAX engine and the reader agree. A `MortalityTable.at`
  or curve read compared and stored moves the same way; a logical over such
  tests (`&`, `|`, `~`) stays a flag, as it does over columns, and the
  comparison used as a `when` condition or beside `&` is unchanged.

- **`fill_null` by a column fills each period one value at a time, and the
  numeric calls refuse a value that is not a number.** A per-period value
  filled by a per-period column took the fill's whole run where the policy
  had none and left a gap inside a present run untouched; it now fills the
  gap from the same period and leaves a policy with no run null, as a fill
  that is a value always did (11.1.13). `exp`, `log`, `sqrt`, `cbrt`,
  `abs`, `sign`, `round`, `floor`, `ceil`, `round_sig_figs`, `norm_cdf`,
  `cum_sum`, `cum_prod`, `sum`, `remaining_sum` and `cumulative_survival`
  over text, a date, a date and time or a time of day are refused where the
  line is written, naming the call: on 0.9.0 `af.code.exp()` read "2.0" as
  a number and "A" as a null, `af.issue.log()` took the logarithm of a day
  count, and the rest failed in Polars' words; `mean` of a run of text,
  which answered null, is refused too. A `UInt64` value past the signed
  64-bit range is refused by name under those calls, which answered it, and
  in a conditional's branch beside a narrower one.

- **A per-period sum, running sum or product, or remaining sum of whole
  numbers whose answer lies past the signed 64-bit range is refused by name
  rather than wrapped.** `[2**63 - 1, 1].list.sum()` answered `-2**63` on
  0.9.0, its `cum_sum` `[2**63 - 1, -2**63]`, and `cum_prod` of `[2**32,
  2**32]` answered `[2**32, 0]`, while the record said `i64`. The fold is
  exact now: the run stops naming the column and the fold where the total,
  or one period of a running fold, has no `i64` to be written in, as a
  total of the book (`run_aggregated`'s `Sum`) already did. A total that
  fits is answered, digit for digit, even where a running total on the way
  passed the range (`[2**63 - 1, 1, -1].list.sum()` is `2**63 - 1`). A run
  whose greatest value times its length is under `2**62` is checked by two
  reductions and folded as before.

- **A `Float32` or `Float16` column is read as a double where it enters the
  frame, so it is computed in the double the record names.** A book column
  and a column a join brings, or a list of one, arrive as `Float64`, as a
  narrow integer arrives as `Int64`. On 0.9.0 a single-precision column was
  computed in its four bytes while the record said `f64`:
  `qx.list.sum()` over `[0.001, 0.0015, 0.002]` answered
  0.0044999998062849045 where the reader and the same book in doubles answer
  0.00450000015553087, `cumulative_survival`, `exp`, `cbrt`, `/` and `**`
  likewise, and `-3e38 * 1.5` overflowed to minus infinity; nothing said so.
  The JAX engine refused such a book ("cast 'qx' to list[f64]") and now reads
  it the same way. The widening is exact, so the book's digest and every
  fingerprint are unchanged; the answers move to the double ones, and a
  results file stores `Float64` where it stored `Float32`.

- **`gspio calc-graph` writes the calculation-graph artifact,
  `gaspatchio-graph/v0-preview.3`, where 0.9.0 wrote an unversioned graph
  JSON.** The artifact is a published format -- a JSON Schema, a
  specification (`spec/graph-artifact/v0-preview.md`) and a conformance kit,
  whose corpus carries the graph fingerprint
  `sha256:20882cdb67b31e9dd707eaa518b99cde4c5a51499bcc18dbd049dcf9e3e675ed`
  -- and it is a preview. Its schema identifier and the byte grammar its
  digests are taken under, `fingerprint_algorithm` `gspv0-preview-3`, may
  move in a 1.x release, and each move is recorded in the specification's
  change log (section 14.1) and here. They already moved while this release
  was built: the grammar twice, for a date literal and for a negative zero,
  and the schema once, for the policy axis. The entries below that name
  `v0-preview.2` or `gspv0-preview-2` describe those steps; no release
  carried either. Two artifacts carrying different tokens must not be
  compared -- not compared with care, not compared -- so `gspio diff`
  refuses the pair rather than reporting on it, and an answer comes from
  re-deriving both from the model source under one grammar. Nothing about
  how a model is written changed: every model that compiles today compiles
  unchanged, and these are changes to the record of a calculation rather
  than to any calculation.

- **`CalculationGraph` is replaced by `CalcGraph`.** The graph is folded from
  the calculation record in a single pass (`fold(af)`) rather than assembled
  by `add_input_column`/`add_computed_operation`, and it mints one node per
  definition instead of one per column name. A model that writes
  `af.policies_in_force` before the maturity test and again after it now has
  two nodes — `policies_in_force@1` and `policies_in_force@2` — and every
  column reference binds to whichever definition was live when it was
  written, so a self-reference is an ordinary edge between two nodes rather
  than a cycle. `find_roots()`, `find_leaves()`, `get_dependencies()` and
  `get_dependents()` are gone; ask `af.graph` instead. The exported graph
  is the artifact the first entry here describes: node ids are versioned
  (`death_claims@1`), a column the model cannot account for is a node of
  kind `hole`, and every node states the ids it `reads` and whether it is
  `in_final_schema`, what the frame's column ends up holding.

- **The calculation-graph export refuses a column of a type the artifact has
  no name for.** The artifact names types in its own vocabulary -- `bool`,
  `i64`, `f64`, `str`, `date`, `datetime` and lists of those -- where 0.9.0
  wrote Polars' display string, lowercased. A model whose finished frame
  holds a duration, a time, a decimal, binary, a categorical or an enum, a
  struct, a fixed-width array, an all-null column, a list nested deeper than
  three levels, or an unsigned or 128-bit integer holding a value past
  `i64`, now stops `gspio calc-graph` and `GraphExporter.export()` with a
  sentence naming the column and the conversion that fixes it -- for a
  categorical, `.to_text()`; for a duration, a count in a unit the model
  states. Running the model is unaffected, and so is a column the model drops
  before it finishes.

- **A column written twice keeps its first definition's values until the
  collect, by default.** So that an export can say what a column held before
  a later line replaced it, the replaced definition's output rides the same
  collect under a hidden name, and `collect()` takes it off the frame it
  hands back. That costs memory while the plan runs: about 43 MB for each
  retained per-period column at 100,000 policies, and 616 MB more at peak
  for ten. `ActuarialFrame(..., retain_superseded=False)` declines it:
  nothing extra is planned or held, and the export then carries a replaced
  definition's formula without its values.

- **A content hash is now taken over the values, not over an engine's file
  format.** The stamp on an assumption table, on a join's right-hand side
  and on an injected column used to be a SHA-256 of the bytes Polars' own
  parquet writer produced. Two things were wrong with that. A Polars
  upgrade that laid a file out differently moved every content stamp in the
  audit chain at once, with no data behind the movement — and a drift alarm
  that fires on a dependency upgrade is an alarm a reader learns to ignore.
  And nobody without that exact writer could reproduce a stamp, so a
  reviewer holding the values could not check the claim made about them.
  The bytes are now the framework's own published grammar
  (`spec/graph-artifact/v0-preview.md` section 12.3, worked example and
  digest included): a count of columns, then per column its name, one tag
  for the type, a count of rows, and every value's bytes behind a marker
  saying whether the value is there at all. **Every table, join and
  `source_sha` stamp moves once, here.** Compare stamps taken since this
  release against each other, not against one from before it. Two
  consequences are deliberate. Storage width is not content: an `Int32` and
  an `Int64` column holding the same numbers now stamp alike, and so do a
  `Float32` and a `Float64` — where narrowing actually rounded a number the
  number moves and the stamp moves with it, which is the movement worth
  seeing. And a column whose type the artifact's vocabulary cannot name
  stops the stamp with the refusal that names the column, the type and the
  cast, rather than hashing something nobody can read back.

- **A period method refuses a column with one value per policy on a frame
  with a projection timeline, where 0.9.0 ran it down the rows -- across the
  policies.** `cumulative_survival`, `previous_period`, `next_period` and
  `at_period` were documented to work down the rows on a scalar column, which
  is right on a frame whose rows are periods. On a projected frame the rows
  are policies, so a rate looked up by issue age where attained age was meant
  gave each policy the cumulative product of the policies above it, and its
  `previous_period()` the previous policy's value. With rates 0.1, 0.2 and 0.3
  on three policies, policy 2's survival read 0.9 in the full run, 1.0 when
  run on its own and 0.7 with the model points reversed, and nothing said so.
  These methods now refuse such a column on the line that asked, naming the
  two ways to give it periods. **Look the column up with a per-period key
  (`af.issue_age + af.month // 12`), or repeat a per-policy value across the
  timeline with `.projection.broadcast_to_periods()`.** A frame without a
  timeline keeps the documented behaviour: its rows are periods and the
  methods run down them, grouped with `.over()`. `remaining_sum` and
  `prospective_value`, which have no down-the-rows form, refuse a per-policy
  column the same way instead of failing inside the query plan, and
  `projection.set()` names a missing `until_value` column, with the columns
  the frame does have, instead of a query-plan dump. None of the tutorial
  models uses the refused form.

- **A Polars row operation over a per-period column is refused when it is
  assigned to a frame with a projection timeline, where 0.9.0 ran it across
  the policies.** The same rule as the period methods above, read the other
  way round: there a period method needs a per-period column, here a row
  operation needs a per-policy one. `af.prev = pl.col("reserve").shift(1)`
  handed each policy the previous policy's whole timeline, and
  `pl.col("reserve").forward_fill()`, `.reverse()`, `.first()` or
  `.fill_null(strategy="mean")` likewise read the neighbouring policies --
  all of them the right shape, with no error. The assignment (and
  `with_columns`) now refuses a plain Polars expression that applies a row
  operation -- `shift`, `diff`, the fills, `interpolate`, `cum_*`,
  `pct_change`, the rolling and `ewm_*` windows, `rank`, `reverse`, a sort,
  `gather`, `slice`, `filter`, `cumulative_eval`, an aggregation -- to a
  column that is per-period, or whose shape cannot be resolved, naming the
  per-period form: **`.list.eval(pl.element().shift(1))`, or the declared
  operation on the column (`af.reserve.projection.previous_period()`,
  `af.cashflow.cum_sum()`).** A row operation over a per-policy column is
  portfolio work and runs as before; so does every row operation on a frame
  without a timeline, whose rows are periods. `af.<column>.polars_native()`
  stays the explicit escape, with its own refusals. The same holds for a
  plain Polars fragment used as an operand inside a framework formula --
  `af.x * pl.col("reserve").shift(1)`, `when(...).then(pl.col("reserve")
  .shift(1))` -- which entered as engine text no different from the
  escape's: the operand door now marks such a fragment as the author's raw
  Polars, and the assignment reads it as it reads the fragment on its own.
  A method chained on a column or on an expression the framework hands back
  already answers this way (see *Fixed*).

- **A producer's expression refuses `sum`, `mean`, `min`, `max` and the other
  Polars names that read the rows, as the column it would become does, where
  0.9.0 ran them across the model points.** `table.lookup(age=af.age)` is a
  Polars expression, so `.sum()` on it was Polars' own: on a projected frame
  every policy got the total of the whole book's rates -- 0.06 for a policy
  whose own rate is 0.01 in a book of three, 0.01 run alone -- with nothing to
  say so, while the same formula over two lines, `af.q = ...` then
  `af.q.sum()`, was refused. A lookup, `MortalityTable.at`, a curve or a
  rollforward read bound to a frame now answers the folds (`sum`, `mean`,
  `min`, `max`, `median`, `first`, `last`, `len`, `count`), the running
  forms (`cum_max`, `cum_min`, `rolling_*`, `ewm_*`, `pct_change`), the orders
  (`sort`, `rank`, `reverse`) and the selections (`filter`, `head`, `tail`,
  `gather`, `slice`) as a column does: refused, naming the door. **For one
  policy's own periods write `.list.sum()` on a per-period value; for a
  figure across the model points on purpose, write `.polars_native().sum()`.**
  An expression with no frame in sight -- a lookup keyed only by literals, a
  `Schedule.*_expr` read -- keeps Polars' meaning, as `pl.col` does. None of
  the tutorial models, skills or docs uses the refused form. **The same rule
  now reads every Polars name whose answer moves with the rest of the file**,
  measured name by name: a statistic of the column (`std`, `var`,
  `quantile`, `product`, `skew`, `kurtosis`, `entropy`, `mode`,
  `approx_n_unique`, `null_count`, `any`, `all`), a comparison of one row
  with the rest (`is_unique`, `is_duplicated`, `is_sorted`, `index_of`), a
  position (`arg_min`, `arg_sort`, `max_by`) and a pick or reshape of the rows
  (`unique`, `sample`, `shuffle`, `top_k`, `bottom_k`, `qcut`, `drop_nulls`,
  `explode`). On a producer's per-policy expression each is refused at the
  method, as on the column; a plain Polars expression over a per-period
  column on a projected frame is refused at the assignment, where it used to
  hand policy 1 another policy's timeline (`shuffle`, `unique`, `mode`,
  `max_by`) or fail later at `collect()` with Polars' own dtype error or a
  panic. A frame without a timeline, a per-policy column, the same method
  inside one policy's own list (`.list.eval(...)`) and `.polars_native()` are
  unchanged.

- **A read across rows is refused wherever the frame is not the whole book,
  where 0.9.0 answered from whichever rows shared the run.** A `sum`, `mean`,
  `rank`, `cum_sum`, `rolling_*`, `pct_change`, an `over` window or `pl.len()`
  written through `.polars_native()` or raw `pl.col` answers from the rows in
  the frame: in a batch runner, the batch; on a scenario axis, every
  scenario. An expense of 1,000,000 allocated by share of sum assured,
  `af.sa / af.sa.polars_native().sum() * 1_000_000`, came back as 1,000,000
  from `collect()`, 3,000,000 from `run_aggregated` at `batch_size=3`,
  8,000,000 at `batch_size=1`, and 500,000 a scenario from a two-scenario
  `ScenarioRun` at any batch size above one -- and `batch_size="auto"` sizes
  batches from the machine's memory, so two laptops could return two totals.
  The assignment is now refused, naming the read, in `run_aggregated` and
  `run_to_parquet` wherever they cut the book into more than one batch
  (`"auto"` included), in every `ScenarioRun` and `for_each_scenario`, and on
  a frame crossed with `with_scenarios` after the cross-join. **Compute a
  figure across the book before the run, as a model-point column the model
  reads, or run the book in one batch.** Where the frame is the book --
  `collect()` without a scenario axis, a runner whose one batch holds every
  policy -- the read runs as before. A fold inside `list.eval(...)` reads one
  policy's own periods and is not a read across rows. **On a scenario axis
  whose policies are not cut into batches** -- every scenario plan, and a
  frame crossed with `with_scenarios` outside a batch runner -- a read
  inside a window whose partition includes the scenario,
  `pl.col("sa").sum().over("scenario_id")` or `.over(["scenario_id",
  "product"])`, answers from one scenario's own copy of the book and runs: the
  allocation totals 1,000,000 in every scenario at every number of scenarios
  per batch, or 1,000,000 a product. Any other read stays refused there, even
  at one scenario per batch, and its refusal names that form; with the
  policies cut into batches the partitioned read is the batch's too, and is
  refused.

- **`with_columns` and `select` refuse an unnamed calculation that would
  overwrite the column it reads, where 0.9.0 wrote over that column
  silently.** Polars names an expression with no alias after the first
  column it reads, so `af.with_columns(table.lookup(age=af.age))` wrote the
  rate over `age`: every later `af.age` read the rate, nothing raised, and
  the record filed `age` as a calculation reading the table. The frame now
  refuses such a line and names the column it would have replaced. **Name the
  column: `af.q = table.lookup(age=af.age)`, or `.alias("q")` inside
  `with_columns`, or a keyword in `select`.** Replacing the column on purpose
  is still one word away -- `af["age"] = ...` or `.alias("age")` -- and a
  column handed back as it stands (`pl.col("age")`, or cast to the type it
  already has) passes as before. That includes an in-place cast to another
  type, `select(pl.col("term").cast(pl.Float64))`, which now needs
  `.alias("term")`. None of the tutorial models, skills or docs uses the
  refused form.

- **`select` takes one expression per column.** `af.select(pl.col("a", "b")
  * 2)` ran in 0.9.0 as two calculations under one expression, and
  `af.select(pl.all().name.suffix("_out"))` as a copy of every column under a
  new name, and nothing recorded any of them. `select` now records each column it calculates, as
  `with_columns` does, and one expression that computes several columns is
  refused, naming them: write `af.select((pl.col("a") * 2).alias("a"),
  (pl.col("b") * 2).alias("b"))`, one expression for each, and each is
  recorded at the select's line.

- **`af.projection.set()` stamps the timeline on the frame you call it on**
  and hands that same frame back. At 0.9.0 it built a new frame and returned
  that. The idiom does not change — `af = af.projection.set(...)` — and the
  reason for the change is what a replacement frame cost: it started with no
  record of anything Phase 1 calculated, so every setup column was silently
  relabelled a field the model points supplied. What does change is that
  there is no "before" frame to keep. A reference held across the call now
  points at the projected frame, and two calls on one frame are not a
  monthly timeline and an annual one — the second re-projects the first. To
  project the same model points two ways, build two frames and set a
  timeline on each.

- **`af.finance.discount_factor(...)` likewise adds its column to the frame
  you called it on** rather than to a fresh one. The new frame it used to
  return had dropped the calculation record, the projection axis and the run
  mode — so the discount factors arrived having erased the history of the
  rates they discount. The call reads exactly as before; the frame handed
  back is the one passed in.

- **`af.date.create_timeline()` and `af.date.add_duration()` stamp the frame
  in place.** Both used to build a replacement frame and hand that back,
  which made them the two odd verbs in the accessor surface:
  `projection.set`, `rename`, `join` and `filter` have always changed the
  frame you called them on. They now do the same — the timeline explode
  changes the row count on that frame, and the offset column lands on it —
  and the same frame comes back, so `af = af.date.add_duration(...)` and a
  bare `af.date.add_duration(...)` are one and the same statement. If you
  were keeping the return value as a *second* frame alongside the original,
  that frame no longer exists: build two frames from the model points and
  put one timeline on each. Nothing changes for the ordinary rebinding
  style, and nothing changes for the calculation record, which stayed with
  the frame either way.

- **`projection.set()` refuses the two argument forms together.** Passing
  `start_date`/`n_periods` alongside `valuation_date`/`until`/`until_value`
  built the calendar grid and never read the valuation date, while the
  projection record echoed every keyword that was passed — so the run laid
  a fixed grid and described itself as policy-anchored, and an author who
  meant each policy to run to its own horizon got a uniform one with no
  word about it. The two forms describe different axes and the framework
  cannot know which was meant, so the call is refused, naming the arguments
  it was given from each form. Pass one: `start_date`/`n_periods` lays a
  calendar grid from a start date; `valuation_date`/`until`/`until_value`
  runs each policy from the valuation date to its own horizon.

- **`af.finance.discount_factor` checks its two input column names at the
  call.** `rate_col` and `periods_col` are given as strings and went
  straight into the query plan, so a typo came back as a resolved Polars
  plan — `unable to find column "period"`, with a projection listing under
  it — naming neither the parameter that carried the name nor, unless the
  engine's own matcher happened to find one, the column that was meant.
  Both now go through the check `present_value` next door already reads by:
  `discount_factor(rate_col="rate", …)` on a frame holding `rates` is
  refused with `rate_col='rate' names a column this frame does not carry.
  Did you mean 'rates'?`. `output_col` is unchanged — it names the column
  being written rather than one being read, so it is the caller's to choose
  and a name the frame already carries is still overwritten.

- **`until="maximum_age"` runs each policy to its own age, where 0.9.0 ran
  every policy on one grid sized from the youngest life in the frame.** An
  older life was projected past the age asked for, and its value moved with
  its neighbours: a 70-year-old's annuity-due of 1,000 a year to age 100 was
  worth 17,028.46 alone -- the hand value -- and 17,778.09 beside a
  50-year-old, whose grid ran it to 120; `run_aggregated` returned 41,127.79
  at `batch_size=1` and 41,877.42 at `batch_size=2`. Each policy now runs
  `until_value` less its own issue age, in whole years at the schedule's
  frequency, for a number, a column name or an expression `until_value`, so
  the 70-year-old is worth 17,028.46 beside anyone and the total is 41,127.79
  at every batch size. The timeline is jagged, as a `term_months` column's
  is; the schedule's recipe states the age and the issue-age column, and the
  `projection_set` record names `issue_age_column`, so the JAX engine now
  lays a `maximum_age` axis it used to refuse (an age written as an
  expression is still refused there, by name). A mortality table need only
  reach `until_value`. Values and digests move for every `maximum_age`
  model, to their hand values; none of the tutorials uses one.
  `per_policy=False` keeps the one shared grid of 0.9.0, refused where the
  frame is not the whole book (below).

- **`until="maximum_age"` at a weekly or daily frequency is refused, as
  `term_months` and `term_years` already were, where 0.9.0 laid one shared
  grid of 52 or 365 periods a year.** A maximum age runs each policy a whole
  number of years, the age less its issue age, and a number of years is not a
  whole number of weeks or days (52 a year against the calendar's 52.18): two
  lives aged 98 and 99 to age 100 both got 105 weekly boundaries. The call
  now refuses in the term horizons' sentence, naming the month-aligned
  frequencies. **Use a monthly, quarterly, semi-annual or annual frequency.**

- **A projection horizon or count that is not a whole number is refused, not
  truncated.** A decimal `term_years` column was cut to whole years before it
  was multiplied out: `[2.5, 0.75, 1.0]` years at monthly cadence projected
  `[24, 0, 12]` periods, so the 0.75-year policy projected nowhere, with no
  word; a decimal `term_months` or `maximum_age` was cut the same way, a text
  column was read as numbers, `until_value=True` or `n_periods=True` was read
  as 1, and a decimal literal failed with `'float' object has no attribute
  'max'`. §11.1.1 takes a whole term and a whole attained age. Now a whole
  number held in any numeric kind (`2.0`, a `Decimal`, a Float64 column of
  whole values) is that number; a value that is not whole is refused, naming
  it and what it would have been cut to; text and flags are refused by kind.
  `n_periods` and `steps_per_year` follow the same rule. **Round a term the
  way you mean in the model, or write a term with months in it as
  `until="term_months"`.**

- **`until="next_anniversary"` and `projection.set(inception_column=)` are
  removed.** `next_anniversary` laid `until_value` whole years from the
  valuation date for every policy -- `term_years`'s count, `k × p` periods --
  while its name promised each policy's own contract anniversary: three
  policies whose anniversaries fell 5.42, 1.02 and 11.96 months away all ran
  13 monthly boundaries, and `next_anniversary 1` and `term_years 1` gave the
  same numbers under two fingerprints. `inception_column=` was accepted and
  never read, and a column that did not exist ran. `until="next_anniversary"`
  is now refused by name, on the producer and the JAX engine, and §11.1.1 no
  longer lists it; `inception_column=` is no longer a keyword of
  `projection.set` (`Schedule.from_inception(inception_column=)` is
  unchanged). **For k whole years write `until="term_years",
  until_value=k`, the same count; for a horizon on each policy's
  anniversaries lay the axis with `Schedule.from_inception(...)` and read
  renewals with `af.projection.anniversary_mask()`.**

- **A shared projection grid sized from the rows is refused wherever the
  frame is not the whole book, where 0.9.0 sized it from whichever rows
  shared the run.** `projection.set(..., per_policy=False)` over a maximum
  age lays every policy's axis to the youngest life in the frame; over a
  term column or a term expression, to the longest horizon in the frame. That length is a read across rows: a
  70-year-old's annuity-due of 1,000 a year to age 100 on a grid shared with
  a 50-year-old was 17,778.09 (run on to age 120), so `run_aggregated`
  returned 41,877.42 at `batch_size=2` and 41,127.79 at `batch_size=1`; a
  5-year term beside a 10-year one was 11,000 against 6,000 alone. The call
  is now refused, naming the grid, what in the rows sizes it, and the routes,
  exactly where a read across rows is: in `run_aggregated` and
  `run_to_parquet` wherever they cut the book into more than one batch, in
  every scenario plan, and on a frame crossed with `with_scenarios`. **Leave
  `per_policy` at its default, which runs each policy to its own horizon;
  or take the length over the book before the run and state it as a number;
  or run the book in one batch.** `collect()` and a one-batch run keep the
  shared grid, and so does a grid laid before the scenario cross-join.

- **Arithmetic on a `UInt64`, `Int128` or `UInt128` column holding a value
  past the signed 64-bit range is refused, where 0.9.0 wrapped it; one whose
  values all fit is read as `Int64`.** The record names every integer `i64`,
  and the frame computed in the width the data arrived in: a `UInt64` policy
  number of 7 less 10 was 18,446,744,073,709,551,613, a list's length less one
  on an empty row was 18,446,744,073,709,551,615, and `run_aggregated` summed
  the wrapped values to a total that moved with `batch_size`. One rule now
  holds where the book enters the frame, a column a `join` brings included: a
  column whose every value fits an `i64` is read as `Int64` (7 - 10 is -3),
  and one holding a value outside keeps the width it arrived in, so
  `to_text()` still writes that value by its digits and `to_integer()` still
  refuses it. Arithmetic on a column still that wide -- any operator, either
  side, per policy or per period, a column the model computed through
  `.polars_native()` included -- is refused by name when the frame runs, never
  wrapped. A book handed over as a `LazyFrame` keeps such a column's width,
  and arithmetic reads it as `Int64` where its values fit and refuses where
  one does not. `run_aggregated` and `run_to_parquet` judge the column over
  the whole book, so every batch reads it in one width. **Keep an identifier
  as text -- `af.pid.to_text()` -- or choose the narrower type a quantity is
  carried in and state it on the model points before the run.** A results file
  carries `Int64` where it carried `UInt64` for such a column, and a book
  whose wide column fits now digests as the `i64` book it is read as, so
  `gspio run-model` writes its manifest where it wrote none.

- **An integer literal outside the signed 64-bit range is refused where it is
  written into a formula, where 0.9.0 answered null.** Every integer in the
  record is an `i64`, a literal as much as a column, and the engine gave such
  a literal no number either: `af.pid == 2**64 - 1` answered null for every
  policy of an `Int64` column, `af.pid + 2**64` a null, `when(...).then(2**64)`
  an `Int128` column the record has no name for, and the record carried a
  number no consumer reads. The literal -- an operand of any operator, a
  member of an `is_in` or `replace` sequence, a `clip` bound, a `fill_null`
  value, and a call's setting such as `round(decimals=...)` or
  `projection.at_period(...)` -- now raises a `ValueError` at the line,
  naming it. **Compare an identifier as text --
  `af.pid.to_text() == "18446744073709551615"` -- or write a quantity as a
  decimal literal, `1.8446744073709552e19`.** A literal at either end of the
  range is unchanged, and a raw Polars predicate keeps Polars' meaning. The
  JAX engine, which already refused such a literal in a document, now names
  the same two moves under section 10.

- **`2 ** af.n` over an integer column answers `Int64`, where 0.9.0 answered
  `Int32` and wrapped.** Polars gives a bare integer literal no width of its
  own and takes a power's type from its base, so `2 ** af.n` was an `Int32`
  and 2 ** 40 came out as 0, while the record named the column `i64` and the
  JAX engine answered 1,099,511,627,776. A whole-number base is now read as
  the `Int64` the record names, so the two engines agree (`2 ** 40` is
  1,099,511,627,776, `(-2) ** 3` is -8); a results file carries `Int64` where
  it carried `Int32` for such a column.

- **A whole number written into a formula is an `Int64` wherever it sets a
  column's type, where 0.9.0 stored an `Int32` and wrapped past 2,147,483,647
  without a word.** Polars gives a bare integer literal no width of its own,
  and where nothing beside it set the type it settled on `Int32`: `af.c = 5`
  stored an `Int32` column, `when(af.x > 2).then(70000).otherwise(0)` answered
  one per policy and per period alike, and `* 70000` downstream answered
  605,032,704 where the hand value is 4,900,000,000 -- while the record named
  the column `i64` and the JAX engine, replaying it, answered 4,900,000,000.
  Every whole number the frame turns into a literal is now stated as an
  `Int64`: an operand, a `when` branch, a fill, a constant assigned as a
  column, a NumPy integer such as `numpy.int32(5)`, and an integer `Series` or
  NumPy array handed in as a column, which is read as a book column is. Beside
  a decimal it still widens to the decimal, and beside an `Int64` column
  nothing changes. A results file carries `Int64` where it carried `Int32` for
  such a column, and an error panel's operation line shows `(5)` where it
  showed `(dyn int: 5)`. A raw Polars literal the author builds --
  `pl.lit(5)` -- keeps Polars' own type.

- **`run_aggregated`'s `Sum` of an integer column totals it exactly, and a
  total past the signed 64-bit range is refused by name, where 0.9.0 wrapped it
  by batch.** Each batch of an `Int64` column was summed in `Int64`, so
  2**62, 2**62 and 5 answered 9.2e18 one policy a batch and -9.2e18 two or
  three a batch, and 2**62, 2**62 and -2**62, whose total 2**62 fits,
  answered -1.38e19 two a batch; a scenario plan's `within="sum"` wrapped
  each scenario's total the same way. The JAX engine folds a per-policy `Sum`
  through the same fold and answered the same wrong numbers. A batch of whole
  numbers is now summed exactly and the total carried exactly across
  batches and scenarios: one that fits answers the double nearest it at
  every batch size, on both engines, and one outside the range raises a
  `ValueError` naming the column, the exact total and, within a scenario,
  the scenario. **Carry a quantity as a decimal before it is summed --
  `af.x * 1.0` -- or rescale it to a unit whose total fits.** A decimal
  column's `Sum` is unchanged.

- **`PeriodSum` of an integer column totals each period exactly, and a
  period's total past the signed 64-bit range is refused by name, where 0.9.0
  wrapped it by batch.** Each batch's periods of a `list[i64]` column were
  summed in `Int64` and carried across batches as doubles, so 2**62, 2**62
  and 5 answered 9.2e18 at every period one policy a batch and -9.2e18 two or
  three a batch; 2**62, 2**62 and -2**62, whose total 2**62 fits, answered
  -1.38e19 two a batch; and 2**53, 1 and 1 answered 9,007,199,254,740,992 one
  a batch where the total 9,007,199,254,740,994 is a double. On the scenario
  axis each scenario's per-period total wrapped the same way under every
  per-period aggregator (`PeriodMean`, `PeriodMax`, `PeriodMedian` and the
  rest read those totals). The JAX engine totalled the periods on the device
  in one `int64` and answered the same wrong numbers. Each period is now
  totalled exactly and carried exactly across batches and scenarios, on both
  engines: a total that fits answers the double nearest it at every batch
  size, and one outside the range raises a `ValueError` naming the column,
  the exact total, the period and, within a scenario, the scenario. **Carry
  a quantity as a decimal before it is summed -- `af.x * 1.0` -- or rescale
  it.** A decimal column's `PeriodSum` is unchanged.

- **`Mean`, `Variance`, `Std`, `PeriodMean`, `PeriodVariance` and `PeriodStd`
  of an integer column answer the double nearest their exact value at every
  `batch_size`, on both axes and both engines, where 0.9.0 wrapped or moved
  them by batch.** `PeriodMean` totalled each batch's periods of a `list[i64]`
  column in `Int64`, so 2**62 and 2**62 averaged 4.6e18 one policy a batch
  and -4.6e18 two a batch, and 2**63 - 1, 2**63 - 2 and 2**63 - 3 averaged
  3.07e18 two a batch. The other four folded whole numbers as doubles:
  2**63 - 1, -2**63 and 5 averaged 1.67 where the mean is 4/3 (0.0 under
  `"auto"`); 2**63 - 1, 2**63 - 2 and 2**63 - 3 had a variance of 0.0 where
  it is 1; and 2**53 + 1, 2**53 + 2, 2**53 + 3 and 2**53 + 5, whose variance
  is 35/12, answered 5.22, 6.67 or 3.67 by batch. The JAX engine answered the same numbers. Each now
  carries the exact count, total and, for a spread, total of squares, and
  reads its answer once from them: a mean is the double nearest the exact
  total over the count, a variance the double nearest the exact ratio, and a
  standard deviation that ratio's root rounded once. A mean of whole numbers
  always fits, so none is refused. A decimal column's figures are unchanged,
  and a whole number folded beside a decimal is read as a double from then on,
  as before.

- **A per-period conditional answers its branches' type, a `None` branch
  takes the other branch's, and a whole number past 2**53 keeps every bit,
  where 0.9.0 answered doubles.** `when(af.month > 0).then(None).otherwise(
  af.k)` over a `list[i64]` run answered `list[f64]` and held 2**53 where the
  run held 2**53 + 1, and the record said `list[f64]`; a flag run beside a
  `None` came back as 0.0 and 1.0, a date run as day counts, and a text run
  was refused by the selection kernel. Each now answers the other branch's
  type: `list[i64]`, `list[bool]`, `list[date]`, `list[str]`. The same kernel
  selected two integer branches in doubles and typed the answer back, so
  `when(af.month > 0).then(0).otherwise(af.k)` held 2**53 where the JAX
  engine held 2**53 + 1, and a branch holding 2**63 - 1 failed to collect; a
  pair of 64-bit whole numbers is now selected on each value's high and low
  32 bits, which a double holds exactly, and joined, so the two engines agree.
  Two date branches answer dates, not day counts. A pair written only as
  literals a double holds (`.then(1).otherwise(0)`) is selected once, as
  before; one reading a 64-bit run costs a second pass of the kernel. A
  `None` branch still reaches the record as an engine-native fragment, which
  the JAX engine refuses by name. The per-policy form of each line already
  answered so.

- **A per-period conditional of two dates and times answers a date and time
  in their unit and zone, every bit of it, where 0.9.0 answered doubles.**
  `when(af.m > 0).then(af.t).otherwise(af.o)` over two `list[datetime]` runs
  answered `list[f64]` counts of the runs' unit, so a nanosecond count lost
  its last digits and the record said `list[f64]`; a `None` beside such a run
  did the same. Each now answers the runs' own `Datetime`, unit and zone kept,
  and the record says `list[datetime]`. The JAX engine carries no date and
  time: it refuses such a book column by its type, where it told the author
  to cast the column to the type it already was. The same selection answered
  a duration and a time of day as doubles, a decimal pair as doubles, a
  Categorical or Enum pair as plain text, and two `None` branches as
  `list[f64]`; each now answers the type the per-policy form of the line
  answers -- two `None` branches a null of no type, which the record refuses
  by name. A 128-bit whole number was selected on two 32-bit halves and kept
  its bits only below 2**85, and an unsigned one made the selection kernel
  panic; every value is now selected as the whole number it is held as, 32
  bits at a time, and joined. A zone-naive date and time beside a zoned one,
  or a Categorical beside an Enum, is refused by name where the line is
  written, on both routes, where the per-policy form failed only when the
  frame ran and the per-period form answered; an unsigned value past `i64`
  beside an `i64` run fails by its value, as the per-policy form does, where
  the per-period form answered a null. A per-period conditional reading a
  date-and-time or duration run costs a second pass of the kernel.

- **A conditional of two time units answers the finer unit, every digit of
  both, where 0.9.0 answered the coarser.** `when(af.x > 2).then(af.us)
  .otherwise(af.ms)` over a microsecond and a millisecond date and time
  answered milliseconds, so 2025-01-01 00:00:00.627779 came back as .627, and
  a Python `datetime` literal (held in microseconds) beside a nanosecond
  column dropped the column's last three digits; two durations did the same.
  It was Polars' common type for the pair, on both routes, and nothing said
  so. Both branches are now read in the finer unit, into which every value
  of the coarser converts exactly, per policy and per period, a chain of
  three units included. A value the finer unit cannot hold -- a nanosecond
  count reaches only the years 1677 to 2262, so an open-ended 9999-12-31
  beside a nanosecond column is one -- refuses the run by name, naming the
  column where a column holds it, rather than becoming a null; a model that
  wrote such a pair and ran on 0.9.0 now refuses there.

- **A flag beside a whole number in a conditional answers a double on both
  routes and both engines, where 0.9.0 answered a whole number per policy.**
  `when(af.x > 2).then(True).otherwise(af.n)` answered `Int64` per policy,
  Polars reading the flag as 0 or 1, and `list[f64]` per period, where the
  selection kernel works in doubles; the record and the JAX engine split the
  same way, and the JAX engine computed the per-period pair in integers and
  settled it to the record's double only at the end, so `% 0` of it refused
  there where the frame answered NaN. The pair now answers `f64`, the flag
  read as its 0.0/1.0 indicator, as arithmetic already reads a flag beside a
  number. A whole number past 2**53 beside a flag is rounded to its double
  on Polars and refused by name on JAX, as `flag + n` already is, and a
  column stored wider than `i64` beside a flag is read as arithmetic reads
  one -- as the `Int64` its values fit, refused by name where one does not --
  where the per-policy form kept its `UInt64` and the per-period form rounded
  it into a double. The reference reader types a flag beside a whole
  number as `f64`, where it took the then branch's type.

- **A per-period comparison of whole numbers, dates and times or durations
  is exact, where 0.9.0 decided it by the nearest double.** The per-period
  route compares through a kernel that reads both sides as doubles, so past
  2**53 two neighbouring values were one: `af.k > 2**53` over a run holding
  2**53 + 1 answered 0.0 in every period, `af.k == 2**63 - 2` held 1.0 where
  the run held 2**63 - 1, and a nanosecond date and time or a duration one
  unit after another compared equal to it -- the same line written per
  policy answered each exactly. The kernel is now handed the two values'
  exact difference against nought, whose sign a double keeps, so every
  per-period comparison of `Int64`, `UInt64`, a date and time (every unit,
  zoned or not) or a duration answers what the per-policy form answers, as
  an indicator, inside a `when` and assigned as a column. Two per-period
  dates and times in different units are compared in the finer unit, where
  their raw counts were compared. A whole number beside a decimal keeps the
  stated bound. The JAX engine compares a per-period `i64` run past 2**53,
  where it refused it. Such a comparison costs one more pass over the run:
  over 10,000 policies x 121 periods a run against a value went from 0.015 s
  to 0.021 s, and a run against another run, which the kernel also checks for
  equal lengths, from 0.019 s to 0.046 s.

- **A per-policy comparison of two dates and times, or two durations, in
  different units answers in the finer unit, as the per-period one does,
  where 0.9.0 answered in the coarser.** Polars compared a nanosecond column
  with a microsecond one by cutting the nanoseconds off first, so a value one
  nanosecond after an instant compared equal to that instant held in
  microseconds, and `>` answered 0.0 where the per-period form of the same
  line answered 1.0. Both sides are now read as counts of the finer unit, in
  a width that holds every value of either unit, so nothing is cut and an
  open-ended 9999-12-31 beside a nanosecond column is still compared
  exactly. Two dates and times in different time zones compare by the
  instant each names, per policy as per period, where Polars refused the
  pair when the frame ran.

- **A per-period comparison is never decided by the nearest double of an
  operand whose type went unread.** A run compared with a sequence written
  into the formula -- `af.k > (2**53, 2**53)`, one timeline every policy
  shares -- had no type for the sequence, so it was compared in doubles and
  2**53 + 1 against it answered 0.0 in every period; the sequence is now
  typed and the comparison exact. A formula built on no frame
  (`ExpressionProxy(expr, parent=None)` and what is composed on it) was
  lowered blind to its operands, so a per-period comparison in it reached
  Polars as a native comparison of a list and was refused in Polars' words
  when the frame ran; it is now lowered against the frame it is assigned
  to, and answers what the same line written on that frame's columns
  answers. An operand whose type the frame cannot read at all is refused by
  name, where it was compared in doubles.

- **A zoned date and time compared with a zone-naive one is refused where
  the line is written, where 0.9.0 failed when the frame ran.** Per policy,
  Polars refused the pair at collect in its own words; per period it
  compared the two counts. The line now names both operands and the move:
  give the zone-naive one its zone where the data is loaded.

- **A column still wider than `i64` is compared exactly, and a literal past
  `i64` may be written against it; `replace` and `cut` over it read it as
  `Int64` where it fits and refuse it by name where it does not.**
  `af.pid == 2**64 - 1` against a `UInt64` identifier holding that value was
  refused as a literal past `i64`; it is admitted in a comparison or an
  `is_in` against such a column, and refused everywhere else. `af.pid > 7`
  answered null for the policy holding 2**64 - 1, because Polars compared
  the two in a type that holds neither; a pair of whole numbers of different
  widths is now compared in one that holds both. `replace` over a fitting
  `UInt64` column answered `UInt64` from a LazyFrame and `Int64` from a
  DataFrame; it answers `Int64` from both, and over a value past `i64` it is
  refused, naming the column and `to_text()`, where it answered in the
  column's width. `cut` over a value past `i64` is refused the same way,
  since its breakpoints are decimals.

- **A scenario's `within="mean"` of an integer column is the double nearest
  its exact mean, where 0.9.0 added the values as doubles.** On the scenario
  axis each scenario's policies are first reduced by `within`, and `"mean"`
  was Polars' own mean, which reads each whole number as a double before
  adding: 2**63 - 1, -2**63 and 5 averaged 5/3 where the mean is 4/3, and
  2**53 + 1, 2**53 + 1 and 2**53 + 2 averaged 9007199254740992.0 where the
  double nearest 2**53 + 4/3 is 9007199254740994.0. Every statistic across
  scenarios read that figure, so a `Sum(..., within="mean")` over two such
  scenarios answered 10/3, and an `ArgMax` could name the wrong scenario. The
  mean is now read once from the scenario's exact total and count, as every
  other mean of whole numbers is. The other `within` kinds were already
  exact (`"sum"` refuses a total past `i64`), and a decimal column's mean is
  unchanged.

- **`PeriodMedian`, `PeriodQuantile` and `PeriodCTE` read -2**63 as itself,
  where 0.9.0 answered its median as +9.2e18.** Each period's values were
  binned in the column's own width, where the least `i64`'s absolute value
  wraps to itself, so three policies of -2**63 had a median of +9.2236e18,
  and `PeriodCTE(level=0.5)` of -2**63, -2**63 + 1 and -2**63 + 2 answered
  -102.4. The values are
  now read as the doubles a sketch holds before they are binned, as `Median`
  and the other per-policy sketches always read them.

- **A shift under a decimal fill, `prospective_value` and
  `cumulative_survival` widen a whole-number run on the record, as
  `accumulate` does, where 0.9.0 converted it silently.** Each runs in
  doubles, and handed an integer run -- a policy count, `af.month`, a column
  computed in whole numbers -- the frame converted it in the engine without
  a word: a count of 2**53 + 1 came back as 2**53, and a
  `previous_period()`, `next_period()` or `at_period()` under the default
  `0.0` fill stored `list[f64]` under a record that still named the column
  `list[i64]`, so the JAX engine refused the document. The widening is now
  written into the record as `to_float(...)`, the checked conversion
  `accumulate` already wrote, so the record's type is the frame's, both
  engines answer the same doubles, and a whole number no double names
  exactly is refused by name rather than rounded. A shift under a
  whole-number fill (`fill_value=0`) keeps the run whole, as before.

- **`round_sig_figs` of a whole number is exact, on both engines, where
  0.9.0 rounded it through a double and cast it back.** Section 11.1.12 calls
  the operation exact, and an integer column came back wrong well inside the
  range a double names: 781,098 to one figure was 799,999, 8.5e15 was
  8,999,999,999,999,999, and 2**63 - 1 to two figures was
  9,199,999,999,999,998,976; the JAX engine computed the same wrong figures,
  and refused a whole number past 2**53. The figures are now counted and cut
  in whole-number arithmetic, a tie away from zero, so 781,098 is 800,000 and
  2**63 - 1 is 9,200,000,000,000,000,000 on both engines and in the reference
  reader. An answer that rounds up past the signed 64-bit range (2**63 - 1 to
  ten figures) is refused by name rather than wrapped, and so is a column
  still wider than `i64`.

- **`round_sig_figs` of a double rounds the fifteen significant figures a
  spreadsheet shows, on both engines and in the reference reader, where 0.9.0
  scaled the double by a power of ten in doubles.** The value is read as its
  fifteen-significant-digit decimal -- a sixteenth digit of 5 or more going
  away from zero, as `.excel.round()` reads it -- that decimal is kept to its
  figures with a half away from zero, and the answer is the double nearest
  the result, so the framework has one rounding rule. 0.285 to two figures is
  0.29 where it was 0.28 and 1.005 to three is 1.01 where it was 1.0, while
  0.15 to one is 0.2 and 2.675 to three is 2.68 as before; 781098.0 to one
  figure is 800000.0 where the scaling answered 799999.9999999999. From
  fifteen figures up the answer is the fifteen-digit value, so
  0.30000000000000004 to seventeen figures is 0.3. A whole-number column
  keeps every digit it has. The figures are exact from 10**(digits - 23)
  (10**-8 at fifteen figures or more) to below 10**37; outside that range
  both engines answer by Polars' own scaling, as 0.9.0 did, which may sit a
  few units in the last place from the fifteen-digit reading, or a figure
  away within a few units of a half -- so `3e-24` left by a cancellation
  where nought was meant rounds rather than stopping the run. A `Float32`
  column is read as the double it exactly is and answers in its own width.
  Zero, NaN and infinity are their own answers. A sweep of 61,867 values
  within three units of a half matches Python's decimal arithmetic with no
  misses on either engine. On the reference producer the exact route costs
  about 0.9 s per million values, where Polars' own rounding took about
  0.05 s.

- **`.round()` rounds the fifteen significant figures a spreadsheet shows,
  under either tie rule, on both engines and in the reference reader, where
  0.9.0 scaled the double by a power of ten.** The double is read as its
  fifteen-significant-digit decimal -- a sixteenth digit of 5 or more going
  away from zero, as `.excel.round()` and `round_sig_figs` read it -- and that
  decimal is moved to its places by the mode, so the framework has one
  reading. Near-ties move: 0.285 away from zero is 0.29 where it was 0.28,
  1.005 is 1.01 where it was 1.0, and a workbook's 68049.31499999999 is
  68049.32 at two places under either rule, where it was 68049.31; 2.675 to
  the even neighbour is 2.68 in the reference reader, where it was 2.67, as
  the engines already answered. `round(d, mode="half_away_from_zero")` now
  equals `.excel.round(d)`. Every value below 10**37 at up to 22 places is
  exact. From 10**37 a double is a whole number and its own answer, where
  Polars' scaling moved some by a unit in the last place and the JAX engine
  answered infinity once the scaling overflowed; past 22 places Polars' own
  rounding answers on both engines. A whole-number column keeps its type
  and every digit. Two sweeps of 40,000 values, most of them near a half,
  match Python's decimal arithmetic inside that range with no misses on
  either engine or in the reader, per policy and per period. A
  `Float32` column is read as the double it exactly is and answers in its
  own width, and a value whose type the lowering cannot read is refused by
  name rather than rounded by Polars, for `round` and `round_sig_figs` alike.

- **A sum, a running fold, a signed absolute value and a rollforward over a
  `UInt64`, `Int128` or `UInt128` column holding a value past the signed
  64-bit range are refused, as arithmetic on it is, where 0.9.0 wrapped or
  rounded it.** In the column's own width `[2**63, 2**63, 1]` summed to 1
  under `.list.sum()` and ran to `[2**63, 0, 1]` under `cum_sum()` (and
  `cum_prod()` and `projection.remaining_sum()` alike), `abs()` of an
  `Int128`'s least value answered that value, a rollforward opened at
  2**64 - 1 lost every premium added after it in the rounding to a double (a
  `UInt128` one stopped the plan with a panic), and `run_aggregated`'s `Sum`
  added 7 and 2**64 - 1 to 6. Each is now refused by name in the sentence
  arithmetic is, naming the column, `to_text()` and a narrower type, and
  reads a column whose values all fit as the `Int64` they are -- so a book
  handed over as a `LazyFrame` answers in `Int64`, as one handed over as a
  DataFrame does. An unsigned column is its own absolute value and keeps
  its width; a mean, a least or greatest value, `Max` and `Min` read such a
  column as before.

- **A wide integer column of a book handed over as a `LazyFrame` comes back
  `Int64` from `collect()` where every value fits, as from a DataFrame.** A
  `UInt64`, `Int128` or `UInt128` book column whose values fit was read as
  `Int64` where a DataFrame entered the frame, and kept its width where a
  LazyFrame did -- so a policy number no line read was `Int64` in one
  results file and `UInt64` in the other, and `gspio run-model`, which scans
  the book, wrote `UInt64`. The values are in hand when the frame is
  collected, so such a column that arrived with the book and was not written
  over is judged there by the same rule; one holding a value past `i64`
  keeps its width and every digit. The plan's own schema, before the run,
  still shows the width the column arrived in.

- **A least or greatest value, a bound, a rounding, a sign, a fill, an
  absolute value or a period's value of a `UInt64`, `Int128` or `UInt128`
  column answers `Int64` from both doors where every value fits, and is
  refused by name where one does not.** Over a book handed over as a
  `LazyFrame` such a line kept the wide type where the same book handed
  over as a DataFrame answered `Int64` -- `af.ids.list.max()` was `UInt64`
  from one door and `Int64` from the other. Each of these operations now
  reads such a column as arithmetic does: `Int64` where its values fit, on
  either door, and refused in arithmetic's sentence where one holds a value
  past `i64` -- including an unsigned column's absolute value and these
  reads of a past-`i64` identifier, which 0.9.0 answered in its width.
  **Keep such an identifier as text -- `af.pid.to_text()`.** A conversion
  (`to_text`, `to_integer`, `to_float`), a test of presence and a comparison
  read the value as before.

- **`step` is reserved on a fixed-step projection axis, as `month` is.**
  `projection.set(n_periods=..., step_years=...)` (or `steps_per_year=`)
  stamps a `step` index, and refuses model points that already carry a
  `step` column of their own rather than overwrite it. **Rename it --
  `mp.rename({"step": "source_step"})` -- or drop it if it came from a
  previous run's output.** A calendar axis stamps no `step` and leaves such a
  column alone. A model that carried the step index as data, as the only
  route to an off-calendar axis before this release did, declares the axis
  instead and reads `af.step` from it.

- **A model's column may not be named under the frame's working prefixes.**
  The frame keeps its own working columns under `__rollforward_` and
  `__gaspatchio_retained__`, and in 0.9.0 a model column named under either
  was accepted and then dropped at collect with them. 1.0.0 refuses the name
  wherever a column enters the frame: the constructor, from a DataFrame, a
  LazyFrame, a dict or `continue_from=`; an assignment and `with_columns`;
  a name `select` creates; `rename`; a join's right side; a date verb's
  `new_col_name=`; and a scenario axis's `scenario_column=`. Each refusal
  names the column and the argument to change. A batch file written by
  0.9.0's `run_to_parquet` or `for_each_scenario(return_full_grid=True)`
  carries the kernel's own `__rollforward_<fingerprint>` column, and the
  refusal for that shape names `df.drop(...)` to run before building the
  frame.

- **A column answers gaspatchio's own vocabulary; the rest of Polars is
  reached by name, through `polars_native()`.** A column used to answer any
  method Polars puts on an expression, because the proxy copied every public
  name off `pl.Expr` when the package was imported. So
  `af.premium.rolling_mean(3)` worked without anything in the framework
  knowing what a rolling mean is, the meaning of a model's line depended on
  which Polars happened to be installed, and the exported record of that line
  could say no more than that some engine text had run. The surface is now
  written from the declared operation set, so a call either names an
  operation any engine holding the vocabulary can evaluate, or it says out
  loud that it is Polars. Measured against Polars 1.42.1 — the public names
  on `pl.Expr` less the names the declared surface holds — **177 of 220
  method names are no longer reachable directly on a column** (179 on an
  expression built from columns, which loses `map_elements` and
  `map_batches` as well), and neither are the `dt`, `arr`, `struct`, `cat`
  and `bin` namespaces. Six operator
  spellings went with them: `^` and its reflected form, unary `+`, the
  truth-value hook (restored as a refusal — see Fixed, below), NumPy's ufunc
  hook and the unpickling hook. Nothing has stopped working:
  `af.premium.polars_native().rolling_mean(3)` returns the same number, and
  what changes is the record, which names the engine and takes that column
  off the portable subset. `str` and `list` survive as namespaces narrowed to
  the operations the vocabulary declares — `str.to_date`, and `list.sum`,
  `mean`, `min`, `max` and `get` — and gaspatchio's own `date`, `finance`,
  `excel`, `projection`, `schedule`, `curve` and `mortality` accessors are
  untouched, so `af.issue_date.date` and `af.qx.projection` are unaffected by
  any of this. A name with nowhere to go is refused where it was written,
  naming the door: `No 'rolling_mean' column accessor … write
  .polars_native().rolling_mean`.

  **The escape is not a drop-in replacement on a per-period column, and that
  is the one place a mechanical upgrade can move your numbers.** Polars reads
  a column of per-policy lists as one value per policy, so a method whose
  meaning *is* the axis it runs along runs down the model points rather than
  along each policy's projection periods. `af.account_value.shift(1)` used to
  move each policy's values one period; the same line through the escape
  moves each policy's whole timeline onto the next policy, and hands back a
  right-shaped answer with nothing to say which axis it used. Write the
  per-period form explicitly —
  `af.account_value.polars_native().list.eval(pl.element().shift(1))` — and
  check the axis on anything else you move to the escape. `shift`, `diff`,
  `interpolate`, `forward_fill` and `backward_fill` are now refused on a
  per-period column rather than answered down the wrong one (see Fixed,
  below); the rest are not, because the rest either fail loudly on the list
  dtype or are the portfolio-level work the escape exists for.

- **`.polars_native().list.reverse()` is refused and names
  `.list.reverse()`.** `list.reverse` is a declared operation now (see *A
  workbook's rollback converts as one portable line*, under Fixed), and the
  escape spelling of a declared name is refused for the reason every declared
  name's is: one calculation would record two ways. Drop `.polars_native()`.
  For the reverse-accumulate-reverse recipe a linear rollback was written
  with, write `projection.accumulate(..., reverse=True)` instead.

- **A table, mortality, curve or schedule read written inside a Polars
  expression is refused when it is assigned to a frame, where 0.9.0 recorded
  it as an engine fragment that named no table.** `af.q =
  mortality.lookup(age=af.age).cast(pl.Float32)` -- the same read continued
  by any Polars method the vocabulary does not declare (`cast`, `is_between`,
  `over`, ...), handed to a Polars function (`pl.max_horizontal`, `pl.when`,
  `pl.coalesce`, `pl.concat_list`) or opened with `.polars_native()` -- reached
  the record as one fragment identified by Polars' text, which prints the
  lookup and not the table. Two models whose tables differed in name and
  rates exported the same `graph_fingerprint`, and the table was in no
  node's `reads_assumptions` and not in `assumptions[]`. The line is now
  refused, naming the table and the moves. **Store the read as its own
  column and continue from it -- `af.q_read = mortality.lookup(age=af.age)`,
  then `af.q = af.q_read.polars_native().cast(pl.Float32)` -- or keep it in
  the declared vocabulary: `to_float()` / `to_integer()` / `to_text()` /
  `to_list()` for a conversion, `fill_nan(0.0)` for a NaN fill (see *Added*).**
  The same holds on a producer for the cross-model-point escape
  above: `.polars_native().sum()` opens on the stored column. Operators,
  declared methods (`fill_null`, `fill_nan`, `clip`, `round`, ...) and
  gaspatchio's `when` keep the read a node, as they did. `.alias(...)` on a
  producer now keeps the read too, so `af.with_columns(table.lookup(age=af.age).alias("q"))`
  records the lookup -- and an extraction renamed that way answers
  `.increments` and `.captures` as its rollforward's state, where it used to be
  refused. A compiled rollforward's expression is not refused, because its
  fragment reads the rollforward by name. A plain Polars frame is untouched:
  `df.with_columns(table.lookup(age=pl.col("age")).fill_nan(0.0))` keeps
  Polars' meaning. None of the tutorial models, `gaspatchio-models`, skills
  or docs uses the refused form. Spec Annex A.2's second case is closed.

- **A bare string where a column-level operand belongs is refused, not
  filled with nulls.** `af.issue_date.excel.edate("months")` looks like it
  names the `months` column, and read that way it is wrong — a
  column-level operand is the other half of a formula, so the string became
  the literal text, the arithmetic ran against it, and the column came back
  full of nulls that surfaced pages later as a reserve nobody could trace.
  The framework cannot know which was meant, so it no longer guesses: the
  call raises, naming the parameter, the string, and both spellings —
  `af["months"]` (or `af.months`) for the column, a number or a
  `datetime.date` for a value. The rule, stated in the docstrings on both
  sides: **on a column accessor a bare string operand is refused — write the
  operand as `af.column` or `af["column"]`.** Frame-level methods name a
  column by string: `af.date.create_timeline`, `af.date.add_duration`,
  `af.finance.present_value`. Ten operands across eight methods are covered:
  `excel.yearfrac(end_date_expr)`, `excel.irr(guess)`, `excel.pv(nper,
  pmt)`, `excel.days(start_date)`, `excel.edate(months)`,
  `excel.eomonth(months)`, `date.months_between(other)` and
  `finance.discount(rate_expr, n_periods_expr)`. Each parameter's type now
  states what it actually takes — a column, an expression, or a number or
  date — instead of the wider alias that included `str`.

- **A column-level operand is never a column name: `accumulate` and
  `with_period`/`with_periods` refuse a bare string.**
  `accumulate(initial="av_init", multiplier="growth", addend="net_flow")`
  read those strings as column names, which made the three operands the one
  place in the API where a column-level argument meant something the rest of
  the surface refuses — everywhere else a bare string could equally be a
  value, so the framework declines to guess. Write them the way every other
  column accessor takes them: `accumulate(initial=af.av_init,
  multiplier=af.growth, addend=af.net_flow)`. The refusal says so at the
  call — `initial='av_init' is
  a bare string, which could be a column name or a value. For the column,
  pass af["av_init"] (or af.av_init); for a value, pass a number. ...` — so
  the next attempt converges without a doc lookup.
  `with_period(1, value="x")` and `with_periods({1: "x"})` are refused in the
  same voice with the remedy that is true there: an override is one number,
  and a column is not one of the answers, because a replacement that varies
  by policy is a `when/otherwise` conditional rather than a spliced element.
  `prospective_value` joins the shared wording too — a string `discount_rate`
  or `discount_factor` used to get `must be float, ExpressionProxy, or
  ColumnProxy, got <class 'str'>`, which named the types but not the way out;
  the factor's message points at `discount_rate=` rather than offering a
  single number that argument would refuse anyway. Every refusal offers only
  what the parameter it names will actually take — a number on a numeric
  operand, a number or a `datetime.date` on a date formula — so no remedy
  sends you into a refusal on the next line. One rule now holds
  everywhere and is stated once: **frame-level methods name a column by
  string (`rename`, `drop`, `projection.set(issue_age_column=...)`,
  `af.date.create_timeline`, `af.date.add_duration`,
  `af.finance.present_value`); a column-level operand never does — write
  `af.column` or `af["column"]`.**

- **`accumulate`'s operands are `multiplier=` and `addend=`, the nouns the
  format specification already used for them.** Section 11.1.20 states the
  recurrence as `projection.accumulate(initial, multiplier, addend)` —
  `state[t] = state[t-1] * multiplier[t] + addend[t]` — while the accessor
  spelled the same two operands `multiply=` and `add=`. A reader
  implementing from the specification and a reader writing model code met
  two names for one thing, and the accessor answered `multiplier=` with *Did
  you mean 'multiply'?*, pointing away from the document it conforms to. The
  two verbs are now the nouns the third operand, `initial=`, always was.
  **Change `multiply=` to `multiplier=` and `add=` to `addend=` at every
  call.** There is no alias and no deprecation window: the old spelling is a
  `TypeError` on the line that wrote it rather than a warning in a log
  somewhere, and Python's own suggestion carries the new word — `got an
  unexpected keyword argument 'multiply'. Did you mean 'multiplier'?`.
  Nothing about the calculation moved. The three operands travel
  positionally on the wire with empty attributes, so an exported node — its
  operation tree, its fingerprint, the document's digest — is byte-identical
  either side of the rename, and no conformance vector, golden or
  specification clause changes with it.

- **`accumulate` takes numbers, and refuses anything else at the
  assignment.** Each of `initial`, `multiplier` and `addend`, scalar or per
  period, is read by its type when the line is written. A number or a null
  is read as it is, and a Decimal as its value. A Boolean is refused: write
  `when(af.in_force).then(1.0).otherwise(0.0)`, which says what a missing
  flag counts as and is what the exported record can carry. A date,
  a time or a duration is refused, where 0.9.0 read the number it is stored
  as, a date as its days since 1970; so is a category, where 0.9.0 read its
  codes, and text, where 0.9.0 parsed numeric text and failed on any other
  with "add values not contiguous". The refusal names the operand and its
  type, and the conversion to write: `excel.days` or `excel.yearfrac` for a
  date, a cast for text that holds numbers, and a Table lookup or
  `when/then` for a category.

- **A value written where another stood is the same kind, or the line is
  refused.** `af.rate.fill_null("n/a")` over a column of decimals answered
  text, `['1.0', 'n/a']`, and so did `fill_nan("n/a")`: Polars makes a fill
  fit by finding a type both sides can be written in, and the JAX engine and
  the conformance reader refused what the frame had produced. The same
  conversion nobody wrote waited in every operation that puts one value where
  another stood, and two of them cut a wider number down to the column's
  type: `replace({2.5: 9})` over whole numbers matched the policy holding 2,
  `replace({2: 2.5})` stored 2, whole numbers clipped at `1.5` were clipped
  at 1, `when(...).then(af.rate).otherwise("n/a")` answered text for every
  policy, and `previous_period()` over a run of product codes put the text
  `'0.0'` at period zero. Each is now refused at the line, naming both kinds
  and the move -- `af.rate.to_text().fill_null("n/a")` when text is meant, a
  `fill_value` the column can hold, a bound or a replacement written in the
  column's own kind. A whole number beside a decimal is still the declared
  widening (sections 11.1.13 and 11.1.28), a flag still fills or meets a
  number as the 0/1 indicator a stored comparison is, and `fill_nan`'s fill
  is a whole number or a decimal, the domain section 11.1.13 states. A
  per-period `when` that mixed text and numbers used to fail at `collect()`
  with the kernel's "mixed branch dtypes"; it is now refused where it is
  written.

  Serves *Sharp knives, no magic*: a fill never changes the type of the
  column it fills.

- **A comparison across two kinds is refused at the line, and so is an
  `is_in` member of another kind.** `af.issue_date < 3` over a column of
  dates ran and answered `0.0` for every policy, per policy and per period:
  Polars compared each date's day count with 3. `af.plan == 1` over text,
  `af.rate == "a"`, a timestamp against a date, and `af.issue_date.is_in([1,
  2])` were refused only when the frame ran, in Polars' words. Section
  11.1.26 infers no ordering between two families, so all six comparisons --
  per policy and per period, in either operand order, assigned as a value or
  written as a `when` condition or under `&`/`|` -- and every `is_in` member
  now refuse two kinds where the line is written, naming both and the move:
  `af.issue_date < date(2025, 6, 1)`, a number compared as a code through
  `to_text()`, members written in the column's own kind. A whole number
  beside a decimal is still one kind, a category is text, and a flag still
  compares with a number as the 0/1 indicator a stored comparison is
  (`af.flag == 1`); in `is_in`, where Polars has no membership between a
  flag and a number, that pair is refused with the move too. `is_between` is
  not a declared operation; its declared form is the two comparisons, and
  each is held to the rule.

  Serves *Sharp knives, no magic*: no answer rests on a conversion the
  formula never wrote.

- **A number filling flags, and `fill_nan` over a value that holds no NaN,
  are refused where the line is written.** `af.has_rider.fill_null(0.0)`
  failed at `collect()` with Polars' "invalid or ambiguous dtypes", and
  `fill_null(0)` answered by turning every flag into a 32-bit whole number;
  both are refused at the line, naming the move: `fill_null(False)`, or
  `when(af.has_rider.is_null()).then(0.0).otherwise(af.has_rider)` when a
  number is meant. `fill_nan` over text, a flag or a date failed at
  `collect()` with Polars' "is_not_nan operation not supported"; it is refused
  at the line, naming the value's kind and `fill_null` as the fill for a
  missing value. Section 11.1.13 now states `fill_null`'s domain -- a value
  and a fill of one family -- which is what the producer enforces.

  Serves *LLM-shaped from the inside out*: the refusal says what to write,
  in the model's own terms, before anything runs.

- **Arithmetic between two per-policy flags is refused at the line.**
  `af.smoker * af.rider` over two per-policy Boolean columns failed inside
  Polars when the frame ran -- "`multiply` operation not supported for dtype
  `bool`" -- with no gaspatchio sentence, and `-`, `//`, `%` and `**` did
  the same; `+` answered an unsigned count that the exported record called
  `i64` and the JAX engine answers as a double, and `/` answered a double.
  Section 11.1.25 does not admit a per-policy flag on both sides of one
  operation, so all seven are refused at the assignment, naming the move:
  `af.smoker & af.rider` where `*` means both, `af.smoker | af.rider` where
  `+` means either, or the conversion `when(af.smoker).then(1.0)
  .otherwise(0.0) * af.rider` where an amount is meant. A flag beside a
  number, and a per-period flag beside anything, reads as the 0 or 1 it
  indicates, as before.

  Serves *Sharp knives, no magic*: a line with no stated answer is refused
  where it is written, not answered in three types.

- **A per-policy flag in arithmetic reads as its 0/1 double, under every
  operator.** Beside a whole number the answer took Polars' integer type --
  `af.smoker + 1` was an `Int32` the record called `i64`, `af.smoker *
  af.count` an `Int64` -- while the same line per period, a stored
  comparison and the JAX engine answer a double; `2 // af.smoker` answered
  null where the per-period form answers infinity, and `af.smoker ** 2.0`,
  `af.smoker ** af.x` and `2.0 ** af.smoker` failed inside Polars, which
  raises no Boolean to a power. A per-policy flag beside a number is now
  read as 0.0 or 1.0, a Float64, so all seven operators answer `f64` on
  either side and the record writes `f64`: `af.smoker + 1` is `[2.0, 1.0]`
  where it was `[2, 1]`. Two flags in one operation stay refused. No
  fingerprint moves; a node's `dtype` and a results file's column type do.

  Serves *Sharp knives, no magic*: one answer type for one line, whichever
  engine runs it and whichever shape the flag has.

- **`excel.yearfrac` is Excel's YEARFRAC.** It negated the answer when the
  end date came first, so a workbook's `YEARFRAC(valuation, issue)`
  converted as written came back negative; Excel takes the earlier date as
  the start, and so does gaspatchio now -- the answer never depends on the
  order and is never negative. Two rules follow Excel too. Basis 0: a start
  on February's last day becomes the 30th and an end day of 31 then stays
  31 (29 February to 31 March 2024 is 31/360, not 30/360). Basis 1: the
  one-year denominator applies where the end falls in the next year on or
  before the start's month and day, not wherever the interval is 366 days
  or fewer, and there is no anniversary rule for a 29 February start -- 25
  September 2020 to 26 September 2021 is 366/365.5, not 366/365, and 29
  February 2024 to 28 February 2025 is 365/366, not 1. Checked against D. A.
  Wheeler's reverse-engineered algorithm (the one OpenFormula and Gnumeric
  follow): 0 mismatches over 20,006 date pairs on every basis, reversed
  pairs equal to forward, on the JAX engine and the reference producer. A
  model that told pre-inception periods apart by a negative year fraction
  compares the dates instead: `when(af.date < af.issue_date)`. The
  conformance kit's yearfrac vectors and its reader follow.

  Serves *Meet you where you are*: a workbook's YEARFRAC converts as
  written and answers what Excel answered.

- **An integer narrower than 64 bits is read as `Int64` where it enters the
  frame.** The record names every integer `i64` and the JAX engine computes
  in it, but the frame computed in the width the data arrived in: an `Int32`
  sum assured of 25,000,000 times 100 came back as -1,794,967,296 where JAX
  answered 2,500,000,000, `month * 1_000_000_000` wrapped at month 3, and an
  unsigned `1 - 2` was 4,294,967,295. A book column, a column `join` brings,
  and the `month`, `step` and `num_proj_months` a projection stamps are now
  `Int64` (lists of them `list[Int64]`); `Int8` through `UInt32` widen
  exactly. A results file carries `Int64` where it carried `Int32`, so its
  file digest moves once; the book's digest and every fingerprint, which
  already collapsed widths, do not. An assumption table's integer keys were
  already normalised and are unchanged.

  Serves *Audit by default*: the run computes in the type its record states.

- **A running fold now answers null from the first period it does not have
  onward, instead of folding past it.** `cum_sum`, `cum_prod` and
  `projection.cumulative_survival` used to skip a period carrying no value
  and carry on, leaving one null cell and a running total that had quietly
  lost a term. They now mark that period and every later period in the fold's
  own direction: `cum_sum([1.0, null, 3.0, 4.0])` answered
  `[1.0, null, 4.0, 8.0]` and now answers `[1.0, null, null, null]`; reversed
  it answered `[8.0, null, 7.0, 4.0]` and now answers
  `[null, null, 7.0, 4.0]`, because the direction of the fold is the
  direction a lost period runs in. A survival built on a decrement column
  with a missing period is the case this is for: it used to read as a correct
  curve with one null cell in the middle, and now says it does not know the
  survival after the decrement it never got. `start_at` is unaffected — the
  opening value is the boundary the projection starts from, never the factor
  that went missing, so `cumulative_survival` on `[0.01, null, 0.01, 0.01]`
  answers `[1.0, 0.99, null, null]`.

  **This moves numbers in a model whose data carries a null period in one of
  those three inputs.** If a null there means zero, say so — `.fill_null(0.0)`
  before the fold — and the old answer comes back, now written down where a
  reviewer can see it. If it means the value is missing, the new answer is the
  honest one and the periods it nulls were never supported by the data.
  Nothing changes for a column with no null in it, and the framework mints no
  null periods of its own: a null period comes from your data.

  **What this entry left for the one below it.** `sum`, `mean`, `min`, `max`,
  `projection.remaining_sum` and `projection.prospective_value` kept the
  published rule that a null period is *absent* to the fold, so a present
  value taken as `.list.sum()` over a survival this rule had nulled folded
  past the null tail; the entry below extends the rule to those six, and this
  release ships both. The period shifts are untouched, as is the
  down-the-column form of `cumulative_survival`, which folds the model points
  rather than the periods. Sections 11.1.9, 11.1.14 and 11.1.19 of
  `spec/graph-artifact/v0-preview.md` state the rule and the closure beside
  it — a policy whose whole column is null answers null through all six folds
  — and section 14.1 carries the line. No field, tag, attribute or byte
  encoding moves: only the answer at a null period is different.

- **A total over a period it does not have now answers null, instead of
  folding past it.** `sum`, `mean`, `min` and `max` used to treat a period
  carrying no value as a period that was not there, so
  `[10.0, null, 30.0, 40.0]` summed to 80.0, averaged to 26.666666666666668,
  and gave 10.0 and 40.0 for its least and greatest — every one of them the
  answer the three periods that arrived would give, and none of them saying a
  fourth had gone missing. All four now answer null. `projection.remaining_sum`
  and `projection.prospective_value` fold from the last period back, so they
  null that position and every earlier one: the suffix sums of that run
  answered `[80.0, 70.0, null, 40.0]` and answer `[null, null, 70.0, 40.0]`,
  and a present value over it nulls the same two positions under either
  timing. A run of nothing but nulls answers null through all four totals,
  where `sum` used to give the empty run's nought; the empty run itself is
  untouched and still sums to nought, because a fold that reaches no period
  has lost none.

  **This is the rule the running folds already follow, reaching the last place
  a missing period could disappear without a word.** The total is the one
  number a reviewer signs, and the present value taken as `.list.sum()` over a
  survival curve with a hole in it was the number that still read as correct.
  **If a null period means zero, say so** — `af.col.fill_null(0.0)` before the
  total brings every old answer back, and the filling is a node of the model's
  own record, where a reviewer reads the assumption instead of inferring it.
  Nothing changes for a column with no null in it, and the framework mints no
  null periods of its own: a null period comes from your data.

  **What this entry left for the one below it.** `projection.accumulate` kept
  carrying a null into a non-finite state — `[110.0, null, nan, nan]` for a
  null multiplier — because its recurrence is a compiled kernel rather than an
  expression and this change rebuilt nothing; the entry below takes it, and
  this release ships both. Sections 11.1.9, 11.1.14 to 11.1.17, 11.1.20 and
  11.1.21 of `spec/graph-artifact/v0-preview.md` state the rule, 11.1.14
  states once for the family that a modeller who means nought writes it, and
  section 14.1 carries the line. Seven published conformance answers change
  with the clauses and the packaged reader changes with them; no field, tag,
  attribute or byte encoding moves.

- **`projection.accumulate` answers null from a lost period onward, instead of
  null and then NaN.** The recurrence used to mark the missing period null and
  carry a NaN state into every period after it, so an account value opening at
  100 with `multiplier = [1.1, null, 1.1, 1.1]` answered
  `[110.0, null, nan, nan]`, and a null addend at period 2 answered
  `[110.0, 121.0, null, nan]`. That NaN was not the arithmetic's answer —
  nothing in the data was non-finite — it was a stand-in the kernel put in for
  a state it no longer had, and it read as a broken calculation rather than as
  a missing input. A running state that has lost a period is unknown from
  there on, and now says so at every later period: those two runs answer
  `[110.0, null, null, null]` and `[110.0, 121.0, null, null]`. A null opening
  value answers a run of nulls, as it always did.

  **This is the last member of the family to take the rule**, after the three
  running folds and the six totals in the two entries above, and it is the one
  that had a fourth answer of its own for the one shape. **A NaN is left
  exactly where it is:** it is a value the arithmetic carries, not a period
  that went missing, so a NaN multiplier still gives a NaN state and every
  state after it is NaN — a modeller reading nulls knows an input was missing,
  and one reading NaN knows a number went non-finite, and the two must not
  answer alike. **If a null period means zero, say so** —
  `af.col.fill_null(0.0)` before the recurrence brings the old fold back, and
  the filling is a node of the model's own record where a reviewer reads the
  assumption. Nothing changes for a column with no null in it, and the
  framework mints no null periods of its own: a null period comes from your
  data.

  Section 11.1.20 of `spec/graph-artifact/v0-preview.md` states the rule where
  it used to place a null step outside its stated form, and section 14.1
  carries the line. **No published expected value moves** — `nulls.json`
  carried no `projection.accumulate` case, and the recurrence's three cases
  elsewhere carry no null — and five join it for the rule, every expected
  value hand-derived from the clause. A non-finite operand and a null outer
  list to the recurrence stay outside the entry, so no vector claims either.
  No field, tag, attribute or byte encoding moves.

- **A NaN in a scenario column was counted as an exact zero by three
  statistics, and now makes every statistic over that column NaN.** `Median`,
  `Quantile` and `CTE` are backed by a signed sketch that routes each
  observation by sign: positive one way, negative the other, everything else
  to an exact-zero bucket. A NaN is neither greater nor less than zero, so it
  fell into that bucket and was ranked as a zero. On the column
  `[-500, -400, NaN, 300, 400]` the median answered `0.0000` and the
  upper-half CTE `249.9912`, against the `-50.0195` and `275.4891` the same
  column gives with the NaN taken out. A `0/0` anywhere in ordinary model
  arithmetic is enough to produce one, and Polars' `drop_nulls()` does not
  remove it. The NaN is now counted on its own, the zero bucket holds real
  zeros and nothing else, and any NaN at all takes the answer away from a
  median, a quantile, a CTE and a quantile rank.

  **`Min` and `Max` change too, and they are the one place this replaces an
  answer that was defensible.** Both used to pass over a NaN and report the
  smallest and largest *known* value — which is what Polars' and Python's own
  `min` and `max` do. On the column above they answered `-500` and `400`, and
  answer NaN. The reason is one rule instead of three: *a NaN in a column
  makes every statistic over it NaN* is a rule a second engine can implement
  without exceptions, and in capital work the scenario that divided by zero is
  usually the stressed one — the tail being measured. `Count` is unchanged: a
  NaN is an observation, and five values is five.

  **A model that produces a NaN today gets a different number tomorrow.**
  That is the change rather than a side effect of it — the number it used to
  get was wrong and looked right. A NaN in a report is loud and not explained:
  it names the aggregate, and finding the division is still yours. Nothing
  moves for a column with no NaN in it; every figure above is unchanged on the
  NaN-free column.

  **The audit sidecar is now valid JSON when an aggregate is non-finite.** A
  NaN result was written as the bare token `NaN`, which the JSON grammar does
  not have: the file read as valid until somebody parsed it strictly, and then
  the one number that most needed reading took the whole record down with it.
  A non-finite result now travels as the string naming itself — `"NaN"`,
  `"Infinity"`, `"-Infinity"` — which is what §10 of
  `spec/graph-artifact/v0-preview.md` already says such a value travels as,
  and it reaches inside period vectors and partitioned frames as well as
  standing on its own. This is the Python scenario surface and not the
  artifact format: no schema changes, and no digest moves.

- **Assigning a non-finite literal to a column now refuses** — both
  `af.reserve = float("nan")` and `af.benefit_cap = float("inf")` raise at
  the line that wrote them, naming the value. A NaN or infinite literal is a
  bug, not a value: it propagates silently through a projection and surfaces
  as null reserves nobody can trace back to a line. An operand refuses the
  same way: `af.account_value * float("nan")` raises at its own line, where
  0.9.0 carried the NaN through the projection. If you were using
  `float("inf")` as a deliberate "no cap" sentinel, use an explicit large
  bound, or leave the cap column out and skip the `clip`.

- **`when(af.a and af.b)` is refused, instead of quietly paying the policies
  the first test excluded.** Python's `and`, `or` and `not` ask their operand
  for a single true or false. A column holds one answer per policy, and on a
  projection one per period, so it has none to give — but while the question
  was answerable, `af.a and af.b` evaluated `af.a`, found an object rather
  than a flag, and handed back `af.b` whole. The first test dropped out of
  the model, every policy it excluded was paid anyway, nothing raised, and
  the exported record showed a well-formed one-column predicate: the audit
  trail read correctly while the number was wrong, which is the worst
  combination available. `bool()`, `and`, `or`, `not`, a bare `if` and
  `assert` now raise on a column, on an unfinished expression and on a
  comparison — so `(af.age > 60) and (af.sum_assured > 1000000)` is refused
  too, which it was before this release's surface change and is the older
  half of the defect. The refusal names the element-wise operators that do
  the work: `&` for and, `|` for or, `~` for not, each comparison in its own
  brackets, and `when(...).then(...).otherwise(...)` for a value that depends
  on the test. Nothing that was already correct moves in value: `&`, `|` and
  `~` between two comparisons, and `&` and `~` on per-policy Boolean columns,
  return exactly what they did. Two things do move, the next two entries:
  the operators no longer do bit arithmetic on whole numbers, which 0.9.0's
  `&` and `~` did and its `|` did after a comparison, and two forms that
  answered in 0.9.0 answer in another type.

- **`&`, `|` and `~` on whole numbers are refused, where 0.9.0 did bit
  arithmetic.** In 0.9.0 `&` and `~` reached Polars' bitwise operations
  whenever an operand was a whole number: `af.i & af.j` over `[6, 3]` and
  `[3, 5]` gave `[2, 1]`, `~af.i` gave `[-7, -4]`, `af.i & 1` gave `[0, 1]`,
  and `af.a & af.b` over two 0/1 flag columns gave 0s and 1s rather than a
  selection. `|` did the same with a comparison on its left and a whole
  number on its right: `(af.i > 4) | af.j` gave `[3, 5]`, an `Int64` column,
  and `(af.i > 4) | 1` gave `[1, 1]`. The specification's logical
  operations mean conjunction, disjunction and negation, never integer bit
  operations (section 11.1.27 of `spec/graph-artifact/v0-preview.md`), so
  1.0.0 takes Boolean operands -- a comparison, a Boolean column, `True` or
  `False` -- and a stored Float64 column holding exactly 0.0 or 1.0, and
  refuses any other at the line that wrote it. The default error mode prints,
  for `af.i & af.j`: `TypeError: Error calling gaspatchio method '__and__':
  __and__ combines Boolean values, predicate masks, or a stored 0.0/1.0
  Float64 column. Compare numeric flags explicitly (af.flag == 1). For integer
  bit operations use polars_native().and_(...), .or_(...), or .not_().` A
  0.9.0 model that
  combines integer flags with `&` or `|` stops at that line on upgrade. For
  flags held as whole numbers, compare them: `(af.a == 1) & (af.b == 1)` and
  `(af.i > 4) | (af.j == 1)` answer the Boolean selection, `True` and `False`
  where 0.9.0 answered whole numbers. For bit arithmetic, which is Polars'
  own and no part of the vocabulary, write `af.i.polars_native().and_(af.j)`,
  `.or_(...)` or `.not_()`: over the same columns they return `[2, 1]`,
  `[7, 7]` and `[-7, -4]`, and the record marks the line as Polars', off the
  portable subset. On a per-period column 0.9.0's bit arithmetic already
  failed at `collect()`, and 1.0.0 refuses it at the assignment instead. A
  per-period comparison beside a number is the exception: 0.9.0 did
  arithmetic on its 0/1 indicator, so `(af.li > 2) & 2` answered `0.0` and
  `2.0` and `(af.li > 2) | 0.5` answered `0.5` and `1.0`, and 1.0.0 refuses
  those as well.

- **Two forms of `&` and `|` that answered in 0.9.0 answer in another type.**
  The type is the one the specification states for a logical operation
  (section 11.1.27 of `spec/graph-artifact/v0-preview.md`), and the truth
  values are the same wherever no operand is null.

  - **`|` with a Boolean expression on its left and a comparison on its
    right.** The expression is anything but a bare column or a comparison:
    one built by `&`, `|` or `~`, a method answering a Boolean such as
    `is_null()`, `is_not_null()`, `is_in()` or `is_nan()`, or a `when()`
    choosing between `True` and `False`. 0.9.0's `|` did not take such an
    expression, so Python handed the pair to the comparison's reflected
    operator, which answered a 0/1 mask: `(af.a & af.b) | (af.i > 4)` over
    `a = [True, False]`, `b = [False, False]` and `i = [6, 3]` gave `1.0` and
    `0.0`, a `Float64` column, and gives `True` and `False`, a Boolean one.
    So do `(~af.a) | (af.i > 4)`, `af.x.is_null() | (af.i > 4)` and
    `((af.i > 4) & (af.i < 5)) | (af.i > 9)`, and so does anything built on
    such a result, `((af.a & af.b) | (af.i > 4)) & True` among them. Where an
    operand is null the answer can move as well: 0.9.0's mask carried the
    null through, and 11.1.27's three-valued logic makes `True` or a null
    `True`. So `af.x.is_nan() | (af.i > 4)` with `x` null and `i` 6,
    `af.c.is_in(["p"]) | (af.i > 4)` with `c` null, and
    `(~af.a) | (af.x > 0)` with `a` False and `x` null each gave null and
    each gives `True`; `False` or a null is still null. Where a line reads
    the column as a number, write the number:
    `when((af.a & af.b) | (af.i > 4)).then(1.0).otherwise(0.0)` gives 0.9.0's
    `1.0` and `0.0` wherever no operand is null. Where one is, it gives
    `1.0` or `0.0` where 0.9.0 gave null.
  - **A per-period Boolean `& True`** -- `af.flags & True` over a per-period
    Boolean column, or `af.values.is_null() & True` over a per-period one --
    gave the operand's own `list[bool]`: the one `&` over per-period Booleans
    that answered in 0.9.0 rather than failing at `collect()`. It now answers
    each period as a 0/1 indicator, `list[f64]`, as every logical operation
    over a per-period operand does. `af.flags & True` is `af.flags`: read the
    operand itself where the Booleans are wanted.

- **On a per-period column, `is_in` and `replace` answer each period, and a
  `clip` bounded by columns answers as Polars' own `clip` does.**
  `per.is_in([1.0, 2.0])` over `[1.0, 13.0, 25.0, 37.0]` answered one Boolean
  for the whole policy, `False`, and `per.replace([1.0], [5.0])` matched
  nothing and handed the periods back unchanged. They now answer
  `[True, False, False, False]` and `[5.0, 13.0, 25.0, 37.0]`, and `cut`
  bands each period where it raised. A membership set given as a column has
  no per-period form, and that one combination is refused at the line rather
  than answered once per policy. A per-period `clip` whose bounds are columns
  runs a kernel of its own, which composed `max` then `min`: on crossed
  bounds -- lower 8, upper 2 -- it answered `[2, 2, 2]` over `[1, 5, 10]`
  where Polars' `clip` answers `[8, 8, 2]`, and it turned a NaN into a bound.
  It now answers as Polars' `clip` does, a NaN staying NaN. Nothing moves
  where the bounds are ordered and no value is NaN.

- **A labelled `cut` refuses breakpoints that run downward, and labels that do
  not match its bands, at the line that wrote it.** `cut([50, 30],
  labels=[...])` bands every life correctly and labels each band as another
  -- a 25-year-old filed under "over 50" -- because the engine sorts the
  breakpoints and keeps the labels in the order they were written; 0.9.0 ran
  it with nothing raised. A label count that does not match the bands failed
  only at `collect()`, against a query plan. Both are refused where the band
  was written now, naming the breakpoints. An unlabelled `cut` bands and
  names exactly as before, whatever order its breakpoints are written in.

- **Assigning a column to a name the frame already uses now refuses, instead
  of quietly doing nothing.** `ActuarialFrame` carries 33 public names, and 28
  of them answered an assignment with something other than a column.
  Twenty-five swallowed the line whole: `af.sum = af.premium * af.rate` stored
  the expression on the frame, minted no column, and `collect()` returned a
  frame without it, with nothing raised at any point — and `sum`, `count`,
  `min`, `max` and `product` are ordinary model-point field names, not exotic
  ones. `collect` was the worst of the twenty-five, because its silence did
  not stay put: the assignment said nothing, and the next collect of that
  model died on `TypeError: 'ExpressionProxy' object is not callable`, naming
  neither the column meant nor the line that wrote it. The other three —
  `columns`, `dtypes` and `schema` — did refuse, with Python's own *property
  'columns' of 'ActuarialFrame' object has no setter*, which says nothing
  about columns and is the complaint that earned the accessor names their own
  refusal. All 28 now raise that same sentence: the name, that no column was
  created, `af["sum"] = ...` as the way to write a column called that, and
  what the name already is on the frame — a method, or a property. The
  bracket form is unchanged and is the door, on a frame that arrived carrying
  a `sum` column as much as on one that did not: `af["sum"] = ...` writes it
  and `af["sum"]` reads it back. No calculation changes and no digest moves; a
  line that silently did nothing now says so, on the line that wrote it.

- **`register_accessor` refuses a name nobody could reach, and assigning to a
  registered accessor's name refuses.** An accessor registered under a name
  `ActuarialFrame` already carries -- `max`, `filter`, `collect` -- was
  accepted and could never be reached, because the frame's own attribute is
  found first; so was one registered under a Python keyword, or a name that
  is not an identifier. All three are refused at registration now, naming
  the clash. And `af.<name> = ...`, where `<name>` is a registered accessor's
  name other than the framework's own five, created no column and left the
  expression where the accessor had been; it raises now, pointing at
  `af["<name>"] = ...`.

- **`graph`, `schema`, `dtypes` and `materialize` are the frame's own names.**
  `af.graph`, `af.schema`, `af.dtypes` and `af.materialize()` are new, so a
  data column called one of them, which 0.9.0 reached as `af.schema`, is
  reached as `af["schema"]` and assigned as `af["schema"] = ...`; reading it
  as an attribute raises, naming the bracket form. See *`af.graph` — ask a
  model how each of its columns was made* and *`af.materialize()`*, under
  Added.

- **A column of Python objects cannot be assigned at all**, as a series or as
  a NumPy object array: it is refused at the line that wrote it. See *A
  column of values injected wholesale is identified by what was injected*,
  under Fixed.

- **A column of Python objects nested inside a list or an array is refused
  at the assignment too.** The check at the door read the outermost layer
  of the dtype only, so `List(Object)` and `Array(Object, k)` went past
  it — an imploded object column produces the first, and the
  two-dimensional object array a simulation can hand back produces the
  second. What followed was still not the error the check was written to
  give. Taking the injection's content stamp hashes the values under the
  artifact's own content grammar, and that grammar has no tag for a Python
  object, so the complaint came from the identity layer rather than from the
  line: the imploded column came back refused, naming the column and the
  types the vocabulary does have, and the fixed-width array came back as the
  engine's own panic out of the cast that widens an array to a list.
  Neither of them names the assignment that wrote the column. The dtype is
  now walked to the bottom (list and array inners, every struct field) and
  an Object anywhere in it is refused where it was written, naming the whole
  dtype: `Cannot assign a column of dtype List(Object): a column holding
  Python objects, at any depth, is not a column of a model …`. Nesting
  itself is not what is refused — a `List(Float64)` is what every projection
  produces, and a fixed-width `Array(Float64, k)` is a simulated path per
  policy.

- **A join keeps the frame's rows where they were, so one file gives one
  book on every run.** `ActuarialFrame.join` left row order to
  Polars, and the streaming engine `collect()` uses by default hands a
  join's rows back in a different order from run to run. The book digest is
  taken over rows in the order the book holds them, so a model that joined
  its enrichment data in Phase 1 and rebuilt its frame from the result
  recorded a different book digest on every run over the same in-force
  file -- five digests in five runs at 400,000 policies -- and
  `diff_artifacts` reported the model points changed between runs that
  differed in nothing. The join now keeps the calling frame's rows first and
  in their order unless told otherwise: `maintain_order="left_right"` for a
  left or inner join -- a lookup keeping the policies where they were, as
  VLOOKUP does, and giving a policy the other table matches more than once
  its matches in the order that table lists them, where `"left"` alone
  handed them back in a different order on each of four runs --
  `"left_right"` for a full, right or cross join, which puts
  the other table's rows after the frame's in their own order, and `"left"`
  for a semi or anti join. Each was checked under the streaming engine cut
  into 1,000-row morsels: one answer run after run, the frame's rows first
  and in order. An explicit `maintain_order` always wins, `"none"` included,
  which is how a model asks for Polars' faster unordered join; a join kind
  the frame does not know how to keep in order is refused by name. It costs
  time: two joins over a million policies and a streaming collect took 77 ms
  against 46 ms, median of seven on the Intel laptop, and 46 ms again with
  `maintain_order="none"`. The tutorials, which already passed `"left"` by
  hand, are unchanged.

- **`ActuarialFrame.join` refuses a key whose name holds `,` or `=`, or is
  empty**, before anything changes, and asks for the column to be renamed.
  See *What a join key drives is now in its lineage*, under Fixed.

- **A lookup built before its table was registered again with other data
  refuses at collect.** Tables resolve by name when a plan runs, so in 0.9.0
  a lookup built against one `Table` and collected after another `Table` of
  the same name was built over different data read the second table's
  values -- the shape a lost scenario override takes, reporting zero
  sensitivity. 0.9.0 already refused the stale `Table` object at the next
  `lookup()`; the lookups built before the replacement now refuse too, when
  they are collected, naming the table. Build the lookup from the most
  recent `Table` of that name, or give the two tables different names.
  Registering byte-identical data again changes nothing. A shocked scenario
  run stacks each base table under one name batch by batch, and collects a
  batch before it stacks the next, so nothing built against a batch's table
  outlives it: those tables replace themselves without the warning a user's
  own table gets.

- **`with_scenarios` returns model points major, scenarios minor, under the
  collect every model runs.** The scenario axis is a cross join, and a bare
  cross join commits to no row order: Polars' in-memory engine returned model
  points major, and the streaming engine `collect()` uses by default returned
  scenarios major -- every policy under the first scenario, then every policy
  under the next. So 0.9.0 handed back the opposite of the order its own
  tutorials show. The join now keeps policy 1 under every scenario, then
  policy 2, on either engine. No scenario's total moves; code that read a
  run's rows by position does, and should sort by the model's own axes
  (`scenario_id`, the policy identifier) rather than trust either order.

- **A shocks plan runs the frame-only model, and the scenario door it used
  to need is retired.** Code that ran on 0.9.0 and now raises or reads
  differently, each with its move:
  - `ScenarioRun.run(af, model_fn)` and a shocks-dict `for_each_scenario`
    call the model as `model(af)`. A function requiring `tables=` or
    `drivers=` is refused, naming the move: pass the reconciled model,
    `plan.run(af, model.main)`. A model still guarding its lookups with
    `"scenario_id" in table.dimensions` keeps working, because the guard is
    false on its own table. The three-argument form stays on
    `for_each_scenario` for the ids and drivers shapes.
  - A shock names exactly one target: `table=` a table by the name its
    `Table` was built with, or `column=` a **model-point column**. A shock
    with neither is refused (it moved every table). So is a shock with both:
    0.9.0 ignored `column=` there, and the interim value-column form is not
    carried into 1.0. Confine a table shock to some rows with
    `FilteredShock(where=...)`. A time condition on a column shock is
    refused, because a model-point column has no periods.
  - `ParameterShock` is removed: write `AdditiveShock(0.01,
    column="infl_rate")` (or `MultiplicativeShock`, `OverrideShock`). A
    recipe's `param:` key is read as `column:`.
  - `RelativeFloorShock` is removed, because it refused at run: write
    `MaxShock(MultiplicativeShock(0.5), AdditiveShock(-0.2), table=...)`.
  - `TimeConditionalShock(time_column=...)` is removed: it moved the plan's
    identity and nothing it computed. Drop the argument.
  - A seeded plan's seed is the `rng_seed` column, at any batch size, where
    it was `drivers["rng_seed"]` at batch size 1 only. Read `af.rng_seed`.
  - `base_tables` is optional and keyed by each table's own name. Given, it
    is a content check, and the run refuses a model whose table differs.
    Only a table a shock names is stacked.
  - Inside a run, `to_dataframe()` of a table a shock names is refused,
    because its rows differ by scenario. Read it through `lookup()`, or take
    its rows before the run.
  - `graph_fingerprint_by_scenario` now names each scenario composed on its
    own (BASE is the standalone model), rather than the axis-carrying batch.
  - `Table.with_shock()` and `Table.from_shocks()` refuse any `column=`,
    because a table holds no model-point column, and a `table=` naming
    another table.

- **A rollforward's `.apply()` is refused when the rollforward is
  compiled.** 0.9.0 accepted `.apply()` and failed in every `collect()`.
  `compile_rollforward` now refuses it whatever its body, before a tracked
  rollforward asks for a label, naming the operations to use instead. `Apply`
  stays in the artifact format's vocabulary, and a reader still accepts it.

- **A rollforward step's label may not contain `@`, and a tracked rollforward
  reports a movement for every step.** With `track_increments` on, 0.9.0
  emitted one field per labelled step, and `Floor` and `Round` carry no
  label, so the amount a floor absorbed was on no output at all. Every step
  emits now: a labelled one under `increment_<label>` as before, a floor or a
  round under `<kind>@<ordinal>` -- `floor@3`, its 1-based position in the
  chain -- which `increment_for` reads back. `@` is reserved for that, so a
  label carrying one is refused at compile, tracked or not. A chain with no
  floor or round emits exactly the fields it did, and no compiled
  fingerprint moves.

- **A located validation error now reaches the caller.**
  `capture_validation_context` exists to answer the question a validation
  helper cannot — which line passed the bad value — and no caller had ever
  received its answer. The raise that carried the located error sat inside
  a `try` whose own `except` caught it and re-raised the original, so the
  work of finding the model's line ran on every failure and was thrown away
  every time; what came out was the bare `ValueError`, with no file, no
  line and no chained cause. Enhancement was also gated on finding a frame
  among the call's arguments, which a plain validator taking a rate or a
  term never has, so the error mode had nothing to switch on. The located
  error is now raised **from** the original, so the first message, its type
  and its traceback all stay on the chain; a `ValidationError` that arrives
  already typed keeps its identity and only gains the location. The caller
  is found by the same walk past framework frames that expression lineage
  uses, rather than a hand-written list of file names to skip, and if that
  walk fails the error is still raised — with no location on it. Nothing in
  the enhancement path can now hide the failure it was handed. One thing to
  check on the way in: a `TypeError` or `KeyError` raised inside a decorated
  function now arrives as a `ValidationError`, which subclasses `ValueError`
  alone, so an `except TypeError` or an `except KeyError` around such a call
  stops catching it — catch `ValidationError`, or `ValueError`, at those
  sites.

- **`af.trace(...)` follows the frame's own mode, not the global default read
  at call time.** A frame takes its mode when it is created — the `mode=`
  it was given, else the default at that moment — and every other behaviour
  already read that. Tracing alone re-read the global default when the traced
  function ran, so `run_model(..., mode="debug")` under an `optimize` default
  traced nothing. It now agrees with the frame. The one visible difference:
  calling `set_default_mode("debug")` *after* building a frame no longer turns
  tracing on for that frame — build the frame after setting the mode, or pass
  `mode="debug"` to it. The command line sets the mode first and is unaffected.

- **`gspio verify --model` decides the model by the graph its files rebuild.**
  It imports the model and runs it over `--model-points` in a fresh
  interpreter, without collecting, and holds the rebuilt `graph_fingerprint`
  against the record's, in a new `graph` line beside the stamps. A
  `verify --model` without `--model-points` is now exit 4 where it was exit 0
  ("the graph is rebuilt by running the model over the policy data"); a
  scenario plan's record also needs the plan, `--scenarios run_scenarios.py`
  (`verify_artifact(..., scenarios=)`), and is exit 4 without it; a model that
  cannot be rebuilt in the verifier's environment, and a line that hands the
  engine a Python function or a compiled plugin, are exit 4, named. The report
  gains the `graph` and `scenarios` lines, so a stored report lists two more
  checks. The verdict now holds in the verifier's environment: the model's
  own code runs, and needs the files it reads where it reads them.

- **`gspio describe` and `analyze_table` describe the file they were handed,
  and never name a column it does not hold.** 0.9.0 read a 1,000-row sample
  and reported every dimension fact off it beside the whole file's row count
  -- on a ten-thousand-policy extract `point_id` read 1,000 distinct values --
  and answered a value column of `rate` or `value` where the file had no such
  column, even over a `--value-column` the caller had just declared.
  `describe` now reads the whole file up to five million cells, and above
  that the largest sample the budget buys, and `--json` says which in `scan`
  and `scanned_rows`. It names the rule that chose its value column, lists
  the columns it could not rule out in `value_column_candidates`, says in
  `value_column_source` whether the name is `declared`, `inferred`,
  `after_melt` or `none`, honours a declared `--value-column` in both output
  modes, and reads a model-point extract as one, in the console as in the
  payload. `detected_value_column` is empty where there is no value column to
  name, so read `value_column_source` before trusting it. `analyze_table`
  reads every row unless handed `sample_rows`, reports `sampled_rows` when it
  samples, and takes `value_column=`. Each dimension's `sample_values` -- in
  the payload and in `Table.schema` -- are its five lowest distinct values,
  ascending, where 0.9.0 gave five in an order that moved between runs.

- **Dependencies.** `pyarrow` 16 or later is required, where 0.9.0 accepted
  15, and `executing` and `jsonschema` are new runtime dependencies.

- **`gspio tutorial init --force` replaces only a directory it can lose
  nothing from.** It deleted whatever the destination held before copying, so
  `--dest . --force` inside a project took the project and its `.git` with it.
  Every copy now carries a `.gspio-tutorial` marker, and `--force` replaces
  an empty directory (copying into it) or a marked copy; any other directory,
  a directory holding `.git`, and the directory the command runs in or one
  above it are refused with exit status 2, naming `--dest` and what the
  directory holds, and nothing is deleted. A copy made before this release has
  no marker: empty it, or name a new `--dest`.

- **Every datetime column's digest moves once: the content grammar now
  carries a timestamp's zone and its whole instant.** A `datetime` column's
  header writes its zone after the `0x17` tag (empty for a zone-naive or UTC
  column, which digest alike), and each value writes its microseconds and then
  the nanoseconds past them. The book digest, a table's and a join's
  fingerprint, a hole's content stamp and a results manifest's
  `inputs_digest` all read it, so every document, manifest or table stamp
  over a datetime column states a new digest; the token stays
  `gspv0-preview-3`, as no golden, corpus or released document holds one.

- **A table keyed by a date or a timestamp is fingerprinted as the dates or
  instants it holds, so `gspio verify` no longer agrees over another unit.**
  The fingerprint was taken over the count the lookup kernel keys by, with no
  unit, zone or kind: one instant kept in ms, µs and ns gave three
  fingerprints, while 5 ms, 5 µs, 5 ns, day 5, the integer 5 and any zone
  shared one, and a run whose claims read 10 against a millisecond table
  verified ✓ on assumptions, graph and book against a microsecond file with
  the same counts, whose claims read 20. The key is now hashed under the
  content grammar's own `date` or `datetime` tag, with its zone, as the book
  digest hashes a column, so every table keyed by a date or a timestamp --
  and its shocked, copied and stacked tables -- states a new fingerprint,
  and with it every graph reading one; no shipped tutorial, golden or room
  holds such a table. A millisecond key whose microseconds leave `i64` is
  refused by name, as at every other door. The audit payload carries such a
  key as `date` or `datetime` ISO-8601 text, and a timestamp key in a zone
  other than UTC as the `unavailable` omission, since a payload names no
  zone. `Table.extend` appends a slice keyed in another unit as the same
  instants, and refuses a slice key of another kind by kind. §12.3 and §15
  say so.

- **A table can no longer be keyed on a duration or a time of day.** The
  content grammar names a date and an instant but neither of these, so such a
  key was fingerprinted as the bare count of its unit: a 5 ms duration key
  shared a fingerprint with the integer 5, with 5 µs and with 5 ns. `Table`,
  `TableBuilder`, `Table.extend`, the `gspio verify --assumptions` re-read and
  every shocked or stacked copy now refuse the key column by name, as every
  other door that hashes a column already refuses those types, and the
  refusal names the move: key the table on a whole number of the unit you
  mean (`pl.col("k").dt.total_days()`), or on a date. This withdraws the
  duration- and time-keyed tables this release had admitted; no shipped
  tutorial, kit vector or room keys a table on either. §11.1.24 says so.

- **Models that choose rows get new identities, and an executable export
  refuses a selection no replay can make.** An `af.filter(...)` or a semi or
  anti join is recorded as a selection step and enters `graph_fingerprint`,
  `formulas_fingerprint` and the book's columns, so an audit file of a model
  that selects carries digests 0.9.0 never wrote; a model that selects
  nothing keeps every digest it had. `profile="executable"`,
  `gspio calc-graph --profile executable` and `af.collect(engine=...)` /
  `run_aggregated(engine=...)` refuse, naming the line, a filter whose
  condition is outside the core vocabulary (a string method, a cast, a
  window) or reads a column the model calculates: write the condition from
  model-point columns with comparisons, `&`, `|`, `~`, `is_in` and the null
  tests, or select the model points before the run. The audit profile still
  records every selection.

- **`run_aggregated(...).n_policies` counts the policies the model valued.**
  On the Polars path it was the rows the book held, so a model filtering four
  policies to its three in force reported 4 beside a total over three, where
  the JAX engine reported 3. It is now the rows the folds saw on every engine,
  and the audit record's `n_policies` says the same.

- **`run_to_parquet(...).n_policies` counts the policies the model valued.**
  It was the rows the book held, so a model filtering four policies to its
  three in force reported 4 beside the three rows it wrote, and a check that
  the rows read back equal `spill.n_policies` failed. It is now the rows
  written, at every batch size.

- **A batch runner refuses a frame the setup rebuilt from collected values,
  and a hole the frame arrived holding moves the model's identity.** The 0.9
  setup step -- `mp = af.collect()`, a join or a column in plain Polars,
  `af = ActuarialFrame(mp)` -- is the Phase-1 shape of 0.9.0's AGENTS.md
  template, the model-building skill and the L3-reconcile, L4 and L5
  tutorials. Its work is outside the frame's record, so a share of the book
  taken there was the batch's share: `run_aggregated` answered 6000 at
  `batch_size=1` and 5000 at 2 where the book's total is 3000, and
  `run_to_parquet` wrote the per-batch figures, with nothing refused.
  Wherever `run_aggregated` or `run_to_parquet` cuts the book into more than
  one batch, a frame the model builds from a DataFrame -- bare or with
  `continue_from=` -- holding a column the batch did not hold, a batch
  column whose values changed, or other rows (a filter) is refused by name,
  per-row joins included, since a DataFrame holds values and not the work
  that made them; a DataFrame that is the batch's own values passes, and a
  `LazyFrame` is judged on its plan, so a per-row `af._df.with_columns(...)`
  runs and one reading across rows is refused. The refusal names the four
  ways out: `af.join(table, on=...)`, the column computed on the book before
  the run, one batch, or `engine="jax"`. Over the whole book -- one batch,
  `collect()`, the command line, a scenario plan -- the setup runs as before.
  Separately, a column the frame arrived holding that nothing accounts for
  -- a `rebuilt` hole, and an `unrecorded` name the book never had -- now
  carries the content stamp of what it held (the holes section's `content`),
  and `graph_fingerprint` folds it beside the name: an edit to a file the
  setup joined moves `graph_fingerprint` and every run record's figure,
  where it moved none; `formulas_fingerprint` and `book.digest` do not move.
  `run_aggregated`, `run_to_parquet` and the scenario plans now tell the
  record which columns the book carried, as `gspio calc-graph` does, so the
  joined column is a hole in their records too rather than a field of the
  book. So every model with an arriving hole writes a new `graph_fingerprint`
  once; a model with none, or only a column written over past the frame's
  doors, keeps every digest it had. `gspio verify` still holds a holed record
  open.

### Removed

- **The `gaspatchio_core` import name is gone.** Its deprecation warning has
  said it would be removed in 1.0 since 0.9.0, when the import name became
  the package name. `import gaspatchio_core` now raises Python's own
  `ModuleNotFoundError`; write `import gaspatchio`, which has named the same
  modules since then. The wheel no longer ships the alias package, and
  `gspio` no longer surfaces its warning.

- **`RollforwardCollector` is gone.** Deprecated since 0.6, it was a second
  door to the extractions `CompiledRollforward` already publishes:
  `RollforwardCollector(compiled).expr_for("av")` said what
  `compiled.expr_for("av")` says, and `.increment_for("COI")` sat beside it.
  Those two methods are the doors now. `from gaspatchio import
  RollforwardCollector` and `from gaspatchio.rollforward import
  RollforwardCollector` raise `ImportError`, and
  `gaspatchio.rollforward._collector` no longer imports. The replacement is
  a deletion at the call site — drop `RollforwardCollector(...)` and call
  the compiled artefact directly — and it is also faster: on an
  `ActuarialFrame` every extraction from one compiled rollforward shares a
  single kernel call, where the facade ran the kernel once per extraction.
  On a raw Polars frame, where there is no `ActuarialFrame` to materialise
  the shared column, `compiled.plugin_expr()` is the published escape
  hatch: one struct expression carrying its own kernel call, aliased onto
  the frame and read with `pl.col("rf").struct.field("av@eop")`.

- **`gaspatchio.functions.vector` and `gaspatchio.functions.utils` are gone.**
  Neither module held an implementation. `vector` republished the six plugin
  wrappers — `accumulate`, `curve_eval`, `fill_series`, `list_clip`,
  `list_conditional` and `list_pow` — and `utils` republished the operand
  converter `to_polars_expression`. Each now has exactly one home, the one the
  code was already written in: `gaspatchio.frame.lowering._polars.plugins` and
  `gaspatchio.frame.lowering._polars.expressions`. Importing either retired
  path raises `ModuleNotFoundError`. `gaspatchio.functions` itself no longer
  publishes `fill_series`, and its type stub no longer claims a `when` the
  runtime never had; `when` is unmoved in `gaspatchio.functions.conditional`
  and is reached, as model code always reached it, from the top-level
  `gaspatchio` namespace. The underscore in `_polars` says what the wrappers
  are — the inside of a lowering, not a door a model is meant to open. If you
  were calling one directly, the operation you want is on the column:
  `af.multiplier.projection.accumulate(...)` rather than `accumulate(...)`,
  `af.disc_rate_ann.finance.to_monthly(...)` rather than `list_pow(...)`.

- **`gaspatchio.polars_backend` and `gaspatchio.accessors.excel_functions` are
  gone**, and so is the private `gaspatchio.schedule._canonical`. Thirteen
  modules between them, and not one line of implementation: `polars_backend`
  republished the Polars expression helpers — `accumulate`, `fill_series`,
  `list_clip`, `list_conditional`, `list_pow`, `curve_eval`,
  `to_boolean_expr`, `unwrap_for_list_eval`, `dispatch_list_op`,
  `execute_list_clip`, `execute_list_pow` — out of
  `gaspatchio.frame.lowering._polars`; `excel_functions` republished `days`,
  `edate`, `eomonth`, `irr`, `pv`, `round` and `yearfrac` out of
  `gaspatchio.frame.lowering._excel`; and `schedule._canonical` republished
  `canonical_bytes` out of `gaspatchio._identity` to no caller at all. Those
  three are the home for each name, and importing any retired path now raises
  `ModuleNotFoundError`. The Excel functions are reached the way they have
  always been reached from a model, on the accessor —
  `af.issue_date.excel.yearfrac(...)`, `af.cashflows.excel.irr()` — and the
  underscore in `_polars` and `_excel` says the modules behind them are the
  inside of a lowering rather than a door. A test now walks the package and
  refuses any module that defines nothing and only re-publishes another
  module's names, so the count of second spellings stays at zero.

- **`gaspatchio.column.dispatch` is gone**, along with the three
  underscore-private modules behind it: `_dispatch_autopatch`, which copied
  Polars' expression methods onto both proxies as the package was imported,
  `_dispatch_execution`, which called them, and `_dispatch_namespaces`, which
  did the same for `dt`, `arr`, `struct`, `cat` and `bin`. That module's only
  documented export was the `capture_source_context` re-export covered below;
  everything else it published described the machinery rather than the API.
  What replaces it is not a module to import but the generated surface itself
  — see Breaking above. `gaspatchio.column.proxy`'s type stub goes with them,
  so an editor now completes the operations gaspatchio names rather than the
  whole of `pl.Expr`: a much shorter list, on which every name has a
  signature, a docstring and a meaning the calculation record can carry.

- **`gaspatchio.errors.TracedOperation` is gone.** It was the record type of
  the old debug-mode computation graph, which ran in parallel with the
  durable calculation log until the log took over every reader — error
  attribution, query-plan logging, and the calc-graph export. There is one
  record type now, `gaspatchio.frame.calculations.CalculationRecord`, minted
  on every assignment in every mode rather than only under `--mode debug`.
  If you were reading `af._computation_graph` (an internal field, also gone),
  read `af._calculations` instead: `record.column` replaces `operation.alias`,
  `record.expr` replaces `operation.expression`, `record.dtype` replaces
  `operation.expected_dtype`, and `record.source` replaces
  `operation.metadata` — a statement-scoped span, so it carries the whole
  assignment's text rather than one physical line.

- **`gaspatchio.errors.capture_source_context` and
  `gaspatchio.errors.OperationMetadata` are gone**, along with the
  `capture_source_context` re-export from `gaspatchio.column.dispatch`.
  `capture_source_context` read one frame at a caller-chosen depth and
  described it; nothing in the framework calls it any more, because counting
  frames to reach the caller cannot work when the number of framework frames
  in between depends on the route the call took (see the attribution fix
  below). If you were calling it, call
  `gaspatchio.frame.calculations.capture_source_span()` instead: it takes no
  depth, walks past the framework's own frames wherever they sit, and returns
  a `SourceSpan` — `span.file` replaces `metadata.file_name`, `span.line`
  replaces `metadata.line_number`, `span.function` replaces
  `metadata.function_name`, and `span.statement` replaces
  `metadata.source_line` with the whole statement rather than one physical
  line. It returns `None` when the location cannot be resolved, where the old
  function returned a placeholder string. `gaspatchio.errors.metadata`, the
  module that held these two and `TracedOperation`, is gone as well, and
  `display_filename` -- 0.9.0's `OperationMetadata.display_filename()`,
  which renders a notebook cell's filename as its cell label -- is no longer
  public: the framework still labels a cell that way in its own reports,
  from a private module.

- **`gaspatchio.registry` is gone: `TableRegistry`, `AssumptionTableRegistry`
  and `WideToLongTransformSpec`.** The two classes wrapped the Rust table
  lookups that `gaspatchio.assumptions.Table` already registers and reads,
  and the dict subclass carried five fields nothing read. Importing the
  module raises `ModuleNotFoundError`. Build and look up tables through
  `gaspatchio.assumptions` -- `Table(...)` and `Table.lookup(...)` -- which is
  now the only door to a lookup table.

- **`gaspatchio.column.namespaces` is gone**, with `DtNamespaceProxy` and
  `StringNamespaceProxy`, the proxies behind a column's `dt` and `str`
  namespaces. A column's `str` namespace now holds the declared text
  operations and nothing else, and a column has no `dt` namespace: the date
  operations are on `af.<column>.date`, and anything else Polars offers is
  behind `.polars_native()`. See *A column answers gaspatchio's own
  vocabulary*, under Breaking.

- **What `gaspatchio.errors` publishes is narrower.**
  - `ErrorBoundaryFinder` is no longer exported from `gaspatchio.errors`. It
    stays in `gaspatchio.errors.boundary`, beside `search_collect_failure`,
    the one search both error paths now run.
    `gaspatchio.errors.boundary.attribute_collect_failure` is gone: it
    returned `search_collect_failure(af, exception).attribution`, so read
    that field.
  - `SuggestionType.TYPE_CAST`, `OPERATION_SPLIT` and `CODE_EXAMPLE` are gone;
    nothing constructed them, and `TYPO_FIX` and `DOCUMENTATION` stay.
    `DataFrameContext.dataframe_schema`, a field nothing set, is gone with
    `DataFrameContext.display_columns()` and `display_preview()`;
    `ValidationError.enhanced_message` is gone, its text already in the
    exception's `args`; and so are `ColumnInfo.display()`,
    `OperationContext.display()`, `Suggestion.display()` and
    `SourceLocation.display_location`. `EnhancedError.to_console` renders
    the report from the models themselves.
  - `gaspatchio.errors.formatter.FriendlyErrorFormatter` and
    `gaspatchio.errors.suggestions.ErrorSuggestionEngine.suggest_fixes` take
    the calculation record as `record=` where they took `operation=`, since
    `TracedOperation` is gone.
  - `gaspatchio.errors.constants.MAX_SUGGESTIONS` and
    `gaspatchio.errors.frame_utils.find_user_code_frame` are deleted with the
    definitions nothing in the package called (see Internal);
    `find_calling_user_code()` beside the latter does what it did.

- **The fields of 0.9.0's graph models went with `CalculationGraph`.** In
  `gaspatchio.frame.graph`, `DataSource` and
  `graph_models.ListBroadcastMetadata` are gone. `GraphNode` carries `kind`
  where it carried `type`, and no `label`. `NodeData` requires `id` and
  `column`; it states a column's arrival as `provenance` where it held a
  `DataSource` in `source`, what it read as `reads` where it held
  `dependencies`, and it has no `kind` (value or Boolean mask) and no
  `list_broadcast`. `GraphEdge` requires `relationship` and `subtype`.
  `graph_utils.simplify_dtype` is gone, because the artifact names types in
  its own vocabulary. Code that built these models by hand needs the new
  fields; a document's own shape is the specification's, and the first
  entry under Breaking says how it moved.

- **Importable internals that moved, went private or changed shape.** Each
  was reachable by import from a public module path:
  - `gaspatchio.cli.DescribeResponse`, `DimensionDetail`,
    `InterpolationDetail` and `ListColumnDetail`, the models behind
    `gspio describe --json`, are private now; the JSON they write is the
    contract, and how it moved is under Breaking.
    `gaspatchio.cli.validate_file_path` is deleted.
  - `gaspatchio.column.shape.kind_from_dtype` is private.
  - `gaspatchio.column.condition_expression.ConditionExpression` is built
    from one operation-tree node, where it took `expr`, `operator`, `left`
    and `right`, and `gaspatchio.functions.conditional.ConditionalProxy`
    takes `condition=` where it took `condition_expr=`. Write a condition
    with `when(...)`, which builds both.
  - `gaspatchio.frame.tracing.append_operation_to_graph` is gone, and
    `log_query_plan` takes `records=` where it took `operations=`.
  - `gaspatchio.runner.ModelRunResult` has no `error_context` field; nothing
    read it.
  - `gaspatchio.examples.docstrings.style.ImplicitOutputRule`, a rule that
    returned an empty list and was missing from the checker's own list of
    rules, is deleted.

### Fixed

- **A JAX capability refusal sends a reader to Polars only where Polars
  answers.** Every refusal from the tree named one move, "run this model on
  Polars, or keep the column out of the artifact", including where the
  reference producer refuses the same line: a fold or a running fold over a
  per-policy value, a selection or a reversal of one, a date operation or a
  month move over a value per period, a rate or a period count held per
  period in `finance.discount` or `finance.present_value`, a per-period
  initial value in `projection.accumulate`, a per-period guess in
  `excel.irr`, a flag, text or a date in `to_float`, a decimal position in
  `list.get`, a flag or text as `excel.edate`'s or `excel.eomonth`'s months,
  and an unlisted `excel.yearfrac` basis. Each now names the operation's own
  move; a form the producer answers (`excel.pv` or `to_text` per period, a
  per-period value in `finance.discount`) still names Polars.

- **Every date operation but `excel.yearfrac` refuses a value per period by
  name, on Polars, the JAX engine and the kit's reader alike.** §11.1.33 states
  `date.months_between`, `excel.days`, `date.to_period`, `date.offset_by`,
  `date.date_ranges` and `excel.from_excel_serial` over one value per policy,
  as it does `excel.edate` and `excel.eomonth`. Over a date or a serial held
  per period, Polars failed when the frame ran, in its own words (`` `year`
  operation not supported``, `cannot cast List type`); the JAX engine and the
  reader answered per period, and the JAX engine failed `date.date_ranges` with
  an array error. Each is now refused where the line is written, naming the
  operation, the operand and the move. The JAX engine refuses from the
  record's shape before any book is read, and in the lowering for a
  calculation; the reader refuses with `calendar-operand-per-period`. The kit
  publishes one refusal case per operation. `excel.yearfrac` still reads a
  date in every period. §11.1.33 says so.

- **A millisecond timestamp whose microseconds leave `i64` is refused by
  name, not wrapped onto another instant.** The content grammar scaled a
  millisecond count to microseconds with two's-complement wrap-around, so
  9,223,372,036,854,776 ms wrote the same bytes, and the same digest, as the
  microsecond count -9,223,372,036,854,775,616: two instants under one
  identity. The core encoder, the Python reference and the kit reader now
  refuse such a value naming the column and the count (beyond about 292,000
  years either side of 1970). No representable digest moves; the kit gains
  two refusal cases and an edge case. §12.3 says so.

- **A negative zero in data reads as zero, under the one identity it already
  had.** A one-cell table holding `0.0` and one holding `-0.0` shared one
  table fingerprint and one graph fingerprint, yet `to_text` answered `'0.0'`
  and `'-0.0'` and `sign` `0.0` and `-0.0`. A `-0.0` is now written as `0.0`
  where data enters -- an assumption table's source (and `Table.extend`) and a
  column injected as a `pl.Series` or NumPy array -- before it is hashed or
  read; the JAX engine and the kit reader read a table's `-0.0` answer cell
  the same way. **Behaviour change:** a sign-reading operation (`sign`,
  `to_text`) over a data `-0.0` now sees `+0.0`. No published hash moves and
  `fingerprint_algorithm` stays; a literal and a compiled machine's setting
  (`floor(value=-0.0)`) keep their sign. Two kit vectors pin it, reading the
  sign through a reciprocal (`1 / 0.0` is `+inf`) so every engine answers them. §12.3 says
  so.

- **A Phase-1 rebuild under a scenario batch holding several scenarios is
  refused by name.** `mp = af.collect()`, a share of the book taken in
  Polars, and `ActuarialFrame(mp)` under `ScenarioRun` answered 450 for 900
  at `batch_size=2`, unrefused: the collected frame holds every scenario's
  copy of the book, so the share was taken over both. Where a scenario
  plan's batch holds more than one scenario, a frame the model builds is
  now judged against that crossed frame as a rebuild in a batch of policies
  is, and refused naming the routes (the column on the book before the run,
  a join through the frame, one scenario a batch). One scenario a batch
  answers as before. §13.2 says so.

- **An operand held at the wrong shape is refused by name, on every
  engine.** A fold or a running fold over one value per policy (`sum`,
  `mean`, `min`, `max`, `cum_sum`, `cum_prod`), a period override over one,
  a broadcast onto a per-policy axis, an `excel.irr` guess, a
  `projection.accumulate` initial value, or a `finance.discount` /
  `finance.present_value` rate or period count held per period, and
  `date.to_period(freq="Q")`, each failed when the frame ran in Polars' words
  (`list.eval operation not supported for dtype f64`, `cannot cast List
  type`, `expected leading integer in the duration string`). The producer
  now refuses each where the line is written, naming the clause and the move;
  `freq` takes an interval written with its count (`"1q"`) as before. The
  JAX engine refused the column forms already and now refuses the nested
  ones it answered or failed on (a guess per period answered, an initial
  value per period raised an array error, a broadcast of a per-period value
  answered the wrong list), and names the producer's move for `freq="Q"`;
  the kit's reader refuses the forms it answered or failed on. Fourteen kit
  refusal vectors; 858 published. §11.1.18 says so.

- **A null per-policy operand of `excel.pv` beside two per-period ones is a
  null in each period.** §11.1.18 repeats a null scalar to the policy's
  periods, and the producer did so beside one per-period operand; beside two
  it answered a null run, as if the policy had no periods, where the
  reference reader answered a run of nulls. It now answers the run of nulls
  on every path, and §11.1.35 says so. Three kit cases; 880 published.

- **A null beside a test a NaN left unknown wins, in a per-policy `&` or
  `|`.** `flag | (ratio > 1.0)` with the flag missing and the ratio 0/0
  answered true -- Polars' own `|` over the NaN comparison it orders above
  every number -- and `flag & (ratio < 1.0)` answered false; a `when` over
  either selected by that answer. §11.1.26-27 say the null wins over the
  unknown beside it: the combination is a null there, in either operand
  order, in memory and streaming, and a `when` over it selects its
  `otherwise`. A null beside a side with a truth value is three-valued logic
  as before (false AND null is false), also where the null is a combination
  a null won. The kit's reader already answered so. Five kit cases; 885
  published (the JAX engine refuses their books, which hold a null).

- **The kit's reader answers a selection case's column as it answers a
  value case's.** A `selection-value` case's `expr` was read with the
  reader's internal evaluator, which reads a comparison as a flag rather
  than its `f64` indicator and keeps an unknown as a NaN inside a flag; a
  case over a comparison or a per-policy `&` would have failed a conforming
  producer. Every published selection case publishes a bare column, so no
  published answer moves.

- **The JAX engine answers `is_null` and `fill_null` over a per-period test
  a NaN left unknown.** Per period that test is its NaN indicator, and a NaN
  is not a null (§11.1.13): `(flag & (rate > 1.0)).is_null()` is false in
  every period and `.fill_null(0.0)` keeps the NaN, as on Polars and the
  kit's reader. The engine refused both lines by name. Per policy they still
  refuse: the unknown there is a null, which the engine does not carry.

- **The JAX engine answers a per-policy NaN test combined with a per-period
  run as unknown in every period.** `when((af.month < 2) | (af.av / af.gtee >
  1.0)).then(1.0).otherwise(0.0)` over a nought guarantee answered NaN in
  period 0 and read the 0/0 test as false from period 1 on -- `[NaN, 1.0,
  0.0, 0.0]` where Polars and the kit's reader answer NaN in every period --
  whenever the run beside it was not a double: a whole number (the
  projection's own `month`), text, a date, a stored flag or `flag == True`,
  under `|`, `&`, `<` and `!=` in either order. A policy's value repeats over
  its periods (§11.1.18), so the test has no truth value in any of them; the
  engine kept the unknown one cell wide and widened it as a run one period
  long. Six kit cases; 900 published.

- **The JAX engine refuses by name every read of a flag a per-period `when`
  left null.** Two flag branches over a condition a NaN left without a truth
  value answer a null there (§11.1.28: a flag holds no NaN), and the engine,
  which carries no null, refused the flag stored as it is, `== 1` and
  `is_in`; read by arithmetic (`* 1.0`, `- q`, `+ 0`), `&`, `~` or another
  `when`'s condition it answered NaN, and `is_null` and `is_not_null` gave
  the wrong flag. Each now refuses those cells by name, and a refusal
  raised as a node's value is settled names the node, as every other
  refusal does, rather than the check. Five kit cases; 905 published. The
  JAX README's list of answers that are a null now includes the flag.

- **A per-period `when` over a condition with no truth value answers NaN in
  a double result whichever branch holds a null.** Neither branch is selected
  there (§11.1.28), but the producer made the answer NaN by adding a NaN to
  the selection, and a null plus a NaN is a null: `when(r < 1.0).then(a)
  .otherwise(run)` with the run null at the period where `r` is NaN answered
  null, the same null in the `then` answered NaN, and per policy every
  placement answered NaN. The cell is NaN now on every route a per-period
  selection takes -- a comparison, a combined mask, a per-policy condition
  over a run -- and §11.1.28 says a branch's null does not change it. A
  result type that holds no NaN keeps its null. The conditional kernel
  answers the NaN itself in the same pass that selects, so the line takes
  no extra pass; a selection whose two branches are literals is read as
  before. Four kit cases; 909 published (the JAX engine refuses their books,
  which hold a null).

- **A per-period `excel.pv` whose first rows answer only null runs is an
  answer, not a panic.** Under the streaming engine a null run in the first
  policy -- beside one per-period operand, or beside two or three -- came back
  untyped, and the next rows' values panicked with "type Float64 is
  incompatible with expected type Null"; in memory it answered. The kernel now
  states its `list[f64]` as declared, so the streaming answer is the in-memory
  one: a null run where the run is null.

- **`finance.discount` and `finance.present_value` refuse a value held per
  period by name.** §11.1.29 states both over scalar operands only and names
  `projection.prospective_value` as the per-period valuation; the producer
  answered a per-period value as a list no clause states, while the JAX
  engine and the kit's reader refused it. The producer now refuses it where
  the line is written, with that move, and the JAX engine names the move
  rather than Polars. Two kit refusal vectors; 860 published.

- **A rebuild over a `with_scenarios` crossing of several scenarios is
  refused by name.** `with_scenarios` hands the crossed frame back with no
  runner around the model, so the judgement above never reached it: `mp =
  af.collect()`, a share of the total sum assured taken in Polars, and
  `ActuarialFrame(mp)` answered 111.1 for a policy whose figure is 222.2,
  from every scenario's copy at once. A crossing of more than one scenario
  is now held, and a frame built over a table carrying its axis and its
  columns, or over a plan scanning its book and its axis, is judged against
  it and refused naming the routes this door has (the column on the book
  before it is crossed, a join through the frame). One scenario crossed
  answers as before; a summary that kept the axis and dropped the book's
  columns is not judged. §13.2 says so.

- **The JAX engine refuses the kit's duration cases by name.** Its vector
  runner had no reading of the envelope's input-only `duration` and
  `list[duration]`, so the 26 duration-refusal cases stopped in the adapter
  as *not-yet-lowered*. The runner now records such a column as the whole
  number of microseconds its values are stated in and hands the engine the
  duration itself; the engine's door refuses it by name, naming the cast,
  as the producer and the reader refuse those calls. All 26 are
  `domain-refusal-matched`.

- **A `maximum_age` horizon names an issue-age column it cannot read.**
  `projection.set(until="maximum_age", ...)` over a frame with no column
  `issue_age_column` names failed inside the query plan with Polars'
  `ColumnNotFoundError`; an issue age held as text failed there as
  arithmetic on a string, and one held as a flag was read as an age of 1.
  Each is now refused at `projection.set()`, naming the column and the move.

- **`gspio verify --model` names a rollforward machine edited after export.**
  A compiled rollforward enters the graph only by its identity, so a body
  whose floor or operation was edited and the file resealed rebuilt the same
  graph, and verify agreed (exit 0) while the file ran another machine. The
  graph line now takes each published body's identity again (§12.1) before
  the rebuild decides, and disagrees, naming the compilation, where the body
  is not the machine its identity names. §13 says so.

- **The JAX engine refuses an `excel.edate` or `excel.eomonth` over a
  per-period date or months by name, as the reference producer does.** The
  producer refuses either held per period where the line is written
  (§11.1.33 states one of each per policy); the JAX engine, handed a document
  holding one, answered per period, so the two engines parted on a model the
  specification does not state. It now refuses from the record's declared
  shape before any book is read, and in the lowering where the operand is a
  calculation that declares no shape. §11.1.33 says so.

- **A NaN or an infinity written into an `is_in` set is refused by name.**
  `af.x.is_in([1.0, float("nan")])` was refused in the words of a signature
  mismatch, which the call is not. A NaN is a member of no set, so the
  refusal now says so and names the move, `af.x.is_in([...]) | af.x.is_nan()`;
  an infinity names `is_infinite()` with its sign. A non-finite argument to
  any other declared method (`fill_null(float("nan"))`, `clip(0.0,
  float("inf"))`) is named as the non-finite literal it is.

- **A lookup miss states no count.** The refusal said how many rows missed
  "in the batch it was handed": the lookup sees one batch of the frame at a
  time, so under the default streaming engine three misses spread over a
  book of 50,000 were reported as 1, and a number beside a miss is read as
  the frame's however it is worded. The message now names the keys that
  missed -- which find every row behind them -- and no count.

- **`excel.eomonth` moves a date a whole number of months, or refuses, as
  `excel.edate` does; and a month move over a run of periods is refused by
  name.** A months column of doubles that were not whole was truncated (1.5
  moved one month), text was parsed (`"2"` moved two, `"1.5"` answered a
  silent null) and `True` moved one, where the JAX engine refused every
  double. A whole double is now that number on every side; a fraction is
  refused by value, in the words `to_integer` uses, on Polars, the JAX engine
  and the reader; text and a flag are refused by kind where the line is
  written. An `edate` or `eomonth` whose date or months are held per period
  -- outside §11.1.33, which states one of each per policy -- failed when the
  frame ran with Polars' `cannot cast List type`; it is refused where the
  line is written, with the move.

- **An error block's `Graph:` line is about the failure, or is left out.**
  The graph folds the whole frame, so a type it cannot name anywhere on it --
  a `UInt64` holding a value past `i64`, a fixed-width `Array` -- silences its
  `Blocks:` and `Reading:` answers, and the block printed that refusal in
  their place even where the refused column was one the failing line never
  read: a list read that failed for its own reason went out under `Graph:
  Column 'big' holds 18446744073709551615 ...`. The line is now printed only
  where the refused column is the failing one or one its formula reads.

- **`gspio calc-graph` names a refused policy by the `--policy-id-column`
  it was told.** `run-model` and `run-single-policy` did; `calc-graph` ran
  the model outside that telling, so a book keyed by `pid` got
  `Policy: row 1` with no identifier under the same flag. It now reads
  `Policy: pid=B2 (row 1)`.

- **`is_in` of a NaN is false, on every side.** Membership is equality, and
  a NaN equals no member, so a NaN is a member of no set (§11.1.26): false,
  not the unknown a comparison with a NaN stores, and not null. Over a set
  written into the formula every side already answered so; over a per-policy
  set read from a column that held a NaN, Polars hashed one NaN equal to
  another and answered true. It answers false.

- **`gspio compare` names the document it was handed by its seal as well as
  its fingerprint.** The report carried the artifact's `graph_fingerprint`
  alone, so two exports of one model -- one fingerprint, two seals -- gave
  byte-equal reports that could not say which written document they were a
  comparison under, though §13.1 has every record citing a document carry its
  `document_digest`. The report now carries `document_digest` beside
  `artifact_fingerprint` (null where the document is unsealed); it is
  recorded, never compared, so the verdict does not move. The report grammar
  is `gaspatchio-graph-compare/v0-preview.2`.

- **`excel.pv` meets its 1e-12 at every nonzero rate, however near nought.**
  The kernel took `(1 + r) ** -n`, and `1 + r` rounds away a small rate's last
  digits: 360 payments of 100 and a future value of 1000 at `r = 1e-12` were
  8.9e-5 relative wrong (6e-9 at `1e-8`), and the answer stepped by 0.044 where
  the kernel switched to the flat form below `1e-12`. The discount factor is
  now `exp(-n·log1p(r))` and the paid-off fraction `-expm1(-n·log1p(r))` on the
  producer, the JAX engine and the reader alike, within 2e-16 of the exact
  answer on that grid; the flat form `-(p·n + F)` is the answer at a rate of
  nought only (§11.1.35). The two engines' `exp` and `log1p` are their own,
  so `excel.pv` now records a ratio in the JAX engine's agreement file.

- **`excel.edate` moves a date a whole number of months, or refuses.** A
  months column of doubles that were not whole was truncated (1.5 moved one
  month), text was parsed (`"2"` moved two, `"1.5"` answered a silent null)
  and `True` moved one, where the JAX engine refused all of them and §11.1.33
  says a signed whole number. A whole double is now that number on every
  side; a fraction is refused by value, in the words `to_integer` uses, on
  Polars, the JAX engine and the reader; text and a flag are refused by kind
  where the line is written.

- **A nested per-period comparison of whole numbers, or clip of whole numbers
  by a bound read from a column, grows with the lines written.** The exact
  comparison reads each side four or five times and the clip the value and
  each bound three times or more, so three levels deep were 58 kB and 15 kB of
  plan, growing geometrically. Each now holds its operands once (4 kB and 3 kB
  at depth three, linear), every answer and refusal unchanged, and the
  walk-through and the lowered facet write the operands back where they are
  read, so the record reads as it did.

- **A band compared with a label has one meaning, or is refused by name.**
  `af.age.cut([29, 59], labels=["under 30", "30 to 59", "60 plus"]) <
  "30 to 59"` answered the band's order per policy (`[1, 0, 0]`) and the
  letters' per period, on the JAX engine and in the reader (`[0, 0, 0]`), and
  the record could say only the second. An ordering of a band against text is
  now refused where it is written, on both shapes and every side, naming the
  two lines that each mean one thing (`af.issue_age < 30`, or `.to_text() <
  "30 to 59"`); two bands of different categories likewise. `==`, `!=` and
  `is_in` answer, a label outside the categories unequal and no member, and
  `is_in`/`replace` with such a label no longer stop the run in Polars' words
  (`conversion from str to enum failed`). A category against text still
  compares as its text (§11.1.26).

- **A null base raised to a run is a run of nulls.** `af.b ** af.run` with a
  null `b` answered a null outer list -- a policy with no periods -- where
  `af.b * af.run`, `+`, `-`, `/` and a null exponent all answer
  `[null, null]`, as §11.1.25 and the reader do.

- **`0 ** run` keeps a null period null.** A zero base raised to a per-period
  exponent sent a null period to the branch for a negative exponent, so
  `0 ** [2.5, null, 0.0, 1.0]` answered `[0.0, NaN, 1.0, 0.0]` -- a NaN no
  formula wrote, where §11.1.25 answers null at that position, as it already
  did for any other base.

- **A sum over a policy's periods is taken in period order, on every side.**
  `70000 // [0.2, -2.0, 0.2, 1.5].list.sum()` is `-700000` on Polars and the JAX
  engine, which both fold left to right; the kit's reader answered `-700001`,
  because Python's own `sum` of doubles is compensated from 3.12 and gives the
  exactly rounded total, whose floor is a whole step away. §11.1.14 now fixes
  the order for `sum`, `mean`, `cum_sum`, `cum_prod` and
  `remaining_sum`, the reader folds in it, and the kit publishes the case.
  Totals across policies keep the agreement band.

- **An empty sum is +0.0 on every side.** The total of a policy with no
  periods came back `-0.0` from Polars' list kernel, so `4.0 / af.r.list.sum()`
  was `-inf` where the JAX engine, the reader and Polars' own column sum answer
  `+inf`. It is now `+0.0`, and §11.1.14 says so. A run of one `-0.0` sums to
  `-0.0` on every side: the JAX engine and the reader started a sum from
  `+0.0`, which turned it positive, and now start from IEEE's `-0.0`.

- **A flag times a negative zero keeps the zero's sign on the JAX engine.**
  `af.flag * af.nz` with a false flag and `nz = -0.0` is `-0.0` by §11.1.25's
  "a flag is its 0.0 or 1.0", and `-3 / that` is `+inf`; XLA rewrote a product
  by a converted flag into a selection with a constant `+0.0`, so the engine
  answered `-inf`. The flag's product is now held apart from that rewrite,
  per policy and per period, and the kit publishes the case.

- **The reference reader keeps the sign of a floor that is a negative zero.**
  `0.0 // -2.0` is `-0.0`, and `1.0 / (0.0 // -2.0)` is `-inf` on both engines;
  the kit's reader answered `+inf`, because `math.floor` returns an integer,
  which has no negative zero. §11.1.25 lets the sign of a zero decide a
  division, and the kit now publishes the case.

- **A per-period extreme over a book the model's selection emptied answers
  nothing on the JAX engine.** `PeriodMin` and `PeriodMax` through
  `run_aggregated(engine="jax")` raised numpy's "zero-size array to reduction
  operation min which has no identity" when every policy was filtered out --
  a run-off cohort, a closed block -- where Polars, and the engine's own
  `PeriodSum` and `PeriodMean`, answered `[]`. Each extreme now starts from its
  identity.

- **The reference reader answers a whole number raised to a negative literal.**
  `af.term_years ** -1` is the double power of `term_years`, within §11.1.25's
  relative `1e-12` of `1 / term_years`, which both engines answer; the kit's
  reader refused it
  (`integer-power-exponent`) because it read the exponent's type and not
  whether the record wrote it as a literal. An exponent held in a column
  keeps the integer rule. The kit publishes the case per policy and per
  period.

- **`run_aggregated` folds a per-period whole-number column on its own.**
  `PeriodSum("claims_count")` over a count held per period was refused --
  "the model produced no List(Float64) column to reduce over" -- unless some
  other column of the model held decimals per period, and then the same fold
  answered; the JAX engine answered either way. The check read the model's
  whole output rather than the column folded. A per-period aggregator named
  on a column of one value per policy is now refused by name on
  `run_aggregated` and on a scenario plan, as the JAX engine refuses it,
  rather than in Polars' words from inside `list.len`.

- **A decimal clipped at a whole-number bound runs on the JAX engine.**
  `af.av.clip(lower_bound=0)` over one value per policy was refused before
  the book was read, "the answer's own type would not be on the record",
  citing §11.1.3 -- the clause that states the answer: a decimal value answers
  decimals whatever its bound is. Polars, the reader and the engine's own
  per-period form all answered. The bound is now read as its double; a
  whole number held between decimal bounds, which has two answers and is
  refused by the producer where it is written, is still refused by name.

- **A product is rounded before the sum that reads it on the JAX engine, so a
  threshold answers as it does on Polars.** XLA's CPU backend fused a multiply
  feeding an addition into one multiply-add, which rounds once where §11.1.25
  rounds twice. Inside the agreement band that is a place in the last digit;
  under a comparison, a `when`, a floor, `//` or `%` it is a whole step:
  `0.5 + 5 * 0.011 >= 0.555` answered 1 on JAX and 0 on Polars, a bonus paid
  at `prem >= 0.685` paid on one engine only, and a threshold at a spelled
  decimal over a grid of loadings, units and rates flipped in 4,450 of 68,000
  policies. Every product is now held apart -- the arithmetic `*`, the
  recurrence of `projection.accumulate`, a rollforward's growth and charge
  before its next step, the present value's weighting, and a curve's line
  between two knots, now written in the producer's own grouping rather than
  through `jnp.interp`. Tutorial levels 4 and 5 answer every line to the bit
  on Polars and JAX (33 lines differed by a place before), and the kit
  publishes one case for each.

- **A remainder of a product answers the producer's number on the JAX engine.**
  `(t * 12) % 12` -- a month's position in its year, rebuilt from a time in
  years -- let XLA fuse the product in the dividend with the remainder's own
  subtraction into one multiply-add, which rounds once where §11.1.25 rounds
  the product and then the difference. Month 13 came back at position 0, and
  395 of the months 0 to 1,200 took the neighbouring floor. The dividend is now
  held apart from the subtraction as the divisor's product already was, and
  the kit publishes the case per policy and per period.

- **A column shock whose condition selects no policy of the book is refused
  by name.** `FilteredShock(shock, where={"sex": "f"}, column="sa")` over a
  book whose policies hold `"F"` and `"M"` moved nothing and folded as BASE
  to the bit. It is now refused before the run, in `ScenarioRun` and in a
  shocks-dict `for_each_scenario`, naming the scenario, the condition and
  what the book holds, as a table shock whose condition selects no row of
  its table already is; a condition on a column the book lacks is refused
  naming the closest. The cost is stated in the refusal: a plan run on a
  sample book that lacks the segment is refused too, naming the condition.

- **An export whose sampled row holds a date past the calendar is refused by
  the column.** `excel.edate(1)` on an open-ended `9999-12-31` is year 10000,
  which the run holds as a count of days; the export, reading the sampled
  row's value as a date to write it as ISO-8601 text, raised the host
  language's `ValueError: year 10000 is out of range`, naming no column. It
  now refuses naming the column and the usual cause (section 11.1.33 puts such
  a result outside the domain).

- **An export whose sampled row holds a date or a timestamp the calendar
  cannot hold refuses by the column, never with a Rust panic.** Past about
  262,000 years from 1970 -- a millisecond or microsecond timestamp, naive or
  zoned, or a date, in the row the record samples, the millisecond values the
  identity check accepts included -- the engine's own conversion panicked
  (`PanicException:
  NaiveDateTime + TimeDelta overflowed`), which no `except Exception`
  catches, and `calc-graph` died with a Rust traceback; a zoned instant whose
  wall clock left the year 9999 raised a bare `OverflowError`. The sampled
  count is now judged before it is read, per policy and in every period of a
  per-period column, and anything outside the years 1 to 9999 refuses the
  export naming the column, on every path that samples a row.

- **`gspio diff --results` over a date or a timestamp the calendar cannot
  hold refuses by the column, never with a Rust panic.** The change report
  reads the results files' cells as values to write the cell that ranks a
  moved line, the policy the record declares, the policies' names and their
  timelines' start dates; a date or timestamp past about 262,000 years from
  1970 panicked there (`PanicException`), and one from the year 10000 raised
  `year 10183 is out of range`, naming no column. Each column whose cells
  the diff reads -- a compared line that moved, each identity column, and a
  `projection_start_date` that moved -- is now judged on its counts before it
  is read, and anything outside the years 1 to 9999 refuses the values naming
  the side and the column: `gspio diff --results` exits 2 with the refusal,
  and a diff over recorded results says the values were not compared and
  why. A line whose values held is measured by equality as the files hold
  it, reads no cell, and is compared whatever dates it holds.

- **An audit payload carries a list of dates, and states a date past the
  calendar unavailable.** A join whose right side held a `list[date]` or
  `list[datetime]` column died exporting (`Object of type date is not JSON
  serializable`); each element is now written as section 10's ISO-8601 text
  and `gspio validate` reads it back, so the payload re-hashes to its
  fingerprint. A table or join payload holding a date or timestamp outside
  the years 1 to 9999 was written as text no reader of that form reads
  (`+10183-01-01`), or panicked inside the engine past about 262,000 years
  from 1970; it is now the `unavailable` omission, with a warning naming the
  column, as a timestamp in a zone other than UTC already was -- in a list
  too. §15 says so.

- **An audit payload carries a non-finite float inside a list.** A join whose
  right side held a `list[f64]` column with a NaN or an infinity died
  exporting (`Out of range float values are not JSON compliant`): section 10's
  `"NaN"` / `"Infinity"` / `"-Infinity"` text was written for a scalar `f64`
  cell only. Each list element is now written that way, at any depth, and
  `gspio validate` reads it back to the float, so the payload re-hashes to its
  fingerprint. §13 says so. No identity moves.

- **The JAX engine names Polars for a join bringing a list or a date.** A
  join whose right side carries a `date`, `list[date]` or `list[f64]` column
  answers on Polars and refuses on JAX, which holds a joined column only as a
  number, a whole number, a flag or text. The refusal said the type was one
  "a payload cell is not", cited the lookup clause and sent the reader to
  re-export; it now names the join clause (11.1.2) and the move: run on
  Polars, or drop the column from the right side.

- **`Table.extend` extends a table held as an array.** `storage_mode="auto"`,
  the default, holds an ordinary table as a dense array, and `extend` refused
  every such table with a raw `RuntimeError` telling the reader to "use
  StorageMode::Hash" -- a Rust name no Python caller can pass -- so the
  method's own docstring examples failed. An array-held table is now built
  again whole from the extended rows after the same moved-table check, and
  its fingerprint is the one the combined source builds. A slice repeating a
  key the table holds is refused by name (the key and the move) on either
  storage, rather than as the native append's raw duplicate error.

- **A join whose right side cannot be hashed says why.** A right side the
  content grammar refuses -- a millisecond instant whose microseconds leave
  `i64`, refused by name -- is recorded with a null `right_fingerprint`, as
  §11.1.2 states; the refusal was logged at TRACE, so nothing said why. It is
  logged at WARNING now, in the refusal's own words, as a hole whose values
  cannot be stamped is. No identity moves.

- **Text a strict parse cannot read as a date is refused in the framework's
  words, and names its line on the streaming engine.** `af.t.str.to_date(
  "%Y-%m-%d")` over `"31/12/2025"` refused, as a strict parse must, in Polars'
  `conversion from `str` to `date` failed` with Polars' own advice, and under
  the default streaming engine lost the line that wrote it (the batch's counts
  and sampled values never matched the replay's). The refusal now opens with
  the column, a value that did not read, and the two ways through -- the
  format the text is in, or `strict=False` where some values are meant to be
  missing -- and a strict cast of a column is matched across batches by the
  column and the two types it names. The engine's line stays beneath it.

- **A position one policy's run does not hold is refused in words that name
  the run, the policy and the way through.** `af.last_av = af.av.list.get(36)`
  over a book holding a 24-period policy, a missing run or a missing position
  failed with Polars' `get index is out of bounds` over an expression dump.
  The refusal now opens with a sentence naming the column read, what has no
  value to give, and the move (test the position against `.list.len()` in a
  `when()`, read the last period with `.list.get(-1)`, or fill the missing
  run or position), and the report names the first policy it stops at on
  either engine. The engine's line stays beneath it.

- **A refusal of an id two rows carry never names the export's own row
  stamp as the way through.** `calc-graph --policies P2` over a book where two
  rows carry `P2` recommended `--filter "col('__gaspatchio_export_row__') ==
  1"`: the stamp separates every row by construction, so it was always the
  column found, and taking the advice put the stamp on the wire. The stamp is
  passed over; where no column of the book separates the rows, the refusal
  names `--policy-id-column` and a `:N` slice (`'1:2'`), which works and
  writes no stamp.

- **A refusal the plan raises names its line on the streaming engine and in a
  book of more than ten thousand policies.** A sum, running sum or product, a
  remaining sum, an absolute value, a clip, a rounding or a conversion that
  refuses a value while the frame runs -- `af.units_t.list.sum()` past `i64` --
  carried the `Failing column / Defined as / At` block in memory and lost it
  under the default streaming engine, whose failed-value count is its batch's
  (`1 out of 3 values`) where the replay that finds the line counts its own
  (`1 out of 12`); a refused policy past the replay's first 10,000 rows lost it
  on either engine. The line is now found by the refusal's own sentence, which
  is the same in every batch and is written into the one calculation that
  checks it; where two calculations carry the same sentence neither is named.

- **A maths call over a flag answers the producer's double on the JAX engine on every
  platform.** `exp`, `log`, `log10`, `log1p`, `sqrt`, `cbrt` and `norm_cdf` over a
  flag answer one of two values, the call at 1.0 and at 0.0, and the JAX engine
  now answers them from those two values written as the doubles nearest e, ln 2
  and Φ(1) (the rest are whole numbers or −∞) rather than computing them. On
  Linux, XLA's CPU `exp` answered 2.7182818284590455 at 1.0 where the producer
  answers e, 2.718281828459045, so `exp` over a flag disagreed by one place in
  the last digit there and not on macOS. Over a number the calls are unchanged
  and held to §11.1.12's tolerance as before.

- **The page keeps up with the period slider on a slower machine.** A step of
  the row cursor redrew parts of the page that do not read the period -- the
  search box and the identity strip, React Flow's whole tree under the cone,
  every part of a cone box whose value line changed, the Node tab's record and
  the walk for what the column reaches -- and laid the page out twice, once
  for the grid following the cursor and once more for the cone's value lines;
  and on Linux, where Chromium draws text for an LCD panel, the grid was
  scrolled by painting it again, so each row it followed the cursor down
  repainted the grid's whole area. A step now redraws what it moves, the follow
  lays the page out once and not at all while the cursor's row is in sight,
  and the grid scrolls as a layer of its own, as it already did on a Mac. The
  page draws exactly what it drew.

- **The JAX engine's `round` past 22 places answers the producer's double on
  every platform.** Past 22 places both engines scale the value, round it to a
  whole number and scale back. The producer scales by ten raised the way
  Rust's `powi` raises it, squared and multiplied with every product rounded;
  the JAX engine scaled by the host's `pow`. The two part company at 252 of
  the place counts from 33 to 308 on macOS, where a correctly rounded `pow`
  gives the double nearest the power and `powi` does not, and on Linux at 23
  places as well, where ten to the 23rd lies halfway between two doubles and
  glibc's `pow` takes the other one: `round(2.5e-23, 23)` answered 3e-23 on the
  JAX engine and 2.0000000000000002e-23 on the frame. The engine now scales by
  the producer's own power, which is one double on every machine.

- **The comparison page names a hole whose stamp moved, the lines under it,
  and the model's own files.** `gspio diff --html` derives its comparison in
  the page from the two documents, and the page had no `hole` kind: an edit to
  a file the model's setup joined showed as columns marked *data* with
  "nothing in the record explains this move", while `gspio diff` named the
  hole. The page now lists the hole underneath the model, between the book and
  the handed-over columns, in the report's words where a side has no stamp;
  marks each line that reads it as moved by that hole, with no note owed; lets
  a moved book outrank it; prints the report's `hole` cause in the book-wide
  reading; and states the model file and each helper module that moved, under
  "the model's own files", never counted as a change (14.2).

- **A door that resolves the plan, after a fragment Polars cannot type,
  names the line that broke.** After `af.band = pl.col("code") * pl.col("sa")`
  over a text column the plan no longer resolves, and `projection.set`,
  `select`, `rename` and `drop`, which resolve the whole plan at their own
  line, raised that break there in Polars' words, naming no line, so the
  healthy line read as the one at fault. Each now raises the break before it
  runs, through the same handler `collect()` uses, naming the column and the
  line that broke, with a note that the door was not run; `with_columns`,
  which already named the line, adds the note. A door whose own expression
  fails still fails as its own.

- **`gspio diff` names a helper module that moved, and a line moved by a
  hole's stamp names the hole.** A helper the model imports is listed in
  `model.modules` with a stamp of its bytes, and the change report never read
  it: a comment in a helper showed nowhere, and a constant edited in one was a
  changed calculation with no line naming its file. The report's `source` now
  carries `modules`, each helper whose stamp moved (paired by its place beside
  the model file), stated on its own line and never counted as drift, so a
  helper-only edit still exits 0. And with the two results files read, a line
  whose numbers moved under an unmoved definition because a hole it reads
  changed its stamp -- the side file a 0.9 setup joined, edited -- was labelled
  `unexplained`; it is now `cause: "hole"` with `holes` naming it
  (`pv_prem` 400 → 440.00000000000006 under `hole load`), while a line that
  reads no moved hole keeps the comparison's cause and a moved book still
  outranks it (14.2).

- **The JAX engine folds a run of flags in whole numbers, and keeps a
  whole-number `remaining_sum` whole.** `sum`, `mean`, `cum_sum` both ways,
  `cum_prod` and `projection.remaining_sum` over a per-period Boolean column
  were refused by name before the book was read, where the producer and the
  reference reader count the flags (`[True, False, True, True].list.sum()`
  is 3, an `i64`; the mean 0.75). They now answer the producer's values and
  types, and so do `min` and `max`, which answer the flag they choose (`bool`:
  whether every period was set, whether any was). And
  `remaining_sum` over a run of whole numbers, which the record types
  `list[i64]`, was computed in doubles and refused as a widened type: it now
  takes `cum_sum(reverse=True)`'s checked whole-number total, exact past
  2**53 (`[2**53 + 1, 2]` answers `[9007199254740995, 2]`), and refuses a
  period past `i64` by name (`i64.range`), as the producer does. Two kit
  cases move: one to a value, one to a refusal for the reader's reason.

- **A lookup's comparison named with `.alias()` stores its indicator.**
  `af.with_columns((table.lookup(age=af.age) > 60).alias("over_60"))`, and
  the same in `select`, lost the name when the test was rebuilt as the
  comparison it is, so Polars named the indicator after the lookup's key
  column and the frame refused the line for writing over it. The name is
  kept, and the column stores the `f64` indicator assignment stores (11.1.26).

- **Arithmetic between a duration and a number is refused where it is
  written.** `af.term = af.maturity - af.issue` is a duration, and
  `af.term + 1`, `af.term // 12`, `1 / af.term` and every pairing beside a
  run of durations but a scale by a written number failed only when the
  frame ran, in Polars' words (`+ not allowed on duration[μs] and i64`). The
  line is now refused at the assignment, naming the duration and the count
  to write instead (`.polars_native().dt.total_days()`), since the
  vocabulary has no time-delta type (11.1.25). A duration times a number,
  or over one, still answers as before.

- **A line written after a fragment Polars cannot type reads the types the
  model wrote.** After `af.band = pl.col("code") * pl.col("sa")` over a text
  column the plan no longer resolves, and a frame of fewer than sixteen
  columns kept the schema from before that line: a `code` recast to a number
  was still read as text, so the healthy `af.out = af.code * af.sa` was
  refused as text times a number, naming the wrong line, while a number
  column overwritten with text was let through. Each assignment now types its
  own column into the cached schema once the plan stops resolving, as a wider
  frame always did, and a column it cannot type is unknown rather than read
  at its old type. The break itself still fails at `collect()`.

- **`gspio calc-graph --portfolio` folds the book whole, on every machine.**
  The fold ran the model again through `run_aggregated` with the batch size
  left to the memory budget, whose seed is a tenth of the book, so a model
  whose setup collects and rebuilds its frame (`mp = af.collect()`, a join in
  Polars, `ActuarialFrame(mp)`) was refused under `--portfolio` on a book of
  three policies, and on a larger book whether it was refused depended on the
  reviewer's memory. The command's own run already holds every policy at
  once, and the fold now runs the book as one batch: the same total on every
  machine, the setup folded rather than refused (7.4).

- **`gspio diff` names a hole whose stamp moved.** A column the model's setup
  joined in plain Polars and rebuilt with `ActuarialFrame(mp)` is a hole that
  carries a stamp of what it held, and an edit to the joined file moves
  `graph_fingerprint` and no node digest. Read node by node, the two documents
  differed in nothing, so `gspio diff` printed "nothing moved" and exited 0
  over two different fingerprints. The change report now compares the holes
  both documents list on their stamps: a moved stamp is a `data` entry of
  kind `hole` naming the column, with the two stamps, and it is drift (exit
  1); a hole stamped on one side only is written with a `reason` saying the
  two could not be compared (14.2).

- **A rounding of a rounding answers, and its plan grows with the calls.** The
  exact roundings read their operand many times -- a whole number's figures
  are counted against eighteen powers of ten -- and each read wrote the
  operand's whole expression out again, so a call over another call's answer
  multiplied the plan: `af.a.round_sig_figs(3).round_sig_figs(2)` over an
  `Int64` column was 47.9 MB of plan and "round each component, then the
  total", `(af.a.round_sig_figs(3) + af.b.round_sig_figs(3)).round_sig_figs(3)`,
  93.2 MB, and neither answered in a minute or 4 GB. The same held, more
  slowly, for `round_sig_figs` of a double (three levels took 14 s on 1,000
  rows) and `round` to a step either side of the point. Each now holds its
  operand once, as a struct field, and reads the field: every value is the
  same to the bit, and the plan grows by one call's steps per call -- the
  rounded total answers in 0.07 s. The engine's own rendering of such a node
  (the non-normative `gaspatchio_lowered` facet) now shows the struct.

- **The conformance kit publishes whole numbers at the edges, a stored lookup
  comparison and a null run in a branch.** Twenty-eight cases join the
  reviewed boundaries (764 published): `floor`, `ceil`, `abs`, `sign` and
  `round_sig_figs` of a whole number past 2**53 and at the edge of `i64`,
  answering every digit; `sum`, `cum_sum` both ways, `cum_prod` and
  `remaining_sum` over such runs, exact, with a total that fits answered
  where a running total on the way passed `i64`; `sqrt`, `cbrt`, `exp`,
  `log`, `log10`, `log1p` and `mean` of whole numbers answering `f64`; five
  refusals past `i64` (`integer-overflow`), the absolute value of `-2**63`
  among them; a comparison of a table lookup stored as the `f64` indicator;
  and a null run in the selected branch, the unselected one and beside a
  per-policy condition, each nulling the policy. The reference reader passes
  every case. The JAX engine answers 19 of them and refuses the rest by name:
  the five refusals with the reader's reason, and the running total past
  `i64` and the null runs as its README says.

- **The conformance kit publishes a run of flags' least and greatest, and the
  calls refused over a duration.** `vectors/flag-extremes.json`: `min` and
  `max` over a run of flags answer `bool` (whether every period was set,
  whether any was), never the 0 or 1 the totals count.
  `vectors/duration-refusals.json`: the thirteen maths calls other than
  `abs`, plus `cum_prod` and `cumulative_survival`, over a duration per policy
  and per period, each refused (`duration-read-as-a-number`); the envelope
  gains `duration` and `list[duration]` as input-only names, and the reference
  reader refuses the same calls. Twenty-eight cases (828 published).

- **The conformance kit publishes `excel.eomonth`'s months as it publishes
  `excel.edate`'s.** `vectors/date-excel.json` gains a whole double (that
  number of months, then the month's last day), a fraction
  (`checked-integer-conversion`) and a flag (`calendar-months-kind`). The JAX
  engine's runner matched `calendar-months-kind` only in `edate`'s words, so
  an `eomonth` flag refusal read as a mismatch; a cause can now be named in
  either operation's words. Three cases (831 published).

- **The conformance kit publishes NaN membership, and its reader no longer
  counts a NaN a member of a set holding that NaN.**
  `vectors/existing-contracts.json` gains `is_in` of a NaN against a written
  set, per policy and per period (false, §11.1.26), and against a set held per
  policy that holds a NaN (false too). The kit's reader matched membership with Python's `in`,
  which tries identity before equality, so a NaN was a member of a set holding
  the very NaN it was decoded to and answered true; it now compares member by
  member. A NaN written into a set literal has no document form -- a vector
  cell's non-finite tag is never an operation literal -- and the producer
  refuses it where the formula is written, so it has no case. Three cases
  (844 published).

- **The conformance kit publishes a comparison report citing the corpus by its
  seal.** `conformance/citations.json` carries two reports the producer writes
  over the §12.5 corpus: one handed the corpus, and one handed another export
  of the same model (one fingerprint, another seal). `reader.pyz --citation`
  recomputes the corpus's seal from its bytes and finds the first citing it
  and the second citing another document, as §13.1's citation rule asks of
  every record that points at a document it does not enclose. Two cases.

- **The conformance kit publishes the content grammar's bytes, the datetime
  carrier first.** `conformance/content-identity.json` describes frames in
  plain JSON with the bytes section 12.3 writes for them and their digest:
  one instant in ms, µs and ns writing one encoding, a UTC column writing as a
  naive one, the zone in the column's header and behind a `list[datetime]`'s
  element tag, nanoseconds past the earlier microsecond (`-1` ns, `i64`'s
  least, two instants 500 ns apart), a missing value, and the section's worked
  example. `reader.pyz --content` re-derives every case with the standard
  library. Eleven cases.

- **Arithmetic between a number and text or a date is refused where it is
  written.** `af.n * af.code` over text, `af.issue + 1` over dates,
  `-af.code` and `af.rate * "10"` each failed only when the frame ran, in
  Polars' words (`arithmetic on dtypes str and i64 is not allowed`, `cannot
  add two list columns with non-numeric inner types`). The line is now
  refused at the assignment, naming the operand, its kind and the number to
  write instead (11.1.25); a fixed-point decimal never reaches the line (see
  Breaking: it is read as its double where it enters). An operand that is
  itself arithmetic is typed too, so `af.issue + (af.term * 365)` is refused
  as `af.issue + af.term` is, naming the operand as written, where it failed
  in Polars' `+ not allowed on date and i64`. Two values neither of which is a number, such as two dates,
  are left to the engine; a clash inside a Polars expression written by
  hand still surfaces when the frame runs, with its failing column named.
- **A fold of one policy's own periods in Polars is left to run.**
  `pl.col("reserve").list.agg(pl.element().sum())` assigned to a frame with a
  projection timeline was refused as a cumulative evaluation that runs down
  the rows; `list.agg` reads one policy's own list, as `list.eval` does, and
  only `cumulative_eval` reads the policies above it.

- **An executable record of a plan that cannot be typed is refused, not
  written untyped.** A model whose plan Polars cannot type -- arithmetic
  over text, say -- exported without results as an executable record whose
  every column said `dtype: unknown` and none was in the final schema; the
  JAX engine ran it and handed back the book's own columns, no answer and
  no refusal. The executable export now refuses by name, quoting the
  engine's reason and naming `af.collect()` to find the line; an audit
  record, which no engine runs, is still written for the reader.

- **A conditional with a flag beside a double exports as the double it ran
  as.** `when(af.smoker == "Y").then(False).otherwise(3.25)` ran and answered
  `Float64`, but the frame recorded no type for it, and the export refused
  the model, calling the column "type Unknown". The flag is read as its
  0.0/1.0 double beside a double, as beside a whole number or a fixed-point
  decimal, so the frame's schema, the record (`f64`), the JAX engine and
  the reference reader agree.

- **A book holding policies with no run no longer panics the engine.**
  `(af.pols * af.prem).round_sig_figs(3)`, with one side of the product
  absent for some policies, raised a Rust `PanicException` on the
  in-memory engine, and `cumulative_survival()` over a book whose first
  policies had no run raised one on the streaming engine; a panic walks past
  `except Exception`. Both answer now, on both engines, a policy with no run
  answering null.

- **A per-period value can be filled by a per-policy column.**
  `af.premium.fill_null(af.scheme_default)` over a per-period premium
  failed as `SchemaError: failed to determine supertype of list[f64] and
  f64`; every missing period of the policy now takes the policy's own
  default, as `fill_nan` already did, on both Polars engines and as the
  reference reader answers it. A per-period fill for a per-policy value is
  refused by name rather than in Polars' words.

- **The absolute value of `-2**63` is refused by name, and a run of flags
  totals to the `i64` its record names.** `abs` over an `i64` holding
  `-2**63`, per policy or per period, answered `-2**63` -- a negative
  absolute value -- where its absolute value 2**63 has no `i64`; the run now
  stops naming the column, as the reference reader refuses it. A per-period
  `sum`, `cum_sum`, `cum_prod` or `remaining_sum` over a stored True/False
  run answered `UInt64` or `List(UInt32)` while the record said `i64`; it
  answers the `Int64` count the record names.

- **A per-period clip of whole numbers keeps whole numbers whatever its bound
  is.** `af.duration.clip(upper_bound=af.cap)` answered `list[f64]`
  (`[0.0, 5.0, 10.0]`) where `clip(upper_bound=10)` kept `list[i64]`; the
  record said `list[f64]`, the JAX engine followed it, and the reference
  reader answered `list[i64]`. A bound read from a per-policy or a
  per-period column now answers the run's own whole numbers on both Polars
  engines, the record names `list[i64]`, and the JAX engine and the reader
  agree. That route holds the values in doubles, so a value or bound at or
  beyond 2**53 in magnitude is refused by name rather than compared as its
  nearest double; a literal bound holds every whole number exactly.

- **A policy with no run compares to null on either side of a comparison.**
  `af.av < af.gmdb`, with one policy's `gmdb` run absent, answered
  `[None, None]` for that policy where `af.gmdb > af.av` answered null, and
  a `when` on it the same; so a `fill_null(0.0)` and a total gave 0.0 or
  null depending on the order the comparison was written in. A null outer
  list now answers null as the right-hand operand of every comparison and
  of a conditional's comparison, per period, on both Polars engines, as it
  does on the left and as the reference reader answers it.

- **The maths calls over a flag answer its 0.0 or 1.0, on both engines and in
  the reference reader.** `abs`, `sign`, `sqrt`, `cbrt`, `exp`, `log`,
  `log10`, `log1p`, `norm_cdf`, `round_sig_figs`, `round`, `floor` and `ceil`
  over a stored True/False column, a comparison, or a test combined with `&`,
  `|` or `~` read the flag as the 0.0/1.0 it reads as in arithmetic and answer
  a decimal column, per policy and per period: `af.in_force.sign()` is
  `[1.0, 0.0]`, `(af.age > 60).round()` is the indicator, and the log of a
  false flag is minus infinity, as of any 0.0. On 0.9.0 the frame cast six of
  them (`sqrt`, `cbrt`, `exp`, `log`, `log10`, `log1p`) and failed on the other
  seven in Polars' words (`sign operation not supported for dtype bool`), every
  one failed on a per-period comparison, and the JAX engine refused them over
  a Boolean by name -- except `sign` and `norm_cdf`, whose line the frame
  could not type, so a JAX run of the record came back without the column and
  nothing said so. Each is now answered alike, to the bit, on both
  Polars engines, the JAX engine and the reference reader, which typed nine of
  the answers `bool` and could not take the logarithm of nought. A comparison
  carries these thirteen methods, where `(af.k > 2).round()` raised Python's
  own `AttributeError`; any other column method on a comparison is refused by
  name, naming the two ways to say whether the truth value or the indicator is
  meant. The JAX engine's refusal of `floor` or `ceil` over a value outside
  its domain names the call, where it said `round`. The conformance kit gains
  26 cases (736 published).

- **A per-policy table lookup answers every operator as the column it would be.**
  A lookup, a schedule read or a rollforward read the frame hands back kept
  Polars' own operators per policy: `table.lookup(age=af.age) & 1` failed in
  Polars' words (`bitand operation not supported for dtype f64`) where a column
  refuses it by name, `lookup ** True` and `True ** lookup` failed in Polars'
  words where a column answers them, `lookup ^ 1` was refused at assignment as
  an engine fragment hiding the table, and the expression's own quotient by a
  literal, read in plain Polars, was Polars' product by the reciprocal
  (135.021 / 1000 came back 0.135021, where the column, the record and the JAX
  engine answer 0.13502099999999997). Each operator is now the frame's, as it
  already was per period. A comparison on a per-policy lookup is still a
  Polars expression, marked a comparison, so `&` and `|` read it as a test
  even where the value's type is known only when the frame runs. Writing a
  line on a lookup costs about 0.4 ms more; running it costs the same.

- **The reference reader reads a stored flag in arithmetic as the 0 or 1 it
  indicates.** Section 11.1.25 reads a Boolean operand of arithmetic as 1.0
  for true, 0.0 for false and null for null, per policy and per period, on
  either side and under every operator. The producer and the JAX engine
  answered `af.b * 1.0` as `[1.0, 0.0]`; the reader refused the record
  (`numeric-operands-required`) for a stored Boolean column, a run of them,
  and a `True` written into the formula. It now answers them, and refuses a
  per-policy Boolean on both sides of one operation
  (`boolean-on-both-sides`), as the producer does. `reader.pyz` is rebuilt;
  `index.json` and the vectors are unchanged.

- **The reference reader answers each line in the type the producer's record
  names.** The reader's `verify` checks a result's type before its values, so
  a label that contradicts the record fails a conforming producer. It typed
  `sqrt`, `cbrt`, `exp`, `log`, `log10` and `log1p` of a whole number `i64`
  while it held doubles (`af.age.sqrt()` is `f64` in the record), typed
  `list.mean` of a whole-number run `i64` (100.75 under an `i64` label), and
  kept `fill_null` of a whole number with a double `i64`, where section 11.1.13
  says `f64`. It also held a whole number under an `f64` label -- a fill of 7,
  a clip bound of 0, `excel.round` of a whole number, a `with_period` value, a
  survival opened at 1 -- or a flag under an `i64` one, which a comparison of
  values cannot see, since 2 equals 2.0. Every label is now the record's type
  and every value is held as it; a running sum, product or remaining sum over
  a run of flags is `list[i64]`, as the record says; and `verify` fails a case
  whose answer is held as another type than its label, so a reader that
  slipped again would be caught by the kit rather than pass on equal values.
  No published vector moves; `reader.pyz` is rebuilt.

- **The reference reader keeps a whole number's every digit, and refuses one
  past i64 by name.** `floor`, `ceil`, `abs` and `sign` of a whole number, and
  `sum`, `cum_sum`, `cum_prod` and `remaining_sum` over a whole-number run,
  went through doubles and lost digits past 2**53: `floor` of 2**53 + 1 was
  2**53, and `[2**53 + 1, 2**53 + 1]` summed to 18014398509481984 where the
  record and both Polars engines answer 18014398509481986. `round_sig_figs`
  put the sign back through a double, so 2**62 to seventeen figures came back
  unrounded and 2**63 - 1 to seventeen figures, 9223372036854775800, was
  refused. Each is now whole-number arithmetic, to the digit. An answer an
  `i64` does not hold -- `[2**63 - 1, 1].list.sum()`, a running product past
  it, `abs` of -2**63 -- is refused (`integer-overflow`) where the reader
  answered a double; the producer wraps these, which section 11.1.25 says is
  no portable guarantee. A whole number past 2**53 meeting a double fill in
  `fill_null` or `fill_nan` is refused as it is in arithmetic, and a decimal
  `clip` bound on a whole number is refused, as the producer refuses it. No
  published vector moves; `reader.pyz` is rebuilt.

- **`round_sig_figs` keeping no figures is refused where it is written.**
  `round_sig_figs(0)` (or a negative count) failed in Polars' words on a
  decimal and answered 5 as 10 on a whole number; it is refused naming the
  declared form, a whole number of at least one, and the reader refuses both
  records.

- **Every operator on a value the frame hands back answers, or is refused in
  gaspatchio's words.** An operator a value's class did not define fell
  through to Python. An unfinished `when(...).then(...)` compared with
  anything answered Python's `False` or `True`, and used in arithmetic, as a
  stored column or as another chain's condition it was refused in Python's or
  Polars' words; it is now refused wherever it is used as a value, naming
  `.otherwise()`. `^` raised Python's own `unsupported operand type(s)` on a
  column, an expression, a comparison or a mask, and Polars' words beside a
  lookup; the vocabulary has no exclusive-or, and it is now refused naming
  the comparison that writes "one test or the other, not both" (`(a > 1) !=
  (b > 2)`). `+af.x` raised Python's own TypeError and now answers `af.x`.
  And a number raised to a lookup's power, `1.05 ** table.lookup(age=af.age)`,
  recursed until Python gave up; it answers.

- **A comparison compared answers a column, where `==` and `!=` answered
  Python's own `False` or `True`.** `af.r = (af.k > 2) == 1` stored a column
  of `False` on every policy and raised nothing: the comparison's wrapper had
  no comparison operators, so `==` and `!=` fell through to Python's identity
  test, against a number, a flag, `True` or another comparison, in either
  order and per policy as per period, and `<`, `<=`, `>` and `>=` raised
  Python's own TypeError. A lookup compared with a comparison answered the
  same Python `bool`. Each comparison on a comparison is now the declared
  one, recording one comparison over the other, and answers as a stored flag
  compared does: per policy by its truth value, per period by its 0.0/1.0
  indicator, which the frame read in Polars' words before (`could not
  evaluate '>=' comparison`). The JAX engine and the reference reader answer
  the record alike.

- **An arriving column the model renamed, dropped or wrote over is typed
  in the record as it arrived, from either door.** A book handed over as a
  `LazyFrame` with a `UInt64` policy number renamed on the way in
  (`af.rename({"pid": "policy"})`) was refused at export on the width
  alone, where the same book as a `DataFrame` exported, and the frame
  collected the renamed column as `UInt64` from the one door and `Int64`
  from the other; dropped, its input leaf was `unknown` from the one door
  and `i64` from the other. And an input leaf took the type of whatever
  later held its name -- `af.n = af.n * 1.5`, or `af.pid = af.x * 2` after
  `pid` was renamed or dropped -- so an `i64` field was recorded as `f64`.
  Each is now typed as the data arrived, a wide column on the values read
  off the book: `i64` where they fit, refused naming the value where the
  model holds one past `i64`, and `unknown` (history) where it dropped one.
  A model that writes an arriving column over with a different type
  records a different leaf type, so its graph fingerprint moves.

- **The reference reader refuses a whole number past 2**53 beside a double
  in a conditional, as it refuses the same pair in arithmetic.** Section
  11.1.28 admits an `i64` branch beside an `f64` one only within the exact
  integer-conversion range; the reader refused `k + x` and a flag beside
  such a `k`, but answered `when(c).then(k).otherwise(x)` with `k` at
  2**53 + 1 as the double 2**53, where the JAX engine refuses the line by
  name. It now refuses the pair over every value of both branches, per
  policy as per period. The reference producer rounds such a value to its
  double, as it does `k + x`. No published vector holds the pair, so no kit
  result moves; `reader.pyz` is rebuilt.

- **A comparison in arithmetic reads as its 0.0/1.0 indicator with the
  comparison on either side.** `af.x * (af.k > 2)` answered, but
  `(af.k > 2) * af.x`, `(af.k > 2) * 1.0`, `1 - (af.k > 2)`, two comparisons
  added, and `-(af.k > 2)` raised Python's own `unsupported operand type(s)
  ... 'ConditionExpression'`, per policy and per period: the comparison's
  wrapper carried the logical operators and none of the arithmetic ones.
  Each arithmetic operator on a comparison is now the declared one, and
  answers `f64`, as a flag beside a number does; the JAX engine and the
  reference reader answer the record alike.

- **A per-period selection between decimals answers the decimals it
  selected, at any number of places, where it answered a run of nulls.**
  `when(af.month >= 1).then(af.a).otherwise(af.b)` over two
  `Decimal(38, 20)` columns answered `[None, None]` for every policy, and so
  did any value held to `s` places with `38 - 2s` whole digits or more --
  from 0.01 at twenty places, from 1 at nineteen, from `10**34` at two --
  beside another decimal, a whole number or a `None`: the selection held
  each decimal as its digits and read them back through a product Polars
  takes at the decimal's scale, which holds nothing past `10**(38 - s)`
  units. The digits are now read back exactly, so the
  per-period form answers what the per-policy form answers. A decimal beside
  a whole number, or one of fewer places, answers in the decimal type Polars
  gives the pair, and a value that type cannot hold -- `2**62` beside twenty
  places needs thirty-nine digits -- is refused by name on both routes, where
  Polars refused it in its own conversion text.

- **A refusal names a date-and-time literal by its value, not as "an
  expression".** `af.zoned > datetime(2025, 1, 1)` is refused because one
  side names an instant and the other a clock reading with no place; the
  sentence called the literal "an expression", though the author wrote one
  value on the line. It now names it by that value
  (`datetime.datetime(2025, 1, 1, 0, 0)`), as a number or a date written
  there is named, and so does every refusal that names its operands.

- **A book handed over as a `LazyFrame` exports, fingerprints and runs on an
  engine when its `UInt64`, `Int128` or `UInt128` column fits `i64`, as the
  same book handed over as a DataFrame does.** The DataFrame door reads such
  a column as `Int64` where every value fits; the lazy door has no values
  in hand there, and an export with no results read none either, so the
  column's input leaf was refused on its width alone (`Column 'pid' has type
  UInt64, which the calculation graph has no name for`) and
  `af.collect(engine="jax")` failed with it. The export now reads such a
  column off the book as it arrived, as the book's digest already does, and
  names it on its numbers: both doors write one document. A value past
  `i64` in it is refused naming the value, from either door, where the
  DataFrame door named only the width. A calculated column of such a width
  has no book to be read from and is still refused on its width when no
  results are in hand.

- **A constant past `i64` assigned as a column is refused in the formula's
  sentence.** `af.c = 2**64` reached Polars, which refused it in its own
  words (`conversion from i128 to i64 failed in column 'literal'`), where
  the same number written into a formula is refused naming it and the two
  moves -- `to_text()` for an identifier, a decimal literal for a quantity.
  The assignment door now gives it that sentence, as an
  `IntegerLiteralPastI64Error`, for a Python or a NumPy whole number alike;
  a constant at either end of the range is stored as before.

- **`run_aggregated` and `run_to_parquet` take a book handed over as a
  `LazyFrame`, as a scenario plan does.** `pl.scan_parquet` hands back a
  `LazyFrame`, and both runners failed inside with `'LazyFrame' object has no
  attribute 'height'` while `ScenarioRun.run(ActuarialFrame(lazy), ...)` ran.
  Each now collects the book at its door and runs it as a DataFrame,
  judging a wide integer column over the whole book; a book of any other
  type is refused with a `TypeError` naming the two it takes.

- **A filter on a rollforward's state runs.**
  `af.filter(compiled.expr_for("av").list.get(0) > 0)` failed in both Polars
  engines with `ColumnNotFoundError: '__rollforward_<fp>'`, because the filter
  never put the run on the plan. It now keeps the policies the condition holds
  for, records its selection step by the state's own tree -- reading the
  compiled rollforward's node, never its hidden column -- and is refused from
  the executable profile, and by `af.collect(engine=...)`, naming the step,
  its line and the state as the author wrote it (`the rollforward state 'av'`,
  with the run's node id beside it), as a filter on any calculated column is
  refused by its column. An error inside a run
  whose only reader is such a filter reaches the user as the kernel's own
  sentence, with no line wrongly named.

- **A model whose only step is choosing its policies exports.** A frame that
  filtered, or semi or anti joined, and calculated nothing was refused as
  "No calculations found". It now exports with its selection, the book columns
  it reads and no calculated node, in both profiles, and an engine replays it.
  A frame that neither calculates nor selects is still refused.

- **`af.head()`, `af.tail()`, `af.limit()`, `af.slice()`, `af.unique()`,
  `af.drop_nulls()` and `af.drop_nans()` say why they are not model steps.**
  Each failed as "If 'head' is a column name, use af['head'] instead". Each
  now says that a model chooses which policies it values by a condition the
  record states, and names `af.filter(...)` or the cut made on the model
  points before the frame is built. A column with one of those names is still
  reached as `af.head`.

- **`af.sample()`, `af.top_k()`, `af.bottom_k()`, `af.gather_every()` and
  `af.remove()` say what to write instead.** They too failed as "If 'sample'
  is a column name, use af['sample'] instead". The first four now say why
  they are not model steps -- a random choice, a ranking that rests on the
  other rows, a position -- and name `af.filter(...)` or the cut on the model
  points. `af.remove()` names `af.filter` with the condition for the policies
  kept, and with its null test beside it where, as Polars' `remove` does, a
  policy whose condition is null is to stay.

- **A filter whose condition answers once a period is refused where it is
  written.** `af.filter(af.x > 0)` with `x` per period reached Polars, which
  failed with ``SchemaError: could not evaluate '>' comparison between series
  'x' of dtype: List(Float64) and series 'literal'`` (a per-period null test
  with "filter predicate must be of type `Boolean`, got `List(Boolean)`").
  `af.filter` now says that a selection keeps or drops whole policies, names
  the per-period column or rollforward state, and names the reductions to
  one value per policy -- `af.x.list.get(0) > 0`, `af.x.list.min() > 0` for
  every period, `af.x.list.max() > 0` for any -- or the cut on the model
  points, or `when(...)` to leave periods out instead.

- **The audit file says which library produced its numbers.** A record
  stated `producer: {name: gaspatchio, version: ...}` and nothing else: the
  extension, Polars, Python and the platform were only in a results file's
  Parquet footer, and an editable install -- core 0.9.0 over a 1.0.0
  extension -- looked like a release. Every export now writes
  `producer.versions`, the six keys a results file's manifest states (one
  run, one set), and `imports`, each installed package the model imports
  with its version -- an in-house package as much as `numpy`. `gspio
  verify` adds a `versions` line holding them against this process, and
  against the results file's manifest under `--results`; it moves no exit
  status. `gspio diff` prints one `library:` line where two documents'
  versions differ, with no data entry and no change of exit status.
  `GraphExporter.export(versions="withheld")` and `gspio calc-graph
  --no-versions` record them as withheld, for a document committed as a
  golden. A scenario run's sidecar states the same six keys, with
  `ddsketch_version` beside them, in place of `library_version`.

- **A record with no git revision says why.** `model.git` was null whether
  the model sat outside a repository or git refused the directory (the
  "dubious ownership" of a shared drive), was missing from `PATH` or did not
  answer. Null now means only that git found no working tree; every other
  case is `{"omitted": "unavailable", "detail": ...}` with git's own first
  line, the export logs one line saying the revision was not recorded, and
  `gspio verify --model` reads the reason as an indeterminate `git` line that
  moves no exit status.

- **One figure says whether any formula moved, or only the data.** A
  record's `graph_fingerprint` is the model as run, so a re-sourced
  mortality table moved it exactly as an edited formula did, and a reviewer
  had no single figure to quote for "the logic did not change". Every export
  now writes `formulas_fingerprint` beside it: the same fold with every
  table's, join's, mortality basis's, curve's and schedule's content digest
  -- and a column of values handed over at a line -- masked, and the tables
  section left out. A table, curve or schedule refresh moves only
  `graph_fingerprint`; an edited formula, a literal, a table name, a key or a
  typed valuation date moves both. Under a compiled rollforward a schedule
  change is data too: the compiled machine's identity leaves its schedule out
  (see **A compiled rollforward's identity is its machine** under Changed).
  `gspio diff` prints `formulas unchanged (formulas_fingerprint
  equal); data changed: table mortality` or `formulas changed`, and its JSON
  `compared` records carry the figure; a document written before it gets no
  such line. `gspio validate --deep` recomputes it from an executable
  document, and the Audit View's Model tab shows it beside the graph figure,
  each with a line saying what it covers.

- **An edited assumption table, or an edited helper the model imports, no
  longer passes `gspio verify`.** `source_sha` covered the model file alone
  and nothing read a table back from its file, so a rate changed on disk and
  an accessor module edited beside the model both verified with exit 0. The
  audit file now records the modules and the tables' files, and `verify
  --model` and `verify --assumptions` check them (see *Added*).

- **`gspio compare` pairs two results files policy by policy.** Two runs of
  one model over the same policies in another order -- a re-extract sorted
  differently -- were compared row against row, so each policy was held
  against another and the report said *disagree*; two books whose values
  happened to line up by position said *agree*. Results files written by
  `run-model --results` (and `--every-node`), `run-single-policy`,
  `calc-graph --results` and `run-artifact` recorded no row identity unless
  a command was told one. Each now records the policy-id column the runner
  resolves -- the one `--policy-id-column` names, else `policy_id`,
  `point_id` and the other names it reads as an identifier -- and on a
  scenario run the scenario column beside it, whatever `with_scenarios`
  called it, wherever those name each row once. `run-model` and
  `run-artifact` take `--policy-id-column` for a book keyed otherwise,
  repeatable for a second column; a column named there that names no row
  once is said, and `run-artifact` refuses it before the engine runs.
  `compare` pairs rows on that identity, or on the columns its own new
  `--policy-id-column` names (give it twice for a scenario column). A file
  that records none is paired by position only where the order is shown --
  the other side's identity column is in the same order, or both read one
  book -- and is otherwise refused with a sentence naming the flag. The
  report says how rows were paired and on what, in a new `rows_matched_on`.
  The manifest's `gaspatchio.row_identity` is now a list of column names;
  a file stating one name is still read.

- **`gspio calc-graph --branches` states each policy's own branches.** With
  more than one policy on the axis (`--policies all`, `:3`, a list), every
  policy's `then`, `otherwise` and `fired` were evaluated off the frame's
  first row, so a policy whose condition held was said to have taken
  `otherwise`, beside a sample and a walk-through that said `then`. Each
  policy's branches are now evaluated off that policy's row.

- **An exported `accumulate` over an integer states the widening.**
  `af.x.projection.accumulate(initial=af.av_pp_init, ...)` with an integer
  `av_pp_init` was recorded with the integer column bare, where spec §11.1.20
  states the recurrence over Float64, so a strict reader refused the line
  and the 51 calculations downstream of it in the level-4 tutorial. The
  kernel widens the integer to a double, and the record now says so: an
  integer operand is recorded as `to_float(...)` (§11.1.38, which refuses an
  integer no double holds exactly), and an integer literal opening balance
  as the double it opens at (`initial=0` is `0.0`). The numbers are
  unchanged; the fingerprints of such calculations, and of the graph, move.

- **A per-policy flag times a decimal exports.** `af.smoker * 100.0`
  computed a Float64 and the frame's schema stated `Unknown` for it --
  Polars widens a Boolean beside an untyped decimal only when the frame runs
  -- so `gspio calc-graph` refused the model: "Column 'a' has type Unknown,
  which the calculation graph has no name for". A decimal literal beside a
  per-policy flag is now held as the Float64 it was written as, on either
  side of `+`, `-` and `*`, so the schema states the type the answer already
  had and the record writes `f64`. The numbers, the answer's type and the
  operation tree are unchanged. (A flag beside a whole number answers a
  double too now; see Breaking.)

- **A file outside the model's root is named, not climbed to from `/`.**
  Policy data on a shared volume, results under `/tmp` or a helper module
  on another top-level directory were written as a climb of `..` to the
  filesystem's root and back down --
  `../../../../../tmp/run-42/inforce_2026Q3.parquet`
  -- which names the machine in a document sent to a reviewer, and on
  Windows a file on another drive kept its absolute path. Such a file is
  now its name under `<outside the model's root>`:
  `<outside the model's root>/inforce_2026Q3.parquet`, in `model_points`,
  `results`, `source_path`, a node's `source_location`, `sources[].path`
  and an assumption's `source_file`. A file under the root, and one beside
  it in a directory the root shares, are written as before, `..` included.
  `gspio verify` and `gspio diff` read either form.

  Serves *Audit by default*: the record says which file the run read
  without saying whose machine it was.

- **A broadcast's `like=` column is an indirect read.**
  `af.rate.projection.broadcast_to_periods(like=af.policy_year)` recorded
  `policy_year` as `DIRECT` / `TRANSFORMATION`, a value in the number, so
  the rate sat in `policy_year`'s impact cone although only the list's
  length is used. The axis is now `INDIRECT` / `WINDOW` (spec §9 gains the
  rule); the read and its edge stay. No fingerprint moves.

- **A NaN or an infinity in an exported value is written as `"NaN"`,
  `"Infinity"` or `"-Infinity"`.** `gspio calc-graph --scenarios`, and any
  export carrying more than one policy, stopped with only `Out of range
  float values are not JSON compliant: inf`, naming no column, node or
  scenario; a one-policy export wrote the value as `null`, which states the
  column held nothing. Samples, branches, walk-throughs and folds now carry
  the strings spec §10 defines, so both exports write and conform. Anything
  that still cannot be written is refused naming the node, the field, the
  position and the policy or scenario it belongs to.

- **An exported number is the number the run held.** Every value an
  artifact carries -- samples on every policy of the axis, the branch a
  condition did not take, a rollforward's movements and balances, the book's
  fold, and the numbers a walk-through states -- was rounded to six decimal
  places, so a timeline rebuilt from the artifact matched the results file in
  some cells and not others (`0.9400000000000001` arrived as `0.94`), and a
  check at `1e-9` reported honest numbers as wrong. Each is now the full
  double, written as the shortest decimal that reads back to it, and equals
  the results file's cell bit for bit; a walk-through's prose and the viewer
  still round for reading. Spec §8 states it and §16's balance reading keeps
  its tolerance. A document carrying values grows by a few per cent -- the
  level-4 tutorial's one-policy export from 1,729,777 to 1,757,373 bytes --
  and `--max-size` still measures the finished document.

- **A walk-through reads the same wherever gaspatchio is installed.** From a
  wheel in a virtual environment the first line of a walk-through, and the
  `gaspatchio_lowered` facet, carried half of the library's path:
  `duration.lib_conditional(1, sum_assured, 0)` and `(1.lib) / (itm)` where a
  checkout wrote `duration_conditional(1, sum_assured, 0)` and `(1) / (itm)`.
  Polars names the library relative to the environment when it sits inside
  one, and the cleaning read only a path from the root. It now uses the scrub
  the fingerprint text already used, so both installs write one text.

- **A walk-through names the operation the model wrote.** A `when` over a
  per-period column opened its walk-through as `duration_conditional(1,
  sum_assured, 0)` -- a function that exists nowhere, with the comparison
  gone and `duration` fused into the name, so its values were never put in
  -- because the cleaning stripped every `.list` it met, kernel names
  included. It now opens `.when((duration) > (1)).then(sum_assured)
  .otherwise(0)`, a per-period power reads `.pow(...)` and a per-period clip
  `.clip(...)`, in the walk-through, the `gaspatchio_lowered` facet and an
  error panel's Operation line alike. No fingerprint moves.

- **`gspio diff` no longer sends you to a `gspio compare` that refuses.**
  Under a results file that moved, it told you to run `gspio compare` on the
  later audit file and the two results files, and after any edit to the model
  compare refused them (the results are not of one artifact). The sentence
  now depends on what moved: after an edit it says compare will refuse and
  points at the calculations the report lists and at reading the two files
  side by side; over a changed book it says compare measures how far each
  column moved over the same policies and refuses books of different sizes;
  where only the file moved it still points at compare. The comparison page
  (`gspio diff --html`) writes the same sentence by the same rule.

- **A fault while reading a calculation graph's sample values is raised,**
  where it was written into the export as a missing sample.

- **`af.graph.holes()` and the graph's other questions answer for a
  calculation whose type the graph has no name for.** An unsigned count from
  `list.len()` or `pl.len()`, or a `pl.struct(...)`, made by `select`,
  `with_columns` or an assignment on a frame of 16 or more columns, made
  `holes()`, `trace`, `fingerprint` and the rest raise `UnmappedDtypeError`,
  because every question shared the export's type check. They now answer;
  the export still refuses the type by name, with the cast that carries it.

- **`gspio calc-graph`'s node line adds up on a rollforward model.** It
  counts compiled rollforwards and running states beside the inputs, the
  calculations and the columns nothing accounts for, naming the two only where
  a model has them, and refuses a node kind it does not know rather than
  leaving it out of the total.

- **One CSV book is one input to every command.** `gspio calc-graph` and
  `gspio verify` read a CSV book as `gspio run-model` does, inferring its
  column types from 10,000 rows rather than 100, so a column empty for its
  first hundred rows is typed alike and the book has one fingerprint and one
  digest whichever command read it.

- **The calculation graph's public docstrings are written for the reader of
  the API reference.** The reference renders `GraphExporter`, `export()`,
  `node_values()`, `diff_artifacts` and the rest of `gaspatchio.frame.graph`
  verbatim, and several of them spoke the project's own vocabulary: "the
  engine seam's reference adapter", "That layer is unstable ... while the
  preview is open", "On from `gaspatchio-graph/v0-preview.2`", a decision's
  filing number. They now say what each call is for and are exact about what
  is stable: the format is a pre-release version, and the executable
  profile's operation trees -- what another engine runs the model from -- may
  change between releases before its first stable version, each change
  recorded in the specification's change log. That warning is the one the
  schema's operation-tree definition and the specification's section 3 carry
  too, so it is reworded in all three at once and a consumer holding any one
  of them reads the same words: it now names what the trees are for and what
  covers them today -- the JAX engine runs the operations its coverage table
  lists and refuses the rest by name -- where it cited an evidence trail.
  Examples that spelled a format identifier out use the package's constants. A new test walks the whole
  public surface -- every class and function in the package's `__all__`,
  their public methods and properties, and every model field's description
  -- and fails on an internal term, naming where it is and what to write
  instead; its table of terms is meant to grow.

- **Every exported artifact records the book it was built over, and
  `diff_artifacts` reports a changed book as data drift with no argument.**
  Two exports of one model over two entirely different in-force
  files used to compare as `drift: False`, with nothing under
  `calculations` and nothing under `data`, unless each export had been handed
  a `ModelIdentity(model_points=...)`: the model never reads a model point by
  name, so nothing in the graph moves when the policies do. The envelope now
  carries `book` (specification section 7.5): the input columns the model's
  answers rest on -- the ones it reads and the ones it hands back -- in name
  order, and a content digest of them under the
  specification's content grammar -- the digest a result manifest already
  records as `inputs_digest` when the engine was handed the book itself,
  taken by the same function, so a filing and such a result can be matched
  by the data behind them; an engine handed the book crossed with a
  scenario axis, or filtered, records a digest of what it was handed
  instead. The Polars reference's manifest records the book's own digest,
  the one the export took, so an input the model read and then dropped
  counts in both. The
  columns are the graph's required inputs, the ones an engine is handed. The
  digest is of the data, never of a file: the same in-force written out
  twice, or with its columns in another order, is one book, and a book
  revised only in a column the model neither reads nor hands back is no
  change. Where both documents state a book digest, `diff_artifacts` (and
  the comparison page `gspio diff --html` writes) reports the policy data
  from it, as a `model_points` entry named by the file the run recorded;
  where either states none, it falls back to the file stamps
  `model.model_points` records, exactly as before; and where neither can
  decide -- no digest on one side and no file named by both runs -- the
  report still writes the policy data, as an entry whose new `reason` says
  the two books could not be compared and why, and that entry is drift: a
  comparison that could not tell never answers "the same policies".
  `gspio diff` prints the reason under the entry, and the comparison page
  writes the same sentence. An explicit
  `ModelIdentity` still records what it names. `validate_artifact(...,
  book=frame)` takes the digest again over data you hold -- handing over the
  book is the request, with or without `deep=True` -- and refuses a
  document that was built over other policy data, naming both digests; the
  structural reading refuses a column list out of name order or naming a
  column the model does not read. A producer with no book to hand, or one
  holding a column the content grammar cannot read, writes the digest as
  `{"omitted": "unavailable", "detail": ...}` rather than failing the export,
  `detail` saying which of the two it was and, for a refusal, the column and
  the type it met. A document the frame builds only to hand to a second
  engine -- `collect(engine=...)`, `run_aggregated(engine=...)` -- takes no
  digest either, and says it was left to the engine: the engine digests the
  inputs it runs over into its own result manifest, so a digest in the door
  was a pass over the book paid on every run and read by nothing. On level 4
  over a million policies the door went from 0.88 s to 0.50 s, the engine's
  own digest (0.30 s) paid once. A column held
  as categories is not one of those: the digest reads a `Categorical` or an
  `Enum` as the text it holds, as it reads an `Int32` as the `Int64` of the
  same numbers, so the same policies extracted as categories by one pipeline
  and as text by another are one book, and two different books held as
  categories are two.

  **The member is required**, so a document written without it is refused
  by the schema, as with `policies` before it; the schema identifier stays
  `gaspatchio-graph/v0-preview.3` and `fingerprint_algorithm` stays
  `gspv0-preview-3`. No node fingerprint and no graph fingerprint moves;
  `document_digest` moves on every document. The published conformance
  corpus, the checked-in example artifacts and the JAX engine's committed
  artifacts carry it now. The export digests the book the frame was handed
  -- kept on the frame as the plan it arrived as, and carried through a
  timeline, a scenario axis and `continue_from=` -- which costs 0.33 s per
  million policies on the level-4 book's fourteen required columns: a
  values-free export of level 4 over a million policies took 0.40 s against
  0.06 s without the digest (median of five, the Intel laptop).

- **What a join key drives is now in its lineage: `dependents()` and
  `affected()` follow a key through the join.** A column a join brings in
  holds whichever row of the other table its key matched, but the graph
  recorded the key only as an attribute of the join and gave the joined
  column no reads at all. So after `af.join(products, on="product_id")`,
  `af.graph.dependents("product_id")` answered `()` and
  `af.graph.affected("product_id")` answered `('product_id',)`, while
  `commission_rate` and `commission`, struck on the joined rate, move whenever
  a policy's product does. That is the comfortable empty answer the query
  surface refuses to give for a name it does not know, given for a name it
  does -- and a reviewer bounding a restatement with `affected()` under-scoped
  it. Every column a join brings in now reads the key or keys it was matched
  on: the left side's columns, in the order `on` or `left_on` gives them,
  bound to the definition each key held when the join ran, and classified
  `INDIRECT`/`JOIN` -- the key selected the row, as a lookup's key does. The
  same model now answers `('rate@1',)` and `('product_id', 'rate@1',
  'commission_rate@1', 'commission@1')`, `precedents()` of a joined column
  names its key, and `trace()` runs through it. A cross join states no key and
  its columns still read nothing.

  **The key is read as written, everywhere, and a name the record cannot
  carry is refused.** The record lists a join's keys in one attribute,
  separated by `,` and `=`, and four readers each split it their own way; the
  JAX engine trimmed the spaces off each name, so a key called `" code "` was
  bound to a column called `code` that the lineage never named. One reader
  now serves them all, through `gaspatchio.engines.format.join_key_sides`,
  and trims nothing. `ActuarialFrame.join` refuses a key whose name holds `,`
  or `=` -- or is empty -- before anything changes, naming the column and
  asking for it to be renamed: Polars joins on such a name happily, and the
  record would have named other keys.

  **Fingerprints of models with joins move.** No calculation's own digest
  changes, but every joined column and everything downstream of it now folds
  its key in, and so does the graph fingerprint: on the level-4 and level-5
  tutorials, 85 node fingerprints each and the graph fingerprint, with not one
  `local_fingerprint`. A comparison across this change reports those nodes as
  inherited movement. The specification's section 11.1.2 is amended to match
  (a `join` node reads its key), the execution inspector binds the key like
  any other read, the JAX engine resolves a join's key through the node's own
  `reads` and refuses by name a document whose join does not read its key, and
  the engine's committed level-4 and level-5 artifacts are exported again.

- **`gspio calc-graph` names what each sampled calculation reads.** The
  terminal summary's *Sample computed nodes* lines looked up a `dependencies`
  member no artifact carries, so every line stopped at the arrow --
  `death_claims@1 ← ` -- on every model. Each line now reads the node's own
  `reads`, the member the document writes, so the terminal says what the file
  says: `reserve@1 ← death_claims@1, premium_received`. A calculation that
  reads no column says `nothing` rather than trailing off.

- **Three lowering refusals name the mistake now, not the rule it broke.** A
  `lookup` node short an attribute, carrying one twice, or carrying a fifth
  met one sentence for all six defects — *"lookup requires table,
  table_fingerprint, on_missing and fill_value attributes"* — which says what
  a lookup needs and nothing about the node in hand. Beside it, the identity
  check said both halves had to be nonempty text without saying which half
  was wrong; the miss-policy check restated the three allowed pairings
  without saying which one arrived; and the key-arity check asked for one
  operand per key column without saying how many of either it had.
  `to_integer` and `list.get` did the same, one sentence each across a
  missing operand, a surplus one and a stray attribute. Each defect now
  raises its own sentence: the attribute that never arrived, named — all of
  them, where several are missing at once — or the one written twice, or the
  one the operation does not carry and the value it came with; which of
  `table` and `table_fingerprint` is empty or of another type, and which
  type; the `on_missing` value and the `fill_value` beside it, against the
  three pairings a miss policy has; and the operand count against the
  processed table's key columns, naming the table and its keys. Every one of
  them ends where the signature is stated — §11.1.22 for `list.get`,
  §11.1.23 for `to_integer`, the lookup row of §11.1.11 and §11.1.24 for
  `lookup`, in `spec/graph-artifact/v0-preview.md` — so the next move is a
  place to go rather than a rule to re-derive from the sentence that refused.
  Nothing a model computes changes: the same nodes are refused, with the same
  `TypeError`, and every well-formed node lowers exactly as before.

- **A sequence written as an operand of a formula is identified by its
  values.** `af.loaded_premium = af.annual_premium * [1.00, 1.05, 1.10]`, a
  list in a `when/then` branch, anywhere a Python list or tuple reaches the
  calculation record directly: such a sequence arrived there as engine
  text, and that text is the engine's own *display* of the values, which
  abbreviates a long sequence to its first two entries and its last. So
  `[18, 25, 35, 45, 55, 65, 75, 85]` and `[18, 25, 35, 46, 56, 66, 75, 85]`
  both displayed as `[18, 25, … 85]` and hashed alike: the model changed
  and its fingerprint said it had not, which is worse than no fingerprint,
  because it is a positive claim of sameness a reviewer relies on. A
  sequence of numbers, text or flags in that position is now held as the
  literal it is and identified by its values, member by member and in
  order. Every such calculation's fingerprint moves once as a
  result, and with it the model digest of any model holding one; nothing
  else moves. The node also stops claiming to need Polars — a band of
  boundaries is engine-free — so in the exported graph its `engines` goes
  from `["polars"]` to `[]` and its `period_reference` from `"unknown"` to
  null: that second field marks a formula the framework could not read, and
  it can read this one. What the engine is asked to compute is unchanged:
  no model's numbers move.

  **A sequence handed to an engine's own method is not covered by this.**
  `is_in([...])`, `cut(...)` and `replace(...)` are inherited from Polars
  unchanged, so the sequence never reaches the calculation record at all:
  the whole expression arrives as one piece of engine text — declared as
  such, with `engines` naming the engine — and its identity is still that
  text as the engine displays it. Two `is_in` bands differing only in the
  abbreviated middle still share a fingerprint, and `cut` is worse: its
  boundaries never appear in that text at all, so every `cut` band on a
  column shares one, whatever its length or values. The wider closure of
  engine-returning methods is tracked separately.

- **A column of values injected wholesale is identified by what was
  injected.** A stochastic model hands its simulated series to the frame as
  data — `af.shock = pl.Series(...)` — and the frame recorded the fact of
  the injection without recording the values. Two models given different
  simulated data under one column name therefore fingerprinted identically,
  and nothing upstream could carry the difference on their behalf: an
  injection reads nothing, so there is no Merkle layer to fold anything in.
  It was the one input for which the model's stamp could stay still while
  the numbers moved. The injection record now carries the same `sha256:`
  content stamp an assumption table and a join's right side carry, taken
  over the values, their type and their count, so a changed simulation
  moves the model's fingerprint. The series' own name is not part of that
  identity — the column's name is the assignment key — so the same values
  stamp alike whatever the series they arrived in was called. Row order is
  part of that identity too: an injected column lands on your policies by
  position, so the second value belongs to the second policy and reordering
  the same numbers is a different injection. The NumPy array a simulation
  actually hands back — `rng.binomial(...)` returns an array, not a series
  — is stamped the same way, over the same bytes, so the same values carry
  the same stamp whichever of the two they arrived in and the record's
  `origin` says which one that was. A rank-0 array is not a column at all:
  it holds one number, which Polars broadcasts to every row, so it stays
  the literal it behaves as. The cost is one encoding pass over data you
  are already holding, paid at each assignment whichever container the
  values arrived in: about 5 ms for a 100,000-row float column, where an
  array assignment used to cost about 0.09 ms. So hoist an injection out of
  a per-scenario loop if the values do not change with the scenario. One
  thing follows from the stamp being taken over the values themselves: a
  column of Python objects can no longer be assigned, as a series or as an
  object array — it has no dtype anything can project, discount or stamp,
  so it is refused at the line that wrote it rather than accepted and found
  unusable later.

- **A column written under a name the model renamed or dropped away is
  reported as the hole it is.** The names a frame knew its data arrived
  with never moved: after `af.rename({"Sum Assured": "sum_assured"})` the
  frame still counted `Sum Assured` among them, and after
  `af.drop("temp_debug")` it still counted `temp_debug`. Write a column
  straight into the query plan under one of those names afterwards and the
  frame credited it to the model points — `af.graph.holes()` returned `[]`
  and the exported graph stated that a field the actuary supplied was
  behind numbers nothing could account for. The arriving set now follows a
  rename and shrinks with a drop, so such a column is reported as the hole
  it is. The names the columns arrived under are kept alongside it, so a
  model that renames its vendor columns on the way in still says which
  field of the source file each of its inputs was.

- **`gspio calc-graph`'s node breakdown adds up.** The summary line counted
  inputs and calculations only, so a model holding a column it could not
  account for printed a breakdown that came to less than its own total. All
  three kinds are named now, and "0 unaccounted for" is stated positively
  rather than left to be inferred. The command's sample block also took the
  first three nodes and then kept the calculated ones among them, so a model
  whose first three nodes are columns its data arrived with printed the
  header with nothing under it; it filters first and slices after.

- **A join records only what the join actually brought.** It worked out what
  had arrived by comparing the schema against the frame's own column order,
  which lists neither a column written straight into the query plan nor the
  rollforward kernel's internal scratch column — so both were recorded as
  having arrived from a table they never touched, with that table's keys,
  join type and content fingerprint attached. What a join brought is now what
  the schema gained.

- **An exported trace is withheld rather than shown with the wrong numbers.**
  Sample values are read out of the finished frame, one per column, so they
  can only speak for the definition that column ended up holding. A
  calculation that read a definition something later replaced was given the
  surviving values anyway: death claims taken on the inforce before the
  maturity zeroing exported a walk-through reading `((0)) * ((0.01))` and
  reporting `0.01` — arithmetic that does not produce its own stated answer,
  against a formula and a reads list that both said otherwise. The numeric
  walk-through is now omitted for those calculations; the formula, the label,
  what it read and where it was written all stay, so what was computed is
  still fully stated and only the numbers nobody can supply are absent.

- **The audit export's leaf for a vendor field you renamed now says what type
  it was.** The graph names an input leaf for the field the data arrived
  under rather than for what the model renamed it to — `Sum Assured`, with
  `sum_assured` reading it — so a reviewer chasing a number back to the
  source file finds the source file's own name. Its type was the half nobody
  could answer: the type was read off the finished frame, which holds the
  column under the new name, so `af.rename({"Sum Assured": "sum_assured"})`
  put `dtype: unknown` on the leaf naming the vendor field, and so did
  assigning the column to a new name and dropping the old one. An arriving
  `f64` had been met at the door and the document said nothing about it,
  which is the one thing §10 of `spec/graph-artifact/v0-preview.md` says a
  producer never does. The frame now keeps the schema its data arrived with
  beside the names it already kept — through a rename, a drop, a scenario
  axis and a `continue_from` handover, none of which can move it — and the
  leaf reads `dtype: f64`, `shape: scalar`. Its `value_sample` stays null,
  and the two absences are no longer one: the type is remembered, and the
  values really are gone from the collected frame.

  **A document carrying such a leaf changes its fingerprints.** A leaf's
  canonical bytes are its tag, its name and its type, so a leaf hashed over
  `unknown` and one hashed over `f64` are different bytes — and that is the
  correction rather than a side effect of it: a renamed arrival's leaf is now
  byte-identical to the one a model that kept the vendor name writes, which
  is what it always should have been. No model that renames nothing moves a
  digit. No field, tag or byte grammar moves, the published conformance corpus renames nothing and is
  unchanged, and §14.1 carries the line. One case keeps `unknown`: a type
  this vocabulary has no name for — a vendor `Categorical` carried in by
  `to_text()` and then dropped — because refusing the export over a column
  the model has already carried into the vocabulary and let go of would be
  refusing history.

  Serves *Audit by default*: the leaf that names the vendor field now says
  what type that field was, and a field that arrives as text one quarter and
  as a number the next is visible as a change rather than as two leaves both
  saying nothing.

- **A frame exported from Python with no model identity writes no absolute
  path.** `GraphExporter(af).export()` -- the call the review skill teaches --
  wrote each node's location, each source entry and each selection step and
  boundary as the exporting machine's absolute path, against section 7's rule
  that none appears anywhere in an artifact; the committed one-policy golden
  carried six. With no `ModelIdentity` and no `source_root`, the root is now
  the checkout the model's file sits in, or that file's own directory outside
  one, as `ModelIdentity.of` decides it. The golden is regenerated.

- **`gspio validate` refuses what sections 7 and 8 say does not conform.** An
  absolute path in any member that holds one, a one-policy document carrying
  a value wrapped in an array of one, and a sources section naming one path
  twice or out of order each passed as "conforms"; each is now an error,
  naming the member.

- **`validate_artifact` refuses a document that states no type for a column
  the frame holds.** Section 10 of `spec/graph-artifact/v0-preview.md` says a
  validator flags `unknown` on any node that is in the final schema — the
  model's answers carry real types, only its history may go untyped — and no
  validator did: `frame/graph/validate.py` carried no occurrence of the word.
  The semantic reading gains the rule, as one error per node naming whichever
  of `dtype` and `shape` the node left untyped and giving the two moves that
  fit it: state the type the column holds, or state `in_final_schema: false`
  where the node is history after all. The execution inspector's
  `input_dtype_unknown` and `input_shape_unknown` are unchanged and answer
  the other question — whether an artifact can be run, asked of input leaves
  only.

  Nothing this producer writes reaches it. A type the vocabulary cannot name
  on a column the frame holds is refused at export, and a dropped arrival's
  leaf carries the type it arrived under, so the rule guards a document that
  came from somewhere else or one somebody edited after it was written. The
  four checked-in goldens and the published section 12.5 corpus carry three
  `unknown` nodes between them — one superseded definition in the corpus and
  the two hand-built section 17 examples — and none of the three is in the
  final schema, so no shipped document changes its report and no golden,
  corpus digest or vector bundle moves a byte.

  Serves *Audit by default*: a document's answers carry real types, and a
  reader handed one that does not is told so rather than finding out when a
  consumer builds the column back as the wrong thing.

- **`gspio verify`'s modules line names the file it read.** Given
  `--model edited/model.py`, the line read ".../original/helpers.py is
  sha256:<the edited copy's digest>": the path the audit file records beside
  the hash of the file actually read, so a reviewer holding two folders read
  the original as changed. The line now names the file read, from where the
  command was run, and the recorded path beside it where the two differ:
  "edited/helpers.py (recorded as original/helpers.py) is sha256:...".

  Serves *Audit by default*: a digest is printed beside the file it is of.

- **A `gspio verify` line not asked says why on the line.** Given
  `--model-points`, the report printed `model_points  not asked`, which read
  as a flag ignored: the policy data had been checked, by the `book` line,
  which decides wherever the audit file states a book digest, and the file's
  own bytes were set beside it for information. Each line not asked now
  carries its reason -- `model_points  not asked: the book check decides`,
  `results  not asked: no results file was given` -- and the detail beneath
  it says the rest. Every such detail opens with that one sentence, in
  `--json` too; the outcomes and the exit status are unchanged.

- **`--mode` names one of two modes, or is refused.** `gspio run-model` and
  `gspio run-single-policy` replaced any `--mode` they did not know with
  `debug` and said nothing, so `--mode optimise` -- the British spelling --
  or a typo ran with profiling on and exited 0. Both now refuse it as a bad
  parameter (exit 2), naming `debug` and `optimize` and the closest
  (`Did you mean 'optimize'?`). The two modes still change diagnostics only,
  never a number.

- **`gspio calc-graph --policy-id-column` repeats, as `run-model`,
  `run-artifact`, `compare` and `diff` do.** A book whose rows a policy and
  a scenario column name together could not say so to `calc-graph`, which
  took the option once. Given twice, the first column names the policy and
  the results file records both as each row's identity.

  Serves *Meet you where you are*: one option spelled one way on every
  command.

- **An output into a directory that is not there is refused before
  anything is written.** `gspio sheet -o report/policy.xlsx` with no
  `report/` raised a `FileNotFoundError` traceback, and `gspio calc-graph
  --xlsx report/policy.xlsx` raised it after the audit file was already on
  disk; `--artifact`, `--results` and `--html` into a missing directory
  failed the same way. No command creates a directory for its output, so
  both now check every output they were given before the model runs or a
  file is written, and refuse with exit status 2, naming the flag and the
  directory and saying to create it with `mkdir -p`.

- **Every other output flag refuses a path with no place to go, by name.**
  `gspio run-model -o report/results.parquet` and `run-single-policy -o` ran
  the whole model and then raised a traceback when `report/` was not there;
  `run-artifact -o` raised one from the engine's staging; `run-artifact
  --aggregate -o report/totals.json` quietly created `report/`; and `diff
  --html` raised one after the `-o` report was stored. An output path that is
  itself a directory raised on every command, `calc-graph --html` and
  `--xlsx` only after the audit file was written. Each now checks its output
  before the model or the engine starts and refuses with exit status 2,
  naming the flag and the path: a directory that does not exist (with the
  `mkdir -p` that makes it), a directory that is a file, or a path that is a
  directory. `validate`, `diff`, `compare`, `verify` and the `gspio graph`
  questions still say their verdict first, and their `-o` refusal -- exit 2,
  as before -- now names the flag beside the path. A file already at the
  path is replaced, as before. `gspio tutorial init --dest` still creates
  its destination and the directories above it; the two destinations that
  raised a traceback -- one inside a file, and a file given with `--force`,
  which it tried to delete -- are refused with exit status 2, naming `--dest`.

  Serves *LLM-shaped from the inside out*: the next attempt converges on a
  sentence that names the flag, not on a traceback.

- **The Audit View shows every member the record carries.** Its Model tab
  listed the source, results, model points, book, git and producer, and
  nothing a record now states beside them: a reviewer could not see the
  helper modules or the tables' files that `gspio verify --model` and
  `--assumptions` check, nor the library that produced the values. It now has
  "the model's own files" (each module with its short stamp, or "imports
  nothing from beside itself") and "the library" (one fact per
  `producer.versions` key, the extension's digest shortened, `imports`
  listed, a withheld set said to be withheld). The git rows state the
  record's reason -- "exported outside a git working tree", or git's own
  sentence where it could not answer -- where an unavailable git printed "no
  git commit recorded" over a dirty row reading `undefined`. The Table panel
  says where its table was read from, or "built from a frame in code", and a
  table whose recipe reshaped its file says so in one sentence: verify cannot
  hold it against that file.

- **A cell's every digit is one click away in the Audit View, and copying a
  cell copies them.** The page writes values rounded for reading -- two
  decimals, or six significant figures below one -- and a record now carries
  every digit, but there was no way to read them or take them out: a copied
  cell was the rounded text. Selecting a cell now shows the value the file
  holds in the drawer ("the file holds 11.562642361111111"), in the file's
  own spelling, under "shown rounded; the file holds every digit", with a
  control that copies it; copying a cell out of the grid copies those digits.
  The proof's "the trace says ... and the sample says ..." chip prints both
  numbers whole, where two that differed past the sixth figure printed as
  the same number.

- **The Audit View's comparison names a library that moved under one
  release.** Where two runs' values moved and their definitions did not, the
  page offered the producer as a candidate cause -- keyed on the whole
  producer block, but worded from its name and version alone, so two runs of
  one release on different libraries read "the producer changed between the
  runs, from gaspatchio 1.0.0 to gaspatchio 1.0.0". It now says what moved,
  in `gspio diff`'s own words: "the library changed between the runs
  (library: polars 1.42.1 → 1.43.0; extension sha differs)", or the library
  beside a new release where both moved. A library one side withholds or
  does not state is not offered, as `gspio diff` prints no library line for
  that pair.

- **The Audit View names a folded pane in the words its documentation
  teaches.** A pane put away to a rail was labelled with the id the page's
  code keys it by -- `grid`, `cone`, `inspector` -- words no page of the
  documentation uses. The rail now says `worksheet`, `derivation and proof`
  or `record`, and so do its `open` title and the pane's collapse, expand and
  restore controls, which a screen reader announces. The cone's pane carries
  the proof as a strip under the derivation, so its one name says both, as
  its rail's figure already did. The ids themselves are unchanged: they key
  the layout a browser remembers and every test id, so a page that was
  railed yesterday opens railed today. The bundle grows by 42 gzip bytes,
  and its ceiling with it.

- **The comparison page compares what `gspio diff` compares.** A page
  carrying two artifacts whose `model.source_path` differed showed the later
  one alone and compared nothing, while `gspio diff` over the same two files
  reported every line that moved -- the two readings of one comparison
  disagreeing at the first question. The path is written relative to the
  model's root, so it moves when last quarter's model is copied into a new
  folder of one repository, the case the page exists for. The page now
  refuses exactly the pair the report refuses -- digests taken under two
  fingerprint algorithms -- and compares every other pair as the report
  does.

  Serves *Audit by default*: the page and the report give one answer.

- **A scenario run's own record can withhold the machine it ran on.**
  `gspio calc-graph --scenarios --no-versions` withheld the library versions
  in the document and went on stating them -- core and extension versions,
  the extension's digest, Polars, Python, the platform and ddsketch -- in the
  `*.run.audit.json` the same command wrote, so a sidecar committed as a
  golden moved with whoever regenerated it. The record now takes section
  6.1's withheld form on the same switch: each of those keys reads
  `{"omitted": "withheld"}`, and on a second engine `engine_versions` does
  too. `ScenarioRun.run(versions="withheld")` and
  `run_aggregated(versions="withheld")` ask for it from Python; it is never
  the default, and any other value is refused before the run starts.

- **`ScenarioRun.to_yaml()` and `from_yaml()` work on a plain install.**
  They needed PyYAML, which only a development dependency group installed, so
  `pip install gaspatchio` followed by the scenario pages' YAML recipe raised
  `ModuleNotFoundError: No module named 'yaml'`. PyYAML is now a dependency.

- **An aggregator's `within=` is honoured where it has a meaning and refused
  where it has none.** Every `Period*` kind accepted `within=` and then summed
  each scenario's policies anyway: `PeriodMax("claims", within="max")`, the
  largest single policy per period, answered the largest scenario total
  (`[28, 56, 84]` where the hand value is `[12, 24, 36]`). On the scenario
  axis a `Period*` kind now reduces each scenario's policies by `within`
  (`mean`, `max`, `min`, `count`, `first`, `last`) before its statistic is
  taken across scenarios, at every `batch_size`; partitioned over
  `scenario_id`, where there is nothing left to reduce first, a non-default
  `within` is refused. `run_aggregated` has no scenarios, and dropped
  `within=` on every kind -- `Sum("pv", within="mean")` answered the policy
  total, on Polars and JAX alike -- so it now refuses a `within` other than
  `"sum"` by name, as it refuses `.of()`. A `Period*` kind's
  `canonical_form()` carries `within` where it is not `"sum"`, so the record
  and a YAML round-trip say what was asked; at the default it is unchanged,
  and no recorded plan moves.

- **A tail direction or level that would be read as another is refused.**
  `CTE` and `PeriodCTE` compared `direction` with `"upper"` and averaged the
  lower tail for anything else: `direction="Upper"`, or `direction: up` in a
  YAML plan, answered an SCR 33 times too small. `Quantile(99.5)` -- a
  percent for a probability -- answered the largest value, `Quantile(-0.2)`
  extrapolated below the smallest, and `CTE(level=1.5)` answered a number.
  `CTE`/`PeriodCTE` now refuse a `direction` other than exactly `"upper"` or
  `"lower"` and a `level` outside (0, 1], and `Quantile`/`PeriodQuantile` a
  level outside [0, 1], where the aggregator is built, from code or YAML.

- **A scenario aggregator never turns a missing value into a number.** A
  scenario whose IRR does not exist (null on the frame, Excel's `#NUM!`) was
  reported by `Sum`, `Mean`, `Min` and `Max` over `scenario_id` as `0.0`, a
  plausible rate nobody computed, and `Count` counted it: the within-scenario
  `sum` totalled the lone null to `0.0` before any aggregator saw it. A null
  is now skipped wherever it is read, and an aggregator that saw nothing but
  nulls answers null (`Count` answers `0`); each aggregator's docstring says
  so. An aggregator that saw nothing at all answers null too, where `Mean`,
  `Min`, `Max` and the sketch-backed kinds answered NaN; a NaN in the column
  still makes the answer NaN.

- **A per-period aggregator never turns a period with no value into a
  number.** A period whose every value was null came out of `PeriodSum` as
  `0.0` and out of `PeriodMean`, `PeriodMin`, `PeriodMax`, `PeriodVariance`,
  `PeriodStd`, `PeriodMedian`, `PeriodQuantile` and `PeriodCTE` as NaN; on
  the scenario axis a scenario whose period held only nulls was totalled to
  `0.0` and counted as a value; and a batch with no value at a period made
  `PeriodMin`/`PeriodMax` NaN there even where another batch had one. The
  scalar aggregators' null rule now holds period by period: the answer is a
  numpy masked array, masked at a period with no value (`None` in
  `.tolist()`, null in a partitioned answer's frame and in the audit record,
  NaN under the mask), and `PeriodCount` counts `0` there.

- **`ScenarioRun.to_yaml()` refuses a plan it cannot write before it touches
  the file.** A plan holding a shock the recipe has no form for (a clip,
  floor, filter, time condition or pipeline) left a 0-byte file at the path,
  or truncated the recipe already there, and the error named a private helper
  and "v0.2". The recipe is now built first, so the path is left as it was,
  and the error names the scenario and the shock and says a recipe holds
  multiply, add and set shocks.

- **The scenarios package says what to write, not which pre-release came
  before.** `parse_aggregations` (and so `ScenarioRun.from_yaml`) refused
  aggregations given as a mapping with "v0.1 plan format detected ... v0.2
  uses a list ... See ref/41-backend-portability/specs/...§10", and public
  docstrings named a pre-release surface by its internal issue number.
  The refusal now shows the list a plan's aggregations are, names the keys it
  was given, and says to move each into its entry as `alias`.

- **`return_full_grid=True` needs a `sink_dir`, and says so.** With no
  `sink_dir`, `for_each_scenario` and `ScenarioRun.run` created
  `./scenarios_<epoch>/` in the working directory and wrote the grid there
  without a word. They now raise `ValueError` before the run starts, naming
  `sink_dir=`. The grid is still written to disk, one parquet file per batch,
  and never held in memory.

- **`sink_dir` takes a string or any path-like, as well as a `Path`.**
  `for_each_scenario(..., sink_dir="grid")` and `ScenarioRun.run(...,
  sink_dir="out", audit=True)` failed with `AttributeError: 'str' object has
  no attribute 'mkdir'` and a `TypeError` building the audit record's path.
  `sink_dir` is now made a `Path` where it comes in; `result.sink_dir` is that
  `Path`.

- **`audit=` takes a string or any path-like as the record's path.**
  `ScenarioRun.run(..., audit="record.json")` and `run_aggregated(...,
  audit="record.json")` read the string as `True` and wrote the record to
  `./gaspatchio_audit/<run_id>.audit.json`, leaving nothing where the caller
  asked. A string or `os.PathLike` is now the path, as a `Path` is; `True`
  and `False` keep their meaning.

- **A shocked or scenario-stacked table is built the way you built yours.**
  `Table.with_shock()`, `Table.from_shocks()` and a scenario run's stacked
  `<name>_stacked` table rebuilt the table under the default
  `storage_mode="auto"` and `on_missing="raise"`, and stacking dropped its
  metadata. A one-row String-keyed table, which builds only under
  `storage_mode="hash"`, then failed inside the framework at
  `batch_size=1`, and a table declared `on_missing="nan"` raised on a miss
  once shocked. Every copy now keeps the base table's `storage_mode`,
  `on_missing` and metadata.

- **A scenario fold answers the same bits on every run and at every batch
  size.** A statistic across scenarios moved in its last bits from run to run
  and with the batch size. The fold took a batch's scenarios in the order a
  `group_by` returned them, which Polars does not fix, so a `Mean`,
  `Variance` or `Std` across 40 scenarios gave three different answers in
  three identical runs at batch size 10. Each scenario's total over its
  policies was also taken on the whole batch frame, so the same scenario
  summed its policies to different last bits at batch size 1 and 10, and
  even a `Min` of those totals moved. Each scenario is now reduced on its own
  rows and folded in the run's order. All 27 scalar, partitioned and
  `Period*` folds measured are bit-identical across repeated runs and across
  batch sizes 1, 10 and auto. The level-5 stochastic step runs at its
  natural batch size again. On the policy axis, `run_aggregated` is
  bit-identical across runs at one stated batch size and agrees across batch
  sizes only to floating-point reassociation, because a different batch
  groups the sum over policies differently. Its docstring states that
  contract.

- **A scenario shock moves exactly the target it names.** A shock written
  without a target -- `MultiplicativeShock(factor=2.0)` -- moved every base
  table at once, so a mortality stress doubled lapse beside it. A
  `ScenarioRun` or a shocks-dict `for_each_scenario` now refuses it, naming
  the tables the plan states and the `column=` alternative. A nested shock
  (a pipeline step, the shock a filter wraps) may repeat its outer shock's
  target or name none; one naming another target is refused rather than
  silently moving the outer one.

- **A shock on a table no read reaches is refused, not folded as BASE.**
  `table="mortt"` for a table built as `"mort"` moved nothing, and the
  scenario's numbers equalled BASE. A plan stating `base_tables` now refuses
  an unknown table at construction, naming the closest. Any plan refuses,
  after the first batch is composed, a shocked table the model never read,
  naming the scenario, the table, the tables the model did read and the
  closest of them.

- **A conditional shock whose condition selects no row is refused, not folded
  as BASE.** `TimeConditionalShock(AdditiveShock(0.30), when={"t": {"eq": 0}},
  table="lapse")` over a lapse table keyed by policy year 1 to 5 -- the
  docstring's own mass lapse -- selected nothing, and the scenario equalled
  BASE to the bit with no word; so did `where={"sex": "f"}` over a table
  holding `"F"`, a range past the keys and a reversed `between`. A
  `FilteredShock` or `TimeConditionalShock` (nested in a pipeline too) whose
  condition selects no row of the table it moves is now refused in a
  `ScenarioRun`, a shocks-dict `for_each_scenario` and `Table.with_shock()`,
  naming the scenario, the condition and what the table holds (`'t' holds 1
  to 5`). A shock that selects rows and leaves them as they were, a cap that
  binds nowhere, still runs.

- **A shock condition on a column its table does not hold is refused by
  name.** `TimeConditionalShock(..., when={"t": {"lte": 1}}, table=
  "mortality")` over a table keyed by `age` failed in Polars' words, `unable
  to find column "t"`, with no next move; so did a `FilteredShock` `where=`
  on a column the table lacks, in a run and in `Table.with_shock()`. Each is
  now refused naming the column, the closest the table holds, every column
  it holds and the move -- write the condition on a column the table holds
  -- and a `when=` refusal says the condition reads the table's own key
  columns, not the model's projection time.

- **`column=` on a shock is read.** It was never read: `column=
  "no_such_column"` still doubled a table's value. It now names the
  model-point column the shock moves, and a column the model points do not
  hold is refused with the closest name and the conversion skill's rule that
  a single-cell defined name becomes a model-point column.

- **`Table.with_shock()` and `Table.from_shocks()` read the shock's target.**
  They ignored `table=` and `column=`: a shock written for `lapse` applied to
  the mortality table moved mortality, and `column="no_such_column"` still
  moved the value column. A shock naming another table is now refused,
  naming both, and so is any `column=`, which names a model-point column. A
  shock with no `table=` takes the table it is applied to as its target, and
  a shocked copy answers to the table it came from, so a chain of
  `with_shock()` calls may keep naming the original.

- **A shock argument written in the wrong slot is refused where the shock
  is built.** A shock's arguments are read in order, so
  `PipelineShock(MultiplicativeShock(1.4), ClipShock(1.0))` built a pipeline
  whose `table` was a `ClipShock`, and the plan failed only when it ran, with
  "'ClipShock' object is not iterable". Every shock class now refuses, at
  construction, a `table` or `column` that is not a name (a `Table` passed
  for its name is told the name), a nested shock that is not a shock,
  pipeline steps that are not a sequence of shocks, and a `where` or `when`
  that is not a mapping, naming the slot and the shock written with every
  argument named: `PipelineShock(shocks=(MultiplicativeShock(1.4),
  ClipShock(max_value=1.0)), column="lapse_rate")`. Arguments written in the
  slots they belong to construct as before.

- **`gspio calc-graph --scenarios` names the run's own record once.** It
  appended `.audit.json` to the artifact's name, so an artifact named the
  way the docs name one, `-o model.audit.json`, got
  `model.audit.audit.json` beside it. The record is now
  `model.run.audit.json` for `-o model.audit.json` and `-o model.json`
  alike; the artifact still names it by path and digest, which is how
  `gspio verify` finds it.

- **A fold's sentence on the policy axis counts what it folds.** Each fold
  entry's `why` said "folded by sum over N policies" with N the book's size
  whenever the cut named a column the book does not hold: a scenario export's
  `.over(("scenario_id", "policy_id"))` entries each select one policy and
  each said "over 2 policies", and a cut by a column the model computes said
  the whole book. Cuts are now counted on the frame the model returned, one
  policy is "1 policy", and a fold that spans scenarios says how many.

- **`Quantile(...).over(...)` and `PeriodQuantile(...).over(...)` are refused
  where `.over()` is written.** Both were accepted when written and refused
  only when a run reached its first fold -- after the plan was built, the
  book cross-joined and a batch projected -- in a scenario plan,
  `run_aggregated` and on the JAX engine alike. No driver folds a
  multi-level quantile partitioned, so the refusal now comes at the call, in
  the words the run used, naming the kinds that do run under `.over()`:
  `Median`, `CTE` or `QuantileRank`, and `PeriodMedian` or `PeriodCTE`.

  Serves *Optimize for the laptop, not the cluster*: a plan that cannot run is
  refused before it spends a batch.

- **A run never writes over another run's record without being told to.**
  `plan.run(..., audit=True)` and `run_aggregated(..., audit=True)` name their
  record by the run's id -- the time to the second and the plan's sha -- so
  two runs of one plan in one second wrote one file, and the second silently
  replaced the first, into `./gaspatchio_audit/` or a `sink_dir` alike. A
  record already under the run's own name is now refused, naming the move,
  `audit=Path('...')`, and the earlier record is left as it was; the name's
  format is unchanged, and a path the caller names is still theirs to
  replace. A full grid written with `return_full_grid=True` into a
  `sink_dir` that already holds another run's `batch_*.parquet` files is
  refused before anything runs: batches are named by index, so the second
  run would have overwritten the batches it reached and left the rest, one
  directory read as one grid made of two runs.

  Serves *Audit by default*: evidence is never replaced silently.

- **An aggregator of one value per policy on a per-period column names its
  `Period` form.** `Sum("net_cf")` over a column holding one value per
  period failed inside Polars' grouped sum -- "`sum` operation not supported
  for dtype `list[f64]`" -- with no sentence of gaspatchio's, in a scenario
  plan and in `run_aggregated`; written with `within="max"`, `"min"` or
  `"mean"` it answered null for every scenario without a word. It is now
  refused before anything is folded, naming `PeriodSum("net_cf")` (or the
  kind's own `Period` form) and the per-policy alternatives.
  `within="count"`, which counts the policies, runs as before.

  Serves *Sharp knives, no magic*: a fold the column cannot answer is refused
  rather than answered with nothing.

- **Dividing by a number divides, on every engine, at every size and in both
  `run-model` modes.** `af.coi_per_1000 / 1000`, `af.annual_rate / 12`,
  `af.month / 12.0` -- and `//` and `%` -- reached a Polars float kernel that
  multiplies by the divisor's reciprocal instead of dividing, whenever the
  divisor was a literal or a column holding one constant: 135.021 / 1000 read
  0.135021, not 0.13502099999999997; 5 / 12 read 0.41666666666666663; and
  0.3 // 0.1 read 3 with a negative remainder. Which kernel a formula met
  depended on the engine and on how it split the rows, so `gspio run-model
  --mode debug` disagreed with `--mode optimize`, and a portfolio with a
  three-policy test of it. Every `/`, `//` and `%` over numbers -- per-policy
  or per-period, written as an operator or inside `finance.to_monthly`,
  `finance.compound`, `finance.discount`, `finance.present_value`,
  `projection.prospective_value` and `excel.round` -- now divides each
  element by its own divisor, and matches Python and Excel to the bit.
  Integer `//` and `%` keep their integer answer; a duration divided by a
  number keeps Polars' meaning.

- **The JAX engine divides as Polars does: `/`, `//` and `%` are one IEEE
  operation per element, whatever the divisor.** XLA turned a division by a
  literal into a multiplication by its reciprocal, so `af.maint_fee_rate /
  12.0` and `444391 / 10` (44439.100000000006) came back a unit in the last
  place off, and `0.3 // 0.1` read 3.0 where spec section 11.1.25's floor of
  the rounded quotient is 2.0. And `%` was the exact remainder a language
  computes rather than the clause's `a - b * floor(a / b)` in binary64:
  `1.0 % 0.1` read 0.09999999999999995 where Polars reads 0.0, and `1.0 %
  inf` read 1.0 where Polars reads NaN. A literal, a per-policy value, a
  per-period list: each now divides, floors and takes the remainder as the
  reference producer does, to the bit, on a corpus searched for the cases
  where the two rules differ. Levels 4 and 5 have nine more lines identical
  to Polars on the JAX engine; their worst line is unchanged.

- **Every JAX lowering that divides now divides as Polars does.** XLA rewrote
  each division by the form of its divisor -- a literal into its reciprocal,
  a power into the opposite power, a quotient of a quotient into one
  division by a product -- so `af.a / af.b / af.c` and `af.a / af.b / 12.0`,
  `finance.to_monthly(method="simple")`, `finance.compound`,
  `finance.discount`, `finance.present_value`, `round`, `round_sig_figs`,
  `excel.yearfrac` on all five bases, `excel.pv` and the end-of-period
  `projection.prospective_value` each answered a unit in the last place
  from Polars somewhere, and `round` a whole step: 75178.04 read
  75178.04000000001. Each is now the reference producer's own arithmetic, to
  the bit, on a corpus searched for the cases where the two forms differ.
  `round(1, mode="half_away_from_zero")` and `round_sig_figs` also kept a
  value just short of a half down, as Polars does, where the engine sent
  0.049999999999999996 to 0.1.

- **A forward discount factor is one over one plus the rate, on every
  platform.** `af.finance.discount_factor(..., method="forward")` raised
  `1 + r` to the power -1 through the power kernel, which is the platform's
  libm `pow`: correctly rounded on Linux and not on macOS, where about one
  rate in six hundred came back a unit in the last place off `1 / (1 + r)`,
  and every later factor in the running product carried it. It is now one
  IEEE division per period, as spec section 11.1.30 states it, so the factors
  are the same doubles on macOS, Linux and the JAX engine.

- **The JAX engine answers three more lines as Polars does, to the bit.**
  `excel.pv` takes the flat form `-(pmt * nper + fv)` for a rate within
  1e-12 of nought, as the core does, where it divided a cancellation by
  almost nothing at `r = 1e-13`; `projection.prospective_value` with a rate
  written as a number forms its discount factors as `v ** t`, the core's
  closed form, rather than a running product of `v`; and
  `projection.t_years()` adds each period's year fraction to the one before,
  where `k / 12` and twelve additions of a twelfth part company in the last
  place.

- **The JAX engine takes the book the core takes.** A book file whose sum
  assured is `Int32`, or whose age is `UInt8`, ran on Polars -- which reads
  every integer narrower than 64 bits as `Int64` where it enters the frame --
  and `gspio run-artifact --engine jax`, `--aggregate` and
  `run_aggregated(..., engine="jax")` refused the same file: "cast 'sa' to
  i64 before the run". The engine now reads `Int8` through `UInt32`, and a
  list of them, as `i64` at its door too, so the two answer one book alike
  (2,500,000,000 for 25,000,000 times 100) and record one book digest. A
  `UInt64`, `Int128` or `UInt128` column is one rule with the core's door: read
  as `i64` where every value fits, where it was refused by its width ("cast
  'sa' to i64"), and refused by the value past `i64` where one is not, naming
  `to_text()` and a narrower type.

- **The JAX engine runs a flag in arithmetic.** `af.smoker + 1`, `af.n *
  af.smoker`, `2 // af.smoker`, `2.0 ** af.smoker` and `af.in_force + 1` over
  a per-period flag answer `f64` on Polars, and the JAX engine refused every
  one of them by capability ("add is written over a Boolean at operand 0").
  It now reads a Boolean operand as its 0.0 or 1.0, per policy and per period,
  on either side and under all seven operators, and answers each line exactly
  as Polars does (`2 // af.smoker` is infinity where the flag is false). A
  per-policy flag on both sides of one operation is still refused, as the core
  refuses it where the line is written.

- **`10 ** af.t` is exact.** A number raised to a per-period exponent went
  through `exp(t * ln 10)`, which reads 10 ** 14 as 100000000000000.12, and a
  discount factor `(1 + r) ** -t` differed from Python's `**` in the last
  place in one month in five. It is now a power per element, as a list base
  already was. Zero and negative bases answer as before.

- **Two rates raised to a per-period power are two calculations.** A
  plugin call on a decimal -- `1.01 ** af.t` written through raw Polars, say
  -- lost the digits after the point when the library path in front of the
  call was scrubbed (`dyn float: 1.<plugin>:list_pow(...)`), so `1.01` and
  `1.07` fingerprinted as one engine-native fragment, and from a wheel the
  walk-through printed `1.` for the rate. The scrub now starts at the dot
  before the library, not inside the number. A model with such a fragment
  stamps differently; no other does.

- **A Smith-Wilson spot rate is nan wherever the fitted discount factor is
  zero or negative,** the out-of-range value the curve documents, on the
  scalar path and the column path alike. `spot_rate(t)` returned a complex
  number there, `discount_factor(t)` raised, a price of exactly zero raised
  `ZeroDivisionError`, and a column of times answered a number at t = 1 or
  t = 0.5 -- at 0.5 a positive discount factor from a negative price.

- **`.excel.round()` and the rollforward's rounding answer what Excel's
  `ROUND` answers.** Excel rounds the value a cell holds -- its 15
  significant digits -- not the double beneath it, and both rounded the
  double. A workbook's `ROUND(1.5 * 45366.20999999999, 2)` caches `68049.32`
  and `.excel.round(2)` gave `68049.31` (the double is `68049.31499999999…`,
  whose fifteen digits are a half); `0.5 * 161451.33` gave `80725.66` for the
  workbook's `80725.67`, which `round_sig_figs(15)` could not reach either;
  and a 3% credit on `5657268.499999999` under `grow(..., round_charge=2)`
  was `169718.05` for the workbook's `169718.06`, a cent the recursion then
  carried. One implementation in the core now serves `.excel.round()`,
  `round_charge=` on `charge`, `grow` and `deduct_nar`, and the state's
  `.round()`: the value's decimal expansion to fifteen digits (a sixteenth
  digit of 5 or more away from zero), then the stated places half away from
  zero, then the nearest double. **Results move** only where the two rules
  disagree: a value whose fifteen digits are a half its double is not
  (`2.675` and `1.005` at 2 places now give `2.68` and `1.01`), and values
  whose fifteen digits are coarser than the step (10^13 or more at cents),
  which now answer the fifteen-digit value as Excel does. Section 11.1.35 of
  the specification states the rule, the JAX engine answers it, and the
  published vectors carry the workbook's values. Two edges move with it: a
  negative value rounded at 309 or more places to the left now answers
  `-0.0` as every other negative that rounds to nothing does, and an infinity
  there stays infinite rather than becoming NaN. And a whole-number column
  now answers `Float64` at every place, as section 11.1.35 states and the JAX
  engine already answered; at places after the point it used to come back as
  the integers it went in as.

  Serves *Meet you where you are*: the number a converted model rounds is
  the number in the workbook.

- **A literal answers every policy, whichever engine runs the model.**
  `af.issue_date.excel.yearfrac(date(2025, 1, 1))` -- a year fraction to a
  valuation date -- refused under `collect(engine="in-memory")` ("Series
  years, length 1 doesn't match the DataFrame height of 3") and answered
  under the streaming default. The in-memory engine hands a plugin a literal
  as one row beside the frame, the streaming engine broadcasts it first, and
  the kernels walked their operands in step, so they stopped after the first
  policy. The same held for `irr` with one guess, and for a one-row list
  literal in a per-period `when/then/otherwise` (numeric or text), a power,
  `projection.accumulate` (one of its forms panicked), `excel.pv` and
  `list_clip`'s values. Each now reads a one-row operand for every policy,
  and an operand of any other height is refused with one sentence naming
  both counts. The quotients, `list_clip`'s bounds, lookups and the
  rollforward already answered every policy.

- **A per-period text or categorical condition costs about what a numeric
  one does.** `when(af.plan_code == "A")` over 100,000 policies x 360
  periods took 3.9 s collected in memory and 0.63 s (8.3 s of CPU)
  streaming; it now takes 1.5 s and 0.22 s (2.8 s of CPU), against 0.9 s and
  0.14 s for the same condition over numbers. A categorical column went from
  6.4 s to 3.0 s in memory and from 44 s to 36 s of CPU streaming; most of
  what remains is Polars passing a categorical column into a plugin. The
  comparison is decided in one pass over the periods instead of building a
  text value for every period; equality, code-point ordering, nulls and the
  refusal of text against a number are unchanged.

- **A per-period Categorical or Enum condition costs what a numeric one
  does.** `af.plan == "A"` over a per-period Categorical column, 100,000
  policies x 360 periods, took 4.2 s streaming (47 s of CPU) and 3.4 s in
  memory; it now takes 0.11 s (1.4 s of CPU) and 0.72 s. Against a value per
  policy (`af.plan == af.target`) it went from 4.5 s to 0.11 s streaming and
  from 3.6 s to 0.70 s in memory; an Enum column from 1.8 s to 0.11 s
  streaming and from 2.4 s to 0.70 s in memory. `==` and `!=` reach the
  kernel as the column's codes, with the right side cast to the column's own
  categories inside the expression, so Polars no longer re-enters every
  label at the plugin boundary. The answers are the labels' answers: a label
  the categories do not hold never matches, and a null on either side is
  null. The record still says `plan == "A"`. The orderings stay on the
  labels.

- **What the per-period comparison kernel costs now, measured.** Against the
  kernel this release started from (the build before its hardening), on
  100,000 policies x 360 periods, paired medians over six rounds on a quiet
  machine: `af.x == 0.0` through the frame is 13% faster in memory and 13%
  faster streaming; called directly on the kernel it is 14% and 13% faster;
  a comparison that holds in about half the periods (`> 1.0`, value
  branches) is 19% faster in memory and 16% streaming; a list on the right
  with value branches is 5% faster streaming and 3% slower in memory. Two
  later changes in this release move these. One answers a null operand or a
  null branch with null, as the specification requires. The other decides
  each period over plain numbers wherever a policy's branches are present,
  and that choice is branch-free: a large gain where the comparison is
  unpredictable, and a small cost where it is perfectly predictable. Against
  the build just before those two changes, `== 0.0` (never true over
  continuous values) is about 6% slower in memory and 2% streaming, where
  `> 1.0` is 25% and 10% faster; it is still the 13% gain above against the
  start of the release. Kernel timings of unchanged code move a few percent
  from one build to the next -- clip with per-policy bounds read 3% faster
  against one build and 4% slower against the next, with no change to its
  code -- so differences of that size are below what these measurements can
  resolve.

- **A per-period comparison with a null on the right answers null in those
  periods.** `af.x == af.v`, with `v` null for one policy, refused the whole
  run ("right at row 1 is null"). Against a per-period `v` whose row was
  null, it answered an empty run, as if the policy had no periods. A `when`
  with text branches on such a comparison nulled the whole policy. A null
  operand is a null comparison, as the specification states: that policy now
  answers null in each of its periods, and a `when` on it selects neither
  branch there. The other policies are unchanged. Text comparisons already
  answered this way.

- **A per-period list of the wrong length is refused by both lengths.**
  Numeric list comparisons said only "mismatched inner list lengths"; they
  now say `mismatched inner list lengths in one policy: right against left`
  with `left=1, right=3 in that policy`, as text comparisons do.

- **A per-period `then` or `otherwise` of the wrong length is refused, not
  cut short.** `when(af.x > 1).then(af.short).otherwise(0.0)`, with `short`
  one period shorter than `x` for a policy, answered that policy with the
  shorter run, and a longer `then` lost its extra periods: a wrong number
  with nothing said. This happened with a value or a list on the right, with
  all three lists, under a per-period flag and under a text condition. Every
  list branch must now have its policy's number of periods, as the
  specification states, and a misfit is refused by branch and both
  lengths: `mismatched inner list lengths in one policy: then against left`,
  `left=3, then=2 in that policy`. The shapes that already refused now say
  it the same way.

- **A per-period conditional's null branch answers null where it is
  selected, and nothing where it is not.** With number branches,
  `when(af.x > 1).then(af.v).otherwise(0.0)`, `v` null for one policy,
  refused the whole run (`then_val at row 1 is null`), and so did
  `.otherwise(None)`. A `then` or `otherwise` list null for one policy, or a
  null per-period column, answered that policy with an empty run, as if it
  had no periods, and a comparison assigned as a value did the same; a
  period whose unselected list branch was null answered null. As the
  specification states, and as text branches already answered: a null
  selected branch is null in those periods, a null unselected branch
  changes nothing, a null policy is null, and an empty one is still empty.

- **A per-period PV whose lists differ in length within a policy is
  refused, not cut short.** `af.rate.excel.pv(af.nper, af.pmt)` with two or
  three per-period operands paired them by zipping, so a policy with three
  periods of rate and two of pmt answered two present values and said
  nothing. Every list operand must now have its policy's number of periods,
  as every other list kernel already required: `mismatched inner list
  lengths in one policy: pmt against rate`, `rate=3, pmt=2 in that policy`.

- **A null exponent, or a null per-period value under `clip`, answers
  null.** `af.x ** af.e`, with the per-policy `e` null for one policy,
  refused the whole run (`rhs scalar at row 1 is null`); that policy now
  answers null in each of its periods, as the specification states for a
  null operand of any arithmetic. `af.x.clip(af.lo, af.hi)`, with `x` null
  for a policy, answered an empty run -- a policy with no periods, which a
  later sum reads as nought -- where the same clip with literal bounds
  answered null; it now answers null by either route.

- **A per-period conditional with text branches keeps its text type when
  every policy is null.** `when(af.x > 1).then(af.label).otherwise("z")`
  over a batch whose `x` is null for every policy answered a column of type
  `List(Null)`, where the schema says `List(String)`; it now answers
  `List(String)`, nulls and all.

- **A text operand of `**` is refused by name, not answered with nulls.**
  `af.fund_value ** af.codes` (a text list as the exponent) and `af.codes **
  af.e` (a text list as the base) answered a run of nulls: the kernel cast
  the text to numbers, and text cast to a number is null. A text value per
  policy as the exponent was refused only because that null exponent was.
  All three now refuse: `list_pow works on numbers, and these lists hold
  str`. A `Decimal` operand of `**` is refused the same way, as `/` already
  refuses one: cast it to `Float64` first.

- **An integer raised to a negative power is a double.** `af.a ** -1` and
  `af.a.pow(-2)` on an integer column failed when the frame ran, inside
  Polars -- ``conversion from `i32` to `u32` failed in column 'literal'`` --
  while the audit file called the line `i64`, and the JAX engine refused it.
  Two integers keep an integer power only for an exponent from 0 to
  2**32 - 1 (section 11.1.25); a written exponent outside that reads the base
  as its double, so `af.a ** -1` is the double power, within §11.1.25's
  relative `1e-12` of `1 / a`, and the record says `f64`, on both engines. An exponent that is a column keeps the integer rule.

- **An integer raised to an integer column outside 0 to 2**32 - 1 says to
  write `to_float()`.** `af.a ** af.k` with a negative `k` failed inside
  Polars with ``conversion from `i64` to `u32` failed in column 'k'``, and
  the JAX engine's refusal said only "write the power in floating point". The
  line still answers an integer where the exponent is in range; outside it,
  both engines now name `to_float()` on either operand --
  `af.a.to_float() ** af.k` or `af.a ** af.k.to_float()` -- and Polars keeps
  its own text beneath the sentence.

- **A list kernel's refusal names the policy, not a row of its batch.** The
  engine hands a list kernel one batch of rows at a time, and the row a
  refusal named was counted within that batch: under the default streaming
  engine a misfit on frame row 1, policy P002, read `row 0`, and in memory
  `row 1`. The streaming error also lost its `Failing column` block, because
  the two engines' first lines differed. Every kernel that pairs per-period
  operands -- a conditional, a comparison, `**`, `/`, `//`, `%`, `clip`,
  `accumulate`, `yearfrac`, a lookup with list keys, a rollforward's inputs
  -- now says `in one policy` with the operand and both lengths, and a null
  per-policy clip bound says `is null for one policy`. The error
  report then reads the frame once and adds the policy:
  `Policy: policy_id=P002 (row 1), and 2 more`, by the column
  `--policy-id-column` named, else `policy_id`, `point_id` and the other
  identifier names the runner reads, or by the row alone where there is
  none. It costs nothing on a run that succeeds.

- **Polars' own list-length error names the calculation under streaming
  too.** `af.out = af.x * af.short` with one policy a period short raised
  `list lengths differed at index 0: 3 != 2` under the default streaming
  engine with no `Failing column` block: Polars counts that index within
  the batch it was computing, the replay that names the calculation counts
  it within its own head, and the replay compared first lines byte for
  byte. That one Polars line is now read by its form, its digits as the
  batch's, so the block names the calculation and the policy in both
  engines, through `+`, `-`, `*` and a raw Polars expression alike.
  gaspatchio's own error lines are still compared exactly. With two
  genuine breaks the block can name the one the replay reaches while the
  line's digits describe the other; it never names a calculation that did
  not break.

- **A rollforward's refusal through a frame names the line that read the
  run.** `af.av = compile_rollforward(builder).expr_for("av")` with an input
  a period short for one policy refused with `mismatched inner list lengths
  in one policy: rollforward input column premium against the policy's
  period count` and no `Failing column` block, in either engine: the frame
  puts the run on its plan as a hidden column when `av` is assigned, and
  the error report's replay could not rebuild the plan from before it. It
  now does, and names `av` -- the line that put the run on the plan, at its
  own source line -- with the policy (`Policy: policy_id=P002 (row 1)`) and
  what it blocks. Two runs put on the plan by one call that break on one
  line are refused by name, listing both readers. A run that only a
  `select` reads still has no block, and nor, for now, does a run the
  frame goes on to filter or to follow with a second run. The `Reading:`
  line still says `rollforward:<fingerprint> (unknown)`.

- **A per-period text column compared with text decides by the text.**
  `af.db_option_t == "A"`, and `when()` on it, failed at collect with `the
  plugin failed with message: right at row 0 is null`: the per-period
  comparison cast both sides to numbers. Text now compares with text, by exact
  equality and, for `<`, `<=`, `>` and `>=`, by code point, against a value, a
  per-policy column or another per-period column, and selects numeric or text
  branches as a numeric condition does. Text against a number is refused by
  name.

- **A per-period conditional over two integers holds integers.**
  `when(af.duration > 24).then(24).otherwise(af.duration)` on a per-period
  column came back as a list of floats (`[3.0, 3.0, ...]`), because the
  list kernel selects in Float64; the same line on a per-policy column, and
  the JAX engine, kept the integers. The exported artifact declared the node
  `list[f64]` over a tree whose two branches are integers, which spec
  §11.1.28 types `list[i64]`, so a strict reader refused it. Two integer
  branches now give an integer list on every per-period route; an integer
  opposite a double is still a double. The numbers are unchanged; the
  column's type is `List(Int64)` where it was `List(Float64)`.

- **A per-period flag reads as 1.0 or 0.0 in arithmetic, whatever the
  operator or the side it is on.** `af.in_force * 1.0` and `af.in_force -
  0.5` over a per-period Boolean column failed with "failed to materialize
  unknown type" while `1.0 * af.in_force` worked, and the forms that worked
  disagreed about the type (`+ 1` gave whole numbers, `flag * flag` unsigned
  ones). A per-period flag is now read as a run of 0.0/1.0 before any
  operator, `/`, `//` and `%` included, as a per-policy flag already was.

- **`&`, `|` and `~` take a flag the model stored as a 0.0/1.0 number.**
  `when(af.flag)` ran over a Float64 column holding 0.0 and 1.0 -- an input
  column, or a comparison assigned earlier such as `af.in_force = af.month <
  af.term` -- while `af.flag & af.eligible` and `~af.flag` refused it at the
  line ("Compare numeric flags explicitly"). The operators now read such a
  column under the same check `when` applies (section 11.1.27 of
  `spec/graph-artifact/v0-preview.md`), per policy and per period: -0.0 is
  0.0, and a null, NaN, infinity or any other number -- 2.0, 0.5 -- stops the
  run at `collect()` with "Column 'flag' is used as a condition but holds a
  value that is neither 0.0 nor 1.0", naming `(af.flag == 1.0)` as the
  comparison to write instead. The column keeps its Float64 storage; a
  per-policy answer is a Boolean and a per-period one a run of 0.0/1.0, as
  for any other operand, and either stands as a condition. A whole-number
  column, a literal number and an arithmetic result are still refused where
  they are written. The JAX engine runs the same lines over an exported
  artifact and checks the same values, so the two engines agree on what such
  a model means.

- **A period shift over a per-period flag asks for a flag to fill with.**
  `previous_period()`, `next_period()` and `at_period()` fill the period they
  run off the projection with `fill_value`, whose default is `0.0`; over a
  per-period Boolean column that failed with "failed to materialize unknown
  type". It now refuses by name and says to pass `fill_value=False` (or
  `True`, or `None`), or to turn the flag into an amount first.

- **A per-period conditional over two flags holds flags.**
  `when(af.month < af.term).then(True).otherwise(af.rider_active)` on a
  per-period column came back as 1.0/0.0 doubles; the same line on a
  per-policy column, and the JAX engine, kept a Boolean, which is the type
  spec §11.1.28 gives it. Two Boolean branches now give a `List(Boolean)` on
  every per-period route. Arithmetic over the result reads it as 1.0/0.0
  (above); a period shift over it needs `fill_value=False`. A comparison
  written as a branch is still the 1.0/0.0 indicator the frame stores for a
  comparison.

- **A null per-period column raised to a power is null.** `af.base **
  af.exponent` and `af.base ** 2.0`, where a policy's whole per-period base
  or exponent was null, answered an empty run (`[]`), which says the policy
  has no periods; spec §11.1.25 answers null, as a per-policy base already
  did. They now answer null.

- **`|` works between Boolean columns.** In 0.9.0 `|` answered only when
  one of its operands was a comparison, and not always then: `af.a | af.b`
  over two Boolean columns raised `TypeError: unsupported operand type(s) for
  |: 'ColumnProxy' and 'ColumnProxy'`, as it did with `True` or `False`, and
  a column on its left with a comparison on its right raised an
  `AttributeError`. It now takes any Boolean operand on either side, as `&`
  does, and answers a Boolean: `af.a | af.b` over `[True, False]` and
  `[False, False]` is `[True, False]`. The two forms that did answer and now
  answer in another type, `(af.a & af.b) | (af.i > 4)` among them, are
  listed under *Breaking*. On per-period Boolean columns `&`, `|` and `~`
  answer each period as a 0/1 indicator, where 0.9.0's `|` raised and its
  `&` and `~` failed at `collect()` -- all but `& True`, which answered and
  is the second of those two forms.

- **`cut`'s documentation writes a band the record can carry.** Both of its
  examples assigned the bare band, `af.band = af.age.cut(...)`, and the
  export then refused the model with `Column 'band' has type Enum`: a band is
  an ordered category, which the artifact's type vocabulary has no name for
  (section 11.1.4 of the specification). The docstring now says so, and the
  examples end in `.to_text()`, which carries every label unchanged. The
  export's refusal of a bare band is unchanged and names the same move.

- **A workbook's rollback converts as one portable line.** A reserve whose
  row reads the row below it -- `V[t] = v[t] * V[t+1] + cf[t]`, a workbook's
  `R[1]C` -- had no spelling on the proxy. The discovery reference said
  "reverse, accumulate, reverse back", `list.reverse` was not a declared
  operation, and through `polars_native()` three of the line's nodes became
  engine text: `validate --engine jax` refused the model and the audit tier
  read "engine fragment". `af.cf.projection.accumulate(initial=0.0,
  multiplier=af.v, addend=af.cf, reverse=True)` is now that rollback in one
  line, run back from each policy's own last period and stepped, never
  divided; a null step loses every earlier position. `af.x.list.reverse()` is
  declared too -- each policy turned within its own length, a null moving
  with its position -- for a rollback that is not linear. Both are core
  nodes the JAX engine lowers, and the named rollback equals the three-step
  spelling to the bit. Every `projection.accumulate` node now records
  `reverse`, false where it ran forward, so its digest and
  `graph_fingerprint` move once with the same numbers behind them; a
  document written before it reads as the forward recurrence it was. The
  discovery and extending skills route a rollback to `prospective_value` for
  discounting, `remaining_sum` for a suffix sum and `accumulate(reverse=True)`
  for any other linear one; a floored rollback has no named form in 1.0.

- **`projection.accumulate` reads only the policies it is handed.** Over an
  integer per-period column, each streaming morsel converted the whole book's
  values to decimals: 100,000 x 360 took 9.3 s and 36 s of CPU, against 0.9 s
  in memory. It now streams in 0.17 s (1.7 s of CPU).

- **A method chained straight onto a projection timeline means what it means
  on the column.** `af.projection.year_fractions().cum_sum()` ran Polars' own
  `cum_sum` on the timeline: on a shared grid it was accepted with shape
  `scalar` and failed at collect ("cum_sum operation not supported for dtype
  list[f64]"), or later with a refusal naming another line ("this column has
  one value per policy", a `list.get` argument error), while assigning the
  timeline to a column first gave the right answer. The six frame-level
  methods (`period_dates`, `year_fractions`, `t_years`, `anniversary_mask`,
  `is_in_force`, `contract_boundary`) now return an expression bound to the
  frame: still a `pl.Expr`, so `pl.concat_list` and `.alias` work as before,
  but every declared operation -- `cum_sum`, `list.get`, `clip`, ... -- and
  every registered accessor answers as on the column, folding along each
  policy's periods. So `list.head`, refused on a column, is now refused on
  `t_years()` too, with the same words and the same `.polars_native()` door.
  A literal list (a shared grid's timeline) is classified per-period rather
  than per-policy wherever shape is resolved. And `year_fractions().shift(1)`,
  which answered null in every row without a word, is refused as on a column
  -- as are `diff`, `forward_fill`, `backward_fill` and `interpolate` -- with
  the per-period `list.eval` spelling named.

- **The same holds for every expression the framework hands back.**
  `Table.lookup`, `MortalityTable.at`, `Curve.discount_factor` and
  `spot_rate`, and `CompiledRollforward.expr_for` and `increment_for` are
  bound to the frame their operands (or the rollforward's states) came from,
  so a method chained straight on means what it does on the assigned column:
  `lookup(age=af.attained_age).cum_sum()` folds each policy's periods instead
  of failing at collect, `expr_for("av").list.get(-1)` reads a period,
  `lookup(age=af.age).cum_sum()` -- which summed one policy's rate into the
  next -- is refused as on a per-policy column, and `shift`, `diff` and the
  fills on a per-period read are refused instead of moving values between
  policies. A comparison on a per-period read (`lookup(...) > 0.1`), which
  Polars refused as list-against-number, reads each period, and `mask &
  (af.t > 1)` and `when(af.projection.anniversary_mask())` work inline as they
  do on a stored mask. A rollforward holds its frame weakly. An expression
  with no frame in sight -- `Schedule.*_expr`, the raw-Polars door, or a
  lookup keyed only by literals -- stays a plain Polars expression, as
  `pl.col(...)` is. `list.get` and the other list methods on a per-policy
  column now say the column holds one value per policy, rather than that the
  arguments did not match.

- **`-`, `abs()` and `~` on an expression the framework hands back keep
  what it is.** They returned a plain expression with no record of the
  operand and no frame, so `-af.projection.t_years()` was engine text and a
  method chained after it ran Polars' meaning again, and
  `~af.projection.anniversary_mask()` was refused at collect ("dtype
  List(Boolean) not supported in 'not' operation"). On a bound expression
  they are now the operation a column's would be, per period; with no frame,
  `-` and `abs` keep Polars' value and record the operation.

- **`accumulate` reads a Decimal operand as its value.** A list of Decimals
  reached the kernel as unscaled integers, so a `Decimal(10,2)` addend of
  5.00 added 500 a period and a multiplier of 1.00 multiplied by 100; at
  scale 4 the error was ten thousandfold.

- **A per-period column is refused to the escape's `shift`, `diff`,
  `interpolate`, `forward_fill` and `backward_fill`, rather than answered
  down the model points.** These five have no operation in the vocabulary, so
  `polars_native()` is the only way to reach them — and Polars reads a column
  of per-policy lists as one value per policy. On two policies of three
  periods, `polars_native().shift(1)` gave `[null, [1.5, 2.5, 3.5]]`: the
  first policy's entire timeline moved onto the second policy's row, the
  right shape, the right dtype, no error. `diff` subtracted one policy from
  another; the three fills walked down the book, leaving an interior gap in a
  timeline unfilled, or dragging a neighbouring policy's values across the
  boundary. All five now refuse a per-period receiver, naming the axis and
  giving the spelling that means what an actuary reading `shift` reads:
  `af.account_value.polars_native().list.eval(pl.element().shift(1))`. On a
  per-policy column all five still answer exactly as before — the refusal is
  a question about the column's shape, not about the method's name, which is
  the same test that has always let a per-policy `cum_sum` through. The
  refusal you get for writing `af.account_value.shift(1)` without the escape
  is shape-aware for the same reason: on a per-period column it no longer
  sends you to a door that would answer a different question, but names the
  axis and the `list.eval` form alongside it.

- **`date.to_period()` works again.** Every call raised
  `AttributeError: No '_parent_frame' column accessor registered` — the
  accessor reached for a frame attribute that has never existed under that
  name, so the documented method could not be called at all. Snapping claim
  dates back to the month, quarter or year they fall in — the aggregation
  key an experience study groups on — now does what its docstring says.

- **A table's metadata is the metadata that table was given.** It was kept in
  one registry keyed by the table's name and written only when metadata was
  given, so a second table built under the same name with none reported the
  first one's study through `table.metadata` and `get_table_metadata()`, and a
  third built with other metadata rewrote what the first one reported. Each
  table now holds its own; the name reports the table it answers to for
  lookups, and none where that table was given none.

- **A table-read refusal names only moves that work where the line was
  written.** `af.q2 = mort.lookup(age=40).fill_nan(0.0)` -- a read keyed by
  values rather than by a frame column -- was refused with advice whose first
  move was `fill_nan(0.0)`, the line already written: on a read bound to no
  frame column the method is Polars' own. It now names the one move that
  works there: store the read as its own column, then continue from it with
  a declared operation or the escape. And `mort.lookup(age=af.age).sum()`,
  or a row-reading name on a timeline such as
  `af.projection.year_fractions().shift`, was told to write
  `.polars_native().sum`, which the frame then refused for hiding the read in
  a Polars expression; it now names the stored column's escape,
  `af.<column>_read.polars_native().sum`, beside the per-period form it
  already named.

  Serves *LLM-shaped from the inside out*: each refusal's next move runs.

- **A refused method form names the declared forms, and `replace(old, new)`
  is the mapping it means.** `af.x.fill_nan(None)` was refused citing
  `fill_nan(value: object | None)` as "the gaspatchio form", and
  `af.status.replace("IF", "INFORCE")` citing `replace(old: object, new:
  object | None = None, ...)` -- signatures that admit the very call refused.
  The refusal now names the forms that are declared -- for `fill_nan`,
  `fill_null`, `replace`, `clip`, `cut`, `round` and `round_sig_figs` -- and
  for `fill_nan(None)` says what to write instead: the number the model means
  there, or `.polars_native().fill_nan(None)`, which records the line as
  engine_native. One value and its replacement, `replace("IF", "INFORCE")` or
  `replace(old="IF", new="INFORCE")`, is now accepted as the one-entry mapping
  `replace({"IF": "INFORCE"})` and recorded as it is: one calculation, one
  record, one fingerprint, and the JAX engine runs it as it runs the mapping.

  Serves *Meet you where you are*: Polars' commonest spelling of a
  substitution is accepted, with nothing guessed.

- **A frame rebuilt from a weekly, daily or inception projection still
  refuses a period method on a per-policy column.** Over
  `ActuarialFrame(out)`, where `out` was a collected weekly projection,
  `af.q.projection.previous_period()` ran down the policies: three policies
  with `q` 0.1, 0.2 and 0.3 read `[0.0, 0.1, 0.2]`, each the previous
  policy's rate, and `cumulative_survival` gave `[1.0, 0.9, 0.72]`. The guard
  recognised a rebuilt frame by its per-period `month`, which only the
  month-aligned axes anchored on the projection stamp. It now also reads the
  `num_proj_months` every axis stamps, beside a per-period column, so the
  refusal is one rule on every axis; a Polars row operation over a
  per-period column on such a frame is refused the same way. A projection's
  output exploded to one row per period still runs the methods down its
  rows.

- **A weekly or daily axis no longer reads time in years that stands
  still.** Under the default `OneTwelfth` day count, four weeks from 31
  January gave `t_years()` `[0, 1/12, 1/12, 1/12, 1/12]` and
  `year_fractions()` `[1/12, 0, 0, 0]`, and a daily axis the same: the
  convention counts one twelfth of a year per whole calendar month, a week
  or a day spans none, and only the period that crossed a month end counted
  at all. A discount factor built on it discounted the first week by a month
  and the rest not at all. `OneTwelfth` now refuses to give year fractions
  on a weekly or daily schedule, at the line that asks, naming
  `Actual365Fixed()` and `ActualActualISDA()` and the move:
  `af.projection.set(schedule=Schedule.from_calendar_grid(...,
  frequency="1W", day_count=Actual365Fixed()))`, which gives every week
  7/365. The axis's dates and masks, which no day count reads, are
  unchanged, as is `OneTwelfth` on the monthly, quarterly, semi-annual and
  annual cadences.

- **`projection.set` on a frame with no data says the frame is
  uninitialized,** where it raised `AttributeError`.

- **`af.date.create_timeline()` and `af.date.add_duration()` keep the
  calculation record.** Both used to hand back a frame with no history:
  every column calculated before the call was silently relabelled a field
  the model points supplied, and a column nothing could account for was
  relabelled the same way. The frame after a date verb is the same model one
  step further on, so the record stays with it, and the column each verb
  creates is recorded as the calculation it is — a date range over the start
  and end it was handed, or a column moved by a duration.

- **`af.date.add_duration("issue_date", "1y")` does what its docstring
  says.** The in-place form the method has always advertised — name the
  column, get the offset dates back in it — did not work: the string became
  the literal text `"issue_date"` rather than a reference to the column, and
  the model failed at `collect()` with a Polars type error about a String
  where a Date was wanted. A string at frame level is a column name now, on
  `add_duration`'s `date_col`, on `create_timeline`'s `start_col` and
  `end_col`, and on `finance.present_value`'s `cashflow_col`, `rate_col` and
  `period_col` — which had the same defect, failing at `collect()` with
  `division with 'String' datatypes is not allowed` while its neighbour
  `finance.discount_factor` had always taken names. All of them now read the
  way `rename`, `drop` and `projection.set(issue_age_column=...)` already
  read one. A name the frame does not carry is refused at the call, naming
  the nearest columns it does carry, rather than becoming a literal that
  fails a projection later, and each of those parameters now declares that
  it takes a name or a column instead of borrowing the general expression
  alias, whose `str` means a literal everywhere else. Column-*level*
  operands are the other half of the same rule and go the other way: see
  the bare-string refusal under Breaking.

- **`af.date.create_timeline()` refuses a `new_col_name` the frame already
  holds.** The timeline is built under a temporary name and renamed into
  place, so asking for a name already on the frame landed a second column
  under it — legal to build, fatal at `collect()` with a Polars duplicate
  error, and, now that the verb stamps in place, on the only frame you had.
  It is refused at the call, naming the column and the two ways on: pick a
  name the frame does not hold, or drop that column first.

- **`af.date.create_timeline()` no longer emits a Polars deprecation
  warning.** The explode that turns each policy's date range into one row
  per period left `empty_as_null` to its default, which Polars 2.0 flips,
  so every timeline printed a deprecation notice from inside the framework
  that no model author could act on. The argument is stated now, at the
  value that keeps today's rows: a policy whose interval is empty — expired
  before it started, or a zero-length term under `closed="left"` — keeps one
  row carrying a null date, so it stays in the frame and is visible as a
  policy with no periods rather than disappearing from the model without a
  word.

- **A re-projection leaves no index of the old axis behind.** Calling
  `af.projection.set(...)` a second time replaced only the columns the new
  axis stamps, so a weekly axis laid over a monthly one kept a three-long
  `month` beside seven boundaries, a fixed step laid over a calendar grid
  kept its dates and `month`, and a calendar grid over a fixed step kept a
  four-long `step`. `broadcast_to_periods()` sizes itself from `month` or
  `step`, so on the weekly frame it gave a per-policy rate three values where
  the axis has seven. A re-projection now drops every column the previous
  axis stamped that the new one does not, and only those: the frame knows
  its own stamps from its calculation record, so a model-point column or one
  the model wrote over is never dropped. The reserved-name refusal holds on a
  re-projection too: a model point's `month` carried through a weekly axis,
  or its `step` through a calendar one, is refused by a later `set()` that
  would mint the name, where it used to be overwritten silently.

  Serves *Sharp knives, no magic*: a column of the old axis's length never
  passes for the new axis's index.

- **Two books that compute different numbers no longer share one digest.** A
  timestamp was digested at whole microseconds in UTC, so a book whose claim
  was notified 500 ns after the cut-off, and the same issue instants shown in
  Pacific/Auckland -- each of which the model answers differently --
  digested alike, and `gspio verify --model-points` said "✓ book agrees". The
  grammar now carries the column's zone and the instant to the nanosecond; a
  zone holding a NUL, reachable only with Polars' own zone validation off, is
  refused by name rather than read cut short.

- **An assumption table's identity is its content, whatever order the source
  listed its columns in.** The same rates published with two columns swapped
  used to carry two `table_fingerprint`s in the calculation graph, two graph
  fingerprints, and a warning that the table had been re-registered with
  different data. The processed table now puts itself in one canonical form --
  key columns by name, the value column last, rows sorted by the keys -- before
  it is hashed, registered, looked up and exported, so reordering a source's
  columns or rows, declaring its dimensions in another order, or re-saving it
  in another file format moves nothing, and a changed rate moves every reader.
  `Table.to_dataframe()` returns the table in that order. A table whose source
  held its keys out of name order, or its value column anywhere but last,
  stamps differently from 0.9.0 once; spec section 14.1 records the movement.
  `Table.canonical_form()` and `Table.source_sha()` no longer raise
  `ColumnNotFoundError` for a dimension declared with
  `DataDimension(rename_to=...)`, and `Table.extend()` accepts a slice whose
  columns are listed in another order.

- **A join's right side and a mortality basis are identified by their
  content too.** A join's `right_fingerprint` used to move when the right-side
  frame listed its columns in another order; the right side is now hashed with
  its columns in name order and its rows sorted, so only a changed value moves
  it. `MortalityTable.source_sha()` -- the `mortality` attribute on every
  `mortality.at` read -- left the rates out, so two mortality bases under one
  name with different rates shared it; it now carries the table's content
  fingerprint, and `MortalityTable.fingerprint()` returns the rates' identity
  alone. Both stamp differently from 0.9.0 once.

- **A key declared whole with `DataDimension(dtype=pl.Int64)` is read only
  from whole numbers.** The declared dtype was a truncating cast: keys 40.9
  and 42 became 40 and 42, so a lookup at age 40 answered the 40.9 row's rate
  where it should miss, and `"-1.5"` became -1, with only a log line saying a
  conversion would be attempted. A key that is not whole -- a double, a
  decimal or text -- is now refused, naming its value and source row, and a
  flag under an integer dtype is refused by kind. Whole numbers held as
  doubles, decimals or text read as those numbers, as before.

- **A dimension declared text with `DataDimension(dtype=pl.String)` stays
  text.** A text column whose cells all spell numbers -- maturity bands `"1"`
  and `"5"` -- is judged on those numbers when nothing says otherwise, and the
  declaration was judged the same way, so it changed nothing: the table held
  `1.0` and `5.0`, and text keys missed. The declared column now keeps its
  text, so `"05"` and `"5"` stay two labels, and a shocked copy, an extended
  table and a scenario run's stacked table keep it too. An undeclared column
  is judged on its numbers as before.

- **A lookup key is read by its value in the table's kind, or refused by
  kind -- never reported as a miss.** A flag, a fixed-point decimal or a date
  against a table of another kind passed the text-or-number check and was
  reported as "missing keys", with advice (`on_missing="nan"`) that turned
  every policy to NaN; a Bool-keyed table missed its own Bool query, a
  date-keyed table missed its own dates and answered an integer day count
  silently, and two nanosecond timestamps one apart would not build as two
  keys. A flag now reads as its 0 or 1 against a dimension keyed 0 and 1 --
  the record writes the operand `key * 1.0`, so every engine answers alike --
  and is refused naming the keys against any other ("this table's keys are
  1, 2"). A decimal key reads by value. A date or timestamp key answers a
  dimension of its own kind, in the table's unit, and a key of
  another kind on either side is refused by kind with the conversion to
  write, whatever the miss policy; a zone-naive timestamp against a zoned
  table is refused. Such keys are held as the whole number of their unit, so
  nanosecond instants stay distinct.

- **A text key looked up against a dimension the table holds as numbers is
  refused when the lookup is written.** It missed on every row -- reported as
  `missing keys (k="5")` beside a table whose source plainly held `"5"`, and
  as a silent NaN or fill under `on_missing="nan"` or a fill value. The
  refusal names the dimension, says when the table's own text column was read
  as numbers, and gives both ways out: declare the dimension text, or convert
  the key column to numbers while setting up the model points. A number
  looked up against a dimension the table holds as text is refused the same
  way, naming the cast that turns the key into text (and, where the dimension
  is declared text, the declaration to drop if its cells are quantities).

- **A table keyed by fractional numbers builds under the default storage.**
  An in-the-money band keyed 0.8 / 1.0 / 1.2, or a half-year duration keyed
  0.0 / 0.5 / 1.0 -- valid keys under section 11.1.24 -- raised the array
  encoder's own words ("Float64 keys with decimals not supported for array
  storage") before the default storage could fall back to hash storage. It
  now takes hash storage and answers by value; `storage_mode="array"` still
  refuses such keys.

- **A one-row table keyed by text builds.** A single-row parameter table --
  one switch keyed by its name -- was refused under the default storage with
  `null or unencodable key value in column 'item' at source row 0 while
  building table`, though two rows, or `storage_mode="hash"`, built. Polars
  holds a one-row column as a scalar, and the array store's key encoder had no
  arm for the form a scalar hands its text key back in. The refusal's log line
  also read "Failed to registered table"; it reads "Failed to register table",
  and "replace" and "append to" likewise.

- **A table whose answers are whole numbers builds.** A rate in basis
  points, an integer percentage or a count arrived as an integer column, and
  `Table(...)` failed with the kernel's `RuntimeError: invalid series dtype:
  expected Float64, got i32`; a `Float32` file failed the same way. The
  answer column is now read as the `f64` a lookup answers -- every integer
  width, and `Float32` -- so the table is the one its `3.0`-spelled twin is,
  under the same fingerprint, and `extend()` reads a slice the same way. An
  integer past 2**53, which no double holds exactly, is refused by its value,
  and an answer that is not a number -- a flag, text, an array -- is refused
  with a `ValueError` naming the cast, where the kernel raised a
  `RuntimeError`.

- **A categorical or Enum key reads a hash-stored table by its label.** Hash
  storage hashed such a key's dictionary index rather than its text, so a key
  the table held missed: a silent NaN under `on_missing="nan"`, and the fill
  value instead of the rate under a fill, where array storage answered the
  rate. A table is hash-stored on request, or when its keys are too sparse for
  an array.

- **A number looked up against a hash-stored text table misses, as it does
  against an array-stored one.** Hash storage hashed a number's decimal
  spelling, so the key `5` found a row keyed `"5"` where array storage missed
  it, and the answer depended on which storage the table was given. One query
  against one table now gives one answer, whichever storage it got.

- **A `Table` source that cannot be read lists its suggestions on separate
  lines,** where the message printed a literal `\n` between them. A dimension
  whose type conversion or expression fails carries the Polars error as its
  cause, and the table snippet `suggest_table_config` writes has no trailing
  whitespace.

- **`Table` takes any mapping of dimensions, and integer scenario ids, in
  its types.** `Table(...)`, `Table.from_scenario_files` and
  `Table.from_scenario_template` declared `dimensions` a `dict`, so a
  caller's own `dict[str, str]` failed a type checker though it ran; they now
  take any mapping. `from_scenario_files` takes integer scenario ids in its
  type, as it always did when run.

- **`TableBuilder`'s repr names a DataFrame source,** where printing a
  builder over one raised `TypeError`.

- **The classes `gaspatchio.assumptions` names are the ones `Table` accepts,
  to a type checker as at run time.** `Table(..., dimensions={"age":
  DataDimension("age")})` written with the public import failed mypy and
  pyright, because the package's stub declared classes of its own.
  `configure_telemetry` and the names `gaspatchio.errors` exports type-check
  too.

- **A text key column that spells whole numbers is judged on those integers,
  so a CSV of scheme references and a Parquet file of the same numbers publish
  one stamp.** A key column is cast to `Float64` on the way in wherever a
  double carries every one of its values exactly, and the range that decides
  it — the closed `[-2**53, 2**53]` — is what the entry below says, what
  section 11.1.24 of `spec/graph-artifact/v0-preview.md` says, and what its
  section 14.1 line spelled out when the payload grammar widened. Only the
  integer branch had ever drawn it closed. Handed the same numbers as text,
  the check compared the floats they parsed into and admitted only what fell
  strictly inside, because by then `"9007199254740992"` and
  `"9007199254740993"` are one double and admitting the first would have
  admitted the second. The text branch now asks what the cells spell before it
  asks what they parse to: where every cell spells a whole number, the column
  is judged on those integers, against the same closed range — which is
  already how text is read below the boundary, where `["007", "008"]` has
  always meant `["7", "8"]`. Any other spelling — a decimal, an exponent, text
  that is not a number, digits past a 64-bit integer — keeps the float rule it
  had. **One stamp moves.** A table whose text keys sit exactly on 2⁵³ is now
  cast as the integer source of the same values is, so it publishes that
  source's `table_fingerprint` rather than one of its own; below the boundary
  nothing moves, because the two sources already agreed there, and above it
  nothing moves either. That leaves the asymmetry above 2⁵³ standing — an
  integer key travels as `i64` and the same digits written as text travel as
  `str` — and section 15 of the format now states it as known. No shipped
  number changes: across the 156 data files in this repository, 315 text
  columns spell no whole integers at all, so this meets a table nobody has
  written yet and the answer to every lookup that worked before is the answer
  it gives now.

- **An assumption table's integer key stays exact past 2⁵³, instead of being
  cast to a float that folds neighbouring keys together.** Every numeric key
  column of a table was cast to `Float64` on the way in — a real speed choice,
  and the right one for the ages, durations, policy years and bands almost
  every key is. Past 2⁵³ a double stops carrying every integer, so a key
  column holding policy numbers, scheme identifiers or claim references in
  that range arrived with neighbouring keys rounded onto each other: two rows
  the file distinguished became one key, and the lookup answered one of them
  for both. A key column whose values do not all fit `[-2**53, 2**53]` is now
  left at the type it arrived in, so it is matched, published and hashed with
  every digit. Nothing changes for a key that fits — it is still cast, and a
  model that ran before this release returns exactly what it did. **The
  payload grammar widens with it.** A table payload's columns were `f64` and
  `str` and nothing else; they are now `f64`, `i64` or `str`, which a consumer
  parsing an exported artifact's inline table values meets directly. Section
  15 of `spec/graph-artifact/v0-preview.md` states the grammar and section
  14.1 now carries the line saying when it widened. **One stamp moves, and
  only where the keys behind it do.** The `table_fingerprint` on a lookup node
  is the content digest of the processed table, and the content grammar tags
  each column by its type — so a table with a wide integer key now stamps
  under `i64` and its exact values where it stamped under `f64` and rounded
  ones. That is a stamp moving because the content genuinely changed, which is
  the only reason a stamp in this framework should ever move; every table
  whose keys fit stamps exactly as it did. This rode in under a commit titled
  `fix(assumptions)` with no note of the grammar or the stamp; this is the
  note it should have had. It is the `Int64` half of the entry below, which
  says `Int64` keys were untouched by the *unsigned* work — they were, and
  this is where their exactness came from.

- **An unsigned assumption-table key is judged on its values now, not on its
  type.** Keys travel as signed 64-bit integers everywhere a model can be
  read back — the lookup, the assumption payload, the content hash — so a
  `UInt64` key column holding anything above 2⁵³, which is where a float
  starts folding neighbouring keys together, was refused outright. That
  refused far more than it needed to: policy numbers, scheme identifiers and
  claim references arrive as `UInt64` from plenty of warehouses, and nearly
  all of them fit a signed 64-bit integer exactly. Such a column is now
  measured and given the signed name its values do fit, so a table that
  loaded before this release's exactness work loads again and publishes its
  keys as `i64` with every digit intact. Only a value past
  9223372036854775807 is refused, and the refusal names that value rather
  than the type, and offers text — `.cast(pl.String)` on the table and on the
  query — as the way to keep the digits. `Int64` keys are untouched, above
  2⁵³ and below it. The blanket refusal went out undeclared; this is the note
  it should have had. This was about an assumption table's **keys** and
  nothing else when it shipped: a model's own `UInt64` column was still
  refused when the artifact was exported, because the type vocabulary was
  handed a type there rather than the values and so had nothing to measure.
  The export measures now as well — see **A model's own unsigned column is
  judged on its values at export, not on its width** under Changed below,
  which is this same rule reaching the other half of a run.

- **A compiled rollforward answers for the policies it is handed, and only
  those.** Over `ActuarialFrame(mp.head(1000))` -- or any zero-copy slice of
  a book -- it refused with "null inner values" when a policy the slice left
  out had a missing period. Through the streaming engine `collect()` uses by
  default, every morsel copied every input column of the whole book: a
  single-state rollforward over 100,000 policies x 360 periods took 17 s and
  48 s of CPU, against 2.6 s collected in memory. A sliced list column keeps
  the whole column's inner values and moves only its offsets; the kernel now
  cuts each input to its own rows before it reads them, and the same
  rollforward streams in 0.5 s (4.8 s of CPU).

- **`CompiledRollforward.increment_for` says what it reports.** Its
  docstring promised "what the op actually applied"; the value is, as the
  graph-artifact specification (section 16.2) rules, the target's value
  after the step minus its value before, in binary64 -- so an interest
  credit rounded to 151.62 can read `151.6199999999999`, and a period's
  increments sum to that period's change in the balance. The docstring now
  says so; the values are unchanged.

- **`af.<state>.increments[label]` and `.captures[point]` work, and answer
  only for the run the column holds.** The API reference documented both,
  and in 0.9.0 and since both raised `KeyError`. They now read the compiled
  rollforward the column came from, through a rename too, a swap or a chain
  in one `rename()` call included: `increments[label]` is its
  `increment_for(label)`, and `captures[point]` its
  `expr_for(state, point=point)`, and the stub declares both. After
  `materialize()`, `continue_from=`, a `select` that drops the run, or a
  rebuild from collected values, that run is no longer in the frame and both
  refuse: read them first, or call those methods knowing they run on the
  inputs as they are now. A label whose step moves another state is refused,
  naming the state that reads it, and a column no rollforward produced is
  refused, saying what defines it.

- **A rollforward read written after one of its inputs moved is refused.**
  In 0.9.0, `af.av = c.expr_for("av")`, then rewriting `fund_return`, then
  `af.av_after = c.expr_for("av")` gave `av_after` the first run's balance
  without a word; after `materialize()` or a `select` that dropped the run,
  the same line ran the kernel again over the later values, which neither the
  exported graph -- it binds a compiled rollforward to its inputs where the
  frame first reads it -- nor a second engine running it did. Such a read is
  now refused, naming the input and both lines: write it before the input
  changes, or give the later values a column and a rollforward of their own.
  A state's own `increments` and `captures` still answer from its run,
  written into a formula or not, and an input rewritten in a way that plainly
  keeps its values -- `af.fee = af.fee`, `af.fee = af.fee * 1` in the same
  type, or `projection.set` stamping the same timeline again -- is not counted
  as a change.

- **A number written as a rollforward step's amount is refused by name.**
  `.add(5.0)`, or a number given to any step that takes an amount, failed at
  compile with `AttributeError: 'float' object has no attribute 'meta'`, as
  it did in 0.9.0. `compile_rollforward` now refuses it, and a `pl.lit(...)`
  alike, aliased or not, naming the field and the move: put the value in a column
  (`af["amount"] = 5.0`) and pass that column, since the kernel reads each
  amount from a column, one value per period. A bare string amount, which
  could name a column or be a value, is refused at the step.

- **A rollforward increment's `reads_running_balance` is read off the amount
  now, and can say it cannot tell.** The `increments` summary a compiled
  rollforward carries in the `audit` profile answers, per movement, the
  question that justifies reaching for a state machine at all: does this
  movement's amount depend on the balance it is changing? Seven of the ten
  operations answer from their shape — a charge struck on the balance, a
  growth of it, a cost of insurance on the net amount at risk. `Add`,
  `Subtract` and `Apply` are the three whose expression **is** the amount, and
  those were answering a flat `false` whatever they had been handed. So an
  `Apply` whose body reads `av@bop` on a target of `av@eop` — an amount taken
  off the opening value of the very balance it moves, which is the movement
  that most plainly justifies the escalation — was published as not reading
  the balance at all. Those three now answer from the amount expression:
  `true` where it names the same state the increment's `target` names, at
  either point; `false` where it names an input column or a different state;
  and `null` where the amount is not a single column reference and cannot be
  classified. **Null is a claim, not a gap** — the producer looked and cannot
  say, which is what null means everywhere else in a node's record, and it
  sends a reader to the expression instead of a quiet `false` telling them
  nothing depended on the balance. An artifact exported from a build taken
  between the summary's first landing and this correction therefore says
  `false` on movements this release says `true` or `null` about. The member
  has been typed `boolean | null` in the published schema, and stated this way
  in section 16 and section 14.1 of `spec/graph-artifact/v0-preview.md`, since
  the summary was first written; it was the producer that answered a constant,
  and the correction went out under a commit message that did not name it.
  This is the note it should have had.
  No digest moves. An increment's identity is its position in its compilation
  — the compilation's `fingerprint` and the increment's ordinal — no
  per-increment digest is minted, and nothing about the summary enters a
  node's canonical bytes, so a movement whose answer changed carries the
  `fingerprint` it always did.

- **A rollforward's scratch column no longer reaches a scenario run's parquet
  files.** A compiled rollforward materialises one hidden struct so its kernel
  runs once however many states are read back out of it. `collect()` takes it
  off the frame it hands over and `af.schema` never lists it, so inside a
  model it does not exist — but the memory-safe drivers do not go through
  `collect()`, and `run_to_parquet` and `for_each_scenario(return_full_grid=True)`
  were writing `__rollforward_<fingerprint>` into every batch file beside the
  model's own columns. A column nobody wrote, that no node of the calculation
  graph answers for, and that is not even a number. Both hidden families — this
  one and the values a superseded definition keeps — now come off the plan in
  one place, without a schema resolve on the batch path.

- **The rollforward's length refusal advises only moves that work.** An
  input one element too long -- every column derived from a projection axis
  carries one value per period boundary -- was told "e.g. `.list.head(1)`",
  which is not a declared operation and is refused, naming the escape. No
  declared operation drops a column's final boundary, so the refusal now
  leads with the period-indexed builds that run -- a per-policy value passed
  as it stands, `.projection.broadcast_to_periods(like=af.projection.year_fractions())`,
  a column derived from `af.projection.year_fractions()` -- and names the
  escape, `.polars_native().list.head(n)`, with what it costs: the line
  records as engine_native and runs only on Polars, as does every
  calculation that reads it.

  Serves *LLM-shaped from the inside out*: the advice that runs comes first,
  and the one that costs portability says so.

- **A rollforward refusal no longer advises the impossible when an operation
  reads a running balance.** An operation whose arithmetic combined columns
  was told to work the expression out as a column of the frame first, which
  cannot be done where one of them is a running balance the machine itself
  computes. The refusal now says that balance has no column until the machine
  has run, and names the route for multi-state occupancy: one
  `projection.accumulate()` per state, in order. An expression over columns
  the frame holds keeps the old advice, which works there.

- **A model imports the files beside it under every `gspio` command.**
  `import norm_accessors` at the top of a model, with `norm_accessors.py` in
  the same directory, raised `ModuleNotFoundError` under `gspio run-model`,
  `run-single-policy` and `calc-graph`, although `python model.py` ran it: the
  loader did not put the model's directory on the path. It does now, for the
  model's import, as `calc-graph --scenarios` already did for a run script,
  and takes it off again afterwards. A second model loaded in the same process
  with a helper of the same name beside it now gets its own helper rather than
  the first model's, which Python had cached under the bare name -- under
  `calc-graph --scenarios` as well, where two run scripts each importing their
  own `model` were handed the first one's.

- **`gspio run-single-policy` refuses a policy it cannot find in one sentence,
  not a traceback.** A book with no identifier column -- a workbook's
  `scenario` column, a `variant_id` -- an id the column does not hold, or a
  `--policy-id-column` the book does not carry, printed a forty-line traceback
  through the runner and exited 1, the status of a model that raised. It now
  says the one sentence on stderr -- the names looked for, the columns the
  book holds, and `--policy-id-column <column>` -- and exits 3, as
  `calc-graph` does for a selection that names nothing. Which columns are read
  as a policy identifier is unchanged: only the names listed, never a guess.

- **An accessor needs no constructor of its own.** The column and frame
  accessor bases marked their working `__init__` abstract, so an accessor
  written without one could not be built. An accessor whose constructor
  raises now says so, naming the accessor, rather than vanishing behind an
  `AttributeError` that `hasattr` reads as "no such accessor".

- **`GASPATCHIO_MODE=optimize` refuses only the user's own `map_elements`.**
  It refused the framework's own slow path too -- a Schedule's
  `Actual365Fixed` day count -- in a model that wrote none.

- **A join that cannot happen leaves the frame as it was.**
  `ActuarialFrame.join` replaced the frame's plan first and wrote the join's
  record after, so a join that failed in between left a frame holding the
  other table's columns with no record of where they came from: a key given
  as an expression (`on=pl.col("product")`) failed with `'Expr' object is not
  iterable` after the columns had arrived, and a key that was a projected
  column of lists failed with Polars' `SchemaError` the same way. Both are
  now refused in plain words before anything changes -- a key is a column's
  name, and a column holding one value per period cannot be matched on --
  and the joined plan is resolved and its record built on the side, so any
  error Polars raises resolving a join, or the content grammar raises
  stamping its right side, leaves the frame untouched too.

- **`AF_ERROR_MODE=off` now switches error enhancement off on every frame.**
  The variable is the operator's kill-switch, and two kinds of frame used to
  survive it: one built with `mode="debug"`, and one that had been through a
  traced run. Both reached the column formatter regardless, so a misspelled
  column still came back wearing a did-you-mean panel in a session that had
  asked for no error handling at all — and the validation decorator enhanced
  on the frame's mode alone, whatever the session was set to. The environment
  variable now decides: under `off` the original exception is re-raised
  untouched, whatever the frame asks for. That covers the two rewrites that
  happen on the assignment line itself, before a collect is ever reached — a
  Polars method called through a column proxy no longer comes back prefixed
  `Error calling proxied Polars method '…'` with a source panel under it, and
  a value the frame cannot assign no longer comes back prefixed `Error setting
  column '…'`. A frame's own `mode="debug"` still adds detail *within* an
  enhancing mode, the default is still `enhanced`, and `basic` is unchanged.

- **Security: the panel for an attribute error no longer evaluates text taken
  from the exception.** It ran `eval()` on a type name read out of the error
  message, and any code can raise such a message. It now looks the name up
  among the builtins and the modules already imported, and runs nothing.

- **An error panel shows a division as `/`.** The panel's `Operation:` line
  (and the compilation panel's) printed the engine's raw text, so `af.a /
  af.b` appeared as the quotient kernel's name behind the absolute path of
  the library it lives in. It is now written as the audit record writes it:
  `[(col("a")) / (col("b"))]`.

- **A failed lookup names the lookup, not where the library is installed.**
  A lookup miss -- and any other error a framework kernel raised -- ended
  with Polars' expression line, `col("age")./home/<you>/.../_internal.
  cpython-313-darwin.so:lookup_by_table_and_hash()`, so every log the error
  reached carried the home directory. The line now reads
  `col("age").<plugin>:lookup_by_table_and_hash()`, the stand-in the audit
  file uses, under every error mode but `AF_ERROR_MODE=off`, which hands the
  engine's exception over as raised.

- **An error is located at the user's own line, whatever the file is
  called.** `raise_validation_error` and `gspio run-model --mode debug`
  decided which stack frames were gaspatchio's by file name, so a model kept
  in `validation.py`, `runner.py` or `execution.py`, or anywhere under a
  directory named `env`, was located at its caller instead. Every locator,
  and the line each calculation records as its source, now asks one
  question of a frame's file: is it inside the installed package, the
  interpreter's standard library or an environment's installed packages.
  That holds on Windows paths, where the patterns, written with `/`, matched
  nothing, and it passes over the standard library, so an error
  raised under `unittest` or a notebook's event loop is located at the
  user's line.

- **The missing-column panel lists the columns the failing line could
  read.** It listed the frame's current columns, the failing one among them
  when it was defined later, so the panel said a column was available while
  reporting it missing. Where the panel cannot tell which line failed, its
  location says so rather than naming a line it has not established.

- **A refusal the calculation plan raises now reads as a sentence, on its
  first line.** A lazy plan cannot raise, so a per-row refusal travels as a
  string made to fail a cast, and what a user met was Polars' headline about
  converting `str` to `i64` in a column called `literal`, with the real
  sentence third, inside an expression dump. Two refusals were delivered that
  way and both are now lifted to the front, naming the column and the next
  move: a stored numeric condition that is not exactly 0.0 or 1.0 (compare it
  — `when(af.flag == 1.0)`), and a whole-number conversion of something that
  is not whole (say which rounding you mean —
  `af.value.floor().to_integer()`). Everything the engine said is kept
  underneath, so nothing is lost. The lift reads only the list of values the
  cast actually refused: an unrelated failure on a model that happens to hold
  a stored indicator keeps its own headline, and under `AF_ERROR_MODE=off`
  nothing is lifted at all.

- **An enriched method error now names your line, not the framework's.** When
  a Polars method called through a column proxy raised during a traced run
  (`--mode debug`), the `Called from:` line in the rewritten message reported
  a file inside `gaspatchio/column/` and quoted framework source. It never
  reported the model's own line, for any model, at any depth. The location is
  now resolved the same way every calculation record's is — past the
  framework's frames to the model author's — so the message names the
  assignment you wrote, whole, and the function you wrote it in. Setting
  `GASPATCHIO_SOURCE_SPANS=off` now suppresses this location block too, since
  both readers share one capture; the failure itself is reported either way.

- **Validation and attribute error reports no longer claim a function scope
  they don't know.** An error raised at module level — a script, a notebook
  cell, the top of a model file — printed `Function: <module>` or
  `Function: module level` in its report: a placeholder, not knowledge. The
  Function line now appears only when the report genuinely knows the
  function the error was raised in, and is omitted entirely otherwise.
  Errors raised inside a function are unchanged and still name it.

- **A source location with no line to quote is reported, not dropped.**
  `SourceLocation.source_line` was a required string, so building a
  location for a frame with no readable source — a notebook cell, an
  `exec`-compiled snippet, a file edited since it was imported — raised
  inside pydantic and the whole location was lost, taking the file and line
  number with it. It is optional now: the location is reported with what is
  known, and a report with nothing to quote omits the source block rather
  than printing a heading over the word `None`.

- **Four refusals say what is true.** The column-shock refusal cited
  "skills/gaspatchio-workbook-conversion, spreadsheet-conversion.md", which
  does not exist; it cites
  `skills/gaspatchio-model-discovery/references/spreadsheet-conversion.md`.
  The validator's refusal of an accumulation setting outside what it admits
  said that "with constant rates both conventions give identical numbers";
  they differ at flat rates by a period's decrement or discount, and the
  refusal now says so, and that what flat rates hide is a wrong conversion
  between them. A shock naming both `table=` and `column=` was described as
  "(multiply to mortality.disc_rate by 1.1)", a dotted name neither field
  means; it now reads "(multiply by 1.1)" beside the two fields. And `gspio
  compare` no longer opens "These two results cannot be compared: These
  results are not of this artifact".

  Serves *LLM-shaped from the inside out*: an error message is read as
  instruction, so each one is true.

- **A refusal that sends a line through `.polars_native()` says what that
  costs.** Every refusal that names the escape now says the line records as
  `engine_native` and runs only on Polars, as does every calculation that
  reads it: `af.graph.tiers()` (or `gspio graph tiers`) names the line, and
  `gspio validate --engine jax` names it and every calculation that reads it.
  `is_between` names its declared spelling first, `(af.<column> >= lower) &
  (af.<column> <= upper)`, both bounds included as Polars' are, and
  `fill_nan(None)`'s refusal names the escape that fits the column's shape:
  `.polars_native().fill_nan(None)` on a value per policy,
  `.list.eval(pl.element().fill_nan(None))` per period.

- **`fill_series` logs the shape of its input, not its data.** With info
  logging on, every call rendered the whole input column into one log line,
  once per streaming morsel; it now logs the row count and type.

- **The API reference shows the docstrings for `scenarios`, `MortalityTable`,
  `TableBuilder` and `read_model_points`.** Four package stubs redeclared
  their names without docstrings, and the reference read the stubs: 41 entries
  on the scenarios page rendered blank, and `MortalityTable` did. The stubs are
  gone; each name is documented where it is defined. With them went two typing
  gaps they hid: pyright now keeps an `@scenario_aggregator` class's own type
  (built-in aggregators included) instead of reading instances as `Any`, and
  mypy accepts `Sum("pv").alias("pv")` inside `ScenarioRun`.

- **Editor help for `ActuarialFrame`, the column proxies and `when()` shows
  the full docstrings,** not the stubs' one-line copies, and `af.pipe(func,
  *args, **kwargs)` is type-checked against `func`'s signature.

- **`gspio knowledge` filters match in any case, and an empty result says
  why.** `-T IFRS17`, `-j EU` and `-d Standard` returned nothing because the
  index stores its values in lower case. When a filter matches nothing, the
  command says so on stderr and in the JSON `note`, names any value the index
  does not use, lists the ones it does, and suggests running without the
  filter; the same holds for an `--answer` left with no sources. The help, the
  CLI guide, `AGENTS.md` and the model-building and model-discovery skills now
  use filter values that exist -- most of their examples returned nothing --
  and say that repeating `-T` widens a search rather than narrowing it.

- **The principles link in `PRINCIPLES.md`, `README.md` and `AGENTS.md`
  resolves:** it pointed at a page that returns 404 and now points at
  https://gaspatchio.dev/latest/principles/.

- **`gp-docstrings run-print-check` exits with pytest's own code** when the
  structural lint fails, and no longer reports that pytest could not be run.

- **The published wheels carry the tutorials' data, not Git LFS pointer
  files.** Every release on PyPI from 0.5.0 to 0.9.0 shipped 81 of its 92
  tutorial data files as pointer text: one wheel of each of the eleven
  releases, and 0.9.0's sdist and its macOS and Windows wheels, fifteen
  downloads in all, each carry the same 81. So levels 3, 4 and 5 of
  `gspio tutorial init` wrote out small text files where the parquet data
  should have been, and those tutorials failed on their first read. The
  release build checked the repository out without its LFS objects and packed
  what it found. The build jobs now fetch the LFS objects of everything each
  distribution ships, and the release refuses any wheel or sdist that holds a
  pointer file.

- **The core's wheels and sdist carry the notices of the Rust code compiled
  into them.** The extension, `gaspatchio._internal`, is built from 284
  crates -- Polars, PyO3, their dependencies and theirs -- on the four
  platforms the wheels are built for and on Windows and Linux on arm64,
  where pip builds the sdist, and it links the Rust standard library. Most of
  that is MIT, which asks every copy to carry its copyright notice, and
  0.9.0's wheels carried none of it. The core now ships
  `third-party-notices.txt`, beside its other licence files in each wheel's
  `.dist-info/licenses/` and in the sdist: every one of those crates, with
  the licence it declares, the licence it is taken under and its licence
  text as the crate ships it, and a section on the standard library, whose
  crates' copyright lines it gives. It carries, too, the notices crates hold
  without declaring them: the C libraries two of them compile in, LZ4's
  (BSD-2-Clause) and Zstandard's (BSD-3-Clause, with divsufsort's MIT and
  the legacy decoders' BSD-2-Clause notices inside it), and the notices
  written out at the head of compiled files under copyrights their crates'
  licence files do not name -- among them Dmitry Vyukov's queue in
  futures-channel (BSD-2-Clause-Views) and third-party ISC notices in ring
  and rustls-webpki.
  The core's `License-Expression` is widened from `Apache-2.0` to what the
  wheel carries, `Apache-2.0 AND BSD-2-Clause AND BSD-2-Clause-Views AND
  BSD-3-Clause AND BSL-1.0 AND ISC AND MIT AND Unicode-3.0 AND
  Unicode-DFS-2016 AND Zlib`, and each of those licences' texts is among its
  licence files. `scripts/rust_notices.py` writes the file from `Cargo.lock`
  with cargo-about 0.9.2. CI holds it to what cargo compiles into the
  extension on each of those six platforms, and fails on any notice in those
  crates that it neither carries nor accounts for: a licence file below a
  crate's root, a licence written out in its files, a notice at its root
  that cargo-about did not read as a licence, or a crate's own licence text
  gone missing behind a standard one. The release refuses a wheel or sdist
  whose copy is not the one tagged, and the licence files are checked out
  with LF on every platform, so the Windows wheels carry the bytes the tag
  does.

  Serves *No vendor lock-in* and *Audit by default*: what ships says what it
  contains.

- **The `polars_backend` plugin examples show the output they produce.**
  `accumulate`, `list_clip`, `list_conditional` and `list_pow` each ended on
  a `with_columns(...)` call and documented no output for it, so a reader who
  copied one got a printed DataFrame the page had not shown. Each now binds
  its frame and shows the computed column as a list.

- **`gspio describe`'s suggested code reads the names it carries, and never
  runs them.** The snippet pasted each column name and the file's own name
  between quotes, so a name holding a quote closed the string and the rest of
  it ran as code when the snippet did -- `describe --json` offers that snippet
  to agents as `suggested_code`. Every name is now a Python string literal of
  the name, in the read-back, model-point and `Table(...)` snippets alike, and
  the console prints the snippet as code, unwrapped, never as markup. Serves
  *Sharp knives, no magic*: the tool does not author code its input chose.

- **`gspio describe` suggests a select and ultimate table that reads its
  ultimate rates along the attained age.** For the published layout -- rows by
  issue age, columns `1` to `N`, and `Ult.` -- it suggested
  `ExtendOverflow('Ult.')` with `overflow=` inside the `dimensions` dict, which
  is not Python; mended, it copied each row's ultimate rate to every later
  year, so a policy's rate stayed at its age at issue plus `N` for life (a
  tenth of the right rate at year 30 of a 3-year select table). It now
  suggests one long table keyed by issue age and policy year whose later years
  carry the `Ult.` rate re-keyed to the attained age, so a year past the last
  `Ult.` row is a lookup miss rather than a rate held flat. A key named only
  `Age` is read as the issue age, and the snippet says so; a table keyed by
  attained age, or with no age key, still extends its row with
  `ExtendOverflow`, now placed inside the `MeltDimension` it extends.

- **What `gspio graph` and `gspio describe` print is what the file holds.** A
  column name or node id carrying escape sequences set the terminal's title,
  wrote its clipboard (OSC 52) or erased the line above; one carrying Rich
  markup became a live link, and a column named `[/bogus]` made `describe`
  raise `MarkupError`. Every control character in their output is now written
  out as its escape (`\x1b`, `\x07`), the form `gspio validate` already shows
  an id in, and every name is printed as text. The same holds for every other
  command's console output, and for the names `validate`, `compare` and
  `verify` print. Serves *Audit by default*.

- **The paths, messages and frames the other commands print are text too.** A
  directory whose name reads as Rich markup -- `[link=…]`, or a closing tag
  such as `[/bogus]` -- made `calc-graph`, `run-model`, `run-single-policy` and
  `run-artifact` raise `MarkupError` at the line naming the file they had just
  written, and made `run-artifact`'s unreadable-book and aggregator lines,
  `compare`'s unreadable-result line (a damaged manifest member named there
  with what it holds) and the artifact readers' error lines do the same or
  print a live link. Those paths, the engine name and every error text are now
  printed as text. `run-model` and `run-single-policy` printed their result
  frame, and a failed model's message, with `print()`, so an escape sequence in
  a text cell or a column name reached the terminal; each is now written with
  its control characters spelled, as the consoles write them.

- **The results-analysis scripts' CSV is safe to open in a spreadsheet.**
  `artifact_timeline.py` and `portfolio_totals.py` wrote a text cell or a
  header beginning `=`, `+`, `-`, `@`, a tab or a carriage return as it was, so
  a column named `=HYPERLINK(...)` became a live formula in Excel. Each such
  cell and header now begins with `'`; numbers are written as they were.

- **`LinearInterpolate` fills a blank along the key, not the column order.**
  A melted table's blank cell was interpolated between its neighbours in the
  order the wide columns were listed, so durations `1, 2, 3, 5` with 0.08
  at duration 2, 0.02 at duration 5 and duration 3 blank gave 0.05 (the
  next column along) where 0.06 is a third of the way, and headers sorted as text (`'1', '10', '15', '2', ...`) gave
  0.03 where 0.07 is right. The fill now interpolates by the key's value
  within each group; where the columns were evenly spaced and in order no
  number moves. A blank along a key that is not a number (`'d1'`, `'Male'`)
  is refused by name, since there is no distance to interpolate over.

- **`LinearInterpolate(extrapolate=, fill_gaps=)` do what they say.** Both
  fields were declared and never read: `extrapolate=True` left a trailing
  blank blank, so the lookup refused it as a missing key (or, with
  `on_missing` set, answered NaN where the line gives 0.05), and
  `fill_gaps=False` still filled the interior. `extrapolate=True` now fills
  a blank before a group's first value or after its last along the line
  through the two nearest values (in log space for `"log-linear"`; a group
  with one value keeps its blanks), and `fill_gaps=False` leaves the blanks
  between values as they are. `LinearInterpolate(fill_gaps=False)` alone
  fills nothing and is refused. A table that sets neither field reads the
  same numbers as before.

- **`ExtendOverflow` with `to_value` inside the select period is refused.** A
  5-year select table with an `Ult.` column and `ExtendOverflow("Ult.",
  to_value=5)` (or 3) extended the ultimate rows over no duration, so they
  dropped out of the table with no word and a lookup at duration 6 missed --
  or, under `on_missing`, answered its fill. The extension now refuses,
  naming where it would start (the duration after the last select column, or
  `from_value`) and that `to_value` must reach it.

- **`FillForward` fills a blank from the key before it, not the column listed
  before it.** A melted table's blank cell took the value of whichever column
  happened to be listed before it, so durations whose headers sort as text
  (`'1', '10', '15', '2', '20', '3', '5'`) filled duration 3 with duration 20's
  0.02 where duration 2's 0.08 is right, and a column listed out of place took
  its listed neighbour's rate. The fill now runs along the key's value within
  each group and hands the rows back in the order they came; where the columns
  were in order no number moves. A blank along a key that is not a number
  (`'d1'`) is refused by name, as `LinearInterpolate` refuses it.

- **A lookup miss names a key passed as a value by its dimension.** A key
  written as a value, `lookup(product="pension", age=af.age)`, reached the
  lookup as a Polars literal, and the miss said "for key columns 'literal',
  'age'" and "(literal=pension, age=40)", naming nothing the author wrote. It
  now names the table's key column for that operand (`product=pension`); an
  operand that is a column keeps its own name (`attained_age=77`).

- **An annual month-end grid lands on 29 February in a leap year.** A
  calendar grid steps each boundary from the one before and re-normalises it
  to the month's end, but the annual step was left out of that rule, so a
  grid through February stayed on the 28th: from 2023-02-28 the boundaries
  ran 2024-02-28 and 2028-02-28, a day short, which an actual day count or a
  date column carried as the wrong day. Every month cadence -- monthly,
  quarterly, semi-annual and annual -- now keeps to the month's end, as the
  record format states.

- **A results file whose manifest holds the wrong shape is refused in a
  sentence, not a traceback.** A manifest member that parsed as JSON but
  not as what its writer writes -- `gaspatchio.columns` as a list,
  `gaspatchio.dtypes` as a number, `gaspatchio.versions` as a nested list --
  reached `gspio compare`, `gspio diff --results` and `gspio verify
  --results` and failed there with an `AttributeError`. Each member is now
  held to its shape when the file is read: `compare` and `diff` refuse the
  file, exit 2, naming the member and what it holds; `verify` names it as
  damage on the `results_manifest` line, as it already did for a member
  that is missing or does not parse.

- **`gspio validate` reads a wide sum back.** An executable artifact of a
  line summing about 195 terms or more -- a per-rider or per-cohort total,
  which the producer writes without complaint -- made `gspio validate`, and
  the structural read `gspio run-artifact` starts with, fail with a
  `RecursionError` traceback: the schema check recursed about six frames for
  every level of the operation tree. A tree deeper than 64 levels is now held
  to the schema one tree node at a time, with no recursion, so any depth is
  read (3,000 levels in about eight seconds), and a defect deep in a tree is
  named at its own pointer. Shallower trees are read exactly as before.

- **A column shock on a column no line of the model reads is refused.**
  `AdditiveShock(delta=0.01, column="valuation_rate")` over a model that
  discounts at a literal `0.03` -- common after a workbook conversion --
  ran, and reported a scenario equal to BASE to every digit under a
  fingerprint that said something changed. The `table=` equivalent was
  already refused. The run now refuses the plan after the first batch,
  naming the column and the model-point columns the model's lines do read,
  with the line each is read at. A column an aggregation folds directly is
  not refused, and the check stands aside where the record cannot answer: a
  model that collects and builds a new frame, or that filters, joins,
  renames or selects.

- **A helper edited between two runs in one process runs as its file now
  reads.** A model file was executed afresh on every load, but a helper
  imported from the same directory stayed in Python's module cache, so a
  notebook that edited `loadings.py` and ran the model again computed with
  the old helper, while the record -- which stamps the files on disk --
  named the edited one, and `gspio verify` agreed. Loading a model now lets
  go of every module cached from its own directory, including one the caller
  imported there by hand, so the helpers run again with it. An accessor such
  a helper declares is declared again by the same class statement and takes
  the earlier definition's place, rather than being refused as a second
  class under its name.

- **`gspio verify` no longer agrees over numbers that moved outside every
  stamp.** A model reads values from places no recorded file holds -- a
  scalar taken with `.item()` from a parameter file, a JSON config, an
  environment variable, a module imported through `sys.path` from outside the
  model's folder, a scenario plan's shock factor, the file behind a shocked
  table, a helper edited in the process that exported -- and each moved the
  results while every line agreed: tutorial level 5 printed "Nothing differs"
  over a moved `expense_maint`, and level 3's step 07 gave ✓, exit 0, over a
  moved discount rate in `../../base/model.py`. Given `--model` and
  `--model-points`, verify now rebuilds the graph from the files in hand and
  a graph that differs is ✗ whatever the stamps say, naming each line whose
  own calculation moved, with its formula and where it was written
  (`disc_factors@1 (model.py:219): (1.0 + disc_rate_mth) ** ...`). A scenario
  plan's export records its run script as `model.scenarios`, which
  `--scenarios` holds and rebuilds the record through.

- **A shocked or scenario-stacked table names the file its base was read
  from.** `with_shock()`, `from_shocks()` and a plan's shocked and stacked
  copies wrote `source_file: null` -- read by `verify` as "built from a frame
  in its own code" -- for a table the model had read from a named file and
  then shocked. They now carry the base's file, with `shaped_by` listing the
  base's own steps and then the shock in words (`shocked`) and, for a stacked
  copy, `stacked`, so the file is never read back as a plain read of the
  shocked table. A null `source_file` is described as what it is: the model
  handed the table a frame rather than a file's path.

- **`gspio verify` no longer agrees over a joined file or a helper loaded by
  path that it never checked.** A model that joined
  `assumptions/products.parquet` and loaded `helpers.py` with
  `importlib.util.spec_from_file_location` -- the route the model-building
  skill teaches for a directory that is not a package -- had both edited
  after export, and `verify --model --assumptions` printed `✓ assumptions
  agrees` and `✓ modules agrees` and exited 0. Each join the audit file
  records now has an `assumptions` line of its own: the right side is found
  by `NAME=FILE` under the join's recorded name (`join:1aa0680a=FILE`, no
  longer refused) or by its content among the files and directories given,
  and agrees where a file reads as it; where none does, the line says it
  could not be checked (exit 4), since the record names the joined frame's
  content and not its file. The `modules` line names each call by which the
  model or a local module loads code its import statements do not name
  (`model.py:6 spec_from_file_location`) and says it could not be checked,
  because `model.modules` lists what the import statements reach.

- **`gspio verify` no longer agrees over a column the record cannot account
  for.** A model that collected its model points, joined `loads.parquet` in
  Polars and built `ActuarialFrame(mp)` records the joined column as a hole,
  by name only; with the file edited after export, `verify --model
  --model-points --results` over the old results printed `✓ Every check asked
  agrees` and exited 0 while a re-run gave other numbers. A new `holes` line,
  read wherever `--model`, `--model-points` or `--assumptions` is given, names
  each hole in the record, its reason and the columns resting on it, and says
  it could not be checked (exit 4), for every reason a hole carries; an empty
  holes section agrees, and a results file checked alone is not asked. And
  `verify --assumptions <dir>` on a model that reads no table agrees, where
  it exited 4, so the documented command can pass there.

- **A frame a filter empties runs to an empty result on every door.** A
  model that values only its in-force policies (`af.filter(af.status ==
  "IF")`) and reads its horizon from a column (`until_value="term_months"`,
  or any `maximum_age`) raised a bare `TypeError: int() argument must be ...
  not 'NoneType'` from `projection.set()` wherever the filter kept nothing:
  in `collect()` over a lapsed book, and in any batch of `run_to_parquet`,
  `run_aggregated` or `ScenarioRun` that held no in-force policy. A frame with
  no rows now lays an axis of no periods and answers no rows; rows whose
  per-policy horizon is null in every one each project nowhere, as one such
  row already did; and one shared grid sized from rows that are all null is
  refused, naming the column. The largest horizon is read over the rows the
  frame holds -- a batch's in a batched run -- and on a per-policy axis it
  only records the longest, so each policy's numbers are those `collect()`
  gives. A `Table.lookup` with a literal key (`sex="M"`) over a frame with no
  rows answers no rows on the in-memory engine too, where it refused "key
  columns not equal length" -- the read a `column=` shock's factors make in a
  `ScenarioRun` batch.

- **A scenario's column has one type in every batch file, whatever shares its
  batch.** A `column=` shock that makes a whole-number column a decimal
  (`MultiplicativeShock(1.5, column="n")`) left BASE's `n` Int64 in a batch
  of its own and Float64 in a batch beside the shocked scenario, so a
  scenario's type followed the batch size and a `return_full_grid` directory
  could not be read as one dataset (`pl.scan_parquet` raised a
  `SchemaError`). A whole-number column any scenario of the plan shocks to a
  double is now a double in every batch file, its whole numbers exact; a
  shock that keeps a whole number (`AdditiveShock(1, column="n")`) keeps the
  column's type, and every scenario's numbers are unchanged.

- **A table shock reaches its scenario's fingerprint through the table's
  content.** A scenario composed alone read its shocked table through a copy
  registered as `<name>_shocked`, and a table read carries the table's name,
  so an identity shock (`MultiplicativeShock(1.0, table=...)`,
  `AdditiveShock(0.0, table=...)`), whose rates are BASE's, gave a
  fingerprint other than BASE's, and a real shock's fingerprint could be
  reproduced only by a model whose table was named `<name>_shocked`. Each
  scenario's `graph_fingerprint_by_scenario` entry now reads the copy as the
  table the model named, for `Table.lookup` and `MortalityTable.at` alike:
  an identity shock gives BASE's figure, and a x 1.1 shock gives the figure
  the model gives over the x 1.1 rates under the table's own name.

- **The refusal of a whole number past 2**53 states the rule it applies.**
  `to_float`, and every period operation that widens through it
  (`accumulate`, a shift under a decimal fill), refuses a whole number
  outside `[-2**53, 2**53]`, and said the column "holds a whole number no
  double names exactly" -- false for `2**53 + 2` or `374477 * 2**40`, each a
  double, refused because the doubles around it are more than one apart. It
  now says the number is outside `[-2**53, 2**53]`, where two neighbouring
  whole numbers can share one double; the refusal itself is unchanged.

- **A filter whose condition reads across rows is refused where the rows are
  not the book.** `af.filter(pl.col("sa") > pl.col("sa").mean())` kept the
  policies above the mean sum assured of the rows in the frame, so in
  `run_aggregated` or `run_to_parquet` cut into batches it chose from each
  batch's mean -- a total of `None` at a batch of one and 2200 at two over a
  book whose answer is 3000 -- and on a scenario axis from every scenario's
  rows together, with nothing refused. The filter is now held to the rule an
  assignment already meets: a condition reading across rows (a sum, mean,
  max, quantile, rank, window or row count) is refused by name in a batch of
  several and on a scenario axis, naming the model-point column to compute
  before the run; over the whole book it stands, and a read partitioned by
  `scenario_id` stands on a scenario axis whose policies are whole.

- **A Python function is refused where the rows are not the book.**
  `af.res.polars_native().map_batches(lambda s: s.rank() / s.len())` is a
  percentile of the reserve, a read across rows, but Polars will not hand a
  Python function's body over to be read, so nothing saw it: `run_aggregated`
  answered 110 over the whole book, 130 at a batch of two and 150 at a batch
  of one, where the same read written as `rank()` was refused. A
  `map_batches`, `map_elements` or `rolling_map` is now refused wherever a read
  across rows is -- a batch of several, a scenario axis -- whatever it
  declares, since its body cannot be
  read, and the refusal adds a third route: write it in Polars' own
  expressions. A plugin is taken at its own declaration: one registered with
  `is_elementwise=False` is a read across rows and refused there; one
  registered as elementwise stands. Over the whole book both stand.

- **An injected column is refused where it cannot be paired with its rows.** A
  column of values handed over wholesale -- a `pl.Series`, a NumPy array,
  `pl.lit(Series)`, a fixed `pl.int_range` -- lands on the rows by position.
  In `run_aggregated` or `run_to_parquet` cutting the book into batches its
  values were paired with whichever policies shared a batch, and on a batch
  of one Polars' streaming engine copied the one row once for each value:
  four policies became sixteen and a total of 3000 came back as 10000, a
  batch of two failed in Polars' words, and a one-row book through
  `collect()` came back three rows long. An injection of more than one value
  -- assigned, filtered on, or written inside a formula -- is now refused
  where a runner cuts the book, naming the model-point column and the one
  batch as the routes, and anywhere its length is not the frame's row count,
  naming both. One value stands anywhere, and the whole book takes an
  injection of its own length as before.

- **`gspio run-single-policy` shows the run's number for a model that reads
  across rows.** The command cut the book to its one policy and ran the model
  on that row, outside the rule the batch runners keep, so an overhead of
  12,000 allocated by share of sum assured gave every policy 12,000 where the
  run gives policy 1 its 1,500, a grid sized from the youngest life gave a
  policy a horizon of its own, and a filter on the book's mean valued a
  policy the run drops -- each exiting 0 with nothing said. The policy now
  runs alone under that rule: a model that reads one row at a time runs as
  fast as before, and where the model reads across rows -- a sum, a share, a
  grid sized from the rows, a setup rebuilt from collected values, a Python
  function, an injected column -- the whole book runs, the policy is selected
  from it, and one line names the read and its line: `model.py:8 reads across
  rows (sum on col("sa")), so this ran the 4-policy book and selected policy
  1`. A results file's manifest names the book that ran: the one row, or the
  whole book beside the selected row. A policy the model's own selection
  drops is refused by name. `gaspatchio.runner.run_single_policy` does the
  same and hands the line back as `route`.

- **`gspio run-artifact --engine jax` runs a wide sum, a deep `when` and a long
  conjunction.** The engine lowered an operation tree one Python call inside
  the next, so a line summing about 190 terms or more -- which the producer
  writes up to about 245 -- a `when` nested a few hundred times in its
  `otherwise`, or a long `&` of conditions stopped `run-artifact` with a
  `RecursionError` traceback. The arithmetic operators, the comparisons,
  `and`, `or`, `not` and `when` are now lowered from one stack, in the order
  and with the checks they always had, so a tree of them lowers at any depth
  the producer writes. Any other operation nested past Python's call depth,
  and a crafted tree deeper than the engine's checks of arriving operands walk
  (about 330 levels), is refused naming the node, how many operations deep its
  tree goes, and the move (split the line into named intermediate columns, or
  run on Polars). A
  crafted artifact nested deeper than the core reads trees (about 490 levels)
  is a finding on its node under `gspio validate --deep` and the engine's
  inspection, rather than a traceback.

- **`gspio validate --engine jax` reports the rollforward `run-artifact` will
  refuse.** A compiled rollforward on a schedule outside the two forms the
  executable subset states -- a `term_months` per-policy grid -- was read as
  `58 lowered, 0 refused` by `validate --engine jax`, and `run-artifact` then
  refused it (16.1), so a CI job gating on `validate` passed a model the
  engine would not run. The inspection now holds each machine's body and
  schedule to the run's own check, from the file alone, and names the
  running state and the line that reads it, refused, in the run's sentence
  and clause.

- **`gspio validate --engine jax` reports the projection axis `run-artifact`
  will refuse.** The level-1 steps, level 2, level 3 and every model that
  reads `period_dates()`, `t_years()` or `year_fractions()` on a calendar
  grid anchored on a month end validated as `0 refused` and then were
  refused by the run under 11.1.37; every `projection.set(schedule=...)`
  model, the level-3 typed tutorial among them, and every shared grid sized
  from the rows were refused under 11.1.1. The inspection now runs each
  axis-laying call's sizing from the record, as the run sizes it, and names
  the same nodes, in the run's sentence and clause.

- **Which policies a model values is part of its record.** `af.filter(...)`
  and semi and anti joins left `graph_fingerprint`, `formulas_fingerprint`
  and `book.digest` where they were whatever they selected -- keeping two,
  three or all four of four policies gave one identity -- so `gspio diff`
  said "formulas unchanged" across a change to the in-force definition,
  `gspio verify` agreed with a book in which a policy had lapsed once the
  model dropped its status column, and `gspio run-artifact --engine jax`
  valued the policies the model left out: net cash flow at t=0 came out
  -89.35174 where the model said -69.94987, the lapsed policy's -19.40187 in
  a total stamped with the model's own fingerprint. Each step now enters the
  audit file's `selection` list -- its kind, its condition as an operation
  tree, the columns it reads and, for a join, its right side's fingerprint
  and the table itself -- and both fingerprints cover it; the columns it
  reads are part of the book, so `verify` checks the in-force flag even where
  the model drops it; `gspio diff` reports a changed selection among the
  calculations; and every replay -- `run-artifact`, its `--aggregate` fold,
  `collect(engine=...)` and `run_aggregated(engine=...)` -- applies the
  recorded selection to the book before it projects. Selecting the model
  points before the frame is built is unchanged: that frame's book is the
  selected rows. The specification states it in section 7.6, and the
  conformance kit gains `vectors/selection.json`.

- **The JAX engine orders text.** `af.plan < "Whole"`, `when(af.plan >
  "TERM")` and `af.filter(af.plan >= "UL")` were refused on the JAX engine --
  "lt is written over text" -- though section 11.1.26 orders text by code point
  and the Polars engine answered them, so a model that ran on Polars did not
  run there. The engine holds text as one run's interned codes, which say which
  string and nothing about where it sorts; the four orderings now read each
  code's rank among the run's strings sorted by code point, per policy and per
  period, and answer exactly as Polars does (`"B" < "a"`, `"ab" < "abc"`, `"z" <
  "é"`). Equality is unchanged, and text against a number or a date is still
  refused.

### Changed

- **A negative zero now has its own fingerprint, and the byte-grammar token
  moves `gspv0-preview-2` → `gspv0-preview-3`.** Until now the canonical bytes
  of a calculation wrote `-0.0` as `0.0`, on the reasoning that the two are one
  number in the arithmetic. They are — but `to_text` spells them apart, `sign`
  reads the sign, and a finite number divided by one goes to a differently
  signed infinity than by the other. An external review exported one
  model twice, changing a single literal from `0.0` to `-0.0` and nothing else,
  and got `0.0` from one run and `100.0` from the other **under identical node,
  closure and graph fingerprints**, with `gspio diff` reporting no drift and
  both documents validating. An identity that equates what an operation can
  tell apart is an identity whose silence is wrong, so the normalisation is
  gone. Every NaN is still written as one quiet NaN: no operation in this
  vocabulary reads a NaN's payload bits, and two runs that both produced one
  have not drifted.

  **What this costs you.** The only document whose bytes differ under the new
  token is one carrying a negative-zero literal — measured across every
  artifact this repository publishes, **0 of 2,692 node digests moved**. But
  the token moves on every document all the same, because a consumer cannot
  tell from the outside which documents a grammar change reached: **two
  artifacts carrying different tokens must not be compared**, and `gspio diff`
  refuses in words naming both tokens rather than reporting an empty
  comparison. Re-export both sides from their models and compare those. The
  published schema pins the token, so a document written under
  `gspv0-preview-2` is now refused by shape; **the schema identifier
  `gaspatchio-graph/v0-preview.3` does not move**, because what a document may
  carry is unchanged. The published conformance corpus is regenerated and
  reprinted, and it gains a column holding a negative-zero literal so a second
  implementation has something to prove agreement on.

  The content grammar that hashes assumption tables and injected columns keeps
  writing a negative zero as zero, and now says so in its own words instead of
  pointing at the identity grammar: there a zero's sign is what an arithmetic
  left behind rather than what an author wrote, and a basis republished with
  the same rates should not announce a change nobody made.

- **The calculation-graph artifact moves to
  `gaspatchio-graph/v0-preview.3`**, which is the policy axis landing in the
  format: a required `policies` array in the envelope (section 7.4), and
  `value_sample`, `trace` and `branches` read along it. **A document carrying
  one policy is byte for byte what it was**, apart from `schema`, each
  facet's `_producer` and a hole's `closes_with` — three strings that name
  the edition of the specification the producer wrote under, and that move
  with the schema identifier for that reason — so each enrichment field on
  such a document is the value itself and never an array of one. A consumer written against `v0-preview.2` reads
  a single-policy document exactly as it always did and a multi-policy one as
  its first policy, `enrichment` being `policies[0]` with `why` left off.
  **No byte grammar moves**: a policy is no part of
  any node's canonical bytes, and measured on the level-4 tutorial model all
  128 node fingerprints and the graph fingerprint are identical between a
  one-policy export and a two-policy one. `document_digest` moves on every
  document, because every document gains the member.

- **A compiled rollforward's identity is its machine; the schedule it runs on
  is data.** `CompiledRollforward.fingerprint()` -- and so the
  `rollforward:` node id built from it -- was taken over the machine and its
  schedule together, so moving a quarter's valuation date under a UL or VA
  roll renamed the compilation and moved `formulas_fingerprint` as though the
  logic had changed. It is now taken over the machine alone: every state and
  opening value, every operation in order with its operands, label, rounding
  and timing, the stopping conditions, the batch axes, increment tracking and
  the engine binding. The schedule travels beside it: every rollforward call
  in the record carries a `schedule` attribute, the schedule's own
  `source_sha()`, which `graph_fingerprint` reads and `formulas_fingerprint`
  masks. A re-sourced schedule -- a new start date, another cadence, another
  fixed step -- moves `graph_fingerprint` and nothing else; an edited
  operation, operand or rounding moves the fingerprint, the id and both
  figures.
  - **Every compiled fingerprint and `rollforward:` id moves once**, and with
    them the digests of every rollforward node, every line reading one and
    the `graph_fingerprint` of every model holding one, with the same numbers
    behind them. Two machines that differed only in their schedule now share
    a fingerprint. Compared across this release with `gspio diff`, each
    compilation reads as renamed once. `fingerprint_algorithm` stays
    `gspv0-preview-3`: no byte grammar moved.
  - One machine compiled on two schedules in one process -- last quarter's
    model beside this quarter's -- runs as two kernel runs: the process files
    a compilation under the pair, and the kernel's scratch column is named
    for it.
  - One *model* holding one machine on two schedules is refused at export,
    naming the machine and both schedules, because the two runs would claim
    one node id. A model reaches it only by handing `RollforwardBuilder` a
    schedule other than its own projection's.
  - A line that wraps an extraction in an expression the record keeps as
    engine text (`pl.concat_list([opening, compiled.expr_for("av")])`) names
    the kernel's scratch column, which names the run, so under that one line
    a schedule change still moves `formulas_fingerprint`; section 12.6 of
    `spec/graph-artifact/v0-preview.md` states it.
  - The kit's rollforward vectors carry the new identities and the
    attribute, and its index is regenerated; the JAX engine's two
    rollforward-pattern artifacts are exported again.

  Serves *Audit by default* -- "the logic did not change" is a figure a
  reviewer can quote under a state machine too -- and *Sharp knives, no
  magic*: one identity with one meaning, and no exception to remember.

- **A compiled rollforward's `'portable'` binding now says the whole
  expression was recognised, not that six strings were absent.** The stamp on
  a compilation names which backends can run it, and it was derived by
  rendering each operation's expression to text and searching that text for
  six substrings — the five horizontal aggregates, and one fragment for an
  expression namespace nothing in the framework emits. A hit was always real
  and a miss meant only that none of those six had appeared, so a body
  reaching for `.list.sum()`, `.arr.sum()`, `.str.len_chars()`, a cast, an
  alias, an aggregate or `.shift()` was stamped `'portable'` — a claim about
  a body no portable backend could lower. The walk now reads each
  expression's own serialised tree and accepts exactly the closed subset the
  module has always documented: `pl.col`, `pl.lit`, `+ - * / **`, the six
  comparisons, `&` / `|` / `~`, when/then/otherwise, and the typed inputs
  `Schedule.year_fractions_expr`, `Curve.spot_rate`,
  `Curve.discount_factor`, `MortalityTable.at` and `Table.lookup`.
  Everything else is `'polars'` — an operation the walk has never seen
  included, and an expression the engine cannot serialise at all with it. A
  hit and a miss both mean something now, which is the whole point of a stamp
  a reviewer is asked to trust.

  **No compiled fingerprint moves.** The stamp is folded into the canonical
  form and so into `spec_fingerprint`, so this is the change most able to
  move every digest at once, and it was measured before it was made: the
  three shipped rollforward patterns, the level-3 step-07 model, and all 235
  compilations the test suite builds — 120 distinct fingerprints — stamp
  `'portable'` and carry the same digest on both sides of the change. Nothing
  the framework itself emits into an operation reaches outside the subset,
  which is why the correction costs nothing today and everything it is worth
  on the day a body does.

  Three admissions the one-line subset does not spell, each measured rather
  than assumed. `Clip` is accepted because `MortalityTable.at` on a
  select-ultimate table emits one, for the duration clamp at `select_period`;
  it is an elementwise three-argument min/max that every portable backend
  holds. `**` is accepted under the one payload it produces, so `.sqrt()` and
  `.cbrt()` — the same payload family under other names — refuse. A call into
  the framework's own extension is accepted by symbol, and only where the
  library it names is the extension the running process loaded, so the same
  symbol in somebody else's library refuses. A census test pins, construct by
  construct, the node identities the subset serialises to and the Polars
  version they were measured on (1.42.1), because a release that renamed a
  node kind would otherwise refuse every rollforward silently and move every
  fingerprint with it.

  Serves *Audit by default* — a stamp a reader can trust in both directions —
  and *Sharp knives, no magic*: an expression the framework cannot vouch for
  is refused rather than passed. Strains *Meet you where you are*: a body
  reaching outside the subset now binds to `'polars'`, which is what it
  always was.

- **A model's own unsigned column is judged on its values at export, not on
  its width.** Warehouses write policy numbers, scheme identifiers and claim
  references as `UInt64`, and an artifact names every integer `i64`, which
  travels as a signed 64-bit value — so a model whose model points carried
  one ran to completion and was refused at the last step, the export, with a
  refusal telling the author to go and cast it. That refused a finished run
  over a fact about somebody's Parquet writer rather than about the model,
  and asked for exactly the operation the exporter can check for itself: it
  holds the collected frame. It measures now. A `UInt64`, `Int128` or
  `UInt128` column whose every value fits a signed 64-bit integer is written
  as `i64`, and the node it writes is the one a hand-written
  `.cast(pl.Int64)` in the model produces — the same `local_fingerprint`,
  the same `graph_fingerprint`, the same bytes throughout. **No digest moves
  and none could:** no artifact carrying such a column could be written
  before this, so there is nothing published for a reader to compare against.
  Only a value no `i64` carries is refused — a `.hash()` column is past 2⁶³
  by construction and stays refused — and the refusal names the value and
  the column and offers `.cast(pl.String)` as the way to keep the digits.
  That is the shape an assumption table's unsigned key has been refused
  under since **An unsigned assumption-table key is judged on its values now,
  not on its type** under Fixed above, and this is the same rule reaching the
  other half of a run. **Where no values are in reach the refusal is
  unchanged, word for word.** A structural fingerprint
  (`af.graph.fingerprint()`) and an export asked for without the collected
  frame have the width and nothing else, and the producer does not guess.
  Section 10 of `spec/graph-artifact/v0-preview.md` states the rule and
  section 14.1 carries the line saying when the refusal narrowed.

- **A join with an eager right side takes that table's content fingerprint**,
  so a reviewer can tell which version of the expense table a run used. It is
  not free: the whole right side is sorted and serialised once. That is
  nothing for the reference tables a join usually brings and real for a right
  side of millions of rows. Pass a LazyFrame (`other.lazy()`,
  `pl.scan_parquet(...)`) to skip it — a lazy right side records no
  fingerprint, because hashing it would mean collecting the frame you
  deliberately handed over lazily. A join that brings no columns at all
  (`how="semi"`/`"anti"`) never pays it either.

- **A result's `inputs_digest` is the book's content, not a file's bytes.**
  The manifest's digest of the model points a run read was a SHA-256
  over the Parquet bytes Polars wrote for them. Those bytes move when a writer
  changes a default, so two runs over one book a Polars upgrade apart could
  report different inputs. No engine without Polars' writer could reproduce it
  either. It is now `content_sha_of` over the input columns, in name order:
  the specification's content grammar (§12.3), the same one every assumption
  table's stamp uses. Storage width is not content, so an `Int32` and an
  `Int64` holding the same numbers digest alike. A result file written by an
  earlier preview carries the old digest, so `gspio compare` against it
  reports different inputs. Re-run it to compare.
  - The digest reads every cell of the book, so its speed is the run's
    business at scale. Text and true/false columns are now encoded by
    whole-array arithmetic, as numbers and sequences already were, and a
    number column's varints are built only as wide as its largest value
    needs. The bytes are held identical to the row-by-row definition by
    test. The level-4 book's digest on a laptop fell from 3.25 s to 2.20 s
    at a million policies, and from 39.6 s to 27.7 s at ten million.
  - The encoder now runs in the Rust core. `content_sha_of` and
    `content_bytes_of` keep their names and their bytes, so no stamp
    moves; the Python encoder stays as the reference the core is held
    byte-identical to by test, over every type the grammar tags, nulls at
    every level of a list, sliced and chunked columns, and 300 frames
    drawn at random. The digest streams into SHA-256 as the core writes
    it, with the GIL released, so no buffer the size of the book is built.
    Types are still named in Python first, so every refusal reads as it
    did. Column names cross to the core as a list beside the frame: the
    Arrow C interface the frame crosses carries a name as a NUL-terminated
    string, and a Polars name may hold a NUL, so any name is hashed as it
    always was. A timestamp's zone is dropped on the way in, since the
    grammar hashes the UTC instant. One edge belongs to both encoders, and
    §12.3 does not settle it: a millisecond timestamp more than about
    292,000 years from 1970 wraps when it is scaled to microseconds, as
    Polars' own unit cast does. On the Intel laptop (i9-9880H) on
    2026-09-24, each run in a fresh process, median of three, the level-4
    book's digest fell from 1.88 s to 0.42 s at a million policies and
    from 22.3 s to 4.77 s at ten million, against the Python encoder
    measured the same way that day.
    A level-4 fold of a million policies through `JaxEngine().aggregate`
    spent 0.66 s of its 41–45 s on the digest, against 2.8–3.2 s with the
    Python encoder. What is left is mostly SHA-256 itself: this CPU has no
    SHA instructions, and the portable code in the `sha2` crate hashes at
    about 200 MB/s, half what OpenSSL manages on the same machine, over
    the 665 MB a ten-million-policy book encodes to.

- **Result files are written by Polars, and their manifest is read from the
  Parquet footer.** `gspio run-artifact` and `gspio run-model --every-node`
  now write through `DataFrame.write_parquet` rather than pyarrow. Writing
  the level-4 result at 10,000 policies (128 columns) takes 0.49 s instead of
  2.02 s, and the file is 111 MB instead of 70 MB: Polars' zstd with less
  dictionary encoding, against pyarrow's snappy. The result manifest
  goes in the footer's key-value metadata, and `read_manifest` reads it from
  there -- the one place every Parquet writer shares. Before, it read
  pyarrow's embedded Arrow schema, so a file written by Polars, DuckDB or
  parquet-rs with an identical manifest was refused as carrying none. Files
  written by earlier previews carry the manifest in both places and still
  read.

- **`round_sig_figs` states which way a tie goes: half away from zero.** 2.5 to
  one significant figure is 3.0, −2.5 is −3.0, 1245.0 to three is 1250.0. That
  is what the engine has always done, so **no number and no fingerprint moves**
  — what changes is that it is now written down, after the same review found an
  independent implementation reading the specification and answering 2.0,
  because its language takes a tie to the even neighbour. A model that wants
  the even neighbour uses `round`, which carries a `mode`. The clause's own
  worked example is corrected in the same pass: `0.001234567` to three
  significant figures is `0.00123`, not the `0.001234` it printed.

- **`to_text` states how it lays a float out, not only which digits it keeps.**
  "The shortest decimal that reads back to the same number" fixes the digits
  and leaves the layout to whatever the engine prints, and two implementations
  then wrote one number two ways — `1e-7` against `1e-07`, `0.00001` against
  `1e-05`, `NaN` against `nan`. Since this text is used as a key and tested in
  conditions, that is a difference in the model. The convention is now stated
  at the width the record carries: fixed form for a decimal exponent from −5
  to 15 inclusive and exponent form outside it, the exponent always signed and
  never padded, a whole decimal keeping its `.0`, a negative zero keeping its
  `-`, and `NaN`, `inf` and `-inf` for the three non-finite values. **It is the
  spelling every artifact already carries**, so no text a model ever computed
  changes.

- **`select` records each column it calculates,** as `with_columns` does, at
  the select's line, and takes a list of names as Polars does. A column
  handed back as it stands records nothing. Before this, a select that wrote
  a new expression under an existing name left Polars, the JAX engine and the
  exported artifact with three different answers and no refusal.

- **`collect()` keeps its view of the values for as long as you hold the
  DataFrame it returned,** where the frame holds anything a calculation
  produced, so a frame built over them can say which columns were
  calculated. It is a container over the same buffers, not a second copy.

- **Each public module states its public names.** Every module the API
  reference documents lists those names in `__all__`, and so does its stub;
  so do the two a custom accessor imports from, `gaspatchio.accessors.base`
  (the two bases) and `gaspatchio.frame.registry` (`register_accessor`).
  `gaspatchio.column` also exports `ListNamespace`, `StringNamespace`,
  `ConditionExpression` and the three `PolarsNative*` escapes, which were
  importable only from private modules. No `__all__` lists an underscore name.
  The tutorials import only public names (`gaspatchio.compile_rollforward`,
  `gaspatchio.assumptions.DataDimension`). Nothing is renamed or removed and
  every name still imports by name, but `import *` from a module now brings
  only the names it lists.

- **An aggregator's `.alias()` takes a string.** 0.9.0 accepted any value
  there, `Sum("pv").alias(5)` among them; it is refused at the call, naming
  the aggregator and the value.

- **Every reserved accessor name on the frame now says it is one.**
  `af.date`, `af.excel`, `af.finance`, `af.graph` and `af.projection` always
  resolve to the accessor, whatever the model points carry — a portfolio
  file with a column genuinely called `date` still has it, reached as
  `af["date"]` and assigned as `af["date"] = ...`, and this is the kind of
  thing an actuary meets once, at the wrong moment, with a vendor extract.
  Only `af.graph` documented it. Each frame accessor's docstring now says it
  of its own name, and attribute access on `ActuarialFrame` lists all five
  in one place alongside the two rules that were already there — Python
  keywords and underscore-prefixed names are not reachable as attributes
  either.

- **`executing` is a new runtime dependency.** It is what lets a calculation
  record name the statement that wrote it — the whole assignment, wherever in
  the file it sits and however many framework frames stand between it and the
  record — instead of a line guessed by counting frames. Every source
  location the framework reports now comes from that resolution. Setting
  `GASPATCHIO_SOURCE_SPANS=off` skips the capture: it walks the stack and
  resolves an AST statement on every assignment, which an unattended batch
  run pays for and nobody reads. What that costs is the whole audit surface,
  not only the locations — the formula an exported calculation graph shows a
  reviewer is the statement's own right-hand side, read off the same span, so
  with the switch off every computed node reports neither. The numbers and
  the fingerprints are exactly what they were.

- **The level-5 tutorial runs its model unchanged under every plan.**
  `model.main(af)` lost its `assumptions_override=` parameter and the
  `_maybe_scenario` guard at its four lookups, and every run script calls
  `plan.run(af, model.main)` with no wrapper. The per-scenario totals are the
  ones the door gave, bit for bit, over steps 01 and 02 and the rate
  scenarios at batch sizes 1, 2 and auto. Step 02 drops `time_column=`. Step
  04 writes its whole plan to YAML, the filtered stress included, and reads
  it back to the same SHA. Step 05 draws each scenario's mortality
  multiplier up front as that scenario's shock, so the plan carries every
  draw and runs at any batch size.

- **`gspio compare` takes seconds where it took minutes, and says the same
  thing.** It held each policy's timeline as Python lists, so level 4's
  every-node results took 92 s to compare over 10,000 policies and 12 s over
  1,000. Section 11.1.12's rule is now written once and read one line at a
  time in one Polars pass: the same comparison takes 5 s and 2 s from the
  command line, the comparison itself 1.5 s and 0.4 s. Every report is unchanged -- verdicts, `max_abs`, `max_ratio`,
  `scale`, `exact_class`, `rows_matched_on` and every sentence, byte for byte
  over the compare tests and level-4 runs.

- **Library logs are quiet unless you turn them on, and a warning you need
  arrives as a Python warning.** A script or notebook that uses gaspatchio
  writes no DEBUG or INFO lines to stderr, where 0.9.0 wrote six for every
  assumption table it built; `gspio` turns its logs on as before, and
  a script does the same with `logger.enable("gaspatchio")` after the
  import. What a user has to hear unasked -- a table name registered again
  with other data, a slow `map_elements`, an interpolation that fell back to
  another method, a filter that could not be applied -- arrives as a
  `GaspatchioWarning`, a `UserWarning`, through Python's `warnings`, located
  at the user's own line -- whether the code runs as a script, in a notebook
  cell, through `runpy.run_path` or with `python -m` -- so
  `warnings.filterwarnings` silences it and pytest captures it. `PerformanceWarning` is a `GaspatchioWarning`, and so
  are `Curve.from_svensson`'s two warnings, which were plain `UserWarning`s.
  What an exported document records about itself -- a book digest or a
  table it could not take -- the document says, and `validate`, `verify`
  and the viewer show it; it is not said twice.

- **`gspio describe` refuses a file it cannot read in one sentence, on
  stderr, and exits 2,** where 0.9.0 printed a whole framed traceback, with
  the cause on its last line, and exited 1. The sentence names the file and
  the reason --
  missing, a directory, a broken link and its target, permission denied, not
  a format `describe` reads, or damaged, with the next move -- and a Git LFS
  pointer is named as one, with `git lfs pull` to fetch the file. With
  `--json`, stdout stays empty.

- **Refusals go to stderr.** Every command writes a refusal as one sentence
  on stderr and exits non-zero, so stdout carries only the command's own
  output, and with `--json` nothing but the document. Several commands
  printed theirs on stdout.

- **`gspio compare` says how to get a result manifest.** A results file that
  carries none is refused naming the commands that write one.

- **`gspio --help` lists the audit commands under one Audit panel:**
  `calc-graph`, `validate`, `diff`, `sheet`, `compare`, `verify` and `graph`,
  where `calc-graph` sat under Model Execution and the rest under Data
  Inspection. `--policy-id-column` names the columns it looks for when it is
  omitted -- `policy_id`, `policy_number`, `policy number`, `policyid`,
  `pol_id`, `point_id`, `id`, the first the book carries, in any case -- and
  says what each command does when the book carries none of them.

- **The JAX engine counts its checks where it computes them, and hands back
  only what a finding reports.** Every check on a calculated value -- a
  lookup miss, a division by nought, an integer leaving its range -- used to
  come back from each batch as a mask over every cell of the batch, and the
  host scanned them all for the few that failed: on level 4, 142 masks and 4.8
  KB a policy, against 0.7 KB of the columns a fold reads -- about 48 GB across
  ten million policies. On an NVIDIA T4 reading those back was most of
  what a batch waited on. Now each batch counts, on the device, how many cells
  each check caught and the first of them, and hands back those two numbers
  for every check in one small array. The two checks whose test inside a
  compiled program over-reaches -- the range of a whole-number product and
  power -- also hand back their cells, which the host reads and judges exactly
  only where the device caught one. What a refusal or a note says does not
  move: the same counts, the same first policy and period, the same sentence.
  The suite holds every finding of levels 4 and 5, with a lookup miss, two
  domain checks and a coarse overflow put into their books, to the findings
  every mask read whole gives, batch by batch and merged, one batch at a time
  and one ahead, and level 4's, written out, to what the engine before this
  change found.

  On an NVIDIA Tesla T4 -- on 2026-09-25, against the code before this change
  on 2026-09-24 -- a ten-million-policy level-4 fold as a card runs it took
  17.8 s against 40.3, its loop 13.0 s against 35.5, reading back 0.14
  s against 22.3; a region pass one batch ahead took 15.14 s against 30.42,
  reading back 0.25 s against 18.65; and a million-policy fold 5.15 s against
  7.00. Three things rose, and the figures say so. Dispatching a batch, 7.29
  to 10.29 s in that region pass: with nothing left to read back, the host
  waits for the card there instead, so one batch ahead still buys only about 2
  per cent. The card's own calculation, by about a third, 8.23 to 10.86 s over
  the ten million: the counting's own cost on the card. And a program's cold
  compile on the T4, 1.45 to 4.12 s for level 4 at 4,096 policies.

  On a laptop the counting is laid out so the CPU pays no more than the scan
  it replaces: each policy's row is counted first, in a byte, and the checks
  of one shape are read together. Counted one mask at a time over every cell,
  a million level-4 policies' fold took 37 to 39 s where it had taken 22 to 26.
  On the Intel laptop on 2026-09-25, against the code before this change, the
  same fold one batch at a time took 23.4 and 26.0 s against 21.9 to 25.9 s,
  reading back
  15.3 and 17.0 s against 14.7 to 17.2 s -- on the CPU reading back is waiting
  for the calculation -- and peaked lower, at 1.38 to 1.39 GiB against 1.81 to
  1.83. A million-policy region pass through the engine's own loop one batch
  at a time peaked higher, though: 4.41 to 4.45 GiB against 4.08 to 4.09,
  about 8 per cent. One batch through the same program, once, peaks about 300
  MiB lower than before -- its masks -- so that rise is the loop's timing and
  the allocator's, not the program's. A level-4 program at 4,096 policies
  compiles cold in 2.6 to 2.8 s against 1.8 to 1.9 s, and loads from the
  cache in 0.15 to 0.17 s against 0.12 to 0.13.

  Building it found that the engine judged a whole-number product of a
  per-policy and a per-period value against another policy's cell: a product
  that had left `i64` could be published wrapped -- `2^62 * 4` came back as
  `0` -- or the run raised an `IndexError` instead of refusing. It now refuses,
  naming the cell.

- **A book the JAX engine hands over in its own order is written once,
  straight into the result.** The file sink staged every batch as a part
  file and, at publication, read every part back and wrote the whole book again
  in its own order, so each row was encoded and written twice: at 100,000
  level-4 policies with `--every-node` the merge was 6.5 to 6.8 s of a 19 to
  24 s run, and writing the parts another 3.6 to 6.4 s. The engine's batching
  plan is settled before anything is computed, and where it hands the book over
  front to back and every policy has the same timeline on every axis -- levels 4
  and 5 -- the engine now says so as it opens the sink,
  `Sink.open(manifest, in_order=True)`. Every batch is held to that
  promise: one at any other positions is refused as a defect in the engine, and
  nothing written remains. The file sink then writes each batch straight into
  the one unpublished result through Polars' own writer, with the manifest in
  the footer as before, and renames it into place when the run finishes. A
  million level-4 policies every node now publish in 141 and 124 s at 4.41 and
  4.51 GiB, against 272 and 253 s at 4.73 and 4.77 GiB staged; 100,000 in 18.7
  and 25.1 s against 25.0 and 32.7 s, peaking 0.1 to 0.2 GiB lower (the Intel
  laptop on 2026-09-25, fresh processes alternated with the staged code, other
  work loading it); re-measured after review the same day, 100,000 in 18.0 to
  22.8 s at 3.72 to 3.73 GiB against 29.4 to 46.7 s at 3.73 to 3.93 GiB. A run
  of one batch peaks about 0.2 GiB higher, because the rows in the writer's
  flight are copies. Every other book is staged as before: one whose widths
  interleave, such as the jagged term book, and one whose rows can widen --
  sorted by term, or with timelines that differ within a width -- because a
  file written straight through sizes its row groups from the first batch's
  rows and cannot resize them: at 400,000 level-4 policies sorted by width they
  reached 860 MiB where a block is 64 MiB.

  The file is the same: every node of levels 4 and 5 publishes the same rows,
  values, types and footer, in the same 64 MiB row groups and at the same size,
  as it did staged. What the writer holds is what Polars' writer has in flight,
  about two row groups a thread whatever the size of the book, and at 100,000
  policies it added nothing to the run's peak. Handing a batch over waits until
  every row of it has been copied into a piece of its own and taken, so a batch
  is let go before the next is built, and a key pressed meanwhile stops the run
  there -- as does one pressed as the writer starts, or a second one as the run
  is abandoned. A finished file is held to the rows handed over, and every wait
  on the writer gives up, and says so, after a minute in which it took no row
  and wrote no byte. Nothing partial is ever visible, as before: a refusal, an
  interrupt, a full disk or a fault leaves the destination as it was with no
  temporary file beside it. What the writer's own source met comes out as
  itself -- a key pressed as `KeyboardInterrupt` -- rather than inside the
  `ComputeError` Polars wraps round it; a full disk, which Polars' writer meets
  itself, comes out as the `ComputeError` Polars raises for it, naming the
  operating system's error ("File too large (os error 27)" where a file
  outgrew what the system allows).

- **On a card, the JAX engine settles the next batch while the card computes
  this one; and a fold's program hands back only the columns it folds (item
  3).** A book runs batch by batch -- settle a batch on the host, find its
  program, run it, read the answers back -- and each step used to wait for the
  one before it, so the card idled while the host settled and the host idled
  while the card computed. On a card the host now settles the next batch and
  hands it to its program before it reads this one back: settling overlaps
  computing, and reading a batch back waits for that batch's program and no
  other. That rests on settling reading nothing back off the device -- every
  width an axis takes was already counted when the book was prepared, and each
  lowering that lays an axis is now handed its batch's own counts -- because a
  read-back queues behind whatever the card is still computing. A calendar
  range's kept count is the one read left. A fold's per-period partials are
  queued straight behind their batch's own program. Nothing moves but the
  timing: findings stay in batch order, a refusal met settling a batch or
  building its program comes after every batch before it, a held fault stays
  behind a refusal, and every value is bit-identical either way: every node of
  levels 4 and 5 at 70,000 policies (on the Intel laptop on 2026-09-24), and in
  the suite every node of both and of a jagged book and every fold's totals
  (`tests/test_overlap.py`). On the CPU the batches still run one at a time,
  because there the device is the host's own cores: overlap measured a wash for
  a million-policy region pass and 30 to 40 per cent slower for a stream of
  140,000 level-4 policies every node, on the Intel laptop on 2026-09-24.

  Each batch of a fold now runs a program that returns the columns folded, the
  axes they stand on and every check's mask, and nothing else. Every node is
  still traced and every check still carried, so what refuses still refuses; a
  column no aggregator reads never leaves the device. Folding a best estimate
  and a cashflow term structure of level 4 returns two of the final schema's 128
  columns -- about 0.7 KB a policy where every column was 47 KB -- and a million
  policies on the laptop folded in 28.4 s at a peak of 1.84 GiB, against 32.6 s
  at 3.96 GiB returning every column (2026-09-24). Totals move only in the last
  bits a different compilation gives a policy's value, 2.8e-15 at worst over
  every supported aggregator on levels 4 and 5, and still agree with Polars
  under the agreement rule. Each set of columns folded is a program of its
  own, so a set folded for the first time compiles afresh and a column's last
  bits can differ from
  one set to another: `net_cf` folded alone and beside `pv_net_cf` differs by at
  most 6.0e-15 of a period's own total (the laptop, 2026-09-24). On an NVIDIA
  Tesla T4 (2026-09-24) one batch ahead saved 1 to
  3 per cent at ten million policies -- the fold's loop went from 36.3 to 35.6 s
  and a level-4 region pass from 31.15 to 30.29 s -- because the loop waits on
  reading every check's mask back (19.4 s of that region pass) and on dispatch
  (7.2 s), not on settling (1.9 s); reducing the checks on the card is the
  measured next lever, not yet decided. Returning only the columns folded halved
  the card's peak for a ten-million-policy fold, 5,009 to 2,485 MiB, in the same
  time.

- **The JAX engine writes every batch away as it finishes, so a book is never
  held whole.** `gspio run-artifact --engine jax` used to keep every
  batch's values, rebuild the book in its own order and hold the frames until
  publication, so a run's memory grew with the book: level 4 with
  `--every-node` peaked at 1.8 GiB at 10,000 policies and 3.9 to 4.4 GiB at
  30,000, and by the same slope would need about 11 GiB at 100,000. Now each
  batch's columns go to the sink the moment the batch finishes, with the book
  positions of its rows, and each column's buffer is released as it is copied
  out. The file sink stages every batch in a part file of its own in
  `<name>.<uuid>.unpublished.d/` beside the destination and, once every batch
  and every completion check has passed, streams the parts into one Parquet
  file in the book's order -- through Polars' own writer, with the manifest in
  the footer as before -- and renames it into place; a run of one batch
  renames its one part. The same runs peak at 0.96 GiB, 2.0 GiB and 4.2 GiB,
  about one batch's columns plus the book's own inputs and the process, and a
  million policies now publish on the same laptop: an 11.1 GiB file in under
  six minutes, at 5.1 GiB.

  Publication holds, whatever the size of the book, the 64 MiB block being
  put in order, a few blocks of reads across the parts -- each part is
  written in row groups of its share of a block, so however finely the
  engine's width groups interleave the parts together hold a few blocks --
  and up to about two row groups per thread in Polars' writer. Measured, it
  added 0.3 GiB to a jagged 100,000-policy book in four width groups and
  0.9 GiB to 100,000 policies in one; 32 parts interleaved row by row, which
  held 4.3 GiB when a part's leftover rows were kept whole, add 1.0 GiB.

  The price is disk. A file is written in 64 MiB row groups, one batch or
  many, and against a file written as one row group that costs 3 per cent
  for 30,000 distinct level-4 policies. The model books here are tiled from
  a thousand model points, whose repeats a single row group compresses away:
  for those it is 8 per cent at 10,000 policies and 28 per cent at 30,000.

  Nothing partial is ever visible, as before: a refusal, an interrupt or a
  fault leaves no destination, no temporary file and no staging directory. A
  fault building a batch's columns is held until every batch has been
  checked, so a refusal in a later batch is still the run's answer; once the
  findings so far refuse, nothing more is built or staged.

- **The JAX engine's host work around a batch is about eleven times smaller.**
  At a million level-4 policies on a laptop CPU, the work before and between
  batches fell from 58 s to 5 s. The calculation itself took 23–27 s, and every
  node's values are bit-identical. The causes:
  - The projection timeline's calendar arithmetic ran one operation at a time
    as each batch settled (50.5 s, now 3.1 s). It is now compiled once per
    batch shape, and only the columns that read the boundaries lay them.
  - `str.to_date` parsed every row (preparation 6.5 s, now 1.8 s). It now
    parses each distinct string once.
  - Text columns were encoded value by value (validation 1.0 s, now 0.2 s).
    They are now encoded by their distinct strings, which get the same codes
    in the same order.
  - Grouping policies by the widths of their timelines before batching sorted
    the whole book's keys row by row and then walked it one policy at a time:
    25 s at ten million policies with two axes, now 0.8 s. It is now
    whole-array NumPy, which gives the same groups, in the same order, with
    the same rows.
  - The two operations answered on the host before a run, `str.to_date` and
    `to_text`, built a Python object per policy and walked them. They now
    answer each distinct value once and gather the answers back by position.
    Floats are told apart by their bits, so `-0.0` still writes as `-0.0`.
    Preparation at five million level-4 policies went from 11.7 s to 4.5 s,
    timed alternately with the old code on one laptop.
  - Settling a batch cut each of its columns out of the book on its own: a
    dispatch, a fresh copy of the batch's row positions onto the device and
    the bounds arithmetic on those positions, once per column. On a T4 that
    was 32 ms of a 53 ms settle per level-4 batch, and on a laptop CPU the
    cut took 14.4 ms. The batch's columns are now cut by one compiled gather
    (1.1 ms on the laptop), and the cells are the same, per-period columns
    and their horizons included.
  - Publishing a batch's columns walked every date one Python object at a
    time, and made three passes over every per-period cell: a fixed-width
    array, then a list, then a slice to each policy's own periods. A date is
    now its count of days until a strict cast names it a date, and a
    per-period column is one compaction handed to Polars as an Arrow list.
    For one level-4 batch of 20,000 policies, every node, building its 128
    columns took 2.19 s and now takes 0.38 s, and every column is identical.
    A whole level-4 every-node run of 100,000 policies went from 35.2 s to
    26.6 s, median of four runs alternated with the old code in fresh
    processes on the Intel laptop. Peak memory is unchanged.

### Documentation

- **The skills teach Phase 1 under a scenario plan before the refusal does.**
  A plan's batch is the book crossed with as many scenarios as `batch_size`
  packs into it, and a frame rebuilt there from collected values is refused by
  name wherever a batch holds more than one scenario -- so a plan that ran with
  two scenarios can be refused with fifty under `"auto"`. The scenarios skill,
  and model-building's `scenarios.md`, `running-at-scale.md` and
  `model-phases.md`, now show the routes the refusal names: a book-wide figure
  computed on the model points before the run, a side table through
  `af.join(...)` and per-row work by assignment closed with `materialize()`,
  and `batch_size=1` where the values must leave the frame. They also say that
  `with_scenarios` refuses nothing, so a figure taken across its crossed frame
  reads every scenario's copy.

- **The raw `edate` and `eomonth` kernels say what they do.** Their
  docstrings said "Non-integer values are truncated" and that the months
  could be a list column. Called directly, the kernel does truncate a
  fraction, parse whole-number text and move a flag; the operation
  `excel.edate`/`excel.eomonth` refuses all three and a per-period operand,
  and the docstrings now say both.

- **The front door says what is true.** `AGENTS.md`, the Copilot instructions
  generated from it, and `CONTRIBUTING.md` no longer say that a flat-rate
  test proves a timing convention: the two conventions differ even at flat
  rates, and what flat rates hide is a wrong conversion between them. AGENTS.md
  no longer calls a joined column a leaf, points a reviewer at `gspio verify`,
  `gspio diff --results`, `gspio graph` and `gspio sheet`, gives the one-line
  rollback `accumulate(..., reverse=True)`, and says a scenario plan runs the
  reconciled model unchanged. The agent plugin is 1.4.0.

- **Where a policy-anchored projection starts is said as the spec states it.**
  The `projection.set` docstring said the policy-anchored form "starts on the
  `valuation_date` as given", and `model-phases.md` said so with an example
  (2025-06-15 gives 2025-06-15). That holds only on a per-policy grid -- a
  term column, or `maximum_age` at the default `per_policy`. Every shared
  grid -- a whole-number `until_value`, `fixed_date`, `per_policy=False` --
  opens on the start month's last day (§11.1.1): valued 2025-06-15 the axis
  opens 2025-06-30, `fixed_date=2026-06-15` closes it 2026-06-30, and an
  attained age read off `period_dates()` is a year older from the first period
  for a birthday in between. Both now name the forms and the anchor.

- **`cumulative_survival(start_at=)` is documented as the opening value it is.**
  The docstring's "Partial Cohort" example ("95% survived underwriting - use
  start_at") and the parameter text ("0.95 for partial cohort") described a
  curve scaled by 0.95, while `start_at=0.95` sets only the opening boundary
  (§11.1.19): `[0.95, 0.999, 0.997002]`, an in-force that rises at t=1. The
  example now scales the curve, `0.95 * af.qx.projection.cumulative_survival()`
  (`[0.95, 0.94905, 0.947152]`), the parameter text says what `start_at` is,
  and `timing-and-dates.md` says the same.

- **`TimeConditionalShock` documents the condition it reads.** Its docstring
  said `when` "uses 't' column by default" -- `time_column=` was removed in
  1.0 -- and taught a mass lapse "at t=0" as `when={"t": {"eq": 0}}`, which
  over a lapse table keyed by policy year 1 to N selects nothing (and now is
  refused). It now says the condition reads the shocked table's own key
  columns, not projection time, gives the mass lapse as
  `when={"policy_year": {"eq": 1}}` on a table keyed from 1, and names the two
  refusals; the shock refusals' spelled-out example and the scenarios skill's
  refusal table say the same.

- **The audit-record reference says what an identity column shock does to a
  scenario's fingerprint.** A `column=` shock is recorded as an assignment
  whatever its factor (§13.2), so `MultiplicativeShock(1.0, column="sa")`
  gives its scenario a fingerprint other than BASE's while every number
  equals BASE's; an identity table shock leaves BASE's fingerprint. The
  model-review skill's `audit-record.md` now says so beside the other
  readings a reviewer gets wrong, so a moved scenario fingerprint is not read
  as a moved number.

- **The level-5 tutorial reads its expense parameters the way the skills
  teach.** Its base model pulled `expense_acq` and `expense_maint` out of
  `space_params.parquet` with `.item()` and wrote them into formulas as bare
  numbers, the pattern the model-building skill forbids: the record named no
  file or row for them, an edit to the file was not traced to it, and no
  scenario could shock them. It now reads each through a one-row `Table`
  (`space_expense_acq`, `space_expense_maint`) looked up at `space="GMXB"`, so
  the record names the table and its content. Every number is unchanged
  (bit-identical on the 1,000-policy book; the JAX engine agrees on all 125
  lines); the model's fingerprints move, and the JAX suite's committed
  `level-5.artifact.json` is re-exported.

- **The authoring skills teach 1.0's shapes and refusals.** The model-building,
  extending and quickstart skills teach multi-state occupancy as one
  `accumulate()` per state on the fixed-step axis, never the rollforward;
  `accumulate(reverse=True)`; a portable floored backward recursion; the kind,
  row-guard and table-read refusals, each with its move; and what
  `.polars_native()` costs. The extending skill leads with accessor bodies that
  record as core, and its Solvency II lapse stress, backward reserve and shock
  spellings now mean what they say. The quickstart names the command line's
  defaults: the policy id is positional, `--policy-id-column` repeats, and
  `calc-graph` samples one policy unless told otherwise.

- **The workbook-conversion and discovery skills prove a conversion can
  fail.** The conversion skill asks for negative controls -- one line mutated,
  the reconciliation run again -- before a conversion is called done. Its
  deliverables name the 1.0 audit tools (`gspio verify --assumptions`, `gspio
  sheet` or `calc-graph --xlsx`, one policy by default, and `gspio diff`) and
  give the hand route for comparing a model's graph with a workbook's, which
  1.0 does not ship. The discovery skill routes multi-state occupancy to
  per-state `accumulate()` rather than the rollforward, and no longer says the
  timing conventions agree at constant rates. The conversion reference warns
  that xl-marinade 0.4.0 drops edges to blank cells, and that Excel's `^` with
  a whole-number exponent is square-and-multiply, which parts from `**`
  (`pow`) in the last bits.

- **The governance and scenario skills teach the audit tools.** The
  model-review, model-reconciliation, results-analysis and model-scenarios
  skills teach `gspio verify` (and why exit 4 is not a pass), `gspio diff` with
  values beside `gspio compare`, the one-policy workbook `gspio sheet`, which
  identity answers which question (model-review's audit-record reference), the
  check that BASE's fingerprint is the reconciled model's, where a scenario
  run's record is written, what a `Period*` aggregator returns, and which
  quantile aggregators take `.over()`.

- **The results-analysis skill's `artifact_timeline.py` names a blank last
  row.** A per-period node beside the time axis's `n_periods + 1` boundaries,
  such as a rollforward's balances, has no value at the final boundary; the
  script now names every such node instead of leaving that row to read as one
  more period.

- **Four docstrings say what is true.** `cumulative_survival` and
  `deduct_nar` no longer claim the timing conventions agree at constant rates.
  `prospective_value` states its end-of-period formula and that it is a
  discounted reverse cumulative sum, not a stepped recursion. `projection.set`
  states that its synthetic grid starts at a month-end whatever the start day,
  and that `num_proj_months` counts boundaries.

- **The model-building skeleton values a term policy as the hand loop does.**
  Its claims ran over every point of the `month` axis, the maturity boundary
  included -- 13 claims for a 12-month term, +6.8% on the present value -- and
  it applied the table's annual mortality rate and a 3% annual discount rate
  once a month. The skeleton now stops claims at maturity, converts the rate
  to monthly, and discounts at the monthly equivalent. `AGENTS.md` references
  a column as `af["product"]` (`af.product` is a frame method and was
  refused), `model-phases.md` says where each grid starts (the date given on a
  per-policy grid, its month's last day on a shared one), and `assumptions.md` says the
  overflow and fill strategies act when a table is built, not when a key falls
  outside it.

- **`gspio verify`'s documentation shows the join line and the helper loaded by
  path.** The model-review skill's `audit-record.md` sample is now the output
  of a model that reads a table by path, joins a file and loads a helper with
  `importlib`, and says what the join's `assumptions` line holds and why the
  `modules` line could not be checked; `gspio verify --help`, its command
  docstring and `verify_artifact` say the same.

- **The specification states what wave five's rulings changed, and the
  model-building skill imports a helper by name.** `spec/graph-artifact/v0-preview.md`
  now states the `maximum_age` horizon per policy and the refusal of a read across
  rows wherever a run cuts the book or carries a scenario axis (sections 11.1.1,
  11.1.37, 11.2 and 13.2), the name a file outside the model's root is written under
  (7 and 7.3), Excel's YEARFRAC (11.1.34), the `f64` answer of a per-policy flag in
  arithmetic (11.1.25), list-shaped date comparisons (11.1.26), that a consumer of
  the `audit` profile may recompute a leaf's fingerprint (13), that a helper loaded
  by path is a modules check that could not be made (7 and 13), and that a model
  reading `scenario_id` is composed over a one-scenario axis (13.2). The three
  hand-built example documents are written again by a generator, so every digest in
  them that follows from the file is taken rather than typed, and the conformance
  kit gains `vectors/list-dates.json`. The model-building skill teaches a plain
  `import` for a model's own helper modules, never a load by path.

- **The specification states the edges wave five's bug fixes moved, and the
  supervisory annex's example carries its own digests.** `spec/graph-artifact/v0-preview.md`
  now states that a model whose only step is a selection is a document, that a
  selection step may read a rollforward's state and is then refused from the
  `executable` profile, and that a filter's condition answers once per policy
  (7.6); that a consumer reads a book's narrow integers as `i64` (10); that an
  answer column of whole numbers is read as `f64` (11.1.24); that a power under
  a written exponent outside `[0, 2^32-1]` answers `f64` and a column exponent
  past that range is refused naming `to_float()` (11.1.25); and that
  `n_policies` counts the policies the model valued (13.2). The annex example's
  curve now carries the digest its values hash to, `sha256:0483acfa…`, and is
  named `curve:0483acfa`, and its mortality table is inlined in the form the
  specification states, so its digest can be checked. The conformance kit gains
  `vectors/text-order.json`, five cases of an ordering over text.

- **The specification states the shared grid, the scenario-partitioned read and
  the maximum age's cadence as they now run, and section 17's state-graph example
  carries its own digests.** `spec/graph-artifact/v0-preview.md` now says that a
  `maximum_age` horizon needs a month-aligned cadence and that a shared grid
  sized from the rows is laid only where the frame is the whole book (11.1.1),
  and that a read partitioned exactly by the scenario is admitted on a scenario
  axis whose policies are whole while a shared grid is refused with every other
  read across rows (13.2, pointed at from 11.2). The state-graph example's two
  inline tables are written in the form section 15 states, under the content
  hashes their values take (`sha256:d39ce174…` and `sha256:bd877d7a…`), and the
  `table_fingerprint` each intensity carries follows them.

- **The specification states how a book integer wider than `i64` is read, and
  admits a window over the scenario and another key.** Section 10 says that a
  `UInt64`, `Int128` or `UInt128` column whose values fit is read as `i64` by the
  producer and by a consumer, that one holding a value past that range keeps
  its width for `to_text` and `to_integer` while arithmetic on it is refused by
  name, and how a book handed over as a plan and a batched run apply the rule;
  section 11.1.25 points at it. Section 13.2 admits a read inside a window
  whose partition includes the scenario, with further keys, on a scenario axis
  whose policies are whole (pointed at from 11.2). The five wide-integer
  conversion vectors are unchanged.

### Known limits

- **Two failures do not yet name the failing column or the policy.** A list
  of the wrong length inside Polars' own arithmetic, under the streaming
  engine `collect()` runs by default, arrives as Polars' `ShapeError` without
  the *Failing column* and *Policy* blocks the in-memory engine's report
  carries; collect again with `af.collect(engine="in-memory")` to get them. A
  rollforward input of the wrong length, refused through a frame, names
  neither under either engine; its first line names the input column.

- **On a calendar grid, `t_years()` is a running sum of year fractions,** so
  a monthly grid differs from `k/12` in the last bits: at 219 of 241
  boundaries over twenty years, by up to 25 units in the last place. Expect
  that against a workbook's `A/12`. Where there is no calendar, the
  fixed-step axis gives `k/12` exactly.

- **A band written in raw Polars is identified by Polars' display text.**
  `pl.col("x").is_in([...])` or `.cut([...])` is recorded as engine text, so
  a member or a break that changes in its eighth decimal can leave the
  fingerprint where it was. The declared operations on the column,
  `af.x.is_in([...])`, `cut` and `replace`, record their values and move it;
  `af.graph.tiers()` names any band still written in raw Polars.

- **Results files are compared by value, not by hash.** Runs on one machine
  write the same bytes, but a results file's footer records the platform and
  the library versions that wrote it, so files from two machines or two
  builds differ in bytes: compare them with `gspio compare` or `gspio diff
  --results`. `producer.versions.imports` names the installed distributions
  a model imports; the standard library and a module found only on
  `PYTHONPATH` are not listed.

- **A table built from a frame in code cannot be held against a file that
  differs from it.** `gspio verify --assumptions` answers `indeterminate`,
  exit 4, because nothing records that the frame was the file as it stands;
  a table whose recipe reshaped what it read is the same. Hand `Table` the
  file path for a difference to decide.

- **Three questions are answered one step away.** `formulas_fingerprint` has
  no `af.graph` method: read it off an exported audit file, or in Python as
  `"sha256:" + formulas_fingerprint(fold(af)).hex()`, both from
  `gaspatchio.frame.graph`. `gspio calc-graph` does not also write
  every node's values from the same run; `gspio run-model ... --every-node
  --results FILE` does, as a second run. And `Quantile(...).over(...)` and
  `PeriodQuantile(...).over(...)` are refused: per scenario, `Median`,
  `CTE`, `QuantileRank`, `PeriodMedian` and `PeriodCTE` run under `.over()`.

- **No declared operation drops a column's final period boundary.** A
  column derived from the projection axis carries one value per boundary,
  one more than a rollforward's periods; the rollforward's refusal names the
  per-period builds that run, and the escape,
  `.polars_native().list.head(n)`, records the line as engine text that
  runs only on Polars.

- **That Excel reads a sheet's cells back to the record's doubles is still
  to be confirmed by hand.** `gspio sheet` writes each number with up to 17
  significant digits, the shortest that reads back to the same double, and
  no cell holds a formula; Excel for Windows and for macOS have not yet been
  checked reading them.

- **On the JAX engine's CPU backend, XLA flushes subnormal numbers to zero**
  (`5e-324 / 1.0` is `0.0`). A
  value below the least normal double (about 2.2e-308) is outside the agreement rule: a
  comparison, `sign` and `cbrt` of one can differ from the producer's
  outright -- `x == 5e-324` answers 1 where `x` is 0.0, and `sign` of 1e-310
  answers 0 -- because the engine reads it as zero. No actuarial quantity
  lives there, and the engine leaves the backend's mode as XLA sets it on
  the CPU and on a GPU.

- **A maths call can still move a threshold set at its own value on the JAX
  engine.** `exp`, `cbrt`, `norm_cdf` and the rest of §11.1.12 are held to
  that section's tolerance, and one engine's answer may sit one place from
  the other's, and a comparison against the call's own value can then answer
  1 on one engine and 0 on the other (measured for `norm_cdf` and `cbrt`).
  Every product and division is the producer's to the bit; this residue is
  the one the engines keep.

- **The JAX engine refuses a whole-number total whose running total passes
  `i64` on the way, though the total fits.** `[2**63 - 1, 1, -1].list.sum()`
  is `2**63 - 1` on both Polars engines and in the reference reader; the
  JAX engine checks each partial sum and refuses the run by name
  (`i64.range`). A refusal, never a different value.

- **A loop of writes straight into the query plan slows as the plan grows.**
  Each `af._df = ...` is read whole so that `holes()` can name the columns it
  overwrote, and Polars converts the whole plan whenever it is asked about
  any part of it: about 12 ms a write on the level-4 tutorial model, so 200
  writes in a loop take about 4 s. Write the columns in one `with_columns`,
  which is one write, or use the frame's own assignment, which reads nothing.
  An ordinary model makes no such reads.

### Internal

- **The content grammar's Python reference loses a branch no column could
  reach.** `_as_whole_number` converted a timestamp to whole microseconds, but
  `_value_block` sends every timestamp to `_instant_block` first, which keeps
  the nanoseconds past each microsecond; the branch, and `datetime` in the set
  of names that travel as one whole number, are gone. No byte moves.

- **CI runs green on Linux and on Python 3.12, where the local gates ran on
  macOS and Python 3.13.** The lower-tail test of `norm_cdf` held the textbook
  formula to macOS's `erf`, which answers -1 at -8.36 / √2 where glibc's
  answers the nearer double; it now holds the formula to the contract on both,
  and the kernel, which is the `libm` crate's on every platform, answers the
  same bits on each. The JAX suite's fused-remainder reference used
  `math.fma`, new in Python 3.13; it now works the product exactly in
  rationals and is checked bit for bit against `math.fma` where there is one.
  The engine's table of dtypes is typed by what XLA's calls accept, so it
  type-checks under JAX 0.12's stubs as under 0.11's. A scenario page's test
  read the policy switcher before the page had drawn it and failed on WebKit
  under load; it now waits for the switcher. The reader's bundle ceiling is
  CI's figure, 197,220. The engine's and the reader's lockfiles move the
  packages the security scan flagged: certifi to 2026.10.19, the OpenTelemetry
  family to 1.45.1 with logfire 5.2.0, vitest to 5.0.3 and vite to 8.3.3.

- **The core's lockfiles move off the advisories the weekly security scan
  reports, each package to the least version that clears it.** In
  `bindings/python/uv.lock`, what a gaspatchio install reaches: anyio 4.14.2,
  certifi 2026.10.19, urllib3 2.8.0, and the OpenTelemetry family to 1.45.1
  with logfire 5.2.0, as the engine's lock already has. In the `evals` group
  only: pydantic-ai 2.53.0 with the floors it sets (anthropic 1.9.0, openai
  3.19.0, google-genai 2.25.0), mcp 1.30.0, fastmcp-slim 3.4.10, authlib
  1.9.1, PyJWT 2.15.0, httpx2 2.12.0 and dnspython 2.9.0. In `Cargo.lock`:
  tokio 1.51.6, rustls 0.23.46, rustls-webpki 0.103.16, quinn-proto 0.11.18
  and xxhash-rust 0.8.16, with the least of what tokio and quinn-proto then
  require, and the third-party notices follow. Polars does not move. Three
  crates keep advisories that no lockfile change can clear: zstd 0.13.3 and
  zstd-safe 7.2.4, fixed only in zstd 0.14, which no release of polars
  accepts, and block-buffer 0.10.4, fixed only under sha2 0.11, which polars
  does not take. zstd-sys 2.0.15 keeps one that affects WebAssembly builds
  only, which gaspatchio does not make.

- **Ruff reports 80 findings over the package, from 1,071.** Every mechanical
  finding is fixed, and every finding that needed a decision is fixed or kept
  with an inline `noqa` naming the fact that makes the rule not apply. What
  remains is public-API shape and complexity, which only breaking changes or
  refactors remove.

- **mypy, in strict mode, and pyright pass with no errors over the
  package,** where this release's work began with 104 of each, and with no
  ignore added. The stubs re-export the classes the package names, and
  stubtest reads the graph API and the error modules again.

- **`tests/test_stub_sync.py` asserts on the module count stubtest's
  closing summary line reports,** so a run that aborts before comparing
  anything fails instead of passing on the absence of `error:` lines alone;
  it also fails on any `unused allowlist entry` note from now on. The test
  and CI (`.github/workflows/CI.yml`) now run the exact same stubtest
  command, so an allowlist that passes locally passes there too —
  `stubtest-allowlist.txt`'s 42 entries that no longer matched anything
  under that shared command are pruned, the missing-stub ledger CI depends
  on stands, and the allowlist is current.

- **The docstring test plugin keeps a docstring's examples when its field
  parser rejects the docstring,** where they silently left the test run, and
  reports a lint failure that carries no issue rather than raising while it
  writes the report. The scenario audit reader refuses JSON that is not an
  audit, naming the file.

- **Comments, docstrings and test descriptions give reasons, not decision
  numbers.** They cited internal decision numbers a reader could not look
  up. Each now says the reason, or the section of the specification that
  states the rule, and a test reads the shipped sources, Python, TypeScript
  and Rust, and fails on any citation that comes back.

- **The scenario run record's module says what it is, and its version note
  says what 2.1 removed.** Its docstring named an issue number, and the
  comment over `AUDIT_SCHEMA_VERSION` called 2.1 additive over 2.0: it
  removes `run_metadata.library_version`, as section 13.2 of the
  specification states.

- **No file that ships names a private issue.** The aggregate-at-scale and
  period-aggregators tutorials, the variable-annuity stress script, the
  docstring checker, the accumulate lowering and five scenario modules cited
  issues in a tracker no reader can open, and a stress report printed an
  internal branch name. Each now says what it meant in words, keeping a
  public `gh#` or `PR #` reference where there was one, and a test reads
  every tracked file under the package, `skills`, `spec`, `engines/jax/src`
  and `viewer/python`, in any case, so none comes back.

- **Sixteen definitions nothing in the package called are deleted**, out of
  the 287 a static finder lists over the package. Four sat at importable
  paths and are named under Removed too. `assumptions/_analysis.py`'s
  `_analyse_shape` was 127 lines under its own banner asking for its removal,
  superseded by `analyze_table()`. `cli.validate_file_path` was never a Typer
  callback. `errors.frame_utils.find_user_code_frame` is what
  `find_calling_user_code()` beside it already does.
  `examples.docstrings.style.ImplicitOutputRule` returned an empty list and was
  absent from the checker's own list of rules. `trace_generator._format_number`
  was a copy of the `_format_scalar` branch that is called. A nested
  `prepare_date_expr` in the yearfrac lowering was defined and stepped over —
  the four lines after it pass the expressions through unchanged, which is what
  the Rust side wants. `_fill` on the period extremum aggregators was a
  `NotImplementedError` hook and two overrides that nothing called; the same
  identity values are literals in `_combine`, where they are read. With them go
  `errors.constants.MAX_SUGGESTIONS`, `scenarios._config.MODIFIER_KEYS` and
  `RESERVED_KEYS`, two parser attributes assigned and never read, and two loop
  names bound and never read.

  The other 271 candidates stay, each with the one line of evidence that
  reaches it: a decorator, a quoted name, the model machinery that reads a
  class body by name, or a model, a stub, an `__all__`, the documentation, the
  skills, the tutorials, the jobs or the format specification. Nothing in that
  second group was touched, so no import a model can write changes and no test
  was removed.

- **The lookup's "the cause is how the key is stored" refusal is gone,** with
  the re-run that decided it (the binding's `encoding_that_caused_the_miss`)
  and `key_encoding_refusal` in the core. It fired only when a categorical or
  Enum key missed a table that held its label, which hash storage did by
  hashing the key's dictionary index; both storages now place such a key by
  its label, so no lookup reaches it. A key the table does not hold is still
  refused as a missing key.

- **A calculation-graph node with no formula recorded no longer logs
  `Failed to generate trace for <node>` at WARNING.** It is a node the export
  cannot trace, not a failure, and it now says so at TRACE alongside the two
  neighbouring cases (no sample value, a read of a replaced value) that were
  already reported that way. If you grep a run's logs at WARNING for that
  line, it will no longer be there.

- **The core no longer declares `dashmap` or `tracing-subscriber`,** which no
  code used, so the nine crates only they brought in leave the extension's
  build and its notices. A test fails on any dependency the lockfile holds
  for a declaration no source uses.

- **The viewer's build tools take `source-map-js` 1.2.2,** for the
  denial-of-service advisory GHSA-68fv-2mgg-jv7q in 1.2.1. It is a
  development dependency only: the bundle the distribution ships is
  byte-for-byte the same.

- **Every tool a workflow installs is pinned,** to an exact version and,
  where its distribution allows, a digest: one uv in every workflow, the
  release's maturin and twine, the licence check's cargo-license, reuse and
  pip-licenses, and the build backend of the engine and viewer
  distributions. A test fails on any install that floats, and on a digest
  used on a platform it was not taken for.

- **The tutorial CLI tests run `gspio` through the interpreter running them,**
  as `python -m gaspatchio.cli`, where they shelled `uv run gspio` -- which
  resolves, and so builds, the project in whatever tree the tests start in,
  so the test measured a fresh build of the Rust core rather than the package
  under test. A guard reads every module under the repository's `tests/` and
  fails on a subprocess call that starts `uv`, `uvx`, `maturin` or `cargo`.

- **The performance probe's workload directory is named only by
  `GASPATCHIO_PROBE_WORKLOAD_DIR`, and there is no default.** The workload is a
  machine-local model that is not part of this repository, so a default
  resolved to a path only one machine had — everywhere else it read as
  "the workload is missing" rather than "you never said where it is", and
  a test asserting that path passed green on machines the directory had
  never existed on. Unset now means the model path is `None`, and every
  entry point says which of the two things is wrong: nobody named a
  directory (the message names the variable and the two files it must
  hold), or the directory named is missing one of them (the message names
  that directory and the file). Both CLIs exit non-zero with the sentence
  rather than a traceback.

## [0.9.0] — One name, and the surfaces meet you halfway

The release's headline is the smallest possible diff with the largest reach:
the import is now the package name. Around it, the API surfaces got more
liberal about the shapes they accept — a scalar growth factor, a
survival-shaped column — while keeping the refusals sharp where meaning is
genuinely ambiguous, and a season of truth-telling landed: the docs, the
tutorials, the design spec, and the validation harness all now describe the
framework that actually ships.

### Changed

- **The import name is now `gaspatchio`**, matching the package name on PyPI
  and in the documentation — `from gaspatchio import ActuarialFrame`. The old
  `gaspatchio_core` import keeps working until 1.0 as a deprecated alias that
  resolves to the same module objects at every depth, and warns once per
  process — including under `gspio run-model`. Static type checkers resolve
  only the new name, so rename imports in typed code. The `gspio` CLI is
  unchanged. (#129)

### Added

- **`accumulate()` broadcasts a scalar `multiply`/`add`** to the sibling
  list's per-policy timeline — `accumulate(multiply=1.02)`, the natural
  spelling for a level growth factor, now works, jagged timelines included.
  `initial=` always broadcast; the asymmetry is gone. Two scalars still
  refuse (no timeline to infer), and the refusal now names the growth-free
  closed form (`initial + flow.cum_sum()`). Closes #128. (#155)
- **`cumulative_survival()` accepts survival-shaped input** — pass the
  survival probabilities you already have instead of reshaping them into
  decrements first. (#143)
- **The workbook-conversion discipline is a skill** —
  `gaspatchio-workbook-conversion` walks an agent through converting an
  Excel model end to end. (#114)
- `gspio docs`/`gspio knowledge` results get deduplication and snippet
  windows by default (#138), and a failed `--answer` degrades to search
  results instead of a dead end (#142).
- Calc-graph nodes carry shape and kind from the shape source of truth
  (#134); `ActuarialFrame.join` passes `maintain_order` through (#131).

### Fixed

- **The docs tell the truth batch**: the runner's `point_id` contract, the
  Level-2 tutorial data, four skill examples that crashed verbatim, and the
  kwargs wire format documented as it actually is. (#148)
- **Lookups from a superseded `Table` object refuse loudly** instead of
  silently reading stale rates. (#137)
- The runner registers the model module in `sys.modules` before exec —
  dataclasses and pickling inside models work again. (#135)
- Frame-level projection methods return wrapped expressions, keeping
  accessor chaining intact. (#133)
- **Tutorial repairs**: the Level-4 reconcile builds its time index
  per-policy (jagged-safe), the Level-5 model wires its shipped ultimate
  mortality rates into the select/ultimate structure, and the perf stress
  demonstrates the table-coverage rule instead of violating it. (#152)
- The docstring-example harness can no longer leak subprocesses (a
  timed-out ruff child is killed and reaped), parses diagnostics
  stdout-first, and classifies syntax errors by message rather than
  code-literal roulette. (#153)

### Internal

- Ruff 0.11.12 → 0.16.3 with the rule-set pinned as part of the test
  contract (#144, #146), then the lint burn-down: config truth (#150) and
  1,728 safe autofixes driven to the fix/format fixpoint (#151).
- The rollforward v2 design spec now records the shipped Phase-1/2
  contracts — as-quoted rates, `"state@point"` reads, the `Apply` refusal —
  with the deferred end-states routed to the arc backlog. (#154)
- Benchmark model points are generated instead of committed as 22.8 MB of
  LFS (#140), with LFS fetches cached and scoped in CI (#139); transitive
  `h2` bumped for RUSTSEC-2026-0258 (#149).

## [0.8.2] — The recursion tells the whole truth

Where 0.8.1 made the surface honest about what didn't exist, 0.8.2 ships
the two things the clean-room UL conversions actually asked the recursion
for: the flows it applied, and the spreadsheet's rounding placement. The
rollforward now reports what it did — per-op, signed, period by period —
instead of leaving flows to be reconstructed from state differences. Around
it, the window lands where the docs promise, the type stubs stop hiding the
API from editors, and two conversion paths accept composed expressions they
previously refused.

### Added

- **`track_increments=True` emits real per-op increments.** Every labelled
  op contributes a signed per-period delta — what it actually applied to
  its target: negative for charges, positive for credits, and zero after a
  stop or lapse. Zero-after-lapse is the honest representation:
  reconstructing flows from state differences conflates "no charge" with
  "nothing left to charge against", which was silently wrong for 55 of 111
  projection years in the clean-room UL conversion. Read them via
  `compiled.increment_for(label)` or the builder's `increment()` handle; an
  unknown label refuses immediately on every path — including the
  deprecated collector facade — naming the labels that exist. Closes the
  #69 arc: accepted-but-inert, then a loud refusal in 0.8.1, now the real
  thing. (#69)
- **`round_charge=` on `charge`, `grow`, and `deduct_nar` — round the
  flow, not the state.** Spreadsheets place `ROUND()` on the individual
  charge where it is computed; the rollforward's `Round` op rounds the
  running balance. Those are different numbers that compound differently,
  and only one placement was expressible. Both now are, each requested by
  name; under the end-of-period NAR convention the circular charge is
  solved first and rounded once, and a non-integer precision refuses at
  construction rather than deep in the kernel. (#92)

### Fixed

- **`.between()` scope sticks to its handle, not the builder.** Ops
  chained from a plain `b["state"]` handle default to `eop` as the docs
  promise; a mid-chain `.between()` window no longer silently captures
  every later step. (#101)
- **The shipped stubs tell the truth about the rollforward API.**
  `compile_rollforward`, `Schedule`, `Curve`, and `MortalityTable` import
  cleanly, `af.projection` types as the accessor it is, and `rollforward()`
  shows its real signature — so Pylance stops red-squiggling a correct
  model. The stubtest CI gate now runs un-blinded, with deliberate
  omissions recorded in a reasoned allowlist instead of a flag that hid
  everything. (#104)
- **`finance.to_monthly` converts composed list expressions.** The list
  path gated on proxy *type* rather than *shape*, so a composed expression
  that was list-shaped fell through to the scalar path and failed at
  collect. Shape decides now. (#86)
- **`scalar ** lookup(list key)` works.** Pow dispatch resolves the shape
  of bare polars expressions instead of only proxy-wrapped ones, so the
  natural spelling of a compound-growth formula against a looked-up rate
  no longer raises. (#89)
- **The skills stop over-promising.** The conversion reference no longer
  claims `formula_pattern` reports the dominant pattern — it teaches the
  distribution query that actually settles a merged binding (#103) — and
  the model-building skill draws the proxy duck-typing boundary honestly:
  `clip` and `when/then` are the idioms, the polars `*_horizontal` free
  functions are outside it (#102).

## [0.8.1] — The surface tells the truth

Four small fixes from the second, clean-room field test of the Type A UL
conversion — all in the retrieval-and-refusal surface rather than the
numerics. The pattern the field test exposed: content and features the
framework already had were unreachable or over-promised, so an agent (or
an actuary) working from the surface alone concluded they didn't exist.
No numeric behaviour changes.

### Fixed

- **`gspio tutorial` reaches the shipped rollforward patterns.** The
  worked rollforward examples ship in the wheel, but `tutorial list`
  never showed them and `init` refused them — so the state-machine
  recursion, the framework's flagship escalation, had no reachable worked
  example. `list` now shows the collection, `init rollforward-patterns`
  copies it, and `verify` runs its self-asserting scripts. (#94)
- **Capture-slot errors name the real rule.** Reading a declared point
  that no Op targets raised "declare the point" — a no-op when the point
  is already declared. The error now states which precondition failed,
  lists what is captured for the state, and names the next move,
  including the opening-balance idiom (prior period's `eop`). (#93)
- **`track_increments=True` refuses loudly at build time.** The flag was
  accepted, validated, and explained while the kernel emitted no
  increment fields, so the failure arrived at `collect()` phrased as a
  wrong field name. The builder now raises `NotImplementedError` at the
  call that asks for it, naming the gap and the workaround — and the
  workaround's known trap. Increment emission itself remains open. (#69)
- **The skill routing table names skills that exist.** The always-loaded
  agent knowledge routed to `model-building` and friends — names that
  resolve nowhere; the canonical names are `gaspatchio-model-building`
  et al., plugin-prefixed in Claude Code. The table now uses the real
  names and gains the missing `gaspatchio-extending` row. (#99)

## [0.8.0] — Rounding is requested by name, and lookups commute

The v0.6.0 field-test issue batch (#66–#68, #70–#73), plus the rollforward
hardening that preceded it. Two threads: conventions are named, not
guessed — Excel's half-away-from-zero and polars' banker's rounding are
now each requested explicitly, and `deduct_nar` states its timing — and
formulas work as written in either operand order. Nothing that worked
before breaks; the only removals are wrappers that could never do
anything but panic.

### Added

- **`.excel.round(num_digits)` — working per-period column rounding,
  named by its convention.** There was no working way to round a list
  column: polars' `.round()` raises on lists, and `plugins.round` /
  `round_to_int` / `floor` called Rust symbols that were never
  implemented, dying with a dlsym panic that even `except Exception`
  cannot catch. The new accessor applies Excel's half-away-from-zero
  (7558.485 → 7558.49), works element-wise on per-period list columns and
  scalars alike, and supports Excel's negative `num_digits`. It is the
  column-side counterpart of the rollforward's `Round` op — deliberately
  the same rule — while polars' native `.round()` keeps banker's
  rounding: two conventions, each requested by name. The dead wrappers
  are removed rather than implemented. (#68, #70)
- **Rollforward `Round` op**, for products whose spec rounds the running
  balance inside the recursion — same half-away-from-zero rule as
  `.excel.round`, by design. (#74)
- **Corridor test on `deduct_nar`, and a negative NAR refuses to run.**
  Once a well-funded policy's account value outgrows its death benefit,
  `death_benefit − account_value` goes negative, the COI becomes a credit,
  and the account runs away — 166× too large on a constructed UL policy,
  silently, after 49 years of exact agreement. `corridor_factor=` adds
  the regulatory corridor test real UL products carry; independently, a
  negative NAR now raises instead of compounding. (#78)

### Fixed

- **`lookup()` cooperates with proxies in either operand order.**
  `af.col * lookup(...)` worked while `lookup(...) * af.col` raised,
  because polars' `Expr` operators raise instead of returning
  `NotImplemented` (filed upstream as pola-rs/polars#28748), so Python
  never offers the proxy its reflected method. Lookup results — and the
  other bare-expression surfaces: rollforward `expr_for` /
  `increment_for` and the `Schedule.*_expr` family — now return an
  internal `pl.Expr` subclass that hands mixed operations to the proxy
  layer, which owns the operator semantics polars lacks (`**` on list
  columns included). The guarantee covers operators; a method chain
  (`.clip()`, …) returns a plain polars expression — assign to a column
  first. Held in place by a 40-cell operator × shape × operand-order
  test matrix. (#67)
- **Only declared columns become dimension keys.** An undeclared source
  column riding along in a table's DataFrame was silently promoted into
  the lookup key, so the composition on screen was not the composition
  that ran. Construction and `extend()` now trim to the declared
  dimensions. (#66)
- **Scalar rollforward inputs broadcast across periods, and `deduct_nar`
  names its timing convention.** A level death benefit is one value per
  policy; it no longer has to be materialised as n_periods identical
  copies, and List inputs are untouched (bit-identical plans). (#65)
- **The rollforward length-mismatch error points at what actually
  fails**, distinguishing point-indexed from period-indexed columns
  instead of advising the wrong fix. (#73)
- **The assumptions type stubs no longer describe an API that does not
  exist.** (#72)
- **The Claude plugin installs `skills/`, not the repository.** A
  marketplace `source: "./"` shipped the whole tree — 47 MB from a clean
  checkout, 25 GB from one carrying build output — to deliver seven
  skill directories. (#75)

### Documentation

- Spreadsheet-to-gaspatchio translation reference for the discovery
  skill: what a workbook's structure implies about the model you should
  write, with every row naming the failure that is silent. (#76)
- Model-building skill gotcha #4 corrected: `af.month` exists —
  `projection.set()` materialises it. (#71)
- README gained a Performance section linking the live per-commit
  benchmark dashboard. (#81)
- CONTRIBUTING is canonical for the GitHub workflow (branches vs forks,
  signing, merge policy); code of conduct and PR template added. (#87)

### Security

- cryptography 49.0.0 → 50.0.0; the new pymdown-extensions ReDoS
  advisory (GHSA-gm37-52c6-37mw) is filtered with reachability reasoning
  — marimo caps `pymdown-extensions<11`, and the vulnerable extensions
  are absent from gaspatchio's runtime closure. (#88)
- GitHub Actions dependency bumps across the workflow set. (#20)

## [0.7.1] — Addition commutes, and panics name their column

Three fixes, all traced back to the v0.6.0 field test, none breaking — a
drop-in upgrade. The thread connecting them: a formula should work as
written, and when it can't, the refusal should name the thing that's
wrong. One upstream polars quirk made `+` order-dependent; one pyo3
escape hatch let plan-lowering panics bypass the named-column error
contract; one scenario-stacking overwrite turned a modelling mistake
into a far-away duplicate-key error. (#52, #53, #54)

### Fixed

- **Schema failures inside `when()` branches are attributed errors, not raw
  panics.** A schema mismatch in a `when().then()` branch fails during plan
  lowering, where polars panics instead of raising a typed error — and
  pyo3's `PanicException` bypassed both `except Exception` and the
  collect-time column attribution (#39), reaching the model author as a
  bare Rust panic naming nothing. The `collect()`/`profile()` boundary now
  converts that panic into a catchable `SchemaError` carrying the standard
  attribution block (failing column + defining expression), chained to the
  original panic. Panics of any other origin — and real interrupts — pass
  through untouched. (#54)
- **Scalar/list broadcast is order-independent for `+` and `-`.** polars
  broadcasts a scalar into list arithmetic only when the scalar side is a
  *leaf* (bare column or literal) — a compound scalar expression
  (`af.a * af.b`) against a list operand failed supertype derivation, and
  only for `+`/`-`, so the natural expense formula
  `AnnPrem * ExpsPerPrem + (SA * ExpsPerSA + ExpsPol) * InflFactor` lived
  or died on operand order. The proxy layer now pre-broadcasts the
  compound scalar side with `repeat_by` to the list side's per-row lengths
  (jagged-safe) and the op proceeds as native list-list arithmetic.
  Engaged only for the shapes that natively fail — bare columns, literals,
  `*`, and `/` keep their existing plans. Three instances found in the
  wild during the v0.6.0 field test, all previously "fixed" by flipping
  operands. (#53)
- **A shocks-dict `ScenarioRun` refuses a base table that already carries
  `scenario_id`.** Stacking stamps the batch's scenario key over every
  `base_tables` entry, so a table already keyed by a scenario axis had its
  original scenarios silently collapsed onto one key — the cause of the
  shipped scenarios docs example printing every scenario at the UP rate,
  and (since strict table builds) of a `Duplicate key combination` error
  far from the cause. The stacking boundary now raises upfront, naming the
  table, its existing `scenario_id` dimension, and both remedies: keep the
  table scenario-invariant and express differences as shocks, or pass the
  scenario-keyed table through the id-list/drivers shapes, where
  `base_tables` reach the model untouched. (#52)

## [0.7.0] — Book shapes are declared, and conditionals speak strings

A short, sharp release from the post-v0.6.0 audit batch (Linear GSP-111)
and one long-standing modelling gap (GSP-110). The audits followed the
template that keeps paying off — sweep the parameter that changes the
iteration shape, assert a strong invariant — and one of them caught a
shipped chunk-stability bug in the rollforward kernel. The one behaviour
change is breaking and carries an **Action** line below.

### Breaking

- **Rollforward book shape is declared by the schedule, not inferred from
  the batch.** The uniform-schedule length guard fired only when *every*
  policy in the batch shared one wrong list length — but the batch is a
  streaming-engine choice, so identical books passed or failed depending on
  chunk width, and a genuinely jagged book could error mid-stream whenever
  a chunk happened to hold same-length policies. The guard is now per-row
  and driven by declared intent: a `from_calendar_grid` / `from_inception`
  schedule requires every policy's input lists to have exactly `n_periods`
  elements (this also catches mixed stale books the old heuristic waved
  through); jagged horizons use a per-policy grid
  (`af.projection.set(..., per_policy=True)` or
  `Schedule.from_per_policy_grid`), whose per-row lengths are authoritative.

  **Action:** a rollforward that fed variable-length input lists to a
  uniform calendar-grid schedule now raises — declare the horizons with a
  per-policy grid instead. Found by the GSP-112 chunk-invariance audit.

### Added

- **List-broadcast `when()` supports string outputs.**
  `when(af.code_list == 0).then("PP23").otherwise("PP24")` now produces a
  `List(String)` column — previously the list path was f64-only and string
  branches died with a misleading `then_val at row 0 is null`, forcing raw
  Polars `list.eval` workarounds or numeric-code re-encodings into model
  code. String columns, string lists, and categoricals all work as branch
  values; chained `when()`s fold through; a string branch against a numeric
  branch refuses loudly (one column, one dtype). (GSP-110)
- **`broadcast_to_periods()`** on the projection accessor broadcasts a
  per-policy scalar of any dtype — strings, booleans, categoricals — to a
  per-period list aligned with the frame's `month` axis (or any list column
  via `like=`). Replaces the numbers-only `af.scalar + af.list * 0.0` idiom
  and hand-rolled `repeat_by` helpers for string-keyed lookups. (GSP-110)

## [0.6.0] — Silent wrong numbers become loud errors

Nineteen issues from a field report (an actuary porting a production model)
and two internal audits, in one release. Nearly every defect shared one
shape: the framework silently doing something plausible — returning NaN for
a missed lookup, keeping a stale column, clamping a curve into nonsense —
instead of loudly doing the right thing. Five behaviour changes are
breaking; each carries an **Action** line below. (#21–#31, #33, #35–#40,
#42)

### Breaking

- **Lookup misses raise instead of silently returning NaN.** A missing key
  returned bare NaN — invisible to `is_null()`/`fill_null()` — and flowed
  into reserves unnoticed. Misses now error at `collect()`, naming the
  table, the miss count, and the first missing key tuples. Opt-outs:
  `Table(..., on_missing="nan")` restores the old behaviour,
  `on_missing=0.0` fills with a constant, and a per-lookup override covers
  a single call site. Note that `when(guard).then(...).otherwise(lookup(...))`
  evaluates *both* branches, so a guarded lookup still runs on the excluded
  rows — those expected misses must be declared with `on_missing="nan"` on
  the lookup.

  **Action:** any lookup that relies on misses coming back as NaN must now
  declare it. (#24)

- **`prospective_value` end-of-period values under varying rates change.**
  The ordinary-annuity path discounted the whole tail by position *t*'s
  factor — an identity that only holds for constant rates. Each cashflow now
  carries its own compounded factor:
  `pv(t) = Σ_{s≥t} CF[s] · Π_{u=t..s} v[u]`. Constant-rate results are
  unchanged; per-period-rate end-of-period results change. NaN cashflows
  also propagate instead of being silently zeroed — beyond-term periods
  must be zeroed explicitly.

  **Action:** re-run any reconciliation that discounts with a per-period
  rate vector. (#28)

- **A bare string lookup key is the value, not a column name** — VLOOKUP
  semantics. `lookup(product="annuity", age=af.age)` now matches rows whose
  product dimension equals `"annuity"`; previously the string was read as a
  column reference and raised a misleading `ColumnNotFoundError` for a
  column that was never meant to exist. Columns are referenced as
  `af.product`, `af["product"]`, or `pl.col(...)`.

  **Action:** any lookup that passed a column *name* as a bare string must
  switch to `af["name"]`. (#37)

- **`projection.set()` stamps a `month` period index — and refuses a frame
  that already carries one.** `month` is elapsed whole months from the
  projection start (`0,1,2,…` monthly; `0,3,6,…` quarterly), length
  `n_periods + 1` and aligned with `t_years()`, so shipped examples like
  `when(af.month == af.policy_term * 12)` now run as written. It is stamped
  only where the name is honest: month-aligned frequencies on a
  projection-anchored axis — not weekly/daily grids, not `from_inception`
  schedules (that axis is policy duration). There is deliberately no
  `proj_year`/`year` column: a projection-year label depends on the model's
  timing convention, and the candidates disagree at every anniversary
  boundary — write the one-line formula you mean (both are documented in
  AGENTS.md).

  **Action:** if your model points carry their own `month` column, rename
  it — or `drop("month")` if it came from a previous run's output — before
  calling `projection.set()`. (#36)

- **`log_linear` curves: rates outside the knot range change.** Extrapolation
  previously clamped the log-discount-factor *level*, so beyond the last knot
  the discount factor stopped decaying and spot rates collapsed toward zero —
  a flat 5% curve returned ≈1.64% at 30y, carrying a 30-year cashflow at
  ≈2.7× its true value — and below the first knot the implied spot blew up as
  `t` shrank. `extrapolation="flat"` (the default) now holds the boundary
  knot's **spot rate**, matching what `"flat"` has always meant for
  `linear`/`pchip`, whose knots are rates. `extrapolation="forward"`
  (`log_linear` only) holds the last segment's forward rate — the
  market-consistent choice for discounting beyond the last liquid tenor.
  Unknown values now raise instead of being silently ignored; rate-space
  methods reject `"forward"`. Curve identity: the default keeps every
  existing `source_sha()`; a `"forward"` curve hashes differently.

  **Action:** if you evaluate a `log_linear` curve outside its knot range,
  those rates change. Re-run any reconciliation that discounts past the last
  knot (typically 20y+ cashflows). (#31)

### Fixed
- **Reassigning an existing column via attribute updates the frame.**
  `af.premium = af.premium * 1.1` previously became a shadow instance
  attribute: reads returned the new values while `collect()` kept the stale
  column, silently mixing old and new numbers in one output. Existing
  columns now route through the same path as bracket assignment. (#21)
- **Unit-length literal lookup keys broadcast to the batch length.**
  `lookup(..., pl.lit(x))` raised `lengths don't match: key columns not
  equal length` whenever Polars didn't pre-broadcast the literal — always
  in-memory, and beyond one morsel under streaming, so toy frames passed
  while production frames failed. (#22)
- **Scalar-key lookups declare their true schema.** The output dtype was
  unconditionally `List(Float64)` while scalar-key lookups return flat
  `Float64`; the stale schema broke `when()/otherwise()` and scalar-last
  arithmetic with errors naming innocent columns. Declared dtype now
  matches runtime. (#23)
- **Hash-storage key encoding is honest.** Null and narrow-integer keys
  were encoded to 0 and returned key 0's rate; categorical keys all
  collided onto a single rate; `UInt8`/`UInt16` key columns panicked the
  plugin; duplicate key rows at build silently last-write-won; ragged inner
  key lists misaligned every subsequent policy's rates. Each is now either
  correct or a loud build/lookup error naming the offending row. (#25, #26)
- **Debug and optimize modes produce identical numbers.** The computation
  graph both applied operations at the call site and replayed them at
  `collect()`, double-applying self-referential assignments in debug mode
  (the CLI default) — `af["x"] = af["x"] + 1` differed between modes. The
  graph is record-only now; every operation applies exactly once. (#27)
- **`Period*` aggregators reduce across scenarios on every path.** The
  sketch variants (`PeriodMedian`/`PeriodQuantile`/`PeriodCTE`) crashed on
  the scenario axis; partitioned `.over(dim)` still reduced over
  policy×scenario cells; and non-additive `.of()` aggregations under
  `run_aggregated` were silently batch-size-dependent (now rejected at
  validation with guidance). (#29)
- **The documented `dimensions` rename mapping works.**
  `dimensions={"duration": "policy_duration_yrs"}` discarded the dict key,
  so renamed lookups failed with `No value provided for key column`.
  Lookups now always speak the dimension-dict vocabulary, and the
  unmatched-key error reports both vocabularies. (#30)
- **Unary negation works on list columns** — `-af.claims` instead of
  `0 - af.claims` — on both column and expression proxies, and it preserves
  integer dtypes (negating a duration no longer silently widens it to
  Float64). (#38)
- **`gspio describe` handles projection output.** Parquet files with list
  columns no longer leak a Rust storage-layer error; list columns get a
  per-period summary, are excluded from suggested lookup dimensions, and
  the printed code example actually runs. (#40)
- **Collect-time failures now name the offending column.** (#39) A lazy
  chain failing at `collect()` used to surface the raw Polars error — e.g.
  `ShapeError: list lengths differed at index 0: 6 != 3` — with no clue
  which of a model's columns produced it. Every assignment is now recorded
  (as a bare name/expression pair; no tracing overhead) and, when a
  `ShapeError`, `InvalidOperationError` or `SchemaError` reaches the
  `collect()` boundary, the recorded assignments are replayed against a
  pristine baseline (row-capped, so diagnosis stays fast at scale) until one
  reproduces the error class AND message. The message then ends with
  `Failing column: 'x'` and the column's defining expression. The batched
  at-scale runners (`run_to_parquet`, `run_aggregated`) route their collect
  failures through the same boundary. When attribution is not certain —
  nothing recorded reproduces the error, the replay itself fails, or an
  unrecorded plan change (filter/join/select) made replay unsound — the
  original error passes through byte-for-byte: a wrong column name costs
  more than no column name.

### Changed
- **Rollforward extractions now share ONE kernel call, by construction.**
  `CompiledRollforward` gains the expression surface directly —
  `compiled.expr_for(state)` / `compiled.increment_for(label)` — and
  extractions reference a single hidden struct column that `ActuarialFrame`
  materialises on first use (and strips from output, as it always has). The
  old design cached one plugin expression and relied on the Polars optimiser's
  common-subexpression elimination to deduplicate the kernel call; Polars 1.42
  stopped applying CSE to plugin expressions, and in worksheet-style models
  (each `af.x = ...` its own `with_columns`) CSE never folded across
  assignments anyway — a K-state rollforward has always cost K kernel runs.
  It now costs one. `RollforwardCollector` remains as a deprecated facade
  with its old self-contained-expression semantics (one kernel call per
  extraction), which is also the pattern for raw Polars frames alongside the
  new `compiled.plugin_expr()` escape hatch.
- Dependency bumps: `polars` 1.38.1 → 1.42.1, `numpy` cap raised to `<2.6`.
  The error formatter's missing-column extraction now parses Polars 1.42's
  richer `ColumnNotFoundError` text (which appends a query-plan dump whose
  `COLUMNS` token the old first-word heuristic misread) and still handles the
  older formats.

### Documentation
- The AGENTS.md quickstart called a removed projection API
  (`create_projection_timeline`); a sweep found six stale locations, all
  corrected, and the quickstart now runs end-to-end as a test so it cannot
  rot silently again. (#35)
- Timing conventions are surfaced in the top-level docs: `prospective_value`
  defaults to end-of-period while `cumulative_survival` defaults to
  beginning-of-period — opposite defaults — with the warning that constant
  rates make a wrong choice invisible until rates vary. (#42)
- `PRINCIPLES.md` records the framework's positions (published at
  gaspatchio.dev/principles) in-repo, loaded into every agent session
  alongside the existing rules.

### Infrastructure
- `uv.lock` is tracked and CI installs with `--locked`, so a new release of
  a dev tool can no longer break unrelated PRs; a repo-root workspace
  boundary stops `uv` from silently resolving a parent multi-repo
  workspace. (#33)
- Issue templates with auto-triage labels, release-notes configuration, a
  public roadmap policy (ROADMAP.md), and a private email intake for bug
  reports whose reproductions can't be posted publicly (SECURITY.md).

### Security
- Bumped `pyasn1` 0.6.3 → 0.6.4 (clears five advisories). Recorded an
  explicit osv-scanner exception for GHSA-9xwg-3r6f-jcx2
  (`pymdown-extensions`, dev-docs only; the fix is hard-capped upstream by
  `marimo <11`) with its reachability argument.

## [0.5.3] — Scenario auto-batching can no longer OOM the box

The `batch_size="auto"` scenario search measures candidate batch sizes by
running them; three field-observed ways that measurement itself could exceed
physical memory and get the process kernel-killed are now closed. (#8, #10,
#11)

### Fixed
- `for_each_scenario(batch_size="auto")` no longer risks a kernel OOM-kill
  while *measuring* candidate batch sizes. The streaming-batch search now
  predicts each ladder rung from the last measured one and never launches a
  probe whose predicted peak already exceeds the memory budget. Previously
  the search ran every rung unconditionally and checked the budget only after
  the fact — a probe larger than physical memory died mid-`collect()`, before
  any back-off logic could run (observed as a CI runner death on a
  10-scenario × 100K-policy cell, where the b=4 streaming probe demanded
  ~11.5 GB on a 16 GB box). The prediction is linear-in-batch times
  `streaming_batch_inflation` (3.0): under the streaming engine the scenario
  cross-join peak is *super-linear* in batch at high policy counts
  (Polars #20786; the same cell measured b=4 at ~8.6× the b=1 rung, 2.2×
  above linear), so a bare linear gate still under-predicted the killer rung.
  Over-predicting costs at most a smaller batch; under-predicting costs the
  process. Probe peaks are additionally floored by the materialised frame's
  size: in a process with retained allocator pools a batch can be served
  entirely from pooled memory — RSS never grows, the sampler reads ~0, and
  any prediction multiplied from that zero is blind. The frame's bytes are
  live memory regardless of where the allocator got them (the same floor the
  policy axis has always applied to its seed measurement).

## [0.5.2] — Post-release correctness fixes

Correctness and robustness fixes surfaced by a thorough onboarding and
due-diligence review, plus a vectorised aggregation fold and a dependency
security bump. (#7)

### Changed
- **`prospective_value` timing now follows the Excel annuity convention.**
  `end_of_period` is the ordinary annuity (Excel `PV` type 0) and
  `beginning_of_period` is the annuity-due (type 1); the two labels were
  previously inverted. Models that passed a timing argument will see their
  present values change — re-check any `prospective_value` timing against the
  Excel convention.

### Fixed
- `maximum_age` projection grids are sized from the *youngest* life in the book,
  so no policy's horizon is silently truncated.
- Excel `pv` is computed per policy instead of broadcasting the first row's
  `nper`/`pmt`/`rate` across the whole frame.
- Assumption-table dimension null-fills stay within their group instead of
  bleeding across partitions.
- Re-registering a table under an existing name with *different* data now warns
  instead of silently keeping the first table.
- `Period*` scenario aggregators reduce across scenarios per period on the
  scenario axis.
- Non-additive `run_aggregated` aggregators (`Mean`, `Variance`, `Std`,
  `Median`, `CTE`) are batch-invariant — both the plain and partitioned
  `.over()` folds divide by the policy count, not the number of batches.
- `RelativeFloorShock` raises with guidance instead of silently doing nothing.
- A uniform book whose input lists all disagree with the schedule's `n_periods`
  now fails loudly instead of truncating to the wrong horizon; variable-horizon
  ("jagged") books are unaffected.

### Performance
- `run_aggregated` batch folds are vectorised: `Sum`/`Min`/`Max`/`Mean`/
  `Variance`/`Std` reduce each batch in a single Polars pass, and the
  partitioned `.over()` path folds per group rather than iterating per policy.

### Security
- Bumped `crossbeam-epoch` 0.9.18 → 0.9.20 (RUSTSEC-2026-0204).

### Documentation
- The install page explains how to install `uv` and adds a verify step; the
  rollforward inspection page and the bundled model-building skill were corrected.

## [0.5.1] — CLI model-points loading

Bug-fix release for the `gspio` CLI and assumption-file loading. No engine or API
changes. (#5)

### Fixed
- `run-model`, `run-single-policy`, and `calc-graph` load model points from CSV as well
  as Parquet — the loader was Parquet-only despite the `--help` text; unsupported
  extensions now raise a clear error.
- Model points may live in any directory: the CLI previously kept only the file's
  basename and looked for it next to the model, so a path elsewhere failed with
  `FileNotFoundError`.
- `Table.from_scenario_files()` and `from_scenario_template()` accept CSV, Parquet, or a
  mix, matching the other assumption loaders (which were already format-agnostic).
- `run-single-policy` auto-detects the policy-ID column (`policy_id`, `policy_number`, …)
  when `--policy-id-column` is omitted, honouring an explicit name case-insensitively.

## [0.4.2] — First published release (docs + packaging)

Same engine as the v0.4.0 and v0.4.1 tags — neither shipped a populated release (0.4.0's
wheel build was blocked by a CI billing limit; 0.4.1's tag was burned when the release job
created an empty release under the org's immutable-releases policy). 0.4.2 is the first
published GitHub Release carrying wheels: identical computation, plus the documentation and
CI tidy-up landed since the 0.4.0 tag. No API or behaviour changes. (Distributed via GitHub
Release assets; PyPI publishing is not yet wired up.)

### Documentation
- Single canonical root `README.md` (the duplicate `readme.md` case-collision that left GitHub rendering a stale landing page is removed).
- Pydantic-style rewrites of the root, Python, and Rust READMEs — badges, docs-forward, cross-linked to [gaspatchio.dev](https://gaspatchio.dev/) and the [benchmark dashboards](https://opioinc.github.io/gaspatchio-core/).
- `ref/ARCHITECTURE.md` brought current: projection axis (jagged timelines + rollforward kernel), the scenarios/aggregation layer, and the streaming engine.

### Infrastructure
- Cut Actions spend: benchmark/eval jobs run on push to `main` (plus schedule / `benchmark` label / dispatch) instead of every push to `develop`; dropped the `windows-m` leg from the per-PR benchmark; grouped Dependabot updates into one PR per ecosystem; per-ref CI concurrency cancellation.
- Release job now creates a draft, attaches the wheels, then publishes — compatible with the org's immutable-releases policy, which locks a published release's assets at publish time.

---

## [0.4.0] — Unified aggregation surface + jagged timelines

Everything merged to `develop` since v0.3.1 (#99–#114). The headline is a single aggregation
vocabulary across two axes — **the aggregator is the primitive, the driver is the axis** — plus
jagged per-policy timelines becoming the default projection shape and live streaming/progress
on the scenario drivers.

### Added
- **`run_aggregated`** policy-axis driver: batch policies, fold each to per-period vectors, never co-resident. (#111)
- **`Period*` aggregator family** — `PeriodSum`/`Count`/`Mean`/`Min`/`Max`/`Variance`/`Std` (additive; `Mean` is exact Sum/Count, `Var`/`Std` are vector Welford–Chan), robust to jagged timelines. (#111)
- **`.over(by)` portfolio partitioning** on both drivers (`run_aggregated` and `for_each_scenario`) — product / cohort / channel splits without re-running the model; tidy long output, lossless (sum over partitions == the unpartitioned total). (#111)
- **`run_to_parquet`** policy-axis spill for the full-output path that can't fold: batch + stream each batch to parquet, refusing RAM-backed targets, preflighting disk, renaming atomically. (#111)
- **Rank-based per-period aggregates** — `PeriodQuantile`/`Median`/`CTE` via a vectorized DDSketch histogram (no per-value loop). (#111)
- **Shape-aware `for_each_scenario` auto driver** — `batch_size="auto"` runs a measured streaming-batch search over a geometric ladder and records the full `SelectionDecision`/`ProbeResult` ladder for audit. (#106, #111)
- **Cgroup-aware batch sizing** — sizes against the cgroup's own-usage headroom (v1/v2), subtracts base RSS, **fails open** to host RAM, **fails loud** (`IrreducibleCellError`) instead of silently clamping. (#111)
- **`ScenarioRun` + mergeable aggregator layer (v0.2 surface)** — Beam-style aggregator Protocol with `.alias()` / `.over()` / `.of()`, DDSketch CTE/Quantile/Median, Welford+Chan Mean/Variance/Std, opt-in audit-sidecar JSON. (#105)
- **Chained `.when()` on list columns** (GSP-87). (#99)
- **Streaming + progress on `ScenarioRun`** — `ScenarioRun.run(progress=…, on_batch=…)` forwards to the same loop as `for_each_scenario` (live observation only — `source_sha()` / audit unchanged); `BatchSnapshot` becomes a progress type (`elapsed_s` + `fraction_done` / `eta_s` / `throughput`) and `progress=True` logs `"47% · ETA 3m12s"`; `ScenarioResult` gains `n_batches`. (#114)

### Changed (behaviour)
- **Jagged per-policy timelines are now the default** projection shape (per-policy start/end via kernel + masks + reconciliation), replacing the uniform-grid default. (#108, #106)
- **Projection-axis API unification** on top of a rollforward state-machine kernel. (#104)
- Polars plugin dispatch extracted into a `polars_backend/` subpackage; `Shape` is now the single source of truth (`ColumnTypeDetector` removed). (GSP-95: #100, #101, #102)

### Performance
- **O(1) plan-build per assignment** via lazy + incremental schema resolution. (#109)

### Infrastructure
- **Apache-2.0 licensing** — root LICENSE + NOTICE, SPDX headers (REUSE 3.3), and an outbound-compatibility licence-check workflow.
- **Windows benchmark lanes** on core-matched runners. (#112)
- Dependency/security: cleared Rust OSV advisories via lockfile bumps. (#110)
- lifelib reference data extracted into a `gaspatchio-benchmarks` sister repo; agent instructions consolidated into `AGENTS.md` + `CLAUDE.md` shims. (#107)

### Known limits
- `PeriodQuantile.over()` is deferred (its multi-level output has no tidy single-column form); `Count` / `ArgMin` / `ArgMax` remain scenario-axis-only and are rejected under `.over()`.
- DDSketch CTE / Quantile precision ≈ 10 bp at the 99.5th percentile — within actuarial SCR / CTE-70 tolerance; tighten via a lower `relative_accuracy`.

---

## [0.2.0] — GSP-101 Mergeable Aggregator Layer

### Added
- Beam-style `Aggregator` Protocol (5-tuple: `within_expr`, `create_accumulator`, `add_input`, `merge_accumulators`, `extract_output`) plus `canonical_form()`
- `.alias(name)`, `.over(by)`, `.of(expr)` modifiers on every aggregator
- Multi-column partitioning via `.over(tuple)`; output shape: scalar metric → scalar, partitioned metric → `pl.DataFrame` keyed by partition columns
- DDSketch-backed mergeable `Quantile` / `Median` / `CTE` / `QuantileRank` (paired signed-value sub-sketches; `relative_accuracy` tunable, defaults to `1e-4`)
- Welford + Chan parallel-merge `Mean` / `Variance` / `Std`
- Hypothesis property test pinning merge associativity + commutativity for every built-in aggregator
- Opt-in audit sidecar JSON via `ScenarioRun.run(audit=True | Path)`; default location `./gaspatchio_audit/<run_id>.audit.json`
- Cross-process governance test: plan + custom aggregator survives YAML round-trip across fresh interpreters with bit-exact aggregations + identical `source_sha()`
- `parse_aggregations(spec)` recursive parser for the new list-of-dict YAML shape, including `_Partitioned` round-trip

### Removed (breaking)
- `MultiAgg` — pass aggregators directly: `ScenarioRun(aggregations=(Sum("loss").alias("total"), ...))`
- `GroupedAgg` — use `.over(by)`: `ArgMax("loss").over("lob").alias("worst")`
- `metric(col, agg)` — the column travels with the aggregator: `Sum("loss")` instead of `metric("loss", Sum())`
- `ScenarioMetric` — folded into the aggregator base class
- `for_each_scenario(agg=..., per_scenario=...)` kwargs — replaced by `aggregations: Sequence[Aggregator | _Partitioned]` where each aggregator carries its own `within_expr`
- `ScenarioRun.aggregations: dict[str, ScenarioMetric]` — now `tuple[Aggregator | _Partitioned, ...]` with `.alias()` providing the output key

### Migration table

| v0.1 | v0.2 |
|---|---|
| `MultiAgg({"total": Sum()})` | `(Sum("loss").alias("total"),)` |
| `GroupedAgg(by="lob", metric=ArgMax())` | `ArgMax("loss").alias("worst").over("lob")` |
| `metric("loss", CTE(0.005))` | `CTE("loss", level=0.005).alias("scr")` |
| `ScenarioMetric(per_scenario=expr, across_scenario=Sum())` | `Sum.of(expr).alias("name")` |
| `for_each_scenario(..., agg=Sum(), per_scenario=pl.col("loss").sum())` | `for_each_scenario(..., aggregations=(Sum("loss").alias("total"),))` |
| `ScenarioRun(aggregations={"total": metric("loss", Sum())})` | `ScenarioRun(aggregations=(Sum("loss").alias("total"),))` |
| `result.aggregations` (scalar) | `result.aggregations["total"]` (dict keyed by alias) |

Loading a v0.1-shaped YAML plan raises `ValueError("v0.1 plan format detected ...")` pointing at this table.

### Known limits
- DDSketch-backed aggregators allocate ~1.2 MB per sub-sketch at `relative_accuracy=1e-4`; tune via constructor kwarg (≈125 KB at `1e-3`)
- DDSketch CTE / Quantile precision ≈ 10 bp at the 99.5th percentile — within actuarial SCR / CTE-70 tolerance; tighten via lower `relative_accuracy`
- Polars 1.38.x pin required for `Expr.meta.serialize()` bit-exactness on the `.of(pl.Expr)` escape hatch
- `master_seed` + `batch_size > 1` raises `ValueError` (unchanged from GSP-100)
- Drivers-dict scenario shape forwards drivers only at `batch_size=1`; raises at `batch_size > 1` rather than silently dropping them

---

## [Unreleased] — GSP-100 ScenarioRun

### Added
- `ScenarioRun` typed plan with `canonical_form()` / `source_sha()` / `describe()`
- `for_each_scenario` bounded-memory loop primitive
- `ScenarioMetric(per_scenario, across_scenario)` reduction recipe with `metric()` sugar
- 15 starter aggregators: Sum, Count, Mean, Std, Variance, Min, Max, ArgMin, ArgMax, CTE, Quantile, Median, QuantileRank, GroupedAgg, MultiAgg
- `@scenario_aggregator()` decorator for user-defined plugins
- `Table.canonical_form()` and `Table.source_sha()`
- `master_seed` plumbing via `drivers["rng_seed"]` (sha256-derived)
- Memory benchmark verifying batch-bounded peak RSS

### Removed (breaking)
- `batch_scenarios` (use `for_each_scenario(batch_size=N)`)
- `describe_scenarios` (use `ScenarioRun.describe()`)
- `sensitivity_analysis` (now internal; use `ScenarioRun` configs)

### Internal
- `canonical_bytes` lifted from `schedule/_canonical.py` to `_identity.py`

### Known limits (v0.1)
- `master_seed` and the drivers-dict scenario shape currently inject per-scenario state only at `batch_size=1`. A `UserWarning` surfaces this when `batch_size > 1`. Spec §5.5 follow-up edit pending.
