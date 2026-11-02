# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a join key drives: every column the join brought in, and past them.

A column a join brings in holds whichever row of the other table its key
matched, so the key decides its value -- change a policy's product code and
its commission rate is another product's. The graph used to record the key as
an attribute of the join and read nothing, which left ``dependents`` answering
``()`` and ``affected`` answering the key alone: the comfortable answer the
query surface refuses to give for a name it does not know, given for a name it
does. A reviewer bounding a restatement with ``affected`` under-scoped it the
moment a join was involved.

The rule now: every column a join brings in reads the key or keys it was
matched on, as the left side names them, bound to the definition each key held
when the join ran, and each read is ``INDIRECT``/``JOIN`` -- the key selected
the row, as a lookup key does. Everything below is that rule met by the join
forms the frame supports.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import Call
from gaspatchio._semantic.join_keys import join_on_attribute
from gaspatchio.frame.graph import (
    GraphExporter,
    inspect_execution,
    validate_artifact,
)
from gaspatchio.frame.graph.edges import join_keys
from gaspatchio.frame.graph.graph_builder import fold

# --- the book and the tables it is joined to ---------------------------------

_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "product_id": ["A", "B", "A"],
        "issue_age": [35, 45, 35],
        "premium": [100.0, 200.0, 300.0],
    }
)

_PRODUCTS = pl.DataFrame(
    {"product_id": ["A", "B"], "rate": [0.1, 0.2], "fee": [5.0, 6.0]}
)

# The reproduction's right side: one column, the commission rate.
_RATES = pl.DataFrame({"product_id": ["A", "B"], "rate": [0.1, 0.2]})


def _commission_model() -> ActuarialFrame:
    """Return the reproduction: a rate joined in, and a commission struck on it."""
    af = ActuarialFrame(_BOOK).join(_RATES, on="product_id")
    af.commission_rate = af.rate * 1.0
    af.commission = af.commission_rate * af.premium
    return af


def _joined_reads(af: ActuarialFrame) -> dict[str, tuple[str, ...]]:
    """Return what each column the join brought in reads, by node id."""
    return {
        node.id: node.data.reads
        for node in fold(af).nodes.values()
        if node.data.provenance is not None and node.data.provenance.value == "join"
    }


def _edge_classes(af: ActuarialFrame) -> dict[tuple[str, str], tuple[str, str]]:
    """Return every edge's two-word classification, keyed by its two ends."""
    return {
        (edge.source, edge.target): (edge.relationship, edge.subtype)
        for edge in fold(af).edges
    }


# --- the reproduction ---------------------------------------------------------


def test_the_key_a_join_matched_on_has_the_joined_columns_as_dependents() -> None:
    """``dependents`` of the key is the join, where it used to be ``()``."""
    assert _commission_model().graph.dependents("product_id") == ("rate@1",)


def test_affected_follows_a_join_key_through_everything_downstream() -> None:
    """Restate the product a policy is on, and its commission moves with it."""
    assert _commission_model().graph.affected("product_id") == (
        "product_id",
        "rate@1",
        "commission_rate@1",
        "commission@1",
    )


def test_a_joined_in_column_still_answers_for_its_own_cone() -> None:
    """What already worked keeps working: the rate reaches the commission."""
    assert _commission_model().graph.affected("rate") == (
        "rate@1",
        "commission_rate@1",
        "commission@1",
    )


# --- what the read is -----------------------------------------------------------


def test_every_column_a_join_brings_in_reads_the_key() -> None:
    """One join, two arriving columns, one key: both read it."""
    af = ActuarialFrame(_BOOK).join(_PRODUCTS, on="product_id")

    assert _joined_reads(af) == {
        "rate@1": ("product_id",),
        "fee@1": ("product_id",),
    }


def test_a_join_key_is_an_indirect_join_read() -> None:
    """The key selected the row, as a lookup key does; it is not the value."""
    af = ActuarialFrame(_BOOK).join(_PRODUCTS, on="product_id")

    edges = _edge_classes(af)

    assert edges[("product_id", "rate@1")] == ("INDIRECT", "JOIN")
    assert edges[("product_id", "fee@1")] == ("INDIRECT", "JOIN")


def test_a_multi_key_join_reads_every_key_in_the_order_given() -> None:
    """A rate keyed on product and age is chosen by both."""
    rates = pl.DataFrame(
        {"product_id": ["A", "B"], "issue_age": [35, 45], "loading": [0.01, 0.02]}
    )
    af = ActuarialFrame(_BOOK).join(rates, on=["issue_age", "product_id"])

    assert _joined_reads(af) == {"loading@1": ("issue_age", "product_id")}
    assert af.graph.affected("issue_age") == ("issue_age", "loading@1")


def test_left_on_and_right_on_read_the_keys_this_frame_holds() -> None:
    """The right side's names are the other table's; the reads are this frame's."""
    book = _BOOK.rename({"product_id": "product_code"})
    af = ActuarialFrame(book).join(
        _PRODUCTS, left_on="product_code", right_on="product_id"
    )

    assert _joined_reads(af) == {
        "rate@1": ("product_code",),
        "fee@1": ("product_code",),
    }


def test_several_differently_named_keys_read_the_left_side_in_order() -> None:
    """``left_on`` and ``right_on`` as lists: the left list, as given."""
    book = _BOOK.rename({"product_id": "product_code", "issue_age": "age"})
    rates = pl.DataFrame(
        {"product_id": ["A", "B"], "issue_age": [35, 45], "loading": [0.01, 0.02]}
    )
    af = ActuarialFrame(book).join(
        rates, left_on=["product_code", "age"], right_on=["product_id", "issue_age"]
    )

    assert _joined_reads(af) == {"loading@1": ("product_code", "age")}


def test_a_key_read_by_a_join_and_by_arithmetic_is_read_both_ways() -> None:
    """Two readers of one column, each read the way it was made."""
    rates = pl.DataFrame({"issue_age": [35, 45], "loading": [0.01, 0.02]})
    af = ActuarialFrame(_BOOK).join(rates, on="issue_age")
    af.attained_age = af.issue_age + 1
    af.loaded_premium = af.premium * (1.0 + af.loading)

    edges = _edge_classes(af)

    assert af.graph.dependents("issue_age") == ("loading@1", "attained_age@1")
    assert edges[("issue_age", "loading@1")] == ("INDIRECT", "JOIN")
    assert edges[("issue_age", "attained_age@1")] == ("DIRECT", "TRANSFORMATION")
    assert af.graph.affected("issue_age") == (
        "issue_age",
        "loading@1",
        "attained_age@1",
        "loaded_premium@1",
    )


def test_a_join_reads_the_definition_its_key_held_when_the_join_ran() -> None:
    """A key rewritten after the join is not the key the join matched on."""
    rates = pl.DataFrame({"band": [3, 4], "loading": [0.01, 0.02]})
    af = ActuarialFrame(_BOOK)
    af.band = af.issue_age // 10
    af = af.join(rates, on="band")
    af.band = af.band * 10

    assert af.graph.precedents("loading") == ("band@1",)
    assert af.graph.affected("band@1") == ("band@1", "loading@1", "band@2")
    assert af.graph.affected("band@2") == ("band@2",)


# --- the join kinds -------------------------------------------------------------


@pytest.mark.parametrize("how", ["left", "inner", "right", "full"])
def test_every_keyed_join_kind_reads_its_key(how: str) -> None:
    """Which rows survive is the kind's business; which row matched is the key's."""
    af = ActuarialFrame(_BOOK).join(_PRODUCTS, on="product_id", how=how)

    reads = _joined_reads(af)

    assert reads
    assert set(reads.values()) == {("product_id",)}


def test_a_full_join_s_own_copy_of_the_key_reads_the_key_too() -> None:
    """Where the right side's key column arrives as a column, it arrived by the key."""
    af = ActuarialFrame(_BOOK).join(_PRODUCTS, on="product_id", how="full")

    assert _joined_reads(af)["product_id_right@1"] == ("product_id",)


def test_a_cross_join_states_no_key_and_reads_nothing() -> None:
    """Every row pairs with every row: no column chose the pairing."""
    scenarios = pl.DataFrame({"scenario": ["base", "stress"], "shock": [1.0, 1.1]})
    af = ActuarialFrame(_BOOK).join(scenarios, how="cross")

    assert _joined_reads(af) == {"scenario@1": (), "shock@1": ()}


@pytest.mark.parametrize("how", ["semi", "anti"])
def test_a_join_that_brings_nothing_mints_nothing(how: str) -> None:
    """No arriving column, so no node, and nothing for a key to be read by."""
    af = ActuarialFrame(_BOOK).join(_PRODUCTS, on="product_id", how=how)

    assert _joined_reads(af) == {}
    assert af.graph.dependents("product_id") == ()


def test_a_lazy_right_side_still_reads_its_key() -> None:
    """A deferred right side records no fingerprint, and the key read all the same."""
    af = ActuarialFrame(_BOOK).join(_PRODUCTS.lazy(), on="product_id")

    assert _joined_reads(af) == {
        "rate@1": ("product_id",),
        "fee@1": ("product_id",),
    }


# --- affected() bounds a restatement --------------------------------------------


def _banded_model(book: pl.DataFrame) -> ActuarialFrame:
    """Return a model whose rate is joined on a band the model computes from age."""
    rates = pl.DataFrame({"band": ["young", "old"], "rate": [0.001, 0.004]})
    af = ActuarialFrame(book)
    af.band = when(af.issue_age < 40).then(pl.lit("young")).otherwise(pl.lit("old"))
    af = af.join(rates, on="band", maintain_order="left")
    af.risk_premium = af.premium * af.rate
    af.reserve = af.risk_premium * 0.5
    af.admin = af.premium * 0.01
    return af


def test_affected_bounds_a_restatement_that_crosses_a_join() -> None:
    """Every column a restated age moves is inside ``affected('issue_age')``.

    The age is restated for one policy, far enough to change its band. The
    band is a join key, so the rate is another row's, and the premium and
    reserve struck on it move too. Each column whose values moved is compared
    with the cone ``affected`` drew, which is the promise the method makes to
    a reviewer scoping a re-run: nothing outside it moved.
    """
    restated = _BOOK.with_columns(pl.Series("issue_age", [35, 45, 55]))
    before = _banded_model(_BOOK)
    before_values = before.collect()
    after_values = _banded_model(restated).collect()

    moved = {
        column
        for column in before_values.columns
        if not before_values[column].equals(after_values[column])
    }
    cone = {
        before.graph._graph.nodes[node_id].data.column  # noqa: SLF001 -- the node's own column
        for node_id in before.graph.affected("issue_age")
    }

    assert moved == {"issue_age", "band", "rate", "risk_premium", "reserve"}
    assert moved <= cone
    assert "admin" not in cone


# --- the record, written out ----------------------------------------------------


def test_a_joined_model_s_artifact_holds_to_every_reading() -> None:
    """The key read is on the document, and the document still checks out."""
    af = _commission_model()
    document = json.loads(GraphExporter(af).export(af.collect(), profile="executable"))

    joined = next(node for node in document["nodes"] if node["id"] == "rate@1")
    narrowed = joined["facets"]["gaspatchio_column_transformation"]["reads"]
    verdict = validate_artifact(document, deep=True)

    assert joined["reads"] == ["product_id"]
    assert narrowed == [
        {
            "source": "product_id",
            "transformations": [{"type": "INDIRECT", "subtype": "JOIN"}],
        }
    ]
    assert {
        "source": "product_id",
        "target": "rate@1",
        "relationship": "INDIRECT",
    } in document["edges"]
    assert verdict.ok, [finding.message for finding in verdict.findings]
    assert not inspect_execution(document).findings


# --- the attribute the key travels in -------------------------------------------


@pytest.mark.parametrize(
    ("on", "left_on", "right_on", "keys"),
    [
        ("product_id", None, None, ("product_id",)),
        (["product_id", "issue_age"], None, None, ("product_id", "issue_age")),
        (None, "pol_num", "policy_id", ("pol_num",)),
        (None, ["a", "b"], ["x", "y"], ("a", "b")),
        (None, None, None, ()),
    ],
)
def test_the_key_the_join_writes_is_the_key_the_graph_reads(
    on: str | list[str] | None,
    left_on: str | list[str] | None,
    right_on: str | list[str] | None,
    keys: tuple[str, ...],
) -> None:
    """The writer and the reader of the ``on`` attribute agree, form by form."""
    written = Call("join", (), (("on", join_on_attribute(on, left_on, right_on)),))

    assert join_keys(written) == keys


# --- a key name the record has to carry ---------------------------------------


_CODES = ["A", "B", "A"]


@pytest.mark.parametrize(
    ("book", "rates", "keys", "named"),
    [
        (
            {"prod,code": _CODES},
            {"prod,code": ["A", "B"]},
            {"on": "prod,code"},
            "prod,code",
        ),
        (
            {"policy_id": [1, 2, 3], "a=b": _CODES},
            {"policy_id": [1, 2], "a=b": ["A", "B"]},
            {"on": ["policy_id", "a=b"]},
            "a=b",
        ),
        (
            {"prod,code": _CODES},
            {"product_id": ["A", "B"]},
            {"left_on": "prod,code", "right_on": "product_id"},
            "prod,code",
        ),
        (
            {"product_id": _CODES},
            {"code=x": ["A", "B"]},
            {"left_on": "product_id", "right_on": "code=x"},
            "code=x",
        ),
    ],
    ids=["comma-on", "equals-in-a-list", "comma-left", "equals-right"],
)
def test_a_key_name_the_record_cannot_carry_is_refused_by_name(
    book: dict[str, list[object]],
    rates: dict[str, list[object]],
    keys: dict[str, object],
    named: str,
) -> None:
    """A comma or an equals sign in a key's name would read back as other keys.

    The join's record writes its keys in one attribute separated by those two
    characters, so a key called ``prod,code`` would be recorded as the two
    keys ``prod`` and ``code`` -- a lineage of columns the model never
    matched on. Polars itself joins on the name happily; the frame refuses it
    before anything changes, naming the column and the move: rename it before
    the join.
    """
    left = pl.DataFrame({**book, "premium": [100.0, 200.0, 300.0]})
    right = pl.DataFrame({**rates, "rate": [0.1, 0.2]})
    assert left.join(right, how="left", **keys).height == left.height  # type: ignore[arg-type]
    af = ActuarialFrame(left)
    before = list(af.columns)

    with pytest.raises(ValueError, match="rename") as refused:
        af.join(right, **keys)  # type: ignore[arg-type]

    assert repr(named) in str(refused.value)
    assert list(af.columns) == before


def test_a_key_with_spaces_in_its_name_is_read_as_written() -> None:
    """A column called ``" code "`` is not the column called ``"code"``.

    The record's reader trims nothing, so the key the join matched on is the
    key its columns read, and the document's executable reading binds it.
    """
    book = _BOOK.rename({"product_id": " code "})
    rates = _RATES.rename({"product_id": " code "})
    af = ActuarialFrame(book).join(rates, on=" code ")
    af.commission = af.rate * af.premium

    assert af.graph.precedents("rate") == (" code ",)
    assert "rate@1" in af.graph.dependents(" code ")
    document = json.loads(GraphExporter(af).export(profile="executable"))
    assert inspect_execution(document).findings == ()
    assert validate_artifact(document).ok
