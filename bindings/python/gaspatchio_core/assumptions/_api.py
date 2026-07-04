# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TID252, TRY003, EM101, EM102, E501, PLR0913, ANN204, FBT001, FBT002
# ruff: noqa: C901, PD901, SIM102, PLR0912, F821, SLF001, PGH003, B007, PERF102
# ruff: noqa: ANN003, BLE001, D413
# mypy: disable-error-code="import-untyped,arg-type,name-defined"
"""
Main assumption table API (v2) - Table class with dimension-based structure.

This module replaces the old monolithic load_assumptions() function with a
modular system that separates concerns and improves composability.
"""

from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.scenarios.shocks import Shock
from loguru import logger
from polars.plugins import register_plugin_function

from .._internal import PyAssumptionTableRegistry
from ._analysis import TableSchema, analyze_table
from ._dimensions import DataDimension, Dimension
from ._utils import _convert_keys_to_f64, _materialise


def _suggest_dimension(invalid_name: str, valid_names: list[str]) -> str | None:
    """Suggest a valid dimension name based on fuzzy matching.

    Uses difflib.get_close_matches for fuzzy matching, with fallback to
    prefix and suffix matching for cases like 'age' -> 'age_last'.

    Args:
        invalid_name: The invalid dimension name provided by the user
        valid_names: List of valid dimension names

    Returns:
        The suggested dimension name, or None if no close match found

    """
    # Try fuzzy match first (cutoff=0.6 catches most typos)
    matches = get_close_matches(invalid_name, valid_names, n=1, cutoff=0.6)
    if matches:
        return matches[0]

    # Try prefix matching (e.g., 'age' matches 'age_last')
    prefix_matches = [v for v in valid_names if v.startswith(invalid_name)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    # Try suffix matching (e.g., 'last' matches 'age_last')
    suffix_matches = [v for v in valid_names if v.endswith(invalid_name)]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None


# Import for type hints without circular dependency

# Global metadata storage for assumption tables
_TABLE_METADATA: dict[str, dict[str, Any]] = {}

# Import LIB path for plugin calls
try:
    from .. import _internal

    LIB = Path(_internal.__file__)
except ImportError as e:
    raise ImportError(
        "Failed to import the gaspatchio_core native extension (_internal). "
        "Ensure the project is built and installed correctly (e.g., using 'maturin develop -uv').",
    ) from e


class Table:
    """
    Main assumption table class with dimension-based structure.

    This class provides a clean API for creating assumption tables using
    composable dimension types and strategies, replacing the old monolithic
    load_assumptions() function.
    """

    def __init__(
        self,
        name: str,
        source: str | Path | pl.DataFrame,
        dimensions: dict[str, str | Dimension],
        value: str = "rate",
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
        storage_mode: str = "auto",
    ):
        """Create a new assumption table.

        Initializes and registers a new assumption table with the framework, processing
        the source data through dimension transformations and making it available for
        high-performance lookups in actuarial calculations. The table becomes immediately
        available for use in model projections and analysis workflows.

        !!! note "When to use"
            * **Model Setup:** Create assumption tables during model initialization
                to load mortality, lapse, expense, and interest rate assumptions.
            * **Data Integration:** Transform raw assumption data from CSV, Parquet,
                or database sources into optimized lookup tables.
            * **Dynamic Models:** Register assumption tables with metadata for
                model versioning, governance, and automated documentation.
            * **Multi-Product Models:** Set up separate assumption tables for
                different product lines with appropriate dimension structures.

        Args:
            name: Unique table name for registration
            source: Data source (file path or DataFrame)
            dimensions: Mapping of dimension names to dimension objects or column names
            value: Name for the value column
            validate: Whether to validate data on load
            metadata: Optional metadata dictionary to store with the table
            storage_mode: Storage backend - "auto" (default, chooses based on density),
                "hash" (always use hash table), or "array" (prefer array indexing)

        Examples:
        --------
        **Scalar Example: Basic Mortality Table Creation**

        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        # Create mortality rate data
        mortality_data = pl.DataFrame(
            {
                "age": [25, 30, 35, 40, 45, 50, 55, 60],
                "mortality_rate": [
                    0.0008,
                    0.001,
                    0.0015,
                    0.0025,
                    0.004,
                    0.007,
                    0.012,
                    0.020,
                ],
            }
        )

        # Create and register mortality table
        mortality_table = Table(
            name="mortality_standard",
            source=mortality_data,
            dimensions={"age": "age"},
            value="mortality_rate",
            validate=True,
            metadata={
                "description": "Standard mortality rates for term life insurance",
                "source": "2017 CSO Table",
                "effective_date": "2024-01-01",
            },
        )

        print(f"Created table: {mortality_table._name}")
        print(f"Dimensions: {list(mortality_table.dimensions.keys())}")
        ```

        ```text
        Created table: mortality_standard
        Dimensions: ['age']
        ```

        **Vector Example: Multi-Dimensional Lapse Table**

        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        # Create lapse rate data with multiple dimensions
        lapse_data = pl.DataFrame({
            "duration": [1, 1, 1, 2, 2, 2, 3, 3, 3],
            "product_type": ["TERM", "WL", "UL", "TERM", "WL", "UL", "TERM", "WL", "UL"],
            "lapse_rate": [0.05, 0.03, 0.07, 0.08, 0.05, 0.10, 0.12, 0.07, 0.13]
        })

        # Create multi-dimensional table with categorical dimension
        lapse_table = Table(
            name="lapse_by_product",
            source=lapse_data,
            dimensions={
                "duration": "duration",
                "product_type": "product_type"
            },
            value="lapse_rate",
            metadata={
                "description": "Lapse rates by product type and duration",
                "source": "Company Experience Study 2023",
                "products_included": ["Term Life", "Whole Life", "Universal Life"],
                "study_period": "2020-2023",
                "credibility": "Fully Credible"
            }
        )

        print(f"Table: {lapse_table._name}")
        print(f"Rows: {len(lapse_table.to_dataframe())}")
        print(f"Key columns: {[col for col in lapse_table.to_dataframe().columns if col != 'lapse_rate']}")
        ```

        ```text
        Table: lapse_by_product
        Rows: 9
        Key columns: ['duration', 'product_type']
        ```
        """
        self._name = name

        # Normalize dimensions - convert strings to DataDimension objects
        self._dimensions = {}
        for dim_name, dim_config in dimensions.items():
            if isinstance(dim_config, str):
                self._dimensions[dim_name] = DataDimension(dim_config)
            else:
                self._dimensions[dim_name] = dim_config

        self._value = value
        self._validate = validate
        self._storage_mode = storage_mode
        self._df: pl.DataFrame | None = None
        self._schema: TableSchema | None = None
        # Store Enum types for string key columns to enable auto-categorical conversion.
        # Maps column name -> pl.Enum with sorted categories for deterministic index mapping.
        self._key_categories: dict[str, pl.Enum] = {}

        # Store metadata if provided
        if metadata is not None:
            _TABLE_METADATA[name] = metadata.copy()
            logger.debug(f"Stored metadata for table '{name}': {metadata}")

        # Process the data during initialization
        self._process_data(source)

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
    ) -> Table:
        """
        Create a Table by concatenating per-scenario assumption files.

        Loads each file, adds scenario_column with the scenario ID, concatenates
        all into a single DataFrame, and creates a Table with scenario_column
        as an additional dimension.

        This is useful when assumptions are stored as separate files per scenario
        (e.g., from an ESG tool that outputs per-scenario returns).

        !!! note "When to use"
            * **ESG Integration:** Load per-scenario returns or yield curves from
                economic scenario generator outputs stored as separate files.
            * **Stress Testing:** Combine base, stressed, and adverse scenario
                assumption files into a single Table for multi-scenario runs.
            * **Regulatory Scenarios:** Load prescribed regulatory scenarios
                (e.g., IFRS17, Solvency II) from separate assumption files.

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
            Loading per-scenario rate files:

            ```python no_output_check
            from gaspatchio_core.assumptions import Table

            rates_table = Table.from_scenario_files(
                scenario_files={
                    "BASE": "scenarios/BASE/rates.parquet",
                    "UP": "scenarios/UP/rates.parquet",
                    "DOWN": "scenarios/DOWN/rates.parquet",
                },
                scenario_column="scenario_id",
                dimensions={"year": "year"},
                value="forward_rate",
                name="discount_rates",
            )
            ```

        """
        if not scenario_files:
            raise ValueError(
                "scenario_files cannot be empty. "
                "Provide at least one scenario_id -> file path mapping."
            )

        dfs = []
        for scenario_id, path in scenario_files.items():
            # Load the file (Parquet or CSV, chosen by extension)
            file_path = Path(path) if isinstance(path, str) else path
            scenario_df = _materialise(file_path)

            # Add scenario column
            scenario_df = scenario_df.with_columns(
                pl.lit(scenario_id).alias(scenario_column)
            )
            dfs.append(scenario_df)

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
    ) -> Table:
        """
        Create a Table from scenario files matching a path template.

        Convenience method when scenario files follow a predictable naming pattern.
        Expands the template with each scenario ID and delegates to from_scenario_files().

        !!! note "When to use"
            * **Templated Paths:** When scenario files follow a naming convention
                like `scenarios/{scenario_id}/rates.parquet` or similar patterns.
            * **Stochastic Scenarios:** For thousands of numbered scenarios where
                manually specifying each path would be impractical.
            * **Convention over Configuration:** When file organization follows
                a predictable directory structure per scenario.

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
            Loading files from templated paths:

            ```python no_output_check
            from gaspatchio_core.assumptions import Table

            # Files: scenarios/BASE/returns.parquet, scenarios/UP/returns.parquet
            returns_table = Table.from_scenario_template(
                path_template="scenarios/{scenario_id}/returns.parquet",
                scenario_ids=["BASE", "UP", "DOWN"],
                scenario_column="scenario_id",
                dimensions={"t": "t"},
                value="inv_return_mth",
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

    @classmethod
    def from_shocks(
        cls,
        base_table: Table,
        shocks: dict[str, list[Shock]],
        value_column: str,
    ) -> dict[str, Table]:
        """
        Create multiple shocked tables from a base table and shock specifications.

        Takes a base assumption table and a dictionary mapping scenario IDs to lists
        of shocks. Returns a dictionary of Tables, one for each scenario, with the
        appropriate shocks applied.

        !!! note "When to use"
            * **Sensitivity Analysis:** When you need to create multiple shocked
                versions of an assumption table for parameter sweeps.
            * **Ad-hoc Scenarios:** When scenario shocks are defined programmatically
                rather than loaded from files.
            * **Integration with sensitivity_analysis():** The output from
                sensitivity_analysis() can be passed directly to this method.

        Args:
            base_table: The original assumption table to apply shocks to
            shocks: Mapping of scenario ID to list of shocks to apply
            value_column: The column to apply shocks to

        Returns:
            Dictionary mapping scenario IDs to shocked Table instances

        Raises:
            ValueError: If value_column doesn't exist in the base table

        Examples:
            Create stressed mortality tables:

            ```python no_output_check
            from gaspatchio_core.assumptions import Table
            from gaspatchio_core.scenarios.shocks import MultiplicativeShock

            base_mortality = Table(...)  # Load base mortality table

            shocks = {
                "BASE": [],
                "UP": [MultiplicativeShock(factor=1.2)],
                "DOWN": [MultiplicativeShock(factor=0.8)],
            }

            tables = Table.from_shocks(base_mortality, shocks, value_column="qx")
            # tables["BASE"], tables["UP"], tables["DOWN"] are all Table instances
            ```

            Integration with sensitivity_analysis():

            ```python no_output_check
            from gaspatchio_core.assumptions import Table
            from gaspatchio_core.scenarios._sensitivity import sensitivity_analysis
            import polars as pl

            # Create a base table
            base_df = pl.DataFrame({"age": [30, 40], "rate": [0.01, 0.02]})
            base_table = Table("mortality", base_df, {"age": "age"}, "rate")

            shocks = sensitivity_analysis(
                table="mortality",
                shock_type="multiplicative",
                values=[0.9, 1.0, 1.1],
            )

            tables = Table.from_shocks(base_table, shocks, value_column="rate")
            ```

        """
        if not shocks:
            return {}

        # Validate value_column exists
        base_df = base_table.to_dataframe()
        if value_column not in base_df.columns:
            msg = f"value_column '{value_column}' not found in table columns: {base_df.columns}"
            raise ValueError(msg)

        result: dict[str, Table] = {}

        for scenario_id, shock_list in shocks.items():
            if not shock_list:
                # No shocks - use base table as-is but create a copy
                # Create a new table with same data
                result[scenario_id] = Table(
                    name=f"{base_table._name}_{scenario_id}",
                    source=base_df.clone(),
                    dimensions={name: name for name in base_table._dimensions},
                    value=base_table._value,
                    validate=False,
                    metadata=base_table.metadata,
                )
            else:
                # Apply shocks sequentially
                table = base_table
                for shock in shock_list:
                    table = table.with_shock(shock)

                # Rename to include scenario ID
                result[scenario_id] = Table(
                    name=f"{base_table._name}_{scenario_id}",
                    source=table.to_dataframe(),
                    dimensions={name: name for name in base_table._dimensions},
                    value=base_table._value,
                    validate=False,
                    metadata=base_table.metadata,
                )

        return result

    def _process_data(self, source: str | Path | pl.DataFrame) -> None:
        """Process the data through dimension transformations and register with Rust.

        Internal method that processes source data through dimension transformations,
        validates the result, and registers the table with the Rust backend for
        high-performance lookups. This method handles the core data processing
        pipeline for assumption table creation.

        !!! note "When to use"
            * **Internal Use Only:** This is a private method called automatically
                during table initialization and extension operations.

        Args:
            source: Data source to process (file path or DataFrame)

        Examples:
        --------
        ```python
        # This method is called internally - not for direct use
        # It's invoked automatically when creating or extending tables
        ```

        """
        logger.debug(f"Processing data for table '{self._name}'")

        # Materialize the source data
        df = _materialise(source)

        if self._validate:
            # Check if we have MeltDimension - if so, value column will be created
            has_melt_dimension = any(
                dim.__class__.__name__ == "MeltDimension"
                for dim in self._dimensions.values()
            )

            # Only validate value column exists if we don't have melt dimension
            if not has_melt_dimension and self._value not in df.columns:
                available_cols = ", ".join(df.columns)
                raise ValueError(
                    f"Value column '{self._value}' not found in DataFrame.\n"
                    f"Available columns: {available_cols}",
                )

        # Process dimensions in order
        # Note: Order matters for dependencies (e.g., ComputedDimension depends on others)
        current_df = df

        # Process dimensions in a specific order:
        # 1. DataDimension (base columns, renames)
        # 2. CategoricalDimension (add constant columns)
        # 3. MeltDimension (pivot operations)
        # 4. ComputedDimension (depends on other columns)

        dimension_order = [
            "DataDimension",
            "CategoricalDimension",
            "MeltDimension",
            "ComputedDimension",
        ]

        for dimension_type in dimension_order:
            for dim_name, dimension in self._dimensions.items():
                if dimension.__class__.__name__ == dimension_type:
                    if self._validate:
                        dimension.validate(current_df)
                    current_df = dimension.process(current_df)
                    logger.debug(f"Processed dimension '{dim_name}' ({dimension_type})")

                    # Handle MeltDimension value column naming
                    if (
                        dimension_type == "MeltDimension"
                        and "value" in current_df.columns
                    ):
                        if self._value != "value":
                            current_df = current_df.rename({"value": self._value})
                            logger.debug(
                                f"Renamed melt value column from 'value' to '{self._value}'",
                            )

        # Collect key columns (all columns except the value column)
        key_columns = [col for col in current_df.columns if col != self._value]

        if not key_columns:
            raise ValueError(
                f"No key columns found after dimension processing. "
                f"All columns cannot be the value column '{self._value}'",
            )

        # Capture sorted categories for string columns to enable auto-categorical conversion.
        # The sorted order matches Rust's KeyEncoder dictionary ordering for deterministic lookups.
        for col in key_columns:
            if current_df[col].dtype == pl.String:
                categories = current_df[col].unique().sort().to_list()
                self._key_categories[col] = pl.Enum(categories)
                max_categories_to_show = 5
                logger.debug(
                    f"Captured {len(categories)} categories for string column '{col}': "
                    f"{categories[:max_categories_to_show]}"
                    f"{'...' if len(categories) > max_categories_to_show else ''}"
                )

        # Convert keys to f64 for Rust compatibility
        processed_df = _convert_keys_to_f64(current_df, key_columns)

        # Sort by key columns to ensure array storage indices match categorical order.
        # This is critical for array storage where position == index.
        processed_df = processed_df.sort(key_columns)

        # Store the processed DataFrame
        self._df = processed_df

        # Register with Rust registry using idempotent method
        try:
            registry = PyAssumptionTableRegistry()
            # Use register_or_replace_table for idempotent behavior
            registry.register_or_replace_table(
                name=self._name,
                df=processed_df,
                keys=key_columns,
                value_column=self._value,
                force_replace=True,  # Always replace for reentrancy support
                storage_mode=self._storage_mode,
            )
            # Query the actual storage mode chosen by Rust (may differ from requested if "auto")
            actual_mode = (
                registry.get_table_storage_mode(self._name) or self._storage_mode
            )
            logger.debug(
                f"Registered table '{self._name}': {len(processed_df):,} rows, "
                f"keys={key_columns}, storage={actual_mode}"
                + (
                    f" (requested={self._storage_mode})"
                    if self._storage_mode != actual_mode
                    else ""
                ),
            )
        except Exception as e:
            logger.error(f"Failed to register table '{self._name}' with Rust: {e}")
            raise

    def lookup(
        self,
        _dimensions: dict[str, str | pl.Expr | ColumnProxy] | None = None,
        **kwargs: str | pl.Expr | ColumnProxy,
    ) -> pl.Expr:
        """Create a lookup expression using dimension names.

        Generates a high-performance lookup expression that retrieves assumption values
        from the registered table based on provided dimension keys. The lookup is
        optimized for vectorized operations and integrates seamlessly with ActuarialFrame
        workflows for efficient model projections and calculations.

        !!! note "When to use"
            * **Model Projections:** Retrieve mortality, lapse, expense, or interest
                rates during actuarial model calculations and cash flow projections.
            * **Dynamic Lookups:** Perform lookups where dimension values come from
                model point data or intermediate calculation results.
            * **Multi-Dimensional Tables:** Look up values from tables with multiple
                dimensions like age, duration, product type, and risk class.
            * **Vectorized Operations:** Execute efficient batch lookups across
                thousands or millions of policies in model projections.

        Can be called in three ways:
        1. With keyword arguments for clean dimension names:
           table.lookup(age=af["age"], duration=af["duration"])

        2. With a dictionary for dimension names with spaces or special characters:
           table.lookup({"policy duration": af["policy_duration_as_int"]})

        3. Or both combined:
           table.lookup({"policy duration": af["duration"]}, age=af["age"])

        Args:
            _dimensions: Optional dictionary mapping dimension names to columns/expressions
            **kwargs: Dimension name to column/expression mapping

        Returns:
            Polars expression for the lookup

        Examples:
        --------
        **Scalar Example: Simple Mortality Lookup**

        ```python
        from gaspatchio_core.assumptions import Table
        from gaspatchio_core import ActuarialFrame
        import polars as pl

        # Create mortality table
        mortality_data = pl.DataFrame(
            {
                "age": [30, 35, 40, 45, 50],
                "mortality_rate": [0.001, 0.002, 0.004, 0.008, 0.015],
            }
        )

        mortality_table = Table(
            name="mortality_std",
            source=mortality_data,
            dimensions={"age": "age"},
            value="mortality_rate",
        )

        # Create model data and perform lookup
        model_data = {
            "policy_id": ["P001", "P002", "P003"],
            "current_age": [35, 40, 50],
        }
        af = ActuarialFrame(model_data)

        # Lookup mortality rates
        af.mortality_rate = mortality_table.lookup(age=af.current_age)

        print(af.collect())
        ```

        ```text
        shape: (3, 3)
        ┌───────────┬─────────────┬────────────────┐
        │ policy_id ┆ current_age ┆ mortality_rate │
        │ ---       ┆ ---         ┆ ---            │
        │ str       ┆ i64         ┆ f64            │
        ╞═══════════╪═════════════╪════════════════╡
        │ P001      ┆ 35          ┆ 0.002          │
        │ P002      ┆ 40          ┆ 0.004          │
        │ P003      ┆ 50          ┆ 0.015          │
        └───────────┴─────────────┴────────────────┘
        ```

        **Vector Example: Multi-Dimensional Lapse Lookup**

        ```python
        from gaspatchio_core.assumptions import Table
        from gaspatchio_core import ActuarialFrame
        import polars as pl

        # Create multi-dimensional lapse table
        lapse_data = pl.DataFrame({
            "duration": [1, 1, 2, 2, 3, 3],
            "product_type": ["TERM", "WL", "TERM", "WL", "TERM", "WL"],
            "lapse_rate": [0.05, 0.03, 0.08, 0.05, 0.12, 0.07]
        })

        lapse_table = Table(
            name="lapse_rates",
            source=lapse_data,
            dimensions={"duration": "duration", "product_type": "product_type"},
            value="lapse_rate"
        )

        # Create model points with policy data
        model_points = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "product_code": ["TERM", "WL", "TERM", "WL"],
            "policy_year": [1, 2, 3, 1]
        }
        af = ActuarialFrame(model_points)

        # Lookup lapse rates using multiple dimensions
        af.lapse_rate = lapse_table.lookup(
            duration=af.policy_year,
            product_type=af.product_code
        )

        print(af.collect())
        ```

        ```text
        shape: (4, 4)
        ┌───────────┬──────────────┬─────────────┬────────────┐
        │ policy_id ┆ product_code ┆ policy_year ┆ lapse_rate │
        │ ---       ┆ ---          ┆ ---         ┆ ---        │
        │ str       ┆ str          ┆ i64         ┆ f64        │
        ╞═══════════╪══════════════╪═════════════╪════════════╡
        │ P001      ┆ TERM         ┆ 1           ┆ 0.05       │
        │ P002      ┆ WL           ┆ 2           ┆ 0.05       │
        │ P003      ┆ TERM         ┆ 3           ┆ 0.12       │
        │ P004      ┆ WL           ┆ 1           ┆ 0.03       │
        └───────────┴──────────────┴─────────────┴────────────┘
        ```
        """
        # Merge both sources of dimensions
        all_dimensions = {}
        if _dimensions:
            all_dimensions.update(_dimensions)
        all_dimensions.update(kwargs)

        if self._validate:
            self.validate_lookup(**all_dimensions)

        # Convert all_dimensions to a list of expressions in the order of key columns
        if self._df is None:
            raise RuntimeError("Table data not processed. This should not happen.")

        key_columns = [col for col in self._df.columns if col != self._value]

        # Validate that all required dimensions are provided
        if set(all_dimensions.keys()) != set(self._dimensions.keys()):
            provided = set(all_dimensions.keys())
            required = set(self._dimensions.keys())
            missing = required - provided
            extra = provided - required

            error_parts = []
            if missing:
                error_parts.append(f"Missing dimensions: {sorted(missing)}")
            if extra:
                # Add suggestions for extra (invalid) dimensions
                extra_with_suggestions = []
                for dim in sorted(extra):
                    suggestion = _suggest_dimension(dim, list(required))
                    if suggestion:
                        extra_with_suggestions.append(
                            f"'{dim}' (did you mean '{suggestion}'?)"
                        )
                    else:
                        extra_with_suggestions.append(f"'{dim}'")
                error_parts.append(f"Extra dimensions: {extra_with_suggestions}")

            raise ValueError(
                f"Dimension mismatch for table '{self._name}'. "
                + "; ".join(error_parts)
                + f"\nRequired dimensions: {sorted(required)}",
            )

        # Build list of expressions in key column order
        key_exprs = []
        for col in key_columns:
            if col in all_dimensions:
                value = all_dimensions[col]
                if isinstance(value, str):
                    expr = pl.col(value)
                elif isinstance(value, pl.Expr):
                    expr = value
                elif hasattr(value, "_to_expr"):
                    # Handle ColumnProxy objects from ActuarialFrame
                    expr = value._to_expr()
                else:
                    # Convert literal values to expressions
                    expr = pl.lit(value)

                # Note: String columns are handled by the Rust
                # CategoricalWithStringFallback encoder which maps
                # strings to the table's internal categorical indices.
                # No pre-cast needed — the encoder handles raw strings.

                key_exprs.append(expr)
            else:
                # This shouldn't happen due to validation above, but handle gracefully
                raise ValueError(f"No value provided for key column '{col}'")

        # Create the actual plugin call to Rust lookup implementation
        # is_elementwise=True: each row's lookup depends only on that row's keys,
        # not on other rows. This enables the Polars streaming engine to process
        # the query in chunks without falling back to in-memory execution.
        return register_plugin_function(
            plugin_path=LIB,
            function_name="lookup_by_table_and_hash",  # Must match #[polars_expr] function name
            args=key_exprs,
            kwargs={"table_name": self._name},
            is_elementwise=True,
        )

    def extend(
        self,
        source: str | Path | pl.DataFrame,
        dimensions: dict[str, Dimension] | None = None,
        validate: bool = True,
    ) -> Table:
        """Extend table with additional data slices.

        Appends additional data to an existing assumption table, allowing for
        incremental loading of assumption data from multiple sources or files.
        The new data undergoes the same dimension processing as the original
        table and becomes immediately available for lookups in model calculations.

        !!! note "When to use"
            * **Incremental Loading:** Add new assumption data slices from
                multiple files or data sources to build comprehensive tables.
            * **Time-Based Updates:** Append new vintage data to existing
                assumption tables for model updates and refreshes.
            * **Multi-Source Integration:** Combine assumption data from
                different systems, departments, or external providers.
            * **Scenario Analysis:** Add alternative assumption sets to
                existing tables for stress testing and scenario modeling.

        Args:
            source: Additional data to add
            dimensions: Dimension overrides for this slice
            validate: Whether to validate compatibility

        Returns:
            Self for chaining

        Examples:
        --------
        **Scalar Example: Extending Mortality Table**

        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        # Create initial mortality table
        initial_data = pl.DataFrame(
            {"age": [30, 35, 40], "mortality_rate": [0.001, 0.002, 0.004]}
        )

        mortality_table = Table(
            name="mortality_extended",
            source=initial_data,
            dimensions={"age": "age"},
            value="mortality_rate",
        )

        print(f"Initial rows: {len(mortality_table.to_dataframe())}")

        # Extend with additional age bands
        additional_data = pl.DataFrame(
            {"age": [45, 50, 55], "mortality_rate": [0.008, 0.015, 0.025]}
        )

        mortality_table.extend(source=additional_data)
        print(f"After extension: {len(mortality_table.to_dataframe())}")
        print(mortality_table.to_dataframe().sort("age"))
        ```

        ```text
        Initial rows: 3
        After extension: 6
        shape: (6, 2)
        ┌──────┬────────────────┐
        │ age  ┆ mortality_rate │
        │ ---  ┆ ---            │
        │ f64  ┆ f64            │
        ╞══════╪════════════════╡
        │ 30.0 ┆ 0.001          │
        │ 35.0 ┆ 0.002          │
        │ 40.0 ┆ 0.004          │
        │ 45.0 ┆ 0.008          │
        │ 50.0 ┆ 0.015          │
        │ 55.0 ┆ 0.025          │
        └──────┴────────────────┘
        ```

        **Vector Example: Multi-File Lapse Rate Integration**

        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        # Create base mortality table
        base_data = pl.DataFrame({
            "age": [30, 35, 40],
            "rate": [0.001, 0.002, 0.004]
        })

        table = Table(
            name="mortality_extended",
            source=base_data,
            dimensions={"age": "age"},
            value="rate"
        )

        print("Initial rows:", len(table.to_dataframe()))

        # Extend with additional ages
        additional_data = pl.DataFrame({
            "age": [45, 50],
            "rate": [0.008, 0.015]
        })

        table.extend(source=additional_data)
        print("After extension:", len(table.to_dataframe()))
        ```

        ```text
        Initial rows: 3
        After extension: 5
        ```
        """
        logger.debug(f"Extending table '{self._name}' with additional data")

        # Use original dimensions by default, with optional overrides
        extend_dimensions = self._dimensions.copy()
        if dimensions:
            extend_dimensions.update(dimensions)

        # Process the additional data the same way as original
        df = _materialise(source)
        current_df = df

        # Apply dimension processing
        dimension_order = [
            "DataDimension",
            "CategoricalDimension",
            "MeltDimension",
            "ComputedDimension",
        ]

        for dimension_type in dimension_order:
            for dim_name, dimension in extend_dimensions.items():
                if dimension.__class__.__name__ == dimension_type:
                    if validate:
                        dimension.validate(current_df)
                    current_df = dimension.process(current_df)

        # Get key columns
        key_columns = [col for col in current_df.columns if col != self._value]

        # Convert keys to f64
        processed_df = _convert_keys_to_f64(current_df, key_columns)

        # Append to existing table using Rust registry
        try:
            registry = PyAssumptionTableRegistry()
            registry.append_to_table(
                name=self._name,
                df=processed_df,
                keys=key_columns,
                value_column=self._value,
            )
            logger.debug(
                f"Successfully extended table '{self._name}' with {len(processed_df)} additional rows",
            )
        except Exception as e:
            logger.error(f"Failed to extend table '{self._name}': {e}")
            raise

        # Update our stored DataFrame by concatenating
        if self._df is not None:
            self._df = pl.concat([self._df, processed_df])

        return self

    @property
    def name(self) -> str:
        """Get the table name supplied at construction.

        Returns the stable identifier used by the registry, the typed-input
        audit trail (e.g. :class:`gaspatchio_core.MortalityTable.source_sha`),
        and any external consumer that needs a consistent reference for this
        table.

        !!! note "When to use"
            *   **Audit trail**: Record the table's name alongside model
                results so reviewers can identify which assumption set
                produced each valuation.
            *   **Registry lookups**: Pass the name to other gaspatchio
                components (typed inputs, scenario configs) that need a
                consistent reference for this table across the model.
            *   **Reproducibility**: Pin the name into release manifests
                so a future rerun can confirm the same table was used.

        Returns:
            str: The name string passed to the constructor

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})
        table = Table("mortality_standard", data, {"age": "age"}, "rate")

        print(table.name)
        ```

        """
        return self._name

    @property
    def schema(self) -> TableSchema:
        """Get the analyzed schema of this table.

        Returns comprehensive schema information about the assumption table including
        column types, value ranges, and structural metadata useful for validation,
        debugging, and documentation generation.

        !!! note "When to use"
            * **Data Validation:** Check table schema before model execution
                to ensure data types and ranges meet model requirements.
            * **Debugging:** Inspect table structure when troubleshooting
                lookup failures or data quality issues.
            * **Documentation:** Generate technical documentation showing
                table structure and data characteristics.

        Returns:
            TableSchema: Analyzed schema with column information

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35, 40], "rate": [0.001, 0.002, 0.004]})

        table = Table("test", data, {"age": "age"}, "rate")
        schema = table.schema
        print(f"Columns: {len(schema.columns)}")
        ```

        """
        if self._schema is None:
            if self._df is None:
                raise RuntimeError("Table data not processed")
            self._schema = analyze_table(self._df)
        return self._schema

    @property
    def dimensions(self) -> dict[str, Dimension]:
        """Get dimension configuration (returns a copy).

        Returns the dimension configuration used to structure this assumption
        table, providing access to dimension types, processing strategies,
        and validation rules for model analysis and debugging.

        !!! note "When to use"
            * **Model Analysis:** Inspect dimension configuration to understand
                table structure and lookup requirements.
            * **Dynamic Lookups:** Build lookup calls programmatically based
                on available dimensions and their configurations.
            * **Validation:** Check dimension compatibility when extending
                tables or building complex lookup expressions.

        Returns:
            dict[str, Dimension]: Copy of dimension configuration

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})
        table = Table("test", data, {"age": "age"}, "rate")

        dims = table.dimensions
        print(f"Dimensions: {list(dims.keys())}")
        ```

        """
        return self._dimensions.copy()

    def dimension_values(self, dimension: str) -> list[Any]:
        """Get unique values for a specific dimension.

        Returns a list of all unique values found in the specified dimension
        column of the assumption table. Useful for understanding the range
        of lookup keys available and for validation of lookup arguments.

        !!! note "When to use"
            * **Data Validation:** Check available dimension values before
                performing lookups to ensure valid lookup keys.
            * **Model Analysis:** Examine the range of ages, durations, or
                product types covered by assumption tables.
            * **Dynamic UI:** Build dropdown lists or selection interfaces
                showing available lookup values for assumption tables.

        Args:
            dimension: Name of the dimension to get values for

        Returns:
            list[Any]: List of unique values in the dimension

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame(
            {"age": [30, 35, 40, 30, 35], "rate": [0.001, 0.002, 0.004, 0.001, 0.002]}
        )

        table = Table("test", data, {"age": "age"}, "rate")
        ages = table.dimension_values("age")
        print(f"Available ages: {sorted(ages)}")
        ```

        """
        if dimension not in self._dimensions:
            available_dims = ", ".join(self._dimensions.keys())
            raise ValueError(
                f"Dimension '{dimension}' not found. Available dimensions: {available_dims}",
            )

        if self._df is None:
            raise RuntimeError("Table data not processed")

        # Find the actual column name for this dimension
        # For most dimensions, it's the same as the dimension name
        # But some dimensions might rename columns
        column_name = dimension

        # Check if column exists directly
        if column_name in self._df.columns:
            return self._df[column_name].unique().to_list()

        # For dimensions that might rename, try to find the actual column
        # This is a simplified approach - a full implementation would track renames
        for col in self._df.columns:
            if col != self._value:  # Skip value column
                # This is a placeholder - real implementation would have better logic
                return self._df[col].unique().to_list()

        return []

    def to_dataframe(self) -> pl.DataFrame:
        """Export the complete table as a DataFrame.

        Returns the complete processed assumption table as a Polars DataFrame,
        including all key columns and the value column after dimension processing.
        Useful for data inspection, validation, and integration with external systems.

        !!! note "When to use"
            * **Data Inspection:** Export table data for validation, quality
                checks, and manual review of assumption values.
            * **Integration:** Export assumption data for use in external
                systems, reporting tools, or alternative calculation engines.
            * **Debugging:** Examine processed table structure and data
                after dimension transformations and validation.

        Returns:
            pl.DataFrame: Complete table with all processed data

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})
        table = Table("test", data, {"age": "age"}, "rate")

        df = table.to_dataframe()
        print(f"Exported {len(df)} rows")
        ```

        """
        if self._df is None:
            raise RuntimeError("Table data not processed")
        return self._df.clone()

    def describe(self) -> str:
        """Get a human-readable description of the table.

        Returns a formatted string describing the table structure, including
        row count, column information, and dimension configuration. Useful
        for debugging, documentation, and model analysis.

        !!! note "When to use"
            * **Debugging:** Get quick overview of table structure when
                troubleshooting lookup issues or data problems.
            * **Documentation:** Generate summary information for model
                documentation and technical specifications.
            * **Model Analysis:** Review table characteristics during
                model development and validation processes.

        Returns:
            str: Human-readable description of the table

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35, 40], "rate": [0.001, 0.002, 0.004]})

        table = Table("mortality", data, {"age": "age"}, "rate")
        print(table.describe())
        ```

        """
        if self._df is None:
            return f"Table '{self._name}' (not processed)"

        key_columns = [col for col in self._df.columns if col != self._value]

        lines = [
            f"Table: {self._name}",
            f"Rows: {len(self._df):,}",
            f"Storage mode: {self.storage_mode}",
            f"Value column: {self._value}",
            f"Key columns ({len(key_columns)}): {', '.join(key_columns)}",
            f"Dimensions ({len(self._dimensions)}): {', '.join(self._dimensions.keys())}",
        ]

        # Add dimension details
        for dim_name, dimension in self._dimensions.items():
            dim_type = dimension.__class__.__name__
            lines.append(f"  - {dim_name}: {dim_type}")

        return "\n".join(lines)

    @property
    def metadata(self) -> dict[str, Any] | None:
        """Get metadata for this table.

        Returns stored metadata for this assumption table including descriptions,
        data sources, validation status, and business context that was provided
        during table creation.

        !!! note "When to use"
            * **Documentation:** Access table metadata for automated
                documentation generation and model reporting.
            * **Governance:** Retrieve data lineage, validation status,
                and review information for compliance reporting.
            * **Model Management:** Check table metadata for version
                control, effective dates, and change management.

        Returns:
            dict[str, Any] | None: Copy of metadata if available, None otherwise

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})
        table = Table(
            "test", data, {"age": "age"}, "rate", metadata={"source": "2023 Study"}
        )

        meta = table.metadata
        print(f"Source: {meta['source'] if meta else 'None'}")
        ```

        """
        metadata = _TABLE_METADATA.get(self._name)
        if metadata is not None:
            return metadata.copy()
        return None

    @property
    def storage_mode(self) -> str:
        """Get the actual storage mode used by this table.

        Returns the storage backend actually being used for lookups, which may
        differ from the requested mode when using "auto". This is useful for
        verifying that array storage was selected for dense tables.

        !!! note "When to use"
            * **Performance Verification:** Check if "auto" mode selected array
                storage (35x faster) or fell back to hash storage.
            * **Debugging:** Verify storage mode when troubleshooting lookup
                performance issues.
            * **Logging:** Record actual storage mode for model run diagnostics.

        Returns:
            str: The actual storage mode - "hash" or "array"

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        # Dense table - should use array storage
        data = pl.DataFrame(
            {
                "age": list(range(18, 101)),  # 83 ages
                "rate": [0.001 * (1 + a / 100) for a in range(18, 101)],
            }
        )

        table = Table(
            name="mortality_auto_test",
            source=data,
            dimensions={"age": "age"},
            value="rate",
            storage_mode="auto",  # Let Rust decide
        )

        print(f"Requested: auto, Actual: {table.storage_mode}")
        # Output: Requested: auto, Actual: array
        ```

        """
        try:
            registry = PyAssumptionTableRegistry()
            mode = registry.get_table_storage_mode(self._name)
        except Exception:
            return self._storage_mode
        else:
            return mode if mode else self._storage_mode

    def canonical_form(self) -> dict[str, Any]:
        """Deterministic JSON-encodable identity recipe for the audit chain.

        Returns a dictionary that uniquely identifies this table's content
        and shape: name, sorted dimension keys, value column, and a
        row-order-independent SHA-256 of the underlying data. Two tables
        with the same content but loaded in different row orders produce
        the same canonical_form; two tables differing in any cell value
        produce different ones.

        !!! note "When to use"
            * **Audit chains:** Feed into `source_sha()` so a regulator
              can verify the table used in a SCR run by hash alone.
            * **Reproducibility checks:** Confirm that a Table reloaded
              from disk matches the Table the run was authored against.
            * **Change detection:** Compare canonical_form between
              versions to detect data drift without re-running models.

        Returns:
            Dictionary with `kind`, `name`, sorted `dimensions`,
            `value_column`, and a content `content_sha` over the
            row-sorted parquet bytes of the data.

        Examples:
        --------
        ```python
        import polars as pl
        from gaspatchio_core.assumptions import Table

        mortality = Table(
            name="mortality",
            source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]}),
            dimensions={"age": "age"},
            value="rate",
        )

        recipe = mortality.canonical_form()
        print(sorted(recipe.keys()))
        ```

        ```text
        ['content_sha', 'dimensions', 'kind', 'name', 'value_column']
        ```

        """
        return {
            "kind": "Table",
            "name": self._name,
            "dimensions": sorted(self._dimensions.keys()),
            "value_column": self._value,
            "content_sha": self._content_sha(),
        }

    def source_sha(self) -> str:
        """SHA-256 over `canonical_form` bytes; stable for the same content + name.

        The single content hash an auditor can reproduce from the same input
        data. Identical Tables produce identical SHAs; any change to name,
        dimensions, value column, or row content changes the SHA. Combine
        with `ScenarioRun.source_sha()` to attest that an SCR run used a
        specific input table.

        !!! note "When to use"
            * **Audit sidecar:** Embedded under the plan's
              `canonical_form`/`source_sha` chain so the input data is
              identifiable from the run record alone.
            * **Pre-run validation:** Compare against a known-good SHA
              before running production batches to catch silent drift in
              assumption files.
            * **Cross-team reproducibility:** Two analysts loading the
              same parquet file produce the same SHA regardless of their
              load order.

        Returns:
            64-character lowercase hexadecimal SHA-256 digest prefixed
            with `sha256:`.

        Examples:
        --------
        ```python
        import polars as pl
        from gaspatchio_core.assumptions import Table

        mortality = Table(
            name="mortality",
            source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]}),
            dimensions={"age": "age"},
            value="rate",
        )

        sha = mortality.source_sha()
        print(sha.startswith("sha256:"))
        ```

        ```text
        True
        ```

        """
        from gaspatchio_core._identity import source_sha_of

        return source_sha_of(self.canonical_form())

    def _content_sha(self) -> str:
        """Row-order-independent content hash via parquet bytes of sorted frame.

        Algorithm:
            1. Materialise frame as DataFrame.
            2. Select [sorted(dim_names) + [value_column]].
            3. Sort by all dimension columns.
            4. Hash the parquet-serialised bytes (sha256).
        """
        import hashlib
        import io

        df = self._materialised_df()
        dim_cols = sorted(self._dimensions.keys())
        sorted_df = df.select([*dim_cols, self._value]).sort(dim_cols)
        buf = io.BytesIO()
        sorted_df.write_parquet(buf)
        return f"sha256:{hashlib.sha256(buf.getvalue()).hexdigest()}"

    def _materialised_df(self) -> pl.DataFrame:
        """Return a materialised polars DataFrame view of the table's data.

        ``Table._df`` is set to a materialised ``pl.DataFrame`` by
        ``_process_data`` before any user code sees it; the ``LazyFrame``
        branch is defensive (handles a hypothetical future where a lazy
        frame is stored directly).

        Raises:
            RuntimeError: If ``_df`` is None (table has no materialised source).
        """
        if self._df is not None:
            if isinstance(self._df, pl.LazyFrame):
                return self._df.collect()
            return self._df
        msg = "Table has no materialisable source"
        raise RuntimeError(msg)

    def with_shock(
        self,
        shock: Shock,
        name: str | None = None,
    ) -> Table:
        """Apply a shock to create a modified copy of this table.

        Creates a new Table with the shock applied to the value column. The original
        table is unchanged. This enables scenario analysis by creating stressed
        versions of assumption tables.

        !!! note "When to use"
            * **Stress Testing:** Create stressed assumption tables for regulatory
                capital calculations and risk analysis.
            * **Sensitivity Analysis:** Generate tables with parameter variations
                to understand model sensitivity to assumptions.
            * **Ad-hoc Scenarios:** Create one-off shocked tables without needing
                to load separate scenario files.

        Args:
            shock: Shock specification to apply (Multiplicative, Additive, or Override)
            name: Optional name for the shocked table (defaults to original_shocked)

        Returns:
            New Table with shocked values

        Examples:
        --------
        **Stress testing mortality:**

        ```python no_output_check
        from gaspatchio_core.assumptions import Table
        from gaspatchio_core.scenarios.shocks import MultiplicativeShock
        import polars as pl

        mortality_data = pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.002]})
        mortality = Table("mortality", mortality_data, {"age": "age"}, "qx")

        # Create 20% stressed version
        shocked = mortality.with_shock(MultiplicativeShock(factor=1.2))
        ```

        **Adding basis points to rates:**

        ```python no_output_check
        from gaspatchio_core.assumptions import Table
        from gaspatchio_core.scenarios.shocks import AdditiveShock
        import polars as pl

        rates_data = pl.DataFrame({"term": [1, 2], "rate": [0.05, 0.06]})
        rates_table = Table("rates", rates_data, {"term": "term"}, "rate")

        # Add 50bps to discount rates
        stressed_rates = rates_table.with_shock(AdditiveShock(delta=0.005))
        ```

        """
        if self._df is None:
            raise RuntimeError("Table data not processed")

        # Import Shock type here to avoid circular imports
        from gaspatchio_core.scenarios.shocks import Shock as ShockType

        if not isinstance(shock, ShockType):
            msg = f"Expected Shock instance, got {type(shock).__name__}"
            raise TypeError(msg)

        # Apply shock expression to value column
        shocked_df = self._df.with_columns(
            shock.to_expression(pl.col(self._value)).alias(self._value)
        )

        # Determine name for shocked table
        shocked_name = name or f"{self._name}_shocked"

        # Create new Table with shocked data
        # Recreate dimensions dict with string column names for constructor
        new_dimensions = {
            dim_name: dim.column_name if hasattr(dim, "column_name") else str(dim_name)
            for dim_name, dim in self._dimensions.items()
        }

        return Table(
            name=shocked_name,
            source=shocked_df,
            dimensions=new_dimensions,
            value=self._value,
            validate=False,  # Already validated
            metadata=self.metadata,
        )

    def validate_lookup(
        self,
        _dimensions: dict[str, str | pl.Expr | ColumnProxy] | None = None,
        **kwargs,
    ) -> None:
        """Validate a lookup configuration without executing.

        Checks that a lookup configuration provides all required dimensions
        and that dimension names match the table's configuration. Useful
        for validating lookup calls before execution and catching errors early.

        !!! note "When to use"
            * **Error Prevention:** Validate lookup configurations before
                execution to catch missing or invalid dimensions early.
            * **Dynamic Validation:** Check programmatically generated
                lookup calls for correctness in complex model workflows.
            * **Testing:** Validate lookup configurations in unit tests
                without executing expensive lookup operations.

        Args:
            _dimensions: Optional dictionary mapping dimension names to columns/expressions
            **kwargs: Dimension name to column/expression mapping

        Raises:
            ValueError: If dimension configuration is invalid

        Examples:
        --------
        ```python
        from gaspatchio_core.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})

        table = Table("test", data, {"age": "age"}, "rate")

        # Valid lookup - no error
        table.validate_lookup(age="current_age")

        # Invalid lookup - raises ValueError
        try:
            table.validate_lookup(invalid_dim="some_col")
        except ValueError as e:
            print(f"Validation error: {e}")
        ```

        """
        # Merge both sources of dimensions
        all_dimensions = {}
        if _dimensions:
            all_dimensions.update(_dimensions)
        all_dimensions.update(kwargs)

        # Check that all provided dimensions exist
        for dim_name in all_dimensions:
            if dim_name not in self._dimensions:
                available = list(self._dimensions.keys())
                suggestion = _suggest_dimension(dim_name, available)

                msg = f"Invalid dimension '{dim_name}' for table '{self._name}'."
                if suggestion:
                    msg += f"\n\nDid you mean '{suggestion}'?"
                msg += f"\n\nAvailable dimensions: {', '.join(available)}"

                raise ValueError(msg)

        # Check that all required dimensions are provided
        required_dims = set(self._dimensions.keys())
        provided_dims = set(all_dimensions.keys())

        if required_dims != provided_dims:
            missing = required_dims - provided_dims
            extra = provided_dims - required_dims

            error_parts = []
            if missing:
                error_parts.append(f"Missing: {sorted(missing)}")
            if extra:
                error_parts.append(f"Extra: {sorted(extra)}")

            raise ValueError(
                f"Dimension mismatch for table '{self._name}': "
                + "; ".join(error_parts),
            )


def get_table_metadata(table_name: str) -> dict[str, Any] | None:
    """Retrieve metadata for a registered assumption table.

    Fetches stored metadata for an assumption table that was registered with the
    framework. Metadata includes information like table descriptions, data sources,
    validation rules, effective dates, and business context that actuaries need
    for model documentation and compliance reporting.

    !!! note "When to use"
        * **Model Documentation:** Retrieve table descriptions, sources, and
            business context for automated model documentation generation.
        * **Audit Trails:** Access metadata for regulatory compliance and
            audit trails showing table lineage and validation status.
        * **Data Validation:** Check table metadata before performing lookups
            to ensure data quality and appropriateness for calculations.
        * **Model Versioning:** Track assumption table versions and effective
            dates for model change management and rollback procedures.

    Args:
        table_name: Name of the table to get metadata for

    Returns:
        dict | None: Copy of metadata dictionary if found, None otherwise

    Examples:
    --------
    **Scalar Example: Basic Metadata Retrieval**

    ```python
    from gaspatchio_core.assumptions import Table, get_table_metadata
    import polars as pl

    # Create and register a mortality table with metadata
    mortality_data = pl.DataFrame(
        {
            "age": [30, 35, 40, 45, 50],
            "mortality_rate": [0.001, 0.002, 0.004, 0.008, 0.015],
        }
    )

    mortality_table = Table(
        name="mortality_2023",
        source=mortality_data,
        dimensions={"age": "age"},
        value="mortality_rate",
        metadata={
            "description": "Standard mortality rates for term life insurance",
            "source": "Industry Standard Tables 2023",
            "effective_date": "2023-01-01",
            "validation_status": "approved",
        },
    )

    # Retrieve metadata
    metadata = get_table_metadata("mortality_2023")
    print(metadata)
    ```

    ```text
    {'description': 'Standard mortality rates for term life insurance', 'source': 'Industry Standard Tables 2023', 'effective_date': '2023-01-01', 'validation_status': 'approved'}
    ```

    **Vector Example: Metadata for Model Documentation**

    ```python
    from gaspatchio_core.assumptions import Table, get_table_metadata
    import polars as pl

    # Create multiple assumption tables with rich metadata
    tables_config = [
        {
            "name": "lapse_rates_term",
            "data": pl.DataFrame({
                "duration": [1, 2, 3, 4, 5],
                "lapse_rate": [0.05, 0.08, 0.12, 0.15, 0.18]
            }),
            "metadata": {
                "description": "Lapse rates for term life products",
                "business_unit": "Individual Life",
                "last_updated": "2023-12-01",
                "data_quality": "high"
            }
        },
        {
            "name": "expense_rates",
            "data": pl.DataFrame({
                "year": [1, 2, 3],
                "expense_rate": [150.0, 25.0, 15.0]
            }),
            "metadata": {
                "description": "Annual expense rates per policy",
                "currency": "USD",
                "inflation_adjusted": True,
                "review_frequency": "quarterly"
            }
        }
    ]

    # Register lapse rates table
    Table(
        name="lapse_rates_term",
        source=tables_config[0]["data"],
        dimensions={"duration": "duration"},
        value="lapse_rate",
        metadata=tables_config[0]["metadata"]
    )

    # Register expense rates table
    Table(
        name="expense_rates",
        source=tables_config[1]["data"],
        dimensions={"year": "year"},
        value="expense_rate",
        metadata=tables_config[1]["metadata"]
    )

    # Check metadata count
    print(f"Registered {len([get_table_metadata('lapse_rates_term'), get_table_metadata('expense_rates')])} tables with metadata")
    ```

    ```text
    Registered 2 tables with metadata
    ```
    """
    metadata = _TABLE_METADATA.get(table_name)
    if metadata is not None:
        return metadata.copy()
    return None


def list_tables() -> list[str]:
    """List all registered assumption tables.

    Retrieves the names of all assumption tables that have been registered with
    the framework. Essential for model inventory management, debugging lookup
    failures, and ensuring all required tables are available before running
    actuarial projections or model validations.

    !!! note "When to use"
        * **Model Validation:** Check that all required assumption tables are
            loaded before starting model calculations or projections.
        * **Debugging:** Troubleshoot lookup failures by verifying table
            registration status and identifying missing tables.
        * **Model Inventory:** Generate reports of available assumption tables
            for model documentation and governance processes.
        * **Dynamic Configuration:** Build dynamic model configurations that
            adapt based on available assumption tables.

    Returns:
        list[str]: List of table names that have been registered

    Examples:
    --------
    **Scalar Example: Basic Table Listing**

    ```python
    from gaspatchio_core.assumptions import Table, list_tables
    import polars as pl

    # Register some assumption tables
    mortality_data = pl.DataFrame(
        {"age": [30, 40, 50], "mortality_rate": [0.001, 0.004, 0.015]}
    )

    lapse_data = pl.DataFrame({"duration": [1, 2, 3], "lapse_rate": [0.05, 0.08, 0.12]})

    Table(
        name="mortality_list_ex",
        source=mortality_data,
        dimensions={"age": "age"},
        value="mortality_rate",
    )
    Table(
        name="lapse_list_ex",
        source=lapse_data,
        dimensions={"duration": "duration"},
        value="lapse_rate",
    )

    # Check that tables were registered
    tables = list_tables()
    print("mortality_list_ex registered:", "mortality_list_ex" in tables)
    print("lapse_list_ex registered:", "lapse_list_ex" in tables)
    ```

    ```text
    mortality_list_ex registered: True
    lapse_list_ex registered: True
    ```

    **Vector Example: Model Validation Workflow**

    ```python
    from gaspatchio_core.assumptions import Table, list_tables
    import polars as pl

    # Define required tables for a term life model
    required_tables = [
        "mortality_validation_ex",
        "lapse_validation_ex",
        "expense_validation_ex",
        "interest_validation_ex"
    ]

    # Register some tables (simulating partial loading)
    mortality_data = pl.DataFrame({
        "age": [25, 30, 35, 40],
        "rate": [0.0008, 0.001, 0.0015, 0.0025]
    })

    lapse_data = pl.DataFrame({
        "duration": [1, 2, 3, 4],
        "rate": [0.05, 0.08, 0.10, 0.12]
    })

    Table(name="mortality_validation_ex", source=mortality_data,
          dimensions={"age": "age"}, value="rate")
    Table(name="lapse_validation_ex", source=lapse_data,
          dimensions={"duration": "duration"}, value="rate")

    # Validate model readiness
    available_tables = list_tables()
    missing_tables = [table for table in required_tables
                     if table not in available_tables]

    print("Loaded tables:", ["mortality_validation_ex", "lapse_validation_ex"])
    print("Missing tables:", missing_tables)
    print(f"⚠️  Model not ready - missing {len(missing_tables)} tables")
    ```

    ```text
    Loaded tables: ['mortality_validation_ex', 'lapse_validation_ex']
    Missing tables: ['expense_validation_ex', 'interest_validation_ex']
    ⚠️  Model not ready - missing 2 tables
    ```
    """
    try:
        registry = PyAssumptionTableRegistry()
        return registry.list_tables()
    except Exception as e:
        logger.warning(f"Failed to get table list from registry: {e}")
        return []


def list_tables_with_metadata() -> dict[str, dict[str, Any]]:
    """List all assumption tables that have metadata stored.

    Returns a dictionary mapping table names to their stored metadata for all
    tables that were registered with metadata. Useful for generating comprehensive
    model documentation, conducting data lineage analysis, and ensuring proper
    governance over assumption tables used in actuarial models.

    !!! note "When to use"
        * **Documentation Generation:** Create comprehensive model documentation
            showing all assumption tables with their descriptions and sources.
        * **Governance Reporting:** Generate reports for regulatory compliance
            showing data lineage, validation status, and review dates.
        * **Quality Assurance:** Identify tables missing critical metadata
            like effective dates, validation status, or business descriptions.
        * **Model Inventory:** Maintain centralized inventory of all assumption
            tables with their business context and technical specifications.

    Returns:
        dict: Dictionary mapping table names to their metadata

    Examples:
    --------
    **Scalar Example: Basic Metadata Listing**

    ```python
    from gaspatchio_core.assumptions import Table, list_tables_with_metadata
    import polars as pl

    # Register tables with rich metadata
    mortality_data = pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.004, 0.015]})

    Table(
        name="mortality_meta_ex1",
        source=mortality_data,
        dimensions={"age": "age"},
        value="rate",
        metadata={
            "description": "Base mortality rates for healthy lives",
            "source": "Company Experience Study 2023",
            "effective_date": "2024-01-01",
        },
    )

    # Check table has metadata
    tables_metadata = list_tables_with_metadata()
    print(f"mortality_meta_ex1 has metadata: {'mortality_meta_ex1' in tables_metadata}")
    ```

    ```text
    mortality_meta_ex1 has metadata: True
    ```

    **Vector Example: Model Documentation Report**

    ```python
    from gaspatchio_core.assumptions import Table, list_tables_with_metadata
    import polars as pl

    # Register multiple tables with metadata
    mortality_df = pl.DataFrame({
        "age": [30, 35, 40],
        "rate": [0.001, 0.002, 0.004]
    })

    lapse_df = pl.DataFrame({
        "duration": [1, 2, 3],
        "rate": [0.05, 0.08, 0.12]
    })

    # Create tables with metadata
    Table(
        name="mortality_meta_ex2",
        source=mortality_df,
        dimensions={"age": "age"},
        value="rate",
        metadata={"source": "2017 CSO", "version": "v2.1"}
    )

    Table(
        name="lapse_meta_ex2",
        source=lapse_df,
        dimensions={"duration": "duration"},
        value="rate",
        metadata={"source": "Company Study", "quality": "High"}
    )

    # Check tables with metadata
    tables_meta = list_tables_with_metadata()
    has_mortality = "mortality_meta_ex2" in tables_meta
    has_lapse = "lapse_meta_ex2" in tables_meta
    print("Found 2 tables with metadata")
    print(f"mortality_meta_ex2 registered: {has_mortality}")
    print(f"lapse_meta_ex2 registered: {has_lapse}")
    ```

    ```text
    Found 2 tables with metadata
    mortality_meta_ex2 registered: True
    lapse_meta_ex2 registered: True
    ```
    """
    return _TABLE_METADATA.copy()
