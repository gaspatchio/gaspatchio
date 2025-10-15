# Gaspatchio Core

A high-performance actuarial modeling framework built with Python, Polars, and Rust extensions.

## Installation

```bash
pip install gaspatchio-core
# or with uv
uv pip install gaspatchio-core
```

For development:
```bash
uv sync
```

## Command Line Interface (CLI)

Gaspatchio Core includes a powerful CLI tool called `gspio` for executing actuarial models.

### Enable Shell Completion

For better developer experience, enable tab completion:

```bash
gspio --install-completion
```

This enables tab completion for commands, options, and even option values like `--mode`.

### Running Models

#### Full Model Run

Execute an actuarial model for all policies in your dataset:

```bash
gspio run-model model.py model-points.parquet
```

With options:
```bash
gspio run-model model.py data.parquet --mode optimize --rows 20
```

#### Single Policy Run

Debug or analyze a specific policy by running the model for just one policy ID:

```bash
gspio run-single-policy model.py model-points.parquet 12345
```

With custom policy ID column:
```bash
gspio run-single-policy model.py data.parquet 12345 --policy-id-column "PolicyNumber"
```

**Important**: The `--policy-id-column` option tells the CLI which column contains your policy identifiers. This is crucial because the CLI needs to:
1. Filter the data to find the specific policy
2. Know which column to use when transposing results

##### Result Transposition

For single policy runs, the CLI automatically transposes vector results for better readability. This converts time-series data from columns to rows:

**Before transposition** (standard model output):
| Policy number | proj_months | policy_year | premium | mortality_rate | lapse_rate | claim_amount |
|--------------|-------------|-------------|---------|----------------|------------|--------------|
| 12345 | [0, 1, 2, ..., 359] | [1, 1, 1, ..., 30] | [125.50, 125.50, 125.50, ...] | [0.00105, 0.00105, 0.00106, ...] | [0.15, 0.15, 0.12, ...] | [0, 0, 0, ..., 50000] |

**After transposition** (single policy output):
| Policy number | proj_months | policy_year | premium | mortality_rate | lapse_rate | claim_amount |
|--------------|-------------|-------------|---------|----------------|------------|--------------|
| 12345 | 0 | 1 | 125.50 | 0.00105 | 0.15 | 0 |
| 12345 | 1 | 1 | 125.50 | 0.00105 | 0.15 | 0 |
| 12345 | 2 | 1 | 125.50 | 0.00106 | 0.15 | 0 |
| 12345 | 12 | 2 | 125.50 | 0.00115 | 0.12 | 0 |
| 12345 | 24 | 3 | 125.50 | 0.00128 | 0.10 | 0 |
| ... | ... | ... | ... | ... | ... | ... |
| 12345 | 359 | 30 | 125.50 | 0.00834 | 0.05 | 50000 |

Each row now represents a time period, making it much easier to follow the progression of values over time.

### CLI Options

#### Execution Options

- `--mode, -m`: Execution mode (`debug` or `optimize`)
  - `debug`: Provides detailed error messages and tracking (default)
  - `optimize`: Faster execution with less debugging information

- `--policy-id-column`: Column name containing policy IDs (default: "Policy number")

#### Display Options

Control how results are displayed in the terminal:

- `--rows, -r`: Number of rows to display (default: 15)
- `--first-n, -f`: Number of first columns to show (default: 5)
- `--last-n, -l`: Number of last columns to show (default: 10)
- `--start-at, -s`: Starting column index, 0-based (default: 0)

### Examples

#### Basic Usage

```bash
# Run model with default settings
gspio run-model calculations.py policies.parquet

# Run single policy
gspio run-single-policy calculations.py policies.parquet 1001
```

#### Advanced Column Filtering

```bash
# Show columns 10-20 and last 5 columns, with 30 rows
gspio run-model model.py data.parquet -s 10 -f 10 -l 5 -r 30

# For single policy, show specific columns
gspio run-single-policy model.py data.parquet 42 -s 5 -f 15 -l 3
```

#### Performance Optimization

```bash
# Run in optimized mode for better performance
gspio run-model model.py large-dataset.parquet --mode optimize

# Debug mode for development
gspio run-model model.py test-data.parquet --mode debug -r 50
```

#### Custom Policy Identifiers

```bash
# Using different policy ID columns
gspio run-single-policy model.py data.parquet ABC123 --policy-id-column "ContractID"
gspio run-single-policy model.py data.parquet 789 --policy-id-column "policyholder nr"
```

### Model File Requirements

Your model file should contain a function (default name: `life_model`) that accepts an ActuarialFrame:

```python
from gaspatchio_core import ActuarialFrame

def life_model(af: ActuarialFrame) -> None:
    # Your actuarial calculations here
    af["premium"] = af["sum_assured"] * af["premium_rate"]
    # ... more calculations
```

### Data File Requirements

Model points data can be in:
- Parquet format (recommended for performance)
- CSV format

The data should include:
- A policy identifier column (default: "Policy number")
- Any columns referenced in your model calculations

## Running Tests

```bash
uv run pytest
```

## Stubs and types

```bash
uv run -- python -m mypy.stubtest gaspatchio_core
```

## Documentation & Docstring Validation

We use a custom docstring validation system to ensure high-quality documentation with executable examples.

### Docstring Example Validation

The test suite automatically validates docstring code examples for:
- **Syntax errors** (via Ruff linting)
- **Code style** (optional, via custom style rules)
- **Runtime correctness** (optional, validates output matches expected)

### Running Docstring Tests

#### Basic Linting (Default)

Runs syntax checks on all docstring examples:
```bash
uv run pytest
```

#### Style Checking

Detect old bracket notation (`af["column"]`) and suggest modern attribute notation (`af.column`):

```bash
# Show style warnings (doesn't fail tests)
uv run pytest gaspatchio_core/column/namespaces/dt_proxy.py --gp-style-check=warn -s

# Fail tests on style violations
uv run pytest gaspatchio_core/accessors/excel.py --gp-style-check=strict

# Check specific file
uv run pytest gaspatchio_core/accessors/date.py --gp-style-check=warn -s
```

**Note:** Use `-s` flag with `warn` mode to see warnings in real-time.

#### Runtime Validation

Execute docstring examples and validate output:

```bash
# Run code and check output matches expected
uv run pytest gaspatchio_core/column/namespaces/dt_proxy.py --gp-run-examples

# Combine with style checking
uv run pytest gaspatchio_core/accessors/excel.py --gp-style-check=warn --gp-run-examples -s
```

### Style Rules

Current style rules enforced:

- **GP001**: Prefer attribute notation (`af.column`) over bracket notation (`af["column"]`)
  - Only applies when column name is a valid Python identifier
  - Helps with code readability and IntelliSense support

### Testing Specific Files

```bash
# Single file with all checks
uv run pytest gaspatchio_core/column/namespaces/dt_proxy.py --gp-style-check=strict --gp-run-examples

# Multiple files
uv run pytest gaspatchio_core/accessors/date.py gaspatchio_core/accessors/excel.py --gp-style-check=warn -s

# Specific example
uv run pytest gaspatchio_core/column/namespaces/dt_proxy.py::dt_proxy.DtNamespaceProxy.year-ex0 --gp-style-check=strict
```

### Docstring Configuration

Files to validate are configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = [
    "--gp-docstring-paths=gaspatchio_core/column/namespaces/dt_proxy.py",
    "--gp-docstring-paths=gaspatchio_core/accessors/excel.py",
    # ... more paths
]
```