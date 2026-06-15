# Gaspatchio

[![CI](https://github.com/opioinc/gaspatchio-core/actions/workflows/CI.yml/badge.svg)](https://github.com/opioinc/gaspatchio-core/actions/workflows/CI.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://gaspatchio.dev/)
[![Docs](https://img.shields.io/badge/docs-gaspatchio.dev-blue.svg)](https://gaspatchio.dev/)

**High-performance actuarial modeling — Python ergonomics, a Rust + Polars engine.**

Gaspatchio is a DataFrame-like engine for actuarial work: policy projections, assumption-table
lookups, and Excel-compatible financial maths over millions of model points. You write models in
Python that read like the formulas on a spreadsheet, and a Rust core runs them.

📖 **Documentation → [gaspatchio.dev](https://gaspatchio.dev/)**

---

## Links

| | |
|---|---|
| 📖 **Documentation** | **[gaspatchio.dev](https://gaspatchio.dev/)** — guides, tutorials, full API reference, recipes |
| 🐍 **Python package** | [`bindings/python/`](bindings/python/README.md) — install, the `gspio` CLI, building models · **start here** |
| 🦀 **Rust engine** | [`core/`](core/README.md) — assumption registry, vector plugins, projection kernels |
| 📊 **Performance benchmarks** | **[opioinc.github.io/gaspatchio-core](https://opioinc.github.io/gaspatchio-core/)** — live benchmark dashboards |

## The formula IS the code

Actuaries audit every calculation for regulatory compliance, so the maths stays visible — no
hidden framework magic:

```python
from gaspatchio_core import when

# Simple maths uses operators directly
af.pols_death = af.pols_if * af.mort_rate_mth
af.net_cf = af.premiums - af.claims - af.expenses - af.commissions

# Complex operations use named, domain-specific methods
af.survival = af.combined_decrement.projection.cumulative_survival()
af.reserve_prev = af.reserve.projection.previous_period()

# Business logic reads like Excel's IF()
af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)
```

Every line is auditable: the calculation **is** the code. A complete, runnable model — data
loading, the `gspio` CLI, and the projection lifecycle — is in the
[Python package README](bindings/python/README.md) and the [documentation](https://gaspatchio.dev/).

## Why Gaspatchio

- **The formula is the code** — operators for simple maths, named methods for complex operations,
  `when/then/otherwise` for business rules. Every line auditable; nothing hidden.
- **Meets your data where it is** — assumption tables accept data however it arrives; vector
  shimming reconciles scalar/list shapes automatically; Excel function semantics are preserved.
- **Fast by default** — tight change-test-refine loops with no warmup or JIT; quick on common
  hardware, scaling to large model-point sets without extra effort.
- **Built for AI-assisted work** — every public method ships docstring examples tested against
  their output, with clear error messages and an MCP/plugin surface, so you can use AI coding
  assistants to build and verify models — while the calculations stay auditable by you.

## Repository layout

- **[`bindings/python/`](bindings/python/README.md)** — the user-facing Python package
  (`gaspatchio_core`), PyO3 bindings, and the `gspio` CLI. **Model developers start here.**
- **[`core/`](core/README.md)** — the Rust engine: assumption registry, vector/Excel plugins,
  projection kernels.
- **`tutorial/`** — incremental tutorial models (hello-world → reconciled lifelib → scenarios).
- **`ref/`** — design specs and [architecture notes](ref/ARCHITECTURE.md).

## Contributing

Install `cargo` (Rust) and `uv` (Python), then from `bindings/python/`:

```bash
uv sync                 # install dependencies
maturin develop -uv     # build the Rust extension into the venv
uv run pytest           # run the tests
```

See [`core/README.md`](core/README.md) for the Rust engine, and the per-directory `AGENTS.md`
files for contributor rules and coding standards.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
