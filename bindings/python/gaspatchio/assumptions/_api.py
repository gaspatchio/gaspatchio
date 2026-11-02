# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TID252, TRY003, EM101, EM102, E501, PLR0913, ANN204, FBT001, FBT002
# ruff: noqa: SLF001, B007, PERF102
# ruff: noqa: BLE001
"""
Main assumption table API (v2) - Table class with dimension-based structure.

This module replaces the old monolithic load_assumptions() function with a
modular system that separates concerns and improves composability.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

import polars as pl

from gaspatchio._dtypes import with_signed_zeros_as_zero
from gaspatchio._identity import source_sha_of
from gaspatchio._scenario_reads import rebound_read
from gaspatchio._table_lifecycle import registering_framework_owned
from gaspatchio._warning import warn
from gaspatchio.assumptions._data import (
    _REGISTERED_TABLE_SHAS,
    TableData,
    TableSupersededError,
    _declared_output_columns,
    _declared_text_columns,
    _normalise_on_missing,
)
from gaspatchio.frame.lowering.lookup import lookup_node
from gaspatchio.scenarios.shocks import Shock

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio.assumptions._dimensions import Dimension
    from gaspatchio.column.column_proxy import ColumnProxy

    # A dimension key is as often a line the model has not named yet --
    # ``mort.lookup(age=af.issue_age + af.month // 12)`` -- as it is a column
    # the frame already holds. Both arrive here and both have always worked;
    # only the annotation said otherwise.
    from gaspatchio.column.expression_proxy import ExpressionProxy
from loguru import logger

from .._internal import PyAssumptionTableRegistry
from ..column.proxy_aware_expr import ProxyAwareExpr
from ..frame.lowering.context import context_for_operands
from ..frame.lowering.polars import lower_polars
from ._analysis import TableSchema, analyze_table
from ._processing import (
    _answer_read_as_f64,
    _canonical_frame,
    _canonical_key_columns,
    _hash_processed_df,
    _held_as_counts,
    _in_its_kinds,
    _judged_frame,
    _normalised_dimensions,
    _refuse_a_duration_or_time_key,
    _shaped_frame,
)
from ._utils import _materialise, _normalise_key_dtypes

# Global metadata storage for assumption tables
_TABLE_METADATA: dict[str, dict[str, Any]] = {}

# A scenario id is a name or a number, and one table's ids are all one or the
# other: they fill a single column.
_ScenarioId = TypeVar("_ScenarioId", str, int)


class Table(TableData):
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
        dimensions: Mapping[str, str | Dimension],
        value: str = "rate",
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
        storage_mode: Literal["auto", "hash", "array"] = "auto",
        on_missing: str | float = "raise",
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
            on_missing: What a lookup miss does - "raise" (default) errors at
                collect() naming the table and the first missing keys; "nan"
                returns NaN for missing keys (the pre-0.6 behaviour); a number
                fills missing keys with that constant. Lookups are exact-match,
                so a miss usually means a data or key-mapping defect. Note that
                when/then/otherwise evaluates both branches, so a lookup guarded
                by a condition still runs on the excluded rows - declare those
                expected misses with on_missing="nan" on the lookup.

        Examples:
        --------
        **Scalar Example: Basic Mortality Table Creation**

        ```python
        from gaspatchio.assumptions import Table
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
        from gaspatchio.assumptions import Table
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

        # Normalize dimensions - convert strings to DataDimension objects.
        # The dict maps YOUR name -> SOURCE column name, so the source column
        # is renamed to the dimension name during processing; lookup() kwargs
        # then match the processed table's key columns (issue #30 — the
        # shorthand previously discarded the dict key and the rename never
        # happened).
        self._dimensions = _normalised_dimensions(dimensions)

        self._value = value
        self._validate = validate
        self._storage_mode = storage_mode
        self._on_missing_mode, self._on_missing_fill = _normalise_on_missing(on_missing)
        self._df: pl.DataFrame | None = None
        self._schema: TableSchema | None = None
        # Store Enum types for string key columns to enable auto-categorical conversion.
        # Maps column name -> pl.Enum with sorted categories for deterministic index mapping.
        self._key_categories: dict[str, pl.Enum] = {}
        # The kind of each key column held as a date, a timestamp, a duration
        # or a time of day before it was held as a whole number.
        self._key_kinds: Mapping[str, pl.DataType] = {}
        # A shocked copy answers to the table it was shocked from, so a
        # chain of with_shock() calls may keep naming the original target.
        self._shock_origin: str | None = None

        # The metadata this table was given, held by the table itself: a later
        # table built under the same name describes itself, not this one.
        self._metadata = None if metadata is None else metadata.copy()

        # Where the table was handed a file, the run record names that file:
        # a reviewer holding it re-reads it as this table. A frame names no
        # file, and the record says so rather than guessing which one it was.
        self._source_file = (
            Path(source).resolve() if isinstance(source, str | Path) else None
        )

        # Process the data during initialization
        self._process_data(source)

        # The name now answers to this table for lookups, so it answers to this
        # table's metadata too -- and to none where this table was given none,
        # rather than to whatever an earlier table of the same name was given.
        # Written once the table is built, so a build that fails leaves the
        # earlier table's entry where it was.
        if self._metadata is None:
            _TABLE_METADATA.pop(name, None)
        else:
            _TABLE_METADATA[name] = self._metadata.copy()
            logger.debug(f"Stored metadata for table '{name}': {metadata}")

    @classmethod
    def from_scenario_files(
        cls,
        scenario_files: Mapping[_ScenarioId, str | Path],
        scenario_column: str,
        dimensions: Mapping[str, str | Dimension],
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
            scenario_files: Mapping of scenario_id -> file path. The ids are
                all strings or all integers: they fill one column.
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
            from gaspatchio.assumptions import Table

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

    # String ids or integer ids, one or the other in a call. Declared as two
    # signatures so that a caller holding list[str] | list[int] type-checks,
    # and implemented once over the id type that from_scenario_files takes.
    @overload
    @classmethod
    def from_scenario_template(
        cls,
        path_template: str,
        scenario_ids: list[str],
        scenario_column: str,
        dimensions: Mapping[str, str | Dimension],
        value: str,
        name: str | None = None,
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> Table: ...
    @overload
    @classmethod
    def from_scenario_template(
        cls,
        path_template: str,
        scenario_ids: list[int],
        scenario_column: str,
        dimensions: Mapping[str, str | Dimension],
        value: str,
        name: str | None = None,
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> Table: ...
    @classmethod
    def from_scenario_template(
        cls,
        path_template: str,
        scenario_ids: list[_ScenarioId],
        scenario_column: str,
        dimensions: Mapping[str, str | Dimension],
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
            from gaspatchio.assumptions import Table

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
            from gaspatchio.assumptions import Table
            from gaspatchio.scenarios.shocks import MultiplicativeShock

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
            from gaspatchio.assumptions import Table
            from gaspatchio.scenarios._sensitivity import sensitivity_analysis
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
                    source=_in_its_kinds(base_df, base_table._key_kinds),
                    dimensions=base_table._rebuild_dimensions(),
                    value=base_table._value,
                    validate=False,
                    **base_table._rebuild_arguments(),
                )
                result[scenario_id]._carry_the_source_of(base_table)
            else:
                # Apply shocks sequentially
                table = base_table
                for shock in shock_list:
                    table = table.with_shock(shock)

                # Rename to include scenario ID. Reconstruction dims must come
                # from the table whose PROCESSED frame is the source: after
                # with_shock, an explicit rename_to has already collapsed to
                # the dimension name.
                result[scenario_id] = Table(
                    name=f"{base_table._name}_{scenario_id}",
                    source=_in_its_kinds(table.to_dataframe(), table._key_kinds),
                    dimensions=table._rebuild_dimensions(),
                    value=base_table._value,
                    validate=False,
                    **base_table._rebuild_arguments(),
                )
                result[scenario_id]._carry_the_source_of(table)

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

        current_df = _shaped_frame(
            df,
            self._dimensions,
            self._value,
            validate=self._validate,
            name=self._name,
        )

        # Collect key columns (all columns except the value column), in the
        # canonical order: ascending by name. The order a source happened to
        # list its columns in is how it was published, not what it says, so
        # it must not reach the table's identity (spec section 12.3).
        key_columns = _canonical_key_columns(current_df.columns, self._value)

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

        # A date or a timestamp is a key of its own kind: a lookup reads it
        # only with a key of that kind, converted to the table's unit. It is
        # held as the whole number of its unit -- exact for a nanosecond
        # timestamp, where a double would merge two instants into one key --
        # and its kind is kept beside the table, which is the kind its
        # fingerprint is taken in. A duration or a time of day has no kind
        # the fingerprint can be taken in, and is refused by name.
        _refuse_a_key_column_of_no_scalar_kind(self._name, current_df, key_columns)
        _refuse_a_duration_or_time_key(self._name, current_df, key_columns)
        current_df, self._key_kinds = _held_as_counts(current_df, key_columns)

        processed_df = _judged_frame(
            current_df, self._dimensions, self._value, name=self._name
        )

        # Store the processed DataFrame
        self._df = processed_df

        # Warn if this name was already registered in this process with DIFFERENT
        # content. The native kernel refuses previously built lazy lookups once
        # the registered content changes; warn here so callers can rebuild them.
        # Byte-identical re-registration (the common issue-#39 reentrancy case)
        # stays silent. Never raise here — that would reintroduce the #39 bug.
        # Hash the processed frame itself (exactly the bytes handed to Rust); it
        # is in canonical form above, so identical source data yields an
        # identical hash whatever order its rows or columns arrived in.
        content_sha = _hash_processed_df(processed_df, self._key_kinds)
        self._registered_sha = content_sha
        previous_sha = _REGISTERED_TABLE_SHAS.get(self._name)
        # A table on the framework's own lifecycle (a scenario batch's stacked
        # table, collected before its name is registered again) leaves no
        # lookup behind to go stale, so it replaces itself without a word.
        if (
            previous_sha is not None
            and previous_sha != content_sha
            and not registering_framework_owned()
        ):
            warn(
                f"Assumption table '{self._name}' was re-registered with "
                f"different data. Lazy expressions already built against the "
                f"previous version will refuse to collect. Give the tables "
                f"distinct names, or rebuild expressions from the current Table "
                f"after re-registering.",
            )

        # Register with Rust registry using idempotent method. The frame is
        # freshly sorted, so no fixed-width array crosses as a slice of a
        # larger one: Polars 1.42.1's Arrow export double-counts such a
        # slice's offset and the import panics (pola-rs/polars#28583, fixed
        # upstream in 1.43.2; the pin stays at 1.42.1 until the move to Polars 2).
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
                fingerprint=content_sha,
            )
            # Record the hash only once the registry actually holds this data;
            # recording before a failed replacement would poison the guard and
            # wrongly refuse lookups from the still-valid previous table.
            _REGISTERED_TABLE_SHAS[self._name] = content_sha
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
            # The error is raised as it stands; this only says which table.
            logger.debug(f"Failed to register table '{self._name}' with Rust: {e}")
            raise

    def lookup(
        self,
        _dimensions: Mapping[str, str | pl.Expr | ColumnProxy | ExpressionProxy]
        | None = None,
        on_missing: str | float | None = None,
        **kwargs: str | pl.Expr | ColumnProxy | ExpressionProxy,
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

        The returned expression cooperates with ``af`` columns in either
        operand order: ``table.lookup(...) * af.pols`` and
        ``af.pols * table.lookup(...)`` agree, including the list-column
        operator shims (``**`` on per-period columns). That guarantee covers
        *operators* only — an Expr method call (``.clip()``,
        ``.fill_null()``, …) returns a plain polars expression, after which
        a proxy operand raises again. For method chains, assign the lookup
        to a column first (``af.mort_rate = table.lookup(...)``) and
        continue from the column.

        Args:
            _dimensions: Optional dictionary mapping dimension names to columns/expressions
            on_missing: Per-lookup override of the table's miss policy -
                "raise", "nan", or a numeric fill constant. Defaults to the
                policy set on the Table. Use on_missing="nan" for lookups
                inside when/then/otherwise guards: both branches evaluate, so
                guarded rows still run the lookup and their misses are expected.
            **kwargs: Dimension name to column/expression mapping

        Returns:
            Polars expression for the lookup

        Examples:
        --------
        **Scalar Example: Simple Mortality Lookup**

        ```python
        from gaspatchio.assumptions import Table
        from gaspatchio import ActuarialFrame
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
        from gaspatchio.assumptions import Table
        from gaspatchio import ActuarialFrame
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
        all_dimensions: dict[str, str | pl.Expr | ColumnProxy | ExpressionProxy] = {}
        if _dimensions:
            all_dimensions.update(_dimensions)
        all_dimensions.update(kwargs)
        # Inside a scenario run that shocks this table, the read lowers against
        # the table shocked for the run's scenarios, keyed by the scenario
        # axis; every other read is left exactly as the model wrote it.
        table: TableData = self
        keys: Mapping[str, object] = all_dimensions
        rebound = rebound_read(self, all_dimensions)
        if rebound is not None:
            table, keys = rebound
        ctx = context_for_operands(keys.values())
        node = lookup_node(table, keys, on_missing, ctx=ctx)
        # Bound to the frame the keys came from, so a method chained on the
        # lookup means what it means on the column it would be assigned to.
        parent = None if ctx is None else ctx.frame
        return ProxyAwareExpr.wrap(lower_polars(node, ctx), node=node, parent=parent)

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

        Raises:
            ValueError: If the slice repeats a key tuple the table already
                holds, or repeats one within itself: extend adds rows the
                table does not have yet.
            RuntimeError: If another Table has been registered under this
                name since this one was built.

        A table held in either storage extends: one held as a hash map takes
        the new rows in place, and one held as a dense array -- what
        ``storage_mode="auto"`` picks for an ordinary table -- is built again
        whole from the extended rows, under the storage it was asked for.

        Examples:
        --------
        **Scalar Example: Extending Mortality Table**

        ```python
        from gaspatchio.assumptions import Table
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
        from gaspatchio.assumptions import Table
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
        base_df = self.to_dataframe()
        expected_fingerprint = self._registered_sha

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

        # Believe the declaration here too: an undeclared column in an
        # extension slice must not become a key, or the appended slice's key
        # schema silently diverges from the (already trimmed) base table and
        # the append fails without naming the column. Use the effective
        # dimensions for THIS slice — extend() accepts per-slice overrides.
        declared_outputs = set(_declared_output_columns(extend_dimensions).values())
        undeclared = [
            c
            for c in current_df.columns
            if c not in declared_outputs and c != self._value
        ]
        if undeclared:
            current_df = current_df.drop(undeclared)
            logger.debug(
                f"Table '{self._name}': ignoring undeclared columns "
                f"{undeclared} in extend() slice (neither in dimensions= "
                f"nor the value column)",
            )

        # Get key columns, in the canonical order the base table holds them.
        key_columns = _canonical_key_columns(current_df.columns, self._value)

        # A date-like key is appended as the count the table holds it by, in
        # the table's own unit and zone: a microsecond count appended to a
        # millisecond table as it stands would be another instant. A duration
        # or a time of day is refused by name, as at construction.
        _refuse_a_duration_or_time_key(self._name, current_df, key_columns)
        current_df = _in_the_kinds_of(
            self._name, current_df, key_columns, self._key_kinds
        )
        current_df, _ = _held_as_counts(current_df, key_columns)

        # Normalize ordinary keys without rounding wide integer identities,
        # leaving a key declared text as text, as the base table did.
        declared_text = _declared_text_columns(extend_dimensions)
        processed_df = _answer_read_as_f64(
            _normalise_key_dtypes(
                current_df
                if registering_framework_owned()
                else with_signed_zeros_as_zero(current_df),
                [col for col in key_columns if col not in declared_text],
            ),
            self._value,
            name=self._name,
        )

        # Build the post-extension frame and its content identity BEFORE the
        # native append, re-sorted by keys to keep the _process_data
        # invariant (self._df sorted, hash canonical). A Python-side failure
        # here (e.g. a schema mismatch polars rejects that the native layer
        # would accept) aborts the extend with the registry untouched — the
        # two sides must commit together or not at all.
        all_key_columns = [c for c in base_df.columns if c != self._value]
        if set(processed_df.columns) == set(base_df.columns):
            # The slice in the base's canonical column order, so a slice whose
            # source lists its columns differently appends rather than failing.
            processed_df = processed_df.select(base_df.columns)
        extended_df = _canonical_frame(
            pl.concat([base_df, processed_df]), all_key_columns, self._value
        )
        _refuse_a_key_the_table_holds(self._name, extended_df, all_key_columns)
        content_sha = _hash_processed_df(extended_df, self._key_kinds)

        # Append to existing table using Rust registry
        try:
            registry = PyAssumptionTableRegistry()
            if registry.get_table_storage_mode(self._name) == "array":
                # The native append adds rows to a hash map; a table held as a
                # dense array -- what "auto" picks for an ordinary table -- is
                # built again whole from the extended frame instead, under the
                # same storage request, after the same moved-table check.
                self._refuse_if_moved(expected_fingerprint)
                registry.register_or_replace_table(
                    name=self._name,
                    df=extended_df,
                    keys=all_key_columns,
                    value_column=self._value,
                    force_replace=True,
                    storage_mode=self._storage_mode,
                    fingerprint=content_sha,
                )
            else:
                registry.append_to_table(
                    name=self._name,
                    df=processed_df,
                    keys=key_columns,
                    value_column=self._value,
                    expected_fingerprint=expected_fingerprint,
                    fingerprint=content_sha,
                )
            logger.debug(
                f"Successfully extended table '{self._name}' with {len(processed_df)} additional rows",
            )
        except Exception as e:
            # The error is raised as it stands; this only says which table.
            logger.debug(f"Failed to extend table '{self._name}': {e}")
            raise

        # Commit the Python-side state; plain assignments cannot fail, so the
        # registry and this object's identity move together. Re-stamping the
        # hashes matters: leaving them at the pre-extension value makes a
        # later registration of the ORIGINAL data read as idempotent
        # reentrancy, and a lookup from this object then passes the
        # superseded guard while the appended rows are silently gone.
        self._df = extended_df
        self._registered_sha = content_sha
        _REGISTERED_TABLE_SHAS[self._name] = content_sha
        # The table now holds rows its file does not, so it is no longer the
        # file's to vouch for: a record names no file for it.
        self._source_file = None

        return self

    def _refuse_if_moved(self, expected_fingerprint: str) -> None:
        """Refuse an extend of this object once its table has been replaced.

        The native append refuses when the registry no longer holds the
        version this object stamps; a whole rebuild does the same check
        against the version this process last registered under the name.
        """
        if _REGISTERED_TABLE_SHAS.get(self._name) == expected_fingerprint:
            return
        msg = (
            f"Assumption table '{self._name}' changed before it could be "
            f"extended: another Table registered under this name since this "
            f"one was built. Call extend() on the current Table instead."
        )
        # The type the native append's refusal arrives as, so one refusal is
        # one exception whichever storage the table is held in.
        raise RuntimeError(msg)

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
        from gaspatchio.assumptions import Table
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
        from gaspatchio.assumptions import Table
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
        from gaspatchio.assumptions import Table
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
        from gaspatchio.assumptions import Table
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
        when this table was created. It is this table's own: a later table built
        under the same name, with other metadata or none, does not change it.

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
        from gaspatchio.assumptions import Table
        import polars as pl

        data = pl.DataFrame({"age": [30, 35], "rate": [0.001, 0.002]})
        table = Table(
            "test", data, {"age": "age"}, "rate", metadata={"source": "2023 Study"}
        )

        meta = table.metadata
        print(f"Source: {meta['source'] if meta else 'None'}")
        ```

        """
        return None if self._metadata is None else self._metadata.copy()

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
        from gaspatchio.assumptions import Table
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
            return mode or self._storage_mode

    def canonical_form(self) -> dict[str, Any]:
        """Deterministic JSON-encodable identity recipe for the audit chain.

        Returns a dictionary that uniquely identifies this table's content
        and shape: name, sorted dimension keys, value column, and the
        table's content fingerprint (:meth:`fingerprint`). Two tables with
        the same content but loaded with their rows or columns in different
        orders produce the same canonical_form; two tables differing in any
        cell value produce different ones.

        !!! note "When to use"
            * **Audit chains:** Feed into `source_sha()` so a regulator
              can verify the table used in a SCR run by hash alone.
            * **Reproducibility checks:** Confirm that a Table reloaded
              from disk matches the Table the run was authored against.
            * **Change detection:** Compare canonical_form between
              versions to detect data drift without re-running models.

        Returns:
            Dictionary with `kind`, `name`, sorted `dimensions`,
            `value_column`, and `content_sha`, which is exactly
            :meth:`fingerprint`.

        Examples:
        --------
        ```python
        import polars as pl
        from gaspatchio.assumptions import Table

        mortality = Table(
            name="mortality",
            source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]}),
            dimensions={"age": "age"},
            value="rate",
        )

        recipe = mortality.canonical_form()
        print(sorted(recipe.keys()))
        print(recipe["content_sha"] == mortality.fingerprint())
        ```

        ```text
        ['content_sha', 'dimensions', 'kind', 'name', 'value_column']
        True
        ```
        """
        return {
            "kind": "Table",
            "name": self._name,
            "dimensions": sorted(self._dimensions.keys()),
            "value_column": self._value,
            "content_sha": self.fingerprint(),
        }

    def fingerprint(self) -> str:
        """Return the table's content identity: the hash the run record carries.

        A SHA-256 over the table's processed values in canonical form --
        key columns ascending by name, the value column last, rows ascending
        by the keys -- under the content grammar of the graph artifact
        specification (section 12.3). It is the `fingerprint` of this
        table's entry in a calculation graph's `assumptions` section and the
        `table_fingerprint` every lookup node reading it carries, so it is
        the hash `gspio diff` and the viewer compare, and it feeds the graph
        fingerprint `gspio verify` checks.

        **It depends on the values and nothing else.** Reordering the
        source's rows or columns, re-encoding the file (parquet to CSV, a
        different compression), or renaming the table leaves it unchanged;
        a changed cell changes it.

        **Which hash is which.** A table carries two stamps and they answer
        different questions:

        | Stamp | Identifies | Moves when |
        |-------|-----------|------------|
        | `fingerprint()` | the **content** -- the values a lookup answers from | any value changes |
        | `source_sha()` | the **table object** -- its recipe: name, dimensions, value column and this fingerprint | the values change, or the table is renamed or re-keyed |

        Use `fingerprint()` to ask "is this the same basis the record was
        run on?" -- it is the one the record carries. Use `source_sha()` to
        pin the whole configured table, name included.

        !!! note "When to use"
            * **Audit:** Match a live table against the `fingerprint` a
              run record's `assumptions` entry carries.
            * **Quarter-over-quarter drift:** Two loads of the same rates
              agree however the file was laid out; a moved rate does not.
            * **Pre-run checks:** Compare against a known-good fingerprint
              before a production batch.

        Returns:
            `sha256:` followed by 64 lowercase hexadecimal digits.

        Examples:
        --------
        ```python
        import polars as pl
        from gaspatchio.assumptions import Table

        rates = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
        published = Table("mortality", rates, {"age": "age"}, "rate")
        reordered = Table(
            "mortality_copy",
            rates.select("rate", "age").reverse(),
            {"age": "age"},
            "rate",
        )

        print(published.fingerprint() == reordered.fingerprint())
        print(published.source_sha() == reordered.source_sha())
        print(published.fingerprint() == published.source_sha())
        ```

        ```text
        True
        False
        False
        ```
        """
        return self._registered_sha

    def source_sha(self) -> str:
        """SHA-256 over `canonical_form` bytes: the table object's identity.

        Hashes the table's recipe -- name, dimensions, value column and its
        content :meth:`fingerprint` -- so it changes when the values do and
        also when the table is renamed or re-keyed. It is **not** the hash a
        run record carries for the table: that is :meth:`fingerprint`, the
        content identity, which ignores the name. Combine with
        `ScenarioRun.source_sha()` to attest that an SCR run used a
        specific, named input table.

        !!! note "When to use"
            * **Audit sidecar:** Embedded under the plan's
              `canonical_form`/`source_sha` chain so the configured table is
              identifiable from the run record alone.
            * **Pre-run validation:** Compare against a known-good SHA
              before running production batches to catch silent drift in
              assumption files or in how they are configured.
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
        from gaspatchio.assumptions import Table

        rates = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
        q2 = Table("mortality_2026q2", rates, {"age": "age"}, "rate")
        q3 = Table("mortality_2026q3", rates, {"age": "age"}, "rate")

        print(q2.source_sha().startswith("sha256:"))
        print(q2.source_sha() == q3.source_sha())  # renamed: the recipe moved
        print(q2.fingerprint() == q3.fingerprint())  # same rates: content did not
        ```

        ```text
        True
        False
        True
        ```
        """
        return source_sha_of(self.canonical_form())

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
            New Table with shocked values, built with this table's
            ``storage_mode``, ``on_missing`` policy and metadata.

        Raises:
            ValueError: The shock's ``table=`` names a different table than
                this one (or than the table this shocked copy came from), or
                its ``column=`` is not this table's value column. A shock
                with no ``table=`` takes this table as its target.

        Examples:
        --------
        **Stress testing mortality:**

        ```python no_output_check
        from gaspatchio.assumptions import Table
        from gaspatchio.scenarios.shocks import MultiplicativeShock
        import polars as pl

        mortality_data = pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.002]})
        mortality = Table("mortality", mortality_data, {"age": "age"}, "qx")

        # Create 20% stressed version
        shocked = mortality.with_shock(MultiplicativeShock(factor=1.2))
        ```

        **Adding basis points to rates:**

        ```python no_output_check
        from gaspatchio.assumptions import Table
        from gaspatchio.scenarios.shocks import AdditiveShock
        import polars as pl

        rates_data = pl.DataFrame({"term": [1, 2], "rate": [0.05, 0.06]})
        rates_table = Table("rates", rates_data, {"term": "term"}, "rate")

        # Add 50bps to discount rates
        stressed_rates = rates_table.with_shock(AdditiveShock(delta=0.005))
        ```

        """
        if self._df is None:
            raise RuntimeError("Table data not processed")

        if not isinstance(shock, Shock):
            msg = f"Expected Shock instance, got {type(shock).__name__}"
            raise TypeError(msg)
        # The scenarios package imports this module while it initialises.
        from gaspatchio.scenarios._targets import (  # noqa: PLC0415 -- cycle, above
            check_conditions_select,
            check_shock_applies_to,
        )

        # A shock written for another table, or with a column it would not
        # move, is refused rather than applied to this table's value column;
        # so is a condition this table cannot read or that selects none of it.
        origin = self._shock_origin
        check_shock_applies_to(shock, self, origin)
        check_conditions_select("Table.with_shock()", shock, self._name, self._df)

        # Apply shock expression to value column
        shocked_df = self._df.with_columns(
            shock.to_expression(pl.col(self._value)).alias(self._value)
        )

        # Determine name for shocked table
        shocked_name = name or f"{self._name}_shocked"

        # Create new Table with shocked data
        # Recreate dimensions dict against the PROCESSED column names,
        # preserving the lookup vocabulary (issue #30 review follow-up).
        new_dimensions = self._rebuild_dimensions()

        shocked = Table(
            name=shocked_name,
            source=_in_its_kinds(shocked_df, self._key_kinds),
            dimensions=new_dimensions,
            value=self._value,
            validate=False,  # Already validated
            **self._rebuild_arguments(),
        )
        shocked._shock_origin = origin or self._name
        shocked._carry_the_source_of(
            self,
            {"step": "shocked", "column": self._value, "by": shock.describe()},
        )
        return shocked

    def _carry_the_source_of(self, base: TableData, *steps: dict[str, Any]) -> None:
        """Name the file ``base`` was read from, with the steps that made this table.

        A shocked or scenario-stacked table is built from ``base``'s
        processed frame, and that frame came from the file ``base`` was
        handed: so the record names that file, and lists every step between
        the file and this table -- ``base``'s own recipe, what it carried
        over, and the shock or stacking that made this one -- so a reviewer
        holding the file reads it as the source and never as a plain read of
        this table.
        """
        from ._processing import shaping_steps  # noqa: PLC0415 -- beside _api

        self._source_file = base._source_file
        self._key_kinds = {**base._key_kinds, **self._key_kinds}
        self._inherited_steps = (
            *base._inherited_steps,
            *shaping_steps(base._dimensions),
            *steps,
        )

    def _rebuild_arguments(self) -> dict[str, Any]:
        """Return the construction arguments a rebuilt copy of this table keeps.

        A shocked, per-scenario or scenario-stacked copy is built from this
        table's processed data, and must be built the way the user built this
        one: under the same ``storage_mode`` (a layout ``auto`` cannot encode
        is why a user names one), the same ``on_missing`` policy, and the same
        metadata. ``name``, ``source``, ``dimensions``, ``value`` and
        ``validate`` are the rebuilding caller's to give.
        """
        on_missing: str | float = (
            self._on_missing_fill
            if self._on_missing_mode == "fill" and self._on_missing_fill is not None
            else self._on_missing_mode
        )
        return {
            "storage_mode": self._storage_mode,
            "on_missing": on_missing,
            "metadata": self.metadata,
        }


def _in_the_kinds_of(
    name: str,
    frame: pl.DataFrame,
    key_columns: list[str],
    kinds: Mapping[str, pl.DataType],
) -> pl.DataFrame:
    """Return an extension slice with each date-like key in the table's own kind.

    A slice keyed in another unit is converted to the table's; a slice key of
    another kind than the table's -- a date against timestamps, a number
    against dates, a zone-naive timestamp against zoned ones -- is refused by
    kind, as a lookup key of another kind is: no conversion between them is
    the slice's to guess.
    """
    converted: list[pl.Expr] = []
    for column in key_columns:
        held = frame.schema[column]
        kind = kinds.get(column)
        if kind is None and not held.is_temporal():
            continue
        if kind is None or not _of_one_kind(held, kind):
            table_holds = "numbers or text" if kind is None else str(kind)
            msg = (
                f"Table {name!r} cannot be extended with key column {column!r} "
                f"of {held}: the table holds {column!r} as {table_holds}, and a "
                "key of another kind never equals one of these. Convert the "
                f"slice's column first: pl.col({column!r}).cast(<the table's "
                "kind>)."
            )
            raise TypeError(msg)
        if held != kind:
            converted.append(pl.col(column).cast(kind))
    return frame.with_columns(converted) if converted else frame


def _of_one_kind(held: pl.DataType, kind: pl.DataType) -> bool:
    """Return whether a slice's key type is the table's kind, whatever its unit.

    One kind is one base type -- a date or a timestamp -- and, for a timestamp, zoned or zone-naive on both sides; the unit
    and the zone's name are conversions, not kinds.
    """
    if held.base_type() != kind.base_type():
        return False
    if isinstance(kind, pl.Datetime):
        return (getattr(held, "time_zone", None) is None) == (kind.time_zone is None)
    return True


def _refuse_a_key_column_of_no_scalar_kind(
    name: str, frame: pl.DataFrame, key_columns: list[str]
) -> None:
    """Refuse a key column whose cells are not one value each, by its kind.

    A key is one value per row -- a number, text, a flag, a date -- and a
    lookup matches it exactly. A column of lists, fixed-width arrays,
    structs or Python objects holds no such value, so it is refused here,
    naming the column and its type, before the registry is asked to encode
    it and answers about a row instead of the column's kind.
    """
    for column in key_columns:
        dtype = frame.schema[column]
        if dtype.is_nested() or dtype.base_type() in (pl.Object, pl.Binary):
            msg = (
                f"Table {name!r} key column {column!r} holds {dtype}, and a key "
                "is one value per row -- a number, text, a flag or a date -- that "
                "a lookup matches exactly. Key the table by a column of one of "
                f"those kinds, or keep {column!r} out of the dimensions: unnest "
                "or explode it into scalar columns before building the table."
            )
            raise ValueError(msg)


def _refuse_a_key_the_table_holds(
    name: str, extended: pl.DataFrame, key_columns: list[str]
) -> None:
    """Refuse an extend whose slice repeats a key tuple, naming the first one.

    ``Table.extend`` adds rows the table does not have yet: a key tuple that
    is there twice would answer two rates for one cell, which construction
    refuses too. Judged over the extended frame, so a tuple the slice repeats
    within itself is caught as well as one the table already holds.
    """
    repeated = extended.filter(extended.select(key_columns).is_duplicated())
    if repeated.is_empty():
        return
    first = repeated.row(0, named=True)
    where = ", ".join(f"{column}={first[column]!r}" for column in key_columns)
    tuples = repeated.select(key_columns).n_unique()
    more = f" (and {tuples - 1} more)" if tuples > 1 else ""
    msg = (
        f"Table '{name}' would hold two rates at {where}{more} once extended: "
        f"extend() adds rows the table does not have yet. Drop those rows "
        f"from the slice, or build the table again from the combined source "
        f"if the slice is meant to replace them."
    )
    raise ValueError(msg)


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
    from gaspatchio.assumptions import Table, get_table_metadata
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
    from gaspatchio.assumptions import Table, get_table_metadata
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
    from gaspatchio.assumptions import Table, list_tables
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
    from gaspatchio.assumptions import Table, list_tables
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
        names: list[str] = registry.list_tables()
    except Exception as e:
        warn(
            f"list_tables() could not read the table registry, so it lists none: "
            f"{e}. The registry lives in gaspatchio's compiled extension; if this "
            f"repeats, reinstall gaspatchio."
        )
        return []
    return names


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
    from gaspatchio.assumptions import Table, list_tables_with_metadata
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
    from gaspatchio.assumptions import Table, list_tables_with_metadata
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


__all__ = [
    "Table",
    "TableSupersededError",
    "get_table_metadata",
    "list_tables",
    "list_tables_with_metadata",
]
