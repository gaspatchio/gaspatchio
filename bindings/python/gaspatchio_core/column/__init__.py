"""Column submodule, providing proxy classes for interacting with Polars expressions."""

# Import the proxy classes from their respective modules
from .column_proxy import ColumnProxy

# Import the autopatching function
from .dispatch import _autopatch
from .expression_proxy import ExpressionProxy

# Apply the autopatching logic to add Polars methods dynamically
# This must happen after the classes are defined and imported.
_autopatch(ColumnProxy)
_autopatch(ExpressionProxy)

# Define the public API for this submodule
__all__ = ["ColumnProxy", "ExpressionProxy"]
