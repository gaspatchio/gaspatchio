# Gaspatchio (Python)

The Python package for [Gaspatchio](../../README.md) — a high-performance actuarial modeling
framework. You write models in Python that read like spreadsheet formulas, and a Rust + Polars
engine runs them over millions of model points.

📖 **Documentation, tutorials, and full API + CLI reference → [gaspatchio.dev](https://gaspatchio.dev/)**

## Install

```bash
pip install gaspatchio        # or:  uv pip install gaspatchio
```

Then `import gaspatchio_core`. For a source/dev build, see [Building from source](#building-from-source).

## Quick start

```python
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table

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
gspio run-model model.py data.parquet --mode optimize          # optimized execution
gspio --install-completion                                     # shell tab-completion
```

- `--policy-id-column` sets the policy-identifier column (default `"Policy number"`).
- `--mode {debug,optimize}` plus display flags (`--rows/-r`, `--first-n/-f`, `--last-n/-l`,
  `--start-at/-s`) control execution and terminal output.

**Full CLI reference, with every flag and the single-policy result transposition →
[gaspatchio.dev](https://gaspatchio.dev/).**

## Building from source

The Rust extension is built with [maturin](https://www.maturin.rs/). `uv sync` builds in **debug**
mode (fast compiles); use `--release` for benchmarking/production:

```bash
uv sync                                                        # debug build, into the venv
maturin build --release -uv                                    # optimized build
RUSTFLAGS="-C target-cpu=native" maturin build --release -uv   # + native SIMD (AVX2/512)
```

`target-cpu=native` binaries only run on CPUs with the same or newer instruction sets — use them
for local benchmarking, **not** for distributable packages or CI builds.

## Testing

```bash
uv run pytest                                                  # tests + docstring-example validation
uv run python -m mypy.stubtest gaspatchio_core --allowlist stubtest-allowlist.txt --mypy-config-file mypy-stubtest.ini
```

Public-API docstrings carry examples validated against their output. The docstring/style tooling
and contributor coding standards live in [`AGENTS.md`](AGENTS.md).

## Learn more

- 📖 [Documentation](https://gaspatchio.dev/) — guides, tutorials, full API + CLI reference
- 🦀 [Rust engine](../../core/README.md) — the core that powers this package
- 🏠 [Project overview](../../README.md)
