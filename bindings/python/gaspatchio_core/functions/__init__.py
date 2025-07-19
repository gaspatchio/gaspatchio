# functions/__init__.py

# Import and re-export wrapper functions from submodules
from .excel import yearfrac
from .vector import (
    fill_series,
    floor,
    round,
    round_to_int,
)

__all__ = [
    "fill_series",
    "floor",
    "round",
    "round_to_int",
    "yearfrac",
]
