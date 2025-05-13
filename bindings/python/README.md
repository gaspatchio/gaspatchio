# Gaspatchio Core

A high-performance actuarial modeling framework built with Python, Polars, and Rust extensions.

## Installation

```bash
uv sync
```


### Running Tests

Python tests
```bash
uv run pytest
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

## License

This project is licensed under the MIT License - see the LICENSE file for details.