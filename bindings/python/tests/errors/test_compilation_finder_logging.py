# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The compilation finder logs a failure only when it actually failed.

``_handle_compilation_error_enhanced`` replays the recorded operations, builds
the compilation panel, rewrites the exception's message and re-raises it. That
delivering raise used to sit *inside* the same ``try`` as the replay, so the
block's own ``except Exception`` caught the exception it had just raised and
logged ``Enhanced compilation error finder failed:`` -- followed by the whole
panel -- on every run in which the finder had succeeded. The user's message was
right either way (the handler re-raises the same object, already rewritten), but
a debug session was told the opposite of what happened.

This is the third path with that defect. The traced-run tier repaired it with
its ``panel_built`` flag and says so in a comment; the basic column formatter
was repaired the same way, and chains its genuine failure onto the exception it
delivers. The compilation tier never got either treatment.

The four cases below pin the repaired contract: silence on a successful panel,
the panel and its chain state unchanged, silence when replay declines to name a
calculation and hands over to basic formatting, and a genuine finder failure
still announced once -- still delivering polars' original error, now with the
finder's own failure chained onto it.
"""

from __future__ import annotations

import polars as pl
import pytest
from loguru import logger

from gaspatchio import ActuarialFrame
from gaspatchio.errors import compilation_finder, formatting_errors
from gaspatchio.util import set_error_mode

# The handler's own words. Present in the log means it believes the finder
# failed.
_FAILURE_LINE = "Enhanced compilation error finder failed"

# The column the model asks for and the frame does not have.
_MISSING_COLUMN = "a_column_that_does_not_exist_anywhere_in_this_frame"


def _capture_debug() -> tuple[list[str], int]:
    """Add a loguru DEBUG sink and return (captured_messages, sink_id)."""
    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(message.record["message"]),
        level="DEBUG",
    )
    return captured, sink_id


def _failing_frame() -> ActuarialFrame:
    """Build a traced frame whose last assignment reads a column that is absent.

    Traced, because only a traced run routes to the compilation finder
    (``formatting_errors.py`` checks ``frame._traced_run`` before calling it);
    the default path keeps the terse basic formatting.
    """
    af = ActuarialFrame(
        {
            "policy_id": [1, 2, 3],
            "sum_assured": [100.0, 200.0, 300.0],
            "mortality_rate": [0.01, 0.02, 0.03],
        },
    )
    af._traced_run = True  # noqa: SLF001 -- standing in for the trace decorator
    af.policies_in_force = 1.0 - af.mortality_rate
    af.reserve_factor = af.sum_assured * pl.col(_MISSING_COLUMN)
    return af


def _polars_column_not_found() -> pl.exceptions.ColumnNotFoundError:
    """Polars' own error, so the handler under test sees real wording."""
    try:
        pl.DataFrame({"age": [30], "sum_assured": [100.0]}).lazy().select(
            pl.col("premium_pp"),
        ).collect()
    except pl.exceptions.ColumnNotFoundError as err:
        return err
    msg = "polars accepted a column that is not there"
    raise AssertionError(msg)


def _plain_frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame({"age": [30, 40], "sum_assured": [100.0, 200.0]}),
    )


def test_a_successful_panel_logs_no_finder_failure() -> None:
    """The run that produced a panel must not be logged as one that could not.

    End to end, through the collect-time handler, which is where a user meets
    this: a traced calculation naming a column the frame never had. The panel
    arrives and ``_enhanced_processed`` is set, so the finder plainly
    succeeded -- and before the repair the log carried the failure line anyway,
    with the entire panel pasted after it.
    """
    set_error_mode("enhanced")
    af = _failing_frame()

    captured, sink_id = _capture_debug()
    try:
        with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
            af.collect()
    finally:
        logger.remove(sink_id)

    # The finder succeeded: the panel was built and the marker set.
    assert getattr(caught.value, "_enhanced_processed", False) is True
    assert hasattr(caught.value, "enhanced_error")

    # So nothing may claim it failed.
    assert [message for message in captured if _FAILURE_LINE in message] == []


def test_the_delivered_panel_and_its_chain_are_untouched() -> None:
    """Moving the raise out of the ``try`` must not touch what the user reads.

    The same object, carrying the panel the finder built, and carrying no
    chain: nothing failed, so there is nothing to chain. The assertions hold
    before the repair too, which is the point -- this is the guard that the log
    fix cost the delivered exception nothing.
    """
    set_error_mode("enhanced")
    af = _failing_frame()

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        af.collect()

    panel = str(caught.value)
    assert "column_not_found" in panel
    assert _MISSING_COLUMN in panel
    assert caught.value.enhanced_error.metadata.original_message

    # A success carries no cause and no context.
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert caught.value.__suppress_context__ is False


def test_a_declined_replay_hands_over_without_claiming_the_finder_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay may name no calculation; that is not a finder failure either.

    When the finder declines, the handler falls back to
    ``_handle_basic_column_error``, whose own raise used to land inside this
    ``try`` as well -- so the handover, too, was logged as the finder falling
    over. The basic panel still arrives; the log stays quiet.
    """
    set_error_mode("enhanced")
    frame = _plain_frame()
    err = _polars_column_not_found()

    class _Declines:
        """A finder that replays and attributes nothing."""

        groups: tuple[()] = ()

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def find_failing_operation(self) -> tuple[int, None, None]:
            return (0, None, None)

    monkeypatch.setattr(compilation_finder, "CompilationErrorFinder", _Declines)

    captured, sink_id = _capture_debug()
    try:
        with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
            formatting_errors._handle_compilation_error_enhanced(frame, err)  # noqa: SLF001
    finally:
        logger.remove(sink_id)

    # Basic formatting delivered the message, on the same object.
    assert caught.value is err
    assert caught.value._basic_formatted is True  # noqa: SLF001

    assert [message for message in captured if _FAILURE_LINE in message] == []


def test_a_genuine_finder_failure_still_logs_and_chains_the_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback keeps its job: say so, hand back the untouched error, chain.

    With the finder itself made to throw, the handler has nothing to deliver
    but polars' original message -- and this is the one run on which the
    failure line belongs in the log. The finder's own error now travels on the
    delivered exception as ``__cause__`` rather than only in a DEBUG line a
    sink level can filter away.
    """
    set_error_mode("enhanced")
    frame = _plain_frame()
    err = _polars_column_not_found()
    original_message = str(err)

    class _Explodes:
        """A finder that cannot even be constructed."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            msg = "the compilation finder itself fell over"
            raise RuntimeError(msg)

    monkeypatch.setattr(compilation_finder, "CompilationErrorFinder", _Explodes)

    captured, sink_id = _capture_debug()
    try:
        with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
            formatting_errors._handle_compilation_error_enhanced(frame, err)  # noqa: SLF001
    finally:
        logger.remove(sink_id)

    # The original exception, with the message polars gave it.
    assert caught.value is err
    assert str(caught.value) == original_message
    assert not hasattr(caught.value, "_enhanced_processed")

    failures = [message for message in captured if _FAILURE_LINE in message]
    assert len(failures) == 1
    assert "the compilation finder itself fell over" in failures[0]

    # The finder's failure is reachable from the delivered object, not only
    # from the log: the handler re-raises `from finder_error`, so the cause is
    # stamped on the exception a caller catches.
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "the compilation finder itself fell over"
    assert caught.value.__context__ is caught.value.__cause__
    assert caught.value.__suppress_context__ is True
