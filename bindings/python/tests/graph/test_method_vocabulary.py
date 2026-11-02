# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Engine method names the format's own vocabulary spells, and what they record.

A proxy carries Polars' whole method surface: whatever ``pl.Expr`` has, an
actuary can call. Most of that surface is genuinely one engine's own, and a
node reaching it says so. A handful of those names, though, are operations
the artifact format lists in section 11.1 with semantics of its own -- a
value held between two bounds, and the banding and parsing verbs that
follow it -- and for those the honest record is the operation, not the
engine's rendering of it.

Three claims, and each family below makes all three:

- **the tree says the operation**, so a reader sees a bound where a bound
  was written and a consumer holding the vocabulary can evaluate it;
- **the numbers do not move**, because this is a change to what is
  recorded and not to what is computed -- every shape a projection puts
  these operations in is pinned against the values it already gave;
- **the fallback still bites**: an operand the actuary wrote in the
  engine's own language stays an engine fragment, and one escape hatch
  anywhere makes the whole node engine-native.
"""

from __future__ import annotations

import datetime
import inspect
import json
import re
from collections.abc import Callable
from typing import Any, Final, Literal

import numpy as np
import polars as pl
import pytest

from gaspatchio._authoring import emit
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio._semantic.operations import _cut
from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.fingerprint import local_fingerprint
from gaspatchio.frame.graph.op_json import op_node_from_json


def _artifact(
    frame: ActuarialFrame, *, profile: Literal["audit", "executable"] = "executable"
) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export(profile=profile))
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _tree(frame: ActuarialFrame, node_id: str) -> dict[str, Any]:
    """Return the operation tree ``node_id`` carries, as the file writes it."""
    written: dict[str, Any] = _node(_artifact(frame), node_id)["expr"]
    return written


# --- bounds ------------------------------------------------------------------


def _a_model_capping_a_duration() -> ActuarialFrame:
    """Return a model holding a duration at the last row its table carries.

    The line level 4 writes as a conditional, written the way the method
    surface offers it: past the select period every duration reads the
    ultimate row, so the lookup key is the duration held at that row.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"duration": [3, 20, 40], "table_last": [14, 14, 14]})
    )
    frame.duration_capped = frame.duration.clip(0, 14)
    return frame


def test_a_capped_duration_records_as_a_bound_and_not_as_engine_text() -> None:
    """The operation section 11.1 names, in the tree, with its bounds beside it."""
    frame = _a_model_capping_a_duration()

    assert _tree(frame, "duration_capped@1") == {
        "op": "call",
        "name": "clip",
        "args": [
            {"op": "col", "name": "duration"},
            {"op": "lit", "value": 0},
            {"op": "lit", "value": 14},
        ],
        "attrs": {"bounds": "both"},
    }
    assert _node(_artifact(frame), "duration_capped@1")["tier"] == "core"
    assert _node(_artifact(frame), "duration_capped@1")["engines"] == []


def test_which_side_a_one_sided_bound_is_is_on_the_record() -> None:
    """A floor and a cap each carry one operand, so the record says which.

    Without the attribute the two are the same document -- one value, one
    bound -- and a consumer would have to guess whether a reserve was being
    floored at zero or capped at it.
    """
    frame = ActuarialFrame(pl.DataFrame({"reserve": [-100.0, 250.0]}))
    frame.floored = frame.reserve.clip(lower_bound=0.0)
    frame.capped = frame.reserve.clip(upper_bound=0.0)

    assert _tree(frame, "floored@1")["attrs"] == {"bounds": "lower"}
    assert _tree(frame, "capped@1")["attrs"] == {"bounds": "upper"}
    assert _tree(frame, "floored@1")["args"] == [
        {"op": "col", "name": "reserve"},
        {"op": "lit", "value": 0.0},
    ]


def test_a_bound_that_varies_by_policy_is_a_column_the_node_reads() -> None:
    """A bound is an operand, so a varying one declares its read like any other.

    This is why the bounds are not attributes: an attribute is a flat typed
    value and could not carry a column at all, so a vocabulary that put them
    there would state a constant floor and push every varying one back into
    an engine fragment.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"credited": [0.01, 0.06], "floor": [0.02, 0.02]})
    )
    frame.credited_floored = frame.credited.clip(lower_bound=frame.floor)
    node = _node(_artifact(frame), "credited_floored@1")

    assert node["tier"] == "core"
    assert sorted(node["reads"]) == ["credited", "floor"]


def test_the_positional_and_the_named_spelling_of_one_bound_are_one_node() -> None:
    """``clip(0, 14)`` and ``clip(lower_bound=0, upper_bound=14)`` are one formula."""
    positional = ActuarialFrame(pl.DataFrame({"duration": [3, 20, 40]}))
    positional.duration_capped = positional.duration.clip(0, 14)
    named = ActuarialFrame(pl.DataFrame({"duration": [3, 20, 40]}))
    named.duration_capped = named.duration.clip(lower_bound=0, upper_bound=14)

    assert (
        _node(_artifact(positional), "duration_capped@1")["local_fingerprint"]
        == (_node(_artifact(named), "duration_capped@1")["local_fingerprint"])
    )


def test_two_different_caps_are_two_different_nodes() -> None:
    """The bound is in the identity, which is the whole point of holding it.

    A capping duration that moved from 14 to 24 between two quarters is a
    model change, and a record that identified both lines the same way would
    be a change report that reported nothing.
    """
    at_fourteen = ActuarialFrame(pl.DataFrame({"duration": [3, 20, 40]}))
    at_fourteen.duration_capped = at_fourteen.duration.clip(0, 14)
    at_twenty_four = ActuarialFrame(pl.DataFrame({"duration": [3, 20, 40]}))
    at_twenty_four.duration_capped = at_twenty_four.duration.clip(0, 24)

    assert (
        _node(_artifact(at_fourteen), "duration_capped@1")["local_fingerprint"]
        != _node(_artifact(at_twenty_four), "duration_capped@1")["local_fingerprint"]
    )


def test_a_bound_the_actuary_wrote_in_the_engine_is_still_declared() -> None:
    """The operation is recognised; whose expression the bound is, is not changed.

    An actuary who reaches past the frame and hands ``pl.col(...)`` in has
    written an engine expression, and the record says so: that operand stays
    ``engine_native``, and one escape hatch anywhere makes the whole node
    engine-native. Pinned beside the flip so the change cannot be read as
    "a clip is always core".
    """
    frame = ActuarialFrame(
        pl.DataFrame({"credited": [0.01, 0.06], "floor": [0.02, 0.02]})
    )
    frame.credited_floored = frame.credited.clip(pl.col("floor"), 0.05)
    node = _node(_artifact(frame), "credited_floored@1")

    assert node["tier"] == "engine_native"
    assert node["engines"] == ["polars"]
    assert node["expr"]["name"] == "clip"
    assert node["expr"]["args"][1]["op"] == "engine_native"


def test_a_clip_with_no_bound_uses_the_explicit_engine_escape() -> None:
    """Nothing is bounded, so nothing is recorded as a bound.

    ``clip()`` asks the engine for the values back unchanged. Recording it
    as a bounding operation would put a claim in the file that the line
    does not make. The direct method refuses it and names the explicit
    engine escape, which records the fragment here.
    """
    frame = ActuarialFrame(pl.DataFrame({"reserve": [-100.0, 250.0]}))
    frame.unbounded = frame.reserve.polars_native().clip()

    assert _node(_artifact(frame), "unbounded@1")["tier"] == "engine_native"


def test_bounding_a_per_policy_column_gives_the_values_it_always_gave() -> None:
    """One value per policy, held between two bounds, nulls untouched."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {"age": [35, 45, 55, None], "lo": [40, 40, 40, 40], "hi": [50, 50, 50, 50]}
        )
    )
    frame.by_value = frame.age.clip(40, 50)
    frame.by_column = frame.age.clip(frame.lo, frame.hi)
    frame.floored = frame.age.clip(lower_bound=40)
    computed = frame.collect()

    assert computed["by_value"].to_list() == [40, 45, 50, None]
    assert computed["by_column"].to_list() == [40, 45, 50, None]
    assert computed["floored"].to_list() == [40, 45, 55, None]


def test_bounding_a_per_period_column_gives_the_values_it_always_gave() -> None:
    """Each period's own value against the same pair of bounds.

    Both forms Polars offers for a per-period bound are exercised, because
    the two are not interchangeable: a bound that is a value runs inside
    each row's list, where a named column cannot be reached at all, and a
    bound that reads a column goes to the kernel that takes the three
    columns side by side.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1"], "lo": [2.0], "hi": [4.0]})
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=5, frequency="monthly"
    )
    frame.value = frame.month * 1.0
    frame.by_value = frame.value.clip(2.0, 4.0)
    frame.by_column = frame.value.clip(frame.lo, frame.hi)
    frame.floored_by_column = frame.value.clip(lower_bound=frame.lo)
    computed = frame.collect()

    assert computed["by_value"].to_list() == [[2.0, 2.0, 2.0, 3.0, 4.0, 4.0]]
    assert computed["by_column"].to_list() == [[2.0, 2.0, 2.0, 3.0, 4.0, 4.0]]
    assert computed["floored_by_column"].to_list() == [[2.0, 2.0, 2.0, 3.0, 4.0, 5.0]]


# --- banding -----------------------------------------------------------------


def test_a_membership_test_records_the_set_it_tested_against() -> None:
    """The set is what identifies the test, so the tree holds it.

    The engine's rendering of a long argument list abbreviates its middle
    away, which is exactly where two filings differ: a set of forty state
    codes and a set of the same forty minus one displayed identically, so
    the two lines were one document.
    """
    frame = ActuarialFrame(pl.DataFrame({"product_code": ["TERM", "WL", "UL"]}))
    frame.on_the_guaranteed_basis = frame.product_code.is_in(["TERM", "WL"])

    assert _tree(frame, "on_the_guaranteed_basis@1") == {
        "op": "call",
        "name": "is_in",
        "args": [
            {"op": "col", "name": "product_code"},
            {"op": "lit", "values": ["TERM", "WL"]},
        ],
        "attrs": {"nulls_equal": False},
    }
    assert _node(_artifact(frame), "on_the_guaranteed_basis@1")["tier"] == "core"


def test_two_sets_differing_only_in_the_middle_are_two_nodes() -> None:
    """The defect the sequence literal exists to cure, at a banding.

    Forty product codes and the same forty with one dropped display the
    same way once an engine abbreviates the middle. Held as values, they
    are two calculations with two digests, which is what lets a change
    report say a filing's scope moved.
    """
    forty = [f"P{index:02d}" for index in range(40)]
    whole = ActuarialFrame(pl.DataFrame({"product_code": ["P00"]}))
    whole.in_scope = whole.product_code.is_in(forty)
    less_one = ActuarialFrame(pl.DataFrame({"product_code": ["P00"]}))
    less_one.in_scope = less_one.product_code.is_in([*forty[:20], *forty[21:]])

    assert (
        _node(_artifact(whole), "in_scope@1")["local_fingerprint"]
        != _node(_artifact(less_one), "in_scope@1")["local_fingerprint"]
    )


def test_a_band_records_its_breakpoints_and_its_labels() -> None:
    """Both halves of what identifies a banding are in the tree.

    A banded value is an ordered category, which section 10's type
    vocabulary has no name for, so the band is read here through the
    comparison a model writes against it -- which is also how a `cut`
    reaches an artifact at all today.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [35, 45, 55]}))
    frame.is_young = frame.age.cut([40.0, 50.0], labels=["young", "mid", "old"]) == (
        "young"
    )
    band = _tree(frame, "is_young@1")["left"]

    assert band == {
        "op": "call",
        "name": "cut",
        "args": [
            {"op": "col", "name": "age"},
            {"op": "lit", "values": [40.0, 50.0]},
            {"op": "lit", "values": ["young", "mid", "old"]},
        ],
        "attrs": {"left_closed": False, "include_breaks": False},
    }
    assert _node(_artifact(frame), "is_young@1")["tier"] == "core"


def test_a_band_with_no_labels_of_its_own_carries_two_operands() -> None:
    """Where the intervals name themselves there is no label sequence to record."""
    frame = ActuarialFrame(pl.DataFrame({"age": [35, 45, 55]}))
    frame.is_lowest = frame.age.cut([40.0, 50.0]) == "(-inf, 40]"
    band = _tree(frame, "is_lowest@1")["left"]

    assert len(band["args"]) == 2
    assert band["args"][1] == {"op": "lit", "values": [40.0, 50.0]}


def test_a_bare_band_held_by_the_model_is_refused_at_export_naming_to_text() -> None:
    """Section 11.1.4: the band is an ordered category, and section 10 names none.

    A producer must refuse a type it met and could not map (section 10), so
    the export refuses; what it owes the reader is the move, ``.to_text()``.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [25, 45, 65]}))
    frame.band = frame.age.cut([30.0, 50.0], labels=["young", "mid", "old"])

    with pytest.raises(UnmappedDtypeError, match=r"Column 'band'") as refused:
        GraphExporter(frame).export(include_source=False)

    assert ".to_text()" in str(refused.value)


def test_the_declared_band_examples_export() -> None:
    """Every example ``cut`` documents reaches the record, as text.

    The examples assigned the bare band, which the export then refused, so a
    model written from the documentation could not show its work.
    """
    examples = re.findall(r"```python\n(.*?)```", inspect.getdoc(_cut) or "", re.DOTALL)
    assert len(examples) == 2

    for example in examples:
        scope: dict[str, Any] = {}
        exec(example, scope)  # noqa: S102 -- the documented example, run as written
        frame = scope["af"]
        document = json.loads(GraphExporter(frame).export(include_source=False))
        band = next(node for node in document["nodes"] if node["column"] == "band")
        assert band["dtype"] in {"str", "list[str]"}
        assert band["tier"] == "core"


def test_breakpoints_written_the_wrong_way_up_are_refused_at_the_line() -> None:
    """The silent one: bands reported under other bands' names.

    Descending breakpoints, all different and all finite, with one
    distinct label per interval, are not refused by the engine. It puts
    the intervals in order and leaves the labels in the order they
    were written, so the population is banded correctly and labelled
    wrongly, with nothing raised at any point -- the 25-year-old below
    comes back as "over 50" and the 65-year-old as "under 30". Reversing
    two breakpoints leaves the middle band under its own name, so it is
    the outer bands that carry the harm here, not all three. A wrong
    number that announces itself is a bug; a wrong number that does not
    is a filing.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [25, 45, 65]}))

    with pytest.raises(ValueError, match="run up the line they cut") as refused:
        frame.band = frame.age.cut(
            [50.0, 30.0], labels=["over 50", "30 to 50", "under 30"]
        )

    assert "does not sit above" in str(refused.value)
    assert "lowest to highest" in str(refused.value)


def test_labels_that_do_not_name_every_interval_are_refused_at_the_line() -> None:
    """Two breakpoints cut the line into three, and three is the only count.

    The engine agrees, and says so when the frame is collected -- which in
    a model of any size is a long way from the line that wrote the pair,
    and says it against a query plan rather than against a band.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [25, 45, 65]}))

    with pytest.raises(ValueError, match="cut it into 3") as refused:
        frame.band = frame.age.cut([30.0, 50.0], labels=["young", "old"])

    assert "2 labels were written" in str(refused.value)
    assert "Name every interval" in str(refused.value)


def test_unwritten_descending_breakpoints_use_the_explicit_engine_escape() -> None:
    """The refusals are about what a written-out band means, not about reach.

    Breakpoints the op-tree has no literal form for are outside the direct
    operation. The two semantic checks above never see them, and the explicit
    engine escape keeps that different calculation available.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [35, 45, 55]}))
    frame.banded = (
        frame.age.polars_native()
        .cut(range(50, 30, -10))
        .polars_native()
        .cast(pl.String)
    )

    assert _node(_artifact(frame), "banded@1")["tier"] == "engine_native"


@pytest.mark.parametrize(
    "labels",
    [
        pytest.param(["o50", "mid", "u30"], id="list"),
        pytest.param(("o50", "mid", "u30"), id="tuple"),
        pytest.param(np.array(["o50", "mid", "u30"]), id="numpy-array"),
        pytest.param(pl.Series(["o50", "mid", "u30"]), id="series"),
        pytest.param(
            pl.DataFrame({"label": ["o50", "mid", "u30"]})["label"].to_numpy(),
            id="frame-column-to-numpy",
        ),
        pytest.param(
            pl.DataFrame({"label": ["o50", "mid", "u30"]})["label"],
            id="frame-column",
        ),
    ],
)
def test_the_wrong_way_up_is_refused_whatever_the_labels_arrived_in(
    labels: object,
) -> None:
    """What the labels are carried in is not what makes the band wrong.

    The breakpoints here are written out and read perfectly well; only
    the container the labels came in varies, and a ``Series`` or an array
    off a frame is an ordinary way to have them. Ask about the ordering
    after declining the labels the tree cannot hold, and every one of the
    four unreadable spellings walks through: banded, recorded, collected,
    the 25-year-old filed as "o50" and nothing said. So the ordering is
    asked of the breakpoints alone, before the labels are read at all.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [25, 45, 65]}))

    with pytest.raises(ValueError, match="run up the line they cut"):
        frame.band = frame.age.cut([50.0, 30.0], labels=labels)


def test_a_band_with_no_labels_has_nothing_to_mislabel_and_is_banded() -> None:
    """Unlabelled, a descending band is the ascending one, named correctly.

    The harm the refusal above names needs labels: it is the written
    order surviving beside intervals the engine has re-ordered. Write
    none and the engine generates each interval's name from its own
    sorted breakpoints, so the 25-year-old is in ``(-inf, 30]`` where she
    belongs. Refusing this shape would be refusing a reader for a harm
    their code cannot do, which is filling one in.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [25, 45, 65]}))
    frame.band = frame.age.cut([50.0, 30.0]).polars_native().cast(pl.String)

    assert _node(_artifact(frame), "band@1")["tier"] == "engine_native"
    assert frame.collect()["band"].to_list() == [
        "(-inf, 30]",
        "(30, 50]",
        "(50, inf]",
    ]


def test_a_repeated_breakpoint_with_no_labels_is_the_engines_own_refusal() -> None:
    """The accepted consequence of asking about ordering only under labels.

    A repeated breakpoint names an interval no life can fall in, which is
    worth refusing at the line that wrote it -- but only where there are
    labels to hang the refusal on. Unlabelled it goes back to where it
    was: the engine refuses it, correctly and by name, when the frame is
    collected. That is the milder half of the pair, and a run away from
    the line is the price of not refusing the descending spelling beside
    it, which the engine names correctly.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [25, 45, 65]}))
    frame.band = frame.age.cut([30.0, 30.0]).polars_native().cast(pl.String)

    with pytest.raises(pl.exceptions.DuplicateError, match="breaks are not unique"):
        frame.collect()


def test_a_repeated_breakpoint_with_labels_is_refused_but_not_as_a_mislabel() -> None:
    """Refused at the line, and told which of the two harms is theirs.

    The ordering refusal fires on two families and only one of them is
    the silent one. Breakpoints written downwards but all different and
    all finite, labelled one distinct name per interval, are banded and
    labelled with nothing raised anywhere, which is why the refusal
    exists. A repeated breakpoint is a different band entirely:
    the engine refuses it itself, by name, when the frame is collected,
    and nothing is filed under anyone else's name on the way. Both are
    worth stopping at the line that wrote them, and refusing this one is
    right -- but a refusal telling this reader their 25-year-old had
    been filed as "over 50" would be naming a harm their band cannot do,
    and would send them looking for a mislabelling that is not there.

    So the mislabel account has to be absent from the repeated sentence
    and governed by the condition in the ordering one. Co-location either
    side of "Repeated," is not enough on its own: a wording that states
    the mislabel unconditioned and appends "out of order and all
    different" afterwards as a separate sentence satisfies that and still
    misleads, which is why the condition is asked to come first.

    Two further assertions pin content and no more. The first is that the
    quantifier stays partial: reversing two breakpoints leaves the middle
    band under its own name, so a message claiming *every* band comes
    back under another band's name would overstate what it can show. The
    second is that every condition the mislabel account depends on is
    stated before the account arrives -- finiteness, and the labels
    being one per interval and all different, each of which the engine
    refuses by name when it fails. The two label conditions are asked
    for as the single phrase that states them together, because "all
    different" on its own is already said of the breakpoints two
    clauses earlier: a message that dropped it from the labels would
    still be answered by that earlier occurrence, and the condition
    would go unpinned. The wording is otherwise deliberately left free:
    pinning the whole message would make every future clarification a
    test edit rather than a rewording.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [25, 45, 65]}))

    with pytest.raises(ValueError, match="run up the line they cut") as refused:
        frame.band = frame.age.cut([30.0, 30.0], labels=["u30", "mid", "o50"])

    message = str(refused.value)
    scoped, _, repeated = message.partition("Repeated,")

    assert "Out of order and all different" in scoped
    assert "nothing anywhere says so" in scoped
    assert "filed as" in scoped
    assert scoped.index("Out of order and all different") < scoped.index("filed as")
    assert "nothing anywhere says so" not in repeated
    assert "filed as" not in repeated
    assert "when the frame is collected" in repeated
    assert "every band" not in message
    assert all(
        condition in scoped and scoped.rindex(condition) < scoped.index("filed as")
        for condition in ("finite", "one per interval and all different")
    )


def test_the_two_spellings_of_one_substitution_are_one_node() -> None:
    """A mapping and two sequences are one calculation, so they are one record."""
    as_mapping = ActuarialFrame(pl.DataFrame({"code": ["A", "B", "C"]}))
    as_mapping.basis = as_mapping.code.replace({"A": "TERM", "B": "WL"})
    as_sequences = ActuarialFrame(pl.DataFrame({"code": ["A", "B", "C"]}))
    as_sequences.basis = as_sequences.code.replace(["A", "B"], ["TERM", "WL"])

    assert _tree(as_mapping, "basis@1") == _tree(as_sequences, "basis@1")
    assert (
        _node(_artifact(as_mapping), "basis@1")["local_fingerprint"]
        == _node(_artifact(as_sequences), "basis@1")["local_fingerprint"]
    )


def test_two_orderings_of_one_substitution_are_one_node() -> None:
    """The order a substitution was written in is not part of what it does.

    A substitution maps each value to the one standing opposite it, all at
    once and with no value replaced twice -- the engine refuses a repeated
    left side outright -- so which pair an actuary typed first changes
    nothing about the answer. Left as written, two spellings of one mapping
    carried two digests, and a change report would have called drift on a
    line whose calculation had not moved. The pairs therefore sort into one
    order, the way section 12.1 already sorts a call's attributes.
    """
    as_written = ActuarialFrame(pl.DataFrame({"code": ["A", "B", "C"]}))
    as_written.basis = as_written.code.replace({"A": "TERM", "B": "WL"})
    reordered = ActuarialFrame(pl.DataFrame({"code": ["A", "B", "C"]}))
    reordered.basis = reordered.code.replace({"B": "WL", "A": "TERM"})
    as_sequences = ActuarialFrame(pl.DataFrame({"code": ["A", "B", "C"]}))
    as_sequences.basis = as_sequences.code.replace(["B", "A"], ["WL", "TERM"])

    stamps = {
        _node(_artifact(frame), "basis@1")["local_fingerprint"]
        for frame in (as_written, reordered, as_sequences)
    }

    assert _tree(as_written, "basis@1") == _tree(reordered, "basis@1")
    assert len(stamps) == 1
    assert reordered.collect()["basis"].to_list() == ["TERM", "WL", "C"]


def test_one_replacement_standing_for_every_value_records_as_one_value() -> None:
    """Collapsing several codes into one is a substitution with a single right side."""
    frame = ActuarialFrame(pl.DataFrame({"code": ["A", "B", "C"]}))
    frame.basis = frame.code.replace(["A", "B"], "GUARANTEED")

    assert _tree(frame, "basis@1")["args"][2] == {"op": "lit", "value": "GUARANTEED"}


def test_a_substitution_with_a_default_uses_the_explicit_engine_escape() -> None:
    """The vocabulary names the substitution, not what happens to what it missed.

    Polars' deprecated ``default`` turns the operation into something else
    -- every unmatched value replaced too -- and that is not what 11.1.6
    describes, so the explicit engine spelling records it as a fragment.
    """
    frame = ActuarialFrame(pl.DataFrame({"code": ["A", "B", "C"]}))
    with pytest.deprecated_call():
        frame.basis = frame.code.polars_native().replace(
            ["A"], ["TERM"], default="OTHER"
        )

    assert _node(_artifact(frame), "basis@1")["tier"] == "engine_native"


def test_unwritten_breakpoints_use_the_explicit_engine_escape() -> None:
    """Half a band is not a band, so nothing claims to have recorded one.

    A ``range`` is a sequence the engine accepts and the op-tree has no
    literal form for, so it uses the explicit engine escape. The node is
    worth reading, because the engine's own text for it is
    ``col("age").cut()``, with the breakpoints nowhere in the document at
    all. That is what an unrecorded band costs, and why declining says so
    rather than half-recording one.
    """
    frame = ActuarialFrame(pl.DataFrame({"age": [35, 45, 55]}))
    frame.banded = (
        frame.age.polars_native().cut(range(40, 60, 10)).polars_native().cast(pl.String)
    )
    node = _node(_artifact(frame), "banded@1")

    assert node["tier"] == "engine_native"
    assert node["expr"]["op"] == "engine_native"


def test_a_membership_set_the_actuary_wrote_in_the_engine_is_still_declared() -> None:
    """The set is an operand, so an engine expression there is declared as one."""
    frame = ActuarialFrame(
        pl.DataFrame({"code": ["A", "B", "C"], "allowed": [["A"], ["A"], ["A"]]})
    )
    frame.member = frame.code.is_in(pl.col("allowed"))
    node = _node(_artifact(frame), "member@1")

    assert node["tier"] == "engine_native"
    assert node["engines"] == ["polars"]
    assert node["expr"]["name"] == "is_in"
    assert node["expr"]["args"][1]["op"] == "engine_native"


def test_an_unordered_membership_set_uses_the_explicit_engine_escape() -> None:
    """A set the runtime iterates in its own order is not a written-out set.

    A Python set has no order, so the only order a producer could write its
    members in is whichever one the run happened to iterate -- and two runs
    of one model would then be two documents. Through the explicit escape,
    the whole node records as an engine fragment, without even the ``call``
    wrapper a set arriving as an expression keeps, because a membership test
    against a set nobody wrote out is not the operation 11.1.5 names.
    """
    frame = ActuarialFrame(pl.DataFrame({"product_code": ["TERM", "WL", "UL"]}))
    frame.on_the_guaranteed_basis = frame.product_code.polars_native().is_in(
        {"TERM", "WL"}
    )
    node = _node(_artifact(frame), "on_the_guaranteed_basis@1")

    assert node["tier"] == "engine_native"
    assert node["expr"]["op"] == "engine_native"
    assert frame.collect()["on_the_guaranteed_basis"].to_list() == [True, True, False]


def test_banding_gives_the_values_it_always_gave() -> None:
    """Every form the three take, against the answers they already gave."""
    frame = ActuarialFrame(
        pl.DataFrame({"age": [35, 45, 55, None], "code": ["A", "B", "C", None]})
    )
    frame.member = frame.code.is_in(["A", "B"])
    frame.member_nulls_equal = frame.code.is_in(["A"], nulls_equal=True)
    frame.mapped = frame.code.replace({"A": "TERM", "B": "WL"})
    frame.mapped_the_other_way_round = frame.code.replace({"B": "WL", "A": "TERM"})
    frame.collapsed = frame.code.replace(["B", "A"], "GUARANTEED")
    frame.renumbered = frame.age.replace([45, 35], [2, 1])
    frame.banded = frame.age.cut([40.0, 50.0]).polars_native().cast(pl.String)
    frame.banded_left = (
        frame.age.cut([40.0, 50.0], left_closed=True).polars_native().cast(pl.String)
    )
    computed = frame.collect()

    assert computed["member"].to_list() == [True, True, False, None]
    assert computed["member_nulls_equal"].to_list() == [True, False, False, False]
    assert computed["mapped"].to_list() == ["TERM", "WL", "C", None]
    assert (
        computed["mapped_the_other_way_round"].to_list() == computed["mapped"].to_list()
    )
    assert computed["collapsed"].to_list() == ["GUARANTEED", "GUARANTEED", "C", None]
    assert computed["renumbered"].to_list() == [1, 2, 55, None]
    assert computed["banded"].to_list() == [
        "(-inf, 40]",
        "(40, 50]",
        "(50, inf]",
        None,
    ]
    assert computed["banded_left"].to_list() == [
        "[-inf, 40)",
        "[40, 50)",
        "[50, inf)",
        None,
    ]


def _a_projection_of_attained_ages() -> ActuarialFrame:
    """Return a projection carrying one age per period, the shape a band keys on."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1"], "seed": [[35.0, 45.0, 55.0, 65.0]]})
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="annual"
    )
    frame.age = frame.seed
    return frame


def test_banding_a_projection_answers_period_by_period() -> None:
    """11.1.4, 11.1.5 and 11.1.6 all say "each value", and now all three do it.

    Handed a per-period column, Polars' column-level ``is_in`` asks whether
    the whole run of periods is a member and answers one Boolean for the
    policy; its ``replace`` matches none of them and hands the run back
    untouched; its ``cut`` cannot cast a list at all. The first two did
    that under a node recorded as the operation, so the file asserted a
    portable calculation whose answer was wrong -- the failure mode this
    framework's own principles name, in the tier that means trustworthy.
    """
    frame = _a_projection_of_attained_ages()
    frame.in_the_band = frame.age.is_in([35.0, 55.0])
    frame.regrouped = frame.age.replace([45.0], [40.0])
    frame.banded = frame.age.cut([40.0, 50.0], labels=["young", "mid", "old"])
    computed = frame.collect()

    assert computed["in_the_band"].to_list() == [[True, False, True, False]]
    assert computed["regrouped"].to_list() == [[35.0, 40.0, 55.0, 65.0]]
    assert computed["banded"].to_list() == [["young", "mid", "old", "old"]]


def test_banding_a_projection_records_the_operation_it_computed() -> None:
    """The record was already right for two of them; the answer was not."""
    frame = _a_projection_of_attained_ages()
    frame.in_the_band = frame.age.is_in([35.0, 55.0])
    frame.regrouped = frame.age.replace([45.0], [40.0])
    artifact = _artifact(frame)

    for column, identifier in (("in_the_band", "is_in"), ("regrouped", "replace")):
        node = _node(artifact, f"{column}@1")
        assert node["tier"] == "core"
        assert node["engines"] == []
        assert node["expr"]["name"] == identifier


def test_a_per_period_membership_set_that_is_a_column_is_refused() -> None:
    """Nothing inside a projection's periods can read another column.

    So a per-period value tested against a set that arrived as a column has
    no per-element answer to give -- and the whole-column answer is the one
    Boolean per policy this operation has stopped giving. The refusal names
    the shape rather than falling back to it.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1"],
                "seed": [[35.0, 45.0]],
                "allowed": [[35.0, 99.0]],
            }
        )
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=1, frequency="annual"
    )
    frame.age = frame.seed

    with pytest.raises(ValueError, match="written into the formula"):
        frame.member = frame.age.is_in(frame.allowed)


# --- parsing -----------------------------------------------------------------


def _a_model_parsing_its_entry_dates(date_format: str = "%Y/%m/%d") -> ActuarialFrame:
    """Return the first line of a projection whose entry dates arrived as text."""
    frame = ActuarialFrame(
        pl.DataFrame({"entry_date": ["2024/01/15", "2024/02/15", "2024/03/15"]})
    )
    frame.entry_date_parsed = frame.entry_date.str.to_date(date_format)
    return frame


def test_a_parsed_entry_date_records_the_format_it_was_read_under() -> None:
    """The whole of what makes one parse different from another, on the record."""
    frame = _a_model_parsing_its_entry_dates()

    assert _tree(frame, "entry_date_parsed@1") == {
        "op": "call",
        "name": "str.to_date",
        "args": [{"op": "col", "name": "entry_date"}],
        "attrs": {
            "format": "%Y/%m/%d",
            "strict": True,
            "exact": True,
        },
    }
    assert _node(_artifact(frame), "entry_date_parsed@1")["tier"] == "core"


def test_a_parse_records_what_it_computes_and_not_how_fast_it_ran() -> None:
    """A memoisation hint cannot change a date, so it is no part of the parse.

    Polars takes a ``cache`` argument that reuses the conversion of a string
    it has already read. It is a hint about speed: the dates that come back
    are the same dates either way. Section 12 takes a node's canonical bytes
    over what the node computes and nothing else, so recording the hint
    would make one parse two documents with two digests -- a change report
    calling drift where the calculation did not move, which is the same
    false identity this entry exists to close.
    """
    hinted = ActuarialFrame(pl.DataFrame({"entry_date": ["2024/01/15"]}))
    hinted.entry_date_parsed = hinted.entry_date.str.to_date("%Y/%m/%d", cache=False)
    plain = ActuarialFrame(pl.DataFrame({"entry_date": ["2024/01/15"]}))
    plain.entry_date_parsed = plain.entry_date.str.to_date("%Y/%m/%d")

    assert "cache" not in _tree(hinted, "entry_date_parsed@1")["attrs"]
    assert (
        _node(_artifact(hinted), "entry_date_parsed@1")["local_fingerprint"]
        == _node(_artifact(plain), "entry_date_parsed@1")["local_fingerprint"]
    )
    assert hinted.collect()["entry_date_parsed"].to_list() == (
        plain.collect()["entry_date_parsed"].to_list()
    )


def test_two_date_formats_are_two_nodes() -> None:
    """The identity defect this entry exists to close, stated as a test.

    ``"%Y/%m/%d"`` and ``"%d/%m/%Y"`` read the same characters into two
    different dates. The engine's rendering of the expression drops the
    format entirely -- both print ``str.strptime(["raise"])`` -- so the two
    lines were one document with one digest, which is a false identity
    rather than merely an unhelpful one.
    """
    year_first = _a_model_parsing_its_entry_dates("%Y/%m/%d")
    day_first = _a_model_parsing_its_entry_dates("%d/%m/%Y")

    assert (
        _node(_artifact(year_first), "entry_date_parsed@1")["local_fingerprint"]
        != _node(_artifact(day_first), "entry_date_parsed@1")["local_fingerprint"]
    )


def test_a_parse_that_tolerates_a_bad_string_says_so() -> None:
    """``strict`` changes what an unparseable string becomes, so it is recorded."""
    frame = ActuarialFrame(pl.DataFrame({"entry_date": ["2024/01/15"]}))
    frame.entry_date_parsed = frame.entry_date.str.to_date("%Y/%m/%d", strict=False)

    assert _tree(frame, "entry_date_parsed@1")["attrs"]["strict"] is False


def test_a_format_the_producer_inferred_is_recorded_as_absent() -> None:
    """A null format is the honest record of a parse nobody named.

    The parse depended on the text the run happened to hold, and a second
    implementation cannot reproduce it. The vocabulary reaches the
    operation; what it cannot reach is a format that was never written, and
    a null says which of the two happened.
    """
    frame = ActuarialFrame(pl.DataFrame({"entry_date": ["2024-01-15"]}))
    frame.entry_date_parsed = frame.entry_date.str.to_date()

    assert _tree(frame, "entry_date_parsed@1")["attrs"]["format"] is None
    assert _node(_artifact(frame), "entry_date_parsed@1")["tier"] == "core"


def test_the_sibling_parses_the_vocabulary_does_not_reach_still_say_so() -> None:
    """A datetime carries a time unit and a zone no operation here names.

    The gap is left visible rather than closed approximately: ``to_datetime``
    stays an engine fragment and the node declares it, which is what a tier
    is for.
    """
    frame = ActuarialFrame(pl.DataFrame({"stamp": ["2024-01-15 09:30:00"]}))
    frame.stamped = frame.stamp.polars_native().str.to_datetime("%Y-%m-%d %H:%M:%S")

    assert _node(_artifact(frame), "stamped@1")["tier"] == "engine_native"
    assert _node(_artifact(frame), "stamped@1")["engines"] == ["polars"]


def test_parsing_gives_the_dates_it_always_gave() -> None:
    """Every form the parse takes, against the values it already gave."""
    frame = ActuarialFrame(
        pl.DataFrame({"entry_date": ["2024/01/15", "2024/02/15", None]})
    )
    frame.parsed = frame.entry_date.str.to_date("%Y/%m/%d")
    frame.parsed_named = frame.entry_date.str.to_date(format="%Y/%m/%d", strict=False)
    frame.parsed_wrong = frame.entry_date.str.to_date("%d/%m/%Y", strict=False)
    frame.parsed_uncached = frame.entry_date.str.to_date("%Y/%m/%d", cache=False)
    computed = frame.collect()

    assert [str(value) for value in computed["parsed"].to_list()] == [
        "2024-01-15",
        "2024-02-15",
        "None",
    ]
    assert computed["parsed_named"].to_list() == computed["parsed"].to_list()
    assert computed["parsed_wrong"].to_list() == [None, None, None]
    assert computed["parsed_uncached"].to_list() == computed["parsed"].to_list()


def test_parsing_a_per_period_column_reads_each_period_s_own_string() -> None:
    """One string at a time, inside the list the strings are in."""
    frame = ActuarialFrame(
        pl.DataFrame({"stamps": [["2024/01/15", "2024/02/15"]]}).with_columns(
            pl.col("stamps").cast(pl.List(pl.String))
        )
    )
    frame.parsed = frame.stamps.str.to_date("%Y/%m/%d")

    assert [str(value) for value in frame.collect()["parsed"].to_list()[0]] == [
        "2024-01-15",
        "2024-02-15",
    ]


def _a_model_whose_per_period_dates_arrived_padded() -> ActuarialFrame:
    """Return per-period entry dates with the whitespace an extract carries.

    The ordinary shape of the awkward case: the strings are in the list they
    were always in, and the line that reads them has to tidy them first.
    """
    return ActuarialFrame(
        pl.DataFrame({"stamps": [[" 2024/01/15 ", " 2024/02/15 "]]}).with_columns(
            pl.col("stamps").cast(pl.List(pl.String))
        )
    )


def test_a_per_period_parse_reads_the_same_strings_at_the_end_of_a_chain() -> None:
    """Tidying the text first does not move the strings out of their lists."""
    frame = _a_model_whose_per_period_dates_arrived_padded()
    frame.parsed = (
        frame.stamps.polars_native()
        .list.eval(pl.element().str.strip_chars())
        .str.to_date("%Y/%m/%d")
    )

    assert [str(value) for value in frame.collect()["parsed"].to_list()[0]] == [
        "2024-01-15",
        "2024-02-15",
    ]


def test_the_sibling_parse_reaches_a_per_period_string_the_same_way() -> None:
    """Like shapes behave alike, whether or not 11.1 lists the method.

    Whether the text is per-period is a fact about the column, not about
    which operation is reading it. A rule that reached ``to_date`` because
    the vocabulary names it and stopped short of ``to_datetime`` because it
    does not would be a rule no actuary could predict: two lines over one
    column, one of them working and one of them refusing, for a reason
    visible only in section 11.1's table. The record still tells the two
    apart -- the datetime parse is an engine fragment and says so -- and
    that is the difference the vocabulary is entitled to make.
    """
    frame = _a_model_whose_per_period_dates_arrived_padded()
    frame.stamped = frame.stamps.polars_native().list.eval(
        pl.element().str.strip_chars().str.to_datetime("%Y/%m/%d")
    )

    assert [str(value) for value in frame.collect()["stamped"].to_list()[0]] == [
        "2024-01-15 00:00:00",
        "2024-02-15 00:00:00",
    ]
    assert _node(_artifact(frame), "stamped@1")["tier"] == "engine_native"


# --- rounding ----------------------------------------------------------------


def test_a_rounded_value_records_as_a_rounding_and_not_as_engine_text() -> None:
    """The operation section 11.1 names, with the places it kept beside it."""
    frame = ActuarialFrame(pl.DataFrame({"premium": [1234.567, 89.014]}))
    frame.premium_billed = frame.premium.round(2)

    assert _tree(frame, "premium_billed@1") == {
        "op": "call",
        "name": "round",
        "args": [{"op": "col", "name": "premium"}],
        "attrs": {"decimals": 2, "mode": "half_to_even"},
    }
    assert _node(_artifact(frame), "premium_billed@1")["tier"] == "core"


def test_the_two_directions_of_a_rounding_are_two_operations() -> None:
    """A floor and a ceiling answer different questions and record as different names.

    ``ceil`` is the whole units a premium has to be billed in; ``floor`` is
    the completed years a duration has run. Neither is the other with a
    flag, so neither is recorded as the other with a flag.
    """
    frame = ActuarialFrame(pl.DataFrame({"exact_years": [3.2, 7.8]}))
    frame.years_up = frame.exact_years.ceil()
    frame.years_down = frame.exact_years.floor()

    assert _tree(frame, "years_up@1") == {
        "op": "call",
        "name": "ceil",
        "args": [{"op": "col", "name": "exact_years"}],
        "attrs": {},
    }
    assert _tree(frame, "years_down@1") == {
        "op": "call",
        "name": "floor",
        "args": [{"op": "col", "name": "exact_years"}],
        "attrs": {},
    }


def test_two_roundings_to_different_places_are_two_nodes() -> None:
    """The places are what identifies one rounding against another."""
    pennies = ActuarialFrame(pl.DataFrame({"premium": [1234.567]}))
    pennies.billed = pennies.premium.round(2)
    pounds = ActuarialFrame(pl.DataFrame({"premium": [1234.567]}))
    pounds.billed = pounds.premium.round(0)

    assert (
        _node(_artifact(pennies), "billed@1")["local_fingerprint"]
        != _node(_artifact(pounds), "billed@1")["local_fingerprint"]
    )


def test_the_tie_rule_is_on_the_record_because_it_moves_the_money() -> None:
    """Half a penny up or to the even neighbour is a different premium.

    The two rules part company on the ties whose away-from-zero neighbour is
    odd -- 0.5 and 2.5 below, while 1.5 goes to 2.0 under both -- and which
    one an engine applies by default is the engine's choice rather than the
    model's, so the record carries the rule the parse actually ran under
    rather than leaving a reader to look one up.
    """
    frame = ActuarialFrame(pl.DataFrame({"premium": [0.5, 1.5, 2.5]}))
    frame.to_even = frame.premium.round(0)
    frame.away = frame.premium.round(0, mode="half_away_from_zero")
    computed = frame.collect()

    assert _tree(frame, "away@1")["attrs"] == {
        "decimals": 0,
        "mode": "half_away_from_zero",
    }
    assert computed["to_even"].to_list() == [0.0, 2.0, 2.0]
    assert computed["away"].to_list() == [1.0, 2.0, 3.0]


def test_significant_figures_are_their_own_operation_and_not_a_rounding() -> None:
    """Significant figures are not places, and the record does not conflate them.

    Both are on the record now, under two identifiers, which is the point:
    three significant figures leave 1234.567 as 1230.0 where three places
    leave it untouched, so one name carrying a different attribute would
    publish one identity for two calculations.
    """
    frame = ActuarialFrame(pl.DataFrame({"premium": [1234.567]}))
    frame.headline = frame.premium.round_sig_figs(3)
    frame.billed = frame.premium.round(3)

    assert _tree(frame, "headline@1") == {
        "op": "call",
        "name": "round_sig_figs",
        "args": [{"op": "col", "name": "premium"}],
        "attrs": {"digits": 3},
    }
    assert _node(_artifact(frame), "headline@1")["tier"] == "core"
    assert (
        _node(_artifact(frame), "headline@1")["local_fingerprint"]
        != _node(_artifact(frame), "billed@1")["local_fingerprint"]
    )
    computed = frame.collect()
    assert computed["headline"].to_list() == [1230.0]
    assert computed["billed"].to_list() == [1234.567]


def test_rounding_gives_the_values_it_always_gave() -> None:
    """Every form the rounding takes, against the values it already gave."""
    frame = ActuarialFrame(pl.DataFrame({"exact": [1.234, 5.678, -2.5, None]}))
    frame.pennies = frame.exact.round(2)
    frame.whole = frame.exact.round()
    frame.up = frame.exact.ceil()
    frame.down = frame.exact.floor()
    computed = frame.collect()

    assert computed["pennies"].to_list() == [1.23, 5.68, -2.5, None]
    assert computed["whole"].to_list() == [1.0, 6.0, -2.0, None]
    assert computed["up"].to_list() == [2.0, 6.0, -2.0, None]
    assert computed["down"].to_list() == [1.0, 5.0, -3.0, None]


def test_rounding_a_per_period_column_rounds_each_period_s_own_value() -> None:
    """One value at a time, inside the list the values are in."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"]}))
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=4, frequency="monthly"
    )
    frame.exact = frame.month * 0.4
    frame.up = frame.exact.ceil()
    frame.pennies = frame.exact.round(1)
    computed = frame.collect()

    assert _node(_artifact(frame), "up@1")["tier"] == "core"
    assert computed["up"].to_list() == [[0.0, 1.0, 1.0, 2.0, 2.0]]
    assert computed["pennies"].to_list() == [[0.0, 0.4, 0.8, 1.2, 1.6]]


def test_a_rounding_authenticates_itself_with_its_places_in_the_stamp() -> None:
    """Parse what is written, hash what was parsed, reach the node's own stamp."""
    frame = ActuarialFrame(pl.DataFrame({"premium": [1234.567]}))
    frame.billed = frame.premium.round(2)
    node = _node(_artifact(frame), "billed@1")

    assert node["tier"] == "core"
    assert (
        f"sha256:{local_fingerprint(op_node_from_json(node['expr'])).hex()}"
        == node["local_fingerprint"]
    )


# --- accumulation ------------------------------------------------------------


def _a_model_accumulating_a_growth_factor() -> ActuarialFrame:
    """Return the line level 3 opens its account-value roll with.

    One growth factor per period, multiplied along the periods, which is
    the fund's cumulative growth from the start of the projection.
    """
    frame = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"], "factor": [1.5]}))
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="annual"
    )
    frame.growth_factor = frame.factor.projection.broadcast_to_periods()
    frame.cumulative_growth = frame.growth_factor.cum_prod()
    return frame


def test_a_cumulative_growth_factor_records_as_the_accumulation_it_is() -> None:
    """The operation section 11.1 names, not the engine's rendering of a fold."""
    frame = _a_model_accumulating_a_growth_factor()

    assert _tree(frame, "cumulative_growth@1") == {
        "op": "call",
        "name": "cum_prod",
        "args": [{"op": "col", "name": "growth_factor"}],
        "attrs": {"reverse": False},
    }
    assert _node(_artifact(frame), "cumulative_growth@1")["tier"] == "core"


def test_the_direction_an_accumulation_runs_in_is_on_the_record() -> None:
    """A sum of what is still to come is not a sum of what has been."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"], "amount": [1.0]}))
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="annual"
    )
    frame.cashflow = frame.amount.projection.broadcast_to_periods()
    frame.paid_so_far = frame.cashflow.cum_sum()
    frame.still_to_come = frame.cashflow.cum_sum(reverse=True)
    computed = frame.collect()

    assert _tree(frame, "paid_so_far@1")["attrs"] == {"reverse": False}
    assert _tree(frame, "still_to_come@1")["attrs"] == {"reverse": True}
    assert computed["paid_so_far"].to_list() == [[1.0, 2.0, 3.0, 4.0]]
    assert computed["still_to_come"].to_list() == [[4.0, 3.0, 2.0, 1.0]]


def test_the_column_an_accumulation_folded_is_read_as_an_aggregation() -> None:
    """Every period's factor is in every later answer, and the edge says so.

    A cumulative product is not a transformation of this period's value: an
    impact cone drawn through one of these has to sweep in the whole
    period axis, and an edge that called it a transformation would tell a
    reviewer the opposite.
    """
    frame = _a_model_accumulating_a_growth_factor()
    artifact = _artifact(frame)

    folded = [
        edge
        for edge in artifact["edges"]
        if edge["target"] == "cumulative_growth@1"
        and edge["source"] == ("growth_factor@1")
    ]
    narrowed = [
        read
        for node in artifact["nodes"]
        if node["id"] == "cumulative_growth@1"
        for read in node["facets"]["gaspatchio_column_transformation"]["reads"]
        if read["source"] == "growth_factor@1"
    ]

    assert [edge["relationship"] for edge in folded] == ["DIRECT"]
    # And which periods it swept: the run up to the period being computed
    # (section 9), quoted from cum_prod's own direction.
    assert [read["transformations"] for read in narrowed] == [
        [
            {
                "type": "DIRECT",
                "subtype": "AGGREGATION",
                "periods": {"from": "first", "to": 0},
            }
        ]
    ]


def test_an_accumulation_down_the_model_points_uses_the_explicit_escape() -> None:
    """The vocabulary names a fold along the periods, and this is not one.

    ``cum_prod`` on a per-policy column runs down the model points, which is
    a different calculation with a different answer -- and one whose answer
    depends on the order the rows happen to stand in. The record does not
    borrow the period operation's name for it: the explicit engine escape
    records a row accumulation as an engine fragment and says so.
    """
    frame = ActuarialFrame(pl.DataFrame({"factor": [1.1, 1.2, 1.3]}))
    frame.running = frame.factor.polars_native().cum_prod()

    assert _node(_artifact(frame), "running@1")["tier"] == "engine_native"
    assert frame.collect()["running"].to_list() == pytest.approx([1.1, 1.32, 1.716])


def test_accumulating_gives_the_values_it_always_gave() -> None:
    """Both folds, along the periods, against the values they already gave."""
    frame = _a_model_accumulating_a_growth_factor()
    frame.running_sum = frame.growth_factor.cum_sum()
    computed = frame.collect()

    assert computed["cumulative_growth"].to_list()[0] == pytest.approx(
        [1.5, 2.25, 3.375, 5.0625]
    )
    assert computed["running_sum"].to_list() == [[1.5, 3.0, 4.5, 6.0]]


def test_an_accumulation_authenticates_itself() -> None:
    """Parse what is written, hash what was parsed, reach the node's own stamp."""
    frame = _a_model_accumulating_a_growth_factor()
    node = _node(_artifact(frame), "cumulative_growth@1")

    assert node["tier"] == "core"
    assert (
        f"sha256:{local_fingerprint(op_node_from_json(node['expr'])).hex()}"
        == node["local_fingerprint"]
    )


# --- the plain maths ---------------------------------------------------------

# Every one of the seventeen, with the arguments a call needs to be the
# operation at all. Written once because three tests below ask three
# different questions of the same list: what each mints on a per-policy
# column, what each mints on a per-period one, and whether the format can
# account for the node either way.
_ONE_VALUE_AT_A_TIME: Final[dict[str, tuple[tuple[object, ...], str]]] = {
    "abs": ((), "abs"),
    "cbrt": ((), "cbrt"),
    "exp": ((), "exp"),
    "log": ((), "log"),
    "log10": ((), "log10"),
    "log1p": ((), "log1p"),
    "norm_cdf": ((), "norm_cdf"),
    "round_sig_figs": ((3,), "round_sig_figs"),
    "sign": ((), "sign"),
    "sqrt": ((), "sqrt"),
    "fill_null": ((0.0,), "fill_null"),
    "is_finite": ((), "is_finite"),
    "is_infinite": ((), "is_infinite"),
    "is_nan": ((), "is_nan"),
    "is_not_nan": ((), "is_not_nan"),
    "is_not_null": ((), "is_not_null"),
    "is_null": ((), "is_null"),
}

# The seven whose answer is a transcendental function of a binary float, and
# the relative tolerance the specification states for them (11.1.12). The
# other ten are exact and are checked against their values exactly.
_TRANSCENDENTAL: Final[frozenset[str]] = frozenset(
    {"cbrt", "exp", "log", "log10", "log1p", "norm_cdf", "sqrt"}
)
_TOLERANCE: Final[float] = 1e-12


def _a_per_policy_frame() -> ActuarialFrame:
    """Return a frame of one value per policy, the shape a lookup key is in."""
    return ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1", "P2"], "value": [1.5, 8.0]})
    )


def _a_per_period_frame() -> ActuarialFrame:
    """Return a frame of one value per projection period."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"]}))
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.value = frame.month * 1.0 + 1.0
    return frame


@pytest.mark.parametrize(("method", "case"), sorted(_ONE_VALUE_AT_A_TIME.items()))
def test_a_per_policy_value_records_the_operation_and_not_engine_text(
    method: str, case: tuple[tuple[object, ...], str]
) -> None:
    """Seventeen ordinary lines, each recorded as the operation an actuary wrote."""
    args, identifier = case
    frame = _a_per_policy_frame()
    frame.answer = getattr(frame.value, method)(*args)

    tree = _tree(frame, "answer@1")
    assert tree["op"] == "call"
    assert tree["name"] == identifier
    assert tree["args"][0] == {"op": "col", "name": "value"}
    assert _node(_artifact(frame), "answer@1")["tier"] == "core"


@pytest.mark.parametrize(("method", "case"), sorted(_ONE_VALUE_AT_A_TIME.items()))
def test_a_per_period_value_records_the_same_operation(
    method: str, case: tuple[tuple[object, ...], str]
) -> None:
    """The shape changes how the operation reaches the engine, never what it is.

    Pinned beside the per-policy case rather than instead of it: node kind
    here turns on the frame's shape as well as on the call's arguments --
    ``cum_sum`` mints an engine fragment on one shape and the operation on
    the other -- so a claim proved on one shape is no evidence about the
    other.
    """
    args, identifier = case
    frame = _a_per_period_frame()
    frame.answer = getattr(frame.value, method)(*args)

    tree = _tree(frame, "answer@1")
    assert tree["op"] == "call"
    assert tree["name"] == identifier
    assert _node(_artifact(frame), "answer@1")["tier"] == "core"
    assert _node(_artifact(frame), "answer@1")["engines"] == []


@pytest.mark.parametrize("method", sorted(_ONE_VALUE_AT_A_TIME))
def test_one_value_at_a_time_authenticates_itself(method: str) -> None:
    """Parse what is written, hash what was parsed, reach the node's own stamp."""
    args, _ = _ONE_VALUE_AT_A_TIME[method]
    frame = _a_per_policy_frame()
    frame.answer = getattr(frame.value, method)(*args)
    node = _node(_artifact(frame), "answer@1")

    assert (
        f"sha256:{local_fingerprint(op_node_from_json(node['expr'])).hex()}"
        == node["local_fingerprint"]
    )


def test_the_plain_maths_give_the_values_they_always_gave() -> None:
    """Nine lines, per policy, against the answers the sealed path produced.

    The three exact ones are pinned exactly. The six transcendentals are
    pinned to the relative tolerance 11.1.12 states, which is the contract
    a second engine is held to: two libraries computing a logarithm
    correctly may still part company in the last place.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": [1.5, -2.25, 8.0, 1234.567]}))
    frame.magnitude = frame.value.abs()
    frame.direction = frame.value.sign()
    frame.headline = frame.value.round_sig_figs(2)
    frame.root = frame.magnitude.sqrt()
    frame.cube_root = frame.magnitude.cbrt()
    frame.grown = frame.direction.exp()
    frame.natural_log = frame.magnitude.log()
    frame.log_ten = frame.magnitude.log10()
    frame.log_one_plus = frame.magnitude.log1p()
    computed = frame.collect()

    assert computed["magnitude"].to_list() == [1.5, 2.25, 8.0, 1234.567]
    assert computed["direction"].to_list() == [1.0, -1.0, 1.0, 1.0]
    assert computed["headline"].to_list() == [1.5, -2.3, 8.0, 1200.0]
    assert computed["root"].to_list() == pytest.approx(
        [1.224744871391589, 1.5, 2.8284271247461903, 35.136405621520254],
        rel=_TOLERANCE,
    )
    assert computed["cube_root"].to_list() == pytest.approx(
        [1.1447142425533319, 1.3103706971044482, 2.0, 10.727657218553581],
        rel=_TOLERANCE,
    )
    assert computed["natural_log"].to_list() == pytest.approx(
        [0.4054651081081644, 0.8109302162163288, 2.0794415416798357, 7.118475580297523],
        rel=_TOLERANCE,
    )
    assert computed["log_ten"].to_list() == pytest.approx(
        [
            0.17609125905568124,
            0.3521825181113625,
            0.9030899869919435,
            3.091514664086263,
        ],
        rel=_TOLERANCE,
    )
    assert computed["log_one_plus"].to_list() == pytest.approx(
        [0.9162907318741551, 1.1786549963416462, 2.1972245773362196, 7.119285253015384],
        rel=_TOLERANCE,
    )
    assert computed["grown"].to_list() == pytest.approx(
        [2.718281828459045, 0.36787944117144233, 2.718281828459045, 2.718281828459045],
        rel=_TOLERANCE,
    )


def test_the_plain_maths_answer_each_period_s_own_value() -> None:
    """One value at a time, inside the list the values are in."""
    frame = _a_per_period_frame()
    frame.root = frame.value.sqrt()
    frame.direction = frame.value.sign()
    frame.headline = frame.value.round_sig_figs(1)
    computed = frame.collect()

    assert computed["root"].to_list()[0] == pytest.approx(
        [1.0, 1.4142135623730951, 1.7320508075688772, 2.0], rel=_TOLERANCE
    )
    assert computed["direction"].to_list() == [[1.0, 1.0, 1.0, 1.0]]
    assert computed["headline"].to_list() == [[1.0, 2.0, 3.0, 4.0]]


def test_log1p_keeps_its_accuracy_where_that_is_the_whole_point() -> None:
    """The one property 11.1.12 claims for ``log1p``, on an input that tests it.

    ``log1p`` is in the vocabulary as "the form that keeps its accuracy for
    a value near zero", and on 1.5, 2.25, 8.0 and 1234.567 -- the inputs the
    family's value test uses -- a ``log1p`` implemented as ``log(1 + x)`` is
    bit-identical to a correct one. Those inputs would therefore pass an
    engine that had not implemented the operation at all, which makes the
    1e-12 the section states unfalsifiable rather than generous.

    At 1e-12 the two part company. The true value is 1e-12 - 5e-25 to
    within a rounding, which is 9.999999999995e-13; the naive form loses
    the difference between 1 and 1 + x to the float and answers
    1.000088900581841e-12, out by 8.9e-5 relative -- eight orders wider
    than the tolerance. The assertion below is the same 1e-12 the rest of
    the family is held to, and it is now a claim that can fail.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": [1e-12]}))
    frame.log_one_plus = frame.value.log1p()

    assert _tree(frame, "log_one_plus@1")["name"] == "log1p"
    assert frame.collect()["log_one_plus"].to_list() == pytest.approx(
        [9.999999999995e-13], rel=_TOLERANCE
    )


def test_a_logarithm_to_a_named_base_uses_the_explicit_escape() -> None:
    """The vocabulary names the natural logarithm and no other.

    Recording the default base as the literal 2.718281828459045 would put a
    truncated double where the operation is, so a call naming a base stays
    the engine fragment it is and says so. ``log10`` is a function an engine
    has rather than a division by a written-down constant, which is why it
    is an identifier and this is not.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": [8.0]}))
    frame.to_base_two = frame.value.polars_native().log(2)

    assert _node(_artifact(frame), "to_base_two@1")["tier"] == "engine_native"
    assert frame.collect()["to_base_two"].to_list() == pytest.approx([3.0])


# --- one operation, two spellings --------------------------------------------

# Each operation a model author can write two ways, beside the answer both
# ways must give over the signed projection below. The claim is not that
# either spelling is preferable -- it is that they are one line, so neither
# the record nor the answer may turn on which was typed.
_TWO_SPELLINGS: Final[dict[str, list[float]]] = {
    "abs": [1.0, 2.0, 3.0, 4.0],
    "neg": [1.0, -2.0, 3.0, -4.0],
}


def _a_per_period_frame_of_signed_values() -> ActuarialFrame:
    """Return a projection whose periods alternate in sign."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1"], "seed": [[-1.0, 2.0, -3.0, 4.0]]})
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.value = frame.seed
    return frame


def _written_both_ways(frame: ActuarialFrame, operation: str) -> ActuarialFrame:
    """Assign both spellings of ``operation`` over ``frame.value``."""
    if operation == "abs":
        frame.one_way = frame.value.abs()
        frame.other_way = abs(frame.value)
    else:
        frame.one_way = -frame.value
        frame.other_way = frame.value.neg()
    return frame


@pytest.mark.parametrize("operation", sorted(_TWO_SPELLINGS))
def test_two_spellings_of_one_operation_record_the_same_node(
    operation: str,
) -> None:
    """``abs(af.v)`` is ``af.v.abs()``; ``af.v.neg()`` is ``-af.v``.

    Both arrive at the dispatch door under a name of their own -- Python
    reaches a builtin through ``__abs__``, and Polars offers ``neg`` as the
    named form of unary minus -- and each used to take a different path
    from the line it is identical to, which put an ordinary arithmetic
    inside or outside the portable subset depending on how it was typed.
    """
    frame = _written_both_ways(_a_per_policy_frame(), operation)
    artifact = _artifact(frame)

    assert _node(artifact, "one_way@1")["tier"] == "core"
    assert _node(artifact, "other_way@1")["tier"] == "core"
    assert _tree(frame, "one_way@1") == _tree(frame, "other_way@1")


@pytest.mark.parametrize("operation", sorted(_TWO_SPELLINGS))
def test_two_spellings_of_one_operation_both_run_over_periods(
    operation: str,
) -> None:
    """The disagreement was not only about the record: one spelling did not run.

    Polars has no ``abs`` or ``neg`` kernel for a ``list`` column, so on a
    projection the unrouted spelling of each raised
    ``InvalidOperationError`` at collect while its twin answered. Two ways
    of writing one line, one of which failed the model.
    """
    frame = _written_both_ways(_a_per_period_frame_of_signed_values(), operation)
    computed = frame.collect()

    assert computed["one_way"].to_list() == computed["other_way"].to_list()
    assert computed["one_way"].to_list() == [_TWO_SPELLINGS[operation]]


# --- the comparisons, written both ways --------------------------------------

# Each comparison's two spellings -- the operator and Polars' own name for
# it -- beside the answer both give over a projection whose periods run
# 1, 2, 3, 4, tested against 2. The operator emits the comparison node and
# the method reached Polars' own kernel, which has none for a ``list``
# column, so before they were one line the second raised ``SchemaError``
# on every projection while the first answered.
_COMPARISON_SPELLINGS: Final[
    dict[str, tuple[Callable[[Any], Any], Callable[[Any], Any], list[float]]]
] = {
    "eq": (lambda v: v == 2, lambda v: v.eq(2), [0.0, 1.0, 0.0, 0.0]),
    "ge": (lambda v: v >= 2, lambda v: v.ge(2), [0.0, 1.0, 1.0, 1.0]),
    "gt": (lambda v: v > 2, lambda v: v.gt(2), [0.0, 0.0, 1.0, 1.0]),
    "le": (lambda v: v <= 2, lambda v: v.le(2), [1.0, 1.0, 0.0, 0.0]),
    "lt": (lambda v: v < 2, lambda v: v.lt(2), [1.0, 0.0, 0.0, 0.0]),
    "ne": (lambda v: v != 2, lambda v: v.ne(2), [1.0, 0.0, 1.0, 1.0]),
}


def _a_projection_counting_its_periods() -> ActuarialFrame:
    """Return a projection whose value runs 1, 2, 3, 4 -- one per period."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"]}))
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.value = frame.month * 1.0 + 1.0
    return frame


@pytest.mark.parametrize("comparison", sorted(_COMPARISON_SPELLINGS))
def test_both_spellings_of_a_comparison_run_over_periods(comparison: str) -> None:
    """``af.month == af.policy_term * 12`` is this framework's maturity idiom.

    Written Polars' other way -- ``af.month.eq(...)`` -- it reached the
    engine's comparison kernel, which has none for a ``list`` column, and
    raised ``SchemaError: could not evaluate comparison`` on every
    projection. The most-written family in an actuarial model was the one
    that could not be written the engine's way.
    """
    operator_form, method_form, expected = _COMPARISON_SPELLINGS[comparison]
    frame = _a_projection_counting_its_periods()
    frame.one_way = operator_form(frame.value)
    frame.other_way = method_form(frame.value)
    computed = frame.collect()

    assert computed["one_way"].to_list() == [expected]
    assert computed["other_way"].to_list() == [expected]


@pytest.mark.parametrize("comparison", sorted(_COMPARISON_SPELLINGS))
def test_both_spellings_of_a_comparison_record_the_same_node(
    comparison: str,
) -> None:
    """Per policy neither raised, and the two disagreed quietly instead.

    The operator recorded the comparison and answered with the 0/1
    indicator; the method recorded an engine fragment and answered with a
    Boolean. Two ways of writing one line, two tiers and two types.
    """
    operator_form, method_form, _ = _COMPARISON_SPELLINGS[comparison]
    frame = _a_per_policy_frame()
    frame.one_way = operator_form(frame.value)
    frame.other_way = method_form(frame.value)
    artifact = _artifact(frame)

    assert _node(artifact, "one_way@1")["tier"] == "core"
    assert _node(artifact, "other_way@1")["tier"] == "core"
    assert _tree(frame, "one_way@1") == _tree(frame, "other_way@1")


def test_a_null_safe_comparison_is_not_a_second_spelling_of_one() -> None:
    """``eq_missing`` and ``ne_missing`` read like two more and are not.

    A null compares as a value in them, so against 1.0 they answer where
    ``eq`` and ``ne`` answer null. The operator vocabulary has no
    null-safe comparison to carry that, so routing either to its
    near-namesake would record a different calculation from the one
    written and change the answer for every missing value. Both stay the
    engine fragments they honestly are.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": [1.0, None, 2.0]}))
    frame.plain = frame.value.eq(1.0)
    frame.null_safe = frame.value.polars_native().eq_missing(1.0)
    frame.null_safe_negated = frame.value.polars_native().ne_missing(1.0)
    artifact = _artifact(frame)
    computed = frame.collect()

    assert _node(artifact, "plain@1")["tier"] == "core"
    assert _node(artifact, "null_safe@1")["tier"] == "engine_native"
    assert _node(artifact, "null_safe_negated@1")["tier"] == "engine_native"
    assert computed["plain"].to_list() == [1.0, None, 0.0]
    assert computed["null_safe"].to_list() == [True, False, False]
    assert computed["null_safe_negated"].to_list() == [False, True, True]


def test_boolean_columns_have_both_declared_logical_operators() -> None:
    """Boolean AND and OR have explicit spellings independent of metaclass union."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "in_force": [True, True, False, False],
                "selected": [True, False, True, False],
            }
        )
    )
    frame.both = frame.in_force & frame.selected

    assert frame.collect()["both"].to_list() == [True, False, False, False]
    frame.either = frame.in_force | frame.selected
    assert frame.collect()["either"].to_list() == [True, True, True, False]


def test_a_mask_combines_with_another_predicate_through_either_operator() -> None:
    """Both operators combine an existing list mask with another predicate."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1"],
                "seed": [[60.0, 65.0, 70.0, 75.0]],
                "sum_assured": [500000.0],
                "duration": [3],
            }
        )
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="annual"
    )
    frame.age = frame.seed
    frame.either = ((frame.age >= 65) & (frame.sum_assured > 400000)) | (
        frame.duration < 5
    )

    assert frame.collect()["either"].to_list() == [[1.0, 1.0, 1.0, 1.0]]

    same_shape_with_and = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"]}))
    same_shape_with_and = same_shape_with_and.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="annual"
    )
    same_shape_with_and.age = same_shape_with_and.month * 1.0 + 60.0
    same_shape_with_and.sum_assured = 500000.0
    same_shape_with_and.duration = 3
    same_shape_with_and.both = (
        (same_shape_with_and.age >= 65) & (same_shape_with_and.sum_assured > 400000)
    ) & (same_shape_with_and.duration < 5)

    assert same_shape_with_and.collect()["both"].to_list() == [[0.0, 1.0, 1.0, 1.0]]


# --- what fills a gap --------------------------------------------------------


def test_the_fill_is_an_operand_so_a_varying_one_declares_its_read() -> None:
    """A fill that reads a column stands in the tree, like any other operand.

    This is why the fill is not an attribute: an attribute is one flat typed
    value and could not carry a column at all, so a vocabulary that put it
    there would record the constant fills and silently drop every varying
    one.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"rate": [0.01, None], "scheme_default": [0.02, 0.02]})
    )
    frame.filled = frame.rate.fill_null(frame.scheme_default)
    node = _node(_artifact(frame), "filled@1")

    assert node["tier"] == "core"
    assert sorted(node["reads"]) == ["rate", "scheme_default"]
    assert frame.collect()["filled"].to_list() == [0.01, 0.02]


def test_a_fill_the_actuary_wrote_in_the_engine_is_still_declared() -> None:
    """The operation is recognised; whose expression the fill is, is not changed."""
    frame = ActuarialFrame(pl.DataFrame({"rate": [0.01, None]}))
    frame.filled = frame.rate.fill_null(pl.col("rate").mean())
    node = _node(_artifact(frame), "filled@1")

    assert node["tier"] == "engine_native"
    assert node["expr"]["name"] == "fill_null"
    assert node["expr"]["args"][1]["op"] == "engine_native"


def test_a_fill_from_the_neighbouring_rows_is_a_different_operation() -> None:
    """A strategy fills from the rows around it, not from a value.

    Its answer depends on the order the rows happen to stand in, which is
    not the operation this vocabulary names, so the line uses the explicit
    engine escape.
    """
    frame = ActuarialFrame(pl.DataFrame({"rate": [0.01, None, 0.03]}))
    frame.carried = frame.rate.polars_native().fill_null(strategy="forward")

    assert _node(_artifact(frame), "carried@1")["tier"] == "engine_native"
    assert frame.collect()["carried"].to_list() == [0.01, 0.01, 0.03]


def test_filling_a_per_period_column_fills_each_period_s_own_gap() -> None:
    """The missing periods take the fill, and the present ones are untouched."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1"], "seed": [[1.0, None, 3.0, None]]})
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.rate = frame.seed
    frame.filled = frame.rate.fill_null(0.0)

    assert _node(_artifact(frame), "filled@1")["tier"] == "core"
    assert frame.collect()["filled"].to_list() == [[1.0, 0.0, 3.0, 0.0]]


def test_a_per_period_fill_column_fills_each_period_one_value_at_a_time() -> None:
    """A fill that reads a column fills the same period, as a value fill does (11.1.13).

    It used to fill at the row: a policy whose whole run of periods was
    missing took the fill column's run, and P1's single missing period was
    left alone. Each period is filled one value at a time now, and a policy
    with no run at all has no period to fill and stays null, as it does
    under a value fill.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                "seed": [[1.0, None, 3.0, 4.0], None],
                "backup": [[9.0, 9.0, 9.0, 9.0], [7.0, 7.0, 7.0, 7.0]],
            }
        )
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.rate = frame.seed
    frame.fallback = frame.backup
    frame.filled = frame.rate.fill_null(frame.fallback)
    node = _node(_artifact(frame), "filled@1")

    assert node["tier"] == "core"
    assert sorted(node["reads"]) == ["fallback@1", "rate@1"]
    assert frame.collect()["filled"].to_list() == [[1.0, 9.0, 3.0, 4.0], None]


def test_a_per_policy_column_fills_every_missing_period_of_its_policy() -> None:
    """Every missing period of this policy takes the scheme's own default.

    The line an actuary would most expect to work failed as Polars'
    ``SchemaError: failed to determine supertype``; the fill is an operand
    (11.1.13), and it fills the policy's missing periods as ``fill_nan``'s
    does.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1"],
                "seed": [[1.0, None, 3.0, 4.0]],
                "scheme_default": [0.02],
            }
        )
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.rate = frame.seed
    frame.filled = frame.rate.fill_null(frame.scheme_default)

    assert frame.collect()["filled"].to_list() == [[1.0, 0.02, 3.0, 4.0]]


# --- the six tests of a value that is not there ------------------------------


def test_a_null_and_a_nan_are_two_different_absences() -> None:
    """Two operations rather than one with a flag, because they answer differently.

    A null was never there; a NaN is a value an arithmetic produced and
    cannot name. A model that tests one where it meant the other passes
    every row it has data for.
    """
    frame = ActuarialFrame(pl.DataFrame({"rate": [0.01, None, float("nan")]}))
    frame.missing = frame.rate.is_null()
    frame.unnameable = frame.rate.is_nan()
    computed = frame.collect()

    assert computed["missing"].to_list() == [False, True, False]
    assert computed["unnameable"].to_list() == [False, None, True]


def _a_per_period_frame_of_absences() -> ActuarialFrame:
    """Return a projection whose second period has no value at all."""
    frame = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1"], "seed": [[1.0, None, 3.0, 4.0]]})
    )
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.rate = frame.seed
    return frame


def test_the_negations_are_their_own_operations_and_keep_their_type() -> None:
    """``not_(is_nan(x))`` is not ``is_not_nan(x)``, and the per-period type says so.

    ``not_`` has no element-wise negation that reaches inside a ``list``, so
    it negates arithmetically as ``1.0 - mask``, and the subtraction is what
    changes the type. What the two direct tests hand back is pinned here
    and what the composition hands back in the test after it, so the reason
    they are separate identifiers is measured rather than asserted.
    """
    frame = _a_per_period_frame_of_absences()
    frame.present = frame.rate.is_not_null()
    frame.nameable = frame.rate.is_not_nan()
    computed = frame.collect()

    assert _tree(frame, "present@1")["name"] == "is_not_null"
    assert _tree(frame, "nameable@1")["name"] == "is_not_nan"
    assert computed.schema["present"] == pl.List(pl.Boolean)
    assert computed.schema["nameable"] == pl.List(pl.Boolean)
    assert computed["present"].to_list() == [[True, False, True, True]]
    assert computed["nameable"].to_list() == [[True, None, True, True]]


def test_the_composition_a_producer_must_not_record_changes_the_type() -> None:
    """``not_(is_nan(x))`` answers ``List(Float64)`` where ``is_not_nan`` is Boolean.

    This is the composition 11.1.13 forbids a producer from recording, run
    rather than described. It is built through ``emit.call`` because that is
    a direct way to build the composition. An author can also write it with
    ``~``, as the next test shows. A producer must preserve that distinction
    rather than rewrite the separate ``is_not_nan`` identifier.

    The population is the same either way: the null period stays null and
    every other period says "not a NaN", so nothing about the values argues
    for six identifiers over four. The type does. A per-period predicate
    that arrives as a number is a different thing to feed onward from one
    that arrives as a mask.
    """
    frame = _a_per_period_frame_of_absences()
    frame.composed = emit.call(
        "not_", (frame.rate.is_nan(),), frame, kind="boolean_mask"
    )
    computed = frame.collect()

    assert computed.schema["composed"] == pl.List(pl.Float64)
    assert computed["composed"].to_list() == [[1.0, None, 1.0, 1.0]]


def test_negating_an_absence_test_records_the_composition_as_written() -> None:
    """An authored inversion records not_(is_nan), retaining its mask dtype.

    The whole recorded tree is compared, because the claim in the name is
    about its shape and not about the column existing: a producer that
    collapsed ``~is_nan(x)`` to the separate ``is_not_nan`` identifier
    would hand back the same values and fail here, which is the distinction
    the test above this one measures from the other side.
    """
    frame = _a_per_period_frame_of_absences()
    frame.hand_negated = ~(frame.rate.is_nan())

    computed = frame.collect()
    assert computed.schema["hand_negated"] == pl.List(pl.Float64)
    assert computed["hand_negated"].to_list() == [[1.0, None, 1.0, 1.0]]
    assert _tree(frame, "hand_negated@1") == {
        "op": "call",
        "name": "not_",
        "args": [
            {
                "op": "call",
                "name": "is_nan",
                "args": [{"op": "col", "name": "rate"}],
                "attrs": {},
            }
        ],
        "attrs": {},
    }


def test_the_finiteness_tests_answer_what_they_always_answered() -> None:
    """Infinite, NaN, and finite, each told apart from the other two.

    A missing value is none of the three, and the last column of each is
    where 11.1.13's rule about it is pinned: the four tests that read the
    number answer null for a value that is not there, rather than asserting
    something about a value the model does not have. Only the two tests of
    presence itself answer without a null.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"factor": [1.0, float("inf"), -float("inf"), float("nan"), None]})
    )
    frame.finite = frame.factor.is_finite()
    frame.unbounded = frame.factor.is_infinite()
    frame.unnameable = frame.factor.is_nan()
    frame.nameable = frame.factor.is_not_nan()
    frame.present = frame.factor.is_not_null()
    computed = frame.collect()

    assert computed["finite"].to_list() == [True, False, False, False, None]
    assert computed["unbounded"].to_list() == [False, True, True, False, None]
    assert computed["unnameable"].to_list() == [False, False, False, True, None]
    assert computed["nameable"].to_list() == [True, True, True, False, None]
    assert computed["present"].to_list() == [True, True, True, True, False]


def test_a_whole_number_column_answers_the_tests_rather_than_failing() -> None:
    """A whole number cannot hold a NaN, and the test says so instead of failing.

    The vocabulary carries no dtype, so the identifier alone does not say
    which of the two answers an engine gives. What the artifact carries
    beside it does: every node records the dtype it resolved to, and the
    column this reads records ``i64``. 11.1.13 states the answer so a
    consumer does not have to infer it from one engine's habit.
    """
    frame = ActuarialFrame(pl.DataFrame({"duration": [3, 0]}))
    frame.unnameable = frame.duration.is_nan()
    frame.finite = frame.duration.is_finite()
    artifact = _artifact(frame)
    computed = frame.collect()

    assert computed["unnameable"].to_list() == [False, False]
    assert computed["finite"].to_list() == [True, True]
    assert _node(artifact, "duration")["dtype"] == "i64"
    assert _node(artifact, "unnameable@1")["dtype"] == "bool"


# Every whole-number type Polars offers, which is the width 11.1.13's rule
# is stated over. The rule is one sentence about a family, and one member
# of it is no evidence about the other seven.
_WHOLE_NUMBERS: Final[tuple[pl.DataType, ...]] = (
    pl.Int8(),
    pl.Int16(),
    pl.Int32(),
    pl.Int64(),
    pl.UInt8(),
    pl.UInt16(),
    pl.UInt32(),
    pl.UInt64(),
)

# Three types that cannot hold a NaN either and are not whole numbers, each
# beside the name the engine prints for it in a refusal. The rule stops at
# the whole numbers because these are where it stops being true, and a rule
# stated wider than it holds is a rule a second engine implements into a
# disagreement. A fixed-point decimal is not among them: it is read as the
# double it denotes where it enters the frame, and a double answers.
_NOT_A_NUMBER_AT_ALL: Final[tuple[tuple[str, pl.Series], ...]] = (
    ("bool", pl.Series("value", [True, False], dtype=pl.Boolean)),
    ("str", pl.Series("value", ["a", "b"], dtype=pl.String)),
    ("date", pl.Series("value", [datetime.date(2026, 1, 1)] * 2, dtype=pl.Date)),
)

# The four tests that read the number, and what each answers over a value
# of a type that cannot hold a NaN or an infinity.
_TRIVIAL_ANSWERS: Final[tuple[tuple[str, bool], ...]] = (
    ("is_nan", False),
    ("is_infinite", False),
    ("is_not_nan", True),
    ("is_finite", True),
)

_TESTS_THAT_READ_THE_NUMBER: Final[tuple[str, ...]] = tuple(
    method for method, _ in _TRIVIAL_ANSWERS
)


@pytest.mark.parametrize("dtype", _WHOLE_NUMBERS)
@pytest.mark.parametrize(("method", "answer"), _TRIVIAL_ANSWERS)
def test_every_whole_number_type_answers_the_same_way(
    dtype: pl.DataType, method: str, *, answer: bool
) -> None:
    """The rule 11.1.13 states holds across the whole family, not on i64 alone."""
    frame = ActuarialFrame(
        pl.DataFrame({"value": pl.Series("value", [3, 0], dtype=dtype)})
    )
    frame.answer = getattr(frame.value, method)()

    assert frame.collect()["answer"].to_list() == [answer, answer]


@pytest.mark.parametrize(("printed_as", "series"), _NOT_A_NUMBER_AT_ALL)
@pytest.mark.parametrize("method", _TESTS_THAT_READ_THE_NUMBER)
def test_a_type_that_is_not_a_number_is_where_the_rule_stops(
    printed_as: str, series: pl.Series, method: str
) -> None:
    """These three refuse, which is why 11.1.13 does not promise an answer for them.

    A Boolean, a string and a date cannot hold a NaN any more
    than an integer can, and the trivially-true answer would be as
    available. This producer does not give it -- it refuses, before this
    vocabulary reached these names and after -- so a rule saying "they do
    not fail" for every type that cannot hold one would be a rule stating
    the opposite of what its own reference producer does, and a second
    engine implementing it literally would answer where this one raises.
    The rule is narrowed to the whole numbers, and this is the measurement
    that narrows it.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": series}))
    frame.answer = getattr(frame.value, method)()

    with pytest.raises(pl.exceptions.InvalidOperationError, match=printed_as):
        frame.collect()


# --- a literal the tree cannot hold ------------------------------------------

# Four of the five direct operations that build a literal, written with a
# non-finite number where the literal goes, beside the answer the engine
# gives for it. A NaN and an infinity are not values the op-tree can record
# -- ``Lit`` refuses them, which is what makes ``af.value * float("nan")``
# raise at the line that wrote it -- and none of these is that line. Each uses
# the explicit engine escape, so the node seals and the model runs.
#
# ``cut`` is the fifth operation and is not here, because for it only the
# first half of that is true. Through the escape, the engine refuses the band
# rather than banding with it (``breaks cannot be NaN``, ``don't include -inf
# in breaks``). That is the engine's answer, so it is pinned below under its
# own claim rather than under this one.
_A_LITERAL_THE_TREE_CANNOT_HOLD: Final[
    dict[str, tuple[str, tuple[object, ...], list]]
] = {
    "fill_null": ("rate", (float("nan"),), [0.01, float("nan"), 0.03]),
    "fill_null_from_an_infinity": ("rate", (float("inf"),), [0.01, float("inf"), 0.03]),
    "clip": ("value", (float("nan"), 8.0), [1.0, 8.0, 2.0]),
    "is_in": ("value", ([1.0, float("nan")],), [True, False, False]),
    "replace": ("value", ({float("nan"): 1.0},), [1.0, 9.0, 2.0]),
}

_CALLED: Final[dict[str, str]] = {
    "fill_null": "fill_null",
    "fill_null_from_an_infinity": "fill_null",
    "clip": "clip",
    "is_in": "is_in",
    "replace": "replace",
}


@pytest.mark.parametrize("case", sorted(_A_LITERAL_THE_TREE_CANNOT_HOLD))
def test_a_literal_the_tree_cannot_hold_seals_the_node_and_still_computes(
    case: str,
) -> None:
    """An engine escape can compute a value the core tree cannot record.

    Every one of these ran before the vocabulary reached the name, and
    the direct operation refuses these forms because it cannot record them.
    The explicit engine escape keeps the computation available and seals the
    node as the engine fragment it is.

    ``fill_null`` is here because it regressed -- it worked, then raised.
    ``clip`` is here because it never worked and nothing said so: it
    carried the same defect from the day it was recognised, and only
    ``fill_null`` moved because only ``fill_null`` was new.
    """
    column, args, expected = _A_LITERAL_THE_TREE_CANNOT_HOLD[case]
    frame = ActuarialFrame(
        pl.DataFrame({"rate": [0.01, None, 0.03], "value": [1.0, 9.0, 2.0]})
    )
    escaped = getattr(frame, column).polars_native()
    frame.answer = getattr(escaped, _CALLED[case])(*args)

    assert _node(_artifact(frame), "answer@1")["tier"] == "engine_native"
    assert frame.collect()["answer"].to_list() == pytest.approx(expected, nan_ok=True)


# A band whose breakpoints hold a non-finite number, written both ways the
# recogniser distinguishes: with labels, and without. The two used to part
# company here -- see below -- and the claim is that they no longer do.
_A_BAND_THE_ENGINE_WILL_NOT_CUT: Final[dict[str, dict[str, object]]] = {
    "bare": {},
    "labelled": {"labels": ["under", "between", "over"]},
}


@pytest.mark.parametrize("spelling", sorted(_A_BAND_THE_ENGINE_WILL_NOT_CUT))
def test_a_band_the_tree_cannot_hold_uses_escape_and_the_engine_refuses(
    spelling: str,
) -> None:
    """Escaped ``cut`` leaves a non-finite band to the engine's refusal.

    The engine will not band with a breakpoint that is not a place on the
    line, so unlike ``fill_null`` or ``clip`` there is no answer waiting
    behind the explicit escape. That is the engine's refusal and not this
    vocabulary's, and it is named here so the family's claim is not read
    as covering a case where it does not hold.

    **The two spellings used to disagree about which refusal fired.**
    ``not lower < upper`` is true of every comparison against a NaN, so
    with labels written the ordering refusal reached it first and told the
    author that *"nan does not sit above 1.0"* -- an instruction to
    reorder breakpoints that were already in order, for a band the engine
    was going to refuse by name anyway.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": [1.0, 9.0, 2.0]}))
    frame.answer = frame.value.polars_native().cut(
        [1.0, float("nan")], **_A_BAND_THE_ENGINE_WILL_NOT_CUT[spelling]
    )

    with pytest.raises(pl.exceptions.ComputeError, match="breaks cannot be NaN"):
        frame.collect()


def test_a_non_finite_number_written_into_a_formula_still_refuses_at_that_line() -> (
    None
):
    """The refusal that must survive: an arithmetic seeded with a NaN.

    The seam above is a recogniser asking whether a value can be recorded
    and being answered rather than thrown at. It is not a relaxation of
    what a literal may be: an operator dunder has nowhere else to leave
    the line, and a NaN multiplied through a projection is a bug at its
    own line, not an operation the vocabulary declines to name.
    """
    frame = ActuarialFrame(pl.DataFrame({"value": [1.0, 9.0]}))

    with pytest.raises(ValueError, match="is not finite"):
        frame.scaled = frame.value * float("nan")


def test_a_non_finite_configuration_refuses_at_the_line_that_wrote_it() -> None:
    """An operand and a configuration are both what a node is made of.

    The rule against a NaN is a rule about the node, not about which half
    held it, and only the operands were being held to it: an accumulation
    started at one built, ran, and put a NaN at the head of every policy's
    survival curve. The artifact then refused to write, because JSON has
    no NaN, with ``Out of range float values are not JSON compliant``
    naming neither the column nor the line -- the same rule arriving after
    the whole model instead of at the argument, and the run in between the
    one whose numbers a reader would have believed.
    """
    frame = ActuarialFrame(pl.DataFrame({"policy_id": ["P1"]}))
    frame = frame.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    frame.qx = frame.month * 0.0 + 0.01

    with pytest.raises(ValueError, match="is not finite") as refused:
        frame.survival = frame.qx.projection.cumulative_survival(start_at=float("nan"))

    assert "projection.cumulative_survival" in str(refused.value)
    assert "start_at" in str(refused.value)


# --- the list reductions -----------------------------------------------------


def _a_model_taking_a_present_value() -> ActuarialFrame:
    """Return the flagship's own PV line, in miniature.

    ``(cashflow * discount_factor).list.sum()`` is what an actuary writes
    for a present value and what a supervisory reader asks for by name. The
    whole line -- the multiplication included -- reached the record as one
    engine fragment before this vocabulary reached the reduction.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "claims": [[100.0, 200.0, 300.0], [50.0, 60.0, 70.0]],
                "disc_factors": [[1.0, 0.95, 0.90], [1.0, 0.95, 0.90]],
            }
        )
    )
    frame.pv_claims = (frame.claims * frame.disc_factors).list.sum()
    return frame


def test_a_present_value_records_as_a_fold_and_not_as_engine_text() -> None:
    """The fold is a named operation and the multiplication reappears beneath it.

    Before, the node said: this is Polars text, and the columns it declares
    it reads are ``claims`` and ``disc_factors``. The ``mul`` the actuary
    wrote was invisible inside the fragment, and a node computing a
    discounted present value told a second implementation to give up.
    """
    frame = _a_model_taking_a_present_value()

    assert _tree(frame, "pv_claims@1") == {
        "op": "call",
        "name": "sum",
        "args": [
            {
                "op": "binop",
                "kind": "mul",
                "left": {"op": "col", "name": "claims"},
                "right": {"op": "col", "name": "disc_factors"},
            }
        ],
        "attrs": {},
    }
    node = _node(_artifact(frame), "pv_claims@1")
    assert node["tier"] == "core"
    assert node["engines"] == []


def test_the_present_value_is_the_number_it_always_was() -> None:
    """A change to what is recorded and not to what is computed."""
    frame = _a_model_taking_a_present_value()

    assert frame.collect()["pv_claims"].to_list() == [
        pytest.approx(100.0 + 200.0 * 0.95 + 300.0 * 0.90),
        pytest.approx(50.0 + 60.0 * 0.95 + 70.0 * 0.90),
    ]


def test_the_answer_of_a_fold_is_not_the_shape_of_its_operand() -> None:
    """The first operations in this vocabulary whose result changes shape.

    Nothing on the record says so: the node states the shape of its own
    answer and its operand's node states the operand's, so a third
    statement would be free to disagree with the two that exist. Section
    11.1.14 says it in prose instead, which is what this pins.
    """
    artifact = _artifact(_a_model_taking_a_present_value())

    assert _node(artifact, "claims")["shape"] == "list"
    assert _node(artifact, "pv_claims@1")["shape"] == "scalar"


@pytest.mark.parametrize(
    ("method", "identifier", "carried_on"),
    [
        pytest.param("sum", "sum", 80.0, id="sum"),
        pytest.param("mean", "mean", 80.0 / 3, id="mean"),
        pytest.param("min", "min", 10.0, id="min"),
        pytest.param("max", "max", 40.0, id="max"),
    ],
)
def test_each_fold_records_its_own_identifier_and_nulls_a_lost_period(
    method: str, identifier: str, carried_on: float
) -> None:
    """All four fold one policy's own periods, and a lost period nulls the total.

    A total is one number, and one number cannot say a period went missing
    underneath it -- so each of the four says it in the only way a total can,
    by answering null. ``carried_on`` is the answer the same four periods
    give once the hole is taken out of them, which is what this fold used to
    report over the run that still had it.
    """
    frame = ActuarialFrame(
        pl.DataFrame({"cashflow": [[10.0, None, 30.0, 40.0], [10.0, 30.0, 40.0]]})
    )
    frame.folded = getattr(frame.cashflow.list, method)()

    assert _tree(frame, "folded@1") == {
        "op": "call",
        "name": identifier,
        "args": [{"op": "col", "name": "cashflow"}],
        "attrs": {},
    }
    assert frame.collect()["folded"].to_list() == [None, pytest.approx(carried_on)]


def test_a_read_into_a_fold_is_an_aggregation_and_not_a_transformation() -> None:
    """Every period is in the answer, so an impact cone has to sweep the axis in.

    A reviewer told this was a transformation of one period's value would
    be told the opposite of the truth. The relationship is on the edge and
    the narrowing beside it, the same as ``cum_sum``'s.
    """
    artifact = _artifact(_a_model_taking_a_present_value())
    narrowing = _node(artifact, "pv_claims@1")["facets"][
        "gaspatchio_column_transformation"
    ]

    assert {
        read["source"]: read["transformations"][0]["subtype"]
        for read in narrowing["reads"]
    } == {"claims": "AGGREGATION", "disc_factors": "AGGREGATION"}
    assert {
        edge["relationship"]
        for edge in artifact["edges"]
        if edge["target"] == "pv_claims@1"
    } == {"DIRECT"}


def test_a_fold_carrying_an_argument_stays_on_the_engine_path() -> None:
    """Polars' own list folds take none, so a call with one cannot run.

    Minting a node for a call the engine itself refuses would record a
    calculation nothing can reproduce. This is the accumulation's existing
    discipline, reused, and it is checked at the door rather than trusted.
    """
    from gaspatchio._semantic.ir import Col
    from gaspatchio.frame.lowering.methods import core_list_call

    receiver = Col("cashflow")

    assert core_list_call("sum", receiver, (), {}) is not None
    assert core_list_call("sum", receiver, (1,), {}) is None
    assert core_list_call("sum", receiver, (), {"reverse": True}) is None


def test_a_list_method_the_vocabulary_does_not_name_is_left_alone() -> None:
    """The door is four names wide, and everything else takes the path it took.

    ``eval`` is the escape hatch a model reaches for when the vocabulary
    has nothing, and it must keep working exactly as it did -- unrecognised,
    computed, and recorded as the engine text it is.
    """
    from gaspatchio._semantic.ir import Col
    from gaspatchio.frame.lowering.methods import core_list_call

    assert core_list_call("eval", Col("cashflow"), (), {}) is None
    assert core_list_call("sort", Col("cashflow"), (), {}) is None

    frame = ActuarialFrame(pl.DataFrame({"cashflow": [[10.0, 20.0, 30.0]]}))
    frame.running = frame.cashflow.polars_native().list.eval(pl.element().cum_sum())

    assert frame.collect()["running"].to_list() == [[10.0, 30.0, 60.0]]
    assert _node(_artifact(frame), "running@1")["tier"] == "engine_native"


def test_a_fold_of_something_with_no_period_axis_is_not_this_operation() -> None:
    """The shape guard, which the string namespace's own door does not have.

    It is only *because* the receiver is a per-period column that this is
    the period axis at all. A fold down the model points is a different
    calculation whose answer depends on the order the rows stand in, and
    this vocabulary does not name it -- so where the shape does not resolve
    to ``list`` the door declines and the call goes where it always went.
    """
    per_policy = ActuarialFrame(pl.DataFrame({"premium": [100.0, 200.0]}))
    assert getattr(per_policy.premium, "shape", None) == "scalar"
    with pytest.raises(TypeError, match="polars_native"):
        per_policy.premium.list.sum()
    per_policy.total = per_policy.premium.polars_native().list.sum()

    # Declined at the door, so the node is the engine text it always was --
    # and the engine still refuses the line, which is the answer the model
    # author already got and not a new one this vocabulary invented. The
    # plan cannot be typed, so an engine is handed no document of it.
    assert (
        _node(_artifact(per_policy, profile="audit"), "total@1")["tier"]
        == "engine_native"
    )
    with pytest.raises(ValueError, match="cannot state the type of its plan"):
        _artifact(per_policy)
    with pytest.raises(pl.exceptions.InvalidOperationError):
        per_policy.collect()

    # The same method on a per-period column is the operation, and is minted.
    per_period = ActuarialFrame(pl.DataFrame({"premium": [[100.0, 200.0]]}))
    assert getattr(per_period.premium, "shape", None) == "list"
    per_period.total = per_period.premium.list.sum()

    assert _node(_artifact(per_period), "total@1")["tier"] == "core"


def test_all_four_folds_read_a_whole_axis_and_not_one_period_of_it() -> None:
    """An impact cone over any of the four has to sweep the period axis in.

    The test above shows what that membership buys, on ``sum``: the reads
    under a present value are aggregations rather than transformations of
    one period's value. This says the other three are in the same set, so
    none of them can be the transformation a reviewer would be told the
    opposite of the truth about.

    That the four are rows of the published vocabulary at ``core`` is said
    once, in the table's own census -- ``test_vocabulary.py`` holds
    ``TIERS`` to the row's tier column and ``test_tiers.py``'s
    ``test_every_classified_operation_is_core`` holds every row of it to
    ``core``.
    """
    from gaspatchio.frame.graph.edges import AGGREGATING_CALLS

    for identifier in ("sum", "mean", "min", "max"):
        assert identifier in AGGREGATING_CALLS
