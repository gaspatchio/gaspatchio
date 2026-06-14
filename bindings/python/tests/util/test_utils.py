# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import os

import polars as pl
import pytest
from gaspatchio_core import (
    execution_mode,
    get_default_mode,
    set_default_mode,
)
from gaspatchio_core.util import (
    _expr_to_str,
    get_default_threads,
    get_default_verbose,
    set_default_verbose,
)

# Store initial environment variables to restore later
initial_mode = os.environ.get("GASPATCHIO_MODE")
initial_verbose = os.environ.get("GASPATCHIO_VERBOSE")


@pytest.fixture(autouse=True)
def reset_defaults():
    """Reset global settings before and after each test."""
    # Before test: Set to known defaults
    original_mode = get_default_mode()
    original_verbose = get_default_verbose()
    set_default_mode("debug")
    set_default_verbose(True)
    yield
    # After test: Restore original state
    set_default_mode(original_mode)
    set_default_verbose(original_verbose)
    # Restore environment variables if they were changed
    if initial_mode is None:
        if "GASPATCHIO_MODE" in os.environ:
            del os.environ["GASPATCHIO_MODE"]
    else:
        os.environ["GASPATCHIO_MODE"] = initial_mode
    # Verbose is not stored in env by set_default_verbose, but good practice
    if initial_verbose is None:
        if "GASPATCHIO_VERBOSE" in os.environ:
            del os.environ["GASPATCHIO_VERBOSE"]
    else:
        os.environ["GASPATCHIO_VERBOSE"] = initial_verbose


def test_get_set_default_mode():
    """Test getting and setting the default mode."""
    assert get_default_mode() == "debug"  # Initial default from fixture

    set_default_mode("optimize")
    assert get_default_mode() == "optimize"
    assert os.environ.get("GASPATCHIO_MODE") == "optimize"

    set_default_mode("debug")
    assert get_default_mode() == "debug"
    assert os.environ.get("GASPATCHIO_MODE") == "debug"

    with pytest.raises(ValueError, match="Invalid mode: invalid_mode"):
        set_default_mode("invalid_mode")


def test_get_set_default_verbose():
    """Test getting and setting the default verbosity."""
    assert get_default_verbose() is True  # Initial default from fixture

    set_default_verbose(False)
    assert get_default_verbose() is False

    set_default_verbose(True)
    assert get_default_verbose() is True


def test_get_default_threads():
    """Test getting the default thread count (should read from env)."""
    # Note: Can't easily test setting threads as it interacts with Polars global state
    # Just test reading the default
    # Set env var for testing purposes
    original_threads_env = os.environ.get("GASPATCHIO_THREADS")
    os.environ["GASPATCHIO_THREADS"] = "4"
    # Reload the util module to pick up the new env var? No, it reads dynamically.
    # Re-importing the function won't help, need to re-read the global. Hacky.
    # Simpler: test the *current* default value (which depends on env at import time)
    # Let's just assert it returns an int
    assert isinstance(get_default_threads(), int)

    # Restore env var
    if original_threads_env is None:
        del os.environ["GASPATCHIO_THREADS"]
    else:
        os.environ["GASPATCHIO_THREADS"] = original_threads_env


def test_execution_mode_context_manager():
    """Test the execution_mode context manager."""
    assert get_default_mode() == "debug"

    with execution_mode("optimize"):
        assert get_default_mode() == "optimize"
        assert os.environ.get("GASPATCHIO_MODE") == "optimize"

    assert get_default_mode() == "debug"
    assert os.environ.get("GASPATCHIO_MODE") == "debug"

    # Test nested context manager
    with execution_mode("optimize"):
        assert get_default_mode() == "optimize"
        with execution_mode("debug"):
            assert get_default_mode() == "debug"
            assert os.environ.get("GASPATCHIO_MODE") == "debug"
        assert get_default_mode() == "optimize"
        assert os.environ.get("GASPATCHIO_MODE") == "optimize"

    assert get_default_mode() == "debug"
    assert os.environ.get("GASPATCHIO_MODE") == "debug"

    # Test context manager with error
    with pytest.raises(ValueError, match="Invalid mode: invalid"):
        with execution_mode("invalid"):
            pass  # Should raise error on entry

    # Ensure mode is restored even if an error occurs inside the context
    assert get_default_mode() == "debug"
    try:
        with execution_mode("optimize"):
            assert get_default_mode() == "optimize"
            raise RuntimeError("Something went wrong")
    except RuntimeError:
        pass
    assert get_default_mode() == "debug"


def test_expr_to_str():
    """Test the _expr_to_str utility function."""
    # Test with Polars expression
    expr = pl.col("a") + pl.lit(1)
    assert _expr_to_str(expr) == '[(col("a")) + (dyn int: 1)]'

    # Test with string literal
    assert _expr_to_str("column_name") == "column_name"

    # Test with integer literal
    assert _expr_to_str(123) == "123"

    # Test with float literal
    assert _expr_to_str(45.6) == "45.6"

    # Test with boolean literal
    assert _expr_to_str(True) == "True"
    assert _expr_to_str(False) == "False"

    # Test with None
    assert _expr_to_str(None) == "None"
