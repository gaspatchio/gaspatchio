"""
Tests for enhanced compilation error handling.

Tests the compilation error detection, replay, and formatting functionality
including Pydantic models and multiple output formats.
"""

import json
import os
from unittest.mock import patch

import polars as pl
import pytest

from gaspatchio_core.errors.models import EnhancedError, ErrorType
from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.util import get_error_mode, set_error_mode


class TestCompilationErrorHandling:
    """Test compilation error handling with enhanced context."""
    
    def setup_method(self):
        """Set up test data for each test."""
        self.test_data = pl.DataFrame({
            "policy_id": [1, 2, 3, 4, 5],
            "premium": [100.0, 200.0, 300.0, 400.0, 500.0],
            "sum_assured": [10000.0, 20000.0, 30000.0, 40000.0, 50000.0],
            "age": [25, 35, 45, 55, 65],
            "duration": [1, 2, 3, 4, 5],
        })
        
        # Save current error mode
        self.original_error_mode = get_error_mode()
    
    def teardown_method(self):
        """Reset error mode after each test."""
        set_error_mode(self.original_error_mode)
    
    def test_missing_column_compilation_enhanced(self):
        """Test enhanced compilation error for missing column."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        af._tracing = True  # Enable tracing to capture operations
        
        # Add some valid operations first
        af["ratio"] = pl.col("sum_assured") / pl.col("premium")
        af["age_band"] = (pl.col("age") // 10) * 10
        
        # Add an operation that references a non-existent column
        af["bad_calc"] = pl.col("nonexistent_column") * 2
        
        # This should trigger compilation error
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        # Check that enhanced error attributes are attached
        error = exc_info.value
        assert hasattr(error, 'enhanced_error')
        assert hasattr(error, 'llm_context')
        assert hasattr(error, 'to_json')
        
        # Verify enhanced error structure
        enhanced = error.enhanced_error
        assert isinstance(enhanced, EnhancedError)
        assert enhanced.metadata.error_type == ErrorType.COLUMN_NOT_FOUND
        assert enhanced.metadata.error_category == "compilation"
        
        # Check operation context
        assert enhanced.operation.alias == "bad_calc"
        assert "nonexistent_column" in enhanced.operation.expression
        assert enhanced.operation.index == 2  # Third operation
        
        # Check dataframe context
        # Shape might be (0, 7) if only schema is collected during compilation error
        assert enhanced.dataframe.shape[1] == 7  # Original 5 cols + 2 successful ops
        column_names = [col.name for col in enhanced.dataframe.columns]
        assert "ratio" in column_names
        assert "age_band" in column_names
        
        # Check suggestions
        assert len(enhanced.suggestions) > 0
        # Should suggest checking available columns
        assert any("af.columns" in s.text for s in enhanced.suggestions)
    
    def test_compilation_error_console_output(self):
        """Test console output formatting for compilation errors."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        af._tracing = True
        af["missing"] = pl.col("not_found")
        
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        error = exc_info.value
        
        # Test console output with emoji
        console_output = error.enhanced_error.to_console(use_emoji=True)
        assert "❌" in console_output
        assert "🔍" in console_output
        assert "📊" in console_output
        assert "💡" in console_output
        
        # Test console output without emoji
        plain_output = error.enhanced_error.to_console(use_emoji=False)
        assert "ERROR:" in plain_output
        assert "Failed Operation:" in plain_output
        assert "DataFrame State:" in plain_output
        
    def test_compilation_error_json_output(self):
        """Test JSON output for compilation errors."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        af._tracing = True
        af["calc"] = pl.col("missing_col") + 1
        
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        error = exc_info.value
        
        # Test JSON output
        json_str = error.enhanced_error.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["metadata"]["error_type"] == "column_not_found"
        assert parsed["operation"]["alias"] == "calc"
        assert len(parsed["dataframe"]["columns"]) == 5
        assert "suggestions" in parsed
    
    def test_compilation_error_llm_context(self):
        """Test LLM context generation for compilation errors."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        af._tracing = True
        af["result"] = pl.col("unknown")
        
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        error = exc_info.value
        llm_context = error.enhanced_error.to_llm_context()
        
        # Check flattened structure
        assert llm_context["error_type"] == "column_not_found"
        assert llm_context["error_category"] == "compilation"
        assert "failing_operation" in llm_context
        assert "available_columns" in llm_context
        assert isinstance(llm_context["available_columns"], list)
        assert all("name" in col and "type" in col for col in llm_context["available_columns"])
    
    def test_type_mismatch_compilation_error(self):
        """Test compilation error for type mismatches."""
        set_error_mode("enhanced")
        
        # Create data that will cause a type error
        data = pl.DataFrame({
            "id": [1, 2, 3],
            "text": ["a", "b", "c"],
            "number": [10, 20, 30]
        })
        
        af = ActuarialFrame(data, mode="debug")
        af._tracing = True
        
        # This should cause a type error (can't add string to number)
        af["bad_mix"] = pl.col("text") + pl.col("number")
        
        with pytest.raises(Exception) as exc_info:
            af.collect()
        
        # Check that it's some kind of error
        error_str = str(exc_info.value)
        assert len(error_str) > 0  # Just verify we got an error
    
    def test_compilation_error_fallback(self):
        """Test fallback when enhanced handling fails."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        
        # Force a scenario where enhanced handling might fail
        # by not having TracedOperations in the graph
        af._computation_graph = [("bad", pl.col("missing"))]  # Tuple instead of TracedOperation
        
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        # Should still get basic error handling
        error_str = str(exc_info.value)
        assert "missing" in error_str or "not found" in error_str
    
    def test_compilation_error_basic_mode(self):
        """Test that basic mode doesn't add enhanced context."""
        set_error_mode("basic")
        
        af = ActuarialFrame(self.test_data)
        af["bad"] = pl.col("nonexistent")
        
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        error = exc_info.value
        # Should not have enhanced attributes in basic mode
        assert not hasattr(error, 'enhanced_error')
        assert not hasattr(error, 'to_json')
    
    @patch('gaspatchio_core.errors.formatting_errors._is_interactive_console')
    def test_console_detection(self, mock_console):
        """Test console detection for emoji display."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        af._tracing = True
        af["bad"] = pl.col("missing")
        
        # Test with console detected
        mock_console.return_value = True
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        error_str = str(exc_info.value)
        assert "❌" in error_str  # Should have emoji
        
        # Test without console
        mock_console.return_value = False
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        error_str = str(exc_info.value)
        # Check for plain text markers instead of emoji
        assert "ERROR:" in error_str or "Failed" in error_str
    
    def test_multiple_operations_before_error(self):
        """Test error finding with multiple successful operations before failure."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        af._tracing = True
        
        # Add several successful operations
        af["ratio"] = pl.col("sum_assured") / pl.col("premium")
        af["age_squared"] = pl.col("age") ** 2
        af["premium_pct"] = pl.col("premium") / pl.col("sum_assured") * 100
        af["is_senior"] = pl.col("age") >= 60
        
        # Then add failing operation
        af["bad_calc"] = pl.col("missing_column") * pl.col("ratio")
        
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        enhanced = exc_info.value.enhanced_error
        
        # Should identify the correct failing operation
        assert enhanced.operation.alias == "bad_calc"
        assert enhanced.operation.index == 4  # Fifth operation (0-indexed)
        
        # DataFrame context should include all successful operations
        column_names = [col.name for col in enhanced.dataframe.columns]
        assert "ratio" in column_names
        assert "age_squared" in column_names
        assert "premium_pct" in column_names
        assert "is_senior" in column_names
    
    def test_similar_column_suggestions(self):
        """Test that similar column names are suggested."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(self.test_data, mode="debug")
        af._tracing = True
        
        # Typo in column name
        af["calc"] = pl.col("permium") * 2  # Should be "premium"
        
        with pytest.raises(pl.ColumnNotFoundError) as exc_info:
            af.collect()
        
        enhanced = exc_info.value.enhanced_error
        
        # Should suggest "premium" as similar column
        suggestions_text = [s.text for s in enhanced.suggestions]
        assert any("premium" in text for text in suggestions_text)
        
        # Check code example in suggestion
        code_examples = [s.code_example for s in enhanced.suggestions if s.code_example]
        assert any("pl.col('premium')" in ex for ex in code_examples)


class TestCompilationErrorEdgeCases:
    """Test edge cases and error recovery."""
    
    def test_empty_dataframe(self):
        """Test compilation error with empty DataFrame."""
        set_error_mode("enhanced")
        
        empty_df = pl.DataFrame()
        af = ActuarialFrame(empty_df, mode="debug")
        af["bad"] = pl.col("missing")
        
        with pytest.raises(Exception):  # Could be various error types
            af.collect()
    
    def test_very_long_expression(self):
        """Test error formatting with very long expressions."""
        set_error_mode("enhanced")
        
        af = ActuarialFrame(pl.DataFrame({"a": [1, 2, 3]}), mode="debug")
        
        # Create a very long expression
        long_expr = pl.col("missing")
        for i in range(20):
            long_expr = long_expr + pl.col("missing") * i
        
        af["long"] = long_expr
        
        with pytest.raises(Exception) as exc_info:
            af.collect()
        
        if hasattr(exc_info.value, 'enhanced_error'):
            console_output = exc_info.value.enhanced_error.to_console()
            # Should truncate long expressions
            assert "..." in console_output