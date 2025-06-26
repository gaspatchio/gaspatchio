"""
Trace generation for calculation graph nodes.

This module provides functionality to generate step-by-step traces
showing how computed values are calculated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union

from loguru import logger


@dataclass
class TraceStep:
    """Represents a single step in a calculation trace."""
    
    step: int
    expr: str
    values: Optional[dict[str, Union[float, int, str, None]]] = None
    result: Optional[Union[float, int, str, None]] = None
    comment: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        d = {"step": self.step, "expr": self.expr}
        if self.values is not None:
            d["values"] = self.values
        if self.result is not None:
            d["result"] = self.result
        if self.comment is not None:
            d["comment"] = self.comment
        return d


class TraceGenerator:
    """Generates calculation traces for computed nodes.
    
    This simplified version avoids regex and complex parsing, focusing on
    showing the formula, value substitution, and final result.
    """
    
    def __init__(self, dependency_values: dict[str, Any]):
        """
        Initialize with dependency values.
        
        Args:
            dependency_values: Map of column names to their sample values
        """
        self.dependency_values = dependency_values
        
    def generate_trace(
        self, 
        formula: str, 
        dependencies: list[str],
        result_value: Any
    ) -> list[dict[str, Any]]:
        """
        Generate a simplified trace for a computed formula.
        
        This shows:
        1. The cleaned formula
        2. The formula with values substituted (if dependencies exist)
        3. The final result
        
        Args:
            formula: The raw formula string from the computation graph
            dependencies: List of dependency column names
            result_value: The final computed value
            
        Returns:
            List of TraceStep dictionaries
        """
        trace_steps = []
        
        # Step 1: Show cleaned formula
        clean_formula = self._minimal_clean(formula)
        trace_steps.append(TraceStep(step=1, expr=clean_formula).to_dict())
        
        # Step 2: Show with values substituted (if there are dependencies)
        if dependencies and self.dependency_values:
            expr_with_values = clean_formula
            values_used = {}
            
            # Sort dependencies by length (longest first) to avoid partial replacements
            sorted_deps = sorted(dependencies, key=len, reverse=True)
            
            for dep in sorted_deps:
                if dep in self.dependency_values:
                    value = self.dependency_values[dep]
                    formatted_value = self._format_value(value)
                    
                    # Simple replacement - look for the column name as a whole word
                    if dep in expr_with_values:
                        # Wrap in parentheses to maintain expression structure
                        expr_with_values = expr_with_values.replace(dep, f"({formatted_value})")
                        values_used[dep] = self._simplify_value(value)
            
            if values_used:
                trace_steps.append(TraceStep(
                    step=2,
                    expr=expr_with_values,
                    values=values_used
                ).to_dict())
        
        # Final step: Show the result
        final_step_num = len(trace_steps) + 1
        trace_steps.append(TraceStep(
            step=final_step_num,
            expr=self._format_value(result_value),
            result=self._simplify_value(result_value) if isinstance(result_value, list) else result_value
        ).to_dict())
        
        return trace_steps
    
    def _minimal_clean(self, formula: str) -> str:
        """
        Minimal cleaning to make formulas more readable.
        
        Uses simple string replacements instead of regex for better
        maintainability and performance.
        """
        clean = formula
        
        # Remove Polars column syntax
        clean = clean.replace('col("', '').replace('")', '')
        clean = clean.replace("col('", "").replace("')", "")
        
        # Remove type hints
        clean = clean.replace("dyn int: ", "")
        clean = clean.replace("dyn float: ", "")
        clean = clean.replace("dyn str: ", "")
        
        # Clean up list/array notation
        clean = clean.replace("[(", "(").replace(")]", ")")
        clean = clean.replace("[", "").replace("]", "")
        
        # Remove method calls that don't affect the visual representation
        clean = clean.replace(".eval()", "")
        clean = clean.replace(".list", "")
        clean = clean.replace(".element()", "")
        
        # Simplify common operations
        if ".clip(" in clean:
            # Simple handling of clip - just show it was clipped
            clean = clean.split(".clip(")[0] + " [clipped]"
        
        if "lookup_by_table_and_hash" in clean:
            # Simplify lookup operations
            clean = clean.split(".lookup_by_table_and_hash")[0] + " [lookup]"
        
        # Clean up extra spaces
        while "  " in clean:
            clean = clean.replace("  ", " ")
        
        return clean.strip()
    
    
    def _format_value(self, value: Any) -> str:
        """Format a value for display in the trace."""
        if isinstance(value, float):
            # Format floats nicely
            if abs(value) < 0.01 and value != 0:
                return f"{value:.6f}".rstrip('0').rstrip('.')
            else:
                return f"{value:.6g}"
        elif isinstance(value, list):
            # For lists, just use the first value if it's for year filtering
            if len(value) > 0:
                return self._format_value(value[0])
            return "[]"
        elif value is None:
            return "null"
        else:
            return str(value)
    
    def _format_number(self, value: Union[int, float]) -> str:
        """Format a number for final display."""
        if isinstance(value, float):
            if abs(value) < 0.01 and value != 0:
                return f"{value:.6f}".rstrip('0').rstrip('.')
            else:
                return f"{value:.6g}"
        return str(value)
    
    def _simplify_value(self, value: Any) -> Any:
        """Simplify a value for the values map."""
        if isinstance(value, list) and len(value) > 0:
            # For lists, return the first value
            return value[0]
        return value