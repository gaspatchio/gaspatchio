"""Type stubs for gaspatchio_core.column submodule."""

# Re-export the proxy classes from their specific modules
from .column_proxy import ColumnProxy as ColumnProxy
from .expression_proxy import ExpressionProxy as ExpressionProxy

# The _autopatch function is internal and typically not part of the public stub

__all__ = ["ColumnProxy", "ExpressionProxy"]
