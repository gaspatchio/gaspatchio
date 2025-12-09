# RFC 29b: JAX Backend Architecture

**Status**: Draft
**Date**: 2025-12-09
**Author**: Claude & Gaz Wright
**Depends On**: RFC 29 (Assumption Lookup Performance Optimization)

## Summary

Define a backend-agnostic execution architecture for gaspatchio that allows the same actuarial DSL to run transparently on CPU (Polars) or GPU (JAX). Actuaries write models exactly as they do today; the framework chooses the optimal execution backend automatically.

**The Golden Rule**: Actuaries never write JAX code. Ever.

```python
# Actuary writes this (unchanged):
af.base_mort_rate = mortality_table.lookup(
    table_id=af.mort_table_id,
    age=af.age_at_entry,
    duration=af.duration
)
af.death_benefit = af.base_mort_rate * af.sum_assured * af.lives
result = af.collect()  # ← Backend chosen here, transparently

# Framework decides: Polars/CPU or JAX/GPU
# Actuary doesn't know or care
```

---

## Motivation

### Why This Matters

RFC 29 establishes that replacing hash tables with multi-dimensional arrays enables a 45x speedup path (27s → 0.6s). But that speedup requires JAX/GPU execution, and we absolutely cannot expose JAX complexity to actuaries.

**Actuaries are domain experts, not ML engineers.** They should focus on:
- Mortality assumptions
- Lapse rates
- Policy cash flows
- Regulatory calculations

**Not on:**
- `jax.device_put()`
- `jax.lax.scan()`
- GPU memory management
- Tensor shapes and broadcasting

### The Challenge

Current architecture is tightly coupled to Polars:

```
┌─────────────────────────────────────────────────────────┐
│  Actuarial DSL                                          │
│  af.x = table.lookup(...)                               │
│  af.y = af.x * af.z                                     │
└─────────────────────┬───────────────────────────────────┘
                      │ Directly creates
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Polars LazyFrame                                       │
│  pl.col("x"), pl.when(...), etc.                       │
└─────────────────────┬───────────────────────────────────┘
                      │ Executes via
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Rust Plugins (assumptions, vectors)                    │
└─────────────────────────────────────────────────────────┘
```

To add JAX, we need an abstraction layer:

```
┌─────────────────────────────────────────────────────────┐
│  Actuarial DSL (unchanged)                              │
│  af.x = table.lookup(...)                               │
│  af.y = af.x * af.z                                     │
└─────────────────────┬───────────────────────────────────┘
                      │ Creates
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Expression Tree (backend-agnostic)                     │
│  LookupExpr, BinaryOpExpr, TimeExpandExpr, etc.        │
└─────────────────────┬───────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
┌─────────────────┐     ┌─────────────────┐
│  Polars Backend │     │  JAX Backend    │
│  (CPU)          │     │  (GPU)          │
└─────────────────┘     └─────────────────┘
```

---

## Architecture Overview

### Core Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ACTUARIAL DSL LAYER                              │
│  ─────────────────────────────────────────                              │
│  ActuarialFrame, Table.lookup(), time_expand(), collect()               │
│  (What actuaries interact with - NO CHANGES)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        EXPRESSION LAYER                                 │
│  ─────────────────────────────────────────                              │
│  ExpressionTree: captures computation graph                             │
│  Expr nodes: LookupExpr, ArithmeticExpr, AggregateExpr, etc.           │
│  (Backend-agnostic intermediate representation)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│      POLARS BACKEND           │   │        JAX BACKEND            │
│  ─────────────────────────    │   │  ─────────────────────────    │
│  • Converts Expr → pl.Expr    │   │  • Converts Expr → JAX ops    │
│  • Uses Rust plugins          │   │  • Compiles to XLA            │
│  • Executes on CPU            │   │  • Executes on GPU            │
│  • Returns pl.DataFrame       │   │  • Returns pl.DataFrame       │
└───────────────────────────────┘   └───────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **ActuarialFrame** | DSL entry point, builds expression tree, delegates to backend |
| **ExpressionTree** | Captures all operations as a directed acyclic graph (DAG) |
| **Expr (base class)** | Abstract node in the computation graph |
| **BackendRegistry** | Discovers and selects appropriate backend |
| **PolarsBackend** | Converts expression tree to Polars lazy operations |
| **JaxBackend** | Compiles expression tree to JAX, executes on GPU |

---

## Expression Tree Design

### Base Expression Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class Expr(ABC):
    """Base class for all expressions in the computation graph."""

    # Unique identifier for this expression
    id: str

    # Data type of the result (inferred or explicit)
    dtype: str | None = None

    @abstractmethod
    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        """Convert this expression to a Polars expression."""
        ...

    @abstractmethod
    def to_jax(self, ctx: JaxContext) -> JaxExpr:
        """Convert this expression to JAX operations."""
        ...

    def __add__(self, other): return BinaryOpExpr("+", self, other)
    def __mul__(self, other): return BinaryOpExpr("*", self, other)
    def __sub__(self, other): return BinaryOpExpr("-", self, other)
    def __truediv__(self, other): return BinaryOpExpr("/", self, other)
    # ... etc
```

### Expression Types

```python
@dataclass
class ColumnExpr(Expr):
    """Reference to a column in the model points."""
    column_name: str

    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        return pl.col(self.column_name)

    def to_jax(self, ctx: JaxContext) -> jnp.ndarray:
        return ctx.model_points[self.column_name]


@dataclass
class LiteralExpr(Expr):
    """A constant value."""
    value: float | int | str

    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        return pl.lit(self.value)

    def to_jax(self, ctx: JaxContext) -> jnp.ndarray:
        return jnp.full(ctx.batch_size, self.value)


@dataclass
class BinaryOpExpr(Expr):
    """Binary operation: +, -, *, /, etc."""
    op: str
    left: Expr
    right: Expr

    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        left = self.left.to_polars(ctx)
        right = self.right.to_polars(ctx)
        return {
            "+": left + right,
            "-": left - right,
            "*": left * right,
            "/": left / right,
        }[self.op]

    def to_jax(self, ctx: JaxContext) -> jnp.ndarray:
        left = self.left.to_jax(ctx)
        right = self.right.to_jax(ctx)
        return {
            "+": jnp.add,
            "-": jnp.subtract,
            "*": jnp.multiply,
            "/": jnp.divide,
        }[self.op](left, right)


@dataclass
class LookupExpr(Expr):
    """Assumption table lookup."""
    table: "Table"
    keys: dict[str, Expr]

    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        # Current implementation: Polars plugin
        key_exprs = {k: v.to_polars(ctx) for k, v in self.keys.items()}
        return self.table._polars_lookup(**key_exprs)

    def to_jax(self, ctx: JaxContext) -> jnp.ndarray:
        # New implementation: Array indexing
        # 1. Get the dense array for this table
        array = ctx.gpu_tables[self.table.name]

        # 2. Encode keys to indices
        indices = []
        for key_name, key_expr in self.keys.items():
            key_values = key_expr.to_jax(ctx)
            encoder = ctx.encoders[self.table.name][key_name]
            indices.append(encoder.encode_jax(key_values))

        # 3. Compute linear index
        linear_idx = sum(
            idx * stride
            for idx, stride in zip(indices, self.table.strides)
        )

        # 4. Gather from array
        return jnp.take(array.ravel(), linear_idx)


@dataclass
class ConditionalExpr(Expr):
    """If-then-else expression."""
    condition: Expr
    then_expr: Expr
    else_expr: Expr

    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        return pl.when(self.condition.to_polars(ctx)).then(
            self.then_expr.to_polars(ctx)
        ).otherwise(
            self.else_expr.to_polars(ctx)
        )

    def to_jax(self, ctx: JaxContext) -> jnp.ndarray:
        return jnp.where(
            self.condition.to_jax(ctx),
            self.then_expr.to_jax(ctx),
            self.else_expr.to_jax(ctx)
        )


@dataclass
class ClipExpr(Expr):
    """Clip values to a range."""
    expr: Expr
    lower: float | None = None
    upper: float | None = None

    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        result = self.expr.to_polars(ctx)
        if self.lower is not None:
            result = result.clip(lower_bound=self.lower)
        if self.upper is not None:
            result = result.clip(upper_bound=self.upper)
        return result

    def to_jax(self, ctx: JaxContext) -> jnp.ndarray:
        return jnp.clip(
            self.expr.to_jax(ctx),
            self.lower if self.lower is not None else -jnp.inf,
            self.upper if self.upper is not None else jnp.inf
        )


@dataclass
class AggregateExpr(Expr):
    """Aggregation: sum, mean, etc."""
    op: str  # "sum", "mean", "min", "max"
    expr: Expr
    group_by: list[str] | None = None

    def to_polars(self, ctx: PolarsContext) -> pl.Expr:
        base = self.expr.to_polars(ctx)
        agg_fn = getattr(base, self.op)
        if self.group_by:
            return agg_fn().over(self.group_by)
        return agg_fn()

    def to_jax(self, ctx: JaxContext) -> jnp.ndarray:
        values = self.expr.to_jax(ctx)
        if self.group_by:
            # Segment-based aggregation for grouped ops
            return ctx.segment_aggregate(values, self.op, self.group_by)
        return getattr(jnp, self.op)(values)
```

### Time Expansion Expression

```python
@dataclass
class TimeExpandExpr(Expr):
    """Expand model points across timesteps."""
    base: Expr
    n_timesteps: int
    time_column: str = "t"

    def to_polars(self, ctx: PolarsContext) -> pl.LazyFrame:
        # Current implementation: cross join with time series
        base_lf = self.base.to_polars(ctx)
        time_df = pl.DataFrame({self.time_column: range(self.n_timesteps)})
        return base_lf.join(time_df.lazy(), how="cross")

    def to_jax(self, ctx: JaxContext) -> JaxTimeExpandedContext:
        # For JAX, we don't actually expand - we use scan
        # This returns a context that will be used by jax.lax.scan
        return JaxTimeExpandedContext(
            base_ctx=ctx,
            n_timesteps=self.n_timesteps
        )
```

---

## Expression Tree Builder

### The ActuarialFrame Interface

```python
class ActuarialFrame:
    """
    The primary interface for actuaries.

    Builds an expression tree from operations, then executes
    on the appropriate backend at collect() time.
    """

    def __init__(
        self,
        model_points: pl.DataFrame | pl.LazyFrame,
        tables: dict[str, Table] | None = None,
    ):
        self._model_points = model_points
        self._tables = tables or {}
        self._columns: dict[str, Expr] = {}
        self._expr_tree = ExpressionTree()

        # Initialize column references for model point columns
        for col in model_points.columns:
            self._columns[col] = ColumnExpr(id=col, column_name=col)

    def __getattr__(self, name: str) -> Expr:
        """Access a column or computed expression."""
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._columns:
            raise AttributeError(f"Column '{name}' not found")
        return self._columns[name]

    def __setattr__(self, name: str, value: Expr | float | int):
        """Define a new computed column."""
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        if isinstance(value, (int, float)):
            value = LiteralExpr(id=f"lit_{name}", value=value)
        elif not isinstance(value, Expr):
            raise TypeError(f"Expected Expr, got {type(value)}")

        self._columns[name] = value
        self._expr_tree.add_output(name, value)

    def time_expand(self, n_timesteps: int, time_column: str = "t") -> "ActuarialFrame":
        """Expand the frame across timesteps."""
        # Create new frame with time expansion marker
        expanded = ActuarialFrame.__new__(ActuarialFrame)
        expanded._model_points = self._model_points
        expanded._tables = self._tables
        expanded._columns = self._columns.copy()
        expanded._expr_tree = self._expr_tree.with_time_expansion(n_timesteps, time_column)

        # Add time column
        expanded._columns[time_column] = ColumnExpr(id=time_column, column_name=time_column)
        expanded._columns["duration"] = BinaryOpExpr(
            id="duration",
            op="+",
            left=expanded._columns.get("duration_at_entry", LiteralExpr(id="zero", value=0)),
            right=expanded._columns[time_column]
        )

        return expanded

    def collect(self, backend: str = "auto") -> pl.DataFrame:
        """
        Execute the expression tree and return results.

        Args:
            backend: "auto", "polars", or "jax"
                - "auto": Choose based on data size and GPU availability
                - "polars": Force CPU execution via Polars
                - "jax": Force GPU execution via JAX

        Returns:
            pl.DataFrame with all computed columns
        """
        if backend == "auto":
            backend = self._select_backend()

        executor = BackendRegistry.get(backend)
        return executor.execute(
            expr_tree=self._expr_tree,
            model_points=self._model_points,
            tables=self._tables
        )

    def _select_backend(self) -> str:
        """Automatically select the best backend."""
        # Estimate total operations
        n_rows = self._estimate_rows()
        has_gpu = self._check_gpu_available()

        # Heuristics
        if has_gpu and n_rows > 1_000_000:
            return "jax"
        return "polars"

    def _estimate_rows(self) -> int:
        """Estimate total rows after time expansion."""
        base_rows = (
            self._model_points.select(pl.len()).collect().item()
            if isinstance(self._model_points, pl.LazyFrame)
            else len(self._model_points)
        )
        time_expansion = self._expr_tree.time_expansion_factor or 1
        return base_rows * time_expansion

    def _check_gpu_available(self) -> bool:
        """Check if JAX GPU backend is available."""
        try:
            import jax
            return len(jax.devices("gpu")) > 0
        except Exception:
            return False
```

---

## Backend Implementations

### Backend Registry

```python
class BackendRegistry:
    """Registry of available execution backends."""

    _backends: dict[str, "Backend"] = {}

    @classmethod
    def register(cls, name: str, backend: "Backend"):
        cls._backends[name] = backend

    @classmethod
    def get(cls, name: str) -> "Backend":
        if name not in cls._backends:
            raise ValueError(f"Unknown backend: {name}. Available: {list(cls._backends.keys())}")
        return cls._backends[name]

    @classmethod
    def available(cls) -> list[str]:
        return list(cls._backends.keys())


class Backend(ABC):
    """Abstract base class for execution backends."""

    @abstractmethod
    def execute(
        self,
        expr_tree: ExpressionTree,
        model_points: pl.DataFrame | pl.LazyFrame,
        tables: dict[str, Table],
    ) -> pl.DataFrame:
        """Execute the expression tree and return results."""
        ...
```

### Polars Backend (Current Implementation)

```python
class PolarsBackend(Backend):
    """Execute expression tree using Polars (CPU)."""

    def execute(
        self,
        expr_tree: ExpressionTree,
        model_points: pl.DataFrame | pl.LazyFrame,
        tables: dict[str, Table],
    ) -> pl.DataFrame:
        ctx = PolarsContext(tables=tables)

        # Start with model points
        lf = model_points.lazy() if isinstance(model_points, pl.DataFrame) else model_points

        # Apply time expansion if needed
        if expr_tree.time_expansion:
            n_timesteps, time_col = expr_tree.time_expansion
            time_df = pl.DataFrame({time_col: range(n_timesteps)})
            lf = lf.join(time_df.lazy(), how="cross")

        # Build all output columns
        output_exprs = []
        for name, expr in expr_tree.outputs.items():
            output_exprs.append(expr.to_polars(ctx).alias(name))

        # Execute
        return lf.with_columns(output_exprs).collect()


# Register the Polars backend
BackendRegistry.register("polars", PolarsBackend())
```

### JAX Backend (New Implementation)

```python
class JaxBackend(Backend):
    """Execute expression tree using JAX (GPU)."""

    def execute(
        self,
        expr_tree: ExpressionTree,
        model_points: pl.DataFrame | pl.LazyFrame,
        tables: dict[str, Table],
    ) -> pl.DataFrame:
        import jax
        import jax.numpy as jnp
        from functools import partial

        # 1. Prepare GPU-resident tables
        gpu_tables = self._prepare_tables(tables)

        # 2. Prepare encoders for string columns
        encoders = self._prepare_encoders(tables)

        # 3. Encode model points
        mp_df = model_points.collect() if isinstance(model_points, pl.LazyFrame) else model_points
        encoded_mp = self._encode_model_points(mp_df, encoders)

        # 4. Compile expression tree to JAX function
        compute_fn = self._compile_expressions(expr_tree, gpu_tables, encoders)

        # 5. Execute
        if expr_tree.time_expansion:
            n_timesteps, _ = expr_tree.time_expansion
            results = self._execute_with_time_loop(
                compute_fn, encoded_mp, gpu_tables, n_timesteps
            )
        else:
            results = self._execute_single(compute_fn, encoded_mp, gpu_tables)

        # 6. Convert back to Polars DataFrame
        return self._results_to_polars(results, mp_df, expr_tree)

    def _prepare_tables(self, tables: dict[str, Table]) -> dict[str, jnp.ndarray]:
        """Upload assumption tables to GPU as dense arrays."""
        import jax

        gpu_tables = {}
        for name, table in tables.items():
            dense_array = table.to_dense_array()  # From RFC 29 Strategy 5
            gpu_tables[name] = jax.device_put(dense_array)

        return gpu_tables

    def _prepare_encoders(self, tables: dict[str, Table]) -> dict[str, dict[str, KeyEncoder]]:
        """Get key encoders for each table."""
        return {
            name: table.get_key_encoders()
            for name, table in tables.items()
        }

    def _encode_model_points(
        self,
        mp_df: pl.DataFrame,
        encoders: dict[str, dict[str, KeyEncoder]]
    ) -> dict[str, jnp.ndarray]:
        """Convert model points to GPU-friendly format."""
        import jax.numpy as jnp

        encoded = {}

        for col in mp_df.columns:
            series = mp_df[col]

            # Check if this column needs encoding (is it a key for any table?)
            encoder = self._find_encoder_for_column(col, encoders)

            if encoder is not None:
                # Encode string → index
                encoded[col] = jnp.array(encoder.encode(series))
            elif series.dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
                # Numeric column - direct copy
                encoded[col] = jnp.array(series.to_numpy())
            else:
                # String column not used as key - skip for now
                # (or encode to categorical if needed)
                pass

        return encoded

    def _compile_expressions(
        self,
        expr_tree: ExpressionTree,
        gpu_tables: dict[str, jnp.ndarray],
        encoders: dict[str, dict[str, KeyEncoder]]
    ):
        """Compile expression tree to a JAX function."""
        import jax

        def compute_outputs(mp_data: dict, tables: dict, t: int | None = None):
            """Compute all output columns for given inputs."""
            ctx = JaxContext(
                model_points=mp_data,
                gpu_tables=tables,
                encoders=encoders,
                current_t=t
            )

            outputs = {}
            for name, expr in expr_tree.outputs.items():
                outputs[name] = expr.to_jax(ctx)

            return outputs

        return compute_outputs

    def _execute_with_time_loop(
        self,
        compute_fn,
        encoded_mp: dict[str, jnp.ndarray],
        gpu_tables: dict[str, jnp.ndarray],
        n_timesteps: int
    ) -> dict[str, jnp.ndarray]:
        """Execute with time loop using jax.lax.scan."""
        import jax
        import jax.numpy as jnp

        n_policies = next(iter(encoded_mp.values())).shape[0]

        @jax.jit
        def run_projection(mp_data, tables):
            def step(carry, t):
                # Add current timestep to context
                mp_with_t = {**mp_data, "t": jnp.full(n_policies, t)}

                # Compute duration from t
                if "duration_at_entry" in mp_data:
                    mp_with_t["duration"] = mp_data["duration_at_entry"] + t
                else:
                    mp_with_t["duration"] = jnp.full(n_policies, t)

                outputs = compute_fn(mp_with_t, tables, t)
                return carry, outputs

            _, all_outputs = jax.lax.scan(
                step,
                init=None,
                xs=jnp.arange(n_timesteps)
            )

            return all_outputs

        return run_projection(encoded_mp, gpu_tables)

    def _execute_single(
        self,
        compute_fn,
        encoded_mp: dict[str, jnp.ndarray],
        gpu_tables: dict[str, jnp.ndarray]
    ) -> dict[str, jnp.ndarray]:
        """Execute without time loop."""
        import jax

        @jax.jit
        def run(mp_data, tables):
            return compute_fn(mp_data, tables)

        return run(encoded_mp, gpu_tables)

    def _results_to_polars(
        self,
        results: dict[str, jnp.ndarray],
        original_mp: pl.DataFrame,
        expr_tree: ExpressionTree
    ) -> pl.DataFrame:
        """Convert JAX results back to Polars DataFrame."""
        import jax

        # Transfer from GPU to CPU
        cpu_results = jax.device_get(results)

        # Handle time-expanded results
        if expr_tree.time_expansion:
            n_timesteps, time_col = expr_tree.time_expansion
            n_policies = len(original_mp)

            # Results are shape [n_timesteps, n_policies]
            # Need to flatten and add time column
            data = {time_col: np.tile(np.arange(n_timesteps), n_policies)}

            # Tile original model point columns
            for col in original_mp.columns:
                data[col] = np.repeat(original_mp[col].to_numpy(), n_timesteps)

            # Add computed columns
            for name, arr in cpu_results.items():
                # arr is [n_timesteps, n_policies], need [n_policies * n_timesteps]
                data[name] = arr.T.ravel()

            return pl.DataFrame(data)
        else:
            # Simple case - just add computed columns
            data = {col: original_mp[col] for col in original_mp.columns}
            for name, arr in cpu_results.items():
                data[name] = arr

            return pl.DataFrame(data)


# Register the JAX backend (conditionally)
try:
    import jax
    BackendRegistry.register("jax", JaxBackend())
except ImportError:
    pass  # JAX not installed, backend not available
```

---

## Key Encoder System

### Encoder Interface

```python
class KeyEncoder(ABC):
    """Encodes column values to array indices."""

    @abstractmethod
    def encode(self, series: pl.Series) -> np.ndarray:
        """Encode a Polars series to integer indices."""
        ...

    @abstractmethod
    def encode_jax(self, arr: jnp.ndarray) -> jnp.ndarray:
        """Encode JAX array (for values already on GPU)."""
        ...

    @property
    @abstractmethod
    def size(self) -> int:
        """Number of unique values (array dimension size)."""
        ...


class IntRangeEncoder(KeyEncoder):
    """Encoder for integer columns with known range."""

    def __init__(self, min_val: int, max_val: int):
        self.min_val = min_val
        self.max_val = max_val
        self._size = max_val - min_val + 1

    def encode(self, series: pl.Series) -> np.ndarray:
        return (series.to_numpy() - self.min_val).astype(np.int32)

    def encode_jax(self, arr: jnp.ndarray) -> jnp.ndarray:
        return (arr - self.min_val).astype(jnp.int32)

    @property
    def size(self) -> int:
        return self._size


class DictionaryEncoder(KeyEncoder):
    """Encoder for string columns via dictionary lookup."""

    def __init__(self, values: list[str]):
        self.value_to_idx = {v: i for i, v in enumerate(values)}
        self._size = len(values)

        # Pre-compute for Polars categorical optimization
        self._categorical_mapping = None

    def encode(self, series: pl.Series) -> np.ndarray:
        # Fast path: if series is categorical with matching encoding
        if series.dtype == pl.Categorical:
            return series.to_physical().to_numpy().astype(np.int32)

        # Slow path: lookup each value
        return np.array([
            self.value_to_idx.get(v, -1)
            for v in series.to_list()
        ], dtype=np.int32)

    def encode_jax(self, arr: jnp.ndarray) -> jnp.ndarray:
        # Values should already be encoded before hitting JAX
        return arr.astype(jnp.int32)

    @property
    def size(self) -> int:
        return self._size


class CategoricalEncoder(KeyEncoder):
    """Encoder for Polars categorical columns - uses physical values directly."""

    def __init__(self, n_categories: int):
        self._size = n_categories

    def encode(self, series: pl.Series) -> np.ndarray:
        if series.dtype != pl.Categorical:
            raise TypeError(f"Expected Categorical, got {series.dtype}")
        return series.to_physical().to_numpy().astype(np.int32)

    def encode_jax(self, arr: jnp.ndarray) -> jnp.ndarray:
        return arr.astype(jnp.int32)

    @property
    def size(self) -> int:
        return self._size
```

---

## Table Integration

### Updated Table Class

```python
class Table:
    """
    Assumption table with multi-backend support.

    Supports both Polars (hash-based) and JAX (array-based) lookups
    through a unified interface.
    """

    def __init__(
        self,
        df: pl.DataFrame,
        keys: list[str],
        value_column: str,
    ):
        self.df = df
        self.keys = keys
        self.value_column = value_column
        self.name = None  # Set when registered

        # Build encoders for each key column
        self._encoders = self._build_encoders()

        # Build dense array for array-based backends
        self._dense_array = None
        self._strides = None

    def _build_encoders(self) -> dict[str, KeyEncoder]:
        """Build key encoders based on column types and values."""
        encoders = {}

        for key in self.keys:
            col = self.df[key]

            if col.dtype == pl.Categorical:
                encoders[key] = CategoricalEncoder(col.n_unique())
            elif col.dtype in [pl.Int64, pl.Int32]:
                min_val = col.min()
                max_val = col.max()
                encoders[key] = IntRangeEncoder(min_val, max_val)
            elif col.dtype == pl.Utf8:
                unique_vals = col.unique().sort().to_list()
                encoders[key] = DictionaryEncoder(unique_vals)
            else:
                raise TypeError(f"Unsupported key type: {col.dtype}")

        return encoders

    def to_dense_array(self) -> np.ndarray:
        """Convert table to dense multi-dimensional array."""
        if self._dense_array is not None:
            return self._dense_array

        # Compute dimensions
        dims = [self._encoders[key].size for key in self.keys]
        total_size = np.prod(dims)

        # Compute strides
        self._strides = []
        stride = 1
        for dim in reversed(dims):
            self._strides.insert(0, stride)
            stride *= dim

        # Allocate array with NaN default
        self._dense_array = np.full(total_size, np.nan, dtype=np.float64)

        # Fill from DataFrame
        for row in self.df.iter_rows(named=True):
            # Compute linear index
            linear_idx = 0
            for key, stride in zip(self.keys, self._strides):
                key_val = row[key]
                encoder = self._encoders[key]
                if isinstance(encoder, DictionaryEncoder):
                    idx = encoder.value_to_idx[key_val]
                else:
                    idx = key_val - encoder.min_val
                linear_idx += idx * stride

            self._dense_array[linear_idx] = row[self.value_column]

        return self._dense_array

    def get_key_encoders(self) -> dict[str, KeyEncoder]:
        """Get encoders for each key column."""
        return self._encoders

    @property
    def strides(self) -> list[int]:
        """Get strides for linear index computation."""
        if self._strides is None:
            self.to_dense_array()  # Compute strides as side effect
        return self._strides

    def lookup(self, **keys: Expr) -> LookupExpr:
        """
        Create a lookup expression.

        This is what actuaries call - returns an Expr that can be
        evaluated by any backend.
        """
        return LookupExpr(
            id=f"lookup_{self.name}_{id(keys)}",
            table=self,
            keys=keys
        )
```

---

## Usage Examples

### Basic Usage (Unchanged for Actuaries)

```python
# Load data
model_points = pl.read_parquet("model_points.parquet")

# Load tables
mortality = Table.from_csv("mortality.csv", keys=["table_id", "age", "duration"], value="rate")
lapse = Table.from_csv("lapse.csv", keys=["lapse_id", "duration"], value="rate")

# Create frame
af = ActuarialFrame(model_points, tables={"mortality": mortality, "lapse": lapse})

# Define calculations (EXACTLY AS TODAY)
af.base_mort_rate = mortality.lookup(
    table_id=af.mort_table_id,
    age=af.age_at_entry,
    duration=af.duration
)
af.base_lapse_rate = lapse.lookup(
    lapse_id=af.lapse_id,
    duration=af.duration.clip(upper=14)
)
af.qx = af.base_mort_rate * af.mort_scalar
af.wx = af.base_lapse_rate * af.lapse_scalar
af.total_decrement = af.qx + af.wx * (1 - af.qx)

# Execute - backend chosen automatically!
result = af.collect()

# Or explicitly choose backend:
result_cpu = af.collect(backend="polars")
result_gpu = af.collect(backend="jax")
```

### Time-Expanded Model (Unchanged)

```python
af = ActuarialFrame(model_points, tables=tables)

# Expand across 180 months
af = af.time_expand(n_timesteps=180)

# Duration now varies with t
af.duration_capped = af.duration.clip(upper=24)

# Lookups work the same
af.mort_rate = mortality.lookup(
    table_id=af.mort_table_id,
    age=af.age_at_entry + af.duration,
    duration=af.duration_capped
)

# Calculations
af.deaths = af.mort_rate * af.lives
af.lapses = af.lapse_rate * (af.lives - af.deaths)
af.end_lives = af.lives - af.deaths - af.lapses

# Collect - framework handles time loop appropriately per backend
result = af.collect()
```

### Checking Backend Selection

```python
# See what backend would be chosen
af = ActuarialFrame(model_points, tables=tables)
af = af.time_expand(180)

print(f"Estimated rows: {af._estimate_rows():,}")
print(f"GPU available: {af._check_gpu_available()}")
print(f"Selected backend: {af._select_backend()}")

# Output:
# Estimated rows: 54,000,000
# GPU available: True
# Selected backend: jax
```

---

## Migration Path

### Phase 1: Expression Tree Refactor

**Goal**: Decouple DSL from Polars without changing behavior

1. Introduce `Expr` base class and expression types
2. Refactor `ActuarialFrame` to build expression tree
3. Implement `PolarsBackend` that converts tree → current behavior
4. **All existing tests pass unchanged**

### Phase 2: JAX Backend

**Goal**: Add GPU execution path

1. Implement `JaxBackend`
2. Add `Table.to_dense_array()` (from RFC 29 Strategy 5)
3. Implement key encoders
4. Add `backend="jax"` option to `collect()`
5. **New GPU benchmarks pass**

### Phase 3: Auto-Selection

**Goal**: Transparent backend selection

1. Implement `_select_backend()` heuristics
2. Set `backend="auto"` as default
3. Add logging/observability for backend selection
4. **Users get GPU acceleration without code changes**

### Phase 4: Optimization

**Goal**: Maximize GPU performance

1. Kernel fusion for common patterns
2. Memory optimization (streaming large models)
3. Multi-GPU support
4. JIT compilation caching

---

## Open Questions

1. **Expression tree completeness**: What DSL operations need Expr implementations?
   - All arithmetic: +, -, *, /, **, %
   - Comparisons: <, >, <=, >=, ==, !=
   - Logical: and, or, not
   - Aggregations: sum, mean, min, max, count
   - Window functions: cumsum, shift, diff
   - Conditionals: if/then/else

2. **State between timesteps**: How do we handle stateful calculations?
   - `af.lives` depends on previous timestep's deaths/lapses
   - Need to track which columns are "state" vs "output"
   - JAX `scan` carry mechanism handles this

3. **Debugging**: How do actuaries debug when backend is transparent?
   - Add `af.collect(backend="polars", debug=True)` for step-through
   - Logging of backend selection and performance
   - Ability to compare results across backends

4. **Partial GPU**: What if some operations can't be GPU-accelerated?
   - Sparse table lookups (Strategy 6b)
   - Complex string operations
   - External API calls

5. **Testing**: How do we ensure backends produce identical results?
   - Property-based testing with random inputs
   - Numerical tolerance for floating point
   - Regression test suite

---

## References

- [RFC 29: Assumption Lookup Performance](./29-lookup-performance-rfc.md)
- [JAX Documentation](https://jax.readthedocs.io/)
- [Polars Lazy API](https://pola-rs.github.io/polars/py-polars/html/reference/lazyframe/)
- [XLA Compilation](https://www.tensorflow.org/xla)
