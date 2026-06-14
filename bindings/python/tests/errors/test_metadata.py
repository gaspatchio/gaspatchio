# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the metadata capture functionality.

Tests cover source capture from different contexts, nested functions,
lambda expressions, and edge cases.
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from gaspatchio_core.errors.metadata import (
    OperationMetadata,
    TracedOperation,
    _get_source_line_safe,
    capture_source_context,
)


class TestOperationMetadata:
    """Test OperationMetadata dataclass and its properties."""

    def test_basic_metadata_creation(self):
        """Test basic OperationMetadata creation."""
        metadata = OperationMetadata(
            file_name="test.py",
            line_number=42,
            source_line="x = y + z",
            function_name="test_func",
        )

        assert metadata.file_name == "test.py"
        assert metadata.line_number == 42
        assert metadata.source_line == "x = y + z"
        assert metadata.function_name == "test_func"
        assert metadata.timestamp is None

    def test_is_jupyter_property(self):
        """Test detection of Jupyter notebook context."""
        # Regular file
        metadata = OperationMetadata(
            file_name="/path/to/test.py",
            line_number=1,
            source_line="test",
        )
        assert not metadata.is_jupyter

        # Jupyter notebook input
        jupyter_metadata = OperationMetadata(
            file_name="<ipython-input-1-abc123>",
            line_number=1,
            source_line="test",
        )
        assert jupyter_metadata.is_jupyter

        # Alternative Jupyter format
        jupyter_metadata2 = OperationMetadata(
            file_name="ipython-input-5-def456",
            line_number=1,
            source_line="test",
        )
        assert jupyter_metadata2.is_jupyter

    def test_display_filename_property(self):
        """Test human-readable filename display."""
        # Regular file
        metadata = OperationMetadata(
            file_name="/path/to/script.py",
            line_number=1,
            source_line="test",
        )
        assert metadata.display_filename == "/path/to/script.py"

        # Jupyter notebook with cell number
        jupyter_metadata = OperationMetadata(
            file_name="<ipython-input-3-abc123>",
            line_number=1,
            source_line="test",
        )
        assert jupyter_metadata.display_filename == "Jupyter Cell 3"

        # Malformed Jupyter filename
        jupyter_metadata_bad = OperationMetadata(
            file_name="<ipython-input-malformed",
            line_number=1,
            source_line="test",
        )
        assert jupyter_metadata_bad.display_filename == "Jupyter Notebook"


class TestTracedOperation:
    """Test TracedOperation dataclass."""

    def test_traced_operation_creation(self):
        """Test TracedOperation creation with metadata."""
        metadata = OperationMetadata(
            file_name="test.py",
            line_number=10,
            source_line="af['result'] = af['x'] + af['y']",
            function_name="calculate",
        )

        # Mock expression (would be pl.Expr in real usage)
        mock_expr = "mock_polars_expression"

        operation = TracedOperation(
            alias="result",
            expression=mock_expr,
            metadata=metadata,
        )

        assert operation.alias == "result"
        assert operation.expression == mock_expr
        assert operation.metadata == metadata
        assert operation.metadata.line_number == 10


class TestCaptureSourceContext:
    """Test source context capture functionality."""

    def test_capture_basic_context(self):
        """Test basic source context capture."""

        def test_function():
            return capture_source_context(depth=1)

        metadata = test_function()

        assert metadata.file_name.endswith("test_metadata.py")
        assert metadata.function_name == "test_function"
        assert metadata.line_number > 0
        assert "return capture_source_context" in metadata.source_line

    def test_capture_with_depth(self):
        """Test source capture with different stack depths."""

        def inner_function():
            return capture_source_context(depth=2)  # Skip inner_function frame

        def outer_function():
            return inner_function()

        metadata = outer_function()

        assert metadata.function_name == "outer_function"
        assert "return inner_function()" in metadata.source_line

    def test_capture_nested_functions(self):
        """Test source capture with nested function calls."""

        def level_three():
            return capture_source_context(depth=1)

        def level_two():
            return level_three()

        def level_one():
            return level_two()

        metadata = level_one()

        # Should capture level_three function context
        assert metadata.function_name == "level_three"

    def test_capture_with_lambda(self):
        """Test source capture from lambda expressions."""
        # Lambda that calls capture_source_context
        lambda_func = lambda: capture_source_context(depth=1)

        metadata = lambda_func()

        assert metadata.function_name == "<lambda>"
        assert "lambda_func = lambda:" in metadata.source_line

    def test_capture_with_timestamp(self):
        """Test source capture with timestamp enabled."""
        start_time = time.time()
        metadata = capture_source_context(include_timestamp=True)
        end_time = time.time()

        assert metadata.timestamp is not None
        assert start_time <= metadata.timestamp <= end_time

    def test_capture_without_timestamp(self):
        """Test source capture without timestamp (default)."""
        metadata = capture_source_context()
        assert metadata.timestamp is None

    def test_capture_at_stack_limit(self):
        """Test behavior when requested depth exceeds stack depth."""
        # Request depth that exceeds current stack
        metadata = capture_source_context(depth=100)

        # Should not crash and should return some valid metadata
        assert metadata.file_name is not None
        assert metadata.line_number > 0

    def test_capture_from_temporary_file(self):
        """Test source capture from a temporary file."""
        # Create a temporary file with known content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def temp_function():\n")
            f.write(
                "    from gaspatchio_core.errors.metadata import capture_source_context\n",
            )
            f.write("    return capture_source_context(depth=1)\n")
            temp_path = f.name

        try:
            # Execute the temporary file
            with open(temp_path) as f:
                code = compile(f.read(), temp_path, "exec")
                namespace = {}
                exec(code, namespace)

                metadata = namespace["temp_function"]()

                assert metadata.file_name == temp_path
                assert metadata.function_name == "temp_function"
                assert "return capture_source_context" in metadata.source_line
        finally:
            Path(temp_path).unlink()


class TestGetSourceLineSafe:
    """Test the safe source line retrieval function."""

    def test_get_existing_source_line(self):
        """Test getting source line from existing file."""
        # Get source from this test file
        current_file = __file__
        line_number = 1  # First line should exist

        source_line = _get_source_line_safe(current_file, line_number)

        # Should get actual source content (first line is likely a docstring or comment)
        assert source_line != "<source unavailable>"
        assert len(source_line) > 0

    def test_get_nonexistent_file(self):
        """Test handling of non-existent file."""
        source_line = _get_source_line_safe("/nonexistent/file.py", 1)
        assert source_line == "<source unavailable>"

    def test_get_jupyter_context(self):
        """Test handling of Jupyter notebook context."""
        source_line = _get_source_line_safe("<ipython-input-1-abc123>", 1)
        assert source_line == "<Jupyter notebook cell>"

    def test_get_interactive_context(self):
        """Test handling of interactive Python context."""
        source_line = _get_source_line_safe("<stdin>", 1)
        assert source_line == "<interactive input>"

    def test_get_compiled_string_context(self):
        """Test handling of compiled string context."""
        source_line = _get_source_line_safe("<string>", 1)
        assert source_line == "<compiled string>"

    def test_get_compiled_code_context(self):
        """Test handling of compiled Python code."""
        source_line = _get_source_line_safe("/path/to/file.pyc", 1)
        assert source_line == "<compiled code>"

        source_line = _get_source_line_safe("/path/__pycache__/file.py", 1)
        assert source_line == "<compiled code>"

    def test_get_empty_line(self):
        """Test handling of empty source lines."""
        with patch("linecache.getline", return_value="   \n"):
            source_line = _get_source_line_safe("test.py", 1)
            assert source_line == "<source unavailable>"

    def test_get_line_exception(self):
        """Test handling of exceptions during source retrieval."""
        with patch("linecache.getline", side_effect=Exception("Test error")):
            source_line = _get_source_line_safe("test.py", 1)
            assert source_line == "<source unavailable>"


class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""

    def test_class_method_context(self):
        """Test source capture from within class methods."""

        class TestClass:
            def method(self):
                return capture_source_context(depth=1)

        instance = TestClass()
        metadata = instance.method()

        assert metadata.function_name == "method"
        assert "return capture_source_context" in metadata.source_line

    def test_nested_class_context(self):
        """Test source capture from nested classes."""

        class OuterClass:
            class InnerClass:
                def method(self):
                    return capture_source_context(depth=1)

        instance = OuterClass.InnerClass()
        metadata = instance.method()

        assert metadata.function_name == "method"

    def test_decorator_context(self):
        """Test source capture through decorators."""

        def simple_decorator(func):
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            return wrapper

        @simple_decorator
        def decorated_function():
            return capture_source_context(depth=1)  # Capture decorated_function frame

        metadata = decorated_function()

        # The function we capture is the decorated function itself
        assert metadata.function_name == "decorated_function"

    def test_comprehension_context(self):
        """Test source capture from within comprehensions."""
        # This tests a more complex scenario where capture might be called
        # indirectly through operations
        results = []

        def capture_in_comprehension():
            results.append(capture_source_context(depth=1))
            return True

        # List comprehension that calls our function
        [capture_in_comprehension() for _ in range(1)]

        metadata = results[0]
        # The function captured is the one that actually called capture_source_context
        assert metadata.function_name == "capture_in_comprehension"
