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


def _table(name: str, rates: list[float], storage_mode: str = "auto") -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [30, 40, 50], "rate": rates}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode=storage_mode,
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
    """The message states the hazard and both ways out."""
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


def test_extend_updates_content_identity() -> None:
    """extend() re-stamps the content hash it registers under the name.

    Without the re-stamp both compared hashes stay at the pre-extension
    value: a later registration of the ORIGINAL data reads as idempotent,
    and a lookup from the extended object passes the guard while the
    appended rows are silently gone.
    """
    extended = _table("superseded_extend", [1.0, 2.0, 3.0], storage_mode="hash")
    extended.extend(pl.DataFrame({"age": [60], "rate": [4.0]}))

    # Original content re-registers (the reentrancy flow).
    _table("superseded_extend", [1.0, 2.0, 3.0], storage_mode="hash")

    with pytest.raises(TableSupersededError, match="superseded_extend"):
        extended.lookup(age=pl.col("age"))


def test_extended_table_still_looks_up_its_own_data() -> None:
    """The extended object's own lookups keep working after the re-stamp."""
    table = _table("superseded_extend_ok", [1.0, 2.0, 3.0], storage_mode="hash")
    table.extend(pl.DataFrame({"age": [60], "rate": [4.0]}))

    af = ActuarialFrame({"policy_id": [1], "age": [60]})
    af.rate = table.lookup(age=af.age)

    assert af.collect()["rate"].to_list() == [4.0]


def test_failed_replacement_does_not_poison_the_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed same-name registration must not corrupt supersession tracking.

    If the Rust registration raises, the registry still serves the original
    data — so the original object's lookups must keep working, not be
    refused against a hash the registry never accepted.
    """
    from gaspatchio_core.assumptions import _api

    original = _table("superseded_failed_swap", [1.0, 2.0, 3.0])

    class _ExplodingRegistry:
        def register_or_replace_table(self, **_kwargs: object) -> None:
            msg = "simulated native registration failure"
            raise RuntimeError(msg)

    monkeypatch.setattr(_api, "PyAssumptionTableRegistry", _ExplodingRegistry)
    with pytest.raises(RuntimeError, match="simulated native registration"):
        _table("superseded_failed_swap", [9.0, 8.0, 7.0])
    monkeypatch.undo()

    af = ActuarialFrame({"policy_id": [1], "age": [40]})
    af.rate = original.lookup(age=af.age)

    assert af.collect()["rate"].to_list() == [2.0]


def test_lookup_after_identical_reregistration_works_on_both_objects() -> None:
    """The issue-#39 reentrancy case: identical data, both objects stay valid."""
    first = _table("superseded_reentrant", [1.0, 2.0, 3.0])
    second = _table("superseded_reentrant", [1.0, 2.0, 3.0])

    af = ActuarialFrame({"policy_id": [1, 2], "age": [30, 50]})
    af.rate_first = first.lookup(age=af.age)
    af.rate_second = second.lookup(age=af.age)
    result = af.collect()

    assert result["rate_first"].to_list() == result["rate_second"].to_list()
