# Gaspatchio

**High-Performance Actuarial Modeling Framework**

Gaspatchio is a next-generation actuarial modeling engine that combines the ease of Python with the raw speed of Rust. It provides a DataFrame-like API specialized for actuarial projections, assumption management, and financial calculations.

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
