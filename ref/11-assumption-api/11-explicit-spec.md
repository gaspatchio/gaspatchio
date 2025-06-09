# Gaspatchio Assumption API v2 Specification

## Executive Summary

This specification defines a new assumption table API that separates concerns, improves composability, and enables better LLM integration. The design moves from a monolithic `load_assumptions()` function to a modular system with distinct phases: analysis, configuration, and usage.

## Core Design Principles

1. **Separation of Concerns**: Each phase (analyze, configure, use) has distinct responsibilities
2. **Explicit over Implicit**: All transformations and mappings are visible and configurable
3. **Composable Building Blocks**: Dimension types and strategies can be combined
4. **LLM-Friendly**: Structured outputs and code generation helpers for AI assistance
5. **Progressive Disclosure**: Simple cases stay simple, complex cases are possible

## API Components

### 1. Analysis API

```python
from dataclasses import dataclass
from typing import Literal, Optional, Union, Dict, Any, List
from pathlib import Path
import polars as pl

@dataclass
class DimensionInfo:
    """Information about a detected dimension in the data"""
    name: str
    dtype: str
    unique_count: int
    sample_values: List[Any]  # First 5 unique values
    suggested_type: Literal["key", "melt", "categorical"]
    numeric_pattern: Optional[str] = None  # e.g., "1-25", "continuous"

@dataclass
class InterpolationHint:
    """Suggestion for interpolation opportunities"""
    dimension: str
    detected_values: List[Union[int, float]]
    missing_values: List[Union[int, float]]
    suggested_method: Literal["linear", "log-linear", "cubic"]

@dataclass
class TableSchema:
    """Complete analysis result for a table"""
    data_dimensions: List[DimensionInfo]
    value_columns: List[str]
    format: Literal["curve", "wide"]
    overflow_candidate: Optional[str] = None
    interpolation_opportunities: List[InterpolationHint] = field(default_factory=list)
    row_count: int = 0
    
    def suggest_table_config(self) -> str:
        """Generate example code for loading this table"""
        # Implementation below
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        pass

def analyze_table(
    source: Union[str, Path, pl.DataFrame],
    sample_rows: int = 1000,
    detect_overflow: bool = True,
    detect_interpolation: bool = True
) -> TableSchema:
    """
    Analyze table structure and suggest loading configuration.
    
    Args:
        source: Data source to analyze
        sample_rows: Number of rows to sample for analysis
        detect_overflow: Whether to detect overflow columns
        detect_interpolation: Whether to detect interpolation opportunities
        
    Returns:
        TableSchema with analysis results
    """
    pass
```

### 2. Dimension Types

```python
from abc import ABC, abstractmethod

class Dimension(ABC):
    """Base class for all dimension types"""
    
    @abstractmethod
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Process the dimension on the given DataFrame"""
        pass
    
    @abstractmethod
    def validate(self, df: pl.DataFrame) -> None:
        """Validate this dimension can be applied to the DataFrame"""
        pass

@dataclass
class DataDimension(Dimension):
    """Map a data column directly to a dimension"""
    column: str
    rename_to: Optional[str] = None
    dtype: Optional[pl.DataType] = None  # Force specific dtype
    
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        # Implementation
        pass

@dataclass
class MeltDimension(Dimension):
    """Melt wide columns into a long format dimension"""
    columns: List[str]
    name: str = "variable"
    overflow: Optional['OverflowStrategy'] = None
    fill: Optional['FillStrategy'] = None
    
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        # Implementation
        pass

@dataclass
class CategoricalDimension(Dimension):
    """Add a constant categorical value as a dimension"""
    value: Any
    name: Optional[str] = None  # Auto-generated if not provided
    
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        # Implementation
        pass

@dataclass
class ComputedDimension(Dimension):
    """Compute a dimension from existing columns"""
    expression: pl.Expr
    name: str
    
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        # Implementation
        pass
```

### 3. Strategy Types

```python
class OverflowStrategy(ABC):
    """Base class for overflow handling strategies"""
    
    @abstractmethod
    def apply(self, df: pl.DataFrame, dimension_name: str) -> pl.DataFrame:
        pass

@dataclass
class ExtendOverflow(OverflowStrategy):
    """Extend an overflow column to a specified value"""
    column: str  # Column name like "Ultimate", "Ult."
    to_value: int = 200
    from_value: Optional[int] = None  # Auto-detect if None
    
@dataclass
class AutoDetectOverflow(OverflowStrategy):
    """Automatically detect and extend overflow column"""
    patterns: List[str] = field(default_factory=lambda: ["ult", "ultimate", "999", ""])
    to_value: int = 200

class FillStrategy(ABC):
    """Base class for filling missing values"""
    
    @abstractmethod  
    def apply(self, values: List[Any]) -> pl.DataFrame:
        pass

@dataclass
class LinearInterpolate(FillStrategy):
    """Linear interpolation between values"""
    method: Literal["linear", "log-linear", "cubic"] = "linear"
    fill_gaps: bool = True
    extrapolate: bool = False

@dataclass
class FillConstant(FillStrategy):
    """Fill with a constant value"""
    value: Any

@dataclass
class FillForward(FillStrategy):
    """Forward fill missing values"""
    limit: Optional[int] = None
```

### 4. Table Class

```python
class Table:
    """
    Main assumption table class with dimension-based structure.
    """
    
    def __init__(
        self,
        name: str,
        source: Union[str, Path, pl.DataFrame],
        dimensions: Dict[str, Dimension],
        value: str = "rate",
        validate: bool = True,
    ):
        """
        Create a new assumption table.
        
        Args:
            name: Unique table name for registration
            source: Data source
            dimensions: Mapping of dimension names to dimension objects
            value: Name for the value column
            validate: Whether to validate data on load
        """
        self._name = name
        self._dimensions = dimensions
        self._value = value
        self._df: Optional[pl.DataFrame] = None
        self._schema: Optional[TableSchema] = None
        
    def extend(
        self,
        source: Union[str, Path, pl.DataFrame],
        dimensions: Optional[Dict[str, Dimension]] = None,
        validate: bool = True,
    ) -> "Table":
        """
        Extend table with additional data slices.
        
        Args:
            source: Additional data to add
            dimensions: Dimension overrides for this slice
            validate: Whether to validate compatibility
            
        Returns:
            Self for chaining
        """
        pass
    
    def lookup(self, **kwargs: Union[str, pl.Expr]) -> pl.Expr:
        """
        Create a lookup expression using dimension names.
        
        Args:
            **kwargs: Dimension name to column/expression mapping
            
        Returns:
            Polars expression for the lookup
        """
        pass
    
    @property
    def schema(self) -> TableSchema:
        """Get the analyzed schema of this table"""
        pass
    
    @property
    def dimensions(self) -> Dict[str, Dimension]:
        """Get dimension configuration"""
        return self._dimensions.copy()
    
    def dimension_values(self, dimension: str) -> List[Any]:
        """Get unique values for a specific dimension"""
        pass
    
    def to_dataframe(self) -> pl.DataFrame:
        """Export the complete table as a DataFrame"""
        pass
    
    def describe(self) -> str:
        """Get a human-readable description of the table"""
        pass
    
    def validate_lookup(self, **kwargs) -> None:
        """Validate a lookup configuration without executing"""
        pass
```

### 5. Builder Pattern (Optional)

```python
class TableBuilder:
    """Fluent builder for complex table configurations"""
    
    def __init__(self, name: str):
        self.name = name
        self._dimensions = {}
        
    def from_source(self, source: Union[str, Path, pl.DataFrame]) -> "TableBuilder":
        self._source = source
        return self
        
    def with_data_dimension(self, name: str, column: str, **kwargs) -> "TableBuilder":
        self._dimensions[name] = DataDimension(column, **kwargs)
        return self
        
    def with_melt_dimension(self, name: str, columns: List[str], **kwargs) -> "TableBuilder":
        self._dimensions[name] = MeltDimension(columns, name=name, **kwargs)
        return self
        
    def with_categorical_dimension(self, name: str, value: Any) -> "TableBuilder":
        self._dimensions[name] = CategoricalDimension(value, name=name)
        return self
        
    def with_value_column(self, name: str) -> "TableBuilder":
        self._value = name
        return self
        
    def build(self) -> Table:
        return Table(self.name, self._source, self._dimensions, self._value)
```

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1-2)

#### 1.1 Create New Module Structure
```
gaspatchio_core/assumptions/
├── __init__.py          # Public API exports
├── _api_v2.py          # New Table and dimension classes
├── _analysis_v2.py     # Enhanced analysis functions
├── _dimensions.py      # Dimension implementations
├── _strategies.py      # Strategy implementations
├── _builder.py         # TableBuilder implementation
└── _compat.py          # Compatibility layer
```

#### 1.2 Implement Analysis API

**File: `_analysis_v2.py`**
```python
# Enhance existing _analyse_shape to return TableSchema
# Add overflow detection from _overflow.py
# Add interpolation detection logic
# Implement suggest_table_config() code generation
```

#### 1.3 Implement Dimension Types

**File: `_dimensions.py`**
```python
# Move and refactor from _transform.py:
# - _tidy_curve → DataDimension.process()
# - _tidy_wide_basic → MeltDimension.process()
# - Add CategoricalDimension.process()
# - Add ComputedDimension.process()
```

#### 1.4 Implement Strategy Types

**File: `_strategies.py`**
```python
# Move and refactor from _overflow.py:
# - _create_overflow_expansion → ExtendOverflow.apply()
# - _detect_overflow_column → AutoDetectOverflow.apply()
# Add interpolation strategies
```

### Phase 2: Table Implementation (Week 3)

#### 2.1 Implement Table Class

**File: `_api_v2.py`**
```python
# Core Table class with:
# - Dimension processing pipeline
# - Integration with PyAssumptionTableRegistry
# - Lookup expression generation
# - Schema introspection
```

#### 2.2 Update Rust Integration

**Files to modify:**
- `gaspatchio-core/core/src/assumptions/`
  - Add support for named dimensions in lookup
  - Extend table metadata to include dimension info

### Phase 3: Compatibility Layer (Week 4)

#### 3.1 Create Compatibility Wrapper

**File: `_compat.py`**
```python
def load_assumptions_v1(*args, **kwargs) -> pl.DataFrame:
    """Original API preserved for backward compatibility"""
    # Convert to Table API internally
    # Return DataFrame for compatibility
    
def assumption_lookup_v1(*args, **kwargs) -> pl.Expr:
    """Original positional lookup preserved"""
    # Convert to named lookup internally
```

#### 3.2 Update Public API

**File: `__init__.py`**
```python
# Phase 1: Add new API alongside old
from ._api_v2 import Table, analyze_table
from ._dimensions import *
from ._strategies import *
from ._builder import TableBuilder

# Keep old API available
from .api import load_assumptions as load_assumptions_v1
from .api import assumption_lookup as assumption_lookup_v1

# Phase 2: Switch defaults
load_assumptions = load_assumptions_v2  # New wrapper
assumption_lookup = assumption_lookup_v2  # New wrapper
```

### Phase 4: Testing & Documentation (Week 5)

#### 4.1 Test Suite
```
tests/assumptions/
├── test_analysis_v2.py
├── test_dimensions.py
├── test_strategies.py
├── test_table.py
├── test_builder.py
└── test_compat.py
```

#### 4.2 Documentation Updates
- API reference with examples
- Migration guide from v1 to v2
- LLM integration examples

## Usage Examples

### Example 1: Simple Curve Table

```python
import gaspatchio_core as gs

# Analyze first
schema = gs.analyze_table("interest_rates.csv")
print(schema)
# TableSchema(
#   format='curve',
#   data_dimensions=[DimensionInfo(name='term', suggested_type='key')],
#   value_columns=['rate']
# )

# Load with minimal config
rates = gs.Table(
    name="treasury_curve",
    source="interest_rates.csv",
    dimensions={
        'term': gs.DataDimension('term')
    },
    value='rate'
)

# Use in model
result = df.with_columns(
    rates.lookup(term=pl.col("duration")).alias("discount_rate")
)
```

### Example 2: Wide Table with Overflow

```python
# Analyze mortality table
schema = gs.analyze_table("mortality_select.csv")
print(schema.overflow_candidate)  # "Ultimate"

# Load with overflow expansion
mortality = gs.Table(
    name="mortality_2015",
    source="mortality_select.csv",
    dimensions={
        'age': gs.DataDimension('issue_age'),
        'duration': gs.MeltDimension(
            columns=['1', '2', '3', '4', '5', '10', '15', '20', '25'],
            overflow=gs.ExtendOverflow('Ultimate', to_value=120)
        ),
    },
    value='qx'
)

# Clean lookup syntax
result = df.with_columns(
    mortality.lookup(
        age=pl.col("issue_age"),
        duration=pl.col("policy_year")
    ).alias("qx")
)
```

### Example 3: Multi-Dimensional Table

```python
# Build incrementally
mortality = (
    gs.TableBuilder("mortality_cso")
    .from_source("cso_2015_Male_Nonsmoker.csv")
    .with_data_dimension("age", "Age")
    .with_melt_dimension("duration", ['1', '2', '3', 'Ultimate'])
    .with_categorical_dimension("sex", "M")
    .with_categorical_dimension("smoking", "NS")
    .with_value_column("qx")
    .build()
)

# Extend with other slices
mortality.extend(
    "cso_2015_Female_Nonsmoker.csv",
    dimensions={
        'sex': gs.CategoricalDimension('F'),
        'smoking': gs.CategoricalDimension('NS'),
    }
)

# Lookup with all dimensions
result = df.with_columns(
    mortality.lookup(
        age=pl.col("issue_age"),
        duration=pl.col("year"),
        sex=pl.col("gender"),
        smoking=pl.col("smoker_flag")
    ).alias("mortality_rate")
)
```

### Example 4: LLM Integration

```python
# LLM analyzes and generates code
schema = gs.analyze_table("complex_assumption.csv")
code = schema.suggest_table_config()
print(code)

# Output:
"""
# Detected wide table with possible overflow column
# Suggested configuration:

table = gs.Table(
    name="your_table_name",
    source="complex_assumption.csv",
    dimensions={
        'policy_year': gs.DataDimension('PolicyYear'),
        'age_band': gs.DataDimension('AgeBand'),
        'values': gs.MeltDimension(
            columns=['Y1', 'Y2', 'Y3', 'Y4', 'Y5', 'Y10', 'Y15', 'Y20'],
            overflow=gs.ExtendOverflow('Ultimate', to_value=100),
            fill=gs.LinearInterpolate(method='linear', fill_gaps=True)
        ),
    },
    value='rate'
)

# Note: Detected possible interpolation opportunities between Y5 and Y10
"""
```

## Migration Strategy

### For Existing Code

```python
# Old code
gs.load_assumptions("mort", df, id="age", overflow="auto")
result = gs.assumption_lookup("age", table_name="mort")

# New code (automatic conversion)
mort = gs.Table("mort", df, dimensions={'age': gs.DataDimension('age')})
result = mort.lookup(age=pl.col("age"))

# Or use compatibility layer
gs.load_assumptions_v1("mort", df, id="age", overflow="auto")
```

### Deprecation Timeline

1. **v2.0**: Introduce new API, keep old API as primary
2. **v2.1**: Switch primary API to new, deprecation warnings on old
3. **v3.0**: Move old API to optional compatibility package

## Key Benefits

1. **Discoverability**: `analyze_table()` helps understand data
2. **Explicitness**: All transformations are visible
3. **Composability**: Dimensions and strategies compose cleanly  
4. **Type Safety**: Strong typing throughout
5. **LLM-Friendly**: Structured data and code generation
6. **Performance**: Same underlying Rust engine
7. **Flexibility**: Handles complex scenarios elegantly

## Implementation Notes

- Reuse existing Rust infrastructure where possible
- Keep backward compatibility until v3.0
- Focus on developer experience and API clarity
- Ensure all examples in documentation work
- Add comprehensive error messages with suggestions

## Concrete Implementation Example

Here's how to transform the existing `_analysis.py` into the new API:

### Current _analyse_shape() Function
```python
def _analyse_shape(df, id):
    # Returns: (id_columns, numeric_wide_cols, text_wide_cols, is_wide)
    ...
```

### New analyze_table() Implementation
```python
# _analysis_v2.py
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict, Any, Literal
import polars as pl
from pathlib import Path
from loguru import logger

from ._source import _materialise
from ._overflow import _detect_overflow_column

@dataclass
class DimensionInfo:
    name: str
    dtype: str
    unique_count: int
    sample_values: List[Any]
    suggested_type: Literal["key", "melt", "categorical"]
    numeric_pattern: Optional[str] = None

@dataclass
class TableSchema:
    data_dimensions: List[DimensionInfo]
    value_columns: List[str]
    format: Literal["curve", "wide"]
    overflow_candidate: Optional[str] = None
    interpolation_opportunities: List[InterpolationHint] = field(default_factory=list)
    row_count: int = 0
    
    def suggest_table_config(self) -> str:
        """Generate example code for loading this table"""
        lines = ["import gaspatchio_core as gs", ""]
        
        # Start building the table configuration
        lines.append(f"# Detected {self.format} table with {self.row_count} rows")
        
        if self.format == "curve":
            # Simple curve table
            lines.append("table = gs.Table(")
            lines.append('    name="your_table_name",')
            lines.append(f'    source="your_source",')
            lines.append("    dimensions={")
            
            for dim in self.data_dimensions:
                if dim.suggested_type == "key":
                    lines.append(f'        "{dim.name}": gs.DataDimension("{dim.name}"),')
            
            lines.append("    },")
            if self.value_columns:
                lines.append(f'    value="{self.value_columns[0]}"')
            lines.append(")")
            
        else:  # wide table
            lines.append("table = gs.Table(")
            lines.append('    name="your_table_name",')
            lines.append(f'    source="your_source",')
            lines.append("    dimensions={")
            
            # Add key dimensions
            for dim in self.data_dimensions:
                if dim.suggested_type == "key":
                    lines.append(f'        "{dim.name}": gs.DataDimension("{dim.name}"),')
            
            # Add melt dimension
            if self.value_columns:
                lines.append(f'        "variable": gs.MeltDimension(')
                lines.append(f'            columns={self.value_columns},')
                
                if self.overflow_candidate:
                    lines.append(f'            overflow=gs.ExtendOverflow("{self.overflow_candidate}", to_value=200),')
                
                lines.append('        ),')
            
            lines.append("    },")
            lines.append('    value="rate"')
            lines.append(")")
        
        if self.interpolation_opportunities:
            lines.append("")
            lines.append("# Note: Detected interpolation opportunities:")
            for hint in self.interpolation_opportunities:
                lines.append(f"#   - {hint.dimension}: gaps between {hint.detected_values}")
        
        return "\n".join(lines)

def analyze_table(
    source: Union[str, Path, pl.DataFrame],
    sample_rows: int = 1000,
    detect_overflow: bool = True,
    detect_interpolation: bool = True
) -> TableSchema:
    """Analyze table structure and suggest loading configuration."""
    
    logger.info(f"Analyzing table structure from {source}")
    
    # Materialize the data
    df = _materialise(source)
    
    # Sample if needed
    if len(df) > sample_rows:
        df_sample = df.sample(n=sample_rows, seed=42)
    else:
        df_sample = df
    
    # Detect dimensions
    dimensions = []
    numeric_cols = []
    non_numeric_cols = []
    
    for col in df.columns:
        dtype = str(df[col].dtype)
        unique_count = df[col].n_unique()
        sample_values = df[col].unique().limit(5).to_list()
        
        if df[col].dtype.is_numeric():
            numeric_cols.append(col)
            
            # Check if this looks like a key column
            if unique_count < len(df) * 0.8:  # Not mostly unique
                suggested_type = "key"
            else:
                suggested_type = "melt"  # Likely a value column
                
            # Detect numeric patterns
            if all(isinstance(v, (int, float)) for v in sample_values):
                sorted_vals = sorted(v for v in sample_values if v is not None)
                if sorted_vals:
                    numeric_pattern = f"{min(sorted_vals)}-{max(sorted_vals)}"
                else:
                    numeric_pattern = None
            else:
                numeric_pattern = None
                
        else:
            non_numeric_cols.append(col)
            suggested_type = "key"  # Non-numeric are usually keys
            numeric_pattern = None
        
        dimensions.append(DimensionInfo(
            name=col,
            dtype=dtype,
            unique_count=unique_count,
            sample_values=sample_values,
            suggested_type=suggested_type,
            numeric_pattern=numeric_pattern
        ))
    
    # Determine format
    potential_value_cols = [d for d in dimensions if d.suggested_type == "melt"]
    is_wide = len(potential_value_cols) > 1
    
    # Detect overflow
    overflow_candidate = None
    if detect_overflow and is_wide:
        value_col_names = [d.name for d in potential_value_cols]
        overflow_candidate = _detect_overflow_column(value_col_names, "auto")
    
    # Build schema
    schema = TableSchema(
        data_dimensions=[d for d in dimensions if d.suggested_type == "key"],
        value_columns=[d.name for d in potential_value_cols],
        format="wide" if is_wide else "curve",
        overflow_candidate=overflow_candidate,
        row_count=len(df)
    )
    
    # Detect interpolation opportunities
    if detect_interpolation and is_wide:
        for dim in potential_value_cols:
            if dim.numeric_pattern:
                # Simple gap detection
                try:
                    numeric_vals = [int(dim.name) for dim in potential_value_cols 
                                   if dim.name.isdigit()]
                    if numeric_vals:
                        numeric_vals.sort()
                        gaps = []
                        for i in range(len(numeric_vals) - 1):
                            if numeric_vals[i+1] - numeric_vals[i] > 1:
                                gaps.extend(range(numeric_vals[i]+1, numeric_vals[i+1]))
                        
                        if gaps:
                            schema.interpolation_opportunities.append(
                                InterpolationHint(
                                    dimension="variable",
                                    detected_values=numeric_vals,
                                    missing_values=gaps[:10],  # First 10 gaps
                                    suggested_method="linear"
                                )
                            )
                except:
                    pass  # Skip if can't parse as numbers
    
    logger.info(f"Analysis complete: {schema.format} table with {len(dimensions)} dimensions")
    return schema
```

### Transform Existing Functions to Dimension Classes

```python
# _dimensions.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Any
import polars as pl
from loguru import logger

from ._transform import _convert_keys_to_f64

class Dimension(ABC):
    """Base class for all dimension types"""
    
    @abstractmethod
    def process(self, df: pl.DataFrame) -> tuple[pl.DataFrame, List[str]]:
        """Process dimension and return (df, key_columns)"""
        pass
    
    @abstractmethod
    def validate(self, df: pl.DataFrame) -> None:
        """Validate this dimension can be applied"""
        pass

@dataclass
class DataDimension(Dimension):
    """Direct column mapping"""
    column: str
    rename_to: Optional[str] = None
    dtype: Optional[pl.DataType] = None
    
    def validate(self, df: pl.DataFrame) -> None:
        if self.column not in df.columns:
            raise ValueError(f"Column '{self.column}' not found in DataFrame")
    
    def process(self, df: pl.DataFrame) -> tuple[pl.DataFrame, List[str]]:
        self.validate(df)
        
        # Handle renaming
        if self.rename_to and self.rename_to != self.column:
            df = df.rename({self.column: self.rename_to})
            key_name = self.rename_to
        else:
            key_name = self.column
            
        # Handle dtype conversion
        if self.dtype:
            df = df.with_columns(pl.col(key_name).cast(self.dtype))
            
        return df, [key_name]

@dataclass
class MeltDimension(Dimension):
    """Melt wide columns into long format"""
    columns: List[str]
    name: str = "variable"
    overflow: Optional['OverflowStrategy'] = None
    fill: Optional['FillStrategy'] = None
    
    def validate(self, df: pl.DataFrame) -> None:
        missing = [col for col in self.columns if col not in df.columns]
        if missing:
            raise ValueError(f"Columns not found: {missing}")
    
    def process(self, df: pl.DataFrame) -> tuple[pl.DataFrame, List[str]]:
        from ._transform import _tidy_wide_with_overflow_expansion
        
        self.validate(df)
        
        # Determine id columns (all non-melt columns)
        id_cols = [col for col in df.columns if col not in self.columns]
        
        # Process overflow if specified
        if self.overflow:
            overflow_col = self.overflow.column if hasattr(self.overflow, 'column') else None
            max_val = self.overflow.to_value if hasattr(self.overflow, 'to_value') else 200
            
            df = _tidy_wide_with_overflow_expansion(
                df, id_cols, self.columns, "temp_value",
                overflow_col, max_val
            )
            # Rename temp_value and variable columns
            df = df.rename({"variable": self.name, "temp_value": "value"})
        else:
            # Simple melt
            df = df.unpivot(
                on=self.columns,
                index=id_cols, 
                variable_name=self.name,
                value_name="value"
            )
        
        # Apply fill strategy if specified
        if self.fill:
            df = self.fill.apply(df, self.name)
            
        return df, id_cols + [self.name]

@dataclass  
class CategoricalDimension(Dimension):
    """Add constant categorical column"""
    value: Any
    name: Optional[str] = None
    
    def validate(self, df: pl.DataFrame) -> None:
        if self.name and self.name in df.columns:
            raise ValueError(f"Column '{self.name}' already exists")
    
    def process(self, df: pl.DataFrame) -> tuple[pl.DataFrame, List[str]]:
        self.validate(df)
        
        # Auto-generate name if needed
        if not self.name:
            self.name = f"cat_{str(self.value).lower()}"
            
        df = df.with_columns(pl.lit(self.value).alias(self.name))
        return df, []  # Not a lookup key by default
```

### Implementing the Table Class

```python
# _api_v2.py
from typing import Dict, List, Optional, Union, Any
from pathlib import Path
import polars as pl
from loguru import logger

from .._internal import PyAssumptionTableRegistry
from ._source import _materialise
from ._analysis_v2 import analyze_table, TableSchema
from ._dimensions import Dimension
from ._transform import _convert_keys_to_f64

class Table:
    """Main assumption table class"""
    
    def __init__(
        self,
        name: str,
        source: Union[str, Path, pl.DataFrame],
        dimensions: Dict[str, Dimension],
        value: str = "rate",
        validate: bool = True,
    ):
        self._name = name
        self._dimensions = dimensions
        self._value = value
        self._registry = PyAssumptionTableRegistry()
        
        # Process the data
        self._process_data(source, validate)
        
    def _process_data(self, source: Union[str, Path, pl.DataFrame], validate: bool):
        """Process source data through dimension pipeline"""
        df = _materialise(source)
        
        # Collect all key columns
        all_keys = []
        
        # Process each dimension in order
        for dim_name, dimension in self._dimensions.items():
            logger.debug(f"Processing dimension '{dim_name}': {type(dimension).__name__}")
            
            if validate:
                dimension.validate(df)
                
            df, keys = dimension.process(df)
            all_keys.extend(keys)
        
        # Ensure value column exists
        if self._value not in df.columns:
            # Assume last column is value if not specified
            value_cols = [col for col in df.columns if col not in all_keys]
            if value_cols:
                df = df.rename({value_cols[-1]: self._value})
            else:
                raise ValueError(f"No value column '{self._value}' found")
        
        # Convert keys to f64 where possible
        df = _convert_keys_to_f64(df, all_keys)
        
        # Register with the underlying system
        self._registry.register_table(
            name=self._name,
            df=df,
            keys=all_keys,
            value_column=self._value
        )
        
        self._df = df
        self._keys = all_keys
        logger.info(f"Registered table '{self._name}' with {len(df)} rows, keys: {all_keys}")
    
    def lookup(self, **kwargs: Union[str, pl.Expr]) -> pl.Expr:
        """Create lookup expression using dimension names"""
        from polars.plugins import register_plugin_function
        from pathlib import Path
        
        # Validate all required dimensions are provided
        missing = set(self._keys) - set(kwargs.keys())
        if missing:
            raise ValueError(f"Missing lookup keys: {missing}")
            
        # Convert to expressions in correct order
        key_exprs = []
        for key in self._keys:
            val = kwargs.get(key)
            if isinstance(val, str):
                key_exprs.append(pl.col(val))
            else:
                key_exprs.append(val)
        
        # Use existing plugin infrastructure
        LIB = Path(__file__).parent.parent
        return register_plugin_function(
            plugin_path=LIB,
            function_name="lookup_by_table_and_hash",
            args=key_exprs,
            kwargs={"table_name": self._name},
            is_elementwise=False,
        )
    
    def extend(
        self,
        source: Union[str, Path, pl.DataFrame],
        dimensions: Optional[Dict[str, Dimension]] = None,
        validate: bool = True,
    ) -> "Table":
        """Extend table with new data"""
        # Use existing dimensions if not overridden
        dims = self._dimensions.copy()
        if dimensions:
            dims.update(dimensions)
            
        # Process new data
        df = _materialise(source)
        all_keys = []
        
        for dim_name, dimension in dims.items():
            if validate:
                dimension.validate(df)
            df, keys = dimension.process(df)
            all_keys.extend(keys)
            
        # Append to registry
        self._registry.append_to_table(
            name=self._name,
            df=df,
            keys=all_keys,
            value_column=self._value
        )
        
        logger.info(f"Extended table '{self._name}' with {len(df)} additional rows")
        return self
    
    @property
    def schema(self) -> TableSchema:
        """Get table schema"""
        if not hasattr(self, '_schema'):
            self._schema = analyze_table(self._df)
        return self._schema
    
    def to_dataframe(self) -> pl.DataFrame:
        """Export as DataFrame"""
        return self._df.clone()
```

## Key Transformation Steps

1. **Split monolithic functions into composable classes**
   - `_analyse_shape()` → `analyze_table()` + `TableSchema`
   - `_tidy_*` functions → `Dimension.process()` methods
   - `_detect_overflow_column()` → `OverflowStrategy` classes

2. **Make implicit behavior explicit**
   - Auto-detection results visible in `TableSchema`
   - All transformations visible as `Dimension` objects
   - Clear separation between analysis and processing

3. **Enable composition**
   - Dimensions can be combined
   - Strategies can be mixed
   - Tables can be extended incrementally

4. **Improve developer experience**
   - Named parameters in lookups
   - Code generation helpers
   - Clear error messages with suggestions
