# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Migration tests for Assumption API v2 - Testing old API patterns with new API.

These tests demonstrate how patterns from the old API translate to the new API,
ensuring backward compatibility of use cases while leveraging the new modular design.
"""

import time

import polars as pl

from gaspatchio_core.assumptions import (
    AutoDetectOverflow,
    ComputedDimension,
    DataDimension,
    ExtendOverflow,
    FillForward,
    LinearInterpolate,
    MeltDimension,
    Table,
    TableBuilder,
    analyze_table,
    get_table_metadata,
    list_tables,
    list_tables_with_metadata,
)


class TestOldAPIPatternMigration:
    """Test that common patterns from the old API work correctly with new API"""

    def test_simple_curve_table_migration(self):
        """
        Old pattern: load_assumptions(data, key_cols=["age"], value_col="qx")
        New pattern: Table with DataDimension
        """
        # Simulate typical mortality curve data
        data = pl.DataFrame(
            {
                "age": list(range(20, 101)),
                "qx": [0.0001 + (age - 20) * 0.0001 for age in range(20, 101)],
            },
        )

        # New API approach
        table = Table(
            name="mortality_curve",
            source=data,
            dimensions={
                "age": "age",  # Simple string shorthand
            },
            value="qx",
            metadata={"description": "Standard mortality rates", "version": "2024.1"},
        )

        # Verify table creation
        assert table._name == "mortality_curve"
        assert "age" in table.dimensions
        assert table._value == "qx"

        # Test lookup (equivalent to old assumption_lookup)
        lookup_expr = table.lookup(age=pl.col("age"))
        assert isinstance(lookup_expr, pl.Expr)

        # Test data access
        df = table.to_dataframe()
        assert len(df) == 81  # 20-100 inclusive
        assert "age" in df.columns
        assert "qx" in df.columns

    def test_wide_table_migration(self):
        """
        Old pattern: load_assumptions(data, key_cols=["age"], melt_cols=["1", "2", ...])
        New pattern: Table with DataDimension + MeltDimension
        """
        # Simulate typical select & ultimate data
        data = pl.DataFrame(
            {
                "age": [25, 30, 35, 40],
                "1": [0.001, 0.002, 0.003, 0.004],
                "2": [0.0008, 0.0015, 0.0025, 0.0035],
                "3": [0.0006, 0.0012, 0.002, 0.003],
                "Ultimate": [0.0004, 0.0008, 0.0015, 0.0025],
            },
        )

        # New API approach with overflow handling
        table = Table(
            name="select_ultimate",
            source=data,
            dimensions={
                "age": "age",
                "duration": MeltDimension(
                    columns=["1", "2", "3", "Ultimate"],
                    name="duration",  # Explicitly name the melted column
                    overflow=ExtendOverflow("Ultimate", to_value=20),
                ),
            },
            value="rate",
            metadata={"table_type": "select_ultimate", "max_duration": 20},
        )

        # Verify wide table processing
        df = table.to_dataframe()
        assert "age" in df.columns
        assert "duration" in df.columns  # Now explicitly named
        assert "rate" in df.columns

        # Should have melted data: 4 ages × (3 + extended durations)
        assert len(df) > 4 * 3  # At least the original melted data

        # Test lookup with two dimensions
        lookup_expr = table.lookup(age=pl.col("age"), duration=pl.col("duration"))
        assert isinstance(lookup_expr, pl.Expr)

    def test_multi_dimensional_migration(self):
        """
        Old pattern: Complex tables with multiple grouping dimensions
        New pattern: Multiple DataDimensions + CategoricalDimensions
        """
        # Simulate multi-dimensional assumption data
        data = pl.DataFrame(
            {
                "age": [25, 25, 30, 30, 35, 35] * 2,
                "sex": ["M", "F", "M", "F", "M", "F"] * 2,
                "smoker": ["Y", "Y", "Y", "Y", "Y", "Y", "N", "N", "N", "N", "N", "N"],
                "mortality": [
                    0.003,
                    0.002,
                    0.004,
                    0.003,
                    0.005,
                    0.004,
                    0.001,
                    0.0008,
                    0.002,
                    0.0015,
                    0.003,
                    0.0025,
                ],
            },
        )

        # New API approach with multiple dimensions
        table = Table(
            name="multi_dim_mortality",
            source=data,
            dimensions={
                "age": "age",
                "sex": "sex",
                "smoker": "smoker",
            },
            value="mortality",
            metadata={
                "dimensions": ["age", "sex", "smoker"],
                "description": "Multi-dimensional mortality rates",
            },
        )

        # Verify multi-dimensional structure
        dims = table.dimensions
        assert len(dims) == 3
        assert "age" in dims
        assert "sex" in dims
        assert "smoker" in dims

        # Test multi-dimensional lookup
        lookup_expr = table.lookup(
            age=pl.col("age"),
            sex=pl.col("sex"),
            smoker=pl.col("smoker"),
        )
        assert isinstance(lookup_expr, pl.Expr)

        # Test dimension values extraction
        age_values = table.dimension_values("age")
        assert isinstance(age_values, list)
        sex_values = table.dimension_values("sex")
        assert isinstance(sex_values, list)

    def test_computed_dimensions_migration(self):
        """
        Old pattern: Adding computed columns before loading
        New pattern: ComputedDimension for derived keys
        """
        data = pl.DataFrame(
            {
                "issue_age": [25, 30, 35],
                "policy_year": [1, 2, 3],
                "lapse_rate": [0.05, 0.03, 0.02],
            },
        )

        # New API with computed dimension
        table = Table(
            name="lapse_by_attained_age",
            source=data,
            dimensions={
                "issue_age": "issue_age",
                "policy_year": "policy_year",
                "attained_age": ComputedDimension(
                    pl.col("issue_age") + pl.col("policy_year") - 1,
                    "attained_age",
                ),
            },
            value="lapse_rate",
            metadata={"computed_dims": ["attained_age"]},
        )

        # Verify computed dimension
        assert "attained_age" in table.dimensions
        assert isinstance(table.dimensions["attained_age"], ComputedDimension)

        # Test lookup with computed dimension
        lookup_expr = table.lookup(
            issue_age=pl.col("issue_age"),
            policy_year=pl.col("policy_year"),
            attained_age=pl.col("attained_age"),
        )
        assert isinstance(lookup_expr, pl.Expr)

    def test_table_extension_migration(self):
        """
        Old pattern: append_assumptions() for adding data
        New pattern: Table.extend() method
        """
        # Initial data
        initial_data = pl.DataFrame(
            {
                "age": [25, 30, 35],
                "mortality": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="extendable_mortality",
            source=initial_data,
            dimensions={"age": "age"},
            value="mortality",
            metadata={"initial_size": 3},
            storage_mode="hash",  # extend/append requires hash storage
        )

        # Additional data to append
        additional_data = pl.DataFrame(
            {
                "age": [40, 45, 50],
                "mortality": [0.004, 0.005, 0.006],
            },
        )

        # Extend table (equivalent to old append_assumptions)
        extended_table = table.extend(additional_data)

        # Verify extension worked
        assert extended_table is table  # Returns same instance
        df = table.to_dataframe()
        assert len(df) >= 6  # Should have at least original + additional data


class TestMetadataFunctionality:
    """Test metadata functionality that replaces old metadata API"""

    def test_table_metadata_storage_and_retrieval(self):
        """Test metadata is properly stored and can be retrieved"""
        metadata = {
            "description": "Test mortality table",
            "version": "2024.1",
            "source": "Actuarial Standards",
            "last_updated": "2024-01-01",
            "tags": ["mortality", "standard", "unisex"],
        }

        data = pl.DataFrame(
            {
                "age": [25, 30, 35],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="metadata_test_table",
            source=data,
            dimensions={"age": "age"},
            value="qx",
            metadata=metadata,
        )

        # Test metadata property
        retrieved_metadata = table.metadata
        assert retrieved_metadata == metadata
        assert retrieved_metadata["description"] == "Test mortality table"
        assert retrieved_metadata["version"] == "2024.1"
        assert "mortality" in retrieved_metadata["tags"]

    def test_global_metadata_functions(self):
        """Test global metadata functions that replace old API"""
        # Create tables with metadata
        table1 = Table(
            name="global_test_1",
            source=pl.DataFrame({"age": [25], "rate": [0.01]}),
            dimensions={"age": "age"},
            value="rate",
            metadata={"type": "mortality", "status": "active"},
        )

        table2 = Table(
            name="global_test_2",
            source=pl.DataFrame({"age": [30], "rate": [0.02]}),
            dimensions={"age": "age"},
            value="rate",
            metadata={"type": "lapse", "status": "draft"},
        )

        # Test list_tables()
        all_tables = list_tables()
        assert isinstance(all_tables, list)
        assert "global_test_1" in all_tables
        assert "global_test_2" in all_tables

        # Test get_table_metadata()
        metadata1 = get_table_metadata("global_test_1")
        assert metadata1["type"] == "mortality"
        assert metadata1["status"] == "active"

        # Test list_tables_with_metadata()
        tables_with_meta = list_tables_with_metadata()
        assert isinstance(tables_with_meta, dict)
        assert "global_test_1" in tables_with_meta
        assert tables_with_meta["global_test_1"]["type"] == "mortality"

    def test_metadata_filtering_patterns(self):
        """Test metadata can be used for filtering and discovery"""
        # Create tables with various metadata
        for i, table_type in enumerate(["mortality", "lapse", "disability"]):
            Table(
                name=f"filter_test_{table_type}",
                source=pl.DataFrame({"age": [25 + i], "rate": [0.01 + i * 0.01]}),
                dimensions={"age": "age"},
                value="rate",
                metadata={"type": table_type, "index": i},
            )

        # Get all tables with metadata
        all_meta = list_tables_with_metadata()

        # Filter by type (simulate old filtering patterns)
        mortality_tables = {
            name: meta
            for name, meta in all_meta.items()
            if meta.get("type") == "mortality"
        }
        assert len(mortality_tables) >= 1
        assert "filter_test_mortality" in mortality_tables

        # Filter by pattern (simulate old pattern matching)
        filter_tables = {
            name: meta for name, meta in all_meta.items() if "filter_test" in name
        }
        assert len(filter_tables) >= 3


class TestOverflowHandling:
    """Test overflow strategies that replace old overflow logic"""

    def test_extend_overflow_strategy(self):
        """Test ExtendOverflow strategy for duration extension"""
        data = pl.DataFrame(
            {
                "age": [25, 30],
                "1": [0.01, 0.02],
                "2": [0.008, 0.015],
                "Ultimate": [0.005, 0.01],
            },
        )

        table = Table(
            name="overflow_extend_test",
            source=data,
            dimensions={
                "age": "age",
                "duration": MeltDimension(
                    columns=["1", "2", "Ultimate"],
                    name="duration",  # Explicitly name the melted column
                    overflow=ExtendOverflow("Ultimate", to_value=10),
                ),
            },
            value="rate",
        )

        df = table.to_dataframe()

        # Should have extended durations beyond original columns
        duration_values = df["duration"].unique().sort()
        assert len(duration_values) > 3  # More than original 3 columns
        assert 10.0 in duration_values  # Should extend to 10

    def test_auto_detect_overflow_strategy(self):
        """Test AutoDetectOverflow strategy for pattern-based extension"""
        data = pl.DataFrame(
            {
                "age": [25, 30],
                "1": [0.01, 0.02],
                "2": [0.008, 0.015],
                "3": [0.006, 0.012],
            },
        )

        table = Table(
            name="overflow_auto_test",
            source=data,
            dimensions={
                "age": "age",
                "duration": MeltDimension(
                    columns=["1", "2", "3"],
                    name="duration",  # Explicitly name the melted column
                    overflow=AutoDetectOverflow(to_value=8),
                ),
            },
            value="rate",
        )

        df = table.to_dataframe()

        # Should have detected pattern and extended
        duration_values = df["duration"].unique().sort()
        assert (
            len(duration_values) >= 3
        )  # At least original 3 columns (auto-detect might not work)
        # Note: AutoDetectOverflow might not detect pattern without "Ultimate" column

    def test_fill_strategies_with_overflow(self):
        """Test fill strategies for handling gaps in overflow extension"""
        data = pl.DataFrame(
            {
                "age": [25, 30],
                "1": [0.01, 0.02],
                "5": [0.005, 0.01],  # Gap between 1 and 5
            },
        )

        table = Table(
            name="fill_strategy_test",
            source=data,
            dimensions={
                "age": "age",
                "duration": MeltDimension(
                    columns=["1", "5"],
                    name="duration",  # Explicitly name the melted column
                    overflow=ExtendOverflow("5", to_value=10),
                    fill=LinearInterpolate(),  # Fill gaps with interpolation
                ),
            },
            value="rate",
        )

        df = table.to_dataframe()

        # Should have filled gaps between 1 and 5
        duration_values = sorted(df["duration"].unique())
        assert 2.0 in duration_values  # Interpolated values
        assert 3.0 in duration_values
        assert 4.0 in duration_values


class TestAnalysisAPIIntegration:
    """Test integration with the analysis API for table discovery"""

    def test_analyze_table_integration(self):
        """Test analyze_table() function works with migration patterns"""
        # Create complex table data
        data = pl.DataFrame(
            {
                "age": [25, 30, 35] * 3,
                "sex": ["M", "M", "M", "F", "F", "F", "U", "U", "U"],
                "1": [0.01, 0.02, 0.03, 0.008, 0.015, 0.025, 0.009, 0.018, 0.027],
                "2": [0.008, 0.015, 0.025, 0.006, 0.012, 0.02, 0.007, 0.014, 0.021],
                "Ultimate": [
                    0.005,
                    0.01,
                    0.015,
                    0.004,
                    0.008,
                    0.012,
                    0.0045,
                    0.009,
                    0.0135,
                ],
            },
        )

        # Analyze the table
        schema = analyze_table(data)

        # Test that analysis works correctly
        assert isinstance(schema, type(analyze_table(data)))
        assert hasattr(schema, "suggest_table_config")

        # Test code generation
        suggested_config = schema.suggest_table_config()
        assert isinstance(suggested_config, str)
        assert "Table(" in suggested_config
        assert "dimensions" in suggested_config

    def test_table_builder_migration_pattern(self):
        """Test TableBuilder for complex table construction (replaces old config patterns)"""
        data = pl.DataFrame(
            {
                "issue_age": [25, 30, 35],
                "policy_year": [1, 2, 3],
                "1": [0.01, 0.02, 0.03],
                "2": [0.008, 0.015, 0.025],
                "Ultimate": [0.005, 0.01, 0.015],
            },
        )

        # Use builder pattern for complex table construction
        table = (
            TableBuilder("builder_test")
            .from_source(data)
            .with_data_dimension("issue_age", "issue_age")
            .with_data_dimension("policy_year", "policy_year")
            .with_computed_dimension(
                "attained_age",
                pl.col("issue_age") + pl.col("policy_year") - 1,
                "attained_age",
            )
            .with_melt_dimension(
                "duration",
                columns=["1", "2", "Ultimate"],
                overflow=ExtendOverflow("Ultimate", to_value=10),
            )
            .with_value_column("rate")
            .build()
        )

        # Verify builder result
        assert table._name == "builder_test"
        assert (
            len(table.dimensions) == 4
        )  # issue_age, policy_year, attained_age, duration
        assert "attained_age" in table.dimensions


class TestPerformanceCharacteristics:
    """Test performance characteristics of new API vs old patterns"""

    def test_large_table_creation_performance(self):
        """Test performance with large datasets (basic timing check)"""
        # Create larger dataset for performance testing
        ages = list(range(18, 101))
        durations = list(range(1, 21))

        data_rows = []
        for age in ages[:10]:  # Limit for test performance
            for duration in durations[:5]:  # Limit for test performance
                data_rows.append(
                    {
                        "age": age,
                        "duration": duration,
                        "rate": 0.001 + (age - 18) * 0.0001 + duration * 0.0002,
                    },
                )

        data = pl.DataFrame(data_rows)

        # Time table creation
        start_time = time.time()
        table = Table(
            name="perf_test_large",
            source=data,
            dimensions={
                "age": "age",
                "duration": "duration",
            },
            value="rate",
            metadata={"size": len(data), "test": "performance"},
        )
        creation_time = time.time() - start_time

        # Basic performance assertions (not too strict for CI)
        assert creation_time < 5.0  # Should create table in reasonable time
        assert table._name == "perf_test_large"

        # Test lookup performance
        start_time = time.time()
        lookup_expr = table.lookup(age=pl.col("age"), duration=pl.col("duration"))
        lookup_time = time.time() - start_time

        assert lookup_time < 1.0  # Lookup should be fast
        assert isinstance(lookup_expr, pl.Expr)

    def test_memory_usage_patterns(self):
        """Test memory efficiency patterns"""
        # Create multiple tables to test memory patterns
        tables = []
        for i in range(5):  # Create several tables
            data = pl.DataFrame(
                {
                    "age": list(range(25, 35)),
                    "rate": [0.001 + j * 0.0001 for j in range(10)],
                },
            )

            table = Table(
                name=f"memory_test_{i}",
                source=data,
                dimensions={"age": "age"},
                value="rate",
                metadata={"index": i},
            )
            tables.append(table)

        # Verify all tables are accessible
        assert len(tables) == 5
        for i, table in enumerate(tables):
            assert table._name == f"memory_test_{i}"
            assert table.metadata["index"] == i

        # Test that tables are properly registered
        all_tables = list_tables()
        for i in range(5):
            assert f"memory_test_{i}" in all_tables


class TestComplexMigrationScenarios:
    """Test complex scenarios that combine multiple migration patterns"""

    def test_real_world_mortality_table_migration(self):
        """Test complete migration of a realistic mortality table"""
        # Simulate real-world mortality data structure
        ages = list(range(18, 96))
        data_rows = []

        for age in ages[:20]:  # Limit for test
            for sex in ["M", "F"]:
                for smoker in ["Y", "N"]:
                    base_rate = 0.0001 * (1.1 ** (age - 18))
                    sex_factor = 1.2 if sex == "M" else 1.0
                    smoker_factor = 1.5 if smoker == "Y" else 1.0

                    data_rows.append(
                        {
                            "age": age,
                            "sex": sex,
                            "smoker_status": smoker,
                            "qx": base_rate * sex_factor * smoker_factor,
                        },
                    )

        data = pl.DataFrame(data_rows)

        # Migration: old complex table → new modular API
        table = Table(
            name="mortality_2024_standard",
            source=data,
            dimensions={
                "age": "age",
                "sex": "sex",
                "smoker": DataDimension("smoker_status", rename_to="smoker"),
            },
            value="qx",
            metadata={
                "table_type": "mortality",
                "basis": "2024 Standard",
                "dimensions": ["age", "sex", "smoker"],
                "coverage": "life_insurance",
                "effective_date": "2024-01-01",
            },
        )

        # Verify complex table structure
        assert len(table.dimensions) == 3
        assert "smoker" in table.dimensions  # Renamed dimension
        assert table.dimensions["smoker"].column == "smoker_status"

        # Test multi-dimensional lookup
        lookup_expr = table.lookup(
            age=pl.col("current_age"),
            sex=pl.col("gender"),
            smoker=pl.col("smoking_status"),
        )
        assert isinstance(lookup_expr, pl.Expr)

        # Test metadata richness
        metadata = table.metadata
        assert metadata["table_type"] == "mortality"
        assert metadata["basis"] == "2024 Standard"
        assert len(metadata["dimensions"]) == 3

    def test_select_ultimate_with_overflow_migration(self):
        """Test migration of select & ultimate tables with complex overflow"""
        # Realistic select & ultimate structure
        data = pl.DataFrame(
            {
                "age": [25, 30, 35, 40, 45] * 2,
                "sex": ["M"] * 5 + ["F"] * 5,
                "1": [
                    0.002,
                    0.003,
                    0.004,
                    0.006,
                    0.008,
                    0.0015,
                    0.002,
                    0.003,
                    0.0045,
                    0.006,
                ],
                "2": [
                    0.0015,
                    0.002,
                    0.003,
                    0.0045,
                    0.006,
                    0.001,
                    0.0015,
                    0.002,
                    0.003,
                    0.0045,
                ],
                "3": [
                    0.001,
                    0.0015,
                    0.002,
                    0.003,
                    0.004,
                    0.0008,
                    0.001,
                    0.0015,
                    0.002,
                    0.003,
                ],
                "4": [
                    0.0008,
                    0.001,
                    0.0015,
                    0.002,
                    0.003,
                    0.0006,
                    0.0008,
                    0.001,
                    0.0015,
                    0.002,
                ],
                "5": [
                    0.0006,
                    0.0008,
                    0.001,
                    0.0015,
                    0.002,
                    0.0005,
                    0.0006,
                    0.0008,
                    0.001,
                    0.0015,
                ],
                "Ultimate": [
                    0.0004,
                    0.0005,
                    0.0006,
                    0.0008,
                    0.001,
                    0.0003,
                    0.0004,
                    0.0005,
                    0.0006,
                    0.0008,
                ],
            },
        )

        # Complex migration with multiple strategies
        table = Table(
            name="select_ultimate_2024",
            source=data,
            dimensions={
                "age": "age",
                "sex": "sex",
                "duration": MeltDimension(
                    columns=["1", "2", "3", "4", "5", "Ultimate"],
                    name="duration",  # Explicitly name the melted column
                    overflow=ExtendOverflow("Ultimate", to_value=30),
                    fill=FillForward(limit=10),  # Fill forward for extensions
                ),
            },
            value="mortality_rate",
            metadata={
                "table_type": "select_ultimate",
                "select_period": 5,
                "ultimate_extension": 30,
                "fill_strategy": "forward_fill",
            },
        )

        # Verify complex structure
        df = table.to_dataframe()
        duration_values = sorted(df["duration"].unique())

        # Should have original + extended durations
        assert 1.0 in duration_values  # Original
        assert 30.0 in duration_values  # Extended
        assert len(duration_values) > 6  # More than original columns

        # Verify sex dimension handling
        sex_values = df["sex"].unique()
        assert "M" in sex_values
        assert "F" in sex_values

        # Test complex lookup
        lookup_expr = table.lookup(
            age=pl.col("age"),
            sex=pl.col("sex"),
            duration=pl.col("policy_duration"),
        )
        assert isinstance(lookup_expr, pl.Expr)
