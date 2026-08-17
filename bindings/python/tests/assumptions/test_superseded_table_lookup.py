# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the superseded-table lookup refusal (#116).

Tables resolve by NAME at execution time (last-writer-wins), so a ``Table``
object whose name has since been re-registered with different data would
silently serve the newer values — the vm20 clean-room shape where a scenario
override built before ``load_assumptions()`` resolves to base data and the
sweep reports zero sensitivity. A lookup from such a stale object is
guaranteed wrong, so it refuses loudly instead.

Re-registration itself stays permissive (same-name tables across different
models in one process are legitimate), and the identical-content reentrancy
case (issue #39) stays silent and working on both objects.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table, TableSupersededError


def _table(name: str, rates: list[float]) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 40, 50], "rate": rates}),
        dimensions={"age": "age"},
        value="rate",
    )


def test_lookup_on_superseded_table_raises() -> None:
    """The vm20 shape: override built first, base re-registers the name.

    Holding the override object must not silently produce base data — the
    lookup refuses, naming the table and the fix.
    """
    override = _table("superseded_premium", [6100.0, 6100.0, 6100.0])
    _table("superseded_premium", [610.0, 610.0, 610.0])  # base wins the name

    with pytest.raises(TableSupersededError, match="superseded_premium"):
        override.lookup(age=pl.col("age"))


def test_error_names_the_hazard_and_the_fix() -> None:
    override = _table("superseded_msg", [1.0, 2.0, 3.0])
    _table("superseded_msg", [9.0, 8.0, 7.0])

    with pytest.raises(TableSupersededError) as excinfo:
        override.lookup(age=pl.col("age"))

    message = str(excinfo.value)
    assert "different data" in message
    assert "distinct names" in message


def test_lookup_on_current_table_after_supersede_works() -> None:
    """The notebook flow: rebuilding a table and looking up from the NEW object."""
    _table("superseded_iterate", [1.0, 2.0, 3.0])
    current = _table("superseded_iterate", [9.0, 8.0, 7.0])

    af = ActuarialFrame({"policy_id": [1], "age": [40]})
    af.rate = current.lookup(age=af.age)
    result = af.collect()

    assert result["rate"].to_list() == [8.0]


def test_lookup_after_identical_reregistration_works_on_both_objects() -> None:
    """The issue-#39 reentrancy case: identical data, both objects stay valid."""
    first = _table("superseded_reentrant", [1.0, 2.0, 3.0])
    second = _table("superseded_reentrant", [1.0, 2.0, 3.0])

    af = ActuarialFrame({"policy_id": [1, 2], "age": [30, 50]})
    af.rate_first = first.lookup(age=af.age)
    af.rate_second = second.lookup(age=af.age)
    result = af.collect()

    assert result["rate_first"].to_list() == result["rate_second"].to_list()
