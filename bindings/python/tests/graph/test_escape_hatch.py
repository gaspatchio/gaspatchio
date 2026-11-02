# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The explicit way out of the vocabulary: what it records, and what it refuses.

``af.<column>.polars_native().<method>(...)`` reaches a Polars expression
method the framework's own vocabulary does not name. The calculation runs;
what changes is the record, and the point of spelling the escape out loud is
that the change is visible at the line the author wrote rather than at the
line somebody else later cannot re-run.

Four claims about what it records, and three about what it will not accept:

- the record says the engine, and an exported one cannot be re-run, which is
  the trade the escape exists to make visible;
- the columns the formula reads stay declared, so lineage survives;
- the recorded text carries nothing machine-local, so the same model records
  the same way on two machines;
- a call the vocabulary already names is refused, and one the recogniser
  declines -- a fold down the model points rather than along the periods --
  is exactly what the escape is for and is let through;
- a per-period column is refused to the handful of names whose meaning is
  the axis they run along and which the vocabulary does not name, because
  the escape would run them down the model points and say nothing; the same
  names on a per-policy column are let through unchanged;
- an expression that will not say what it reads is refused unless the author
  declares it, and a declaration that is not the read-set is refused too;
- an engine nothing here can lower is refused where the escape is opened,
  not where it would have run.

Nothing this file exercises removes anything: the reflective Polars surface
answers exactly as it did, and the two spellings are checked against each
other at the end.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio._authoring.escape import PolarsNative, _resolved_deps
from gaspatchio._semantic.ir import Call, EngineNative, col_refs, walk
from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.fingerprint import canonical_bytes
from gaspatchio.frame.graph.op_json import op_node_from_json, op_node_to_json
from gaspatchio.frame.lowering._polars.plugins import list_clip, list_pow
from gaspatchio.frame.lowering.ingress import _without_machine_paths, native_node
from gaspatchio.frame.lowering.polars import LoweringError, lower_polars

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode

# One book, three policies, sized so an ordering across them is visible.
_SUMS_ASSURED = [50000.0, 250000.0, 100000.0]


def _a_book() -> ActuarialFrame:
    """Return a three-policy frame to rank, cap and net down."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": _SUMS_ASSURED,
                "account_value": [100.0, 120.0, 90.0],
                "charge": [1.0, 2.0, 3.0],
            }
        )
    )


# Two policies, three periods each, with the periods rising inside a policy
# and the policies an order of magnitude apart -- so an answer taken down the
# model points cannot be mistaken for one taken along the periods.
_TWO_TIMELINES = [[1.5, 2.5, 3.5], [10.5, 20.5, 30.5]]


def _a_projection() -> ActuarialFrame:
    """Return a frame whose column holds one value per projection period."""
    return ActuarialFrame(
        pl.DataFrame({"account_value": _TWO_TIMELINES, "premium": [100.0, 200.0]})
    )


def _written_node(frame: ActuarialFrame, column: str) -> dict[str, Any]:
    """Return the artifact's own record of the latest definition of ``column``."""
    artifact: dict[str, Any] = json.loads(
        GraphExporter(frame).export(profile="executable")
    )
    latest = frame.graph.latest(column)
    written = [node for node in artifact["nodes"] if node["id"] == latest]
    assert written, f"{latest!r} is not in the artifact"
    return written[0]


def _node_of(frame: ActuarialFrame, column: str) -> OpNode:
    """Return the op-tree the frame's record holds for ``column``."""
    return op_node_from_json(_written_node(frame, column)["expr"])


# --- what the escape records -------------------------------------------------


def test_the_escape_records_the_engine_that_answered() -> None:
    """A ranked book is an engine fragment, declared as one, not an operation."""
    frame = _a_book()
    ranked = frame.sum_assured.polars_native().rank(method="ordinal")

    node = ranked._node  # noqa: SLF001 -- the record under test is the node itself

    assert isinstance(node, EngineNative)
    assert node.engine == "polars"
    frame.size_rank = ranked
    assert frame.collect()["size_rank"].to_list() == [1, 3, 2]


def test_an_exported_escape_is_a_record_and_not_a_calculation() -> None:
    """Written out and read back, the fragment refuses to run, saying why.

    The round trip through the artifact's own reader is the shape a second
    process is in: the node compares equal, and is a different object, so the
    live expression it was minted from is not reachable from it. This is the
    cost the escape's name and docstring exist to state at the point of use.
    """
    frame = _a_book()
    ranked = frame.sum_assured.polars_native().rank(method="ordinal")
    written = op_node_to_json(ranked._node)  # noqa: SLF001 -- the exported record

    read_back = op_node_from_json(json.loads(json.dumps(written)))

    assert read_back == ranked._node  # noqa: SLF001 -- same record...
    assert read_back is not ranked._node  # noqa: SLF001 -- ...different object
    with pytest.raises(LoweringError, match="must be re-supplied"):
        lower_polars(read_back, None)


def test_the_columns_the_escape_reads_stay_declared() -> None:
    """Lineage survives: the node is a leaf, and it still names its reads."""
    frame = _a_book()
    net = frame.account_value - frame.charge
    frame.high_water = net.polars_native().cum_max()

    node = _node_of(frame, "high_water")

    assert isinstance(node, EngineNative)
    assert list(walk(node)) == [node], "an engine fragment is a leaf"
    assert col_refs(node) == ("account_value", "charge")
    assert frame.graph.precedents("high_water") == ("account_value", "charge")
    assert frame.collect()["high_water"].to_list() == [99.0, 118.0, 118.0]


def test_the_record_names_the_engine_the_node_reaches() -> None:
    """The exported node declares Polars, which is what makes it unportable."""
    frame = _a_book()
    frame.high_water = frame.account_value.polars_native().cum_max()

    written = _written_node(frame, "high_water")

    assert written["engines"] == ["polars"]
    assert written["tier"] == "engine_native"


def test_a_column_composed_on_an_escape_speaks_only_for_its_own_line() -> None:
    """``engines`` is what a node's own text needs, never the closure over its reads.

    ``downstream`` is a multiplication and a subtraction -- operations the
    format names, in the format's own vocabulary -- so its record says
    ``core`` and ``[]``, and both are true of the line that was written.
    Neither is a statement that the column can be produced: the escape is
    upstream of it, and an evaluation needs the inputs as well as the line.
    Spec section 8.3 settles the field this way, so the reach is answered
    beside the record rather than inside it.
    """
    frame = _a_book()
    frame.high_water = frame.account_value.polars_native().cum_max()
    frame.downstream = frame.high_water * 2 - frame.charge

    escaped = _written_node(frame, "high_water")
    composed = _written_node(frame, "downstream")

    assert escaped["engines"] == ["polars"]
    assert composed["engines"] == [], "its own text reaches into no engine"
    assert composed["tier"] == "core"
    assert composed["reads"] == ["high_water@1", "charge"]


def test_the_reading_against_another_engine_names_the_reach_as_well() -> None:
    """One refusal and one remark: where it stops, and what stops with it.

    A reader counting refusals is counting the lines that have to be
    rewritten, and ``downstream`` is not one of them -- it runs under ``jax``
    the moment what it reads does. A reader asking which columns ``jax``
    produces needs it named all the same, because an empty ``engines`` on it
    answers for its own line and the per-node record has nothing else to say.
    """
    frame = _a_book()
    frame.high_water = frame.account_value.polars_native().cum_max()
    frame.downstream = frame.high_water * 2 - frame.charge
    document = json.loads(GraphExporter(frame).export(profile="executable"))

    report = validate_artifact(document, engine="jax")
    portability = [f for f in report.findings if f.section == "portability"]

    assert not report.ok
    assert [f.where for f in portability if f.severity == "error"] == ["high_water@1"]
    assert [f.where for f in portability if f.severity == "warning"] == [
        "envelope",
        "downstream@1",
    ]
    (reach,) = [f for f in portability if f.where == "downstream@1"]
    assert "reads 'high_water@1'" in reach.message
    assert "not the closure over what it reads" in reach.message


# --- the machine-local path --------------------------------------------------
#
# A compiled plugin renders inside the engine's text as the absolute path of
# the library holding it. ``text`` is written verbatim into the artifact and
# folded into the fingerprint, so that path made one calculation record two
# ways on two machines.

_ON_MACOS = (
    'col("v")./Users/someone/lab/bindings/python/gaspatchio'
    "/_internal.cpython-313-darwin.so:list_pow([dyn float: 2])"
)
_ON_LINUX = (
    'col("v")./home/ci/.venv/lib/python3.12/site-packages/gaspatchio'
    "/_internal.cpython-312-x86_64-linux-gnu.so:list_pow([dyn float: 2])"
)
_ON_WINDOWS = (
    'col("v").C:\\Users\\ci\\env\\Lib\\site-packages\\gaspatchio'
    "\\_internal.cp313-win_amd64.pyd:list_pow([dyn float: 2])"
)

_A_PLUGIN_ON_THREE_MACHINES = (_ON_MACOS, _ON_LINUX, _ON_WINDOWS)

_THE_SAME_CALCULATION = 'col("v").<plugin>:list_pow([dyn float: 2])'


@pytest.mark.parametrize("rendered", _A_PLUGIN_ON_THREE_MACHINES)
def test_a_plugin_library_path_leaves_the_recorded_text(rendered: str) -> None:
    """macOS, Linux and Windows renderings all record as one calculation."""
    assert _without_machine_paths(rendered) == _THE_SAME_CALCULATION


def test_three_machines_reach_one_fingerprint() -> None:
    """The fingerprint identifies the calculation, not the machine that ran it.

    Three before, one after: ``text`` is folded into the canonical bytes, so
    an absolute path in it moved the digest of a formula nobody had changed.
    """

    def digest(text: str) -> str:
        return hashlib.sha256(
            canonical_bytes(EngineNative("polars", text, ("v",)))
        ).hexdigest()

    assert len({digest(text) for text in _A_PLUGIN_ON_THREE_MACHINES}) == 3
    assert (
        len({digest(_without_machine_paths(t)) for t in _A_PLUGIN_ON_THREE_MACHINES})
        == 1
    )


@pytest.mark.parametrize(
    "rendered",
    [
        pytest.param(
            'col("v")./Users/Jane Doe/env/gaspatchio'
            "/_internal.cpython-313-darwin.so:list_pow([dyn float: 2])",
            id="a-path-with-a-space-in-it",
        ),
        pytest.param(
            'col("v").C:\\Program Files (x86)\\gaspatchio'
            "\\_internal.cp313-win_amd64.pyd:list_pow([dyn float: 2])",
            id="a-path-with-parentheses-in-it",
        ),
    ],
)
def test_an_awkward_install_path_leaves_the_text_whole(rendered: str) -> None:
    """Half a path is still a leaked path: spaces and parens are ordinary."""
    assert _without_machine_paths(rendered) == _THE_SAME_CALCULATION


def test_a_column_name_holding_a_slash_survives() -> None:
    """The path goes; the column name it was written after does not.

    ``col("premium/month")`` puts a slash inside the rendering before the
    plugin's path ever starts, and a scrub that began there would take the
    closing quote and the column's own name out with it -- trading a leak
    for a record that no longer says which column was read.
    """
    node = native_node(list_pow(pl.col("premium/month"), pl.lit(2.0)))

    assert node.text == 'col("premium/month").<plugin>:list_pow([dyn float: 2])'


def test_two_plugins_in_one_formula_both_lose_their_paths() -> None:
    """One rendering can name the library twice, and neither copy survives."""
    both = list_pow(pl.col("v"), pl.lit(2.0)) * list_clip(
        pl.col("w"), pl.lit(0.0), pl.lit(1.0)
    )

    text = native_node(both).text

    assert text.count("<plugin>") == 2
    assert ".so" not in text


def test_a_live_plugin_expression_records_no_path() -> None:
    """Driven on this build's own plugin, not on a written-down rendering."""
    node = native_node(list_pow(pl.col("v"), pl.lit(2.0)))

    assert node.text == _THE_SAME_CALCULATION
    assert ".so" not in node.text
    assert "/" not in node.text
    assert op_node_to_json(node)["text"] == _THE_SAME_CALCULATION


def test_three_names_shaped_like_a_path_stay_three_calculations() -> None:
    """The scrub takes out machine-local detail; it must not take out a name.

    These three aliases are three different calculations. Matched on shape
    alone they all read as a library path, all scrubbed to one text, and all
    fingerprinted the same -- a scrub written to stop one model recording two
    ways instead made three models record one way, which is the worse of the
    two failures by some distance. The path is taken from the position the
    rendering writes one in, after the method dot, and an alias is not
    written there.
    """

    def digest(name: str) -> str:
        text = _without_machine_paths(str(pl.col("account_value").alias(name)))
        return hashlib.sha256(
            canonical_bytes(EngineNative("polars", text, ("account_value",)))
        ).hexdigest()

    three = {digest(name) for name in ("a/b.so:c", "a/z.so:c", "a/OTHER.so:c")}

    assert len(three) == 3


def test_a_name_the_engine_writes_bare_is_left_alone_too() -> None:
    """A struct field is rendered without quotes around it, and still survives.

    The quotes around a column name were never what protected it: what
    protects any author's name is that the engine writes a library where a
    name is not written. ``field_by_name(x/y.so:z)`` has no quotes anywhere
    near the shape, and keeps every character.
    """
    rendered = str(pl.col("v").struct.field("x/y.so:z"))

    assert _without_machine_paths(rendered) == rendered
    assert "x/y.so:z" in rendered


@pytest.mark.parametrize(
    ("rendered", "expected"),
    [
        pytest.param(
            'col("v").build/lib/gaspatchio/_internal.cpython-313-darwin.so'
            ":list_pow([dyn float: 2])",
            _THE_SAME_CALCULATION,
            id="a-library-named-from-the-working-directory",
        ),
        pytest.param(
            'col("v").C:\\Users\\ci\\env\\gaspatchio\\_internal.CP313-WIN_AMD64.PYD'
            ":list_pow([dyn float: 2])",
            _THE_SAME_CALCULATION,
            id="an-extension-written-in-capitals",
        ),
        pytest.param(
            'col("v").\\\\build-server\\wheels\\gaspatchio\\_internal.dll'
            ":list_pow([dyn float: 2])",
            _THE_SAME_CALCULATION,
            id="a-library-on-another-machine-entirely",
        ),
    ],
)
def test_a_library_not_named_from_the_root_still_leaves_the_text(
    rendered: str, expected: str
) -> None:
    """Half a path is still a leaked path, and so is a path in capitals.

    A relative name kept the directory it was reached from, an extension in
    capitals kept the whole home directory in front of it, and a UNC name
    kept the build server that produced the wheel. Each is machine-local in
    exactly the way the absolute POSIX one is.
    """
    assert _without_machine_paths(rendered) == expected


# --- what the escape refuses -------------------------------------------------


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("round", lambda escape: escape.round(2)),
        ("clip", lambda escape: escape.clip(0.0, 100.0)),
        ("cut", lambda escape: escape.cut([1.0, 2.0])),
    ],
)
def test_a_call_the_vocabulary_names_is_refused(method: str, call: Any) -> None:  # noqa: ANN401
    """Two records for one calculation is the thing the escape must not allow."""
    frame = _a_book()

    with pytest.raises(
        ValueError, match=f"{method!r} as you have written it"
    ) as raised:
        call(frame.sum_assured.polars_native())

    assert "vocabulary" in str(raised.value)
    assert "Drop .polars_native()" in str(raised.value)


def test_the_shape_the_vocabulary_declines_is_let_through() -> None:
    """A fold down the model points is a different calculation, and is allowed.

    ``cum_sum`` is an operation along the projection's periods. On a
    per-policy column it runs down the model points instead, which the
    recogniser declines -- so the surface has always answered it in Polars,
    and the escape is where that now says so out loud. Refusing on the
    method's *name* would have closed this door.
    """
    frame = _a_book()

    running = frame.sum_assured.polars_native().cum_sum()

    assert isinstance(running._node, EngineNative)  # noqa: SLF001 -- the record
    frame.running = running
    assert frame.collect()["running"].to_list() == [50000.0, 300000.0, 400000.0]


@pytest.mark.parametrize(
    "method", ["backward_fill", "diff", "forward_fill", "interpolate", "shift"]
)
def test_a_per_period_column_is_refused_to_a_method_that_runs_down_the_rows(
    method: str,
) -> None:
    """The axis, named, before the wrong number rather than after it.

    These five are the other side of the ``cum_sum`` coin above: the
    vocabulary does not hold them, so nothing on the ordinary surface can
    decline the wrong meaning, and Polars reads a per-period column as one
    value per policy. ``shift(1)`` moved each policy's whole timeline onto
    the next policy and came back the right shape with no error.
    """
    frame = _a_projection()

    with pytest.raises(
        ValueError, match=f"{method!r} on a per-period column"
    ) as raised:
        getattr(frame.account_value.polars_native(), method)()

    message = str(raised.value)
    assert "runs down the model points" in message
    assert "along each policy's projection periods" in message
    assert f"list.eval(pl.element().{method}(...))" in message


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("shift", [None, 100.0]),
        ("diff", [None, 100.0]),
        ("forward_fill", [100.0, 200.0]),
        ("backward_fill", [100.0, 200.0]),
        ("interpolate", [100.0, 200.0]),
    ],
)
def test_a_per_policy_column_still_reaches_all_five_through_the_escape(
    method: str, expected: list[float | None]
) -> None:
    """Down the model points is the calculation, where that is what was written.

    The guard is a question about the receiver's shape, not about the
    method's name. On a per-policy column these are ordinary row semantics
    and the escape is exactly the door for them.
    """
    frame = _a_projection()

    frame.answer = getattr(frame.premium.polars_native(), method)()

    assert frame.collect()["answer"].to_list() == expected


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("shift", [[None, 1.5, 2.5], [None, 10.5, 20.5]]),
        ("diff", [[None, 1.0, 1.0], [None, 10.0, 10.0]]),
    ],
)
def test_the_spelling_the_refusal_gives_answers_along_the_periods(
    method: str, expected: list[list[float | None]]
) -> None:
    """The remedy in the message is run, not asserted -- and it is the answer.

    Through the bare escape ``shift(1)`` gave ``[None, [1.5, 2.5, 3.5]]``:
    one policy's timeline on the next policy's row. Inside ``list.eval`` it
    moves values between periods, which is what an actuary reading ``shift``
    reads.
    """
    frame = _a_projection()

    frame.answer = frame.account_value.polars_native().list.eval(
        getattr(pl.element(), method)()
    )

    assert frame.collect()["answer"].to_list() == expected


def test_the_undeclared_name_refusal_says_which_axis_the_escape_would_use() -> None:
    """The door is named either way; on a per-period column, so is its cost.

    ``af.account_value.shift(1)`` has no declared operation behind it, and
    the refusal has always pointed at ``polars_native()``. On a per-period
    column that door is a different calculation, so the refusal that sends
    the author through it says so, and gives the spelling that is not.
    """
    frame = _a_projection()

    with pytest.raises(AttributeError) as per_period:
        frame.account_value.shift(1)
    with pytest.raises(AttributeError) as per_policy:
        frame.premium.shift(1)

    along_the_periods = str(per_period.value)
    down_the_rows = str(per_policy.value)
    assert along_the_periods != down_the_rows
    assert down_the_rows in along_the_periods
    assert "moving values between policies rather than between periods" in (
        along_the_periods
    )
    assert "list.eval(pl.element().shift(...))" in along_the_periods
    assert "model points" not in down_the_rows


def test_the_vocabulary_still_answers_the_ordinary_spelling() -> None:
    """Nothing is removed: the same name without the escape records the op."""
    frame = _a_book()
    frame.rounded = frame.sum_assured.round(2)

    node = _node_of(frame, "rounded")

    assert isinstance(node, Call)
    assert node.name == "round"


class _RootlessExpression:
    """Stands in for an expression that will not report its root names.

    ``pl.Expr.meta.root_names()`` is documented as best-effort and
    ``ingress.native_node`` has always had a branch for its refusal, but no
    Polars expression I could build declines -- the framework's own compiled
    plugin reports ``['v']`` like anything else. The branch is driven here
    with a stand-in rather than left unexercised, because under the escape it
    is the difference between refusing and recording a calculation with no
    inputs.
    """

    class _Meta:
        def root_names(self) -> list[str]:
            msg = "this expression will not say"
            raise RuntimeError(msg)

    meta = _Meta()


def test_an_expression_that_will_not_say_what_it_reads_is_refused() -> None:
    """No declaration and no report is a node with no precedents -- refuse."""
    with pytest.raises(ValueError, match="will not say which columns it reads"):
        _resolved_deps(_RootlessExpression(), None, "some_plugin_call")  # type: ignore[arg-type]


def test_a_declaration_answers_for_an_expression_that_will_not_say() -> None:
    """Declared, the same expression is recorded with the reads it declares."""
    assert _resolved_deps(
        _RootlessExpression(),  # type: ignore[arg-type]
        ("account_value",),
        "some_plugin_call",
    ) == ("account_value",)


def test_a_declaration_that_is_not_the_read_set_is_refused() -> None:
    """Where the expression does report, the declaration is checked, not trusted."""
    frame = _a_book()

    with pytest.raises(ValueError, match="is not what this expression reads"):
        frame.sum_assured.polars_native(deps=["charge"]).rank()


def test_a_declaration_that_agrees_is_carried() -> None:
    """A correct declaration is an assertion the record keeps."""
    frame = _a_book()

    ranked = frame.sum_assured.polars_native(deps=["sum_assured"]).rank()

    assert ranked._node.deps == ("sum_assured",)  # noqa: SLF001 -- the record


@pytest.mark.parametrize(
    ("deps", "expected"),
    [
        ("sum_assured", "is one string"),
        ([1], "is not a column name"),
        ([""], "is not a column name"),
    ],
)
def test_a_declaration_that_is_not_column_names_is_refused(
    deps: Any,  # noqa: ANN401
    expected: str,
) -> None:
    """A read-set is a list of column names, and a string is not one."""
    frame = _a_book()

    with pytest.raises(TypeError, match=expected):
        frame.sum_assured.polars_native(deps=deps)


def test_an_engine_with_no_lowering_is_refused_where_it_is_opened() -> None:
    """Refused at the line the author wrote, not three phases later.

    Reached through a subclass because ``polars_native`` is the only spelling
    that ships and it names its engine: there is no target-engine choice
    anywhere at mint time today, so no line a user can write reaches this.
    The guard is where the engine is chosen, so the second engine's escape
    inherits it.
    """

    class _JaxNative(PolarsNative):
        engine = "jax"

    frame = _a_book()

    with pytest.raises(ValueError, match="nothing here can lower a 'jax' expression"):
        _JaxNative(frame.sum_assured)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("rolling_meen", "has no method named"),
        ("_expr", "is not something to reach through the escape"),
    ],
)
def test_a_name_that_is_not_a_polars_method_is_refused(
    name: str, expected: str
) -> None:
    """A misspelling and a private name each say which they are."""
    frame = _a_book()

    with pytest.raises(AttributeError, match=expected):
        getattr(frame.sum_assured.polars_native(), name)


def test_the_open_escape_says_what_an_expression_built_here_costs() -> None:
    """``repr`` names the receiver, the engine, and the trade."""
    frame = _a_book()

    shown = repr(frame.sum_assured.polars_native(deps=["sum_assured"]))

    assert "sum_assured" in shown
    assert "polars text" in shown
    assert "no export can re-run" in shown
