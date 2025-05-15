# Gaspatchio Core

A high-performance actuarial modeling framework built with Python, Polars, and Rust extensions.

## Installation

```bash
uv sync
```

## Running Tests

```bash
uv run pytest
```

## Stubs and types

```bash
uv run -- python -m mypy.stubtest gaspatchio_core
```

## Documentation

We use standard doctest to generate great docs and tests for the python bindings.

you can run these (and they also run as a part of the test suite) with:

```bash
uv run pytest --doctest-modules --doctest-glob="*.pyi" 
```

we're also using pytest-accept to generate outputs once we have the right tests in place. 

> The "test" here actually means we're checking that the output matches◊ the expected output.
there's no 'assert' as such, that should be in the regular pytest tests. 

If you want to force the examples to have the output you expect, you can use:
```bash
uv run pytest gaspatchio_core/accessors/excel.py --doctest-modules --doctest-glob="*.pyi" --accept
```