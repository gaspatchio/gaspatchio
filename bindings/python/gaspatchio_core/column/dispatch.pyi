"""Type stubs for dispatch.py."""

from typing import TYPE_CHECKING, Any, Callable, Optional, Set, Type, TypeAlias

# Use forward references for types defined elsewhere to avoid circular imports
if TYPE_CHECKING:
    from ..frame.base import ActuarialFrame
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    # Define a type alias for proxy types used in this module
    ProxyType: TypeAlias = ColumnProxy | ExpressionProxy

# Constants
_NUMERIC_UNARY: Set[str]
_NAMESPACES: Set[str]

# Helper Functions
def _unwrap(arg: Any) -> Any: ...
def _wrap(parent: Optional["ActuarialFrame"], result: Any) -> Any: ...

# Descriptor
class DelegatorDescriptor:
    name: str
    wrapper_logic: Callable[["ProxyType", ...], Any]

    def __init__(self, name: str) -> None: ...
    def __get__(
        self, instance: Optional["ProxyType"], owner: Optional[Type["ProxyType"]] = None
    ) -> Any: ...

# Wrapper Factory
def _make_wrapper(name: str) -> Callable[["ProxyType", ...], Any]: ...

# Autopatching Function
def _autopatch(proxy_cls: Type["ProxyType"]) -> None: ...
