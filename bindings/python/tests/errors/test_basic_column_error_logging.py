# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The basic column formatter logs a failure only when it actually failed.

``_handle_basic_column_error`` rewrites a Polars ``ColumnNotFoundError`` into
the ``Calculation Error`` panel and re-raises it. The raise that delivered the
panel used to sit *inside* the formatting ``try``, so the ``except Exception``
caught the exception it had itself just raised and logged ``Failed to format
column error:`` on every successful run. The user's message was right either
way -- the fallback re-raises the same object, already rewritten -- but the
log said the opposite of what happened, and the log is what a debug session
reads.

That is the identical defect the enhanced path repaired with its
``panel_built`` flag; the basic path never got the same treatment. The three
cases below pin the repaired contract: silence on success, the delivered
message unchanged to the byte, and a real formatting failure still announced,
still delivering the original error, and now chaining the formatter's own
failure onto it.
"""

from __future__ import annotations

import polars as pl
import pytest
from loguru import logger

from gaspatchio import ActuarialFrame
from gaspatchio.errors import formatting_errors
from gaspatchio.util import set_error_mode

# The fallback handler's own words. Present in the log means the handler
# believes formatting failed.
_FAILURE_LINE = "Failed to format column error"
_PANEL_HEADING = "Calculation Error"


def _capture_debug() -> tuple[list[str], int]:
    """Add a loguru DEBUG sink and return (captured_messages, sink_id)."""
    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(message.record["message"]),
        level="DEBUG",
    )
    return captured, sink_id


def _polars_column_not_found() -> pl.exceptions.ColumnNotFoundError:
    """Polars' own error, so the extraction under test sees real wording."""
    try:
        pl.DataFrame({"age": [30], "sum_assured": [100.0]}).lazy().select(
            pl.col("premium_pp"),
        ).collect()
    except pl.exceptions.ColumnNotFoundError as err:
        return err
    msg = "polars accepted a column that is not there"
    raise AssertionError(msg)


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame({"age": [30, 40], "sum_assured": [100.0, 200.0]}),
    )


def test_a_successful_format_logs_no_formatting_failure() -> None:
    """The run that produced a panel must not be logged as one that could not.

    End to end, through the collect-time handler, which is where a user
    meets this: a calculation naming a column the frame never had. The
    panel arrives and ``_basic_formatted`` is set, so formatting plainly
    succeeded -- and before the repair the log carried the failure line
    anyway.
    """
    set_error_mode("enhanced")
    af = _frame()
    af.claims = pl.col("premium_pp") * pl.col("sum_assured")

    captured, sink_id = _capture_debug()
    try:
        with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
            af.collect()
    finally:
        logger.remove(sink_id)

    # Formatting succeeded: the panel was built and the marker set.
    assert getattr(caught.value, "_basic_formatted", False) is True
    assert _PANEL_HEADING in str(caught.value)

    # So nothing may claim it failed.
    assert [message for message in captured if _FAILURE_LINE in message] == []


def test_the_delivered_message_is_the_formatter_output_byte_for_byte() -> None:
    """Moving the raise out of the ``try`` must not touch what the user reads.

    The formatter's return value is the whole of the delivered message, and
    equality here is byte equality -- the same assertion holds before the
    repair, which is the point: this is the guard that the log fix cost the
    message nothing.
    """
    set_error_mode("enhanced")
    frame = _frame()
    err = _polars_column_not_found()
    expected = formatting_errors._format_column_message(  # noqa: SLF001
        frame,
        "premium_pp",
        str(err),
    )

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        formatting_errors._handle_basic_column_error(frame, err)  # noqa: SLF001

    # The original object, carrying the formatter's text unaltered.
    assert caught.value is err
    assert str(caught.value) == expected
    assert caught.value._basic_formatted is True  # noqa: SLF001


def test_a_genuine_formatting_failure_still_logs_and_re_raises_the_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback keeps its job: say so, and hand back the untouched error.

    With the formatter itself made to throw, the handler has nothing to
    deliver but the original message -- and this is the one run on which the
    failure line belongs in the log.
    """
    set_error_mode("enhanced")
    frame = _frame()
    err = _polars_column_not_found()
    original_message = str(err)

    def _explode(*_args: object, **_kwargs: object) -> str:
        msg = "the formatter itself fell over"
        raise RuntimeError(msg)

    monkeypatch.setattr(formatting_errors, "_format_column_message", _explode)

    captured, sink_id = _capture_debug()
    try:
        with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
            formatting_errors._handle_basic_column_error(frame, err)  # noqa: SLF001
    finally:
        logger.remove(sink_id)

    # The original exception, with the message Polars gave it.
    assert caught.value is err
    assert str(caught.value) == original_message
    assert not hasattr(caught.value, "_basic_formatted")

    failures = [message for message in captured if _FAILURE_LINE in message]
    assert len(failures) == 1
    assert "the formatter itself fell over" in failures[0]

    # The formatter's own failure is reachable from the delivered object, not
    # only from the log: the handler re-raises `from format_err`, so the cause
    # is stamped on the exception a caller catches. A log line can be filtered
    # out by sink level; the chain cannot.
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "the formatter itself fell over"
    assert caught.value.__context__ is caught.value.__cause__
    assert caught.value.__suppress_context__ is True
