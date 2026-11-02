# Gaspatchio

[![CI](https://github.com/gaspatchio/gaspatchio/actions/workflows/CI.yml/badge.svg)](https://github.com/gaspatchio/gaspatchio/actions/workflows/CI.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://gaspatchio.dev/)
[![Docs](https://img.shields.io/badge/docs-gaspatchio.dev-blue.svg)](https://gaspatchio.dev/)

**High-performance actuarial modeling — Python ergonomics, a Rust + Polars engine.**

Gaspatchio is a DataFrame-like engine for actuarial work: policy projections, assumption-table
lookups, and Excel-compatible financial maths over millions of model points. You write models in
Python that read like the formulas on a spreadsheet, and a Rust core runs them.

📖 **Documentation → [gaspatchio.dev](https://gaspatchio.dev/)**

```bash
pip install gaspatchio              # the framework and the gspio command line
pip install "gaspatchio[jax]"       # adds the JAX engine: run a model's exported artifact on a CPU
pip install "jax[cuda12]"           # ...and on a GPU, with jax's CUDA wheels beside it
pip install "gaspatchio[viewer]"    # adds the viewer: gspio calc-graph --html writes one page a reviewer opens
```

The engine and the viewer are distributions of their own, `gaspatchio-jax` and
`gaspatchio-viewer`, each pinned exactly by its extra; the core installs neither jax nor any
JavaScript.

---

## Links

| | |
|---|---|
| 📖 **Documentation** | **[gaspatchio.dev](https://gaspatchio.dev/)** — guides, tutorials, full API reference, recipes |
| 📊 **Benchmarks** | [gaspatchio.github.io/gaspatchio](https://gaspatchio.github.io/gaspatchio/) — live per-commit performance dashboard |
| 🐍 **Python package** | [`bindings/python/`](bindings/python/README.md) — install, the `gspio` CLI, building models · **start here** |
| 🦀 **Rust engine** | [`core/`](core/README.md) — assumption registry, vector plugins, projection kernels |

## The formula IS the code

Actuaries audit every calculation for regulatory compliance, so the maths stays visible — no
hidden framework magic:

```python
from gaspatchio import when

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
- **Every model shows its work** — `gspio calc-graph` exports a model as a calculation-graph
  artifact: each column's formula, what it read, the assumption tables and data behind it, and a
  fingerprint of each. `gspio diff` compares two exports, last quarter's and this one's, by what
  changed in the calculation and what changed in the data, and, reading the results files the
  two record, which lines' numbers moved, in how many policies and by how much. `gspio verify`
  holds the files in hand against the record, and the viewer opens either export as a page.
  The same artifact runs on the JAX engine, which agrees with the Polars engine on the CPU to
  within 1e-12 of each line's scale.
- **Built for AI-assisted work** — every public method ships docstring examples tested against
  their output, with clear error messages and an MCP/plugin surface, so you can use AI coding
  assistants to build and verify models — while the calculations stay auditable by you.

## Performance

Gaspatchio targets the machine on your desk, not a cluster. The constraint we design to — not
a benchmark result, a constraint — is that a 100,000-policy run with monthly projections over
30 years finishes in seconds on a laptop, and a million policies is minutes; the edit-run-refine
loop slipping past a few seconds is treated as a bug
([the principles](https://gaspatchio.dev/latest/principles/) explain why we would drop a capability
before loosening the loop).

**[The benchmark dashboard](https://gaspatchio.github.io/gaspatchio/)** tracks measured
performance per commit, straight from CI (hosted runners, so laptop times differ):

- **Model benchmarks** — the Level 4 variable annuity model, end to end, up to
  100,000 policies
- **Gaspatchio vs lifelib** — cross-engine comparison on identical models; both engines
  reconcile to **0.0000% across 9 million data points**, so the speed numbers compare
  like for like
- **Aggregation & scenario benchmarks** — memory and throughput for portfolio-scale runs
- **[Rust core microbenchmarks](https://gaspatchio.github.io/gaspatchio/rust.html)** —
  Criterion results for the lookup and projection kernels

The speed comes from the architecture, not tuning flags: closed-form kernels instead of
recursive cell-graphs, and Polars' streaming engine with vectorised Rust plugins — no
per-row Python anywhere on the hot path.

## Repository layout

- **[`bindings/python/`](bindings/python/README.md)** — the user-facing Python package
  (`gaspatchio`), PyO3 bindings, and the `gspio` CLI. **Model developers start here.**
- **[`core/`](core/README.md)** — the Rust engine: assumption registry, vector/Excel plugins,
  projection kernels.
- **[`engines/jax/`](engines/jax/README.md)** — the JAX engine (`gaspatchio-jax`), which runs a
  model's exported executable artifact: `gspio run-artifact model.json points.parquet --engine jax`.
- **[`viewer/`](viewer/python/README.md)** — the viewer (`gaspatchio-viewer`), the page
  `gspio calc-graph ... --html` writes.
- **[`spec/`](spec/graph-artifact/v0-preview.md)** — the calculation-graph artifact's
  specification, a preview (`gaspatchio-graph/v0-preview.3`), with its schemas and conformance kit.
- **`tutorial/`** — incremental tutorial models (hello-world → reconciled lifelib → scenarios).
- **`ref/`** — design specs and [architecture notes](ref/ARCHITECTURE.md).

## AI plugin installation

Gaspatchio ships as a plugin for AI coding agents. Install once to get 9 actuarial modeling skills and always-loaded framework knowledge.

**Claude Code** (recommended)

```
/plugin marketplace add gaspatchio/gaspatchio
/plugin install gaspatchio@gaspatchio
```

**VS Code / GitHub Copilot** — search `@agentPlugins gaspatchio` in VS Code, or add to user
settings (Agent Plugins is in preview, so it also needs `"chat.plugins.enabled": true`):

```json
{
  "chat.plugins.marketplaces": ["gaspatchio/gaspatchio"]
}
```

**Cursor** — open any gaspatchio project; the `.cursor-plugin/` directory is auto-detected.

**Any agent** (universal) — `npx skills add gaspatchio/gaspatchio`; on Windows append
`--copy`, because symlinks need Developer Mode.

**Firewalled or offline** — clone the repository. Editors auto-detect plugin directories when
the project is opened.

What you get:

- **9 skills**: gaspatchio-quickstart, gaspatchio-model-discovery, gaspatchio-workbook-conversion, gaspatchio-model-building, gaspatchio-model-reconciliation, gaspatchio-model-review, gaspatchio-model-scenarios, gaspatchio-results-analysis, gaspatchio-extending
- **`AGENTS.md`** — always-loaded framework knowledge (API patterns, CLI reference, gotchas).

## Contributing

Install `cargo` (Rust) and `uv` (Python), then from `bindings/python/`:

```bash
uv sync --locked                     # install the pinned dependencies
uvx maturin develop --release --uv   # build the Rust extension into the source tree
.venv/bin/python -m pytest           # run the tests
```

Run the tests from `.venv/bin/` rather than through `uv run`, which re-syncs the project and,
after a Rust change, rebuilds the extension at the dev profile; [`CONTRIBUTING.md`](CONTRIBUTING.md)
says why that matters.

See [`core/README.md`](core/README.md) for the Rust engine, and the per-directory `AGENTS.md`
files for contributor rules and coding standards.

## Security & supply chain

- **Reporting a vulnerability** — see [SECURITY.md](SECURITY.md). Report privately via GitHub's
  "Report a vulnerability" button, not public issues.
- **SBOM** — every release ships a CycloneDX Software Bill of Materials (`sbom.cdx.json`, covering
  both the Rust and Python dependency graphs) as a
  [release](https://github.com/gaspatchio/gaspatchio/releases) asset. Fetch it with:

  ```bash
  gh release download <tag> --repo gaspatchio/gaspatchio --pattern 'sbom.cdx.json'
  ```
- **Build provenance** — wheels are published to PyPI via
  [Trusted Publishing](https://docs.pypi.org/trusted-publishers/), so each release carries
  [PEP 740](https://peps.python.org/pep-0740/) digital attestations on its PyPI files.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
