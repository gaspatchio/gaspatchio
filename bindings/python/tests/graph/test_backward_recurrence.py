# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A workbook's rollback converts as one portable line, not three engine fragments.

A spreadsheet writes a reserve whose row reads the row below it --
``V[t] = v[t] * V[t+1] + cf[t]`` -- and the discovery reference told a
converter to write it as "reverse, accumulate, reverse back". The proxy could
not spell the reversal, so it went through ``polars_native()``: three of the
line's nodes became engine text, the recurrence between them could not run
anywhere the text could not, and ``validate --engine jax`` refused the model.

Two spellings close it (section 11.1.20 and section 11.1.41):

* ``projection.accumulate(..., reverse=True)`` -- the backward recurrence as one
  named node, the workbook's own rollback;
* ``list.reverse()`` -- declared, so a rollback that is *not* linear can still
  be written as reverse, a forward calculation, and reverse back.

The two agree to the bit on the same operands, because the first is the second
composed in the lowering.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Call, Col
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.edges import Periods, ReadClaim, claim_over, classify_reads
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.trace_voice import sentence_for
from gaspatchio.frame.lowering.polars import lower_polars as lower

AGGREGATION = ("DIRECT", "AGGREGATION")


def _bits(rows: list[list[float | None] | None]) -> list[list[str | None] | None]:
    """Return every double as its exact bit pattern, so equality is to the bit."""
    return [
        None if row is None else [None if x is None else float(x).hex() for x in row]
        for row in rows
    ]


def _collected(af: ActuarialFrame, column: str) -> list[Any]:
    return af.collect()[column].to_list()


# --- A2: the backward recurrence --------------------------------------------


def test_the_workbook_rollback_is_one_line() -> None:
    """V[t] = v * V[t+1] + cf[t], from nought after each policy's own last period."""
    af = ActuarialFrame(
        {"cf": [[1.0, 2.0, 3.0], [10.0], []], "v": [[0.9, 0.9, 0.9], [0.5], []]}
    )
    af.reserve = af.cf.projection.accumulate(
        initial=0.0, multiplier=af.v, addend=af.cf, reverse=True
    )
    assert _collected(af, "reserve") == [[5.23, 4.7, 3.0], [10.0], []]


def test_the_clause_s_own_examples() -> None:
    """Section 11.1.20's printed answers, both directions, to the bit."""
    af = ActuarialFrame(
        {
            "m": [[2.0, None, 3.0, 4.0], [2.0, 2.0, 2.0, 2.0]],
            "a": [[1.0, 1.0, 1.0, 1.0], [1.0, 2.0, None, 4.0]],
            "i": [10.0, 10.0],
        }
    )
    af.forward = af.a.projection.accumulate(initial=af.i, multiplier=af.m, addend=af.a)
    af.backward = af.a.projection.accumulate(
        initial=af.i, multiplier=af.m, addend=af.a, reverse=True
    )
    result = af.collect()
    assert result["forward"].to_list() == [
        [21.0, None, None, None],
        [21.0, 44.0, None, None],
    ]
    assert result["backward"].to_list() == [
        [None, None, 124.0, 41.0],
        [None, None, None, 24.0],
    ]


def test_a_lost_step_loses_every_earlier_position_under_reverse() -> None:
    """The null runs toward period zero, the direction the run travels.

    A run that skipped the hole and carried on would report 124 * 2 + 1 at
    position 0 -- a reserve with a period's discounting missing from under
    it, with nothing wrong on the face of it.
    """
    af = ActuarialFrame(
        {"m": [[2.0, None, 3.0, 4.0]], "a": [[1.0, 1.0, 1.0, 1.0]], "i": [10.0]}
    )
    af.backward = af.a.projection.accumulate(
        initial=af.i, multiplier=af.m, addend=af.a, reverse=True
    )
    assert _collected(af, "backward") == [[None, None, 124.0, 41.0]]


def test_a_null_opening_state_nulls_the_whole_run_either_way() -> None:
    af = ActuarialFrame({"m": [[2.0, 3.0]], "a": [[1.0, 1.0]], "i": [None]})
    af.backward = af.a.projection.accumulate(
        initial=af.i, multiplier=af.m, addend=af.a, reverse=True
    )
    assert _collected(af, "backward") == [[None, None]]


def test_zero_and_negative_multipliers_are_ordinary_values_backward() -> None:
    """Stepped, never divided out: a division would have no answer past the zero."""
    af = ActuarialFrame({"m": [[-1.0, 0.0, 2.0]], "a": [[1.0, 1.0, 1.0]]})
    af.backward = af.a.projection.accumulate(
        initial=4.0, multiplier=af.m, addend=af.a, reverse=True
    )
    assert _collected(af, "backward") == [[0.0, 1.0, 9.0]]


def test_a_literal_multiplier_broadcasts_along_each_policy_s_own_periods() -> None:
    """GSP-156's broadcast, run backward: each policy's own length repeats it.

    s[1] = 100 * 0.5 + 20 = 70 and s[0] = 70 * 0.5 + 10 = 45; the one-period
    policy is 10 * 0.5 + 1 = 6.
    """
    af = ActuarialFrame({"opening": [100.0, 10.0], "flow": [[10.0, 20.0], [1.0]]})
    af.backward = af.flow.projection.accumulate(
        initial=af.opening, multiplier=0.5, addend=af.flow, reverse=True
    )
    assert _collected(af, "backward") == [[45.0, 70.0], [6.0]]


def test_a_literal_addend_broadcasts_along_each_policy_s_own_periods() -> None:
    """s[1] = 1 * 3 + 1 = 4 and s[0] = 4 * 2 + 1 = 9; the short one 1 * 2 + 1."""
    af = ActuarialFrame({"rate": [[2.0, 3.0], [2.0]]})
    af.backward = af.rate.projection.accumulate(
        initial=1.0, multiplier=af.rate, addend=1.0, reverse=True
    )
    assert _collected(af, "backward") == [[9.0, 4.0], [3.0]]


def test_the_forward_recurrence_is_unchanged() -> None:
    """``reverse=False`` is today's recurrence, value for value."""
    af = ActuarialFrame(
        {
            "av_init": [1000.0, 2000.0],
            "growth": [[1.01, 1.01, 1.01], [1.02, 1.02, 1.02]],
            "net_flow": [[50.0, 50.0, 50.0], [100.0, 100.0, 100.0]],
        }
    )
    af.av = af.growth.projection.accumulate(
        initial=af.av_init, multiplier=af.growth, addend=af.net_flow
    )
    af.av_stated = af.growth.projection.accumulate(
        initial=af.av_init, multiplier=af.growth, addend=af.net_flow, reverse=False
    )
    result = af.collect()
    assert result["av"].to_list() == [
        [1060.0, 1120.6, 1181.8059999999998],
        [2140.0, 2282.8, 2428.456],
    ]
    assert _bits(result["av"].to_list()) == _bits(result["av_stated"].to_list())


@pytest.mark.parametrize("written", [1, 0, "yes", None])
def test_a_direction_that_is_not_true_or_false_is_refused(written: object) -> None:
    """The direction is the calculation, so it is never read out of a number."""
    af = ActuarialFrame({"a": [[1.0, 2.0]]})
    with pytest.raises(TypeError, match=r"reverse=\.\.\.\) takes True or False"):
        af.a.projection.accumulate(
            initial=0.0,
            multiplier=1.0,
            addend=af.a,
            reverse=written,  # type: ignore[arg-type]
        )


# --- the record --------------------------------------------------------------


@pytest.mark.parametrize("reverse", [False, True])
def test_the_direction_is_always_on_the_record(*, reverse: bool) -> None:
    """``reverse`` is written whichever way the run went, as ``cum_sum``'s is."""
    af = ActuarialFrame({"a": [[1.0, 2.0]], "m": [[0.5, 0.5]]})
    af.run = af.a.projection.accumulate(
        initial=0.0, multiplier=af.m, addend=af.a, reverse=reverse
    )
    tree = fold(af).op_trees["run@1"]
    assert isinstance(tree, Call)
    assert tree.name == "projection.accumulate"
    assert tree.attrs == (("reverse", reverse),)


def test_two_directions_are_two_digests() -> None:
    """The account carried forward and the reserve rolled back are two columns."""
    af = ActuarialFrame({"a": [[1.0, 2.0]], "m": [[0.5, 0.5]]})
    af.forward = af.a.projection.accumulate(initial=0.0, multiplier=af.m, addend=af.a)
    af.backward = af.a.projection.accumulate(
        initial=0.0, multiplier=af.m, addend=af.a, reverse=True
    )
    nodes = {
        node["id"]: node
        for node in json.loads(GraphExporter(af).export(profile="executable"))["nodes"]
    }
    assert (
        nodes["forward@1"]["local_fingerprint"]
        != nodes["backward@1"]["local_fingerprint"]
    )


def test_a_tree_written_before_the_attribute_runs_forward() -> None:
    """A tree from before 11.1.20 stated a direction meant the forward one."""
    frame = pl.DataFrame({"i": [10.0], "m": [[2.0, 3.0]], "a": [[1.0, 1.0]]})
    older = Call("projection.accumulate", (Col("i"), Col("m"), Col("a")))
    stated = Call(
        "projection.accumulate",
        (Col("i"), Col("m"), Col("a")),
        (("reverse", False),),
    )
    assert (
        frame.select(lower(older).alias("x"))["x"].to_list()
        == frame.select(lower(stated).alias("x"))["x"].to_list()
        == [[21.0, 64.0]]
    )


def test_the_walk_through_says_which_way_the_run_went() -> None:
    af = ActuarialFrame({"a": [[1.0, 2.0]], "m": [[0.5, 0.5]]})
    af.backward = af.a.projection.accumulate(
        initial=0.0, multiplier=af.m, addend=af.a, reverse=True
    )
    sentence = sentence_for(fold(af).op_trees["backward@1"], None)
    assert sentence == (
        "the linear recurrence: each state is the state the run just left x m + a, "
        "run backwards from the end of the projection and opening at 0.0"
    )


def test_every_operand_of_the_backward_recurrence_is_in_every_period() -> None:
    """An impact cone through a rollback sweeps the whole axis, from t to the end.

    The step operands are read over this period and every later one -- the
    window section 9 has ``accumulate(reverse=True)`` state, ``{0, last}`` -- and
    the opening value over no window: it is where the run starts.
    """
    tree = Call(
        "projection.accumulate",
        (Col("opening"), Col("v"), Col("cf")),
        (("reverse", True),),
    )
    from_now_to_the_end = claim_over(AGGREGATION, (Periods(0, "last"),))
    assert classify_reads(tree) == {
        "opening": ReadClaim(AGGREGATION),
        "v": from_now_to_the_end,
        "cf": from_now_to_the_end,
    }


# --- A1: list.reverse --------------------------------------------------------


def test_each_policy_is_reversed_within_its_own_length() -> None:
    af = ActuarialFrame({"x": [[10.0, 20.0, 30.0], [5.0], []]})
    af.turned = af.x.list.reverse()
    assert _collected(af, "turned") == [[30.0, 20.0, 10.0], [5.0], []]


def test_a_null_moves_with_its_position_and_stays_null() -> None:
    """A permutation combines nothing, so nothing beside the null is lost."""
    af = ActuarialFrame({"x": [[1.0, None, 3.0], None, [None, 2.0]]})
    af.turned = af.x.list.reverse()
    assert _collected(af, "turned") == [[3.0, None, 1.0], None, [2.0, None]]


@pytest.mark.parametrize(
    ("values", "dtype"),
    [
        ([[1, 2, 3]], pl.List(pl.Int64)),
        ([[True, False]], pl.List(pl.Boolean)),
        ([["issue", "maturity"]], pl.List(pl.String)),
    ],
    ids=["i64", "bool", "str"],
)
def test_the_element_type_is_kept(values: list[Any], dtype: pl.DataType) -> None:
    af = ActuarialFrame(pl.DataFrame({"x": values}, schema={"x": dtype}))
    af.turned = af.x.list.reverse()
    result = af.collect()
    assert result.schema["turned"] == dtype
    assert result["turned"].to_list() == [values[0][::-1]]


def test_a_per_policy_value_has_no_periods_to_turn() -> None:
    af = ActuarialFrame({"x": [1.0, 2.0]})
    with pytest.raises(TypeError, match=r"list\.reverse"):
        af.x.list.reverse()


def test_a_reversal_is_a_declared_core_node_not_an_engine_fragment() -> None:
    af = ActuarialFrame({"x": [[1.0, 2.0]]})
    af.turned = af.x.list.reverse()
    tree = fold(af).op_trees["turned@1"]
    assert tree == Call("list.reverse", (Col("x"),))
    nodes = {
        node["id"]: node for node in json.loads(GraphExporter(af).export())["nodes"]
    }
    assert nodes["turned@1"]["tier"] == "core"
    assert nodes["turned@1"]["engines"] == []


def test_the_escape_spelling_is_pointed_at_the_declared_one() -> None:
    """Two spellings of one calculation would record two different things."""
    af = ActuarialFrame({"x": [[1.0, 2.0]]})
    with pytest.raises(ValueError, match=r"Drop \.polars_native\(\) from this line"):
        af.x.polars_native().list.reverse()


def test_a_reversed_operand_is_read_across_the_whole_axis() -> None:
    """Period t reads period T-1-t: no single offset, so AGGREGATION, no offset.

    And no single distance or end either, so the window is the whole run --
    the tightest ``periods`` can write for a read that turns on the
    policy's own length.
    """
    assert classify_reads(Call("list.reverse", (Col("cf"),))) == {
        "cf": claim_over(AGGREGATION, (Periods("first", "last"),))
    }


def test_the_walk_through_names_the_reversal() -> None:
    assert sentence_for(Call("list.reverse", (Col("cf"),)), None) == (
        "cf turned end for end within each policy's own periods, its last period first"
    )


def test_a_reversal_carrying_an_attribute_is_refused() -> None:
    frame = pl.DataFrame({"x": [[1.0, 2.0]]})
    with pytest.raises(TypeError, match="has nothing to configure"):
        frame.select(lower(Call("list.reverse", (Col("x"),), (("k", 1),))))


# --- A2 equals A1, to the bit -----------------------------------------------


def _a_jagged_book(seed: int, policies: int = 200) -> pl.DataFrame:
    """Return a book of random doubles over policies of different lengths."""
    rng = random.Random(seed)  # noqa: S311 -- reproducible test data, not secrets
    lengths = [rng.randrange(0, 40) for _ in range(policies)]
    return pl.DataFrame(
        {
            "opening": [rng.uniform(-50.0, 50.0) for _ in lengths],
            "v": [[rng.uniform(-1.5, 1.5) for _ in range(n)] for n in lengths],
            "cf": [[rng.uniform(-100.0, 100.0) for _ in range(n)] for n in lengths],
        },
        schema={
            "opening": pl.Float64,
            "v": pl.List(pl.Float64),
            "cf": pl.List(pl.Float64),
        },
    )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_named_rollback_equals_reverse_accumulate_reverse_to_the_bit(
    seed: int,
) -> None:
    af = ActuarialFrame(_a_jagged_book(seed))
    af.named = af.cf.projection.accumulate(
        initial=af.opening, multiplier=af.v, addend=af.cf, reverse=True
    )
    af.v_r = af.v.list.reverse()
    af.cf_r = af.cf.list.reverse()
    af.forward_r = af.cf_r.projection.accumulate(
        initial=af.opening, multiplier=af.v_r, addend=af.cf_r
    )
    af.three_step = af.forward_r.list.reverse()
    result = af.collect()
    assert _bits(result["named"].to_list()) == _bits(result["three_step"].to_list())


def test_a_loop_over_the_clause_agrees_to_the_bit() -> None:
    """The lowering against the clause's own definition, written out as a loop."""
    book = _a_jagged_book(7)
    af = ActuarialFrame(book)
    af.named = af.cf.projection.accumulate(
        initial=af.opening, multiplier=af.v, addend=af.cf, reverse=True
    )
    got = af.collect()["named"].to_list()
    want: list[list[float]] = []
    for opening, vs, cfs in book.iter_rows():
        state, out = opening, [0.0] * len(vs)
        for t in range(len(vs) - 1, -1, -1):
            state = vs[t] * state + cfs[t]
            out[t] = state
        want.append(out)
    assert _bits(got) == _bits(want)
    assert all(math.isfinite(x) for row in got for x in row)


# --- the room's shape: an NPR rollback, portable ------------------------------


def _npr_rollback(*, three_step: bool) -> ActuarialFrame:
    """Return a VM-20 NPR-shaped rollback over a jagged book, in one spelling."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "q": [[0.01, 0.02, 0.03, 0.04], [0.05, 0.06], [0.02, 0.02, 0.02]],
                "benefit": [1000.0, 500.0, 2000.0],
                "premium": [12.0, 30.0, 40.0],
            }
        )
    )
    af.v = af.q * 0.0 + 1.0 / 1.04
    af.net_cf = af.benefit * af.q - af.premium
    if three_step:
        af.cf_r = af.net_cf.list.reverse()
        af.v_r = af.v.list.reverse()
        af.acc = af.cf_r.projection.accumulate(
            initial=0.0, multiplier=af.v_r, addend=af.cf_r
        )
        af.npr = af.acc.list.reverse()
    else:
        af.npr = af.net_cf.projection.accumulate(
            initial=0.0, multiplier=af.v, addend=af.net_cf, reverse=True
        )
    return af


@pytest.mark.parametrize("three_step", [False, True], ids=["named", "three-step"])
def test_the_npr_rollback_is_core_throughout_and_reads_as_portable_to_jax(
    *, three_step: bool
) -> None:
    """No node is engine text, and the portability reading against jax is clean."""
    af = _npr_rollback(three_step=three_step)
    artifact: dict[str, Any] = json.loads(
        GraphExporter(af).export(profile="executable")
    )
    computed = [node for node in artifact["nodes"] if node["kind"] == "computed"]
    assert {node["tier"] for node in computed} == {"core"}
    assert all(node["engines"] == [] for node in computed)
    report = validate_artifact(artifact, engine="jax", deep=True)
    assert report.ok, report.findings
    assert [
        f
        for f in report.findings
        if f.section == "portability" and f.severity == "error"
    ] == []


def test_the_two_npr_spellings_are_the_same_reserve() -> None:
    named = _npr_rollback(three_step=False).collect()["npr"].to_list()
    three = _npr_rollback(three_step=True).collect()["npr"].to_list()
    assert _bits(named) == _bits(three)
    assert [len(row) for row in named] == [4, 2, 3]
