# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the source-context enrichment on proxied-method errors.

When a generated method called through a column proxy raises, ``ErrorEnhancer``
rewrites the exception. During a **traced run** -- the model function went
through the trace decorator, which ``--mode debug`` does -- it also appends
where the failing call came from. Outside a traced run it does not: reading
the source costs a stack walk per failure, and the default path should not
pay for a panel nobody asked to read.

Two things are pinned here, and the second is why the first is worth
stating precisely.

``_traced_run`` is the gate, pinned in both directions.

**The location must be the model author's own line.** The enrichment now
reaches it through ``capture_source_span``, which walks past every frame
the framework contributes at whatever depth they sit, so the reported line
is the assignment the author wrote rather than a framework wrapper's line.
The assertions below name that line exactly -- found by locating the
statement in this file's own source, so an edit that moves it moves the
expectation with it -- because a shape-only assertion ("some file, some
line") passes just as happily on a wrapper's line as on the author's.

This suite is deliberately end to end: a real generated method, a real
failure, the real message. The enrichment resolves a live call stack, so
anything that stands in for that stack proves nothing about the path a
model actually takes.

The last three tests widen the subject by one step, to everything the
framework writes onto an exception raised from a model author's assignment
line: the generated-method rewrite above, and the sibling rewrite inside
``__setitem__`` for a value that never reaches a proxy at all. Both are
switched off by ``AF_ERROR_MODE=off`` and by nothing else.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

# The enrichment appends labelled lines under the rewritten message.
_CALLED_FROM = "Called from:"
_FUNCTION = "Function:"
_SOURCE = "Source:"

# The two framework-authored prefixes, one per assignment-time path.
_GENERATED_METHOD_PREFIX = "Error calling gaspatchio method"
_SET_COLUMN_PREFIX = "Error setting column"

# The statement below, written once so the assertions and the call site
# cannot drift apart.
_FAILING_STATEMENT = 'af.rounded_premium = af.annual_premium.round("two")'

# What Polars raises for a value it cannot turn into a literal -- the
# original text under the ``__setitem__`` rewrite.
_UNASSIGNABLE_VALUE = "cannot create expression literal for value of type object"

# The switch that turns source capture off for a whole run.
_SPANS_ENV_VAR = "GASPATCHIO_SOURCE_SPANS"

# The switch that turns error handling off for a whole session.
_ERROR_MODE_ENV_VAR = "AF_ERROR_MODE"


def _line_of(statement: str) -> int:
    """Return the line in this file where ``statement`` is written on its own.

    Located rather than hardcoded, so moving the call site does not silently
    turn a location assertion into a coincidence.
    """
    lines = Path(__file__).read_text(encoding="utf-8").splitlines()
    written_at = [
        number
        for number, line in enumerate(lines, start=1)
        if line.strip() == statement
    ]
    if len(written_at) != 1:
        message = f"expected exactly one line reading {statement!r}, found {written_at}"
        raise AssertionError(message)
    return written_at[0]


def _premium_frame() -> ActuarialFrame:
    """Return a one-policy frame with a premium to call a method on."""
    return ActuarialFrame(pl.DataFrame({"annual_premium": [1200.0]}))


def _failing_method_call(af: ActuarialFrame) -> str:
    """Call a generated method that refuses its arguments, returning the message.

    ``round`` wants an integer number of decimal places. Handing it a
    string is refused before execution. The generated surface keeps the
    model-source enrichment while naming the supported form and escape.
    """
    with pytest.raises(TypeError) as excinfo:
        af.rounded_premium = af.annual_premium.round("two")
    return str(excinfo.value)


def _traced_frame() -> ActuarialFrame:
    """Return a frame flagged the way the trace decorator flags one."""
    af = _premium_frame()
    af._traced_run = True  # noqa: SLF001 -- the flag the trace decorator sets
    return af


def test_a_traced_run_reports_the_line_the_model_author_wrote() -> None:
    """The location is this file and the exact line holding the failing call."""
    message = _failing_method_call(_traced_frame())

    assert "Error calling gaspatchio method 'round'" in message
    assert f"{_CALLED_FROM} {__file__}:{_line_of(_FAILING_STATEMENT)}" in message


def test_a_traced_run_quotes_the_authors_whole_statement() -> None:
    """The source line quoted is the author's assignment, not a framework line."""
    message = _failing_method_call(_traced_frame())

    assert f"{_SOURCE} {_FAILING_STATEMENT}" in message


def test_a_traced_run_names_the_function_the_call_was_written_in() -> None:
    """The enclosing scope is reported alongside the line."""
    message = _failing_method_call(_traced_frame())

    assert f"{_FUNCTION} _failing_method_call" in message


def test_invalid_generated_arity_keeps_the_model_source_context() -> None:
    """The signature guard and value binder report the same author's location."""
    af = _traced_frame()
    with pytest.raises(TypeError) as excinfo:
        af.rounded_premium = af.annual_premium.round(1, 2, 3)

    statement = "af.rounded_premium = af.annual_premium.round(1, 2, 3)"
    message = str(excinfo.value)
    assert "Error calling gaspatchio method 'round'" in message
    assert ".polars_native().round(...)" in message
    assert f"{_CALLED_FROM} {__file__}:{_line_of(statement)}" in message
    assert f"{_SOURCE} {statement}" in message


def test_native_methods_keep_their_engine_error_context() -> None:
    """The explicit engine escape preserves authored-line error context."""
    af = _traced_frame()
    with pytest.raises(TypeError) as excinfo:
        af.cast_premium = af.annual_premium.polars_native().cast("not_a_dtype")

    statement = (
        'af.cast_premium = af.annual_premium.polars_native().cast("not_a_dtype")'
    )
    message = str(excinfo.value)
    assert "Error calling proxied Polars method 'polars_native().cast'" in message
    assert "cannot parse input of type 'str'" in message
    assert f"{_CALLED_FROM} {__file__}:{_line_of(statement)}" in message
    assert f"{_SOURCE} {statement}" in message


def test_the_location_is_never_the_frameworks_own_dispatch_machinery() -> None:
    """No framework file or wrapper name may appear as the reported location.

    The regression pin. The enrichment used to walk a fixed number of frames,
    which landed inside the method wrapper every time and could not reach the
    author's code at any depth, so every enriched error named the framework.
    """
    message = _failing_method_call(_traced_frame())

    called_from = next(line for line in message.splitlines() if _CALLED_FROM in line)
    assert "gaspatchio/column/" not in called_from
    assert "gaspatchio/frame/" not in called_from
    assert "_method_caller" not in message
    assert "_dispatch" not in message


def test_outside_a_traced_run_the_source_location_is_absent() -> None:
    """The default path is not asked for the panel, so it does not pay for it.

    The failure itself is still reported and still names the method -- only
    the stack-walked source location is withheld.
    """
    af = _premium_frame()
    assert af._traced_run is False  # noqa: SLF001 -- the default, stated

    message = _failing_method_call(af)

    assert "Error calling gaspatchio method 'round'" in message
    assert _CALLED_FROM not in message
    assert _FUNCTION not in message
    assert _SOURCE not in message


def test_the_gate_is_the_only_difference_between_the_two_messages() -> None:
    """Flipping the flag adds the location block and changes nothing else.

    Pinned as a consequence rather than by call-counting: the traced
    message is the untraced one plus the enrichment, so a regression that
    silently stopped enriching, or started enriching unconditionally, moves
    this assertion.
    """
    traced_message = _failing_method_call(_traced_frame())
    untraced_message = _failing_method_call(_premium_frame())

    assert traced_message != untraced_message
    assert traced_message.startswith(untraced_message)


def test_turning_source_spans_off_also_silences_this_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One switch, one capture mechanism: off means off here too.

    The enrichment reads the same capture the calculation log reads, so a
    run that opted out of paying for source spans opts out of this panel as
    well -- even with the traced-run flag set.
    """
    monkeypatch.setenv(_SPANS_ENV_VAR, "off")

    message = _failing_method_call(_traced_frame())

    assert _CALLED_FROM not in message
    assert _SOURCE not in message


def test_a_capture_that_finds_nothing_leaves_the_original_error_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capture returning nothing degrades the panel, never the failure.

    This code decorates an exception already in flight, which is the worst
    place in the framework to throw: whatever it raised would replace the
    failure the model author actually needs to read. So a capture that
    yields nothing costs the location lines and nothing else -- same
    exception type, same original text.
    """
    monkeypatch.setenv(_SPANS_ENV_VAR, "off")

    # The helper raises through ``pytest.raises(TypeError)``, so the type is
    # pinned there: an enrichment that threw would surface something else.
    traced_message = _failing_method_call(_traced_frame())

    assert "arguments supplied do not match" in traced_message
    assert ".polars_native().round(...)" in traced_message
    assert traced_message == _failing_method_call(_premium_frame())


def test_error_mode_off_leaves_a_generated_method_refusal_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``AF_ERROR_MODE=off`` takes the prefix as well as the panel.

    The rewrite is the framework writing on an exception in flight, and a
    session that switched error handling off asked for none of it -- not the
    ``Error calling gaspatchio method`` prefix, not the location block.
    The traced-run flag is set here deliberately: it is the condition that
    used to outrank the switch.
    """
    monkeypatch.setenv(_ERROR_MODE_ENV_VAR, "off")

    message = _failing_method_call(_traced_frame())

    assert message.startswith("round() is declared as round(decimals)")
    assert "arguments supplied do not match" in message
    assert ".polars_native().round(...)" in message
    assert _GENERATED_METHOD_PREFIX not in message
    assert _CALLED_FROM not in message
    assert _FUNCTION not in message
    assert _SOURCE not in message


def test_error_mode_off_leaves_a_failed_assignment_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same switch, on the assignment that never reaches a proxy.

    A value Polars cannot turn into a literal fails inside ``__setitem__``
    rather than inside a proxied method, and that path rewrote the message
    on its own terms -- naming the column and appending the value's type.
    Under ``off`` the model author gets what Polars raised.
    """
    monkeypatch.setenv(_ERROR_MODE_ENV_VAR, "off")
    af = _traced_frame()

    with pytest.raises(TypeError) as excinfo:
        af.unassignable = object()

    message = str(excinfo.value)
    assert message.startswith(_UNASSIGNABLE_VALUE)
    assert _SET_COLUMN_PREFIX not in message
    assert "Value type:" not in message


def test_a_failed_assignment_is_still_named_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard on the other side: only ``off`` is switched off.

    The column name and the value's type are what make a failed assignment
    diagnosable, and every mode but ``off`` keeps them.
    """
    monkeypatch.setenv(_ERROR_MODE_ENV_VAR, "enhanced")
    af = _traced_frame()

    with pytest.raises(TypeError) as excinfo:
        af.unassignable = object()

    message = str(excinfo.value)
    assert message.startswith(f"{_SET_COLUMN_PREFIX} 'unassignable'")
    assert _UNASSIGNABLE_VALUE in message
    assert "Value type: object" in message


@pytest.mark.parametrize(
    ("inner", "wrapped"),
    [
        ("the refusal ends its sentence.", "the refusal ends its sentence."),
        ("the refusal ends without one", "the refusal ends without one."),
    ],
    ids=["ends-in-a-stop", "ends-without-one"],
)
def test_a_failed_assignment_ends_the_inner_sentence_once(
    monkeypatch: pytest.MonkeyPatch, inner: str, wrapped: str
) -> None:
    """The wrapper closes the inner message with one full stop, never two.

    Nearly every refusal the framework raises is a sentence that already
    ends in a full stop, and the wrapper used to add another before the
    value's type, so the reader met "...cum_sum().. Value type".
    """
    monkeypatch.setenv(_ERROR_MODE_ENV_VAR, "enhanced")
    af = ActuarialFrame({"a": [1.0]})

    def refuse(_frame: ActuarialFrame, _value: object) -> pl.Expr:
        raise ValueError(inner)

    monkeypatch.setattr(ActuarialFrame, "_convert_to_expr", refuse)

    with pytest.raises(ValueError, match="Error setting column") as excinfo:
        af["x"] = 1.0

    assert (
        str(excinfo.value) == f"Error setting column 'x': {wrapped} Value type: float"
    )


def test_a_framework_refusal_reaches_the_reader_with_one_full_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same, through a real refusal raised while the formula is lowered."""
    monkeypatch.setenv(_ERROR_MODE_ENV_VAR, "enhanced")
    af = ActuarialFrame({"b": [[1.0, 2.0]]})

    with pytest.raises(ValueError, match="cum_sum") as excinfo:
        af["y"] = af.b.projection.accumulate(initial=1.0, multiplier=1.0, addend=2.0)

    message = str(excinfo.value)
    assert "initial + flow.cum_sum(). Value type: ExpressionProxy" in message
    assert ".." not in message
