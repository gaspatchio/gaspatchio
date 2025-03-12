# Gaspatchio Core

A high-performance actuarial modeling framework built with Python, Polars, and Rust extensions.

## Installation

```bash
uv sync
```


### Setting Up Pre-commit Hooks

The project uses pre-commit hooks to ensure code quality. To set them up:

```bash
# Install pre-commit hooks in your git repository
pre-commit install

# Install commit-msg hook for commit message validation
pre-commit install --hook-type commit-msg

# Test if the hooks are working
pre-commit run --all-files
```

### Running Tests

```bash
uv run pytest
```

### Building the Project

To build locally. 
```bash
maturin build --uv
```

If you want to release a new version, you can use the following command:
```bash
docker run --rm -v $(pwd):/io ghcr.io/pyo3/maturin build --release
```
The command `docker run --rm -v $(pwd):/io ghcr.io/pyo3/maturin build --release` builds the project in a Docker container using the maturin image. This approach creates a "manylinux" compatible wheel that can be distributed and installed on most Linux distributions - esp useful when you're running on a Mac.

## License

This project is licensed under the MIT License - see the LICENSE file for details.