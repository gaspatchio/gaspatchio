# Gaspatchio

**High-Performance Actuarial Modeling Framework**

Gaspatchio is a next-generation actuarial modeling engine that combines the ease of Python with the raw speed of Rust. It provides a DataFrame-like API specialized for actuarial projections, assumption management, and financial calculations.

## Design Principles

The framework evolved over time. Each major decision is documented in the `ref/` directory.

### The Formula IS the Code

Actuaries need to audit every calculation for regulatory compliance. In Gaspatchio, the math is completely visible—no hidden framework magic:

```python
# Simple math uses operators directly
af.pols_death = af.pols_if * af.mort_rate_mth
af.net_cf = af.premiums - af.claims - af.expenses - af.commissions

# Complex operations use named methods
af.pols_if = af.combined_decrement.projection.cumulative_survival()
af.reserve_prev = af.reserve.projection.previous_period()

# Business logic reads like English
af.commissions = when(af.duration == 0).then(af.premiums).otherwise(0.0)
```

Each line is auditable. The calculation **is** the code.

### Meet You Where You Are

Ergonomics that feel like Python but read like a spreadsheet or pure formulas. Assumption tables respect data however it turns up—you don't need clean data or ETL from other system outputs. Vector shimming handles shape mismatches automatically. Excel function compatibility means familiar semantics.

### Design for AI

LLM-native from the ground up: great docs, great error messages, built to be used (and tested with) agentic loops. Includes an MCP server and a free agent for helping you build models.

### Default Fast, Nudge to Faster

Works quickly on your local machine on CPUs, scales with zero extra effort to GPUs. Key benchmarks are:

- **Change-test-refine loop**: How easy is it to make a change and see the result quickly? No warmup, no JIT, just go. You'll be in that loop for a while, so we make it as tight as possible.
- **Common hardware first**: Things should run quickly on common hardware. Meet people where they are.

### Amazing Docs

- Every method for every function is documented with examples that have verified output
- Documentation tailored to actuarial use cases
- "Recipes" for common actuarial patterns
- All documentation is built to be used by AI to help build models

## 📂 Repository Structure

This repository contains the complete source code for the Gaspatchio system:

*   **`bindings/python/`**: The main user-facing product. This directory contains the Python package (`gaspatchio_core`) which developers use to build models. It includes the PyO3 bindings that connect to the Rust engine.
*   **`core/`**: The high-performance Rust engine. This contains the implementation of the Assumption Registry, vector plugins, and core algorithms.
*   **`ref/`**: Architecture documentation and design notes.

## 🚀 Getting Started

If you are a model developer, start with the **Python Bindings**:

👉 **[Python Package Documentation](bindings/python/README.md)**

### Quick Example

```python
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table

# 1. Load Assumptions
mortality = Table(
    name="mortality_v1",
    source="data/mortality.parquet",
    dimensions={"age": "age"},
    value="rate"
)

# 2. Build Model
def projection(af: ActuarialFrame):
    # Vectorized date math (using Excel conventions)
    af.attained_age = af.dob.excel.yearfrac(af.val_date) + af.t
    
    # High-speed Assumption Lookup
    af.qx = mortality.lookup(age=af.attained_age)
    
    # Vectorized Projection
    af.pols_if = af.pols_start * (1 - af.qx - af.w_rate)

# 3. Run
af = ActuarialFrame(data="model_points.parquet")
projection(af)
result = af.collect()
```

## 📖 Architecture

For a deep dive into how Gaspatchio works under the hood, see:

👉 **[Architecture Guide](ref/ARCHITECTURE.md)**

## 🛠 For Contributors

To work on the core engine:

1.  Ensure you have `cargo` (Rust) and `uv` (Python) installed.
2.  Navigate to `bindings/python`.
3.  Run `uv sync` to install dependencies.
4.  Run `maturin develop -uv` to build the Rust extensions and install them into the virtual environment.

See `core/README.md` for more details on the Rust implementation.
