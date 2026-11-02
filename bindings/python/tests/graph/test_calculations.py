# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the calculation-record vocabulary and statement-scoped capture.

``gaspatchio.frame.calculations`` defines what the frame's durable
calculation log stores per column -- ``CalculationRecord``, its frozen
``SourceSpan``, the ``BoundaryRecord`` marker, and the ``LogEntry`` union --
plus ``capture_source_span``, the one function here with real behavior.

Nothing in this suite touches ``ActuarialFrame``: the wiring of these
records into ``__setitem__``/``__setattr__``/``with_columns`` is exercised
by ``test_log.py``, against the real frame. Instead, ``fake_frame`` builds
a tiny stand-in exposing the same assignment dunders
``ActuarialFrame`` does (``__setattr__``, ``__setitem__``), compiled under a
filename that lives inside the real ``gaspatchio/frame/`` directory (nothing
is written to disk -- ``compile``/``linecache`` only need the string). That
makes ``capture_source_span``'s real internal-frame check --
``is_framework_or_interpreter_file``, the rule the error locators follow
too -- treat the stand-in's dunders as framework machinery to walk past,
exactly as it treats ``ActuarialFrame``'s own dunders when the real frame
calls this module from there. Every test below exercises the real rule, not
a monkeypatched substitute -- except one, which deliberately breaks the
``executing`` library itself to prove the top-level "never raise" contract
holds even then.
"""

from __future__ import annotations

import ast
import importlib.util
import linecache
import types
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import TYPE_CHECKING, cast

import executing
import polars as pl
import pytest

from gaspatchio._semantic.ir import BinOp, Col
from gaspatchio.frame import calculations
from gaspatchio.frame.calculations import (
    BoundaryRecord,
    CalculationRecord,
    SourceSpan,
    _source_segment,
    capture_source_span,
)
from gaspatchio.frame.lowering.polars import lower_polars

if TYPE_CHECKING:
    from gaspatchio.frame.calculations import LogEntry, RecordOrigin

# --- fixture machinery: a stand-in for ActuarialFrame's assignment dunders --

# Deliberately not the real gaspatchio.functions.conditional.when -- this is
# only a source-shape fixture, standing in for a multi-line when()/then()/
# otherwise() chain so a test can assert the whole statement is captured,
# independent of what the real accessor actually computes.
_FAKE_INTERNAL_SOURCE = '''
"""Stand-in for ActuarialFrame's column-assignment dunders.

Every ``FakeFrame`` write records ``capture_source_span()``'s result onto
``history`` rather than actually storing the assigned value -- this module
exists purely to sit between a test's own assignment statement and the
real ``capture_source_span``, the same way ``ActuarialFrame.__setattr__``/
``__setitem__`` do.
"""
from gaspatchio.frame.calculations import capture_source_span


class FakeFrame:
    """Minimal stand-in exposing ActuarialFrame's assignment surface."""

    def __init__(self):
        object.__setattr__(self, "history", [])

    def __setattr__(self, name, value):
        object.__getattribute__(self, "history").append(capture_source_span())

    def __setitem__(self, key, value):
        object.__getattribute__(self, "history").append(capture_source_span())

    def __getattr__(self, name):
        return 1.0
'''


def _build_fake_frame_module() -> types.ModuleType:
    """Compile the ``FakeFrame`` fixture under a real ``gaspatchio/frame/`` path.

    Nothing is written to disk: ``compile`` only needs the filename string,
    and ``linecache`` is seeded manually (``mtime=None``, the documented
    convention for a runtime-generated source -- see ``linecache``'s own
    cache-invalidation contract) so ``executing`` can still retrieve and
    parse the text when it resolves a frame running this code.
    """
    package_root = Path(calculations.__file__).resolve().parent
    filename = str(package_root / "_fixture_fake_frame_for_test_calculations.py")
    lines = cast("list[str]", _FAKE_INTERNAL_SOURCE.splitlines(keepends=True))
    linecache.cache[filename] = (len(_FAKE_INTERNAL_SOURCE), None, lines, filename)
    module = types.ModuleType("_fixture_fake_frame_for_test_calculations")
    code = compile(_FAKE_INTERNAL_SOURCE, filename, "exec")
    exec(code, module.__dict__)  # noqa: S102 -- controlled fixture source, not untrusted input
    return module


@pytest.fixture
def fake_frame():
    """Build a fresh ``FakeFrame`` instance backed by its own compiled module."""
    return _build_fake_frame_module().FakeFrame()


class _FakeChain:
    """A chainable stand-in for when/then/otherwise -- shape only, not semantics."""

    def then(self, _value: object) -> _FakeChain:
        return self

    def otherwise(self, value: object) -> object:
        return value


def _fake_when(_condition: object) -> _FakeChain:
    """Return a chainable stand-in -- a source shape to capture, not real semantics."""
    return _FakeChain()


# --- capture_source_span: single-line assignment ----------------------------


def test_single_line_attribute_assignment_captures_the_whole_statement(
    fake_frame,
) -> None:
    """A plain ``stub.column = expr`` line is captured as one whole statement."""
    fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths

    span = fake_frame.history[-1]

    assert span is not None
    assert span.file == __file__
    assert span.line == span.end_line
    assert span.statement == (
        "fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths"
    )
    assert span.rhs == "fake_frame.sum_assured * fake_frame.expected_deaths"
    assert span.target_literal is True


def test_single_line_literal_subscript_assignment_is_also_target_literal(
    fake_frame,
) -> None:
    """A plain ``stub["column"] = expr`` line is also ``target_literal=True``."""
    fake_frame["death_claims"] = 5.0

    span = fake_frame.history[-1]

    assert span is not None
    assert span.statement == 'fake_frame["death_claims"] = 5.0'
    assert span.rhs == "5.0"
    assert span.target_literal is True


# --- capture_source_span: multi-line statements captured whole --------------


def test_multiline_when_chain_is_captured_whole(fake_frame) -> None:
    """A multi-line, parenthesised conditional chain is captured start to end."""
    fake_frame.policies_maturing = (
        _fake_when(fake_frame.month == fake_frame.policy_term)
        .then(fake_frame.policies_in_force)
        .otherwise(0.0)
    )

    span = fake_frame.history[-1]

    assert span is not None
    assert span.line != span.end_line
    assert span.statement.startswith("fake_frame.policies_maturing = (")
    assert ".otherwise(0.0)" in span.statement
    assert span.rhs is not None
    assert span.rhs.strip().startswith("_fake_when(")
    assert span.target_literal is True


# --- capture_source_span: helper-function assignment ------------------------


def test_helper_function_assignment_reports_the_helpers_own_line(fake_frame) -> None:
    """The captured span is the helper's own line, never its caller's call site."""

    def compute_death_claims() -> None:
        fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths

    def outer_driver() -> None:
        compute_death_claims()  # must NOT be what gets captured

    outer_driver()

    span = fake_frame.history[-1]

    assert span is not None
    assert span.file == __file__
    assert "compute_death_claims" not in span.statement
    assert "outer_driver" not in span.statement
    assert span.statement == (
        "fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths"
    )


# --- capture_source_span: the enclosing function scope ----------------------


def test_capture_names_the_function_the_assignment_was_written_in(
    fake_frame,
) -> None:
    """A span written inside a function reports that function by name."""
    fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths

    span = fake_frame.history[-1]

    assert span is not None
    assert span.function == (
        "test_capture_names_the_function_the_assignment_was_written_in"
    )


def test_capture_qualifies_a_nested_helpers_name_through_its_enclosing_scope(
    fake_frame,
) -> None:
    """A closure reports the scope it is nested in, not a bare local name."""

    def compute_death_claims() -> None:
        fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths

    compute_death_claims()

    span = fake_frame.history[-1]

    assert span is not None
    assert span.function == (
        "test_capture_qualifies_a_nested_helpers_name_through_its_enclosing_scope"
        ".<locals>.compute_death_claims"
    )


def test_capture_qualifies_a_method_with_the_class_that_owns_it(fake_frame) -> None:
    """A method reports ``Class.method``, not the bare name it may share."""

    class ReserveModel:
        def project(self) -> None:
            fake_frame.reserve = 1.0

    ReserveModel().project()

    span = fake_frame.history[-1]

    assert span is not None
    assert span.function.endswith("ReserveModel.project")


def test_module_level_assignment_reports_no_function_rather_than_the_sentinel(
    fake_frame, tmp_path
) -> None:
    """A statement at module level has no enclosing scope, and says so with None.

    The interpreter calls a module frame ``"<module>"``. That string is a
    placeholder for the absence of a scope, and a record that carried it
    would push the placeholder out to every renderer downstream, each of
    which would then have to know to suppress it.
    """
    module_source = "stub.premium_income = 1.0\n"
    module_path = tmp_path / "module_level_model.py"
    module_path.write_text(module_source)
    exec(  # noqa: S102 -- controlled fixture source, not untrusted input
        compile(module_source, str(module_path), "exec"), {"stub": fake_frame}
    )

    span = fake_frame.history[-1]

    assert span is not None
    assert span.statement == "stub.premium_income = 1.0"
    assert span.function is None


# --- capture_source_span: loop-built column -> target_literal False ---------


def test_loop_built_column_assignment_is_not_target_literal(fake_frame) -> None:
    """``stub[name] = ...`` inside a loop is captured but flagged non-literal."""
    for name in ["premium", "claim"]:
        fake_frame[name] = 0.0

    assert len(fake_frame.history) == 2
    for span in fake_frame.history:
        assert span is not None
        assert span.statement == "fake_frame[name] = 0.0"
        assert span.rhs == "0.0"
        assert span.target_literal is False


def test_setattr_built_column_takes_its_formula_from_the_calls_own_argument(
    fake_frame,
) -> None:
    """``setattr(stub, name, expr)`` is a call, and its value argument is the formula.

    Attribute syntax has no dynamic form, so a model building a family of
    columns whose names it only knows at run time writes them through the
    builtin. What that parses to is a call statement rather than an
    assignment, and the right-hand side the author wrote is the argument
    they wrote it in -- read from there, or the column has no as-written
    account at all.

    The target is still not literal: the name is a variable, exactly as it
    is in the subscript form above.
    """
    for name in ["death_claims", "lapse_claims"]:
        setattr(fake_frame, name, fake_frame.sum_assured * 2)

    assert len(fake_frame.history) == 2
    for span in fake_frame.history:
        assert span is not None
        assert span.statement == (
            "setattr(fake_frame, name, fake_frame.sum_assured * 2)"
        )
        assert span.rhs == "fake_frame.sum_assured * 2"
        assert span.target_literal is False


def test_augmented_assignment_is_not_treated_as_a_plain_assignment(fake_frame) -> None:
    """``stub.column += value`` triggers ``__setattr__`` but isn't a plain Assign."""
    fake_frame.reserve += 1.0

    span = fake_frame.history[-1]

    assert span is not None
    assert "+=" in span.statement
    assert span.rhs is None
    assert span.target_literal is False


def test_a_tuple_assignment_has_no_right_hand_side_of_its_own(fake_frame) -> None:
    """One statement writes two columns, and its value computes neither alone.

    The right-hand side of ``stub.a, stub.b = x, y`` is the whole tuple.
    Reported against either column it is text that does not compute the
    number beside it, which is the same reason a batch call's statement
    earns a null -- so the span records none, and both readers of ``rhs``
    (the exported ``formula`` and the error block's quoted line) are told
    the one thing that is true.
    """
    fake_frame.death_claims, fake_frame.lapse_claims = 1.0, 2.0

    assert len(fake_frame.history) == 2
    for span in fake_frame.history:
        assert span is not None
        assert span.statement.startswith("fake_frame.death_claims,")
        assert span.rhs is None
        assert span.target_literal is False


# --- capture_source_span: documented failure modes degrade to None ---------


def test_exec_compiled_call_site_with_no_retrievable_source_degrades_to_none(
    fake_frame,
) -> None:
    """An ``exec``-compiled statement with no registered source yields no span."""
    code = compile("fake_frame.reserve = 1.0\n", "<test-exec-no-source>", "exec")

    exec(code, {"fake_frame": fake_frame})  # noqa: S102 -- controlled fixture, not untrusted input

    assert fake_frame.history[-1] is None


def test_capture_source_span_never_raises_even_if_executing_blows_up(
    monkeypatch,
) -> None:
    """A failure inside ``executing`` itself degrades to ``None``, never propagates."""

    def _boom(_frame: object) -> None:
        msg = "simulated executing failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(executing.Source, "executing", staticmethod(_boom))

    assert capture_source_span() is None


# --- capture_source_span: GASPATCHIO_SOURCE_SPANS=off escape hatch ----------


def test_source_spans_off_switch_short_circuits_before_the_frame_walk(
    monkeypatch,
) -> None:
    """``GASPATCHIO_SOURCE_SPANS=off`` returns ``None`` without walking frames.

    Stubs ``_nearest_external_frame`` to raise if it is ever called, so a
    regression that computed the span and only discarded it afterwards --
    still correct by return value, but defeating the whole point of the
    switch -- would fail this test even though the weaker
    ``capture_source_span() is None`` assertion alone would not catch it.
    """

    def _fail_if_called() -> None:
        msg = "the off switch must short-circuit before the frame walk runs"
        raise AssertionError(msg)

    monkeypatch.setattr(calculations, "_nearest_external_frame", _fail_if_called)
    monkeypatch.setenv("GASPATCHIO_SOURCE_SPANS", "off")

    assert capture_source_span() is None


def test_source_spans_off_switch_matches_only_the_documented_value(
    monkeypatch,
) -> None:
    """Any value other than the exact string ``"off"`` leaves capture enabled."""
    monkeypatch.setenv("GASPATCHIO_SOURCE_SPANS", "OFF")

    assert capture_source_span() is not None


def test_source_spans_off_switch_pins_both_modes(fake_frame, monkeypatch) -> None:
    """The same real assignment captures a span normally, then ``None`` once off.

    Explicitly clears the variable before the "on" half so this test's
    result cannot depend on whatever an ambient shell happened to export --
    the same import-order-adjacent fragility class the ``AF_ERROR_MODE``
    globals in ``gaspatchio.util`` are already known to have.
    """
    monkeypatch.delenv("GASPATCHIO_SOURCE_SPANS", raising=False)
    fake_frame.reserve = fake_frame.premium * 1.05
    assert fake_frame.history[-1] is not None

    monkeypatch.setenv("GASPATCHIO_SOURCE_SPANS", "off")
    fake_frame.reserve = fake_frame.premium * 1.05
    assert fake_frame.history[-1] is None


# --- statement text: the standard library's answer, at the standard ----------
# --- library's cost only for the statement itself ----------------------------


def test_statement_text_matches_the_standard_library_across_a_real_corpus() -> None:
    """Every positioned node of three real modules extracts identically.

    ``_source_segment`` returns what ``ast.get_source_segment`` returns
    without that helper's habit of re-splitting the whole file from the top
    on every call. "What it returns" is the entire claim, so it is checked
    against the standard library over a real corpus -- every AST node
    carrying a source position -- rather than over a handful of hand-picked
    shapes.

    The corpus is stated rather than left as "everything under
    ``gaspatchio/frame/``": the module this function lives in, plus
    ``frame/base.py`` and ``_authoring/_native_docs.py``, the two longest
    modules beside it. They are named by path, so a reader knows what was read
    and a new module landing next door does not silently change the reading.
    Walking all seventy-nine cost a minute of the serial suite, and the
    standard library's helper is quadratic by construction, so the whole
    subpackage bought repetition rather than coverage: what varies between
    nodes is the shape of the span, and the parametrised cases below carry the
    shapes -- multibyte text before and inside a node, carriage returns, tabs,
    a form feed, no trailing newline -- that the corpus only ever supplies by
    accident. The floor of a thousand nodes is unchanged and these three
    modules clear it many times over.
    """
    module_path = Path(calculations.__file__).resolve()
    package_root = module_path.parent
    corpus = (
        module_path,
        package_root / "base.py",
        package_root.parent / "_authoring" / "_native_docs.py",
    )
    checked = 0
    for path in corpus:
        source = executing.Source.for_filename(str(path))
        assert source.tree is not None, path
        for node in ast.walk(source.tree):
            if not isinstance(node, (ast.stmt, ast.expr)):
                continue
            assert _source_segment(source, node) == ast.get_source_segment(
                source.text, node
            ), f"{path}:{node.lineno}"
            checked += 1
    assert checked > 1000


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("plain", "premium = 1.0\nreserve = (\n    premium\n    * 1.05\n)\n"),
        # Multibyte characters only ever INSIDE the node. Byte and character
        # offsets coincide at both of its ends, so this shape does not
        # exercise the byte arithmetic at all -- it is here for the round
        # trip, and the two cases below are the ones that guard.
        (
            "non_ascii_inside_node",
            'note = "premium → réserve"\nreserve = (\n    note\n)\n',
        ),
        # A multibyte character BEFORE the node, on the same line: every
        # offset of the second statement is now a byte offset that a
        # character slice reads at the wrong place.
        ("non_ascii_before_node", 'x = "→"; reserve = 1.05\n'),
        (
            "non_ascii_before_multiline_node",
            'x = "→"; reserve = (\n    1.05\n    * 2\n)\n',
        ),
        ("carriage_returns", "premium = 1.0\r\nreserve = (\r\n    premium\r\n)\r\n"),
        (
            "tab_indented",
            "def build():\n\tpremium = 1.0\n\treturn (\n\t\tpremium\n\t)\n",
        ),
        ("no_trailing_newline", "premium = 1.0\nreserve = (\n    premium\n)"),
        ("form_feed", "premium = 1.0\n\x0c\nreserve = (\n    premium\n)\n"),
    ],
)
def test_statement_text_matches_the_standard_library_on_awkward_files(
    tmp_path, name: str, content: str
) -> None:
    """Line endings, tabs, page breaks and non-ASCII all extract identically.

    A column offset counts bytes, not characters, so an extractor that
    sliced the line as text would read at the wrong place on any line
    holding a multi-byte character -- and would return a plausible-looking
    wrong string rather than failing loudly.

    Only the ``non_ascii_before_node`` cases actually catch that. Where the
    multi-byte characters sit *inside* the node, both of its offsets shift
    by the same amount and a character slice lands correctly anyway; the
    guard needs a multi-byte character *before* the node on its own line.
    Both branches of the extractor are covered, the single-line one and the
    multi-line rejoin.
    """
    path = tmp_path / f"{name}.py"
    # Written as bytes so the line endings survive verbatim: `write_text`
    # would translate them and the carriage-return case would stop being one.
    path.write_bytes(content.encode())
    source = executing.Source.for_filename(str(path))

    assert source.tree is not None
    nodes = [n for n in ast.walk(source.tree) if isinstance(n, (ast.stmt, ast.expr))]
    assert nodes
    for node in nodes:
        assert _source_segment(source, node) == ast.get_source_segment(
            source.text, node
        )


def test_capture_never_reaches_for_the_file_rescanning_helper(
    fake_frame, monkeypatch
) -> None:
    """Capture reads statement text without ``ast.get_source_segment``.

    That helper re-splits the source from the top of the file on every
    call, so its cost grows with how far down the file the statement sits
    -- and capture would pay it twice per assignment, once for the
    statement and once for the right-hand side. Making it raise here pins
    the property by construction: a regression that reached for it again
    would fail this test rather than only showing up as a slow model.
    """

    def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        msg = "capture must not re-split the whole file to read one statement"
        raise AssertionError(msg)

    monkeypatch.setattr(ast, "get_source_segment", _fail_if_called)

    fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths

    span = fake_frame.history[-1]
    assert span is not None
    assert span.statement == (
        "fake_frame.death_claims = fake_frame.sum_assured * fake_frame.expected_deaths"
    )


def test_statement_text_degrades_to_none_when_the_node_outruns_the_source(
    tmp_path,
) -> None:
    """A node naming a line the retrieved source does not have yields ``None``.

    The source text and the parsed statement can disagree -- a file rewritten
    between one read and the next is the ordinary way it happens. Reporting
    nothing is the only honest answer; raising, or reading whatever line
    happens to sit at that index, are both worse.
    """
    path = tmp_path / "short.py"
    path.write_text("premium = 1.0\n")
    source = executing.Source.for_filename(str(path))
    node = ast.parse("premium = 1.0\n" * 20).body[-1]

    assert _source_segment(source, node) is None


def test_statement_text_degrades_to_none_for_a_node_with_no_end_position() -> None:
    """A node carrying no end position yields ``None``, exactly as the stdlib does."""
    source = executing.Source.for_filename(str(Path(calculations.__file__).resolve()))
    node = ast.parse("premium = 1.0\n").body[0]
    node.end_lineno = None

    assert _source_segment(source, node) is None
    assert ast.get_source_segment(source.text, node) is None


# --- fidelity: the statement is the one that ran, not the file as it is now ---


def test_a_captured_statement_survives_the_file_being_rewritten(tmp_path) -> None:
    """A span captured at assignment still reads its own statement afterwards.

    The source file a model was defined in can change while the session that
    ran it is still open -- an editor save between an assignment and the
    error message that quotes it is the everyday case. What a record reports
    must be the statement that actually produced the column, so the text is
    read at assignment time and never re-derived from whatever the file
    holds later.
    """
    module_path = tmp_path / "model_under_edit.py"
    module_path.write_text(
        "def build(frame):\n"
        "    frame.death_claims = frame.sum_assured * frame.expected_deaths\n"
    )
    spec = importlib.util.spec_from_file_location("model_under_edit", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fake_frame = _build_fake_frame_module().FakeFrame()
    module.build(fake_frame)
    span = fake_frame.history[-1]

    assert span is not None
    assert span.statement == (
        "frame.death_claims = frame.sum_assured * frame.expected_deaths"
    )

    module_path.write_text(
        "def build(frame):\n    frame.death_claims = 0.0  # rewritten after the run\n"
    )
    linecache.checkcache(str(module_path))

    assert span.statement == (
        "frame.death_claims = frame.sum_assured * frame.expected_deaths"
    )
    assert span.rhs == "frame.sum_assured * frame.expected_deaths"


# --- record construction -----------------------------------------------------


def test_calculation_record_construction_derives_expr_from_its_node() -> None:
    """A record's ``expr`` is what ``lower_polars`` derives from its ``node``."""
    node = BinOp(op="mul", left=Col("sum_assured"), right=Col("expected_deaths"))
    expr = lower_polars(node)

    record = CalculationRecord(
        column="death_claims",
        ordinal=1,
        operation_id=1,
        node=node,
        expr=expr,
        dtype=None,
        source=None,
        origin="assignment",
    )

    assert record.column == "death_claims"
    assert record.ordinal == 1
    assert record.operation_id == 1
    assert record.node == node
    expected = pl.col("sum_assured").mul(pl.col("expected_deaths"))
    assert record.expr.meta.serialize() == expected.meta.serialize()
    assert record.dtype is None
    assert record.source is None
    assert record.origin == "assignment"


def test_calculation_record_is_mutable() -> None:
    """Unlike ``SourceSpan``/``BoundaryRecord``, a record may be updated in place."""
    node = Col("premium")
    record = CalculationRecord(
        column="premium",
        ordinal=1,
        operation_id=1,
        node=node,
        expr=lower_polars(node),
        dtype=None,
        source=None,
        origin="assignment",
    )

    record.dtype = pl.Float64()

    assert record.dtype == pl.Float64()


def test_source_span_is_frozen() -> None:
    """``SourceSpan`` rejects attribute assignment after construction."""
    span = SourceSpan(
        file="model.py",
        line=1,
        end_line=1,
        function="price_policy",
        statement="af.premium = af.premium_pp * af.policies_in_force",
        rhs="af.premium_pp * af.policies_in_force",
        target_literal=True,
    )

    with pytest.raises(FrozenInstanceError):
        span.line = 2  # type: ignore[misc]


def test_boundary_record_is_frozen_and_holds_kind_position_and_source() -> None:
    """Frozen, and it records its own place in the log and where the freeze was."""
    boundary = BoundaryRecord(kind="materialization", position=5, source=None)

    assert boundary.kind == "materialization"
    assert boundary.position == 5
    assert boundary.source is None
    with pytest.raises(FrozenInstanceError):
        boundary.position = 6  # type: ignore[misc]


def test_log_entry_accepts_both_calculation_and_boundary_records() -> None:
    """``LogEntry`` is the union both record shapes satisfy."""
    node = Col("premium")
    entries: list[LogEntry] = [
        CalculationRecord(
            column="premium",
            ordinal=1,
            operation_id=1,
            node=node,
            expr=lower_polars(node),
            dtype=None,
            source=None,
            origin="assignment",
        ),
        BoundaryRecord(kind="materialization", position=1, source=None),
    ]

    assert isinstance(entries[0], CalculationRecord)
    assert isinstance(entries[1], BoundaryRecord)


def test_every_record_origin_value_constructs_a_calculation_record() -> None:
    """Every ``RecordOrigin`` literal value is a valid ``CalculationRecord.origin``."""
    node = Col("premium")
    origins: tuple[RecordOrigin, ...] = (
        "assignment",
        "batch",
        "rollforward",
        "rename",
        "join",
        "projection",
        "date",
    )

    for origin in origins:
        record = CalculationRecord(
            column="premium",
            ordinal=1,
            operation_id=1,
            node=node,
            expr=lower_polars(node),
            dtype=None,
            source=None,
            origin=origin,
        )
        assert record.origin == origin
