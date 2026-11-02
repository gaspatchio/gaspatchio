# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``AF_ERROR_MODE=off`` switches error enhancement off on every frame.

The variable is the operator's kill-switch, and two kinds of frame used to
survive it. A frame built with ``mode="debug"`` and a frame that had been
through a traced run both bypassed the collect-time handler's early exit and
reached the basic column formatter, so a misspelled column still came back
wearing a did-you-mean panel in a session that had asked for no error
handling at all. The validation decorator carried the same override, on the
frame's mode alone.

The rule pinned here: the environment variable decides. A frame's own
``mode="debug"`` adds detail *within* an enhancing mode; it never turns
enhancement on under ``off``. The ``enhanced`` cases are the other half of
the contract -- switching ``off`` off must not cost the debug-mode frame the
panel it is entitled to.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.errors import ValidationError, capture_validation_context

# The raw Polars text, as it reads before any framework formatting. The
# framework's own panel is recognisable by the two phrases below it.
_RAW_POLARS_MESSAGE = 'unable to find column "premum"'
_FRAMEWORK_PANEL = "Available columns"
_FRAMEWORK_SUGGESTION = "Did you mean one of these?"


def _frame(*, mode: str) -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "premium": [100.0]}),
        mode=mode,
    )


def _misspell(af: ActuarialFrame) -> None:
    """Assign a column off a name that does not exist -- fails at collect."""
    af.doubled = af["premum"] * 2.0


@capture_validation_context
def _rejects(frame: ActuarialFrame, value: int) -> int:
    """Stand in for a validator called with the frame among its arguments."""
    if value < 0:
        msg = f"Invalid value: {value}"
        raise ValueError(msg)
    return value


def test_off_leaves_a_debug_mode_frames_collect_error_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frame asked for debug; the session asked for no error handling."""
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _frame(mode="debug")
    _misspell(af)

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert message.startswith(_RAW_POLARS_MESSAGE)
    assert _FRAMEWORK_PANEL not in message
    assert _FRAMEWORK_SUGGESTION not in message
    assert not hasattr(excinfo.value, "_basic_formatted")


def test_off_leaves_a_traced_runs_collect_error_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A traced run is a request for detail, not a licence to ignore ``off``."""
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _frame(mode="optimize")
    af._traced_run = True  # noqa: SLF001 -- the flag the trace decorator sets
    _misspell(af)

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert message.startswith(_RAW_POLARS_MESSAGE)
    assert _FRAMEWORK_PANEL not in message
    assert _FRAMEWORK_SUGGESTION not in message
    assert not hasattr(excinfo.value, "_basic_formatted")


def test_enhanced_still_enhances_a_debug_mode_frames_collect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression guard: the default mode keeps the did-you-mean panel."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    af = _frame(mode="debug")
    _misspell(af)

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert _FRAMEWORK_PANEL in message
    assert _FRAMEWORK_SUGGESTION in message


def test_basic_still_formats_a_debug_mode_frames_collect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``basic`` is unchanged on the collect path too.

    Here the debug-mode frame overrides the session mode, which is what the
    early exit in ``_handle_frame_error`` still governs -- and what the new
    ``off`` guard above it must not have swallowed on its way past.
    """
    monkeypatch.setenv("AF_ERROR_MODE", "basic")
    af = _frame(mode="debug")
    _misspell(af)

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as excinfo:
        af.collect()

    message = str(excinfo.value)
    assert _FRAMEWORK_PANEL in message
    assert _FRAMEWORK_SUGGESTION in message


def test_off_leaves_a_debug_mode_frames_validation_error_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same rule on the validation decorator's own frame-mode override."""
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _frame(mode="debug")

    with pytest.raises(ValueError, match="Invalid value: -1") as excinfo:
        _rejects(af, -1)

    # ValidationError is a ValueError, so the type has to be checked directly.
    assert not isinstance(excinfo.value, ValidationError)
    assert excinfo.value.__cause__ is None


def test_basic_still_enhances_a_debug_mode_frames_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``basic`` is unchanged: a debug-mode frame still overrides it."""
    monkeypatch.setenv("AF_ERROR_MODE", "basic")
    af = _frame(mode="debug")

    with pytest.raises(ValidationError) as excinfo:
        _rejects(af, -1)

    assert excinfo.value.source_location is not None
