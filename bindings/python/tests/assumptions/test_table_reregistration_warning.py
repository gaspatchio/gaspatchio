# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the same-name / different-data re-registration warning.

Re-registering an assumption table under a name that already exists but with
DIFFERENT content invalidates any lazy lookup expression already built against
the previous same-named table. The native kernel refuses those expressions at
collection; the earlier warning tells callers to rebuild them when the content
differs.

The identical-content case is the common issue-#39 reentrancy scenario
(re-running the same model in the same process) and must stay SILENT. Neither
case may raise (see ``test_issue_39_reentrancy.py``).

The warning is a ``GaspatchioWarning`` raised through Python's ``warnings``,
not a log record: the package mutes its own logs when it is used as a
library, and this is something the user must hear whether or not they are
on. It is said through that one channel only.
"""

from __future__ import annotations

import warnings
from contextlib import contextmanager
from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

from gaspatchio import GaspatchioWarning
from gaspatchio.assumptions import Table

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def _capture_warnings() -> Iterator[tuple[list[warnings.WarningMessage], list[str]]]:
    """Record the warnings raised, and the log records written, inside the block."""
    logged: list[str] = []
    sink_id = logger.add(
        lambda msg: logged.append(msg.record["message"]),
        level="WARNING",
    )
    try:
        with warnings.catch_warnings(record=True) as heard:
            warnings.simplefilter("always")
            yield heard, logged
    finally:
        logger.remove(sink_id)


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

    with _capture_warnings() as (heard, logged):
        # Second registration with byte-identical data — common reentrancy case.
        Table(
            name="warn_identical_data",
            source=data,
            dimensions={"age": "age"},
            value="rate",
        )

    said = [str(w.message) for w in heard] + logged
    reregistration_warnings = [m for m in said if "re-registered" in m]
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

    with _capture_warnings() as (heard, logged):
        # Second registration with DIFFERENT values under the same name.
        Table(
            name="warn_different_data",
            source=pl.DataFrame({"age": [25, 30, 35], "rate": [0.9, 0.8, 0.7]}),
            dimensions={"age": "age"},
            value="rate",
        )

    reregistration_warnings = [w for w in heard if "re-registered" in str(w.message)]
    assert len(reregistration_warnings) == 1, (
        f"Expected exactly one re-registration warning for different data, "
        f"got: {[str(w.message) for w in heard]}"
    )
    (warning,) = reregistration_warnings
    # A GaspatchioWarning, located at the line that registered the table
    # again, and said through that channel only: no log record repeats it.
    assert issubclass(warning.category, GaspatchioWarning)
    assert warning.filename == __file__
    assert [m for m in logged if "re-registered" in m] == []
    message = str(warning.message)
    # The table name must be identifiable in the message.
    assert "warn_different_data" in message
    # The condition that raised it.
    assert "different data" in message
    # The consequence, and the remedy that follows from it. These two are the
    # half of the sentence that reversed on 2026-09-10: it previously said the
    # already-built lookups "will now resolve to the NEW values" and that an
    # intentional shock could ignore the warning. They are refused now, and a
    # reword restoring the old meaning would have to drop both phrases. A
    # reword that keeps the meaning keeps them.
    assert "refuse to collect" in message
    assert "rebuild expressions from the current Table" in message


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
