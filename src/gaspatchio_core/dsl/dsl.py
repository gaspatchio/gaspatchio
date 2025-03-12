from __future__ import annotations

import ast
import inspect
from typing import Any, Callable, Dict, Optional

import polars as pl
from gaspatchio_core.plugin import fill_series, floor


class PolarVar:
    """A variable representing a Polars column or computation."""

    def __init__(self, value: Any):
        if isinstance(value, PolarVar):
            self.expr = value.expr
        elif isinstance(value, pl.Expr):
            self.expr = value
        elif isinstance(value, (int, float, str, bool)):
            self.expr = pl.lit(value)
        else:
            self.expr = value

    def __add__(self, other):
        return PolarVar(self.expr + _to_expr(other))

    def __radd__(self, other):
        return PolarVar(_to_expr(other) + self.expr)

    def __sub__(self, other):
        return PolarVar(self.expr - _to_expr(other))

    def __rsub__(self, other):
        return PolarVar(_to_expr(other) - self.expr)

    def __mul__(self, other):
        return PolarVar(self.expr * _to_expr(other))

    def __rmul__(self, other):
        return PolarVar(_to_expr(other) * self.expr)

    def __truediv__(self, other):
        return PolarVar(self.expr / _to_expr(other))

    def __rtruediv__(self, other):
        return PolarVar(_to_expr(other) / self.expr)

    def __floordiv__(self, other):
        return PolarVar(self.expr.floordiv(_to_expr(other)))

    def __rfloordiv__(self, other):
        return PolarVar(_to_expr(other).floordiv(self.expr))

    def __neg__(self):
        return PolarVar(-self.expr)

    def __pos__(self):
        return self

    def __lt__(self, other):
        return PolarVar(self.expr < _to_expr(other))

    def __le__(self, other):
        return PolarVar(self.expr <= _to_expr(other))

    def __gt__(self, other):
        return PolarVar(self.expr > _to_expr(other))

    def __ge__(self, other):
        return PolarVar(self.expr >= _to_expr(other))

    def __eq__(self, other):
        return PolarVar(self.expr == _to_expr(other))

    def __ne__(self, other):
        return PolarVar(self.expr != _to_expr(other))


def _to_expr(value: Any) -> pl.Expr:
    """Convert a value to a Polars expression."""
    if isinstance(value, PolarVar):
        return value.expr
    elif isinstance(value, pl.Expr):
        return value
    else:
        return pl.lit(value)


class ModelContext:
    """A context for executing model calculations with Polars."""

    def __init__(self, data: Optional[pl.LazyFrame] = None):
        self.data = data or pl.LazyFrame()
        self.variables: Dict[str, PolarVar] = {}
        self.results: Dict[str, Any] = {}

    def __getattr__(self, name: str) -> PolarVar:
        """Access a variable or column by name."""
        if name in self.variables:
            return self.variables[name]
        return PolarVar(pl.col(name))

    def __setattr__(self, name: str, value: Any):
        """Set a variable or column."""
        if name in ["data", "variables", "results"]:
            super().__setattr__(name, value)
        else:
            if isinstance(value, PolarVar):
                self.variables[name] = value
            else:
                self.variables[name] = PolarVar(value)

    def from_file(self, path: str) -> ModelContext:
        """Load data from a file."""
        if path.endswith(".parquet"):
            self.data = pl.scan_parquet(path)
        elif path.endswith(".csv"):
            self.data = pl.scan_csv(path, infer_schema_length=10000)
        else:
            raise ValueError(f"Unsupported file format: {path}")
        return self

    def from_df(self, df: pl.LazyFrame) -> ModelContext:
        """Use an existing DataFrame."""
        self.data = df
        return self

    def run(self, model_func: Callable):
        """Run the model function in this context."""
        source = inspect.getsource(model_func)
        tree = ast.parse(source)
        func_def = tree.body[0]

        # Create a locals dictionary for our executions
        locals_dict = {"self": self}

        # Extract the function body
        if isinstance(func_def, ast.FunctionDef):
            # Process each statement in the function body
            for stmt in func_def.body:
                if isinstance(stmt, ast.Assign):
                    # For assignment statements (var = value)
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            # Get the variable name
                            var_name = target.id

                            # Evaluate the right side of the assignment using our locals
                            value = eval(
                                compile(ast.Expression(stmt.value), "<string>", "eval"),
                                globals(),
                                {**locals_dict, **self._build_locals()},
                            )

                            # Store the value in our context and locals
                            if isinstance(value, (int, float, str, bool)):
                                # For scalar values, store directly
                                self.variables[var_name] = PolarVar(value)
                                locals_dict[var_name] = value
                            else:
                                # For expressions, store as PolarVar
                                self.variables[var_name] = value
                                locals_dict[var_name] = value

        # Apply all variables to the dataframe
        columns = {
            name: var.expr
            for name, var in self.variables.items()
            if not isinstance(var.expr, (int, float, str, bool))
        }
        self.data = self.data.with_columns(**columns)
        return self

    def _build_locals(self) -> Dict[str, Any]:
        """Build a dictionary of local variables for execution context."""
        # Include all variables and functions accessible in the model context
        return {
            **{name: var for name, var in self.variables.items()},
            "fill_series": self._wrap_func(fill_series),
            "floor": self._wrap_func(floor),
            "round_down": self._wrap_func(lambda x: floor(x)),  # Simplified round_down
        }

    def _wrap_func(self, func: Callable) -> Callable:
        """Wrap a Polars function to handle PolarVar arguments."""

        def wrapper(*args, **kwargs):
            # Convert PolarVar arguments to expressions
            new_args = [
                _to_expr(arg) if isinstance(arg, PolarVar) else arg for arg in args
            ]
            new_kwargs = {
                k: _to_expr(v) if isinstance(v, PolarVar) else v
                for k, v in kwargs.items()
            }
            # Call the original function with the converted arguments
            result = func(*new_args, **new_kwargs)
            # Wrap the result in a PolarVar
            return PolarVar(result)

        return wrapper

    def collect(self) -> pl.DataFrame:
        """Collect the results."""
        return self.data.collect()

    def result(self) -> pl.LazyFrame:
        """Return the lazy frame result."""
        return self.data


# Create helper functions for common operations
def col(name: str) -> PolarVar:
    """Create a column reference."""
    return PolarVar(pl.col(name))


# Re-export plugin functions with PolarVar wrapper
def p_fill_series(expr, start: int = 0, increment: int = 1) -> PolarVar:
    """Fill a series with sequential values."""
    return PolarVar(fill_series(_to_expr(expr), start, increment))


def p_floor(expr, divisor: int = 1, default: int = 0) -> PolarVar:
    """Floor division with a default value."""
    return PolarVar(floor(_to_expr(expr), divisor, default))


def p_round_down(expr) -> PolarVar:
    """Round down transformation."""
    return PolarVar(floor(_to_expr(expr)))


def run_model_function(model_func: Callable, data: pl.LazyFrame) -> pl.LazyFrame:
    """Run a model function on a dataframe."""
    context = ModelContext().from_df(data)
    return context.run(model_func).result()
