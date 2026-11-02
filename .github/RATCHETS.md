# Ratchets and instruments

What this repository measures about itself, how to reproduce every number, and
which of them can fail a build.

A **ratchet** is a measured figure that moves in one direction only. Most of
them are ceilings: the check fails when the count goes *above* the recorded
number, never on today's state, so adopting one costs nothing on the day it
lands and everything it is worth on the day something regresses. When work
removes violations, lower the ceiling in the same commit — otherwise the
ground it recovered is quietly available to the next regression. Raising one
is allowed and is meant to be conspicuous: a line in the diff with a reason
beside it.

Two of them are **floors**, and they are the denominators. A count of errors
says nothing on its own about how much was counted: narrow the scope of a type
checker and its count falls, and a step reading only the count reports the
fall as ground gained. The floors record how much of the package each count
has to have been taken over. They move the opposite way — up as the package
grows, down only in the commit that genuinely removes source files, with the
reason beside it.

Two more are **digests**, and they ratchet in no direction, because they are
not counts. A floor is one of two conditions a count must meet before it is
comparable with its ceiling, not the only one. Scope is one of two ways to
empty a count without touching a line of source; the other is to stop a
diagnostic being raised, which moves neither the count's ceiling nor its
denominator. The digests record the settings each count was taken under, and
what is enforced is content identity rather than a number — the same as the
duplication baseline below. They are replaced, not raised or lowered, in the
commit that changes the settings, alongside a re-measurement of the ceiling
and floor beside them.

An **instrument** is a number nobody enforces. It is read at a release, or
when choosing what to work on next, and it never fails a build. Instruments
are here because a measurement you have to reinvent is a measurement you stop
taking.

Every number below is the one measured by the change that last moved it, with
the command that measures it printed beside it. Re-run the command to check
the number is still true. A figure here with no command beside it is a defect
in this document, not a fact — it is exactly the thing nobody can check.

---

## Ratchets (CI, `.github/workflows/CI.yml`)

The ceilings, floors and digests live in
[`.github/ratchets.env`](ratchets.env), sourced by the steps that enforce them,
so they are in one place and the workflow does not restate them.

### The engine's lanes

The **JAX Engine** workflow in [`workflows/jax.yml`](workflows/jax.yml) runs
Linux/Python 3.12 against the engine lock and against an upgrade to the current
JAX release. Both rows print their actual interpreter, package versions,
platform and extension path and SHA256. Coincident versions mean two runs of
one version. The core and engine environments install the same freshly built
core wheel; live tutorial references run through the separate core CLI.

Ruff lint and formatting, mypy strict, and pyright standard must all be clean.
There is no allowance for the new package and no ceiling to raise. Reproduce
from `engines/jax` with its environment already installed:

```bash
.venv/bin/ruff check src tests bench
.venv/bin/ruff format --check src tests bench
.venv/bin/mypy src
.venv/bin/pyright src
.venv/bin/python -m pytest -q
```

[`../engines/jax/agreement.json`](../engines/jax/agreement.json) is the only
home of observed agreement ratios, by identifier and by model. The engine
suite checks them under the specification's agreement rule (section 11.1.12:
two engines agree on a line to 1e-12 of its scale), keeping the strict
comparison beside it. A ratio
may worsen only with the reason beside the value in the same change; the
agreement rule itself does not move. Coverage is generated from runtime
capabilities and vector expectations name individual outcomes. A refusal for
another cause, or a case the adapter cannot form, earns no conformance claim.

The core's existing ceilings and clone baseline remain in force, including
`engines/jax/src` in the clone scan. Neither of the lane's environments builds
the core from the checkout. The Polars reference installs the core lock's
dependencies with `uv sync --locked --no-install-project`, so a stale core
lock fails here as it does in the Python tests, and then the lane's one core
wheel with `--no-deps`. The engine's environment is `bootstrap.sh`: the engine
lock with `--no-install-package gaspatchio`, then the same wheel.

Each section below whose value *is* one of those recorded values carries a
`<!-- ratchet: NAME -->` anchor above its heading, and
`bindings/python/tests/test_ratchet_documents_agree.py` reads it: the value in
the heading and the expected output in the first command block under it must
both equal the recorded value, in both directions. That holds for a digest
exactly as it holds for a figure — a sixty-four character heading is a price
worth paying for a value nothing else can check. Keep the anchor with the
heading if either moves. Nothing else in a section is read, so each section
below states what its value measures, why it sits where it does and how to move
it, and leaves the history of how it got there to the commits that moved it.

<!-- ratchet: RUFF_MAX -->
### Ruff violations — `80`

Job: **Measurement Ratchets**, step "Ruff violations are not above their
baseline". Run from `bindings/python`:

```bash
.venv/bin/ruff check gaspatchio            # ruff 0.16.3 -> "Found 80 errors."
```

**What it counts.** Every violation ruff reports over the package under the
declared configuration in `bindings/python/pyproject.toml` — `select = ["ALL"]`,
less the ignores listed there — with file-level `# ruff: noqa: …` headers and
inline `noqa` comments honoured. It counts what ruff reports, not what it would
report unsuppressed. Eight files carry a file-level header: seven modules
(`cli.py`, `accessors/projection.py`, `frame/base.py`,
`column/expression_proxy.py`, `assumptions/_api.py`,
`scenarios/_with_scenarios.py`, `scenarios/_config.py`) and one stub
(`__init__.pyi`).

**Why it sits at 80.** It is the count measured by the change that last
lowered it. Every finding a mechanical fix could clear is cleared, and every
finding that needed a decision was either fixed or kept with an inline `noqa`
naming the fact that makes the rule not apply (the import cycle, the optional
dependency, the protocol that fixes a signature) — never a bare "intentional".
What remains is public-API shape (boolean positional arguments, which only a
breaking change removes), complexity limits (refactors), and the few findings
whose fix would change what a user sees. It falls as work touches them.

**How to move it.** When a change removes violations, lower `RUFF_MAX` in
`.github/ratchets.env` and this heading in the same commit; the step prints a
notice when the count falls below the ceiling. Raise it only with the reason
beside it in `ratchets.env`. The raise to expect is a file-level header coming
off a file: it exposes the violations it was hiding, so the count rises in the
commit that removes it, and that commit says so. Headers come off one file at
a time, never in bulk.

CI resolves ruff's version from the `ruff==` pin in
`bindings/python/pyproject.toml` rather than repeating it, because the count
is only reproducible against one version of the rule set.

<!-- ratchet: CLIPPY_MAX -->
### Clippy warnings — `36`

Job: **Clippy Warning Ratchet**, step "Clippy warnings are not above their
baseline". Run from the repository root:

```bash
cargo clippy --workspace --all-targets --message-format=json > clippy.json
python3 -c '
import json, sys
n = 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line.startswith("{"):
        continue
    message = json.loads(line).get("message")
    if not isinstance(message, dict) or message.get("level") != "warning":
        continue
    if (message.get("code") or {}).get("code"):
        n += 1
print(n)
' clippy.json                              # -> 36
```

**What it counts.** Clippy and rustc warnings across the Rust workspace, all
targets, counted as diagnostics that carry a lint code; the "N warnings
emitted" summaries have no code and are not counted twice. The 36 are 34 in
the core crate and 2 in the Python binding crate, and the binding's two are
one site: a `too_many_arguments` on its internal registration function,
reported once for the library and once for its tests, and left visible rather
than suppressed.

**Why it sits at 36.** It is the count measured on toolchain 1.94.0 by the
change that last lowered it.

**How to move it.** Lower it in the commit that removes warnings, and raise it
only with the reason beside it. The job pins toolchain **1.94.0**, the one this
number was measured on: a newer stable can add lints, and a count that moves
when nobody changed code is not a ratchet. Bumping the toolchain is a
deliberate act, and the same commit re-measures this number. The `rust-tests`
job stays on `stable`; compiling against the current compiler is its job, not
this one's. Not `-D warnings`, deliberately: that demands a mass fix in one go,
which is the opposite of a burn-down.

The step ships this counting rule with one guard around it. Skipping non-JSON
lines is right for cargo's chatter, but it also lets an empty or plain-text
`clippy.json` count cleanly to zero, and zero is under every ceiling, so the
step counts the cargo records it parsed and fails when there are none: a
clippy that did not run cannot present itself as a clippy that found nothing.
Every ratchet step also refuses to run at all if its ceiling is missing or is
not a whole number — `[ 5 -gt "" ]` exits 2, which `if` reads as false, so an
unset variable would otherwise pass a real regression while printing an empty
ceiling.

<!-- ratchet: MYPY_MAX -->
### Mypy errors — `0`

Job: **Measurement Ratchets**, step "Mypy errors are not above their
baseline". Run from `bindings/python`:

```bash
.venv/bin/python -m mypy gaspatchio \
  | sed -n -e 's/^Found \([0-9]*\) errors.*/\1/p' -e 's/^Success: no issues found.*/0/p'
# -> 0
```

**What it counts.** Errors under the strict configuration in
`bindings/python/pyproject.toml`, across the package, with its `exclude` list
honoured. The `sed` is the same extraction the step performs, reading a clean
run's summary as zero; without it the line reads `Success: no issues found in
232 source files`. The count
comes off that summary line rather than out of `--output=json`, and that is
what makes the step fail closed: the JSON carries no summary, so an empty JSON
file counts cleanly to zero, and zero is under any ceiling. mypy prints one of
`Found N errors …` or `Success: no issues found …` whenever it completes and
neither when it does not, so requiring one of them is the guard.

The step needs the third-party packages installed, and that is not
belt-and-braces. With them absent the count does not fall, it rises:
`ignore_missing_imports` turns each unresolved import into `Any`, and under
`strict = true` every `# type: ignore` that no longer suppresses anything comes
back as `unused-ignore`, while every decorator that became `Any` raises
`untyped-decorator`. A dependency-less run is a different measurement, and it
would fail this ceiling on every green commit.

**Why it exists, and why it sits at 0.** `bindings/python/AGENTS.md` governs
type errors with a per-change rule — the files in your diff gain no new errors
— and that rule is right, but it reads a diff and cannot see the whole
package's count move. This ceiling answers that second question. Since
2026-10-04 the package type-checks clean in strict mode, so the ceiling is
zero: any error is a regression, not ground still to win.

**How to move it.** Lower it, here and in `ratchets.env`, in the commit that
removes errors; raise it only with the reason beside it. A fall means
something only if the floor below held and the settings digest did not move,
so the step checks both before it compares the count.

<!-- ratchet: MYPY_MIN_FILES -->
#### Source files mypy must have checked — `254`

The denominator for the ceiling above: how much of the package the count has
to have been taken over before it is comparable with `MYPY_MAX` at all. Run
from `bindings/python`:

```bash
.venv/bin/python -m mypy gaspatchio | sed -n 's/.* \([0-9]*\) source files.*/\1/p'
# -> 254
```

The `sed` reads the file total out of whichever summary line mypy printed —
both the `Found …` and the `Success: no issues found …` shapes carry it.

**What it closes.** A ratchet that counts errors without counting what it
counted is sampling whatever happened to be in scope. Widen `exclude` by one
directory and the count falls; with no floor, the step would report that fall
as ground gained and invite the next commit to lower `MYPY_MAX` to it. With the
floor in place a narrowed run fails, and so does `Success: no issues found in
0 source files`. A run that checks nothing at all prints `There are no .py[i]
files in directory 'gaspatchio'` and no summary line, and the step refuses to
report a count for a run that did not finish. The step checks the floor
*before* the ceiling, so a narrowed run never reaches the comparison. mypy has
a third summary shape, printed when a blocking error stops it early —
`(errors prevented further checking)` stands where the file total would be —
and a run that stopped early is a run over an unknown fraction of the package,
so the step names it and refuses rather than counting it.

**Why it sits at 254.** It is the number of source files the run checks: every
module under `gaspatchio/` outside the `exclude` list, with a stub checked
*instead of* the module it sits beside. That is why this figure is smaller
than pyright's below rather than in conflict with it.

**How to move it.** Up in the commit that adds source, and down only in the
commit that deletes it, with the reason beside it in `ratchets.env`. Deleting a
module moves the two floors by different amounts, so work the number out
rather than copying the other one: a module with no stub beside it is −1 here
and −1 on `PYRIGHT_MIN_FILES`, but a module deleted together with the stub
that shadows it is −1 here and −2 there. The step says so when it fires.

<!-- ratchet: MYPY_SUPPRESSION_SHA -->
#### Settings mypy's two figures were measured under — `67afd8f9332c3914fc71a888f64dafa7a5405fe27001cdbd0e040e0513dd8544`

Job: **Measurement Ratchets**, step "Type-checker settings are the ones the
counts were measured under", which runs before both type-checking steps. Run
from `bindings/python`:

```bash
.venv/bin/python ../../.github/type_suppression_fingerprint.py mypy
# -> 67afd8f9332c3914fc71a888f64dafa7a5405fe27001cdbd0e040e0513dd8544
```

Add `--document` to print the JSON that was hashed.

**What it closes.** `exclude` is not the only lever that empties a count; it
is only the one that moves a denominator. Four lines appended to
`bindings/python/pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "gaspatchio.*"
ignore_errors = true
```

→ `Success: no issues found`, with the file total exactly where the floor
wants it: the count is 0, the step would exit 0 and print its invitation to
lower `MYPY_MAX`, and nothing was narrowed. `disable_error_code` naming a few
codes empties part of it by the same route. The floor cannot see either, and
this digest does.

**What is hashed: mypy's own resolution, not the file.**
`mypy.main.process_options` is the function `mypy` calls before it checks
anything, so the document is the configuration mypy read — out of whichever
file mypy chose to read it from. That is worth more than parsing
`[tool.mypy]`: mypy prefers `mypy.ini` and `.mypy.ini` to `pyproject.toml`, so
a digest over the TOML alone would not see a `mypy.ini` dropped in beside it,
and this one does.

The document is every key of mypy's options snapshot **except** a named few —
a deny-list, not an allow-list. An allow-list is the more precise instrument
and the wrong one here: it stops covering a setting silently the day a release
adds or renames one, and a guard that quietly narrows is the failure this page
exists to record. The price of a deny-list is a digest that also moves on a
setting nobody would call a suppression, and that price is one line in
`ratchets.env` with a reason beside it, which every figure here already asks
for.

**What it does not cover**, stated plainly, because a guard claiming more than
it enforces is worse than one that says where it stops:

- **Scope.** `exclude` and `exclude_gitignore` are out. `MYPY_MIN_FILES` is
  the guard, and two guards answering for one thing is how a gap gets left
  between them. The floor is a floor and not an equality, so widening
  `exclude` while adding source elsewhere is still not caught by either.
- **The host.** `python_executable` is dropped and `platform` is reduced to
  *whether it was overridden at all* rather than which platform it is,
  because CI and a keyboard disagree about both, and a digest they disagree
  about is worth no more than a ceiling they disagree about. Pinning
  `platform` in configuration therefore does move the digest; the value it is
  pinned to does not.
- **The tool version.** `uv.lock` pins mypy and `uv sync --locked` installs
  it, and a bump re-measures the ceiling and the floor anyway.
- **The command line.** `files`, `modules`, `packages` and `verbosity` follow
  the invocation, and the invocation belongs to the workflow step, which is in
  the diff like everything else.

**How to move it.** Replace it, never raise or lower it: in the commit that
changes the settings, with `MYPY_MAX` and `MYPY_MIN_FILES` re-measured under the
new ones beside it.

<!-- ratchet: PYRIGHT_MAX -->
### Pyright errors — `0`

Job: **Measurement Ratchets**, step "Pyright errors are not above their
baseline". Run from `bindings/python`:

```bash
.venv/bin/python -m pyright gaspatchio --outputjson \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["summary"]["errorCount"])'
# -> 0
```

**What it counts.** Errors only; the same run reports one warning, which
nothing counts. `--outputjson` is also what makes the step fail closed:
pyright puts the summary in the document, and a pyright that did not run
writes no parseable document. The file total in that same summary is the floor
below.

**Configured before it is measured, on purpose.** An unconfigured pyright
reports the environment it found as much as the package it was pointed at: it
takes both the language level and the third-party search path from whichever
Python environment it discovers, and what it discovers depends on the shell.
When the configuration was written, the same tree read 895 errors unconfigured
with `.venv/bin` off `PATH` and 245 with it on — and 120 either way as
configured. A number CI and a keyboard can disagree about is not a ceiling
anyone can argue with, so `[tool.pyright]` in `bindings/python/pyproject.toml`
names the language level and the virtualenv, writes `typeCheckingMode =
"standard"` down rather than inheriting it, and adopts mypy's `exclude` list,
so both ceilings answer for the same files. No key in it silences a
diagnostic. The tutorials it excludes are standalone example scripts that
`gspio tutorial init` copies into a user's own directory, which mypy has never
checked either.

**Why it sits at 0.** The package has type-checked clean since 2026-10-04,
so any error is a regression; the count is taken under pyright **1.1.411**, which `bindings/python/uv.lock` pins and
`uv sync --locked` installs.

**How to move it.** Lower it in the commit that removes errors, here and in
`ratchets.env`; raise it only with the reason beside it. As for mypy, the
floor and the settings digest are checked first.

<!-- ratchet: PYRIGHT_MIN_FILES -->
#### Files pyright must have analysed — `274`

The denominator for the ceiling above, on the same argument as
`MYPY_MIN_FILES`. Run from `bindings/python`:

```bash
.venv/bin/python -m pyright gaspatchio --outputjson \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["summary"]["filesAnalyzed"])'
# -> 274
```

Read out of the same document as the count, so the floor and the number it
qualifies come from one run. A run that analysed zero files is the extreme of
this comparison rather than a case of its own.

**Why it sits at 274.** It is every `.py` and `.pyi` under `gaspatchio/`
outside the `exclude` list. Pyright analyses both members of a module/stub
pair where mypy checks only the stub, which is the difference from mypy's 254
and the reason a module deleted with its stub takes −2 off this floor where it
takes −1 off that one.

**How to move it.** As for `MYPY_MIN_FILES`: up with added source, down only
with deleted source, with the reason beside it.

<!-- ratchet: PYRIGHT_SUPPRESSION_SHA -->
#### Settings pyright's two figures were measured under — `a94c7167b52aa4fa16ef6cb1513b18235dd6a67834a46892d971d0750429a63b`

Job: **Measurement Ratchets**, step "Type-checker settings are the ones the
counts were measured under". Run from `bindings/python`:

```bash
.venv/bin/python ../../.github/type_suppression_fingerprint.py pyright
# -> a94c7167b52aa4fa16ef6cb1513b18235dd6a67834a46892d971d0750429a63b
```

Add `--document` to print the JSON that was hashed. The argument is
`MYPY_SUPPRESSION_SHA`'s, and pyright's version of the hole is `ignore`: it
suppresses diagnostics in the paths it names while leaving `filesAnalyzed`
untouched, so `PYRIGHT_MIN_FILES` cannot see it and this is the only recorded
value that can. `ignore` is inside the digest for that reason; `exclude` is
outside it, because that is the floor's job.

**What is hashed: the file, because pyright will not report itself.** This is
the one asymmetry with mypy above, and it is not a preference. `--verbose`
prints pyright's search paths and its language level and stops there;
`--outputjson` carries the summary and the diagnostics and nothing about the
rule set; there is no flag that dumps the effective configuration. So the
document is `[tool.pyright]` as parsed out of
`bindings/python/pyproject.toml`, minus `include` and `exclude`.

The one thing that costs is bought back rather than left as a blind spot: the
document also records **whether a `pyrightconfig.json` exists** in
`bindings/python`, because pyright reads that *instead of* `pyproject.toml`.
A digest over a file the tool has stopped reading is the same class of defect
as a count over a package the tool has stopped checking.

**What it does not cover.** Scope, the host and the tool version, exactly as
for mypy above — plus one more, which is the cost of reading a file rather
than a resolution: this digest sees a setting only where pyright's own
precedence rules say pyright will look, which is why the two config-file
locations are recorded rather than assumed. Rule severities that
`typeCheckingMode` decides are covered only through that key, so the mode is
what has to hold.

**How to move it.** Replace it in the commit that changes the settings, with
`PYRIGHT_MAX` and `PYRIGHT_MIN_FILES` re-measured under the new ones.

### Duplicate clones — a fingerprint baseline, not a count

**This heading carries no figure, deliberately.** What the step enforces is
not a count, so there is no `NAME=<integer>` for it in
[`.github/ratchets.env`](ratchets.env) and nothing that could hold a figure in
this heading to one. The clone count is in the command's own output, where a
reader can reproduce it.

Job: **Measurement Ratchets**, step "No duplicate clones outside the
baseline". Run from the repository root:

```bash
bash scripts/check-clones.sh
```

The script is the sole scan definition, and CI runs it exactly as above: the
core's Python, Rust and JAX source (`bindings/python/gaspatchio`, `core/src`,
`engines/jax/src`); jscpd 5.1.2 at 12 lines and 70 tokens; the tutorials,
bytecode caches, conformance vectors and conformance kit left out; and the
fingerprint baseline. `bindings/python/tests/test_jscpd_ignore_agrees.py`
holds CI and this page to the script. Read on 2026-09-30: 267 files, 127,920
lines, **51 clones, 838 duplicated lines (0.66%), zero new clones**.

Two things are left out on purpose. The conformance vectors and their index
are near-identical by construction — each records the same envelope around a
different case — so counting them would measure the fixture format rather
than the code. And `column/_generated_proxy.py` carries generated
`jscpd:ignore-start/end` markers: it is regenerated from
`_semantic/operations.py`, which stays scanned, and an exact-regeneration test
guards every byte of it, so its copies of that file's docstrings are not
authored duplication.

The ratchet is keyed on content fingerprints, not counts or line numbers:
[`.github/jscpd-baseline.json`](jscpd-baseline.json) maps each known clone's
fingerprint to how many times it occurs, and `--fail-on-new-clones` fails only
on a clone whose fingerprint is not in it. Moving a known clone is not an
event; adding one is. Rewrite the file when a clone is genuinely removed, or
when a new one is deliberately accepted:

```bash
npx --yes jscpd@5.1.2 … --baseline .github/jscpd-baseline.json --update-baseline
```

The version pin is not decoration: `--baseline` does not exist before jscpd
5.x, and fingerprints are only comparable against the detector that produced
them.

### Census allowlist totals — `34` / `124` / `113`

Enforced by `tests/graph/census.py::test_allowlist_totals_do_not_grow`, in the
normal Python suite rather than in a job of its own. Run from
`bindings/python`:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0, '');
from tests.graph.census import _allowlist_entry_counts as c; print(c())"
# -> {'ALLOWLIST': 34, 'ACCESSOR_METHOD_ALLOWLIST': 124,
#     'EXPR_RETURNING_DEF_ALLOWLIST': 113}
```

**What it counts.** The census asserts that every expression-producing site in
the package is accounted for, which an allowlist entry silences the moment it
is added. The totals answer the second question: how many sites are still
being accounted for that way. Three numbers rather than one sum, because the
three structures empty out on different work:

- `ALLOWLIST` holds raw sites — a `pl.col(` or an `ActuarialFrame(` in a file
  where it is not a model's expression, such as the filters the export runs
  over its own row stamp to find a selected policy again.
- `ACCESSOR_METHOD_ALLOWLIST` holds the public accessor-family names, so each
  entry is public surface made visible; `polars_native`, the named escape out
  of the operation vocabulary, is one.
- `EXPR_RETURNING_DEF_ALLOWLIST` holds the definitions whose declared return
  is an expression.

The two name-keyed lists are keyed on method *names*, so a body moving into
`frame/lowering/` does not move them.

**How to move them.** Down whenever entries come off. Up only as a reviewed
addition, in the commit that needs it, saying what the entry is and why it
cannot be avoided; a new generated method on the proxy surface is capability
growth and is recorded the same way. The ceilings live in
`ALLOWLIST_CEILINGS` in `tests/graph/census.py`, not in `ratchets.env`, which
is why this section has its own name rather than a `ratchet:` anchor;
`tests/test_ratchet_documents_agree.py` checks this heading and the output
above against those ceilings, and the census suite checks the actual counts.

### Import layering contracts — all nine enforced

Job: **Measurement Ratchets**, step "Import architecture boundaries". Run from
`bindings/python`:

```bash
PYTHONPATH=. uvx --from import-linter==2.15 lint-imports --config .importlinter
# -> Contracts: 9 kept, 0 broken.
```

The nine contracts in `bindings/python/.importlinter`:

- engine protocol and reports do not depend on model execution;
- source and schema metadata do not depend on their consumers;
- the calc graph does not import the error surface;
- lowering sits below the accessors and proxies that call it;
- Polars primitives do not depend on model authoring;
- call recognition does not depend on an engine or authoring;
- and neither the graph modules, the lowering modules nor `frame`'s own
  modules import each other in cycles.

CI runs the whole configuration, and no indirect or type-only import is
exempted. These are static import boundaries, not a claim that the runtime is
free from every form of coupling.

---

## Ratchets (Viewer, `.github/workflows/viewer.yml`)

The reader's workspace has a lane of its own, because GitHub filters paths on
a workflow's trigger rather than on one job of many and nothing here should
run on a Python-only change. Its ceiling lives in the same
[`.github/ratchets.env`](ratchets.env) as every other, is read with the same
three refusal patterns, and carries the same `<!-- ratchet: NAME -->` anchor,
so `bindings/python/tests/test_ratchet_documents_agree.py` holds this section
to that file exactly as it holds the ones above.

<!-- ratchet: VIEWER_BUNDLE_GZIP_MAX -->
### The reader's bundle, gzipped — `197735`

Job: **Viewer (Node)**, step "The bundle's gzip size is not above its
ceiling". Run from `viewer`:

```bash
npm ci && node build.mjs   # on Node 24.21.0; prints jsBytes, cssBytes and the figure below
# -> 197735
```

**What it counts.** `viewer/dist/viewer.js` and `viewer/dist/viewer.css`
together, at gzip level 9 — what a browser is asked to hold when somebody
opens an exported page. The artifact inlined beside them is the larger half of
that file and is deliberately not counted: its size is the model's, it moves
with every export, and a ceiling over it would be a ceiling over somebody
else's data.

**Why it sits at 197735.** The ceiling is written at exactly the size Node
24.21.0 builds — 596,395 JavaScript bytes and 38,088 CSS bytes before
compression — so no capability lands without this line moving. It was measured
by hand on macOS with that Node, which gives the Viewer job's own figure for
the tree before it byte for byte. It was raised by 90 bytes for the grid
drawing its rows in blocks (99, less 9 the commits before it freed), by 4 for its rows painting on their own, by
141 for the cursor's row landing inside what a reader can see, by 56 for
the comparison page's advice on two uncompared books naming the call a Python
export names its files with, by 438 for the comparison page reading the
results file each run recorded, as `gspio diff` does, by 444 for the page
naming a cause for a moved value only where the record does, and by 577 for
keying that cause on the book alone and reading a move within section
11.1.12's tolerance as agreement, and by 1,394 for the tier census in the
Audit View, the row labels sticking as one column and a label for each side
of a comparison, and by 432 for the comparison page saying which advice
applies when the results files differ, as `gspio diff` does, and by 1,898
for the reader showing every member the audit record carries -- the model's
own files, the library versions, why git is not recorded, a table's source
and shaping, and every digit of a selected cell, and by 344 for the comparison page
naming a library that moved under one release, and by 139 for the Model
tab showing the formulas fingerprint beside the graph fingerprint, and by 511 for a
read's period window drawn the way its offset is, and by 1,471 for the comparison page
showing how far each change moved over the whole book, less 105 when
the page stopped refusing a pair gspio diff compares, and by 1,327 for the
comparison page naming a moved hole, the lines under it and the model's own
files, and by 515 for a cheaper period step on the comparison page's
scrub, which missed its frame budget on slow runners; what they
bought is beside the value in `ratchets.env`. The figure is Node's as much as
the bundle's: zlib's output moves between Node releases and platforms, and a
Mac on Node 24.3.0 compresses the same bytes to 190,899. The lane therefore
pins its Node exactly, and CI's figure is the gate; a figure measured by hand
elsewhere can differ by a few hundred bytes.

**How to move it.** Take the bytes back out, or, if a capability earned them,
raise it in the same commit, in both `ratchets.env` and this heading, with
what the bytes bought beside it in `ratchets.env`. Lower it when bytes come
out. It is dependency-bound, the way the ruff and clippy ceilings are
toolchain-bound: React, React Flow, dagre and the virtualiser are the bulk of
these bytes, esbuild decides how they are minified, and all of them are pinned
in `viewer/package-lock.json`. The lane installs from that lockfile, so a
figure that moves with nothing touched under `viewer/src` is a dependency
moving, and the commit that moves it re-measures this number. A Node bump
does the same: raise `node-version` in `viewer.yml` and `CI.yml` and
re-measure this line in one commit.

### Frame times — enforced

`viewer/perf/measure.mjs` takes them and `viewer/perf/check.mjs` judges them
against the viewer's frame budget: a 95th-percentile frame under 33 ms on pan,
zoom and scrub, and a cold open under one second. The scrub is measured three
times — in the default layout, with the cone expanded across the whole pane
area, and on the two-document comparison page — and one budget judges all
three: a period step is the one interaction whose cost grows with how much is
being drawn at once. Run from `viewer`:

```bash
node pack.mjs level4 && node pack.mjs compare-after --second compare-before && npm run perf
```

Not a ratchet: the budget is the design's and nothing here moves it. The
lane's step "Frame times are inside the budget" enforces it, and a step that
stops passing is fixed in the page, never in the threshold.

What is judged is the median of the three timed runs' 95th percentiles, not
the percentile of all their frames pooled. Frames arrive on the display's
16.7 ms tick, so one missed tick reads as 33.3 ms and the budget amounts to no
more than one frame in twenty missing a tick. On the shared 2-core runner one
run in three could lose that alone — the step failed three times on unchanged
viewer code (on 2026-10-08, the scrub at 33.3 and the comparison scrub at 33.4)
before this rule — and pooled, that one run decided the answer. A page that is
really slower is slower in every run and still fails; the budget did not move.

A page can be over the budget on a runner slower than the machine at hand, as
this one was on a 2-core CI runner. `measure.mjs` slows the
page's CPU by the rate `VIEWER_PERF_CPU_THROTTLE` names; unset, it measures the
machine as it is, which is all CI does. On the development Mac, 1.25 is the
rate that reproduces that runner:

```bash
VIEWER_PERF_CPU_THROTTLE=1.25 npm run perf
```

Last read on 2026-09-29 over the level-4 export and its comparison page, on
the development Mac. Natively, every interaction at a 95th-percentile frame of
16.8 ms or under and a cold open of 409.1 ms; at 1.25, the scrub at 16.7 ms
with 1 of 249 frames over and scrubCompare at 16.8 with none, where the tree
before read 33.3 and 33.4 there. The frame-time step's comments in
`viewer.yml` carry the table at 1.5 and 2 beside it.

---

## Performance (CI, `.github/workflows/bench-pr.yml`)

Not a ratchet — there is no recorded number here to raise, and nothing in this
file to keep in step with one. It is written down because it is the other
thing that can fail a pull request. On a PR touching `core/**`, `bench-pr.yml`
runs `realistic_vector_lookup` at 1,000 and 10,000 policies (the `.*1000.*`
filter matches both) beside its `assumption_table_lookup_benchmark` filter —
the target `core/AGENTS.md` calls authoritative for lookup performance — and
compares both against the last point pushed to `gh-pages` under `dev/bench`.
A case 1.3x slower than that point is commented on; a case 1.5x slower fails
the PR. A case with no point of the same name in the previous entry is
skipped, so adding a benchmark never reds the PR that adds it.

---

## Instruments (local, per release — these never fail a build)

Each is read at a release, or when choosing what to work on next, and the
reading under each command is the latest, with its date. Tools run
ephemerally through `uvx`/`npx`; none needs installation into the project
environment.

### Cognitive complexity — 60 functions over 15

Run from `bindings/python`:

```bash
uvx --from complexipy==8.0.1 complexipy gaspatchio -e "**/tutorials/**" \
  --output-format json --output complexipy.json --quiet   # complexipy 8.0.1
python3 -c "import json; d=json.load(open('complexipy.json'));
print(len(d), 'functions,', sum(1 for f in d if f['complexity'] > 15), 'over 15')"
# -> 2425 functions, 60 over 15
```

Read on 2026-09-29. The highest five:
`examples/docstrings/models.py::GaspatchioDocstring::validate_structure` (51),
`examples/docstrings/pytest_plugin.py::DocstringExampleItem::repr_failure`
(44), `scenarios/_for_each.py::for_each_scenario` (44),
`scenarios/_config.py::parse_shock_config` (43) and
`assumptions/_api.py::Table::_process_data` (40).

complexipy is used for two properties rather than for the metric: it is immune
to `# noqa`, where ruff's own complexity rule is not, and `--diff` gives a
per-change comparison. The suppression gap, from `bindings/python` with the
pinned ruff:

```bash
.venv/bin/ruff check gaspatchio --select C901                 # -> "Found 7 errors."
.venv/bin/ruff check gaspatchio --select C901 --ignore-noqa   # -> "Found 17 errors."
```

Ten of C901's seventeen hits are suppressed, leaving seven reported — and a
rule you can silence per line is not a measurement of the codebase. That is
the argument for complexipy here; it is not a claim that cognitive complexity
is the better metric. Cognitive and cyclomatic complexity barely differ on this
codebase, so the tooling is the reason to prefer it.

### Public API surface — 3,036 objects, against 50 in `__all__`

Run from `bindings/python`:

```bash
uvx griffe dump gaspatchio -s . -f -o api.json          # griffe 2.3.0
python3 -c "
import json, collections
kinds = collections.Counter()
def walk(node, path):
    if not isinstance(node, dict):
        return
    if node.get('kind') and node.get('is_public') is True and 'tutorials' not in path:
        kinds[node['kind']] += 1
    members = node.get('members')
    for name, member in (members or {}).items() if isinstance(members, dict) else ():
        walk(member, path + '.' + name)
for top, node in json.load(open('api.json')).items():
    walk(node, top)
print(kinds, 'total', sum(kinds.values()), 'ex-aliases', sum(kinds.values()) - kinds['alias'])
"
# -> function 1324, attribute 1268, class 295, alias 341, module 146, type alias 3
#    total 3377, ex-aliases 3036
```

Read on 2026-10-08, at the 1.0.0 candidate. It fell from 3,188 when four package stubs
that redeclared their modules' names were deleted, so each name is counted once,
where it is defined. `-f/--full` matters: only then does every member carry an
explicit `is_public`. No build of the extension is needed — griffe reads the
source.

The gap between 3,036 reachable public objects and the 50 names in top-level
`__all__` is not code waiting to be deleted; it is code that is public *by
default* rather than public *by intent*. Every module the API reference
documents now declares its public names in `__all__` -- 576 names across 61
public modules, the top level among them -- so what is public by intent can
be read off the package; what remains public only by default is the rest. The cheapest reduction in surface
area available here is therefore marking internals private and declaring
`__all__`, and this number is what makes that visible.

### Honest size, and net change per release

Run from the repository root:

```bash
npx --yes cloc core/src bindings/python/gaspatchio \
  --exclude-dir=__pycache__,tutorials                  # cloc 2.06
# -> Python 246 files, 45,364 comment, 45,801 code
#    Rust    24 files,  2,699 comment, 11,892 code

npx --yes cloc --git --diff v0.9.0 HEAD --include-lang=Python,Rust
# -> Python: added 106,001 code / removed 8,121 / modified 4,127
#    Rust:   added   3,572 code / removed   313 / modified   232
```

Read on 2026-10-08, at the 1.0.0 candidate, the second against the previous
release's tag. About half
of the package's Python lines are docstrings and comments, and they are
load-bearing — the docstrings are doctests and the retrieval surface — so a
raw line count would show documentation work as the codebase "growing".
Separating code from comments is what makes a net-negative claim checkable
rather than rhetorical.

### Hotspots — churn × complexity, for choosing targets

Run from the repository root:

```bash
uvx --from scc-bin scc --hotspots --cognitive --depth 400 --format json \
    --report-skip cocomo,locomo,files,uloc,linelength,card,coupling,authors,timeline \
    bindings/python/gaspatchio core/src > scc.json          # scc 4.0.0
python3 -c "
import json
files = json.load(open('scc.json'))['files']
for f in sorted(files, key=lambda f: f['codeChurn'] * f['complexity'], reverse=True)[:5]:
    print(f\"{f['codeChurn'] * f['complexity']:>9,d}  {f['file']}\")
"
```

The window is the last 400 commits of the history you run it in. Two things to
know before using the list:

- **Rank on `codeChurn × complexity`, not on scc's own `score`.** scc's JSON
  separates code churn from comment churn, and on this codebase the
  distinction is not cosmetic: much of the churn on the most-edited files is
  documentation, and ranking on the built-in score and ranking on code churn
  order them differently.
- **Churn on young code measures construction, not decay.** A file churns
  because it is being built; an old file that is still churning is the kind
  that means something.

The git-history report runs against the repository, not only the paths given
(scc says so: *"history reports run against a single repository; ignoring
extra paths"*), so a test file can appear on the list. That is information,
not noise — but it is why this is a diagnostic for choosing what to work on,
never a build failure. COCOMO and LOCOMO cost estimates are suppressed in the
invocation above on purpose: a currency figure attached to a codebase is a
number that gets quoted and cannot be defended.

### Places one operation's wording stands in — 200 files, 6 of them generated

Run from `bindings/python`:

```bash
.venv/bin/python scripts/wording_places.py
# -> 98 identifiers, 83 of them found anywhere, 67 in more than one file
#    194 hand-written mentions, 6 generated, 200 in all
```

Read on 2026-09-29. It counts how many files move when one operation's wording
changes. For every identifier in the format's vocabulary it counts the files
carrying that operation's trace sentence or the rule its specification clause
states for a period carrying no value — the sentence itself, and the longest
literal run between a template's fields where that run reaches twenty-four
characters, because a shorter run is ordinary English ("the present value
of", "significant figures") that matches prose about something else. A path
argument reads another checkout with this tree's wording; `--all` lists every
identifier rather than only those standing in more than one file.

The copies are held to each other: a docstring stating a rule its row does not
state fails `tests/graph/test_vocabulary.py`, and a row quoting a rule its
clause does not state fails there too. The search is literal, so a sentence
carrying code spans, which the specification marks with one backtick and a
docstring with two, is under-counted, which is the side this number errs on.
This is a size read at a release and never a build failure — a docstring that
states a rule where a reader needs it is worth the repetition, and the number
is here so the repetition is visible rather than free.

### The suite's wall time — 282 s serial, 143 s on four workers

Run from `bindings/python`:

```bash
# The serial form: what every count and timing figure is quoted against.
.venv/bin/python -m pytest -q \
  --deselect tests/probe/test_probe_emission.py::test_microbench_worker_stdout_is_pure_json
# -> 7897 passed, 3 skipped, 58 deselected, 5 xfailed in 281.71s

# The everyday form. Cap engine threads to the worker count: Polars is already
# multi-threaded, so four workers at the default ask a 16-core laptop for
# 4x16 threads and spend the difference on contention.
POLARS_MAX_THREADS=4 .venv/bin/python -m pytest -q -n 4 \
  --deselect tests/probe/test_probe_emission.py::test_microbench_worker_stdout_is_pure_json
# -> 7897 passed, 3 skipped, 5 xfailed in 143.44s
```

Read on 2026-09-29 on a 16-core MacBookPro16,1 running macOS 15.7.9, with other
work sharing the machine, so read both as upper bounds; a reading from another
machine is that machine's number, not a regression. The serial
form is the one every figure on this page is quoted against, and it stays that
way: `-n` is deliberately absent from `addopts`, so a bare `pytest` in a
checkout someone is reading stays single-process and sprouts no workers it was
not asked for. Nothing in CI runs the four-worker form.

---

## Deliberately absent

Maintainability Index and letter-grade composites (docstrings inflate the
comment ratio, so this repository would score better for the wrong half of a
change), COCOMO cost output, coverage percentage targets (cheapest to raise
with assertion-free tests — a real exposure for a heavily agent-authored
suite), whole-codebase mutation scores (targeted runs only, where a specific
test claim needs teeth), comment-density ratios, raw undifferentiated line
counts, Halstead metrics, and bus-factor reports. Each was considered and
refused for a stated reason; adding one back is a decision to argue, not an
oversight to correct.
