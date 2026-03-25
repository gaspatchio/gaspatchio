"""Type stubs for base accessors."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..frame.base import ActuarialFrame

class BaseFrameAccessor(ABC):
    _frame: "ActuarialFrame"
    @abstractmethod
    def __init__(self, frame: "ActuarialFrame") -> None: ...

class BaseColumnAccessor(ABC):
    _proxy: "ColumnProxy | ExpressionProxy | Any"
    @abstractmethod
    def __init__(self, proxy: "ColumnProxy | ExpressionProxy | Any") -> None: ...
