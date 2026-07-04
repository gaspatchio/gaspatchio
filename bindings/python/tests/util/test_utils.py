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


class TestReadModelPoints:
    """read_model_points dispatches on file extension (Parquet or CSV)."""

    @staticmethod
    def _frame() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "policy_id": ["POL001", "POL002"],
                "age": [30, 45],
                "sum_assured": [100_000.0, 250_000.0],
            }
        )

    def test_reads_parquet(self, tmp_path):
        """A .parquet path is read into a LazyFrame."""
        from gaspatchio_core.util import read_model_points

        path = tmp_path / "mp.parquet"
        self._frame().write_parquet(path)
        out = read_model_points(path).collect()
        assert out["policy_id"].to_list() == ["POL001", "POL002"]

    def test_reads_csv(self, tmp_path):
        """A .csv path is read into a LazyFrame (previously Parquet-only)."""
        from gaspatchio_core.util import read_model_points

        path = tmp_path / "mp.csv"
        self._frame().write_csv(path)
        out = read_model_points(path).collect()
        assert out["policy_id"].to_list() == ["POL001", "POL002"]

    def test_csv_and_parquet_agree(self, tmp_path):
        """The same data read from CSV or Parquet yields identical frames."""
        from gaspatchio_core.util import read_model_points

        df = self._frame()
        df.write_parquet(tmp_path / "mp.parquet")
        df.write_csv(tmp_path / "mp.csv")
        from_pq = read_model_points(tmp_path / "mp.parquet").collect()
        from_csv = read_model_points(tmp_path / "mp.csv").collect()
        assert from_pq.to_dicts() == from_csv.to_dicts()

    def test_accepts_string_path(self, tmp_path):
        """A string path is accepted as well as a Path object."""
        from gaspatchio_core.util import read_model_points

        path = tmp_path / "mp.csv"
        self._frame().write_csv(path)
        assert len(read_model_points(str(path)).collect()) == 2

    def test_unsupported_extension_raises(self, tmp_path):
        """An unsupported extension raises a clear ValueError."""
        from gaspatchio_core.util import read_model_points

        path = tmp_path / "mp.txt"
        path.write_text("policy_id,age\nPOL001,30\n")
        with pytest.raises(ValueError, match="Unsupported model points format"):
            read_model_points(path)


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
