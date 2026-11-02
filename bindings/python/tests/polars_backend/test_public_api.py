# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The retired import paths refuse, and the refusal is the assertion.

Every path named here once resolved to a module that held no implementation
and only re-published another module's names. Each is deleted, and each
import below must now raise. Not unused, not dead — do not "fix" one away.
"""

from __future__ import annotations

from importlib import import_module

import pytest


def test_functions_vector_is_refused() -> None:
    """The plugin wrappers have one home, and it is not ``functions.vector``.

    The import IS the assertion: a second spelling of the wrappers must
    stay gone, so importing the retired path must fail. Not unused, not
    dead — do not "fix" it away.
    """
    with pytest.raises(ModuleNotFoundError):
        import gaspatchio.functions.vector  # noqa: F401


def test_functions_utils_is_refused() -> None:
    """``to_polars_expression`` has one home, and it is not ``functions.utils``.

    Same shape as the sibling above: the retired path must refuse.
    """
    with pytest.raises(ModuleNotFoundError):
        import gaspatchio.functions.utils  # noqa: F401


@pytest.mark.parametrize(
    "retired_path",
    [
        "gaspatchio.polars_backend",
        "gaspatchio.polars_backend._shared",
        "gaspatchio.polars_backend.list_eval",
        "gaspatchio.polars_backend.masks",
        "gaspatchio.polars_backend.operators",
        "gaspatchio.polars_backend.plugins",
        "gaspatchio.accessors.excel_functions",
        "gaspatchio.accessors.excel_functions.days",
        "gaspatchio.accessors.excel_functions.edate",
        "gaspatchio.accessors.excel_functions.eomonth",
        "gaspatchio.accessors.excel_functions.irr",
        "gaspatchio.accessors.excel_functions.pv",
        "gaspatchio.accessors.excel_functions.round",
        "gaspatchio.accessors.excel_functions.yearfrac",
        "gaspatchio.schedule._canonical",
    ],
)
def test_a_retired_second_door_is_refused(retired_path: str) -> None:
    """Each deleted re-export module raises rather than resolving.

    ``polars_backend`` re-published ``frame.lowering._polars``,
    ``accessors.excel_functions`` re-published ``frame.lowering._excel``, and
    ``schedule._canonical`` re-published ``canonical_bytes`` out of
    ``gaspatchio._identity``. Those three are where the names are written,
    and now the only places they are published from.
    """
    with pytest.raises(ModuleNotFoundError):
        import_module(retired_path)
