# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the enhanced analysis module with analyze_table function.
"""

import polars as pl
import pytest

from gaspatchio.assumptions._analysis import (
    DimensionInfo,
    InterpolationHint,
    TableSchema,
    _analyze_numeric_pattern,
    _detect_interpolation_opportunities,
    _is_likely_id_column,
    analyze_table,
)


class TestDimensionInfo:
    """Test DimensionInfo dataclass"""

    def test_dimension_info_creation(self):
        """Test basic DimensionInfo creation"""
        dim = DimensionInfo(
            name="age",
            dtype="Int64",
            unique_count=10,
            sample_values=[30, 31, 32, 33, 34],
            suggested_type="key",
            numeric_pattern="30-39",
        )

        assert dim.name == "age"
        assert dim.dtype == "Int64"
        assert dim.unique_count == 10
        assert dim.sample_values == [30, 31, 32, 33, 34]
        assert dim.suggested_type == "key"
        assert dim.numeric_pattern == "30-39"


class TestInterpolationHint:
    """Test InterpolationHint dataclass"""

    def test_interpolation_hint_creation(self):
        """Test basic InterpolationHint creation"""
        hint = InterpolationHint(
            dimension="age",
            detected_values=[30, 32, 35],
            missing_values=[31, 33, 34],
            suggested_method="linear",
        )

        assert hint.dimension == "age"
        assert hint.detected_values == [30, 32, 35]
        assert hint.missing_values == [31, 33, 34]
        assert hint.suggested_method == "linear"


class TestTableSchema:
    """Test TableSchema dataclass and methods"""

    def test_curve_table_config_generation(self):
        """Test code generation for curve tables"""
        dimensions = [
            DimensionInfo("age", "Int64", 10, [30, 31], "key"),
            DimensionInfo("rate", "Float64", 10, [0.001, 0.002], "key"),
        ]

        schema = TableSchema(
            data_dimensions=dimensions,
            value_columns=["rate"],
            format="curve",
        )

        config = schema.suggest_table_config()

        assert "gs.Table(" in config
        assert "curve table" in config
        assert "'age': gs.DataDimension('age')" in config
        assert 'value="rate"' in config
        # Should not include the value column in dimensions
        assert "'rate': gs.DataDimension('rate')" not in config

    def test_wide_table_config_generation(self):
        """Test code generation for wide tables"""
        dimensions = [
            DimensionInfo("age", "Int64", 10, [30, 31], "key"),
            DimensionInfo("1", "Float64", 10, [0.001, 0.002], "melt"),
            DimensionInfo("2", "Float64", 10, [0.002, 0.003], "melt"),
        ]

        schema = TableSchema(
            data_dimensions=dimensions,
            value_columns=["value"],
            format="wide",
            overflow_candidate="Ultimate",
        )

        config = schema.suggest_table_config()

        assert "gs.Table(" in config
        assert "wide table" in config
        assert "'age': gs.DataDimension('age')" in config
        # The strategy inside the MeltDimension it extends: once it sat in
        # the dimensions dict, and the snippet was not Python.
        assert "gs.MeltDimension(['1', '2'], overflow=gs.ExtendOverflow(" in config
        compile(config, "suggested", "exec")
        assert "gs.ExtendOverflow('Ultimate'" in config

    def test_the_suggested_snippets_carry_no_trailing_whitespace(self):
        """Both snippets are code a reader copies out, byte for byte.

        The wide snippet's ``source=`` line once ended in two spaces its
        curve twin does not have, which an editor or a linter then flags in
        the reader's own file.
        """
        dimensions = [
            DimensionInfo("age", "Int64", 10, [30, 31], "key"),
            DimensionInfo("1", "Float64", 10, [0.001, 0.002], "melt"),
        ]
        for table_format in ("curve", "wide"):
            schema = TableSchema(
                data_dimensions=dimensions,
                value_columns=["value"],
                format=table_format,
            )

            config = schema.suggest_table_config()

            assert [line for line in config.splitlines() if line != line.rstrip()] == []

    def test_a_schema_with_no_value_column_names_none(self):
        """A curve snippet with nothing to name says so instead of guessing.

        The fallback used to be the literal ``rate``, so an analysis that
        found no value column at all -- a frame with no columns is the
        plainest way there -- offered code naming a column the source may
        never have carried. `gspio describe` reaches a different snippet for
        an empty file, so this is the analysis API's own answer.
        """
        schema = analyze_table(pl.DataFrame())

        config = schema.suggest_table_config()

        assert schema.value_columns == []
        assert 'value="rate"' not in config
        assert "no value column found" in config

    def test_a_wide_schema_with_no_value_column_names_none_either(self):
        """The wide branch carries the same fallback, and the same answer."""
        schema = TableSchema(
            data_dimensions=[DimensionInfo("age", "Int64", 10, [30, 31], "key")],
            value_columns=[],
            format="wide",
        )

        config = schema.suggest_table_config()

        assert 'value="rate"' not in config
        assert "no value column found" in config

    def test_to_dict_serialization(self):
        """Test dictionary serialization"""
        dimensions = [
            DimensionInfo("age", "Int64", 10, [30, 31], "key", "30-39"),
        ]

        hint = InterpolationHint("age", [30, 32], [31], "linear")

        schema = TableSchema(
            data_dimensions=dimensions,
            value_columns=["rate"],
            format="curve",
            overflow_candidate=None,
            interpolation_opportunities=[hint],
            row_count=100,
        )

        result = schema.to_dict()

        assert result["format"] == "curve"
        assert result["row_count"] == 100
        assert len(result["data_dimensions"]) == 1
        assert result["data_dimensions"][0]["name"] == "age"
        assert result["data_dimensions"][0]["numeric_pattern"] == "30-39"
        assert len(result["interpolation_opportunities"]) == 1
        assert result["interpolation_opportunities"][0]["dimension"] == "age"


class TestAnalyzeTable:
    """Test the main analyze_table function"""

    def test_curve_table_analysis(self):
        """Test analysis of a simple curve table"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32, 33, 34],
                "rate": [0.001, 0.002, 0.003, 0.004, 0.005],
            },
        )

        schema = analyze_table(df)

        assert schema.format == "curve"
        assert schema.row_count == 5
        assert len(schema.data_dimensions) == 2
        assert schema.value_columns == ["rate"]

        # Check dimension analysis
        age_dim = next(d for d in schema.data_dimensions if d.name == "age")
        assert age_dim.suggested_type == "key"
        assert age_dim.unique_count == 5

        rate_dim = next(d for d in schema.data_dimensions if d.name == "rate")
        # Rate column should be detected as value column in curve table
        assert rate_dim.suggested_type == "value"

    def test_wide_table_analysis(self):
        """Test analysis of a wide table"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "1": [0.001, 0.002, 0.003],
                "2": [0.002, 0.003, 0.004],
                "3": [0.003, 0.004, 0.005],
                "Ultimate": [0.004, 0.005, 0.006],
            },
        )

        schema = analyze_table(df, detect_overflow=True)

        assert schema.format == "wide"
        assert schema.row_count == 3
        assert len(schema.data_dimensions) == 5
        assert schema.value_columns == [
            "value",
        ]  # Wide tables use "value" after melting

        # Check overflow detection
        assert schema.overflow_candidate == "Ultimate"

        # Check dimension analysis
        age_dim = next(d for d in schema.data_dimensions if d.name == "age")
        assert age_dim.suggested_type == "key"

        # Duration columns should be marked as melt type
        duration_dims = [
            d for d in schema.data_dimensions if d.name in ["1", "2", "3", "Ultimate"]
        ]
        for dim in duration_dims:
            assert dim.suggested_type == "melt"

    def test_overflow_detection_disabled(self):
        """Test that overflow detection can be disabled"""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.001, 0.002],
                "Ultimate": [0.004, 0.005],
            },
        )

        schema = analyze_table(df, detect_overflow=False)

        assert schema.overflow_candidate is None

    def test_interpolation_detection(self):
        """Test interpolation opportunity detection"""
        df = pl.DataFrame(
            {
                "age": [30, 32, 35, 40],  # Gaps at 31, 33, 34, 36-39
                "rate": [0.001, 0.002, 0.003, 0.004],
            },
        )

        schema = analyze_table(df, detect_interpolation=True)

        # Should detect interpolation opportunities
        assert len(schema.interpolation_opportunities) > 0

        age_hint = next(
            (h for h in schema.interpolation_opportunities if h.dimension == "age"),
            None,
        )
        if age_hint:
            assert age_hint.suggested_method in ["linear", "log-linear", "cubic"]

    def test_interpolation_detection_disabled(self):
        """Test that interpolation detection can be disabled"""
        df = pl.DataFrame(
            {
                "age": [30, 32, 35],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        schema = analyze_table(df, detect_interpolation=False)

        assert len(schema.interpolation_opportunities) == 0

    def test_sampling_for_large_data(self):
        """A sample is taken when asked for, and the result says it was.

        ``row_count`` names the SOURCE, not the sample: it used to carry the
        sampled height, which is how a payload came to report a 10,000-row
        file's true row count beside a 1,000-row sample's distinct counts.
        ``sampled_rows`` is where the sample's size lives now.
        """
        # Create large dataset
        large_df = pl.DataFrame(
            {
                "age": list(range(30, 2030)),  # 2000 rows
                "rate": [0.001 + i * 0.0001 for i in range(2000)],
            },
        )

        schema = analyze_table(large_df, sample_rows=100)

        # Should still analyze correctly despite sampling
        assert schema.format == "curve"
        assert schema.row_count == 2000  # The source's own height
        assert schema.sampled_rows == 100  # What the facts were measured on
        assert schema.data_dimensions[0].unique_count == 100
        assert len(schema.data_dimensions) == 2

    def test_nothing_inside_the_budget_is_sampled(self):
        """Under the scan's cell budget the default reads whole, and says so.

        4,000 cells against a budget of five million: `sampled_rows is None`
        is the result asserting that every count below it is the source's own.
        """
        large_df = pl.DataFrame(
            {
                "age": list(range(30, 2030)),  # 2000 rows
                "rate": [0.001 + i * 0.0001 for i in range(2000)],
            },
        )

        schema = analyze_table(large_df)

        assert schema.row_count == 2000
        assert schema.sampled_rows is None
        assert schema.data_dimensions[0].unique_count == 2000

    def test_mixed_data_types(self):
        """Test analysis with mixed data types"""
        df = pl.DataFrame(
            {
                "product": ["Term", "WL", "UL"],
                "sex": ["M", "F", "M"],
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        schema = analyze_table(df)

        assert schema.format == "curve"
        assert len(schema.data_dimensions) == 4

        # Check that string columns are detected as keys
        product_dim = next(d for d in schema.data_dimensions if d.name == "product")
        assert product_dim.suggested_type == "key"
        assert "String" in product_dim.dtype

        sex_dim = next(d for d in schema.data_dimensions if d.name == "sex")
        assert sex_dim.suggested_type == "key"


class TestUtilityFunctions:
    """Test utility functions"""

    def test_is_likely_id_column(self):
        """Test ID column detection"""
        assert _is_likely_id_column("age") == True
        assert _is_likely_id_column("Age") == True
        assert _is_likely_id_column("duration") == True
        assert _is_likely_id_column("product_code") == True
        assert _is_likely_id_column("rate") == False
        assert _is_likely_id_column("value") == False
        assert _is_likely_id_column("qx") == False

    def test_analyze_numeric_pattern(self):
        """Test numeric pattern analysis"""
        # Sequential pattern
        sequential = pl.Series([1, 2, 3, 4, 5])
        pattern = _analyze_numeric_pattern(sequential)
        assert pattern == "1-5"

        # Continuous data
        continuous = pl.Series([1.1, 1.15, 1.2, 1.8, 2.3])
        pattern = _analyze_numeric_pattern(continuous)
        assert pattern == "continuous"

        # Empty series
        empty = pl.Series([], dtype=pl.Int64)
        pattern = _analyze_numeric_pattern(empty)
        assert pattern is None

    def test_a_column_the_helpers_cannot_measure_is_not_reported_as_no_pattern(
        self,
    ):
        """The numeric helpers raise on a column they cannot difference.

        Their callers hand them numeric columns only, so nothing here is
        reachable through analyze_table. A helper that did meet one used to
        answer "no pattern" and "no gaps" in place of the error, which reads
        as a fact about the data rather than as a bug in the caller.
        """
        letters = pl.Series("age", ["a", "b", "d"])

        with pytest.raises(pl.exceptions.InvalidOperationError):
            _analyze_numeric_pattern(letters)
        with pytest.raises(pl.exceptions.InvalidOperationError):
            _detect_interpolation_opportunities(letters)


class TestErrorCases:
    """Test error handling and edge cases"""

    def test_empty_dataframe(self):
        """Test analysis of empty DataFrame"""
        df = pl.DataFrame({"age": [], "rate": []})

        schema = analyze_table(df)

        assert schema.row_count == 0
        assert len(schema.data_dimensions) == 2
        assert schema.format in ["curve", "wide"]  # Should handle gracefully

    def test_single_column_dataframe(self):
        """Test analysis of single column DataFrame"""
        df = pl.DataFrame({"rate": [0.001, 0.002, 0.003]})

        schema = analyze_table(df)

        assert schema.row_count == 3
        assert len(schema.data_dimensions) == 1
        assert schema.format == "curve"
        assert schema.value_columns == ["rate"]

    def test_all_string_columns(self):
        """Test analysis with only string columns"""
        df = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "description": ["Term Life", "Whole Life"],
            },
        )

        schema = analyze_table(df)

        assert schema.row_count == 2
        assert len(schema.data_dimensions) == 2
        # Should default to first column as value
        assert len(schema.value_columns) == 1


class TestSuggestedCodeRuns:
    """The configuration the analysis suggests is Python that reads the table right.

    The wide suggestion once put ``overflow=`` inside the ``dimensions`` dict,
    so it was not Python at all; mended the obvious way, its
    ``ExtendOverflow('Ult.')`` copied each issue-age row's ultimate rate to
    every later year, freezing mortality at one attained age for life -- a
    tenth of the right rate by year 30 of a 3-year select table.
    """

    SELECT_YEARS = 3
    ISSUE_AGES = range(20, 81)

    @staticmethod
    def _ultimate(attained: int) -> float:
        return round(0.0005 * 1.09 ** (attained - 20), 10)

    def _select(self, issue: int, year: int) -> float:
        return round(self._ultimate(issue + year - 1) * (0.5 + 0.15 * year), 10)

    def _run(self, frame: pl.DataFrame, tmp_path) -> tuple[str, dict]:
        path = tmp_path / "table.csv"
        frame.write_csv(path)
        code = analyze_table(frame).suggest_table_config()
        compile(code, "suggested", "exec")  # valid Python, as printed
        namespace: dict = {}
        exec(  # noqa: S102 -- running the suggestion is the test
            compile(
                code.replace('"path/to/your/data.csv"', repr(str(path))), "s", "exec"
            ),
            namespace,
        )
        return code, namespace

    def test_select_and_ultimate_rates_follow_the_attained_age(self, tmp_path):
        from gaspatchio import ActuarialFrame

        n = self.SELECT_YEARS
        frame = pl.DataFrame(
            {
                "Issue Age": list(self.ISSUE_AGES),
                **{
                    str(year): [self._select(x, year) for x in self.ISSUE_AGES]
                    for year in range(1, n + 1)
                },
                "Ult.": [self._ultimate(x + n) for x in self.ISSUE_AGES],
            }
        )
        code, namespace = self._run(frame, tmp_path)
        years = [1, 3, 4, 5, 10, 30]
        af = ActuarialFrame(pl.DataFrame({"issue": [40] * 6, "year": years}))
        af.q = namespace["table"].lookup(**{"Issue Age": af.issue, "duration": af.year})

        got = af.collect()["q"].to_list()

        want = [
            self._select(40, d) if d <= n else self._ultimate(40 + d - 1) for d in years
        ]
        assert got == pytest.approx(want, rel=1e-12)
        assert "ExtendOverflow" not in code
        assert "select and ultimate" in code

    def test_a_year_past_the_last_ultimate_row_is_a_miss(self, tmp_path):
        from gaspatchio import ActuarialFrame

        frame = pl.DataFrame(
            {"Issue Age": [40, 41, 42], "1": [0.1, 0.2, 0.3], "Ult.": [0.4, 0.5, 0.6]}
        )
        _, namespace = self._run(frame, tmp_path)
        af = ActuarialFrame(pl.DataFrame({"issue": [40], "year": [5]}))
        af.q = namespace["table"].lookup(**{"Issue Age": af.issue, "duration": af.year})

        with pytest.raises(Exception, match="missing keys"):
            af.collect()

    def test_an_attained_age_table_extends_its_own_row_and_is_valid_python(
        self, tmp_path
    ):
        from gaspatchio import ActuarialFrame

        frame = pl.DataFrame(
            {
                "Attained Age": [40, 41],
                "1": [0.1, 0.2],
                "2": [0.3, 0.4],
                "Ult.": [0.5, 0.6],
            }
        )
        code, namespace = self._run(frame, tmp_path)
        af = ActuarialFrame(pl.DataFrame({"a": [41], "d": [7]}))
        af.q = namespace["table"].lookup(**{"Attained Age": af.a, "duration": af.d})

        assert "overflow=gs.ExtendOverflow('Ult.', to_value=200))" in code
        assert af.collect()["q"].to_list() == [0.6]

    def test_a_bare_age_says_it_is_read_as_the_issue_age(self, tmp_path):
        frame = pl.DataFrame(
            {"Age": [40, 41, 42], "1": [0.1, 0.2, 0.3], "Ult.": [0.4, 0.5, 0.6]}
        )
        code, _ = self._run(frame, tmp_path)

        assert "'Age' is read as the issue age" in code
