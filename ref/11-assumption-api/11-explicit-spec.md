# Gaspatchio Assumption API v2 Specification

## Executive Summary

This specification defines a new assumption table API that separates concerns, improves composability, and enables better LLM integration. The design moves from a monolithic `load_assumptions()` function to a modular system with distinct phases: analysis, configuration, and usage.

**Note: This is a complete replacement of the existing API with no backward compatibility requirements.**

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

### Phase 1: Core Infrastructure (Week 1)

#### 1.1 Create New Module Structure
```
gaspatchio-core/bindings/python/gaspatchio_core/assumptions/
├── __init__.py          # Public API exports (REPLACE EXISTING)
├── _api.py             # Table and core classes (REPLACE EXISTING api.py)
├── _analysis.py        # Enhanced analysis functions (REPLACE EXISTING)
├── _dimensions.py      # Dimension implementations (CREATE NEW)
├── _strategies.py      # Strategy implementations (CREATE NEW)
├── _builder.py         # TableBuilder implementation (CREATE NEW)

# Files to remove:
├── api.py              # DELETE - replaced by _api.py
```

#### 1.2 Implement Analysis API

**File: `gaspatchio-core/bindings/python/gaspatchio_core/assumptions/_analysis.py`** (REPLACE EXISTING)
```python
# Replace existing _analysis.py entirely with new implementation
# Import from existing modules:
from ._source import _materialise  # Keep existing
from ._overflow import _detect_overflow_column  # Keep existing helper

# Add new functionality:
# - TableSchema dataclass
# - analyze_table() function
# - Code generation in suggest_table_config()
```

#### 1.3 Implement Dimension Types

**File: `gaspatchio-core/bindings/python/gaspatchio_core/assumptions/_dimensions.py`** (CREATE NEW)
```python
# Import useful functions from existing modules:
from ._transform import (
    # Extract these functions as utilities, don't delete _transform.py yet
    _convert_keys_to_f64
)

# Implement dimension classes that replace the old transform logic
```

#### 1.4 Implement Strategy Types

**File: `gaspatchio-core/bindings/python/gaspatchio_core/assumptions/_strategies.py`** (CREATE NEW)
```python
# Import useful functions from existing modules:
from ._overflow import (
    # Extract these as utilities
    _create_overflow_expansion,
    _detect_overflow_column
)

# Implement strategy classes
```

### Phase 2: Table Implementation and API Replacement (Week 2)

#### 2.1 Implement Table Class

**File: `gaspatchio-core/bindings/python/gaspatchio_core/assumptions/_api.py`** (REPLACE api.py)
```python
# Complete replacement of existing api.py
# No need to maintain old load_assumptions() or assumption_lookup()

from .._internal import PyAssumptionTableRegistry
from ._source import _materialise
from ._analysis import analyze_table, TableSchema
from ._dimensions import Dimension
from ._transform import _convert_keys_to_f64

class Table:
    """Main assumption table class - replaces load_assumptions()"""
    # Full implementation as specified
```

#### 2.2 Update Public API

**File: `gaspatchio-core/bindings/python/gaspatchio_core/assumptions/__init__.py`** (REPLACE CONTENTS)
```python
# Complete replacement - no backward compatibility

from ._api import Table
from ._analysis import analyze_table, TableSchema, DimensionInfo
from ._dimensions import (
    Dimension, DataDimension, MeltDimension, 
    CategoricalDimension, ComputedDimension
)
from ._strategies import (
    OverflowStrategy, ExtendOverflow, AutoDetectOverflow,
    FillStrategy, LinearInterpolate, FillConstant, FillForward
)
from ._builder import TableBuilder

__all__ = [
    # Core API
    "Table", "analyze_table", "TableBuilder",
    # Schema types
    "TableSchema", "DimensionInfo",
    # Dimensions
    "DataDimension", "MeltDimension", "CategoricalDimension", "ComputedDimension",
    # Strategies
    "ExtendOverflow", "AutoDetectOverflow", 
    "LinearInterpolate", "FillConstant", "FillForward",
]
```

#### 2.3 Update Rust Integration

**Files to modify:**
- `gaspatchio-core/bindings/python/src/assumptions.rs` (MODIFY)
  - Update to support named dimensions in lookup
  
### Phase 3: Testing & Documentation (Week 3)

#### 3.1 Update All Tests

**Test Directory: `gaspatchio-core/bindings/python/tests/assumptions/`**

```
# Update existing tests to new API:
tests/assumptions/
├── test_analysis.py         # UPDATE to test analyze_table()
├── test_api.py             # UPDATE to test Table class
├── test_dimensions.py      # CREATE NEW
├── test_strategies.py      # CREATE NEW
├── test_builder.py         # CREATE NEW
├── test_curve.py          # UPDATE to use new API
├── test_wide_basic.py     # UPDATE to use new API
├── test_overflow.py       # UPDATE to use new API
├── test_integration.py    # UPDATE to use new API

# Remove old test patterns, update to new API
```

#### 3.2 Test Execution Commands

```bash
# Run all tests after conversion
cd gaspatchio-core/bindings/python
pytest tests/assumptions/ -v

# Run specific test files during development
pytest tests/assumptions/test_analysis.py -v
pytest tests/assumptions/test_api.py -v
pytest tests/assumptions/test_dimensions.py -v

# Run with coverage
pytest tests/assumptions/ --cov=gaspatchio_core.assumptions --cov-report=html
```

#### 3.3 Documentation

**Documentation files:**
```
gaspatchio-docs/docs/api/
├── assumptions.md          # UPDATE - Complete rewrite for v2 API

gaspatchio-core/bindings/python/gaspatchio_core/examples/
├── assumptions_basic.py    # CREATE NEW - Basic examples
├── assumptions_advanced.py # CREATE NEW - Advanced patterns
```

### Phase 4: Cleanup (Week 4)

#### 4.1 Remove Old Code
- Delete unused functions from `_transform.py` after extracting utilities
- Delete unused functions from `_overflow.py` after extracting utilities
- Clean up any remaining old API artifacts

#### 4.2 Final Testing
- Run full test suite
- Update any models using the API
- Performance benchmarking

## Key Benefits of Straight Cutover

1. **Simplicity**: No compatibility layer complexity
2. **Speed**: Faster implementation without legacy constraints
3. **Clean Code**: No deprecated code paths
4. **Testing**: All tests use new API from the start
5. **Documentation**: Single, clear API to document

## Usage Examples

### Example 1: Simple Curve Table

```python
import gaspatchio_core as gs

# Analyze first
schema = gs.analyze_table("interest_rates.csv")
print(schema)

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

## Implementation Notes

### File Organization
- All new files go in: `gaspatchio-core/bindings/python/gaspatchio_core/assumptions/`
- All tests updated in place: `gaspatchio-core/bindings/python/tests/assumptions/`
- Examples go in: `gaspatchio-core/bindings/python/gaspatchio_core/examples/`
- Documentation goes in: `gaspatchio-docs/docs/api/`

### Key Technical Notes
- Reuse existing Rust infrastructure (PyAssumptionTableRegistry)
- Replace API completely - no backward compatibility
- Focus on getting to testable state quickly
- Update all tests to use new API

### Testing Strategy
- Convert existing tests to new API
- Add new tests for new components
- Aim for working end-to-end test ASAP

## Development Workflow

```bash
# Start development in the correct directory
cd ~/Projects/gaspatchio/gaspatchio-core/bindings/python

# Create new files
touch gaspatchio_core/assumptions/_api.py  # Will replace api.py
touch gaspatchio_core/assumptions/_dimensions.py
touch gaspatchio_core/assumptions/_strategies.py
touch gaspatchio_core/assumptions/_builder.py

# Update existing files
# _analysis.py - replace implementation
# __init__.py - replace exports

# Create/update test files
touch tests/assumptions/test_dimensions.py
touch tests/assumptions/test_strategies.py
touch tests/assumptions/test_builder.py

# Run tests during development
pytest tests/assumptions/test_analysis.py -v
pytest tests/assumptions/test_api.py -v

# Full test suite
pytest tests/assumptions/ -v
```

## Phase 5: Old API Removal Plan (Breaking Changes)

### Overview
This phase removes the old monolithic API completely, with no backward compatibility. The new API is fully implemented and tested, so we can cleanly remove ~11,300 lines of old code.

### Old API Components to Remove

#### 1. Core API Files (~2,900 lines)
- **api.py** (1,539 lines) - Contains `load_assumptions()`, `append_assumptions()`, `assumption_lookup()`
- **_validation.py** (213 lines) - Validation helpers for old API
- **_config.py** (92 lines) - Configuration storage for append operations
- **_transform.py** (208 lines) - Data transformation utilities
- **_overflow.py** (191 lines) - Overflow detection and expansion
- **_source.py** (104 lines) - Data materialization

#### 2. Test Files (~8,400 lines)
- **test_api_append.py** (896 lines) - Tests for append_assumptions
- **test_api_load.py** (598 lines) - Tests for load_assumptions
- **test_api_lookup.py** (405 lines) - Tests for assumption_lookup
- **test_validation.py** (456 lines) - Validation tests
- **test_config.py** (305 lines) - Config storage tests
- **test_errors.py** (460 lines) - Error handling tests
- **test_overflow.py** (464 lines) - Overflow logic tests
- **test_curve.py** (422 lines) - Curve table tests
- **test_wide_basic.py** (739 lines) - Wide table tests
- **test_advanced.py** (710 lines) - Advanced scenarios
- **test_duplicates.py** (450 lines) - Duplicate handling tests
- **test_breaking_changes.py** (251 lines) - Breaking change tests
- **test_integration.py** (351 lines) - Integration tests
- **test_integration_append.py** (1,510 lines) - Append integration tests
- **test_performance.py** (800 lines) - Performance tests

### Migration Strategy

#### Step 1: Extract Shared Utilities
Some functions are still needed by the new API:
- `_materialise()` - Used by Table and analyze_table
- `_convert_keys_to_f64()` - Used by Table for Rust compatibility
- `_detect_overflow_column()` - Used by analyze_table

Create a new `_utils.py` module with only these functions.

#### Step 2: Add Missing Features to New API
The new API needs:
1. **Metadata support** - Add metadata parameter and storage to Table class
2. **Table listing** - Add function to list all registered tables
3. **Proper lookup** - Connect Table.lookup() to actual Rust plugin

#### Step 3: Clean Removal
1. Delete all old API files
2. Delete all old test files
3. Update __init__.py to remove old imports
4. Create single migration test file to ensure coverage

### Mapping Old API to New API

| Old API | New API | Notes |
|---------|---------|-------|
| `load_assumptions(name, source, id=..., value=..., value_vars=..., overflow=..., max_overflow=..., metadata=..., lookup_keys=..., additional_keys=...)` | `Table(name, source, dimensions={...}, value=...)` | Dimensions replace all the individual parameters |
| `append_assumptions(name, source, additional_keys=...)` | `table.extend(source, dimensions=...)` | Method on Table instance |
| `assumption_lookup(*keys, table_name=...)` | `table.lookup(**kwargs)` | Method on Table instance with named parameters |
| `get_table_metadata(name)` | `table.metadata` | Property on Table instance |
| `list_tables_with_metadata()` | `list_tables()` | New function to implement |

### Example Migrations

#### Simple Curve Table
```python
# OLD API
gs.load_assumptions("interest_rates", "rates.csv", value="rate")
rate = gs.assumption_lookup("term", table_name="interest_rates")

# NEW API
rates = gs.Table("interest_rates", "rates.csv", 
                 dimensions={"term": "term"}, value="rate")
rate = rates.lookup(term=pl.col("duration"))
```

#### Wide Table with Overflow
```python
# OLD API
gs.load_assumptions("mortality", "mort.csv", 
                   value_vars=['1', '2', '3', 'Ultimate'],
                   overflow="Ultimate", max_overflow=120)
qx = gs.assumption_lookup("age", "variable", table_name="mortality")

# NEW API
mortality = gs.Table("mortality", "mort.csv",
    dimensions={
        "age": "age",
        "duration": gs.MeltDimension(
            columns=['1', '2', '3', 'Ultimate'],
            overflow=gs.ExtendOverflow('Ultimate', to_value=120)
        )
    },
    value="qx"
)
qx = mortality.lookup(age=pl.col("issue_age"), duration=pl.col("policy_year"))
```

#### Multi-dimensional Table
```python
# OLD API
gs.load_assumptions("mortality_base", mort_data,
                   additional_keys={"sex": "M", "smoking": "NS"})
gs.append_assumptions("mortality_base", mort_data2,
                     additional_keys={"sex": "F", "smoking": "NS"})

# NEW API
mortality = gs.Table("mortality", mort_data,
    dimensions={
        "age": "age",
        "sex": gs.CategoricalDimension("M"),
        "smoking": gs.CategoricalDimension("NS")
    }
)
mortality.extend(mort_data2, 
    dimensions={"sex": gs.CategoricalDimension("F")})
```

### Benefits of Complete Removal

1. **Code Reduction**: Remove ~11,300 lines of code
2. **Clarity**: Single, consistent API pattern
3. **Maintainability**: No compatibility layer complexity
4. **Performance**: No overhead from supporting two APIs
5. **Documentation**: Single API to document and explain

### Risk Mitigation

1. **Complete Test Coverage**: New API has 99 tests passing
2. **Migration Tests**: Create specific tests for common patterns
3. **Clear Documentation**: Migration guide with examples
4. **Phased Rollout**: Can be done in separate PR after new API is stable
