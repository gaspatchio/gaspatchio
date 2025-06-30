"""
DataFrame filtering logic for calculation graphs.

This module handles filtering DataFrames based on expressions, with optimizations
for common patterns like year filtering.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from polars import DataFrame


class DataFrameFilter:
    """Handles filtering of DataFrames with expression evaluation."""
    
    # Common time-based columns that might be lists
    TIME_COLUMNS = ["year", "month", "date", "year_frac", "quarter", "period"]
    
    def __init__(self, df: DataFrame):
        """
        Initialize the filter with a DataFrame.
        
        Args:
            df: The DataFrame to filter
        """
        self.df = df
        self._list_columns = self._identify_list_columns()
    
    def _identify_list_columns(self) -> list[str]:
        """Identify columns with List data type."""
        list_cols = []
        for col in self.TIME_COLUMNS:
            if col in self.df.columns:
                dtype = self.df[col].dtype
                if isinstance(dtype, pl.List):
                    list_cols.append(col)
        return list_cols
    
    def apply_filter(self, filter_expr: str) -> DataFrame:
        """
        Apply a filter expression to the DataFrame.
        
        Args:
            filter_expr: Polars filter expression as a string
            
        Returns:
            Filtered DataFrame
        """
        if not filter_expr:
            return self.df
        
        try:
            logger.debug(f"Applying filter expression: {filter_expr}")
            
            # Check for optimizable year filter
            if self._is_simple_year_filter(filter_expr):
                return self._apply_optimized_year_filter(filter_expr)
            
            # Apply general filter
            return self._apply_general_filter(filter_expr)
            
        except Exception as e:
            logger.warning(f"Failed to apply filter expression '{filter_expr}': {e}")
            logger.warning("Continuing with unfiltered DataFrame")
            return self.df
    
    def _is_simple_year_filter(self, filter_expr: str) -> bool:
        """Check if this is a simple year equality filter."""
        pattern = r"col\(['\"]year['\"]\)\s*==\s*\d+"
        return bool(re.match(pattern, filter_expr.strip())) and self._list_columns
    
    def _apply_optimized_year_filter(self, filter_expr: str) -> DataFrame:
        """Apply optimized year filtering without exploding lists."""
        match = re.match(r"col\(['\"]year['\"]\)\s*==\s*(\d+)", filter_expr.strip())
        if not match:
            return self._apply_general_filter(filter_expr)
        
        target_year = int(match.group(1))
        year_index = target_year - 1  # Convert to 0-based index
        
        logger.debug(f"Using optimized year filter for year {target_year} (index {year_index})")
        
        # Add year index as a column for value extraction
        return self.df.with_columns(
            pl.lit(year_index).alias("__filter_year_index__")
        )
    
    def _apply_general_filter(self, filter_expr: str) -> DataFrame:
        """Apply a general filter expression."""
        # Check if we need to explode list columns
        if self._needs_list_explosion(filter_expr):
            df = self._explode_list_columns()
        else:
            df = self.df
        
        # Evaluate the filter expression
        filter_result = eval(filter_expr, {"pl": pl, "col": pl.col}, {})
        filtered_df = df.filter(filter_result)
        
        logger.debug(f"Filter reduced rows from {len(df)} to {len(filtered_df)}")
        return filtered_df
    
    def _needs_list_explosion(self, filter_expr: str) -> bool:
        """Check if filter expression requires list column explosion."""
        if not self._list_columns:
            return False
        return any(col in filter_expr for col in self._list_columns)
    
    def _explode_list_columns(self) -> DataFrame:
        """Explode all list columns to create multiple rows."""
        logger.debug(f"Exploding list columns: {self._list_columns}")
        df = self.df
        
        for col in self.df.columns:
            if isinstance(df[col].dtype, pl.List):
                df = df.explode(col)
        
        logger.debug(f"After exploding: {len(df)} rows")
        return df