# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the ErrorSuggestionEngine.

The engine chooses an advice family from the exception's class, the op-tree
the failing column was written as, and the operand dtypes the calculation
graph holds -- so every stimulus below is one of those three, never a
sentence written to contain a trigger word. ``tests/errors/
test_advice_is_routed_on_facts.py`` drives the same router from real
failures; this file exercises it directly, family by family.
"""

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import BinOp, Call, Col
from gaspatchio.assumptions import Table
from gaspatchio.errors.boundary import search_collect_failure
from gaspatchio.errors.formatter import GraphFacts, Operand
from gaspatchio.errors.suggestions import ErrorSuggestionEngine
from gaspatchio.frame.calculations import CalculationRecord, SourceSpan


def _reading(*pairs: tuple[str, str]) -> GraphFacts:
    """Build the graph's answer: what the failing formula read, and its dtypes."""
    return GraphFacts(
        blocks=(),
        reading=tuple(
            Operand(node=name, column=name, dtype=dtype) for name, dtype in pairs
        ),
    )


class TestErrorSuggestionEngine:
    """Test the ErrorSuggestionEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ErrorSuggestionEngine()
        self.source = SourceSpan(
            file="test_model.py",
            line=42,
            end_line=42,
            function="build_projection",
            statement='af["result"] = af["premium"] * 12',
            rhs='af["premium"] * 12',
            target_literal=True,
        )
        self.available_columns = [
            "policy_id",
            "premium",
            "claims",
            "age",
            "assumption_mortality",
            "assumption_lapse",
            "calc_present_value",
            "date_issued",
        ]

    def _create_operation(self, column: str = "annual_premium") -> CalculationRecord:
        """Helper to create a recorded calculation for testing."""
        return CalculationRecord(
            column=column,
            ordinal=1,
            operation_id=0,
            node=BinOp("mul", Col("premium"), Col("twelve")),
            expr=pl.col("premium") * 12,
            dtype=None,
            source=self.source,
            origin="assignment",
        )

    def test_column_not_found_typo_suggestions(self):
        """Test suggestions for column not found with typos."""
        # Test common actuarial typo
        error = pl.exceptions.ColumnNotFoundError("column 'premiun' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert len(suggestions) >= 1
        assert "Did you mean 'premium'? (common actuarial typo)" in suggestions

    def test_column_not_found_similar_name(self):
        """Test suggestions for column not found with similar names."""
        error = pl.exceptions.ColumnNotFoundError("column 'premiums' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should find 'premium' as similar
        assert any("Did you mean 'premium'?" in s for s in suggestions)

    def test_column_not_found_case_sensitivity(self):
        """Test suggestions handle case sensitivity."""
        error = pl.exceptions.ColumnNotFoundError("column 'PREMIUM' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should find 'premium' despite case difference
        assert any("premium" in s.lower() for s in suggestions)

    def test_column_not_found_multiple_similar(self):
        """Test suggestions when multiple similar columns exist."""
        columns_with_similar = self.available_columns + [
            "premium_annual",
            "premium_monthly",
        ]
        error = pl.exceptions.ColumnNotFoundError("column 'premiumz' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(error, operation, columns_with_similar)

        # Should suggest best match and mention others
        assert len(suggestions) >= 2
        assert any("Did you mean" in s for s in suggestions)
        assert any("Other similar columns" in s for s in suggestions)

    def test_column_not_found_id_pattern(self):
        """Test suggestions for missing ID columns."""
        error = pl.exceptions.ColumnNotFoundError("column 'customer_id' does not exist")
        operation = self._create_operation()

        # Use columns without any ID columns
        columns_without_ids = ["premium", "claims", "age", "assumption_mortality"]

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            columns_without_ids,
        )

        # Should suggest joining additional data since no ID columns exist
        assert any("join additional data" in s for s in suggestions)

    def test_column_not_found_calc_pattern(self):
        """Test suggestions for missing calculated columns."""
        error = pl.exceptions.ColumnNotFoundError(
            "column 'calc_something' does not exist",
        )
        operation = self._create_operation()

        # Use columns without any calc columns
        columns_without_calcs = ["premium", "claims", "age", "assumption_mortality"]

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            columns_without_calcs,
        )

        # Should suggest ensuring calculations are defined
        assert any("calculations are defined" in s for s in suggestions)

    def test_a_class_only_column_refusal_is_still_the_column_family(self):
        """The class routes; only the NAME is still read off the refusal."""
        error = pl.exceptions.ColumnNotFoundError("nothing quotable here")
        operation = self._create_operation()

        assert self.engine.suggest_fixes(error, operation, ["premium"]) == []

    def test_type_mismatch_general(self):
        """A dtype refusal earns the type family whatever the graph could say."""
        error = pl.exceptions.InvalidOperationError("the operation was refused")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert "Ensure all expressions have consistent types" in suggestions
        assert "Consider using .cast() to explicitly set types" in suggestions

    def test_type_mismatch_string_numeric(self):
        """A `str` operand beside an `f64` one earns the cast-to-number advice."""
        error = pl.exceptions.InvalidOperationError("the operation was refused")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("product_code", "str"), ("premium", "f64")),
        )

        assert any(
            "cast(pl.Float64)" in s or "cast(pl.Int64)" in s for s in suggestions
        )

    def test_type_mismatch_float_int(self):
        """Both numeric names on the graph earn the widening advice."""
        error = pl.exceptions.InvalidOperationError("the operation was refused")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("term", "i64"), ("premium", "f64")),
        )

        assert any("Mix of integers and floats" in s for s in suggestions)

    def test_type_mismatch_boolean(self):
        """A `bool` operand earns the condition advice."""
        error = pl.exceptions.InvalidOperationError("the operation was refused")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("in_force", "bool"), ("premium", "f64")),
        )

        assert any("True/False" in s for s in suggestions)

    def test_type_mismatch_datetime(self):
        """A `date` operand earns the date-type advice -- because it IS a date."""
        error = pl.exceptions.InvalidOperationError("the operation was refused")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("issued", "date"), ("premium", "f64")),
        )

        assert any(
            "str.to_datetime()" in s or "cast(pl.Date)" in s for s in suggestions
        )

    def test_a_column_named_like_a_date_that_holds_a_number_is_a_number(self):
        """The dtype decides, not the name -- this is the routing this replaced."""
        error = pl.exceptions.InvalidOperationError("the operation was refused")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("product_code", "str"), ("valuation_date", "f64")),
        )

        assert not any("cast(pl.Date)" in s for s in suggestions), suggestions
        assert any("cast(pl.Float64)" in s for s in suggestions), suggestions

    def test_a_dtype_the_graph_never_resolved_refines_nothing(self):
        """`unknown` is the graph's silence, and silence chooses no refinement."""
        error = pl.exceptions.InvalidOperationError("the operation was refused")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("a", "unknown"), ("b", "unknown")),
        )

        assert suggestions == [
            "Ensure all expressions have consistent types",
            "Consider using .cast() to explicitly set types",
        ]

    def test_a_schema_error_is_answered_about_the_declared_type(self):
        """A `SchemaError` here is a type a value contradicts, not a join.

        The four lines this replaced were about joins: check the join
        keys, cast before joining, verify the names, select fewer
        columns. This router answers one shape -- a column assignment
        that failed at collect -- and a column assignment does not join.
        The one calculation in this framework's vocabulary that does is a
        ``Table.lookup``, and that is answered by identity before any
        class is asked, so the join lines named an operation the failing
        calculation could not contain.
        """
        error = pl.exceptions.SchemaError("schemas do not match")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("declared to produce" in line for line in suggestions), suggestions
        assert not any("join" in line for line in suggestions), suggestions

    def test_a_map_elements_dtype_mismatch_is_told_about_return_dtype(self):
        """The shape that used to be told to check its join keys.

        ``map_elements(..., return_dtype=pl.Float64)`` whose body returns
        a string raises a ``SchemaError`` in a model with no join
        anywhere. Raised through the public API rather than constructed,
        so the class, the record and the graph are the ones a run
        produces.
        """
        af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "n": [1.0, 2.0]}))
        af.wrong = af.n.map_elements(lambda _v: "not a float", return_dtype=pl.Float64)
        with pytest.raises(pl.exceptions.SchemaError) as caught:
            af.collect()
        record, last_good = search_collect_failure(af, caught.value)
        assert isinstance(record, CalculationRecord), record
        assert last_good is not None

        suggestions = self.engine.suggest_fixes(
            caught.value,
            record,
            list(last_good.columns),
        )

        assert any("`return_dtype=`" in line for line in suggestions), suggestions
        assert not any("join" in line for line in suggestions), suggestions

    def test_list_length_suggestions_need_a_list_operand(self):
        """A `ShapeError` over list operands is the jagged family."""
        error = pl.exceptions.ShapeError("list lengths differed at index 0: 2 != 3")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("per_policy", "list[f64]"), ("curve", "list[f64]")),
        )

        assert any("List lengths differ across rows" in s for s in suggestions)

    def test_a_shape_error_over_scalars_is_not_the_jagged_family(self):
        """A height clash is not a jagged-list clash, and is not answered as one."""
        error = pl.exceptions.ShapeError("unable to add a column of length 3")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
            _reading(("premium", "f64"), ("term", "i64")),
        )

        assert suggestions == []

    def test_assumption_lookup_suggestions(self):
        """A lookup lowering IS an assumption read, and names its own table."""
        error = pl.exceptions.ComputeError("the plugin failed with message: ...")
        operation = CalculationRecord(
            column="mortality_rate",
            ordinal=1,
            operation_id=0,
            node=Call(
                "lookup",
                (Col("attained_age"),),
                (("table", "mortality"), ("on_missing", "raise")),
            ),
            expr=pl.col("attained_age"),
            dtype=None,
            source=self.source,
            origin="assignment",
        )

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("assumption key matches exactly" in s for s in suggestions)
        assert any("assumption table is loaded" in s for s in suggestions)
        assert any("'mortality'" in s for s in suggestions)

    def test_a_lookup_under_arithmetic_is_still_a_lookup(self):
        """`table.lookup(...) * 12` is a lookup with a multiply on top of it."""
        error = pl.exceptions.ComputeError("the plugin failed with message: ...")
        operation = CalculationRecord(
            column="monthly_rate",
            ordinal=1,
            operation_id=0,
            node=BinOp(
                "mul",
                Call("lookup", (Col("attained_age"),), (("table", "lapse"),)),
                Col("factor"),
            ),
            expr=pl.col("attained_age"),
            dtype=None,
            source=self.source,
            origin="assignment",
        )

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("'lapse'" in s for s in suggestions), suggestions

    def test_extract_column_name_single_quotes(self):
        """Test extracting column names from error messages with single quotes."""
        error_msg = "column 'nonexistent_col' does not exist"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "nonexistent_col"

    def test_extract_column_name_double_quotes(self):
        """Test extracting column names from error messages with double quotes."""
        error_msg = 'column "nonexistent_col" not found'
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "nonexistent_col"

    def test_extract_column_name_no_quotes(self):
        """Test extracting column names without quotes."""
        error_msg = "column premium_amount does not exist"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "premium_amount"

    def test_extract_column_name_key_error(self):
        """Test extracting column names from key errors."""
        error_msg = "key 'missing_key' not found"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "missing_key"

    def test_extract_column_name_not_found(self):
        """Test extraction when no column name is present."""
        error_msg = "some generic error message"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name is None

    def test_find_similar_columns_exact_match(self):
        """Test finding exact column matches."""
        similar = self.engine._find_similar_columns("premium", self.available_columns)
        assert "premium" in similar

    def test_find_similar_columns_case_insensitive(self):
        """Test case insensitive column matching."""
        similar = self.engine._find_similar_columns("PREMIUM", self.available_columns)
        assert "premium" in similar

    def test_find_similar_columns_substring(self):
        """Test substring matching in column names."""
        similar = self.engine._find_similar_columns("prem", self.available_columns)
        assert "premium" in similar

    def test_find_similar_columns_edit_distance(self):
        """Test edit distance matching."""
        similar = self.engine._find_similar_columns("premiums", self.available_columns)
        assert "premium" in similar

    def test_find_similar_columns_threshold(self):
        """Test similarity threshold filtering."""
        # Very different name should not match
        similar = self.engine._find_similar_columns("xyz", self.available_columns)
        assert len(similar) == 0

    def test_find_similar_columns_empty_list(self):
        """Test with empty available columns list."""
        similar = self.engine._find_similar_columns("premium", [])
        assert similar == []

    def test_find_similar_columns_prefix_boost(self):
        """Test prefix matching boost."""
        columns = ["premium_annual", "premium_monthly", "claims_total"]
        similar = self.engine._find_similar_columns("prem", columns)
        assert "premium_annual" in similar
        assert "premium_monthly" in similar

    def test_actuarial_typos_comprehensive(self):
        """Test all defined actuarial typos."""
        for typo, correct in self.engine.ACTUARIAL_TYPOS.items():
            error_msg = f"column '{typo}' does not exist"
            extracted = self.engine._extract_column_name(error_msg)
            assert extracted == typo

            # If the correct column is available, should suggest it
            if correct in self.available_columns:
                error = pl.exceptions.ColumnNotFoundError(error_msg)
                operation = self._create_operation()
                suggestions = self.engine.suggest_fixes(
                    error,
                    operation,
                    self.available_columns,
                )
                assert any(f"Did you mean '{correct}'?" in s for s in suggestions)

    def test_no_suggestions_for_unknown_error(self):
        """A class no family claims earns nothing, however it is worded."""
        error = Exception("completely unknown error type")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should return empty list for unknown error types
        assert suggestions == []

    def test_case_insensitive_name_extraction(self):
        """The residue that still reads a string reads it case-insensitively."""
        error = pl.exceptions.ColumnNotFoundError("COLUMN 'PREMIUN' NOT FOUND")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert len(suggestions) > 0
        assert any("premium" in s.lower() for s in suggestions)

    def test_suggestion_engine_with_no_available_columns(self):
        """Test suggestion engine with empty available columns list."""
        error = pl.exceptions.ColumnNotFoundError("column 'test' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(error, operation, [])

        # Should not crash, may return empty or generic suggestions
        assert isinstance(suggestions, list)


class TestLiveRefusalRouting:
    """The advice printed under a real lookup refusal, chosen by its record.

    The wording of this message is written in another repository
    (``core/src/assumptions/miss_message.rs``), and for as long as the
    advice beneath them was picked by testing lowercased substrings of the
    message, one ordinary English word could re-route it: "the engine hands
    this lookup one batch of rows at a time" answered a missing attained
    age with "Check date format matches your data".

    It cannot now. The refusal below is raised for real, the record the
    replay attributes is the one the panel path holds, and the family is
    chosen by that record's own lowering -- ``Call("lookup")`` IS an
    assumption-table read whatever the sentence says. These stay green
    however the Rust builders are reworded, which is what they are for.
    """

    DATE_ADVICE = "Check date format matches your data"
    NULL_ADVICE = "Handle null values with"

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ErrorSuggestionEngine()

    def _advice(self, af: ActuarialFrame, raised: Exception) -> list[str]:
        """Return the advice the router prints under a real refusal."""
        record, last_good = search_collect_failure(af, raised)
        assert isinstance(record, CalculationRecord), record
        columns = [] if last_good is None else list(last_good.columns)
        return self.engine.suggest_fixes(raised, record, columns)

    @staticmethod
    def _missing_key_refusal() -> tuple[ActuarialFrame, Exception]:
        """Raise a real lookup miss -- a life at 99, a table stopping at 42."""
        table = Table(
            name="suggestion_routing_missing_key",
            source=pl.DataFrame(
                {"age": [40, 41, 42], "rate": [0.001, 0.0011, 0.0012]},
            ),
            dimensions={"age": "age"},
            value="rate",
        )
        af = ActuarialFrame(
            pl.DataFrame({"policy_id": [1, 2, 3], "attained_age": [40, 41, 99]}),
        )
        af.mortality_rate = table.lookup(age=af.attained_age)

        with pytest.raises(pl.exceptions.ComputeError) as caught:
            af.collect()
        return af, caught.value

    def test_a_lookup_miss_reaches_the_assumption_advice(self):
        """The keys are missing from a table, so the advice must be about it."""
        advice = self._advice(*self._missing_key_refusal())

        assert any("assumption key matches exactly" in line for line in advice), advice
        assert any("suggestion_routing_missing_key" in line for line in advice), advice

    def test_a_lookup_miss_is_never_answered_with_date_advice(self):
        """An actuary whose table stops at 45 is not told to check her dates."""
        advice = self._advice(*self._missing_key_refusal())

        assert not any(self.DATE_ADVICE in line for line in advice), advice
        assert not any("to_datetime" in line for line in advice), advice
        assert not any(self.NULL_ADVICE in line for line in advice), advice
