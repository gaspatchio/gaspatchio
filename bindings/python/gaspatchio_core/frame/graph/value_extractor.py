"""
Sample value extraction from DataFrames for calculation graphs.

This module handles extracting and formatting sample values from Polars DataFrames.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from polars import DataFrame


class SampleValueExtractor:
    """Extracts and formats sample values from DataFrames."""
    
    def __init__(
        self,
        df: DataFrame,
        policy_id: str | None = None,
        policy_id_column: str = "Policy number",
    ):
        """
        Initialize the extractor with a DataFrame.
        
        Args:
            df: The DataFrame to extract values from
            policy_id: Optional policy ID for filtering
            policy_id_column: Name of the policy ID column
        """
        self.df = df
        self.policy_id = policy_id
        self.policy_id_column = policy_id_column
        self._year_index = self._get_year_index()
    
    def _get_year_index(self) -> int | None:
        """Get the year filter index if present."""
        if "__filter_year_index__" in self.df.columns:
            return self.df["__filter_year_index__"][0]
        return None
    
    def extract(self, column_name: str) -> Any:
        """
        Extract a sample value from the specified column.
        
        Args:
            column_name: The column to extract value from
            
        Returns:
            A formatted sample value suitable for JSON serialization
        """
        if column_name not in self.df.columns:
            logger.debug(f"Column {column_name} not in DataFrame")
            return None
        
        try:
            value = self._get_raw_value(column_name)
            return self._format_value(value)
        except Exception as e:
            logger.trace(f"Could not extract sample value for {column_name}: {e}")
            return None
    
    def _get_raw_value(self, column_name: str) -> Any:
        """Get the raw value from the DataFrame."""
        if self.policy_id is not None:
            return self._get_policy_specific_value(column_name)
        return self.df[column_name][0]
    
    def _get_policy_specific_value(self, column_name: str) -> Any:
        """Get value for a specific policy ID."""
        if self.policy_id_column not in self.df.columns:
            return self.df[column_name][0]
        
        # Try to convert policy_id to appropriate type
        try:
            policy_id_value = int(self.policy_id)
        except ValueError:
            policy_id_value = self.policy_id
        
        filtered = self.df.filter(pl.col(self.policy_id_column) == policy_id_value)
        if len(filtered) > 0:
            return filtered[column_name][0]
        
        # Fallback to first row
        return self.df[column_name][0]
    
    def _format_value(self, value: Any) -> Any:
        """Format a value for JSON serialization."""
        if isinstance(value, (list, pl.Series)):
            return self._format_list_value(value)
        elif isinstance(value, float):
            return round(value, 6)
        elif isinstance(value, (datetime.date, datetime.datetime)):
            return value.isoformat()
        elif value is None or isinstance(value, (int, str, bool)):
            return value
        else:
            return str(value)
    
    def _format_list_value(self, value: list | pl.Series) -> Any:
        """Format list/series values."""
        if isinstance(value, pl.Series):
            value = value.to_list()
        
        if not isinstance(value, list):
            return value
        
        # Handle year-indexed extraction
        if self._year_index is not None and len(value) > self._year_index:
            return self._format_value(value[self._year_index])
        
        # Show first few elements
        formatted = []
        for item in value[:5]:
            formatted.append(self._format_value(item))
        
        if len(value) > 5:
            formatted.append("...")
        
        return formatted