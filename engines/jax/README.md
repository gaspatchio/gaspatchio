# gaspatchio-jax

A second engine for gaspatchio: it reads the graph artifact's **executable**
profile and nothing else, lowers section 11.1 to XLA with each value in the
type the node record declares, and refuses in words whatever the format does
not yet say or this engine does not yet do.

## Installing

```bash
pip install "gaspatchio[jax]"
```

The `jax` extra pins this engine exactly, and the engine requires exactly the
core release it is qualified against, so the two always arrive as a pair;
`pip install gaspatchio-jax` brings the same core. jax and jaxlib are the
floor or newer: an Intel Mac gets 0.4.38, the last release with a wheel for
it, and other machines get the current release. That is jax's CPU build. For
a GPU, add jax's CUDA wheels beside it, `pip install "jax[cuda12]"`, which is
how the engine is qualified on an NVIDIA T4; selecting the engine never
promises a GPU, as the next section says.

Working on the engine inside this repository is different: the core arrives
as a locally built wheel, and the two projects resolve each other from the
checkout. That route is under *Installing it here*, below.

## Running it

It is reached through the two doors the core already carries:

```bash
gspio run-artifact artifact.json book.parquet --engine jax --results results.parquet
```

```python
values = af.collect(engine="jax")
summary = af.graph.last_run
notes = summary.report.notes  # Successful findings from this execution.
```

`collect()` still returns a Polars DataFrame. `af.graph.last_run` names the engine,
result shape and original run report; reading it performs no work. It is `None`
before execution, after the plan changes, or when a new attempt has not completed.
Keep the returned immutable summary if you need it after further modelling.

Three choices have different meanings: `debug` / `optimize` controls diagnostics;
`streaming` / `in-memory` / `auto` selects Polars execution; `jax` selects this
engine. Hardware placement follows JAX configuration before initialization.
Selecting `jax` does not promise GPU execution, and the run summary does not infer
a device from that name. The numerical engine and its device placement are unchanged
by reading the summary.

That is the installed-package form. **Inside this repository**, use
`engines/jax/.venv/bin/gspio` for the JAX commands: that environment contains
both packages. `bindings/python/.venv/bin/gspio` runs the Polars reference.

The core never imports this package. It knows the *name* `jax` and the module
this lives in, and reaches for it only when somebody asks for that name — so a
core installation without this package installed loads none of jax's
dependencies.

## Reading the format

The engine reads a document through `gaspatchio.engines.format` and nothing
else in the core: the formula nodes, the operation vocabulary,
`op_node_from_json`, `inspect_execution`, the document digest and the
producer's own fingerprint grammar. A second Python engine can use the same
module, so its identity checks are the producer's rather than a copy. The
module is a preview tied to `SCHEMA_ID` and changes only with a schema bump.
`tests/test_boundary.py` holds this engine to an allow-list of
`gaspatchio.engines.*` and the native extension.

## The floor, and the two rows the lock resolves

`jax` and `jaxlib` at **0.4.38** or above. The lockfile resolves **two rows**,
deliberately:

| platform | jax / jaxlib |
|---|---|
| darwin x86_64 (this laptop) | **0.4.38** — the last jax with an Intel-Mac wheel |
| linux (locked lane) | **0.11.2** — the committed lock's version |

CI also resolves and installs the current JAX release on a second Linux row.
The stamps establish which versions actually ran; when they coincide, they
are two runs of one version. Both rows use Python 3.12. Local measurements
on the floor do not establish that either Linux row passes.

Beside them: numpy 2.5.3, polars 1.42.1 **on the 64-bit index runtime**,
pyarrow 25.0.1, jsonschema 4.26.0. The runtime width is not incidental: polars
ships its engine as a separate wheel and the bare requirement resolves the
32-bit one, while the core's own environment runs the 64-bit one — so
`polars[rt64]` is named in `pyproject.toml` beside `polars`, and the suite
asserts which runtime loaded before it runs a test.

**64-bit values are enabled at import, and a failure to enable them refuses the
package by name.** Every value this engine holds is the type the record
declares — `f64` in float64, `i64` in int64, dates as day counts, text as
interned codes — and none of that is available at jax's 32-bit defaults.

**A division is one IEEE quotient, a product is rounded before it is read, and
two things are stated rather than changed.** Every
floating-point division a lowering writes goes through `gaspatchio_jax/ieee.py`,
so XLA cannot rewrite it by its form — a literal divisor into its reciprocal, a
divisor that is a power into the opposite power, a quotient of a quotient into
one division by a product — and the engine's `/`, `//`, `%`, rates, discounts,
roundings and day counts are the reference producer's to the bit. Every
product goes through the same file too: XLA's CPU backend lets a multiply that
feeds an addition fuse into one multiply-add that rounds once, where the record
rounds the product and then the sum, and under a threshold that place is a whole
step (`0.5 + 5 * 0.011 >= 0.555`). The arithmetic `*`, the recurrence, a
rollforward's growth and charge, the present value and a curve's line between
two knots each round the product first. What is left:

- **A maths call one place from the producer's.** `exp`, `cbrt`, `norm_cdf`
  and the other calls of §11.1.12 are answered inside that section's
  tolerance, and one place apart is inside it; a threshold set at the call's
  own value can still answer the other way on the two engines.
- **Subnormal numbers flush to zero on XLA's CPU backend.** A value below
  about 2.2e-308 in magnitude, as an operand or a result of any operation,
  is read and written as zero: `5e-324 / 1.0` answers `0.0` on the CPU where
  Python and Polars answer `5e-324`. So a comparison, `sign` and `cbrt` of
  such a value can differ from the producer's by more than any agreement
  band: `x == 5e-324` answers 1 where `x` is 0.0, because the literal is
  read as zero; `x > 0.0` answers 0 and `sign` 0 for `x` = 1e-310, where
  the producer answers 1 and 1; and `cbrt` of 1e-310 answers 1e-310 where
  the producer answers 4.6e-104. No actuarial quantity lives there, and the
  engine leaves the backend's mode as XLA sets it, on the CPU and on a GPU,
  whose trade-offs this engine favours; a claim that this engine agrees
  with Polars, to the bit or inside the agreement rule, excludes values
  below the least normal double. The GPU backend was not measured for this.

## Installing it here

Inside this repository the core arrives as a **wheel**, never as an editable
install into `bindings/python`: a measurement taken against a swapped build is
a measurement of something else. `bootstrap.sh` is the whole recipe, and it
runs from this directory only. Build the core wheel for the interpreter first
(`maturin build --release --interpreter <python>` in `bindings/python` writes
it to `target/wheels/` at the repository root), then:

```bash
cd engines/jax
./bootstrap.sh ../../target/wheels/gaspatchio-<version>-cp313-cp313-<platform>.whl
```

The optional second argument selects the interpreter, for example
`./bootstrap.sh /path/to/python312-core.whl /path/to/python3.12`.
The default remains Python 3.13; the wheel must match the selected interpreter
and platform. CI builds its own release wheel and installs it into both the
engine environment and a separate core reference environment.

It creates `.venv`, installs every locked dependency except the core
(`uv sync --locked --no-install-package gaspatchio`), installs the core wheel
with `--no-deps`, and prints the stamp the suite then asserts: the interpreter,
the jax and jaxlib versions, the core's version, and the imported extension's
path and sha256. The extension has to be the one inside **this** venv, and the
core's version the one `pyproject.toml` pins.

Inside the venv, executables are run directly:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests bench
.venv/bin/ruff format --check src tests bench
.venv/bin/mypy src
.venv/bin/pyright src
```

**The two projects resolve each other from the checkout.** `pyproject.toml`
requires the core exactly, and the core's `jax` extra pins this engine
exactly. Neither version is on the index before its release tag, so each lock
resolves the other through `[tool.uv.sources]`, which only uv reads: the
core's lock finds this engine at `../../engines/jax`, and this lock finds the
core at `../../bindings/python`. The published metadata is untouched by
either, so an installer outside the repository sees the two exact pins and
nothing else.

- `uv lock` in this directory is how the lockfile is made. It reads the
  core's static metadata from `bindings/python/pyproject.toml` and builds
  nothing. A change to either project's dependencies or version leaves both
  locks stale, so relock both, this one and the core's.
- The core's source is marked editable. The core's own lock reaches this
  directory through its `jax` extra and meets its root project again at the
  far end, and uv refuses two references to one directory that disagree about
  being editable. Nothing installs the core from that source.
- `bootstrap.sh` is the supported route: it skips the core in the sync and
  installs the wheel itself. `no-build-package = ["gaspatchio"]` is a guard
  beside it. Measured with uv 0.12.1 and 0.12.19, `uv sync` and `uv run` in
  this directory refuse by name rather than build the core. The guard does
  not reach uv's pip interface, which builds a first-party or editable source
  it is asked for directly, so `uv pip install -e ../../bindings/python`
  compiles the core; the suite's stamp then refuses to run, because the
  extension is no longer inside this venv.
- uv drops a version specifier that a path source satisfies, so neither lock
  can see a pin that disagrees with the version it names.
  `bindings/python/tests/test_distributions.py` compares them instead, and
  the suite's stamp reads the core version from this project's own pin.

## Validate and compare

Inspect portability before supplying a book:

```bash
gspio validate artifact.json --engine jax
```

It reports each node as lowered, lowered off the trace under a stated
condition, or refused with its reason. It checks the tree; input and
completion checks still run when a book is supplied.

For numerical agreement, export the executable `artifact.json` from the same
`model.py`. Produce both results with every value-bearing node
named by its node id, including superseded definitions and state balances:

```bash
gspio calc-graph model.py book.parquet --profile executable --artifact artifact.json
gspio run-model model.py book.parquet --every-node --results polars.parquet
gspio run-artifact artifact.json book.parquet --engine jax --every-node --results jax.parquet
gspio compare artifact.json polars.parquet jax.parquet --json
```

`compare` needs no JAX installation. It checks the artifact identities and
states the input digests, comparison scope and row matching. The agreement rule
compares finite values against each policy's own timeline scale, including the
values read by the formula; integer, Boolean, date and text values compare
exactly. The strict fixed-floor result is kept beside the agreement rule's.

| Verdict | Exit status | Meaning |
|---|---|---|
| agree | 0 | The supplied results satisfy the comparison. |
| disagree | 1 | A complete comparison fails. |
| indeterminate | 4 | Missing results or reads prevent a verdict; the report names what is absent. |
| unreadable or incompatible | 2 | The files cannot be compared as supplied. |

Final-schema files can agree on the reduced scale, but missing reads can
make a failing reduced test indeterminate. Use `--every-node` on both runs
for the full scale and check `same_inputs` before claiming conformance.

## What it does today

`coverage.json` is the authority and is generated from the capability
predicates the runtime applies — so it cannot claim more than the engine does.
Of the 101 identifiers the format names: **96 lowered**, **2 lowered off the
trace** (`to_text` and `str.to_date`, on the host, from operands that arrived
or were written into the formula), **3 refused by name** — with the sentence
and the clause each refusal rests on rather than the bare word.
`rollforward.increment` needs a machine that tracks its increments, which
section 16.1's executable subset excludes; `rollforward.struct` answers a
Struct and section 10 has no Struct type (16.3); and `to_list`'s operand is a
fixed-width array section 10 names no type for, so no document this engine can
be handed carries one (11.1.40).

A **compiled rollforward** runs as one `lax.scan` down the periods, with the
declared states as the carry and the increments applied inside a period in the
order the compilation serialized them — section 16.1's bounded portable subset
and nothing wider. Every state is checked finite at every step, and a refusal
names the compilation and which of its steps produced the value. Extraction is
at `eop` and nowhere else: 16.1 states a portable value there and says outright
that `bop` does not acquire one, so a `bop` read refuses by name. A body
outside the subset — tracking, a lapse condition, a contract boundary, a
non-portable binding, an operation outside the closed list, a rounded charge,
an ungated ratchet — refuses before the book is opened, where the document
carries the compilation's own node.

The three reads that select a row — `lookup`, `mortality.at` and `join` — go
through one dense grid per basis, addressed by arithmetic, with an exact
sorted-rows search wherever the key space overflows a flat index, would take
over a hundred mebibytes, or is under ten per cent dense. Every basis that
takes the search is reported by name, with the condition and the numbers. No
basis in either shipped model's artifact takes it: the sparsest is a select
mortality grid at 80 %.

A left `join` whose record carries `on_missing="null"` keeps a policy whose key
reached no row (§11.1.2). The engine holds no null, so the miss is held beside
the arriving column: published as it stands, the column carries the null Polars
publishes; read by `fill_null`, it is filled; read by any other formula, or
folded by `run_aggregated`, it refuses for the policies it stands in, as a null
read as a value does. A join without the attribute refuses every miss.

`agreement.json` records the worst observed ratio per identifier under the
agreement rule. It is a ratchet: a landing that worsens a ratio moves the
number with the reason beside it, and nothing else may move it.

`tests/expectations.json` records what this engine expects of each of the
conformance kit's 894 published cases. A case moving from *not-yet-lowered* to
*value-pass* is an edit somebody made to that file, reviewed in the diff.

## Refusals and remaining vector boundaries

One `EngineRefusal` carries the run report. The CLI prints it and exits 1; the
frame door raises it. Tree refusals name unsupported operations, unknown types,
computed text, and compilations outside section 16.1. Input refusals name
missing or mistyped columns, null values (which the engine cannot hold, so it
refuses them at the door), unexplained list lengths, and invalid input domains.
Both end **Nothing was computed.** Checks on computed values are decided at
completion and end **No results were published.** Each finding carries its
location, count where available, next move and the section of the
specification it rests on; an aggregation refusal cites none, because the
specification leaves aggregates out of the artifact. An existing destination
survives a refused run.

**A NaN reaching a comparison (section 11.1.26) is answered where its answer
holds a NaN, and refused by name where it would be a null.** A stored
comparison is a NaN indicator, and `&`, `|` and `~` over it have no truth
value either, as on every side: per period the indicator is NaN; per policy
the result is a Boolean, null there wherever it is read (section 11.1.27). A
`when` whose condition is a comparison a NaN reached answers NaN in those
cells where its answer is a double, as the reference producer and the reader
do, and is refused for them by name (`comparison.unknown`) where its answer
would be a null -- a whole number, text, a flag or a date. On either shape
that refusal reaches whatever reads the null, not only storing it: a flag a
per-period `when` left null is refused under arithmetic, `&`, `~`, a null
test or another `when`'s condition, as it is stored. A per-policy NaN
combined with a per-period run of any type repeats over every period of its
policy (section 11.1.18), so the combination has no truth value in any of
them. A `when` over a per-policy
`&`, `|` or `~` a NaN left null answers its otherwise there, and so does an
enclosing `&` or `|` under three-valued logic (false AND null is false);
anything else that reads that null -- storing it, comparing it, arithmetic,
`is_in`, `is_null`, `fill_null` -- is refused by name, this engine carrying
no null. Per period, `is_null` over the NaN indicator is false and
`fill_null` keeps it. A band `cut` places a NaN in is a null and refused the
same way (`cut.nan`).

**A whole-number total is refused where a running total on the way passes
`i64`, though the total itself fits.** `[2**63 - 1, 1, -1].list.sum()` is
`2**63 - 1`, and the reference producer and the reader answer it digit for
digit; this engine adds the periods in `i64` in order, checks every partial
sum against the range, and refuses the run by name at the second period
(`i64.range`). That is a refusal, never a different value: a total, or one
period of a running fold, that has no `i64` to be written in is refused by
all three. A total whose partials all fit is exact here as there.

**A check on a computed value is counted where it was computed.** A finding
needs two numbers from a check's cells: how many it caught, and the first of
them, off which the report names a policy and a period. So each batch's program
counts them on the device and hands back those two numbers for every check, in
one small array, rather than every check's cells; the report reads the same
count, the same first policy and period and the same sentence off them as it
read off the cells. Two checks over-reach inside a program -- the range of a
whole-number product and of a whole-number power, which cannot be tested
exactly in the type being tested -- and their caught cells come back beside the
count, to be judged exactly on the host, only where the device caught one: a
cell they catch that is inside `i64` finds nothing, and each is judged against
its own operands, a per-policy one read along the periods where it stands.

The following nine conversion vectors stop **in the vector adapter, before
engine inspection**. Section 10 has no portable type name for their inputs;
`normalise` raises `AdapterGap` naming `x` and its type. They remain
`not-yet-lowered`, with no engine or domain-refusal conformance claim.
Case names below have the prefix `conversion-`:

| Cases | Input type |
|---|---|
| `to_float-unsigned-within-the-boundary`, `to_float-unsigned-past-the-boundary` | `u64` |
| `to_text-unsigned-past-i64` | `u64` |
| `to_text-signed-128` | `i128` |
| `to_text-categorical` | `categorical` |
| `to_text-refuses-an-array` | `array[f64,2]` |
| `to_integer-unsigned-within-range`, `to_integer-unsigned-past-i64` | `u64` |
| `to_integer-signed-128-below-i64` | `i128` |

The `to_list` array vectors stop at the same boundary. Its list/scalar
refusal cases reach tree inspection, which refuses the whole identifier
under section 11.1.40; that does not match their requested operand-type cause.
These outcomes also remain `not-yet-lowered`.

The 26 `duration-refusals.json` cases carry an input-only `duration` (or
`list[duration]`) that section 10 cannot name, so no document holds one. The
adapter records the column as the whole number of microseconds its values are
stated in and hands the engine the book as it is, a duration; **the engine's
door refuses the book's column by name** and names the cast that carries it as
a whole number, which is the refusal section 10 asks of whoever meets a time
delta. They earn `domain-refusal-matched`, as the producer and the reader
refuse the same calls.

`raw-struct-export-refuses` reaches **tree inspection** and names the
Struct output's missing portable contract under **16.3**, so it earns
`domain-refusal-matched`. Its report also names tracking under 16.1; that
finding alone cannot earn the Struct result. Other tracked rollforward cases
whose expected cause is obscured by tracking remain `not-yet-lowered`.

## How a book is run

Policies are **grouped by the widths their axes take** — two policies whose
timelines round up to one width are two rows of one rectangle, and two whose
do not are not. Each group is cut into **batches** whose size is read off the
compiled program's own temporaries against a two-gigabyte budget, from the
grid `256, 1024, 4096, 16384, 65536`. Each `(width, batch)` shape is **one
compiled program** that every batch of that group shares.

A **width is not an argument**: everything a program is built around — how
wide a rectangle is, whether two per-period operands are the same timeline —
is settled on the host before the program exists, and everything else goes in
as an argument. That is why a second book of one shape is the same executable
over different numbers, and why the operations that read the width of their
own answer (`projection_set`, the schedule family, `date.date_ranges`) are
lowered before the program rather than inside it.

**On a card, the host and the card work at once.** A compiled
program runs by itself once it has its batch, so the host settles the next
batch and hands it to its program before it reads this one's answers back:
settling overlaps computing, and reading a batch back waits for that batch's
program and no other. It rests on settling reading nothing back off the
device -- every width an axis takes was counted when the book was prepared,
and each lowering that lays an axis is handed its batch's own counts --
because on one device stream a read-back waits for everything already queued.
A calendar range's kept count is the one read left. Work a reader wants on
the device beside a batch -- a fold's partials -- goes in straight behind that
batch's program. Nothing moves but the timing: batches are handed over in the
order they were dispatched, so findings arrive in batch order; a refusal met
settling a batch or building its program comes after every batch before it;
and every value is bit-identical either way. `tests/test_overlap.py` holds
every node of levels 4 and 5 and of a jagged book, and every fold's totals, at
both depths; every node of levels 4 and 5 at 70,000 policies was identical
too, on this laptop on 2026-09-24. What is alive at once is the batch on the
card and the one being written or folded, and a depth past one -- three alive
-- is refused. The batch budget counts one program's temporaries and none of
any batch's answers, so one ahead a card holds two batches' answers beside it:
on level 4 publishing every column, about 3.4 GB a batch of 65,536.

**On the CPU the batches run one at a time, as before**, because there the
device is the host's own cores. XLA runs a CPU program's work in order and
stops taking new work at about thirty-two computations in flight, so a
settlement dispatched behind a running program waits for it; and a batch
written while the next one computes builds and compresses its columns on the
cores the program is using. On this laptop on 2026-09-24, 140,000 level-4
policies every node through the file sink took 61 and 62 s one at a time
against 79 and 86 s one ahead, peaking at 4.5 and 4.6 GiB against 5.5 and
5.3; a million-policy region pass was a wash, 30 and 36 s against 34 and 29 s,
the host's waiting moving from reading back (19 and 23 s) into settling (11
and 10 s).

**On a T4 the overlap bought little, and the reason is measured.** On the GPU
runner's Tesla T4 -- on 2026-09-24, jax 0.11.2 -- a level-4
region pass through the engine's own loop took, one batch at a time and one
ahead, 5.20 and 4.77 s at a million policies, 16.25 and 16.20 s at five
million, and 31.15 and 30.29 s at ten million (level 5 at ten million: 30.03
and 29.62 s). Settling is not what the loop waits on. At ten million the host
spent 19.4 s reading batches back and 7.2 s dispatching them, against 1.9 s
settling them; the same batches' programs took about 8 s in the report's own
region pass, which waits for each batch's columns and reads no mask back.
Reading a batch back reads every check's mask back whole: on level 4, 142
checks and 4.8 KB a policy, about 48 GB across ten million policies. (Those
are the counts the measurements in this section and below were taken at.
Level 4 carries 134 checks today, 4.1 KB of masks a policy, pinned by
`tests/test_tallies.py`: its duration keys became whole numbers, which took
eight range checks away, and its recurrence's widening is now on the record,
which turned one into `to_float.exact`. The timings were not re-run.) So the
masks, not the host, are the bottleneck, and reducing the checks on the card
before they cross back is the measured next lever -- which is not decided
here. What the card did confirm is the premise: `tests/test_overlap.py` passed
there, 29 of 29, with JAX's transfer guard refusing any device-to-host
transfer in every settlement of levels 4 and 5 and the jagged book.

**Reading a batch back now reads what its findings need.** Each batch's program
counts its checks where it computed them and hands back two numbers a check in
one array: on level 4, 142 checks in 2.3 KB a batch, where their masks were 4.8
KB a policy -- about 310 MB a batch of 65,536, and 48 GB across ten million
policies. The one coarse check hands back its cells beside its count, 17 bytes
a policy, and they are read only where the program caught one. A level-4
program that publishes every column hands back 134 arrays where it handed back
274, and a fold's program 7 where it handed back 147. Nothing a finding says
moves: `tests/test_tallies.py` holds every finding of levels 4 and 5, with a
lookup miss, two domain checks and a coarse overflow put into their books, to
the findings every mask read whole gives, batch by batch and merged, one batch
at a time and one ahead; and level 4's, written out, to what the engine found
when it read every mask back.

**On a card, the read-back is what goes.** A level-4 region pass through the
engine's own loop at ten million policies, on the GPU runner's Tesla T4 (jax
0.11.2), before the change on 2026-09-24 and after it on 2026-09-25:

| | one at a time, before | after | one ahead, before | after |
|---|---|---|---|---|
| wall s | 36.05 | 15.50 | 30.42 | 15.14 |
| read back s | 23.28 | 0.76 | 18.65 | 0.25 |
| dispatch s | 7.52 | 10.15 | 7.29 | 10.29 |
| device peak | 5,009 MiB | 4,715 MiB | 8,315 MiB | 8,194 MiB |

Level 5 at ten million went from 29.35 to 15.60 s one ahead, and level 4 at
one and five million from 4.77 to 3.45 s and from 16.09 to 8.66 s. Three
things rose, and they are the price. **Dispatch**, 7.29 to 10.29 s one ahead:
with nothing left to read back, the host waits there instead -- dispatching a
batch now takes about as long as the card takes to compute it, at either
depth, so one batch ahead still buys only 2 per cent (15.14 s against 15.50).
**The card's own calculation**, by about a third: the report's own region
pass, which waits for each batch's columns and reads nothing else, took 10.86
s against 8.23 at ten million, a warm batch of 65,536 0.0699 s against 0.0526
-- the counting's own cost on the card. **Compilation**: a level-4 program for
4,096 policies compiled cold on the runner in 4.12 s against 1.45 (level 5,
4.49 against 1.33; the jagged book, 4.02 against 1.60), and loaded from the
cache in 0.15 s against 0.12.

**The counting is laid out for a laptop too.** Summed and `argmax`-ed laid
flat, one mask at a time, as first written, it cost this laptop more than the
scan it replaced: one level-4 batch of 65,536 policies returning the two
columns a fold reads ran in 2.06 s against 0.88 s. XLA's CPU reduces along a
row in wide vector steps and across a whole mask a cell at a time, so the
engine counts each policy's row first, in a byte, and reads the rows of every
check of one shape together; the same batch runs in 0.87 to 1.01 s against the
scan's 0.82 to 0.94, over three rounds of each. A million level-4 policies'
region pass through the engine's own loop (`bench/test_scaling.py`) on this
laptop on 2026-09-25, three times before that change and twice after it, with
other work loading the machine:

| depth | wall s | read back s | dispatch s | RSS peak |
|---|---|---|---|---|
| 0, before | 29.8–34.1 | 18.7–21.5 | 0.015–0.018 | 4.08–4.09 GiB |
| 0, after | 30.2–31.3 | 24.0–25.3 | 0.019–0.034 | 4.41–4.45 GiB |
| 1, before | 27.2–32.2 | 1.1–2.5 | 0.018–0.038 | 4.54–5.04 GiB |
| 1, after | 29.3–32.8 | 0.05 | 0.012–0.014 | 4.02–4.45 GiB |

On the CPU reading a batch back is waiting for its calculation, so the time
moves between stages and not out of the loop: one batch at a time, the 7.7 to
8.6 s the loop used to spend outside every stage -- letting go of each batch's
142 masks -- is gone, and read-back took it. **One batch at a time, the loop's
peak rose**, from 4.08–4.09 GiB to 4.41–4.45, about 8 per cent, and it is not
the program's: one batch of 65,536 through the same publishing program, once,
in a fresh process, peaks at 3,515 to 3,522 MiB against 3,813 to 3,816
(after against before, in the runs the loaded machine did not slow)
-- about 300 MiB lower, the batch's masks -- so the rise is the loop's timing
and the allocator's. The fold's peak fell, 1.81–1.83 GiB to 1.38–1.39 (below).
What the CPU pays is compilation: the fold's program, built for 65,536
policies, is 9,091 optimised instructions against 8,185 (built for 4,096,
8,823 against 7,885; laid flat, 12,607 and 12,103), and a publishing program
for 4,096 policies compiles cold in 2.6 to 2.8 s against 1.8 to 1.9.

Compiled programs are kept twice: **in the process**, keyed by the shape, and
**on disk** under the user's cache directory through jax's persistent cache,
which is configured when this package is imported because XLA reads that
location when it first compiles and never again. The run's report tells the
three outcomes apart in words — *compiled*, *reused in this process*, *loaded
from the persistent cache* — because a reader cannot act on "cached": only
the third is the one that survives closing the laptop.

**`JAX_COMPILATION_CACHE_DIR` is the knob.** Set it and the executables go
there; leave it and they go under the user's own cache directory. A location
that cannot be written — a read-only home, a full disk, a sandboxed runner
that grants the path and not the write — costs the compiler's seconds and
nothing else: the engine says so in the run's report and carries on. The
cache is an optimisation, and the engine is not.

**Publication is one moment, and the book is never held whole.** Each batch's
columns go to the sink the moment the batch finishes, with the book positions
of its rows, and each column's buffer is let go as it is copied out: what
outlives a batch is its findings. Nothing is visible until every batch has run
and the flags of all of them have been read together. Then the file sink
renames one finished Parquet file into place, the manifest in its footer, and
the frame sink puts its rows in order with one gather. A refusal, an interrupt
or a fault leaves the destination exactly as it was, and nothing beside it. A
fault building a batch's columns waits until every batch has been checked, so
a refusal in a later batch is still the run's answer; and once the findings so
far refuse, nothing more is built or written.

**A book that arrives in its own order, on one timeline, is written once.** The
batching plan is settled before the first batch, and where it hands the book
over front to back and every policy has the same timeline on every axis — as
in levels 4 and 5 — the engine says so as it opens the sink, and every batch is
held to that promise. The file sink then writes each batch straight into
`<name>.<uuid>.unpublished` through Polars' own writer, on a thread of its own,
a 64 MiB block of rows to a row group. Handing a batch over waits until the
writer has copied every row of it into a piece of its own and taken it, so the
batch is let go before the next is built. Every other book is staged: each
batch a part file of its own in `<name>.<uuid>.unpublished.d/`, streamed into
one file in the book's own order at the end, a block at a time. That writes
every row twice, the price of an order known only at the end; a run of one
staged batch renames its one part. A book whose widths interleave — the jagged
one — is staged because it arrives grouped by width. A book sorted by term,
shortest first, arrives in its own order and is staged all the same, because
its rows widen batch by batch: a file written straight through sizes its row
groups from the first batch's rows and cannot resize them, and at 400,000
level-4 policies sorted by width they reached 860 MiB where a block is 64 MiB.

**What the file sink holds is bounded, whatever the size of the book.**
Written straight through, it is what Polars' writer has in flight: up to its
thread count plus four row groups being encoded or written, each beside its
encoded pages, and a few pieces in front of them — about two blocks per
thread, at most about 2.6 GiB on this sixteen-thread laptop. In practice the
writer added nothing to the run's peak: 100,000 level-4 policies every node,
sampled in process every 2 ms, peaked at 3.72 GiB written straight through
and at 3.72 GiB through a sink that writes nothing, where the staged route
peaked at 4.09 and 4.15 GiB and then spent 9.7 s putting its parts in order.
Staged, publication holds the 64 MiB block being put in order
and its gathered copy; each open part's current read, which is four of the
part's row groups — and a part is written in row groups of its share of a
block, so however finely the engine's width groups interleave, the parts
together hold a few blocks; and the writer's own flight.

**A key pressed at any moment stops the writer and leaves nothing.** The sink
holds the writer before its thread starts, so a key pressed as it starts finds
it to stop; it tells the writer the run is abandoned with a plain store rather
than a call, so a second key press cannot come between the two; and every wait
looks up every tenth of a second as well as when woken. A writer given up
removes its own file as it ends, and a wait on a writer that takes no row and
writes no byte for a minute gives up and says so. A finished file is held to
the rows handed over, as staged parts are held to the book, so a row lost on
the way into it refuses publication rather than publishing short.

What that buys, for level 4 with `--every-node` through a fresh
`gspio run-artifact` on this laptop on 2026-09-24, before and after the stream
(peak resident memory from `/usr/bin/time -l`, with other work loading the
machine):

| policies | holding the book (before) | streaming (after) |
|---|---|---|
| 10,000 | 1.82 GiB, 6.7–7.3 s | 0.96 GiB, 6.1 s |
| 30,000 | 3.87 GiB, 16.3 s (4.41 GiB under heavier load) | 2.04 GiB, 10.0 s |
| 100,000 | about 11 GiB and 49 s, estimated by the slope | 4.18 GiB, 33.6 s |
| 1,000,000 | — | 5.11 GiB, 348 s, an 11.09 GiB file |

What is left is about one batch's columns, the book's own inputs and the
process. Staged, publication itself added, over the memory it started with,
0.31 GiB to a jagged level-4 book of 100,000 policies in four width groups,
0.86 GiB to 100,000 in-order level-4 policies, and 1.01 GiB to 32 parts
interleaved row by row; on the jagged book that put the run's peak 0.14 GiB
above the stream's.

Writing a book in its own order once rather than twice, alternated with the
staged code in fresh processes on this laptop on 2026-09-25, other work
loading it to 7–13 (the same harness, before and after):

| level 4, every node | staged (before) | written once (after) |
|---|---|---|
| 20,000 policies, one batch | 8.4 s, 1.43 GiB | 7.2 s, 1.64 GiB |
| 100,000, two batches | 25.0 and 32.7 s; 3.99 and 3.85 GiB | 18.7 and 25.1 s; 3.77 and 3.72 GiB |
| 1,000,000, sixteen batches | 272 and 253 s; 4.73 and 4.77 GiB | 141 and 124 s; 4.41 and 4.51 GiB |
| jagged, 100,000 — staged either way | 31.0 and 17.5 s; 1.09 and 1.05 GiB | 18.8 and 18.9 s; 1.07 and 1.04 GiB |

The files are the same size in the same row groups — 1,136.2 MiB at 100,000
policies and 11,352.3 MiB at a million — and every value in them is the same.
Re-measured after review, three pairs alternated with the staged code, with
other work loading the machine to 7–15: 100,000 policies in
22.8, 18.0 and 18.6 s at 3.72, 3.73 and 3.72 GiB written once, against 46.7,
38.7 and 29.4 s at 3.93, 3.73 and 3.92 GiB staged.
A run of one batch peaks about 0.2 GiB higher written straight through, because
the pieces in the writer's flight are copies where its one part was written
from the batch itself.

The price is disk. A file is written in 64 MiB row groups, whichever route it
took, and against a file written as one row group that costs 3 per cent
for 30,000 distinct level-4 policies. The model books here are tiled from a
thousand model points, whose repeats one row group compresses away; for
those it is 8 per cent at 10,000 policies and 28 per cent at 30,000:

| row group | 30,000 distinct policies | 30,000 tiled from 1,000 |
|---|---|---|
| one group | 519 MiB | 307 MiB |
| 256 MiB | 524 MiB (+0.8 %) | 346 MiB (+12.7 %) |
| **64 MiB** | **536 MiB (+3.2 %)** | **394 MiB (+28 %)** |
| 32 MiB | 568 MiB (+9.3 %) | 528 MiB (+72 %) |
| 16 MiB | 595 MiB (+14.7 %) | 565 MiB (+84 %) |

## Reducing on the card

A best estimate over ten million policies is a handful of numbers, and the
per-policy rows that make it are hundreds of gigabytes nobody reads. So the
engine can fold instead of publish: each batch is reduced where it was
computed, into the aggregators `run_aggregated` already takes, and only the
totals come back.

```python
from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.scenarios import PeriodSum, Sum

totals = run_aggregated(
    model_fn,                 # the same model function the Polars path runs
    model_points,             # the book, as a Polars DataFrame
    [
        Sum("pv_net_cf").alias("bel"),
        PeriodSum("net_cf").alias("net_cf"),
        PeriodSum("net_cf").alias("net_cf_by_product").over("product_id"),
    ],
    engine="jax",
)
totals.bel                    # a float
totals.net_cf                 # one value per period
totals.net_cf_by_product      # {product_id, period, net_cf}, tidy
totals.produced_by            # the engine, its versions, the graph and the book
```

`run_aggregated` builds the model once over the book without computing it and
hands `JaxEngine.aggregate` exactly what `collect(engine="jax")` hands `run` --
the executable artifact and the columns the frame arrived with, through one
frame method -- with the aggregators. A setup phase that collects the model
points and derives a column folds as it collects. The same fold is reached from
a file:

```bash
gspio run-artifact artifact.json book.parquet --engine jax \
    --aggregate spec.json --results totals.json
```

where `spec.json` lists each aggregator as its canonical form beside its alias:

```json
[
  {"alias": "bel", "kind": "Sum", "column": "pv_net_cf"},
  {"alias": "net_cf_by_product", "kind": "PeriodSum", "column": "net_cf",
   "over": ["product_id"]}
]
```

and `totals.json` is the record `run_aggregated(..., audit=...)` writes, whole
or not at all: each alias's value, what each value is, the artifact's
fingerprint, the book's stamp, and the engine with every version it ran under
and the device it ran on. An inception-aligned artifact -- read from its
schedule, or from its `projection_set` where nothing reads the schedule -- is
refused unless `--align duration`.

**What folds where.** An aggregator of one value per policy -- `Sum`, `Min`,
`Max`, `Mean`, `Variance`, `Std`, `Quantile`, `Median`, `CTE`, `QuantileRank`
-- pulls that one column for the batch, one value per policy, and folds it
through the Polars path's own per-policy fold, so `.over(by)` groups exactly as
`run_aggregated` groups. The door publishes that fold and not the per-period
one, so a per-period partial is always this engine's own. The seven per-period kinds whose partial is a closed
form -- `PeriodSum`, `PeriodCount`, `PeriodMin`, `PeriodMax`, `PeriodMean`,
`PeriodVariance`, `PeriodStd` -- are reduced on the device, each policy masked
to its own horizon; what crosses back is one value per period per partition.
Partitions are the columns a book arrived with, sorted once on the host before
anything runs; each batch then reduces by segment.

**What agrees, and how closely.** The accumulators are the core's own, so the
answer is Polars' fold under the agreement rule -- the order floating-point
additions were made in is the only permitted difference. On levels 4 and 5,
every kind above, alone and partitioned, through both doors: worst ratio
**4.8e-15** (`PeriodMax` under `.over`), counts exact.
`tests/test_aggregate.py` holds it.

The quantile family is the one exception, and the record says so. `Quantile`,
`Median`, `CTE` and `QuantileRank` fold into the core's DDSketch on both paths,
which is accurate to 1e-4 by default. The engine's per-policy values can differ
from Polars' in the last bit, and a value on a bucket's edge can then land in
the neighbouring bucket and move the answer by about twice the sketch's
accuracy. So these agree with Polars within the sketch's accuracy rather than
under the agreement rule. They were identical on levels 4 and 5, and each one's
note in the result's record names its own accuracy.

**What is refused, before the book is read.** `Count`, `ArgMin`, `ArgMax`,
`.of()` and a multi-level quantile under `.over()`, decided by
`run_aggregated`'s own guards and each worded with a next step that works on
this engine; `PeriodQuantile`, `PeriodMedian` and `PeriodCTE`, which keep a sketch
per period and have no partial this engine can compute, pointing to Polars; a
column that is not in the final schema, a per-policy kind over a per-period
column or the reverse, text or dates; and a partition column the model
calculates. A check the trace carried refuses at completion as it does for
`run`, and nothing is returned.

**What the fold is fed, and what it holds.** The fold is a function of one
batch and holds nothing of it once folded, and it is fed the plan's own stream:
each batch is handed over the moment it finishes -- on a card with the next
already computing -- under the stream's own rules: findings kept whatever
happens, nothing folded once they refuse, a fault held behind a refusal. A
per-period fold's partial is queued on the device straight behind its batch's
own program, so reading it back waits for nothing after it.
`tests/test_retention.py` holds the fold to keeping no batch's values alongside
the stream's own consumers, one batch at a time and one ahead.

**Each batch's program returns only the columns folded**, the axes they
stand on and every check's mask. Every node is still traced and every check
still carried, so what refuses still refuses; but a column no aggregator reads
never leaves the device. Folding `Sum("pv_net_cf")` and `PeriodSum("net_cf")`
of level 4, that is two columns of the final schema's 128 -- about 0.7 KB a
policy where every column was 47 KB, beside 4.8 KB of masks. The totals move
only in the last bits a different compilation gives a policy's value: 2.8e-15
at worst against the fold returning every column, over every supported
aggregator on levels 4 and 5. **Each set of columns folded is a program of its
own**, so a set folded for the first time compiles afresh -- 4.5 and 1.9 s at
82,496 level-4 policies for `net_cf` alone, 4.8 and 2.2 s beside `pv_net_cf`,
cold, while a set folded before loads from the cache -- and a column's last
bits belong to its set: `net_cf` folded alone and beside `pv_net_cf` differs
in 60 of 83 periods, by at most 1.2e-18 of the largest period total and 6.0e-15
of a period's own (this laptop, 2026-09-24). What a fold holds at once is
those columns, for the batch being folded and, on a card, the one computing,
beside the accumulators -- so the book's size moves the time and not the peak.

Level 4, `Sum` and `PeriodSum`, the batch pinned at 2,000, each size in a fresh
process, peak resident memory from `ru_maxrss`; measured on 2026-09-24 on the
Intel laptop (i9-9880H, 16 GiB, macOS 15.7.9, jax 0.4.38, extension
`16df6b51…`), the before being the same fold fed by the loop that held every
batch:

| policies | before | after |
|---|---|---|
| 2,000 | 433 MiB | 445 MiB |
| 8,000 | 716 MiB | 449 MiB |
| 24,000 | 1,453 MiB | 452 MiB |
| 96,000 | 2,845 MiB | 483 MiB |

The after column's 38 MiB across a 48-fold book is the book itself and the
columns carried in, not any batch. At the engine's own batch size a million
level-4 policies folded in 34.9 s at a peak of 4.05 GiB -- sixteen batches of
65,536, one batch's 2.9 GiB of final-schema values plus the program's
temporaries and the book -- where the fold before it rode the stream would have
held about 44 GiB (`bench/aggregate_probe.py`, same laptop, 2026-09-24,
agreeing with Polars at ten thousand policies to 1.6e-16).

Returning only the columns folded takes most of that batch away. A
million level-4 policies folded into those two on the same laptop on
2026-09-24, each way in a fresh process after its programs were compiled
once (other work was loading the machine; `bench/aggregate_probe.py
--variants`):

| | wall s | loop s | without the inputs digest s | peak RSS |
|---|---|---|---|---|
| one at a time, every column (before) | 32.6 | 28.7 | 30.7 | 3.96 GiB |
| one ahead, every column | 37.8 | 32.8 | 35.1 | 4.21 GiB |
| one at a time, the columns folded (the CPU's own) | 28.4 | 22.9 | 25.8 | 1.84 GiB |
| one ahead, the columns folded (a card's own) | 25.8 | 20.4 | 23.3 | 1.80 GiB |

The inputs digest was 1.9 to 2.6 s of each; its encoder has since moved into
the Rust core. The same fold at ten thousand agreed with Polars to 6.3e-16,
through both doors.

The same four on the GPU runner's Tesla T4 -- on 2026-09-24, jax 0.11.2 --
at one and ten million policies, each in a fresh process after
its programs were compiled once:

| | policies | wall s | loop s | without the inputs digest s | device peak |
|---|---|---|---|---|---|
| one at a time, every column (before) | 1,000,000 | 8.20 | 5.29 | 7.10 | 3,702 MiB |
| one ahead, every column | 1,000,000 | 8.15 | 5.25 | 7.05 | 7,087 MiB |
| one at a time, the columns folded | 1,000,000 | 8.14 | 5.26 | 7.05 | 1,197 MiB |
| one ahead, the columns folded (a card's own) | 1,000,000 | 8.05 | 5.16 | 6.95 | 1,550 MiB |
| one at a time, every column (before) | 10,000,000 | 51.02 | 36.29 | 40.04 | 5,009 MiB |
| one ahead, every column | 10,000,000 | 50.62 | 35.88 | 39.62 | 8,315 MiB |
| one at a time, the columns folded | 10,000,000 | 51.00 | 36.37 | 40.06 | 2,485 MiB |
| one ahead, the columns folded (a card's own) | 10,000,000 | 50.24 | 35.64 | 39.34 | 2,876 MiB |

Returning only the columns folded halved the card's peak at ten million --
5,009 to 2,485 MiB one batch at a time -- and moved no time. One ahead saved
1.1 and 2.0 per cent of the loop at ten million (0.8 and 1.5 of the whole
fold), returning every column and the columns folded; from the fold before the
overlap to a card's own, the loop went from 36.3 to 35.6 s. Holding a second
batch cost the card 391 MiB returning the columns folded and 3,305 MiB
returning every column. The loop is still 22.5 to 23.1 s of reading back --
almost every byte of it a check's mask -- and 7.5 to 7.7 s of dispatch, out of
about 36. The inputs digest was 10.9 to 11.0 s of each fold at ten million; its
encoder has since moved into the Rust core. The fold agreed with Polars at ten
thousand policies to 7.9e-16, through both doors, on the card.

**A fold's batch now hands back its checks' counts, not their masks**: about
0.7 KB a policy of the columns folded and 17 bytes of the one coarse check,
where it was 5.5 KB. On this laptop -- the Intel i9-9880H, 16 GiB, macOS
15.7.9, jax 0.4.38, extension `05aeac55…` -- the four ways at a million level-4
policies on 2026-09-25, `bench/aggregate_probe.py --variants` three times
before that change and twice after it, other work loading the machine:

| | wall s, before | after | read back s, before | after | peak RSS, before | after |
|---|---|---|---|---|---|---|
| one at a time, every column | 33.0–36.6 | 34.5–36.2 | 19.0–21.3 | 20.1–21.1 | 3.96–3.99 GiB | 3.67 GiB |
| one ahead, every column | 32.8–34.6 | 30.1–32.3 | 1.3–1.6 | 0.07 | 4.21–4.90 GiB | 3.85 GiB |
| one at a time, the columns folded (the CPU's own) | 21.9–25.9 | 23.4–26.0 | 14.7–17.2 | 15.3–17.0 | 1.81–1.83 GiB | 1.38–1.39 GiB |
| one ahead, the columns folded (a card's own) | 20.6–23.6 | 22.8–25.2 | 1.1–1.2 | 0.26–0.30 | 1.83 GiB | 1.38–1.40 GiB |

Dispatch was 0.009 to 0.028 s before and 0.004 to 0.011 s after: on the CPU it
was never the cost. The time is where it was -- reading back one batch at a
time is waiting for the calculation -- and the peak is about 440 MiB lower.
Counted one mask at a time and laid flat, as first written, the CPU's own fold
took 37.4 and 38.6 s, reading back 30.2 and 31.1 s. Every finding is the one the
masks gave (`tests/test_tallies.py`).

The same four at ten million policies on the GPU runner's Tesla T4, before the
change on 2026-09-24 and after it on 2026-09-25, each in a fresh process after
its programs were compiled once:

| | fold s, before | after | loop s, before | after | read back s, before | after | device peak, before | after |
|---|---|---|---|---|---|---|---|---|
| one at a time, every column | 41.09 | 20.52 | 36.26 | 15.71 | 23.10 | 0.70 | 5,009 MiB | 4,715 MiB |
| one ahead, every column | 40.57 | 20.16 | 35.76 | 15.32 | 22.59 | 0.24 | 8,315 MiB | 7,935 MiB |
| one at a time, the columns folded | 40.59 | 18.17 | 35.78 | 13.36 | 22.60 | 0.54 | 2,485 MiB | 2,303 MiB |
| one ahead, the columns folded (a card's own) | 40.33 | 17.80 | 35.52 | 13.01 | 22.34 | 0.14 | 2,876 MiB | 2,394 MiB |

At a million policies a card's own fold took 5.15 s against 7.00 and peaked at
1,054 MiB against 1,550. As in the region pass, the host now waits for the card
where it hands work over: a card's own fold at ten million spent 5.80 s
dispatching and 2.17 s queuing the partials beside each program, against 7.52
and 0.08, and one ahead bought 2 per cent (17.80 against 18.17 s). The inputs
digest was 1.26 s of each. The fold agreed with Polars at ten thousand
policies to 7.9e-16, as before.

`bench/aggregate_probe.py` measures level 4 at one and ten million policies,
with Polars' agreement at ten thousand, on the GPU runner; `--variants` folds
each size the four ways above, and `--batch` pins the batch.

## Measured on this build

Taken 2026-09-21 on this laptop: jax 0.4.38 / jaxlib 0.4.38, polars 1.42.1 on
`_polars_runtime_64`, core 0.9.0 -- the development build of 1.0.0, before its
version moved -- extension sha256
`16df6b5117fdb148c293d4f07013c1e40fe3da9474f4cd402cc0d2fe20c9fa90`.

**The frame door's fold.** `collect(engine=…)` exports the executable document
before anything in the engine runs, a cost the engine's design left unmeasured:

| model | fold |
|---|---|
| 3 definitions × 1 000 policies | 3.1 ms |
| 25 definitions × 1 000 policies | 6.0 ms |
| 100 definitions × 1 000 policies | 14.6 ms |
| 100 definitions × 100 000 policies | 15.5 ms |

Flat in policies, linear in definitions.

**What a basis costs, dense against the fallback.** One read on a basis shaped
like level 4's `mortality_select` (120 ages × 25 durations, 80 % present),
over 10,000 policies × 83 periods — warm median of seven, compiled:

| storage | warm median | against the grid |
|---|---|---|
| dense grid, direct address | **0.69 ms** | — |
| fallback: density under 10 % | 37.4 ms | 54× |
| fallback: key space over a flat index (no packing, lexicographic) | 68.2 ms | 99× |
| fallback: value array over 100 MiB | 36.7 ms | 53× |

Taken 2026-09-21 on this laptop against the build stamped above — extension
sha256 `16df6b5117fdb148…`, jax 0.4.38. Every basis in both shipped models'
artifacts takes the dense grid, so none of the three lower rows is a cost a
shipped model pays today; a basis that does take one is reported by name in
the run's own report, with the condition and the numbers.

**What a book costs, compiled and batched.** Level 4 and level 5, monthly to
each policy's own term over 83 boundaries, on the machine above, taken
2026-09-24. The whole table, with peak memory — the kernel's
high-water mark, each row in a process of its own — and Polars beside, is in
`bench/scaling.md`, written by `bench/test_scaling.py` behind the
`benchmark` marker:

| | level 4 | level 5 |
|---|---|---|
| cold compile at 4,096 policies, empty cache directory | 1.91 s | 1.89 s |
| the same program at 4,096, loaded from the cache | **0.13 s** | **0.14 s** |
| one warm batch of 65,536 policies | **1.30 s** | **1.46 s** |
| temporaries, per policy | 1,345 B | 1,345 B |
| a million policies, region pass | 16 batches, **2 compilations**, 24 s | 16 batches, 2 compilations, 29 s |

Each figure is at the size its own row names — the compile figures at one
batch size on the grid, the warm batch at the grid's widest. The warm-batch
row is the million-policy run's, where fifteen of sixteen batches are full;
`scaling.md`'s column is the median over *every* batch of a run, so the
hundred-thousand row averages a 65,536 batch with a 34,464 one and is not a
figure about either size. The cold and cached figures are each taken in a
*fresh interpreter* over a cache directory that starts empty: XLA reads that
location when it first compiles and never again, so both cannot be measured
in one process.

**Against Polars.** At 10,000 level-4 policies a whole run is 3.5 s here
against 3.1 s for `gspio run-model` there (level 5: 3.8 s against 3.4 s), of
which the compiled region is 0.19 s; the rest is building the columns and
writing them. The two are not measured alike — the figure here runs from
reading the document to the rename, in process, and the Polars one is a
fresh command — so read them as close rather than as a ranking. The hundred
thousand and million-policy rows measure the region pass alone, the
projection's own cost; a whole run at those sizes publishes too, as the
publication paragraph above measures.
