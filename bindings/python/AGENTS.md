# gaspatchio-core / bindings/python — Python development rules

Canonical contributor rules for the PyO3 Python bindings and the actuary-facing API. Read
natively by AI coding agents and by Claude Code via the sibling `CLAUDE.md` import shim.
Applies to all Python under `bindings/python/`.

## API philosophy

**The full account is [`docs/api-philosophy.md`](docs/api-philosophy.md)** — the tension
between convention and control, worked through a production term-insurance model line by
line. It moved there so this file plus the root `AGENTS.md` fit the 32 KiB window Codex
merges them into. Read it before proposing anything that would hide a calculation. The short
form: **simple maths uses operators**
(`af.claims = af.sum_assured * af.pols_death` — the formula is the code, audited by reading
the line); **complex operations use named methods under a domain namespace**
(`.projection.cumulative_survival()`, `.finance.to_monthly()` — verbs stating the intent);
**business logic uses `when/then/otherwise`**, which mirrors Excel's `IF()`. Which rules out
a method that hides the formula (`af.projection.project_cashflows(periods=30)` — *what
formula is that?*): actuaries must audit every calculation for regulatory compliance.

## Development commands

**Never `uv run` pytest, mypy or pyright.** `uv run` re-syncs through the maturin backend,
and `[tool.uv] cache-keys` covers `**/*.rs`, so it rebuilds the extension at `--profile=dev`
before running anything — replacing the parked **release** extension with a **debug** one,
which silently changes test outcomes and invalidates every timing figure in this repository.
CI, [`.github/RATCHETS.md`](../../.github/RATCHETS.md) and `.github/ratchets.env` use the
`.venv/bin/python -m ...` spelling, so four places agree on one command and one count.

```bash
# Build. `develop`, not `build`: a .pth puts this directory on sys.path, so the
# extension has to land in the source tree, and `build` only writes a wheel.
uvx maturin develop --release --uv   # or `maturin develop --release`, venv active
uv sync                              # install all workspace dependencies

# The whole suite, single-process -- what every count and timing figure is
# quoted against. The --deselect is standing: that test asserts a worker's
# stdout is pure JSON and is not stable under this harness.
.venv/bin/python -m pytest \
  --deselect tests/probe/test_probe_emission.py::test_microbench_worker_stdout_is_pure_json

# The edit-run-refine loop. Cap engine threads to the worker count: Polars is
# already multi-threaded, so four workers at the default ask a 16-core laptop
# for 4x16 threads and spend the difference on contention. Add
# --ignore=tests/scenarios/test_aggregator_property.py for a ~1 minute loop.
POLARS_MAX_THREADS=4 .venv/bin/python -m pytest -n 4

# Docstring validation; --accept updates expectations. Serial only, because
# pytest-accept rewrites the files it is checking.
.venv/bin/python -m pytest --doctest-modules --doctest-glob="*.pyi"
.venv/bin/python -m pytest gaspatchio/accessors/excel.py --doctest-modules --accept

.venv/bin/python -m pytest -m "not benchmark"   # skip slow benchmarks
.venv/bin/python -m pytest -m performance       # only performance tests
.venv/bin/python -m mypy gaspatchio
.venv/bin/python -m pyright gaspatchio

# Stub/runtime drift. The relaxed config is required (stubtest builds with mypy
# first and aborts on a build error); the allowlist records the deliberate
# differences. No --ignore-missing-stub: "exists at runtime, missing from stub"
# is a drift class this repo checks for.
.venv/bin/python -m mypy.stubtest gaspatchio \
    --allowlist stubtest-allowlist.txt --mypy-config-file mypy-stubtest.ini

# Model runs. LOGURU_LEVEL=TRACE GASPATCHIO_VERBOSE=true for the full trace.
.venv/bin/gspio run-model model.py data.parquet --output-file results.parquet
.venv/bin/gspio run-model model.py data.parquet --mode debug -r 50
.venv/bin/gspio run-single-policy model.py data.parquet 1 \
    --policy-id-column "Policy number"
```

### Linter behaviour note

**IMPORTANT:** the on-save hook runs `ruff`, which removes unused imports, so add a new
import AND its first use in a **single edit** — split across two, `from loguru import logger`
is stripped before the usage lands.

### Type-checking baseline

Neither checker is clean over the whole package, so passing is not the rule and never was.
What is enforced — a per-change rule (the files in your diff gain no new errors) and a
whole-package ceiling with a floor beside it — is in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md); the live figures and the command reproducing each
are in [`.github/RATCHETS.md`](../../.github/RATCHETS.md) and `.github/ratchets.env`. **Do
not copy a count into this file**: it goes stale here and nothing notices.

One fact belongs here rather than there. Both checkers skip `gaspatchio/tutorials/`, `jobs/`
and `tests/scratch/` via identical `exclude` lists in `pyproject.toml`, so "clean" means the
same files whichever you ask: those trees reuse basenames across sibling directories with no
package markers, and mypy stops at the first duplicate rather than checking anything at all.
The tutorials must **not** gain `__init__.py` to work around it — `gspio tutorial init`
copies them verbatim into a user's own directory, where a package marker would be wrong.

## Architecture

**[`docs/architecture.md`](docs/architecture.md)** maps the package by ownership — for each
layer the question it owns, its canonical source and the symbol that is the door, and where
new work of that kind goes: the authoring surface, operation declarations and the op-tree,
engine lowering, execution and its four routes, the calculation log, the artifact and its
consumers, the rollforward, assumption tables, and the Rust boundary. Four rules stay
here because missing one produces a wrong change, not a slow one:

1. **`_internal.pyi` must match the Rust exports exactly.** `mypy.stubtest` is what catches
   the drift, and "exists at runtime, missing from stub" is not accepted silently.
2. **Docstring examples are tests**, validated by pytest; `--accept` updates them.
3. **Performance warnings are deliberate** — the codebase warns on suboptimal patterns such
   as iterating over policies. Vectorize rather than silence.
4. **Error formatting is a contract**, not decoration: `errors/formatter.py` gives a message
   its context, so preserve the pattern when you add a refusal. (Telemetry, by contrast, is
   optional — Logfire stays dormant until `LOGFIRE_TOKEN` is set.)

## Related repositories

Siblings in a multi-repo checkout: `../../../gaspatchio-docs` (the MkDocs site),
`../../../gaspatchio-models` (example models). Installing the plugin — Claude Code, Copilot,
Cursor, `npx skills` — is in the repository [`README.md`](../../README.md).

## Python Development Standards

### Code style and formatting

- Code arrives **already formatted**; `ruff format` runs in CI, and ruff is configured
  `select = ["ALL"]`, so it lints clean but for the `pyproject.toml` ignores
- **f-strings** for interpolation, **`pathlib.Path`** over `os.path`, **`with`** for resources
- Never `print()` in production code — use the project's `loguru` logger
- Lowercase-with-underscores for directories and files (`utils/data_processor.py`)

### Type hints and data structures

- **Every new function, method, or class carries explicit type hints** (no implicit `Any`)
- Declare a non-`Any` return type; prefer `| None` over `Optional[T]`
- Wrap third-party untyped calls in a small typed helper rather than sprinkling `Any`
- `@dataclass(slots=True)` or `pydantic.BaseModel` for structured data, never an ad-hoc dict

### Patterns, errors, docstrings

- Functional and declarative; classes only for stateful components or clear organization
- Prefer iteration and modularization over duplication; descriptive names with auxiliary
  verbs (`is_valid`, `has_data`)
- Receive an Object, Return an Object: one object parameter in, one object out, Pydantic both
- Handle errors and edge cases at the **beginning** of the function, with early returns, so
  the happy path lands last and nothing nests deeply. No unnecessary `else`
- Loguru for structured logging with context; Pydantic to validate and parse complex inputs
- Docstring rules are in `ref/12-docstring-and-examples/12-docstring-README.md`

### Key dependencies

Pydantic v2 (validation, serialization), Typer (CLI), Polars (data), Loguru (logging),
Pydantic.AI (LLM interactions), uv (packaging — `uv add <package>`; for *running*, see the
spellings above).
