# Gaspatchio (Python)

The Python package for [Gaspatchio](../../README.md) — a high-performance actuarial modeling
framework. You write models in Python that read like spreadsheet formulas, and a Rust + Polars
engine runs them over millions of model points.

📖 **Documentation, tutorials, and full API + CLI reference → [gaspatchio.dev](https://gaspatchio.dev/)**

## Install

```bash
pip install gaspatchio                # or:  uv pip install gaspatchio
pip install "gaspatchio[jax]"         # adds the JAX engine (gaspatchio-jax)
pip install "gaspatchio[viewer]"      # adds the viewer (gaspatchio-viewer), for --html
```

Then `import gaspatchio`. Each extra pins its distribution exactly, and neither is needed to
build or run a model. For a source/dev build, see [Building from source](#building-from-source).

## Quick start

```python
from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

# 1. Load assumption tables (registered + optimized by the Rust engine)
mortality = Table(
    name="mortality",
    source="data/mortality.parquet",
    dimensions={"age": "age", "gender": "sex"},
    value="rate",
)

# 2. Define the model — the formula IS the code
def projection(af: ActuarialFrame) -> ActuarialFrame:
    af.attained_age = af.dob.excel.yearfrac(af.val_date) + af.t      # Excel-compatible date maths
    af.qx = mortality.lookup(age=af.attained_age, gender=af.gender)  # vectorized lookup
    af.pols_if = af.pols_start * (1 - af.qx - af.lapse_rate)         # vectorized projection
    return af

# 3. Run (millions of model points supported)
af = ActuarialFrame(data="model_points.parquet")
result = projection(af).collect()
```

New here? The [tutorials](https://gaspatchio.dev/) build from hello-world to a lifelib-reconciled
model and on to scenarios.

## CLI: `gspio`

Run models from the command line:

```bash
gspio run-model model.py model-points.parquet                  # run all policies
gspio run-single-policy model.py model-points.parquet 12345    # debug one policy (transposed output)
gspio run-model model.py data.parquet --mode optimize          # skip tracing and profiling
gspio --install-completion                                     # shell tab-completion
```

- `--policy-id-column` sets the policy-identifier column (auto-detected if omitted).
- `--mode {debug,optimize}` plus display flags (`--rows/-r`, `--first-n/-f`, `--last-n/-l`,
  `--start-at/-s`) control execution and terminal output.

Use `--results` for calculated values across `run-model`, `run-single-policy`,
`calc-graph` and `run-artifact`. For a review, one export can write the values,
their calculation record and an HTML viewer:

```bash
gspio calc-graph model.py data.parquet \
  --results results.parquet --artifact audit.json --html review.html
```

`--artifact` names the JSON calculation graph; `--html` needs the viewer extra,
`pip install "gaspatchio[viewer]"`.
The graph names its results file by path and content hash. Existing flags keep
their meanings: `--output-file` still names results on the model/export commands;
`--output` and `-o` still name the artifact on `calc-graph`, and results on
`run-artifact`. `-o` also remains a results alias on the two model commands.

Diagnostic mode and execution engine are separate choices. `--mode debug` traces
and profiles the Python model; `--mode optimize` skips that work. Both model
commands use Polars. `run-artifact --engine jax` selects the optional JAX engine,
which `pip install "gaspatchio[jax]"` installs, over an artifact exported with
`calc-graph --profile executable`; JAX configuration selects its device. Choosing
JAX does not itself select a GPU.

**Full CLI reference, with every flag and the single-policy result transposition →
[gaspatchio.dev](https://gaspatchio.dev/).**

## Building from source

The Rust extension is built with [maturin](https://www.maturin.rs/). `uv sync` builds in **debug**
mode (fast compiles); use `--release` for benchmarking/production:

```bash
uv sync                                                             # debug build, into the source tree
uvx maturin develop --release --uv                                  # optimized build
RUSTFLAGS="-C target-cpu=native" uvx maturin develop --release --uv # + native SIMD (AVX2/512)
```

`develop`, not `build`: the venv imports `gaspatchio` from this directory via a `.pth`, so the
extension has to be installed into the source tree — `maturin build` writes a wheel to
`target/wheels` and leaves the imported `.so` exactly where it was.

`target-cpu=native` binaries only run on CPUs with the same or newer instruction sets — use them
for local benchmarking, **not** for distributable packages or CI builds.

## Testing

```bash
.venv/bin/python -m pytest                                     # tests + docstring-example validation
.venv/bin/python -m mypy.stubtest gaspatchio --allowlist stubtest-allowlist.txt --mypy-config-file mypy-stubtest.ini
```

Public-API docstrings carry examples validated against their output. The docstring/style tooling
and contributor coding standards live in [`AGENTS.md`](AGENTS.md).

## Learn more

- 📖 [Documentation](https://gaspatchio.dev/) — guides, tutorials, full API + CLI reference
- 🦀 [Rust engine](../../core/README.md) — the core that powers this package
- 🏠 [Project overview](../../README.md)
