# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Verify plugin import paths after polars_backend relocation."""

from __future__ import annotations


def test_functions_vector_imports_still_work() -> None:
    """Legacy import path remains stable for external code."""
    from gaspatchio_core.functions.vector import (  # noqa: F401
        accumulate,
        fill_series,
        floor,
        list_clip,
        list_conditional,
        list_pow,
        round,
        round_to_int,
    )


def test_polars_backend_plugins_imports() -> None:
    """New canonical import path resolves directly from the submodule.

    The package-root re-export (``from gaspatchio_core.polars_backend
    import accumulate``) is wired in Task 3.5; tests for that path live
    there. For now the canonical path is ``polars_backend.plugins``.
    """
    from gaspatchio_core.polars_backend.plugins import (  # noqa: F401
        accumulate,
        fill_series,
        floor,
        list_clip,
        list_conditional,
        list_pow,
        round,
        round_to_int,
    )


def test_re_exports_are_same_function() -> None:
    """Old and new paths reach the same callable, not a copy."""
    from gaspatchio_core.functions.vector import accumulate as old_accumulate
    from gaspatchio_core.polars_backend.plugins import accumulate as new_accumulate

    assert old_accumulate is new_accumulate


def test_polars_backend_package_root_imports() -> None:
    """All public names resolve from the polars_backend package root."""
    from gaspatchio_core.polars_backend import (  # noqa: F401
        accumulate,
        boolean_and,
        boolean_not,
        boolean_or,
        dispatch_list_op,
        execute_list_clip,
        execute_list_pow,
        fill_series,
        floor,
        list_clip,
        list_conditional,
        list_pow,
        round,
        round_to_int,
        to_boolean_expr,
        unwrap_for_list_eval,
    )
