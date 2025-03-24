# Refactoring Strategy: Separating Core Rust Logic from Python Bindings

This document outlines a strategy to refactor a project that currently mixes core Rust logic with PyO3 bindings in a single crate. The goal is to decouple the business logic from the Python integration so that the core library is testable, maintainable, and deployable independently from its Python wrapper.

---

## 1. The Problem with Combined Bindings

- **Linking & Build Issues:**  
  When Python extension settings (e.g., `"cdylib"` with the `extension-module` feature) are combined with your core logic, running tests via `cargo test` may fail due to linker errors and other build complications.

- **Tight Coupling:**  
  The core logic becomes tied to Python-specific dependencies and build configurations, making it harder to test and reuse in a pure Rust context.

- **Reduced Developer Productivity:**  
  Every test run or refactor of your business logic forces you to handle Python integration issues, slowing down the development cycle.

---

## 2. The Refactoring Strategy

### A. Split into Two Crates in a Workspace

1. **Pure Rust Library Crate (Core):**
   - **Purpose:**  
     Contains your core business logic without any Python dependencies.
   - **Configuration:**  
     - In its `Cargo.toml`, set the library type as `"rlib"`.
     - Write all your unit and integration tests here.
   - **Benefits:**  
     - Tests run normally using `cargo test`.
     - No extra linking or Python environment issues.

2. **Python Bindings Crate (Wrapper):**
   - **Purpose:**  
     Contains the PyO3 code that wraps your core library to expose a Python module.
   - **Configuration:**  
     - In its `Cargo.toml`, set the library type as `"cdylib"` (or include both `"rlib"` and `"cdylib"` if needed for tests).
     - Depend on the pure library crate via a path dependency.
     - Include all the `#[pymodule]` and `#[pyfunction]` annotations.
   - **Benefits:**  
     - This crate is solely responsible for building the shared library that Python can import.
     - Its build process (using maturin or setuptools‑rust) is isolated from the core logic.

3. **Cargo Workspace Manifest:**
   - Create a workspace `Cargo.toml` at the root listing both the core and bindings crates as members.
   - This allows you to manage, build, and test both crates together if needed.

### B. Why This Separation?

- **Decoupling:**  
  Your business logic becomes independent of the Python runtime and specific build configurations. This makes testing and maintenance more straightforward.

- **Maintainability:**  
  The Python bindings serve as a thin adapter over the core library, reducing the risk of Python-specific bugs affecting your core logic.

- **Build Flexibility:**  
  You can run standard Rust commands (like `cargo test`) on the core library, while using tools like maturin to package and distribute the Python extension from the separate bindings crate.

---

## 3. Implementation Steps

1. **Create a New Workspace:**
   - At the root of your project, create a `Cargo.toml` that defines the workspace:
     ```toml
     [workspace]
     members = [
         "core",
         "bindings"
     ]
     ```

2. **Extract Core Logic:**
   - Move your business logic, models, algorithms, and tests into a new crate (e.g., `core/`).
   - In `core/Cargo.toml`, set:
     ```toml
     [lib]
     crate-type = ["rlib"]
     ```

3. **Create the Python Bindings Crate:**
   - In a new directory (e.g., `bindings/`), create a crate that wraps the `core` crate.
   - Add `core` as a dependency:
     ```toml
     [dependencies]
     core = { path = "../core" }
     pyo3 = { version = "0.24.0", features = ["extension-module"] }
     ```
   - Set the crate type in `bindings/Cargo.toml`:
     ```toml
     [lib]
     crate-type = ["cdylib"]
     ```

4. **Write the Bindings Code:**
   - In `bindings/src/lib.rs`, write your PyO3 wrapper:
     ```rust
     use pyo3::prelude::*;
     use core::{your_core_functions, YourCoreType};

     #[pyfunction]
     fn wrapped_function(args: /* appropriate types */) -> PyResult<ReturnType> {
         // Call your core function here
         your_core_functions(args)
     }

     #[pymodule]
     fn your_module_name(m: &PyModule) -> PyResult<()> {
         m.add_function(wrap_pyfunction!(wrapped_function, m)?)?;
         Ok(())
     }
     ```
   - Ensure the module name matches what you want to import in Python.

5. **Integrate with Maturin or setuptools‑rust:**
   - Optionally, add a `pyproject.toml` to manage packaging:
     ```toml
     [build-system]
     requires = ["maturin>=0.12"]
     build-backend = "maturin"
     ```

6. **Testing:**
   - Run tests on the core crate independently:
     ```sh
     cd core && cargo test
     ```
   - Build and test the Python extension separately with maturin:
     ```sh
     cd bindings && maturin develop
     ```

---

## 4. Benefits for the Team

- **Cleaner Code Separation:**  
  Developers can focus on business logic without being distracted by Python integration issues.

- **Faster Testing & Iteration:**  
  Running `cargo test` on the core library is fast and avoids the complexities of dynamic linking.

- **Modular Deployment:**  
  The Python bindings can be updated, built, and deployed independently from the core library, allowing for clearer versioning and rollback strategies.

- **Easier Onboarding:**  
  A modularized project structure makes it easier for new team members—or even LLM-based assistants—to understand each crate's responsibilities.

---

## Conclusion

By refactoring your project into a workspace with a pure Rust library and a dedicated Python bindings crate, you decouple your core logic from Python integration concerns. This improves build reliability, testability, and maintainability while simplifying deployment and development processes.

This approach is employed by several major projects (e.g., **pydantic‑core**, **tokenizers**, **py‑polars**) and is considered best practice when extending Python with Rust using PyO3.