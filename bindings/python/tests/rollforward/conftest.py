"""Skip rollforward tests when the Rust rollforward plugin isn't available.

The rollforward #[polars_expr] is registered in bindings/python/src/vector.rs,
but uv sync in CI doesn't always rebuild the Rust extension. When the cached
.so doesn't include the rollforward symbol, tests fail with:
  NameError: name 'LIB' is not defined

This skip is intentional — the rollforward tests pass locally after
`maturin develop -uv`. Once the rollforward feature merges to main and
the CI cache rebuilds, this skip can be removed.
"""

import pytest


def _rollforward_available() -> bool:
    """Check if the rollforward Rust plugin function is available."""
    try:
        from gaspatchio_core.functions.vector import rollforward_plugin  # noqa: F401

        return True
    except (ImportError, NameError):
        return False


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip rollforward kernel tests if the plugin is not available."""
    if _rollforward_available():
        return

    skip_marker = pytest.mark.skip(reason="rollforward Rust plugin not available (stale CI cache)")
    for item in items:
        if "rollforward" in str(item.fspath):
            item.add_marker(skip_marker)
