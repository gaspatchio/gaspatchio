"""
Compilation error finder using schema validation and operation replay.

This module extends ErrorBoundaryFinder to handle compilation-specific errors
by using schema validation instead of execution to find failing operations.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

from .boundary import ErrorBoundaryFinder

if TYPE_CHECKING:
    from ..frame.base import ActuarialFrame
    from .metadata import TracedOperation


class CompilationErrorFinder(ErrorBoundaryFinder):
    """
    Extends ErrorBoundaryFinder for compilation errors.
    Uses schema validation instead of execution to find failures.
    """
    
    def __init__(self, af: ActuarialFrame, exception: Exception) -> None:
        """
        Initialize the compilation error finder.
        
        Args:
            af: The ActuarialFrame with failed compilation
            exception: The compilation exception that was raised
        """
        super().__init__(af, exception)
        self.compilation_error_type = type(exception)
        logger.debug(f"CompilationErrorFinder initialized for {self.compilation_error_type}")
    
    def find_failing_operation(self) -> tuple[int, TracedOperation | None, pl.DataFrame]:
        """
        Find the failing operation using schema validation.
        
        Returns:
            Tuple of (failing_index, failing_operation, last_good_dataframe)
            If no failing operation found, returns (-1, None, original_df)
        """
        operations = self.af._computation_graph
        
        if not operations:
            logger.debug("Empty computation graph, no operations to search")
            return -1, None, self.original_df
        
        # Use linear search for compilation errors to get accurate context
        return self._linear_search_with_schema()
    
    def _linear_search_with_schema(self) -> tuple[int, TracedOperation | None, pl.DataFrame]:
        """
        Perform linear search using schema validation.
        
        Returns:
            Tuple of (failing_index, failing_operation, last_good_dataframe)
        """
        operations = self.af._computation_graph
        last_good_df = self.original_df
        
        logger.debug(f"Starting linear schema search on {len(operations)} operations")
        
        for i in range(len(operations)):
            try:
                # Apply operations up to this point
                test_df = self._apply_single_operation(i, last_good_df)
                if test_df is not None:
                    last_good_df = test_df
                logger.trace(f"Operation {i} succeeded")
            except Exception as e:
                if self._is_same_compilation_error(e):
                    logger.debug(f"Found compilation error at operation {i}")
                    operation = self._get_operation_at(i)
                    return i, operation, last_good_df
                else:
                    logger.trace(f"Different error type at operation {i}: {type(e)}")
        
        logger.debug("No failing operation found in linear search")
        return -1, None, last_good_df
    
    def _apply_single_operation(self, index: int, base_df: pl.DataFrame) -> pl.DataFrame | None:
        """
        Apply a single operation and validate its schema.
        
        Args:
            index: Index of operation to apply
            base_df: Base DataFrame to apply operation to
            
        Returns:
            Resulting DataFrame or None if operation is invalid
        """
        operation = self._get_operation_at(index)
        if operation is None:
            return None
        
        # Start with lazy frame
        current_df = base_df.lazy() if not hasattr(base_df, 'lazy') else base_df
        
        # Apply all operations up to and including this one
        for i in range(index + 1):
            op = self._get_operation_at(i)
            if op is not None:
                if isinstance(op, tuple):
                    alias, expr = op
                else:
                    alias, expr = op.alias, op.expression
                
                current_df = current_df.with_columns(expr.alias(alias))
        
        # Try to validate schema
        try:
            # First try schema collection (cheapest)
            _ = current_df.collect_schema()
            # If schema is valid, collect limited data for context
            return self._safe_collect(current_df)
        except Exception as schema_error:
            # Re-raise to be caught by caller
            raise schema_error
    
    def _safe_collect(self, df: pl.LazyFrame) -> pl.DataFrame:
        """
        Safely collect limited data for error context.
        
        Args:
            df: LazyFrame to collect
            
        Returns:
            Collected DataFrame with limited rows
        """
        try:
            # Try to collect just a few rows for context
            return df.limit(10).collect()
        except Exception:
            try:
                # If that fails, try empty collection with schema
                schema = df.collect_schema()
                return pl.DataFrame(schema=schema)
            except Exception:
                # Last resort - return original
                return self.original_df
    
    def _is_same_compilation_error(self, exception: Exception) -> bool:
        """
        Check if exception is the same compilation error type.
        
        Args:
            exception: Exception to check
            
        Returns:
            True if it's the same compilation error
        """
        # Check exact type match
        if isinstance(exception, self.compilation_error_type):
            return True
        
        # Check for common compilation error types
        compilation_types = (
            pl.exceptions.ComputeError,
            pl.exceptions.ColumnNotFoundError,
            pl.exceptions.SchemaError if hasattr(pl.exceptions, 'SchemaError') else None,
        )
        
        # Filter out None values
        compilation_types = tuple(t for t in compilation_types if t is not None)
        
        return isinstance(exception, compilation_types) and self._has_compilation_context(exception)
    
    def _has_compilation_context(self, exception: Exception) -> bool:
        """
        Check if exception has compilation context indicators.
        
        Args:
            exception: Exception to check
            
        Returns:
            True if exception appears to be compilation-related
        """
        error_str = str(exception)
        compilation_indicators = [
            "FAILED HERE RESOLVING",
            "query optimization",
            "type inference",
            "schema",
            "unable to determine output"
        ]
        
        return any(indicator in error_str for indicator in compilation_indicators)