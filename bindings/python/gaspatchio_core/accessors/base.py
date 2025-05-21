"""Base classes for ActuarialFrame accessors."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    # Updated imports to point to new locations
    from ..column.proxy import ColumnProxy, ExpressionProxy  # Adjusted path
    from ..frame.base import ActuarialFrame  # Adjusted path


class BaseFrameAccessor(ABC):
    """Abstract base class for Frame-level accessors.

    Provides a structure for accessors that operate on the entire
    ActuarialFrame. Subclasses should implement domain-specific methods.
    """

    @abstractmethod
    def __init__(self, frame: "ActuarialFrame"):
        """Initialize the accessor with the parent frame.

        Args:
            frame: The ActuarialFrame instance this accessor is bound to.
        """
        self._frame = frame


class BaseColumnAccessor(ABC):
    """Abstract base class for Column/Expression-level accessors.

    Provides a structure for accessors that operate on a specific
    column or expression within an ActuarialFrame. Subclasses should
    implement domain-specific methods operating on `self._proxy`.
    """

    @abstractmethod
    def __init__(self, proxy: "ColumnProxy | ExpressionProxy | Any"):
        """Initialize the accessor with the parent proxy object.

        Args:
            proxy: The ColumnProxy or ExpressionProxy instance this
                   accessor is bound to. Using Any initially for flexibility,
                   will be refined.
        """
        self._proxy = proxy
