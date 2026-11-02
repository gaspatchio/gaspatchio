# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What nothing reads, how far a cone runs, and what a table reaches.

Three questions a reviewer puts to a model that ``af.graph`` and an audit file
now both answer:

- **Which calculations does nothing use?** Each node nothing reads is put
  under one class the record states -- superseded, data, stamp, length only,
  terminal -- and none of them is a guess. A result and dead code both read
  as ``terminal``, because the model does not say which; naming the results
  moves them to ``kept``.
- **How far back, or forward?** A cone runs to the end by default; ``depth``
  cuts it after that many reads.
- **If this assumption table moves, what moves?** ``affected(assumption=)``
  opens the cone at every calculation whose own formula looked the table up.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.graph import GraphDocument
from gaspatchio.rollforward import compile_rollforward


def _projected(columns: dict[str, list[object]]) -> ActuarialFrame:
    """Return a frame over ``columns`` with a three-month timeline set up."""
    return ActuarialFrame(pl.DataFrame(columns)).projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )


def _both(af: ActuarialFrame) -> tuple[Any, Any]:
    """Return the frame's graph and its exported audit file, read back.

    Every question below is asked of both, because the two are one reader.
    """
    return af.graph, GraphDocument(json.loads(GraphExporter(af).export()))


# --- one fixture per class ------------------------------------------------------


def test_a_definition_replaced_before_anything_read_it_is_superseded() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0], "q": [0.01]}))
    af.claims = af.sum_assured * af.q
    af.claims = af.sum_assured * af.q * 1.05

    for asked in _both(af):
        assert asked.unused().superseded == ("claims@1",)


def test_a_definition_its_replacement_read_is_not_unused() -> None:
    """The reassignment idiom: the second line reads the first, so it is used."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0], "q": [0.01]}))
    af.claims = af.sum_assured * af.q
    af.claims = af.claims * 1.05

    assert af.graph.unused().superseded == ()
    assert af.graph.unused().terminal == ("claims@2",)


def test_an_arriving_or_joined_column_nothing_reads_is_data() -> None:
    products = pl.DataFrame({"product": ["term"], "commission_rate": [0.05]})
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": ["A"], "product": ["term"], "premium": [1_200.0]})
    )
    af = af.join(products, on="product")
    af.charge = af.premium * 0.01

    for asked in _both(af):
        assert asked.unused().data == ("policy_id", "commission_rate@1")


def test_a_column_the_projection_set_up_that_nothing_reads_is_a_stamp() -> None:
    af = _projected({"premium": [1_200.0]})
    af.premiums = af.premium * (af.month * 0 + 1)

    for asked in _both(af):
        assert asked.unused().stamp == (
            "projection_start_date@1",
            "projection_end_date@1",
            "num_proj_months@1",
        )


def test_a_column_read_only_for_its_length_is_length_only() -> None:
    af = _projected({"smoker": ["N"]})
    af.smoker_by_period = af.smoker.projection.broadcast_to_periods(like=af.month)

    for asked in _both(af):
        unused = asked.unused()
        assert unused.length_only == ("month@1",)
        assert "month@1" not in unused.stamp


def test_a_length_read_beside_a_value_read_is_a_use() -> None:
    af = _projected({"smoker": ["N"]})
    af.smoker_by_period = af.smoker.projection.broadcast_to_periods(like=af.month)
    af.months_elapsed = af.month * 1

    assert af.graph.unused().length_only == ()


def test_a_live_calculation_nothing_reads_is_terminal_and_keep_moves_it() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0], "q": [0.01]}))
    af.claims = af.sum_assured * af.q
    af.check = af.claims * 0.0

    for asked in _both(af):
        unused = asked.unused()
        kept = asked.unused(keep=["claims"])
        assert unused.terminal == ("check@1",)
        assert unused.kept == ()
        assert kept.terminal == ("check@1",)
        assert kept.kept == ()
        assert asked.unused(keep=["check"]).kept == ("check@1",)


def test_keep_names_the_live_definition_and_leaves_dead_code_dead() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0], "q": [0.01]}))
    af.claims = af.sum_assured * af.q
    af.claims = af.sum_assured * 0.02

    kept = af.graph.unused(keep=["claims"])

    assert kept.kept == ("claims@2",)
    assert kept.superseded == ("claims@1",)


def test_keep_refuses_a_name_the_graph_does_not_hold() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0], "q": [0.01]}))
    af.claims = af.sum_assured * af.q

    for asked in _both(af):
        with pytest.raises(ValueError, match=r"Did you mean 'claims'"):
            asked.unused(keep=["clams"])


def test_a_column_nothing_accounts_for_is_named_by_holes_not_unused() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.claims = af.sum_assured * 0.01
    plan = af._df  # noqa: SLF001 -- a write past the frame, under test
    assert plan is not None
    af._df = plan.with_columns(pl.lit(1.0).alias("mystery"))  # noqa: SLF001

    for asked in _both(af):
        assert [hole.column for hole in asked.holes()] == ["mystery"]
        assert "mystery" not in [
            node for name in ("data", "terminal") for node in asked.unused().of(name)
        ]


def test_a_balance_column_nothing_reads_is_terminal_though_its_state_is_read() -> None:
    """Delete the line and nothing changes: the state machine reads the state."""
    af = _projected({"av_init": [100.0], "rate": [[0.01] * 4]})
    builder = af.projection.rollforward(states={"fund": af["av_init"]})
    builder["fund"].grow(af["rate"], label="growth")
    af.fund = compile_rollforward(builder).expr_for("fund")

    assert af.graph.dependents("fund") != ()
    assert af.graph.unused().terminal == ("fund@1",)


def test_counts_state_every_class_and_of_refuses_an_unknown_one() -> None:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.claims = af.sum_assured * 0.01
    unused = af.graph.unused()

    assert unused.counts == {
        "superseded": 0,
        "data": 0,
        "stamp": 0,
        "length_only": 0,
        "terminal": 1,
        "kept": 0,
    }
    with pytest.raises(ValueError, match="not a class"):
        unused.of("dead")


# --- depth ---------------------------------------------------------------------


def _chain() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"a": [1.0]}))
    af.b = af.a * 2
    af.c = af.b * 2
    af.d = af.c * 2
    return af


def test_depth_cuts_the_cone_after_that_many_reads_both_ways() -> None:
    for asked in _both(_chain()):
        assert asked.trace("d", depth=0) == ("d@1",)
        assert asked.trace("d", depth=2) == ("b@1", "c@1", "d@1")
        assert asked.trace("d") == ("a", "b@1", "c@1", "d@1")
        assert asked.affected("a", depth=1) == ("a", "b@1")


@pytest.mark.parametrize("depth", [-1, 1.5, True])
def test_a_depth_that_is_not_a_number_of_reads_is_refused(depth: object) -> None:
    with pytest.raises(ValueError, match="not a number of reads"):
        _chain().graph.trace("d", depth=depth)  # type: ignore[arg-type]


# --- the cone of an assumption table ---------------------------------------------


def _priced() -> ActuarialFrame:
    lapse = Table(
        name="unused_and_cones_lapse",
        source=pl.DataFrame({"year": [1, 2], "rate": [0.05, 0.03]}),
        dimensions={"year": "year"},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"year": [1], "premium": [1_200.0]}))
    af.lapse_rate = lapse.lookup(year=af.year)
    af.lapses = af.premium * af.lapse_rate
    af.commission = af.premium * 0.05
    return af


def test_affected_of_an_assumption_opens_at_every_reader_of_the_table() -> None:
    for asked in _both(_priced()):
        assert asked.affected(assumption="unused_and_cones_lapse") == (
            "lapse_rate@1",
            "lapses@1",
        )


def test_affected_refuses_an_assumption_nothing_reads_with_the_near_names() -> None:
    for asked in _both(_priced()):
        with pytest.raises(ValueError, match="Did you mean 'unused_and_cones_lapse'"):
            asked.affected(assumption="unused_and_cones_lpse")
        with pytest.raises(ValueError, match="key it was matched on"):
            asked.affected(assumption="products")


def test_affected_takes_a_column_or_an_assumption_and_not_both() -> None:
    af = _priced()

    with pytest.raises(ValueError, match="not both"):
        af.graph.affected("premium", assumption="unused_and_cones_lapse")
    with pytest.raises(ValueError, match="not both"):
        af.graph.affected()


# --- the document reader refuses what is not an audit file ---------------------


@pytest.mark.parametrize(
    ("document", "said"),
    [
        ({}, "carries no nodes array"),
        ({"nodes": [{"id": 1, "reads": []}]}, "without a string id"),
        ({"nodes": [{"id": "x", "reads": ["y"]}]}, "reads 'y', which is no node"),
    ],
)
def test_a_document_without_readable_nodes_is_refused(
    document: dict[str, object], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        GraphDocument(document)
