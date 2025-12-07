# RFC 27: Scenario Support - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add minimal framework support for running actuarial models across multiple economic scenarios in a single vectorized execution.

**Architecture:** Two core additions: (1) `with_scenarios()` function that cross-joins an ActuarialFrame with scenario IDs, adding a `scenario_id` column; (2) `Table.from_scenario_files()` and `Table.from_scenario_template()` classmethods to load per-scenario assumption files into unified Tables. All scenario operations are transparent data operations - no magic.

**Tech Stack:** Python 3.11+, Polars, gaspatchio_core (existing), pytest for testing.

---

## Phase 1: Core Scenario Expansion (MVP)

### Task 1: Create Scenario Module Structure

**Files:**
- Create: `gaspatchio_core/scenarios/__init__.py`
- Create: `gaspatchio_core/scenarios/_with_scenarios.py`

**Step 1: Write the failing test**

Create test file first:

```bash
mkdir -p tests/scenarios
touch tests/scenarios/__init__.py
```

Create: `tests/scenarios/test_with_scenarios.py`

```python
# ABOUTME: Tests for scenario expansion functionality.
# ABOUTME: Verifies with_scenarios() cross-joins ActuarialFrame with scenario IDs.

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios


class TestWithScenariosBasic:
    """Basic tests for with_scenarios() function."""

    def test_expands_single_row_to_multiple_scenarios(self):
        """One model point × 3 scenarios = 3 rows."""
        # Arrange
        af = ActuarialFrame({"policy_id": [1], "premium": [100.0]})

        # Act
        result = with_scenarios(af, ["BASE", "UP", "DOWN"])

        # Assert
        df = result.collect()
        assert len(df) == 3
        assert "scenario_id" in df.columns
        assert set(df["scenario_id"].to_list()) == {"BASE", "UP", "DOWN"}
        # Original columns preserved
        assert df["policy_id"].to_list() == [1, 1, 1]
        assert df["premium"].to_list() == [100.0, 100.0, 100.0]

    def test_expands_multiple_rows_to_scenarios(self):
        """3 model points × 2 scenarios = 6 rows."""
        # Arrange
        af = ActuarialFrame({
            "policy_id": [1, 2, 3],
            "premium": [100.0, 200.0, 300.0],
        })

        # Act
        result = with_scenarios(af, ["BASE", "STRESS"])

        # Assert
        df = result.collect()
        assert len(df) == 6
        assert set(df["scenario_id"].to_list()) == {"BASE", "STRESS"}

    def test_returns_actuarial_frame(self):
        """Result should be an ActuarialFrame, not a DataFrame."""
        af = ActuarialFrame({"x": [1]})
        result = with_scenarios(af, ["A"])
        assert isinstance(result, ActuarialFrame)

    def test_single_scenario_deterministic(self):
        """Single scenario is valid - the scenario-ready-by-default pattern."""
        af = ActuarialFrame({"policy_id": [1, 2]})
        result = with_scenarios(af, ["DETERMINISTIC"])
        df = result.collect()
        assert len(df) == 2
        assert df["scenario_id"].to_list() == ["DETERMINISTIC", "DETERMINISTIC"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'gaspatchio_core.scenarios'"

**Step 3: Create scenarios module structure**

Create: `gaspatchio_core/scenarios/__init__.py`

```python
# ABOUTME: Scenario support module for multi-scenario actuarial model execution.
# ABOUTME: Provides with_scenarios() for cross-joining ActuarialFrames with scenario IDs.

from ._with_scenarios import with_scenarios

__all__ = ["with_scenarios"]
```

Create: `gaspatchio_core/scenarios/_with_scenarios.py`

```python
# ABOUTME: Implementation of with_scenarios() for scenario expansion.
# ABOUTME: Cross-joins ActuarialFrame with scenario IDs to enable multi-scenario runs.

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from ..frame import ActuarialFrame


def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    categorical: bool = False,
) -> ActuarialFrame:
    """
    Expand ActuarialFrame across scenarios via cross-join.

    Creates a new ActuarialFrame with len(af) × len(scenario_ids) rows,
    preserving all original columns and adding a scenario_id column.

    This is the fundamental operation for running actuarial models across
    multiple economic scenarios in a single vectorized execution.

    Args:
        af: Input ActuarialFrame to expand
        scenario_ids: List of scenario identifiers (strings or integers)
        scenario_column: Name for the scenario ID column (default: "scenario_id")
        categorical: If True and scenario_ids are strings, use Categorical dtype
                    for better join/groupby performance (default: False)

    Returns:
        ActuarialFrame with expanded rows and scenario_column added.

    Examples:
    --------
    **Basic scenario expansion:**

    ```python
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.scenarios import with_scenarios

    # 2 policies
    af = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})

    # Expand to 3 scenarios → 6 rows
    af = with_scenarios(af, ["BASE", "UP", "DOWN"])
    print(af.collect())
    ```

    **Single deterministic scenario (scenario-ready-by-default):**

    ```python
    # Even single-scenario models should use with_scenarios
    af = with_scenarios(af, ["DETERMINISTIC"])
    ```

    **Integer scenarios for stochastic runs:**

    ```python
    # For 10K stochastic scenarios, use integers for performance
    af = with_scenarios(af, list(range(1, 10001)))
    ```

    **Categorical encoding for named scenarios:**

    ```python
    # Use categorical=True for better groupby/join performance with string IDs
    af = with_scenarios(af, ["BASE", "UP", "DOWN"], categorical=True)
    ```
    """
    # Import here to avoid circular dependency
    from ..frame import ActuarialFrame

    # Create scenarios DataFrame
    scenarios_df = pl.DataFrame({scenario_column: scenario_ids})

    # Apply categorical encoding if requested
    if categorical and scenarios_df[scenario_column].dtype == pl.Utf8:
        scenarios_df = scenarios_df.with_columns(
            pl.col(scenario_column).cast(pl.Categorical)
        )

    # Collect the ActuarialFrame to DataFrame for cross-join
    # Note: collect() returns a DataFrame, which we can join
    af_df = af.collect()

    # Perform cross-join to expand rows
    expanded = af_df.join(scenarios_df, how="cross")

    # Return as ActuarialFrame, preserving mode
    return ActuarialFrame(expanded, mode=af._mode, verbose=af._verbose)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/ tests/scenarios/
git commit -m "$(cat <<'EOF'
feat(scenarios): add with_scenarios() for scenario expansion

Implements RFC 27 Phase 1 - core scenario expansion via cross-join.
with_scenarios(af, scenario_ids) expands an ActuarialFrame across
multiple scenarios, enabling vectorized multi-scenario model runs.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add Integer and Categorical Scenario ID Tests

**Files:**
- Modify: `tests/scenarios/test_with_scenarios.py`

**Step 1: Write additional failing tests**

Add to `tests/scenarios/test_with_scenarios.py`:

```python
class TestWithScenariosPerformance:
    """Tests for scenario ID encoding and performance features."""

    def test_integer_scenario_ids(self):
        """Integer scenario IDs for stochastic runs."""
        af = ActuarialFrame({"x": [1]})
        result = with_scenarios(af, [1, 2, 3, 4, 5])
        df = result.collect()
        assert len(df) == 5
        assert df["scenario_id"].dtype == pl.Int64
        assert set(df["scenario_id"].to_list()) == {1, 2, 3, 4, 5}

    def test_categorical_encoding(self):
        """Categorical encoding for string scenario IDs."""
        af = ActuarialFrame({"x": [1]})
        result = with_scenarios(af, ["A", "B", "C"], categorical=True)
        df = result.collect()
        assert df["scenario_id"].dtype == pl.Categorical

    def test_categorical_not_applied_to_integers(self):
        """Categorical flag should not affect integer IDs."""
        af = ActuarialFrame({"x": [1]})
        result = with_scenarios(af, [1, 2, 3], categorical=True)
        df = result.collect()
        # Integer IDs stay as integers even with categorical=True
        assert df["scenario_id"].dtype == pl.Int64

    def test_custom_scenario_column_name(self):
        """Custom scenario column name."""
        af = ActuarialFrame({"x": [1]})
        result = with_scenarios(af, ["A", "B"], scenario_column="scen")
        df = result.collect()
        assert "scen" in df.columns
        assert "scenario_id" not in df.columns


class TestWithScenariosPreservation:
    """Tests for ActuarialFrame property preservation."""

    def test_preserves_mode(self):
        """Mode should be preserved from input ActuarialFrame."""
        af = ActuarialFrame({"x": [1]}, mode="optimize")
        result = with_scenarios(af, ["A"])
        assert result._mode == "optimize"

    def test_preserves_verbose(self):
        """Verbose flag should be preserved."""
        af = ActuarialFrame({"x": [1]}, verbose=True)
        result = with_scenarios(af, ["A"])
        assert result._verbose is True

    def test_preserves_all_original_columns(self):
        """All original columns should be present in result."""
        af = ActuarialFrame({
            "policy_id": [1],
            "sum_assured": [100000],
            "age": [35],
            "sex": ["M"],
        })
        result = with_scenarios(af, ["BASE"])
        df = result.collect()
        assert set(df.columns) == {"policy_id", "sum_assured", "age", "sex", "scenario_id"}
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py -v`
Expected: PASS (implementation already handles these cases)

**Step 3: Commit**

```bash
git add tests/scenarios/test_with_scenarios.py
git commit -m "$(cat <<'EOF'
test(scenarios): add performance and preservation tests for with_scenarios

Tests integer scenario IDs, categorical encoding, custom column names,
and ActuarialFrame property preservation (mode, verbose).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Export with_scenarios from gaspatchio_core

**Files:**
- Modify: `gaspatchio_core/__init__.py`

**Step 1: Write the failing test**

Add to `tests/scenarios/test_with_scenarios.py`:

```python
def test_import_from_top_level():
    """with_scenarios should be importable from gaspatchio_core."""
    from gaspatchio_core import with_scenarios
    assert callable(with_scenarios)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py::test_import_from_top_level -v`
Expected: FAIL with "ImportError: cannot import name 'with_scenarios' from 'gaspatchio_core'"

**Step 3: Add export to __init__.py**

Modify: `gaspatchio_core/__init__.py`

Add import after other imports (around line 29):

```python
from .scenarios import with_scenarios
```

Add to `__all__` list:

```python
    "with_scenarios",
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py::test_import_from_top_level -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/__init__.py tests/scenarios/test_with_scenarios.py
git commit -m "$(cat <<'EOF'
feat(scenarios): export with_scenarios from gaspatchio_core

with_scenarios is now importable directly from gaspatchio_core:
from gaspatchio_core import with_scenarios

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add Table.from_scenario_files() Classmethod

**Files:**
- Create: `tests/scenarios/test_table_scenario_loading.py`
- Modify: `gaspatchio_core/assumptions/_api.py`

**Step 1: Write the failing test**

Create: `tests/scenarios/test_table_scenario_loading.py`

```python
# ABOUTME: Tests for loading assumption tables from per-scenario files.
# ABOUTME: Verifies Table.from_scenario_files() concatenates scenario files correctly.

from pathlib import Path
import tempfile

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table


class TestTableFromScenarioFiles:
    """Tests for Table.from_scenario_files() classmethod."""

    @pytest.fixture
    def scenario_files(self, tmp_path: Path) -> dict[str, Path]:
        """Create temporary scenario files for testing."""
        # BASE scenario
        base_df = pl.DataFrame({
            "year": [1, 2, 3],
            "rate": [0.03, 0.035, 0.04],
        })
        base_path = tmp_path / "base_rates.parquet"
        base_df.write_parquet(base_path)

        # UP scenario (+50bps)
        up_df = pl.DataFrame({
            "year": [1, 2, 3],
            "rate": [0.035, 0.04, 0.045],
        })
        up_path = tmp_path / "up_rates.parquet"
        up_df.write_parquet(up_path)

        # DOWN scenario (-50bps)
        down_df = pl.DataFrame({
            "year": [1, 2, 3],
            "rate": [0.025, 0.03, 0.035],
        })
        down_path = tmp_path / "down_rates.parquet"
        down_df.write_parquet(down_path)

        return {
            "BASE": base_path,
            "UP": up_path,
            "DOWN": down_path,
        }

    def test_concatenates_scenario_files(self, scenario_files):
        """Should create a single table with all scenarios concatenated."""
        table = Table.from_scenario_files(
            scenario_files=scenario_files,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates",
        )

        df = table.to_dataframe()

        # 3 scenarios × 3 years = 9 rows
        assert len(df) == 9
        assert "scenario_id" in df.columns
        assert set(df["scenario_id"].unique().to_list()) == {"BASE", "UP", "DOWN"}

    def test_scenario_column_becomes_dimension(self, scenario_files):
        """scenario_column should be added to dimensions."""
        table = Table.from_scenario_files(
            scenario_files=scenario_files,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates",
        )

        assert "scenario_id" in table.dimensions

    def test_lookup_with_scenario_dimension(self, scenario_files):
        """Lookup should work with scenario_id as a dimension."""
        from gaspatchio_core import ActuarialFrame

        table = Table.from_scenario_files(
            scenario_files=scenario_files,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates_lookup",
        )

        # Create test data
        af = ActuarialFrame({
            "scenario_id": ["BASE", "UP", "DOWN"],
            "year": [1, 1, 1],
        })

        af.rate = table.lookup(scenario_id=af.scenario_id, year=af.year)
        df = af.collect()

        # BASE year 1 = 0.03, UP year 1 = 0.035, DOWN year 1 = 0.025
        assert df["rate"].to_list() == pytest.approx([0.03, 0.035, 0.025])

    def test_accepts_string_paths(self, scenario_files):
        """Should accept string paths as well as Path objects."""
        string_paths = {k: str(v) for k, v in scenario_files.items()}

        table = Table.from_scenario_files(
            scenario_files=string_paths,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates_strings",
        )

        assert len(table.to_dataframe()) == 9
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_table_scenario_loading.py -v`
Expected: FAIL with "AttributeError: type object 'Table' has no attribute 'from_scenario_files'"

**Step 3: Implement Table.from_scenario_files()**

Add to `gaspatchio_core/assumptions/_api.py` as a classmethod on Table class (after `validate_lookup` method, around line 1027):

```python
    @classmethod
    def from_scenario_files(
        cls,
        scenario_files: dict[str, str | Path],
        scenario_column: str,
        dimensions: dict[str, str | Dimension],
        value: str,
        name: str | None = None,
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "Table":
        """
        Create a Table by concatenating per-scenario assumption files.

        Loads each file, adds scenario_column with the scenario ID, concatenates
        all into a single DataFrame, and creates a Table with scenario_column
        as an additional dimension.

        This is useful when assumptions are stored as separate files per scenario
        (e.g., from an ESG tool that outputs per-scenario returns).

        Args:
            scenario_files: Mapping of scenario_id -> file path
            scenario_column: Name for the scenario ID column
            dimensions: Dimension mapping (excluding scenario, which is added automatically)
            value: Value column name
            name: Optional table name (defaults to "from_scenarios")
            validate: Whether to validate data on load
            metadata: Optional metadata dictionary

        Returns:
            Table with scenario_column added to dimensions

        Examples:
        --------
        **Loading per-scenario rate files:**

        ```python
        from gaspatchio_core.assumptions import Table

        rates_table = Table.from_scenario_files(
            scenario_files={
                "BASE": "scenarios/BASE/rates.parquet",
                "UP": "scenarios/UP/rates.parquet",
                "DOWN": "scenarios/DOWN/rates.parquet",
            },
            scenario_column="scenario_id",
            dimensions={"year": "year", "currency": "currency"},
            value="forward_rate",
            name="discount_rates",
        )

        # Lookup uses scenario_id as a dimension
        rate = rates_table.lookup(
            scenario_id=af.scenario_id,
            year=af.year,
            currency=pl.lit("USD"),
        )
        ```
        """
        dfs = []
        for scenario_id, path in scenario_files.items():
            # Load the file
            file_path = Path(path) if isinstance(path, str) else path
            df = pl.read_parquet(file_path)

            # Add scenario column
            df = df.with_columns(pl.lit(scenario_id).alias(scenario_column))
            dfs.append(df)

        # Concatenate all scenario DataFrames
        combined = pl.concat(dfs)

        # Build dimensions with scenario_column first
        all_dimensions = {scenario_column: scenario_column, **dimensions}

        return cls(
            name=name or "from_scenarios",
            source=combined,
            dimensions=all_dimensions,
            value=value,
            validate=validate,
            metadata=metadata,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_table_scenario_loading.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/assumptions/_api.py tests/scenarios/test_table_scenario_loading.py
git commit -m "$(cat <<'EOF'
feat(scenarios): add Table.from_scenario_files() for per-scenario loading

Classmethod to load per-scenario assumption files and concatenate them
into a single Table with scenario_id as a dimension. Enables lookups
that vary by scenario without changing Table's core lookup logic.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Add Table.from_scenario_template() Convenience Method

**Files:**
- Modify: `tests/scenarios/test_table_scenario_loading.py`
- Modify: `gaspatchio_core/assumptions/_api.py`

**Step 1: Write the failing test**

Add to `tests/scenarios/test_table_scenario_loading.py`:

```python
class TestTableFromScenarioTemplate:
    """Tests for Table.from_scenario_template() classmethod."""

    @pytest.fixture
    def templated_scenario_files(self, tmp_path: Path) -> tuple[str, list[str]]:
        """Create scenario files following a template pattern."""
        scenarios = ["BASE", "UP", "DOWN"]

        for scenario in scenarios:
            scenario_dir = tmp_path / scenario
            scenario_dir.mkdir()
            df = pl.DataFrame({
                "year": [1, 2, 3],
                "rate": [0.03, 0.035, 0.04] if scenario == "BASE"
                    else [0.035, 0.04, 0.045] if scenario == "UP"
                    else [0.025, 0.03, 0.035],
            })
            df.write_parquet(scenario_dir / "rates.parquet")

        template = str(tmp_path / "{scenario_id}" / "rates.parquet")
        return template, scenarios

    def test_expands_template_to_files(self, templated_scenario_files):
        """Should expand template with scenario IDs."""
        template, scenarios = templated_scenario_files

        table = Table.from_scenario_template(
            path_template=template,
            scenario_ids=scenarios,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="templated_rates",
        )

        df = table.to_dataframe()
        assert len(df) == 9  # 3 scenarios × 3 years
        assert set(df["scenario_id"].unique().to_list()) == {"BASE", "UP", "DOWN"}

    def test_template_with_integer_scenarios(self, tmp_path: Path):
        """Template should work with integer scenario IDs."""
        for i in range(1, 4):
            scenario_dir = tmp_path / str(i)
            scenario_dir.mkdir()
            df = pl.DataFrame({"t": [1, 2], "rate": [0.01 * i, 0.02 * i]})
            df.write_parquet(scenario_dir / "data.parquet")

        template = str(tmp_path / "{scenario_id}" / "data.parquet")

        table = Table.from_scenario_template(
            path_template=template,
            scenario_ids=[1, 2, 3],
            scenario_column="scen",
            dimensions={"t": "t"},
            value="rate",
            name="int_templated",
        )

        df = table.to_dataframe()
        assert len(df) == 6  # 3 scenarios × 2 periods
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_table_scenario_loading.py::TestTableFromScenarioTemplate -v`
Expected: FAIL with "AttributeError: type object 'Table' has no attribute 'from_scenario_template'"

**Step 3: Implement Table.from_scenario_template()**

Add to `gaspatchio_core/assumptions/_api.py` after `from_scenario_files`:

```python
    @classmethod
    def from_scenario_template(
        cls,
        path_template: str,
        scenario_ids: list[str] | list[int],
        scenario_column: str,
        dimensions: dict[str, str | Dimension],
        value: str,
        name: str | None = None,
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "Table":
        """
        Create a Table from scenario files matching a path template.

        Convenience method when scenario files follow a predictable naming pattern.
        Expands the template with each scenario ID and delegates to from_scenario_files().

        Args:
            path_template: Path with {scenario_id} placeholder
            scenario_ids: List of scenario IDs to load
            scenario_column: Name for the scenario ID column
            dimensions: Dimension mapping (excluding scenario)
            value: Value column name
            name: Optional table name
            validate: Whether to validate data on load
            metadata: Optional metadata dictionary

        Returns:
            Table with scenario_column added to dimensions

        Examples:
        --------
        **Loading files from templated paths:**

        ```python
        from gaspatchio_core.assumptions import Table

        # Files: scenarios/BASE/returns.parquet, scenarios/UP/returns.parquet, etc.
        returns_table = Table.from_scenario_template(
            path_template="scenarios/{scenario_id}/returns.parquet",
            scenario_ids=["BASE", "UP", "DOWN"],
            scenario_column="scenario_id",
            dimensions={"t": "t", "fund_index": "fund_index"},
            value="inv_return_mth",
        )
        ```

        **With integer scenario IDs:**

        ```python
        # Files: stochastic/1/returns.parquet, stochastic/2/returns.parquet, etc.
        returns_table = Table.from_scenario_template(
            path_template="stochastic/{scenario_id}/returns.parquet",
            scenario_ids=list(range(1, 10001)),
            scenario_column="scenario_id",
            dimensions={"t": "t"},
            value="return",
        )
        ```
        """
        scenario_files = {
            scenario_id: path_template.format(scenario_id=scenario_id)
            for scenario_id in scenario_ids
        }
        return cls.from_scenario_files(
            scenario_files=scenario_files,
            scenario_column=scenario_column,
            dimensions=dimensions,
            value=value,
            name=name,
            validate=validate,
            metadata=metadata,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_table_scenario_loading.py::TestTableFromScenarioTemplate -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/assumptions/_api.py tests/scenarios/test_table_scenario_loading.py
git commit -m "$(cat <<'EOF'
feat(scenarios): add Table.from_scenario_template() convenience method

Convenience method for loading per-scenario files that follow a naming
pattern like scenarios/{scenario_id}/rates.parquet. Delegates to
from_scenario_files() after expanding the template.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Integration Test - Full Scenario Workflow

**Files:**
- Create: `tests/scenarios/test_scenario_workflow.py`

**Step 1: Write the integration test**

Create: `tests/scenarios/test_scenario_workflow.py`

```python
# ABOUTME: Integration tests for complete scenario workflows.
# ABOUTME: Tests the full pattern: model points + scenarios + lookups + aggregation.

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, with_scenarios
from gaspatchio_core.assumptions import Table


class TestScenarioWorkflowIntegration:
    """End-to-end tests for scenario-aware model execution."""

    @pytest.fixture
    def scenario_rates_table(self, tmp_path: Path) -> Table:
        """Create a discount rates table with scenario dimension."""
        # Create scenario rate files
        scenarios = {
            "BASE": [0.03, 0.035, 0.04],
            "UP": [0.04, 0.045, 0.05],
            "DOWN": [0.02, 0.025, 0.03],
        }

        for scenario_id, rates in scenarios.items():
            df = pl.DataFrame({
                "year": [1, 2, 3],
                "rate": rates,
            })
            df.write_parquet(tmp_path / f"{scenario_id}_rates.parquet")

        return Table.from_scenario_files(
            scenario_files={
                "BASE": tmp_path / "BASE_rates.parquet",
                "UP": tmp_path / "UP_rates.parquet",
                "DOWN": tmp_path / "DOWN_rates.parquet",
            },
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates_integration",
        )

    def test_full_scenario_workflow(self, scenario_rates_table):
        """Test: model points × scenarios → lookup → aggregate by scenario."""
        # === 1. Create model points ===
        model_points = {
            "policy_id": [1, 2],
            "premium": [1000.0, 2000.0],
            "year": [1, 2],
        }
        af = ActuarialFrame(model_points)

        # === 2. Expand across scenarios ===
        af = with_scenarios(af, ["BASE", "UP", "DOWN"])

        # Should have 2 policies × 3 scenarios = 6 rows
        assert len(af.collect()) == 6

        # === 3. Lookup scenario-varying rates ===
        af.disc_rate = scenario_rates_table.lookup(
            scenario_id=af.scenario_id,
            year=af.year,
        )

        # === 4. Simple calculation ===
        af.discounted_premium = af.premium * (1 - af.disc_rate)

        # === 5. Verify results ===
        df = af.collect()

        # Check we have all scenarios
        assert set(df["scenario_id"].unique().to_list()) == {"BASE", "UP", "DOWN"}

        # Check lookup worked correctly
        # Policy 1, year 1: BASE=0.03, UP=0.04, DOWN=0.02
        base_p1 = df.filter(
            (pl.col("scenario_id") == "BASE") & (pl.col("policy_id") == 1)
        )
        assert base_p1["disc_rate"].item() == pytest.approx(0.03)
        assert base_p1["discounted_premium"].item() == pytest.approx(1000.0 * 0.97)

    def test_scenario_aggregation(self, scenario_rates_table):
        """Test: aggregate results by scenario for risk metrics."""
        # Create model points
        af = ActuarialFrame({
            "policy_id": [1, 2, 3],
            "premium": [100.0, 200.0, 300.0],
            "year": [1, 1, 1],
        })

        # Expand and calculate
        af = with_scenarios(af, ["BASE", "UP", "DOWN"])
        af.disc_rate = scenario_rates_table.lookup(
            scenario_id=af.scenario_id,
            year=af.year,
        )
        af.pv_premium = af.premium * (1 - af.disc_rate)

        # Aggregate by scenario
        df = af.collect()
        by_scenario = df.group_by("scenario_id").agg([
            pl.col("pv_premium").sum().alias("total_pv_premium"),
        ])

        # BASE: sum = 600 * (1 - 0.03) = 582
        # UP: sum = 600 * (1 - 0.04) = 576
        # DOWN: sum = 600 * (1 - 0.02) = 588
        base_total = by_scenario.filter(pl.col("scenario_id") == "BASE")["total_pv_premium"].item()
        assert base_total == pytest.approx(582.0)

    def test_scenario_ready_by_default_pattern(self, scenario_rates_table):
        """Test: single scenario model uses same pattern as multi-scenario."""
        # The pattern should work identically with 1 or N scenarios
        af = ActuarialFrame({
            "policy_id": [1],
            "premium": [1000.0],
            "year": [1],
        })

        # Single scenario - same code pattern
        af = with_scenarios(af, ["BASE"])
        af.disc_rate = scenario_rates_table.lookup(
            scenario_id=af.scenario_id,
            year=af.year,
        )
        af.result = af.premium * (1 - af.disc_rate)

        df = af.collect()
        assert len(df) == 1
        assert df["scenario_id"].item() == "BASE"
        assert df["result"].item() == pytest.approx(970.0)
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_scenario_workflow.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/scenarios/test_scenario_workflow.py
git commit -m "$(cat <<'EOF'
test(scenarios): add integration tests for complete scenario workflow

Tests the full RFC 27 pattern:
- Model points × scenarios via with_scenarios()
- Scenario-varying lookups via Table with scenario_id dimension
- Aggregation by scenario for risk metrics

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Add Lazy Mode Support for with_scenarios

**Files:**
- Modify: `tests/scenarios/test_with_scenarios.py`
- Modify: `gaspatchio_core/scenarios/_with_scenarios.py`

**Step 1: Write the failing test**

Add to `tests/scenarios/test_with_scenarios.py`:

```python
class TestWithScenariosLazyMode:
    """Tests for lazy mode support in with_scenarios()."""

    def test_works_with_lazy_input(self):
        """with_scenarios should work when given a lazy ActuarialFrame."""
        # Create ActuarialFrame from LazyFrame
        lf = pl.LazyFrame({"x": [1, 2, 3]})
        af = ActuarialFrame(lf, mode="optimize")

        result = with_scenarios(af, ["A", "B"])

        # Should produce 6 rows when collected
        df = result.collect()
        assert len(df) == 6

    def test_scan_parquet_workflow(self, tmp_path):
        """Test the lazy loading pattern from RFC."""
        # Create a test parquet file
        test_df = pl.DataFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})
        test_path = tmp_path / "model_points.parquet"
        test_df.write_parquet(test_path)

        # Load lazily
        af = ActuarialFrame(pl.scan_parquet(test_path))

        # Expand
        af = with_scenarios(af, ["BASE", "STRESS"])

        # Collect
        df = af.collect()
        assert len(df) == 4  # 2 policies × 2 scenarios
```

**Step 2: Run test**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py::TestWithScenariosLazyMode -v`

The current implementation calls `af.collect()` which will work, but we should verify it handles lazy inputs gracefully.

**Step 3: Verify implementation handles lazy mode**

The current implementation already handles this correctly because:
1. `af.collect()` works on both lazy and eager ActuarialFrames
2. The result is created as a new ActuarialFrame from the expanded DataFrame

No code changes needed if tests pass.

**Step 4: Commit**

```bash
git add tests/scenarios/test_with_scenarios.py
git commit -m "$(cat <<'EOF'
test(scenarios): add lazy mode tests for with_scenarios

Verifies with_scenarios() works correctly with lazy ActuarialFrames
and the scan_parquet() workflow from the RFC.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Run Full Test Suite and Type Checks

**Files:**
- No new files

**Step 1: Run all scenario tests**

```bash
uv run pytest tests/scenarios/ -v
```

Expected: All tests PASS

**Step 2: Run type checker**

```bash
uv run mypy gaspatchio_core/scenarios/
```

Expected: No errors

**Step 3: Run full test suite to check for regressions**

```bash
uv run pytest -x --tb=short
```

Expected: All tests PASS

**Step 4: Final commit for Phase 1**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(scenarios): complete Phase 1 - core scenario support

RFC 27 Phase 1 complete. Provides:
- with_scenarios(af, scenario_ids) for cross-join expansion
- Table.from_scenario_files() for per-scenario file loading
- Table.from_scenario_template() for templated file patterns
- Full test coverage for scenario workflows

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2: Validation, Error Handling & Polish

### Task 9: Add Clear Error Messages for Missing Scenarios

**Files:**
- Modify: `tests/scenarios/test_with_scenarios.py`
- Modify: `gaspatchio_core/scenarios/_with_scenarios.py`

**Step 1: Write the failing test**

Add to `tests/scenarios/test_with_scenarios.py`:

```python
class TestWithScenariosValidation:
    """Tests for input validation and error messages."""

    def test_empty_scenario_list_raises(self):
        """Empty scenario list should raise ValueError."""
        af = ActuarialFrame({"x": [1]})
        with pytest.raises(ValueError, match="at least one scenario"):
            with_scenarios(af, [])

    def test_duplicate_scenarios_raises(self):
        """Duplicate scenario IDs should raise ValueError."""
        af = ActuarialFrame({"x": [1]})
        with pytest.raises(ValueError, match="duplicate"):
            with_scenarios(af, ["A", "B", "A"])

    def test_scenario_column_conflict_raises(self):
        """Should raise if scenario_column already exists in frame."""
        af = ActuarialFrame({"scenario_id": [1], "x": [2]})
        with pytest.raises(ValueError, match="already exists"):
            with_scenarios(af, ["A", "B"])
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py::TestWithScenariosValidation -v`
Expected: FAIL

**Step 3: Add validation to with_scenarios()**

Update `gaspatchio_core/scenarios/_with_scenarios.py`:

Add validation at the start of the function, after the docstring:

```python
def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
    categorical: bool = False,
) -> ActuarialFrame:
    """...(existing docstring)..."""
    # Import here to avoid circular dependency
    from ..frame import ActuarialFrame

    # === Validation ===
    if not scenario_ids:
        raise ValueError(
            "with_scenarios() requires at least one scenario ID. "
            "For single-scenario models, use: with_scenarios(af, ['DETERMINISTIC'])"
        )

    if len(scenario_ids) != len(set(scenario_ids)):
        duplicates = [s for s in scenario_ids if scenario_ids.count(s) > 1]
        raise ValueError(
            f"with_scenarios() received duplicate scenario IDs: {set(duplicates)}. "
            "Each scenario ID must be unique."
        )

    # Check if scenario_column already exists
    af_columns = af.get_column_order()
    if scenario_column in af_columns:
        raise ValueError(
            f"Column '{scenario_column}' already exists in ActuarialFrame. "
            f"Either rename the existing column or use a different scenario_column name. "
            f"Existing columns: {af_columns}"
        )

    # ... rest of existing implementation ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py::TestWithScenariosValidation -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_with_scenarios.py tests/scenarios/test_with_scenarios.py
git commit -m "$(cat <<'EOF'
feat(scenarios): add input validation for with_scenarios()

Validates:
- Non-empty scenario list with helpful error message
- No duplicate scenario IDs
- Scenario column doesn't conflict with existing columns

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Add batch_scenarios() Helper

**Files:**
- Create: `gaspatchio_core/scenarios/_batching.py`
- Modify: `gaspatchio_core/scenarios/__init__.py`
- Create: `tests/scenarios/test_batching.py`

**Step 1: Write the failing test**

Create: `tests/scenarios/test_batching.py`

```python
# ABOUTME: Tests for scenario batching utilities.
# ABOUTME: Verifies batch_scenarios() yields correct scenario ID batches.

import pytest

from gaspatchio_core.scenarios import batch_scenarios


class TestBatchScenarios:
    """Tests for batch_scenarios() helper."""

    def test_yields_batches_of_correct_size(self):
        """Should yield batches of batch_size."""
        scenario_ids = list(range(1, 11))  # 10 scenarios
        batches = list(batch_scenarios(scenario_ids, batch_size=3))

        assert len(batches) == 4  # 3 + 3 + 3 + 1
        assert batches[0] == [1, 2, 3]
        assert batches[1] == [4, 5, 6]
        assert batches[2] == [7, 8, 9]
        assert batches[3] == [10]

    def test_single_batch_when_smaller_than_batch_size(self):
        """When scenarios < batch_size, yield single batch."""
        scenario_ids = ["A", "B", "C"]
        batches = list(batch_scenarios(scenario_ids, batch_size=10))

        assert len(batches) == 1
        assert batches[0] == ["A", "B", "C"]

    def test_exact_batch_size_division(self):
        """When scenarios divides evenly by batch_size."""
        scenario_ids = list(range(1, 7))  # 6 scenarios
        batches = list(batch_scenarios(scenario_ids, batch_size=2))

        assert len(batches) == 3
        assert all(len(b) == 2 for b in batches)

    def test_default_batch_size(self):
        """Default batch_size should be 1000."""
        scenario_ids = list(range(1, 101))  # 100 scenarios
        batches = list(batch_scenarios(scenario_ids))

        # 100 < 1000, so should be single batch
        assert len(batches) == 1

    def test_works_with_string_ids(self):
        """Should work with string scenario IDs."""
        scenario_ids = [f"SCEN_{i}" for i in range(5)]
        batches = list(batch_scenarios(scenario_ids, batch_size=2))

        assert len(batches) == 3
        assert batches[0] == ["SCEN_0", "SCEN_1"]

    def test_is_iterator(self):
        """Should return an iterator, not a list."""
        from collections.abc import Iterator

        scenario_ids = [1, 2, 3]
        result = batch_scenarios(scenario_ids, batch_size=2)

        assert isinstance(result, Iterator)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_batching.py -v`
Expected: FAIL with "ImportError: cannot import name 'batch_scenarios'"

**Step 3: Implement batch_scenarios()**

Create: `gaspatchio_core/scenarios/_batching.py`

```python
# ABOUTME: Batching utilities for large-scale scenario processing.
# ABOUTME: Provides batch_scenarios() for chunked scenario execution.

from __future__ import annotations

from collections.abc import Iterator
from typing import TypeVar

T = TypeVar("T", str, int)


def batch_scenarios(
    scenario_ids: list[T],
    batch_size: int = 1000,
) -> Iterator[list[T]]:
    """
    Yield scenario IDs in batches.

    For very large scenario sets (10K+), processing all scenarios at once
    may exceed available memory. This helper yields scenario IDs in chunks
    for explicit batched processing.

    Args:
        scenario_ids: Full list of scenario IDs
        batch_size: Number of scenarios per batch (default: 1000)

    Yields:
        Lists of scenario IDs, each of length <= batch_size

    Examples:
    --------
    **Batched execution pattern:**

    ```python
    from gaspatchio_core import ActuarialFrame, with_scenarios
    from gaspatchio_core.scenarios import batch_scenarios
    import polars as pl

    scenario_ids = list(range(1, 10001))  # 10K scenarios
    all_results = []

    for batch_ids in batch_scenarios(scenario_ids, batch_size=1000):
        # Process batch
        af = ActuarialFrame(pl.scan_parquet("model_points.parquet"))
        af = with_scenarios(af, batch_ids)
        result = main(af)

        # Aggregate this batch
        batch_totals = result.collect().group_by("scenario_id").agg(
            pl.col("pv_net_cf").sum()
        )
        all_results.append(batch_totals)

    # Combine all batches
    final = pl.concat(all_results)
    ```
    """
    for i in range(0, len(scenario_ids), batch_size):
        yield scenario_ids[i : i + batch_size]
```

Update: `gaspatchio_core/scenarios/__init__.py`

```python
# ABOUTME: Scenario support module for multi-scenario actuarial model execution.
# ABOUTME: Provides with_scenarios() for cross-joining ActuarialFrames with scenario IDs.

from ._batching import batch_scenarios
from ._with_scenarios import with_scenarios

__all__ = ["batch_scenarios", "with_scenarios"]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_batching.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_batching.py gaspatchio_core/scenarios/__init__.py tests/scenarios/test_batching.py
git commit -m "$(cat <<'EOF'
feat(scenarios): add batch_scenarios() for chunked processing

Helper for processing large scenario sets in memory-bounded batches.
Useful when Polars streaming isn't sufficient or recovery points are needed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Export batch_scenarios from gaspatchio_core

**Files:**
- Modify: `gaspatchio_core/__init__.py`
- Modify: `tests/scenarios/test_batching.py`

**Step 1: Write the failing test**

Add to `tests/scenarios/test_batching.py`:

```python
def test_import_from_top_level():
    """batch_scenarios should be importable from gaspatchio_core."""
    from gaspatchio_core import batch_scenarios
    assert callable(batch_scenarios)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_batching.py::test_import_from_top_level -v`
Expected: FAIL

**Step 3: Add export to __init__.py**

Modify: `gaspatchio_core/__init__.py`

Update the import line:

```python
from .scenarios import batch_scenarios, with_scenarios
```

Add to `__all__`:

```python
    "batch_scenarios",
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_batching.py::test_import_from_top_level -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/__init__.py tests/scenarios/test_batching.py
git commit -m "$(cat <<'EOF'
feat(scenarios): export batch_scenarios from gaspatchio_core

batch_scenarios is now importable directly:
from gaspatchio_core import batch_scenarios

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Add Docstring Examples to with_scenarios

**Files:**
- Modify: `gaspatchio_core/scenarios/_with_scenarios.py`

**Step 1: Update docstring with testable examples**

The docstring already has examples. Ensure they are pytest-doctest compatible by running:

```bash
uv run pytest gaspatchio_core/scenarios/_with_scenarios.py --doctest-modules -v
```

If examples fail, adjust them to be self-contained and correct.

**Step 2: Commit if changes needed**

```bash
git add gaspatchio_core/scenarios/_with_scenarios.py
git commit -m "$(cat <<'EOF'
docs(scenarios): ensure docstring examples are testable

Updated with_scenarios() docstring examples to be pytest-doctest
compatible.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Final Test Suite Run and Documentation Check

**Files:**
- No new files

**Step 1: Run full test suite**

```bash
uv run pytest -v --tb=short
```

Expected: All tests PASS

**Step 2: Run type checker on all scenario code**

```bash
uv run mypy gaspatchio_core/scenarios/
uv run pyright gaspatchio_core/scenarios/
```

Expected: No errors

**Step 3: Run docstring tests**

```bash
uv run pytest --doctest-modules gaspatchio_core/scenarios/ -v
```

Expected: PASS (or no doctest issues)

**Step 4: Verify imports work correctly**

```bash
uv run python -c "from gaspatchio_core import with_scenarios, batch_scenarios; print('Imports OK')"
```

Expected: "Imports OK"

**Step 5: Final commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(scenarios): complete Phase 2 - validation and polish

RFC 27 Phase 2 complete. All scenario functionality tested and
type-checked. Ready for production use.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3: Ad-hoc Shock Specifications (LLM-Friendly)

This phase implements declarative shock specifications that allow LLMs to generate scenarios from natural language questions without modifying model code.

### Task 14: Create Shock Specification Data Model

**Files:**
- Create: `gaspatchio_core/scenarios/_shocks.py`
- Create: `tests/scenarios/test_shocks.py`

**Step 1: Write the failing test**

Create: `tests/scenarios/test_shocks.py`

```python
# ABOUTME: Tests for ad-hoc shock specification parsing and application.
# ABOUTME: Verifies shock configs can modify assumption table values at runtime.

import polars as pl
import pytest
from pydantic import ValidationError

from gaspatchio_core.scenarios._shocks import (
    ShockSpec,
    ScenarioSpec,
    parse_scenario_config,
)


class TestShockSpecModel:
    """Tests for ShockSpec Pydantic model."""

    def test_add_shock(self):
        """Test add operation shock."""
        spec = ShockSpec(table="discount_rates", add=0.005)
        assert spec.table == "discount_rates"
        assert spec.add == 0.005
        assert spec.multiply is None
        assert spec.set is None

    def test_multiply_shock(self):
        """Test multiply operation shock."""
        spec = ShockSpec(table="lapse_rates", multiply=1.25)
        assert spec.multiply == 1.25

    def test_set_shock(self):
        """Test set operation shock."""
        spec = ShockSpec(table="expense_rates", set=0.0)
        assert spec.set == 0.0

    def test_shock_with_filter(self):
        """Test shock with row filter."""
        spec = ShockSpec(
            table="lapse_rates",
            filter={"duration": {"lte": 3}},
            multiply=1.25,
        )
        assert spec.filter == {"duration": {"lte": 3}}

    def test_multiple_operations_raises(self):
        """Only one operation allowed per shock."""
        with pytest.raises(ValidationError):
            ShockSpec(table="rates", add=0.01, multiply=1.1)


class TestScenarioSpecModel:
    """Tests for ScenarioSpec Pydantic model."""

    def test_base_scenario_no_shocks(self):
        """BASE scenario with no modifications."""
        spec = ScenarioSpec(id="BASE")
        assert spec.id == "BASE"
        assert spec.shocks == []

    def test_scenario_with_single_shock(self):
        """Scenario with one shock."""
        spec = ScenarioSpec(
            id="RATES_UP_50BPS",
            shocks=[ShockSpec(table="discount_rates", add=0.005)],
        )
        assert len(spec.shocks) == 1
        assert spec.shocks[0].add == 0.005

    def test_scenario_with_multiple_shocks(self):
        """Scenario with composable shocks."""
        spec = ScenarioSpec(
            id="COMBINED_STRESS",
            shocks=[
                ShockSpec(table="discount_rates", add=0.005),
                ShockSpec(table="lapse_rates", filter={"duration": {"lte": 3}}, multiply=1.25),
            ],
        )
        assert len(spec.shocks) == 2


class TestParseScenarioConfig:
    """Tests for parse_scenario_config() function."""

    def test_parse_list_of_dicts(self):
        """Parse scenario config from list of dicts."""
        config = [
            {"id": "BASE"},
            {
                "id": "RATES_UP",
                "shocks": [{"table": "discount_rates", "add": 0.005}],
            },
        ]
        specs = parse_scenario_config(config)
        assert len(specs) == 2
        assert specs[0].id == "BASE"
        assert specs[1].id == "RATES_UP"
        assert specs[1].shocks[0].add == 0.005

    def test_parse_scenario_ids_only(self):
        """String-only config creates scenarios without shocks."""
        config = ["BASE", "UP", "DOWN"]
        specs = parse_scenario_config(config)
        assert len(specs) == 3
        assert all(s.shocks == [] for s in specs)

    def test_mixed_config(self):
        """Mix of string IDs and full specs."""
        config = [
            "BASE",
            {"id": "STRESS", "shocks": [{"table": "rates", "multiply": 0.8}]},
        ]
        specs = parse_scenario_config(config)
        assert specs[0].id == "BASE"
        assert specs[1].id == "STRESS"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_shocks.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement shock data models**

Create: `gaspatchio_core/scenarios/_shocks.py`

```python
# ABOUTME: Data models and parsing for ad-hoc shock specifications.
# ABOUTME: Enables LLM-generated scenarios without modifying model code.

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator, model_validator


class ShockSpec(BaseModel):
    """
    Specification for a single shock to an assumption table.

    Exactly one operation (add, multiply, set, replace_with) must be specified.
    Optional filter targets specific rows in the table.
    """

    table: str
    filter: dict[str, Any] | None = None
    add: float | None = None
    multiply: float | None = None
    set: float | None = None
    replace_with: str | None = None

    @model_validator(mode="after")
    def exactly_one_operation(self) -> "ShockSpec":
        """Validate exactly one operation is specified."""
        ops = [self.add, self.multiply, self.set, self.replace_with]
        specified = sum(1 for op in ops if op is not None)
        if specified != 1:
            raise ValueError(
                f"Exactly one operation (add, multiply, set, replace_with) must be specified, "
                f"got {specified}. Shock: table='{self.table}'"
            )
        return self


class ScenarioSpec(BaseModel):
    """
    Specification for a single scenario.

    A scenario has an ID and zero or more shocks to apply to assumption tables.
    """

    id: str
    shocks: list[ShockSpec] = []


class SweepSpec(BaseModel):
    """
    Specification for a sensitivity sweep across a parameter range.

    Expands to multiple scenarios with incrementally varying shock values.
    """

    id_template: str
    table: str
    filter: dict[str, Any] | None = None
    add_range: dict[str, float] | None = None  # {"from_bps": -100, "to_bps": 100, "step_bps": 25}
    multiply_range: dict[str, float] | None = None  # {"from": 0.8, "to": 1.2, "step": 0.1}

    @model_validator(mode="after")
    def exactly_one_range(self) -> "SweepSpec":
        """Validate exactly one range is specified."""
        ranges = [self.add_range, self.multiply_range]
        specified = sum(1 for r in ranges if r is not None)
        if specified != 1:
            raise ValueError(
                "Exactly one range (add_range, multiply_range) must be specified."
            )
        return self

    def expand(self) -> list[ScenarioSpec]:
        """Expand sweep into individual scenario specs."""
        scenarios = []

        if self.add_range:
            from_bps = self.add_range["from_bps"]
            to_bps = self.add_range["to_bps"]
            step_bps = self.add_range["step_bps"]

            bps = from_bps
            while bps <= to_bps:
                scenario_id = self.id_template.format(bps=bps)
                shock = ShockSpec(
                    table=self.table,
                    filter=self.filter,
                    add=bps / 10000,  # Convert bps to decimal
                )
                scenarios.append(ScenarioSpec(id=scenario_id, shocks=[shock]))
                bps += step_bps

        elif self.multiply_range:
            from_val = self.multiply_range["from"]
            to_val = self.multiply_range["to"]
            step_val = self.multiply_range["step"]

            val = from_val
            while val <= to_val + 1e-9:  # Handle float comparison
                # Format multiplier for ID (e.g., 0.8 -> "080", 1.2 -> "120")
                scenario_id = self.id_template.format(mult=int(val * 100))
                shock = ShockSpec(
                    table=self.table,
                    filter=self.filter,
                    multiply=val,
                )
                scenarios.append(ScenarioSpec(id=scenario_id, shocks=[shock]))
                val += step_val

        return scenarios


def parse_scenario_config(
    config: list[str | dict[str, Any]],
) -> list[ScenarioSpec]:
    """
    Parse a scenario configuration into ScenarioSpec objects.

    Accepts:
    - List of scenario ID strings: ["BASE", "UP", "DOWN"]
    - List of scenario spec dicts: [{"id": "BASE"}, {"id": "STRESS", "shocks": [...]}]
    - Mixed list

    Args:
        config: Scenario configuration in various formats

    Returns:
        List of ScenarioSpec objects

    Examples:
    --------
    ```python
    # Simple string IDs
    specs = parse_scenario_config(["BASE", "UP", "DOWN"])

    # Full specs with shocks
    specs = parse_scenario_config([
        {"id": "BASE"},
        {"id": "RATES_UP", "shocks": [{"table": "discount_rates", "add": 0.005}]},
    ])

    # With sweep
    specs = parse_scenario_config([
        {"id": "BASE"},
        {"sweep": {"id_template": "RATES_{bps:+04d}BPS", "table": "rates", "add_range": {...}}},
    ])
    ```
    """
    scenarios = []

    for item in config:
        if isinstance(item, str):
            # Simple scenario ID
            scenarios.append(ScenarioSpec(id=item))
        elif isinstance(item, dict):
            if "sweep" in item:
                # Sweep specification - expand to multiple scenarios
                sweep = SweepSpec(**item["sweep"])
                scenarios.extend(sweep.expand())
            else:
                # Full scenario specification
                scenarios.append(ScenarioSpec(**item))
        else:
            raise TypeError(f"Invalid scenario config item: {item}")

    return scenarios
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_shocks.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_shocks.py tests/scenarios/test_shocks.py
git commit -m "$(cat <<'EOF'
feat(scenarios): add shock specification data models

Pydantic models for declarative shock specifications:
- ShockSpec: single shock (add, multiply, set, replace_with)
- ScenarioSpec: scenario with optional shocks
- SweepSpec: sensitivity sweep expansion
- parse_scenario_config() for parsing mixed configs

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: Implement Shock Application to Tables

**Files:**
- Modify: `gaspatchio_core/scenarios/_shocks.py`
- Modify: `tests/scenarios/test_shocks.py`

**Step 1: Write the failing test**

Add to `tests/scenarios/test_shocks.py`:

```python
from gaspatchio_core.scenarios._shocks import apply_shocks_to_table
from gaspatchio_core.assumptions import Table


class TestApplyShocksToTable:
    """Tests for applying shocks to assumption tables."""

    @pytest.fixture
    def base_rates_table(self) -> Table:
        """Create a base rates table for testing."""
        df = pl.DataFrame({
            "year": [1, 2, 3, 4, 5],
            "rate": [0.03, 0.035, 0.04, 0.045, 0.05],
        })
        return Table(
            name="test_rates_shock",
            source=df,
            dimensions={"year": "year"},
            value="rate",
        )

    def test_add_shock_to_all_rows(self, base_rates_table):
        """Add shock applies to all rows."""
        shock = ShockSpec(table="test_rates_shock", add=0.01)
        shocked_df = apply_shocks_to_table(base_rates_table, [shock])

        original = base_rates_table.to_dataframe()["rate"].to_list()
        expected = [r + 0.01 for r in original]
        assert shocked_df["rate"].to_list() == pytest.approx(expected)

    def test_multiply_shock(self, base_rates_table):
        """Multiply shock scales values."""
        shock = ShockSpec(table="test_rates_shock", multiply=1.5)
        shocked_df = apply_shocks_to_table(base_rates_table, [shock])

        original = base_rates_table.to_dataframe()["rate"].to_list()
        expected = [r * 1.5 for r in original]
        assert shocked_df["rate"].to_list() == pytest.approx(expected)

    def test_set_shock(self, base_rates_table):
        """Set shock overrides values."""
        shock = ShockSpec(table="test_rates_shock", set=0.05)
        shocked_df = apply_shocks_to_table(base_rates_table, [shock])

        assert all(r == 0.05 for r in shocked_df["rate"].to_list())

    def test_shock_with_filter(self, base_rates_table):
        """Filter restricts shock to matching rows."""
        # Only shock years <= 3
        shock = ShockSpec(
            table="test_rates_shock",
            filter={"year": {"lte": 3}},
            add=0.01,
        )
        shocked_df = apply_shocks_to_table(base_rates_table, [shock])

        # Years 1-3 should be shocked, years 4-5 unchanged
        result = shocked_df.sort("year")["rate"].to_list()
        assert result[0] == pytest.approx(0.04)  # 0.03 + 0.01
        assert result[1] == pytest.approx(0.045)  # 0.035 + 0.01
        assert result[2] == pytest.approx(0.05)  # 0.04 + 0.01
        assert result[3] == pytest.approx(0.045)  # unchanged
        assert result[4] == pytest.approx(0.05)  # unchanged

    def test_composable_shocks(self, base_rates_table):
        """Multiple shocks apply in sequence."""
        shocks = [
            ShockSpec(table="test_rates_shock", add=0.01),
            ShockSpec(table="test_rates_shock", multiply=2.0),
        ]
        shocked_df = apply_shocks_to_table(base_rates_table, shocks)

        # (0.03 + 0.01) * 2 = 0.08
        first_rate = shocked_df.sort("year")["rate"].to_list()[0]
        assert first_rate == pytest.approx(0.08)

    def test_shock_wrong_table_ignored(self, base_rates_table):
        """Shocks for other tables are ignored."""
        shock = ShockSpec(table="other_table", add=0.99)
        shocked_df = apply_shocks_to_table(base_rates_table, [shock])

        # Should be unchanged
        original = base_rates_table.to_dataframe()["rate"].to_list()
        assert shocked_df["rate"].to_list() == pytest.approx(original)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_shocks.py::TestApplyShocksToTable -v`
Expected: FAIL with "ImportError: cannot import name 'apply_shocks_to_table'"

**Step 3: Implement apply_shocks_to_table()**

Add to `gaspatchio_core/scenarios/_shocks.py`:

```python
import polars as pl

from ..assumptions import Table


def _build_filter_expr(filter_spec: dict[str, Any]) -> pl.Expr:
    """
    Build a Polars filter expression from a filter specification.

    Filter spec format:
    - Simple equality: {"column": value}
    - Comparison: {"column": {"gte": value}} or {"lte": value} or {"between": [low, high]}
    - Multiple conditions are ANDed together
    """
    conditions = []

    for column, condition in filter_spec.items():
        if isinstance(condition, dict):
            # Comparison operators
            if "gte" in condition:
                conditions.append(pl.col(column) >= condition["gte"])
            if "lte" in condition:
                conditions.append(pl.col(column) <= condition["lte"])
            if "gt" in condition:
                conditions.append(pl.col(column) > condition["gt"])
            if "lt" in condition:
                conditions.append(pl.col(column) < condition["lt"])
            if "between" in condition:
                low, high = condition["between"]
                conditions.append(pl.col(column).is_between(low, high))
            if "in" in condition:
                conditions.append(pl.col(column).is_in(condition["in"]))
        else:
            # Simple equality
            conditions.append(pl.col(column) == condition)

    if not conditions:
        return pl.lit(True)

    result = conditions[0]
    for cond in conditions[1:]:
        result = result & cond
    return result


def apply_shocks_to_table(
    table: Table,
    shocks: list[ShockSpec],
) -> pl.DataFrame:
    """
    Apply shocks to a Table and return the modified DataFrame.

    Shocks are applied in sequence. Only shocks matching the table name are applied.

    Args:
        table: The assumption Table to shock
        shocks: List of ShockSpec objects

    Returns:
        DataFrame with shocked values
    """
    df = table.to_dataframe()
    value_col = table._value

    for shock in shocks:
        # Skip shocks for other tables
        if shock.table != table._name:
            continue

        # Build filter expression
        if shock.filter:
            mask = _build_filter_expr(shock.filter)
        else:
            mask = pl.lit(True)

        # Apply the operation
        if shock.add is not None:
            df = df.with_columns(
                pl.when(mask)
                .then(pl.col(value_col) + shock.add)
                .otherwise(pl.col(value_col))
                .alias(value_col)
            )
        elif shock.multiply is not None:
            df = df.with_columns(
                pl.when(mask)
                .then(pl.col(value_col) * shock.multiply)
                .otherwise(pl.col(value_col))
                .alias(value_col)
            )
        elif shock.set is not None:
            df = df.with_columns(
                pl.when(mask)
                .then(pl.lit(shock.set))
                .otherwise(pl.col(value_col))
                .alias(value_col)
            )

    return df
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_shocks.py::TestApplyShocksToTable -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_shocks.py tests/scenarios/test_shocks.py
git commit -m "$(cat <<'EOF'
feat(scenarios): implement apply_shocks_to_table()

Applies shock specifications to assumption tables:
- add, multiply, set operations
- Filter expressions for targeted shocks
- Composable shocks applied in sequence

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: Implement describe_scenarios() for Audit Trail

**Files:**
- Create: `gaspatchio_core/scenarios/_audit.py`
- Create: `tests/scenarios/test_audit.py`
- Modify: `gaspatchio_core/scenarios/__init__.py`

**Step 1: Write the failing test**

Create: `tests/scenarios/test_audit.py`

```python
# ABOUTME: Tests for scenario description and audit trail functionality.
# ABOUTME: Verifies describe_scenarios() produces human-readable output.

import pytest

from gaspatchio_core.scenarios import describe_scenarios
from gaspatchio_core.scenarios._shocks import ScenarioSpec, ShockSpec


class TestDescribeScenarios:
    """Tests for describe_scenarios() function."""

    def test_describe_base_scenario(self):
        """BASE scenario shows no modifications."""
        config = [{"id": "BASE"}]
        output = describe_scenarios(config)
        assert "BASE" in output
        assert "No modifications" in output or "no shocks" in output.lower()

    def test_describe_add_shock(self):
        """Add shock shows table and operation."""
        config = [
            {"id": "BASE"},
            {"id": "RATES_UP", "shocks": [{"table": "discount_rates", "add": 0.005}]},
        ]
        output = describe_scenarios(config)
        assert "RATES_UP" in output
        assert "discount_rates" in output
        assert "+ 0.005" in output or "+0.005" in output

    def test_describe_multiply_shock(self):
        """Multiply shock shows factor."""
        config = [
            {"id": "LAPSE_STRESS", "shocks": [{"table": "lapse_rates", "multiply": 1.25}]},
        ]
        output = describe_scenarios(config)
        assert "× 1.25" in output or "* 1.25" in output or "multiply" in output.lower()

    def test_describe_filtered_shock(self):
        """Filtered shock shows condition."""
        config = [
            {
                "id": "EARLY_LAPSE",
                "shocks": [
                    {"table": "lapse_rates", "filter": {"duration": {"lte": 3}}, "multiply": 1.5}
                ],
            },
        ]
        output = describe_scenarios(config)
        assert "duration" in output.lower()
        assert "≤ 3" in output or "<= 3" in output or "lte" in output.lower()

    def test_describe_multiple_shocks(self):
        """Multiple shocks in one scenario."""
        config = [
            {
                "id": "COMBINED",
                "shocks": [
                    {"table": "rates", "add": 0.01},
                    {"table": "lapse", "multiply": 1.2},
                ],
            },
        ]
        output = describe_scenarios(config)
        assert "rates" in output
        assert "lapse" in output

    def test_describe_returns_string(self):
        """Output is a string."""
        config = [{"id": "BASE"}]
        output = describe_scenarios(config)
        assert isinstance(output, str)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_audit.py -v`
Expected: FAIL with "ImportError"

**Step 3: Implement describe_scenarios()**

Create: `gaspatchio_core/scenarios/_audit.py`

```python
# ABOUTME: Audit trail and description utilities for scenario configurations.
# ABOUTME: Provides describe_scenarios() for human-readable shock summaries.

from __future__ import annotations

from typing import Any

from ._shocks import parse_scenario_config, ScenarioSpec, ShockSpec


def _format_filter(filter_spec: dict[str, Any]) -> str:
    """Format a filter specification as human-readable text."""
    parts = []
    for column, condition in filter_spec.items():
        if isinstance(condition, dict):
            for op, value in condition.items():
                if op == "gte":
                    parts.append(f"{column} ≥ {value}")
                elif op == "lte":
                    parts.append(f"{column} ≤ {value}")
                elif op == "gt":
                    parts.append(f"{column} > {value}")
                elif op == "lt":
                    parts.append(f"{column} < {value}")
                elif op == "between":
                    parts.append(f"{value[0]} ≤ {column} ≤ {value[1]}")
                elif op == "in":
                    parts.append(f"{column} in {value}")
        else:
            parts.append(f"{column} = {condition}")
    return " AND ".join(parts) if parts else ""


def _format_shock(shock: ShockSpec) -> str:
    """Format a single shock as human-readable text."""
    parts = [f"  - {shock.table}"]

    if shock.add is not None:
        parts.append(f"+ {shock.add}")
    elif shock.multiply is not None:
        parts.append(f"× {shock.multiply}")
    elif shock.set is not None:
        parts.append(f"= {shock.set}")
    elif shock.replace_with is not None:
        parts.append(f"replace with {shock.replace_with}")

    if shock.filter:
        parts.append(f"where {_format_filter(shock.filter)}")

    return " ".join(parts)


def describe_scenarios(
    config: list[str | dict[str, Any]],
) -> str:
    """
    Generate a human-readable description of scenario configurations.

    Useful for audit trails, logging, and presenting scenario configurations
    to users for verification.

    Args:
        config: Scenario configuration (same format as with_scenarios() accepts)

    Returns:
        Multi-line string describing each scenario and its shocks

    Examples:
    --------
    ```python
    from gaspatchio_core.scenarios import describe_scenarios

    config = [
        {"id": "BASE"},
        {"id": "RATES_UP_50BPS", "shocks": [{"table": "discount_rates", "add": 0.005}]},
    ]

    print(describe_scenarios(config))
    # Output:
    # BASE: No modifications
    # RATES_UP_50BPS:
    #   - discount_rates + 0.005
    ```
    """
    specs = parse_scenario_config(config)
    lines = []

    for spec in specs:
        if not spec.shocks:
            lines.append(f"{spec.id}: No modifications")
        else:
            lines.append(f"{spec.id}:")
            for shock in spec.shocks:
                lines.append(_format_shock(shock))

    return "\n".join(lines)
```

Update `gaspatchio_core/scenarios/__init__.py`:

```python
# ABOUTME: Scenario support module for multi-scenario actuarial model execution.
# ABOUTME: Provides with_scenarios() for cross-joining ActuarialFrames with scenario IDs.

from ._audit import describe_scenarios
from ._batching import batch_scenarios
from ._shocks import parse_scenario_config, ScenarioSpec, ShockSpec, SweepSpec
from ._with_scenarios import with_scenarios

__all__ = [
    "batch_scenarios",
    "describe_scenarios",
    "parse_scenario_config",
    "ScenarioSpec",
    "ShockSpec",
    "SweepSpec",
    "with_scenarios",
]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_audit.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_audit.py gaspatchio_core/scenarios/__init__.py tests/scenarios/test_audit.py
git commit -m "$(cat <<'EOF'
feat(scenarios): add describe_scenarios() for audit trail

Human-readable description of scenario configurations showing:
- Scenario IDs
- Shock operations (add, multiply, set)
- Filter conditions

Useful for logging, audit trails, and user verification.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: Implement sensitivity_analysis() for Sweep Results

**Files:**
- Create: `gaspatchio_core/scenarios/_sensitivity.py`
- Create: `tests/scenarios/test_sensitivity.py`
- Modify: `gaspatchio_core/scenarios/__init__.py`

**Step 1: Write the failing test**

Create: `tests/scenarios/test_sensitivity.py`

```python
# ABOUTME: Tests for sensitivity analysis of sweep results.
# ABOUTME: Verifies sensitivity_analysis() computes statistics across scenarios.

import polars as pl
import pytest

from gaspatchio_core.scenarios import sensitivity_analysis


class TestSensitivityAnalysis:
    """Tests for sensitivity_analysis() function."""

    @pytest.fixture
    def sweep_results(self) -> pl.DataFrame:
        """Sample sweep results for testing."""
        return pl.DataFrame({
            "scenario_id": [
                "RATES_-100BPS", "RATES_-075BPS", "RATES_-050BPS", "RATES_-025BPS",
                "RATES_+000BPS", "RATES_+025BPS", "RATES_+050BPS", "RATES_+075BPS", "RATES_+100BPS",
            ],
            "total_pv": [
                2800000, 2600000, 2400000, 2200000,
                2000000, 1800000, 1600000, 1400000, 1200000,
            ],
            "profit_margin": [
                1600000, 1575000, 1550000, 1525000,
                1500000, 1475000, 1450000, 1425000, 1400000,
            ],
        })

    def test_returns_dict_with_metrics(self, sweep_results):
        """Output contains metrics dict."""
        result = sensitivity_analysis(
            sweep_results,
            sweep_prefix="RATES_",
            metrics=["total_pv", "profit_margin"],
        )
        assert "metrics" in result
        assert "total_pv" in result["metrics"]
        assert "profit_margin" in result["metrics"]

    def test_computes_min_max(self, sweep_results):
        """Computes min/max values and scenarios."""
        result = sensitivity_analysis(
            sweep_results,
            sweep_prefix="RATES_",
            metrics=["total_pv"],
        )
        pv_stats = result["metrics"]["total_pv"]

        assert pv_stats["min"]["value"] == 1200000
        assert pv_stats["min"]["scenario"] == "RATES_+100BPS"
        assert pv_stats["max"]["value"] == 2800000
        assert pv_stats["max"]["scenario"] == "RATES_-100BPS"

    def test_computes_range(self, sweep_results):
        """Computes range of metric values."""
        result = sensitivity_analysis(
            sweep_results,
            sweep_prefix="RATES_",
            metrics=["total_pv"],
        )
        pv_stats = result["metrics"]["total_pv"]

        assert pv_stats["range"] == 1600000  # 2800000 - 1200000

    def test_extracts_parameter_from_scenario_id(self, sweep_results):
        """Extracts parameter values from scenario IDs."""
        result = sensitivity_analysis(
            sweep_results,
            sweep_prefix="RATES_",
            metrics=["total_pv"],
        )
        pv_stats = result["metrics"]["total_pv"]

        assert pv_stats["min"]["param"] == 100  # +100BPS
        assert pv_stats["max"]["param"] == -100  # -100BPS

    def test_includes_scenarios_count(self, sweep_results):
        """Reports number of scenarios analyzed."""
        result = sensitivity_analysis(
            sweep_results,
            sweep_prefix="RATES_",
            metrics=["total_pv"],
        )
        assert result["scenarios_count"] == 9

    def test_includes_data_dataframe(self, sweep_results):
        """Includes filtered DataFrame for custom analysis."""
        result = sensitivity_analysis(
            sweep_results,
            sweep_prefix="RATES_",
            metrics=["total_pv"],
        )
        assert "data" in result
        assert isinstance(result["data"], pl.DataFrame)

    def test_filters_by_prefix(self):
        """Only scenarios matching prefix are included."""
        df = pl.DataFrame({
            "scenario_id": ["RATES_+050BPS", "RATES_-050BPS", "LAPSE_HIGH", "BASE"],
            "value": [100, 200, 300, 400],
        })
        result = sensitivity_analysis(df, sweep_prefix="RATES_", metrics=["value"])

        assert result["scenarios_count"] == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_sensitivity.py -v`
Expected: FAIL

**Step 3: Implement sensitivity_analysis()**

Create: `gaspatchio_core/scenarios/_sensitivity.py`

```python
# ABOUTME: Sensitivity analysis utilities for sweep scenario results.
# ABOUTME: Computes statistics across parameter sweeps for risk analysis.

from __future__ import annotations

import re
from typing import Any

import polars as pl


def _extract_param_from_scenario_id(
    scenario_id: str,
    pattern: str | None = None,
) -> int | None:
    """
    Extract parameter value from scenario ID.

    Default pattern extracts signed integer before unit suffix.
    E.g., "RATES_+050BPS" -> 50, "RATES_-100BPS" -> -100
    """
    if pattern is None:
        # Default: extract signed integer before BPS/PCT/etc
        match = re.search(r"([+-]?\d+)(?:BPS|PCT|%|$)", scenario_id)
        if match:
            return int(match.group(1))
    else:
        match = re.search(pattern, scenario_id)
        if match:
            return int(match.group(1))
    return None


def sensitivity_analysis(
    df: pl.DataFrame,
    sweep_prefix: str,
    metrics: list[str],
    parameter_extractor: str | None = None,
    base_scenario: str | None = None,
) -> dict[str, Any]:
    """
    Summarize results across sweep scenarios.

    Computes min, max, range, mean, and sensitivity statistics for each metric
    across scenarios matching the sweep prefix.

    Args:
        df: DataFrame with scenario_id and metric columns (already grouped by scenario)
        sweep_prefix: Filter to scenarios starting with this prefix
        metrics: List of metric column names to summarize
        parameter_extractor: Regex to extract parameter value from scenario_id
                            Default: extracts signed integer before unit suffix
        base_scenario: Scenario ID to use as base for comparison (optional)

    Returns:
        Dictionary with summary statistics for each metric

    Examples:
    --------
    ```python
    from gaspatchio_core.scenarios import sensitivity_analysis

    # After running sweep and aggregating by scenario
    by_scenario = result.group_by("scenario_id").agg(
        pl.col("pv_net_cf").sum().alias("total_pv")
    ).collect()

    summary = sensitivity_analysis(
        by_scenario,
        sweep_prefix="RATES_",
        metrics=["total_pv"],
    )

    print(f"Range: {summary['metrics']['total_pv']['range']:,.0f}")
    print(f"Sensitivity: {summary['metrics']['total_pv']['sensitivity_per_unit']:,.0f} per bps")
    ```
    """
    # Filter to sweep scenarios
    sweep_df = df.filter(pl.col("scenario_id").str.starts_with(sweep_prefix))
    scenarios_count = len(sweep_df)

    if scenarios_count == 0:
        return {
            "scenarios_count": 0,
            "metrics": {},
            "data": sweep_df,
        }

    # Extract parameters from scenario IDs
    params = []
    for sid in sweep_df["scenario_id"].to_list():
        params.append(_extract_param_from_scenario_id(sid, parameter_extractor))

    sweep_df = sweep_df.with_columns(pl.Series("_param", params))

    # Compute statistics for each metric
    metrics_stats = {}
    for metric in metrics:
        metric_values = sweep_df.select([
            "scenario_id",
            "_param",
            pl.col(metric),
        ]).sort(metric)

        min_row = metric_values.row(0, named=True)
        max_row = metric_values.row(-1, named=True)

        min_val = min_row[metric]
        max_val = max_row[metric]
        range_val = max_val - min_val

        # Compute mean and std
        mean_val = sweep_df[metric].mean()
        std_val = sweep_df[metric].std()

        # Compute sensitivity (change in metric per unit param change)
        sensitivity = None
        if min_row["_param"] is not None and max_row["_param"] is not None:
            param_range = max_row["_param"] - min_row["_param"]
            if param_range != 0:
                # Note: min metric might be at max param, so use correlation direction
                sorted_by_param = sweep_df.sort("_param")
                first_metric = sorted_by_param[metric][0]
                last_metric = sorted_by_param[metric][-1]
                first_param = sorted_by_param["_param"][0]
                last_param = sorted_by_param["_param"][-1]
                if last_param != first_param:
                    sensitivity = (last_metric - first_metric) / (last_param - first_param)

        # Get base value if specified
        base_val = None
        if base_scenario:
            base_rows = sweep_df.filter(pl.col("scenario_id") == base_scenario)
            if len(base_rows) > 0:
                base_val = base_rows[metric][0]

        metrics_stats[metric] = {
            "min": {
                "scenario": min_row["scenario_id"],
                "param": min_row["_param"],
                "value": min_val,
            },
            "max": {
                "scenario": max_row["scenario_id"],
                "param": max_row["_param"],
                "value": max_val,
            },
            "base": base_val,
            "mean": mean_val,
            "std": std_val,
            "range": range_val,
            "sensitivity_per_unit": sensitivity,
        }

    return {
        "scenarios_count": scenarios_count,
        "metrics": metrics_stats,
        "data": sweep_df.drop("_param"),
    }
```

Update `gaspatchio_core/scenarios/__init__.py`:

```python
# ABOUTME: Scenario support module for multi-scenario actuarial model execution.
# ABOUTME: Provides with_scenarios() for cross-joining ActuarialFrames with scenario IDs.

from ._audit import describe_scenarios
from ._batching import batch_scenarios
from ._sensitivity import sensitivity_analysis
from ._shocks import parse_scenario_config, ScenarioSpec, ShockSpec, SweepSpec
from ._with_scenarios import with_scenarios

__all__ = [
    "batch_scenarios",
    "describe_scenarios",
    "parse_scenario_config",
    "ScenarioSpec",
    "sensitivity_analysis",
    "ShockSpec",
    "SweepSpec",
    "with_scenarios",
]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_sensitivity.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_sensitivity.py gaspatchio_core/scenarios/__init__.py tests/scenarios/test_sensitivity.py
git commit -m "$(cat <<'EOF'
feat(scenarios): add sensitivity_analysis() for sweep results

Summarizes sweep scenario results:
- Min/max values with scenarios and parameters
- Range, mean, std statistics
- Sensitivity per unit parameter change
- Filtered DataFrame for custom analysis

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: Integrate Shocks with with_scenarios()

**Files:**
- Modify: `gaspatchio_core/scenarios/_with_scenarios.py`
- Modify: `tests/scenarios/test_with_scenarios.py`

**Step 1: Write the failing test**

Add to `tests/scenarios/test_with_scenarios.py`:

```python
class TestWithScenariosShockConfig:
    """Tests for with_scenarios() accepting shock configurations."""

    def test_accepts_shock_config(self):
        """with_scenarios can accept shock configuration dicts."""
        af = ActuarialFrame({"x": [1]})
        config = [
            {"id": "BASE"},
            {"id": "STRESS", "shocks": [{"table": "rates", "add": 0.01}]},
        ]
        result = with_scenarios(af, config)
        df = result.collect()

        assert len(df) == 2
        assert set(df["scenario_id"].to_list()) == {"BASE", "STRESS"}

    def test_accepts_sweep_config(self):
        """with_scenarios can accept sweep configuration."""
        af = ActuarialFrame({"x": [1]})
        config = [
            {"id": "BASE"},
            {
                "sweep": {
                    "id_template": "RATES_{bps:+04d}BPS",
                    "table": "discount_rates",
                    "add_range": {"from_bps": -50, "to_bps": 50, "step_bps": 25},
                }
            },
        ]
        result = with_scenarios(af, config)
        df = result.collect()

        # BASE + 5 sweep scenarios (-50, -25, 0, +25, +50)
        assert len(df) == 6

    def test_mixed_string_and_config(self):
        """Mix of string IDs and config dicts."""
        af = ActuarialFrame({"x": [1]})
        config = [
            "BASE",
            {"id": "STRESS", "shocks": []},
        ]
        result = with_scenarios(af, config)
        assert len(result.collect()) == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py::TestWithScenariosShockConfig -v`
Expected: FAIL (current implementation only accepts list[str] | list[int])

**Step 3: Update with_scenarios() to accept config**

Update `gaspatchio_core/scenarios/_with_scenarios.py`:

```python
# ABOUTME: Implementation of with_scenarios() for scenario expansion.
# ABOUTME: Cross-joins ActuarialFrame with scenario IDs to enable multi-scenario runs.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

from ._shocks import parse_scenario_config

if TYPE_CHECKING:
    from ..frame import ActuarialFrame


def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int] | list[dict[str, Any]],
    scenario_column: str = "scenario_id",
    categorical: bool = False,
) -> ActuarialFrame:
    """
    Expand ActuarialFrame across scenarios via cross-join.

    Creates a new ActuarialFrame with len(af) × len(scenario_ids) rows,
    preserving all original columns and adding a scenario_id column.

    This is the fundamental operation for running actuarial models across
    multiple economic scenarios in a single vectorized execution.

    Args:
        af: Input ActuarialFrame to expand
        scenario_ids: Scenario specification - can be:
            - List of scenario ID strings: ["BASE", "UP", "DOWN"]
            - List of scenario ID integers: [1, 2, 3, ...] (for stochastic)
            - List of scenario config dicts: [{"id": "BASE"}, {"id": "STRESS", "shocks": [...]}]
            - Mixed list of strings and config dicts
        scenario_column: Name for the scenario ID column (default: "scenario_id")
        categorical: If True and scenario_ids are strings, use Categorical dtype
                    for better join/groupby performance (default: False)

    Returns:
        ActuarialFrame with expanded rows and scenario_column added.

    Examples:
    --------
    **Basic scenario expansion:**

    ```python
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.scenarios import with_scenarios

    af = ActuarialFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})
    af = with_scenarios(af, ["BASE", "UP", "DOWN"])
    ```

    **With shock configuration (for LLM-generated scenarios):**

    ```python
    config = [
        {"id": "BASE"},
        {"id": "RATES_UP", "shocks": [{"table": "discount_rates", "add": 0.005}]},
    ]
    af = with_scenarios(af, config)
    ```

    **With sweep expansion:**

    ```python
    config = [
        {"id": "BASE"},
        {"sweep": {"id_template": "RATES_{bps:+04d}BPS", "table": "rates",
                   "add_range": {"from_bps": -100, "to_bps": 100, "step_bps": 25}}},
    ]
    af = with_scenarios(af, config)  # Expands to BASE + 9 sweep scenarios
    ```
    """
    # Import here to avoid circular dependency
    from ..frame import ActuarialFrame

    # Parse scenario config to extract IDs
    # Check if we have config dicts vs simple IDs
    if scenario_ids and isinstance(scenario_ids[0], dict):
        # Parse full config
        specs = parse_scenario_config(scenario_ids)
        extracted_ids = [spec.id for spec in specs]
    elif scenario_ids and isinstance(scenario_ids[0], str) and any(
        isinstance(s, dict) for s in scenario_ids
    ):
        # Mixed list
        specs = parse_scenario_config(scenario_ids)
        extracted_ids = [spec.id for spec in specs]
    else:
        # Simple list of IDs
        extracted_ids = scenario_ids

    # === Validation ===
    if not extracted_ids:
        raise ValueError(
            "with_scenarios() requires at least one scenario ID. "
            "For single-scenario models, use: with_scenarios(af, ['DETERMINISTIC'])"
        )

    if len(extracted_ids) != len(set(extracted_ids)):
        duplicates = [s for s in extracted_ids if extracted_ids.count(s) > 1]
        raise ValueError(
            f"with_scenarios() received duplicate scenario IDs: {set(duplicates)}. "
            "Each scenario ID must be unique."
        )

    # Check if scenario_column already exists
    af_columns = af.get_column_order()
    if scenario_column in af_columns:
        raise ValueError(
            f"Column '{scenario_column}' already exists in ActuarialFrame. "
            f"Either rename the existing column or use a different scenario_column name. "
            f"Existing columns: {af_columns}"
        )

    # Create scenarios DataFrame
    scenarios_df = pl.DataFrame({scenario_column: extracted_ids})

    # Apply categorical encoding if requested
    if categorical and scenarios_df[scenario_column].dtype == pl.Utf8:
        scenarios_df = scenarios_df.with_columns(
            pl.col(scenario_column).cast(pl.Categorical)
        )

    # Collect the ActuarialFrame to DataFrame for cross-join
    af_df = af.collect()

    # Perform cross-join to expand rows
    expanded = af_df.join(scenarios_df, how="cross")

    # Return as ActuarialFrame, preserving mode
    return ActuarialFrame(expanded, mode=af._mode, verbose=af._verbose)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_with_scenarios.py::TestWithScenariosShockConfig -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/scenarios/_with_scenarios.py tests/scenarios/test_with_scenarios.py
git commit -m "$(cat <<'EOF'
feat(scenarios): with_scenarios() accepts shock/sweep configs

with_scenarios() now accepts:
- Simple ID lists: ["BASE", "UP", "DOWN"]
- Config dicts with shocks: [{"id": "STRESS", "shocks": [...]}]
- Sweep configs that expand to multiple scenarios

Enables LLM-generated scenario configurations.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 19: Export Phase 3 Functions from gaspatchio_core

**Files:**
- Modify: `gaspatchio_core/__init__.py`

**Step 1: Add exports**

Update `gaspatchio_core/__init__.py`:

```python
from .scenarios import (
    batch_scenarios,
    describe_scenarios,
    parse_scenario_config,
    ScenarioSpec,
    sensitivity_analysis,
    ShockSpec,
    SweepSpec,
    with_scenarios,
)
```

Add to `__all__`:

```python
    "describe_scenarios",
    "parse_scenario_config",
    "ScenarioSpec",
    "sensitivity_analysis",
    "ShockSpec",
    "SweepSpec",
```

**Step 2: Commit**

```bash
git add gaspatchio_core/__init__.py
git commit -m "$(cat <<'EOF'
feat(scenarios): export Phase 3 APIs from gaspatchio_core

Exports for ad-hoc shock specifications:
- describe_scenarios, sensitivity_analysis
- parse_scenario_config
- ScenarioSpec, ShockSpec, SweepSpec models

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 20: Integration Test - Full Shock Workflow

**Files:**
- Create: `tests/scenarios/test_shock_workflow.py`

**Step 1: Write comprehensive integration test**

Create: `tests/scenarios/test_shock_workflow.py`

```python
# ABOUTME: Integration tests for complete shock specification workflows.
# ABOUTME: Tests the full pattern: config → expansion → shocks → aggregation → analysis.

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, with_scenarios
from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import (
    describe_scenarios,
    sensitivity_analysis,
)


class TestShockWorkflowIntegration:
    """End-to-end tests for shock-based scenario workflows."""

    @pytest.fixture
    def rates_table(self, tmp_path: Path) -> Table:
        """Create a discount rates table."""
        df = pl.DataFrame({
            "year": [1, 2, 3, 4, 5],
            "rate": [0.03, 0.035, 0.04, 0.045, 0.05],
        })
        df.write_parquet(tmp_path / "rates.parquet")
        return Table(
            name="discount_rates",
            source=df,
            dimensions={"year": "year"},
            value="rate",
        )

    def test_llm_generated_scenario_workflow(self, rates_table):
        """
        Test the LLM-generated scenario workflow from the RFC.

        User asks: "What happens if rates rise 50 basis points?"
        LLM generates config, framework executes, results compared.
        """
        # === 1. LLM generates this config ===
        config = [
            {"id": "BASE"},
            {
                "id": "RATES_UP_50BPS",
                "shocks": [{"table": "discount_rates", "add": 0.005}],
            },
        ]

        # === 2. Describe for transparency ===
        description = describe_scenarios(config)
        assert "BASE" in description
        assert "RATES_UP_50BPS" in description
        assert "discount_rates" in description

        # === 3. Create model points and expand ===
        af = ActuarialFrame({
            "policy_id": [1, 2],
            "year": [1, 2],
            "premium": [1000.0, 2000.0],
        })
        af = with_scenarios(af, config)

        # === 4. Verify expansion ===
        df = af.collect()
        assert len(df) == 4  # 2 policies × 2 scenarios
        assert set(df["scenario_id"].unique().to_list()) == {"BASE", "RATES_UP_50BPS"}

    def test_sensitivity_sweep_workflow(self, rates_table):
        """
        Test sensitivity sweep workflow.

        User asks: "Show me sensitivity to rates from -100 to +100bps"
        """
        # === 1. Config with sweep ===
        config = [
            {"id": "BASE"},
            {
                "sweep": {
                    "id_template": "RATES_{bps:+04d}BPS",
                    "table": "discount_rates",
                    "add_range": {"from_bps": -100, "to_bps": 100, "step_bps": 50},
                }
            },
        ]

        # === 2. Expand ===
        af = ActuarialFrame({"policy_id": [1], "premium": [1000.0]})
        af = with_scenarios(af, config)
        df = af.collect()

        # BASE + 5 sweep scenarios (-100, -50, 0, +50, +100)
        assert len(df) == 6

        # === 3. Simulate results (in real workflow, this comes from model) ===
        results = pl.DataFrame({
            "scenario_id": [
                "BASE", "RATES_-100BPS", "RATES_-050BPS",
                "RATES_+000BPS", "RATES_+050BPS", "RATES_+100BPS",
            ],
            "total_pv": [2000, 2200, 2100, 2000, 1900, 1800],
        })

        # === 4. Analyze sensitivity ===
        summary = sensitivity_analysis(
            results,
            sweep_prefix="RATES_",
            metrics=["total_pv"],
        )

        assert summary["scenarios_count"] == 5  # Excludes BASE (doesn't match prefix)
        assert summary["metrics"]["total_pv"]["min"]["value"] == 1800
        assert summary["metrics"]["total_pv"]["max"]["value"] == 2200
        assert summary["metrics"]["total_pv"]["range"] == 400

    def test_composable_shocks_workflow(self, rates_table):
        """
        Test combining multiple shocks in one scenario.

        User asks: "What if rates rise AND early lapses increase?"
        """
        config = [
            {"id": "BASE"},
            {
                "id": "RATE_RISE_WITH_LAPSE_STRESS",
                "shocks": [
                    {"table": "discount_rates", "add": 0.005},
                    {"table": "lapse_rates", "filter": {"duration": {"lte": 3}}, "multiply": 1.25},
                ],
            },
        ]

        description = describe_scenarios(config)
        assert "discount_rates" in description
        assert "lapse_rates" in description
        assert "1.25" in description
```

**Step 2: Run test**

Run: `uv run pytest tests/scenarios/test_shock_workflow.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/scenarios/test_shock_workflow.py
git commit -m "$(cat <<'EOF'
test(scenarios): add integration tests for shock workflows

Tests the full LLM-friendly scenario workflow:
- Config generation from natural language questions
- Sensitivity sweeps with analysis
- Composable shocks

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 21: Final Phase 3 Test Suite and Type Checks

**Files:**
- No new files

**Step 1: Run all scenario tests**

```bash
uv run pytest tests/scenarios/ -v
```

Expected: All tests PASS

**Step 2: Run type checker**

```bash
uv run mypy gaspatchio_core/scenarios/
uv run pyright gaspatchio_core/scenarios/
```

Expected: No errors

**Step 3: Run full test suite**

```bash
uv run pytest -x --tb=short
```

Expected: All tests PASS

**Step 4: Final commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(scenarios): complete Phase 3 - ad-hoc shock specifications

RFC 27 Phase 3 complete. Provides:
- ShockSpec, ScenarioSpec, SweepSpec data models
- parse_scenario_config() for flexible input parsing
- describe_scenarios() for audit trail
- sensitivity_analysis() for sweep result analysis
- with_scenarios() accepts full config including sweeps

All scenario functionality tested and type-checked.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Summary

### Files Created

**Phase 1-2: Core Scenario Support**
- `gaspatchio_core/scenarios/__init__.py`
- `gaspatchio_core/scenarios/_with_scenarios.py`
- `gaspatchio_core/scenarios/_batching.py`
- `tests/scenarios/__init__.py`
- `tests/scenarios/test_with_scenarios.py`
- `tests/scenarios/test_table_scenario_loading.py`
- `tests/scenarios/test_scenario_workflow.py`
- `tests/scenarios/test_batching.py`

**Phase 3: Ad-hoc Shock Specifications**
- `gaspatchio_core/scenarios/_shocks.py`
- `gaspatchio_core/scenarios/_audit.py`
- `gaspatchio_core/scenarios/_sensitivity.py`
- `tests/scenarios/test_shocks.py`
- `tests/scenarios/test_audit.py`
- `tests/scenarios/test_sensitivity.py`
- `tests/scenarios/test_shock_workflow.py`

### Files Modified
- `gaspatchio_core/__init__.py` (add exports)
- `gaspatchio_core/assumptions/_api.py` (add classmethods)

### Public API Added

**Core Scenario Expansion:**
```python
from gaspatchio_core import with_scenarios, batch_scenarios
from gaspatchio_core.assumptions import Table

# Expand ActuarialFrame across scenarios
af = with_scenarios(af, ["BASE", "UP", "DOWN"])

# Load per-scenario files
table = Table.from_scenario_files({...})
table = Table.from_scenario_template("path/{scenario_id}/file.parquet", [...])

# Batch processing
for batch in batch_scenarios(scenario_ids, batch_size=1000):
    ...
```

**Ad-hoc Shock Specifications (LLM-Friendly):**
```python
from gaspatchio_core import (
    with_scenarios,
    describe_scenarios,
    sensitivity_analysis,
    ShockSpec,
    ScenarioSpec,
    SweepSpec,
)

# LLM-generated scenario config
config = [
    {"id": "BASE"},
    {"id": "RATES_UP", "shocks": [{"table": "discount_rates", "add": 0.005}]},
    {"sweep": {"id_template": "RATES_{bps:+04d}BPS", "table": "rates",
               "add_range": {"from_bps": -100, "to_bps": 100, "step_bps": 25}}},
]

# Expand with shock/sweep configs
af = with_scenarios(af, config)

# Audit trail
print(describe_scenarios(config))

# Sensitivity analysis
summary = sensitivity_analysis(by_scenario, sweep_prefix="RATES_", metrics=["total_pv"])
```

### Not Implemented (Future Phases)
- CLI integration (`gspio run-model --scenarios`)
- Runtime shock application to Table lookups (shocks stored but not auto-applied)
- GPU acceleration for scenario aggregations
