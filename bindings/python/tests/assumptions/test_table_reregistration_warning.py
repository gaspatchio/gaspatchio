# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the same-name / different-data re-registration warning (F8a).

Re-registering an assumption table under a name that already exists but with
DIFFERENT content silently swaps the data under any lazy lookup expression that
was already built against the previous same-named table (tables resolve by name
at execution time, last-writer-wins). That is a silent-wrong-number footgun, so
we emit a clear warning when — and only when — the content differs.

The identical-content case is the common issue-#39 reentrancy scenario
(re-running the same model in the same process) and must stay SILENT. Neither
case may raise (see ``test_issue_39_reentrancy.py``).
"""

from __future__ import annotations

import polars as pl
from loguru import logger

from gaspatchio_core.assumptions import Table


def _capture_warnings() -> tuple[list[str], int]:
    """Add a loguru WARNING sink and return (captured_messages, sink_id)."""
    captured: list[str] = []
    sink_id = logger.add(
        lambda msg: captured.append(msg.record["message"]),
        level="WARNING",
    )
    return captured, sink_id


def test_same_name_identical_data_emits_no_warning() -> None:
    """Re-registering the same name with IDENTICAL data must stay silent."""
    data = pl.DataFrame({"age": [25, 30, 35], "rate": [0.001, 0.002, 0.003]})

    # First registration establishes the known content hash for this name.
    Table(
        name="warn_identical_data",
        source=data,
        dimensions={"age": "age"},
        value="rate",
    )

    captured, sink_id = _capture_warnings()
    try:
        # Second registration with byte-identical data — common reentrancy case.
        Table(
            name="warn_identical_data",
            source=data,
            dimensions={"age": "age"},
            value="rate",
        )
    finally:
        logger.remove(sink_id)

    reregistration_warnings = [m for m in captured if "re-registered" in m]
    assert reregistration_warnings == [], (
        f"Expected no re-registration warning for identical data, got: "
        f"{reregistration_warnings}"
    )


def test_same_name_different_data_emits_warning() -> None:
    """Re-registering the same name with DIFFERENT data must warn."""
    # First registration.
    Table(
        name="warn_different_data",
        source=pl.DataFrame({"age": [25, 30, 35], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
    )

    captured, sink_id = _capture_warnings()
    try:
        # Second registration with DIFFERENT values under the same name.
        Table(
            name="warn_different_data",
            source=pl.DataFrame({"age": [25, 30, 35], "rate": [0.9, 0.8, 0.7]}),
            dimensions={"age": "age"},
            value="rate",
        )
    finally:
        logger.remove(sink_id)

    reregistration_warnings = [m for m in captured if "re-registered" in m]
    assert len(reregistration_warnings) == 1, (
        f"Expected exactly one re-registration warning for different data, "
        f"got: {reregistration_warnings}"
    )
    message = reregistration_warnings[0]
    # The table name must be identifiable in the message.
    assert "warn_different_data" in message
    # The message must explain the resolve-by-name / last-writer-wins hazard.
    assert "different data" in message
    assert "name" in message


def test_same_name_different_data_does_not_raise() -> None:
    """The warning path must never raise (preserve issue-#39 reentrancy)."""
    Table(
        name="warn_no_raise",
        source=pl.DataFrame({"x": [1, 2, 3], "y": [10.0, 20.0, 30.0]}),
        dimensions={"x": "x"},
        value="y",
    )

    # Different data, same name — must return a Table, not raise.
    table = Table(
        name="warn_no_raise",
        source=pl.DataFrame({"x": [1, 2, 3], "y": [100.0, 200.0, 300.0]}),
        dimensions={"x": "x"},
        value="y",
    )
    assert table is not None
