from __future__ import annotations

# ADDED: Import directly from Rust bindings temporarily
try:
    # Assuming functions are exposed via _internal, adjust if needed
    # These are the core Rust functions we are wrapping
    from gaspatchio_core._internal import (
        fill_series as core_fill_series,
    )
    from gaspatchio_core._internal import (
        floor as core_floor,
    )
    from gaspatchio_core._internal import (
        round as core_round,
    )
    from gaspatchio_core._internal import (
        round_to_int as core_round_to_int,
    )
except ImportError:
    print("Warning: Could not import core functions from Rust bindings.")

    # Define dummies or raise if bindings are missing during development/testing
    def core_fill_series(*args, **kwargs):
        raise NotImplementedError("Rust bindings missing or not found in _internal")

    def core_floor(*args, **kwargs):
        raise NotImplementedError("Rust bindings missing or not found in _internal")

    def core_round(*args, **kwargs):
        raise NotImplementedError("Rust bindings missing or not found in _internal")

    def core_round_to_int(*args, **kwargs):
        raise NotImplementedError("Rust bindings missing or not found in _internal")


# The Python wrapper functions (initially just re-exporting, could add logic later)
# These are the functions that ActuarialFrame will import and use.
fill_series = core_fill_series
floor = core_floor
round = core_round
round_to_int = core_round_to_int
